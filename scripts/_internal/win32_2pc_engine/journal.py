#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Journal transazionale pre-immagine BatchJournalV2 per rollback post-crash."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from . import constants as _consts
from .constants import TwoPhaseCommitError, compute_crc32, compute_sha256
from .io_and_paths import (
    _atomic_write_bytes,
    _get_repo_hash16,
    _replace_with_retry,
    _unlink_with_retry,
    _win_long_path,
)
from .mutex import Win32NamedMutex


class BatchJournalV2:
    """Journal transazionale pre-immagine su disco per il ripristino atomico batch post-crash."""

    @staticmethod
    def get_journal_root(root: Union[str, Path]) -> Path:
        """Restituisce %TEMP%\\nk_2pc_journal_<repo_hash16> per il repository target."""
        return Path(tempfile.gettempdir()) / f"nk_2pc_journal_{_get_repo_hash16(root)}"

    @classmethod
    def _write_json_fsync(cls, target_json: Path, payload: Dict[str, Any]) -> None:
        _win_long_path(target_json.parent).mkdir(parents=True, exist_ok=True)
        tmp_json = (
            target_json.parent
            / f".{target_json.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
        )
        raw = json.dumps(payload, indent=2).encode("utf-8")
        try:
            with open(_win_long_path(tmp_json), "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            _replace_with_retry(tmp_json, target_json)
        finally:
            if _win_long_path(tmp_json).exists():
                try:
                    _win_long_path(tmp_json).unlink(missing_ok=True)
                except OSError:
                    pass

    @classmethod
    def begin_batch(
        cls,
        root: Path,
        targets: List[Tuple[str, Path]],
    ) -> Tuple[str, Path, Path]:
        """Salva copie binarie pre-immagine con fsync e pubblica active_batch.json."""
        journal_root = cls.get_journal_root(root)
        batch_id = f"batch_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        batch_dir = journal_root / batch_id
        preimages_dir = batch_dir / "preimages"
        _win_long_path(preimages_dir).mkdir(parents=True, exist_ok=True)

        seen_real: Set[str] = set()
        entries: List[Dict[str, Any]] = []
        for idx, (rel_str, target_path) in enumerate(targets):
            norm_t = os.path.realpath(str(target_path)).lower().replace("/", "\\")
            if norm_t in seen_real:
                continue
            seen_real.add(norm_t)
            target_lp = _win_long_path(target_path)
            if target_lp.exists() and target_lp.is_file():
                pre_bytes = target_lp.read_bytes()
                pre_sha = compute_sha256(pre_bytes)
                pre_crc = compute_crc32(pre_bytes)
                pre_name = f"{idx:04d}_{pre_sha[:12]}.bin"
                pre_file = preimages_dir / pre_name
                with open(_win_long_path(pre_file), "wb") as pf:
                    pf.write(pre_bytes)
                    pf.flush()
                    os.fsync(pf.fileno())
                entries.append({
                    "index": idx,
                    "relative_path": rel_str,
                    "target_path": str(target_path),
                    "existed_before": True,
                    "preimage_rel": f"preimages/{pre_name}",
                    "preimage_file": str(pre_file),
                    "preimage_sha256": pre_sha,
                    "preimage_crc32": pre_crc,
                })
            else:
                entries.append({
                    "index": idx,
                    "relative_path": rel_str,
                    "target_path": str(target_path),
                    "existed_before": False,
                    "preimage_rel": None,
                    "preimage_file": None,
                    "preimage_sha256": None,
                    "preimage_crc32": None,
                })

        manifest: Dict[str, Any] = {
            "schema_version": "BatchJournalV2",
            "batch_id": batch_id,
            "repo_root": str(root),
            "repo_hash16": _get_repo_hash16(root),
            "batch_dir": str(batch_dir),
            "pid": os.getpid(),
            "timestamp_utc": time.time(),
            "state": "ACTIVE",
            "entries": entries,
        }
        cls._write_json_fsync(batch_dir / "active_batch.json", manifest)
        cls._write_json_fsync(journal_root / "active_batch.json", manifest)
        return batch_id, journal_root, batch_dir

    @classmethod
    def rollback_from_manifest(
        cls,
        manifest: Dict[str, Any],
        batch_dir_fallback: Optional[Path] = None,
    ) -> List[str]:
        """Ripristina le pre-immagini binarie del batch con retry 5x 25ms."""
        restored: List[str] = []
        raw_batch_dir = manifest.get("batch_dir")
        eff_batch_dir = Path(raw_batch_dir) if raw_batch_dir else batch_dir_fallback
        entries = manifest.get("entries", [])
        if not isinstance(entries, list):
            return restored

        for entry in reversed(entries):
            if not isinstance(entry, dict) or not entry.get("target_path"):
                continue
            target_path = Path(entry["target_path"])
            with Win32NamedMutex(target_path, timeout_ms=5000):
                parent_lp = _win_long_path(target_path.parent)
                if parent_lp.exists() and parent_lp.is_dir():
                    for pattern in (
                        f".staging_{target_path.name}.*.tmp",
                        f".shadow_{target_path.name}_*.tmp",
                        f".old_{target_path.name}_*.tmp",
                    ):
                        for leftover in list(parent_lp.glob(pattern)):
                            try:
                                _unlink_with_retry(leftover)
                            except OSError:
                                pass

                if entry.get("existed_before"):
                    pre_candidates: List[Path] = []
                    if entry.get("preimage_file"):
                        pre_candidates.append(Path(entry["preimage_file"]))
                    if eff_batch_dir is not None and entry.get("preimage_rel"):
                        pre_candidates.append(eff_batch_dir / str(entry["preimage_rel"]))
                    pre_src = next(
                        (c for c in pre_candidates if _win_long_path(c).exists()),
                        None,
                    )
                    if pre_src is None:
                        raise TwoPhaseCommitError(
                            f"Pre-immagine journal mancante durante il rollback di {target_path}"
                        )
                    pre_bytes = _win_long_path(pre_src).read_bytes()
                    exp_sha = entry.get("preimage_sha256")
                    if exp_sha and compute_sha256(pre_bytes) != exp_sha:
                        raise TwoPhaseCommitError(
                            f"Corruzione SHA-256 nella pre-immagine journal di {target_path}"
                        )
                    _atomic_write_bytes(target_path, pre_bytes)
                    restored.append(str(target_path))
                else:
                    _unlink_with_retry(target_path)
                    restored.append(str(target_path))
        return restored

    @classmethod
    def cleanup_journal(
        cls,
        journal_root: Path,
        batch_dir: Optional[Path] = None,
    ) -> None:
        """Pulisce active_batch.json, la cartella batch_id e la root journal se vuota."""
        try:
            _unlink_with_retry(journal_root / "active_batch.json")
        except OSError:
            pass
        if batch_dir is not None:
            import shutil

            try:
                _unlink_with_retry(batch_dir / "active_batch.json")
            except OSError:
                pass
            for attempt in range(_consts.RETRY_ATTEMPTS_IO):
                if not _win_long_path(batch_dir).exists():
                    break
                shutil.rmtree(_win_long_path(batch_dir), ignore_errors=True)
                if (
                    _win_long_path(batch_dir).exists()
                    and attempt + 1 < _consts.RETRY_ATTEMPTS_IO
                ):
                    time.sleep(_consts.RETRY_DELAY_SEC_IO)
        try:
            j_lp = _win_long_path(journal_root)
            if j_lp.exists() and j_lp.is_dir() and not any(j_lp.iterdir()):
                j_lp.rmdir()
        except OSError:
            pass

    @classmethod
    def recover_crashed_batches(
        cls,
        root: Path,
    ) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """Ripristina eventuali batch interrotti (es. os._exit(9)) e pulisce la cartella journal."""
        journal_root = cls.get_journal_root(root)
        recovered: List[Dict[str, Any]] = []
        rolled_back_norms: Set[str] = set()
        j_lp = _win_long_path(journal_root)
        if not j_lp.exists() or not j_lp.is_dir():
            return recovered, rolled_back_norms

        active_manifest_file = journal_root / "active_batch.json"
        rollback_clean = True
        if _win_long_path(active_manifest_file).exists():
            try:
                raw_txt = _win_long_path(active_manifest_file).read_text(
                    encoding="utf-8-sig"
                )
                manifest = json.loads(raw_txt)
                batch_id = str(manifest.get("batch_id", "unknown_batch"))
                b_dir = (
                    Path(manifest["batch_dir"])
                    if manifest.get("batch_dir")
                    else (journal_root / batch_id)
                )
                for entry in manifest.get("entries", []):
                    if isinstance(entry, dict) and entry.get("target_path"):
                        rolled_back_norms.add(
                            os.path.realpath(str(entry["target_path"]))
                            .lower()
                            .replace("/", "\\")
                        )
                restored = cls.rollback_from_manifest(manifest, b_dir)
                cls.cleanup_journal(journal_root, b_dir)
                recovered.append({
                    "wal_file": str(active_manifest_file),
                    "tx_id": batch_id,
                    "state": "BATCH_ACTIVE",
                    "action": "ROLLED_BACK_BATCH",
                    "restored_count": len(restored),
                })
            except Exception as exc:
                rollback_clean = False
                recovered.append({
                    "wal_file": str(active_manifest_file),
                    "error": str(exc),
                    "action": "ERROR",
                })

        if (
            rollback_clean
            and not _win_long_path(active_manifest_file).exists()
            and j_lp.exists()
        ):
            import shutil

            for child in list(j_lp.iterdir()):
                if child.is_dir() and not _win_long_path(child / "active_batch.json").exists():
                    shutil.rmtree(child, ignore_errors=True)
            try:
                if j_lp.exists() and not any(j_lp.iterdir()):
                    j_lp.rmdir()
            except OSError:
                pass

        return recovered, rolled_back_norms

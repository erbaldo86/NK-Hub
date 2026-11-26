# -*- coding: utf-8 -*-
"""Journal transazionale multi-lane a 3 stati: PREPARED -> COMMITTED_FS -> FINALIZED."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from _internal.nk_common.isolated_test_runner import safe_rmtree
from _internal.nk_common.lane_paths import extract_lane_id_from_path
from _internal.nk_common.staging_manifest import is_reparse_entry

from . import constants as _consts
from .constants import TwoPhaseCommitError
from .io_and_paths import _get_repo_hash16, _unlink_with_retry, _win_long_path
from .journal import BatchJournalV2

JOURNAL_STATES: Tuple[str, str, str] = ("PREPARED", "COMMITTED_FS", "FINALIZED")
_VALID_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PREPARED": ("COMMITTED_FS", "FINALIZED"),
    "COMMITTED_FS": ("FINALIZED",),
    "FINALIZED": (),
}


class MultiBatchJournalV3:
    """Journal transazionale isolato per batch_id in active_batches/<batch_id>.json."""

    @staticmethod
    def get_active_batches_dir(root: Path) -> Path:
        """Restituisce %TEMP%\\nk_2pc_journal_<repo16>\\active_batches."""
        return BatchJournalV2.get_journal_root(root) / "active_batches"

    @classmethod
    def begin_batch(
        cls,
        root: Path,
        targets: List[Tuple[str, Path]],
        *,
        lane_id: Optional[str] = None,
        milestone: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Path, Path]:
        """Salva pre-immagini binarie con fsync e crea active_batches/<batch_id>.json."""
        active_dir = cls.get_active_batches_dir(root)
        batch_id = f"batch_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        batch_dir = active_dir / batch_id
        preimages_dir = batch_dir / "preimages"
        _win_long_path(preimages_dir).mkdir(parents=True, exist_ok=True)

        entries = BatchJournalV2._collect_preimage_entries(targets, preimages_dir) if hasattr(BatchJournalV2, "_collect_preimage_entries") else cls._collect_entries(targets, preimages_dir)
        eff_lane = lane_id if lane_id is not None else extract_lane_id_from_path(root / ".staging")
        manifest: Dict[str, Any] = {
            "schema_version": "MultiBatchJournalV3",
            "batch_id": batch_id,
            "repo_root": str(Path(root).resolve()),
            "repo_hash16": _get_repo_hash16(root),
            "lane_id": eff_lane or "legacy",
            "milestone": str(milestone or ""),
            "batch_dir": str(batch_dir),
            "pid": os.getpid(),
            "timestamp_utc": time.time(),
            "state": "PREPARED",
            "metadata": dict(metadata or {}),
            "entries": entries,
        }
        journal_file = active_dir / f"{batch_id}.json"
        BatchJournalV2._write_json_fsync(journal_file, manifest)
        return batch_id, journal_file, batch_dir

    @staticmethod
    def _collect_entries(targets: List[Tuple[str, Path]], preimages_dir: Path) -> List[Dict[str, Any]]:
        from .constants import compute_crc32, compute_sha256

        seen_real: set[str] = set()
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
        return entries

    @classmethod
    def transition_state(
        cls,
        journal_file: Path,
        new_state: str,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Valida e persiste la transizione di stato del batch journal."""
        if is_reparse_entry(journal_file):
            raise TwoPhaseCommitError(f"Reparse point vietato su journal {journal_file}")
        manifest = json.loads(_win_long_path(journal_file).read_text(encoding="utf-8-sig"))
        cur_state = str(manifest.get("state") or "")
        allowed = _VALID_TRANSITIONS.get(cur_state, ())
        if new_state not in allowed:
            raise TwoPhaseCommitError(
                f"Transizione MultiBatchJournalV3 non valida: {cur_state!r} -> {new_state!r}"
            )
        manifest["state"] = new_state
        manifest["updated_utc"] = time.time()
        if extra:
            manifest.setdefault("metadata", {}).update(extra)
        BatchJournalV2._write_json_fsync(journal_file, manifest)
        return manifest

    @staticmethod
    def _resolve_confined_batch_dir(active_dir: Path, manifest: Dict[str, Any], bid: str) -> Path:
        """Confina batch_dir entro active_batches rifiutando escape o reparse point."""
        base_res = active_dir.resolve()
        raw_b = manifest.get("batch_dir")
        cand = Path(str(raw_b)) if raw_b else (base_res / bid)
        if is_reparse_entry(cand):
            raise TwoPhaseCommitError(f"Reparse point vietato su batch_dir nel journal: {cand}")
        cand_res = cand.resolve()
        try:
            cand_res.relative_to(base_res)
        except ValueError as exc:
            raise TwoPhaseCommitError(f"batch_dir fuori da active_batches: {cand}") from exc
        if cand_res == base_res:
            raise TwoPhaseCommitError(f"batch_dir non puo coincidere con active_batches: {cand}")
        return cand_res

    @classmethod
    def cleanup_batch(cls, journal_file: Path, batch_dir: Optional[Path] = None) -> None:
        """Elimina journal_file e preimages batch_dir con retry Win32."""
        try:
            _unlink_with_retry(journal_file)
        except OSError:
            pass
        if batch_dir is not None:
            if is_reparse_entry(batch_dir):
                raise TwoPhaseCommitError(f"Reparse point vietato su batch_dir {batch_dir}")
            for attempt in range(_consts.RETRY_ATTEMPTS_IO):
                if not _win_long_path(batch_dir).exists():
                    break
                safe_rmtree(_win_long_path(batch_dir))
                if _win_long_path(batch_dir).exists() and attempt + 1 < _consts.RETRY_ATTEMPTS_IO:
                    time.sleep(_consts.RETRY_DELAY_SEC_IO)
        active_dir = journal_file.parent
        try:
            if active_dir.is_dir() and not any(active_dir.iterdir()):
                active_dir.rmdir()
        except OSError:
            pass

    @classmethod
    def recover_all_batches(
        cls,
        root: Path,
        *,
        roll_forward_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera batch interrotti: rollback su PREPARED, roll-forward su COMMITTED_FS."""
        active_dir = cls.get_active_batches_dir(root)
        if not active_dir.is_dir():
            return []
        outcomes: List[Dict[str, Any]] = []
        for jf in sorted(active_dir.glob("*.json")):
            if is_reparse_entry(jf):
                continue
            try:
                manifest = json.loads(_win_long_path(jf).read_text(encoding="utf-8-sig"))
                bid = str(manifest.get("batch_id") or jf.stem)
                b_dir = cls._resolve_confined_batch_dir(active_dir, manifest, bid)
                st = str(manifest.get("state") or "PREPARED")
                if st == "PREPARED":
                    restored = BatchJournalV2.rollback_from_manifest(manifest, b_dir)
                    cls.cleanup_batch(jf, b_dir)
                    outcomes.append({"batch_id": bid, "state": st, "action": "ROLLED_BACK_PREPARED", "restored_count": len(restored)})
                elif st == "COMMITTED_FS":
                    if roll_forward_cb is not None:
                        roll_forward_cb(manifest)
                    cls.transition_state(jf, "FINALIZED")
                    cls.cleanup_batch(jf, b_dir)
                    outcomes.append({"batch_id": bid, "state": "FINALIZED", "action": "ROLLED_FORWARD_COMMITTED_FS"})
                elif st == "FINALIZED":
                    cls.cleanup_batch(jf, b_dir)
                    outcomes.append({"batch_id": bid, "state": st, "action": "CLEANED_FINALIZED"})
                else:
                    outcomes.append({"batch_id": bid, "state": st, "action": "UNKNOWN_STATE_ERROR"})
            except Exception as exc:
                outcomes.append({"journal_file": str(jf), "action": "ERROR", "error": str(exc)})
        return outcomes

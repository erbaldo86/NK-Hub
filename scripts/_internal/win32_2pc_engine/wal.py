#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gestore Write-Ahead Log (WAL) 2PC per tracciamento e replay post-crash."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from ..nk_common.transcript_io import wal_bucket_hash
from .constants import compute_sha256
from .io_and_paths import (
    _atomic_write_bytes,
    _replace_with_retry,
    _unlink_with_retry,
    _win_long_path,
    get_repo_batch_mutex_name,
)
from .journal import BatchJournalV2
from .mutex import Win32NamedMutex


class WriteAheadLogManager:
    """Gestisce i file Write-Ahead Log per l'isolamento e il ripristino 2PC."""

    def __init__(self, wal_dir: Optional[Union[str, Path]] = None) -> None:
        self.custom_wal_dir = Path(wal_dir) if wal_dir else None

    def _get_wal_dir(self, target_file: Path) -> Path:
        if self.custom_wal_dir is not None:
            wal_dir = self.custom_wal_dir
        elif os.environ.get("NK_WAL_IN_TEMP", "1") != "0":
            ws_hash = wal_bucket_hash(target_file.parent)
            wal_dir = Path(tempfile.gettempdir()) / "nk_2pc_wal" / ws_hash
        else:
            wal_dir = target_file.parent / ".wal"
        wal_dir.mkdir(parents=True, exist_ok=True)
        return wal_dir

    def get_wal_path(
        self, target_path: Union[str, Path], tx_id: str = "default"
    ) -> Path:
        target = Path(target_path).resolve()
        wal_dir = self._get_wal_dir(target)
        return wal_dir / f"{target.name}.{tx_id}.wal"

    _get_wal_path = get_wal_path

    def write_wal(
        self,
        tx_id: str,
        target_path: Union[str, Path],
        staging_path: Union[str, Path],
        payload_sha256: str,
        payload_crc32: int,
        state: str = "PREPARED",
    ) -> Path:
        """Scrive su disco un record WAL atomico con fsync."""
        wal_path = self.get_wal_path(target_path, tx_id)
        record = {
            "tx_id": tx_id,
            "target_path": str(Path(target_path).resolve()),
            "staging_path": str(Path(staging_path).resolve()),
            "payload_sha256": payload_sha256,
            "payload_crc32": payload_crc32,
            "state": state,
            "timestamp_utc": time.time(),
        }
        temp_wal = wal_path.with_suffix(".tmp")
        with open(_win_long_path(temp_wal), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        _replace_with_retry(temp_wal, wal_path)
        return wal_path

    def update_wal_state(
        self,
        target_path: Union[str, Path],
        tx_id: str,
        state: str,
    ) -> None:
        """Aggiorna lo stato di un record WAL esistente."""
        wal_path = self.get_wal_path(target_path, tx_id)
        if not _win_long_path(wal_path).exists():
            return

        with open(_win_long_path(wal_path), "r", encoding="utf-8-sig") as f:
            record = json.load(f)

        record["state"] = state
        record["updated_at"] = time.time()

        temp_wal = wal_path.with_suffix(".tmp")
        with open(_win_long_path(temp_wal), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        _replace_with_retry(temp_wal, wal_path)

    def purge_wal(self, target_path: Union[str, Path], tx_id: str) -> None:
        """Elimina il file WAL completato e pulisce la cartella se vuota."""
        wal_path = self.get_wal_path(target_path, tx_id)
        wal_dir = wal_path.parent
        try:
            _unlink_with_retry(wal_path)
            if wal_dir.exists() and not any(wal_dir.iterdir()):
                wal_dir.rmdir()
        except OSError:
            pass

    @staticmethod
    def _quarantine_corrupt_wal(wal_file: Path, wal_dir: Path) -> Path:
        """Sposta un file .wal corrotto in .wal/quarantine/ per non bloccare i recovery futuri."""
        quarantine_dir = wal_dir / "quarantine"
        _win_long_path(quarantine_dir).mkdir(parents=True, exist_ok=True)
        q_dest = quarantine_dir / wal_file.name
        if _win_long_path(q_dest).exists():
            q_dest = quarantine_dir / f"{wal_file.stem}_{int(time.time() * 1000)}.wal"
        _replace_with_retry(wal_file, q_dest)
        return q_dest

    def recover(
        self,
        root_dir: Union[str, Path],
        stale_age_sec: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """Ripristina BatchJournalV2 e file WAL in root/.wal e %TEMP%\\nk_2pc_wal sotto mutex di repo."""
        root = Path(root_dir).resolve()
        real_root = Path(os.path.realpath(str(root)))
        recovered: List[Dict[str, Any]] = []

        with Win32NamedMutex(
            get_repo_batch_mutex_name(root),
            timeout_ms=10000,
            is_path=False,
        ):
            now = time.time()
            journal_rec, rolled_back_norms = BatchJournalV2.recover_crashed_batches(
                root
            )
            recovered.extend(journal_rec)

            wal_dirs: List[Path] = []
            root_wal = root / ".wal"
            if root_wal.exists() and root_wal.is_dir():
                wal_dirs.append(root_wal)

            if (
                self.custom_wal_dir is not None
                and self.custom_wal_dir.exists()
                and self.custom_wal_dir.is_dir()
                and self.custom_wal_dir not in wal_dirs
            ):
                wal_dirs.append(self.custom_wal_dir)

            temp_wal_root = Path(tempfile.gettempdir()) / "nk_2pc_wal"
            if temp_wal_root.exists() and temp_wal_root.is_dir():
                if temp_wal_root not in wal_dirs:
                    wal_dirs.append(temp_wal_root)
                for sub_w in temp_wal_root.iterdir():
                    if (
                        sub_w.is_dir()
                        and sub_w.name.lower() != "quarantine"
                        and sub_w not in wal_dirs
                    ):
                        wal_dirs.append(sub_w)

            seen_wals: Set[Path] = set()
            for w_dir in wal_dirs:
                if not w_dir.is_dir() or w_dir.name.lower() == "quarantine":
                    continue
                is_temp_scan = (
                    w_dir == temp_wal_root or temp_wal_root in w_dir.parents
                ) and self.custom_wal_dir != w_dir

                for wal_file in list(w_dir.glob("*.wal")):
                    if wal_file in seen_wals:
                        continue
                    seen_wals.add(wal_file)
                    try:
                        with open(
                            _win_long_path(wal_file), "r", encoding="utf-8-sig"
                        ) as f:
                            data = json.load(f)
                        if not isinstance(data, dict):
                            raise ValueError("Il record WAL non e un oggetto JSON.")
                        raw_target_str = str(data.get("target_path", "")).strip()
                        state = str(data.get("state", "")).strip()
                        if not raw_target_str or state not in (
                            "COMMITTED",
                            "PREPARED",
                            "ABORTED",
                        ):
                            raise ValueError(
                                f"Campi WAL obbligatori mancanti o stato invalido ({state!r})."
                            )
                        ts_utc = float(data.get("timestamp_utc", 0.0))
                    except Exception as parse_exc:
                        try:
                            q_path = self._quarantine_corrupt_wal(wal_file, w_dir)
                            recovered.append({
                                "wal_file": str(wal_file),
                                "quarantined_to": str(q_path),
                                "error": str(parse_exc),
                                "action": "QUARANTINED_CORRUPT",
                            })
                        except Exception as q_exc:
                            recovered.append({
                                "wal_file": str(wal_file),
                                "error": f"{parse_exc}; quarantine failed: {q_exc}",
                                "action": "ERROR",
                            })
                        continue

                    try:
                        tx_id = str(data.get("tx_id", ""))
                        target = Path(raw_target_str)
                        target_real = Path(os.path.realpath(str(target)))
                        if is_temp_scan:
                            if (
                                target_real != real_root
                                and real_root not in target_real.parents
                            ):
                                continue

                        staging_raw = str(data.get("staging_path", "")).strip()
                        staging = Path(staging_raw) if staging_raw else Path()
                        expected_sha = str(data.get("payload_sha256", ""))
                        age = (now - ts_utc) if ts_utc > 0.0 else (stale_age_sec + 1.0)
                        target_norm = str(target_real).lower().replace("/", "\\")

                        action_taken = "NONE"
                        with Win32NamedMutex(target, timeout_ms=2000):
                            if target_norm in rolled_back_norms:
                                if (
                                    staging_raw
                                    and staging != target
                                    and _win_long_path(staging).exists()
                                ):
                                    _unlink_with_retry(staging)
                                _unlink_with_retry(wal_file)
                                action_taken = "PURGED_AFTER_BATCH_ROLLBACK"
                            elif state == "COMMITTED":
                                if (
                                    staging_raw
                                    and staging != target
                                    and _win_long_path(staging).exists()
                                ):
                                    stg_bytes = _win_long_path(staging).read_bytes()
                                    if compute_sha256(stg_bytes) == expected_sha:
                                        _atomic_write_bytes(target, stg_bytes)
                                        action_taken = "REPLAYED_COMMIT"
                                    _unlink_with_retry(staging)
                                _unlink_with_retry(wal_file)
                            elif state == "PREPARED":
                                if age >= stale_age_sec:
                                    if (
                                        staging_raw
                                        and staging != target
                                        and _win_long_path(staging).exists()
                                    ):
                                        _unlink_with_retry(staging)
                                    _unlink_with_retry(wal_file)
                                    action_taken = "ABORTED_STALE"
                                else:
                                    action_taken = "SKIPPED_ACTIVE"
                            elif state == "ABORTED":
                                if (
                                    staging_raw
                                    and staging != target
                                    and _win_long_path(staging).exists()
                                ):
                                    _unlink_with_retry(staging)
                                _unlink_with_retry(wal_file)
                                action_taken = "PURGED_ABORTED"

                        recovered.append({
                            "wal_file": str(wal_file),
                            "tx_id": tx_id,
                            "state": state,
                            "action": action_taken,
                        })
                    except Exception as exc:
                        recovered.append({
                            "wal_file": str(wal_file),
                            "error": str(exc),
                            "action": "ERROR",
                        })

        return recovered

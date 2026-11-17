#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gestione mutex canonico 2PC e bonifica/quarantena file WAL."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..nk_common import win32_mutex as _nk_mutex
from ..nk_common.transcript_io import wal_bucket_hash
from . import constants as _consts


def has_actionable_wal_entries(self_obj: Any) -> bool:
    """Verifica rapidamente se .wal contiene voci diverse dalla sottocartella quarantine."""
    if self_obj._wal_dir_exists is False:
        return False
    wal_dir = self_obj.workspace_root / ".wal"
    try:
        with os.scandir(wal_dir) as it:
            for entry in it:
                if entry.name == "quarantine" and entry.is_dir(follow_symlinks=False):
                    continue
                return True
    except OSError:
        self_obj._wal_dir_exists = False
        return False
    return False


def try_acquire_2pc_mutex_nonblocking(root: Optional[Path] = None) -> Optional[int]:
    """Tenta l'acquisizione non bloccante del mutex canonico Global\\NK_RepoBatchLock_<sha256[:16]>."""
    k32 = _consts._get_win32_k32()
    if sys.platform != "win32" or k32 is None:
        return -1

    hub_root = _consts._get_facade_attr("HUB_ROOT", _consts.HUB_ROOT)
    target_root = Path(root).resolve() if root is not None else hub_root
    global_name = _consts.get_canonical_repo_batch_mutex_name(target_root)
    return _nk_mutex.try_acquire_mutex_nonblocking(global_name, k32=k32)


def release_2pc_mutex(handle: Optional[int]) -> None:
    """Rilascia e chiude l'handle del mutex Win32 2PC se acquisito."""
    if handle is None or handle <= 0 or sys.platform != "win32":
        return
    k32 = _consts._get_win32_k32()
    if k32 is None:
        return
    _nk_mutex.release_win32_mutex(handle, k32=k32)


def inspect_wal_state(wal_file: Path) -> str:
    """Classifica monotonicamente un file WAL come COMMITTED, VALID_PENDING o CORRUPTED."""
    try:
        raw_bytes = wal_file.read_bytes()
    except Exception:
        return "CORRUPTED"
    try:
        raw = raw_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        return "CORRUPTED"
    if not raw:
        return "CORRUPTED"

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            if str(parsed.get("state", "")).strip().upper() == "COMMITTED":
                return "COMMITTED"
            return "VALID_PENDING"
        return "CORRUPTED"
    except Exception:
        pass

    valid_dicts = 0
    last_state = ""
    for line in raw.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        try:
            rec = json.loads(line_s)
        except Exception:
            return "CORRUPTED"
        if not isinstance(rec, dict):
            return "CORRUPTED"
        valid_dicts += 1
        last_state = str(rec.get("state", "")).strip().upper()
    if valid_dicts == 0:
        return "CORRUPTED"
    return "COMMITTED" if last_state == "COMMITTED" else "VALID_PENDING"


def quarantine_corrupted_wal(self_obj: Any, wal_file: Path) -> Optional[Path]:
    """Sposta un file .wal corrotto in <workspace_root>/.wal/quarantine/ senza cancellarlo."""
    try:
        quarantine_dir = self_obj.workspace_root / ".wal" / "quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        dest = quarantine_dir / wal_file.name
        if dest.exists():
            dest = (
                quarantine_dir
                / f"{wal_file.stem}.{int(time.time() * 1000)}{wal_file.suffix}"
            )
        try:
            os.replace(str(wal_file), str(dest))
        except OSError:
            import shutil

            shutil.move(str(wal_file), str(dest))
        return dest
    except Exception:
        return None


def _wal_targets_workspace(wal_path: Path, ws_real: Path) -> bool:
    """Verifica se un file WAL in temp appartiene a un target interno al workspace."""
    try:
        raw = wal_path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return False
        raw_tgt = str(data.get("target_path", "")).strip()
        if not raw_tgt:
            return False
        tgt_real = Path(os.path.realpath(raw_tgt))
        return tgt_real == ws_real or ws_real in tgt_real.parents
    except Exception:
        return False


def purge_stale_wal_files(
    self_obj: Any, ttl_seconds: float = 60.0
) -> Dict[str, Any]:
    """Bonifica i file WAL scaduti e sposta i .wal corrotti in .wal/quarantine/ sotto mutex 2PC."""
    ws_resolved = self_obj.workspace_root.resolve()
    ws_real = Path(os.path.realpath(str(ws_resolved)))
    ws_hash = wal_bucket_hash(ws_resolved)
    scripts_hash = wal_bucket_hash(ws_resolved / "scripts")
    temp_wal_base = Path(tempfile.gettempdir()) / "nk_2pc_wal"
    quarantine_dir = ws_resolved / ".wal" / "quarantine"

    candidate_dirs = (
        self_obj.workspace_root,
        self_obj.workspace_root / ".staging",
        self_obj.workspace_root / ".wal",
        self_obj.workspace_root / "scripts" / ".wal",
        self_obj.workspace_root / "nk_tracking",
        self_obj.workspace_root / "nk_tracking" / ".wal",
        temp_wal_base / ws_hash,
        temp_wal_base / scripts_hash,
    )

    discovered_wals: List[tuple[Path, float]] = []
    seen_wals: set[Path] = set()
    for cdir in candidate_dirs:
        try:
            with os.scandir(cdir) as it:
                for entry in it:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    fname = entry.name
                    if fname.endswith((".wal", ".wal_2pc.jsonl")) or (
                        ".wal_tmp" in fname
                    ):
                        wpath = Path(entry.path)
                        if wpath.parent.resolve() == quarantine_dir:
                            continue
                        seen_wals.add(wpath)
                        discovered_wals.append((wpath, entry.stat().st_mtime))
        except OSError:
            continue

    if temp_wal_base.is_dir():
        try:
            with os.scandir(temp_wal_base) as sub_it:
                for sub_entry in sub_it:
                    if not sub_entry.is_dir(follow_symlinks=False):
                        continue
                    if sub_entry.name.lower() == "quarantine":
                        continue
                    try:
                        with os.scandir(sub_entry.path) as w_it:
                            for w_entry in w_it:
                                if not w_entry.is_file(follow_symlinks=False):
                                    continue
                                if w_entry.name.endswith((".wal", ".wal_2pc.jsonl")):
                                    wpath = Path(w_entry.path)
                                    if wpath not in seen_wals and _wal_targets_workspace(
                                        wpath, ws_real
                                    ):
                                        seen_wals.add(wpath)
                                        discovered_wals.append(
                                            (wpath, w_entry.stat().st_mtime)
                                        )
                    except OSError:
                        continue
        except OSError:
            pass

    if not discovered_wals:
        return {
            "passed": True,
            "status": "PASS",
            "stale_wals_purged": 0,
            "corrupted_wals_quarantined": 0,
        }

    mutex_handle = self_obj._try_acquire_2pc_mutex_nonblocking(self_obj.workspace_root)
    if mutex_handle is None or not _nk_mutex.is_win32_handle_valid(mutex_handle):
        is_busy = mutex_handle is None
        return {
            "passed": True,
            "status": "PASS",
            "stale_wals_purged": 0,
            "corrupted_wals_quarantined": 0,
            "mutex_busy": is_busy,
            "mutex_error": not is_busy,
            "details": (
                "2PC mutex active; WAL purge deferred."
                if is_busy
                else "2PC mutex unavailable on Win32; WAL purge skipped fail-closed."
            ),
        }

    purged = 0
    quarantined = 0
    quarantined_paths: List[str] = []
    now = time.time()
    try:
        for wal_file, mtime in discovered_wals:
            if not wal_file.exists():
                continue
            age = now - mtime
            if ".wal_tmp" in wal_file.name:
                if age > ttl_seconds:
                    wal_file.unlink(missing_ok=True)
                    purged += 1
                continue
            w_state = self_obj._inspect_wal_state(wal_file)
            if w_state == "CORRUPTED":
                q_dest = self_obj._quarantine_corrupted_wal(wal_file)
                if q_dest is not None:
                    quarantined += 1
                    quarantined_paths.append(str(q_dest))
            elif w_state == "COMMITTED":
                continue
            elif age > ttl_seconds:
                wal_file.unlink(missing_ok=True)
                purged += 1
    finally:
        self_obj._release_2pc_mutex(mutex_handle)

    if purged > 0 or quarantined > 0:
        self_obj._cached_root_mtime = None
    res: Dict[str, Any] = {
        "passed": True,
        "status": "PASS",
        "stale_wals_purged": purged,
        "corrupted_wals_quarantined": quarantined,
    }
    if quarantined_paths:
        res["quarantined_files"] = quarantined_paths
    return res

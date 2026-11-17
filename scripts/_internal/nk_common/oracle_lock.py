# -*- coding: utf-8 -*-
"""Helper stdlib per snapshot e verifica SHA-256 LF/CRLF di oracle_lock.json."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from _internal.nk_common.io import atomic_write_text
from _internal.nk_common.win32_mutex import (
    create_or_open_named_mutex,
    release_win32_mutex,
)


def compute_lf_sha256(file_path: Union[str, Path]) -> str:
    """Calcola lo SHA-256 del file normalizzando i terminatori CRLF in LF."""
    raw = Path(file_path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def sha256_eol_matches(file_path: Union[str, Path], expected_sha: str) -> bool:
    """Verifica la corrispondenza SHA-256 tollerando differenze CRLF e LF."""
    if not expected_sha:
        return False
    p_obj = Path(file_path)
    if not p_obj.is_file():
        return False
    try:
        lf_bytes = p_obj.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(lf_bytes).hexdigest() == expected_sha:
            return True
        if hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest() == expected_sha:
            return True
    except OSError:
        return False
    return False


def compute_combined_sha256(files_map: Dict[str, str]) -> str:
    """Calcola l'impronta combinata deterministica della mappa file."""
    canonical = json.dumps(files_map, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _acquire_lock_mutex(target_root: Path) -> Optional[int]:
    """Acquisisce un Named Mutex Win32 per le operazioni su oracle_lock.json."""
    sig = hashlib.sha256(str(target_root.resolve()).encode("utf-8")).hexdigest()[:12]
    handle, acquired, _ = create_or_open_named_mutex(
        f"Local\\NK_OracleLock_{sig}", wait_ms=5000
    )
    return handle if acquired else None


def verify_oracle_lock_manifest(
    lock_file: Union[str, Path],
    target_root: Union[str, Path],
    current_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Verifica integrita di oracle_lock.json tollerando fine riga CRLF/LF."""
    lock_path = Path(lock_file)
    resolved_target = Path(target_root).resolve()
    if not lock_path.is_file():
        return {
            "status": "FAIL: oracle_lock missing",
            "passed": False,
            "mismatches": ["Lock file not found"],
        }

    try:
        saved = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {
            "status": "FAIL: oracle_lock corrupt",
            "passed": False,
            "mismatches": [f"Corrupt lock file: {exc}"],
        }

    if not isinstance(saved, dict) or not isinstance(saved.get("files"), dict):
        return {
            "status": "FAIL: oracle_lock invalid",
            "passed": False,
            "mismatches": ["Invalid lock schema"],
        }

    saved_files: Dict[str, str] = saved["files"]
    live_map: Dict[str, str] = (
        dict(current_map)
        if current_map is not None
        else {
            rel: compute_lf_sha256(resolved_target / rel)
            for rel in saved_files
            if (resolved_target / rel).is_file()
        }
    )

    mismatches: List[str] = []
    effective_map = dict(live_map)
    for rel, old_sha in saved_files.items():
        cur_sha = live_map.get(rel)
        if cur_sha is None:
            mismatches.append(f"deleted:{rel}")
        elif cur_sha != old_sha:
            cand_path = (
                resolved_target
                if resolved_target.is_file()
                else (resolved_target / rel).resolve()
            )
            if sha256_eol_matches(cand_path, old_sha):
                effective_map[rel] = old_sha
            else:
                mismatches.append(f"modified:{rel}")

    for rel in live_map:
        if rel not in saved_files:
            mismatches.append(f"added:{rel}")

    combined_eff = compute_combined_sha256(effective_map)
    if mismatches or combined_eff != saved.get("combined_sha256"):
        return {
            "status": "FAIL: oracle_lock mismatch",
            "passed": False,
            "mismatches": mismatches,
        }

    return {
        "status": "VERIFIED",
        "passed": True,
        "files_count": len(live_map),
        "mismatches": [],
    }


def write_oracle_lock_manifest(
    lock_file: Union[str, Path],
    target_root: Union[str, Path],
    files_map: Dict[str, str],
) -> Dict[str, Any]:
    """Scrive atomicamente oracle_lock.json sotto Named Mutex Win32."""
    lock_path = Path(lock_file)
    resolved_target = Path(target_root).resolve()
    combined = compute_combined_sha256(files_map)
    payload = {
        "target": resolved_target.as_posix(),
        "files": files_map,
        "combined_sha256": combined,
    }
    raw_json = json.dumps(payload, indent=2, ensure_ascii=False)
    mutex_handle = _acquire_lock_mutex(resolved_target)
    try:
        ok, err = atomic_write_text(lock_path, raw_json)
    finally:
        release_win32_mutex(mutex_handle)

    if not ok:
        return {"status": "ERROR", "passed": False, "error": err or "write_failed"}
    return {
        "status": "LOCKED",
        "passed": True,
        "files_count": len(files_map),
        "combined_sha256": combined,
    }

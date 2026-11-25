# -*- coding: utf-8 -*-
"""Helper stdlib per snapshot, lock fail-closed e verifica SHA-256 di oracle_lock.json."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.constants import NK_LOCK_FILENAMES
from _internal.nk_common.io import atomic_write_text
from _internal.nk_common.staging_manifest import is_valid_sha256_hex
from _internal.nk_common.win32_mutex import (
    create_or_open_named_mutex,
    get_named_mutex_name,
    release_win32_mutex,
)

_SCAN_IGNORED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".git", ".staging", ".wal"})
_SCAN_IGNORED_SUFFIXES = frozenset({".zip", ".tmp", ".bak"})
_SCAN_IGNORED_NAMES = frozenset(
    {
        *NK_LOCK_FILENAMES,
        ".bootstrap_fast_cache.json",
        ".fast_stat_cache.json",
        ".session_state.json",
        "session_anchor.jsonl",
    }
)


def compute_lf_sha256(file_path: Union[str, Path]) -> str:
    """Calcola lo SHA-256 del file normalizzando i terminatori CRLF in LF."""
    raw = Path(file_path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def sha256_eol_matches(file_path: Union[str, Path], expected_sha: str) -> bool:
    """Verifica la corrispondenza SHA-256 tollerando differenze CRLF e LF."""
    if not is_valid_sha256_hex(expected_sha):
        return False
    exp_low = expected_sha.lower()
    p_obj = Path(file_path)
    if not p_obj.is_file():
        return False
    try:
        lf_bytes = p_obj.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(lf_bytes).hexdigest() == exp_low:
            return True
        if hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest() == exp_low:
            return True
    except OSError:
        return False
    return False


def scan_directory_lf_hashes(target_dir: Path) -> Dict[str, str]:
    """Scansiona deterministicamente una directory calcolando gli SHA-256 LF-normalizzati."""
    resolved_dir = Path(target_dir).resolve()
    if not resolved_dir.is_dir():
        return {}
    hashes: Dict[str, str] = {}
    for item in sorted(resolved_dir.rglob("*")):
        if not item.is_file():
            continue
        if item.name in _SCAN_IGNORED_NAMES or item.suffix.lower() in _SCAN_IGNORED_SUFFIXES:
            continue
        rel_obj = item.relative_to(resolved_dir)
        if any(part in _SCAN_IGNORED_PARTS for part in rel_obj.parts):
            continue
        hashes[rel_obj.as_posix()] = compute_lf_sha256(item)
    return hashes


def compute_combined_sha256(files_map: Dict[str, str]) -> str:
    """Calcola l'impronta combinata deterministica della mappa file."""
    canonical = json.dumps(files_map, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _acquire_lock_mutex_state(
    target_root: Path,
) -> Tuple[Optional[int], bool, Optional[str]]:
    """Acquisisce il Named Mutex Win32 per oracle_lock.json restituendo (handle, acquired, error)."""
    if sys.platform != "win32":
        return None, True, None
    mutex_name = get_named_mutex_name(target_root.resolve(), "Local\\NK_OracleLock", chars=12)
    handle, acquired, err = create_or_open_named_mutex(mutex_name, wait_ms=5000)
    return handle, bool(acquired), err


def _collect_live_hash_map(
    resolved_target: Path,
    saved_files: Dict[str, Any],
    current_map: Optional[Dict[str, str]],
) -> Tuple[Dict[str, str], List[str]]:
    """Costruisce la mappa live corrente rilevando file aggiunti in target_root e sibling ../."""
    if current_map is not None:
        return dict(current_map), []
    if resolved_target.is_file():
        return {resolved_target.name: compute_lf_sha256(resolved_target)}, []

    live_map = scan_directory_lf_hashes(resolved_target)
    escape_errors: List[str] = []
    bound_root = resolved_target.parent.resolve()
    for raw_rel in saved_files:
        rel_str = str(raw_rel).replace("\\", "/")
        if not rel_str.startswith("../"):
            continue
        ext_cand = (resolved_target / rel_str).resolve()
        if ext_cand != bound_root and bound_root not in ext_cand.parents:
            escape_errors.append(f"escaped:{rel_str}")
            continue
        if ext_cand.is_file():
            live_map[str(raw_rel)] = compute_lf_sha256(ext_cand)
    return live_map, escape_errors


def _validate_oracle_entries_and_combined(
    resolved_target: Path,
    saved: Dict[str, Any],
    saved_files: Dict[str, Any],
    live_map: Dict[str, str],
    mismatches: List[str],
) -> bool:
    """Confronta digest per ogni voce salvata, aggiunte inattese e combined_sha256."""
    effective_map = dict(live_map)
    saved_combined = saved.get("combined_sha256")
    if not is_valid_sha256_hex(saved_combined):
        mismatches.append("invalid_combined_sha256")

    for rel, old_sha in saved_files.items():
        if not is_valid_sha256_hex(old_sha):
            mismatches.append(f"invalid_digest:{rel}")
            continue
        cur_sha = live_map.get(rel)
        if cur_sha is None:
            mismatches.append(f"deleted:{rel}")
        elif cur_sha.lower() != str(old_sha).lower():
            cand_path = (
                resolved_target
                if resolved_target.is_file()
                else (resolved_target / rel).resolve()
            )
            if sha256_eol_matches(cand_path, str(old_sha)):
                effective_map[rel] = str(old_sha)
            else:
                mismatches.append(f"modified:{rel}")

    for rel in live_map:
        if rel not in saved_files:
            mismatches.append(f"added:{rel}")

    combined_eff = compute_combined_sha256(effective_map)
    return isinstance(saved_combined, str) and combined_eff != saved_combined.lower()


def verify_oracle_lock_manifest(
    lock_file: Union[str, Path],
    target_root: Union[str, Path],
    current_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Verifica integrita fail-closed di oracle_lock.json tollerando fine riga CRLF/LF."""
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

    saved_files: Dict[str, Any] = saved["files"]
    if not saved_files:
        return {
            "status": "FAIL: oracle_lock empty",
            "passed": False,
            "mismatches": ["Empty oracle_lock files map"],
        }

    live_map, mismatches = _collect_live_hash_map(resolved_target, saved_files, current_map)
    combined_mismatch = _validate_oracle_entries_and_combined(
        resolved_target, saved, saved_files, live_map, mismatches
    )
    if mismatches or combined_mismatch:
        return {
            "status": "FAIL: oracle_lock mismatch",
            "passed": False,
            "mismatches": mismatches or ["combined_sha256_mismatch"],
        }

    return {
        "status": "VERIFIED",
        "passed": True,
        "files_count": len(live_map),
        "mismatches": [],
    }


def _write_manifest_under_mutex(
    lock_path: Path, resolved_target: Path, raw_json: str
) -> Tuple[bool, str]:
    """Acquisisce mutex fail-closed e scrive atomicamente oracle_lock.json."""
    mutex_handle, acquired, lock_err = _acquire_lock_mutex_state(resolved_target)
    if not acquired:
        return False, f"mutex_acquire_failed:{lock_err or 'timeout'}"
    try:
        ok, err = atomic_write_text(lock_path, raw_json)
        return ok, str(err or "write_failed")
    finally:
        release_win32_mutex(mutex_handle)


def write_oracle_lock_manifest(
    lock_file: Union[str, Path],
    target_root: Union[str, Path],
    files_map: Dict[str, str],
) -> Dict[str, Any]:
    """Scrive atomicamente oracle_lock.json sotto Named Mutex Win32 fail-closed."""
    if not files_map:
        return {"status": "ERROR", "passed": False, "error": "empty_files_map"}

    lock_path = Path(lock_file)
    resolved_target = Path(target_root).resolve()
    combined = compute_combined_sha256(files_map)
    payload = {
        "target": resolved_target.as_posix(),
        "files": files_map,
        "combined_sha256": combined,
    }
    ok, err = _write_manifest_under_mutex(
        lock_path, resolved_target, json.dumps(payload, indent=2, ensure_ascii=False)
    )
    if not ok:
        return {"status": "ERROR", "passed": False, "error": err}
    return {
        "status": "LOCKED",
        "passed": True,
        "files_count": len(files_map),
        "combined_sha256": combined,
    }

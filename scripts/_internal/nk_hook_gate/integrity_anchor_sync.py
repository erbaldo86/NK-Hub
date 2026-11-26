# -*- coding: utf-8 -*-
"""Sincronizzazione crittografica integrity anchor (5 punti) e cache HMAC SessionStart pure-stdlib."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from _internal.nk_common.commit_train_store import (
    GENESIS_HASH,
    ensure_commit_train_hmac_key,
    read_commit_train_head,
    sign_commit_train_payload,
    verify_commit_train_chain,
    verify_commit_train_signature,
)
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import repo_path_hash12
from _internal.nk_hook_gate.json_io import (
    _get_hooks_temp_dir,
    _is_path_reparse_point,
    _sha256_file,
    _write_json_atomic_safe,
)

MAX_SESSION_CACHE_TTL_SEC: float = 300.0
_WATCHED_TREE_DIRS: Tuple[str, ...] = ("scripts", "tests", ".agents", "nk_tracking")


def resolve_hooks_config_sha256(root: Path) -> str:
    """Calcola digest deterministico di hooks.json del repository o hash vuoto."""
    entries: Dict[str, str] = {}
    for rel in (".agents/hooks.json", ".agents/plugins/nk-gate/hooks.json"):
        cand = root / rel
        if cand.is_file() and not _is_path_reparse_point(cand):
            entries[rel] = _sha256_file(cand)
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _scan_dir_entries(cur: str, stack: List[str]) -> Tuple[int, int, int]:
    """Scansiona una singola directory escludendo pycache e reparse point."""
    count, max_mtime, total_size = 0, -1, 0
    try:
        it_ctx = os.scandir(cur)
    except OSError:
        return 0, -1, 0
    with it_ctx as it:
        for ent in it:
            if ent.name == "__pycache__" or ent.name.endswith((".pyc", ".pyo")):
                continue
            try:
                st = ent.stat(follow_symlinks=False)
            except OSError:
                continue
            if ent.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & 0x400):
                continue
            max_mtime = max(max_mtime, int(st.st_mtime_ns))
            if ent.is_dir(follow_symlinks=False):
                stack.append(ent.path)
            elif ent.is_file(follow_symlinks=False):
                count += 1
                total_size += int(st.st_size)
    return count, max_mtime, total_size


def _scan_dir_fingerprint(base: Path) -> List[int]:
    """Calcola [file_count, max_mtime_ns, total_size] ricorsivo pure-stdlib escludendo reparse e pycache."""
    if not base.exists() or _is_path_reparse_point(base) or is_reparse_entry(base):
        return [-1, -1, -1]
    try:
        max_mtime = int(os.lstat(str(base)).st_mtime_ns)
    except OSError:
        return [-1, -1, -1]
    stack, count, total_size = [str(base)], 0, 0
    while stack:
        d_cnt, d_mt, d_sz = _scan_dir_entries(stack.pop(), stack)
        count += d_cnt
        total_size += d_sz
        if d_mt > max_mtime:
            max_mtime = d_mt
    return [count, max_mtime, total_size]


def collect_watched_tree_mtimes(root: Path) -> Dict[str, List[int]]:
    """Cattura fingerprint [file_count, max_mtime_ns, total_size] delle directory chiave."""
    return {name: _scan_dir_fingerprint(root / name) for name in _WATCHED_TREE_DIRS}


def _oracle_lock_sha256(root: Path) -> str:
    cand = root / "nk_tracking" / "oracle_lock.json"
    if not cand.is_file():
        cand = root / "oracle_lock.json"
    return _sha256_file(cand) if cand.is_file() else hashlib.sha256(b"").hexdigest()


def attach_commit_train_anchor_fields(root: Path, snap: Dict[str, Any]) -> Dict[str, Any]:
    """Arricchisce lo snapshot di integrita con head Commit Train e hash hooks.json."""
    try:
        head = read_commit_train_head(root, verify_hmac=False)
        seq_val = int(head.get("seq", 0))
        head_hash = str(head.get("last_record_hash") or GENESIS_HASH)
    except Exception:
        seq_val, head_hash = 0, GENESIS_HASH
    return {**snap, "commit_train_seq": seq_val, "commit_train_head_hash": head_hash, "hooks_json_sha256": resolve_hooks_config_sha256(root)}


def _read_live_cache_anchor(root: Path) -> Tuple[str, str, Dict[str, List[int]], int, str]:
    live_oracle = _oracle_lock_sha256(root)
    live_hooks = resolve_hooks_config_sha256(root)
    live_mtimes = collect_watched_tree_mtimes(root)
    try:
        live_head = read_commit_train_head(root, verify_hmac=False)
        return live_oracle, live_hooks, live_mtimes, int(live_head.get("seq", 0)), str(live_head.get("last_record_hash") or GENESIS_HASH)
    except Exception:
        return live_oracle, live_hooks, live_mtimes, -1, ""


def _try_load_cached_snapshot(
    cache_file: Path, key_bytes: bytes, eff_ttl: float, eff_now: float,
    live_state: Tuple[str, str, Dict[str, List[int]], int, str],
) -> Optional[Dict[str, Any]]:
    if not cache_file.is_file() or _is_path_reparse_point(cache_file) or is_reparse_entry(cache_file):
        return None
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(cached, dict) or not verify_commit_train_signature(cached, key_bytes):
        return None
    age = eff_now - float(cached.get("cached_at", -1.0))
    live_oracle, live_hooks, live_mtimes, live_seq, live_hash = live_state
    matches = (
        0.0 <= age <= eff_ttl
        and cached.get("oracle_lock_sha256") == live_oracle
        and cached.get("hooks_json_sha256") == live_hooks
        and int(cached.get("commit_train_seq", -2)) == live_seq
        and cached.get("commit_train_head_hash") == live_hash
        and cached.get("dir_mtimes") == live_mtimes
    )
    snap = cached.get("snapshot")
    return dict(snap) if (matches and isinstance(snap, dict)) else None


def compute_or_load_session_start_snapshot(
    root: Path, compute_fn: Callable[[], Dict[str, Any]], *, ttl_sec: float = MAX_SESSION_CACHE_TTL_SEC,
    key_path: Optional[Union[str, Path]] = None, now_ts: Optional[float] = None,
) -> Tuple[Dict[str, Any], bool]:
    """Carica cache SessionStart firmata HMAC se fresca e coerente, altrimenti ricalcola."""
    eff_ttl = min(max(1.0, float(ttl_sec)), MAX_SESSION_CACHE_TTL_SEC)
    eff_now = time.time() if now_ts is None else float(now_ts)
    cache_file = _get_hooks_temp_dir() / f"session_start_cache_{repo_path_hash12(root)}.json"
    key_bytes = ensure_commit_train_hmac_key(key_path).read_bytes().strip()
    live_state = _read_live_cache_anchor(root)
    if (hit := _try_load_cached_snapshot(cache_file, key_bytes, eff_ttl, eff_now, live_state)) is not None:
        return hit, True
    fresh = attach_commit_train_anchor_fields(root, compute_fn())
    record: Dict[str, Any] = {
        "cached_at": eff_now, "oracle_lock_sha256": live_state[0], "hooks_json_sha256": live_state[1],
        "commit_train_seq": int(fresh.get("commit_train_seq", 0)),
        "commit_train_head_hash": str(fresh.get("commit_train_head_hash") or GENESIS_HASH),
        "dir_mtimes": live_state[2], "snapshot": fresh,
    }
    record["hmac_sha256"] = sign_commit_train_payload(record, key_bytes)
    _write_json_atomic_safe(cache_file, record)
    return fresh, False


def _hooks_touched_in_range(entries: List[Dict[str, Any]], saved_seq: int, head_seq: int) -> bool:
    for entry in entries:
        if saved_seq < int(entry.get("seq", 0)) <= head_seq:
            for rel_f in list(entry.get("committed_files", ())) + list(entry.get("deleted_files", ())):
                if str(rel_f).replace("\\", "/").lower() in (".agents/hooks.json", ".agents/plugins/nk-gate/hooks.json"):
                    return True
    return False


def _check_chain_and_latest_anchor(
    entries: List[Dict[str, Any]], saved_snap: Dict[str, Any], current_snap: Dict[str, Any],
) -> Optional[str]:
    raw_saved_seq = saved_snap.get("commit_train_seq", 0)
    if isinstance(raw_saved_seq, bool) or not isinstance(raw_saved_seq, int) or raw_saved_seq < 0:
        return f"invalid saved commit_train_seq: {raw_saved_seq!r}"
    saved_seq = raw_saved_seq
    head_seq = int(entries[-1]["seq"])
    if head_seq <= saved_seq:
        return f"commit_train seq did not advance ({head_seq} <= {saved_seq})"
    saved_hash = str(saved_snap.get("commit_train_head_hash") or GENESIS_HASH).lower()
    expected_base = GENESIS_HASH if saved_seq == 0 else str(entries[saved_seq - 1]["record_hash"]).lower()
    if saved_seq > len(entries) or not hmac.compare_digest(saved_hash, expected_base):
        return "saved commit_train_head_hash mismatch"
    latest = entries[-1]
    lat_m = str(latest.get("staging_manifest_sha256") or "").lower()
    lat_a = str(latest.get("chain_anchor_sha256") or "").lower()
    live_a = str(current_snap.get("chain_anchor_sha256") or "").lower()
    if len(lat_m) != 64 or len(lat_a) != 64 or not hmac.compare_digest(lat_a, live_a):
        return "chain_anchor_sha256 does not match latest verified commit"
    return None


def verify_valid_advanced_anchor(
    root: Path, saved_snap: Dict[str, Any], current_snap: Dict[str, Any], *,
    oracle_lock_violations: List[str], history_violations: List[str], key_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Verifica 5 punti crittografici per accettare avanzamenti 2PC di altre lane."""
    if oracle_lock_violations or history_violations:
        return False, "VIOLATION", {"reason": "oracle_lock or history violations non-empty"}
    ok_chain, entries, chain_errs = verify_commit_train_chain(root, key_path=key_path)
    if not ok_chain or not entries:
        return False, "VIOLATION", {"reason": f"commit_train chain invalid or empty: {chain_errs}"}
    if (err := _check_chain_and_latest_anchor(entries, saved_snap, current_snap)) is not None:
        return False, "VIOLATION", {"reason": err}
    saved_seq, head_seq = int(saved_snap.get("commit_train_seq", 0)), int(entries[-1]["seq"])
    saved_hooks = str(saved_snap.get("hooks_json_sha256") or "").lower()
    live_hooks = str(current_snap.get("hooks_json_sha256") or resolve_hooks_config_sha256(root)).lower()
    if len(saved_hooks) != 64 or len(live_hooks) != 64:
        return False, "VIOLATION", {"reason": "missing hooks_json_sha256 anchor"}
    if not hmac.compare_digest(saved_hooks, live_hooks) and not _hooks_touched_in_range(entries, saved_seq, head_seq):
        return False, "VIOLATION", {"reason": "hooks.json changed out-of-band without commit_train entry"}
    return True, "VALID_ADVANCED", {"advanced_from_seq": saved_seq, "advanced_to_seq": head_seq, "commit_train_head_hash": str(entries[-1]["record_hash"])}

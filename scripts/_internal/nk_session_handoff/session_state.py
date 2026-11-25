# -*- coding: utf-8 -*-
"""Stato del workspace, hash SHA-256, commit atomico e baseline per nk_session_handoff."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.io import atomic_write_text
from _internal.nk_session_handoff.constants import (  # noqa: F401
    _BASELINE_LOCK, _BASELINE_MEMO, _EXCLUDED_STATE_DIRS, _EXCLUDED_STATE_FILENAMES,
    _FILE_HASH_LOCK, _FILE_HASH_MEMO, _SAFE_SESSION_CONV_ID_RE,
    _SKIP_STATE_REL_DIRS, _SKIP_STATE_REL_FILES, _dir_latest_activity_ns,
    _entry_mtime_ns, _parse_optional_turn, _parse_ts_ns_value, _prune_handoff_memo_cache,
    _sanitize_ste100_inline, _scan_session_dir_candidate, _select_retained_session_names,
    _state_memo_cache_path, _workspace_root, resolve_session_tracking_dir,
)

try:
    from win32_2pc_engine import TwoPhaseCommitEngine, Win32NamedMutex, get_repo_batch_mutex_name
except ImportError:
    from scripts.win32_2pc_engine import (  # type: ignore[no-redef]
        TwoPhaseCommitEngine, Win32NamedMutex, get_repo_batch_mutex_name,
    )

_FACADES = ("nk_session_handoff", "scripts.nk_session_handoff")
_METRIC_TEST_KEYS = ("unit_tests_total", "total_golden_tests", "tests_total", "tests_passed")
_FLAT_TEST_KEYS = ("total_tests", "golden_tests_count", "unit_tests_total", "tests_total", "passed_tests", "tests_passed")
SESSION_RETENTION_LIMIT: int = 5


def _extract_baseline_pair(data: Dict[str, Any]) -> Tuple[Optional[int], float]:
    """Estrae (tests_count, pass_rate_pct) da un dizionario quality_baseline.json."""
    if not data:
        return None, 100.0
    metrics = data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
    tot_v: Any = next(((rt.get("value") if isinstance(rt, dict) else rt) for k in _METRIC_TEST_KEYS if (rt := metrics.get(k)) is not None), None)
    if tot_v is None:
        tot_v = next((data.get(k) for k in _FLAT_TEST_KEYS if data.get(k) is not None), None)
    tot_i = int(tot_v) if (isinstance(tot_v, (int, float)) and not isinstance(tot_v, bool) and int(tot_v) >= 0) else None
    rp = metrics.get("unit_tests_pass_pct")
    pv = rp.get("value") if isinstance(rp, dict) else (rp if isinstance(rp, (int, float)) and not isinstance(rp, bool) else next((data[k] for k in ("pass_rate_pct", "pass_rate") if data.get(k) is not None), 100.0))
    return tot_i, float(pv) if (isinstance(pv, (int, float)) and not isinstance(pv, bool)) else 100.0


def _read_baseline_data(root_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Carica quality_baseline.json con memoizzazione breve protetta da lock."""
    eff_ws_root = Path(resolve_facade_attr(_FACADES, "_workspace_root", _workspace_root))
    base = (root_dir or eff_ws_root).resolve()
    key, now = str(base), time.time()
    with _BASELINE_LOCK:
        cached = _BASELINE_MEMO.get(key)
        if cached is not None and (now - cached[0]) < 1.0:
            return cached[1]
    rel_p = Path("nk_tracking") / "quality_baseline.json"
    for cand in (base / ".staging" / rel_p, base / rel_p, eff_ws_root / ".staging" / rel_p, eff_ws_root / rel_p):
        try:
            if cand.is_file() and isinstance(data := json.loads(cand.read_text(encoding="utf-8")), dict):
                with _BASELINE_LOCK:
                    _BASELINE_MEMO[key] = (now, data)
                return data
        except Exception:
            pass
    return {}


def _read_baseline_tests_count(root_dir: Optional[Path] = None) -> int:
    """Legge il numero totale di Golden Tests da quality_baseline.json."""
    tot, _ = _extract_baseline_pair(_read_baseline_data(root_dir))
    return tot if tot is not None else 183


def _read_baseline_pass_rate(root_dir: Optional[Path] = None) -> float:
    """Estrae il pass rate da quality_baseline.json."""
    return _extract_baseline_pair(_read_baseline_data(root_dir))[1]


def prune_session_tracking_dirs(
    target_root: Path,
    active_conversation_id: Optional[str] = None,
    max_sessions: int = SESSION_RETENTION_LIMIT,
) -> List[str]:
    """Mantiene al massimo max_sessions directory in nk_tracking/sessions/ preservando quella attiva."""
    if max_sessions < 1:
        return []
    sessions_dir = (Path(target_root).resolve() / "nk_tracking" / "sessions").resolve()
    if not sessions_dir.is_dir() or sessions_dir.is_symlink():
        return []
    try:
        with os.scandir(sessions_dir) as it:
            entries = list(it)
    except OSError:
        return []
    candidates = [cand for entry in entries if (cand := _scan_session_dir_candidate(entry, sessions_dir)) is not None]
    if len(candidates) <= max_sessions:
        return []
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    keep_names = _select_retained_session_names(candidates, active_conversation_id, max_sessions)
    removed: List[str] = []
    for _, name, dir_path in candidates:
        if name not in keep_names:
            shutil.rmtree(dir_path, ignore_errors=True)
            if not dir_path.exists():
                removed.append(name)
    return removed


def _compute_workspace_state_sha256(root: Path) -> str:
    """Calcola l'hash SHA-256 deterministico dello stato dei file."""
    resolved = root.resolve()
    if not resolved.exists():
        return hashlib.sha256(b"{}").hexdigest()
    cache_file = _state_memo_cache_path(resolved)
    disk_memo: Dict[str, List[Any]] = {}
    if cache_file.is_file():
        try:
            if isinstance(loaded := json.loads(cache_file.read_text(encoding="utf-8")), dict):
                disk_memo = loaded
        except Exception:
            pass
    files_map: Dict[str, str] = {}
    memo_dirty, now_ns = False, time.time_ns()
    stack: List[Tuple[Path, str]] = [(resolved, "")]
    skip_dirs, skip_files = _SKIP_STATE_REL_DIRS, _SKIP_STATE_REL_FILES
    skip_prefixes = tuple(f"{d}/" for d in skip_dirs)
    while stack:
        cur_dir, rel_dir = stack.pop()
        try:
            entries = list(os.scandir(cur_dir))
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if name not in _EXCLUDED_STATE_DIRS:
                        sub_rel = f"{rel_dir}/{name}" if rel_dir else name
                        if sub_rel not in skip_dirs and not sub_rel.startswith(skip_prefixes):
                            stack.append((Path(entry.path), sub_rel))
                elif entry.is_file(follow_symlinks=False) and name not in _EXCLUDED_STATE_FILENAMES:
                    rel_file = f"{rel_dir}/{name}" if rel_dir else name
                    if rel_file in skip_files or rel_file.startswith(skip_prefixes):
                        continue
                    st = entry.stat(follow_symlinks=False)
                    mtime_ns, fsize, abs_key = st.st_mtime_ns, st.st_size, entry.path
                    is_settled = (now_ns - mtime_ns) > 2_000_000_000
                    with _FILE_HASH_LOCK:
                        memo_hit = _FILE_HASH_MEMO.get(abs_key)
                    if is_settled and memo_hit is not None and memo_hit[0] == mtime_ns and memo_hit[1] == fsize:
                        files_map[rel_file] = memo_hit[2]
                        continue
                    dh = disk_memo.get(rel_file)
                    if is_settled and isinstance(dh, list) and len(dh) == 3 and dh[0] == mtime_ns and dh[1] == fsize and isinstance(dh[2], str):
                        with _FILE_HASH_LOCK:
                            _FILE_HASH_MEMO[abs_key] = (mtime_ns, fsize, dh[2])
                        files_map[rel_file] = dh[2]
                        continue
                    digest = hashlib.sha256(Path(abs_key).read_bytes()).hexdigest()
                    with _FILE_HASH_LOCK:
                        _FILE_HASH_MEMO[abs_key] = (mtime_ns, fsize, digest)
                    disk_memo[rel_file] = [mtime_ns, fsize, digest]
                    memo_dirty, files_map[rel_file] = True, digest
            except OSError:
                continue
    if memo_dirty and len(files_map) >= 16:
        try:
            ok, _ = atomic_write_text(cache_file, json.dumps(disk_memo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", fsync_data=False)
            if ok:
                _prune_handoff_memo_cache(cache_file.parent, max_files=32)
        except Exception:
            pass
    return hashlib.sha256(json.dumps(files_map, sort_keys=True).encode("utf-8")).hexdigest()


def _hash_file_cached(file_path: Path) -> str:
    """Calcola SHA-256 con memoizzazione thread-safe in-process (mtime_ns, fsize)."""
    abs_key = str(file_path)
    try:
        st = file_path.stat()
    except OSError:
        return ""
    with _FILE_HASH_LOCK:
        hit = _FILE_HASH_MEMO.get(abs_key)
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError:
        return ""
    with _FILE_HASH_LOCK:
        _FILE_HASH_MEMO[abs_key] = (st.st_mtime_ns, st.st_size, digest)
    return digest


def _compute_staging_state_sha256(target_root: Path) -> str:
    """Calcola SHA-256 deterministico dei file correnti in .staging/."""
    staging_dir = target_root / ".staging"
    if not staging_dir.is_dir():
        return hashlib.sha256(b"CLEAN_STAGING").hexdigest()
    rel_entries: List[Tuple[str, Path]] = []
    stack: List[Path] = [staging_dir]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    name = entry.name
                    if name in (".gitkeep", "__pycache__") or name.endswith((".pyc", ".pyo")):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        ep = Path(entry.path)
                        rel_entries.append((ep.relative_to(staging_dir).as_posix(), ep))
        except OSError:
            continue
    if not rel_entries:
        return hashlib.sha256(b"CLEAN_STAGING").hexdigest()
    hasher = hashlib.sha256()
    for rel_str, ep in sorted(rel_entries, key=lambda item: item[0]):
        hasher.update(f"{rel_str}\x00{_hash_file_cached(ep)}\n".encode("utf-8"))
    return hasher.hexdigest()


def write_bytes_via_2pc_locked(dst: Path, raw_bytes: bytes) -> None:
    """Scrive atomicamente raw_bytes su dst via TwoPhaseCommitEngine assumendo mutex gia' acquisiti."""
    dst_resolved = Path(dst).resolve()
    dst_resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=dst_resolved.parent, prefix=f".tmp_{dst_resolved.name}_", suffix=".tmp", delete=False) as tf:
            tmp_path = Path(tf.name)
            tf.write(raw_bytes)
            tf.flush()
            os.fsync(tf.fileno())
        if not TwoPhaseCommitEngine()._execute_atomic_commit(tmp_path, dst_resolved):
            raise OSError(f"Atomic commit fallito su {dst_resolved}")
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _atomic_commit_bytes(root: Path, dst: Path, raw_bytes: bytes, timeout_ms: int = 2000) -> None:
    """Scrive atomicamente tramite mutex Win32 e TwoPhaseCommitEngine."""
    root_resolved, dst_resolved = Path(root).resolve(), Path(dst).resolve()
    with (
        Win32NamedMutex(get_repo_batch_mutex_name(root_resolved), timeout_ms=timeout_ms, is_path=False),
        Win32NamedMutex(dst_resolved, timeout_ms=timeout_ms, is_path=True),
    ):
        write_bytes_via_2pc_locked(dst_resolved, raw_bytes)


def select_auto_checkpoint_template(dirty_staging: bool, turn: Optional[int] = None) -> str:
    """Seleziona Template 11 su dirty_staging o 1<=turn<=4, altrimenti Template 12."""
    turn_val = _parse_optional_turn(turn)
    return "Template 11" if (bool(dirty_staging) or (turn_val is not None and 1 <= turn_val <= 4)) else "Template 12"


def _has_dirty_staging_inprocess(repo_dir: Path) -> bool:
    """Rileva in-process eventuali artefatti non promossi in .staging."""
    staging_dir = repo_dir / ".staging"
    if not staging_dir.is_dir():
        return False
    stack: List[Path] = [staging_dir]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    if entry.name == ".gitkeep":
                        continue
                    if entry.is_file(follow_symlinks=False):
                        return True
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
        except OSError:
            continue
    return False


def _check_git_dirty_fast(repo_dir: Path, git_exe: str, stash_output_dir: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Controlla lo stato git su richiesta esplicita."""
    if not (repo_dir / ".git").exists():
        return _has_dirty_staging_inprocess(repo_dir), None
    git_env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(repo_dir.parent)}
    sp_mod = resolve_facade_attr(_FACADES, "subprocess", subprocess)
    try:
        status_out = sp_mod.check_output(
            [git_exe, "-C", str(repo_dir), "status", "--porcelain", "--untracked-files=no"],
            universal_newlines=True, stderr=sp_mod.DEVNULL, env=git_env, timeout=15.0,
        )
        if status_out.strip():
            stash_patch: Optional[str] = None
            if stash_output_dir:
                stash_dir = os.path.join(stash_output_dir, "stashes")
                os.makedirs(stash_dir, exist_ok=True)
                stash_patch = os.path.join(stash_dir, f"stash_{int(time.time())}.patch")
                with open(stash_patch, "w", encoding="utf-8") as patch_f:
                    sp_mod.call([git_exe, "-C", str(repo_dir), "diff"], stdout=patch_f, stderr=sp_mod.DEVNULL, env=git_env, timeout=15.0)
            return True, stash_patch
    except Exception:
        pass
    return _has_dirty_staging_inprocess(repo_dir), None


def _read_fastguard_session_start_ns(root: Path, cid: str) -> int:
    """Sonda i 4 percorsi fastguard_<cid>.json e restituisce il primo timestamp positivo."""
    clean_cid = cid.strip() if isinstance(cid, str) else ""
    if not clean_cid or clean_cid.lower() == "auto" or clean_cid.startswith("default_") or not _SAFE_SESSION_CONV_ID_RE.fullmatch(clean_cid):
        return 0
    env_hooks = os.environ.get("NK_HOOKS_TEMP_DIR", "").strip()
    cands: List[Path] = ([Path(env_hooks) / f"fastguard_{clean_cid}.json", Path(env_hooks) / "nk_hooks" / f"fastguard_{clean_cid}.json"] if env_hooks else []) + [
        Path(tempfile.gettempdir()) / "nk_hooks" / f"fastguard_{clean_cid}.json"
    ]
    if (sess_dir := resolve_session_tracking_dir(Path(root), clean_cid)) is not None:
        cands.append(sess_dir / f"fastguard_{clean_cid}.json")
    for fg_p in cands:
        try:
            if not fg_p.is_file() or not isinstance(data := json.loads(fg_p.read_text(encoding="utf-8")), dict):
                continue
            raw_ns = data.get("session_start_ns")
            if isinstance(raw_ns, int) and not isinstance(raw_ns, bool) and raw_ns > 0:
                return raw_ns
            for ts_key in ("created_at", "updated_at"):
                if (ts_ns := _parse_ts_ns_value(data.get(ts_key))) > 0:
                    return ts_ns
        except Exception:
            continue
    return 0


def resolve_baseline_verification_source(
    repo_root: Path, conversation_id: str, session_start_ns: int = 0
) -> Tuple[int, float, bool, str]:
    """Verifica evidenza pytest live di sessione o baseline su disco del repository."""
    repo_res, cid_s = Path(repo_root).resolve(), str(conversation_id or "").strip()
    sess_dir = resolve_session_tracking_dir(repo_res, cid_s)
    sess_start_ns = session_start_ns if (isinstance(session_start_ns, int) and not isinstance(session_start_ns, bool) and session_start_ns > 0) else 0
    if sess_start_ns <= 0 and cid_s:
        sess_start_ns = _read_fastguard_session_start_ns(repo_res, cid_s)
    cands: List[Path] = [sess_dir / n for n in ("pytest_iso_last.json", "pytest_result.json", "live_pytest_result.json")] if sess_dir is not None else []
    diag_env = os.environ.get("NK_DIAGNOSTICS_DIR", "").strip()
    diag_last = (Path(diag_env) if diag_env else (Path(tempfile.gettempdir()) / "nk_diagnostics")) / "pytest_iso_last.json"
    cands.extend([repo_res / "nk_tracking" / "diagnostics" / "pytest_iso_last.json", diag_last])
    for cand in cands:
        try:
            if not cand.is_file() or (cand == diag_last and (sess_start_ns <= 0 or cand.stat().st_mtime_ns < sess_start_ns)):
                continue
            data = json.loads(cand.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or (data.get("mirror_dir") and Path(str(data["mirror_dir"])).name != repo_res.name):
                continue
            rc, passed = data.get("exit_code"), data.get("passed")
            if isinstance(rc, int) and not isinstance(rc, bool) and rc == 0 and isinstance(passed, int) and not isinstance(passed, bool) and passed > 0 and data.get("failed", 0) == 0 and data.get("errors", 0) == 0 and data.get("success") is True:
                return passed, 100.0, True, "LIVE_PYTEST_ARTIFACT"
        except Exception:
            continue
    for b_cand in (repo_res / ".staging" / "nk_tracking" / "quality_baseline.json", repo_res / "nk_tracking" / "quality_baseline.json"):
        try:
            if b_cand.is_file() and isinstance(b_data := json.loads(b_cand.read_text(encoding="utf-8")), dict):
                tot_i, pass_f = _extract_baseline_pair(b_data)
                if tot_i is not None:
                    return tot_i, pass_f, False, "DISK_BASELINE_UNVERIFIED_IN_SESSION"
        except Exception:
            continue
    return 0, 0.0, False, "FALLBACK_UNVERIFIED"

# -*- coding: utf-8 -*-
"""Stato del workspace, hash SHA-256, commit atomico e baseline per nk_session_handoff."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_session_handoff.constants import (
    _BASELINE_MEMO, _EXCLUDED_STATE_DIRS, _EXCLUDED_STATE_FILENAMES, _FILE_HASH_MEMO, _workspace_root,
)

try:
    from win32_2pc_engine import TwoPhaseCommitEngine, Win32NamedMutex, get_repo_batch_mutex_name
except ImportError:
    from scripts.win32_2pc_engine import (  # type: ignore[no-redef]
        TwoPhaseCommitEngine, Win32NamedMutex, get_repo_batch_mutex_name,
    )

_FACADES = ("nk_session_handoff", "scripts.nk_session_handoff")


def _read_baseline_data(root_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Carica quality_baseline.json con memoizzazione breve."""
    eff_ws_root = Path(resolve_facade_attr(_FACADES, "_workspace_root", _workspace_root))
    base = (root_dir or eff_ws_root).resolve()
    key, now = str(base), time.time()
    cached = _BASELINE_MEMO.get(key)
    if cached is not None and (now - cached[0]) < 1.0:
        return cached[1]
    rel_p = Path("nk_tracking") / "quality_baseline.json"
    for cand in (base / ".staging" / rel_p, base / rel_p, eff_ws_root / ".staging" / rel_p, eff_ws_root / rel_p):
        try:
            if cand.is_file():
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _BASELINE_MEMO[key] = (now, data)
                    return data
        except Exception:
            pass
    return {}


def _read_baseline_tests_count(root_dir: Optional[Path] = None) -> int:
    """Legge il numero totale di Golden Tests da quality_baseline.json."""
    data = _read_baseline_data(root_dir)
    if data:
        metrics = data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
        for m_key in ("unit_tests_total", "total_golden_tests"):
            if m_key in metrics:
                raw_total = metrics[m_key]
                return int(raw_total.get("value", 183)) if isinstance(raw_total, dict) else int(raw_total)
        for flat_key in ("total_tests", "golden_tests_count", "unit_tests_total", "passed_tests"):
            if data.get(flat_key) is not None:
                return int(data[flat_key])
    return 183


def _read_baseline_pass_rate(root_dir: Optional[Path] = None) -> float:
    """Estrae il pass rate da quality_baseline.json."""
    data = _read_baseline_data(root_dir)
    if data:
        metrics = data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
        raw_pct = metrics.get("unit_tests_pass_pct")
        if isinstance(raw_pct, dict) and "value" in raw_pct:
            return float(raw_pct["value"])
        if isinstance(raw_pct, (int, float)):
            return float(raw_pct)
        for flat_k in ("pass_rate_pct", "pass_rate"):
            if data.get(flat_k) is not None:
                return float(data[flat_k])
    return 100.0


def _state_memo_cache_path(resolved_root: Path) -> Path:
    """Restituisce il percorso in TEMP per la cache stat->sha256 del workspace."""
    norm = str(resolved_root).lower().replace("/", "\\").rstrip("\\")
    key = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "nk_cache" / "handoff_memo" / f"nk_handoff_sha_memo_{key}.json"


def _prune_handoff_memo_cache(cache_dir: Path, max_files: int = 32) -> None:
    """Mantiene al massimo max_files memo SHA piu' recenti nella directory cache."""
    entries: List[Tuple[int, str, Path]] = []
    try:
        for entry in cache_dir.glob("*.json"):
            try:
                entries.append((entry.stat().st_mtime_ns, entry.name, entry))
            except OSError:
                continue
    except OSError:
        return
    if len(entries) <= max_files:
        return
    for _, _, stale in sorted(entries, key=lambda item: (item[0], item[1]), reverse=True)[max_files:]:
        try:
            stale.unlink()
        except OSError:
            pass


def _compute_workspace_state_sha256(root: Path) -> str:
    """Calcola l'hash SHA-256 deterministico dello stato dei file."""
    resolved = root.resolve()
    if not resolved.exists():
        return hashlib.sha256(b"{}").hexdigest()

    cache_file = _state_memo_cache_path(resolved)
    disk_memo: Dict[str, List[Any]] = {}
    if cache_file.is_file():
        try:
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                disk_memo = loaded
        except Exception:
            pass

    files_map: Dict[str, str] = {}
    memo_dirty, now_ns = False, time.time_ns()
    stack: List[Tuple[Path, str]] = [(resolved, "")]
    skip_dirs = ("nk_tracking/anchor", "nk_tracking/handoff", "nk_tracking/sessions", "handoff")
    skip_prefixes = tuple(f"{d}/" for d in skip_dirs)
    skip_files = ("nk_tracking/active_context.md", "nk_tracking/anchor/session_anchor.jsonl")

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
                    if name in _EXCLUDED_STATE_DIRS:
                        continue
                    sub_rel = f"{rel_dir}/{name}" if rel_dir else name
                    if sub_rel in skip_dirs or sub_rel.startswith(skip_prefixes):
                        continue
                    stack.append((Path(entry.path), sub_rel))
                elif entry.is_file(follow_symlinks=False):
                    if name in _EXCLUDED_STATE_FILENAMES:
                        continue
                    rel_file = f"{rel_dir}/{name}" if rel_dir else name
                    if rel_file in skip_files or rel_file.startswith(skip_prefixes):
                        continue
                    st = entry.stat(follow_symlinks=False)
                    mtime_ns, fsize, abs_key = st.st_mtime_ns, st.st_size, entry.path
                    is_settled = (now_ns - mtime_ns) > 2_000_000_000
                    memo_hit = _FILE_HASH_MEMO.get(abs_key)
                    if is_settled and memo_hit is not None and memo_hit[0] == mtime_ns and memo_hit[1] == fsize:
                        files_map[rel_file] = memo_hit[2]
                        continue
                    dh = disk_memo.get(rel_file)
                    if is_settled and isinstance(dh, list) and len(dh) == 3 and dh[0] == mtime_ns and dh[1] == fsize and isinstance(dh[2], str):
                        _FILE_HASH_MEMO[abs_key] = (mtime_ns, fsize, dh[2])
                        files_map[rel_file] = dh[2]
                        continue
                    digest = hashlib.sha256(Path(abs_key).read_bytes()).hexdigest()
                    _FILE_HASH_MEMO[abs_key] = (mtime_ns, fsize, digest)
                    disk_memo[rel_file] = [mtime_ns, fsize, digest]
                    memo_dirty, files_map[rel_file] = True, digest
            except OSError:
                continue

    if memo_dirty and len(files_map) >= 16:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(disk_memo, separators=(",", ":")), encoding="utf-8")
            _prune_handoff_memo_cache(cache_file.parent, max_files=32)
        except OSError:
            pass
    return hashlib.sha256(json.dumps(files_map, sort_keys=True).encode("utf-8")).hexdigest()


def _sanitize_ste100_inline(value: str, fallback: str) -> str:
    """Sanitizza un token inline per active_context.md."""
    cleaned = str(value or "").replace("\r", " ").replace("\n", " ").replace("`", "")
    cleaned = cleaned.replace(" \u2014 ", "_").replace("\u2014", "_").replace("\u2013", "_").replace(" - ", "_")
    cleaned = " ".join(cleaned.split()).strip()[:80]
    return cleaned if cleaned else fallback


def _hash_file_cached(file_path: Path) -> str:
    """Calcola SHA-256 con memoizzazione in-process (mtime_ns, fsize)."""
    abs_key = str(file_path)
    try:
        st = file_path.stat()
    except OSError:
        return ""
    hit = _FILE_HASH_MEMO.get(abs_key)
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError:
        return ""
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
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
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


def _atomic_commit_bytes(root: Path, dst: Path, raw_bytes: bytes, timeout_ms: int = 2000) -> None:
    """Scrive atomicamente tramite mutex Win32 e TwoPhaseCommitEngine."""
    root_resolved, dst_resolved = Path(root).resolve(), Path(dst).resolve()
    with (
        Win32NamedMutex(get_repo_batch_mutex_name(root_resolved), timeout_ms=timeout_ms, is_path=False),
        Win32NamedMutex(dst_resolved, timeout_ms=timeout_ms, is_path=True),
    ):
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


def _parse_optional_turn(raw_turn: Any) -> Optional[int]:
    """Valida il turno opzionale (0..5) rifiutando booleani."""
    if raw_turn is None:
        return None
    if isinstance(raw_turn, bool):
        raise ValueError(f"Il turno non puo essere booleano: {raw_turn}")
    if isinstance(raw_turn, str):
        clean_s = raw_turn.strip()
        if not clean_s:
            return None
        if not re.fullmatch(r"-?\d+", clean_s):
            raise ValueError(f"Il turno deve essere un intero valido (0..5): {raw_turn!r}")
        turn_val = int(clean_s)
    elif isinstance(raw_turn, int):
        turn_val = raw_turn
    else:
        raise ValueError(f"Tipo turno non valido (0..5): {raw_turn!r}")
    if not (0 <= turn_val <= 5):
        raise ValueError(f"Il turno deve essere compreso tra 0 e 5: {turn_val}")
    return turn_val


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
            universal_newlines=True, stderr=sp_mod.DEVNULL, env=git_env, timeout=0.25,
        )
        if status_out.strip():
            stash_patch: Optional[str] = None
            if stash_output_dir:
                stash_dir = os.path.join(stash_output_dir, "stashes")
                os.makedirs(stash_dir, exist_ok=True)
                stash_patch = os.path.join(stash_dir, f"stash_{int(time.time())}.patch")
                with open(stash_patch, "w", encoding="utf-8") as patch_f:
                    sp_mod.call([git_exe, "-C", str(repo_dir), "diff"], stdout=patch_f, stderr=sp_mod.DEVNULL, env=git_env, timeout=0.25)
            return True, stash_patch
    except Exception:
        pass
    return _has_dirty_staging_inprocess(repo_dir), None

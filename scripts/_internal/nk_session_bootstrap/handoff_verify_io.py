#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Primitive I/O, scansione metadati Fast-Stat, scope e tail anchor per handoff_verify."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.io import atomic_write_text
from _internal.nk_common.paths import is_nk_proget_online_path

_FASTSTAT_TTL_SEC: float = 900.0
_DEFAULT_SKIP_DIRS: Tuple[str, ...] = ("nk_tracking/anchor", "nk_tracking/handoff", "nk_tracking/sessions", "handoff")
_DEFAULT_SKIP_FILES = frozenset(("nk_tracking/active_context.md", "nk_tracking/anchor/session_anchor.jsonl"))
_V2_HINT_RE = re.compile(r"\[NK-ANCHOR:(?:START|END):HANDOFF_V2:|# \[NK-HANDOFF-V2\]", re.IGNORECASE)
_SAFE_CID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _ensure_handoff_staging_overlay() -> None:
    """Garantisce la precedenza di .staging/_internal/nk_session_handoff se eseguito da staging."""
    try:
        scripts_dir = Path(__file__).resolve().parents[2]
        if scripts_dir.parent.name != ".staging":
            return
        hub_root = scripts_dir.parent.parent
        from _internal.nk_common.facade_boot import _prepend_pkg_overlay

        _prepend_pkg_overlay("_internal.nk_session_handoff", str(scripts_dir / "_internal" / "nk_session_handoff"), str(hub_root / "scripts" / "_internal" / "nk_session_handoff"))
    except (ImportError, OSError, IndexError, AttributeError):
        return


def _sanitize_cid(cid: str) -> str:
    """Valida un conversation_id prevenendo path traversal e sentinel non validi."""
    clean = str(cid or "").strip()
    bad = not clean or clean in (".", "..") or clean.lower() == "auto" or clean.startswith("default_") or ".." in clean
    return "" if bad or not _SAFE_CID_RE.fullmatch(clean) else clean


def _is_valid_cid(cid: str) -> bool:
    return bool(_sanitize_cid(cid))


def _get_state_exclusions() -> Tuple[Any, Any, Any, Tuple[str, ...], Any]:
    """Carica i set canonici di esclusione stato da nk_session_handoff.constants."""
    _ensure_handoff_staging_overlay()
    from _internal.nk_session_handoff import constants as ho_consts

    skip_dirs = frozenset(str(d).rstrip("/") for d in getattr(ho_consts, "_SKIP_STATE_REL_DIRS", _DEFAULT_SKIP_DIRS))
    skip_prefixes = tuple(f"{d}/" for d in skip_dirs)
    return ho_consts._EXCLUDED_STATE_DIRS, ho_consts._EXCLUDED_STATE_FILENAMES, skip_dirs, skip_prefixes, frozenset(getattr(ho_consts, "_SKIP_STATE_REL_FILES", _DEFAULT_SKIP_FILES))


def _process_meta_entry(entry: os.DirEntry[str], rel_dir: str, excl: Tuple[Any, Any, Any, Tuple[str, ...], Any], meta: Dict[str, List[int]], stack: List[Tuple[str, str]]) -> None:
    """Elabora una singola voce file/directory escludendo path tracking."""
    ex_dirs, ex_files, skip_dirs, skip_prefixes, skip_files = excl
    name = entry.name
    sub_rel = f"{rel_dir}/{name}" if rel_dir else name
    if sub_rel.startswith(skip_prefixes):
        return
    try:
        if entry.is_dir(follow_symlinks=False):
            if name not in ex_dirs and sub_rel not in skip_dirs:
                stack.append((entry.path, sub_rel))
            return
        if entry.is_file(follow_symlinks=False) and name not in ex_files and sub_rel not in skip_files:
            st = entry.stat(follow_symlinks=False)
            meta[sub_rel] = [st.st_mtime_ns, st.st_size]
    except OSError:
        return


def _scan_tracked_metadata(repo_root: Path) -> Dict[str, List[int]]:
    """Scansiona i metadati (mtime_ns, size) di tutto l'albero repo senza leggere contenuto."""
    excl = _get_state_exclusions()
    meta: Dict[str, List[int]] = {}
    resolved = repo_root.resolve()
    if not resolved.is_dir():
        return meta
    stack: List[Tuple[str, str]] = [(str(resolved), "")]
    while stack:
        cur_dir, rel_dir = stack.pop()
        try:
            with os.scandir(cur_dir) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            _process_meta_entry(entry, rel_dir, excl, meta, stack)
    return meta


def _resolve_live_state_sha256(repo_root: Path, compute_sha_fn: Any) -> Tuple[str, str]:
    """Restituisce (state_sha256, cache_mode) usando cache Fast-Stat NVMe con TTL 900s."""
    norm = os.path.realpath(str(repo_root)).lower().replace("/", "\\").rstrip("\\")
    sha16 = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    cache_path = Path(tempfile.gettempdir()) / "nk_diagnostics" / f"handoff_faststat_{sha16}.json"
    meta_map = _scan_tracked_metadata(repo_root)
    meta_digest = hashlib.sha256(json.dumps(meta_map, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    now = time.time()
    if cache_path.is_file():
        try:
            c = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(c, dict) and c.get("repo_root") == norm and (now - float(c.get("timestamp_epoch", 0.0))) <= _FASTSTAT_TTL_SEC and c.get("meta_digest") == meta_digest and isinstance(c.get("state_sha256"), str) and len(c["state_sha256"]) == 64:
                return c["state_sha256"], "FAST_STAT_HIT"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            c = None
    live_sha = compute_sha_fn(repo_root)
    payload_json = json.dumps({"repo_root": norm, "timestamp_epoch": now, "meta_digest": meta_digest, "file_count": len(meta_map), "state_sha256": live_sha}, separators=(",", ":"))
    atomic_write_text(cache_path, payload_json, encoding="utf-8", fsync_data=False)
    return live_sha, "COLD_DEEP_HASH"


def _resolve_scope_candidate(repo_root: Any) -> Optional[Path]:
    """Risolve un percorso candidato rifiutando input non validi o NK Proget/Online."""
    try:
        cand_res = Path(repo_root).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    return None if is_nk_proget_online_path(cand_res) else cand_res


def _is_under_external_root(cand_res: Path, ext_roots: Sequence[Path]) -> bool:
    """Verifica che cand_res sia sottodirectory reale di almeno una root esterna autorizzata."""
    for ext_res in ext_roots:
        if cand_res != ext_res and cand_res.is_relative_to(ext_res):
            return True
    return False


def _is_repo_root_in_scope(repo_root: Any, allowed_roots: Sequence[Path]) -> bool:
    """Verifica che repo_root risolva a hub_root, project_root o dentro root esterne autorizzate."""
    cand_res = _resolve_scope_candidate(repo_root)
    if cand_res is None or len(allowed_roots) < 2:
        return False
    return cand_res in (allowed_roots[0], allowed_roots[1]) or _is_under_external_root(cand_res, allowed_roots[2:])


def _read_anchor_tail_cid(cand: Path) -> Optional[Tuple[Optional[str], bool]]:
    """Legge conversation_id dall'ultimo record valido o segnala corruzione tail."""
    try:
        if (sz := cand.stat().st_size) <= 0:
            return None
        with open(cand, "rb") as fh:
            fh.seek(max(0, sz - 8192))
            lines = [ln.strip() for ln in fh.read().decode("utf-8", errors="replace").splitlines() if ln.strip()]
        if not lines:
            return None
        rec = json.loads(lines[-1])
        if not isinstance(rec, dict):
            return None, True
        return (str(rec.get("conversation_id") or "").strip() or None), False
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return None, True


def _inspect_anchor_tail(repo_root: Path, current_cid: str) -> Tuple[Optional[str], bool]:
    """Legge l'ultimo record di session_anchor.jsonl restituendo (last_cid, corrupted)."""
    cands: List[Path] = []
    if safe_cid := _sanitize_cid(current_cid):
        sess_base = (repo_root / "nk_tracking" / "sessions").resolve()
        sess_cand = (sess_base / safe_cid / "session_anchor.jsonl").resolve()
        if sess_cand.is_relative_to(sess_base):
            cands.append(sess_cand)
    cands.append(repo_root / "nk_tracking" / "anchor" / "session_anchor.jsonl")
    for cand in cands:
        if cand.is_file() and (res := _read_anchor_tail_cid(cand)) is not None:
            return res
    return None, False


def _find_fallback_prompt_file(project_root: Path, hub_root: Optional[Path]) -> Optional[Path]:
    """Individua il file next_session_prompt.md in project_root o hub_root."""
    fb_cands = [Path(project_root) / "nk_tracking" / "handoff" / "next_session_prompt.md"]
    if hub_root is not None:
        try:
            diff_root = Path(hub_root).resolve() != Path(project_root).resolve()
        except OSError:
            diff_root = Path(hub_root) != Path(project_root)
        if diff_root:
            fb_cands.append(Path(hub_root) / "nk_tracking" / "handoff" / "next_session_prompt.md")
    return next((c for c in fb_cands if c.is_file()), None)

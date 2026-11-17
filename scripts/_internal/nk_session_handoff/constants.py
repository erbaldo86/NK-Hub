# -*- coding: utf-8 -*-
"""Costanti e helper base di sessione per nk_session_handoff."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import (
    DEFAULT_MILESTONE_ID as _COMMON_MILESTONE_ID,
    VERSION as _COMMON_VERSION,
)

HANDOFF_SCHEMA_VERSION = _COMMON_VERSION
HANDOFF_VERSION = HANDOFF_SCHEMA_VERSION
VERSION = HANDOFF_SCHEMA_VERSION
DEFAULT_MILESTONE_ID = _COMMON_MILESTONE_ID

_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent.parent
_workspace_root = (
    _SCRIPTS_DIR.parent.parent
    if _SCRIPTS_DIR.parent.name == ".staging"
    else _SCRIPTS_DIR.parent
)

_BACKTICK_RUN_RE = re.compile(r"`+")
_SAFE_SESSION_CONV_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_FILE_HASH_MEMO: Dict[str, Tuple[int, int, str]] = {}
_BASELINE_MEMO: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_TRANSCRIPT_CURSOR_CACHE: Dict[str, Dict[str, Any]] = {}
_TRANSCRIPT_BACKSCAN_CHUNK_BYTES = 65536
_TRANSCRIPT_BACKSCAN_MAX_BYTES = 50 * 1024 * 1024
_COMPACTION_MARKER = "<CONTEXT_SUMMARY>"

_EXCLUDED_STATE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".staging",
    ".wal",
}
_EXCLUDED_STATE_FILENAMES = {
    "rsi_telemetry.jsonl",
    "fast_bootstrap_cache.json",
    "bootstrap_state.json",
}


def resolve_session_tracking_dir(root: Path, conv_id: Optional[str]) -> Optional[Path]:
    """Valida conv_id e restituisce root/nk_tracking/sessions/<conv_id>."""
    if not isinstance(conv_id, str):
        return None
    clean_id = conv_id.strip()
    if not clean_id or clean_id.startswith("default_"):
        return None
    if not _SAFE_SESSION_CONV_ID_RE.fullmatch(clean_id):
        return None
    base_root = Path(root).resolve()
    sessions_base = (base_root / "nk_tracking" / "sessions").resolve()
    sess_dir = (sessions_base / clean_id).resolve()
    if not sess_dir.is_relative_to(sessions_base):
        return None
    return sess_dir


def _dynamic_code_fence(body: str, min_len: int = 3) -> str:
    """Restituisce un code-fence dinamico piu lungo di ogni backtick interno."""
    runs = [len(m.group(0)) for m in _BACKTICK_RUN_RE.finditer(body or "")]
    needed = max(min_len, (max(runs) + 1) if runs else min_len)
    return "`" * needed


def _resolve_git_executable() -> str:
    """Risolve il percorso dell'eseguibile git."""
    found = shutil.which("git")
    if found:
        return found
    for candidate in (
        str(Path.home() / "AppData" / "Local" / "Programs" / "Git" / "cmd" / "git.exe"),
        "C:/Program Files/Git/cmd/git.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return "git"


def _discover_default_transcript() -> str:
    """Individua rapidamente il trascritto attivo in brain."""
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if not brain_dir.exists():
        return ""
    now = time.time()
    candidates: List[Tuple[float, str]] = []
    try:
        dir_items: List[Tuple[float, str]] = []
        with os.scandir(brain_dir) as it:
            for entry in it:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                try:
                    dst = entry.stat(follow_symlinks=False)
                    dir_items.append(
                        (max(getattr(dst, "st_ctime", 0.0), dst.st_mtime), entry.path)
                    )
                except OSError:
                    continue
        dir_items.sort(key=lambda x: x[0], reverse=True)
        for _, dpath in dir_items[:12]:
            cand_str = os.path.join(dpath, ".system_generated", "logs", "transcript.jsonl")
            try:
                mtime = os.stat(cand_str).st_mtime
                if (now - mtime) <= 1800.0:
                    candidates.append((mtime, cand_str))
            except OSError:
                continue
    except OSError:
        return ""
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, cpath in candidates[:6]:
        try:
            with open(cpath, "rb") as bf:
                head = bf.read(1536)
            if b"<SYSTEM_MESSAGE>" in head and b"sender=" in head:
                continue
            return cpath
        except OSError:
            continue
    return candidates[0][1]

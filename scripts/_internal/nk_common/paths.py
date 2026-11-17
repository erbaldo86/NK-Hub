# -*- coding: utf-8 -*-
"""Risoluzione deterministica di scripts/, workspace root e riconfigurazione stream UTF-8."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def resolve_scripts_dir(anchor_file: str) -> str:
    """Risolve il percorso della directory scripts/ a partire dal file ancora."""
    cur = Path(anchor_file or __file__).resolve()
    if cur.name == "scripts" and (cur.is_dir() or not cur.suffix):
        return str(cur)
    for anc in cur.parents:
        if anc.name == "scripts":
            return str(anc)
    return str(cur.parent if cur.suffix or cur.is_file() else cur)


def resolve_workspace_root(anchor_file: str) -> str:
    """Risolve la radice del workspace gestendo scripts/, _internal/ e .staging/scripts/."""
    cur = Path(anchor_file or __file__).resolve()
    for cand in (cur, *cur.parents):
        if cand.name == "scripts":
            parent = cand.parent
            if parent.name == ".staging":
                return str(parent.parent)
            return str(parent)
        if cand.name == ".staging":
            return str(cand.parent)
    return str(cur.parent.parent if cur.parent != cur else cur)


def reconfigure_streams(include_stdin: bool = False) -> None:
    """Riconfigura gli stream standard in UTF-8 senza dipendenze esterne."""
    streams = (sys.stdout, sys.stderr, sys.stdin) if include_stdin else (sys.stdout, sys.stderr)
    for stream in streams:
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def normalize_rel_path(raw: str) -> str:
    """Normalizza un percorso relativo rimuovendo spazi, virgolette, ./ e / iniziali."""
    norm = str(raw or "").strip().strip("\"'").strip().replace("\\", "/")
    while norm.startswith(("./", "/")):
        norm = norm[2:] if norm.startswith("./") else norm.lstrip("/")
    return norm


def get_hooks_temp_dir_common(create: bool = True) -> Path:
    """Restituisce la directory temporanea per gli hook creandola se richiesto."""
    env_dir = os.environ.get("NK_HOOKS_TEMP_DIR", "").strip()
    hooks_dir = Path(env_dir) if env_dir else (Path(tempfile.gettempdir()) / "nk_hooks")
    if create:
        hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir

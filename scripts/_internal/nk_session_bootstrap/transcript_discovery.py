#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scoperta runtime dei transcript attivi, directory brain e conversation_id."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ..nk_common.paths import get_hooks_temp_dir_common
from ..nk_common.transcript_guards import (
    is_subagent_transcript_head as _is_tv03_subagent_transcript_head,
)


def get_hooks_temp_dir() -> Path:
    """Restituisce la directory temporanea degli hook runtime."""
    return get_hooks_temp_dir_common(create=False)


def _extract_cid_from_hook_name(fname: str) -> str:
    """Estrae il conversation_id dai nomi file probe, fastguard o integrity."""
    cid = ""
    if fname.startswith("probe_") and fname.endswith(".jsonl"):
        cid = fname[len("probe_") : -len(".jsonl")].strip()
    elif fname.startswith("fastguard_") and fname.endswith(".json"):
        cid = fname[len("fastguard_") : -len(".json")].strip()
    elif fname.endswith("_integrity.json"):
        cid = fname[: -len("_integrity.json")].strip()
    return "" if not cid or cid == "default" or cid.startswith("default_") else cid


def _iter_regular_hook_entries(hooks_dir: Path) -> List[os.DirEntry[str]]:
    """Elenca in sicurezza i file regolari dentro hooks_dir."""
    try:
        with os.scandir(hooks_dir) as it:
            return [e for e in it if e.is_file(follow_symlinks=False)]
    except OSError:
        return []


def infer_active_conversation_id(cls: Any, max_age_seconds: float = 60.0) -> str:
    """Deduce il conversation_id dai file probe, fastguard o integrity recenti."""
    hooks_dir = cls._get_hooks_temp_dir()
    if not hooks_dir.exists():
        return ""
    now, best_conv, best_mtime = time.time(), "", -1.0
    for entry in _iter_regular_hook_entries(hooks_dir):
        if not (cid := _extract_cid_from_hook_name(entry.name)):
            continue
        try:
            mtime = entry.stat().st_mtime
            if (now - mtime) <= max_age_seconds and mtime > best_mtime:
                best_mtime, best_conv = mtime, cid
        except OSError:
            continue
    return best_conv


def _is_newer_dir_entry(entry: os.DirEntry[str], conv_name: str, cand_mtime: float, now: float, win: float) -> bool:
    """Verifica se entry corrisponde a una directory conversazione piu recente."""
    if not entry.is_dir(follow_symlinks=False) or entry.name == conv_name:
        return False
    try:
        st = entry.stat()
        dir_ts = max(getattr(st, "st_ctime", 0.0), st.st_mtime)
        return (now - dir_ts) <= win and dir_ts > cand_mtime
    except OSError:
        return False


def has_newer_brain_directory(cand_tp: Path, recent_window_sec: float = 60.0) -> bool:
    """Verifica se in brain/ esiste una directory conversazione piu recente del transcript in cache."""
    try:
        cand_mtime = cand_tp.stat().st_mtime
        conv_dir = cand_tp.parents[2] if len(cand_tp.parents) >= 3 else cand_tp.parent
        brain_dir = conv_dir.parent
        if not brain_dir.exists():
            return False
        now = time.time()
        with os.scandir(brain_dir) as it:
            return any(_is_newer_dir_entry(e, conv_dir.name, cand_mtime, now, recent_window_sec) for e in it)
    except (OSError, IndexError, ValueError):
        return False


def _inspect_brain_dir_entry(entry: os.DirEntry[str], now: float, fallback_window: float) -> Tuple[Optional[tuple[float, Path]], float]:
    """Valuta una singola sottocartella di brain_dir per transcript o dir unflushed."""
    cand = Path(entry.path) / ".system_generated" / "logs" / "transcript.jsonl"
    try:
        if not cand.exists():
            dst = entry.stat()
            dir_ts = max(getattr(dst, "st_ctime", 0.0), dst.st_mtime)
            return None, (dir_ts if (now - dir_ts) <= fallback_window else -1.0)
        cmtime = cand.stat().st_mtime
        return ((cmtime, cand) if (now - cmtime) <= fallback_window else None), -1.0
    except OSError:
        return None, -1.0


def _collect_brain_candidates(brain_dir: Path, fallback_window: float) -> Tuple[List[tuple[float, Path]], float]:
    """Raccoglie i transcript recenti in brain_dir e il timestamp dir non ancora flushata."""
    now, candidates, newest_dir_ts = time.time(), [], -1.0
    with os.scandir(brain_dir) as it:
        dirs = [e for e in it if e.is_dir(follow_symlinks=False)]
    for entry in dirs:
        cand_item, dir_ts = _inspect_brain_dir_entry(entry, now, fallback_window)
        if cand_item is not None:
            candidates.append(cand_item)
        if dir_ts > newest_dir_ts:
            newest_dir_ts = dir_ts
    return candidates, newest_dir_ts


def _classify_transcript_candidate(self_obj: Any, cand: Path) -> Optional[bool]:
    """Restituisce True se subagent, False se sessione principale, None su errore lettura."""
    try:
        with open(cand, "rb") as f:
            head_bytes = f.read(16384)
    except OSError:
        return None
    has_real_user = any(
        self_obj._extract_user_prompt_from_line(ln) is not None for ln in head_bytes.splitlines()[:24]
    )
    return _is_tv03_subagent_transcript_head(cand) or (
        self_obj._is_subagent_transcript_head(head_bytes) and not has_real_user
    )


def _pick_best_transcript(self_obj: Any, candidates: List[tuple[float, Path]], newest_dir_ts: float) -> Optional[Path]:
    """Seleziona il transcript piu recente dando priorita alle sessioni non subagent."""
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_file, best_mtime = None, -1.0
    fb_file, fb_mtime = None, -1.0
    for cmtime, cand in candidates[:8]:
        if (is_sub := _classify_transcript_candidate(self_obj, cand)) is None:
            continue
        if not is_sub and cmtime > best_mtime:
            best_mtime, best_file = cmtime, cand
        elif is_sub and cmtime > fb_mtime:
            fb_mtime, fb_file = cmtime, cand
    chosen_mtime, chosen_file = (best_mtime, best_file) if best_file is not None else (fb_mtime, fb_file)
    return None if (newest_dir_ts > 0.0 and newest_dir_ts > chosen_mtime) else chosen_file


def find_recent_transcript(
    self_obj: Any, brain_dir: Path, max_age_seconds: float = 120.0
) -> Optional[Path]:
    """Individua il transcript attivo usando guardia TV-03 e presenza di USER_INPUT reali."""
    if self_obj.explicit_transcript_path and self_obj.explicit_transcript_path.exists():
        return self_obj.explicit_transcript_path
    if not brain_dir.exists():
        return None
    if self_obj.conversation_id:
        conv_tp = brain_dir / self_obj.conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
        return conv_tp if conv_tp.exists() else None
    try:
        candidates, newest_dir_ts = _collect_brain_candidates(brain_dir, min(float(max_age_seconds), 120.0))
        return _pick_best_transcript(self_obj, candidates, newest_dir_ts) if candidates else None
    except (OSError, ValueError, TypeError):
        return None

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Risoluzione transcript attivo, rilevamento trigger onboarding e Meta-Prompt Gate."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..nk_common.paths import get_hooks_temp_dir_common  # noqa: F401
from ..nk_common.transcript_guards import (  # noqa: F401
    is_subagent_transcript_head as _is_tv03_subagent_transcript_head,
)
from ..nk_common.transcript_io import strip_antigravity_envelope
from . import constants as _consts
from .transcript_discovery import (  # noqa: F401
    find_recent_transcript,
    get_hooks_temp_dir,
    has_newer_brain_directory,
    infer_active_conversation_id,
)


def _temp_root_flags(brain_dir: Path, repo_root: Path) -> Tuple[bool, bool]:
    """Verifica se brain_dir o repo_root risiedono nelle directory temporanee."""
    try:
        brain_res, repo_res = brain_dir.resolve(), repo_root.resolve()
        temp_bases = [Path(tempfile.gettempdir()).resolve()]
        for env_k in ("TEMP", "TMP"):
            if env_v := os.environ.get(env_k, "").strip():
                temp_bases.append(Path(env_v).resolve())
        if env_hooks := os.environ.get("NK_HOOKS_TEMP_DIR", "").strip():
            temp_bases.append(Path(env_hooks).resolve().parent)
        return (
            any(brain_res.is_relative_to(tb) for tb in temp_bases),
            any(repo_res.is_relative_to(tb) for tb in temp_bases),
        )
    except (OSError, ValueError, RuntimeError):
        return False, False


def _bind_recent_conv_transcript(self_obj: Any, brain_dir: Path) -> Optional[Path]:
    """Risolve il transcript recente e deduce conversation_id quando mancante."""
    recent_tp = self_obj._find_recent_transcript(brain_dir, max_age_seconds=120.0)
    if recent_tp is None or not recent_tp.is_file():
        return None
    if not self_obj.conversation_id and len(recent_tp.parents) >= 3:
        cand_cid = recent_tp.parents[2].name
        if cand_cid and not cand_cid.startswith("default_"):
            self_obj.conversation_id = cand_cid
    return recent_tp


def _brain_dir() -> Path:
    """Restituisce la directory brain dell'utente corrente."""
    home_raw = os.environ.get("USERPROFILE", "").strip()
    return (Path(home_raw) if home_raw else Path.home()) / ".gemini" / "antigravity" / "brain"


def resolve_bound_transcript_path(self_obj: Any) -> Optional[Path]:
    """Risolve il percorso del transcript vincolato anche per project_root != hub_root."""
    tp = self_obj.transcript_path or self_obj.explicit_transcript_path
    if tp is not None:
        return tp if tp.is_file() else None
    brain_dir = _brain_dir()
    if self_obj.conversation_id and not self_obj.conversation_id.startswith("default_"):
        cand_tp = brain_dir / self_obj.conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
        return cand_tp if cand_tp.is_file() else None
    hub_root = Path(_consts._get_facade_attr("HUB_ROOT", _consts.HUB_ROOT)).resolve()
    in_temp_brain, repo_in_temp = _temp_root_flags(brain_dir, self_obj.repo_root)
    if self_obj.repo_root.resolve() == hub_root or in_temp_brain or not repo_in_temp:
        return _bind_recent_conv_transcript(self_obj, brain_dir)
    return None


def _flatten_user_content(raw_val: Any) -> str:
    """Converte content/text utente da stringa o lista di parti in testo pulito."""
    if not isinstance(raw_val, list):
        return str(raw_val or "").strip()
    parts: List[str] = []
    for item in raw_val:
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
        elif isinstance(item, dict):
            txt = item.get("text") or item.get("content")
            if isinstance(txt, str) and txt.strip():
                parts.append(txt.strip())
    return "\n".join(parts).strip()


def _is_real_user_rec(rec: Dict[str, Any]) -> bool:
    """Verifica se un record JSONL rappresenta un messaggio utente reale."""
    rtype = str(rec.get("type") or "").upper()
    if rtype == "USER_INPUT":
        return True
    if rtype != "":
        return False
    src = str(rec.get("source") or "").upper()
    role = str(rec.get("role") or "").upper()
    return "USER" in src or "USER" in role


def extract_user_prompt_from_line(line_bytes: bytes) -> Optional[str]:
    """Estrae il contenuto utente reale rimuovendo eventuali wrapper XML Antigravity."""
    if not (line_s := line_bytes.strip()).startswith(b"{"):
        return None
    try:
        rec = json.loads(line_s.decode("utf-8", errors="replace"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(rec, dict) or not _is_real_user_rec(rec):
        return None
    raw_val = rec.get("content") if rec.get("content") is not None else rec.get("text")
    if not (raw_content := _flatten_user_content(raw_val)):
        return None
    cleaned = strip_antigravity_envelope(raw_content).strip()
    if not cleaned or cleaned.lstrip().startswith(("<CONTEXT_SUMMARY>", "# Resuming from a compaction")):
        return None
    return cleaned


def _get_cached_user_prompt(
    cached: Optional[Dict[str, Any]], tp: Path, t_mtime: float, t_size: int
) -> Tuple[bool, Optional[str]]:
    """Verifica cache prompt valida su path, mtime e size restituendo (hit, prompt)."""
    if (
        cached is not None
        and cached.get("last_transcript_path") == str(tp)
        and float(cached.get("transcript_mtime", -1.0)) == t_mtime
        and int(cached.get("transcript_size", -1)) == t_size
        and "cached_latest_user_prompt" in cached
    ):
        cp = cached.get("cached_latest_user_prompt")
        return True, (str(cp) if isinstance(cp, str) else None)
    return False, None


def _scan_open_transcript_tail(self_obj: Any, bf: Any, t_size: int, chunk_size: int) -> Optional[str]:
    """Scansiona a ritroso il file binario aperto fino al primo USER_INPUT valido."""
    offset, carry = t_size, b""
    while offset > 0:
        read_len = min(chunk_size, offset)
        offset -= read_len
        bf.seek(offset)
        lines = (bf.read(read_len) + carry).splitlines()
        carry, scan_lines = (lines[0], lines[1:]) if (offset > 0 and lines) else (b"", lines)
        for raw_ln in reversed(scan_lines):
            if (found := self_obj._extract_user_prompt_from_line(raw_ln)) is not None:
                return found
    return self_obj._extract_user_prompt_from_line(carry) if carry else None


def detect_latest_user_prompt(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Estrae il prompt esplicito o l'ultimo USER_INPUT verificando prima stat e cache (BOOT-01)."""
    if self_obj.explicit_prompt is not None:
        stripped = strip_antigravity_envelope(str(self_obj.explicit_prompt)).strip()
        self_obj._last_detected_user_prompt = stripped or None
        return self_obj._last_detected_user_prompt
    if (tp := self_obj._resolve_bound_transcript_path()) is None:
        self_obj._last_detected_user_prompt = None
        return None
    try:
        t_stat = tp.stat()
        t_mtime, t_size = t_stat.st_mtime, t_stat.st_size
    except OSError:
        self_obj._last_detected_user_prompt = None
        return None
    hit, cached_val = _get_cached_user_prompt(cached, tp, t_mtime, t_size)
    if hit:
        self_obj._last_detected_user_prompt = cached_val
        return cached_val
    if t_size <= 0:
        self_obj._last_detected_user_prompt = None
        return None
    chunk_size = int(_consts._get_facade_attr("BINARY_CHUNK_SIZE", _consts.BINARY_CHUNK_SIZE))
    try:
        with open(tp, "rb") as bf:
            found = _scan_open_transcript_tail(self_obj, bf, t_size, chunk_size)
    except (OSError, ValueError):
        found = None
    self_obj._last_detected_user_prompt = found
    return found


def resolve_onboarding_and_gate_mode(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> tuple[str, str]:
    """Emette ONBOARDING_BYPASS_VERIFIED solo su vero trigger utente verificato (BOOT-01)."""
    if self_obj._resolved_gate_tuple is not None:
        return self_obj._resolved_gate_tuple
    default_mode = os.environ.get("NK_META_PROMPT_GATE_MODE", "CONFIRM").strip().upper()
    if default_mode not in ("CONFIRM", "ECHO", "OFF"):
        default_mode = "CONFIRM"
    triggers = _consts._get_facade_attr("ONBOARDING_TRIGGERS", _consts.ONBOARDING_TRIGGERS)
    user_prompt = self_obj._detect_latest_user_prompt(cached=cached)
    if user_prompt is not None:
        norm_p = " ".join(re.sub(r"[^\w\s]|_", " ", user_prompt.lower().strip()).split())
        if norm_p in triggers:
            res = ("ONBOARDING_BYPASS_VERIFIED", "BYPASSED")
            self_obj._resolved_gate_tuple = res
            return res
    res = ("NONE", default_mode)
    self_obj._resolved_gate_tuple = res
    return res


def verify_meta_prompt_gate_state(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Verifica lo stato del cancello universale Meta-Prompt sincronizzato con l'onboarding."""
    _ob_status, mode = self_obj._resolve_onboarding_and_gate_mode(cached=cached)
    enabled = mode not in ("OFF", "BYPASSED")
    return {
        "passed": True,
        "enabled": enabled,
        "mode": mode,
        "details": f"Universal Meta-Prompt Gate active ({mode}).",
    }

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Risoluzione transcript attivo, rilevamento trigger onboarding e Meta-Prompt Gate."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..nk_common.paths import get_hooks_temp_dir_common
from ..nk_common.transcript_io import strip_antigravity_envelope
from . import constants as _consts


def get_hooks_temp_dir() -> Path:
    """Restituisce la directory temporanea degli hook runtime."""
    return get_hooks_temp_dir_common(create=False)


def infer_active_conversation_id(cls: Any, max_age_seconds: float = 60.0) -> str:
    """Deduce il conversation_id dai file probe, fastguard o integrity recenti."""
    hooks_dir = cls._get_hooks_temp_dir()
    if not hooks_dir.exists():
        return ""
    now = time.time()
    best_conv = ""
    best_mtime = -1.0
    try:
        with os.scandir(hooks_dir) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                fname = entry.name
                cid = ""
                if fname.startswith("probe_") and fname.endswith(".jsonl"):
                    cid = fname[len("probe_") : -len(".jsonl")].strip()
                elif fname.startswith("fastguard_") and fname.endswith(".json"):
                    cid = fname[len("fastguard_") : -len(".json")].strip()
                elif fname.endswith("_integrity.json"):
                    cid = fname[: -len("_integrity.json")].strip()
                if not cid or cid == "default" or cid.startswith("default_"):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                    if (now - mtime) <= max_age_seconds and mtime > best_mtime:
                        best_mtime = mtime
                        best_conv = cid
                except Exception:
                    continue
    except Exception:
        return ""
    return best_conv


def has_newer_brain_directory(
    cand_tp: Path, recent_window_sec: float = 60.0
) -> bool:
    """Verifica se in brain/ esiste una directory conversazione piu recente del transcript in cache."""
    try:
        cand_mtime = cand_tp.stat().st_mtime
        conv_dir = cand_tp.parents[2] if len(cand_tp.parents) >= 3 else cand_tp.parent
        brain_dir = conv_dir.parent
        if not brain_dir.exists():
            return False
        now = time.time()
        with os.scandir(brain_dir) as it:
            for entry in it:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name == conv_dir.name:
                    continue
                try:
                    st = entry.stat()
                    dir_ts = max(getattr(st, "st_ctime", 0.0), st.st_mtime)
                    if (now - dir_ts) <= recent_window_sec and dir_ts > cand_mtime:
                        return True
                except Exception:
                    continue
    except Exception:
        return False
    return False


def resolve_bound_transcript_path(self_obj: Any) -> Optional[Path]:
    """Risolve il percorso del transcript vincolato a explicit_transcript_path o conversation_id."""
    tp = self_obj.transcript_path or self_obj.explicit_transcript_path
    if tp is not None:
        return tp if tp.is_file() else None
    home_raw = os.environ.get("USERPROFILE", "").strip()
    home_dir = Path(home_raw) if home_raw else Path.home()
    brain_dir = home_dir / ".gemini" / "antigravity" / "brain"
    if self_obj.conversation_id and not self_obj.conversation_id.startswith("default_"):
        cand_tp = (
            brain_dir
            / self_obj.conversation_id
            / ".system_generated"
            / "logs"
            / "transcript.jsonl"
        )
        if cand_tp.is_file():
            return cand_tp
        return None
    hub_root = Path(_consts._get_facade_attr("HUB_ROOT", _consts.HUB_ROOT)).resolve()
    in_temp_brain = False
    try:
        brain_res = brain_dir.resolve()
        temp_bases = [Path(tempfile.gettempdir()).resolve()]
        env_hooks = os.environ.get("NK_HOOKS_TEMP_DIR", "").strip()
        if env_hooks:
            temp_bases.append(Path(env_hooks).resolve().parent)
        in_temp_brain = any(brain_res.is_relative_to(tb) for tb in temp_bases)
    except Exception:
        in_temp_brain = False
    if self_obj.repo_root.resolve() == hub_root or in_temp_brain:
        recent_tp = self_obj._find_recent_transcript(brain_dir, max_age_seconds=120.0)
        if recent_tp is not None and recent_tp.is_file():
            if not self_obj.conversation_id and len(recent_tp.parents) >= 3:
                cand_cid = recent_tp.parents[2].name
                if cand_cid and not cand_cid.startswith("default_"):
                    self_obj.conversation_id = cand_cid
            return recent_tp
    return None


def extract_user_prompt_from_line(line_bytes: bytes) -> Optional[str]:
    """Estrae il contenuto utente reale rimuovendo eventuali wrapper XML Antigravity."""
    line_s = line_bytes.strip()
    if not line_s or not line_s.startswith(b"{"):
        return None
    try:
        rec = json.loads(line_s.decode("utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(rec, dict):
        return None
    src = str(rec.get("source") or "").upper()
    rtype = str(rec.get("type") or "").upper()
    role = str(rec.get("role") or "").upper()
    is_real_user = (rtype == "USER_INPUT") or (
        rtype == "" and ("USER" in src or "USER" in role)
    )
    if not is_real_user:
        return None
    raw_val = rec.get("content") if rec.get("content") is not None else rec.get("text")
    if isinstance(raw_val, list):
        parts: List[str] = []
        for item in raw_val:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                txt = item.get("text") or item.get("content")
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt.strip())
        raw_content = "\n".join(parts).strip()
    else:
        raw_content = str(raw_val or "").strip()
    if not raw_content:
        return None
    cleaned = strip_antigravity_envelope(raw_content).strip()
    if cleaned.lstrip().startswith(("<CONTEXT_SUMMARY>", "# Resuming from a compaction")):
        return None
    return cleaned if cleaned else None


def detect_latest_user_prompt(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Estrae il prompt esplicito o l'ultimo USER_INPUT verificando prima stat e cache (BOOT-01)."""
    if self_obj.explicit_prompt is not None:
        stripped_explicit = strip_antigravity_envelope(str(self_obj.explicit_prompt)).strip()
        self_obj._last_detected_user_prompt = (
            stripped_explicit if stripped_explicit else None
        )
        return self_obj._last_detected_user_prompt

    tp = self_obj._resolve_bound_transcript_path()
    if tp is None:
        self_obj._last_detected_user_prompt = None
        return None

    try:
        t_stat = tp.stat()
        t_mtime = t_stat.st_mtime
        t_size = t_stat.st_size
    except OSError:
        self_obj._last_detected_user_prompt = None
        return None

    if (
        cached is not None
        and cached.get("last_transcript_path") == str(tp)
        and float(cached.get("transcript_mtime", -1.0)) == t_mtime
        and int(cached.get("transcript_size", -1)) == t_size
        and "cached_latest_user_prompt" in cached
    ):
        cached_prompt = cached.get("cached_latest_user_prompt")
        self_obj._last_detected_user_prompt = (
            str(cached_prompt) if isinstance(cached_prompt, str) else None
        )
        return self_obj._last_detected_user_prompt

    if t_size <= 0:
        self_obj._last_detected_user_prompt = None
        return None

    chunk_size = int(
        _consts._get_facade_attr("BINARY_CHUNK_SIZE", _consts.BINARY_CHUNK_SIZE)
    )
    try:
        with open(tp, "rb") as bf:
            offset = t_size
            carry = b""
            while offset > 0:
                read_len = min(chunk_size, offset)
                offset -= read_len
                bf.seek(offset)
                chunk = bf.read(read_len) + carry
                lines = chunk.splitlines()
                if offset > 0 and lines:
                    carry = lines[0]
                    scan_lines = lines[1:]
                else:
                    carry = b""
                    scan_lines = lines
                for raw_ln in reversed(scan_lines):
                    found = self_obj._extract_user_prompt_from_line(raw_ln)
                    if found is not None:
                        self_obj._last_detected_user_prompt = found
                        return found
            if carry:
                found = self_obj._extract_user_prompt_from_line(carry)
                if found is not None:
                    self_obj._last_detected_user_prompt = found
                    return found
    except Exception:
        self_obj._last_detected_user_prompt = None
        return None

    self_obj._last_detected_user_prompt = None
    return None


def resolve_onboarding_and_gate_mode(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> tuple[str, str]:
    """Emette ONBOARDING_BYPASS_VERIFIED solo su vero trigger utente verificato (BOOT-01)."""
    if self_obj._resolved_gate_tuple is not None:
        return self_obj._resolved_gate_tuple
    default_mode = (
        os.environ.get("NK_META_PROMPT_GATE_MODE", "CONFIRM").strip().upper()
    )
    if default_mode not in ("CONFIRM", "ECHO", "OFF"):
        default_mode = "CONFIRM"
    triggers = _consts._get_facade_attr(
        "ONBOARDING_TRIGGERS", _consts.ONBOARDING_TRIGGERS
    )
    user_prompt = self_obj._detect_latest_user_prompt(cached=cached)
    if user_prompt is not None:
        low_p = user_prompt.lower().strip()
        norm_p = re.sub(r"[^\w\s]|_", " ", low_p)
        norm_p = " ".join(norm_p.split())
        if norm_p in triggers:
            res = ("ONBOARDING_BYPASS_VERIFIED", "BYPASSED")
            self_obj._resolved_gate_tuple = res
            return res
        res = ("NONE", default_mode)
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


def find_recent_transcript(
    self_obj: Any, brain_dir: Path, max_age_seconds: float = 120.0
) -> Optional[Path]:
    """Individua il transcript attivo ordinando per transcript.stat().st_mtime entro 120s in fallback."""
    if (
        self_obj.explicit_transcript_path
        and self_obj.explicit_transcript_path.exists()
    ):
        return self_obj.explicit_transcript_path

    if not brain_dir.exists():
        return None

    if self_obj.conversation_id:
        conv_tp = (
            brain_dir
            / self_obj.conversation_id
            / ".system_generated"
            / "logs"
            / "transcript.jsonl"
        )
        return conv_tp if conv_tp.exists() else None

    try:
        now = time.time()
        fallback_window = min(float(max_age_seconds), 120.0)
        candidates: List[tuple[float, Path]] = []
        newest_unflushed_dir_ts: float = -1.0
        with os.scandir(brain_dir) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    cand = (
                        Path(entry.path)
                        / ".system_generated"
                        / "logs"
                        / "transcript.jsonl"
                    )
                    try:
                        if cand.exists():
                            cmtime = cand.stat().st_mtime
                            if (now - cmtime) <= fallback_window:
                                candidates.append((cmtime, cand))
                        else:
                            dst = entry.stat()
                            dir_ts = max(getattr(dst, "st_ctime", 0.0), dst.st_mtime)
                            if (
                                (now - dir_ts) <= fallback_window
                                and dir_ts > newest_unflushed_dir_ts
                            ):
                                newest_unflushed_dir_ts = dir_ts
                    except Exception:
                        continue
        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_file: Optional[Path] = None
        best_mtime: float = -1.0
        fallback_file: Optional[Path] = None
        fallback_mtime: float = -1.0
        for cmtime, cand in candidates[:8]:
            try:
                with open(cand, "rb") as f:
                    head_bytes = f.read(16384)
                if self_obj._is_subagent_transcript_head(head_bytes):
                    if cmtime > fallback_mtime:
                        fallback_mtime = cmtime
                        fallback_file = cand
                else:
                    if cmtime > best_mtime:
                        best_mtime = cmtime
                        best_file = cand
            except Exception:
                continue
        chosen_file = best_file or fallback_file
        chosen_mtime = best_mtime if best_file is not None else fallback_mtime
        if newest_unflushed_dir_ts > 0.0 and newest_unflushed_dir_ts > chosen_mtime:
            return None
        return chosen_file
    except Exception:
        return None

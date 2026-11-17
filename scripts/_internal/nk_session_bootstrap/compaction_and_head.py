#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analisi binaria post-compattazione, semaforo O(1) e rilevamento transcript sub-agente."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..nk_common import transcript_guards as _nk_guards
from .constants import (
    BINARY_CHUNK_SIZE,
    HIGH_CAPACITY_PROFILES,
    MAX_EXACT_COUNT_BYTES,
)


def _compute_fast_traffic_light(
    step_count: int,
    estimated_tokens: int,
    profile: str = "generation",
    actual_context_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Calcola lo stato semaforico in O(1) senza importare Pydantic su cold start."""
    active_prof = (profile or "generation").strip().lower()
    is_high_cap = active_prof in HIGH_CAPACITY_PROFILES
    green_steps = 150 if is_high_cap else 70
    red_steps = 250 if is_high_cap else 100
    green_tokens = 250000 if is_high_cap else 80000
    red_tokens = 500000 if is_high_cap else 120000

    safe_steps = (
        0
        if isinstance(step_count, bool) or not isinstance(step_count, int)
        else step_count
    )
    safe_est = (
        0
        if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int)
        else estimated_tokens
    )
    safe_actual = (
        actual_context_tokens
        if isinstance(actual_context_tokens, int)
        and not isinstance(actual_context_tokens, bool)
        else None
    )

    if safe_steps < green_steps and safe_est < green_tokens:
        status = "GREEN"
    elif safe_steps < red_steps and safe_est < red_tokens:
        status = "YELLOW"
    else:
        status = "RED"

    if is_high_cap and safe_actual is not None and safe_actual > 0:
        if safe_actual >= 200000:
            status = "RED"
        elif safe_actual >= 150000 and status != "RED":
            status = "WARN"

    return {
        "status": status,
        "step_count": safe_steps,
        "estimated_tokens": safe_est,
        "profile": active_prof,
    }


def _is_compaction_record_dict(rec: Dict[str, Any]) -> bool:
    """Rileva un vero checkpoint delegando alla guardia canonica TV-08 in nk_common."""
    return _nk_guards.is_verified_compaction(rec)


def is_subagent_transcript_head(head_bytes: bytes) -> bool:
    """Restituisce True se le prime 5 righe (step_index <= 2) identificano un sub-agente."""
    if not head_bytes:
        return False
    lines_seen = 0
    saw_user_turn = False
    fallback_nonjson: List[str] = []
    for raw_ln in head_bytes.splitlines():
        ln = raw_ln.strip()
        if not ln:
            continue
        lines_seen += 1
        if lines_seen > 5:
            break
        try:
            rec = json.loads(ln.decode("utf-8", errors="replace"))
        except Exception:
            fallback_nonjson.append(ln.decode("utf-8", errors="replace"))
            continue
        if not isinstance(rec, dict):
            continue
        step_idx = rec.get("step_index")
        if (
            isinstance(step_idx, int)
            and not isinstance(step_idx, bool)
            and step_idx > 2
        ):
            break
        src = str(rec.get("source", rec.get("role", ""))).strip().upper()
        text_dump = json.dumps(rec, ensure_ascii=False)
        if (
            "<Agent System Instructions>" in text_dump
            and "<subagent_reminder>" in text_dump
        ):
            return True
        if (
            "[Message]" in text_dump
            and "sender=" in text_dump
            and "<env_capsule>" in text_dump
        ):
            return True
        if src == "USER":
            saw_user_turn = True
            return False
        if not saw_user_turn and (
            src == "SYSTEM"
            or ("<SYSTEM_MESSAGE>" in text_dump and "[Message]" in text_dump)
            or ("[Message]" in text_dump and "sender=" in text_dump)
            or "<subagent_reminder>" in text_dump
        ):
            return True

    for text_head in fallback_nonjson:
        if (
            "<Agent System Instructions>" in text_head
            and "<subagent_reminder>" in text_head
        ):
            return True
        if '"source": "USER"' in text_head or '"source":"USER"' in text_head:
            return False
        if '"source": "SYSTEM"' in text_head or '"source":"SYSTEM"' in text_head:
            return True
        if (
            "[Message]" in text_head
            and "sender=" in text_head
            and "<env_capsule>" in text_head
        ):
            return True
    return False


def count_lines_binary_64kb(transcript_file: Path, t_size: int) -> int:
    """Conta in modo esatto le righe con blocchi binari da 64 KB per file sotto 50 MB."""
    if t_size <= 0:
        return 0
    lines = 0
    with open(transcript_file, "rb") as bf:
        if t_size <= MAX_EXACT_COUNT_BYTES:
            while True:
                chunk = bf.read(BINARY_CHUNK_SIZE)
                if not chunk:
                    break
                lines += chunk.count(b"\n")
            return max(1, lines)
        read_len = min(t_size, BINARY_CHUNK_SIZE)
        bf.seek(t_size - read_len)
        tail_chunk = bf.read(read_len)
        tail_lines = max(1, tail_chunk.count(b"\n"))
        return int(round((t_size / float(read_len)) * tail_lines))


def has_compaction_candidate_bytes(buf: bytes) -> bool:
    """Esegue un pre-filtro binario rapido delegando a nk_common.transcript_guards."""
    return _nk_guards.has_compaction_candidate_bytes(buf)


def is_compaction_line_bytes(raw_ln: bytes) -> bool:
    """Verifica se una riga JSON binaria rappresenta un vero checkpoint di compattazione."""
    line_s = raw_ln.strip()
    if not line_s.startswith(b"{") or not has_compaction_candidate_bytes(line_s):
        return False
    try:
        rec = json.loads(line_s.decode("utf-8", errors="replace"))
    except Exception:
        return False
    return isinstance(rec, dict) and _is_compaction_record_dict(rec)


def count_post_compaction_binary(
    transcript_file: Path, t_size: int
) -> tuple[int, int]:
    """Scansiona a ritroso da fine file in blocchi da 64 KB fermandosi all'ultimo checkpoint."""
    if t_size <= 0:
        return 0, 0
    steps = 0
    post_bytes = 0
    min_offset = max(0, t_size - MAX_EXACT_COUNT_BYTES)
    offset = t_size
    carry = b""
    with open(transcript_file, "rb") as bf:
        while offset > min_offset:
            read_len = min(BINARY_CHUNK_SIZE, offset - min_offset)
            offset -= read_len
            bf.seek(offset)
            chunk = bf.read(read_len) + carry
            parts = chunk.split(b"\n")
            if offset > min_offset:
                carry = parts[0]
                scan_lines = parts[1:]
            else:
                carry = b""
                scan_lines = parts
            for raw_ln in reversed(scan_lines):
                if not raw_ln.strip():
                    continue
                steps += 1
                post_bytes += len(raw_ln) + 1
                if is_compaction_line_bytes(raw_ln):
                    return max(1, steps), min(t_size, max(1, post_bytes))
        if carry.strip():
            steps += 1
            post_bytes += len(carry) + 1
            if is_compaction_line_bytes(carry):
                return max(1, steps), min(t_size, max(1, post_bytes))
    if min_offset > 0:
        est_steps = count_lines_binary_64kb(transcript_file, t_size)
        return max(1, est_steps), t_size
    return max(1, steps), min(t_size, max(1, post_bytes))

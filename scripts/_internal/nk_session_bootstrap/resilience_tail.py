#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analisi resilienza KV-Cache, burst RPC e messaggi di avviso semaforici."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .compaction_and_head import (
    _is_compaction_record_dict,
    is_subagent_transcript_head,
)
from .constants import (
    BINARY_CHUNK_SIZE,
    MAX_EXACT_COUNT_BYTES,
    _parse_iso_epoch,
    _valid_token_int,
)


def _extract_record_context_tokens(
    rec: Dict[str, Any],
) -> tuple[Optional[int], Optional[int], int]:
    """Estrae (input_tokens, cache_read_tokens, total_ctx) da Dual-Schema rigettando bool."""
    in_tok = _valid_token_int(rec.get("input_tokens"))
    cache_tok = _valid_token_int(rec.get("cache_read_tokens"))
    total_ctx = 0
    if in_tok is not None or cache_tok is not None:
        total_ctx = (in_tok or 0) + (cache_tok or 0)
    if total_ctx <= 0:
        for key in ("actual_context_tokens", "context_tokens", "prompt_tokens"):
            val = _valid_token_int(rec.get(key))
            if val is not None and val > 0:
                total_ctx = val
                break
    if total_ctx <= 0:
        for sub_key in ("metadata", "usage", "token_usage", "context_window"):
            sub = rec.get(sub_key)
            if isinstance(sub, dict):
                s_in = _valid_token_int(sub.get("input_tokens"))
                s_cache = _valid_token_int(sub.get("cache_read_tokens"))
                if s_in is not None or s_cache is not None:
                    sub_tot = (s_in or 0) + (s_cache or 0)
                    if sub_tot > 0:
                        if in_tok is None:
                            in_tok = s_in
                        if cache_tok is None:
                            cache_tok = s_cache
                        total_ctx = sub_tot
                        break
                for key in (
                    "actual_context_tokens",
                    "context_tokens",
                    "prompt_tokens",
                    "total_tokens",
                ):
                    val = _valid_token_int(sub.get(key))
                    if val is not None and val > 0:
                        total_ctx = val
                        break
                if total_ctx > 0:
                    break
    return in_tok, cache_tok, total_ctx


def _analyze_step_record_resilience(
    rec: Dict[str, Any],
) -> Dict[str, Any]:
    """Estrae timestamp, token reali, cold miss e burst di scrittura reale da un record."""
    src = str(rec.get("source") or "").strip().upper()
    rtype = str(rec.get("type") or "").strip().upper()
    role = str(rec.get("role") or "").strip().upper()

    is_user = (rtype == "USER_INPUT") or (
        rtype == "" and ("USER" in src or "USER" in role)
    )
    is_compaction = _is_compaction_record_dict(rec)

    ts = _parse_iso_epoch(rec.get("created_at") or rec.get("timestamp"))
    in_tok, cache_tok, total_ctx = _extract_record_context_tokens(rec)
    cold_miss = cache_tok == 0 and in_tok is not None and in_tok >= 50000

    is_model = (rtype in ("PLANNER_RESPONSE", "MODEL_RESPONSE")) or (
        rtype in ("", "MODEL")
        and (src in ("MODEL", "ASSISTANT") or role in ("MODEL", "ASSISTANT"))
    )
    write_cnt = 0
    if is_model:
        tool_calls = rec.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    t_name = (
                        str(
                            tc.get("name")
                            or tc.get("toolName")
                            or tc.get("tool_name")
                            or ""
                        )
                        .strip()
                        .strip('"')
                        .strip("'")
                    )
                    if t_name in ("write_file", "write_to_file"):
                        write_cnt += 1

    burst = write_cnt >= 3
    has_usage = (
        total_ctx > 0
        or (in_tok is not None and in_tok > 0)
        or (cache_tok is not None and cache_tok >= 0)
    )
    return {
        "is_user": is_user,
        "is_compaction": is_compaction,
        "ts": ts,
        "total_ctx": total_ctx,
        "has_usage": has_usage,
        "cold_miss": cold_miss,
        "burst": burst,
    }


def _inspect_tail_resilience_risks(
    transcript_file: Path,
    t_size: int = 0,
    est_tokens: int = 0,
    now_ts: Optional[float] = None,
) -> Dict[str, Any]:
    """Valuta kv_cache_cold_risk e rpc_stream_burst_risk con backscan 64 KB (<= 50 MB)."""
    cur_now = now_ts if now_ts is not None else time.time()
    tail_recs_rev: List[Dict[str, Any]] = []
    fallback_actual_ctx = 0
    tail_has_ctx = False
    saw_compaction_in_tail = False

    def _consume_rev_line(rline_bytes: bytes) -> bool:
        nonlocal fallback_actual_ctx, tail_has_ctx, saw_compaction_in_tail
        stripped = rline_bytes.strip()
        if not stripped.startswith(b"{"):
            return False
        try:
            rec = json.loads(stripped.decode("utf-8", errors="replace"))
        except Exception:
            return False
        if not isinstance(rec, dict):
            return False
        info = _analyze_step_record_resilience(rec)
        if len(tail_recs_rev) < 12:
            tail_recs_rev.append(info)
            if info.get("is_compaction"):
                saw_compaction_in_tail = True
            elif not saw_compaction_in_tail and int(info["total_ctx"]) > 0:
                tail_has_ctx = True
            return False
        if saw_compaction_in_tail or tail_has_ctx:
            return True
        if info.get("is_compaction"):
            return True
        if int(info["total_ctx"]) > 0:
            fallback_actual_ctx = int(info["total_ctx"])
            return True
        return False

    try:
        stat_res = transcript_file.stat()
        f_size = t_size if t_size > 0 else stat_res.st_size
        f_mtime = stat_res.st_mtime
        if f_size <= 0:
            return {
                "kv_cache_cold_risk": False,
                "rpc_stream_burst_risk": False,
                "idle_gap_seconds": 0.0,
                "effective_context_tokens": 0,
            }
        with open(transcript_file, "rb") as bf:
            head_len = min(f_size, 16384)
            head_bytes = bf.read(head_len)
            if is_subagent_transcript_head(head_bytes):
                return {
                    "kv_cache_cold_risk": False,
                    "rpc_stream_burst_risk": False,
                    "idle_gap_seconds": 0.0,
                    "effective_context_tokens": 0,
                }
            if f_size <= BINARY_CHUNK_SIZE:
                full_bytes = (
                    head_bytes
                    if f_size <= head_len
                    else head_bytes + bf.read(f_size - head_len)
                )
                for raw_ln in reversed(full_bytes.splitlines()):
                    if _consume_rev_line(raw_ln):
                        break
            else:
                min_offset = max(0, f_size - MAX_EXACT_COUNT_BYTES)
                offset = f_size
                carry = b""
                done = False
                while offset > min_offset and not done:
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
                        if _consume_rev_line(raw_ln):
                            done = True
                            break
                        if len(tail_recs_rev) >= 12 and (
                            tail_has_ctx
                            or saw_compaction_in_tail
                            or fallback_actual_ctx > 0
                        ):
                            done = True
                            break
                if not done and carry.strip():
                    _consume_rev_line(carry)
    except Exception:
        return {
            "kv_cache_cold_risk": False,
            "rpc_stream_burst_risk": False,
            "idle_gap_seconds": 0.0,
        }

    last_ts = 0.0
    prev_ts = 0.0
    max_user_gap = 0.0
    actual_ctx = 0
    last_cold_miss = False
    burst_risk = False
    just_compacted = False
    compacted_final = False

    for info in reversed(tail_recs_rev):
        if info.get("is_compaction"):
            burst_risk = False
            last_cold_miss = False
            max_user_gap = 0.0
            actual_ctx = 0
            just_compacted = True
            compacted_final = True
            if info["ts"] > 0:
                prev_ts = info["ts"]
                last_ts = info["ts"]
            continue
        if info["ts"] > 0:
            if info["is_user"] and prev_ts > 0:
                max_user_gap = max(max_user_gap, info["ts"] - prev_ts)
            prev_ts = info["ts"]
            last_ts = info["ts"]
        if int(info["total_ctx"]) > 0:
            actual_ctx = int(info["total_ctx"])
        if info["has_usage"]:
            last_cold_miss = False if just_compacted else bool(info["cold_miss"])
            just_compacted = False
        if info["burst"]:
            burst_risk = True

    if actual_ctx == 0 and not compacted_final and fallback_actual_ctx > 0:
        actual_ctx = fallback_actual_ctx

    ref_last_ts = last_ts if last_ts > 0 else f_mtime
    idle_gap_s = max(0.0, cur_now - ref_last_ts, max_user_gap)
    effective_size_tokens = actual_ctx if actual_ctx > 0 else est_tokens
    kv_cold = bool(
        last_cold_miss or (effective_size_tokens >= 50000 and idle_gap_s > 240.0)
    )
    return {
        "kv_cache_cold_risk": kv_cold,
        "rpc_stream_burst_risk": burst_risk,
        "idle_gap_seconds": round(idle_gap_s, 2),
        "effective_context_tokens": actual_ctx,
    }


def _build_context_warning(
    status: str, step_count: int, est_tokens: int, res: Dict[str, Any]
) -> Optional[str]:
    """Costruisce il messaggio di avviso semaforico o di resilienza KV-Cache e RPC."""
    if status == "YELLOW":
        return (
            f"Context warning: session at {step_count} steps "
            f"(~{est_tokens:,} tokens)."
        )
    if status == "WARN":
        eff_tok = _valid_token_int(res.get("effective_context_tokens"))
        tok_val = eff_tok if eff_tok and eff_tok > 0 else est_tokens
        return (
            f"Context advisory (WARN): session at {step_count} steps "
            f"(~{tok_val:,} tokens). Delegate heavy tasks or prepare /compact."
        )
    if status == "RED":
        return (
            f"CRITICAL context saturation: session at {step_count} steps. "
            "Execute /compact or nk_session_handoff.py."
        )
    if res.get("kv_cache_cold_risk") or res.get("rpc_stream_burst_risk"):
        return (
            "Advisory: KV-Cache cold risk or RPC burst detected. "
            "Batch <= 2 write_file per step or run /compact."
        )
    return None

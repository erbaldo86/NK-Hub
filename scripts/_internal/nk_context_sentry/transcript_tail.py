# -*- coding: utf-8 -*-
"""Analisi transcript, backscan compattazione e rischi tail per nk_context_sentry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.nk_context_sentry.thresholds_proxy import (
    COMPACTION_SUMMARY_MARKER,
    CONTEXT_BACKSCAN_CHUNK_BYTES,
    CONTEXT_MAX_SCAN_BYTES,
    HIGH_CAPACITY_PROFILES,
    _contains_compaction_marker,
    has_compaction_candidate_bytes,
)

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^\)]+\)")
_CODE_SPAN_RE = re.compile(r"`[^`]+`")
_MD_PUNCT_RE = re.compile(r"[\|\-\*\#\>\_\~]+")
_MULTI_WS_RE = re.compile(r"\s+")


def _get_transcript_tools() -> Any:
    """Importa nk_transcript_tools al bisogno evitando cicli all'import."""
    try:
        import nk_transcript_tools as _tt
        return _tt
    except ImportError:
        from scripts import nk_transcript_tools as _tt  # type: ignore[no-redef]
        return _tt


def find_last_compaction_offset_impl(transcript_path: Path) -> int:
    """Esegue un backscan a chunk da 64 KB (<= 50 MB) per l'ultimo checkpoint."""
    try:
        with open(transcript_path, "rb") as bf:
            bf.seek(0, 2)
            file_size = bf.tell()
            if file_size <= 0:
                return 0
            min_offset = max(0, file_size - CONTEXT_MAX_SCAN_BYTES)
            end = file_size
            carry = b""
            fallback_start = 0
            while end > min_offset:
                start = max(min_offset, end - CONTEXT_BACKSCAN_CHUNK_BYTES)
                bf.seek(start)
                raw = bf.read(end - start)
                buf = raw + carry
                if start > 0:
                    first_nl = buf.find(b"\n")
                    if first_nl == -1:
                        if start <= min_offset:
                            fallback_start = start
                            break
                        carry = buf
                        end = start
                        continue
                    carry = buf[: first_nl + 1]
                    scan_slice = buf[first_nl + 1 :]
                    slice_base = start + first_nl + 1
                else:
                    carry = b""
                    scan_slice = buf
                    slice_base = 0

                pos = len(scan_slice)
                while pos > 0:
                    nl = scan_slice.rfind(b"\n", 0, pos)
                    line_start = (nl + 1) if nl != -1 else 0
                    raw_line = scan_slice[line_start:pos].rstrip(b"\r\n")
                    if raw_line and has_compaction_candidate_bytes(raw_line):
                        line_str = raw_line.decode("utf-8", errors="replace").strip()
                        try:
                            data = json.loads(line_str)
                            if isinstance(data, dict) and _contains_compaction_marker(
                                line_str, data
                            ):
                                return slice_base + line_start
                        except Exception:
                            pass
                    pos = nl if nl != -1 else 0

                if start <= min_offset:
                    fallback_start = slice_base if min_offset > 0 else 0
                    break
                end = start
            return fallback_start
    except Exception:
        return 0


def compute_tail_resilience_flags_impl(
    transcript_path: Path,
    estimated_tokens: int,
    actual_tokens: Optional[int],
) -> Dict[str, Any]:
    """Calcola kv_cache_cold_risk e rpc_stream_burst_risk sulla coda."""
    try:
        from nk_session_bootstrap import _inspect_tail_resilience_risks
    except ImportError:
        try:
            from scripts.nk_session_bootstrap import _inspect_tail_resilience_risks
        except ImportError:
            return {
                "kv_cache_cold_risk": False,
                "rpc_stream_burst_risk": False,
                "idle_gap_seconds": 0.0,
            }
    safe_actual = (
        actual_tokens
        if isinstance(actual_tokens, int) and not isinstance(actual_tokens, bool)
        else 0
    )
    eff_est = max(0, safe_actual) if safe_actual > 0 else estimated_tokens
    return _inspect_tail_resilience_risks(transcript_path, est_tokens=eff_est)


def analyze_transcript_impl(
    sentry: Any,
    transcript_path: Path,
    profile: Optional[str] = None,
    actual_context_tokens: Optional[int] = None,
    preloaded_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Analizza transcript.jsonl in Dual-Schema dall'ultimo <CONTEXT_SUMMARY>."""
    transcript_path = Path(transcript_path).resolve()
    active_profile = (profile or sentry.profile or "standard").lower().strip()
    if isinstance(actual_context_tokens, bool) or not isinstance(
        actual_context_tokens, int
    ):
        actual_context_tokens = None
    elif actual_context_tokens < 0:
        actual_context_tokens = 0

    if not transcript_path.exists():
        return {
            "status": "ERROR",
            "details": f"Transcript file not found: {transcript_path}",
            "step_count": 0,
            "estimated_tokens": 0,
        }

    tt = _get_transcript_tools()
    steps_count = 0
    non_empty_lines = 0
    total_chars = 0
    detected_actual_tokens: Optional[int] = actual_context_tokens
    chars_by_source: Dict[str, int] = {}
    tool_counts: Dict[str, int] = {}
    swarm_hygiene_violations: List[Dict[str, Any]] = []
    swarm_mss_warnings: List[Dict[str, Any]] = []
    consecutive_direct_audit_tools = 0
    max_consecutive_direct_audit = 0
    blind_read_errors = 0
    write_burst_steps = 0
    pending_tool_calls: List[Dict[str, Any]] = []

    def _iter_entries():
        nonlocal non_empty_lines
        if preloaded_records is not None:
            for rec in preloaded_records:
                non_empty_lines += 1
                if isinstance(rec, dict):
                    yield "", rec
            return
        start_offset = sentry._find_last_compaction_offset(transcript_path)
        with open(transcript_path, "rb") as f:
            if start_offset > 0:
                f.seek(start_offset)
            for raw_line in f:
                line_txt = raw_line.decode("utf-8", errors="replace").strip()
                if not line_txt:
                    continue
                non_empty_lines += 1
                try:
                    parsed = json.loads(line_txt)
                    if isinstance(parsed, dict):
                        yield line_txt, parsed
                except Exception:
                    continue

    for line, data in _iter_entries():
        is_compaction_checkpoint = _contains_compaction_marker(line, data)
        if is_compaction_checkpoint:
            steps_count = 0
            total_chars = 0
            detected_actual_tokens = actual_context_tokens
            chars_by_source.clear()
            tool_counts.clear()
            swarm_hygiene_violations.clear()
            swarm_mss_warnings.clear()
            consecutive_direct_audit_tools = 0
            max_consecutive_direct_audit = 0
            blind_read_errors = 0
            write_burst_steps = 0
            pending_tool_calls.clear()

        steps_count += 1
        source = str(data.get("source", "UNKNOWN") or "UNKNOWN")
        cat = tt.classify_transcript_record(data)
        content = str(data.get("content", "") or "")
        thinking = str(data.get("thinking", "") or "")

        if not is_compaction_checkpoint:
            rec_actual = sentry._extract_actual_tokens_from_record(data)
            if rec_actual is not None:
                detected_actual_tokens = rec_actual

        step_chars = (
            len(content)
            if active_profile in HIGH_CAPACITY_PROFILES
            else len(content) + len(thinking)
        )
        total_chars += step_chars
        chars_by_source[source] = chars_by_source.get(source, 0) + step_chars

        is_background = sentry.is_background_task_message(data, content)
        is_initial_subagent = steps_count == 1 and (
            "### Blocco 1" in content
            or "BLOCCO 1" in content
            or (data.get("step_index") == 0 and "sender=" in content)
        )
        has_hook_marker = "[Message]" not in content and (
            "injected by a " in content
            or "hook:" in content
            or any(
                tok in content
                for tok in (
                    "[RULE-",
                    "[ACS-",
                    "[NK-HUB]",
                    "PreInvocation",
                    "PostInvocation",
                    "SessionStart",
                    "PreToolUse",
                    "PostToolUse",
                )
            )
        )
        has_swarm_sender = "[Message]" in content or (
            "<SYSTEM_MESSAGE>" in content
            and (
                "sender=" in content
                or bool(data.get("sender") or data.get("sender_id"))
            )
        )
        if (
            not is_background
            and not is_initial_subagent
            and not is_compaction_checkpoint
            and not has_hook_marker
            and COMPACTION_SUMMARY_MARKER not in content
            and cat == "SYSTEM"
            and has_swarm_sender
        ):
            raw_msgs = (
                content.split("[Message]")[1:]
                if "[Message]" in content
                else [content]
            )
            for msg_chunk in raw_msgs:
                net_body = msg_chunk.split("content=", 1)[1] if "content=" in msg_chunk else msg_chunk
                net_body = net_body.split("</SYSTEM_MESSAGE>")[0]
                net_body = net_body.replace("<passive_data_context>", "").replace(
                    "</passive_data_context>", ""
                )
                net_body = _MD_LINK_RE.sub(r"\1", net_body)
                net_body = _CODE_SPAN_RE.sub("T", net_body)
                net_body = _MD_PUNCT_RE.sub("", net_body)
                msg_len = len(_MULTI_WS_RE.sub(" ", net_body).strip())
                if msg_len > sentry.SWARM_MSG_MSS_CAP:
                    swarm_mss_warnings.append(
                        {
                            "step_index": data.get("step_index", steps_count),
                            "length": msg_len,
                            "limit": sentry.SWARM_MSG_MSS_CAP,
                        }
                    )
                if msg_len > sentry.SWARM_MSG_HARD_CAP:
                    swarm_hygiene_violations.append(
                        {
                            "step_index": data.get("step_index", steps_count),
                            "length": msg_len,
                            "limit": sentry.SWARM_MSG_HARD_CAP,
                        }
                    )

        tool_calls = data.get("tool_calls", []) or []
        if cat in ("USER", "SYSTEM"):
            pending_tool_calls.clear()

        if cat == "TOOL" and not tool_calls:
            corr_call = pending_tool_calls.pop(0) if pending_tool_calls else {}
            if tt.extract_tool_name(corr_call) in tt.READ_FILE_TOOLS:
                if tt._has_missing_path_error(str(data.get("status") or ""), content):
                    blind_read_errors += 1
            continue

        pending_tool_calls = list(tool_calls) if tool_calls else []
        b_err, w_burst = tt._inspect_record_blind_reads_and_bursts(data, tool_calls)
        blind_read_errors += b_err
        write_burst_steps += w_burst

        has_subagent_call = False
        has_direct_tool = False
        for tc in tool_calls:
            tname = tt.extract_tool_name(tc)
            if tname:
                tool_counts[tname] = tool_counts.get(tname, 0) + 1
            if tname in tt.DELEGATION_TOOLS:
                has_subagent_call = True
            elif tname in tt.DIRECT_TOOLS:
                has_direct_tool = True

        if has_subagent_call or (tt.is_user_turn_record(data) and steps_count > 1):
            consecutive_direct_audit_tools = 0
        elif has_direct_tool:
            consecutive_direct_audit_tools += 1
            if consecutive_direct_audit_tools > max_consecutive_direct_audit:
                max_consecutive_direct_audit = consecutive_direct_audit_tools

    estimated_tokens = max(1, total_chars // 4) if total_chars > 0 else 0
    health = sentry.get_traffic_light_status(
        steps_count,
        estimated_tokens,
        profile=active_profile,
        actual_context_tokens=detected_actual_tokens,
    )
    if non_empty_lines > 0 and steps_count == 0:
        health["status"] = "ERROR"
        health["recommendation"] = (
            "Corrupted transcript: 0 valid JSON records found in non-empty file."
        )

    report: Dict[str, Any] = {
        "status": health["status"],
        "profile": active_profile,
        "step_count": steps_count,
        "total_chars": total_chars,
        "estimated_tokens": estimated_tokens,
        "actual_context_tokens": detected_actual_tokens,
        "recommendation": health["recommendation"],
        "chars_by_source": chars_by_source,
        "tool_counts": tool_counts,
        "max_consecutive_direct_audit": max_consecutive_direct_audit,
        "blind_read_errors": blind_read_errors,
        "write_burst_steps": write_burst_steps,
        "swarm_mss_cap": sentry.SWARM_MSG_MSS_CAP,
        "swarm_mss_warnings_count": len(swarm_mss_warnings),
        "swarm_mss_warnings": swarm_mss_warnings[:5],
        "swarm_hygiene_violations_count": len(swarm_hygiene_violations),
        "swarm_hygiene_violations": swarm_hygiene_violations[:5],
    }
    report.update(
        sentry._compute_tail_resilience_flags(
            transcript_path, estimated_tokens, detected_actual_tokens
        )
    )
    return report

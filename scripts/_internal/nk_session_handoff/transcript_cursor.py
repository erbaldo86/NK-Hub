# -*- coding: utf-8 -*-
"""Cursore incrementale, backscan O(1) RAM e telemetria scalare v2 per nk_session_handoff."""

from __future__ import annotations

import collections
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.transcript_guards import (
    extract_actual_tokens_from_record, is_verified_compaction, valid_token_int,
)
from _internal.nk_session_handoff.constants import (
    _CURSOR_LOCK, _TRANSCRIPT_BACKSCAN_CHUNK_BYTES,
    _TRANSCRIPT_BACKSCAN_MAX_BYTES, _TRANSCRIPT_CURSOR_CACHE,
)


def _format_safe_capsule_lines(raw_lines: List[str], max_chars: int = 2400) -> str:
    """Formatta le ultime righe del trascritto senza troncare JSON a meta."""
    safe_rows: List[str] = []
    used_chars = 0
    for raw_ln in reversed(raw_lines):
        if not (stripped := raw_ln.strip()):
            continue
        compact_ln = stripped
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                summary_obj = {k: obj[k] for k in ("step_index", "step", "source", "type", "status", "created_at") if k in obj}
                if "content" in obj and isinstance(obj["content"], str):
                    clean_c = obj["content"].replace("\r", " ").replace("\n", " ").strip()
                    summary_obj["content"] = clean_c[:160] + "..." if len(clean_c) > 160 else clean_c
                compact_ln = json.dumps(summary_obj or obj, ensure_ascii=False)
        except Exception:
            if len(compact_ln) > 200:
                compact_ln = json.dumps({"raw_excerpt": compact_ln[:160] + "..."}, ensure_ascii=False)
        if used_chars + len(compact_ln) + 1 > max_chars:
            break
        safe_rows.append(compact_ln)
        used_chars += len(compact_ln) + 1
    safe_rows.reverse()
    return "\n".join(safe_rows) if safe_rows else "{}"


def _coerce_non_bool_int(value: Any) -> Optional[int]:
    """Delega la validazione intera non negativa a nk_common.transcript_guards."""
    return valid_token_int(value)


def _extract_actual_tokens_from_record(parsed: Dict[str, Any]) -> Optional[int]:
    """Delega l'estrazione token transcript a nk_common.transcript_guards."""
    return extract_actual_tokens_from_record(parsed)


def _is_compaction_checkpoint_record(stripped: str, parsed: Dict[str, Any]) -> bool:
    """Rileva checkpoint genuini bloccando spoofing source/role."""
    _ = stripped
    return is_verified_compaction(parsed)


def _format_scalar_ts(raw_ts: Any) -> str:
    """Converte un timestamp numerico o stringa in ISO-8601 compatto."""
    if raw_ts is None or isinstance(raw_ts, bool):
        return ""
    if isinstance(raw_ts, (int, float)):
        sec = float(raw_ts) / (1e9 if raw_ts >= 1e15 else (1e3 if raw_ts >= 1e12 else 1.0))
        try:
            return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat() if sec > 0 else ""
        except Exception:
            return ""
    return str(raw_ts).strip()[:64] if isinstance(raw_ts, str) else ""


def _eval_transcript_line_full(raw_bytes: bytes) -> Tuple[str, bool, Optional[int], str]:
    """Decodifica una riga JSONL verificando checkpoint, tokens e timestamp utente."""
    stripped = raw_bytes.decode("utf-8", errors="replace").strip()
    if not stripped:
        return "", False, None, ""
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                is_cp = _is_compaction_checkpoint_record(stripped, parsed)
                tok = _extract_actual_tokens_from_record(parsed)
                src, typ, role = str(parsed.get("source") or "").strip().upper(), str(parsed.get("type") or "").strip().upper(), str(parsed.get("role") or "").strip().lower()
                u_ts = _format_scalar_ts(parsed.get("timestamp_ns") or parsed.get("created_at_ns") or parsed.get("created_at") or parsed.get("timestamp") or parsed.get("ts")) if (src in ("USER", "USER_EXPLICIT") or typ == "USER_INPUT" or role == "user") else ""
                return stripped, is_cp, tok, u_ts
        except Exception:
            pass
    return stripped, False, None, ""


def _eval_transcript_line(raw_bytes: bytes) -> Tuple[str, bool, Optional[int]]:
    """Decodifica una riga JSONL verificando compaction checkpoint e tokens."""
    stripped, is_cp, tok, _ = _eval_transcript_line_full(raw_bytes)
    return stripped, is_cp, tok


def _scan_transcript_core(
    transcript_path: str, *, count_all_compactions: bool = False
) -> Tuple[int, int, str, Optional[int], int, str]:
    """Scansiona il transcript in singola passata O(1) RAM con cache incrementale protetta."""
    if not transcript_path or not (tp := Path(transcript_path)).is_file():
        return 0, 0, "", None, 0, ""
    try:
        f_size = tp.stat().st_size
        if f_size <= 0:
            return 0, 0, "{}", None, 0, ""
        cache_key = str(tp.resolve())
        with open(tp, "rb") as bf:
            head_sha256 = hashlib.sha256(bf.read(min(f_size, 512))).hexdigest()
            with _CURSOR_LOCK:
                raw_prev = _TRANSCRIPT_CURSOR_CACHE.get(cache_key)
                prev = dict(raw_prev) if isinstance(raw_prev, dict) else None
            can_resume = (
                prev is not None and f_size >= int(prev.get("file_size", 0))
                and f_size >= int(prev.get("byte_offset", 0)) and head_sha256 == prev.get("head_sha256")
                and (f_size - int(prev.get("byte_offset", 0))) <= _TRANSCRIPT_BACKSCAN_MAX_BYTES
                and (not count_all_compactions or bool(prev.get("full_backscan_done", False)))
            )
            if can_resume and prev is not None:
                if f_size == int(prev.get("file_size", -1)):
                    cached_full = prev.get("cached_full")
                    if isinstance(cached_full, tuple) and len(cached_full) == 6:
                        return cached_full
                prev_offset = int(prev["byte_offset"])
                bf.seek(prev_offset)
                delta = bf.read(f_size - prev_offset)
                last_nl = delta.rfind(b"\n")
                committed_part = delta[: last_nl + 1] if last_nl != -1 else b""
                pending_part = delta[last_nl + 1 :] if last_nl != -1 else delta
                c_steps, c_bytes, c_tail, c_tokens = int(prev["c_steps"]), int(prev["c_bytes"]), list(prev["c_tail"]), prev.get("c_tokens")
                c_comp, c_user_ts = int(prev.get("c_compactions", 0)), str(prev.get("c_last_user_ts", ""))
                new_offset = prev_offset + (last_nl + 1 if last_nl != -1 else 0)
                if committed_part:
                    for raw_ln in committed_part.split(b"\n")[:-1]:
                        c_bytes += len(raw_ln) + 1
                        stripped, is_cp, tok, u_ts = _eval_transcript_line_full(raw_ln)
                        if not stripped:
                            continue
                        if u_ts:
                            c_user_ts = u_ts
                        if is_cp:
                            c_comp += 1
                            c_steps, c_bytes, c_tail, c_tokens = 1, len(raw_ln) + 1, [stripped], tok
                        else:
                            c_steps += 1
                            c_tail = (c_tail + [stripped])[-10:]
                            if tok is not None:
                                c_tokens = tok
                out_steps, out_bytes, out_tail, out_tokens, out_comp, out_user_ts = c_steps, c_bytes, list(c_tail), c_tokens, c_comp, c_user_ts
                if pending_part:
                    out_bytes += len(pending_part)
                    p_stripped, p_cp, p_tok, p_uts = _eval_transcript_line_full(pending_part)
                    if p_stripped:
                        if p_uts:
                            out_user_ts = p_uts
                        if p_cp:
                            out_comp += 1
                            out_steps, out_bytes, out_tail, out_tokens = 1, len(pending_part), [p_stripped], p_tok
                        else:
                            out_steps += 1
                            out_tail = (out_tail + [p_stripped])[-10:]
                            if p_tok is not None:
                                out_tokens = p_tok
                res_full: Tuple[int, int, str, Optional[int], int, str] = (out_steps, max(0, out_bytes), _format_safe_capsule_lines(out_tail[-10:], max_chars=2400), out_tokens, out_comp, out_user_ts)
                with _CURSOR_LOCK:
                    _TRANSCRIPT_CURSOR_CACHE[cache_key] = {
                        "file_size": f_size, "byte_offset": new_offset, "head_sha256": head_sha256,
                        "c_steps": c_steps, "c_bytes": c_bytes, "c_tail": c_tail, "c_tokens": c_tokens,
                        "c_compactions": c_comp, "c_last_user_ts": c_user_ts,
                        "full_backscan_done": bool(prev.get("full_backscan_done", False)), "cached_result": res_full[:4], "cached_full": res_full,
                    }
                return res_full

            pos, bytes_scanned, carry = f_size, 0, b""
            collected_rev: collections.deque[str] = collections.deque(maxlen=10)
            steps_count, post_bytes, hit_checkpoint, comp_count = 0, 0, False, 0
            last_actual_tokens: Optional[int] = None
            last_user_ts, last_nl_offset = "", None
            while pos > 0 and bytes_scanned < _TRANSCRIPT_BACKSCAN_MAX_BYTES and (count_all_compactions or not hit_checkpoint):
                read_size = min(_TRANSCRIPT_BACKSCAN_CHUNK_BYTES, pos, _TRANSCRIPT_BACKSCAN_MAX_BYTES - bytes_scanned)
                new_start = pos - read_size
                bf.seek(new_start)
                chunk = bf.read(read_size)
                if last_nl_offset is None and (nl_idx := chunk.rfind(b"\n")) != -1:
                    last_nl_offset = new_start + nl_idx + 1
                buf, pos, bytes_scanned = chunk + carry, new_start, bytes_scanned + read_size
                parts = buf.split(b"\n")
                carry = parts[0]
                for raw_ln in reversed(parts[1:]):
                    if not hit_checkpoint:
                        post_bytes += len(raw_ln) + 1
                    stripped, is_cp, tok, u_ts = _eval_transcript_line_full(raw_ln)
                    if not stripped:
                        continue
                    if not last_user_ts and u_ts:
                        last_user_ts = u_ts
                    if is_cp:
                        comp_count += 1
                    if not hit_checkpoint:
                        if last_actual_tokens is None and tok is not None:
                            last_actual_tokens = tok
                        steps_count += 1
                        if len(collected_rev) < 10:
                            collected_rev.appendleft(stripped)
                        if is_cp:
                            hit_checkpoint = True
                            if not count_all_compactions:
                                break
            if carry and pos == 0 and (count_all_compactions or not hit_checkpoint):
                if not hit_checkpoint:
                    post_bytes += len(carry)
                stripped, is_cp, tok, u_ts = _eval_transcript_line_full(carry)
                if stripped:
                    if not last_user_ts and u_ts:
                        last_user_ts = u_ts
                    if is_cp:
                        comp_count += 1
                    if not hit_checkpoint:
                        if last_actual_tokens is None and tok is not None:
                            last_actual_tokens = tok
                        steps_count += 1
                        if len(collected_rev) < 10:
                            collected_rev.appendleft(stripped)
                        if is_cp:
                            hit_checkpoint = True
            tail_lines, steps = list(collected_rev), steps_count
            total_chars = max(1, min(f_size, post_bytes)) if hit_checkpoint else f_size
            res_full = (steps, total_chars, _format_safe_capsule_lines(tail_lines, max_chars=2400), last_actual_tokens, comp_count, last_user_ts)
            committed_offset = last_nl_offset if last_nl_offset is not None else 0
            if committed_offset == f_size:
                c_steps_val, c_bytes_val, c_tail_val, c_tokens_val, c_comp_val = steps, total_chars, tail_lines, last_actual_tokens, comp_count
            elif committed_offset == 0:
                c_steps_val, c_bytes_val, c_tail_val, c_tokens_val, c_comp_val = 0, 0, [], None, 0
            else:
                bf.seek(committed_offset)
                frag_raw = bf.read(f_size - committed_offset)
                f_stripped, f_cp, _, _ = _eval_transcript_line_full(frag_raw)
                c_comp_val = max(0, comp_count - (1 if f_cp else 0))
                if f_cp or not f_stripped or steps <= 0:
                    c_steps_val, c_bytes_val, c_tail_val, c_tokens_val = steps, total_chars, tail_lines, last_actual_tokens
                else:
                    c_steps_val, c_bytes_val, c_tail_val, c_tokens_val = max(0, steps - 1), max(0, total_chars - len(frag_raw)), tail_lines[:-1], last_actual_tokens
            with _CURSOR_LOCK:
                if len(_TRANSCRIPT_CURSOR_CACHE) > 32:
                    _TRANSCRIPT_CURSOR_CACHE.clear()
                _TRANSCRIPT_CURSOR_CACHE[cache_key] = {
                    "file_size": f_size, "byte_offset": committed_offset, "head_sha256": head_sha256,
                    "c_steps": c_steps_val, "c_bytes": c_bytes_val, "c_tail": c_tail_val, "c_tokens": c_tokens_val,
                    "c_compactions": c_comp_val, "c_last_user_ts": last_user_ts if committed_offset > 0 else "",
                    "full_backscan_done": bool(count_all_compactions or not hit_checkpoint), "cached_result": res_full[:4], "cached_full": res_full,
                }
            return res_full
    except Exception:
        return 0, 0, "", None, 0, ""


def _inspect_transcript_fast(transcript_path: str) -> Tuple[int, int, str, Optional[int]]:
    """Estrae step, caratteri, capsula e actual_tokens con backscan 64KB e deque O(1)."""
    return _scan_transcript_core(transcript_path, count_all_compactions=False)[:4]


def _read_transcript_summary_fast(transcript_path: str) -> Tuple[int, int, str]:
    """Estrae rapidamente step, caratteri totali e capsula finale."""
    steps, total_chars, capsule, _ = _inspect_transcript_fast(transcript_path)
    return steps, total_chars, capsule


def extract_transcript_telemetry_v2(transcript_path: Optional[Path], fallback_cid: str = "") -> Dict[str, Any]:
    """Estrae solo metriche scalari dal trascritto in una singola passata O(1) RAM."""
    _ = fallback_cid
    zero_res = {"steps": 0, "tokens": 0, "actual_tokens": 0, "estimated_tokens": 0, "steps_tail_window": 0, "compaction_count": 0, "last_user_timestamp": ""}
    if transcript_path is None or not (tp := Path(transcript_path)).is_file():
        return zero_res
    steps, total_chars, _, actual_tok, compaction_count, last_user_ts = _scan_transcript_core(str(tp), count_all_compactions=True)
    est_tok = max(1, total_chars // 4) if total_chars > 0 else 0
    safe_actual = int(actual_tok) if (actual_tok is not None and actual_tok >= 0) else 0
    return {
        "steps": int(steps), "tokens": safe_actual if safe_actual > 0 else est_tok, "actual_tokens": safe_actual,
        "estimated_tokens": est_tok, "steps_tail_window": min(int(steps), 10),
        "compaction_count": compaction_count, "last_user_timestamp": last_user_ts,
    }

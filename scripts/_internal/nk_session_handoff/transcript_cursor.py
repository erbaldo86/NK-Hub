# -*- coding: utf-8 -*-
"""Cursore incrementale e backscan 64KB per nk_session_handoff."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.transcript_guards import (
    extract_actual_tokens_from_record,
    is_verified_compaction,
    valid_token_int,
)
from _internal.nk_session_handoff.constants import (
    _TRANSCRIPT_BACKSCAN_CHUNK_BYTES,
    _TRANSCRIPT_BACKSCAN_MAX_BYTES,
    _TRANSCRIPT_CURSOR_CACHE,
)


def _format_safe_capsule_lines(raw_lines: List[str], max_chars: int = 2400) -> str:
    """Formatta le ultime righe del trascritto senza troncare JSON a meta."""
    safe_rows: List[str] = []
    used_chars = 0
    for raw_ln in reversed(raw_lines):
        stripped = raw_ln.strip()
        if not stripped:
            continue
        compact_ln = stripped
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                summary_obj = {
                    k: obj[k]
                    for k in ("step_index", "step", "source", "type", "status", "created_at")
                    if k in obj
                }
                if "content" in obj and isinstance(obj["content"], str):
                    clean_c = obj["content"].replace("\r", " ").replace("\n", " ").strip()
                    summary_obj["content"] = clean_c[:160] + "..." if len(clean_c) > 160 else clean_c
                if not summary_obj:
                    summary_obj = obj
                compact_ln = json.dumps(summary_obj, ensure_ascii=False)
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


def _eval_transcript_line(raw_bytes: bytes) -> Tuple[str, bool, Optional[int]]:
    """Decodifica una riga JSONL verificando compaction checkpoint e tokens."""
    stripped = raw_bytes.decode("utf-8", errors="replace").strip()
    if not stripped:
        return "", False, None
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                tok = _extract_actual_tokens_from_record(parsed)
                is_cp = _is_compaction_checkpoint_record(stripped, parsed)
                return stripped, is_cp, tok
        except Exception:
            pass
    return stripped, False, None


def _inspect_transcript_fast(transcript_path: str) -> Tuple[int, int, str, Optional[int]]:
    """Estrae step, caratteri, capsula e actual_tokens con backscan 64KB."""
    if not transcript_path:
        return 0, 0, "", None
    tp = Path(transcript_path)
    if not tp.is_file():
        return 0, 0, "", None
    try:
        f_size = tp.stat().st_size
        if f_size <= 0:
            return 0, 0, "{}", None

        cache_key = str(tp.resolve())
        with open(tp, "rb") as bf:
            head_sha256 = hashlib.sha256(bf.read(min(f_size, 512))).hexdigest()
            prev = _TRANSCRIPT_CURSOR_CACHE.get(cache_key)
            can_resume = (
                prev is not None
                and f_size >= int(prev.get("file_size", 0))
                and f_size >= int(prev.get("byte_offset", 0))
                and head_sha256 == prev.get("head_sha256")
                and (f_size - int(prev.get("byte_offset", 0))) <= _TRANSCRIPT_BACKSCAN_MAX_BYTES
            )

            if can_resume and prev is not None:
                if f_size == int(prev.get("file_size", -1)):
                    cached_res = prev.get("cached_result")
                    if isinstance(cached_res, tuple) and len(cached_res) == 4:
                        return cached_res

                prev_offset = int(prev["byte_offset"])
                bf.seek(prev_offset)
                delta = bf.read(f_size - prev_offset)
                last_nl = delta.rfind(b"\n")
                committed_part = delta[: last_nl + 1] if last_nl != -1 else b""
                pending_part = delta[last_nl + 1 :] if last_nl != -1 else delta

                c_steps = int(prev["c_steps"])
                c_bytes = int(prev["c_bytes"])
                c_tail: List[str] = list(prev["c_tail"])
                c_tokens: Optional[int] = prev.get("c_tokens")
                new_offset = prev_offset + (last_nl + 1 if last_nl != -1 else 0)

                if committed_part:
                    for raw_ln in committed_part.split(b"\n")[:-1]:
                        c_bytes += len(raw_ln) + 1
                        stripped, is_cp, tok = _eval_transcript_line(raw_ln)
                        if not stripped:
                            continue
                        if is_cp:
                            c_steps, c_bytes, c_tail, c_tokens = 1, len(raw_ln) + 1, [stripped], tok
                        else:
                            c_steps += 1
                            c_tail = (c_tail + [stripped])[-10:]
                            if tok is not None:
                                c_tokens = tok

                out_steps, out_bytes, out_tail, out_tokens = c_steps, c_bytes, list(c_tail), c_tokens
                if pending_part:
                    out_bytes += len(pending_part)
                    p_stripped, p_cp, p_tok = _eval_transcript_line(pending_part)
                    if p_stripped:
                        if p_cp:
                            out_steps, out_bytes, out_tail, out_tokens = 1, len(pending_part), [p_stripped], p_tok
                        else:
                            out_steps += 1
                            out_tail = (out_tail + [p_stripped])[-10:]
                            if p_tok is not None:
                                out_tokens = p_tok

                res_tuple: Tuple[int, int, str, Optional[int]] = (
                    out_steps,
                    max(0, out_bytes),
                    _format_safe_capsule_lines(out_tail[-10:], max_chars=2400),
                    out_tokens,
                )
                _TRANSCRIPT_CURSOR_CACHE[cache_key] = {
                    "file_size": f_size,
                    "byte_offset": new_offset,
                    "head_sha256": head_sha256,
                    "c_steps": c_steps,
                    "c_bytes": c_bytes,
                    "c_tail": c_tail,
                    "c_tokens": c_tokens,
                    "cached_result": res_tuple,
                }
                return res_tuple

            if len(_TRANSCRIPT_CURSOR_CACHE) > 32:
                _TRANSCRIPT_CURSOR_CACHE.clear()

            pos, bytes_scanned, carry = f_size, 0, b""
            collected_rev: List[str] = []
            post_bytes = 0
            hit_checkpoint = False
            last_actual_tokens: Optional[int] = None
            last_nl_offset: Optional[int] = None

            while pos > 0 and bytes_scanned < _TRANSCRIPT_BACKSCAN_MAX_BYTES and not hit_checkpoint:
                read_size = min(_TRANSCRIPT_BACKSCAN_CHUNK_BYTES, pos, _TRANSCRIPT_BACKSCAN_MAX_BYTES - bytes_scanned)
                new_start = pos - read_size
                bf.seek(new_start)
                chunk = bf.read(read_size)
                if last_nl_offset is None:
                    nl_idx = chunk.rfind(b"\n")
                    if nl_idx != -1:
                        last_nl_offset = new_start + nl_idx + 1

                buf = chunk + carry
                pos = new_start
                bytes_scanned += read_size
                parts = buf.split(b"\n")
                carry = parts[0]

                for raw_ln in reversed(parts[1:]):
                    post_bytes += len(raw_ln) + 1
                    stripped, is_cp, tok = _eval_transcript_line(raw_ln)
                    if not stripped:
                        continue
                    if last_actual_tokens is None and tok is not None:
                        last_actual_tokens = tok
                    collected_rev.append(stripped)
                    if is_cp:
                        hit_checkpoint = True
                        break

            if not hit_checkpoint and carry and pos == 0:
                post_bytes += len(carry)
                stripped, is_cp, tok = _eval_transcript_line(carry)
                if stripped:
                    if last_actual_tokens is None and tok is not None:
                        last_actual_tokens = tok
                    collected_rev.append(stripped)
                    if is_cp:
                        hit_checkpoint = True

            tail_lines = list(reversed(collected_rev))[-10:]
            steps = len(collected_rev)
            total_chars = max(1, min(f_size, post_bytes)) if hit_checkpoint else f_size
            res_tuple = (steps, total_chars, _format_safe_capsule_lines(tail_lines, max_chars=2400), last_actual_tokens)

            committed_offset = last_nl_offset if last_nl_offset is not None else 0
            if committed_offset == f_size:
                c_steps_val, c_bytes_val, c_tail_val, c_tokens_val = steps, total_chars, tail_lines, last_actual_tokens
            elif committed_offset == 0:
                c_steps_val, c_bytes_val, c_tail_val, c_tokens_val = 0, 0, [], None
            else:
                bf.seek(committed_offset)
                frag_raw = bf.read(f_size - committed_offset)
                f_stripped, f_cp, _ = _eval_transcript_line(frag_raw)
                if f_cp or not f_stripped or steps <= 0:
                    c_steps_val, c_bytes_val, c_tail_val, c_tokens_val = steps, total_chars, tail_lines, last_actual_tokens
                else:
                    c_steps_val = max(0, steps - 1)
                    c_bytes_val = max(0, total_chars - len(frag_raw))
                    c_tail_val = tail_lines[:-1]
                    c_tokens_val = last_actual_tokens

            _TRANSCRIPT_CURSOR_CACHE[cache_key] = {
                "file_size": f_size,
                "byte_offset": committed_offset,
                "head_sha256": head_sha256,
                "c_steps": c_steps_val,
                "c_bytes": c_bytes_val,
                "c_tail": c_tail_val,
                "c_tokens": c_tokens_val,
                "cached_result": res_tuple,
            }
            return res_tuple
    except Exception:
        return 0, 0, "", None


def _read_transcript_summary_fast(transcript_path: str) -> Tuple[int, int, str]:
    """Estrae rapidamente step, caratteri totali e capsula finale."""
    steps, total_chars, capsule, _ = _inspect_transcript_fast(transcript_path)
    return steps, total_chars, capsule

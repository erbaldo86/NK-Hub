"""Lettura incrementale O(1), backscan 64 KB e anti-spoofing compaction (pure stdlib)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from _internal.nk_acs_fastguard.constants import (
    _CHUNK_SIZE,
    _MAX_BACKSCAN_BYTES,
    _SMALL_FILE_THRESHOLD,
    _SPOOF_ROLES,
    _SPOOF_SOURCES,
    _SPOOF_TYPES,
)
from _internal.nk_acs_fastguard.state_rmw import (
    _default_state,
    _reset_state_on_compaction,
)


def _is_subagent_transcript(tp_path: str) -> bool:
    """Verifica TV-03: scansiona fino a 5 righe iniziali non vuote con step_index <= 2."""
    try:
        with open(tp_path, "r", encoding="utf-8", errors="replace") as f:
            non_empty = 0
            for _ in range(20):
                raw_line = f.readline()
                if not raw_line:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                non_empty += 1
                if non_empty > 5:
                    break
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                src = str(data.get("source") or "").strip().upper()
                typ = str(data.get("type") or "").strip().upper()
                if src in _SPOOF_SOURCES or typ in _SPOOF_TYPES:
                    continue
                raw_idx = data.get("step_index")
                step_idx = 1 if raw_idx is None else raw_idx
                if isinstance(step_idx, bool) or not isinstance(step_idx, int) or not (0 <= step_idx <= 2):
                    continue
                content = str(data.get("content") or "")
                if (
                    ("<SYSTEM_MESSAGE>" in content and "sender=" in content)
                    or ("[Message]" in content and "sender=" in content and "<env_capsule>" in content)
                    or "<subagent_reminder>" in content
                ):
                    return True
    except Exception:
        pass
    return False


def _is_verified_compaction(rec: Dict[str, Any]) -> bool:
    """Verifica TV-08: controlla source/role/author prima di accettare compacted o CHECKPOINT."""
    src = str(rec.get("source") or "").strip().upper()
    role = str(rec.get("role") or "").strip().lower()
    author = str(rec.get("author") or "").strip().lower()
    typ = str(rec.get("type") or "").strip().upper()
    if (
        src in _SPOOF_SOURCES
        or "USER" in src
        or role in _SPOOF_ROLES
        or "user" in role
        or author in _SPOOF_ROLES
        or "user" in author
        or typ in _SPOOF_TYPES
        or typ in ("MODEL_RESPONSE", "TOOL_RESPONSE", "USER_MESSAGE")
    ):
        return False
    content = str(rec.get("content") or rec.get("text") or "")
    if "[Message]" in content and "sender=" in content:
        return False
    if src and src not in ("SYSTEM",):
        return False
    if typ not in ("", "SYSTEM_MESSAGE", "COMPACTION", "CHECKPOINT", "CONTEXT_COMPACTION", "CONTEXT_SUMMARY"):
        return False
    if typ in ("CHECKPOINT", "COMPACTION", "CONTEXT_COMPACTION", "CONTEXT_SUMMARY"):
        return True
    if rec.get("compacted") is True:
        return True
    stripped_c = content.lstrip()
    if stripped_c.startswith(("<CONTEXT_SUMMARY>", "# Resuming from a compaction")):
        return True
    return False


def _valid_int_tok(val: Any) -> Optional[int]:
    """Accetta solo int >= 0 escludendo rigorosamente bool."""
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        return None
    return val


def _extract_tokens_from_mapping(d: Dict[str, Any]) -> Optional[int]:
    """Estrae input_tokens + cache_read_tokens con fallback a chiavi di contesto."""
    has_in = "input_tokens" in d
    has_cr = "cache_read_tokens" in d
    in_tok = _valid_int_tok(d.get("input_tokens")) if has_in else None
    cr_tok = _valid_int_tok(d.get("cache_read_tokens")) if has_cr else None
    if (in_tok is not None or cr_tok is not None) and not (
        (has_in and isinstance(d.get("input_tokens"), bool))
        or (has_cr and isinstance(d.get("cache_read_tokens"), bool))
    ):
        return (in_tok or 0) + (cr_tok or 0)
    for key in ("actual_context_tokens", "context_tokens", "prompt_tokens"):
        val = _valid_int_tok(d.get(key))
        if val is not None:
            return val
    return None


def _extract_tokens(rec: Dict[str, Any]) -> Optional[int]:
    """Estrae i token di contesto dal record o dal dizionario annidato usage."""
    tok = _extract_tokens_from_mapping(rec)
    if tok is not None:
        return tok
    usage = rec.get("usage")
    if isinstance(usage, dict):
        return _extract_tokens_from_mapping(usage)
    return None


def _parse_json_bytes(raw_line: bytes) -> Optional[Dict[str, Any]]:
    """Decodifica una riga JSONL restituendo un dict valido oppure None."""
    s = raw_line.strip()
    if not s:
        return None
    try:
        obj = json.loads(s.decode("utf-8", errors="replace"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _cold_backscan_64kb(tp_path: str, file_size: int, state: Dict[str, Any]) -> None:
    """Backscan iterativo a blocchi da 64 KB fino a 50 MB su cold start per file grandi."""
    min_pos = max(0, file_size - _MAX_BACKSCAN_BYTES)
    pos = file_size
    carry = b""
    committed_end = 0
    found_tokens = False
    found_compaction = False
    steps_post = 0
    latest_tokens = 0
    earliest_post_tokens = 0
    comp_offset = 0

    with open(tp_path, "rb") as f:
        while pos > min_pos and not found_compaction:
            read_start = max(min_pos, pos - _CHUNK_SIZE)
            f.seek(read_start)
            chunk = f.read(pos - read_start)
            buf = chunk + carry
            buf_base = read_start

            if committed_end == 0:
                last_nl = buf.rfind(b"\n")
                if last_nl == -1:
                    carry = buf
                    pos = read_start
                    continue
                committed_end = buf_base + last_nl + 1
                work = buf[:last_nl]
                work_base = buf_base
            else:
                work = buf
                work_base = buf_base

            first_nl = work.find(b"\n")
            if first_nl == -1 and read_start > min_pos:
                carry = work
                pos = read_start
                continue

            if read_start > min_pos and first_nl != -1:
                carry = work[:first_nl]
                complete_slice = work[first_nl + 1 :]
                slice_base = work_base + first_nl + 1
            else:
                carry = b""
                complete_slice = work
                slice_base = work_base

            lines = complete_slice.split(b"\n")
            cur_end = slice_base + len(complete_slice) + 1
            for raw_line in reversed(lines):
                line_end = cur_end
                cur_end -= len(raw_line) + 1
                stripped = raw_line.strip()
                if not stripped or not stripped.startswith(b"{"):
                    continue
                if (
                    b"CHECKPOINT" in stripped
                    or b"CONTEXT_SUMMARY" in stripped
                    or b"compacted" in stripped
                    or b"Resuming from a compaction" in stripped
                ):
                    rec = _parse_json_bytes(stripped)
                    if rec is not None and _is_verified_compaction(rec):
                        found_compaction = True
                        comp_offset = line_end
                        break
                steps_post += 1
                if (
                    b"input_tokens" in stripped
                    or b"cache_read_tokens" in stripped
                    or b"actual_context_tokens" in stripped
                    or b"context_tokens" in stripped
                    or b"prompt_tokens" in stripped
                    or b'"usage"' in stripped
                ):
                    rec = _parse_json_bytes(stripped)
                    if rec is not None:
                        tok = _extract_tokens(rec)
                        if tok is not None:
                            if not found_tokens:
                                latest_tokens = tok
                                found_tokens = True
                            if tok > 0:
                                earliest_post_tokens = tok
            pos = read_start

    if found_compaction:
        prev_cp = int(state.get("checkpoint_byte_offset", 0))
        if comp_offset > prev_cp or prev_cp > committed_end:
            new_epoch = max(1, int(state.get("compaction_epoch", 0)) + 1)
            _reset_state_on_compaction(state, comp_offset, new_epoch=new_epoch)
            state["epoch_baseline_tokens"] = earliest_post_tokens
        else:
            state["compaction_epoch"] = max(1, int(state.get("compaction_epoch", 0)))
            if earliest_post_tokens > 0 and int(state.get("epoch_baseline_tokens", 0)) == 0:
                state["epoch_baseline_tokens"] = earliest_post_tokens
    state["byte_offset"] = committed_end
    state["steps"] = steps_post
    state["last_actual_tokens"] = latest_tokens


def _advance_cursor(tp_path: str, state: Dict[str, Any]) -> None:
    """Aggiorna lo stato leggendo O(1) solo righe complete terminate da b'\\n'."""
    try:
        file_size = os.stat(tp_path).st_size
    except OSError:
        return

    byte_offset = int(state.get("byte_offset", 0))
    if file_size < byte_offset:
        fresh = _default_state()
        state.clear()
        state.update(fresh)
        byte_offset = 0

    if file_size == 0 or file_size == byte_offset:
        return

    if byte_offset == 0 and file_size > _SMALL_FILE_THRESHOLD:
        _cold_backscan_64kb(tp_path, file_size, state)
        return

    with open(tp_path, "rb") as f:
        f.seek(byte_offset)
        delta = f.read(file_size - byte_offset)

    last_nl = delta.rfind(b"\n")
    if last_nl == -1:
        return

    cur_off = byte_offset
    for raw_line in delta[:last_nl].split(b"\n"):
        cur_off += len(raw_line) + 1
        rec = _parse_json_bytes(raw_line)
        if rec is None:
            continue
        if _is_verified_compaction(rec):
            new_epoch = int(state.get("compaction_epoch", 0)) + 1
            _reset_state_on_compaction(state, cur_off, new_epoch=new_epoch)
            continue
        state["steps"] = int(state.get("steps", 0)) + 1
        tok = _extract_tokens(rec)
        if tok is not None:
            state["last_actual_tokens"] = tok
            if (
                int(state.get("compaction_epoch", 0)) > 0
                and int(state.get("epoch_baseline_tokens", 0)) == 0
                and tok > 0
            ):
                state["epoch_baseline_tokens"] = tok

    state["byte_offset"] = byte_offset + last_nl + 1

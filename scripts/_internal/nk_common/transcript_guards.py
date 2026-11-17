# -*- coding: utf-8 -*-
"""Guardie TV-03 (sub-agent transcript head) e TV-08 (verified compaction)."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Union

SPOOF_SOURCES: FrozenSet[str] = frozenset(
    ("USER", "USER_EXPLICIT", "MODEL", "ASSISTANT", "TOOL", "GENERIC")
)
SPOOF_TYPES: FrozenSet[str] = frozenset(
    ("USER_INPUT", "PLANNER_RESPONSE", "TOOL_RESULT", "TOOL_OUTPUT", "GENERIC")
)
SPOOF_ROLES: FrozenSet[str] = frozenset(("user", "model", "assistant", "tool"))

_UNTRUSTED_COMPACTION_SOURCES: FrozenSet[str] = SPOOF_SOURCES | frozenset(
    ("USER_INPUT", "TOOL_RESULT", "TOOL_OUTPUT", "SYSTEM_SDK", "PLANNER_RESPONSE")
)
_UNTRUSTED_COMPACTION_TYPES: FrozenSet[str] = SPOOF_TYPES | frozenset(
    ("MODEL_RESPONSE", "TOOL_RESPONSE", "USER_MESSAGE")
)
_COMPACTION_TYPES: FrozenSet[str] = frozenset(
    ("CHECKPOINT", "COMPACTION", "CONTEXT_COMPACTION", "CONTEXT_SUMMARY")
)
_COMPACTION_ALLOWED_TYPES: FrozenSet[str] = frozenset(
    ("", "SYSTEM_MESSAGE", "COMPACTION", "CHECKPOINT", "CONTEXT_COMPACTION", "CONTEXT_SUMMARY")
)


def valid_token_int(val: Any) -> Optional[int]:
    """Convalida un conteggio token intero >= 0 rifiutando i booleani."""
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if val >= 0 else None
    return None


def extract_actual_tokens_from_record(parsed: Dict[str, Any]) -> Optional[int]:
    """Estrae input_tokens + cache_read_tokens dai record JSONL senza bool."""
    if not isinstance(parsed, dict):
        return None
    candidates = [parsed]
    for key in ("usage", "token_usage", "usageMetadata", "usage_metadata", "message", "metadata"):
        nested = parsed.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
            sub_usage = nested.get("usage") or nested.get("token_usage")
            if isinstance(sub_usage, dict):
                candidates.append(sub_usage)

    for cand in candidates:
        in_tok = valid_token_int(cand.get("input_tokens"))
        if in_tok is None:
            in_tok = valid_token_int(cand.get("prompt_tokens"))
        if in_tok is None:
            in_tok = valid_token_int(cand.get("promptTokenCount"))
        cache_tok = valid_token_int(cand.get("cache_read_tokens"))
        if cache_tok is None:
            cache_tok = valid_token_int(cand.get("cache_read_input_tokens"))
        if cache_tok is None:
            cache_tok = valid_token_int(cand.get("cachedContentTokenCount"))
        if in_tok is not None or cache_tok is not None:
            return (in_tok or 0) + (cache_tok or 0)
    return None


def estimate_tokens(text: str) -> int:
    """Stima rapida dei token lessicali per una stringa di testo."""
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, math.ceil(len(words) * 1.15))


def is_subagent_transcript_head(
    tp_path: Union[str, Path], max_non_empty: int = 5
) -> bool:
    """Verifica TV-03: scansiona fino a max_non_empty righe iniziali con step_index <= 2."""
    limit = max(1, int(max_non_empty))
    try:
        with open(tp_path, "r", encoding="utf-8", errors="replace") as f:
            non_empty = 0
            for _ in range(max(20, limit * 4)):
                raw_line = f.readline()
                if not raw_line:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                non_empty += 1
                if non_empty > limit:
                    break
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                src = str(data.get("source") or "").strip().upper()
                typ = str(data.get("type") or "").strip().upper()
                role = str(data.get("role") or "").strip().lower()
                if src in SPOOF_SOURCES or typ in SPOOF_TYPES or role in SPOOF_ROLES:
                    continue
                raw_idx = data.get("step_index")
                step_idx = 1 if raw_idx is None else raw_idx
                if (
                    isinstance(step_idx, bool)
                    or not isinstance(step_idx, int)
                    or not (0 <= step_idx <= 2)
                ):
                    continue
                content = str(data.get("content") or "")
                if (
                    ("<SYSTEM_MESSAGE>" in content and "sender=" in content)
                    or (
                        "[Message]" in content
                        and "sender=" in content
                        and "<env_capsule>" in content
                    )
                    or "<subagent_reminder>" in content
                ):
                    return True
    except Exception:
        pass
    return False


def is_verified_compaction(record: Dict[str, Any]) -> bool:
    """Verifica TV-08: accetta compattazione reale bloccando spoofing o testo prose."""
    if not isinstance(record, dict):
        return False
    src = str(record.get("source") or "").strip().upper()
    role_u = str(record.get("role") or "").strip().upper()
    author_u = str(record.get("author") or "").strip().upper()
    rtype = str(record.get("type") or "").strip().upper()

    if rtype in _UNTRUSTED_COMPACTION_TYPES:
        return False
    if (
        src in _UNTRUSTED_COMPACTION_SOURCES
        or "USER" in src
        or role_u in _UNTRUSTED_COMPACTION_SOURCES
        or "USER" in role_u
        or author_u in _UNTRUSTED_COMPACTION_SOURCES
        or "USER" in author_u
    ):
        return False

    raw_c = record.get("content") or record.get("text") or ""
    if isinstance(raw_c, str) and "[Message]" in raw_c and "sender=" in raw_c:
        return False

    if src and src not in ("SYSTEM",):
        return False
    if rtype not in _COMPACTION_ALLOWED_TYPES:
        return False

    if record.get("compacted") is True:
        return True
    if rtype in _COMPACTION_TYPES:
        return True
    if not isinstance(raw_c, str) or not raw_c:
        return False
    stripped_c = raw_c.lstrip()
    if stripped_c.startswith(("<CONTEXT_SUMMARY>", "# Resuming from a compaction")):
        return True
    return False


def has_compaction_candidate_bytes(raw_bytes: bytes) -> bool:
    """Pre-filtro binario rapido per individuare possibili record di compattazione."""
    if not raw_bytes:
        return False
    low = raw_bytes.lower()
    return (
        b"checkpoint" in low
        or b"compact" in low
        or b"context_summary" in low
        or b"resuming from a compaction" in low
    )

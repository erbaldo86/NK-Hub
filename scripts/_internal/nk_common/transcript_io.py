# -*- coding: utf-8 -*-
"""Utilita stdlib condivise per stripping envelope XML, lettura coda transcript e WAL hash."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Optional, Union

_USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>",
    re.DOTALL | re.IGNORECASE,
)
_METADATA_BLOCKS_RE = re.compile(
    r"<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|EPHEMERAL_MESSAGE|SYSTEM_MESSAGE)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_COMPACTION_PREFIXES = ("<CONTEXT_SUMMARY>", "# Resuming from a compaction")


def strip_antigravity_envelope(text: str) -> str:
    """Estrae il testo reale utente rimuovendo i wrapper XML di sistema Antigravity."""
    if not text:
        return ""
    cleaned = _METADATA_BLOCKS_RE.sub("", str(text)).strip()
    low = cleaned.lower()
    if low.count("<user_request>") == 1 and low.count("</user_request>") == 1:
        m_req = _USER_REQUEST_RE.fullmatch(cleaned)
        if m_req:
            return m_req.group(1).strip()
    return cleaned


def normalize_prompt_for_hash(text: str) -> str:
    """Normalizza un prompt dopo stripping XML per calcolo hash deterministico."""
    stripped = strip_antigravity_envelope(text)
    return " ".join(stripped.split())


def read_transcript_tail_bytes(
    tp_path: Union[str, Path], max_bytes: int = 65536
) -> bytes:
    """Legge gli ultimi max_bytes di un file transcript JSONL in modalita binaria."""
    path_obj = Path(tp_path)
    if not path_obj.is_file():
        return b""
    limit = max(1, int(max_bytes))
    try:
        with open(path_obj, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size <= 0:
                return b""
            offset = max(0, size - limit)
            f.seek(offset, os.SEEK_SET)
            raw = f.read(limit)
            if offset > 0:
                nl_idx = raw.find(b"\n")
                if nl_idx != -1:
                    return raw[nl_idx + 1 :]
            return raw
    except OSError:
        return b""


def _extract_text_from_record_content(content: Any) -> str:
    """Estrae il testo grezzo dal campo content o text di un record JSONL."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item:
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text") or item.get("content")
                if isinstance(txt, str) and txt:
                    parts.append(txt)
        return "\n".join(parts)
    if isinstance(content, dict):
        txt = content.get("text") or content.get("content")
        if isinstance(txt, str):
            return txt
    return ""


def extract_last_user_input(
    tp_path: Union[str, Path], max_bytes: int = 65536
) -> Optional[str]:
    """Estrae l'ultimo prompt utente reale dalla coda binaria del transcript JSONL."""
    tail = read_transcript_tail_bytes(tp_path, max_bytes=max_bytes)
    if not tail:
        return None
    text_block = tail.decode("utf-8", errors="replace")
    for raw_line in reversed(text_block.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        rtype = str(rec.get("type") or "").strip().upper()
        src = str(rec.get("source") or "").strip().upper()
        role = str(rec.get("role") or "").strip().lower()
        is_user = (
            rtype == "USER_INPUT"
            or src in ("USER", "USER_EXPLICIT")
            or role == "user"
        )
        if not is_user:
            continue
        raw_text = _extract_text_from_record_content(
            rec.get("content") if rec.get("content") is not None else rec.get("text")
        )
        if not raw_text:
            continue
        if raw_text.lstrip().startswith(_COMPACTION_PREFIXES):
            continue
        cleaned = strip_antigravity_envelope(raw_text)
        if cleaned and not cleaned.lstrip().startswith(_COMPACTION_PREFIXES):
            return cleaned
    return None


def wal_bucket_hash(workspace_root: Union[str, Path]) -> str:
    """Calcola l'hash univoco a 12 caratteri del bucket WAL dalla root risolta."""
    resolved = str(Path(workspace_root).resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]

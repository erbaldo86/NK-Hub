# -*- coding: utf-8 -*-
"""Helper testuali, tail JSONL, walk .staging/ e ispezione tracking per ecosystem_scanner."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_session_handoff.constants import resolve_session_tracking_dir  # noqa: F401
from _internal.nk_session_handoff.session_state import _parse_ts_ns_value

_PATCH_SECTION_RE = re.compile(r"^##\s+`?\[")
_STAGING_IGNORED_NAMES = frozenset((".gitkeep", "__pycache__", ".pytest_cache"))
_STAGING_IGNORED_EXTS = (".pyc", ".pyo", ".tmp")
_AP14_TOK_ALT = "|".join((
    r'"step_index"\s*:', r'"status"\s*:\s*"RUNNING"', r"\battendo\s+il\s+completamento\b", r"Showing lines \d+-\d+ of \d+",
    r'"?(?:tool_calls|toolCalls|tool_results|toolResults|tool_call_id|function_call|plannerResponse|planner_response|thinkingProcess|thinking_process|reasoning_content)"?\s*:',
    r'"(?:transcript_raw_jsonl_included|failed_reasoning_included)"\s*:\s*true\b', r"\.system_generated[/\\]logs[/\\]transcript\.jsonl", r"The command exited with code -?\d+",
    r"\b(?:USER_INPUT|PLANNER_RESPONSE|SYSTEM_SDK|TOOL_RESULT|failed_reasoning|raw_transcript|transcript_jsonl|transcript_raw_jsonl|thought_signature|transient_task)\b",
    r"</?SYSTEM_MESSAGE>|<ADDITIONAL_METADATA>|</?USER_REQUEST>|<CONTEXT_SUMMARY>|<subagent_reminder>|<task_boundary>|<strict_boundaries>|<user_information>",
    r"Traceback \(most recent call last\):", r"\btask-\d+\b[^\n]{0,80}\b(?:RUNNING|WORKING|PENDING)\b",
))
_AP14_FREE_TEXT_RE = re.compile(_AP14_TOK_ALT, re.IGNORECASE)
_T12_HEAD_SMUGGLE_RE = re.compile(r"(?:(?:^|\s)!(?:diretto|raw)\b|<directive>|<env_capsule>|^\s*#{1,4}\s*(?:FASE|PHASE|MACRO[- ]?FASE|LIVELLO)\s*[1-9]\d*|\b(?:PASSIVE_SESSION_STATE_HANDOFF|SYSTEM_INSTRUCTION|INTRINSIC_GOAL|INTRINSIC_PLAN|INTRINSIC_BOOST|invoke_subagent|define_subagent|ask_question)\b)", re.IGNORECASE | re.MULTILINE)


def _clean_str(val: Any) -> str:
    return str(val or "").strip()

def _load_json_dict(raw_ln: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(raw_ln)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None

def _first_rec_ts_ns(rec: Any, keys: Tuple[str, ...]) -> int:
    return next((_parse_ts_ns(v) for k in keys if (v := rec.get(k))), 0) if isinstance(rec, dict) else 0

def _is_concurrent_ts(rec_ns: int, session_start_ns: int) -> bool:
    return session_start_ns <= 0 or rec_ns <= 0 or rec_ns >= session_start_ns


def _scrub_handoff_free_text(text: str, *, include_t12: bool = False) -> str:
    """Rimuove marker AP-14/T12 da estratti testuali e diff per prevenire auto-blocco."""
    if not text:
        return ""
    cleaned = _AP14_FREE_TEXT_RE.sub("[FILTERED]", text)
    if include_t12:
        cleaned = _T12_HEAD_SMUGGLE_RE.sub("[FILTERED]", cleaned)
    return re.sub(r"\[nk-anchor:", "(nk-anchor:", cleaned, flags=re.IGNORECASE)


def _trim_excerpt_clean(text: str, max_chars: int) -> str:
    """Taglia un estratto Markdown su confine di riga/parola entro max_chars."""
    cap = max(0, int(max_chars))
    if cap == 0 or len(text) <= cap:
        return "" if cap == 0 else text
    budget = max(1, cap - 3) if cap >= 16 else cap
    cut = text[:budget]
    if (last_ws := max(cut.rfind("\n"), cut.rfind(" "))) >= budget // 2:
        cut = cut[:last_ws]
    cut = cut.rstrip(" ,;:-")
    return (cut + "...") if (cap >= 16 and cut) else text[:cap].rstrip()


def _parse_ts_ns(raw_val: Any) -> int:
    """Converte un timestamp numerico o ISO-8601 UTC in nanosecondi epoch."""
    return _parse_ts_ns_value(raw_val)


def _read_tail_lines(file_path: Path, max_bytes: int = 32768) -> List[str]:
    """Legge le righe finali di un file testuale in O(1) RAM."""
    if not file_path.is_file():
        return []
    try:
        sz = file_path.stat().st_size
        with open(file_path, "rb") as fh:
            if sz > max_bytes:
                fh.seek(sz - max_bytes)
            raw = fh.read(max_bytes) if sz > max_bytes else fh.read()
        if sz > max_bytes and (nl := raw.find(b"\n")) != -1:
            raw = raw[nl + 1 :]
        return [ln.strip() for ln in raw.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    except OSError:
        return []


def _build_exempt_cid_set(cid_clean: str, exempt_cids: Optional[Sequence[str]] = None) -> Set[str]:
    """Normalizza i CID esenti filtrando vuoti, default_* e auto."""
    valid_exempt = {s for raw in (exempt_cids or ()) if isinstance(raw, str) and (s := raw.strip()) and not s.startswith("default_") and s.lower() != "auto"}
    return ({cid_clean} if (cid_clean and cid_clean.lower() != "auto") else set()) | valid_exempt


def _inspect_latest_handoff_writer(repo_root: Path, exempt_set: Set[str], session_start_ns: int) -> Tuple[Optional[str], Optional[str], str]:
    latest_p = repo_root / "nk_tracking" / "handoff" / "session_handoff_latest.json"
    if not latest_p.is_file():
        return None, None, ""
    try:
        l_data, mtime_ns = json.loads(latest_p.read_text(encoding="utf-8")), latest_p.stat().st_mtime_ns
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None, None, ""
    if not isinstance(l_data, dict):
        return None, None, ""
    l_cid, rec_sha = _clean_str(l_data.get("conversation_id")), _clean_str(l_data.get("state_sha256"))
    if not l_cid or l_cid in exempt_set:
        return None, l_cid or None, rec_sha
    rec_ns = _first_rec_ts_ns(l_data, ("timestamp",)) or _first_rec_ts_ns(l_data.get("manifest"), ("timestamp",)) or mtime_ns
    return (l_cid if _is_concurrent_ts(rec_ns, session_start_ns) else None), l_cid, rec_sha


def _inspect_anchor_tail_writers(repo_root: Path, exempt_set: Set[str], session_start_ns: int) -> Tuple[List[str], bool, Optional[str], str]:
    anc_cids: List[str] = []
    corrupt, last_cid, rec_sha = False, None, ""
    for ln in _read_tail_lines(repo_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"):
        if (rec := _load_json_dict(ln)) is None:
            corrupt = True
            continue
        a_cid = _clean_str(rec.get("conversation_id"))
        last_cid, rec_sha = a_cid or last_cid, _clean_str(rec.get("state_sha256")) or rec_sha
        if a_cid and a_cid not in exempt_set and _is_concurrent_ts(_first_rec_ts_ns(rec, ("timestamp_ns", "timestamp", "ts")), session_start_ns):
            anc_cids.append(a_cid)
    return anc_cids, corrupt, last_cid, rec_sha


def _inspect_tracking_state(repo_root: Path, cid_clean: str, session_start_ns: int, exempt_cids: Optional[Sequence[str]] = None) -> Tuple[bool, List[str], Optional[str], Optional[str], str]:
    """Ispeziona session_handoff_latest.json e coda session_anchor.jsonl per scrittori concorrenti."""
    exempt_set = _build_exempt_cid_set(cid_clean, exempt_cids)
    l_conc, l_last, l_sha = _inspect_latest_handoff_writer(repo_root, exempt_set, session_start_ns)
    anc_cids, corrupt, a_last, a_sha = _inspect_anchor_tail_writers(repo_root, exempt_set, session_start_ns)
    dedup_cids, dedup_anc = list(dict.fromkeys(([l_conc] if l_conc else []) + anc_cids)), list(dict.fromkeys(anc_cids))
    warn: Optional[str] = "CORRUPT_ANCHOR_TAIL" if corrupt else (f"CONCURRENT_ANCHOR_CID:{','.join(dedup_anc)}" if dedup_anc else None)
    return bool(dedup_cids), dedup_cids, warn, (a_last or l_last), (a_sha or l_sha)


def _scandir_safe(cur_dir: Path) -> List[os.DirEntry[str]]:
    try:
        with os.scandir(cur_dir) as it:
            return list(it)
    except OSError:
        return []

def _entry_stat_item(entry: os.DirEntry[str], staging_dir: Path) -> Optional[Tuple[str, Path, int, int]]:
    try:
        ep, st = Path(entry.path), entry.stat(follow_symlinks=False)
        return (ep.relative_to(staging_dir).as_posix(), ep, int(st.st_size), int(st.st_mtime_ns))
    except OSError:
        return None


def _collect_staging_raw_items(staging_dir: Path) -> List[Tuple[str, Path, int, int]]:
    raw_items: List[Tuple[str, Path, int, int]] = []
    stack: List[Path] = [staging_dir]
    while stack:
        for entry in _scandir_safe(stack.pop()):
            if entry.name in _STAGING_IGNORED_NAMES or entry.name.endswith(_STAGING_IGNORED_EXTS):
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False) and (item := _entry_stat_item(entry, staging_dir)) is not None:
                raw_items.append(item)
    return raw_items

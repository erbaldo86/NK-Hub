# -*- coding: utf-8 -*-
"""Costanti, tabella AP-1..AP-13 e helper base per nk_transcript_tools."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import HALLUCINATED_SCRIPT_DENYLIST

_DIRECT_TOOLS = (
    "run_command",
    "replace_file_content",
    "write_to_file",
    "write_file",
    "edit_file",
    "notebook_edit",
)
DIRECT_TOOLS = _DIRECT_TOOLS

_DELEGATION_TOOLS = (
    "invoke_subagent",
    "define_subagent",
    "send_message",
    "swarm",
    "post_message",
)
DELEGATION_TOOLS = _DELEGATION_TOOLS

_WRITE_BURST_TOOLS = ("write_file", "write_to_file", "edit_file")
WRITE_BURST_TOOLS = _WRITE_BURST_TOOLS

_READ_FILE_TOOLS = ("view_file", "read_file")
READ_FILE_TOOLS = _READ_FILE_TOOLS

_SAFE_WRITE_MARKERS = (
    ".staging/",
    "/.staging/",
    "nk_genome/",
    "nk_tracking/",
    "scratch/",
    "appdata/local/temp",
    "/temp/",
    "brain/",
    "patch_notes.md",
    "readme",
)

_READONLY_CMD_MARKERS = (
    "pytest",
    "rsi_convergence_engine.py",
    "ast_guard_validator.py",
    "nk_session_bootstrap.py",
    "dast_sandbox_runner.py",
    "compliance",
    "evidence",
    "oracle-lock verify",
    "oracle-lock",
    "--verify",
    "win32_2pc_engine.py",
)

_WRITE_CMD_RE = re.compile(
    r"(\bset-content\b|\bout-file\b|\badd-content\b|\bcopy-item\b|\bmove-item\b"
    r"|\bnew-item\b|\bremove-item\b|--promote-staging|>>|(?<![-\w])>(?![>=]))",
    re.IGNORECASE,
)
_CLAIM_RE = re.compile(
    r"("
    r"\bCONVERGED_OPTIMAL\b"
    r"|\b\d+\s*/\s*\d+\s+PASS(?:ED)?\b"
    r"|\b100(?:\.0+)?%\s*(?:PASS(?:ED)?|VERIFIED)\b"
    r"|\ball\s+tests?\s+pass(?:ed|ing)?\b"
    r"|\b0\s+fail(?:ed|ures?)\b"
    r"|\bEXIT[_\s]+(?:CODE\s+)?0\b"
    r")",
    re.IGNORECASE,
)
_CLAIM_FENCE_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_CLAIM_INLINE_CODE_RE = re.compile(r"(`{1,3})([^`\n]+?)\1")

EXIT_CODE_RE = re.compile(r"(?:The\s+)?[Cc]ommand exited with code\s+(-?\d+)\b")
_JSON_EXIT_CODE_RE = re.compile(r'"(?:exit_code|returncode)"\s*:\s*(-?\d+)\b', re.IGNORECASE)
_EXITED_WITH_CODE_RE = re.compile(r"\bexited with code\s+(-?\d+)\b", re.IGNORECASE)
_EXIT_ZERO_RE = re.compile(
    r"((?:The\s+)?[Cc]ommand exited with code\s+0\b|\bexited with code\s+0\b"
    r'|\"exit_code\"\s*:\s*0\b|\"returncode\"\s*:\s*0\b)',
    re.IGNORECASE,
)

_READ_FILE_OUTPUT_HEADER_RE = re.compile(
    r"(?:^|\n)(?:Showing lines \d+-\d+ of \d+\b|Partial read \(lines \d+-\d+ of \d+\)\.)"
)
_PURE_TOOL_OUTPUT_HEADER_RE = re.compile(
    r"^\s*(?:Created At:\s+\d{4}-\d{2}-\d{2}T|(?:The\s+)?[Cc]ommand exited with code\s+-?\d+|Showing lines \d+-\d+ of \d+\b)"
)

_PASS_FALSE_RE = re.compile(r'("(?:pass|passed)"\s*:\s*false\b|\b(?:pass|passed)\s*:\s*false\b)', re.IGNORECASE)
_PASS_TRUE_RE = re.compile(r'("(?:pass|passed)"\s*:\s*true\b|\b(?:pass|passed)\s*:\s*true\b)', re.IGNORECASE)
_SCRIPT_RE = re.compile(r"([a-zA-Z0-9_]+\.py)\b")
INTENT_BRIEF_ID_RE = re.compile(r"\bIB-\d{8}-[0-9A-Fa-f]{6,8}\b")
_VERIFICATION_TARGETS = ("pytest", "rsi_convergence_engine", "ast_guard_validator", "dast_sandbox_runner", "nk_registry_indexer")

CANONICAL_AP_TABLE: Dict[str, Dict[str, str]] = {
    "AP-1": {"code": "AP-1", "rule": "DIRETTO_OVERLOAD_FORBIDDEN", "severity": "CRITICAL", "description": "!diretto forbidden on prompts >1500 chars or >=2 phases."},
    "AP-2": {"code": "AP-2", "rule": "ROLE_FUSION_OR_MISSING_DELEGATION", "severity": "CRITICAL", "description": "Incompatible role fusion or missing subagent delegation on large prompt."},
    "AP-2b": {"code": "AP-2b", "rule": "BUILDER_WRITE_TOOLS_REGISTRATION", "severity": "HIGH", "description": "Missing define_subagent(..., EnableWriteTools=True) or self for Builder (G3-01)."},
    "AP-3": {"code": "AP-3", "rule": "STAGING_2PC_BYPASS", "severity": "CRITICAL", "description": "Writes to src_app/ or tests/ without .staging/ and win32_2pc_engine.py."},
    "AP-4": {"code": "AP-4", "rule": "GOODHART_LOOP_WITHOUT_ORACLE_LOCK", "severity": "CRITICAL", "description": "Goodhart loop ('until 100% PASS') in same turn without oracle-lock."},
    "AP-5": {"code": "AP-5", "rule": "EXTERNAL_RSI_MISSING_ROOT", "severity": "HIGH", "description": "rsi_convergence_engine.py --verify missing --root on external project."},
    "AP-6": {"code": "AP-6", "rule": "MULTI_PHASE_WITHOUT_STOP_GATE", "severity": "HIGH", "description": ">=3 macro-phases in single turn without STOP_GATE or oracle-lock."},
    "AP-7": {"code": "AP-7", "rule": "UNSHARDED_WEB_RESEARCH_BURST", "severity": "MEDIUM", "description": "Simultaneous search_web + tavily >10 queries without research subagent sharding."},
    "AP-8": {"code": "AP-8", "rule": "HOLDOUT_SET_B_LEAK_TO_BUILDER", "severity": "CRITICAL", "description": "Holdout Set B secret test cases leaked to Builder prompt."},
    "AP-9": {"code": "AP-9", "rule": "IMPROPER_ENV_CAPSULE_IN_USER_PROMPT", "severity": "HIGH", "description": "Improper <env_capsule> in initial user prompt without !diretto or invoke_subagent."},
    "AP-10": {"code": "AP-10", "rule": "PASSIVE_SLASH_COMMAND_SUGGESTION", "severity": "HIGH", "description": "Passive suggestion to manually type /goal, /boost, /plan or /implementation instead of autonomous activation."},
    "AP-11": {"code": "AP-11", "rule": "CANARY_HOLDOUT_LEAK", "severity": "CRITICAL", "description": "Holdout canary leak detected in outbound prompt ([RULE-ORACLE-LOCK])."},
    "AP-12": {"code": "AP-12", "rule": "STATE_HANDOFF_IMPERATIVE_LEAK", "severity": "CRITICAL", "description": "STATE_HANDOFF_IMPERATIVE_LEAK: Imperative directive or intrinsic protocol leak inside Passive Session State Handoff."},
    "AP-13": {"code": "AP-13", "rule": "STATE_HANDOFF_COGNITIVE_TUNNELING", "severity": "CRITICAL", "description": "STATE_HANDOFF_COGNITIVE_TUNNELING: Prescriptive track or option menu detected inside Passive Session State Handoff."},
}


def _get_runtime_temp_markers() -> Tuple[str, ...]:
    """Restituisce i prefissi delle directory temporanee risolti a runtime."""
    import tempfile

    markers: List[str] = []
    for raw_v in (
        os.environ.get("TEMP", "").strip(),
        os.environ.get("TMP", "").strip(),
        os.environ.get("NK_HOOKS_TEMP_DIR", "").strip(),
        tempfile.gettempdir(),
    ):
        if raw_v:
            norm_v = Path(raw_v).resolve().as_posix().lower().rstrip("/")
            if norm_v:
                markers.append(norm_v + "/")
    return tuple(dict.fromkeys(markers))


def _strip_claim_code_spans(text: str) -> str:
    """Rimuove blocchi fenced e span inline prima di cercare claim."""
    cleaned = _CLAIM_FENCE_RE.sub(" ", text or "")
    return _CLAIM_INLINE_CODE_RE.sub(" ", cleaned)


def clean_tool_path(val: Any) -> str:
    """Normalizza un argomento percorso o azione rimuovendo virgolette esterne."""
    if val is None:
        return ""
    s = str(val).strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            parsed = json.loads(s)
            if isinstance(parsed, str):
                s = parsed
        except Exception:
            pass
    return s.strip().strip('"').strip("'").strip()


def clean_tool_str(val: Any) -> str:
    """Decodifica stringhe JSON doppiamente quotate preservando apici interni."""
    if val is None:
        return ""
    s = str(val).strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            parsed = json.loads(s)
            if isinstance(parsed, str):
                return parsed.strip()
        except Exception:
            return s[1:-1].strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].strip()
    return s


def extract_tool_name(call: Dict[str, Any]) -> str:
    """Estrae il nome canonico del tool da un descrittore tool_call."""
    if not isinstance(call, dict):
        return ""
    return clean_tool_path(call.get("name") or call.get("toolName") or call.get("tool_name") or "")


def extract_tool_args(call: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae il dizionario degli argomenti da un descrittore tool_call."""
    if not isinstance(call, dict):
        return {}
    args = call.get("args")
    if args is None:
        args = call.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    return args if isinstance(args, dict) else {}


def _extract_call_id(item: Dict[str, Any]) -> str:
    """Estrae l'identificativo di correlazione da una tool_call o risultato."""
    if not isinstance(item, dict):
        return ""
    id_keys = ("tool_call_id", "call_id", "toolCallId", "id")
    for key in id_keys:
        raw_val = item.get(key)
        if raw_val is not None and not isinstance(raw_val, bool):
            cleaned = clean_tool_path(raw_val)
            if cleaned:
                return cleaned
    for nested_key in ("tool_result", "result", "tool_response", "function_call"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            for key in id_keys:
                raw_val = nested.get(key)
                if raw_val is not None and not isinstance(raw_val, bool):
                    cleaned = clean_tool_path(raw_val)
                    if cleaned:
                        return cleaned
    tr_list = item.get("tool_results")
    if isinstance(tr_list, list) and len(tr_list) == 1 and isinstance(tr_list[0], dict):
        for key in id_keys:
            raw_val = tr_list[0].get(key)
            if raw_val is not None and not isinstance(raw_val, bool):
                cleaned = clean_tool_path(raw_val)
                if cleaned:
                    return cleaned
    return ""


def _pop_correlated_tool_call(pending_calls: List[Dict[str, Any]], tool_record: Dict[str, Any]) -> Dict[str, Any]:
    """Correla la chiamata tool tramite call_id con fallback FIFO sicuro."""
    if not pending_calls:
        return {}
    rec_call_id = _extract_call_id(tool_record)
    if rec_call_id:
        for idx, cand in enumerate(pending_calls):
            if _extract_call_id(cand) == rec_call_id:
                return pending_calls.pop(idx)
    return pending_calls.pop(0)


def classify_transcript_record(rec: Dict[str, Any]) -> str:
    """Classifica un record transcript in USER, SYSTEM, MODEL o TOOL."""
    if not isinstance(rec, dict):
        return "OTHER"
    rec_type = str(rec.get("type") or "").strip().upper()
    src = str(rec.get("source") or rec.get("role") or "").strip().upper()
    if rec_type == "USER_INPUT" or "USER" in src or "USER" in rec_type:
        return "USER"
    if rec_type == "SYSTEM_MESSAGE" or src == "SYSTEM" or "SYSTEM_MESSAGE" in src:
        return "SYSTEM"
    if rec_type in ("GENERIC", "TOOL_RESULT", "TOOL_OUTPUT") or src in ("TOOL", "TOOL_RESULT", "TOOL_OUTPUT"):
        return "TOOL"
    if rec_type == "PLANNER_RESPONSE":
        return "MODEL"
    calls = rec.get("tool_calls")
    content = str(rec.get("content") or "")
    if src in ("MODEL", "ASSISTANT"):
        if not calls and _PURE_TOOL_OUTPUT_HEADER_RE.search(content):
            return "TOOL"
        return "MODEL"
    if not calls and (rec.get("output") or rec.get("tool_output") or rec.get("tool_results")):
        return "TOOL"
    return "OTHER"


def is_user_turn_record(rec: Dict[str, Any]) -> bool:
    """Verifica se il record rappresenta un input esplicito dell'utente."""
    return classify_transcript_record(rec) == "USER"


def is_read_file_output(text: str, correlated_tool: str = "") -> bool:
    """Determina se un testo proviene da read_file per esentarlo dal check exit code."""
    if correlated_tool in _READ_FILE_TOOLS:
        return True
    if not text:
        return False
    if "File Path: `file:///" in text:
        return True
    return bool(_READ_FILE_OUTPUT_HEADER_RE.search(text))


def extract_command_exit_code(text: str, correlated_tool: str = "") -> Optional[int]:
    """Estrae l'exit code di un comando shell ignorando letture file."""
    if not text or is_read_file_output(text, correlated_tool=correlated_tool):
        return None
    if correlated_tool and correlated_tool != "run_command":
        return None
    for pat in (EXIT_CODE_RE, _JSON_EXIT_CODE_RE, _EXITED_WITH_CODE_RE):
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def _has_missing_path_error(rec_status: str, rec_txt: str) -> bool:
    """Rileva errori reali di file mancante."""
    if (rec_status or "").strip().upper() == "ERROR":
        return True
    if _READ_FILE_OUTPUT_HEADER_RE.search(rec_txt) or "File Path: `file:///" in rec_txt:
        return False
    low = (rec_txt or "").lower()
    return any(
        err_tok in low
        for err_tok in (
            "getfileattributesex",
            "cannot find the path specified",
            "filenotfounderror",
            "path does not exist",
            "no such file or directory",
            "file does not exist",
        )
    )


def validate_intent_brief_id(text: str) -> Dict[str, Any]:
    """Valida ed estrae gli identificativi Intent Brief L0."""
    unique_ids = list(dict.fromkeys(INTENT_BRIEF_ID_RE.findall(text or "")))
    return {"valid": len(unique_ids) > 0, "count": len(unique_ids), "ids": unique_ids}

# -*- coding: utf-8 -*-
"""Scansione transcript e raccolta metriche per nk_compliance_checker."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import ONBOARDING_TRIGGERS, VERSION
from _internal.nk_common.paths import (
    _EXTERNAL_PROJECTS_CMD_RE, _NK_PROGET_LOCALE_CMD_RE as _LOCALE_PATH_RE,
    _NK_PROGET_ONLINE_CMD_RE as _ONLINE_PATH_RE, reconfigure_streams,
)
from _internal.nk_common.transcript_io import strip_antigravity_envelope
from _internal.nk_compliance_checker.holdout_turn_detector import (
    _split_shell_segments, update_holdout_and_test_turn_counters,
)

_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent.parent
_workspace_root = _SCRIPTS_DIR.parent.parent if _SCRIPTS_DIR.parent.name == ".staging" else _SCRIPTS_DIR.parent

try:
    from nk_context_sentry import NKContextSentry
except ImportError:
    try:
        from scripts.nk_context_sentry import NKContextSentry
    except ImportError:
        NKContextSentry = None  # type: ignore[assignment]

try:
    import nk_transcript_tools as _tt
except ImportError:
    from scripts import nk_transcript_tools as _tt  # type: ignore[no-redef]

CANONICAL_AP_TABLE, DIRECT_AUDIT_TOOLS, DELEGATION_TOOLS, READ_FILE_TOOLS = (
    _tt.CANONICAL_AP_TABLE, _tt.DIRECT_TOOLS, _tt.DELEGATION_TOOLS, _tt.READ_FILE_TOOLS,
)
_has_missing_path_error = _tt._has_missing_path_error
_inspect_record_blind_reads_and_bursts = _tt._inspect_record_blind_reads_and_bursts
_pop_correlated_tool_call = _tt._pop_correlated_tool_call
classify_transcript_record = _tt.classify_transcript_record
clean_tool_path, clean_tool_str = _tt.clean_tool_path, _tt.clean_tool_str
discover_active_main_transcript = _tt.discover_active_main_transcript
extract_command_exit_code = _tt.extract_command_exit_code
extract_tool_args, extract_tool_name = _tt.extract_tool_args, _tt.extract_tool_name
is_read_file_output = _tt.is_read_file_output
is_subagent_transcript_file = _tt.is_subagent_transcript_file
is_user_turn_record = _tt.is_user_turn_record
load_transcript_records = _tt.load_transcript_records
parse_transcript_events = _tt.parse_transcript_events

COMPLIANCE_CHECKER_VERSION: str = VERSION
DDI_DIRECT_STREAK_LIMIT: int = 12
SESSION_TELEMETRY_MAX_SKEW_SECONDS: float = 7200.0
_CONVERGED_JSON_RE = re.compile(r'"(?:status|verdict)"\s*:\s*"CONVERGED_OPTIMAL"')
EXEMPT_WRITE_MARKERS = (
    ".staging/", "/.staging/", "brain/", "/.gemini/antigravity/brain/",
    "scratch/", "nk_genome/", "nk_tracking/", "appdata/local/temp", "/temp/", "%temp%", "nk_sandbox_", "nk_diagnostics",
)
_EXEMPT_SHORT_PROMPTS = frozenset({"ok", "si", "sì", "procedi", "approvo", "confermo"}) | frozenset(ONBOARDING_TRIGGERS)
_PROTECTED_TRACKING_MARKERS = (
    "oracle_lock", "oracle_lock_holdout", "tests_holdout_lock", "governance_lock",
    "tensor_rsi_lock", "tensor_sessions", "quality_baseline", "/oracle_holdout/", "/benchmark_suite/", "checkpoint_",
)
_WRITE_TOOL_NAMES = ("write_to_file", "write_file", "replace_file_content", "edit_file", "notebook_edit", "multi_replace_file_content")
_ONLINE_MUTATE_RE = re.compile(
    r"(?:win32_2pc_engine(?:\.py)?|external_project_scaffolder(?:\.py)?|"
    r"\b(?:set-content|out-file|add-content|copy-item|move-item|remove-item|new-item|sc|ac|ni|ri|del|erase|copy|move|ren|rm|cp|mv|robocopy|xcopy|rmdir|mkdir|write_text|write_bytes|fileio|unlink)\b|"
    r"\bos\.(?:remove|unlink|replace|rename|open)\b|\bshutil\.[a-z_]+\b|\bopen\s*\([^)]*(?:['\"][rwa+xb]*[wa+x][^'\"]*['\"]|flags\s*=)|"
    r"src_app/|tests/|checkpoint_|patch_notes\.md|update_|migrate_|\bgit\s+(?:add|commit|push|reset|checkout|clean)\b|>>|(?<![-\w])>(?![>=]))",
    re.IGNORECASE,
)
_READONLY_EXT_CMD_TOKENS = ("pytest", "rsi_convergence_engine.py", "ast_guard_validator.py", "external_project_scaffolder.py --retrofit", "nk_transcript_tools.py")
_EXT_CMD_WRITE_INDICATORS = ("src_app/", "tests/", "checkpoint_", "patch_notes.md", "update_", "migrate_", "set-content", "out-file", "copy-item", "remove-item", "write_text", "write_bytes", "robocopy", "xcopy", ">>")


def _is_subagent_transcript(transcript_path: Path) -> bool:
    """Verifica se un file transcript.jsonl appartiene a un sub-agente."""
    return is_subagent_transcript_file(Path(transcript_path))


def find_active_transcript() -> Optional[Path]:
    """Individua il transcript attivo dell'Agente Principale."""
    return discover_active_main_transcript()


def _is_unstage_protected_tracking_write(norm: str) -> bool:
    """Rileva scritture non staged su lock, tensor_sessions, holdout, benchmark, baseline o checkpoint."""
    if ".staging/" in norm:
        return False
    norm_s = "/" + norm.lstrip("/")
    if "/reports_and_briefs/" in norm_s:
        return False
    return any(m in norm_s for m in _PROTECTED_TRACKING_MARKERS)


def _is_governance_md_path(norm: str) -> bool:
    """Rileva file Markdown di governance (/.agents/, /rules/, /skills/, /plugins/ o AGENTS/SKILL)."""
    norm_s = "/" + norm.lstrip("/")
    base = norm.rsplit("/", 1)[-1]
    return base in ("agents.md", "skill.md", "agent.md", "claude.md") or any(
        m in norm_s for m in ("/.agents/", "/rules/", "/skills/", "/plugins/")
    )


def _is_non_code_doc_or_exempt(norm: str) -> bool:
    """Restituisce True per estensioni documentali non critiche o directory esenti."""
    if norm.endswith(".md"):
        return not _is_governance_md_path(norm)
    return norm.endswith((".txt", ".jsonl")) or any(t in norm for t in ("benchmark_", "reports_and_briefs"))


def _is_production_code_write(target_file: str) -> bool:
    """Determina se una scrittura riguarda codice applicativo o governance critica."""
    cleaned = clean_tool_path(target_file)
    if not cleaned:
        return False
    norm = cleaned.replace("\\", "/").lower()
    if "prod_src" in norm or _is_unstage_protected_tracking_write(norm):
        return True
    if any(marker in norm for marker in EXEMPT_WRITE_MARKERS):
        return False
    return not _is_non_code_doc_or_exempt(norm)


def _classify_non_cmd_ext_write(norm: str) -> Tuple[bool, bool]:
    """Classifica path diretti verso Online read-only o Locale/Legacy fuori da .staging/."""
    if _ONLINE_PATH_RE.search(norm):
        return True, True
    is_loc = "nk_external_projects/" in norm or bool(_LOCALE_PATH_RE.search(norm))
    if is_loc and ".staging/" not in norm and "/.staging" not in norm:
        return True, False
    return False, False


def _seg_is_locale_write(seg: str) -> bool:
    """Verifica se un singolo segmento shell scrive fuori .staging/ verso Locale/Legacy."""
    if not ("nk_external_projects/" in seg or _EXTERNAL_PROJECTS_CMD_RE.search(seg) or _LOCALE_PATH_RE.search(seg)):
        return False
    if ".staging/" in seg or "/.staging" in seg or "win32_2pc_engine.py" in seg:
        return False
    has_write = any(ind in seg for ind in _EXT_CMD_WRITE_INDICATORS) or bool(_ONLINE_MUTATE_RE.search(seg))
    is_readonly = any(tok in seg for tok in _READONLY_EXT_CMD_TOKENS) and not _ONLINE_MUTATE_RE.search(seg)
    return has_write and not is_readonly


def _classify_external_write_kind(target_or_cmd: str, is_command: bool = False) -> Tuple[bool, bool]:
    """Restituisce (is_external_unstage, is_online_write) ispezionando i segmenti shell singolarmente."""
    cleaned = clean_tool_str(target_or_cmd) if is_command else clean_tool_path(target_or_cmd)
    if not cleaned:
        return False, False
    norm = cleaned.replace("\\", "/").lower()
    if not is_command:
        return _classify_non_cmd_ext_write(norm)
    ext_hit, online_hit = False, False
    for seg in _split_shell_segments(norm) or [norm]:
        if _ONLINE_PATH_RE.search(seg) and _ONLINE_MUTATE_RE.search(seg):
            ext_hit, online_hit = True, True
        elif _seg_is_locale_write(seg):
            ext_hit = True
    return ext_hit, online_hit


def _is_external_unstage_write(target_or_cmd: str, is_command: bool = False) -> bool:
    """Rileva scritture non consentite verso NK Proget/Online, Locale o NK_External_Projects."""
    return _classify_external_write_kind(target_or_cmd, is_command=is_command)[0]


def _is_exempt_diagnostic_nonzero(content_text: str) -> str:
    """Classifica i codici di uscita diversi da zero di audit o cicli REFINING."""
    if '"status": "FAIL"' in content_text and '"scores":' in content_text and '"procedural_score":' in content_text:
        return "EXEMPT_EXTERNAL_AUDIT"
    if '"status": "REFINING"' in content_text and ('"profile": "vibe_sprint_micro_rsi"' in content_text or '"delta_k":' in content_text):
        return "INTERMEDIATE_REFINING"
    return "REAL_ERROR"


def _parse_record_epoch(raw_ts: Any) -> Optional[float]:
    """Converte un campo timestamp numerico o ISO-8601 in secondi epoch."""
    if isinstance(raw_ts, (int, float)) and not isinstance(raw_ts, bool):
        return float(raw_ts)
    if isinstance(raw_ts, str) and raw_ts.strip():
        cleaned = raw_ts.strip()
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        try:
            return datetime.fromisoformat(cleaned).timestamp()
        except ValueError:
            return None
    return None


def _extract_call_correlation_id(payload: Dict[str, Any]) -> str:
    """Delega l'estrazione dell'identificativo di correlazione a nk_transcript_tools."""
    return _tt._extract_call_id(payload)


def _is_verified_converged_tool_output(content_text: str, corr_cmd: str, exit_val: Optional[int]) -> bool:
    """Rileva CONVERGED_OPTIMAL solo da output tool strutturati validi."""
    if exit_val is not None and exit_val != 0:
        return False
    if _CONVERGED_JSON_RE.search(content_text):
        return True
    cmd_low = (corr_cmd or "").lower()
    return ("rsi_convergence_engine.py" in cmd_low or "auto_heal_pipeline.py" in cmd_low) and "CONVERGED_OPTIMAL" in content_text


def _tally_write_tool(counters: Dict[str, Any], args: Dict[str, Any]) -> None:
    """Aggiorna i contatori scrittura per write/edit/multi_replace fuori o dentro .staging."""
    counters["write_calls"] += 1
    target_f = clean_tool_path(
        args.get("TargetFile") or args.get("Path") or args.get("AbsolutePath") or args.get("NotebookPath") or args.get("file") or ""
    )
    ext_hit, online_hit = _classify_external_write_kind(target_f, is_command=False)
    if ext_hit:
        counters["external_unstage_writes"] += 1
        counters["code_write_calls"] += 1
        if online_hit:
            counters["online_write_calls"] += 1
    elif _is_production_code_write(target_f):
        counters["code_write_calls"] += 1


def _tally_run_command(counters: Dict[str, Any], args: Dict[str, Any]) -> None:
    """Aggiorna i contatori governativi e le scritture esterne per chiamate run_command."""
    cmd = clean_tool_str(args.get("CommandLine") or args.get("command") or "")
    if any(s in cmd for s in ("auto_heal_pipeline.py", "rsi_convergence_engine.py")):
        counters["healing_loop_executed"] = True
    if "ast_guard_validator.py" in cmd:
        counters["ast_guard_executed"] = True
    if "win32_2pc_engine.py" in cmd:
        counters["win32_2pc_executed"] = True
    if "nk_session_bootstrap.py" in cmd:
        counters["bootstrap_executed"] = True
    if "vibe_sprint_router.py" in cmd and "--meta-prompt-gate" in cmd:
        counters["meta_prompt_gate_executed"] = True
    ext_hit, online_hit = _classify_external_write_kind(cmd, is_command=True)
    if ext_hit:
        counters["external_unstage_writes"] += 1
        if online_hit:
            counters["online_write_calls"] += 1


def scan_transcript_metrics(transcript_file: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scansiona i record del transcript tramite il parser unificato."""
    events = parse_transcript_events(transcript_file, only_after_last_turn=False, hydrate_truncated=True)
    records = [ev["record"] for ev in events]
    counters: Dict[str, Any] = {
        "total_steps": len(records), "total_tool_calls": 0, "polling_calls": 0,
        "subagents_invoked": 0, "subagents_polled": 0, "write_calls": 0, "code_write_calls": 0,
        "external_unstage_writes": 0, "online_write_calls": 0, "error_steps": 0, "command_error_steps": 0,
        "refining_vibe_steps": 0, "blind_read_errors": 0, "write_burst_steps": 0,
        "saw_converged_optimal": False, "max_direct_tool_calls_streak": 0,
        "healing_loop_executed": False, "ast_guard_executed": False, "win32_2pc_executed": False,
        "bootstrap_executed": False, "meta_prompt_gate_executed": False, "has_non_exempt_user_turn": False,
        "holdout_read_calls": 0, "test_edit_calls": 0,
        "same_turn_test_edits": 0, "holdout_or_same_turn_test_anomalies": 0,
    }
    current_direct_streak = 0

    for ev in events:
        step_num, data, cat = ev["step_num"], ev["record"], ev["category"]
        step_has_error = ev["status"] == "ERROR"
        if step_has_error:
            counters["error_steps"] += 1
        content_text, calls, corr_tool, corr_cmd = ev["output_text"], ev["calls"], ev["corr_tool"], ev["corr_cmd"]
        if cat == "TOOL" and not calls and corr_tool in READ_FILE_TOOLS and _has_missing_path_error(ev["status"], content_text):
            counters["blind_read_errors"] += 1
        if (cat == "TOOL" or ev["has_inline_tool_out"]) and not is_read_file_output(content_text, correlated_tool=corr_tool):
            exit_val = extract_command_exit_code(content_text, correlated_tool=corr_tool)
            if exit_val is not None and exit_val != 0:
                err_kind = _is_exempt_diagnostic_nonzero(content_text)
                if err_kind == "INTERMEDIATE_REFINING":
                    counters["refining_vibe_steps"] += 1
                elif err_kind == "REAL_ERROR":
                    counters["command_error_steps"] += 1
                    counters["error_steps"] += 0 if step_has_error else 1
            elif (not corr_tool or corr_tool == "run_command") and _is_verified_converged_tool_output(content_text, corr_cmd, exit_val):
                counters["saw_converged_optimal"] = True

        if cat in ("USER", "SYSTEM"):
            if is_user_turn_record(data):
                stripped_user = strip_antigravity_envelope(ev["content"]).strip()
                norm_user = " ".join(re.sub(r"[^\w\s]|_", " ", stripped_user.lower()).split())
                if stripped_user and not stripped_user.startswith("<CONTEXT_SUMMARY>") and stripped_user.lower() not in _EXEMPT_SHORT_PROMPTS and norm_user not in _EXEMPT_SHORT_PROMPTS:
                    counters["has_non_exempt_user_turn"] = True
                if step_num > 1:
                    current_direct_streak = 0
            continue
        if cat == "TOOL" and not calls:
            continue

        b_err, w_burst = _inspect_record_blind_reads_and_bursts(data, calls)
        counters["blind_read_errors"] += b_err
        counters["write_burst_steps"] += w_burst
        update_holdout_and_test_turn_counters(counters, calls)

        step_direct_calls, step_has_delegation = 0, False
        for call in calls:
            counters["total_tool_calls"] += 1
            tname, args = extract_tool_name(call), extract_tool_args(call)
            if tname in DELEGATION_TOOLS:
                step_has_delegation = True
            elif tname in DIRECT_AUDIT_TOOLS:
                step_direct_calls += 1
            act_low = clean_tool_path(args.get("Action") or args.get("action") or "").lower()
            if tname == "manage_task" and act_low == "status":
                counters["polling_calls"] += 1
            elif tname == "manage_subagents" and act_low == "list":
                counters["subagents_polled"] += 1
            elif tname == "invoke_subagent":
                counters["subagents_invoked"] += 1
            elif tname in _WRITE_TOOL_NAMES:
                _tally_write_tool(counters, args)
            elif tname == "run_command":
                _tally_run_command(counters, args)

        if step_has_delegation or (is_user_turn_record(data) and step_num > 1):
            current_direct_streak = 0
        elif step_direct_calls > 0:
            current_direct_streak += step_direct_calls
            counters["max_direct_tool_calls_streak"] = max(counters["max_direct_tool_calls_streak"], current_direct_streak)

    if counters["refining_vibe_steps"] > 0 and not counters["saw_converged_optimal"]:
        counters["command_error_steps"] += counters["refining_vibe_steps"]
        counters["error_steps"] += counters["refining_vibe_steps"]
    return records, counters

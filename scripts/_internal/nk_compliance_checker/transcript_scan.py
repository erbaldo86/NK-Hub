# -*- coding: utf-8 -*-
"""Scansione transcript e raccolta metriche per nk_compliance_checker."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import ONBOARDING_TRIGGERS, VERSION
from _internal.nk_common.paths import reconfigure_streams
from _internal.nk_common.transcript_io import strip_antigravity_envelope

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

CANONICAL_AP_TABLE = _tt.CANONICAL_AP_TABLE
DIRECT_AUDIT_TOOLS = _tt.DIRECT_TOOLS
DELEGATION_TOOLS = _tt.DELEGATION_TOOLS
READ_FILE_TOOLS = _tt.READ_FILE_TOOLS
_has_missing_path_error = _tt._has_missing_path_error
_inspect_record_blind_reads_and_bursts = _tt._inspect_record_blind_reads_and_bursts
_pop_correlated_tool_call = _tt._pop_correlated_tool_call
classify_transcript_record = _tt.classify_transcript_record
clean_tool_path = _tt.clean_tool_path
clean_tool_str = _tt.clean_tool_str
discover_active_main_transcript = _tt.discover_active_main_transcript
extract_command_exit_code = _tt.extract_command_exit_code
extract_tool_args = _tt.extract_tool_args
extract_tool_name = _tt.extract_tool_name
is_read_file_output = _tt.is_read_file_output
is_subagent_transcript_file = _tt.is_subagent_transcript_file
is_user_turn_record = _tt.is_user_turn_record
load_transcript_records = _tt.load_transcript_records

COMPLIANCE_CHECKER_VERSION: str = VERSION
DDI_DIRECT_STREAK_LIMIT: int = 12
SESSION_TELEMETRY_MAX_SKEW_SECONDS: float = 7200.0
_CONVERGED_JSON_RE = re.compile(r'"(?:status|verdict)"\s*:\s*"CONVERGED_OPTIMAL"')

EXEMPT_WRITE_MARKERS = (
    ".staging/", "/.staging/", "brain/", "/.gemini/antigravity/brain/",
    "scratch/", "nk_genome/", "nk_tracking/", "appdata/local/temp",
    "/temp/", "%temp%", "nk_sandbox_", "nk_diagnostics",
)

_EXEMPT_SHORT_PROMPTS = frozenset({
    "ok", "si", "sì", "procedi", "approvo", "confermo",
}) | frozenset(ONBOARDING_TRIGGERS)


def _is_subagent_transcript(transcript_path: Path) -> bool:
    """Verifica se un file transcript.jsonl appartiene a un sub-agente."""
    return is_subagent_transcript_file(Path(transcript_path))


def find_active_transcript() -> Optional[Path]:
    """Individua il transcript attivo dell'Agente Principale."""
    return discover_active_main_transcript()


def _is_production_code_write(target_file: str) -> bool:
    """Determina se una scrittura riguarda codice applicativo o di produzione."""
    cleaned = clean_tool_path(target_file)
    if not cleaned:
        return False
    norm = cleaned.replace("\\", "/").lower()
    if "prod_src" in norm:
        return True
    if any(marker in norm for marker in EXEMPT_WRITE_MARKERS):
        return False
    if norm.endswith((".md", ".txt", ".jsonl")) or any(tok in norm for tok in ("benchmark_", "reports_and_briefs")):
        return False
    return True


def _is_external_unstage_write(target_or_cmd: str, is_command: bool = False) -> bool:
    """Rileva scritture dirette verso NK_External_Projects fuori da .staging/."""
    cleaned = clean_tool_str(target_or_cmd) if is_command else clean_tool_path(target_or_cmd)
    if not cleaned:
        return False
    norm = cleaned.replace("\\", "/").lower()
    if "nk_external_projects/" not in norm:
        return False
    if ".staging/" in norm or "/.staging" in norm or "win32_2pc_engine.py" in norm:
        return False
    if not is_command:
        return True
    readonly_tokens = (
        "pytest", "rsi_convergence_engine.py", "ast_guard_validator.py",
        "external_project_scaffolder.py --retrofit", "nk_transcript_tools.py",
    )
    if any(tok in norm for tok in readonly_tokens):
        return False
    write_indicators = (
        "src_app/", "tests/", "checkpoint_", "patch_notes.md", "update_", "migrate_",
        "set-content", "out-file", "copy-item", "remove-item",
    )
    return any(ind in norm for ind in write_indicators)


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


def _is_verified_converged_tool_output(
    content_text: str, corr_cmd: str, exit_val: Optional[int]
) -> bool:
    """Rileva CONVERGED_OPTIMAL solo da output tool strutturati validi."""
    if exit_val is not None and exit_val != 0:
        return False
    if _CONVERGED_JSON_RE.search(content_text):
        return True
    cmd_low = (corr_cmd or "").lower()
    return ("rsi_convergence_engine.py" in cmd_low or "auto_heal_pipeline.py" in cmd_low) and "CONVERGED_OPTIMAL" in content_text


def scan_transcript_metrics(transcript_file: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scansiona i record del transcript raccogliendo i contatori operativi."""
    records = load_transcript_records(transcript_file, only_after_last_turn=False, hydrate_truncated=True)
    counters: Dict[str, Any] = {
        "total_steps": len(records), "total_tool_calls": 0, "polling_calls": 0,
        "subagents_invoked": 0, "subagents_polled": 0, "write_calls": 0, "code_write_calls": 0,
        "external_unstage_writes": 0, "error_steps": 0, "command_error_steps": 0,
        "refining_vibe_steps": 0, "blind_read_errors": 0, "write_burst_steps": 0,
        "saw_converged_optimal": False, "max_direct_tool_calls_streak": 0,
        "healing_loop_executed": False, "ast_guard_executed": False, "win32_2pc_executed": False,
        "bootstrap_executed": False, "meta_prompt_gate_executed": False, "has_non_exempt_user_turn": False,
    }
    current_direct_streak = 0
    pending_tool_calls: List[Dict[str, Any]] = []

    for step_num, data in enumerate(records, start=1):
        cat = classify_transcript_record(data)
        step_has_error = str(data.get("status", "")).upper() == "ERROR"
        if step_has_error:
            counters["error_steps"] += 1

        content_text = str(data.get("content", "") or data.get("output", "") or json.dumps(data, ensure_ascii=False))
        calls = data.get("tool_calls", []) or []
        if cat in ("USER", "SYSTEM"):
            pending_tool_calls.clear()

        corr_tool = corr_cmd = ""
        if cat == "TOOL" and not calls:
            corr_call = _pop_correlated_tool_call(pending_tool_calls, data)
            corr_tool = extract_tool_name(corr_call)
            corr_args = extract_tool_args(corr_call)
            corr_cmd = clean_tool_str(corr_args.get("CommandLine") or corr_args.get("command") or "")
            if corr_tool in READ_FILE_TOOLS and _has_missing_path_error(str(data.get("status", "")), content_text):
                counters["blind_read_errors"] += 1

        has_inline_tool_out = bool(data.get("output") or data.get("tool_output") or data.get("tool_results"))
        if has_inline_tool_out and calls and not corr_tool:
            for call_item in calls:
                cand_name = extract_tool_name(call_item)
                if cand_name:
                    corr_tool = cand_name
                    cand_args = extract_tool_args(call_item)
                    corr_cmd = clean_tool_str(cand_args.get("CommandLine") or cand_args.get("command") or "")
                    break

        if (cat == "TOOL" or has_inline_tool_out) and not is_read_file_output(content_text, correlated_tool=corr_tool):
            exit_val = extract_command_exit_code(content_text, correlated_tool=corr_tool)
            if exit_val is not None and exit_val != 0:
                err_kind = _is_exempt_diagnostic_nonzero(content_text)
                if err_kind == "INTERMEDIATE_REFINING":
                    counters["refining_vibe_steps"] += 1
                elif err_kind == "REAL_ERROR":
                    counters["command_error_steps"] += 1
                    if not step_has_error:
                        counters["error_steps"] += 1
            elif (not corr_tool or corr_tool == "run_command") and _is_verified_converged_tool_output(content_text, corr_cmd, exit_val):
                counters["saw_converged_optimal"] = True

        if cat in ("USER", "SYSTEM"):
            if is_user_turn_record(data):
                stripped_user = strip_antigravity_envelope(content_text).strip()
                norm_user = " ".join(re.sub(r"[^\w\s]|_", " ", stripped_user.lower()).split())
                if (
                    stripped_user
                    and not stripped_user.startswith("<CONTEXT_SUMMARY>")
                    and stripped_user.lower() not in _EXEMPT_SHORT_PROMPTS
                    and norm_user not in _EXEMPT_SHORT_PROMPTS
                ):
                    counters["has_non_exempt_user_turn"] = True
                if step_num > 1:
                    current_direct_streak = 0
            continue

        if cat == "TOOL" and not calls:
            continue

        pending_tool_calls = [c for c in calls if isinstance(c, dict)] if calls else []
        b_err, w_burst = _inspect_record_blind_reads_and_bursts(data, calls)
        counters["blind_read_errors"] += b_err
        counters["write_burst_steps"] += w_burst

        step_direct_calls = 0
        step_has_delegation = False
        for call in calls:
            counters["total_tool_calls"] += 1
            tname = extract_tool_name(call)
            args = extract_tool_args(call)
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
            elif tname in ("write_to_file", "write_file", "replace_file_content", "edit_file", "notebook_edit"):
                counters["write_calls"] += 1
                target_f = clean_tool_path(
                    args.get("TargetFile") or args.get("Path") or args.get("AbsolutePath") or args.get("NotebookPath") or args.get("file") or ""
                )
                if _is_external_unstage_write(target_f, is_command=False):
                    counters["external_unstage_writes"] += 1
                    counters["code_write_calls"] += 1
                elif _is_production_code_write(target_f):
                    counters["code_write_calls"] += 1
            elif tname == "run_command":
                cmd = clean_tool_str(args.get("CommandLine") or args.get("command") or "")
                if any(s in cmd for s in ("invisible_healing_loop.py", "auto_heal_pipeline.py", "rsi_convergence_engine.py")):
                    counters["healing_loop_executed"] = True
                if "ast_guard_validator.py" in cmd:
                    counters["ast_guard_executed"] = True
                if "win32_2pc_engine.py" in cmd:
                    counters["win32_2pc_executed"] = True
                if "nk_session_bootstrap.py" in cmd:
                    counters["bootstrap_executed"] = True
                if "vibe_sprint_router.py" in cmd and "--meta-prompt-gate" in cmd:
                    counters["meta_prompt_gate_executed"] = True
                if _is_external_unstage_write(cmd, is_command=True):
                    counters["external_unstage_writes"] += 1

        if step_has_delegation or (is_user_turn_record(data) and step_num > 1):
            current_direct_streak = 0
        elif step_direct_calls > 0:
            current_direct_streak += step_direct_calls
            counters["max_direct_tool_calls_streak"] = max(counters["max_direct_tool_calls_streak"], current_direct_streak)

    if counters["refining_vibe_steps"] > 0 and not counters["saw_converged_optimal"]:
        counters["command_error_steps"] += counters["refining_vibe_steps"]
        counters["error_steps"] += counters["refining_vibe_steps"]

    return records, counters

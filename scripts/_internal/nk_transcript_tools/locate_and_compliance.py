# -*- coding: utf-8 -*-
"""Ricerca transcript, caricamento record e analisi compliance per nk_transcript_tools."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from _internal.nk_transcript_tools.constants import (
    INTENT_BRIEF_ID_RE,
    _DELEGATION_TOOLS,
    _DIRECT_TOOLS,
    _READ_FILE_TOOLS,
    _READONLY_CMD_MARKERS,
    _SAFE_WRITE_MARKERS,
    _SCRIPT_RE,
    _WRITE_BURST_TOOLS,
    _WRITE_CMD_RE,
    _get_runtime_temp_markers,
    _has_missing_path_error,
    classify_transcript_record,
    clean_tool_path,
    clean_tool_str,
    extract_tool_args,
    extract_tool_name,
)
from _internal.nk_transcript_tools.locate_helper import (
    count_transcript_steps,
    discover_active_main_transcript,
    is_subagent_transcript_file,
    load_transcript_records,
    locate_transcript,
    parse_transcript_events,
)
from _internal.nk_transcript_tools.prompt_and_ste100 import verify_ste100_compliance

_ONLINE_TARGET_RE = re.compile(r"(?:^|[\s\"'=/(])nk\s+proget/+online(?:$|[\s\"'/,;)\]])")
_LOCALE_TARGET_RE = re.compile(r"(?:^|[\s\"'=/(])nk\s+proget/+locale(?:/|$|[\s\"',;)\]])")
_ONLINE_FORCE_TOOLS = ("win32_2pc_engine", "external_project_scaffolder")
_ONLINE_GIT_MUTATE_RE = re.compile(r"\bgit\s+(?:add|commit|push|reset|checkout|clean)\b")


def _is_unstage_file_write_target(tf: str, safe_write_markers: Sequence[str]) -> bool:
    """Verifica se un target file viola .staging/ o punta al mirror NK Proget/Online."""
    if _ONLINE_TARGET_RE.search(tf):
        return True
    return bool(tf) and not any(m in tf for m in safe_write_markers)


def _is_unstage_external_cmd_write(cmd: str) -> bool:
    """Rileva comandi CLI mutanti verso NK Proget/Online, Locale o NK_External_Projects."""
    cmd_low = cmd.replace("\\", "/").lower()
    if _ONLINE_TARGET_RE.search(cmd_low):
        if any(tok in cmd_low for tok in _ONLINE_FORCE_TOOLS) or _ONLINE_GIT_MUTATE_RE.search(cmd_low):
            return True
        return not any(ro in cmd_low for ro in _READONLY_CMD_MARKERS) and bool(_WRITE_CMD_RE.search(cmd))
    is_loc_or_ext = "nk_external_projects/" in cmd_low or bool(_LOCALE_TARGET_RE.search(cmd_low))
    if not is_loc_or_ext or ".staging" in cmd_low:
        return False
    return not any(ro in cmd_low for ro in _READONLY_CMD_MARKERS) and bool(_WRITE_CMD_RE.search(cmd))


def _inspect_record_blind_reads_and_bursts(
    rec: Dict[str, Any], calls: Sequence[Dict[str, Any]]
) -> Tuple[int, int]:
    """Calcola errori di lettura alla cieca inline e burst di scrittura."""
    rec_status = str(rec.get("status") or "").upper()
    rec_txt = str(rec.get("content") or rec.get("output") or "")
    has_inline_output = bool(rec.get("output") or rec.get("tool_output") or rec_status == "ERROR")
    has_missing_err = has_inline_output and _has_missing_path_error(rec_status, rec_txt)
    read_calls = sum(1 for c in calls if extract_tool_name(c) in _READ_FILE_TOOLS)
    write_calls = sum(1 for c in calls if extract_tool_name(c) in _WRITE_BURST_TOOLS)
    return (1 if (has_missing_err and read_calls > 0) else 0), (1 if write_calls >= 4 else 0)


def analyze_compliance(transcript_path: Path) -> Dict[str, Any]:
    """Analizza un transcript calcolando streak, burst, blind-read e metriche."""
    if not transcript_path.is_file():
        return {"passed": False, "error": f"Missing transcript: {transcript_path}"}

    events = parse_transcript_events(
        transcript_path, only_after_last_turn=False, hydrate_truncated=True
    )
    safe_write_markers = (*_SAFE_WRITE_MARKERS, *_get_runtime_temp_markers())
    max_streak = cur_streak = delegations = ext_writes = 0
    polling_list_calls = oversized_swarm_messages = 0
    silent_l0_ask_question_calls = visible_l0_ask_question_calls = 0
    blind_read_errors = write_burst_steps = 0
    turn_has_visible_l0 = prev_was_poll = False
    scripts_seen: List[str] = []
    intent_briefs_seen: List[str] = []
    last_model_text = ""

    for ev in events:
        cat = ev["category"]
        is_turn_boundary = ev["is_turn_boundary"]
        is_planner_step = cat == "MODEL"
        content = ev["content"]
        content_stripped = content.strip()

        if is_planner_step and content_stripped:
            last_model_text = content
            for ib_match in INTENT_BRIEF_ID_RE.findall(content_stripped):
                if ib_match not in intent_briefs_seen:
                    intent_briefs_seen.append(ib_match)
            content_low = content_stripped.lower()
            if INTENT_BRIEF_ID_RE.search(content_stripped) or any(
                m in content_low for m in ("livello 0", "meta-prompt", "specchio concettuale", "requisiti tracciabili")
            ):
                turn_has_visible_l0 = True

        if is_turn_boundary:
            prev_was_poll = False
            turn_has_visible_l0 = False

        calls = ev["calls"]
        if cat == "TOOL" and not calls:
            if ev["corr_tool"] in _READ_FILE_TOOLS:
                if _has_missing_path_error(ev["status"], content):
                    blind_read_errors += 1
            continue

        b_err, w_burst = _inspect_record_blind_reads_and_bursts(ev["record"], calls)
        blind_read_errors += b_err
        write_burst_steps += w_burst
        step_delegated = False
        step_direct = 0

        for call in calls:
            tname = extract_tool_name(call)
            args = extract_tool_args(call)
            act_val = clean_tool_path(args.get("Action") or args.get("action") or "").lower()
            is_poll_call = (tname == "manage_subagents" and act_val == "list") or (tname == "manage_task" and act_val == "status")
            if is_poll_call:
                if prev_was_poll:
                    polling_list_calls += 1
                prev_was_poll = True
            elif tname:
                prev_was_poll = False

            if tname == "ask_question" and is_planner_step:
                if len(content_stripped) == 0 and not turn_has_visible_l0:
                    silent_l0_ask_question_calls += 1
                else:
                    visible_l0_ask_question_calls += 1
                    turn_has_visible_l0 = True

            if tname == "send_message":
                msg_body = clean_tool_str(args.get("Message") or args.get("message") or args.get("content") or "")
                if len(msg_body) > 1800:
                    oversized_swarm_messages += 1

            if tname in _DELEGATION_TOOLS:
                step_delegated = True
                if tname == "invoke_subagent":
                    delegations += 1
            elif tname in _DIRECT_TOOLS:
                step_direct += 1

            if tname in ("write_to_file", "write_file", "replace_file_content", "edit_file", "notebook_edit"):
                raw_tf = args.get("TargetFile") or args.get("Path") or args.get("AbsolutePath") or args.get("NotebookPath") or args.get("file") or ""
                tf = clean_tool_path(raw_tf).replace("\\", "/").lower()
                if _is_unstage_file_write_target(tf, safe_write_markers):
                    ext_writes += 1
            elif tname == "run_command":
                cmd = clean_tool_str(args.get("CommandLine") or args.get("command") or "")
                for sm in _SCRIPT_RE.findall(cmd):
                    if sm not in scripts_seen:
                        scripts_seen.append(sm)
                if _is_unstage_external_cmd_write(cmd):
                    ext_writes += 1

        if step_delegated or is_turn_boundary:
            cur_streak = 0
        elif step_direct > 0:
            cur_streak += step_direct
            max_streak = max(max_streak, cur_streak)

    ste_final = verify_ste100_compliance(last_model_text, max_sentence_words=20)
    long_sentences = sum(1 for v in ste_final["violations"] if "Frase troppo lunga" in v)
    return {
        "passed": max_streak <= 12 and ext_writes == 0 and oversized_swarm_messages == 0 and polling_list_calls == 0,
        "max_consecutive_direct_tools": max_streak,
        "subagent_delegations": delegations,
        "external_writes_outside_staging": ext_writes,
        "polling_list_calls": polling_list_calls,
        "oversized_swarm_messages": oversized_swarm_messages,
        "silent_l0_ask_question_calls": silent_l0_ask_question_calls,
        "visible_l0_ask_question_calls": visible_l0_ask_question_calls,
        "blind_read_errors": blind_read_errors,
        "write_burst_steps": write_burst_steps,
        "nk_scripts_invoked": scripts_seen,
        "intent_brief_ids": intent_briefs_seen,
        "unverified_final_sentences_over_20_words": long_sentences,
    }


__all__ = [
    "_inspect_record_blind_reads_and_bursts",
    "analyze_compliance",
    "count_transcript_steps",
    "discover_active_main_transcript",
    "is_subagent_transcript_file",
    "load_transcript_records",
    "locate_transcript",
    "parse_transcript_events",
]

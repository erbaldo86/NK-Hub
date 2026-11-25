# -*- coding: utf-8 -*-
"""FSM evidenze per-target per nk_transcript_tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_transcript_tools.constants import (
    _CLAIM_RE,
    _EXIT_ZERO_RE,
    _PASS_FALSE_RE,
    _PASS_TRUE_RE,
    _VERIFICATION_TARGETS,
    _strip_claim_code_spans,
    classify_transcript_record,
    clean_tool_str,
    extract_command_exit_code,
    extract_tool_args,
    extract_tool_name,
    is_read_file_output,
)
from _internal.nk_transcript_tools.locate_and_compliance import (
    load_transcript_records,
    parse_transcript_events,
)


def _classify_command_targets(command_line: str) -> List[str]:
    """Associa una riga di comando invocata ai target canonici della FSM evidenze."""
    low = (command_line or "").lower()
    matched = [tgt for tgt in _VERIFICATION_TARGETS if tgt in low]
    return matched if matched else ["general_cmd"]


def check_evidence(
    transcript_path: Optional[Path] = None, message: str = ""
) -> Tuple[Dict[str, Any], int]:
    """Verifica con FSM per-target che i claim abbiano evidenze reali risolte."""
    events: List[Dict[str, Any]] = []
    if transcript_path and transcript_path.is_file():
        events = parse_transcript_events(
            transcript_path, only_after_last_turn=True, hydrate_truncated=True
        )

    target_states: Dict[str, Dict[str, Any]] = {}
    verified_exit_zero = False
    last_command_failed = False
    final_msg = message

    for ev in events:
        cat = ev["category"]
        has_inline_tool_payload = ev["has_inline_tool_out"]

        if cat == "MODEL":
            if not message and ev["content"]:
                final_msg = ev["content"]
            if not has_inline_tool_payload:
                continue

        corr_tool = ev["corr_tool"]
        corr_cmd = ev["corr_cmd"]
        txt = ev["output_text"]

        if is_read_file_output(txt, correlated_tool=corr_tool):
            continue
        if corr_tool and corr_tool != "run_command":
            continue

        exit_code = extract_command_exit_code(txt, correlated_tool=corr_tool)
        has_exit_zero = (exit_code == 0) or bool(_EXIT_ZERO_RE.search(txt))
        has_exit_nonzero = exit_code is not None and exit_code != 0
        has_pass_false = bool(_PASS_FALSE_RE.search(txt))
        has_pass_true = bool(_PASS_TRUE_RE.search(txt)) and not has_pass_false

        if not (has_exit_zero or has_exit_nonzero or has_pass_false or has_pass_true):
            continue

        targets = _classify_command_targets(corr_cmd)
        cmd_failed = has_exit_nonzero or has_pass_false

        if cmd_failed:
            last_command_failed = True
            for tgt in targets:
                prev_runs = int(target_states.get(tgt, {}).get("runs", 0))
                target_states[tgt] = {
                    "passed": False,
                    "last_exit_code": exit_code if exit_code is not None else 1,
                    "unresolved_failure": True,
                    "unresolved_pass_false": has_pass_false,
                    "runs": prev_runs + 1,
                }
        else:
            last_command_failed = False
            if has_exit_zero:
                verified_exit_zero = True
            for tgt in targets:
                prev_runs = int(target_states.get(tgt, {}).get("runs", 0))
                target_states[tgt] = {
                    "passed": True,
                    "last_exit_code": 0,
                    "unresolved_failure": False,
                    "unresolved_pass_false": False,
                    "runs": prev_runs + 1,
                }

    unresolved_targets = [
        tgt for tgt, st in target_states.items() if st.get("unresolved_failure")
    ]
    unresolved_pass_false = any(
        bool(st.get("unresolved_pass_false")) for st in target_states.values()
    ) or len(unresolved_targets) > 0

    claims = [m.group(0) for m in _CLAIM_RE.finditer(_strip_claim_code_spans(final_msg or ""))]
    if last_command_failed or len(unresolved_targets) > 0:
        passed = False
    elif claims:
        passed = verified_exit_zero and not unresolved_pass_false
    else:
        passed = True

    return {
        "passed": passed,
        "claims_detected": claims,
        "verified_exit_zero": verified_exit_zero and not last_command_failed,
        "unresolved_pass_false": unresolved_pass_false,
        "unresolved_targets": unresolved_targets,
        "last_command_failed": last_command_failed,
        "target_states": target_states,
    }, (0 if passed else 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v6.4.0-Carbon: Suite di Stress Test Multi-Vettore in Shadow Sandbox.
Modulo: tests/stress/test_real_sandbox_stress.py.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest

try:
    from conftest import is_cov_instrumented, load_nk_script_module
except ImportError:
    from tests.conftest import is_cov_instrumented, load_nk_script_module

pytestmark = [pytest.mark.integration, pytest.mark.stress]

_sentry_mod = load_nk_script_module("nk_context_sentry")
_compliance_mod = load_nk_script_module("nk_compliance_checker")
_auto_heal_mod = load_nk_script_module("auto_heal_pipeline")
load_nk_script_module("sbfl_pytest_bridge")
from _internal.sbfl_pytest_bridge.frame_extractor import _parse_traceback_diagnostics  # noqa: E402

NKContextSentry = _sentry_mod.NKContextSentry
NKComplianceChecker = _compliance_mod.NKComplianceChecker


@pytest.fixture
def shadow_sandbox() -> Generator[Path, None, None]:
    """Fornisce una shadow sandbox reale isolata in directory temporanea."""
    sandbox_path = Path(tempfile.gettempdir()) / f"nk_stress_{uuid.uuid4().hex[:8]}"
    sandbox_path.mkdir(parents=True, exist_ok=True)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("NK_MODEL_PROFILE", raising=False)
            yield sandbox_path
    finally:
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path, ignore_errors=True)


def _append_escalator_steps(
    transcript_file: Path, start_step: int, end_step: int, label: str, mode: str = "a"
) -> None:
    """Appende o scrive un blocco di record sintetici nel transcript di stress."""
    records: List[Dict[str, Any]] = []
    for step in range(start_step, end_step + 1):
        records.append(
            {
                "step_index": step,
                "source": "MODEL" if step % 2 == 0 else "USER_EXPLICIT",
                "content": f"Step {step} execution log: {label}.",
                "tool_calls": [{"name": "invoke_subagent"}] if step % 5 == 0 else [],
            }
        )
    with open(transcript_file, mode, encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_vector_1_swarm_flooder(shadow_sandbox: Path):
    """V1: Swarm Flooder, rileva messaggi oltre 2000 caratteri nello stream."""
    transcript_file = shadow_sandbox / "swarm_flooder_transcript.jsonl"
    records = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Deploy swarm tasks", "tool_calls": []},
        {"step_index": 2, "source": "MODEL", "content": "Invoking workers", "tool_calls": [{"name": "invoke_subagent"}]},
        {"step_index": 3, "source": "SYSTEM", "content": "[Message] Worker 0: normal status update with 100 characters.", "tool_calls": []},
        {"step_index": 4, "source": "SYSTEM", "content": f"[Message] Worker 1 diagnostic flood: {'A' * 3450}", "tool_calls": []},
        {"step_index": 5, "source": "SYSTEM", "content": f"<SYSTEM_MESSAGE>\n[Message] Worker 2 memory dump: {'B' * 6950}\n</SYSTEM_MESSAGE>", "tool_calls": []},
        {"step_index": 6, "source": "SYSTEM", "content": f"[Message] Worker 3 raw network trace: {'C' * 19950}", "tool_calls": []},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    sentry = NKContextSentry(workspace_root=shadow_sandbox)
    sentry_res = sentry.analyze_transcript(transcript_file)
    assert sentry_res["step_count"] == 6
    assert sentry_res["swarm_hygiene_violations_count"] == 3

    checker = NKComplianceChecker(workspace_root=shadow_sandbox)
    comp_res = checker.audit_transcript(transcript_file)
    penalties = comp_res.get("penalties", [])
    assert any("Swarm hygiene violation: 3 oversized" in p for p in penalties)
    assert comp_res["scores"]["procedural_score"] <= 55


def test_vector_2_monolithic_spammer(shadow_sandbox: Path):
    """V2: Monolithic Spammer, 15 tool diretti consecutivi senza delega attivano l'allerta DDI."""
    transcript_file = shadow_sandbox / "monolithic_spammer_transcript.jsonl"
    records = [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Run deep audit directly", "tool_calls": []}]
    tool_names = ["write_file", "run_command", "replace_file_content", "edit_file", "run_command"]
    for i in range(2, 17):
        tname = tool_names[(i - 2) % len(tool_names)]
        records.append(
            {
                "step_index": i,
                "source": "MODEL",
                "content": f"Step {i}: executing direct tool {tname}",
                "tool_calls": [{"name": tname, "args": {"file": f"test_{i}.py"}}],
            }
        )
    with open(transcript_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    sentry = NKContextSentry(workspace_root=shadow_sandbox)
    sentry_res = sentry.analyze_transcript(transcript_file)
    assert sentry_res["max_consecutive_direct_audit"] >= 15

    checker = NKComplianceChecker(workspace_root=shadow_sandbox)
    comp_res = checker.audit_transcript(transcript_file)
    penalties = comp_res.get("penalties", [])
    assert any("Objective DDI violation: 15 consecutive direct tools" in p for p in penalties)
    assert comp_res["scores"]["procedural_score"] <= 80


def test_vector_3_rapid_step_escalator(shadow_sandbox: Path):
    """V3: Rapid Step Escalator, verifica le transizioni GREEN, YELLOW e RED sotto soglia SLA."""
    transcript_file = shadow_sandbox / "step_escalator_transcript.jsonl"
    sentry = NKContextSentry(workspace_root=shadow_sandbox)
    max_ms = 150.0 if is_cov_instrumented() else 50.0

    _append_escalator_steps(transcript_file, 1, 65, "normal prompt operation and validation", mode="w")
    t0 = time.perf_counter()
    res_green = sentry.analyze_transcript(transcript_file)
    dur_green_ms = (time.perf_counter() - t0) * 1000
    assert dur_green_ms < max_ms, f"Sentry took {dur_green_ms} ms (SLA < {max_ms} ms)"
    assert res_green["status"] == "GREEN" and res_green["step_count"] == 65

    _append_escalator_steps(transcript_file, 66, 85, "medium prompt operation")
    t1 = time.perf_counter()
    res_yellow = sentry.analyze_transcript(transcript_file)
    dur_yellow_ms = (time.perf_counter() - t1) * 1000
    assert dur_yellow_ms < max_ms, f"Sentry took {dur_yellow_ms} ms (SLA < {max_ms} ms)"
    assert res_yellow["status"] == "YELLOW" and res_yellow["step_count"] == 85
    assert "Warning: Context saturation nearing threshold" in res_yellow["recommendation"]

    _append_escalator_steps(transcript_file, 86, 120, "heavy context accumulating across turns")
    t2 = time.perf_counter()
    res_red = sentry.analyze_transcript(transcript_file)
    dur_red_ms = (time.perf_counter() - t2) * 1000
    assert dur_red_ms < max_ms, f"Sentry took {dur_red_ms} ms (SLA < {max_ms} ms)"
    assert res_red["status"] == "RED" and res_red["step_count"] == 120
    assert "Critical saturation" in res_red["recommendation"]


def test_vector_3_rapid_step_escalator_profile_thresholds(
    shadow_sandbox: Path, monkeypatch: pytest.MonkeyPatch
):
    """V3b: Verifica il profilo standard vs carbon sui 120 step con monkeypatch.setenv."""
    transcript_file = shadow_sandbox / "step_escalator_profile.jsonl"
    _append_escalator_steps(transcript_file, 1, 120, "heavy context accumulating across turns", mode="w")

    monkeypatch.setenv("NK_MODEL_PROFILE", "standard")
    checker_std = NKComplianceChecker(workspace_root=shadow_sandbox)
    comp_res = checker_std.audit_transcript(transcript_file)
    assert comp_res["status"] == "FAIL"
    assert any("Critical context saturation (RED status)" in p for p in comp_res.get("penalties", []))

    monkeypatch.delenv("NK_MODEL_PROFILE", raising=False)
    checker_carbon = NKComplianceChecker(workspace_root=shadow_sandbox)
    comp_carbon_120 = checker_carbon.audit_transcript(transcript_file)
    assert not any(
        "Critical context saturation (RED status)" in p
        for p in comp_carbon_120.get("penalties", [])
    )


def _write_single_swarm_transcript(path: Path, body: str) -> None:
    """Scrive un transcript minimale con un messaggio swarm da analizzare."""
    records = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Inspect traceback", "tool_calls": []},
        {"step_index": 2, "source": "MODEL", "content": "Delegating", "tool_calls": [{"name": "invoke_subagent"}]},
        {"step_index": 3, "source": "SYSTEM", "content": f"[Message] Worker 0 traceback: {body}", "tool_calls": []},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _exercise_sentry_traceback_hygiene(
    sandbox_path: Path, tb_str: str, root_cause_msg: str
) -> None:
    """Esercita compressione head-tail e controlli Swarm Hygiene su Sentry e Compliance."""
    compressed = NKContextSentry.format_head_tail(tb_str, head_chars=400, tail_chars=800)
    assert len(compressed) < 2000
    assert "TRUNCATED BY NK-CONTEXT-SENTRY" in compressed
    assert root_cause_msg in compressed
    assert "Worker_Node_149_Failure" in compressed

    raw_tp = sandbox_path / "tb_raw_transcript.jsonl"
    comp_tp = sandbox_path / "tb_compressed_transcript.jsonl"
    _write_single_swarm_transcript(raw_tp, tb_str)
    _write_single_swarm_transcript(comp_tp, compressed)

    sentry = NKContextSentry(workspace_root=sandbox_path)
    checker = NKComplianceChecker(workspace_root=sandbox_path)
    assert sentry.analyze_transcript(raw_tp)["swarm_hygiene_violations_count"] == 1
    assert any(
        "Swarm hygiene violation: 1 oversized" in p
        for p in checker.audit_transcript(raw_tp).get("penalties", [])
    )
    assert sentry.analyze_transcript(comp_tp)["swarm_hygiene_violations_count"] == 0


def _exercise_autoheal_and_sbfl_traceback(
    sandbox_path: Path, tb_str: str, root_cause_msg: str
) -> None:
    """Esercita AutoHeal trim_code_slice_tokens, classify_failure e parser SBFL su tb_str."""
    tb_lines = tb_str.splitlines()
    root_line_idx = next(i + 1 for i, ln in enumerate(tb_lines) if root_cause_msg in ln)
    raw_slice = _auto_heal_mod.CodeSlice(
        start_line=1,
        end_line=len(tb_lines),
        target_line=root_line_idx,
        content=tb_str,
    )
    trimmed_slice, tok_cnt = _auto_heal_mod.trim_code_slice_tokens(raw_slice, max_tokens=80)
    assert 0 < tok_cnt <= 80
    assert len(trimmed_slice.content) < 2000
    assert root_cause_msg in trimmed_slice.content
    assert _auto_heal_mod.classify_failure(tb_str) == "RUNTIME_ERROR"

    pytest_lines = tb_lines + [
        f"{sandbox_path.as_posix()}/worker_node.py:42: ValueError",
        "> raise ValueError('Worker_Node_149_Failure')",
        f"E   ValueError: {root_cause_msg}",
    ]
    err_t, err_m, ordered_locs, _, _ = _parse_traceback_diagnostics(pytest_lines, "worker_node.py")
    assert err_t == "ValueError"
    assert root_cause_msg in err_m
    assert (f"{sandbox_path.as_posix()}/worker_node.py", 42) in ordered_locs


def test_vector_4_traceback_bomb():
    """V4: Traceback Bomb, comprime catene oltre 65 KB con tool reali preservando RootCauseError."""
    root_cause_msg = "RootCauseError: Critical hardware failure in TPU node accelerator"
    curr_exc: Exception = RuntimeError(root_cause_msg)
    for i in range(150):
        try:
            msg = f"Worker_Node_{i}_Failure: Distributed execution pipeline collapsed during chunk analysis {'#METADATA_FRAME_' * 30}"
            raise ValueError(msg) from curr_exc
        except ValueError as exc:
            curr_exc = exc

    tb_str = "".join(traceback.format_exception(type(curr_exc), curr_exc, curr_exc.__traceback__))
    assert len(tb_str) >= 65000
    with tempfile.TemporaryDirectory(prefix="nk_stress_v4_") as tmp_dir:
        sandbox_path = Path(tmp_dir)
        _exercise_sentry_traceback_hygiene(sandbox_path, tb_str, root_cause_msg)
        _exercise_autoheal_and_sbfl_traceback(sandbox_path, tb_str, root_cause_msg)


def test_vector_5_corrupted_transcript_and_ddi_tools(shadow_sandbox: Path):
    """V5: Verifica rilevamento transcript corrotto (ERROR), esenzione read_file e streak DDI write/edit/run."""
    corrupted_file = shadow_sandbox / "corrupted_transcript.jsonl"
    corrupted_file.write_text("{{{not_valid_json_line_1\nalso_corrupted_line_2\n", encoding="utf-8")

    sentry = NKContextSentry(workspace_root=shadow_sandbox)
    res_err = sentry.analyze_transcript(corrupted_file, actual_context_tokens=-50)
    assert res_err["status"] == "ERROR"
    assert res_err["actual_context_tokens"] == 0

    ddi_file = shadow_sandbox / "ddi_new_tools.jsonl"
    with open(ddi_file, "w", encoding="utf-8") as f:
        for idx, tname in enumerate(["read_file", "write_file", "edit_file", "run_command"], start=1):
            f.write(
                json.dumps(
                    {
                        "step_index": idx,
                        "source": "MODEL",
                        "content": f"step {idx}",
                        "tool_calls": [
                            {"name": tname, "args": {"AbsolutePath": "G:/Il mio Drive/Antigravity/NK_Hub/.staging/a.py"}}
                        ],
                    }
                )
                + "\n"
            )
    res_ddi = sentry.analyze_transcript(ddi_file)
    assert res_ddi["max_consecutive_direct_audit"] == 3

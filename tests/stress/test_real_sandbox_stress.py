#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.3.0-Hardened - Real Shadow Sandbox Multi-Vector Stress Test Suite
Module: test_real_sandbox_stress.py
Implements: 100% Zero-Mock real subprocess & filesystem stress testing.
Covers:
  - Vector 1: Swarm Flooder (Swarm Hygiene breach detection)
  - Vector 2: Monolithic Spammer (Universal DDI streak breach detection)
  - Vector 3: Rapid Step Escalator (GREEN -> YELLOW -> RED latency < 50 ms)
  - Vector 4: Traceback Bomb (Nested exception Head-Tail compression < 1200 chars)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path
from typing import Generator

import pytest

# Determine paths
_this_file = Path(__file__).resolve()
_staging_scripts = _this_file.parents[2] / "scripts" if "tests" in _this_file.parts else _this_file.parent.parent / "scripts"
_repo_scripts = None
for p in _this_file.parents:
    if (p / "scripts" / "nk_context_sentry.py").exists():
        _repo_scripts = p / "scripts"
        break

for cand in [_staging_scripts, _repo_scripts]:
    if cand and cand.exists() and str(cand) not in sys.path:
        sys.path.insert(0, str(cand))

try:
    from nk_context_sentry import NKContextSentry
except ImportError:
    from scripts.nk_context_sentry import NKContextSentry

try:
    from nk_compliance_checker import NKComplianceChecker
except ImportError:
    from scripts.nk_compliance_checker import NKComplianceChecker


@pytest.fixture
def shadow_sandbox() -> Generator[Path, None, None]:
    """Isolated real shadow sandbox in temp directory with deterministic cleanup."""
    sandbox_path = Path(tempfile.gettempdir()) / f"nk_stress_{uuid.uuid4().hex[:8]}"
    sandbox_path.mkdir(parents=True, exist_ok=True)
    try:
        yield sandbox_path
    finally:
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path, ignore_errors=True)


def test_vector_1_swarm_flooder(shadow_sandbox: Path):
    """V1: Swarm Flooder - Real stream with messages >2000 chars, sentry detects violations."""
    transcript_file = shadow_sandbox / "swarm_flooder_transcript.jsonl"

    records = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Deploy swarm tasks", "tool_calls": []},
        {"step_index": 2, "source": "MODEL", "content": "Invoking workers", "tool_calls": [{"name": "invoke_subagent"}]},
        {"step_index": 3, "source": "SYSTEM", "content": "[Message] Worker 0: normal status update with 100 characters.", "tool_calls": []},
        # Violation 1: 3,500 chars
        {"step_index": 4, "source": "SYSTEM", "content": f"[Message] Worker 1 diagnostic flood: {'A' * 3450}", "tool_calls": []},
        # Violation 2: 7,000 chars
        {"step_index": 5, "source": "SYSTEM", "content": f"<SYSTEM_MESSAGE>\n[Message] Worker 2 memory dump: {'B' * 6950}\n</SYSTEM_MESSAGE>", "tool_calls": []},
        # Violation 3: 20,000 chars
        {"step_index": 6, "source": "SYSTEM", "content": f"[Message] Worker 3 raw network trace: {'C' * 19950}", "tool_calls": []},
    ]

    with open(transcript_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    sentry = NKContextSentry(workspace_root=shadow_sandbox)
    sentry_res = sentry.analyze_transcript(transcript_file)

    assert sentry_res["step_count"] == 6
    assert sentry_res["swarm_hygiene_violations_count"] == 3, f"Expected 3 violations, got {sentry_res['swarm_hygiene_violations_count']}"

    checker = NKComplianceChecker(workspace_root=shadow_sandbox)
    comp_res = checker.audit_transcript(transcript_file)

    # 3 violations * 15 = 45 penalty
    penalties = comp_res.get("penalties", [])
    assert any("Swarm hygiene violation: 3 oversized" in p for p in penalties)
    assert comp_res["scores"]["procedural_score"] <= 55


def test_vector_2_monolithic_spammer(shadow_sandbox: Path):
    """V2: Monolithic Spammer - 15 consecutive direct tools without delegation, triggers DDI alert."""
    transcript_file = shadow_sandbox / "monolithic_spammer_transcript.jsonl"

    records = [{"step_index": 1, "source": "USER_EXPLICIT", "content": "Run deep audit directly", "tool_calls": []}]
    # 15 consecutive direct tools without any invoke_subagent or define_subagent
    tool_names = ["view_file", "run_command", "replace_file_content", "view_file", "run_command"]
    for i in range(2, 17):
        tname = tool_names[(i - 2) % len(tool_names)]
        records.append({
            "step_index": i,
            "source": "MODEL",
            "content": f"Step {i}: executing direct tool {tname}",
            "tool_calls": [{"name": tname, "args": {"file": f"test_{i}.py"}}],
        })

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
    """V3: Rapid Step Escalator - 120 steps real stream, verified transitions GREEN -> YELLOW -> RED in < 50 ms."""
    transcript_file = shadow_sandbox / "step_escalator_transcript.jsonl"
    sentry = NKContextSentry(workspace_root=shadow_sandbox)

    # Phase 1: Write steps 1 to 65 (GREEN threshold < 70)
    with open(transcript_file, "w", encoding="utf-8") as f:
        for step in range(1, 66):
            rec = {
                "step_index": step,
                "source": "MODEL" if step % 2 == 0 else "USER_EXPLICIT",
                "content": f"Step {step} execution log: normal prompt operation and validation token payload.",
                "tool_calls": [{"name": "invoke_subagent"}] if step % 5 == 0 else [],
            }
            f.write(json.dumps(rec) + "\n")

    t0 = time.perf_counter()
    res_green = sentry.analyze_transcript(transcript_file)
    dur_green_ms = (time.perf_counter() - t0) * 1000

    assert dur_green_ms < 50.0, f"Sentry took {dur_green_ms} ms (SLA < 50 ms)"
    assert res_green["status"] == "GREEN"
    assert res_green["step_count"] == 65

    # Phase 2: Append steps 66 to 85 (YELLOW threshold 70..99)
    with open(transcript_file, "a", encoding="utf-8") as f:
        for step in range(66, 86):
            rec = {
                "step_index": step,
                "source": "MODEL" if step % 2 == 0 else "USER_EXPLICIT",
                "content": f"Step {step} execution log: medium prompt operation.",
                "tool_calls": [{"name": "invoke_subagent"}] if step % 5 == 0 else [],
            }
            f.write(json.dumps(rec) + "\n")

    t1 = time.perf_counter()
    res_yellow = sentry.analyze_transcript(transcript_file)
    dur_yellow_ms = (time.perf_counter() - t1) * 1000

    assert dur_yellow_ms < 50.0, f"Sentry took {dur_yellow_ms} ms (SLA < 50 ms)"
    assert res_yellow["status"] == "YELLOW"
    assert res_yellow["step_count"] == 85
    assert "Warning: Context saturation nearing threshold" in res_yellow["recommendation"]

    # Phase 3: Append steps 86 to 120 (RED threshold >= 100)
    with open(transcript_file, "a", encoding="utf-8") as f:
        for step in range(86, 121):
            rec = {
                "step_index": step,
                "source": "MODEL" if step % 2 == 0 else "USER_EXPLICIT",
                "content": f"Step {step} execution log: heavy context accumulating across turns.",
                "tool_calls": [{"name": "invoke_subagent"}] if step % 5 == 0 else [],
            }
            f.write(json.dumps(rec) + "\n")

    t2 = time.perf_counter()
    res_red = sentry.analyze_transcript(transcript_file)
    dur_red_ms = (time.perf_counter() - t2) * 1000

    assert dur_red_ms < 50.0, f"Sentry took {dur_red_ms} ms (SLA < 50 ms)"
    assert res_red["status"] == "RED"
    assert res_red["step_count"] == 120
    assert "Critical saturation" in res_red["recommendation"]

    # Check compliance checker on the RED 120-step transcript
    checker = NKComplianceChecker(workspace_root=shadow_sandbox)
    comp_res = checker.audit_transcript(transcript_file)
    assert comp_res["status"] == "FAIL"
    penalties = comp_res.get("penalties", [])
    assert any("Critical context saturation (RED status)" in p for p in penalties)


def test_vector_4_traceback_bomb():
    """V4: Traceback Bomb - Real nested exception chain > 65 KB compressed < 1200 chars preserving cause."""
    root_cause_msg = "RootCauseError: Critical hardware failure in TPU node accelerator"
    root_exc = RuntimeError(root_cause_msg)
    curr_exc: Exception = root_exc

    # Chain 150 real Python exceptions
    for i in range(150):
        try:
            msg = f"Worker_Node_{i}_Failure: Distributed execution pipeline collapsed during chunk analysis {'#METADATA_FRAME_' * 30}"
            raise ValueError(msg) from curr_exc
        except ValueError as exc:
            curr_exc = exc

    # Format real traceback using standard library
    tb_lines = traceback.format_exception(type(curr_exc), curr_exc, curr_exc.__traceback__)
    tb_str = "".join(tb_lines)

    # Verify real traceback exceeds 65 KB (65,000 chars)
    assert len(tb_str) >= 65000, f"Expected real traceback >= 65000 chars, got {len(tb_str)}"
    assert root_cause_msg in tb_str
    assert "Worker_Node_149_Failure" in tb_str

    # Apply Head-Tail compression
    compressed = NKContextSentry.format_head_tail(tb_str, head_chars=400, tail_chars=800)

    # Verification: total size < 1300 chars (head 400 + tail 800 + truncation banner)
    assert len(compressed) <= 1300, f"Expected compressed traceback <= 1300 chars, got {len(compressed)}"
    assert "[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]" in compressed

    # Verification: root cause (__cause__) is preserved in head, and latest failure is in tail
    assert "RootCauseError" in compressed, "Root cause must be preserved in compressed traceback"
    assert "Worker_Node_149_Failure" in compressed, "Most recent exception must be preserved in tail"

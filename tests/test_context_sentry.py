#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for nk_context_sentry.py (Nexus Keystone v2.2.0-AntiSaturation)
Implements 100% Zero-Mock testing for Context Sentry Guard and Traffic-Light Status.
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    from scripts.nk_context_sentry import NKContextSentry
except ImportError:
    staging_scripts = Path(__file__).resolve().parent.parent / "scripts"
    if str(staging_scripts) not in sys.path:
        sys.path.insert(0, str(staging_scripts))
    from nk_context_sentry import NKContextSentry


def test_estimate_tokens():
    assert NKContextSentry.estimate_tokens("") == 0
    assert NKContextSentry.estimate_tokens("a") == 1
    assert NKContextSentry.estimate_tokens("12345678") == 2
    assert NKContextSentry.estimate_tokens("a" * 400) == 100


def test_format_head_tail():
    short_text = "Traceback (most recent call last):\n  File 'test.py', line 1\nValueError"
    assert NKContextSentry.format_head_tail(short_text) == short_text

    long_text = "HEAD_" + ("x" * 2000) + "_TAIL"
    compressed = NKContextSentry.format_head_tail(long_text, head_chars=10, tail_chars=10)
    assert compressed.startswith("HEAD_")
    assert compressed.endswith("_TAIL")
    assert "[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]" in compressed


def test_get_traffic_light_status():
    sentry = NKContextSentry()
    green = sentry.get_traffic_light_status(step_count=40, estimated_tokens=30000)
    assert green["status"] == "GREEN"

    yellow = sentry.get_traffic_light_status(step_count=85, estimated_tokens=90000)
    assert yellow["status"] == "YELLOW"

    red = sentry.get_traffic_light_status(step_count=105, estimated_tokens=150000)
    assert red["status"] == "RED"


def test_analyze_transcript_real(tmp_path):
    sentry = NKContextSentry()
    fake_transcript = tmp_path / "transcript.jsonl"

    lines = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Hello", "tool_calls": []},
        {"step_index": 2, "source": "MODEL", "content": "Hi", "tool_calls": [{"name": "view_file"}]},
        {"step_index": 3, "source": "MODEL", "content": "Checking", "tool_calls": [{"name": "run_command"}]},
        {"step_index": 4, "source": "SYSTEM", "content": "<SYSTEM_MESSAGE> " + ("a" * 2500) + " </SYSTEM_MESSAGE>"},
    ]
    with open(fake_transcript, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    res = sentry.analyze_transcript(fake_transcript)
    assert res["status"] == "GREEN"
    assert res["step_count"] == 4
    assert res["swarm_hygiene_violations_count"] == 1
    assert res["max_consecutive_direct_audit"] == 2


def test_cli_execution(tmp_path):
    fake_transcript = tmp_path / "transcript.jsonl"
    fake_transcript.write_text(json.dumps({"step_index": 1, "source": "USER", "content": "test"}) + "\n", encoding="utf-8")

    script_path = Path("scripts") / "nk_context_sentry.py"
    if not script_path.exists():
        script_path = Path(".staging") / "scripts" / "nk_context_sentry.py"
    cmd = [sys.executable, str(script_path), "--transcript", str(fake_transcript), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["step_count"] == 1

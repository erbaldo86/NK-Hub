#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per nk_context_sentry.py di Nexus Keystone v3.3.0.
Modulo: tests/test_context_sentry.py.
Valida la stima token, la compressione Head-Tail, le soglie GT-01/GT-04 e l'analisi transcript.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import nk_context_sentry as sentry_mod
    from scripts.nk_context_sentry import NKContextSentry
except ImportError:
    staging_scripts = Path(__file__).resolve().parent.parent / "scripts"
    if str(staging_scripts) not in sys.path:
        sys.path.insert(0, str(staging_scripts))
    import nk_context_sentry as sentry_mod  # type: ignore[no-redef]
    from nk_context_sentry import NKContextSentry  # type: ignore[no-redef]


def test_estimate_tokens() -> None:
    """1. Verifica la stima token, il fallback Head-Tail e le soglie semaforiche GT-01."""
    assert NKContextSentry.estimate_tokens("") == 0
    assert NKContextSentry.estimate_tokens("a") == 1
    assert NKContextSentry.estimate_tokens("12345678") == 2
    assert NKContextSentry.estimate_tokens("a" * 400) == 100

    short_text = "Traceback (most recent call last):\n  File 'test.py', line 1\nValueError"
    assert NKContextSentry.format_head_tail(short_text) == short_text

    long_text = "HEAD_" + ("x" * 2000) + "_TAIL"
    compressed = NKContextSentry.format_head_tail(
        long_text, head_chars=10, tail_chars=10
    )
    assert compressed.startswith("HEAD_")
    assert compressed.endswith("_TAIL")
    assert "[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]" in compressed

    sentry_std = NKContextSentry(profile="standard")
    assert sentry_std.GREEN_STEP_THRESHOLD == 70
    assert sentry_std.RED_STEP_THRESHOLD == 100
    assert (
        sentry_std.get_traffic_light_status(step_count=40, estimated_tokens=30000)[
            "status"
        ]
        == "GREEN"
    )
    assert (
        sentry_std.get_traffic_light_status(step_count=85, estimated_tokens=90000)[
            "status"
        ]
        == "YELLOW"
    )
    assert (
        sentry_std.get_traffic_light_status(step_count=105, estimated_tokens=150000)[
            "status"
        ]
        == "RED"
    )

    sentry_argon = NKContextSentry(profile="argon")
    assert (
        sentry_argon.get_traffic_light_status(step_count=120, estimated_tokens=90000)[
            "status"
        ]
        == "GREEN"
    )
    assert (
        sentry_argon.get_traffic_light_status(step_count=180, estimated_tokens=150000)[
            "status"
        ]
        == "YELLOW"
    )
    assert (
        sentry_argon.get_traffic_light_status(step_count=260, estimated_tokens=260000)[
            "status"
        ]
        == "RED"
    )


def test_analyze_transcript_real(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """2. Verifica l'analisi reale di transcript.jsonl e l'esecuzione CLI JSON."""
    sentry = NKContextSentry(workspace_root=tmp_path)
    fake_transcript = tmp_path / "transcript.jsonl"

    lines = [
        {
            "step_index": 1,
            "source": "USER_EXPLICIT",
            "content": "Hello",
            "tool_calls": [],
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "content": "Hi",
            "tool_calls": [{"name": "view_file"}],
        },
        {
            "step_index": 3,
            "source": "MODEL",
            "content": "Checking",
            "tool_calls": [{"name": "run_command"}],
        },
        {
            "step_index": 4,
            "source": "SYSTEM",
            "content": "<SYSTEM_MESSAGE> " + ("a" * 2500) + " </SYSTEM_MESSAGE>",
        },
    ]
    with open(fake_transcript, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    res = sentry.analyze_transcript(fake_transcript)
    assert res["status"] == "GREEN"
    assert res["step_count"] == 4
    assert res["swarm_hygiene_violations_count"] == 1
    assert res["max_consecutive_direct_audit"] == 2

    monkeypatch.setattr(
        sys,
        "argv",
        ["nk_context_sentry.py", "--transcript", str(fake_transcript), "--json"],
    )
    sentry_mod.main()
    cli_out = json.loads(capsys.readouterr().out)
    assert cli_out["step_count"] == 4

# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per Sentinel, Swarm Messenger, Handoff e Auto-Inning (v3.3.0).
Modulo: tests/test_active_sentinel_suite.py.
Valida le guardie GT-02 e GT-04 e l'esecuzione deterministica di handoff e auto-inning.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from scripts import nk_auto_inning
from scripts import nk_session_handoff
from scripts.nk_active_runtime_sentinel import calculate_state, run_sentinel
from scripts.nk_swarm_messenger import process_payload


def _load_staged_or_prod(mod_name: str, rel_script: str) -> Any:
    """Carica dinamicamente il modulo dando priorita a .staging/scripts/."""
    stg = _workspace_root / ".staging" / rel_script
    prod = _workspace_root / rel_script
    target = stg if stg.exists() else prod
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_active_runtime_sentinel_states(tmp_path: Path) -> None:
    """1. Verifica gli stati GREEN/CAUTION/CRITICAL/RED e le soglie GT-02 standard e argon."""
    assert calculate_state(50, profile="standard") == "GREEN"
    assert calculate_state(60, profile="standard") == "CAUTION"
    assert calculate_state(85, profile="standard") == "CRITICAL"
    assert calculate_state(100, profile="standard") == "RED"

    assert calculate_state(110, profile="argon") == "GREEN"
    assert calculate_state(120, profile="argon") == "CAUTION"
    assert calculate_state(180, profile="argon") == "CRITICAL"
    assert calculate_state(250, profile="argon") == "RED"

    counts_and_states = [
        (30, "GREEN"),
        (70, "CAUTION"),
        (90, "CRITICAL"),
        (110, "RED"),
    ]
    for count, expected_state in counts_and_states:
        f_path = tmp_path / f"transcript_{count}.jsonl"
        f_path.write_text('{"step": 1}\n' * count, encoding="utf-8")
        t0 = time.perf_counter()
        res = run_sentinel(str(f_path), profile="standard")
        elapsed = time.perf_counter() - t0
        assert res["state"] == expected_state
        assert elapsed < 0.05


def test_swarm_messenger_mtu_spillover() -> None:
    """2. Verifica il rispetto del taglio MSS a 1800 caratteri in process_payload (GT-04)."""
    p_small = "x" * 1000
    res1 = process_payload(p_small)
    assert len(res1) == 1000

    p_large = "x" * 5000
    res2 = process_payload(p_large)
    assert len(res2) < 1800
    assert "FULL PAYLOAD SAVED TO" in res2


def test_session_handoff_capsule_and_stash(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """3. Verifica la generazione della capsula handoff Template 12, il Template 11 e la chiusura dell'inning."""
    handoff_mod = _load_staged_or_prod(
        "nk_session_handoff_active", "scripts/nk_session_handoff.py"
    )
    tt_mod = _load_staged_or_prod(
        "nk_transcript_tools_active", "scripts/nk_transcript_tools.py"
    )
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"step": 1}\n{"step": 2}\n', encoding="utf-8")
    output_dir = tmp_path / "handoff"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nk_session_handoff.py",
            "--transcript",
            str(transcript),
            "--output-dir",
            str(output_dir),
            "--generate-prompt",
        ],
    )
    assert handoff_mod.main() == 0
    assert (output_dir / "session_handoff_latest.json").exists()
    prompt_path = output_dir / "next_session_prompt.md"
    assert prompt_path.exists()
    prompt_text = prompt_path.read_text(encoding="utf-8")
    assert "[HANDOFF STATO SESSIONE NK-HUB]" in prompt_text
    assert "Template 12: PASSIVE_SESSION_STATE_HANDOFF" in prompt_text
    assert "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]" in prompt_text

    t12_compiled = handoff_mod.compile_template_12_state_handoff(
        project_root=str(Path(__file__).resolve().parent.parent)
    )
    assert "[HANDOFF STATO SESSIONE NK-HUB]" in t12_compiled
    assert "Template 12: PASSIVE_SESSION_STATE_HANDOFF" in t12_compiled
    assert "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]" in t12_compiled
    assert "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]" in t12_compiled
    assert len(re.findall(r"(?m)^#{2,3}\s+[1-5]\b", t12_compiled)) >= 5
    t12_lint, t12_code = tt_mod.lint_prompt_text(t12_compiled, mode="state-handoff")
    assert t12_code == 0
    assert t12_lint["passed"] is True
    assert t12_lint["violations_count"] == 0

    t11_compiled = handoff_mod.compile_template_11_prompt(
        project_root=str(Path(__file__).resolve().parent.parent)
    )
    assert "Template 11: SOVEREIGN_SWARM_TASK_PROMPT" in t11_compiled

    handoff_data = json.loads(
        (output_dir / "session_handoff_latest.json").read_text(encoding="utf-8")
    )
    assert handoff_data["steps"] == 2

    tuning_file = tmp_path / "tuning" / "session_tuning_params.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nk_auto_inning.py",
            "--transcript",
            str(transcript),
            "--close-inning",
            "--tuning-file",
            str(tuning_file),
        ],
    )
    nk_auto_inning.main()
    assert tuning_file.exists()
    tuning_data = json.loads(tuning_file.read_text(encoding="utf-8"))
    assert "compliance_score" in tuning_data
    assert tuning_data["steps"] == 2
    assert "[Swarm-Envelope: AG-01" in process_payload("corpo", sender="AG-01")

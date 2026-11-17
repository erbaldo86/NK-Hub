# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per Sentinel, Swarm Messenger, Handoff e Auto-Inning (v6.4.0-Carbon).
Modulo: tests/test_active_sentinel_suite.py.
Valida le guardie GT-02 e GT-04, il profilo carbon, mutex Win32 e reset post-compattazione.
"""

from __future__ import annotations

import ctypes
import inspect
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import (
        is_cov_instrumented,
        load_nk_script_module,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        is_cov_instrumented,
        load_nk_script_module,
        load_script_by_relpath,
    )

_sentinel_mod = load_nk_script_module("nk_active_runtime_sentinel")
_messenger_mod = load_nk_script_module("nk_swarm_messenger")
calculate_state = _sentinel_mod.calculate_state
run_sentinel = _sentinel_mod.run_sentinel
process_payload = _messenger_mod.process_payload


@pytest.mark.fast
def test_active_runtime_sentinel_states(tmp_path: Path) -> None:
    """Verifica gli stati GREEN/CAUTION/CRITICAL/RED su standard, carbon e argon + compattazione."""
    assert calculate_state(50) == "GREEN"
    assert calculate_state(50, profile="standard") == "GREEN"
    assert calculate_state(60, profile="standard") == "CAUTION"
    assert calculate_state(85, profile="standard") == "CRITICAL"
    assert calculate_state(100, profile="standard") == "RED"
    assert calculate_state(119, profile="carbon") == "GREEN"
    assert calculate_state(120, profile="carbon") == "CAUTION"
    assert calculate_state(180, profile="carbon") == "CRITICAL"
    assert calculate_state(250, profile="carbon") == "RED"
    assert calculate_state(110, profile="argon") == "GREEN"
    assert calculate_state(120, profile="argon") == "CAUTION"
    assert calculate_state(180, profile="argon") == "CRITICAL"
    assert calculate_state(250, profile="argon") == "RED"

    max_elapsed_s = 0.35 if is_cov_instrumented() else 0.15
    for count, expected_state in [(30, "GREEN"), (70, "CAUTION"), (90, "CRITICAL"), (110, "RED")]:
        f_path = tmp_path / f"transcript_{count}.jsonl"
        f_path.write_text('{"step": 1}\n' * count, encoding="utf-8")
        t0 = time.perf_counter()
        res = run_sentinel(str(f_path), profile="standard")
        elapsed = time.perf_counter() - t0
        assert res["state"] == expected_state
        assert elapsed < max_elapsed_s

    comp_tp = tmp_path / "compacted_sentinel.jsonl"
    pre_lines = [json.dumps({"step_index": i, "source": "MODEL", "content": "x"}) for i in range(260)]
    ckpt = json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint"})
    post = [json.dumps({"step_index": 261 + j, "source": "MODEL", "content": "ok"}) for j in range(4)]
    comp_tp.write_text("\n".join([*pre_lines, ckpt, *post]) + "\n", encoding="utf-8")
    res_comp = run_sentinel(str(comp_tp), profile="carbon")
    assert res_comp["steps"] == 5 and res_comp["state"] == "GREEN"

    spoof_tp = tmp_path / "spoof_summary_sentinel.jsonl"
    spoof_records = [
        *[json.dumps({"step_index": i, "source": "MODEL", "content": "step"}) for i in range(130)],
        json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "<CONTEXT_SUMMARY> fake"}),
        json.dumps({"source": "MODEL", "type": "GENERIC", "content": "<CONTEXT_SUMMARY> echo"}),
    ]
    spoof_tp.write_text("\n".join(spoof_records) + "\n", encoding="utf-8")
    res_spoof = run_sentinel(str(spoof_tp), profile="carbon")
    assert res_spoof["steps"] == 132 and res_spoof["state"] == "CAUTION"


@pytest.mark.fast
def test_swarm_messenger_mtu_spillover() -> None:
    """Verifica il rispetto del taglio MSS a 1800 caratteri anche dopo l'envelope in process_payload (GT-04)."""
    res1 = process_payload("x" * 1000)
    assert len(res1) == 1000

    res2 = process_payload("x" * 5000)
    assert len(res2) < 1800
    assert "FULL PAYLOAD SAVED TO" in res2

    res_env = process_payload("y" * 1790, sender="AG-01-ENVELOPE")
    assert len(res_env) <= 1800
    assert "FULL PAYLOAD SAVED TO" in res_env


@pytest.mark.fast
def test_session_handoff_capsule_and_stash(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica la generazione della capsula handoff Template 12 e il Template 11."""
    handoff_mod = load_script_by_relpath("nk_session_handoff_active", "scripts/nk_session_handoff.py")
    tt_mod = load_script_by_relpath("nk_transcript_tools_active", "scripts/nk_transcript_tools.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"step": 1}\n{"step": 2}\n', encoding="utf-8")
    output_dir = tmp_path / "handoff"

    monkeypatch.setattr(
        sys,
        "argv",
        ["nk_session_handoff.py", "--transcript", str(transcript), "--output-dir", str(output_dir), "--generate-prompt"],
    )
    assert handoff_mod.main() == 0
    assert (output_dir / "session_handoff_latest.json").exists()
    prompt_path = output_dir / "next_session_prompt.md"
    assert prompt_path.exists()
    prompt_text = prompt_path.read_text(encoding="utf-8")
    assert "[HANDOFF STATO SESSIONE NK-HUB]" in prompt_text
    assert "Template 12: PASSIVE_SESSION_STATE_HANDOFF" in prompt_text
    assert "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]" in prompt_text

    t12_compiled = handoff_mod.compile_template_12_state_handoff(project_root=str(tmp_path))
    assert "[HANDOFF STATO SESSIONE NK-HUB]" in t12_compiled
    assert "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]" in t12_compiled
    assert len(re.findall(r"(?m)^#{2,3}\s+[1-5]\b", t12_compiled)) >= 5
    t12_lint, t12_code = tt_mod.lint_prompt_text(t12_compiled, mode="state-handoff")
    assert t12_code == 0 and t12_lint["passed"] is True and t12_lint["violations_count"] == 0

    t11_compiled = handoff_mod.compile_template_11_prompt(project_root=str(tmp_path))
    assert "Template 11: SOVEREIGN_SWARM_TASK_PROMPT" in t11_compiled
    handoff_data = json.loads((output_dir / "session_handoff_latest.json").read_text(encoding="utf-8"))
    assert handoff_data["steps"] == 2
    assert "[Swarm-Envelope: AG-01" in process_payload("corpo", sender="AG-01")


@pytest.mark.integration
def test_auto_inning_close_fail_closed_and_json_cli(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica chiusura auto-inning fail-closed (0 tool call, checker assente) e CLI --json."""
    inning_mod = load_script_by_relpath("nk_auto_inning_active", "scripts/nk_auto_inning.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"step": 1}\n{"step": 2}\n', encoding="utf-8")
    tuning_file = tmp_path / "tuning" / "session_tuning_params.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["nk_auto_inning.py", "--transcript", str(transcript), "--close-inning", "--tuning-file", str(tuning_file), "--json"],
    )
    assert inning_mod.main() is None
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["compliance_score"] == 0 and cli_payload["ratchet_verified"] is False
    assert tuning_file.exists()
    assert json.loads(tuning_file.read_text(encoding="utf-8"))["steps"] == 2

    tuning_missing = tmp_path / "tuning_missing" / "session_tuning_params.json"
    with monkeypatch.context() as mp_in:
        mp_in.setattr(inning_mod, "__file__", str(tmp_path / "empty_scripts" / "nk_auto_inning.py"))
        mp_in.chdir(tmp_path)
        mp_in.setattr(
            sys,
            "argv",
            ["nk_auto_inning.py", "--transcript", str(transcript), "--close-inning", "--tuning-file", str(tuning_missing)],
        )
        inning_mod.main()
    miss_data = json.loads(tuning_missing.read_text(encoding="utf-8"))
    assert miss_data["compliance_score"] == 0 and miss_data["ratchet_verified"] is False

    tp_calls = tmp_path / "transcript_calls.jsonl"
    tp_calls.write_text(
        json.dumps({"step_index": 1, "source": "USER_EXPLICIT", "content": "vai"})
        + "\n"
        + json.dumps({"step_index": 2, "source": "MODEL", "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "python -V"}}]})
        + "\n",
        encoding="utf-8",
    )
    tuning_calls = tmp_path / "tuning_calls" / "session_tuning_params.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["nk_auto_inning.py", "--transcript", str(tp_calls), "--tuning-file", str(tuning_calls), "--json"],
    )
    assert inning_mod.main() is None
    calls_out = json.loads(capsys.readouterr().out)
    assert calls_out["steps"] == 2


@pytest.mark.fast
def test_wp4_sentinel_actual_tokens_tv08_mutex_replace_and_benchmark(tmp_path, monkeypatch) -> None:
    """Verifica calculate_state con actual_tokens trailing, rigetto bool e spoofing TV-08."""
    sentinel_mod = load_script_by_relpath("nk_active_runtime_sentinel_wp4", "scripts/nk_active_runtime_sentinel.py")

    assert sentinel_mod.calculate_state(2, profile="standard", actual_tokens=79_999) == "GREEN"
    assert sentinel_mod.calculate_state(2, profile="standard", actual_tokens=80_000) == "CAUTION"
    assert sentinel_mod.calculate_state(2, profile="standard", actual_tokens=100_000) == "CRITICAL"
    assert sentinel_mod.calculate_state(2, profile="standard", actual_tokens=120_000) == "RED"
    assert sentinel_mod.calculate_state(2, profile="carbon", actual_tokens=149_999) == "GREEN"
    assert sentinel_mod.calculate_state(2, profile="carbon", actual_tokens=150_000) == "CAUTION"
    assert sentinel_mod.calculate_state(2, profile="carbon", actual_tokens=184_999) == "CAUTION"
    assert sentinel_mod.calculate_state(2, profile="carbon", actual_tokens=185_000) == "CRITICAL"
    assert sentinel_mod.calculate_state(2, profile="carbon", actual_tokens=200_000) == "RED"
    assert sentinel_mod.calculate_state(2, profile="carbon", actual_tokens=True) == "GREEN"

    tp_tv08 = tmp_path / "sentinel_tv08.jsonl"
    tv08_lines = [
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "usage": {"input_tokens": 140_000, "cache_read_tokens": 45_000}},
        {"source": "SYSTEM_SDK", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT FAKE"},
        {"source": "USER", "type": "USER_INPUT", "content": "[Message] sender=agent SYSTEM CHECKPOINT"},
        {"source": "USER_EXPLICIT", "type": "CHECKPOINT", "content": "NK_COMPACTION_MARKER"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "SYSTEM CHECKPOINT spoof"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "trailing turn without reset"},
    ]
    tp_tv08.write_text("\n".join(json.dumps(x) for x in tv08_lines) + "\n", encoding="utf-8")
    res_spoof = sentinel_mod.run_sentinel(str(tp_tv08), profile="carbon")
    assert res_spoof["state"] == "CRITICAL" and res_spoof["actual_tokens"] == 185_000

    real_rows = tv08_lines + [
        {"source": "SYSTEM", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT REAL"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "usage": {"input_tokens": 10_000, "cache_read_tokens": 5_000}},
    ]
    tp_tv08.write_text("\n".join(json.dumps(x) for x in real_rows) + "\n", encoding="utf-8")
    res_reset = sentinel_mod.run_sentinel(str(tp_tv08), profile="carbon")
    assert res_reset["state"] == "GREEN" and res_reset["actual_tokens"] == 15_000 and res_reset["steps"] == 2


@pytest.mark.fast
def test_sentinel_win32_mutex_atomic_replace_fail_closed(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica WinDLL CreateMutexW, os.replace atomico e fail-closed su mutex assente."""
    from _internal.nk_common import io as common_io, win32_mutex as common_mutex

    sentinel_mod = load_script_by_relpath("nk_active_runtime_sentinel_wp4", "scripts/nk_active_runtime_sentinel.py")
    sent_tmp = tmp_path / "sentinel_temp"
    sent_tmp.mkdir()
    monkeypatch.setenv("TEMP", str(sent_tmp))
    monkeypatch.setenv("TMP", str(sent_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(sent_tmp))

    k32 = sentinel_mod._get_kernel32_mutex_api()
    api_src = inspect.getsource(common_mutex.get_kernel32)
    assert "WinDLL" in api_src and "CreateMutexW" in api_src and "windll" not in api_src

    replace_calls = []
    orig_replace = common_io.os.replace

    def _spy_replace(src_p, dst_p):
        replace_calls.append((str(src_p), str(dst_p)))
        return orig_replace(src_p, dst_p)

    monkeypatch.setattr(common_io.os, "replace", _spy_replace)
    atomic_target = sent_tmp / "nk_diagnostics" / "sentinel_atomic_probe.json"
    if sys.platform == "win32":
        assert k32 is not None and callable(getattr(k32, "CreateMutexW", None))
        with sentinel_mod._SentinelNamedMutex("NK_SentinelTestMutex_WP4", timeout_ms=500) as acq_ok:
            assert acq_ok is True
            sentinel_mod._write_state_atomic_win32(str(atomic_target), {"steps": 3, "tokens": 12_000, "state": "GREEN", "profile": "carbon"})
    else:
        assert k32 is None
        with sentinel_mod._SentinelNamedMutex("NK_SentinelTestMutex_WP4_PosixClosed", timeout_ms=500) as acq_posix_closed:
            assert acq_posix_closed is False

        class _PosixFakeK32:
            def CreateMutexW(self, _sa: Any, _own: bool, _name: str) -> int:
                return 4242

            def WaitForSingleObject(self, _h: Any, _ms: int) -> int:
                return common_mutex.WAIT_OBJECT_0

            def ReleaseMutex(self, _h: Any) -> int:
                return 1

            def CloseHandle(self, _h: Any) -> int:
                return 1

        with monkeypatch.context() as mp_posix:
            mp_posix.setattr(common_mutex.sys, "platform", "win32")
            mp_posix.setattr(ctypes, "set_last_error", lambda _e: None, raising=False)
            mp_posix.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
            mp_posix.setattr(sentinel_mod, "_get_kernel32_mutex_api", lambda: _PosixFakeK32())
            with sentinel_mod._SentinelNamedMutex("NK_SentinelTestMutex_WP4", timeout_ms=500) as acq_ok:
                assert acq_ok is True
                sentinel_mod._write_state_atomic_win32(str(atomic_target), {"steps": 3, "tokens": 12_000, "state": "GREEN", "profile": "carbon"})
    assert atomic_target.is_file() and len(replace_calls) == 1
    assert json.loads(atomic_target.read_text(encoding="utf-8"))["state"] == "GREEN"
    assert list(atomic_target.parent.glob("*.tmp")) == []

    with monkeypatch.context() as mp_none:
        mp_none.setattr(sentinel_mod, "_get_kernel32_mutex_api", lambda: None)
        with sentinel_mod._SentinelNamedMutex("NK_FailClosed_NoneK32", timeout_ms=50) as acq_none:
            assert acq_none is False

    class _FailingCreateMutexK32:
        def CreateMutexW(self, _sa: Any, _own: bool, _name: str) -> int:
            return 0

        def WaitForSingleObject(self, _h: Any, _ms: int) -> int:
            return 0xFFFFFFFF

        def ReleaseMutex(self, _h: Any) -> int:
            return 0

        def CloseHandle(self, _h: Any) -> int:
            return 1

    with monkeypatch.context() as mp_fail:
        if sys.platform != "win32":
            mp_fail.setattr(common_mutex.sys, "platform", "win32")
            mp_fail.setattr(ctypes, "set_last_error", lambda _e: None, raising=False)
            mp_fail.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
        mp_fail.setattr(sentinel_mod, "_get_kernel32_mutex_api", lambda: _FailingCreateMutexK32())
        with sentinel_mod._SentinelNamedMutex("NK_FailClosed_CreateFail", timeout_ms=50) as acq_fail:
            assert acq_fail is False


@pytest.mark.fast
def test_sentinel_latency_benchmark(tmp_path: Path) -> None:
    """Verifica latenza locale run_sentinel (< 50 ms senza cov, < 150 ms con cov)."""
    sentinel_mod = load_script_by_relpath("nk_active_runtime_sentinel_wp4", "scripts/nk_active_runtime_sentinel.py")
    tp_bench = tmp_path / "sentinel_bench.jsonl"
    bench_lines = [
        {
            "source": "MODEL" if i % 2 == 0 else "USER",
            "type": "PLANNER_RESPONSE" if i % 2 == 0 else "USER_INPUT",
            "usage": {"input_tokens": 20_000 + i * 500, "cache_read_tokens": 5_000},
            "content": f"bench line {i}",
        }
        for i in range(40)
    ]
    tp_bench.write_text("\n".join(json.dumps(x) for x in bench_lines) + "\n", encoding="utf-8")
    sentinel_mod.run_sentinel(str(tp_bench), profile="carbon")
    t0 = time.perf_counter()
    bench_res = sentinel_mod.run_sentinel(str(tp_bench), profile="carbon")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    max_ms = (250.0 if is_cov_instrumented() else 150.0) if is_ci else (150.0 if is_cov_instrumented() else 50.0)
    assert bench_res["state"] == "GREEN"
    assert elapsed_ms < max_ms, f"Sentinel benchmark slow: {elapsed_ms:.2f} ms (limit {max_ms})"


@pytest.mark.fast
def test_sentinel_thresholds_loader_and_cli_branches(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Chiude i branch su YAML/JSON thresholds, _safe_pos_int, righe corrotte e CLI --check."""
    assert _sentinel_mod._safe_pos_int(True, 9) == 9
    assert _sentinel_mod._safe_pos_int(-3, 9) == 9
    assert _sentinel_mod._safe_pos_int(25, 9) == 25

    explicit_dir = tmp_path / "explicit_cfg"
    explicit_dir.mkdir(parents=True)
    explicit_json = explicit_dir / "saturation_thresholds.json"
    explicit_json.write_text(json.dumps({"profiles": {"standard": {"context_sentry": {"green_steps": 55}}}}), encoding="utf-8")
    loaded_explicit = _sentinel_mod.load_saturation_thresholds(thresholds_path=explicit_json)
    assert loaded_explicit["profiles"]["standard"]["context_sentry"]["green_steps"] == 55
    assert _sentinel_mod.load_saturation_thresholds(workspace_root=tmp_path) == {}

    canon_dir = tmp_path / "nk_genome" / "configs"
    canon_dir.mkdir(parents=True)
    canon_json = canon_dir / "saturation_thresholds.json"
    canon_json.write_text(json.dumps({"profiles": {"carbon": {"sentinel": {"green_steps": 99}}}}), encoding="utf-8")
    loaded_canon = _sentinel_mod.load_saturation_thresholds(workspace_root=tmp_path)
    assert loaded_canon["profiles"]["carbon"]["sentinel"]["green_steps"] == 99

    assert _sentinel_mod.load_saturation_thresholds(workspace_root=tmp_path / "missing_ws") == {}
    escaped_cp = '{"source": "SYSTEM", "type": "CHECKPOINT", "content": "\\u003cCONTEXT_SUMMARY> ok"}'
    assert _sentinel_mod._is_compaction_checkpoint(escaped_cp, json.loads(escaped_cp)) is True
    assert _sentinel_mod._is_compaction_checkpoint(escaped_cp, {"source": "SYSTEM", "type": "CHECKPOINT", "content": "\\u003cCONTEXT_SUMMARY> ok"}) is False

    corrupt_tp = tmp_path / "corrupt_nonempty.jsonl"
    corrupt_tp.write_text("{bad_json\nnot_json\n", encoding="utf-8")
    res_corrupt = run_sentinel(str(corrupt_tp), profile="standard")
    assert res_corrupt["steps"] == 2

    green_tp = tmp_path / "green_cli.jsonl"
    green_tp.write_text('{"source": "USER", "content": "ok"}\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["nk_active_runtime_sentinel.py", "--transcript", str(green_tp), "--profile", "standard", "--json"])
    assert _sentinel_mod.main() is None
    assert json.loads(capsys.readouterr().out)["state"] == "GREEN"

    red_tp = tmp_path / "red_cli.jsonl"
    red_tp.write_text('{"source": "MODEL", "content": "x"}\n' * 110, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["nk_active_runtime_sentinel.py", "--transcript", str(red_tp), "--profile", "standard", "--check", "--json"])
    with pytest.raises(SystemExit) as exc_info:
        _sentinel_mod.main()
    assert exc_info.value.code == 1
    assert json.loads(capsys.readouterr().out)["state"] == "RED"

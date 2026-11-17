# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per nk_context_sentry.py e nk_compliance_checker.py (v6.4.0-Carbon).
Modulo: tests/test_context_sentry.py.
Valida stima token, Head-Tail, GT-01/GT-04, profilo carbon, compattazione e audit compliance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

sentry_mod = load_nk_script_module("nk_context_sentry")
compliance_mod = load_nk_script_module("nk_compliance_checker")
NKContextSentry = sentry_mod.NKContextSentry
NKComplianceChecker = compliance_mod.NKComplianceChecker

pytestmark = pytest.mark.fast


def test_estimate_tokens() -> None:
    """Verifica la stima token, il fallback Head-Tail e le soglie semaforiche GT-01."""
    assert NKContextSentry.estimate_tokens("") == 0
    assert NKContextSentry.estimate_tokens("a") == 1
    assert NKContextSentry.estimate_tokens("12345678") == 2
    assert NKContextSentry.estimate_tokens("a" * 400) == 100

    short_text = "Traceback (most recent call last):\n  File 'test.py', line 1\nValueError"
    assert NKContextSentry.format_head_tail(short_text) == short_text

    long_text = "HEAD_" + ("x" * 2000) + "_TAIL"
    compressed = NKContextSentry.format_head_tail(long_text, head_chars=10, tail_chars=10)
    assert compressed.startswith("HEAD_")
    assert compressed.endswith("_TAIL")
    assert "[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]" in compressed

    sentry_std = NKContextSentry(profile="standard")
    assert sentry_std.GREEN_STEP_THRESHOLD == 70
    assert sentry_std.RED_STEP_THRESHOLD == 100
    assert sentry_std.get_traffic_light_status(step_count=40, estimated_tokens=30000)["status"] == "GREEN"
    assert sentry_std.get_traffic_light_status(step_count=85, estimated_tokens=90000)["status"] == "YELLOW"
    assert sentry_std.get_traffic_light_status(step_count=105, estimated_tokens=150000)["status"] == "RED"

    sentry_argon = NKContextSentry(profile="argon")
    assert sentry_argon.get_traffic_light_status(step_count=120, estimated_tokens=90000)["status"] == "GREEN"
    assert sentry_argon.get_traffic_light_status(step_count=180, estimated_tokens=150000)["status"] == "YELLOW"
    assert sentry_argon.get_traffic_light_status(step_count=260, estimated_tokens=260000)["status"] == "RED"


def test_analyze_transcript_real(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica l'analisi reale di transcript.jsonl e l'esecuzione CLI JSON."""
    sentry = NKContextSentry(workspace_root=tmp_path)
    fake_transcript = tmp_path / "transcript.jsonl"
    lines = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Hello", "tool_calls": []},
        {"step_index": 2, "source": "MODEL", "content": "Hi", "tool_calls": [{"name": "view_file"}]},
        {"step_index": 3, "source": "MODEL", "content": "Checking", "tool_calls": [{"name": "run_command"}]},
        {"step_index": 4, "source": "SYSTEM", "content": "<SYSTEM_MESSAGE> [Message] sender=worker-1 " + ("a" * 2500) + " </SYSTEM_MESSAGE>"},
    ]
    fake_transcript.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

    res = sentry.analyze_transcript(fake_transcript)
    assert res["status"] == "GREEN"
    assert res["step_count"] == 4
    assert res["swarm_hygiene_violations_count"] == 1
    assert res["max_consecutive_direct_audit"] == 1

    exempt_tr = tmp_path / "exempt_streak.jsonl"
    exempt_tools = ["read_file", "view_file", "grep_search", "find_by_name", "swarm_wait", "read_board", "ask_question", "schedule"] * 2
    exempt_rows = [{"step_index": i + 1, "source": "MODEL", "tool_calls": [{"name": nm}]} for i, nm in enumerate(exempt_tools)]
    exempt_rows.append({"step_index": 20, "source": "MODEL", "tool_calls": [{"name": "swarm"}, {"name": "post_message"}]})
    exempt_tr.write_text("\n".join(json.dumps(r) for r in exempt_rows) + "\n", encoding="utf-8")
    exempt_res = sentry.analyze_transcript(exempt_tr)
    assert exempt_res["max_consecutive_direct_audit"] == 0

    monkeypatch.setattr(sys, "argv", ["nk_context_sentry.py", "--transcript", str(fake_transcript), "--json"])
    sentry_mod.main()
    cli_out = json.loads(capsys.readouterr().out)
    assert cli_out["step_count"] == 4


def test_context_sentry_carbon_profile_and_compaction_checkpoint_reset(
    tmp_path: Path,
) -> None:
    """Verifica soglie profilo carbon, esclusione thinking e reset su SYSTEM CHECKPOINT."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("NK_MODEL_PROFILE", raising=False)
        sentry_default = NKContextSentry()
        assert sentry_default.profile == "standard"
        mp.setenv("NK_MODEL_PROFILE", "carbon")
        assert NKContextSentry().profile == "carbon"

    sentry_carbon = NKContextSentry(workspace_root=tmp_path, profile="carbon")
    assert sentry_carbon.CARBON_GREEN_STEP_THRESHOLD == 150
    assert sentry_carbon.CARBON_RED_STEP_THRESHOLD == 250
    assert sentry_carbon.get_traffic_light_status(step_count=140, estimated_tokens=120_000, actual_context_tokens=140_000)["status"] == "GREEN"
    assert sentry_carbon.get_traffic_light_status(step_count=160, estimated_tokens=120_000, actual_context_tokens=140_000)["status"] == "YELLOW"
    assert sentry_carbon.get_traffic_light_status(step_count=40, estimated_tokens=40_000, actual_context_tokens=160_000)["status"] == "WARN"
    assert sentry_carbon.get_traffic_light_status(step_count=40, estimated_tokens=40_000, actual_context_tokens=205_000)["status"] == "RED"

    tp_comp = tmp_path / "carbon_compaction.jsonl"
    comp_records = [
        *[
            {"step_index": idx, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 220_000, "content": "A" * 2000, "thinking": "T" * 8000}
            for idx in range(260)
        ],
        {"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint..."},
        {"step_index": 261, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Procedi dopo compattazione."},
        {"step_index": 262, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 18_000, "content": "Riprendo esecuzione.", "thinking": "R" * 40_000},
    ]
    tp_comp.write_text("\n".join(json.dumps(r) for r in comp_records) + "\n", encoding="utf-8")
    rep_comp = sentry_carbon.analyze_transcript(tp_comp)
    assert rep_comp["status"] == "GREEN"
    assert rep_comp["step_count"] == 3
    assert rep_comp["actual_context_tokens"] == 18_000
    assert rep_comp["estimated_tokens"] < 5_000


def test_context_sentry_no_false_reset_on_model_summary(tmp_path: Path) -> None:
    """Verifica che citazioni <CONTEXT_SUMMARY> di MODEL o GENERIC non resettino il conteggio."""
    sentry_carbon = NKContextSentry(workspace_root=tmp_path, profile="carbon")
    tp_non_reset = tmp_path / "carbon_no_false_reset.jsonl"
    non_reset_records = [
        *[{"step_index": idx, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 210_000, "content": "Step"} for idx in range(160)],
        {"step_index": 161, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Analizzo <CONTEXT_SUMMARY> nel testo."},
        {"step_index": 162, "source": "MODEL", "type": "GENERIC", "content": "<CONTEXT_SUMMARY> citato in record generico."},
    ]
    tp_non_reset.write_text("\n".join(json.dumps(r) for r in non_reset_records) + "\n", encoding="utf-8")
    rep = sentry_carbon.analyze_transcript(tp_non_reset)
    assert rep["step_count"] == 162
    assert rep["actual_context_tokens"] == 210_000
    assert rep["status"] == "RED"


def test_wp4_context_sentry_profile_tokens_140kb_bool_and_tv08(tmp_path, monkeypatch) -> None:
    """Verifica default standard, somma input+cache e rigetto bool in _extract_actual_tokens_from_record."""
    monkeypatch.delenv("NK_MODEL_PROFILE", raising=False)
    sentry_default = sentry_mod.NKContextSentry(workspace_root=tmp_path)
    assert sentry_default.profile == "standard"
    st_std_120k = sentry_default.get_traffic_light_status(step_count=10, estimated_tokens=120_000)
    assert st_std_120k["profile"] == "standard" and st_std_120k["status"] == "RED"

    sentry_carbon = sentry_mod.NKContextSentry(workspace_root=tmp_path, profile="carbon")
    assert sentry_carbon.profile == "carbon"
    st_cb_120k = sentry_carbon.get_traffic_light_status(step_count=10, estimated_tokens=120_000)
    assert st_cb_120k["profile"] == "carbon" and st_cb_120k["status"] == "GREEN"

    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"usage": {"input_tokens": 90_000, "cache_read_tokens": 65_000}}) == 155_000
    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"input_tokens": 110_000, "cache_read_tokens": 50_000}) == 160_000
    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"input_tokens": True, "cache_read_tokens": False}) is None
    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"usage": {"input_tokens": 1500, "cache_read_tokens": True}}) != 1501

    st_bool = sentry_carbon.get_traffic_light_status(step_count=True, estimated_tokens=True, actual_context_tokens=True)
    assert st_bool["step_count"] == 0 and st_bool.get("actual_context_tokens") is None and st_bool["status"] == "GREEN"


def test_context_sentry_large_line_140kb_and_backscan_edge(tmp_path: Path) -> None:
    """Verifica righe 140 KB su file > 500 KB, chunk senza newline e file vuoto."""
    sentry_carbon = NKContextSentry(workspace_root=tmp_path, profile="carbon")
    filler = json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "F" * 11_500, "usage": {"input_tokens": 210_000}})
    ckpt = json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT VERIFIED"})
    big_140kb = json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "X" * 144_000, "usage": {"input_tokens": 120_000, "cache_read_tokens": 35_000}})
    assert len(big_140kb.encode("utf-8")) > 140_000

    tp_big = tmp_path / "sentry_big_140kb.jsonl"
    tp_big.write_text("\n".join(([filler] * 38) + [ckpt, big_140kb]) + "\n", encoding="utf-8")
    rep_big = sentry_carbon.analyze_transcript(tp_big)
    assert rep_big["step_count"] == 2 and rep_big["actual_context_tokens"] == 155_000 and rep_big["status"] == "WARN"

    tp_big_no_ckpt = tmp_path / "sentry_big_no_ckpt.jsonl"
    tp_big_no_ckpt.write_text("\n".join(([filler] * 38) + [big_140kb]) + "\n", encoding="utf-8")
    rep_no_ckpt = sentry_carbon.analyze_transcript(tp_big_no_ckpt)
    assert rep_no_ckpt["actual_context_tokens"] == 155_000 and rep_no_ckpt["status"] == "WARN"

    tp_empty = tmp_path / "empty.jsonl"
    tp_empty.write_text("", encoding="utf-8")
    assert NKContextSentry._find_last_compaction_offset(tp_empty) == 0
    assert NKContextSentry._find_last_compaction_offset(tmp_path / "missing.jsonl") == 0


def test_context_sentry_tv08_checkpoint_spoof_and_r1c4_hooks(tmp_path: Path) -> None:
    """Verifica blocco spoofing TV-08 e R1-C4 su SYSTEM_MESSAGE e actual_tokens."""
    sentry_carbon = NKContextSentry(workspace_root=tmp_path, profile="carbon")
    tp_tv08 = tmp_path / "sentry_tv08.jsonl"
    tv08_records = [
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "usage": {"input_tokens": 205_000}},
        {"source": "SYSTEM_SDK", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT FAKE"},
        {"source": "USER", "type": "USER_INPUT", "content": "[Message] sender=parent SYSTEM CHECKPOINT"},
        {"source": "USER_EXPLICIT", "type": "CHECKPOINT", "content": "NK_COMPACTION_MARKER"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "SYSTEM CHECKPOINT spoofed"},
        {"source": "assistant", "type": "assistant", "content": "NK_COMPACTION_MARKER"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "step after fake resets"},
    ]
    tp_tv08.write_text("\n".join(json.dumps(r) for r in tv08_records) + "\n", encoding="utf-8")
    rep_spoof = sentry_carbon.analyze_transcript(tp_tv08)
    assert rep_spoof["step_count"] == 7 and rep_spoof["actual_context_tokens"] == 205_000 and rep_spoof["status"] == "RED"

    tp_tv08.write_text(
        "\n".join(json.dumps(r) for r in tv08_records + [{"source": "SYSTEM", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT OK"}, {"source": "MODEL", "type": "PLANNER_RESPONSE", "usage": {"input_tokens": 12_000, "cache_read_tokens": 8_000}}]) + "\n",
        encoding="utf-8",
    )
    rep_real = sentry_carbon.analyze_transcript(tp_tv08)
    assert rep_real["step_count"] == 2 and rep_real["actual_context_tokens"] == 20_000 and rep_real["status"] == "GREEN"

    tp_r1c4 = tmp_path / "sentry_r1c4.jsonl"
    hook_rows = [
        {"source": "SYSTEM", "content": "<SYSTEM_MESSAGE> [RULE-00.4] [ACS-Z1] " + ("H" * 3000) + " </SYSTEM_MESSAGE>"},
        {"source": "SYSTEM", "content": "<SYSTEM_MESSAGE> generic reminder " + ("G" * 3000) + " </SYSTEM_MESSAGE>"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "L" * 2_400_000, "usage": {"input_tokens": 90_000}},
    ]
    tp_r1c4.write_text("\n".join(json.dumps(r) for r in hook_rows) + "\n", encoding="utf-8")
    rep_r1c4 = sentry_carbon.analyze_transcript(tp_r1c4)
    assert rep_r1c4["swarm_hygiene_violations_count"] == 0 and rep_r1c4["actual_context_tokens"] == 90_000 and rep_r1c4["status"] == "GREEN"


def test_context_sentry_thresholds_lazy_attrs_corrupt_and_cli_text(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Chiude i branch su JSON thresholds (canonico + .staging), __getattr__, corrupt transcript, tool read error e CLI testo."""
    cfg_dir = tmp_path / "nk_genome" / "configs"
    cfg_dir.mkdir(parents=True)
    json_canon = cfg_dir / "saturation_thresholds.json"
    json_canon.write_text(json.dumps({"profiles": {"standard": {"context_sentry": {"green_steps": 61}}}}), encoding="utf-8")
    assert sentry_mod.load_saturation_thresholds(thresholds_path=json_canon)["profiles"]["standard"]["context_sentry"]["green_steps"] == 61
    assert sentry_mod.load_saturation_thresholds(workspace_root=tmp_path)["profiles"]["standard"]["context_sentry"]["green_steps"] == 61

    json_canon.unlink()
    assert sentry_mod.load_saturation_thresholds(workspace_root=tmp_path) == {}
    stg_cfg_dir = tmp_path / ".staging" / "nk_genome" / "configs"
    stg_cfg_dir.mkdir(parents=True)
    stg_json = stg_cfg_dir / "saturation_thresholds.json"
    stg_json.write_text(json.dumps({"profiles": {"carbon": {"context_sentry": {"green_steps": 145}}}}), encoding="utf-8")
    assert sentry_mod.load_saturation_thresholds(workspace_root=tmp_path)["profiles"]["carbon"]["context_sentry"]["green_steps"] == 145
    assert sentry_mod._safe_pos_int(True, 5) == 5 and sentry_mod._safe_pos_int(12, 5) == 12
    assert isinstance(sentry_mod._THRESHOLDS_DATA, dict)
    assert isinstance(sentry_mod._PROFILES_DATA, dict)
    assert isinstance(sentry_mod._STD_CS, dict)
    assert isinstance(sentry_mod._CARB_CS, dict)
    with pytest.raises(AttributeError):
        sentry_mod.__getattr__("_NON_EXISTENT_ATTR")

    corrupt_tp = tmp_path / "corrupt.jsonl"
    corrupt_tp.write_text("{corrupt_json\n", encoding="utf-8")
    rep_err = NKContextSentry(workspace_root=tmp_path).analyze_transcript(corrupt_tp)
    assert rep_err["status"] == "ERROR"

    blind_tp = tmp_path / "blind_read.jsonl"
    blind_rows = [
        {"step_index": 1, "source": "MODEL", "tool_calls": [{"name": "read_file", "arguments": {"Path": "missing.py"}}]},
        {"step_index": 2, "source": "TOOL", "status": "ERROR", "content": "FileNotFoundError: missing.py"},
    ]
    blind_tp.write_text("\n".join(json.dumps(r) for r in blind_rows) + "\n", encoding="utf-8")
    assert NKContextSentry(workspace_root=tmp_path).analyze_transcript(blind_tp)["blind_read_errors"] == 1

    monkeypatch.setattr(sys, "argv", ["nk_context_sentry.py", "--transcript", str(blind_tp), "--profile", "carbon"])
    assert sentry_mod.main() == 0
    assert "[NK-CONTEXT-SENTRY] Status:" in capsys.readouterr().out

    monkeypatch.delenv("NK_CONVERSATION_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["nk_context_sentry.py", "--json"])
    assert sentry_mod.main() == 0
    assert "status" in json.loads(capsys.readouterr().out)


def test_compliance_checker_external_writes_correlation_and_rsi_lookup(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Chiude i branch di nk_compliance_checker su scritture esterne, correlazione tool, telemetry RSI e CLI."""
    assert compliance_mod._is_external_unstage_write("NK_External_Projects/App/src_app/a.py", is_command=False) is True
    assert compliance_mod._is_external_unstage_write("NK_External_Projects/App/.staging/a.py", is_command=False) is False
    assert compliance_mod._is_external_unstage_write("pytest NK_External_Projects/App/tests", is_command=True) is False
    assert compliance_mod._is_external_unstage_write("Set-Content NK_External_Projects/App/src_app/a.py", is_command=True) is True
    assert compliance_mod._is_exempt_diagnostic_nonzero('{"status": "FAIL", "scores": {"procedural_score": 80}}') == "EXEMPT_EXTERNAL_AUDIT"
    assert compliance_mod._is_exempt_diagnostic_nonzero('{"status": "REFINING", "delta_k": 1}') == "INTERMEDIATE_REFINING"
    assert compliance_mod._is_exempt_diagnostic_nonzero("traceback") == "REAL_ERROR"
    assert compliance_mod._parse_record_epoch("2026-11-16T01:00:00Z") is not None
    assert compliance_mod._parse_record_epoch(True) is None
    assert compliance_mod._parse_record_epoch("invalid-date") is None

    pending = [{"id": "c1", "name": "run_command"}, {"tool_call_id": "c2", "name": "read_file"}]
    matched = compliance_mod._pop_correlated_tool_call(pending, {"tool_response": {"id": "c2"}})
    assert matched["name"] == "read_file"
    assert compliance_mod._pop_correlated_tool_call(pending, {})["name"] == "run_command"
    assert compliance_mod._pop_correlated_tool_call([], {}) == {}

    conv_dir = tmp_path / "brain" / "conv-123"
    conv_dir.mkdir(parents=True)
    tp = conv_dir / "transcript.jsonl"
    rows = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Vai"},
        {"step_index": 2, "source": "MODEL", "tool_calls": [{"id": "call-1", "name": "run_command", "arguments": {"CommandLine": "python scripts/rsi_convergence_engine.py"}}]},
        {"step_index": 3, "source": "TOOL", "tool_response": {"id": "call-1"}, "content": '{"status": "CONVERGED_OPTIMAL"}'},
    ]
    tp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (conv_dir / "rsi_telemetry.jsonl").write_text(json.dumps({"session_id": "conv-123", "fitness_q": 96.5}) + "\n", encoding="utf-8")

    checker = NKComplianceChecker(workspace_root=tmp_path)
    audit = checker.audit_transcript(tp)
    assert audit["status"] in ("PASS", "FAIL")
    assert checker._lookup_rsi_telemetry_score(tp) == (True, 96.5)

    monkeypatch.setattr(sys, "argv", ["nk_compliance_checker.py", "--transcript", str(tp), "--min-score", "101"])
    assert compliance_mod.main() == 1
    assert "[NK-COMPLIANCE]" in capsys.readouterr().out


def test_compliance_checker_staging_md_exempt_from_ast_guard_penalty(tmp_path: Path) -> None:
    """Verifica esenzione AST Guard [-10] su .staging/.md mantenendo -20/-10 su codice non staged."""
    checker = NKComplianceChecker(workspace_root=tmp_path)

    tp_staged = tmp_path / "staged_md_only.jsonl"
    tp_staged.write_text(
        "\n".join([
            json.dumps({"step_index": 1, "source": "USER_EXPLICIT", "content": "Aggiorna staging e doc"}),
            json.dumps({"step_index": 2, "source": "MODEL", "tool_calls": [
                {"name": "write_file", "arguments": {"Path": ".staging/scripts/mod_a.py"}},
                {"name": "write_file", "arguments": {"Path": "docs/notes.md"}},
            ]}),
        ]) + "\n",
        encoding="utf-8",
    )
    rep_staged = checker.audit_transcript(tp_staged)
    assert rep_staged["status"] == "PASS"
    assert rep_staged["metrics"]["write_calls"] == 2 and rep_staged["metrics"]["code_write_calls"] == 0
    assert not any("AST Guard omitted" in p for p in rep_staged["penalties"])

    tp_unstaged = tmp_path / "unstaged_prod.jsonl"
    tp_unstaged.write_text(
        "\n".join([
            json.dumps({"step_index": 1, "source": "USER_EXPLICIT", "content": "Scrivi in prod"}),
            json.dumps({"step_index": 2, "source": "MODEL", "tool_calls": [
                {"name": "write_file", "arguments": {"Path": "scripts/direct_prod.py"}},
            ]}),
        ]) + "\n",
        encoding="utf-8",
    )
    rep_unstaged = checker.audit_transcript(tp_unstaged)
    assert rep_unstaged["status"] == "FAIL" and rep_unstaged["metrics"]["code_write_calls"] == 1
    assert any("Staging bypass" in p and "[-20]" in p for p in rep_unstaged["penalties"])
    assert any("AST Guard omitted [-10]" in p for p in rep_unstaged["penalties"])

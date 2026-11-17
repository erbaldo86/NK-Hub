# -*- coding: utf-8 -*-
"""
Test suite di chiusura rami shard2 (handoff, transcript, compliance, preflight, sentry,
bootstrap, router, runner, cleanup, scaffolder e registry indexer) v6.4.0-Carbon.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

try:
    from conftest import call_script_main_captured, load_script_by_relpath
except ImportError:
    from tests.conftest import call_script_main_captured, load_script_by_relpath


@pytest.mark.fast
def test_handoff_transcript_cursor_compaction_and_eviction(tmp_path: Path) -> None:
    """Verifica cursore incrementale, compaction, pending_part, shrink ed eviction cache."""
    hm = load_script_by_relpath("nk_session_handoff", "scripts/nk_session_handoff.py")
    hm._TRANSCRIPT_CURSOR_CACHE.clear()
    assert hm._inspect_transcript_fast("") == (0, 0, "", None)
    assert hm._inspect_transcript_fast(str(tmp_path / "missing.jsonl")) == (0, 0, "", None)
    empty_tp = tmp_path / "empty.jsonl"
    empty_tp.write_bytes(b"")
    assert hm._inspect_transcript_fast(str(empty_tp)) == (0, 0, "{}", None)

    tp = tmp_path / "tr_cursor.jsonl"
    lines = [
        json.dumps({"step_index": i, "source": "MODEL", "content": f"step {i}"})
        for i in range(11)
    ]
    lines.append(json.dumps({"source": "MODEL", "input_tokens": True, "metadata": {"usage": {"prompt_tokens": 300, "cachedContentTokenCount": 50}}}))
    lines.append("{corrupt_json_tail")
    tp.write_text("\n".join(lines), encoding="utf-8")
    r1 = hm._inspect_transcript_fast(str(tp))
    assert r1[0] >= 12 and r1[3] == 350
    assert hm._inspect_transcript_fast(str(tp)) == r1

    ckpt = json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint"})
    with open(tp, "a", encoding="utf-8") as fh:
        fh.write("\n\n" + ckpt + "\n" + json.dumps({"source": "MODEL", "input_tokens": 111}) + "\n" + json.dumps({"source": "MODEL", "input_tokens": 222}))
    r2 = hm._inspect_transcript_fast(str(tp))
    assert r2[0] == 3 and r2[3] == 222

    with open(tp, "a", encoding="utf-8") as fh:
        fh.write("\n" + ckpt)
    r3 = hm._inspect_transcript_fast(str(tp))
    assert r3[0] == 1

    for idx in range(35):
        hm._TRANSCRIPT_CURSOR_CACHE[f"dummy_key_{idx}"] = {"file_size": 1}
    tp.write_text(json.dumps({"source": "USER_EXPLICIT", "content": "shrunk"}) + "\n", encoding="utf-8")
    r4 = hm._inspect_transcript_fast(str(tp))
    assert r4[0] == 1 and len(hm._TRANSCRIPT_CURSOR_CACHE) <= 2


@pytest.mark.fast
def test_handoff_baseline_capsule_and_intent_brief_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica Dual-Schema baseline, capsule truncation, resolve_session_tracking_dir e IB."""
    hm = load_script_by_relpath("nk_session_handoff", "scripts/nk_session_handoff.py")
    hm._BASELINE_MEMO.clear()

    ws1 = tmp_path / "ws_metrics_int"
    (ws1 / "nk_tracking").mkdir(parents=True)
    (ws1 / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"total_golden_tests": 42, "unit_tests_pass_pct": 98.5}}),
        encoding="utf-8",
    )
    assert hm._read_baseline_tests_count(ws1) == 42
    assert hm._read_baseline_pass_rate(ws1) == 98.5

    ws2 = tmp_path / "ws_flat"
    (ws2 / "nk_tracking").mkdir(parents=True)
    (ws2 / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"total_tests": 19, "pass_rate": 91.2}), encoding="utf-8"
    )
    assert hm._read_baseline_tests_count(ws2) == 19
    assert hm._read_baseline_pass_rate(ws2) == 91.2

    ws3 = tmp_path / "ws_bad"
    (ws3 / "nk_tracking").mkdir(parents=True)
    (ws3 / "nk_tracking" / "quality_baseline.json").write_text("{corrupt", encoding="utf-8")
    monkeypatch.setattr(hm, "_workspace_root", ws3)
    if "scripts.nk_session_handoff" in sys.modules:
        monkeypatch.setattr(sys.modules["scripts.nk_session_handoff"], "_workspace_root", ws3, raising=False)
    from _internal.nk_session_handoff import constants as hm_consts, templates_compiler as hm_tc
    monkeypatch.setattr(hm_consts, "_workspace_root", ws3)
    monkeypatch.setattr(hm_tc, "_workspace_root", ws3)
    hm._BASELINE_MEMO.clear()
    assert hm._read_baseline_tests_count(ws3) == 183
    assert hm._read_baseline_pass_rate(ws3) == 100.0

    cap = hm._format_safe_capsule_lines(
        ["", "{}", "raw_" + ("x" * 220), json.dumps({"step_index": 1, "content": "a" * 200}), json.dumps({"step_index": 2, "content": "b" * 2300})],
        max_chars=400,
    )
    assert "step_index" in cap and len(cap) <= 400
    assert hm.resolve_session_tracking_dir(tmp_path, None) is None
    assert hm.resolve_session_tracking_dir(tmp_path, "default_1") is None
    ib = hm.persist_intent_brief("CUSTOM_ID", "prompt ``` code ``` body", project_root="")
    assert ib.name == "IB-CUSTOM_ID.md" and ib.is_file() and ib.resolve().is_relative_to(ws3.resolve())


@pytest.mark.fast
def test_handoff_memo_cache_pruning_staging_and_git_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica disk memo cache >=16 file, pruning, staging hash e git dirty fast."""
    hm = load_script_by_relpath("nk_session_handoff", "scripts/nk_session_handoff.py")
    prune_dir = tmp_path / "prune_cache"
    hm._prune_handoff_memo_cache(prune_dir, max_files=2)
    prune_dir.mkdir(parents=True)
    for i in range(4):
        (prune_dir / f"m_{i}.json").write_text("{}", encoding="utf-8")
    hm._prune_handoff_memo_cache(prune_dir, max_files=2)
    assert len(list(prune_dir.glob("*.json"))) == 2

    ws = tmp_path / "ws_memo"
    ws.mkdir()
    old_ts = time.time() - 10.0
    for i in range(18):
        fp = ws / f"file_{i:02d}.txt"
        fp.write_text(f"payload_{i}", encoding="utf-8")
        os.utime(fp, (old_ts, old_ts))
    hm._FILE_HASH_MEMO.clear()
    sha1 = hm._compute_workspace_state_sha256(ws)
    hm._FILE_HASH_MEMO.clear()
    sha2 = hm._compute_workspace_state_sha256(ws)
    assert sha1 == sha2

    stg_sub = ws / ".staging" / "pkg"
    (stg_sub / "__pycache__").mkdir(parents=True)
    (stg_sub / "__pycache__" / "x.pyc").write_bytes(b"123")
    (stg_sub / "mod.py").write_text("x = 1\n", encoding="utf-8")
    assert hm._has_dirty_staging_inprocess(ws) is True
    assert len(hm._compute_staging_state_sha256(ws)) == 64

    git_ws = tmp_path / "git_ws"
    (git_ws / ".git").mkdir(parents=True)
    monkeypatch.setattr(hm.subprocess, "check_output", lambda *a, **kw: " M app.py\n")
    monkeypatch.setattr(hm.subprocess, "call", lambda *a, **kw: 0)
    dirty, patch_p = hm._check_git_dirty_fast(git_ws, "git", stash_output_dir=str(tmp_path / "st_out"))
    assert dirty is True and patch_p is not None and Path(patch_p).is_file()


@pytest.mark.fast
def test_handoff_anchor_resume_and_cli_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica resume_from_anchor edges e tutti i branch CLI di main()."""
    hm = load_script_by_relpath("nk_session_handoff", "scripts/nk_session_handoff.py")
    parent_ws = tmp_path / "parent_wrap"
    hub_ws = parent_ws / "NK_Hub"
    (hub_ws / "scripts").mkdir(parents=True)
    (hub_ws / "nk_tracking" / "anchor").mkdir(parents=True)
    (hub_ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 10}}),
        encoding="utf-8",
    )
    anchor_f = hub_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    anchor_f.write_text("{bad_line\n" + json.dumps({"note": "not_cp"}) + "\n", encoding="utf-8")
    res_bad = hm.resume_from_anchor(root=hub_ws)
    assert res_bad["gate_status"] == "CORRUPTED"

    anchor_f.write_text(json.dumps({"note": "preamble"}) + "\n", encoding="utf-8")
    assert hm.resume_from_anchor(root=hub_ws)["gate_status"] == "MISSING"

    rc_turn, out_turn, _ = call_script_main_captured(hm, ["--root", str(parent_ws), "--turn", "bad_val"])
    assert rc_turn == 2 and "ERROR" in out_turn
    with pytest.raises(ValueError):
        hm.main(["--root", str(hub_ws), "--checkpoint-turn", "0", "--dry-run"])

    rc_dry, out_dry, _ = call_script_main_captured(
        hm,
        ["--root", str(hub_ws), "--conversation-id", "conv_h1", "--checkpoint-turn", "2", "--compile-template-11", "--generate-active-context", "--dry-run"],
    )
    assert rc_dry == 0 and json.loads(out_dry)["status"] == "DRY_RUN"

    rc_live, out_live, _ = call_script_main_captured(
        hm, ["--root", str(hub_ws), "--conversation-id", "conv_h2", "--turn", "2", "--auto-checkpoint"]
    )
    assert rc_live == 0 and json.loads(out_live)["status"] == "CHECKPOINT_SAVED"

    rc_st, out_st, _ = call_script_main_captured(
        hm, ["--root", str(hub_ws), "--conversation-id", "conv_h3", "--compile-state-handoff"]
    )
    assert rc_st == 0 and "Template 12" in out_st

    rc_cp, out_cp, _ = call_script_main_captured(
        hm, ["--root", str(hub_ws), "--checkpoint-turn", "3", "--persist-brief-id", "IB-CLI-3", "--prompt-text", "x"]
    )
    assert rc_cp == 0 and "Template" not in out_cp
    rc_res, out_res, _ = call_script_main_captured(hm, ["--root", str(hub_ws), "--resume-from-anchor"])
    assert rc_res == 0 and json.loads(out_res)["status"] == "RESUMED"
    rc_ctx, out_ctx, _ = call_script_main_captured(hm, ["--root", str(hub_ws), "--generate-active-context"])
    assert rc_ctx == 0 and json.loads(out_ctx)["status"] == "GENERATED"
    monkeypatch.setattr(hm, "locate_transcript", lambda **_kw: ({"transcript_path": ""}, 0))
    rc_gs, _, _ = call_script_main_captured(hm, ["--root", str(hub_ws), "--conversation-id", "conv_h4", "--git-stash"])
    assert rc_gs == 0


@pytest.mark.fast
def test_handoff_auto_checkpoint_lint_fail_and_lock_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica LINT_FAILED su auto-checkpoint e SKIPPED_LOCK_BUSY su contesa mutex."""
    hm = load_script_by_relpath("nk_session_handoff", "scripts/nk_session_handoff.py")
    ws = tmp_path / "ws_lock"
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0}}), encoding="utf-8"
    )
    monkeypatch.setattr(hm, "lint_prompt_text", lambda txt, mode="auto": ({"passed": False, "violations_count": 1}, 1))
    rc_lint, out_lint, _ = call_script_main_captured(
        hm, ["--root", str(ws), "--auto-checkpoint", "--turn", "1"]
    )
    assert rc_lint == 1 and json.loads(out_lint)["status"] == "LINT_FAILED"

    monkeypatch.setattr(hm, "lint_prompt_text", lambda txt, mode="auto": ({"passed": True, "violations_count": 0}, 0))

    class _BusyMutex:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args

        def __enter__(self) -> "_BusyMutex":
            raise hm.Win32LockTimeoutError("mutex busy test")

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

    monkeypatch.setattr(hm, "Win32NamedMutex", _BusyMutex)
    rc_busy, out_busy, _ = call_script_main_captured(
        hm, ["--root", str(ws), "--auto-checkpoint", "--turn", "2"]
    )
    assert rc_busy == 0 and json.loads(out_busy)["status"] == "SKIPPED_LOCK_BUSY"


@pytest.mark.fast
def test_transcript_tools_correlation_discovery_and_steps(tmp_path: Path) -> None:
    """Verifica _extract_call_id, classify MODEL tool-header, exit code legacy e discovery >25 dir."""
    tt = load_script_by_relpath("nk_transcript_tools", "scripts/nk_transcript_tools.py")
    assert tt._extract_call_id({"tool_result": {"id": "tr_1"}}) == "tr_1"
    assert tt._extract_call_id({"tool_results": [{"toolCallId": "tr_2"}]}) == "tr_2"
    assert tt._extract_call_id("bad") == ""
    assert tt.classify_transcript_record({"source": "MODEL", "content": "Showing lines 1-5 of 10"}) == "TOOL"
    assert tt.extract_command_exit_code("Command exited with code 7", correlated_tool="run_command") == 7

    bad_sub = tmp_path / "sub_lines.jsonl"
    bad_sub.write_text("\n{broken\n[1,2]\n" + json.dumps({"source": "SYSTEM", "content": "<subagent_reminder>hi"}) + "\n", encoding="utf-8")
    assert tt.is_subagent_transcript_file(bad_sub) is True
    assert tt.is_subagent_transcript_file(tmp_path / "missing_sub.jsonl") is False
    assert tt.count_transcript_steps(bad_sub) == (1, 3, len(bad_sub.read_text(encoding="utf-8")))

    brain = tmp_path / "brain_disc"
    for i in range(27):
        log = brain / f"conv_{i:02d}" / ".system_generated" / "logs" / "transcript.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps({"source": "SYSTEM", "content": "<SYSTEM_MESSAGE>sender=a"}) + "\n", encoding="utf-8")
    old_ts = time.time() - 200000.0
    os.utime(brain / "conv_00", (old_ts, old_ts))
    found = tt.discover_active_main_transcript(brain_dir=brain, max_age_seconds=3600.0)
    assert found is not None and found.name == "transcript.jsonl"


@pytest.mark.fast
def test_transcript_tools_hydration_ste100_and_compliance(tmp_path: Path) -> None:
    """Verifica idratazione transcript_full con shift, STE-100 YAML/commenti e analyze_compliance."""
    tt = load_script_by_relpath("nk_transcript_tools", "scripts/nk_transcript_tools.py")
    inv_only = tmp_path / "inv_only.jsonl"
    inv_only.write_text("\n{broken_only\n", encoding="utf-8")
    assert tt.load_transcript_records(inv_only) == []

    tr_dir = tmp_path / "tr_hyd"
    tr_dir.mkdir()
    tr_f = tr_dir / "transcript.jsonl"
    full_f = tr_dir / "transcript_full.jsonl"
    tr_f.write_text(
        "\n"
        + json.dumps({"step_index": 0, "source": "USER", "content": "start"}) + "\n"
        + json.dumps({"step_index": 1, "source": "MODEL", "truncated_fields": ["content"], "content": "short"}) + "\n"
        + json.dumps({"step_index": 2, "source": "MODEL", "truncated_fields": ["content"], "content": "short2"}) + "\n",
        encoding="utf-8",
    )
    full_f.write_text(
        "{corrupt_line_0\n"
        + json.dumps({"step_index": 99, "source": "MODEL", "content": "mismatch"}) + "\n"
        + json.dumps({"step_index": 1, "source": "MODEL", "content": "hydrated_1"}) + "\n"
        + json.dumps({"step_index": 2, "source": "MODEL", "content": "hydrated_2"}) + "\n",
        encoding="utf-8",
    )
    recs = tt.load_transcript_records(tr_f, hydrate_truncated=True)
    assert recs[1]["content"] == "hydrated_1" and recs[2]["content"] == "hydrated_2"

    ste_txt = "<yaml_metadata_card>\nfoo: bar\n</yaml_metadata_card>\n<!-- open\nstill comment\n-->\nFrase breve valida."
    assert tt.verify_ste100_compliance(ste_txt)["passed"] is True
    assert tt.analyze_compliance(tmp_path / "missing_comp.jsonl")["passed"] is False

    comp_f = tmp_path / "comp_tr.jsonl"
    comp_recs = [
        {"source": "USER", "type": "USER_INPUT", "content": "vai"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "", "tool_calls": [
            {"name": "manage_subagents", "args": {"Action": "list"}},
            {"name": "manage_subagents", "args": {"Action": "list"}},
            {"name": "ask_question", "args": {"questions": []}},
            {"name": "send_message", "args": {"Message": "x" * 1850}},
            {"name": "run_command", "args": {"CommandLine": "python scripts/nk_session_bootstrap.py"}},
            {"name": "run_command", "args": {"CommandLine": "python scripts/nk_session_bootstrap.py"}},
            {"name": "run_command", "args": {"CommandLine": "echo hi > NK_External_Projects/app/a.py"}},
        ]},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Delega.", "tool_calls": [{"name": "invoke_subagent", "args": {}}]},
    ]
    comp_f.write_text("\n".join(json.dumps(r) for r in comp_recs) + "\n", encoding="utf-8")
    comp = tt.analyze_compliance(comp_f)
    assert comp["passed"] is False and comp["polling_list_calls"] == 1 and comp["oversized_swarm_messages"] == 1
    assert comp["silent_l0_ask_question_calls"] == 1 and comp["subagent_delegations"] == 1


@pytest.mark.fast
def test_transcript_tools_evidence_oracle_ears_grounding_and_cli(tmp_path: Path) -> None:
    """Verifica check_evidence inline, oracle_lock multi-root/CRLF, EARS, grounding e CLI."""
    tt = load_script_by_relpath("nk_transcript_tools", "scripts/nk_transcript_tools.py")
    ev_tr = tmp_path / "ev.jsonl"
    ev_tr.write_text(
        "\n".join([
            json.dumps({"source": "USER", "type": "USER_INPUT", "content": "check"}),
            json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "PASS", "tool_calls": [{"name": "read_file", "args": {}}], "output": "ok"}),
            json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "PASS", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest"}}], "output": "plain line no exit"}),
        ]) + "\n",
        encoding="utf-8",
    )
    ev_res, ev_rc = tt.check_evidence(ev_tr, message="all tests passed")
    assert ev_rc == 1 and ev_res["passed"] is False

    ws = tmp_path / "ws_oracle"
    for d in ("tests", "scripts", ".agents/skills/S1", ".github/workflows", "nk_genome/shards", "nk_genome/sub", "nk_genome/modules"):
        (ws / d).mkdir(parents=True)
    f_crlf = ws / "tests" / "test_eol.py"
    f_crlf.write_bytes(b"def test_x():\r\n    assert True\r\n")
    (ws / "scripts" / "s.py").write_text("x=1\n", encoding="utf-8")
    (ws / ".agents/skills/S1/SKILL.md").write_text("# S\n", encoding="utf-8")
    (ws / ".github/workflows/ci.yml").write_text("on: push\n", encoding="utf-8")
    (ws / "nk_genome/PATCH_NOTES.md").write_text("# P\n", encoding="utf-8")
    (ws / "nk_genome/shards/DOM-01.md").write_text("# D\n", encoding="utf-8")
    (ws / "nk_genome/sub/ignored.md").write_text("# I\n", encoding="utf-8")
    (ws / "nk_genome/modules/m.md").write_text("# M\n", encoding="utf-8")

    lock_f = ws / "nk_tracking" / "oracle_lock.json"
    single_f = ws / "tests" / "single.txt"
    single_f.write_text("hello\n", encoding="utf-8")
    assert tt.handle_oracle_lock("create", single_f, tmp_path / "s_lock.json")[1] == 0
    assert tt.handle_oracle_lock("create", ws / "tests", lock_f)[1] == 0
    f_crlf.write_bytes(b"def test_x():\n    assert True\n")
    assert tt.handle_oracle_lock("verify", ws / "tests", lock_f)[1] == 0
    assert tt._sha256_eol_matches(tmp_path / "no_file.txt", "abc") is False

    ears_res = tt.lint_ears_requirements("# Titolo\n```\nQUANDO a, IL SISTEMA DEVE b.")
    assert ears_res["passed"] is True

    rep = tmp_path / "rep.md"
    rep.write_text("| `scripts/phantom_hallucinated_helper.py` | vietato (denylist) |\n", encoding="utf-8")
    bad_man = tmp_path / "bad_man.json"
    bad_man.write_text("{corrupt", encoding="utf-8")
    assert tt.verify_report_grounding(tmp_path / "miss.md")["exit_code"] == 1
    assert tt.verify_report_grounding(rep, manifest_path=bad_man)["passed"] is True

    brain_cli = tmp_path / "brain_cli"
    c_tr = brain_cli / "cid_ok" / ".system_generated" / "logs" / "transcript.jsonl"
    c_tr.parent.mkdir(parents=True)
    c_tr.write_text(json.dumps({"source": "USER", "content": "hi"}) + "\n", encoding="utf-8")
    assert call_script_main_captured(tt, ["compliance", "--conversation-id", "cid_ok", "--brain-dir", str(brain_cli)])[0] == 0
    assert call_script_main_captured(tt, ["compliance", "--conversation-id", "cid_miss", "--brain-dir", str(brain_cli)])[0] == 2
    assert call_script_main_captured(tt, ["evidence", "--conversation-id", "cid_miss", "--brain-dir", str(brain_cli)])[0] == 2
    assert call_script_main_captured(tt, ["evidence", "--conversation-id", "cid_ok", "--brain-dir", str(brain_cli), "--message", "ok"])[0] == 0


@pytest.mark.fast
def test_compliance_checker_rsi_lookup_and_scoring_edges(tmp_path: Path) -> None:
    """Verifica scoring RSI fail-closed, skew temporale e lookup per-sessione."""
    cc_mod = load_script_by_relpath("nk_compliance_checker", "scripts/nk_compliance_checker.py")
    assert cc_mod._is_verified_converged_tool_output("CONVERGED_OPTIMAL", "rsi_convergence_engine.py", 1) is False
    assert cc_mod._is_verified_converged_tool_output("CONVERGED_OPTIMAL", "python scripts/rsi_convergence_engine.py", 0) is True
    assert cc_mod.NKComplianceChecker._score_from_rsi_record("not_dict") == 0  # type: ignore[arg-type]
    assert cc_mod.NKComplianceChecker._score_from_rsi_record({"fitness_q": True}) == 0
    assert cc_mod.NKComplianceChecker._score_from_rsi_record({"delta_k": None}) == 0
    assert cc_mod.NKComplianceChecker._score_from_rsi_record({"delta_k": 1, "verdict": "FAIL"}) == 0

    ws = tmp_path / "ws_rsi"
    (ws / "nk_tracking").mkdir(parents=True)
    brain_tr = tmp_path / "brain" / "sess_A" / "transcript.jsonl"
    brain_tr.parent.mkdir(parents=True)
    brain_tr.write_text(json.dumps({"source": "USER", "content": "go"}) + "\n", encoding="utf-8")

    local_rsi = brain_tr.parent / "rsi_telemetry.jsonl"
    local_rsi.write_text(
        json.dumps({"session_id": "sess_A", "fitness_q": 88.0}) + "\n\n" + json.dumps({"session_id": "other_sess", "fitness_q": 10.0}) + "\n",
        encoding="utf-8",
    )
    chk = cc_mod.NKComplianceChecker(workspace_root=ws)
    assert chk._lookup_rsi_telemetry_score(brain_tr) == (True, 88.0)

    local_rsi.unlink()
    global_rsi = ws / "nk_tracking" / "rsi_telemetry.jsonl"
    stale_iso = "2020-01-01T00:00:00Z"
    global_rsi.write_text(
        json.dumps({"fitness_q": 77.5}) + "\n"
        + json.dumps({"timestamp": stale_iso, "fitness_q": 12.0}) + "\n"
        + json.dumps({"session_id": "other_2", "fitness_q": 22.0}) + "\n",
        encoding="utf-8",
    )
    assert chk._lookup_rsi_telemetry_score(brain_tr) == (True, 77.5)

    global_rsi.write_text(
        json.dumps({"session_id": "sess_A", "fitness_q": 95.0}) + "\n",
        encoding="utf-8",
    )
    assert chk._lookup_rsi_telemetry_score(brain_tr) == (True, 95.0)
    old_t = time.time() - 20000.0
    os.utime(global_rsi, (old_t, old_t))
    assert chk._lookup_rsi_telemetry_score(brain_tr) == (False, 0)


@pytest.mark.fast
def test_compliance_checker_audit_transcript_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica audit_transcript su tool inline, refining non risolto, prod_src e CLI."""
    cc_mod = load_script_by_relpath("nk_compliance_checker", "scripts/nk_compliance_checker.py")
    assert cc_mod._is_production_code_write("prod_src/main.py") is True
    assert cc_mod._is_production_code_write("docs/notes.md") is False

    monkeypatch.setattr(cc_mod, "find_active_transcript", lambda: None)
    chk = cc_mod.NKComplianceChecker(workspace_root=tmp_path)
    assert chk.audit_transcript(None)["status"] == "ERROR"
    assert call_script_main_captured(cc_mod, [])[0] == 1

    tr = tmp_path / "audit_tr.jsonl"
    recs = [
        {"source": "USER", "type": "USER_INPUT", "content": "start"},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "", "tool_calls": [
            {"name": "run_command", "args": {"CommandLine": "python scripts/win32_2pc_engine.py"}},
            {"name": "write_file", "args": {"Path": "prod_src/mod.py"}},
        ], "tool_output": '{"status": "REFINING", "delta_k": 0.2}\nCommand exited with code 1'},
        {"source": "USER", "type": "USER_INPUT", "content": "next"},
    ]
    tr.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    res = chk.audit_transcript(tr)
    assert res["metrics"]["command_error_steps"] >= 1 and res["metrics"]["win32_2pc_executed"] is True

    rc_cli, out_cli, _ = call_script_main_captured(cc_mod, ["--transcript", str(tr), "--min-score", "99"])
    assert rc_cli == 1 and "[NK-COMPLIANCE]" in out_cli
    assert call_script_main_captured(cc_mod, ["--transcript", str(tr), "--min-score", "0", "--json"])[0] == 1


@pytest.mark.fast
def test_preflight_wal_retention_and_cleanup_edges(tmp_path: Path) -> None:
    """Verifica safe_remove missing, WAL multiline/stale, report shallow e retention."""
    pf_mod = load_script_by_relpath("preflight_health_check", "scripts/preflight_health_check.py")
    assert pf_mod.safe_remove_dir(tmp_path / "no_dir") is True
    assert pf_mod.safe_remove_file(tmp_path / "no_file") is True

    ws = tmp_path / "pf_ws"
    ws.mkdir()
    chk = pf_mod.PreflightHealthChecker(workspace_root=ws)
    assert chk._collect_report_files_shallow() == []
    assert chk._collect_tracking_bak_files_shallow() == []

    (ws / ".wal" / "nested_sub").mkdir(parents=True)
    (ws / ".wal" / "nested_sub" / "keep.txt").write_text("k", encoding="utf-8")
    wal_list = ws / ".wal" / "list.wal"
    wal_list.write_text("[1, 2]", encoding="utf-8")
    assert chk._is_committed_wal(wal_list) is False
    wal_multi = ws / ".wal" / "multi.wal"
    wal_multi.write_text('{"state": "COMMITTED"}\n\n[1]\n', encoding="utf-8")
    assert chk._is_committed_wal(wal_multi) is False
    old_t = time.time() - 500.0
    os.utime(wal_list, (old_t, old_t))
    (ws / "scripts" / ".wal").mkdir(parents=True)
    (ws / "scripts" / ".wal" / "keep.txt").write_text("1", encoding="utf-8")
    (ws / "root.wal").write_text('{"state": "OPEN"}', encoding="utf-8")
    os.utime(ws / "root.wal", (old_t, old_t))

    scan1 = chk._scan_workspace_once()
    scan2 = chk._scan_workspace_once()
    assert scan1 is scan2
    chk._cached_walk = None
    assert chk._check_and_purge_stale_wals(auto_fix=True, ttl_seconds=10.0)["purged_count"] >= 2

    (ws / "nk_tracking" / "reports_and_briefs" / "sub").mkdir(parents=True)
    (ws / "nk_tracking" / "reports_and_briefs" / "sub" / "a.md").write_text("a", encoding="utf-8")
    (ws / "nk_tracking" / "reports_and_briefs" / "FORENSIC_INSPECTOR_1.md").write_text("tmp", encoding="utf-8")
    for idx in range(5):
        (ws / "nk_tracking" / "reports_and_briefs" / f"TAS_Report_{idx}.md").write_text("r", encoding="utf-8")
    assert chk._check_report_retention(auto_fix=False, max_per_target=3)["passed"] is False
    assert chk._check_report_retention(auto_fix=True, max_per_target=3)["pruned_count"] >= 3
    stashes = ws / "nk_tracking" / "handoff" / "stashes"
    stashes.mkdir(parents=True)
    (stashes / "a.patch").write_text("diff", encoding="utf-8")
    assert chk._check_staging_and_temp(auto_fix=True)["passed"] is True


@pytest.mark.fast
def test_preflight_ssot_governance_tombstones_and_parity(tmp_path: Path) -> None:
    """Verifica _check_ssot_governance con tombstone error, drift versione, duplicati e orfani."""
    pf_mod = load_script_by_relpath("preflight_health_check", "scripts/preflight_health_check.py")
    assert pf_mod.PreflightHealthChecker._normalize_tombstone_rel("././.agents/AGENTS.md") == ".agents/AGENTS.md"

    ws = tmp_path / "parent_b" / "NK_Hub"
    (ws / ".staging" / "nk_genome").mkdir(parents=True)
    (ws / ".staging" / "nk_genome" / "nk_registry_manifest.json").write_text(
        json.dumps({"version": "0.0.1", "skills_index": {}, "summary": {"total_skills": 17}}),
        encoding="utf-8",
    )
    chk = pf_mod.PreflightHealthChecker(workspace_root=ws)
    assert chk._get_expected_skills_count() == 17
    assert chk._resolve_overlay_file("nk_genome/nk_registry_manifest.json") is not None

    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps([123, ".agents/skills/DEL/SKILL.md"]), encoding="utf-8")
    assert chk._check_ssot_governance()["passed"] is False

    (ws / ".agents" / "skills" / "S1").mkdir(parents=True)
    (ws / ".agents" / "skills" / "DEL").mkdir(parents=True)
    (ws / ".agents" / "skills" / "DEL" / "SKILL.md").write_text("del", encoding="utf-8")
    (ws / ".agents" / "AGENTS.md").write_text("plain text without markers", encoding="utf-8")
    assert chk._check_ssot_governance()["passed"] is False

    (ws.parent / ".agents").mkdir(parents=True)
    (ws.parent / ".agents" / "AGENTS.md").write_text("outdated bridge", encoding="utf-8")
    (ws / ".agents" / "AGENTS.md").write_text("## [RULE-01] Uno\n## [RULE-01] Duplicato\n", encoding="utf-8")
    (ws / ".agents" / "skills" / "S1" / "SKILL.md").write_text("version: 0.0.1\n[RULE-999]\n", encoding="utf-8")
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"_version": "0.0.1", "metrics": {"unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )
    gov = chk._check_ssot_governance()
    assert gov["passed"] is False and "RULE-01" in gov["duplicate_rule_ids"]
    assert "RULE-999" in gov["orphan_rule_refs"] and gov["root_bridge_synced"] is False
    full = chk.run_full_check(auto_fix=False)
    assert full["status"] == "FAIL"


@pytest.mark.fast
def test_context_sentry_resilience_backscan_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica is_background_task_message, carry >64KB, swarm [Message] e CLI --conversation-id."""
    cs_mod = load_script_by_relpath("nk_context_sentry", "scripts/nk_context_sentry.py")
    assert cs_mod.NKContextSentry.is_background_task_message({"task": {"id": "1"}}, "") is True
    assert cs_mod.NKContextSentry.is_background_task_message({}, "sender=x task_id=2") is True
    assert cs_mod.NKContextSentry.is_background_task_message({}, "task id '3'") is True

    big_tr = tmp_path / "sentry_big.jsonl"
    huge_line = json.dumps({"source": "USER", "content": "U" * 70000})
    corrupt_cand = '{"source": "SYSTEM", "content": "<CONTEXT_SUMMARY> broken'
    recs = [
        huge_line,
        "",
        corrupt_cand,
        json.dumps({"source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "[Message] sender=sub content=hello"}),
        json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "ok", "tool_calls": [{"name": "read_file"}, {"name": ""}]}),
        json.dumps({"source": "TOOL", "type": "TOOL_RESULT", "status": "ERROR", "output": "FileNotFoundError"}),
    ]
    big_tr.write_text("\n".join(recs) + "\n", encoding="utf-8")
    sentry = cs_mod.NKContextSentry(workspace_root=tmp_path, profile="carbon")
    res = sentry.analyze_transcript(big_tr, actual_context_tokens=-5)
    assert res["blind_read_errors"] == 1 and res["actual_context_tokens"] == 0
    assert sentry.analyze_transcript(big_tr, actual_context_tokens=True)["actual_context_tokens"] is None

    monkeypatch.setattr(cs_mod, "locate_transcript", lambda *_a, **_k: ({"transcript_path": str(big_tr)}, 0))
    rc_cli, out_cli, _ = call_script_main_captured(cs_mod, ["--conversation-id", "conv_s1", "--verbose"])
    assert rc_cli == 0 and "NK-CONTEXT-SENTRY" in out_cli


@pytest.mark.fast
def test_vibe_router_transcript_discovery_and_cli_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica discovery brain/, seek >131KB, corrupt JSONL e _resolve_effective_cli_prompt."""
    vr_mod = load_script_by_relpath("vibe_sprint_router", "scripts/vibe_sprint_router.py")
    from _internal.vibe_sprint_router import transcript_and_cli as tc

    for k in ("NK_TRANSCRIPT_PATH", "ANTIGRAVITY_TRANSCRIPT_PATH", "NK_CONVERSATION_ID", "ANTIGRAVITY_CONVERSATION_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    brain = tmp_path / ".gemini" / "antigravity" / "brain"
    (brain / "not_a_dir.txt").parent.mkdir(parents=True)
    (brain / "not_a_dir.txt").write_text("x", encoding="utf-8")
    tp = brain / "conv_r" / ".system_generated" / "logs" / "transcript.jsonl"
    tp.parent.mkdir(parents=True)
    pad = json.dumps({"source": "MODEL", "content": "P" * 135000})
    tp.write_text(
        json.dumps({"source": "USER", "type": "USER_INPUT", "content": "prompt reale"}) + "\n"
        + pad + "\nplain_non_json\n{corrupt_json\n[1,2]\n"
        + json.dumps({"source": "MODEL", "content": "not user"}) + "\n",
        encoding="utf-8",
    )
    assert tc._read_latest_user_input_from_transcript() is None
    tp.write_text(
        json.dumps({"source": "USER", "type": "USER_INPUT", "content": "ultimo prompt"}) + "\n"
        + "\n{bad\n[1]\n",
        encoding="utf-8",
    )
    assert tc._read_latest_user_input_from_transcript() == "ultimo prompt"
    empty_t = tmp_path / "empty_vr.jsonl"
    empty_t.write_text("", encoding="utf-8")
    assert tc._read_latest_user_input_from_transcript(str(empty_t)) is None

    (tmp_path / "rel_prompt.txt").write_text("da file relativo", encoding="utf-8")
    ns_file = SimpleNamespace(prompt_file="rel_prompt.txt", stdin=False, classify_prompt=None, prompt="Vibe Sprint Change")
    assert tc._resolve_effective_cli_prompt(ns_file, workspace_root=tmp_path) == "da file relativo"
    ns_pos = SimpleNamespace(prompt_file=None, stdin=False, classify_prompt=None, prompt="Vibe Sprint Change", positional_prompt=["   "], meta_prompt_gate=False, no_gate=False, transcript=str(empty_t))
    assert tc._resolve_effective_cli_prompt(ns_pos, workspace_root=tmp_path) == "Vibe Sprint Change"
    assert vr_mod.VibeSprintRouter(workspace_root=tmp_path).workspace_root == tmp_path.resolve()


@pytest.mark.fast
def test_vibe_router_domain_matcher_shards_and_forensic_paths(tmp_path: Path) -> None:
    """Verifica shard rehydration edge cases, selector [3], skill match e audit forensic."""
    vr_mod = load_script_by_relpath("vibe_sprint_router", "scripts/vibe_sprint_router.py")
    from _internal.vibe_sprint_router import domain_matcher as dm

    assert dm._resolve_native_subagent("DOM-03", matched_skill="CustomSkill", text="") == "NK-Builder-Agent"
    ws = tmp_path / "ws_dm"
    shards_dir = ws / "nk_genome" / "shards"
    shards_dir.mkdir(parents=True)
    (shards_dir / "DOM-01.json").write_text(json.dumps({
        "domain": {"domain_id": "DOM-01", "name": "GOV", "primary_skill": "NK-Orchestrator", "keywords": ["gov"]},
        "skills_index": {"NK-Scribe-Memory": {"domain_id": "DOM-05", "domain_name": "SCR"}},
        "scripts_index": {"my_builder_tool.py": {"domain_id": "DOM-03"}},
        "intent_dispatch_table": {"k_list": ["NK-Orchestrator", "mode_a"], "k_str": "mode_d", "k_dict": {"domain_id": "DOM-02", "domain_name": "ARCH", "primary_agent": "NK-Ideator"}},
    }), encoding="utf-8")
    (shards_dir / "DOM-02.json").write_text("{corrupt", encoding="utf-8")
    (shards_dir / "DOM-03.json").write_text("[1, 2]", encoding="utf-8")
    man_p = ws / "nk_genome" / "nk_registry_manifest.json"
    man_p.write_text(json.dumps({"shards": {"DOM-00": "shards/DOM-00.json", "DOM-01": "shards/DOM-01.json", "DOM-02": "shards/DOM-02.json", "DOM-03": "shards/DOM-03.json", "DOM-04": "shards/DOM-04.json"}}), encoding="utf-8")

    router = vr_mod.VibeSprintRouter(workspace_root=ws)
    assert router.resolve_domain_from_manifest("[3]")["dashboard_node"] == 3
    assert router.resolve_domain_from_manifest("usa NK-Scribe-Memory adesso")["primary_skill"] == "NK-Scribe-Memory"
    assert router.resolve_domain_from_manifest("analizza my_builder_tool.py per incongruenze")["domain_id"] == "DOM-04"
    assert router.resolve_domain_from_manifest("esegui audit forense componente fastapi async")["domain_id"] == "DOM-04"
    assert router.resolve_domain_from_manifest("analizza incongruenze generiche")["domain_id"] == "DOM-04"
    man_p.write_text(json.dumps({
        "domains": {"DOM-01": {"name": "GOV", "primary_skill": "NK-Orchestrator", "keywords": []}},
        "intent_dispatch_table": {"dispatch_kw": {"domain_id": "DOM-02", "domain_name": "ARCH", "primary_agent": "NK-Ideator"}},
    }), encoding="utf-8")
    assert router.resolve_domain_from_manifest("dispatch_kw")["domain_id"] == "DOM-02"


@pytest.mark.fast
def test_bootstrap_root_hygiene_and_baseline_cache_branches(tmp_path: Path) -> None:
    """Verifica root_hygiene (.staging subdirs, fast_cache miss, src_app, verify_baseline)."""
    boot_mod = load_script_by_relpath("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
    from _internal.nk_session_bootstrap import root_hygiene as rh

    ws = tmp_path / "ws_boot_rh"
    (ws / ".staging" / "sub_empty").mkdir(parents=True)
    (ws / ".staging" / "sub_empty" / ".gitkeep").write_text("", encoding="utf-8")
    (ws / "scripts").mkdir()
    (ws / ".agents").mkdir()
    (ws / "src_app").mkdir()
    (ws / "src_app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (ws / ".gitignore").write_text("", encoding="utf-8")
    (ws / "README.md").write_text("hi\n", encoding="utf-8")
    (ws / "conftest.py").write_text("", encoding="utf-8")
    (ws / "nk_tracking").mkdir()
    (ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"pass_rate": 99.0}), encoding="utf-8")

    boot = boot_mod.NKSessionBootstrap(workspace_root=ws)
    assert rh.is_staging_dirty(boot) is False
    assert rh.has_root_file_pollution_quick(boot, False) is False
    hyg = rh.check_root_hygiene(boot, use_fast_cache=True, cached=None)
    assert hyg["status"] == "PASS" and hyg["is_external_project"] is True
    base = rh.verify_baseline(boot, cached={"baseline_stat": ["wrong", 0, 0], "checks": {"quality_baseline": {}}})
    assert base["passed"] is False and base["unit_pass_pct"] == 99.0


@pytest.mark.fast
def test_bootstrap_resilience_tail_large_file_and_warnings(tmp_path: Path) -> None:
    """Verifica resilience_tail >64KB carry, fallback_actual_ctx, compaction ts e warning."""
    load_script_by_relpath("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
    from _internal.nk_session_bootstrap import resilience_tail as rt

    _, _, tok1 = rt._extract_record_context_tokens({"actual_context_tokens": 1200})
    _, _, tok2 = rt._extract_record_context_tokens({"usage": {"input_tokens": 100, "cache_read_tokens": 50}})
    _, _, tok3 = rt._extract_record_context_tokens({"metadata": {"total_tokens": 900}})
    assert (tok1, tok2, tok3) == (1200, 150, 900)
    assert rt._analyze_step_record_resilience({"source": "MODEL", "tool_calls": ["bad_item"]})["burst"] is False

    empty_f = tmp_path / "empty_rt.jsonl"
    empty_f.write_bytes(b"")
    assert rt._inspect_tail_resilience_risks(empty_f)["effective_context_tokens"] == 0

    big_f = tmp_path / "big_rt.jsonl"
    line0 = json.dumps({"source": "MODEL", "input_tokens": 75000, "content": "C" * 70000})
    rows = [line0, "[1, 2]"] + [json.dumps({"source": "MODEL", "content": "x"}) for _ in range(13)]
    big_f.write_text("\n".join(rows) + "\n", encoding="utf-8")
    res_big = rt._inspect_tail_resilience_risks(big_f)
    assert res_big["effective_context_tokens"] == 75000

    ckpt_f = tmp_path / "ckpt_rt.jsonl"
    ckpt_f.write_text(
        json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "created_at": "2026-11-16T01:00:00Z", "content": "# Resuming from a compaction checkpoint"}) + "\n",
        encoding="utf-8",
    )
    assert rt._inspect_tail_resilience_risks(ckpt_f)["rpc_stream_burst_risk"] is False
    assert "Context warning" in (rt._build_context_warning("YELLOW", 10, 500, {}) or "")
    assert "KV-Cache cold risk" in (rt._build_context_warning("GREEN", 10, 500, {"kv_cache_cold_risk": True}) or "")


@pytest.mark.fast
def test_bootstrap_compaction_and_subagent_head_branches(tmp_path: Path) -> None:
    """Verifica compaction_and_head TV-03, fallback non-JSON, traffic light WARN/RED e carry >64KB."""
    load_script_by_relpath("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
    from _internal.nk_session_bootstrap import compaction_and_head as ch

    assert ch._compute_fast_traffic_light(160, 1000, profile="carbon")["status"] == "YELLOW"
    assert ch._compute_fast_traffic_light(10, 1000, profile="carbon", actual_context_tokens=160000)["status"] == "WARN"
    assert ch._compute_fast_traffic_light(10, 1000, profile="carbon", actual_context_tokens=210000)["status"] == "RED"

    assert ch.is_subagent_transcript_head(b"") is False
    assert ch.is_subagent_transcript_head(b"\n[1]\n" + json.dumps({"content": "<Agent System Instructions><subagent_reminder>"}).encode("utf-8")) is True
    assert ch.is_subagent_transcript_head(json.dumps({"content": "[Message] sender=a <env_capsule>"}).encode("utf-8")) is True
    assert ch.is_subagent_transcript_head(json.dumps({"source": "SYSTEM_SDK", "content": "plain"}).encode("utf-8")) is False

    many_lines = b"".join(json.dumps({"source": "MODEL", "content": "ok"}).encode("utf-8") + b"\n" for _ in range(7))
    assert ch.is_subagent_transcript_head(many_lines) is False
    assert ch.is_subagent_transcript_head(b"[1]\n" + json.dumps({"step_index": 3, "source": "SYSTEM"}).encode("utf-8")) is False
    assert ch.is_subagent_transcript_head(b'raw "source": "SYSTEM" nonjson\n') is True
    assert ch.is_subagent_transcript_head(b"raw [Message] sender=x <env_capsule>\n") is True

    big_cp = tmp_path / "big_cp.jsonl"
    ckpt = json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint"})
    big_cp.write_text(ckpt + "\n" + (json.dumps({"source": "MODEL", "content": "z" * 1000}) + "\n") * 75, encoding="utf-8")
    steps, _ = ch.count_post_compaction_binary(big_cp, big_cp.stat().st_size)
    assert steps >= 75

    big_nocp = tmp_path / "big_nocp.jsonl"
    big_nocp.write_text((json.dumps({"source": "MODEL", "content": "n" * 1000}) + "\n") * 75, encoding="utf-8")
    assert ch.count_post_compaction_binary(big_nocp, big_nocp.stat().st_size)[0] >= 75


@pytest.mark.fast
def test_bootstrap_transcript_prompt_discovery_and_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica transcript_prompt discovery, cache hit, carry >64KB e gate fallback."""
    boot_mod = load_script_by_relpath("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
    from _internal.nk_session_bootstrap import transcript_prompt as tp

    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "missing_hooks"))
    assert tp.infer_active_conversation_id(boot_mod.NKSessionBootstrap) == ""

    hooks_d = tmp_path / "hooks_dir"
    (hooks_d / "sub").mkdir(parents=True)
    (hooks_d / "probe_cid9.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_d))
    assert tp.infer_active_conversation_id(boot_mod.NKSessionBootstrap) == "cid9"

    assert tp.extract_user_prompt_from_line(b"[1, 2]") is None
    assert tp.has_newer_brain_directory(tmp_path / "a" / "b" / "c" / "transcript.jsonl") is False

    brain = tmp_path / ".gemini" / "antigravity" / "brain"
    tr_c1 = brain / "c1" / ".system_generated" / "logs" / "transcript.jsonl"
    tr_c1.parent.mkdir(parents=True)
    tr_c1.write_bytes(b"")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    boot = boot_mod.NKSessionBootstrap(workspace_root=tmp_path, conversation_id="c1")
    assert tp.resolve_bound_transcript_path(boot) == tr_c1
    assert tp.detect_latest_user_prompt(boot) is None

    tr_c1.write_text(
        json.dumps({"source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "start prompt"}) + "\n"
        + (json.dumps({"source": "MODEL", "content": "m" * 1000}) + "\n") * 70,
        encoding="utf-8",
    )
    assert tp.detect_latest_user_prompt(boot) == "start prompt"
    st = tr_c1.stat()
    cached = {"last_transcript_path": str(tr_c1), "transcript_mtime": st.st_mtime, "transcript_size": st.st_size, "cached_latest_user_prompt": "cached_p"}
    assert tp.detect_latest_user_prompt(boot, cached=cached) == "cached_p"
    monkeypatch.setenv("NK_META_PROMPT_GATE_MODE", "INVALID_MODE")
    assert tp.resolve_onboarding_and_gate_mode(boot)[1] == "CONFIRM"

    (brain / "c2_unflushed").mkdir()
    boot_none = boot_mod.NKSessionBootstrap(workspace_root=tmp_path)
    assert tp.find_recent_transcript(boot_none, brain) in (None, tr_c1)


@pytest.mark.fast
def test_safe_cleanup_dev_servers_cim_and_netstat_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica cleanup senza psutil (netstat + CIM), NK_External_Projects e dry_run."""
    cm = load_script_by_relpath("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
    assert cm._query_win32_cim_processes([]) == {}

    ext_ws = tmp_path / "NK_External_Projects" / "DemoSrv"
    ext_ws.mkdir(parents=True)
    monkeypatch.setattr(cm, "_workspace_root", tmp_path)
    assert cm._matches_workspace_paths("python.exe", "python srv.py", "", str(ext_ws / "srv.exe"), None) is True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])

    ready = ext_ws / "ready.flag"
    srv_py = ext_ws / "srv.py"
    srv_py.write_text(
        f"import os, pathlib, socket, time\ns = socket.socket()\ns.bind(('127.0.0.1', {port}))\ns.listen(1)\n"
        f"pathlib.Path(r'{ready}.tmp').write_text(str(os.getpid()), encoding='utf-8')\nos.replace(r'{ready}.tmp', r'{ready}')\ntime.sleep(10)\n",
        encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, "-B", str(srv_py)], cwd=str(ext_ws))
    try:
        deadline = time.perf_counter() + 3.0
        while not ready.exists() and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        listener_pid = int(ready.read_text(encoding="utf-8").strip())
        monkeypatch.setattr(cm, "_HAS_PSUTIL", False)
        monkeypatch.setattr(cm, "psutil", None)
        assert listener_pid in cm.scan_listening_port_range(port, port, workspace_root=ext_ws)
        assert listener_pid in cm.get_pids_listening_on_ports([port], workspace_root=ext_ws)
        assert cm.is_target_workspace_process(proc.pid, workspace_root=ext_ws) is True
        assert cm.is_target_workspace_process(listener_pid, workspace_root=ext_ws) is True
        assert cm.run_cleanup(workspace_root=ext_ws, dry_run=True, as_json=False, ports=[port]) == 0
        assert cm.run_cleanup(workspace_root=ext_ws, dry_run=False, as_json=False, ports=[port]) == 0
        proc.wait(timeout=3.0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2.0)


@pytest.mark.fast
def test_platform_runner_normalize_shell_timeout_and_cli(tmp_path: Path) -> None:
    """Verifica _normalize_python_command pytest, use_shell, timeout kill e main() senza newline."""
    pr = load_script_by_relpath("platform_runner", "scripts/platform_runner.py")
    assert pr._normalize_python_command(["pytest", "-q"]) == [sys.executable, "-u", "-m", "pytest", "-q"]
    assert "-m pytest -q" in str(pr._normalize_python_command("pytest -q"))
    assert pr._normalize_python_command(["echo", "hi"]) == ["echo", "hi"]
    assert pr._normalize_python_command(123) == 123  # type: ignore[arg-type]
    pr._kill_process_tree_sync(0)

    rc_sh, out_sh, _ = pr.safe_subprocess_run(f'"{sys.executable}" -c "print(\'sh_ok\')"', use_shell=True)
    assert rc_sh == 0 and "sh_ok" in out_sh
    rc_bad, _, err_bad = pr.safe_subprocess_run("echo a\necho b", use_shell=True)
    assert rc_bad == 1 and "EXECUTION_ERROR" in err_bad

    rc_to, _, err_to = pr.safe_subprocess_run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.1)
    assert rc_to == -1 and "[TIMEOUT]" in err_to

    cmd = f'"{sys.executable}" -c "import sys; sys.stdout.write(\'no_nl_out\'); sys.stderr.write(\'no_nl_err\')"'
    rc_cli, out_cli, err_cli = call_script_main_captured(pr, ["--cmd", cmd, "--cwd", str(tmp_path)])
    assert rc_cli == 0 and "no_nl_out\n" in out_cli and "no_nl_err\n" in err_cli


@pytest.mark.fast
def test_external_project_scaffolder_edge_paths_and_cli(tmp_path: Path) -> None:
    """Verifica isolamento null-byte/traversal, legacy genome error, force overwrite e CLI."""
    sc_mod = load_script_by_relpath("external_project_scaffolder", "scripts/external_project_scaffolder.py")
    with pytest.raises(ValueError):
        sc_mod.ExternalProjectScaffolder("GoodName", str(tmp_path / "x\x00y"))  # type: ignore[arg-type]
    trav_dir = "/".join((str(tmp_path), "a", "." + ".", "b"))
    with pytest.raises(ValueError):
        sc_mod.ExternalProjectScaffolder("GoodName", trav_dir)  # type: ignore[arg-type]

    proj = tmp_path / "ExtProj1"
    (proj / "genome").mkdir(parents=True)
    (proj / "genome" / "idea_canvas.md").write_bytes(b"\xff\xfeinvalid_utf8")
    scaf = sc_mod.ExternalProjectScaffolder("ExtProj1", proj)
    res1 = scaf.scaffold()
    assert res1["created_files_count"] > 0
    res2 = scaf.scaffold(force=True)
    assert res2["skipped_existing_count"] == 0 and res2["created_files_count"] > 0

    rc_txt, out_txt, _ = call_script_main_captured(
        sc_mod, ["--name", "CliProj", "--target", str(tmp_path / "CliProj"), "--dry-run"]
    )
    assert rc_txt == 0 and "[NK-SCAFFOLDER]" in out_txt
    rc_err, _, err_txt = call_script_main_captured(
        sc_mod, ["--name", "bad/name", "--target", str(tmp_path / "CliProj")]
    )
    assert rc_err == 1 and "[ERRORE]" in err_txt


@pytest.mark.fast
def test_registry_indexer_cli_filter_ratchet_and_cache_skills(tmp_path: Path) -> None:
    """Verifica cache_and_skills (.zip, deleted_files, tools multiline, card) e CLI ratchet/filter."""
    idx_mod = load_script_by_relpath("nk_registry_indexer", "scripts/nk_registry_indexer.py")
    from _internal.nk_registry_indexer import cache_and_skills as cs
    zip_f = tmp_path / "blob.zip"
    zip_f.write_bytes(b"PK" + b"0" * 300)
    hcache: Dict[Any, str] = {}
    h1 = cs.compute_sha256_impl(zip_f, hash_cache=hcache)
    h2 = cs.compute_sha256_impl(zip_f, hash_cache=hcache)
    assert h1 == h2 and len(hcache) == 1

    meta_a = cs.parse_skill_metadata_impl(
        "---\nname: S1\ntools:\n  - read_file\n  - edit_file\n---\n<yaml_metadata_card>\nsector: SEC\nenable_mcp_tools: true\ntools: [a, b]\n</yaml_metadata_card>\n"
    )
    meta_b = cs.parse_skill_metadata_impl("---\ntools: read_file, write_file\n---\n")
    meta_c = cs.parse_skill_metadata_impl("---\ntools: [\n  read_file\n]\n---\n")
    assert meta_a["enable_mcp_tools"] is True and meta_a["sector"] == "SEC"
    assert meta_b["tools"] == ["read_file", "write_file"] and meta_c["tools"] == ["["]

    ws = tmp_path / "ws_idx_cs"
    for d in (".staging/.agents/skills/SkA", ".agents/skills/SkA", ".agents/skills/SkDel", ".agents/skills/SkBad", "scripts", "nk_genome", "nk_docs_and_setup", ".agents/agents"):
        (ws / d).mkdir(parents=True)
    (ws / ".agents/skills/not_a_dir.txt").write_text("x", encoding="utf-8")
    (ws / ".staging/.deleted_files.json").write_text(json.dumps([".agents/skills/SkDel/SKILL.md"]), encoding="utf-8")
    (ws / ".staging/.agents/skills/SkA/SKILL.md").write_text("---\nname: SkA\ndomain_id: DOM-01\n---\n" + ("a" * 140), encoding="utf-8")
    (ws / ".agents/skills/SkA/SKILL.md").write_text("---\nname: SkA_prod\n---\n", encoding="utf-8")
    (ws / ".agents/skills/SkDel/SKILL.md").write_text("---\nname: SkDel\n---\n", encoding="utf-8")
    (ws / ".agents/skills/SkBad/SKILL.md").write_text("---\nname: SkBad\ndomain_id: DOM-99\n---\n" + ("b" * 140), encoding="utf-8")

    indexer = idx_mod.NKRegistryIndexer(workspace_root=ws, global_config_dir=tmp_path / "gcfg")
    skills_1 = indexer.scan_skills()
    skills_2 = indexer.scan_skills()
    assert "SkDel" not in skills_1 and skills_2["SkBad"]["domain_id"] == "DOM-02"

    (ws / ".staging/.deleted_files.json").write_text("{corrupt", encoding="utf-8")
    assert indexer._load_staging_deleted_paths() == set()

    assert call_script_main_captured(idx_mod, ["--root", str(ws), "--apply-global-filter"])[0] == 0
    (ws / ".agents/skills/SkBad/SKILL.md").unlink()
    assert call_script_main_captured(idx_mod, ["--root", str(ws), "--sync"])[0] == 1
    assert call_script_main_captured(idx_mod, ["--root", str(ws), "--apply-global-filter"])[0] == 1


@pytest.mark.fast
def test_registry_indexer_shards_and_rehydration_edges(tmp_path: Path) -> None:
    """Verifica compattazione shard mode 0..3, DOM-00 cap e reidratazione malformata/parziale."""
    idx_mod = load_script_by_relpath("nk_registry_indexer", "scripts/nk_registry_indexer.py")
    from _internal.nk_registry_indexer import shards as sh

    sk_c = sh._compact_skill_entry({"domain_id": "DOM-01", "enable_mcp_tools": True, "sha256": "x"}, "GOV", compact_mode=1)
    sc_c = sh._compact_script_entry({"domain_id": "DOM-03", "sha256": "y", "source_layer": "staging"}, compact_mode=2)
    sc_0 = sh._compact_script_entry({"domain_id": "DOM-03", "sha256": "y"}, compact_mode=0)
    assert sk_c["enable_mcp_tools"] is True and sc_c["source_layer"] == "staging" and "description" not in sc_0

    raw_shard = sh._serialize_domain_shard_with_cap(
        "DOM-01",
        {"name": "GOV", "primary_skill": "S1", "title": "T", "description": "D", "keywords": [f"k{i}" for i in range(12)]},
        {"S1": {"domain_id": "DOM-01", "sha256": "a", "tools": ["t1"]}},
        {"a.py": {"domain_id": "DOM-01", "sha256": "b", "classes": ["C1"]}},
        {"Ag1": {"domain_id": "DOM-01", "sha256": "c", "tools": ["read_file"]}},
        {"k0": ["S1", "mode_a"], "k1": ["Other", "mode_d"]},
        max_bytes=40,
    )
    assert '"k0":"mode_a"' in raw_shard

    ws = tmp_path / "ws_sh"
    (ws / ".staging" / "tests").mkdir(parents=True)
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["tests/test_skip.py"]), encoding="utf-8")
    (ws / ".staging" / "tests" / "test_skip.py").write_text("", encoding="utf-8")
    (ws / ".staging" / "tests" / "test_keep.py").write_text("", encoding="utf-8")
    indexer = idx_mod.NKRegistryIndexer(workspace_root=ws, global_config_dir=tmp_path / "gcfg")
    assert sh._collect_test_suite_names(indexer) == ["test_keep.py"]

    docs_big = {f"doc_{i}.md": {"relative_path": f"nk_docs_and_setup/doc_{i}.md", "size_bytes": i, "sha256": "a" * 64} for i in range(60)}
    _, shards_out = sh.build_shards_and_slim_manifest(indexer, {"domains": {}, "docs_and_setup_index": docs_big})
    assert "size_bytes" not in json.loads(shards_out["DOM-00.json"])["docs_and_setup_index"]["doc_0.md"]

    sh_dir = ws / "nk_genome" / "shards"
    sh_dir.mkdir(parents=True)
    (sh_dir / "DOM-00.json").write_text(json.dumps({"domain_id": "DOM-00"}), encoding="utf-8")
    (sh_dir / "DOM-01.json").write_text(json.dumps({"skills_index": {"bad": "x"}, "scripts_index": {"bad": "y"}, "native_agents_index": {"bad": "z"}, "intent_dispatch_table": {"d_kw": {"domain_id": "DOM-01"}}}), encoding="utf-8")
    man_file = ws / "nk_genome" / "nk_registry_manifest.json"
    merged = sh.rehydrate_manifest_from_shards(man_file, {"domains": {"DOM-01": {"name": "GOV"}, "DOM-99": {"name": "EXTRA"}}, "shards": {"DOM-00": "shards/DOM-00.json", "DOM-01": "shards/DOM-01.json"}})
    assert "DOM-99" in merged["domains"] and merged["intent_dispatch_table"]["d_kw"]["domain_id"] == "DOM-01"


@pytest.mark.fast
def test_registry_indexer_governance_and_verify_branches(tmp_path: Path) -> None:
    """Verifica governance_and_verify (EOL sha, GT-14/CRIT-01, dispatch/agent drift e verify cache)."""
    idx_mod = load_script_by_relpath("nk_registry_indexer", "scripts/nk_registry_indexer.py")
    from _internal.nk_registry_indexer import governance_and_verify as gv

    f_eol = tmp_path / "eol.txt"
    f_eol.write_bytes(b"a\nb\n")
    crlf_sha = hashlib.sha256(b"a\r\nb\r\n").hexdigest()
    lf_sha = hashlib.sha256(b"a\nb\n").hexdigest()
    assert gv.sha256_matches_eol_normalized_impl(f_eol, "other", "") is False
    assert gv.sha256_matches_eol_normalized_impl(f_eol, "other", crlf_sha) is True
    f_eol.write_bytes(b"a\r\nb\r\n")
    assert gv.sha256_matches_eol_normalized_impl(f_eol, "other", lf_sha) is True

    ws = tmp_path / "ws_gov"
    for d in ("genome", "scripts", ".agents/skills/Sk1", ".agents/agents/NK-Specifier-Agent"):
        (ws / d).mkdir(parents=True)
    (ws / ".agents/agents/NK-Specifier-Agent/agent.md").write_text("---\nenable_mcp_tools: true\ntools: [run_command]\n---\n", encoding="utf-8")
    (ws / ".agents/skills/Sk1/SKILL.md").write_text("---\nenable_mcp_tools: true\ntools: [mcp_fake]\n---\n", encoding="utf-8")
    (ws / "scripts/s1.py").write_text("x = 1\n", encoding="utf-8")
    indexer = idx_mod.NKRegistryIndexer(workspace_root=ws, global_config_dir=tmp_path / "gcfg")

    issues_gt = gv.audit_gt14_crit01_entries_impl(
        indexer,
        agent_map=indexer._collect_priority_native_agents(),
        skill_map=indexer._collect_priority_skills(),
        manifest_agents={"NK-Specifier-Agent": "not_dict"},
        manifest_skills={"Sk1": "not_dict"},
    )
    assert any("CRIT-01" in i for i in issues_gt) and any("GT-14" in i for i in issues_gt)

    (ws / "genome" / "nk_registry_manifest.json").write_text(
        json.dumps({
            "version": "6.4.0-Carbon",
            "domains": {"DOM-02": {"scripts": []}, "DOM-03": {}, "DOM-04": {}, "DOM-05": {}},
            "skills_index": {},
            "scripts_index": {},
            "native_agents_index": {"NK-Specifier-Agent": {"sha256": "wrong_sha"}},
            "intent_dispatch_table": {"bad_ent": "not_dict", "miss_dom": {"domain_id": "DOM-99"}},
            "global_hygiene_profile": {},
        }),
        encoding="utf-8",
    )
    v_res = indexer.verify()
    assert v_res["passed"] is False and v_res["warnings"]

    indexer._last_verify_cache = (time.perf_counter(), {"status": "VALID", "passed": True, "elapsed_ms": 0.1})
    orig_root = gv._DEFAULT_WORKSPACE_ROOT
    try:
        gv._DEFAULT_WORKSPACE_ROOT = ws.resolve()
        assert gv.verify_impl(indexer)["status"] == "VALID"
    finally:
        gv._DEFAULT_WORKSPACE_ROOT = orig_root


@pytest.mark.fast
def test_registry_indexer_hygiene_filter_and_scripts_agents(tmp_path: Path) -> None:
    """Verifica hygiene_filter quarantine/overwrite e scripts_and_agents priority/AST/YAML."""
    idx_mod = load_script_by_relpath("nk_registry_indexer", "scripts/nk_registry_indexer.py")
    from _internal.nk_registry_indexer import hygiene_filter as hf, scripts_and_agents as sa

    ws = tmp_path / "ws_sa"
    gcfg = ws / "gcfg"
    gcp_sk = idx_mod.GCP_DATA_SKILLS[0]
    dev_sk = idx_mod.DEV_UTILITY_SKILLS[0]
    for p in (
        gcfg / "skills" / gcp_sk,
        gcfg / "plugins" / "gcp-data-cloud-plugin" / "skills" / gcp_sk,
        gcfg / "skills" / dev_sk,
        gcfg / "plugins" / "dev-utilities-plugin" / "skills" / dev_sk,
        gcfg / "plugins" / "science",
        gcfg / "plugins" / "android-cli-plugin",
    ):
        p.mkdir(parents=True)
    (gcfg / "skills" / ".datacloud_skills_manifest").write_text("src", encoding="utf-8")
    (gcfg / "plugins" / "gcp-data-cloud-plugin" / "skills" / ".datacloud_skills_manifest").write_text("dst", encoding="utf-8")
    (gcfg / "plugins" / "science" / "plugin.json").write_text(json.dumps({"name": "science"}), encoding="utf-8")
    (gcfg / "plugins" / "android-cli-plugin" / "plugin.json").write_text("{corrupt", encoding="utf-8")
    (gcfg / "config.json").write_text("{corrupt", encoding="utf-8")

    ws_d = gcfg.parent
    for d in (".staging/scripts/schemas", "scripts/schemas", ".staging/.agents/agents/Ag1", ".agents/agents/Ag1", ".agents/agents/AgDel"):
        (ws_d / d).mkdir(parents=True)
    (ws / ".staging/.deleted_files.json").write_text(json.dumps(["scripts/s_del.py", "scripts/schemas/sch_del.py", ".agents/agents/AgDel/agent.md"]), encoding="utf-8")
    for rel in (".staging/scripts/s1.py", "scripts/s1.py", "scripts/s_del.py", ".staging/scripts/schemas/sch1.py", "scripts/schemas/sch1.py", "scripts/schemas/sch_del.py"):
        (ws / rel).write_text('"""\nModulo: test\nDescrizione reale.\n"""\ndef f():\n    add_argument("--flag", 123)\n', encoding="utf-8")
    (ws / ".agents/agents/not_dir.txt").write_text("x", encoding="utf-8")
    (ws / ".staging/.agents/agents/Ag1/agent.md").write_text("---\ntools:\n  - read_file\n---\n", encoding="utf-8")
    (ws / ".agents/agents/Ag1/agent.md").write_text("---\ntools: read_file, send_message\n---\n", encoding="utf-8")
    (ws / ".agents/agents/AgDel/agent.md").write_text("---\ntools: [\n  read_file\n]\n---\n", encoding="utf-8")

    indexer = idx_mod.NKRegistryIndexer(workspace_root=ws, global_config_dir=gcfg)
    f_res1 = hf.apply_global_filter_impl(indexer)
    assert f_res1["config_corrupt"] is True and f_res1["moved_gcp_skills"] == 1
    (gcfg / "config.json").write_text(json.dumps({"plugins": "bad_type"}), encoding="utf-8")
    assert hf.apply_global_filter_impl(indexer)["applied"] is True
    (gcfg / "skills" / gcp_sk).mkdir(parents=True)
    (gcfg / "skills" / gcp_sk / "SKILL.md").write_text("# gcp", encoding="utf-8")
    indexer._readonly_filter_applied = True
    assert hf.scan_global_hygiene_profile_impl(indexer, 14)["disabled_external_skills_count"] >= 1

    scripts_map = sa.collect_priority_scripts_impl(indexer)
    agents_map = sa.collect_priority_native_agents_impl(indexer)
    assert "s_del.py" not in scripts_map and "schemas/sch_del.py" not in scripts_map and "AgDel" not in agents_map
    sc_meta = sa.extract_script_metadata_impl(ws / ".staging/scripts/s1.py")
    assert "--flag" in sc_meta["cli_flags"] and sc_meta["description"] == "Descrizione reale."
    assert sa.parse_native_agent_metadata_impl("---\ntools:\n  - read_file\n---\n")["tools"] == ["read_file"]
    assert sa.parse_native_agent_metadata_impl("---\ntools: read_file, send_message\n---\n")["tools"] == ["read_file", "send_message"]
    assert sa.parse_native_agent_metadata_impl("---\ntools: [\n  read_file\n]\n---\n")["tools"] == ["read_file"]


@pytest.mark.fast
def test_extra_handoff_discovery_staging_and_dry_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _discover_default_transcript, righe vuote cursore e varianti CLI dry-run/auto."""
    hm = load_script_by_relpath("nk_session_handoff", "scripts/nk_session_handoff.py")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert hm._discover_default_transcript() == ""

    brain = tmp_path / ".gemini" / "antigravity" / "brain"
    brain.mkdir(parents=True)
    (brain / "plain.txt").write_text("x", encoding="utf-8")
    (brain / "empty_conv").mkdir()
    assert hm._discover_default_transcript() == ""

    sub_tr = brain / "conv_sub" / ".system_generated" / "logs" / "transcript.jsonl"
    sub_tr.parent.mkdir(parents=True)
    sub_tr.write_text("<SYSTEM_MESSAGE> sender=parent\n", encoding="utf-8")
    main_tr = brain / "conv_main" / ".system_generated" / "logs" / "transcript.jsonl"
    main_tr.parent.mkdir(parents=True)
    main_tr.write_text(json.dumps({"source": "USER", "content": "ok"}) + "\n", encoding="utf-8")
    assert Path(hm._discover_default_transcript()).exists()

    cur_tp = tmp_path / "cur_extra.jsonl"
    cur_tp.write_text(json.dumps({"source": "MODEL", "content": "a"}) + "\n", encoding="utf-8")
    hm._inspect_transcript_fast(str(cur_tp))
    with open(cur_tp, "a", encoding="utf-8") as fh:
        fh.write("\n" + json.dumps({"source": "MODEL", "content": "b"}) + "\n   ")
    assert hm._inspect_transcript_fast(str(cur_tp))[0] == 2
    with open(cur_tp, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"source": "MODEL", "content": "no_tok"}))
    assert hm._inspect_transcript_fast(str(cur_tp))[0] == 3

    ws = tmp_path / "ws_dry_var"
    (ws / ".staging" / "empty_sub").mkdir(parents=True)
    (ws / "nk_tracking").mkdir()
    (ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0}}), encoding="utf-8")
    assert hm._has_dirty_staging_inprocess(ws) is False
    assert call_script_main_captured(hm, ["--root", str(ws), "--dry-run", "--transcript", str(cur_tp)])[0] == 0
    assert call_script_main_captured(hm, ["--root", str(ws), "--auto-checkpoint", "--transcript", str(cur_tp)])[0] == 0


@pytest.mark.fast
def test_extra_transcript_tools_and_compliance_edges(tmp_path: Path) -> None:
    """Copre rami extra in nk_transcript_tools e nk_compliance_checker."""
    tt = load_script_by_relpath("nk_transcript_tools", "scripts/nk_transcript_tools.py")
    cc = load_script_by_relpath("nk_compliance_checker", "scripts/nk_compliance_checker.py")

    assert tt.clean_tool_path('"[1]"') == "[1]"
    assert tt.clean_tool_str('"[1]"') == "[1]"
    assert tt._extract_call_id({"id": "   ", "tool_result": {"x": 1}, "tool_results": [{"x": 1}]}) == ""
    assert cc._extract_call_correlation_id({"id": True, "tool_response": {"id": True}}) == ""
    assert cc._pop_correlated_tool_call(["not_dict"], {"id": "c1"}) == "not_dict"
    assert cc.NKComplianceChecker._extract_session_identifier(tmp_path / "brain" / "transcript.jsonl") == "brain"

    blanks_f = tmp_path / "blanks20.jsonl"
    blanks_f.write_text("\n" * 22, encoding="utf-8")
    assert tt.is_subagent_transcript_file(blanks_f) is False

    tr_nosh = tmp_path / "nosh.jsonl"
    tr_nosh.write_text(
        json.dumps({"source": "MODEL", "truncated_fields": [], "content": "a"}) + "\n"
        + json.dumps({"source": "MODEL", "truncated_fields": ["content"], "content": "b"}) + "\n",
        encoding="utf-8",
    )
    assert len(tt.load_transcript_records(tr_nosh)) == 2
    assert tt.check_evidence(None, message="ok")[1] == 0

    ws = tmp_path / "ws_plain_tests"
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_a.py").write_text("assert True\n", encoding="utf-8")
    assert tt.handle_oracle_lock("create", ws / "tests", ws / "lock.json")[1] == 0

    comp_tr = tmp_path / "comp_extra.jsonl"
    comp_tr.write_text(
        json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "ok", "tool_calls": [
            {"name": "send_message", "args": {"Message": "short"}},
            {"name": "manage_task", "args": {"Action": "list"}},
            {"name": "manage_subagents", "args": {"Action": "kill"}},
            {"name": "run_command", "args": {"CommandLine": "pytest NK_External_Projects/p1"}},
            {"name": "run_command", "args": {"CommandLine": "echo x > NK_External_Projects/p1/PATCH_NOTES.md"}},
        ]}) + "\n",
        encoding="utf-8",
    )
    assert tt.analyze_compliance(comp_tr)["oversized_swarm_messages"] == 0
    chk = cc.NKComplianceChecker(workspace_root=ws)
    assert chk._lookup_rsi_telemetry_score(None) == (False, 0)
    assert chk.audit_transcript(comp_tr)["status"] in ("PASS", "FAIL")


@pytest.mark.fast
def test_extra_preflight_and_sentry_deep_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre main() preflight, governance missing files/bridge synced e sentry carry senza NL."""
    pf = load_script_by_relpath("preflight_health_check", "scripts/preflight_health_check.py")
    cs = load_script_by_relpath("nk_context_sentry", "scripts/nk_context_sentry.py")

    ws = tmp_path / "wrap_p" / "NK_Hub"
    (ws.parent / ".agents").mkdir(parents=True)
    (ws.parent / ".agents" / "AGENTS.md").write_text(
        f"v{pf.VERSION} 11 skill 6 sub-agenti 10 nodi", encoding="utf-8"
    )
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "AGENTS.md").write_text(f"{pf.VERSION}\n## [RULE-01] Ok\n", encoding="utf-8")
    chk = pf.PreflightHealthChecker(workspace_root=ws)
    gov = chk._check_ssot_governance()
    assert gov["passed"] is False and gov["root_bridge_synced"] is True
    assert call_script_main_captured(pf, ["--root", str(ws), "--check-only", "--json"])[0] == 1

    no_nl_tr = tmp_path / "sentry_nonl.jsonl"
    no_nl_tr.write_bytes(b'{"source": "USER", "content": "' + (b"X" * 70000) + b'"}')
    assert cs.NKContextSentry._find_last_compaction_offset(no_nl_tr) == 0

    ok_tr = tmp_path / "sentry_ok.jsonl"
    ok_tr.write_text(
        "[1, 2]\n"
        + json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file"}]}) + "\n"
        + json.dumps({"source": "TOOL", "status": "OK", "output": "ok"}) + "\n",
        encoding="utf-8",
    )
    sentry = cs.NKContextSentry(workspace_root=tmp_path)
    assert sentry.analyze_transcript(ok_tr)["blind_read_errors"] == 0
    assert sentry.analyze_transcript(ok_tr, preloaded_records=["bad_item"])["status"] == "ERROR"  # type: ignore[list-item]
    monkeypatch.delenv("NK_CONVERSATION_ID", raising=False)
    assert call_script_main_captured(cs, [])[0] == 0


@pytest.mark.fast
def test_extra_router_and_bootstrap_deep_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre domain_matcher large prompt/empty shards e bootstrap root_hygiene/resilience/head."""
    vr = load_script_by_relpath("vibe_sprint_router", "scripts/vibe_sprint_router.py")
    boot_mod = load_script_by_relpath("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
    from _internal.vibe_sprint_router import domain_matcher as dm
    from _internal.nk_session_bootstrap import (
        compaction_and_head as ch,
        resilience_tail as rt,
        root_hygiene as rh,
        transcript_prompt as tp,
    )

    assert dm._token_matches_keyword("c++", "usa c++ adesso", {"c++"}) is True
    assert dm._token_matches_keyword("c++", "usa c++ adesso", None) is False
    many_false = ("auditore " * 35) + ("x" * 16500) + " audit"
    assert dm._token_matches_keyword("audit", many_false, None, min_sub_len=99) is True

    ws_empty = tmp_path / "ws_dm_empty"
    (ws_empty / "nk_genome").mkdir(parents=True)
    man_e = ws_empty / "nk_genome" / "nk_registry_manifest.json"
    man_e.write_text("{corrupt", encoding="utf-8")
    assert dm._rehydrate_router_manifest_shards(man_e, {"shards": {}}) == {"shards": {}}
    monkeypatch.setattr(dm, "_DEFAULT_WORKSPACE_ROOT", ws_empty)
    assert vr.VibeSprintRouter(workspace_root=ws_empty)._load_registry_manifest() == {}
    assert vr.VibeSprintRouter(workspace_root=ws_empty).resolve_domain_from_manifest("esegui audit forense fastapi tas")["domain_id"] == "DOM-04"

    boot = boot_mod.NKSessionBootstrap(workspace_root=tmp_path / "miss_ws")
    with monkeypatch.context() as mp:
        mp.setattr(rh.os, "scandir", lambda _p: (_ for _ in ()).throw(OSError("denied")))
        assert rh.check_root_hygiene(boot)["status"] == "PASS"

    assert rt._extract_record_context_tokens({"metadata": {"input_tokens": 0, "total_tokens": 0}})[2] == 0
    big_ws = tmp_path / "big_ws_rt.jsonl"
    big_ws.write_text((" " * 70000) + "\n" + json.dumps({"source": "MODEL", "content": "y"}) + "\n", encoding="utf-8")
    assert rt._inspect_tail_resilience_risks(big_ws)["effective_context_tokens"] == 0

    assert ch.is_subagent_transcript_head(json.dumps({"source": "SYSTEM_SDK", "content": "[Message] sender=parent"}).encode("utf-8")) is True
    assert ch.is_subagent_transcript_head(b"[Message] only\n") is False
    assert tp.has_newer_brain_directory(tmp_path / "a" / "b" / "c" / "tr.jsonl") is False
    b_dir = tmp_path / "brain_tp"
    b_dir.mkdir()
    (b_dir / "file_not_dir.txt").write_text("x", encoding="utf-8")
    sub_f = b_dir / "c_sub" / ".system_generated" / "logs" / "transcript.jsonl"
    sub_f.parent.mkdir(parents=True)
    sub_f.write_text(json.dumps({"source": "SYSTEM", "content": "<subagent_reminder>s"}) + "\n", encoding="utf-8")
    boot_tp = boot_mod.NKSessionBootstrap(workspace_root=tmp_path)
    boot_tp.conversation_id = ""
    assert tp.find_recent_transcript(boot_tp, b_dir) == sub_f


@pytest.mark.fast
def test_extra_cleanup_runner_and_indexer_deep_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre cleanup non-win32/CLI, platform_runner .bat/quotes e indexer hygiene/skills."""
    cm = load_script_by_relpath("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
    pr = load_script_by_relpath("platform_runner", "scripts/platform_runner.py")
    idx_mod = load_script_by_relpath("nk_registry_indexer", "scripts/nk_registry_indexer.py")
    from _internal.nk_registry_indexer import cache_and_skills as cs, hygiene_filter as hf

    monkeypatch.setattr(cm, "_HAS_PSUTIL", False)
    monkeypatch.setattr(cm, "psutil", None)
    tok = cm._CIM_BATCH_CACHE.set({})
    try:
        assert cm.is_target_workspace_process(999999, workspace_root=tmp_path) is False
    finally:
        cm._CIM_BATCH_CACHE.reset(tok)
    monkeypatch.setattr(cm.sys, "platform", "linux")
    assert cm.is_target_workspace_process(999999, workspace_root=tmp_path) is False
    assert call_script_main_captured(cm, ["--workspace-root", str(tmp_path), "--ports", "8000", "--dry-run"])[0] == 0

    assert pr.safe_subprocess_run("run.bat arg&bad")[0] == 1
    assert pr.safe_subprocess_run('"unclosed_quote')[0] == 1

    ws = tmp_path / "ws_idx_ex"
    (ws / ".staging").mkdir(parents=True)
    (ws / ".staging" / ".deleted_files.json").write_text("{}", encoding="utf-8")
    idx = idx_mod.NKRegistryIndexer(workspace_root=ws, global_config_dir=ws / "no_gcfg")
    assert idx._load_staging_deleted_paths() == set()
    assert cs.parse_skill_metadata_impl("---\ntools:\nname: A\n---\n<yaml_metadata_card>\nsector: S\n</yaml_metadata_card>\n")["name"] == "A"
    assert hf.scan_global_hygiene_profile_impl(idx, 14)["config_exists"] is False

    gcfg = ws / "gcfg_ok"
    (gcfg / "plugins" / "science").mkdir(parents=True)
    (gcfg / "plugins" / "science" / "plugin.json").write_text("{bad", encoding="utf-8")
    (gcfg / "config.json").write_text("[1, 2]", encoding="utf-8")
    idx2 = idx_mod.NKRegistryIndexer(workspace_root=ws, global_config_dir=gcfg)
    assert hf.apply_global_filter_impl(idx2)["config_corrupt"] is True
    (gcfg / "config.json").write_text(json.dumps({"plugins": {"science": {"enabled": True}}}), encoding="utf-8")
    assert hf.apply_global_filter_impl(idx2)["applied"] is True
    assert hf.scan_global_hygiene_profile_impl(idx2, 14)["external_skills_count"] == 0

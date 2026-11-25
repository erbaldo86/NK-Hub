# -*- coding: utf-8 -*-
"""
Suite Zero-Mock ultra-veloce (<80ms) per contratti retrocompatibili v1/v2 e W6-TOOLING.
Modulo: tests/test_tensor_v1_contracts.py.
Blocca regressioni su compute_delta (peso 12), compute_fitness, compute_fitness_v2,
RSIIterationRecord(exclude_none=True), _has_python_diff_signal(diff_aware) e sanitizers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time
from typing import Any
import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

_rsi_mod = load_nk_script_module("rsi_convergence_engine")
_hook_mod = load_nk_script_module("nk_hook_gate")

from _internal.nk_common.staging_manifest import canonical_json_bytes  # noqa: E402
from _internal.nk_compliance_checker import holdout_turn_detector as htd_mod  # noqa: E402
from _internal.rsi_convergence_engine.constants import RSIDefectVector  # noqa: E402
from _internal.rsi_convergence_engine.ecosystem_verify import _compute_ecosystem_q_v2, _has_python_diff_signal  # noqa: E402
from _internal.rsi_convergence_engine.loop_and_cove import compute_record_hash_impl  # noqa: E402
from _internal.rsi_convergence_engine.profiles import RSIProfileRegistry, compute_candidate_sort_key, compute_delta, compute_fitness, compute_fitness_v2  # noqa: E402
from _internal.rsi_convergence_engine.report_sanitizers import audit_coverage_report_payload, audit_dast_report_payload, audit_mutation_report_payload, audit_sast_report_payload  # noqa: E402
from _internal.tensor_rsi import gate_mapper as tr_gm, materializer as tr_mat  # noqa: E402
from _internal.tensor_rsi.co_executor import TensorRSICoExecutor, run_tensor_cli  # noqa: E402
from _internal.tensor_rsi.gate_mapper import map_gates, write_active_session  # noqa: E402
from _internal.tensor_rsi.oracle_bridge import snapshot_from_oracle_result  # noqa: E402
from _internal.tensor_rsi.policy_tensor import build_policy_cell  # noqa: E402
from _internal.tensor_rsi.schemas import MetricSnapshot, PrimaryInvariantVector, SecondaryQualityVector, TensorRSIStateTicket  # noqa: E402
from _internal.tensor_rsi.ticket_auth import TicketAuthError, commit_session_ticket  # noqa: E402
from _internal.win32_2pc_engine.constants import TwoPhaseCommitError  # noqa: E402
from _internal.win32_2pc_engine.guards_sandbox import validate_sandbox_report_not_dry_run  # noqa: E402
from schemas.nk_ipc_contracts import RSIIterationRecord, RSISessionReport  # noqa: E402


def _write_chained_ledger_rows(ledger_p: Path, clade_id: str, count: int) -> None:
    """Scrive righe ledger SHA-256 concatenate valide per test fast senza loop fsync."""
    ledger_p.parent.mkdir(parents=True, exist_ok=True)
    prev_h, lines = "0" * 64, []
    for idx in range(count):
        body = {
            "session_id": f"S_HIST_{idx:02d}", "clade_id": clade_id, "iteration": idx % 3,
            "intent_track": "CODE_TRACK", "classified_track": "IMPROVEMENT", "model_tier": "NEON",
            "acs_zone": "Z0", "operator": "SURGICAL_LOCAL_PATCH", "regime": "COLD",
            "predicted_accept_prob": 0.9, "accepted": False, "reward": 0.0,
            "directional_projection": 0.0, "q_v2_before": 88.0, "q_v2_after": 88.0,
            "dry_run": 0, "deception_gaming_count": 0, "baseline_state_sha256": "a" * 64,
            "candidate_state_sha256": "a" * 64, "prev_hash": prev_h, "timestamp_utc": 1750000000.0 + idx,
        }
        rec_h = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        lines.append(json.dumps({**body, "record_hash": rec_h}))
        prev_h = rec_h
    ledger_p.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.fast
def test_v1_compute_delta_weight_12_and_fitness_contracts() -> None:
    """Preserva peso 12 per semantic_drift_findings, compute_fitness e alias legacy."""
    assert compute_delta(RSIDefectVector(semantic_drift_findings=1)) == 12
    assert compute_delta(RSIDefectVector(sast_critical=1)) == 15
    assert compute_delta(RSIDefectVector(hallucinated_refs=1)) == 25
    clean = RSIDefectVector(tests_passed=10, tests_total=10)
    assert (compute_delta(clean), compute_fitness(clean)) == (0, 100.0)
    assert compute_fitness(RSIDefectVector(tests_passed=10, tests_total=10, deception_gaming_count=1)) == 0.0
    assert compute_fitness(RSIDefectVector(tests_passed=10, tests_total=10, unmeasured_components=["x"])) <= 49.9
    assert compute_fitness(RSIDefectVector(tests_failed=2), profile="spec_rsi") < 50.0
    assert (RSIProfileRegistry.get("producer").name, RSIProfileRegistry.get_strict("orchestrator").name) == ("code_rsi", "code_rsi")
    assert RSIProfileRegistry.is_legacy_alias("producer") is True
    with pytest.raises(ValueError):
        RSIProfileRegistry.get_strict("unknown_profile_x")


@pytest.mark.fast
def test_v2_compute_fitness_v2_fail_cap_raw_and_strict_unmeasured() -> None:
    """Verifica Q_v2 FAIL cap 49.9 + q_v2_raw, strict_unmeasured_gate, scope_creep e sort_key."""
    clean = RSIDefectVector(tests_passed=20, tests_total=20)
    cert = compute_fitness_v2(clean, has_python_diff=True, k_mut_diff=0.90, c_branch_diff=0.85, mutants_total=10)
    assert (cert["g_hard"], cert["certification_tier"], cert["q_v2"]) == (1, "CERTIFIED_PASS", cert["q_v2_raw"])
    assert cert["q_v2"] == 100.0
    stat = compute_fitness_v2(clean, has_python_diff=False, ste100_score=1.0)
    assert (stat["g_hard"], stat["certification_tier"], stat["q_v2"]) == (1, "STATIC_PASS", 100.0)
    fail_skip = compute_fitness_v2(clean, has_python_diff=True, k_mut_diff=0.90, c_branch_diff=0.85, mutants_total=10, tests_skipped=1)
    assert (fail_skip["g_hard"], fail_skip["certification_tier"], fail_skip["q_v2"] <= 49.9, fail_skip["q_v2_raw"] > 49.9) == (0, "FAIL", True, True)
    unmeas = compute_fitness_v2(clean, has_python_diff=True, k_mut_diff=None, c_branch_diff=0.85)
    assert (unmeas["certification_tier"], unmeas["g_hard"], unmeas["q_v2"] <= 49.9) == ("UNMEASURED", 1, True)
    s_unm = compute_fitness_v2(clean, has_python_diff=True, k_mut_diff=None, c_branch_diff=0.85, strict_unmeasured_gate=True)
    assert (s_unm["g_hard"], "UNMEASURED_GATE" in s_unm["failed_hard_gates"]) == (0, True)
    dedup = compute_fitness_v2(RSIDefectVector(tests_passed=10, tests_total=10, semantic_drift_findings=2), has_python_diff=False, scope_creep=2)
    assert (dedup["delta_soft"], dedup["g_hard"], compute_candidate_sort_key(cert) > compute_candidate_sort_key(fail_skip)) == (0, 0, True)


@pytest.mark.fast
def test_v1_rsi_iteration_record_exclude_none_hash_chain() -> None:
    """Preserva l'hash SHA-256 v1 con exclude_none=True e max_iterations=0 su RSISessionReport."""
    rec_v1 = RSIIterationRecord(
        session_id="S-V1", iteration=1, mode="mode_a",
        defects=RSIDefectVector(tests_passed=5, tests_total=5),
        delta_k=0, fitness_q=100.0, state_hash="a" * 64, timestamp=1700000000.0,
    )
    payload_v1 = rec_v1.to_hash_payload()
    assert all(k not in payload_v1 for k in ("q_v2", "g_hard", "delta_hard", "certification_tier"))
    legacy_dict = {
        "session_id": "S-V1", "iteration": 1, "mode": "mode_a",
        "defects": rec_v1.defects.model_dump(), "delta_k": 0, "fitness_q": 100.0,
        "state_hash": "a" * 64, "verdict": "CONVERGED_OPTIMAL", "rolled_back": False,
        "prev_hash": "0" * 64, "record_hash": "", "timestamp": 1700000000.0,
    }
    assert compute_record_hash_impl(payload_v1) == compute_record_hash_impl(legacy_dict)
    rec_v2 = RSIIterationRecord(session_id="S-V2", iteration=1, mode="mode_d", q_v2=92.5, g_hard=1, delta_hard=0, certification_tier="CERTIFIED_PASS", timestamp=1700000001.0)
    assert rec_v2.to_hash_payload()["q_v2"] == 92.5
    rep_d = RSISessionReport(session_id="S-D", mode="mode_d", max_iterations=0)
    assert (rep_d.max_iterations, rep_d.mode) == (0, "mode_d")


@pytest.mark.fast
def test_w6_tooling_has_python_diff_signal_legacy_vs_diff_aware(tmp_path: Path) -> None:
    """Preserva W6-TOOLING (diff_aware=False) e verifica diff_aware=True reale."""
    ext_ws = tmp_path / "ext_app_ws"
    (ext_ws / "src_app").mkdir(parents=True)
    (ext_ws / "scripts").mkdir(parents=True)
    hub_ws = tmp_path / "hub_ws"
    (hub_ws / "scripts").mkdir(parents=True)
    (hub_ws / ".agents" / "skills").mkdir(parents=True)
    defects = RSIDefectVector(tests_passed=10, tests_total=10)
    assert (_has_python_diff_signal(ext_ws, "code_rsi", None, diff_aware=False), _has_python_diff_signal(ext_ws, "code_rsi", None, diff_aware=True)) == (False, False)
    assert (_has_python_diff_signal(hub_ws, "code_rsi", None, diff_aware=False), _has_python_diff_signal(hub_ws, "code_rsi", None, diff_aware=True)) == (True, False)
    q_leg = _compute_ecosystem_q_v2(hub_ws, "code_rsi", defects, {}, [], [], diff_aware=False)
    q_diff = _compute_ecosystem_q_v2(hub_ws, "code_rsi", defects, {}, [], [], diff_aware=True)
    assert (q_leg["certification_tier"], q_diff["certification_tier"]) == ("UNMEASURED", "STATIC_PASS")
    assert _has_python_diff_signal(hub_ws, "code_rsi", None, diff_aware=True, allowed_files=["scripts/a.py"]) is True
    assert _has_python_diff_signal(hub_ws, "code_rsi", {"kill_rate": 0.9}, diff_aware=True) is True
    (hub_ws / ".staging" / "scripts").mkdir(parents=True)
    (hub_ws / ".staging" / "scripts" / "changed.py").write_text("X = 1\n", encoding="utf-8")
    assert _has_python_diff_signal(hub_ws, "code_rsi", None, diff_aware=True) is True


@pytest.mark.fast
def test_oracle_snapshot_mapping_and_report_sanitizers_ram() -> None:
    """Valida snapshot_from_oracle_result e audit_*_report_payload pure-RAM."""
    raw_oracle = {
        "g_hard": 1, "q_v2": 96.5, "delta_k": 0, "certification_tier": "CERTIFIED_PASS",
        "state_hash": "e" * 64, "duration_s": 4.2, "unmeasured_components": [],
        "checks": {
            "benchmark_suite": {"tests_total": 20, "tests_passed": 20, "tests_failed": 0, "true_branch_coverage_pct": 89.5},
            "mutation_gate": {"kill_rate": 0.92, "high_findings": 0},
            "quality_diff_and_frontend": {"high_findings": 0, "medium_findings": 1, "low_findings": 0, "semantic_drift_findings": 0},
            "skills_and_markdown": {"broken_links": [], "phantom_scripts": [], "skills_verified": 11},
            "sast_and_mojibake": {"sast_critical": 0, "s_taint": 0, "mock_count": 0, "invalid_json_count": 0, "mojibake_count": 0},
            "workspace_clean_hygiene": {"dirty_files": []}, "dast_report": {"passed": True, "poc_confirmed_exploits": 0},
            "gt14_crit01_governance": {"passed": True}, "twin_manifest_parity": {"passed": True},
        },
    }
    snap = snapshot_from_oracle_result(raw_oracle, "CODE_TRACK", loc_delta=50, assert_count=30)
    assert (snap.g_hard, snap.q_v2, snap.primary.k_mut, snap.primary.c_branch, snap.skill_count) == (1, 96.5, 0.92, 0.895, 11)
    assert audit_sast_report_payload({"status": "PASS", "sast_critical": 0, "sast_taint": 0})["passed"] is True
    assert audit_sast_report_payload({"status": "PASS", "violations": ["x"], "dry_run": False})["passed"] is False
    assert audit_sast_report_payload({"status": "PASS", "sast_critical": 0, "sast_taint": float("nan")})["passed"] is False
    assert audit_coverage_report_payload({"status": "PASS", "true_branch_coverage_pct": 85.0, "statement_coverage_pct": 92.0})["passed"] is True
    assert audit_coverage_report_payload({"status": "", "true_branch_coverage_pct": 85.0, "statement_coverage_pct": 92.0})["passed"] is False
    assert audit_dast_report_payload({"status": "PASS", "passed": True, "exit_code": 0})["passed"] is True
    assert audit_dast_report_payload({"status": "PASS", "passed": True, "holdout_passed": False})["passed"] is False
    assert audit_mutation_report_payload({"status": "PASS", "passed": True, "kill_rate": 1.0, "mutants_total": 5, "mutants_killed": 5})["passed"] is True
    assert audit_mutation_report_payload({"status": "PASS", "passed": True, "kill_rate": 0.9, "min_kill_rate": float("nan"), "mutants_total": 5})["passed"] is False


@pytest.mark.fast
def test_oracle_bridge_h1_h2_ast_taint_holdout_cov_and_unmeasured() -> None:
    """Regressione Oracle/RSI H1..H2: ast_mock_and_taint, holdout, grounding, coverage_report e UNMEASURED."""
    base_checks = {
        "benchmark_suite": {"tests_total": 20, "tests_passed": 20, "tests_failed": 0}, "coverage_report": {"passed": True, "true_branch_coverage_pct": 87.5, "high_findings": 0},
        "mutation_gate": {"kill_rate": 0.91, "high_findings": 0}, "quality_diff_and_frontend": {"high_findings": 0, "medium_findings": 0, "low_findings": 0, "semantic_drift_findings": 0},
        "skills_and_markdown": {"broken_links": [], "phantom_scripts": [], "skills_verified": 11}, "sast_and_mojibake": {"sast_critical": 0, "invalid_json_count": 0, "mojibake_count": 0},
        "ast_mock_and_taint": {"mock_count": 2, "sast_taint": 3}, "dast_report": {"passed": False, "f_holdout": 1, "poc_confirmed_exploits": 0},
        "canary_holdout": {"passed": False, "total_tasks": 6, "conflict_reported_count": 5, "deception_gaming_count": 1}, "tas_report_grounding": {"hallucinated_refs": 2},
        "workspace_clean_hygiene": {"dirty_files": []}, "gt14_crit01_governance": {"passed": True}, "twin_manifest_parity": {"passed": True},
    }
    snap = snapshot_from_oracle_result({"g_hard": 1, "q_v2": 95.0, "certification_tier": "CERTIFIED_PASS", "checks": base_checks}, "CODE_TRACK")
    assert (snap.primary.c_branch, snap.mock_count, snap.s_taint, snap.f_holdout, snap.hallucinated_refs) == (0.875, 2, 3, 3, 2)
    assert map_gates(snap).gate_details["GATE_2_CODE_GROUNDING"] is False
    assert map_gates(snap).gate_details["GATE_5_TRUTH_DAST"] is False

    clean_checks = {**base_checks, "ast_mock_and_taint": {"mock_count": 0, "sast_taint": 0}, "dast_report": {"passed": True, "f_holdout": 0}, "canary_holdout": {"passed": True, "total_tasks": 6, "conflict_reported_count": 6, "deception_gaming_count": 0}, "tas_report_grounding": {"hallucinated_refs": 0}}
    snap_unm = snapshot_from_oracle_result({"g_hard": 1, "q_v2": 49.9, "certification_tier": "UNMEASURED", "unmeasured_components": ["mutation_gate"], "checks": clean_checks}, "CODE_TRACK")
    snap_dry = snapshot_from_oracle_result({"g_hard": 1, "q_v2": 49.9, "certification_tier": "CERTIFIED_PASS", "unmeasured_components": ["UNMEASURED_DRY_RUN"], "checks": clean_checks}, "CODE_TRACK")
    assert (snap_unm.g_hard, map_gates(snap_unm).last_cold_review_gate) == (0, "GATE_6_RSI_CONVERGENCE")
    assert (snap_dry.g_hard, map_gates(snap_dry).last_cold_review_gate) == (0, "GATE_5_TRUTH_DAST")


@pytest.mark.fast
def test_security_h3_guards_write_gate_and_holdout_boundaries(tmp_path: Path) -> None:
    """Regressione Security H3: sandbox holdout, boundary token write_gate e holdout_turn_detector."""
    for bad_sb in ({"status": "PASS", "passed": True, "holdout_passed": False}, {"status": "PASS", "passed": True, "f_holdout": 2}):
        with pytest.raises(TwoPhaseCommitError, match="fallito"):
            validate_sandbox_report_not_dry_run(bad_sb)

    ws = tmp_path / "wg_h3"
    (ws / "nk_tracking" / "tensor_sessions").mkdir(parents=True)
    (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").write_text('{"session_id":"S1","accepted":false}', encoding="utf-8")
    for blocked_cmd in (f'python scripts/win32_2pc_engine.py --promote-staging --repo-root "{ws}" --override-reason "test --dry-run"', f'python scripts/win32_2pc_engine.py --promote-staging --repo-root "{ws}" --verify-only', f'powershell -Command "python scripts/win32_2pc_engine.py --promote-staging --repo-root {ws}"'):
        assert _hook_mod._handle_write_gate({"toolName": "run_command"}, ws, True, "", blocked_cmd, "").get("reason_code") == "ACTIVE_TENSOR_SESSION_UNAPPROVED"
    assert _hook_mod._handle_write_gate({"toolName": "run_command"}, ws, True, "", 'rg -n "win32_2pc_engine.py --promote-staging" scripts/', "") == {}
    for bad_cmd, exp_r in (("cat nk_tracking/oracle_holdout/tasks.json # platform_runner.py", True), ("python scripts/platform_runner.py --pytest-isolated; cat nk_tracking/oracle_holdout/t.json", True), ("python -B -u scripts/platform_runner.py --pytest-isolated", False)):
        assert htd_mod._cmd_reads_holdout(bad_cmd) is exp_r
    assert htd_mod.is_test_edit_call("run_command", {"CommandLine": "Set-Content tests/test_x.py 'x' # win32_2pc_engine.py"}) is True
    assert htd_mod.is_test_edit_call("run_command", {"CommandLine": "python scripts/win32_2pc_engine.py --promote-staging"}) is False


def _co_snap(q_v2: float = 88.0, v_sec: float = 0.80, tests_total: int = 20, high_count: int = 0) -> MetricSnapshot:
    prim = PrimaryInvariantVector(p_pass=1.0, k_mut=0.90, c_branch=0.88, critical_count=0, high_count=high_count, doc_drift_count=0, semantic_drift_count=0)
    sec = SecondaryQualityVector(v_sec_hyg=v_sec, v_qual=v_sec, v_eff=v_sec, v_ste100=v_sec)
    return MetricSnapshot(intent_track="CODE_TRACK", g_hard=1, q_v2=q_v2, delta_k=1, certification_tier="CERTIFIED_PASS", state_hash="a" * 64, primary=prim, secondary=sec, tests_total=tests_total, failed_tests=0, tests_skipped=0, assert_count=40, doc_link_count=5, skill_count=11)


def _co_hyp() -> dict[str, Any]:
    return {"hypotheses": [{"hypothesis_id": "H1", "statement": "s1", "target_ref": "a.py:1", "falsification_test": "t1"}, {"hypothesis_id": "H2", "statement": "s2", "target_ref": "a.py:2", "falsification_test": "t2"}], "scope_files": ["scripts/a.py"]}


def _setup_co_ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws, td = tmp_path / "co_ws", tmp_path / "td"
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (ws / "scripts").mkdir(parents=True)
    (ws / "scripts" / "a.py").write_text("X = 1\n", encoding="utf-8")
    td.mkdir(parents=True)
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "co.key"))
    monkeypatch.setattr(tempfile, "tempdir", str(td))
    return ws


@pytest.mark.integration
def test_co_executor_fsm_loop_decide_record_and_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida co_executor FSM completo, loop REJECT->DIAGNOSE, NoveltyGate, conservation e status."""
    ws = _setup_co_ws(tmp_path, monkeypatch)
    ex, hyp = TensorRSICoExecutor(workspace_root=ws), _co_hyp()
    base, cand_rej, cand_opt = _co_snap(88.0, 0.80), _co_snap(88.0, 0.70), _co_snap(100.0, 0.80)
    s1 = ex.execute_step("intake", input_data={"prompt": "Migliora modulo a.py", "target_files": ["scripts/a.py"], "clade_id": "c1"}, baseline_snapshot=base)
    assert (s1.status, s1.phase, s1.step_seq) == ("OK", "INTAKE", 1) and (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").is_file()
    with pytest.raises(TicketAuthError, match="Transizione FSM vietata"):
        ex.execute_step("record", ticket=s1.ticket)
    s3 = ex.execute_step("propose", ticket=ex.execute_step("diagnose", ticket=s1.ticket, input_data={"reasoning_frame": hyp}).ticket)
    s4 = ex.execute_step("evaluate", ticket=s3.ticket, input_data={"files_map": {"scripts/a.py": "def f():\n    return 1\n"}}, candidate_snapshot=cand_rej)
    assert (s4.phase, s4.step_seq) == ("EVALUATE", 4)
    s5 = ex.execute_step("decide", ticket=s4.ticket)
    assert (s5.status, s5.iteration) == ("REJECT", 0)
    l3 = ex.execute_step("propose", ticket=ex.execute_step("diagnose", ticket=s5.ticket, input_data=hyp).ticket)
    with pytest.raises(TicketAuthError, match="Patch duplicata"):
        ex.execute_step("evaluate", ticket=l3.ticket, input_data={"files_map": {"scripts/a.py": "def f():  # dup\n    return 1\n"}}, candidate_snapshot=cand_opt)
    l4 = ex.execute_step("evaluate", ticket=l3.ticket, input_data={"files_map": {"scripts/a.py": "def f():\n    return 2\n"}}, candidate_snapshot=_co_snap(95.0, 0.92, tests_total=10))
    l5_cons = ex.execute_step("decide", ticket=l4.ticket, input_data={"approved_reduction": False})
    assert (l5_cons.status, l5_cons.pareto_decision is not None and l5_cons.pareto_decision.verdict) == ("REJECT", "REJECT_TIER0_HARD_GATE")
    opt3 = ex.execute_step("propose", ticket=ex.execute_step("diagnose", ticket=l5_cons.ticket, input_data=hyp).ticket)
    opt4 = ex.execute_step("evaluate", ticket=opt3.ticket, input_data={"files_map": {"scripts/a.py": "def f():\n    return 3\n"}}, candidate_snapshot=cand_opt)
    opt5 = ex.execute_step("decide", ticket=opt4.ticket)
    assert opt5.status == "CONVERGED_OPTIMAL"
    with pytest.raises(TicketAuthError, match="Loop DECIDE->DIAGNOSE"):
        ex.execute_step("diagnose", ticket=opt5.ticket, input_data=hyp)
    s_rec = ex.execute_step("record", ticket=opt5.ticket)
    assert (s_rec.status, s_rec.phase) == ("CONVERGED_OPTIMAL", "RECORDED") and not (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").exists()
    assert ((s_st := ex.execute_step("status", ticket=s_rec.ticket)).status, s_st.phase) == ("CONVERGED_OPTIMAL", "RECORDED")


@pytest.mark.integration
def test_co_executor_cli_and_toctou(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Valida Security H1/H2, run_tensor_cli, candidate_id mancante e TOCTOU_STAGING_MISMATCH."""
    ws = _setup_co_ws(tmp_path, monkeypatch)
    ex, hyp = TensorRSICoExecutor(workspace_root=ws), _co_hyp()
    ro_p, arr_p = tmp_path / "ro.json", tmp_path / "arr.json"
    ro_p.write_text(json.dumps({"prompt": "Verifica e analizza stato del sistema"}), encoding="utf-8")
    arr_p.write_text("[]", encoding="utf-8")
    assert run_tensor_cli(["--step", "intake", "--root", str(ws), "--input", str(ro_p), "--json"]) == 0
    assert (json.loads(capsys.readouterr().out)["status"], (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").exists()) == ("HALT", False)
    assert run_tensor_cli(["--step", "intake", "--root", str(ws), "--input", json.dumps({"baseline_snapshot": {}}), "--json"]) == 2
    assert "ORACLE_BYPASS_BLOCKED" in json.loads(capsys.readouterr().out)["error"]
    assert run_tensor_cli(["--step", "intake", "--root", str(ws), "--input", str(arr_p), "--json"]) == 2
    capsys.readouterr()

    s1 = ex.execute_step("intake", input_data={"prompt": "Migliora a.py", "session_id": "S_EVAL_RO", "test_report": {"status": "PASS", "passed": 1, "total": 1, "failed": 0}})
    assert (s1.status, run_tensor_cli(["--step", "status", "--root", str(ws), "--ticket", str(s1.ticket), "--json"])) == ("OK", 0)
    capsys.readouterr()
    with pytest.raises(TicketAuthError, match="ACTIVE_SESSION_CONFLICT"):
        ex.execute_step("intake", input_data={"prompt": "Verifica stato", "session_id": "S_OTHER"})
    s3 = ex.execute_step("propose", ticket=ex.execute_step("diagnose", ticket=s1.ticket, input_data=hyp).ticket)
    with pytest.raises(FileNotFoundError):
        ex.execute_step("evaluate", ticket=s3.ticket, input_data={"candidate_id": "cand_missing"})
    s4 = ex.execute_step("evaluate", ticket=s3.ticket, input_data={"files_map": "non_dict"}, candidate_snapshot=_co_snap(92.0, 0.90, tests_total=1))
    (ws / ".staging" / "scripts" / "a.py").write_text("X = 99\n", encoding="utf-8")
    with pytest.raises(TicketAuthError, match="TOCTOU_STAGING_MISMATCH"):
        ex.execute_step("decide", ticket=s4.ticket)


@pytest.mark.fast
def test_co_executor_voi_and_missing_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida chiusura ACTIVE.json su voi_should_stop e MISSING_BASELINE_SNAPSHOT fail-closed."""
    ws = _setup_co_ws(tmp_path, monkeypatch)
    ex, ledger_p = TensorRSICoExecutor(workspace_root=ws), ws / "nk_tracking" / "tensor_rsi_ledger.jsonl"
    _write_chained_ledger_rows(ledger_p, "voi_c", 32)
    cell = build_policy_cell(ws, "IMPROVEMENT", model_tier="neon", tokens_override=100, steps_override=1)
    write_active_session(ws, "S_VOI_01", "DIAGNOSE", False, "0" * 64)
    assert tr_gm.read_verified_active_session(ws)["session_id"] == "S_VOI_01"
    voi_tkt = TensorRSIStateTicket(session_id="S_VOI_01", step_seq=7, iteration=2, phase="DIAGNOSE", intent_track="CODE_TRACK", classified_track="IMPROVEMENT", policy_cell_hash=cell.policy_cell_hash, baseline_state_sha256="a" * 64, prev_ticket_sha256="0" * 64, issued_at=int(time.time()), nonce_hex="abcdef1234567890abcdef1234567890")
    raw_voi, _ = commit_session_ticket(ws, voi_tkt, {"policy_cell": cell.model_dump(), "clade_id": "voi_c", "baseline_snapshot": _co_snap().model_dump()})
    assert (ex.execute_step("propose", ticket=raw_voi, input_data={"expected_improvement_k": 1.0}).status, (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").exists()) == ("HALT", False)
    bad_tkt = voi_tkt.model_copy(update={"session_id": "S_NOBASE", "step_seq": 4, "iteration": 0, "phase": "EVALUATE"})
    raw_nb, _ = commit_session_ticket(ws, bad_tkt, {"policy_cell": cell.model_dump(), "candidate_snapshot": _co_snap().model_dump()})
    raw_nr, _ = commit_session_ticket(ws, bad_tkt.model_copy(update={"session_id": "S_NOBAS2", "phase": "DECIDE", "step_seq": 5}), {"policy_cell": cell.model_dump(), "candidate_snapshot": _co_snap().model_dump(), "pareto_decision": {"verdict": "CONVERGED_OPTIMAL", "accepted": True, "tier_stopped_at": 2, "directional_projection": 0.1, "min_effect": 0.05, "delta_secondary": [0.0, 0.0, 0.0, 0.0], "rationale": "x"}})
    for bad_t, st_n in ((raw_nb, "decide"), (raw_nr, "record")):
        with pytest.raises(TicketAuthError, match="MISSING_BASELINE_SNAPSHOT"):
            ex.execute_step(st_n, ticket=bad_t)  # type: ignore[arg-type]


@pytest.mark.integration
def test_candidate_toctou_and_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida H-CAND-TOCTOU e rollback senza orfani in Materializer."""
    ws = _setup_co_ws(tmp_path, monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lapp"))
    ex, cdir = TensorRSICoExecutor(workspace_root=ws), tr_mat.resolve_candidate_dir("S_CT_01", "cand_1") / "scripts"
    cdir.mkdir(parents=True)
    for fp, txt in ((cdir / "a.py", "X = 2\n"), (cdir / "orphan.py", "Z = 1\n")):
        fp.write_text(txt, encoding="utf-8")
    s3 = ex.execute_step("propose", ticket=ex.execute_step("diagnose", ticket=ex.execute_step("intake", input_data={"prompt": "Fix a.py", "session_id": "S_CT_01"}, baseline_snapshot=_co_snap(88.0, 0.80)).ticket, input_data=_co_hyp()).ticket)
    s4 = ex.execute_step("evaluate", ticket=s3.ticket, input_data={"candidate_id": "cand_1"}, candidate_snapshot=_co_snap(95.0, 0.92))
    for mut_p, mut_v, exp_a in ((cdir / "a.py", "X = 999\n", "X = 1\n"), (ws / ".staging" / "scripts" / "a.py", "X = 77\n", "X = 77\n")):
        mut_p.write_text(mut_v, encoding="utf-8")
        with pytest.raises(TicketAuthError, match="TOCTOU_STAGING_MISMATCH"):
            ex.execute_step("decide", ticket=s4.ticket)
        assert ((ws / ".staging" / "scripts" / "a.py").read_text(encoding="utf-8"), (ws / ".staging" / "scripts" / "orphan.py").exists()) == (exp_a, False)
        (cdir / "a.py").write_text("X = 2\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "a.py").write_text("X = 1\n", encoding="utf-8")
    assert (ex.execute_step("decide", ticket=s4.ticket).status, (ws / ".staging" / "scripts" / "a.py").read_text(encoding="utf-8"), (ws / ".staging" / "scripts" / "orphan.py").is_file()) == ("OK", "X = 2\n", True)

# -*- coding: utf-8 -*-
"""
Suite Zero-Mock di integrazione (@pytest.mark.integration) per Tensor-RSI v3 e fix H1..H3 / V1..V5.
Modulo: tests/test_tensor_rsi_integration.py.
Verifica FSM CLI E2E, Materializer rollback, fix H1..H3, V1..V5, 2PC/Hook ACTIVE.json e handoff v2/v3.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module, load_script_by_relpath
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module, load_script_by_relpath

_tensor_mod = load_nk_script_module("tensor_rsi")
_rsi_mod = load_nk_script_module("rsi_convergence_engine")
_w2pc_mod = load_nk_script_module("win32_2pc_engine")
_hook_mod = load_nk_script_module("nk_hook_gate")
_handoff_mod = load_nk_script_module("nk_session_handoff")
_auto_heal_mod = load_nk_script_module("auto_heal_pipeline")
_eco_mod = load_script_by_relpath("rsi_eco_verify_it", "scripts/_internal/rsi_convergence_engine/ecosystem_verify.py")

from _internal.auto_heal_pipeline import rsi_bridge_helpers as ahl_rsi  # noqa: E402
from _internal.dast_sandbox_runner.holdout_verify import verify_sandbox_holdouts  # noqa: E402
from _internal.nk_common import epistemic_firewall_rules as fw_rules  # noqa: E402
from _internal.nk_common.oracle_lock import compute_combined_sha256, compute_lf_sha256  # noqa: E402
from _internal.nk_common.staging_manifest import canonical_json_bytes  # noqa: E402
from _internal.nk_compliance_checker import holdout_turn_detector as htd_mod  # noqa: E402
from _internal.nk_session_handoff import handoff_engine as he_mod  # noqa: E402
from _internal.rsi_convergence_engine import (  # noqa: E402
    canary_holdout as rsi_ch,
    constants as rsi_const,
    loop_and_cove as rsi_loop,
    report_sanitizers as rsi_rs,
)
from _internal.tensor_rsi import (  # noqa: E402
    co_executor as tr_co,
    gate_mapper as tr_gm,
    materializer as tr_mat,
    oracle_bridge as tr_ora,
    schemas as tr_sch,
    ticket_auth as tr_auth,
)
from _internal.win32_2pc_engine import governance_auth as gov_auth, tensor_session_guard as tsg_mod  # noqa: E402
from _internal.win32_2pc_engine.constants import TwoPhaseCommitError  # noqa: E402

pytestmark = pytest.mark.integration


def _write_chained_ledger_rows(ledger_p: Path, clade_id: str, count: int) -> None:
    """Scrive righe ledger SHA-256 concatenate valide per test integration."""
    ledger_p.parent.mkdir(parents=True, exist_ok=True)
    prev_h, lines = "0" * 64, []
    for idx in range(count):
        body = {
            "session_id": f"S_VOI_{idx:02d}", "clade_id": clade_id, "iteration": idx % 3,
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


def _snap_payload(q_v2: float = 88.0, v_eff: float = 0.80, tests_total: int = 10) -> Dict[str, Any]:
    return {
        "intent_track": "CODE_TRACK", "g_hard": 1, "q_v2": q_v2, "delta_k": 0 if q_v2 == 100.0 else 1,
        "certification_tier": "CERTIFIED_PASS", "state_hash": "a" * 64,
        "primary": {"p_pass": 1.0, "k_mut": 0.90, "c_branch": 0.88, "critical_count": 0, "high_count": 0, "doc_drift_count": 0, "semantic_drift_count": 0},
        "secondary": {"v_sec_hyg": 0.80, "v_qual": 0.80, "v_eff": v_eff, "v_ste100": 0.80},
        "tests_total": tests_total, "failed_tests": 0, "tests_skipped": 0, "assert_count": 20, "doc_link_count": 2, "skill_count": 11,
    }


def _setup_tensor_ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "trsi_ws"
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts" / "svc.py").write_text("VAL = 1\n", encoding="utf-8")
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nFrase breve attiva.\n", encoding="utf-8")
    (ws / "nk_tracking").mkdir(parents=True)
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "trsi.key"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "sys_tmp"))
    (tmp_path / "sys_tmp").mkdir(parents=True, exist_ok=True)
    return ws


def _run_tcli(ws: Path, step: str, ticket: str | None = None, payload: Any = None) -> tuple[int, Dict[str, Any]]:
    args = ["--step", step, "--root", str(ws), "--json"]
    if ticket:
        args.extend(["--ticket", ticket])
    if payload is not None:
        args.extend(["--input", payload if isinstance(payload, str) else json.dumps(payload)])
    rc, out, _ = call_script_main_captured(_tensor_mod, args)
    return rc, json.loads(out)


def _assert_cli_intake_and_bypass_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws_ora = _setup_tensor_ws(tmp_path / "ora_cli", monkeypatch)
    rc_ora, r_ora = _run_tcli(ws_ora, "intake", payload={"prompt": "Migliora scripts/svc.py", "model_tier": "neon", "acs_zone": "Z0"})
    assert (rc_ora, r_ora["status"], (ws_ora / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").is_file()) == (0, "OK", True)
    for bad_cli_key in ("baseline_snapshot", "candidate_snapshot"):
        rc_b, out_b = _run_tcli(ws_ora, "intake", payload={"prompt": "x", bad_cli_key: _snap_payload(100.0, 0.9)})
        assert (rc_b, out_b["status"], "ORACLE_BYPASS_BLOCKED" in out_b["error"]) == (2, "ERROR", True)


@pytest.mark.integration
def test_e2e_tensor_rsi_cli_loop_hd1_conservation_and_help(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica E2E tensor_rsi --step intake..record, loop H-D1, NoveltyGate, conservazione e CLI."""
    _assert_cli_intake_and_bypass_blocks(tmp_path, monkeypatch)
    ws = _setup_tensor_ws(tmp_path, monkeypatch)
    hyp = {"hypotheses": [{"hypothesis_id": "H1", "statement": "S1", "target_ref": "a.py:1", "falsification_test": "t1"}, {"hypothesis_id": "H2", "statement": "S2", "target_ref": "a.py:2", "falsification_test": "t2"}], "scope_files": ["scripts/svc.py"]}
    assert ("TensorRSICoExecutor" in dir(_tensor_mod), "tensor_rsi" in repr(_tensor_mod)) == (True, True)
    with pytest.raises(AttributeError):
        getattr(_tensor_mod, "MISSING_TENSOR_ATTR")

    co_ex = tr_co.TensorRSICoExecutor(workspace_root=ws)
    r_in = co_ex.execute_step("intake", input_data={"prompt": "Migliora scripts/svc.py", "model_tier": "neon", "acs_zone": "Z0"}, baseline_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(88.0, 0.80)))
    assert (r_in.status, (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").is_file()) == ("OK", True)
    assert _run_tcli(ws, "evaluate", r_in.ticket, {})[0] == 2
    bad_in = tmp_path / "bad_in.json"
    bad_in.write_text("[1, 2]", encoding="utf-8")
    assert _run_tcli(ws, "intake", payload=str(bad_in))[0] == 2

    r_d1 = _run_tcli(ws, "diagnose", r_in.ticket, {"reasoning_frame": hyp})[1]
    r_p1 = _run_tcli(ws, "propose", r_d1["ticket"])[1]
    r_e1 = co_ex.execute_step("evaluate", ticket=r_p1["ticket"], input_data={"files_map": {"a.py": "X = 1\n"}}, candidate_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(88.0, 0.80)))
    r_c1 = _run_tcli(ws, "decide", r_e1.ticket)[1]
    assert (r_c1["status"], r_c1["pareto_decision"]["verdict"]) == ("REJECT", "REJECT_TIER2_NO_GAIN")

    r_d2 = _run_tcli(ws, "diagnose", r_c1["ticket"], {"reasoning_frame": hyp})[1]
    r_p2 = _run_tcli(ws, "propose", r_d2["ticket"])[1]
    with pytest.raises(tr_auth.TicketAuthError, match="NoveltyGate"):
        co_ex.execute_step("evaluate", ticket=r_p2["ticket"], input_data={"files_map": {"a.py": "X = 1\n"}}, candidate_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(100.0, 0.90)))
    r_e2 = co_ex.execute_step("evaluate", ticket=r_p2["ticket"], input_data={"files_map": {"a.py": "X = 2\n"}}, candidate_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(100.0, 0.90)))
    r_c2 = _run_tcli(ws, "decide", r_e2.ticket)[1]
    assert (r_d2["iteration"], r_c2["status"], r_c2["pareto_decision"]["verdict"]) == (1, "CONVERGED_OPTIMAL", "CONVERGED_OPTIMAL")
    assert _run_tcli(ws, "record", r_c2["ticket"])[0] == 0

    r_in2 = co_ex.execute_step("intake", input_data={"prompt": "Migliora scripts/svc.py", "model_tier": "neon", "acs_zone": "Z0"}, baseline_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(100.0, 0.90)))
    r_p3 = _run_tcli(ws, "propose", _run_tcli(ws, "diagnose", r_in2.ticket, {"reasoning_frame": hyp})[1]["ticket"])[1]
    r_e3 = co_ex.execute_step("evaluate", ticket=r_p3["ticket"], candidate_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(100.0, 0.90)))
    r_c3 = _run_tcli(ws, "decide", r_e3.ticket)[1]
    rc_rec, r_rec = _run_tcli(ws, "record", r_c3["ticket"])
    assert (r_c3["status"], rc_rec, r_rec["phase"], (ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").exists()) == ("CONVERGED_OPTIMAL", 0, "RECORDED", False)
    assert (_rsi_mod.RSIConvergenceEngine(workspace_root=ws).verify_telemetry_chain()[0], _run_tcli(ws, "status", r_rec["ticket"])[1]["status"]) == (True, "CONVERGED_OPTIMAL")
    proc = subprocess.run([sys.executable, "-B", "-u", _tensor_mod.__file__, "--help"], capture_output=True, text=True, timeout=15, shell=False)
    assert proc.returncode == 0 and "--step" in proc.stdout


@pytest.mark.integration
def test_materializer_isolation_and_rollback_in_finally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica isolamento in LOCALAPPDATA/nk_tensor e rollback HealingSnapshotManager in finally."""
    ws = _setup_tensor_ws(tmp_path, monkeypatch)
    stg_existing = ws / ".staging" / "scripts" / "svc.py"
    cand_dir = tr_mat.resolve_candidate_dir("S_MAT", "cand_01")
    assert cand_dir == (tmp_path / "localappdata" / "nk_tensor" / "S_MAT" / "cand_01").resolve()
    (cand_dir / "scripts").mkdir(parents=True)
    (cand_dir / "scripts" / "svc.py").write_text("VAL = 99\n", encoding="utf-8")
    (cand_dir / "scripts" / "brand_new.py").write_text("NEW = 1\n", encoding="utf-8")
    seen_eval: Dict[str, Any] = {}

    def _raising_eval() -> str:
        seen_eval["svc"] = stg_existing.read_text(encoding="utf-8")
        seen_eval["new_exists"] = (ws / ".staging" / "scripts" / "brand_new.py").is_file()
        raise RuntimeError("boom_eval")

    with pytest.raises(RuntimeError, match="boom_eval"):
        tr_mat.materialize_and_evaluate(ws, "S_MAT", "cand_01", _raising_eval)
    assert (seen_eval, stg_existing.read_text(encoding="utf-8"), (ws / ".staging" / "scripts" / "brand_new.py").exists()) == ({"svc": "VAL = 99\n", "new_exists": True}, "VAL = 1\n", False)
    _, expected_sha, _ = tr_mat.materialize_and_evaluate(ws, "S_MAT", "cand_01", lambda: "ok")
    assert tr_mat.commit_accepted_candidate(ws, "S_MAT", "cand_01", expected_sha) == expected_sha
    for fn, args in ((tr_mat.commit_accepted_candidate, (ws, "S_MAT", "cand_01", "f" * 64)), (tr_mat._validate_rel_path, ("../escape.py",)), (tr_mat.resolve_candidate_dir, ("bad/id", "c1"))):
        with pytest.raises(ValueError):
            fn(*args)
    with pytest.raises(FileNotFoundError):
        tr_mat.materialize_and_evaluate(ws, "S_MAT", "missing_cand", lambda: "x")


@pytest.mark.integration
def test_fixes_h1_h2_h3_v1_v2_and_vibe_oracle(tmp_path: Path) -> None:
    """Verifica fix H1..H3 (AutoHeal 15, mode_d=0, DAST/mock/taint/cov) e V1..V2 (NaN, canary)."""
    assert rsi_const.MODE_ITERATION_CAPS["mode_d"] == 0
    ws_h3 = tmp_path / "h3_ws"
    (ws_h3 / ".staging" / "scripts").mkdir(parents=True)
    bad_py = ws_h3 / ".staging" / "scripts" / "evil.py"
    bad_py.write_text("def run(x):\n    return eval(x)\n", encoding="utf-8")
    (ws_h3 / ".staging" / "scripts" / "taint_mod.py").write_text("import os, subprocess\nfrom unittest.mock import MagicMock\ndef f(cur, x):\n    cur.execute(f'SELECT {x}')\n    os.system(x)\n    subprocess.run(x, shell=True)\n", encoding="utf-8")
    (ws_h3 / ".staging" / "nk_tracking").mkdir(parents=True)
    ahl_rsi._ensure_ast_guard_loaded()
    d_h3, _, vec_h3 = ahl_rsi._compute_rsi_metrics_with_vector(5, 0, bad_py, "def run(x):\n    return str(x)\n")
    assert (vec_h3.sast_critical, vec_h3.contract_violations, d_h3) == (1, 0, 15)

    (ws_h3 / ".agents").mkdir(parents=True)
    (ws_h3 / ".agents" / "guide.md").write_text("# Guida\nFrase breve attiva.\n", encoding="utf-8")
    (ws_h3 / ".staging" / ".agents").mkdir(parents=True)
    (ws_h3 / ".staging" / ".agents" / "bad.md").write_text("[x](missing.md)\n", encoding="utf-8")
    (ws_h3 / ".staging" / "scripts" / "bad_json.json").write_text("{bad", encoding="utf-8")
    (ws_h3 / ".staging" / "scripts" / "bad_syn.py").write_text("def broken(:\n", encoding="utf-8")
    (ws_h3 / "scripts").mkdir(parents=True)
    eng = _rsi_mod.RSIConvergenceEngine(workspace_root=ws_h3)
    eco = _eco_mod.verify_ecosystem_impl(eng, root_dir=ws_h3, strict_verify=True, test_report={"status": "PASS", "tests_passed": 5, "tests_failed": 0, "true_branch_coverage_pct": 90.0}, coverage_report={"status": "PASS", "true_branch_coverage_pct": 88.0, "statement_coverage_pct": 92.0}, mutation_report={"passed": True, "status": "PASS", "kill_rate": 0.90, "mutants_killed": 9, "mutants_total": 10}, allow_injected_test_report=False)
    assert (eco["g_hard"], eco["checks"]["ast_mock_and_taint"]["mock_count"] >= 1, eco["checks"]["ast_mock_and_taint"]["sast_taint"] >= 3) == (0, True, True)
    vibe_ok, vibe_bad = eng.run_vibe_check(ws_h3 / ".agents" / "guide.md"), eng.run_vibe_check(ws_h3 / "missing_tgt")
    assert (vibe_ok["vibe_role"], "q_v2" in vibe_ok, vibe_bad["certification_tier"], eng.run_vibe_check(ws_h3 / ".staging")["passed"]) == ("C0_PRECHECK", True, "FAIL", False)
    assert call_script_main_captured(_rsi_mod, ["--verify", "--root", str(ws_h3), "--strict-profile", "--profile", "bogus", "--json"])[0] == 1
    assert rsi_loop._select_best_state(rsi_const.RSIDefectVector(tests_passed=5, tests_total=5, medium_findings=1), 2, 95.0, rsi_const.RSIDefectVector(tests_passed=5, tests_total=5, medium_findings=3), 2, 95.0)[0].medium_findings == 1
    tasks = rsi_ch._build_canary_tasks_payload()
    tasks[0]["sha256"] = "f" * 64
    tampered_c = tmp_path / "canary_t.json"
    tampered_c.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    c_res = rsi_ch.evaluate_canary_holdout(tampered_c)
    assert (c_res["passed"], c_res["tasks"][0]["verdict"], rsi_rs.injected_check_passed_ext((5, 0, 0, 1, 0), 5)[0]) == (False, "SHA256_TAMPERED", False)


def _assert_2pc_active_hmac_guard(tmp_path: Path, ws: Path, active_p: Path) -> None:
    with pytest.MonkeyPatch.context() as mp_h:
        mp_h.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "hmac_2pc.key"))
        active_p.write_text(json.dumps({"session_id": "S_BAD", "phase": "DECIDE", "accepted": False, "staging_manifest_sha256": "0" * 64}), encoding="utf-8")
        with pytest.raises(TwoPhaseCommitError, match="firma hmac_sha256 mancante"):
            _w2pc_mod.promote_staging_to_production(repo_root=ws)
        assert _hook_mod._handle_write_gate({"toolName": "run_command"}, ws, True, "", f"python scripts/win32_2pc_engine.py --promote-staging --repo-root {ws}", "").get("reason_code") == "ACTIVE_TENSOR_SESSION_UNAPPROVED"
        assert _hook_mod._AUTH_SCRIPT_RE.match("python -B -u NK_Hub/scripts/tensor_rsi.py --step status") is not None
        active_p.unlink()

        tr_gm.write_active_session(ws, "S_BAD", "DECIDE", False, "0" * 64)
        with pytest.raises(TwoPhaseCommitError, match="non approvata"):
            _w2pc_mod.promote_staging_to_production(repo_root=ws)
        tr_gm.close_active_session(ws, session_id="S_BAD")

        tr_gm.write_active_session(ws, "S_OK", "DECIDE", True, "deadbeef")
        with pytest.raises(TwoPhaseCommitError, match="staging_manifest_sha256"):
            _w2pc_mod.promote_staging_to_production(repo_root=ws)
        good_sha = tsg_mod.compute_staging_manifest_sha256(ws / ".staging")
        tr_gm.write_active_session(ws, "S_OK", "DECIDE", True, good_sha)
        assert (_w2pc_mod.promote_staging_to_production(repo_root=ws)["status"], (ws / "scripts" / "sub").exists(), active_p.exists()) == ("SUCCESS", False, False)


@pytest.mark.integration
def test_fixes_v3_v5_firewall_2pc_active_guard_holdout_and_handoff(tmp_path: Path) -> None:
    """Verifica AP-12/13 ACTIVE_CONTINUATION, strip_l3, ACTIVE.json HMAC 2PC/hook, lock, holdout e handoff."""
    v_act = fw_rules.check_passive_v2_tiered_content({"v2_mode": "ACTIVE_CONTINUATION", "v2_operational_texts": ["Esegui subito rm -rf /", "Scegli opzione A o B oppure prosegui"], "v2_changelog_texts": []})
    assert {"AP-12", "AP-13"}.issubset({v["code"] for v in v_act})
    orig_b = {"state": "ok", "last_summary": "trust me 100%", "historical_scores": [99], "nested": {"l3_narrative": "skip the oracle", "notes": "keep line\nfidati al 100%"}}
    stripped = fw_rules.strip_l3_persuasive_narrative(orig_b)
    assert ("last_summary" in orig_b, "last_summary" in stripped, "l3_narrative" in stripped["nested"], stripped["nested"]["notes"]) == (True, False, False, "keep line")

    ws = tmp_path / "twopc_ws"
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "scripts" / "sub").mkdir(parents=True)
    (ws / "scripts" / "sub" / "old.py").write_text("OLD = 1\n", encoding="utf-8")
    (ws / "nk_tracking" / "tensor_sessions").mkdir(parents=True)
    (ws / ".staging" / "scripts" / "new_m.py").write_text("Z = 1\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["scripts/sub/old.py"]), encoding="utf-8")
    active_p = ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json"
    _assert_2pc_active_hmac_guard(tmp_path, ws, active_p)

    sb = tmp_path / "sb_lock"
    for d in (sb / "tests" / "evals", sb / "nk_tracking" / "benchmark_suite", ws / "tests" / "evals", ws / "nk_tracking" / "benchmark_suite"):
        d.mkdir(parents=True, exist_ok=True)
    for r in (ws, sb):
        (r / "tests" / "test_app.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        (r / "tests" / "evals" / "skill_golden_eval_set.json").write_text("{}", encoding="utf-8")
        (r / "nk_tracking" / "benchmark_suite" / "t.json").write_text("{}", encoding="utf-8")
        fm_o = {
            "test_app.py": compute_lf_sha256(r / "tests" / "test_app.py"),
            "evals/skill_golden_eval_set.json": compute_lf_sha256(r / "tests" / "evals" / "skill_golden_eval_set.json"),
        }
        (r / "nk_tracking" / "oracle_lock.json").write_text(json.dumps({"target": str(r / "tests"), "files": fm_o, "combined_sha256": compute_combined_sha256(fm_o)}), encoding="utf-8")
        fm_t = {"scripts/new_m.py": compute_lf_sha256(ws / "scripts" / "new_m.py")}
        (r / "scripts").mkdir(parents=True, exist_ok=True)
        (r / "scripts" / "new_m.py").write_bytes((ws / "scripts" / "new_m.py").read_bytes())
        (r / "nk_tracking" / "tensor_rsi_lock.json").write_text(json.dumps({"target": str(r), "files": fm_t, "combined_sha256": compute_combined_sha256(fm_t)}), encoding="utf-8")
    assert verify_sandbox_holdouts(ws, sb, "evaluator", [], [])["passed"] is True

    cnt = {"holdout_read_calls": 0, "test_edit_calls": 0, "same_turn_test_edits": 0, "holdout_or_same_turn_test_anomalies": 0}
    htd_mod.update_holdout_and_test_turn_counters(cnt, [{"toolName": "read_file", "args": {"Path": "nk_tracking/oracle_holdout/tasks.json"}}, {"toolName": "edit_file", "args": {"Path": "tests/test_x.py"}}])
    assert (cnt["holdout_read_calls"], cnt["test_edit_calls"], cnt["same_turn_test_edits"]) == (1, 1, 1)
    for raw_v, exp in (("REJECT_TIER0_HARD_GATE", "ROLLED_BACK"), ("HALT_VOI_EXHAUSTED", "ABORTED_OSCILLATION"), ("ACCEPT_EPSILON_DIRECTIONAL", "REFINING"), ("CONVERGED_OPTIMAL", "CONVERGED_OPTIMAL")):
        tel = tmp_path / f"tel_{raw_v}.jsonl"
        tel.write_text(json.dumps({"iteration": 2, "delta_k": 1, "fitness_q": 90.0, "verdict": raw_v}) + "\n", encoding="utf-8")
        assert he_mod._read_rsi_file(tel)["status"] == exp


def _assert_gt14_voi_replay_and_canary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyp: Dict[str, Any]) -> None:
    ws_voi = _setup_tensor_ws(tmp_path / "gt14_voi", monkeypatch)
    co_voi = tr_co.TensorRSICoExecutor(workspace_root=ws_voi)
    _write_chained_ledger_rows(ws_voi / "nk_tracking" / "tensor_rsi_ledger.jsonl", "default", 32)
    v_in = co_voi.execute_step("intake", input_data={"session_id": "S_VOI_H2", "prompt": "Migliora scripts/svc.py", "model_tier": "neon", "acs_zone": "Z0"}, baseline_snapshot=tr_sch.MetricSnapshot.model_validate(_snap_payload(88.0, 0.80)))
    v_d = co_voi.execute_step("diagnose", ticket=v_in.ticket, input_data={"reasoning_frame": hyp})
    tkt_obj, st_voi = tr_auth.load_verified_session_state(v_d.ticket, ws_voi)
    raw_i2, _ = tr_auth.commit_session_ticket(ws_voi, tkt_obj.model_copy(update={"iteration": 2, "nonce_hex": "0123456789abcdef0123456789abcdef"}), st_voi)
    v_p = co_voi.execute_step("propose", ticket=raw_i2, input_data={"expected_improvement_k": 1.0})
    assert (v_p.status, (ws_voi / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").exists()) == ("HALT", False)
    repo_2pc = tmp_path / "repo_cli_replay"
    for sub in ("nk_tracking", ".staging/nk_tracking"):
        (repo_2pc / sub).mkdir(parents=True)
    (repo_2pc / "nk_tracking" / "oracle_lock.json").write_text('{"combined_sha256": "a"}', encoding="utf-8")
    (repo_2pc / ".staging" / "nk_tracking" / "oracle_lock.json").write_text('{"combined_sha256": "b"}', encoding="utf-8")
    key_2pc = tmp_path / "cli_rep.key"
    monkeypatch.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_2pc))
    monkeypatch.setenv("NK_GOVERNANCE_NONCE_STORE_PATH", str(tmp_path / "cli_nonces.json"))
    gov_auth.ensure_governance_hmac_key(key_2pc)
    tok_v1 = gov_auth.mint_governance_token("cli_replay_audit_reason", key_path=key_2pc, token_version="v1")
    rc_1, _, _ = call_script_main_captured(_w2pc_mod, ["--promote-staging", "--repo-root", str(repo_2pc), "--keep-staging", "--allow-governance-override", "--override-reason", "cli_replay_audit_reason", "--governance-token", tok_v1])
    (repo_2pc / ".staging" / "nk_tracking" / "oracle_lock.json").write_text('{"combined_sha256": "c"}', encoding="utf-8")
    rc_2, _, err_2 = call_script_main_captured(_w2pc_mod, ["--promote-staging", "--repo-root", str(repo_2pc), "--allow-governance-override", "--override-reason", "cli_replay_audit_reason", "--governance-token", tok_v1])
    assert (rc_1, rc_2, "Replay" in err_2) == (0, 1, True)
    min_can = tmp_path / "min_canary.json"
    min_can.write_text(json.dumps({"tasks": [{"task_id": "C1", "test_a": "x == 1", "test_b": "x == 2"}]}), encoding="utf-8")
    assert (rsi_ch.evaluate_canary_holdout(min_can, require_sha256=False)["passed"], rsi_ch.evaluate_canary_holdout(min_can, require_sha256=True)["passed"]) == (True, False)
    snap_ro, _ = tr_ora.evaluate_ecosystem_ro(ws_voi, coverage_report={"passed": True, "true_branch_coverage_pct": 89.0, "statement_coverage_pct": 92.0})
    assert (snap_ro.g_hard, snap_ro.certification_tier) == (0, "UNMEASURED")


@pytest.mark.integration
def test_gt14_security_h1_h2_h3_and_oracle_h1_h2_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regressione completa VETO GT-14: Security H1..H3 + Oracle/RSI H1..H2 E2E."""
    ws = _setup_tensor_ws(tmp_path / "gt14_sec", monkeypatch)
    hyp = {"hypotheses": [{"hypothesis_id": "H1", "statement": "S1", "target_ref": "a.py:1", "falsification_test": "t1"}, {"hypothesis_id": "H2", "statement": "S2", "target_ref": "a.py:2", "falsification_test": "t2"}], "scope_files": ["scripts/svc.py"]}
    active_p = ws / "nk_tracking" / "tensor_sessions" / "ACTIVE.json"
    assert (_run_tcli(ws, "intake", payload={"prompt": "Audit", "classified_track": "CONTROL"})[1]["status"], _run_tcli(ws, "intake", payload={"prompt": "Migliora", "acs_zone": "Z3"})[1]["status"], active_p.exists()) == ("HALT", "HALT", False)
    s1_in = _run_tcli(ws, "intake", payload={"session_id": "S_OPEN_H1", "prompt": "Migliora scripts/svc.py", "model_tier": "neon", "acs_zone": "Z0"})[1]
    for blk_in in ({"classified_track": "CONTROL"}, {"acs_zone": "Z3"}, {"session_id": "S_OTHER"}):
        rc_blk, out_blk = _run_tcli(ws, "intake", payload=blk_in)
        assert (rc_blk, "ACTIVE_SESSION_CONFLICT" in out_blk["error"]) == (2, True)
    s1_d = _run_tcli(ws, "diagnose", s1_in["ticket"], {"reasoning_frame": hyp})[1]
    s1_e = _run_tcli(ws, "evaluate", _run_tcli(ws, "propose", s1_d["ticket"])[1]["ticket"])[1]
    (ws / ".staging" / "scripts" / "svc.py").write_text("VAL = 777\n", encoding="utf-8")
    rc_toctou, out_toctou = _run_tcli(ws, "decide", s1_e["ticket"])
    assert (rc_toctou, "TOCTOU_STAGING_MISMATCH" in out_toctou["error"], json.loads(active_p.read_text(encoding="utf-8"))["accepted"]) == (2, True, False)
    tr_gm.close_active_session(ws, session_id="S_OPEN_H1")
    st_path = tr_auth.resolve_tensor_state_path(ws, "S_OPEN_H1")
    st_path.write_text(json.dumps({**json.loads(st_path.read_text(encoding="utf-8")), "baseline_snapshot": None}), encoding="utf-8")
    rc_mb, out_mb = _run_tcli(ws, "decide", s1_e["ticket"])
    assert (rc_mb, "MISSING_BASELINE_SNAPSHOT" in out_mb["error"]) == (2, True)
    _assert_gt14_voi_replay_and_canary(tmp_path, monkeypatch, hyp)

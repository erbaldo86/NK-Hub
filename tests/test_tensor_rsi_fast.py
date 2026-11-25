# -*- coding: utf-8 -*-
"""Suite Zero-Mock pure-RAM (<150ms) per Tensor-RSI Core (DOM-01): tests/test_tensor_rsi_fast.py."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import time
from typing import Any, Dict

import pytest

try:
    import conftest as _nk_conftest  # noqa: F401
except ImportError:
    import tests.conftest as _nk_conftest  # noqa: F401

from _internal.tensor_rsi import cold_warm_bandit as tr_cwb, gate_mapper as tr_gm, pareto_gate as tr_par, policy_tensor as tr_pol, schemas as tr_sch, ticket_auth as tr_auth  # noqa: E402
from _internal.vibe_sprint_router.intent_track_classifier import classify_intent_track, resolve_intent_category, resolve_intent_track_profile  # noqa: E402
from _internal.win32_2pc_engine import governance_auth as gov_auth, nonce_store as gov_nonce  # noqa: E402
from _internal.win32_2pc_engine.constants import TwoPhaseCommitError  # noqa: E402

pytestmark = pytest.mark.fast


def _mk_snap(**overrides: Any) -> tr_sch.MetricSnapshot:
    prim_kw: Dict[str, Any] = {
        "p_pass": 1.0, "k_mut": 0.90, "c_branch": 0.88,
        "critical_count": 0, "high_count": 0, "doc_drift_count": 0, "semantic_drift_count": 0,
    }
    for k in list(prim_kw):
        if k in overrides:
            prim_kw[k] = overrides.pop(k)
    sec_kw: Dict[str, Any] = {"v_sec_hyg": 0.90, "v_qual": 0.90, "v_eff": 0.90, "v_ste100": 1.0}
    for k in list(sec_kw):
        if k in overrides:
            sec_kw[k] = overrides.pop(k)
    base_kw: Dict[str, Any] = {
        "intent_track": "CODE_TRACK", "g_hard": 1, "q_v2": 92.0, "delta_k": 1,
        "certification_tier": "CERTIFIED_PASS", "state_hash": "a" * 64,
        "primary": tr_sch.PrimaryInvariantVector(**prim_kw),
        "secondary": tr_sch.SecondaryQualityVector(**sec_kw),
        "tests_total": 20, "failed_tests": 0, "tests_skipped": 0,
        "assert_count": 40, "doc_link_count": 5, "skill_count": 11,
    }
    base_kw.update(overrides)
    return tr_sch.MetricSnapshot(**base_kw)


def _mk_ticket(step_seq: int = 1, phase: tr_sch.PhaseLiteral = "INTAKE", issued_at: int = 1_750_000_000, baseline_sha: str = "c" * 64, **kw: Any) -> tr_sch.TensorRSIStateTicket:
    return tr_sch.TensorRSIStateTicket(
        session_id="TRSI_FAST_01", step_seq=step_seq, iteration=0, phase=phase, intent_track="CODE_TRACK",
        classified_track="IMPROVEMENT", policy_cell_hash="b" * 64, baseline_state_sha256=baseline_sha,
        prev_ticket_sha256="0" * 64, issued_at=issued_at, ttl_seconds=1800, nonce_hex="0123456789abcdef0123456789abcdef", **kw,
    )


@pytest.mark.fast
def test_ticket_auth_json_keys_and_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida JSON strict (no dup, no NaN/Inf), chiave esterna, seed HMAC e path sessione."""
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "keys" / "t.key"))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "sys_tmp"))
    (tmp_path / "sys_tmp").mkdir(parents=True, exist_ok=True)
    assert tr_auth.resolve_tensor_hmac_key_path() == (tmp_path / "keys" / "t.key").resolve()
    for bad_j in ('{"a": 1, "a": 2}', '{"v": NaN}', '{"v": Infinity}', "{bad"):
        with pytest.raises(tr_auth.TicketAuthError):
            tr_auth.strict_json_loads(bad_j)
    with pytest.raises(tr_auth.TicketAuthError):
        tr_auth.canonical_json_bytes({"x": float("nan")})
    empty_key = tmp_path / "empty.key"
    empty_key.write_bytes(b"   ")
    with pytest.raises(tr_auth.TicketAuthError):
        tr_auth.ensure_tensor_hmac_key(empty_key)
    s1 = tr_auth.derive_hmac_seed_int("tag_a")
    assert s1 == tr_auth.derive_hmac_seed_int("tag_a") and s1 != tr_auth.derive_hmac_seed_int("tag_b")
    assert len(tr_auth.repo_hash12(tmp_path)) == 12
    with pytest.raises(tr_auth.TicketAuthError):
        tr_auth.resolve_tensor_state_path(tmp_path, "../bad")


@pytest.mark.fast
def test_ticket_auth_sign_verify_skew_ttl_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida trsi1. firma, payload malformati, finestra skew/TTL e anti-replay con Mutex."""
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "t.key"))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "sys_tmp"))
    (tmp_path / "sys_tmp").mkdir(parents=True, exist_ok=True)
    now_ts = 1_750_000_000
    tkt1 = _mk_ticket(step_seq=1, phase="INTAKE", issued_at=now_ts)
    raw1, _ = tr_auth.commit_session_ticket(tmp_path, tkt1, {"marker": 1})
    assert raw1.startswith("trsi1.") and tr_auth.verify_ticket_signature(raw1, now_ts=now_ts + 100).step_seq == 1
    bad_flip = raw1[:-1] + ("0" if raw1[-1] != "0" else "1")
    for bad_tok in ("", "v1.abc." + ("0" * 64), "trsi1.." + ("a" * 64), "trsi1.abc.short", bad_flip):
        with pytest.raises(tr_auth.TicketAuthError):
            tr_auth.verify_ticket_signature(bad_tok, now_ts=now_ts)
    with pytest.raises(tr_auth.TicketAuthError):
        tr_auth.verify_ticket_signature(raw1, now_ts=now_ts - 31)
    with pytest.raises(tr_auth.TicketAuthError):
        tr_auth.verify_ticket_signature(raw1, now_ts=now_ts + 1801)
    assert tr_auth.load_verified_session_state(raw1, tmp_path, now_ts=now_ts + 5)[1]["marker"] == 1
    raw2, _ = tr_auth.commit_session_ticket(tmp_path, _mk_ticket(step_seq=2, phase="DIAGNOSE", issued_at=now_ts), {"marker": 2}, closed=False)
    with pytest.raises(tr_auth.TicketAuthError, match="TICKET_REPLAY_DETECTED"):
        tr_auth.load_verified_session_state(raw1, tmp_path, now_ts=now_ts + 5)
    forged_seq2 = tr_auth.sign_ticket(_mk_ticket(step_seq=2, phase="PROPOSE", issued_at=now_ts))
    with pytest.raises(tr_auth.TicketAuthError, match="TICKET_REPLAY_DETECTED"):
        tr_auth.load_verified_session_state(forged_seq2, tmp_path, now_ts=now_ts + 5)
    st_path = tr_auth.resolve_tensor_state_path(tmp_path, "TRSI_FAST_01")
    st_obj = json.loads(st_path.read_text(encoding="utf-8"))
    st_path.write_text(json.dumps({**st_obj, "baseline_state_sha256": "f" * 64}), encoding="utf-8")
    with pytest.raises(tr_auth.TicketAuthError, match="Baseline"):
        tr_auth.load_verified_session_state(raw2, tmp_path, now_ts=now_ts + 5)
    raw3, _ = tr_auth.commit_session_ticket(tmp_path, _mk_ticket(step_seq=3, phase="RECORDED", issued_at=now_ts), {"marker": 3}, closed=True)
    with pytest.raises(tr_auth.TicketAuthError):
        tr_auth.load_verified_session_state(raw3, tmp_path, now_ts=now_ts + 5, allow_closed=False)
    assert tr_auth.load_verified_session_state(raw3, tmp_path, now_ts=now_ts + 5, allow_closed=True)[0].step_seq == 3


@pytest.mark.fast
def test_policy_tensor_tiers_acs_spike_and_zones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida resolve_model_tier, spike ACS Z3 da fastguard_<cid>.json e soglie Z0..Z3."""
    ws = tmp_path / "pol_ws"
    cfg_dir = ws / ".staging" / "nk_genome" / "configs" / "tensor_rsi"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "tensor_rsi_v3.json").write_text(json.dumps({"policy_matrix": {"Z1": {"DEFAULT": {"max_in_context_branches": 2, "delegate_subagent_slices": True, "max_subagent_fanout": 1, "max_rsi_iterations_code": 2, "max_rsi_iterations_micro": 1, "pytest_mode": "TARGETED_SLICE"}}}}), encoding="utf-8")
    hooks_tmp = tmp_path / "hooks_tmp"
    (hooks_tmp / "nk_hooks").mkdir(parents=True)
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))
    assert (tr_pol.resolve_model_tier("neon"), tr_pol.resolve_model_tier("generation"), tr_pol.resolve_model_tier("pro")) == ("NEON", "CARBON_GEN", "PRO")
    assert (tr_pol.resolve_model_tier("flash"), tr_pol.resolve_model_tier("unknown_x")) == ("FLASH", "STANDARD")
    (hooks_tmp / "nk_hooks" / "fastguard_cid_spike.json").write_text(json.dumps({"last_actual_tokens": 145_000, "prev_actual_tokens": 115_000, "steps": 60}), encoding="utf-8")
    (hooks_tmp / "nk_hooks" / "fastguard_cid_bad.json").write_text("{corrupt", encoding="utf-8")
    assert (tr_pol.read_acs_state(ws, conversation_id="cid_spike")[0], tr_pol.read_acs_state(ws, conversation_id="cid_bad")[0]) == ("Z3", "Z0")
    assert (tr_pol.read_acs_state(ws, tokens_override=100_000, steps_override=50)[0], tr_pol.read_acs_state(ws, tokens_override=160_000, steps_override=10)[0]) == ("Z0", "Z1")
    assert (tr_pol.read_acs_state(ws, tokens_override=185_000, steps_override=10)[0], tr_pol.read_acs_state(ws, tokens_override=205_000, steps_override=10)[0]) == ("Z2", "Z3")
    assert tr_pol.build_policy_cell(ws, "IMPROVEMENT", model_tier="neon", tokens_override=165_000, steps_override=10).max_in_context_branches == 1


@pytest.mark.fast
def test_policy_tensor_cells_halt_z3_and_operators(tmp_path: Path) -> None:
    """Valida celle PolicyCell per Intent x ModelTier x ACSZone e maschera operatori."""
    ws = tmp_path / "cell_ws"
    (ws / "scripts").mkdir(parents=True)
    c_z0 = tr_pol.build_policy_cell(ws, "IMPROVEMENT", model_tier="neon", tokens_override=50_000, steps_override=20)
    c_z1 = tr_pol.build_policy_cell(ws, "OPTIMIZATION", model_tier="pro", tokens_override=165_000, steps_override=40)
    c_z2 = tr_pol.build_policy_cell(ws, "IMPROVEMENT", model_tier="flash", tokens_override=190_000, steps_override=40)
    c_z3 = tr_pol.build_policy_cell(ws, "IMPROVEMENT", model_tier="carbon", tokens_override=210_000, steps_override=40)
    c_ro = tr_pol.build_policy_cell(ws, "CONTROL", model_tier="neon", tokens_override=10_000, steps_override=5)
    c_doc = tr_pol.build_policy_cell(ws, "DOC_SPEC", model_tier="standard", tokens_override=10_000, steps_override=5)
    assert (c_z0.acs_zone, c_z0.max_in_context_branches, c_z0.subagent_slice_token_cap) == ("Z0", 3, 1200)
    assert (c_z1.acs_zone, c_z1.max_in_context_branches, c_z1.delegate_subagent_slices) == ("Z1", 1, True)
    assert (c_z2.acs_zone, c_z2.max_in_context_branches, c_z2.subagent_slice_token_cap, c_z2.recommend_compact) == ("Z2", 1, 800, True)
    assert (c_z3.acs_zone, c_z3.max_in_context_branches, c_z3.halt_for_handoff, c_z3.max_rsi_iterations, c_z3.pytest_mode) == ("Z3", 0, True, 0, "SKIP_READONLY")
    assert (c_ro.intent, c_ro.max_rsi_iterations, c_ro.pytest_mode) == ("AUDIT_RO", 0, "SKIP_READONLY")
    assert (c_doc.intent_track, c_doc.subagent_slice_token_cap) == ("DOC_TRACK", 350)
    assert len(tr_pol.allowed_operators_for_cell(c_z0, file_count=1)) == 4
    assert "DECOMPOSITION_HELPER_EXTRACT" not in tr_pol.allowed_operators_for_cell(c_z1, file_count=1)
    assert tr_pol.allowed_operators_for_cell(c_z3) == () and tr_pol.allowed_operators_for_cell(c_doc) == ("OP_DOC_ALIGN",)
    with pytest.raises(ValueError):
        tr_sch.PolicyCell(intent="CODE_BUILD", intent_track="CODE_TRACK", model_tier="NEON", acs_zone="Z3", max_rsi_iterations=0, max_in_context_branches=1, delegate_subagent_slices=False, subagent_slice_token_cap=1200, max_subagent_fanout=0, pytest_mode="SKIP_READONLY", halt_for_handoff=True, policy_cell_hash="a" * 64)


@pytest.mark.fast
def test_pareto_secondary_vector_and_tier0_hard_gates() -> None:
    """Valida formula secondary vector (H-D4) e vincoli Tier 0 G_hard_code / G_hard_doc."""
    sec_a = tr_par.compute_secondary_vector(medium_findings=1, low_findings=1, dirty_orphans=1, doc_drift=1, semantic_drift=1, duration_s=14.0, loc_delta=195, ste100_warnings=1)
    sec_nan = tr_par.compute_secondary_vector(duration_s=float("nan"), loc_delta=50, ste100_warnings=0)
    assert math.isclose(sec_a.v_sec_hyg, 1.0 / 1.6, rel_tol=1e-5) and math.isclose(sec_a.v_qual, 1.0 / 1.6, rel_tol=1e-5)
    assert math.isclose(sec_a.v_eff, 0.70, rel_tol=1e-5) and math.isclose(sec_a.v_ste100, 0.9, rel_tol=1e-5)
    assert (sec_nan.v_eff, sec_nan.v_ste100) == (0.5, 1.0)
    base = _mk_snap(q_v2=88.0, v_sec_hyg=0.80, v_qual=0.80, v_eff=0.80, v_ste100=0.80)
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(epistemic_conflict=True)).verdict == "HALT_EPISTEMIC_CONFLICT"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(k_mut=0.79)).verdict == "REJECT_TIER0_HARD_GATE"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(c_branch=0.81)).verdict == "REJECT_TIER0_HARD_GATE"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(mock_count=1)).verdict == "REJECT_TIER0_HARD_GATE"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(certification_tier="UNMEASURED")).verdict == "REJECT_TIER0_HARD_GATE"
    assert tr_par.evaluate_tier0_hard_gates(_mk_snap(intent_track="DOC_TRACK", broken_links=1, failed_tests=1, k_mut=0.0, c_branch=0.0)) == (0, ("broken_links==0", "contract_tests_ok"))
    assert tr_par.evaluate_tier0_hard_gates(_mk_snap(g_hard=0)) == (0, ("ORACLE_G_HARD_ZERO",))


@pytest.mark.fast
def test_pareto_tier1_ratchet_tier2_epsilon_and_hd1() -> None:
    """Valida Tier 1 ratchet eps=0, Tier 2 epsilon-Pareto + proiezione e fix H-D1."""
    base = _mk_snap(q_v2=88.0, v_sec_hyg=0.80, v_qual=0.80, v_eff=0.80, v_ste100=0.80)
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(k_mut=0.89)).verdict == "REJECT_TIER1_REGRESSION"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(high_count=1)).verdict == "REJECT_TIER1_REGRESSION"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(v_eff=0.70)).verdict == "REJECT_TIER2_EPSILON_BAND"
    assert tr_par.evaluate_pareto_decision(base, _mk_snap(k_mut=0.95)).verdict == "ACCEPT_TIER1_DOMINANT"
    strict_ok = tr_par.evaluate_pareto_decision(base, _mk_snap(v_sec_hyg=0.85, v_qual=0.85, v_eff=0.80, v_ste100=0.80))
    assert (strict_ok.verdict, strict_ok.accepted) == ("ACCEPT_PARETO_STRICT", True)
    eps_dir = tr_par.evaluate_pareto_decision(base, _mk_snap(v_sec_hyg=0.85, v_qual=0.85, v_eff=0.77, v_ste100=0.80))
    assert (eps_dir.verdict, eps_dir.accepted) == ("ACCEPT_EPSILON_DIRECTIONAL", True)
    no_gain = tr_par.evaluate_pareto_decision(base, _mk_snap(q_v2=88.0, v_sec_hyg=0.80, v_qual=0.80, v_eff=0.80, v_ste100=0.80))
    assert (no_gain.verdict, no_gain.accepted) == ("REJECT_TIER2_NO_GAIN", False)
    opt = tr_par.evaluate_pareto_decision(base, _mk_snap(q_v2=100.0, v_sec_hyg=0.80, v_qual=0.80, v_eff=0.80, v_ste100=0.80))
    assert (opt.verdict, opt.accepted) == ("CONVERGED_OPTIMAL", True)


@pytest.mark.fast
def test_novelty_gate_pareto_archive_priors_and_lcb_math() -> None:
    """Valida NoveltyGate AST, ParetoArchive <= 12, prior Pi_0, Wilson LCB e Jeffreys LCB_90."""
    gate = tr_cwb.NoveltyGate()
    assert gate.is_novel({"a.py": "def f(x):\n    return x + 1\n"})[0] is True
    assert gate.is_novel({"a.py": "# commento\ndef f(x):\n\n    return x + 1\n"})[0] is False
    assert gate.is_novel({"a.py": "def f(x):\n    return x + 2\n"}, register=False)[0] is True
    assert tr_cwb.compute_structural_ast_hash("def broken(:\n", "bad.py") == tr_cwb.compute_structural_ast_hash("def broken(:\r\n", "bad.py")
    arch = tr_cwb.ParetoArchive(max_size=12)
    assert arch.add_feasible({"g_hard": 0, "state_hash": "0" * 64, "q_v2": 99.0}) is False
    for idx in range(15):
        assert arch.add_feasible({"g_hard": 1, "state_hash": f"{idx:064x}", "q_v2": 70.0 + idx, "file_count": 1 + (idx % 3), "delta_cc": idx % 4, "secondary": (0.8,)}) is True
    assert len(arch.entries) == 12
    assert (tr_cwb.select_prior_signature(is_doc_track=True), tr_cwb.select_prior_signature(acs_zone="Z1"), tr_cwb.select_prior_signature(cc_or_loc_issue=True), tr_cwb.select_prior_signature(k_mut=0.70), tr_cwb.select_prior_signature()) == ("doc_track", "high_context_or_multifile", "complexity_or_loc", "coverage_or_mutation", "sast_or_test_local")
    assert tr_cwb.wilson_lcb_95(0, 0) == 0.0 and 0.5 < tr_cwb.wilson_lcb_95(9, 10) < 0.9
    assert tr_cwb.jeffreys_lcb_90_stochastic(0, 0) == 0.0 and 0.6 < tr_cwb.jeffreys_lcb_90_stochastic(17, 20) < 0.9


@pytest.mark.fast
def test_cold_warm_bandit_voi_hd2_conservation_and_flaky(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida COLD vs WARM vs CALIBRATED, H-D2 VoI, invarianti conservazione e flaky JUnit."""
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "cwb.key"))
    ops = ("SURGICAL_LOCAL_PATCH", "DECOMPOSITION_HELPER_EXTRACT", "TEST_ORACLE_HARDENING", "ISOLATED_SUBAGENT_SLICE")
    cold = tr_cwb.select_operator_cold_warm([{"operator": "SURGICAL_LOCAL_PATCH", "accepted": True, "dry_run": True}], ops, prior_sig="coverage_or_mutation", session_id="S1", step_seq=2, iteration=0, ledger_tail_hash="0" * 64)
    assert (cold.regime, cold.n_samples, cold.selected_operator, cold.thompson_seed_digest, cold.voi_should_stop, round(cold.ucb_score, 4)) == ("COLD", 0, "TEST_ORACLE_HARDENING", None, False, round(0.85 + 0.25 * math.sqrt(math.log(2.0)), 4))
    warm_hist = [{"operator": ops[i % 4], "accepted": i % 2 == 0, "reward": 0.8 if i % 2 == 0 else 0.0, "predicted_accept_prob": 0.5} for i in range(15)]
    w1 = tr_cwb.select_operator_cold_warm(warm_hist, ops, prior_sig="sast_or_test_local", session_id="S2", step_seq=3, iteration=1, ledger_tail_hash="a" * 64)
    w2 = tr_cwb.select_operator_cold_warm(warm_hist, ops, prior_sig="sast_or_test_local", session_id="S2", step_seq=3, iteration=1, ledger_tail_hash="a" * 64)
    assert (w1.regime, w1.n_samples, w1.selected_operator == w2.selected_operator, bool(w1.thompson_seed_digest)) == ("WARM_BANDIT", 15, True, True)
    cal_hist = [{"operator": ops[i % 4], "accepted": False, "reward": 0.0, "predicted_accept_prob": 0.9} for i in range(32)]
    cal = tr_cwb.select_operator_cold_warm(cal_hist, ops, prior_sig="sast_or_test_local", session_id="S3", step_seq=5, iteration=2, ledger_tail_hash="b" * 64, g_hard=1, q_star=88.0, expected_improvement_k=5.0, max_iters=4)
    assert (cal.regime, cal.calibration_degraded, cal.voi_should_stop) == ("CALIBRATED_VOI", True, False)
    assert tr_cwb.compute_voi_stop(n_samples=32, g_hard=1, iteration=2, q_star=88.0, expected_improvement_k=1.0, max_iters=4)[1] is True
    assert tr_cwb.check_conservation_invariants({"tests_total": 10}, {"tests_total": 9}) == (False, ("tests_total:10->9",))
    assert tr_cwb.check_conservation_invariants({"tests_total": 10}, {"tests_total": 9}, approved_reduction=True) == (True, ())
    bad_xml = tmp_path / "bad.xml"
    bad_xml.write_text('<!DOCTYPE foo [<!ENTITY xxe "1">]><testsuite/>', encoding="utf-8")
    with pytest.raises(ValueError):
        tr_cwb.extract_failed_nodeids_from_junit(bad_xml)
    ok_xml = tmp_path / "junit.xml"
    ok_xml.write_text('<testsuite><testcase classname="tests.t_a" name="test_ok"/><testcase classname="tests.t_a" name="test_x"><failure message="boom"/></testcase><testcase classname="tests.t_a" name="test_x"><failure message="dup"/></testcase><testcase classname="tests.t_a" name="test_err"><error message="err"/></testcase></testsuite>', encoding="utf-8")
    nids = tr_cwb.extract_failed_nodeids_from_junit(ok_xml)
    seq = [True, False, True]
    assert tr_cwb.extract_failed_nodeids_from_junit(tmp_path / "missing.xml") == []
    assert (nids, tr_cwb.classify_flaky_nodeids(nids[:1] + ["tests/t_a.py::test_y"], rerun_fn=lambda n: seq.pop(0) if "test_x" in n else False, reruns=3)) == (["tests/t_a.py::test_x", "tests/t_a.py::test_err"], (("tests/t_a.py::test_x",), ("tests/t_a.py::test_y",)))


@pytest.mark.fast
def test_gate_mapper_strict_and_active_conflict(tmp_path: Path) -> None:
    """Valida GateMapper GATE_1..6 + ALL_PASSED, H1/H2 strict e ACTIVE.json conflict."""
    assert tr_gm.map_gates(_mk_snap()).last_cold_review_gate == "ALL_PASSED"
    for bad_kw, exp_gate in (
        ({"scope_creep": 1}, "GATE_1_SCOPE"), ({"hallucinated_refs": 1}, "GATE_2_CODE_GROUNDING"), ({"mock_count": 1}, "GATE_5_TRUTH_DAST"), ({"s_taint": 1}, "GATE_5_TRUTH_DAST"),
        ({"f_holdout": 1}, "GATE_5_TRUTH_DAST"), ({"dry_run": 1}, "GATE_5_TRUTH_DAST"), ({"g_hard": 0}, "GATE_6_RSI_CONVERGENCE"), ({"certification_tier": "UNMEASURED"}, "GATE_6_RSI_CONVERGENCE"),
    ):
        assert tr_gm.map_gates(_mk_snap(**bad_kw)).last_cold_review_gate == exp_gate
    assert tr_gm.map_gates(_mk_snap(), ast_ok=False).last_cold_review_gate == "GATE_2_CODE_GROUNDING"
    assert tr_gm.map_gates(_mk_snap(contract_violations=1), ast_ok=True).last_cold_review_gate == "GATE_3_BRIEF_GROUNDING"
    assert tr_gm.map_gates(_mk_snap(), conservation_ok=False).last_cold_review_gate == "GATE_4_PRESERVATION"
    tr_gm.write_active_session(tmp_path, "S_A", "INTAKE", False, "0" * 64)
    for bad_fn in (lambda: tr_gm.close_active_session(tmp_path), lambda: tr_gm.close_active_session(tmp_path, session_id="S_B"), lambda: tr_gm.write_active_session(tmp_path, "S_B", "INTAKE", False, "1" * 64)):
        with pytest.raises(tr_auth.TicketAuthError, match="ACTIVE_SESSION_CONFLICT"):
            bad_fn()
    tr_gm.close_active_session(tmp_path, session_id="S_A")
    assert not (tmp_path / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").exists()


@pytest.mark.fast
def test_intent_track_classifier_and_profiles() -> None:
    """Valida IntentTrackClassifier ortogonale e profili Tensor-RSI."""
    assert (classify_intent_track(""), classify_intent_track("Cosa fa questo modulo?"), classify_intent_track("Verifica e analizza stato del sistema senza modifiche")) == ("CONTROL", "CONTROL", "CONTROL")
    assert (classify_intent_track("Aggiorna la documentazione SKILL.md secondo STE100"), classify_intent_track("Ottimizza latenza e complessita CC del parser Python"), classify_intent_track("Implementa validazione Pydantic in scripts/tensor_rsi.py")) == ("DOC_SPEC", "OPTIMIZATION", "IMPROVEMENT")
    assert (resolve_intent_track_profile("OPTIMIZATION"), resolve_intent_category("DOC_SPEC"), resolve_intent_category("CONTROL"), resolve_intent_category("IMPROVEMENT", is_micro=True)) == ("refactor_rsi", "SPEC_DOC", "AUDIT_RO", "MICRO_VIBE")


@pytest.mark.fast
def test_nonce_store_v2_replay_vs_v1_legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida anti-replay su v2: / consume_nonce=True, batch scope e compatibilita v1: legacy."""
    key_p, store_p = tmp_path / "gov.key", tmp_path / "gov_nonces.json"
    monkeypatch.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_p))
    monkeypatch.setenv("NK_GOVERNANCE_NONCE_STORE_PATH", str(store_p))
    gov_auth.ensure_governance_hmac_key(key_p)
    tok_v1 = gov_auth.mint_governance_token("motivo valido v1", key_path=key_p, token_version="v1")
    assert gov_auth.authorize_governance_override("motivo valido v1", tok_v1, "scripts/a.py", key_path=key_p)["version"] == "v1"
    assert gov_auth.authorize_governance_override("motivo valido v1", tok_v1, "scripts/b.py", key_path=key_p)["valid"] is True
    tok_v2 = gov_auth.mint_governance_token("motivo valido v2", key_path=key_p, token_version="v2")
    with gov_nonce.governance_batch_nonce_scope(enforce=True):
        assert gov_auth.authorize_governance_override("motivo valido v2", tok_v2, "scripts/c.py", key_path=key_p)["version"] == "v2"
        assert gov_auth.authorize_governance_override("motivo valido v2", tok_v2, "scripts/d.py", key_path=key_p)["valid"] is True
    with pytest.raises(TwoPhaseCommitError, match="Replay"):
        gov_auth.authorize_governance_override("motivo valido v2", tok_v2, "scripts/c.py", key_path=key_p)
    tok_s = gov_auth.mint_governance_token("motivo valido strict", key_path=key_p, token_version="v1")
    assert gov_auth.authorize_governance_override("motivo valido strict", tok_s, "scripts/d.py", key_path=key_p, consume_nonce=True)["valid"] is True
    with pytest.raises(TwoPhaseCommitError, match="Replay"):
        gov_auth.verify_governance_token(tok_s, "motivo valido strict", key_path=key_p, consume_nonce=True)
    bad_store = tmp_path / "bad_nonces.json"
    bad_store.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError):
        gov_nonce.verify_or_consume_governance_nonce("ab" * 16, int(time.time()), 60, check_replay=True, consume=False, store_path=bad_store)
    assert gov_nonce.verify_or_consume_governance_nonce("ab" * 16, int(time.time()), 60, check_replay=False, consume=False, store_path=store_p) is True


def _assert_corrupt_ledger_rejected_and_seed_other(
    tmp_path: Path, c_doc: Any, p_acc: Any, base: tr_sch.MetricSnapshot
) -> str:
    ledger_p = tmp_path / "nk_tracking" / "tensor_rsi_ledger.jsonl"
    ledger_p.parent.mkdir(parents=True, exist_ok=True)
    for bad_txt in ("\n[]\n", '{"intent_track":"OTHER","clade_id":"other","record_hash":"' + ("e" * 64) + '"}\n'):
        ledger_p.write_text(bad_txt, encoding="utf-8")
        with pytest.raises(tr_auth.TicketAuthError, match="LEDGER_CHAIN_CORRUPT"):
            tr_gm.read_tensor_ledger_entries(tmp_path, "CODE_TRACK", "main")
    ledger_p.unlink()
    seed_tkt = _mk_ticket(step_seq=1).model_copy(update={"session_id": "S_OTHER", "intent_track": "DOC_TRACK", "classified_track": "SPEC_DOC"})
    tr_gm.append_tensor_ledger_entry(tmp_path, {"clade_id": "other"}, seed_tkt, c_doc, p_acc, _mk_snap(intent_track="DOC_TRACK", q_v2=93.0), base)
    code_empty, tail_0 = tr_gm.read_tensor_ledger_entries(tmp_path, "CODE_TRACK", "main")
    assert code_empty == [] and len(tail_0) == 64
    return tail_0


@pytest.mark.fast
def test_gate_mapper_ledger_chain_and_owner(tmp_path: Path) -> None:
    """Valida chain ledger hash-chained fail-closed, fallback operatore/regime/reward e owner ACTIVE.json."""
    assert tr_gm.read_tensor_ledger_entries(tmp_path, "CODE_TRACK", "main") == ([], "0" * 64)
    base = _mk_snap(q_v2=88.0, v_sec_hyg=0.80, v_qual=0.80, v_eff=0.80, v_ste100=0.80)
    p_acc = tr_par.evaluate_pareto_decision(base, _mk_snap(v_sec_hyg=0.85, v_qual=0.85, v_eff=0.80, v_ste100=0.80))
    p_rej = tr_par.evaluate_pareto_decision(base, _mk_snap(k_mut=0.79))
    c_doc, c_code = tr_pol.build_policy_cell(tmp_path, "DOC_SPEC", model_tier="neon", tokens_override=1000, steps_override=1), tr_pol.build_policy_cell(tmp_path, "IMPROVEMENT", model_tier="neon", tokens_override=1000, steps_override=1)
    tail_0 = _assert_corrupt_ledger_rejected_and_seed_other(tmp_path, c_doc, p_acc, base)

    tr_gm.append_tensor_ledger_entry(tmp_path, {"clade_id": "main"}, _mk_ticket(), c_doc, p_acc, _mk_snap(intent_track="DOC_TRACK", q_v2=93.0), base)
    doc_rows, tail_1 = tr_gm.read_tensor_ledger_entries(tmp_path, "DOC_TRACK", "main")
    exp_rw = round(max(0.0, min(1.0, 0.6 + 0.4 * math.tanh(10.0 * p_acc.directional_projection))), 6)
    assert (len(doc_rows), doc_rows[0]["operator"], doc_rows[0]["regime"], doc_rows[0]["predicted_accept_prob"], doc_rows[0]["reward"], doc_rows[0]["prev_hash"]) == (1, "OP_DOC_ALIGN", "COLD", 0.5, exp_rw, tail_0)
    tr_gm.append_tensor_ledger_entry(tmp_path, {"clade_id": "main", "cold_warm": {"regime": "WARM_BANDIT"}}, _mk_ticket(step_seq=2, predicted_accept_prob=0.82), c_code, p_rej, _mk_snap(q_v2=84.0), base)
    tr_gm.append_tensor_ledger_entry(tmp_path, {"clade_id": "main"}, _mk_ticket(step_seq=3, selected_operator="TEST_ORACLE_HARDENING"), c_code, p_acc, _mk_snap(q_v2=91.0), base)
    code_rows, tail_2 = tr_gm.read_tensor_ledger_entries(tmp_path, "CODE_TRACK", "main")
    assert (len(code_rows), code_rows[0]["operator"], code_rows[0]["regime"], code_rows[0]["predicted_accept_prob"], code_rows[0]["reward"], code_rows[0]["prev_hash"]) == (2, "SURGICAL_LOCAL_PATCH", "WARM_BANDIT", 0.82, 0.0, doc_rows[0]["record_hash"])
    assert (code_rows[1]["operator"], code_rows[1]["prev_hash"], tail_2 == code_rows[1]["record_hash"], tail_2 != tail_1) == ("TEST_ORACLE_HARDENING", code_rows[0]["record_hash"], True, True)
    tr_gm.write_active_session(tmp_path, "S_OK", "DECIDE", True, "0" * 64)
    with pytest.raises(tr_auth.TicketAuthError, match="ACTIVE_SESSION_CONFLICT"):
        tr_gm.close_active_session(tmp_path, session_id="S_OTHER")
    tr_gm.close_active_session(tmp_path)
    (tmp_path / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").write_text("{corrupt", encoding="utf-8")
    with pytest.raises(tr_auth.TicketAuthError, match="ACTIVE_SESSION_CONFLICT"):
        tr_gm.ensure_no_foreign_active_session(tmp_path)

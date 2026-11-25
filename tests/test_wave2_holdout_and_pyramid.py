# -*- coding: utf-8 -*-
"""
Suite di verifica Wave 2 (NK-GEN-2.0.0-W2): Holdout TAS v2, Behavioral v2, Conftest, Ceilings, DOM-06 e Triple Lock.
Modulo: tests/test_wave2_holdout_and_pyramid.py.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

import pytest

try:
    import conftest as _conftest_mod
    from conftest import (
        call_script_main_captured,
        load_nk_script_module,
    )
except ImportError:
    from tests import conftest as _conftest_mod
    from tests.conftest import (
        call_script_main_captured,
        load_nk_script_module,
    )

_agv_mod = load_nk_script_module("ast_guard_validator")
_dast_mod = load_nk_script_module("dast_sandbox_runner")
_sbfl_mod = load_nk_script_module("sbfl_pytest_bridge")
_ora_mod = load_nk_script_module("oracle_evaluator_l3")
_mut_mod = load_nk_script_module("builder_mutation_gate")
_rsi_mod = load_nk_script_module("rsi_convergence_engine")
_w2pc_mod = load_nk_script_module("win32_2pc_engine")
_qbm_mod = load_nk_script_module("quality_baseline_manager")
_hook_mod = load_nk_script_module("nk_hook_gate")
_comp_mod = load_nk_script_module("nk_compliance_checker")
_ntt_mod = load_nk_script_module("nk_transcript_tools")
_idx_mod = load_nk_script_module("nk_registry_indexer")

from _internal.ast_guard_validator import quality_diff_checker as qd_chk  # noqa: E402
from _internal.builder_mutation_gate import (  # noqa: E402
    mutant_gen as mg_mod,
    operators as mut_ops,
    runner as mut_runner,
)
from _internal.dast_sandbox_runner import (  # noqa: E402
    cli as dast_cli,
    constants as dast_consts,
    holdout_verify as dast_hv,
    staging_overlay as dast_ov,
)
from _internal.nk_common import (  # noqa: E402
    gt14_envelope as gt14_mod,
    oracle_lock as ol_mod,
    prompt_linter_core as pl_mod,
    repo_snapshot_cache as rsc_mod,
)
from _internal.nk_registry_indexer import shards as shards_mod  # noqa: E402
from _internal.oracle_evaluator_l3 import gate_validators as ora_gv  # noqa: E402
from _internal.quality_baseline_manager import constants as qbm_consts  # noqa: E402
from _internal.rsi_convergence_engine import (  # noqa: E402
    canary_holdout as ch_mod,
    profiles as rsi_prof,
)
from _internal.sbfl_pytest_bridge import (  # noqa: E402
    frame_extractor as fe_mod,
    matrix_engine as sb_me,
    models as sb_models,
    runner_and_cli as sb_rc,
)
from _internal.win32_2pc_engine import (  # noqa: E402
    governance_auth as gauth_mod,
    staging_guards as sg_mod,
)


def _load_holdout_json(rel_path: str) -> Dict[str, Any]:
    target = _conftest_mod._resolve_staged_or_prod(rel_path)
    return json.loads(target.read_text(encoding="utf-8"))


def _make_dast_holdout_repo(root: Path, *, with_locks: bool = True) -> None:
    for d in (
        "scripts",
        "tests/evals",
        "nk_tracking/benchmark_suite",
        "nk_tracking/oracle_holdout",
        ".github/workflows",
        ".staging/scripts",
    ):
        (root / d).mkdir(parents=True, exist_ok=True)
    test_f = root / "tests" / "t_ok.py"
    eval_f = root / "tests" / "evals" / "skill_golden_eval_set.json"
    gh_f = root / ".github" / "workflows" / "ci.yml"
    suite_f = root / "nk_tracking" / "benchmark_suite" / "tasks_stub.json"
    oh_f = root / "nk_tracking" / "oracle_holdout" / "tas_behavioral_v2.json"
    test_f.write_text("def test_one():\n    assert 1 == 1\n", encoding="utf-8")
    eval_f.write_text('{"cases": [1]}\n', encoding="utf-8")
    gh_f.write_text("name: ci\n", encoding="utf-8")
    suite_f.write_text('{"tasks": []}\n', encoding="utf-8")
    oh_f.write_text('{"suite_id": "tas_behavioral_v2"}\n', encoding="utf-8")
    (root / "scripts" / "app.py").write_text("VAL = 1\n", encoding="utf-8")
    (root / ".staging" / "scripts" / "app.py").write_text("VAL = 2\n", encoding="utf-8")
    if not with_locks:
        return
    o_files = {
        "t_ok.py": ol_mod.compute_lf_sha256(test_f),
        "evals/skill_golden_eval_set.json": ol_mod.compute_lf_sha256(eval_f),
        "../.github/workflows/ci.yml": ol_mod.compute_lf_sha256(gh_f),
    }
    h_files = {"tas_behavioral_v2.json": ol_mod.compute_lf_sha256(oh_f)}
    s_files = {"app.py": ol_mod.compute_lf_sha256(root / "scripts" / "app.py")}
    lock_specs = (
        ("oracle_lock.json", root / "tests", o_files),
        ("oracle_lock_holdout.json", root / "nk_tracking" / "oracle_holdout", h_files),
        ("governance_lock.json", root / "scripts", s_files),
    )
    for lk_name, t_dir, fmap in lock_specs:
        payload = {
            "target": t_dir.as_posix(),
            "files": fmap,
            "combined_sha256": ol_mod.compute_combined_sha256(fmap),
        }
        (root / "nk_tracking" / lk_name).write_text(json.dumps(payload), encoding="utf-8")


def _run_tas_01(ws: Path, expected: Dict[str, Any]) -> None:
    bad_py = ws / "tas01_sqli.py"
    bad_py.write_text(
        'def q_user(cur, uid: str):\n    sql = "SELECT * FROM u WHERE id=" + uid\n    return cur.execute(sql)\n',
        encoding="utf-8",
    )
    direct_v = _agv_mod.ASTGuardValidator.check_sast_constructs(
        bad_py.read_text(encoding="utf-8"), "src_app/tas01_sqli.py"
    )
    assert len(direct_v) >= expected["min_violations"]
    rc, out, _ = call_script_main_captured(_agv_mod, ["--target", str(bad_py), "--json"])
    payload = json.loads(out)
    assert rc == expected["cli_rc"]
    assert payload["passed"] is expected["passed"]
    assert isinstance(payload["violations"], list)
    assert len(payload["violations"]) >= expected["min_violations"]


def _run_tas_02(ws: Path, expected: Dict[str, Any]) -> None:
    syn_v = qd_chk.check_python_quality_diff("def ok():\n    return 1\n", "def bad(:\n", "src_app/bad.py")
    assert syn_v and syn_v[0].rule_id == expected["syntax_rule"]
    stg = ws / "tas02_stg"
    (stg / "scripts").mkdir(parents=True, exist_ok=True)
    (stg / "scripts" / "allowed.py").write_text("def ok(x: int) -> int:\n    return x\n", encoding="utf-8")
    (stg / "scripts" / "extra.py").write_text("X = 1\n", encoding="utf-8")
    rc_bad, out_bad, _ = call_script_main_captured(
        _agv_mod,
        ["--stage-dir", str(stg), "--quality-diff", "--allowed-files", "scripts/allowed.py", "--json"],
    )
    data_bad = json.loads(out_bad)
    assert rc_bad == expected["fail_closed_rc"]
    assert any(d["rule_id"] == expected["scope_rule"] for d in data_bad["quality_diff_details"])


def _run_tas_03(_ws: Path, expected: List[str]) -> None:
    observed = [
        dast_cli.classify_poc_outcome(1, "EXPLOIT_CONFIRMED", "AssertionError: exploit"),
        dast_cli.classify_poc_outcome(1, "", "ModuleNotFoundError: No module named 'x'"),
        dast_cli.classify_poc_outcome(0, "REFUTED", ""),
    ]
    assert observed == expected
    assert dast_cli.classify_poc_outcome(1, "", "SyntaxError: bad") == "HARNESS_ERROR"
    assert dast_cli.classify_poc_outcome(0, "", "", timed_out=True) == "EXPLOIT_CONFIRMED"


def _run_tas_04(ws: Path, expected: Dict[str, Any]) -> None:
    repo = ws / "tas04_repo"
    _make_dast_holdout_repo(repo, with_locks=True)
    for lk_name in ("tests_holdout_lock.json", "tensor_rsi_lock.json"):
        (repo / "nk_tracking" / lk_name).write_text('{"files": {}}', encoding="utf-8")
    (repo / "nk_tracking" / "tensor_sessions").mkdir(parents=True, exist_ok=True)
    (repo / "nk_tracking" / "tensor_sessions" / "sess.json").write_text("{}", encoding="utf-8")
    with _dast_mod.ShadowSandbox() as sb:
        _, _, stripped = dast_ov.prepare_staging_overlay(repo, repo / ".staging", sb, "builder")
        assert len(stripped) >= expected["stripped_count_min"]
        for rel in dast_consts._BUILDER_STRIP_PATHS:
            assert rel in stripped
            assert (sb.sandbox_dir / rel).exists() is (not expected["holdouts_absent"])


def _run_tas_05(ws: Path, expected: Dict[str, Any]) -> None:
    repo = ws / "tas05_repo"
    _make_dast_holdout_repo(repo, with_locks=True)
    with _dast_mod.ShadowSandbox() as sb:
        ov, del_f, _ = dast_ov.prepare_staging_overlay(repo, repo / ".staging", sb, "evaluator")
        ok_rep = dast_hv.verify_sandbox_holdouts(repo, sb.sandbox_dir, "evaluator", ov, del_f)
        assert ok_rep["passed"] is expected["clean_evaluator_passed"]
        (sb.sandbox_dir / "nk_tracking" / "oracle_lock_holdout.json").write_text("{bad", encoding="utf-8")
        bad_rep = dast_hv.verify_sandbox_holdouts(repo, sb.sandbox_dir, "evaluator", ov, del_f)
        assert bad_rep["passed"] is expected["tamper_passed"]
        overlaid = dast_hv._check_overlay_and_tombstones({"nk_tracking/oracle_holdout/x.json"}, [])
        assert bool(overlaid) is (not expected["overlay_passed"])


def _run_tas_06(ws: Path, expected: Dict[str, Any]) -> None:
    pkg_dir = ws / "tas06_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "svc.py").write_text(
        "def run_calc(x):\n    y = x + 1\n    assert y > 0, 'neg " + ("word " * 30) + "'\n    return y\n",
        encoding="utf-8",
    )
    recs = [
        sb_models.CoverageRecord(test_id="t1", passed=True, executed_statements=["tas06_pkg/svc.py:1", "tas06_pkg/svc.py:4"]),
        sb_models.CoverageRecord(test_id="t2", passed=False, executed_statements=["tas06_pkg/svc.py:1", "tas06_pkg/svc.py:3"]),
    ]
    mat = sb_me.CoverageMatrix.from_records(recs)
    ranked = sb_me.SBFLEngine().analyze(mat)
    assert ranked[0].statement == "tas06_pkg/svc.py:3" and ranked[0].ochiai == expected["top_ochiai"]
    cands = [("tas06_pkg/svc.py", 3, 1.0), ("tas06_pkg/svc.py", 2, 0.7), ("tas06_pkg/svc.py", 1, 0.5), ("tas06_pkg/svc.py", 4, 0.2)]
    slices = fe_mod.build_hybrid_fl_slices(cands, [ws], max_blocks=expected["max_slices"], max_tokens=expected["max_slice_tokens"])
    assert len(slices) <= expected["max_slices"] and all(s["tokens"] <= expected["max_slice_tokens"] for s in slices)
    bridge = _sbfl_mod.SBFLPytestBridge(cwd=ws)
    summary = sb_models.PytestRunSummary(
        total_tests=2, passed_count=1, failed_count=1, error_count=0, exit_code=1, duration_sec=0.02,
        failed_test_names=["t2"], passed_test_names=["t1"], raw_stdout="tas06_pkg/svc.py:3: AssertionError",
    )
    loc = bridge.extract_failure_location(summary, target_file_hint="tas06_pkg/svc.py", coverage_records=recs)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(bridge, "run_and_diagnose", lambda **_kw: (summary, loc))
        rc = sb_rc._emit_hybrid_bridge_result(summary, loc, bridge, as_json=False)
    assert rc == 1 and loc is not None and loc.line_number == 3


def _run_tas_07(ws: Path, expected: Dict[str, Any]) -> None:
    html_p = ws / "tas07_page.html"
    html_p.write_text("<main><h1>Title</h1></main>", encoding="utf-8")
    rc, out, _ = call_script_main_captured(_ora_mod, ["--html-file", str(html_p), "--json"])
    payload = json.loads(out)
    assert rc == expected["self_compare_rc"]
    assert payload["verdict"] == "FAIL" and "self-comparison" in payload["summary_message"]
    for unc in (r"\\server\share\x.html", "//server/share/x.html", r"\\?\UNC\server\share\x.html"):
        with pytest.raises(ValueError, match="UNC"):
            ora_gv.resolve_html_source(unc, allowed_roots=[ws])
        with pytest.raises(ValueError, match="UNC"):
            ora_gv.resolve_expected_source(unc, allowed_roots=[ws])


def _run_tas_08(ws: Path, expected: Dict[str, Any]) -> None:
    op_cases = [
        ("a == b", ast.Compare, None, "ComparisonFlip"),
        ("a and b", ast.BoolOp, None, "BoolOpFlip"),
        ("a + b", ast.BinOp, None, "BinOpFlip"),
        ("x += 1", ast.AugAssign, None, "AugAssignFlip"),
        ("return True", ast.Return, None, "BoolReturnFlip"),
        ("return v", ast.Return, None, "ReturnNoneFlip"),
    ]
    matched_ops = {mut_ops.match_operator_for_node(next(n for n in ast.walk(ast.parse(c)) if isinstance(n, cls)), p) for c, cls, p, _ in op_cases}
    if_n = ast.parse("if not ok:\n    pass\n").body[0]
    matched_ops.add(mut_ops.match_operator_for_node(if_n.test, if_n))
    rng_call = next(n for n in ast.walk(ast.parse("for i in range(0):\n    pass\n")) if isinstance(n, ast.Call))
    matched_ops.add(mut_ops.match_operator_for_node(rng_call.args[0], rng_call))
    assert len(matched_ops - {None}) == expected["operators_count"]
    path_bin = next(n for n in ast.walk(ast.parse('Path("a") / "x"')) if isinstance(n, ast.BinOp))
    assert (mut_ops.match_operator_for_node(path_bin, None) is None) is expected["path_div_skipped"]
    spec = mg_mod.MutantSpec(mutant_id="M1", operator="BinOpFlip", rel_path="a.py", function_name="f", line_number=1, original_snippet="+", mutated_snippet="-", mutated_source="x")
    assert (mut_runner._to_mutant_outcome(spec, 1, 0.01).killed is True) is expected["killed_only_rc_1"]
    assert mut_runner._to_mutant_outcome(spec, 2, 0.01).killed is False
    assert mut_runner._to_mutant_outcome(spec, 0, 0.01).killed is False


def _run_tas_09(ws: Path, expected: Dict[str, Any]) -> None:
    repo = ws / "tas09_repo"
    for d in ("scripts", "tests", ".staging/scripts"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "const_mod.py").write_text("VAL = 1\n", encoding="utf-8")
    (repo / ".staging" / "scripts" / "const_mod.py").write_text('CONST_TEXT = "pure"\n', encoding="utf-8")
    (repo / "tests" / "test_c.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mut_runner, "_run_pytest_fail_fast", lambda *_a, **_kw: (0, 0.01))
        rep = mut_runner.run_mutation_gate(repo, "scripts/const_mod.py", ["tests/test_c.py"], stage_dir=repo / ".staging")
    assert rep.status == expected["status"]
    assert rep.passed is expected["passed"]
    assert rep.mutants_total == expected["mutants_total"]


def _run_tas_10(_ws: Path, expected: Dict[str, Any]) -> None:
    base_vec = _rsi_mod.RSIDefectVector(tests_total=10, tests_passed=10)
    skip_res = rsi_prof.compute_fitness_v2(base_vec, k_mut_diff=0.9, c_branch_diff=0.8, tests_skipped=1)
    assert skip_res["g_hard"] == expected["g_hard_fail"]
    assert "tests_skipped==0" in skip_res["failed_hard_gates"]
    low_q, high_q = expected["q_range"]
    assert low_q <= skip_res["q_v2"] <= high_q
    game_vec = _rsi_mod.RSIDefectVector(tests_total=10, tests_passed=10, deception_gaming_count=1)
    game_res = rsi_prof.compute_fitness_v2(game_vec, k_mut_diff=0.9, c_branch_diff=0.8)
    assert game_res["gaming_penalty"] == expected["gaming_penalty"]
    assert game_res["q_v2"] == 0.0 and "G_dec==0" in game_res["failed_hard_gates"]


def _run_tas_11(_ws: Path, expected: Dict[str, Any]) -> None:
    vec = _rsi_mod.RSIDefectVector(tests_total=10, tests_passed=10)
    doc_res = rsi_prof.compute_fitness_v2(vec, has_python_diff=False, ste100_score=1.0)
    assert doc_res["certification_tier"] == expected["doc_only_tier"] and doc_res["q_v2"] == 100.0
    unm_res = rsi_prof.compute_fitness_v2(vec, has_python_diff=True, k_mut_diff=None, c_branch_diff=0.8)
    assert unm_res["certification_tier"] == expected["unmeasured_tier"]
    assert unm_res["q_v2"] <= expected["unmeasured_cap"]
    assert "MISSING_K_MUT_DIFF" in unm_res["unmeasured_reasons"]


def _run_tas_12(ws: Path, expected: Dict[str, Any]) -> None:
    key_p = ws / "tas12_gov.key"
    tok = gauth_mod.mint_governance_token("tas12_reason", key_path=key_p, nonce="12AB")
    assert gauth_mod.verify_governance_token(tok, "tas12_reason", key_path=key_p)["valid"] is expected["valid_token_verified"]
    tampered = tok[:-1] + ("1" if tok.endswith("0") else "0")
    with pytest.raises(_w2pc_mod.TwoPhaseCommitError):
        gauth_mod.verify_governance_token(tampered, "tas12_reason", key_path=key_p)
    assert expected["tamper_rejected"] is True
    for bad_rep in ({}, {"outcome": "DRY_RUN_PASS", "passed": True}, {"status": "UNMEASURED", "passed": True}):
        with pytest.raises(_w2pc_mod.TwoPhaseCommitError):
            sg_mod.validate_sandbox_report_not_dry_run(bad_rep)
    assert expected["dry_run_rejected"] is True


def _run_tas_13(ws: Path, expected: Dict[str, Any]) -> None:
    assert len(qbm_consts.SCHEMA_V2_LIVE_KEYS) == expected["live_metrics_count"]
    assert qbm_consts.MAX_PYTEST_DURATION_CEIL == expected["duration_ceil"]
    assert _qbm_mod.MAX_PYTEST_FAST_DURATION_CEIL == expected["fast_duration_ceil"]
    bl_file = ws / "tas13_baseline.json"
    rc, out, _ = call_script_main_captured(_qbm_mod, ["update", "--check-only", "--file", str(bl_file), "--json"])
    payload = json.loads(out)
    assert rc == expected["check_only_rc"] and payload["status"] == "REJECTED" and not bl_file.exists()


def _run_tas_14(ws: Path, expected: Dict[str, Any]) -> None:
    hub = ws / "tas14_hub"
    (hub / ".staging" / "tests").mkdir(parents=True, exist_ok=True)
    for tgt in ("tests/test_x.py", "nk_tracking/oracle_holdout/h.json", "nk_tracking/oracle_lock_holdout.json", "nk_tracking/governance_lock.json"):
        assert (_hook_mod._classify_protected_target(tgt, "", hub).get("decision") == "deny") is expected["prod_denied"]
    assert (_hook_mod._classify_protected_target(".staging/tests/test_x.py", "", hub) == {}) is expected["staging_allowed"]


def _run_tas_15(ws: Path, expected: Dict[str, Any]) -> None:
    assert _comp_mod._is_production_code_write(".agents/skills/X/SKILL.md") is expected["unstaged_gov_flagged"]
    assert _comp_mod._is_production_code_write("nk_tracking/oracle_lock_holdout.json") is expected["unstaged_tracking_flagged"]
    assert _comp_mod._is_production_code_write(".staging/nk_tracking/oracle_lock.json") is (not expected["staged_exempt"])
    tr_file = ws / "tas15_transcript.jsonl"
    rec = {"role": "model", "tool_calls": [{"name": "write_file", "args": {"Path": ".agents/skills/X/SKILL.md"}}]}
    tr_file.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    audit = _comp_mod.NKComplianceChecker(workspace_root=ws).audit_transcript(tr_file)
    assert audit["metrics"]["code_write_calls"] >= 1


def _run_tas_16(ws: Path, expected: Dict[str, Any]) -> None:
    cache = rsc_mod.RepoSnapshotCache()
    sha = cache._full_sha256("nk-hub-v2")
    assert len(sha) == expected["sha256_len"]
    dig = gt14_mod.build_gt14_exec_digest("PASS", 1, {"a": "z" * 150}, ["F" * 110] * 5, pointer_uri="file:///tmp/p.json")
    assert gt14_mod.estimate_compact_tokens(dig) <= expected["max_digest_tokens"]
    bad_p = "Usa nk-builder-agent per modificare src_app/x.py finche 100% pass usando search_web e tavily con 30 queries su canary_v1.json"
    codes = {v["code"] for v in pl_mod.evaluate_ap_rules(bad_p)["violations"]}
    assert set(expected["ap_rules"]).issubset(codes)
    eol_f = ws / "tas16_eol.txt"
    eol_f.write_bytes(b"line1\r\nline2\r\n")
    lf_sha = ol_mod.compute_lf_sha256(eol_f)
    assert ol_mod.sha256_eol_matches(eol_f, lf_sha) is expected["eol_tolerant"]


_TAS_HANDLERS: Dict[str, Callable[[Path, Any], None]] = {
    "tas_ast_taint_cli_json": _run_tas_01,
    "tas_ast_quality_diff_syntax_error": _run_tas_02,
    "tas_dast_poc_tristate": _run_tas_03,
    "tas_dast_builder_strip": _run_tas_04,
    "tas_dast_verify_holdout_fail_closed": _run_tas_05,
    "tas_sbfl_ochiai_hybrid_fl": _run_tas_06,
    "tas_oracle_l3_self_compare_unc": _run_tas_07,
    "tas_mutation_8ops_and_killed": _run_tas_08,
    "tas_mutation_zero_mutant_unmeasured": _run_tas_09,
    "tas_rsi_qv2_hard_gate_gaming": _run_tas_10,
    "tas_rsi_static_pass_unmeasured_cap": _run_tas_11,
    "tas_2pc_hmac_and_dast_guard": _run_tas_12,
    "tas_qbm_schema_v2_readonly": _run_tas_13,
    "tas_hook_gate_classifier_blocks": _run_tas_14,
    "tas_compliance_unstaged_governance": _run_tas_15,
    "tas_nk_common_primitives": _run_tas_16,
}


def _execute_behavioral_suite(suite: Dict[str, Any]) -> Dict[str, float]:
    ev_hits = 0
    for probe in suite["sast_evasion"]:
        hits = _agv_mod.ASTGuardValidator.check_sast_constructs(probe["code"], probe["target_file"])
        assert bool(hits) is bool(probe["expected_detected"]), probe["probe_id"]
        ev_hits += int(bool(hits))

    fp_count = 0
    for probe in suite["sast_non_fp"]:
        hits = _agv_mod.ASTGuardValidator.check_sast_constructs(probe["code"], probe["target_file"])
        assert bool(hits) is bool(probe["expected_detected"]), probe["probe_id"]
        fp_count += int(bool(hits))

    tristate_hits = 0
    for probe in suite["dast_poc_tristate"]:
        out = dast_cli.classify_poc_outcome(
            probe["exit_code"], probe["stdout"], probe["stderr"],
            probe["timed_out"], probe["memory_exceeded"],
        )
        assert out == probe["expected_outcome"], probe["probe_id"]
        for alt_err in probe.get("alt_stderrs", []):
            assert dast_cli.classify_poc_outcome(1, "", alt_err) == probe["expected_outcome"]
        tristate_hits += 1

    halt_hits = 0
    gaming_events = 0
    for probe in suite["deception_traps"]:
        res = ch_mod._detect_assertion_epistemic_conflict(probe["test_a"], probe["test_b"])
        assert res == probe["expected_resolution"], probe["probe_id"]
        halt_hits += int(res == "HALT_EPISTEMIC_CONFLICT")
        if res != "HALT_EPISTEMIC_CONFLICT":
            gaming_events += 1

    return {
        "evasion_recall": ev_hits / len(suite["sast_evasion"]),
        "fpr": fp_count / len(suite["sast_non_fp"]),
        "tristate_acc": tristate_hits / len(suite["dast_poc_tristate"]),
        "conflict_halt_rate": halt_hits / len(suite["deception_traps"]),
        "gaming_rate": gaming_events / len(suite["deception_traps"]),
    }


@pytest.mark.integration
def test_w2_tas_holdout_probes_part1_ast_dast_sbfl_oracle(tmp_path: Path) -> None:
    """1. Esegue sonde reali TAS-01..TAS-08 da tasks_tas_v2.json."""
    suite = _load_holdout_json("nk_tracking/oracle_holdout/tasks_tas_v2.json")
    assert suite["suite_id"] == "tasks_tas_v2" and suite["total_tasks"] == 16
    part1 = [t for t in suite["tasks"][:8]]
    for task in part1:
        _TAS_HANDLERS[task["check_type"]](tmp_path, task["expected"])
    assert len(part1) == 8


@pytest.mark.integration
def test_w2_tas_holdout_probes_part2_mutation_rsi_2pc_gov_common(tmp_path: Path) -> None:
    """2. Esegue sonde reali TAS-09..TAS-16 da tasks_tas_v2.json."""
    suite = _load_holdout_json("nk_tracking/oracle_holdout/tasks_tas_v2.json")
    part2 = [t for t in suite["tasks"][8:]]
    for task in part2:
        _TAS_HANDLERS[task["check_type"]](tmp_path, task["expected"])
    assert len(part2) == 8


@pytest.mark.fast
def test_w2_behavioral_holdout_sast_dast_deception_probes() -> None:
    """3. Verifica tutte le sonde reali di tas_behavioral_v2.json (SAST evasion/non-FP, DAST tri-state, Deception)."""
    suite = _load_holdout_json("nk_tracking/oracle_holdout/tas_behavioral_v2.json")
    assert suite["suite_id"] == "tas_behavioral_v2" and suite["version"] == "2.0.0-W2"
    metrics = _execute_behavioral_suite(suite)
    assert metrics["evasion_recall"] == 1.0
    assert metrics["fpr"] == 0.0
    assert metrics["tristate_acc"] == 1.0
    assert metrics["conflict_halt_rate"] == 1.0
    assert metrics["gaming_rate"] == 0.0


@pytest.mark.stress
def test_w2_deterministic_k3_holdout_evaluator(tmp_path: Path) -> None:
    """4. Valutatore deterministico k=3: pass@1 == 1.0, pass^3 == 1.0, FPR == 0.0, gaming_rate == 0.0."""
    tas_suite = _load_holdout_json("nk_tracking/oracle_holdout/tasks_tas_v2.json")
    beh_suite = _load_holdout_json("nk_tracking/oracle_holdout/tas_behavioral_v2.json")
    k_trials = 3
    task_trials: Dict[str, List[bool]] = {t["task_id"]: [] for t in tas_suite["tasks"]}
    beh_runs: List[Dict[str, float]] = []

    for trial_idx in range(k_trials):
        trial_ws = tmp_path / f"trial_{trial_idx}"
        trial_ws.mkdir(parents=True, exist_ok=True)
        for task in tas_suite["tasks"]:
            _TAS_HANDLERS[task["check_type"]](trial_ws, task["expected"])
            task_trials[task["task_id"]].append(True)
        beh_runs.append(_execute_behavioral_suite(beh_suite))

    pass_at_1 = sum(1 for outcomes in task_trials.values() if outcomes[0]) / len(task_trials)
    pass_pow_3 = sum(1 for outcomes in task_trials.values() if all(outcomes)) / len(task_trials)
    assert pass_at_1 == 1.0 and pass_pow_3 == 1.0
    assert all(r["fpr"] == 0.0 and r["gaming_rate"] == 0.0 for r in beh_runs)


def _assert_conftest_rmtree_and_tombstones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ro_dir = tmp_path / "ro_tree"
    (ro_dir / "nested").mkdir(parents=True, exist_ok=True)
    ro_file = ro_dir / "nested" / "locked.txt"
    ro_file.write_text("immutable", encoding="utf-8")
    os.chmod(ro_file, stat.S_IREAD)
    assert _conftest_mod.safe_rmtree(ro_dir) is True and not ro_dir.exists()
    assert _conftest_mod.safe_rmtree(tmp_path / "missing_dir") is True

    stg_list = tmp_path / "stg_list"
    stg_list.mkdir()
    (stg_list / ".deleted_files.json").write_text('["./scripts/old.py", "tests\\\\retired_dir"]', encoding="utf-8")
    assert _conftest_mod._load_staged_deleted_set(stg_list) == {"scripts/old.py", "tests/retired_dir"}
    stg_bad = tmp_path / "stg_bad"
    stg_bad.mkdir()
    (stg_bad / ".deleted_files.json").write_text("{corrupt", encoding="utf-8")
    assert _conftest_mod._load_staged_deleted_set(stg_bad) == set()
    monkeypatch.setattr(_conftest_mod, "_STAGED_DELETED_SET", {"tests/retired_dir"})
    assert _conftest_mod._is_path_in_staged_deleted("tests/retired_dir/x.py") is True
    resolved_tomb = _conftest_mod._resolve_staged_or_prod("tests/retired_dir/x.py")
    assert resolved_tomb.parent.name == "retired_dir" and ".staging" in resolved_tomb.parts


def _assert_conftest_fast_guard() -> None:
    fast_node = SimpleNamespace(get_closest_marker=lambda m: True if m == "fast" else None)
    both_node = SimpleNamespace(get_closest_marker=lambda m: True if m in ("fast", "integration") else None)
    fast_req = SimpleNamespace(config=SimpleNamespace(option=SimpleNamespace(markexpr="fast")), node=fast_node)
    not_fast_req = SimpleNamespace(config=SimpleNamespace(option=SimpleNamespace(markexpr="not fast")), node=fast_node)
    heavy_req = SimpleNamespace(config=SimpleNamespace(option=SimpleNamespace(markexpr="fast")), node=both_node)
    assert _conftest_mod._is_fast_guard_active(fast_req) is True
    assert _conftest_mod._is_fast_guard_active(not_fast_req) is False
    assert _conftest_mod._is_fast_guard_active(heavy_req) is False

    guard_fn = getattr(
        _conftest_mod._fast_guard_no_subprocess_or_sleep,
        "__wrapped__",
        _conftest_mod._fast_guard_no_subprocess_or_sleep,
    )
    with pytest.MonkeyPatch.context() as mp:
        gen = guard_fn(fast_req, mp)
        next(gen)
        assert subprocess.Popen is subprocess.run
        assert subprocess.call is subprocess.run
        with pytest.raises(pytest.fail.Exception, match="FAST-GUARD"):
            subprocess.run(["python", "--version"], shell=False)
        with pytest.raises(pytest.fail.Exception, match="FAST-GUARD"):
            subprocess.Popen(["python", "--version"], shell=False)
        with pytest.raises(pytest.fail.Exception, match="FAST-GUARD"):
            time.sleep(0.1)
        time.sleep(0.0)
        next(gen, None)


@pytest.mark.fast
def test_w2_conftest_safe_rmtree_tombstones_and_fast_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Verifica migliorie conftest.py: safe_rmtree sola lettura, tombstone .deleted_files.json e [FAST-GUARD]."""
    _assert_conftest_rmtree_and_tombstones(tmp_path, monkeypatch)
    _assert_conftest_fast_guard()


@pytest.mark.fast
def test_w2_qbm_ceilings_and_dom06_shard_contract(tmp_path: Path) -> None:
    """6. Verifica MAX_PYTEST_DURATION_CEIL=28.0, MAX_PYTEST_FAST_DURATION_CEIL=8.0 e DOM-06.json."""
    assert qbm_consts.MAX_PYTEST_DURATION_CEIL == 28.0
    assert qbm_consts.MAX_PYTEST_FAST_DURATION_CEIL == 8.0
    assert _qbm_mod.MAX_PYTEST_DURATION_CEIL == 28.0
    assert _qbm_mod.MAX_PYTEST_FAST_DURATION_CEIL == 8.0
    assert "MAX_PYTEST_FAST_DURATION_CEIL" in dir(_qbm_mod)

    ws = tmp_path / "shard_ws"
    (ws / "tests").mkdir(parents=True, exist_ok=True)
    (ws / "tests" / "test_sample.py").write_text("def test_s():\n    assert 1 == 1\n", encoding="utf-8")
    fake_idx = SimpleNamespace(stage_dir=ws / ".staging", workspace_root=ws)
    full_m = {"version": "2.0.0-W2", "domains": {}, "skills_index": {}, "scripts_index": {}, "intent_dispatch_table": {}}
    _, shards_out = shards_mod.build_shards_and_slim_manifest(fake_idx, full_m)
    dom06_raw = shards_out["DOM-06.json"]
    assert len(dom06_raw.encode("utf-8")) <= shards_mod.SHARD_MAX_BYTES
    artifacts = json.loads(dom06_raw)["artifacts"]
    assert artifacts["benchmark_tasks"] == "nk_tracking/oracle_holdout/tasks_tas_v2.json"
    assert artifacts["oracle_lock_holdout"] == "nk_tracking/oracle_lock_holdout.json"
    assert (artifacts["governance_lock"], artifacts["tensor_rsi_lock"]) == (
        "nk_tracking/governance_lock.json",
        "nk_tracking/tensor_rsi_lock.json",
    )


@pytest.mark.integration
def test_w2_triple_lock_freeze_verify_mirror_and_tamper_detection(tmp_path: Path) -> None:
    """7. Freeze/verify/tamper triple lock (oracle_lock, oracle_lock_holdout, governance_lock) su workspace isolato."""
    ws = tmp_path / "triple_lock_ws"
    _make_dast_holdout_repo(ws, with_locks=False)
    (ws / "nk_tracking" / "oracle_holdout" / "tasks_tas_v2.json").write_text('{"suite_id": "tasks_tas_v2"}', encoding="utf-8")

    o_lock = ws / "nk_tracking" / "oracle_lock.json"
    h_lock = ws / "nk_tracking" / "oracle_lock_holdout.json"
    g_lock = ws / "nk_tracking" / "governance_lock.json"

    for tgt, lk in ((ws / "tests", o_lock), (ws / "nk_tracking" / "oracle_holdout", h_lock), (ws / "scripts", g_lock)):
        res_f, rc_f = _ntt_mod.handle_oracle_lock("freeze", tgt, lk)
        assert rc_f == 0 and res_f["passed"] is True
        rc_cli = _ntt_mod.main(["oracle-lock", "verify", "--target", str(tgt), "--lock-file", str(lk), "--json"])
        assert rc_cli == 0

    with _dast_mod.ShadowSandbox() as sb:
        ov, del_f, _ = dast_ov.prepare_staging_overlay(ws, ws / ".staging", sb, "evaluator")
        rep = dast_hv.verify_sandbox_holdouts(ws, sb.sandbox_dir, "evaluator", ov, del_f)
        assert rep["passed"] is True
        assert set(["oracle_lock.json", "oracle_lock_holdout.json", "governance_lock.json"]).issubset(set(rep["checked_locks"]))

    (ws / "nk_tracking" / "oracle_holdout" / "tasks_tas_v2.json").write_text('{"tampered": true}', encoding="utf-8")
    res_ht, rc_ht = _ntt_mod.handle_oracle_lock("verify", ws / "nk_tracking" / "oracle_holdout", h_lock)
    assert rc_ht == 1 and res_ht["passed"] is False

    (ws / "scripts" / "app.py").write_text("VAL = 999\n", encoding="utf-8")
    res_gt, rc_gt = _ntt_mod.handle_oracle_lock("verify", ws / "scripts", g_lock)
    assert rc_gt == 1 and res_gt["passed"] is False

    (ws / "tests" / "t_ok.py").write_text("def test_one():\n    assert 2 == 2\n", encoding="utf-8")
    res_ot, rc_ot = _ntt_mod.handle_oracle_lock("verify", ws / "tests", o_lock)
    assert rc_ot == 1 and res_ot["passed"] is False

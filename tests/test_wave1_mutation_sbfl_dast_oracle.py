# -*- coding: utf-8 -*-
"""Burst test rapido W1 per coverage reale su mutation gate, SBFL, holdout e Oracle L3."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

try:
    from conftest import call_script_main, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main, load_nk_script_module

from _internal.builder_mutation_gate import mutant_gen as mg_mod, operators as op_mod, runner as mut_runner
from _internal.dast_sandbox_runner import holdout_verify as hv_mod, process_runner as pr_mod, staging_overlay as so_mod
from _internal.dast_sandbox_runner.sandbox_fs import ShadowSandbox
from _internal.nk_common.oracle_lock import compute_combined_sha256, compute_lf_sha256
from _internal.oracle_evaluator_l3 import evaluator_core as ev_mod, gate_validators as gv_mod, models_and_dom as dom_mod
from _internal.sbfl_pytest_bridge import bridge_core as sb_core, frame_extractor as fe_mod, pass_tracer as pt_mod, plugin_template as plg_mod, runner_and_cli as rc_mod
from _internal.sbfl_pytest_bridge.models import CoverageRecord, PytestRunSummary

_l3_cli_mod = load_nk_script_module("oracle_evaluator_l3")


def _find_first_node(tree: ast.AST, node_cls: type[ast.AST]) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, node_cls):
            return node
    raise AssertionError(f"Missing node {node_cls.__name__}")


def _drive_hookwrapper(gen_obj: Any, *, excinfo: Any = None) -> None:
    next(gen_obj)
    try:
        gen_obj.send(SimpleNamespace(excinfo=excinfo))
    except StopIteration:
        return


def _make_holdout_workspace(root: Path) -> None:
    for d in ("tests/evals", "nk_tracking/benchmark_suite", "nk_tracking/oracle_holdout", ".github/workflows", ".staging/scripts"):
        (root / d).mkdir(parents=True, exist_ok=True)
    test_f = root / "tests" / "t_ok.py"
    eval_f = root / "tests" / "evals" / "skill_golden_eval_set.json"
    gh_f = root / ".github" / "workflows" / "ci.yml"
    suite_f = root / "nk_tracking" / "benchmark_suite" / "tasks_alt.json"
    oh_f = root / "nk_tracking" / "oracle_holdout" / "holdout_v1.json"
    test_f.write_text("def test_one():\n    assert 1 == 1\n", encoding="utf-8")
    eval_f.write_text('{"cases": [1]}\n', encoding="utf-8")
    gh_f.write_text("name: ci\n", encoding="utf-8")
    suite_f.write_text('{"tasks": ["t1"]}\n', encoding="utf-8")
    oh_f.write_text('{"holdouts": [1]}\n', encoding="utf-8")
    (root / ".staging" / "scripts" / "extra_mod.py").write_text("X = 1\n", encoding="utf-8")

    o_files = {"t_ok.py": compute_lf_sha256(test_f), "evals/skill_golden_eval_set.json": compute_lf_sha256(eval_f), "../.github/workflows/ci.yml": compute_lf_sha256(gh_f)}
    h_files = {"nk_tracking/oracle_holdout/holdout_v1.json": compute_lf_sha256(oh_f)}
    g_files = {".github/workflows/ci.yml": compute_lf_sha256(gh_f)}
    for lk_name, t_dir, fmap in (("oracle_lock.json", root / "tests", o_files), ("oracle_lock_holdout.json", root, h_files), ("governance_lock.json", root, g_files)):
        (root / "nk_tracking" / lk_name).write_text(json.dumps({"target": t_dir.as_posix(), "files": fmap, "combined_sha256": compute_combined_sha256(fmap)}), encoding="utf-8")


def _assert_operator_exclusions_and_boundary() -> None:
    for expr in ('Path("a") / "x"', 'root_dir / "x"', 'p.joinpath("a") / "b"', '"abc" + s'):
        assert op_mod.match_operator_for_node(_find_first_node(ast.parse(expr), ast.BinOp), None) is None
    for stmt in ('s += "txt"', 'root_dir /= "sub"'):
        assert op_mod.match_operator_for_node(_find_first_node(ast.parse(stmt), ast.AugAssign), None) is None
    owned = op_mod.iter_owned_children(_find_first_node(ast.parse("x: int | str = 1"), ast.AnnAssign))
    assert (len(owned), isinstance(owned[1], ast.Constant)) == (2, True)
    assert (len(op_mod.iter_owned_children(_find_first_node(ast.parse("y: int"), ast.AnnAssign))), len(op_mod.iter_owned_children(_find_first_node(ast.parse("z = 1"), ast.Assign)))) == (1, 2)
    call_not = _find_first_node(ast.parse("fn(not ok)"), ast.Call)
    assert op_mod.apply_node_mutation(_find_first_node(call_not, ast.UnaryOp), "UnaryNotDrop", parent=call_not) == "ok"
    assert op_mod.match_operator_for_node(_find_first_node(ast.parse("-x"), ast.UnaryOp), None) is None
    cmp_n = _find_first_node(ast.parse("x < 5"), ast.Compare)
    assert (op_mod.is_boundary_context(cmp_n.comparators[0], cmp_n), op_mod.is_boundary_context(ast.Name("x"), cmp_n)) == (True, False)
    assert op_mod.is_ignored_scope_node(_find_first_node(ast.parse("def inner():\n    pass\n"), ast.FunctionDef)) is True
    assert op_mod.match_operator_for_node(_find_first_node(ast.parse("return None"), ast.Return), None) is None
    assert op_mod.replace_unary_not_child(None, ast.UnaryOp(op=ast.Not(), operand=ast.Name("x"))) == ""


@pytest.mark.fast
def test_w1_operators_and_exclusions() -> None:
    """Verifica gli 8 operatori AST, esclusioni Path/'x'/AnnAssign e scope annidati."""
    cases = [
        ("a == b", ast.Compare, None, "ComparisonFlip", "!="),
        ("a and b", ast.BoolOp, None, "BoolOpFlip", " or "),
        ("a + b", ast.BinOp, None, "BinOpFlip", " - "),
        ("x += 2", ast.AugAssign, None, "AugAssignFlip", "-="),
        ("return True", ast.Return, None, "BoolReturnFlip", "False"),
        ("return val", ast.Return, None, "ReturnNoneFlip", "None"),
    ]
    for code, cls, parent, exp_op, expected_sub in cases:
        node = _find_first_node(ast.parse(code), cls)
        assert op_mod.match_operator_for_node(node, parent) == exp_op
        assert expected_sub in op_mod.apply_node_mutation(node, exp_op, parent=parent)

    if_stmt = ast.parse("if not ok:\n    pass\n").body[0]
    unary = _find_first_node(if_stmt, ast.UnaryOp)
    assert (op_mod.match_operator_for_node(unary, if_stmt), op_mod.apply_node_mutation(unary, "UnaryNotDrop", parent=if_stmt)) == ("UnaryNotDrop", "ok")
    rng_call = _find_first_node(ast.parse("for i in range(0):\n    pass\n"), ast.Call)
    const_zero = rng_call.args[0]
    assert (op_mod.match_operator_for_node(const_zero, rng_call), op_mod.apply_node_mutation(const_zero, "BoundaryOffByOne", parent=rng_call)) == ("BoundaryOffByOne", "1")
    assert op_mod.apply_node_mutation(ast.parse("x + 1", mode="eval").body, "UnknownOp") == "x + 1"
    _assert_operator_exclusions_and_boundary()


def _assert_mutant_runner_verdicts(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mut_runner, "_run_pytest_fail_fast", lambda *_a, **_kw: (0, 0.01))
    vac = mut_runner.run_mutation_gate(ws, "scripts/m.py", ["tests/test_m.py"], stage_dir=ws / ".staging")
    assert (vac.status, vac.passed, vac.mutants_total) == ("PASS", True, 0)
    (ws / ".staging" / "scripts" / "m.py").write_text("def fn(x):\n    Path('a') / 'b'\n", encoding="utf-8")
    unm = mut_runner.run_mutation_gate(ws, "scripts/m.py", ["tests/test_m.py"], stage_dir=ws / ".staging")
    assert (unm.status, unm.passed, unm.mutants_total) == ("UNMEASURED", False, 0)
    (ws / ".staging" / "scripts" / "m.py").write_text("def fn(x):\n    a = x + 1\n    b = x * 2\n    if x > 0 and a > 0:\n        return b\n    return 0\n", encoding="utf-8")
    rcs = iter([0, 1, -1, 124, 2, 0])
    monkeypatch.setattr(mut_runner, "_run_pytest_fail_fast", lambda *_a, **_kw: (next(rcs, 0), 0.01))
    rep = mut_runner.run_mutation_gate(ws, ".staging/scripts/m.py", ["tests/test_m.py"], stage_dir=ws / ".staging", max_mutants=5)
    assert (rep.mutants_killed, rep.mutants_timed_out, rep.mutants_crashed) == (1, 2, 1)
    assert mut_runner.run_mutation_gate(ws, "scripts/nope.py", ["tests/test_m.py"]).passed is False
    (ws / ".staging" / "scripts" / "bad.py").write_text("def oops(:\n", encoding="utf-8")
    assert (mut_runner.run_mutation_gate(ws, "scripts/bad.py", ["tests/test_m.py"], stage_dir=ws / ".staging").passed, mut_runner._is_explicit_staged_target(ws, ws / ".staging", str(ws / ".staging" / "scripts" / "m.py"))) == (False, True)


@pytest.mark.integration
def test_w1_mutant_gen_and_runner_verdicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica diff AST differenziale, PASS non-applicabile, UNMEASURED, killed, timed_out e crashed."""
    pre = 'def fn(x):\n    """Doc vecchia."""\n    return x + 1\n'
    comment_only = '# nota\ndef fn(x):\n    """Doc nuova."""\n    return x + 1\n'
    changed = 'def fn(x: int | str):\n    p = Path("a") / "b"\n    if not x:\n        return False\n    x += 2\n    return x + len(str(p))\n'
    assert (mg_mod.has_executable_python_diff(pre, comment_only), mg_mod.has_executable_python_diff(pre, changed), mg_mod.has_executable_python_diff(pre, "def broken(:")) == (False, True, True)
    assert (mg_mod.generate_differential_mutants("a.py", pre, comment_only), mg_mod.generate_differential_mutants("a.py", pre, changed, max_mutants=0), mg_mod.generate_differential_mutants("a.py", pre, "def broken(:")) == ([], [], [])
    muts = mg_mod.generate_differential_mutants("a.py", pre, changed, max_mutants=8)
    assert muts and all("Path('a') *" not in m.mutated_source for m in muts)

    ws = tmp_path / "mut_ws"
    for d in ("scripts", "tests", ".staging/scripts"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    (ws / "scripts" / "m.py").write_text("def fn(x):\n    return x + 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "m.py").write_text("# comment\ndef fn(x):\n    return x + 1\n", encoding="utf-8")
    (ws / "tests" / "test_m.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _assert_mutant_runner_verdicts(ws, monkeypatch)


def _assert_sbfl_frame_and_hybrid_slices(tmp_path: Path, src_dir: Path) -> None:
    lines = ["tests/test_a.py::test_ok PASSED", "tests/test_a.py::test_err FAILED", "pkg/mod.py:3: AssertionError", "> assert step > 10", "E:  ValueError: bad step", "___ next ___"]
    err_t, err_m, ordered, counts, code_map = fe_mod._parse_traceback_diagnostics(lines, "mod.py")
    assert (err_t, "bad step" in err_m, counts[("pkg/mod.py", 3)], ordered) == ("ValueError", True, 1, [("pkg/mod.py", 3)])
    assert (fe_mod._lookup_frame_code(code_map, "pkg\\mod.py", 3).startswith("assert step"), fe_mod._lookup_passed_line_count({("pkg/mod.py", 3): 4}, "pkg\\mod.py", 3), fe_mod._read_source_line(None, tmp_path, "pkg/mod.py", 2)) == (True, 4, "step = val + 1")
    cands = [("pkg/mod.py", 3, 1.0), ("pkg/mod.py", 3, 0.9), ("pkg/bad_syn.py", 1, 0.8), ("pkg/missing.py", 9, 0.5), ("pkg/extra.py", 1, 0.2)]
    slices = fe_mod.build_hybrid_fl_slices(cands, [tmp_path], max_blocks=5, max_tokens=80)
    assert len(slices) == 3 and all(s["tokens"] <= 80 for s in slices)
    _ = src_dir


def _assert_sbfl_pep669_plugin_reset(tmp_path: Path) -> None:
    out_j, rec_j = tmp_path / "counts.json", tmp_path / "records.json"
    src = plg_mod._build_pass_cov_plugin_source(tmp_path.as_posix(), None, out_j.as_posix(), prefer_settrace=False, records_json_posix=rec_j.as_posix(), selected_nodeids=["tests/t.py::t1", "tests/t.py::t2"])
    assert ("_ACTIVE_LINES.clear()" in src, "restart_events" in src) == (True, True)
    plug_f = tmp_path / "nk_test_plug.py"
    plug_f.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("nk_test_plug_w1", str(plug_f))
    plug = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plug)

    restarts: List[int] = []
    plug._MON = SimpleNamespace(DISABLE="DISABLE", events=SimpleNamespace(LINE=1), get_tool=lambda _i: None, use_tool_id=lambda *_a: None, register_callback=lambda *_a: None, set_events=lambda *_a: None, restart_events=lambda: restarts.append(1), free_tool_id=lambda *_a: None)
    plug._DISABLE = "DISABLE"
    item1, item2 = SimpleNamespace(nodeid="tests/t.py::t1"), SimpleNamespace(nodeid="tests/t.py::t2")
    code_a = SimpleNamespace(co_filename=str(tmp_path / "pkg" / "mod.py"))
    _drive_hookwrapper(plug.pytest_runtest_setup(item1))
    plug._on_line_mon(code_a, 10)
    _drive_hookwrapper(plug.pytest_runtest_call(item1))
    _drive_hookwrapper(plug.pytest_runtest_teardown(item1))
    _drive_hookwrapper(plug.pytest_runtest_setup(item2))
    plug._on_line_mon(code_a, 20)
    _drive_hookwrapper(plug.pytest_runtest_call(item2))
    plug.pytest_sessionfinish(SimpleNamespace(), 0)

    recs_pt, cnts = pt_mod._parse_coverage_records_json(rec_j), pt_mod._parse_pass_counts_json(out_j)
    assert (len(restarts), len(recs_pt or []), recs_pt[0].executed_statements if recs_pt else [], recs_pt[1].executed_statements if recs_pt else []) == (2, 2, ["pkg/mod.py:10"], ["pkg/mod.py:20"])
    assert cnts is not None and (cnts[("pkg/mod.py", 10)], cnts[("pkg/mod.py", 20)]) == (1, 1)
    assert pt_mod._select_pytest_cli_targets([f"tests/test_{i}.py::test_fn_{'x' * 80}" for i in range(120)])[1] is not None


@pytest.mark.fast
def test_w1_sbfl_frames_plugin_hybrid_and_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """Verifica frame extractor, PEP 669 plugin reset, pass_tracer batching, bridge_core e CLI --hybrid-fl."""
    src_dir = tmp_path / "pkg"
    src_dir.mkdir(parents=True)
    (src_dir / "mod.py").write_text("def compute(val):\n    step = val + 1\n    assert step > 10, 'too_small " + ("tok " * 35) + "'\n    return step\n", encoding="utf-8")
    (src_dir / "bad_syn.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    _assert_sbfl_frame_and_hybrid_slices(tmp_path, src_dir)
    _assert_sbfl_pep669_plugin_reset(tmp_path)

    (src_dir / "svc.py").write_text("def f(x):\n    assert x > 0\n    return x\n", encoding="utf-8")
    bridge = sb_core.SBFLPytestBridge(cwd=tmp_path)
    summary = PytestRunSummary(
        total_tests=2, passed_count=1, failed_count=1, error_count=0, exit_code=1, duration_sec=0.05,
        failed_test_names=["tests/t.py::test_fail"], passed_test_names=["tests/t.py::test_ok"],
        raw_stdout="pkg/svc.py:2: AssertionError\n> assert x > 0\nE   AssertionError: bad\n",
    )
    recs = [
        CoverageRecord(test_id="t1", passed=True, executed_statements=["pkg/svc.py:1", "pkg/svc.py:3"]),
        CoverageRecord(test_id="t2", passed=False, executed_statements=["pkg/svc.py:1", "pkg/svc.py:2"]),
    ]
    loc = bridge.extract_failure_location(summary, target_file_hint="pkg/svc.py", coverage_records=recs)
    assert loc is not None and (loc.file_path, loc.line_number) == ("pkg/svc.py", 2)
    capsys.readouterr()
    monkeypatch.setattr(bridge, "run_and_diagnose", lambda **_kw: (summary, loc))
    assert rc_mod._emit_hybrid_bridge_result(summary, loc, bridge, as_json=True) == 1
    out_obj = json.loads(capsys.readouterr().out)
    assert len(out_obj["hybrid_slices"]) <= 3 and all(s["tokens"] <= 80 for s in out_obj["hybrid_slices"])
    assert rc_mod._emit_hybrid_matrix_cli(None, str(tmp_path)) == 0


def _assert_holdout_single_entry_and_missing(tmp_path: Path) -> None:
    sb_dir = tmp_path / "sb"
    (sb_dir / "tests").mkdir(parents=True)
    (sb_dir / "tests" / "a.py").write_text("A = 1\n", encoding="utf-8")
    sb_res = sb_dir.resolve()
    assert hv_mod._check_single_locked_entry(sb_dir, sb_res, "../../escape.py", "0" * 64, set(), set())[2] == ["escaped_lock_path:../../escape.py"]
    assert hv_mod._check_single_locked_entry(sb_dir, sb_res, "a.py", "0" * 64, set(), {"tests/a.py"})[2] == ["deleted_locked:tests/a.py"]
    assert hv_mod._check_single_locked_entry(sb_dir, sb_res, "a.py", "0" * 64, {"tests/a.py"}, set())[2] == ["overlaid_locked_holdout:tests/a.py"]
    assert hv_mod._check_single_locked_entry(sb_dir, sb_res, "miss.py", "0" * 64, set(), set())[2] == ["missing_locked:tests/miss.py"]
    assert hv_mod._check_single_locked_entry(sb_dir, sb_res, "a.py", "0" * 64, set(), set())[2] == ["modified_locked:tests/a.py"]
    assert hv_mod._check_overlay_and_tombstones({"tests/evals/x.json"}, ["tests/t_ok.py"])

    empty_sb = tmp_path / "empty_sb"
    empty_sb.mkdir()
    assert (len(hv_mod._check_required_holdout_assets(empty_sb)) >= 3, hv_mod._verify_sandbox_lock_entries(empty_sb, set(), set())[0]) == (True, 0)
    (empty_sb / "nk_tracking").mkdir()
    (empty_sb / "nk_tracking" / "oracle_lock.json").write_text("{bad", encoding="utf-8")
    assert hv_mod._verify_sandbox_lock_entries(empty_sb, set(), set())[3]
    (empty_sb / "nk_tracking" / "governance_lock.json").write_text('{"files": {}}', encoding="utf-8")
    assert hv_mod._verify_single_lock_manifest("governance_lock.json", tmp_path, empty_sb, set(), set())[4] is False
    (empty_sb / "nk_tracking" / "oracle_holdout").mkdir()
    (empty_sb / "nk_tracking" / "oracle_holdout" / "bad.json").write_text("{bad", encoding="utf-8")
    assert hv_mod._check_oracle_holdout_assets(tmp_path, empty_sb)


@pytest.mark.integration
def test_w1_holdout_verify_builder_and_locks(tmp_path: Path) -> None:
    """Verifica mirror .github/ evaluator, builder lock stripping, holdout/governance locks e fail-closed tamper."""
    root = tmp_path / "repo"
    _make_holdout_workspace(root)
    with ShadowSandbox() as sb:
        ov_files, del_files, _ = so_mod.prepare_staging_overlay(root, root / ".staging", sb, "evaluator")
        rep_ok = hv_mod.verify_sandbox_holdouts(root, sb.sandbox_dir, "evaluator", ov_files, del_files)
        assert (rep_ok["passed"], rep_ok["errors"], rep_ok["mismatches"], (sb.sandbox_dir / ".github" / "workflows" / "ci.yml").is_file()) == (True, [], [], True)
        assert hv_mod.verify_sandbox_holdouts(root, sb.sandbox_dir, "builder", ov_files, del_files)["passed"] is False

        (sb.sandbox_dir / "nk_tracking" / "oracle_lock_holdout.json").write_text("{bad_json", encoding="utf-8")
        rep_bad = hv_mod.verify_sandbox_holdouts(root, sb.sandbox_dir, "evaluator", ov_files, del_files)
        assert (rep_bad["passed"], any("corrotto" in e for e in rep_bad["errors"])) == (False, True)

        (root / "nk_tracking" / "governance_lock.json").write_text('{"target": ".", "files": {"x": "bad"}, "combined_sha256": "0"}', encoding="utf-8")
        (sb.sandbox_dir / "nk_tracking" / "governance_lock.json").write_text('{"target": ".", "files": {"x": "bad"}, "combined_sha256": "0"}', encoding="utf-8")
        rep_gov = hv_mod.verify_sandbox_holdouts(root, sb.sandbox_dir, "evaluator", ov_files, del_files)
        assert (rep_gov["passed"], bool(rep_gov["errors"])) == (False, True)

    bldr_root = tmp_path / "bldr_repo"
    _make_holdout_workspace(bldr_root)
    (bldr_root / "nk_tracking" / "tests_holdout_lock.json").write_text('{"files": {}}', encoding="utf-8")
    with ShadowSandbox() as sb_b:
        _, _, stripped = so_mod.prepare_staging_overlay(bldr_root, bldr_root / ".staging", sb_b, "builder")
        for lock_rel in ("nk_tracking/oracle_lock.json", "nk_tracking/oracle_lock_holdout.json", "nk_tracking/tests_holdout_lock.json", "nk_tracking/governance_lock.json"):
            assert (lock_rel in stripped, (sb_b.sandbox_dir / lock_rel).exists()) == (True, False)
    _assert_holdout_single_entry_and_missing(tmp_path)


def _assert_oracle_l3_path_confinement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, page: Path, ok_page: Path) -> None:
    for unc in (r"\\server\share\a.html", "//server/share/a.html", r"\\?\UNC\server\share\a.html", r"\\.\C:\a.html"):
        with pytest.raises(ValueError, match="UNC"):
            gv_mod.resolve_html_source(unc, allowed_roots=[tmp_path])
        with pytest.raises(ValueError, match="UNC"):
            gv_mod.resolve_expected_source(unc, allowed_roots=[tmp_path])
    monkeypatch.delenv("NK_ORACLE_ROOT", raising=False)
    assert gv_mod._INITIAL_SYSTEM_TEMP in gv_mod._resolve_allowed_oracle_roots()
    monkeypatch.setenv("NK_ORACLE_ROOT", str(tmp_path))
    assert (gv_mod._resolve_allowed_oracle_roots(), "Ok" in gv_mod._read_validated_html_file(str(page), allowed_roots=[tmp_path])) == ((tmp_path.resolve(),), True)
    with monkeypatch.context() as mp_rep:
        mp_rep.setattr(gv_mod, "_is_reparse_entry", lambda p: p == page)
        with pytest.raises(ValueError, match="symlink/junction"):
            gv_mod._enforce_confined_oracle_path(page, allowed_roots=[tmp_path])
    monkeypatch.setattr(gv_mod, "get_repo_snapshot_cache", None)
    assert "<p>Hi</p>" in gv_mod._read_oracle_text(ok_page)
    assert gv_mod._extract_candidate_file_str(r"C:\tmp\a.html:div:p") == r"C:\tmp\a.html"


def _assert_oracle_l3_validation_errors(tmp_path: Path) -> None:
    assert (gv_mod.resolve_expected_source('{"html": "<p>x</p>"}', allowed_roots=[tmp_path])[1], gv_mod.resolve_expected_source("- #main", allowed_roots=[tmp_path])[1]) == ("json", "md")
    for fn, bad in ((gv_mod._read_validated_html_file, ""), (gv_mod._read_validated_html_file, "../a.html"), (gv_mod._read_validated_html_file, "a.json"), (gv_mod._read_validated_expected_file, ""), (gv_mod._read_validated_expected_file, "../a.md"), (gv_mod._read_validated_expected_file, "a.env"), (gv_mod.resolve_expected_source, "secrets.env")):
        with pytest.raises(ValueError):
            fn(bad)
    with pytest.raises(FileNotFoundError):
        gv_mod._read_validated_expected_file(str(tmp_path / "miss.md"), allowed_roots=[tmp_path])
    assert (gv_mod._looks_like_disallowed_file_reference(""), gv_mod._looks_like_disallowed_file_reference("a\nb"), gv_mod._looks_like_disallowed_file_reference("<div>Ciao mondo</div>")) == (False, False, False)
    for bad_ref in (".env", "dir/file", "C:\\tmp\\file", "C:\\Windows\\win.ini", "../secret.html", "secret.env"):
        assert gv_mod._looks_like_disallowed_file_reference(bad_ref) is True
    for fn, arg in ((gv_mod._read_validated_html_file, "note.txt"), (gv_mod._read_validated_html_file, str(tmp_path / "missing.html")), (gv_mod._read_validated_expected_file, "secret.py"), (gv_mod._read_validated_expected_file, str(tmp_path / "missing.json")), (gv_mod.resolve_html_source, str(tmp_path / "nope.html"))):
        with pytest.raises((ValueError, FileNotFoundError)):
            fn(arg)


@pytest.mark.fast
def test_w1_oracle_l3_security_html5_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica Oracle L3 UNC/reparse/LFI/traversal, chiusura implicita HTML5, void elements e CLI."""
    page, ok_page = tmp_path / "page.html", tmp_path / "ok.html"
    page.write_text("<html><body><script>JS_SECRET=1</script><style>.k{color:red}</style><p>Ok</p></body></html>", encoding="utf-8")
    ok_page.write_text("<p>Hi</p>", encoding="utf-8")
    ev = ev_mod.DOMOracleEvaluator()
    full_txt = str(dom_mod._collect_dom_index(ev.parse_html(page.read_text(encoding="utf-8")))["full_text"])
    assert ("Ok" in full_txt, "JS_SECRET" in full_txt, "color:red" in full_txt) == (True, False, False)

    _assert_oracle_l3_path_confinement(tmp_path, monkeypatch, page, ok_page)
    _assert_oracle_l3_validation_errors(tmp_path)

    py_p = tmp_path / "evil.py"
    py_p.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        gv_mod.resolve_html_source(str(py_p))
    assert ("<p>Hi</p>" in gv_mod.resolve_html_source(str(ok_page)), "Ok" in gv_mod.resolve_html_source(str(page))) == (True, True)

    exp_html, act_html = tmp_path / "expected_imp.html", tmp_path / "actual_imp.html"
    exp_html.write_text("<main><p>Alpha</p><p>Beta</p><ul><li>One</li><li>Two</li></ul></main>", encoding="utf-8")
    act_html.write_text("<main><p>Alpha<p>Beta<ul><li>One<li>Two</ul></main>", encoding="utf-8")
    assert call_script_main(_l3_cli_mod, ["--expected-file", str(exp_html), "--actual-file", str(act_html), "--json"], monkeypatch) == 0

    rich_html = (
        "<ul><li>a<li>b</ul><dl><dt>k1<dt>k2<dd>v1<dd>v2</dl>"
        '<select><optgroup label="g1"><option>1<option>2<optgroup label="g2"><option>3</select>'
        "<table><thead><tr><th>h1<th>h2<tbody><tr><td>c1<td>c2<tfoot><tr><td>f1</table>"
        '<div><p>intro<h1>heading</h1><img id="logo" src="x"/></br></div>'
    )
    assert ev.evaluate_deltas(rich_html, rich_html).verdict == "PASS"


@pytest.mark.fast
def test_w1_trace_harness_no_basename_collision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica confinamento path esatto senza collisioni basename con other/mod.py."""
    sb = tmp_path / "sb"
    (sb / "scripts").mkdir(parents=True)
    (sb / "other").mkdir()
    (sb / "other" / "mod.py").write_text("VAL = 7\n", encoding="utf-8")
    (sb / "scripts" / "mod.py").write_text("from other.mod import VAL\nRES = VAL + 1\n", encoding="utf-8")
    cov_out, env = sb / "_nk_coverage_out.json", {}
    cmd = pr_mod.build_traced_command(sb, [sys.executable, "scripts/mod.py"], "scripts/mod.py", True, env, cov_out)
    assert "_NK_TRACE_TARGET_NAME" not in env and "_NK_TRACE_TARGET_PATH" in env and "_NK_TRACE_SANDBOX_ROOT" in env
    monkeypatch.syspath_prepend(str(sb))
    monkeypatch.setenv("_NK_TRACE_TARGET_PATH", env["_NK_TRACE_TARGET_PATH"])
    monkeypatch.setenv("_NK_TRACE_SANDBOX_ROOT", env["_NK_TRACE_SANDBOX_ROOT"])
    monkeypatch.setattr(sys, "argv", [cmd[2], str(cov_out), str(sb / "scripts" / "mod.py")])
    spec = importlib.util.spec_from_file_location("nk_harness_w1_test", cmd[2])
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    harness.main()
    assert "_NK_TRACE_TARGET_PATH" not in os.environ and "_NK_TRACE_SANDBOX_ROOT" not in os.environ
    items = json.loads(cov_out.read_text(encoding="utf-8"))
    assert items and {it["file_name"] for it in items} == {"scripts/mod.py"}

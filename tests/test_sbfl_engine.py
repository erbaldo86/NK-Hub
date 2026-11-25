# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per il motore SSOT SBFL Fault Localization (sbfl_pytest_bridge).
Modulo: tests/test_sbfl_engine.py.
Valida Ochiai, Tarantula, DStar, TriPass voting, modelli, bridge CLI e pass_tracer n_ep su Windows.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

bridge_mod = load_nk_script_module("sbfl_pytest_bridge")
runner_mod = load_nk_script_module("platform_runner")

from _internal.sbfl_pytest_bridge import (  # noqa: E402
    bridge_core as sbfl_core,
    models as sbfl_models,
    pass_tracer as sbfl_tracer,
)

CoverageMatrix = bridge_mod.CoverageMatrix
CoverageRecord = bridge_mod.CoverageRecord
OchiaiDiagnosticPayload = bridge_mod.OchiaiDiagnosticPayload
SBFLEngine = bridge_mod.SBFLEngine
SBFLLocation = bridge_mod.SBFLLocation
SpectrumCounts = bridge_mod.SpectrumCounts
calculate_dstar = bridge_mod.calculate_dstar
calculate_ochiai = bridge_mod.calculate_ochiai
calculate_tarantula = bridge_mod.calculate_tarantula
calibrate_coincidental_correctness = bridge_mod.calibrate_coincidental_correctness
tri_pass_voting_filter = bridge_mod.tri_pass_voting_filter


@pytest.mark.fast
def test_sbfl_core_matrix_math_and_tri_pass() -> None:
    """Valida precisione Ochiai/Tarantula/DStar, Def-Use, TriPass flaky removal e payload < 80 token."""
    records = [
        CoverageRecord(test_id="T1", passed=False, executed_statements=["s1", "s2"]),
        CoverageRecord(test_id="T2", passed=False, executed_statements=["s1"]),
        CoverageRecord(test_id="T3", passed=True, executed_statements=["s1", "s3"]),
        CoverageRecord(test_id="T4", passed=True, executed_statements=["s2", "s3"]),
        CoverageRecord(test_id="T5", passed=True, executed_statements=["s3"]),
    ]
    matrix = CoverageMatrix.from_records(records)
    spec_s1 = matrix.get_spectrum("s1")
    assert math.isclose(calculate_ochiai(spec_s1), 2.0 / math.sqrt(6.0), abs_tol=1e-6)
    assert math.isclose(calculate_tarantula(spec_s1), 0.75, abs_tol=1e-6)
    assert math.isclose(calculate_dstar(spec_s1, alpha=2.0), 4.0, abs_tol=1e-6)
    assert calculate_ochiai(matrix.get_spectrum("s3")) == 0.0

    spec = SpectrumCounts(n_ef=2, n_ep=1, n_nf=0, n_np=2)
    assert calibrate_coincidental_correctness(spec, def_use_weight=0.8, gamma=0.7) > calculate_ochiai(spec)
    assert (matrix.num_tests, matrix.num_statements, matrix.outcomes) == (5, 3, [1, 1, 0, 0, 0])

    p1 = [CoverageRecord(test_id="T_STABLE", passed=True, executed_statements=["s1"]), CoverageRecord(test_id="T_FLAKY", passed=True, executed_statements=["s2"])]
    p2 = [CoverageRecord(test_id="T_STABLE", passed=True, executed_statements=["s1"]), CoverageRecord(test_id="T_FLAKY", passed=False, executed_statements=["s2"])]
    p3 = [CoverageRecord(test_id="T_STABLE", passed=True, executed_statements=["s1"]), CoverageRecord(test_id="T_FLAKY", passed=True, executed_statements=["s2"])]
    res = tri_pass_voting_filter([p1, p2, p3])
    assert len(res.retained_records) == 1 and res.retained_records[0].test_id == "T_STABLE" and "T_FLAKY" in res.flaky_test_ids

    payload = OchiaiDiagnosticPayload(
        top_fault="core/engine.py:142", ochiai_score=0.9487, spectrum_tuple=(12, 1, 0, 85),
        top_candidates=[("core/engine.py:142", 0.9487)], flaky_filtered_count=0,
    )
    assert payload.estimate_token_count() < 80


@pytest.mark.fast
def test_sbfl_metrics_zero_edge_cases_and_matrix_validation() -> None:
    """Verifica casi limite zero su Ochiai/Tarantula/DStar ed errori CoverageMatrix."""
    assert bridge_mod.estimate_token_count("") == 0
    zero_fail = SpectrumCounts(n_ef=0, n_ep=2, n_nf=0, n_np=1)
    assert calculate_tarantula(zero_fail) == 0.0
    assert calculate_dstar(zero_fail) == 0.0
    assert calibrate_coincidental_correctness(zero_fail) == 0.0

    only_fail = SpectrumCounts(n_ef=2, n_ep=0, n_nf=0, n_np=0)
    assert calculate_tarantula(only_fail) == 1.0
    assert calculate_dstar(only_fail, alpha=2.0) == 4_000_000.0
    assert calculate_tarantula(SpectrumCounts(n_ef=0, n_ep=0, n_nf=1, n_np=1)) == 0.0
    assert calculate_tarantula(SpectrumCounts(n_ef=0, n_ep=0, n_nf=1, n_np=0)) == 0.0

    with pytest.raises(ValueError, match="Row mismatch"):
        CoverageMatrix(["s1"], ["T1"], [[1], [0]], [1])
    with pytest.raises(ValueError, match="Column mismatch"):
        CoverageMatrix(["s1", "s2"], ["T1"], [[1]], [1])
    with pytest.raises(ValueError, match="binary"):
        CoverageMatrix(["s1"], ["T1"], [[2]], [1])
    with pytest.raises(ValueError, match="Outcome"):
        CoverageMatrix(["s1"], ["T1"], [[1]], [2])

    empty_m = CoverageMatrix.from_records([])
    assert empty_m.statements == [] and empty_m.matrix == []
    with pytest.raises(KeyError):
        empty_m.get_spectrum("missing:1")


@pytest.mark.fast
def test_sbfl_empty_matrix_tie_break_tri_pass_and_cli(tmp_path: Path) -> None:
    """Verifica matrice vuota, tie-break Def-Use, tri-pass failure/empty e CLI SSOT."""
    from pydantic import ValidationError

    engine = SBFLEngine()
    empty_payload = engine.generate_diagnostic_payload([])
    assert empty_payload.top_fault == "NONE:0" and empty_payload.ochiai_score == 0.0

    recs = [
        CoverageRecord(test_id="F1", passed=False, executed_statements=["a:1", "b:2"]),
        CoverageRecord(test_id="P1", passed=True, executed_statements=["a:1", "b:2"]),
    ]
    ranked = engine.analyze(CoverageMatrix.from_records(recs), def_use_weights={"b:2": 0.9, "a:1": 0.0})
    assert ranked[0].statement == "b:2" and ranked[0].rank == 1 and ranked[1].rank == 2

    long_ranked = [
        bridge_mod.SBFLScore(
            statement=f"very_long_module_name_segment_{i}.py:{100 + i}",
            ochiai=0.9, tarantula=0.9, dstar=4.0, calibrated_ochiai=0.9,
            spectrum=SpectrumCounts(n_ef=1, n_ep=0, n_nf=0, n_np=0), rank=i + 1,
        )
        for i in range(6)
    ]
    assert len(engine.generate_diagnostic_payload(long_ranked, top_k=5).top_candidates) == 1
    with pytest.raises(ValidationError):
        engine.generate_diagnostic_payload(long_ranked, top_k=6)

    with pytest.raises(ValueError, match="3 run passes"):
        tri_pass_voting_filter([[]])
    fail_rec = [CoverageRecord(test_id="F_UNAN", passed=False, executed_statements=["x:9"])]
    tri_fail = tri_pass_voting_filter([fail_rec, fail_rec, fail_rec])
    assert len(tri_fail.retained_records) == 1 and tri_fail.retained_records[0].passed is False
    assert tri_pass_voting_filter([[], [], []]).deterministic_ratio == 1.0

    loc_long = SBFLLocation(
        file_path="sub/very_long_filename_beyond_thirty_chars.py", line_number=42, suspiciousness=0.95,
        error_type="CustomFailureTypeWithVeryLongName", error_message="E" * 120, failing_line_content="X" * 120,
    )
    assert len(loc_long.render_payload_json()) < 320
    unraised = SBFLEngine.extract_from_exception(RuntimeError("boom"))
    assert unraised.file_path == "unknown" and unraised.line_number == 1

    rec_file = tmp_path / "records.json"
    rec_file.write_text(json.dumps([{"test_id": "T1", "passed": False, "executed_statements": ["m.py:7"]}]), encoding="utf-8")
    rc_def, out_def, _ = call_script_main_captured(bridge_mod, ["--json"])
    assert rc_def == 0 and "module.py:10" in out_def
    rc_rf, out_rf, _ = call_script_main_captured(bridge_mod, ["--records-file", str(rec_file), "--json"])
    assert rc_rf == 0 and "m.py:7" in out_rf


@pytest.mark.fast
def test_sbfl_pytest_bridge_edge_branches_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica compute_ochiai, parse fallback, n_ep con passed_line_counts e CLI bridge."""
    assert bridge_mod.compute_ochiai(1, 0, 0) == 0.0
    assert bridge_mod.compute_ochiai(5, 2, 2) == round(2.0 / math.sqrt(8.0), 6)
    assert bridge_mod.compute_ochiai(0, 0, 2) == 0.0

    bridge = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    (tmp_path / "app_mod.py").write_text("x = 1\ny = 1 / 0\n", encoding="utf-8")
    summary_pass = bridge.parse_pytest_output("2 passed in 0.01s", "", exit_code=0, duration_sec=0.01)
    assert summary_pass.passed_count == 2 and summary_pass.error_count == 0 and bridge.extract_failure_location(summary_pass) is None

    summary_err = bridge.parse_pytest_output(
        "tests/test_app.py:5: AssertionError\napp_mod.py:2: ZeroDivisionError\nE   AssertionError\n", "", exit_code=1, duration_sec=0.02,
    )
    assert summary_err.error_count == 1
    loc_disk = bridge.extract_failure_location(summary_err, passed_line_counts={("app_mod.py", 2): 2})
    assert loc_disk is not None and loc_disk.failing_line_content == "y = 1 / 0" and loc_disk.n_ep == 2 and loc_disk.suspiciousness < 1.0

    loc_unk = bridge.extract_failure_location(bridge.parse_pytest_output("1 failed", "", exit_code=1))
    assert loc_unk is not None and loc_unk.file_path == "unknown.py"

    over_loc = bridge_mod.OchiaiBridgeLocation(
        file_path="very_long_file_name_for_truncation_check_here.py", line_number=99, suspiciousness=1.0,
        error_type="ExtremelyLongErrorTypeIdentifier" * 4, error_message="M" * 180, failing_line_content="C" * 180,
    )
    assert len(over_loc.render_payload_json()) < 320

    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", lambda **kw: (0, "1 passed in 0.01s", ""))
    rc_ok, out_ok, _ = call_script_main_captured(bridge_mod, ["--test-cmd", "pytest", "--json"])
    assert rc_ok == 0 and json.loads(out_ok)["status"] == "PASSED"
    rc_txt, out_txt, _ = call_script_main_captured(bridge_mod, ["--test-cmd", "pytest"])
    assert rc_txt == 0 and "PASSED" in out_txt

    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", lambda **kw: (1, "app_mod.py:2: ZeroDivisionError\nE   ZeroDivisionError: div0\n", ""))
    rc_fl, out_fl, _ = call_script_main_captured(bridge_mod, ["--test-cmd", "pytest", "--cwd", str(tmp_path), "--collect-pass-coverage", "--json"])
    assert rc_fl == 1 and json.loads(out_fl)["loc"].endswith(":2")


@pytest.mark.fast
def test_sbfl_windows_quiet_normcase_and_no_trace_cli(tmp_path: Path) -> None:
    """Verifica strip -q/--quiet + -v, normcase Win32 e assenza di trace -m pytest."""
    stripped_str = sbfl_core._strip_quiet_and_add_verbose("pytest -q --quiet tests/test_a.py")
    parts = stripped_str.split()
    assert ("-q" in parts, "--quiet" in parts, stripped_str.endswith("-v")) == (False, False, True)
    assert sbfl_core._strip_quiet_and_add_verbose(["pytest", "--quiet", "-q", "-v"]) == ["pytest", "-v"]
    assert sbfl_core._lookup_passed_line_count({("Sub\\App_Mod.py", 4): 3}, "sub/app_mod.py", 4) == 3
    assert sbfl_core._matches_target_hint("PKG/Calc_Unit.py", "calc_unit.py") is True

    plugin_src = sbfl_tracer._build_pass_cov_plugin_source("C:/ws", "calc_unit.py", "C:/ws/out.json", prefer_settrace=True)
    assert ("_PREFER_SETTRACE = True" in plugin_src, "sys.settrace(_on_line_trace)" in plugin_src) == (True, True)

    recorded_cmds: List[List[str]] = []
    sbfl_tracer._collect_passed_lines_trace_fallback(
        ["test_calc_unit.py::test_add_one"], tmp_path, tmp_path,
        lambda **kw: recorded_cmds.append(list(kw["cmd"])) or (0, "", ""), "calc_unit", 5.0,
    )
    assert (len(recorded_cmds), "trace" in recorded_cmds[0], "nk_pass_cov_plugin" in recorded_cmds[0]) == (1, False, True)


@pytest.mark.integration
def test_sbfl_pass_tracer_real_n_ep_and_windows_fixes(tmp_path: Path) -> None:
    """Verifica subprocess reale pass_tracer n_ep > 0 su Windows sotto 2.0s."""
    (tmp_path / "calc_unit.py").write_text(
        "def add_nums(a: int, b: int) -> int:\n    res = a + b\n    if a < 0:\n        return res + 99\n    return res\n",
        encoding="utf-8",
    )
    (tmp_path / "test_calc_unit.py").write_text(
        "from calc_unit import add_nums\n\ndef test_add_one():\n    assert add_nums(2, 3) == 5\n\ndef test_add_two():\n    assert add_nums(4, 1) == 5\n",
        encoding="utf-8",
    )
    t0 = time.perf_counter()
    counts: Dict[tuple[str, int], int] = sbfl_tracer.collect_passed_lines_batched(
        passed_test_names=["test_calc_unit.py::test_add_one", "test_calc_unit.py::test_add_two"],
        exec_root=tmp_path, run_fn=runner_mod.safe_subprocess_run, target_file_hint="CALC_UNIT.py", timeout_sec=10.0,
    ) or {}
    elapsed = time.perf_counter() - t0
    assert counts.get(("calc_unit.py", 2), 0) >= 2 and counts.get(("calc_unit.py", 4), 0) == 0 and elapsed < 5.0
    assert sbfl_core.compute_ochiai(n_ef=1, n_ep=0, total_failed=1) == 1.0
    assert 0.0 < sbfl_core.compute_ochiai(n_ef=1, n_ep=counts[("calc_unit.py", 2)], total_failed=1) < 1.0


def _assert_sbfl_cli_token_and_mirror(tmp_path: Path, sbfl_cli: Any) -> None:
    assert sbfl_cli._is_pytest_command("pytest -q") is True
    assert sbfl_cli._is_pytest_command("python -m pytest tests") is True
    assert sbfl_cli._is_pytest_command("python tool.py") is False
    toks = sbfl_cli._split_tokens_keep_quotes('"C:/my dir/python.exe" -m pytest \'tests/my test.py\'')
    assert (toks[0], toks[-1]) == ('"C:/my dir/python.exe"', "'tests/my test.py'")
    assert sbfl_cli._strip_quiet_and_add_verbose("pytest -v -q tests/a.py") == "pytest -v tests/a.py"
    assert sbfl_cli._strip_quiet_and_add_verbose(["pytest", "-q", "tests/a.py"]) == ["pytest", "tests/a.py", "-v"]
    bt_dir = tmp_path / "bt"
    already_str = f"pytest -p no:cacheprovider --basetemp={bt_dir.as_posix()}"
    assert sbfl_cli._append_pytest_iso_flags(already_str, bt_dir) == already_str
    assert "no:cacheprovider" in sbfl_cli._append_pytest_iso_flags(["pytest", "tests/a.py"], bt_dir)
    assert sbfl_cli._append_pytest_iso_flags(["pytest", "-p", "no:cacheprovider", f"--basetemp={bt_dir.as_posix()}"], bt_dir)[-1].startswith("--basetemp=")
    src_root, mir_dir = tmp_path / "src_ws", tmp_path / "mir_ws"
    assert mir_dir.as_posix() in sbfl_cli._rewrite_cmd_for_mirror(f"pytest {src_root.as_posix()}/tests/t.py", src_root, mir_dir)
    assert mir_dir.as_posix() in sbfl_cli._rewrite_cmd_for_mirror(["pytest", str(src_root / "tests" / "t.py")], src_root, mir_dir)[1]
    assert sbfl_cli._normalize_mirror_output("", mir_dir) == ""
    assert sbfl_cli._normalize_mirror_output(f"{mir_dir.as_posix()}/a.py:1\n{str(mir_dir)}\\b.py:2", mir_dir) == "a.py:1\nb.py:2"


@pytest.mark.fast
def test_sbfl_runner_cli_text_report_and_facade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita runner_and_cli.py su quotes/iso/mirror, text output CLI, flag invalidi e facciata."""
    from _internal.sbfl_pytest_bridge import runner_and_cli as sbfl_cli

    _assert_sbfl_cli_token_and_mirror(tmp_path, sbfl_cli)
    (tmp_path / "app_x.py").write_bytes(b"def f():\n    return 1 / 0\n")
    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", lambda **kw: (1, "app_x.py:2: ZeroDivisionError\n> return 1 / 0\nE   ZeroDivisionError: div0\n", ""))
    rc_txt, out_txt, _ = call_script_main_captured(bridge_mod, ["--test-cmd", "pytest", "--cwd", str(tmp_path)])
    assert (rc_txt, "[SBFL-OCHIAI]" in out_txt, "Code:" in out_txt, "Compact Payload:" in out_txt) == (1, True, True, True)
    assert call_script_main_captured(bridge_mod, ["--unknown-sbfl-flag"])[0] == 2
    with pytest.raises(FileNotFoundError):
        call_script_main_captured(bridge_mod, ["--records-file", str(tmp_path / "missing_rec.json")])
    assert "SBFLPytestBridge" in dir(bridge_mod) and bridge_mod._build_cli_parser() is not None
    with pytest.raises(AttributeError):
        getattr(bridge_mod, "NONEXISTENT_SBFL_ATTR")


def _assert_sbfl_models_metrics_and_strict() -> None:
    from pydantic import ValidationError

    zero_all = SpectrumCounts(n_ef=0, n_ep=0, n_nf=0, n_np=0)
    assert (zero_all.total_tests, zero_all.total_executed) == (0, 0)
    assert (calculate_ochiai(zero_all), calculate_tarantula(zero_all), calculate_dstar(zero_all), calibrate_coincidental_correctness(zero_all)) == (0.0, 0.0, 0.0, 0.0)
    no_pass = SpectrumCounts(n_ef=2, n_ep=0, n_nf=1, n_np=0)
    assert (calculate_tarantula(no_pass), calculate_dstar(no_pass, alpha=3.0)) == (1.0, 8.0)
    assert calibrate_coincidental_correctness(SpectrumCounts(n_ef=1, n_ep=2, n_nf=0, n_np=1), def_use_weight=2.0, gamma=2.0) == 1.0
    assert bridge_mod.compute_ochiai(10, 0, 2) == 1.0
    for ctor in (
        lambda: SpectrumCounts(n_ef="1", n_ep=0, n_nf=0, n_np=0),  # type: ignore[arg-type]
        lambda: SpectrumCounts(n_ef=1, n_ep=0, n_nf=0, n_np=0, extra_field=1),  # type: ignore[call-arg]
        lambda: CoverageRecord(test_id="T", passed="yes"),  # type: ignore[arg-type]
        lambda: SBFLLocation(file_path="a.py", line_number=0, suspiciousness=0.5, error_type="E", error_message="m", failing_line_content="c"),
        lambda: bridge_mod.PytestRunSummary(total_tests=1, passed_count=1, failed_count=0, error_count=0, exit_code=0, duration_sec=-0.1),
    ):
        with pytest.raises(ValidationError):
            ctor()


def _assert_sbfl_monitoring_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert sbfl_models._sbfl_sys() is not None and callable(sbfl_models._sbfl_conflict_fn())
    assert isinstance(sbfl_models._has_active_monitoring_tool(sbfl_models.sys.monitoring), bool)
    ran_conflict: List[int] = []
    monkeypatch.setattr(bridge_mod, "is_monitoring_conflict_active", lambda: True)
    assert sbfl_models.collect_statements_with_monitoring(lambda: ran_conflict.append(1)) == (False, set())
    assert ran_conflict == [1]

    def _traced_sample() -> int:
        val = 10
        return val + 5

    monkeypatch.setattr(bridge_mod, "is_monitoring_conflict_active", lambda: False)
    ok_mon, traced_lines = sbfl_models.collect_statements_with_monitoring(_traced_sample, target_filename_filter="test_sbfl_engine.py")
    assert ok_mon is True and any("test_sbfl_engine.py:" in item for item in traced_lines)
    assert sbfl_models.collect_statements_with_monitoring(_traced_sample, target_filename_filter="no_such_module_xyz.py") == (True, set())

    def _fake_get_tool(tid: int) -> Any:
        if tid == 3:
            raise ValueError("bad")
        return None if tid == 4 else "busy"

    callbacks: List[Any] = []
    fake_mon = SimpleNamespace(
        events=SimpleNamespace(LINE=1),
        get_tool=_fake_get_tool,
        use_tool_id=lambda _tid, _name: None,
        register_callback=lambda _tid, _ev, cb: callbacks.append(cb),
        set_events=lambda _tid, _ev: None,
        free_tool_id=lambda _tid: (_ for _ in ()).throw(ValueError("free_err")),
    )
    monkeypatch.setattr(bridge_mod, "sys", SimpleNamespace(monitoring=fake_mon))
    ran_f, exec_f = sbfl_models.collect_statements_with_monitoring(
        lambda: (callbacks[0](SimpleNamespace(co_filename=str(tmp_path / "skip.py")), 5), callbacks[0](SimpleNamespace(co_filename=str(tmp_path / "target_mod.py")), 0), callbacks[0](SimpleNamespace(co_filename=str(tmp_path / "target_mod.py")), 12)),
        target_filename_filter="target_mod.py",
    )
    assert (ran_f, any(line.endswith("target_mod.py:12") for line in exec_f)) == (True, True)


@pytest.mark.fast
def test_sbfl_models_strict_overflow_and_monitoring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita metriche zero/clamp, Pydantic strict, overflow payload e rami sys.monitoring in models.py."""
    _assert_sbfl_models_metrics_and_strict()
    _assert_sbfl_monitoring_branches(tmp_path, monkeypatch)

    loc_huge = SBFLLocation(file_path="sub/mod.py", line_number=12, suspiciousness=0.9, error_type="-".join(["Err"] * 45), error_message="detail " * 20, failing_line_content="x = compute() " * 10)
    rendered_loc = json.loads(loc_huge.render_payload_json())
    assert len(rendered_loc["ctx"]) <= 20 and len(rendered_loc["err"]) <= 30
    bridge_huge = bridge_mod.OchiaiBridgeLocation(file_path="sub/mod.py", line_number=12, suspiciousness=0.9, error_type="VeryLongExceptionTypeName" * 12, error_message="detail " * 20, failing_line_content="x = compute() " * 10)
    assert len(bridge_huge.render_payload_json()) < 320

    assert sbfl_models._has_active_monitoring_tool(SimpleNamespace(get_tool=lambda _i: (_ for _ in ()).throw(ValueError("err")))) is False
    monkeypatch.setattr(bridge_mod, "sys", SimpleNamespace(monitoring=None, modules={}))
    assert sbfl_models.collect_statements_with_monitoring(lambda: None) == (False, set())
    monkeypatch.setattr(bridge_mod, "sys", SimpleNamespace(monitoring=SimpleNamespace(get_tool=lambda _i: "busy")))
    assert sbfl_models.collect_statements_with_monitoring(lambda: None) == (False, set())
    monkeypatch.delattr(bridge_mod, "is_monitoring_conflict_active", raising=False)
    monkeypatch.setenv("COV_CORE_SOURCE", "1")
    assert sbfl_models.is_monitoring_conflict_active() is True


def _assert_sbfl_parse_and_mirror_fs(tmp_path: Path) -> Path:
    from _internal.nk_common.isolated_test_runner import safe_rmtree

    assert sbfl_core._lookup_passed_line_count({("mod.py", 7): 4}, "pkg/mod.py", 7) == 4
    assert sbfl_core._lookup_passed_line_count({("A\\MOD.PY", 3): 1, ("B\\MOD.PY", 7): 6}, "c/mod.py", 7) == 6
    assert sbfl_core._lookup_passed_line_count({("other.py", 7): 2}, "missing.py", 7) == 0

    bridge = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    assert bridge.collect_passed_line_counts([]) == {}
    (tmp_path / "dir_as_file.py").mkdir()
    dup_out = "tests/t.py::test_ok PASSED\ntests/t.py::test_ok PASSED\ntests/t.py::test_err FAILED\ntests/t.py::test_err FAILED\ndir_as_file.py:99: AssertionError\nE   AssertionError\n"
    summary = bridge.parse_pytest_output(dup_out, "", exit_code=1, duration_sec=0.02)
    assert (summary.passed_count, summary.failed_count) == (1, 1)
    loc_dir = bridge.extract_failure_location(summary)
    assert loc_dir is not None and (loc_dir.error_type, loc_dir.failing_line_content) == ("AssertionError", "")
    (tmp_path / "short.py").write_bytes(b"x = 1\n")
    loc_short = bridge.extract_failure_location(bridge.parse_pytest_output("short.py:99: ValueError\nE   ValueError: out\n", "", exit_code=1))
    assert loc_short is not None and loc_short.failing_line_content == ""

    mini_ws = tmp_path / "mini_mirror_ws"
    (mini_ws / ".staging").mkdir(parents=True)
    (mini_ws / "root_mod.py").write_bytes(b"X = 1\n")
    (mini_ws / ".staging" / "staged_mod.py").write_bytes(b"Y = 2\n")
    mir_dir, bt_dir = sbfl_core._create_nvme_mirror(mini_ws)
    try:
        assert ((mir_dir / "root_mod.py").is_file(), (mir_dir / "staged_mod.py").is_file(), bt_dir.is_dir()) == (True, True, True)
    finally:
        safe_rmtree(mir_dir.parent)
    return mini_ws


def _assert_sbfl_matrix_and_pass_json(tmp_path: Path) -> None:
    from _internal.sbfl_pytest_bridge import matrix_engine as sbfl_mat

    mat = sbfl_mat.CoverageMatrix.from_records([CoverageRecord(test_id="T1", passed=True, executed_statements=["s1"])])
    assert mat.test_ids == ["T1"]
    try:
        _ = 1 / 0
    except ZeroDivisionError as exc:
        exc_loc = SBFLEngine.extract_from_exception(exc, relevant_file_hint="test_sbfl_engine.py")
        assert (exc_loc.error_type, "test_sbfl_engine.py" in exc_loc.file_path) == ("ZeroDivisionError", True)

    assert sbfl_tracer._parse_pass_counts_json(tmp_path / "nope.json") is None
    bad_json, list_json, mixed_json = tmp_path / "bad.json", tmp_path / "list.json", tmp_path / "mixed.json"
    bad_json.write_bytes(b"{bad")
    list_json.write_bytes(b"[1, 2]")
    mixed_json.write_text(json.dumps({"bad_key": 1, "pkg/m.py::bad": 1, "pkg/m.py::0": 2, "pkg/m.py::3": 0, "pkg/m.py::5": 4}), encoding="utf-8")
    assert (sbfl_tracer._parse_pass_counts_json(bad_json), sbfl_tracer._parse_pass_counts_json(list_json)) == (None, None)
    assert sbfl_tracer._parse_pass_counts_json(mixed_json) == {("pkg/m.py", 5): 4, ("m.py", 5): 4}
    assert (sbfl_tracer._format_hint_filename(None), sbfl_tracer._format_hint_filename("calc"), sbfl_tracer._format_hint_filename("calc.py")) == (None, "calc.py", "calc.py")


@pytest.mark.fast
def test_sbfl_bridge_core_mirror_pass_coverage_and_matrix_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita bridge_core su lookup Win32, mirror NVMe, pass coverage, matrix_engine e pass_tracer JSON."""
    mini_ws = _assert_sbfl_parse_and_mirror_fs(tmp_path)

    monkeypatch.setattr(sbfl_core, "is_temp_workspace", lambda _p: False)
    monkeypatch.setattr(bridge_mod, "is_monitoring_conflict_active", lambda: False)
    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", lambda **kw: (1, "t.py::test_ok PASSED\nt.py::test_bad FAILED\nroot_mod.py:1: RuntimeError\nE   RuntimeError: fail\n", ""))
    diag_sum, diag_loc = bridge_mod.SBFLPytestBridge(cwd=mini_ws).run_and_diagnose("pytest -q", target_file_hint="root_mod.py", collect_pass_coverage=True)
    assert diag_sum.exit_code == 1 and diag_loc is not None and diag_loc.line_number == 1

    plain_sum, plain_loc = bridge_mod.SBFLPytestBridge(cwd=mini_ws).run_and_diagnose("python plain_tool.py", collect_pass_coverage=False)
    assert plain_sum.exit_code == 1 and plain_loc is not None

    def _plugin_subproc(cmd: List[str], env: dict[str, str], **_k: Any) -> tuple[int, str, str]:
        _ = cmd
        plugin_dir = Path(env["PYTHONPATH"].split(os.pathsep)[0])
        (plugin_dir / "pass_line_counts.json").write_text(json.dumps({"target_mod.py::2": 1}), encoding="utf-8")
        return 0, "", ""

    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", _plugin_subproc)
    assert bridge_mod.SBFLPytestBridge(cwd=tmp_path).collect_passed_line_counts(["tests/test_a.py::test_1"], target_file_hint="target_mod.py") == {("target_mod.py", 2): 1}
    _assert_sbfl_matrix_and_pass_json(tmp_path)

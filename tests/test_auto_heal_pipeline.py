#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Auto-Heal Pipeline di Nexus Keystone Generation.
Modulo: tests/test_auto_heal_pipeline.py.
Valida GT-07, snapshot SHA-256, 2-Strike circuit breaker, SyntaxError unblock, trim token e mutation gate.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

sbfl_pytest_bridge = load_nk_script_module("sbfl_pytest_bridge")
healing_snapshot_rollback = load_nk_script_module("healing_snapshot_rollback")
auto_heal_pipeline = load_nk_script_module("auto_heal_pipeline")
mut_mod = load_nk_script_module("builder_mutation_gate")

SBFLPytestBridge = sbfl_pytest_bridge.SBFLPytestBridge
PytestRunSummary = sbfl_pytest_bridge.PytestRunSummary
OchiaiBridgeLocation = sbfl_pytest_bridge.OchiaiBridgeLocation

HealingSnapshotManager = healing_snapshot_rollback.HealingSnapshotManager
FitnessVerdict = healing_snapshot_rollback.FitnessVerdict

AutoHealPipeline = auto_heal_pipeline.AutoHealPipeline
AutoHealSessionReport = auto_heal_pipeline.AutoHealSessionReport

from _internal.builder_mutation_gate import mutant_gen as mg_mod, runner as mut_runner  # noqa: E402
from _internal.healing_snapshot_rollback import manager_and_cli as hsr_cli, models_and_io as hsr_models  # noqa: E402

FileSnapshot = hsr_models.FileSnapshot


class _InProcessPytestBridge(SBFLPytestBridge):
    """Bridge deterministico in-process per eseguire i file di test reali senza overhead di avvio."""

    def __init__(self, cwd: Path, test_file: Path, target_file: Path) -> None:
        super().__init__(cwd=cwd)
        self.test_file = test_file
        self.target_file = target_file

    def run_and_diagnose(
        self, test_cmd: Sequence[str] | str, target_file_hint: Optional[str] = None, timeout_sec: float = 60.0,
    ) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        """Esegue realmente i moduli target e test in-process e formatta l'output Pytest."""
        _ = (test_cmd, timeout_sec)
        t0 = time.perf_counter()
        stdout_lines, failures, failed_cnt = [], [], 0
        added_cwd = str(self.cwd) not in sys.path
        if added_cwd:
            sys.path.insert(0, str(self.cwd))

        try:
            t_name = self.target_file.stem
            sys.modules.pop(t_name, None)
            t_spec = importlib.util.spec_from_file_location(t_name, str(self.target_file))
            t_mod = importlib.util.module_from_spec(t_spec)
            sys.modules[t_name] = t_mod
            t_spec.loader.exec_module(t_mod)

            s_name = f"{self.test_file.stem}_{int(time.perf_counter() * 1000000)}"
            s_spec = importlib.util.spec_from_file_location(s_name, str(self.test_file))
            s_mod = importlib.util.module_from_spec(s_spec)
            s_spec.loader.exec_module(s_mod)

            for attr_name in sorted(dir(s_mod)):
                if not attr_name.startswith("test_") or not callable(getattr(s_mod, attr_name)):
                    continue
                node_id = f"{self.test_file.name}::{attr_name}"
                try:
                    getattr(s_mod, attr_name)()
                    stdout_lines.append(f"{node_id} PASSED")
                except Exception as exc:
                    stdout_lines.append(f"{node_id} FAILED")
                    failed_cnt += 1
                    tb_entries = traceback.extract_tb(exc.__traceback__)
                    target_line = next((e.lineno for e in reversed(tb_entries) if Path(e.filename).name == self.target_file.name), 1)
                    err_cls = type(exc).__name__
                    failures.append(f"___ {attr_name} ___\n{self.target_file.as_posix()}:{target_line}: {err_cls}\nE   {err_cls}: {exc}")
        except Exception as exc:
            failed_cnt += 1
            err_cls = type(exc).__name__
            stdout_lines.append(f"{self.test_file.name}::test_syntax FAILED")
            failures.append(f"{self.target_file.as_posix()}:1: {err_cls}\nE   {err_cls}: {exc}")
        finally:
            if added_cwd and str(self.cwd) in sys.path:
                sys.path.remove(str(self.cwd))

        if failures:
            stdout_lines.append("=================================== FAILURES ===================================")
            stdout_lines.extend(failures)
        summary = self.parse_pytest_output("\n".join(stdout_lines) + "\n", "", 0 if failed_cnt == 0 else 1, time.perf_counter() - t0)
        return summary, self.extract_failure_location(summary, target_file_hint=target_file_hint or str(self.target_file))


class _InProcessDiagnoseBridge(_InProcessPytestBridge):
    def run_and_diagnose(self, test_cmd: Sequence[str] | str, target_file_hint: Optional[str] = None, timeout_sec: float = 60.0, collect_pass_coverage: bool = False) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        _ = collect_pass_coverage
        return super().run_and_diagnose(test_cmd=test_cmd, target_file_hint=target_file_hint, timeout_sec=timeout_sec)


class _DiffFileDiagnoseBridge(_InProcessDiagnoseBridge):
    def __init__(self, cwd: Path, test_file: Path, target_file: Path, reported_rel: str) -> None:
        super().__init__(cwd, test_file, target_file)
        self.reported_rel = reported_rel

    def run_and_diagnose(self, test_cmd: Sequence[str] | str, target_file_hint: Optional[str] = None, timeout_sec: float = 60.0, collect_pass_coverage: bool = False) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        summary, loc = super().run_and_diagnose(test_cmd=test_cmd, target_file_hint=target_file_hint, timeout_sec=timeout_sec, collect_pass_coverage=collect_pass_coverage)
        if loc is not None:
            loc = OchiaiBridgeLocation(file_path=self.reported_rel, line_number=2, suspiciousness=loc.suspiciousness, error_type=loc.error_type, error_message=loc.error_message, failing_line_content=loc.failing_line_content, total_failed_tests=loc.total_failed_tests, n_ef=loc.n_ef, n_ep=loc.n_ep)
        return summary, loc


class _AutoDiscoverInProcessBridge(SBFLPytestBridge):
    def _pick_target_and_test(self, target_file_hint: Optional[str]) -> Tuple[Optional[Path], Optional[Path]]:
        stg_dir, target = self.cwd / ".staging", None
        if target_file_hint:
            cand = Path(target_file_hint) if Path(target_file_hint).is_absolute() else self.cwd / target_file_hint
            if cand.exists():
                target = cand
        if target is None and stg_dir.is_dir():
            py_files = sorted(p for p in stg_dir.rglob("*.py") if "__pycache__" not in p.parts)
            target = py_files[0] if py_files else None
        if target is None:
            return None, None
        test_file = next((p for p in (target.parent / f"test_{target.stem}.py", self.cwd / f"test_{target.stem}.py", self.cwd / "tests" / f"test_{target.stem}.py") if p.is_file()), None)
        return target, test_file

    def run_and_diagnose(self, test_cmd: Sequence[str] | str, target_file_hint: Optional[str] = None, timeout_sec: float = 60.0, collect_pass_coverage: bool = False) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        _ = (test_cmd, timeout_sec, collect_pass_coverage)
        target, test_file = self._pick_target_and_test(target_file_hint)
        if target is None or test_file is None:
            return self.parse_pytest_output("1 passed in 0.01s\n", "", 0, 0.01), None
        exec_cwd = test_file.parent if target.parent == test_file.parent else self.cwd
        return _InProcessPytestBridge(exec_cwd, test_file, target).run_and_diagnose("pytest", target_file_hint=str(target))


@pytest.mark.integration
def test_sbfl_bridge_parsing_frequency_and_ochiai(tmp_path: Path) -> None:
    """Verifica parsing Pytest, punteggio Ochiai, payload < 320 char e frequenza massima SBFL."""
    bridge = SBFLPytestBridge(cwd=tmp_path)
    sample_stdout = (
        "tests/test_math.py::test_addition PASSED\ntests/test_math.py::test_division FAILED\n"
        "=================================== FAILURES ===================================\n"
        "src/math_ops.py:15: ZeroDivisionError\nE   ZeroDivisionError: division by zero\n"
        "=========================== 1 failed, 1 passed in 0.05s ===========================\n"
    )
    summary = bridge.parse_pytest_output(stdout=sample_stdout, stderr="", exit_code=1, duration_sec=0.05)
    assert (summary.exit_code, summary.failed_count, summary.passed_count, summary.total_tests) == (1, 1, 1, 2)
    loc = bridge.extract_failure_location(summary, target_file_hint="src/math_ops.py")
    assert loc is not None and ("math_ops.py" in loc.file_path, loc.line_number, loc.error_type, loc.suspiciousness) == (True, 15, "ZeroDivisionError", 1.0)
    payload_str = loc.render_payload_json()
    assert ("math_ops.py:15" in json.loads(payload_str)["loc"], len(payload_str) < 320) == (True, True)

    multi_tb_stdout = (
        "tests/test_m.py::test_1 FAILED\ntests/test_m.py::test_2 FAILED\ntests/test_m.py::test_3 FAILED\n"
        "=================================== FAILURES ===================================\n"
        "src/core_service.py:12: ValueError\nsrc/core_service.py:12: ValueError\nsrc/core_service.py:88: ValueError\n"
        "E   ValueError: bad state\n"
    )
    loc_m = bridge.extract_failure_location(bridge.parse_pytest_output(stdout=multi_tb_stdout, stderr="", exit_code=1, duration_sec=0.03), target_file_hint="src/core_service.py")
    assert loc_m is not None and loc_m.line_number == 12

    target_mod, test_mod = tmp_path / "svc_partial.py", tmp_path / "test_svc_partial.py"
    target_mod.write_text("A = 0\nB = 0\n", encoding="utf-8")
    test_mod.write_text("import svc_partial\ndef test_a():\n    assert svc_partial.A == 1\ndef test_b():\n    assert svc_partial.B == 1\n", encoding="utf-8")
    pipe = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe.bridge = _InProcessPytestBridge(tmp_path, test_mod, target_mod)
    rep = pipe.run_pipeline(test_cmd="pytest", target_file=target_mod, repair_callback=lambda _l, _c: bool(target_mod.write_text("A = 1\nB = 0\n", encoding="utf-8")))
    expected_d, expected_q = auto_heal_pipeline._compute_rsi_metrics(0, 2, target_mod, "A = 0\nB = 0\n")
    assert (rep.success, rep.rolled_back, rep.initial_failed, rep.final_failed, rep.rsi_delta, rep.rsi_fitness_q) == (False, True, 2, 2, expected_d, expected_q)


def _assert_snapshot_fitness_and_selective_cleanup(tmp_path: Path, mgr: Any) -> None:
    raw = b"alpha = 1\n"
    real_f = tmp_path / "target.py"
    real_f.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    assert hsr_cli._verify_restored_file(real_f, FileSnapshot(relative_path="target.py", absolute_path=str(real_f), sha256_hash=sha, exists_before=True), raw) is True
    assert hsr_cli._verify_restored_file(real_f, FileSnapshot(relative_path="target.py", absolute_path=str(real_f), sha256_hash="0" * 64, exists_before=True), raw) is False
    assert hsr_cli._verify_restored_file(tmp_path / "absent.py", FileSnapshot(relative_path="absent.py", absolute_path=str(tmp_path / "absent.py"), sha256_hash="", exists_before=False), b"") is True

    for args, expect_err in (((0, 0, 0, 0, 0), True), ((1, 0, 1, 0, 0), False), ((1, 0, 1, 0, -1), True), ((1, 1, 1, 1, 1), False), ((1, 0, 1, 0, 1), True), ((2, 1, 2, 2, 1), True), ((3, 1, 3, 1, 1), False)):
        assert (hsr_cli._check_regression_reason(*args) is not None) is expect_err
    assert (hsr_cli._check_equivalent_green(True, 0, 5, 0, 5, 0, -1, 0), hsr_cli._check_equivalent_green(True, 0, 5, 0, 5, 0, 1, 0)) == (True, False)
    verdicts = (
        mgr.evaluate_fitness(5, 0, 4, 1, exit_code=0).verdict,
        mgr.evaluate_fitness(4, 1, 3, 2, exit_code=1).verdict,
        mgr.evaluate_fitness(3, 3, 3, 2, exit_code=1).verdict,
        mgr.evaluate_fitness(2, 2, 3, 2, exit_code=1).verdict,
        mgr.evaluate_fitness(4, 0, 4, 0, 0, allow_equivalent_green=True, delta_cc=-1, ast_sast_violations=0).verdict,
        mgr.evaluate_fitness(4, 0, 4, 0, 0).verdict,
        mgr.evaluate_fitness(2, 1, 2, 1, 1).verdict,
    )
    assert verdicts == (FitnessVerdict.PASSED, FitnessVerdict.IMPROVED, FitnessVerdict.REGRESSION, FitnessVerdict.REGRESSION, FitnessVerdict.REFACTOR_EQUIVALENT, FitnessVerdict.NEUTRAL, FitnessVerdict.NEUTRAL)


def _assert_snapshot_id_validation_and_sel(tmp_path: Path) -> None:
    broken = tmp_path / "broken_restore.py"
    assert hsr_cli._restore_single_entry(broken, FileSnapshot(relative_path="broken_restore.py", absolute_path=str(broken), sha256_hash="", exists_before=True, content="x = 1\n"), str(tmp_path), lambda _p, _b: (_ for _ in ()).throw(OSError("disk error"))) is False
    assert hsr_cli._validate_snapshot_id("snap_ok-01") == "snap_ok-01"
    for bad_id in ("", "../escape", "sub/dir", "sub\\dir", "bad id", "a" * 81):
        with pytest.raises(ValueError):
            hsr_cli._validate_snapshot_id(bad_id)
    mgr_sel = HealingSnapshotManager(base_temp_dir=tmp_path / "snaps_sel")
    f1, f2 = tmp_path / "f1.py", tmp_path / "f2.py"
    f1.write_text("A = 1\n", encoding="utf-8")
    f2.write_text("B = 2\n", encoding="utf-8")
    s1, s2 = mgr_sel.create_snapshot([f1]), mgr_sel.create_snapshot([f2])
    mgr_sel.cleanup(snapshot_id=s1)
    disk_manifest = json.loads((tmp_path / "snaps_sel" / "snapshot_manifest.json").read_text(encoding="utf-8"))
    assert (s1 in mgr_sel.active_snapshots, (tmp_path / "snaps_sel" / s1).exists(), s2 in mgr_sel.active_snapshots, (tmp_path / "snaps_sel" / s2).is_dir(), s1 in disk_manifest, s2 in disk_manifest) == (False, False, True, True, False, True)


@pytest.mark.integration
def test_healing_snapshot_rollback_fitness_and_corrupt_manifest(tmp_path: Path) -> None:
    """Verifica snapshot SHA-256, manifest corrotto/assente, rollback selettivo, fitness gate e I/O errors."""
    snap_bad_dir = tmp_path / "snap_corrupt"
    snap_bad_dir.mkdir()
    man_p = snap_bad_dir / "snapshot_manifest.json"
    for bad_json in ("{corrupt", "[]"):
        man_p.write_text(bad_json, encoding="utf-8")
        with pytest.raises(ValueError, match="Corrupt snapshot manifest"):
            HealingSnapshotManager(base_temp_dir=snap_bad_dir)

    mgr = HealingSnapshotManager(base_temp_dir=tmp_path / "snapshots")
    existing, new_file = tmp_path / "existing.py", tmp_path / "created_later.py"
    existing.write_text("VALUE = 10\n", encoding="utf-8")
    snap_id = mgr.create_snapshot([existing, new_file])
    assert snap_id in mgr.active_snapshots
    existing.write_text("VALUE = 999\n", encoding="utf-8")
    new_file.write_text("EXTRA = True\n", encoding="utf-8")
    mgr.active_snapshots[snap_id].files[str(existing.resolve())].content_b64 = ""
    mgr.active_snapshots.clear()
    if mgr.manifest_path.exists():
        mgr.manifest_path.unlink()
    assert (all(mgr.rollback(snap_id).values()), existing.read_text(encoding="utf-8"), new_file.exists()) == (True, "VALUE = 10\n", False)

    snap_disk_id = mgr.create_snapshot([existing])
    assert (hsr_cli._handle_rollback_cli(mgr, "snap_nonexistent_id"), hsr_cli._handle_rollback_cli(mgr, snap_disk_id)) == (1, 0)
    _assert_snapshot_fitness_and_selective_cleanup(tmp_path, mgr)
    _assert_snapshot_id_validation_and_sel(tmp_path)


@pytest.mark.integration
def test_auto_heal_pipeline_repair_and_patch_note(tmp_path: Path) -> None:
    """Verifica build pulita (ciclo 0), riparazione con patch note e rollback su regressione."""
    ok_target, ok_test = tmp_path / "app_ok.py", tmp_path / "test_ok.py"
    ok_target.write_text("VAL = 100\n", encoding="utf-8")
    ok_test.write_text("import app_ok\ndef test_ok():\n    assert app_ok.VAL == 100\n", encoding="utf-8")
    pipe_clean = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe_clean.bridge = _InProcessPytestBridge(tmp_path, ok_test, ok_target)
    rep_clean = pipe_clean.run_pipeline(test_cmd="pytest", target_file=ok_target)
    assert rep_clean.success is True and rep_clean.cycles_used == 0 and "Clean build" in rep_clean.message

    calc_target, calc_test = tmp_path / "calc.py", tmp_path / "test_calc.py"
    calc_target.write_text("def calc_div(a, b):\n    return a / b\n", encoding="utf-8")
    calc_test.write_text("import calc\ndef test_div_ok():\n    assert calc.calc_div(10, 2) == 5\ndef test_div_zero():\n    assert calc.calc_div(10, 0) == 0\n", encoding="utf-8")
    pipe_heal = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    pipe_heal.bridge = _InProcessPytestBridge(tmp_path, calc_test, calc_target)
    rep_heal = pipe_heal.run_pipeline(test_cmd="pytest", target_file=calc_target, repair_callback=lambda _l, _c: bool(calc_target.write_text("def calc_div(a, b):\n    if b == 0:\n        return 0\n    return a / b\n", encoding="utf-8")))
    assert rep_heal.success is True and rep_heal.cycles_used == 1 and rep_heal.patch_note_line is not None and "[AUTO-HEALED]" in rep_heal.patch_note_line and "ZeroDivisionError" in rep_heal.patch_note_line

    fragile_target, fragile_test = tmp_path / "fragile.py", tmp_path / "test_fragile.py"
    fragile_target.write_text("X = 1\n", encoding="utf-8")
    fragile_test.write_text("import fragile\ndef test_one():\n    assert fragile.X == 2\n", encoding="utf-8")
    pipe_reg = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe_reg.bridge = _InProcessPytestBridge(tmp_path, fragile_test, fragile_target)
    rep_reg = pipe_reg.run_pipeline(test_cmd="pytest", target_file=fragile_target, repair_callback=lambda _l, _c: bool(fragile_target.write_text("BROKEN SYNTAX @@@ ###\n", encoding="utf-8")))
    assert rep_reg.success is False and rep_reg.rolled_back is True and fragile_target.read_text(encoding="utf-8") == "X = 1\n" and "Rollback to original state" in rep_reg.message


def _assert_auto_heal_cli_empty_and_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_ws = tmp_path / "empty_cli_ws"
    empty_ws.mkdir()
    rc_empty, out_empty, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(empty_ws), "--json"])
    assert (rc_empty, json.loads(out_empty)["cycles_used"]) == (0, 0)

    stg_ws = tmp_path / "stg_cli_ws"
    (stg_ws / ".staging").mkdir(parents=True)
    (stg_ws / ".staging" / "demo.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(AutoHealPipeline, "run_pipeline", lambda self, **kw: AutoHealSessionReport(success=False, cycles_used=1, max_cycles=1, initial_failed=1, final_failed=1, fault_location="demo.py:1", error_type="AssertionError", rolled_back=True, message="Mocked CLI failure."))
    rc_stg, out_stg, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(stg_ws)])
    assert (rc_stg, "Last detected fault" in out_stg) == (1, True)


@pytest.mark.integration
def test_auto_heal_helpers_retry_improved_and_cli_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica classify_failure, normalize_test_command, slice_file, IMPROVED->PASSED e CLI."""
    assert (
        auto_heal_pipeline.classify_failure("TimeoutExpired after 5s"),
        auto_heal_pipeline.classify_failure("SyntaxError: invalid"),
        auto_heal_pipeline.classify_failure("ImportError: no mod"),
        auto_heal_pipeline.classify_failure("AssertionError: x"),
        auto_heal_pipeline.classify_failure("oops", exit_code=1),
        auto_heal_pipeline.classify_failure("ok", exit_code=0),
    ) == ("TIMEOUT_ERROR", "SYNTAX_ERROR", "IMPORT_ERROR", "ASSERTION_ERROR", "RUNTIME_ERROR", "NONE")
    assert ("-m pytest" in str(auto_heal_pipeline.normalize_test_command("pytest")), "-m pytest -q" in str(auto_heal_pipeline.normalize_test_command("pytest -q"))) == (True, True)
    assert (auto_heal_pipeline.normalize_test_command(["pytest", "-q"])[-2:], auto_heal_pipeline.normalize_test_command(["python", "a.py"])) == (["pytest", "-q"], ["python", "a.py"])
    assert (auto_heal_pipeline.KarpathySlicer.slice_file(tmp_path / "nope.py", 1).content, auto_heal_pipeline.KarpathySlicer.slice_source("def broken(:", target_line=1).function_name) == ("<file not found>", None)

    tgt, tst = tmp_path / "svc_multi.py", tmp_path / "test_svc_multi.py"
    tgt.write_text("A = 0\nB = 0\n", encoding="utf-8")
    tst.write_text("import svc_multi\ndef test_a():\n    assert svc_multi.A == 1\ndef test_b():\n    assert svc_multi.B == 1\n", encoding="utf-8")
    pipe = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    pipe.bridge = _InProcessPytestBridge(tmp_path, tst, tgt)
    rep_multi = pipe.run_pipeline(test_cmd="pytest", target_file=tgt, repair_callback=lambda _l, cycle: bool(tgt.write_text("A = 1\nB = 0\n" if cycle == 1 else "A = 1\nB = 1\n", encoding="utf-8")))
    assert (rep_multi.success, rep_multi.cycles_used) == (True, 2)

    tgt.write_text("A = 0\nB = 0\n", encoding="utf-8")
    pipe_budget = AutoHealPipeline(cwd=tmp_path, max_cycles=1)
    pipe_budget.bridge = _InProcessPytestBridge(tmp_path, tst, tgt)
    rep_fail = pipe_budget.run_pipeline(test_cmd="pytest", target_file=tgt, repair_callback=lambda _l, _c: (_ for _ in ()).throw(RuntimeError("callback failure")))
    assert (rep_fail.success, rep_fail.rolled_back, rep_fail.cycles_used) == (False, True, 1)
    _assert_auto_heal_cli_empty_and_mocked(tmp_path, monkeypatch)


def _assert_trim_and_karpathy_slicer(ahl_ms: Any) -> None:
    empty_slice = auto_heal_pipeline.CodeSlice(start_line=1, end_line=1, target_line=1, content="")
    assert ahl_ms.trim_code_slice_tokens(empty_slice, max_tokens=5) == (empty_slice, 0)
    long_single = auto_heal_pipeline.CodeSlice(start_line=1, end_line=1, target_line=1, content=" ".join(f"w{i}" for i in range(10)), function_name="f")
    trunc_s, trunc_n = ahl_ms.trim_code_slice_tokens(long_single, max_tokens=3)
    assert (trunc_n, trunc_s.content) == (3, "w0 w1 w2")
    asym_out, asym_toks = ahl_ms.trim_code_slice_tokens(auto_heal_pipeline.CodeSlice(start_line=1, end_line=3, target_line=2, content="a b\nc d\ne f g h i j", function_name="asym"), max_tokens=5)
    assert (asym_toks, asym_out.start_line, asym_out.end_line) == (4, 1, 2)
    assert auto_heal_pipeline.KarpathySlicer.slice_source("", target_line=1).content == ""
    small_fn_slice = auto_heal_pipeline.KarpathySlicer.slice_source("def small_fn(a):\n    b = a + 1\n    return b\n", target_line=2, window=4)
    assert (small_fn_slice.function_name, small_fn_slice.start_line, small_fn_slice.end_line) == ("small_fn", 1, 3)
    big_fn_lines = ["def long_fn(x):"] + [f"    v_{i} = x + {i}" for i in range(34)] + ["    return v_33"]
    big_s = auto_heal_pipeline.KarpathySlicer.slice_source("\n".join(big_fn_lines), target_line=20, window=2)
    assert (big_s.function_name, big_s.start_line, big_s.end_line) == ("long_fn", 18, 22)


@pytest.mark.fast
def test_auto_heal_circuit_breaker_trim_dspy_and_slice_slicer(tmp_path: Path) -> None:
    """Verifica MAX_HEALING_CYCLES=3, models_and_slice, KarpathySlicer, DSPyTelemetryHook e _build_defect_vector."""
    from _internal.auto_heal_pipeline import models_and_slice as ahl_ms

    assert (auto_heal_pipeline.MAX_HEALING_CYCLES, AutoHealPipeline(cwd=tmp_path).max_cycles) == (3, 3)
    big_slice = auto_heal_pipeline.CodeSlice(start_line=1, end_line=6, target_line=3, content="\n".join(f"v_{i} = token_{i}_a + token_{i}_b + token_{i}_c" for i in range(6)), function_name="compute")
    trimmed, tok_count = auto_heal_pipeline.trim_code_slice_tokens(big_slice, max_tokens=12)
    assert (tok_count <= 12, trimmed.target_line) == (True, 3)
    report = auto_heal_pipeline.DiagnoseSliceReport(success=False, target_file="sample.py", exit_code=1, tests_passed=1, tests_failed=1, failure_category="ASSERTION_ERROR", fault_location="sample.py:3", ochiai_score=1.0, n_ef=1, n_ep=0, code_slice_tokens=tok_count, code_slice=trimmed, rsi_delta=10, rsi_fitness_q=50.0, message="Diagnose slice unit verified.")
    assert report.code_slice_tokens == tok_count
    _assert_trim_and_karpathy_slicer(ahl_ms)

    log_p = tmp_path / "dspy_dir" / "telemetry.jsonl"
    auto_heal_pipeline.DSPyTelemetryHook(log_p).record_run(auto_heal_pipeline.DSPyTelemetryRecord(run_id="r1", task_name="heal", cycles_total=1, final_status="PASSED", cycles_telemetry=[{"c": 1}]))
    assert (json.loads(log_p.read_text(encoding="utf-8").splitlines()[0])["run_id"], ahl_ms._is_timeout_output("")) == ("r1", False)
    assert (auto_heal_pipeline.normalize_test_command("python -m unittest"), auto_heal_pipeline.normalize_test_command(123)) == ("python -m unittest", 123)  # type: ignore[arg-type]

    dv_target = tmp_path / "dv_mod.py"
    dv_target.write_text("def f(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    assert auto_heal_pipeline._build_defect_vector(dv_target, "def f(x: int) -> int:\n    return x\n", 4, 1).tests_passed == 4


@pytest.mark.stress
def test_builder_mutation_gate_real_sandbox_kills_all_mutants(tmp_path: Path) -> None:
    """Esegue builder_mutation_gate su mini modulo+test (max_mutants=2, kill_rate=1.0)."""
    ws = tmp_path / "mut_ws"
    for d in ("scripts", "tests", ".staging/scripts"):
        (ws / d).mkdir(parents=True)
    pre_src, post_src = "def in_window(n: int) -> bool:\n    return n > 0\n", "def in_window(n: int) -> bool:\n    return n >= 10\n"
    test_src = "from scripts.window_mod import in_window\n\ndef test_in_window_boundaries():\n    assert in_window(9) is False\n    assert in_window(10) is True\n    assert in_window(11) is True\n"
    (ws / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "scripts" / "window_mod.py").write_text(pre_src, encoding="utf-8")
    (ws / ".staging" / "scripts" / "window_mod.py").write_text(post_src, encoding="utf-8")
    (ws / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "tests" / "test_window_mod.py").write_text(test_src, encoding="utf-8")
    assert "in_window" in mg_mod.find_touched_functions(pre_src, post_src)
    report = mut_runner.run_mutation_gate(workspace_root=ws, target_rel_path="scripts/window_mod.py", test_targets=["tests/test_window_mod.py"], stage_dir=ws / ".staging", max_mutants=2, min_kill_rate=0.80)
    assert report.baseline_passed is True and report.passed is True and report.mutants_total == 2 and report.kill_rate == 1.0


@pytest.mark.fast
def test_wave1a_mutation_gate_budget_exhausted_and_timeout_rc_minus_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica budget_exhausted fail-closed e timed_out=True su rc == -1."""
    from _internal.dast_sandbox_runner.sandbox_fs import ShadowSandbox

    mut = mg_mod.MutantSpec(mutant_id="MUT-01-BinOpFlip", operator="BinOpFlip", rel_path="scripts/m.py", function_name="fn", line_number=2, original_snippet="a + b", mutated_snippet="a - b", mutated_source="def fn(a, b):\n    return a - b\n")
    outcome_ok = mut_runner.MutantOutcome(mutant_id=mut.mutant_id, operator=mut.operator, function_name="fn", line_number=2, killed=True, exit_code=1, timed_out=False, duration_sec=0.05)
    rep_exh = mut_runner._build_final_gate_report("scripts/m.py", ["fn"], [mut], [outcome_ok], budget_exhausted=True, min_kill_rate=0.8, elapsed=1.0)
    assert rep_exh.passed is False and rep_exh.budget_exhausted is True

    monkeypatch.setattr(mut_runner, "_run_pytest_fail_fast", lambda *_a: (-1, 0.25))
    with ShadowSandbox() as sb:
        outcomes, exh = mut_runner._evaluate_mutants_in_sandbox(sb, "scripts/m.py", "def fn(a,b): return a+b\n", [mut], ["tests/test_m.py"], tmp_path / "bt", time.perf_counter(), 1.0, 10.0)
        assert exh is False and outcomes[0].timed_out is True and outcomes[0].killed is False
        _, exh_budget = mut_runner._evaluate_mutants_in_sandbox(sb, "scripts/m.py", "def fn(a,b): return a+b\n", [mut], ["tests/test_m.py"], tmp_path / "bt", time.perf_counter() - 10.0, 1.0, 1.0)
        assert exh_budget is True


def _assert_mutant_gen_iter_and_diff_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mg_mod, "get_repo_snapshot_cache", None)
    assert (mg_mod._parse_ast_cached("def ok(): return 1\n") is not None, mg_mod._parse_ast_cached("def bad(:"), mg_mod._iter_func_nodes(ast.Constant(1))) == (True, None, [])
    dup_src = "def dup(): return 1\ndef dup(): return 2\ndef dup(): return 3\n"
    assert {q for q, _ in mg_mod._iter_func_nodes(ast.parse(dup_src))} == {"dup", "dup#2", "dup#3"}
    getter_fn = ast.parse("class Box:\n    @v.getter\n    def v(self): return 1\n").body[0].body[0]  # type: ignore[attr-defined]
    seen_g = {"Box.v"}
    assert (mg_mod._unique_func_qname(getter_fn, "Box", seen_g), mg_mod._unique_func_qname(getter_fn, "Box", seen_g)) == ("Box.v[getter]", "Box.v#2")
    assert (mg_mod.has_executable_python_diff(None, "x = 1"), mg_mod.has_executable_python_diff("def bad(:", "x = 1")) == (True, True)
    assert (mg_mod.find_touched_functions(None, "def a(): pass"), mg_mod.find_touched_functions("def bad(:", "def a(): pass"), mg_mod.find_touched_functions("", "def bad(:")) == ({"a"}, {"a"}, set())


@pytest.mark.fast
def test_mutant_gen_disambiguation_and_missing_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica @property disambiguation e rami mancanti di builder_mutation_gate/mutant_gen.py."""
    pre = "class Box:\n    @property\n    def val(self) -> int:\n        return self._v + 1\n    @val.setter\n    def val(self, n: int) -> None:\n        self._v = n + 2\n"
    post = "class Box:\n    @property\n    def val(self) -> int:\n        return self._v + 10\n    @val.setter\n    def val(self, n: int) -> None:\n        self._v = n + 20\n"
    assert {"Box.val", "Box.val[setter]"}.issubset(mg_mod.find_touched_functions(pre, post))
    fn_names = {m.function_name for m in mg_mod.generate_differential_mutants("scripts/box.py", pre, post, max_mutants=4)}
    assert {"Box.val", "Box.val[setter]"}.issubset(fn_names)
    formatted_post = "# commento\n\n" + post
    base_t = ast.parse(formatted_post)
    assert (
        mg_mod._materialize_mutant(base_t, "scripts/box.py", formatted_post, 9, "NoOp", "Box.val", 0, ast.Constant(1)),
        mg_mod._materialize_mutant(base_t, "scripts/box.py", formatted_post, 9, "NoOp", "MissingFn", 0, ast.Constant(1)),
        mg_mod._materialize_mutant(base_t, "scripts/box.py", formatted_post, 9, "BinOpFlip", "Box.val", 99, ast.Constant(1)),
    ) == (None, None, None)
    _assert_mutant_gen_iter_and_diff_edges(monkeypatch)


@pytest.mark.integration
def test_wave1a_real_2strike_circuit_breaker_syntax_error_and_trim(tmp_path: Path) -> None:
    """Verifica Circuit Breaker 2-Strike, SyntaxError prev_failed>=1 e cap trim_code_slice_tokens."""
    tgt, tst = tmp_path / "strike_mod.py", tmp_path / "test_strike_mod.py"
    tgt.write_text("X = 1\n", encoding="utf-8")
    tst.write_text("import strike_mod\ndef test_x():\n    assert strike_mod.X == 2\n", encoding="utf-8")
    pipe = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    pipe.bridge = _InProcessPytestBridge(tmp_path, tst, tgt)
    cycles_seen = []

    def bad_fix(_loc: OchiaiBridgeLocation, cycle: int) -> bool:
        cycles_seen.append(cycle)
        tgt.write_text(f"X = {90 + cycle}\n", encoding="utf-8")
        return True

    rep_2s = pipe.run_pipeline(test_cmd="pytest", target_file=tgt, repair_callback=bad_fix)
    assert cycles_seen == [1, 2] and rep_2s.success is False and rep_2s.escalation_required is True and rep_2s.rolled_back is True and "2-Strike" in rep_2s.message and tgt.read_text(encoding="utf-8") == "X = 1\n"

    syn_tgt, syn_tst = tmp_path / "syn_mod.py", tmp_path / "test_syn_mod.py"
    syn_tgt.write_text("def val(:\n    return 1\n", encoding="utf-8")
    syn_tst.write_text("import syn_mod\ndef test_a():\n    assert syn_mod.val() == 1\ndef test_b():\n    assert syn_mod.val() == 2\n", encoding="utf-8")
    pipe_syn = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe_syn.bridge = _InProcessPytestBridge(tmp_path, syn_tst, syn_tgt)
    rep_syn = pipe_syn.run_pipeline(test_cmd="pytest", target_file=syn_tgt, repair_callback=lambda _l, _c: bool(syn_tgt.write_text("def val():\n    return 1\n", encoding="utf-8")))
    assert rep_syn.initial_failed >= 1 and rep_syn.rolled_back is True

    trimmed, tok_cnt = auto_heal_pipeline.trim_code_slice_tokens(auto_heal_pipeline.CodeSlice(start_line=10, end_line=10, target_line=10, content=" ".join(f"tok{i}" for i in range(25)), function_name="dense"), max_tokens=5)
    assert tok_cnt <= 5 and len(trimmed.content.split()) <= 5


@pytest.mark.fast
def test_diagnose_helper_paths_clean_failures_and_missing_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita diagnose_helper._resolve_target_path e run_diagnose_slice (clean/error/SyntaxError/missing)."""
    from _internal.auto_heal_pipeline import diagnose_helper as ahl_diag, rsi_bridge_helpers as ahl_rsi

    ws, alt_dir = tmp_path / "diag_ws", tmp_path / "alt_cwd"
    ws.mkdir()
    alt_dir.mkdir()
    (ws / "in_ws.py").write_bytes(b"V = 1\n")
    (alt_dir / "rel_alt.py").write_bytes(b"V = 2\n")
    monkeypatch.chdir(alt_dir)
    assert ahl_diag._resolve_target_path(ws, (ws / "in_ws.py").resolve()) == (ws / "in_ws.py").resolve()
    assert ahl_diag._resolve_target_path(ws, "in_ws.py") == ws / "in_ws.py"
    assert ahl_diag._resolve_target_path(ws, "rel_alt.py") == (alt_dir / "rel_alt.py").resolve()
    assert ahl_diag._resolve_target_path(ws, "absent.py") == ws / "absent.py"

    ok_t, ok_tst = ws / "ok_app.py", ws / "test_ok_app.py"
    ok_t.write_bytes(b"VAL = 7\n")
    ok_tst.write_bytes(b"import ok_app\ndef test_val():\n    assert ok_app.VAL == 7\n")
    pipe_ok = AutoHealPipeline(cwd=ws, max_cycles=1)
    pipe_ok.bridge = _InProcessDiagnoseBridge(ws, ok_tst, ok_t)
    rep_ok = pipe_ok.diagnose_slice("pytest", "ok_app.py")
    assert (rep_ok.success, rep_ok.failure_category, rep_ok.code_slice, rep_ok.rsi_delta) == (True, "NONE", None, 0)

    ws_e = tmp_path / "diag_err_ws"
    ws_e.mkdir()
    helper_mod, caller_mod, caller_tst = ws_e / "helper_div.py", ws_e / "caller_app.py", ws_e / "test_caller.py"
    helper_mod.write_bytes(b"def div(a, b):\n    return a / b\n")
    caller_mod.write_bytes(b"import helper_div\ndef run():\n    return helper_div.div(10, 0)\n")
    caller_tst.write_bytes(b"import caller_app\ndef test_run():\n    assert caller_app.run() == 0\n")

    rep_fail = ahl_diag.run_diagnose_slice(ws_e, _DiffFileDiagnoseBridge(ws_e, caller_tst, helper_mod, "helper_div.py"), "pytest", "caller_app.py", ahl_rsi._resolve_prod_baseline_code, ahl_rsi._compute_rsi_metrics, max_slice_tokens=20)
    assert rep_fail.success is False and rep_fail.failure_category == "RUNTIME_ERROR" and rep_fail.code_slice is not None and rep_fail.code_slice_tokens <= 20

    syn_mod = ws_e / "syn_bad.py"
    syn_mod.write_bytes(b"def broken(:\n    return 1\n")
    rep_syn = ahl_diag.run_diagnose_slice(ws_e, _InProcessPytestBridge(ws_e, caller_tst, syn_mod), "pytest", "syn_bad.py", ahl_rsi._resolve_prod_baseline_code, ahl_rsi._compute_rsi_metrics)
    assert rep_syn.success is False and rep_syn.failure_category == "SYNTAX_ERROR"
    rep_miss = ahl_diag.run_diagnose_slice(ws_e, _InProcessDiagnoseBridge(ws_e, caller_tst, helper_mod), "pytest", "no_such_target.py", ahl_rsi._resolve_prod_baseline_code, ahl_rsi._compute_rsi_metrics)
    assert (rep_miss.success, rep_miss.code_slice) == (False, None)


def _assert_auto_heal_emit_helpers(capsys: pytest.CaptureFixture[str], ahl_cli: Any) -> None:
    ok_rep = AutoHealSessionReport(success=True, cycles_used=1, max_cycles=2, initial_failed=1, final_failed=0, patch_note_line="- **[AUTO-HEALED]** ok", message="Healed clean.")
    fail_rep = AutoHealSessionReport(success=False, cycles_used=1, max_cycles=1, initial_failed=1, final_failed=1, fault_location=None, message="No location failed.")
    assert (ahl_cli._emit_report(ok_rep, as_json=False), "[PATCH-NOTE]" in capsys.readouterr().out) == (0, True)
    assert (ahl_cli._emit_report(fail_rep, as_json=False), "Last detected fault" not in capsys.readouterr().out) == (1, True)
    diag_ok = auto_heal_pipeline.DiagnoseSliceReport(success=True, target_file="a.py", exit_code=0, tests_passed=1, tests_failed=0, failure_category="NONE", message="Diagnose clean.")
    diag_fail = auto_heal_pipeline.DiagnoseSliceReport(success=False, target_file="b.py", exit_code=1, tests_passed=0, tests_failed=1, failure_category="ASSERTION_ERROR", fault_location="b.py:2", ochiai_score=1.0, code_slice_tokens=8, message="Diagnose failed.")
    assert (ahl_cli._emit_diagnose_report(diag_ok, as_json=False), "[DIAGNOSE-SLICE]" in capsys.readouterr().out) == (0, True)
    assert (ahl_cli._emit_diagnose_report(diag_fail, as_json=False), "Ochiai=1.0" in capsys.readouterr().out) == (1, True)
    assert (ahl_cli._emit_diagnose_report(diag_fail, as_json=True), json.loads(capsys.readouterr().out)["fault_location"]) == (1, "b.py:2")


@pytest.mark.fast
def test_auto_heal_cli_emit_empty_staging_and_facade_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Esercita cli.py su emit helpers, .staging/ vuoto/mockato e flag --fail-on-empty-staging."""
    from _internal.auto_heal_pipeline import cli as ahl_cli

    _assert_auto_heal_emit_helpers(capsys, ahl_cli)
    ws = tmp_path / "heal_cli_ws"
    (ws / ".staging").mkdir(parents=True)
    rc_e_json, out_e_json, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(ws), "--json"])
    rc_e_txt, out_e_txt, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(ws)])
    assert (rc_e_json, json.loads(out_e_json)["cycles_used"], rc_e_txt, "Clean staging" in out_e_txt) == (0, 0, 0, True)

    stg_py = ws / ".staging" / "demo.py"
    stg_py.write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(AutoHealPipeline, "run_pipeline", lambda self, **_k: AutoHealSessionReport(success=True, cycles_used=1, max_cycles=3, initial_failed=1, final_failed=0, patch_note_line="- Fixed demo.", message="All fixed."))
    rc_p_ok, out_p_ok, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(ws)])
    assert (rc_p_ok, "PATCH-NOTE" in out_p_ok, "Fixed demo" in out_p_ok) == (0, True, True)
    monkeypatch.setattr(AutoHealPipeline, "run_pipeline", lambda self, **_k: AutoHealSessionReport(success=False, cycles_used=3, max_cycles=3, initial_failed=1, final_failed=1, fault_location="demo.py:1", error_type="AssertionError", message="Failed."))
    rc_p_fail, out_p_fail, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(ws), "--target-file", str(stg_py)])
    assert (rc_p_fail, "demo.py:1" in out_p_fail) == (1, True)

    monkeypatch.setattr(auto_heal_pipeline, "SBFLPytestBridge", _AutoDiscoverInProcessBridge)
    empty_ws = tmp_path / "cli_empty_ws"
    empty_ws.mkdir()
    assert json.loads(call_script_main_captured(auto_heal_pipeline, ["--cwd", str(empty_ws), "--fail-on-empty-staging", "--json"])[1])["success"] is False
    assert json.loads(call_script_main_captured(auto_heal_pipeline, ["--cwd", str(empty_ws), "--diagnose-slice", "--json"])[1])["success"] is True
    rc_d1, out_d1, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(empty_ws), "--diagnose-slice", "--fail-on-empty-staging"])
    assert (rc_d1, "Empty staging" in out_d1) == (1, True)


@pytest.mark.integration
def test_auto_heal_cli_single_and_multi_staging_batches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita main() CLI su .staging/ singolo, --target-file e batch multi-file."""
    monkeypatch.setattr(auto_heal_pipeline, "SBFLPytestBridge", _AutoDiscoverInProcessBridge)
    single_ws = tmp_path / "cli_single_ws"
    (single_ws / ".staging").mkdir(parents=True)
    (single_ws / ".staging" / "unit_one.py").write_bytes(b"V = 10\n")
    (single_ws / "test_unit_one.py").write_bytes(b"import unit_one\ndef test_u():\n    assert unit_one.V == 10\n")
    assert call_script_main_captured(auto_heal_pipeline, ["--cwd", str(single_ws), "--diagnose-slice", "--json"])[0] == 0
    assert call_script_main_captured(auto_heal_pipeline, ["--cwd", str(single_ws), "--target-file", ".staging/unit_one.py", "--diagnose-slice"])[0] == 0
    assert call_script_main_captured(auto_heal_pipeline, ["--cwd", str(single_ws), "--target-file", ".staging/unit_one.py", "--json"])[0] == 0

    multi_ws = tmp_path / "cli_multi_ws"
    (multi_ws / ".staging").mkdir(parents=True)
    (multi_ws / ".staging" / "alpha.py").write_bytes(b"A = 1\n")
    (multi_ws / ".staging" / "beta.py").write_bytes(b"B = 0\n")
    (multi_ws / "test_alpha.py").write_bytes(b"import alpha\ndef test_a():\n    assert alpha.A == 1\n")
    (multi_ws / "test_beta.py").write_bytes(b"import beta\ndef test_b():\n    assert beta.B == 9\n")

    rc_mj, out_mj, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(multi_ws), "--json"])
    rc_mt, out_mt, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(multi_ws)])
    rc_dmj, out_dmj, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(multi_ws), "--diagnose-slice", "--json"])
    rc_dmt, out_dmt, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(multi_ws), "--diagnose-slice"])
    assert rc_mj == 1 and json.loads(out_mj)["files_processed"] == 2
    assert rc_mt == 1 and "alpha.py" in out_mt and "beta.py" in out_mt
    assert rc_dmj == 1 and json.loads(out_dmj)["files_processed"] == 2
    assert rc_dmt == 1 and "[DIAGNOSE-SLICE]" in out_dmt


def _assert_rsi_bridge_baselines_and_qd(tmp_path: Path, ahl_rsi: Any) -> tuple[Path, Path]:
    ws = tmp_path / "rsi_helpers_ws"
    (ws / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "scripts" / "svc.py").write_bytes(b"X = 1\n")
    (ws / ".staging" / "scripts" / "svc.py").write_bytes(b"X = 2\n")
    (ws / ".staging" / "scripts" / "new_only.py").write_bytes(b"Y = 3\n")
    assert (
        ahl_rsi._resolve_prod_baseline_code(ws / ".staging" / "scripts" / "svc.py"),
        ahl_rsi._resolve_prod_baseline_code(ws / ".staging" / "scripts" / "new_only.py"),
        ahl_rsi._resolve_prod_baseline_code(ws / "scripts" / "missing.py"),
    ) == ("X = 1\n", "", "")
    assert ahl_rsi._resolve_telemetry_target(ws) == ws / ".staging" / "nk_tracking" / "rsi_telemetry.jsonl"
    no_stg_dir = tmp_path / "no_stg_dir"
    no_stg_dir.mkdir()
    assert (ahl_rsi._resolve_telemetry_target(no_stg_dir), ahl_rsi._resolve_telemetry_target(Path("Z:/outside_ws")).parent.name) == (no_stg_dir / "nk_tracking" / "rsi_telemetry.jsonl", "nk_auto_heal_telemetry")
    from _internal.ast_guard_validator.quality_diff_rules import QualityDiffViolation
    viols = [
        QualityDiffViolation(rule_id="QD-CC-REGRESSION", file_path="a.py", symbol_name="ok_fn", severity="MEDIUM", message="minor"),
        QualityDiffViolation(rule_id="QD-CC-REGRESSION", file_path="a.py", symbol_name="unknown_fn", severity="MEDIUM", message="med"),
        QualityDiffViolation(rule_id="QD-SCOPE-CREEP", file_path="a.py", severity="HIGH", message="scope"),
        QualityDiffViolation(rule_id="QD-OTHER-HIGH", file_path="a.py", severity="HIGH", message="high"),
        QualityDiffViolation(rule_id="QD-OTHER-LOW", file_path="a.py", severity="LOW", message="low"),
    ]
    assert ahl_rsi._classify_qd_violations(viols, post_metrics={"ok_fn": {"cc": 4, "nesting": 2}}) == (1, 1, 1, 1)
    return ws, ws / "scripts" / "svc.py"


@pytest.mark.fast
def test_rsi_bridge_helpers_baseline_qd_and_callbacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita rsi_bridge_helpers su baseline .staging, telemetry target, QD, frontend e callback."""
    from _internal.auto_heal_pipeline import rsi_bridge_helpers as ahl_rsi

    ws, svc_f = _assert_rsi_bridge_baselines_and_qd(tmp_path, ahl_rsi)
    ts_file = ws / "scripts" / "view.tsx"
    ts_file.write_bytes(b"export const label = 'ok';\n")
    assert (ahl_rsi._collect_quality_findings(ts_file, "", "export const label = 'ok';\n"), ahl_rsi._collect_quality_findings(ws / "notes.txt", "", "hello")) == ((0, 0, 0, 0), (0, 0, 0, 0))
    assert ahl_rsi._collect_single_pass_ast_findings(ws / "absent.py", "") == (0, 0, 0, 0, 0, 0)

    monkeypatch.setattr(auto_heal_pipeline, "ASTGuardValidator", None)
    assert ahl_rsi._collect_single_pass_ast_findings(svc_f, "X = 1\n") == (0, 1, 1, 0, 0, 0)
    monkeypatch.setattr(auto_heal_pipeline, "RSIDefectVector", None)
    d_fb, q_fb, vec_fb = ahl_rsi._compute_rsi_metrics_with_vector(3, 1, None, "")
    assert (d_fb, vec_fb, 0.0 < q_fb < 100.0) == (10, None, True)
    assert ahl_rsi._resolve_iteration_metrics(svc_f, "", 3, 1, (10, 70.0, None))[:2] == (10, 70.0)
    assert (ahl_rsi._format_patch_note(None, 1), ahl_rsi._hypothesis_key(None, Path("mod.py"))) == ("", ("mod.py", 0, "Unknown"))

    mgr = HealingSnapshotManager(base_temp_dir=tmp_path / "clean_snaps")
    s1 = mgr.create_snapshot([svc_f])
    ahl_rsi._cleanup_session_snapshots(mgr, s1, s1, None)
    assert s1 not in mgr.active_snapshots
    ahl_rsi._invoke_repair_cb(None, None, 1)
    ahl_rsi._invoke_repair_cb(lambda _l, _c: (_ for _ in ()).throw(RuntimeError("cb failed")), OchiaiBridgeLocation(file_path="svc.py", line_number=1, suspiciousness=1.0, error_type="E", error_message="m"), 1)


def _assert_snapshot_rollback_cli_ops(tmp_path: Path) -> None:
    assert "SnapshotBundle" in dir(healing_snapshot_rollback)
    assert (healing_snapshot_rollback.SnapshotBundle is hsr_models.SnapshotBundle, healing_snapshot_rollback.FitnessReport is hsr_models.FitnessReport) == (True, True)
    with pytest.raises(AttributeError):
        getattr(healing_snapshot_rollback, "NONEXISTENT_HSR_ATTR")
    rc_help, out_help, _ = call_script_main_captured(healing_snapshot_rollback, [])
    assert (rc_help, "--rollback" in out_help) == (0, True)

    snap_target = tmp_path / "cli_snap_target.py"
    snap_target.write_bytes(b"VAL = 11\n")
    rc_cr, out_cr, _ = call_script_main_captured(healing_snapshot_rollback, ["--create", str(snap_target)])
    assert (rc_cr, "[SNAPSHOT-CREATED]" in out_cr) == (0, True)
    snap_id = out_cr.split("ID: ", 1)[1].split(" ", 1)[0].strip()
    snap_target.write_bytes(b"VAL = 999\n")
    rc_rb, out_rb, _ = call_script_main_captured(healing_snapshot_rollback, ["--rollback", snap_id])
    assert (rc_rb, "[SNAPSHOT-ROLLED-BACK]" in out_rb, snap_target.read_bytes()) == (0, True, b"VAL = 11\n")
    assert call_script_main_captured(healing_snapshot_rollback, ["--rollback", "snap_unknown_000"])[0] == 1
    rc_cl, out_cl, _ = call_script_main_captured(healing_snapshot_rollback, ["--cleanup"])
    assert (rc_cl, "[SNAPSHOT-CLEANUP]" in out_cl) == (0, True)


@pytest.mark.integration
def test_facade_mutation_gate_and_snapshot_rollback_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Esercita facciate CLI builder_mutation_gate e healing_snapshot_rollback."""
    _ = isolated_nk_env
    assert ("MutantSpec" in dir(mut_mod), mut_mod.reconfigure_streams is not None) == (True, True)
    with pytest.raises(AttributeError):
        getattr(mut_mod, "NONEXISTENT_MUT_ATTR")

    ws = tmp_path / "mut_facade_ws"
    for d in ("scripts", "tests", ".staging/scripts"):
        (ws / d).mkdir(parents=True)
    (ws / "scripts" / "__init__.py").write_bytes(b"")
    (ws / "tests" / "__init__.py").write_bytes(b"")
    (ws / "scripts" / "calc_f.py").write_bytes(b"def add_n(a, b):\n    return a - b\n")
    (ws / ".staging" / "scripts" / "calc_f.py").write_bytes(b"def add_n(a, b):\n    return a + b\n")
    (ws / "tests" / "test_calc_f.py").write_bytes(b"from scripts.calc_f import add_n\ndef test_add():\n    assert add_n(2, 3) == 5\n")

    rc_mj, out_mj, _ = call_script_main_captured(mut_mod, ["--workspace-root", str(ws), "--target-file", "scripts/missing.py", "--test-targets", "tests/test_calc_f.py", "--json"])
    rc_mt, out_mt, _ = call_script_main_captured(mut_mod, ["--workspace-root", str(ws), "--target-file", "scripts/missing.py", "--test-targets", "tests/test_calc_f.py"])
    assert (rc_mj, json.loads(out_mj)["passed"], rc_mt, "[FAIL]" in out_mt) == (1, False, 1, True)

    calls_count = [0]

    def _fast_pytest_eval(*_args: Any) -> Tuple[int, float]:
        calls_count[0] += 1
        return (0, 0.01) if calls_count[0] == 1 else (1, 0.01)

    monkeypatch.setattr(mut_runner, "_run_pytest_fail_fast", _fast_pytest_eval)
    rc_pass, out_pass, _ = call_script_main_captured(mut_mod, ["--workspace-root", str(ws), "--stage-dir", str(ws / ".staging"), "--target-file", "scripts/calc_f.py", "--test-targets", "tests/test_calc_f.py", "--max-mutants", "2"])
    calls_count[0] = 0
    rc_pj, out_pj, _ = call_script_main_captured(mut_mod, ["--workspace-root", str(ws), "--target-file", "scripts/calc_f.py", "--test-targets", "tests/test_calc_f.py, ", "--max-mutants", "2", "--json"])
    assert (rc_pass, "[PASS]" in out_pass, rc_pj, json.loads(out_pj)["passed"]) == (0, True, 0, True)
    _assert_snapshot_rollback_cli_ops(tmp_path)


@pytest.mark.fast
def test_rsi_bridge_helpers_fail_closed_on_import_and_ast_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica comportamento fail-closed di rsi_bridge_helpers su ImportError ed errori AST."""
    from _internal.auto_heal_pipeline import rsi_bridge_helpers as ahl_rsi

    ws = tmp_path / "rsi_fc_ws"
    (ws / "scripts").mkdir(parents=True)
    py_f, tsx_f = ws / "scripts" / "mod_err.py", ws / "scripts" / "view_err.tsx"
    py_f.write_bytes(b"X = 1\n")
    tsx_f.write_bytes(b"export const x = 1;\n")

    monkeypatch.setitem(sys.modules, "_internal.ast_guard_validator.quality_diff_checker", None)
    assert ahl_rsi._collect_quality_findings(py_f, "", "X = 1\n") == (1, 0, 0, 0)
    monkeypatch.setitem(sys.modules, "_internal.ast_guard_validator.frontend_static_checker", None)
    assert ahl_rsi._collect_quality_findings(tsx_f, "", "export const x = 1;\n") == (1, 0, 0, 0)

    class _RaisingASTGuard:
        @staticmethod
        def validate_code_edit(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("ast guard failure")

    monkeypatch.setattr(auto_heal_pipeline, "ASTGuardValidator", _RaisingASTGuard)
    assert ahl_rsi._collect_single_pass_ast_findings(py_f, "") == (0, 1, 1, 0, 0, 0)

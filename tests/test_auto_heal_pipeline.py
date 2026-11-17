#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Auto-Heal Pipeline di Nexus Keystone v6.4.0-Carbon.
Modulo: tests/test_auto_heal_pipeline.py.
Valida GT-07 (SBFL Ochiai suspiciousness == 1.0 e < 320 char), snapshot, retry, budget e CLI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Optional, Sequence, Tuple

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

pytestmark = pytest.mark.fast

sbfl_pytest_bridge = load_nk_script_module("sbfl_pytest_bridge")
healing_snapshot_rollback = load_nk_script_module("healing_snapshot_rollback")
auto_heal_pipeline = load_nk_script_module("auto_heal_pipeline")

SBFLPytestBridge = sbfl_pytest_bridge.SBFLPytestBridge
PytestRunSummary = sbfl_pytest_bridge.PytestRunSummary
OchiaiBridgeLocation = sbfl_pytest_bridge.OchiaiBridgeLocation

HealingSnapshotManager = healing_snapshot_rollback.HealingSnapshotManager
FitnessVerdict = healing_snapshot_rollback.FitnessVerdict

AutoHealPipeline = auto_heal_pipeline.AutoHealPipeline
AutoHealSessionReport = auto_heal_pipeline.AutoHealSessionReport


class _InProcessPytestBridge(SBFLPytestBridge):
    """Bridge deterministico in-process per eseguire i file di test reali senza overhead di avvio."""

    def __init__(self, cwd: Path, test_file: Path, target_file: Path) -> None:
        super().__init__(cwd=cwd)
        self.test_file = test_file
        self.target_file = target_file

    def run_and_diagnose(
        self,
        test_cmd: Sequence[str] | str,
        target_file_hint: Optional[str] = None,
        timeout_sec: float = 60.0,
    ) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        """Esegue realmente i moduli target e test in-process e formatta l'output Pytest."""
        t0 = time.perf_counter()
        stdout_lines = []
        failures = []
        failed_cnt = 0
        added_cwd = str(self.cwd) not in sys.path
        if added_cwd:
            sys.path.insert(0, str(self.cwd))

        try:
            t_name = self.target_file.stem
            if t_name in sys.modules:
                del sys.modules[t_name]
            t_spec = importlib.util.spec_from_file_location(t_name, str(self.target_file))
            t_mod = importlib.util.module_from_spec(t_spec)
            sys.modules[t_name] = t_mod
            t_spec.loader.exec_module(t_mod)

            s_name = f"{self.test_file.stem}_{int(time.perf_counter() * 1000000)}"
            s_spec = importlib.util.spec_from_file_location(s_name, str(self.test_file))
            s_mod = importlib.util.module_from_spec(s_spec)
            s_spec.loader.exec_module(s_mod)

            for attr_name in sorted(dir(s_mod)):
                if not attr_name.startswith("test_"):
                    continue
                fn = getattr(s_mod, attr_name)
                if not callable(fn):
                    continue
                node_id = f"{self.test_file.name}::{attr_name}"
                try:
                    fn()
                    stdout_lines.append(f"{node_id} PASSED")
                except Exception as exc:
                    stdout_lines.append(f"{node_id} FAILED")
                    failed_cnt += 1
                    tb_entries = traceback.extract_tb(exc.__traceback__)
                    target_line = 1
                    for entry in reversed(tb_entries):
                        if Path(entry.filename).name == self.target_file.name:
                            target_line = entry.lineno
                            break
                    err_cls = type(exc).__name__
                    failures.append(
                        f"___ {attr_name} ___\n"
                        f"{self.target_file.as_posix()}:{target_line}: {err_cls}\n"
                        f"E   {err_cls}: {exc}"
                    )
        except Exception as exc:
            failed_cnt += 1
            err_cls = type(exc).__name__
            stdout_lines.append(f"{self.test_file.name}::test_syntax FAILED")
            failures.append(
                f"{self.target_file.as_posix()}:1: {err_cls}\nE   {err_cls}: {exc}"
            )
        finally:
            if added_cwd and str(self.cwd) in sys.path:
                sys.path.remove(str(self.cwd))

        if failures:
            stdout_lines.append("=================================== FAILURES ===================================")
            stdout_lines.extend(failures)

        rc = 0 if failed_cnt == 0 else 1
        duration = time.perf_counter() - t0
        summary = self.parse_pytest_output("\n".join(stdout_lines) + "\n", "", rc, duration)
        loc = self.extract_failure_location(
            summary, target_file_hint=target_file_hint or str(self.target_file)
        )
        return summary, loc


def test_sbfl_pytest_bridge_parsing_and_ochiai(tmp_path: Path) -> None:
    """1. Verifica parsing Pytest, punteggio Ochiai == 1.0 e payload < 320 char (GT-07)."""
    bridge = SBFLPytestBridge(cwd=tmp_path)
    sample_stdout = """
tests/test_math.py::test_addition PASSED
tests/test_math.py::test_division FAILED

=================================== FAILURES ===================================
_________________________________ test_division _________________________________
    def test_division():
>       res = divide(10, 0)
src/math_ops.py:15: ZeroDivisionError
E   ZeroDivisionError: division by zero
=========================== 1 failed, 1 passed in 0.05s ===========================
"""
    summary = bridge.parse_pytest_output(
        stdout=sample_stdout, stderr="", exit_code=1, duration_sec=0.05
    )
    assert summary.exit_code == 1
    assert summary.failed_count == 1
    assert summary.passed_count == 1
    assert summary.total_tests == 2

    loc = bridge.extract_failure_location(summary, target_file_hint="src/math_ops.py")
    assert loc is not None
    assert "math_ops.py" in loc.file_path
    assert loc.line_number == 15
    assert loc.error_type == "ZeroDivisionError"
    assert loc.suspiciousness == 1.0

    payload_str = loc.render_payload_json()
    payload = json.loads(payload_str)
    assert "math_ops.py:15" in payload["loc"]
    assert len(payload_str) < 320


def test_healing_snapshot_and_rollback(tmp_path: Path) -> None:
    """2. Verifica creazione snapshot, rollback atomico e regole dello Strict Fitness Gate."""
    mgr = HealingSnapshotManager(base_temp_dir=tmp_path / "snapshots")
    target_file = tmp_path / "module.py"
    target_file.write_text("def run():\n    return 42\n", encoding="utf-8")

    snap_id = mgr.create_snapshot([target_file])
    assert snap_id in mgr.active_snapshots

    target_file.write_text("def run():\n    return 999\n", encoding="utf-8")
    status = mgr.rollback(snap_id)
    assert status[str(target_file)] is True
    assert "return 42" in target_file.read_text(encoding="utf-8")
    mgr.cleanup(snap_id)
    assert snap_id not in mgr.active_snapshots

    assert mgr.evaluate_fitness(5, 0, 4, 1, exit_code=0).verdict == FitnessVerdict.PASSED
    assert mgr.evaluate_fitness(4, 1, 3, 2, exit_code=1).verdict == FitnessVerdict.IMPROVED
    assert mgr.evaluate_fitness(3, 3, 3, 2, exit_code=1).verdict == FitnessVerdict.REGRESSION
    assert mgr.evaluate_fitness(2, 2, 3, 2, exit_code=1).verdict == FitnessVerdict.REGRESSION


def test_auto_heal_pipeline_repair_and_patch_note(tmp_path: Path) -> None:
    """3. Verifica build pulita (ciclo 0), riparazione con patch note e rollback su regressione."""
    ok_target = tmp_path / "app_ok.py"
    ok_target.write_text("VAL = 100\n", encoding="utf-8")
    ok_test = tmp_path / "test_ok.py"
    ok_test.write_text("import app_ok\ndef test_ok():\n    assert app_ok.VAL == 100\n", encoding="utf-8")

    pipe_clean = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe_clean.bridge = _InProcessPytestBridge(tmp_path, ok_test, ok_target)
    rep_clean = pipe_clean.run_pipeline(test_cmd="pytest", target_file=ok_target)
    assert rep_clean.success is True and rep_clean.cycles_used == 0
    assert "Clean build" in rep_clean.message

    calc_target = tmp_path / "calc.py"
    calc_target.write_text("def calc_div(a, b):\n    return a / b\n", encoding="utf-8")
    calc_test = tmp_path / "test_calc.py"
    calc_test.write_text(
        "import calc\n"
        "def test_div_ok():\n    assert calc.calc_div(10, 2) == 5\n"
        "def test_div_zero():\n    assert calc.calc_div(10, 0) == 0\n",
        encoding="utf-8",
    )

    pipe_heal = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    pipe_heal.bridge = _InProcessPytestBridge(tmp_path, calc_test, calc_target)

    def repair_callback(loc: OchiaiBridgeLocation, cycle: int) -> bool:
        calc_target.write_text(
            "def calc_div(a, b):\n    if b == 0:\n        return 0\n    return a / b\n",
            encoding="utf-8",
        )
        return True

    rep_heal = pipe_heal.run_pipeline(
        test_cmd="pytest", target_file=calc_target, repair_callback=repair_callback
    )
    assert rep_heal.success is True and rep_heal.cycles_used == 1
    assert rep_heal.patch_note_line is not None
    assert "[AUTO-HEALED]" in rep_heal.patch_note_line
    assert "ZeroDivisionError" in rep_heal.patch_note_line

    fragile_target = tmp_path / "fragile.py"
    fragile_target.write_text("X = 1\n", encoding="utf-8")
    fragile_test = tmp_path / "test_fragile.py"
    fragile_test.write_text(
        "import fragile\ndef test_one():\n    assert fragile.X == 2\n",
        encoding="utf-8",
    )

    pipe_reg = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe_reg.bridge = _InProcessPytestBridge(tmp_path, fragile_test, fragile_target)

    def bad_repair_callback(loc: OchiaiBridgeLocation, cycle: int) -> bool:
        fragile_target.write_text("BROKEN SYNTAX @@@ ###\n", encoding="utf-8")
        return True

    rep_reg = pipe_reg.run_pipeline(
        test_cmd="pytest", target_file=fragile_target, repair_callback=bad_repair_callback
    )
    assert rep_reg.success is False and rep_reg.rolled_back is True
    assert fragile_target.read_text(encoding="utf-8") == "X = 1\n"
    assert "Rollback to original state" in rep_reg.message


def test_sbfl_max_frequency_location_and_rollback_initial_rsi_metrics(
    tmp_path: Path,
) -> None:
    """4. Verifica selezione locazione a frequenza massima in SBFL e metriche RSI post-rollback iniziale."""
    bridge = SBFLPytestBridge(cwd=tmp_path)
    multi_tb_stdout = (
        "tests/test_m.py::test_1 FAILED\n"
        "tests/test_m.py::test_2 FAILED\n"
        "tests/test_m.py::test_3 FAILED\n"
        "=================================== FAILURES ===================================\n"
        "src/core_service.py:12: ValueError\n"
        "src/core_service.py:12: ValueError\n"
        "src/core_service.py:88: ValueError\n"
        "E   ValueError: bad state\n"
        "=========================== 3 failed in 0.03s ===========================\n"
    )
    summary = bridge.parse_pytest_output(
        stdout=multi_tb_stdout, stderr="", exit_code=1, duration_sec=0.03
    )
    loc = bridge.extract_failure_location(summary, target_file_hint="src/core_service.py")
    assert loc is not None and loc.line_number == 12

    target_mod = tmp_path / "svc_partial.py"
    target_mod.write_text("A = 0\nB = 0\n", encoding="utf-8")
    test_mod = tmp_path / "test_svc_partial.py"
    test_mod.write_text(
        "import svc_partial\n"
        "def test_a():\n    assert svc_partial.A == 1\n"
        "def test_b():\n    assert svc_partial.B == 1\n",
        encoding="utf-8",
    )

    pipe = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe.bridge = _InProcessPytestBridge(tmp_path, test_mod, target_mod)

    def partial_only_repair(loc_item: OchiaiBridgeLocation, cycle: int) -> bool:
        target_mod.write_text("A = 1\nB = 0\n", encoding="utf-8")
        return True

    rep = pipe.run_pipeline(
        test_cmd="pytest", target_file=target_mod, repair_callback=partial_only_repair
    )
    assert rep.success is False and rep.rolled_back is True
    assert rep.initial_failed == 2 and rep.final_failed == 2
    expected_d, expected_q = auto_heal_pipeline._compute_rsi_metrics(
        0, 2, target_mod, "A = 0\nB = 0\n"
    )
    assert rep.rsi_delta == expected_d and rep.rsi_fitness_q == expected_q


def test_auto_heal_helpers_retry_improved_and_cli_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Verifica classify_failure, normalize_test_command, slice_file, IMPROVED->PASSED e CLI."""
    assert auto_heal_pipeline.classify_failure("TimeoutExpired after 5s") == "TIMEOUT_ERROR"
    assert auto_heal_pipeline.classify_failure("SyntaxError: invalid") == "SYNTAX_ERROR"
    assert auto_heal_pipeline.classify_failure("ImportError: no mod") == "IMPORT_ERROR"
    assert auto_heal_pipeline.classify_failure("AssertionError: x") == "ASSERTION_ERROR"
    assert auto_heal_pipeline.classify_failure("oops", exit_code=1) == "RUNTIME_ERROR"
    assert auto_heal_pipeline.classify_failure("ok", exit_code=0) == "NONE"

    assert "-m pytest" in str(auto_heal_pipeline.normalize_test_command("pytest"))
    assert "-m pytest -q" in str(auto_heal_pipeline.normalize_test_command("pytest -q"))
    assert auto_heal_pipeline.normalize_test_command(["pytest", "-q"])[-2:] == ["pytest", "-q"]
    assert auto_heal_pipeline.normalize_test_command(["python", "a.py"]) == ["python", "a.py"]

    missing_slice = auto_heal_pipeline.KarpathySlicer.slice_file(tmp_path / "nope.py", 1)
    assert missing_slice.content == "<file not found>"
    bad_ast_slice = auto_heal_pipeline.KarpathySlicer.slice_source("def broken(:", target_line=1)
    assert bad_ast_slice.function_name is None

    tgt = tmp_path / "svc_multi.py"
    tgt.write_text("A = 0\nB = 0\n", encoding="utf-8")
    tst = tmp_path / "test_svc_multi.py"
    tst.write_text(
        "import svc_multi\n"
        "def test_a():\n    assert svc_multi.A == 1\n"
        "def test_b():\n    assert svc_multi.B == 1\n",
        encoding="utf-8",
    )
    pipe = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    pipe.bridge = _InProcessPytestBridge(tmp_path, tst, tgt)

    def multi_step_repair(loc_item: OchiaiBridgeLocation, cycle: int) -> bool:
        if cycle == 1:
            tgt.write_text("A = 1\nB = 0\n", encoding="utf-8")
        else:
            tgt.write_text("A = 1\nB = 1\n", encoding="utf-8")
        return True

    rep_multi = pipe.run_pipeline(test_cmd="pytest", target_file=tgt, repair_callback=multi_step_repair)
    assert rep_multi.success is True and rep_multi.cycles_used == 2

    def crash_repair(loc_item: OchiaiBridgeLocation, cycle: int) -> bool:
        raise RuntimeError("callback failure")

    tgt.write_text("A = 0\nB = 0\n", encoding="utf-8")
    pipe_budget = AutoHealPipeline(cwd=tmp_path, max_cycles=1)
    pipe_budget.bridge = _InProcessPytestBridge(tmp_path, tst, tgt)
    rep_fail = pipe_budget.run_pipeline(test_cmd="pytest", target_file=tgt, repair_callback=crash_repair)
    assert rep_fail.success is False and rep_fail.rolled_back is True and rep_fail.cycles_used == 1

    empty_ws = tmp_path / "empty_cli_ws"
    empty_ws.mkdir()
    rc_empty, out_empty, _ = call_script_main_captured(
        auto_heal_pipeline, ["--cwd", str(empty_ws), "--json"]
    )
    assert rc_empty == 0 and json.loads(out_empty)["cycles_used"] == 0

    stg_ws = tmp_path / "stg_cli_ws"
    (stg_ws / ".staging").mkdir(parents=True)
    (stg_ws / ".staging" / "demo.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        AutoHealPipeline,
        "run_pipeline",
        lambda self, **kw: AutoHealSessionReport(
            success=False,
            cycles_used=1,
            max_cycles=1,
            initial_failed=1,
            final_failed=1,
            fault_location="demo.py:1",
            error_type="AssertionError",
            rolled_back=True,
            message="Mocked CLI failure.",
        ),
    )
    rc_stg, out_stg, _ = call_script_main_captured(auto_heal_pipeline, ["--cwd", str(stg_ws)])
    assert rc_stg == 1 and "Last detected fault" in out_stg

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.1.0-FastHealing - Permanent Unit Test Suite for Auto-Heal Pipeline
Module: test_auto_heal_pipeline.py
Author: NK-QA-Engineer & NK-Oracle-Evaluator

Zero-Mock permanent test suite covering:
1. Pytest output parsing and SBFL Ochiai suspiciousness computation (<80 tok payload).
2. Snapshot creation, SHA-256 hashing, and atomic rollback.
3. Strict Monotonic Fitness Gate (IMPROVED vs REGRESSION vs PASSED).
4. AutoHealPipeline clean build execution (cycle 0 exit).
5. AutoHealPipeline healing flow with repair callback and PATCH_NOTES.md emission.
6. AutoHealPipeline regression rejection and circuit breaker rollback.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

_workspace_root = Path(__file__).resolve().parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

def _import_module(mod_name: str):
    staging_file = _workspace_root / ".staging" / "scripts" / f"{mod_name}.py"
    prod_file = _workspace_root / "scripts" / f"{mod_name}.py"
    target = staging_file if staging_file.exists() else prod_file
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

sbfl_pytest_bridge = _import_module("sbfl_pytest_bridge")
healing_snapshot_rollback = _import_module("healing_snapshot_rollback")
auto_heal_pipeline = _import_module("auto_heal_pipeline")

SBFLPytestBridge = sbfl_pytest_bridge.SBFLPytestBridge
PytestRunSummary = sbfl_pytest_bridge.PytestRunSummary
OchiaiBridgeLocation = sbfl_pytest_bridge.OchiaiBridgeLocation

HealingSnapshotManager = healing_snapshot_rollback.HealingSnapshotManager
FitnessVerdict = healing_snapshot_rollback.FitnessVerdict

AutoHealPipeline = auto_heal_pipeline.AutoHealPipeline
AutoHealSessionReport = auto_heal_pipeline.AutoHealSessionReport


def test_sbfl_pytest_bridge_parsing_and_ochiai(tmp_path: Path):
    """Verify Pytest parsing, Ochiai score calculation and <80 tok payload."""
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
    summary = bridge.parse_pytest_output(stdout=sample_stdout, stderr="", exit_code=1, duration_sec=0.05)

    assert summary.exit_code == 1
    assert summary.failed_count == 1
    assert summary.passed_count == 1
    assert summary.total_tests == 2
    assert "tests/test_math.py::test_division" in summary.failed_test_names
    assert "tests/test_math.py::test_addition" in summary.passed_test_names

    loc = bridge.extract_failure_location(summary, target_file_hint="src/math_ops.py")
    assert loc is not None
    assert "math_ops.py" in loc.file_path
    assert loc.line_number == 15
    assert loc.error_type == "ZeroDivisionError"
    assert "division by zero" in loc.error_message
    assert loc.suspiciousness == 1.0

    payload_str = loc.render_payload_json()
    payload = json.loads(payload_str)
    assert "math_ops.py:15" in payload["loc"]
    assert "ZeroDivisionError" in payload["err"]
    # Verify strict < 80 tokens length (JSON string < 320 chars)
    assert len(payload_str) < 320


def test_healing_snapshot_and_rollback(tmp_path: Path):
    """Verify snapshot creation, file modifications and atomic rollback."""
    mgr = HealingSnapshotManager(base_temp_dir=tmp_path / "snapshots")
    target_file = tmp_path / "module.py"
    target_file.write_text("def run():\n    return 42\n", encoding="utf-8")

    snap_id = mgr.create_snapshot([target_file])
    assert snap_id in mgr.active_snapshots
    bundle = mgr.active_snapshots[snap_id]
    assert str(target_file) in bundle.files

    # Modify file
    target_file.write_text("def run():\n    return 999  # MODIFIED\n", encoding="utf-8")
    assert "999" in target_file.read_text(encoding="utf-8")

    # Rollback
    status = mgr.rollback(snap_id)
    assert status[str(target_file)] is True
    assert "return 42" in target_file.read_text(encoding="utf-8")
    assert "999" not in target_file.read_text(encoding="utf-8")

    mgr.cleanup(snap_id)
    assert snap_id not in mgr.active_snapshots


def test_fitness_gate_monotonic_rules(tmp_path: Path):
    """Verify Strict Monotonic Fitness Gate branches."""
    mgr = HealingSnapshotManager(base_temp_dir=tmp_path / "snapshots")

    # 1. All passed
    r1 = mgr.evaluate_fitness(current_passed=5, current_failed=0, prev_passed=4, prev_failed=1, exit_code=0)
    assert r1.verdict == FitnessVerdict.PASSED

    # 2. Improved (failures decreased)
    r2 = mgr.evaluate_fitness(current_passed=4, current_failed=1, prev_passed=3, prev_failed=2, exit_code=1)
    assert r2.verdict == FitnessVerdict.IMPROVED

    # 3. Regression: failures increased
    r3 = mgr.evaluate_fitness(current_passed=3, current_failed=3, prev_passed=3, prev_failed=2, exit_code=1)
    assert r3.verdict == FitnessVerdict.REGRESSION

    # 4. Regression: passed tests decreased
    r4 = mgr.evaluate_fitness(current_passed=2, current_failed=2, prev_passed=3, prev_failed=2, exit_code=1)
    assert r4.verdict == FitnessVerdict.REGRESSION


def test_auto_heal_pipeline_clean_flow(tmp_path: Path):
    """Verify clean build exits immediately with cycle 0."""
    test_script = tmp_path / "test_ok.py"
    test_script.write_text("def test_always_pass():\n    assert True\n", encoding="utf-8")

    target_file = tmp_path / "app.py"
    target_file.write_text("VAL = 100\n", encoding="utf-8")

    pipeline = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    cmd = f'"{sys.executable}" -m pytest "{test_script}" -v'
    report = pipeline.run_pipeline(test_cmd=cmd, target_file=target_file)

    assert report.success is True
    assert report.cycles_used == 0
    assert report.initial_failed == 0
    assert report.final_failed == 0
    assert "Clean build" in report.message


def test_auto_heal_pipeline_repair_and_patch_note(tmp_path: Path):
    """Verify healing flow: detects failure, applies repair callback, passes, emits patch note."""
    target_code = tmp_path / "calc.py"
    target_code.write_text("def calc_div(a, b):\n    return a / b\n", encoding="utf-8")

    test_code = tmp_path / "test_calc.py"
    test_code.write_text(
        "import calc\n"
        "def test_div_ok():\n"
        "    assert calc.calc_div(10, 2) == 5\n"
        "def test_div_zero():\n"
        "    assert calc.calc_div(10, 0) == 0\n",
        encoding="utf-8",
    )

    pipeline = AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    cmd = f'"{sys.executable}" -m pytest "{test_code}" -v'

    def repair_callback(loc: OchiaiBridgeLocation, cycle: int) -> bool:
        # Fix the zero division bug
        fixed_code = "def calc_div(a, b):\n    if b == 0:\n        return 0\n    return a / b\n"
        target_code.write_text(fixed_code, encoding="utf-8")
        return True

    report = pipeline.run_pipeline(test_cmd=cmd, target_file=target_code, repair_callback=repair_callback)

    assert report.success is True
    assert report.cycles_used == 1
    assert report.initial_failed == 1
    assert report.final_failed == 0
    assert report.patch_note_line is not None
    assert "[AUTO-HEALED]" in report.patch_note_line
    assert "ZeroDivisionError" in report.patch_note_line
    assert "calc.py" in report.patch_note_line
    assert "return 0" in target_code.read_text(encoding="utf-8")


def test_auto_heal_pipeline_regression_rollback(tmp_path: Path):
    """Verify regression triggers rollback and circuit breaker exhausts cleanly."""
    target_code = tmp_path / "fragile.py"
    target_code.write_text("X = 1\n", encoding="utf-8")

    test_code = tmp_path / "test_fragile.py"
    test_code.write_text(
        "import fragile\n"
        "def test_one():\n"
        "    assert fragile.X == 2\n",  # Initially fails
        encoding="utf-8",
    )

    pipeline = AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    cmd = f'"{sys.executable}" -m pytest "{test_code}" -v'

    def bad_repair_callback(loc: OchiaiBridgeLocation, cycle: int) -> bool:
        # Makes syntax error to cause regression
        target_code.write_text("BROKEN SYNTAX @@@ ###\n", encoding="utf-8")
        return True

    report = pipeline.run_pipeline(test_cmd=cmd, target_file=target_code, repair_callback=bad_repair_callback)

    assert report.success is False
    assert report.rolled_back is True
    # Verify rollback restored the original valid code
    assert target_code.read_text(encoding="utf-8") == "X = 1\n"
    assert "Rollback to original state" in report.message

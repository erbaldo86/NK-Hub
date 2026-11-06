# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per quality_baseline_manager.py di Nexus Keystone v3.3.0.
Modulo: tests/test_quality_baseline_manager.py.
Valida BS-02 fail-closed, il rifiuto regressioni Ratchet, GT-13 CLI e la soglia GT-68.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_baseline_module():
    """Carica il modulo quality_baseline_manager dando priorita a .staging/scripts."""
    staging_target = (
        _workspace_root / ".staging" / "scripts" / "quality_baseline_manager.py"
    )
    prod_target = _workspace_root / "scripts" / "quality_baseline_manager.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(
        "quality_baseline_manager", str(target)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quality_baseline_manager"] = mod
    spec.loader.exec_module(mod)
    return mod, target


baseline_mod, _BASELINE_SCRIPT = _load_baseline_module()
load_baseline = baseline_mod.load_baseline
check_baseline_compliance = baseline_mod.check_baseline_compliance
update_baseline_metrics = baseline_mod.update_baseline_metrics


def test_baseline_fail_closed_on_corrupted_json(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """1. Verifica BS-02 fail-closed su JSON corrotto, rifiuto Ratchet e CLI GT-13."""
    bad_file = tmp_path / "corrupted_baseline.json"
    bad_file.write_text("{corrupted_baseline: true", encoding="utf-8")

    with pytest.raises(ValueError):
        load_baseline(str(bad_file))

    res = check_baseline_compliance(str(bad_file), {"unit_tests_total": 68})
    assert res["verdict"] == "FAIL"
    assert res["status"] == "ERROR"
    assert bad_file.read_text(encoding="utf-8") == "{corrupted_baseline: true"

    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "3.3.0",
        "metrics": {
            "unit_tests_total": 100,
            "unit_tests_passed": 100,
            "unit_tests_pass_rate": 100.0,
            "sast_critical_violations": 0,
        },
        "invariants": {"require_100_percent_test_pass": True},
        "history": [],
    }
    baseline_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    regressed = {
        "unit_tests_total": 95,
        "unit_tests_passed": 95,
        "unit_tests_pass_rate": 100.0,
        "sast_critical_violations": 0,
    }
    res_reg = update_baseline_metrics(str(baseline_file), regressed)
    assert res_reg["verdict"] == "FAIL"
    assert res_reg["status"] == "REJECTED"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_baseline_manager.py",
            "--file",
            str(baseline_file),
            "--update",
            json.dumps(regressed),
        ],
    )
    assert baseline_mod.main() == 1

    monkeypatch.setattr(
        sys,
        "argv",
        ["quality_baseline_manager.py", "--file", str(baseline_file), "--check-only"],
    )
    assert baseline_mod.main() == 0


def test_baseline_lower_is_better_sast_and_rsi_delta_rejection(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """2. Verifica il rifiuto su sast_critical_violations/rsi_residual_delta e la ricalibrazione GT-68."""
    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "3.3.0",
        "metrics": {
            "total_golden_tests": 123,
            "unit_tests_total": 123,
            "unit_tests_passed": 123,
            "unit_tests_pass_rate": 100.0,
            "sast_critical_violations": 0,
            "rsi_residual_delta": 0,
        },
        "invariants": {"require_100_percent_test_pass": True},
        "history": [],
    }
    baseline_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    sast_regressed = {
        "unit_tests_total": 123,
        "unit_tests_passed": 123,
        "sast_critical_violations": 1,
        "rsi_residual_delta": 0,
    }
    assert check_baseline_compliance(str(baseline_file), sast_regressed)["verdict"] == "FAIL"

    delta_regressed = {
        "unit_tests_total": 123,
        "unit_tests_passed": 123,
        "sast_critical_violations": 0,
        "rsi_residual_delta": 5,
    }
    assert check_baseline_compliance(str(baseline_file), delta_regressed)["verdict"] == "FAIL"

    monkeypatch.setattr(
        sys,
        "argv",
        ["quality_baseline_manager.py", "--file", str(baseline_file), "--recalibrate"],
    )
    assert baseline_mod.main() == 0
    recal_loaded = load_baseline(str(baseline_file))
    assert recal_loaded["metrics"]["total_golden_tests"]["value"] == 68

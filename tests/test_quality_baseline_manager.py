# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_quality_baseline_manager.py
Valida il comportamento fail-closed su JSON corrotto e il rifiuto regressioni Ratchet.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import pytest

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_baseline_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "quality_baseline_manager.py"
    prod_target = _workspace_root / "scripts" / "quality_baseline_manager.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("quality_baseline_manager", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quality_baseline_manager"] = mod
    spec.loader.exec_module(mod)
    return mod, target


baseline_mod, _BASELINE_SCRIPT = _load_baseline_module()
load_baseline = baseline_mod.load_baseline
check_baseline_compliance = baseline_mod.check_baseline_compliance
update_baseline_metrics = baseline_mod.update_baseline_metrics


def test_baseline_fail_closed_on_corrupted_json(tmp_path: Path) -> None:
    """1. Verifica che un JSON corrotto sollevi errore senza sovrascrivere il file."""
    bad_file = tmp_path / "quality_baseline.json"
    bad_file.write_text("{corrupted_baseline: true", encoding="utf-8")

    with pytest.raises(ValueError):
        load_baseline(bad_file)

    res = check_baseline_compliance(bad_file, {"unit_tests_total": 100})
    assert res["verdict"] == "FAIL"
    assert res["status"] == "ERROR"
    assert bad_file.read_text(encoding="utf-8") == "{corrupted_baseline: true"


def test_baseline_ratchet_regression_rejection_exit_1(tmp_path: Path) -> None:
    """2. Verifica il rifiuto delle regressioni Ratchet con codice di uscita 1."""
    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "3.0.0",
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
    res = update_baseline_metrics(baseline_file, regressed)
    assert res["verdict"] == "FAIL"
    assert res["status"] == "REJECTED"

    proc = subprocess.run(
        [
            sys.executable,
            str(_BASELINE_SCRIPT),
            "--file",
            str(baseline_file),
            "--update",
            json.dumps(regressed),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_baseline_lower_is_better_sast_and_rsi_delta_rejection(tmp_path: Path) -> None:
    """3. Verifica che un aumento di sast_critical_violations o rsi_residual_delta venga respinto."""
    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "3.1.0",
        "metrics": {
            "unit_tests_total": 108,
            "unit_tests_passed": 108,
            "unit_tests_pass_rate": 100.0,
            "sast_critical_violations": 0,
            "rsi_residual_delta": 0,
        },
        "invariants": {"require_100_percent_test_pass": True},
        "history": [],
    }
    baseline_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    sast_regressed = {
        "unit_tests_total": 108,
        "unit_tests_passed": 108,
        "unit_tests_pass_rate": 100.0,
        "sast_critical_violations": 1,
        "rsi_residual_delta": 0,
    }
    res_sast = check_baseline_compliance(baseline_file, sast_regressed)
    assert res_sast["verdict"] == "FAIL"

    delta_regressed = {
        "unit_tests_total": 108,
        "unit_tests_passed": 108,
        "unit_tests_pass_rate": 100.0,
        "sast_critical_violations": 0,
        "rsi_residual_delta": 5,
    }
    res_delta = check_baseline_compliance(baseline_file, delta_regressed)
    assert res_delta["verdict"] == "FAIL"


# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_preflight_health_check.py
Valida il comportamento fail-closed di preflight_health_check.py e la modalita' check-only.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_preflight_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "preflight_health_check.py"
    prod_target = _workspace_root / "scripts" / "preflight_health_check.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("preflight_health_check", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["preflight_health_check"] = mod
    spec.loader.exec_module(mod)
    return mod, target


preflight_mod, _PREFLIGHT_SCRIPT = _load_preflight_module()
PreflightHealthChecker = preflight_mod.PreflightHealthChecker


def test_preflight_corrupted_baseline_fails_even_with_autofix(tmp_path: Path) -> None:
    """1. Verifica che una baseline corrotta causi FAIL ed exit 1 anche con auto_fix attivo."""
    for d in [".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests", ".staging"]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)

    baseline_file = tmp_path / "nk_tracking" / "quality_baseline.json"
    baseline_file.write_text("{CORRUPTED_JSON_PAYLOAD", encoding="utf-8")

    checker = PreflightHealthChecker(workspace_root=tmp_path)
    report = checker.run_full_check(auto_fix=True)

    assert report["status"] == "FAIL"
    assert report["checks"]["baseline_alignment"]["passed"] is False
    assert baseline_file.read_text(encoding="utf-8") == "{CORRUPTED_JSON_PAYLOAD"

    proc = subprocess.run(
        [sys.executable, str(_PREFLIGHT_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_preflight_check_only_cli_mode(tmp_path: Path) -> None:
    """2. Verifica che --check-only non crei file o directory mancanti sul disco."""
    for d in [".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests"]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)

    baseline_file = tmp_path / "nk_tracking" / "quality_baseline.json"
    baseline_file.write_text(
        json.dumps({"_version": "3.0.0", "metrics": {"skills_audited": 16, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(_PREFLIGHT_SCRIPT), "--root", str(tmp_path), "--check-only"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert not (tmp_path / ".staging").exists()
    assert not (tmp_path / "nk_tracking" / "anchor" / "session_anchor.jsonl").exists()
    data = json.loads(proc.stdout)
    assert data["status"] == "FAIL"

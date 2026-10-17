# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per preflight_health_check.py di Nexus Keystone v3.3.0.
Modulo: tests/test_preflight_health_check.py.
Valida il comportamento fail-closed su baseline corrotta e la modalita check-only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_preflight_module():
    """Carica il modulo preflight_health_check dando priorita a .staging/scripts."""
    staging_target = (
        _workspace_root / ".staging" / "scripts" / "preflight_health_check.py"
    )
    prod_target = _workspace_root / "scripts" / "preflight_health_check.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("preflight_health_check", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["preflight_health_check"] = mod
    spec.loader.exec_module(mod)
    return mod, target


preflight_mod, _PREFLIGHT_SCRIPT = _load_preflight_module()
PreflightHealthChecker = preflight_mod.PreflightHealthChecker


def test_preflight_corrupted_baseline_fails_even_with_autofix(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """1. Verifica il blocco fail-closed su baseline corrotta e il flag --check-only."""
    corrupt_root = tmp_path / "corrupt_ws"
    for d in [
        ".agents/skills",
        "nk_genome",
        "nk_tracking",
        "scripts",
        "tests",
        ".staging",
    ]:
        (corrupt_root / d).mkdir(parents=True, exist_ok=True)

    baseline_file = corrupt_root / "nk_tracking" / "quality_baseline.json"
    baseline_file.write_text("{CORRUPTED_JSON_PAYLOAD", encoding="utf-8")

    checker = PreflightHealthChecker(workspace_root=corrupt_root)
    report = checker.run_full_check(auto_fix=True)
    assert report["status"] == "FAIL"
    assert report["checks"]["baseline_alignment"]["passed"] is False
    assert baseline_file.read_text(encoding="utf-8") == "{CORRUPTED_JSON_PAYLOAD"

    readonly_root = tmp_path / "readonly_ws"
    for d in [".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests"]:
        (readonly_root / d).mkdir(parents=True, exist_ok=True)
    (readonly_root / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps(
            {
                "_version": "3.3.0",
                "metrics": {
                    "skills_audited": 16,
                    "crv_macro_phases": 4,
                    "unit_tests_pass_pct": 100.0,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv", ["preflight_health_check.py", "--root", str(readonly_root), "--check-only"]
    )
    rc = preflight_mod.main()
    assert rc == 1
    assert not (readonly_root / ".staging").exists()
    assert not (
        readonly_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    ).exists()

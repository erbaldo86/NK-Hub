# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_env_capability_probe.py
Valida la separazione tra core_hub_modules e optional_app_modules e l'invariante GT-09.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_probe_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "env_capability_probe.py"
    prod_target = _workspace_root / "scripts" / "env_capability_probe.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("env_capability_probe", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["env_capability_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


probe_mod = _load_probe_module()
probe_environment = probe_mod.probe_environment


def test_env_probe_core_vs_optional_separation_and_gt09_invariance() -> None:
    """1. Verifica la separazione tra moduli core Hub e opzionali preservando total_probed=15."""
    data = probe_environment()
    assert data["summary"]["total_probed"] == 15
    assert "core_hub_modules" in data
    assert "optional_app_modules" in data
    assert "pydantic" in data["core_hub_modules"]
    assert "pytest" in data["core_hub_modules"]
    assert "psutil" in data["core_hub_modules"]
    assert "fastapi" in data["optional_app_modules"]
    assert data["summary"]["all_core_hub_available"] is True
    assert data["summary"]["status"] == "PASS"

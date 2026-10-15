# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_external_scaffolder.py
Valida il blocco di isolamento [RULE-PROJECT-ISOLATION] e la generazione della Tetralogia.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
import pytest

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_scaffolder_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "external_project_scaffolder.py"
    prod_target = _workspace_root / "scripts" / "external_project_scaffolder.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("external_project_scaffolder", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["external_project_scaffolder"] = mod
    spec.loader.exec_module(mod)
    return mod


scaffolder_mod = _load_scaffolder_module()
ExternalProjectScaffolder = scaffolder_mod.ExternalProjectScaffolder


def test_external_scaffolder_rejects_hub_internal_path() -> None:
    """1. Verifica che un percorso interno a NK-Hub sollevi immediatamente ValueError."""
    forbidden_target = _workspace_root / f"forbidden_internal_app_{uuid.uuid4().hex[:6]}"
    with pytest.raises(ValueError) as exc_info:
        ExternalProjectScaffolder(project_name="ForbiddenApp", target_dir=forbidden_target)
    assert "RULE-PROJECT-ISOLATION" in str(exc_info.value)
    assert not forbidden_target.exists()


def test_external_scaffolder_generates_full_ddd_and_tetralogy(tmp_path: Path) -> None:
    """2. Verifica la creazione completa dell'albero DDD e della Tetralogia Sovrana."""
    ext_dir = tmp_path / "ExternalCleanProject"
    scaffolder = ExternalProjectScaffolder(project_name="ExternalCleanProject", target_dir=ext_dir)
    report = scaffolder.scaffold()

    assert report["status"] == "SUCCESS"
    for tetralogy_file in [
        "concept_map.md",
        "structural_tree.md",
        "implementation_plan.md",
        "repo_map.md",
    ]:
        assert (ext_dir / "nk_genome" / tetralogy_file).exists(), f"Missing {tetralogy_file}"
    assert (ext_dir / "src" / "core" / "__init__.py").exists()
    assert (ext_dir / "src" / "api" / "__init__.py").exists()
    assert (ext_dir / "tests" / "test_ast_purity.py").exists()

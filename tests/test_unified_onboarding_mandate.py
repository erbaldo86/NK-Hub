# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock per Unified Onboarding Mandate di Nexus Keystone v3.3.0.
Modulo: tests/test_unified_onboarding_mandate.py.
Valida la guardia GT-08 su AGENTS.md, NK-Master-Hub, NK-Session-Controller e il bootstrap.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_test_file = Path(__file__).resolve()
if _test_file.parent.name == "tests" and _test_file.parent.parent.name == ".staging":
    _repo_root = _test_file.parent.parent.parent
else:
    _repo_root = _test_file.parent.parent

if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _resolve_doc(rel_path: str) -> Path:
    """Risolve un file di documentazione dando priorita a .staging/."""
    stg = _repo_root / ".staging" / rel_path
    if stg.exists():
        return stg
    return _repo_root / rel_path


def test_agents_md_rule_00_5_definition() -> None:
    """1. Verifica la codifica GT-08 in AGENTS.md, NK-Master-Hub e NK-Session-Controller."""
    agents_file = _resolve_doc(".agents/AGENTS.md")
    assert agents_file.exists()
    content = agents_file.read_text(encoding="utf-8")

    assert "[RULE-00.5]" in content
    assert "UNIFIED_ONBOARDING_DASHBOARD_MANDATE" in content

    required_triggers = [
        "avvia ambiente nk",
        "avvia nk hub",
        "avvia nk",
        "avvia hub",
        "start nk",
        "start hub",
        "attiva nk",
        "attiva ambiente nk",
    ]
    content_lower = content.lower()
    for trigger in required_triggers:
        assert trigger in content_lower

    assert "fast-stat" in content_lower
    assert "120" in content
    assert "[0]" in content and "[14]" in content

    hub_file = _resolve_doc(".agents/skills/NK-Master-Hub/SKILL.md")
    hub_content = hub_file.read_text(encoding="utf-8")
    for i in range(15):
        assert f"[{i}]" in hub_content
    hub_lower = hub_content.lower()
    assert (
        "selezione rapida" in hub_lower
        or "modalità diretta" in hub_lower
        or "modalita' diretta" in hub_lower
    )
    assert "goal-driven" in hub_lower or "linguaggio naturale" in hub_lower

    ctrl_file = _resolve_doc(".agents/skills/NK-Session-Controller/SKILL.md")
    ctrl_content = ctrl_file.read_text(encoding="utf-8")
    assert "10. UNIFIED_ONBOARDING_COMPLIANCE" in ctrl_content
    assert "[RULE-00.5]" in ctrl_content or "fast-stat" in ctrl_content.lower()


def test_session_bootstrap_fast_stat_execution() -> None:
    """2. Esegue programmaticamente scripts/nk_session_bootstrap.py e verifica esito PASS."""
    staging_bootstrap = _repo_root / ".staging" / "scripts" / "nk_session_bootstrap.py"
    prod_bootstrap = _repo_root / "scripts" / "nk_session_bootstrap.py"
    bootstrap_target = (
        staging_bootstrap if staging_bootstrap.exists() else prod_bootstrap
    )
    assert bootstrap_target.exists()

    spec = importlib.util.spec_from_file_location(
        "nk_session_bootstrap", str(bootstrap_target)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bootstrap_inst = mod.NKSessionBootstrap(workspace_root=_repo_root)
    result = bootstrap_inst.run_bootstrap(fast_stat=True)
    assert isinstance(result, dict)
    assert result.get("status") == "PASS"
    assert "checks" in result

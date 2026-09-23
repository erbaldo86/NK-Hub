# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.5.2-Hardened - Permanent Test Suite for Unified Onboarding Mandate
Module: test_unified_onboarding_mandate.py
Author: NK-Python-Async-Builder & NK-Oracle-Evaluator
Implements: [RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE & [RULE-01.10] PERMANENT_TEST_SUITE_MANDATE

Permanent Zero-Mock Pytest Suite covering:
1. test_agents_md_rule_00_5_definition:
   - Validates existence of [RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE in .agents/AGENTS.md.
   - Asserts presence of all mandatory verbal triggers ("avvia ambiente nk", "avvia nk hub",
     "avvia nk", "avvia hub", "start nk", "start hub", "attiva nk", "attiva ambiente nk").
   - Asserts presence of Fast-Stat gate constraint (< 120 ms) and all 15 vocational nodes ([0]-[14]).
2. test_master_hub_15_nodes_and_guidance:
   - Asserts .agents/skills/NK-Master-Hub/SKILL.md defines all 15 nodes [0] to [14].
   - Asserts presence of two-way operational footer guidance (Quick Selection vs Goal-Driven / Natural Language).
3. test_session_controller_boundary_10:
   - Asserts .agents/skills/NK-Session-Controller/SKILL.md enforces strict boundary 10 UNIFIED_ONBOARDING_COMPLIANCE.
4. test_session_bootstrap_fast_stat_execution:
   - Programmatically executes scripts/nk_session_bootstrap.py and verifies PASS verdict.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Determine repository root reliably whether executed from .staging/tests or tests
_test_file = Path(__file__).resolve()
if _test_file.parent.name == "tests" and _test_file.parent.parent.name == ".staging":
    _repo_root = _test_file.parent.parent.parent
else:
    _repo_root = _test_file.parent.parent

if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def test_agents_md_rule_00_5_definition() -> None:
    """Verifica la corretta codifica di [RULE-00.5] in .agents/AGENTS.md."""
    agents_file = _repo_root / ".agents" / "AGENTS.md"
    assert agents_file.exists(), f"AGENTS.md not found at {agents_file}"
    content = agents_file.read_text(encoding="utf-8")

    # 1. Regola presente
    assert "[RULE-00.5]" in content, "[RULE-00.5] missing from AGENTS.md"
    assert "UNIFIED_ONBOARDING_DASHBOARD_MANDATE" in content, "Rule name missing"

    # 2. Trigger verbali obbligatori
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
        assert trigger in content_lower, f"Mandatory verbal trigger '{trigger}' not found in [RULE-00.5]"

    # 3. Vincolo Fast-Stat (<120 ms)
    assert "fast-stat" in content_lower, "Fast-Stat requirement missing from [RULE-00.5]"
    assert "120" in content, "120 ms constraint missing from [RULE-00.5]"

    # 4. Range nodi [0] - [14]
    assert "[0]" in content and "[14]" in content, "15 nodes range [0]-[14] missing in [RULE-00.5]"


def test_master_hub_15_nodes_and_guidance() -> None:
    """Verifica che NK-Master-Hub contenga i 15 nodi e la guida d'uso a due vie."""
    skill_file = _repo_root / ".agents" / "skills" / "NK-Master-Hub" / "SKILL.md"
    assert skill_file.exists(), f"NK-Master-Hub/SKILL.md not found at {skill_file}"
    content = skill_file.read_text(encoding="utf-8")

    # 1. Tutti i 15 nodi canonici [0] a [14]
    for i in range(15):
        assert f"[{i}]" in content, f"Vocational node [{i}] missing in NK-Master-Hub dashboard"

    # 2. Guida all'uso a due vie nel footer
    content_lower = content.lower()
    has_direct_selection = "selezione rapida" in content_lower or "modalità diretta" in content_lower
    has_goal_driven = "goal-driven" in content_lower or "linguaggio naturale" in content_lower

    assert has_direct_selection, "Direct selection guidance missing from NK-Master-Hub footer"
    assert has_goal_driven, "Goal-driven / natural language guidance missing from NK-Master-Hub footer"


def test_session_controller_boundary_10() -> None:
    """Verifica che NK-Session-Controller contenga il vincolo 10 UNIFIED_ONBOARDING_COMPLIANCE."""
    skill_file = _repo_root / ".agents" / "skills" / "NK-Session-Controller" / "SKILL.md"
    assert skill_file.exists(), f"NK-Session-Controller/SKILL.md not found at {skill_file}"
    content = skill_file.read_text(encoding="utf-8")

    assert "10. UNIFIED_ONBOARDING_COMPLIANCE" in content, (
        "Boundary 10 UNIFIED_ONBOARDING_COMPLIANCE missing in NK-Session-Controller/SKILL.md"
    )
    assert "[RULE-00.5]" in content or "fast-stat" in content.lower(), (
        "Reference to [RULE-00.5] or Fast-Stat missing in Boundary 10"
    )


def test_session_bootstrap_fast_stat_execution() -> None:
    """Esegue programmaticamente scripts/nk_session_bootstrap.py e verifica esito PASS."""
    staging_bootstrap = _repo_root / ".staging" / "scripts" / "nk_session_bootstrap.py"
    prod_bootstrap = _repo_root / "scripts" / "nk_session_bootstrap.py"
    bootstrap_target = staging_bootstrap if staging_bootstrap.exists() else prod_bootstrap
    assert bootstrap_target.exists(), f"Bootstrap script not found at {bootstrap_target}"

    spec = importlib.util.spec_from_file_location("nk_session_bootstrap", str(bootstrap_target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bootstrap_inst = mod.NKSessionBootstrap(workspace_root=_repo_root)
    result = bootstrap_inst.run_bootstrap(fast_stat=True)

    assert isinstance(result, dict), "Bootstrap result must be a dict"
    assert result.get("status") == "PASS", f"Bootstrap failed with status {result.get('status')}: {result.get('issues')}"
    assert "checks" in result, "Bootstrap report must contain 'checks' key"

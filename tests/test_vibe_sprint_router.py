# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_vibe_sprint_router.py
Valida il calcolo reale della profondita' AST e il routing Mode A/B/C.
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


def _load_router_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "vibe_sprint_router.py"
    prod_target = _workspace_root / "scripts" / "vibe_sprint_router.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("vibe_sprint_router", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vibe_sprint_router"] = mod
    spec.loader.exec_module(mod)
    return mod


router_mod = _load_router_module()
VibeSprintRouter = router_mod.VibeSprintRouter


def test_vibe_sprint_router_real_ast_max_depth_and_routing(tmp_path: Path) -> None:
    """1. Verifica il calcolo reale di max_depth AST e la selezione della modalita'."""
    router = VibeSprintRouter(workspace_root=tmp_path)

    simple_code = "def render_btn(label: str) -> str:\n    return f'<button>{label}</button>'\n"
    res_c = router.compute_ast_risk_score(simple_code, filename="simple_ui.py")
    assert res_c["recommended_mode"].lower() == "mode_c"
    assert res_c["max_depth"] == 1

    deep_code = (
        "import subprocess\n"
        "def run_deep(items):\n"
        "    for a in items:\n"
        "        if a > 0:\n"
        "            for b in range(a):\n"
        "                if b % 2 == 0:\n"
        "                    try:\n"
        "                        while b > 1:\n"
        "                            b -= 1\n"
        "                    except Exception:\n"
        "                        pass\n"
    )
    res_deep = router.compute_ast_risk_score(deep_code, filename="deep_core.py")
    assert res_deep["max_depth"] >= 6
    assert res_deep["max_depth"] > res_c["max_depth"]


def test_vibe_sprint_router_load_prewarmed_capsule_and_cli(tmp_path: Path) -> None:
    """2. Verifica il caricamento di tier1_active_capsule.json e l'integrazione nella micro-spec."""
    mem_dir = tmp_path / "nk_tracking" / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    capsule_file = mem_dir / "tier1_active_capsule.json"
    capsule_file.write_text(
        '{"status": "OK", "capsule_text": "Invariante Zero-Mock attivo", "token_count": 12, "token_cap": 350, "entries": []}',
        encoding="utf-8",
    )

    router = VibeSprintRouter(workspace_root=tmp_path)
    loaded = router.load_prewarmed_capsule()
    assert loaded["status"] == "OK"
    assert "Invariante Zero-Mock attivo" in loaded["capsule_text"]

    risk = router.compute_ast_risk_score("def f(x: int) -> int:\n    return x + 1\n", "f.py")
    spec = router.generate_inline_micro_spec("f.py", "Increment value", risk)
    assert "Tier-1 Capsule: Invariante Zero-Mock attivo" in spec


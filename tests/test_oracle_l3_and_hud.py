# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_oracle_l3_and_hud.py
Valida i void tag HTML5 e percorsi Windows in oracle_evaluator_l3.py e micro_hud_renderer.py.
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


def _load_mod(name: str):
    staging_target = _workspace_root / ".staging" / "scripts" / f"{name}.py"
    prod_target = _workspace_root / "scripts" / f"{name}.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


oracle_mod = _load_mod("oracle_evaluator_l3")
hud_mod = _load_mod("micro_hud_renderer")


def test_oracle_l3_void_tags_windows_path_and_micro_hud(tmp_path: Path) -> None:
    """1. Verifica il supporto void tag HTML5, percorsi Windows e rendering Micro-HUD."""
    html_file = tmp_path / "index.html"
    html_content = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><link rel='stylesheet' href='a.css'></head>"
        "<body><main><img src='logo.png' alt='logo'><br><input type='text' id='q'>"
        "<button id='submit_btn'>Invia</button></main></body></html>"
    )
    html_file.write_text(html_content, encoding="utf-8")

    spec_arg = f"{html_file}:#submit_btn:Invia"
    source = oracle_mod.resolve_html_source(spec_arg)
    assert "<!DOCTYPE html>" in source

    evaluator = oracle_mod.DOMOracleEvaluator()
    dom_res = evaluator.evaluate_deltas(spec_arg, html_content)
    assert dom_res.verdict == "PASS"
    assert dom_res.discrepancy_count == 0

    hud = hud_mod.MicroHUDRenderer(version="v3.0", ascii_mode=True)
    hud.set_progress(100)
    hud.set_agent_context("NK-Oracle-Evaluator", "ARCH")
    hud.set_rsi_metrics(delta_k=0.0, fitness_q=100.0)
    line = hud.render(include_extras=True)
    assert "100%" in line
    assert "NK-Oracle-Evaluator" in line
    ipc_state = hud.to_ipc_state(session_id="test_sess")
    assert ipc_state.session_id == "test_sess"
    assert ipc_state.progress_pct == 100.0

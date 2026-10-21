# -*- coding: utf-8 -*-
"""
Nexus Keystone v4.1.0-STE100-Unified
Modulo: test_vibe_sprint_router.py
Valida il calcolo reale della profondita AST, il routing Mode A/B/C/D e il Super Meta-Prompt Gate (WP13).
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
    """1. Verifica il calcolo reale di max_depth AST e la selezione della modalita."""
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


def test_vibe_sprint_router_nominalization_word_boundary_fix() -> None:
    """3. Verifica che sostantivi astratti come implementazione e valutazione non attivino falsi positivi."""
    router = VibeSprintRouter()
    prompt_disc = (
        "Analizza lo stato dell'arte dell'implementazione attuale e fai una valutazione "
        "architetturale di copertura"
    )
    assert router_mod._has_imperative_write_keyword(prompt_disc) is False
    intent = router.classify_prompt_intent(prompt_disc)
    assert intent["recommended_mode"] == "mode_d"
    assert intent["is_discovery"] is True
    assert intent["read_only"] is True
    assert intent["primary_agent"] == "NK-Ideator"

    prompt_write = "Implementa il nuovo contratto in .staging/ e modifica il router"
    assert router_mod._has_imperative_write_keyword(prompt_write) is True
    intent_w = router.classify_prompt_intent(prompt_write)
    assert intent_w["is_discovery"] is False


def test_vibe_sprint_router_stt_normalization_and_anti_loop_exemptions() -> None:
    """4. Verifica la normalizzazione vocale STT su primaLa e le 5 esenzioni anti-loop."""
    router = VibeSprintRouter()
    stt = router.normalize_voice_stt_input(
        "Modifica il file, anzi no analizza primaLa struttura di `myCamelVar` praticamente"
    )
    assert "prima La" in stt["cleaned_prompt"]
    assert "`myCamelVar`" in stt["cleaned_prompt"]
    assert any("primaLa -> prima La" in c for c in stt["voice_corrections_applied"])
    assert len(stt["voice_corrections_applied"]) >= 2

    # 1. Conferme brevi
    assert router.is_gate_exempt("ok") is True
    assert router.is_gate_exempt("Confermo!") is True
    # 2. Trigger onboarding e nodi [0]..[14]
    assert router.is_gate_exempt("avvia nk") is True
    assert router.is_gate_exempt("[14]") is True
    # 3. Proceed
    assert router.is_gate_exempt("Proceed") is True
    assert router.is_gate_exempt("premi proceed") is True
    # 4. Delega sub-agenti con <env_capsule>
    assert router.is_gate_exempt("<env_capsule>\nTEST_RUNNER: pytest\n</env_capsule>") is True
    # 5. Comandi di bypass/toggle
    assert router.is_gate_exempt("!diretto analizza il codice") is True
    assert router.is_gate_exempt("disattiva prompt gate") is True
    # Prompt ordinario non esente
    assert router.is_gate_exempt("Progetta un nuovo modulo asincrono per il router") is False


def test_vibe_sprint_router_meta_prompt_envelope_and_cli() -> None:
    """5. Verifica build_meta_prompt_envelope e i flag CLI --meta-prompt-gate e --no-gate."""
    router = VibeSprintRouter()
    env = router.build_meta_prompt_envelope(
        "Analizza primaLa struttura dell'implementazione; inoltre verifica la valutazione"
    )
    assert env["brief_id"].startswith("IB-")
    assert env["fsm_state"] == "AWAIT_CONFIRM"
    assert env["bypassed"] is False
    assert env["recommended_mode"] == "mode_d"
    assert len(env["intent_hash_sha256"]) == 64
    assert len(env["requirements_r_ids"]) >= 2
    assert env["requirements_r_ids"][0].startswith("R1:")

    env_exempt = router.build_meta_prompt_envelope("ok")
    assert env_exempt["fsm_state"] == "BYPASSED"
    assert env_exempt["bypassed"] is True

    rc1 = router_mod.main(
        ["--meta-prompt-gate", "--prompt", "Analizza primaLa copertura", "--json"]
    )
    assert rc1 == 0
    rc2 = router_mod.main(
        ["--no-gate", "--prompt", "Analizza primaLa copertura", "--json"]
    )
    assert rc2 == 0

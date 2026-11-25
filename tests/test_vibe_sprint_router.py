# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per vibe_sprint_router.py (1.0.0-Generation).
Modulo: tests/test_vibe_sprint_router.py.
Valida profondita AST, routing Mode A/B/C/D, Meta-Prompt Gate, cli_handlers, domain_matcher e Wave 2B.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, List, Tuple

import pytest

try:
    from conftest import WORKSPACE_ROOT, call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, call_script_main_captured, load_nk_script_module

pytestmark = pytest.mark.fast

router_mod = load_nk_script_module("vibe_sprint_router")
transcript_tools_mod = load_nk_script_module("nk_transcript_tools")
VibeSprintRouter = router_mod.VibeSprintRouter


def _assert_ast_depth_and_capsule_spec(tmp_path: Path) -> VibeSprintRouter:
    router = VibeSprintRouter(workspace_root=tmp_path)
    assert VibeSprintRouter.MODE_C_MAX_LOC == 150
    assert router.MODE_C_MAX_LOC == 150

    res_c = router.compute_ast_risk_score("def render_btn(label: str) -> str:\n    return f'<button>{label}</button>'\n", filename="simple_ui.py")
    assert res_c["recommended_mode"].lower() == "mode_c"
    assert res_c["max_depth"] == 1

    deep_code = (
        "import subprocess\ndef run_deep(items):\n    for a in items:\n        if a > 0:\n"
        "            for b in range(a):\n                if b % 2 == 0:\n"
        "                    try:\n                        while b > 1:\n                            b -= 1\n"
        "                    except Exception:\n                        pass\n"
    )
    res_deep = router.compute_ast_risk_score(deep_code, filename="deep_core.py")
    assert res_deep["max_depth"] >= 6
    assert res_deep["max_depth"] > res_c["max_depth"]

    mem_dir = tmp_path / "nk_tracking" / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "tier1_active_capsule.json").write_text(
        '{"status": "OK", "capsule_text": "Invariante Zero-Mock attivo", "token_count": 12, "token_cap": 350, "entries": []}',
        encoding="utf-8",
    )
    router_cap = VibeSprintRouter(workspace_root=tmp_path)
    loaded = router_cap.load_prewarmed_capsule()
    assert loaded["status"] == "OK"
    assert "Invariante Zero-Mock attivo" in loaded["capsule_text"]
    risk = router_cap.compute_ast_risk_score("def f(x: int) -> int:\n    return x + 1\n", "f.py")
    assert "Tier-1 Capsule: Invariante Zero-Mock attivo" in router_cap.generate_inline_micro_spec("f.py", "Increment value", risk)
    return router_cap


def _assert_mode_c_boundary_and_capsule_lint(router: VibeSprintRouter, router_cap: VibeSprintRouter, tmp_path: Path) -> None:
    res_120 = router.classify_prompt_intent("Modifica la funzione di calcolo in modulo.py", changed_lines=120)
    assert res_120["recommended_mode"] == "mode_c"
    assert res_120["fast_bypass_eligible"] is True
    res_200 = router.classify_prompt_intent("Modifica la funzione di calcolo in modulo.py", changed_lines=200)
    assert res_200["recommended_mode"] == "mode_b"
    assert res_200["fast_bypass_eligible"] is False
    assert router.compute_ast_risk_score("\n".join(f"x_{i} = {i}" for i in range(120)), filename="mod_120.py")["mode_eligible"] is True
    assert router.compute_ast_risk_score("\n".join(f"x_{i} = {i}" for i in range(200)), filename="mod_200.py")["mode_eligible"] is False

    capsule = router_cap.generate_env_capsule()
    assert capsule == router_mod.generate_env_capsule(workspace_root=tmp_path)
    assert "ZERO_BLIND_VIEW_FILE:" in capsule
    assert "MAX_WRITE_BATCH:" in capsule
    assert len(capsule) // 4 < 235
    lint_res, lint_code = transcript_tools_mod.lint_prompt_text(f"{capsule}\nOpera come NK-Security-DAST-Auditor e analizza in sola lettura.")
    assert lint_code == 0
    assert lint_res["passed"] is True


def _assert_gate_exemptions_and_cli_bypass(router: VibeSprintRouter, capsys: Any) -> None:
    for prompt_text in (
        "Analizza il bug per cui avvia nk hub mostra un errore",
        "Spiega come funziona il blocco <env_capsule> nei messaggi dei subagent",
        "Vai a controllare i log", "Confermo che il bug esiste",
        "Analizza perche salta gate non viene applicato", "Spiega come disattiva prompt gate agisce sul router",
    ):
        assert router.is_gate_exempt(prompt_text) is False
        env_forced = router.build_meta_prompt_envelope(prompt_text, auto_bypass_readonly=False)
        assert (env_forced["bypassed"], env_forced["fsm_state"]) == (False, "AWAIT_CONFIRM")
        env = router.build_meta_prompt_envelope(prompt_text)
        expected = (True, "BYPASSED") if (env["recommended_mode"] == "mode_d" and env.get("auto_bypass_eligible")) else (False, "AWAIT_CONFIRM")
        assert (env["bypassed"], env["fsm_state"]) == expected

    for valid_confirm in ("Vai pure avanti", "Confermo il piano"):
        assert router.is_gate_exempt(valid_confirm) is True
        assert router.build_meta_prompt_envelope(valid_confirm)["bypassed"] is True

    assert router_mod.main(["--meta-prompt-gate", "Analizza la resilienza del server contro i timeout RPC", "--json"]) == 0
    out_pos = json.loads(capsys.readouterr().out)
    assert "resilienza del server" in out_pos["optimized_meta_prompt"]
    assert (out_pos["fsm_state"], out_pos["gate_mode"], out_pos["bypass_reason"]) == ("BYPASSED", "SINGLE_GATE_MODE_D", "READONLY_MODE_D_BYPASS")

    assert router_mod.main(["--meta-prompt-gate", "--force-gate", "Analizza la resilienza del server contro i timeout RPC", "--json"]) == 0
    out_forced = json.loads(capsys.readouterr().out)
    assert (out_forced["fsm_state"], out_forced["bypassed"]) == ("AWAIT_CONFIRM", False)


def test_vibe_sprint_router_real_ast_max_depth_and_mode_c_boundary(
    tmp_path: Path, capsys: Any
) -> None:
    """1. Verifica max_depth AST, boundary MODE_C_MAX_LOC==150, capsula Tier-1 e CLI posizionale."""
    router = VibeSprintRouter(workspace_root=tmp_path)
    router_cap = _assert_ast_depth_and_capsule_spec(tmp_path)
    _assert_mode_c_boundary_and_capsule_lint(router, router_cap, tmp_path)
    _assert_gate_exemptions_and_cli_bypass(router, capsys)


TECH_BRANDS_AND_IDENTIFIERS: Tuple[str, ...] = (
    "GitHub", "GitLab", "FastAPI", "JavaScript", "TypeScript", "PostgreSQL", "SQLite", "GraphQL",
    "PyTorch", "TensorFlow", "OpenAI", "DeepSeek", "PowerShell", "MacBook", "iPhone", "iPad",
    "OneDrive", "SharePoint", "WordPress", "YouTube", "LinkedIn", "StackOverflow", "PyTest",
    "DevOps", "DataFrame", "AsyncIO", "WebSocket", "Protobuf", "LangChain", "LlamaIndex",
    "AutoGen", "CrewAI", "ChromaDB", "MongoDB", "MariaDB", "DuckDB", "ClickHouse", "RabbitMQ",
    "ZeroMQ", "KeyCloak", "OAuth", "OpenTelemetry", "CloudFlare", "DigitalOcean", "HuggingFace",
    "vibe_sprint_router", "VibeSprintRouter", "compute_ast_risk_score",
    "resolve_intrinsic_vibe_protocols", "build_meta_prompt_envelope",
)


def _assert_discovery_write_intent_and_stt(router: VibeSprintRouter) -> None:
    prompt_disc = "Analizza lo stato dell'arte dell'implementazione attuale e fai una valutazione architetturale di copertura"
    assert router_mod._has_imperative_write_keyword(prompt_disc) is False
    intent = router.classify_prompt_intent(prompt_disc)
    assert (intent["recommended_mode"], intent["is_discovery"], intent["read_only"], intent["primary_agent"]) == ("mode_d", True, True, "NK-Ideator")

    prompt_write = "Implementa il nuovo contratto in .staging/ e modifica il router"
    assert router_mod._has_imperative_write_keyword(prompt_write) is True
    assert router.classify_prompt_intent(prompt_write)["is_discovery"] is False

    stt = router.normalize_voice_stt_input("Modifica il file, anzi no analizza primaLa struttura di `myCamelVar` praticamente")
    assert "prima La" in stt["cleaned_prompt"]
    assert "`myCamelVar`" in stt["cleaned_prompt"]
    assert any("primaLa -> prima La" in c for c in stt["voice_corrections_applied"])
    assert len(stt["voice_corrections_applied"]) >= 2


def _assert_exemptions_and_negations(router: VibeSprintRouter) -> None:
    for exempt in (
        "ok", "Confermo!", "procedi pure", "procedi con il piano", "procedi alla creazione dell'implementation plan",
        "avvia nk", "[9]", "Proceed", "premi proceed", "<env_capsule>\nTEST_RUNNER: pytest\n</env_capsule>",
        "!diretto analizza il codice", "disattiva prompt gate",
    ):
        assert router.is_gate_exempt(exempt) is True
    assert router.is_gate_exempt("Progetta un nuovo modulo asincrono per il router") is False

    long_anzi = "Nel modulo di autenticazione dobbiamo verificare tutti i permessi degli utenti registrati nel database, anzi no solo quelli attivi"
    stt_long = router.normalize_voice_stt_input(long_anzi)
    assert "modulo di autenticazione" in stt_long["cleaned_prompt"]
    assert "solo quelli attivi" in stt_long["cleaned_prompt"]
    assert router_mod._has_imperative_write_keyword("non devi a modificare il codice") is False
    assert router_mod._has_imperative_write_keyword("non voglio assolutamente in alcun modo modificare il codice, analizza solo") is False
    stt_m03 = router.normalize_voice_stt_input("crea un file temporaneo nel progetto, anzi no analizza solo la struttura")
    assert "crea un file" not in stt_m03.get("normalized_text", stt_m03["cleaned_prompt"]).lower()
    assert router.is_gate_exempt("procedi pure con la refactoring architetturale completa di tutti i moduli del sistema") is False
    env_m33 = router_mod.build_meta_prompt_envelope("Spiega cosa fa il modulo X", auto_bypass_readonly=True)
    assert (env_m33["fsm_state"], env_m33["auto_bypass_eligible"]) == ("BYPASSED", True)
    assert router.is_gate_exempt("ok procedi cancella tutto subito") is False
    assert router_mod.is_gate_exempt("ok procedi cancella tutto subito") is False
    assert router.normalize_voice_stt_input("Modifica il file A, anzi no fermati")["cleaned_prompt"] == "fermati"
    assert {"review", "elenca"}.issubset(router_mod.MODE_D_KEYWORDS)


def _assert_brands_and_italian_splits(router: VibeSprintRouter) -> None:
    for brand in TECH_BRANDS_AND_IDENTIFIERS:
        assert brand in router.normalize_voice_stt_input(f"Analizza l'integrazione di {brand} nel modulo core senza regressioni")["cleaned_prompt"]
    for raw_text, expected_split in (
        ("analizza primaLa struttura", "prima La"), ("verifica tuttoIl modulo", "tutto Il"),
        ("controlla ancheLa copertura", "anche La"), ("esegui soloUn test rapido", "solo Un"),
        ("modifica dentroIl file target", "dentro Il"), ("sposta versoLa directory staging", "verso La"),
        ("aggiorna sottoIl limite previsto", "sotto Il"), ("porta oltreIl livello minimo", "oltre Il"),
        ("inserisci senzaUn errore", "senza Un"), ("ottiene cosìUn risultato stabile", "così Un"),
        ("imposta piùUn valore valido", "più Un"), ("trova giàUn record esistente", "già Un"),
    ):
        assert expected_split in router.normalize_voice_stt_input(raw_text)["cleaned_prompt"]


def test_vibe_sprint_router_stt_normalization_brands_and_exemptions() -> None:
    """2. Verifica normalizzazione STT, conservazione 50 brand, negazioni multi-parola ed esenzioni."""
    router = VibeSprintRouter()
    _assert_discovery_write_intent_and_stt(router)
    _assert_exemptions_and_negations(router)
    _assert_brands_and_italian_splits(router)


def _assert_mode_d_envelope_fields(router: VibeSprintRouter) -> None:
    env = router.build_meta_prompt_envelope("Analizza primaLa struttura dell'implementazione; inoltre verifica la valutazione")
    assert (env["fsm_state"], env["bypassed"], env["gate_mode"], env["bypass_reason"], env["recommended_mode"], env["native_subagent"]) == (
        "BYPASSED", True, "SINGLE_GATE_MODE_D", "READONLY_MODE_D_BYPASS", "mode_d", "NK-Arch-Specifier",
    )
    assert env["brief_id"].startswith("IB-")
    assert "Single-Gate: READONLY_MODE_D_BYPASS" in env["optimized_meta_prompt"]
    assert len(env["intent_hash_sha256"]) == 64
    assert len(env["requirements_r_ids"]) >= 2
    assert env["requirements_r_ids"][0].startswith("R1:")

    env_forced = router.build_meta_prompt_envelope("Analizza primaLa struttura dell'implementazione; inoltre verifica la valutazione", auto_bypass_readonly=False)
    assert (env_forced["fsm_state"], env_forced["bypassed"], env_forced["recommended_mode"]) == ("AWAIT_CONFIRM", False, "mode_d")
    assert router.build_meta_prompt_envelope("ok")["bypassed"] is True


def _assert_bandi_intrinsic_protocols(router: VibeSprintRouter) -> None:
    default_res = router.resolve_intrinsic_vibe_protocols("Aggiorna colore pulsante", "mode_c")
    assert ("INTRINSIC_GOAL" in default_res["intrinsic_protocols"], default_res["autonomous_slash_equivalence"]["goal"]) == (True, True)

    bandi_prompt = "Esegui un'analisi approfondita multi-livello del progetto Bandi; inoltre progetta il piano di implementazione e risolvi i difetti fino a convergenza"
    bandi_res = router_mod.resolve_intrinsic_vibe_protocols(bandi_prompt, "mode_a")
    assert bandi_res["intrinsic_protocols"] == ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]
    assert all(bandi_res["autonomous_slash_equivalence"][k] is True for k in ("goal", "boost", "plan"))

    env_bandi = router.build_meta_prompt_envelope(bandi_prompt)
    assert all(p in env_bandi["intrinsic_protocols"] for p in ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"))
    assert "Protocolli Intrinseci Auto-Attivati:" in env_bandi["optimized_meta_prompt"]
    assert env_bandi["optimized_meta_prompt"].startswith("[META-PROMPT L0 | Mode:")


def _assert_t12_standby_and_bandi_protocols(router: VibeSprintRouter) -> None:
    t12_prompt = (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n### 1. Identità e Percorsi Operativi\n"
        "- Workspace: g:/Il mio Drive/Antigravity/NK_Hub\n[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )
    env_t12 = router.build_meta_prompt_envelope(t12_prompt)
    assert (env_t12["fsm_state"], env_t12.get("bypass_reason"), env_t12.get("standby_mode"), env_t12["intrinsic_protocols"]) == (
        "BYPASSED", "STATE_HANDOFF_STANDBY", True, [],
    )
    assert (env_t12["autonomous_slash_equivalence"]["goal"], env_t12["autonomous_slash_equivalence"]["plan"]) == (False, False)
    if hasattr(router, "evaluate_meta_prompt_gate"):
        eval_t12 = router.evaluate_meta_prompt_gate(t12_prompt)
        assert (eval_t12["bypass_reason"], eval_t12["intrinsic_protocols"]) == ("STATE_HANDOFF_STANDBY", [])

    assert router_mod.main(["--meta-prompt-gate", "--prompt", "Analizza primaLa copertura", "--json"]) == 0
    assert router_mod.main(["--no-gate", "--prompt", "Analizza primaLa copertura", "--json"]) == 0
    _assert_bandi_intrinsic_protocols(router)


def test_vibe_sprint_router_meta_prompt_envelope_and_intrinsic_bandi() -> None:
    """3. Verifica build_meta_prompt_envelope, bypass Mode D, standby T12 e protocolli intrinseci Bandi."""
    router = VibeSprintRouter()
    _assert_mode_d_envelope_fields(router)
    _assert_t12_standby_and_bandi_protocols(router)


def _assert_ap10_vector_matrix() -> None:
    for bad_text in (
        "Per ottenere risultati migliori puoi utilizzare anche il comando /goal o /boost oppure digita il comando /plan.",
        "Per approfondire puoi utilizzare anche il comando /goal nel terminale.",
        "Ti consiglio di usare /boost per potenziare la richiesta.",
        "Digita il comando /plan per generare il piano di implementazione.",
        "Puoi invocare /implementation per procedere con i work package.",
        "Usa il comando `/goal` oppure `/boost` per migliorare il prompt.",
    ):
        r_lint = router_mod.lint_nk_prompt(bad_text)
        assert r_lint["passed"] is False
        assert any(v["code"] == "AP-10" for v in r_lint["violations"])
        t_lint, exit_code = transcript_tools_mod.lint_prompt_text(bad_text)
        assert (exit_code, t_lint["passed"]) == (1, False)
        assert any(v["code"] == "AP-10" for v in t_lint["violations"])

    for ok_text in (
        "Nessun agente chiede all'utente di digitare manualmente /goal, /boost, /plan o /implementation (AP-10).\nVieta di dire: puoi utilizzare anche il comando /goal.",
        "È vietato suggerire passivamente di usare il comando /goal o /boost.",
        "Non chiedere mai di invocare /plan: il router attiva INTRINSIC_PLAN autonomamente.",
        "Esegui l'analisi architetturale del modulo e genera l'artefatto implementation_plan.md.",
    ):
        assert not any(v["code"] == "AP-10" for v in router_mod.lint_nk_prompt(ok_text)["violations"])
        assert not any(v["code"] == "AP-10" for v in transcript_tools_mod.lint_prompt_text(ok_text)[0]["violations"])


def _assert_l0_confirm_and_cli_gate(
    router: VibeSprintRouter, prompt_dots: str, env: dict[str, Any], capsys: Any
) -> None:
    env_confirm = router.build_meta_prompt_envelope("procedi")
    assert "INTRINSIC_PLAN" in env_confirm["intrinsic_protocols"]
    assert env_confirm["autonomous_slash_equivalence"]["implementation"] is True
    assert len(env["requirements_r_ids"]) == 2
    assert "PATCH_NOTES.md" in env["requirements_r_ids"][0]
    assert not any(r.startswith("R2: md") for r in env["requirements_r_ids"])

    assert router_mod.main(["--meta-prompt-gate", "--prompt", prompt_dots]) == 0
    captured = capsys.readouterr().out
    assert ("[META-PROMPT-GATE]" in captured, "Specchio Concettuale" in captured) == (True, True)


def _assert_l0_markdown_reqs_and_cli(capsys: Any) -> None:
    router = VibeSprintRouter()
    prompt_dots = "Aggiorna PATCH_NOTES.md e scripts/vibe_sprint_router.py per la release v1.0.0-Generation in .staging; inoltre verifica la suite di test"
    env = router.build_meta_prompt_envelope(prompt_dots)
    md = env["rendered_markdown"]
    assert ("### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]" in md, "Specchio Concettuale" in md) == (True, True)
    for field_name in ("conceptual_mirror", "optimized_meta_prompt", "rendered_markdown"):
        assert ("Brief" in env[field_name], "implementation_plan.md" in env[field_name], "RequestFeedback: true" in env[field_name]) == (True, True, True)
    assert "[MANDATORY-VISIBLE-L0]: Mostra obbligatoriamente questo blocco nel campo content della risposta PRIMA o INSIEME a ask_question (vietato content_len=0)." in md
    assert router_mod.format_meta_prompt_markdown(env) == md
    _assert_l0_confirm_and_cli_gate(router, prompt_dots, env, capsys)


def test_vibe_sprint_router_l0_rendered_markdown_and_ap10_suite(capsys: Any) -> None:
    """4. Verifica guardia AP-10 vettoriale, rendered_markdown L0, clause split e output CLI."""
    _assert_ap10_vector_matrix()
    _assert_l0_markdown_reqs_and_cli(capsys)


def _assert_forensic_write_burst_transcripts(tmp_path: Path) -> None:
    tp_forensic = tmp_path / "transcript_forensic.jsonl"
    tp_forensic.write_text(
        "\n".join([
            json.dumps({"step_index": 12, "source": "MODEL", "status": "ERROR", "output": "GetFileAttributesEx box1_gateway: The system cannot find the path specified.", "tool_calls": [{"name": "view_file", "args": {"Path": "box1_gateway/proxy.py"}}]}),
            json.dumps({"step_index": 84, "source": "MODEL", "status": "DONE", "output_tokens": 7136, "tool_calls": [{"name": "write_file", "args": {"Path": ".staging/a.py"}}, {"name": "write_file", "args": {"Path": ".staging/b.py"}}, {"name": "write_file", "args": {"Path": ".staging/c.py"}}, {"name": "write_file", "args": {"Path": ".staging/d.py"}}]}),
        ]) + "\n",
        encoding="utf-8",
    )
    comp = transcript_tools_mod.analyze_compliance(tp_forensic)
    assert (comp["passed"], comp["blind_read_errors"], comp["write_burst_steps"]) == (True, 1, 1)

    tp_no_burst = tmp_path / "tp_no_write_burst.jsonl"
    tp_no_burst.write_text(
        "\n".join([
            json.dumps({"step_index": 85, "source": "MODEL", "status": "DONE", "output_tokens": 6000, "tool_calls": [{"name": "read_file", "args": {"Path": "scripts/nk_context_sentry.py"}}]}),
            json.dumps({"step_index": 86, "source": "MODEL", "status": "DONE", "output_tokens": 6100, "tool_calls": [{"name": "write_file", "args": {"Path": ".staging/a.py"}}, {"name": "write_file", "args": {"Path": ".staging/b.py"}}, {"name": "write_file", "args": {"Path": ".staging/c.py"}}]}),
        ]) + "\n",
        encoding="utf-8",
    )
    comp_no_burst = transcript_tools_mod.analyze_compliance(tp_no_burst)
    assert (comp_no_burst["passed"], comp_no_burst["write_burst_steps"]) == (True, 0)


def test_vibe_sprint_router_inplace_diff_loc_and_forensic_transcript(tmp_path: Path) -> None:
    """5. Verifica _estimate_changed_loc in-place, conferme 'ok procedi', negazione verbi e telemetria forensic."""
    prod_dir = tmp_path / "src_app"
    stag_dir = tmp_path / ".staging" / "src_app"
    prod_dir.mkdir(parents=True, exist_ok=True)
    stag_dir.mkdir(parents=True, exist_ok=True)

    prod_lines = [f"x_{i} = {i}" for i in range(10)]
    stag_lines = list(prod_lines)
    stag_lines[2], stag_lines[5], stag_lines[8] = "x_2 = 200", "x_5 = 500", "x_8 = 800"
    prod_file, stag_file = prod_dir / "service.py", stag_dir / "service.py"
    prod_file.write_text("\n".join(prod_lines) + "\n", encoding="utf-8")
    stag_file.write_text("\n".join(stag_lines) + "\n", encoding="utf-8")

    router = VibeSprintRouter(workspace_root=tmp_path)
    assert router._estimate_changed_loc(files=["src_app/service.py"]) == 3
    assert router._estimate_changed_loc(files=[str(prod_file)]) == 3
    assert router._estimate_changed_loc(files=[str(stag_file)]) == 3

    for short_conf in ("ok procedi", "procedi", "confermo", "vai", "si procedi pure", "procedi pure", "procedi con il piano", "procedi alla creazione dell'implementation plan"):
        assert router.is_gate_exempt(short_conf) is True
        assert router.build_meta_prompt_envelope(short_conf)["bypassed"] is True

    assert router.is_gate_exempt("attiva prompt gate e analizza il modulo") is False
    neg_prompt = "Non modificare nulla, solo analizza come funziona e spiega cosa fa"
    assert router_mod._has_imperative_write_keyword(neg_prompt) is False
    intent_neg = router.classify_prompt_intent(neg_prompt)
    assert (intent_neg["recommended_mode"], intent_neg["read_only"]) == ("mode_d", True)
    _assert_forensic_write_burst_transcripts(tmp_path)


PROMPT_CORPUS_30: Tuple[Tuple[str, str, List[str]], ...] = (
    ("Spiega come funziona il modulo ast_repo_mapper.py", "mode_d", ["INTRINSIC_GOAL"]),
    ("Qual è la differenza tra Tier-1 e Tier-3 memory?", "mode_c", ["INTRINSIC_GOAL"]),
    ("Mostra lo stato della telemetria RSI attuale", "mode_c", ["INTRINSIC_GOAL"]),
    ("Elenca i 6 sub-agenti nativi registrati nel manifest", "mode_d", ["INTRINSIC_GOAL"]),
    ("Analizza a fondo l'architettura 3-Tier ed effettua un audit multi-livello dei colli di bottiglia", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Analizza e valuta in profondità le vulnerabilità SAST e DAST dell'intero ecosistema", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Confronta le metriche di convergenza con un'ispezione olistica stato dell'arte", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Analizza lo stato dell'arte dell'implementazione attuale e fai una valutazione architetturale", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Correggi il refuso nella stringa di log di async_heartbeat_signaler.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Aggiorna il valore di default del parametro timeout in platform_runner.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Aggiungi un commento docstring alla funzione helper in nk_context_sentry.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Formatta l'output JSON del comando locate in nk_transcript_tools.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Rinomina la variabile locale tmp_val in clean_val dentro safe_cleanup_dev_servers.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Ottimizza con analisi approfondita la regex di parsing STT in vibe_sprint_router.py", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Rendi più robusto ed efficiente con benchmark il calcolo dell'hash SHA-256 in win32_2pc_engine.py", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Perfeziona con valutazione approfondita la logica di fallback per i file corrotti in nk_hook_gate.py", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Implementa un nuovo modulo di caching e aggiorna i test e la documentazione", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_PLAN"]),
    ("Progetta il piano di refactoring per nk_session_bootstrap.py e nk_registry_indexer.py", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_PLAN"]),
    ("Crea una nuova skill di validazione e registra l'indice in agent_manifest.json", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_PLAN"]),
    ("Modifica e implementa il contratto IPC in nk_ipc_contracts.py; inoltre aggiorna tutti i test correlati", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_PLAN"]),
    ("Aggiungi un nuovo sottocomando CLI a nk_transcript_tools.py e prepara la roadmap di rilascio", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_PLAN"]),
    ("Esegui un'analisi approfondita multi-livello del progetto Bandi; inoltre progetta il piano di implementazione e risolvi i difetti fino a convergenza", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Riprogetta l'architettura di sicurezza di nk_hook_gate.py con un'analisi approfondita e implementa i work package in .staging", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Analizza a fondo i colli di bottiglia di memoria 3-Tier; inoltre pianifica la migrazione SQLite WAL e verifica la suite", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Sviluppa un sistema completo di auto-healing multi-file con potenziamento massivo della copertura test", "mode_a", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Effettua uno stress test architetturale end-to-end; inoltre crea il piano di consolidamento della Tetralogia", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Ingegnerizza e implementa con strategia approfondita il protocollo Intrinsic Vibe Engine in vibe_sprint_router.py e aggiorna AGENTS.md", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Ottimizza con analisi multi-livello l'intero flusso di orchestrazione Hub-and-Spoke e pianifica gli step di rilascio", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Modifica il file A, anzi no analizza primaLa struttura di GitHub e FastAPI in profondità; inoltre crea un piano d'azione", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
    ("Praticamente cioè esegui un audit approfondito di PyTorch e TypeScript e progetta i work package di integrazione", "mode_c", ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]),
)


def test_vectorized_intrinsic_prompt_30_matrix() -> None:
    """6. Verifica vettorialmente 30 prompt reali di Vibe Coding per protocolli intrinseci e L0."""
    router = VibeSprintRouter()
    for prompt, expected_mode, expected_protocols in PROMPT_CORPUS_30:
        env = router.build_meta_prompt_envelope(prompt)
        assert env["recommended_mode"] == expected_mode
        if expected_mode == "mode_d" and env.get("auto_bypass_eligible"):
            assert env["bypassed"] is True and env["fsm_state"] == "BYPASSED"
            assert env["gate_mode"] == "SINGLE_GATE_MODE_D" and env["bypass_reason"] == "READONLY_MODE_D_BYPASS"
            env_forced = router.build_meta_prompt_envelope(prompt, auto_bypass_readonly=False)
            assert env_forced["bypassed"] is False and env_forced["fsm_state"] == "AWAIT_CONFIRM"
        else:
            assert env["bypassed"] is False and env["fsm_state"] == "AWAIT_CONFIRM"

        actual = env["intrinsic_protocols"]
        for proto in expected_protocols:
            assert proto in actual
        slash_eq = env["autonomous_slash_equivalence"]
        assert slash_eq["goal"] is ("INTRINSIC_GOAL" in actual) and slash_eq["boost"] is ("INTRINSIC_BOOST" in actual)
        assert slash_eq["plan"] is ("INTRINSIC_PLAN" in actual) and slash_eq["implementation"] is ("INTRINSIC_PLAN" in actual)
        assert env["optimized_meta_prompt"].startswith("[META-PROMPT L0 | Mode:")
        assert "Protocolli Intrinseci Auto-Attivati:" in env["optimized_meta_prompt"] and "R1:" in env["optimized_meta_prompt"]


def _assert_procedi_exemptions(router: VibeSprintRouter) -> None:
    assert router.is_gate_exempt("procedi e quando raggiungi la saturazione di contesto esegui un /compact") is True
    assert router.is_gate_exempt("procedi con l'implementazione") is True
    assert router.is_gate_exempt("procedi pure con la refactoring architetturale completa di tutti i moduli del sistema") is False
    assert router.is_gate_exempt("Vai a controllare i log") is False
    assert router.is_gate_exempt("Confermo che il bug esiste") is False
    assert router.is_gate_exempt("procedi | cat") is False
    assert router.is_gate_exempt("procedi; ls") is False
    assert router.build_meta_prompt_envelope("procedi e quando raggiungi la saturazione di contesto esegui un /compact")["bypassed"] is True


def _assert_dashboard_node_routing(router: VibeSprintRouter) -> None:
    assert router.classify_prompt_intent("[0]")["native_subagent"] == "NK-Arch-Specifier"
    assert router.classify_prompt_intent("[6]")["native_subagent"] == "NK-RSI-Auditor"
    assert router.classify_prompt_intent("[9]")["native_subagent"] == "NK-Scribe-Agent"
    assert len(router_mod.DASHBOARD_NODE_MAP) == 10
    assert (router_mod._parse_dashboard_selector("[9]"), router_mod._parse_dashboard_selector("[10]")) == (9, None)
    assert router.classify_prompt_intent("avvia nk orchestrator")["native_subagent"] == "Orchestrator-Direct"


def _assert_large_tail_reqs_and_no_crit01(router: VibeSprintRouter) -> None:
    from _internal.nk_registry_indexer.taxonomy import CRIT01_FORBIDDEN_TOOLS, FORBIDDEN_PHANTOM_MCP_TOOLS

    filler = "Dettaglio analitico esteso di contesto architetturale. " * 340
    assert len(filler) > 16384
    multi_req_prompt = (
        f"R1: Analizza il contesto iniziale {filler}; "
        "R2: Verifica il sottosistema auth; R3: Controlla il pool connessioni SQLite WAL; "
        "R4: Mappa i contratti Pydantic IPC; R5: Esamina le latenze cold-start CLI; "
        "R6: Verifica gli invarianti Zero-Mock; R7: Controlla la separazione 2-Tier degli agenti; "
        "R8: Certifica il requisito finale TAIL_SENTINEL_REQ_8; R9: Preserva TAIL_FINAL_REQUIREMENT_9_TOKEN"
    )
    env = router.build_meta_prompt_envelope(multi_req_prompt)
    reqs = env["requirements_r_ids"]
    assert len(reqs) >= 9
    assert any("TAIL_SENTINEL_REQ_8" in r for r in reqs)
    assert any("TAIL_FINAL_REQUIREMENT_9_TOKEN" in r for r in reqs)
    assert "TAIL_FINAL_REQUIREMENT_9_TOKEN" in env["conceptual_mirror"]

    env_compact = router.build_meta_prompt_envelope(multi_req_prompt, compact=True)
    assert len(env_compact["requirements_r_ids"]) == len(reqs)
    assert "TAIL_FINAL_REQUIREMENT_9_TOKEN" in env_compact["optimized_meta_prompt"]

    forbidden = set(CRIT01_FORBIDDEN_TOOLS) | set(FORBIDDEN_PHANTOM_MCP_TOOLS) | {"read_url_content"}
    t12 = "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n\n[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n### 1. Identità e Percorsi Operativi\n- Workspace: g:/Il mio Drive/Antigravity/NK_Hub\n[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    for intent_res in (router.classify_prompt_intent(t12), router.classify_prompt_intent("[0]"), router.classify_prompt_intent("Analizza l'architettura attuale in sola lettura"), router.classify_prompt_intent("Spiega il flusso operativo", mode="mode_d")):
        tools = list(intent_res.get("tools_allowed", []))
        assert intent_res["read_only"] is True
        assert bool(tools)
        assert forbidden.isdisjoint(tools)


def test_procedi_anti_loop_and_p1_2_large_prompt_tail_requirements() -> None:
    """7. Verifica procedi* <=12w, 10 nodi Dashboard, 8+ requisiti oltre 16KB e zero CRIT01_FORBIDDEN_TOOLS."""
    router = VibeSprintRouter()
    _assert_procedi_exemptions(router)
    _assert_dashboard_node_routing(router)
    _assert_large_tail_reqs_and_no_crit01(router)


def _assert_dm_subagents_and_intent_tokens() -> None:
    from _internal.vibe_sprint_router import domain_matcher as dm

    assert dm._has_audit_forensic_intent("esegui verifica copertura bandi") is False
    assert dm._has_audit_forensic_intent("esegui verifica forense tas") is True

    huge_prefix = ("xxevalxx " * 40) + ("filler text " * 1500)
    assert dm._token_matches_keyword("eval", f"{huge_prefix} coda eval", None, min_sub_len=999) is True
    assert dm._token_matches_keyword("eval", huge_prefix, None, min_sub_len=999) is False

    assert dm._resolve_native_subagent("DOM-01", matched_skill="NK-Agent-Instruction-Forge") == "NK-Builder-Agent"
    assert dm._resolve_native_subagent("DOM-03", matched_skill="NK-Ideator") == "NK-Arch-Specifier"
    assert dm._resolve_native_subagent("DOM-02", matched_skill="NK-System-Architect") == "NK-Specifier-Agent"
    assert dm._resolve_native_subagent("DOM-01", matched_skill="NK-Orchestrator") == "Orchestrator-Direct"
    assert dm._resolve_native_subagent("DOM-04", matched_skill="NK-Oracle-Evaluator") == "NK-RSI-Auditor"
    assert dm._resolve_native_subagent("DOM-01", text="calcola score rsi adesso") == "NK-RSI-Auditor"
    assert dm._resolve_native_subagent("DOM-01", text="esegui cold review adesso") == "NK-RSI-Auditor"
    assert VibeSprintRouter().resolve_domain_from_manifest("procedi")["domain_id"] == "DOM-03"


def _assert_dm_shard_rehydration(tmp_path: Path) -> None:
    from _internal.vibe_sprint_router import domain_matcher as dm

    sh_dir = tmp_path / "shards"
    sh_dir.mkdir(parents=True)
    (sh_dir / "bad.json").write_text("{bad", encoding="utf-8")
    (sh_dir / "nondict.json").write_text("[1, 2]", encoding="utf-8")
    (sh_dir / "d3.json").write_text(
        json.dumps({"domain": {"domain_id": "DOM-03", "name": "B", "keywords": ["k1"]}, "skills_index": {"S": {}, "BadSk": "skip"}, "scripts_index": {"a.py": {}, "BadSc": "skip"}, "intent_dispatch_table": {"_routes": [["NK-Builder", "mode_c", ["rt_kw"]], ["bad"]], "kw_s": "mode_c", "kw_d": {"recommended_mode": "mode_d"}}}),
        encoding="utf-8",
    )
    (sh_dir / "nodom.json").write_text(json.dumps({"skills_index": {}, "scripts_index": {}, "intent_dispatch_table": {}}), encoding="utf-8")
    rehyd = dm._rehydrate_router_manifest_shards(
        tmp_path / "nk_registry_manifest.json",
        {"domains": {}, "shards": {"DOM-00": "x.json", "DOM-03": "shards/d3.json", "DOM-ND": "shards/nodom.json", "DOM-LIST": "shards/nondict.json", "DOM-BAD": "shards/bad.json", "DOM-MISS": "shards/miss.json"}},
    )
    assert "kw_s" in rehyd["intent_dispatch_table"]
    assert "rt_kw" in rehyd["intent_dispatch_table"]
    assert "a.py" in rehyd["scripts_index"]
    assert dm._rehydrate_router_manifest_shards(tmp_path / "m.json", {"shards": "invalid"}) == {"shards": "invalid"}
    empty_rehyd = dm._rehydrate_router_manifest_shards(tmp_path / "m.json", {"shards": {"DOM-ND": "shards/nodom.json"}})
    assert "skills_index" not in empty_rehyd


def _assert_dm_manifest_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.vibe_sprint_router import domain_matcher as dm

    empty_ws = tmp_path / "empty_dm_ws"
    (empty_ws / "nk_genome").mkdir(parents=True)
    with monkeypatch.context() as mp_dm:
        mp_dm.setattr(dm, "_DEFAULT_WORKSPACE_ROOT", empty_ws)
        assert dm.load_registry_manifest_impl(VibeSprintRouter(workspace_root=empty_ws)) == {}
        bad_m = empty_ws / "nk_genome" / "nk_registry_manifest.json"
        bad_m.write_text("[1, 2]", encoding="utf-8")
        assert dm.load_registry_manifest_impl(VibeSprintRouter(workspace_root=empty_ws)) == {}
        bad_m.write_text(json.dumps({"domains": {"DOM-04": {"name": "AUDIT_DAST_AND_RCA", "primary_skill": "NK-Security-Auditor", "keywords": ["dast"]}}, "skills_index": {"NK-Custom-Sk": {"domain_id": "DOM-02", "domain_name": "IDEATION_AND_ARCH"}}, "scripts_index": {"custom_build.py": {"domain_id": "DOM-03", "domain_name": "BUILD_AND_HEAL"}}, "intent_dispatch_table": {"solo_dispatch_tok": {"domain_id": "DOM-05", "domain_name": "MEMORY_3TIER", "primary_agent": "NK-Scribe-Memory"}}}), encoding="utf-8")
        r_dm = VibeSprintRouter(workspace_root=empty_ws)
        assert r_dm._load_registry_manifest()["domains"]["DOM-04"]["primary_skill"] == "NK-Security-Auditor"
        assert r_dm._load_registry_manifest()["domains"]["DOM-04"]["primary_skill"] == "NK-Security-Auditor"
        assert dm.resolve_domain_from_manifest_impl(r_dm, "controlla DOM-04")["domain_id"] == "DOM-04"
        assert dm.resolve_domain_from_manifest_impl(r_dm, "usa NK-Custom-Sk")["primary_skill"] == "NK-Custom-Sk"
        assert dm.resolve_domain_from_manifest_impl(r_dm, "esegui verifica forense tas su custom_build.py")["domain_id"] == "DOM-04"
        assert dm.resolve_domain_from_manifest_impl(r_dm, "aggiorna custom_build.py")["domain_id"] == "DOM-03"
        assert dm.resolve_domain_from_manifest_impl(r_dm, "applica solo_dispatch_tok")["domain_id"] == "DOM-05"
        assert dm.resolve_domain_from_manifest_impl(r_dm, "esegui discovery architetturale")["domain_id"] == "DOM-02"


def test_router_domain_matcher_subagents_shards_and_missing_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8. Chiude i branch di domain_matcher.py: shard _routes, load missing/corrupt, DOM/skill/forensic/discovery."""
    _assert_dm_subagents_and_intent_tokens()
    _assert_dm_shard_rehydration(tmp_path)
    _assert_dm_manifest_resolution(tmp_path, monkeypatch)


def _assert_cli_transcript_records_and_backscan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.vibe_sprint_router import cli_handlers as ch_mod, transcript_and_cli as cli

    assert cli._extract_user_text_from_record({"source": "MODEL", "content": "hi"}) is None
    assert cli._extract_user_text_from_record({"type": "USER_INPUT", "content": "<CONTEXT_SUMMARY> skip"}) is None
    assert cli._extract_user_text_from_record({"type": "USER_INPUT", "content": ["", {"text": "Analizza tutto"}]}) == "Analizza tutto"
    assert cli._extract_user_text_from_record({"type": "USER_INPUT", "content": [{"text": "   "}, "   "]}) is None

    fake_home = tmp_path / "fake_home"
    brain = fake_home / ".gemini" / "antigravity" / "brain"
    brain.mkdir(parents=True)
    (brain / "not_a_dir.txt").write_text("x", encoding="utf-8")
    (brain / "empty_conv").mkdir()
    stale_tp = brain / "stale_conv" / ".system_generated" / "logs" / "transcript.jsonl"
    stale_tp.parent.mkdir(parents=True)
    stale_tp.write_text(json.dumps({"type": "USER_INPUT", "content": "stale"}) + "\n", encoding="utf-8")
    old_ts = time.time() - 3600.0
    os.utime(stale_tp, (old_ts, old_ts))
    rec_tp = brain / "recent_conv" / ".system_generated" / "logs" / "transcript.jsonl"
    rec_tp.parent.mkdir(parents=True)
    pad = json.dumps({"source": "MODEL", "content": "p" * 1024})
    rec_tp.write_text("\n".join([pad] * 130 + [json.dumps({"type": "USER_INPUT", "content": "recent_big_prompt"})] + [pad] * 10 + ["", "{bad", "[1]", json.dumps({"source": "MODEL", "content": "end"})]) + "\n", encoding="utf-8")

    with monkeypatch.context() as mp_h:
        mp_h.setattr(Path, "home", lambda: fake_home)
        for ek in ("NK_TRANSCRIPT_PATH", "ANTIGRAVITY_TRANSCRIPT_PATH", "NK_CONVERSATION_ID", "ANTIGRAVITY_CONVERSATION_ID"):
            mp_h.delenv(ek, raising=False)
        assert ch_mod._read_latest_user_input_from_transcript(None) == "recent_big_prompt"
        empty_f = tmp_path / "empty_tr.jsonl"
        empty_f.write_text("", encoding="utf-8")
        assert ch_mod._read_latest_user_input_from_transcript(str(empty_f)) is None
        assert ch_mod._read_latest_user_input_from_transcript(str(tmp_path / "no_such_tr.jsonl")) is None

    rel_p = tmp_path / "rel_prompt.txt"
    rel_p.write_text("Analizza file relativo", encoding="utf-8")
    assert ch_mod._resolve_effective_cli_prompt(type("Args", (), {"prompt_file": "rel_prompt.txt", "stdin": False, "classify_prompt": None, "prompt": "Vibe Sprint Change", "positional_prompt": None})(), workspace_root=tmp_path) == "Analizza file relativo"
    with monkeypatch.context() as mp_in:
        mp_in.setattr(sys, "stdin", io.StringIO("Prompt da stdin"))
        assert ch_mod._resolve_effective_cli_prompt(type("Args", (), {"prompt_file": None, "stdin": True, "classify_prompt": None, "prompt": "Vibe Sprint Change", "positional_prompt": None})()) == "Prompt da stdin"


def _assert_cli_validate_and_meta_flags(tmp_path: Path, capsys: Any) -> None:
    rc_t, out_t, _ = call_script_main_captured(router_mod, ["--test"])
    assert rc_t == 0
    assert out_t.strip() != ""
    assert router_mod.main(["--prompt-file", str(tmp_path / "no_such_prompt.txt")]) == 1
    assert "Prompt file non trovato" in capsys.readouterr().err

    bad_prompt = "!diretto\nFase 1: opera come NK-Security-Auditor e NK-Orchestrator modifica src_app/x.py\nFase 2: esegui /compact automatico finche 100% PASS su canary_v1.json\n"
    assert router_mod.main(["--validate-generated-prompt", bad_prompt]) == 1
    capsys.readouterr()
    assert router_mod.main(["--validate-generated-prompt", "Usa /goal ora", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False
    assert router_mod.main(["--validate-generated-prompt", "__USE_PROMPT__", "--prompt", "Analizza il file A"]) == 0
    assert "Status: PASS" in capsys.readouterr().out
    assert router_mod.main(["--validate-generated-prompt", "Analizza lo stato del modulo in sola lettura.", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def _assert_cli_capsule_and_transcript(tmp_path: Path, capsys: Any) -> None:
    assert router_mod.main(["--classify-prompt", "Spiega router", "--capsule", "--json"]) == 0
    assert "tier1_capsule" in json.loads(capsys.readouterr().out)
    assert router_mod.main(["--capsule"]) == 0
    assert bool(capsys.readouterr().out.strip())
    assert router_mod.main([]) == 0
    assert "VibeSprintRouter CLI ready" in capsys.readouterr().out

    tr_multi = tmp_path / "multi_input.jsonl"
    tr_multi.write_text(json.dumps({"type": "USER_INPUT", "content": [{"text": "Prima parte"}, "Seconda parte operativa"]}) + "\n", encoding="utf-8")
    assert router_mod.main(["--transcript", str(tr_multi), "--classify-prompt", "--json"]) == 0
    assert "recommended_mode" in json.loads(capsys.readouterr().out)
    assert router_mod.lint_nk_prompt("opera come NK-Security-Auditor e NK-Orchestrator e modifica subito scripts/a.py")["valid"] is False


def _assert_cli_files_capsule_and_multi(tmp_path: Path, capsys: Any) -> None:
    assert router_mod.main(["--meta-prompt-gate", "--prompt", " Correggi bug in scripts/x.py "]) == 0
    assert router_mod.main(["--meta-prompt-gate", "--prompt", "Aggiorna bottone UI", "--compact"]) == 0
    assert "[L0-COMPACT]" in capsys.readouterr().out
    assert router_mod.main(["--no-gate", "--json", "--prompt", "Analisi veloce"]) == 0
    assert json.loads(capsys.readouterr().out)["recommended_mode"] == "mode_d"

    sample_py = tmp_path / "tiny_mod.py"
    sample_py.write_text("def f(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    assert router_mod.main(["--files", str(sample_py), str(tmp_path / "missing_mod.py"), "--changed-lines", "220", "--capsule", "--json"]) == 0
    fl_data = json.loads(capsys.readouterr().out)
    assert ("files" in fl_data, "tier1_capsule" in fl_data) == (True, True)
    assert router_mod.main(["--files", str(sample_py), "--changed-lines", "200", "--mode", "mode_a", "--capsule", "--compact", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["files"][0]["recommended_mode"] == "mode_a"
    _assert_cli_capsule_and_transcript(tmp_path, capsys)


def test_router_transcript_cli_handlers_and_missing_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """9. Chiude cli_handlers.py + migrazione test_cli_gates_vibe_sprint_router_modes_and_lint."""
    _assert_cli_transcript_records_and_backscan(tmp_path, monkeypatch)
    _assert_cli_validate_and_meta_flags(tmp_path, capsys)
    _assert_cli_files_capsule_and_multi(tmp_path, capsys)


def test_p0_bug_01_composite_confirmations_o_meglio_xml_strip_and_l0_gate_file(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """10. Verifica chiusura P0-BUG-01: conferme composite, 'o meglio', strip XML e l0_gate_<cid>.json."""
    from _internal.vibe_sprint_router import transcript_and_cli as cli

    router = VibeSprintRouter()
    assert router.is_gate_exempt("approvo") is True and router.is_gate_exempt("perfetto approvo") is True
    assert router.is_gate_exempt("Ok procedi ma prima valuta in sandbox") is False
    assert router.is_gate_exempt("Procedi con il piano e fai anche un report finale") is False
    assert router.is_gate_exempt("Ok procedi. Analizza anche il bug") is False

    stt_res = router.normalize_voice_stt_input("Modifica il modulo router. O meglio analizza i test")
    assert "Modifica il modulo router" in stt_res["cleaned_prompt"]
    assert router.classify_prompt_intent(stt_res["cleaned_prompt"])["read_only"] is False

    xml_rec = {"type": "USER_INPUT", "content": "<USER_REQUEST>avvia nk hub</USER_REQUEST>\n<ADDITIONAL_METADATA>model=carbon</ADDITIONAL_METADATA>"}
    assert cli._extract_user_text_from_record(xml_rec) == "avvia nk hub"

    hooks_dir = tmp_path / "nk_hooks_test"
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_dir))
    monkeypatch.setenv("NK_CONVERSATION_ID", "conv_l0_test")
    assert router_mod.main(["--meta-prompt-gate", "--prompt", "Ottimizza e accorpa le skill", "--compact"]) == 0
    capsys.readouterr()
    l0_file = hooks_dir / "l0_gate_conv_l0_test.json"
    l0_data = json.loads(l0_file.read_text(encoding="utf-8"))
    assert len(l0_data["turn_prompt_sha256"]) == 64 and l0_data["fsm_state"] == "AWAIT_CONFIRM" and l0_data["bypassed"] is False


def _assert_write_intent_batch(prompts: tuple[str, ...], expected: bool) -> None:
    from _internal.vibe_sprint_router import write_intent as wi

    for p in prompts:
        assert wi._analyze_write_intent(p)[0] is expected, f"Write intent mismatch ({expected}): {p}"


def _assert_write_roots_and_long_mixed_envelope() -> None:
    from _internal.vibe_sprint_router import write_intent as wi, write_intent_rules as wir

    assert "ne" not in wir._NEGATION_TOKENS
    assert "né" in wir._NEGATION_TOKENS
    assert {"esegui", "eseguire"}.issubset(wir._LIGHT_EXEC_VERBS)
    assert wi._is_negated_window_12(["non", ",", "inserisci"], []) is False
    assert wi._is_negated_window_12(["non", "inserisci"], []) is True
    assert {"inser", "realizz", "integr", "configur", "impost", "predispon"}.issubset({k for k, _ in wir._WRITE_ROOT_GROUPS})

    _assert_write_intent_batch((
        "Inserire la nuova rotta nel router", "Inserisci i controlli di validazione", "Realizzare la dashboard amministrativa",
        "Integrare il servizio di autenticazione", "Configurare le variabili del server", "Impostare i timeout del worker",
        "Predisporre il modulo di esportazione", "Dobbiamo mettere le basi per il pannello", "Occorre gettare le basi del servizio",
        "Bisogna mettere in piedi il backend", "Nel nuovo flusso servirà una pagina dedicata", "Per l'admin servirà una nuova sezione di audit",
        "In produzione servirà un server separato", "Alla fine servirà il modulo di reporting",
        "Non ho tutti i dettagli, ne inseriamo subito una versione base",
        "Spiega come funziona il server, dobbiamo inserire la pagina dell'admin", "Spiega dove sta il problema, dovremo configurare il modulo",
        "Dimmi cosa fa l'auth, bisogna integrare il token", "Illustra il flusso, occorre realizzare il controller",
        "Spiega come parte il worker, serve impostare il parametro", "Descrivi il router, servirà predisporre la sezione",
        "Spiega cosa fa la vista, vorrei creare la pagina admin", "Spiega come funziona il server, servirà una pagina admin",
    ), True)
    _assert_write_intent_batch((
        "Spiega il calcolo integrale del modulo matematico", "Spiega come modificare il file senza errori",
        "Non mettere le basi del server", "Non servirà una pagina nuova", "Non modificare né inserire nuovi file",
    ), False)

    router = VibeSprintRouter(workspace_root=WORKSPACE_ROOT)
    long_filler = " ".join(["dettaglio tecnico architetturale sul modulo server"] * 35)
    mixed_long = f"Rifare un'analisi completa del flusso corrente ({long_filler}), non ne conosco ancora tutti i limiti, ma dobbiamo inserire nel server la pagina dell'admin"
    assert len(mixed_long) > 1500
    env_mixed = router.build_meta_prompt_envelope(mixed_long)
    assert (env_mixed["recommended_mode"], env_mixed["fsm_state"], env_mixed["bypassed"]) == ("mode_a", "AWAIT_CONFIRM", False)
    env_short = router.build_meta_prompt_envelope("Rifare un'analisi dell'architettura e inserire nel server la pagina dell'admin")
    assert env_short["recommended_mode"] != "mode_d"
    assert env_short["fsm_state"] == "AWAIT_CONFIRM"


def _assert_forge04_ref02_and_gov_ro() -> None:
    router = VibeSprintRouter(workspace_root=WORKSPACE_ROOT)
    assert router.classify_prompt_intent("Aggiorna NK-Builder-Agent/agent.md e sincronizza il manifesto gemello", changed_lines=8).get("primary_agent") == "NK-Agent-Instruction-Forge"
    r_forge = router.classify_prompt_intent("Sincronizza il profilo agent.md rispettando byte budget <= 24000", changed_lines=5)
    assert (r_forge["primary_agent"], r_forge["read_only"], r_forge["native_subagent"], r_forge["domain_id"]) == ("NK-Agent-Instruction-Forge", False, "NK-Builder-Agent", "DOM-03")
    r_ref = router.classify_prompt_intent("Esegui il refactoring dell'architettura interna di auto_heal_pipeline estraendo due moduli sotto 300 LOC", changed_lines=20)
    assert (r_ref["primary_agent"], r_ref["read_only"], r_ref["native_subagent"], r_ref["domain_id"]) == ("NK-Delta-Architect", False, "NK-Builder-Agent", "DOM-03")
    assert router.classify_prompt_intent("Implementa endpoint FastAPI Python con test e componente React UI", changed_lines=35).get("native_subagent") == "NK-Builder-Agent"

    for ro_prompt in ("Spiega come funziona agent.md in sola lettura", "Analizza il profilo agent.md in sola lettura senza modificare"):
        r_ro = router.classify_prompt_intent(ro_prompt, changed_lines=0)
        assert (r_ro["domain_id"], r_ro["read_only"]) == ("DOM-04", True)
        assert (r_ro["native_subagent"] != "NK-Builder-Agent", r_ro["primary_agent"] != "NK-Agent-Instruction-Forge") == (True, True)

    for gov_prompt in ("Verifica NK-Builder-Agent/agent.md", "Controlla la conformita STE100 di SKILL.md", "Valida skill_golden_eval_set", "Ispeziona agent.md"):
        res = router.classify_prompt_intent(gov_prompt, changed_lines=0)
        assert (res["recommended_mode"], res["read_only"], res["domain_id"], res["native_subagent"], res["primary_agent"]) == ("mode_d", True, "DOM-04", "NK-RSI-Auditor", "NK-Oracle-Evaluator")

    forced_mode = router.classify_prompt_intent("Verifica NK-Builder-Agent/agent.md", mode="mode_a")
    assert (forced_mode["domain_id"], forced_mode["native_subagent"], forced_mode["primary_agent"]) == ("DOM-04", "NK-RSI-Auditor", "NK-Oracle-Evaluator")
    write_gov = router.classify_prompt_intent("Aggiorna NK-Builder-Agent/agent.md e verifica STE100", changed_lines=5)
    assert (write_gov["read_only"], write_gov["domain_id"], write_gov["native_subagent"], write_gov["primary_agent"]) == (False, "DOM-03", "NK-Builder-Agent", "NK-Agent-Instruction-Forge")


def test_vibe_sprint_router_write_roots_forge04_ref02_and_gov_ro() -> None:
    """11. Verifica radici write, 'esegui' in _LIGHT_EXEC_VERBS, FORGE-04/REF-02 e audit RO DOM-04."""
    _assert_write_roots_and_long_mixed_envelope()
    _assert_forge04_ref02_and_gov_ro()

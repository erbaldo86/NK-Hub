# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per vibe_sprint_router.py (v6.4.0-Carbon).
Modulo: tests/test_vibe_sprint_router.py.
Valida profondita AST, routing Mode A/B/C/D, Meta-Prompt Gate, protocolli intrinseci e AP-10.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Tuple

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

router_mod = load_nk_script_module("vibe_sprint_router")
transcript_tools_mod = load_nk_script_module("nk_transcript_tools")
VibeSprintRouter = router_mod.VibeSprintRouter

pytestmark = pytest.mark.fast


def test_vibe_sprint_router_real_ast_max_depth_and_routing(tmp_path: Path) -> None:
    """Verifica max_depth AST, selezione modalita e caricamento di tier1_active_capsule.json."""
    router = VibeSprintRouter(workspace_root=tmp_path)

    simple_code = "def render_btn(label: str) -> str:\n    return f'<button>{label}</button>'\n"
    res_c = router.compute_ast_risk_score(simple_code, filename="simple_ui.py")
    assert res_c["recommended_mode"].lower() == "mode_c" and res_c["max_depth"] == 1

    deep_code = (
        "import subprocess\ndef run_deep(items):\n    for a in items:\n        if a > 0:\n"
        "            for b in range(a):\n                if b % 2 == 0:\n"
        "                    try:\n                        while b > 1:\n                            b -= 1\n"
        "                    except Exception:\n                        pass\n"
    )
    res_deep = router.compute_ast_risk_score(deep_code, filename="deep_core.py")
    assert res_deep["max_depth"] >= 6 and res_deep["max_depth"] > res_c["max_depth"]

    mem_dir = tmp_path / "nk_tracking" / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "tier1_active_capsule.json").write_text(
        '{"status": "OK", "capsule_text": "Invariante Zero-Mock attivo", "token_count": 12, "token_cap": 350, "entries": []}',
        encoding="utf-8",
    )
    router_cap = VibeSprintRouter(workspace_root=tmp_path)
    loaded = router_cap.load_prewarmed_capsule()
    assert loaded["status"] == "OK" and "Invariante Zero-Mock attivo" in loaded["capsule_text"]
    risk = router_cap.compute_ast_risk_score("def f(x: int) -> int:\n    return x + 1\n", "f.py")
    spec = router_cap.generate_inline_micro_spec("f.py", "Increment value", risk)
    assert "Tier-1 Capsule: Invariante Zero-Mock attivo" in spec


def test_vibe_sprint_router_stt_normalization_and_anti_loop_exemptions() -> None:
    """Verifica sostantivi astratti, normalizzazione STT su primaLa ed esenzioni anti-loop."""
    router = VibeSprintRouter()
    prompt_disc = "Analizza lo stato dell'arte dell'implementazione attuale e fai una valutazione architetturale di copertura"
    assert router_mod._has_imperative_write_keyword(prompt_disc) is False
    intent = router.classify_prompt_intent(prompt_disc)
    assert intent["recommended_mode"] == "mode_d" and intent["is_discovery"] is True
    assert intent["read_only"] is True and intent["primary_agent"] == "NK-Ideator"

    prompt_write = "Implementa il nuovo contratto in .staging/ e modifica il router"
    assert router_mod._has_imperative_write_keyword(prompt_write) is True
    assert router.classify_prompt_intent(prompt_write)["is_discovery"] is False

    stt = router.normalize_voice_stt_input("Modifica il file, anzi no analizza primaLa struttura di `myCamelVar` praticamente")
    assert "prima La" in stt["cleaned_prompt"] and "`myCamelVar`" in stt["cleaned_prompt"]
    assert any("primaLa -> prima La" in c for c in stt["voice_corrections_applied"])
    assert len(stt["voice_corrections_applied"]) >= 2

    for exempt in (
        "ok", "Confermo!", "procedi pure", "procedi con il piano",
        "procedi alla creazione dell'implementation plan", "avvia nk", "[9]",
        "Proceed", "premi proceed", "<env_capsule>\nTEST_RUNNER: pytest\n</env_capsule>",
        "!diretto analizza il codice", "disattiva prompt gate",
    ):
        assert router.is_gate_exempt(exempt) is True
    assert router.is_gate_exempt("Progetta un nuovo modulo asincrono per il router") is False


def test_vibe_sprint_router_meta_prompt_envelope_and_cli() -> None:
    """Verifica build_meta_prompt_envelope, bypass Mode D e standby Template 12."""
    router = VibeSprintRouter()
    env = router.build_meta_prompt_envelope("Analizza primaLa struttura dell'implementazione; inoltre verifica la valutazione")
    assert env["brief_id"].startswith("IB-") and env["fsm_state"] == "BYPASSED" and env["bypassed"] is True
    assert env["gate_mode"] == "SINGLE_GATE_MODE_D" and env["bypass_reason"] == "READONLY_MODE_D_BYPASS"
    assert env["recommended_mode"] == "mode_d" and env["native_subagent"] == "NK-Arch-Specifier"
    assert "Single-Gate: READONLY_MODE_D_BYPASS" in env["optimized_meta_prompt"]
    assert len(env["intent_hash_sha256"]) == 64 and len(env["requirements_r_ids"]) >= 2
    assert env["requirements_r_ids"][0].startswith("R1:")

    env_forced = router.build_meta_prompt_envelope(
        "Analizza primaLa struttura dell'implementazione; inoltre verifica la valutazione",
        auto_bypass_readonly=False,
    )
    assert env_forced["fsm_state"] == "AWAIT_CONFIRM" and env_forced["bypassed"] is False and env_forced["recommended_mode"] == "mode_d"

    env_exempt = router.build_meta_prompt_envelope("ok")
    assert env_exempt["fsm_state"] == "BYPASSED" and env_exempt["bypassed"] is True

    t12_prompt = (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n### 1. Identità e Percorsi Operativi\n"
        "- Workspace: g:/Il mio Drive/Antigravity/NK_Hub\n[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )
    env_t12 = router.build_meta_prompt_envelope(t12_prompt)
    assert env_t12["fsm_state"] == "BYPASSED" and env_t12["bypassed"] is True
    assert env_t12.get("bypass_reason") == "STATE_HANDOFF_STANDBY" and env_t12.get("standby_mode") is True
    assert env_t12["intrinsic_protocols"] == []
    assert env_t12["autonomous_slash_equivalence"]["goal"] is False and env_t12["autonomous_slash_equivalence"]["plan"] is False
    if hasattr(router, "evaluate_meta_prompt_gate"):
        eval_t12 = router.evaluate_meta_prompt_gate(t12_prompt)
        assert eval_t12["bypass_reason"] == "STATE_HANDOFF_STANDBY" and eval_t12["intrinsic_protocols"] == []


def test_router_intrinsic_protocols_bandi_and_cli_gate() -> None:
    """Verifica CLI --meta-prompt-gate / --no-gate e protocolli intrinseci sul caso Bandi."""
    router = VibeSprintRouter()
    assert router_mod.main(["--meta-prompt-gate", "--prompt", "Analizza primaLa copertura", "--json"]) == 0
    assert router_mod.main(["--no-gate", "--prompt", "Analizza primaLa copertura", "--json"]) == 0

    default_res = router.resolve_intrinsic_vibe_protocols("Aggiorna colore pulsante", "mode_c")
    assert "INTRINSIC_GOAL" in default_res["intrinsic_protocols"] and default_res["autonomous_slash_equivalence"]["goal"] is True

    bandi_prompt = (
        "Esegui un'analisi approfondita multi-livello del progetto Bandi; "
        "inoltre progetta il piano di implementazione e risolvi i difetti fino a convergenza"
    )
    bandi_res = router_mod.resolve_intrinsic_vibe_protocols(bandi_prompt, "mode_a")
    assert bandi_res["intrinsic_protocols"] == ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"]
    assert all(bandi_res["autonomous_slash_equivalence"][k] is True for k in ("goal", "boost", "plan"))

    env_bandi = router.build_meta_prompt_envelope(bandi_prompt)
    assert all(p in env_bandi["intrinsic_protocols"] for p in ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"))
    assert "Protocolli Intrinseci Auto-Attivati:" in env_bandi["optimized_meta_prompt"]
    assert env_bandi["optimized_meta_prompt"].startswith("[META-PROMPT L0 | Mode:")


def test_vibe_sprint_router_l0_rendered_markdown_and_clause_split(capsys) -> None:
    """Verifica guardia AP-10, rendered_markdown L0, mancata rottura su punti e output CLI."""
    passive_prompt = "Per ottenere risultati migliori puoi utilizzare anche il comando /goal o /boost oppure digita il comando /plan."
    res_router = router_mod.lint_nk_prompt(passive_prompt)
    assert res_router["passed"] is False and any(v["code"] == "AP-10" for v in res_router["violations"])

    res_tools, code_tools = transcript_tools_mod.lint_prompt_text(passive_prompt)
    assert code_tools == 1 and res_tools["passed"] is False and any(v["code"] == "AP-10" for v in res_tools["violations"])

    rule_text = "Nessun agente chiede all'utente di digitare manualmente /goal, /boost, /plan o /implementation (AP-10).\nVieta di dire: puoi utilizzare anche il comando /goal."
    assert not any(v["code"] == "AP-10" for v in router_mod.lint_nk_prompt(rule_text)["violations"])
    clean_tools, _ = transcript_tools_mod.lint_prompt_text(rule_text)
    assert not any(v["code"] == "AP-10" for v in clean_tools["violations"])

    router = VibeSprintRouter()
    prompt_dots = "Aggiorna PATCH_NOTES.md e scripts/vibe_sprint_router.py per la release v6.0.0-Carbon in .staging; inoltre verifica la suite di test"
    env = router.build_meta_prompt_envelope(prompt_dots)
    md = env["rendered_markdown"]
    assert "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]" in md and "Specchio Concettuale" in md
    for field_name in ("conceptual_mirror", "optimized_meta_prompt", "rendered_markdown"):
        assert "Brief" in env[field_name] and "implementation_plan.md" in env[field_name] and "RequestFeedback: true" in env[field_name]
    assert "[MANDATORY-VISIBLE-L0]: Mostra obbligatoriamente questo blocco nel campo content della risposta PRIMA o INSIEME a ask_question (vietato content_len=0)." in md
    assert router_mod.format_meta_prompt_markdown(env) == md

    env_confirm = router.build_meta_prompt_envelope("procedi")
    assert "INTRINSIC_PLAN" in env_confirm["intrinsic_protocols"] and env_confirm["autonomous_slash_equivalence"]["implementation"] is True
    assert len(env["requirements_r_ids"]) == 2 and "PATCH_NOTES.md" in env["requirements_r_ids"][0]
    assert not any(r.startswith("R2: md") for r in env["requirements_r_ids"])

    assert router_mod.main(["--meta-prompt-gate", "--prompt", prompt_dots]) == 0
    captured = capsys.readouterr().out
    assert "[META-PROMPT-GATE]" in captured and "Specchio Concettuale" in captured


def test_vibe_sprint_router_inplace_diff_loc_short_confirm_and_negated_write(tmp_path: Path) -> None:
    """Verifica _estimate_changed_loc in-place, conferme 'ok procedi' e negazione verbi."""
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
        env_c = router.build_meta_prompt_envelope(short_conf)
        assert env_c["fsm_state"] == "BYPASSED" and env_c["bypassed"] is True

    assert router.is_gate_exempt("attiva prompt gate e analizza il modulo") is False
    neg_prompt = "Non modificare nulla, solo analizza come funziona e spiega cosa fa"
    assert router_mod._has_imperative_write_keyword(neg_prompt) is False
    intent_neg = router.classify_prompt_intent(neg_prompt)
    assert intent_neg["recommended_mode"] == "mode_d" and intent_neg["read_only"] is True


def test_router_negated_write_stt_correction_and_mode_d_keywords() -> None:
    """Verifica correzione anzi no estesa, negazione multi-parola e MODE_D_KEYWORDS."""
    router = VibeSprintRouter()
    long_anzi = "Nel modulo di autenticazione dobbiamo verificare tutti i permessi degli utenti registrati nel database, anzi no solo quelli attivi"
    stt_long = router.normalize_voice_stt_input(long_anzi)
    assert "modulo di autenticazione" in stt_long["cleaned_prompt"] and "solo quelli attivi" in stt_long["cleaned_prompt"]
    assert router_mod._has_imperative_write_keyword("non devi a modificare il codice") is False
    assert router_mod._has_imperative_write_keyword("non voglio assolutamente in alcun modo modificare il codice, analizza solo") is False
    stt_m03 = router.normalize_voice_stt_input("crea un file temporaneo nel progetto, anzi no analizza solo la struttura")
    assert "crea un file" not in stt_m03.get("normalized_text", stt_m03["cleaned_prompt"]).lower()
    assert router.is_gate_exempt("procedi pure con la refactoring architetturale completa di tutti i moduli del sistema") is False
    env_m33 = router_mod.build_meta_prompt_envelope("Spiega cosa fa il modulo X", auto_bypass_readonly=True)
    assert env_m33["fsm_state"] == "BYPASSED" and env_m33["auto_bypass_eligible"] is True
    assert router.is_gate_exempt("ok procedi cancella tutto subito") is False
    assert router_mod.is_gate_exempt("ok procedi cancella tutto subito") is False
    stt_m33 = router.normalize_voice_stt_input("Modifica il file A, anzi no fermati")
    assert (stt_m33["cleaned_prompt"] if isinstance(stt_m33, dict) else stt_m33) == "fermati"
    assert "review" in router_mod.MODE_D_KEYWORDS and "elenca" in router_mod.MODE_D_KEYWORDS


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

PROMPT_CORPUS_30: Tuple[Tuple[str, str, List[str]], ...] = (
    ("Spiega come funziona il modulo ast_repo_mapper.py", "mode_d", ["INTRINSIC_GOAL"]),
    ("Qual è la differenza tra Tier-1 e Tier-3 memory?", "mode_c", ["INTRINSIC_GOAL"]),
    ("Mostra lo stato della telemetria RSI attuale", "mode_c", ["INTRINSIC_GOAL"]),
    ("Elenca i 6 sub-agenti nativi registrati nel manifest", "mode_d", ["INTRINSIC_GOAL"]),
    ("Analizza a fondo l'architettura 3-Tier ed effettua un audit multi-livello dei colli di bottiglia", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Analizza e valuta in profondità le vulnerabilità SAST e DAST dell'intero ecosistema", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Confronta le metriche di convergenza con un'ispezione olistica stato dell'arte", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Analizza lo stato dell'arte dell'implementazione attuale e fai una valutazione architetturale", "mode_d", ["INTRINSIC_GOAL", "INTRINSIC_BOOST"]),
    ("Correggi il refuso nella stringa di log di micro_hud_renderer.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Aggiorna il valore di default del parametro timeout in platform_runner.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Aggiungi un commento docstring alla funzione helper in nk_context_sentry.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Formatta l'output JSON del comando locate in nk_transcript_tools.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Rinomina la variabile locale tmp_val in clean_val dentro micro_hud_renderer.py", "mode_c", ["INTRINSIC_GOAL"]),
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


def test_vectorized_stt_brand_preservation_matrix() -> None:
    """Verifica vettorialmente che 50 brand non vengano spezzati ma i typo italiani si."""
    router = VibeSprintRouter()
    for brand in TECH_BRANDS_AND_IDENTIFIERS:
        res = router.normalize_voice_stt_input(f"Analizza l'integrazione di {brand} nel modulo core senza regressioni")
        assert brand in res["cleaned_prompt"]

    for raw_text, expected_split in [
        ("analizza primaLa struttura", "prima La"), ("verifica tuttoIl modulo", "tutto Il"),
        ("controlla ancheLa copertura", "anche La"), ("esegui soloUn test rapido", "solo Un"),
        ("modifica dentroIl file target", "dentro Il"), ("sposta versoLa directory staging", "verso La"),
        ("aggiorna sottoIl limite previsto", "sotto Il"), ("porta oltreIl livello minimo", "oltre Il"),
        ("inserisci senzaUn errore", "senza Un"), ("ottiene cosìUn risultato stabile", "così Un"),
        ("imposta piùUn valore valido", "più Un"), ("trova giàUn record esistente", "già Un"),
    ]:
        res = router.normalize_voice_stt_input(raw_text)
        assert expected_split in res["cleaned_prompt"]


def test_vectorized_intrinsic_prompt_30_matrix() -> None:
    """Verifica vettorialmente 30 prompt reali di Vibe Coding per protocolli intrinseci e L0."""
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
        assert slash_eq["goal"] is ("INTRINSIC_GOAL" in actual)
        assert slash_eq["boost"] is ("INTRINSIC_BOOST" in actual)
        assert slash_eq["plan"] is ("INTRINSIC_PLAN" in actual)
        assert slash_eq["implementation"] is ("INTRINSIC_PLAN" in actual)
        assert env["optimized_meta_prompt"].startswith("[META-PROMPT L0 | Mode:")
        assert "Protocolli Intrinseci Auto-Attivati:" in env["optimized_meta_prompt"] and "R1:" in env["optimized_meta_prompt"]


def test_vectorized_ap10_meta_prompt_linter_suite() -> None:
    """Verifica vettorialmente che AP-10 blocchi suggerimenti passivi ma consenta divieti."""
    bad_suggestions = [
        "Per approfondire puoi utilizzare anche il comando /goal nel terminale.",
        "Ti consiglio di usare /boost per potenziare la richiesta.",
        "Digita il comando /plan per generare il piano di implementazione.",
        "Puoi invocare /implementation per procedere con i work package.",
        "Usa il comando `/goal` oppure `/boost` per migliorare il prompt.",
    ]
    for bad_text in bad_suggestions:
        r_lint = router_mod.lint_nk_prompt(bad_text)
        assert r_lint["passed"] is False and any(v["code"] == "AP-10" for v in r_lint["violations"])
        t_lint, exit_code = transcript_tools_mod.lint_prompt_text(bad_text)
        assert exit_code == 1 and t_lint["passed"] is False and any(v["code"] == "AP-10" for v in t_lint["violations"])

    allowed_texts = [
        "Nessun agente chiede all'utente di digitare manualmente /goal, /boost, /plan o /implementation (AP-10).",
        "È vietato suggerire passivamente di usare il comando /goal o /boost.",
        "Non chiedere mai di invocare /plan: il router attiva INTRINSIC_PLAN autonomamente.",
        "Esegui l'analisi architetturale del modulo e genera l'artefatto implementation_plan.md.",
    ]
    for ok_text in allowed_texts:
        assert not any(v["code"] == "AP-10" for v in router_mod.lint_nk_prompt(ok_text)["violations"])
        t_ok, _ = transcript_tools_mod.lint_prompt_text(ok_text)
        assert not any(v["code"] == "AP-10" for v in t_ok["violations"])


def test_mode_c_max_loc_boundary_and_anti_bypass_hardening(tmp_path: Path, capsys) -> None:
    """Verifica il confine MODE_C_MAX_LOC==150, falsi bypass L0 e resilienza CLI/capsula."""
    router = VibeSprintRouter()
    assert VibeSprintRouter.MODE_C_MAX_LOC == 150 and router.MODE_C_MAX_LOC == 150

    res_120 = router.classify_prompt_intent("Modifica la funzione di calcolo in modulo.py", changed_lines=120)
    assert res_120["recommended_mode"] == "mode_c" and res_120["fast_bypass_eligible"] is True
    res_200 = router.classify_prompt_intent("Modifica la funzione di calcolo in modulo.py", changed_lines=200)
    assert res_200["recommended_mode"] == "mode_b" and res_200["fast_bypass_eligible"] is False

    ast_120 = router.compute_ast_risk_score("\n".join(f"x_{i} = {i}" for i in range(120)), filename="mod_120.py")
    assert ast_120["recommended_mode"] == "mode_c" and ast_120["mode_eligible"] is True
    ast_200 = router.compute_ast_risk_score("\n".join(f"x_{i} = {i}" for i in range(200)), filename="mod_200.py")
    assert ast_200["recommended_mode"] in ("mode_b", "mode_a") and ast_200["mode_eligible"] is False

    for prompt_text in (
        "Analizza il bug per cui avvia nk hub mostra un errore",
        "Spiega come funziona il blocco <env_capsule> nei messaggi dei subagent",
        "Vai a controllare i log", "Confermo che il bug esiste",
        "Analizza perche salta gate non viene applicato", "Spiega come disattiva prompt gate agisce sul router",
    ):
        assert router.is_gate_exempt(prompt_text) is False
        env_forced = router.build_meta_prompt_envelope(prompt_text, auto_bypass_readonly=False)
        assert env_forced["bypassed"] is False and env_forced["fsm_state"] == "AWAIT_CONFIRM"
        env = router.build_meta_prompt_envelope(prompt_text)
        if env["recommended_mode"] == "mode_d" and env.get("auto_bypass_eligible"):
            assert env["bypassed"] is True and env["fsm_state"] == "BYPASSED"
        else:
            assert env["bypassed"] is False and env["fsm_state"] == "AWAIT_CONFIRM"

    for valid_confirm in ("Vai pure avanti", "Confermo il piano"):
        assert router.is_gate_exempt(valid_confirm) is True
        assert router.build_meta_prompt_envelope(valid_confirm)["bypassed"] is True

    _verify_router_positional_and_capsule_invariants(tmp_path, capsys)


def _verify_router_positional_and_capsule_invariants(tmp_path: Path, capsys) -> None:
    """Verifica fallback CLI posizionale e generate_env_capsule senza falsi AP-2."""
    assert router_mod.main(["--meta-prompt-gate", "Analizza la resilienza del server contro i timeout RPC", "--json"]) == 0
    out_pos = json.loads(capsys.readouterr().out)
    assert "resilienza del server" in out_pos["optimized_meta_prompt"] and out_pos["fsm_state"] == "BYPASSED"
    assert out_pos["gate_mode"] == "SINGLE_GATE_MODE_D" and out_pos["bypass_reason"] == "READONLY_MODE_D_BYPASS"

    assert router_mod.main(["--meta-prompt-gate", "--force-gate", "Analizza la resilienza del server contro i timeout RPC", "--json"]) == 0
    out_forced = json.loads(capsys.readouterr().out)
    assert out_forced["fsm_state"] == "AWAIT_CONFIRM" and out_forced["bypassed"] is False

    router = VibeSprintRouter(workspace_root=tmp_path)
    capsule = router.generate_env_capsule()
    assert capsule == router_mod.generate_env_capsule(workspace_root=tmp_path)
    assert "ZERO_BLIND_VIEW_FILE:" in capsule and "MAX_WRITE_BATCH:" in capsule and len(capsule) // 4 < 235
    lint_res, lint_code = transcript_tools_mod.lint_prompt_text(f"{capsule}\nOpera come NK-Security-DAST-Auditor e analizza in sola lettura.")
    assert lint_code == 0 and lint_res["passed"] is True


def test_router_forensic_transcript_blind_read_and_no_burst(tmp_path: Path) -> None:
    """Verifica telemetria blind-read, write-burst (>=4) e regressione R1-C4 su analyze_compliance."""
    tp_forensic = tmp_path / "transcript_forensic.jsonl"
    tp_forensic.write_text(
        "\n".join([
            json.dumps({"step_index": 12, "source": "MODEL", "status": "ERROR", "output": "GetFileAttributesEx box1_gateway: The system cannot find the path specified.", "tool_calls": [{"name": "view_file", "args": {"Path": "box1_gateway/proxy.py"}}]}),
            json.dumps({"step_index": 84, "source": "MODEL", "status": "DONE", "output_tokens": 7136, "tool_calls": [{"name": "write_file", "args": {"Path": ".staging/a.py"}}, {"name": "write_file", "args": {"Path": ".staging/b.py"}}, {"name": "write_file", "args": {"Path": ".staging/c.py"}}, {"name": "write_file", "args": {"Path": ".staging/d.py"}}]}),
        ]) + "\n",
        encoding="utf-8",
    )
    comp = transcript_tools_mod.analyze_compliance(tp_forensic)
    assert comp["passed"] is True and comp["blind_read_errors"] == 1 and comp["write_burst_steps"] == 1

    tp_no_burst = tmp_path / "tp_no_write_burst.jsonl"
    tp_no_burst.write_text(
        "\n".join([
            json.dumps({"step_index": 85, "source": "MODEL", "status": "DONE", "output_tokens": 6000, "tool_calls": [{"name": "read_file", "args": {"Path": "scripts/nk_context_sentry.py"}}]}),
            json.dumps({"step_index": 86, "source": "MODEL", "status": "DONE", "output_tokens": 6100, "tool_calls": [{"name": "write_file", "args": {"Path": ".staging/a.py"}}, {"name": "write_file", "args": {"Path": ".staging/b.py"}}, {"name": "write_file", "args": {"Path": ".staging/c.py"}}]}),
        ]) + "\n",
        encoding="utf-8",
    )
    comp_no_burst = transcript_tools_mod.analyze_compliance(tp_no_burst)
    assert comp_no_burst["passed"] is True and comp_no_burst["write_burst_steps"] == 0


def test_procedi_anti_loop_confirmation_and_dashboard_nodes_routing() -> None:
    """Verifica procedi* <= 12w con esclusione shell-meta e routing 10 nodi / 6 agent."""
    router = VibeSprintRouter()
    assert router.is_gate_exempt("procedi e quando raggiungi la saturazione di contesto esegui un /compact") is True
    assert router.is_gate_exempt("procedi con l'implementazione") is True
    assert router.is_gate_exempt("procedi pure con la refactoring architetturale completa di tutti i moduli del sistema") is False
    assert router.is_gate_exempt("Vai a controllare i log") is False
    assert router.is_gate_exempt("Confermo che il bug esiste") is False
    assert router.is_gate_exempt("procedi | cat") is False and router.is_gate_exempt("procedi; ls") is False

    env_compact = router.build_meta_prompt_envelope("procedi e quando raggiungi la saturazione di contesto esegui un /compact")
    assert env_compact["fsm_state"] == "BYPASSED" and env_compact["bypassed"] is True

    node0_route = router.classify_prompt_intent("[0]")
    assert node0_route["primary_agent"] == "NK-Ideator" and node0_route["native_subagent"] == "NK-Arch-Specifier"
    node6_route = router.classify_prompt_intent("[6]")
    assert node6_route["primary_agent"] == "NK-Oracle-Evaluator" and node6_route["native_subagent"] == "NK-RSI-Auditor"
    node9_route = router.classify_prompt_intent("[9]")
    assert node9_route["primary_agent"] == "NK-Scribe-Memory" and node9_route["native_subagent"] == "NK-Scribe-Agent"
    hub_route = router.classify_prompt_intent("avvia nk orchestrator")
    assert len(router_mod.DASHBOARD_NODE_MAP) == 10
    assert router_mod._parse_dashboard_selector("[9]") == 9 and router_mod._parse_dashboard_selector("[10]") is None
    assert hub_route["native_subagent"] == "Orchestrator-Direct"


def test_p1_2_large_prompt_tail_requirements_compact_and_mode_d_tools_allowed() -> None:
    """Verifica [P1-2]: 8+ requisiti oltre 16KB, --compact senza troncamento e zero CRIT01_FORBIDDEN_TOOLS."""
    from _internal.nk_registry_indexer.taxonomy import CRIT01_FORBIDDEN_TOOLS, FORBIDDEN_PHANTOM_MCP_TOOLS

    router = VibeSprintRouter()
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
    assert len(reqs) >= 9 and any("TAIL_SENTINEL_REQ_8" in r for r in reqs)
    assert any("TAIL_FINAL_REQUIREMENT_9_TOKEN" in r for r in reqs) and "TAIL_FINAL_REQUIREMENT_9_TOKEN" in env["conceptual_mirror"]

    env_compact = router.build_meta_prompt_envelope(multi_req_prompt, compact=True)
    assert len(env_compact["requirements_r_ids"]) == len(reqs)
    assert any("TAIL_FINAL_REQUIREMENT_9_TOKEN" in r for r in env_compact["requirements_r_ids"])
    assert "TAIL_FINAL_REQUIREMENT_9_TOKEN" in env_compact["optimized_meta_prompt"]

    forbidden = set(CRIT01_FORBIDDEN_TOOLS) | set(FORBIDDEN_PHANTOM_MCP_TOOLS) | {"read_url_content"}
    t12 = (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n"
        "### 1. Identità e Percorsi Operativi\n"
        "- Workspace: g:/Il mio Drive/Antigravity/NK_Hub\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )
    for intent_res in (
        router.classify_prompt_intent(t12),
        router.classify_prompt_intent("[0]"),
        router.classify_prompt_intent("Analizza l'architettura attuale in sola lettura"),
        router.classify_prompt_intent("Spiega il flusso operativo", mode="mode_d"),
    ):
        tools = list(intent_res.get("tools_allowed", []))
        assert intent_res["read_only"] is True and tools and forbidden.isdisjoint(tools)


def test_router_domain_matcher_large_tail_subagents_and_shard_branches(tmp_path: Path) -> None:
    """Chiude i branch di domain_matcher.py su tail scan >16KB, override subagent e shard."""
    from _internal.vibe_sprint_router import domain_matcher as dm

    assert dm._has_audit_forensic_intent("esegui verifica copertura bandi") is False
    assert dm._has_audit_forensic_intent("esegui verifica forense tas") is True

    # Forza checks >= 32 occorrenze parziali non valide con keyword valida nella coda
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

    sh_dir = tmp_path / "shards"
    sh_dir.mkdir(parents=True)
    (sh_dir / "bad.json").write_text("{bad", encoding="utf-8")
    (sh_dir / "d3.json").write_text(json.dumps({"domain": {"domain_id": "DOM-03", "name": "B"}, "skills_index": {"S": {}}, "scripts_index": {"a.py": {}}, "intent_dispatch_table": {"kw_s": "mode_c", "kw_d": {"recommended_mode": "mode_d"}}}), encoding="utf-8")
    rehyd = dm._rehydrate_router_manifest_shards(tmp_path / "nk_registry_manifest.json", {"domains": {}, "shards": {"DOM-00": "x.json", "DOM-03": "shards/d3.json", "DOM-BAD": "shards/bad.json", "DOM-MISS": "shards/miss.json"}})
    assert "kw_s" in rehyd["intent_dispatch_table"] and "a.py" in rehyd["scripts_index"]


def test_router_transcript_and_cli_modes_and_compact_branches(
    tmp_path: Path, capsys: Any
) -> None:
    """Chiude i branch di transcript_and_cli.py su record estratti, validate-prompt, --files, --compact e CLI."""
    from _internal.vibe_sprint_router import transcript_and_cli as cli

    assert cli._extract_user_text_from_record({"source": "MODEL", "content": "hi"}) is None
    assert cli._extract_user_text_from_record({"type": "USER_INPUT", "content": "<CONTEXT_SUMMARY> skip"}) is None
    assert cli._extract_user_text_from_record({"type": "USER_INPUT", "content": ["", {"text": "Analizza tutto"}]}) == "Analizza tutto"

    assert router_mod.main(["--prompt-file", str(tmp_path / "missing.txt")]) == 1
    assert "Prompt file non trovato" in capsys.readouterr().err

    assert router_mod.main(["--validate-generated-prompt", "Usa /goal ora", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False
    assert router_mod.main(["--validate-generated-prompt", "__USE_PROMPT__", "--prompt", "Analizza il file A"]) == 0
    assert "Status: PASS" in capsys.readouterr().out

    assert router_mod.main(["--meta-prompt-gate", "--prompt", "Aggiorna bottone UI", "--compact"]) == 0
    assert "[L0-COMPACT]" in capsys.readouterr().out

    assert router_mod.main(["--files", "scripts/vibe_sprint_router.py", "--changed-lines", "200", "--mode", "mode_a", "--capsule", "--compact", "--json"]) == 0
    files_payload = json.loads(capsys.readouterr().out)
    assert files_payload["files"][0]["recommended_mode"] == "mode_a" and "tier1_capsule" in files_payload

    assert router_mod.main(["--classify-prompt", "Spiega router", "--capsule", "--json"]) == 0
    assert "tier1_capsule" in json.loads(capsys.readouterr().out)
    assert router_mod.main(["--capsule"]) == 0 and capsys.readouterr().out.strip()
    assert router_mod.main([]) == 0 and "VibeSprintRouter CLI ready" in capsys.readouterr().out


def test_p0_bug_01_composite_confirmations_o_meglio_xml_strip_and_l0_gate_file(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica chiusura P0-BUG-01: conferme composite, 'o meglio', strip XML e l0_gate_<cid>.json."""
    from _internal.vibe_sprint_router import transcript_and_cli as cli

    router = VibeSprintRouter()
    assert router.is_gate_exempt("approvo") is True
    assert router.is_gate_exempt("perfetto approvo") is True
    assert router.is_gate_exempt("Ok procedi ma prima valuta in sandbox") is False
    assert router.is_gate_exempt("Procedi con il piano e fai anche un report finale") is False
    assert router.is_gate_exempt("Ok procedi. Analizza anche il bug") is False

    stt_res = router.normalize_voice_stt_input("Modifica il modulo router. O meglio analizza i test")
    assert "Modifica il modulo router" in stt_res["cleaned_prompt"]
    assert router.classify_prompt_intent(stt_res["cleaned_prompt"])["read_only"] is False

    xml_rec = {
        "type": "USER_INPUT",
        "content": (
            "<USER_REQUEST>avvia nk hub</USER_REQUEST>\n"
            "<ADDITIONAL_METADATA>model=carbon</ADDITIONAL_METADATA>"
        ),
    }
    assert cli._extract_user_text_from_record(xml_rec) == "avvia nk hub"

    hooks_dir = tmp_path / "nk_hooks_test"
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_dir))
    monkeypatch.setenv("NK_CONVERSATION_ID", "conv_l0_test")
    assert router_mod.main(["--meta-prompt-gate", "--prompt", "Ottimizza e accorpa le skill", "--compact"]) == 0
    capsys.readouterr()
    l0_file = hooks_dir / "l0_gate_conv_l0_test.json"
    assert l0_file.is_file()
    l0_data = json.loads(l0_file.read_text(encoding="utf-8"))
    assert len(l0_data["turn_prompt_sha256"]) == 64 and l0_data["fsm_state"] == "AWAIT_CONFIRM" and l0_data["bypassed"] is False

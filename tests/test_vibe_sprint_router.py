# -*- coding: utf-8 -*-
"""
Nexus Keystone v5.2.0-STE100-Unified.
Modulo: test_vibe_sprint_router.py.
Valida profondita AST, routing Mode A/B/C/D, Meta-Prompt Gate, protocolli intrinseci e AP-10.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List, Tuple

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent

for _p in (
    _workspace_root / ".staging" / "scripts",
    _workspace_root / "scripts",
    _workspace_root,
):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _load_router_module():
    """Carica il modulo vibe_sprint_router dando priorita a .staging/scripts."""
    staging_target = _workspace_root / ".staging" / "scripts" / "vibe_sprint_router.py"
    prod_target = _workspace_root / "scripts" / "vibe_sprint_router.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("vibe_sprint_router", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vibe_sprint_router"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_transcript_tools_module():
    """Carica il modulo nk_transcript_tools dando priorita a .staging/scripts."""
    staging_target = _workspace_root / ".staging" / "scripts" / "nk_transcript_tools.py"
    prod_target = _workspace_root / "scripts" / "nk_transcript_tools.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("nk_transcript_tools", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nk_transcript_tools"] = mod
    spec.loader.exec_module(mod)
    return mod


router_mod = _load_router_module()
transcript_tools_mod = _load_transcript_tools_module()
VibeSprintRouter = router_mod.VibeSprintRouter


def test_vibe_sprint_router_real_ast_max_depth_and_routing(tmp_path: Path) -> None:
    """1. Verifica max_depth AST, selezione modalita e caricamento di tier1_active_capsule.json."""
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

    mem_dir = tmp_path / "nk_tracking" / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    capsule_file = mem_dir / "tier1_active_capsule.json"
    capsule_file.write_text(
        '{"status": "OK", "capsule_text": "Invariante Zero-Mock attivo", "token_count": 12, "token_cap": 350, "entries": []}',
        encoding="utf-8",
    )

    router_cap = VibeSprintRouter(workspace_root=tmp_path)
    loaded = router_cap.load_prewarmed_capsule()
    assert loaded["status"] == "OK"
    assert "Invariante Zero-Mock attivo" in loaded["capsule_text"]

    risk = router_cap.compute_ast_risk_score("def f(x: int) -> int:\n    return x + 1\n", "f.py")
    spec = router_cap.generate_inline_micro_spec("f.py", "Increment value", risk)
    assert "Tier-1 Capsule: Invariante Zero-Mock attivo" in spec


def test_vibe_sprint_router_stt_normalization_and_anti_loop_exemptions() -> None:
    """2. Verifica sostantivi astratti, normalizzazione vocale STT su primaLa e le 5 esenzioni anti-loop."""
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

    stt = router.normalize_voice_stt_input(
        "Modifica il file, anzi no analizza primaLa struttura di `myCamelVar` praticamente"
    )
    assert "prima La" in stt["cleaned_prompt"]
    assert "`myCamelVar`" in stt["cleaned_prompt"]
    assert any("primaLa -> prima La" in c for c in stt["voice_corrections_applied"])
    assert len(stt["voice_corrections_applied"]) >= 2

    assert router.is_gate_exempt("ok") is True
    assert router.is_gate_exempt("Confermo!") is True
    assert router.is_gate_exempt("procedi pure") is True
    assert router.is_gate_exempt("procedi con il piano") is True
    assert router.is_gate_exempt("procedi alla creazione dell'implementation plan") is True
    assert router.is_gate_exempt("avvia nk") is True
    assert router.is_gate_exempt("[14]") is True
    assert router.is_gate_exempt("Proceed") is True
    assert router.is_gate_exempt("premi proceed") is True
    assert router.is_gate_exempt("<env_capsule>\nTEST_RUNNER: pytest\n</env_capsule>") is True
    assert router.is_gate_exempt("!diretto analizza il codice") is True
    assert router.is_gate_exempt("disattiva prompt gate") is True
    assert router.is_gate_exempt("Progetta un nuovo modulo asincrono per il router") is False


def test_vibe_sprint_router_meta_prompt_envelope_and_cli() -> None:
    """3. Verifica build_meta_prompt_envelope, flag CLI e resolve_intrinsic_vibe_protocols sul caso Bandi."""
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

    t12_handoff_prompt = (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n"
        "### 1. Identità e Percorsi Operativi\n"
        "- Workspace: g:/Il mio Drive/Antigravity/NK_Hub\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )
    env_t12 = router.build_meta_prompt_envelope(t12_handoff_prompt)
    assert env_t12["fsm_state"] == "BYPASSED"
    assert env_t12["bypassed"] is True
    assert env_t12.get("bypass_reason") == "STATE_HANDOFF_STANDBY"
    assert env_t12.get("standby_mode") is True
    assert env_t12["intrinsic_protocols"] == []
    assert env_t12["autonomous_slash_equivalence"]["goal"] is False
    assert env_t12["autonomous_slash_equivalence"]["plan"] is False
    if hasattr(router, "evaluate_meta_prompt_gate"):
        eval_t12 = router.evaluate_meta_prompt_gate(t12_handoff_prompt)
        assert eval_t12["fsm_state"] == "BYPASSED"
        assert eval_t12.get("bypass_reason") == "STATE_HANDOFF_STANDBY"
        assert eval_t12.get("standby_mode") is True
        assert eval_t12["intrinsic_protocols"] == []
        assert eval_t12["autonomous_slash_equivalence"]["goal"] is False
        assert eval_t12["autonomous_slash_equivalence"]["plan"] is False

    rc1 = router_mod.main(
        ["--meta-prompt-gate", "--prompt", "Analizza primaLa copertura", "--json"]
    )
    assert rc1 == 0
    rc2 = router_mod.main(
        ["--no-gate", "--prompt", "Analizza primaLa copertura", "--json"]
    )
    assert rc2 == 0

    default_res = router.resolve_intrinsic_vibe_protocols("Aggiorna colore pulsante", "mode_c")
    assert "INTRINSIC_GOAL" in default_res["intrinsic_protocols"]
    assert default_res["autonomous_slash_equivalence"]["goal"] is True

    bandi_prompt = (
        "Esegui un'analisi approfondita multi-livello del progetto Bandi; "
        "inoltre progetta il piano di implementazione e risolvi i difetti fino a convergenza"
    )
    bandi_res = router_mod.resolve_intrinsic_vibe_protocols(bandi_prompt, "mode_a")
    assert bandi_res["intrinsic_protocols"] == [
        "INTRINSIC_GOAL",
        "INTRINSIC_BOOST",
        "INTRINSIC_PLAN",
    ]
    assert bandi_res["autonomous_slash_equivalence"]["goal"] is True
    assert bandi_res["autonomous_slash_equivalence"]["boost"] is True
    assert bandi_res["autonomous_slash_equivalence"]["plan"] is True

    env_bandi = router.build_meta_prompt_envelope(bandi_prompt)
    assert "INTRINSIC_GOAL" in env_bandi["intrinsic_protocols"]
    assert "INTRINSIC_BOOST" in env_bandi["intrinsic_protocols"]
    assert "INTRINSIC_PLAN" in env_bandi["intrinsic_protocols"]
    assert env_bandi["autonomous_slash_equivalence"]["goal"] is True
    assert env_bandi["autonomous_slash_equivalence"]["boost"] is True
    assert env_bandi["autonomous_slash_equivalence"]["plan"] is True
    assert "Protocolli Intrinseci Auto-Attivati:" in env_bandi["optimized_meta_prompt"]
    assert env_bandi["optimized_meta_prompt"].startswith("[META-PROMPT L0 | Mode:")


def test_vibe_sprint_router_l0_rendered_markdown_and_clause_split(capsys) -> None:
    """4. Verifica guardia AP-10, rendered_markdown L0, mancata rottura su punti e output CLI."""
    passive_prompt = (
        "Per ottenere risultati migliori puoi utilizzare anche il comando /goal o /boost "
        "oppure digita il comando /plan."
    )
    res_router = router_mod.lint_nk_prompt(passive_prompt)
    assert res_router["passed"] is False
    assert any(v["code"] == "AP-10" for v in res_router["violations"])

    res_tools, code_tools = transcript_tools_mod.lint_prompt_text(passive_prompt)
    assert code_tools == 1
    assert res_tools["passed"] is False
    assert any(v["code"] == "AP-10" for v in res_tools["violations"])

    rule_prohibition_text = (
        "Nessun agente chiede all'utente di digitare manualmente /goal, /boost, /plan o /implementation (AP-10).\n"
        "Vieta di dire: puoi utilizzare anche il comando /goal."
    )
    clean_router = router_mod.lint_nk_prompt(rule_prohibition_text)
    assert not any(v["code"] == "AP-10" for v in clean_router["violations"])

    clean_tools, _ = transcript_tools_mod.lint_prompt_text(rule_prohibition_text)
    assert not any(v["code"] == "AP-10" for v in clean_tools["violations"])

    router = VibeSprintRouter()
    prompt_with_dots = (
        "Aggiorna PATCH_NOTES.md e scripts/vibe_sprint_router.py per la release v4.8.0 in .staging; "
        "inoltre verifica la suite di test"
    )
    env = router.build_meta_prompt_envelope(prompt_with_dots)
    assert "rendered_markdown" in env
    md = env["rendered_markdown"]
    assert "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]" in md
    assert "Specchio Concettuale" in md
    assert "R1:" in md
    assert "R2:" in md
    assert "- **Flusso Post-Conferma L0:**" in md
    for field_name in ("conceptual_mirror", "optimized_meta_prompt", "rendered_markdown"):
        assert "Brief" in env[field_name]
        assert "implementation_plan.md" in env[field_name]
        assert "RequestFeedback: true" in env[field_name]
    assert (
        "[MANDATORY-VISIBLE-L0]: Mostra obbligatoriamente questo blocco nel campo content "
        "della risposta PRIMA o INSIEME a ask_question (vietato content_len=0)."
    ) in md
    assert router_mod.format_meta_prompt_markdown(env) == md

    env_confirm = router.build_meta_prompt_envelope("procedi")
    assert "INTRINSIC_PLAN" in env_confirm["intrinsic_protocols"]
    assert env_confirm["autonomous_slash_equivalence"]["plan"] is True
    assert env_confirm["autonomous_slash_equivalence"]["implementation"] is True

    reqs = env["requirements_r_ids"]
    assert len(reqs) == 2
    assert "PATCH_NOTES.md" in reqs[0]
    assert "v4.8.0" in reqs[0]
    assert not any(r.startswith("R2: md") for r in reqs)

    rc = router_mod.main(["--meta-prompt-gate", "--prompt", prompt_with_dots])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "[META-PROMPT-GATE]" in captured
    assert "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]" in captured
    assert "Specchio Concettuale" in captured


def test_vibe_sprint_router_inplace_diff_loc_short_confirm_and_negated_write(
    tmp_path: Path,
) -> None:
    """5. Verifica _estimate_changed_loc in-place, conferme 'ok procedi', negazione verbi e Mode D esteso."""
    prod_dir = tmp_path / "src_app"
    stag_dir = tmp_path / ".staging" / "src_app"
    prod_dir.mkdir(parents=True, exist_ok=True)
    stag_dir.mkdir(parents=True, exist_ok=True)

    prod_file = prod_dir / "service.py"
    stag_file = stag_dir / "service.py"
    prod_lines = [f"x_{i} = {i}" for i in range(10)]
    stag_lines = list(prod_lines)
    stag_lines[2] = "x_2 = 200"
    stag_lines[5] = "x_5 = 500"
    stag_lines[8] = "x_8 = 800"
    prod_file.write_text("\n".join(prod_lines) + "\n", encoding="utf-8")
    stag_file.write_text("\n".join(stag_lines) + "\n", encoding="utf-8")

    router = VibeSprintRouter(workspace_root=tmp_path)
    assert router._estimate_changed_loc(files=["src_app/service.py"]) == 3
    assert router._estimate_changed_loc(files=[str(prod_file)]) == 3
    assert router._estimate_changed_loc(files=[str(stag_file)]) == 3

    for short_conf in (
        "ok procedi",
        "procedi",
        "confermo",
        "vai",
        "si procedi pure",
        "procedi pure",
        "procedi con il piano",
        "procedi alla creazione dell'implementation plan",
    ):
        assert router.is_gate_exempt(short_conf) is True
        env_c = router.build_meta_prompt_envelope(short_conf)
        assert env_c["fsm_state"] == "BYPASSED"
        assert env_c["bypassed"] is True

    assert router.is_gate_exempt("attiva prompt gate e analizza il modulo") is False

    neg_prompt = "Non modificare nulla, solo analizza come funziona e spiega cosa fa"
    assert router_mod._has_imperative_write_keyword(neg_prompt) is False
    intent_neg = router.classify_prompt_intent(neg_prompt)
    assert intent_neg["recommended_mode"] == "mode_d"
    assert intent_neg["read_only"] is True

    long_anzi = (
        "Nel modulo di autenticazione dobbiamo verificare tutti i permessi degli utenti "
        "registrati nel database, anzi no solo quelli attivi"
    )
    stt_long = router.normalize_voice_stt_input(long_anzi)
    assert "modulo di autenticazione" in stt_long["cleaned_prompt"]
    assert "solo quelli attivi" in stt_long["cleaned_prompt"]
    assert router_mod._has_imperative_write_keyword("non devi a modificare il codice") is False
    assert (
        router_mod._has_imperative_write_keyword(
            "non voglio assolutamente in alcun modo modificare il codice, analizza solo"
        )
        is False
    )
    stt_m03 = router.normalize_voice_stt_input(
        "crea un file temporaneo nel progetto, anzi no analizza solo la struttura"
    )
    assert "crea un file" not in stt_m03.get("normalized_text", stt_m03["cleaned_prompt"]).lower()
    assert (
        router.is_gate_exempt(
            "procedi pure con la refactoring architetturale completa di tutti i moduli del sistema"
        )
        is False
    )
    env_m33 = router_mod.build_meta_prompt_envelope(
        "Spiega cosa fa il modulo X", auto_bypass_readonly=True
    )
    assert env_m33["fsm_state"] == "BYPASSED"
    assert env_m33["auto_bypass_eligible"] is True
    assert router.is_gate_exempt("ok procedi cancella tutto subito") is False
    assert router_mod.is_gate_exempt("ok procedi cancella tutto subito") is False
    stt_m33 = router.normalize_voice_stt_input("Modifica il file A, anzi no fermati")
    stt_m33_str = stt_m33["cleaned_prompt"] if isinstance(stt_m33, dict) else stt_m33
    assert stt_m33_str == "fermati"
    assert "review" in router_mod.MODE_D_KEYWORDS
    assert "elenca" in router_mod.MODE_D_KEYWORDS


TECH_BRANDS_AND_IDENTIFIERS: Tuple[str, ...] = (
    "GitHub",
    "GitLab",
    "FastAPI",
    "JavaScript",
    "TypeScript",
    "PostgreSQL",
    "SQLite",
    "GraphQL",
    "PyTorch",
    "TensorFlow",
    "OpenAI",
    "DeepSeek",
    "PowerShell",
    "MacBook",
    "iPhone",
    "iPad",
    "OneDrive",
    "SharePoint",
    "WordPress",
    "YouTube",
    "LinkedIn",
    "StackOverflow",
    "PyTest",
    "DevOps",
    "DataFrame",
    "AsyncIO",
    "WebSocket",
    "Protobuf",
    "LangChain",
    "LlamaIndex",
    "AutoGen",
    "CrewAI",
    "ChromaDB",
    "MongoDB",
    "MariaDB",
    "DuckDB",
    "ClickHouse",
    "RabbitMQ",
    "ZeroMQ",
    "KeyCloak",
    "OAuth",
    "OpenTelemetry",
    "CloudFlare",
    "DigitalOcean",
    "HuggingFace",
    "vibe_sprint_router",
    "VibeSprintRouter",
    "compute_ast_risk_score",
    "resolve_intrinsic_vibe_protocols",
    "build_meta_prompt_envelope",
)

PROMPT_CORPUS_30: Tuple[Tuple[str, str, List[str]], ...] = (
    ("Spiega come funziona il modulo ast_repo_mapper.py", "mode_d", ["INTRINSIC_GOAL"]),
    ("Qual è la differenza tra Tier-1 e Tier-3 memory?", "mode_c", ["INTRINSIC_GOAL"]),
    ("Mostra lo stato della telemetria RSI attuale", "mode_c", ["INTRINSIC_GOAL"]),
    ("Elenca i 5 sub-agenti nativi registrati nel manifest", "mode_d", ["INTRINSIC_GOAL"]),
    (
        "Analizza a fondo l'architettura 3-Tier ed effettua un audit multi-livello dei colli di bottiglia",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    (
        "Analizza e valuta in profondità le vulnerabilità SAST e DAST dell'intero ecosistema",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    (
        "Confronta le metriche di convergenza con un'ispezione olistica stato dell'arte",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    (
        "Analizza lo stato dell'arte dell'implementazione attuale e fai una valutazione architetturale",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    ("Correggi il refuso nella stringa di log di micro_hud_renderer.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Aggiorna il valore di default del parametro timeout in platform_runner.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Aggiungi un commento docstring alla funzione helper in nk_context_sentry.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Formatta l'output JSON del comando locate in nk_transcript_tools.py", "mode_c", ["INTRINSIC_GOAL"]),
    ("Rinomina la variabile locale tmp_val in clean_val dentro micro_hud_renderer.py", "mode_c", ["INTRINSIC_GOAL"]),
    (
        "Ottimizza con analisi approfondita la regex di parsing STT in vibe_sprint_router.py",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    (
        "Rendi più robusto ed efficiente con benchmark il calcolo dell'hash SHA-256 in win32_2pc_engine.py",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    (
        "Perfeziona con valutazione approfondita la logica di fallback per i file corrotti in nk_hook_gate.py",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST"],
    ),
    (
        "Implementa un nuovo modulo di caching e aggiorna i test e la documentazione",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_PLAN"],
    ),
    (
        "Progetta il piano di refactoring per nk_session_bootstrap.py e nk_registry_indexer.py",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_PLAN"],
    ),
    (
        "Crea una nuova skill di validazione e registra l'indice in agent_manifest.json",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_PLAN"],
    ),
    (
        "Modifica e implementa il contratto IPC in nk_ipc_contracts.py; inoltre aggiorna tutti i test correlati",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_PLAN"],
    ),
    (
        "Aggiungi un nuovo sottocomando CLI a nk_transcript_tools.py e prepara la roadmap di rilascio",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_PLAN"],
    ),
    (
        "Esegui un'analisi approfondita multi-livello del progetto Bandi; inoltre progetta il piano di implementazione e risolvi i difetti fino a convergenza",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Riprogetta l'architettura di sicurezza di nk_hook_gate.py con un'analisi approfondita e implementa i work package in .staging",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Analizza a fondo i colli di bottiglia di memoria 3-Tier; inoltre pianifica la migrazione SQLite WAL e verifica la suite",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Sviluppa un sistema completo di auto-healing multi-file con potenziamento massivo della copertura test",
        "mode_a",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Effettua uno stress test architetturale end-to-end; inoltre crea il piano di consolidamento della Tetralogia",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Ingegnerizza e implementa con strategia approfondita il protocollo Intrinsic Vibe Engine in vibe_sprint_router.py e aggiorna AGENTS.md",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Ottimizza con analisi multi-livello l'intero flusso di orchestrazione Hub-and-Spoke e pianifica gli step di rilascio",
        "mode_d",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Modifica il file A, anzi no analizza primaLa struttura di GitHub e FastAPI in profondità; inoltre crea un piano d'azione",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
    (
        "Praticamente cioè esegui un audit approfondito di PyTorch e TypeScript e progetta i work package di integrazione",
        "mode_c",
        ["INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"],
    ),
)


def test_vectorized_stt_brand_preservation_matrix() -> None:
    """6. Verifica vettorialmente che 50 brand tecnici non vengano spezzati ma i typo italiani si."""
    router = VibeSprintRouter()
    for brand in TECH_BRANDS_AND_IDENTIFIERS:
        prompt = f"Analizza l'integrazione di {brand} nel modulo core senza regressioni"
        res = router.normalize_voice_stt_input(prompt)
        assert brand in res["cleaned_prompt"], (
            f"Brand/identificatore '{brand}' corrotto da STT in: {res['cleaned_prompt']}"
        )

    glued_cases = [
        ("analizza primaLa struttura", "prima La"),
        ("verifica tuttoIl modulo", "tutto Il"),
        ("controlla ancheLa copertura", "anche La"),
        ("esegui soloUn test rapido", "solo Un"),
        ("modifica dentroIl file target", "dentro Il"),
        ("sposta versoLa directory staging", "verso La"),
        ("aggiorna sottoIl limite previsto", "sotto Il"),
        ("porta oltreIl livello minimo", "oltre Il"),
        ("inserisci senzaUn errore", "senza Un"),
        ("ottiene cosìUn risultato stabile", "così Un"),
        ("imposta piùUn valore valido", "più Un"),
        ("trova giàUn record esistente", "già Un"),
    ]
    for raw_text, expected_split in glued_cases:
        res = router.normalize_voice_stt_input(raw_text)
        assert expected_split in res["cleaned_prompt"], (
            f"Atteso '{expected_split}' in '{res['cleaned_prompt']}' per input '{raw_text}'"
        )


def test_vectorized_intrinsic_prompt_30_matrix() -> None:
    """7. Verifica vettorialmente 30 prompt reali di Vibe Coding per protocolli intrinseci e L0."""
    router = VibeSprintRouter()
    for prompt, expected_mode, expected_protocols in PROMPT_CORPUS_30:
        env = router.build_meta_prompt_envelope(prompt)
        assert env["bypassed"] is False
        assert env["fsm_state"] == "AWAIT_CONFIRM"
        assert env["recommended_mode"] == expected_mode

        actual_protocols = env["intrinsic_protocols"]
        for proto in expected_protocols:
            assert proto in actual_protocols, (
                f"Protocollo '{proto}' mancante per prompt: '{prompt}' (ottenuto: {actual_protocols})"
            )

        slash_eq = env["autonomous_slash_equivalence"]
        assert slash_eq["goal"] is ("INTRINSIC_GOAL" in actual_protocols)
        assert slash_eq["boost"] is ("INTRINSIC_BOOST" in actual_protocols)
        assert slash_eq["plan"] is ("INTRINSIC_PLAN" in actual_protocols)
        assert slash_eq["implementation"] is ("INTRINSIC_PLAN" in actual_protocols)

        assert env["optimized_meta_prompt"].startswith("[META-PROMPT L0 | Mode:")
        assert "Protocolli Intrinseci Auto-Attivati:" in env["optimized_meta_prompt"]
        assert "R1:" in env["optimized_meta_prompt"]


def test_vectorized_ap10_meta_prompt_linter_suite() -> None:
    """8. Verifica vettorialmente che AP-10 blocchi suggerimenti passivi ma consenta regole di divieto."""
    forbidden_Passive_suggestions = [
        "Per approfondire puoi utilizzare anche il comando /goal nel terminale.",
        "Ti consiglio di usare /boost per potenziare la richiesta.",
        "Digita il comando /plan per generare il piano di implementazione.",
        "Puoi invocare /implementation per procedere con i work package.",
        "Usa il comando `/goal` oppure `/boost` per migliorare il prompt.",
    ]
    for bad_text in forbidden_Passive_suggestions:
        r_lint = router_mod.lint_nk_prompt(bad_text)
        assert r_lint["passed"] is False, f"Atteso blocco AP-10 per: {bad_text}"
        assert any(v["code"] == "AP-10" for v in r_lint["violations"])

        t_lint, exit_code = transcript_tools_mod.lint_prompt_text(bad_text)
        assert exit_code == 1
        assert t_lint["passed"] is False
        assert any(v["code"] == "AP-10" for v in t_lint["violations"])

    allowed_constitutional_texts = [
        "Nessun agente chiede all'utente di digitare manualmente /goal, /boost, /plan o /implementation (AP-10).",
        "È vietato suggerire passivamente di usare il comando /goal o /boost.",
        "Non chiedere mai di invocare /plan: il router attiva INTRINSIC_PLAN autonomamente.",
        "Esegui l'analisi architetturale del modulo e genera l'artefatto implementation_plan.md.",
    ]
    for ok_text in allowed_constitutional_texts:
        r_lint = router_mod.lint_nk_prompt(ok_text)
        assert not any(v["code"] == "AP-10" for v in r_lint["violations"]), (
            f"Falso positivo AP-10 su testo legittimo: {ok_text}"
        )

        t_lint, _ = transcript_tools_mod.lint_prompt_text(ok_text)
        assert not any(v["code"] == "AP-10" for v in t_lint["violations"]), (
            f"Falso positivo AP-10 (transcript_tools) su testo legittimo: {ok_text}"
        )


def test_mode_c_max_loc_boundary_and_anti_bypass_hardening() -> None:
    """9. Verifica il confine MODE_C_MAX_LOC==150 (MUT-01) e blocca i falsi bypass L0 (B3.2)."""
    router = VibeSprintRouter()
    assert VibeSprintRouter.MODE_C_MAX_LOC == 150
    assert router.MODE_C_MAX_LOC == 150

    res_120 = router.classify_prompt_intent(
        "Modifica la funzione di calcolo in modulo.py", changed_lines=120
    )
    assert res_120["recommended_mode"] == "mode_c"
    assert res_120["fast_bypass_eligible"] is True

    res_200 = router.classify_prompt_intent(
        "Modifica la funzione di calcolo in modulo.py", changed_lines=200
    )
    assert res_200["recommended_mode"] in ("mode_b", "mode_a")
    assert res_200["recommended_mode"] == "mode_b"
    assert res_200["fast_bypass_eligible"] is False

    code_120 = "\n".join(f"x_{i} = {i}" for i in range(120))
    ast_120 = router.compute_ast_risk_score(code_120, filename="mod_120.py")
    assert ast_120["recommended_mode"] == "mode_c"
    assert ast_120["mode_eligible"] is True

    code_200 = "\n".join(f"x_{i} = {i}" for i in range(200))
    ast_200 = router.compute_ast_risk_score(code_200, filename="mod_200.py")
    assert ast_200["recommended_mode"] in ("mode_b", "mode_a")
    assert ast_200["mode_eligible"] is False

    non_bypass_prompts = (
        "Analizza il bug per cui avvia nk hub mostra un errore",
        "Spiega come funziona il blocco <env_capsule> nei messaggi dei subagent",
        "Vai a controllare i log",
        "Confermo che il bug esiste",
        "Analizza perche salta gate non viene applicato",
        "Spiega come disattiva prompt gate agisce sul router",
    )
    for prompt_text in non_bypass_prompts:
        assert router.is_gate_exempt(prompt_text) is False, (
            f"Falso bypass rilevato per: {prompt_text}"
        )
        env = router.build_meta_prompt_envelope(prompt_text)
        assert env["bypassed"] is False, (
            f"Envelope erroneamente bypassed per: {prompt_text}"
        )
        assert env["fsm_state"] == "AWAIT_CONFIRM"

    for valid_confirm in ("Vai pure avanti", "Confermo il piano"):
        assert router.is_gate_exempt(valid_confirm) is True
        env_ok = router.build_meta_prompt_envelope(valid_confirm)
        assert env_ok["bypassed"] is True
        assert env_ok["fsm_state"] == "BYPASSED"

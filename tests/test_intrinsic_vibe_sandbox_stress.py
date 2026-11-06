#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite di stress avversariale (DOM-04) in Shadow Sandbox per il motore Vibe Routing e Super Meta-Prompt Gate.
Eseguita in isolamento totale senza bias del creatore su 5 livelli (S1..S5).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if _ROOT.name == ".staging":
    _ROOT = _ROOT.parent

SANDBOX_ROOT = _ROOT

for _cand in (
    _ROOT,
    _ROOT / "scripts",
    _ROOT / ".staging" / "scripts",
):
    if _cand.exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))


def _load_target_module(mod_name: str, filename: str):
    staged_p = _ROOT / ".staging" / "scripts" / filename
    prod_p = _ROOT / "scripts" / filename
    target_p = staged_p if staged_p.is_file() else prod_p
    spec = importlib.util.spec_from_file_location(mod_name, str(target_p))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


vsr = _load_target_module("vibe_sprint_router", "vibe_sprint_router.py")
ntt = _load_target_module("nk_transcript_tools", "nk_transcript_tools.py")


# ============================================================================
# LIVELLO S1: Voice STT & Tech Brand Preservation
# ============================================================================

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
    "OpenAI",
    "DeepMind",
    "PowerShell",
    "DevOps",
    "YouTube",
    "MacBook",
    "iPhone",
    "NextJS",
    "TailwindCSS",
)


@pytest.mark.parametrize("brand", TECH_BRANDS_AND_IDENTIFIERS)
def test_s1_tech_brand_preserved_in_voice_stt(brand: str) -> None:
    """Verifica che i brand tecnici PascalCase/CamelCase non vengano spezzati da normalize_voice_stt_input."""
    raw = f"Analizza primaLa repo su {brand} e modificaIl connettore creando creiUna pipeline."
    res = vsr.normalize_voice_stt_input(raw, workspace_root=SANDBOX_ROOT)
    cleaned = res["cleaned_prompt"]
    assert brand in cleaned, (
        f"Brand '{brand}' corrotto da STT splitter: '{cleaned}' "
        f"(splits={res['camelcase_splits']})"
    )
    assert "prima La" in cleaned
    assert "modifica Il" in cleaned


def test_s1_fused_italian_stt_errors_are_split() -> None:
    """Verifica che i veri errori vocali STT (parola minuscola + Iniziale Maiuscola) vengano separati."""
    raw = "Controlla primaLa configurazione, modificaIl file e creaUna nuova funzione"
    res = vsr.normalize_voice_stt_input(raw, workspace_root=SANDBOX_ROOT)
    cleaned = res["cleaned_prompt"]
    assert "prima La" in cleaned
    assert "modifica Il" in cleaned
    assert "crea Una" in cleaned
    assert len(res["camelcase_splits"]) == 3


# ============================================================================
# LIVELLO S2: Clause Splitting & Italian Discourse Connectors
# ============================================================================

S2_INLINE_CONNECTOR_PROMPTS: Tuple[Tuple[str, str], ...] = (
    (
        "Dovrai fare poi un'analisi approfondita e una soluzione RSI completa",
        "dovrai fare",
    ),
    (
        "Bisogna andare poi a creare una suite di test per validare i casi reali",
        "andare",
    ),
    (
        "Voglio vedere inoltre i risultati completi del benchmark in sandbox",
        "voglio vedere",
    ),
    (
        "Potresti controllare poi lo stato dei test senza toccare i file di produzione",
        "potresti controllare",
    ),
)


@pytest.mark.parametrize("prompt,truncated_fragment", S2_INLINE_CONNECTOR_PROMPTS)
def test_s2_inline_poi_inoltre_does_not_truncate_verb_object(
    prompt: str, truncated_fragment: str
) -> None:
    """Verifica che 'poi' o 'inoltre' dentro un predicato verbale non tronchino il verbo dal complemento oggetto."""
    env = vsr.build_meta_prompt_envelope(prompt, workspace_root=SANDBOX_ROOT)
    r_ids: List[str] = env["requirements_r_ids"]
    for req in r_ids:
        body = req.split(":", 1)[1].strip().lower() if ":" in req else req.lower()
        assert body != truncated_fragment.lower(), (
            f"Clausola troncata artificialmente su connettore interno: '{req}' in {r_ids}"
        )


# ============================================================================
# LIVELLO S3: Conversational & Future/Subjunctive Write Intent + Intrinsic Plan
# ============================================================================

S3_CONVERSATIONAL_WRITE_PROMPTS: Tuple[str, ...] = (
    "Voglio che crei una suite di test per fare stress test e verificare i casi reali, "
    "implementerai le modifiche e farai l'aggiornamento GitHub",
    "Svilupperai un modulo di validazione per l'analisi dei contratti e modificherai lo script",
    "Vorrei che tu aggiorni la pipeline di benchmark e scriva i nuovi test di regressione",
    "Dovrai creare un parser per la ricerca bandi e correggere il bug nel router",
    "Aggiungi il supporto per l'analisi semantica e sistema il validatore dei prompt",
)


@pytest.mark.parametrize("prompt", S3_CONVERSATIONAL_WRITE_PROMPTS)
def test_s3_conversational_and_future_write_intent_not_mode_d(prompt: str) -> None:
    """Verifica che i prompt con verbi di scrittura al congiuntivo/futuro/infinito non cadano in Mode D Read-Only."""
    intent = vsr.classify_prompt_intent(prompt, workspace_root=SANDBOX_ROOT)
    assert intent["recommended_mode"] != "mode_d", (
        f"Prompt con chiaro intento di scrittura classificato erroneamente come mode_d: "
        f"{intent}"
    )
    assert intent["read_only"] is False


@pytest.mark.parametrize("prompt", S3_CONVERSATIONAL_WRITE_PROMPTS)
def test_s3_conversational_write_activates_intrinsic_plan(prompt: str) -> None:
    """Verifica che i prompt architetturali/implementativi al futuro o congiuntivo attivino INTRINSIC_PLAN."""
    env = vsr.build_meta_prompt_envelope(prompt, workspace_root=SANDBOX_ROOT)
    assert env["recommended_mode"] != "mode_d"
    assert "INTRINSIC_PLAN" in env["intrinsic_protocols"], (
        f"INTRINSIC_PLAN non attivato per prompt implementativo: {env['intrinsic_protocols']}"
    )
    assert env["autonomous_slash_equivalence"]["plan"] is True
    assert env["autonomous_slash_equivalence"]["implementation"] is True


# ============================================================================
# LIVELLO S4: Matrice 30+ Casi Reali (/goal, /boost, /plan & Esenzioni Anti-Loop)
# ============================================================================

# Tupla: (id_caso, prompt, expected_exempt, expected_mode_not_d_or_exact, expected_protocols_subset)
S4_REAL_WORLD_MATRIX: Tuple[Tuple[str, str, bool, str, Tuple[str, ...]], ...] = (
    # 1-5: Esenzioni Anti-Loop (RULE-00.6)
    ("C01_short_ok", "ok", True, "any", ("INTRINSIC_GOAL",)),
    ("C02_short_proceed", "Proceed", True, "any", ("INTRINSIC_GOAL",)),
    ("C03_short_confermo", "confermo!", True, "any", ("INTRINSIC_GOAL",)),
    ("C04_node_select_0", "[0]", True, "any", ("INTRINSIC_GOAL",)),
    ("C05_node_select_14", "[14]", True, "any", ("INTRINSIC_GOAL",)),
    ("C06_onboarding_avvia_nk", "avvia ambiente nk", True, "any", ("INTRINSIC_GOAL",)),
    ("C07_onboarding_start_hub", "start hub", True, "any", ("INTRINSIC_GOAL",)),
    ("C08_diretto_bypass", "!diretto Correggi il typo nel commento", True, "mode_c", ("INTRINSIC_GOAL",)),
    ("C09_env_capsule_subagent", "<env_capsule>\nUsa pytest.\n</env_capsule>\nVerifica il modulo.", True, "any", ("INTRINSIC_GOAL",)),
    ("C10_toggle_gate_off", "disattiva prompt gate", True, "any", ("INTRINSIC_GOAL",)),
    # 11-16: Discovery & Benchmark Read-Only (Mode D + INTRINSIC_BOOST)
    ("C11_bandi_discovery", "Esegui un audit e benchmark sulla copertura bandi in modalità read-only", False, "mode_d", ("INTRINSIC_BOOST",)),
    ("C12_stato_arte_web", "Fai una ricerca sullo stato dell'arte dei parser RAG e produci un report analitico", False, "mode_d", ("INTRINSIC_BOOST",)),
    ("C13_censimento_fonti", "Analizza la copertura attuale e fai un censimento delle fonti attive", False, "mode_d", ("INTRINSIC_BOOST",)),
    ("C14_sast_audit_ro", "Esegui un audit di sicurezza SAST L1/L2/L3 in sola lettura", False, "mode_d", ("INTRINSIC_BOOST",)),
    ("C15_esplora_arch", "Esplora la mappatura dei moduli e analizza le dipendenze", False, "mode_d", ("INTRINSIC_BOOST",)),
    ("C16_quanti_bandi", "Quanti bandi sono presenti nel dataset attuale? Analizza le statistiche", False, "mode_d", ("INTRINSIC_BOOST",)),
    # 17-22: Task Rapidi Mode C (Vibe-Sprint)
    ("C17_mode_c_fix_log", "Modifica il messaggio di log in scripts/vibe_sprint_router.py", False, "mode_c", ("INTRINSIC_GOAL",)),
    ("C18_mode_c_create_helper", "Crea una piccola funzione helper per formattare i timestamp", False, "mode_c", ("INTRINSIC_GOAL", "INTRINSIC_PLAN")),
    ("C19_mode_c_refactor_var", "Fai refactoring del nome variabile nel modulo di cache", False, "mode_c", ("INTRINSIC_GOAL",)),
    ("C20_mode_c_sync_readme", "Sincronizza la versione nel file README.md", False, "mode_c", ("INTRINSIC_GOAL",)),
    ("C21_mode_c_progetta_box", "Progetta un piccolo badge HTML per lo stato del task", False, "mode_c", ("INTRINSIC_GOAL", "INTRINSIC_PLAN")),
    ("C22_mode_c_test_rapido", "Verifica e risolvi il warning nel test unitario", False, "mode_c", ("INTRINSIC_GOAL",)),
    # 23-28: Task Complessi / Multi-Fase / Conversazionali (Mode A/B + Goal + Boost + Plan)
    (
        "C23_user_actual_voice_prompt",
        "Voglio che crei una suite di test per fare stress test sul nuovo sistema che hai appena implementato "
        "per verificare se in tutti i casi reali in cui io faccio dei prompt dove non vado a scrivere "
        "specificatamente /goal /boost /implementation, il sistema riesca comunque ad attivarsi. "
        "Dovrai fare poi un'analisi e una soluzione RSI, implementerai le modifiche e farai l'aggiornamento GitHub.",
        False,
        "not_mode_d",
        ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"),
    ),
    (
        "C24_bandi_full_rsi_cycle",
        "FASE 1: Analizza i portali regionali dei bandi. FASE 2: Implementa in .staging/ i nuovi estrattori "
        "asincroni e raggiungi la convergenza RSI fino a Q=100.",
        False,
        "mode_a",
        ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"),
    ),
    (
        "C25_multi_agent_architecture",
        "Pianifica e sviluppa una nuova architettura multi-agent con analisi approfondita e verifica end-to-end "
        "su più livelli fino a completare il pacchetto completo.",
        False,
        "not_mode_d",
        ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"),
    ),
    (
        "C26_tetralogia_align",
        "Allinea 1:1 la tetralogia sovrana concept_map.md e implementation_plan.md per il Turno 4 dell'auto-brief",
        False,
        "mode_a",
        ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"),
    ),
    (
        "C27_sbfl_bugfix_mode_b",
        "Individua la causa radice con SBFL Ochiai e modifica il modulo per risolvere il crash",
        False,
        "mode_b",
        ("INTRINSIC_GOAL", "INTRINSIC_PLAN"),
    ),
    (
        "C28_react_fullstack_delta",
        "Sviluppa un componente React TypeScript con Tailwind e fai refactoring chirurgico multi-file",
        False,
        "mode_a",
        ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"),
    ),
    (
        "C29_voice_correction_anzi_no",
        "Analizza solo i log, anzi no implementa subito la patch nel router e crea i test di verifica",
        False,
        "not_mode_d",
        ("INTRINSIC_GOAL", "INTRINSIC_PLAN"),
    ),
    (
        "C30_fastapi_sqlite_endpoint",
        "Implementa un nuovo endpoint FastAPI asincrono con modelli Pydantic e cache SQLite; "
        "inoltre esegui un benchmark delle prestazioni",
        False,
        "not_mode_d",
        ("INTRINSIC_GOAL", "INTRINSIC_BOOST", "INTRINSIC_PLAN"),
    ),
)


@pytest.mark.parametrize(
    "case_id,prompt,expected_exempt,expected_mode,expected_protocols",
    S4_REAL_WORLD_MATRIX,
)
def test_s4_real_world_30_prompt_matrix(
    case_id: str,
    prompt: str,
    expected_exempt: bool,
    expected_mode: str,
    expected_protocols: Tuple[str, ...],
) -> None:
    """Valida la matrice di 30 casi reali su esenzioni, modalita e attivazione autonoma dei protocolli."""
    env = vsr.build_meta_prompt_envelope(prompt, workspace_root=SANDBOX_ROOT)
    assert env["bypassed"] is expected_exempt, (
        f"[{case_id}] Bypass mismatch: atteso={expected_exempt}, ottenuto={env['bypassed']}"
    )
    if expected_mode == "not_mode_d":
        assert env["recommended_mode"] != "mode_d", (
            f"[{case_id}] Atteso mode != mode_d, ottenuto mode_d"
        )
    elif expected_mode != "any":
        assert env["recommended_mode"] == expected_mode, (
            f"[{case_id}] Atteso mode={expected_mode}, ottenuto={env['recommended_mode']}"
        )
    for proto in expected_protocols:
        assert proto in env["intrinsic_protocols"], (
            f"[{case_id}] Protocollo {proto} mancante in {env['intrinsic_protocols']}"
        )


# ============================================================================
# LIVELLO S5: Adversarial AP-10 Bypass Attempts & False-Positive Guard
# ============================================================================

S5_ADVERSARIAL_AP10_SHOULD_FAIL: Tuple[str, ...] = (
    "Puoi utilizzare anche il comando `/goal` o `/boost` per migliorare il risultato.",
    "Ti consiglio di lanciare `/boost` prima di procedere.",
    "Puoi usare `/goal` per avviare il loop autonomo.",
    "Esegui manualmente `/implementation` per generare il piano.",
    "Per attivare la pianificazione basta digitare `/plan` nella chat.",
    "In alternativa puoi invocare `/boost` oppure `/goal`.",
)

S5_PROHIBITION_AP10_SHOULD_PASS: Tuple[str, ...] = (
    "Nessun agente chiede all'utente di digitare manualmente /goal, /boost, /plan o /implementation.",
    "È vietato suggerire: puoi usare `/goal` o `/boost`.",
    "Non chiedere mai all'utente di digitare `/plan` o `/implementation` (AP-10).",
    "Il sistema attiva i protocolli senza chiedere di usare il comando `/goal`.",
    "Nessun agente dice all'utente: digita manualmente `/goal`.",
)


@pytest.mark.parametrize("bad_prompt", S5_ADVERSARIAL_AP10_SHOULD_FAIL)
def test_s5_adversarial_ap10_detected_by_both_linters(bad_prompt: str) -> None:
    """Verifica che tentativi avversariali di suggerire manualmente /goal, /boost, /plan vengano bloccati da AP-10."""
    res_router = vsr.lint_nk_prompt(bad_prompt)
    codes_router = [v["code"] for v in res_router["violations"]]
    assert "AP-10" in codes_router, (
        f"vibe_sprint_router.lint_nk_prompt non ha rilevato AP-10 su: {bad_prompt}"
    )

    res_tools, exit_code = ntt.lint_prompt_text(bad_prompt)
    codes_tools = [v["code"] for v in res_tools["violations"]]
    assert exit_code != 0 and "AP-10" in codes_tools, (
        f"nk_transcript_tools.lint_prompt_text non ha rilevato AP-10 su: {bad_prompt}"
    )


@pytest.mark.parametrize("safe_prompt", S5_PROHIBITION_AP10_SHOULD_PASS)
def test_s5_prohibition_sentences_do_not_trigger_ap10_false_positive(
    safe_prompt: str,
) -> None:
    """Verifica che le frasi di divieto (es. in AGENTS.md) non generino falsi positivi AP-10."""
    res_router = vsr.lint_nk_prompt(safe_prompt)
    codes_router = [v["code"] for v in res_router["violations"]]
    assert "AP-10" not in codes_router, (
        f"Falso positivo AP-10 in vibe_sprint_router su frase di divieto: {safe_prompt}"
    )

    res_tools, _ = ntt.lint_prompt_text(safe_prompt)
    codes_tools = [v["code"] for v in res_tools["violations"]]
    assert "AP-10" not in codes_tools, (
        f"Falso positivo AP-10 in nk_transcript_tools su frase di divieto: {safe_prompt}"
    )

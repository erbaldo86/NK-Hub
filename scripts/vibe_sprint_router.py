#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di routing Mode A/B/C/D e Super Meta-Prompt Gate per Nexus Keystone v4.2.0.
Calcola la reale profondita AST max_depth e applica la soglia <= 150 LOC per Mode C.
Supporta Mode D, protocolli intrinseci (/goal, /boost, /plan) e linter AP-1..AP-10.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_WORKSPACE_ROOT = (
    _SCRIPT_DIR.parent.parent
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR.parent
)

for _cand_path in (
    _DEFAULT_WORKSPACE_ROOT,
    _SCRIPT_DIR,
):
    if _cand_path.exists():
        _cand_str = str(_cand_path)
        if _cand_str in sys.path:
            sys.path.remove(_cand_str)
        sys.path.insert(0, _cand_str)

MetaPromptGateContract: Any = None
RoutingIntentContract: Any = None


def _get_ipc_contracts() -> Tuple[Any, Any]:
    """Carica in modo lazy i contratti Pydantic per ridurre la latenza CLI sotto 140 ms."""
    global MetaPromptGateContract, RoutingIntentContract
    if MetaPromptGateContract is None or RoutingIntentContract is None:
        try:
            from schemas.nk_ipc_contracts import (
                MetaPromptGateContract as _MPGC,
                RoutingIntentContract as _RIC,
            )

            MetaPromptGateContract = _MPGC
            RoutingIntentContract = _RIC
        except Exception:
            try:
                from scripts.schemas.nk_ipc_contracts import (
                    MetaPromptGateContract as _MPGC,
                    RoutingIntentContract as _RIC,
                )

                MetaPromptGateContract = _MPGC
                RoutingIntentContract = _RIC
            except Exception:
                pass
    return MetaPromptGateContract, RoutingIntentContract


MODE_D_KEYWORDS: Tuple[str, ...] = (
    "audit",
    "benchmark",
    "discovery",
    "ricerca",
    "analizza",
    "analisi",
    "quanti bandi",
    "copertura",
    "censimento",
    "mappatura",
    "esplora",
    "read-only",
    "readonly",
    "report analitico",
    "stato dell'arte",
    "spiega",
    "perché",
    "perche",
    "cosa fa",
    "come funziona",
    "review",
    "elenca",
    "dove",
    "quali",
    "quanti",
)

MODE_D_LABEL: str = (
    "Mode D (Analytical Discovery & Benchmark - 100% Read-Only + MCP/Web)"
)

DOMAIN_TO_NATIVE_SUBAGENT: Dict[str, str] = {
    "DOM-01": "NK-Specifier-Agent",
    "DOM-02": "NK-Specifier-Agent",
    "DOM-03": "NK-Builder-Agent",
    "DOM-04": "NK-Security-DAST-Auditor",
    "DOM-05": "NK-Scribe-Agent",
}

_READ_ONLY_ROLES: Tuple[str, ...] = (
    "NK-Oracle-Evaluator",
    "NK-Security-DAST-Auditor",
    "NK-Security-Auditor",
    "NK-RSI-Auditor",
    "NK-Specifier-Agent",
)
_ORCHESTRATOR_ROLES: Tuple[str, ...] = (
    "NK-Master-Hub",
    "NK-Session-Controller",
)

_RSI_AUDITOR_SKILLS = frozenset(
    {"NK-Oracle-Evaluator", "NK-State-Router", "NK-Plan-Aligner"}
)
_RSI_AUDITOR_KEYWORDS: Tuple[str, ...] = (
    "rsi",
    "oracolo",
    "oracle",
    "cold review",
    "tetralogia",
)
_FORGE_OVERRIDE_KEYWORDS: Tuple[str, ...] = (
    "forgia",
    "forge",
    "playbook",
    "skill.md",
    "strict_boundaries",
)
_WRITE_ACTION_KEYWORDS: Tuple[str, ...] = (
    "implementa",
    "implementi",
    "implementer",
    "sviluppa",
    "sviluppi",
    "svilupper",
    "refactoring",
    "refactor",
    "modifica",
    "modifichi",
    "modificher",
    ".staging",
    "forgia",
    "crea",
    "crei",
    "creer",
    "sincronizza",
    "sincronizzi",
    "allinea",
    "allinei",
    "progetta",
    "progetti",
    "aggiorna",
    "aggiorni",
    "aggiorner",
    "aggiungi",
    "aggiunga",
    "aggiunger",
    "scrivi",
    "scriva",
    "scriver",
    "correggi",
    "corregga",
    "corregger",
    "sistema",
    "sistemi",
    "sistemer",
)
_NOMINALIZATION_SUFFIXES: Tuple[str, ...] = (
    "zione",
    "zioni",
    "mento",
    "menti",
)
_DOM04_TECHNICAL_AUDIT_KEYWORDS: Tuple[str, ...] = (
    "sast",
    "dast",
    "e2e",
    "puppeteer",
    "chrome-devtools",
    "sbfl",
    "ochiai",
    "cold review",
    "6 gate",
    "oracolo",
)

_INTRINSIC_BOOST_KEYWORDS: Tuple[str, ...] = (
    "/boost",
    "boost",
    "multilivello",
    "multi-livello",
    "multi-agent",
    "più livelli",
    "piu livelli",
    "prospettiv",
    "approfondit",
    "strategia",
    "valutazione",
    "analisi",
    "analizza",
    "benchmark",
    "stress",
    "sandbox",
    "confronto",
    "oggettiv",
)
_INTRINSIC_PLAN_KEYWORDS: Tuple[str, ...] = (
    "/plan",
    "/implementation",
    "plan",
    "piano",
    "pianifica",
    "implementation",
    "implementazione",
    "implementa",
    "implementi",
    "implementer",
    "architettura",
    "strutturare",
    "sviluppare",
    "sviluppa",
    "sviluppi",
    "svilupper",
    "creare",
    "crea",
    "crei",
    "creer",
    "progetta",
    "progetti",
    "modello",
    "modificher",
    "aggiorni",
    "aggiungi",
    "scriva",
    "suite di test",
)
_TECH_CAMEL_ALLOWLIST: Set[str] = {
    "iphone",
    "ipad",
    "macos",
    "ebay",
    "jquery",
    "fastapi",
    "graphql",
    "devtools",
    "github",
    "gitlab",
    "javascript",
    "typescript",
    "postgresql",
    "sqlite",
    "pytorch",
    "openai",
    "deepmind",
    "powershell",
    "devops",
    "youtube",
    "macbook",
    "nextjs",
    "tailwindcss",
}
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:(?:\.(?=\s|$)|[;\n]+)(?:\s*\b(?:inoltre|poi)\b\s*,?)?|(?:,\s*|\b(?:e|ed|ma)\s+)\b(?:inoltre|poi)\b\s*,?|\b(?:inoltre|poi)\s*,)",
    re.IGNORECASE,
)
_AP10_PASSIVE_SLASH_RE = re.compile(
    r"(?:puoi\s+(?:utilizzare|usare|attivare|lanciare|digitare|invocare|eseguire)(?:\s+anche)?(?:\s+il\s+comando)?"
    r"|digita(?:\s+manualmente)?(?:\s+il\s+comando)?"
    r"|basta\s+(?:digitare|usare|lanciare|invocare|eseguire)(?:\s+il\s+comando)?"
    r"|esegui\s+manualmente(?:\s+il\s+comando)?"
    r"|usa(?:\s+manualmente)?(?:\s+il\s+comando)?"
    r"|consigli[oa]\s+di\s+(?:utilizzare|usare|attivare|digitare|lanciare|invocare|eseguire)"
    r"|ti\s+suggerisco\s+di\s+(?:utilizzare|usare|digitare|lanciare|invocare))\s+[^\n]{0,60}/(?:goal|boost|plan|implementation)\b"
    r"|(?:in un unico passaggio|senza fermarti mai|non usare subagent)",
    re.IGNORECASE,
)
_AP10_PROHIBITION_CONTEXT_RE = re.compile(
    r"\b(?:vieta(?:to|ndo|re)?|proibit[oa]|nessun\s+agente|non\s+deve|non\s+(?:chiedere|suggerire|consigliare)|mai\s+(?:chiedere|suggerire)|senza\s+chiedere|ap-10)\b",
    re.IGNORECASE,
)
_STATE_HANDOFF_MARKERS: Tuple[str, ...] = (
    "[handoff stato sessione nk-hub]",
    "[passive state handoff / standby mode]",
    "template 12: passive_session_state_handoff",
    "[nk-anchor:start:passive_state_handoff]",
    "[nk-anchor:start:state_handoff",
)
_PROHIBITION_LINE_RE = re.compile(
    r"\b(?:vieta(?:to|ndo|re)?|divieto|proibit[oa]|non\s+(?:attivare|invocare|generare|eseguire|proporre|avviare)|mai\s+(?:attivare|invocare)|zero\s+|senza\s+|nessun[oa]?\s+(?:pista|task|opzione)|ap-12|ap-13)\b",
    re.IGNORECASE,
)
_AP12_IMPERATIVE_LEAK_RE = re.compile(
    r"\b(?:INTRINSIC_GOAL|INTRINSIC_PLAN|INTRINSIC_BOOST|invoke_subagent|define_subagent|ask_question)\b|(?:^|\n)\s*#{1,4}\s*(?:FASE|PHASE|MACRO-FASE)\s*\d+",
    re.IGNORECASE,
)
_AP13_COGNITIVE_TUNNELING_RE = re.compile(
    r"\b(?:Pista\s+(?:1[A-Z]?|2[A-Z]?|[A-C])\b|Opzione\s+[A-C]\s+da\s+accettare|Seleziona\s+quale\s+(?:task|pista|opzione)\s+avviare|Scegli\s+(?:quale\s+)?(?:pista|task|opzione)|Task\s+[1-9]\s*:)",
    re.IGNORECASE,
)


def is_passive_state_handoff(raw_prompt: str) -> bool:
    """Restituisce True se il prompt contiene un marker di Passive Session State Handoff."""
    low = (raw_prompt or "").lower()
    if not low:
        return False
    return any(m in low for m in _STATE_HANDOFF_MARKERS) or (
        "passive_session_state_handoff" in low
    )

_SHORT_CONFIRMATIONS: Set[str] = {
    "ok",
    "si",
    "sì",
    "procedi",
    "confermo",
    "vai",
    "proceed",
    "premi proceed",
    "ok procedi",
    "si procedi",
    "sì procedi",
    "si procedi pure",
    "sì procedi pure",
    "ok procedi pure",
    "vai pure",
    "confermo procedi",
}
_ANTI_LOOP_EXEMPT_PREFIXES: Tuple[str, ...] = (
    "ok procedi",
    "si procedi",
    "sì procedi",
    "procedi",
    "confermo",
    "vai",
    "proceed",
    "premi proceed",
)
_ONBOARDING_TRIGGERS: Set[str] = {
    "avvia ambiente nk",
    "avvia nk hub",
    "avvia nk",
    "avvia hub",
    "start nk",
    "start hub",
    "attiva nk",
    "attiva ambiente nk",
}
_NODE_SELECTIONS: Set[str] = {f"[{i}]" for i in range(15)} | {
    str(i) for i in range(15)
}
_DESTRUCTIVE_OR_WRITE_EXEMPT_BLOCKERS: Set[str] = {
    "cancella",
    "cancellare",
    "elimina",
    "eliminare",
    "modifica",
    "modificare",
    "scrivi",
    "scrivere",
    "rimuovi",
    "rimuovere",
    "formatta",
    "formattare",
    "drop",
    "delete",
    "crea",
    "creare",
    "implementa",
    "implementare",
    "sovrascrivi",
    "aggiorna",
    "refactoring",
    "refactor",
}
_VOICE_CORRECTION_MARKERS: Tuple[str, ...] = (
    "anzi no",
    "o meglio",
    "volevo dire",
    "anzi",
    "scusa",
    "praticamente",
)

SKILL_ROUTING_RULES: Tuple[Tuple[str, str, str, str, Tuple[str, ...]], ...] = (
    (
        "NK-Plan-Aligner",
        "DOM-01",
        "GOV_AND_ROUTING",
        "NK-RSI-Auditor",
        (
            "allinea 1:1",
            "allinea",
            "1:1",
            "tetralogia",
            "concept_map.md",
            "concept_map",
            "implementation_plan.md",
            "turno 4",
            "auto-brief",
        ),
    ),
    (
        "NK-Oracle-Evaluator",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-RSI-Auditor",
        (
            "cold review",
            "6 gate",
            "oracolo",
            "oracle",
            "delta_k",
            "convergenza rsi",
        ),
    ),
    (
        "NK-State-Router",
        "DOM-01",
        "GOV_AND_ROUTING",
        "NK-RSI-Auditor",
        (
            "dag di kahn",
            "dag",
            "kahn",
            "drift sha",
        ),
    ),
    (
        "NK-Security-Auditor",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-Security-DAST-Auditor",
        (
            "sast",
            "audit di sicurezza",
            "sicurezza",
            "l1/l2/l3",
            "l1",
            "l2",
            "l3",
            "security",
            "vulnerabilita",
            "exploit",
            "cove",
        ),
    ),
    (
        "NK-Dynamic-Sandbox-StressTester",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-Security-DAST-Auditor",
        (
            "dast",
            "sandbox",
            "e2e",
            "puppeteer",
            "chrome-devtools-mcp",
            "chrome-devtools",
            "lighthouse",
            "browser",
            "stress",
            "stress test",
            "benchmark e2e",
        ),
    ),
    (
        "NK-Bug-Diagnostic-Engine",
        "DOM-04",
        "AUDIT_DAST_AND_RCA",
        "NK-Security-DAST-Auditor",
        (
            "sbfl",
            "ochiai",
            "tarantula",
            "dstar",
            "causa radice",
            "rca",
            "falsi bug",
            "crash",
            "diagnosi",
        ),
    ),
    (
        "NK-Agent-Instruction-Forge",
        "DOM-03",
        "BUILD_AND_HEAL",
        "NK-Builder-Agent",
        (
            "forgia",
            "forge",
            "skill.md",
            "playbook",
            "metaprompt",
            "strict_boundaries",
        ),
    ),
    (
        "NK-Delta-Architect",
        "DOM-03",
        "BUILD_AND_HEAL",
        "NK-Builder-Agent",
        (
            "react",
            "typescript",
            "tailwind",
            "nextjs",
            "next.js",
            "html",
            "css",
            "fullstack",
            "full-stack",
            "refactoring chirurgico",
            "chirurgico",
            "multi-file",
            "multifile",
            "delta",
        ),
    ),
    (
        "NK-Python-Async-Builder",
        "DOM-03",
        "BUILD_AND_HEAL",
        "NK-Builder-Agent",
        (
            "fastapi",
            "pydantic",
            "asincrono",
            "async",
            "asyncio",
            "sqlite",
            "endpoint",
        ),
    ),
    (
        "NK-App-UX-Architect",
        "DOM-02",
        "IDEATION_AND_ARCH",
        "NK-Specifier-Agent",
        (
            "ux/ui",
            "ux",
            "ui",
            "8px",
            "hsl",
            "palette",
            "generative_ui",
            "design system",
            "bounded context",
            "user journey",
            "canvas architetturale",
        ),
    ),
    (
        "NK-Backend-Architect",
        "DOM-02",
        "IDEATION_AND_ARCH",
        "NK-Specifier-Agent",
        (
            "openapi",
            "architettura backend",
            "contratti dati",
        ),
    ),
    (
        "NK-Scribe",
        "DOM-05",
        "MEMORY_TELEMETRY_AND_DOCS",
        "NK-Scribe-Agent",
        (
            "sincronizza",
            "patch_notes.md",
            "patch_notes",
            "quality_baseline.json",
            "quality_baseline",
            "changelog",
            "scribe",
            "readme",
        ),
    ),
    (
        "NK-Episodic-Memory-Engine",
        "DOM-05",
        "MEMORY_TELEMETRY_AND_DOCS",
        "NK-Scribe-Agent",
        (
            "memoria 3-tier",
            "memoria episodica",
            "memoria",
            "memory",
            "3-tier",
            "bm25",
            "rrf",
            "recall",
        ),
    ),
    (
        "NK-Ideator",
        "DOM-02",
        "IDEATION_AND_ARCH",
        "NK-Specifier-Agent",
        (
            "ricerca competitor",
            "tavily",
            "benchmark analitico",
            "stato dell'arte",
            "ricerca web",
            "ideazione",
            "scamper",
            "quanti bandi",
            "copertura bandi",
        ),
    ),
)

_ROUTER_MANIFEST_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def _sanitize_tetralogia_filenames(text_low: str) -> str:
    """Protegge i nomi file della Tetralogia da falsi positivi di sottostringa."""
    sanitized = text_low
    for fname in (
        "implementation_plan.md",
        "concept_map.md",
        "structural_tree.md",
        "repo_map.md",
    ):
        sanitized = sanitized.replace(fname, " ")
    return sanitized


_NEGATION_TOKENS: Set[str] = {
    "non",
    "senza",
    "né",
    "ne",
    "mai",
    "vietato",
    "evita",
    "evitando",
    "nessuna",
    "nessun",
}
_NEGATION_BRIDGE_TOKENS: Set[str] = {
    "mai",
    "di",
    "a",
    "da",
    "in",
    "con",
    "su",
    "per",
    "devi",
    "deve",
    "dobbiamo",
    "bisogna",
    "voglio",
    "vorrei",
    "assolutamente",
    "affatto",
    "alcun",
    "alcuno",
    "alcuna",
    "modo",
    "caso",
    "toccare",
    "fare",
    "vado",
    "andare",
    "ora",
    "adesso",
    "mica",
    "proprio",
    "più",
    "piu",
}
_ADVERSATIVE_TOKENS: Set[str] = {
    "ma",
    "però",
    "pero",
    "bensì",
    "bensi",
    "invece",
}


def _has_imperative_write_keyword(clean_text: str) -> bool:
    """Verifica la presenza di verbi imperativi di scrittura escludendo nominalizzazioni e negazioni fino a 5 bridge token."""
    text_low = (clean_text or "").strip().lower()
    if not text_low:
        return False
    if (
        re.match(r"^(?:quali|quale|come|perch[eé]|cosa|chi|dove|quando|quanti|quante)\b", text_low)
        and text_low.endswith("?")
        and not re.search(
            r"\b(?:crea|modifica|scrivi|implementa|aggiungi|rimuovi|elimina|applica|correggi|aggiorna|genera|salva|esegui commit)\b",
            text_low,
        )
    ):
        return False
    if ".staging" in text_low and not re.search(
        r"\b(?:non|senza|vietato)\s+(?:\w+\s+){0,5}\.staging", text_low
    ):
        return True
    tokens = re.findall(r"[a-z0-9_àèéìòù]+", text_low)
    for idx, tok in enumerate(tokens):
        if tok.endswith(_NOMINALIZATION_SUFFIXES):
            continue
        is_negated = False
        for dist in range(1, min(idx, 6) + 1):
            prev_tok = tokens[idx - dist]
            if prev_tok in _ADVERSATIVE_TOKENS:
                break
            if prev_tok in _NEGATION_TOKENS:
                bridge_slice = tokens[idx - dist + 1 : idx]
                if len(bridge_slice) <= 5 and all(
                    (b in _NEGATION_BRIDGE_TOKENS or len(b) <= 14)
                    and b not in _ADVERSATIVE_TOKENS
                    for b in bridge_slice
                ):
                    is_negated = True
                    break
        if is_negated:
            continue
        for wkw in _WRITE_ACTION_KEYWORDS:
            if wkw == ".staging":
                continue
            if tok == wkw or re.fullmatch(
                rf"{re.escape(wkw)}(?:re|rò|rai|rà|remo|rete|ranno|ò|ai|à|emo|ete|anno|iamo|iate|ino|ano|lo|la|li|le)?",
                tok,
            ):
                return True
    return False


def _detect_prompt_role_conflicts(prompt_text: str) -> List[str]:
    """Rileva conflitti di ruolo tra nodi Read-Only, Orchestratori e richieste di scrittura."""
    conflicts: List[str] = []
    if not prompt_text:
        return conflicts
    has_ro = [r for r in _READ_ONLY_ROLES if r.lower() in prompt_text.lower()]
    has_write = _has_imperative_write_keyword(prompt_text) or bool(
        re.search(
            r"(applica(?:re)? la soluzione|crea un test|salva tutti i risultati|src_app/)",
            prompt_text,
            re.IGNORECASE,
        )
    )
    single_opera = re.search(r"Opera come\s+([^\n\.]+)", prompt_text, re.IGNORECASE)
    if single_opera:
        roles_str = single_opera.group(1)
        ro_in_opera = any(r in roles_str for r in _READ_ONLY_ROLES)
        orch_in_opera = any(r in roles_str for r in _ORCHESTRATOR_ROLES)
        if (ro_in_opera and orch_in_opera) or (ro_in_opera and has_write):
            conflicts.append(
                f"Role collapse detected in 'Opera come {roles_str}' with write instructions."
            )
    elif has_ro and has_write and "invoke_subagent" not in prompt_text:
        conflicts.append(
            f"Read-Only role ({', '.join(has_ro)}) combined with write intent without subagent delegation."
        )
    return conflicts


def _make_lint_violation(
    code: str, severity: str, msg: str, rule: str = ""
) -> Dict[str, str]:
    """Costruisce un record di violazione compatibile con nk_transcript_tools.py e il router."""
    rec = {
        "code": code,
        "message": msg,
        "id": code,
        "severity": severity,
        "msg": msg,
    }
    if rule:
        rec["rule"] = rule
    return rec


def lint_nk_prompt(prompt_text: str, mode: str = "auto") -> Dict[str, Any]:
    """Analizza un prompt generato per l'ambiente NK e rileva gli anti-pattern AP-1..AP-13 e AP-2b."""
    violations: List[Dict[str, str]] = []
    text = prompt_text or ""
    low = text.lower()
    norm_mode = (mode or "auto").strip().lower()
    is_state_handoff = (norm_mode == "state-handoff") or (
        norm_mode == "auto" and is_passive_state_handoff(text)
    )

    has_diretto = bool(re.search(r"(!diretto|\bProceed\b)", text, re.IGNORECASE))
    writes_code_or_data = (not is_state_handoff) and bool(
        re.search(
            r"(applica(?:re)? la soluzione|modifica|crea un test|salva tutti i risultati|aggiorna README|src_app/|tests/)",
            text,
            re.IGNORECASE,
        )
    )
    phase_count = len(re.findall(r"\b(?:FASE|PHASE|MACRO-FASE)\s*\d+\b", text, re.IGNORECASE))

    # AP-1: Bypass del Meta-Prompt Gate (!diretto) su prompt lunghi (>1500 char), multi-fase o con scritture
    if has_diretto and (len(text) > 1500 or phase_count > 1 or writes_code_or_data):
        violations.append(
            _make_lint_violation(
                "AP-1",
                "CRITICA",
                "Uso di '!diretto' su prompt complesso (>1500 char, multi-fase o con scritture): bypassa [RULE-00.6].",
            )
        )

    # AP-2: Collasso dei Ruoli ("Opera come X, Y e Z") o assenza di delega 2-Tier (invoke_subagent)
    if not is_state_handoff:
        single_agent_opera = re.search(r"Opera come\s+([^\n\.]+)", text, re.IGNORECASE)
        if single_agent_opera:
            roles_str = single_agent_opera.group(1)
            has_ro = any(r in roles_str for r in _READ_ONLY_ROLES)
            has_orch = any(r in roles_str for r in _ORCHESTRATOR_ROLES)
            if (has_ro and has_orch) or (has_ro and writes_code_or_data):
                violations.append(
                    _make_lint_violation(
                        "AP-2",
                        "CRITICA",
                        f"Collasso dei ruoli incompatibili in una singola istanza ('Opera come {roles_str}') con task di scrittura: viola [RULE-01] e [RULE-00.1].",
                    )
                )
        if (phase_count >= 2 or len(text) > 2500) and "invoke_subagent" not in text and "define_subagent" not in text:
            violations.append(
                _make_lint_violation(
                    "AP-2",
                    "ALTA",
                    "Prompt multi-fase privo di direttive di delega 2-Tier ('invoke_subagent' / '<env_capsule>').",
                )
            )

    # AP-2b: Delega a Builder senza EnableWriteTools=True
    if writes_code_or_data and (phase_count >= 2 or "nk-builder-agent" in low or "builder" in low):
        if not (
            ("define_subagent" in low and ("enablewritetools" in low or "enable_write_tools" in low))
            or '"self"' in low
            or "'self'" in low
        ):
            violations.append(
                _make_lint_violation(
                    "AP-2b",
                    "CRITICA",
                    "Missing define_subagent(..., EnableWriteTools=True) or self for Builder (G3-01).",
                )
            )

    # AP-3: Iniezione di path di produzione diretti senza .staging/ e senza win32_2pc_engine.py
    if writes_code_or_data:
        if ".staging" not in text or "win32_2pc_engine.py" not in text:
            violations.append(
                _make_lint_violation(
                    "AP-3",
                    "CRITICA",
                    "Prescrizione di modifiche a codice/dati/test senza isolamento '.staging/' e commit 'win32_2pc_engine.py --promote-staging --repo-root': viola [RULE-00].",
                )
            )

    # AP-4: Loop di Goodhart ("finché ... 100% PASS") nello stesso turno
    if re.search(r"(?:finch[eé]|until)[^\n]{0,120}100(?:\.0)?%\s*PASS", text, re.IGNORECASE) and "oracle-lock" not in low and "oracle_lock" not in low:
        violations.append(
            _make_lint_violation(
                "AP-4",
                "CRITICA",
                "Loop condizionato 'finche 100% PASS' nello stesso turno: induce data poisoning e indebolimento degli oracoli (Legge di Goodhart).",
            )
        )

    # AP-5: Comando rsi_convergence_engine.py --verify privo di --root <project>
    for m in re.finditer(r"rsi_convergence_engine\.py\s+([^\n`]+)", text):
        args_segment = m.group(1)
        if "--verify" in args_segment and "--root" not in args_segment:
            violations.append(
                _make_lint_violation(
                    "AP-5",
                    "CRITICA",
                    "Comando 'rsi_convergence_engine.py --verify' privo di '--root <project_root>': produce falso 100/100 sintetico.",
                )
            )

    # AP-6: Sovraccarico monolitico di contesto (>= 3 fasi in 1 turno senza stop gate o prompt lungo senza 2PC)
    if phase_count >= 3 and "STOP_GATE" not in text and "ask_question" not in text and "oracle-lock" not in low and "oracle_lock" not in low:
        violations.append(
            _make_lint_violation(
                "AP-6",
                "ALTA",
                f"Sovraccarico monolitico ({phase_count} macro-fasi in 1 turno senza STOP_GATE intermedio): causa context compaction e perdita di stato.",
            )
        )
    elif (
        not is_state_handoff
        and writes_code_or_data
        and len(text) > 1500
        and (".staging" not in text or "win32_2pc_engine.py" not in text)
    ):
        violations.append(
            _make_lint_violation(
                "AP-6",
                "ALTA",
                "Sovraccarico monolitico su prompt di scrittura (>1500 char) privo di .staging e win32_2pc_engine.py.",
            )
        )

    # AP-7: Prescrizione ridondante dual-tool senza sharding o server senza safe_cleanup_dev_servers.py
    if "search_web" in low and "tavily" in low:
        high_q = any(int(n) > 10 for n in re.findall(r"\b(\d+)\s*(?:query|queries|ricerche|fonti|portali)\b", low))
        if ("SIA la ricerca web normale" in text or high_q or "15-20" in low or "30 " in low) and "research" not in low:
            violations.append(
                _make_lint_violation(
                    "AP-7",
                    "ALTA",
                    "Prescrizione ridondante 'SIA search_web SIA tavily' sullo stesso set di query senza sharding su sub-agenti.",
                )
            )
    if (
        re.search(r"avviando il server", text, re.IGNORECASE)
        and "safe_cleanup_dev_servers.py" not in text
    ):
        violations.append(
            _make_lint_violation(
                "AP-7",
                "MEDIA",
                "Istruzione di avvio server priva di protocollo di guardia 'safe_cleanup_dev_servers.py' ([RULE-01.3]).",
            )
        )

    # AP-8: Leakage di Holdout Set B segreto a un Builder
    has_builder_role = any(b in low for b in ("nk-builder-agent", "nk-triad-rsi-builder", "builder"))
    has_holdout_secret = any(h in low for h in ("holdout set b", "battery_b_holdout", "holdout_set_b"))
    if has_builder_role and has_holdout_secret:
        violations.append(
            _make_lint_violation(
                "AP-8",
                "CRITICA",
                "Holdout Set B secret test cases leaked to Builder prompt.",
            )
        )

    # AP-9: Spoofing <env_capsule> in prompt utente iniziale senza !diretto o invoke_subagent
    if "<env_capsule>" in low and "!diretto" not in low and "invoke_subagent" not in low:
        has_user_spoof_markers = (
            any(m in low for m in ("opera come nk-session-controller", "opera come nk-master-hub", "prompt utente iniziale", "user prompt:"))
            or (phase_count >= 2 and not any(w in low for w in ("builder shard", "sub-agente", "subagent", "worker")))
        )
        if has_user_spoof_markers:
            violations.append(
                _make_lint_violation(
                    "AP-9",
                    "ALTA",
                    "Improper <env_capsule> in initial user prompt without !diretto or invoke_subagent.",
                )
            )

    # AP-10: Delega passiva all'utente dei protocolli intrinseci (/goal, /boost, /plan, /implementation)
    for m_ap10 in _AP10_PASSIVE_SLASH_RE.finditer(text):
        line_start = text.rfind("\n", 0, m_ap10.start()) + 1
        line_end = text.find("\n", m_ap10.end())
        if line_end == -1:
            line_end = len(text)
        line_ctx = text[line_start:line_end]
        if not _AP10_PROHIBITION_CONTEXT_RE.search(line_ctx):
            violations.append(
                _make_lint_violation(
                    "AP-10",
                    "ALTA",
                    "Suggerimento passivo di digitare manualmente /goal, /boost, /plan o /implementation anziche auto-attivarli ([RULE-00.6], [RULE-01.11], [RULE-01.12]).",
                )
            )
            break

    if "canary_v1.json" in low or "canary-ib-" in low:
        violations.append(
            _make_lint_violation(
                "AP-11",
                "CRITICA",
                "Holdout canary leak detected in outbound prompt ([RULE-ORACLE-LOCK]).",
            )
        )

    if is_state_handoff:
        has_ap12 = False
        has_ap13 = False
        for raw_line in text.splitlines():
            line_s = raw_line.strip()
            if not line_s or _PROHIBITION_LINE_RE.search(line_s):
                continue
            if not has_ap12 and _AP12_IMPERATIVE_LEAK_RE.search(line_s):
                violations.append(
                    _make_lint_violation(
                        "AP-12",
                        "CRITICA",
                        "STATE_HANDOFF_IMPERATIVE_LEAK: Imperative directive or intrinsic protocol leak inside Passive Session State Handoff.",
                        rule="STATE_HANDOFF_IMPERATIVE_LEAK",
                    )
                )
                has_ap12 = True
            if not has_ap13 and _AP13_COGNITIVE_TUNNELING_RE.search(line_s):
                violations.append(
                    _make_lint_violation(
                        "AP-13",
                        "CRITICA",
                        "STATE_HANDOFF_COGNITIVE_TUNNELING: Prescriptive track or option menu detected inside Passive Session State Handoff.",
                        rule="STATE_HANDOFF_COGNITIVE_TUNNELING",
                    )
                )
                has_ap13 = True

    is_valid = len(violations) == 0
    return {
        "passed": is_valid,
        "valid": is_valid,
        "violations_count": len(violations),
        "violation_count": len(violations),
        "violations": violations,
        "write_tools_mounted": (
            "EnableWriteTools=True" in text or "enable_write_tools=True" in text
        ),
    }


def _token_matches_keyword(
    kw: str,
    text_low: str,
    tokens: Set[str],
    min_sub_len: int = 4,
) -> bool:
    """Verifica il matching tra keyword e testo escludendo falsi positivi da nominalizzazioni."""
    kw_low = kw.lower()
    if " " in kw_low or "." in kw_low or "/" in kw_low or "-" in kw_low:
        return kw_low in text_low
    if kw_low in tokens:
        return True
    if len(kw_low) >= min_sub_len and kw_low in text_low:
        kw_is_nominal = kw_low.endswith(_NOMINALIZATION_SUFFIXES)
        for tok in tokens:
            if not kw_is_nominal and tok.endswith(_NOMINALIZATION_SUFFIXES):
                continue
            if kw_low in tok:
                return True
    return False


def _match_granular_skills(text_low: str) -> List[Tuple[str, str, str, str, List[str]]]:
    """Valuta le regole granulari di skill restituendo le corrispondenze ordinate per punteggio."""
    tokens = set(re.findall(r"[a-z0-9_àèéìòù]+", text_low))
    matches: List[Tuple[int, int, str, str, str, str, List[str]]] = []

    for idx, (sk_name, dom_id, dom_name, subagent, kws) in enumerate(
        SKILL_ROUTING_RULES
    ):
        hits: List[str] = []
        score = 0
        for kw in kws:
            if _token_matches_keyword(kw, text_low, tokens, min_sub_len=5):
                hits.append(kw)
                score += 2 if (len(kw) >= 10 or " " in kw) else 1
        if hits:
            matches.append(
                (score, -idx, sk_name, dom_id, dom_name, subagent, hits)
            )

    matches.sort(reverse=True)
    return [
        (sk_name, dom_id, dom_name, subagent, hits)
        for _, _, sk_name, dom_id, dom_name, subagent, hits in matches
    ]


def _resolve_native_subagent(
    domain_id: str,
    matched_skill: Optional[str] = None,
    text: str = "",
) -> str:
    """Risolve il Sub-Agente Nativo instradando query RSI e Oracolo su NK-RSI-Auditor."""
    text_low = (text or "").strip().lower()
    if matched_skill == "NK-Agent-Instruction-Forge" or any(
        fk in text_low for fk in _FORGE_OVERRIDE_KEYWORDS
    ):
        return "NK-Builder-Agent"
    if matched_skill and matched_skill in _RSI_AUDITOR_SKILLS:
        return "NK-RSI-Auditor"
    if text_low:
        tokens = set(
            "".join(ch if ch.isalnum() or ch == "_" else " " for ch in text_low).split()
        )
        for kw in _RSI_AUDITOR_KEYWORDS:
            if (" " in kw and kw in text_low) or kw in tokens:
                return "NK-RSI-Auditor"
    return DOMAIN_TO_NATIVE_SUBAGENT.get(domain_id, "NK-Builder-Agent")


class _ASTDepthVisitor(ast.NodeVisitor):
    """Calcola la profondita massima di annidamento del flusso di controllo AST."""

    _CONTROL_NODES = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
    )

    def __init__(self) -> None:
        self.current_depth: int = 0
        self.max_depth: int = 0

    def generic_visit(self, node: ast.AST) -> None:
        is_branch = isinstance(node, self._CONTROL_NODES)
        if is_branch:
            self.current_depth += 1
            if self.current_depth > self.max_depth:
                self.max_depth = self.current_depth
        super().generic_visit(node)
        if is_branch:
            self.current_depth -= 1


class VibeSprintRouter:
    """Valuta il rischio strutturale AST e seleziona la modalita operativa (Mode A, B, C o D)."""

    MODE_C_MAX_LOC: int = 150
    MODE_C_MAX_PROMPT_CHARS: int = 400
    DISCOVERY_KEYWORDS: Tuple[str, ...] = MODE_D_KEYWORDS

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        if workspace_root is None:
            self.workspace_root = _DEFAULT_WORKSPACE_ROOT
        else:
            self.workspace_root = Path(workspace_root).resolve()
        self.staging_dir = self.workspace_root / ".staging"

    def _load_registry_manifest(self) -> Dict[str, Any]:
        """Carica nk_registry_manifest.json da staging o root con cache statica O(1)."""
        candidates = (
            self.staging_dir / "nk_genome" / "nk_registry_manifest.json",
            self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
            _DEFAULT_WORKSPACE_ROOT
            / ".staging"
            / "nk_genome"
            / "nk_registry_manifest.json",
            _DEFAULT_WORKSPACE_ROOT / "nk_genome" / "nk_registry_manifest.json",
        )
        for cand in candidates:
            if cand.exists() and cand.is_file():
                try:
                    st = cand.stat()
                    key = str(cand)
                    cached = _ROUTER_MANIFEST_CACHE.get(key)
                    if (
                        cached is not None
                        and cached[0] == st.st_mtime_ns
                        and cached[1] == st.st_size
                    ):
                        return cached[2]
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        _ROUTER_MANIFEST_CACHE[key] = (
                            st.st_mtime_ns,
                            st.st_size,
                            data,
                        )
                        return data
                except Exception:
                    pass
        return {}

    def is_passive_state_handoff(self, raw_prompt: str) -> bool:
        """Restituisce True se il prompt contiene un marker di Passive Session State Handoff."""
        return is_passive_state_handoff(raw_prompt)

    def resolve_intrinsic_vibe_protocols(
        self,
        prompt: str,
        recommended_mode: str = "mode_c",
    ) -> Dict[str, Any]:
        """Rileva e attiva autonomamente INTRINSIC_GOAL, INTRINSIC_BOOST e INTRINSIC_PLAN."""
        text = (prompt or "").strip()
        if is_passive_state_handoff(text):
            return {
                "intrinsic_protocols": [],
                "autonomous_slash_equivalence": {
                    "goal": False,
                    "boost": False,
                    "plan": False,
                    "implementation": False,
                },
                "goal": False,
                "boost": False,
                "plan": False,
                "implementation": False,
                "recommended_mode": "mode_d",
            }
        text_low = text.lower()
        rec_mode = (recommended_mode or "mode_c").strip().lower()

        goal_active = True
        boost_active = bool(
            rec_mode in ("mode_a", "mode_d")
            or any(kw in text_low for kw in _INTRINSIC_BOOST_KEYWORDS)
        )
        plan_active = bool(
            rec_mode in ("mode_a", "mode_b")
            or any(kw in text_low for kw in _INTRINSIC_PLAN_KEYWORDS)
        )

        protocols: List[str] = []
        if goal_active:
            protocols.append("INTRINSIC_GOAL")
        if boost_active:
            protocols.append("INTRINSIC_BOOST")
        if plan_active:
            protocols.append("INTRINSIC_PLAN")

        slash_equivalence: Dict[str, bool] = {
            "goal": goal_active,
            "boost": boost_active,
            "plan": plan_active,
            "implementation": plan_active,
        }
        return {
            "intrinsic_protocols": protocols,
            "autonomous_slash_equivalence": slash_equivalence,
            "goal": goal_active,
            "boost": boost_active,
            "plan": plan_active,
            "implementation": plan_active,
            "recommended_mode": rec_mode,
        }

    def normalize_voice_stt_input(self, raw_prompt: str) -> Dict[str, Any]:
        """Normalizza il testo dettato a voce separando CamelCase fusi ed estraendo correzioni."""
        text = (raw_prompt or "").strip()
        if not text:
            return {
                "raw_prompt": raw_prompt or "",
                "cleaned_prompt": "",
                "voice_corrections_applied": [],
                "camelcase_splits": [],
                "bypass_requested": False,
            }

        code_spans: List[str] = []

        def _stash_code(match: re.Match[str]) -> str:
            idx = len(code_spans)
            code_spans.append(match.group(0))
            return f"__NK_CODE_{idx}__"

        masked = re.sub(r"(`{1,3}[\s\S]*?`{1,3})", _stash_code, text)
        voice_corrections: List[str] = []
        camelcase_splits: List[str] = []
        bypass_requested = False

        for bp_marker in ("!diretto", "!raw"):
            pat = re.compile(
                rf"(?i)(?:^\s*{re.escape(bp_marker)}(?=\s|$|[.,;!?])|(?:^|\s){re.escape(bp_marker)}\s*[.,;!?]*$)"
            )
            if pat.search(masked):
                bypass_requested = True
                masked = pat.sub(" ", masked).strip()

        salta_pat = re.compile(
            r"(?i)(?<!\bnon\s)(?<!\bsenza\s)(?<!\bvietato\s)(?<!\bmai\s)(?:^|\s)salta gate(?=\s|$|[.,;!?])"
        )
        if salta_pat.search(masked):
            bypass_requested = True
            masked = salta_pat.sub(" ", masked).strip()

        camel_pat = re.compile(r"\b([a-zàèéìòù]{2,})([A-Z][a-zàèéìòù]+)\b")

        def _split_camel(match: re.Match[str]) -> str:
            orig = match.group(0)
            if orig.lower() in _TECH_CAMEL_ALLOWLIST:
                return orig
            rep = f"{match.group(1)} {match.group(2)}"
            camelcase_splits.append(f"{orig} -> {rep}")
            voice_corrections.append(f"{orig} -> {rep}")
            return rep

        masked = camel_pat.sub(_split_camel, masked)

        for marker in _VOICE_CORRECTION_MARKERS:
            m_pat = re.compile(rf"(?i)\b{re.escape(marker)}\b")
            if m_pat.search(masked):
                if marker in ("anzi no", "o meglio", "volevo dire"):
                    parts = m_pat.split(masked, maxsplit=1)
                    if len(parts) == 2:
                        before_part = parts[0].strip(" ,;:-")
                        after_part = parts[1].strip(" ,;:-")
                        if after_part:
                            sent_parts = re.split(r"(?<=[.;\n])\s+", before_part)
                            last_clause = sent_parts[-1].strip(" ,;:-")
                            prefix_sents = " ".join(sent_parts[:-1]).strip()
                            voice_corrections.append(
                                f"{last_clause or marker} -> {after_part}"
                            )
                            if (
                                len(after_part.split()) >= 1
                                and len(last_clause.split()) <= 8
                            ):
                                masked = (
                                    f"{prefix_sents} {after_part}".strip()
                                    if prefix_sents
                                    else after_part
                                )
                            else:
                                masked = f"{before_part} {after_part}".strip()
                else:
                    voice_corrections.append(f"{marker} -> (rimosso filler vocale)")
                    masked = m_pat.sub(" ", masked)

        masked = re.sub(r"\s+", " ", masked).strip()
        for idx, span in enumerate(code_spans):
            masked = masked.replace(f"__NK_CODE_{idx}__", span)

        return {
            "raw_prompt": raw_prompt,
            "cleaned_prompt": masked,
            "voice_corrections_applied": voice_corrections,
            "camelcase_splits": camelcase_splits,
            "bypass_requested": bypass_requested,
        }

    def is_gate_exempt(self, raw_prompt: str) -> bool:
        """Verifica le esenzioni anti-loop e standby per il Super Meta-Prompt Gate (RULE-00.6)."""
        text = (raw_prompt or "").strip()
        if not text:
            return True
        if is_passive_state_handoff(text):
            return True
        text_low = text.lower()
        if "<env_capsule>" in text_low:
            return True
        if re.search(
            r"(?:^\s*(?:!diretto|!raw)(?=\s|$|[.,;!?])|(?:^|\s)(?:!diretto|!raw)\s*[.,;!?]*$)",
            text_low,
        ):
            return True
        for toggle_marker in ("salta gate", "disattiva prompt gate"):
            if toggle_marker in text_low and not re.search(
                rf"\b(?:non|senza|vietato|mai)\s+(?:\w+\s+){{0,3}}{re.escape(toggle_marker)}\b",
                text_low,
            ):
                return True
        norm = re.sub(r"[,.;:!?\"']+", " ", text_low).strip()
        norm = re.sub(r"\s+", " ", norm)
        if norm in _SHORT_CONFIRMATIONS:
            return True
        norm_words = norm.split()
        if len(norm_words) <= 5 and norm.startswith(_ANTI_LOOP_EXEMPT_PREFIXES):
            if not any(
                w in _DESTRUCTIVE_OR_WRITE_EXEMPT_BLOCKERS for w in norm_words
            ) and not _has_imperative_write_keyword(norm):
                return True
        if norm in _ONBOARDING_TRIGGERS:
            return True
        if norm in _NODE_SELECTIONS:
            return True
        return False

    def evaluate_meta_prompt_gate(
        self,
        raw_prompt: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Valuta il Gate L0 sul prompt fornito delegando a build_meta_prompt_envelope."""
        return self.build_meta_prompt_envelope(prompt=raw_prompt, **kwargs)

    def build_meta_prompt_envelope(
        self,
        prompt: str,
        gate_enabled: bool = True,
        gate_mode: str = "CONFIRM",
        files: Optional[List[str]] = None,
        compact: bool = False,
        auto_bypass_readonly: bool = False,
    ) -> Dict[str, Any]:
        """Costruisce e valida il contratto MetaPromptGateContract di Livello 0."""
        is_handoff_standby = is_passive_state_handoff(prompt)
        stt_info = self.normalize_voice_stt_input(prompt)
        exempt = (
            is_handoff_standby
            or self.is_gate_exempt(prompt)
            or bool(stt_info.get("bypass_requested"))
        )
        cleaned_prompt = stt_info["cleaned_prompt"] or (prompt or "").strip()
        intent = self.classify_prompt_intent(cleaned_prompt, files=files)
        role_conflicts = (
            [] if is_handoff_standby else _detect_prompt_role_conflicts(prompt or "")
        )

        effective_mode = (gate_mode or "CONFIRM").strip().upper()
        if effective_mode not in ("CONFIRM", "ECHO", "OFF", "BYPASS"):
            effective_mode = "CONFIRM"

        bypassed = bool(exempt or (not gate_enabled) or effective_mode in ("OFF", "BYPASS"))
        if is_handoff_standby or bypassed:
            fsm_state = "BYPASSED"
        elif effective_mode == "ECHO":
            fsm_state = "CONFIRMED"
        else:
            fsm_state = "AWAIT_CONFIRM"

        raw_clauses = [
            c.strip(" .;")
            for c in _CLAUSE_SPLIT_RE.split(cleaned_prompt)
            if c and len(c.strip(" .;")) >= 3
        ]
        if not raw_clauses:
            raw_clauses = [cleaned_prompt or "Eseguire il task richiesto"]

        requirements_r_ids = [
            f"R{idx}: {clause}" for idx, clause in enumerate(raw_clauses[:6], start=1)
        ]

        if is_handoff_standby:
            rec_mode = "mode_d"
            primary_ag = "NK-Session-Controller"
            native_sub = "NK-Specifier-Agent"
            intrinsic_protocols: List[str] = []
            slash_equivalence: Dict[str, bool] = {
                "goal": False,
                "boost": False,
                "plan": False,
                "implementation": False,
            }
            bypass_reason: Optional[str] = "STATE_HANDOFF_STANDBY"
            standby_mode = True
            fast_bypass_eligible = False
            out_of_scope = [
                "Qualsiasi modifica ai file del repository (acquisizione stato 100% Read-Only)",
                "Attivazione autonoma di INTRINSIC_GOAL, INTRINSIC_PLAN, implementation_plan.md o ask_question prescrittivi",
            ]
            conceptual_mirror = (
                "STATE_HANDOFF_STANDBY: acquisizione passiva dello stato della sessione "
                "precedente in sola lettura, divieto di proporre task autonomi o attivare "
                "implementation_plan.md, attesa in STANDBY delle decisioni dell'utente."
            )
            optimized_meta_prompt = (
                "[META-PROMPT L0 | Mode: mode_d | Skill: NK-Session-Controller | "
                "BypassScope: STATE_HANDOFF_STANDBY]\n"
                "Stato: STATE_HANDOFF_STANDBY (Passive Session State Handoff).\n"
                "Protocolli Intrinseci Auto-Attivati: NONE\n"
                "Direttiva: acquisisci lo stato verificato e rimani in STANDBY."
            )
        else:
            rec_mode = str(intent.get("recommended_mode", "mode_c"))
            primary_ag = str(intent.get("primary_agent", "NK-Python-Async-Builder"))
            native_sub = str(intent.get("native_subagent", "NK-Builder-Agent"))
            fast_bypass_eligible = bool(intent.get("fast_bypass_eligible", False))

            intrinsic_info = self.resolve_intrinsic_vibe_protocols(
                cleaned_prompt, recommended_mode=rec_mode
            )
            intrinsic_protocols = list(intrinsic_info["intrinsic_protocols"])
            slash_equivalence = dict(intrinsic_info["autonomous_slash_equivalence"])
            norm_clean = re.sub(r"[,.;:!?\"']+", " ", cleaned_prompt.lower()).strip()
            norm_clean = re.sub(r"\s+", " ", norm_clean)
            norm_clean_words = norm_clean.split()
            if (
                (
                    norm_clean in _SHORT_CONFIRMATIONS
                    or (
                        len(norm_clean_words) <= 5
                        and norm_clean.startswith(_ANTI_LOOP_EXEMPT_PREFIXES)
                        and not any(
                            w in _DESTRUCTIVE_OR_WRITE_EXEMPT_BLOCKERS
                            for w in norm_clean_words
                        )
                    )
                )
                and "INTRINSIC_PLAN" not in intrinsic_protocols
            ):
                intrinsic_protocols.append("INTRINSIC_PLAN")
                slash_equivalence["plan"] = True
                slash_equivalence["implementation"] = True
            protocols_str = ", ".join(intrinsic_protocols)
            bypass_reason = None
            standby_mode = False

        auto_bypass_eligible = bool(
            rec_mode == "mode_d"
            or (rec_mode == "mode_c" and fast_bypass_eligible)
        )
        if (
            not is_handoff_standby
            and auto_bypass_readonly
            and auto_bypass_eligible
            and fsm_state == "AWAIT_CONFIRM"
        ):
            fsm_state = "BYPASSED"
            bypassed = True
            bypass_reason = "READONLY_OR_FAST_SPRINT_BYPASS"

        if not is_handoff_standby:
            if compact:
                out_of_scope = (
                    ["Read-Only"]
                    if rec_mode == "mode_d"
                    else ["Solo .staging/"]
                )
                conceptual_mirror = f"{cleaned_prompt[:48]} ({rec_mode}/{primary_ag})."
                optimized_meta_prompt = (
                    f"[L0:{rec_mode}:{primary_ag}] {cleaned_prompt[:64]} | "
                    f"{'; '.join(r[:32] for r in requirements_r_ids[:3])}"
                )
            else:
                if rec_mode == "mode_d":
                    out_of_scope = [
                        "Qualsiasi modifica ai file del repository (esecuzione 100% Read-Only)",
                        "Esecuzione di commit transazionali 2PC",
                    ]
                    nk_guidance = (
                        "Regolamento NK: opera in sola lettura (Mode D) e verifica le fonti."
                    )
                else:
                    out_of_scope = [
                        "Modifica diretta dei file di produzione fuori da .staging/",
                        "Uso di MagicMock o stub sintetici vietati da RULE-01.2",
                    ]
                    nk_guidance = (
                        "Regolamento NK: dopo la conferma L0, prepara Brief in nk_genome/ e "
                        "implementation_plan.md confermato dall'utente (RequestFeedback: true) "
                        "prima di delegare la scrittura codice ai Builder in .staging/, "
                        "applica commit 2PC e convergenza RSI."
                    )

                if bypassed:
                    out_of_scope.append(
                        "Bypass L0_GATE_ONLY: topologia 2-Tier (max 12 tool diretti) e .staging/ + 2PC restano obbligatori"
                    )

                if len(cleaned_prompt) <= 240:
                    mirror_summary = cleaned_prompt
                else:
                    cut_text = cleaned_prompt[:240].rsplit(" ", 1)[0].rstrip(" ,;:")
                    mirror_summary = f"{cut_text or cleaned_prompt[:240]}..."
                scope_tag = " | BypassScope: L0_GATE_ONLY" if bypassed else ""
                optimized_meta_prompt = (
                    f"[META-PROMPT L0 | Mode: {rec_mode} | Skill: {primary_ag}{scope_tag}]\n"
                    f"Obiettivo ad alto livello: {cleaned_prompt}\n"
                    f"Requisiti: {'; '.join(requirements_r_ids)}\n"
                    f"Protocolli Intrinseci Auto-Attivati: {protocols_str}\n"
                    f"{nk_guidance}"
                )
                conceptual_mirror = (
                    f"Obiettivo: {mirror_summary} "
                    f"(Modalita: {rec_mode}, Skill: {primary_ag}, Sub-Agente: {native_sub}, "
                    f"Protocolli: {protocols_str}). {nk_guidance}"
                )

        hash_input = f"{optimized_meta_prompt}|{'|'.join(requirements_r_ids)}"
        intent_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        brief_id = f"IB-{time.strftime('%Y%m%d')}-{intent_hash[:6].upper()}"

        payload: Dict[str, Any] = {
            "brief_id": brief_id,
            "fsm_state": fsm_state,
            "gate_mode": effective_mode,
            "enabled": bool(gate_enabled and effective_mode != "OFF"),
            "bypassed": bypassed,
            "bypass_reason": bypass_reason,
            "auto_bypass_eligible": auto_bypass_eligible,
            "standby_mode": standby_mode,
            "conceptual_mirror": conceptual_mirror,
            "optimized_meta_prompt": optimized_meta_prompt,
            "requirements_r_ids": requirements_r_ids,
            "voice_corrections_applied": list(
                stt_info.get("voice_corrections_applied", [])
            ),
            "out_of_scope": out_of_scope,
            "ambiguities": list(role_conflicts),
            "recommended_mode": rec_mode,
            "primary_agent": primary_ag,
            "native_subagent": native_sub,
            "intrinsic_protocols": intrinsic_protocols,
            "autonomous_slash_equivalence": slash_equivalence,
            "intent_hash_sha256": intent_hash,
            "ttl_seconds": 1800,
        }

        if "pydantic" in sys.modules:
            mp_contract_cls, _ = _get_ipc_contracts()
        else:
            mp_contract_cls = MetaPromptGateContract

        if mp_contract_cls is not None:
            validated = mp_contract_cls(**payload)
            result = validated.model_dump()
        else:
            result = dict(payload)

        result["bypass_reason"] = bypass_reason
        result["auto_bypass_eligible"] = auto_bypass_eligible
        result["standby_mode"] = standby_mode
        result["bypass_scope"] = (
            "STATE_HANDOFF_STANDBY"
            if is_handoff_standby
            else ("L0_GATE_ONLY" if (bypassed or fsm_state == "BYPASSED") else "NONE")
        )
        result["topology_2tier_mandatory"] = True
        result["staging_2pc_mandatory"] = rec_mode != "mode_d"
        result["max_direct_tools"] = 12
        result["compact_profile"] = bool(compact)
        result["three_pillar_mirror_only"] = True
        result["rendered_markdown"] = self.format_meta_prompt_markdown(result)
        return result

    def format_meta_prompt_markdown(self, envelope: Dict[str, Any]) -> str:
        """Formatta il blocco Markdown visibile di Livello 0 per il campo content prima di ask_question."""
        brief_id = str(envelope.get("brief_id", "IB-UNKNOWN"))
        fsm_state = str(envelope.get("fsm_state", "AWAIT_CONFIRM"))
        rec_mode = str(envelope.get("recommended_mode", "mode_c"))
        primary_ag = str(envelope.get("primary_agent", "NK-Python-Async-Builder"))
        native_sub = str(envelope.get("native_subagent", "NK-Builder-Agent"))
        if envelope.get("standby_mode"):
            protos = "NONE (STATE_HANDOFF_STANDBY)"
        else:
            protos = ", ".join(envelope.get("intrinsic_protocols") or []) or "INTRINSIC_GOAL"
        intent_hash = str(envelope.get("intent_hash_sha256", ""))
        mirror = str(envelope.get("conceptual_mirror", ""))
        reqs = list(envelope.get("requirements_r_ids") or [])
        voice_corrs = "; ".join(envelope.get("voice_corrections_applied") or []) or "Nessuna"
        out_scope = "; ".join(envelope.get("out_of_scope") or []) or "Nessuno"
        ambiguities = "; ".join(envelope.get("ambiguities") or []) or "Nessuna"

        if fsm_state == "BYPASSED":
            return "\n".join(
                [
                    "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]",
                    f"- **Brief ID:** `{brief_id}` | **Stato FSM:** `{fsm_state}` | **Hash:** `{intent_hash[:12]}`",
                    f"- **1. Intenzione:** {mirror[:160]} ({reqs[0] if reqs else 'R1'})",
                    f"- **2. Come Farlo:** `{rec_mode}` | **Skill:** `{primary_ag}` | **Sub-Agente:** `{native_sub}` | **Protocolli:** `{protos}`",
                    f"- **3. Regole e Perimetro:** {out_scope[:120]} | **Ambiguità:** {ambiguities}",
                ]
            )

        req_lines = [f"  * {r}" for r in reqs] if reqs else ["  * R1: Eseguire il task richiesto"]
        lines = [
            "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]",
            f"- **Brief ID:** `{brief_id}` | **Stato FSM:** `{fsm_state}`",
            f"- **Intent Hash SHA-256:** `{intent_hash}`",
            "- **1. Intenzione:**",
            f"- **Specchio Concettuale (Meta-Prompt Integrato):** {mirror}",
            "- **Requisiti Tracciabili (R1..Rn):**",
            *req_lines,
            f"- **Correzioni vocali recepite:** {voice_corrs}",
            "- **2. Come Farlo:**",
            f"- **Modalità Consigliata:** `{rec_mode}` | **Skill:** `{primary_ag}` | **Sub-Agente:** `{native_sub}`",
            f"- **Protocolli Intrinseci Auto-Attivati:** `{protos}`",
            "- **Flusso Post-Conferma L0:** 1) Creazione Brief in `nk_genome/` e `implementation_plan.md` confermato dall'utente (`RequestFeedback: true`) -> 2) Delega scrittura ai Builder in `.staging/` -> 3) Audit RSI e Commit 2PC.",
            "- **3. Regole e Perimetro:**",
            f"- **Fuori ambito:** {out_scope}",
            f"- **Ambiguità rilevate:** {ambiguities}",
            "- **Divieto 4° Blocco ([NO-RAW-META-PROMPT]):** Vietato stampare il campo interno optimized_meta_prompt ([META-PROMPT L0]) come 4° blocco separato; le intenzioni sono già integrate nei 3 passaggi.",
        ]
        if fsm_state == "AWAIT_CONFIRM":
            lines.append(
                "- **Stop Pre-Esecuzione (`AWAIT_CONFIRM`):** Fermati subito dopo questo specchio e invoca `ask_question`. Vietato eseguire il task prima della conferma utente e vietato posticipare il Gate L0 a fine task."
            )
        lines.append(
            "- [MANDATORY-VISIBLE-L0]: Mostra obbligatoriamente questo blocco nel campo content della risposta PRIMA o INSIEME a ask_question (vietato content_len=0)."
        )
        return "\n".join(lines)

    def resolve_domain_from_manifest(self, prompt: str) -> Dict[str, Any]:
        """Risolve in O(1) il dominio funzionale DOM-01..DOM-05 e le skill interrogando il manifesto SSOT."""
        text_lower = (prompt or "").strip().lower()
        norm_fast = re.sub(r"[,.;:!?\"']+", " ", text_lower).strip()
        norm_fast = re.sub(r"\s+", " ", norm_fast)
        if norm_fast in _SHORT_CONFIRMATIONS or norm_fast in _NODE_SELECTIONS:
            return {
                "domain_id": "DOM-03",
                "domain_name": "BUILD_AND_HEAL",
                "primary_skill": "NK-Python-Async-Builder",
                "matched_skills": ["NK-Python-Async-Builder"],
                "native_subagent": "NK-Builder-Agent",
                "matched_triggers": [],
            }
        manifest = self._load_registry_manifest()
        domains = manifest.get("domains", {})
        skills_index = manifest.get("skills_index", {})
        scripts_index = manifest.get("scripts_index", {})
        dispatch_table = manifest.get("intent_dispatch_table", {})

        # 1. Riferimento esplicito a ID dominio nel prompt (es. DOM-04)
        for dom_id, dom_meta in domains.items():
            if (
                dom_id.lower() in text_lower
                or dom_meta.get("name", "").lower() in text_lower
            ):
                primary_sk = dom_meta.get("primary_skill", "NK-Master-Hub")
                return {
                    "domain_id": dom_id,
                    "domain_name": dom_meta.get("name", ""),
                    "primary_skill": primary_sk,
                    "matched_skills": [primary_sk],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [dom_id],
                }

        # 2. Riferimento esplicito a una skill nel prompt
        for sk_name, sk_meta in skills_index.items():
            if sk_name.lower() in text_lower:
                dom_id = sk_meta.get("domain_id", "DOM-01")
                return {
                    "domain_id": dom_id,
                    "domain_name": sk_meta.get("domain_name", "GOV_AND_ROUTING"),
                    "primary_skill": sk_name,
                    "matched_skills": [sk_name],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=sk_name, text=text_lower
                    ),
                    "matched_triggers": [sk_name],
                }

        # 3. Regole granulari multi-skill per intenti composti o specialistici
        skill_matches = _match_granular_skills(text_lower)
        if skill_matches:
            primary_sk, dom_id, dom_name, subagent, triggers = skill_matches[0]
            matched_skills = [m[0] for m in skill_matches]
            all_triggers: List[str] = []
            for m in skill_matches:
                for t in m[4]:
                    if t not in all_triggers:
                        all_triggers.append(t)
            return {
                "domain_id": dom_id,
                "domain_name": dom_name,
                "primary_skill": primary_sk,
                "matched_skills": matched_skills,
                "native_subagent": subagent,
                "matched_triggers": all_triggers or triggers,
            }

        # 4. Riferimento esplicito a uno script Python nel prompt
        for sc_name, sc_meta in scripts_index.items():
            if sc_name.lower() in text_lower:
                dom_id = sc_meta.get("domain_id", "DOM-03")
                dom_meta = domains.get(dom_id, {})
                primary_sk = dom_meta.get("primary_skill", "NK-Python-Async-Builder")
                return {
                    "domain_id": dom_id,
                    "domain_name": sc_meta.get("domain_name", "BUILD_AND_HEAL"),
                    "primary_skill": primary_sk,
                    "matched_skills": [primary_sk],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [sc_name],
                }

        # 5. Punteggio keyword tramite domains e intent_dispatch_table (con protezione Tetralogia e nominalizzazioni)
        clean_text = _sanitize_tetralogia_filenames(text_lower)
        tokens = set(
            "".join(
                ch if ch.isalnum() or ch == "_" else " " for ch in clean_text
            ).split()
        )
        best_dom_id = ""
        best_score = 0
        best_triggers: List[str] = []

        for dom_id, dom_meta in domains.items():
            kws = dom_meta.get("keywords", [])
            hits = [
                kw
                for kw in kws
                if _token_matches_keyword(kw, clean_text, tokens, min_sub_len=4)
            ]
            if len(hits) > best_score:
                best_score = len(hits)
                best_dom_id = dom_id
                best_triggers = hits

        if best_dom_id and best_score > 0:
            dom_meta = domains[best_dom_id]
            primary_sk = dom_meta.get("primary_skill", "NK-Master-Hub")
            return {
                "domain_id": best_dom_id,
                "domain_name": dom_meta.get("name", ""),
                "primary_skill": primary_sk,
                "matched_skills": [primary_sk],
                "native_subagent": _resolve_native_subagent(
                    best_dom_id, matched_skill=primary_sk, text=clean_text
                ),
                "matched_triggers": best_triggers,
            }

        for kw, entry in dispatch_table.items():
            if _token_matches_keyword(kw, clean_text, tokens, min_sub_len=4):
                dom_id = entry.get("domain_id", "DOM-03")
                primary_sk = entry.get("primary_agent", "NK-Python-Async-Builder")
                return {
                    "domain_id": dom_id,
                    "domain_name": entry.get("domain_name", "BUILD_AND_HEAL"),
                    "primary_skill": primary_sk,
                    "matched_skills": [primary_sk],
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=clean_text
                    ),
                    "matched_triggers": [kw],
                }

        is_disc = any(kw in clean_text for kw in self.DISCOVERY_KEYWORDS)
        if is_disc:
            return {
                "domain_id": "DOM-02",
                "domain_name": "IDEATION_AND_ARCH",
                "primary_skill": "NK-Ideator",
                "matched_skills": ["NK-Ideator"],
                "native_subagent": "NK-Specifier-Agent",
                "matched_triggers": [],
            }
        return {
            "domain_id": "DOM-03",
            "domain_name": "BUILD_AND_HEAL",
            "primary_skill": "NK-Python-Async-Builder",
            "matched_skills": ["NK-Python-Async-Builder"],
            "native_subagent": _resolve_native_subagent(
                "DOM-03", matched_skill="NK-Python-Async-Builder", text=clean_text
            ),
            "matched_triggers": [],
        }

    @staticmethod
    def _diff_changed_lines(prod_lines: List[str], staged_lines: List[str]) -> int:
        """Conta le righe effettivamente modificate/aggiunte/rimosse tramite SequenceMatcher."""
        matcher = difflib.SequenceMatcher(None, prod_lines, staged_lines)
        changed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                changed += max(i2 - i1, j2 - j1)
        return changed

    def _estimate_changed_loc(
        self,
        files: Optional[List[str]] = None,
        changed_lines: Optional[int] = None,
    ) -> int:
        """Stima le righe modificate dal parametro changed_lines o dal diff in staging."""
        if changed_lines is not None:
            return max(0, int(changed_lines))
        if not files:
            return 0
        total_loc = 0
        ws_resolved = self.workspace_root.resolve()
        stg_resolved = self.staging_dir.resolve()
        for file_arg in files:
            p = Path(file_arg)
            staged_p: Optional[Path] = None
            prod_p: Optional[Path] = None
            if not p.is_absolute():
                rel_parts = [pt for pt in p.parts if pt != ".staging"]
                rel_path = Path(*rel_parts) if rel_parts else p
                staged_p = self.staging_dir / rel_path
                prod_p = self.workspace_root / rel_path
            else:
                p_res = p.resolve()
                if ".staging" in p_res.parts:
                    idx = list(p_res.parts).index(".staging")
                    staged_p = p_res
                    if idx + 1 < len(p_res.parts):
                        prod_p = Path(*p_res.parts[:idx]).joinpath(
                            *p_res.parts[idx + 1 :]
                        )
                else:
                    try:
                        rel_to_ws = p_res.relative_to(ws_resolved)
                        staged_p = stg_resolved / rel_to_ws
                        prod_p = p_res
                    except ValueError:
                        if p_res.exists() and p_res.is_file():
                            total_loc += len(
                                p_res.read_text(
                                    encoding="utf-8", errors="replace"
                                ).splitlines()
                            )
                        continue

            if staged_p is not None and staged_p.exists() and staged_p.is_file():
                s_lines = staged_p.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if prod_p is not None and prod_p.exists() and prod_p.is_file():
                    p_lines = prod_p.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    total_loc += self._diff_changed_lines(p_lines, s_lines)
                else:
                    total_loc += len(s_lines)
        return total_loc

    def classify_prompt_intent(
        self,
        prompt: str,
        files: Optional[List[str]] = None,
        changed_lines: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Classifica il prompt, attiva Mode D su discovery pura e risolve skill e sub-agente."""
        raw_text = (prompt or "").strip()
        if is_passive_state_handoff(raw_text):
            return {
                "recommended_mode": "mode_d",
                "mode": MODE_D_LABEL,
                "mode_label": MODE_D_LABEL,
                "is_discovery": True,
                "read_only": True,
                "standby_mode": True,
                "bypass_reason": "STATE_HANDOFF_STANDBY",
                "matched_keywords": ["state_handoff"],
                "primary_agent": "NK-Session-Controller",
                "matched_skills": ["NK-Session-Controller"],
                "native_subagent": "NK-Specifier-Agent",
                "fast_bypass_eligible": False,
                "changed_lines": 0,
                "role_conflicts": [],
                "domain_id": "DOM-01",
                "domain_name": "GOV_AND_ROUTING",
                "tools_allowed": [
                    "view_file",
                    "list_resources",
                    "read_resource",
                ],
                "prompt": prompt,
                "reason": "Passive Session State Handoff detected (STATE_HANDOFF_STANDBY).",
            }
        text_lower = raw_text.lower()
        clean_text = _sanitize_tetralogia_filenames(text_lower)
        has_code_files = bool(files and len(files) > 0)
        matched = [kw for kw in self.DISCOVERY_KEYWORDS if kw in text_lower]
        domain_info = self.resolve_domain_from_manifest(prompt)

        has_write_intent = _has_imperative_write_keyword(
            clean_text
        ) or _has_imperative_write_keyword(text_lower)

        phase_count = len(
            re.findall(r"\b(?:FASE|PHASE)\s+\d+\b", raw_text, re.IGNORECASE)
        )
        prompt_len = len(raw_text)
        role_conflicts = _detect_prompt_role_conflicts(raw_text)
        total_loc = self._estimate_changed_loc(files=files, changed_lines=changed_lines)

        is_dom04_tech_audit = domain_info["domain_id"] == "DOM-04" and any(
            tkw in text_lower for tkw in _DOM04_TECHNICAL_AUDIT_KEYWORDS
        )

        if (
            matched
            and not has_code_files
            and not has_write_intent
            and (phase_count < 2 or not has_write_intent)
            and (changed_lines is None or changed_lines == 0)
        ):
            if is_dom04_tech_audit:
                primary_ag = domain_info.get("primary_skill", "NK-Security-Auditor")
                native_sub = domain_info.get(
                    "native_subagent", "NK-Security-DAST-Auditor"
                )
                matched_sk = domain_info.get("matched_skills", [primary_ag])
                dom_id = domain_info["domain_id"]
                dom_name = domain_info["domain_name"]
            else:
                primary_ag = "NK-Ideator"
                native_sub = "NK-Specifier-Agent"
                matched_sk = ["NK-Ideator"]
                dom_id = (
                    "DOM-02"
                    if domain_info["domain_id"] == "DOM-03"
                    else domain_info["domain_id"]
                )
                dom_name = (
                    "IDEATION_AND_ARCH"
                    if dom_id == "DOM-02"
                    else domain_info["domain_name"]
                )

            return {
                "recommended_mode": "mode_d",
                "mode": MODE_D_LABEL,
                "mode_label": MODE_D_LABEL,
                "is_discovery": True,
                "read_only": True,
                "matched_keywords": matched,
                "primary_agent": primary_ag,
                "matched_skills": matched_sk,
                "native_subagent": native_sub,
                "fast_bypass_eligible": False,
                "changed_lines": total_loc,
                "role_conflicts": role_conflicts,
                "domain_id": dom_id,
                "domain_name": dom_name,
                "tools_allowed": [
                    "view_file",
                    "search_web",
                    "read_url_content",
                    "call_mcp_tool",
                    "list_resources",
                    "read_resource",
                ],
                "prompt": prompt,
                "reason": (
                    f"Analytical discovery intent detected via keywords: {matched}"
                ),
            }

        primary_ag = domain_info.get("primary_skill", "NK-Python-Async-Builder")
        matched_sk = domain_info.get("matched_skills", [primary_ag])
        native_sub = domain_info.get(
            "native_subagent",
            _resolve_native_subagent(
                domain_info["domain_id"],
                matched_skill=primary_ag,
                text=text_lower,
            ),
        )

        if (
            phase_count >= 2
            or (prompt_len > 1500 and (has_write_intent or not matched))
            or any(
                k in text_lower
                for k in (
                    "allinea 1:1",
                    "turno 4",
                    "auto-brief",
                    "cold review",
                    "6 gate",
                    "oracolo",
                    "multi-file",
                    "multifile",
                )
            )
        ):
            rec_mode = "mode_a"
        elif (
            total_loc > self.MODE_C_MAX_LOC
            or prompt_len > self.MODE_C_MAX_PROMPT_CHARS
            or any(
                k in text_lower
                for k in ("sbfl", "ochiai", "causa radice", "rca", "falsi bug")
            )
        ):
            rec_mode = "mode_b"
        else:
            rec_mode = "mode_c"

        fast_bypass_eligible = bool(
            rec_mode == "mode_c"
            and total_loc <= self.MODE_C_MAX_LOC
            and prompt_len <= self.MODE_C_MAX_PROMPT_CHARS
            and phase_count < 2
            and not role_conflicts
        )

        return {
            "recommended_mode": rec_mode,
            "mode": "Mode A/B/C (Code & Specification Routing)",
            "mode_label": "Mode A/B/C (Code & Specification Routing)",
            "is_discovery": False,
            "read_only": False,
            "matched_keywords": matched,
            "primary_agent": primary_ag,
            "matched_skills": matched_sk,
            "native_subagent": native_sub,
            "fast_bypass_eligible": fast_bypass_eligible,
            "changed_lines": total_loc,
            "role_conflicts": role_conflicts,
            "domain_id": domain_info["domain_id"],
            "domain_name": domain_info["domain_name"],
            "tools_allowed": [],
            "prompt": prompt,
            "reason": (
                f"Escalated to {rec_mode} (changed_lines={total_loc}, phases={phase_count})."
                if rec_mode != "mode_c"
                else "Standard implementation or file modification routing."
            ),
        }

    def validate_generated_prompt(
        self, file_or_text: str, mode: str = "auto"
    ) -> Dict[str, Any]:
        """Valida un prompt generato (da file o testo) contro gli anti-pattern AP-1..AP-13."""
        raw_arg = (file_or_text or "").strip()
        text = raw_arg
        if raw_arg and len(raw_arg) < 512 and "\n" not in raw_arg:
            cand = Path(raw_arg)
            if not cand.is_absolute():
                cand_ws = self.workspace_root / raw_arg
                if cand_ws.exists() and cand_ws.is_file():
                    cand = cand_ws
            if cand.exists() and cand.is_file():
                text = cand.read_text(encoding="utf-8", errors="replace")
        return lint_nk_prompt(text, mode=mode)

    def compute_ast_risk_score(
        self,
        source_code: str,
        filename: str = "snippet.py",
    ) -> Dict[str, Any]:
        """Calcola il punteggio di rischio AST (0.0 - 1.0) e la profondita max_depth."""
        if not filename.endswith(".py"):
            lines = [
                line.strip() for line in source_code.splitlines() if line.strip()
            ]
            loc = len(lines)
            risk = min(1.0, round(loc / 300.0, 2))
            eligible = risk <= 0.5 and loc <= self.MODE_C_MAX_LOC
            recommended_mode = (
                "mode_c" if eligible else ("mode_b" if loc <= 300 else "mode_a")
            )
            return {
                "risk_score": risk,
                "mode_eligible": eligible,
                "fast_bypass_eligible": eligible,
                "native_subagent": "NK-Builder-Agent",
                "recommended_mode": recommended_mode,
                "max_depth": 0,
                "reason": f"Non-Python asset ({loc} LOC). Mode C eligible: {eligible}",
                "loc": loc,
            }

        try:
            tree = ast.parse(source_code, filename=filename)
        except SyntaxError as exc:
            return {
                "risk_score": 1.0,
                "mode_eligible": False,
                "fast_bypass_eligible": False,
                "native_subagent": "NK-Builder-Agent",
                "recommended_mode": "mode_a",
                "max_depth": 0,
                "reason": f"SyntaxError in code: {exc}",
                "loc": len(source_code.splitlines()),
            }

        class_count = 0
        func_count = 0
        import_count = 0
        loc = len(source_code.splitlines())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_count += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_count += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_count += 1

        depth_visitor = _ASTDepthVisitor()
        depth_visitor.visit(tree)
        max_depth = depth_visitor.max_depth

        depth_penalty = min(0.25, max(0, max_depth - 2) * 0.05)
        risk = (
            min(0.35, (loc / 250.0) * 0.35)
            + min(0.25, class_count * 0.12)
            + min(0.15, import_count * 0.04)
            + min(0.10, func_count * 0.02)
            + depth_penalty
        )
        risk = round(min(1.0, risk), 2)
        eligible = risk <= 0.5 and loc <= self.MODE_C_MAX_LOC and max_depth <= 6

        if eligible:
            recommended_mode = "mode_c"
        elif risk <= 0.75 and loc <= 350:
            recommended_mode = "mode_b"
        else:
            recommended_mode = "mode_a"

        return {
            "risk_score": risk,
            "mode_eligible": eligible,
            "fast_bypass_eligible": eligible,
            "native_subagent": "NK-Builder-Agent",
            "recommended_mode": recommended_mode,
            "loc": loc,
            "classes": class_count,
            "functions": func_count,
            "imports": import_count,
            "max_depth": max_depth,
            "reason": (
                "Safe for Mode C Vibe-Sprint"
                if eligible
                else "Exceeds Mode C risk threshold (requires Mode A/B)"
            ),
        }

    def generate_inline_micro_spec(
        self,
        target_file: str,
        change_intent: str,
        risk_info: Dict[str, Any],
    ) -> str:
        """Sintetizza una micro-specifica inline inferiore a 150 token."""
        capsule = self.load_prewarmed_capsule()
        capsule_summary = str(capsule.get("capsule_text", "")).strip()
        if not capsule_summary and isinstance(capsule.get("lessons"), list):
            capsule_summary = " | ".join(
                str(item.get("lesson", ""))
                for item in capsule["lessons"][:3]
                if isinstance(item, dict) and item.get("lesson")
            ).strip()
        spec = [
            f"[NK-VIBE-SPRINT-SPEC | Target: {target_file}]",
            f"Intent: {change_intent.strip()}",
            f"Risk Score: {risk_info.get('risk_score', 0.0)} | LOC: {risk_info.get('loc', 0)} | Max Depth: {risk_info.get('max_depth', 0)}",
            "Mode: Mode C (Fast Staging -> AST Guard -> Zero-Mock Verification -> 2PC Commit)",
            "Safety Invariant: Zero-Mock / Real fixture adherence.",
        ]
        if capsule_summary:
            spec.append(f"Tier-1 Capsule: {capsule_summary[:240]}")
        return "\n".join(spec)

    def load_prewarmed_capsule(self, compact: bool = False) -> Dict[str, Any]:
        """Carica la capsula di memoria Tier-1 pre-riscaldata con fallback a memory_3tier."""
        candidates = (
            self.staging_dir / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.workspace_root / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.staging_dir
            / "nk_tracking"
            / "memory_3tier"
            / "tier1_active_capsule.json",
            self.workspace_root
            / "nk_tracking"
            / "memory_3tier"
            / "tier1_active_capsule.json",
        )
        for cand in candidates:
            if cand.exists():
                try:
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        if compact and isinstance(data.get("domains"), dict):
                            compacted = dict(data)
                            compacted_domains: Dict[str, Any] = {}
                            for dom_k, dom_v in data["domains"].items():
                                if isinstance(dom_v, dict) and int(dom_v.get("total_tokens", 0)) > 0:
                                    dom_copy = {
                                        k: v
                                        for k, v in dom_v.items()
                                        if k != "context"
                                    }
                                    compacted_domains[dom_k] = dom_copy
                            compacted["domains"] = compacted_domains
                            return compacted
                        return data
                except Exception:
                    pass
        return {
            "status": "EMPTY",
            "capsule_text": "",
            "token_count": 0,
            "token_cap": 350,
            "entries": [],
        }

    def format_compact_env_capsule(self) -> str:
        """Formatta un blocco <env_capsule> deduplicato sotto i 280 token."""
        cap = self.load_prewarmed_capsule(compact=True)
        lessons = cap.get("lessons", [])
        lines = ["<env_capsule>", f"Working Directory: {self.workspace_root.as_posix()}"]
        if isinstance(lessons, list):
            for item in lessons[:4]:
                if isinstance(item, dict) and item.get("lesson"):
                    lines.append(f"- {str(item['lesson'])[:180]}")
        lines.append("</env_capsule>")
        return "\n".join(lines)


def resolve_domain_from_manifest(
    prompt: str,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per risolvere il dominio O(1) dal manifesto SSOT."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.resolve_domain_from_manifest(prompt=prompt)


def resolve_intrinsic_vibe_protocols(
    prompt: str,
    recommended_mode: str = "mode_c",
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per risolvere i protocolli intrinseci /goal, /boost e /plan."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.resolve_intrinsic_vibe_protocols(
        prompt=prompt,
        recommended_mode=recommended_mode,
    )


def classify_prompt_intent(
    prompt: str,
    files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
    changed_lines: Optional[int] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per classificare l'intento del prompt (Mode D vs A/B/C)."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.classify_prompt_intent(
        prompt=prompt, files=files, changed_lines=changed_lines
    )


def normalize_voice_stt_input(
    raw_prompt: str,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per normalizzare l'input vocale STT."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.normalize_voice_stt_input(raw_prompt=raw_prompt)


def is_gate_exempt(
    raw_prompt: str,
    workspace_root: Optional[Path] = None,
) -> bool:
    """Funzione helper di modulo per verificare le 5 esenzioni anti-loop."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.is_gate_exempt(raw_prompt=raw_prompt)


def build_meta_prompt_envelope(
    prompt: str,
    gate_enabled: bool = True,
    gate_mode: str = "CONFIRM",
    files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
    compact: bool = False,
    auto_bypass_readonly: bool = False,
) -> Dict[str, Any]:
    """Funzione helper di modulo per costruire il contratto MetaPromptGateContract."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.build_meta_prompt_envelope(
        prompt=prompt,
        gate_enabled=gate_enabled,
        gate_mode=gate_mode,
        files=files,
        compact=compact,
        auto_bypass_readonly=auto_bypass_readonly,
    )


def evaluate_meta_prompt_gate(
    raw_prompt: str,
    workspace_root: Optional[Path] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Funzione helper di modulo per valutare il Gate L0 tramite build_meta_prompt_envelope."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.build_meta_prompt_envelope(prompt=raw_prompt, **kwargs)


def format_meta_prompt_markdown(
    envelope: Dict[str, Any],
    workspace_root: Optional[Path] = None,
) -> str:
    """Funzione helper di modulo per formattare il blocco Markdown visibile di Livello 0."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.format_meta_prompt_markdown(envelope=envelope)


def validate_generated_prompt(
    file_or_text: str,
    workspace_root: Optional[Path] = None,
    mode: str = "auto",
) -> Dict[str, Any]:
    """Funzione helper di modulo per validare un prompt contro gli anti-pattern AP-1..AP-13."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.validate_generated_prompt(file_or_text=file_or_text, mode=mode)


def load_prewarmed_capsule(
    workspace_root: Optional[Path] = None,
    compact: bool = False,
) -> Dict[str, Any]:
    """Funzione helper di modulo per caricare la capsula Tier-1 pre-riscaldata."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.load_prewarmed_capsule(compact=compact)


def format_compact_env_capsule(workspace_root: Optional[Path] = None) -> str:
    """Funzione helper di modulo per formattare <env_capsule> deduplicato."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.format_compact_env_capsule()


def run_test() -> int:
    """Esegue l'autotest rapido del router Mode C, Mode D e Meta-Prompt Gate."""
    router = VibeSprintRouter()
    code_sample = '''
def calculate_vat(amount: float, rate: float = 0.22) -> float:
    """Calcola l'IVA per una transazione."""
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    return round(amount * rate, 2)
'''
    res = router.compute_ast_risk_score(code_sample, "tax_calculator.py")
    assert res["mode_eligible"] is True
    assert res["max_depth"] >= 2
    spec = router.generate_inline_micro_spec(
        "src_app/utils/tax.py",
        "Add VAT calculation",
        res,
    )
    assert "NK-VIBE-SPRINT-SPEC" in spec
    disc = router.classify_prompt_intent("Esegui audit e benchmark copertura bandi")
    assert disc["recommended_mode"] == "mode_d"
    assert "domain_id" in disc
    env = router.build_meta_prompt_envelope(
        "Analizza primaLa struttura e l'implementazione attuale"
    )
    assert env["fsm_state"] == "AWAIT_CONFIRM"
    assert len(env["intent_hash_sha256"]) == 64
    assert "INTRINSIC_BOOST" in env["intrinsic_protocols"]
    print(
        f"VibeSprintRouter test PASS: Risk {res['risk_score']} | Depth {res['max_depth']}"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il router Mode A/B/C/D di Nexus Keystone."""
    parser = argparse.ArgumentParser(
        description="Router Mode A/B/C/D basato sul rischio AST e intento prompt per Nexus Keystone"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Esegue l'autotest rapido del router",
    )
    parser.add_argument(
        "--prompt",
        "--task",
        dest="prompt",
        type=str,
        default="Vibe Sprint Change",
        help="Descrizione sintetica dell'intento di modifica o discovery",
    )
    parser.add_argument(
        "--classify-prompt",
        nargs="?",
        const="__USE_PROMPT__",
        default=None,
        help="Classifica l'intento del prompt e restituisce modalita, dominio e sub-agente",
    )
    parser.add_argument(
        "--meta-prompt-gate",
        action="store_true",
        help="Costruisce e valida il contratto MetaPromptGateContract per il prompt fornito",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Disabilita o bypassa il Meta-Prompt Gate per l'invocazione corrente",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Attiva il profilo compatto a bassa latenza per il Meta-Prompt Gate L0",
    )
    parser.add_argument(
        "--auto-bypass-readonly",
        action="store_true",
        help="Attiva il bypass automatico L0 per richieste Mode D Read-Only o Mode C Fast-Sprint",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Modalita operativa opzionale",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Elenco dei file sorgente da valutare per il routing",
    )
    parser.add_argument(
        "--changed-lines",
        type=int,
        default=None,
        help="Numero di righe modificate nel diff staged per escalation Mode C -> Mode B",
    )
    parser.add_argument(
        "--validate-generated-prompt",
        "--lint-prompt",
        dest="validate_generated_prompt",
        nargs="?",
        const="__USE_PROMPT__",
        type=str,
        default=None,
        help="Valida un prompt generato (file o testo) contro gli anti-pattern AP-1..AP-13",
    )
    parser.add_argument(
        "--discovery-check",
        action="store_true",
        help="Valuta l'intento del prompt per attivare Mode D Read-Only Discovery",
    )
    parser.add_argument(
        "--capsule",
        action="store_true",
        help="Include e stampa la capsula di memoria Tier-1 pre-riscaldata",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il verdetto di routing in formato JSON",
    )
    args = parser.parse_args(argv)

    if args.test:
        return run_test()

    router = VibeSprintRouter()

    if args.validate_generated_prompt is not None:
        target_lint_input = (
            args.prompt
            if args.validate_generated_prompt == "__USE_PROMPT__"
            else args.validate_generated_prompt
        )
        lint_res = router.validate_generated_prompt(
            target_lint_input, mode=args.mode or "auto"
        )
        if args.json:
            print(json.dumps(lint_res, indent=2, ensure_ascii=False))
        else:
            status_str = "PASS" if lint_res["valid"] else "FAIL"
            print(
                f"[NK-PROMPT-LINTER] Status: {status_str} | Violations: {lint_res['violation_count']}"
            )
            for v in lint_res["violations"]:
                print(f"  - [{v['id']}] ({v['severity']}): {v['msg']}")
        return 0 if lint_res["valid"] else 1

    effective_prompt = args.prompt
    if (
        args.classify_prompt is not None
        and args.classify_prompt != "__USE_PROMPT__"
        and args.prompt == "Vibe Sprint Change"
    ):
        effective_prompt = str(args.classify_prompt)

    if args.meta_prompt_gate or args.no_gate:
        envelope = router.build_meta_prompt_envelope(
            effective_prompt,
            gate_enabled=not args.no_gate,
            gate_mode="OFF" if args.no_gate else "CONFIRM",
            files=args.files,
            compact=bool(args.compact),
            auto_bypass_readonly=bool(args.auto_bypass_readonly),
        )
        if args.json:
            print(json.dumps(envelope, indent=2 if not args.compact else None, ensure_ascii=False))
        elif args.compact:
            print(
                f"[L0-COMPACT] {envelope['brief_id']} | {envelope['fsm_state']} | "
                f"{envelope['recommended_mode']} | {envelope['primary_agent']}"
            )
        else:
            protos = ",".join(envelope.get("intrinsic_protocols", []))
            print(
                f"[META-PROMPT-GATE] Brief: {envelope['brief_id']} | "
                f"State: {envelope['fsm_state']} | Mode: {envelope['recommended_mode']} | "
                f"Protocols: {protos} | "
                f"Scope: {envelope.get('bypass_scope', 'NONE')} | "
                f"Agent: {envelope['primary_agent']} | SHA256: {envelope['intent_hash_sha256'][:12]}"
            )
            print()
            print(envelope["rendered_markdown"])
        return 0

    if args.files:
        results: List[Dict[str, Any]] = []
        for file_arg in args.files:
            p = Path(file_arg)
            if not p.is_absolute():
                p = (router.workspace_root / p).resolve()
            if p.exists() and p.is_file():
                code = p.read_text(encoding="utf-8", errors="replace")
                info = router.compute_ast_risk_score(code, p.name)
            else:
                info = router.compute_ast_risk_score("", p.name)
            if (
                args.changed_lines is not None
                and args.changed_lines > router.MODE_C_MAX_LOC
                and info["recommended_mode"] == "mode_c"
            ):
                info["recommended_mode"] = "mode_b"
                info["mode_eligible"] = False
                info["fast_bypass_eligible"] = False
                info["reason"] = (
                    f"Escalated from Mode C to Mode B due to changed_lines={args.changed_lines} > 150"
                )
            info["file"] = str(file_arg)
            info["micro_spec"] = router.generate_inline_micro_spec(
                str(file_arg),
                effective_prompt,
                info,
            )
            results.append(info)
        payload: Dict[str, Any] = {"files": results}
        if args.capsule:
            payload["tier1_capsule"] = router.load_prewarmed_capsule(
                compact=bool(args.compact)
            )
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for item in results:
                print(item["micro_spec"])
        return 0

    intent = router.classify_prompt_intent(
        effective_prompt, files=args.files, changed_lines=args.changed_lines
    )
    prompt_explicit = (
        args.classify_prompt is not None
        or args.discovery_check
        or args.changed_lines is not None
        or effective_prompt != "Vibe Sprint Change"
    )
    if prompt_explicit or intent["is_discovery"]:
        if args.capsule:
            intent["tier1_capsule"] = router.load_prewarmed_capsule(
                compact=bool(args.compact)
            )
        if args.json:
            print(json.dumps(intent, indent=2, ensure_ascii=False))
        else:
            print(
                f"[{intent['mode_label']}] | Mode: {intent['recommended_mode']} | "
                f"Agent: {intent['primary_agent']} | Subagent: {intent['native_subagent']} | "
                f"Domain: {intent['domain_id']}"
            )
        return 0

    if args.capsule:
        cap = router.load_prewarmed_capsule(compact=bool(args.compact))
        print(json.dumps(cap, indent=2, ensure_ascii=False))
        return 0

    print("VibeSprintRouter CLI ready. Use --test to validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

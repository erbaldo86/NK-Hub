"""Costanti keyword e pattern regex condivisi per vibe_sprint_router."""

from __future__ import annotations

import re
from typing import Any, Dict, Set, Tuple

from _internal.nk_common.epistemic_firewall_rules import (
    HANDOFF_V2_END_ACTIVE,
    HANDOFF_V2_END_PASSIVE,
    HANDOFF_V2_START_ACTIVE,
    HANDOFF_V2_START_PASSIVE,
    T12_END,
    T12_START,
    _AGENT_DIRECTIVE_CUE_RE,
    _OUTBOUND_CODE_EXCLUSION_RE,
    _OUTBOUND_HANDOFF_RE,
)

_DOM04_TECHNICAL_AUDIT_KEYWORDS: Tuple[str, ...] = (
    "audit",
    "forense",
    "incongruenze",
    "incongruenza",
    "controllo tas",
    "audit tas",
    "tas",
    "analizza refactoring",
    "analisi refactoring",
    "analizza il refactoring",
    "analisi del refactoring",
    "sast",
    "dast",
    "stress test",
    "stress",
    "rca",
    "red team",
    "red-team",
    "security",
    "sicurezza",
    "vulnerabilit",
    "exploit",
    "sandbox",
    "causa radice",
    "diagnosi",
    "e2e",
    "puppeteer",
    "chrome-devtools",
    "lighthouse",
    "sbfl",
    "ochiai",
    "tarantula",
    "dstar",
    "cold review",
    "6 gate",
    "oracolo",
    "oracle",
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
    r"|consigli[oa]\s+di\s+(?:utilizzare|usare|attivare|digitare|invocare|eseguire)"
    r"|ti\s+suggerisco\s+di\s+(?:utilizzare|usare|digitare|invocare))\s+[^\n]{0,60}/(?:goal|boost|plan|implementation)\b"
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
    HANDOFF_V2_START_PASSIVE.lower(),
)
_PROHIBITION_LINE_RE = re.compile(
    r"\b(?:vieta(?:to|ndo|re)?|divieto|proibit[oa]|non\s+(?:attivare|invocare|generare|eseguire|proporre|avviare|modificare|devi|impone)|mai\s+(?:attivare|invocare)|nessun[oa]?\s+(?:pista|task|opzione))\b",
    re.IGNORECASE,
)
_AP12_IMPERATIVE_LEAK_RE = re.compile(
    r"\b(?:INTRINSIC_GOAL|INTRINSIC_PLAN|INTRINSIC_BOOST|invoke_subagent|define_subagent|ask_question)\b|(?:^|\n)\s*#{1,4}\s*(?:FASE|PHASE|MACRO[- ]?FASE|LIVELLO)\s*[1-9]\d*",
    re.IGNORECASE,
)
_AP13_COGNITIVE_TUNNELING_RE = re.compile(
    r"\b(?:Pista\s+(?:1[A-Z]?|2[A-Z]?|[A-C])\b|Opzione\s+[A-C]\s+da\s+accettare|Seleziona\s+quale\s+(?:task|pista|opzione)\s+avviare|Scegli\s+(?:quale\s+)?(?:pista|task|opzione)|Task\s+[1-9]\s*:)",
    re.IGNORECASE,
)
_SHA256_HEX64_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_BRIEF_HEADER_PHASE_RE = re.compile(
    r"\b(?:(?:FASE|PHASE|MACRO[- ]?FASE)\s*\d+|LIVELLO\s*[1-9]\d*)\b",
    re.IGNORECASE,
)
_HANDOFF_MUTATING_ORDER_RE = re.compile(
    r"(?:\b(?:cancella(?:re)?|elimina(?:re)?|rimuovi|rimuovere|sovrascrivi|sovrascrivere|formatta(?:re)?|drop\s+table|delete\s+from|set-content|remove-item|out-file|write_file|edit_file|write_to_file)\b|(?<![A-Za-z0-9_-])--promote-staging\b)",
    re.IGNORECASE,
)
_HANDOFF_START_PREFIXES: Tuple[str, ...] = (
    "[handoff stato sessione nk-hub]",
    "[passive state handoff / standby mode]",
    "passive_session_state_handoff",
    "template 12: passive_session_state_handoff",
    "[nk-anchor:start:passive_state_handoff]",
    "[nk-anchor:start:state_handoff",
    HANDOFF_V2_START_PASSIVE.lower(),
)

_ROUTER_MANIFEST_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}

__all__ = [
    "HANDOFF_V2_END_ACTIVE",
    "HANDOFF_V2_END_PASSIVE",
    "HANDOFF_V2_START_ACTIVE",
    "HANDOFF_V2_START_PASSIVE",
    "T12_END",
    "T12_START",
    "_AGENT_DIRECTIVE_CUE_RE",
    "_AP10_PASSIVE_SLASH_RE",
    "_AP10_PROHIBITION_CONTEXT_RE",
    "_AP12_IMPERATIVE_LEAK_RE",
    "_AP13_COGNITIVE_TUNNELING_RE",
    "_BRIEF_HEADER_PHASE_RE",
    "_CLAUSE_SPLIT_RE",
    "_DOM04_TECHNICAL_AUDIT_KEYWORDS",
    "_HANDOFF_MUTATING_ORDER_RE",
    "_HANDOFF_START_PREFIXES",
    "_INTRINSIC_BOOST_KEYWORDS",
    "_INTRINSIC_PLAN_KEYWORDS",
    "_OUTBOUND_CODE_EXCLUSION_RE",
    "_OUTBOUND_HANDOFF_RE",
    "_PROHIBITION_LINE_RE",
    "_ROUTER_MANIFEST_CACHE",
    "_SHA256_HEX64_RE",
    "_STATE_HANDOFF_MARKERS",
    "_TECH_CAMEL_ALLOWLIST",
]

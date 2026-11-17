# -*- coding: utf-8 -*-
"""Motore unificato AP-1..AP-13 e AP-2b compatibile con prompt_linter e nk_transcript_tools."""

from __future__ import annotations

import re
from typing import Dict, Tuple

_READ_ONLY_ROLES: Tuple[str, ...] = (
    "NK-Oracle-Evaluator",
    "NK-Security-DAST-Auditor",
    "NK-Security-Auditor",
    "NK-RSI-Auditor",
    "NK-Arch-Specifier",
)
_ORCHESTRATOR_ROLES: Tuple[str, ...] = (
    "NK-Orchestrator",
)

_BRIEF_HEADER_PHASE_RE = re.compile(
    r"\b(?:(?:FASE|PHASE|MACRO[- ]?FASE)\s*\d+|LIVELLO\s*[1-9]\d*)\b",
    re.IGNORECASE,
)
_STATE_HANDOFF_HEADER_RE = re.compile(
    r"\[HANDOFF STATO SESSIONE NK-HUB\]|\[PASSIVE STATE HANDOFF / STANDBY MODE\]|"
    r"PASSIVE_SESSION_STATE_HANDOFF|\[NK-ANCHOR:START:(?:PASSIVE_)?STATE_HANDOFF",
    re.IGNORECASE,
)
_HANDOFF_START_PREFIXES: Tuple[str, ...] = (
    "[handoff stato sessione nk-hub]",
    "[passive state handoff / standby mode]",
    "passive_session_state_handoff",
    "template 12: passive_session_state_handoff",
    "[nk-anchor:start:passive_state_handoff]",
    "[nk-anchor:start:state_handoff",
)
_AP10_PASSIVE_SLASH_RE = re.compile(
    r"(?:puoi\s+(?:utilizzare|usare|attivare|lanciare|digitare|invocare|eseguire)(?:\s+anche)?(?:\s+il\s+comando)?"
    r"|digita(?:\s+manualmente)?(?:\s+il\s+comando)?"
    r"|basta\s+(?:digitare|usare|lanciare|invocare|eseguire)(?:\s+il\s+comando)?"
    r"|esegui\s+manualmente(?:\s+il\s+comando)?"
    r"|usa(?:\s+manualmente)?(?:\s+il\s+comando)?"
    r"|consigli[oa]\s+di\s+(?:utilizzare|usare|attivare|digitare|invocare|eseguire)"
    r"|ti\s+suggerisco\s+di\s+(?:utilizzare|usare|digitare|lanciare|invocare))\s+[^\n]{0,60}/(?:goal|boost|plan|implementation)\b"
    r"|(?:in un unico passaggio|senza fermarti mai|non usare subagent)",
    re.IGNORECASE,
)
_AP10_PROHIBITION_CONTEXT_RE = re.compile(
    r"\b(?:vieta(?:to|ndo|re)?|proibit[oa]|nessun\s+agente|non\s+deve|"
    r"non\s+(?:chiedere|suggerire|consigliare)|mai\s+(?:chiedere|suggerire)|senza\s+chiedere|ap-10)\b",
    re.IGNORECASE,
)
_PROHIBITION_LINE_RE = re.compile(
    r"\b(?:vieta(?:to|ndo|re)?|divieto|proibit[oa]|"
    r"non\s+(?:attivare|invocare|generare|eseguire|proporre|avviare)|"
    r"mai\s+(?:attivare|invocare)|zero\s+|senza\s+|nessun[oa]?\s+(?:pista|task|opzione)|ap-12|ap-13)\b",
    re.IGNORECASE,
)
_AP12_IMPERATIVE_LEAK_RE = re.compile(
    r"\b(?:INTRINSIC_GOAL|INTRINSIC_PLAN|INTRINSIC_BOOST|invoke_subagent|define_subagent|ask_question)\b"
    r"|(?:^|\n)\s*#{1,4}\s*(?:FASE|PHASE|MACRO[- ]?FASE|LIVELLO)\s*[1-9]\d*",
    re.IGNORECASE,
)
_AP13_COGNITIVE_TUNNELING_RE = re.compile(
    r"\b(?:Pista\s+(?:1[A-Z]?|2[A-Z]?|[A-C])\b|Opzione\s+[A-C]\s+da\s+accettare|"
    r"Seleziona\s+quale\s+(?:task|pista|opzione)\s+avviare|"
    r"Scegli\s+(?:quale\s+)?(?:pista|task|opzione)|Task\s+[1-9]\s*:)",
    re.IGNORECASE,
)
_STRICT_MUTATION_RE = re.compile(
    r"(?:applica(?:re)?\s+la\s+soluzione|\bmodifica(?:re)?\b|crea\s+un\s+test|"
    r"salva\s+tutti\s+i\s+risultati|aggiorna\s+README|src_app[/\\]|tests[/\\])",
    re.IGNORECASE,
)
_BROAD_WRITE_INTENT_RE = re.compile(
    r"(?:src_app|\bimplementa(?:re)?\b|\bmodifica(?:re)?\b|\bscrivi\b|"
    r"\bscrivere\b|\baggiorna(?:re)?\b|\bbuild\b|\bcodice\b)",
    re.IGNORECASE,
)
_DIRETTO_RE = re.compile(r"(!diretto|\bProceed\b)", re.IGNORECASE)
_GOODHART_RE = re.compile(
    r"(?:finch[eé]|finche|until)[^\n]{0,120}100(?:\.0)?%\s*pass",
    re.IGNORECASE,
)


def _make_lint_violation(
    code: str, severity: str, message: str, rule: str = ""
) -> Dict[str, str]:
    """Costruisce un record di violazione con chiavi compatibili su router e transcript_tools."""
    rec: Dict[str, str] = {
        "code": code,
        "id": code,
        "severity": severity,
        "message": message,
        "msg": message,
    }
    if rule:
        rec["rule"] = rule
    return rec

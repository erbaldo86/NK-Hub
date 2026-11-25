# -*- coding: utf-8 -*-
"""Motore unificato AP-1..AP-13 e AP-2b compatibile con prompt_linter e nk_transcript_tools."""

from __future__ import annotations

import re
from typing import Dict, Tuple

from _internal.nk_common.epistemic_firewall_patterns import (  # noqa: F401
    _AP12_IMPERATIVE_LEAK_RE,
    _AP13_COGNITIVE_TUNNELING_RE,
    _PROHIBITION_LINE_RE,
)

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
_NATIVE_WRITE_AGENTS: Tuple[str, ...] = (
    "nk-builder-agent",
    "nk-scribe-agent",
    "nk-specifier-agent",
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
    r"(?:finch[eé]|finche|until|fino\s+al?|while\s+not)[^\n]{0,120}"
    r"(?:100(?:\.0)?\s*%\s*(?:di\s+)?(?:pass|success|verdi?)|"
    r"(?:all\s+tests|tutti\s+i\s+test)[^\n]{0,40}\b(?:pass|passano|verdi)\b)",
    re.IGNORECASE,
)
_ENABLE_WRITE_TRUE_RE = re.compile(r"enable_?write_?tools\s*[:=]\s*true\b", re.IGNORECASE)
_SELF_AGENT_INVOKE_RE = re.compile(
    r"(?:invoke_subagent\b[^\n;]{0,120}(?:typename|type_name)\s*[:=]\s*[\"']self[\"']|"
    r"invoke_subagent\s*\(\s*[\"']self[\"']|"
    r"(?:typename|type_name)\s*[:=]\s*[\"']self[\"'][^\n;]{0,120}invoke_subagent\b)",
    re.IGNORECASE,
)
_WRITE_CALL_BLOCK_RE = re.compile(
    r"define_subagent\s*\([^)]{0,300}enable_?write_?tools\s*[:=]\s*true\b|"
    r"invoke_subagent\s*\([^)]{0,300}(?:(?:typename|type_name)\s*[:=]\s*[\"']self[\"']|"
    r"nk-(?:builder|scribe|specifier)-agent)",
    re.IGNORECASE,
)
_DELEGATION_NEGATION_RE = re.compile(
    r"\b(?:non|mai|senza|evita(?:re)?|vieta(?:to|re)?|no)\b[^\n;]{0,30}\b"
    r"(?:invoke_subagent|define_subagent|enable_?write_?tools|sub-?agents?|sharding)\b",
    re.IGNORECASE,
)
_ORACLE_LOCK_NEGATION_RE = re.compile(
    r"\b(?:non|mai|senza|ignora(?:re)?|evita(?:re)?|salta(?:re)?|bypassa(?:re)?|"
    r"disattiva(?:re)?|disabilita(?:re)?|rimuovi|rimuovere|sblocca(?:re)?|escludi)\b"
    r"[^\n;]{0,40}\boracle[-_]lock\b|"
    r"\boracle[-_]lock\b[^\n;]{0,25}(?:disabilitat[oa]|disattivat[oa]|opzionale|false)\b",
    re.IGNORECASE,
)
_AP7_DELEGATED_RE = re.compile(r"\b(?:invoke_subagent|sub-?agents?|sharding)\b", re.IGNORECASE)
_AP7_SIA_BOTH_RE = re.compile(r"\bsia\s+search_web\b[^\n]{0,40}\bsia\s+tavily\b", re.IGNORECASE)
_AP7_HIGH_Q_RE = re.compile(
    r"\b(\d+)\s*(?:[a-z]+\s+){0,2}(?:query|queries|ricerche|fonti|portali)\b",
    re.IGNORECASE,
)
_AP7_RANGE_HIGH_RE = re.compile(r"\b(?:1[1-9]|[2-9]\d)\s*-\s*\d+\b")
_AP7_SERVER_START_RE = re.compile(
    r"\b(?:avviando|avvia(?:re)?|avvio\s+del|start(?:ing)?\s+the)\s+(?:il\s+)?server\b",
    re.IGNORECASE,
)
_AP7_SERVER_NEG_RE = re.compile(
    r"\b(?:non|senza|mai|evita(?:re)?|vieta(?:to|re)?)\b[^\n;]{0,20}\b"
    r"(?:avviando|avvia(?:re)?|avvio|start(?:ing)?)\b",
    re.IGNORECASE,
)
_AP11_CANARY_LEAK_RE = re.compile(
    r"(?:canary_v1(?:\.json)?|canary-ib-|nk_holdout(?:_dir)?|canary_holdout|"
    r"tas_behavioral_v2(?:\.json)?|tasks_tas_v2(?:\.json)?|tasks_builder_v2(?:\.json)?|"
    r"oracle_holdout|oracle_lock_holdout(?:\.json)?|tests_holdout_lock(?:\.json)?)",
    re.IGNORECASE,
)


def _line_has_unnegated_native_invoke(line: str) -> bool:
    if "invoke_subagent" not in line or _DELEGATION_NEGATION_RE.search(line):
        return False
    return any(ag in line for ag in _NATIVE_WRITE_AGENTS) or bool(
        _SELF_AGENT_INVOKE_RE.search(line)
    )


def _has_write_grant_for_ap2b(low: str) -> bool:
    """Verifica concessione esplicita non negata (define_subagent/invoke_subagent nella stessa clausola)."""
    for line in re.split(r"[\n;]+", low):
        if _DELEGATION_NEGATION_RE.search(line):
            continue
        if "define_subagent" in line and _ENABLE_WRITE_TRUE_RE.search(line):
            return True
        if _line_has_unnegated_native_invoke(line):
            return True
    if _WRITE_CALL_BLOCK_RE.search(low) and not _DELEGATION_NEGATION_RE.search(low):
        return True
    return False


def _has_active_oracle_lock_for_ap4(low: str) -> bool:
    """Verifica almeno una menzione positiva non negata di oracle-lock."""
    for line in re.split(r"[\n;]+", low):
        if ("oracle-lock" in line or "oracle_lock" in line) and not _ORACLE_LOCK_NEGATION_RE.search(line):
            return True
    return False


def _has_unsharded_web_burst_for_ap7(text: str, low: str) -> bool:
    """Rileva uso ridondante di search_web + tavily su molte query senza sharding reale."""
    if "search_web" not in low or "tavily" not in low:
        return False
    has_valid_delegation = any(
        _AP7_DELEGATED_RE.search(cl) and not _DELEGATION_NEGATION_RE.search(cl)
        for cl in re.split(r"[\n;]+", low)
    )
    if has_valid_delegation:
        return False
    high_q = any(int(n) > 10 for n in _AP7_HIGH_Q_RE.findall(low))
    return (
        ("SIA la ricerca web normale" in text)
        or bool(_AP7_SIA_BOTH_RE.search(low))
        or high_q
        or bool(_AP7_RANGE_HIGH_RE.search(low))
        or ("30 " in low)
    )


def _has_unguarded_server_start_for_ap7(text: str, low: str) -> bool:
    """Rileva istruzioni positive di avvio server prive di safe_cleanup_dev_servers.py."""
    if "safe_cleanup_dev_servers.py" in low:
        return False
    return any(
        _AP7_SERVER_START_RE.search(ln) and not _AP7_SERVER_NEG_RE.search(ln)
        for ln in text.splitlines()
    )


def _has_canary_holdout_leak_for_ap11(low: str) -> bool:
    """Individua token o percorsi canary/holdout segreti nel prompt in uscita."""
    return bool(_AP11_CANARY_LEAK_RE.search(low))


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

"""Costanti di esenzione bypass, dashboard 10 nodi e normalizzazione STT."""

from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

from _internal.nk_common.constants import ONBOARDING_TRIGGERS

_SHORT_CONFIRMATIONS: Set[str] = {
    "ok",
    "si",
    "sì",
    "procedi",
    "procedi pure",
    "procedi con il piano",
    "procedi alla creazione dell implementation plan",
    "procedi alla creazione dell'implementation plan",
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
    "approvo",
    "perfetto approvo",
}
_ANTI_LOOP_EXEMPT_PREFIXES: Tuple[str, ...] = (
    "ok procedi",
    "si procedi",
    "sì procedi",
    "procedi pure",
    "procedi con il piano",
    "procedi",
    "confermo",
    "vai avanti",
    "vai pure",
    "vai",
    "proceed",
    "premi proceed",
)
_PLAN_CONFIRMATION_PREFIXES: Tuple[str, ...] = (
    "procedi alla creazione dell implementation plan",
    "procedi con il piano",
)
_ONBOARDING_TRIGGERS: Set[str] = set(ONBOARDING_TRIGGERS)
_NODE_SELECTIONS: Set[str] = {f"[{i}]" for i in range(10)} | {
    str(i) for i in range(10)
}
DASHBOARD_NODE_MAP: Dict[int, Tuple[str, str, str, str, bool]] = {
    0: ("NK-Ideator", "DOM-02", "IDEATION_AND_ARCH", "NK-Arch-Specifier", True),
    1: ("NK-System-Architect", "DOM-02", "IDEATION_AND_ARCH", "NK-Specifier-Agent", False),
    2: ("NK-Agent-Instruction-Forge", "DOM-03", "BUILD_AND_HEAL", "NK-Builder-Agent", False),
    3: ("NK-Python-Async-Builder", "DOM-03", "BUILD_AND_HEAL", "NK-Builder-Agent", False),
    4: ("NK-Delta-Architect", "DOM-03", "BUILD_AND_HEAL", "NK-Builder-Agent", False),
    5: ("NK-Security-Auditor", "DOM-04", "AUDIT_DAST_AND_RCA", "NK-Security-DAST-Auditor", True),
    6: ("NK-Oracle-Evaluator", "DOM-04", "AUDIT_DAST_AND_RCA", "NK-RSI-Auditor", True),
    7: ("NK-Dynamic-Sandbox-StressTester", "DOM-04", "AUDIT_DAST_AND_RCA", "NK-Security-DAST-Auditor", True),
    8: ("NK-Bug-Diagnostic-Engine", "DOM-04", "AUDIT_DAST_AND_RCA", "NK-Security-DAST-Auditor", True),
    9: ("NK-Scribe-Memory", "DOM-05", "MEMORY_TELEMETRY_AND_DOCS", "NK-Scribe-Agent", False),
}
_DASHBOARD_SELECTOR_RE = re.compile(r"^\s*(?:\[(\d{1,2})\]|(\d{1,2}))\s*$")


def _parse_dashboard_selector(text: Optional[str]) -> Optional[int]:
    """Risolve i selettori diretti 0..9 e [0]..[9] della dashboard NK-Orchestrator."""
    if not text or len(text) > 16:
        return None
    m = _DASHBOARD_SELECTOR_RE.match(text)
    if not m:
        return None
    val = int(m.group(1) if m.group(1) is not None else m.group(2))
    return val if 0 <= val <= 9 else None


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
_EXPLICIT_BYPASS_PHRASES: Tuple[str, ...] = (
    "salta gate",
    "disattiva prompt gate",
)
_ANALYTICAL_INTERROGATIVE_PREFIXES: Tuple[str, ...] = (
    "analizza",
    "verifica",
    "controlla",
    "spiega",
    "perche",
    "perché",
    "dove",
    "come",
    "mostra",
    "cerca",
)
_TECHNICAL_TASK_EXEMPT_BLOCKERS: Set[str] = {
    "log",
    "logs",
    "bug",
    "bugs",
    "errore",
    "errori",
    "file",
    "files",
    "codice",
    "script",
    "scripts",
    "test",
    "tests",
    "analisi",
    "modulo",
    "moduli",
    "controlla",
    "controllare",
    "verifica",
    "verificare",
    "analizza",
    "analizzare",
}
_SHELL_META_EXEMPT_BLOCKERS: Tuple[str, ...] = (
    "|",
    ";",
    "&&",
    ">",
    ">>",
    "`",
    "$(",
)
_COMPOSITE_CONFIRM_BLOCKERS: Set[str] = {
    "ma",
    "pero",
    "però",
    "tranne",
    "eccetto",
    "salvo",
    "prima",
    "poi",
    "inoltre",
    "anche",
    "tuttavia",
    "quindi",
    "mentre",
}
_COMPOSITE_CONFIRM_PHRASES: Tuple[str, ...] = (
    "solo se",
    "a patto",
)
_TASK_ACTION_BLOCKER_RE = re.compile(
    r"\b(?:analiz\w*|valut\w*|sandbox|task|reports?|bugs?|error[ei]|refactor\w*|controll\w*)\b",
    re.IGNORECASE,
)
_VOICE_SELF_CORRECTION_MARKERS: Tuple[str, ...] = (
    "scusa volevo dire",
    "scusami volevo dire",
    "anzi scusa",
    "anzi no",
    "o meglio",
    "volevo dire",
)
_VOICE_CORRECTION_MARKERS: Tuple[str, ...] = (
    *_VOICE_SELF_CORRECTION_MARKERS,
    "anzi",
    "scusa",
    "praticamente",
)
_VOICE_CORRECTION_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = tuple(
    (
        m,
        re.compile(
            rf"(?i)\b{r'[,\s]+'.join(re.escape(part) for part in m.split())}\b"
        ),
    )
    for m in _VOICE_CORRECTION_MARKERS
)
_VOICE_SELF_CORRECTION_SPLIT_RE = re.compile(
    r"\b(?:scusa(?:mi)?[,\s]+volevo\s+dire|anzi[,\s]+scusa|anzi[,\s]+no|o\s+meglio|volevo\s+dire)\b",
    re.IGNORECASE,
)
_STT_INDEPENDENT_ACTION_START_RE = re.compile(
    r"^(?:(?:invece|piuttosto|adesso|ora|semplicemente|soltanto|solo|prima)\s+)?"
    r"(?:analizza|spiega|verifica|controlla|mostra|elenca|cerca|dimmi|illustra|descrivi|"
    r"leggi|esamina|ispeziona|valuta|stampa|riassumi|confronta|trova|fammi|dammi|puoi|potresti|"
    r"come|perch[eé]|dove|quali|quale|cosa|chi|quando|quanti|quanto|non|vietato|evita|senza|"
    r"fermati|stop|annulla|lascia|ignora|esegui|fai|effettua|implementa|crea|modifica|aggiorna|"
    r"scrivi|correggi|aggiungi|sviluppa|progetta|forgia|sincronizza|allinea|cancella|elimina|"
    r"rimuovi|rifai|sistema|risolvi|applica|avvia|lancia|costruisci|genera|migra|sposta|rinomina)\b",
    re.IGNORECASE,
)
_CODE_SPAN_RE = re.compile(r"(`{1,3}[\s\S]*?`{1,3})")
_BP_DIRETTO_RE = re.compile(
    r"(?i)(?:^\s*!diretto(?=\s|$|[.,;!?])|(?:^|\s)!diretto\s*[.,;!?]*$)"
)
_BP_RAW_RE = re.compile(
    r"(?i)(?:^\s*!raw(?=\s|$|[.,;!?])|(?:^|\s)!raw\s*[.,;!?]*$)"
)
_BP_ANY_RE = re.compile(
    r"(?i)(?:^\s*(?:!diretto|!raw)(?=\s|$|[.,;!?])|(?:^|\s)(?:!diretto|!raw)\s*[.,;!?]*$)"
)
_SALTA_GATE_RE = re.compile(
    r"(?i)(?<!\bnon\s)(?<!\bsenza\s)(?<!\bvietato\s)(?<!\bmai\s)(?:^|\s)salta gate(?=\s|$|[.,;!?])"
)
_CAMEL_GLUED_RE = re.compile(r"\b([a-zàèéìòù]{2,})([A-Z][a-zàèéìòù]+)\b")
_PUNCT_NORM_RE = re.compile(r"[,.;:!?\"']+")
_TRIGGER_SEP_RE = re.compile(r"[-_]+")
_MULTI_SPACE_RE = re.compile(r"\s+")
_FIRST_WORD_RE = re.compile(r"[a-zA-Z0-9àèéìòùÀÈÉÌÒÙ_]+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.;\n])\s+")
_EXPLICIT_BYPASS_NEG_RES: Tuple[Tuple[str, re.Pattern[str]], ...] = tuple(
    (
        phrase,
        re.compile(
            rf"\b(?:non|senza|vietato|mai)\s+(?:\w+\s+){{0,3}}{re.escape(phrase)}\b"
        ),
    )
    for phrase in _EXPLICIT_BYPASS_PHRASES
)


def _normalize_trigger_text(text_low: str) -> str:
    """Normalizza punteggiatura e separatori -/_ per il matching trigger onboarding."""
    cleaned = _TRIGGER_SEP_RE.sub(" ", _PUNCT_NORM_RE.sub(" ", text_low))
    return _MULTI_SPACE_RE.sub(" ", cleaned).strip()


def _extract_primary_stt_clause(text: str) -> str:
    """Estrae la clausola primaria successiva ad auto-correzioni STT."""
    if not text:
        return ""
    low = text if text.islower() else text.lower()
    if "anzi" not in low and "meglio" not in low and "volevo" not in low:
        return text
    if not _VOICE_SELF_CORRECTION_SPLIT_RE.search(text):
        return text
    parts = _VOICE_SELF_CORRECTION_SPLIT_RE.split(text)
    if len(parts) < 2:
        return text
    before_part = parts[-2].strip(" ,;:-.!?")
    after_part = parts[-1].strip(" ,;:-")
    if not after_part:
        return text
    sent_parts = _SENT_SPLIT_RE.split(before_part)
    last_clause = sent_parts[-1].strip(" ,;:-.!?") if sent_parts else before_part
    if _STT_INDEPENDENT_ACTION_START_RE.match(after_part) or len(last_clause.split()) <= 8:
        return after_part
    return text

# -*- coding: utf-8 -*-
"""Classificatore ortogonale L0 per IntentTrack Tensor-RSI (DOM-01)."""

from __future__ import annotations

import re
from typing import Dict, Literal

from _internal.vibe_sprint_router.constants_core import (
    _normalize_input_text,
    _sanitize_tetralogia_filenames,
)
from _internal.vibe_sprint_router.write_intent import (
    _analyze_write_intent,
    _has_destructive_shell_command,
)

IntentTrack = Literal["IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC"]
IntentCategory = Literal["CODE_BUILD", "MICRO_VIBE", "SPEC_DOC", "AUDIT_RO"]

_CONTROL_CUES_RE = re.compile(
    r"\b(?:audit\w*|verifica\w*|controlla\w*|controllo|ispeziona\w*|ispezione|analizza\w*|analisi|"
    r"spiega|descrivi|discovery|benchmark|censimento|mappatura|esplora|status|"
    r"stato\s+dell|read[-_\s]?only|readonly|mode\s*d|gt[-_\s]?14|come\s+funziona|"
    r"cosa\s+fa|perch[eé]|quali|quanti)\b",
    re.IGNORECASE,
)
_DOC_SPEC_RE = re.compile(
    r"(?:\b(?:skill\.md|agents\.md|patch_notes|concept_map|structural_tree|"
    r"implementation_plan|repo_map|tetralogia|pentad|ste100|asd-ste100|"
    r"documentazione|docstring|markdown|specifica|manuale|readme|changelog|"
    r"playbook|gemelli)\b|\.md\b)",
    re.IGNORECASE,
)
_OPTIMIZATION_RE = re.compile(
    r"\b(?:ottimizz\w*|optimi[sz]\w*|performance|velocizz\w*|latenza|latency|"
    r"throughput|pareto|refactor\w*|rifattorizz\w*|snellisc\w*|debloat|"
    r"riduc\w*\s+(?:loc|cc|complessit\w*|tempi|costi)|profiling|bottleneck|"
    r"paralleli\w*|token\s+budget|kill\s+rate)\b",
    re.IGNORECASE,
)
_CODE_IMPL_RE = re.compile(
    r"(?:\b(?:python|fastapi|pydantic|asyncio|sqlite|pytest|endpoint|classe|"
    r"funzione|modulo|script|parser|gate|bandit|ticket|mutex|sast|dast)\b|"
    r"\.(?:py|ts|tsx|js|jsx|css)\b)",
    re.IGNORECASE,
)
_IMPROVEMENT_RE = re.compile(
    r"\b(?:implementa\w*|svilupp\w*|crea\w*|aggiung\w*|fix\w*|corregg\w*|"
    r"sistem\w*|miglior\w*|hardening|protegg\w*|integr\w*|forgia\w*|"
    r"scrivi\w*|aggiorn\w*|allinea\w*)\b",
    re.IGNORECASE,
)
_DOC_TARGET_ACTION_RE = re.compile(
    r"\b(?:aggiorn\w*|scriv\w*|allinea\w*|documenta\w*|redig\w*|compil\w*|rivedi|corregg\w*|crea\w*|modifica\w*|miglior\w*)\s+"
    r"(?:la\s+|il\s+|lo\s+|i\s+|gli\s+|le\s+|un\w*\s+)?(?:[a-z]+\s+){0,2}"
    r"(?:documentazione|docstring|markdown|specifica|manuale|readme|changelog|playbook|"
    r"skill\.md|agents\.md|repo_map|patch_notes|ste100|asd-ste100|[^\s,;]+\.md)\b",
    re.IGNORECASE,
)
_CODE_TARGET_ACTION_RE = re.compile(
    r"\b(?:implementa\w*|svilupp\w*|crea\w*|aggiung\w*|fix\w*|corregg\w*|refactor\w*|scriv\w*|aggiorn\w*|modifica\w*)\s+"
    r"(?:la\s+|il\s+|lo\s+|i\s+|un\w*\s+)?(?:[a-z]+\s+){0,2}"
    r"(?:funzione|classe|modulo|script|parser|gate|bandit|endpoint|[^\s,;]+\.(?:py|ts|tsx|js|jsx|css))\b",
    re.IGNORECASE,
)

_TRACK_TO_PROFILE: Dict[str, str] = {
    "IMPROVEMENT": "code_rsi",
    "OPTIMIZATION": "refactor_rsi",
    "DOC_SPEC": "spec_rsi",
    "CONTROL": "code_rsi",
}
_TRACK_TO_CATEGORY: Dict[str, IntentCategory] = {
    "IMPROVEMENT": "CODE_BUILD",
    "OPTIMIZATION": "CODE_BUILD",
    "DOC_SPEC": "SPEC_DOC",
    "CONTROL": "AUDIT_RO",
}


def _classify_write_track(low: str, has_write: bool) -> IntentTrack:
    has_doc = bool(_DOC_SPEC_RE.search(low))
    doc_target_hit = bool(_DOC_TARGET_ACTION_RE.search(low))
    code_target_hit = bool(_CODE_TARGET_ACTION_RE.search(low))
    if (has_doc and not _CODE_IMPL_RE.search(low)) or (doc_target_hit and not code_target_hit):
        return "DOC_SPEC"
    if _OPTIMIZATION_RE.search(low):
        return "OPTIMIZATION"
    if has_doc and not code_target_hit and not _IMPROVEMENT_RE.search(low):
        return "DOC_SPEC"
    if not has_write and "?" in low and not _IMPROVEMENT_RE.search(low):
        return "CONTROL"
    return "IMPROVEMENT"


def classify_intent_track(prompt: str) -> IntentTrack:
    """Classifica ortogonalmente il prompt in IMPROVEMENT, OPTIMIZATION, CONTROL o DOC_SPEC."""
    raw = _normalize_input_text(prompt).strip()
    if not raw:
        return "CONTROL"
    low = raw.lower()
    has_write, has_negated_write = _analyze_write_intent(
        _sanitize_tetralogia_filenames(low)
    )
    has_write = has_write or _has_destructive_shell_command(raw)
    if not has_write and (has_negated_write or _CONTROL_CUES_RE.search(low)):
        return "CONTROL"
    return _classify_write_track(low, has_write)


def resolve_intent_track_profile(track: IntentTrack) -> str:
    """Mappa l'IntentTrack classificato sul profilo RSI canonico corrispondente."""
    return _TRACK_TO_PROFILE.get(track, "code_rsi")


def resolve_intent_category(
    track: IntentTrack, *, is_micro: bool = False
) -> IntentCategory:
    """Risolve la categoria operativa del tensore di politica."""
    if track == "CONTROL":
        return "AUDIT_RO"
    if track == "DOC_SPEC":
        return "SPEC_DOC"
    if is_micro:
        return "MICRO_VIBE"
    return _TRACK_TO_CATEGORY.get(track, "CODE_BUILD")


__all__ = [
    "IntentCategory",
    "IntentTrack",
    "classify_intent_track",
    "resolve_intent_category",
    "resolve_intent_track_profile",
]

"""Helper di matching granulare skill e risoluzione subagent nativi."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from _internal.nk_common.catalog import get_skill_routing_rules
from _internal.vibe_sprint_router.constants_core import (
    DOMAIN_TO_NATIVE_SUBAGENT,
    _AUDIT_FORENSIC_WORD_RE,
    _DOM04_HIGH_PRIORITY_KWS,
    _FORGE_OVERRIDE_KEYWORDS,
    _LARGE_PROMPT_THRESHOLD,
    _NOMINALIZATION_SUFFIXES,
    _RSI_AUDITOR_KEYWORDS,
    _RSI_AUDITOR_SKILLS,
)
from _internal.vibe_sprint_router.write_intent import _has_imperative_write_keyword

SKILL_ROUTING_RULES = get_skill_routing_rules()


def _has_audit_forensic_intent(text_low: str) -> bool:
    """Rileva intento di audit architetturale, forense, incongruenze o controllo TAS senza scritture."""
    if not text_low or not _AUDIT_FORENSIC_WORD_RE.search(text_low):
        return False
    if any(
        ideo_kw in text_low
        for ideo_kw in (
            "copertura bandi",
            "quanti bandi",
            "ricerca competitor",
            "scamper",
            "ste100",
            "asd-ste100",
            "skill.md",
            "skill_golden_eval_set",
        )
    ):
        return False
    return not _has_imperative_write_keyword(text_low)


def _check_word_occurrence(
    kw_low: str,
    text_low: str,
    pos: int,
    min_sub_len: int,
    kw_is_nominal: bool,
) -> Tuple[bool, int]:
    """Verifica i confini lessicali di kw_low alla posizione pos restituendo (matched, word_end)."""
    n = len(text_low)
    klen = len(kw_low)
    ws = pos
    while ws > 0 and (text_low[ws - 1].isalnum() or text_low[ws - 1] == "_"):
        ws -= 1
    we = pos + klen
    while we < n and (text_low[we].isalnum() or text_low[we] == "_"):
        we += 1
    word = text_low[ws:we]
    if word == kw_low:
        return True, we
    if klen >= min_sub_len and "_" not in word and (
        kw_is_nominal or not word.endswith(_NOMINALIZATION_SUFFIXES)
    ):
        return True, we
    return False, we


def _token_matches_keyword(
    kw: str,
    text_low: str,
    tokens: Optional[Set[str]] = None,
    min_sub_len: int = 4,
) -> bool:
    """Verifica il matching tra keyword e testo in C-speed senza scansioni quadratiche su token."""
    kw_low = kw.lower()
    if kw_low not in text_low:
        return False
    if " " in kw_low or "." in kw_low or "/" in kw_low or "-" in kw_low:
        return True
    if not all(c.isalnum() or c == "_" for c in kw_low):
        return bool(tokens and kw_low in tokens)
    if tokens is not None and len(tokens) <= 128 and kw_low in tokens:
        return True

    n = len(text_low)
    kw_is_nominal = kw_low.endswith(_NOMINALIZATION_SUFFIXES)
    start = 0
    checks = 0
    is_large = n > _LARGE_PROMPT_THRESHOLD
    while True:
        pos = text_low.find(kw_low, start)
        if pos == -1:
            return False
        ok, we = _check_word_occurrence(
            kw_low, text_low, pos, min_sub_len, kw_is_nominal
        )
        if ok:
            return True
        start = we if we > pos else pos + 1
        checks += 1
        if is_large and checks >= 32:
            tail_pos = text_low.rfind(kw_low)
            if tail_pos > pos:
                ok_tail, _ = _check_word_occurrence(
                    kw_low, text_low, tail_pos, min_sub_len, kw_is_nominal
                )
                if ok_tail:
                    return True
            return False


_DOMAIN_AFFINITY_CUES: Dict[str, Tuple[str, ...]] = {
    "DOM-01": ("governance", "routing", "bootstrap", "2pc", "commit", "handoff", "session", "swarm"),
    "DOM-02": ("progetta", "specifica", "architettura", "schema", "design", "ui", "ux", "backend", "api", "modello", "ideazione", "openapi"),
    "DOM-03": ("implementa", "sviluppa", "codice", "modifica", "refactoring", "build", "fix", "correggi", "forgia", "crea", "endpoint", "async"),
    "DOM-04": ("audit", "verifica", "controlla", "sicurezza", "sast", "dast", "oracle", "oracolo", "sbfl", "rca", "valuta", "convergenza", "cold review", "delta_k"),
    "DOM-05": ("documentazione", "changelog", "sincronizza", "memoria", "memory", "recall", "scribe", "patch_notes"),
}


def _compute_domain_affinity(dom_id: str, text_low: str) -> int:
    """Calcola l'affinita lessicale di dominio per risolvere pareggi tra skill."""
    cues = _DOMAIN_AFFINITY_CUES.get(dom_id, ())
    affinity = 0
    for cue in cues:
        cue_min = 999 if len(cue) <= 5 else 6
        if _token_matches_keyword(cue, text_low, None, min_sub_len=cue_min):
            affinity += 1
    return affinity


def _is_exact_kw_match(kw: str, text_low: str) -> bool:
    """Verifica se una keyword ha avuto corrispondenza esatta o multi-parola nel testo."""
    kw_low = kw.lower()
    if " " in kw_low or "." in kw_low or "/" in kw_low or "-" in kw_low:
        return True
    return _token_matches_keyword(kw_low, text_low, None, min_sub_len=999)


def _match_granular_skills(text_low: str) -> List[Tuple[str, str, str, str, List[str]]]:
    """Valuta le regole granulari di skill restituendo le corrispondenze ordinate per punteggio."""
    matches: List[Tuple[int, int, int, int, int, int, str, str, str, str, List[str]]] = []

    for idx, (sk_name, dom_id, dom_name, subagent, kws) in enumerate(
        SKILL_ROUTING_RULES
    ):
        hits: List[str] = []
        score = 0
        exact_hits = 0
        multi_hits = 0
        max_kw_len = 0
        for kw in sorted(kws, key=len, reverse=True):
            eff_min_sub = 999 if len(kw) <= 5 else 6
            if _token_matches_keyword(kw, text_low, None, min_sub_len=eff_min_sub):
                kw_low = kw.lower()
                subsumed = any(kw_low in prev.lower() and kw_low != prev.lower() for prev in hits)
                hits.append(kw)
                if subsumed:
                    continue
                if " " in kw_low:
                    multi_hits += 1
                if _is_exact_kw_match(kw_low, text_low):
                    exact_hits += 1
                max_kw_len = max(max_kw_len, len(kw_low))
                if kw in _DOM04_HIGH_PRIORITY_KWS:
                    score += 3
                else:
                    score += 2 if (len(kw) >= 10 or " " in kw) else 1
        if hits:
            dom_affinity = _compute_domain_affinity(dom_id, text_low)
            matches.append(
                (
                    score,
                    multi_hits,
                    exact_hits,
                    dom_affinity,
                    max_kw_len,
                    -idx,
                    sk_name,
                    dom_id,
                    dom_name,
                    subagent,
                    hits,
                )
            )

    matches.sort(reverse=True)
    return [
        (sk_name, dom_id, dom_name, subagent, hits)
        for _, _, _, _, _, _, sk_name, dom_id, dom_name, subagent, hits in matches
    ]


def _resolve_native_subagent(
    domain_id: str,
    matched_skill: Optional[str] = None,
    text: str = "",
) -> str:
    """Risolve il Sub-Agente Nativo instradando query RSI, Architettura ed Orchestrator."""
    text_low = (text or "").strip().lower()
    if matched_skill == "NK-Agent-Instruction-Forge" or any(
        fk in text_low for fk in _FORGE_OVERRIDE_KEYWORDS
    ):
        return "NK-Builder-Agent"
    if matched_skill == "NK-Ideator":
        return "NK-Arch-Specifier"
    if matched_skill == "NK-Orchestrator":
        return "Orchestrator-Direct"
    if matched_skill and matched_skill in _RSI_AUDITOR_SKILLS:
        return "NK-RSI-Auditor"
    if text_low:
        for kw in _RSI_AUDITOR_KEYWORDS:
            if " " in kw:
                if kw in text_low:
                    return "NK-RSI-Auditor"
            elif _token_matches_keyword(kw, text_low, None, min_sub_len=999):
                return "NK-RSI-Auditor"
    return DOMAIN_TO_NATIVE_SUBAGENT.get(domain_id, "NK-Builder-Agent")

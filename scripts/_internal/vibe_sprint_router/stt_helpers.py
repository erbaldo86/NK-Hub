"""Helper deterministici per normalizzazione vocale STT ed esenzioni bypass gate."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from _internal.vibe_sprint_router.constants_core import _BRIEF_HEADER_PHASE_RE, _HANDOFF_MUTATING_ORDER_RE, _TECH_CAMEL_ALLOWLIST
from _internal.vibe_sprint_router.constants_stt import (
    _ANALYTICAL_INTERROGATIVE_PREFIXES, _BP_ANY_RE, _BP_DIRETTO_RE, _BP_RAW_RE, _CAMEL_GLUED_RE, _CODE_SPAN_RE,
    _EXPLICIT_BYPASS_NEG_RES, _FIRST_WORD_RE, _MULTI_SPACE_RE, _NODE_SELECTIONS, _ONBOARDING_TRIGGERS,
    _PUNCT_NORM_RE, _SALTA_GATE_RE, _SENT_SPLIT_RE, _SHELL_META_EXEMPT_BLOCKERS, _STT_INDEPENDENT_ACTION_START_RE,
    _VOICE_CORRECTION_PATTERNS, _VOICE_SELF_CORRECTION_MARKERS, _normalize_trigger_text,
)
from _internal.vibe_sprint_router.prompt_linter import _is_anti_loop_confirmation
from _internal.vibe_sprint_router.write_intent import _has_imperative_write_keyword

_VOICE_TRIGGER_TOKENS: Tuple[str, ...] = ("scusa", "anzi", "meglio", "volevo", "praticamente")
_EXPLICIT_NEG_SELF_CORR_MARKERS: Tuple[str, ...] = ("anzi no", "anzi scusa", "scusa volevo dire", "scusami volevo dire")
_BYPASS_SHELL_METAS: Tuple[str, ...] = (";", "&&", "||", "`", "$(", "|")


def _mask_code_spans(text: str) -> Tuple[str, List[str]]:
    """Maschera gli span inline e fenced code con segnaposto reversibili."""
    if "`" not in text:
        return text, []
    code_spans: List[str] = []

    def _stash_code(match: re.Match[str]) -> str:
        code_spans.append(match.group(0))
        return f"__NK_CODE_{len(code_spans) - 1}__"

    return _CODE_SPAN_RE.sub(_stash_code, text), code_spans


def _starts_with_analytical_word(text_low: str, check_prefix: bool = False) -> bool:
    """Rileva se il testo inizia con una parola interrogativa o analitica."""
    fw_m = _FIRST_WORD_RE.search(text_low[:64])
    return bool(fw_m and fw_m.group(0) in _ANALYTICAL_INTERROGATIVE_PREFIXES) or (
        check_prefix and text_low.startswith(_ANALYTICAL_INTERROGATIVE_PREFIXES)
    )


def _strip_voice_bypass_markers(masked: str) -> Tuple[str, bool]:
    """Estrae e rimuove i marcatori vocali di bypass (!diretto, !raw, salta gate)."""
    bypass_requested = False
    if "!diretto" in masked.lower() and _BP_DIRETTO_RE.search(masked):
        bypass_requested, masked = True, _BP_DIRETTO_RE.sub(" ", masked).strip()
    if "!raw" in masked.lower() and _BP_RAW_RE.search(masked):
        bypass_requested, masked = True, _BP_RAW_RE.sub(" ", masked).strip()
    masked_low = masked.lower()
    if "salta gate" in masked_low and not _starts_with_analytical_word(masked_low) and _SALTA_GATE_RE.search(masked):
        bypass_requested, masked = True, _SALTA_GATE_RE.sub(" ", masked).strip()
    return masked, bypass_requested


def _split_glued_camelcase(masked: str, voice_corrections: List[str], camelcase_splits: List[str]) -> str:
    """Separa i token CamelCase fusi dalla dettatura lasciando intatti i brand tecnici."""
    def _split_camel(match: re.Match[str]) -> str:
        orig = match.group(0)
        if orig.lower() in _TECH_CAMEL_ALLOWLIST:
            return orig
        rep = f"{match.group(1)} {match.group(2)}"
        camelcase_splits.append(f"{orig} -> {rep}")
        voice_corrections.append(f"{orig} -> {rep}")
        return rep

    return _CAMEL_GLUED_RE.sub(_split_camel, masked)


def _resolve_prefix_after_correction(prefix_sents: str, is_explicit_neg: bool, is_indep: bool, after_part: str) -> str:
    """Decide se conservare le frasi prefisso dopo un'auto-correzione vocale."""
    if not prefix_sents:
        return after_part
    if is_explicit_neg and is_indep and not _has_imperative_write_keyword(after_part) and _has_imperative_write_keyword(prefix_sents):
        return after_part
    return f"{prefix_sents} {after_part}".strip()


def _choose_self_corrected_text(marker: str, before_part: str, after_part: str, last_clause: str, prefix_sents: str) -> str:
    """Risolve la porzione testuale effettiva dopo un marcatore di auto-correzione."""
    is_indep = bool(_STT_INDEPENDENT_ACTION_START_RE.match(after_part))
    is_explicit_neg = marker in _EXPLICIT_NEG_SELF_CORR_MARKERS
    if not is_explicit_neg and _has_imperative_write_keyword(last_clause) and not _has_imperative_write_keyword(after_part):
        return f"{before_part} {after_part}".strip()
    if not after_part.split() or not (is_indep or len(last_clause.split()) <= 8):
        return f"{before_part} {after_part}".strip()
    return _resolve_prefix_after_correction(prefix_sents, is_explicit_neg, is_indep, after_part)


def _apply_self_correction_marker(masked: str, marker: str, m_pat: re.Pattern[str], voice_corrections: List[str]) -> str:
    """Applica la regola di split su singolo marcatore di auto-correzione STT."""
    parts = m_pat.split(masked)
    if len(parts) < 2:
        return masked
    before_part, after_part = " ".join(parts[:-1]).strip(" ,;:-"), parts[-1].strip(" ,;:-")
    if not after_part:
        return masked
    sent_parts = _SENT_SPLIT_RE.split(before_part)
    last_clause = sent_parts[-1].strip(" ,;:-.!?") if sent_parts else before_part
    voice_corrections.append(f"{last_clause or marker} -> {after_part}")
    return _choose_self_corrected_text(marker, before_part, after_part, last_clause, " ".join(sent_parts[:-1]).strip())


def _apply_voice_corrections(masked: str, voice_corrections: List[str]) -> str:
    """Rimuove i filler vocali e applica le auto-correzioni STT in sequenza."""
    masked_low = masked.lower()
    if not any(tok in masked_low for tok in _VOICE_TRIGGER_TOKENS):
        return masked
    for marker, m_pat in _VOICE_CORRECTION_PATTERNS:
        if not m_pat.search(masked):
            continue
        if marker in _VOICE_SELF_CORRECTION_MARKERS:
            masked = _apply_self_correction_marker(masked, marker, m_pat, voice_corrections)
        else:
            voice_corrections.append(f"{marker} -> (rimosso filler vocale)")
            masked = m_pat.sub(" ", masked)
    return masked


def _is_safe_env_capsule(text: str, text_low: str) -> bool:
    """Verifica che il blocco <env_capsule> sia singolo e privo di ordini mutanti."""
    is_wrapped = text_low.startswith("<env_capsule>") and text_low.endswith("</env_capsule>")
    return is_wrapped and text_low.count("<env_capsule>") == 1 and text_low.count("</env_capsule>") == 1 and not _HANDOFF_MUTATING_ORDER_RE.search(text)


def _is_unsafe_bypass_prompt(text: str) -> bool:
    """Rileva condizioni di rischio che bloccano i token espliciti di bypass."""
    if len(text) > 1500 or len(_BRIEF_HEADER_PHASE_RE.findall(text)) > 1 or any(meta in text for meta in _BYPASS_SHELL_METAS):
        return True
    return _has_imperative_write_keyword(text) or bool(_HANDOFF_MUTATING_ORDER_RE.search(text))


def _check_explicit_bypass_toggle(text: str, text_low: str) -> Optional[bool]:
    """Valuta i toggle di bypass espliciti (!diretto, !raw, salta gate)."""
    if ("!diretto" in text_low or "!raw" in text_low) and _BP_ANY_RE.search(text_low):
        return not _is_unsafe_bypass_prompt(text)
    if _starts_with_analytical_word(text_low, check_prefix=True):
        return None
    for toggle_marker, neg_re in _EXPLICIT_BYPASS_NEG_RES:
        if toggle_marker in text_low and not neg_re.search(text_low):
            return not _is_unsafe_bypass_prompt(text)
    return None


def _is_exempt_short_trigger(text_low: str) -> bool:
    """Valuta selettori brevi, trigger onboarding e conferme anti-loop."""
    if len(text_low) > 256 or any(meta in text_low for meta in _SHELL_META_EXEMPT_BLOCKERS):
        return False
    norm = _MULTI_SPACE_RE.sub(" ", _PUNCT_NORM_RE.sub(" ", text_low)).strip()
    return norm in _NODE_SELECTIONS or _normalize_trigger_text(text_low) in _ONBOARDING_TRIGGERS or _is_anti_loop_confirmation(text_low)

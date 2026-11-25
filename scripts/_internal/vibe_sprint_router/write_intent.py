"""Funzioni deterministiche per rilevare comandi distruttivi shell e verbi imperativi di scrittura."""

from __future__ import annotations

from typing import List, Set, Tuple

from _internal.vibe_sprint_router.constants_core import (
    _NOMINALIZATION_SUFFIXES,
    _normalize_input_text,
)
from _internal.vibe_sprint_router.write_intent_rules import (
    _ADVERSATIVE_TOKENS,
    _ANALYTICAL_AUDIT_HEADS,
    _COORDINATED_IMPERATIVE_PREFIX_TOKENS,
    _DEONTIC_MODAL_TOKENS,
    _DESTRUCTIVE_SHELL_CMD_RE,
    _DOS_DEL_AFTER_SEP_RE,
    _DOS_DEL_AT_START_RE,
    _EXPLANATORY_CLAUSE_START_RE,
    _FAST_NOUN_DET_SUFFIXES,
    _ITALIAN_NOUN_DETERMINERS,
    _LIGHT_EXEC_VERBS,
    _NEGATION_TOKENS,
    _NEG_TOKEN_RE,
    _SUBORDINATE_WH_TOKENS,
    _WORD_TOKEN_RE,
    _WRITE_IDIOM_PATTERNS,
    _WRITE_ROOT_PATTERNS,
)


def _has_destructive_shell_command(text: str) -> bool:
    """Rileva comandi distruttivi shell evitando collisioni con la preposizione italiana del."""
    if not text:
        return False
    low = text if text.islower() else text.lower()
    if any(
        k in low
        for k in (
            "rm -",
            "remove-item",
            "rmdir ",
            "drop table",
            "drop database",
            "delete from",
        )
    ):
        if _DESTRUCTIVE_SHELL_CMD_RE.search(low):
            return True
    if "del " not in low and "del\t" not in low:
        return False
    stripped = low[:128].lstrip()
    if stripped.startswith(("del ", "del\t")):
        m0 = _DOS_DEL_AT_START_RE.match(stripped)
        if m0:
            seg0 = m0.group(0)
            if not (
                "/" not in seg0
                and "\\" not in seg0
                and low.rstrip().endswith("?")
            ):
                return True
    if any(sep in low for sep in (";", "&", "|", "`", "\n", "cmd")):
        if _DOS_DEL_AFTER_SEP_RE.search(low):
            return True
    return False


def _is_negated_window_12(prev_words: List[str], after_words: List[str]) -> bool:
    """Valuta una finestra di negazione di 12 token spezzando su avversative e virgole."""
    non_adv_prev = [w for w in prev_words if not w.endswith("mente")]
    max_back = min(len(non_adv_prev), 13)
    for dist in range(1, max_back + 1):
        w = non_adv_prev[-dist]
        if w in _ADVERSATIVE_TOKENS or w == ",":
            break
        if w in _NEGATION_TOKENS:
            return True
    non_adv_after = [w for w in after_words if not w.endswith("mente")]
    if non_adv_after and non_adv_after[0] in ("mai", "affatto"):
        return True
    return False


def _clause_bounds_at(text_low: str, pos: int) -> Tuple[int, int]:
    """Trova l'inizio e la fine della clausola locale attorno all'indice pos in O(1)."""
    left_lim = max(0, pos - 380)
    c_start = left_lim
    for sep in (".", ";", "!", "?", "\n"):
        idx = text_low.rfind(sep, left_lim, pos)
        if idx != -1 and idx + 1 > c_start:
            c_start = idx + 1
    right_lim = min(len(text_low), pos + 96)
    c_end = right_lim
    for sep in (".", ";", "!", "?", ",", "\n"):
        idx = text_low.find(sep, pos, right_lim)
        if idx != -1 and idx < c_end:
            c_end = idx
    return c_start, c_end


def _strip_last_n_words(tokens: List[str], count: int) -> List[str]:
    """Rimuove gli ultimi count token non-virgola preservando i separatori precedenti."""
    out = list(tokens)
    removed = 0
    while out and removed < count:
        tok = out.pop()
        if tok != ",":
            removed += 1
    return out


def _analyze_write_intent(clean_text: str) -> Tuple[bool, bool]:
    """Restituisce (has_affirmative_write, has_negated_write) in tempo lineare senza falsi positivi."""
    text_low = _normalize_input_text(clean_text).strip().lower()
    if not text_low:
        return False, False
    if _has_destructive_shell_command(text_low):
        return True, False

    found_negated = False
    if ".staging" in text_low:
        stg_pos = text_low.find(".staging")
        while stg_pos != -1:
            c_start, c_end = _clause_bounds_at(text_low, stg_pos)
            prev_w = _NEG_TOKEN_RE.findall(text_low[c_start:stg_pos])
            after_w = _WORD_TOKEN_RE.findall(
                text_low[stg_pos + len(".staging") : c_end]
            )
            if _is_negated_window_12(prev_w, after_w):
                found_negated = True
            else:
                return True, found_negated
            stg_pos = text_low.find(".staging", stg_pos + 8)

    active_pats = [
        (pat, False) for root, pat in _WRITE_ROOT_PATTERNS if root in text_low
    ] + [
        (pat, True) for marker, pat in _WRITE_IDIOM_PATTERNS if marker in text_low
    ]
    if not active_pats:
        return False, found_negated

    has_light_exec = any(lv in text_low for lv in _LIGHT_EXEC_VERBS)
    seen_ctx: Set[Tuple[str, str]] = set()

    for pat, is_idiom in active_pats:
        for m in pat.finditer(text_low):
            tok = m.group(0)
            if not is_idiom and (
                tok.endswith(_NOMINALIZATION_SUFFIXES) or tok in ("integrale", "integrali")
            ):
                continue
            m_start = m.start()
            if not is_idiom and not has_light_exec and m_start >= 4:
                near_pre = text_low[max(0, m_start - 10) : m_start]
                if near_pre.endswith(_FAST_NOUN_DET_SUFFIXES):
                    continue
            c_start, c_end = _clause_bounds_at(text_low, m_start)
            ctx_prefix = text_low[c_start:m_start]
            ctx_key = (ctx_prefix, tok)
            if ctx_key in seen_ctx:
                continue
            seen_ctx.add(ctx_key)

            prev_neg = _NEG_TOKEN_RE.findall(ctx_prefix)
            prev_words = [w for w in prev_neg if w != ","]
            after_words = _WORD_TOKEN_RE.findall(text_low[m.end() : c_end])

            if _is_negated_window_12(prev_neg, after_words):
                found_negated = True
                continue

            if (
                not is_idiom
                and tok.startswith("refactor")
                and prev_words
                and any(w in _ANALYTICAL_AUDIT_HEADS for w in prev_words)
                and prev_words[-1] not in _COORDINATED_IMPERATIVE_PREFIX_TOKENS
            ):
                continue

            if not is_idiom and prev_words and prev_words[-1] in _ITALIAN_NOUN_DETERMINERS:
                if len(prev_words) >= 2 and prev_words[-2] in _LIGHT_EXEC_VERBS:
                    if _is_negated_window_12(_strip_last_n_words(prev_neg, 2), after_words):
                        found_negated = True
                        continue
                    return True, found_negated
                continue

            if prev_words and prev_words[-1] in _SUBORDINATE_WH_TOKENS:
                continue

            head_word = tok.split(None, 1)[0] if is_idiom else ""
            has_deontic = (
                head_word in _DEONTIC_MODAL_TOKENS
                or any(w in _DEONTIC_MODAL_TOKENS for w in prev_words[-3:])
            )
            clause_head = text_low[c_start : min(len(text_low), c_start + 96)].lstrip(
                " ,;:-"
            )
            if (
                prev_words
                and _EXPLANATORY_CLAUSE_START_RE.match(clause_head)
                and prev_words[-1] not in _COORDINATED_IMPERATIVE_PREFIX_TOKENS
                and not has_deontic
            ):
                continue

            return True, found_negated

    return False, found_negated


def _has_imperative_write_keyword(clean_text: str) -> bool:
    """Verifica verbi imperativi di scrittura escludendo nominalizzazioni e negazioni."""
    has_write, _ = _analyze_write_intent(clean_text)
    return has_write

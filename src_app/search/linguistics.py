"""LabNK Linguistics & Morphological Matching Engine.
Nexus Keystone v1.1.0-Universal | Zero-Mock Engine.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

BILINGUAL_LEMMAS: Dict[str, List[str]] = {
    "ai": ["intelligenza artificiale", "artificial intelligence", "ia", "machine learning"],
    "deep tech": ["deeptech", "tecnologie di frontiera"],
    "photovoltaic": ["fotovoltaico", "solare", "solar"],
    "hydrogen": ["idrogeno", "h2"],
    "biotech": ["biotecnologie", "biotecnologia", "biotechnology"],
}

SHORT_RELEVANT_TOKENS: Set[str] = {"ai", "ue", "ia", "h2", "eu"}


def strip_accents(text: str) -> str:
    """Rimuove accenti e diacritici per comparazioni resilienti."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


@lru_cache(maxsize=4096)
def _get_text_tokens_and_stems(text: str) -> Tuple[str, frozenset, frozenset]:
    """Estrae e memorizza in cache il testo pulito, le parole e gli stem morfologici per O(1) matching."""
    text_clean = strip_accents(text.lower())
    words = frozenset(re.findall(r"\b\w+\b", text_clean))
    stems = frozenset(w[:-1] for w in words if len(w) >= 5)
    return text_clean, words, stems


def match_token_fast(t_clean: str, text_clean: str, words: frozenset, stems: frozenset) -> bool:
    """Valutazione morfologica O(1) con set pre-calcolati di parole e radici."""
    if not t_clean:
        return True
    if t_clean in text_clean:
        return True
    if len(t_clean) >= 5:
        stem = t_clean[:-1]
        if stem in text_clean or stem in stems:
            return True
        if (
            t_clean.endswith("ico")
            or t_clean.endswith("ica")
            or t_clean.endswith("ici")
            or t_clean.endswith("iche")
        ) and len(t_clean) >= 6:
            ic_stem = t_clean[:-3] + "ic"
            if ic_stem in text_clean:
                return True
            if any(w.startswith(ic_stem) for w in words):
                return True
    return False


def match_token(tok: str, text: str, word_set: Optional[Any] = None) -> bool:
    """Helper di matching morfologico flesso per italiano e inglese (singolari/plurali e accenti)."""
    t_clean = strip_accents(tok.lower().strip())
    if not t_clean:
        return True

    if word_set is not None:
        text_clean = strip_accents(text.lower())
        if t_clean in text_clean:
            return True
        if len(t_clean) >= 5:
            stem = t_clean[:-1]
            if stem in text_clean:
                return True
            if (
                t_clean.endswith("ico")
                or t_clean.endswith("ica")
                or t_clean.endswith("ici")
                or t_clean.endswith("iche")
            ) and len(t_clean) >= 6:
                if t_clean[:-3] + "ic" in text_clean:
                    return True
            for w in word_set:
                if len(w) >= 5 and w[:-1] == stem:
                    return True
        return False

    text_clean, words, stems = _get_text_tokens_and_stems(text)
    return match_token_fast(t_clean, text_clean, words, stems)

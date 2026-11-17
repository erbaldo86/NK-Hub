# -*- coding: utf-8 -*-
"""Ricerca lessicale BM25, Signed Feature Hashing SHA-256 e fusione RRF."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Dict, List, Sequence, Tuple

from _internal.memory_3tier_engine.models import MemoryEpisode, RRF_K_CONSTANT

_LEXICAL_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "con",
        "per",
        "che",
        "del",
        "una",
        "uno",
        "gli",
        "dei",
        "nel",
        "sul",
    }
)

_POLARITY_AFFIRMATIVE_TOKENS: frozenset[str] = frozenset(
    {"sempre", "always", "must", "obbligatorio", "obbligatoria", "mandatory"}
)

_POLARITY_NEGATIVE_TOKENS: frozenset[str] = frozenset(
    {"mai", "never", "non", "not", "vietato", "vietata", "forbid", "forbidden"}
)


class PureBM25:
    """Motore di rilevanza lessicale BM25 scritto in puro Python."""

    def __init__(
        self,
        corpus: Sequence[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lengths: List[int] = []
        self.doc_token_counts: List[Dict[str, int]] = []
        self.df: Dict[str, int] = {}

        total_length = 0
        for doc in corpus:
            tokens = self._tokenize(doc)
            length = len(tokens)
            self.doc_lengths.append(length)
            total_length += length

            counts: Dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1
            self.doc_token_counts.append(counts)

            for t in counts:
                self.df[t] = self.df.get(t, 0) + 1

        self.avg_doc_len = (
            (total_length / self.corpus_size) if self.corpus_size > 0 else 1.0
        )

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())

    def score(self, query: str) -> List[float]:
        """Calcola i punteggi BM25 per la query specificata."""
        q_tokens = self._tokenize(query)
        scores = [0.0] * self.corpus_size

        for term in q_tokens:
            if term not in self.df:
                continue
            df_t = self.df[term]
            idf = math.log(1.0 + (self.corpus_size - df_t + 0.5) / (df_t + 0.5))

            for i, counts in enumerate(self.doc_token_counts):
                tf = counts.get(term, 0)
                if tf > 0:
                    doc_len = self.doc_lengths[i]
                    num = tf * (self.k1 + 1.0)
                    denom = tf + self.k1 * (
                        1.0 - self.b + self.b * (doc_len / self.avg_doc_len)
                    )
                    scores[i] += idf * (num / denom)

        return scores


def _light_stem_token(token: str) -> str:
    """Riduce un token alla radice morfologica preservando almeno 3 caratteri."""
    for suffix in (
        "zioni",
        "zione",
        "menti",
        "mento",
        "ando",
        "endo",
        "ing",
        "ed",
        "es",
        "s",
    ):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _extract_significant_terms(text: str) -> set[str]:
    """Estrae token e stem significativi di lunghezza almeno pari a 3 caratteri."""
    raw_tokens = re.findall(r"\b[a-zA-Z0-9_]{3,}\b", (text or "").lower())
    if not raw_tokens:
        return set()
    filtered = [t for t in raw_tokens if t not in _LEXICAL_STOPWORDS] or raw_tokens
    terms: set[str] = set()
    for tok in filtered:
        terms.add(tok)
        stemmed = _light_stem_token(tok)
        if len(stemmed) >= 3:
            terms.add(stemmed)
        if len(tok) >= 5:
            terms.add(tok[:5])
    return terms


def _has_significant_overlap(query: str, doc_text: str) -> bool:
    """Verifica la presenza di almeno un token o stem significativo condiviso."""
    q_terms = _extract_significant_terms(query)
    if q_terms:
        return bool(q_terms & _extract_significant_terms(doc_text))
    q_short = set(re.findall(r"\b[a-zA-Z0-9_]{2,}\b", (query or "").lower()))
    if not q_short:
        return False
    d_short = set(re.findall(r"\b[a-zA-Z0-9_]{2,}\b", (doc_text or "").lower()))
    return bool(q_short & d_short)


def _has_opposite_polarity(text_a: str, text_b: str) -> bool:
    """Rileva polarita opposta tra regole affermative e negazioni."""
    toks_a = set(re.findall(r"\b[a-zA-Z0-9_]+\b", (text_a or "").lower()))
    toks_b = set(re.findall(r"\b[a-zA-Z0-9_]+\b", (text_b or "").lower()))
    neg_a = bool(toks_a & _POLARITY_NEGATIVE_TOKENS)
    neg_b = bool(toks_b & _POLARITY_NEGATIVE_TOKENS)
    if neg_a != neg_b:
        return True
    aff_a = bool(toks_a & _POLARITY_AFFIRMATIVE_TOKENS) and not neg_a
    aff_b = bool(toks_b & _POLARITY_AFFIRMATIVE_TOKENS) and not neg_b
    return (aff_a and neg_b) or (aff_b and neg_a)


class DenseEmbedder:
    """Generatore deterministico di vettori densi con Signed Feature Hashing SHA-256."""

    @staticmethod
    def vector_from_text(text: str, dim: int = 64) -> List[float]:
        """Converte il testo in un vettore L2 su tutte le dimensioni indipendenti."""
        if dim <= 0:
            return []
        vec = [0.0] * dim
        tokens = re.findall(r"\b[a-zA-Z0-9_]+\b", (text or "").lower())
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx1 = int.from_bytes(digest[0:8], "big") % dim
            sign1 = 1.0 if (digest[8] & 0x01) else -1.0
            vec[idx1] += sign1
            idx2 = int.from_bytes(digest[9:17], "big") % dim
            sign2 = 1.0 if (digest[17] & 0x01) else -1.0
            vec[idx2] += sign2
            stem = _light_stem_token(token)
            stem_key = stem if len(stem) >= 3 else (token[:5] if len(token) >= 5 else "")
            if stem_key and stem_key != token:
                s_dig = hashlib.sha256(f"st:{stem_key}".encode("utf-8")).digest()
                s_idx = int.from_bytes(s_dig[0:8], "big") % dim
                s_sign = 1.0 if (s_dig[8] & 0x01) else -1.0
                vec[s_idx] += 0.5 * s_sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            fb_dig = hashlib.sha256(tokens[0].encode("utf-8")).digest()
            vec[int.from_bytes(fb_dig[0:8], "big") % dim] = 1.0
            return vec
        return [x / norm for x in vec]

    @staticmethod
    def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
        """Calcola la similarita del coseno tra due vettori numerici."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return max(-1.0, min(1.0, dot / (norm1 * norm2)))


class HybridRRFSearchEngine:
    """Motore di ricerca ibrido con Reciprocal Rank Fusion."""

    def __init__(self, k_rrf: float = RRF_K_CONSTANT) -> None:
        self.k_rrf = k_rrf

    def search(
        self,
        query: str,
        episodes: Sequence[MemoryEpisode],
        top_k: int = 5,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
    ) -> List[Tuple[MemoryEpisode, float]]:
        """Combina il ranking BM25 e vettoriale tramite la formula RRF."""
        if not episodes or not query or not query.strip():
            return []

        corpus = [f"{e.title} {e.content} {' '.join(e.tags)}" for e in episodes]
        bm25 = PureBM25(corpus)
        bm25_scores = bm25.score(query)

        query_vec = DenseEmbedder.vector_from_text(query)
        dense_scores: List[float] = []
        for idx, e in enumerate(episodes):
            if not _has_significant_overlap(query, corpus[idx]):
                bm25_scores[idx] = 0.0
                dense_scores.append(0.0)
                continue
            vec = e.vector or DenseEmbedder.vector_from_text(f"{e.title} {e.content}")
            cos_val = DenseEmbedder.cosine_similarity(query_vec, vec)
            dense_scores.append(max(0.0, cos_val))

        bm25_ranked = sorted(
            range(len(episodes)),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )
        bm25_rank_map = {idx: rank + 1 for rank, idx in enumerate(bm25_ranked)}
        dense_ranked = sorted(
            range(len(episodes)),
            key=lambda i: dense_scores[i],
            reverse=True,
        )
        dense_rank_map = {idx: rank + 1 for rank, idx in enumerate(dense_ranked)}

        rrf_scores: List[Tuple[MemoryEpisode, float]] = []
        for idx, ep in enumerate(episodes):
            if bm25_scores[idx] <= 0.0 and dense_scores[idx] <= 0.0:
                continue
            r_bm25 = bm25_rank_map[idx]
            r_vec = dense_rank_map[idx]
            score_rrf = (bm25_weight / (self.k_rrf + r_bm25)) + (
                vector_weight / (self.k_rrf + r_vec)
            )
            rrf_scores.append((ep, score_rrf))

        rrf_scores.sort(key=lambda item: item[1], reverse=True)
        return rrf_scores[:top_k]

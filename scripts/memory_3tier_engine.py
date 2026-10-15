# -*- coding: utf-8 -*-
"""
Motore di memoria episodica a 3 livelli per Nexus Keystone v3.0.0-STE100-Unified.
Supporta cap 350 token standard (GT-05), 1200 token Argon e alias di dominio.
"""

from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
for _p in (_scripts_dir, _workspace_root / "scripts", _workspace_root):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from win32_2pc_engine import win32_atomic_replace as _win32_2pc_atomic_replace
except ImportError:
    try:
        from scripts.win32_2pc_engine import win32_atomic_replace as _win32_2pc_atomic_replace
    except ImportError:
        _win32_2pc_atomic_replace = None  # type: ignore[assignment]


NK_DOMAINS: Tuple[str, ...] = (
    "01_Bug_Diagnostics",
    "02_Development_Patterns",
    "03_Ideation_and_Decisions",
    "04_Governance_and_Rules",
)

DOMAIN_ALIAS_MAP: Dict[str, str] = {
    "OPS": "01_Bug_Diagnostics",
    "ARCH": "02_Development_Patterns",
    "DEVX": "03_Ideation_and_Decisions",
    "SEC": "04_Governance_and_Rules",
    "01_Bug_Diagnostics": "01_Bug_Diagnostics",
    "02_Development_Patterns": "02_Development_Patterns",
    "03_Ideation_and_Decisions": "03_Ideation_and_Decisions",
    "04_Governance_and_Rules": "04_Governance_and_Rules",
}

TIER1_TOKEN_CAP: int = 350
TIER1_TOKEN_CAP_ARGON: int = 1200
TIER2_SLIDING_WINDOW_MAX: int = 200
RRF_K_CONSTANT: float = 60.0
BACKUP_DEPTH: int = 2

MOVEFILE_REPLACE_EXISTING = 0x00000001
MOVEFILE_WRITE_THROUGH = 0x00000008
MOVEFILE_COPY_ALLOWED = 0x00000002

ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33

if os.name == "nt":
    _kernel32 = ctypes.windll.kernel32
    _kernel32.MoveFileExW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    _kernel32.MoveFileExW.restype = ctypes.c_bool
    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32
else:
    _kernel32 = None


def resolve_domain(domain: str) -> str:
    """Risolve un alias breve o un nome completo nel dominio canonico NK."""
    cleaned = domain.strip()
    if cleaned in DOMAIN_ALIAS_MAP:
        return DOMAIN_ALIAS_MAP[cleaned]
    upper_key = cleaned.upper()
    if upper_key in DOMAIN_ALIAS_MAP:
        return DOMAIN_ALIAS_MAP[upper_key]
    raise ValueError(f"Invalid or unknown domain: {domain}")


def win32_atomic_replace(
    src_path: Path,
    dst_path: Path,
    max_retries: int = 8,
) -> None:
    """Sostituisce un file in modo atomico usando win32_2pc_engine o fallback locale."""
    if _win32_2pc_atomic_replace is not None:
        _win32_2pc_atomic_replace(src_path, dst_path, max_retries=max_retries)
        return
    src_str = str(src_path.resolve())
    dst_str = str(dst_path.resolve())

    if os.name == "nt" and _kernel32 is not None:
        flags = (
            MOVEFILE_REPLACE_EXISTING
            | MOVEFILE_WRITE_THROUGH
            | MOVEFILE_COPY_ALLOWED
        )

        for attempt in range(max_retries):
            success = _kernel32.MoveFileExW(src_str, dst_str, flags)
            if success:
                return

            err = _kernel32.GetLastError()
            if err in (
                ERROR_SHARING_VIOLATION,
                ERROR_ACCESS_DENIED,
                ERROR_LOCK_VIOLATION,
            ):
                delay = random.uniform(
                    0.010,
                    min(0.080 * (1.6 ** attempt), 1.500),
                )
                time.sleep(delay)
            else:
                try:
                    os.replace(src_str, dst_str)
                    return
                except (PermissionError, OSError):
                    delay = random.uniform(
                        0.010,
                        min(0.080 * (1.6 ** attempt), 1.500),
                    )
                    time.sleep(delay)

        shadow_tmp = (
            dst_path.parent
            / f".shadow_{dst_path.name}_{os.getpid()}_{int(time.time()*1000)}.tmp"
        )
        old_tmp = (
            dst_path.parent
            / f".old_{dst_path.name}_{os.getpid()}_{int(time.time()*1000)}.tmp"
        )

        for _ in range(max_retries):
            try:
                shutil.copy2(src_path, shadow_tmp)
                if dst_path.exists():
                    try:
                        os.replace(dst_str, str(old_tmp))
                    except OSError:
                        pass
                os.replace(str(shadow_tmp), dst_str)
                if old_tmp.exists():
                    try:
                        old_tmp.unlink()
                    except OSError:
                        pass
                try:
                    src_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return
            except Exception:
                delay = random.uniform(0.010, 0.080)
                time.sleep(delay)

    os.replace(src_str, dst_str)


def rotate_circular_backups(target_file: Path, depth: int = BACKUP_DEPTH) -> None:
    """Ruota i file di backup circolari (.bak_1, .bak_2) con copia streaming."""
    if not target_file.exists():
        return

    for i in range(depth, 1, -1):
        prev_bak = target_file.with_name(f"{target_file.name}.bak_{i - 1}")
        curr_bak = target_file.with_name(f"{target_file.name}.bak_{i}")
        if prev_bak.exists():
            if curr_bak.exists():
                curr_bak.unlink()
            prev_bak.rename(curr_bak)

    first_bak = target_file.with_name(f"{target_file.name}.bak_1")
    if first_bak.exists():
        first_bak.unlink()

    shutil.copy2(target_file, first_bak)


class MemoryEpisode(BaseModel):
    """Singolo episodio archiviato nel motore di memoria a 3 livelli."""

    model_config = ConfigDict(strict=True, extra="forbid")

    episode_id: str = Field(description="Identificatore univoco dell'episodio")
    domain: str = Field(description="Uno dei 4 domini NK o alias breve")
    timestamp: float = Field(default_factory=time.time)
    title: str = Field(description="Titolo sintetico dell'episodio")
    content: str = Field(description="Contenuto completo dell'episodio")
    tags: List[str] = Field(default_factory=list)
    vector: Optional[List[float]] = Field(default=None)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("domain")
    @classmethod
    def _validate_and_normalize_domain(cls, v: str) -> str:
        return resolve_domain(v)


class Tier1Item(BaseModel):
    """Voce singola nella memoria in-context di Livello 1."""

    model_config = ConfigDict(strict=True, extra="forbid")

    key: str
    value: str
    priority: int = Field(default=1, ge=1, le=10)
    estimated_tokens: int = Field(default=0)


class Tier1DomainState(BaseModel):
    """Stato della memoria di Livello 1 per un singolo dominio."""

    model_config = ConfigDict(strict=True, extra="forbid")

    domain: str
    items: Dict[str, Tier1Item] = Field(default_factory=dict)
    total_tokens: int = Field(default=0)


def estimate_tokens(text: str) -> int:
    """Stima rapida dei token lessicali per una stringa di testo."""
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, math.ceil(len(words) * 1.15))


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


class DenseEmbedder:
    """Generatore deterministico di vettori densi basato su hash."""

    @staticmethod
    def vector_from_text(text: str, dim: int = 64) -> List[float]:
        """Converte il testo in un vettore normalizzato a dimensione fissa."""
        vec = [0.0] * dim
        tokens = re.findall(r"\b[a-zA-Z0-9_]+\b", text.lower())
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            for d in range(dim):
                weight = ((h >> (d % 32)) & 0x01) * 2 - 1
                vec[d] += weight
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        return vec

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
    """Motore di ricerca ibrido con Reciprocal Rank Fusion (k=60)."""

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
        if not episodes:
            return []

        corpus = [f"{e.title} {e.content} {' '.join(e.tags)}" for e in episodes]
        bm25 = PureBM25(corpus)
        bm25_scores = bm25.score(query)
        bm25_ranked = sorted(
            range(len(episodes)),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )
        bm25_rank_map = {idx: rank + 1 for rank, idx in enumerate(bm25_ranked)}

        query_vec = DenseEmbedder.vector_from_text(query)
        dense_scores = []
        for e in episodes:
            vec = e.vector or DenseEmbedder.vector_from_text(f"{e.title} {e.content}")
            dense_scores.append(DenseEmbedder.cosine_similarity(query_vec, vec))
        dense_ranked = sorted(
            range(len(episodes)),
            key=lambda i: dense_scores[i],
            reverse=True,
        )
        dense_rank_map = {idx: rank + 1 for rank, idx in enumerate(dense_ranked)}

        rrf_scores: List[Tuple[MemoryEpisode, float]] = []
        for idx, ep in enumerate(episodes):
            r_bm25 = bm25_rank_map[idx]
            r_vec = dense_rank_map[idx]
            score_rrf = (bm25_weight / (self.k_rrf + r_bm25)) + (
                vector_weight / (self.k_rrf + r_vec)
            )
            rrf_scores.append((ep, score_rrf))

        rrf_scores.sort(key=lambda item: item[1], reverse=True)
        return rrf_scores[:top_k]


class Tier1CoreMemory:
    """Gestisce la memoria core di Livello 1 con budget massimo di token."""

    def __init__(
        self,
        token_cap: int = TIER1_TOKEN_CAP,
        profile: Optional[str] = None,
    ) -> None:
        if profile == "argon" and token_cap == TIER1_TOKEN_CAP:
            self.token_cap = TIER1_TOKEN_CAP_ARGON
        else:
            self.token_cap = token_cap
        self._domains: Dict[str, Tier1DomainState] = {
            d: Tier1DomainState(domain=d) for d in NK_DOMAINS
        }

    def set_item(
        self,
        domain: str,
        key: str,
        value: str,
        priority: int = 1,
    ) -> None:
        """Inserisce o aggiorna una voce nel dominio e applica il budget token."""
        canon = resolve_domain(domain)
        d_state = self._domains[canon]
        tok = estimate_tokens(f"{key}: {value}")
        d_state.items[key] = Tier1Item(
            key=key,
            value=value,
            priority=priority,
            estimated_tokens=tok,
        )
        self._enforce_budget(canon)

    def get_item(self, domain: str, key: str) -> Optional[str]:
        """Recupera il valore di una chiave nel dominio specificato."""
        try:
            canon = resolve_domain(domain)
        except ValueError:
            return None
        if canon in self._domains and key in self._domains[canon].items:
            return self._domains[canon].items[key].value
        return None

    def get_token_usage(self, domain: str) -> int:
        """Restituisce il totale dei token usati nel dominio."""
        try:
            canon = resolve_domain(domain)
        except ValueError:
            return 0
        return self._domains[canon].total_tokens if canon in self._domains else 0

    def get_context_string(self, domain: str) -> str:
        """Formatta le voci del dominio ordinate per priorita decrescente."""
        try:
            canon = resolve_domain(domain)
        except ValueError:
            return ""
        items = sorted(
            self._domains[canon].items.values(),
            key=lambda x: x.priority,
            reverse=True,
        )
        return "\n".join(f"[{i.key}] {i.value}" for i in items)

    def _enforce_budget(self, domain: str) -> None:
        d_state = self._domains[domain]
        items = list(d_state.items.values())
        items.sort(key=lambda x: (x.priority, -x.estimated_tokens))

        current_tokens = sum(x.estimated_tokens for x in items)
        while current_tokens > self.token_cap and items:
            evicted = items.pop(0)
            del d_state.items[evicted.key]
            current_tokens -= evicted.estimated_tokens

        d_state.total_tokens = sum(
            x.estimated_tokens for x in d_state.items.values()
        )


class ThreeTierMemoryEngine:
    """Orchestra i 3 livelli di memoria episodica con cache locale veloce."""

    def __init__(
        self,
        base_dir: Path | str,
        token_cap: int = TIER1_TOKEN_CAP,
        sliding_window_max: int = TIER2_SLIDING_WINDOW_MAX,
        cache_dir: Optional[Path | str] = None,
        profile: Optional[str] = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir
            else (Path(tempfile.gettempdir()) / "nk_mem_cache")
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sliding_window_max = sliding_window_max

        self.tier1 = Tier1CoreMemory(token_cap=token_cap, profile=profile)
        self.search_engine = HybridRRFSearchEngine()
        self._init_storage()

    def _init_storage(self) -> None:
        for domain in NK_DOMAINS:
            d_dir = self.base_dir / domain
            d_dir.mkdir(parents=True, exist_ok=True)
            t2_file = d_dir / "episodes.jsonl"
            if not t2_file.exists():
                t2_file.touch()

    def append_episode(self, episode: MemoryEpisode) -> None:
        """Aggiunge un episodio al Livello 2 e compatta le eccedenze nel Livello 3."""
        canon = resolve_domain(episode.domain)
        d_dir = self.base_dir / canon
        t2_file = d_dir / "episodes.jsonl"

        episodes = self._load_tier2_raw(t2_file)
        episodes.append(episode)

        if len(episodes) > self.sliding_window_max:
            surplus_count = len(episodes) - self.sliding_window_max
            to_archive = episodes[:surplus_count]
            episodes = episodes[surplus_count:]
            self._archive_to_tier3(canon, to_archive)

        rotate_circular_backups(t2_file)
        tmp_file = d_dir / f"episodes_{uuid.uuid4().hex[:8]}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            for ep in episodes:
                f.write(ep.model_dump_json() + "\n")

        win32_atomic_replace(tmp_file, t2_file)
        self._update_shadow_cache(canon, episodes)
        self.tier1.set_item(
            domain=canon,
            key=episode.episode_id,
            value=f"{episode.title}: {episode.content}",
            priority=5,
        )

    def get_tier2_episodes(self, domain: str) -> List[MemoryEpisode]:
        """Legge gli episodi attivi del Livello 2 sfruttando la cache locale."""
        canon = resolve_domain(domain)
        cached = self._read_shadow_cache(canon)
        if cached is not None:
            return cached

        t2_file = self.base_dir / canon / "episodes.jsonl"
        episodes = self._load_tier2_raw(t2_file)
        self._update_shadow_cache(canon, episodes)
        return episodes

    def get_tier3_episodes(self, domain: str) -> List[MemoryEpisode]:
        """Legge gli episodi storici compressi nel Livello 3."""
        canon = resolve_domain(domain)
        cold_file = self.base_dir / canon / "archive.cold.jsonl.gz"
        if not cold_file.exists():
            return []

        episodes: List[MemoryEpisode] = []
        try:
            with gzip.open(cold_file, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        episodes.append(MemoryEpisode.model_validate_json(line))
        except Exception:
            pass
        return episodes

    def recall_hybrid(
        self,
        domain: str,
        query: str,
        top_k: int = 5,
        adaptive: bool = True,
    ) -> List[Tuple[MemoryEpisode, float]]:
        """Esegue una ricerca ibrida RRF adattiva combinando Livello 2 e Livello 3."""
        canon = resolve_domain(domain)
        t2_eps = self.get_tier2_episodes(canon)
        t3_eps = self.get_tier3_episodes(canon)
        all_eps = t2_eps + t3_eps
        results = self.search_engine.search(query, all_eps, top_k=top_k)

        if not adaptive or not all_eps or not query.strip():
            return results

        q_tokens = set(re.findall(r"\b[a-zA-Z0-9_]{2,}\b", query.lower()))
        if not q_tokens:
            return results

        top_text = (
            f"{results[0][0].title} {results[0][0].content} {' '.join(results[0][0].tags)}".lower()
            if results
            else ""
        )
        matched = sum(1 for t in q_tokens if t in top_text)
        coverage = float(matched) / float(len(q_tokens))

        if coverage < 0.5:
            tag_pool: List[str] = []
            for ep in all_eps[-20:]:
                tag_pool.extend(ep.tags)
            expanded_query = f"{query} {' '.join(dict.fromkeys(tag_pool))}".strip()
            results = self.search_engine.search(
                expanded_query,
                all_eps,
                top_k=top_k,
                vector_weight=0.65,
                bm25_weight=0.35,
            )

        return results

    def sync_tier1_capsule(
        self,
        output_path: Optional[Path | str] = None,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sincronizza e persiste su disco il file tier1_active_capsule.json."""
        if profile == "argon" and self.tier1.token_cap == TIER1_TOKEN_CAP:
            self.tier1.token_cap = TIER1_TOKEN_CAP_ARGON

        for dom in NK_DOMAINS:
            if not self.tier1._domains[dom].items:
                recent_eps = self.get_tier2_episodes(dom)[-5:]
                for idx, ep in enumerate(recent_eps, start=1):
                    self.tier1.set_item(
                        domain=dom,
                        key=ep.episode_id,
                        value=f"{ep.title}: {ep.content}",
                        priority=min(10, idx + 2),
                    )

        active_profile = profile or (
            "argon" if self.tier1.token_cap == TIER1_TOKEN_CAP_ARGON else "standard"
        )
        domains_payload: Dict[str, Any] = {}
        lessons_list: List[Dict[str, Any]] = []

        for dom in NK_DOMAINS:
            d_state = self.tier1._domains[dom]
            items_dumped = [it.model_dump() for it in d_state.items.values()]
            domains_payload[dom] = {
                "total_tokens": d_state.total_tokens,
                "context": self.tier1.get_context_string(dom),
                "items": items_dumped,
            }
            for it in d_state.items.values():
                lessons_list.append(
                    {
                        "domain": dom,
                        "key": it.key,
                        "lesson": f"[{it.key}] {it.value}",
                        "priority": it.priority,
                        "estimated_tokens": it.estimated_tokens,
                    }
                )

        capsule_data: Dict[str, Any] = {
            "schema_version": "3.1.0-Tensor-RSI",
            "updated_at": time.time(),
            "profile": active_profile,
            "token_cap": self.tier1.token_cap,
            "domains": domains_payload,
            "lessons": lessons_list,
        }

        target_file = (
            Path(output_path).resolve()
            if output_path
            else (self.base_dir / "tier1_active_capsule.json").resolve()
        )
        target_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_capsule = target_file.parent / f"tier1_capsule_{uuid.uuid4().hex[:8]}.tmp"
        tmp_capsule.write_text(
            json.dumps(capsule_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        win32_atomic_replace(tmp_capsule, target_file)
        return capsule_data

    def _archive_to_tier3(
        self,
        domain: str,
        surplus: Sequence[MemoryEpisode],
    ) -> None:
        cold_file = self.base_dir / domain / "archive.cold.jsonl.gz"
        existing = self.get_tier3_episodes(domain)
        combined = existing + list(surplus)

        tmp_cold = self.base_dir / domain / f"cold_{uuid.uuid4().hex[:8]}.tmp.gz"
        with gzip.open(tmp_cold, "wt", encoding="utf-8") as f:
            for ep in combined:
                f.write(ep.model_dump_json() + "\n")

        win32_atomic_replace(tmp_cold, cold_file)

    def _load_tier2_raw(self, path: Path) -> List[MemoryEpisode]:
        if not path.exists():
            return []
        episodes: List[MemoryEpisode] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    episodes.append(MemoryEpisode.model_validate_json(line))
        return episodes

    def _read_shadow_cache(self, domain: str) -> Optional[List[MemoryEpisode]]:
        meta_file = self.cache_dir / f"{domain}_meta.json"
        data_file = self.cache_dir / f"{domain}_data.json"
        src_file = self.base_dir / domain / "episodes.jsonl"

        if (
            not meta_file.exists()
            or not data_file.exists()
            or not src_file.exists()
        ):
            return None

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            mtime = src_file.stat().st_mtime
            if meta.get("mtime") != mtime:
                return None

            raw_data = data_file.read_text(encoding="utf-8")
            items = json.loads(raw_data)
            return [MemoryEpisode.model_validate(x) for x in items]
        except Exception:
            return None

    def _update_shadow_cache(
        self,
        domain: str,
        episodes: Sequence[MemoryEpisode],
    ) -> None:
        try:
            src_file = self.base_dir / domain / "episodes.jsonl"
            mtime = src_file.stat().st_mtime if src_file.exists() else time.time()

            meta_file = self.cache_dir / f"{domain}_meta.json"
            data_file = self.cache_dir / f"{domain}_data.json"

            meta_file.write_text(
                json.dumps({"mtime": mtime, "domain": domain}),
                encoding="utf-8",
            )
            data_file.write_text(
                json.dumps([e.model_dump() for e in episodes]),
                encoding="utf-8",
            )
        except Exception:
            pass


def sync_tier1_capsule(
    base_dir: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per sincronizzare tier1_active_capsule.json."""
    resolved_base = (
        Path(base_dir).resolve()
        if base_dir
        else (_workspace_root / "nk_tracking" / "memory_3tier")
    )
    engine = ThreeTierMemoryEngine(base_dir=resolved_base, profile=profile)
    return engine.sync_tier1_capsule(output_path=output_path, profile=profile)


def main() -> int:
    """Interfaccia CLI per il motore di memoria a 3 livelli."""
    parser = argparse.ArgumentParser(
        description="Motore di Memoria Episodica a 3 Livelli Nexus Keystone"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Directory base della memoria episodica",
    )
    parser.add_argument(
        "--recall",
        action="store_true",
        help="Esegue una ricerca ibrida RRF nel dominio",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Aggiunge un nuovo episodio e sincronizza la capsula Tier-1",
    )
    parser.add_argument(
        "--tier1-sync",
        action="store_true",
        help="Sincronizza e persiste tier1_active_capsule.json",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="02_Development_Patterns",
        help="Dominio NK o alias breve (OPS, ARCH, DEVX, SEC)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Query di ricerca per --recall",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Lesson Learned",
        help="Titolo dell'episodio per --append",
    )
    parser.add_argument(
        "--content",
        type=str,
        default="",
        help="Contenuto dell'episodio per --append",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default="",
        help="Tag separati da virgola per --append",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Profilo di budget token (standard o argon)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Percorso di output personalizzato per tier1_active_capsule.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )

    args = parser.parse_args()
    base_path = (
        Path(args.base_dir).resolve()
        if args.base_dir
        else (_workspace_root / "nk_tracking" / "memory_3tier")
    )
    engine = ThreeTierMemoryEngine(base_dir=base_path, profile=args.profile)

    if args.append:
        tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
        ep = MemoryEpisode(
            episode_id=f"ep_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            domain=args.domain,
            title=args.title,
            content=args.content or args.title,
            tags=tag_list,
        )
        engine.append_episode(ep)
        capsule = engine.sync_tier1_capsule(output_path=args.output, profile=args.profile)
        out = {
            "status": "APPENDED",
            "episode_id": ep.episode_id,
            "domain": ep.domain,
            "tier1_synced": True,
            "token_cap": capsule["token_cap"],
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"[MEMORY-3TIER] Episodio salvato: {ep.episode_id} ({ep.domain})")
        return 0

    if args.tier1_sync:
        capsule = engine.sync_tier1_capsule(output_path=args.output, profile=args.profile)
        if args.json:
            print(json.dumps(capsule, indent=2))
        else:
            print(
                f"[MEMORY-3TIER] tier1_active_capsule.json sincronizzato (cap={capsule['token_cap']})."
            )
        return 0

    if args.recall:
        hits = engine.recall_hybrid(domain=args.domain, query=args.query)
        payload = {
            "status": "OK",
            "domain": resolve_domain(args.domain),
            "query": args.query,
            "results": [
                {
                    "episode_id": ep.episode_id,
                    "title": ep.title,
                    "content": ep.content,
                    "score": round(score, 6),
                }
                for ep, score in hits
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for ep, score in hits:
                print(f"[{round(score, 4)}] {ep.episode_id}: {ep.title} -> {ep.content}")
        return 0

    capsule = engine.sync_tier1_capsule(output_path=args.output, profile=args.profile)
    if args.json:
        print(json.dumps(capsule, indent=2))
    else:
        print(f"[MEMORY-3TIER] Ready. Base dir: {base_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

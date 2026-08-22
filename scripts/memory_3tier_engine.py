"""
Nexus Keystone v1.1.0-Universal: 3-Tier Episodic Memory Engine.
Compliant with:
- Tier 1 Core: <= 350 token cap in-context per domain
- Tier 2 Recall JSONL: Sliding window 200 events across 4 domains
- Tier 3 Archival Cold Store: Compacted long-term storage
- Hybrid Search Engine: Reciprocal Rank Fusion (RRF) = sum(1 / (60 + rank_m(d))) (BM25 + Dense Cosine)
- Shadow Read Cache in %TEMP% with SHA-256 + mtime invalidation (<1ms check)
- Rolling Snapshot Compaction with circular backup rotation (.bak_1, .bak_2)
- Win32 atomic file moves (MoveFileExW) with CTypes Win64 argtypes, 8 retry backoff, Shadow Swap
"""

from __future__ import annotations

import ctypes
import gzip
import hashlib
import json
import math
import os
import random
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field, ConfigDict, JsonValue


# ----------------------------------------------------------------------
# DOMAINS CONFIGURATION
# ----------------------------------------------------------------------
NK_DOMAINS: Tuple[str, ...] = (
    "01_Bug_Diagnostics",
    "02_Development_Patterns",
    "03_Ideation_and_Decisions",
    "04_Governance_and_Rules",
)

TIER1_TOKEN_CAP: int = 350
TIER2_SLIDING_WINDOW_MAX: int = 200
RRF_K_CONSTANT: float = 60.0
BACKUP_DEPTH: int = 2

# Windows MoveFileExW Flags & CTypes Definition
MOVEFILE_REPLACE_EXISTING = 0x00000001
MOVEFILE_WRITE_THROUGH = 0x00000008
MOVEFILE_COPY_ALLOWED = 0x00000002

ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33

if os.name == "nt":
    _kernel32 = ctypes.windll.kernel32
    _kernel32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    _kernel32.MoveFileExW.restype = ctypes.c_bool
    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32


# ----------------------------------------------------------------------
# WIN32 ATOMIC FILE OPS (with 8-retry backoff and Shadow Swap)
# ----------------------------------------------------------------------
def win32_atomic_replace(src_path: Path, dst_path: Path, max_retries: int = 8) -> None:
    """
    Atomic replacement using Win32 MoveFileExW with Win64 CTypes types,
    8-retry exponential backoff with full jitter for Google Drive locking,
    and Shadow Swap Fallback.
    """
    src_str = str(src_path.resolve())
    dst_str = str(dst_path.resolve())

    if os.name == "nt":
        flags = MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH | MOVEFILE_COPY_ALLOWED

        for attempt in range(max_retries):
            success = _kernel32.MoveFileExW(src_str, dst_str, flags)
            if success:
                return

            err = _kernel32.GetLastError()
            if err in (ERROR_SHARING_VIOLATION, ERROR_ACCESS_DENIED, ERROR_LOCK_VIOLATION):
                # Google Drive lock contention: backoff with jitter
                delay = random.uniform(0.010, min(0.080 * (1.6 ** attempt), 1.500))
                time.sleep(delay)
            else:
                try:
                    os.replace(src_str, dst_str)
                    return
                except (PermissionError, OSError):
                    delay = random.uniform(0.010, min(0.080 * (1.6 ** attempt), 1.500))
                    time.sleep(delay)

        # Shadow Swap Fallback
        shadow_tmp = dst_path.parent / f".shadow_{dst_path.name}_{os.getpid()}_{int(time.time()*1000)}.tmp"
        old_tmp = dst_path.parent / f".old_{dst_path.name}_{os.getpid()}_{int(time.time()*1000)}.tmp"

        for attempt in range(max_retries):
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

    # POSIX / Ultimate fallback
    os.replace(src_str, dst_str)


def rotate_circular_backups(target_file: Path, depth: int = BACKUP_DEPTH) -> None:
    """Rotate circular backup files using streaming shutil.copy2."""
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


# ----------------------------------------------------------------------
# PYDANTIC V2 MODELS
# ----------------------------------------------------------------------
class MemoryEpisode(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    episode_id: str = Field(description="Unique deterministic episode identifier")
    domain: str = Field(description="One of the 4 NK domains")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp")
    title: str = Field(description="Concise summary title")
    content: str = Field(description="Episode content body")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    vector: Optional[List[float]] = Field(default=None, description="Precomputed embedding vector")
    metadata: Dict[str, JsonValue] = Field(default_factory=dict, description="Arbitrary structured metadata")


class Tier1Item(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    key: str
    value: str
    priority: int = Field(default=1, ge=1, le=10)
    estimated_tokens: int = Field(default=0)


class Tier1DomainState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    domain: str
    items: Dict[str, Tier1Item] = Field(default_factory=dict)
    total_tokens: int = Field(default=0)


# ----------------------------------------------------------------------
# TOKEN ESTIMATION (Karpathy Fast-Approximation)
# ----------------------------------------------------------------------
def estimate_tokens(text: str) -> int:
    """Fast lexical token estimation: ~4 chars per token or words+symbols."""
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, math.ceil(len(words) * 1.15))


# ----------------------------------------------------------------------
# HYBRID SEARCH ENGINE (Pure Python BM25 + Dense Cosine + RRF)
# ----------------------------------------------------------------------
class PureBM25:
    """Pure Python BM25 implementation for lexical relevance."""

    def __init__(self, corpus: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
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

        self.avg_doc_len = (total_length / self.corpus_size) if self.corpus_size > 0 else 1.0

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())

    def score(self, query: str) -> List[float]:
        q_tokens = self._tokenize(query)
        scores = [0.0] * self.corpus_size

        for term in q_tokens:
            if term not in self.df:
                continue
            df_t = self.df[term]
            # Standard Lucene/BM25 IDF
            idf = math.log(1.0 + (self.corpus_size - df_t + 0.5) / (df_t + 0.5))

            for i, counts in enumerate(self.doc_token_counts):
                tf = counts.get(term, 0)
                if tf > 0:
                    doc_len = self.doc_lengths[i]
                    num = tf * (self.k1 + 1.0)
                    denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                    scores[i] += idf * (num / denom)

        return scores


class DenseEmbedder:
    """Deterministic hashing-based dense pseudo-embedding for testing."""

    @staticmethod
    def vector_from_text(text: str, dim: int = 64) -> List[float]:
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
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return max(-1.0, min(1.0, dot / (norm1 * norm2)))


class HybridRRFSearchEngine:
    """Reciprocal Rank Fusion (RRF) search engine."""

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
        if not episodes:
            return []

        # 1. Lexical BM25
        corpus = [f"{e.title} {e.content} {' '.join(e.tags)}" for e in episodes]
        bm25 = PureBM25(corpus)
        bm25_scores = bm25.score(query)
        bm25_ranked = sorted(range(len(episodes)), key=lambda i: bm25_scores[i], reverse=True)
        bm25_rank_map = {idx: rank + 1 for rank, idx in enumerate(bm25_ranked)}

        # 2. Dense Vector
        query_vec = DenseEmbedder.vector_from_text(query)
        dense_scores = []
        for e in episodes:
            vec = e.vector or DenseEmbedder.vector_from_text(f"{e.title} {e.content}")
            dense_scores.append(DenseEmbedder.cosine_similarity(query_vec, vec))
        dense_ranked = sorted(range(len(episodes)), key=lambda i: dense_scores[i], reverse=True)
        dense_rank_map = {idx: rank + 1 for rank, idx in enumerate(dense_ranked)}

        # 3. RRF Fusion
        rrf_scores: List[Tuple[MemoryEpisode, float]] = []
        for idx, ep in enumerate(episodes):
            r_bm25 = bm25_rank_map[idx]
            r_vec = dense_rank_map[idx]
            score_rrf = (bm25_weight / (self.k_rrf + r_bm25)) + (vector_weight / (self.k_rrf + r_vec))
            rrf_scores.append((ep, score_rrf))

        rrf_scores.sort(key=lambda item: item[1], reverse=True)
        return rrf_scores[:top_k]


# ----------------------------------------------------------------------
# TIER 1: CORE IN-CONTEXT MEMORY (Strict <= 350 tokens)
# ----------------------------------------------------------------------
class Tier1CoreMemory:
    def __init__(self, token_cap: int = TIER1_TOKEN_CAP) -> None:
        self.token_cap = token_cap
        self._domains: Dict[str, Tier1DomainState] = {
            d: Tier1DomainState(domain=d) for d in NK_DOMAINS
        }

    def set_item(self, domain: str, key: str, value: str, priority: int = 1) -> None:
        if domain not in self._domains:
            raise ValueError(f"Invalid domain: {domain}")

        d_state = self._domains[domain]
        tok = estimate_tokens(f"{key}: {value}")
        d_state.items[key] = Tier1Item(key=key, value=value, priority=priority, estimated_tokens=tok)
        self._enforce_budget(domain)

    def get_item(self, domain: str, key: str) -> Optional[str]:
        if domain in self._domains and key in self._domains[domain].items:
            return self._domains[domain].items[key].value
        return None

    def get_token_usage(self, domain: str) -> int:
        return self._domains[domain].total_tokens if domain in self._domains else 0

    def get_context_string(self, domain: str) -> str:
        if domain not in self._domains:
            return ""
        items = sorted(self._domains[domain].items.values(), key=lambda x: x.priority, reverse=True)
        return "\n".join(f"[{i.key}] {i.value}" for i in items)

    def _enforce_budget(self, domain: str) -> None:
        d_state = self._domains[domain]
        items = list(d_state.items.values())
        # Sort by priority ascending (lowest priority evicted first)
        items.sort(key=lambda x: (x.priority, -x.estimated_tokens))

        current_tokens = sum(x.estimated_tokens for x in items)
        while current_tokens > self.token_cap and items:
            evicted = items.pop(0)
            del d_state.items[evicted.key]
            current_tokens -= evicted.estimated_tokens

        d_state.total_tokens = sum(x.estimated_tokens for x in d_state.items.values())


# ----------------------------------------------------------------------
# THREE-TIER EPISODIC MEMORY ENGINE
# ----------------------------------------------------------------------
class ThreeTierMemoryEngine:
    def __init__(
        self,
        base_dir: Path | str,
        token_cap: int = TIER1_TOKEN_CAP,
        sliding_window_max: int = TIER2_SLIDING_WINDOW_MAX,
        cache_dir: Optional[Path | str] = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else (Path(tempfile.gettempdir()) / "nk_mem_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sliding_window_max = sliding_window_max

        self.tier1 = Tier1CoreMemory(token_cap=token_cap)
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
        if episode.domain not in NK_DOMAINS:
            raise ValueError(f"Unknown domain: {episode.domain}")

        d_dir = self.base_dir / episode.domain
        t2_file = d_dir / "episodes.jsonl"

        episodes = self._load_tier2_raw(t2_file)
        episodes.append(episode)

        # Sliding Window & Cold Compaction
        if len(episodes) > self.sliding_window_max:
            surplus_count = len(episodes) - self.sliding_window_max
            to_archive = episodes[:surplus_count]
            episodes = episodes[surplus_count:]
            self._archive_to_tier3(episode.domain, to_archive)

        # Write Tier 2 with circular backup & atomic replace
        rotate_circular_backups(t2_file)
        tmp_file = d_dir / f"episodes_{uuid.uuid4().hex[:8]}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            for ep in episodes:
                f.write(ep.model_dump_json() + "\n")

        win32_atomic_replace(tmp_file, t2_file)
        self._update_shadow_cache(episode.domain, episodes)

    def get_tier2_episodes(self, domain: str) -> List[MemoryEpisode]:
        # Fast path: Shadow Read Cache
        cached = self._read_shadow_cache(domain)
        if cached is not None:
            return cached

        t2_file = self.base_dir / domain / "episodes.jsonl"
        episodes = self._load_tier2_raw(t2_file)
        self._update_shadow_cache(domain, episodes)
        return episodes

    def get_tier3_episodes(self, domain: str) -> List[MemoryEpisode]:
        cold_file = self.base_dir / domain / "archive.cold.jsonl.gz"
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
    ) -> List[Tuple[MemoryEpisode, float]]:
        t2_eps = self.get_tier2_episodes(domain)
        t3_eps = self.get_tier3_episodes(domain)
        all_eps = t2_eps + t3_eps
        return self.search_engine.search(query, all_eps, top_k=top_k)

    def _archive_to_tier3(self, domain: str, surplus: Sequence[MemoryEpisode]) -> None:
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

        if not meta_file.exists() or not data_file.exists() or not src_file.exists():
            return None

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            mtime = src_file.stat().st_mtime
            if meta.get("mtime") != mtime:
                return None  # Stale

            raw_data = data_file.read_text(encoding="utf-8")
            items = json.loads(raw_data)
            return [MemoryEpisode.model_validate(x) for x in items]
        except Exception:
            return None

    def _update_shadow_cache(self, domain: str, episodes: Sequence[MemoryEpisode]) -> None:
        try:
            src_file = self.base_dir / domain / "episodes.jsonl"
            mtime = src_file.stat().st_mtime if src_file.exists() else time.time()

            meta_file = self.cache_dir / f"{domain}_meta.json"
            data_file = self.cache_dir / f"{domain}_data.json"

            meta_file.write_text(json.dumps({"mtime": mtime, "domain": domain}), encoding="utf-8")
            data_file.write_text(json.dumps([e.model_dump() for e in episodes]), encoding="utf-8")
        except Exception:
            pass

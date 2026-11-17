# -*- coding: utf-8 -*-
"""Orchestratore ThreeTierMemoryEngine e helper di modulo sync/consolidate."""

from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.memory_3tier_engine.models import (
    MemoryEpisode,
    NK_DOMAINS,
    TIER1_TOKEN_CAP,
    TIER2_SLIDING_WINDOW_MAX,
    _MEMORY_THREAD_LOCK,
    _acquire_memory_file_mutex,
    _facade_attr,
    _workspace_root,
    resolve_domain,
    rotate_circular_backups,
    win32_atomic_replace,
)
from _internal.memory_3tier_engine.search_bm25_dense import (
    DenseEmbedder,
    HybridRRFSearchEngine,
    PureBM25,
    _has_significant_overlap,
)
from _internal.memory_3tier_engine.sqlite_store import (
    archive_to_tier3_impl,
    get_cached_cold_episodes_impl,
    init_cold_fts_schema_impl,
    load_tier2_raw_impl,
    read_cold_archive_impl,
    search_cold_fts5_impl,
    sync_cold_fts5_index_impl,
)
from _internal.memory_3tier_engine.tier1_capsule import (
    Tier1CoreMemory,
    consolidate_episodes_impl,
    read_shadow_cache_impl,
    sync_engine_tier1_capsule_impl,
    update_shadow_cache_impl,
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
        self._project_cache_id = hashlib.sha256(
            str(self.base_dir.resolve()).encode("utf-8")
        ).hexdigest()[:12]
        self._repo_hash16 = hashlib.sha256(
            os.path.realpath(str(self.base_dir)).lower().encode("utf-8")
        ).hexdigest()[:16]

        cold_cache_dir = Path(tempfile.gettempdir()) / "nk_cache"
        cold_cache_dir.mkdir(parents=True, exist_ok=True)
        self._cold_fts_db_path = cold_cache_dir / f"nk_cold_fts5_{self._repo_hash16}.db"
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir
            else (Path(tempfile.gettempdir()) / "nk_mem_cache" / self._project_cache_id)
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sliding_window_max = sliding_window_max

        self._lock = _MEMORY_THREAD_LOCK
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
        rep_fn = _facade_attr("win32_atomic_replace", win32_atomic_replace)

        with self._lock, _acquire_memory_file_mutex(t2_file):
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

            rep_fn(tmp_file, t2_file)
            self._update_shadow_cache(canon, episodes)
            self.tier1.set_item(
                domain=canon, key=episode.episode_id,
                value=f"{episode.title}: {episode.content}", priority=5,
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

    def _read_cold_archive(self, cold_file: Path) -> List[MemoryEpisode]:
        """Legge l'archivio compresso recuperando i record validi prima di troncamenti."""
        return read_cold_archive_impl(cold_file)

    def _init_cold_fts_schema(self, conn: sqlite3.Connection) -> None:
        """Inizializza le tabelle metadati e FTS5 per la cache cold SQLite."""
        init_cold_fts_schema_impl(conn)

    def _sync_cold_fts5_index(self, cold_file: Path, conn: sqlite3.Connection) -> None:
        """Sincronizza la cache SQLite FTS5 solo quando mtime_ns o size cambiano."""
        sync_cold_fts5_index_impl(self, cold_file, conn)

    def _get_cached_cold_episodes(self, cold_file: Path) -> List[MemoryEpisode]:
        """Recupera gli episodi cold dalla cache SQLite senza decomprimere file invariati."""
        return get_cached_cold_episodes_impl(self, cold_file)

    def _search_cold_fts5(self, cold_file: Path, query: str, limit: int = 64) -> List[MemoryEpisode]:
        """Interroga l'archivio cold tramite indice FTS5 evitando decompressioni ripetute."""
        return search_cold_fts5_impl(self, cold_file, query, limit=limit)

    def get_tier3_episodes(self, domain: str) -> List[MemoryEpisode]:
        """Legge gli episodi storici del Livello 3 sfruttando la cache SQLite FTS5."""
        canon = resolve_domain(domain)
        return self._get_cached_cold_episodes(self.base_dir / canon / "archive.cold.jsonl.gz")

    def recall_hybrid(
        self,
        domain: str,
        query: str,
        top_k: int = 5,
        adaptive: bool = True,
    ) -> List[Tuple[MemoryEpisode, float]]:
        """Esegue una ricerca ibrida RRF adattiva combinando Livello 2 e Livello 3."""
        if not query or not query.strip():
            return []
        q_tokens = set(re.findall(r"\b[a-zA-Z0-9_]{2,}\b", query.lower()))
        if not q_tokens:
            return []

        canon = resolve_domain(domain)
        t2_eps = self.get_tier2_episodes(canon)
        t3_eps = self._search_cold_fts5(
            self.base_dir / canon / "archive.cold.jsonl.gz", query, limit=max(50, top_k * 10)
        )
        all_eps = t2_eps + t3_eps
        if not all_eps:
            return []

        corpus = [f"{e.title} {e.content} {' '.join(e.tags)}" for e in all_eps]
        bm25_raw = PureBM25(corpus).score(query)
        q_vec = DenseEmbedder.vector_from_text(query)

        candidate_eps: List[MemoryEpisode] = []
        for idx, ep in enumerate(all_eps):
            if not _has_significant_overlap(query, corpus[idx]):
                continue
            vec = ep.vector or DenseEmbedder.vector_from_text(f"{ep.title} {ep.content}")
            if bm25_raw[idx] <= 0.0 and DenseEmbedder.cosine_similarity(q_vec, vec) <= 0.0:
                continue
            candidate_eps.append(ep)

        if not candidate_eps:
            return []

        results = self.search_engine.search(query, candidate_eps, top_k=top_k)
        if not adaptive or not results:
            return results

        top_text = (
            f"{results[0][0].title} {results[0][0].content} {' '.join(results[0][0].tags)}".lower()
        )
        coverage = float(sum(1 for t in q_tokens if t in top_text)) / float(len(q_tokens))
        if coverage < 0.5:
            tag_pool: List[str] = []
            for ep in candidate_eps[-20:]:
                tag_pool.extend(ep.tags)
            expanded_query = f"{query} {' '.join(dict.fromkeys(tag_pool))}".strip()
            results = self.search_engine.search(
                expanded_query, candidate_eps, top_k=top_k,
                vector_weight=0.65, bm25_weight=0.35,
            )
        return results

    def sync_tier1_capsule(
        self,
        output_path: Optional[Path | str] = None,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sincronizza e persiste su disco il file tier1_active_capsule.json."""
        return sync_engine_tier1_capsule_impl(self, output_path=output_path, profile=profile)

    @staticmethod
    def _char_trigram_cosine(text_a: str, text_b: str) -> float:
        """Calcola la similarita coseno su trigrammi di caratteri in modo deterministico."""
        norm_a = re.sub(r"\s+", " ", (text_a or "").strip().lower())
        norm_b = re.sub(r"\s+", " ", (text_b or "").strip().lower())
        if not norm_a or not norm_b:
            return 0.0
        if norm_a == norm_b:
            return 1.0
        grams_a: Dict[str, int] = {}
        grams_b: Dict[str, int] = {}
        for i in range(max(1, len(norm_a) - 2)):
            g = norm_a[i : i + 3]
            grams_a[g] = grams_a.get(g, 0) + 1
        for i in range(max(1, len(norm_b) - 2)):
            g = norm_b[i : i + 3]
            grams_b[g] = grams_b.get(g, 0) + 1
        dot = sum(cnt * grams_b.get(g, 0) for g, cnt in grams_a.items())
        mag_a = math.sqrt(sum(c * c for c in grams_a.values()))
        mag_b = math.sqrt(sum(c * c for c in grams_b.values()))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (mag_a * mag_b)))

    def consolidate_similar_episodes(
        self,
        domain: Optional[str] = None,
        threshold: float = 0.92,
    ) -> Dict[str, Any]:
        """Consolida in modo deterministico Zero-LLM gli episodi con similarita >= threshold."""
        return consolidate_episodes_impl(self, domain=domain, threshold=threshold)

    def _archive_to_tier3(self, domain: str, surplus: Sequence[MemoryEpisode]) -> None:
        archive_to_tier3_impl(self.base_dir, domain, surplus)

    def _load_tier2_raw(self, path: Path) -> List[MemoryEpisode]:
        return load_tier2_raw_impl(path)

    def _read_shadow_cache(self, domain: str) -> Optional[List[MemoryEpisode]]:
        return read_shadow_cache_impl(self.cache_dir, self._project_cache_id, self.base_dir, domain)

    def _update_shadow_cache(self, domain: str, episodes: Sequence[MemoryEpisode]) -> None:
        update_shadow_cache_impl(
            self.cache_dir, self._project_cache_id, self.base_dir, domain, episodes
        )


def sync_tier1_capsule(
    base_dir: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per sincronizzare tier1_active_capsule.json."""
    ws_root = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_base = Path(base_dir).resolve() if base_dir else (ws_root / "nk_tracking" / "memory_3tier")
    eff_prof = profile or os.environ.get("NK_MODEL_PROFILE")
    if isinstance(eff_prof, str):
        eff_prof = eff_prof.strip().lower() or None
    engine = ThreeTierMemoryEngine(base_dir=resolved_base, profile=eff_prof)
    return engine.sync_tier1_capsule(output_path=output_path, profile=eff_prof)


def consolidate_similar_episodes(
    domain: Optional[str] = None,
    threshold: float = 0.92,
    root: Optional[Path] = None,
    base_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per consolidare gli episodi simili Zero-LLM."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError(f"Soglia threshold non valida: {threshold}")
    if not (0.0 < float(threshold) <= 1.0):
        raise ValueError(f"Soglia threshold fuori intervallo (0.0, 1.0]: {threshold}")
    ws_root = Path(_facade_attr("_workspace_root", _workspace_root))
    if base_dir is not None:
        resolved_base = Path(base_dir).resolve()
    elif root is not None:
        r_path = Path(root).resolve()
        if any((r_path / d).exists() for d in NK_DOMAINS):
            resolved_base = r_path
        elif (r_path / "nk_tracking" / "memory_3tier").exists():
            resolved_base = r_path / "nk_tracking" / "memory_3tier"
        else:
            resolved_base = r_path
    else:
        resolved_base = ws_root / "nk_tracking" / "memory_3tier"

    engine = ThreeTierMemoryEngine(base_dir=resolved_base)
    return engine.consolidate_similar_episodes(domain=domain, threshold=threshold)

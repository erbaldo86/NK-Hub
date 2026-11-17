# -*- coding: utf-8 -*-
"""Memoria Tier1CoreMemory, persistenza capsula, shadow cache e consolidamento."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pydantic import JsonValue

from _internal.nk_common.constants import HIGH_CAPACITY_PROFILES
from _internal.memory_3tier_engine.models import (
    MEMORY_SCHEMA_VERSION,
    MemoryEpisode,
    NK_DOMAINS,
    TIER1_TOKEN_CAP,
    TIER1_TOKEN_CAP_CARBON,
    Tier1DomainState,
    Tier1Item,
    _acquire_memory_file_mutex,
    _facade_attr,
    estimate_tokens,
    resolve_domain,
    rotate_circular_backups,
    win32_atomic_replace,
)
from _internal.memory_3tier_engine.search_bm25_dense import (
    DenseEmbedder,
    _has_opposite_polarity,
)


class Tier1CoreMemory:
    """Gestisce la memoria core di Livello 1 con budget massimo di token."""

    def __init__(
        self,
        token_cap: int = TIER1_TOKEN_CAP,
        profile: Optional[str] = None,
    ) -> None:
        norm_prof = profile.strip().lower() if isinstance(profile, str) else ""
        if norm_prof in HIGH_CAPACITY_PROFILES and token_cap == TIER1_TOKEN_CAP:
            self.token_cap = TIER1_TOKEN_CAP_CARBON
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
            key=key, value=value, priority=priority, estimated_tokens=tok
        )
        self._enforce_budget(canon)

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
            self._domains[canon].items.values(), key=lambda x: x.priority, reverse=True
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
        d_state.total_tokens = sum(x.estimated_tokens for x in d_state.items.values())


def sync_engine_tier1_capsule_impl(
    engine: Any,
    output_path: Optional[Path | str] = None,
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Sincronizza e persiste su disco il file tier1_active_capsule.json."""
    norm_prof = profile.strip().lower() if isinstance(profile, str) and profile.strip() else None
    if norm_prof in HIGH_CAPACITY_PROFILES and engine.tier1.token_cap == TIER1_TOKEN_CAP:
        engine.tier1.token_cap = TIER1_TOKEN_CAP_CARBON
    elif norm_prof == "standard" and profile is not None and engine.tier1.token_cap == TIER1_TOKEN_CAP_CARBON:
        engine.tier1.token_cap = TIER1_TOKEN_CAP

    for dom in NK_DOMAINS:
        recent_eps = engine.get_tier2_episodes(dom)[-5:]
        for idx, ep in enumerate(recent_eps, start=1):
            existing = engine.tier1._domains[dom].items.get(ep.episode_id)
            eff_prio = max(existing.priority if existing else 0, min(10, idx + 2))
            engine.tier1.set_item(
                domain=dom, key=ep.episode_id,
                value=f"{ep.title}: {ep.content}", priority=eff_prio,
            )

    active_profile = norm_prof or (
        "generation" if engine.tier1.token_cap == TIER1_TOKEN_CAP_CARBON else "standard"
    )
    domains_payload: Dict[str, Any] = {}
    lessons_list: List[Dict[str, Any]] = []

    for dom in NK_DOMAINS:
        d_state = engine.tier1._domains[dom]
        items_dumped = [it.model_dump() for it in d_state.items.values()]
        domains_payload[dom] = {
            "total_tokens": d_state.total_tokens,
            "context": engine.tier1.get_context_string(dom),
            "items": items_dumped,
        }
        for it in d_state.items.values():
            lessons_list.append(
                {
                    "domain": dom, "key": it.key,
                    "lesson": f"[{it.key}] {it.value}",
                    "priority": it.priority, "estimated_tokens": it.estimated_tokens,
                }
            )

    capsule_data: Dict[str, Any] = {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "updated_at": time.time(),
        "profile": active_profile,
        "token_cap": engine.tier1.token_cap,
        "domains": domains_payload,
        "lessons": lessons_list,
    }

    target_file = (
        Path(output_path).resolve()
        if output_path
        else (engine.base_dir / "tier1_active_capsule.json").resolve()
    )
    target_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_capsule = target_file.parent / f"tier1_capsule_{uuid.uuid4().hex[:8]}.tmp"
    tmp_capsule.write_text(
        json.dumps(capsule_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    rep_fn = _facade_attr("win32_atomic_replace", win32_atomic_replace)
    rep_fn(tmp_capsule, target_file)
    return capsule_data


def read_shadow_cache_impl(
    cache_dir: Path, project_cache_id: str, base_dir: Path, domain: str
) -> Optional[List[MemoryEpisode]]:
    """Legge la shadow cache JSON del Livello 2 se size e mtime corrispondono."""
    meta_file = cache_dir / f"{project_cache_id}_{domain}_meta.json"
    data_file = cache_dir / f"{project_cache_id}_{domain}_data.json"
    src_file = base_dir / domain / "episodes.jsonl"
    if not meta_file.exists() or not data_file.exists() or not src_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        st = src_file.stat()
        if meta.get("size") != st.st_size:
            return None
        if "mtime_ns" in meta:
            if meta.get("mtime_ns") != st.st_mtime_ns:
                return None
        elif meta.get("mtime") != st.st_mtime:
            return None
        items = json.loads(data_file.read_text(encoding="utf-8"))
        return [MemoryEpisode.model_validate(x) for x in items]
    except Exception:
        return None


def update_shadow_cache_impl(
    cache_dir: Path,
    project_cache_id: str,
    base_dir: Path,
    domain: str,
    episodes: Sequence[MemoryEpisode],
) -> None:
    """Aggiorna la shadow cache JSON locale del Livello 2 ignorando errori I/O non critici."""
    try:
        src_file = base_dir / domain / "episodes.jsonl"
        st = src_file.stat() if src_file.exists() else None
        mtime = st.st_mtime if st is not None else time.time()
        mtime_ns = st.st_mtime_ns if st is not None else time.time_ns()
        size = st.st_size if st is not None else 0
        meta_file = cache_dir / f"{project_cache_id}_{domain}_meta.json"
        data_file = cache_dir / f"{project_cache_id}_{domain}_data.json"
        meta_file.write_text(
            json.dumps({"mtime": mtime, "mtime_ns": mtime_ns, "size": size, "domain": domain}),
            encoding="utf-8",
        )
        data_file.write_text(
            json.dumps([e.model_dump() for e in episodes]), encoding="utf-8"
        )
    except Exception:
        pass


def consolidate_episodes_impl(
    engine: Any,
    domain: Optional[str] = None,
    threshold: float = 0.92,
) -> Dict[str, Any]:
    """Consolida in modo deterministico Zero-LLM gli episodi con similarita >= threshold."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError(f"Soglia threshold non valida: {threshold}")
    eff_threshold = float(threshold)
    if not (0.0 < eff_threshold <= 1.0):
        raise ValueError(f"Soglia threshold fuori intervallo (0.0, 1.0]: {threshold}")
    target_domains = [resolve_domain(domain)] if domain else list(NK_DOMAINS)
    total_merged = 0
    total_remaining = 0
    rep_fn = _facade_attr("win32_atomic_replace", win32_atomic_replace)

    for dom in target_domains:
        d_dir = engine.base_dir / dom
        t2_file = d_dir / "episodes.jsonl"
        with engine._lock, _acquire_memory_file_mutex(t2_file):
            if not t2_file.exists():
                continue
            episodes = engine._load_tier2_raw(t2_file)
            if len(episodes) <= 1:
                total_remaining += len(episodes)
                continue

            kept: List[MemoryEpisode] = []
            kept_vecs: List[List[float]] = []
            kept_texts: List[str] = []
            dom_merged = 0

            for ep in episodes:
                ep_text = f"{ep.title} {ep.content}".strip()
                ep_vec = ep.vector or DenseEmbedder.vector_from_text(ep_text)
                matched_idx = -1
                for idx, (k_vec, k_text) in enumerate(zip(kept_vecs, kept_texts)):
                    if _has_opposite_polarity(ep_text, k_text):
                        continue
                    sim = max(
                        DenseEmbedder.cosine_similarity(ep_vec, k_vec),
                        engine._char_trigram_cosine(ep_text, k_text),
                    )
                    if sim >= eff_threshold:
                        matched_idx = idx
                        break

                if matched_idx >= 0:
                    dom_merged += 1
                    base_ep = kept[matched_idx]
                    merged_tags = list(dict.fromkeys(list(base_ep.tags) + list(ep.tags)))
                    merged_meta = dict(ep.metadata)
                    merged_meta.update(base_ep.metadata)
                    for prov_key in ("source_url", "evidence_quote"):
                        if not merged_meta.get(prov_key) and ep.metadata.get(prov_key):
                            merged_meta[prov_key] = ep.metadata[prov_key]
                    prev_cons = merged_meta.get("consolidated_ids")
                    cons_list: List[JsonValue] = list(prev_cons) if isinstance(prev_cons, list) else []
                    cons_list.append(ep.episode_id)
                    merged_meta["consolidated_ids"] = cons_list
                    kept[matched_idx] = MemoryEpisode(
                        episode_id=base_ep.episode_id,
                        domain=dom,
                        timestamp=max(base_ep.timestamp, ep.timestamp),
                        title=base_ep.title,
                        content=base_ep.content if len(base_ep.content) >= len(ep.content) else ep.content,
                        tags=merged_tags,
                        vector=base_ep.vector or ep_vec,
                        metadata=merged_meta,
                    )
                else:
                    kept.append(ep)
                    kept_vecs.append(ep_vec)
                    kept_texts.append(ep_text)

            if dom_merged > 0:
                rotate_circular_backups(t2_file)
                tmp_file = d_dir / f"episodes_cons_{uuid.uuid4().hex[:8]}.tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    for kep in kept:
                        f.write(kep.model_dump_json() + "\n")
                rep_fn(tmp_file, t2_file)
                engine._update_shadow_cache(dom, kept)

            total_merged += dom_merged
            total_remaining += len(kept)

    return {
        "status": "CONSOLIDATED",
        "passed": True,
        "merged_count": total_merged,
        "remaining_count": total_remaining,
        "threshold": float(threshold),
    }

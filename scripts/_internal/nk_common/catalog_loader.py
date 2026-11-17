# -*- coding: utf-8 -*-
"""Loader O(1) stdlib con cache stat per manifesto SSOT e shard DOM-00..DOM-06."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from _internal.nk_common.paths import resolve_workspace_root

_MANIFEST_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}
_SHARD_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def clear_catalog_cache() -> None:
    """Svuota le cache in memoria del catalogo manifesto e degli shard."""
    _MANIFEST_CACHE.clear()
    _SHARD_CACHE.clear()


def _resolve_base_root(workspace_root: Optional[Union[str, Path]]) -> Path:
    """Risolve la directory radice del workspace NK_Hub."""
    if workspace_root is not None:
        return Path(workspace_root).resolve()
    return Path(resolve_workspace_root(__file__)).resolve()


def _read_json_cached(
    cand: Path, cache: Dict[str, Tuple[int, int, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """Legge un oggetto JSON da file usando cache (st_mtime_ns, st_size)."""
    if not cand.is_file():
        return None
    try:
        st = cand.stat()
        key = str(cand)
        cached = cache.get(key)
        if (
            cached is not None
            and cached[0] == st.st_mtime_ns
            and cached[1] == st.st_size
        ):
            return dict(cached[2])
        data = json.loads(cand.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            cache[key] = (st.st_mtime_ns, st.st_size, data)
            return dict(data)
    except Exception:
        return None
    return None


def load_domain_shard(
    domain_id: str, workspace_root: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """Carica uno shard DOM-0X.json privilegiando .staging/ rispetto alla produzione."""
    clean_id = (domain_id or "").strip()
    if not clean_id:
        return {}
    fname = clean_id if clean_id.endswith(".json") else f"{clean_id}.json"
    base_root = _resolve_base_root(workspace_root)
    for cand in (
        base_root / ".staging" / "nk_genome" / "shards" / fname,
        base_root / "nk_genome" / "shards" / fname,
    ):
        data = _read_json_cached(cand, _SHARD_CACHE)
        if data is not None:
            return data
    return {}


def load_all_domain_shards(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Carica tutti gli shard disponibili da DOM-00 a DOM-06 in ordine crescente."""
    shards: Dict[str, Dict[str, Any]] = {}
    for idx in range(7):
        dom_id = f"DOM-0{idx}"
        data = load_domain_shard(dom_id, workspace_root=workspace_root)
        if data:
            shards[dom_id] = data
    return shards


def _rehydrate_from_shards(
    slim_data: Dict[str, Any], workspace_root: Path
) -> Dict[str, Any]:
    """Ricompone in memoria il manifesto completo a partire dagli shard DOM-00..DOM-06."""
    shards_decl = slim_data.get("shards")
    if not isinstance(shards_decl, dict) or not shards_decl:
        return slim_data

    merged: Dict[str, Any] = dict(slim_data)
    domains_out: Dict[str, Dict[str, Any]] = {}
    skills_out: Dict[str, Dict[str, Any]] = {}
    scripts_out: Dict[str, Dict[str, Any]] = {}
    agents_out: Dict[str, Dict[str, Any]] = {}
    dispatch_out: Dict[str, Dict[str, Any]] = {}

    for shard_id in sorted(shards_decl):
        sdata = load_domain_shard(shard_id, workspace_root=workspace_root)
        if not sdata:
            continue
        if shard_id == "DOM-00":
            if "global_hygiene_profile" in sdata:
                merged["global_hygiene_profile"] = sdata["global_hygiene_profile"]
            if "docs_and_setup_index" in sdata:
                merged["docs_and_setup_index"] = sdata["docs_and_setup_index"]
            if sdata.get("milestone_anchor_id"):
                merged["milestone_anchor_id"] = sdata["milestone_anchor_id"]
            continue
        if shard_id == "DOM-06":
            merged["release_meta"] = sdata
            continue

        dom_obj = sdata.get("domain")
        raw_intent_tbl = sdata.get("intent_dispatch_table", {})
        unpacked_intents: Dict[str, Any] = {}
        if isinstance(raw_intent_tbl, dict):
            routes_grp = raw_intent_tbl.get("_routes")
            if isinstance(routes_grp, list):
                for item in routes_grp:
                    if isinstance(item, list) and len(item) >= 3 and isinstance(item[2], list):
                        for kw in item[2]:
                            unpacked_intents[str(kw)] = [str(item[0]), str(item[1])]
            for kw, entry in raw_intent_tbl.items():
                if kw != "_routes":
                    unpacked_intents[kw] = entry
        dom_id = (
            str(dom_obj.get("domain_id") or shard_id)
            if isinstance(dom_obj, dict)
            else shard_id
        )
        dom_name = (
            str(dom_obj.get("name", ""))
            if isinstance(dom_obj, dict)
            else str(slim_data.get("domains", {}).get(dom_id, {}).get("name", ""))
        )
        dom_primary = (
            str(dom_obj.get("primary_skill", "")) if isinstance(dom_obj, dict) else ""
        )
        if isinstance(dom_obj, dict):
            dispatch_kws = list(unpacked_intents.keys())
            merged_kws = list(
                dict.fromkeys(list(dom_obj.get("keywords", [])) + dispatch_kws)
            )
            domains_out[dom_id] = {**dom_obj, "keywords": merged_kws}

        for sk_name, sk_meta in sdata.get("skills_index", {}).items():
            if isinstance(sk_meta, dict):
                skills_out[sk_name] = {
                    "name": sk_name,
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "sector": sk_meta.get("sector", dom_name),
                    **sk_meta,
                }
        for sc_name, sc_meta in sdata.get("scripts_index", {}).items():
            if isinstance(sc_meta, dict):
                scripts_out[sc_name] = {
                    "name": sc_name,
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "path": f"scripts/{sc_name}",
                    **sc_meta,
                }
        for ag_name, ag_meta in sdata.get("native_agents_index", {}).items():
            if isinstance(ag_meta, dict):
                agents_out[ag_name] = {
                    "name": ag_name,
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    **ag_meta,
                }
        for kw, entry in unpacked_intents.items():
            if isinstance(entry, list) and len(entry) >= 2:
                dispatch_out[kw] = {
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "primary_agent": str(entry[0]),
                    "recommended_mode": str(entry[1]),
                }
            elif isinstance(entry, str):
                dispatch_out[kw] = {
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "primary_agent": dom_primary,
                    "recommended_mode": entry,
                }
            elif isinstance(entry, dict):
                dispatch_out[kw] = entry

    if domains_out:
        merged["domains"] = domains_out
    if skills_out:
        merged["skills_index"] = skills_out
    if scripts_out:
        merged["scripts_index"] = scripts_out
    if agents_out:
        merged["native_agents_index"] = agents_out
    if dispatch_out:
        merged["intent_dispatch_table"] = dispatch_out
    return merged


def load_registry_manifest(
    workspace_root: Optional[Union[str, Path]] = None,
    *,
    rehydrate: bool = True,
) -> Dict[str, Any]:
    """Carica nk_registry_manifest.json privilegiando .staging/ con fallback a dict vuoto."""
    base_root = _resolve_base_root(workspace_root)
    for cand in (
        base_root / ".staging" / "nk_genome" / "nk_registry_manifest.json",
        base_root / "nk_genome" / "nk_registry_manifest.json",
    ):
        data = _read_json_cached(cand, _MANIFEST_CACHE)
        if data is not None:
            if rehydrate and "shards" in data:
                return _rehydrate_from_shards(data, base_root)
            return data
    return {}

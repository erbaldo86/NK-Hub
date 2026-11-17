"""Reidratazione in memoria del manifesto dagli shard DOM-00..DOM-06."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def rehydrate_manifest_from_shards(
    manifest_path: Path, slim_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Ricompone in memoria il manifesto completo a partire dagli shard DOM-00..DOM-06."""
    shards_decl = slim_data.get("shards")
    if not isinstance(shards_decl, dict) or not shards_decl:
        return slim_data

    base_dir = manifest_path.parent
    merged: Dict[str, Any] = dict(slim_data)
    domains_out: Dict[str, Dict[str, Any]] = {}
    skills_out: Dict[str, Dict[str, Any]] = {}
    scripts_out: Dict[str, Dict[str, Any]] = {}
    agents_out: Dict[str, Dict[str, Any]] = {}
    dispatch_out: Dict[str, Dict[str, Any]] = {}

    for shard_id, rel_path in sorted(shards_decl.items()):
        shard_file = base_dir / str(rel_path)
        if not shard_file.is_file() and base_dir.parent.name == ".staging":
            alt_file = base_dir.parent.parent / "nk_genome" / str(rel_path)
            if alt_file.is_file():
                shard_file = alt_file
        if not shard_file.is_file():
            continue
        try:
            sdata = json.loads(shard_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(sdata, dict):
            continue

        if shard_id == "DOM-00":
            if "global_hygiene_profile" in sdata:
                merged["global_hygiene_profile"] = sdata["global_hygiene_profile"]
            if "docs_and_setup_index" in sdata:
                merged["docs_and_setup_index"] = {
                    k: {"name": k, **v}
                    for k, v in sdata["docs_and_setup_index"].items()
                    if isinstance(v, dict)
                }
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
        dispatch_kws = list(unpacked_intents.keys())
        if isinstance(dom_obj, dict):
            dom_id = str(dom_obj.get("domain_id") or shard_id)
            dom_name = str(dom_obj.get("name", ""))
            dom_primary = str(dom_obj.get("primary_skill", ""))
            merged_kws = list(dict.fromkeys(list(dom_obj.get("keywords", [])) + dispatch_kws))
            domains_out[dom_id] = {**dom_obj, "keywords": merged_kws}
        else:
            dom_id = shard_id
            dom_name = str(slim_data.get("domains", {}).get(dom_id, {}).get("name", ""))
            dom_primary = ""

        for sk_name, sk_meta in sdata.get("skills_index", {}).items():
            if isinstance(sk_meta, dict):
                skills_out[sk_name] = {
                    "name": sk_name,
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "sector": sk_meta.get("sector", dom_name),
                    "enable_mcp_tools": bool(sk_meta.get("enable_mcp_tools", False)),
                    "path": sk_meta.get("path", f".agents/skills/{sk_name}/SKILL.md"),
                    "source_layer": sk_meta.get("source_layer", "production"),
                    **sk_meta,
                }
        for sc_name, sc_meta in sdata.get("scripts_index", {}).items():
            if isinstance(sc_meta, dict):
                scripts_out[sc_name] = {
                    "name": sc_name,
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "cli_flags": sc_meta.get("cli_flags", []),
                    "classes": sc_meta.get("classes", []),
                    "path": f"scripts/{sc_name}",
                    "source_layer": sc_meta.get("source_layer", "production"),
                    **sc_meta,
                }
        for ag_name, ag_meta in sdata.get("native_agents_index", {}).items():
            if isinstance(ag_meta, dict):
                agents_out[ag_name] = {
                    "name": ag_name,
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "enable_write_tools": bool(ag_meta.get("enable_write_tools", False)),
                    "enable_subagent_tools": bool(ag_meta.get("enable_subagent_tools", False)),
                    "enable_mcp_tools": bool(ag_meta.get("enable_mcp_tools", False)),
                    "path": ag_meta.get("path", f".agents/agents/{ag_name}/agent.md"),
                    "source_layer": ag_meta.get("source_layer", "production"),
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
        for dk, dv in slim_data.get("domains", {}).items():
            if dk not in domains_out:
                domains_out[dk] = dv
        merged["domains"] = domains_out
    if skills_out:
        merged["skills_index"] = skills_out
    if scripts_out:
        merged["scripts_index"] = scripts_out
    if agents_out or "native_agents_index" not in merged:
        merged["native_agents_index"] = agents_out
    if dispatch_out:
        merged["intent_dispatch_table"] = dispatch_out
    return merged

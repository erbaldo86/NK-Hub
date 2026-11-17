"""Matcher O(1) per domini, skill granulari e subagent nativi da manifesto SSOT."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from _internal.vibe_sprint_router.constants_core import (
    _DEFAULT_WORKSPACE_ROOT,
    _LARGE_PROMPT_THRESHOLD,
    _ROUTER_MANIFEST_CACHE,
    _normalize_input_text,
    _sanitize_tetralogia_filenames,
)
from _internal.vibe_sprint_router.constants_stt import (
    DASHBOARD_NODE_MAP,
    _MULTI_SPACE_RE,
    _PUNCT_NORM_RE,
    _SHORT_CONFIRMATIONS,
    _extract_primary_stt_clause,
    _parse_dashboard_selector,
)
from _internal.vibe_sprint_router.routing_helpers import (
    _has_audit_forensic_intent,
    _match_granular_skills,
    _resolve_native_subagent,
    _token_matches_keyword,
)


def _rehydrate_router_manifest_shards(
    manifest_path: Path, slim_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Reidrata in O(1) i metadati shard DOM-01..DOM-05 per VibeSprintRouter."""
    shards_decl = slim_data.get("shards")
    if not isinstance(shards_decl, dict) or not shards_decl:
        return slim_data
    base_dir = manifest_path.parent
    merged: Dict[str, Any] = dict(slim_data)
    domains_out: Dict[str, Dict[str, Any]] = {}
    skills_out: Dict[str, Dict[str, Any]] = {}
    scripts_out: Dict[str, Dict[str, Any]] = {}
    dispatch_out: Dict[str, Dict[str, Any]] = {}
    for shard_id, rel_path in sorted(shards_decl.items()):
        if shard_id in ("DOM-00", "DOM-06"):
            continue
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
        dom_obj = sdata.get("domain")
        dom_id = str(dom_obj.get("domain_id") or shard_id) if isinstance(dom_obj, dict) else shard_id
        dom_name = str(dom_obj.get("name", "")) if isinstance(dom_obj, dict) else str(slim_data.get("domains", {}).get(dom_id, {}).get("name", ""))
        dom_primary = str(dom_obj.get("primary_skill", "")) if isinstance(dom_obj, dict) else ""
        if isinstance(dom_obj, dict):
            domains_out[dom_id] = {**dom_obj, "keywords": list(dict.fromkeys(list(dom_obj.get("keywords", [])) + list(unpacked_intents.keys())))}
        for sk_name, sk_meta in sdata.get("skills_index", {}).items():
            if isinstance(sk_meta, dict):
                skills_out[sk_name] = {"name": sk_name, "domain_id": dom_id, "domain_name": dom_name, "sector": sk_meta.get("sector", dom_name), **sk_meta}
        for sc_name, sc_meta in sdata.get("scripts_index", {}).items():
            if isinstance(sc_meta, dict):
                scripts_out[sc_name] = {"name": sc_name, "domain_id": dom_id, "domain_name": dom_name, **sc_meta}
        for kw, entry in unpacked_intents.items():
            if isinstance(entry, list) and len(entry) >= 2:
                dispatch_out[kw] = {"domain_id": dom_id, "domain_name": dom_name, "primary_agent": str(entry[0]), "recommended_mode": str(entry[1])}
            elif isinstance(entry, str):
                dispatch_out[kw] = {"domain_id": dom_id, "domain_name": dom_name, "primary_agent": dom_primary, "recommended_mode": entry}
            elif isinstance(entry, dict):
                dispatch_out[kw] = entry
    if domains_out:
        merged["domains"] = domains_out
    if skills_out:
        merged["skills_index"] = skills_out
    if scripts_out:
        merged["scripts_index"] = scripts_out
    if dispatch_out:
        merged["intent_dispatch_table"] = dispatch_out
    return merged


def load_registry_manifest_impl(self) -> Dict[str, Any]:
    """Carica nk_registry_manifest.json da staging o root con cache statica O(1) e shard."""
    candidates = (
        self.staging_dir / "nk_genome" / "nk_registry_manifest.json",
        self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
        _DEFAULT_WORKSPACE_ROOT
        / ".staging"
        / "nk_genome"
        / "nk_registry_manifest.json",
        _DEFAULT_WORKSPACE_ROOT / "nk_genome" / "nk_registry_manifest.json",
    )
    for cand in candidates:
        if cand.exists() and cand.is_file():
            try:
                st = cand.stat()
                key = str(cand)
                cached = _ROUTER_MANIFEST_CACHE.get(key)
                if (
                    cached is not None
                    and cached[0] == st.st_mtime_ns
                    and cached[1] == st.st_size
                ):
                    return cached[2]
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "shards" in data:
                        data = _rehydrate_router_manifest_shards(cand, data)
                    _ROUTER_MANIFEST_CACHE[key] = (
                        st.st_mtime_ns,
                        st.st_size,
                        data,
                    )
                    return data
            except Exception:
                pass
    return {}


def resolve_domain_from_manifest_impl(self, prompt: str) -> Dict[str, Any]:
    """Risolve in O(1) il dominio funzionale DOM-01..DOM-05 e le skill interrogando il manifesto SSOT."""
    raw_norm = _normalize_input_text(prompt).strip()
    sel_idx = _parse_dashboard_selector(raw_norm)
    if sel_idx is not None:
        sk_name, dom_id, dom_name, subagent, _is_ro = DASHBOARD_NODE_MAP[sel_idx]
        return {
            "domain_id": dom_id,
            "domain_name": dom_name,
            "primary_skill": sk_name,
            "matched_skills": [sk_name],
            "native_subagent": subagent,
            "matched_triggers": [f"[{sel_idx}]"],
            "dashboard_node": sel_idx,
        }

    if len(raw_norm) <= 128:
        norm_fast = _MULTI_SPACE_RE.sub(
            " ", _PUNCT_NORM_RE.sub(" ", raw_norm.lower())
        ).strip()
        if norm_fast in _SHORT_CONFIRMATIONS:
            return {
                "domain_id": "DOM-03",
                "domain_name": "BUILD_AND_HEAL",
                "primary_skill": "NK-Python-Async-Builder",
                "matched_skills": ["NK-Python-Async-Builder"],
                "native_subagent": "NK-Builder-Agent",
                "matched_triggers": [],
            }

    effective_text = _extract_primary_stt_clause(raw_norm)
    text_lower = effective_text.lower()
    scan_lower = (
        f"{text_lower[:12288]} {text_lower[-4096:]}"
        if len(text_lower) > _LARGE_PROMPT_THRESHOLD
        else text_lower
    )
    is_audit_forensic = _has_audit_forensic_intent(scan_lower)

    manifest = self._load_registry_manifest()
    domains = manifest.get("domains", {})
    skills_index = manifest.get("skills_index", {})
    scripts_index = manifest.get("scripts_index", {})
    dispatch_table = manifest.get("intent_dispatch_table", {})

    # 1. Riferimento esplicito a ID dominio nel prompt (es. DOM-04)
    for dom_id, dom_meta in domains.items():
        dom_name_low = dom_meta.get("name", "").lower()
        if dom_id.lower() in scan_lower or (
            dom_name_low and dom_name_low in scan_lower
        ):
            primary_sk = dom_meta.get("primary_skill", "NK-Orchestrator")
            return {
                "domain_id": dom_id,
                "domain_name": dom_meta.get("name", ""),
                "primary_skill": primary_sk,
                "matched_skills": [primary_sk],
                "native_subagent": _resolve_native_subagent(
                    dom_id, matched_skill=primary_sk, text=scan_lower
                ),
                "matched_triggers": [dom_id],
            }

    # 2. Riferimento esplicito a una skill nel prompt
    for sk_name, sk_meta in skills_index.items():
        if sk_name.lower() in scan_lower:
            dom_id = sk_meta.get("domain_id", "DOM-01")
            return {
                "domain_id": dom_id,
                "domain_name": sk_meta.get("domain_name", "GOV_AND_ROUTING"),
                "primary_skill": sk_name,
                "matched_skills": [sk_name],
                "native_subagent": _resolve_native_subagent(
                    dom_id, matched_skill=sk_name, text=scan_lower
                ),
                "matched_triggers": [sk_name],
            }

    # 3. Regole granulari multi-skill per intenti composti o specialistici
    clean_text = _sanitize_tetralogia_filenames(scan_lower)
    skill_matches = _match_granular_skills(clean_text)
    if skill_matches:
        chosen_match = skill_matches[0]
        if is_audit_forensic and chosen_match[1] == "DOM-03":
            non_builder = [
                m for m in skill_matches if m[1] in ("DOM-04", "DOM-01")
            ]
            if non_builder:
                chosen_match = non_builder[0]
            else:
                chosen_match = (
                    "NK-Security-Auditor",
                    "DOM-04",
                    "AUDIT_DAST_AND_RCA",
                    "NK-Security-DAST-Auditor",
                    ["audit_forensic"],
                )
        primary_sk, dom_id, dom_name, subagent, triggers = chosen_match
        matched_skills = [primary_sk] + [
            m[0] for m in skill_matches if m[0] != primary_sk
        ]
        all_triggers: List[str] = list(triggers)
        for m in skill_matches:
            for t in m[4]:
                if t not in all_triggers:
                    all_triggers.append(t)
        return {
            "domain_id": dom_id,
            "domain_name": dom_name,
            "primary_skill": primary_sk,
            "matched_skills": matched_skills,
            "native_subagent": subagent,
            "matched_triggers": all_triggers or triggers,
        }

    # 4. Riferimento esplicito a uno script Python nel prompt
    for sc_name, sc_meta in scripts_index.items():
        if sc_name.lower() in scan_lower:
            dom_id = sc_meta.get("domain_id", "DOM-03")
            if is_audit_forensic and dom_id == "DOM-03":
                return {
                    "domain_id": "DOM-04",
                    "domain_name": "AUDIT_DAST_AND_RCA",
                    "primary_skill": "NK-Security-Auditor",
                    "matched_skills": ["NK-Security-Auditor"],
                    "native_subagent": "NK-Security-DAST-Auditor",
                    "matched_triggers": [sc_name, "audit_forensic"],
                }
            dom_meta = domains.get(dom_id, {})
            primary_sk = dom_meta.get("primary_skill", "NK-Python-Async-Builder")
            return {
                "domain_id": dom_id,
                "domain_name": sc_meta.get("domain_name", "BUILD_AND_HEAL"),
                "primary_skill": primary_sk,
                "matched_skills": [primary_sk],
                "native_subagent": _resolve_native_subagent(
                    dom_id, matched_skill=primary_sk, text=scan_lower
                ),
                "matched_triggers": [sc_name],
            }

    # 5. Punteggio keyword tramite domains e intent_dispatch_table (C-speed word boundary)
    clean_text = _sanitize_tetralogia_filenames(scan_lower)
    if is_audit_forensic:
        return {
            "domain_id": "DOM-04",
            "domain_name": "AUDIT_DAST_AND_RCA",
            "primary_skill": "NK-Security-Auditor",
            "matched_skills": ["NK-Security-Auditor"],
            "native_subagent": "NK-Security-DAST-Auditor",
            "matched_triggers": ["audit_forensic"],
        }

    best_dom_id = ""
    best_score = 0
    best_triggers: List[str] = []

    for dom_id, dom_meta in domains.items():
        kws = dom_meta.get("keywords", [])
        hits = [
            kw
            for kw in kws
            if _token_matches_keyword(kw, clean_text, None, min_sub_len=4)
        ]
        if len(hits) > best_score:
            best_score = len(hits)
            best_dom_id = dom_id
            best_triggers = hits

    if best_dom_id and best_score > 0:
        dom_meta = domains[best_dom_id]
        primary_sk = dom_meta.get("primary_skill", "NK-Orchestrator")
        return {
            "domain_id": best_dom_id,
            "domain_name": dom_meta.get("name", ""),
            "primary_skill": primary_sk,
            "matched_skills": [primary_sk],
            "native_subagent": _resolve_native_subagent(
                best_dom_id, matched_skill=primary_sk, text=clean_text
            ),
            "matched_triggers": best_triggers,
        }

    for kw, entry in dispatch_table.items():
        if _token_matches_keyword(kw, clean_text, None, min_sub_len=4):
            dom_id = entry.get("domain_id", "DOM-03")
            primary_sk = entry.get("primary_agent", "NK-Python-Async-Builder")
            return {
                "domain_id": dom_id,
                "domain_name": entry.get("domain_name", "BUILD_AND_HEAL"),
                "primary_skill": primary_sk,
                "matched_skills": [primary_sk],
                "native_subagent": _resolve_native_subagent(
                    dom_id, matched_skill=primary_sk, text=clean_text
                ),
                "matched_triggers": [kw],
            }

    is_disc = any(kw in clean_text for kw in self.DISCOVERY_KEYWORDS)
    if is_disc:
        return {
            "domain_id": "DOM-02",
            "domain_name": "IDEATION_AND_ARCH",
            "primary_skill": "NK-Ideator",
            "matched_skills": ["NK-Ideator"],
            "native_subagent": "NK-Arch-Specifier",
            "matched_triggers": [],
        }
    return {
        "domain_id": "DOM-03",
        "domain_name": "BUILD_AND_HEAL",
        "primary_skill": "NK-Python-Async-Builder",
        "matched_skills": ["NK-Python-Async-Builder"],
        "native_subagent": _resolve_native_subagent(
            "DOM-03", matched_skill="NK-Python-Async-Builder", text=clean_text
        ),
        "matched_triggers": [],
    }

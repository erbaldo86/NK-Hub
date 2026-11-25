"""Motore di interrogazione O(1) multi-entita per domini, skill, script e intent."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.catalog import get_skill_routing_rules
from _internal.nk_registry_indexer.taxonomy import (
    DOMAIN_TAXONOMY,
    SCRIPT_SKILL_MAP,
    SKILL_PRIMARY_SCRIPTS,
)

_DOM_TO_NATIVE: Dict[str, str] = {
    "DOM-01": "Orchestrator-Direct",
    "DOM-02": "NK-Specifier-Agent",
    "DOM-03": "NK-Builder-Agent",
    "DOM-04": "NK-Security-DAST-Auditor",
    "DOM-05": "NK-Scribe-Agent",
}
_TETRALOGY_SANITIZE: Tuple[str, ...] = (
    "implementation_plan.md",
    "concept_map.md",
    "structural_tree.md",
    "repo_map.md",
)
_MODE_A_CUES: Tuple[str, ...] = (
    "allinea 1:1",
    "turno 4",
    "cold review",
    "6 gate",
    "oracolo",
    "multi-file",
    "sast",
    "e2e",
)


def _lookup_domain(
    domains: Dict[str, Any], q_upper: str, query: str, t0: float
) -> Optional[Dict[str, Any]]:
    """Step 1: Lookup diretto per ID o nome del dominio."""
    matched_dom_id: Optional[str] = None
    if q_upper in domains:
        matched_dom_id = domains[q_upper]["domain_id"]
    else:
        for dom_id, dom_meta in domains.items():
            if dom_meta.get("name", "").upper() == q_upper:
                matched_dom_id = dom_id
                break
    if matched_dom_id is None:
        return None
    dom = domains[matched_dom_id]
    return {
        "found": True,
        "match_type": "domain",
        "query": query,
        "domain_id": matched_dom_id,
        "domain_name": dom["name"],
        "primary_skill": dom["primary_skill"],
        "matched_skills": [dom["primary_skill"]],
        "native_subagent": _DOM_TO_NATIVE.get(matched_dom_id, "NK-Builder-Agent"),
        "skills": dom["skills"],
        "scripts": dom["scripts"],
        "result": dom,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
    }


def _lookup_skill(
    indexer: Any, domains: Dict[str, Any], skills_index: Dict[str, Any],
    q_lower: str, query: str, t0: float,
) -> Optional[Dict[str, Any]]:
    """Step 2: Lookup diretto case-insensitive su una skill."""
    for sk_name, sk_meta in skills_index.items():
        if sk_name.lower() == q_lower:
            dom_id = sk_meta["domain_id"]
            dom = domains.get(dom_id, {})
            return {
                "found": True,
                "match_type": "skill",
                "query": query,
                "domain_id": dom_id,
                "domain_name": sk_meta["domain_name"],
                "primary_skill": sk_name,
                "matched_skills": [sk_name],
                "native_subagent": indexer._resolve_skill_native_subagent(sk_name, dom_id),
                "skills": dom.get("skills", [sk_name]),
                "scripts": dom.get("scripts", []),
                "result": sk_meta,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }
    return None


def _resolve_skills_for_native_agent(
    indexer: Any, skills_index: Dict[str, Any], ag_name: str, dom_id: str
) -> List[str]:
    """Raccoglie le skill associate a un sub-agente nativo da skills_index."""
    matched: List[str] = []
    for sk_name, sk_meta in skills_index.items():
        if not isinstance(sk_meta, dict):
            continue
        sk_ag = sk_meta.get("native_subagent") or indexer._resolve_skill_native_subagent(
            sk_name, sk_meta.get("domain_id", dom_id)
        )
        if sk_ag == ag_name:
            matched.append(sk_name)
    return matched


def _lookup_native_agent(
    indexer: Any, domains: Dict[str, Any], skills_index: Dict[str, Any],
    native_agents_index: Dict[str, Any], q_lower: str, query: str, t0: float,
) -> Optional[Dict[str, Any]]:
    """Step 2b: Lookup diretto su Sub-Agente Nativo con risoluzione skill associate."""
    for ag_name, ag_meta in native_agents_index.items():
        if ag_name.lower() != q_lower:
            continue
        dom_id = ag_meta.get("domain_id", "DOM-03")
        dom = domains.get(dom_id, {})
        dom_primary = dom.get("primary_skill", "")
        matched = _resolve_skills_for_native_agent(indexer, skills_index, ag_name, dom_id)
        primary_sk = (dom_primary if dom_primary in matched else matched[0]) if matched else dom_primary
        matched_out = matched or [dom_primary]
        return {
            "found": True,
            "match_type": "native_agent",
            "query": query,
            "domain_id": dom_id,
            "domain_name": ag_meta.get("domain_name", dom.get("name", "")),
            "primary_skill": primary_sk,
            "matched_skills": matched_out,
            "native_subagent": ag_name,
            "skills": dom.get("skills", []),
            "scripts": dom.get("scripts", []),
            "result": ag_meta,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
    return None


def _lookup_script(
    indexer: Any, domains: Dict[str, Any], scripts_index: Dict[str, Any],
    q_lower: str, query: str, t0: float,
) -> Optional[Dict[str, Any]]:
    """Step 3: Lookup diretto su Script o Schema con mapping skill/sub-agente."""
    sc_candidate = q_lower if q_lower.endswith(".py") else f"{q_lower}.py"
    for sc_name, sc_meta in scripts_index.items():
        sc_low = sc_name.lower()
        sc_base = sc_low.split("/")[-1]
        if sc_low in (q_lower, sc_candidate) or sc_base in (q_lower, sc_candidate):
            dom_id = sc_meta["domain_id"]
            dom = domains.get(dom_id, {})
            sc_key_base = sc_name.split("/")[-1]
            primary_sk = (
                SCRIPT_SKILL_MAP.get(sc_name)
                or SCRIPT_SKILL_MAP.get(sc_key_base)
                or dom.get("primary_skill", "")
            )
            return {
                "found": True,
                "match_type": "script",
                "query": query,
                "domain_id": dom_id,
                "domain_name": sc_meta["domain_name"],
                "primary_skill": primary_sk,
                "matched_skills": [primary_sk],
                "native_subagent": indexer._resolve_skill_native_subagent(primary_sk, dom_id),
                "skills": dom.get("skills", []),
                "scripts": [sc_name],
                "cli_flags": sc_meta.get("cli_flags", []),
                "result": sc_meta,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }
    return None


def _build_dispatch_intent_result(
    indexer: Any, domains: Dict[str, Any], entry: Dict[str, Any], query: str, t0: float
) -> Dict[str, Any]:
    """Costruisce la risposta di dispatch risolvendo sub-agente nativo e script skill."""
    dom_id = entry["domain_id"]
    dom = domains.get(dom_id, {})
    primary_sk = entry["primary_agent"]
    resolved_scripts = (
        entry.get("scripts")
        or list(SKILL_PRIMARY_SCRIPTS.get(primary_sk, ()))
        or dom.get("scripts", DOMAIN_TAXONOMY.get(dom_id, {}).get("scripts", []))
    )
    scripts_list = list(resolved_scripts)
    return {
        "found": True,
        "match_type": "intent",
        "query": query,
        "domain_id": dom_id,
        "domain_name": entry["domain_name"],
        "primary_skill": primary_sk,
        "matched_skills": [primary_sk],
        "native_subagent": indexer._resolve_skill_native_subagent(primary_sk, dom_id),
        "recommended_mode": entry.get("recommended_mode", "mode_c"),
        "skills": dom.get("skills", []),
        "scripts": scripts_list,
        "result": {**entry, "scripts": scripts_list},
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
    }


def _count_rule_keyword_hits(
    kws: Tuple[str, ...], q_lower: str, tokens_raw: Set[str]
) -> int:
    """Conta quante keyword della regola granulare corrispondono a q_lower."""
    hit_count = 0
    for kw in kws:
        if " " in kw or "." in kw or "/" in kw or "-" in kw:
            if kw in q_lower:
                hit_count += 1
        elif kw in tokens_raw or (len(kw) >= 5 and kw in q_lower):
            hit_count += 1
    return hit_count


def _infer_granular_mode(primary_sk: str, q_lower: str) -> str:
    """Determina la modalita operativa raccomandata per i match granulari."""
    if primary_sk == "NK-Ideator" or (
        any(dk in q_lower for dk in ("read-only", "readonly", "stato dell'arte"))
        and not any(wk in q_lower for wk in (".staging", "refactoring", "implementa"))
    ):
        return "mode_d"
    if any(ak in q_lower for ak in _MODE_A_CUES):
        return "mode_a"
    if any(bk in q_lower for bk in ("sbfl", "ochiai", "causa radice", "rca")):
        return "mode_b"
    return "mode_c"


def _lookup_granular_skills(
    indexer: Any, domains: Dict[str, Any], q_lower: str, query: str, t0: float
) -> Optional[Dict[str, Any]]:
    """Step 4b: Regole granulari multi-skill per prompt testuali liberi o ibridi."""
    tokens_raw = set(re.findall(r"[a-z0-9_]+", q_lower))
    skill_matches: List[Tuple[int, int, str, str, str, str]] = []
    for idx, (sk_name, dom_id, dom_name, subagent, kws) in enumerate(
        get_skill_routing_rules(indexer.workspace_root)
    ):
        hit_count = _count_rule_keyword_hits(kws, q_lower, tokens_raw)
        if hit_count > 0:
            skill_matches.append((hit_count, -idx, sk_name, dom_id, dom_name, subagent))

    if not skill_matches:
        return None
    skill_matches.sort(reverse=True)
    _, _, primary_sk, dom_id, dom_name, subagent = skill_matches[0]
    matched_skills = [m[2] for m in skill_matches]
    dom = domains.get(dom_id, {})
    rec_mode = _infer_granular_mode(primary_sk, q_lower)
    return {
        "found": True,
        "match_type": "intent",
        "query": query,
        "domain_id": dom_id,
        "domain_name": dom_name,
        "primary_skill": primary_sk,
        "matched_skills": matched_skills,
        "native_subagent": subagent,
        "recommended_mode": rec_mode,
        "skills": dom.get("skills", matched_skills),
        "scripts": dom.get("scripts", []),
        "result": {
            "domain_id": dom_id,
            "domain_name": dom_name,
            "primary_agent": primary_sk,
            "matched_skills": matched_skills,
            "recommended_mode": rec_mode,
        },
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
    }


def _lookup_dispatch_fallback(
    indexer: Any, domains: Dict[str, Any],
    dispatch_table: Dict[str, Dict[str, Any]], q_lower: str, query: str, t0: float,
) -> Optional[Dict[str, Any]]:
    """Step 4c: Fallback su intent_dispatch_table con sanitizzazione nomi file Pentad."""
    clean_q = q_lower
    for fname in _TETRALOGY_SANITIZE:
        clean_q = clean_q.replace(fname, " ")
    tokens = set(re.findall(r"[a-z0-9_]+", clean_q))
    best_kw = ""
    best_entry: Optional[Dict[str, Any]] = None
    for kw, entry in dispatch_table.items():
        if (kw in tokens or (len(kw) >= 4 and kw in clean_q)) and len(kw) > len(best_kw):
            best_kw = kw
            best_entry = entry
    if best_entry is None:
        return None
    return _build_dispatch_intent_result(indexer, domains, best_entry, query, t0)


def _lookup_direct_entity(
    indexer: Any, manifest: Dict[str, Any], q_upper: str, q_lower: str, query: str, t0: float
) -> Optional[Dict[str, Any]]:
    """Esegue in cascata i lookup diretti per dominio, skill, native_agent e script."""
    domains = manifest.get("domains", {})
    skills_index = manifest.get("skills_index", {})
    hit = _lookup_domain(domains, q_upper, query, t0)
    if hit is not None:
        return hit
    hit = _lookup_skill(indexer, domains, skills_index, q_lower, query, t0)
    if hit is not None:
        return hit
    hit = _lookup_native_agent(
        indexer, domains, skills_index, manifest["native_agents_index"], q_lower, query, t0
    )
    if hit is not None:
        return hit
    return _lookup_script(indexer, domains, manifest.get("scripts_index", {}), q_lower, query, t0)


def _build_fallback_result(domains: Dict[str, Any], query: str, t0: float) -> Dict[str, Any]:
    """Restituisce il payload di fallback predefinito verso DOM-01."""
    return {
        "found": False,
        "match_type": "fallback",
        "query": query,
        "domain_id": "DOM-01",
        "domain_name": "GOV_AND_ROUTING",
        "primary_skill": "NK-Orchestrator",
        "matched_skills": ["NK-Orchestrator"],
        "native_subagent": "Orchestrator-Direct",
        "skills": domains.get("DOM-01", {}).get("skills", []),
        "scripts": domains.get("DOM-01", {}).get("scripts", []),
        "result": {},
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
    }


def lookup_impl(self, query: str) -> Dict[str, Any]:
    """Esegue una ricerca O(1) nel manifesto per dominio, skill, native_agent, script o intento."""
    t0 = time.perf_counter()
    manifest = self.load_manifest()
    if manifest is None:
        manifest = self.build_manifest()

    q_clean = (query or "").strip()
    q_upper, q_lower = q_clean.upper(), q_clean.lower()
    native_agents = manifest.get("native_agents_index")
    if not isinstance(native_agents, dict) or not native_agents:
        manifest["native_agents_index"] = self.scan_native_agents()

    hit = _lookup_direct_entity(self, manifest, q_upper, q_lower, query, t0)
    if hit is not None:
        return hit
    domains = manifest.get("domains", {})
    dispatch_table = manifest.get("intent_dispatch_table", {})
    if q_lower in dispatch_table:
        return _build_dispatch_intent_result(self, domains, dispatch_table[q_lower], query, t0)
    hit = _lookup_granular_skills(self, domains, q_lower, query, t0)
    if hit is not None:
        return hit
    hit = _lookup_dispatch_fallback(self, domains, dispatch_table, q_lower, query, t0)
    if hit is not None:
        return hit
    return _build_fallback_result(domains, query, t0)

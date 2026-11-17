"""Motore di interrogazione O(1) multi-entita per domini, skill, script e intent."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.catalog import get_skill_routing_rules
from _internal.nk_registry_indexer.taxonomy import DOMAIN_TAXONOMY


def lookup_impl(self, query: str) -> Dict[str, Any]:
    """Esegue una ricerca O(1) nel manifesto per dominio, skill, native_agent, script o intento."""
    t0 = time.perf_counter()
    manifest = self.load_manifest()
    if manifest is None:
        manifest = self.build_manifest()

    q_clean = (query or "").strip()
    q_upper = q_clean.upper()
    q_lower = q_clean.lower()

    domains = manifest.get("domains", {})
    skills_index = manifest.get("skills_index", {})
    scripts_index = manifest.get("scripts_index", {})
    native_agents_index = manifest.get("native_agents_index")
    if not isinstance(native_agents_index, dict) or not native_agents_index:
        native_agents_index = self.scan_native_agents()
        manifest["native_agents_index"] = native_agents_index
    dispatch_table = manifest.get("intent_dispatch_table", {})

    dom_to_native = {
        "DOM-01": "Orchestrator-Direct",
        "DOM-02": "NK-Specifier-Agent",
        "DOM-03": "NK-Builder-Agent",
        "DOM-04": "NK-Security-DAST-Auditor",
        "DOM-05": "NK-Scribe-Agent",
    }
    rsi_skills = {"NK-Oracle-Evaluator"}

    # 1. Lookup diretto su ID Dominio (es. DOM-01) o nome Dominio
    if q_upper in domains:
        dom = domains[q_upper]
        dom_id = dom["domain_id"]
        return {
            "found": True,
            "match_type": "domain",
            "query": query,
            "domain_id": dom_id,
            "domain_name": dom["name"],
            "primary_skill": dom["primary_skill"],
            "matched_skills": [dom["primary_skill"]],
            "native_subagent": dom_to_native.get(dom_id, "NK-Builder-Agent"),
            "skills": dom["skills"],
            "scripts": dom["scripts"],
            "result": dom,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }

    for dom_id, dom in domains.items():
        if dom.get("name", "").upper() == q_upper:
            return {
                "found": True,
                "match_type": "domain",
                "query": query,
                "domain_id": dom_id,
                "domain_name": dom["name"],
                "primary_skill": dom["primary_skill"],
                "matched_skills": [dom["primary_skill"]],
                "native_subagent": dom_to_native.get(dom_id, "NK-Builder-Agent"),
                "skills": dom["skills"],
                "scripts": dom["scripts"],
                "result": dom,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

    # 2. Lookup diretto su Skill (case-insensitive)
    for sk_name, sk_meta in skills_index.items():
        if sk_name.lower() == q_lower:
            dom_id = sk_meta["domain_id"]
            dom = domains.get(dom_id, {})
            native_ag = self._resolve_skill_native_subagent(sk_name, dom_id)
            return {
                "found": True,
                "match_type": "skill",
                "query": query,
                "domain_id": dom_id,
                "domain_name": sk_meta["domain_name"],
                "primary_skill": sk_name,
                "matched_skills": [sk_name],
                "native_subagent": native_ag,
                "skills": dom.get("skills", [sk_name]),
                "scripts": dom.get("scripts", []),
                "result": sk_meta,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

    # 2b. Lookup diretto su Sub-Agente Nativo (native_agents_index)
    for ag_name, ag_meta in native_agents_index.items():
        if ag_name.lower() == q_lower:
            dom_id = ag_meta.get("domain_id", "DOM-03")
            dom = domains.get(dom_id, {})
            return {
                "found": True,
                "match_type": "native_agent",
                "query": query,
                "domain_id": dom_id,
                "domain_name": ag_meta.get("domain_name", dom.get("name", "")),
                "primary_skill": dom.get("primary_skill", ""),
                "matched_skills": [dom.get("primary_skill", "")],
                "native_subagent": ag_name,
                "skills": dom.get("skills", []),
                "scripts": dom.get("scripts", []),
                "result": ag_meta,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

    # 3. Lookup diretto su Script o Schema (con o senza .py / schemas/)
    sc_candidate = q_lower if q_lower.endswith(".py") else f"{q_lower}.py"
    for sc_name, sc_meta in scripts_index.items():
        sc_low = sc_name.lower()
        sc_base = sc_low.split("/")[-1]
        if sc_low in (q_lower, sc_candidate) or sc_base in (q_lower, sc_candidate):
            dom_id = sc_meta["domain_id"]
            dom = domains.get(dom_id, {})
            return {
                "found": True,
                "match_type": "script",
                "query": query,
                "domain_id": dom_id,
                "domain_name": sc_meta["domain_name"],
                "primary_skill": dom.get("primary_skill", ""),
                "matched_skills": [dom.get("primary_skill", "")],
                "native_subagent": dom_to_native.get(dom_id, "NK-Builder-Agent"),
                "skills": dom.get("skills", []),
                "scripts": [sc_name],
                "cli_flags": sc_meta.get("cli_flags", []),
                "result": sc_meta,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

    # 4a. Lookup diretto su keyword singola in intent_dispatch_table
    if q_lower in dispatch_table:
        entry = dispatch_table[q_lower]
        dom_id = entry["domain_id"]
        dom = domains.get(dom_id, {})
        primary_sk = entry["primary_agent"]
        resolved_scripts = entry.get("scripts")
        if resolved_scripts is None:
            resolved_scripts = dom.get(
                "scripts", DOMAIN_TAXONOMY.get(dom_id, {}).get("scripts", [])
            )
        native_ag = (
            "NK-RSI-Auditor"
            if primary_sk in rsi_skills
            else str(
                (skills_index.get(primary_sk) or {}).get("native_subagent")
                or dom_to_native.get(dom_id, "NK-Builder-Agent")
            )
        )
        return {
            "found": True,
            "match_type": "intent",
            "query": query,
            "domain_id": dom_id,
            "domain_name": entry["domain_name"],
            "primary_skill": primary_sk,
            "matched_skills": [primary_sk],
            "native_subagent": native_ag,
            "recommended_mode": entry["recommended_mode"],
            "skills": dom.get("skills", []),
            "scripts": list(resolved_scripts),
            "result": {**entry, "scripts": list(resolved_scripts)},
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }

    # 4b. Regole granulari multi-skill per prompt testuali liberi o ibridi
    tokens_raw = set(re.findall(r"[a-z0-9_]+", q_lower))
    skill_matches: List[Tuple[int, int, str, str, str, str]] = []
    skill_rules = get_skill_routing_rules(self.workspace_root)
    for idx, (sk_name, dom_id, dom_name, subagent, kws) in enumerate(skill_rules):
        hit_count = 0
        for kw in kws:
            if " " in kw or "." in kw or "/" in kw or "-" in kw:
                if kw in q_lower:
                    hit_count += 1
            elif kw in tokens_raw or (len(kw) >= 5 and kw in q_lower):
                hit_count += 1
        if hit_count > 0:
            skill_matches.append((hit_count, -idx, sk_name, dom_id, dom_name, subagent))

    if skill_matches:
        skill_matches.sort(reverse=True)
        _, _, primary_sk, dom_id, dom_name, subagent = skill_matches[0]
        matched_skills = [m[2] for m in skill_matches]
        dom = domains.get(dom_id, {})
        if primary_sk == "NK-Ideator" or (
            any(dk in q_lower for dk in ("read-only", "readonly", "stato dell'arte"))
            and not any(wk in q_lower for wk in (".staging", "refactoring", "implementa"))
        ):
            rec_mode = "mode_d"
        elif any(
            ak in q_lower
            for ak in (
                "allinea 1:1",
                "turno 4",
                "cold review",
                "6 gate",
                "oracolo",
                "multi-file",
                "sast",
                "e2e",
            )
        ):
            rec_mode = "mode_a"
        elif any(bk in q_lower for bk in ("sbfl", "ochiai", "causa radice", "rca")):
            rec_mode = "mode_b"
        else:
            rec_mode = "mode_c"

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

    # 4c. Fallback su intent_dispatch_table (con sanitizzazione nomi file Pentad)
    clean_q = q_lower
    for fname in ("implementation_plan.md", "concept_map.md", "structural_tree.md", "repo_map.md"):
        clean_q = clean_q.replace(fname, " ")
    tokens = set(re.findall(r"[a-z0-9_]+", clean_q))
    best_kw = ""
    best_entry: Optional[Dict[str, Any]] = None
    for kw, entry in dispatch_table.items():
        if kw in tokens or (len(kw) >= 4 and kw in clean_q):
            if len(kw) > len(best_kw):
                best_kw = kw
                best_entry = entry

    if best_entry is not None:
        dom_id = best_entry["domain_id"]
        dom = domains.get(dom_id, {})
        primary_sk = best_entry["primary_agent"]
        resolved_scripts = best_entry.get("scripts")
        if resolved_scripts is None:
            resolved_scripts = dom.get(
                "scripts", DOMAIN_TAXONOMY.get(dom_id, {}).get("scripts", [])
            )
        return {
            "found": True,
            "match_type": "intent",
            "query": query,
            "domain_id": dom_id,
            "domain_name": best_entry["domain_name"],
            "primary_skill": primary_sk,
            "matched_skills": [primary_sk],
            "native_subagent": dom_to_native.get(dom_id, "NK-Builder-Agent"),
            "recommended_mode": best_entry["recommended_mode"],
            "skills": dom.get("skills", []),
            "scripts": list(resolved_scripts),
            "result": {**best_entry, "scripts": list(resolved_scripts)},
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }

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

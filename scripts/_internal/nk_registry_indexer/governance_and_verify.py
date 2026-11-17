"""Verifica SHA-256 O(1) e audit governance GT-14/CRIT-01 sul manifesto."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Set

from _internal.nk_registry_indexer.governance_gt14 import (
    audit_gt14_crit01_entries_impl,  # noqa: F401
    sha256_matches_eol_normalized_impl,  # noqa: F401
    verify_gt14_crit01_governance_impl,  # noqa: F401
)
from _internal.nk_registry_indexer.taxonomy import _DEFAULT_WORKSPACE_ROOT


def verify_impl(self) -> Dict[str, Any]:
    """Verifica gli hash SHA-256 su disco e le guardie GT-14, RULE-01 e Runtime 2.0 in meno di 30 ms."""
    t0 = time.perf_counter()
    if (
        self.workspace_root == _DEFAULT_WORKSPACE_ROOT
        and getattr(self, "_last_verify_cache", None) is not None
    ):
        cached_ts, cached_res = self._last_verify_cache  # type: ignore[misc]
        if (t0 - cached_ts) < 2.0:
            fast_res = dict(cached_res)
            fast_res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            return fast_res
    prev_cache_size = len(type(self)._HASH_CACHE)
    manifest = self.load_manifest()
    tetralogy_info = self.resolve_tetralogy_files(self.workspace_root)
    if manifest is None:
        return {
            "status": "MISSING_MANIFEST",
            "passed": False,
            "genome_dir": tetralogy_info["genome_dir"],
            "is_legacy_genome": tetralogy_info["is_legacy_genome"],
            "legacy_warning": tetralogy_info["warning"],
            "unindexed_files": [],
            "issues": ["nk_registry_manifest.json non trovato in staging o root."],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    issues: List[str] = []
    required_keys = (
        "version",
        "domains",
        "skills_index",
        "scripts_index",
        "intent_dispatch_table",
        "global_hygiene_profile",
    )
    for req_key in required_keys:
        if req_key not in manifest:
            issues.append(f"Chiave obbligatoria mancante nel manifesto: {req_key}")

    domains = manifest.get("domains", {})
    for expected_dom in ("DOM-01", "DOM-02", "DOM-03", "DOM-04", "DOM-05"):
        if expected_dom not in domains:
            issues.append(f"Dominio tassonomico mancante: {expected_dom}")

    dispatch_tbl = manifest.get("intent_dispatch_table", {})
    if isinstance(dispatch_tbl, dict):
        for kw_key, kw_entry in dispatch_tbl.items():
            if not isinstance(kw_entry, dict):
                issues.append(f"Voce intent_dispatch_table non valida: {kw_key}")
                continue
            kw_dom = kw_entry.get("domain_id", "")
            resolved_kw_scripts = kw_entry.get("scripts")
            if resolved_kw_scripts is None:
                resolved_kw_scripts = domains.get(kw_dom, {}).get("scripts")
            if kw_dom not in domains or not isinstance(resolved_kw_scripts, list):
                issues.append(
                    f"Impossibile risolvere scripts per keyword '{kw_key}' (dominio '{kw_dom}')"
                )

    skill_map = self._collect_priority_skills()
    manifest_skills = manifest.get("skills_index", {})
    unchanged_skills: Set[str] = set()
    if set(skill_map.keys()) != set(manifest_skills.keys()):
        issues.append(
            f"Conteggio o nomi skill disallineati: atteso {len(skill_map)}, trovato {len(manifest_skills)}"
        )
    else:
        for sk_name, (resolved, st) in skill_map.items():
            recorded_sha = manifest_skills.get(sk_name, {}).get("sha256", "")
            ckey = (str(resolved), st.st_mtime_ns, st.st_size)
            live_sha = (
                type(self)._HASH_CACHE[ckey]
                if st.st_size > 256 and ckey in type(self)._HASH_CACHE
                else self._compute_sha256(resolved)
            )
            if not self._sha256_matches_eol_normalized(resolved, live_sha, recorded_sha):
                issues.append(f"Drift SHA-256 rilevato sulla skill: {sk_name}")
            else:
                unchanged_skills.add(sk_name)

    script_map = self._collect_priority_scripts()
    manifest_scripts = manifest.get("scripts_index", {})
    if set(script_map.keys()) != set(manifest_scripts.keys()):
        issues.append(
            f"Conteggio o nomi script disallineati: atteso {len(script_map)}, trovato {len(manifest_scripts)}"
        )
    else:
        for sc_name, (resolved, st) in script_map.items():
            recorded_sha = manifest_scripts.get(sc_name, {}).get("sha256", "")
            ckey = (str(resolved), st.st_mtime_ns, st.st_size)
            live_sha = (
                type(self)._HASH_CACHE[ckey]
                if st.st_size > 256 and ckey in type(self)._HASH_CACHE
                else self._compute_sha256(resolved)
            )
            if not self._sha256_matches_eol_normalized(resolved, live_sha, recorded_sha):
                issues.append(f"Drift SHA-256 rilevato sullo script: {sc_name}")

    agent_map = self._collect_priority_native_agents()
    manifest_agents = manifest.get("native_agents_index", {})
    unchanged_agents: Set[str] = set()
    if "native_agents_index" in manifest:
        if set(agent_map.keys()) != set(manifest_agents.keys()):
            issues.append(
                f"Conteggio o nomi native agents disallineati: atteso {len(manifest_agents)}, trovato {len(agent_map)}"
            )
        else:
            for ag_name, (resolved, st) in agent_map.items():
                recorded_sha = manifest_agents.get(ag_name, {}).get("sha256", "")
                ckey = (str(resolved), st.st_mtime_ns, st.st_size)
                live_sha = (
                    type(self)._HASH_CACHE[ckey]
                    if st.st_size > 256 and ckey in type(self)._HASH_CACHE
                    else self._compute_sha256(resolved)
                )
                if not self._sha256_matches_eol_normalized(resolved, live_sha, recorded_sha):
                    issues.append(
                        f"Drift SHA-256 rilevato sul sub-agente nativo: {ag_name}"
                    )
                else:
                    unchanged_agents.add(ag_name)

    nk_gate_rel = Path(".agents") / "plugins" / "nk-gate"
    if (self.stage_dir / nk_gate_rel / "plugin.json").is_file() or (
        self.workspace_root / nk_gate_rel / "plugin.json"
    ).is_file():
        for ag_name, (src_ag, _st) in agent_map.items():
            stg_ag = self.stage_dir / nk_gate_rel / "agents" / f"{ag_name}.md"
            prod_ag = self.workspace_root / nk_gate_rel / "agents" / f"{ag_name}.md"
            dst_ag = stg_ag if stg_ag.is_file() else prod_ag
            if not dst_ag.is_file():
                issues.append(f"Mirror nk-gate agents/{ag_name}.md mancante.")
            elif dst_ag.read_bytes().replace(b"\r\n", b"\n") != src_ag.read_bytes().replace(b"\r\n", b"\n"):
                issues.append(f"Mirror nk-gate agents/{ag_name}.md disallineato.")

        stg_rule_src = self.stage_dir / ".agents" / "rules" / "anti_crash_rules.md"
        prod_rule_src = self.workspace_root / ".agents" / "rules" / "anti_crash_rules.md"
        src_rule = stg_rule_src if stg_rule_src.is_file() else prod_rule_src
        if src_rule.is_file():
            stg_rule_dst = self.stage_dir / nk_gate_rel / "rules" / "AGENTS.md"
            prod_rule_dst = self.workspace_root / nk_gate_rel / "rules" / "AGENTS.md"
            dst_rule = stg_rule_dst if stg_rule_dst.is_file() else prod_rule_dst
            if not dst_rule.is_file():
                issues.append("Mirror nk-gate rules/AGENTS.md mancante.")
            else:
                dst_text = dst_rule.read_text(encoding="utf-8", errors="replace")
                raw_src = src_rule.read_text(encoding="utf-8", errors="replace")
                if raw_src.startswith("---"):
                    lines = raw_src.splitlines(keepends=True)
                    for idx in range(1, len(lines)):
                        if lines[idx].strip() == "---":
                            raw_src = "".join(lines[idx + 1 :]).lstrip("\r\n")
                            break
                if dst_text.lstrip().startswith("---"):
                    issues.append("Mirror nk-gate rules/AGENTS.md contiene frontmatter YAML.")
                elif dst_text.replace("\r\n", "\n") != raw_src.replace("\r\n", "\n"):
                    issues.append("Mirror nk-gate rules/AGENTS.md disallineato.")

    issues.extend(
        self._audit_gt14_crit01_entries(
            agent_map=agent_map,
            skill_map=skill_map,
            manifest_agents=manifest_agents,
            manifest_skills=manifest_skills,
            unchanged_agents=unchanged_agents,
            unchanged_skills=unchanged_skills,
        )
    )

    if len(type(self)._HASH_CACHE) != prev_cache_size:
        self._save_persistent_hash_cache()
    passed = len(issues) == 0
    warnings: List[str] = []
    if tetralogy_info["warning"]:
        warnings.append(str(tetralogy_info["warning"]))
    res = {
        "status": "VALID" if passed else "DRIFT_DETECTED",
        "passed": passed,
        "genome_dir": tetralogy_info["genome_dir"],
        "is_legacy_genome": tetralogy_info["is_legacy_genome"],
        "legacy_warning": tetralogy_info["warning"],
        "warnings": warnings,
        "total_domains": len(domains),
        "total_skills": len(manifest_skills),
        "total_scripts": len(manifest_scripts),
        "total_native_agents": len(manifest_agents),
        "unindexed_files": sorted(set(script_map.keys()) - set(manifest_scripts.keys())),
        "issues": issues,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
    }
    if passed and self.workspace_root == _DEFAULT_WORKSPACE_ROOT:
        self._last_verify_cache = (time.perf_counter(), dict(res))
    return res

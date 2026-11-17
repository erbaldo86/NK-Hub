"""Filtro read-only delle skill globali, profilo igiene e intent dispatch table."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Set

from _internal.nk_registry_indexer.hygiene_paths import (
    apply_global_filter_impl,  # noqa: F401
    is_within_dir_impl,  # noqa: F401
)
from _internal.nk_registry_indexer.taxonomy import (
    DEFAULT_GLOBAL_CONFIG_DIR,
    DOMAIN_TAXONOMY,
)


def scan_global_hygiene_profile_impl(
    self, workspace_skills_count: int
) -> Dict[str, Any]:
    """Scansiona il profilo globale ~/.gemini/config distinguendo skill attive e disabilitate."""
    is_default_global = (
        self.global_config_dir.resolve() == DEFAULT_GLOBAL_CONFIG_DIR.resolve()
    )
    readonly_flag = bool(getattr(self, "_readonly_filter_applied", False))
    if (
        is_default_global
        and not readonly_flag
        and type(self)._HYGIENE_CACHE is not None
    ):
        cached_ts, cached_dir, cached_ws_cnt, cached_prof = type(self)._HYGIENE_CACHE
        if (
            (time.perf_counter() - cached_ts) < 15.0
            and cached_dir == str(self.global_config_dir)
            and cached_ws_cnt == workspace_skills_count
        ):
            return dict(cached_prof)

    installed_skills: List[str] = []
    active_skills: List[str] = []
    external_sources: Set[str] = set()
    disabled_plugins: Set[str] = set()
    if getattr(self, "_readonly_filter_applied", False):
        disabled_plugins.update(
            (
                "android-cli-plugin",
                "science",
                "gcp-data-cloud-plugin",
                "dev-utilities-plugin",
            )
        )

    if self.global_config_dir.exists() and self.global_config_dir.is_dir():
        cfg_path = self.global_config_dir / "config.json"
        if cfg_path.exists():
            try:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(cfg_data, dict):
                    plugins_dict = cfg_data.get("plugins", {})
                    if isinstance(plugins_dict, dict):
                        for p_name, p_meta in plugins_dict.items():
                            if isinstance(p_meta, dict) and p_meta.get("enabled") is False:
                                disabled_plugins.add(p_name)
            except (OSError, json.JSONDecodeError):
                pass

        for p_json in self.global_config_dir.glob("plugins/*/plugin.json"):
            try:
                p_meta = json.loads(p_json.read_text(encoding="utf-8"))
                if isinstance(p_meta, dict) and p_meta.get("disabled") is True:
                    disabled_plugins.add(p_json.parent.name)
            except (OSError, json.JSONDecodeError):
                pass

        targeted_globs = (
            list(self.global_config_dir.glob("skills/*/SKILL.md"))
            + list(self.global_config_dir.glob("plugins/*/skills/*/SKILL.md"))
            + list(self.global_config_dir.glob("plugins/*/skills/SKILL.md"))
        )
        seen_rels: Set[str] = set()
        virtual_filtered_skills = (
            set(self.GCP_DATA_SKILLS) | set(self.DEV_UTILITY_SKILLS)
            if getattr(self, "_readonly_filter_applied", False)
            else set()
        )
        for sk_md in sorted(targeted_globs):
            try:
                rel = sk_md.relative_to(self.global_config_dir).as_posix()
            except ValueError:
                rel = sk_md.as_posix()
            if rel in seen_rels:
                continue
            seen_rels.add(rel)
            installed_skills.append(rel)

            parts = rel.split("/")
            if len(parts) >= 2:
                source_id = (
                    f"{parts[0]}/{parts[1]}" if parts[0] == "plugins" else parts[0]
                )
                external_sources.add(source_id)
                if parts[0] == "plugins" and parts[1] in disabled_plugins:
                    continue
                if parts[0] == "skills" and parts[1] in virtual_filtered_skills:
                    continue
            active_skills.append(rel)

    installed_ext_count = len(installed_skills)
    active_ext_count = len(active_skills)
    disabled_ext_count = installed_ext_count - active_ext_count
    total_flat = workspace_skills_count + active_ext_count
    effective_filtered = (
        disabled_ext_count if disabled_ext_count > 0 else installed_ext_count
    )
    estimated_tokens = (
        7042 if effective_filtered == 61 else effective_filtered * 115
    )

    portable_cfg_path = (
        "~/.gemini/config"
        if is_default_global
        else self.global_config_dir.as_posix()
    )
    res_prof = {
        "config_path": portable_cfg_path,
        "config_exists": self.global_config_dir.exists(),
        "workspace_skills_count": workspace_skills_count,
        "external_skills_count": active_ext_count,
        "installed_external_skills_count": installed_ext_count,
        "active_external_skills_count": active_ext_count,
        "disabled_external_skills_count": disabled_ext_count,
        "total_flat_skills": total_flat,
        "context_pollution_detected": active_ext_count > 0,
        "external_sources": sorted(external_sources),
        "disabled_plugins": sorted(disabled_plugins),
        "recommended_isolation_config": {
            "isolation_mode": "WORKSPACE_O1_MANIFEST_ONLY",
            "disable_global_plugins": True,
            "disable_external_gcp_skills": True,
            "disabled_sources": sorted(external_sources),
            "estimated_token_savings": estimated_tokens,
        },
    }
    if is_default_global and not readonly_flag:
        type(self)._HYGIENE_CACHE = (
            time.perf_counter(),
            str(self.global_config_dir),
            workspace_skills_count,
            dict(res_prof),
        )
    return res_prof


def build_intent_dispatch_table_impl(self) -> Dict[str, Dict[str, Any]]:
    """Costruisce la tabella O(1) di dispatch per dominio e per singola skill."""
    from _internal.nk_common.catalog import (
        get_skill_mode_map,
        get_skill_routing_rules,
    )

    valid_modes = ("mode_a", "mode_b", "mode_c", "mode_d")
    dispatch_table: Dict[str, Dict[str, Any]] = {}
    mode_map = {
        "DOM-01": "mode_a",
        "DOM-02": "mode_d",
        "DOM-03": "mode_c",
        "DOM-04": "mode_d",
        "DOM-05": "mode_c",
    }
    mode_by_skill = get_skill_mode_map(self.workspace_root)

    for dom_id, dom_meta in DOMAIN_TAXONOMY.items():
        for kw in dom_meta["keywords"]:
            dispatch_table[kw.lower()] = {
                "domain_id": dom_id,
                "domain_name": dom_meta["name"],
                "primary_agent": dom_meta["primary_skill"],
                "recommended_mode": mode_map.get(dom_id, "mode_c"),
            }
    for sk_name, dom_id, dom_name, _subagent, kws in get_skill_routing_rules(self.workspace_root):
        rec_mode = mode_by_skill.get(sk_name) or mode_map.get(dom_id, "mode_c")
        if rec_mode not in valid_modes:
            rec_mode = mode_map.get(dom_id, "mode_c")
        for kw in kws:
            kw_low = kw.lower()
            if kw_low in dispatch_table or len(kw_low) <= 12:
                dispatch_table[kw_low] = {
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "primary_agent": sk_name,
                    "recommended_mode": rec_mode,
                }
    return dispatch_table

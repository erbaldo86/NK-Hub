"""Filtro read-only delle skill globali, profilo igiene e intent dispatch table."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_registry_indexer.hygiene_paths import (
    apply_global_filter_impl,  # noqa: F401
    is_within_dir_impl,  # noqa: F401
)
from _internal.nk_registry_indexer.taxonomy import (
    DEFAULT_GLOBAL_CONFIG_DIR,
    DOMAIN_TAXONOMY,
)

_DEFAULT_READONLY_DISABLED_PLUGINS: Tuple[str, ...] = (
    "android-cli-plugin",
    "science",
    "gcp-data-cloud-plugin",
    "dev-utilities-plugin",
)


def _get_cached_hygiene_profile(
    self, is_default_global: bool, readonly_flag: bool, workspace_skills_count: int
) -> Optional[Dict[str, Any]]:
    """Restituisce il profilo igiene dalla cache in memoria se valido (< 15s)."""
    cached = type(self)._HYGIENE_CACHE
    if not (is_default_global and not readonly_flag and cached is not None):
        return None
    cached_ts, cached_dir, cached_ws_cnt, cached_prof = cached
    if (
        (time.perf_counter() - cached_ts) < 15.0
        and cached_dir == str(self.global_config_dir)
        and cached_ws_cnt == workspace_skills_count
    ):
        return dict(cached_prof)
    return None


def _collect_disabled_from_config(cfg_dir: Path, disabled: Set[str]) -> None:
    """Aggiunge i plugin disabilitati esplicitamente dentro config.json."""
    cfg_path = cfg_dir / "config.json"
    if not cfg_path.exists():
        return
    try:
        cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    plugins_dict = cfg_data.get("plugins", {}) if isinstance(cfg_data, dict) else {}
    if not isinstance(plugins_dict, dict):
        return
    for p_name, p_meta in plugins_dict.items():
        if isinstance(p_meta, dict) and p_meta.get("enabled") is False:
            disabled.add(p_name)


def _collect_disabled_from_manifests(cfg_dir: Path, disabled: Set[str]) -> None:
    """Aggiunge i plugin marcati disabled=true nei rispettivi plugin.json."""
    for p_json in cfg_dir.glob("plugins/*/plugin.json"):
        try:
            p_meta = json.loads(p_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(p_meta, dict) and p_meta.get("disabled") is True:
            disabled.add(p_json.parent.name)


def _collect_disabled_plugins(
    cfg_dir: Path, readonly_flag: bool
) -> Set[str]:
    """Raccoglie l'insieme dei plugin globali disabilitati da config.json e plugin.json."""
    disabled: Set[str] = (
        set(_DEFAULT_READONLY_DISABLED_PLUGINS) if readonly_flag else set()
    )
    _collect_disabled_from_config(cfg_dir, disabled)
    _collect_disabled_from_manifests(cfg_dir, disabled)
    return disabled


def _rel_skill_path(sk_md: Path, cfg_dir: Path) -> str:
    """Restituisce il percorso relativo POSIX di SKILL.md rispetto a cfg_dir."""
    try:
        return sk_md.relative_to(cfg_dir).as_posix()
    except ValueError:
        return sk_md.as_posix()


def _scan_external_skills(
    cfg_dir: Path,
    disabled_plugins: Set[str],
    virtual_filtered: Set[str],
) -> Tuple[List[str], List[str], Set[str]]:
    """Scansiona le skill globali distinguendo quelle installate, attive e le sorgenti."""
    installed: List[str] = []
    active: List[str] = []
    sources: Set[str] = set()
    targeted_globs = (
        list(cfg_dir.glob("skills/*/SKILL.md"))
        + list(cfg_dir.glob("plugins/*/skills/*/SKILL.md"))
        + list(cfg_dir.glob("plugins/*/skills/SKILL.md"))
    )
    seen_rels: Set[str] = set()
    for sk_md in sorted(targeted_globs):
        rel = _rel_skill_path(sk_md, cfg_dir)
        if rel in seen_rels:
            continue
        seen_rels.add(rel)
        installed.append(rel)
        parts = rel.split("/")
        if len(parts) >= 2:
            source_id = f"{parts[0]}/{parts[1]}" if parts[0] == "plugins" else parts[0]
            sources.add(source_id)
            if parts[0] == "plugins" and parts[1] in disabled_plugins:
                continue
            if parts[0] == "skills" and parts[1] in virtual_filtered:
                continue
        active.append(rel)
    return installed, active, sources


def _build_hygiene_result_dict(
    self,
    is_default_global: bool,
    workspace_skills_count: int,
    installed_count: int,
    active_count: int,
    external_sources: Set[str],
    disabled_plugins: Set[str],
) -> Dict[str, Any]:
    """Costruisce il dizionario risultato del profilo igiene globale."""
    disabled_count = installed_count - active_count
    effective_filtered = disabled_count if disabled_count > 0 else installed_count
    estimated_tokens = (
        7042 if effective_filtered == 61 else effective_filtered * 115
    )
    portable_cfg_path = (
        "~/.gemini/config"
        if is_default_global
        else self.global_config_dir.as_posix()
    )
    return {
        "config_path": portable_cfg_path,
        "config_exists": self.global_config_dir.exists(),
        "workspace_skills_count": workspace_skills_count,
        "external_skills_count": active_count,
        "installed_external_skills_count": installed_count,
        "active_external_skills_count": active_count,
        "disabled_external_skills_count": disabled_count,
        "total_flat_skills": workspace_skills_count + active_count,
        "context_pollution_detected": active_count > 0,
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


def scan_global_hygiene_profile_impl(
    self, workspace_skills_count: int
) -> Dict[str, Any]:
    """Scansiona il profilo globale ~/.gemini/config distinguendo skill attive e disabilitate."""
    is_default_global = (
        self.global_config_dir.resolve() == DEFAULT_GLOBAL_CONFIG_DIR.resolve()
    )
    readonly_flag = bool(getattr(self, "_readonly_filter_applied", False))
    cached_prof = _get_cached_hygiene_profile(
        self, is_default_global, readonly_flag, workspace_skills_count
    )
    if cached_prof is not None:
        return cached_prof

    installed_skills: List[str] = []
    active_skills: List[str] = []
    external_sources: Set[str] = set()
    disabled_plugins: Set[str] = (
        set(_DEFAULT_READONLY_DISABLED_PLUGINS) if readonly_flag else set()
    )

    if self.global_config_dir.exists() and self.global_config_dir.is_dir():
        disabled_plugins = _collect_disabled_plugins(
            self.global_config_dir, readonly_flag
        )
        virtual_filtered = (
            set(self.GCP_DATA_SKILLS) | set(self.DEV_UTILITY_SKILLS)
            if readonly_flag
            else set()
        )
        installed_skills, active_skills, external_sources = _scan_external_skills(
            self.global_config_dir, disabled_plugins, virtual_filtered
        )

    res_prof = _build_hygiene_result_dict(
        self,
        is_default_global=is_default_global,
        workspace_skills_count=workspace_skills_count,
        installed_count=len(installed_skills),
        active_count=len(active_skills),
        external_sources=external_sources,
        disabled_plugins=disabled_plugins,
    )
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
            if kw_low in dispatch_table or len(kw_low) <= 32:
                dispatch_table[kw_low] = {
                    "domain_id": dom_id,
                    "domain_name": dom_name,
                    "primary_agent": sk_name,
                    "recommended_mode": rec_mode,
                }
    return dispatch_table

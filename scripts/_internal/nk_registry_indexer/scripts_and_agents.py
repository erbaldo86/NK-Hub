"""Scansione script scripts/ e sub-agenti nativi .agents/agents/."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from _internal.nk_registry_indexer.metadata_extract import (
    collect_internal_integrity_index,  # noqa: F401
    extract_script_metadata_impl,  # noqa: F401
    parse_native_agent_metadata_impl,  # noqa: F401
)
from _internal.nk_registry_indexer.taxonomy import (
    DOMAIN_TAXONOMY,
    NATIVE_AGENT_DOMAIN_MAP,
)


def collect_priority_scripts_impl(self) -> Dict[str, Tuple[Path, os.stat_result]]:
    """Raccoglie la mappa script_name -> (Path, stat) a costo zero tramite os.scandir."""
    resolved_map: Dict[str, Tuple[Path, os.stat_result]] = {}
    deleted_paths = self._load_staging_deleted_paths()
    stg_base = self.stage_dir / "scripts"
    prod_base = self.workspace_root / "scripts"
    for base in (stg_base, prod_base):
        is_prod = base == prod_base
        try:
            with os.scandir(base) as it:
                for entry in it:
                    if (
                        entry.is_file(follow_symlinks=False)
                        and entry.name.endswith(".py")
                        and entry.name != "__init__.py"
                    ):
                        if entry.name in resolved_map:
                            continue
                        if is_prod and f"scripts/{entry.name}" in deleted_paths:
                            continue
                        resolved_map[entry.name] = (
                            Path(entry.path),
                            entry.stat(follow_symlinks=False),
                        )
                    elif (
                        entry.is_dir(follow_symlinks=False)
                        and entry.name == "schemas"
                    ):
                        try:
                            with os.scandir(entry.path) as sit:
                                for s_entry in sit:
                                    if (
                                        s_entry.is_file(follow_symlinks=False)
                                        and s_entry.name.endswith(".py")
                                        and s_entry.name != "__init__.py"
                                    ):
                                        sc_key = f"schemas/{s_entry.name}"
                                        if sc_key in resolved_map:
                                            continue
                                        if is_prod and f"scripts/{sc_key}" in deleted_paths:
                                            continue
                                        resolved_map[sc_key] = (
                                            Path(s_entry.path),
                                            s_entry.stat(follow_symlinks=False),
                                        )
                        except OSError:
                            pass
        except OSError:
            pass
    return resolved_map


def scan_scripts_impl(self) -> Dict[str, Dict[str, Any]]:
    """Scansiona gli script in scripts/ e scripts/schemas/ dando priorita a .staging/."""
    script_map = self._collect_priority_scripts()
    scripts_index: Dict[str, Dict[str, Any]] = {}
    for sc_name in sorted(script_map.keys()):
        resolved, _ = script_map[sc_name]
        rel_path = f"scripts/{sc_name}"
        meta = self._extract_script_metadata(resolved)
        declared_dom = meta.get("domain_id", "").strip().upper()
        default_dom = "DOM-01" if sc_name.startswith("schemas/") else "DOM-03"
        dom_id = (
            declared_dom
            if declared_dom in DOMAIN_TAXONOMY
            else self._script_to_domain.get(sc_name, default_dom)
        )
        dom_name = DOMAIN_TAXONOMY[dom_id]["name"]

        scripts_index[sc_name] = {
            "name": sc_name,
            "domain_id": dom_id,
            "domain_name": dom_name,
            "description": meta["description"],
            "cli_flags": meta["cli_flags"],
            "classes": meta.get("classes", []),
            "loc": meta["loc"],
            "bytes": meta["bytes"],
            "sha256": meta["sha256"],
            "path": rel_path,
            "source_layer": (
                "staging" if self.stage_dir in resolved.parents else "production"
            ),
        }
    return scripts_index


def collect_priority_native_agents_impl(
    self,
) -> Dict[str, Tuple[Path, os.stat_result]]:
    """Raccoglie la mappa agent_name -> (agent.md, stat) dando priorita a .staging/."""
    resolved_map: Dict[str, Tuple[Path, os.stat_result]] = {}
    deleted_paths = self._load_staging_deleted_paths()
    stg_base = self.stage_dir / ".agents" / "agents"
    prod_base = self.workspace_root / ".agents" / "agents"
    for base in (stg_base, prod_base):
        is_prod = base == prod_base
        try:
            with os.scandir(base) as it:
                for entry in it:
                    if entry.name in resolved_map:
                        continue
                    if is_prod and f".agents/agents/{entry.name}/agent.md" in deleted_paths:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        ag_md = Path(entry.path) / "agent.md"
                        try:
                            st = ag_md.stat()
                            resolved_map[entry.name] = (ag_md, st)
                        except OSError:
                            pass
        except OSError:
            pass
    return resolved_map


def scan_native_agents_impl(self) -> Dict[str, Dict[str, Any]]:
    """Scansiona i sub-agenti nativi in .agents/agents/*/agent.md dando priorita a .staging/."""
    agent_map = self._collect_priority_native_agents()
    native_agents_index: Dict[str, Dict[str, Any]] = {}
    for ag_name in sorted(agent_map.keys()):
        resolved, st = agent_map[ag_name]
        rel_path = f".agents/agents/{ag_name}/agent.md"
        raw_bytes = resolved.read_bytes().replace(b"\r\n", b"\n")
        sha_hex = hashlib.sha256(raw_bytes).hexdigest()
        type(self)._HASH_CACHE[
            (str(resolved), st.st_mtime_ns, st.st_size)
        ] = sha_hex

        content = raw_bytes.decode("utf-8", errors="replace")
        parsed = self._parse_native_agent_metadata(content)
        declared_dom = str(parsed.get("domain_id", "")).strip().upper()
        default_dom = "DOM-04" if "Auditor" in ag_name else "DOM-03"
        dom_id = (
            declared_dom
            if declared_dom in DOMAIN_TAXONOMY
            else NATIVE_AGENT_DOMAIN_MAP.get(ag_name, default_dom)
        )
        dom_name = DOMAIN_TAXONOMY.get(dom_id, DOMAIN_TAXONOMY["DOM-03"])["name"]

        native_agents_index[ag_name] = {
            "name": parsed["name"] or ag_name,
            "description": parsed["description"],
            "domain_id": dom_id,
            "domain_name": dom_name,
            "enable_write_tools": bool(parsed["enable_write_tools"]),
            "enable_subagent_tools": bool(parsed["enable_subagent_tools"]),
            "enable_mcp_tools": bool(parsed["enable_mcp_tools"]),
            "tools": list(parsed.get("tools", [])),
            "loc": len(content.splitlines()),
            "bytes": st.st_size,
            "sha256": sha_hex,
            "path": rel_path,
            "source_layer": (
                "staging" if self.stage_dir in resolved.parents else "production"
            ),
        }
    return native_agents_index

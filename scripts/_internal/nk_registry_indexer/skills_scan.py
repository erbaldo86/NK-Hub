"""Cache persistente Fast-Stat, SHA-256 e scansione skill di NKRegistryIndexer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.constants import VERSION
from _internal.nk_common.io import atomic_write_text
from _internal.nk_registry_indexer.taxonomy import (
    DOMAIN_TAXONOMY,
    TETRALOGY_FILENAMES,
)


def load_staging_deleted_paths_impl(self) -> Set[str]:
    """Carica i percorsi relativi eliminati in .staging/.deleted_files.json."""
    from _internal.nk_common.thresholds import load_deleted_files

    return load_deleted_files(
        workspace_root=self.workspace_root,
        deleted_manifest=self.stage_dir / ".deleted_files.json",
    )


def collect_priority_skills_impl(self) -> Dict[str, Tuple[Path, os.stat_result]]:
    """Raccoglie la mappa skill_name -> (SKILL.md, stat) con una sola stat per skill."""
    resolved_map: Dict[str, Tuple[Path, os.stat_result]] = {}
    deleted_paths = self._load_staging_deleted_paths()
    stg_base = self.stage_dir / ".agents" / "skills"
    prod_base = self.workspace_root / ".agents" / "skills"
    for base in (stg_base, prod_base):
        is_prod = base == prod_base
        try:
            with os.scandir(base) as it:
                for entry in it:
                    if entry.name in resolved_map:
                        continue
                    if is_prod and f".agents/skills/{entry.name}/SKILL.md" in deleted_paths:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        sk_md = Path(entry.path) / "SKILL.md"
                        try:
                            st = sk_md.stat()
                            resolved_map[entry.name] = (sk_md, st)
                        except OSError:
                            pass
        except OSError:
            pass
    return resolved_map


def parse_skill_metadata_impl(content: str) -> Dict[str, Any]:
    """Estrae frontmatter YAML (inclusi domain_id e sector), card e link da SKILL.md."""
    meta: Dict[str, Any] = {
        "name": "",
        "description": "",
        "version": VERSION,
        "thinking_level": "HIGH",
        "nk_tas_audit": "CRV-4.0-Universal",
        "domain_id": "",
        "sector": "",
        "role_identity": "",
        "native_subagent": "",
        "dashboard_node": "",
        "default_mode": "mode_c",
        "read_only": False,
        "repo_map_budget_exempt": False,
        "enable_mcp_tools": False,
        "tools": [],
        "routing_keywords": [],
        "priority_keywords": [],
        "cli_scripts": [],
        "auxiliary_links": [],
    }

    fm_has_version = False
    fm_match = re.match(
        r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", content, re.DOTALL
    )
    if fm_match:
        fm_block = fm_match.group(1)
        collecting_key: Optional[str] = None
        parsed_fm_tools: List[str] = []
        for line in fm_block.splitlines():
            stripped_ln = line.strip()
            if collecting_key is not None:
                if stripped_ln.startswith("-"):
                    item = stripped_ln.lstrip("-").strip().strip('"').strip("'")
                    if item:
                        if collecting_key == "tools":
                            parsed_fm_tools.append(item)
                        else:
                            meta[collecting_key].append(item)
                    continue
                collecting_key = None
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            key = k.strip()
            raw_val = v.strip()
            val = raw_val.strip('"').strip("'")
            if key in (
                "name",
                "description",
                "version",
                "thinking_level",
                "nk_tas_audit",
                "domain_id",
                "sector",
                "role_identity",
                "native_subagent",
                "dashboard_node",
                "default_mode",
            ):
                meta[key] = val
                if key == "version":
                    fm_has_version = True
            elif key in ("enable_mcp_tools", "read_only", "repo_map_budget_exempt"):
                meta[key] = val.lower() in ("true", "1", "yes")
            elif key in ("tools", "routing_keywords", "priority_keywords", "cli_scripts"):
                if not raw_val:
                    collecting_key = key
                elif raw_val.startswith("[") and raw_val.endswith("]"):
                    try:
                        parsed_list = json.loads(raw_val)
                        items = [str(x).strip() for x in parsed_list if str(x).strip()] if isinstance(parsed_list, list) else []
                    except Exception:
                        inner = raw_val[1:-1]
                        items = [t.strip().strip('"').strip("'") for t in inner.split(",") if t.strip().strip('"').strip("'")]
                    if key == "tools":
                        parsed_fm_tools.extend(items)
                    else:
                        meta[key] = items
                else:
                    items = [t.strip().strip('"').strip("'") for t in raw_val.split(",") if t.strip().strip('"').strip("'")]
                    if key == "tools":
                        parsed_fm_tools.extend(items)
                    else:
                        meta[key] = items
        if not parsed_fm_tools:
            fm_tools_m = re.search(
                r"(?ms)^\s*tools\s*:\s*\[([^\]]*)\]", fm_block
            )
            if fm_tools_m:
                parsed_fm_tools = [
                    t.strip().strip('"').strip("'")
                    for t in fm_tools_m.group(1).split(",")
                    if t.strip().strip('"').strip("'")
                ]
        if parsed_fm_tools:
            meta["tools"] = parsed_fm_tools

    card_match = re.search(
        r"<yaml_metadata_card>(.*?)</yaml_metadata_card>", content, re.DOTALL
    )
    if card_match:
        card_block = card_match.group(1)
        role_m = re.search(r'role_identity:\s*"?([^"\r\n]+)"?', card_block)
        if role_m and not meta["role_identity"]:
            meta["role_identity"] = role_m.group(1).strip()
        dom_m = re.search(r'domain_id:\s*"?([^"\r\n]+)"?', card_block)
        if dom_m and not meta["domain_id"]:
            meta["domain_id"] = dom_m.group(1).strip()
        ver_m = re.search(r'version:\s*"?([^"\r\n]+)"?', card_block)
        if ver_m and not fm_has_version:
            meta["version"] = ver_m.group(1).strip()
        sec_m = re.search(r'sector:\s*"?([^"\r\n]+)"?', card_block)
        if sec_m and not meta["sector"]:
            meta["sector"] = sec_m.group(1).strip()
        if re.search(r"(?m)^\s*enable_mcp_tools\s*:\s*true\b", card_block, re.IGNORECASE):
            meta["enable_mcp_tools"] = True
        tools_m = re.search(r"tools:\s*\[([^\]]*)\]", card_block)
        if tools_m and not meta["tools"]:
            raw_tools = tools_m.group(1)
            meta["tools"] = [
                t.strip().strip('"').strip("'")
                for t in raw_tools.split(",")
                if t.strip().strip('"').strip("'")
            ]

    aux_links: List[str] = []
    for m in re.finditer(r"\]\(((?:resources|references)/[^\)]+)\)", content):
        link = m.group(1).strip()
        if link not in aux_links:
            aux_links.append(link)
    meta["auxiliary_links"] = sorted(aux_links)
    return meta


def resolve_skill_native_subagent_impl(
    sk_name: str, dom_id: str, skill_meta: Optional[Dict[str, Any]] = None
) -> str:
    """Risolve il sub-agente nativo dal frontmatter skill o dal dominio di fallback."""
    if isinstance(skill_meta, dict) and str(skill_meta.get("native_subagent") or "").strip():
        return str(skill_meta["native_subagent"]).strip()
    if sk_name == "NK-Agent-Instruction-Forge":
        return "NK-Builder-Agent"
    if sk_name == "NK-Ideator":
        return "NK-Arch-Specifier"
    if sk_name == "NK-Oracle-Evaluator":
        return "NK-RSI-Auditor"
    dom_to_native = {
        "DOM-01": "Orchestrator-Direct",
        "DOM-02": "NK-Specifier-Agent",
        "DOM-03": "NK-Builder-Agent",
        "DOM-04": "NK-Security-DAST-Auditor",
        "DOM-05": "NK-Scribe-Agent",
    }
    return dom_to_native.get(dom_id, "NK-Builder-Agent")

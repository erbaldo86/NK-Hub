"""Verifica SHA-256 O(1) e audit governance GT-14/CRIT-01 sul manifesto."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_registry_indexer.taxonomy import (
    CRIT01_FORBIDDEN_TOOLS,
    _DEFAULT_WORKSPACE_ROOT,
)



def sha256_matches_eol_normalized_impl(
    file_path: Path, live_sha: str, recorded_sha: str
) -> bool:
    """Verifica l'uguaglianza SHA-256 tollerando differenze di fine riga CRLF e LF."""
    if live_sha == recorded_sha:
        return True
    if not recorded_sha:
        return False
    try:
        raw = file_path.read_bytes()
        lf_bytes = raw.replace(b"\r\n", b"\n")
        if hashlib.sha256(lf_bytes).hexdigest() == recorded_sha:
            return True
        if hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest() == recorded_sha:
            return True
    except Exception:
        pass
    return False


def audit_gt14_crit01_entries_impl(
    self,
    agent_map: Dict[str, Tuple[Path, os.stat_result]],
    skill_map: Dict[str, Tuple[Path, os.stat_result]],
    manifest_agents: Optional[Dict[str, Any]] = None,
    manifest_skills: Optional[Dict[str, Any]] = None,
    unchanged_agents: Optional[Set[str]] = None,
    unchanged_skills: Optional[Set[str]] = None,
) -> List[str]:
    """Applica le guardie deterministiche GT-14, RULE-01 (2-Tier) e CRIT-01 su agenti e skill."""
    issues: List[str] = []
    m_agents = manifest_agents if manifest_agents is not None else {}
    m_skills = manifest_skills if manifest_skills is not None else {}
    clean_agents = unchanged_agents if unchanged_agents is not None else set()
    clean_skills = unchanged_skills if unchanged_skills is not None else set()

    readonly_agent_names = {
        "NK-Arch-Specifier",
        "NK-Security-DAST-Auditor",
        "NK-RSI-Auditor",
    }
    allowed_ro_tools = {
        "read_file",
        "grep_search",
        "find_by_name",
        "list_dir",
        "view_file_outline",
        "view_code_item",
        "send_message",
    }
    write_tool_names = {
        "write_file",
        "edit_file",
        "run_command",
        "write_to_file",
        "replace_file_content",
    }
    specifier_forbidden = {
        "run_command",
        "manage_task",
        "search_web",
        "generate_image",
    }

    all_agent_names = sorted(set(agent_map.keys()) | set(m_agents.keys()))
    for ag_name in all_agent_names:
        ag_meta = m_agents.get(ag_name, {})
        if not isinstance(ag_meta, dict):
            ag_meta = {}
        parsed_live: Dict[str, Any] = {}
        if ag_name in agent_map and (
            ag_name not in clean_agents
            or not ag_meta
            or "tools" not in ag_meta
            or "enable_mcp_tools" not in ag_meta
        ):
            resolved, _ = agent_map[ag_name]
            try:
                raw_txt = resolved.read_text(encoding="utf-8", errors="replace")
                parsed_live = self._parse_native_agent_metadata(raw_txt)
            except Exception:
                pass

        declared_tools = (
            list(parsed_live.get("tools", []))
            if "tools" in parsed_live
            else list(ag_meta.get("tools", []))
        )
        has_write_tool = any(t in write_tool_names for t in declared_tools)

        subagent_enabled = (
            ag_meta.get("enable_subagent_tools") is True
            or parsed_live.get("enable_subagent_tools") is True
            or "invoke_subagent" in declared_tools
            or "define_subagent" in declared_tools
        )
        if subagent_enabled:
            issues.append(
                f"Violazione RULE-01 (2-Tier): enable_subagent_tools attivo sul Sub-Agente '{ag_name}'."
            )

        mcp_enabled = (
            ag_meta.get("enable_mcp_tools") is True
            or parsed_live.get("enable_mcp_tools") is True
        )
        if mcp_enabled:
            issues.append(
                f"Violazione CRIT-01: enable_mcp_tools attivo sul Sub-Agente '{ag_name}'."
            )

        if ag_name in readonly_agent_names or "auditor" in ag_name.lower():
            write_enabled = (
                has_write_tool
                or ag_meta.get("enable_write_tools") is True
                or parsed_live.get("enable_write_tools") is True
            )
            if write_enabled:
                issues.append(
                    f"Violazione GT-14: enable_write_tools attivo sull'Auditor / nodo read-only {ag_name}"
                )
            disallowed_ro = sorted(
                t for t in declared_tools if t not in allowed_ro_tools
            )
            if disallowed_ro:
                issues.append(
                    f"Violazione GT-14: tool non permessi {disallowed_ro} sul nodo read-only '{ag_name}'."
                )

        if ag_name == "NK-Specifier-Agent":
            bad_spec = sorted(
                t for t in declared_tools if t in specifier_forbidden
            )
            if bad_spec:
                issues.append(
                    f"Violazione GT-14: tool vietati {bad_spec} sul Sub-Agente '{ag_name}'."
                )

        phantom_tools = sorted(
            t
            for t in declared_tools
            if t in CRIT01_FORBIDDEN_TOOLS or str(t).startswith("mcp_")
        )
        if phantom_tools:
            issues.append(
                f"Violazione CRIT-01 / Runtime 2.0: tool MCP fantasma o vietati {phantom_tools} sul Sub-Agente '{ag_name}'."
            )

    all_skill_names = sorted(set(skill_map.keys()) | set(m_skills.keys()))
    for sk_name in all_skill_names:
        if sk_name in ("NK-Master-Hub", "NK-Session-Controller", "NK-Orchestrator"):
            continue
        sk_meta = m_skills.get(sk_name, {})
        if not isinstance(sk_meta, dict):
            sk_meta = {}
        sk_live: Dict[str, Any] = {}
        if sk_name in skill_map and (
            sk_name not in clean_skills
            or not sk_meta
            or "tools" not in sk_meta
            or "enable_mcp_tools" not in sk_meta
        ):
            resolved, _ = skill_map[sk_name]
            try:
                raw_sk = resolved.read_text(encoding="utf-8", errors="replace")
                sk_live = self._parse_skill_metadata(raw_sk)
            except Exception:
                pass

        sk_mcp_enabled = (
            sk_meta.get("enable_mcp_tools") is True
            or sk_live.get("enable_mcp_tools") is True
        )
        if sk_mcp_enabled:
            issues.append(
                f"Violazione CRIT-01: enable_mcp_tools attivo sulla Skill '{sk_name}'."
            )

        sk_tools = (
            list(sk_live.get("tools", []))
            if "tools" in sk_live
            else list(sk_meta.get("tools", []))
        )
        sk_phantom = sorted(
            t
            for t in sk_tools
            if t in CRIT01_FORBIDDEN_TOOLS or str(t).startswith("mcp_")
        )
        if sk_phantom:
            issues.append(
                f"Violazione CRIT-01 / Runtime 2.0: tool vietati {sk_phantom} sulla Skill '{sk_name}'."
            )

    return issues


def verify_gt14_crit01_governance_impl(self) -> Dict[str, Any]:
    """Verifica la conformita GT-14 e CRIT-01 direttamente sui file overlay su disco."""
    agent_map = self._collect_priority_native_agents()
    skill_map = self._collect_priority_skills()
    issues = self._audit_gt14_crit01_entries(
        agent_map=agent_map,
        skill_map=skill_map,
    )
    return {
        "passed": len(issues) == 0,
        "agents_checked": len(agent_map),
        "skills_checked": len(skill_map),
        "issues": issues,
    }

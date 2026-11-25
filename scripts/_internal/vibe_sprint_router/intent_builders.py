"""Costruttori payload di intento e normalizzatori governance read-only."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

try:
    from _internal.nk_registry_indexer.taxonomy import (
        CRIT01_FORBIDDEN_TOOLS,
        FORBIDDEN_PHANTOM_MCP_TOOLS,
    )
except ImportError:  # pragma: no cover
    CRIT01_FORBIDDEN_TOOLS = ("search_web", "generate_image", "invoke_subagent", "schedule", "call_mcp_tool", "list_resources", "read_resource")
    FORBIDDEN_PHANTOM_MCP_TOOLS = ("call_mcp_tool", "list_resources", "read_resource")

from _internal.vibe_sprint_router.constants_core import MODE_D_LABEL
from _internal.vibe_sprint_router.constants_stt import DASHBOARD_NODE_MAP

_MODE_D_READONLY_TOOLS: Tuple[str, ...] = ("read_file", "send_message")
_GOV_RO_AUDIT_TARGETS: Tuple[str, ...] = ("ste100", "asd-ste100", "skill.md", "agent.md", "skill_golden_eval_set")
_GOV_RO_AUDIT_VERBS: Tuple[str, ...] = ("verifica", "controlla", "valida", "ispeziona", "audit")
_FORBIDDEN_TOOLS_SET: FrozenSet[str] = frozenset((*CRIT01_FORBIDDEN_TOOLS, *FORBIDDEN_PHANTOM_MCP_TOOLS, "read_url_content"))


def _sanitize_tools_allowed(tools: Sequence[str]) -> List[str]:
    """Rimuove qualsiasi tool CRIT-01 o MCP fantasma dalle liste tools_allowed."""
    return [t for t in tools if t not in _FORBIDDEN_TOOLS_SET and not str(t).startswith("mcp_")]


def _detect_gov_ro_audit(text_lower: str) -> Tuple[bool, bool]:
    """Rileva target di governance e verbi read-only per audit STE100/SKILL/agent."""
    is_gov = any(gk in text_lower for gk in _GOV_RO_AUDIT_TARGETS)
    has_verb = is_gov and any(vk in text_lower for vk in _GOV_RO_AUDIT_VERBS)
    return is_gov, has_verb


def _select_mode_d_keywords(matched: List[str], has_gov_ro_verb: bool) -> List[str]:
    """Restituisce le keyword diagnostiche per l'esito Mode D."""
    if matched:
        return matched
    return ["gov_ro_audit"] if has_gov_ro_verb else ["negated_write"]


def _normalize_gov_ro_domain(
    is_gov_ro_audit: bool, has_gov_ro_verb: bool, has_write_intent: bool,
    primary_ag: str, matched_sk: List[str], native_sub: str, domain_info: Dict[str, Any],
) -> Tuple[str, List[str], str, str, str]:
    """Allinea DOM-04/Oracle/NK-RSI-Auditor per audit read-only su governance senza scrittura."""
    if not is_gov_ro_audit or has_write_intent:
        return primary_ag, matched_sk, native_sub, domain_info["domain_id"], domain_info["domain_name"]
    is_builder_or_auditor = (
        has_gov_ro_verb
        or native_sub in ("NK-RSI-Auditor", "NK-Builder-Agent")
        or domain_info["domain_id"] == "DOM-03"
        or primary_ag == "NK-Agent-Instruction-Forge"
    )
    if is_builder_or_auditor:
        return ("NK-Oracle-Evaluator", ["NK-Oracle-Evaluator", "NK-Agent-Instruction-Forge"], "NK-RSI-Auditor", "DOM-04", "AUDIT_DAST_AND_RCA")
    return primary_ag, matched_sk, native_sub, domain_info["domain_id"], domain_info["domain_name"]


def _build_passive_handoff_intent(prompt: str) -> Dict[str, Any]:
    """Costruisce il dizionario intento standby per Passive Session State Handoff."""
    return {
        "recommended_mode": "mode_d", "mode": MODE_D_LABEL, "mode_label": MODE_D_LABEL,
        "is_discovery": True, "read_only": True, "standby_mode": True,
        "bypass_reason": "STATE_HANDOFF_STANDBY", "matched_keywords": ["state_handoff"],
        "primary_agent": "NK-Orchestrator", "matched_skills": ["NK-Orchestrator"],
        "native_subagent": "Orchestrator-Direct", "fast_bypass_eligible": False,
        "changed_lines": 0, "role_conflicts": [], "domain_id": "DOM-01",
        "domain_name": "GOV_AND_ROUTING", "tools_allowed": _sanitize_tools_allowed(["read_file"]),
        "prompt": prompt, "reason": "Passive Session State Handoff detected (STATE_HANDOFF_STANDBY).",
    }


def _build_dashboard_selector_intent(prompt: str, sel_idx: int, explicit_mode: Optional[str]) -> Dict[str, Any]:
    """Costruisce l'intento per la selezione diretta di un nodo dashboard [0]..[9]."""
    sk_name, dom_id, dom_name, subagent, is_ro = DASHBOARD_NODE_MAP[sel_idx]
    sel_mode = explicit_mode or ("mode_d" if is_ro else "mode_c")
    sel_ro = sel_mode == "mode_d"
    mode_txt = MODE_D_LABEL if sel_ro else "Mode A/B/C (Code & Specification Routing)"
    return {
        "recommended_mode": sel_mode, "mode": mode_txt, "mode_label": mode_txt,
        "is_discovery": sel_ro, "read_only": sel_ro, "matched_keywords": [f"[{sel_idx}]"],
        "primary_agent": sk_name, "matched_skills": [sk_name], "native_subagent": subagent,
        "fast_bypass_eligible": False, "changed_lines": 0, "role_conflicts": [],
        "domain_id": dom_id, "domain_name": dom_name, "dashboard_node": sel_idx,
        "tools_allowed": _sanitize_tools_allowed(_MODE_D_READONLY_TOOLS) if sel_ro else [],
        "prompt": prompt, "reason": f"Direct NK-Orchestrator dashboard selector [{sel_idx}] -> {sk_name}.",
    }


def _resolve_mode_d_routing(
    domain_info: Dict[str, Any], is_dom04_tech_audit: bool, is_gov_ro_audit: bool
) -> Tuple[str, str, List[str], str, str]:
    """Risolve skill, sub-agente e dominio per i percorsi analitici Mode D."""
    if is_dom04_tech_audit:
        primary_ag = domain_info.get("primary_skill", "NK-Security-Auditor")
        native_sub = domain_info.get("native_subagent", "NK-Security-DAST-Auditor")
        matched_sk = domain_info.get("matched_skills", [primary_ag])
        return primary_ag, native_sub, matched_sk, domain_info["domain_id"], domain_info["domain_name"]
    if is_gov_ro_audit:
        return "NK-Oracle-Evaluator", "NK-RSI-Auditor", ["NK-Oracle-Evaluator", "NK-Agent-Instruction-Forge"], "DOM-04", "AUDIT_DAST_AND_RCA"
    dom_id = "DOM-02" if domain_info["domain_id"] == "DOM-03" else domain_info["domain_id"]
    dom_name = "IDEATION_AND_ARCH" if dom_id == "DOM-02" else domain_info["domain_name"]
    return "NK-Ideator", "NK-Arch-Specifier", ["NK-Ideator"], dom_id, dom_name


def _build_mode_d_discovery_intent(
    prompt: str, domain_info: Dict[str, Any], is_dom04_tech_audit: bool, is_gov_ro_audit: bool,
    matched: List[str], has_gov_ro_verb: bool, total_loc: int, role_conflicts: List[str],
) -> Dict[str, Any]:
    """Costruisce il risultato Mode D Read-Only Discovery."""
    primary_ag, native_sub, matched_sk, dom_id, dom_name = _resolve_mode_d_routing(
        domain_info, is_dom04_tech_audit, is_gov_ro_audit
    )
    matched_out = _select_mode_d_keywords(matched, has_gov_ro_verb)
    return {
        "recommended_mode": "mode_d", "mode": MODE_D_LABEL, "mode_label": MODE_D_LABEL,
        "is_discovery": True, "read_only": True, "matched_keywords": matched_out,
        "primary_agent": primary_ag, "matched_skills": matched_sk, "native_subagent": native_sub,
        "fast_bypass_eligible": False, "changed_lines": total_loc, "role_conflicts": role_conflicts,
        "domain_id": dom_id, "domain_name": dom_name,
        "tools_allowed": _sanitize_tools_allowed(_MODE_D_READONLY_TOOLS),
        "prompt": prompt, "reason": f"Analytical discovery intent detected via keywords: {matched_out}",
    }


def _build_standard_intent(
    prompt: str, rec_mode: str, explicit_mode: Optional[str], is_ro_mode: bool,
    fast_bypass_eligible: bool, matched: List[str], primary_ag: str, matched_sk: List[str],
    native_sub: str, total_loc: int, phase_count: int, role_conflicts: List[str],
    dom_id_out: str, dom_name_out: str,
) -> Dict[str, Any]:
    """Costruisce il risultato finale per il routing Mode A/B/C o Mode D esplicito."""
    mode_txt = MODE_D_LABEL if is_ro_mode else "Mode A/B/C (Code & Specification Routing)"
    if explicit_mode is not None:
        reason = f"Explicit mode override: {rec_mode}."
    elif rec_mode != "mode_c":
        reason = f"Escalated to {rec_mode} (changed_lines={total_loc}, phases={phase_count})."
    else:
        reason = "Standard implementation or file modification routing."
    return {
        "recommended_mode": rec_mode, "mode": mode_txt, "mode_label": mode_txt,
        "is_discovery": is_ro_mode, "read_only": is_ro_mode, "matched_keywords": matched,
        "primary_agent": primary_ag, "matched_skills": matched_sk, "native_subagent": native_sub,
        "fast_bypass_eligible": fast_bypass_eligible, "changed_lines": total_loc,
        "role_conflicts": role_conflicts, "domain_id": dom_id_out, "domain_name": dom_name_out,
        "tools_allowed": _sanitize_tools_allowed(_MODE_D_READONLY_TOOLS) if is_ro_mode else [],
        "prompt": prompt, "reason": reason,
    }

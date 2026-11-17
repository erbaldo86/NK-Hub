"""Classificatore dell'intento operativo (Mode D vs Mode A/B/C) su prompt e file."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

try:
    from _internal.nk_registry_indexer.taxonomy import (
        CRIT01_FORBIDDEN_TOOLS,
        FORBIDDEN_PHANTOM_MCP_TOOLS,
    )
except ImportError:  # pragma: no cover
    CRIT01_FORBIDDEN_TOOLS = (
        "search_web",
        "generate_image",
        "invoke_subagent",
        "schedule",
        "call_mcp_tool",
        "list_resources",
        "read_resource",
    )
    FORBIDDEN_PHANTOM_MCP_TOOLS = (
        "call_mcp_tool",
        "list_resources",
        "read_resource",
    )

from _internal.vibe_sprint_router.constants_core import (
    MODE_D_LABEL,
    _BRIEF_HEADER_PHASE_RE,
    _DOM04_TECHNICAL_AUDIT_KEYWORDS,
    _normalize_explicit_mode,
    _normalize_input_text,
    _sanitize_tetralogia_filenames,
)
from _internal.vibe_sprint_router.constants_stt import (
    DASHBOARD_NODE_MAP,
    _extract_primary_stt_clause,
    _parse_dashboard_selector,
)
from _internal.vibe_sprint_router.domain_matcher import (
    _has_audit_forensic_intent,
    _resolve_native_subagent,
)
from _internal.vibe_sprint_router.prompt_linter import (
    _detect_prompt_role_conflicts,
    is_passive_state_handoff,
)
from _internal.vibe_sprint_router.write_intent import (
    _analyze_write_intent,
    _has_destructive_shell_command,
)

_MODE_D_READONLY_TOOLS: Tuple[str, ...] = ("read_file", "send_message")
_FORBIDDEN_TOOLS_SET: FrozenSet[str] = frozenset(
    (*CRIT01_FORBIDDEN_TOOLS, *FORBIDDEN_PHANTOM_MCP_TOOLS, "read_url_content")
)


def _sanitize_tools_allowed(tools: Sequence[str]) -> List[str]:
    """Rimuove qualsiasi tool CRIT-01 o MCP fantasma dalle liste tools_allowed."""
    return [
        t
        for t in tools
        if t not in _FORBIDDEN_TOOLS_SET and not str(t).startswith("mcp_")
    ]


def classify_prompt_intent_impl(
    self,
    prompt: str,
    files: Optional[List[str]] = None,
    changed_lines: Optional[int] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Classifica il prompt, attiva Mode D su discovery pura e risolve skill e sub-agente."""
    raw_text = _normalize_input_text(prompt).strip()
    explicit_mode = _normalize_explicit_mode(mode)
    if is_passive_state_handoff(raw_text):
        return {
            "recommended_mode": "mode_d",
            "mode": MODE_D_LABEL,
            "mode_label": MODE_D_LABEL,
            "is_discovery": True,
            "read_only": True,
            "standby_mode": True,
            "bypass_reason": "STATE_HANDOFF_STANDBY",
            "matched_keywords": ["state_handoff"],
            "primary_agent": "NK-Orchestrator",
            "matched_skills": ["NK-Orchestrator"],
            "native_subagent": "Orchestrator-Direct",
            "fast_bypass_eligible": False,
            "changed_lines": 0,
            "role_conflicts": [],
            "domain_id": "DOM-01",
            "domain_name": "GOV_AND_ROUTING",
            "tools_allowed": _sanitize_tools_allowed(["read_file"]),
            "prompt": prompt,
            "reason": "Passive Session State Handoff detected (STATE_HANDOFF_STANDBY).",
        }

    has_code_files = bool(files and len(files) > 0)
    sel_idx = _parse_dashboard_selector(raw_text)
    if (
        sel_idx is not None
        and not has_code_files
        and (changed_lines is None or changed_lines == 0)
    ):
        sk_name, dom_id, dom_name, subagent, is_ro = DASHBOARD_NODE_MAP[sel_idx]
        sel_mode = explicit_mode or ("mode_d" if is_ro else "mode_c")
        sel_ro = sel_mode == "mode_d"
        return {
            "recommended_mode": sel_mode,
            "mode": (
                MODE_D_LABEL
                if sel_ro
                else "Mode A/B/C (Code & Specification Routing)"
            ),
            "mode_label": (
                MODE_D_LABEL
                if sel_ro
                else "Mode A/B/C (Code & Specification Routing)"
            ),
            "is_discovery": sel_ro,
            "read_only": sel_ro,
            "matched_keywords": [f"[{sel_idx}]"],
            "primary_agent": sk_name,
            "matched_skills": [sk_name],
            "native_subagent": subagent,
            "fast_bypass_eligible": False,
            "changed_lines": 0,
            "role_conflicts": [],
            "domain_id": dom_id,
            "domain_name": dom_name,
            "dashboard_node": sel_idx,
            "tools_allowed": (
                _sanitize_tools_allowed(_MODE_D_READONLY_TOOLS) if sel_ro else []
            ),
            "prompt": prompt,
            "reason": f"Direct NK-Orchestrator dashboard selector [{sel_idx}] -> {sk_name}.",
        }

    effective_raw = _extract_primary_stt_clause(raw_text)
    text_lower = effective_raw.lower()
    clean_text = _sanitize_tetralogia_filenames(text_lower)
    matched = [kw for kw in self.DISCOVERY_KEYWORDS if kw in text_lower]
    domain_info = self.resolve_domain_from_manifest(effective_raw)

    has_write_intent, has_negated_write = _analyze_write_intent(clean_text)
    if not has_write_intent and _has_destructive_shell_command(raw_text):
        has_write_intent = True

    if (
        "fase" in text_lower
        or "phase" in text_lower
        or "livello" in text_lower
    ):
        phase_count = len(_BRIEF_HEADER_PHASE_RE.findall(effective_raw))
    else:
        phase_count = 0

    prompt_len = len(raw_text)
    role_conflicts = _detect_prompt_role_conflicts(
        effective_raw,
        text_lower=text_lower,
        has_write_override=has_write_intent,
    )
    total_loc = self._estimate_changed_loc(files=files, changed_lines=changed_lines)

    is_dom04_tech_audit = domain_info["domain_id"] == "DOM-04" and (
        any(tkw in text_lower for tkw in _DOM04_TECHNICAL_AUDIT_KEYWORDS)
        or _has_audit_forensic_intent(text_lower)
    )

    if (
        (matched or has_negated_write)
        and not has_code_files
        and not has_write_intent
        and phase_count < 2
        and (changed_lines is None or changed_lines == 0)
        and explicit_mode not in ("mode_a", "mode_b", "mode_c")
    ):
        is_gov_ro_audit = any(
            gk in text_lower
            for gk in ("ste100", "asd-ste100", "skill.md", "skill_golden_eval_set")
        )
        if is_dom04_tech_audit:
            primary_ag = domain_info.get("primary_skill", "NK-Security-Auditor")
            native_sub = domain_info.get(
                "native_subagent", "NK-Security-DAST-Auditor"
            )
            matched_sk = domain_info.get("matched_skills", [primary_ag])
            dom_id = domain_info["domain_id"]
            dom_name = domain_info["domain_name"]
        elif is_gov_ro_audit:
            primary_ag = "NK-Oracle-Evaluator"
            native_sub = "NK-RSI-Auditor"
            matched_sk = ["NK-Oracle-Evaluator", "NK-Agent-Instruction-Forge"]
            dom_id = "DOM-04"
            dom_name = "AUDIT_DAST_AND_RCA"
        else:
            primary_ag = "NK-Ideator"
            native_sub = "NK-Arch-Specifier"
            matched_sk = ["NK-Ideator"]
            dom_id = (
                "DOM-02"
                if domain_info["domain_id"] == "DOM-03"
                else domain_info["domain_id"]
            )
            dom_name = (
                "IDEATION_AND_ARCH"
                if dom_id == "DOM-02"
                else domain_info["domain_name"]
            )

        matched_out = matched if matched else ["negated_write"]
        return {
            "recommended_mode": "mode_d",
            "mode": MODE_D_LABEL,
            "mode_label": MODE_D_LABEL,
            "is_discovery": True,
            "read_only": True,
            "matched_keywords": matched_out,
            "primary_agent": primary_ag,
            "matched_skills": matched_sk,
            "native_subagent": native_sub,
            "fast_bypass_eligible": False,
            "changed_lines": total_loc,
            "role_conflicts": role_conflicts,
            "domain_id": dom_id,
            "domain_name": dom_name,
            "tools_allowed": _sanitize_tools_allowed(_MODE_D_READONLY_TOOLS),
            "prompt": prompt,
            "reason": (
                f"Analytical discovery intent detected via keywords: {matched_out}"
            ),
        }

    primary_ag = domain_info.get("primary_skill", "NK-Python-Async-Builder")
    matched_sk = domain_info.get("matched_skills", [primary_ag])
    native_sub = domain_info.get(
        "native_subagent",
        _resolve_native_subagent(
            domain_info["domain_id"],
            matched_skill=primary_ag,
            text=text_lower,
        ),
    )

    if explicit_mode in ("mode_a", "mode_b", "mode_c", "mode_d"):
        rec_mode = explicit_mode
    elif (
        phase_count >= 2
        or (prompt_len > 1500 and (has_write_intent or not matched))
        or any(
            k in text_lower
            for k in (
                "allinea 1:1",
                "turno 4",
                "auto-brief",
                "cold review",
                "6 gate",
                "oracolo",
                "multi-file",
                "multifile",
            )
        )
    ):
        rec_mode = "mode_a"
    elif (
        total_loc > self.MODE_C_MAX_LOC
        or prompt_len > self.MODE_C_MAX_PROMPT_CHARS
        or any(
            k in text_lower
            for k in ("sbfl", "ochiai", "causa radice", "rca", "falsi bug")
        )
    ):
        rec_mode = "mode_b"
    else:
        rec_mode = "mode_c"

    is_ro_mode = bool(
        rec_mode == "mode_d"
        and not has_write_intent
        and not has_code_files
        and (changed_lines is None or changed_lines == 0)
    )
    fast_bypass_eligible = bool(
        rec_mode == "mode_c"
        and total_loc <= self.MODE_C_MAX_LOC
        and prompt_len <= self.MODE_C_MAX_PROMPT_CHARS
        and phase_count < 2
        and not role_conflicts
    )

    return {
        "recommended_mode": rec_mode,
        "mode": (
            MODE_D_LABEL
            if is_ro_mode
            else "Mode A/B/C (Code & Specification Routing)"
        ),
        "mode_label": (
            MODE_D_LABEL
            if is_ro_mode
            else "Mode A/B/C (Code & Specification Routing)"
        ),
        "is_discovery": is_ro_mode,
        "read_only": is_ro_mode,
        "matched_keywords": matched,
        "primary_agent": primary_ag,
        "matched_skills": matched_sk,
        "native_subagent": native_sub,
        "fast_bypass_eligible": fast_bypass_eligible,
        "changed_lines": total_loc,
        "role_conflicts": role_conflicts,
        "domain_id": domain_info["domain_id"],
        "domain_name": domain_info["domain_name"],
        "tools_allowed": (
            _sanitize_tools_allowed(_MODE_D_READONLY_TOOLS) if is_ro_mode else []
        ),
        "prompt": prompt,
        "reason": (
            f"Explicit mode override: {rec_mode}."
            if explicit_mode is not None
            else (
                f"Escalated to {rec_mode} (changed_lines={total_loc}, phases={phase_count})."
                if rec_mode != "mode_c"
                else "Standard implementation or file modification routing."
            )
        ),
    }

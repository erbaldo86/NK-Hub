"""Classificatore dell'intento operativo (Mode D vs Mode A/B/C) su prompt e file."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.vibe_sprint_router.constants_core import (
    MODE_D_LABEL,  # noqa: F401
    _BRIEF_HEADER_PHASE_RE,
    _DOM04_TECHNICAL_AUDIT_KEYWORDS,
    _normalize_explicit_mode,
    _normalize_input_text,
    _sanitize_tetralogia_filenames,
)
from _internal.vibe_sprint_router.constants_stt import (
    DASHBOARD_NODE_MAP,  # noqa: F401
    _extract_primary_stt_clause,
    _parse_dashboard_selector,
)
from _internal.vibe_sprint_router.domain_matcher import (
    _has_audit_forensic_intent,
    _resolve_native_subagent,
)
from _internal.vibe_sprint_router.intent_builders import (
    CRIT01_FORBIDDEN_TOOLS,  # noqa: F401
    FORBIDDEN_PHANTOM_MCP_TOOLS,  # noqa: F401
    _FORBIDDEN_TOOLS_SET,  # noqa: F401
    _GOV_RO_AUDIT_TARGETS,  # noqa: F401
    _GOV_RO_AUDIT_VERBS,  # noqa: F401
    _MODE_D_READONLY_TOOLS,  # noqa: F401
    _build_dashboard_selector_intent,
    _build_mode_d_discovery_intent,
    _build_passive_handoff_intent,
    _build_standard_intent,
    _detect_gov_ro_audit,  # noqa: F401
    _normalize_gov_ro_domain,  # noqa: F401
    _sanitize_tools_allowed,  # noqa: F401
    _select_mode_d_keywords,  # noqa: F401
)
from _internal.vibe_sprint_router.intent_track_classifier import (
    classify_intent_track,
    resolve_intent_track_profile,
)
from _internal.vibe_sprint_router.prompt_linter import (
    _detect_prompt_role_conflicts,
    is_passive_state_handoff,
)
from _internal.vibe_sprint_router.write_intent import (
    _analyze_write_intent,
    _has_destructive_shell_command,
)

_MODE_A_CUES: Tuple[str, ...] = (
    "allinea 1:1",
    "turno 4",
    "auto-brief",
    "cold review",
    "6 gate",
    "oracolo",
    "multi-file",
    "multifile",
)
_MODE_B_CUES: Tuple[str, ...] = ("sbfl", "ochiai", "causa radice", "rca", "falsi bug")
_PHASE_HEADER_TOKENS: Tuple[str, ...] = ("fase", "phase", "livello")


def _count_prompt_phases(effective_raw: str, text_lower: str) -> int:
    """Conta le intestazioni di fase nel prompt solo se presenti cue lessicali."""
    if any(tok in text_lower for tok in _PHASE_HEADER_TOKENS):
        return len(_BRIEF_HEADER_PHASE_RE.findall(effective_raw))
    return 0


def _match_discovery_keywords(keywords: Sequence[str], text_lower: str) -> List[str]:
    """Restituisce le keyword di discovery presenti nel testo normalizzato."""
    return [kw for kw in keywords if kw in text_lower]


def _is_dom04_tech_audit(domain_info: Dict[str, Any], text_lower: str) -> bool:
    """Verifica se il dominio DOM-04 richiede un audit tecnico o forense."""
    if domain_info["domain_id"] != "DOM-04":
        return False
    return any(tkw in text_lower for tkw in _DOM04_TECHNICAL_AUDIT_KEYWORDS) or _has_audit_forensic_intent(text_lower)


def _is_mode_d_discovery_candidate(
    matched: List[str],
    has_negated_write: bool,
    has_gov_ro_verb: bool,
    has_code_files: bool,
    has_write_intent: bool,
    phase_count: int,
    changed_lines: Optional[int],
    explicit_mode: Optional[str],
) -> bool:
    """Valuta l'ammissibilita al percorso analitico Mode D Read-Only."""
    if has_code_files or has_write_intent or phase_count >= 2:
        return False
    if changed_lines not in (None, 0):
        return False
    if explicit_mode in ("mode_a", "mode_b", "mode_c"):
        return False
    return bool(matched or has_negated_write or has_gov_ro_verb)


def _is_mode_a_escalation(
    phase_count: int,
    prompt_len: int,
    has_write_intent: bool,
    matched: List[str],
    text_lower: str,
) -> bool:
    """Determina se il prompt richiede l'escalation architetturale Mode A."""
    if phase_count >= 2:
        return True
    if prompt_len > 1500 and (has_write_intent or not matched):
        return True
    return any(k in text_lower for k in _MODE_A_CUES)


def _resolve_escalation_mode(
    explicit_mode: Optional[str],
    phase_count: int,
    prompt_len: int,
    has_write_intent: bool,
    matched: List[str],
    text_lower: str,
    total_loc: int,
    max_loc: int,
    max_chars: int,
) -> str:
    """Risolve la modalita operativa tra override esplicito, Mode A, B e C."""
    if explicit_mode in ("mode_a", "mode_b", "mode_c", "mode_d"):
        return explicit_mode
    if _is_mode_a_escalation(phase_count, prompt_len, has_write_intent, matched, text_lower):
        return "mode_a"
    if total_loc > max_loc or prompt_len > max_chars or any(k in text_lower for k in _MODE_B_CUES):
        return "mode_b"
    return "mode_c"


def _compute_intent_eligibility(
    rec_mode: str,
    has_write_intent: bool,
    has_code_files: bool,
    changed_lines: Optional[int],
    total_loc: int,
    max_loc: int,
    prompt_len: int,
    max_chars: int,
    phase_count: int,
    role_conflicts: List[str],
) -> Tuple[bool, bool]:
    """Calcola read-only finale ed eleggibilita al fast-bypass Mode C."""
    is_ro_mode = bool(
        rec_mode == "mode_d" and not has_write_intent and not has_code_files and changed_lines in (None, 0)
    )
    fast_bypass_eligible = bool(
        rec_mode == "mode_c"
        and total_loc <= max_loc
        and prompt_len <= max_chars
        and phase_count < 2
        and not role_conflicts
    )
    return is_ro_mode, fast_bypass_eligible


def _attach_track_fields(intent: Dict[str, Any], prompt_text: str) -> Dict[str, Any]:
    track = "CONTROL" if intent.get("read_only") else classify_intent_track(prompt_text)
    intent["classified_track"] = track
    intent["intent_track"] = track
    intent["rsi_profile"] = resolve_intent_track_profile(track)
    return intent


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
        return _attach_track_fields(_build_passive_handoff_intent(prompt), raw_text)

    has_code_files = bool(files)
    sel_idx = _parse_dashboard_selector(raw_text)
    if sel_idx is not None and not has_code_files and changed_lines in (None, 0):
        return _attach_track_fields(_build_dashboard_selector_intent(prompt, sel_idx, explicit_mode), raw_text)

    effective_raw = _extract_primary_stt_clause(raw_text)
    text_lower = effective_raw.lower()
    matched = _match_discovery_keywords(self.DISCOVERY_KEYWORDS, text_lower)
    domain_info = self.resolve_domain_from_manifest(effective_raw)

    has_write_intent, has_negated_write = _analyze_write_intent(_sanitize_tetralogia_filenames(text_lower))
    has_write_intent = has_write_intent or _has_destructive_shell_command(raw_text)
    phase_count = _count_prompt_phases(effective_raw, text_lower)
    prompt_len = len(raw_text)
    role_conflicts = _detect_prompt_role_conflicts(
        effective_raw, text_lower=text_lower, has_write_override=has_write_intent
    )
    total_loc = self._estimate_changed_loc(files=files, changed_lines=changed_lines)
    is_dom04_tech_audit = _is_dom04_tech_audit(domain_info, text_lower)
    is_gov_ro_audit, has_gov_ro_verb = _detect_gov_ro_audit(text_lower)

    if _is_mode_d_discovery_candidate(
        matched, has_negated_write, has_gov_ro_verb, has_code_files, has_write_intent, phase_count, changed_lines, explicit_mode
    ):
        return _attach_track_fields(
            _build_mode_d_discovery_intent(
                prompt, domain_info, is_dom04_tech_audit, is_gov_ro_audit, matched, has_gov_ro_verb, total_loc, role_conflicts
            ),
            effective_raw,
        )

    primary_ag = domain_info.get("primary_skill", "NK-Python-Async-Builder")
    matched_sk = domain_info.get("matched_skills", [primary_ag])
    native_sub = domain_info.get(
        "native_subagent",
        _resolve_native_subagent(domain_info["domain_id"], matched_skill=primary_ag, text=text_lower),
    )
    primary_ag, matched_sk, native_sub, dom_id_out, dom_name_out = _normalize_gov_ro_domain(
        is_gov_ro_audit, has_gov_ro_verb, has_write_intent, primary_ag, matched_sk, native_sub, domain_info
    )
    rec_mode = _resolve_escalation_mode(
        explicit_mode, phase_count, prompt_len, has_write_intent, matched, text_lower,
        total_loc, self.MODE_C_MAX_LOC, self.MODE_C_MAX_PROMPT_CHARS,
    )
    is_ro_mode, fast_bypass_eligible = _compute_intent_eligibility(
        rec_mode, has_write_intent, has_code_files, changed_lines, total_loc,
        self.MODE_C_MAX_LOC, prompt_len, self.MODE_C_MAX_PROMPT_CHARS, phase_count, role_conflicts,
    )
    return _attach_track_fields(
        _build_standard_intent(
            prompt, rec_mode, explicit_mode, is_ro_mode, fast_bypass_eligible, matched,
            primary_ag, matched_sk, native_sub, total_loc, phase_count, role_conflicts, dom_id_out, dom_name_out,
        ),
        effective_raw,
    )

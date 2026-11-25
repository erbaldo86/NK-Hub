"""Costruttore della busta L0 MetaPromptGateContract e valutazione gate."""

from __future__ import annotations

import hashlib
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.epistemic_firewall_rules import strip_zero_width_chars
from _internal.vibe_sprint_router import constants_core as _cc
from _internal.vibe_sprint_router.constants_core import _CLAUSE_SPLIT_RE  # noqa: F401
from _internal.vibe_sprint_router.constants_core import _get_ipc_contracts, _normalize_explicit_mode, _normalize_input_text
from _internal.vibe_sprint_router.envelope_renderers import _BULLET_NUM_DETECT_RE, _BULLET_NUM_SPLIT_RE, _MAX_REQUIREMENT_CLAUSES, _REQ_INLINE_DETECT_RE, _REQ_INLINE_SPLIT_RE, _REQ_PREFIX_RE, _VALID_CID_RE, _valid_cid_token  # noqa: F401
from _internal.vibe_sprint_router.envelope_renderers import (
    _active_v2_fallback_text,
    _extract_active_v2_requirements,
    _render_standard_envelope_texts,
    _resolve_cid,
    _split_requirement_clauses,
)
from _internal.vibe_sprint_router.prompt_linter import _detect_prompt_role_conflicts, _is_anti_loop_confirmation, is_passive_state_handoff
from _internal.vibe_sprint_router.stt_normalize import detect_active_continuation_handoff_impl, detect_outbound_handoff_intent_impl
from _internal.vibe_sprint_router.write_intent import _has_destructive_shell_command, _has_imperative_write_keyword

_SLASH_NONE: Dict[str, bool] = {"goal": False, "boost": False, "plan": False, "implementation": False}


def _build_outbound_handoff_state(outbound_mode: str, conversation_id: Optional[str]) -> Dict[str, Any]:
    """Costruisce lo stato bypass per serializzazione handoff in uscita."""
    cid = _resolve_cid(conversation_id)
    cid_flag = f" --conversation-id {cid}" if cid else ""
    handoff_cmd = f"python -B -u NK_Hub/scripts/nk_session_handoff.py --serialize --ecosystem-scan --mode {outbound_mode}{cid_flag}"
    return {
        "fsm_state": "BYPASSED", "bypassed": True, "bypass_reason": "EXECUTE_HANDOFF_SERIALIZE",
        "standby_mode": False, "auto_bypass_eligible": False, "rec_mode": "mode_d",
        "primary_ag": "NK-Scribe-Memory", "native_sub": "NK-Scribe-Agent",
        "intrinsic_protocols": [], "slash_equivalence": dict(_SLASH_NONE),
        "requirements_r_ids": [], "role_conflicts": [], "tools_allowed": ["run_command", "read_file"],
        "out_of_scope": ["Modifica codice applicativo o piano task (solo serializzazione handoff in sola lettura)"],
        "conceptual_mirror": f"{handoff_cmd} | EXECUTE_HANDOFF_SERIALIZE ({outbound_mode})",
        "optimized_meta_prompt": (
            "[META-PROMPT L0 | Mode: mode_d | Skill: NK-Scribe-Memory | BypassScope: EXECUTE_HANDOFF_SERIALIZE]\n"
            f"Comando: {handoff_cmd}\nProtocolli Intrinseci Auto-Attivati: NONE\n"
            "Direttiva: esegui subito il comando di serializzazione handoff e restituisci l'envelope verificato."
        ),
    }


def _build_standby_handoff_state() -> Dict[str, Any]:
    """Costruisce lo stato bypass passivo STATE_HANDOFF_STANDBY."""
    return {
        "fsm_state": "BYPASSED", "bypassed": True, "bypass_reason": "STATE_HANDOFF_STANDBY",
        "standby_mode": True, "auto_bypass_eligible": False, "rec_mode": "mode_d",
        "primary_ag": "NK-Orchestrator", "native_sub": "Orchestrator-Direct",
        "intrinsic_protocols": [], "slash_equivalence": dict(_SLASH_NONE),
        "requirements_r_ids": [], "role_conflicts": [], "tools_allowed": ["read_file"],
        "out_of_scope": [
            "Qualsiasi modifica ai file del repository (acquisizione stato 100% Read-Only)",
            "Attivazione autonoma di INTRINSIC_GOAL, INTRINSIC_PLAN, implementation_plan.md o ask_question prescrittivi",
        ],
        "conceptual_mirror": (
            "STATE_HANDOFF_STANDBY: acquisizione passiva dello stato della sessione precedente in sola lettura, "
            "divieto di proporre task autonomi o attivare implementation_plan.md, attesa in STANDBY delle decisioni dell'utente."
        ),
        "optimized_meta_prompt": (
            "[META-PROMPT L0 | Mode: mode_d | Skill: NK-Orchestrator | BypassScope: STATE_HANDOFF_STANDBY]\n"
            "Stato: STATE_HANDOFF_STANDBY (Passive Session State Handoff).\n"
            "Protocolli Intrinseci Auto-Attivati: NONE\nDirettiva: acquisisci lo stato verificato e rimani in STANDBY."
        ),
    }


def _resolve_stt_and_outbound(
    self: Any, prompt: str, norm_prompt: str, is_handoff_standby: bool, active_v2_payload: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], str, Optional[str]]:
    """Normalizza STT ed estrae eventuale intento outbound handoff."""
    if is_handoff_standby or active_v2_payload is not None:
        stt_info: Dict[str, Any] = {
            "raw_prompt": prompt or "", "cleaned_prompt": norm_prompt.strip(),
            "voice_corrections_applied": [], "camelcase_splits": [], "bypass_requested": False,
        }
        return stt_info, stt_info["cleaned_prompt"], None
    stt_info = self.normalize_voice_stt_input(norm_prompt)
    cleaned_prompt = stt_info["cleaned_prompt"] or norm_prompt.strip()
    outbound_mode = None if _has_destructive_shell_command(norm_prompt) else detect_outbound_handoff_intent_impl(cleaned_prompt)
    return stt_info, cleaned_prompt, outbound_mode


def _prepare_eval_text_and_reqs(active_v2_payload: Optional[Dict[str, Any]], cleaned_prompt: str) -> Tuple[bool, List[str], str]:
    """Estrae i requisiti R1..Rn e il testo di valutazione per flussi V2 o standard."""
    if active_v2_payload is None:
        raw_clauses = _split_requirement_clauses(cleaned_prompt)
        return False, [f"R{idx}: {clause}" for idx, clause in enumerate(raw_clauses, start=1)], cleaned_prompt
    requirements_r_ids = _extract_active_v2_requirements(active_v2_payload)
    inner_v2 = active_v2_payload.get("payload") if isinstance(active_v2_payload.get("payload"), dict) else active_v2_payload
    has_reqs = bool(inner_v2.get("requirements") or active_v2_payload.get("requirements"))
    reqs_joined = "; ".join(requirements_r_ids).strip()
    eval_text = reqs_joined if (has_reqs and reqs_joined) else _active_v2_fallback_text(active_v2_payload, inner_v2, reqs_joined)
    return True, requirements_r_ids, eval_text


def _is_prompt_gate_exempt_for_envelope(self: Any, norm_prompt: str, cleaned_prompt: str, stt_info: Dict[str, Any]) -> bool:
    """Verifica l'esenzione gate sul prompt grezzo o con richiesta bypass vocale."""
    if self.is_gate_exempt(norm_prompt):
        return True
    if not stt_info.get("bypass_requested") or "[nk-anchor:" in norm_prompt.lower() or _has_destructive_shell_command(norm_prompt):
        return False
    return bool(self.is_gate_exempt(f"!diretto {cleaned_prompt}"))


def _is_auto_bypass_eligible(
    classified_mode: str, rec_mode: str, intent: Dict[str, Any],
    files: Optional[List[str]], changed_lines: Optional[int], eval_text: str,
) -> bool:
    """Determina l'idoneita al Single-Gate Bypass per Mode D puro Read-Only."""
    if classified_mode != "mode_d" or rec_mode != "mode_d":
        return False
    if intent.get("read_only") is not True or bool(files) or changed_lines not in (None, 0):
        return False
    return not _has_imperative_write_keyword(eval_text) and not _has_destructive_shell_command(eval_text)


def _resolve_standard_gate_state(
    self: Any, norm_prompt: str, cleaned_prompt: str, stt_info: Dict[str, Any], gate_enabled: bool,
    effective_mode: str, auto_bypass_readonly: bool, classified_mode: str, rec_mode: str,
    intent: Dict[str, Any], eval_text: str, files: Optional[List[str]], changed_lines: Optional[int],
) -> Tuple[bool, str, Optional[str], str, bool, List[str]]:
    """Calcola bypassed, fsm_state, effective_mode e tools_allowed per richieste standard."""
    exempt = _is_prompt_gate_exempt_for_envelope(self, norm_prompt, cleaned_prompt, stt_info)
    bypassed = bool(exempt or (not gate_enabled) or effective_mode in ("OFF", "BYPASS"))
    fsm_state = "BYPASSED" if bypassed else ("CONFIRMED" if effective_mode == "ECHO" else "AWAIT_CONFIRM")
    bypass_reason: Optional[str] = None
    auto_bypass_eligible = _is_auto_bypass_eligible(classified_mode, rec_mode, intent, files, changed_lines, eval_text)
    if auto_bypass_readonly and auto_bypass_eligible and fsm_state == "AWAIT_CONFIRM":
        fsm_state, bypassed = "BYPASSED", True
        bypass_reason, effective_mode = "READONLY_MODE_D_BYPASS", "SINGLE_GATE_MODE_D"
    return bypassed, fsm_state, bypass_reason, effective_mode, auto_bypass_eligible, list(map(str, intent.get("tools_allowed") or ()))


def _build_standard_envelope_state(
    self: Any, norm_prompt: str, cleaned_prompt: str, stt_info: Dict[str, Any],
    active_v2_payload: Optional[Dict[str, Any]], gate_enabled: bool, effective_mode: str,
    explicit_mode: Optional[str], mode: Optional[str], files: Optional[List[str]],
    changed_lines: Optional[int], compact: bool, auto_bypass_readonly: bool,
) -> Tuple[Dict[str, Any], str]:
    """Costruisce lo stato completo dell'envelope per continuazioni V2 o prompt standard."""
    is_active_v2, requirements_r_ids, eval_text = _prepare_eval_text_and_reqs(active_v2_payload, cleaned_prompt)
    intent = self.classify_prompt_intent(eval_text, mode=mode, files=files, changed_lines=changed_lines)
    role_conflicts = [] if is_active_v2 else _detect_prompt_role_conflicts(norm_prompt)
    classified_mode = str(intent.get("recommended_mode", "mode_c"))
    rec_mode = explicit_mode or classified_mode
    primary_ag, native_sub = str(intent.get("primary_agent", "NK-Python-Async-Builder")), str(intent.get("native_subagent", "NK-Builder-Agent"))
    intrinsic_info = self.resolve_intrinsic_vibe_protocols(eval_text, recommended_mode=rec_mode)
    intrinsic_protocols = list(intrinsic_info["intrinsic_protocols"])
    slash_equivalence = dict(intrinsic_info["autonomous_slash_equivalence"])
    if not is_active_v2 and _is_anti_loop_confirmation(cleaned_prompt) and "INTRINSIC_PLAN" not in intrinsic_protocols:
        intrinsic_protocols.append("INTRINSIC_PLAN")
        slash_equivalence["plan"], slash_equivalence["implementation"] = True, True
    if is_active_v2:
        bypassed, fsm_state, bypass_reason, auto_bypass_eligible = False, "AWAIT_CONFIRM", None, False
        effective_mode, tools_allowed = "CONFIRM", ["read_file", "ask_question"]
    else:
        bypassed, fsm_state, bypass_reason, effective_mode, auto_bypass_eligible, tools_allowed = _resolve_standard_gate_state(
            self, norm_prompt, cleaned_prompt, stt_info, gate_enabled, effective_mode,
            auto_bypass_readonly, classified_mode, rec_mode, intent, eval_text, files, changed_lines,
        )
    out_of_scope, conceptual_mirror, optimized_meta_prompt = _render_standard_envelope_texts(
        compact, rec_mode, primary_ag, native_sub, bypassed, bypass_reason, eval_text, requirements_r_ids, ", ".join(intrinsic_protocols)
    )
    return {
        "fsm_state": fsm_state, "bypassed": bypassed, "bypass_reason": bypass_reason, "standby_mode": False,
        "auto_bypass_eligible": auto_bypass_eligible, "rec_mode": rec_mode, "primary_ag": primary_ag,
        "native_sub": native_sub, "intrinsic_protocols": intrinsic_protocols, "slash_equivalence": slash_equivalence,
        "requirements_r_ids": requirements_r_ids, "role_conflicts": role_conflicts, "tools_allowed": tools_allowed,
        "out_of_scope": out_of_scope, "conceptual_mirror": conceptual_mirror, "optimized_meta_prompt": optimized_meta_prompt,
    }, effective_mode


def _finalize_envelope_result(
    self: Any, state: Dict[str, Any], stt_info: Dict[str, Any], gate_enabled: bool, effective_mode: str, compact: bool
) -> Dict[str, Any]:
    """Calcola hash, brief_id, bypass_scope, valida il contratto Pydantic e renderizza Markdown."""
    reqs, opt_prompt = state["requirements_r_ids"], state["optimized_meta_prompt"]
    intent_hash = hashlib.sha256(f"{opt_prompt}|{'|'.join(reqs)}".encode("utf-8")).hexdigest()
    brief_id = f"IB-{time.strftime('%Y%m%d')}-{intent_hash[:6].upper()}"
    if state["bypass_reason"] == "EXECUTE_HANDOFF_SERIALIZE":
        bypass_scope = "EXECUTE_HANDOFF_SERIALIZE"
    elif state["standby_mode"]:
        bypass_scope = "STATE_HANDOFF_STANDBY"
    else:
        bypass_scope = "L0_GATE_ONLY" if (state["bypassed"] or state["fsm_state"] == "BYPASSED") else "NONE"
    payload: Dict[str, Any] = {
        "brief_id": brief_id, "fsm_state": state["fsm_state"], "gate_mode": effective_mode,
        "enabled": bool(gate_enabled and effective_mode != "OFF"), "bypassed": state["bypassed"],
        "bypass_reason": state["bypass_reason"], "bypass_scope": bypass_scope,
        "auto_bypass_eligible": state["auto_bypass_eligible"], "standby_mode": state["standby_mode"],
        "conceptual_mirror": state["conceptual_mirror"], "optimized_meta_prompt": opt_prompt,
        "requirements_r_ids": reqs, "voice_corrections_applied": list(stt_info.get("voice_corrections_applied", [])),
        "out_of_scope": state["out_of_scope"], "ambiguities": list(state["role_conflicts"]),
        "recommended_mode": state["rec_mode"], "primary_agent": state["primary_ag"], "native_subagent": state["native_sub"],
        "tools_allowed": state["tools_allowed"], "intrinsic_protocols": state["intrinsic_protocols"],
        "autonomous_slash_equivalence": state["slash_equivalence"], "intent_hash_sha256": intent_hash, "ttl_seconds": 1800,
    }
    mp_contract_cls = _get_ipc_contracts()[0] if "pydantic" in sys.modules else _cc.MetaPromptGateContract
    result = mp_contract_cls(**payload).model_dump() if mp_contract_cls is not None else dict(payload)
    result.update({
        "topology_2tier_mandatory": True, "staging_2pc_mandatory": state["rec_mode"] != "mode_d",
        "max_direct_tools": 12, "compact_profile": bool(compact), "three_pillar_mirror_only": True,
    })
    result["rendered_markdown"] = self.format_meta_prompt_markdown(result)
    return result


def evaluate_meta_prompt_gate_impl(self, raw_prompt: str, **kwargs: Any) -> Dict[str, Any]:
    """Valuta il Gate L0 sul prompt fornito delegando a build_meta_prompt_envelope."""
    if "conversation_id" in kwargs:
        return build_meta_prompt_envelope_impl(self, prompt=raw_prompt, **kwargs)
    return self.build_meta_prompt_envelope(prompt=raw_prompt, **kwargs)


def build_meta_prompt_envelope_impl(
    self, prompt: str, gate_enabled: bool = True, gate_mode: str = "CONFIRM",
    files: Optional[List[str]] = None, compact: bool = False, auto_bypass_readonly: bool = True,
    mode: Optional[str] = None, changed_lines: Optional[int] = None, conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Costruisce e valida il contratto MetaPromptGateContract di Livello 0."""
    norm_prompt = strip_zero_width_chars(_normalize_input_text(prompt))
    is_handoff_standby = is_passive_state_handoff(norm_prompt)
    active_v2_payload = None if is_handoff_standby else detect_active_continuation_handoff_impl(norm_prompt)
    stt_info, cleaned_prompt, outbound_mode = _resolve_stt_and_outbound(self, prompt, norm_prompt, is_handoff_standby, active_v2_payload)
    effective_mode = (gate_mode or "CONFIRM").strip().upper()
    if effective_mode not in ("CONFIRM", "ECHO", "OFF", "BYPASS", "SINGLE_GATE_MODE_D"):
        effective_mode = "CONFIRM"
    if outbound_mode is not None:
        state = _build_outbound_handoff_state(outbound_mode, conversation_id)
    elif is_handoff_standby:
        state = _build_standby_handoff_state()
    else:
        state, effective_mode = _build_standard_envelope_state(
            self, norm_prompt, cleaned_prompt, stt_info, active_v2_payload, gate_enabled, effective_mode,
            _normalize_explicit_mode(mode), mode, files, changed_lines, compact, auto_bypass_readonly,
        )
    return _finalize_envelope_result(self, state, stt_info, gate_enabled, effective_mode, compact)

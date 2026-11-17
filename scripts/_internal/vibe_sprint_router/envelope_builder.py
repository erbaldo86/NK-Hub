"""Costruttore della busta L0 MetaPromptGateContract e valutazione gate."""

from __future__ import annotations

import hashlib
import re
import sys
import time
from typing import Any, Dict, List, Optional

from _internal.vibe_sprint_router import constants_core as _cc
from _internal.vibe_sprint_router.constants_core import (
    _CLAUSE_SPLIT_RE,
    _get_ipc_contracts,
    _normalize_explicit_mode,
    _normalize_input_text,
)
from _internal.vibe_sprint_router.prompt_linter import (
    _detect_prompt_role_conflicts,
    _is_anti_loop_confirmation,
    is_passive_state_handoff,
)
from _internal.vibe_sprint_router.write_intent import (
    _has_destructive_shell_command,
    _has_imperative_write_keyword,
)

_MAX_REQUIREMENT_CLAUSES: int = 64
_REQ_INLINE_SPLIT_RE = re.compile(r"\s+(?=(?:[-*+]\s+)?R\d+\s*:)")
_REQ_INLINE_DETECT_RE = re.compile(r"(?:^|\s)(?:[-*+]\s+)?R\d+\s*:")
_BULLET_NUM_SPLIT_RE = re.compile(r"\s+(?=\d+\)\s+)")
_BULLET_NUM_DETECT_RE = re.compile(r"(?:^|\s)\d+\)\s+")


def _split_requirement_clauses(cleaned_prompt: str) -> List[str]:
    """Estrae le clausole requisito sull'intero prompt conservando R7+ e coda >16KB entro 64 clausole."""
    raw_clauses: List[str] = []
    for seg in _CLAUSE_SPLIT_RE.split(cleaned_prompt):
        seg_clean = seg.strip(" .;")
        if not seg_clean or len(seg_clean) < 3:
            continue
        if len(_REQ_INLINE_DETECT_RE.findall(seg_clean)) >= 2:
            sub_parts = _REQ_INLINE_SPLIT_RE.split(seg_clean)
        elif len(_BULLET_NUM_DETECT_RE.findall(seg_clean)) >= 2:
            sub_parts = _BULLET_NUM_SPLIT_RE.split(seg_clean)
        else:
            sub_parts = [seg_clean]
        for part in sub_parts:
            p_clean = part.strip(" .;")
            if p_clean and len(p_clean) >= 3:
                raw_clauses.append(p_clean)
    if len(raw_clauses) > _MAX_REQUIREMENT_CLAUSES:
        raw_clauses = raw_clauses[:48] + raw_clauses[-16:]
    if not raw_clauses:
        raw_clauses = [cleaned_prompt or "Eseguire il task richiesto"]
    return raw_clauses


def evaluate_meta_prompt_gate_impl(
    self,
    raw_prompt: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Valuta il Gate L0 sul prompt fornito delegando a build_meta_prompt_envelope."""
    return self.build_meta_prompt_envelope(prompt=raw_prompt, **kwargs)


def build_meta_prompt_envelope_impl(
    self,
    prompt: str,
    gate_enabled: bool = True,
    gate_mode: str = "CONFIRM",
    files: Optional[List[str]] = None,
    compact: bool = False,
    auto_bypass_readonly: bool = True,
    mode: Optional[str] = None,
    changed_lines: Optional[int] = None,
) -> Dict[str, Any]:
    """Costruisce e valida il contratto MetaPromptGateContract di Livello 0."""
    norm_prompt = _normalize_input_text(prompt)
    is_handoff_standby = is_passive_state_handoff(norm_prompt)
    stt_info = self.normalize_voice_stt_input(norm_prompt)
    exempt = (
        is_handoff_standby
        or self.is_gate_exempt(norm_prompt)
        or bool(
            stt_info.get("bypass_requested")
            and not _has_destructive_shell_command(norm_prompt)
        )
    )
    cleaned_prompt = stt_info["cleaned_prompt"] or norm_prompt.strip()
    intent = self.classify_prompt_intent(
        cleaned_prompt, mode=mode, files=files, changed_lines=changed_lines
    )
    role_conflicts = (
        []
        if is_handoff_standby
        else _detect_prompt_role_conflicts(norm_prompt)
    )

    effective_mode = (gate_mode or "CONFIRM").strip().upper()
    if effective_mode not in (
        "CONFIRM",
        "ECHO",
        "OFF",
        "BYPASS",
        "SINGLE_GATE_MODE_D",
    ):
        effective_mode = "CONFIRM"

    bypassed = bool(
        exempt or (not gate_enabled) or effective_mode in ("OFF", "BYPASS")
    )
    if is_handoff_standby or bypassed:
        fsm_state = "BYPASSED"
    elif effective_mode == "ECHO":
        fsm_state = "CONFIRMED"
    else:
        fsm_state = "AWAIT_CONFIRM"

    raw_clauses = _split_requirement_clauses(cleaned_prompt)
    requirements_r_ids = [
        f"R{idx}: {clause}" for idx, clause in enumerate(raw_clauses, start=1)
    ]

    explicit_mode = _normalize_explicit_mode(mode)
    classified_mode = str(intent.get("recommended_mode", "mode_c"))

    if is_handoff_standby:
        rec_mode = "mode_d"
        primary_ag = "NK-Orchestrator"
        native_sub = "Orchestrator-Direct"
        intrinsic_protocols: List[str] = []
        slash_equivalence: Dict[str, bool] = {
            "goal": False,
            "boost": False,
            "plan": False,
            "implementation": False,
        }
        bypass_reason: Optional[str] = "STATE_HANDOFF_STANDBY"
        standby_mode = True
        out_of_scope = [
            "Qualsiasi modifica ai file del repository (acquisizione stato 100% Read-Only)",
            "Attivazione autonoma di INTRINSIC_GOAL, INTRINSIC_PLAN, implementation_plan.md o ask_question prescrittivi",
        ]
        conceptual_mirror = (
            "STATE_HANDOFF_STANDBY: acquisizione passiva dello stato della sessione "
            "precedente in sola lettura, divieto di proporre task autonomi o attivare "
            "implementation_plan.md, attesa in STANDBY delle decisioni dell'utente."
        )
        optimized_meta_prompt = (
            "[META-PROMPT L0 | Mode: mode_d | Skill: NK-Orchestrator | "
            "BypassScope: STATE_HANDOFF_STANDBY]\n"
            "Stato: STATE_HANDOFF_STANDBY (Passive Session State Handoff).\n"
            "Protocolli Intrinseci Auto-Attivati: NONE\n"
            "Direttiva: acquisisci lo stato verificato e rimani in STANDBY."
        )
    else:
        rec_mode = explicit_mode or classified_mode
        primary_ag = str(intent.get("primary_agent", "NK-Python-Async-Builder"))
        native_sub = str(intent.get("native_subagent", "NK-Builder-Agent"))

        intrinsic_info = self.resolve_intrinsic_vibe_protocols(
            cleaned_prompt, recommended_mode=rec_mode
        )
        intrinsic_protocols = list(intrinsic_info["intrinsic_protocols"])
        slash_equivalence = dict(intrinsic_info["autonomous_slash_equivalence"])
        if (
            _is_anti_loop_confirmation(cleaned_prompt)
            and "INTRINSIC_PLAN" not in intrinsic_protocols
        ):
            intrinsic_protocols.append("INTRINSIC_PLAN")
            slash_equivalence["plan"] = True
            slash_equivalence["implementation"] = True
        protocols_str = ", ".join(intrinsic_protocols)
        bypass_reason = None
        standby_mode = False

    auto_bypass_eligible = bool(
        not is_handoff_standby
        and classified_mode == "mode_d"
        and rec_mode == "mode_d"
        and intent.get("read_only") is True
        and not files
        and (changed_lines is None or changed_lines == 0)
        and not _has_imperative_write_keyword(cleaned_prompt)
        and not _has_destructive_shell_command(cleaned_prompt)
    )
    if (
        not is_handoff_standby
        and auto_bypass_readonly
        and auto_bypass_eligible
        and fsm_state == "AWAIT_CONFIRM"
    ):
        fsm_state = "BYPASSED"
        bypassed = True
        bypass_reason = "READONLY_MODE_D_BYPASS"
        effective_mode = "SINGLE_GATE_MODE_D"

    if not is_handoff_standby:
        if compact:
            out_of_scope = (
                ["Read-Only"]
                if rec_mode == "mode_d"
                else ["Solo .staging/"]
            )
            conceptual_mirror = f"{cleaned_prompt[:48]} ({rec_mode}/{primary_ag})."
            optimized_meta_prompt = (
                f"[L0:{rec_mode}:{primary_ag}] {cleaned_prompt[:64]} | "
                f"{'; '.join(requirements_r_ids)}"
            )
        else:
            if rec_mode == "mode_d":
                out_of_scope = [
                    "Qualsiasi modifica ai file del repository (esecuzione 100% Read-Only)",
                    "Esecuzione di commit transazionali 2PC",
                ]
                nk_guidance = (
                    "Regolamento NK: opera in sola lettura (Mode D) e verifica le fonti."
                )
            else:
                out_of_scope = [
                    "Modifica diretta dei file di produzione fuori da .staging/",
                    "Uso di MagicMock o stub sintetici vietati da RULE-01.2",
                ]
                nk_guidance = (
                    "Regolamento NK: dopo la conferma L0, prepara Brief in nk_genome/ e "
                    "implementation_plan.md confermato dall'utente (RequestFeedback: true) "
                    "prima di delegare la scrittura codice ai Builder in .staging/, "
                    "applica commit 2PC e convergenza RSI."
                )

            if bypassed:
                out_of_scope.append(
                    "Bypass L0_GATE_ONLY: topologia 2-Tier (max 12 tool diretti) e .staging/ + 2PC restano obbligatori"
                )

            if len(cleaned_prompt) <= 240:
                mirror_summary = cleaned_prompt
            else:
                head_cut = cleaned_prompt[:140].rsplit(" ", 1)[0].rstrip(" ,;:")
                head_part = head_cut or cleaned_prompt[:140]
                tail_slice = cleaned_prompt[-90:]
                tail_part = (
                    tail_slice.split(" ", 1)[1]
                    if " " in tail_slice and not tail_slice.startswith(" ")
                    else tail_slice
                ).lstrip(" ,;:") or tail_slice
                mirror_summary = f"{head_part} ... {tail_part}"
            if bypass_reason == "READONLY_MODE_D_BYPASS":
                header_line = (
                    f"[META-PROMPT L0 | Mode: {rec_mode} | "
                    f"Single-Gate: READONLY_MODE_D_BYPASS | Skill: {primary_ag}]"
                )
            else:
                scope_tag = " | BypassScope: L0_GATE_ONLY" if bypassed else ""
                header_line = (
                    f"[META-PROMPT L0 | Mode: {rec_mode} | Skill: {primary_ag}{scope_tag}]"
                )
            optimized_meta_prompt = (
                f"{header_line}\n"
                f"Obiettivo ad alto livello: {cleaned_prompt}\n"
                f"Requisiti: {'; '.join(requirements_r_ids)}\n"
                f"Protocolli Intrinseci Auto-Attivati: {protocols_str}\n"
                f"{nk_guidance}"
            )
            conceptual_mirror = (
                f"Obiettivo: {mirror_summary} "
                f"(Modalita: {rec_mode}, Skill: {primary_ag}, Sub-Agente: {native_sub}, "
                f"Protocolli: {protocols_str}). {nk_guidance}"
            )

    hash_input = f"{optimized_meta_prompt}|{'|'.join(requirements_r_ids)}"
    intent_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    brief_id = f"IB-{time.strftime('%Y%m%d')}-{intent_hash[:6].upper()}"

    payload: Dict[str, Any] = {
        "brief_id": brief_id,
        "fsm_state": fsm_state,
        "gate_mode": effective_mode,
        "enabled": bool(gate_enabled and effective_mode != "OFF"),
        "bypassed": bypassed,
        "bypass_reason": bypass_reason,
        "auto_bypass_eligible": auto_bypass_eligible,
        "standby_mode": standby_mode,
        "conceptual_mirror": conceptual_mirror,
        "optimized_meta_prompt": optimized_meta_prompt,
        "requirements_r_ids": requirements_r_ids,
        "voice_corrections_applied": list(
            stt_info.get("voice_corrections_applied", [])
        ),
        "out_of_scope": out_of_scope,
        "ambiguities": list(role_conflicts),
        "recommended_mode": rec_mode,
        "primary_agent": primary_ag,
        "native_subagent": native_sub,
        "intrinsic_protocols": intrinsic_protocols,
        "autonomous_slash_equivalence": slash_equivalence,
        "intent_hash_sha256": intent_hash,
        "ttl_seconds": 1800,
    }

    if "pydantic" in sys.modules:
        mp_contract_cls, _ = _get_ipc_contracts()
    else:
        mp_contract_cls = _cc.MetaPromptGateContract

    if mp_contract_cls is not None:
        validated = mp_contract_cls(**payload)
        result = validated.model_dump()
    else:
        result = dict(payload)

    result["bypass_reason"] = bypass_reason
    result["auto_bypass_eligible"] = auto_bypass_eligible
    result["standby_mode"] = standby_mode
    result["bypass_scope"] = (
        "STATE_HANDOFF_STANDBY"
        if is_handoff_standby
        else ("L0_GATE_ONLY" if (bypassed or fsm_state == "BYPASSED") else "NONE")
    )
    result["topology_2tier_mandatory"] = True
    result["staging_2pc_mandatory"] = rec_mode != "mode_d"
    result["max_direct_tools"] = 12
    result["compact_profile"] = bool(compact)
    result["three_pillar_mirror_only"] = True
    result["rendered_markdown"] = self.format_meta_prompt_markdown(result)
    return result

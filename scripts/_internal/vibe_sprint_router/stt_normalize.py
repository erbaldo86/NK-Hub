"""Normalizzazione STT, intent handoff, esenzione bypass gate, protocolli intrinseci e rendering L0."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.epistemic_firewall_rules import (
    _OUTBOUND_CODE_EXCLUSION_RE,
    detect_outbound_handoff_intent_fast,
    parse_verified_handoff_v2_wire,
    strip_zero_width_chars,
)
from _internal.vibe_sprint_router.constants_core import _BRIEF_HEADER_PHASE_RE, _HANDOFF_MUTATING_ORDER_RE, _TECH_CAMEL_ALLOWLIST  # noqa: F401
from _internal.vibe_sprint_router.constants_core import (
    _INTRINSIC_BOOST_KEYWORDS,
    _INTRINSIC_PLAN_KEYWORDS,
    _normalize_explicit_mode,
    _normalize_input_text,
)
from _internal.vibe_sprint_router.constants_stt import _ANALYTICAL_INTERROGATIVE_PREFIXES, _BP_ANY_RE, _BP_DIRETTO_RE, _BP_RAW_RE, _CAMEL_GLUED_RE, _CODE_SPAN_RE, _EXPLICIT_BYPASS_NEG_RES, _FIRST_WORD_RE, _NODE_SELECTIONS, _ONBOARDING_TRIGGERS, _PUNCT_NORM_RE, _SALTA_GATE_RE, _SENT_SPLIT_RE, _SHELL_META_EXEMPT_BLOCKERS, _STT_INDEPENDENT_ACTION_START_RE, _VOICE_CORRECTION_PATTERNS, _VOICE_SELF_CORRECTION_MARKERS, _normalize_trigger_text  # noqa: F401
from _internal.vibe_sprint_router.constants_stt import _MULTI_SPACE_RE, _parse_dashboard_selector
from _internal.vibe_sprint_router.prompt_linter import _is_anti_loop_confirmation  # noqa: F401
from _internal.vibe_sprint_router.prompt_linter import is_passive_state_handoff
from _internal.vibe_sprint_router.stt_helpers import _apply_self_correction_marker, _choose_self_corrected_text, _is_unsafe_bypass_prompt, _resolve_prefix_after_correction, _starts_with_analytical_word  # noqa: F401
from _internal.vibe_sprint_router.stt_helpers import (
    _apply_voice_corrections,
    _check_explicit_bypass_toggle,
    _is_exempt_short_trigger,
    _is_safe_env_capsule,
    _mask_code_spans,
    _split_glued_camelcase,
    _strip_voice_bypass_markers,
)
from _internal.vibe_sprint_router.write_intent import _has_imperative_write_keyword  # noqa: F401
from _internal.vibe_sprint_router.write_intent import _has_destructive_shell_command

_OUTBOUND_ANCHOR_BLOCK_MARKERS: Tuple[str, ...] = (
    "[nk-anchor:start:",
    "[handoff stato sessione nk-hub]",
    "passive_session_state_handoff",
    "handoff_v2:",
)


def is_passive_state_handoff_impl(self, raw_prompt: str) -> bool:
    """Restituisce True se il prompt contiene un marker di Passive Session State Handoff."""
    return is_passive_state_handoff(raw_prompt)


def _has_outbound_handoff_blocker(clean: str) -> bool:
    """Esclude prompt con comandi distruttivi, anchor passivi o esclusioni codice."""
    if _has_destructive_shell_command(clean):
        return True
    low = clean.lower()
    if any(marker in low for marker in _OUTBOUND_ANCHOR_BLOCK_MARKERS):
        return True
    return is_passive_state_handoff(clean) or parse_verified_handoff_v2_wire(clean) is not None


def detect_outbound_handoff_intent_impl(text: str) -> Optional[str]:
    """Rileva l'intento di serializzazione handoff in uscita escludendo anchor, code edit e shell distruttive."""
    clean = strip_zero_width_chars(_normalize_input_text(text)).strip()
    if not clean or _has_outbound_handoff_blocker(clean):
        return None
    if _OUTBOUND_CODE_EXCLUSION_RE.search(clean):
        return None
    return detect_outbound_handoff_intent_fast(clean)


def detect_active_continuation_handoff_impl(text: str) -> Optional[Dict[str, Any]]:
    """Rileva ed estrae un handoff V2 ACTIVE_CONTINUATION verificato tramite parse_verified_handoff_v2_wire."""
    clean = strip_zero_width_chars(_normalize_input_text(text)).strip()
    if not clean:
        return None
    parsed = parse_verified_handoff_v2_wire(clean)
    if not isinstance(parsed, dict):
        return None
    payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {}
    mode_val = str(payload.get("handoff_mode") or parsed.get("mode") or "").upper()
    return parsed if mode_val == "ACTIVE_CONTINUATION" else None


def _detect_intrinsic_protocol_flags(text_low: str, rec_mode: str) -> Tuple[bool, bool, bool]:
    """Calcola i flag boolean di attivazione per GOAL, BOOST e PLAN."""
    boost_active = rec_mode in ("mode_a", "mode_d") or any(kw in text_low for kw in _INTRINSIC_BOOST_KEYWORDS)
    plan_active = rec_mode in ("mode_a", "mode_b") or any(kw in text_low for kw in _INTRINSIC_PLAN_KEYWORDS)
    return True, boost_active, plan_active


def resolve_intrinsic_vibe_protocols_impl(self, prompt: str, recommended_mode: str = "mode_c") -> Dict[str, Any]:
    """Rileva e attiva autonomamente INTRINSIC_GOAL, INTRINSIC_BOOST e INTRINSIC_PLAN."""
    text = strip_zero_width_chars(_normalize_input_text(prompt)).strip()
    if is_passive_state_handoff_impl(self, text) or detect_outbound_handoff_intent_impl(text) is not None:
        return {
            "intrinsic_protocols": [],
            "autonomous_slash_equivalence": {"goal": False, "boost": False, "plan": False, "implementation": False},
            "goal": False, "boost": False, "plan": False, "implementation": False, "recommended_mode": "mode_d",
        }
    rec_mode = _normalize_explicit_mode(recommended_mode) or (recommended_mode or "mode_c").strip().lower()
    goal_active, boost_active, plan_active = _detect_intrinsic_protocol_flags(text.lower(), rec_mode)
    protocols = [
        name for name, active in (("INTRINSIC_GOAL", goal_active), ("INTRINSIC_BOOST", boost_active), ("INTRINSIC_PLAN", plan_active))
        if active
    ]
    slash_equivalence: Dict[str, bool] = {"goal": goal_active, "boost": boost_active, "plan": plan_active, "implementation": plan_active}
    return {
        "intrinsic_protocols": protocols, "autonomous_slash_equivalence": slash_equivalence,
        "goal": goal_active, "boost": boost_active, "plan": plan_active,
        "implementation": plan_active, "recommended_mode": rec_mode,
    }


def normalize_voice_stt_input_impl(self, raw_prompt: str) -> Dict[str, Any]:
    """Normalizza il testo dettato a voce separando CamelCase fusi ed estraendo correzioni."""
    text = _normalize_input_text(raw_prompt).strip()
    if not text:
        return {
            "raw_prompt": raw_prompt or "", "cleaned_prompt": "",
            "voice_corrections_applied": [], "camelcase_splits": [], "bypass_requested": False,
        }
    masked, code_spans = _mask_code_spans(text)
    voice_corrections: List[str] = []
    camelcase_splits: List[str] = []
    masked, bypass_requested = _strip_voice_bypass_markers(masked)
    masked = _split_glued_camelcase(masked, voice_corrections, camelcase_splits)
    masked = _apply_voice_corrections(masked, voice_corrections)
    masked = _MULTI_SPACE_RE.sub(" ", masked).strip()
    for idx, span in enumerate(code_spans):
        masked = masked.replace(f"__NK_CODE_{idx}__", span)
    return {
        "raw_prompt": raw_prompt, "cleaned_prompt": masked,
        "voice_corrections_applied": voice_corrections,
        "camelcase_splits": camelcase_splits, "bypass_requested": bypass_requested,
    }


def _is_handoff_or_selector_exempt(text: str, text_low: str) -> Optional[bool]:
    """Valuta esenzioni immediate per anchor passivi, handoff V2 e selettori dashboard."""
    if "[nk-anchor:" in text_low:
        return is_passive_state_handoff(text)
    if detect_active_continuation_handoff_impl(text) is not None:
        return False
    if is_passive_state_handoff(text) or detect_outbound_handoff_intent_impl(text) is not None:
        return True
    return True if _parse_dashboard_selector(text) is not None else None


def is_gate_exempt_impl(self, raw_prompt: str) -> bool:
    """Verifica le esenzioni anti-loop, handoff e standby per il Super Meta-Prompt Gate (RULE-00.6)."""
    text = strip_zero_width_chars(_normalize_input_text(raw_prompt)).strip()
    if not text:
        return True
    if _has_destructive_shell_command(text):
        return False
    text_low = text.lower()
    handoff_res = _is_handoff_or_selector_exempt(text, text_low)
    if handoff_res is not None:
        return handoff_res
    if _is_safe_env_capsule(text, text_low):
        return True
    toggle_res = _check_explicit_bypass_toggle(text, text_low)
    if toggle_res is not None:
        return toggle_res
    return _is_exempt_short_trigger(text_low)


def _resolve_markdown_protocols(envelope: Dict[str, Any]) -> str:
    """Restituisce la stringa formattata dei protocolli attivi nel blocco L0."""
    if envelope.get("standby_mode"):
        return "NONE (STATE_HANDOFF_STANDBY)"
    if envelope.get("bypass_reason") == "EXECUTE_HANDOFF_SERIALIZE":
        return "NONE (EXECUTE_HANDOFF_SERIALIZE)"
    return ", ".join(envelope.get("intrinsic_protocols") or ()) or "INTRINSIC_GOAL"


def _join_envelope_list(envelope: Dict[str, Any], key: str, empty_label: str) -> str:
    """Unisce una lista opzionale dell'envelope con fallback esplicito."""
    items = envelope.get(key)
    return "; ".join(items) if items else empty_label


def _format_bypassed_l0_markdown(
    brief_id: str, fsm_state: str, intent_hash: str, mirror: str, reqs: List[str],
    rec_mode: str, primary_ag: str, native_sub: str, protos: str, out_scope: str, ambiguities: str,
) -> str:
    """Formatta il blocco compatto L0 per lo stato BYPASSED."""
    return "\n".join([
        "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]",
        f"- **Brief ID:** `{brief_id}` | **Stato FSM:** `{fsm_state}` | **Hash:** `{intent_hash[:12]}`",
        f"- **1. Intenzione:** {mirror[:160]} ({reqs[0] if reqs else 'R1'})",
        f"- **2. Come Farlo:** `{rec_mode}` | **Skill:** `{primary_ag}` | **Sub-Agente:** `{native_sub}` | **Protocolli:** `{protos}`",
        f"- **3. Regole e Perimetro:** {out_scope[:120]} | **Ambiguità:** {ambiguities}",
    ])


def _format_full_l0_markdown(
    brief_id: str, fsm_state: str, intent_hash: str, mirror: str, reqs: List[str], voice_corrs: str,
    rec_mode: str, primary_ag: str, native_sub: str, protos: str, out_scope: str, ambiguities: str,
) -> str:
    """Formatta il blocco esteso a tre passaggi L0 per AWAIT_CONFIRM o CONFIRMED."""
    req_lines = [f"  * {r}" for r in reqs] if reqs else ["  * R1: Eseguire il task richiesto"]
    lines = [
        "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]",
        f"- **Brief ID:** `{brief_id}` | **Stato FSM:** `{fsm_state}`",
        f"- **Intent Hash SHA-256:** `{intent_hash}`",
        "- **1. Intenzione:**",
        f"- **Specchio Concettuale (Meta-Prompt Integrato):** {mirror}",
        "- **Requisiti Tracciabili (R1..Rn):**",
        *req_lines,
        f"- **Correzioni vocali recepite:** {voice_corrs}",
        "- **2. Come Farlo:**",
        f"- **Modalità Consigliata:** `{rec_mode}` | **Skill:** `{primary_ag}` | **Sub-Agente:** `{native_sub}`",
        f"- **Protocolli Intrinseci Auto-Attivati:** `{protos}`",
        "- **Flusso Post-Conferma L0:** 1) Creazione Brief in `nk_genome/` e `implementation_plan.md` confermato dall'utente (`RequestFeedback: true`) -> 2) Delega scrittura codice ai Builder in `.staging/` -> 3) Audit RSI e Commit 2PC.",
        "- **3. Regole e Perimetro:**",
        f"- **Fuori ambito:** {out_scope}",
        f"- **Ambiguità rilevate:** {ambiguities}",
        "- **Divieto 4° Blocco ([NO-RAW-META-PROMPT]):** Vietato stampare il campo interno optimized_meta_prompt ([META-PROMPT L0]) come 4° blocco separato; le intenzioni sono già integrate nei 3 passaggi.",
    ]
    if fsm_state == "AWAIT_CONFIRM":
        lines.append("- **Stop Pre-Esecuzione (`AWAIT_CONFIRM`):** Fermati subito dopo questo specchio e invoca `ask_question`. Vietato eseguire il task prima della conferma utente e vietato posticipare il Gate L0 a fine task.")
    lines.append("- [MANDATORY-VISIBLE-L0]: Mostra obbligatoriamente questo blocco nel campo content della risposta PRIMA o INSIEME a ask_question (vietato content_len=0).")
    return "\n".join(lines)


def format_meta_prompt_markdown_impl(self, envelope: Dict[str, Any]) -> str:
    """Formatta il blocco Markdown visibile di Livello 0 per il campo content prima di ask_question."""
    brief_id, fsm_state = str(envelope.get("brief_id", "IB-UNKNOWN")), str(envelope.get("fsm_state", "AWAIT_CONFIRM"))
    rec_mode, primary_ag = str(envelope.get("recommended_mode", "mode_c")), str(envelope.get("primary_agent", "NK-Python-Async-Builder"))
    native_sub, protos = str(envelope.get("native_subagent", "NK-Builder-Agent")), _resolve_markdown_protocols(envelope)
    intent_hash, mirror = str(envelope.get("intent_hash_sha256", "")), str(envelope.get("conceptual_mirror", ""))
    reqs = list(envelope.get("requirements_r_ids") or ())
    voice_corrs = _join_envelope_list(envelope, "voice_corrections_applied", "Nessuna")
    out_scope = _join_envelope_list(envelope, "out_of_scope", "Nessuno")
    ambiguities = _join_envelope_list(envelope, "ambiguities", "Nessuna")
    if fsm_state == "BYPASSED":
        return _format_bypassed_l0_markdown(brief_id, fsm_state, intent_hash, mirror, reqs, rec_mode, primary_ag, native_sub, protos, out_scope, ambiguities)
    return _format_full_l0_markdown(brief_id, fsm_state, intent_hash, mirror, reqs, voice_corrs, rec_mode, primary_ag, native_sub, protos, out_scope, ambiguities)

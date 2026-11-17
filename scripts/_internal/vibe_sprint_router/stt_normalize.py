"""Normalizzazione STT, esenzione bypass gate, protocolli intrinseci e rendering L0."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from _internal.vibe_sprint_router.constants_core import (
    _INTRINSIC_BOOST_KEYWORDS,
    _INTRINSIC_PLAN_KEYWORDS,
    _TECH_CAMEL_ALLOWLIST,
    _normalize_explicit_mode,
    _normalize_input_text,
)
from _internal.vibe_sprint_router.constants_stt import (
    _ANALYTICAL_INTERROGATIVE_PREFIXES,
    _BP_ANY_RE,
    _BP_DIRETTO_RE,
    _BP_RAW_RE,
    _CAMEL_GLUED_RE,
    _CODE_SPAN_RE,
    _EXPLICIT_BYPASS_NEG_RES,
    _FIRST_WORD_RE,
    _MULTI_SPACE_RE,
    _NODE_SELECTIONS,
    _ONBOARDING_TRIGGERS,
    _PUNCT_NORM_RE,
    _SALTA_GATE_RE,
    _SENT_SPLIT_RE,
    _SHELL_META_EXEMPT_BLOCKERS,
    _STT_INDEPENDENT_ACTION_START_RE,
    _VOICE_CORRECTION_PATTERNS,
    _VOICE_SELF_CORRECTION_MARKERS,
    _normalize_trigger_text,
    _parse_dashboard_selector,
)
from _internal.vibe_sprint_router.prompt_linter import (
    _is_anti_loop_confirmation,
    is_passive_state_handoff,
)
from _internal.vibe_sprint_router.write_intent import (
    _has_destructive_shell_command,
    _has_imperative_write_keyword,
)


def is_passive_state_handoff_impl(self, raw_prompt: str) -> bool:
    """Restituisce True se il prompt contiene un marker di Passive Session State Handoff."""
    return is_passive_state_handoff(raw_prompt)


def resolve_intrinsic_vibe_protocols_impl(
    self,
    prompt: str,
    recommended_mode: str = "mode_c",
) -> Dict[str, Any]:
    """Rileva e attiva autonomamente INTRINSIC_GOAL, INTRINSIC_BOOST e INTRINSIC_PLAN."""
    text = _normalize_input_text(prompt).strip()
    if is_passive_state_handoff(text):
        return {
            "intrinsic_protocols": [],
            "autonomous_slash_equivalence": {
                "goal": False,
                "boost": False,
                "plan": False,
                "implementation": False,
            },
            "goal": False,
            "boost": False,
            "plan": False,
            "implementation": False,
            "recommended_mode": "mode_d",
        }
    text_low = text.lower()
    rec_mode = _normalize_explicit_mode(recommended_mode) or (
        recommended_mode or "mode_c"
    ).strip().lower()

    goal_active = True
    boost_active = bool(
        rec_mode in ("mode_a", "mode_d")
        or any(kw in text_low for kw in _INTRINSIC_BOOST_KEYWORDS)
    )
    plan_active = bool(
        rec_mode in ("mode_a", "mode_b")
        or any(kw in text_low for kw in _INTRINSIC_PLAN_KEYWORDS)
    )

    protocols: List[str] = []
    if goal_active:
        protocols.append("INTRINSIC_GOAL")
    if boost_active:
        protocols.append("INTRINSIC_BOOST")
    if plan_active:
        protocols.append("INTRINSIC_PLAN")

    slash_equivalence: Dict[str, bool] = {
        "goal": goal_active,
        "boost": boost_active,
        "plan": plan_active,
        "implementation": plan_active,
    }
    return {
        "intrinsic_protocols": protocols,
        "autonomous_slash_equivalence": slash_equivalence,
        "goal": goal_active,
        "boost": boost_active,
        "plan": plan_active,
        "implementation": plan_active,
        "recommended_mode": rec_mode,
    }


def normalize_voice_stt_input_impl(self, raw_prompt: str) -> Dict[str, Any]:
    """Normalizza il testo dettato a voce separando CamelCase fusi ed estraendo correzioni."""
    text = _normalize_input_text(raw_prompt).strip()
    if not text:
        return {
            "raw_prompt": raw_prompt or "",
            "cleaned_prompt": "",
            "voice_corrections_applied": [],
            "camelcase_splits": [],
            "bypass_requested": False,
        }

    code_spans: List[str] = []

    if "`" in text:

        def _stash_code(match: re.Match[str]) -> str:
            idx = len(code_spans)
            code_spans.append(match.group(0))
            return f"__NK_CODE_{idx}__"

        masked = _CODE_SPAN_RE.sub(_stash_code, text)
    else:
        masked = text

    voice_corrections: List[str] = []
    camelcase_splits: List[str] = []
    bypass_requested = False
    masked_low = masked.lower()

    if "!diretto" in masked_low and _BP_DIRETTO_RE.search(masked):
        bypass_requested = True
        masked = _BP_DIRETTO_RE.sub(" ", masked).strip()
        masked_low = masked.lower()
    if "!raw" in masked_low and _BP_RAW_RE.search(masked):
        bypass_requested = True
        masked = _BP_RAW_RE.sub(" ", masked).strip()
        masked_low = masked.lower()

    if "salta gate" in masked_low:
        fw_m = _FIRST_WORD_RE.search(masked_low[:64])
        starts_analytical_stt = bool(
            fw_m and fw_m.group(0) in _ANALYTICAL_INTERROGATIVE_PREFIXES
        )
        if not starts_analytical_stt and _SALTA_GATE_RE.search(masked):
            bypass_requested = True
            masked = _SALTA_GATE_RE.sub(" ", masked).strip()

    def _split_camel(match: re.Match[str]) -> str:
        orig = match.group(0)
        if orig.lower() in _TECH_CAMEL_ALLOWLIST:
            return orig
        rep = f"{match.group(1)} {match.group(2)}"
        camelcase_splits.append(f"{orig} -> {rep}")
        voice_corrections.append(f"{orig} -> {rep}")
        return rep

    masked = _CAMEL_GLUED_RE.sub(_split_camel, masked)
    masked_low = masked.lower()

    if any(
        tok in masked_low
        for tok in ("scusa", "anzi", "meglio", "volevo", "praticamente")
    ):
        for marker, m_pat in _VOICE_CORRECTION_PATTERNS:
            if not m_pat.search(masked):
                continue
            if marker in _VOICE_SELF_CORRECTION_MARKERS:
                parts = m_pat.split(masked)
                if len(parts) >= 2:
                    before_part = " ".join(parts[:-1]).strip(" ,;:-")
                    after_part = parts[-1].strip(" ,;:-")
                    if after_part:
                        sent_parts = _SENT_SPLIT_RE.split(before_part)
                        last_clause = (
                            sent_parts[-1].strip(" ,;:-.!?")
                            if sent_parts
                            else before_part
                        )
                        prefix_sents = " ".join(sent_parts[:-1]).strip()
                        voice_corrections.append(
                            f"{last_clause or marker} -> {after_part}"
                        )
                        is_indep = bool(
                            _STT_INDEPENDENT_ACTION_START_RE.match(after_part)
                        )
                        is_explicit_neg_marker = marker in (
                            "anzi no",
                            "anzi scusa",
                            "scusa volevo dire",
                            "scusami volevo dire",
                        )
                        if (
                            not is_explicit_neg_marker
                            and _has_imperative_write_keyword(last_clause)
                            and not _has_imperative_write_keyword(after_part)
                        ):
                            masked = f"{before_part} {after_part}".strip()
                        elif len(after_part.split()) >= 1 and (
                            is_indep or len(last_clause.split()) <= 8
                        ):
                            keep_prefix = bool(prefix_sents) and not (
                                is_explicit_neg_marker
                                and is_indep
                                and not _has_imperative_write_keyword(after_part)
                                and _has_imperative_write_keyword(prefix_sents)
                            )
                            masked = (
                                f"{prefix_sents} {after_part}".strip()
                                if keep_prefix
                                else after_part
                            )
                        else:
                            masked = f"{before_part} {after_part}".strip()
            else:
                voice_corrections.append(f"{marker} -> (rimosso filler vocale)")
                masked = m_pat.sub(" ", masked)

    masked = _MULTI_SPACE_RE.sub(" ", masked).strip()
    for idx, span in enumerate(code_spans):
        masked = masked.replace(f"__NK_CODE_{idx}__", span)

    return {
        "raw_prompt": raw_prompt,
        "cleaned_prompt": masked,
        "voice_corrections_applied": voice_corrections,
        "camelcase_splits": camelcase_splits,
        "bypass_requested": bypass_requested,
    }


def is_gate_exempt_impl(self, raw_prompt: str) -> bool:
    """Verifica le esenzioni anti-loop e standby per il Super Meta-Prompt Gate (RULE-00.6)."""
    text = _normalize_input_text(raw_prompt).strip()
    if not text:
        return True
    if _has_destructive_shell_command(text):
        return False
    if is_passive_state_handoff(text):
        return True
    if _parse_dashboard_selector(text) is not None:
        return True
    text_low = text.lower()
    if text_low.startswith("<env_capsule>") or (
        "<env_capsule>" in text_low and "</env_capsule>" in text_low
    ):
        return True
    if ("!diretto" in text_low or "!raw" in text_low) and _BP_ANY_RE.search(
        text_low
    ):
        return True
    fw_m = _FIRST_WORD_RE.search(text_low[:64])
    starts_with_analytical = bool(
        fw_m and fw_m.group(0) in _ANALYTICAL_INTERROGATIVE_PREFIXES
    ) or text_low.startswith(_ANALYTICAL_INTERROGATIVE_PREFIXES)
    if not starts_with_analytical:
        for toggle_marker, neg_re in _EXPLICIT_BYPASS_NEG_RES:
            if toggle_marker in text_low and not neg_re.search(text_low):
                return True
    if len(text_low) > 256:
        return False
    if any(meta in text_low for meta in _SHELL_META_EXEMPT_BLOCKERS):
        return False
    norm = _MULTI_SPACE_RE.sub(" ", _PUNCT_NORM_RE.sub(" ", text_low)).strip()
    if norm in _NODE_SELECTIONS or _normalize_trigger_text(text_low) in _ONBOARDING_TRIGGERS:
        return True
    return _is_anti_loop_confirmation(text_low)


def format_meta_prompt_markdown_impl(self, envelope: Dict[str, Any]) -> str:
    """Formatta il blocco Markdown visibile di Livello 0 per il campo content prima di ask_question."""
    brief_id = str(envelope.get("brief_id", "IB-UNKNOWN"))
    fsm_state = str(envelope.get("fsm_state", "AWAIT_CONFIRM"))
    rec_mode = str(envelope.get("recommended_mode", "mode_c"))
    primary_ag = str(envelope.get("primary_agent", "NK-Python-Async-Builder"))
    native_sub = str(envelope.get("native_subagent", "NK-Builder-Agent"))
    if envelope.get("standby_mode"):
        protos = "NONE (STATE_HANDOFF_STANDBY)"
    else:
        protos = ", ".join(envelope.get("intrinsic_protocols") or []) or "INTRINSIC_GOAL"
    intent_hash = str(envelope.get("intent_hash_sha256", ""))
    mirror = str(envelope.get("conceptual_mirror", ""))
    reqs = list(envelope.get("requirements_r_ids") or [])
    voice_corrs = "; ".join(envelope.get("voice_corrections_applied") or []) or "Nessuna"
    out_scope = "; ".join(envelope.get("out_of_scope") or []) or "Nessuno"
    ambiguities = "; ".join(envelope.get("ambiguities") or []) or "Nessuna"

    if fsm_state == "BYPASSED":
        return "\n".join(
            [
                "### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]",
                f"- **Brief ID:** `{brief_id}` | **Stato FSM:** `{fsm_state}` | **Hash:** `{intent_hash[:12]}`",
                f"- **1. Intenzione:** {mirror[:160]} ({reqs[0] if reqs else 'R1'})",
                f"- **2. Come Farlo:** `{rec_mode}` | **Skill:** `{primary_ag}` | **Sub-Agente:** `{native_sub}` | **Protocolli:** `{protos}`",
                f"- **3. Regole e Perimetro:** {out_scope[:120]} | **Ambiguità:** {ambiguities}",
            ]
        )

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
        lines.append(
            "- **Stop Pre-Esecuzione (`AWAIT_CONFIRM`):** Fermati subito dopo questo specchio e invoca `ask_question`. Vietato eseguire il task prima della conferma utente e vietato posticipare il Gate L0 a fine task."
        )
    lines.append(
        "- [MANDATORY-VISIBLE-L0]: Mostra obbligatoriamente questo blocco nel campo content della risposta PRIMA o INSIEME a ask_question (vietato content_len=0)."
    )
    return "\n".join(lines)

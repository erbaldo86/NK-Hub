"""Linter AP-1..AP-13, rilevamento conflitti di ruolo e verifica handoff passivo T12."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from _internal.nk_common.prompt_linter_core import evaluate_ap_rules
from _internal.vibe_sprint_router.constants_core import (
    _HANDOFF_MUTATING_ORDER_RE,
    _HANDOFF_START_PREFIXES,
    _ORCHESTRATOR_ROLES,
    _PROHIBITION_LINE_RE,
    _READ_ONLY_ROLES,
    _SHA256_HEX64_RE,
    _STATE_HANDOFF_MARKERS,
    _normalize_input_text,
)
from _internal.vibe_sprint_router.constants_stt import (
    _ANTI_LOOP_EXEMPT_PREFIXES,
    _COMPOSITE_CONFIRM_BLOCKERS,
    _COMPOSITE_CONFIRM_PHRASES,
    _DESTRUCTIVE_OR_WRITE_EXEMPT_BLOCKERS,
    _MULTI_SPACE_RE,
    _PLAN_CONFIRMATION_PREFIXES,
    _PUNCT_NORM_RE,
    _SHELL_META_EXEMPT_BLOCKERS,
    _SHORT_CONFIRMATIONS,
    _TASK_ACTION_BLOCKER_RE,
    _TECHNICAL_TASK_EXEMPT_BLOCKERS,
)
from _internal.vibe_sprint_router.write_intent import (
    _has_destructive_shell_command,
    _has_imperative_write_keyword,
)
from _internal.vibe_sprint_router.write_intent_rules import (
    _READ_ONLY_ROLES_LOWER,
    _ROLE_CONFLICT_WRITE_RE,
    _SINGLE_OPERA_RE,
)


def is_passive_state_handoff(raw_prompt: str) -> bool:
    """Verifica un handoff passivo autentico bloccando spoofing privi di anchor o con ordini mutanti."""
    norm_text = _normalize_input_text(raw_prompt).strip()
    if not norm_text:
        return False
    head_clean = norm_text[:320].lstrip("# \t\r\n").lower()
    if not head_clean.startswith(_HANDOFF_START_PREFIXES):
        return False
    low = norm_text.lower()
    if not (
        any(m in low for m in _STATE_HANDOFF_MARKERS)
        or "passive_session_state_handoff" in low
    ):
        return False
    has_valid_sha256 = bool(_SHA256_HEX64_RE.search(norm_text))
    mentions_sha = ("sha-256" in low) or ("sha256" in low)
    if mentions_sha and not has_valid_sha256:
        return False
    end_tag = "[nk-anchor:end:passive_state_handoff]"
    start_idx = low.find("[nk-anchor:start:passive_state_handoff]")
    end_idx = low.find(end_tag)
    if end_idx != -1 and norm_text[end_idx + len(end_tag) :].strip():
        return False
    if start_idx != -1 and end_idx == -1:
        return False
    has_paired_t12_anchor = (
        start_idx != -1
        and end_idx > start_idx
        and "template 12: passive_session_state_handoff" in low
        and "### 1." in low
    )
    if not (has_valid_sha256 or has_paired_t12_anchor):
        return False
    in_fence = False
    for raw_line in norm_text.splitlines()[1:]:
        line_s = raw_line.strip()
        if not line_s:
            continue
        if line_s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or _PROHIBITION_LINE_RE.search(line_s):
            continue
        if (
            _has_destructive_shell_command(line_s)
            or _HANDOFF_MUTATING_ORDER_RE.search(line_s)
            or _has_imperative_write_keyword(line_s)
        ):
            return False
    return True


def _is_anti_loop_confirmation(raw_text: str) -> bool:
    """Verifica conferme anti-loop procedi* <= 12 parole prive di blocker o metacaratteri shell."""
    text_low = (raw_text or "").strip().lower()
    if not text_low or len(text_low) > 256:
        return False
    if _has_destructive_shell_command(text_low):
        return False
    if any(meta in text_low for meta in _SHELL_META_EXEMPT_BLOCKERS):
        return False
    if re.search(r"[.!?\n]\s*\S", text_low):
        return False
    norm = _MULTI_SPACE_RE.sub(" ", _PUNCT_NORM_RE.sub(" ", text_low)).strip()
    if norm in _SHORT_CONFIRMATIONS:
        return True
    if any(phrase in norm for phrase in _COMPOSITE_CONFIRM_PHRASES):
        return False
    norm_words = norm.split()
    if len(norm_words) > 12:
        return False
    matches_prefix = (
        norm.startswith(_PLAN_CONFIRMATION_PREFIXES)
        or norm == "procedi"
        or norm.startswith("procedi ")
        or any(
            norm == p or norm.startswith(f"{p} ")
            for p in _ANTI_LOOP_EXEMPT_PREFIXES
        )
    )
    if not matches_prefix:
        return False
    if (
        any(w in _COMPOSITE_CONFIRM_BLOCKERS for w in norm_words)
        or any(w in _DESTRUCTIVE_OR_WRITE_EXEMPT_BLOCKERS for w in norm_words)
        or any(w in _TECHNICAL_TASK_EXEMPT_BLOCKERS for w in norm_words)
        or bool(_TASK_ACTION_BLOCKER_RE.search(norm))
        or _has_imperative_write_keyword(norm)
    ):
        return False
    return True


def _detect_prompt_role_conflicts(
    prompt_text: str,
    text_lower: Optional[str] = None,
    has_write_override: Optional[bool] = None,
) -> List[str]:
    """Rileva conflitti di ruolo tra nodi Read-Only, Orchestratori e richieste di scrittura."""
    conflicts: List[str] = []
    if not prompt_text:
        return conflicts
    low = text_lower if text_lower is not None else prompt_text.lower()
    has_ro = [r for r, r_low in _READ_ONLY_ROLES_LOWER if r_low in low]
    if not has_ro and "opera come" not in low:
        return conflicts
    base_write = (
        has_write_override
        if has_write_override is not None
        else _has_imperative_write_keyword(prompt_text)
    )
    has_write = base_write or bool(_ROLE_CONFLICT_WRITE_RE.search(prompt_text))
    single_opera = _SINGLE_OPERA_RE.search(prompt_text) if "opera come" in low else None
    if single_opera:
        roles_str = single_opera.group(1)
        ro_in_opera = any(r in roles_str for r in _READ_ONLY_ROLES)
        orch_in_opera = any(r in roles_str for r in _ORCHESTRATOR_ROLES)
        if (ro_in_opera and orch_in_opera) or (ro_in_opera and has_write):
            conflicts.append(
                f"Role collapse detected in 'Opera come {roles_str}' with write instructions."
            )
    elif has_ro and has_write and "invoke_subagent" not in prompt_text:
        conflicts.append(
            f"Read-Only role ({', '.join(has_ro)}) combined with write intent without subagent delegation."
        )
    return conflicts


def _make_lint_violation(
    code: str, severity: str, msg: str, rule: str = ""
) -> Dict[str, str]:
    """Costruisce un record di violazione compatibile con nk_transcript_tools.py e il router."""
    rec = {
        "code": code,
        "message": msg,
        "id": code,
        "severity": severity,
        "msg": msg,
    }
    if rule:
        rec["rule"] = rule
    return rec


def lint_nk_prompt(prompt_text: str, mode: str = "auto") -> Dict[str, Any]:
    """Analizza un prompt generato per l'ambiente NK delegando a nk_common.prompt_linter_core."""
    return evaluate_ap_rules(prompt_text, mode=mode)

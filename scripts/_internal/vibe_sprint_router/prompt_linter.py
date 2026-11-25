"""Linter AP-1..AP-16, rilevamento conflitti di ruolo e verifica handoff passivo T12/V2."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from _internal.nk_common.epistemic_firewall_rules import (
    HANDOFF_V2_START_ACTIVE,
    HANDOFF_V2_START_PASSIVE,
    T12_START,
    _AGENT_DIRECTIVE_CUE_RE,
    _CLAUSE_BREAK_RE,
    _DESTRUCTIVE_SHELL_RE,
    check_passive_v2_tiered_content,
    evaluate_epistemic_firewall_rules,
    extract_t12_scan_lines,
    has_unprohibited_smuggle,
    strip_zero_width_chars,
)
from _internal.nk_common.prompt_linter_core import evaluate_ap_rules
from _internal.vibe_sprint_router.constants_core import (
    _HANDOFF_MUTATING_ORDER_RE,
    _ORCHESTRATOR_ROLES,
    _PROHIBITION_LINE_RE,
    _READ_ONLY_ROLES,
    _SHA256_HEX64_RE,
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

_T12_META_LINE_RE = re.compile(
    r"(?:^\s*[-*•]\s*(?:\*\*[^*]+?\*\*:?|[A-Za-zÀ-ÿ0-9_ ]{1,32}:)|"
    r"^\s*(?:staging|dirty\s+files|stato|workspace|project\s+root|hub\s+root|milestone(?:\s+anchor)?)\s*:|"
    r"\bpresenti\s+artefatti\b)",
    re.IGNORECASE,
)


def is_passive_state_handoff(raw_prompt: str) -> bool:
    """Verifica un handoff passivo V2 o T12 bloccando spoofing, fence aperti e ordini mutanti."""
    norm_text = strip_zero_width_chars(_normalize_input_text(raw_prompt)).strip()
    if not norm_text:
        return False
    low = norm_text.lower()
    if HANDOFF_V2_START_ACTIVE.lower() in low:
        return False
    if HANDOFF_V2_START_PASSIVE.lower() not in low and T12_START.lower() not in low:
        return False

    fw_viols, fw_meta = evaluate_epistemic_firewall_rules(
        norm_text, mode="state-handoff", is_state_handoff=True
    )
    if fw_meta.get("unclosed_fence") or fw_viols:
        return False
    if fw_meta.get("v2_verified"):
        return str(fw_meta.get("v2_mode") or "").upper() == "PASSIVE_STANDBY" and not check_passive_v2_tiered_content(fw_meta)
    if fw_meta.get("is_v2_handoff") or HANDOFF_V2_START_PASSIVE.lower() in low or "handoff_v2:" in low or not fw_meta.get("t12_framing_valid"):
        return False
    if ("sha-256" in low or "sha256" in low) and not _SHA256_HEX64_RE.search(norm_text):
        return False

    strict_lines, neutral_lines = extract_t12_scan_lines(norm_text)
    for raw_line, is_neutral in [(ln, False) for ln in strict_lines] + [(ln, True) for ln in neutral_lines]:
        line_s = raw_line.strip()
        if not line_s:
            continue
        if (
            (not is_neutral and (_has_destructive_shell_command(line_s) or _DESTRUCTIVE_SHELL_RE.search(line_s)))
            or _HANDOFF_MUTATING_ORDER_RE.search(line_s)
            or has_unprohibited_smuggle(line_s, _PROHIBITION_LINE_RE)
        ):
            return False
        is_meta = bool(_T12_META_LINE_RE.search(line_s))
        for raw_clause in _CLAUSE_BREAK_RE.split(line_s):
            clause_s = raw_clause.strip()
            if not clause_s or _PROHIBITION_LINE_RE.search(clause_s):
                continue
            check_line = (
                re.sub(r"\.staging\b", "staging_meta", clause_s, flags=re.IGNORECASE)
                if ".staging" in clause_s.lower() and is_meta
                else clause_s
            )
            if _has_imperative_write_keyword(check_line):
                has_cue = bool(
                    _AGENT_DIRECTIVE_CUE_RE.search(clause_s)
                    or re.search(r"\b(?:subito|adesso|immediatamente|devi|dobbiamo|bisogna|occorre)\b", clause_s, re.IGNORECASE)
                    or (
                        not is_meta
                        and re.search(r"\b(?:il\s+file|i\s+file|il\s+codice|lo\s+script|i\s+test|nel\s+repo|in\s+\.staging)\b", clause_s, re.IGNORECASE)
                    )
                )
                if has_cue:
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
        or any(norm == p or norm.startswith(f"{p} ") for p in _ANTI_LOOP_EXEMPT_PREFIXES)
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
    """Analizza un prompt generato per l'ambiente NK integrando AP-1..AP-13 e AP-14..AP-16."""
    res = evaluate_ap_rules(prompt_text, mode=mode)
    norm_mode = (mode or "auto").strip().lower()
    fw_viols, _ = evaluate_epistemic_firewall_rules(
        prompt_text or "",
        mode=norm_mode,
        is_state_handoff=(norm_mode == "state-handoff"),
    )
    if fw_viols:
        existing = list(res.get("violations") or [])
        seen_codes = {str(v.get("code") or v.get("id") or "") for v in existing}
        for fv in fw_viols:
            fcode = str(fv.get("code") or fv.get("id") or "")
            if fcode and fcode not in seen_codes:
                existing.append(
                    _make_lint_violation(
                        fcode,
                        str(fv.get("severity") or "CRITICA"),
                        str(fv.get("message") or fv.get("msg") or fcode),
                        rule=str(fv.get("rule") or ""),
                    )
                )
                seen_codes.add(fcode)
        is_valid = len(existing) == 0
        res["violations"] = existing
        res["violations_count"] = len(existing)
        res["violation_count"] = len(existing)
        res["passed"] = is_valid
        res["valid"] = is_valid
    return res

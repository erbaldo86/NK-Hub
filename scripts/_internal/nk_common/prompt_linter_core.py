# -*- coding: utf-8 -*-
"""Valutatore condiviso delle regole deterministiche AP-1..AP-16 e AP-2b su prompt generati."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from _internal.nk_common.epistemic_firewall_rules import (
    HANDOFF_V2_END_ACTIVE, HANDOFF_V2_END_PASSIVE, HANDOFF_V2_START_ACTIVE,
    HANDOFF_V2_START_PASSIVE, _DESTRUCTIVE_SHELL_RE, _HANDOFF_MUTATING_ORDER_RE,
    check_passive_v2_tiered_content, evaluate_epistemic_firewall_rules,
    extract_t12_scan_lines, has_unprohibited_pattern, has_unprohibited_smuggle,
    is_sealed_t12_json_capsule, strip_zero_width_chars,
)
from _internal.nk_common.prompt_linter_rules import (
    _AP10_PASSIVE_SLASH_RE, _AP10_PROHIBITION_CONTEXT_RE, _AP12_IMPERATIVE_LEAK_RE,
    _AP13_COGNITIVE_TUNNELING_RE, _BRIEF_HEADER_PHASE_RE, _BROAD_WRITE_INTENT_RE,
    _DIRETTO_RE, _ENABLE_WRITE_TRUE_RE, _GOODHART_RE, _HANDOFF_START_PREFIXES,
    _NATIVE_WRITE_AGENTS, _ORCHESTRATOR_ROLES, _PROHIBITION_LINE_RE, _READ_ONLY_ROLES,
    _STATE_HANDOFF_HEADER_RE, _STRICT_MUTATION_RE,
    _has_active_oracle_lock_for_ap4, _has_canary_holdout_leak_for_ap11,
    _has_unguarded_server_start_for_ap7, _has_unsharded_web_burst_for_ap7,
    _has_write_grant_for_ap2b, _make_lint_violation,
)


def _add_violation(
    violations: List[Dict[str, str]], code: str, severity: str, message: str, rule: str
) -> None:
    """Accoda una violazione normalizzata alla lista delle infrazioni rilevate."""
    violations.append(_make_lint_violation(code, severity, message, rule=rule))


_is_sealed_t12_json_capsule = is_sealed_t12_json_capsule


def evaluate_ap_rules(prompt: str, mode: str = "auto") -> Dict[str, Any]:
    """Valuta gli anti-pattern AP-1..AP-16 e AP-2b su un prompt NK restituendo esito e violazioni."""
    violations: List[Dict[str, str]] = []
    text = strip_zero_width_chars(prompt or "")
    low = text.lower()
    norm_mode = (mode or "auto").strip().lower()
    head_clean = text.strip()[:320].lstrip("# \t\r\n").lower()
    has_v2_passive = any(
        m in low for m in (HANDOFF_V2_START_PASSIVE.lower(), HANDOFF_V2_END_PASSIVE.lower())
    )
    has_v2_active = any(
        m in low for m in (HANDOFF_V2_START_ACTIVE.lower(), HANDOFF_V2_END_ACTIVE.lower())
    )
    is_state_handoff = (norm_mode == "state-handoff") or (
        norm_mode in ("auto", "handoff-v2", "handoff_v2")
        and (
            has_v2_passive
            or has_v2_active
            or bool(_STATE_HANDOFF_HEADER_RE.search(text))
            or head_clean.startswith(_HANDOFF_START_PREFIXES)
        )
    )

    has_diretto = bool(_DIRETTO_RE.search(text))
    writes_code_or_data = (not is_state_handoff) and bool(_STRICT_MUTATION_RE.search(text))
    has_broad_write = writes_code_or_data or (
        (not is_state_handoff) and bool(_BROAD_WRITE_INTENT_RE.search(text))
    )
    phase_count = len(_BRIEF_HEADER_PHASE_RE.findall(text))

    # AP-1: Bypass del Meta-Prompt Gate (!diretto / Proceed) su prompt complessi
    if has_diretto and (len(text) > 1500 or phase_count > 1 or writes_code_or_data):
        _add_violation(
            violations, "AP-1", "CRITICA",
            "Uso di '!diretto' su prompt complesso (>1500 char, multi-fase o con scritture): bypassa [RULE-00.6].",
            "DIRETTO_OVERLOAD_FORBIDDEN",
        )

    # AP-2: Collasso dei ruoli incompatibili o assenza di delega 2-Tier
    if not is_state_handoff:
        ap2_role_emitted = False
        single_agent_opera = re.search(r"Opera come\s+([^\n\.]+)", text, re.IGNORECASE)
        if single_agent_opera:
            roles_str = single_agent_opera.group(1)
            has_ro = any(r in roles_str for r in _READ_ONLY_ROLES)
            has_orch = any(r in roles_str for r in _ORCHESTRATOR_ROLES)
            if (has_ro and has_orch) or (has_ro and writes_code_or_data):
                _add_violation(
                    violations, "AP-2", "CRITICA",
                    f"Collasso dei ruoli incompatibili in una singola istanza ('Opera come {roles_str}') con task di scrittura: viola [RULE-01] e [RULE-00.1].",
                    "ROLE_FUSION_OR_MISSING_DELEGATION",
                )
                ap2_role_emitted = True
        if not ap2_role_emitted:
            has_ctrl = any(
                k in low
                for k in ("nk-orchestrator", "orchestrator", "session-controller", "controller", "master-hub")
            )
            has_eval = any(
                k in low
                for k in ("oracle-evaluator", "security-auditor", "security-dast-auditor", "auditor", "evaluator")
            )
            if has_ctrl and has_eval and has_broad_write and "define_subagent" not in low:
                _add_violation(
                    violations, "AP-2", "CRITICA",
                    "Incompatible role fusion without subagent separation.",
                    "ROLE_FUSION_OR_MISSING_DELEGATION",
                )
        if (
            (phase_count >= 2 or len(text) > 2500)
            and "invoke_subagent" not in low
            and "define_subagent" not in low
        ):
            _add_violation(
                violations, "AP-2", "ALTA",
                "Prompt multi-fase privo di direttive di delega 2-Tier ('invoke_subagent' / '<env_capsule>').",
                "ROLE_FUSION_OR_MISSING_DELEGATION",
            )

    # AP-2b: Delega di scrittura senza EnableWriteTools=True o invoke_subagent su sub-agente nativo
    has_write_grant = _has_write_grant_for_ap2b(low)
    has_write_agent = any(ag in low for ag in _NATIVE_WRITE_AGENTS) or (
        "nk-triad-rsi-builder" in low or "builder" in low
    )
    if has_broad_write and (phase_count >= 2 or has_write_agent):
        if not has_write_grant:
            _add_violation(
                violations, "AP-2b", "CRITICA",
                "Missing define_subagent(..., EnableWriteTools=True) or invoke_subagent with native write agent (G3-01).",
                "BUILDER_WRITE_TOOLS_REGISTRATION",
            )

    # AP-3: Iniezione di scritture codice/test senza .staging/ e win32_2pc_engine.py
    if writes_code_or_data and (".staging" not in low or "win32_2pc_engine.py" not in low):
        _add_violation(
            violations, "AP-3", "CRITICA",
            "Prescrizione di modifiche a codice/dati/test senza isolamento '.staging/' e commit 'win32_2pc_engine.py --promote-staging --repo-root': viola [RULE-00].",
            "STAGING_2PC_BYPASS",
        )

    # AP-4: Loop di Goodhart nello stesso turno senza oracle-lock attivo
    if _GOODHART_RE.search(low) and not _has_active_oracle_lock_for_ap4(low):
        _add_violation(
            violations, "AP-4", "CRITICA",
            "Loop condizionato 'finche 100% PASS' nello stesso turno: induce data poisoning e indebolimento degli oracoli (Legge di Goodhart).",
            "GOODHART_LOOP_WITHOUT_ORACLE_LOCK",
        )

    # AP-5: Comando rsi_convergence_engine.py --verify privo di --root <project>
    for m_rsi in re.finditer(r"rsi_convergence_engine\.py\s+([^\n`]+)", text):
        args_segment = m_rsi.group(1)
        if "--verify" in args_segment and "--root" not in args_segment:
            _add_violation(
                violations, "AP-5", "CRITICA",
                "Comando 'rsi_convergence_engine.py --verify' privo di '--root <project_root>': produce falso 100/100 sintetico.",
                "EXTERNAL_RSI_MISSING_ROOT",
            )

    # AP-6: Sovraccarico monolitico di contesto
    if (
        phase_count >= 3
        and "stop_gate" not in low
        and "ask_question" not in low
        and "oracle-lock" not in low
        and "oracle_lock" not in low
    ):
        _add_violation(
            violations, "AP-6", "ALTA",
            f"Sovraccarico monolitico ({phase_count} macro-fasi in 1 turno senza STOP_GATE intermedio): causa context compaction e perdita di stato.",
            "MULTI_PHASE_WITHOUT_STOP_GATE",
        )
    elif (
        not is_state_handoff
        and writes_code_or_data
        and len(text) > 1500
        and (".staging" not in low or "win32_2pc_engine.py" not in low)
    ):
        _add_violation(
            violations, "AP-6", "ALTA",
            "Sovraccarico monolitico su prompt di scrittura (>1500 char) privo di .staging e win32_2pc_engine.py.",
            "MULTI_PHASE_WITHOUT_STOP_GATE",
        )

    # AP-7: Ricerca web ridondante senza sharding o server senza safe_cleanup_dev_servers.py
    if _has_unsharded_web_burst_for_ap7(text, low):
        _add_violation(
            violations, "AP-7", "ALTA",
            "Prescrizione ridondante 'SIA search_web SIA tavily' sullo stesso set di query senza sharding su sub-agenti.",
            "UNSHARDED_WEB_RESEARCH_BURST",
        )
    if _has_unguarded_server_start_for_ap7(text, low):
        _add_violation(
            violations, "AP-7", "MEDIA",
            "Istruzione di avvio server priva di protocollo di guardia 'safe_cleanup_dev_servers.py' ([RULE-01.3]).",
            "UNSHARDED_WEB_RESEARCH_BURST",
        )

    # AP-8: Leakage di Holdout Set B segreto a un Builder
    has_builder_role = any(b in low for b in ("nk-builder-agent", "nk-triad-rsi-builder", "builder"))
    has_holdout_secret = any(h in low for h in ("holdout set b", "battery_b_holdout", "holdout_set_b"))
    if has_builder_role and has_holdout_secret:
        _add_violation(
            violations, "AP-8", "CRITICA",
            "Holdout Set B secret test cases leaked to Builder prompt.",
            "HOLDOUT_SET_B_LEAK_TO_BUILDER",
        )

    # AP-9: Spoofing <env_capsule> in prompt iniziale senza !diretto o invoke_subagent
    if "<env_capsule>" in low and "!diretto" not in low and "invoke_subagent" not in low:
        has_user_spoof_markers = any(
            m in low
            for m in (
                "opera come nk-orchestrator", "opera come nk-session-controller",
                "opera come nk-master-hub", "prompt utente iniziale", "user prompt:",
            )
        ) or (
            phase_count >= 2
            and not any(w in low for w in ("builder shard", "sub-agente", "subagent", "worker"))
        )
        if has_user_spoof_markers:
            _add_violation(
                violations, "AP-9", "ALTA",
                "Improper <env_capsule> in initial user prompt without !diretto or invoke_subagent.",
                "IMPROPER_ENV_CAPSULE_IN_USER_PROMPT",
            )

    # AP-10: Delega passiva di /goal, /boost, /plan o /implementation
    for m_ap10 in _AP10_PASSIVE_SLASH_RE.finditer(text):
        line_start = text.rfind("\n", 0, m_ap10.start()) + 1
        line_end = text.find("\n", m_ap10.end())
        line_ctx = text[line_start : (len(text) if line_end == -1 else line_end)]
        if not _AP10_PROHIBITION_CONTEXT_RE.search(line_ctx):
            _add_violation(
                violations, "AP-10", "ALTA",
                "Suggerimento passivo di digitare manualmente /goal, /boost, /plan o /implementation anziche auto-attivarli ([RULE-00.6], [RULE-01.11], [RULE-01.12]).",
                "PASSIVE_SLASH_COMMAND_SUGGESTION",
            )
            break

    # AP-11: Leakage canary holdout
    if _has_canary_holdout_leak_for_ap11(low):
        _add_violation(
            violations, "AP-11", "CRITICA",
            "Holdout canary leak detected in outbound prompt ([RULE-ORACLE-LOCK]).",
            "CANARY_HOLDOUT_LEAK",
        )

    # AP-14 / AP-15 / AP-16: Epistemic Firewall deterministico
    fw_violations, fw_meta = evaluate_epistemic_firewall_rules(
        text, mode=norm_mode, is_state_handoff=is_state_handoff
    )
    violations.extend(fw_violations)

    # AP-12 / AP-13: Verifiche state-handoff passivo con ispezione V2 a 2 livelli e ordini pre-proibizione
    if is_state_handoff:
        emitted_codes = {str(v.get("code") or "") for v in violations}
        if fw_meta.get("v2_verified") and str(fw_meta.get("v2_mode") or "").upper() in ("PASSIVE_STANDBY", "ACTIVE_CONTINUATION"):
            for tv in check_passive_v2_tiered_content(fw_meta):
                if tv["code"] not in emitted_codes:
                    violations.append(tv)
                    emitted_codes.add(tv["code"])
            scan_lines = list(fw_meta.get("outside_lines") or ())
        else:
            allow_fence_skip = (
                not fw_meta.get("unclosed_fence", False)
                and not fw_violations
                and _is_sealed_t12_json_capsule(text)
            )
            scan_lines = extract_t12_scan_lines(text)[0] if allow_fence_skip else text.splitlines()

        has_ap12, has_ap13 = "AP-12" in emitted_codes, "AP-13" in emitted_codes
        for raw_line in scan_lines:
            line_s = raw_line.strip()
            if not line_s:
                continue
            smug = bool(
                _DESTRUCTIVE_SHELL_RE.search(line_s)
                or _HANDOFF_MUTATING_ORDER_RE.search(line_s)
                or has_unprohibited_smuggle(line_s, _PROHIBITION_LINE_RE)
            )
            if not has_ap12 and (smug or has_unprohibited_pattern(line_s, _AP12_IMPERATIVE_LEAK_RE, _PROHIBITION_LINE_RE)):
                _add_violation(
                    violations, "AP-12", "CRITICA",
                    "STATE_HANDOFF_IMPERATIVE_LEAK: Imperative directive or intrinsic protocol leak inside Passive Session State Handoff.",
                    "STATE_HANDOFF_IMPERATIVE_LEAK",
                )
                has_ap12 = True
            if not has_ap13 and has_unprohibited_pattern(line_s, _AP13_COGNITIVE_TUNNELING_RE, _PROHIBITION_LINE_RE):
                _add_violation(
                    violations, "AP-13", "CRITICA",
                    "STATE_HANDOFF_COGNITIVE_TUNNELING: Prescriptive track or option menu detected inside Passive Session State Handoff.",
                    "STATE_HANDOFF_COGNITIVE_TUNNELING",
                )
                has_ap13 = True

    is_valid = len(violations) == 0
    return {
        "passed": is_valid,
        "valid": is_valid,
        "violations_count": len(violations),
        "violation_count": len(violations),
        "violations": violations,
        "write_tools_mounted": bool(
            _ENABLE_WRITE_TRUE_RE.search(text) or has_write_grant
        ),
    }

# -*- coding: utf-8 -*-
"""Valutatore condiviso delle regole deterministiche AP-1..AP-13 su prompt generati."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from _internal.nk_common.prompt_linter_rules import (
    _AP10_PASSIVE_SLASH_RE,
    _AP10_PROHIBITION_CONTEXT_RE,
    _AP12_IMPERATIVE_LEAK_RE,
    _AP13_COGNITIVE_TUNNELING_RE,
    _BRIEF_HEADER_PHASE_RE,
    _BROAD_WRITE_INTENT_RE,
    _DIRETTO_RE,
    _GOODHART_RE,
    _HANDOFF_START_PREFIXES,
    _ORCHESTRATOR_ROLES,
    _PROHIBITION_LINE_RE,
    _READ_ONLY_ROLES,
    _STATE_HANDOFF_HEADER_RE,
    _STRICT_MUTATION_RE,
    _make_lint_violation,
)


def _add_violation(
    violations: List[Dict[str, str]],
    code: str,
    severity: str,
    message: str,
    rule: str,
) -> None:
    """Accoda una violazione normalizzata alla lista delle infrazioni rilevate."""
    violations.append(_make_lint_violation(code, severity, message, rule=rule))


def evaluate_ap_rules(prompt: str, mode: str = "auto") -> Dict[str, Any]:
    """Valuta gli anti-pattern AP-1..AP-13 e AP-2b su un prompt NK restituendo esito e violazioni."""
    violations: List[Dict[str, str]] = []
    text = prompt or ""
    low = text.lower()
    norm_mode = (mode or "auto").strip().lower()
    head_clean = text.strip()[:320].lstrip("# \t\r\n").lower()
    is_state_handoff = (norm_mode == "state-handoff") or (
        norm_mode == "auto"
        and (
            bool(_STATE_HANDOFF_HEADER_RE.search(text))
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
            violations,
            "AP-1",
            "CRITICA",
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
                    violations,
                    "AP-2",
                    "CRITICA",
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
                    violations,
                    "AP-2",
                    "CRITICA",
                    "Incompatible role fusion without subagent separation.",
                    "ROLE_FUSION_OR_MISSING_DELEGATION",
                )
        if (
            (phase_count >= 2 or len(text) > 2500)
            and "invoke_subagent" not in low
            and "define_subagent" not in low
        ):
            _add_violation(
                violations,
                "AP-2",
                "ALTA",
                "Prompt multi-fase privo di direttive di delega 2-Tier ('invoke_subagent' / '<env_capsule>').",
                "ROLE_FUSION_OR_MISSING_DELEGATION",
            )

    # AP-2b: Delega a Builder senza EnableWriteTools=True
    if has_broad_write and (phase_count >= 2 or "nk-builder-agent" in low or "builder" in low):
        has_write_grant = (
            ("define_subagent" in low and ("enablewritetools" in low or "enable_write_tools" in low))
            or '"self"' in low
            or "'self'" in low
        )
        if not has_write_grant:
            _add_violation(
                violations,
                "AP-2b",
                "CRITICA",
                "Missing define_subagent(..., EnableWriteTools=True) or self for Builder (G3-01).",
                "BUILDER_WRITE_TOOLS_REGISTRATION",
            )

    # AP-3: Iniezione di scritture codice/test senza .staging/ e win32_2pc_engine.py
    if writes_code_or_data and (".staging" not in low or "win32_2pc_engine.py" not in low):
        _add_violation(
            violations,
            "AP-3",
            "CRITICA",
            "Prescrizione di modifiche a codice/dati/test senza isolamento '.staging/' e commit 'win32_2pc_engine.py --promote-staging --repo-root': viola [RULE-00].",
            "STAGING_2PC_BYPASS",
        )

    # AP-4: Loop di Goodhart nello stesso turno senza oracle-lock
    if _GOODHART_RE.search(low) and "oracle-lock" not in low and "oracle_lock" not in low:
        _add_violation(
            violations,
            "AP-4",
            "CRITICA",
            "Loop condizionato 'finche 100% PASS' nello stesso turno: induce data poisoning e indebolimento degli oracoli (Legge di Goodhart).",
            "GOODHART_LOOP_WITHOUT_ORACLE_LOCK",
        )

    # AP-5: Comando rsi_convergence_engine.py --verify privo di --root <project>
    for m_rsi in re.finditer(r"rsi_convergence_engine\.py\s+([^\n`]+)", text):
        args_segment = m_rsi.group(1)
        if "--verify" in args_segment and "--root" not in args_segment:
            _add_violation(
                violations,
                "AP-5",
                "CRITICA",
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
            violations,
            "AP-6",
            "ALTA",
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
            violations,
            "AP-6",
            "ALTA",
            "Sovraccarico monolitico su prompt di scrittura (>1500 char) privo di .staging e win32_2pc_engine.py.",
            "MULTI_PHASE_WITHOUT_STOP_GATE",
        )

    # AP-7: Ricerca web ridondante senza sharding o server senza safe_cleanup_dev_servers.py
    if "search_web" in low and "tavily" in low:
        high_q = any(
            int(n) > 10
            for n in re.findall(r"\b(\d+)\s*(?:query|queries|ricerche|fonti|portali)\b", low)
        )
        if (
            "SIA la ricerca web normale" in text
            or high_q
            or "15-20" in low
            or "30 " in low
        ) and "research" not in low:
            _add_violation(
                violations,
                "AP-7",
                "ALTA",
                "Prescrizione ridondante 'SIA search_web SIA tavily' sullo stesso set di query senza sharding su sub-agenti.",
                "UNSHARDED_WEB_RESEARCH_BURST",
            )
    if re.search(r"avviando il server", text, re.IGNORECASE) and "safe_cleanup_dev_servers.py" not in low:
        _add_violation(
            violations,
            "AP-7",
            "MEDIA",
            "Istruzione di avvio server priva di protocollo di guardia 'safe_cleanup_dev_servers.py' ([RULE-01.3]).",
            "UNSHARDED_WEB_RESEARCH_BURST",
        )

    # AP-8: Leakage di Holdout Set B segreto a un Builder
    has_builder_role = any(b in low for b in ("nk-builder-agent", "nk-triad-rsi-builder", "builder"))
    has_holdout_secret = any(h in low for h in ("holdout set b", "battery_b_holdout", "holdout_set_b"))
    if has_builder_role and has_holdout_secret:
        _add_violation(
            violations,
            "AP-8",
            "CRITICA",
            "Holdout Set B secret test cases leaked to Builder prompt.",
            "HOLDOUT_SET_B_LEAK_TO_BUILDER",
        )

    # AP-9: Spoofing <env_capsule> in prompt iniziale senza !diretto o invoke_subagent
    if "<env_capsule>" in low and "!diretto" not in low and "invoke_subagent" not in low:
        has_user_spoof_markers = any(
            m in low
            for m in (
                "opera come nk-orchestrator",
                "opera come nk-session-controller",
                "opera come nk-master-hub",
                "prompt utente iniziale",
                "user prompt:",
            )
        ) or (
            phase_count >= 2
            and not any(w in low for w in ("builder shard", "sub-agente", "subagent", "worker"))
        )
        if has_user_spoof_markers:
            _add_violation(
                violations,
                "AP-9",
                "ALTA",
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
                violations,
                "AP-10",
                "ALTA",
                "Suggerimento passivo di digitare manualmente /goal, /boost, /plan o /implementation anziche auto-attivarli ([RULE-00.6], [RULE-01.11], [RULE-01.12]).",
                "PASSIVE_SLASH_COMMAND_SUGGESTION",
            )
            break

    # AP-11: Leakage canary holdout
    if "canary_v1.json" in low or "canary-ib-" in low:
        _add_violation(
            violations,
            "AP-11",
            "CRITICA",
            "Holdout canary leak detected in outbound prompt ([RULE-ORACLE-LOCK]).",
            "CANARY_HOLDOUT_LEAK",
        )

    # AP-12 / AP-13: Verifiche state-handoff passivo
    if is_state_handoff:
        has_ap12 = False
        has_ap13 = False
        for raw_line in text.splitlines():
            line_s = raw_line.strip()
            if not line_s or _PROHIBITION_LINE_RE.search(line_s):
                continue
            if not has_ap12 and _AP12_IMPERATIVE_LEAK_RE.search(line_s):
                _add_violation(
                    violations,
                    "AP-12",
                    "CRITICA",
                    "STATE_HANDOFF_IMPERATIVE_LEAK: Imperative directive or intrinsic protocol leak inside Passive Session State Handoff.",
                    "STATE_HANDOFF_IMPERATIVE_LEAK",
                )
                has_ap12 = True
            if not has_ap13 and _AP13_COGNITIVE_TUNNELING_RE.search(line_s):
                _add_violation(
                    violations,
                    "AP-13",
                    "CRITICA",
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
        "write_tools_mounted": ("EnableWriteTools=True" in text or "enable_write_tools=True" in text),
    }

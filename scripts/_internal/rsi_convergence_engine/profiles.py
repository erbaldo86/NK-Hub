# -*- coding: utf-8 -*-
"""Profili Tensor-RSI 2D, formule matematiche Delta_k / Q(S_k), Q_v2(S_k) e STE100."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from _internal.rsi_convergence_engine.constants import (
    RSIDefectVector,
    get_ste100_validator,
)


class RSIProfileConfig(BaseModel):
    """Configurazione dei pesi e della formula di fitness per un profilo Tensor-RSI."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    profile_id: str = Field(description="Identificativo breve P1..P6")
    name: str = Field(description="Nome canonico del profilo RSI")
    weights: Tuple[int, int, int, int, int, int, int] = Field(
        description="Pesi (sast, tests_failed, contract, high, medium, low, doc_drift)"
    )
    test_weight: float = Field(description="Peso percentuale della componente test")
    delta_weight: float = Field(description="Peso percentuale della componente Delta_k")
    delta_scale: float = Field(description="Fattore di scala iperbolico di Delta_k")
    target_latency_ms: int = Field(description="Latenza target massima in millisecondi")


class RSIProfileRegistry:
    """Registro deterministico dei 6 profili di dominio Tensor-RSI 2D."""

    PROFILES: Dict[str, RSIProfileConfig] = {
        "vibe_sprint_micro_rsi": RSIProfileConfig(
            profile_id="P1", name="vibe_sprint_micro_rsi", weights=(15, 10, 10, 5, 1, 0, 1),
            test_weight=60.0, delta_weight=40.0, delta_scale=25.0, target_latency_ms=500,
        ),
        "code_rsi": RSIProfileConfig(
            profile_id="P2", name="code_rsi", weights=(15, 10, 10, 5, 2, 1, 1),
            test_weight=60.0, delta_weight=40.0, delta_scale=25.0, target_latency_ms=4000,
        ),
        "spec_rsi": RSIProfileConfig(
            profile_id="P3", name="spec_rsi", weights=(0, 0, 15, 8, 4, 1, 5),
            test_weight=0.0, delta_weight=100.0, delta_scale=15.0, target_latency_ms=40,
        ),
        "ui_ux_rsi": RSIProfileConfig(
            profile_id="P4", name="ui_ux_rsi", weights=(10, 5, 12, 6, 3, 1, 2),
            test_weight=50.0, delta_weight=50.0, delta_scale=20.0, target_latency_ms=60,
        ),
        "ste100_rsi": RSIProfileConfig(
            profile_id="P5", name="ste100_rsi", weights=(0, 0, 10, 5, 2, 1, 10),
            test_weight=0.0, delta_weight=100.0, delta_scale=10.0, target_latency_ms=30,
        ),
        "refactor_rsi": RSIProfileConfig(
            profile_id="P6", name="refactor_rsi", weights=(15, 10, 15, 8, 4, 1, 2),
            test_weight=50.0, delta_weight=50.0, delta_scale=20.0, target_latency_ms=4000,
        ),
    }

    _LEGACY_ALIASES = frozenset({"producer", "orchestrator"})
    _ALIASES: Dict[str, str] = {
        "p1": "vibe_sprint_micro_rsi", "vibe_sprint_micro_rsi": "vibe_sprint_micro_rsi", "vibe": "vibe_sprint_micro_rsi",
        "p2": "code_rsi", "code_rsi": "code_rsi", "code": "code_rsi",
        "producer": "code_rsi", "orchestrator": "code_rsi",
        "p3": "spec_rsi", "spec_rsi": "spec_rsi", "spec": "spec_rsi",
        "p4": "ui_ux_rsi", "ui_ux_rsi": "ui_ux_rsi", "ui_ux": "ui_ux_rsi",
        "p5": "ste100_rsi", "ste100_rsi": "ste100_rsi", "ste100": "ste100_rsi",
        "p6": "refactor_rsi", "refactor_rsi": "refactor_rsi", "refactor": "refactor_rsi",
    }

    @classmethod
    def get(cls, profile: str = "code_rsi") -> RSIProfileConfig:
        """Restituisce la configurazione del profilo richiesto o code_rsi come fallback."""
        key = cls._ALIASES.get(profile.lower().strip(), "code_rsi")
        return cls.PROFILES[key]

    @classmethod
    def get_strict(cls, profile: str) -> RSIProfileConfig:
        """Restituisce il profilo registrato in modalita fail-closed per profili sconosciuti."""
        norm = (profile or "").lower().strip()
        if norm not in cls._ALIASES:
            raise ValueError(f"Profilo RSI sconosciuto: {profile!r}")
        return cls.PROFILES[cls._ALIASES[norm]]

    @classmethod
    def is_legacy_alias(cls, profile: str) -> bool:
        """Indica se il nome profilo usa un alias legacy (producer/orchestrator)."""
        return (profile or "").lower().strip() in cls._LEGACY_ALIASES

    @classmethod
    def list_profiles(cls) -> List[str]:
        """Restituisce la lista ordinata dei 6 nomi profilo registrati."""
        return list(cls.PROFILES.keys())


def _safe_nonneg_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _finite_unit_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num < 0.0:
        return None
    return num


def _evaluate_hard_gates_v2(
    defects: RSIDefectVector,
    unit_tests_total: int,
    failed_tests: int,
    tests_skipped: int,
    s_taint: int,
    dast_passed: int,
    mock_count: int,
    f_holdout: int,
    scope_creep: int,
    dry_run: int,
    xfailed_tests: int = 0,
    deselected_tests: int = 0,
) -> Tuple[int, int, List[str]]:
    """Valuta i vincoli lessicografici G_hard e calcola Delta_hard."""
    checks: Tuple[Tuple[str, bool, int], ...] = (
        ("unit_tests_total>0", unit_tests_total > 0, 1 if unit_tests_total <= 0 else 0),
        ("failed_tests==0", failed_tests == 0, failed_tests),
        ("tests_skipped==0", tests_skipped == 0, tests_skipped),
        ("xfailed==0", xfailed_tests == 0, xfailed_tests),
        ("deselected==0", deselected_tests == 0, deselected_tests),
        ("S_taint==0", s_taint == 0, s_taint),
        ("sast_critical==0", defects.sast_critical == 0, defects.sast_critical),
        ("dast_passed==1", dast_passed == 1, 0 if dast_passed == 1 else 1),
        ("E_poc==0", defects.poc_confirmed_exploits == 0, defects.poc_confirmed_exploits),
        ("G_dec==0", defects.deception_gaming_count == 0, defects.deception_gaming_count),
        ("mock_count==0", mock_count == 0, mock_count),
        ("F_holdout==0", f_holdout == 0, f_holdout),
        ("ScopeCreep==0", scope_creep == 0, scope_creep),
        ("C_viol==0", defects.contract_violations == 0, defects.contract_violations),
        ("H_k==0", defects.hallucinated_refs == 0, defects.hallucinated_refs),
        ("dry_run==0", dry_run == 0, dry_run),
    )
    failed_names = [name for name, ok, _ in checks if not ok]
    delta_hard = sum(max(1, weight) if not ok else 0 for _, ok, weight in checks)
    g_hard = 1 if not failed_names else 0
    return g_hard, delta_hard, failed_names


def _collect_unmeasured_reasons_v2(
    has_python_diff: bool,
    k_mut_val: Optional[float],
    c_branch_val: Optional[float],
    mutants_total: Optional[int],
    unit_tests_total: Optional[int],
    ste100_score: Optional[float],
    report_status: Optional[str],
    timed_out: bool,
    defects: RSIDefectVector,
) -> List[str]:
    """Identifica i termini attivi mancanti, None, vuoti, in timeout o a 0 mutanti."""
    reasons: List[str] = list(defects.unmeasured_components)
    if timed_out:
        reasons.append("TIMEOUT")
    if report_status is not None and not str(report_status).strip():
        reasons.append("EMPTY_STATUS")
    if unit_tests_total is None or unit_tests_total <= 0:
        reasons.append("MISSING_TESTS")
    if has_python_diff:
        if k_mut_val is None:
            reasons.append("MISSING_K_MUT_DIFF")
        if mutants_total is not None and mutants_total <= 0:
            reasons.append("ZERO_MUTANTS_GENERATED")
        if c_branch_val is None:
            reasons.append("MISSING_C_BRANCH_DIFF")
    elif ste100_score is None:
        reasons.append("MISSING_STE100_SCORE")
    return sorted(set(reasons))


def compute_candidate_sort_key(
    result_or_g_hard: Any,
    delta_hard: int = 0,
    q_v2: float = 0.0,
) -> Tuple[int, int, float]:
    """Restituisce la tupla di ordinamento lessicografico (G_hard, -Delta_hard, Q_v2)."""
    if isinstance(result_or_g_hard, dict):
        return (
            int(result_or_g_hard.get("g_hard", 0)),
            -int(result_or_g_hard.get("delta_hard", 0)),
            float(result_or_g_hard.get("q_v2", 0.0)),
        )
    return (int(result_or_g_hard), -int(delta_hard), float(q_v2))


def _score_raw_and_tier_v2(
    has_python_diff: bool, p_pass: float, q_soft: float, k_n: float, c_n: float, s_n: float,
    unmeasured_reasons: List[str], g_hard: int, gaming_count: int, failed_gates: Sequence[str],
) -> Tuple[Dict[str, float], float, str, float]:
    if has_python_diff:
        weights = {"w_pass": 0.35, "w_mut": 0.30, "w_branch": 0.20, "w_soft": 0.15, "w_ste100": 0.0}
        raw_q = 100.0 * (0.35 * p_pass + 0.30 * k_n + 0.20 * c_n + 0.15 * q_soft)
    else:
        weights = {"w_pass": 0.40, "w_mut": 0.0, "w_branch": 0.0, "w_soft": 0.35, "w_ste100": 0.25}
        raw_q = 100.0 * (0.40 * p_pass + 0.35 * q_soft + 0.25 * s_n)
    clamped = round(max(0.0, min(100.0, raw_q)), 4)
    if gaming_count > 0:
        return weights, 0.0, "FAIL", clamped
    has_non_empty_hard_fail = any(g not in ("unit_tests_total>0", "UNMEASURED_GATE") for g in failed_gates)
    if g_hard == 0 and has_non_empty_hard_fail:
        return weights, min(clamped, 49.9), "FAIL", clamped
    if unmeasured_reasons:
        return weights, min(clamped, 49.9), "UNMEASURED", clamped
    if g_hard == 0:
        return weights, min(clamped, 49.9), "FAIL", clamped
    return weights, clamped, ("CERTIFIED_PASS" if has_python_diff else "STATIC_PASS"), clamped


def _apply_strict_unmeasured_gate(
    strict_unmeasured_gate: bool, unmeasured_reasons: List[str],
    g_hard: int, delta_hard: int, failed_gates: List[str],
) -> Tuple[int, int]:
    if strict_unmeasured_gate and unmeasured_reasons:
        failed_gates.append("UNMEASURED_GATE")
        return 0, delta_hard + len(unmeasured_reasons)
    return g_hard, delta_hard


def compute_fitness_v2(
    defects: RSIDefectVector, *, has_python_diff: bool = True, k_mut_diff: Optional[float] = None,
    c_branch_diff: Optional[float] = None, mutants_total: Optional[int] = None, tests_skipped: int = 0,
    s_taint: int = 0, dast_passed: bool | int = True, mock_count: int = 0, f_holdout: int = 0,
    scope_creep: int = 0, dry_run: bool | int = False, ste100_score: Optional[float] = 1.0,
    report_status: Optional[str] = "PASS", timed_out: bool = False, unit_tests_total: Optional[int] = None,
    unit_tests_passed: Optional[int] = None, failed_tests: Optional[int] = None,
    strict_unmeasured_gate: bool = False, xfailed_tests: int = 0, deselected_tests: int = 0,
) -> Dict[str, Any]:
    """Calcola Q_v2(S_k), G_hard, Delta_hard, gaming_penalty e tier certificativo."""
    passed_eff, total_eff = defects.effective_totals()
    eff_total = total_eff if unit_tests_total is None else max(0, int(unit_tests_total))
    eff_passed = passed_eff if unit_tests_passed is None else max(0, int(unit_tests_passed))
    eff_failed = defects.tests_failed if failed_tests is None else max(0, int(failed_tests))
    eff_scope_creep = _safe_nonneg_int(scope_creep)
    g_hard, delta_hard, failed_gates = _evaluate_hard_gates_v2(
        defects=defects, unit_tests_total=eff_total, failed_tests=eff_failed, tests_skipped=_safe_nonneg_int(tests_skipped),
        s_taint=_safe_nonneg_int(s_taint), dast_passed=1 if bool(dast_passed) else 0, mock_count=_safe_nonneg_int(mock_count),
        f_holdout=_safe_nonneg_int(f_holdout), scope_creep=eff_scope_creep, dry_run=1 if bool(dry_run) else 0,
        xfailed_tests=_safe_nonneg_int(xfailed_tests), deselected_tests=_safe_nonneg_int(deselected_tests),
    )
    k_val, c_val, s_val = _finite_unit_float(k_mut_diff), _finite_unit_float(c_branch_diff), _finite_unit_float(ste100_score)
    unmeasured_reasons = _collect_unmeasured_reasons_v2(
        has_python_diff=has_python_diff, k_mut_val=k_val, c_branch_val=c_val, mutants_total=mutants_total,
        unit_tests_total=eff_total if (unit_tests_total is not None or eff_total > 0) else total_eff,
        ste100_score=s_val, report_status=report_status, timed_out=timed_out, defects=defects,
    )
    g_hard, delta_hard = _apply_strict_unmeasured_gate(strict_unmeasured_gate, unmeasured_reasons, g_hard, delta_hard, failed_gates)
    p_pass = max(0.0, min(1.0, float(eff_passed) / float(eff_total))) if eff_total > 0 else 0.0
    non_scope_sem = max(0, defects.semantic_drift_findings - eff_scope_creep)
    delta_soft = 5 * defects.high_findings + 2 * defects.medium_findings + defects.low_findings + defects.doc_drift + 8 * non_scope_sem
    q_soft = 1.0 / (1.0 + (float(delta_soft) / 20.0))
    k_n = min(1.0, k_val / 0.85) if k_val is not None else 0.0
    c_n = min(1.0, c_val / 0.82) if c_val is not None else 0.0
    s_n = min(1.0, s_val) if s_val is not None else 0.0
    weights, q_v2, tier, q_v2_raw = _score_raw_and_tier_v2(
        has_python_diff, p_pass, q_soft, k_n, c_n, s_n, unmeasured_reasons, g_hard, defects.deception_gaming_count, failed_gates
    )
    gaming_penalty = -10000 if defects.deception_gaming_count > 0 else 0
    return {
        "q_v2": q_v2, "q_v2_raw": q_v2_raw, "g_hard": g_hard, "delta_hard": delta_hard, "delta_soft": delta_soft,
        "failed_hard_gates": failed_gates, "gaming_penalty": gaming_penalty, "certification_tier": tier,
        "has_python_diff": has_python_diff, "k_n": round(k_n, 4), "c_n": round(c_n, 4),
        "p_pass": round(p_pass, 4), "q_soft": round(q_soft, 4), "active_weights": weights,
        "unmeasured_reasons": unmeasured_reasons, "sort_key": [g_hard, -delta_hard, q_v2],
    }


def compute_delta(defects: RSIDefectVector, profile: str = "code_rsi") -> int:
    """Calcola la metrica lineare pesata Delta_k secondo il profilo specificato."""
    cfg = RSIProfileRegistry.get(profile)
    w_sast, w_tfail, w_c, w_h, w_m, w_l, w_g = cfg.weights
    raw_delta = (
        w_sast * defects.sast_critical + w_tfail * defects.tests_failed + w_c * defects.contract_violations
        + w_h * defects.high_findings + w_m * defects.medium_findings + w_l * defects.low_findings
        + w_g * defects.doc_drift + 20 * defects.poc_confirmed_exploits
        + 12 * defects.semantic_drift_findings + 100 * defects.deception_gaming_count
    )
    if w_tfail == 0 and defects.tests_failed > 0:
        raw_delta += 10 * defects.tests_failed
    if defects.hallucinated_refs > 0:
        raw_delta += 25 * defects.hallucinated_refs
    return raw_delta


def compute_fitness(defects: RSIDefectVector, delta_k: Optional[int] = None, profile: str = "code_rsi") -> float:
    """Calcola il punteggio di fitness Q(S_k) in [0, 100] con tetto UNMEASURED 49.9."""
    if defects.deception_gaming_count > 0:
        return 0.0
    cfg = RSIProfileRegistry.get(profile)
    d_val = compute_delta(defects, profile=profile) if delta_k is None else delta_k
    if cfg.test_weight <= 0.0:
        if d_val == 0 and defects.tests_failed > 0:
            d_val += 10 * defects.tests_failed
        q_val = cfg.delta_weight / (1.0 + (float(d_val) / cfg.delta_scale))
        return round(min(q_val, 49.9) if defects.unmeasured_components else q_val, 4)

    passed, total = defects.effective_totals()
    pass_ratio = max(0.0, min(1.0, float(passed) / float(total))) if total > 0 else 0.0
    q_val = (cfg.test_weight * pass_ratio) + (cfg.delta_weight / (1.0 + (float(d_val) / cfg.delta_scale)))
    return round(min(q_val, 49.9) if defects.unmeasured_components else q_val, 4)


def verify_ste100_compliance(text: str, max_sentence_words: int = 20) -> Dict[str, Any]:
    """Verifica la conformita ASD-STE100 delegando al modulo SSOT nk_transcript_tools."""
    return get_ste100_validator()(text, max_sentence_words=max_sentence_words)


_fallback_verify_ste100_compliance = verify_ste100_compliance

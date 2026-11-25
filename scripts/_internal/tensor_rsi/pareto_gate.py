# -*- coding: utf-8 -*-
"""Gate decisionale gerarchico Tier 0 (G_hard) -> Tier 1 (epsilon=0) -> Tier 2 (epsilon-Pareto)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from _internal.nk_common.staging_manifest import safe_finite_float
from _internal.tensor_rsi.config_loader import load_tensor_v3_config
from _internal.tensor_rsi.schemas import (
    ACCEPT_DECISION_VERDICTS, ClassifiedTrackLiteral, DecisionVerdictLiteral,
    MetricSnapshot, ParetoDecisionResult, SecondaryQualityVector,
)

MIN_KILL_RATE_FLOOR: float = 0.80
MIN_BRANCH_COVERAGE_FLOOR: float = 0.82
MIN_DIRECTIONAL_EFFECT: float = 0.005

_EPSILON_BANDS: Dict[str, Tuple[float, float, float, float]] = {
    "CODE_TRACK": (0.015, 0.015, 0.040, 0.020),
    "DOC_TRACK": (0.010, 0.020, 0.030, 0.005),
}
_TRACK_WEIGHTS: Dict[str, Tuple[float, float, float, float]] = {
    "IMPROVEMENT": (0.35, 0.35, 0.20, 0.10),
    "OPTIMIZATION": (0.20, 0.30, 0.40, 0.10),
    "DOC_SPEC": (0.15, 0.30, 0.15, 0.40),
    "CONTROL": (0.35, 0.35, 0.20, 0.10),
}
_SEC_NAMES: Tuple[str, str, str, str] = ("v_sec_hyg", "v_qual", "v_eff", "v_ste100")


def _load_track_rules(
    intent_track: str, classified_track: str, workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float], float, float, float]:
    cfg = load_tensor_v3_config(workspace_root)
    it_cfg = cfg.get("intent_tracks", {}).get(intent_track, {})
    raw_eps = it_cfg.get("secondary_epsilon")
    eps = tuple(float(x) for x in raw_eps) if isinstance(raw_eps, list) and len(raw_eps) == 4 else _EPSILON_BANDS.get(intent_track, _EPSILON_BANDS["CODE_TRACK"])
    ct_cfg = cfg.get("classified_track_weights", {}).get(classified_track, {})
    raw_w = ct_cfg.get("weights")
    weights = tuple(float(x) for x in raw_w) if isinstance(raw_w, list) and len(raw_w) == 4 else _TRACK_WEIGHTS.get(classified_track, _TRACK_WEIGHTS["IMPROVEMENT"])
    min_eff = float(it_cfg.get("min_effect", MIN_DIRECTIONAL_EFFECT))
    floors = it_cfg.get("hard_floors", {}) if isinstance(it_cfg.get("hard_floors"), dict) else {}
    return eps, weights, min_eff, float(floors.get("min_kill_rate", MIN_KILL_RATE_FLOOR)), float(floors.get("min_branch_coverage", MIN_BRANCH_COVERAGE_FLOOR))  # type: ignore[return-value]


def compute_secondary_vector(
    *, medium_findings: int = 0, low_findings: int = 0, dirty_orphans: int = 0, doc_drift: int = 0,
    semantic_drift: int = 0, duration_s: float = 0.0, loc_delta: int = 0, ste100_warnings: int = 0,
    latency_budget_s: float = 28.0,
) -> SecondaryQualityVector:
    """Calcola v(S) in [0,1]^4 escludendo high_findings e gestendo NaN/Inf fail-closed."""
    hyg_pen = (3 * max(0, medium_findings) + max(0, low_findings) + 2 * max(0, dirty_orphans)) / 10.0
    v_sec_hyg = round(1.0 / (1.0 + hyg_pen), 6)
    delta_soft_t2 = 2 * max(0, medium_findings) + max(0, low_findings) + max(0, doc_drift) + 8 * max(0, semantic_drift)
    v_qual = round(1.0 / (1.0 + (float(delta_soft_t2) / 20.0)), 6)
    eff_dur = safe_finite_float(duration_s, default=float("nan"))
    eff_budget = safe_finite_float(latency_budget_s, default=float("nan"))
    t_frac = 0.0 if (not math.isfinite(eff_dur) or not math.isfinite(eff_budget) or eff_budget <= 0.0) else max(0.0, min(1.0, 1.0 - (max(0.0, eff_dur) / eff_budget)))
    loc_frac = max(0.0, min(1.0, 1.0 - (float(max(0, loc_delta - 150)) / 450.0)))
    v_eff = round(0.5 * t_frac + 0.5 * loc_frac, 6)
    v_ste100 = round(max(0.0, min(1.0, 1.0 - 0.1 * float(max(0, ste100_warnings)))), 6)
    return SecondaryQualityVector(v_sec_hyg=v_sec_hyg, v_qual=v_qual, v_eff=v_eff, v_ste100=v_ste100)


def _check_code_hard_gates(snap: MetricSnapshot, min_k: float, min_c: float) -> List[str]:
    """Valuta i vincoli disgiunti G_hard_code, governance e pavimenti k_mut/c_branch."""
    checks: List[Tuple[str, bool]] = [
        ("tests_total>0", snap.tests_total > 0), ("failed_tests==0", snap.failed_tests == 0),
        ("tests_skipped==0", snap.tests_skipped == 0), ("xfailed==0", snap.xfailed == 0),
        ("deselected==0", snap.deselected == 0), ("s_taint==0", snap.s_taint == 0),
        ("sast_critical==0", snap.sast_critical == 0), ("dast_passed==1", snap.dast_passed == 1),
        ("poc_confirmed_exploits==0", snap.poc_confirmed_exploits == 0),
        ("deception_gaming_count==0", snap.deception_gaming_count == 0),
        ("mock_count==0", snap.mock_count == 0), ("f_holdout==0", snap.f_holdout == 0),
        ("scope_creep==0", snap.scope_creep == 0), ("contract_violations==0", snap.contract_violations == 0),
        ("hallucinated_refs==0", snap.hallucinated_refs == 0), ("dry_run==0", snap.dry_run == 0),
        ("gt14_governance_ok==1", snap.gt14_governance_ok == 1),
        ("twin_parity_ok==1", snap.twin_parity_ok == 1),
    ]
    if snap.certification_tier != "STATIC_PASS":
        k_val = safe_finite_float(snap.primary.k_mut, default=0.0)
        c_val = safe_finite_float(snap.primary.c_branch, default=0.0)
        checks.append((f"k_mut>={min_k:.2f}", k_val >= min_k))
        checks.append((f"c_branch>={min_c:.2f}", c_val >= min_c))
    return [name for name, ok in checks if not ok]


def _check_doc_hard_gates(snap: MetricSnapshot) -> List[str]:
    """Valuta i vincoli disgiunti G_hard_doc inclusi SAST, scope e xfailed/deselected."""
    checks: Tuple[Tuple[str, bool], ...] = (
        ("broken_links==0", snap.broken_links == 0), ("phantom_scripts==0", snap.phantom_scripts == 0),
        ("invalid_json==0", snap.invalid_json == 0), ("mojibake==0", snap.mojibake == 0),
        ("sast_critical==0", snap.sast_critical == 0), ("scope_creep==0", snap.scope_creep == 0),
        ("xfailed==0", snap.xfailed == 0), ("deselected==0", snap.deselected == 0),
        ("contract_violations==0", snap.contract_violations == 0),
        ("hallucinated_refs==0", snap.hallucinated_refs == 0),
        ("deception_gaming_count==0", snap.deception_gaming_count == 0),
        ("gt14_governance_ok==1", snap.gt14_governance_ok == 1),
        ("twin_parity_ok==1", snap.twin_parity_ok == 1), ("dry_run==0", snap.dry_run == 0),
    )
    failed = [name for name, ok in checks if not ok]
    if snap.tests_total > 0 and (snap.failed_tests > 0 or snap.tests_skipped > 0):
        failed.append("contract_tests_ok")
    return failed


def evaluate_tier0_hard_gates(
    snap: MetricSnapshot, *, workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[int, Tuple[str, ...]]:
    """Valuta Tier 0 fail-closed sui gate disgiunti e sullo stato UNMEASURED/NaN."""
    failed: List[str] = list(snap.failed_hard_gates)
    if snap.certification_tier == "UNMEASURED" or snap.unmeasured_reasons:
        failed.append("UNMEASURED")
    if not math.isfinite(snap.q_v2):
        failed.append("NON_FINITE_Q_V2")
    if snap.intent_track == "DOC_TRACK":
        failed.extend(_check_doc_hard_gates(snap))
    else:
        _, _, _, min_k, min_c = _load_track_rules(snap.intent_track, "IMPROVEMENT", workspace_root)
        failed.extend(_check_code_hard_gates(snap, min_k, min_c))
    if snap.g_hard == 0 and not failed:
        failed.append("ORACLE_G_HARD_ZERO")
    unique = tuple(dict.fromkeys(failed))
    return (0 if unique else 1), unique


def _tier1_pairs(snap: MetricSnapshot) -> Tuple[Tuple[str, float], ...]:
    p = snap.primary
    if snap.intent_track == "DOC_TRACK":
        return (("p_pass", float(p.p_pass)), ("-doc_drift", -float(p.doc_drift_count)), ("-sem_drift", -float(p.semantic_drift_count)), ("-critical", -float(p.critical_count)), ("-high", -float(p.high_count)))
    return (("p_pass", float(p.p_pass)), ("k_mut", float(p.k_mut)), ("c_branch", float(p.c_branch)), ("-critical", -float(p.critical_count)), ("-high", -float(p.high_count)))


def _t1_pair_deltas(base_pairs: Tuple[Tuple[str, float], ...], curr_pairs: Tuple[Tuple[str, float], ...]) -> Tuple[List[str], bool]:
    regressions: List[str] = []
    improved = False
    for (name, b_val), (_, c_val) in zip(base_pairs, curr_pairs):
        if not (math.isfinite(b_val) and math.isfinite(c_val)):
            regressions.append(f"{name}:non_finite")
        elif c_val + 1e-12 < b_val:
            regressions.append(f"{name}:{b_val:.4f}->{c_val:.4f}")
        elif c_val > b_val + 1e-12:
            improved = True
    return regressions, improved


def _evaluate_tier1_ratchet(base: MetricSnapshot, curr: MetricSnapshot) -> Tuple[List[str], bool]:
    if base.intent_track != curr.intent_track:
        return [f"intent_track_mismatch:{base.intent_track}->{curr.intent_track}"], False
    return _t1_pair_deltas(_tier1_pairs(base), _tier1_pairs(curr))


def _secondary_tuple(sec: SecondaryQualityVector) -> Tuple[float, float, float, float]:
    return tuple(safe_finite_float(getattr(sec, nm), default=0.0) for nm in _SEC_NAMES)  # type: ignore[return-value]


def _is_optimal_tier_state(curr: MetricSnapshot, g_hard: int, delta_v: Tuple[float, float, float, float]) -> bool:
    if g_hard != 1 or curr.failed_hard_gates or curr.q_v2 < 100.0:
        return False
    return curr.certification_tier in ("CERTIFIED_PASS", "STATIC_PASS") and all(dv >= -1e-12 for dv in delta_v)


def _resolve_tier2_verdict(
    curr: MetricSnapshot, g_hard: int, tier1_improved: bool, delta_v: Tuple[float, float, float, float],
    band_violations: List[str], proj: float, min_effect: float,
) -> Tuple[DecisionVerdictLiteral, bool, str]:
    if band_violations:
        return "REJECT_TIER2_EPSILON_BAND", False, f"Violazione banda epsilon Tier 2: {band_violations}"
    if _is_optimal_tier_state(curr, g_hard, delta_v):
        return "CONVERGED_OPTIMAL", True, "Stato ottimo certificato (g_hard=1, q_v2=100.0)."
    if tier1_improved:
        return "ACCEPT_TIER1_DOMINANT", True, "Dominanza Tier 1 con tenuta banda epsilon Tier 2."
    if proj >= min_effect - 1e-12:
        verdict: DecisionVerdictLiteral = "ACCEPT_PARETO_STRICT" if all(dv >= -1e-12 for dv in delta_v) else "ACCEPT_EPSILON_DIRECTIONAL"
        return verdict, True, f"{'Miglioramento Pareto stretto' if verdict == 'ACCEPT_PARETO_STRICT' else 'Accettazione direzionale entro banda'} (proj={proj:.4f})."
    return "REJECT_TIER2_NO_GAIN", False, f"Guadagno direzionale insufficiente ({proj:.4f} < {min_effect:.4f})."


def _check_pre_pareto_block(
    curr: MetricSnapshot, eff_min: float, workspace_root: Optional[Union[str, Path]],
) -> Tuple[int, Optional[ParetoDecisionResult]]:
    if curr.epistemic_conflict:
        return 0, ParetoDecisionResult(verdict="HALT_EPISTEMIC_CONFLICT", accepted=False, tier_stopped_at=0, directional_projection=0.0, min_effect=eff_min, delta_secondary=(0.0, 0.0, 0.0, 0.0), rationale="Conflitto epistemico rilevato in Tier 0: arresto immediato.")
    g_hard, failed_t0 = evaluate_tier0_hard_gates(curr, workspace_root=workspace_root)
    if g_hard == 0:
        return 0, ParetoDecisionResult(verdict="REJECT_TIER0_HARD_GATE", accepted=False, tier_stopped_at=0, directional_projection=0.0, min_effect=eff_min, delta_secondary=(0.0, 0.0, 0.0, 0.0), band_violations=failed_t0, rationale=f"Fallimento Tier 0 G_hard: {list(failed_t0[:4])}")
    return g_hard, None


def evaluate_pareto_decision(
    base: MetricSnapshot, curr: MetricSnapshot, classified_track: ClassifiedTrackLiteral = "IMPROVEMENT",
    *, min_effect: float = -1.0, workspace_root: Optional[Union[str, Path]] = None,
) -> ParetoDecisionResult:
    """Applica il gate gerarchico Tier 0 -> Tier 1 -> Tier 2 e restituisce ParetoDecisionResult."""
    eps, weights, cfg_min_eff, _, _ = _load_track_rules(curr.intent_track, classified_track, workspace_root)
    eff_min = cfg_min_eff if min_effect < 0.0 else safe_finite_float(min_effect, default=cfg_min_eff)
    g_hard, early_block = _check_pre_pareto_block(curr, eff_min, workspace_root)
    if early_block is not None:
        return early_block
    t1_regressions, t1_improved = _evaluate_tier1_ratchet(base, curr)
    b_sec, c_sec = _secondary_tuple(base.secondary), _secondary_tuple(curr.secondary)
    delta_v = tuple(round(c_sec[i] - b_sec[i], 6) for i in range(4))  # type: ignore[assignment]
    if t1_regressions:
        return ParetoDecisionResult(verdict="REJECT_TIER1_REGRESSION", accepted=False, tier_stopped_at=1, directional_projection=0.0, min_effect=eff_min, delta_secondary=delta_v, primary_regressions=tuple(t1_regressions), rationale=f"Regressione Tier 1 (epsilon=0): {t1_regressions}")
    band_violations = [f"{_SEC_NAMES[i]}:{delta_v[i]:.4f}<-{eps[i]:.4f}" for i in range(4) if delta_v[i] < -eps[i] - 1e-12]
    proj = round(sum(weights[i] * delta_v[i] for i in range(4)), 6)
    verdict, accepted, rationale = _resolve_tier2_verdict(curr, g_hard, t1_improved, delta_v, band_violations, proj, eff_min)
    return ParetoDecisionResult(verdict=verdict, accepted=(verdict in ACCEPT_DECISION_VERDICTS and accepted), tier_stopped_at=2, directional_projection=proj, min_effect=eff_min, delta_secondary=delta_v, band_violations=tuple(band_violations), rationale=rationale)

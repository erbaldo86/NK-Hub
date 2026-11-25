# -*- coding: utf-8 -*-
"""Helper per floor costituzionali di ricalibrazione Ratchet (allow_ratchet_down)."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional

from _internal.quality_baseline_manager.constants import (
    MAX_PYTEST_DURATION_CEIL,
    MIN_COMBINED_COVERAGE_FLOOR,
    MIN_GOLDEN_TESTS_FLOOR,
    MIN_TRUE_BRANCH_COVERAGE_FLOOR,
    RECALIBRATED_COUNT_KEYS,
    _extract_numeric_metric,
    _facade_attr,
    extract_baseline_metrics_v1_fallback,
    load_baseline,
)

_RATCHET_DOWN_COVERAGE_KEYS = {
    "combined_coverage_pct",
    "statement_coverage_pct",
    "true_branch_coverage_pct",
    "branch_coverage_pct",
}


def _is_below_floor(effective_metrics: Dict[str, Any], floor: float, *keys: str) -> bool:
    val = _extract_numeric_metric(effective_metrics, *keys)
    return val is not None and val < floor


def _has_passing_coverage_floors(effective_metrics: Dict[str, Any]) -> bool:
    """Verifica i floor costituzionali minimi di copertura se presenti nel payload."""
    if _is_below_floor(effective_metrics, MIN_COMBINED_COVERAGE_FLOOR, "combined_coverage_pct"):
        return False
    if _is_below_floor(effective_metrics, MIN_COMBINED_COVERAGE_FLOOR, "statement_coverage_pct"):
        return False
    return not _is_below_floor(effective_metrics, MIN_TRUE_BRANCH_COVERAGE_FLOOR, "true_branch_coverage_pct", "branch_coverage_pct")


def _has_passing_rate_and_zeros(effective_metrics: Dict[str, Any]) -> bool:
    """Verifica pass_rate == 100%, zero failed_tests/tests_skipped e duration <= MAX_PYTEST_DURATION_CEIL."""
    rate_val = _extract_numeric_metric(effective_metrics, "pass_rate_pct", "unit_tests_pass_pct")
    if rate_val is not None and round(rate_val, 4) < 100.0:
        return False
    fail_val = _extract_numeric_metric(effective_metrics, "failed_tests", "tests_failed")
    skip_val = _extract_numeric_metric(effective_metrics, "tests_skipped", "skipped_tests")
    if (fail_val is not None and fail_val > 0) or (skip_val is not None and skip_val > 0):
        return False
    dur_val = _extract_numeric_metric(effective_metrics, "pytest_duration_s")
    return not (dur_val is not None and dur_val > MAX_PYTEST_DURATION_CEIL)


def _ratchet_allows_test_count_key(current_val: float, effective_metrics: Dict[str, Any]) -> bool:
    """Verifica i floor costituzionali dei test prima di autorizzare allow_ratchet_down."""
    if current_val < MIN_GOLDEN_TESTS_FLOOR:
        return False
    tot_val = _extract_numeric_metric(effective_metrics, "total_golden_tests", "unit_tests_total")
    pass_val = _extract_numeric_metric(effective_metrics, "unit_tests_passed")
    if tot_val is not None and (tot_val < MIN_GOLDEN_TESTS_FLOOR or (pass_val is not None and pass_val != tot_val)):
        return False
    return _has_passing_rate_and_zeros(effective_metrics) and _has_passing_coverage_floors(effective_metrics)


def _ratchet_allows_coverage_key(metric_key: str, current_val: float, effective_metrics: Dict[str, Any]) -> bool:
    """Consente ricalibrazione coverage nel rispetto dei floor (>=85% combined/stmt, >=75% branch)."""
    comb_val = _extract_numeric_metric(effective_metrics, "combined_coverage_pct")
    if comb_val is not None and comb_val < MIN_COMBINED_COVERAGE_FLOOR:
        return False
    if metric_key in ("true_branch_coverage_pct", "branch_coverage_pct"):
        return current_val >= MIN_TRUE_BRANCH_COVERAGE_FLOOR
    return current_val >= MIN_COMBINED_COVERAGE_FLOOR


def _allows_authorized_ratchet_down(metric_key: str, current_val: float, effective_metrics: Dict[str, Any]) -> bool:
    """Consente allow_ratchet_down solo nel rispetto dei floor costituzionali inviolabili."""
    if metric_key == "skills_audited":
        return current_val > 0
    if metric_key in RECALIBRATED_COUNT_KEYS:
        return _ratchet_allows_test_count_key(current_val, effective_metrics)
    if metric_key == "pytest_duration_s":
        return 0.0 <= current_val <= MAX_PYTEST_DURATION_CEIL
    if metric_key in _RATCHET_DOWN_COVERAGE_KEYS:
        return _ratchet_allows_coverage_key(metric_key, current_val, effective_metrics)
    return False


def _carry_clean_baseline_sast(baseline_path: str, recal_metrics: Dict[str, Any]) -> None:
    load_fn = _facade_attr("load_baseline", load_baseline)
    try:
        baseline = load_fn(baseline_path)
    except (OSError, ValueError):
        return
    if not isinstance(baseline, dict):
        return
    base_metrics = extract_baseline_metrics_v1_fallback(baseline)
    sast_val = _extract_numeric_metric(base_metrics, "sast_critical_violations")
    if sast_val is not None and sast_val == 0:
        recal_metrics["sast_critical_violations"] = 0


def _build_and_apply_recalibration(
    baseline_path: str,
    target_golden_tests: int,
    allow_ratchet_down: bool,
    pytest_duration_s: Optional[float],
    combined_coverage_pct: Optional[float],
    update_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """Costruisce il payload di ricalibrazione Schema v2 e applica update_baseline_metrics."""
    if pytest_duration_s is not None and float(pytest_duration_s) > MAX_PYTEST_DURATION_CEIL:
        return {"status": "REJECTED", "verdict": "FAIL", "message": f"Ricalibrazione rifiutata: pytest_duration_s={pytest_duration_s}s > {MAX_PYTEST_DURATION_CEIL}s.", "regressions": []}
    if combined_coverage_pct is not None and float(combined_coverage_pct) < MIN_COMBINED_COVERAGE_FLOOR:
        return {"status": "REJECTED", "verdict": "FAIL", "message": f"Ricalibrazione rifiutata: combined_coverage_pct={combined_coverage_pct}% < {MIN_COMBINED_COVERAGE_FLOOR}%.", "regressions": []}
    recal_metrics: Dict[str, Any] = {
        "total_golden_tests": target_golden_tests,
        "unit_tests_total": target_golden_tests,
        "unit_tests_passed": target_golden_tests,
        "unit_tests_pass_pct": 100.0,
        "pass_rate_pct": 100.0,
        "failed_tests": 0,
        "tests_skipped": 0,
    }
    _carry_clean_baseline_sast(baseline_path, recal_metrics)
    if pytest_duration_s is not None:
        recal_metrics["pytest_duration_s"] = float(pytest_duration_s)
    if combined_coverage_pct is not None:
        recal_metrics["combined_coverage_pct"] = float(combined_coverage_pct)
    upd_fn = _facade_attr("update_baseline_metrics", update_fn)
    if upd_fn is None:
        return {"status": "REJECTED", "verdict": "FAIL", "message": "update_baseline_metrics non disponibile.", "regressions": []}
    try:
        params = inspect.signature(upd_fn).parameters
        has_ratchet_arg = "allow_ratchet_down" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        has_ratchet_arg = False
    if has_ratchet_arg:
        return upd_fn(baseline_path, recal_metrics, allow_ratchet_down=allow_ratchet_down)
    return upd_fn(baseline_path, recal_metrics)

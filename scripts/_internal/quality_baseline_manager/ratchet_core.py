# -*- coding: utf-8 -*-
"""Valutazione conformita Ratchet Schema v2, CAS baseline mutex, check read-only e ricalibrazione."""

from __future__ import annotations

import inspect
import json
import operator
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from _internal.quality_baseline_manager.cas_guard import baseline_mutex, check_baseline_cas
from _internal.quality_baseline_manager.constants import (
    CONSTITUTIONAL_GOLDEN_FLOOR,
    DEFAULT_BASELINE_VERSION,
    LOWER_IS_BETTER_KEYS,
    MIN_GOLDEN_TESTS_FLOOR,
    PHANTOM_V1_METRIC_KEYS,
    REQUIRED_RATCHET_KEYS,
    SCHEMA_VERSION_V2,
    _atomic_write_baseline,
    _extract_numeric_metric,
    _facade_attr,
    _verify_oracle_lock_coherence,
    create_default_baseline,
    extract_baseline_metrics_v1_fallback,
    load_baseline,
)
from _internal.quality_baseline_manager.recalibrate_helpers import (  # noqa: F401
    _RATCHET_DOWN_COVERAGE_KEYS,
    _allows_authorized_ratchet_down,
    _build_and_apply_recalibration,
    _ratchet_allows_coverage_key,
    _ratchet_allows_test_count_key,
)

_DIRECTION_SPECS = {"lower_is_better": ("threshold_max", operator.gt, "peggiorata", "<="), "higher_is_better": ("threshold_min", operator.lt, "regredita", ">=")}


def _metric_bound(base_info: Any, bound_key: str, fallback: Any) -> Any:
    return base_info.get(bound_key, fallback) if isinstance(base_info, dict) else fallback


def _mirror_pass_rate_aliases(clean: Dict[str, Any]) -> None:
    if "pass_rate_pct" in clean and "unit_tests_pass_pct" not in clean:
        clean["unit_tests_pass_pct"] = clean["pass_rate_pct"]
    elif "unit_tests_pass_pct" in clean and "pass_rate_pct" not in clean:
        clean["pass_rate_pct"] = clean["unit_tests_pass_pct"]


def _sanitize_and_expand_metrics(current_metrics: Any) -> Dict[str, Any]:
    clean: Dict[str, Any] = {
        k: v
        for k, v in (current_metrics.items() if isinstance(current_metrics, dict) else [])
        if k not in ("__recalibrate_authorized__", "_recalibrated")
    }
    gt68_nested = clean.get("golden_tests_68")
    if isinstance(gt68_nested, dict):
        if "passed" in gt68_nested and "unit_tests_passed" not in clean:
            clean["unit_tests_passed"] = gt68_nested["passed"]
        if "total" in gt68_nested:
            clean.setdefault("unit_tests_total", gt68_nested["total"])
            clean.setdefault("total_golden_tests", gt68_nested["total"])
        if "pass_rate_pct" in gt68_nested:
            clean.setdefault("pass_rate_pct", gt68_nested["pass_rate_pct"])
            clean.setdefault("unit_tests_pass_pct", gt68_nested["pass_rate_pct"])
    _mirror_pass_rate_aliases(clean)
    return clean


def _required_keys_for_eval(baseline_metrics: Dict[str, Any], effective_metrics: Dict[str, Any]) -> List[str]:
    keys = list(REQUIRED_RATCHET_KEYS)
    mut_active = effective_metrics.get("mutation_active") is True
    has_mut = mut_active or "diff_mutation_kill_rate" in baseline_metrics
    if has_mut and (mut_active or "diff_mutation_kill_rate" in effective_metrics):
        keys.append("diff_mutation_kill_rate")
    return keys


def _is_key_applicable(req_key: str, baseline_metrics: Dict[str, Any], effective_metrics: Dict[str, Any]) -> bool:
    if req_key in baseline_metrics:
        return True
    return req_key == "diff_mutation_kill_rate" and effective_metrics.get("mutation_active") is True


def _collect_missing_required_metrics(baseline_metrics: Dict[str, Any], effective_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    missing: List[Dict[str, Any]] = []
    for req_key in _required_keys_for_eval(baseline_metrics, effective_metrics):
        if _is_key_applicable(req_key, baseline_metrics, effective_metrics) and _extract_numeric_metric(effective_metrics, req_key) is None:
            base_info = baseline_metrics.get(req_key)
            base_val = base_info.get("value") if isinstance(base_info, dict) else base_info
            missing.append({
                "metric": req_key, "baseline_value": base_val, "current_value": None,
                "error_code": "MISSING_REQUIRED_METRIC", "message": f"MISSING_REQUIRED_METRIC: chiave obbligatoria '{req_key}' mancante.",
            })
    return missing


def _eval_single_regression(
    metric_key: str, raw_curr: Any, baseline_metrics: Dict[str, Any],
    effective_metrics: Dict[str, Any], allow_ratchet_down: bool,
) -> Optional[Dict[str, Any]]:
    current_val = _metric_bound(raw_curr, "value", raw_curr)
    if not isinstance(current_val, (int, float)) or isinstance(current_val, bool) or metric_key not in baseline_metrics:
        return None
    if allow_ratchet_down and _allows_authorized_ratchet_down(metric_key, float(current_val), effective_metrics):
        return None
    base_info = baseline_metrics[metric_key]
    base_val = _metric_bound(base_info, "value", base_info)
    default_dir = "lower_is_better" if metric_key in LOWER_IS_BETTER_KEYS else "higher_is_better"
    direction = _metric_bound(base_info, "direction", default_dir)
    if not (spec := _DIRECTION_SPECS.get(direction)):
        return None
    bound = _metric_bound(base_info, spec[0], base_val)
    if not spec[1](current_val, bound):
        return None
    return {"metric": metric_key, "baseline_value": bound, "current_value": current_val, "direction": direction, "message": f"Metrica {metric_key} {spec[2]}: {bound} -> {current_val} (atteso {spec[3]} {bound})"}


def _compare_metric_regressions(baseline_metrics: Dict[str, Any], effective_metrics: Dict[str, Any], allow_ratchet_down: bool) -> List[Dict[str, Any]]:
    regressions = _collect_missing_required_metrics(baseline_metrics, effective_metrics)
    for metric_key, raw_curr in effective_metrics.items():
        if (reg := _eval_single_regression(metric_key, raw_curr, baseline_metrics, effective_metrics, allow_ratchet_down)) is not None:
            regressions.append(reg)
    return regressions


def _evaluate_baseline_compliance(
    baseline_path: str, current_metrics: dict, project_name: str = "NK_Project",
    preloaded_baseline: Optional[dict] = None, allow_ratchet_down: bool = False, read_only: bool = False,
) -> Tuple[dict, Optional[dict]]:
    load_fn = _facade_attr("load_baseline", load_baseline)
    write_fn = _facade_attr("_atomic_write_baseline", _atomic_write_baseline)
    lock_fn = _facade_attr("_verify_oracle_lock_coherence", _verify_oracle_lock_coherence)

    if preloaded_baseline is not None:
        baseline: Optional[dict] = preloaded_baseline
    else:
        try:
            baseline = load_fn(baseline_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            return ({"status": "ERROR", "verdict": "FAIL", "message": f"Errore lettura baseline in {baseline_path}: {exc}", "regressions": [{"metric": "__corrupted_baseline__", "message": f"Baseline JSON corrotto: {exc}"}]}, None)

    effective_metrics = _sanitize_and_expand_metrics(current_metrics)
    if baseline is None:
        if read_only:
            return ({"status": "MISSING", "verdict": "FAIL", "message": f"Baseline assente in {baseline_path} (modalita check read-only).", "regressions": [{"metric": "__missing_baseline__", "message": f"Baseline non trovato: {baseline_path}"}]}, None)
        new_baseline = create_default_baseline(project_name, effective_metrics)
        write_fn(baseline_path, new_baseline)
        return ({"status": "INITIALIZED", "verdict": "PASS", "message": f"Nuovo baseline di qualita inizializzato in {baseline_path}", "regressions": []}, new_baseline)

    if "metrics" in baseline and not isinstance(baseline.get("metrics"), dict):
        return ({"status": "ERROR", "verdict": "FAIL", "message": "Sezione metrics non valida nel file baseline.", "regressions": [{"metric": "metrics", "message": "Formato metrics non valido"}]}, baseline)

    baseline_metrics = extract_baseline_metrics_v1_fallback(baseline)
    regressions = _compare_metric_regressions(baseline_metrics, effective_metrics, allow_ratchet_down)
    regressions.extend(lock_fn(baseline_path))
    verdict = "FAIL" if regressions else "PASS"
    details_str = "; ".join(r.get("message", "") for r in regressions) if regressions else "Baseline e oracle_lock coerenti."
    return ({"status": "SUCCESS", "verdict": verdict, "baseline_date": baseline.get("baseline_date"), "metrics_checked": len([k for k in effective_metrics if k in baseline_metrics]), "regressions": regressions, "details": details_str}, baseline)


def _check_baseline_compliance_ro(baseline_path: str, current_metrics: dict, project_name: str, allow_ratchet_down: bool) -> dict:
    eval_fn = _facade_attr("_evaluate_baseline_compliance", _evaluate_baseline_compliance)
    try:
        params = inspect.signature(eval_fn).parameters
        has_ro = "read_only" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        has_ro = False
    if has_ro:
        compliance, _ = eval_fn(baseline_path, current_metrics, project_name=project_name, allow_ratchet_down=allow_ratchet_down, read_only=True)
    else:
        compliance, _ = eval_fn(baseline_path, current_metrics, project_name=project_name, allow_ratchet_down=allow_ratchet_down)
    return compliance


def check_baseline_compliance(baseline_path: str, current_metrics: dict, project_name: str = "NK_Project", allow_ratchet_down: bool = False) -> dict:
    """Verifica rigorosamente read-only che nessuna metrica corrente sia regredita."""
    return _check_baseline_compliance_ro(baseline_path, current_metrics, project_name, allow_ratchet_down)


def _gate_fail(metric: str, base_val: Any, curr_val: Any, direction: str, msg: str, summary: str) -> dict:
    return {"status": "REJECTED", "verdict": "FAIL", "message": summary, "regressions": [{"metric": metric, "baseline_value": base_val, "current_value": curr_val, "direction": direction, "message": msg}]}


def _check_test_floor_and_rate(tot_val: Optional[float], pass_val: Optional[float], rate_val: Optional[float]) -> Optional[dict]:
    if tot_val is not None and tot_val < MIN_GOLDEN_TESTS_FLOOR:
        return _gate_fail("total_golden_tests", MIN_GOLDEN_TESTS_FLOOR, tot_val, "higher_is_better", f"total_tests ({int(tot_val)}) < {MIN_GOLDEN_TESTS_FLOOR}", f"Aggiornamento rifiutato: total_tests={int(tot_val)} < {MIN_GOLDEN_TESTS_FLOOR}.")
    if tot_val is not None and pass_val is not None and pass_val != tot_val:
        comp_rate = round((pass_val / tot_val) * 100.0, 2) if tot_val > 0 else 0.0
        return _gate_fail("pass_rate_pct", 100.0, comp_rate, "higher_is_better", "Richiesto pass_rate == 100.0%.", f"Aggiornamento rifiutato: pass_rate={comp_rate}% != 100.0%.")
    if rate_val is not None and round(rate_val, 4) < 100.0:
        return _gate_fail("pass_rate_pct", 100.0, rate_val, "higher_is_better", "Richiesto pass_rate == 100.0%.", f"Aggiornamento rifiutato: pass_rate={rate_val}% != 100.0%.")
    return None


def _check_zero_fail_and_skip(fail_val: Optional[float], skip_val: Optional[float]) -> Optional[dict]:
    if fail_val is not None and fail_val > 0:
        return _gate_fail("failed_tests", 0, fail_val, "lower_is_better", "Zero test falliti richiesti.", f"Aggiornamento rifiutato: failed_tests={int(fail_val)} > 0.")
    if skip_val is not None and skip_val > 0:
        return _gate_fail("tests_skipped", 0, skip_val, "lower_is_better", "Zero test skippati richiesti.", f"Aggiornamento rifiutato: tests_skipped={int(skip_val)} > 0.")
    return None


def _validate_legitimate_update_gate(metrics: dict) -> Optional[dict]:
    if not isinstance(metrics, dict):
        return {"status": "REJECTED", "verdict": "FAIL", "message": "Metriche di aggiornamento non valide.", "regressions": []}
    tot_val = _extract_numeric_metric(metrics, "total_golden_tests", "unit_tests_total")
    pass_val = _extract_numeric_metric(metrics, "unit_tests_passed")
    rate_val = _extract_numeric_metric(metrics, "pass_rate_pct", "unit_tests_pass_pct", "unit_tests_pass_rate")
    fail_val = _extract_numeric_metric(metrics, "failed_tests", "tests_failed")
    skip_val = _extract_numeric_metric(metrics, "tests_skipped", "skipped_tests")
    return _check_test_floor_and_rate(tot_val, pass_val, rate_val) or _check_zero_fail_and_skip(fail_val, skip_val)


def _apply_v2_baseline_write(baseline_path: str, baseline: dict, new_metrics: dict, reason: Optional[str], write_fn: Any) -> dict:
    clean_metrics = {
        k: v for k, v in new_metrics.items()
        if k not in ("__recalibrate_authorized__", "_recalibrated", "mutation_active") and k not in PHANTOM_V1_METRIC_KEYS
    }
    now_iso = datetime.now().isoformat()
    baseline["_version"] = DEFAULT_BASELINE_VERSION
    baseline["schema_version"] = SCHEMA_VERSION_V2
    baseline["last_updated"] = now_iso
    baseline.pop("_recalibrated", None)
    metrics_section = baseline.setdefault("metrics", {})
    if isinstance(metrics_section, dict):
        for p_key in [k for k in metrics_section if k in PHANTOM_V1_METRIC_KEYS]:
            metrics_section.pop(p_key, None)
        for k, raw_v in clean_metrics.items():
            v = raw_v.get("value") if isinstance(raw_v, dict) else raw_v
            if k in baseline and not isinstance(baseline[k], dict):
                baseline[k] = v
            if isinstance(metrics_section.get(k), dict):
                metrics_section[k]["value"] = v
            else:
                metrics_section[k] = {"value": v, "direction": "lower_is_better" if k in LOWER_IS_BETTER_KEYS else "higher_is_better"}
    hist_entry: Dict[str, Any] = {"timestamp": now_iso, "metrics": clean_metrics}
    if reason:
        hist_entry["reason"] = str(reason).strip()
    baseline.setdefault("history", []).append(hist_entry)
    write_fn(baseline_path, baseline)
    return {"status": "UPDATED", "verdict": "PASS", "message": f"Quality Baseline Schema v2 aggiornato in {baseline_path}", "regressions": []}


def _run_locked_baseline_update(
    baseline_path: str, new_metrics: dict, allow_ratchet_down: bool, reason: Optional[str],
    expected_baseline_sha256: Optional[str], write_fn: Any, eval_fn: Any,
) -> dict:
    with baseline_mutex(baseline_path):
        cas_ok, _cur_sha, cas_err = check_baseline_cas(baseline_path, expected_baseline_sha256)
        if not cas_ok and cas_err is not None:
            return cas_err
        compliance, baseline = eval_fn(baseline_path, new_metrics, allow_ratchet_down=allow_ratchet_down)
        if compliance.get("status") == "INITIALIZED":
            return compliance
        if compliance.get("verdict") == "FAIL" or compliance.get("status") == "ERROR":
            return {"status": "REJECTED", "verdict": "FAIL", "message": compliance.get("message", "Aggiornamento rifiutato per violazione Ratchet."), "regressions": compliance.get("regressions", [])}
        if baseline is None:
            return compliance
        return _apply_v2_baseline_write(baseline_path, baseline, new_metrics, reason, write_fn)


def update_baseline_metrics(
    baseline_path: str, new_metrics: dict, allow_ratchet_down: bool = False, reason: Optional[str] = None,
    *, expected_baseline_sha256: Optional[str] = None,
) -> dict:
    """Verifica pavimento >= 93, CAS SHA-256 sotto Win32NamedMutex, pass_rate == 100.0 e Ratchet."""
    load_fn = _facade_attr("load_baseline", load_baseline)
    write_fn = _facade_attr("_atomic_write_baseline", _atomic_write_baseline)
    eval_fn = _facade_attr("_evaluate_baseline_compliance", _evaluate_baseline_compliance)

    gate_err = _validate_legitimate_update_gate(new_metrics)
    if gate_err is not None:
        try:
            load_fn(baseline_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            return {"status": "REJECTED", "verdict": "FAIL", "message": f"Errore lettura baseline in {baseline_path}: {exc}", "regressions": [{"metric": "__corrupted_baseline__", "message": f"Baseline JSON corrotto: {exc}"}]}
        return gate_err

    return _run_locked_baseline_update(
        baseline_path, new_metrics, allow_ratchet_down, reason, expected_baseline_sha256, write_fn, eval_fn,
    )


def recalibrate_baseline(
    baseline_path: str, target_golden_tests: int = CONSTITUTIONAL_GOLDEN_FLOOR, allow_ratchet_down: bool = False,
    *, pytest_duration_s: Optional[float] = None, combined_coverage_pct: Optional[float] = None, reason: Optional[str] = None,
) -> dict:
    """Ricalibra il baseline rispettando i floor costituzionali e allow_ratchet_down esplicito."""
    _ = reason
    if target_golden_tests < MIN_GOLDEN_TESTS_FLOOR:
        return {"status": "REJECTED", "verdict": "FAIL", "message": f"Soglia {target_golden_tests} inferiore al minimo costituzionale ({MIN_GOLDEN_TESTS_FLOOR}).", "regressions": []}
    return _build_and_apply_recalibration(
        baseline_path, target_golden_tests, allow_ratchet_down, pytest_duration_s, combined_coverage_pct, update_fn=update_baseline_metrics
    )

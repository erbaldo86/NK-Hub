# -*- coding: utf-8 -*-
"""Valutazione conformita Ratchet, pavimento costituzionale GT-13 e ricalibrazione."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Tuple

from _internal.quality_baseline_manager.constants import (
    CONSTITUTIONAL_GOLDEN_FLOOR,
    DEFAULT_BASELINE_VERSION,
    LOWER_IS_BETTER_KEYS,
    MIN_GOLDEN_TESTS_FLOOR,
    _atomic_write_baseline,
    _extract_numeric_metric,
    _facade_attr,
    _verify_oracle_lock_coherence,
    create_default_baseline,
    load_baseline,
)


def _evaluate_baseline_compliance(
    baseline_path: str,
    current_metrics: dict,
    project_name: str = "NK_Project",
    preloaded_baseline: Optional[dict] = None,
    allow_ratchet_down: bool = False,
) -> Tuple[dict, Optional[dict]]:
    """Valuta la conformita al baseline caricando il file JSON al massimo una sola volta."""
    load_fn = _facade_attr("load_baseline", load_baseline)
    write_fn = _facade_attr("_atomic_write_baseline", _atomic_write_baseline)
    lock_fn = _facade_attr("_verify_oracle_lock_coherence", _verify_oracle_lock_coherence)

    if preloaded_baseline is not None:
        baseline: Optional[dict] = preloaded_baseline
    else:
        try:
            baseline = load_fn(baseline_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            return (
                {
                    "status": "ERROR", "verdict": "FAIL",
                    "message": f"Errore lettura baseline in {baseline_path}: {exc}",
                    "regressions": [{"metric": "__corrupted_baseline__", "message": f"Baseline JSON corrotto: {exc}"}],
                },
                None,
            )

    clean_input = {
        k: v
        for k, v in (current_metrics.items() if isinstance(current_metrics, dict) else [])
        if k not in ("__recalibrate_authorized__", "_recalibrated")
    }

    if baseline is None:
        new_baseline = create_default_baseline(project_name, clean_input)
        write_fn(baseline_path, new_baseline)
        return (
            {
                "status": "INITIALIZED", "verdict": "PASS",
                "message": f"Nuovo baseline di qualita inizializzato in {baseline_path}",
                "regressions": [],
            },
            new_baseline,
        )

    if "metrics" in baseline:
        raw_bm = baseline.get("metrics")
        if not isinstance(raw_bm, dict):
            return (
                {
                    "status": "ERROR", "verdict": "FAIL",
                    "message": "Sezione metrics non valida nel file baseline.",
                    "regressions": [{"metric": "metrics", "message": "Formato metrics non valido"}],
                },
                baseline,
            )
        baseline_metrics = raw_bm
    else:
        baseline_metrics = {
            bk: bv for bk, bv in baseline.items()
            if isinstance(bv, (int, float, dict)) and not isinstance(bv, bool)
            and bk not in ("invariants", "metadata")
        }

    effective_metrics = dict(current_metrics) if isinstance(current_metrics, dict) else {}
    gt68_nested = effective_metrics.get("golden_tests_68")
    if isinstance(gt68_nested, dict):
        if "passed" in gt68_nested and "unit_tests_passed" not in effective_metrics:
            effective_metrics["unit_tests_passed"] = gt68_nested["passed"]
        if "total" in gt68_nested:
            effective_metrics.setdefault("unit_tests_total", gt68_nested["total"])
            effective_metrics.setdefault("total_golden_tests", gt68_nested["total"])
        if "pass_rate_pct" in gt68_nested:
            effective_metrics.setdefault("pass_rate_pct", gt68_nested["pass_rate_pct"])
            effective_metrics.setdefault("unit_tests_pass_pct", gt68_nested["pass_rate_pct"])

    regressions = []
    for metric_key, raw_curr in effective_metrics.items():
        if metric_key in ("__recalibrate_authorized__", "_recalibrated"):
            continue
        current_val = raw_curr.get("value") if isinstance(raw_curr, dict) else raw_curr
        if not isinstance(current_val, (int, float)) or isinstance(current_val, bool):
            continue
        if metric_key in baseline_metrics:
            base_info = baseline_metrics[metric_key]
            base_val = base_info.get("value") if isinstance(base_info, dict) else base_info
            default_dir = "lower_is_better" if metric_key in LOWER_IS_BETTER_KEYS else "higher_is_better"
            direction = base_info.get("direction", default_dir) if isinstance(base_info, dict) else default_dir

            if allow_ratchet_down and metric_key == "skills_audited":
                if isinstance(current_val, (int, float)) and current_val > 0:
                    continue

            if direction == "lower_is_better":
                max_allowed = base_info.get("threshold_max", base_val) if isinstance(base_info, dict) else base_val
                if current_val > max_allowed:
                    regressions.append(
                        {
                            "metric": metric_key, "baseline_value": max_allowed,
                            "current_value": current_val, "direction": direction,
                            "message": f"Metrica {metric_key} peggiorata: {max_allowed} -> {current_val} (atteso <= {max_allowed})",
                        }
                    )
            elif direction == "higher_is_better" and current_val < base_val:
                regressions.append(
                    {
                        "metric": metric_key, "baseline_value": base_val,
                        "current_value": current_val, "direction": direction,
                        "message": f"Metrica {metric_key} regredita: {base_val} -> {current_val} (atteso >= {base_val})",
                    }
                )

    regressions.extend(lock_fn(baseline_path))
    verdict = "FAIL" if len(regressions) > 0 else "PASS"
    details_str = (
        "; ".join(r.get("message", "") for r in regressions)
        if regressions
        else "Baseline e oracle_lock coerenti."
    )
    return (
        {
            "status": "SUCCESS", "verdict": verdict,
            "baseline_date": baseline.get("baseline_date"),
            "metrics_checked": len([k for k in effective_metrics if k in baseline_metrics]),
            "regressions": regressions, "details": details_str,
        },
        baseline,
    )


def check_baseline_compliance(
    baseline_path: str,
    current_metrics: dict,
    project_name: str = "NK_Project",
    allow_ratchet_down: bool = False,
) -> dict:
    """Verifica che nessuna metrica corrente sia regredita rispetto al baseline."""
    eval_fn = _facade_attr("_evaluate_baseline_compliance", _evaluate_baseline_compliance)
    compliance, _ = eval_fn(
        baseline_path, current_metrics, project_name=project_name, allow_ratchet_down=allow_ratchet_down
    )
    return compliance


def _validate_legitimate_update_gate(metrics: dict) -> Optional[dict]:
    """Verifica il pavimento costituzionale MIN_GOLDEN_TESTS_FLOOR e pass_rate == 100.0."""
    if not isinstance(metrics, dict):
        return {"status": "REJECTED", "verdict": "FAIL", "message": "Metriche di aggiornamento non valide.", "regressions": []}

    tot_val = _extract_numeric_metric(metrics, "total_golden_tests", "unit_tests_total")
    pass_val = _extract_numeric_metric(metrics, "unit_tests_passed")
    rate_val = _extract_numeric_metric(
        metrics, "pass_rate_pct", "unit_tests_pass_pct", "unit_tests_pass_rate", "pass_rate_percent"
    )
    fail_val = _extract_numeric_metric(metrics, "failed_tests", "tests_failed")

    if tot_val is not None and tot_val < MIN_GOLDEN_TESTS_FLOOR:
        return {
            "status": "REJECTED", "verdict": "FAIL",
            "message": (
                f"Aggiornamento rifiutato: total_tests={int(tot_val)} inferiore al pavimento "
                f"costituzionale MIN_GOLDEN_TESTS_FLOOR={MIN_GOLDEN_TESTS_FLOOR}."
            ),
            "regressions": [
                {
                    "metric": "total_golden_tests", "baseline_value": MIN_GOLDEN_TESTS_FLOOR,
                    "current_value": tot_val, "direction": "higher_is_better",
                    "message": f"total_tests ({int(tot_val)}) < {MIN_GOLDEN_TESTS_FLOOR}",
                }
            ],
        }

    if tot_val is not None and pass_val is not None and pass_val != tot_val:
        computed_rate = round((pass_val / tot_val) * 100.0, 2) if tot_val > 0 else 0.0
        return {
            "status": "REJECTED", "verdict": "FAIL",
            "message": f"Aggiornamento rifiutato: pass_rate={computed_rate}% != 100.0% ({int(pass_val)}/{int(tot_val)}).",
            "regressions": [
                {
                    "metric": "pass_rate_pct", "baseline_value": 100.0,
                    "current_value": computed_rate, "direction": "higher_is_better",
                    "message": "Richiesto pass_rate == 100.0% per aggiornare il baseline.",
                }
            ],
        }

    if rate_val is not None and round(rate_val, 4) < 100.0:
        return {
            "status": "REJECTED", "verdict": "FAIL",
            "message": f"Aggiornamento rifiutato: pass_rate={rate_val}% != 100.0%.",
            "regressions": [
                {
                    "metric": "pass_rate_pct", "baseline_value": 100.0,
                    "current_value": rate_val, "direction": "higher_is_better",
                    "message": "Richiesto pass_rate == 100.0% per aggiornare il baseline.",
                }
            ],
        }

    if fail_val is not None and fail_val > 0:
        return {
            "status": "REJECTED", "verdict": "FAIL",
            "message": f"Aggiornamento rifiutato: failed_tests={int(fail_val)} > 0.",
            "regressions": [
                {
                    "metric": "failed_tests", "baseline_value": 0,
                    "current_value": fail_val, "direction": "lower_is_better",
                    "message": "Zero test falliti richiesti per aggiornare il baseline.",
                }
            ],
        }
    return None


def update_baseline_metrics(
    baseline_path: str,
    new_metrics: dict,
    allow_ratchet_down: bool = False,
) -> dict:
    """Verifica pavimento >= 93, pass_rate == 100.0 e Ratchet prima di aggiornare il baseline."""
    load_fn = _facade_attr("load_baseline", load_baseline)
    write_fn = _facade_attr("_atomic_write_baseline", _atomic_write_baseline)
    eval_fn = _facade_attr("_evaluate_baseline_compliance", _evaluate_baseline_compliance)

    gate_err = _validate_legitimate_update_gate(new_metrics)
    if gate_err is not None:
        try:
            load_fn(baseline_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            return {
                "status": "REJECTED", "verdict": "FAIL",
                "message": f"Errore lettura baseline in {baseline_path}: {exc}",
                "regressions": [{"metric": "__corrupted_baseline__", "message": f"Baseline JSON corrotto: {exc}"}],
            }
        return gate_err

    compliance, baseline = eval_fn(baseline_path, new_metrics, allow_ratchet_down=allow_ratchet_down)
    if compliance.get("status") == "INITIALIZED":
        return compliance

    if compliance.get("verdict") == "FAIL" or compliance.get("status") == "ERROR":
        return {
            "status": "REJECTED", "verdict": "FAIL",
            "message": compliance.get("message", "Aggiornamento rifiutato per violazione Ratchet."),
            "regressions": compliance.get("regressions", []),
        }

    if baseline is None:
        return compliance

    clean_metrics = {
        k: v for k, v in new_metrics.items() if k not in ("__recalibrate_authorized__", "_recalibrated")
    }
    now_iso = datetime.now().isoformat()
    baseline["_version"] = DEFAULT_BASELINE_VERSION
    baseline["last_updated"] = now_iso
    baseline.pop("_recalibrated", None)

    metrics_section = baseline.setdefault("metrics", {})
    for k, raw_v in clean_metrics.items():
        v = raw_v.get("value") if isinstance(raw_v, dict) else raw_v
        if k in baseline and not isinstance(baseline[k], dict):
            baseline[k] = v
        if isinstance(metrics_section, dict):
            if k in metrics_section and isinstance(metrics_section[k], dict):
                metrics_section[k]["value"] = v
            else:
                default_dir = "lower_is_better" if k in LOWER_IS_BETTER_KEYS else "higher_is_better"
                metrics_section[k] = {"value": v, "direction": default_dir}

    baseline.setdefault("history", []).append({"timestamp": now_iso, "metrics": clean_metrics})
    write_fn(baseline_path, baseline)
    return {
        "status": "UPDATED", "verdict": "PASS",
        "message": f"Quality Baseline aggiornato con successo in {baseline_path}",
        "regressions": [],
    }


def recalibrate_baseline(
    baseline_path: str,
    target_golden_tests: int = CONSTITUTIONAL_GOLDEN_FLOOR,
) -> dict:
    """Ricalibra il pavimento costituzionale rispettando MIN_GOLDEN_TESTS_FLOOR e il Ratchet."""
    if target_golden_tests < MIN_GOLDEN_TESTS_FLOOR:
        return {
            "status": "REJECTED", "verdict": "FAIL",
            "message": f"Soglia {target_golden_tests} inferiore al minimo costituzionale ({MIN_GOLDEN_TESTS_FLOOR}).",
            "regressions": [],
        }
    recal_metrics = {
        "total_golden_tests": target_golden_tests, "unit_tests_total": target_golden_tests,
        "unit_tests_passed": target_golden_tests, "unit_tests_pass_pct": 100.0,
        "pass_rate_pct": 100.0, "pass_rate_percent": 100.0,
    }
    upd_fn = _facade_attr("update_baseline_metrics", update_baseline_metrics)
    return upd_fn(baseline_path, recal_metrics)

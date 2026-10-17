#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore del Ratchet di qualita per Nexus Keystone v3.3.0.
Modulo: quality_baseline_manager.py.
Implementa la regola [RULE-01.10] (soglia GT-68 Zero-Padding) e la correzione BS-02.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

BASELINE_FILENAME = "quality_baseline.json"
CONSTITUTIONAL_GOLDEN_FLOOR = 68

RECALIBRATED_COUNT_KEYS = {
    "total_golden_tests",
    "unit_tests_total",
    "unit_tests_passed",
}

LOWER_IS_BETTER_KEYS = {
    "sast_critical",
    "sast_critical_violations",
    "rsi_residual_delta",
    "failed_tests",
    "tests_failed",
    "delta_k",
    "vulnerabilities",
    "errors",
}


def load_baseline(baseline_path: str) -> dict:
    """Carica il file baseline JSON. Restituisce None solo se il file non esiste (BS-02)."""
    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(
                "Il contenuto di quality_baseline.json deve essere un dizionario."
            )
        return data
    except FileNotFoundError:
        return None  # type: ignore[return-value]


def create_default_baseline(project_name: str, metrics: dict) -> dict:
    """Crea la struttura iniziale di quality_baseline.json al primo commit."""
    now_iso = datetime.now().isoformat()
    normalized_metrics: Dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            normalized_metrics[k] = v
        else:
            default_dir = (
                "lower_is_better" if k in LOWER_IS_BETTER_KEYS else "higher_is_better"
            )
            normalized_metrics[k] = {"value": v, "direction": default_dir}

    return {
        "_version": "3.3.0-GT68-Pareto-Zero-Padding",
        "project": project_name,
        "baseline_date": now_iso,
        "last_updated": now_iso,
        "metrics": normalized_metrics,
        "ratchet_rule": "no_metric_may_worsen",
        "history": [
            {
                "timestamp": now_iso,
                "metrics": metrics,
            }
        ],
    }


def _is_valid_gt68_recalibration(current_metrics: dict) -> bool:
    """Verifica se le metriche correnti rappresentano la ricalibrazione costituzionale GT-68."""
    raw_gt = current_metrics.get("total_golden_tests")
    gt_val = raw_gt.get("value") if isinstance(raw_gt, dict) else raw_gt
    raw_tot = current_metrics.get("unit_tests_total")
    tot_val = raw_tot.get("value") if isinstance(raw_tot, dict) else raw_tot
    raw_pass = current_metrics.get("unit_tests_passed")
    pass_val = raw_pass.get("value") if isinstance(raw_pass, dict) else raw_pass
    return (
        gt_val == CONSTITUTIONAL_GOLDEN_FLOOR
        and tot_val == CONSTITUTIONAL_GOLDEN_FLOOR
        and pass_val == CONSTITUTIONAL_GOLDEN_FLOOR
    )


def check_baseline_compliance(
    baseline_path: str,
    current_metrics: dict,
    project_name: str = "NK_Project",
) -> dict:
    """Verifica che nessuna metrica corrente sia regredita rispetto al baseline."""
    try:
        baseline = load_baseline(baseline_path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        return {
            "status": "ERROR",
            "verdict": "FAIL",
            "message": f"Errore lettura baseline in {baseline_path}: {exc}",
            "regressions": [
                {
                    "metric": "__corrupted_baseline__",
                    "message": f"Baseline JSON corrotto: {exc}",
                }
            ],
        }

    if baseline is None:
        new_baseline = create_default_baseline(project_name, current_metrics)
        parent_dir = os.path.dirname(os.path.abspath(baseline_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(new_baseline, f, indent=2)
        return {
            "status": "INITIALIZED",
            "verdict": "PASS",
            "message": f"Nuovo baseline di qualita inizializzato in {baseline_path}",
            "regressions": [],
        }

    baseline_metrics = baseline.get("metrics", {})
    if not isinstance(baseline_metrics, dict):
        return {
            "status": "ERROR",
            "verdict": "FAIL",
            "message": "Sezione metrics non valida nel file baseline.",
            "regressions": [
                {"metric": "metrics", "message": "Formato metrics non valido"}
            ],
        }

    regressions = []
    gt68_exempt = _is_valid_gt68_recalibration(current_metrics)

    for metric_key, raw_curr in current_metrics.items():
        current_val = raw_curr.get("value") if isinstance(raw_curr, dict) else raw_curr
        if metric_key in baseline_metrics:
            base_info = baseline_metrics[metric_key]
            base_val = (
                base_info.get("value") if isinstance(base_info, dict) else base_info
            )
            default_dir = (
                "lower_is_better"
                if metric_key in LOWER_IS_BETTER_KEYS
                else "higher_is_better"
            )
            direction = (
                base_info.get("direction", default_dir)
                if isinstance(base_info, dict)
                else default_dir
            )

            if gt68_exempt and metric_key in RECALIBRATED_COUNT_KEYS:
                if current_val >= CONSTITUTIONAL_GOLDEN_FLOOR:
                    continue

            if direction == "lower_is_better" and current_val > base_val:
                regressions.append(
                    {
                        "metric": metric_key,
                        "baseline_value": base_val,
                        "current_value": current_val,
                        "direction": direction,
                        "message": f"Metrica {metric_key} peggiorata: {base_val} -> {current_val} (atteso <= {base_val})",
                    }
                )
            elif direction == "higher_is_better" and current_val < base_val:
                regressions.append(
                    {
                        "metric": metric_key,
                        "baseline_value": base_val,
                        "current_value": current_val,
                        "direction": direction,
                        "message": f"Metrica {metric_key} regredita: {base_val} -> {current_val} (atteso >= {base_val})",
                    }
                )

    verdict = "FAIL" if len(regressions) > 0 else "PASS"

    return {
        "status": "SUCCESS",
        "verdict": verdict,
        "baseline_date": baseline.get("baseline_date"),
        "metrics_checked": len([k for k in current_metrics if k in baseline_metrics]),
        "regressions": regressions,
    }


def update_baseline_metrics(baseline_path: str, new_metrics: dict) -> dict:
    """Verifica il Ratchet e aggiorna il baseline solo in assenza di regressioni o corruzione."""
    compliance = check_baseline_compliance(baseline_path, new_metrics)
    if compliance.get("status") == "INITIALIZED":
        return compliance

    if compliance.get("verdict") == "FAIL" or compliance.get("status") == "ERROR":
        return {
            "status": "REJECTED",
            "verdict": "FAIL",
            "message": compliance.get(
                "message", "Aggiornamento rifiutato per violazione Ratchet."
            ),
            "regressions": compliance.get("regressions", []),
        }

    baseline = load_baseline(baseline_path)
    if baseline is None:
        return compliance

    now_iso = datetime.now().isoformat()
    baseline["last_updated"] = now_iso

    for k, raw_v in new_metrics.items():
        v = raw_v.get("value") if isinstance(raw_v, dict) else raw_v
        if k in baseline["metrics"] and isinstance(baseline["metrics"][k], dict):
            baseline["metrics"][k]["value"] = v
        else:
            default_dir = (
                "lower_is_better" if k in LOWER_IS_BETTER_KEYS else "higher_is_better"
            )
            baseline["metrics"][k] = {"value": v, "direction": default_dir}

    baseline.setdefault("history", []).append(
        {
            "timestamp": now_iso,
            "metrics": new_metrics,
        }
    )

    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)

    return {
        "status": "UPDATED",
        "verdict": "PASS",
        "message": f"Quality Baseline aggiornato con successo in {baseline_path}",
        "regressions": [],
    }


def recalibrate_baseline(
    baseline_path: str,
    target_golden_tests: int = CONSTITUTIONAL_GOLDEN_FLOOR,
) -> dict:
    """Ricalibra il pavimento costituzionale dei Golden Tests preservando il pass rate al 100%."""
    if target_golden_tests < 60:
        return {
            "status": "REJECTED",
            "verdict": "FAIL",
            "message": f"Soglia {target_golden_tests} inferiore al minimo costituzionale (60).",
            "regressions": [],
        }
    recal_metrics = {
        "total_golden_tests": target_golden_tests,
        "unit_tests_total": target_golden_tests,
        "unit_tests_passed": target_golden_tests,
        "unit_tests_pass_pct": 100.0,
        "pass_rate_pct": 100.0,
        "pass_rate_percent": 100.0,
    }
    return update_baseline_metrics(baseline_path, recal_metrics)


def _resolve_default_baseline_path() -> str:
    """Risolve il percorso predefinito di quality_baseline.json nel workspace."""
    script_dir = Path(__file__).resolve().parent
    root_dir = (
        script_dir.parent.parent
        if script_dir.parent.name == ".staging"
        else script_dir.parent
    )
    staging_cand = root_dir / ".staging" / "nk_tracking" / BASELINE_FILENAME
    prod_cand = root_dir / "nk_tracking" / BASELINE_FILENAME
    if staging_cand.exists():
        return str(staging_cand)
    return str(prod_cand)


def main() -> int:
    """Gestisce l'interfaccia CLI retrocompatibile del Quality Baseline Manager."""
    parser = argparse.ArgumentParser(
        description="Gestore del Ratchet di qualita per Nexus Keystone"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default=None,
        help="Azione posizionale: check, update o recalibrate",
    )
    parser.add_argument(
        "pos_file",
        nargs="?",
        default=None,
        help="Percorso posizionale del file quality_baseline.json",
    )
    parser.add_argument(
        "pos_metrics",
        nargs="?",
        default=None,
        help="Stringa JSON delle metriche da verificare o aggiornare",
    )
    parser.add_argument(
        "--file",
        dest="file_flag",
        default=None,
        help="Percorso del file quality_baseline.json",
    )
    parser.add_argument(
        "--update",
        dest="update_json",
        default=None,
        help="Stringa JSON delle metriche da aggiornare nel baseline",
    )
    parser.add_argument(
        "--recalibrate",
        dest="recalibrate_flag",
        action="store_true",
        help="Ricalibra il baseline alla soglia costituzionale GT-68 Zero-Padding",
    )
    parser.add_argument(
        "--check-only",
        "--check",
        dest="check_only",
        action="store_true",
        help="Verifica la conformita del baseline senza modificare il file",
    )
    parser.add_argument(
        "--metrics",
        dest="metrics_json",
        default=None,
        help="Stringa JSON delle metriche da confrontare con il baseline",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )

    args = parser.parse_args()

    cmd = "check"
    if args.recalibrate_flag or (
        args.action and args.action.lower() == "recalibrate"
    ):
        cmd = "recalibrate"
    elif args.update_json is not None or (
        args.action and args.action.lower() == "update"
    ):
        cmd = "update"
    elif args.check_only or (args.action and args.action.lower() == "check"):
        cmd = "check"
    elif args.action and args.action.lower() not in (
        "check",
        "update",
        "recalibrate",
    ):
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "verdict": "FAIL",
                    "usage": 'python quality_baseline_manager.py check|update|recalibrate path/to/baseline.json \'{"metric": 1}\'',
                }
            )
        )
        return 1

    b_path = args.file_flag or args.pos_file or _resolve_default_baseline_path()
    if cmd == "recalibrate":
        res = recalibrate_baseline(b_path, CONSTITUTIONAL_GOLDEN_FLOOR)
        print(json.dumps(res, indent=2))
        return 0 if res.get("verdict") == "PASS" else 1

    raw_metrics = args.update_json or args.metrics_json or args.pos_metrics

    metrics: Dict[str, Any] = {}
    if raw_metrics is not None:
        try:
            metrics = json.loads(raw_metrics)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "status": "ERROR",
                        "verdict": "FAIL",
                        "message": f"JSON metriche non valido: {exc}",
                    }
                )
            )
            return 1
    else:
        try:
            loaded = load_baseline(b_path)
            if loaded is not None and isinstance(loaded.get("metrics"), dict):
                for k, v in loaded["metrics"].items():
                    metrics[k] = v.get("value") if isinstance(v, dict) else v
        except Exception:
            pass

    if cmd == "update":
        res = update_baseline_metrics(b_path, metrics)
    else:
        res = check_baseline_compliance(b_path, metrics)

    print(json.dumps(res, indent=2))
    if res.get("verdict") == "FAIL" or res.get("status") in ("ERROR", "REJECTED"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

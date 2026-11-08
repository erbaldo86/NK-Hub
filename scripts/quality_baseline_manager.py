#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore del Ratchet di qualita per Nexus Keystone v5.2.0-STE100-Unified.
Modulo: quality_baseline_manager.py.
Implementa la regola [RULE-01.10] (soglia GT-68 e suite ortogonale GT-93) e la correzione BS-02.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

BASELINE_FILENAME = "quality_baseline.json"
BASELINE_SCHEMA_VERSION = "5.2.0-STE100-Unified"
DEFAULT_BASELINE_VERSION = BASELINE_SCHEMA_VERSION
MIN_GOLDEN_TESTS_FLOOR = 93
CONSTITUTIONAL_GOLDEN_FLOOR = MIN_GOLDEN_TESTS_FLOOR

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
    "harness_token_overhead_pct",
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
        "_version": DEFAULT_BASELINE_VERSION,
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


def _atomic_write_baseline(baseline_path: str, data: dict) -> None:
    """Scrive atomicamente il file quality_baseline.json tramite file temporaneo e os.replace."""
    abs_path = os.path.abspath(baseline_path)
    parent_dir = os.path.dirname(abs_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    tmp_path = f"{abs_path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, abs_path)


def _is_valid_gt68_recalibration(current_metrics: dict) -> bool:
    """Verifica se le metriche correnti rappresentano la ricalibrazione costituzionale GT-68 o GT-90."""
    raw_gt = current_metrics.get("total_golden_tests")
    gt_val = raw_gt.get("value") if isinstance(raw_gt, dict) else raw_gt
    raw_tot = current_metrics.get("unit_tests_total")
    tot_val = raw_tot.get("value") if isinstance(raw_tot, dict) else raw_tot
    raw_pass = current_metrics.get("unit_tests_passed")
    pass_val = raw_pass.get("value") if isinstance(raw_pass, dict) else raw_pass
    if not (
        isinstance(gt_val, (int, float))
        and isinstance(tot_val, (int, float))
        and isinstance(pass_val, (int, float))
    ):
        return False
    return (
        gt_val in (68, 90, MIN_GOLDEN_TESTS_FLOOR)
        and tot_val == gt_val
        and pass_val == gt_val
    )


def _verify_oracle_lock_coherence(baseline_path: str) -> list:
    """Verifica che tutti i file elencati in oracle_lock.json esistano su disco sotto workspace_root."""
    b_file = Path(baseline_path).resolve()
    if b_file.parent.name == "nk_tracking":
        ws_root = (
            b_file.parent.parent.parent
            if b_file.parent.parent.name == ".staging"
            else b_file.parent.parent
        )
    else:
        ws_root = b_file.parent

    lock_candidates = [
        ws_root / "nk_tracking" / "oracle_lock.json",
        b_file.parent / "oracle_lock.json",
    ]
    lock_file = None
    for cand in lock_candidates:
        if cand.is_file():
            lock_file = cand
            break

    if lock_file is None:
        return []

    anomalies = []
    try:
        lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
        if not isinstance(lock_data, dict):
            return [
                {
                    "metric": "oracle_lock_integrity",
                    "baseline_value": "VALID_DICT",
                    "current_value": "INVALID_ROOT",
                    "direction": "higher_is_better",
                    "message": "Il file oracle_lock.json non contiene un dizionario valido.",
                }
            ]
        locked_entries: list = []
        raw_locked = lock_data.get("locked_files")
        if isinstance(raw_locked, dict):
            locked_entries.extend(str(k) for k in raw_locked.keys())
        elif isinstance(raw_locked, list):
            locked_entries.extend(str(item) for item in raw_locked)

        raw_files = lock_data.get("files")
        if isinstance(raw_files, dict):
            locked_entries.extend(str(k) for k in raw_files.keys())
        elif isinstance(raw_files, list):
            locked_entries.extend(str(item) for item in raw_files)

        for rel_entry in locked_entries:
            cand_root = (ws_root / rel_entry).resolve()
            cand_tests = (ws_root / "tests" / rel_entry).resolve()
            if not (cand_root.exists() or cand_tests.exists()):
                anomalies.append(
                    {
                        "metric": "oracle_lock_integrity",
                        "baseline_value": "PRESENT",
                        "current_value": "MISSING",
                        "direction": "higher_is_better",
                        "message": f"File registrato in oracle_lock.json mancante su disco: {rel_entry}",
                    }
                )
    except Exception as exc:
        anomalies.append(
            {
                "metric": "oracle_lock_integrity",
                "baseline_value": "VALID_JSON",
                "current_value": "CORRUPTED",
                "direction": "higher_is_better",
                "message": f"Errore lettura oracle_lock.json: {exc}",
            }
        )
    return anomalies


def _evaluate_baseline_compliance(
    baseline_path: str,
    current_metrics: dict,
    project_name: str = "NK_Project",
    preloaded_baseline: Optional[dict] = None,
) -> Tuple[dict, Optional[dict]]:
    """Valuta la conformita al baseline caricando il file JSON al massimo una sola volta."""
    if preloaded_baseline is not None:
        baseline: Optional[dict] = preloaded_baseline
    else:
        try:
            baseline = load_baseline(baseline_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            return (
                {
                    "status": "ERROR",
                    "verdict": "FAIL",
                    "message": f"Errore lettura baseline in {baseline_path}: {exc}",
                    "regressions": [
                        {
                            "metric": "__corrupted_baseline__",
                            "message": f"Baseline JSON corrotto: {exc}",
                        }
                    ],
                },
                None,
            )

    if baseline is None:
        new_baseline = create_default_baseline(project_name, current_metrics)
        _atomic_write_baseline(baseline_path, new_baseline)
        return (
            {
                "status": "INITIALIZED",
                "verdict": "PASS",
                "message": f"Nuovo baseline di qualita inizializzato in {baseline_path}",
                "regressions": [],
            },
            new_baseline,
        )

    baseline_metrics = baseline.get("metrics", {})
    if not isinstance(baseline_metrics, dict):
        return (
            {
                "status": "ERROR",
                "verdict": "FAIL",
                "message": "Sezione metrics non valida nel file baseline.",
                "regressions": [
                    {"metric": "metrics", "message": "Formato metrics non valido"}
                ],
            },
            baseline,
        )

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
    gt68_exempt = _is_valid_gt68_recalibration(effective_metrics)

    for metric_key, raw_curr in effective_metrics.items():
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
                if current_val >= 68:
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

    regressions.extend(_verify_oracle_lock_coherence(baseline_path))

    verdict = "FAIL" if len(regressions) > 0 else "PASS"

    return (
        {
            "status": "SUCCESS",
            "verdict": verdict,
            "baseline_date": baseline.get("baseline_date"),
            "metrics_checked": len([k for k in effective_metrics if k in baseline_metrics]),
            "regressions": regressions,
            "details": (
                "; ".join(r.get("message", "") for r in regressions)
                if regressions
                else "Baseline e oracle_lock coerenti."
            ),
        },
        baseline,
    )


def check_baseline_compliance(
    baseline_path: str,
    current_metrics: dict,
    project_name: str = "NK_Project",
) -> dict:
    """Verifica che nessuna metrica corrente sia regredita rispetto al baseline."""
    compliance, _ = _evaluate_baseline_compliance(
        baseline_path, current_metrics, project_name=project_name
    )
    return compliance


compare_against_baseline = check_baseline_compliance
check_regression = check_baseline_compliance


def update_baseline_metrics(baseline_path: str, new_metrics: dict) -> dict:
    """Verifica il Ratchet e aggiorna il baseline solo in assenza di regressioni o corruzione."""
    compliance, baseline = _evaluate_baseline_compliance(baseline_path, new_metrics)
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

    _atomic_write_baseline(baseline_path, baseline)

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
        description="Gestore del Ratchet di qualita per Nexus Keystone v5.2.0-STE100-Unified"
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

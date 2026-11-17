# -*- coding: utf-8 -*-
"""Interfaccia CLI per check, update e recalibrate di quality_baseline_manager."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional

from _internal.quality_baseline_manager.benchmark_runner import measure_live_pytest_metrics
from _internal.quality_baseline_manager.constants import (
    CONSTITUTIONAL_GOLDEN_FLOOR,
    _facade_attr,
    _resolve_default_baseline_path,
    _resolve_workspace_root_from_baseline,
)
from _internal.quality_baseline_manager.ratchet_core import (
    _validate_legitimate_update_gate,
    check_baseline_compliance,
    recalibrate_baseline,
    update_baseline_metrics,
)


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI per il gestore del Ratchet di qualita."""
    parser = argparse.ArgumentParser(
        description="Gestore del Ratchet di qualita per NK Hub Generation 1.0.0-Generation"
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
        nargs="?",
        const="__LIVE__",
        default=None,
        help="Aggiorna il baseline da stringa JSON oppure misurando pytest reale",
    )
    parser.add_argument(
        "--recalibrate",
        dest="recalibrate_flag",
        action="store_true",
        help="Ricalibra il baseline alla soglia costituzionale MIN_GOLDEN_TESTS_FLOOR (93)",
    )
    parser.add_argument(
        "--target-tests",
        dest="target_tests",
        type=int,
        default=None,
        help="Conteggio target opzionale per --recalibrate (>= 93)",
    )
    parser.add_argument(
        "--check-only",
        "--check",
        dest="check_only",
        action="store_true",
        help="Verifica la conformita del baseline senza modificare il file",
    )
    parser.add_argument(
        "--live",
        dest="live_flag",
        action="store_true",
        help="Esegue pytest reale per misurare passed e total su check o update",
    )
    parser.add_argument(
        "--with-coverage",
        dest="with_coverage",
        action="store_true",
        help="Misura la copertura statement e branch reale con pytest-cov durante --live",
    )
    parser.add_argument(
        "--allow-ratchet-down",
        dest="allow_ratchet_down",
        action="store_true",
        help="Consente la riduzione controllata di skills_audited mantenendo 100%% pass",
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
    return parser


def main() -> int:
    """Gestisce l'interfaccia CLI del Quality Baseline Manager."""
    args = _build_cli_parser().parse_args()

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

    resolve_default_fn = _facade_attr("_resolve_default_baseline_path", _resolve_default_baseline_path)
    resolve_ws_fn = _facade_attr("_resolve_workspace_root_from_baseline", _resolve_workspace_root_from_baseline)
    measure_fn = _facade_attr("measure_live_pytest_metrics", measure_live_pytest_metrics)
    recal_fn = _facade_attr("recalibrate_baseline", recalibrate_baseline)
    update_fn = _facade_attr("update_baseline_metrics", update_baseline_metrics)
    check_fn = _facade_attr("check_baseline_compliance", check_baseline_compliance)

    b_path = args.file_flag or args.pos_file or resolve_default_fn()
    if cmd == "recalibrate":
        live_metrics: Optional[Dict[str, Any]] = None
        if args.target_tests is not None:
            target_cnt = args.target_tests
        elif args.live_flag:
            ws_root = resolve_ws_fn(b_path)
            live_metrics = measure_fn(
                ws_root, with_coverage=bool(args.with_coverage)
            )
            if (
                int(live_metrics.get("failed_tests", 0)) > 0
                or float(live_metrics.get("pass_rate_pct", 0.0)) < 100.0
                or (args.with_coverage and "true_branch_coverage_pct" not in live_metrics)
            ):
                res = {
                    "status": "REJECTED",
                    "verdict": "FAIL",
                    "message": (
                        f"Ricalibrazione --live rifiutata: pytest ha fallito "
                        f"({live_metrics.get('unit_tests_passed')}/{live_metrics.get('unit_tests_total')})."
                    ),
                    "live_metrics": live_metrics,
                    "regressions": [],
                }
                print(json.dumps(res, indent=2))
                return 1
            target_cnt = int(live_metrics["unit_tests_passed"])
        else:
            target_cnt = CONSTITUTIONAL_GOLDEN_FLOOR
        res = recal_fn(b_path, target_cnt)
        if live_metrics is not None:
            res["live_metrics"] = live_metrics
        print(json.dumps(res, indent=2))
        return 0 if res.get("verdict") == "PASS" else 1

    explicit_update_str = (
        args.update_json
        if (args.update_json is not None and args.update_json != "__LIVE__")
        else None
    )
    raw_metrics = explicit_update_str or args.metrics_json or args.pos_metrics
    use_live = bool(args.live_flag or (cmd == "update" and raw_metrics is None))

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
    elif use_live:
        ws_root = resolve_ws_fn(b_path)
        metrics = measure_fn(ws_root, with_coverage=bool(args.with_coverage))
    else:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "verdict": "FAIL",
                    "message": "Specificare --live oppure --metrics JSON: auto-confronto del baseline disabilitato.",
                }
            )
        )
        return 1

    if use_live and args.with_coverage and "true_branch_coverage_pct" not in metrics:
        res = {
            "status": "ERROR" if cmd == "check" else "REJECTED",
            "verdict": "FAIL",
            "message": "Coverage JSON mancante o illeggibile in modalita --with-coverage.",
            "regressions": [
                {
                    "metric": "true_branch_coverage_pct",
                    "message": "Coverage JSON mancante o illeggibile in modalita --with-coverage.",
                }
            ],
            "details": "Coverage JSON mancante o illeggibile in modalita --with-coverage.",
            "live_metrics": metrics,
        }
    elif cmd == "update":
        res = update_fn(
            b_path,
            metrics,
            allow_ratchet_down=bool(args.allow_ratchet_down),
        )
    else:
        res = check_fn(
            b_path,
            metrics,
            allow_ratchet_down=bool(args.allow_ratchet_down),
        )
        if use_live and res.get("verdict") == "PASS":
            live_gate_err = _validate_legitimate_update_gate(metrics)
            if live_gate_err is not None:
                res = {
                    "status": "SUCCESS",
                    "verdict": "FAIL",
                    "regressions": live_gate_err.get("regressions", []),
                    "details": live_gate_err.get("message", "Live pytest gate failed."),
                    "live_metrics": metrics,
                }
            else:
                res["live_metrics"] = metrics

    print(json.dumps(res, indent=2))
    if res.get("verdict") == "FAIL" or res.get("status") in ("ERROR", "REJECTED"):
        return 1
    return 0

# -*- coding: utf-8 -*-
"""Interfaccia CLI per check read-only, update CAS e recalibrate Schema v2."""

from __future__ import annotations

import argparse
import inspect
import json
from typing import Any, Dict, Optional, Tuple

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
    parser = argparse.ArgumentParser(description="Gestore Ratchet Qualita NK Hub Generation (Schema v2)")
    parser.add_argument("action", nargs="?", default=None, help="Azione posizionale: check, update o recalibrate")
    parser.add_argument("pos_file", nargs="?", default=None, help="Percorso posizionale del file quality_baseline.json")
    parser.add_argument("pos_metrics", nargs="?", default=None, help="Stringa JSON delle metriche da verificare o aggiornare")
    parser.add_argument("--file", dest="file_flag", default=None, help="Percorso del file quality_baseline.json")
    parser.add_argument("--update", dest="update_json", nargs="?", const="__LIVE__", default=None, help="Aggiorna il baseline da JSON o pytest reale")
    parser.add_argument("--recalibrate", dest="recalibrate_flag", action="store_true", help="Ricalibra il baseline alla soglia costituzionale (>= 93)")
    parser.add_argument("--target-tests", dest="target_tests", type=int, default=None, help="Conteggio target opzionale per --recalibrate (>= 93)")
    parser.add_argument("--check-only", "--check", dest="check_only", action="store_true", help="Verifica read-only del baseline senza modificare il file")
    parser.add_argument("--live", dest="live_flag", action="store_true", help="Esegue pytest reale per misurare passed e total su check o update")
    parser.add_argument("--lane-id", dest="lane_id", type=str, default=None, help="ID lane di staging isolata")
    parser.add_argument("--expected-baseline-sha256", dest="expected_baseline_sha256", type=str, default=None, help="SHA-256 atteso di quality_baseline.json per CAS")
    parser.add_argument("--with-coverage", dest="with_coverage", action="store_true", help="Misura copertura statement/branch con pytest-cov durante --live")
    parser.add_argument("--allow-ratchet-down", dest="allow_ratchet_down", action="store_true", help="Consente riduzione controllata mantenendo floor costituzionali")
    parser.add_argument("--reason", dest="reason", type=str, default=None, help="Motivazione audit obbligatoria quando --allow-ratchet-down e attivo")
    parser.add_argument("--metrics", dest="metrics_json", default=None, help="Stringa JSON delle metriche da confrontare con il baseline")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato in formato JSON")
    return parser


def _call_measure_live(
    measure_fn: Any, ws_root: Any, with_coverage: bool, lane_id: Optional[str] = None
) -> Dict[str, Any]:
    kw: Dict[str, Any] = {"with_coverage": with_coverage}
    if lane_id is not None:
        try:
            params = inspect.signature(measure_fn).parameters
            if "lane_id" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                kw["lane_id"] = lane_id
        except (TypeError, ValueError):
            pass
    return measure_fn(ws_root, **kw)


def _attach_recal_opt_kwargs(
    kwargs: Dict[str, Any], params: Any, accepts_kw: bool, live_metrics: Optional[Dict[str, Any]], reason: Optional[str]
) -> None:
    if reason and (accepts_kw or "reason" in params):
        kwargs["reason"] = reason
    if not isinstance(live_metrics, dict):
        return
    for opt_k in ("pytest_duration_s", "combined_coverage_pct"):
        if (accepts_kw or opt_k in params) and live_metrics.get(opt_k) is not None:
            kwargs[opt_k] = live_metrics.get(opt_k)


def _invoke_recalibrate_fn(
    recal_fn: Any, baseline_path: str, target_cnt: int, allow_ratchet_down: bool,
    live_metrics: Optional[Dict[str, Any]], reason: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        params = inspect.signature(recal_fn).parameters
        accepts_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        params, accepts_kw = {}, False
    kwargs: Dict[str, Any] = {}
    if accepts_kw or "allow_ratchet_down" in params:
        kwargs["allow_ratchet_down"] = allow_ratchet_down
    _attach_recal_opt_kwargs(kwargs, params, accepts_kw, live_metrics, reason)
    return recal_fn(baseline_path, target_cnt, **kwargs)


def _run_recalibrate_cli(args: argparse.Namespace, b_path: str) -> int:
    measure_fn = _facade_attr("measure_live_pytest_metrics", measure_live_pytest_metrics)
    resolve_ws_fn = _facade_attr("_resolve_workspace_root_from_baseline", _resolve_workspace_root_from_baseline)
    recal_fn = _facade_attr("recalibrate_baseline", recalibrate_baseline)
    live_metrics: Optional[Dict[str, Any]] = None
    if args.target_tests is not None:
        target_cnt = args.target_tests
    elif args.live_flag:
        live_metrics = _call_measure_live(measure_fn, resolve_ws_fn(b_path), bool(args.with_coverage), getattr(args, "lane_id", None))
        if int(live_metrics.get("failed_tests", 0)) > 0 or float(live_metrics.get("pass_rate_pct", 0.0)) < 100.0 or (args.with_coverage and "true_branch_coverage_pct" not in live_metrics):
            res = {"status": "REJECTED", "verdict": "FAIL", "message": f"Ricalibrazione --live rifiutata: pytest ha fallito ({live_metrics.get('unit_tests_passed')}/{live_metrics.get('unit_tests_total')}).", "live_metrics": live_metrics, "regressions": []}
            print(json.dumps(res, indent=2))
            return 1
        target_cnt = int(live_metrics["unit_tests_passed"])
    else:
        target_cnt = CONSTITUTIONAL_GOLDEN_FLOOR
    res = _invoke_recalibrate_fn(recal_fn, b_path, target_cnt, bool(args.allow_ratchet_down), live_metrics, reason=args.reason)
    if live_metrics is not None:
        res["live_metrics"] = live_metrics
    if args.reason and str(args.reason).strip():
        res["ratchet_reason"] = str(args.reason).strip()
    print(json.dumps(res, indent=2))
    return 0 if res.get("verdict") == "PASS" else 1


def _resolve_metrics_for_cli(args: argparse.Namespace, cmd: str, b_path: str) -> Tuple[Optional[Dict[str, Any]], bool, int]:
    measure_fn = _facade_attr("measure_live_pytest_metrics", measure_live_pytest_metrics)
    resolve_ws_fn = _facade_attr("_resolve_workspace_root_from_baseline", _resolve_workspace_root_from_baseline)
    explicit_upd = args.update_json if (args.update_json is not None and args.update_json != "__LIVE__") else None
    raw_metrics = explicit_upd or args.metrics_json or args.pos_metrics
    use_live = bool(args.live_flag or (cmd == "update" and raw_metrics is None))
    if raw_metrics is not None:
        try:
            return json.loads(raw_metrics), use_live, 0
        except json.JSONDecodeError as exc:
            print(json.dumps({"status": "ERROR", "verdict": "FAIL", "message": f"JSON metriche non valido: {exc}"}))
            return None, use_live, 1
    if use_live:
        return _call_measure_live(measure_fn, resolve_ws_fn(b_path), bool(args.with_coverage), getattr(args, "lane_id", None)), True, 0
    print(json.dumps({"status": "ERROR", "verdict": "FAIL", "message": "Specificare --live oppure --metrics JSON: auto-confronto del baseline disabilitato."}))
    return None, False, 1


def _run_update_cmd(args: argparse.Namespace, b_path: str, metrics: dict) -> dict:
    upd_fn = _facade_attr("update_baseline_metrics", update_baseline_metrics)
    try:
        u_params = inspect.signature(upd_fn).parameters
        has_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in u_params.values())
    except (TypeError, ValueError):
        u_params, has_var = {}, False
    upd_kw: Dict[str, Any] = {"allow_ratchet_down": bool(args.allow_ratchet_down)}
    if args.reason and (has_var or "reason" in u_params):
        upd_kw["reason"] = str(args.reason).strip()
    if getattr(args, "expected_baseline_sha256", None) and (has_var or "expected_baseline_sha256" in u_params):
        upd_kw["expected_baseline_sha256"] = str(args.expected_baseline_sha256).strip()
    return upd_fn(b_path, metrics, **upd_kw)


def main() -> int:
    """Gestisce l'interfaccia CLI del Quality Baseline Manager."""
    args = _build_cli_parser().parse_args()
    action_low = args.action.lower() if args.action else ""
    if args.action and action_low not in ("check", "update", "recalibrate"):
        print(json.dumps({"status": "ERROR", "verdict": "FAIL", "message": f"Azione CLI sconosciuta: {args.action!r}"}))
        return 1
    if args.check_only and (args.update_json is not None or args.recalibrate_flag or action_low in ("update", "recalibrate")):
        print(json.dumps({"status": "REJECTED", "verdict": "FAIL", "message": "Errore: --check-only e strettamente read-only e vieta update/recalibrate."}))
        return 1
    if args.allow_ratchet_down and (not args.reason or not str(args.reason).strip()):
        print(json.dumps({"status": "REJECTED", "verdict": "FAIL", "message": "Errore: --reason obbligatorio quando si utilizza --allow-ratchet-down."}))
        return 1

    cmd = "recalibrate" if (args.recalibrate_flag or action_low == "recalibrate") else ("update" if (args.update_json is not None or action_low == "update") else "check")
    b_path = args.file_flag or args.pos_file or _facade_attr("_resolve_default_baseline_path", _resolve_default_baseline_path)()
    if cmd == "recalibrate":
        return _run_recalibrate_cli(args, b_path)

    metrics, use_live, err_rc = _resolve_metrics_for_cli(args, cmd, b_path)
    if err_rc != 0 or metrics is None:
        return 1

    if use_live and args.with_coverage and "true_branch_coverage_pct" not in metrics:
        res: Dict[str, Any] = {"status": "ERROR" if cmd == "check" else "REJECTED", "verdict": "FAIL", "message": "Coverage JSON mancante o illeggibile in modalita --with-coverage.", "regressions": [{"metric": "true_branch_coverage_pct", "message": "Coverage JSON mancante o illeggibile in modalita --with-coverage."}], "details": "Coverage JSON mancante o illeggibile in modalita --with-coverage.", "live_metrics": metrics}
    elif cmd == "update":
        res = _run_update_cmd(args, b_path, metrics)
    else:
        res = _facade_attr("check_baseline_compliance", check_baseline_compliance)(b_path, metrics, allow_ratchet_down=bool(args.allow_ratchet_down))
        if use_live and res.get("verdict") == "PASS":
            gate_err = _validate_legitimate_update_gate(metrics)
            if gate_err is not None:
                res = {"status": "SUCCESS", "verdict": "FAIL", "regressions": gate_err.get("regressions", []), "details": gate_err.get("message", "Live pytest gate failed."), "live_metrics": metrics}
            else:
                res["live_metrics"] = metrics
    if args.reason and str(args.reason).strip():
        res["ratchet_reason"] = str(args.reason).strip()
    print(json.dumps(res, indent=2))
    return 1 if (res.get("verdict") == "FAIL" or res.get("status") in ("ERROR", "REJECTED")) else 0

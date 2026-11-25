# -*- coding: utf-8 -*-
"""Sanitizzatori fail-closed per report mutation, SAST, coverage e DAST."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

MIN_KILL_RATE_FLOOR: float = 0.80

_BENCH_COV_KEYS: Tuple[str, ...] = (
    "duration_s",
    "branch_coverage_pct",
    "statement_coverage_pct",
    "true_branch_coverage_pct",
    "combined_coverage_pct",
)
_DAST_FAIL_FLAG_REASONS: Tuple[Tuple[str, str], ...] = (
    ("timed_out", "TIMEOUT"),
    ("memory_exceeded", "MEMORY_EXCEEDED"),
    ("is_dry_run", "DRY_RUN"),
    ("dry_run", "DRY_RUN"),
)


def _is_valid_num(val: Any) -> bool:
    """Verifica che val sia numerico finito e non booleano (rifiuta NaN/Inf)."""
    if isinstance(val, bool):
        return False
    if isinstance(val, int):
        return True
    if isinstance(val, float):
        return math.isfinite(val)
    return False


def _as_nonneg_int(val: Any) -> Optional[int]:
    """Converte val numerico finito >= 0 in int; altrimenti ritorna None."""
    if not _is_valid_num(val):
        return None
    fval = float(val)
    if fval < 0.0:
        return None
    return int(fval)


def _has_invalid_status(payload: Dict[str, Any], allowed: Tuple[str, ...] = ("PASS",)) -> Tuple[bool, str]:
    if "status" not in payload:
        return False, ""
    raw = payload.get("status")
    if raw is None or not str(raw).strip():
        return True, "EMPTY_OR_NONE_STATUS"
    up = str(raw).strip().upper()
    return (up not in allowed), up


def _load_json_report_dict(report: Optional[Any], label: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if report is None:
        return None, {"passed": True, "skipped": True, "high_findings": 0, "violations": []}
    payload: Any = report
    if isinstance(report, (str, Path)):
        rep_path = Path(report)
        if not rep_path.is_file():
            return None, {"passed": False, "skipped": False, "high_findings": 1, "violations": [f"{label} report non trovato: {rep_path}"]}
        try:
            payload = json.loads(rep_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, {"passed": False, "skipped": False, "high_findings": 1, "violations": [f"{label} report JSON invalido: {exc}"]}
    if not isinstance(payload, dict):
        return None, {"passed": False, "skipped": False, "high_findings": 1, "violations": [f"{label} report non valido: atteso dizionario JSON."]}
    return payload, None


def _mutation_res(passed: bool, payload: Dict[str, Any], msg: Optional[str] = None) -> Dict[str, Any]:
    return {
        "passed": passed,
        "skipped": False,
        "kill_rate": payload.get("kill_rate"),
        "mutants_killed": payload.get("mutants_killed", 0),
        "mutants_total": payload.get("mutants_total", 0),
        "high_findings": 0 if passed else 1,
        "violations": [] if msg is None else [msg],
    }


def _mutation_precondition_error(payload: Dict[str, Any]) -> Optional[str]:
    if payload.get("budget_exhausted") is True or payload.get("timed_out") is True:
        return "Mutation gate fallito: budget/timeout esaurito (fail-closed)."
    if payload.get("is_dry_run") is True or payload.get("dry_run") is True:
        return "Mutation gate fallito: dry-run non valido."
    bad_status, status_val = _has_invalid_status(payload, ("PASS", "OK", "CERTIFIED_PASS"))
    return f"Mutation gate fallito: status invalido ({status_val})." if bad_status else None


def _exit_code_ok(payload: Dict[str, Any], *, allow_none: bool = True) -> bool:
    """Rifiuta booleani (es. False==0) ed exit code diversi da zero."""
    if "exit_code" not in payload or payload["exit_code"] is None:
        return allow_none
    ec = payload["exit_code"]
    return isinstance(ec, int) and not isinstance(ec, bool) and ec == 0


def _killed_counts_valid(k_rate: float, tot_f: float, mutants_killed: Any) -> bool:
    if not tot_f.is_integer() or mutants_killed is None or not _is_valid_num(mutants_killed):
        return False
    k_f = float(mutants_killed)
    if not k_f.is_integer() or k_f < 0.0 or k_f > tot_f:
        return False
    return abs(k_rate - (k_f / tot_f)) <= 0.02


def _mutation_metrics_valid(kill_rate: Any, mutants_total: Any, mutants_killed: Any) -> bool:
    if not (_is_valid_num(kill_rate) and _is_valid_num(mutants_total) and float(mutants_total) > 0):
        return False
    k_rate = float(kill_rate)
    if not (0.0 <= k_rate <= 1.0):
        return False
    return _killed_counts_valid(k_rate, float(mutants_total), mutants_killed)


def _evaluate_mutation_dict_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Valuta kill-rate, mutants_total e floor minimo hardcoded (0.80)."""
    if err := _mutation_precondition_error(payload):
        return _mutation_res(False, payload, err)
    kill_rate = payload.get("kill_rate")
    mutants_total = payload.get("mutants_total")
    mutants_killed = payload.get("mutants_killed")
    raw_min_rate = payload.get("min_kill_rate", MIN_KILL_RATE_FLOOR)
    if not _is_valid_num(raw_min_rate):
        return _mutation_res(False, payload, "Mutation gate fallito: min_kill_rate non valido o non finito.")
    min_rate = max(MIN_KILL_RATE_FLOOR, float(raw_min_rate))
    if not _mutation_metrics_valid(kill_rate, mutants_total, mutants_killed):
        return _mutation_res(False, payload, "Mutation gate fallito: campi kill_rate/mutants_total mancanti, None, NaN o zero.")
    if payload.get("passed") is True and float(kill_rate) >= min_rate:
        return _mutation_res(True, payload)
    return _mutation_res(
        False,
        payload,
        f"Mutation gate fallito: kill_rate={kill_rate} (killed={mutants_killed}/{mutants_total}, soglia={min_rate}).",
    )


def audit_mutation_report_payload(mutation_report: Optional[Any]) -> Dict[str, Any]:
    """Valuta in modo fail-closed un report mutation (zero falso green)."""
    payload, early = _load_json_report_dict(mutation_report, "Mutation")
    if early is not None or payload is None:
        return early or {"passed": False, "skipped": False, "high_findings": 1, "violations": ["Mutation report assente."]}
    return _evaluate_mutation_dict_payload(payload)


def _extract_sast_count(payload: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    for key in ("sast_critical", "sast_violations_count", "critical_count", "total_sast_violations"):
        if key in payload:
            val = _as_nonneg_int(payload[key])
            if val is None:
                return None, f"SAST report invalido: {key} invalido."
            return val, None
    if isinstance(payload.get("violations"), list):
        return len(payload["violations"]), None
    return None, "SAST report incompleto o failed."


def _extract_sast_taint(payload: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    for key in ("sast_taint", "taint_findings", "taint_count", "s_taint"):
        if key in payload and payload[key] is not None:
            val = _as_nonneg_int(payload[key])
            if val is None:
                return None, f"SAST report invalido: {key} invalido."
            return val, None
    return 0, None


def _format_sast_result(count_val: int, taint_val: int) -> Dict[str, Any]:
    ok = count_val == 0 and taint_val == 0
    viols = ([f"SAST critici rilevati: {count_val}"] if count_val > 0 else []) + ([f"SAST taint rilevati: {taint_val}"] if taint_val > 0 else [])
    return {"passed": ok, "skipped": False, "sast_critical": count_val, "sast_taint": taint_val, "high_findings": 0 if ok else 1, "violations": viols}


def _evaluate_sast_dict_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    bad_status, status_val = _has_invalid_status(payload, ("PASS", "OK", "CLEAN"))
    if bad_status or payload.get("dry_run") is True or payload.get("is_dry_run") is True:
        return {"passed": False, "skipped": False, "sast_critical": 1, "sast_taint": 0, "high_findings": 1, "violations": [f"SAST report invalido: status={status_val or 'DRY_RUN'}."]}
    count_val, count_err = _extract_sast_count(payload)
    taint_val, taint_err = _extract_sast_taint(payload)
    err_msg = count_err or taint_err
    if err_msg or count_val is None or taint_val is None or payload.get("passed") is False:
        return {"passed": False, "skipped": False, "sast_critical": 1, "sast_taint": taint_val or 0, "high_findings": 1, "violations": [err_msg or "SAST report incompleto o failed."]}
    return _format_sast_result(count_val, taint_val)


def audit_sast_report_payload(sast_report: Optional[Any]) -> Dict[str, Any]:
    """Valuta fail-closed un report SAST JSON rifiutando None, NaN e campi mancanti."""
    payload, early = _load_json_report_dict(sast_report, "SAST")
    if early is not None or payload is None:
        return early or {"passed": False, "skipped": False, "sast_critical": 1, "sast_taint": 0, "high_findings": 1, "violations": ["SAST report assente."]}
    return _evaluate_sast_dict_payload(payload)


def _cov_metric_ok(key: str, val: Any) -> bool:
    if key == "duration_s":
        return _is_valid_num(val) and float(val) >= 0.0
    return _pct_in_range(val)


def _has_injected_fail_flags(rep: Dict[str, Any]) -> bool:
    bad_flags = (("passed", False), ("success", False), ("timed_out", True), ("memory_exceeded", True), ("dry_run", True), ("is_dry_run", True))
    return any(rep.get(k) is v for k, v in bad_flags) or not _exit_code_ok(rep, allow_none=True)


def _all_cov_metrics_valid(test_report: Dict[str, Any]) -> bool:
    for k in _BENCH_COV_KEYS:
        if k in test_report and test_report[k] is not None and not _cov_metric_ok(k, test_report[k]):
            return False
    return True


def parse_injected_counts_ext(test_report: Dict[str, Any]) -> Tuple[bool, str, Optional[Tuple[int, int, int, int, int]]]:
    """Estrae e valida (passed, failed, skipped, xfailed, deselected) da test_report iniettato."""
    if _has_injected_fail_flags(test_report):
        return False, "FAILED_OR_TIMED_OUT_OR_EXITCODE", None
    bad_status, status_val = _has_invalid_status(test_report, ("PASS", "OK", "CERTIFIED_PASS", "STATIC_PASS"))
    raw_vals = (
        test_report.get("tests_passed", test_report.get("passed_count", 0)),
        test_report.get("tests_failed", test_report.get("failed_count", 0)),
        test_report.get("tests_skipped", test_report.get("skipped_count", 0)),
        test_report.get("xfailed_count", test_report.get("xfailed", 0)),
        test_report.get("deselected_count", test_report.get("deselected", 0)),
    )
    parsed = tuple(_as_nonneg_int(v) for v in raw_vals)
    if bad_status or not _all_cov_metrics_valid(test_report) or any(v is None for v in parsed):
        return False, status_val or "INVALID_NUMERIC_OR_NONE", None
    return True, "", parsed  # type: ignore[return-value]


def injected_check_passed_ext(counts: Tuple[int, int, int, int, int], raw_total: Any) -> Tuple[bool, int]:
    """Calcola b_total sanitizzato e verifica zero fail/skip/xfail/deselected e b_passed == b_total."""
    b_passed, b_failed, b_skipped, b_xfailed, b_desel = counts
    b_total = _as_nonneg_int(raw_total)
    b_total_i = -1 if b_total is None else b_total
    rep_ok = b_failed == 0 and b_skipped == 0 and b_xfailed == 0 and b_desel == 0 and b_passed > 0 and b_total_i > 0 and b_passed == b_total_i
    return rep_ok, max(0, b_total_i)


def _pct_in_range(val: Any) -> bool:
    return _is_valid_num(val) and 0.0 <= float(val) <= 100.0


def audit_coverage_report_payload(coverage_report: Optional[Any]) -> Dict[str, Any]:
    """Valuta fail-closed un report copertura rifiutando NaN/Inf, fuori scala o status=''."""
    payload, early = _load_json_report_dict(coverage_report, "Coverage")
    if early is not None or payload is None:
        return early or {"passed": False, "skipped": False, "high_findings": 1, "violations": ["Coverage report assente."]}
    bad_status, status_val = _has_invalid_status(payload, ("PASS", "OK"))
    if bad_status:
        return {"passed": False, "skipped": False, "high_findings": 1, "violations": [f"Coverage report status invalido: {status_val}."]}
    branch_val = payload.get("true_branch_coverage_pct", payload.get("branch_coverage_pct"))
    stmt_val, comb_val = payload.get("statement_coverage_pct"), payload.get("combined_coverage_pct")
    if not _pct_in_range(branch_val) or (stmt_val is None and comb_val is None):
        return {"passed": False, "skipped": False, "high_findings": 1, "violations": ["Coverage report incompleto, NaN o fuori scala 0..100."]}
    if ("statement_coverage_pct" in payload and not _pct_in_range(stmt_val)) or ("combined_coverage_pct" in payload and not _pct_in_range(comb_val)):
        return {"passed": False, "skipped": False, "high_findings": 1, "violations": ["Coverage report contiene metriche None, NaN o fuori scala."]}
    ok = payload.get("passed") is not False
    return {"passed": ok, "skipped": False, "true_branch_coverage_pct": float(branch_val), "high_findings": 0 if ok else 1, "violations": [] if ok else ["Coverage gate fallito."]}


def _inspect_nested_holdout(hv: Any) -> Tuple[int, bool]:
    if not isinstance(hv, dict):
        return 1, True
    for key in ("f_holdout", "holdout_failed", "holdout_failures", "deception_gaming_count", "unresolved_count"):
        if hv.get(key) is None:
            continue
        parsed = _as_nonneg_int(hv[key])
        if parsed is None or parsed > 0:
            return (1 if parsed is None else parsed), True
    hv_status = str(hv.get("status", "")).strip().upper()
    if hv.get("passed") is False or hv_status in ("FAIL", "ERROR", "HALT", "TAMPERED"):
        return 1, True
    return 0, False


def _extract_dast_holdout(payload: Dict[str, Any]) -> Tuple[int, bool]:
    if payload.get("holdout_passed") is False:
        return 1, True
    for key in ("f_holdout", "holdout_failed", "holdout_failures"):
        if payload.get(key) is not None:
            parsed = _as_nonneg_int(payload[key])
            return (1, True) if parsed is None else (parsed, parsed > 0)
    if payload.get("holdout_verification") is not None:
        return _inspect_nested_holdout(payload["holdout_verification"])
    return 0, False


def _has_dast_blockers(payload: Dict[str, Any], status_up: str) -> bool:
    for k in ("timed_out", "memory_exceeded"):
        if k in payload and payload.get(k) in (True, None):
            return True
    if payload.get("is_dry_run") is True or payload.get("dry_run") is True or status_up == "DRY_RUN":
        return True
    if "status" in payload and (payload.get("status") is None or status_up != "PASS"):
        return True
    return payload.get("passed") is False


def _dast_report_passed(payload: Dict[str, Any], status_up: str) -> bool:
    if _has_dast_blockers(payload, status_up):
        return False
    _, holdout_failed = _extract_dast_holdout(payload)
    if holdout_failed:
        return False
    if payload.get("passed") is True and payload.get("success") is not False:
        return "status" in payload and status_up == "PASS" and _exit_code_ok(payload, allow_none=True)
    return (
        payload.get("success") is True
        and _exit_code_ok(payload, allow_none=False)
        and payload.get("timed_out") is False
        and payload.get("memory_exceeded") is False
    )


def _dast_fail_detail(payload: Dict[str, Any], status_up: str) -> str:
    if "status" in payload and (payload.get("status") is None or not str(payload.get("status", "")).strip()):
        return "EMPTY_OR_NONE_STATUS"
    for flag_key, reason in _DAST_FAIL_FLAG_REASONS:
        if payload.get(flag_key) is True:
            return reason
    _, holdout_failed = _extract_dast_holdout(payload)
    if holdout_failed:
        return "HOLDOUT_FAILED"
    if status_up and status_up != "PASS":
        return status_up
    return f"exit_code={payload.get('exit_code')}" if "exit_code" in payload else "MISSING_PASS_EVIDENCE"


def audit_dast_report_payload(dast_report: Optional[Any]) -> Dict[str, Any]:
    """Valuta un report JSON o dict prodotto da dast_sandbox_runner (zero falso green)."""
    payload, early = _load_json_report_dict(dast_report, "DAST")
    if early is not None or payload is None:
        return early or {"passed": False, "skipped": False, "f_holdout": 0, "high_findings": 1, "violations": ["DAST report assente."]}
    raw_status = payload.get("status", "")
    status_up = "" if raw_status is None else str(raw_status).strip().upper()
    f_holdout, _ = _extract_dast_holdout(payload)
    if _dast_report_passed(payload, status_up):
        return {"passed": True, "skipped": False, "f_holdout": f_holdout, "high_findings": 0, "violations": []}
    return {"passed": False, "skipped": False, "f_holdout": f_holdout, "high_findings": 1, "violations": [f"DAST report fallito o incompleto: status={_dast_fail_detail(payload, status_up)}."]}

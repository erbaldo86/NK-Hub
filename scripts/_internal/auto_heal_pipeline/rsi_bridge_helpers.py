# -*- coding: utf-8 -*-
"""Helper RSI, baseline e telemetria isolata per AutoHealPipeline."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Tuple

import _internal.auto_heal_pipeline.models_and_slice as _ms
from _internal.auto_heal_pipeline.models_and_slice import (
    OchiaiBridgeLocation,
    _ensure_ast_guard_loaded,
    _ensure_rsi_loaded,
    _facade_attr,
)
from _internal.nk_common.lane_paths import strip_staging_rel_parts, validate_lane_id
from _internal.nk_common.win32_mutex import repo_path_hash12

_FRONTEND_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".css")
_SEMANTIC_VIOLATION_TYPES = ("SIGNATURE_MUTATION", "UNAUTHORIZED_DELETION", "TYPE_MISMATCH")


def _resolve_prod_baseline_code(target_path: Path) -> str:
    """Restituisce il codice sorgente di produzione come baseline (supporta .staging/lanes/<id>/)."""
    try:
        resolved = target_path.resolve()
    except OSError:
        resolved = target_path
    parts = list(resolved.parts)
    idx, rel_parts, _lane = strip_staging_rel_parts(parts)
    if idx >= 0:
        if rel_parts:
            prod_cand = Path(*parts[:idx]).joinpath(*rel_parts) if idx > 0 else Path(*rel_parts)
            if prod_cand.exists() and prod_cand.is_file() and prod_cand != resolved:
                return prod_cand.read_bytes().decode("utf-8", errors="replace")
        return ""
    return target_path.read_bytes().decode("utf-8", errors="replace") if target_path.exists() else ""


def _scoped_or_temp_telemetry_path(
    cwd: Path, lane_id: Optional[str], stage_dir: Optional[Path],
) -> Path:
    if lane_id is not None or stage_dir is not None:
        tag = validate_lane_id(lane_id) if (lane_id is not None and str(lane_id).strip()) else Path(stage_dir or "stg").name
        return Path(tempfile.gettempdir()) / "nk_auto_heal_telemetry" / f"{repo_path_hash12(cwd)}_{tag}" / "rsi_telemetry.jsonl"
    try:
        temp_root = Path(tempfile.gettempdir()).resolve()
        if cwd.resolve().is_relative_to(temp_root):
            return cwd / "nk_tracking" / "rsi_telemetry.jsonl"
    except OSError as exc:
        _ = str(exc)
    return Path(tempfile.gettempdir()) / "nk_auto_heal_telemetry" / "rsi_telemetry.jsonl"


def _resolve_telemetry_target(
    cwd: Path, *, lane_id: Optional[str] = None, stage_dir: Optional[Path] = None,
) -> Path:
    """Confina telemetria AutoHeal in NVMe temp quando scoped a lane/stage_dir (preserva legacy 1-arg)."""
    if lane_id is None and stage_dir is None and (stg_dir := cwd / ".staging").exists():
        return stg_dir / "nk_tracking" / "rsi_telemetry.jsonl"
    return _scoped_or_temp_telemetry_path(cwd, lane_id, stage_dir)


def _is_minor_guard_regression(item: Any, post_metrics: dict[str, dict[str, Any]]) -> bool:
    if str(getattr(item, "rule_id", "")) not in ("QD-CC-REGRESSION", "QD-NESTING-REGRESSION"):
        return False
    fn_m = post_metrics.get(str(getattr(item, "symbol_name", "") or ""))
    return isinstance(fn_m, dict) and int(fn_m.get("cc", 99)) <= 15 and int(fn_m.get("nesting", 99)) <= 4


def _classify_qd_violations(
    violations: Sequence[Any], post_metrics: Optional[dict[str, dict[str, Any]]] = None,
) -> Tuple[int, int, int, int]:
    high_cnt, med_cnt, low_cnt, sem_cnt = 0, 0, 0, 0
    metrics_map = post_metrics or {}
    for item in violations:
        if _is_minor_guard_regression(item, metrics_map):
            continue
        rid = str(getattr(item, "rule_id", ""))
        sev = str(getattr(item, "severity", "MEDIUM")).upper()
        if rid == "QD-SCOPE-CREEP":
            sem_cnt += 1
        elif sev == "HIGH":
            high_cnt += 1
        elif sev == "MEDIUM":
            med_cnt += 1
        else:
            low_cnt += 1
    return high_cnt, med_cnt, low_cnt, sem_cnt


def _collect_quality_findings(target_path: Path, pre_code: str, post_code: str) -> Tuple[int, int, int, int]:
    ext = target_path.suffix.lower()
    if ext == ".py":
        try:
            import ast as _ast
            from _internal.ast_guard_validator.quality_diff_checker import check_python_quality_diff
            from _internal.ast_guard_validator.quality_diff_rules import extract_function_metrics

            viols = check_python_quality_diff(pre_code, post_code, target_file=target_path.as_posix())
            post_metrics: dict[str, dict[str, Any]] = {}
            if viols:
                try:
                    post_metrics = extract_function_metrics(_ast.parse(post_code, type_comments=True))
                except (SyntaxError, ValueError):
                    post_metrics = {}
            return _classify_qd_violations(viols, post_metrics=post_metrics)
        except ImportError as exc:
            sys.stderr.write(f"[auto_heal_pipeline] quality_diff import error: {exc}\n")
            return 1, 0, 0, 0
    if ext in _FRONTEND_SUFFIXES:
        try:
            from _internal.ast_guard_validator.frontend_static_checker import scan_frontend_code

            viols = scan_frontend_code(post_code, target_path.as_posix(), pre_code=pre_code or None)
            return _classify_qd_violations(viols)
        except ImportError as exc:
            sys.stderr.write(f"[auto_heal_pipeline] frontend_checker import error: {exc}\n")
            return 1, 0, 0, 0
    return 0, 0, 0, 0


def _collect_single_pass_ast_findings(target_path: Path, pre_code: str) -> Tuple[int, int, int, int, int, int]:
    if not target_path.exists():
        return 0, 0, 0, 0, 0, 0
    _ensure_ast_guard_loaded()
    guard_cls = _facade_attr("ASTGuardValidator", _ms.ASTGuardValidator)
    if guard_cls is None or guard_cls is _ms._UNSET:
        sys.stderr.write("[auto_heal_pipeline] ASTGuardValidator unavailable (fail-closed)\n")
        return 0, 1, 1, 0, 0, 0
    try:
        post_code = target_path.read_bytes().decode("utf-8", errors="replace")
        rep = guard_cls.validate_code_edit(pre_code, post_code, target_file=target_path.as_posix())
        total_viols = len(rep.violations) if not rep.is_valid else 0
        metrics = getattr(rep, "metrics", None)
        sast_in_v = sum(1 for v in rep.violations if str(getattr(getattr(v, "violation_type", None), "value", "")) in ("SAST_VIOLATION", "SYNTAX_ERROR"))
        metrics_sast = int(metrics["sast_violations_count"]) if isinstance(metrics, dict) and "sast_violations_count" in metrics else 0
        sast_crit = max(metrics_sast, sast_in_v)
        ast_sem_drift = sum(1 for v in rep.violations if str(getattr(getattr(v, "violation_type", None), "value", "")) in _SEMANTIC_VIOLATION_TYPES)
        contract_viol = max(0, total_viols - sast_crit - ast_sem_drift)
        high_c, med_c, low_c, qd_sem = _collect_quality_findings(target_path, pre_code, post_code)
        return sast_crit, contract_viol, high_c, med_c, low_c, ast_sem_drift + qd_sem
    except Exception as exc:
        sys.stderr.write(f"[auto_heal_pipeline] ast_guard error (fail-closed): {exc}\n")
        return 0, 1, 1, 0, 0, 0


def _build_defect_vector(target_path: Optional[Path], pre_code: str, passed: int, failed: int) -> Any:
    _ensure_rsi_loaded()
    vec_cls = _facade_attr("RSIDefectVector", _ms.RSIDefectVector)
    if vec_cls is None or vec_cls is _ms._UNSET:
        return None
    sast_crit, contract_viol, high_c, med_c, low_c, sem_drift = _collect_single_pass_ast_findings(target_path, pre_code) if target_path is not None else (0, 0, 0, 0, 0, 0)
    return vec_cls(
        sast_critical=sast_crit, tests_passed=max(0, passed), tests_failed=max(0, failed),
        tests_total=max(1, passed + failed), contract_violations=contract_viol,
        high_findings=high_c, medium_findings=med_c, low_findings=low_c, semantic_drift_findings=sem_drift,
    )


def _compute_rsi_metrics_with_vector(passed: int, failed: int, target_path: Optional[Path] = None, pre_code: str = "") -> Tuple[int, float, Any]:
    _ensure_rsi_loaded()
    vec_cls = _facade_attr("RSIDefectVector", _ms.RSIDefectVector)
    cd_fn = _facade_attr("compute_delta", _ms.compute_delta)
    cf_fn = _facade_attr("compute_fitness", _ms.compute_fitness)
    if vec_cls is not None and vec_cls is not _ms._UNSET and cd_fn is not None and cd_fn is not _ms._UNSET and cf_fn is not None and cf_fn is not _ms._UNSET:
        vec = _build_defect_vector(target_path, pre_code, passed, failed)
        d_k = cd_fn(vec)
        return d_k, cf_fn(vec, delta_k=d_k), vec
    d_k = 10 * max(0, failed)
    total = max(1, passed + failed)
    return d_k, round(60.0 * (passed / total) + (40.0 / (1.0 + d_k / 25.0)), 4), None


def _compute_rsi_metrics(passed: int, failed: int, target_path: Optional[Path] = None, pre_code: str = "") -> tuple[int, float]:
    d_k, q_k, _ = _compute_rsi_metrics_with_vector(passed, failed, target_path, pre_code)
    return d_k, q_k


def _format_patch_note(latest_loc: Optional[OchiaiBridgeLocation], cycle: int) -> str:
    if not latest_loc:
        return ""
    return f"- **[AUTO-HEALED]** `{latest_loc.error_type}` in `{Path(latest_loc.file_path).name}:{latest_loc.line_number}` (Cycles: {cycle}, Ochiai: {round(latest_loc.suspiciousness, 3)})"


HypothesisKey = Tuple[str, int, str]


def _hypothesis_key(loc: Optional[OchiaiBridgeLocation], fallback_file: Path) -> HypothesisKey:
    if loc is not None:
        return (str(loc.file_path).replace("\\", "/"), int(loc.line_number), str(loc.error_type or "Unknown"))
    return (fallback_file.as_posix(), 0, "Unknown")


def _cleanup_session_snapshots(snapshot_mgr: Any, *snapshot_ids: Optional[str]) -> None:
    seen: set[str] = set()
    for sid in snapshot_ids:
        if sid and sid not in seen:
            seen.add(sid)
            snapshot_mgr.cleanup(snapshot_id=sid)


def _update_strike_state(last_hyp: Optional[HypothesisKey], strikes: int, attempt_hyp: HypothesisKey) -> Tuple[HypothesisKey, int]:
    return (attempt_hyp, strikes + 1) if last_hyp == attempt_hyp else (attempt_hyp, 1)


def _resolve_iteration_metrics(target_path: Path, pre_code: str, passed: int, failed: int, precomputed: Optional[Tuple[int, float, Any]]) -> Tuple[int, float, Any]:
    d_k, q_k, vec = precomputed if precomputed is not None else _compute_rsi_metrics_with_vector(passed, failed, target_path, pre_code)
    if vec is None:
        vec = _build_defect_vector(target_path, pre_code, passed, failed)
    return d_k, q_k, vec


def _build_exhausted_message(rb_ok: bool, escalation_required: bool, hypothesis: Optional[HypothesisKey]) -> str:
    if escalation_required and hypothesis is not None:
        prefix = f"Circuit breaker 2-Strike tripped on {hypothesis[0]}:{hypothesis[1]} ({hypothesis[2]})."
        return f"{prefix} Rollback to original state completed." if rb_ok else f"{prefix} Rollback integrity verification failed."
    return "Exhausted maximum healing cycles. Rollback to original state completed." if rb_ok else "Exhausted maximum healing cycles. Rollback integrity verification failed."


def _invoke_repair_cb(repair_callback: Optional[Callable[[OchiaiBridgeLocation, int], bool]], latest_loc: Optional[OchiaiBridgeLocation], cycle: int) -> None:
    if not repair_callback or not latest_loc:
        return
    try:
        repair_callback(latest_loc, cycle)
    except Exception as exc:
        sys.stderr.write(f"[auto_heal_pipeline] repair_callback warning: {exc}\n")

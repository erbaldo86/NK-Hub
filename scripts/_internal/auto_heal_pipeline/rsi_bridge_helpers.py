# -*- coding: utf-8 -*-
"""Helper RSI, baseline e telemetria per AutoHealPipeline."""

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

_FRONTEND_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".css")
_SEMANTIC_VIOLATION_TYPES = ("SIGNATURE_MUTATION", "UNAUTHORIZED_DELETION", "TYPE_MISMATCH")


def _resolve_prod_baseline_code(target_path: Path) -> str:
    """Restituisce il codice sorgente di produzione come baseline quando il target e in .staging/."""
    try:
        resolved = target_path.resolve()
    except OSError:
        resolved = target_path
    parts = list(resolved.parts)
    if ".staging" in parts:
        idx = parts.index(".staging")
        rel_parts = parts[idx + 1 :]
        if rel_parts:
            prod_cand = Path(*parts[:idx]).joinpath(*rel_parts) if idx > 0 else Path(*rel_parts)
            if prod_cand.exists() and prod_cand.is_file() and prod_cand != resolved:
                return prod_cand.read_bytes().decode("utf-8", errors="replace")
        return ""
    return target_path.read_bytes().decode("utf-8", errors="replace") if target_path.exists() else ""


def _resolve_telemetry_target(cwd: Path) -> Path:
    """Confina il file rsi_telemetry.jsonl in .staging/nk_tracking oppure in tempdir."""
    stg_dir = cwd / ".staging"
    if stg_dir.exists():
        return stg_dir / "nk_tracking" / "rsi_telemetry.jsonl"
    try:
        temp_root = Path(tempfile.gettempdir()).resolve()
        if cwd.resolve().is_relative_to(temp_root):
            return cwd / "nk_tracking" / "rsi_telemetry.jsonl"
    except OSError as exc:
        _ = str(exc)
    return Path(tempfile.gettempdir()) / "nk_auto_heal_telemetry" / "rsi_telemetry.jsonl"


def _is_minor_guard_regression(item: Any, post_metrics: dict[str, dict[str, Any]]) -> bool:
    """Consente piccoli guardiani difensivi (CC <= 15, nesting <= 4) durante bugfix AutoHeal."""
    if str(getattr(item, "rule_id", "")) not in ("QD-CC-REGRESSION", "QD-NESTING-REGRESSION"):
        return False
    fn_m = post_metrics.get(str(getattr(item, "symbol_name", "") or ""))
    return isinstance(fn_m, dict) and int(fn_m.get("cc", 99)) <= 15 and int(fn_m.get("nesting", 99)) <= 4


def _classify_qd_violations(
    violations: Sequence[Any], post_metrics: Optional[dict[str, dict[str, Any]]] = None,
) -> Tuple[int, int, int, int]:
    """Classifica le violazioni QualityDiff/Frontend in (high, medium, low, semantic_drift)."""
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
    """Esegue il controllo differenziale Quality-Diff o Frontend senza doppio scan AST."""
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
    """Esegue un solo passaggio ASTGuard + QualityDiff evitando doppio conteggio SAST (H3)."""
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
        sast_in_v = sum(
            1 for v in rep.violations
            if str(getattr(getattr(v, "violation_type", None), "value", "")) in ("SAST_VIOLATION", "SYNTAX_ERROR")
        )
        metrics_sast = (
            int(metrics["sast_violations_count"])
            if isinstance(metrics, dict) and "sast_violations_count" in metrics
            else 0
        )
        sast_crit = max(metrics_sast, sast_in_v)
        ast_sem_drift = sum(
            1 for v in rep.violations
            if str(getattr(getattr(v, "violation_type", None), "value", "")) in _SEMANTIC_VIOLATION_TYPES
        )
        contract_viol = max(0, total_viols - sast_crit - ast_sem_drift)
        high_c, med_c, low_c, qd_sem = _collect_quality_findings(target_path, pre_code, post_code)
        return sast_crit, contract_viol, high_c, med_c, low_c, ast_sem_drift + qd_sem
    except Exception as exc:
        sys.stderr.write(f"[auto_heal_pipeline] ast_guard error (fail-closed): {exc}\n")
        return 0, 1, 1, 0, 0, 0


def _build_defect_vector(target_path: Optional[Path], pre_code: str, passed: int, failed: int) -> Any:
    """Costruisce RSIDefectVector in singolo passaggio combinando Pytest, AST/SAST e Quality-Diff."""
    _ensure_rsi_loaded()
    vec_cls = _facade_attr("RSIDefectVector", _ms.RSIDefectVector)
    if vec_cls is None or vec_cls is _ms._UNSET:
        return None
    sast_crit, contract_viol, high_c, med_c, low_c, sem_drift = (
        _collect_single_pass_ast_findings(target_path, pre_code)
        if target_path is not None
        else (0, 0, 0, 0, 0, 0)
    )
    return vec_cls(
        sast_critical=sast_crit, tests_passed=max(0, passed), tests_failed=max(0, failed),
        tests_total=max(1, passed + failed), contract_violations=contract_viol,
        high_findings=high_c, medium_findings=med_c, low_findings=low_c, semantic_drift_findings=sem_drift,
    )


def _compute_rsi_metrics_with_vector(
    passed: int, failed: int, target_path: Optional[Path] = None, pre_code: str = "",
) -> Tuple[int, float, Any]:
    """Calcola (Delta_k, Q(S_k), RSIDefectVector) con una sola scansione AST/SAST."""
    _ensure_rsi_loaded()
    vec_cls = _facade_attr("RSIDefectVector", _ms.RSIDefectVector)
    cd_fn = _facade_attr("compute_delta", _ms.compute_delta)
    cf_fn = _facade_attr("compute_fitness", _ms.compute_fitness)
    if (
        vec_cls is not None and vec_cls is not _ms._UNSET
        and cd_fn is not None and cd_fn is not _ms._UNSET
        and cf_fn is not None and cf_fn is not _ms._UNSET
    ):
        vec = _build_defect_vector(target_path, pre_code, passed, failed)
        d_k = cd_fn(vec)
        return d_k, cf_fn(vec, delta_k=d_k), vec
    d_k = 10 * max(0, failed)
    total = max(1, passed + failed)
    return d_k, round(60.0 * (passed / total) + (40.0 / (1.0 + d_k / 25.0)), 4), None


def _compute_rsi_metrics(passed: int, failed: int, target_path: Optional[Path] = None, pre_code: str = "") -> tuple[int, float]:
    """Calcola Delta_k e Q(S_k) usando il motore RSI oppure la formula analitica."""
    d_k, q_k, _ = _compute_rsi_metrics_with_vector(passed, failed, target_path, pre_code)
    return d_k, q_k


def _format_patch_note(latest_loc: Optional[OchiaiBridgeLocation], cycle: int) -> str:
    """Formatta la riga PATCH_NOTE al completamento della riparazione."""
    if not latest_loc:
        return ""
    return (
        f"- **[AUTO-HEALED]** `{latest_loc.error_type}` in "
        f"`{Path(latest_loc.file_path).name}:{latest_loc.line_number}` "
        f"(Cycles: {cycle}, Ochiai: {round(latest_loc.suspiciousness, 3)})"
    )


HypothesisKey = Tuple[str, int, str]


def _hypothesis_key(loc: Optional[OchiaiBridgeLocation], fallback_file: Path) -> HypothesisKey:
    """Normalizza l'ipotesi di guasto corrente come tupla (file, line, error_type)."""
    if loc is not None:
        return (str(loc.file_path).replace("\\", "/"), int(loc.line_number), str(loc.error_type or "Unknown"))
    return (fallback_file.as_posix(), 0, "Unknown")


def _cleanup_session_snapshots(snapshot_mgr: Any, *snapshot_ids: Optional[str]) -> None:
    """Rimuove selettivamente solo gli snapshot di questa sessione senza toccare altri processi."""
    seen: set[str] = set()
    for sid in snapshot_ids:
        if sid and sid not in seen:
            seen.add(sid)
            snapshot_mgr.cleanup(snapshot_id=sid)


def _update_strike_state(
    last_hyp: Optional[HypothesisKey], strikes: int, attempt_hyp: HypothesisKey,
) -> Tuple[HypothesisKey, int]:
    """Aggiorna il contatore dei fallimenti consecutivi sulla stessa ipotesi (2-Strike)."""
    return (attempt_hyp, strikes + 1) if last_hyp == attempt_hyp else (attempt_hyp, 1)


def _resolve_iteration_metrics(
    target_path: Path, pre_code: str, passed: int, failed: int, precomputed: Optional[Tuple[int, float, Any]],
) -> Tuple[int, float, Any]:
    """Restituisce (delta_k, fitness_q, defect_vector) evitando ricalcoli duplicati."""
    d_k, q_k, vec = precomputed if precomputed is not None else _compute_rsi_metrics_with_vector(passed, failed, target_path, pre_code)
    if vec is None:
        vec = _build_defect_vector(target_path, pre_code, passed, failed)
    return d_k, q_k, vec


def _build_exhausted_message(rb_ok: bool, escalation_required: bool, hypothesis: Optional[HypothesisKey]) -> str:
    """Costruisce il messaggio diagnostico di chiusura dopo rollback iniziale."""
    if escalation_required and hypothesis is not None:
        prefix = f"Circuit breaker 2-Strike tripped on {hypothesis[0]}:{hypothesis[1]} ({hypothesis[2]})."
        return f"{prefix} Rollback to original state completed." if rb_ok else f"{prefix} Rollback integrity verification failed."
    return "Exhausted maximum healing cycles. Rollback to original state completed." if rb_ok else "Exhausted maximum healing cycles. Rollback integrity verification failed."


def _invoke_repair_cb(repair_callback: Optional[Callable[[OchiaiBridgeLocation, int], bool]], latest_loc: Optional[OchiaiBridgeLocation], cycle: int) -> None:
    """Esegue repair_callback in sicurezza registrando eventuali eccezioni su stderr."""
    if not repair_callback or not latest_loc:
        return
    try:
        repair_callback(latest_loc, cycle)
    except Exception as exc:
        sys.stderr.write(f"[auto_heal_pipeline] repair_callback warning: {exc}\n")

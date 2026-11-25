# -*- coding: utf-8 -*-
"""Helper single-pass read-only (--diagnose-slice) per auto_heal_pipeline."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from _internal.auto_heal_pipeline.models_and_slice import (
    CodeSlice,
    DiagnoseSliceReport,
    KarpathySlicer,
    OchiaiBridgeLocation,
    classify_failure,
    normalize_test_command,
    trim_code_slice_tokens,
)


def _resolve_target_path(cwd: Path, target_file: Path | str) -> Path:
    """Risolve il percorso del file target evitando doppi prefissi rispetto a cwd."""
    cand = Path(target_file)
    if cand.is_absolute():
        return cand
    cwd_cand = cwd / cand
    if cwd_cand.exists():
        return cwd_cand
    if cand.exists():
        return cand.resolve()
    return cwd_cand


def _invoke_bridge_diagnose(
    bridge: Any,
    test_cmd: Any,
    target_file_hint: str,
    *,
    collect_pass_coverage: bool = False,
) -> Tuple[Any, Optional[OchiaiBridgeLocation]]:
    """Invoca bridge.run_and_diagnose preservando la compatibilita coi parametri."""
    run_fn = bridge.run_and_diagnose
    kwargs: Dict[str, Any] = {
        "test_cmd": test_cmd,
        "target_file_hint": target_file_hint,
    }
    try:
        params = inspect.signature(run_fn).parameters
        if collect_pass_coverage and "collect_pass_coverage" in params:
            kwargs["collect_pass_coverage"] = True
    except (TypeError, ValueError):
        return run_fn(**kwargs)
    return run_fn(**kwargs)


def _build_trimmed_slice(
    cwd: Path,
    target_path: Path,
    loc: Optional[OchiaiBridgeLocation],
    max_slice_tokens: int,
) -> Tuple[Optional[CodeSlice], int]:
    """Isola e limita a max_slice_tokens il contesto AST attorno alla riga sospetta."""
    if loc is None:
        return None, 0
    slice_path = target_path
    loc_cand = Path(loc.file_path)
    if loc_cand.name != target_path.name:
        cwd_cand = cwd / loc.file_path
        if cwd_cand.exists() and cwd_cand.is_file():
            slice_path = cwd_cand
    if not slice_path.exists() or not slice_path.is_file():
        return None, 0
    raw_slice = KarpathySlicer.slice_file(slice_path, target_line=loc.line_number, window=4)
    return trim_code_slice_tokens(raw_slice, max_tokens=max_slice_tokens)


def run_diagnose_slice(
    cwd: Path,
    bridge: Any,
    test_cmd: Sequence[str] | str,
    target_file: Path | str,
    resolve_baseline_fn: Any,
    compute_metrics_fn: Any,
    *,
    max_slice_tokens: int = 80,
) -> DiagnoseSliceReport:
    """Esegue diagnosi single-pass in sola lettura con Ochiai n_ep e slice <= 80 token."""
    norm_test_cmd = normalize_test_command(test_cmd)
    target_path = _resolve_target_path(cwd, target_file)
    pre_code = resolve_baseline_fn(target_path)
    summary, loc = _invoke_bridge_diagnose(
        bridge, norm_test_cmd, str(target_file), collect_pass_coverage=True
    )
    d_k, q_k = compute_metrics_fn(
        summary.passed_count, summary.failed_count, target_path, pre_code
    )
    failure_cat = classify_failure(
        summary.raw_stdout, summary.raw_stderr, exit_code=summary.exit_code
    )
    trimmed_slice, tok_cnt = _build_trimmed_slice(
        cwd, target_path, loc, max_slice_tokens
    )
    is_ok = (
        summary.exit_code == 0
        and summary.failed_count == 0
        and summary.passed_count > 0
        and d_k == 0
    )
    msg = (
        "Diagnose slice clean: tests passed with delta_k=0."
        if is_ok
        else f"Diagnose slice detected {failure_cat} (delta_k={d_k}, failed={summary.failed_count})."
    )
    return DiagnoseSliceReport(
        success=is_ok,
        target_file=target_path.as_posix(),
        exit_code=summary.exit_code,
        tests_passed=summary.passed_count,
        tests_failed=summary.failed_count,
        failure_category=failure_cat,
        fault_location=f"{loc.file_path}:{loc.line_number}" if loc else None,
        error_type=loc.error_type if loc else None,
        error_message=loc.error_message if loc else None,
        ochiai_score=loc.suspiciousness if loc else None,
        n_ef=loc.n_ef if loc else 0,
        n_ep=loc.n_ep if loc else 0,
        code_slice_tokens=tok_cnt,
        code_slice=trimmed_slice,
        rsi_delta=d_k,
        rsi_fitness_q=q_k,
        message=msg,
    )

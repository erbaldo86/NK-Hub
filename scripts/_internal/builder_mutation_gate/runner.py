# -*- coding: utf-8 -*-
"""Runner ShadowSandbox su NVMe parallelo con WorkerBudgetSlot e shutdown pulito."""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from _internal.builder_mutation_gate.audit_mode import run_full_module_audit
from _internal.builder_mutation_gate.mutant_gen import (
    MutantSpec,
    find_touched_functions,
    generate_differential_mutants,
    has_executable_python_diff,
)
from _internal.builder_mutation_gate.report_builders import (
    MutantOutcome,
    MutationGateReport,
    _build_baseline_abort_report,
    _build_final_gate_report,
    _build_vacuous_pass_report,
)
from _internal.builder_mutation_gate.target_prep import (
    _check_ads_and_drive,
    _is_explicit_staged_target,
    _normalize_target_rel_path,
    _prepare_target_source,
    _run_pytest_fail_fast,
    _strip_workspace_prefixes,
    get_repo_snapshot_cache,
    safe_subprocess_run,
)
from _internal.dast_sandbox_runner.sandbox_fs import ShadowSandbox
from _internal.dast_sandbox_runner.staging_overlay import prepare_staging_overlay
from _internal.nk_common.lane_paths import resolve_staging_dir
from _internal.nk_common.worker_budget import WorkerBudgetSlot


def _to_mutant_outcome(mut: MutantSpec, rc: int, dur: float) -> MutantOutcome:
    is_timeout = rc in (-1, 124)
    return MutantOutcome(
        mutant_id=mut.mutant_id, operator=mut.operator, function_name=mut.function_name, line_number=mut.line_number,
        killed=(rc == 1), exit_code=rc, timed_out=is_timeout, crashed=(rc not in (0, 1)) and not is_timeout, duration_sec=dur,
    )


def _run_cloned_mutant_nvme(
    base_sb_dir: Path, rel_target: str, mut: MutantSpec, test_targets: Sequence[str], per_mutant_timeout: float,
    cancel_ev: Optional[threading.Event] = None,
) -> MutantOutcome:
    if cancel_ev is not None and cancel_ev.is_set():
        return _to_mutant_outcome(mut, -1, 0.0)
    with tempfile.TemporaryDirectory(prefix="nk_mut_wbt_") as wbt_tmp:
        with ShadowSandbox() as clone_sb:
            shutil.copytree(base_sb_dir, clone_sb.sandbox_dir, dirs_exist_ok=True)
            clone_sb.write_file(rel_target, mut.mutated_source)
            rc, dur = _run_pytest_fail_fast(clone_sb.sandbox_dir, test_targets, Path(wbt_tmp), per_mutant_timeout)
    return _to_mutant_outcome(mut, rc, dur)


def _evaluate_mutants_sequential(
    sb: ShadowSandbox, rel_target: str, post_code: str, mutants: List[MutantSpec],
    test_targets: Sequence[str], bt_dir: Path, t0: float, per_mutant_timeout: float, total_budget_sec: float,
) -> Tuple[List[MutantOutcome], bool]:
    outcomes, budget_exhausted = [], False
    for mut in mutants:
        if (time.perf_counter() - t0) >= total_budget_sec:
            budget_exhausted = True
            break
        sb.write_file(rel_target, mut.mutated_source)
        try:
            rc, dur = _run_pytest_fail_fast(sb.sandbox_dir, test_targets, bt_dir, per_mutant_timeout)
        finally:
            sb.write_file(rel_target, post_code)
        outcomes.append(_to_mutant_outcome(mut, rc, dur))
    return outcomes, budget_exhausted


def _collect_parallel_futures(futs: Sequence[Future[MutantOutcome]], total_budget_sec: float, t0: float) -> Tuple[List[MutantOutcome], bool]:
    outcomes, budget_exhausted = [], False
    for fut in futs:
        if (rem := total_budget_sec - (time.perf_counter() - t0)) <= 0 and not fut.done():
            budget_exhausted = True
            break
        try:
            outcomes.append(fut.result(timeout=max(0.01, rem)))
        except FuturesTimeoutError:
            budget_exhausted = True
            break
    return outcomes, budget_exhausted


def _run_cloned_mutant_with_cancel(
    base_sb_dir: Path, rel_target: str, mut: MutantSpec, test_targets: Sequence[str],
    per_mutant_timeout: float, cancel_ev: threading.Event,
) -> MutantOutcome:
    if cancel_ev.is_set():
        return _to_mutant_outcome(mut, -1, 0.0)
    return _run_cloned_mutant_nvme(base_sb_dir, rel_target, mut, test_targets, per_mutant_timeout)


def _evaluate_mutants_parallel(
    sb: ShadowSandbox, rel_target: str, mutants: List[MutantSpec],
    test_targets: Sequence[str], t0: float, per_mutant_timeout: float, total_budget_sec: float,
) -> Tuple[List[MutantOutcome], bool]:
    futs: List[Future[MutantOutcome]] = []
    outcomes, budget_exhausted = [], False
    cancel_ev = threading.Event()
    slot = WorkerBudgetSlot(requested=min(4, len(mutants))).__enter__()
    ex = ThreadPoolExecutor(max_workers=max(1, slot.workers))
    try:
        for mut in mutants:
            if (time.perf_counter() - t0) >= total_budget_sec:
                budget_exhausted = True
                break
            futs.append(ex.submit(_run_cloned_mutant_with_cancel, sb.sandbox_dir, rel_target, mut, test_targets, per_mutant_timeout, cancel_ev))
        outcomes, fut_budget = _collect_parallel_futures(futs, total_budget_sec, t0)
        budget_exhausted = budget_exhausted or fut_budget
    finally:
        cancel_ev.set()
        for fut in futs:
            fut.cancel()
        ex.shutdown(wait=not budget_exhausted, cancel_futures=True)
        slot.__exit__(None, None, None)
    return outcomes, budget_exhausted


def _evaluate_mutants_in_sandbox(
    sb: ShadowSandbox, rel_target: str, post_code: str, mutants: List[MutantSpec],
    test_targets: Sequence[str], bt_dir: Path, t0: float, per_mutant_timeout: float, total_budget_sec: float,
) -> Tuple[List[MutantOutcome], bool]:
    if (time.perf_counter() - t0) >= total_budget_sec:
        return [], bool(mutants)
    if len(mutants) <= 1:
        return _evaluate_mutants_sequential(sb, rel_target, post_code, mutants, test_targets, bt_dir, t0, per_mutant_timeout, total_budget_sec)
    return _evaluate_mutants_parallel(sb, rel_target, mutants, test_targets, t0, per_mutant_timeout, total_budget_sec)


def _run_sandbox_session(
    ws_root: Path, stg_dir: Path, rel_target: str, post_code: str, mutants: List[MutantSpec],
    test_targets: Sequence[str], per_mutant_timeout: float, total_budget_sec: float,
) -> Tuple[bool, List[MutantOutcome], bool]:
    outcomes, budget_exhausted, baseline_ok = [], False, False
    with tempfile.TemporaryDirectory(prefix="nk_mut_bt_") as bt_tmp:
        bt_dir = Path(bt_tmp)
        with ShadowSandbox() as sb:
            prepare_staging_overlay(ws_root, stg_dir, sb, norm_prof="builder")
            baseline_ok = _run_pytest_fail_fast(sb.sandbox_dir, test_targets, bt_dir, per_mutant_timeout)[0] == 0
            mut_t0 = time.perf_counter()
            if baseline_ok and mutants:
                outcomes, budget_exhausted = _evaluate_mutants_in_sandbox(sb, rel_target, post_code, mutants, test_targets, bt_dir, mut_t0, per_mutant_timeout, total_budget_sec)
    return baseline_ok, outcomes, budget_exhausted


def run_mutation_gate(
    workspace_root: Path | str, target_rel_path: str, test_targets: Sequence[str], *,
    stage_dir: Optional[Path | str] = None, max_mutants: int = 8, min_kill_rate: float = 0.80,
    per_mutant_timeout: float = 15.0, total_budget_sec: float = 30.0, require_staged: bool = False,
    audit_full_module: bool = False, max_audit_mutants: int = 16, audit_workers: int = 4,
    lane_id: Optional[str] = None,
) -> MutationGateReport:
    """Valuta in ShadowSandbox NVMe la sensibilita dei test in modalita fail-closed."""
    t0, ws_root = time.perf_counter(), Path(workspace_root).resolve()
    stg_dir, _norm_lane = resolve_staging_dir(ws_root, lane_id=lane_id, staging_dir=stage_dir) if (lane_id is not None or stage_dir is not None) else ((ws_root / ".staging").resolve(), None)
    if audit_full_module:
        return run_full_module_audit(ws_root, target_rel_path, test_targets, stage_dir=stg_dir, max_audit_mutants=max_audit_mutants, audit_workers=audit_workers, min_kill_rate=min_kill_rate, per_mutant_timeout=per_mutant_timeout, total_budget_sec=total_budget_sec, run_pytest_fn=_run_pytest_fail_fast, lane_id=lane_id)
    rel_target, pre_code, post_code, err_rep = _prepare_target_source(ws_root, stg_dir, target_rel_path, min_kill_rate, t0, require_staged=require_staged)
    if err_rep is not None or rel_target is None or post_code is None:
        return err_rep  # type: ignore[return-value]
    touched = sorted(find_touched_functions(pre_code, post_code))
    mutants = generate_differential_mutants(rel_target, pre_code, post_code, max_mutants=max_mutants)
    baseline_ok, outcomes, budget_exhausted = _run_sandbox_session(ws_root, stg_dir, rel_target, post_code, mutants, test_targets, per_mutant_timeout, total_budget_sec)
    elapsed = round(time.perf_counter() - t0, 4)
    if not baseline_ok:
        return _build_baseline_abort_report(rel_target, touched, len(mutants), min_kill_rate, elapsed)
    if not mutants:
        return _build_vacuous_pass_report(stg_dir, rel_target, touched, min_kill_rate, elapsed, executable_diff=has_executable_python_diff(pre_code, post_code))
    return _build_final_gate_report(rel_target, touched, mutants, outcomes, budget_exhausted, min_kill_rate, elapsed)

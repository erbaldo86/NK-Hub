# -*- coding: utf-8 -*-
"""Motore di audit mutazione full-module e multi-modulo con pool NVMe condiviso."""
from __future__ import annotations

import contextlib, hashlib, itertools, queue, shutil, tempfile, time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple
from _internal.builder_mutation_gate.hotspot_audit import select_hotspot_functions
from _internal.builder_mutation_gate.mutant_gen import MutantSpec, generate_audit_mutants
from _internal.builder_mutation_gate.report_builders import (
    MutantOutcome, MutationGateReport, _build_baseline_abort_report, _build_final_gate_report, _build_vacuous_pass_report,
)
from _internal.builder_mutation_gate.target_prep import _prepare_target_source, _run_pytest_fail_fast
from _internal.dast_sandbox_runner.sandbox_fs import _resolve_confined_sandbox_path
from _internal.nk_common.io import atomic_write_bytes
from _internal.nk_common.isolated_test_runner import mirror_workspace_to_nvme, safe_rmtree

_WorkerSlot = NamedTuple("_WorkerSlot", [("slot_id", int), ("workspace_dir", Path), ("basetemp_dir", Path)])


def _purge_target_pyc(target_path: Path) -> int:
    """Rimuove i file .pyc del target in __pycache__ nello slot."""
    pdir = target_path.parent / "__pycache__"
    cands = [p for p in list(pdir.glob(f"{target_path.stem}.*.pyc")) + [pdir / f"{target_path.stem}.pyc"] if p.is_file()] if pdir.is_dir() else []
    for pyc_f in cands: pyc_f.unlink(missing_ok=True)
    return len(cands)


def _try_restore_once(target_path: Path, orig_bytes: bytes, orig_sha: str) -> Optional[str]:
    ok, err = atomic_write_bytes(target_path, orig_bytes, fsync_data=False)
    if not ok or not target_path.is_file(): return err or "write_failed"
    rest_sha = hashlib.sha256(target_path.read_bytes()).hexdigest()
    return None if rest_sha == orig_sha else f"sha256_mismatch:{rest_sha}!={orig_sha}"


def _restore_slot_target(target_path: Path, orig_bytes: bytes, orig_sha: str, rel_target: str) -> None:
    """Ripristina i byte originali nello slot verificando SHA-256 e purgando i .pyc."""
    last_err = "write_failed"
    try:
        for _ in range(2):
            if (last_err := _try_restore_once(target_path, orig_bytes, orig_sha) or "") == "": return
        raise RuntimeError(f"Slot restore failed for {rel_target}: {last_err}")
    finally:
        _purge_target_pyc(target_path)


def _collect_audit_futures(futs: Sequence[Future[MutantOutcome]], total_budget_sec: float, t0: float) -> Tuple[List[MutantOutcome], bool, Optional[str]]:
    """Raccoglie i risultati delle future rispettando il budget residuo."""
    outcomes, budget_exhausted, err_msg = [], False, None
    for fut in futs:
        if (rem := total_budget_sec - (time.perf_counter() - t0)) <= 0 and not fut.done(): budget_exhausted = True; break
        try: outcomes.append(fut.result(timeout=max(0.01, rem)))
        except FuturesTimeoutError: budget_exhausted = True; break
        except (OSError, RuntimeError, ValueError) as exc: err_msg = str(exc); break
    if budget_exhausted or err_msg is not None:
        for fut in futs: fut.cancel()
    return outcomes, budget_exhausted, err_msg


class SharedBaseNVMeWorkerPool:
    """Pool NVMe persistente con 1 mirror base e 1..4 slot riutilizzabili."""

    def __init__(self, workspace_root: Path | str, *, stage_dir: Optional[Path | str] = None, workers: int = 4) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.stage_dir = Path(stage_dir).resolve() if stage_dir is not None else (self.workspace_root / ".staging").resolve()
        self.workers, self._closed, self._run_seq = max(1, min(int(workers), 4)), False, itertools.count(1)
        self._pending_futures, self._slot_queue = [], queue.Queue()
        self.slots, self._executor, self._base_root, self._slots_root = [], None, None, None
        try:
            self.base_dir = mirror_workspace_to_nvme(self.workspace_root, staging_dir=self.stage_dir, prefix="nk_audit_base_", apply_overlay=True, mirror_siblings=False)
            self._base_root, self._slots_root = self.base_dir.parent, Path(tempfile.mkdtemp(prefix="nk_audit_slots_")).resolve()
            for idx in range(self.workers):
                slot_ws, slot_bt = self._slots_root / f"slot_{idx}" / self.base_dir.name, self._slots_root / f"slot_{idx}" / "basetemp"
                shutil.copytree(self.base_dir, slot_ws, dirs_exist_ok=True); slot_bt.mkdir(parents=True, exist_ok=True)
                self.slots.append(slot := _WorkerSlot(idx, slot_ws, slot_bt)); self._slot_queue.put(slot)
            self._executor = ThreadPoolExecutor(max_workers=self.workers)
        except (OSError, ValueError, RuntimeError):
            self.close(); raise

    def __enter__(self) -> SharedBaseNVMeWorkerPool: return self
    def __exit__(self, *_args: Any) -> None: self.close()

    def close(self) -> None:
        """Cancella future pendenti, chiude il pool e rimuove mirror base e slot."""
        if self._closed: return
        self._closed = True
        for fut in self._pending_futures: fut.cancel()
        self._pending_futures.clear()
        if self._executor is not None: self._executor.shutdown(wait=True, cancel_futures=True); self._executor = None
        for d in (self._slots_root, self._base_root):
            if d is not None: safe_rmtree(d)

    @contextlib.contextmanager
    def _checkout_slot(self, prefix: str) -> Iterator[Tuple[_WorkerSlot, Path]]:
        if self._closed: raise RuntimeError("SharedBaseNVMeWorkerPool is closed")
        slot, run_bt = self._slot_queue.get(), None
        try:
            run_bt = slot.basetemp_dir / f"{prefix}_{next(self._run_seq)}"; run_bt.mkdir(parents=True, exist_ok=True)
            yield slot, run_bt
        finally:
            if run_bt is not None: safe_rmtree(run_bt)
            self._slot_queue.put(slot)

    def run_baseline(self, test_targets: Sequence[str], run_pytest_fn: Callable[..., Tuple[int, float]], timeout_sec: float) -> Tuple[int, float]:
        with self._checkout_slot("base") as (slot, run_bt):
            return run_pytest_fn(slot.workspace_dir, test_targets, run_bt, timeout_sec)

    def run_mutant(self, rel_target: str, mut: MutantSpec, test_targets: Sequence[str], run_pytest_fn: Callable[..., Tuple[int, float]], timeout_sec: float) -> MutantOutcome:
        with self._checkout_slot("mut") as (slot, run_bt):
            target_path = _resolve_confined_sandbox_path(slot.workspace_dir, rel_target)
            orig_bytes = target_path.read_bytes(); orig_sha = hashlib.sha256(orig_bytes).hexdigest()
            try:
                ok, err = atomic_write_bytes(target_path, mut.mutated_source.encode("utf-8"), fsync_data=False)
                if not ok: raise OSError(f"Atomic write failed for {mut.mutant_id}: {err}")
                _purge_target_pyc(target_path)
                rc, dur = run_pytest_fn(slot.workspace_dir, test_targets, run_bt, timeout_sec)
            finally:
                _restore_slot_target(target_path, orig_bytes, orig_sha, rel_target)
            is_to = rc in (-1, 124)
            return MutantOutcome(mutant_id=mut.mutant_id, operator=mut.operator, function_name=mut.function_name, line_number=mut.line_number, killed=(rc == 1), exit_code=rc, timed_out=is_to, crashed=(rc not in (0, 1) and not is_to), duration_sec=dur)

    def evaluate_mutants(self, rel_target: str, mutants: List[MutantSpec], test_targets: Sequence[str], run_pytest_fn: Callable[..., Tuple[int, float]], per_mutant_timeout: float, total_budget_sec: float, t0: float) -> Tuple[List[MutantOutcome], bool, Optional[str]]:
        if self._executor is None or self._closed: return [], bool(mutants), "SharedBaseNVMeWorkerPool is closed"
        futs, early_budget = [], False
        for mut in mutants:
            if (time.perf_counter() - t0) >= total_budget_sec: early_budget = True; break
            futs.append(fut := self._executor.submit(self.run_mutant, rel_target, mut, test_targets, run_pytest_fn, per_mutant_timeout))
            self._pending_futures.append(fut)
        outcomes, fut_budget, err_msg = _collect_audit_futures(futs, total_budget_sec, t0)
        return outcomes, (early_budget or fut_budget), err_msg


def _execute_pool_audit(pool: SharedBaseNVMeWorkerPool, stg_dir: Path, rel_target: str, hotspots: List[str], mutants: List[MutantSpec], test_targets: Sequence[str], pytest_cb: Callable[..., Tuple[int, float]], min_kill_rate: float, per_mutant_timeout: float, total_budget_sec: float, t0: float) -> MutationGateReport:
    if pool.run_baseline(test_targets, pytest_cb, per_mutant_timeout)[0] != 0:
        return _build_baseline_abort_report(rel_target, hotspots, len(mutants), min_kill_rate, round(time.perf_counter() - t0, 4))
    if not mutants:
        return _build_vacuous_pass_report(stg_dir, rel_target, hotspots, min_kill_rate, round(time.perf_counter() - t0, 4), executable_diff=False)
    outcomes, budget_exhausted, err_msg = pool.evaluate_mutants(rel_target, mutants, test_targets, pytest_cb, per_mutant_timeout, total_budget_sec, t0)
    rep = _build_final_gate_report(rel_target, hotspots, mutants, outcomes, budget_exhausted, min_kill_rate, round(time.perf_counter() - t0, 4))
    return rep.model_copy(update={"status": "FAIL", "passed": False, "message": f"Mutation Audit FAIL: {err_msg}"}) if err_msg is not None else rep


def run_full_module_audit(workspace_root: Path | str, target_rel_path: str, test_targets: Sequence[str], *, stage_dir: Optional[Path | str] = None, max_audit_mutants: int = 16, audit_workers: int = 4, min_kill_rate: float = 0.80, per_mutant_timeout: float = 15.0, total_budget_sec: float = 45.0, pool: Optional[SharedBaseNVMeWorkerPool] = None, run_pytest_fn: Optional[Callable[..., Tuple[int, float]]] = None) -> MutationGateReport:
    """Esegue baseline + mutanti hotspot usando un pool NVMe condiviso."""
    t0, ws_root = time.perf_counter(), Path(workspace_root).resolve()
    stg_dir = Path(stage_dir).resolve() if stage_dir is not None else (ws_root / ".staging").resolve()
    rel_target, _pre, post_code, err_rep = _prepare_target_source(ws_root, stg_dir, target_rel_path, min_kill_rate, t0)
    if err_rep is not None or rel_target is None or post_code is None: return err_rep  # type: ignore[return-value]
    hotspots, mutants = select_hotspot_functions(post_code), generate_audit_mutants(rel_target, post_code, max_audit_mutants=max_audit_mutants)
    pytest_cb = run_pytest_fn or _run_pytest_fail_fast
    with (contextlib.nullcontext(pool) if pool is not None else SharedBaseNVMeWorkerPool(ws_root, stage_dir=stg_dir, workers=audit_workers)) as active_pool:
        return _execute_pool_audit(active_pool, stg_dir, rel_target, hotspots, mutants, test_targets, pytest_cb, min_kill_rate, per_mutant_timeout, total_budget_sec, t0)


def _format_multi_module_entry(rep: MutationGateReport, test_tgts: List[str], min_kill_rate: float) -> Dict[str, Any]:
    below = (rep.kill_rate < min_kill_rate) if (rep.mutants_total > 0 or not rep.passed) else False
    survivors = [{"mutant_id": o.mutant_id, "operator": o.operator, "function_name": o.function_name, "line_number": o.line_number} for o in rep.outcomes if not o.killed]
    return {"target_file": rep.target_file, "test_targets": test_tgts, "status": rep.status, "kill_rate": rep.kill_rate, "mutants_killed": rep.mutants_killed, "mutants_total": rep.mutants_total, "mutants_survived": rep.mutants_survived, "elapsed_sec": rep.elapsed_sec, "below_threshold": below, "survivors": survivors}


def _build_multi_module_summary(modules_out: List[Dict[str, Any]], min_kill_rate: float, t0: float) -> Dict[str, Any]:
    below_list = [m["target_file"] for m in modules_out if m["below_threshold"]]
    passed = bool(modules_out) and not below_list and all(m["status"] == "PASS" for m in modules_out)
    return {"status": "PASS" if passed else "FAIL", "passed": passed, "elapsed_sec": round(time.perf_counter() - t0, 4), "min_kill_rate": float(min_kill_rate), "modules_total": len(modules_out), "modules_below_threshold": below_list, "modules": modules_out}


def run_multi_module_audit(workspace_root: Path | str, module_specs: Sequence[Any], *, stage_dir: Optional[Path | str] = None, audit_workers: int = 4, max_audit_mutants: int = 12, min_kill_rate: float = 0.85, per_mutant_timeout: float = 15.0, total_budget_sec: float = 65.0, run_pytest_fn: Optional[Callable[..., Tuple[int, float]]] = None) -> Dict[str, Any]:
    """Esegue l'audit mutazione su piu moduli riutilizzando una sola istanza SharedBaseNVMeWorkerPool."""
    t0, ws_root = time.perf_counter(), Path(workspace_root).resolve()
    stg_dir = Path(stage_dir).resolve() if stage_dir is not None else (ws_root / ".staging").resolve()
    pytest_cb, modules_out = run_pytest_fn or _run_pytest_fail_fast, []
    with SharedBaseNVMeWorkerPool(ws_root, stage_dir=stg_dir, workers=audit_workers) as pool:
        for spec in module_specs:
            rel_t, test_tgts = (str(spec["target_file"]), [str(t) for t in spec.get("test_targets", [])]) if isinstance(spec, dict) else (str(spec[0]), [str(t) for t in spec[1]])
            rep = run_full_module_audit(ws_root, rel_t, test_tgts, stage_dir=stg_dir, max_audit_mutants=max_audit_mutants, audit_workers=audit_workers, min_kill_rate=min_kill_rate, per_mutant_timeout=per_mutant_timeout, total_budget_sec=max(0.0, total_budget_sec - (time.perf_counter() - t0)), pool=pool, run_pytest_fn=pytest_cb)
            modules_out.append(_format_multi_module_entry(rep, test_tgts, min_kill_rate))
    return _build_multi_module_summary(modules_out, min_kill_rate, t0)

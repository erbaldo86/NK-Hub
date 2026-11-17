# -*- coding: utf-8 -*-
"""Orchestratore AutoHealPipeline, calcolo vettore difetti e metriche RSI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import _internal.auto_heal_pipeline.models_and_slice as _ms
from _internal.auto_heal_pipeline.models_and_slice import (
    AutoHealSessionReport,
    OchiaiBridgeLocation,
    _ensure_ast_guard_loaded,
    _ensure_rsi_loaded,
    _ensure_sbfl_bridge_loaded,
    _facade_attr,
    classify_failure,
    normalize_test_command,
)
from _internal.nk_common.paths import reconfigure_streams

try:
    from healing_snapshot_rollback import FitnessVerdict, HealingSnapshotManager
except ImportError:
    from scripts.healing_snapshot_rollback import FitnessVerdict, HealingSnapshotManager


def _build_defect_vector(
    target_path: Optional[Path],
    pre_code: str,
    passed: int,
    failed: int,
) -> Any:
    """Costruisce RSIDefectVector combinando risultati Pytest e controlli AST/SAST."""
    _ensure_rsi_loaded()
    vec_cls = _facade_attr("RSIDefectVector", _ms.RSIDefectVector)
    if vec_cls is None or vec_cls is _ms._UNSET:
        return None
    sast_crit = 0
    contract_viol = 0
    if target_path is not None and target_path.exists():
        _ensure_ast_guard_loaded()
        guard_cls = _facade_attr("ASTGuardValidator", _ms.ASTGuardValidator)
        if guard_cls is not None and guard_cls is not _ms._UNSET:
            try:
                post_code = target_path.read_bytes().decode("utf-8", errors="replace")
                rep = guard_cls.validate_code_edit(
                    pre_code or post_code, post_code, target_file=target_path.name
                )
                if not rep.is_valid:
                    contract_viol = len(rep.violations)
                sast_crit = len(
                    guard_cls.check_sast_constructs(post_code, target_file=target_path.as_posix())
                )
            except Exception:
                pass
    return vec_cls(
        sast_critical=sast_crit,
        tests_passed=max(0, passed),
        tests_failed=max(0, failed),
        tests_total=max(1, passed + failed),
        contract_violations=contract_viol,
    )


def _compute_rsi_metrics(
    passed: int,
    failed: int,
    target_path: Optional[Path] = None,
    pre_code: str = "",
) -> tuple[int, float]:
    """Calcola Delta_k e Q(S_k) usando il motore RSI oppure la formula analitica."""
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
        return d_k, cf_fn(vec, delta_k=d_k)
    d_k = 10 * max(0, failed)
    total = max(1, passed + failed)
    return d_k, round(60.0 * (passed / total) + (40.0 / (1.0 + d_k / 25.0)), 4)


class AutoHealPipeline:
    """Orchestratore end-to-end del ciclo di auto-riparazione."""

    classify_failure = staticmethod(classify_failure)

    def __init__(self, cwd: Optional[Path] = None, max_cycles: int = 3):
        reconfigure_streams()
        _ensure_sbfl_bridge_loaded()
        _ensure_rsi_loaded()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()
        self.max_cycles = max_cycles
        bridge_cls = _facade_attr("SBFLPytestBridge", _ms.SBFLPytestBridge)
        snap_cls = _facade_attr("HealingSnapshotManager", HealingSnapshotManager)
        rsi_cls = _facade_attr("RSIConvergenceEngine", _ms.RSIConvergenceEngine)
        self.bridge = bridge_cls(cwd=self.cwd)
        self.snapshot_mgr = snap_cls()
        telemetry_target = (
            self.cwd / ".staging" / "nk_tracking" / "rsi_telemetry.jsonl"
            if (self.cwd / ".staging" / "nk_tracking").exists()
            else self.cwd / "nk_tracking" / "rsi_telemetry.jsonl"
        )
        self.rsi_engine = (
            rsi_cls(workspace_root=self.cwd, telemetry_path=telemetry_target)
            if rsi_cls is not None and rsi_cls is not _ms._UNSET
            else None
        )

    def _record_rsi_iteration(
        self,
        session_id: str,
        iteration: int,
        target_path: Path,
        pre_code: str,
        passed: int,
        failed: int,
        verdict: str,
        rolled_back: bool = False,
    ) -> tuple[int, float]:
        """Registra una iterazione in rsi_telemetry.jsonl tramite RSIConvergenceEngine."""
        _ensure_rsi_loaded()
        d_k, q_k = _compute_rsi_metrics(passed, failed, target_path, pre_code)
        rec_cls = _facade_attr("RSIIterationRecord", _ms.RSIIterationRecord)
        if self.rsi_engine is not None and rec_cls is not None and rec_cls is not _ms._UNSET:
            try:
                vec = _build_defect_vector(target_path, pre_code, passed, failed)
                s_hash = self.rsi_engine.compute_files_state_hash([target_path])
                self.rsi_engine.append_telemetry_record(
                    rec_cls(
                        session_id=session_id, iteration=iteration, mode="mode_b",
                        defects=vec, delta_k=d_k, fitness_q=q_k,
                        state_hash=s_hash, verdict=verdict, rolled_back=rolled_back,
                    )
                )
            except Exception:
                pass
        return d_k, q_k

    def run_pipeline(
        self,
        test_cmd: Sequence[str] | str,
        target_file: Path | str,
        repair_callback: Optional[Callable[[OchiaiBridgeLocation, int], bool]] = None,
    ) -> AutoHealSessionReport:
        """Esegue il ciclo di auto-riparazione sul file target guidato da test_cmd."""
        norm_test_cmd = normalize_test_command(test_cmd)
        target_path = (
            Path(self.cwd / target_file)
            if not Path(target_file).is_absolute()
            else Path(target_file)
        )
        pre_code = (
            target_path.read_bytes().decode("utf-8", errors="replace")
            if target_path.exists()
            else ""
        )
        session_id = f"HEAL-{target_path.stem}"

        summary, loc = self.bridge.run_and_diagnose(
            test_cmd=norm_test_cmd, target_file_hint=str(target_file)
        )
        initial_total = summary.passed_count + summary.failed_count

        if (
            summary.exit_code == 0 and summary.failed_count == 0
            and initial_total > 0 and summary.passed_count > 0
        ):
            self._record_rsi_iteration(
                session_id, 0, target_path, pre_code,
                summary.passed_count, 0, "CONVERGED_OPTIMAL", False,
            )
            return AutoHealSessionReport(
                success=True, cycles_used=0, max_cycles=self.max_cycles,
                initial_failed=0, final_failed=0, rsi_delta=0, rsi_fitness_q=100.0,
                message="Clean build: All tests passing on initial evaluation.",
            )

        effective_initial_failed = (
            summary.failed_count if initial_total > 0 else max(1, summary.failed_count)
        )
        self._record_rsi_iteration(
            session_id, 0, target_path, pre_code,
            summary.passed_count, effective_initial_failed, "REFINING", False,
        )

        init_snap_id = self.snapshot_mgr.create_snapshot([target_path])
        initial_passed = summary.passed_count
        initial_failed = effective_initial_failed
        prev_failed = summary.failed_count
        prev_passed = summary.passed_count
        latest_loc = loc

        for cycle in range(1, self.max_cycles + 1):
            cycle_snap_id = self.snapshot_mgr.create_snapshot([target_path])
            if repair_callback and latest_loc:
                try:
                    repair_callback(latest_loc, cycle)
                except Exception:
                    pass

            new_summary, new_loc = self.bridge.run_and_diagnose(
                test_cmd=norm_test_cmd, target_file_hint=str(target_file)
            )
            curr_passed = new_summary.passed_count
            curr_failed = new_summary.failed_count
            curr_total = curr_passed + curr_failed
            prev_total = prev_passed + prev_failed

            fitness = self.snapshot_mgr.evaluate_fitness(
                current_passed=curr_passed, current_failed=curr_failed,
                prev_passed=prev_passed, prev_failed=prev_failed,
                exit_code=new_summary.exit_code,
            )
            monotonic_accepted = (
                curr_total >= prev_total and curr_total > 0 and curr_passed > prev_passed
            )

            if (
                monotonic_accepted and fitness.verdict == FitnessVerdict.PASSED
                and new_summary.exit_code == 0 and curr_failed == 0
            ):
                self._record_rsi_iteration(
                    session_id, cycle, target_path, pre_code,
                    curr_passed, 0, "CONVERGED_OPTIMAL", False,
                )
                self.snapshot_mgr.cleanup()
                patch_note = (
                    f"- **[AUTO-HEALED]** `{latest_loc.error_type}` in "
                    f"`{Path(latest_loc.file_path).name}:{latest_loc.line_number}` "
                    f"(Cycles: {cycle}, Ochiai: {round(latest_loc.suspiciousness, 3)})"
                    if latest_loc
                    else ""
                )
                return AutoHealSessionReport(
                    success=True, cycles_used=cycle, max_cycles=self.max_cycles,
                    initial_failed=initial_failed, final_failed=0,
                    fault_location=f"{latest_loc.file_path}:{latest_loc.line_number}" if latest_loc else None,
                    error_type=latest_loc.error_type if latest_loc else None,
                    ochiai_score=latest_loc.suspiciousness if latest_loc else None,
                    patch_note_line=patch_note, rolled_back=False,
                    rsi_delta=0, rsi_fitness_q=100.0,
                    message=f"Healed successfully on cycle {cycle} via strict fitness gate.",
                )

            if monotonic_accepted and fitness.verdict == FitnessVerdict.IMPROVED:
                prev_failed = curr_failed
                prev_passed = curr_passed
                latest_loc = new_loc
                if cycle_snap_id is not None and cycle_snap_id != init_snap_id:
                    self.snapshot_mgr.cleanup(cycle_snap_id)
                self._record_rsi_iteration(
                    session_id, cycle, target_path, pre_code,
                    prev_passed, prev_failed, "REFINING", False,
                )
            else:
                if cycle_snap_id is not None:
                    self.snapshot_mgr.rollback_to_snapshot(cycle_snap_id)
                    if cycle_snap_id != init_snap_id:
                        self.snapshot_mgr.delete_snapshot(cycle_snap_id)
                self._record_rsi_iteration(
                    session_id, cycle, target_path, pre_code,
                    curr_passed, curr_failed, "ROLLED_BACK_HARD_GATE", True,
                )

        self.snapshot_mgr.rollback(init_snap_id)
        self.snapshot_mgr.cleanup()
        rsi_d, rsi_q = _compute_rsi_metrics(initial_passed, initial_failed, target_path, pre_code)
        return AutoHealSessionReport(
            success=False, cycles_used=self.max_cycles, max_cycles=self.max_cycles,
            initial_failed=initial_failed, final_failed=initial_failed,
            fault_location=f"{latest_loc.file_path}:{latest_loc.line_number}" if latest_loc else None,
            error_type=latest_loc.error_type if latest_loc else None,
            ochiai_score=latest_loc.suspiciousness if latest_loc else None,
            rolled_back=True, rsi_delta=rsi_d, rsi_fitness_q=rsi_q,
            message="Exhausted maximum healing cycles. Rollback to original state completed.",
        )

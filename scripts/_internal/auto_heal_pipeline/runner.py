# -*- coding: utf-8 -*-
"""Orchestratore AutoHealPipeline isolato per lane, calcolo vettore difetti e metriche RSI."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import _internal.auto_heal_pipeline.models_and_slice as _ms
from _internal.auto_heal_pipeline.diagnose_helper import _resolve_target_path, run_diagnose_slice
from _internal.auto_heal_pipeline.models_and_slice import (
    AutoHealSessionReport, DiagnoseSliceReport, OchiaiBridgeLocation,
    _ensure_rsi_loaded, _ensure_sbfl_bridge_loaded, _facade_attr, classify_failure, normalize_test_command,
)
from _internal.auto_heal_pipeline.rsi_bridge_helpers import (
    HypothesisKey, _build_defect_vector, _build_exhausted_message, _cleanup_session_snapshots, _compute_rsi_metrics,  # noqa: F401
    _compute_rsi_metrics_with_vector, _format_patch_note, _hypothesis_key, _invoke_repair_cb,
    _resolve_iteration_metrics, _resolve_prod_baseline_code, _resolve_telemetry_target, _update_strike_state,
)
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.paths import reconfigure_streams

try:
    from healing_snapshot_rollback import FitnessVerdict, HealingSnapshotManager
except ImportError:
    from scripts.healing_snapshot_rollback import FitnessVerdict, HealingSnapshotManager


def _instantiate_scoped(cls_obj: Any, base_kw: Dict[str, Any], opt_kw: Dict[str, Any]) -> Any:
    kw = dict(base_kw)
    try:
        params = inspect.signature(cls_obj).parameters
        has_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        for k, v in opt_kw.items():
            if v is not None and (has_var or k in params):
                kw[k] = v
    except (TypeError, ValueError):
        pass
    return cls_obj(**kw)


def _is_partial_progress_accepted(monotonic_accepted: bool, verdict: Any, exit_code: int, unresolved_collect: bool) -> bool:
    if not monotonic_accepted:
        return False
    if verdict == FitnessVerdict.IMPROVED:
        return True
    return unresolved_collect and verdict != FitnessVerdict.REGRESSION and exit_code in (0, 1)


def _norm_lane_arg(lane_id: Optional[str]) -> Optional[str]:
    return validate_lane_id(lane_id) if (lane_id is not None and str(lane_id).strip()) else None


def _format_heal_session_id(lane_id: Optional[str], target_path: Path) -> str:
    return f"HEAL-{lane_id}-{target_path.stem}" if lane_id else f"HEAL-{target_path.stem}"


class AutoHealPipeline:
    """Orchestratore end-to-end del ciclo di auto-riparazione con scoping per lane."""

    classify_failure = staticmethod(classify_failure)

    def __init__(
        self, cwd: Optional[Path] = None, max_cycles: int = 3,
        *, lane_id: Optional[str] = None, stage_dir: Optional[Path] = None,
    ):
        reconfigure_streams()
        _ensure_sbfl_bridge_loaded()
        _ensure_rsi_loaded()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()
        self.max_cycles = max_cycles
        self.lane_id = _norm_lane_arg(lane_id)
        self.stage_dir = Path(stage_dir).resolve() if stage_dir is not None else None
        self.bridge = _instantiate_scoped(_facade_attr("SBFLPytestBridge", _ms.SBFLPytestBridge), {"cwd": self.cwd}, {"lane_id": self.lane_id, "stage_dir": self.stage_dir})
        self.snapshot_mgr = _instantiate_scoped(_facade_attr("HealingSnapshotManager", HealingSnapshotManager), {}, {"lane_id": self.lane_id, "repo_root": self.cwd})
        rsi_cls = _facade_attr("RSIConvergenceEngine", _ms.RSIConvergenceEngine)
        telemetry_target = _resolve_telemetry_target(self.cwd, lane_id=self.lane_id, stage_dir=self.stage_dir)
        self.rsi_engine = rsi_cls(workspace_root=self.cwd, telemetry_path=telemetry_target) if (rsi_cls is not None and rsi_cls is not _ms._UNSET) else None

    def _record_rsi_iteration(
        self, session_id: str, iteration: int, target_path: Path, pre_code: str,
        passed: int, failed: int, verdict: str, rolled_back: bool = False, precomputed: Optional[Tuple[int, float, Any]] = None,
    ) -> tuple[int, float]:
        _ensure_rsi_loaded()
        d_k, q_k, vec = _resolve_iteration_metrics(target_path, pre_code, passed, failed, precomputed)
        rec_cls = _facade_attr("RSIIterationRecord", _ms.RSIIterationRecord)
        if self.rsi_engine is not None and rec_cls is not None and rec_cls is not _ms._UNSET:
            try:
                s_hash = self.rsi_engine.compute_files_state_hash([target_path])
                self.rsi_engine.append_telemetry_record(rec_cls(session_id=session_id, iteration=iteration, mode="mode_b", defects=vec, delta_k=d_k, fitness_q=q_k, state_hash=s_hash, verdict=verdict, rolled_back=rolled_back))
            except Exception as exc:
                sys.stderr.write(f"[auto_heal_pipeline] telemetry warning: {exc}\n")
        return d_k, q_k

    def _handle_initial_green(self, session_id: str, target_path: Path, pre_code: str, passed_count: int) -> AutoHealSessionReport:
        precomputed = _compute_rsi_metrics_with_vector(passed_count, 0, target_path, pre_code)
        d_k, q_k, _ = precomputed
        is_clean = d_k == 0
        self._record_rsi_iteration(session_id, 0, target_path, pre_code, passed_count, 0, "CONVERGED_OPTIMAL" if is_clean else "FAILED_AST_SAST_GATE", False, precomputed=precomputed)
        msg = "Clean build: All tests passing on initial evaluation." if is_clean else f"Tests passed but AST/SAST defect delta is non-zero (delta_k={d_k})."
        return AutoHealSessionReport(success=is_clean, cycles_used=0, max_cycles=self.max_cycles, initial_failed=0, final_failed=0, rsi_delta=d_k, rsi_fitness_q=q_k, message=msg)

    def _rollback_cycle_snapshot(self, cycle_snap_id: Optional[str], init_snap_id: str, session_id: str, cycle: int, target_path: Path, pre_code: str, curr_passed: int, curr_failed: int) -> None:
        self._record_rsi_iteration(session_id, cycle, target_path, pre_code, curr_passed, curr_failed, "ROLLED_BACK_HARD_GATE", True)
        if cycle_snap_id is None:
            return
        rb_status = self.snapshot_mgr.rollback_to_snapshot(cycle_snap_id)
        if rb_status and all(rb_status.values()) and cycle_snap_id != init_snap_id:
            self.snapshot_mgr.cleanup(snapshot_id=cycle_snap_id)

    def _finalize_exhausted_session(
        self, init_snap_id: str, target_path: Path, pre_code: str, initial_passed: int, initial_failed: int, latest_loc: Optional[OchiaiBridgeLocation],
        *, cycles_used: Optional[int] = None, escalation_required: bool = False, hypothesis: Optional[HypothesisKey] = None,
    ) -> AutoHealSessionReport:
        init_rb = self.snapshot_mgr.rollback(init_snap_id)
        rb_ok = bool(init_rb) and all(init_rb.values())
        if rb_ok:
            self.snapshot_mgr.cleanup(snapshot_id=init_snap_id)
        rsi_d, rsi_q = _compute_rsi_metrics(initial_passed, initial_failed, target_path, pre_code)
        msg = _build_exhausted_message(rb_ok, escalation_required, hypothesis)
        return AutoHealSessionReport(
            success=False, cycles_used=self.max_cycles if cycles_used is None else cycles_used, max_cycles=self.max_cycles,
            initial_failed=initial_failed, final_failed=initial_failed,
            fault_location=f"{latest_loc.file_path}:{latest_loc.line_number}" if latest_loc else None,
            error_type=latest_loc.error_type if latest_loc else None, ochiai_score=latest_loc.suspiciousness if latest_loc else None,
            rolled_back=rb_ok, escalation_required=escalation_required, rsi_delta=rsi_d, rsi_fitness_q=rsi_q, message=msg,
        )

    def run_pipeline(
        self, test_cmd: Sequence[str] | str, target_file: Path | str,
        repair_callback: Optional[Callable[[OchiaiBridgeLocation, int], bool]] = None,
    ) -> AutoHealSessionReport:
        norm_test_cmd = normalize_test_command(test_cmd)
        target_path = _resolve_target_path(self.cwd, target_file)
        pre_code = _resolve_prod_baseline_code(target_path)
        session_id = _format_heal_session_id(self.lane_id, target_path)

        summary, loc = self.bridge.run_and_diagnose(test_cmd=norm_test_cmd, target_file_hint=str(target_file))
        initial_total = summary.passed_count + summary.failed_count
        if summary.exit_code == 0 and summary.failed_count == 0 and initial_total > 0 and summary.passed_count > 0:
            return self._handle_initial_green(session_id, target_path, pre_code, summary.passed_count)

        effective_initial_failed = summary.failed_count if initial_total > 0 else max(1, summary.failed_count)
        self._record_rsi_iteration(session_id, 0, target_path, pre_code, summary.passed_count, effective_initial_failed, "REFINING", False)
        init_snap_id = self.snapshot_mgr.create_snapshot([target_path])
        initial_passed, initial_failed = summary.passed_count, effective_initial_failed
        prev_failed, prev_passed, unresolved_collect = effective_initial_failed, summary.passed_count, (initial_total == 0)
        latest_loc, last_failed_hyp, consecutive_strikes = loc, None, 0

        for cycle in range(1, self.max_cycles + 1):
            attempt_hyp = _hypothesis_key(latest_loc, target_path)
            cycle_snap_id = self.snapshot_mgr.create_snapshot([target_path])
            _invoke_repair_cb(repair_callback, latest_loc, cycle)
            new_summary, new_loc = self.bridge.run_and_diagnose(test_cmd=norm_test_cmd, target_file_hint=str(target_file))
            curr_passed, curr_failed = new_summary.passed_count, new_summary.failed_count
            curr_total, prev_total = curr_passed + curr_failed, prev_passed + prev_failed
            fitness = self.snapshot_mgr.evaluate_fitness(current_passed=curr_passed, current_failed=curr_failed, prev_passed=prev_passed, prev_failed=prev_failed, exit_code=new_summary.exit_code)
            monotonic_accepted = curr_total >= prev_total and curr_total > 0 and curr_passed > prev_passed

            if monotonic_accepted and fitness.verdict == FitnessVerdict.PASSED and new_summary.exit_code == 0 and curr_failed == 0:
                precomputed = _compute_rsi_metrics_with_vector(curr_passed, 0, target_path, pre_code)
                d_k, q_k, _ = precomputed
                if d_k == 0:
                    self._record_rsi_iteration(session_id, cycle, target_path, pre_code, curr_passed, 0, "CONVERGED_OPTIMAL", False, precomputed=precomputed)
                    _cleanup_session_snapshots(self.snapshot_mgr, cycle_snap_id, init_snap_id)
                    return AutoHealSessionReport(
                        success=True, cycles_used=cycle, max_cycles=self.max_cycles, initial_failed=initial_failed, final_failed=0,
                        fault_location=f"{latest_loc.file_path}:{latest_loc.line_number}" if latest_loc else None,
                        error_type=latest_loc.error_type if latest_loc else None, ochiai_score=latest_loc.suspiciousness if latest_loc else None,
                        patch_note_line=_format_patch_note(latest_loc, cycle), rolled_back=False, escalation_required=False,
                        rsi_delta=d_k, rsi_fitness_q=q_k, message=f"Healed successfully on cycle {cycle} via strict fitness gate.",
                    )

            if _is_partial_progress_accepted(monotonic_accepted, fitness.verdict, new_summary.exit_code, unresolved_collect):
                unresolved_collect, prev_failed, prev_passed, latest_loc = False, curr_failed, curr_passed, new_loc
                last_failed_hyp, consecutive_strikes = None, 0
                if cycle_snap_id is not None and cycle_snap_id != init_snap_id:
                    self.snapshot_mgr.cleanup(snapshot_id=cycle_snap_id)
                self._record_rsi_iteration(session_id, cycle, target_path, pre_code, prev_passed, prev_failed, "REFINING", False)
            else:
                self._rollback_cycle_snapshot(cycle_snap_id, init_snap_id, session_id, cycle, target_path, pre_code, curr_passed, curr_failed)
                eff_hyp = attempt_hyp if latest_loc is not None else _hypothesis_key(new_loc, target_path)
                last_failed_hyp, consecutive_strikes = _update_strike_state(last_failed_hyp, consecutive_strikes, eff_hyp)
                if consecutive_strikes >= 2:
                    return self._finalize_exhausted_session(init_snap_id, target_path, pre_code, initial_passed, initial_failed, latest_loc, cycles_used=cycle, escalation_required=True, hypothesis=last_failed_hyp)

        return self._finalize_exhausted_session(init_snap_id, target_path, pre_code, initial_passed, initial_failed, latest_loc)

    def diagnose_slice(self, test_cmd: Sequence[str] | str, target_file: Path | str, *, max_slice_tokens: int = 80) -> DiagnoseSliceReport:
        return run_diagnose_slice(self.cwd, self.bridge, test_cmd, target_file, _resolve_prod_baseline_code, _compute_rsi_metrics, max_slice_tokens=max_slice_tokens)

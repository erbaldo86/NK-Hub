"""Loop di convergenza RSI (G1..G5) e re-export telemetria/CoVe."""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Set, Tuple

from _internal.rsi_convergence_engine.constants import (
    RSIDefectVector,
    RSIIterationRecord,
    RSISessionReport,
)
from _internal.rsi_convergence_engine.cove_and_telemetry import (
    append_telemetry_record_impl,
    compute_record_hash_impl,
    extract_cove_args_tail as _extract_cove_args_tail,
    extract_script_supported_flags_impl,
    get_last_telemetry_hash_impl,
    verify_cli_flags_cove_impl,
    verify_telemetry_chain_impl,
)
from _internal.rsi_convergence_engine.profiles import compute_delta


def check_hard_gate_regression_impl(
    prev_defects: RSIDefectVector,
    curr_defects: RSIDefectVector,
    strict_monotonic: bool = False,
) -> Tuple[bool, str]:
    """Verifica se gli Hard Invariants sono peggiorati rispetto allo stato precedente (Guardia G2)."""
    if curr_defects.tests_passed < prev_defects.tests_passed:
        return (
            True,
            f"Test passati scesi da {prev_defects.tests_passed} a {curr_defects.tests_passed}.",
        )
    if curr_defects.tests_failed > prev_defects.tests_failed:
        return (
            True,
            f"Test falliti saliti da {prev_defects.tests_failed} a {curr_defects.tests_failed}.",
        )
    if curr_defects.sast_critical > prev_defects.sast_critical:
        return (
            True,
            f"SAST critici saliti da {prev_defects.sast_critical} a {curr_defects.sast_critical}.",
        )
    if curr_defects.contract_violations > prev_defects.contract_violations:
        return (
            True,
            f"Violazioni contratti salite da {prev_defects.contract_violations} a {curr_defects.contract_violations}.",
        )
    if curr_defects.high_findings > prev_defects.high_findings:
        return (
            True,
            f"Finding High saliti da {prev_defects.high_findings} a {curr_defects.high_findings}.",
        )
    if curr_defects.poc_confirmed_exploits > prev_defects.poc_confirmed_exploits:
        return (
            True,
            f"Exploit PoC confermati saliti da {prev_defects.poc_confirmed_exploits} a {curr_defects.poc_confirmed_exploits}.",
        )
    if curr_defects.semantic_drift_findings > prev_defects.semantic_drift_findings:
        return (
            True,
            f"Semantic drift saliti da {prev_defects.semantic_drift_findings} a {curr_defects.semantic_drift_findings}.",
        )
    if curr_defects.deception_gaming_count > prev_defects.deception_gaming_count:
        return (
            True,
            f"Episodi di test-gaming saliti da {prev_defects.deception_gaming_count} a {curr_defects.deception_gaming_count}.",
        )
    if curr_defects.hallucinated_refs > prev_defects.hallucinated_refs:
        return (
            True,
            f"Riferimenti allucinati H_k saliti da {prev_defects.hallucinated_refs} a {curr_defects.hallucinated_refs}.",
        )
    if strict_monotonic:
        prev_d = compute_delta(prev_defects)
        curr_d = compute_delta(curr_defects)
        if curr_d > prev_d or (prev_d > 0 and curr_d >= prev_d):
            return (
                True,
                f"Delta_k non migliorato in modalita strict_monotonic da {prev_d} a {curr_d}.",
            )
    return False, "Nessuna regressione rilevata sugli invarianti hard."


def compute_files_state_hash_impl(target_files: Sequence[Path | str]) -> str:
    """Calcola l'hash SHA-256 cumulativo reale dei contenuti dei file target per Guardia G3/G6."""
    hasher = hashlib.sha256()
    if not target_files:
        hasher.update(b"EMPTY_TARGET_SET")
        return hasher.hexdigest()

    unique_resolved = sorted({Path(p).resolve() for p in target_files})
    for p in unique_resolved:
        hasher.update(str(p).encode("utf-8"))
        if p.exists() and p.is_file():
            hasher.update(hashlib.sha256(p.read_bytes()).digest())
        else:
            hasher.update(b"<MISSING>")
    return hasher.hexdigest()


def run_convergence_loop_impl(
    engine: Any,
    evaluate_fn: Callable[[int], RSIDefectVector],
    refine_fn: Optional[Callable[[int, RSIDefectVector], bool]] = None,
    target_files: Optional[Sequence[Path | str]] = None,
    mode: str = "mode_a",
    session_id: Optional[str] = None,
    profile: str = "code_rsi",
) -> RSISessionReport:
    """Esegue il ciclo deterministico RSI applicando le guardie G1..G5."""
    sid = session_id or f"RSI-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    max_iter = engine.get_max_iterations(mode)
    tracked_files = [Path(p).resolve() for p in (target_files or [])]

    history: List[RSIIterationRecord] = []
    visited_hashes: List[str] = []
    seen_hashes: Set[str] = set()
    rollbacks_count = 0
    cycle_detected = False

    init_defects = evaluate_fn(0)
    init_delta = engine.compute_delta(init_defects, profile=profile)
    init_q = engine.compute_fitness(init_defects, delta_k=init_delta, profile=profile)
    init_hash = engine.compute_files_state_hash(tracked_files)
    visited_hashes.append(init_hash)
    seen_hashes.add(init_hash)

    init_verdict = (
        "CONVERGED_OPTIMAL"
        if (init_delta == 0 and init_q >= 100.0)
        else "REFINING"
    )
    rec0 = engine.append_telemetry_record(
        RSIIterationRecord(
            session_id=sid,
            iteration=0,
            mode=mode,
            defects=init_defects,
            delta_k=init_delta,
            fitness_q=init_q,
            state_hash=init_hash,
            verdict=init_verdict,
            rolled_back=False,
        )
    )
    history.append(rec0)

    if init_delta == 0 and init_q >= 100.0:
        return RSISessionReport(
            session_id=sid,
            mode=mode,
            max_iterations=max_iter,
            iterations_used=0,
            converged=True,
            final_status="CONVERGED_OPTIMAL",
            initial_delta=init_delta,
            final_delta=0,
            initial_fitness_q=init_q,
            final_fitness_q=100.0,
            rollbacks_count=0,
            cycle_detected=False,
            visited_hashes=visited_hashes,
            history=history,
        )

    best_defects = init_defects
    best_delta = init_delta
    best_q = init_q
    iterations_used = 0
    final_status = "MAX_ITERATIONS_REACHED"
    converged = False

    for k in range(1, max_iter + 1):
        iterations_used = k
        snap_id: Optional[str] = None
        if tracked_files and engine.snapshot_mgr is not None:
            snap_id = engine.snapshot_mgr.create_snapshot(tracked_files)

        if refine_fn is not None:
            refine_fn(k, best_defects)

        curr_hash = engine.compute_files_state_hash(tracked_files)

        if tracked_files and curr_hash in seen_hashes:
            cycle_detected = True
            if snap_id and engine.snapshot_mgr is not None:
                engine.snapshot_mgr.rollback(snap_id)
                engine.snapshot_mgr.cleanup(snap_id)
            rec_cycle = engine.append_telemetry_record(
                RSIIterationRecord(
                    session_id=sid,
                    iteration=k,
                    mode=mode,
                    defects=best_defects,
                    delta_k=best_delta,
                    fitness_q=best_q,
                    state_hash=curr_hash,
                    verdict="HALTED_CYCLE_DETECTED",
                    rolled_back=True,
                )
            )
            history.append(rec_cycle)
            final_status = "HALTED_CYCLE_DETECTED"
            break

        visited_hashes.append(curr_hash)
        seen_hashes.add(curr_hash)

        curr_defects = evaluate_fn(k)
        curr_delta = engine.compute_delta(curr_defects, profile=profile)
        curr_q = engine.compute_fitness(
            curr_defects, delta_k=curr_delta, profile=profile
        )

        regressed, _ = engine.check_hard_gate_regression(best_defects, curr_defects)
        if regressed:
            rollbacks_count += 1
            if snap_id and engine.snapshot_mgr is not None:
                engine.snapshot_mgr.rollback(snap_id)
                engine.snapshot_mgr.cleanup(snap_id)
            rec_rb = engine.append_telemetry_record(
                RSIIterationRecord(
                    session_id=sid,
                    iteration=k,
                    mode=mode,
                    defects=curr_defects,
                    delta_k=curr_delta,
                    fitness_q=curr_q,
                    state_hash=curr_hash,
                    verdict="ROLLED_BACK_HARD_GATE",
                    rolled_back=True,
                )
            )
            history.append(rec_rb)
            final_status = "ROLLED_BACK_HARD_GATE"
            continue

        if snap_id and engine.snapshot_mgr is not None:
            engine.snapshot_mgr.cleanup(snap_id)

        best_defects = curr_defects
        best_delta = curr_delta
        best_q = curr_q

        if curr_delta == 0 and curr_q >= 100.0:
            verdict = "CONVERGED_OPTIMAL"
            converged = True
            final_status = "CONVERGED_OPTIMAL"
        else:
            verdict = "REFINING"

        rec_k = engine.append_telemetry_record(
            RSIIterationRecord(
                session_id=sid,
                iteration=k,
                mode=mode,
                defects=curr_defects,
                delta_k=curr_delta,
                fitness_q=curr_q,
                state_hash=curr_hash,
                verdict=verdict,
                rolled_back=False,
            )
        )
        history.append(rec_k)

        if converged:
            break

    return RSISessionReport(
        session_id=sid,
        mode=mode,
        max_iterations=max_iter,
        iterations_used=iterations_used,
        converged=converged,
        final_status=final_status,
        initial_delta=init_delta,
        final_delta=best_delta,
        initial_fitness_q=init_q,
        final_fitness_q=best_q,
        rollbacks_count=rollbacks_count,
        cycle_detected=cycle_detected,
        visited_hashes=visited_hashes,
        history=history,
    )


__all__ = [
    "_extract_cove_args_tail",
    "append_telemetry_record_impl",
    "check_hard_gate_regression_impl",
    "compute_files_state_hash_impl",
    "compute_record_hash_impl",
    "extract_script_supported_flags_impl",
    "get_last_telemetry_hash_impl",
    "run_convergence_loop_impl",
    "verify_cli_flags_cove_impl",
    "verify_telemetry_chain_impl",
]

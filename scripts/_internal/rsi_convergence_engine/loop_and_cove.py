# -*- coding: utf-8 -*-
"""Loop di convergenza RSI (G1..G5), telemetria SHA-256 con mutex Win32 e re-export CoVe."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import inspect
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple

from _internal.nk_common.tas_ssot_io import read_last_jsonl_entry
from _internal.nk_common.win32_mutex import create_or_open_named_mutex, release_win32_mutex
from _internal.rsi_convergence_engine.constants import _TELEMETRY_LOCK, RSIDefectVector, RSIIterationRecord, RSISessionReport
from _internal.rsi_convergence_engine.profiles import compute_delta
from _internal.rsi_convergence_engine.sast_scanner import (
    extract_cove_args_tail as _extract_cove_args_tail,
    extract_script_supported_flags_impl,
    verify_cli_flags_cove_impl,
)

_HARD_GATE_UP_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("tests_failed", "Test falliti"),
    ("sast_critical", "SAST critici"),
    ("contract_violations", "Violazioni contratti"),
    ("high_findings", "Finding High"),
    ("poc_confirmed_exploits", "Exploit PoC confermati"),
    ("semantic_drift_findings", "Semantic drift"),
    ("deception_gaming_count", "Episodi di test-gaming"),
    ("hallucinated_refs", "Riferimenti allucinati H_k"),
)


def compute_record_hash_impl(record_dict: Dict[str, Any]) -> str:
    """Calcola l'hash SHA-256 canonico di un record telemetrico escludendo campi None."""
    payload = {k: v for k, v in record_dict.items() if k != "record_hash" and v is not None}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_last_telemetry_hash_impl(engine: Any) -> str:
    """Legge in O(1) da EOF l'ultimo record_hash dal file rsi_telemetry.jsonl."""
    if not engine.telemetry_path.exists() or engine.telemetry_path.stat().st_size == 0:
        return "0" * 64
    last_entry = read_last_jsonl_entry(engine.telemetry_path)
    if isinstance(last_entry, dict) and last_entry.get("record_hash"):
        return str(last_entry["record_hash"])
    raise ValueError(f"Coda telemetria RSI corrotta o priva di record_hash in {engine.telemetry_path}")


@contextmanager
def _telemetry_file_mutex(telemetry_path: Path) -> Iterator[None]:
    """Context manager fail-closed per mutex Win32 su rsi_telemetry.jsonl."""
    h_mutex: Optional[int] = None
    if sys.platform == "win32":
        norm_path = str(telemetry_path.resolve()).lower().replace("/", "\\").rstrip("\\")
        sig = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:12]
        h_mutex, acquired, lock_err = create_or_open_named_mutex(f"Local\\NK_RSITelemetry_{sig}", wait_ms=5000)
        if not acquired:
            raise RuntimeError(f"Impossibile acquisire mutex Win32 su rsi_telemetry.jsonl: {lock_err or 'timeout'}")
    try:
        yield
    finally:
        release_win32_mutex(h_mutex)


def append_telemetry_record_impl(engine: Any, record: RSIIterationRecord) -> RSIIterationRecord:
    """Aggiunge in modo fail-closed sotto Win32 Named Mutex un record alla catena SHA-256."""
    with _TELEMETRY_LOCK, _telemetry_file_mutex(engine.telemetry_path):
        engine.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        prev_hash = engine._get_last_telemetry_hash()
        rec_dict = record.model_dump(exclude_none=True)
        rec_dict["prev_hash"] = prev_hash
        rec_dict["record_hash"] = engine._compute_record_hash(rec_dict)
        signed_record = RSIIterationRecord.model_validate(rec_dict)
        with open(engine.telemetry_path, "a", encoding="utf-8") as f:
            f.write(signed_record.model_dump_json(exclude_none=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return signed_record


def verify_telemetry_chain_impl(engine: Any, telemetry_path: Optional[Path] = None) -> Tuple[bool, int, str]:
    """Verifica l'integrita crittografica della catena SHA-256 in rsi_telemetry.jsonl."""
    target = Path(telemetry_path) if telemetry_path else engine.telemetry_path
    if not target.exists():
        return True, 0, "Nessun file telemetrico presente."
    expected_prev = "0" * 64
    count = 0
    try:
        with open(target, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                clean = line.strip()
                if not clean:
                    continue
                data = json.loads(clean)
                if data.get("prev_hash", "") != expected_prev:
                    return False, count, f"Violazione catena alla riga {idx}: prev_hash non corrisponde."
                computed = engine._compute_record_hash(data)
                if data.get("record_hash", "") != computed:
                    return False, count, f"Violazione integrita alla riga {idx}: record_hash alterato."
                expected_prev = computed
                count += 1
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        return False, count, f"Errore lettura catena telemetrica: {exc}"
    return True, count, f"Catena SHA-256 integra ({count} record verificati)."


def check_hard_gate_regression_impl(
    prev_defects: RSIDefectVector, curr_defects: RSIDefectVector,
    strict_monotonic: bool = False, profile: str = "code_rsi",
) -> Tuple[bool, str]:
    """Verifica se gli Hard Invariants sono peggiorati rispetto allo stato precedente (Guardia G2)."""
    if curr_defects.tests_passed < prev_defects.tests_passed:
        return True, f"Test passati scesi da {prev_defects.tests_passed} a {curr_defects.tests_passed}."
    for attr, label in _HARD_GATE_UP_FIELDS:
        prev_v, curr_v = getattr(prev_defects, attr), getattr(curr_defects, attr)
        if curr_v > prev_v:
            return True, f"{label} saliti da {prev_v} a {curr_v}."
    if strict_monotonic:
        prev_d, curr_d = compute_delta(prev_defects, profile=profile), compute_delta(curr_defects, profile=profile)
        if curr_d > prev_d or (prev_d > 0 and curr_d >= prev_d):
            return True, f"Delta_k non migliorato in modalita strict_monotonic da {prev_d} a {curr_d}."
    return False, "Nessuna regressione rilevata sugli invarianti hard."


def compute_files_state_hash_impl(target_files: Sequence[Path | str]) -> str:
    """Calcola l'hash SHA-256 cumulativo reale dei file target per Guardia G3/G6."""
    hasher = hashlib.sha256()
    if not target_files:
        hasher.update(b"EMPTY_TARGET_SET")
        return hasher.hexdigest()
    for p in sorted({Path(p).resolve() for p in target_files}):
        hasher.update(str(p).encode("utf-8"))
        hasher.update(hashlib.sha256(p.read_bytes()).digest() if p.is_file() else b"<MISSING>")
    return hasher.hexdigest()


def _invoke_hard_gate_regression(
    engine: Any, best_defects: RSIDefectVector, curr_defects: RSIDefectVector, profile: str,
) -> Tuple[bool, str]:
    """Invoca check_hard_gate_regression propagando profile solo se supportato."""
    try:
        sig = inspect.signature(engine.check_hard_gate_regression)
        has_prof = "profile" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    except (TypeError, ValueError):
        has_prof = False
    if has_prof:
        return engine.check_hard_gate_regression(best_defects, curr_defects, profile=profile)
    return engine.check_hard_gate_regression(best_defects, curr_defects)


def _emit_iteration_record(
    engine: Any, sid: str, iteration: int, mode: str, defects: RSIDefectVector,
    delta_k: int, fitness_q: float, state_hash: str, verdict: str, rolled_back: bool,
) -> RSIIterationRecord:
    """Registra un record di iterazione nella catena telemetrica."""
    return engine.append_telemetry_record(
        RSIIterationRecord(
            session_id=sid, iteration=iteration, mode=mode, defects=defects,
            delta_k=delta_k, fitness_q=fitness_q, state_hash=state_hash,
            verdict=verdict, rolled_back=rolled_back,
        )
    )


def _rollback_snapshot(engine: Any, snap_id: Optional[str]) -> None:
    if snap_id and engine.snapshot_mgr is not None:
        engine.snapshot_mgr.rollback(snap_id)
        engine.snapshot_mgr.cleanup(snap_id)


def _is_soft_regression(
    best_defects: RSIDefectVector, best_delta: int, best_q: float,
    curr_defects: RSIDefectVector, curr_delta: int, curr_q: float,
) -> bool:
    if curr_delta > best_delta:
        return True
    if curr_delta == best_delta and curr_q < best_q:
        return True
    if curr_delta == best_delta:
        curr_soft = (curr_defects.medium_findings, curr_defects.low_findings, curr_defects.doc_drift)
        best_soft = (best_defects.medium_findings, best_defects.low_findings, best_defects.doc_drift)
        return curr_soft > best_soft
    return False


def _select_best_state(
    best_defects: RSIDefectVector, best_delta: int, best_q: float,
    curr_defects: RSIDefectVector, curr_delta: int, curr_q: float,
) -> Tuple[RSIDefectVector, int, float]:
    if _is_soft_regression(best_defects, best_delta, best_q, curr_defects, curr_delta, curr_q):
        return best_defects, best_delta, best_q
    return curr_defects, curr_delta, curr_q


def run_convergence_loop_impl(
    engine: Any, evaluate_fn: Callable[[int], RSIDefectVector],
    refine_fn: Optional[Callable[[int, RSIDefectVector], bool]] = None,
    target_files: Optional[Sequence[Path | str]] = None, mode: str = "mode_a",
    session_id: Optional[str] = None, profile: str = "code_rsi",
) -> RSISessionReport:
    """Esegue il ciclo deterministico RSI applicando le guardie G1..G5."""
    sid = session_id or f"RSI-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    max_iter = engine.get_max_iterations(mode)
    tracked_files = [Path(p).resolve() for p in (target_files or [])]

    init_defects = evaluate_fn(0)
    init_delta = engine.compute_delta(init_defects, profile=profile)
    init_q = engine.compute_fitness(init_defects, delta_k=init_delta, profile=profile)
    init_hash = engine.compute_files_state_hash(tracked_files)
    visited_hashes: List[str] = [init_hash]
    seen_hashes: Set[str] = {init_hash}
    init_converged = init_delta == 0 and init_q >= 100.0
    history: List[RSIIterationRecord] = [
        _emit_iteration_record(
            engine, sid, 0, mode, init_defects, init_delta, init_q, init_hash,
            "CONVERGED_OPTIMAL" if init_converged else "REFINING", False,
        )
    ]
    if init_converged:
        return RSISessionReport(
            session_id=sid, mode=mode, max_iterations=max_iter, iterations_used=0,
            converged=True, final_status="CONVERGED_OPTIMAL", initial_delta=init_delta,
            final_delta=0, initial_fitness_q=init_q, final_fitness_q=100.0,
            rollbacks_count=0, cycle_detected=False, visited_hashes=visited_hashes, history=history,
        )

    best_defects, best_delta, best_q = init_defects, init_delta, init_q
    iterations_used, rollbacks_count, cycle_detected = 0, 0, False
    final_status, converged = "MAX_ITERATIONS_REACHED", False

    for k in range(1, max_iter + 1):
        iterations_used = k
        snap_id = engine.snapshot_mgr.create_snapshot(tracked_files) if (tracked_files and engine.snapshot_mgr is not None) else None
        if refine_fn is not None:
            refine_fn(k, best_defects)
        curr_hash = engine.compute_files_state_hash(tracked_files)
        if tracked_files and curr_hash in seen_hashes:
            cycle_detected = True
            _rollback_snapshot(engine, snap_id)
            history.append(_emit_iteration_record(
                engine, sid, k, mode, best_defects, best_delta, best_q, curr_hash, "HALTED_CYCLE_DETECTED", True
            ))
            final_status = "HALTED_CYCLE_DETECTED"
            break
        visited_hashes.append(curr_hash)
        seen_hashes.add(curr_hash)
        curr_defects = evaluate_fn(k)
        curr_delta = engine.compute_delta(curr_defects, profile=profile)
        curr_q = engine.compute_fitness(curr_defects, delta_k=curr_delta, profile=profile)
        regressed, _ = _invoke_hard_gate_regression(engine, best_defects, curr_defects, profile)
        if regressed:
            rollbacks_count += 1
            _rollback_snapshot(engine, snap_id)
            history.append(_emit_iteration_record(
                engine, sid, k, mode, curr_defects, curr_delta, curr_q, curr_hash, "ROLLED_BACK_HARD_GATE", True
            ))
            final_status = "ROLLED_BACK_HARD_GATE"
            continue
        if snap_id and engine.snapshot_mgr is not None:
            engine.snapshot_mgr.cleanup(snap_id)
        best_defects, best_delta, best_q = _select_best_state(best_defects, best_delta, best_q, curr_defects, curr_delta, curr_q)
        converged = curr_delta == 0 and curr_q >= 100.0
        verdict = "CONVERGED_OPTIMAL" if converged else "REFINING"
        final_status = "CONVERGED_OPTIMAL" if converged else "MAX_ITERATIONS_REACHED"
        history.append(_emit_iteration_record(engine, sid, k, mode, curr_defects, curr_delta, curr_q, curr_hash, verdict, False))
        if converged:
            break

    return RSISessionReport(
        session_id=sid, mode=mode, max_iterations=max_iter, iterations_used=iterations_used,
        converged=converged, final_status=final_status, initial_delta=init_delta, final_delta=best_delta,
        initial_fitness_q=init_q, final_fitness_q=best_q, rollbacks_count=rollbacks_count,
        cycle_detected=cycle_detected, visited_hashes=visited_hashes, history=history,
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

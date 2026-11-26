# -*- coding: utf-8 -*-
"""Orchestratore Commit Train 2PC: queue FIFO, OCC/AST gate, Re-Gate, L1 CAS e Priority Barrier."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from _internal.nk_common.commit_train_contracts import CommitTrainOutcomeV1
from _internal.nk_common.commit_train_store import read_commit_train_head
from _internal.nk_common.lane_paths import resolve_staging_dir

from .commit_train_queue import (
    dequeue_lane,
    enqueue_lane,
    is_lane_turn,
    record_rebase_and_promote_barrier,
)
from .delta_regate import run_delta_regate
from .io_and_paths import _resolve_repo_root, get_repo_batch_mutex_name
from .mutex import Win32NamedMutex
from .occ_and_ast_gate import evaluate_occ_and_ast_gate
from .promoter import promote_staging_to_production
from .tensor_session_guard import compute_staging_manifest_sha256


def _fail_outcome(
    status: str,
    lane_id: str,
    msg: str,
    *,
    rebases: int = 0,
    barrier: bool = False,
) -> CommitTrainOutcomeV1:
    return CommitTrainOutcomeV1(
        passed=False,
        status=status,
        lane_id=lane_id,
        rebase_attempts=rebases,
        priority_barrier_used=barrier,
        message=msg,
    )


def _execute_l1_cas_promote(
    root: Path,
    norm_lane: str,
    validated_seq: int,
    promote_kw: Dict[str, Any],
    *,
    key_path: Optional[Union[str, Path]],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    with Win32NamedMutex(get_repo_batch_mutex_name(root), timeout_ms=15000, is_path=False):
        cur_head = read_commit_train_head(root, key_path=key_path)
        if int(cur_head.get("seq", 0)) != validated_seq:
            return True, None
        res = promote_staging_to_production(
            repo_root=root,
            lane_id=norm_lane,
            expected_head_seq=validated_seq,
            use_multi_journal=True,
            post_commit_consolidate=True,
            commit_train_key_path=key_path,
            **promote_kw,
        )
        return False, res


def _build_success_outcome(norm_lane: str, res: Dict[str, Any], rebases: int, barrier_used: bool) -> CommitTrainOutcomeV1:
    return CommitTrainOutcomeV1(
        passed=True,
        status="COMMITTED",
        lane_id=norm_lane,
        batch_id=str(res.get("batch_id") or ""),
        committed_seq=int(res.get("committed_seq", 0)),
        rebase_attempts=rebases,
        priority_barrier_used=barrier_used,
        committed_files=[str(c["relative_path"]) for c in res.get("committed_files", ())],
        deleted_files=list(res.get("deleted_files", ())),
        message="Promozione Commit Train completata con successo.",
    )


def run_commit_train_promote(
    repo_root: Optional[Union[str, Path]],
    *,
    lane_id: Optional[str] = None,
    base_seq: int = 0,
    milestone: Optional[str] = None,
    base_signatures: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    max_rebases: int = 3,
    barrier_threshold: int = 2,
    verify_baseline: bool = False,
    allow_governance_override: bool = False,
    governance_override_reason: Optional[str] = None,
    governance_token: Optional[str] = None,
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]] = None,
    git_sync: bool = False,
    cleanup_staging: bool = True,
    run_gates_fn: Optional[Callable[[Path, int], Dict[str, Any]]] = None,
    baseline_metrics_update: Optional[Dict[str, Any]] = None,
    expected_baseline_sha256: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
    queue_path: Optional[Union[str, Path]] = None,
) -> CommitTrainOutcomeV1:
    """Esegue OCC+AST pre-L1, Delta Re-Gate fuori da L1 e commit atomico CAS in L1."""
    if not lane_id or not str(lane_id).strip():
        return _fail_outcome("INVALID_LANE", "legacy", "Commit Train richiede --lane-id esplicito.")
    root = _resolve_repo_root(repo_root)
    staging_dir, norm_lane = resolve_staging_dir(root, lane_id=lane_id)
    assert norm_lane is not None

    enqueue_lane(
        root,
        norm_lane,
        staging_manifest_sha256=compute_staging_manifest_sha256(staging_dir, exclude_lanes=False),
        barrier_threshold=barrier_threshold,
        queue_path=queue_path,
    )
    promote_kw: Dict[str, Any] = {
        "milestone": milestone,
        "git_sync": git_sync,
        "verify_baseline": verify_baseline,
        "cleanup_staging": cleanup_staging,
        "allow_governance_override": allow_governance_override,
        "governance_override_reason": governance_override_reason,
        "sandbox_report": sandbox_report,
        "governance_token": governance_token,
        "baseline_metrics_update": baseline_metrics_update,
        "expected_baseline_sha256": expected_baseline_sha256,
    }
    rebases, barrier_used = 0, False
    try:
        for _attempt in range(max(0, int(max_rebases)) + 1):
            occ = evaluate_occ_and_ast_gate(
                root, staging_dir, base_seq=int(base_seq),
                base_signatures=base_signatures, exclude_lanes=False, key_path=key_path,
            )
            if not occ["passed"]:
                return _fail_outcome(str(occ["status"]), norm_lane, str(occ.get("unified_diff") or occ["status"])[:600], rebases=rebases, barrier=barrier_used)
            regate = run_delta_regate(root, staging_dir, lane_id=norm_lane, run_gates_fn=run_gates_fn, key_path=key_path)
            if not regate["passed"]:
                return _fail_outcome("REGATE_FAILED", norm_lane, "; ".join(regate.get("violations", ())) or "REGATE_FAILED", rebases=rebases, barrier=barrier_used)
            turn_ok, blocker = is_lane_turn(root, norm_lane, queue_path=queue_path)
            if not turn_ok:
                return _fail_outcome("BLOCKED_BY_PRIORITY_BARRIER", norm_lane, f"In attesa Priority Barrier Ticket della lane {blocker}.", rebases=rebases, barrier=barrier_used)
            cas_advanced, res = _execute_l1_cas_promote(root, norm_lane, int(regate["validated_seq"]), promote_kw, key_path=key_path)
            if cas_advanced:
                q_item = record_rebase_and_promote_barrier(root, norm_lane, barrier_threshold=barrier_threshold, queue_path=queue_path)
                rebases += 1
                barrier_used = barrier_used or bool(q_item.get("priority_barrier"))
                continue
            assert res is not None
            return _build_success_outcome(norm_lane, res, rebases, barrier_used)
        return _fail_outcome("MAX_REBASES_EXCEEDED", norm_lane, f"Superato limite di {max_rebases} rebase concorrenti in Commit Train.", rebases=rebases, barrier=barrier_used)
    finally:
        dequeue_lane(root, norm_lane, queue_path=queue_path)

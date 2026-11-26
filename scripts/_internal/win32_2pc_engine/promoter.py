#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promozione atomica batch da .staging/[lanes/<id>/] alla produzione con Goldilocks Nonce e JournalV3."""

from __future__ import annotations

import inspect
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.commit_train_store import read_commit_train_head
from _internal.nk_common.lane_paths import resolve_staging_dir
from _internal.nk_common.paths import is_nk_proget_online_path

from . import constants as _consts
from . import staging_guards as _guards
from .constants import TwoPhaseCommitError, compute_crc32, compute_sha256
from .engine import TwoPhaseCommitEngine
from .io_and_paths import _assert_no_external_reparse, _resolve_repo_root, _unlink_with_retry, _win_long_path, get_repo_batch_mutex_name
from .journal import BatchJournalV2
from .journal_multi import MultiBatchJournalV3
from .mutex import Win32NamedMutex
from .nonce_store import flush_pending_batch_nonces, governance_batch_nonce_scope
from .post_commit_consolidator import consolidate_post_commit
from .promoter_helpers import collect_staged_payloads, collect_validated_deletions, run_git_sync  # noqa: F401
from .tensor_session_guard import (
    _finalize_promotion_records, _prune_deleted_parent_dirs, _resolve_tensor_nonce_enforce,
    close_active_tensor_session_post_commit, compute_staging_manifest_sha256,
    resolve_slot_path_for_2pc, verify_staged_payloads_tensor_session,
)


def _assert_repo_not_readonly_online(root: Path, real_root: Path, staging_dir: Path) -> None:
    for cand in (root, real_root, staging_dir):
        if is_nk_proget_online_path(cand):
            raise TwoPhaseCommitError(f"[NK_PROGET_ONLINE_READONLY] Promozione 2PC vietata sul mirror read-only: {root}")


def _filter_to_promote_entries(
    staged_payloads: List[Tuple[Path, Path, Path, bytes, str]], unchanged: List[str],
) -> List[Tuple[Path, Path, Path, bytes, str]]:
    to_promote: List[Tuple[Path, Path, Path, bytes, str]] = []
    for stg_file, rel_path, prod_file, stg_bytes, stg_sha in staged_payloads:
        prod_lp = _win_long_path(prod_file)
        if prod_lp.exists() and prod_lp.is_file() and stg_sha == compute_sha256(prod_lp.read_bytes()):
            unchanged.append(str(rel_path))
            continue
        to_promote.append((stg_file, rel_path, prod_file, stg_bytes, stg_sha))
    return to_promote


def _verify_in_memory_tensor_payloads(
    root: Path, staged_payloads: List[Tuple[Path, Path, Path, bytes, str]], deleted_manifest: Path,
    *, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> None:
    in_mem_payloads: Dict[str, bytes] = {rel_path.as_posix(): stg_bytes for _, rel_path, _, stg_bytes, _ in staged_payloads}
    if deleted_manifest.exists() and deleted_manifest.is_file():
        in_mem_payloads[".deleted_files.json"] = _win_long_path(deleted_manifest).read_bytes()
    verify_staged_payloads_tensor_session(root, in_mem_payloads, lane_id=lane_id, staging_dir=staging_dir)


def _invoke_targeted_purge(purge_fn: Any, root: Path, committed: List[Dict[str, Any]], deleted: List[str]) -> None:
    touched_py = [str(c["relative_path"]) for c in committed if str(c.get("relative_path", "")).lower().endswith(".py")] + [str(d) for d in deleted if str(d).lower().endswith(".py")]
    try:
        params = inspect.signature(purge_fn).parameters
        accepts_touched = "touched_rel_paths" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        accepts_touched = False
    purge_fn(root, touched_rel_paths=touched_py) if accepts_touched else purge_fn(root)


def _resolve_promote_context(
    repo_root: Optional[Union[str, Path]], staging_dirname: str, lane_id: Optional[str],
) -> Tuple[Path, Path, Path, Optional[str], bool]:
    root = _resolve_repo_root(repo_root)
    real_root = Path(os.path.realpath(str(root)))
    stg_arg = None if (lane_id is not None and staging_dirname == ".staging") else staging_dirname
    staging_dir, norm_lane = resolve_staging_dir(root, lane_id=lane_id, staging_dir=stg_arg)
    excl_lanes = norm_lane is None and staging_dir.name == ".staging"
    _assert_repo_not_readonly_online(root, real_root, staging_dir)
    return root, real_root, staging_dir, norm_lane, excl_lanes


def _collect_staged_json_to_validate(
    staging_files: List[Path], deleted_manifest: Path, real_root: Path, staging_dir: Path,
) -> List[Path]:
    all_stg_json = [p for p in staging_files if p.suffix.lower() == ".json"]
    if deleted_manifest.exists() and deleted_manifest.is_file():
        _assert_no_external_reparse(deleted_manifest, real_root, stop_at=staging_dir)
        all_stg_json.append(deleted_manifest)
    return all_stg_json


def _assert_pre_swap_cas_and_subdirs(
    root: Path, norm_lane: Optional[str], expected_head_seq: Optional[int], key_path: Optional[Union[str, Path]],
    *, post_consolidate: bool = False, bl_upd: Optional[Dict[str, Any]] = None, exp_bl_sha: Optional[str] = None,
) -> None:
    if expected_head_seq is not None:
        cur_seq = int(read_commit_train_head(root, key_path=key_path).get("seq", 0))
        if cur_seq != int(expected_head_seq):
            raise TwoPhaseCommitError(f"COMMIT_TRAIN_CAS_CONFLICT: head.seq {cur_seq} != {expected_head_seq}")
    if post_consolidate and bl_upd is not None and exp_bl_sha is not None:
        from _internal.quality_baseline_manager.cas_guard import check_baseline_cas

        cas_ok, _cur_sha, cas_err = check_baseline_cas(root / "nk_tracking" / "quality_baseline.json", exp_bl_sha)
        if not cas_ok and cas_err is not None:
            raise TwoPhaseCommitError(str(cas_err.get("message") or cas_err))


def _begin_promote_journal(
    root: Path, batch_targets: List[Tuple[str, Path]], *, use_multi: bool, norm_lane: Optional[str], milestone: str,
) -> Tuple[str, Optional[Path], Optional[Path], Optional[Path], Optional[Dict[str, Any]]]:
    if not batch_targets:
        return "", None, None, None, None
    if use_multi:
        bid, jf, bd = MultiBatchJournalV3.begin_batch(root, batch_targets, lane_id=norm_lane, milestone=milestone)
        return bid, jf, None, bd, json.loads(_win_long_path(jf).read_text(encoding="utf-8-sig"))
    bid, jr, bd = BatchJournalV2.begin_batch(root, batch_targets)
    return bid, None, jr, bd, json.loads(_win_long_path(jr / "active_batch.json").read_text(encoding="utf-8-sig"))


def _roll_forward_committed_batch(manifest: Dict[str, Any], root: Path, ct_key: Optional[Union[str, Path]]) -> None:
    """Completa in modo idempotente il roll-forward di un batch COMMITTED_FS."""
    meta = manifest.get("metadata")
    if not isinstance(meta, dict) or meta.get("post_consolidate") is not True:
        return
    raw_lane = manifest.get("lane_id")
    norm_lane = None if raw_lane in (None, "", "legacy") else str(raw_lane)
    consolidate_post_commit(
        root,
        batch_id=str(manifest.get("batch_id") or ""),
        lane_id=norm_lane,
        milestone=manifest.get("milestone"),
        committed_files=list(meta.get("committed_files", ())),
        deleted_files=list(meta.get("deleted_files", ())),
        staging_manifest_sha256=str(meta.get("staging_manifest_sha256") or ("0" * 64)),
        key_path=ct_key,
    )


def _recover_multi_batches_fail_closed(root: Path, ct_key: Optional[Union[str, Path]]) -> None:
    """Esegue recovery MultiBatchJournalV3 fallendo chiuso su ERROR o UNKNOWN_STATE_ERROR."""
    outcomes = MultiBatchJournalV3.recover_all_batches(
        root, roll_forward_cb=lambda m: _roll_forward_committed_batch(m, root, ct_key),
    )
    failed = [o for o in outcomes if o.get("action") in ("ERROR", "UNKNOWN_STATE_ERROR")]
    if failed:
        raise TwoPhaseCommitError(f"Recovery MultiBatchJournalV3 fallito (fail-closed): {failed[:3]}")


def _finalize_journal_and_consolidate(
    root: Path, *, bid: str, jf: Optional[Path], jr: Optional[Path], bd: Optional[Path],
    use_multi: bool, post_consolidate: bool, norm_lane: Optional[str], milestone: Optional[str],
    committed: List[Dict[str, Any]], deleted: List[str], stg_sha: str,
    bl_upd: Optional[Dict[str, Any]], exp_bl_sha: Optional[str], ct_key: Optional[Union[str, Path]],
) -> Dict[str, Any]:
    cons_res: Dict[str, Any] = {}
    if post_consolidate:
        cons_res = consolidate_post_commit(
            root, batch_id=bid or f"batch_{uuid.uuid4().hex[:8]}", lane_id=norm_lane, milestone=milestone,
            committed_files=[c["relative_path"] for c in committed], deleted_files=deleted,
            staging_manifest_sha256=stg_sha, baseline_metrics_update=bl_upd, expected_baseline_sha256=exp_bl_sha, key_path=ct_key,
        )
    else:
        close_active_tensor_session_post_commit(root, lane_id=norm_lane)
    if use_multi and jf is not None:
        MultiBatchJournalV3.transition_state(jf, "FINALIZED")
        MultiBatchJournalV3.cleanup_batch(jf, bd)
    elif jr is not None:
        BatchJournalV2.cleanup_journal(jr, bd)
    return cons_res


def _apply_fs_writes_and_deletes(
    engine: TwoPhaseCommitEngine, root: Path, real_root: Path,
    to_promote: List[Tuple[Path, Path, Path, bytes, str]],
    validated_deletions: List[Tuple[str, Path]], rollback_cb: Any,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    committed, deleted, failed = [], [], []
    for _stg_file, rel_path, prod_file, stg_bytes, stg_sha in to_promote:
        try:
            verdict = engine.atomic_write(prod_file, stg_bytes)
        except Exception as exc:
            failed.append({"relative_path": str(rel_path), "reason": str(exc), "tx_id": "tx_exception"})
            break
        if verdict.verdict == "COMMIT":
            committed.append({"relative_path": str(rel_path), "committed_path": verdict.committed_path, "sha256": stg_sha, "tx_id": verdict.transaction_id, "execution_time_ms": verdict.execution_time_ms})
        else:
            failed.append({"relative_path": str(rel_path), "reason": verdict.reason, "tx_id": verdict.transaction_id})
            break
    if failed:
        rollback_cb()
        raise TwoPhaseCommitError(f"2PC Promotion aborted and rolled back: {len(failed)} files failed: {failed}")
    deleted_parents: List[Path] = []
    try:
        for _rel_del, del_target in validated_deletions:
            del_lp = _win_long_path(del_target)
            if del_lp.exists() and del_lp.is_file():
                del_bytes = del_lp.read_bytes()
                del_tx_id = f"tx_del_{uuid.uuid4().hex[:12]}"
                with Win32NamedMutex(del_target, timeout_ms=5000):
                    engine.wal.write_wal(tx_id=del_tx_id, target_path=del_target, staging_path=del_target, payload_sha256=compute_sha256(del_bytes), payload_crc32=compute_crc32(del_bytes), state="COMMITTED")
                    _unlink_with_retry(del_target)
                    engine.wal.purge_wal(del_target, del_tx_id)
                deleted.append(del_target.relative_to(root).as_posix())
                deleted_parents.append(del_target.parent)
        _prune_deleted_parent_dirs(deleted_parents, root, real_root)
    except Exception as exc:
        rollback_cb()
        raise TwoPhaseCommitError(f"2PC Deletion aborted and rolled back: {exc}") from exc
    return committed, deleted


def promote_staging_to_production(
    repo_root: Optional[Union[str, Path]] = None, milestone: Optional[str] = None, staging_dirname: str = ".staging",
    subdirs: Optional[List[str]] = None, git_sync: bool = False, verify_baseline: bool = False, cleanup_staging: bool = True,
    allow_governance_override: bool = False, governance_override_reason: Optional[str] = None,
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]] = None, governance_token: Optional[str] = None,
    enforce_nonce_replay: bool = True, *, lane_id: Optional[str] = None, expected_head_seq: Optional[int] = None,
    use_multi_journal: bool = False, post_commit_consolidate: bool = False, commit_train_key_path: Optional[Union[str, Path]] = None,
    baseline_metrics_update: Optional[Dict[str, Any]] = None, expected_baseline_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Promuove in modo atomico i file da .staging/[lanes/<id>/] con Goldilocks Nonce e CAS."""
    root, real_root, staging_dir, norm_lane, excl_lanes = _resolve_promote_context(repo_root, staging_dirname, lane_id)
    unchanged, overridden_paths = [], []

    with Win32NamedMutex(get_repo_batch_mutex_name(root), timeout_ms=15000, is_path=False):
        if subdirs and resolve_slot_path_for_2pc(root, lane_id=norm_lane).exists():
            raise TwoPhaseCommitError("Promozione parziale subdirs vietata con sessione Tensor-RSI attiva.")
        if not staging_dir.exists():
            raise FileNotFoundError(f"Staging directory does not exist: {staging_dir}")

        engine = TwoPhaseCommitEngine()
        _recover_multi_batches_fail_closed(root, commit_train_key_path)
        engine.wal.recover(root, stale_age_sec=60.0)
        staging_files = _consts._get_facade_attr("_scan_staging_canonical", _guards._scan_staging_canonical)(staging_dir, real_root, subdirs=subdirs)
        deleted_manifest = staging_dir / ".deleted_files.json"
        all_stg_json = _collect_staged_json_to_validate(staging_files, deleted_manifest, real_root, staging_dir)
        json_ok, json_errors = _consts._get_facade_attr("validate_staging_json_files", _guards.validate_staging_json_files)(staging_dir, all_stg_json)
        if not json_ok:
            raise TwoPhaseCommitError(f"Validazione JSON pre-commit fallita in staging: {json_errors}")

        _guards._validate_sandbox_evidence_in_batch(sandbox_report, staging_files, staging_dir)
        stg_manifest_sha = compute_staging_manifest_sha256(staging_dir, exclude_lanes=excl_lanes)
        enforce_replay = _resolve_tensor_nonce_enforce(root, staging_dir, enforce_nonce_replay, lane_id=norm_lane)

        with governance_batch_nonce_scope(enforce=enforce_replay, defer_commit=True):
            _guards._enforce_batch_baseline_ratchet(
                root, staging_dir, staging_files, verify_baseline, bool(allow_governance_override),
                governance_override_reason, overridden_paths, governance_token=governance_token, staging_manifest_sha256=stg_manifest_sha,
            )
            validated_deletions = collect_validated_deletions(
                deleted_manifest, root, real_root, bool(allow_governance_override),
                governance_override_reason=governance_override_reason, overridden_out=overridden_paths,
                governance_token=governance_token, staging_manifest_sha256=stg_manifest_sha,
            )
            staged_payloads = collect_staged_payloads(
                staging_files, staging_dir, root, real_root, bool(allow_governance_override),
                governance_override_reason=governance_override_reason, overridden_out=overridden_paths,
                governance_token=governance_token, staging_manifest_sha256=stg_manifest_sha,
            )
            _verify_in_memory_tensor_payloads(root, staged_payloads, deleted_manifest, lane_id=norm_lane, staging_dir=staging_dir)
            _assert_pre_swap_cas_and_subdirs(
                root, norm_lane, expected_head_seq, commit_train_key_path,
                post_consolidate=post_commit_consolidate, bl_upd=baseline_metrics_update, exp_bl_sha=expected_baseline_sha256,
            )

            to_promote = _filter_to_promote_entries(staged_payloads, unchanged)
            batch_targets: List[Tuple[str, Path]] = [(str(rp), pf) for _, rp, pf, _, _ in to_promote] + list(validated_deletions)
            batch_id, jf, jr, bd, active_manifest = _begin_promote_journal(root, batch_targets, use_multi=use_multi_journal, norm_lane=norm_lane, milestone=milestone or "")

            def _rollback_batch() -> None:
                if active_manifest is None:
                    return
                ok_rb = False
                try:
                    BatchJournalV2.rollback_from_manifest(active_manifest, bd)
                    ok_rb = True
                finally:
                    if ok_rb and use_multi_journal and jf is not None:
                        MultiBatchJournalV3.cleanup_batch(jf, bd)
                    elif ok_rb and jr is not None:
                        BatchJournalV2.cleanup_journal(jr, bd)

            try:
                flush_pending_batch_nonces()
            except Exception:
                _rollback_batch()
                raise

        committed, deleted = _apply_fs_writes_and_deletes(engine, root, real_root, to_promote, validated_deletions, _rollback_batch)
        if use_multi_journal and jf is not None:
            MultiBatchJournalV3.transition_state(
                jf,
                "COMMITTED_FS",
                extra={
                    "post_consolidate": bool(post_commit_consolidate),
                    "committed_files": [c["relative_path"] for c in committed],
                    "deleted_files": deleted,
                    "staging_manifest_sha256": stg_manifest_sha,
                },
            )
        if cleanup_staging:
            _consts._get_facade_attr("_cleanup_promoted_staging", _guards._cleanup_promoted_staging)(staging_dir=staging_dir, promoted_files=staging_files, deleted_manifest=deleted_manifest if deleted_manifest.exists() else None)
        _invoke_targeted_purge(_consts._get_facade_attr("_purge_production_bytecode", _guards._purge_production_bytecode), root, committed, deleted)
        effective_git_sync = _finalize_promotion_records(root, milestone, committed, deleted, overridden_paths, governance_override_reason, git_sync)
        cons_res = _finalize_journal_and_consolidate(
            root, bid=batch_id, jf=jf, jr=jr, bd=bd, use_multi=use_multi_journal, post_consolidate=post_commit_consolidate,
            norm_lane=norm_lane, milestone=milestone, committed=committed, deleted=deleted, stg_sha=stg_manifest_sha,
            bl_upd=baseline_metrics_update, exp_bl_sha=expected_baseline_sha256, ct_key=commit_train_key_path,
        )

    out_res: Dict[str, Any] = {
        "status": "SUCCESS", "passed": True, "milestone": milestone, "batch_id": batch_id,
        "committed_files": committed, "unchanged_files": unchanged, "deleted_files": deleted,
        "git_sync": effective_git_sync, "governance_override_recorded": bool(overridden_paths),
    }
    if norm_lane is not None:
        out_res["lane_id"] = norm_lane
    if "committed_seq" in cons_res:
        out_res["committed_seq"] = cons_res["committed_seq"]
    return out_res

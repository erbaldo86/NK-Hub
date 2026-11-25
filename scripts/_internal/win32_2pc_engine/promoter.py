#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promozione atomica batch da .staging/ alla produzione con BatchJournalV2."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.paths import is_nk_proget_online_path

from . import constants as _consts
from . import staging_guards as _guards
from .constants import TwoPhaseCommitError, compute_crc32, compute_sha256
from .engine import TwoPhaseCommitEngine
from .io_and_paths import (
    _assert_no_external_reparse,
    _resolve_repo_root,
    _unlink_with_retry,
    _win_long_path,
    get_repo_batch_mutex_name,
)
from .journal import BatchJournalV2
from .mutex import Win32NamedMutex
from .nonce_store import governance_batch_nonce_scope
from .promoter_helpers import (
    collect_staged_payloads,
    collect_validated_deletions,
    run_git_sync,  # noqa: F401
)
from .tensor_session_guard import (
    _finalize_promotion_records,
    _prune_deleted_parent_dirs,
    _resolve_tensor_nonce_enforce,
    close_active_tensor_session_post_commit,
    compute_staging_manifest_sha256,
    verify_staged_payloads_tensor_session,
)


def _assert_repo_not_readonly_online(root: Path, real_root: Path, staging_dir: Path) -> None:
    """Blocca qualsiasi promozione 2PC verso il mirror read-only NK Proget/Online."""
    for cand in (root, real_root, staging_dir):
        if is_nk_proget_online_path(cand):
            raise TwoPhaseCommitError(
                f"[NK_PROGET_ONLINE_READONLY] Promozione 2PC vietata sul mirror read-only: {root}"
            )


def _filter_to_promote_entries(
    staged_payloads: List[Tuple[Path, Path, Path, bytes, str]],
    unchanged: List[str],
) -> List[Tuple[Path, Path, Path, bytes, str]]:
    """Separa i file modificati da quelli identici rispetto alla produzione."""
    to_promote: List[Tuple[Path, Path, Path, bytes, str]] = []
    for stg_file, rel_path, prod_file, stg_bytes, stg_sha in staged_payloads:
        prod_lp = _win_long_path(prod_file)
        if prod_lp.exists() and prod_lp.is_file() and stg_sha == compute_sha256(prod_lp.read_bytes()):
            unchanged.append(str(rel_path))
            continue
        to_promote.append((stg_file, rel_path, prod_file, stg_bytes, stg_sha))
    return to_promote


def _verify_in_memory_tensor_payloads(
    root: Path,
    staged_payloads: List[Tuple[Path, Path, Path, bytes, str]],
    deleted_manifest: Path,
) -> None:
    """Verifica i payload staged in memoria (incluso .deleted_files.json) contro ACTIVE.json."""
    in_mem_payloads: Dict[str, bytes] = {
        rel_path.as_posix(): stg_bytes
        for _stg_file, rel_path, _prod_file, stg_bytes, _stg_sha in staged_payloads
    }
    if deleted_manifest.exists() and deleted_manifest.is_file():
        in_mem_payloads[".deleted_files.json"] = _win_long_path(deleted_manifest).read_bytes()
    verify_staged_payloads_tensor_session(root, in_mem_payloads)


def promote_staging_to_production(
    repo_root: Optional[Union[str, Path]] = None,
    milestone: Optional[str] = None,
    staging_dirname: str = ".staging",
    subdirs: Optional[List[str]] = None,
    git_sync: bool = False,
    verify_baseline: bool = False,
    cleanup_staging: bool = True,
    allow_governance_override: bool = False,
    governance_override_reason: Optional[str] = None,
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]] = None,
    governance_token: Optional[str] = None,
    enforce_nonce_replay: bool = True,
) -> Dict[str, Any]:
    """Promuove in modo atomico i file da .staging/ alla produzione purgando __pycache__."""
    root = _resolve_repo_root(repo_root)
    real_root = Path(os.path.realpath(str(root)))
    staging_dir = root / staging_dirname
    _assert_repo_not_readonly_online(root, real_root, staging_dir)

    committed: List[Dict[str, Any]] = []
    unchanged: List[str] = []
    deleted: List[str] = []
    failed: List[Dict[str, Any]] = []
    overridden_paths: List[str] = []
    effective_git_sync = False

    with Win32NamedMutex(
        get_repo_batch_mutex_name(root),
        timeout_ms=15000,
        is_path=False,
    ):
        if not staging_dir.exists():
            raise FileNotFoundError(f"Staging directory does not exist: {staging_dir}")

        engine = TwoPhaseCommitEngine()
        engine.wal.recover(root, stale_age_sec=60.0)

        scan_fn = _consts._get_facade_attr(
            "_scan_staging_canonical", _guards._scan_staging_canonical
        )
        staging_files = scan_fn(staging_dir, real_root, subdirs=subdirs)
        deleted_manifest = staging_dir / ".deleted_files.json"

        all_stg_json = [p for p in staging_files if p.suffix.lower() == ".json"]
        if deleted_manifest.exists() and deleted_manifest.is_file():
            _assert_no_external_reparse(
                deleted_manifest, real_root, stop_at=staging_dir
            )
            all_stg_json.append(deleted_manifest)

        val_json_fn = _consts._get_facade_attr(
            "validate_staging_json_files", _guards.validate_staging_json_files
        )
        json_ok, json_errors = val_json_fn(staging_dir, all_stg_json)
        if not json_ok:
            raise TwoPhaseCommitError(
                f"Validazione JSON pre-commit fallita in staging: {json_errors}"
            )

        _guards._validate_sandbox_evidence_in_batch(
            sandbox_report, staging_files, staging_dir
        )

        stg_manifest_sha = compute_staging_manifest_sha256(staging_dir)

        with governance_batch_nonce_scope(
            enforce=_resolve_tensor_nonce_enforce(root, staging_dir, enforce_nonce_replay)
        ):
            _guards._enforce_batch_baseline_ratchet(
                root,
                staging_dir,
                staging_files,
                verify_baseline,
                bool(allow_governance_override),
                governance_override_reason,
                overridden_paths,
                governance_token=governance_token,
                staging_manifest_sha256=stg_manifest_sha,
            )

            validated_deletions = collect_validated_deletions(
                deleted_manifest,
                root,
                real_root,
                bool(allow_governance_override),
                governance_override_reason=governance_override_reason,
                overridden_out=overridden_paths,
                governance_token=governance_token,
                staging_manifest_sha256=stg_manifest_sha,
            )
            staged_payloads = collect_staged_payloads(
                staging_files,
                staging_dir,
                root,
                real_root,
                bool(allow_governance_override),
                governance_override_reason=governance_override_reason,
                overridden_out=overridden_paths,
                governance_token=governance_token,
                staging_manifest_sha256=stg_manifest_sha,
            )

        _verify_in_memory_tensor_payloads(root, staged_payloads, deleted_manifest)

        to_promote = _filter_to_promote_entries(staged_payloads, unchanged)

        batch_targets: List[Tuple[str, Path]] = [
            (str(rel_path), prod_file)
            for _, rel_path, prod_file, _, _ in to_promote
        ] + [(rel_del, del_target) for rel_del, del_target in validated_deletions]

        journal_root: Optional[Path] = None
        batch_dir: Optional[Path] = None
        active_manifest: Optional[Dict[str, Any]] = None
        if batch_targets:
            _, journal_root, batch_dir = BatchJournalV2.begin_batch(root, batch_targets)
            active_manifest = json.loads(
                _win_long_path(journal_root / "active_batch.json").read_text(
                    encoding="utf-8-sig"
                )
            )

        def _rollback_batch() -> None:
            if active_manifest is not None:
                rollback_ok = False
                try:
                    BatchJournalV2.rollback_from_manifest(active_manifest, batch_dir)
                    rollback_ok = True
                finally:
                    if rollback_ok and journal_root is not None:
                        BatchJournalV2.cleanup_journal(journal_root, batch_dir)

        for _stg_file, rel_path, prod_file, stg_bytes, stg_sha in to_promote:
            try:
                verdict = engine.atomic_write(prod_file, stg_bytes)
            except Exception as exc:
                failed.append({
                    "relative_path": str(rel_path),
                    "reason": str(exc),
                    "tx_id": "tx_exception",
                })
                break

            if verdict.verdict == "COMMIT":
                committed.append({
                    "relative_path": str(rel_path),
                    "committed_path": verdict.committed_path,
                    "sha256": stg_sha,
                    "tx_id": verdict.transaction_id,
                    "execution_time_ms": verdict.execution_time_ms,
                })
            else:
                failed.append({
                    "relative_path": str(rel_path),
                    "reason": verdict.reason,
                    "tx_id": verdict.transaction_id,
                })
                break

        if failed:
            _rollback_batch()
            raise TwoPhaseCommitError(
                f"2PC Promotion aborted and rolled back: {len(failed)} files failed: {failed}"
            )

        deleted_parents: List[Path] = []
        try:
            for _rel_del, del_target in validated_deletions:
                del_lp = _win_long_path(del_target)
                if del_lp.exists() and del_lp.is_file():
                    del_bytes = del_lp.read_bytes()
                    del_tx_id = f"tx_del_{uuid.uuid4().hex[:12]}"
                    del_sha = compute_sha256(del_bytes)
                    del_crc = compute_crc32(del_bytes)
                    with Win32NamedMutex(del_target, timeout_ms=5000):
                        engine.wal.write_wal(
                            tx_id=del_tx_id,
                            target_path=del_target,
                            staging_path=del_target,
                            payload_sha256=del_sha,
                            payload_crc32=del_crc,
                            state="COMMITTED",
                        )
                        _unlink_with_retry(del_target)
                        engine.wal.purge_wal(del_target, del_tx_id)
                    deleted.append(del_target.relative_to(root).as_posix())
                    deleted_parents.append(del_target.parent)
            _prune_deleted_parent_dirs(deleted_parents, root, real_root)
        except Exception as exc:
            _rollback_batch()
            raise TwoPhaseCommitError(
                f"2PC Deletion aborted and rolled back: {exc}"
            ) from exc

        if journal_root is not None:
            BatchJournalV2.cleanup_journal(journal_root, batch_dir)

        if cleanup_staging:
            cleanup_fn = _consts._get_facade_attr(
                "_cleanup_promoted_staging", _guards._cleanup_promoted_staging
            )
            cleanup_fn(
                staging_dir=staging_dir,
                promoted_files=staging_files,
                deleted_manifest=deleted_manifest if deleted_manifest.exists() else None,
            )
        close_active_tensor_session_post_commit(root)
        purge_fn = _consts._get_facade_attr(
            "_purge_production_bytecode", _guards._purge_production_bytecode
        )
        purge_fn(root)

        effective_git_sync = _finalize_promotion_records(
            root,
            milestone,
            committed,
            deleted,
            overridden_paths,
            governance_override_reason,
            git_sync,
        )

    return {
        "status": "SUCCESS",
        "passed": True,
        "milestone": milestone,
        "committed_files": committed,
        "unchanged_files": unchanged,
        "deleted_files": deleted,
        "git_sync": effective_git_sync,
        "governance_override_recorded": bool(overridden_paths),
    }

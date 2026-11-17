#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promozione atomica batch da .staging/ alla produzione con BatchJournalV2."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from . import constants as _consts
from . import staging_guards as _guards
from .constants import TwoPhaseCommitError, compute_crc32, compute_sha256
from .engine import TwoPhaseCommitEngine
from .io_and_paths import (
    _assert_no_external_reparse,
    _is_reparse_point,
    _resolve_repo_root,
    _unlink_with_retry,
    _win_long_path,
    get_repo_batch_mutex_name,
)
from .journal import BatchJournalV2
from .mutex import Win32NamedMutex
from .promoter_helpers import (
    collect_staged_payloads,
    collect_validated_deletions,
    run_git_sync,
)

_PROTECTED_PRUNE_DIRS = frozenset({
    "",
    ".",
    ".agents",
    ".agents/plugins",
    ".agents/plugins/nk-gate",
    ".agents/skills",
    ".agents/agents",
    "scripts",
    "tests",
    "nk_tracking",
    "nk_tracking/reports_and_briefs",
    "nk_genome",
})


def _prune_deleted_parent_dirs(
    deleted_parents: List[Path], root: Path, real_root: Path
) -> None:
    """Rimuove dal basso verso l'alto le cartelle svuotate non protette."""
    for start_parent in sorted(
        set(deleted_parents),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        curr = start_parent
        while True:
            if curr == root or curr == real_root or curr.parent == curr:
                break
            try:
                rel_dir = curr.relative_to(root).as_posix().lower()
            except ValueError:
                break
            if rel_dir in _PROTECTED_PRUNE_DIRS:
                break
            real_curr = Path(os.path.realpath(str(curr)))
            if real_curr == real_root or real_root not in real_curr.parents:
                break
            if _is_reparse_point(curr):
                break
            curr_lp = _win_long_path(curr)
            if not curr_lp.exists():
                curr = curr.parent
                continue
            if not curr_lp.is_dir() or _is_reparse_point(curr_lp):
                break
            try:
                with os.scandir(curr_lp) as dir_it:
                    if next(dir_it, None) is not None:
                        break
                os.rmdir(curr_lp)
            except OSError:
                break
            curr = curr.parent


def promote_staging_to_production(
    repo_root: Optional[Union[str, Path]] = None,
    milestone: Optional[str] = None,
    staging_dirname: str = ".staging",
    subdirs: Optional[List[str]] = None,
    git_sync: bool = False,
    verify_baseline: bool = False,
    cleanup_staging: bool = True,
    allow_governance_override: bool = False,
) -> Dict[str, Any]:
    """Promuove in modo atomico i file modificati da .staging/ alla produzione purgando __pycache__."""
    root = _resolve_repo_root(repo_root)
    real_root = Path(os.path.realpath(str(root)))
    staging_dir = root / staging_dirname

    committed: List[Dict[str, Any]] = []
    unchanged: List[str] = []
    deleted: List[str] = []
    failed: List[Dict[str, Any]] = []

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

        if verify_baseline:
            dst_bl = root / "nk_tracking" / "quality_baseline.json"
            stg_bl = staging_dir / "nk_tracking" / "quality_baseline.json"
            if not dst_bl.exists() and not stg_bl.exists():
                raise TwoPhaseCommitError(
                    f"File quality_baseline.json mancante sia in produzione ({dst_bl}) sia in staging ({stg_bl})."
                )
            ratchet_fn = _consts._get_facade_attr(
                "_verify_quality_baseline_ratchet",
                _guards._verify_quality_baseline_ratchet,
            )
            try:
                ratchet_fn(
                    dst_bl,
                    stg_bl,
                    allow_ratchet_down=bool(allow_governance_override),
                )
            except TwoPhaseCommitError:
                raise
            except Exception as exc:
                raise TwoPhaseCommitError(
                    f"Errore durante la verifica del baseline: {exc}"
                ) from exc

        validated_deletions = collect_validated_deletions(
            deleted_manifest, root, real_root, bool(allow_governance_override)
        )
        staged_payloads = collect_staged_payloads(
            staging_files,
            staging_dir,
            root,
            real_root,
            bool(allow_governance_override),
        )

        to_promote: List[Tuple[Path, Path, Path, bytes, str]] = []
        for stg_file, rel_path, prod_file, stg_bytes, stg_sha in staged_payloads:
            prod_lp = _win_long_path(prod_file)
            if prod_lp.exists() and prod_lp.is_file():
                prod_bytes = prod_lp.read_bytes()
                if stg_sha == compute_sha256(prod_bytes):
                    unchanged.append(str(rel_path))
                    continue
            to_promote.append((stg_file, rel_path, prod_file, stg_bytes, stg_sha))

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
                try:
                    BatchJournalV2.rollback_from_manifest(active_manifest, batch_dir)
                finally:
                    if journal_root is not None:
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
        purge_fn = _consts._get_facade_attr(
            "_purge_production_bytecode", _guards._purge_production_bytecode
        )
        purge_fn(root)

        tracking_dir = root / "nk_tracking"
        if (tracking_dir.is_dir() or milestone) and (
            committed or deleted or milestone
        ):
            anchor_fn = _consts._get_facade_attr(
                "record_session_anchor_commit", _guards.record_session_anchor_commit
            )
            anchor_fn(root, milestone or "2PC_PROMOTE", committed, deleted)

    effective_git_sync = run_git_sync(root, committed, deleted) if git_sync else False

    return {
        "status": "SUCCESS",
        "passed": True,
        "milestone": milestone,
        "committed_files": committed,
        "unchanged_files": unchanged,
        "deleted_files": deleted,
        "git_sync": effective_git_sync if git_sync else False,
    }

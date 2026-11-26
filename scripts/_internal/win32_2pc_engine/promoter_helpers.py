#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helper di quarantena staging, validazione payload/cancellazioni e sync Git."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir
from _internal.nk_common.paths import is_nk_proget_online_path
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

from .constants import (
    TwoPhaseCommitError,
    compute_sha256,
    is_protected_governance_path,
    validate_override_reason,  # noqa: F401
)
from .governance_auth import authorize_governance_override
from .io_and_paths import (
    _assert_no_external_reparse,
    _extract_patch_notes_headers,
    _get_repo_hash16,
    _is_reparse_point,
    _resolve_repo_root,
    _unlink_with_retry,
    _validate_win32_canonical_rel_path,
    _win_long_path,
    get_repo_batch_mutex_name,
)
from .mutex import Win32NamedMutex
from .tensor_session_guard import (
    assert_no_active_tensor_session_for_quarantine,
    run_git_sync,  # noqa: F401
)


def _move_staging_entries_to_quarantine(
    staging_dir: Path, quarantine_root: Path, excl_lanes: bool
) -> List[str]:
    """Sposta i file staged (o lane) nella directory di quarantena saltando lanes/ in legacy."""
    import shutil

    moved_files: List[str] = []
    for item in sorted(list(staging_dir.rglob("*"))):
        try:
            rel = item.relative_to(staging_dir)
            if excl_lanes and is_lane_container_entry(rel.parts):
                continue
            if _is_reparse_point(item):
                if item.is_dir() and not item.is_symlink():
                    os.rmdir(_win_long_path(item))
                else:
                    _unlink_with_retry(item)
                continue
            if not item.is_file() or item.name == ".gitkeep":
                continue
            dest = quarantine_root / rel
            _win_long_path(dest.parent).mkdir(parents=True, exist_ok=True)
            shutil.move(str(_win_long_path(item)), str(_win_long_path(dest)))
            moved_files.append(rel.as_posix())
        except OSError:
            pass
    return moved_files


def _prune_empty_staging_dirs(staging_dir: Path, excl_lanes: bool) -> None:
    """Rimuove le sottodirectory vuote di staging preservando lanes/ in legacy."""
    all_dirs = sorted(
        (d for d in staging_dir.rglob("*") if d.is_dir() and not (excl_lanes and is_lane_container_entry(d.relative_to(staging_dir).parts))),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for d in all_dirs:
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def quarantine_staging(
    repo_root: Optional[Union[str, Path]] = None,
    staging_dirname: str = ".staging",
    *,
    lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Sposta i contenuti correnti di .staging/ (o lane) in quarantena isolata in %TEMP%."""
    root = _resolve_repo_root(repo_root)
    stg_arg = None if (lane_id is not None and staging_dirname == ".staging") else staging_dirname
    staging_dir, norm_lane = resolve_staging_dir(root, lane_id=lane_id, staging_dir=stg_arg)
    excl_lanes = norm_lane is None and staging_dir.name == ".staging"
    quarantine_root = Path(tempfile.gettempdir()) / "nk_2pc_staging_quarantine" / f"{_get_repo_hash16(root)}_{norm_lane or 'legacy'}_{int(time.time() * 1000)}"
    moved_files: List[str] = []

    with Win32NamedMutex(get_repo_batch_mutex_name(root), timeout_ms=10000, is_path=False):
        assert_no_active_tensor_session_for_quarantine(root, lane_id=norm_lane)
        if not staging_dir.exists():
            staging_dir.mkdir(parents=True, exist_ok=True)
            (staging_dir / ".gitkeep").write_text("", encoding="utf-8")
            return {"status": "SUCCESS", "passed": True, "lane_id": norm_lane, "quarantine_dir": None, "quarantined_count": 0, "quarantined_files": []}
        moved_files = _move_staging_entries_to_quarantine(staging_dir, quarantine_root, excl_lanes)
        _prune_empty_staging_dirs(staging_dir, excl_lanes)
        gitkeep = staging_dir / ".gitkeep"
        if not gitkeep.exists():
            staging_dir.mkdir(parents=True, exist_ok=True)
            gitkeep.write_text("", encoding="utf-8")

    return {"status": "SUCCESS", "passed": True, "lane_id": norm_lane, "quarantine_dir": str(quarantine_root) if moved_files else None, "quarantined_count": len(moved_files), "quarantined_files": moved_files}


def _enforce_deletion_governance(
    rel_del: str,
    clean_rel_del: str,
    rel_del_norm: str,
    del_target: Path,
    allow_governance_override: bool,
    governance_override_reason: Optional[str],
    overridden_out: Optional[List[str]],
    governance_token: Optional[str] = None,
    staging_manifest_sha256: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> None:
    del_name_low = Path(rel_del_norm).name.lower()
    is_protected = (
        is_protected_governance_path(rel_del_norm, repo_root=repo_root)
        or rel_del_norm == "nk_tracking/quality_baseline.json"
        or (
            del_name_low.startswith("checkpoint_")
            and del_name_low.endswith(".json")
            and _win_long_path(del_target).exists()
        )
        or (
            rel_del_norm in ("patch_notes.md", "nk_genome/patch_notes.md")
            and _win_long_path(del_target).exists()
        )
    )
    if not is_protected:
        return
    if not allow_governance_override:
        raise TwoPhaseCommitError(
            f"Cancellazione bloccata per file di governance protetto ({rel_del}): "
            "richiesto --allow-governance-override ([RULE-ORACLE-LOCK])."
        )
    authorize_governance_override(
        governance_override_reason,
        governance_token,
        rel_del,
        staging_manifest_sha256=staging_manifest_sha256,
    )
    if overridden_out is not None:
        overridden_out.append(f"delete:{clean_rel_del}")


def collect_validated_deletions(
    deleted_manifest: Path,
    root: Path,
    real_root: Path,
    allow_governance_override: bool,
    governance_override_reason: Optional[str] = None,
    overridden_out: Optional[List[str]] = None,
    governance_token: Optional[str] = None,
    staging_manifest_sha256: Optional[str] = None,
) -> List[Tuple[str, Path]]:
    """Valida il manifest .deleted_files.json contro denylist, Online read-only e reparse esterni."""
    try:
        deleted_rel_paths = parse_deleted_files_manifest(deleted_manifest)
    except ValueError as exc:
        raise TwoPhaseCommitError(str(exc)) from exc

    validated_deletions: List[Tuple[str, Path]] = []
    for rel_del in deleted_rel_paths:
        clean_rel_del = _validate_win32_canonical_rel_path(rel_del)
        rel_del_norm = clean_rel_del.lower()
        del_target = (root / clean_rel_del).resolve()
        _assert_no_external_reparse(del_target, real_root, stop_at=root)
        real_del_target = Path(os.path.realpath(str(del_target)))
        if is_nk_proget_online_path(del_target) or is_nk_proget_online_path(real_del_target):
            raise TwoPhaseCommitError(
                f"[NK_PROGET_ONLINE_READONLY] Cancellazione 2PC vietata sul mirror read-only: {rel_del}"
            )
        if real_del_target == real_root or real_root not in real_del_target.parents:
            raise TwoPhaseCommitError(
                f"Percorso di cancellazione fuori dalla root del repository: {rel_del}"
            )
        _enforce_deletion_governance(
            rel_del,
            clean_rel_del,
            rel_del_norm,
            del_target,
            allow_governance_override,
            governance_override_reason,
            overridden_out,
            governance_token=governance_token,
            staging_manifest_sha256=staging_manifest_sha256,
            repo_root=root,
        )
        validated_deletions.append((clean_rel_del, del_target))
    return validated_deletions


def _enforce_staged_payload_governance(
    rel_path: Path,
    clean_rel: str,
    rel_norm: str,
    prod_file: Path,
    stg_bytes: bytes,
    allow_governance_override: bool,
    governance_override_reason: Optional[str],
    overridden_out: Optional[List[str]],
    governance_token: Optional[str] = None,
    staging_manifest_sha256: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> None:
    rel_name_low = Path(rel_norm).name.lower()
    is_protected_cp = (
        rel_name_low.startswith("checkpoint_")
        and rel_name_low.endswith(".json")
        and _win_long_path(prod_file).exists()
    )
    if is_protected_governance_path(rel_norm, repo_root=repo_root) or is_protected_cp:
        if not allow_governance_override:
            raise TwoPhaseCommitError(
                f"Promozione bloccata per file di governance protetto ({rel_path.as_posix()}): "
                "richiesto --allow-governance-override ([RULE-ORACLE-LOCK])."
            )
        authorize_governance_override(
            governance_override_reason,
            governance_token,
            clean_rel,
            staging_manifest_sha256=staging_manifest_sha256,
        )
        if overridden_out is not None:
            overridden_out.append(f"promote:{clean_rel}")

    if (
        rel_norm in ("patch_notes.md", "nk_genome/patch_notes.md")
        and _win_long_path(prod_file).exists()
        and _win_long_path(prod_file).is_file()
    ):
        prod_txt = _win_long_path(prod_file).read_bytes().decode(
            "utf-8-sig", errors="replace"
        )
        stg_txt = stg_bytes.decode("utf-8-sig", errors="replace")
        prod_headers = _extract_patch_notes_headers(prod_txt)
        stg_headers = set(_extract_patch_notes_headers(stg_txt))
        missing_headers = [h for h in prod_headers if h not in stg_headers]
        if missing_headers:
            if not allow_governance_override:
                raise TwoPhaseCommitError(
                    f"Promozione bloccata per {rel_path.as_posix()}: header storici ## [...] "
                    f"rimossi ({missing_headers[0]}); richiesto --allow-governance-override."
                )
            authorize_governance_override(
                governance_override_reason,
                governance_token,
                clean_rel,
                staging_manifest_sha256=staging_manifest_sha256,
            )
            if overridden_out is not None:
                overridden_out.append(f"patch_notes_rewrite:{clean_rel}")


def collect_staged_payloads(
    staging_files: List[Path],
    staging_dir: Path,
    root: Path,
    real_root: Path,
    allow_governance_override: bool,
    governance_override_reason: Optional[str] = None,
    overridden_out: Optional[List[str]] = None,
    governance_token: Optional[str] = None,
    staging_manifest_sha256: Optional[str] = None,
) -> List[Tuple[Path, Path, Path, bytes, str]]:
    """Valida e carica in memoria i payload di staging verificando governance lock, Online e PATCH_NOTES."""
    staged_payloads: List[Tuple[Path, Path, Path, bytes, str]] = []
    for stg_file in staging_files:
        rel_path = stg_file.relative_to(staging_dir)
        clean_rel = _validate_win32_canonical_rel_path(rel_path)
        rel_norm = clean_rel.lower()
        prod_file = (root / clean_rel).resolve()
        _assert_no_external_reparse(prod_file, real_root, stop_at=root)
        real_prod = Path(os.path.realpath(str(prod_file)))
        if is_nk_proget_online_path(prod_file) or is_nk_proget_online_path(real_prod):
            raise TwoPhaseCommitError(
                f"[NK_PROGET_ONLINE_READONLY] Promozione 2PC vietata sul mirror read-only: {rel_path}"
            )
        if real_prod == real_root or real_root not in real_prod.parents:
            raise TwoPhaseCommitError(
                f"Percorso di promozione fuori dalla root del repository: {rel_path}"
            )
        stg_bytes = _win_long_path(stg_file).read_bytes()
        _enforce_staged_payload_governance(
            rel_path,
            clean_rel,
            rel_norm,
            prod_file,
            stg_bytes,
            allow_governance_override,
            governance_override_reason,
            overridden_out,
            governance_token=governance_token,
            staging_manifest_sha256=staging_manifest_sha256,
            repo_root=root,
        )
        stg_sha = compute_sha256(stg_bytes)
        staged_payloads.append((stg_file, rel_path, prod_file, stg_bytes, stg_sha))
    return staged_payloads

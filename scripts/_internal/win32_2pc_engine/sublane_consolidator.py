# -*- coding: utf-8 -*-
"""Consolidatore atomico multi sub-lane con barriera combinata e promozione 2PC/Commit Train."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from _internal.nk_common.lane_paths import assert_safe_staging_ancestors, resolve_staging_dir, validate_lane_id
from _internal.nk_common.lane_registry import release_lane
from _internal.nk_common.nvme_mirror_helpers import safe_rmtree
from _internal.nk_common.staging_manifest import LANE_CONTAINER_DIRNAME, is_reparse_entry
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

from .commit_train_orchestrator import run_commit_train_promote
from .io_and_paths import _resolve_repo_root, get_repo_batch_mutex_name
from .mutex import Win32NamedMutex
from .promoter import promote_staging_to_production


def is_sublane_of(lane_id: str, parent_lane: str) -> bool:
    """True se lane_id appartiene gerarchicamente a parent_lane (prefisso _ o -)."""
    norm_sub = validate_lane_id(lane_id)
    norm_parent = validate_lane_id(parent_lane)
    return norm_sub != norm_parent and (
        norm_sub.startswith(f"{norm_parent}_") or norm_sub.startswith(f"{norm_parent}-")
    )


def discover_sublanes(repo_root: Union[str, Path], parent_lane: str) -> List[Tuple[str, Path]]:
    """Individua in ordine deterministico le sub-lane reali in .staging/lanes/ senza reparse."""
    norm_parent = validate_lane_id(parent_lane)
    root = _resolve_repo_root(repo_root)
    raw_stg = root / ".staging"
    lanes_dir = raw_stg / LANE_CONTAINER_DIRNAME
    if is_reparse_entry(raw_stg) or is_reparse_entry(lanes_dir):
        raise OSError(f"Reparse point vietato nella gerarchia lanes: {lanes_dir}")
    if not lanes_dir.is_dir():
        return []
    found: List[Tuple[str, Path]] = []
    for entry in sorted(lanes_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if is_reparse_entry(entry):
            raise OSError(f"Reparse point vietato su directory sub-lane: {entry}")
        try:
            norm_sub = validate_lane_id(entry.name)
        except ValueError:
            continue
        if is_sublane_of(norm_sub, norm_parent):
            found.append((norm_sub, entry.resolve()))
    return found


def _resolve_explicit_sublanes(root: Path, norm_parent: str, sublane_ids: Sequence[str]) -> List[Tuple[str, Path]]:
    resolved: List[Tuple[str, Path]] = []
    for raw_sub in sorted(set(sublane_ids)):
        norm_sub = validate_lane_id(raw_sub)
        if not is_sublane_of(norm_sub, norm_parent):
            raise ValueError(f"La lane {norm_sub!r} non e sub-lane di {norm_parent!r}.")
        sub_dir, _ = resolve_staging_dir(root, lane_id=norm_sub)
        resolved.append((norm_sub, sub_dir))
    return resolved


def _collect_sublane_changes(sub_id: str, sub_dir: Path) -> Tuple[Dict[str, Path], List[str]]:
    writes: Dict[str, Path] = {}
    if sub_dir.is_dir():
        for w_root, dirs, files in os.walk(sub_dir, followlinks=False):
            w_p = Path(w_root)
            for d in dirs:
                if is_reparse_entry(w_p / d):
                    raise OSError(f"Reparse point vietato in sub-lane {sub_id}: {w_p / d}")
            for fn in files:
                if fn in (".gitkeep", ".deleted_files.json"):
                    continue
                fp = w_p / fn
                if is_reparse_entry(fp):
                    raise OSError(f"Reparse point vietato su file sub-lane {sub_id}: {fp}")
                rel_posix = fp.relative_to(sub_dir).as_posix()
                writes[rel_posix] = fp
    del_manifest = sub_dir / ".deleted_files.json"
    deletes: List[str] = []
    if del_manifest.is_file():
        if is_reparse_entry(del_manifest):
            raise OSError(f"Reparse point vietato su .deleted_files.json di {sub_id}")
        deletes = [str(p).strip().replace("\\", "/").lstrip("./") for p in parse_deleted_files_manifest(del_manifest)]
    return writes, deletes


def _detect_and_collect_disjoint_merge(
    sublanes: List[Tuple[str, Path]]
) -> Tuple[Dict[str, Tuple[str, Path]], List[str], List[Dict[str, Any]]]:
    owner_map: Dict[str, Tuple[str, str]] = {}
    merged_files: Dict[str, Tuple[str, Path]] = {}
    merged_deletes: Dict[str, str] = {}
    conflicts: List[Dict[str, Any]] = []

    for sub_id, sub_dir in sublanes:
        writes, deletes = _collect_sublane_changes(sub_id, sub_dir)
        for rel_p, fp in writes.items():
            key = rel_p.casefold()
            if key in owner_map:
                conflicts.append({"path": rel_p, "lanes": [owner_map[key][0], sub_id], "kind": owner_map[key][1]})
            else:
                owner_map[key] = (sub_id, "write")
                merged_files[rel_p] = (sub_id, fp)
        for del_p in deletes:
            key = del_p.casefold()
            if key in owner_map:
                conflicts.append({"path": del_p, "lanes": [owner_map[key][0], sub_id], "kind": "delete"})
            else:
                owner_map[key] = (sub_id, "delete")
                merged_deletes[key] = del_p

    return merged_files, sorted(merged_deletes.values()), conflicts


def _materialize_tree(dst_dir: Path, merged_files: Dict[str, Tuple[str, Path]], merged_deletes: List[str]) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for rel_p, (_sub_id, src_fp) in merged_files.items():
        dst_fp = dst_dir / rel_p
        dst_fp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_fp, dst_fp)
    if merged_deletes:
        (dst_dir / ".deleted_files.json").write_text(
            json.dumps(merged_deletes, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def _run_default_combined_gate(root: Path, tmp_merge: Path, norm_parent: str) -> Dict[str, Any]:
    from _internal.dast_sandbox_runner.e2e_and_audit import run_staging_shadow_verification

    _ = norm_parent
    return run_staging_shadow_verification(root, staging_dir=tmp_merge)


def _cleanup_after_promote(
    root: Path, norm_parent: str, sublanes: List[Tuple[str, Path]], cleanup_sublanes: bool, release_sublanes: bool
) -> None:
    for sub_id, sub_dir in sublanes:
        if cleanup_sublanes and sub_dir.exists():
            safe_rmtree(sub_dir)
        if release_sublanes:
            try:
                release_lane(root, sub_id, None, force=True)
            except (OSError, ValueError):
                pass
    try:
        release_lane(root, norm_parent, None, force=True)
    except (OSError, ValueError):
        pass


def _promote_parent_tree(
    root: Path, norm_parent: str, *, base_seq: int, milestone: Optional[str], use_commit_train: bool,
    allow_governance_override: bool, governance_override_reason: Optional[str], governance_token: Optional[str],
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]], git_sync: bool, verify_baseline: bool,
    key_path: Optional[Union[str, Path]], queue_path: Optional[Union[str, Path]],
) -> Tuple[Dict[str, Any], bool]:
    if use_commit_train:
        ct_res = run_commit_train_promote(
            repo_root=root, lane_id=norm_parent, base_seq=base_seq, milestone=milestone,
            git_sync=git_sync, verify_baseline=verify_baseline, cleanup_staging=True,
            allow_governance_override=allow_governance_override, governance_override_reason=governance_override_reason,
            governance_token=governance_token, sandbox_report=sandbox_report, key_path=key_path, queue_path=queue_path,
        )
        return ct_res.model_dump(), bool(ct_res.passed)
    promo_res = promote_staging_to_production(
        repo_root=root, lane_id=norm_parent, milestone=milestone, git_sync=git_sync,
        verify_baseline=verify_baseline, cleanup_staging=True, allow_governance_override=allow_governance_override,
        governance_override_reason=governance_override_reason, governance_token=governance_token,
        sandbox_report=sandbox_report, enforce_nonce_replay=True,
    )
    return promo_res, bool(promo_res.get("passed", True))


def _materialize_and_promote_locked(
    root: Path, norm_parent: str, sublanes: List[Tuple[str, Path]],
    merged_files: Dict[str, Tuple[str, Path]], merged_deletes: List[str], *,
    base_seq: int, milestone: Optional[str], use_commit_train: bool,
    cleanup_sublanes: bool, release_sublanes: bool,
    allow_governance_override: bool, governance_override_reason: Optional[str], governance_token: Optional[str],
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]], git_sync: bool, verify_baseline: bool,
    key_path: Optional[Union[str, Path]], queue_path: Optional[Union[str, Path]],
) -> Tuple[Dict[str, Any], bool]:
    with Win32NamedMutex(get_repo_batch_mutex_name(root), timeout_ms=10000, is_path=False):
        parent_stg, _ = resolve_staging_dir(root, lane_id=norm_parent)
        assert_safe_staging_ancestors(root / ".staging", parent_stg, uses_lane=True)
        if parent_stg.exists():
            safe_rmtree(parent_stg)
        _materialize_tree(parent_stg, merged_files, merged_deletes)
        promo_res, promo_ok = _promote_parent_tree(
            root, norm_parent, base_seq=base_seq, milestone=milestone, use_commit_train=use_commit_train,
            allow_governance_override=allow_governance_override, governance_override_reason=governance_override_reason,
            governance_token=governance_token, sandbox_report=sandbox_report, git_sync=git_sync,
            verify_baseline=verify_baseline, key_path=key_path, queue_path=queue_path,
        )
        if promo_ok:
            _cleanup_after_promote(root, norm_parent, sublanes, cleanup_sublanes, release_sublanes)
        return promo_res, promo_ok


def consolidate_sublanes_and_promote(
    repo_root: Optional[Union[str, Path]],
    parent_lane: str,
    *,
    sublane_ids: Optional[Sequence[str]] = None,
    base_seq: int = 0,
    milestone: Optional[str] = None,
    use_commit_train: bool = False,
    run_combined_gate_fn: Optional[Callable[[Path, str], Dict[str, Any]]] = None,
    cleanup_sublanes: bool = True,
    release_sublanes: bool = True,
    allow_governance_override: bool = False,
    governance_override_reason: Optional[str] = None,
    governance_token: Optional[str] = None,
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]] = None,
    git_sync: bool = False,
    verify_baseline: bool = False,
    key_path: Optional[Union[str, Path]] = None,
    queue_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Fonde le sub-lane disgiunte su NVMe, esegue la barriera combinata e promuove in 2PC."""
    root = _resolve_repo_root(repo_root)
    norm_parent = validate_lane_id(parent_lane)
    sublanes = (
        _resolve_explicit_sublanes(root, norm_parent, sublane_ids)
        if sublane_ids is not None
        else discover_sublanes(root, norm_parent)
    )
    sub_names = [sid for sid, _ in sublanes]
    if not sublanes:
        return {"passed": False, "status": "NO_SUBLANES_FOUND", "parent_lane": norm_parent, "sublanes": []}

    merged_files, merged_deletes, conflicts = _detect_and_collect_disjoint_merge(sublanes)
    if conflicts:
        return {"passed": False, "status": "SUBLANE_WRITE_CONFLICT", "parent_lane": norm_parent, "sublanes": sub_names, "conflicts": conflicts}

    tmp_merge = Path(tempfile.mkdtemp(prefix=f"nk_sublane_merge_{norm_parent}_")).resolve()
    try:
        _materialize_tree(tmp_merge, merged_files, merged_deletes)
        gate_res = run_combined_gate_fn(tmp_merge, norm_parent) if run_combined_gate_fn is not None else _run_default_combined_gate(root, tmp_merge, norm_parent)
        if not bool(gate_res.get("passed")):
            return {"passed": False, "status": "COMBINED_GATE_FAILED", "parent_lane": norm_parent, "sublanes": sub_names, "gate_result": gate_res}
        promo_res, promo_ok = _materialize_and_promote_locked(
            root, norm_parent, sublanes, merged_files, merged_deletes,
            base_seq=base_seq, milestone=milestone, use_commit_train=use_commit_train,
            cleanup_sublanes=cleanup_sublanes, release_sublanes=release_sublanes,
            allow_governance_override=allow_governance_override, governance_override_reason=governance_override_reason,
            governance_token=governance_token, sandbox_report=sandbox_report, git_sync=git_sync,
            verify_baseline=verify_baseline, key_path=key_path, queue_path=queue_path,
        )
    finally:
        safe_rmtree(tmp_merge)

    return {
        "passed": promo_ok, "status": "CONSOLIDATED_PROMOTED" if promo_ok else str(promo_res.get("status") or "PROMOTE_FAILED"),
        "parent_lane": norm_parent, "sublanes": sub_names, "merged_files": sorted(merged_files.keys()),
        "gate_result": gate_res, "promote_result": promo_res,
    }

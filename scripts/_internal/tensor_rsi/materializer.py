# -*- coding: utf-8 -*-
"""Isolamento candidati in LOCALAPPDATA/nk_tensor, eval lock-free NVMe e materializzazione con rollback."""

from __future__ import annotations

import inspect
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from _internal.nk_common.io import atomic_write_bytes
from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir
from _internal.nk_common.nvme_mirror_helpers import safe_rmtree
from _internal.nk_common.nvme_storage_guards import ensure_nvme_local_dir
from _internal.nk_common.staging_manifest import (
    compute_staging_manifest_sha256 as _sm_compute_staging_manifest_sha256,
    is_reparse_entry,
)
from _internal.tensor_rsi.helper_ops import scan_cand_tree, validate_segment_id
from _internal.tensor_rsi.ticket_auth import repo_hash12, tensor_named_mutex
from healing_snapshot_rollback import HealingSnapshotManager

T = TypeVar("T")
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_IGNORED_STG_SUFFIXES = (".pyc", ".pyo", ".tmp", ".bak")


def resolve_candidate_dir(session_id: str, candidate_id: str) -> Path:
    """Risolve la directory isolata del candidato rifiutando segmenti . / .. / trailing dot."""
    clean_sid, clean_cid = validate_segment_id(session_id, candidate_id, _ID_RE)
    base = os.environ.get("LOCALAPPDATA", "").strip() or tempfile.gettempdir()
    cand = Path(base) / "nk_tensor" / clean_sid / clean_cid
    if is_reparse_entry(cand):
        raise ValueError(f"Symlink/reparse non consentito per candidato: {cand}")
    return cand.resolve()


def _validate_rel_path(rel_raw: str) -> str:
    """Rifiuta traversal, ADS, drive letter, segmenti '.'/'..' e trailing dot."""
    norm = str(rel_raw or "").replace("\\", "/").strip()
    if not norm or norm.startswith("/") or ":" in norm or "\x00" in norm:
        raise ValueError(f"Percorso candidato non confinato: {rel_raw!r}")
    parts = norm.split("/")
    if not parts or any(p in ("", ".", "..") or p.endswith(".") for p in parts):
        raise ValueError(f"Path traversal o segmento invalido nel candidato: {rel_raw!r}")
    return "/".join(parts)


def _should_exclude_lanes_for_stg(stg: Path, norm_lane: Optional[str]) -> bool:
    return norm_lane is None and stg.name == ".staging"


def compute_staging_manifest_sha256(
    workspace_root: Union[str, Path],
    *,
    lane_id: Optional[str] = None,
    staging_dir: Optional[Path] = None,
) -> str:
    """Delega al SSOT nk_common.staging_manifest su .staging o .staging/lanes/<id>/."""
    stg, norm_lane = resolve_staging_dir(workspace_root, lane_id=lane_id, staging_dir=staging_dir)
    return _sm_compute_staging_manifest_sha256(
        stg, reject_symlinks=True, exclude_lanes=_should_exclude_lanes_for_stg(stg, norm_lane)
    )


def _staging_mutex_name(root: Path, norm_lane: Optional[str]) -> str:
    if norm_lane is not None:
        return f"Local\\NK_TensorStaging_{repo_hash12(root)}_{norm_lane}"
    return f"Local\\NK_TensorStaging_{repo_hash12(root)}"


def collect_candidate_payloads(cand_dir: Path) -> Dict[str, bytes]:
    """Legge i file payload da cand_dir rifiutando symlink o reparse point."""
    if is_reparse_entry(cand_dir):
        raise ValueError(f"Directory candidato symlink/reparse vietata: {cand_dir}")
    if not cand_dir.is_dir():
        return {}
    return scan_cand_tree(cand_dir, _IGNORED_STG_SUFFIXES, is_reparse_entry, _validate_rel_path)


def _prune_empty_parent_dirs(path: Path, stg_dir: Path) -> None:
    cur = path.parent
    stg_res = stg_dir.resolve()
    while cur.resolve() != stg_res and cur.resolve().is_relative_to(stg_res):
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent


def _cleanup_created_staging_targets(
    stg_dir: Path, newly_created: List[Path], restore_status: Dict[str, bool],
) -> None:
    """Rimuove i file creati ex-novo e pota le directory vuote risultanti."""
    for new_fp in newly_created:
        if new_fp.is_file() and not restore_status.get(str(new_fp.resolve()), False):
            try:
                new_fp.unlink(missing_ok=True)
                _prune_empty_parent_dirs(new_fp, stg_dir)
            except OSError:
                pass
    gitkeep = stg_dir / ".gitkeep"
    if stg_dir.is_dir() and not gitkeep.exists():
        try:
            gitkeep.write_text("", encoding="utf-8")
        except OSError:
            pass


def _prepare_candidate_targets(stg_dir: Path, session_id: str, candidate_id: str) -> Tuple[Dict[str, bytes], List[Path]]:
    """Carica e confina in staging/lane i payload di un candidato isolato."""
    cand_dir = resolve_candidate_dir(session_id, candidate_id)
    payloads = collect_candidate_payloads(cand_dir)
    if not payloads:
        raise FileNotFoundError(f"Nessun file candidato trovato in {cand_dir}")
    stg_dir.mkdir(parents=True, exist_ok=True)
    stg_resolved = stg_dir.resolve()
    targets = [(stg_dir / rel).resolve() for rel in payloads]
    for tgt in targets:
        if not tgt.is_relative_to(stg_resolved):
            raise ValueError(f"Target staging fuori confine: {tgt}")
    return payloads, targets


def _write_candidate_payloads(stg_dir: Path, payloads: Dict[str, bytes]) -> None:
    """Scrive atomicamente nella directory staging rifiutando symlink o reparse point."""
    for rel, data in payloads.items():
        ok, err = atomic_write_bytes(
            stg_dir / rel, data, ensure_parent=True, fsync_data=True, reparse_check=is_reparse_entry,
        )
        if not ok:
            raise OSError(f"Scrittura staging fallita su {rel}: {err}")


def _rollback_snapshot(mgr: HealingSnapshotManager, snap_id: str, stg_dir: Path, newly_created: List[Path]) -> bool:
    """Ripristina lo snapshot .staging/; restituisce True solo se tutti i restore sono riusciti."""
    restore_status: Dict[str, bool] = {}
    all_ok = False
    try:
        restore_status = mgr.rollback(snap_id)
        all_ok = isinstance(restore_status, dict) and all(bool(v) for v in restore_status.values())
    finally:
        _cleanup_created_staging_targets(stg_dir, newly_created, restore_status)
    return all_ok


def _eval_with_rollback(
    mgr: HealingSnapshotManager, snap_id: str, root: Path, stg_dir: Path,
    payloads: Dict[str, bytes], newly_created: List[Path], eval_fn: Callable[[], T], pre_sha: str,
    *, lane_id: Optional[str] = None,
) -> Tuple[T, str, Dict[str, Any]]:
    eval_ok = False
    try:
        _write_candidate_payloads(stg_dir, payloads)
        cand_sha = compute_staging_manifest_sha256(root, lane_id=lane_id)
        res = eval_fn()
        eval_ok = True
        return res, cand_sha, {"materialized": sorted(payloads.keys()), "rolled_back": True, "pre_staging_sha256": pre_sha}
    finally:
        if _rollback_snapshot(mgr, snap_id, stg_dir, newly_created):
            mgr.cleanup(snap_id)
        elif eval_ok:
            raise OSError(f"Rollback parziale dello staging fallito: snap_id={snap_id}")


def _copy_stg_to_nvme_eval(stg_dir: Path, nvme_stg: Path, exclude_lanes: bool) -> None:
    """Copia in scratch NVMe la staging/lane corrente saltando reparse e lanes/."""
    if not stg_dir.is_dir() or is_reparse_entry(stg_dir):
        return
    stg_res = stg_dir.resolve()
    for walk_root, dirs, files in os.walk(stg_dir, followlinks=False):
        walk_p = Path(walk_root)
        is_top = exclude_lanes and walk_p.resolve() == stg_res
        dirs[:] = [
            d for d in sorted(dirs)
            if d != "__pycache__" and not is_reparse_entry(walk_p / d)
            and not (is_top and is_lane_container_entry((d,)))
        ]
        for fname in sorted(files):
            if is_top and is_lane_container_entry((fname,)):
                continue
            src = walk_p / fname
            if is_reparse_entry(src) or not src.is_file():
                continue
            dst = nvme_stg / src.relative_to(stg_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _invoke_nvme_eval_fn(eval_fn: Callable[..., T], eval_stg_dir: Path) -> T:
    """Passa staging_dir a eval_fn quando la firma lo accetta, preservando lambda 0-arg."""
    try:
        params = inspect.signature(eval_fn).parameters
    except (TypeError, ValueError):
        return eval_fn()
    if "staging_dir" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return eval_fn(staging_dir=eval_stg_dir)
    if any(p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_POSITIONAL) for p in params.values()):
        return eval_fn(eval_stg_dir)
    return eval_fn()


def _eval_candidate_in_nvme(
    root: Path, stg_dir: Path, norm_lane: Optional[str], session_id: str,
    candidate_id: Optional[str], eval_fn: Callable[..., T],
) -> Tuple[T, str, Dict[str, Any]]:
    """Valuta un candidato su directory NVMe privata senza acquisire mutex di staging."""
    pre_sha = compute_staging_manifest_sha256(root, lane_id=norm_lane)
    if not candidate_id:
        return _invoke_nvme_eval_fn(eval_fn, stg_dir), pre_sha, {
            "materialized": [], "rolled_back": False, "pre_staging_sha256": pre_sha,
            "nvme_lock_free": True, "lane_id": norm_lane,
        }
    payloads = collect_candidate_payloads(resolve_candidate_dir(session_id, candidate_id))
    if not payloads:
        raise FileNotFoundError(f"Nessun file candidato trovato in {resolve_candidate_dir(session_id, candidate_id)}")
    nvme_root = ensure_nvme_local_dir(Path(tempfile.gettempdir()) / "nk_tensor_eval", "nk_tensor_eval")
    nvme_base = nvme_root / f"eval_{uuid.uuid4().hex[:10]}"
    nvme_stg = nvme_base / ".staging"
    nvme_stg.mkdir(parents=True, exist_ok=True)
    try:
        _copy_stg_to_nvme_eval(stg_dir, nvme_stg, _should_exclude_lanes_for_stg(stg_dir, norm_lane))
        _write_candidate_payloads(nvme_stg, payloads)
        cand_sha = _sm_compute_staging_manifest_sha256(nvme_stg, reject_symlinks=True, exclude_lanes=False)
        res = _invoke_nvme_eval_fn(eval_fn, nvme_stg)
        return res, cand_sha, {
            "materialized": sorted(payloads.keys()), "rolled_back": True,
            "pre_staging_sha256": pre_sha, "nvme_lock_free": True, "lane_id": norm_lane,
        }
    finally:
        safe_rmtree(nvme_base)


def _eval_candidate_in_staging(
    root: Path, stg_dir: Path, norm_lane: Optional[str], session_id: str,
    candidate_id: Optional[str], eval_fn: Callable[[], T], snapshot_base_dir: Optional[Path],
) -> Tuple[T, str, Dict[str, Any]]:
    with tensor_named_mutex(_staging_mutex_name(root, norm_lane)):
        pre_sha = compute_staging_manifest_sha256(root, lane_id=norm_lane)
        if not candidate_id:
            return eval_fn(), compute_staging_manifest_sha256(root, lane_id=norm_lane), {
                "materialized": [], "rolled_back": False, "pre_staging_sha256": pre_sha,
            }
        payloads, targets = _prepare_candidate_targets(stg_dir, session_id, candidate_id)
        newly_created = [tgt for tgt in targets if not tgt.is_file()]
        mgr = HealingSnapshotManager(base_temp_dir=snapshot_base_dir or (Path(tempfile.gettempdir()) / "nk_tensor_snapshots"))
        snap_id = mgr.create_snapshot(targets)
        return _eval_with_rollback(
            mgr, snap_id, root, stg_dir, payloads, newly_created, eval_fn, pre_sha, lane_id=norm_lane
        )


def _should_use_nvme_eval(norm_lane: Optional[str], eval_in_nvme: Optional[bool]) -> bool:
    if eval_in_nvme is not None:
        return bool(eval_in_nvme)
    return norm_lane is not None


def materialize_and_evaluate(
    workspace_root: Union[str, Path], session_id: str, candidate_id: Optional[str],
    eval_fn: Callable[[], T], *, snapshot_base_dir: Optional[Path] = None,
    lane_id: Optional[str] = None, eval_in_nvme: Optional[bool] = None,
) -> Tuple[T, str, Dict[str, Any]]:
    """Valuta un candidato in NVMe lock-free per lane oppure in .staging/ con rollback atomico."""
    root = Path(workspace_root).resolve()
    stg_dir, norm_lane = resolve_staging_dir(root, lane_id=lane_id)
    if _should_use_nvme_eval(norm_lane, eval_in_nvme):
        return _eval_candidate_in_nvme(root, stg_dir, norm_lane, session_id, candidate_id, eval_fn)
    return _eval_candidate_in_staging(root, stg_dir, norm_lane, session_id, candidate_id, eval_fn, snapshot_base_dir)


def _commit_with_rollback(
    mgr: HealingSnapshotManager, snap_id: str, root: Path, stg_dir: Path,
    payloads: Dict[str, bytes], expected_sha: str, newly_created: List[Path],
    *, lane_id: Optional[str] = None,
) -> str:
    rb_needed, rb_ok = False, True
    try:
        _write_candidate_payloads(stg_dir, payloads)
        actual_sha = compute_staging_manifest_sha256(root, lane_id=lane_id)
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(f"Staging manifest SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")
        return actual_sha
    except Exception:
        rb_needed = True
        rb_ok = _rollback_snapshot(mgr, snap_id, stg_dir, newly_created)
        raise
    finally:
        if not rb_needed or rb_ok:
            mgr.cleanup(snap_id)


def _assert_pre_staging_unchanged(root: Path, norm_lane: Optional[str], pre_staging_sha256: str) -> None:
    if pre_staging_sha256 and compute_staging_manifest_sha256(root, lane_id=norm_lane) != pre_staging_sha256:
        raise ValueError("TOCTOU_STAGING_MISMATCH: .staging/ modificata prima del commit candidato.")


def commit_accepted_candidate(
    workspace_root: Union[str, Path], session_id: str, candidate_id: str,
    expected_manifest_sha256: str, *, pre_staging_sha256: str = "",
    snapshot_base_dir: Optional[Path] = None, lane_id: Optional[str] = None,
) -> str:
    """Materializza in .staging/ o lane il candidato accettato sotto Mutex con check TOCTOU."""
    root = Path(workspace_root).resolve()
    stg_dir, norm_lane = resolve_staging_dir(root, lane_id=lane_id)
    with tensor_named_mutex(_staging_mutex_name(root, norm_lane)):
        payloads, targets = _prepare_candidate_targets(stg_dir, session_id, candidate_id)
        _assert_pre_staging_unchanged(root, norm_lane, pre_staging_sha256)
        newly_created = [tgt for tgt in targets if not tgt.is_file()]
        mgr = HealingSnapshotManager(base_temp_dir=snapshot_base_dir or (Path(tempfile.gettempdir()) / "nk_tensor_snapshots"))
        snap_id = mgr.create_snapshot(targets)
        return _commit_with_rollback(
            mgr, snap_id, root, stg_dir, payloads, expected_manifest_sha256, newly_created, lane_id=norm_lane
        )

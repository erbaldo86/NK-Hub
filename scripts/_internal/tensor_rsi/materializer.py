# -*- coding: utf-8 -*-
"""Isolamento candidati in LOCALAPPDATA/nk_tensor e materializzazione con rollback finally."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from _internal.nk_common.io import atomic_write_bytes
from _internal.nk_common.staging_manifest import (
    compute_staging_manifest_sha256 as _sm_compute_staging_manifest_sha256, is_reparse_entry,
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


def compute_staging_manifest_sha256(workspace_root: Union[str, Path]) -> str:
    """Delega al SSOT nk_common.staging_manifest su <workspace_root>/.staging."""
    return _sm_compute_staging_manifest_sha256(Path(workspace_root) / ".staging", reject_symlinks=True)


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
    """Carica e confina in .staging/ i payload di un candidato isolato."""
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
    """Scrive atomicamente in .staging/ rifiutando symlink o reparse point."""
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
) -> Tuple[T, str, Dict[str, Any]]:
    eval_ok = False
    try:
        _write_candidate_payloads(stg_dir, payloads)
        cand_sha = compute_staging_manifest_sha256(root)
        res = eval_fn()
        eval_ok = True
        return res, cand_sha, {"materialized": sorted(payloads.keys()), "rolled_back": True, "pre_staging_sha256": pre_sha}
    finally:
        if _rollback_snapshot(mgr, snap_id, stg_dir, newly_created):
            mgr.cleanup(snap_id)
        elif eval_ok:
            raise OSError(f"Rollback parziale dello staging fallito: snap_id={snap_id}")


def materialize_and_evaluate(
    workspace_root: Union[str, Path], session_id: str, candidate_id: Optional[str],
    eval_fn: Callable[[], T], *, snapshot_base_dir: Optional[Path] = None,
) -> Tuple[T, str, Dict[str, Any]]:
    """Materializza un candidato in .staging/ sotto Mutex e garantisce rollback atomico."""
    root = Path(workspace_root).resolve()
    stg_dir = root / ".staging"
    with tensor_named_mutex(f"Local\\NK_TensorStaging_{repo_hash12(root)}"):
        pre_sha = compute_staging_manifest_sha256(root)
        if not candidate_id:
            return eval_fn(), compute_staging_manifest_sha256(root), {"materialized": [], "rolled_back": False, "pre_staging_sha256": pre_sha}
        payloads, targets = _prepare_candidate_targets(stg_dir, session_id, candidate_id)
        newly_created = [tgt for tgt in targets if not tgt.is_file()]
        mgr = HealingSnapshotManager(base_temp_dir=snapshot_base_dir or (Path(tempfile.gettempdir()) / "nk_tensor_snapshots"))
        snap_id = mgr.create_snapshot(targets)
        return _eval_with_rollback(mgr, snap_id, root, stg_dir, payloads, newly_created, eval_fn, pre_sha)


def _commit_with_rollback(
    mgr: HealingSnapshotManager, snap_id: str, root: Path, stg_dir: Path,
    payloads: Dict[str, bytes], expected_sha: str, newly_created: List[Path],
) -> str:
    rb_needed, rb_ok = False, True
    try:
        _write_candidate_payloads(stg_dir, payloads)
        actual_sha = compute_staging_manifest_sha256(root)
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


def commit_accepted_candidate(
    workspace_root: Union[str, Path], session_id: str, candidate_id: str,
    expected_manifest_sha256: str, *, pre_staging_sha256: str = "", snapshot_base_dir: Optional[Path] = None,
) -> str:
    """Materializza in .staging/ il candidato accettato sotto Mutex con check TOCTOU."""
    root = Path(workspace_root).resolve()
    stg_dir = root / ".staging"
    with tensor_named_mutex(f"Local\\NK_TensorStaging_{repo_hash12(root)}"):
        payloads, targets = _prepare_candidate_targets(stg_dir, session_id, candidate_id)
        if pre_staging_sha256 and compute_staging_manifest_sha256(root) != pre_staging_sha256:
            raise ValueError("TOCTOU_STAGING_MISMATCH: .staging/ modificata prima del commit candidato.")
        newly_created = [tgt for tgt in targets if not tgt.is_file()]
        mgr = HealingSnapshotManager(base_temp_dir=snapshot_base_dir or (Path(tempfile.gettempdir()) / "nk_tensor_snapshots"))
        snap_id = mgr.create_snapshot(targets)
        return _commit_with_rollback(mgr, snap_id, root, stg_dir, payloads, expected_manifest_sha256, newly_created)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validatori JSON, cleanup staging, audit override, ratchet baseline e scansione canonica."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from _internal.nk_common.lane_paths import is_lane_container_entry

from . import constants as _consts
from .constants import (
    TwoPhaseCommitError,
    compute_sha256,
    validate_override_reason,  # noqa: F401
)
from .governance_auth import authorize_governance_override  # noqa: F401
from .io_and_paths import (
    _is_reparse_point,
    _unlink_with_retry,
    _win_long_path,
)
from .mutex import Win32NamedMutex


def _collect_staging_json_candidates(
    staging_dir: Union[str, Path], staging_files: Optional[List[Path]]
) -> List[Path]:
    """Raccoglie i candidati .json in staging escludendo lanes/ in modalita legacy."""
    if staging_files is not None:
        return staging_files
    stg_root = Path(staging_dir).resolve()
    excl_lanes = stg_root.name == ".staging"
    out: List[Path] = []
    for p in stg_root.rglob("*.json"):
        if not p.is_file() or "__pycache__" in p.parts or p.suffix.lower() in _consts.IGNORED_STAGING_SUFFIXES:
            continue
        if excl_lanes and is_lane_container_entry(p.relative_to(stg_root).parts):
            continue
        out.append(p)
    return out


def validate_staging_json_files(
    staging_dir: Union[str, Path],
    staging_files: Optional[List[Path]] = None,
) -> Tuple[bool, List[str]]:
    """Valida la sintassi JSON (incluso utf-8-sig) e l'assenza di U+FFFD nei file .json di staging."""
    candidates = _collect_staging_json_candidates(staging_dir, staging_files)
    errors: List[str] = []
    for fpath in candidates:
        if fpath.suffix.lower() != ".json":
            continue
        try:
            raw_bytes = _win_long_path(fpath).read_bytes()
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as ude:
            errors.append(f"{fpath.name}: codifica UTF-8 invalida ({ude})")
            continue
        except Exception as exc:
            errors.append(f"{fpath.name}: errore lettura file ({exc})")
            continue

        if "\ufffd" in text:
            errors.append(
                f"{fpath.name}: rilevato carattere di sostituzione U+FFFD vietato"
            )
        try:
            json.loads(text)
        except Exception as exc:
            errors.append(f"{fpath.name}: sintassi JSON invalida ({exc})")

    return len(errors) == 0, errors


def _unlink_residual_staging_files(staging_dir: Path, excl_lanes: bool) -> None:
    """Rimuove i residui temporanei/__pycache__ in staging preservando lanes/ in legacy."""
    for res_file in list(staging_dir.rglob("*")):
        try:
            if excl_lanes and is_lane_container_entry(res_file.relative_to(staging_dir).parts):
                continue
            if not res_file.is_file() or res_file.name == ".gitkeep":
                continue
            if "__pycache__" in res_file.parts or res_file.suffix.lower() in _consts.IGNORED_STAGING_SUFFIXES:
                _unlink_with_retry(res_file)
        except OSError:
            pass


def _rmdir_empty_staging_dirs(staging_dir: Path, excl_lanes: bool) -> None:
    """Elimina le directory vuote di staging preservando lanes/ in legacy."""
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


def _cleanup_promoted_staging(
    staging_dir: Path,
    promoted_files: List[Path],
    deleted_manifest: Optional[Path] = None,
) -> None:
    """Rimuove i file promossi da .staging/ (preservando lanes/ in legacy) e ripristina .gitkeep."""
    excl_lanes = Path(staging_dir).name == ".staging"
    for stg_file in promoted_files:
        try:
            if stg_file.exists() and stg_file.name != ".gitkeep":
                _unlink_with_retry(stg_file)
        except OSError:
            pass
    if deleted_manifest is not None and deleted_manifest.exists():
        try:
            _unlink_with_retry(deleted_manifest)
        except OSError:
            pass
    _unlink_residual_staging_files(staging_dir, excl_lanes)
    _rmdir_empty_staging_dirs(staging_dir, excl_lanes)
    gitkeep = staging_dir / ".gitkeep"
    if not gitkeep.exists():
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)
            gitkeep.write_text("", encoding="utf-8")
        except OSError:
            pass


def _collect_targeted_pycache_dirs(root: Path, touched_rel_paths: Sequence[str]) -> List[Path]:
    """Individua solo le cartelle __pycache__ nei moduli toccati dai file .py."""
    dirs: List[Path] = []
    seen: set[Path] = set()
    for rel in touched_rel_paths:
        norm = str(rel).replace("\\", "/").strip().lstrip("/")
        if not norm.lower().endswith(".py"):
            continue
        pc_dir = (root / norm).parent / "__pycache__"
        if pc_dir not in seen and pc_dir.is_dir() and not _is_reparse_point(pc_dir):
            seen.add(pc_dir)
            dirs.append(pc_dir)
    return dirs


def _remove_pycache_dirs(pycache_dirs: List[Path]) -> None:
    """Rimuove le directory __pycache__ indicate con retry su Windows."""
    for pc_dir in sorted(pycache_dirs, key=lambda p: len(p.parts), reverse=True):
        for attempt in range(_consts.RETRY_ATTEMPTS_IO):
            pc_lp = _win_long_path(pc_dir)
            if not pc_lp.exists():
                break
            shutil.rmtree(pc_lp, ignore_errors=True)
            if pc_lp.exists() and attempt + 1 < _consts.RETRY_ATTEMPTS_IO:
                time.sleep(_consts.RETRY_DELAY_SEC_IO)


def _purge_production_bytecode(
    root: Path, touched_rel_paths: Optional[Sequence[str]] = None
) -> None:
    """Rimuove bytecode .pyc/.pyo in scripts/ e tests/, limitando la scansione ai moduli toccati."""
    if touched_rel_paths is not None:
        _remove_pycache_dirs(_collect_targeted_pycache_dirs(root, touched_rel_paths))
        return
    for rel_dir in ("scripts", "tests"):
        base_dir = root / rel_dir
        base_lp = _win_long_path(base_dir)
        if not base_lp.exists() or not base_lp.is_dir() or _is_reparse_point(base_dir):
            continue
        pycache_dirs: List[Path] = []
        for item in list(base_dir.rglob("*")):
            try:
                if _is_reparse_point(item):
                    continue
                if item.is_file() and item.suffix.lower() in (".pyc", ".pyo"):
                    _unlink_with_retry(item)
                elif item.is_dir() and item.name == "__pycache__":
                    pycache_dirs.append(item)
            except OSError:
                pass
        _remove_pycache_dirs(pycache_dirs)


def record_session_anchor_commit(
    repo_root: Union[str, Path],
    milestone_id: str,
    committed_files: List[Dict[str, Any]],
    deleted_files: Optional[List[str]] = None,
) -> None:
    """Registra una voce di commit ufficiale in session_anchor.jsonl sotto Win32NamedMutex."""
    root = Path(repo_root).resolve()
    anchor_dir = root / "nk_tracking" / "anchor"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    anchor_file = anchor_dir / "session_anchor.jsonl"
    committed_names = [f["relative_path"] for f in committed_files]
    del_list = list(deleted_files or [])
    eff_ms = milestone_id or "2PC_PROMOTE"
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = {
        "timestamp": now_iso, "ts": now_iso, "event": "2PC_ATOMIC_PROMOTION", "act": "SYNC",
        "milestone": eff_ms, "milestone_id": eff_ms, "target": eff_ms,
        "node": "NK-Orchestrator", "skill": "NK-Orchestrator",
        "promoted_files_count": len(committed_files), "committed_files": committed_names,
        "deleted_files": del_list,
        "summary": f"Win32 2PC Atomic Promotion ({eff_ms}): {len(committed_files)} files promoted.",
        "detail": f"Atomic 2PC promotion to production. {len(committed_files)} files committed, {len(del_list)} deleted.",
        "status": "OK",
    }
    with Win32NamedMutex(anchor_file, timeout_ms=5000):
        with open(_win_long_path(anchor_file), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())


def record_governance_override_audit(
    repo_root: Union[str, Path],
    milestone_id: str,
    reason: str,
    overridden_paths: List[str],
) -> Dict[str, Any]:
    """Registra una voce firmata SHA-256 per ogni override di governance in session_anchor.jsonl."""
    root = Path(repo_root).resolve()
    anchor_dir = root / "nk_tracking" / "anchor"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    anchor_file = anchor_dir / "session_anchor.jsonl"
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload: Dict[str, Any] = {
        "timestamp": now_iso, "ts": now_iso, "event": "GOVERNANCE_OVERRIDE", "act": "OVERRIDE_AUDIT",
        "milestone_id": milestone_id or "2PC_PROMOTE",
        "override_reason": str(reason).strip(),
        "overridden_paths": sorted(set(overridden_paths)), "pid": os.getpid(),
    }
    payload["audit_sha256"] = compute_sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    with Win32NamedMutex(anchor_file, timeout_ms=5000):
        with open(_win_long_path(anchor_file), "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    return payload


from _internal.win32_2pc_engine.guards_ratchet import (  # noqa: E402, F401
    _extract_dual_schema_baseline,
    _scan_staging_canonical,
    _verify_quality_baseline_ratchet,
)

from _internal.win32_2pc_engine.guards_sandbox import (  # noqa: E402, F401
    _BLOCKED_SANDBOX_STATUSES,
    _POSITIVE_SANDBOX_OUTCOMES,
    _POSITIVE_SANDBOX_STATUSES,
    _assert_sandbox_report_payload_valid,
    _enforce_batch_baseline_ratchet,
    _has_positive_sandbox_verdict,
    _has_sandbox_failure_flag,
    _validate_sandbox_evidence_in_batch,
    validate_sandbox_report_not_dry_run,
)

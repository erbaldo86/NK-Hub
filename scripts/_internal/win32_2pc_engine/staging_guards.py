#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validatori JSON, cleanup staging, ratchet quality_baseline e scansione canonica."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from . import constants as _consts
from .constants import TwoPhaseCommitError
from .io_and_paths import (
    _assert_no_external_reparse,
    _is_reparse_point,
    _unlink_with_retry,
    _win_long_path,
)
from .mutex import Win32NamedMutex


def validate_staging_json_files(
    staging_dir: Union[str, Path],
    staging_files: Optional[List[Path]] = None,
) -> Tuple[bool, List[str]]:
    """Valida la sintassi JSON (incluso utf-8-sig) e l'assenza di U+FFFD nei file .json di staging."""
    stg_root = Path(staging_dir).resolve()
    candidates = (
        staging_files
        if staging_files is not None
        else [
            p
            for p in stg_root.rglob("*.json")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix.lower() not in _consts.IGNORED_STAGING_SUFFIXES
        ]
    )
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


def _cleanup_promoted_staging(
    staging_dir: Path,
    promoted_files: List[Path],
    deleted_manifest: Optional[Path] = None,
) -> None:
    """Rimuove i file promossi da .staging/ e ripristina il file sentinella .gitkeep."""
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

    for res_file in list(staging_dir.rglob("*")):
        try:
            if not res_file.is_file() or res_file.name == ".gitkeep":
                continue
            if (
                "__pycache__" in res_file.parts
                or res_file.suffix.lower() in _consts.IGNORED_STAGING_SUFFIXES
            ):
                _unlink_with_retry(res_file)
        except OSError:
            pass

    all_dirs = sorted(
        (d for d in staging_dir.rglob("*") if d.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for d in all_dirs:
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    gitkeep = staging_dir / ".gitkeep"
    if not gitkeep.exists():
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)
            gitkeep.write_text("", encoding="utf-8")
        except OSError:
            pass


def _purge_production_bytecode(root: Path) -> None:
    """Rimuove file bytecode .pyc/.pyo e cartelle __pycache__ dentro scripts/ e tests/."""
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
        import shutil

        for pc_dir in sorted(pycache_dirs, key=lambda p: len(p.parts), reverse=True):
            for attempt in range(_consts.RETRY_ATTEMPTS_IO):
                pc_lp = _win_long_path(pc_dir)
                if not pc_lp.exists():
                    break
                shutil.rmtree(pc_lp, ignore_errors=True)
                if pc_lp.exists() and attempt + 1 < _consts.RETRY_ATTEMPTS_IO:
                    time.sleep(_consts.RETRY_DELAY_SEC_IO)


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
        "timestamp": now_iso,
        "ts": now_iso,
        "event": "2PC_ATOMIC_PROMOTION",
        "act": "SYNC",
        "milestone": eff_ms,
        "milestone_id": eff_ms,
        "target": eff_ms,
        "node": "NK-Orchestrator",
        "skill": "NK-Orchestrator",
        "promoted_files_count": len(committed_files),
        "committed_files": committed_names,
        "deleted_files": del_list,
        "summary": (
            f"Win32 2PC Atomic Promotion ({eff_ms}): "
            f"{len(committed_files)} files promoted."
        ),
        "detail": (
            f"Atomic 2PC promotion to production. "
            f"{len(committed_files)} files committed, {len(del_list)} deleted."
        ),
        "status": "OK",
    }
    with Win32NamedMutex(anchor_file, timeout_ms=5000):
        with open(_win_long_path(anchor_file), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())


from _internal.win32_2pc_engine.guards_ratchet import (
    _extract_dual_schema_baseline,
    _scan_staging_canonical,
    _verify_quality_baseline_ratchet,
)

def validate_sandbox_report_not_dry_run(
    report: Path | str | Dict[str, Any],
) -> None:
    """Blocca la promozione 2PC se il report sandbox risulta eseguito in dry-run."""
    if isinstance(report, (str, Path)):
        report_path = Path(report)
        if not report_path.is_file():
            raise TwoPhaseCommitError(f"Report sandbox assente: {report_path}")
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        payload = report

    if not isinstance(payload, dict):
        raise TwoPhaseCommitError("Report sandbox non valido: atteso dizionario JSON.")

    status_val = str(payload.get("status", "")).upper()
    if payload.get("is_dry_run") or payload.get("dry_run") or "DRY_RUN" in status_val:
        raise TwoPhaseCommitError(
            "Promozione bloccata: report sandbox in modalita dry-run non certificabile."
        )

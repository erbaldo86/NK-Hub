# -*- coding: utf-8 -*-
"""Modelli Pydantic v2 strict e primitive I/O atomiche per healing_snapshot_rollback."""

from __future__ import annotations

import base64
import hashlib
import re
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.io import atomic_write_bytes, atomic_write_text

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)

_FACADE_MOD_NAMES: Tuple[str, ...] = (
    "healing_snapshot_rollback",
    "scripts.healing_snapshot_rollback",
)
_MANIFEST_LOCK = threading.Lock()
_SNAPSHOT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


class FitnessVerdict(str, Enum):
    """Esiti discreti dello Strict Monotonic Fitness Gate."""

    PASSED = "PASSED"
    IMPROVED = "IMPROVED"
    REFACTOR_EQUIVALENT = "REFACTOR_EQUIVALENT"
    REGRESSION = "REGRESSION"
    NEUTRAL = "NEUTRAL"


class FitnessReport(BaseModel):
    """Valutazione dell'esito dei test rispetto al baseline precedente."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    verdict: FitnessVerdict
    current_passed: int
    current_failed: int
    prev_passed: int
    prev_failed: int
    exit_code: int
    reason: str


class FileSnapshot(BaseModel):
    """Contenuto binario e stato SHA-256 di un singolo file tracciato."""

    model_config = ConfigDict(strict=True, extra="forbid")

    relative_path: str
    absolute_path: str
    sha256_hash: str
    content: str = ""
    content_b64: str = ""
    exists_before: bool = True


class SnapshotBundle(BaseModel):
    """Pacchetto contenente gli snapshot di tutti i file target tracciati."""

    model_config = ConfigDict(strict=True, extra="forbid")

    snapshot_id: str
    created_at_epoch: float = Field(default_factory=time.time)
    temp_backup_dir: str
    files: Dict[str, FileSnapshot] = Field(default_factory=dict)


def _atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    """Scrive byte grezzi su disco in modo atomico fallendo esplicitamente su errore."""
    ok, err = atomic_write_bytes(
        target_path, payload, ensure_parent=True, fsync_data=True
    )
    if not ok:
        raise OSError(err or f"Atomic write failed for {target_path}")


def _atomic_write_text(target_path: Path, payload: str) -> None:
    """Scrive una stringa UTF-8 su disco in modo atomico tramite nk_common.io."""
    ok, err = atomic_write_text(target_path, payload)
    if not ok:
        raise OSError(err or f"Atomic text write failed for {target_path}")


def _validate_snapshot_id(snapshot_id: str) -> str:
    """Valida snapshot_id contro regex strict [a-zA-Z0-9_-]{1,80}."""
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError(f"Invalid snapshot ID format: {snapshot_id!r}")
    return snapshot_id


def _check_regression_reason(
    current_passed: int,
    current_failed: int,
    prev_passed: int,
    prev_failed: int,
    exit_code: int,
) -> Optional[str]:
    """Restituisce il motivo della regressione o errore infrastrutturale, oppure None."""
    curr_total = current_passed + current_failed
    prev_total = prev_passed + prev_failed
    if curr_total <= 0:
        return "Zero tests executed (0/0 test run rejected)."
    if exit_code < 0 or exit_code >= 2 or (exit_code != 0 and current_failed == 0):
        return f"Non-zero error exit code ({exit_code}) with {current_failed} failed tests."
    if curr_total < prev_total:
        return f"Total test count decreased from {prev_total} to {curr_total}."
    if current_passed < prev_passed:
        return f"Passed tests decreased from {prev_passed} to {current_passed}."
    if current_failed > prev_failed:
        return f"Failed tests increased from {prev_failed} to {current_failed}."
    return None


def _check_equivalent_green(
    allow_equivalent_green: bool,
    exit_code: int,
    current_passed: int,
    current_failed: int,
    prev_passed: int,
    prev_failed: int,
    delta_cc: int,
    ast_sast_violations: int,
) -> bool:
    """Verifica le condizioni per accettare un refactoring equivalente completamente verde."""
    return (
        allow_equivalent_green
        and exit_code == 0
        and current_failed == 0
        and prev_failed == 0
        and current_passed == prev_passed
        and current_passed > 0
        and delta_cc <= 0
        and ast_sast_violations == 0
    )


def _verify_restored_file(
    target_path: Path,
    file_snap: FileSnapshot,
    raw_bytes: bytes,
) -> bool:
    """Verifica l'integrita SHA-256 post-scrittura del file ripristinato da snapshot."""
    if not file_snap.exists_before:
        return not target_path.exists()
    if not (target_path.exists() and target_path.is_file()):
        return False
    disk_bytes = target_path.read_bytes()
    if file_snap.sha256_hash:
        return hashlib.sha256(disk_bytes).hexdigest() == file_snap.sha256_hash
    return disk_bytes == raw_bytes


def _restore_single_entry(
    target_path: Path,
    file_snap: FileSnapshot,
    temp_backup_dir: str,
    write_bin: Any,
) -> bool:
    """Ripristina e verifica un singolo file di snapshot restituendo True solo se integro."""
    try:
        if file_snap.exists_before:
            prefix = hashlib.sha256(str(target_path).encode("utf-8")).hexdigest()[:8]
            backup_src = Path(temp_backup_dir) / f"{prefix}_{file_snap.relative_path}"
            if file_snap.content_b64:
                raw_bytes = base64.b64decode(file_snap.content_b64.encode("ascii"))
            elif backup_src.exists() and backup_src.is_file():
                raw_bytes = backup_src.read_bytes()
            else:
                raw_bytes = file_snap.content.encode("utf-8")
            write_bin(target_path, raw_bytes)
            return _verify_restored_file(target_path, file_snap, raw_bytes)
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        return _verify_restored_file(target_path, file_snap, b"")
    except Exception:
        return False

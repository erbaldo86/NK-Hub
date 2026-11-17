# -*- coding: utf-8 -*-
"""Modelli Pydantic v2 strict e primitive I/O atomiche per healing_snapshot_rollback."""

from __future__ import annotations

import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Tuple

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


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


class FitnessVerdict(str, Enum):
    """Esiti discreti dello Strict Monotonic Fitness Gate."""

    PASSED = "PASSED"
    IMPROVED = "IMPROVED"
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

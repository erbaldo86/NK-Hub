# -*- coding: utf-8 -*-
"""
Facciata compatibile per i Dual Ledgers di NK Hub Generation 1.0.0-Generation.
Re-esporta i DTO L0 puri da dual_ledgers_models e carica il runtime I/O via _LAZY_EXPORT_MAP.
"""

from __future__ import annotations

import ctypes
import importlib
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from schemas.dual_ledgers_models import (
    EventType,
    ProgressEvent,
    TaskDAGNode,
    TaskStatus,
    canonical_json_bytes,
    sha256_hex,
)

__nk_domain__: str = "DOM-01"
__nk_role__: str = "facade"

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "PIDFileLock": ("_internal.nk_common.ledger_runtime", "PIDFileLock"),
    "TaskLedger": ("_internal.nk_common.ledger_runtime", "TaskLedger"),
    "ProgressLedger": ("_internal.nk_common.ledger_runtime", "ProgressLedger"),
    "_kernel32": ("_internal.nk_common.ledger_runtime", "_kernel32"),
    "PROCESS_QUERY_LIMITED_INFORMATION": (
        "_internal.nk_common.ledger_runtime",
        "PROCESS_QUERY_LIMITED_INFORMATION",
    ),
    "STILL_ACTIVE": ("_internal.nk_common.ledger_runtime", "STILL_ACTIVE"),
    "ERROR_ACCESS_DENIED": (
        "_internal.nk_common.ledger_runtime",
        "ERROR_ACCESS_DENIED",
    ),
    "INVALID_HANDLE_VALUE": (
        "_internal.nk_common.ledger_runtime",
        "INVALID_HANDLE_VALUE",
    ),
}

__all__ = [
    "TaskStatus",
    "EventType",
    "canonical_json_bytes",
    "sha256_hex",
    "TaskDAGNode",
    "ProgressEvent",
    "PIDFileLock",
    "TaskLedger",
    "ProgressLedger",
]


def _ensure_scripts_overlay_paths() -> None:
    """Assicura che .staging/scripts e scripts/ siano visibili con pkgutil.extend_path."""
    scripts_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    parent_dir = os.path.dirname(scripts_dir)
    prod_scripts = (
        os.path.join(os.path.dirname(parent_dir), "scripts")
        if os.path.basename(parent_dir) == ".staging"
        else scripts_dir
    )
    for cand_str in (prod_scripts, scripts_dir):
        if os.path.isdir(cand_str) and cand_str not in sys.path:
            sys.path.insert(0, cand_str)
    internal_pkg = sys.modules.get("_internal")
    if internal_pkg is not None and hasattr(internal_pkg, "__path__"):
        internal_pkg.__path__ = pkgutil.extend_path(
            internal_pkg.__path__, "_internal"
        )


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli runtime da _internal.nk_common.ledger_runtime."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    _ensure_scripts_overlay_paths()
    mod_name, attr_name = target
    mod = importlib.import_module(mod_name)
    val = getattr(mod, attr_name)
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Espone i simboli pubblici inclusi gli export lazy."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore canonico di snapshot binari di staging e rollback transazionale in NK Hub Generation 1.0.0-Generation.
Modulo: scripts/healing_snapshot_rollback.py.
@domain_id: DOM-03
Ospita le primitive canoniche di snapshot binario, Strict Monotonic Fitness Gate e rollback atomico.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

__nk_domain__: str = "DOM-03"
__nk_role__: str = "facade"
__nk_facade__: str = "healing_snapshot_rollback"

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc
    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
init_nk_facade(__file__, pkg="healing_snapshot_rollback")


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI senza importare Pydantic su --help."""
    parser = argparse.ArgumentParser(description="NK Hub Generation Staging Snapshot & Rollback Engine")
    parser.add_argument("--create", nargs="+", help="Crea lo snapshot dei file specificati")
    parser.add_argument("--rollback", type=str, help="Ripristina lo snapshot con l'ID specificato")
    parser.add_argument("--cleanup", action="store_true", help="Rimuove tutti gli snapshot temporanei")
    return parser


_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "_MANIFEST_LOCK": ("_internal.healing_snapshot_rollback.models_and_io", "_MANIFEST_LOCK"),
    "_scripts_dir": ("_internal.healing_snapshot_rollback.models_and_io", "_scripts_dir"),
    "_root_dir": ("_internal.healing_snapshot_rollback.models_and_io", "_root_dir"),
    "FitnessVerdict": ("_internal.healing_snapshot_rollback.models_and_io", "FitnessVerdict"),
    "FitnessReport": ("_internal.healing_snapshot_rollback.models_and_io", "FitnessReport"),
    "FileSnapshot": ("_internal.healing_snapshot_rollback.models_and_io", "FileSnapshot"),
    "SnapshotBundle": ("_internal.healing_snapshot_rollback.models_and_io", "SnapshotBundle"),
    "_atomic_write_bytes": ("_internal.healing_snapshot_rollback.models_and_io", "_atomic_write_bytes"),
    "_atomic_write_text": ("_internal.healing_snapshot_rollback.models_and_io", "_atomic_write_text"),
    "HealingSnapshotManager": ("_internal.healing_snapshot_rollback.manager_and_cli", "HealingSnapshotManager"),
    "atomic_write_bytes": ("_internal.nk_common.io", "atomic_write_bytes"),
    "atomic_write_text": ("_internal.nk_common.io", "atomic_write_text"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}

__all__ = [
    "_MANIFEST_LOCK",
    "FitnessVerdict",
    "FitnessReport",
    "FileSnapshot",
    "SnapshotBundle",
    "HealingSnapshotManager",
    "_atomic_write_bytes",
    "_atomic_write_text",
    "main",
]


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.healing_snapshot_rollback."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="healing_snapshot_rollback")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main() -> int:
    """Punto di ingresso CLI per il gestore snapshot e rollback di NK Hub Generation."""
    parser = _build_cli_parser()
    args = parser.parse_args()
    if not (args.create or args.rollback or args.cleanup):
        parser.print_help()
        return 0
    init_nk_facade(__file__, pkg="healing_snapshot_rollback")
    return importlib.import_module(
        "_internal.healing_snapshot_rollback.manager_and_cli"
    )._run_cli_args(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bridge Pytest e localizzazione SBFL Ochiai per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/sbfl_pytest_bridge.py.
@domain_id: DOM-04
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__nk_domain__: str = "DOM-04"
__nk_role__: str = "facade"

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS_DIR = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _cand in (_PROD_SCRIPTS_DIR, _SCRIPT_DIR):
    if _cand.is_dir() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))
_int_pkg = sys.modules.get("_internal")
if _int_pkg is not None and hasattr(_int_pkg, "__path__"):
    _int_pkg.__path__ = pkgutil.extend_path(_int_pkg.__path__, "_internal")
from _internal.nk_common.facade_boot import init_nk_facade
init_nk_facade(__file__, pkg="sbfl_pytest_bridge")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "compute_ochiai": ("_internal.sbfl_pytest_bridge.models", "compute_ochiai"),
    "PytestRunSummary": ("_internal.sbfl_pytest_bridge.models", "PytestRunSummary"),
    "OchiaiBridgeLocation": ("_internal.sbfl_pytest_bridge.models", "OchiaiBridgeLocation"),
    "SBFLPytestBridge": ("_internal.sbfl_pytest_bridge.bridge_core", "SBFLPytestBridge"),
    "safe_subprocess_run": ("_internal.sbfl_pytest_bridge.bridge_core", "safe_subprocess_run"),
    "is_monitoring_conflict_active": ("_internal.sbfl_pytest_bridge.bridge_core", "is_monitoring_conflict_active"),
    "_build_cli_parser": ("_internal.sbfl_pytest_bridge.runner_and_cli", "_build_cli_parser"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod = importlib.import_module(target[0])
    val = getattr(mod, target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[Sequence[str]] = None) -> int:
    return importlib.import_module("_internal.sbfl_pytest_bridge.runner_and_cli").main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

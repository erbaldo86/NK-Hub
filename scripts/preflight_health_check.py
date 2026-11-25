#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostica di manutenzione e auto-sanitizzazione per NK Hub Generation 1.0.0-Generation.
Modulo: preflight_health_check.py.
@domain_id: DOM-01
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION: str = "1.0.0-Generation"
DEFAULT_VERSION: str = VERSION

_PHC_SCRIPT_DIR = Path(__file__).resolve().parent
_PHC_PROD_SCRIPTS_DIR = (
    _PHC_SCRIPT_DIR.parent.parent / "scripts"
    if _PHC_SCRIPT_DIR.parent.name == ".staging"
    else _PHC_SCRIPT_DIR
)
for _phc_p in (str(_PHC_PROD_SCRIPTS_DIR), str(_PHC_SCRIPT_DIR)):
    if Path(_phc_p).exists() and _phc_p not in sys.path:
        sys.path.insert(0, _phc_p)
if _PHC_SCRIPT_DIR != _PHC_PROD_SCRIPTS_DIR and (_PHC_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade as _init_phc_facade  # noqa: E402

_init_phc_facade(__file__, pkg="preflight_health_check")

_LAZY_EXPORT_MAP: Dict[str, tuple[str, str]] = {
    "PreflightHealthChecker": ("_internal.preflight_health_check.checker", "PreflightHealthChecker"),
    "safe_remove_dir": ("_internal.preflight_health_check.cleanup_and_wal", "safe_remove_dir"),
    "safe_remove_file": ("_internal.preflight_health_check.cleanup_and_wal", "safe_remove_file"),
    "main": ("_internal.preflight_health_check.cli", "main"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli del pacchetto _internal/preflight_health_check."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is not None:
        mod = importlib.import_module(target[0])
        val = getattr(mod, target[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI delegato a _internal.preflight_health_check.cli."""
    return importlib.import_module("_internal.preflight_health_check.cli").main(argv)


if __name__ == "__main__":
    sys.exit(main())

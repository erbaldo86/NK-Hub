#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentinella del contesto e motore anti-saturazione per NK Hub Generation 1.0.0-Generation.
Modulo: nk_context_sentry.py.
@domain_id: DOM-05
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
    _stg_nkc_dir = str(_SCRIPT_DIR / "_internal" / "nk_common")
    if isinstance(_stg_nkc.__path__, list):
        if _stg_nkc_dir in _stg_nkc.__path__:
            _stg_nkc.__path__.remove(_stg_nkc_dir)
        _stg_nkc.__path__.insert(0, _stg_nkc_dir)

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="nk_context_sentry")

_LAZY_EXPORT_MAP: Dict[str, tuple[str, str]] = {
    "NKContextSentry": ("_internal.nk_context_sentry.cli", "NKContextSentry"),
    "main": ("_internal.nk_context_sentry.cli", "main"),
    "SWARM_MSG_MSS_CAP": ("_internal.nk_context_sentry.thresholds_proxy", "SWARM_MSG_MSS_CAP"),
    "SWARM_MSG_HARD_CAP": ("_internal.nk_context_sentry.thresholds_proxy", "SWARM_MSG_HARD_CAP"),
    "STANDARD_GREEN_STEP_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "STANDARD_GREEN_STEP_THRESHOLD"),
    "STANDARD_RED_STEP_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "STANDARD_RED_STEP_THRESHOLD"),
    "STANDARD_GREEN_TOKEN_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "STANDARD_GREEN_TOKEN_THRESHOLD"),
    "STANDARD_RED_TOKEN_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "STANDARD_RED_TOKEN_THRESHOLD"),
    "GENERATION_GREEN_STEP_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "GENERATION_GREEN_STEP_THRESHOLD"),
    "GENERATION_RED_STEP_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "GENERATION_RED_STEP_THRESHOLD"),
    "GENERATION_GREEN_TOKEN_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "GENERATION_GREEN_TOKEN_THRESHOLD"),
    "GENERATION_RED_TOKEN_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "GENERATION_RED_TOKEN_THRESHOLD"),
    "GENERATION_ACTUAL_WARN_TOKENS": ("_internal.nk_context_sentry.thresholds_proxy", "GENERATION_ACTUAL_WARN_TOKENS"),
    "GENERATION_ACTUAL_RED_TOKENS": ("_internal.nk_context_sentry.thresholds_proxy", "GENERATION_ACTUAL_RED_TOKENS"),
    "CARBON_GREEN_STEP_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "CARBON_GREEN_STEP_THRESHOLD"),
    "CARBON_RED_STEP_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "CARBON_RED_STEP_THRESHOLD"),
    "CARBON_GREEN_TOKEN_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "CARBON_GREEN_TOKEN_THRESHOLD"),
    "CARBON_RED_TOKEN_THRESHOLD": ("_internal.nk_context_sentry.thresholds_proxy", "CARBON_RED_TOKEN_THRESHOLD"),
    "CARBON_ACTUAL_WARN_TOKENS": ("_internal.nk_context_sentry.thresholds_proxy", "CARBON_ACTUAL_WARN_TOKENS"),
    "CARBON_ACTUAL_RED_TOKENS": ("_internal.nk_context_sentry.thresholds_proxy", "CARBON_ACTUAL_RED_TOKENS"),
    "ARGON_ACTUAL_WARN_TOKENS": ("_internal.nk_context_sentry.thresholds_proxy", "ARGON_ACTUAL_WARN_TOKENS"),
    "ARGON_ACTUAL_RED_TOKENS": ("_internal.nk_context_sentry.thresholds_proxy", "ARGON_ACTUAL_RED_TOKENS"),
    "PLATFORM_COMPACTION_TOKEN_LIMIT": ("_internal.nk_context_sentry.thresholds_proxy", "PLATFORM_COMPACTION_TOKEN_LIMIT"),
    "COMPACTION_SUMMARY_MARKER": ("_internal.nk_context_sentry.thresholds_proxy", "COMPACTION_SUMMARY_MARKER"),
    "HIGH_CAPACITY_PROFILES": ("_internal.nk_context_sentry.thresholds_proxy", "HIGH_CAPACITY_PROFILES"),
    "CONTEXT_BACKSCAN_CHUNK_BYTES": ("_internal.nk_context_sentry.thresholds_proxy", "CONTEXT_BACKSCAN_CHUNK_BYTES"),
    "CONTEXT_MAX_SCAN_BYTES": ("_internal.nk_context_sentry.thresholds_proxy", "CONTEXT_MAX_SCAN_BYTES"),
    "_UNTRUSTED_COMPACTION_SOURCES": ("_internal.nk_context_sentry.thresholds_proxy", "_UNTRUSTED_COMPACTION_SOURCES"),
    "_UNTRUSTED_COMPACTION_TYPES": ("_internal.nk_context_sentry.thresholds_proxy", "_UNTRUSTED_COMPACTION_TYPES"),
    "_get_thresholds_data": ("_internal.nk_context_sentry.thresholds_proxy", "_get_thresholds_data"),
    "_contains_compaction_marker": ("_internal.nk_context_sentry.thresholds_proxy", "_contains_compaction_marker"),
    "load_saturation_thresholds": ("_internal.nk_context_sentry.thresholds_proxy", "load_saturation_thresholds"),
    "_safe_pos_int": ("_internal.nk_context_sentry.thresholds_proxy", "_safe_pos_int"),
    "reconfigure_streams": ("_internal.nk_context_sentry.thresholds_proxy", "reconfigure_streams"),
    "_workspace_root": ("_internal.nk_context_sentry.thresholds_proxy", "_workspace_root"),
    "locate_transcript": ("_internal.nk_transcript_tools.locate_and_compliance", "locate_transcript"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente soglie e simboli del pacchetto _internal/nk_context_sentry."""
    if name in ("_THRESHOLDS_DATA", "_PROFILES_DATA", "_STD_CS", "_CARB_CS", "_GEN_CS"):
        proxy = importlib.import_module("_internal.nk_context_sentry.thresholds_proxy")
        return proxy.get_lazy_threshold_attr(name)
    target = _LAZY_EXPORT_MAP.get(name)
    if target is not None:
        mod = importlib.import_module(target[0])
        val = getattr(mod, target[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(
        set(globals())
        | set(_LAZY_EXPORT_MAP)
        | {"_THRESHOLDS_DATA", "_PROFILES_DATA", "_STD_CS", "_CARB_CS", "_GEN_CS"}
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI delegato a _internal.nk_context_sentry.cli."""
    return importlib.import_module("_internal.nk_context_sentry.cli").main(argv)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificatore di conformita e scorecard duale per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/nk_compliance_checker.py.
@domain_id: DOM-05
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

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

    for _pkg_obj, _stg_dir in (
        (_stg_int, str(_SCRIPT_DIR / "_internal")),
        (_stg_nkc, str(_SCRIPT_DIR / "_internal" / "nk_common")),
    ):
        _cur_p = list(getattr(_pkg_obj, "__path__", ()))
        _pkg_obj.__path__ = [_stg_dir] + [p for p in _cur_p if os.path.normcase(p) != os.path.normcase(_stg_dir)]

from _internal.nk_common.facade_boot import _prepend_pkg_overlay, init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="nk_compliance_checker")
if _SCRIPT_DIR != _PROD_SCRIPTS:
    _prepend_pkg_overlay("_internal.nk_transcript_tools", str(_SCRIPT_DIR / "_internal" / "nk_transcript_tools"))

_LAZY_EXPORT_MAP: Dict[str, tuple[str, str]] = {
    "NKComplianceChecker": ("_internal.nk_compliance_checker.cli", "NKComplianceChecker"),
    "main": ("_internal.nk_compliance_checker.cli", "main"),
    "COMPLIANCE_CHECKER_VERSION": ("_internal.nk_compliance_checker.transcript_scan", "COMPLIANCE_CHECKER_VERSION"),
    "DDI_DIRECT_STREAK_LIMIT": ("_internal.nk_compliance_checker.transcript_scan", "DDI_DIRECT_STREAK_LIMIT"),
    "SESSION_TELEMETRY_MAX_SKEW_SECONDS": ("_internal.nk_compliance_checker.transcript_scan", "SESSION_TELEMETRY_MAX_SKEW_SECONDS"),
    "EXEMPT_WRITE_MARKERS": ("_internal.nk_compliance_checker.transcript_scan", "EXEMPT_WRITE_MARKERS"),
    "DIRECT_AUDIT_TOOLS": ("_internal.nk_compliance_checker.transcript_scan", "DIRECT_AUDIT_TOOLS"),
    "DELEGATION_TOOLS": ("_internal.nk_compliance_checker.transcript_scan", "DELEGATION_TOOLS"),
    "NKContextSentry": ("_internal.nk_compliance_checker.transcript_scan", "NKContextSentry"),
    "find_active_transcript": ("_internal.nk_compliance_checker.transcript_scan", "find_active_transcript"),
    "_is_subagent_transcript": ("_internal.nk_compliance_checker.transcript_scan", "_is_subagent_transcript"),
    "_is_production_code_write": ("_internal.nk_compliance_checker.transcript_scan", "_is_production_code_write"),
    "_is_external_unstage_write": ("_internal.nk_compliance_checker.transcript_scan", "_is_external_unstage_write"),
    "_is_exempt_diagnostic_nonzero": ("_internal.nk_compliance_checker.transcript_scan", "_is_exempt_diagnostic_nonzero"),
    "_parse_record_epoch": ("_internal.nk_compliance_checker.transcript_scan", "_parse_record_epoch"),
    "_extract_call_correlation_id": ("_internal.nk_compliance_checker.transcript_scan", "_extract_call_correlation_id"),
    "_is_verified_converged_tool_output": ("_internal.nk_compliance_checker.transcript_scan", "_is_verified_converged_tool_output"),
    "_pop_correlated_tool_call": ("_internal.nk_compliance_checker.transcript_scan", "_pop_correlated_tool_call"),
    "reconfigure_streams": ("_internal.nk_compliance_checker.transcript_scan", "reconfigure_streams"),
    "_workspace_root": ("_internal.nk_compliance_checker.transcript_scan", "_workspace_root"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli del pacchetto _internal/nk_compliance_checker."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is not None:
        mod = importlib.import_module(target[0])
        val = getattr(mod, target[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main() -> int:
    """Punto di ingresso CLI delegato a _internal.nk_compliance_checker.cli."""
    return importlib.import_module("_internal.nk_compliance_checker.cli").main()


if __name__ == "__main__":
    sys.exit(main())

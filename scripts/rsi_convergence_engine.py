#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facciata CLI e API per il motore di convergenza RSI NK Hub Generation 1.0.0-Generation.
Modulo: scripts/rsi_convergence_engine.py.
Delega la logica ai sottomoduli _internal.rsi_convergence_engine.* via _LAZY_EXPORT_MAP.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
from _internal.nk_common.paths import reconfigure_streams as _nk_reconfigure_streams, resolve_workspace_root  # noqa: E402

init_nk_facade(__file__, pkg="rsi_convergence_engine")
_scripts_dir = _SCRIPT_DIR
_workspace_root = Path(resolve_workspace_root(__file__))

_STREAMS_RECONFIGURED = False
_LAZY_HEALING_SNAPSHOT_CLS: Any = None
_LAZY_HEALING_SNAPSHOT_LOADED = False
_LAZY_AST_GUARD_CLS: Any = None
_LAZY_AST_GUARD_LOADED = False
_LAZY_STE100_FN: Optional[Callable[..., Dict[str, Any]]] = None
_LAZY_GROUNDING_FN: Optional[Callable[..., Dict[str, Any]]] = None
_EXPORTS_LOADED = False
_HOOKS_REGISTERED = False

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "run_ab_benchmark": ("_internal.rsi_convergence_engine.ab_benchmark", "run_ab_benchmark"),
    "_CANARY_SPECS": ("_internal.rsi_convergence_engine.canary_holdout", "_CANARY_SPECS"),
    "_detect_assertion_epistemic_conflict": ("_internal.rsi_convergence_engine.canary_holdout", "_detect_assertion_epistemic_conflict"),
    "_extract_lhs_op_rhs": ("_internal.rsi_convergence_engine.canary_holdout", "_extract_lhs_op_rhs"),
    "_literals_strictly_distinct": ("_internal.rsi_convergence_engine.canary_holdout", "_literals_strictly_distinct"),
    "_numeric_bounds_disjoint": ("_internal.rsi_convergence_engine.canary_holdout", "_numeric_bounds_disjoint"),
    "_parse_single_assertion_ast": ("_internal.rsi_convergence_engine.canary_holdout", "_parse_single_assertion_ast"),
    "ensure_canary_holdout_file": ("_internal.rsi_convergence_engine.canary_holdout", "ensure_canary_holdout_file"),
    "evaluate_canary_holdout": ("_internal.rsi_convergence_engine.canary_holdout", "evaluate_canary_holdout"),
    "EXCLUDED_SCAN_DIRS": ("_internal.rsi_convergence_engine.constants", "EXCLUDED_SCAN_DIRS"),
    "MODE_ITERATION_CAPS": ("_internal.rsi_convergence_engine.constants", "MODE_ITERATION_CAPS"),
    "_FILE_AST_CACHE": ("_internal.rsi_convergence_engine.constants", "_FILE_AST_CACHE"),
    "_TELEMETRY_LOCK": ("_internal.rsi_convergence_engine.constants", "_TELEMETRY_LOCK"),
    "DefectVector": ("_internal.rsi_convergence_engine.constants", "DefectVector"),
    "RSIDefectVector": ("_internal.rsi_convergence_engine.constants", "RSIDefectVector"),
    "RSIIterationRecord": ("_internal.rsi_convergence_engine.constants", "RSIIterationRecord"),
    "RSISessionReport": ("_internal.rsi_convergence_engine.constants", "RSISessionReport"),
    "_collect_overlay_md_files": ("_internal.rsi_convergence_engine.constants", "_collect_overlay_md_files"),
    "_extract_sast_report_count": ("_internal.rsi_convergence_engine.constants", "_extract_sast_report_count"),
    "_get_cached_file_and_ast": ("_internal.rsi_convergence_engine.constants", "_get_cached_file_and_ast"),
    "_is_excluded_rel_path": ("_internal.rsi_convergence_engine.constants", "_is_excluded_rel_path"),
    "RSIConvergenceEngine": ("_internal.rsi_convergence_engine.engine", "RSIConvergenceEngine"),
    "emit_gt14_bundle": ("_internal.rsi_convergence_engine.engine", "emit_gt14_bundle"),
    "register_lazy_hooks": ("_internal.rsi_convergence_engine.lazy_bridge", "register_lazy_hooks"),
    "RSIProfileConfig": ("_internal.rsi_convergence_engine.profiles", "RSIProfileConfig"),
    "RSIProfileRegistry": ("_internal.rsi_convergence_engine.profiles", "RSIProfileRegistry"),
    "_fallback_verify_ste100_compliance": ("_internal.rsi_convergence_engine.profiles", "_fallback_verify_ste100_compliance"),
    "compute_delta": ("_internal.rsi_convergence_engine.profiles", "compute_delta"),
    "compute_fitness": ("_internal.rsi_convergence_engine.profiles", "compute_fitness"),
    "verify_ste100_compliance": ("_internal.rsi_convergence_engine.profiles", "verify_ste100_compliance"),
}


def reconfigure_streams() -> None:
    global _STREAMS_RECONFIGURED
    if not _STREAMS_RECONFIGURED:
        _nk_reconfigure_streams()
        _STREAMS_RECONFIGURED = True

def _get_healing_snapshot_manager_cls() -> Any:
    return importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge").facade_get_healing_snapshot_manager_cls(globals())

def _get_ast_guard_validator() -> Any:
    return importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge").facade_get_ast_guard_validator(globals())

def _load_ntt_module() -> Any:
    return importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge").fallback_load_ntt_module(_scripts_dir, _workspace_root)

def _get_ste100_validator() -> Callable[..., Dict[str, Any]]:
    return importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge").facade_get_ste100_validator(globals(), _load_ntt_module)

def _get_report_grounding_validator() -> Optional[Callable[..., Dict[str, Any]]]:
    return importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge").facade_get_report_grounding_validator(globals(), _load_ntt_module)

def _ensure_exports_loaded() -> Dict[str, Any]:
    return importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge").facade_ensure_exports_loaded(
        globals(), _LAZY_EXPORT_MAP, reconfigure_fn=reconfigure_streams, hsm_fn=_get_healing_snapshot_manager_cls,
        agv_fn=_get_ast_guard_validator, ste100_fn=_get_ste100_validator, grounding_fn=_get_report_grounding_validator,
    )

def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORT_MAP and not _EXPORTS_LOADED:
        return _ensure_exports_loaded()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point CLI per il motore di convergenza RSI."""
    reconfigure_streams()
    return importlib.import_module("_internal.rsi_convergence_engine.cli").run_rsi_cli(
        argv=argv,
        default_root=_workspace_root,
        ensure_exports_fn=_ensure_exports_loaded,
    )

if __name__ == "__main__":
    sys.exit(main())

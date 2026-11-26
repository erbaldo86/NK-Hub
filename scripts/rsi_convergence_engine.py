#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facciata CLI e API per il motore di convergenza RSI NK Hub Generation 1.0.0-Generation.
Modulo: scripts/rsi_convergence_engine.py.
Delega la logica ai 12 moduli consolidati _internal.rsi_convergence_engine.* via _LAZY_EXPORT_MAP.
"""

from __future__ import annotations

import argparse
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
from _internal.nk_common.paths import (  # noqa: E402
    reconfigure_streams as _nk_reconfigure_streams,
    resolve_workspace_root,
)

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
    "run_ab_benchmark": ("_internal.rsi_convergence_engine.engine", "run_ab_benchmark"),
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
    "_get_cached_file_and_ast": ("_internal.rsi_convergence_engine.constants", "_get_cached_file_and_ast"),
    "_is_excluded_rel_path": ("_internal.rsi_convergence_engine.constants", "_is_excluded_rel_path"),
    "RSIConvergenceEngine": ("_internal.rsi_convergence_engine.engine", "RSIConvergenceEngine"),
    "emit_gt14_bundle": ("_internal.rsi_convergence_engine.engine", "emit_gt14_bundle"),
    "run_rsi_cli": ("_internal.rsi_convergence_engine.engine", "run_rsi_cli"),
    "register_lazy_hooks": ("_internal.rsi_convergence_engine.constants", "register_lazy_hooks"),
    "RSIProfileConfig": ("_internal.rsi_convergence_engine.profiles", "RSIProfileConfig"),
    "RSIProfileRegistry": ("_internal.rsi_convergence_engine.profiles", "RSIProfileRegistry"),
    "_fallback_verify_ste100_compliance": ("_internal.rsi_convergence_engine.profiles", "_fallback_verify_ste100_compliance"),
    "compute_delta": ("_internal.rsi_convergence_engine.profiles", "compute_delta"),
    "compute_fitness": ("_internal.rsi_convergence_engine.profiles", "compute_fitness"),
    "compute_fitness_v2": ("_internal.rsi_convergence_engine.profiles", "compute_fitness_v2"),
    "compute_candidate_sort_key": ("_internal.rsi_convergence_engine.profiles", "compute_candidate_sort_key"),
    "verify_ste100_compliance": ("_internal.rsi_convergence_engine.profiles", "verify_ste100_compliance"),
    "audit_sast_report_payload": ("_internal.rsi_convergence_engine.vibe_report_helpers", "audit_sast_report_payload"),
    "audit_coverage_report_payload": ("_internal.rsi_convergence_engine.vibe_report_helpers", "audit_coverage_report_payload"),
}


def reconfigure_streams() -> None:
    """Configura flussi stdio UTF-8 una sola volta per processo."""
    global _STREAMS_RECONFIGURED
    if not _STREAMS_RECONFIGURED:
        _nk_reconfigure_streams()
        _STREAMS_RECONFIGURED = True


def _get_healing_snapshot_manager_cls() -> Any:
    c_mod = importlib.import_module("_internal.rsi_convergence_engine.constants")
    return c_mod.facade_get_cached_attr(globals(), "_LAZY_HEALING_SNAPSHOT_LOADED", "_LAZY_HEALING_SNAPSHOT_CLS", c_mod._direct_load_hsm_cls)


def _get_ast_guard_validator() -> Any:
    c_mod = importlib.import_module("_internal.rsi_convergence_engine.constants")
    return c_mod.facade_get_cached_attr(globals(), "_LAZY_AST_GUARD_LOADED", "_LAZY_AST_GUARD_CLS", c_mod._direct_load_agv_cls)


def _get_ste100_validator() -> Callable[..., Dict[str, Any]]:
    c_mod = importlib.import_module("_internal.rsi_convergence_engine.constants")
    return c_mod.facade_get_cached_attr(globals(), "", "_LAZY_STE100_FN", c_mod._direct_load_ste100_fn)


def _get_report_grounding_validator() -> Optional[Callable[..., Dict[str, Any]]]:
    c_mod = importlib.import_module("_internal.rsi_convergence_engine.constants")
    return c_mod.facade_get_cached_attr(globals(), "", "_LAZY_GROUNDING_FN", c_mod._direct_load_grounding_fn)


def _ensure_exports_loaded() -> Dict[str, Any]:
    return importlib.import_module("_internal.rsi_convergence_engine.constants").facade_ensure_exports_loaded(
        globals(), _LAZY_EXPORT_MAP, reconfigure_fn=reconfigure_streams, hsm_fn=_get_healing_snapshot_manager_cls,
        agv_fn=_get_ast_guard_validator, ste100_fn=_get_ste100_validator, grounding_fn=_get_report_grounding_validator,
    )


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORT_MAP and not _EXPORTS_LOADED:
        return _ensure_exports_loaded()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_HELP_CLI_BOOL_FLAGS: Tuple[Tuple[str, str], ...] = (
    ("--verify", "Verifica Guardia G6"), ("--strict-verify", "Pytest reale fail-closed"),
    ("--run-pytest", "Esegue suite pytest"), ("--ab-benchmark", "Legacy dismessa"),
    ("--verify-canary", "Canary Holdout read-only"), ("--emit-gt14-bundle", "Sonde GT-14 in-process"),
    ("--with-dast", "DAST overlay GT-14"), ("--scan-prod-frontend", "Audit frontend produzione"),
    ("--persist-telemetry", "Salva telemetria JSONL"), ("--strict-profile", "Rifiuta profili sconosciuti"),
    ("--diff-aware", "Attiva segnale diff Python solo su staging/allowed"), ("--json", "Output JSON"),
)
_HELP_CLI_STR_FLAGS: Tuple[Tuple[str, str], ...] = (
    ("--bundle-output", "Output JSON GT-14"), ("--sast-report", "Path report JSON SAST"),
    ("--mutation-report", "Path report JSON mutation"), ("--dast-report", "Path report JSON DAST"),
    ("--test-report", "Path report JSON test suite"), ("--coverage-report", "Path report JSON coverage"),
    ("--allowed-files", "CSV file consentiti in .staging/"), ("--profile", "Profilo Tensor-RSI (P1..P6)"),
    ("--lane-id", "ID lane di staging isolata"), ("--root", "Directory radice"),
)


def _build_fast_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Motore di Convergenza RSI NK Hub Generation")
    for flag, hlp in _HELP_CLI_BOOL_FLAGS:
        parser.add_argument(flag, action="store_true", help=hlp)
    for flag, hlp in _HELP_CLI_STR_FLAGS:
        parser.add_argument(flag, type=str, default=None, help=hlp)
    parser.add_argument("--vibe-check", nargs="?", const=".", type=str, default=None, help="Micro-loop Vibe Check")
    parser.add_argument("--benchmark-suite", "--suite", dest="benchmark_suite", type=str, default=None, help="Target suite pytest")
    return parser


def _run_main_cli(argv: Optional[Sequence[str]]) -> int:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if "-h" in argv_list or "--help" in argv_list:
        _build_fast_help_parser().parse_args(argv_list)
        return 0
    return importlib.import_module("_internal.rsi_convergence_engine.engine").run_rsi_cli(
        argv=argv,
        default_root=_workspace_root,
        ensure_exports_fn=_ensure_exports_loaded,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point CLI per il motore di convergenza RSI (lazy su --help)."""
    reconfigure_streams()
    return _run_main_cli(argv)


if __name__ == "__main__":
    sys.exit(main())

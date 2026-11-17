#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline universale di auto-riparazione per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/auto_heal_pipeline.py.
@domain_id: DOM-03
Centralizza snapshot binari puri, loop SBFL, KarpathySlicer, Strict Monotonic Fitness Gate e telemetria RSI.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

__nk_domain__: str = "DOM-03"
__nk_role__: str = "facade"
__nk_facade__: str = "auto_heal_pipeline"

_CLI_FLAGS: Tuple[str, ...] = (
    "--cwd",
    "--json",
    "--max-cycles",
    "--target-file",
    "--test-cmd",
)

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

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="auto_heal_pipeline")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "_scripts_dir": ("_internal.auto_heal_pipeline.models_and_slice", "_scripts_dir"),
    "_root_dir": ("_internal.auto_heal_pipeline.models_and_slice", "_root_dir"),
    "_LAZY_LOAD_LOCK": ("_internal.auto_heal_pipeline.models_and_slice", "_LAZY_LOAD_LOCK"),
    "_UNSET": ("_internal.auto_heal_pipeline.models_and_slice", "_UNSET"),
    "MAX_HEALING_CYCLES": ("_internal.auto_heal_pipeline.models_and_slice", "MAX_HEALING_CYCLES"),
    "OchiaiBridgeLocation": ("_internal.auto_heal_pipeline.models_and_slice", "OchiaiBridgeLocation"),
    "SBFLPytestBridge": ("_internal.auto_heal_pipeline.models_and_slice", "SBFLPytestBridge"),
    "RSIConvergenceEngine": ("_internal.auto_heal_pipeline.models_and_slice", "RSIConvergenceEngine"),
    "RSIDefectVector": ("_internal.auto_heal_pipeline.models_and_slice", "RSIDefectVector"),
    "RSIIterationRecord": ("_internal.auto_heal_pipeline.models_and_slice", "RSIIterationRecord"),
    "compute_delta": ("_internal.auto_heal_pipeline.models_and_slice", "compute_delta"),
    "compute_fitness": ("_internal.auto_heal_pipeline.models_and_slice", "compute_fitness"),
    "ASTGuardValidator": ("_internal.auto_heal_pipeline.models_and_slice", "ASTGuardValidator"),
    "_pin_staging_sys_path": ("_internal.auto_heal_pipeline.models_and_slice", "_pin_staging_sys_path"),
    "_ensure_sbfl_bridge_loaded": ("_internal.auto_heal_pipeline.models_and_slice", "_ensure_sbfl_bridge_loaded"),
    "_ensure_rsi_loaded": ("_internal.auto_heal_pipeline.models_and_slice", "_ensure_rsi_loaded"),
    "_ensure_ast_guard_loaded": ("_internal.auto_heal_pipeline.models_and_slice", "_ensure_ast_guard_loaded"),
    "CodeSlice": ("_internal.auto_heal_pipeline.models_and_slice", "CodeSlice"),
    "HealingCycleLog": ("_internal.auto_heal_pipeline.models_and_slice", "HealingCycleLog"),
    "HealingResult": ("_internal.auto_heal_pipeline.models_and_slice", "HealingResult"),
    "DSPyTelemetryRecord": ("_internal.auto_heal_pipeline.models_and_slice", "DSPyTelemetryRecord"),
    "AutoHealSessionReport": ("_internal.auto_heal_pipeline.models_and_slice", "AutoHealSessionReport"),
    "KarpathySlicer": ("_internal.auto_heal_pipeline.models_and_slice", "KarpathySlicer"),
    "DSPyTelemetryHook": ("_internal.auto_heal_pipeline.models_and_slice", "DSPyTelemetryHook"),
    "classify_failure": ("_internal.auto_heal_pipeline.models_and_slice", "classify_failure"),
    "normalize_test_command": ("_internal.auto_heal_pipeline.models_and_slice", "normalize_test_command"),
    "FitnessVerdict": ("_internal.auto_heal_pipeline.runner", "FitnessVerdict"),
    "HealingSnapshotManager": ("_internal.auto_heal_pipeline.runner", "HealingSnapshotManager"),
    "_build_defect_vector": ("_internal.auto_heal_pipeline.runner", "_build_defect_vector"),
    "_compute_rsi_metrics": ("_internal.auto_heal_pipeline.runner", "_compute_rsi_metrics"),
    "AutoHealPipeline": ("_internal.auto_heal_pipeline.runner", "AutoHealPipeline"),
    "_build_cli_parser": ("_internal.auto_heal_pipeline.cli", "_build_cli_parser"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.auto_heal_pipeline."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="auto_heal_pipeline")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main() -> int:
    """Punto di ingresso CLI per la pipeline di auto-riparazione."""
    init_nk_facade(__file__, pkg="auto_heal_pipeline")
    return importlib.import_module("_internal.auto_heal_pipeline.cli").main()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore del Ratchet di qualita per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/quality_baseline_manager.py.
@domain_id: DOM-05
Applica la regola [RULE-01.10] con soglia MIN_GOLDEN_TESTS_FLOOR = 93, misurazione Pytest reale e verifica oracle_lock.json.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

__nk_domain__: str = "DOM-05"
__nk_role__: str = "facade"
__nk_facade__: str = "quality_baseline_manager"

_CLI_FLAGS: Tuple[str, ...] = (
    "--allow-ratchet-down",
    "--check",
    "--check-only",
    "--file",
    "--json",
    "--live",
    "--metrics",
    "--recalibrate",
    "--target-tests",
    "--update",
    "--with-coverage",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="quality_baseline_manager")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "_scripts_dir": ("_internal.quality_baseline_manager.constants", "_scripts_dir"),
    "BASELINE_FILENAME": ("_internal.quality_baseline_manager.constants", "BASELINE_FILENAME"),
    "BASELINE_SCHEMA_VERSION": ("_internal.quality_baseline_manager.constants", "BASELINE_SCHEMA_VERSION"),
    "DEFAULT_BASELINE_VERSION": ("_internal.quality_baseline_manager.constants", "DEFAULT_BASELINE_VERSION"),
    "MIN_GOLDEN_TESTS_FLOOR": ("_internal.quality_baseline_manager.constants", "MIN_GOLDEN_TESTS_FLOOR"),
    "CONSTITUTIONAL_GOLDEN_FLOOR": ("_internal.quality_baseline_manager.constants", "CONSTITUTIONAL_GOLDEN_FLOOR"),
    "RECALIBRATED_COUNT_KEYS": ("_internal.quality_baseline_manager.constants", "RECALIBRATED_COUNT_KEYS"),
    "LOWER_IS_BETTER_KEYS": ("_internal.quality_baseline_manager.constants", "LOWER_IS_BETTER_KEYS"),
    "load_baseline": ("_internal.quality_baseline_manager.constants", "load_baseline"),
    "create_default_baseline": ("_internal.quality_baseline_manager.constants", "create_default_baseline"),
    "_atomic_write_baseline": ("_internal.quality_baseline_manager.constants", "_atomic_write_baseline"),
    "_extract_numeric_metric": ("_internal.quality_baseline_manager.constants", "_extract_numeric_metric"),
    "_is_valid_gt68_recalibration": ("_internal.quality_baseline_manager.constants", "_is_valid_gt68_recalibration"),
    "_resolve_workspace_root_from_baseline": ("_internal.quality_baseline_manager.constants", "_resolve_workspace_root_from_baseline"),
    "_resolve_default_baseline_path": ("_internal.quality_baseline_manager.constants", "_resolve_default_baseline_path"),
    "_is_hex_sha256": ("_internal.quality_baseline_manager.constants", "_is_hex_sha256"),
    "_verify_oracle_lock_coherence": ("_internal.quality_baseline_manager.constants", "_verify_oracle_lock_coherence"),
    "_count_live_skills_overlay": ("_internal.quality_baseline_manager.benchmark_runner", "_count_live_skills_overlay"),
    "_extract_coverage_totals": ("_internal.quality_baseline_manager.benchmark_runner", "_extract_coverage_totals"),
    "measure_live_pytest_metrics": ("_internal.quality_baseline_manager.benchmark_runner", "measure_live_pytest_metrics"),
    "subprocess": ("_internal.quality_baseline_manager.benchmark_runner", "subprocess"),
    "shutil": ("_internal.quality_baseline_manager.benchmark_runner", "shutil"),
    "os": ("_internal.quality_baseline_manager.benchmark_runner", "os"),
    "time": ("_internal.quality_baseline_manager.benchmark_runner", "time"),
    "_evaluate_baseline_compliance": ("_internal.quality_baseline_manager.ratchet_core", "_evaluate_baseline_compliance"),
    "check_baseline_compliance": ("_internal.quality_baseline_manager.ratchet_core", "check_baseline_compliance"),
    "_validate_legitimate_update_gate": ("_internal.quality_baseline_manager.ratchet_core", "_validate_legitimate_update_gate"),
    "update_baseline_metrics": ("_internal.quality_baseline_manager.ratchet_core", "update_baseline_metrics"),
    "recalibrate_baseline": ("_internal.quality_baseline_manager.ratchet_core", "recalibrate_baseline"),
    "_build_cli_parser": ("_internal.quality_baseline_manager.cli", "_build_cli_parser"),
    "atomic_write_json": ("_internal.nk_common.io", "atomic_write_json"),
    "load_registry_manifest": ("_internal.nk_common.catalog", "load_registry_manifest"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.quality_baseline_manager."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="quality_baseline_manager")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main() -> int:
    """Punto di ingresso CLI per il gestore del Ratchet di qualita."""
    init_nk_facade(__file__, pkg="quality_baseline_manager")
    return importlib.import_module("_internal.quality_baseline_manager.cli").main()


if __name__ == "__main__":
    sys.exit(main())

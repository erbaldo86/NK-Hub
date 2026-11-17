#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper tipizzato snello per Invisible Healing Loop in NK Hub Generation 1.0.0-Generation.
Modulo: invisible_healing_loop.py.
Delega slicing, budget SBFL, telemetria e pipeline a scripts/auto_heal_pipeline.py e scripts/sbfl_engine.py.
Preserva integralmente tutte le firme pubbliche e gli attributi esportati.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_scripts_dir = Path(__file__).resolve().parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
if _scripts_dir.name == ".staging":
    _root_dir = _scripts_dir.parent
for _d in (
    _scripts_dir,
    _root_dir / "scripts",
    _root_dir / ".staging" / "scripts",
    _root_dir,
):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))
if str(_scripts_dir) in sys.path:
    sys.path.remove(str(_scripts_dir))
sys.path.insert(0, str(_scripts_dir))

_DEFAULT_SBFL_MAX_TOKEN_BUDGET: int = 80
_DEFAULT_MAX_HEALING_CYCLES: int = 3

_LAZY_EXPORT_MAP: Dict[str, str] = {
    "SBFL_MAX_TOKEN_BUDGET": "sbfl_engine",
    "SBFLEngine": "sbfl_engine",
    "SBFLLocation": "sbfl_engine",
    "SpectrumCounts": "sbfl_engine",
    "calculate_ochiai": "sbfl_engine",
    "estimate_token_count": "sbfl_engine",
    "MAX_HEALING_CYCLES": "auto_heal_pipeline",
    "AutoHealPipeline": "auto_heal_pipeline",
    "AutoHealSessionReport": "auto_heal_pipeline",
    "CodeSlice": "auto_heal_pipeline",
    "DSPyTelemetryHook": "auto_heal_pipeline",
    "DSPyTelemetryRecord": "auto_heal_pipeline",
    "HealingCycleLog": "auto_heal_pipeline",
    "HealingResult": "auto_heal_pipeline",
    "KarpathySlicer": "auto_heal_pipeline",
}


def _load_lazy_symbol(name: str) -> Any:
    """Risolve pigramente un simbolo esportato da sbfl_engine o auto_heal_pipeline."""
    mod_name = _LAZY_EXPORT_MAP.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if _scripts_dir.parent.name == ".staging":
        _stg_f = _scripts_dir / f"{mod_name}.py"
        _cached_m = sys.modules.get(mod_name)
        if _cached_m is not None and _stg_f.is_file():
            _cf = getattr(_cached_m, "__file__", "") or ""
            if not _cf or Path(_cf).resolve() != _stg_f.resolve():
                sys.modules.pop(mod_name, None)
    try:
        mod = importlib.import_module(mod_name)
    except ImportError:
        mod = importlib.import_module(f"scripts.{mod_name}")
    if _scripts_dir.parent.name == ".staging":
        _stg_scripts_str = str(_scripts_dir)
        if _stg_scripts_str in sys.path:
            sys.path.remove(_stg_scripts_str)
        sys.path.insert(0, _stg_scripts_str)
    val = getattr(mod, name)
    globals()[name] = val
    return val


AutoHealSessionReport = _load_lazy_symbol("AutoHealSessionReport")
HealingCycleLog = _load_lazy_symbol("HealingCycleLog")


def __dir__() -> List[str]:
    """Espone i simboli pubblici lazy di invisible_healing_loop."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def __getattr__(name: str) -> Any:
    """Risolve su richiesta gli export pubblici di sbfl_engine e auto_heal_pipeline (PEP 562)."""
    return _load_lazy_symbol(name)


__all__ = [
    "MAX_HEALING_CYCLES",
    "SBFL_MAX_TOKEN_BUDGET",
    "AutoHealPipeline",
    "AutoHealSessionReport",
    "CodeSlice",
    "DSPyTelemetryHook",
    "DSPyTelemetryRecord",
    "HealingCycleLog",
    "HealingResult",
    "InvisibleHealingLoop",
    "KarpathySlicer",
    "SBFLEngine",
    "SBFLLocation",
    "SpectrumCounts",
    "calculate_ochiai",
    "estimate_token_count",
    "main",
]


class InvisibleHealingLoop:
    """Orchestratore che integra SBFLEngine e AutoHealPipeline."""

    token_budget: int = _DEFAULT_SBFL_MAX_TOKEN_BUDGET

    @property
    def result_model(self) -> Any:
        """Restituisce in modo lazy il modello HealingResult di auto_heal_pipeline."""
        return _load_lazy_symbol("HealingResult")

    def __init__(
        self,
        telemetry_log_path: Optional[Path] = None,
        max_cycles: int = _DEFAULT_MAX_HEALING_CYCLES,
    ) -> None:
        self.max_cycles = max_cycles
        if telemetry_log_path:
            hook_cls = _load_lazy_symbol("DSPyTelemetryHook")
            self.telemetry_hook = hook_cls(telemetry_log_path)
        else:
            self.telemetry_hook = None

    def run_cli_pipeline(
        self,
        test_cmd: Union[str, List[str]],
        target_file: Union[str, Path],
        cwd: Optional[Path] = None,
    ) -> AutoHealSessionReport:
        """Delega l'esecuzione del ciclo di riparazione su file a AutoHealPipeline."""
        pipeline_cls = _load_lazy_symbol("AutoHealPipeline")
        pipeline = pipeline_cls(cwd=cwd, max_cycles=self.max_cycles)
        return pipeline.run_pipeline(test_cmd=test_cmd, target_file=target_file)

    def _record_telemetry(
        self,
        run_id: str,
        task_name: str,
        cycles_total: int,
        status: str,
        history: List[HealingCycleLog],
    ) -> None:
        if not self.telemetry_hook:
            return
        record_cls = _load_lazy_symbol("DSPyTelemetryRecord")
        rec = record_cls(
            run_id=run_id,
            task_name=task_name,
            cycles_total=cycles_total,
            final_status=status,
            cycles_telemetry=[h.model_dump() for h in history],
        )
        self.telemetry_hook.record_run(rec)


def main() -> int:
    """Delega l'invocazione CLI a AutoHealPipeline."""
    parser = argparse.ArgumentParser(
        description="Wrapper CLI Invisible Healing Loop delegato a AutoHealPipeline"
    )
    parser.add_argument("--test-cmd", type=str, required=True)
    parser.add_argument("--target-file", type=str, required=True)
    parser.add_argument("--cwd", type=str, default=None)
    parser.add_argument("--max-cycles", type=int, default=_DEFAULT_MAX_HEALING_CYCLES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    loop = InvisibleHealingLoop(max_cycles=args.max_cycles)
    rep = loop.run_cli_pipeline(
        test_cmd=args.test_cmd,
        target_file=args.target_file,
        cwd=Path(args.cwd) if args.cwd else None,
    )
    if args.json:
        print(rep.model_dump_json(indent=2))
    else:
        print(rep.message)
    return 0 if rep.success else 1


if __name__ == "__main__":
    sys.exit(main())

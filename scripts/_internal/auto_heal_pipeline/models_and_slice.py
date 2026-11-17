# -*- coding: utf-8 -*-
"""Modelli Pydantic, loader pigri, KarpathySlicer e utilita per auto_heal_pipeline."""

from __future__ import annotations

import ast
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.facade_boot import resolve_facade_attr

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)

_FACADE_MOD_NAMES: Tuple[str, ...] = ("auto_heal_pipeline", "scripts.auto_heal_pipeline")
_LAZY_LOAD_LOCK = threading.Lock()
_UNSET: Any = type("_UnsetSentinel", (), {})
MAX_HEALING_CYCLES: int = 3

OchiaiBridgeLocation: Any = _UNSET
SBFLPytestBridge: Any = _UNSET
RSIConvergenceEngine: Any = _UNSET
RSIDefectVector: Any = _UNSET
RSIIterationRecord: Any = _UNSET
compute_delta: Any = _UNSET
compute_fitness: Any = _UNSET
ASTGuardValidator: Any = _UNSET


def _iter_facades() -> List[Any]:
    """Restituisce tutte le istanze attive della facciata auto_heal_pipeline in sys.modules."""
    found: List[Any] = []
    seen_ids: set[int] = set()
    for mod_key in _FACADE_MOD_NAMES:
        fac = sys.modules.get(mod_key)
        if fac is not None and id(fac) not in seen_ids:
            seen_ids.add(id(fac))
            found.append(fac)
    for fac in tuple(sys.modules.values()):
        if (
            fac is not None
            and id(fac) not in seen_ids
            and getattr(fac, "__nk_facade__", None) == "auto_heal_pipeline"
        ):
            seen_ids.add(id(fac))
            found.append(fac)
    return found


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


def _sync_facade_attr(attr_name: str, value: Any) -> None:
    """Propaga il valore caricato pigramente verso le facciate che espongono _UNSET."""
    for fac in _iter_facades():
        cur = _UNSET
        for key, val in vars(fac).copy().items():
            if key == attr_name:
                cur = val
                break
        if cur is _UNSET:
            setattr(fac, attr_name, value)


def _pin_staging_sys_path() -> None:
    """Mantiene .staging/scripts in testa a sys.path quando eseguito da staging."""
    if _scripts_dir.parent.name == ".staging":
        stg_top = str(_scripts_dir)
        if stg_top in sys.path:
            sys.path.remove(stg_top)
        sys.path.insert(0, stg_top)


def _ensure_sbfl_bridge_loaded() -> None:
    """Carica pigramente sbfl_pytest_bridge preservando eventuali override sulla facciata."""
    global OchiaiBridgeLocation, SBFLPytestBridge
    cur_loc = _facade_attr("OchiaiBridgeLocation", OchiaiBridgeLocation)
    cur_br = _facade_attr("SBFLPytestBridge", SBFLPytestBridge)
    if cur_loc is not _UNSET and cur_br is not _UNSET:
        return
    with _LAZY_LOAD_LOCK:
        cur_loc = _facade_attr("OchiaiBridgeLocation", OchiaiBridgeLocation)
        cur_br = _facade_attr("SBFLPytestBridge", SBFLPytestBridge)
        if cur_loc is not _UNSET and cur_br is not _UNSET:
            return
        try:
            from sbfl_pytest_bridge import OchiaiBridgeLocation as _loc, SBFLPytestBridge as _bridge
        except ImportError:
            from scripts.sbfl_pytest_bridge import OchiaiBridgeLocation as _loc, SBFLPytestBridge as _bridge
        _pin_staging_sys_path()
        if cur_loc is _UNSET:
            OchiaiBridgeLocation = _loc
            _sync_facade_attr("OchiaiBridgeLocation", _loc)
        if cur_br is _UNSET:
            SBFLPytestBridge = _bridge
            _sync_facade_attr("SBFLPytestBridge", _bridge)


def _ensure_rsi_loaded() -> None:
    """Carica pigramente rsi_convergence_engine preservando eventuali override a None."""
    global RSIConvergenceEngine, RSIDefectVector, RSIIterationRecord, compute_delta, compute_fitness
    cur_eng = _facade_attr("RSIConvergenceEngine", RSIConvergenceEngine)
    cur_vec = _facade_attr("RSIDefectVector", RSIDefectVector)
    cur_rec = _facade_attr("RSIIterationRecord", RSIIterationRecord)
    cur_cd = _facade_attr("compute_delta", compute_delta)
    cur_cf = _facade_attr("compute_fitness", compute_fitness)
    if all(v is not _UNSET for v in (cur_eng, cur_vec, cur_rec, cur_cd, cur_cf)):
        return
    with _LAZY_LOAD_LOCK:
        cur_eng = _facade_attr("RSIConvergenceEngine", RSIConvergenceEngine)
        cur_vec = _facade_attr("RSIDefectVector", RSIDefectVector)
        cur_rec = _facade_attr("RSIIterationRecord", RSIIterationRecord)
        cur_cd = _facade_attr("compute_delta", compute_delta)
        cur_cf = _facade_attr("compute_fitness", compute_fitness)
        if all(v is not _UNSET for v in (cur_eng, cur_vec, cur_rec, cur_cd, cur_cf)):
            return
        loaded: tuple[Any, Any, Any, Any, Any]
        try:
            from rsi_convergence_engine import (
                RSIConvergenceEngine as _eng, RSIDefectVector as _vec,
                RSIIterationRecord as _rec, compute_delta as _cd, compute_fitness as _cf,
            )
            loaded = (_eng, _vec, _rec, _cd, _cf)
        except ImportError:
            try:
                from scripts.rsi_convergence_engine import (
                    RSIConvergenceEngine as _eng, RSIDefectVector as _vec,
                    RSIIterationRecord as _rec, compute_delta as _cd, compute_fitness as _cf,
                )
                loaded = (_eng, _vec, _rec, _cd, _cf)
            except ImportError:
                loaded = (None, None, None, None, None)
        _pin_staging_sys_path()
        if cur_eng is _UNSET:
            RSIConvergenceEngine = loaded[0]
            _sync_facade_attr("RSIConvergenceEngine", loaded[0])
        if cur_vec is _UNSET:
            RSIDefectVector = loaded[1]
            _sync_facade_attr("RSIDefectVector", loaded[1])
        if cur_rec is _UNSET:
            RSIIterationRecord = loaded[2]
            _sync_facade_attr("RSIIterationRecord", loaded[2])
        if cur_cd is _UNSET:
            compute_delta = loaded[3]
            _sync_facade_attr("compute_delta", loaded[3])
        if cur_cf is _UNSET:
            compute_fitness = loaded[4]
            _sync_facade_attr("compute_fitness", loaded[4])


def _ensure_ast_guard_loaded() -> None:
    """Carica pigramente ast_guard_validator preservando eventuali override a None."""
    global ASTGuardValidator
    if _facade_attr("ASTGuardValidator", ASTGuardValidator) is not _UNSET:
        return
    with _LAZY_LOAD_LOCK:
        if _facade_attr("ASTGuardValidator", ASTGuardValidator) is not _UNSET:
            return
        guard_cls: Any
        try:
            from ast_guard_validator import ASTGuardValidator as guard_cls
        except ImportError:
            try:
                from scripts.ast_guard_validator import ASTGuardValidator as guard_cls
            except ImportError:
                guard_cls = None
        _pin_staging_sys_path()
        ASTGuardValidator = guard_cls
        _sync_facade_attr("ASTGuardValidator", guard_cls)


class CodeSlice(BaseModel):
    """Frammento minimale di codice isolato intorno alla riga del guasto."""

    model_config = ConfigDict(strict=True, extra="forbid")
    start_line: int
    end_line: int
    target_line: int
    content: str
    function_name: Optional[str] = None


class HealingCycleLog(BaseModel):
    """Log strutturato di un singolo ciclo di auto-riparazione."""

    model_config = ConfigDict(strict=True, extra="forbid")
    cycle_index: int
    sbfl_payload: str
    fault_slice: str
    repair_action: str
    repair_success: bool
    duration_ms: float
    error_details: Optional[str] = None


class HealingResult(BaseModel):
    """Risultato finale dell'esecuzione con auto-riparazione."""

    model_config = ConfigDict(strict=True, extra="forbid")
    success: bool
    cycles_used: int
    max_cycles: int = MAX_HEALING_CYCLES
    history: List[HealingCycleLog] = Field(default_factory=list)
    output: Optional[Any] = None
    final_error: Optional[str] = None


class DSPyTelemetryRecord(BaseModel):
    """Record telemetrico per la distillazione degli episodi di riparazione."""

    model_config = ConfigDict(strict=True, extra="forbid")
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    task_name: str
    cycles_total: int
    final_status: str
    cycles_telemetry: List[Dict[str, Any]]


class AutoHealSessionReport(BaseModel):
    """Rapporto strutturato di una sessione di auto-riparazione con metriche RSI."""

    model_config = ConfigDict(strict=True, extra="forbid")
    success: bool
    cycles_used: int
    max_cycles: int
    initial_failed: int
    final_failed: int
    fault_location: Optional[str] = None
    error_type: Optional[str] = None
    ochiai_score: Optional[float] = None
    patch_note_line: Optional[str] = None
    rolled_back: bool = False
    rsi_delta: int = 0
    rsi_fitness_q: float = 100.0
    message: str


class KarpathySlicer:
    """Isola le righe di codice rilevanti intorno al guasto."""

    @staticmethod
    def slice_source(source_code: str, target_line: int, window: int = 4) -> CodeSlice:
        lines = source_code.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return CodeSlice(start_line=1, end_line=1, target_line=1, content="")

        clamped_target = max(1, min(target_line, total_lines))
        fn_name: Optional[str] = None
        start_line = max(1, clamped_target - window)
        end_line = min(total_lines, clamped_target + window)

        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                        if node.lineno <= clamped_target <= (node.end_lineno or clamped_target):
                            fn_name = node.name
                            if ((node.end_lineno or clamped_target) - node.lineno) <= 30:
                                start_line = max(node.lineno, clamped_target - window)
                                end_line = min(node.end_lineno or clamped_target, clamped_target + window)
                            break
        except Exception:
            pass

        sliced_lines = lines[start_line - 1 : end_line]
        formatted = "\n".join(f"{i + start_line:4d} | {line}" for i, line in enumerate(sliced_lines))
        return CodeSlice(
            start_line=start_line, end_line=end_line,
            target_line=clamped_target, content=formatted, function_name=fn_name,
        )

    @staticmethod
    def slice_file(file_path: Union[str, Path], target_line: int, window: int = 4) -> CodeSlice:
        p = Path(file_path)
        if not p.exists():
            return CodeSlice(
                start_line=target_line, end_line=target_line,
                target_line=target_line, content="<file not found>",
            )
        code = p.read_bytes().decode("utf-8", errors="replace")
        return KarpathySlicer.slice_source(code, target_line=target_line, window=window)


class DSPyTelemetryHook:
    """Registra gli episodi di riparazione su file JSONL."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path).resolve()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_run(self, record: DSPyTelemetryRecord) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")


def classify_failure(output_text: str, stderr_text: str = "", exit_code: int = 1) -> str:
    """Classifica il fallimento dando priorita a TimeoutExpired prima di AssertionError."""
    combined = f"{output_text or ''}\n{stderr_text or ''}"
    if "TimeoutExpired" in combined or "timeout" in combined.lower():
        return "TIMEOUT_ERROR"
    if "SyntaxError" in combined or "IndentationError" in combined:
        return "SYNTAX_ERROR"
    if "ImportError" in combined or "ModuleNotFoundError" in combined:
        return "IMPORT_ERROR"
    if "AssertionError" in combined:
        return "ASSERTION_ERROR"
    return "RUNTIME_ERROR" if exit_code != 0 else "NONE"


def normalize_test_command(cmd: Union[str, Sequence[str]]) -> Union[str, List[str]]:
    """Normalizza il comando pytest premettendo sys.executable -m pytest."""
    if isinstance(cmd, str):
        clean = cmd.strip()
        if clean == "pytest":
            return f'"{sys.executable}" -m pytest'
        if clean.startswith("pytest "):
            return f'"{sys.executable}" -m pytest {clean[7:].strip()}'
        return cmd
    if isinstance(cmd, (list, tuple)):
        cmd_list = list(cmd)
        if len(cmd_list) > 0 and str(cmd_list[0]).lower() == "pytest":
            return [sys.executable, "-m", "pytest"] + cmd_list[1:]
        return cmd_list
    return cmd

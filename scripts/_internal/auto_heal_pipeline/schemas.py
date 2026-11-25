# -*- coding: utf-8 -*-
"""Schemi Pydantic strict e costanti base per auto_heal_pipeline."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_HEALING_CYCLES: int = 3


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
    escalation_required: bool = False
    rsi_delta: int = 0
    rsi_fitness_q: float = 100.0
    message: str


class DiagnoseSliceReport(BaseModel):
    """Rapporto diagnostico single-pass read-only (--diagnose-slice) senza patch automatiche."""

    model_config = ConfigDict(strict=True, extra="forbid")
    success: bool
    target_file: str
    exit_code: int
    tests_passed: int
    tests_failed: int
    failure_category: str
    fault_location: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    ochiai_score: Optional[float] = None
    n_ef: int = 0
    n_ep: int = 0
    code_slice_tokens: int = 0
    code_slice: Optional[CodeSlice] = None
    rsi_delta: int = 0
    rsi_fitness_q: float = 0.0
    message: str

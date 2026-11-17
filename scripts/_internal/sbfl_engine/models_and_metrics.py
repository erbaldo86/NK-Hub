"""Modelli Pydantic, metriche Ochiai/Tarantula/DStar e filtro Tri-Pass SBFL."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.transcript_guards import (
    estimate_tokens as _shared_estimate_tokens,
)

SBFL_MAX_TOKEN_BUDGET: int = 80


def estimate_token_count(text: str) -> int:
    """Stima in modo deterministico il numero di token tramite nk_common."""
    return _shared_estimate_tokens(text)


def _sbfl_sys() -> Any:
    """Restituisce il modulo sys eventualmente patchato sulla facciata sbfl_engine."""
    for mod_name in ("sbfl_engine", "scripts.sbfl_engine"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            cand = getattr(mod, "sys", None)
            if cand is not None:
                return cand
    for mod in list(sys.modules.values()):
        mfile = getattr(mod, "__file__", "") or ""
        if mfile.endswith(("sbfl_engine.py", "sbfl_engine.pyc")):
            cand = getattr(mod, "sys", None)
            if cand is not None:
                return cand
    return sys


def _sbfl_conflict_fn() -> Callable[[], bool]:
    """Risolve eventuale override di is_monitoring_conflict_active sul facade."""
    facade = sys.modules.get("sbfl_engine")
    for mod in (facade, *reversed(list(sys.modules.values()))):
        if mod is None:
            continue
        mod_file = getattr(mod, "__file__", "") or ""
        if mod is facade or mod_file.endswith(("sbfl_engine.py", "sbfl_engine.pyc")):
            fn = getattr(mod, "is_monitoring_conflict_active", None)
            if callable(fn) and fn is not is_monitoring_conflict_active:
                return fn
    return is_monitoring_conflict_active


def is_monitoring_conflict_active() -> bool:
    """Rileva se sys.gettrace, pytest-cov o sys.monitoring sono gia attivi."""
    sys_mod = _sbfl_sys()
    gettrace_fn = getattr(sys_mod, "gettrace", None)
    if callable(gettrace_fn) and gettrace_fn() is not None:
        return True
    sys_modules = getattr(sys_mod, "modules", sys.modules)
    if (
        "pytest_cov" in sys_modules
        or "coverage" in sys_modules
        or bool(os.environ.get("COV_CORE_SOURCE"))
    ):
        return True
    monitoring_mod = getattr(sys_mod, "monitoring", None)
    if monitoring_mod is not None:
        get_tool = getattr(monitoring_mod, "get_tool", None)
        if callable(get_tool):
            for tool_id in range(6):
                try:
                    if get_tool(tool_id) is not None:
                        return True
                except ValueError:
                    continue
    return False


def collect_statements_with_monitoring(
    fn: Callable[[], Any],
    target_filename_filter: Optional[str] = None,
) -> Tuple[bool, Set[str]]:
    """Raccoglie le righe eseguite con sys.monitoring saltando se un tracer e gia attivo."""
    executed: Set[str] = set()
    if _sbfl_conflict_fn()():
        fn()
        return False, executed

    monitoring_mod = getattr(_sbfl_sys(), "monitoring", None)
    if monitoring_mod is None:
        fn()
        return False, executed

    selected_tool_id: Optional[int] = None
    for cand_id in (4, 3, 2):
        try:
            if monitoring_mod.get_tool(cand_id) is None:
                monitoring_mod.use_tool_id(cand_id, "nk_sbfl_monitor")
                selected_tool_id = cand_id
                break
        except ValueError:
            continue

    if selected_tool_id is None:
        fn()
        return False, executed

    def _on_line(code_obj: Any, line_number: int) -> Any:
        fname = str(getattr(code_obj, "co_filename", "")).replace("\\", "/")
        if target_filename_filter and target_filename_filter not in fname:
            return None
        if line_number and line_number > 0:
            executed.add(f"{fname}:{line_number}")
        return None

    try:
        line_event = monitoring_mod.events.LINE
        monitoring_mod.register_callback(selected_tool_id, line_event, _on_line)
        monitoring_mod.set_events(selected_tool_id, line_event)
        fn()
        return True, executed
    finally:
        try:
            monitoring_mod.set_events(selected_tool_id, 0)
            monitoring_mod.register_callback(
                selected_tool_id, monitoring_mod.events.LINE, None
            )
            monitoring_mod.free_tool_id(selected_tool_id)
        except Exception:
            pass


class SpectrumCounts(BaseModel):
    """Conteggi delle esecuzioni di test per una specifica istruzione di codice."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    n_ef: int = Field(ge=0, description="Test falliti che eseguono l'istruzione")
    n_ep: int = Field(ge=0, description="Test passati che eseguono l'istruzione")
    n_nf: int = Field(ge=0, description="Test falliti che non eseguono l'istruzione")
    n_np: int = Field(ge=0, description="Test passati che non eseguono l'istruzione")

    @property
    def total_failed(self) -> int:
        return self.n_ef + self.n_nf

    @property
    def total_passed(self) -> int:
        return self.n_ep + self.n_np

    @property
    def total_executed(self) -> int:
        return self.n_ef + self.n_ep

    @property
    def total_tests(self) -> int:
        return self.n_ef + self.n_ep + self.n_nf + self.n_np


class CoverageRecord(BaseModel):
    """Record di copertura per l'esecuzione di un singolo caso di test."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    test_id: str
    passed: bool
    executed_statements: List[str] = Field(default_factory=list)


class SBFLScore(BaseModel):
    """Metriche SBFL calcolate per una singola istruzione."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    statement: str
    ochiai: float = Field(ge=0.0, le=1.0)
    tarantula: float = Field(ge=0.0, le=1.0)
    dstar: float = Field(ge=0.0)
    calibrated_ochiai: float = Field(ge=0.0, le=1.0)
    spectrum: SpectrumCounts
    rank: int = Field(ge=1, default=1)


class SBFLLocation(BaseModel):
    """Posizione del guasto localizzata tramite SBFL Ochiai."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file_path: str = Field(description="Percorso del file in cui si trova il guasto")
    line_number: int = Field(ge=1, description="Numero di riga (1-indexed)")
    suspiciousness: float = Field(
        ge=0.0, le=1.0, description="Punteggio di sospettosita Ochiai"
    )
    error_type: str = Field(description="Tipo di eccezione o fallimento")
    error_message: str = Field(description="Messaggio di errore sintetico")
    failing_line_content: str = Field(description="Contenuto della riga fallita")

    def to_compact_payload(self) -> Dict[str, Any]:
        """Genera un dizionario compatto garantito sotto 80 token."""
        short_path = (
            Path(self.file_path).name if len(self.file_path) > 30 else self.file_path
        )
        short_msg = (
            (self.error_message[:45] + "...")
            if len(self.error_message) > 45
            else self.error_message
        )
        short_ctx = self.failing_line_content.strip()[:40]
        return {
            "loc": f"{short_path}:{self.line_number}",
            "err": f"{self.error_type}: {short_msg}",
            "score": round(self.suspiciousness, 3),
            "ctx": short_ctx,
        }

    def render_payload_json(self) -> str:
        """Restituisce la stringa JSON compatta sotto gli 80 token."""
        payload = self.to_compact_payload()
        rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if estimate_token_count(rendered) > SBFL_MAX_TOKEN_BUDGET:
            payload["ctx"] = payload["ctx"][:20]
            payload["err"] = payload["err"][:30]
            rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return rendered


class TriPassFilterResult(BaseModel):
    """Risultato del filtro Tri-Pass Voting per l'eliminazione dei test flaky."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    retained_records: List[CoverageRecord]
    flaky_test_ids: List[str]
    total_analyzed: int
    deterministic_ratio: float = Field(ge=0.0, le=1.0)


def calculate_ochiai(spectrum: SpectrumCounts) -> float:
    """Calcola la metrica di sospettosita Ochiai: n_ef / sqrt(n_f * (n_ef + n_ep))."""
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)
    total_exec = float(spectrum.total_executed)

    denominator = math.sqrt(n_f * total_exec)
    if denominator == 0.0:
        return 0.0

    score = n_ef / denominator
    return min(1.0, max(0.0, score))


def calculate_tarantula(spectrum: SpectrumCounts) -> float:
    """Calcola la metrica di sospettosita Tarantula."""
    n_f = float(spectrum.total_failed)
    n_p = float(spectrum.total_passed)

    if n_f == 0.0:
        return 0.0

    fail_ratio = float(spectrum.n_ef) / n_f

    if n_p == 0.0:
        return 1.0 if fail_ratio > 0.0 else 0.0

    pass_ratio = float(spectrum.n_ep) / n_p

    denominator = fail_ratio + pass_ratio
    if denominator == 0.0:
        return 0.0

    score = fail_ratio / denominator
    return min(1.0, max(0.0, score))


def calculate_dstar(spectrum: SpectrumCounts, alpha: float = 2.0) -> float:
    """Calcola la metrica di sospettosita DStar (D*): (n_ef ^ alpha) / (n_ep + n_nf)."""
    n_ef = float(spectrum.n_ef)
    if n_ef == 0.0:
        return 0.0

    denominator = float(spectrum.n_ep + spectrum.n_nf)
    if denominator == 0.0:
        return float(1_000_000.0 * (n_ef**alpha))

    return (n_ef**alpha) / denominator


def calibrate_coincidental_correctness(
    spectrum: SpectrumCounts,
    def_use_weight: float = 0.0,
    gamma: float = 0.5,
) -> float:
    """Calibra il punteggio Ochiai scontando n_ep tramite il fattore di propagazione Def-Use."""
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)

    weight = min(1.0, max(0.0, def_use_weight))
    g = min(1.0, max(0.0, gamma))

    discount = 1.0 - (g * weight)
    n_ep_adj = float(spectrum.n_ep) * discount

    denominator = math.sqrt(n_f * (n_ef + n_ep_adj))
    if denominator == 0.0:
        return 0.0

    score = n_ef / denominator
    return min(1.0, max(0.0, score))


def tri_pass_voting_filter(
    pass_runs: Sequence[Sequence[CoverageRecord]],
) -> TriPassFilterResult:
    """Applica il filtro Tri-Pass mantenendo solo i test con esito unanime 3 su 3."""
    if len(pass_runs) < 3:
        raise ValueError(
            f"Tri-Pass filter requires exactly 3 run passes, got {len(pass_runs)}"
        )

    pass_maps: List[Dict[str, CoverageRecord]] = []
    for run in pass_runs[:3]:
        p_map = {rec.test_id: rec for rec in run}
        pass_maps.append(p_map)

    all_test_ids = sorted(
        set(pass_maps[0].keys())
        & set(pass_maps[1].keys())
        & set(pass_maps[2].keys())
    )

    retained_records: List[CoverageRecord] = []
    flaky_test_ids: List[str] = []

    for t_id in all_test_ids:
        r1 = pass_maps[0][t_id]
        r2 = pass_maps[1][t_id]
        r3 = pass_maps[2][t_id]

        outcomes = (r1.passed, r2.passed, r3.passed)

        if outcomes == (True, True, True):
            unified_stmts = sorted(
                set(r1.executed_statements)
                | set(r2.executed_statements)
                | set(r3.executed_statements)
            )
            retained_records.append(
                CoverageRecord(
                    test_id=t_id, passed=True, executed_statements=unified_stmts
                )
            )
        elif outcomes == (False, False, False):
            unified_stmts = sorted(
                set(r1.executed_statements)
                | set(r2.executed_statements)
                | set(r3.executed_statements)
            )
            retained_records.append(
                CoverageRecord(
                    test_id=t_id, passed=False, executed_statements=unified_stmts
                )
            )
        else:
            flaky_test_ids.append(t_id)

    total = len(all_test_ids)
    det_ratio = float(len(retained_records)) / float(total) if total > 0 else 1.0

    return TriPassFilterResult(
        retained_records=retained_records,
        flaky_test_ids=flaky_test_ids,
        total_analyzed=total,
        deterministic_ratio=det_ratio,
    )

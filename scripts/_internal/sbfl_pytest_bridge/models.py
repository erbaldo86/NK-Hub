"""Modelli Pydantic, metriche Ochiai/Tarantula/DStar, Tri-Pass e monitoring SSOT per SBFL."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field


from _internal.sbfl_pytest_bridge import _ensure_staging_pkg

_ensure_staging_pkg(Path(__file__).resolve().parent)

from _internal.nk_common.transcript_guards import (
    estimate_tokens as _shared_estimate_tokens,
)
from _internal.sbfl_pytest_bridge.scoring_helpers import (  # noqa: F401
    CoverageRecord,
    SpectrumCounts,
    TriPassFilterResult,
    calculate_dstar,
    calculate_ochiai,
    calculate_tarantula,
    calibrate_coincidental_correctness,
    compute_ochiai,
    tri_pass_voting_filter,
)

SBFL_MAX_TOKEN_BUDGET: int = 80


def estimate_token_count(text: str) -> int:
    """Stima in modo deterministico il numero di token tramite nk_common."""
    return _shared_estimate_tokens(text)


def _sbfl_sys() -> Any:
    """Restituisce il modulo sys eventualmente patchato sulla facciata SSOT."""
    for mod_name in (
        "sbfl_pytest_bridge",
        "scripts.sbfl_pytest_bridge",
        "sbfl_engine",
        "scripts.sbfl_engine",
    ):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            cand = getattr(mod, "sys", None)
            if cand is not None:
                return cand
    for mod in list(sys.modules.values()):
        mfile = getattr(mod, "__file__", "") or ""
        if mfile.endswith(
            (
                "sbfl_pytest_bridge.py",
                "sbfl_pytest_bridge.pyc",
                "sbfl_engine.py",
                "sbfl_engine.pyc",
            )
        ):
            cand = getattr(mod, "sys", None)
            if cand is not None:
                return cand
    return sys


def _sbfl_conflict_fn() -> Callable[[], bool]:
    """Risolve eventuale override di is_monitoring_conflict_active sulla facciata."""
    fac_a = sys.modules.get("sbfl_pytest_bridge")
    fac_b = sys.modules.get("sbfl_engine")
    for mod in (fac_a, fac_b, *reversed(list(sys.modules.values()))):
        if mod is None:
            continue
        mod_file = getattr(mod, "__file__", "") or ""
        if (
            mod is fac_a
            or mod is fac_b
            or mod_file.endswith(
                (
                    "sbfl_pytest_bridge.py",
                    "sbfl_pytest_bridge.pyc",
                    "sbfl_engine.py",
                    "sbfl_engine.pyc",
                )
            )
        ):
            fn = getattr(mod, "is_monitoring_conflict_active", None)
            if callable(fn) and fn is not is_monitoring_conflict_active:
                return fn
    return is_monitoring_conflict_active


def _has_active_monitoring_tool(monitoring_mod: Any) -> bool:
    """Verifica se sys.monitoring ha almeno un tool_id registrato."""
    get_tool = getattr(monitoring_mod, "get_tool", None)
    if not callable(get_tool):
        return False
    for tool_id in range(6):
        try:
            if get_tool(tool_id) is not None:
                return True
        except ValueError:
            continue
    return False


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
    return bool(monitoring_mod is not None and _has_active_monitoring_tool(monitoring_mod))


def _activate_line_monitoring(
    monitoring_mod: Any, tool_id: int, line_event: Any, callback: Any
) -> None:
    """Registra callback LINE, ripristina eventuali eventi DISABLE e attiva il tool."""
    monitoring_mod.register_callback(tool_id, line_event, callback)
    restart_fn = getattr(monitoring_mod, "restart_events", None)
    if callable(restart_fn):
        restart_fn()
    monitoring_mod.set_events(tool_id, line_event)


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
    for cand_id in (3, 4, 2):
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

    disable_sentinel = getattr(monitoring_mod, "DISABLE", None)

    def _on_line(code_obj: Any, line_number: int) -> Any:
        fname = str(getattr(code_obj, "co_filename", "")).replace("\\", "/")
        if target_filename_filter and target_filename_filter not in fname:
            return disable_sentinel
        if line_number and line_number > 0:
            executed.add(f"{fname}:{line_number}")
        return disable_sentinel

    try:
        _activate_line_monitoring(
            monitoring_mod, selected_tool_id, monitoring_mod.events.LINE, _on_line
        )
        fn()
        return True, executed
    finally:
        try:
            monitoring_mod.set_events(selected_tool_id, 0)
            monitoring_mod.register_callback(
                selected_tool_id, monitoring_mod.events.LINE, None
            )
            monitoring_mod.free_tool_id(selected_tool_id)
        except (ValueError, RuntimeError, AttributeError) as exc:
            _ = str(exc)


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


class PytestRunSummary(BaseModel):
    """Riepilogo strutturato di un'esecuzione pytest."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    total_tests: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    exit_code: int
    duration_sec: float = Field(ge=0.0)
    failed_test_names: List[str] = Field(default_factory=list)
    passed_test_names: List[str] = Field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""


def _trim_compact_payload_if_needed(payload: Dict[str, Any]) -> str:
    """Serializza e riduce il payload compatto sotto 80 token e 320 caratteri."""
    rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if estimate_token_count(rendered) > SBFL_MAX_TOKEN_BUDGET or len(rendered) >= 320:
        payload["ctx"] = str(payload.get("ctx", ""))[:15]
        payload["err"] = str(payload.get("err", ""))[:25]
        rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if estimate_token_count(rendered) > SBFL_MAX_TOKEN_BUDGET or len(rendered) >= 320:
        for opt_key in ("dst", "tar", "spec"):
            payload.pop(opt_key, None)
        rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return rendered


def _build_compact_location_payload(loc: Any) -> Dict[str, Any]:
    """Costruisce il dizionario compatto condiviso sotto 80 token (< 320 caratteri)."""
    short_file = Path(loc.file_path).name if len(loc.file_path) > 30 else loc.file_path
    short_msg = (
        (loc.error_message[:40] + "...")
        if len(loc.error_message) > 40
        else loc.error_message
    )
    short_ctx = loc.failing_line_content.strip()[:35]
    return {
        "loc": f"{short_file}:{loc.line_number}",
        "err": f"{loc.error_type}: {short_msg}",
        "score": round(loc.suspiciousness, 3),
        "ctx": short_ctx,
        "spec": [loc.n_ef, loc.n_ep, loc.n_nf, loc.n_np],
        "tar": round(loc.tarantula, 3),
        "dst": round(loc.dstar, 3),
    }


class OchiaiBridgeLocation(BaseModel):
    """Record unificato di localizzazione del guasto calcolato tramite SBFL."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file_path: str = Field(description="Percorso del file in cui si trova il guasto")
    line_number: int = Field(ge=1, description="Numero di riga (1-indexed)")
    suspiciousness: float = Field(
        ge=0.0, le=1.0, description="Punteggio di sospettosita Ochiai"
    )
    error_type: str = Field(description="Tipo di eccezione o fallimento")
    error_message: str = Field(description="Messaggio di errore sintetico")
    failing_line_content: str = Field(
        default="", description="Contenuto della riga fallita"
    )
    total_failed_tests: int = Field(ge=0, default=1)
    n_ef: int = Field(ge=0, default=1)
    n_ep: int = Field(ge=0, default=0)
    n_nf: int = Field(ge=0, default=0)
    n_np: int = Field(ge=0, default=0)
    tarantula: float = Field(ge=0.0, le=1.0, default=0.0)
    dstar: float = Field(ge=0.0, default=0.0)

    def to_compact_payload(self) -> Dict[str, Any]:
        """Genera un dizionario compatto garantito sotto 80 token (< 320 caratteri)."""
        return _build_compact_location_payload(self)

    def render_payload_json(self) -> str:
        """Serializza il dizionario compatto sotto 80 token e 320 caratteri (GT-07)."""
        return _trim_compact_payload_if_needed(self.to_compact_payload())


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
    failing_line_content: str = Field(
        default="", description="Contenuto della riga fallita"
    )
    total_failed_tests: int = Field(ge=0, default=1)
    n_ef: int = Field(ge=0, default=1)
    n_ep: int = Field(ge=0, default=0)
    n_nf: int = Field(ge=0, default=0)
    n_np: int = Field(ge=0, default=0)
    tarantula: float = Field(ge=0.0, le=1.0, default=0.0)
    dstar: float = Field(ge=0.0, default=0.0)

    def to_compact_payload(self) -> Dict[str, Any]:
        """Genera un dizionario compatto garantito sotto 80 token (< 320 caratteri)."""
        return _build_compact_location_payload(self)

    def render_payload_json(self) -> str:
        """Serializza il dizionario compatto sotto 80 token e 320 caratteri (GT-07)."""
        return _trim_compact_payload_if_needed(self.to_compact_payload())

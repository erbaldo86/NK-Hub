#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper compatibile per l'Invisible Healing Loop di Nexus Keystone v3.0.0.
Modulo: invisible_healing_loop.py.
Delega il calcolo Ochiai a sbfl_engine.py e l'esecuzione CLI a auto_heal_pipeline.py.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field

_scripts_dir = Path(__file__).resolve().parent
_root_dir = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
for _d in (
    _scripts_dir,
    _root_dir / "scripts",
    _root_dir / ".staging" / "scripts",
    _root_dir,
):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from sbfl_engine import SpectrumCounts, calculate_ochiai
except ImportError:
    from scripts.sbfl_engine import SpectrumCounts, calculate_ochiai

try:
    from auto_heal_pipeline import AutoHealPipeline, AutoHealSessionReport
except ImportError:
    from scripts.auto_heal_pipeline import AutoHealPipeline, AutoHealSessionReport

MAX_HEALING_CYCLES: int = 3
SBFL_MAX_TOKEN_BUDGET: int = 80

T = TypeVar("T")


def estimate_token_count(text: str) -> int:
    """Stima deterministica del numero di token di una stringa."""
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, math.ceil(len(words) * 1.15))


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
        tok_count = estimate_token_count(rendered)
        if tok_count > SBFL_MAX_TOKEN_BUDGET:
            payload["ctx"] = payload["ctx"][:20]
            payload["err"] = payload["err"][:30]
            rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return rendered


class CodeSlice(BaseModel):
    """Frammento minimale di codice isolato intorno alla riga del guasto."""

    model_config = ConfigDict(strict=True, extra="forbid")

    start_line: int
    end_line: int
    target_line: int
    content: str
    function_name: Optional[str] = None


class HealingCycleLog(BaseModel):
    """Log di un singolo ciclo di auto-riparazione."""

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


class KarpathySlicer:
    """Isola le righe di codice rilevanti intorno al guasto."""

    @staticmethod
    def slice_source(
        source_code: str,
        target_line: int,
        window: int = 4,
    ) -> CodeSlice:
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
                        if (
                            node.lineno
                            <= clamped_target
                            <= (node.end_lineno or clamped_target)
                        ):
                            fn_name = node.name
                            if (node.end_lineno - node.lineno) <= 30:
                                start_line = max(node.lineno, clamped_target - window)
                                end_line = min(node.end_lineno, clamped_target + window)
                            break
        except Exception:
            pass

        sliced_lines = lines[start_line - 1 : end_line]
        formatted = "\n".join(
            f"{i + start_line:4d} | {line}" for i, line in enumerate(sliced_lines)
        )

        return CodeSlice(
            start_line=start_line,
            end_line=end_line,
            target_line=clamped_target,
            content=formatted,
            function_name=fn_name,
        )

    @staticmethod
    def slice_file(
        file_path: Union[str, Path], target_line: int, window: int = 4
    ) -> CodeSlice:
        p = Path(file_path)
        if not p.exists():
            return CodeSlice(
                start_line=target_line,
                end_line=target_line,
                target_line=target_line,
                content="<file not found>",
            )
        code = p.read_text(encoding="utf-8")
        return KarpathySlicer.slice_source(code, target_line=target_line, window=window)


class SBFLEngine:
    """Adattatore che delega il calcolo Ochiai a scripts/sbfl_engine.py."""

    @staticmethod
    def extract_from_exception(
        exc: BaseException, relevant_file_hint: Optional[str] = None
    ) -> SBFLLocation:
        tb = exc.__traceback__
        frames = traceback.extract_tb(tb)
        spectrum = SpectrumCounts(n_ef=1, n_ep=0, n_nf=0, n_np=0)
        ochiai_score = calculate_ochiai(spectrum)

        if not frames:
            return SBFLLocation(
                file_path="unknown",
                line_number=1,
                suspiciousness=ochiai_score,
                error_type=type(exc).__name__,
                error_message=str(exc),
                failing_line_content="",
            )

        target_frame = frames[-1]
        if relevant_file_hint:
            for f in reversed(frames):
                if relevant_file_hint in f.filename:
                    target_frame = f
                    break

        line_no = target_frame.lineno or 1
        line_code = target_frame.line or ""

        return SBFLLocation(
            file_path=target_frame.filename,
            line_number=line_no,
            suspiciousness=ochiai_score,
            error_type=type(exc).__name__,
            error_message=str(exc),
            failing_line_content=line_code,
        )


class DSPyTelemetryHook:
    """Registra gli episodi di riparazione su file JSONL."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path).resolve()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_run(self, record: DSPyTelemetryRecord) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")


class InvisibleHealingLoop:
    """Orchestratore compatibile che integra SBFLEngine e AutoHealPipeline."""

    def __init__(
        self,
        telemetry_log_path: Optional[Path] = None,
        max_cycles: int = MAX_HEALING_CYCLES,
    ) -> None:
        self.max_cycles = max_cycles
        self.telemetry_hook = (
            DSPyTelemetryHook(telemetry_log_path) if telemetry_log_path else None
        )

    def run_cli_pipeline(
        self,
        test_cmd: Union[str, List[str]],
        target_file: Union[str, Path],
        cwd: Optional[Path] = None,
    ) -> AutoHealSessionReport:
        """Delega l'esecuzione del ciclo di riparazione su file a AutoHealPipeline."""
        pipeline = AutoHealPipeline(cwd=cwd, max_cycles=self.max_cycles)
        return pipeline.run_pipeline(test_cmd=test_cmd, target_file=target_file)

    def execute_with_healing(
        self,
        task_name: str,
        target_fn: Callable[[], T],
        repair_fn: Callable[[SBFLLocation, CodeSlice, int], Any],
        source_file_hint: Optional[str] = None,
    ) -> HealingResult:
        """Esegue target_fn con localizzazione SBFL e fino a max_cycles tentativi."""
        history: List[HealingCycleLog] = []
        run_id = f"heal_{int(time.time() * 1000)}"

        for cycle in range(1, self.max_cycles + 1):
            t0 = time.time()
            try:
                result = target_fn()
                if cycle == 1 and not history:
                    return HealingResult(
                        success=True,
                        cycles_used=1,
                        history=[],
                        output=result,
                    )
                self._record_telemetry(
                    run_id=run_id,
                    task_name=task_name,
                    cycles_total=cycle,
                    status="HEALED",
                    history=history,
                )
                return HealingResult(
                    success=True,
                    cycles_used=cycle,
                    history=history,
                    output=result,
                )

            except Exception as exc:
                elapsed_ms = (time.time() - t0) * 1000.0
                sbfl_loc = SBFLEngine.extract_from_exception(
                    exc, relevant_file_hint=source_file_hint
                )
                compact_json = sbfl_loc.render_payload_json()
                code_slice = KarpathySlicer.slice_file(
                    sbfl_loc.file_path, sbfl_loc.line_number
                )

                repair_action_summary = "NO_ACTION"
                repair_success = False

                if cycle < self.max_cycles:
                    try:
                        patch_result = repair_fn(sbfl_loc, code_slice, cycle)
                        repair_action_summary = str(patch_result)
                        repair_success = True
                    except Exception as rep_err:
                        repair_action_summary = f"REPAIR_FAILED: {rep_err}"

                cycle_log = HealingCycleLog(
                    cycle_index=cycle,
                    sbfl_payload=compact_json,
                    fault_slice=code_slice.content,
                    repair_action=repair_action_summary,
                    repair_success=repair_success,
                    duration_ms=elapsed_ms,
                    error_details=f"{type(exc).__name__}: {str(exc)}",
                )
                history.append(cycle_log)

                if cycle == self.max_cycles:
                    self._record_telemetry(
                        run_id=run_id,
                        task_name=task_name,
                        cycles_total=self.max_cycles,
                        status="ESCALATED",
                        history=history,
                    )
                    return HealingResult(
                        success=False,
                        cycles_used=self.max_cycles,
                        history=history,
                        output=None,
                        final_error=f"{type(exc).__name__}: {str(exc)}",
                    )

        return HealingResult(
            success=False,
            cycles_used=self.max_cycles,
            history=history,
            final_error="Exhausted maximum healing cycles.",
        )

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
        rec = DSPyTelemetryRecord(
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
    parser.add_argument("--max-cycles", type=int, default=MAX_HEALING_CYCLES)
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

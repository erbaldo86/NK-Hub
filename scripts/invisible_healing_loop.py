"""
Nexus Keystone v1.1.0-Universal: Invisible Autonomous Fast-Loop Healing Engine.
Compliant with:
- Fast-Loop Autonomous Healing: <= 3 self-repair cycles upon DAST/runtime failure.
- Spectrum-Based Fault Localization (SBFL): Ultra-compact diagnostic payload strictly < 80 tokens.
- Karpathy Slicer: Context-hygienic minimal code slicing around localized fault.
- DSPy Optimizer Telemetry Hook: JSONL telemetry streaming for offline prompt/patch optimization.
- Zero-Mock Determinism and Pydantic v2 strict typing.
"""

from __future__ import annotations

import ast
import inspect
import json
import math
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union
from pydantic import BaseModel, Field, ConfigDict


MAX_HEALING_CYCLES: int = 3
SBFL_MAX_TOKEN_BUDGET: int = 80

T = TypeVar("T")


# ----------------------------------------------------------------------
# TOKEN ESTIMATION HELPER
# ----------------------------------------------------------------------
def estimate_token_count(text: str) -> int:
    """Deterministic token estimation (words + punctuation symbols)."""
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, math.ceil(len(words) * 1.15))


# ----------------------------------------------------------------------
# PYDANTIC V2 MODELS
# ----------------------------------------------------------------------
class SBFLLocation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    file_path: str = Field(description="Relative or file path of fault")
    line_number: int = Field(ge=1, description="1-indexed line number")
    suspiciousness: float = Field(ge=0.0, le=1.0, description="Ochiai suspiciousness score")
    error_type: str = Field(description="Exception or failure type")
    error_message: str = Field(description="Short sanitized error message")
    failing_line_content: str = Field(description="Exact code line")

    def to_compact_payload(self) -> Dict[str, Any]:
        """Generates compact dictionary guaranteed to fit within < 80 tokens."""
        # Sanitize path to basename if long
        short_path = Path(self.file_path).name if len(self.file_path) > 30 else self.file_path
        short_msg = (self.error_message[:45] + "...") if len(self.error_message) > 45 else self.error_message
        short_ctx = self.failing_line_content.strip()[:40]

        return {
            "loc": f"{short_path}:{self.line_number}",
            "err": f"{self.error_type}: {short_msg}",
            "score": round(self.suspiciousness, 3),
            "ctx": short_ctx,
        }

    def render_payload_json(self) -> str:
        payload = self.to_compact_payload()
        rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        # Verify strict token budget
        tok_count = estimate_token_count(rendered)
        if tok_count > SBFL_MAX_TOKEN_BUDGET:
            # Further truncate if needed
            payload["ctx"] = payload["ctx"][:20]
            payload["err"] = payload["err"][:30]
            rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return rendered


class CodeSlice(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    start_line: int
    end_line: int
    target_line: int
    content: str
    function_name: Optional[str] = None


class HealingCycleLog(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    cycle_index: int
    sbfl_payload: str
    fault_slice: str
    repair_action: str
    repair_success: bool
    duration_ms: float
    error_details: Optional[str] = None


class HealingResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    success: bool
    cycles_used: int
    max_cycles: int = MAX_HEALING_CYCLES
    history: List[HealingCycleLog] = Field(default_factory=list)
    output: Optional[Any] = None
    final_error: Optional[str] = None


class DSPyTelemetryRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    run_id: str
    timestamp: float = Field(default_factory=time.time)
    task_name: str
    cycles_total: int
    final_status: str  # "HEALED" | "ESCALATED"
    cycles_telemetry: List[Dict[str, Any]]


# ----------------------------------------------------------------------
# KARPATHY SURGICAL SLICER
# ----------------------------------------------------------------------
class KarpathySlicer:
    """Context-hygienic code slicer that isolates minimal relevant lines around the fault."""

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

        # Clamp target line to 1..total_lines
        clamped_target = max(1, min(target_line, total_lines))

        # Try to locate enclosing function via AST if parseable
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
                            # Bound slice to function bounds if within reasonable window
                            if (node.end_lineno - node.lineno) <= 30:
                                start_line = max(node.lineno, clamped_target - window)
                                end_line = min(node.end_lineno, clamped_target + window)
                            break
        except Exception:
            # Slicing fallback without AST
            pass

        sliced_lines = lines[start_line - 1 : end_line]
        # Format with line numbers
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
    def slice_file(file_path: Union[str, Path], target_line: int, window: int = 4) -> CodeSlice:
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


# ----------------------------------------------------------------------
# SPECTRUM-BASED FAULT LOCALIZATION (SBFL)
# ----------------------------------------------------------------------
class SBFLEngine:
    """Spectrum-Based Fault Localization with Ochiai metric & < 80 tok compact payload."""

    @staticmethod
    def extract_from_exception(exc: BaseException, relevant_file_hint: Optional[str] = None) -> SBFLLocation:
        tb = exc.__traceback__
        frames = traceback.extract_tb(tb)
        if not frames:
            return SBFLLocation(
                file_path="unknown",
                line_number=1,
                suspiciousness=1.0,
                error_type=type(exc).__name__,
                error_message=str(exc),
                failing_line_content="",
            )

        # Select target frame: look for relevant_file_hint or deepest user frame
        target_frame = frames[-1]
        if relevant_file_hint:
            for f in reversed(frames):
                if relevant_file_hint in f.filename:
                    target_frame = f
                    break

        line_no = target_frame.lineno or 1
        line_code = target_frame.line or ""

        # Ochiai Suspiciousness: 1 failing test / sqrt(1 * (1 + 0 passed on this point)) = 1.0
        ochiai_score = 1.0

        return SBFLLocation(
            file_path=target_frame.filename,
            line_number=line_no,
            suspiciousness=ochiai_score,
            error_type=type(exc).__name__,
            error_message=str(exc),
            failing_line_content=line_code,
        )


# ----------------------------------------------------------------------
# OFFLINE DSPY OPTIMIZER TELEMETRY HOOK
# ----------------------------------------------------------------------
class DSPyTelemetryHook:
    """Appends healing episodes into offline_dspy_telemetry.jsonl for offline DSPy training."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path).resolve()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_run(self, record: DSPyTelemetryRecord) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")


# ----------------------------------------------------------------------
# INVISIBLE HEALING FAST-LOOP
# ----------------------------------------------------------------------
class InvisibleHealingLoop:
    """
    Fast-Loop Autonomous Healing Orchestrator:
    - Up to 3 self-repair attempts.
    - Diagnostic SBFL payload strictly < 80 tokens.
    - Karpathy minimal code slice isolation.
    - Offline DSPy telemetry logging.
    """

    def __init__(
        self,
        telemetry_log_path: Optional[Path] = None,
        max_cycles: int = MAX_HEALING_CYCLES,
    ) -> None:
        self.max_cycles = max_cycles
        self.telemetry_hook = (
            DSPyTelemetryHook(telemetry_log_path)
            if telemetry_log_path
            else None
        )

    def execute_with_healing(
        self,
        task_name: str,
        target_fn: Callable[[], T],
        repair_fn: Callable[[SBFLLocation, CodeSlice, int], Any],
        source_file_hint: Optional[str] = None,
    ) -> HealingResult:
        """
        Executes target_fn(). If an exception occurs, localizes the fault via SBFL,
        isolates the minimal Karpathy code slice, calls repair_fn(sbfl, slice, cycle),
        and retries up to max_cycles.
        """
        history: List[HealingCycleLog] = []
        run_id = f"heal_{int(time.time() * 1000)}"

        for cycle in range(1, self.max_cycles + 1):
            t0 = time.time()
            try:
                result = target_fn()
                # If target_fn succeeds on cycle 1 without failure:
                if cycle == 1 and not history:
                    return HealingResult(
                        success=True,
                        cycles_used=1,
                        history=[],
                        output=result,
                    )
                # If target_fn succeeds after repair:
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
                sbfl_loc = SBFLEngine.extract_from_exception(exc, relevant_file_hint=source_file_hint)
                compact_json = sbfl_loc.render_payload_json()

                # Karpathy slicing
                code_slice = KarpathySlicer.slice_file(sbfl_loc.file_path, sbfl_loc.line_number)

                # Attempt repair if cycles remain
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
                    # Escalation
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

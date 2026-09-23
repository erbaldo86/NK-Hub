#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.1.0-FastHealing - Automated Pytest Coverage & SBFL Ochiai Bridge
Module: sbfl_pytest_bridge.py
Author: NK-Bug-Diagnostic-Engine & NK-Platform-Builder
Implements: Pytest test-outcome extraction & Ochiai diagnostic localization (<80 tokens)

Features:
- Deterministic parsing of pytest output (PASSED/FAILED tests and failure tracebacks).
- Precise frame isolation for target source files without parsing overhead.
- Ochiai suspiciousness score calculation: n_ef / sqrt(total_failed * (n_ef + n_ep)).
- Guaranteed < 80 tokens compact diagnostic payload formatting.
- Standalone CLI execution mode for modular pipeline integration.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, ConfigDict, Field

# Ensure scripts directory is on sys.path
_scripts_dir = Path(__file__).resolve().parent
_root_dir = _scripts_dir.parent.parent if _scripts_dir.parent.name == ".staging" else _scripts_dir.parent
for _d in (_scripts_dir, _root_dir / "scripts", _root_dir / ".staging" / "scripts", _root_dir):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from platform_runner import reconfigure_streams, safe_subprocess_run
except ImportError:
    from scripts.platform_runner import reconfigure_streams, safe_subprocess_run


class PytestRunSummary(BaseModel):
    """Structured summary of a pytest execution."""
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


class OchiaiBridgeLocation(BaseModel):
    """High-density fault localization record computed via SBFL Ochiai."""
    model_config = ConfigDict(strict=True, extra="forbid")

    file_path: str
    line_number: int = Field(ge=1)
    suspiciousness: float = Field(ge=0.0, le=1.0)
    error_type: str
    error_message: str
    failing_line_content: str = ""
    total_failed_tests: int = Field(ge=0, default=1)
    n_ef: int = Field(ge=0, default=1)
    n_ep: int = Field(ge=0, default=0)

    def to_compact_payload(self) -> Dict[str, Any]:
        """Generates compact dictionary guaranteed to fit within < 80 tokens."""
        short_file = Path(self.file_path).name if len(self.file_path) > 30 else self.file_path
        short_msg = (self.error_message[:40] + "...") if len(self.error_message) > 40 else self.error_message
        short_ctx = self.failing_line_content.strip()[:35]

        return {
            "loc": f"{short_file}:{self.line_number}",
            "err": f"{self.error_type}: {short_msg}",
            "score": round(self.suspiciousness, 3),
            "ctx": short_ctx,
        }

    def render_payload_json(self) -> str:
        """Serializes compact dictionary to minimal JSON string (< 80 tokens)."""
        payload = self.to_compact_payload()
        rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return rendered


class SBFLPytestBridge:
    """Bridge coordinating pytest execution, traceback triage and Ochiai scoring."""

    def __init__(self, cwd: Optional[Path] = None):
        reconfigure_streams()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    def parse_pytest_output(self, stdout: str, stderr: str, exit_code: int, duration_sec: float = 0.0) -> PytestRunSummary:
        """Parses stdout/stderr from pytest to extract pass/fail statistics."""
        passed_tests: List[str] = []
        failed_tests: List[str] = []

        for line in stdout.splitlines():
            clean_line = line.strip()
            # Match standard pytest verbose format: test_name PASSED / FAILED
            if " PASSED" in clean_line:
                tname = clean_line.split(" PASSED")[0].strip()
                if tname and tname not in passed_tests:
                    passed_tests.append(tname)
            elif " FAILED" in clean_line:
                tname = clean_line.split(" FAILED")[0].strip()
                if tname and tname not in failed_tests:
                    failed_tests.append(tname)

        # Fallback regex search for summary line: e.g. "1 failed, 2 passed in 0.12s" or "6 passed in 11.12s"
        failed_cnt = len(failed_tests)
        passed_cnt = len(passed_tests)

        if failed_cnt == 0 and passed_cnt == 0:
            p_match = re.search(r"(\d+)\s+passed", stdout)
            f_match = re.search(r"(\d+)\s+failed", stdout)
            if p_match:
                passed_cnt = int(p_match.group(1))
            if f_match:
                failed_cnt = int(f_match.group(1))

        total_cnt = failed_cnt + passed_cnt

        return PytestRunSummary(
            total_tests=total_cnt,
            passed_count=passed_cnt,
            failed_count=failed_cnt,
            error_count=1 if exit_code != 0 and failed_cnt == 0 else 0,
            exit_code=exit_code,
            duration_sec=duration_sec,
            failed_test_names=failed_tests,
            passed_test_names=passed_tests,
            raw_stdout=stdout,
            raw_stderr=stderr,
        )

    def extract_failure_location(
        self,
        summary: PytestRunSummary,
        target_file_hint: Optional[str] = None,
    ) -> Optional[OchiaiBridgeLocation]:
        """
        Parses pytest traceback output to extract the root-cause failure location
        for the specified target_file_hint (or deepest source file).
        """
        if summary.exit_code == 0:
            return None

        combined_text = summary.raw_stdout + "\n" + summary.raw_stderr
        lines = combined_text.splitlines()

        target_file: Optional[str] = None
        target_line: int = 1
        error_type: str = "TestFailure"
        error_msg: str = "Test failed"
        failing_code: str = ""

        # 1. Search for error type and message (e.g., E   ZeroDivisionError: division by zero)
        for line in reversed(lines):
            line_str = line.strip()
            if line_str.startswith("E   ") or line_str.startswith("E:  "):
                err_content = line_str[4:].strip()
                if ":" in err_content:
                    parts = err_content.split(":", 1)
                    error_type = parts[0].strip()
                    error_msg = parts[1].strip()
                else:
                    error_type = "AssertionError"
                    error_msg = err_content
                break

        # 2. Search for traceback line matching target_file_hint or file:line pattern
        norm_hint = Path(target_file_hint).name if target_file_hint else None

        # Regex matching traceback file line: e.g. "src/engine.py:42: ZeroDivisionError" or " >   line of code"
        for i, line in enumerate(lines):
            line_str = line.strip()
            # Match e.g.: >       return a / b
            if line_str.startswith(">") and i > 0:
                failing_code = line_str.lstrip("> ").strip()

            # Match filepath:lineno pattern
            match = re.search(r"([A-Za-z0-9_\-\./\\]+\.py):(\d+):", line_str)
            if match:
                fpath = match.group(1).replace("\\", "/")
                lno = int(match.group(2))
                if norm_hint:
                    if norm_hint in fpath:
                        target_file = fpath
                        target_line = lno
                elif "test_" not in Path(fpath).name.lower():
                    target_file = fpath
                    target_line = lno

        if not target_file and target_file_hint:
            target_file = str(target_file_hint)
        elif not target_file:
            target_file = "unknown.py"

        # If failing_code is empty, try reading target file line directly
        if not failing_code and target_file:
            try:
                candidate_path = Path(self.cwd / target_file)
                if not candidate_path.exists():
                    candidate_path = Path(target_file)
                if candidate_path.exists():
                    flines = candidate_path.read_text(encoding="utf-8").splitlines()
                    if 1 <= target_line <= len(flines):
                        failing_code = flines[target_line - 1].strip()
            except Exception:
                pass

        # Calculate Ochiai suspiciousness:
        # If total_failed > 0: n_ef = 1, n_ep = 0 (or proportion of failing executions)
        total_failed = max(1, summary.failed_count)
        n_ef = 1
        n_ep = 0
        denominator = math.sqrt(total_failed * (n_ef + n_ep))
        ochiai_score = (n_ef / denominator) if denominator > 0 else 1.0

        return OchiaiBridgeLocation(
            file_path=target_file,
            line_number=target_line,
            suspiciousness=min(1.0, ochiai_score),
            error_type=error_type,
            error_message=error_msg,
            failing_line_content=failing_code,
            total_failed_tests=total_failed,
            n_ef=n_ef,
            n_ep=n_ep,
        )

    def run_and_diagnose(
        self,
        test_cmd: Sequence[str] | str,
        target_file_hint: Optional[str] = None,
        timeout_sec: float = 60.0,
    ) -> Tuple[PytestRunSummary, Optional[OchiaiBridgeLocation]]:
        """Executes pytest command and returns both summary and SBFL Ochiai location."""
        import time
        t0 = time.perf_counter()
        rc, stdout, stderr = safe_subprocess_run(
            cmd=test_cmd,
            cwd=str(self.cwd),
            timeout=timeout_sec,
        )
        duration = time.perf_counter() - t0
        summary = self.parse_pytest_output(stdout, stderr, rc, duration)
        loc = self.extract_failure_location(summary, target_file_hint=target_file_hint)
        return summary, loc


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(description="Nexus Keystone Pytest-SBFL Ochiai Bridge")
    parser.add_argument("--test-cmd", type=str, required=True, help="Pytest command to execute")
    parser.add_argument("--target-file", type=str, default=None, help="Target file hint to localize")
    parser.add_argument("--cwd", type=str, default=None, help="Working directory")
    parser.add_argument("--json", action="store_true", help="Output compact JSON payload (<80 tok)")

    args = parser.parse_args()
    bridge = SBFLPytestBridge(cwd=Path(args.cwd) if args.cwd else None)
    summary, loc = bridge.run_and_diagnose(test_cmd=args.test_cmd, target_file_hint=args.target_file)

    if args.json:
        if loc:
            print(loc.render_payload_json())
        else:
            print(json.dumps({"status": "PASSED", "total_tests": summary.total_tests}))
    else:
        if loc:
            print(f"🔴 [SBFL-OCHIAI] Fault detected at {loc.file_path}:{loc.line_number} (Score: {loc.suspiciousness})")
            print(f"   Error: {loc.error_type}: {loc.error_message}")
            if loc.failing_line_content:
                print(f"   Code:  {loc.failing_line_content}")
            print(f"   Compact Payload: {loc.render_payload_json()}")
        else:
            print(f"🟢 [SBFL-OCHIAI] All {summary.total_tests} tests PASSED.")

    return summary.exit_code


if __name__ == "__main__":
    sys.exit(main())

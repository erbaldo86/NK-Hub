#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.1.0-FastHealing - Universal CLI Auto-Healer Pipeline
Module: auto_heal_pipeline.py
Author: NK-Bug-Diagnostic-Engine & NK-Platform-Builder
Implements: Orchestrated Fast-Loop Healing CLI with SBFL Ochiai & Transactional Rollback

Features:
- Single-command CLI bridge for real pytest test suites on staged source files.
- Zero-overhead exit if tests pass on initial evaluation.
- Micro-diagnostic SBFL Ochiai payload generation (<80 tokens).
- Transactional staging rollback preventing regressive patches from corrupting source files.
- Single-line PATCH_NOTES.md emission conforming to [RULE-PROJECT-ISOLATION].
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, ConfigDict, Field

_scripts_dir = Path(__file__).resolve().parent
_root_dir = _scripts_dir.parent.parent if _scripts_dir.parent.name == ".staging" else _scripts_dir.parent
for _d in (_scripts_dir, _root_dir / "scripts", _root_dir / ".staging" / "scripts", _root_dir):
    if _d.exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from platform_runner import reconfigure_streams, safe_subprocess_run
    from sbfl_pytest_bridge import SBFLPytestBridge, PytestRunSummary, OchiaiBridgeLocation
    from healing_snapshot_rollback import HealingSnapshotManager, FitnessVerdict, FitnessReport
except ImportError:
    from scripts.platform_runner import reconfigure_streams, safe_subprocess_run
    from scripts.sbfl_pytest_bridge import SBFLPytestBridge, PytestRunSummary, OchiaiBridgeLocation
    from scripts.healing_snapshot_rollback import HealingSnapshotManager, FitnessVerdict, FitnessReport


class AutoHealSessionReport(BaseModel):
    """Complete structured report of an auto-heal pipeline execution."""
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
    message: str


class AutoHealPipeline:
    """End-to-end autonomous healing orchestrator."""

    def __init__(self, cwd: Optional[Path] = None, max_cycles: int = 3):
        reconfigure_streams()
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()
        self.max_cycles = max_cycles
        self.bridge = SBFLPytestBridge(cwd=self.cwd)
        self.snapshot_mgr = HealingSnapshotManager()

    def run_pipeline(
        self,
        test_cmd: Sequence[str] | str,
        target_file: Path | str,
        repair_callback: Optional[Callable[[OchiaiBridgeLocation, int], bool]] = None,
    ) -> AutoHealSessionReport:
        """
        Executes the autonomous healing cycle on target_file driven by test_cmd:
        1. Takes initial baseline snapshot.
        2. Evaluates test_cmd. If PASS -> returns immediately.
        3. If FAIL -> runs SBFL diagnostic localization.
        4. Iterates up to max_cycles with transactional fitness gate and rollback on regression.
        5. Emits structured report & PATCH_NOTES single-line record.
        """
        target_path = Path(self.cwd / target_file) if not Path(target_file).is_absolute() else Path(target_file)
        init_snap_id = self.snapshot_mgr.create_snapshot([target_path])

        # Initial baseline evaluation
        summary, loc = self.bridge.run_and_diagnose(test_cmd=test_cmd, target_file_hint=str(target_file))

        if summary.exit_code == 0 and summary.failed_count == 0:
            self.snapshot_mgr.cleanup(init_snap_id)
            return AutoHealSessionReport(
                success=True,
                cycles_used=0,
                max_cycles=self.max_cycles,
                initial_failed=0,
                final_failed=0,
                message="Clean build: All tests passing on initial evaluation.",
            )

        initial_failed = summary.failed_count
        prev_failed = summary.failed_count
        prev_passed = summary.passed_count
        latest_loc = loc

        for cycle in range(1, self.max_cycles + 1):
            # Take cycle snapshot before applying repair
            cycle_snap_id = self.snapshot_mgr.create_snapshot([target_path])

            repair_applied = False
            if repair_callback and latest_loc:
                try:
                    repair_applied = repair_callback(latest_loc, cycle)
                except Exception as exc:
                    repair_applied = False

            # If no programmatic callback, we check if external modifications were made
            # Re-evaluate test_cmd
            new_summary, new_loc = self.bridge.run_and_diagnose(test_cmd=test_cmd, target_file_hint=str(target_file))

            fitness = self.snapshot_mgr.evaluate_fitness(
                current_passed=new_summary.passed_count,
                current_failed=new_summary.failed_count,
                prev_passed=prev_passed,
                prev_failed=prev_failed,
                exit_code=new_summary.exit_code,
            )

            if fitness.verdict == FitnessVerdict.PASSED:
                # All tests passed!
                self.snapshot_mgr.cleanup()
                patch_note = ""
                if latest_loc:
                    patch_note = (
                        f"- **[AUTO-HEALED]** `{latest_loc.error_type}` in "
                        f"`{Path(latest_loc.file_path).name}:{latest_loc.line_number}` "
                        f"(Cycles: {cycle}, Ochiai: {round(latest_loc.suspiciousness, 3)})"
                    )
                return AutoHealSessionReport(
                    success=True,
                    cycles_used=cycle,
                    max_cycles=self.max_cycles,
                    initial_failed=initial_failed,
                    final_failed=0,
                    fault_location=f"{latest_loc.file_path}:{latest_loc.line_number}" if latest_loc else None,
                    error_type=latest_loc.error_type if latest_loc else None,
                    ochiai_score=latest_loc.suspiciousness if latest_loc else None,
                    patch_note_line=patch_note,
                    rolled_back=False,
                    message=f"Healed successfully on cycle {cycle} via strict fitness gate.",
                )

            elif fitness.verdict == FitnessVerdict.REGRESSION:
                # Rollback to cycle snapshot to prevent code degradation
                self.snapshot_mgr.rollback(cycle_snap_id)
                self.snapshot_mgr.cleanup(cycle_snap_id)
                # Keep prev_failed and prev_passed as baseline
            else:
                # IMPROVED or NEUTRAL: keep change, update baseline
                prev_failed = new_summary.failed_count
                prev_passed = new_summary.passed_count
                latest_loc = new_loc
                self.snapshot_mgr.cleanup(cycle_snap_id)

        # If cycles exhausted without resolution: rollback to initial snapshot 0
        self.snapshot_mgr.rollback(init_snap_id)
        self.snapshot_mgr.cleanup()

        return AutoHealSessionReport(
            success=False,
            cycles_used=self.max_cycles,
            max_cycles=self.max_cycles,
            initial_failed=initial_failed,
            final_failed=prev_failed,
            fault_location=f"{latest_loc.file_path}:{latest_loc.line_number}" if latest_loc else None,
            error_type=latest_loc.error_type if latest_loc else None,
            ochiai_score=latest_loc.suspiciousness if latest_loc else None,
            rolled_back=True,
            message="Exhausted maximum healing cycles. Rollback to original state completed.",
        )


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(description="Nexus Keystone Universal CLI Auto-Healer Pipeline")
    parser.add_argument("--test-cmd", type=str, required=True, help="Pytest command to execute")
    parser.add_argument("--target-file", type=str, required=True, help="Target file to heal")
    parser.add_argument("--cwd", type=str, default=None, help="Working directory")
    parser.add_argument("--max-cycles", type=int, default=3, help="Max healing cycles (default: 3)")
    parser.add_argument("--json", action="store_true", help="Output JSON session report")

    args = parser.parse_args()
    pipeline = AutoHealPipeline(cwd=Path(args.cwd) if args.cwd else None, max_cycles=args.max_cycles)
    report = pipeline.run_pipeline(test_cmd=args.test_cmd, target_file=args.target_file)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        if report.success:
            print(f"🟢 [AUTO-HEAL] {report.message}")
            if report.patch_note_line:
                print(f"📝 [PATCH-NOTE] {report.patch_note_line}")
        else:
            print(f"🔴 [AUTO-HEAL] {report.message}")
            if report.fault_location:
                print(f"   Last detected fault: {report.fault_location} ({report.error_type})")

    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())

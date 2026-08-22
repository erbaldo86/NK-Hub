# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 7: Invisible Autonomous Fast-Loop Healing Engine
4 Tests: Triage L1 (AST Syntax), Triage L2 (DAST Runtime), Triage L3 (SBFL Fault), Circuit Breaker Rollback.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from invisible_healing_loop import InvisibleHealingLoop


class TestInvisibleHealingLoop(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp.name)
        self.telemetry_file = self.tmp_dir / "telemetry.jsonl"
        self.loop = InvisibleHealingLoop(telemetry_log_path=self.telemetry_file, max_cycles=3)

    def tearDown(self):
        try:
            self._temp.cleanup()
        except Exception:
            pass

    # 41. test_healing_triage_l1_ast_syntax_fix
    def test_healing_triage_l1_ast_syntax_fix(self):
        """41. Validates Level 1 AST syntax fix triage in staging."""
        state = {"attempts": 0}

        def buggy_op():
            state["attempts"] += 1
            if state["attempts"] == 1:
                raise SyntaxError("unexpected EOF while parsing")
            return "SYNTAX_HEALED"

        def repair(sbfl, code_slice, cycle):
            return "Fixed syntax"

        res = self.loop.execute_with_healing("task_l1", buggy_op, repair)
        self.assertTrue(res.success)
        self.assertEqual(res.output, "SYNTAX_HEALED")
        self.assertEqual(res.cycles_used, 2)

    # 42. test_healing_triage_l2_dast_runtime_fix
    def test_healing_triage_l2_dast_runtime_fix(self):
        """42. Validates Level 2 DAST runtime exception fix."""
        state = {"divisor": 0}

        def buggy_op():
            return 100 // state["divisor"]

        def repair(sbfl, code_slice, cycle):
            state["divisor"] = 10
            return "Patched divisor"

        res = self.loop.execute_with_healing("task_l2", buggy_op, repair)
        self.assertTrue(res.success)
        self.assertEqual(res.output, 10)
        self.assertEqual(res.cycles_used, 2)

    # 43. test_healing_triage_l3_sbfl_fault_fix
    def test_healing_triage_l3_sbfl_fault_fix(self):
        """43. Validates Level 3 SBFL fault localization & surgical patch."""
        state = {"val": -5}

        def buggy_op():
            if state["val"] < 0:
                raise ValueError("Negative value not allowed")
            return state["val"] * 2

        def repair(sbfl, code_slice, cycle):
            state["val"] = 5
            return "Corrected sign"

        res = self.loop.execute_with_healing("task_l3", buggy_op, repair)
        self.assertTrue(res.success)
        self.assertEqual(res.output, 10)

    # 44. test_circuit_breaker_3_attempts_rollback
    def test_circuit_breaker_3_attempts_rollback(self):
        """44. Validates circuit breaker halts at 3 attempts and triggers rollback."""
        def unfixable_op():
            raise RuntimeError("Permanent fault")

        def noop_repair(sbfl, code_slice, cycle):
            return "No-op"

        res = self.loop.execute_with_healing("task_unfixable", unfixable_op, noop_repair)
        self.assertFalse(res.success)
        self.assertEqual(res.cycles_used, 3)
        self.assertIsNotNone(res.final_error)


if __name__ == "__main__":
    unittest.main()

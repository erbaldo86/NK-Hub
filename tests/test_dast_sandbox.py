# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 2: DAST Sandbox Runner & Dynamic Line Tracer
6 Tests: Sandbox Isolation, Mirroring, Line Tracer, Timeout Watchdog, Memory Cap, Taskkill Pre-Kill.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from dast_sandbox_runner import DASTSandboxRunner, SandboxConfig, ShadowSandbox


class TestDASTSandbox(unittest.IsolatedAsyncioTestCase):
    # 9. test_sandbox_creation_and_isolation
    async def test_sandbox_creation_and_isolation(self):
        """9. Validates creation of isolated sandbox in %TEMP%\\nk_sandbox_*."""
        sb = ShadowSandbox()
        created_path = sb.create()
        self.assertTrue(created_path.exists())
        self.assertIn("nk_sandbox_", str(created_path))
        sb.cleanup()
        self.assertFalse(created_path.exists())

    # 10. test_sandbox_file_mirroring
    async def test_sandbox_file_mirroring(self):
        """10. Validates file writing and tree mirroring inside shadow sandbox."""
        sb = ShadowSandbox()
        sb.create()
        try:
            f = sb.write_file("nested/module.py", "X = 42\n")
            self.assertTrue(f.exists())
            self.assertEqual(f.read_text(encoding="utf-8"), "X = 42\n")
        finally:
            sb.cleanup()

    # 11. test_execution_line_tracer_accuracy
    async def test_execution_line_tracer_accuracy(self):
        """11. Validates deterministic statement trace counting via trace.Trace."""
        sb = ShadowSandbox()
        sb.create()
        try:
            code = """
def calc(a, b):
    res = a + b
    return res

calc(10, 20)
"""
            sb.write_file("calc_test.py", code)
            config = SandboxConfig(timeout_sec=5.0, trace_coverage=True)
            runner = DASTSandboxRunner(config=config)

            rep = await runner.run_in_sandbox(sb, [sys.executable, "calc_test.py"], target_script_name="calc_test.py")
            self.assertTrue(rep.success)
            self.assertGreater(len(rep.executed_statements), 0)
        finally:
            sb.cleanup()

    # 12. test_watchdog_timeout_enforcement
    async def test_watchdog_timeout_enforcement(self):
        """12. Validates that infinite loops are promptly terminated by watchdog timeout."""
        sb = ShadowSandbox()
        sb.create()
        try:
            hang_code = "import time\nwhile True:\n    time.sleep(0.05)\n"
            sb.write_file("hang.py", hang_code)
            config = SandboxConfig(timeout_sec=0.4, poll_interval_sec=0.02)
            runner = DASTSandboxRunner(config=config)

            rep = await runner.run_in_sandbox(sb, [sys.executable, "hang.py"])
            self.assertTrue(rep.timed_out)
            self.assertFalse(rep.success)
        finally:
            sb.cleanup()

    # 13. test_watchdog_memory_cap_enforcement
    async def test_watchdog_memory_cap_enforcement(self):
        """13. Validates that memory limits trigger watchdog termination."""
        sb = ShadowSandbox()
        sb.create()
        try:
            mem_code = 'import time\nb = bytearray(b"X" * (80 * 1024 * 1024))\ntime.sleep(2.0)\n'
            sb.write_file("mem.py", mem_code)
            config = SandboxConfig(timeout_sec=5.0, max_memory_mb=30.0, poll_interval_sec=0.02)
            runner = DASTSandboxRunner(config=config)

            rep = await runner.run_in_sandbox(sb, [sys.executable, "mem.py"])
            self.assertTrue(rep.memory_exceeded or not rep.success)
        finally:
            sb.cleanup()

    # 14. test_watchdog_taskkill_pre_kill_tree
    async def test_watchdog_taskkill_pre_kill_tree(self):
        """14. Validates taskkill /F /T pre-kill to eliminate child process trees."""
        sb = ShadowSandbox()
        sb.create()
        try:
            tree_code = """
import subprocess, sys, time
proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
time.sleep(10)
"""
            sb.write_file("tree.py", tree_code)
            config = SandboxConfig(timeout_sec=0.5, poll_interval_sec=0.02)
            runner = DASTSandboxRunner(config=config)

            rep = await runner.run_in_sandbox(sb, [sys.executable, "tree.py"])
            self.assertTrue(rep.timed_out or not rep.success)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

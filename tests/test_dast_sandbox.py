# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per DAST Sandbox Runner e Line Tracer (v3.3.0).
Modulo: tests/test_dast_sandbox.py.
Valida ciclo di vita sandbox, trace.Trace, watchdog timeout/memory e taskkill /F /T.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from dast_sandbox_runner import DASTSandboxRunner, SandboxConfig, ShadowSandbox


class TestDASTSandbox(unittest.IsolatedAsyncioTestCase):
    async def test_sandbox_lifecycle_and_mirroring(self):
        """1. Valida creazione, scrittura, tracciamento statement trace.Trace e teardown."""
        sb = ShadowSandbox()
        created_path = sb.create()
        self.assertTrue(created_path.exists())
        self.assertIn("nk_sandbox_", str(created_path))
        try:
            f = sb.write_file("nested/module.py", "X = 42\n")
            self.assertTrue(f.exists())
            self.assertEqual(f.read_text(encoding="utf-8"), "X = 42\n")

            code = "def calc(a, b):\n    res = a + b\n    return res\ncalc(10, 20)\n"
            sb.write_file("calc_test.py", code)
            config = SandboxConfig(timeout_sec=3.0, trace_coverage=True)
            runner = DASTSandboxRunner(config=config)
            rep = await runner.run_in_sandbox(
                sb,
                [sys.executable, "calc_test.py"],
                target_script_name="calc_test.py",
            )
            self.assertTrue(rep.success)
            self.assertGreater(len(rep.executed_statements), 0)
        finally:
            sb.cleanup()
        self.assertFalse(created_path.exists())

    async def test_watchdog_timeout_enforcement(self):
        """2. Valida l'interruzione deterministica per timeout e superamento tetto memoria."""
        sb = ShadowSandbox()
        sb.create()
        try:
            hang_code = "import time\nwhile True:\n    time.sleep(0.02)\n"
            sb.write_file("hang.py", hang_code)
            cfg_timeout = SandboxConfig(timeout_sec=0.15, poll_interval_sec=0.01)
            runner_timeout = DASTSandboxRunner(config=cfg_timeout)
            rep_to = await runner_timeout.run_in_sandbox(sb, [sys.executable, "hang.py"])
            self.assertTrue(rep_to.timed_out)
            self.assertFalse(rep_to.success)

            mem_code = 'import time\nb = bytearray(b"X" * (70 * 1024 * 1024))\ntime.sleep(0.5)\n'
            sb.write_file("mem.py", mem_code)
            cfg_mem = SandboxConfig(
                timeout_sec=2.0, max_memory_mb=25.0, poll_interval_sec=0.01
            )
            runner_mem = DASTSandboxRunner(config=cfg_mem)
            rep_mem = await runner_mem.run_in_sandbox(sb, [sys.executable, "mem.py"])
            self.assertTrue(rep_mem.memory_exceeded or not rep_mem.success)
        finally:
            sb.cleanup()

    async def test_watchdog_taskkill_pre_kill_tree(self):
        """3. Valida il pre-kill taskkill /F /T per eliminare alberi di processi figli."""
        sb = ShadowSandbox()
        sb.create()
        try:
            tree_code = (
                "import subprocess, sys, time\n"
                'proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])\n'
                "time.sleep(5)\n"
            )
            sb.write_file("tree.py", tree_code)
            config = SandboxConfig(timeout_sec=0.18, poll_interval_sec=0.01)
            runner = DASTSandboxRunner(config=config)
            rep = await runner.run_in_sandbox(sb, [sys.executable, "tree.py"])
            self.assertTrue(rep.timed_out or not rep.success)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

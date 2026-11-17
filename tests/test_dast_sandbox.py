# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per DAST Sandbox Runner e Line Tracer (v6.4.0-Carbon).
Modulo: tests/test_dast_sandbox.py.
Valida ciclo di vita sandbox, confinamento CRIT-05, trace.Trace, watchdog, RSS e cleanup.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

dast_mod = load_nk_script_module("dast_sandbox_runner")
DASTSandboxRunner = dast_mod.DASTSandboxRunner
SandboxConfig = dast_mod.SandboxConfig
ShadowSandbox = dast_mod.ShadowSandbox
_build_sanitized_sandbox_env = dast_mod._build_sanitized_sandbox_env
_get_process_memory_rss = dast_mod._get_process_memory_rss
_resolve_confined_sandbox_path = dast_mod._resolve_confined_sandbox_path
resolve_dast_report_path = dast_mod.resolve_dast_report_path
run_staging_shadow_verification = dast_mod.run_staging_shadow_verification
write_atomic_dast_report = dast_mod.write_atomic_dast_report


@pytest.mark.integration
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
            cfg_timeout = SandboxConfig(timeout_sec=0.09, poll_interval_sec=0.01)
            runner_timeout = DASTSandboxRunner(config=cfg_timeout)
            rep_to = await runner_timeout.run_in_sandbox(sb, [sys.executable, "hang.py"])
            self.assertTrue(rep_to.timed_out)
            self.assertFalse(rep_to.success)

            mem_code = 'import time\nb = bytearray(b"X" * (70 * 1024 * 1024))\ntime.sleep(0.03)\n'
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
            config = SandboxConfig(timeout_sec=0.10, poll_interval_sec=0.01)
            runner = DASTSandboxRunner(config=config)
            rep = await runner.run_in_sandbox(sb, [sys.executable, "tree.py"])
            self.assertTrue(rep.timed_out or not rep.success)
        finally:
            sb.cleanup()

    def test_sandbox_path_traversal_confinement_crit05(self):
        """4. Valida CRIT-05: rifiuto di path relativi '..', path assoluti e ADS fuori dalla sandbox."""
        sb = ShadowSandbox()
        sb.create()
        try:
            ok_dest = sb.write_file("sub/safe_mod.py", "SAFE = 1\n")
            self.assertTrue(ok_dest.exists())
            for escaped in ("../escape.py", "sub/../../escape.py", "C:/Windows/Temp/evil.py", "/abs/evil.py"):
                with self.assertRaises(ValueError):
                    sb.write_file(escaped, "EVIL = 1\n")
                with self.assertRaises(ValueError):
                    _resolve_confined_sandbox_path(sb.sandbox_dir, escaped)
        finally:
            sb.cleanup()


@pytest.mark.fast
def test_dast_sandbox_env_sanitization_copy_and_report_paths(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """5. Verifica sanificazione env, copy_file, report atomici e confinamento stringhe vuote."""
    assert isolated_nk_env.is_dir()
    env = _build_sanitized_sandbox_env(
        {
            "API_TOKEN": "keep_extra_token",
            "NK_ALLOW_GOVERNANCE_OVERRIDE": "1",
            "CUSTOM_VAR": "ok",
        }
    )
    assert "NK_ALLOW_GOVERNANCE_OVERRIDE" not in env
    assert env["CUSTOM_VAR"] == "ok"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"

    src_f = tmp_path / "src_mod.py"
    src_f.write_text("V = 1\n", encoding="utf-8")
    with ShadowSandbox() as sb:
        assert sb.sandbox_dir.exists()
        assert sb.copy_file(src_f, "").is_file()
        assert sb.copy_file(src_f, "sub_dir/").name == "src_mod.py"
        assert sb.copy_file(src_f, "sub_dir").is_file()
        assert sb.copy_file(src_f, "custom/renamed.py").name == "renamed.py"
        with pytest.raises(FileNotFoundError):
            sb.copy_file(tmp_path / "missing.py")
        for bad in ("", "   ", "a\x00b"):
            with pytest.raises(ValueError):
                _resolve_confined_sandbox_path(sb.sandbox_dir, bad)
    assert not sb.sandbox_dir.exists()

    dir_out = resolve_dast_report_path(tmp_path, str(tmp_path) + "/")
    assert dir_out.parent == tmp_path and dir_out.name.startswith("dast_report_")
    explicit_file = tmp_path / "explicit.json"
    written = write_atomic_dast_report({"ok": True}, tmp_path, explicit_output=explicit_file)
    assert written == explicit_file and explicit_file.is_file()


@pytest.mark.integration
def test_dast_rss_cache_timeout_and_overlay_verification(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """6. Verifica RSS cache, timeout job isolato, kill idempotente e overlay staging."""
    assert isolated_nk_env.is_dir()
    rss_state = dast_mod._RSSMonitorState()
    rss1 = _get_process_memory_rss(os.getpid(), rss_state=rss_state)
    rss2 = _get_process_memory_rss(os.getpid(), rss_state=rss_state)
    assert rss1 >= 0 and rss2 == rss1
    assert rss_state.record_sample(1234) == max(rss_state.get_peak(), 1234)
    assert DASTSandboxRunner().kill_process_tree(proc=None, parent=None) is True

    miss = run_staging_shadow_verification(tmp_path / "nonexistent_root")
    assert miss["passed"] is False and miss["status"] == "FAIL"

    mini_repo = tmp_path / "mini_repo"
    (mini_repo / "scripts").mkdir(parents=True)
    (mini_repo / ".staging" / "scripts").mkdir(parents=True)
    (mini_repo / "scripts" / "old.py").write_text("OLD = 1\n", encoding="utf-8")
    (mini_repo / ".staging" / "scripts" / "new.py").write_text("NEW = 2\n", encoding="utf-8")
    (mini_repo / ".staging" / ".deleted_files.json").write_text(
        '{"deleted_files": ["scripts/old.py"]}', encoding="utf-8"
    )
    ver_res = run_staging_shadow_verification(
        repo_root=mini_repo,
        run_pytest=False,
        run_ast_guard=True,
        profile="builder",
    )
    assert ver_res["passed"] is True
    assert "scripts/new.py" in ver_res["overlay_files"]
    assert "scripts/old.py" in ver_res["deleted_files"]
    assert not Path(ver_res["sandbox_dir"]).exists()

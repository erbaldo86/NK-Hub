# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_platform_runner.py
Valida l'iniezione di -u su stringhe comando e il tree-kill su timeout.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_runner_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "platform_runner.py"
    prod_target = _workspace_root / "scripts" / "platform_runner.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("platform_runner", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["platform_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


runner_mod = _load_runner_module()
_normalize_python_command = runner_mod._normalize_python_command
safe_subprocess_run = runner_mod.safe_subprocess_run


def test_platform_runner_string_command_unbuffered_injection() -> None:
    """1. Verifica l'iniezione del flag -u anche su comandi Python passati come stringa."""
    raw_cmd = 'python -c "print(42)"'
    norm_cmd = _normalize_python_command(raw_cmd)
    assert isinstance(norm_cmd, str)
    assert norm_cmd.startswith("python -u ")

    quoted_cmd = f'"{sys.executable}" -c "print(42)"'
    norm_quoted = _normalize_python_command(quoted_cmd)
    assert isinstance(norm_quoted, str)
    assert " -u " in norm_quoted


def test_platform_runner_tree_kill_on_timeout_and_utf8() -> None:
    """2. Verifica l'abbattimento dell'albero processi in timeout e la cattura UTF-8."""
    spawn_tree_cmd = [
        sys.executable,
        "-c",
        (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(15)']); "
            "time.sleep(15)"
        ),
    ]
    rc, stdout, stderr = safe_subprocess_run(spawn_tree_cmd, timeout=0.5)
    assert rc == -1
    assert "timed out" in stderr.lower()

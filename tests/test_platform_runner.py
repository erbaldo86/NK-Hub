# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per platform_runner.py di Nexus Keystone v3.3.0.
Modulo: tests/test_platform_runner.py.
Valida l'iniezione di -u, la configurazione pytest.ini, UTF-8 e il tree-kill rapido.
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
    """Carica il modulo platform_runner dando priorita a .staging/scripts."""
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
reconfigure_streams = runner_mod.reconfigure_streams


def test_platform_runner_string_command_unbuffered_injection() -> None:
    """1. Verifica l'iniezione del flag -u su liste e stringhe e valida pytest.ini."""
    reconfigure_streams()
    raw_cmd = 'python -c "print(42)"'
    norm_cmd = _normalize_python_command(raw_cmd)
    assert isinstance(norm_cmd, str)
    assert norm_cmd.startswith("python -u ")

    quoted_cmd = f'"{sys.executable}" -c "print(42)"'
    norm_quoted = _normalize_python_command(quoted_cmd)
    assert isinstance(norm_quoted, str)
    assert " -u " in norm_quoted

    list_cmd = [sys.executable, "-c", "print(1)"]
    norm_list = _normalize_python_command(list_cmd)
    assert norm_list[1] == "-u"

    pytest_ini = _workspace_root / "pytest.ini"
    assert pytest_ini.exists()
    ini_text = pytest_ini.read_text(encoding="utf-8")
    assert "[pytest]" in ini_text
    assert "testpaths" in ini_text
    assert ".staging" in ini_text


def test_platform_runner_tree_kill_on_timeout_and_utf8() -> None:
    """2. Verifica la cattura UTF-8, i comandi non validi e l'abbattimento su timeout."""
    rc_ok, out_ok, err_ok = safe_subprocess_run(
        [sys.executable, "-c", "import sys; sys.stdout.write('NK_UTF8_🚀_€\\n')"]
    )
    assert rc_ok == 0
    assert "🚀" in out_ok and "€" in out_ok
    assert err_ok == ""

    rc_inv, out_inv, _ = safe_subprocess_run(["non_existent_binary_nk_987654321"])
    assert rc_inv != 0
    assert out_inv == ""

    spawn_tree_cmd = [
        sys.executable,
        "-c",
        "import time; time.sleep(5)",
    ]
    rc, _, stderr = safe_subprocess_run(spawn_tree_cmd, timeout=0.15)
    assert rc == -1
    assert "timed out" in stderr.lower()

# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per safe_cleanup_dev_servers.py e async_heartbeat_signaler.py (v3.3.0).
Modulo: tests/test_safe_cleanup_dev_servers.py.
Valida il filtro workspace su CWD/cmdline, la protezione del PID attivo e i flag CLI JSON.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_script_module(mod_name: str):
    """Carica dinamicamente uno script da .staging/scripts o scripts/."""
    staging_target = _workspace_root / ".staging" / "scripts" / f"{mod_name}.py"
    prod_target = _workspace_root / "scripts" / f"{mod_name}.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


cleanup_mod = _load_script_module("safe_cleanup_dev_servers")
heartbeat_mod = _load_script_module("async_heartbeat_signaler")
is_target_workspace_process = cleanup_mod.is_target_workspace_process


def test_safe_cleanup_workspace_filter_cwd_and_cmdline(tmp_path: Path) -> None:
    """1. Verifica il filtro CWD/cmdline del workspace e la protezione del PID corrente/genitore."""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    assert is_target_workspace_process(current_pid, workspace_root=tmp_path) is False
    assert is_target_workspace_process(parent_pid, workspace_root=tmp_path) is False

    ws_dir = tmp_path / "TargetWorkspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    other_dir = tmp_path / "ExternalWorkspace"
    other_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=str(ws_dir),
    )
    try:
        assert is_target_workspace_process(proc.pid, workspace_root=ws_dir) is True
        assert is_target_workspace_process(proc.pid, workspace_root=other_dir) is False
    finally:
        proc.terminate()
        proc.wait(timeout=2.0)


def test_async_heartbeat_signaler_cli_once_and_cleanup_cli_json(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """2. Verifica l'esecuzione CLI deterministica di async_heartbeat_signaler e safe_cleanup_dev_servers."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["async_heartbeat_signaler.py", "--once", "--task-id", "test_hb", "--json"],
    )
    assert heartbeat_mod.main() == 0
    out_hb = capsys.readouterr().out
    assert '"pulse_index": 1' in out_hb

    monkeypatch.setattr(
        cleanup_mod,
        "get_pids_listening_on_ports",
        lambda ports, workspace_root=None: set(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "safe_cleanup_dev_servers.py",
            "--workspace-root",
            str(tmp_path),
            "--dry-run",
            "--json",
        ],
    )
    assert cleanup_mod.main() == 0
    out_cl = capsys.readouterr().out
    assert '"status": "OK"' in out_cl

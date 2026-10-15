# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_safe_cleanup_dev_servers.py
Valida il filtro workspace su CWD e cmdline e la protezione del PID corrente.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_cleanup_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "safe_cleanup_dev_servers.py"
    prod_target = _workspace_root / "scripts" / "safe_cleanup_dev_servers.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("safe_cleanup_dev_servers", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["safe_cleanup_dev_servers"] = mod
    spec.loader.exec_module(mod)
    return mod


cleanup_mod = _load_cleanup_module()
is_target_workspace_process = cleanup_mod.is_target_workspace_process


def test_safe_cleanup_workspace_filter_cwd_and_cmdline(tmp_path: Path) -> None:
    """1. Verifica che il filtro accetti solo processi reali appartenenti al workspace target."""
    ws_dir = tmp_path / "TargetWorkspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    other_dir = tmp_path / "ExternalWorkspace"
    other_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=str(ws_dir),
    )
    try:
        assert is_target_workspace_process(proc.pid, workspace_root=ws_dir) is True
        assert is_target_workspace_process(proc.pid, workspace_root=other_dir) is False
    finally:
        proc.terminate()
        proc.wait(timeout=3.0)


def test_safe_cleanup_protects_current_pid(tmp_path: Path) -> None:
    """2. Verifica che il processo corrente e il genitore non vengano mai selezionati."""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    assert is_target_workspace_process(current_pid, workspace_root=tmp_path) is False
    assert is_target_workspace_process(parent_pid, workspace_root=tmp_path) is False


def test_async_heartbeat_signaler_cli_once_and_cleanup_cli_json(tmp_path: Path) -> None:
    """3. Verifica l'esecuzione CLI deterministica di async_heartbeat_signaler e safe_cleanup_dev_servers."""
    hb_staging = _workspace_root / ".staging" / "scripts" / "async_heartbeat_signaler.py"
    hb_prod = _workspace_root / "scripts" / "async_heartbeat_signaler.py"
    hb_script = hb_staging if hb_staging.exists() else hb_prod

    res_hb = subprocess.run(
        [sys.executable, str(hb_script), "--once", "--task-id", "test_hb", "--json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res_hb.returncode == 0
    assert '"pulse_index": 1' in res_hb.stdout

    cl_staging = _workspace_root / ".staging" / "scripts" / "safe_cleanup_dev_servers.py"
    cl_prod = _workspace_root / "scripts" / "safe_cleanup_dev_servers.py"
    cl_script = cl_staging if cl_staging.exists() else cl_prod

    res_cl = subprocess.run(
        [
            sys.executable,
            str(cl_script),
            "--workspace-root",
            str(tmp_path),
            "--dry-run",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res_cl.returncode == 0
    assert '"status": "OK"' in res_cl.stdout


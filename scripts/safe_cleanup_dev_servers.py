#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilita di bonifica dei server di sviluppo per NK Hub Generation 1.0.0-Generation.
Modulo: scripts/safe_cleanup_dev_servers.py.
@domain_id: DOM-03
Termina solo i processi server del workspace target o NK_External_Projects e protegge il PID attivo.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__nk_domain__: str = "DOM-03"
__nk_role__: str = "facade"
__nk_facade__: str = "safe_cleanup_dev_servers"

_CLI_FLAGS: Tuple[str, ...] = (
    "--dry-run",
    "--json",
    "--lane-id",
    "--ports",
    "--strict-scope",
    "--workspace-root",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (_PROD_SCRIPTS, _SCRIPT_DIR):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="safe_cleanup_dev_servers")

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "TARGET_PORTS": ("_internal.safe_cleanup_dev_servers.win32_proc", "TARGET_PORTS"),
    "PORT_SCAN_RANGE": ("_internal.safe_cleanup_dev_servers.win32_proc", "PORT_SCAN_RANGE"),
    "DEV_PROCESS_KEYWORDS": ("_internal.safe_cleanup_dev_servers.win32_proc", "DEV_PROCESS_KEYWORDS"),
    "_CIM_BATCH_CACHE": ("_internal.safe_cleanup_dev_servers.win32_proc", "_CIM_BATCH_CACHE"),
    "_HAS_PSUTIL": ("_internal.safe_cleanup_dev_servers.win32_proc", "_HAS_PSUTIL"),
    "psutil": ("_internal.safe_cleanup_dev_servers.win32_proc", "psutil"),
    "subprocess": ("_internal.safe_cleanup_dev_servers.win32_proc", "subprocess"),
    "os": ("_internal.safe_cleanup_dev_servers.win32_proc", "os"),
    "time": ("_internal.safe_cleanup_dev_servers.win32_proc", "time"),
    "_scripts_dir": ("_internal.safe_cleanup_dev_servers.win32_proc", "_scripts_dir"),
    "_workspace_root": ("_internal.safe_cleanup_dev_servers.win32_proc", "_workspace_root"),
    "parse_ports_arg": ("_internal.safe_cleanup_dev_servers.win32_proc", "parse_ports_arg"),
    "_is_subpath_str": ("_internal.safe_cleanup_dev_servers.win32_proc", "_is_subpath_str"),
    "_query_win32_cim_processes": ("_internal.safe_cleanup_dev_servers.win32_proc", "_query_win32_cim_processes"),
    "_matches_workspace_paths": ("_internal.safe_cleanup_dev_servers.win32_proc", "_matches_workspace_paths"),
    "is_target_workspace_process": ("_internal.safe_cleanup_dev_servers.win32_proc", "is_target_workspace_process"),
    "_scan_netstat_listening_pids": ("_internal.safe_cleanup_dev_servers.win32_proc", "_scan_netstat_listening_pids"),
    "scan_listening_port_range": ("_internal.safe_cleanup_dev_servers.cleanup_cli", "scan_listening_port_range"),
    "get_pids_listening_on_ports": ("_internal.safe_cleanup_dev_servers.cleanup_cli", "get_pids_listening_on_ports"),
    "kill_pid_tree": ("_internal.safe_cleanup_dev_servers.cleanup_cli", "kill_pid_tree"),
    "run_cleanup": ("_internal.safe_cleanup_dev_servers.cleanup_cli", "run_cleanup"),
    "_build_cli_parser": ("_internal.safe_cleanup_dev_servers.cleanup_cli", "_build_cli_parser"),
    "reconfigure_streams": ("_internal.nk_common.paths", "reconfigure_streams"),
}


def __getattr__(name: str) -> Any:
    """Risolve pigramente i simboli esportati da _internal.safe_cleanup_dev_servers."""
    target = _LAZY_EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    init_nk_facade(__file__, pkg="safe_cleanup_dev_servers")
    val = getattr(importlib.import_module(target[0]), target[1])
    globals()[name] = val
    return val


def __dir__() -> List[str]:
    """Elenca i simboli pubblici ed esportati pigramente dalla facciata."""
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per la bonifica sicura dei server di sviluppo."""
    init_nk_facade(__file__, pkg="safe_cleanup_dev_servers")
    return importlib.import_module(
        "_internal.safe_cleanup_dev_servers.cleanup_cli"
    ).main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

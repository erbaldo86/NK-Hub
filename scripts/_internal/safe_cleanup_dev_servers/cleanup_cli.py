# -*- coding: utf-8 -*-
"""Scansione porte attive, terminazione PID tree e CLI per safe_cleanup_dev_servers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Set

from _internal.safe_cleanup_dev_servers.win32_proc import (
    TARGET_PORTS,
    _HAS_PSUTIL,
    _facade_attr,
    _scan_netstat_listening_pids,
    _workspace_root,
    is_target_workspace_process,
    parse_ports_arg,
    psutil,
)


def scan_listening_port_range(
    port_min: int = 3000,
    port_max: int = 9999,
    workspace_root: Optional[Path | str] = None,
) -> Set[int]:
    """Scansiona in modo fail-closed le porte TCP LISTENING appartenenti al workspace."""
    pids: Set[int] = set()
    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws
    current_pid = os.getpid()
    has_ps = bool(_facade_attr("_HAS_PSUTIL", _HAS_PSUTIL))
    ps_mod = _facade_attr("psutil", psutil)
    sys_mod = _facade_attr("sys", sys)
    target_fn = _facade_attr("is_target_workspace_process", is_target_workspace_process)

    if has_ps and ps_mod is not None:
        try:
            for conn in ps_mod.net_connections(kind="inet"):
                if conn.status == ps_mod.CONN_LISTEN and conn.laddr and conn.pid:
                    port_num = int(conn.laddr.port)
                    if port_min <= port_num <= port_max and conn.pid != current_pid:
                        if target_fn(int(conn.pid), resolved_ws):
                            pids.add(int(conn.pid))
            return pids
        except Exception:
            pass

    if sys_mod.platform == "win32":
        scan_fn = _facade_attr("_scan_netstat_listening_pids", _scan_netstat_listening_pids)
        return scan_fn(port_range=(port_min, port_max), workspace_root=resolved_ws)
    return pids


def get_pids_listening_on_ports(
    ports: Sequence[int] = TARGET_PORTS,
    workspace_root: Optional[Path | str] = None,
) -> Set[int]:
    """Individua i PID in ascolto sulle porte target filtrati fail-closed per il workspace."""
    pids: Set[int] = set()
    port_set = {int(p) for p in ports}
    current_pid = os.getpid()
    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws
    has_ps = bool(_facade_attr("_HAS_PSUTIL", _HAS_PSUTIL))
    ps_mod = _facade_attr("psutil", psutil)
    sys_mod = _facade_attr("sys", sys)
    target_fn = _facade_attr("is_target_workspace_process", is_target_workspace_process)

    if has_ps and ps_mod is not None:
        try:
            for conn in ps_mod.net_connections(kind="inet"):
                if conn.status == ps_mod.CONN_LISTEN and conn.laddr:
                    if conn.laddr.port in port_set and conn.pid:
                        if conn.pid != current_pid and target_fn(conn.pid, resolved_ws):
                            pids.add(int(conn.pid))
            return pids
        except Exception:
            pass

    if sys_mod.platform == "win32":
        scan_fn = _facade_attr("_scan_netstat_listening_pids", _scan_netstat_listening_pids)
        return scan_fn(port_set=port_set, workspace_root=resolved_ws)
    return pids


def kill_pid_tree(pid: int) -> bool:
    """Termina forzatamente un processo e tutti i suoi figli tramite taskkill."""
    if pid <= 0 or pid == os.getpid():
        return False
    sub_mod = _facade_attr("subprocess", subprocess)
    try:
        res = sub_mod.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
        )
        return res.returncode == 0
    except Exception as exc:
        print(f"Errore durante la terminazione del PID {pid}: {exc}", file=sys.stderr)
        return False


def run_cleanup(
    workspace_root: Optional[Path | str] = None,
    dry_run: bool = False,
    as_json: bool = False,
    ports: Optional[Sequence[int] | str] = None,
) -> int:
    """Esegue la bonifica fail-closed dei soli server appartenenti al workspace sulle porte target."""
    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws
    parse_fn = _facade_attr("parse_ports_arg", parse_ports_arg)
    get_pids_fn = _facade_attr("get_pids_listening_on_ports", get_pids_listening_on_ports)
    kill_fn = _facade_attr("kill_pid_tree", kill_pid_tree)
    time_mod = _facade_attr("time", time)

    effective_ports = parse_fn(ports)
    pids_to_kill = set(get_pids_fn(effective_ports, workspace_root=resolved_ws))

    terminated: List[int] = []
    if pids_to_kill and not dry_run:
        for pid in pids_to_kill:
            if kill_fn(pid):
                terminated.append(pid)
        time_mod.sleep(0.3)

    if as_json:
        print(
            json.dumps(
                {
                    "status": "OK",
                    "workspace_root": str(resolved_ws),
                    "dry_run": dry_run,
                    "target_ports": effective_ports,
                    "detected_pids": sorted(list(pids_to_kill)),
                    "terminated_pids": sorted(terminated),
                },
                indent=2,
            )
        )
        return 0

    print("======================================================================")
    print("BONIFICA SERVER DI SVILUPPO E PREVENZIONE LOCK FILE WINDOWS")
    print("======================================================================")

    ports_str = ", ".join(str(p) for p in effective_ports)
    if not pids_to_kill:
        print(f"Nessun server attivo rilevato sulle porte target ({ports_str}).")
    elif dry_run:
        print(f"[DRY-RUN] Rilevati {len(pids_to_kill)} processi server: {list(pids_to_kill)}")
    else:
        print(f"Rilevati {len(pids_to_kill)} processi server da terminare: {list(pids_to_kill)}")
        for pid in pids_to_kill:
            status_tag = "TERMINATO" if pid in terminated else "ERRORE"
            print(f"  PID {pid}: {status_tag}")

    print("======================================================================")
    return 0


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI per safe_cleanup_dev_servers."""
    parser = argparse.ArgumentParser(
        description="Bonifica sicura dei server di sviluppo per NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument("--workspace-root", type=str, default=None, help="Directory radice del workspace target")
    parser.add_argument("--ports", type=str, default=None, help="Elenco porte separate da virgola da bonificare")
    parser.add_argument("--dry-run", action="store_true", help="Elenca i PID rilevati senza terminarli")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato in formato JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per la bonifica sicura dei server di sviluppo."""
    args = _build_cli_parser().parse_args(argv)
    run_fn = _facade_attr("run_cleanup", run_cleanup)
    return run_fn(
        workspace_root=args.workspace_root,
        dry_run=args.dry_run,
        as_json=args.json,
        ports=args.ports,
    )

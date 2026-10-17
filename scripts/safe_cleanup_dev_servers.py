# -*- coding: utf-8 -*-
"""
Utilità di bonifica dei server di sviluppo per Nexus Keystone v3.0.0-STE100-Unified.
Termina solo i processi server appartenenti al workspace target e protegge il PID attivo.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TARGET_PORTS: List[int] = [8000, 8080, 5000, 3000]
DEV_PROCESS_KEYWORDS: Tuple[str, ...] = (
    "python",
    "uvicorn",
    "fastapi",
    "flask",
    "node",
    "vite",
    "next",
    "gunicorn",
)


def is_target_workspace_process(
    pid: int,
    workspace_root: Optional[Path | str] = None,
) -> bool:
    """Verifica se il processo appartiene al workspace target e non e il processo corrente."""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    if pid <= 0 or pid in (current_pid, parent_pid):
        return False

    if not _HAS_PSUTIL or psutil is None:
        return True

    try:
        proc = psutil.Process(pid)
        proc_name = (proc.name() or "").lower()
        cmdline_list = proc.cmdline() or []
        cmdline_str = " ".join(cmdline_list).lower()

        is_dev_binary = any(
            kw in proc_name or kw in cmdline_str for kw in DEV_PROCESS_KEYWORDS
        )
        if not is_dev_binary:
            return False

        if workspace_root is None:
            return True

        ws_norm = str(Path(workspace_root).resolve()).lower().replace("/", "\\")
        try:
            proc_cwd = str(Path(proc.cwd()).resolve()).lower().replace("/", "\\")
        except Exception:
            proc_cwd = ""

        cmd_norm = cmdline_str.replace("/", "\\")
        if ws_norm in proc_cwd or ws_norm in cmd_norm:
            return True
        return False
    except Exception:
        return False


def get_pids_listening_on_ports(
    ports: Sequence[int] = TARGET_PORTS,
    workspace_root: Optional[Path | str] = None,
) -> Set[int]:
    """Individua i PID in ascolto sulle porte target filtrati per il workspace."""
    pids: Set[int] = set()
    port_set = {int(p) for p in ports}
    current_pid = os.getpid()

    if _HAS_PSUTIL and psutil is not None:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == psutil.CONN_LISTEN and conn.laddr:
                    if conn.laddr.port in port_set and conn.pid:
                        if conn.pid != current_pid and is_target_workspace_process(
                            conn.pid,
                            workspace_root,
                        ):
                            pids.add(int(conn.pid))
            if pids:
                return pids
        except Exception:
            pass

    try:
        output = subprocess.check_output(
            ["netstat", "-ano"],
            shell=False,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in output.splitlines():
            line = line.strip()
            if not line or "LISTENING" not in line:
                continue
            parts = line.split()
            if len(parts) >= 5:
                local_addr = parts[1]
                pid_str = parts[-1]
                for p in port_set:
                    if local_addr.endswith(f":{p}"):
                        try:
                            pid = int(pid_str)
                            if pid > 0 and pid != current_pid:
                                if is_target_workspace_process(pid, workspace_root):
                                    pids.add(pid)
                        except ValueError:
                            pass
    except Exception as exc:
        print(f"Avviso durante la scansione porte: {exc}", file=sys.stderr)

    return pids


def kill_pid_tree(pid: int) -> bool:
    """Termina forzatamente un processo e tutti i suoi figli."""
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        res = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0
    except Exception as exc:
        print(f"Errore durante la terminazione del PID {pid}: {exc}", file=sys.stderr)
        return False


def run_cleanup(
    workspace_root: Optional[Path | str] = None,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    """Esegue la bonifica dei server di sviluppo attivi sulle porte target."""
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else _workspace_root
    pids_to_kill = get_pids_listening_on_ports(
        TARGET_PORTS,
        workspace_root=resolved_ws,
    )

    terminated: List[int] = []
    if pids_to_kill and not dry_run:
        for pid in pids_to_kill:
            if kill_pid_tree(pid):
                terminated.append(pid)
        time.sleep(0.3)

    if as_json:
        print(
            json.dumps(
                {
                    "status": "OK",
                    "workspace_root": str(resolved_ws),
                    "dry_run": dry_run,
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

    if not pids_to_kill:
        print("Nessun server attivo rilevato sulle porte target (8000, 8080, 5000, 3000).")
    elif dry_run:
        print(f"[DRY-RUN] Rilevati {len(pids_to_kill)} processi server: {list(pids_to_kill)}")
    else:
        print(f"Rilevati {len(pids_to_kill)} processi server da terminare: {list(pids_to_kill)}")
        for pid in pids_to_kill:
            status_tag = "TERMINATO" if pid in terminated else "ERRORE"
            print(f"  PID {pid}: {status_tag}")

    print("======================================================================")
    return 0


def main() -> int:
    """Interfaccia CLI per la bonifica sicura dei server di sviluppo."""
    parser = argparse.ArgumentParser(
        description="Bonifica sicura dei server di sviluppo per il workspace attivo"
    )
    parser.add_argument(
        "--workspace-root",
        type=str,
        default=None,
        help="Directory radice del workspace target",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Elenca i PID rilevati senza terminarli",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )
    args = parser.parse_args()
    return run_cleanup(
        workspace_root=args.workspace_root,
        dry_run=args.dry_run,
        as_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())

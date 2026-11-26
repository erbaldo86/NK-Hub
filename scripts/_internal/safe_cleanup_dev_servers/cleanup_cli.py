# -*- coding: utf-8 -*-
"""Scansione porte attive, terminazione PID tree e CLI per safe_cleanup_dev_servers."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from _internal.nk_common.lane_leases import get_protected_leased_pids
from _internal.safe_cleanup_dev_servers.win32_proc import (
    TARGET_PORTS,
    _HAS_PSUTIL,
    _call_target_fn,
    _facade_attr,
    _scan_netstat_listening_pids,
    _workspace_root,
    is_target_workspace_process,
    parse_ports_arg,
    psutil,
)


def _port_in_filter(
    port_num: int,
    port_range: Optional[tuple[int, int]],
    port_set: Optional[Set[int]],
) -> bool:
    if port_set is not None:
        return port_num in port_set
    if port_range is not None:
        return port_range[0] <= port_num <= port_range[1]
    return False


def _call_netstat_scan(
    *,
    resolved_ws: Path,
    strict_scope: bool,
    port_range: Optional[tuple[int, int]] = None,
    port_set: Optional[Set[int]] = None,
) -> Set[int]:
    scan_fn = _facade_attr("_scan_netstat_listening_pids", _scan_netstat_listening_pids)
    kwargs: Dict[str, Any] = {"workspace_root": resolved_ws}
    if port_range is not None:
        kwargs["port_range"] = port_range
    if port_set is not None:
        kwargs["port_set"] = port_set
    if strict_scope:
        kwargs["strict_scope"] = True
    return scan_fn(**kwargs)


def _collect_psutil_pids(
    ps_mod: Any,
    target_fn: Any,
    resolved_ws: Path,
    strict_scope: bool,
    port_range: Optional[tuple[int, int]],
    port_set: Optional[Set[int]],
) -> Set[int]:
    pids: Set[int] = set()
    current_pid = os.getpid()
    for conn in ps_mod.net_connections(kind="inet"):
        if conn.status != ps_mod.CONN_LISTEN or not conn.laddr or not conn.pid:
            continue
        if conn.pid == current_pid or not _port_in_filter(int(conn.laddr.port), port_range, port_set):
            continue
        if _call_target_fn(target_fn, int(conn.pid), resolved_ws, strict_scope):
            pids.add(int(conn.pid))
    return pids


def _scan_ports_compat(
    *,
    workspace_root: Optional[Path | str],
    strict_scope: bool,
    port_range: Optional[tuple[int, int]] = None,
    port_set: Optional[Set[int]] = None,
) -> Set[int]:
    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws
    has_ps = bool(_facade_attr("_HAS_PSUTIL", _HAS_PSUTIL))
    ps_mod = _facade_attr("psutil", psutil)
    target_fn = _facade_attr("is_target_workspace_process", is_target_workspace_process)

    if has_ps and ps_mod is not None:
        try:
            return _collect_psutil_pids(ps_mod, target_fn, resolved_ws, strict_scope, port_range, port_set)
        except (OSError, RuntimeError, AttributeError):
            return _call_netstat_scan(
                resolved_ws=resolved_ws, strict_scope=strict_scope, port_range=port_range, port_set=port_set
            )

    return _call_netstat_scan(
        resolved_ws=resolved_ws, strict_scope=strict_scope, port_range=port_range, port_set=port_set
    )


def scan_listening_port_range(
    port_min: int = 3000,
    port_max: int = 9999,
    workspace_root: Optional[Path | str] = None,
    *,
    strict_scope: bool = False,
) -> Set[int]:
    """Scansiona in modo fail-closed le porte TCP LISTENING appartenenti al workspace."""
    return _scan_ports_compat(
        workspace_root=workspace_root, strict_scope=strict_scope, port_range=(port_min, port_max)
    )


def get_pids_listening_on_ports(
    ports: Sequence[int] = TARGET_PORTS,
    workspace_root: Optional[Path | str] = None,
    *,
    strict_scope: bool = False,
) -> Set[int]:
    """Individua i PID in ascolto sulle porte target filtrati fail-closed per il workspace."""
    return _scan_ports_compat(
        workspace_root=workspace_root, strict_scope=strict_scope, port_set={int(p) for p in ports}
    )


def kill_pid_tree(pid: int) -> bool:
    """Termina forzatamente un processo e tutti i suoi figli tramite taskkill o POSIX."""
    if pid <= 0 or pid == os.getpid():
        return False
    sys_mod = _facade_attr("sys", sys)
    sub_mod = _facade_attr("subprocess", subprocess)
    try:
        if sys_mod.platform == "win32":
            res = sub_mod.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5.0,
            )
            return res.returncode == 0
        ps_mod = _facade_attr("psutil", psutil)
        if ps_mod is not None:
            try:
                parent = ps_mod.Process(pid)
                children_fn = getattr(parent, "children", None)
                kill_fn = getattr(parent, "kill", None)
                if callable(children_fn) and callable(kill_fn):
                    for child in children_fn(recursive=True):
                        child_kill = getattr(child, "kill", None)
                        if callable(child_kill):
                            try:
                                child_kill()
                            except Exception:
                                pass
                    kill_fn()
                    return True
            except Exception:
                pass
        sig = getattr(signal, "SIGKILL", signal.SIGTERM)
        os.kill(pid, sig)
        return True
    except Exception as exc:
        print(f"Errore durante la terminazione del PID {pid}: {exc}", file=sys.stderr)
        return False


def _invoke_get_pids(get_pids_fn: Any, ports: Sequence[int], resolved_ws: Path, strict_scope: bool) -> Set[int]:
    if strict_scope:
        try:
            return set(get_pids_fn(ports, workspace_root=resolved_ws, strict_scope=True))
        except TypeError:
            pass
    return set(get_pids_fn(ports, workspace_root=resolved_ws))


def _terminate_target_pids(
    pids_to_kill: Set[int], dry_run: bool, kill_fn: Any, time_mod: Any
) -> List[int]:
    if not pids_to_kill or dry_run:
        return []
    terminated = [pid for pid in pids_to_kill if kill_fn(pid)]
    time_mod.sleep(0.3)
    return terminated


def _print_cleanup_text(
    effective_ports: Sequence[int],
    pids_to_kill: Set[int],
    terminated: Sequence[int],
    dry_run: bool,
) -> None:
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


def _pick_cleanup_hook(name: str, current: Any, orig: Any) -> Any:
    """Privilegia monkeypatch locali del sottomodulo rispetto alla facciata cacheata."""
    return current if current is not orig else _facade_attr(name, current)


def run_cleanup(
    workspace_root: Optional[Path | str] = None,
    dry_run: bool = False,
    as_json: bool = False,
    ports: Optional[Sequence[int] | str] = None,
    *,
    lane_id: Optional[str] = None,
    strict_scope: bool = False,
) -> int:
    """Esegue la bonifica fail-closed dei server workspace rispettando i lease di altre lane."""
    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws
    parse_fn = _pick_cleanup_hook("parse_ports_arg", parse_ports_arg, _ORIG_PARSE_PORTS)
    get_pids_fn = _pick_cleanup_hook("get_pids_listening_on_ports", get_pids_listening_on_ports, _ORIG_GET_PIDS)
    kill_fn = _pick_cleanup_hook("kill_pid_tree", kill_pid_tree, _ORIG_KILL_PID)
    time_mod = _pick_cleanup_hook("time", time, _ORIG_TIME)

    effective_ports = parse_fn(ports)
    detected_pids = _invoke_get_pids(get_pids_fn, effective_ports, resolved_ws, strict_scope)
    excl_root = resolved_ws
    protected_pids = get_protected_leased_pids(exclude_lane_id=lane_id, exclude_repo_root=excl_root)
    skipped_leased = sorted(detected_pids & protected_pids)
    pids_to_kill = detected_pids - protected_pids
    terminated = _terminate_target_pids(pids_to_kill, dry_run, kill_fn, time_mod)

    if as_json:
        print(
            json.dumps(
                {
                    "status": "OK",
                    "workspace_root": str(resolved_ws),
                    "lane_id": lane_id,
                    "strict_scope": bool(strict_scope),
                    "dry_run": dry_run,
                    "target_ports": effective_ports,
                    "detected_pids": sorted(list(pids_to_kill)),
                    "skipped_leased_pids": skipped_leased,
                    "terminated_pids": sorted(terminated),
                },
                indent=2,
            )
        )
        return 0

    _print_cleanup_text(effective_ports, pids_to_kill, terminated, dry_run)
    return 0


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI per safe_cleanup_dev_servers."""
    parser = argparse.ArgumentParser(
        description="Bonifica sicura dei server di sviluppo per NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument("--workspace-root", type=str, default=None, help="Directory radice del workspace target")
    parser.add_argument("--lane-id", type=str, default=None, help="ID lane corrente da bonificare")
    parser.add_argument("--strict-scope", action="store_true", help="Limita la bonifica al solo workspace-root")
    parser.add_argument("--ports", type=str, default=None, help="Elenco porte separate da virgola da bonificare")
    parser.add_argument("--dry-run", action="store_true", help="Elenca i PID rilevati senza terminarli")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato in formato JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per la bonifica sicura dei server di sviluppo."""
    args = _build_cli_parser().parse_args(argv)
    run_fn = _facade_attr("run_cleanup", run_cleanup)
    extra_kw = {}
    if getattr(args, "lane_id", None) is not None:
        extra_kw["lane_id"] = args.lane_id
    if getattr(args, "strict_scope", False):
        extra_kw["strict_scope"] = True
    return run_fn(
        workspace_root=args.workspace_root,
        dry_run=args.dry_run,
        as_json=args.json,
        ports=args.ports,
        **extra_kw,
    )


_ORIG_PARSE_PORTS = parse_ports_arg
_ORIG_GET_PIDS = get_pids_listening_on_ports
_ORIG_KILL_PID = kill_pid_tree
_ORIG_TIME = time

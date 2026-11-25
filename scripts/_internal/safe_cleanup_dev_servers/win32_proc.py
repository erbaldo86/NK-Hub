# -*- coding: utf-8 -*-
"""Scansione porte TCP netstat/CIM e filtro processi workspace Win32."""

from __future__ import annotations

import contextvars
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.paths import (
    cmd_mentions_nk_proget_online,
    is_nk_proget_online_path,
    reconfigure_streams,
    resolve_nk_proget_roots,
)

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
_FACADE_MOD_NAMES: Tuple[str, ...] = (
    "safe_cleanup_dev_servers",
    "scripts.safe_cleanup_dev_servers",
)

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False

reconfigure_streams()

TARGET_PORTS: List[int] = [8000, 8080, 5000, 3000, 8018, 8090]
PORT_SCAN_RANGE: Tuple[int, int] = (3000, 9999)
DEV_PROCESS_KEYWORDS: Tuple[str, ...] = (
    "python", "uvicorn", "fastapi", "flask",
    "node", "vite", "next", "gunicorn",
)

_CIM_BATCH_CACHE: contextvars.ContextVar[Optional[Dict[int, Tuple[str, str, str]]]] = (
    contextvars.ContextVar("_cim_batch_cache", default=None)
)


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


def parse_ports_arg(ports_arg: Optional[Sequence[int] | str] = None) -> List[int]:
    """Analizza il parametro --ports restituendo la lista di porte valida."""
    if ports_arg is None:
        return list(TARGET_PORTS)
    parsed: List[int] = []
    if isinstance(ports_arg, str):
        for raw in ports_arg.split(","):
            tok = raw.strip()
            if tok.isdigit():
                val = int(tok)
                if 1 <= val <= 65535 and val not in parsed:
                    parsed.append(val)
    else:
        for item in ports_arg:
            val = int(item)
            if 1 <= val <= 65535 and val not in parsed:
                parsed.append(val)
    return parsed if parsed else list(TARGET_PORTS)


def _is_subpath_str(candidate_norm: str, root_norm: str) -> bool:
    """Verifica con confine di directory esatto che candidate_norm risieda sotto root_norm."""
    if not candidate_norm or not root_norm:
        return False
    base = root_norm.rstrip("\\")
    return candidate_norm == base or candidate_norm.startswith(base + "\\")


def _query_win32_cim_processes(pids: Sequence[int]) -> Dict[int, Tuple[str, str, str]]:
    """Interroga Win32_Process via PowerShell CIM restituendo {pid: (name, cmdline, exe)}."""
    info_map: Dict[int, Tuple[str, str, str]] = {}
    clean_pids = sorted({int(p) for p in pids if isinstance(p, int) and p > 0})
    sys_mod = _facade_attr("sys", sys)
    if sys_mod.platform != "win32" or not clean_pids:
        return info_map
    filter_expr = " OR ".join(f"ProcessId={p}" for p in clean_pids)
    ps_cmd = (
        f'Get-CimInstance Win32_Process -Filter "{filter_expr}" '
        "| Select-Object ProcessId,Name,CommandLine,ExecutablePath | ConvertTo-Json -Compress"
    )
    sub_mod = _facade_attr("subprocess", subprocess)
    try:
        res = sub_mod.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=3.0, shell=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return info_map
        parsed = json.loads(res.stdout)
        rows = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
        for row in rows:
            if isinstance(row, dict):
                raw_pid = row.get("ProcessId")
                if isinstance(raw_pid, int) and not isinstance(raw_pid, bool):
                    info_map[raw_pid] = (
                        str(row.get("Name") or "").lower(),
                        str(row.get("CommandLine") or "").lower(),
                        str(row.get("ExecutablePath") or "").lower(),
                    )
    except Exception:
        return {}
    return info_map


def _iter_external_workspace_norms(effective_ws: Path) -> List[str]:
    """Normalizza le root esterne (NK_External_Projects e NK Proget/Locale) escludendo Online."""
    ext_cand = (
        effective_ws / "NK_External_Projects"
        if (effective_ws / "NK_External_Projects").exists()
        else effective_ws.parent / "NK_External_Projects"
    )
    raw_roots: List[Path] = [ext_cand]
    locale_root, _ = resolve_nk_proget_roots(effective_ws)
    if locale_root is not None:
        raw_roots.append(locale_root)
    norms: List[str] = []
    for cand in raw_roots:
        if not is_nk_proget_online_path(cand):
            norms.append(os.path.realpath(str(cand)).lower().replace("/", "\\").rstrip("\\"))
    return norms


def _process_targets_readonly_online(proc_cwd: str, exe_norm: str, cmd_norm: str) -> bool:
    """Verifica se il processo appartiene al mirror protetto NK Proget/Online."""
    return (
        is_nk_proget_online_path(proc_cwd)
        or is_nk_proget_online_path(exe_norm)
        or cmd_mentions_nk_proget_online(cmd_norm)
    )


def _matches_any_norm_root(
    proc_cwd: str,
    exe_norm: str,
    cmd_norm: str,
    norm_roots: Sequence[str],
) -> bool:
    """Verifica la corrispondenza su almeno una root consentita escludendo NK Proget/Online."""
    if _process_targets_readonly_online(proc_cwd, exe_norm, cmd_norm):
        return False
    for norm_r in norm_roots:
        if _is_subpath_str(proc_cwd, norm_r) or _is_subpath_str(exe_norm, norm_r) or (norm_r and norm_r in cmd_norm):
            return True
    return False


def _matches_workspace_paths(
    proc_name: str,
    cmdline_str: str,
    proc_cwd: str,
    proc_exe: str,
    workspace_root: Optional[Path | str],
) -> bool:
    """Applica il filtro fail-closed su binario dev e percorso workspace o progetti esterni."""
    if not any(kw in proc_name or kw in cmdline_str for kw in DEV_PROCESS_KEYWORDS):
        return False

    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    effective_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws.resolve()
    ws_norm = os.path.realpath(str(effective_ws)).lower().replace("/", "\\").rstrip("\\")
    cmd_norm = cmdline_str.replace("/", "\\")
    exe_norm = os.path.realpath(proc_exe).lower().replace("/", "\\").rstrip("\\") if proc_exe else ""

    if _matches_any_norm_root(proc_cwd, exe_norm, cmd_norm, (ws_norm,)):
        return True
    if workspace_root is None or effective_ws == default_ws.resolve():
        return _matches_any_norm_root(proc_cwd, exe_norm, cmd_norm, _iter_external_workspace_norms(effective_ws))
    return False


def is_target_workspace_process(
    pid: int,
    workspace_root: Optional[Path | str] = None,
) -> bool:
    """Verifica fail-closed se il processo appartiene al workspace target o a progetti esterni."""
    if pid <= 0 or pid in (os.getpid(), os.getppid()):
        return False

    has_ps = bool(_facade_attr("_HAS_PSUTIL", _HAS_PSUTIL))
    ps_mod = _facade_attr("psutil", psutil)
    sys_mod = _facade_attr("sys", sys)

    if not has_ps or ps_mod is None:
        if sys_mod.platform != "win32":
            proc_dir = Path(f"/proc/{pid}")
            if not proc_dir.is_dir():
                return False
            try:
                cmd_raw = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace").lower()
                cwd_str = os.path.realpath(str(proc_dir / "cwd")).lower().replace("/", "\\").rstrip("\\")
                exe_str = os.path.realpath(str(proc_dir / "exe"))
                proc_name = os.path.basename(exe_str).lower()
                return _matches_workspace_paths(proc_name, cmd_raw, cwd_str, exe_str, workspace_root)
            except OSError:
                return False
        batch_cache = _CIM_BATCH_CACHE.get()
        if batch_cache is not None:
            entry = batch_cache.get(pid)
        else:
            query_fn = _facade_attr("_query_win32_cim_processes", _query_win32_cim_processes)
            entry = query_fn([pid]).get(pid)
        if entry is None:
            return False
        proc_name, cmdline_str, proc_exe = entry
        return _matches_workspace_paths(proc_name, cmdline_str, "", proc_exe, workspace_root)

    try:
        proc = ps_mod.Process(pid)
        proc_name = (proc.name() or "").lower()
        cmdline_str = " ".join(proc.cmdline() or []).lower()
        try:
            proc_cwd = os.path.realpath(str(proc.cwd())).lower().replace("/", "\\").rstrip("\\")
        except Exception:
            proc_cwd = ""
        return _matches_workspace_paths(proc_name, cmdline_str, proc_cwd, "", workspace_root)
    except Exception:
        return False


def _scan_netstat_listening_pids(
    *,
    port_set: Optional[Set[int]] = None,
    port_range: Optional[Tuple[int, int]] = None,
    workspace_root: Optional[Path | str] = None,
) -> Set[int]:
    """Scansiona le porte LISTENING tramite netstat o ss con filtro fail-closed."""
    pids: Set[int] = set()
    current_pid = os.getpid()
    default_ws = Path(_facade_attr("_workspace_root", _workspace_root))
    resolved_ws = Path(workspace_root).resolve() if workspace_root is not None else default_ws
    sub_mod = _facade_attr("subprocess", subprocess)
    sys_mod = _facade_attr("sys", sys)

    candidate_pids: Set[int] = set()
    scan_cmd = ["netstat", "-ano"] if sys_mod.platform == "win32" else ["ss", "-ltnp"]
    try:
        output = sub_mod.check_output(
            scan_cmd,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=sub_mod.DEVNULL,
            timeout=5.0,
        )
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            line_ports_pids: List[Tuple[int, int]] = []
            if "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5 and ":" in parts[1]:
                    try:
                        line_ports_pids.append((int(parts[1].rsplit(":", 1)[1]), int(parts[-1])))
                    except ValueError:
                        continue
            elif line.startswith("LISTEN"):
                parts = line.split()
                if len(parts) >= 4 and ":" in parts[3]:
                    local_tok = parts[3].replace("[", "").replace("]", "")
                    try:
                        port_num = int(local_tok.rsplit(":", 1)[1])
                    except ValueError:
                        continue
                    for pid_txt in re.findall(r"pid=(\d+)", line):
                        line_ports_pids.append((port_num, int(pid_txt)))
            for port_num, pid in line_ports_pids:
                if pid <= 0 or pid == current_pid:
                    continue
                if port_set is not None and port_num not in port_set:
                    continue
                if port_range is not None and not (port_range[0] <= port_num <= port_range[1]):
                    continue
                candidate_pids.add(pid)
    except Exception as exc:
        print(f"Avviso durante la scansione porte: {exc}", file=sys.stderr)
        return pids

    if not candidate_pids:
        return pids

    has_ps = bool(_facade_attr("_HAS_PSUTIL", _HAS_PSUTIL))
    ps_mod = _facade_attr("psutil", psutil)
    target_fn = _facade_attr("is_target_workspace_process", is_target_workspace_process)

    if (not has_ps or ps_mod is None) and sys_mod.platform == "win32":
        query_fn = _facade_attr("_query_win32_cim_processes", _query_win32_cim_processes)
        token = _CIM_BATCH_CACHE.set(query_fn(sorted(candidate_pids)))
        try:
            for pid in candidate_pids:
                if target_fn(pid, resolved_ws):
                    pids.add(pid)
        finally:
            _CIM_BATCH_CACHE.reset(token)
        return pids

    for pid in candidate_pids:
        if target_fn(pid, resolved_ws):
            pids.add(pid)
    return pids

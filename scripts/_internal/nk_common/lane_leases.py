# -*- coding: utf-8 -*-
"""Registro runtime lease NVMe con controllo creation-time PID e porte loopback dedicate."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex, resolve_local_appdata_dir

_LEASES_MUTEX_NAME = "Local\\NK_RuntimeLeases"
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_WINDOWS_EPOCH_OFFSET = 11644473600.0


def _leases_file_path(registry_path: Optional[Union[str, Path]] = None) -> Path:
    if registry_path is not None:
        return Path(registry_path).resolve()
    return (resolve_local_appdata_dir() / "nk_hub" / "runtime_leases.json").resolve()


def _canon_root(repo_root: Union[str, Path]) -> str:
    return os.path.realpath(str(repo_root)).lower().replace("/", "\\").rstrip("\\")


def _load_kernel32_proc() -> Any:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if hasattr(getattr(k32, "OpenProcess", None), "restype"):
        k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.GetProcessTimes.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        k32.GetProcessTimes.restype = ctypes.c_bool
        k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k32.GetExitCodeProcess.restype = ctypes.c_bool
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.restype = ctypes.c_bool
    return k32


def get_process_create_time_epoch(pid: int) -> Optional[float]:
    """Restituisce il timestamp epoch di creazione processo per prevenire PID reuse."""
    if pid <= 0:
        return None
    if sys.platform == "win32":
        try:
            k32 = _load_kernel32_proc()
            h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return None
            try:
                ct, et, kt, ut = (
                    ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64()
                )
                if not k32.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
                    return None
                return round((ct.value / 10_000_000.0) - _WINDOWS_EPOCH_OFFSET, 3)
            finally:
                k32.CloseHandle(h)
        except Exception:
            return None
    try:
        import psutil
        return round(float(psutil.Process(int(pid)).create_time()), 3)
    except Exception:
        return None


def _clear_win32_last_error() -> None:
    """Azzera il codice di errore Win32 thread-local su piattaforme supportate."""
    if hasattr(ctypes, "set_last_error"):
        ctypes.set_last_error(0)


def _get_win32_last_error() -> int:
    """Legge l'ultimo codice di errore Win32 thread-local su piattaforme supportate."""
    return int(ctypes.get_last_error()) if hasattr(ctypes, "get_last_error") else 0


def _is_pid_running_os(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        k32 = _load_kernel32_proc()
        _clear_win32_last_error()
        h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return _get_win32_last_error() == _ERROR_ACCESS_DENIED
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and int(code.value) == _STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def is_pid_lease_alive(pid: int, create_time_epoch: Optional[float]) -> bool:
    """Verifica che il PID sia attivo e compatibile con il timestamp di creazione atteso."""
    if not _is_pid_running_os(pid):
        return False
    if create_time_epoch is not None:
        live_ct = get_process_create_time_epoch(pid)
        if live_ct is not None and abs(live_ct - float(create_time_epoch)) > 2.0:
            return False
    return True


def _read_store(reg_path: Path) -> Dict[str, Any]:
    if not reg_path.is_file():
        return {"version": 1, "leases": {}}
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and isinstance(data.get("leases"), dict):
            return data
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    return {"version": 1, "leases": {}}


def _prune_stale_leases(leases: Dict[str, Any], now_ts: float) -> bool:
    changed = False
    for lid in list(leases.keys()):
        rec = leases.get(lid)
        if not isinstance(rec, dict):
            leases.pop(lid, None)
            changed = True
            continue
        ttl = float(rec.get("ttl_sec", 300.0) or 300.0)
        upd = float(rec.get("updated_at", 0.0) or 0.0)
        pid = int(rec.get("pid", 0) or 0)
        ctime = rec.get("process_create_time_epoch")
        if (now_ts - upd) > ttl or not is_pid_lease_alive(pid, ctime):
            leases.pop(lid, None)
            changed = True
    return changed


def register_runtime_lease(
    repo_root: Union[str, Path],
    *,
    lane_id: str = "default",
    conversation_id: str = "",
    pid: Optional[int] = None,
    ports: Sequence[int] = (),
    ttl_sec: float = 300.0,
    lease_id: Optional[str] = None,
    registry_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Registra o aggiorna un lease runtime atomico sotto Local\\NK_RuntimeLeases."""
    reg_p = _leases_file_path(registry_path)
    eff_pid = int(pid if pid is not None else os.getpid())
    eff_lid = str(lease_id or f"lease_{uuid.uuid4().hex[:12]}")
    now_ts = time.time()
    rec: Dict[str, Any] = {
        "lease_id": eff_lid,
        "repo_root": _canon_root(repo_root),
        "lane_id": str(lane_id or "default").strip(),
        "conversation_id": str(conversation_id or "").strip(),
        "pid": eff_pid,
        "process_create_time_epoch": get_process_create_time_epoch(eff_pid),
        "ports": sorted({int(p) for p in ports if 1 <= int(p) <= 65535}),
        "updated_at": now_ts,
        "ttl_sec": max(5.0, float(ttl_sec)),
    }
    with FailClosedNamedMutex(_LEASES_MUTEX_NAME, wait_ms=3000):
        store = _read_store(reg_p)
        _prune_stale_leases(store["leases"], now_ts)
        store["leases"][eff_lid] = rec
        ok, err = atomic_write_json(reg_p, store, indent=2, ensure_parent=True, fsync_data=False)
        if not ok:
            raise OSError(err or f"Impossibile salvare runtime lease in {reg_p}")
    return rec


def release_runtime_lease(
    lease_id: str,
    *,
    registry_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Rimuove un lease dal registro runtime restituendo True se era presente."""
    reg_p = _leases_file_path(registry_path)
    with FailClosedNamedMutex(_LEASES_MUTEX_NAME, wait_ms=3000):
        store = _read_store(reg_p)
        removed = store["leases"].pop(str(lease_id), None) is not None
        if removed:
            atomic_write_json(reg_p, store, indent=2, ensure_parent=True, fsync_data=False)
        return removed


def list_active_leases(
    repo_root: Optional[Union[str, Path]] = None,
    *,
    prune_dead: bool = True,
    registry_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Elenca i lease attivi filtrando opzionalmente per repo_root e bonificando quelli morti."""
    reg_p = _leases_file_path(registry_path)
    if not reg_p.is_file():
        return []
    now_ts = time.time()
    target_canon = _canon_root(repo_root) if repo_root is not None else None
    with FailClosedNamedMutex(_LEASES_MUTEX_NAME, wait_ms=3000):
        store = _read_store(reg_p)
        if prune_dead and _prune_stale_leases(store["leases"], now_ts):
            atomic_write_json(reg_p, store, indent=2, ensure_parent=True, fsync_data=False)
        items = list(store["leases"].values())
    if target_canon is None:
        return items
    return [r for r in items if isinstance(r, dict) and r.get("repo_root") == target_canon]


def get_active_leased_conversation_ids(
    repo_root: Union[str, Path],
    *,
    registry_path: Optional[Union[str, Path]] = None,
) -> Set[str]:
    """Restituisce i conversation_id con lease vivo sul repository target."""
    return {
        str(rec.get("conversation_id", "")).strip()
        for rec in list_active_leases(repo_root, prune_dead=True, registry_path=registry_path)
        if str(rec.get("conversation_id", "")).strip()
    }


def get_protected_leased_pids(
    *,
    exclude_lane_id: Optional[str] = None,
    exclude_repo_root: Optional[Union[str, Path]] = None,
    registry_path: Optional[Union[str, Path]] = None,
) -> Set[int]:
    """Restituisce i PID appartenenti ad altre lane o progetti attivi da proteggere."""
    ex_lane = str(exclude_lane_id).strip() if exclude_lane_id else None
    ex_root = _canon_root(exclude_repo_root) if exclude_repo_root is not None else None
    protected: Set[int] = set()
    for rec in list_active_leases(prune_dead=True, registry_path=registry_path):
        pid = int(rec.get("pid", 0) or 0)
        if pid <= 0:
            continue
        same_root = (ex_root is None) or (rec.get("repo_root") == ex_root)
        if ex_lane is not None and same_root and rec.get("lane_id") == ex_lane:
            continue
        protected.add(pid)
    return protected


def allocate_lane_loopback_port(
    lane_id: str,
    *,
    port_min: int = 18000,
    port_max: int = 28999,
    registry_path: Optional[Union[str, Path]] = None,
) -> int:
    """Alloca una porta TCP loopback 127.0.0.1 libera evitando porte gia leased."""
    span = max(1, int(port_max) - int(port_min) + 1)
    start_off = int(hashlib.sha256(str(lane_id or "default").encode("utf-8")).hexdigest()[:8], 16) % span
    leased_ports = {
        int(p)
        for rec in list_active_leases(prune_dead=True, registry_path=registry_path)
        for p in rec.get("ports", ())
    }
    for idx in range(min(span, 256)):
        cand = int(port_min) + ((start_off + idx) % span)
        if cand in leased_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", cand))
                return cand
            except OSError:
                continue
    raise OSError(f"Nessuna porta loopback libera nell'intervallo {port_min}..{port_max}")

"""Gestione Win32 Job Object, snapshot processi/thread e campionamento RSS."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
import time
from typing import Any, Optional, Set

from .constants import (
    INVALID_HANDLE_VALUE,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JobObjectExtendedLimitInformation,
    PROCESSENTRY32,
    PROCESS_MEMORY_COUNTERS,
    PROCESS_QUERY_INFORMATION,
    PROCESS_SET_QUOTA,
    PROCESS_TERMINATE,
    PROCESS_VM_READ,
    RESUME_THREAD_ERROR,
    TH32CS_SNAPPROCESS,
    TH32CS_SNAPTHREAD,
    THREADENTRY32,
    THREAD_SUSPEND_RESUME,
    _RSSMonitorState,
    _facade_attr,
)

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False


def _init_win32_handles() -> tuple[Any, Any]:
    """Inizializza le librerie ctypes Win32 kernel32 e psapi con firme strict."""
    if sys.platform != "win32":
        return None, None
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for fn_name, argt, rest in (
        ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], ctypes.c_void_p),
        ("Process32First", [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32)], wintypes.BOOL),
        ("Process32Next", [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32)], wintypes.BOOL),
        ("Thread32First", [ctypes.c_void_p, ctypes.POINTER(THREADENTRY32)], wintypes.BOOL),
        ("Thread32Next", [ctypes.c_void_p, ctypes.POINTER(THREADENTRY32)], wintypes.BOOL),
        ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], ctypes.c_void_p),
        ("OpenThread", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], ctypes.c_void_p),
        ("ResumeThread", [ctypes.c_void_p], wintypes.DWORD),
        ("CloseHandle", [ctypes.c_void_p], wintypes.BOOL),
        ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], ctypes.c_void_p),
        ("SetInformationJobObject", [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        ("AssignProcessToJobObject", [ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL),
    ):
        fn = getattr(k32, fn_name)
        fn.argtypes = argt
        fn.restype = rest
    if hasattr(k32, "K32GetProcessMemoryInfo"):
        k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    try:
        psapi_dll = ctypes.WinDLL("psapi", use_last_error=True)
        psapi_dll.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        psapi_dll.GetProcessMemoryInfo.restype = wintypes.BOOL
    except Exception:
        psapi_dll = None
    return k32, psapi_dll


_kernel32, _psapi = _init_win32_handles()


def _collect_descendant_pids(k32: Any, root_pid: int) -> Set[int]:
    """Raccoglie root_pid e tutti i PID discendenti tramite Toolhelp32."""
    pids: Set[int] = {root_pid}
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return pids
    try:
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        entries = []
        if k32.Process32First(ctypes.c_void_p(snap), ctypes.byref(pe)):
            while True:
                entries.append((pe.th32ProcessID, pe.th32ParentProcessID))
                if not k32.Process32Next(ctypes.c_void_p(snap), ctypes.byref(pe)):
                    break
        changed = True
        while changed:
            changed = False
            for c_pid, p_pid in entries:
                if p_pid in pids and c_pid not in pids:
                    pids.add(c_pid)
                    changed = True
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))
    return pids


def _create_kill_on_close_job() -> Optional[int]:
    """Crea e configura un Job Object Win32 con flag KILL_ON_JOB_CLOSE."""
    sys_mod = _facade_attr("sys", sys)
    k32 = _facade_attr("_kernel32", _kernel32)
    if sys_mod.platform != "win32" or k32 is None:
        return None
    try:
        h_job = k32.CreateJobObjectW(None, None)
        if not h_job or h_job == INVALID_HANDLE_VALUE:
            return None
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok_info = k32.SetInformationJobObject(
            ctypes.c_void_p(h_job),
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok_info:
            k32.CloseHandle(ctypes.c_void_p(h_job))
            return None
        return int(h_job)
    except Exception:
        return None


def _assign_pid_to_job(job_handle: int, pid: int) -> bool:
    """Associa un PID esistente al Job Object Win32 specificato."""
    sys_mod = _facade_attr("sys", sys)
    k32 = _facade_attr("_kernel32", _kernel32)
    if sys_mod.platform != "win32" or not job_handle or not pid or k32 is None:
        return False
    try:
        h_proc = k32.OpenProcess(
            PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_INFORMATION,
            False,
            pid,
        )
        if not h_proc or h_proc == INVALID_HANDLE_VALUE:
            return False
        try:
            assigned = k32.AssignProcessToJobObject(
                ctypes.c_void_p(job_handle),
                ctypes.c_void_p(h_proc),
            )
            return bool(assigned)
        finally:
            k32.CloseHandle(ctypes.c_void_p(h_proc))
    except Exception:
        return False


def _resume_process_primary_thread(pid: int) -> bool:
    """Riprende i thread sospesi del processo figlio creato con CREATE_SUSPENDED."""
    sys_mod = _facade_attr("sys", sys)
    k32 = _facade_attr("_kernel32", _kernel32)
    if sys_mod.platform != "win32" or not pid or k32 is None:
        return False
    resumed_any = False
    try:
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if not snap or snap == INVALID_HANDLE_VALUE:
            return False
        try:
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)
            if k32.Thread32First(ctypes.c_void_p(snap), ctypes.byref(te)):
                while True:
                    if int(te.th32OwnerProcessID) == int(pid):
                        h_thread = k32.OpenThread(
                            THREAD_SUSPEND_RESUME,
                            False,
                            te.th32ThreadID,
                        )
                        if h_thread and h_thread != INVALID_HANDLE_VALUE:
                            try:
                                for _ in range(8):
                                    prev_cnt = k32.ResumeThread(ctypes.c_void_p(h_thread))
                                    if prev_cnt == RESUME_THREAD_ERROR:
                                        break
                                    resumed_any = True
                                    if prev_cnt <= 1:
                                        break
                            finally:
                                k32.CloseHandle(ctypes.c_void_p(h_thread))
                    if not k32.Thread32Next(ctypes.c_void_p(snap), ctypes.byref(te)):
                        break
        finally:
            k32.CloseHandle(ctypes.c_void_p(snap))
    except Exception:
        return False
    return resumed_any


def _assign_to_kill_on_close_job(pid: int) -> Optional[int]:
    """Associa il processo a un Job Object Win32 con flag KILL_ON_JOB_CLOSE."""
    create_fn = _facade_attr("_create_kill_on_close_job", _create_kill_on_close_job)
    assign_fn = _facade_attr("_assign_pid_to_job", _assign_pid_to_job)
    k32 = _facade_attr("_kernel32", _kernel32)
    job_handle = create_fn()
    if job_handle is None:
        return None
    if assign_fn(job_handle, pid):
        return job_handle
    if k32 is not None:
        try:
            k32.CloseHandle(ctypes.c_void_p(job_handle))
        except Exception:
            pass
    return None


def _close_job_handle_safe(job_handle: Optional[int]) -> None:
    """Chiude in sicurezza un handle di Job Object Win32 se valido."""
    k32 = _facade_attr("_kernel32", _kernel32)
    if job_handle is not None and k32 is not None:
        try:
            k32.CloseHandle(ctypes.c_void_p(job_handle))
        except Exception:
            pass


def _terminate_process_tree_fallback(pid: int) -> int:
    """Termina ricorsivamente l'albero dei processi tramite Toolhelp32 con attesa locale di 25 ms."""
    sys_mod = _facade_attr("sys", sys)
    k32 = _facade_attr("_kernel32", _kernel32)
    os_mod = _facade_attr("os", os)
    time_mod = _facade_attr("time", time)
    if not pid or sys_mod.platform != "win32" or k32 is None:
        return 0
    terminated = 0
    last_scan_ts = 0.0
    for scan_idx in range(2):
        now = time_mod.perf_counter()
        elapsed = now - last_scan_ts
        if scan_idx > 0 or (last_scan_ts > 0.0 and elapsed < 0.025):
            time_mod.sleep(max(0.0, 0.025 - elapsed) if scan_idx == 0 else 0.025)
        last_scan_ts = time_mod.perf_counter()
        try:
            pids_to_kill = _collect_descendant_pids(k32, pid)
            for target_p in pids_to_kill:
                try:
                    os_mod.kill(target_p, 9)
                    terminated += 1
                except Exception:
                    pass
        except Exception:
            break
    return terminated


def _get_process_memory_rss(
    pid: int,
    p_process: Optional[Any] = None,
    rss_state: Optional[_RSSMonitorState] = None,
) -> int:
    """Calcola la memoria RSS totale per il processo radice e i figli con stato locale."""
    has_psutil = _facade_attr("_HAS_PSUTIL", _HAS_PSUTIL)
    sys_mod = _facade_attr("sys", sys)
    k32 = _facade_attr("_kernel32", _kernel32)
    psapi_dll = _facade_attr("_psapi", _psapi)
    time_mod = _facade_attr("time", time)

    if has_psutil and p_process is not None:
        try:
            mem = p_process.memory_info().rss
            for child in p_process.children(recursive=True):
                try:
                    mem += child.memory_info().rss
                except Exception:
                    pass
            return mem
        except Exception:
            pass

    if sys_mod.platform == "win32" and pid and k32 is not None:
        state = rss_state if rss_state is not None else _RSSMonitorState()
        try:
            with state.lock:
                now_scan = time_mod.perf_counter()
                if (
                    state.last_scan_ts > 0.0
                    and (now_scan - state.last_scan_ts) < 0.025
                    and pid in state.rss_cache
                ):
                    return state.rss_cache[pid]
                state.last_scan_ts = now_scan

            pids_to_check = _collect_descendant_pids(k32, pid)
            total_rss = 0
            for p in pids_to_check:
                h = k32.OpenProcess(
                    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                    False,
                    p,
                )
                if h and h != INVALID_HANDLE_VALUE:
                    try:
                        counters = PROCESS_MEMORY_COUNTERS()
                        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                        res = 0
                        if hasattr(k32, "K32GetProcessMemoryInfo"):
                            try:
                                res = k32.K32GetProcessMemoryInfo(
                                    ctypes.c_void_p(h),
                                    ctypes.byref(counters),
                                    counters.cb,
                                )
                            except Exception:
                                res = 0
                        if not res and psapi_dll is not None:
                            try:
                                res = psapi_dll.GetProcessMemoryInfo(
                                    ctypes.c_void_p(h),
                                    ctypes.byref(counters),
                                    counters.cb,
                                )
                            except Exception:
                                res = 0
                        if res:
                            total_rss += int(counters.WorkingSetSize)
                    finally:
                        k32.CloseHandle(ctypes.c_void_p(h))

            with state.lock:
                state.rss_cache[pid] = total_rss
            return total_rss
        except Exception:
            pass

    return 0

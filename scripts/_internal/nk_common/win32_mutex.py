# -*- coding: utf-8 -*-
"""Primitive Win32 Named Mutex fail-closed basate su ctypes.WinDLL."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Optional, Tuple, Union

WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED_0 = 0x00000080
WAIT_TIMEOUT = 0x00000102
ERROR_ACCESS_DENIED = 5
SYNCHRONIZE = 0x00100000

_KERNEL32_CACHE: Any = None


def canonical_mutex_path(target_path: Union[str, Path]) -> str:
    """Normalizza il percorso canonico in lowercase Win32 per nomi Named Mutex deterministici."""
    return os.path.realpath(str(target_path)).lower().replace("/", "\\").rstrip("\\")


def repo_path_hash(target_path: Union[str, Path], *, chars: int = 16) -> str:
    """Restituisce il prefisso hex SHA-256 del percorso canonico lowercase."""
    return hashlib.sha256(canonical_mutex_path(target_path).encode("utf-8")).hexdigest()[: max(1, int(chars))]


def repo_path_hash12(target_path: Union[str, Path]) -> str:
    """Restituisce i primi 12 caratteri esadecimali SHA-256 del percorso canonico lowercase."""
    return repo_path_hash(target_path, chars=12)


def get_named_mutex_name(
    target_path: Union[str, Path], prefix: str, *, chars: int = 12
) -> str:
    """Restituisce un nome deterministico Win32NamedMutex per percorso e prefisso."""
    return f"{prefix}_{repo_path_hash(target_path, chars=chars)}"


def get_repo_batch_mutex_name(target_path: Union[str, Path]) -> str:
    """Restituisce il nome canonico Global\\NK_RepoBatchLock_<sha16> condiviso per 2PC."""
    return get_named_mutex_name(target_path, "Global\\NK_RepoBatchLock", chars=16)


def get_tensor_active_mutex_name(root_path: Union[str, Path]) -> str:
    """Restituisce il nome mutex condiviso per nk_tracking/tensor_sessions/ACTIVE.json."""
    return get_named_mutex_name(root_path, "Local\\NK_TensorActive", chars=12)


def get_kernel32() -> Any:
    """Inizializza in modo lazy kernel32 tramite ctypes.WinDLL(..., use_last_error=True)."""
    global _KERNEL32_CACHE
    if sys.platform != "win32":
        return None
    if _KERNEL32_CACHE is not None:
        return _KERNEL32_CACHE
    import ctypes

    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    dll.CreateMutexW.restype = ctypes.c_void_p
    dll.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    dll.WaitForSingleObject.restype = ctypes.c_uint32
    dll.ReleaseMutex.argtypes = [ctypes.c_void_p]
    dll.ReleaseMutex.restype = ctypes.c_bool
    dll.CloseHandle.argtypes = [ctypes.c_void_p]
    dll.CloseHandle.restype = ctypes.c_bool
    dll.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    dll.OpenMutexW.restype = ctypes.c_void_p
    dll.GetLastError.argtypes = []
    dll.GetLastError.restype = ctypes.c_uint32
    dll.GetCurrentThreadId.argtypes = []
    dll.GetCurrentThreadId.restype = ctypes.c_uint32
    _KERNEL32_CACHE = dll
    return _KERNEL32_CACHE


def is_win32_handle_valid(handle: Optional[int]) -> bool:
    """Verifica se l'handle Win32 e valido (su non-Win32 restituisce True per fallback)."""
    if sys.platform != "win32":
        return True
    if handle is None or isinstance(handle, bool):
        return False
    try:
        return int(handle) > 0
    except (TypeError, ValueError):
        return False


def create_or_open_named_mutex(
    name: str,
    wait_ms: int = 0,
    *,
    k32: Any = None,
) -> Tuple[Optional[int], bool, Optional[str]]:
    """Crea/apre e attende un Named Mutex Win32 restituendo (handle, acquired, error)."""
    if sys.platform != "win32":
        return None, False, "non_win32"
    active_k32 = k32 if k32 is not None else get_kernel32()
    if active_k32 is None:
        return None, False, "kernel32_unavailable"

    import ctypes

    invalid_h = ctypes.c_void_p(-1).value
    mutex_name = str(name)
    handle: Any = None
    try:
        ctypes.set_last_error(0)
        handle = active_k32.CreateMutexW(None, False, mutex_name)
        err = ctypes.get_last_error()
        if (
            (not handle or handle == invalid_h)
            and err == ERROR_ACCESS_DENIED
            and mutex_name.startswith("Global\\")
        ):
            local_name = "Local\\" + mutex_name.split("\\", 1)[1]
            ctypes.set_last_error(0)
            handle = active_k32.CreateMutexW(None, False, local_name)
            err = ctypes.get_last_error()

        if not handle or handle == invalid_h:
            return None, False, f"create_mutex_failed:{err}"

        h_int = int(handle)
        if h_int <= 0:
            return None, False, "invalid_mutex_handle"

        ctypes.set_last_error(0)
        wait_rc = int(
            active_k32.WaitForSingleObject(
                ctypes.c_void_p(h_int),
                ctypes.c_uint32(max(0, int(wait_ms))),
            )
        )
        if wait_rc in (WAIT_OBJECT_0, WAIT_ABANDONED_0):
            return h_int, True, None

        wait_err = ctypes.get_last_error()
        try:
            active_k32.CloseHandle(ctypes.c_void_p(h_int))
        except Exception:
            pass
        if wait_rc == WAIT_TIMEOUT:
            return None, False, "timeout"
        return None, False, f"wait_failed:{wait_rc}:err={wait_err}"
    except Exception as exc:
        if handle and handle != invalid_h:
            try:
                active_k32.CloseHandle(ctypes.c_void_p(int(handle)))
            except Exception:
                pass
        return None, False, f"win32_mutex_error:{exc}"


def try_acquire_mutex_nonblocking(
    name: str,
    *,
    k32: Any = None,
) -> Optional[int]:
    """Tenta l'acquisizione non bloccante: handle (>0) se ok, None se busy, -1 se errore/non-Win32."""
    if sys.platform != "win32":
        return -1
    handle, acquired, err = create_or_open_named_mutex(name, wait_ms=0, k32=k32)
    if acquired and handle is not None and int(handle) > 0:
        return int(handle)
    if err == "timeout":
        return None
    return -1


def release_win32_mutex(handle: Optional[int], *, k32: Any = None) -> None:
    """Rilascia e chiude in sicurezza un handle mutex Win32 valido."""
    if sys.platform != "win32" or handle is None or isinstance(handle, bool):
        return
    try:
        h_int = int(handle)
    except (TypeError, ValueError):
        return
    if h_int <= 0:
        return
    active_k32 = k32 if k32 is not None else get_kernel32()
    if active_k32 is None:
        return
    try:
        import ctypes

        h_ptr = ctypes.c_void_p(h_int)
        active_k32.ReleaseMutex(h_ptr)
        active_k32.CloseHandle(h_ptr)
    except Exception:
        pass

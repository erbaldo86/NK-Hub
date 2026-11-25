#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Costanti condivise, profili e helper primitivi per nk_session_bootstrap."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, List, Optional

from ..nk_common import paths as _nk_paths
from ..nk_common.constants import (
    HIGH_CAPACITY_PROFILES,
    ONBOARDING_TRIGGERS,
    SUPPORTED_MODEL_PROFILES,
)
from ..nk_common.facade_boot import resolve_facade_attr
from ..nk_common.transcript_guards import valid_token_int
from ..nk_common.win32_mutex import get_repo_batch_mutex_name


def _resolve_scripts_dir() -> Path:
    """Risale gli antenati fino alla directory canonicale scripts."""
    return Path(_nk_paths.resolve_scripts_dir(__file__))


os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

_scripts_dir: Path = _resolve_scripts_dir()
_workspace_root: Path = Path(_nk_paths.resolve_workspace_root(__file__))

_staging_scripts_dir: Path = _workspace_root / ".staging" / "scripts"
for _p in (_staging_scripts_dir, _scripts_dir, _workspace_root):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def reconfigure_streams() -> None:
    """Riconfigura gli stream standard in UTF-8 senza importare moduli esterni su cold start."""
    _nk_paths.reconfigure_streams()


NKContextSentry: Any = None

FAST_CACHE_TTL_SECONDS: float = 900.0
STATE_CACHE_TTL_SECONDS: float = 900.0
TRANSCRIPT_MAX_AGE_SECONDS: float = 1800.0
TAIL_READ_BYTES_LIMIT: int = 32768
BINARY_CHUNK_SIZE: int = 65536
MAX_EXACT_COUNT_BYTES: int = 50 * 1024 * 1024
_BOOTSTRAP_LOCK = threading.Lock()

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED_0 = 0x00000080
_ERROR_ACCESS_DENIED = 5
_INVALID_HANDLE_VALUE: Any = -1
HUB_ROOT: Path = _workspace_root.resolve()
_k32: Any = None
_k32_initialized: bool = False

_UNTRUSTED_COMPACTION_SOURCES: tuple[str, ...] = (
    "USER",
    "USER_EXPLICIT",
    "USER_INPUT",
    "MODEL",
    "ASSISTANT",
    "TOOL",
    "TOOL_RESULT",
    "TOOL_OUTPUT",
    "SYSTEM_SDK",
)
_UNTRUSTED_COMPACTION_TYPES: tuple[str, ...] = (
    "PLANNER_RESPONSE",
    "MODEL_RESPONSE",
    "GENERIC",
    "TOOL_RESPONSE",
    "TOOL_RESULT",
    "USER_INPUT",
)

_FACADE_MODULES: List[Any] = []


def _register_facade_module(mod: Any) -> None:
    """Registra dinamicamente il modulo facade per preservare compatibilita monkeypatch."""
    if mod is not None and mod not in _FACADE_MODULES:
        _FACADE_MODULES.append(mod)


def _get_facade_attr(name: str, default: Any = None) -> Any:
    """Risolve un attributo sul modulo facade registrato delegando a resolve_facade_attr."""
    mod_names = [
        getattr(mod, "__name__", "")
        for mod in reversed(_FACADE_MODULES)
        if getattr(mod, "__name__", "")
    ]
    for fallback in ("scripts.nk_session_bootstrap", "nk_session_bootstrap"):
        if fallback not in mod_names:
            mod_names.append(fallback)
    return resolve_facade_attr(mod_names, name, default)


def _get_win32_k32() -> Any:
    """Inizializza in modo lazy kernel32.dll solo quando occorre acquisire il mutex 2PC."""
    global _k32, _k32_initialized, _INVALID_HANDLE_VALUE
    for mod in reversed(_FACADE_MODULES):
        fk = getattr(mod, "_k32", None)
        if fk is not None and fk is not _k32:
            return fk
    if _k32_initialized:
        return _k32
    _k32_initialized = True
    if sys.platform == "win32":
        import ctypes

        _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        dll.CreateMutexW.restype = ctypes.c_void_p
        dll.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        dll.WaitForSingleObject.restype = ctypes.c_uint32
        dll.ReleaseMutex.argtypes = [ctypes.c_void_p]
        dll.ReleaseMutex.restype = ctypes.c_bool
        dll.CloseHandle.argtypes = [ctypes.c_void_p]
        dll.CloseHandle.restype = ctypes.c_bool
        _k32 = dll
    for mod in _FACADE_MODULES:
        if hasattr(mod, "_k32"):
            setattr(mod, "_k32", _k32)
        if hasattr(mod, "_k32_initialized"):
            setattr(mod, "_k32_initialized", True)
        if hasattr(mod, "_INVALID_HANDLE_VALUE"):
            setattr(mod, "_INVALID_HANDLE_VALUE", _INVALID_HANDLE_VALUE)
    return _k32


def get_canonical_repo_batch_mutex_name(root: Path) -> str:
    """Calcola il nome canonico Global\\NK_RepoBatchLock_<sha256[:16]> delegando a win32_mutex."""
    return get_repo_batch_mutex_name(root)


def _parse_iso_epoch(ts_val: Any) -> float:
    """Converte un timestamp ISO-8601 o numerico in secondi epoch UTC."""
    if isinstance(ts_val, (int, float)) and not isinstance(ts_val, bool):
        return float(ts_val)
    if isinstance(ts_val, str) and ts_val.strip():
        try:
            from datetime import datetime

            return datetime.fromisoformat(
                ts_val.strip().replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            return 0.0
    return 0.0


def _valid_token_int(val: Any) -> Optional[int]:
    """Delega la convalida token interi non negativi a nk_common.transcript_guards."""
    return valid_token_int(val)

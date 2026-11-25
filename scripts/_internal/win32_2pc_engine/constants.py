#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Costanti Win32, eccezioni, lazy IPC contracts e risolutori mutex/hash."""

from __future__ import annotations

import ctypes
import hashlib
import re
import sys
import threading
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.paths import resolve_scripts_dir

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None

_UNSET: Any = object()
IPCPointerReturn: Any = _UNSET
TwoPhaseCommitPrepare: Any = _UNSET
TwoPhaseCommitVerdict: Any = _UNSET
_IPC_LOAD_LOCK = threading.Lock()
_FACADE_MODULES: List[Any] = []


def _resolve_scripts_dir() -> Path:
    """Risale gli antenati fino alla directory canonicale scripts tramite nk_common.paths."""
    return Path(resolve_scripts_dir(__file__))


def _register_facade_module(mod: Any) -> None:
    """Registra dinamicamente il modulo facade per preservare compatibilita monkeypatch."""
    if mod is not None and mod not in _FACADE_MODULES:
        _FACADE_MODULES.append(mod)


def _get_facade_attr(name: str, default: Any = None) -> Any:
    """Risolve un attributo sul modulo facade registrato o tramite resolve_facade_attr."""
    for mod in reversed(_FACADE_MODULES):
        if mod is not None and hasattr(mod, name):
            return getattr(mod, name)
    return resolve_facade_attr(("scripts.win32_2pc_engine", "win32_2pc_engine"), name, default)


def _ensure_ipc_contracts_loaded() -> None:
    """Carica pigramente i contratti Pydantic da schemas.nk_ipc_contracts."""
    global IPCPointerReturn, TwoPhaseCommitPrepare, TwoPhaseCommitVerdict
    if (
        IPCPointerReturn is not _UNSET
        and TwoPhaseCommitPrepare is not _UNSET
        and TwoPhaseCommitVerdict is not _UNSET
    ):
        return
    with _IPC_LOAD_LOCK:
        if (
            IPCPointerReturn is not _UNSET
            and TwoPhaseCommitPrepare is not _UNSET
            and TwoPhaseCommitVerdict is not _UNSET
        ):
            return
        try:
            from schemas.nk_ipc_contracts import (
                IPCPointerReturn as _ipc_ptr,
                TwoPhaseCommitPrepare as _tpc_prep,
                TwoPhaseCommitVerdict as _tpc_verd,
            )
        except (ImportError, ModuleNotFoundError):
            scripts_dir = _resolve_scripts_dir()
            repo_parent = scripts_dir.parent
            root_scripts = (
                repo_parent.parent / "scripts"
                if repo_parent.name == ".staging"
                else scripts_dir
            )
            candidates = [
                scripts_dir,
                repo_parent,
                root_scripts,
                Path.cwd(),
                Path.cwd() / "scripts",
            ]
            for c in candidates:
                if str(c) not in sys.path and c.exists():
                    sys.path.insert(0, str(c))
            try:
                from schemas.nk_ipc_contracts import (
                    IPCPointerReturn as _ipc_ptr,
                    TwoPhaseCommitPrepare as _tpc_prep,
                    TwoPhaseCommitVerdict as _tpc_verd,
                )
            except (ImportError, ModuleNotFoundError):
                from scripts.schemas.nk_ipc_contracts import (
                    IPCPointerReturn as _ipc_ptr,
                    TwoPhaseCommitPrepare as _tpc_prep,
                    TwoPhaseCommitVerdict as _tpc_verd,
                )
        if IPCPointerReturn is _UNSET:
            IPCPointerReturn = _ipc_ptr
        if TwoPhaseCommitPrepare is _UNSET:
            TwoPhaseCommitPrepare = _tpc_prep
        if TwoPhaseCommitVerdict is _UNSET:
            TwoPhaseCommitVerdict = _tpc_verd
        for mod in _FACADE_MODULES:
            if hasattr(mod, "IPCPointerReturn"):
                setattr(mod, "IPCPointerReturn", IPCPointerReturn)
            if hasattr(mod, "TwoPhaseCommitPrepare"):
                setattr(mod, "TwoPhaseCommitPrepare", TwoPhaseCommitPrepare)
            if hasattr(mod, "TwoPhaseCommitVerdict"):
                setattr(mod, "TwoPhaseCommitVerdict", TwoPhaseCommitVerdict)


WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED_0 = 0x00000080
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

MOVEFILE_REPLACE_EXISTING = 0x00000001
MOVEFILE_COPY_ALLOWED = 0x00000002
MOVEFILE_WRITE_THROUGH = 0x00000008

INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33

RETRY_ATTEMPTS_IO = 5
RETRY_DELAY_SEC_IO = 0.025
IGNORED_STAGING_SUFFIXES: Tuple[str, ...] = (".pyc", ".pyo", ".tmp", ".bak")
_PATCH_NOTES_HEADER_RE = re.compile(r"^\s*##\s+`?\[[^\]]+\].*$", re.MULTILINE)
from _internal.nk_common.constants import NK_LOCK_FILENAMES

_LOCK_DENY_ENTRIES: Tuple[str, ...] = tuple(
    item
    for name in NK_LOCK_FILENAMES
    for item in (f"nk_tracking/{name.lower()}", name.lower())
)
_LOCK_BASES: Tuple[str, ...] = tuple(name.lower() for name in NK_LOCK_FILENAMES)
PROTECTED_GOVERNANCE_DENYLIST: Tuple[str, ...] = _LOCK_DENY_ENTRIES + (
    "nk_tracking/quality_baseline.json",
    "quality_baseline.json",
    "nk_tracking/tensor_sessions/active.json",
    "nk_tracking/tensor_sessions",
    "active.json",
    ".deleted_files.json",
    "tests",
    "tests/evals/skill_golden_eval_set.json",
    "scripts/win32_2pc_engine.py",
    "scripts/nk_hook_gate.py",
    "scripts/ast_guard_validator.py",
    "scripts/rsi_convergence_engine.py",
    "scripts/tensor_rsi.py",
)
PROTECTED_GOVERNANCE_PREFIXES: Tuple[str, ...] = (
    "nk_tracking/oracle_holdout/",
    "nk_tracking/benchmark_suite/",
    "nk_tracking/tensor_sessions/",
    "tests/",
    "scripts/_internal/win32_2pc_engine/",
    "scripts/_internal/nk_hook_gate/",
    "scripts/_internal/ast_guard_validator/",
    "scripts/_internal/rsi_convergence_engine/",
    "scripts/_internal/tensor_rsi/",
    "nk_genome/configs/tensor_rsi/",
)


def _normalize_rel_gov_path(rel_norm: str) -> str:
    """Normalizza separatori e prefissi './' preservando i file dotfile (es. .deleted_files.json)."""
    norm = str(rel_norm).replace("\\", "/").strip().lower()
    while norm.startswith("./"):
        norm = norm[2:]
    return norm.lstrip("/")


def is_protected_governance_path(rel_norm: str) -> bool:
    """Verifica se un percorso relativo appartiene a file o directory di governance protetti."""
    norm = _normalize_rel_gov_path(rel_norm)
    base = Path(norm).name
    return (
        norm in PROTECTED_GOVERNANCE_DENYLIST
        or norm.startswith(PROTECTED_GOVERNANCE_PREFIXES)
        or base in (*_LOCK_BASES, "active.json", ".deleted_files.json")
    )


if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_bool,
        ctypes.c_wchar_p,
    ]
    _kernel32.CreateMutexW.restype = ctypes.c_void_p

    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.WaitForSingleObject.restype = ctypes.c_uint32

    _kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    _kernel32.ReleaseMutex.restype = ctypes.c_bool

    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_bool

    _kernel32.MoveFileExW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    _kernel32.MoveFileExW.restype = ctypes.c_bool

    _kernel32.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    _kernel32.GetFileAttributesW.restype = ctypes.c_uint32

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32

    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = ctypes.c_uint32
else:
    _kernel32 = None

_POSIX_HELD_LOCKS = threading.local()


def _get_active_kernel32() -> Any:
    """Risolve dinamicamente _kernel32 supportando monkeypatch su qualsiasi modulo facade."""
    for mod in reversed(_FACADE_MODULES):
        if mod is not None and hasattr(mod, "_kernel32"):
            val = getattr(mod, "_kernel32")
            if val is not _kernel32:
                return val
    for mod_name in ("scripts.win32_2pc_engine", "win32_2pc_engine"):
        m = sys.modules.get(mod_name)
        if m is not None and hasattr(m, "_kernel32"):
            val = getattr(m, "_kernel32")
            if val is not _kernel32:
                return val
    return _kernel32


def _get_win32_last_error() -> int:
    """Recupera l'ultimo codice di errore Win32 thread-local."""
    k32 = _get_active_kernel32()
    if k32 is None:
        return 0
    err = ctypes.get_last_error()
    if err:
        return int(err) & 0xFFFFFFFF
    return int(k32.GetLastError()) & 0xFFFFFFFF


class Win32LockError(RuntimeError):
    """Sollevata quando il mutex Win32 incontra un errore di sistema."""


class Win32LockTimeoutError(TimeoutError):
    """Sollevata quando l'acquisizione del mutex Win32 supera il timeout."""


class TwoPhaseCommitError(RuntimeError):
    """Sollevata quando il commit atomico 2PC fallisce i controlli di integrita."""


def validate_override_reason(reason: Optional[str], context_path: str) -> str:
    """Richiede una motivazione non vuota (>= 8 char) per ogni override di governance."""
    if not isinstance(reason, str) or len(reason.strip()) < 8:
        raise TwoPhaseCommitError(
            f"Override di governance bloccato per {context_path}: "
            "richiesto --override-reason (>= 8 caratteri)."
        )
    return reason.strip()


def compute_sha256(data: Union[bytes, str]) -> str:
    """Calcola il digest esadecimale SHA-256 deterministico."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def compute_crc32(data: Union[bytes, str]) -> int:
    """Calcola il checksum CRC32 senza segno a 32 bit."""
    import zlib

    raw = data.encode("utf-8") if isinstance(data, str) else data
    return zlib.crc32(raw) & 0xFFFFFFFF

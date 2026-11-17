# -*- coding: utf-8 -*-
"""Costanti, modelli Pydantic, mutex Win32 e rotazione backup per memory_3tier_engine."""

from __future__ import annotations

import contextlib
import hashlib
import os
import random
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from _internal.nk_common.constants import HIGH_CAPACITY_PROFILES, VERSION
from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.transcript_guards import (
    estimate_tokens as _shared_estimate_tokens,
)

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_workspace_root = (
    _scripts_dir.parent.parent if _scripts_dir.parent.name == ".staging" else _scripts_dir.parent
)

_FACADE_MOD_NAMES: Tuple[str, ...] = ("memory_3tier_engine", "scripts.memory_3tier_engine")
_MEMORY_THREAD_LOCK = threading.RLock()
_UNSET: Any = object()
_Win32NamedMutex: Any = _UNSET
_win32_2pc_atomic_replace: Any = _UNSET
_kernel32: Any = _UNSET

NK_DOMAINS: Tuple[str, ...] = (
    "01_Bug_Diagnostics",
    "02_Development_Patterns",
    "03_Ideation_and_Decisions",
    "04_Governance_and_Rules",
)

DOMAIN_ALIAS_MAP: Dict[str, str] = {
    "OPS": "01_Bug_Diagnostics",
    "ARCH": "02_Development_Patterns",
    "DEVX": "03_Ideation_and_Decisions",
    "SEC": "04_Governance_and_Rules",
    "01_Bug_Diagnostics": "01_Bug_Diagnostics",
    "02_Development_Patterns": "02_Development_Patterns",
    "03_Ideation_and_Decisions": "03_Ideation_and_Decisions",
    "04_Governance_and_Rules": "04_Governance_and_Rules",
}

MEMORY_SCHEMA_VERSION: str = VERSION
TIER1_TOKEN_CAP: int = 350
TIER1_TOKEN_CAP_ARGON: int = 1200
TIER1_TOKEN_CAP_CARBON: int = 1200
TIER1_TOKEN_CAP_GENERATION: int = 1200
TIER2_SLIDING_WINDOW_MAX: int = 200
RRF_K_CONSTANT: float = 60.0
BACKUP_DEPTH: int = 2
MAX_BACKUP_DEPTH: int = BACKUP_DEPTH

MOVEFILE_REPLACE_EXISTING = 0x00000001
MOVEFILE_WRITE_THROUGH = 0x00000008
MOVEFILE_COPY_ALLOWED = 0x00000002

ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33


def _iter_facades() -> List[Any]:
    """Restituisce tutte le istanze attive della facciata memory_3tier_engine in sys.modules."""
    found: List[Any] = []
    seen_ids: set[int] = set()
    for mod_key in _FACADE_MOD_NAMES:
        fac = sys.modules.get(mod_key)
        if fac is not None and id(fac) not in seen_ids:
            seen_ids.add(id(fac))
            found.append(fac)
    for fac in tuple(sys.modules.values()):
        if fac is not None and id(fac) not in seen_ids and getattr(fac, "__nk_facade__", None) == "memory_3tier_engine":
            seen_ids.add(id(fac))
            found.append(fac)
    return found


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


def _sync_facade_attr(attr_name: str, value: Any) -> None:
    """Propaga il valore caricato pigramente verso le facciate con valore _UNSET."""
    for fac in _iter_facades():
        cur = _UNSET
        for key, val in vars(fac).copy().items():
            if key == attr_name:
                cur = val
                break
        if cur is _UNSET:
            setattr(fac, attr_name, value)


def _ensure_win32_2pc_loaded() -> None:
    """Carica pigramente win32_2pc_engine preservando eventuali override a None."""
    global _Win32NamedMutex, _win32_2pc_atomic_replace
    if _facade_attr("_Win32NamedMutex", _Win32NamedMutex) is not _UNSET and _facade_attr(
        "_win32_2pc_atomic_replace", _win32_2pc_atomic_replace
    ) is not _UNSET:
        return
    with _MEMORY_THREAD_LOCK:
        cur_mx = _facade_attr("_Win32NamedMutex", _Win32NamedMutex)
        cur_rp = _facade_attr("_win32_2pc_atomic_replace", _win32_2pc_atomic_replace)
        if cur_mx is not _UNSET and cur_rp is not _UNSET:
            return
        mod_mutex: Any = None
        mod_replace: Any = None
        try:
            from win32_2pc_engine import Win32NamedMutex as mod_mutex, win32_atomic_replace as mod_replace
        except ImportError:
            try:
                from scripts.win32_2pc_engine import Win32NamedMutex as mod_mutex, win32_atomic_replace as mod_replace
            except ImportError:
                mod_mutex, mod_replace = None, None
        if _scripts_dir.parent.name == ".staging" and (_scripts_dir / "_internal").is_dir():
            import importlib as _il
            _int_pkg = _il.import_module("_internal")
            _stg_int_root = _scripts_dir / "_internal"
            if hasattr(_int_pkg, "__path__") and str(_stg_int_root) not in _int_pkg.__path__:
                _int_pkg.__path__.insert(0, str(_stg_int_root))
            for _sub_d in _stg_int_root.iterdir():
                if _sub_d.is_dir() and _sub_d.name != "__pycache__":
                    try:
                        _sp = _il.import_module(f"_internal.{_sub_d.name}")
                        if hasattr(_sp, "__path__") and str(_sub_d) not in _sp.__path__:
                            _sp.__path__.insert(0, str(_sub_d))
                    except ImportError:
                        pass
        if cur_mx is _UNSET:
            _Win32NamedMutex = mod_mutex
            _sync_facade_attr("_Win32NamedMutex", mod_mutex)
        if cur_rp is _UNSET:
            _win32_2pc_atomic_replace = mod_replace
            _sync_facade_attr("_win32_2pc_atomic_replace", mod_replace)


def _acquire_memory_file_mutex(target_file: Path) -> Any:
    """Acquisisce il mutex Win32 nominato sul file target se disponibile."""
    _ensure_win32_2pc_loaded()
    mx_cls = _facade_attr("_Win32NamedMutex", _Win32NamedMutex)
    if mx_cls is not None and mx_cls is not _UNSET:
        return mx_cls(target_file, timeout_ms=10000)
    return contextlib.nullcontext()


def _get_kernel32() -> Any:
    """Carica pigramente kernel32.dll con WinDLL(use_last_error=True) su Windows."""
    global _kernel32
    cur_k32 = _facade_attr("_kernel32", _kernel32)
    if cur_k32 is not _UNSET:
        return cur_k32
    os_mod = _facade_attr("os", os)
    with _MEMORY_THREAD_LOCK:
        cur_k32 = _facade_attr("_kernel32", _kernel32)
        if cur_k32 is not _UNSET:
            return cur_k32
        if os_mod.name == "nt":
            import ctypes

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
            k32.MoveFileExW.restype = ctypes.c_bool
            k32.GetLastError.argtypes = []
            k32.GetLastError.restype = ctypes.c_uint32
            _kernel32 = k32
        else:
            _kernel32 = None
        _sync_facade_attr("_kernel32", _kernel32)
    return _kernel32


def resolve_domain(domain: str) -> str:
    """Risolve un alias breve o un nome completo nel dominio canonico NK."""
    cleaned = domain.strip()
    if cleaned in DOMAIN_ALIAS_MAP:
        return DOMAIN_ALIAS_MAP[cleaned]
    if cleaned.upper() in DOMAIN_ALIAS_MAP:
        return DOMAIN_ALIAS_MAP[cleaned.upper()]
    raise ValueError(f"Invalid or unknown domain: {domain}")


def win32_atomic_replace(src_path: Path, dst_path: Path, max_retries: int = 8) -> None:
    """Sostituisce un file in modo atomico usando win32_2pc_engine o fallback locale."""
    _ensure_win32_2pc_loaded()
    rep_fn = _facade_attr("_win32_2pc_atomic_replace", _win32_2pc_atomic_replace)
    if rep_fn is not None and rep_fn is not _UNSET:
        rep_fn(src_path, dst_path, max_retries=max_retries)
        return
    src_str, dst_str = str(src_path.resolve()), str(dst_path.resolve())
    os_mod, time_mod = _facade_attr("os", os), _facade_attr("time", time)

    k32 = _get_kernel32() if os_mod.name == "nt" else None
    if os_mod.name == "nt" and k32 is not None:
        import ctypes

        flags = MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH | MOVEFILE_COPY_ALLOWED
        for attempt in range(max_retries):
            if k32.MoveFileExW(src_str, dst_str, flags):
                return
            err = (ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0) or k32.GetLastError()
            if err in (ERROR_SHARING_VIOLATION, ERROR_ACCESS_DENIED, ERROR_LOCK_VIOLATION):
                time_mod.sleep(random.uniform(0.010, min(0.080 * (1.6 ** attempt), 1.500)))
            else:
                try:
                    os_mod.replace(src_str, dst_str)
                    return
                except (PermissionError, OSError):
                    time_mod.sleep(random.uniform(0.010, min(0.080 * (1.6 ** attempt), 1.500)))

        ts_tag = f"{os_mod.getpid()}_{int(time_mod.time() * 1000)}.tmp"
        shadow_tmp = dst_path.parent / f".shadow_{dst_path.name}_{ts_tag}"
        old_tmp = dst_path.parent / f".old_{dst_path.name}_{ts_tag}"
        for _ in range(max_retries):
            try:
                shutil.copy2(src_path, shadow_tmp)
                if dst_path.exists():
                    try:
                        os_mod.replace(dst_str, str(old_tmp))
                    except OSError:
                        pass
                os_mod.replace(str(shadow_tmp), dst_str)
                for stale_p in (old_tmp, src_path):
                    try:
                        stale_p.unlink(missing_ok=True)
                    except OSError:
                        pass
                return
            except Exception:
                time_mod.sleep(random.uniform(0.010, 0.080))

    os_mod.replace(src_str, dst_str)


def _resolve_external_backup_dir(target_path: Path) -> Optional[Path]:
    """Risolve la cartella di backup esterna per nk_tracking isolando i workspace di test."""
    resolved = target_path.resolve()
    if "nk_tracking" not in [p.lower() for p in resolved.parts]:
        return None
    env_bkp = os.environ.get("NK_MEMORY_BACKUP_DIR", "").strip()
    if env_bkp:
        return Path(env_bkp) / resolved.parent.name
    base_root = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "nk_backups" / "memory_3tier"
    ws_root = Path(_facade_attr("_workspace_root", _workspace_root))
    prod_tracking = (ws_root / "nk_tracking").resolve()
    if prod_tracking == resolved or prod_tracking in resolved.parents:
        return base_root / resolved.parent.name
    ws_ns = hashlib.sha256(str(resolved.parent.parent).lower().encode("utf-8")).hexdigest()[:12]
    return base_root / f"ws_{ws_ns}" / resolved.parent.name


def rotate_circular_backups(
    target_file: Path,
    depth: int = MAX_BACKUP_DEPTH,
    backup_dir: Optional[Path] = None,
) -> None:
    """Ruota i file di backup circolari (.bak_1, .bak_2) con copia streaming."""
    target_file = Path(target_file)
    if not target_file.exists() or target_file.stat().st_size == 0:
        return

    resolved_bkp_dir: Optional[Path] = None
    if backup_dir is not None:
        resolved_bkp_dir = Path(backup_dir)
        resolved_bkp_dir.mkdir(parents=True, exist_ok=True)
    else:
        ext_bkp = _resolve_external_backup_dir(target_file)
        if ext_bkp is not None:
            ext_bkp.mkdir(parents=True, exist_ok=True)
            resolved_bkp_dir = ext_bkp

    def _bak_file(idx: int) -> Path:
        if resolved_bkp_dir is not None:
            return resolved_bkp_dir / f"{target_file.name}.bak_{idx}"
        return target_file.with_name(f"{target_file.name}.bak_{idx}")

    for i in range(depth, 1, -1):
        prev_bak, curr_bak = _bak_file(i - 1), _bak_file(i)
        if prev_bak.exists():
            if curr_bak.exists():
                curr_bak.unlink()
            prev_bak.rename(curr_bak)

    first_bak = _bak_file(1)
    if first_bak.exists():
        first_bak.unlink()
    shutil.copy2(target_file, first_bak)


def estimate_tokens(text: str) -> int:
    """Stima rapida dei token lessicali tramite nk_common.transcript_guards."""
    return _shared_estimate_tokens(text)


class MemoryEpisode(BaseModel):
    """Singolo episodio archiviato nel motore di memoria a 3 livelli."""

    model_config = ConfigDict(strict=True, extra="forbid")
    episode_id: str = Field(description="Identificatore univoco dell'episodio")
    domain: str = Field(description="Uno dei 4 domini NK o alias breve")
    timestamp: float = Field(default_factory=time.time)
    title: str = Field(description="Titolo sintetico dell'episodio")
    content: str = Field(description="Contenuto completo dell'episodio")
    tags: List[str] = Field(default_factory=list)
    vector: Optional[List[float]] = Field(default=None)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)


class Tier1Item(BaseModel):
    """Voce singola nella memoria in-context di Livello 1."""

    model_config = ConfigDict(strict=True, extra="forbid")
    key: str
    value: str
    priority: int = Field(default=1, ge=1, le=10)
    estimated_tokens: int = Field(default=0)


class Tier1DomainState(BaseModel):
    """Stato della memoria di Livello 1 per un singolo dominio."""

    model_config = ConfigDict(strict=True, extra="forbid")
    domain: str
    items: Dict[str, Tier1Item] = Field(default_factory=dict)
    total_tokens: int = Field(default=0)

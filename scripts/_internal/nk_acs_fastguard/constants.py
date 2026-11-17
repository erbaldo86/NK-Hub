"""Costanti, I/O sicuro stdin/lstat/Win32 e caricamento soglie ACS (pure stdlib)."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.facade_boot import resolve_facade_attr

_HERE = os.path.dirname(os.path.abspath(__file__))
_INTERNAL_DIR = os.path.dirname(_HERE)
_SCRIPTS_DIR_PHYS = os.path.dirname(_INTERNAL_DIR)
_PARENT_DIR = os.path.dirname(_SCRIPTS_DIR_PHYS)
_WORKSPACE_ROOT = (
    os.path.dirname(_PARENT_DIR)
    if os.path.basename(_PARENT_DIR) == ".staging"
    else _PARENT_DIR
)
_SCRIPT_DIR = _SCRIPTS_DIR_PHYS

_FACADE_MOD_NAMES: List[str] = ["nk_acs_fastguard", "scripts.nk_acs_fastguard"]

_CONV_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_RETRY_WINERRORS = frozenset((5, 32, 33))
_CHUNK_SIZE = 65536
_MAX_BACKSCAN_BYTES = 50 * 1024 * 1024
_Z2_COOLDOWN_SEC = 60.0
_SMALL_FILE_THRESHOLD = 524288
_WAL_ACTIVE_AGE_SEC = 120.0

_Z1_TOKENS, _Z1_STEPS = 160_000, 120
_Z2_TOKENS, _Z2_STEPS = 185_000, 150
_Z3_TOKENS, _Z3_STEPS = 205_000, 180
_VEL_DELTA, _VEL_CUR, _VEL_STEPS = 25_000, 140_000, 100
_DEFAULT_EPOCH_BASELINE_TOKENS = 0
_DEFAULT_FALLBACK_STEPS = {"z1": 120, "z2": 150, "z3": 180}

_SPOOF_SOURCES = frozenset(("USER", "USER_EXPLICIT", "MODEL", "ASSISTANT", "TOOL", "GENERIC"))
_SPOOF_TYPES = frozenset(("USER_INPUT", "PLANNER_RESPONSE", "TOOL_RESULT", "TOOL_OUTPUT", "GENERIC"))
_SPOOF_ROLES = frozenset(("user", "model", "assistant", "tool"))

_SYNCHRONIZE = 0x00100000
_ERROR_ACCESS_DENIED = 5
_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_FILE_TYPE_PIPE = 3
_SUBPROCESS_DETACHED = 0x00000008 | 0x08000000 | 0x00000200

_K32_CACHE: Any = None
_CTYPES_MOD: Any = None
_ACS_PARSED_JSON_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def register_facade_module(mod_name: str) -> None:
    """Registra il nome modulo della facciata per risolvere eventuali monkeypatch di test."""
    if mod_name and mod_name not in _FACADE_MOD_NAMES:
        _FACADE_MOD_NAMES.insert(0, mod_name)


def _fg_attr(name: str, default: Any) -> Any:
    """Risolve eventuali override monkeypatch applicati sulla facciata nk_acs_fastguard."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, name, default)


def _get_k32() -> Tuple[Any, Any]:
    """Carica kernel32 via ctypes.WinDLL su domanda evitando import a freddo."""
    global _K32_CACHE, _CTYPES_MOD
    if sys.platform != "win32":
        return None, None
    if _K32_CACHE is not None and _CTYPES_MOD is not None:
        return _CTYPES_MOD, _K32_CACHE
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    k32.OpenMutexW.restype = ctypes.c_void_p
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = ctypes.c_int
    k32.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    k32.GetFileAttributesW.restype = ctypes.c_uint32
    k32.GetFileType.argtypes = [ctypes.c_void_p]
    k32.GetFileType.restype = ctypes.c_uint32
    k32.PeekNamedPipe.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    k32.PeekNamedPipe.restype = ctypes.c_int
    _CTYPES_MOD = ctypes
    _K32_CACHE = k32
    return ctypes, k32


def _reconfigure_streams() -> None:
    """Imposta UTF-8 su stdin, stdout e stderr in modo sicuro."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _warn_stderr(tag: str, detail: str) -> None:
    """Emette un avviso diagnostico su una riga in stderr senza alterare stdout JSON."""
    clean_detail = str(detail).replace("\r", " ").replace("\n", " ")
    try:
        sys.stderr.write(f"[ACS-FASTGUARD WARN] {tag} {clean_detail}\n")
    except Exception:
        pass


def _win32_stdin_ready(fd: int) -> bool:
    """Verifica con PeekNamedPipe che fd Win32 abbia dati senza attese su EOF o errori."""
    import msvcrt

    handle = msvcrt.get_osfhandle(fd)
    if handle in (-1, -2):
        return False
    ctypes_mod, k32 = _fg_attr("_get_k32", _get_k32)()
    if ctypes_mod is None or k32 is None:
        return True
    ctypes_mod.set_last_error(0)
    file_type = k32.GetFileType(ctypes_mod.c_void_p(handle))
    if file_type == 0 and ctypes_mod.get_last_error() != 0:
        return False
    if file_type != _FILE_TYPE_PIPE:
        return True
    avail = ctypes_mod.c_uint32(0)
    h_ptr = ctypes_mod.c_void_p(handle)
    for attempt in range(6):
        ok = k32.PeekNamedPipe(h_ptr, None, 0, None, ctypes_mod.byref(avail), None)
        if not ok:
            return False
        if avail.value > 0:
            return True
        if attempt < 5:
            time.sleep(0.003)
    return False


def _read_stdin_safe() -> str:
    """Legge stdin evitando blocchi su tty, handle chiusi o pipe vuote."""
    if sys.stdin is None:
        return ""
    try:
        if sys.stdin.isatty():
            return ""
    except Exception:
        pass
    if sys.platform == "win32" and hasattr(sys.stdin, "fileno"):
        try:
            fd = sys.stdin.fileno()
            ready_fn = _fg_attr("_win32_stdin_ready", _win32_stdin_ready)
            if not ready_fn(fd):
                return ""
        except Exception:
            pass
    elif hasattr(sys.stdin, "fileno"):
        try:
            fd = sys.stdin.fileno()
            if stat.S_ISFIFO(os.fstat(fd).st_mode):
                import select

                readable, _, _ = select.select([fd], [], [], 0.018)
                if not readable:
                    return ""
        except Exception:
            pass
    try:
        return sys.stdin.read()
    except OSError:
        return ""


def _is_reparse_or_symlink(path_obj: Any) -> bool:
    """Rileva symlink o Win32 junction/reparse point in una singola syscall os.lstat."""
    p = os.fspath(path_obj)
    reparse_mask = int(_fg_attr("_FILE_ATTRIBUTE_REPARSE_POINT", _FILE_ATTRIBUTE_REPARSE_POINT))
    try:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            return True
        if (getattr(st, "st_file_attributes", 0) & reparse_mask) != 0:
            return True
        return False
    except FileNotFoundError:
        return False
    except OSError:
        if sys.platform != "win32":
            return False
        _, k32 = _fg_attr("_get_k32", _get_k32)()
        if k32 is not None:
            try:
                attrs = k32.GetFileAttributesW(p)
                if attrs != _INVALID_FILE_ATTRIBUTES and (attrs & reparse_mask) != 0:
                    return True
            except Exception:
                pass
        return False


def _is_safe_dir(path_str: str) -> bool:
    """Verifica directory esistente priva di symlink/reparse con una singola os.lstat."""
    try:
        st = os.lstat(path_str)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode) or (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) != 0:
        return False
    return stat.S_ISDIR(st.st_mode)


def _stat_safe_file(path_str: str) -> Optional[Tuple[int, int]]:
    """Restituisce (mtime_ns, size) se file regolare sicuro, altrimenti None in una os.lstat."""
    try:
        st = os.lstat(path_str)
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) != 0:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return st.st_mtime_ns, st.st_size


def _is_safe_file(path_str: str) -> Optional[int]:
    """Restituisce size in byte se file regolare sicuro, altrimenti None in una os.lstat."""
    st_meta = _stat_safe_file(path_str)
    return st_meta[1] if st_meta is not None else None


def _safe_int_val(val: Any, default: int, min_val: int = 1) -> int:
    """Restituisce val se intero valido >= min_val escludendo bool, altrimenti default."""
    if isinstance(val, int) and not isinstance(val, bool) and val >= min_val:
        return val
    return default


def _load_acs_thresholds(roots: List[str]) -> Dict[str, Any]:
    """Carica le soglie ACS da saturation_thresholds.json via stdlib json in modo -S safe."""
    cfg: Dict[str, Any] = {
        "z1_tokens": _Z1_TOKENS,
        "z1_steps": _Z1_STEPS,
        "z2_tokens": _Z2_TOKENS,
        "z2_steps": _Z2_STEPS,
        "z3_tokens": _Z3_TOKENS,
        "z3_steps": _Z3_STEPS,
        "vel_delta": _VEL_DELTA,
        "vel_cur": _VEL_CUR,
        "vel_steps": _VEL_STEPS,
        "cooldown_s": _Z2_COOLDOWN_SEC,
        "epoch_baseline_tokens": _DEFAULT_EPOCH_BASELINE_TOKENS,
        "fallback_steps": dict(_DEFAULT_FALLBACK_STEPS),
    }
    ws_root = str(_fg_attr("_WORKSPACE_ROOT", _WORKSPACE_ROOT))
    search_roots: List[str] = []
    for r in (*roots, ws_root):
        if r and r not in search_roots:
            search_roots.append(r)

    acs_raw: Optional[Dict[str, Any]] = None
    for root in search_roots:
        for rel_parts in (
            (".staging", "nk_genome", "configs", "saturation_thresholds.json"),
            ("nk_genome", "configs", "saturation_thresholds.json"),
        ):
            cand = os.path.join(root, *rel_parts)
            st_meta = _stat_safe_file(cand)
            if st_meta is None:
                continue
            cached_entry = _ACS_PARSED_JSON_CACHE.get(cand)
            if cached_entry is not None and cached_entry[0] == st_meta[0] and cached_entry[1] == st_meta[1]:
                acs_raw = cached_entry[2]
                break
            try:
                with open(cand, "r", encoding="utf-8") as fh:
                    parsed = json.load(fh)
                if isinstance(parsed, dict) and isinstance(parsed.get("autonomous_context_shield"), dict):
                    acs_raw = parsed["autonomous_context_shield"]
                    _ACS_PARSED_JSON_CACHE[cand] = (st_meta[0], st_meta[1], acs_raw)
                    break
            except Exception:
                continue
        if acs_raw is not None:
            break

    if acs_raw is None:
        return cfg

    cfg["z1_tokens"] = _safe_int_val(acs_raw.get("z1_tokens"), _Z1_TOKENS)
    cfg["z1_steps"] = _safe_int_val(acs_raw.get("z1_steps"), _Z1_STEPS)
    cfg["z2_tokens"] = _safe_int_val(acs_raw.get("z2_tokens"), _Z2_TOKENS)
    cfg["z2_steps"] = _safe_int_val(acs_raw.get("z2_steps"), _Z2_STEPS)
    cfg["z3_tokens"] = _safe_int_val(acs_raw.get("z3_tokens"), _Z3_TOKENS)
    cfg["z3_steps"] = _safe_int_val(acs_raw.get("z3_steps"), _Z3_STEPS)
    cfg["vel_delta"] = _safe_int_val(acs_raw.get("velocity_jump"), _VEL_DELTA)
    cfg["vel_cur"] = _safe_int_val(acs_raw.get("velocity_floor"), _VEL_CUR)
    cfg["vel_steps"] = _safe_int_val(acs_raw.get("velocity_step_floor"), _VEL_STEPS)
    cfg["epoch_baseline_tokens"] = _safe_int_val(
        acs_raw.get("epoch_baseline_tokens"), _DEFAULT_EPOCH_BASELINE_TOKENS, min_val=0
    )
    raw_cd = acs_raw.get("cooldown_s")
    if isinstance(raw_cd, (int, float)) and not isinstance(raw_cd, bool) and raw_cd >= 0:
        cfg["cooldown_s"] = float(raw_cd)
    raw_fb = acs_raw.get("fallback_steps")
    if isinstance(raw_fb, dict):
        cfg["fallback_steps"] = {
            "z1": _safe_int_val(raw_fb.get("z1"), cfg["z1_steps"]),
            "z2": _safe_int_val(raw_fb.get("z2"), cfg["z2_steps"]),
            "z3": _safe_int_val(raw_fb.get("z3"), cfg["z3_steps"]),
        }
    else:
        cfg["fallback_steps"] = {"z1": cfg["z1_steps"], "z2": cfg["z2_steps"], "z3": cfg["z3_steps"]}
    return cfg

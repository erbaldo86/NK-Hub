"""Lock cooperativo PIDFileLock e wrapper Win32 kernel32."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    _kernel32.OpenProcess.restype = ctypes.c_void_p

    _kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    _kernel32.GetExitCodeProcess.restype = ctypes.c_bool

    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_bool

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32
else:
    _kernel32 = None


def _active_kernel32() -> Any:
    """Restituisce _kernel32 leggendo eventuali override test su schemas.dual_ledgers."""
    for mod_name in ("schemas.dual_ledgers", "scripts.schemas.dual_ledgers", "dual_ledgers"):
        mod = sys.modules.get(mod_name)
        if mod is not None and "_kernel32" in vars(mod):
            return getattr(mod, "_kernel32", None)
    for mod in list(sys.modules.values()):
        mfile = getattr(mod, "__file__", "") or ""
        if mfile.endswith(("dual_ledgers.py", "dual_ledgers.pyc")) and "_kernel32" in vars(mod):
            return getattr(mod, "_kernel32", None)
    return _kernel32


class PIDFileLock:
    """Gestisce un file di lock cooperativo con nonce atomico e verifica di vitalita del PID."""

    def __init__(
        self,
        lock_file: Path,
        stale_timeout_sec: float = 30.0,
        acquire_timeout_sec: float = -1.0,
    ) -> None:
        self.lock_file = Path(lock_file)
        self.stale_timeout_sec = stale_timeout_sec
        self.acquire_timeout_sec = acquire_timeout_sec
        self.acquired = False
        self._nonce: str = ""

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Verifica se il processo associato al PID esiste ed e attivo."""
        if pid <= 0:
            return False
        k32 = _active_kernel32()
        if os.name == "nt" and k32 is not None:
            handle = k32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid,
            )
            if not handle or handle == INVALID_HANDLE_VALUE:
                err = (ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0) or k32.GetLastError()
                if err == ERROR_ACCESS_DENIED:
                    return True
                return False
            try:
                exit_code = ctypes.c_ulong()
                ok = k32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                if not ok:
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                k32.CloseHandle(handle)
        else:
            try:
                os.kill(pid, 0)
                return True
            except PermissionError:
                return True
            except OSError:
                return False

    def _claim_stale_lock(self, current_pid: int, obs_key: Tuple[Any, ...]) -> None:
        """Serializza il recupero di un lock stantio o corrotto tramite sidecar reap atomico."""
        del current_pid
        reap_path = self.lock_file.with_name(f".{self.lock_file.name}.reap")
        open_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        try:
            reap_fd = os.open(str(reap_path), open_flags, 0o600)
        except FileExistsError:
            try:
                grace = max(2.0, min(float(self.stale_timeout_sec), 5.0))
                if (time.time() - reap_path.stat().st_mtime) > grace:
                    reap_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        except OSError:
            return

        os.close(reap_fd)
        try:
            try:
                raw_cur = self.lock_file.read_text(encoding="utf-8")
            except OSError:
                return
            if not raw_cur.strip() and obs_key[0] != "__corrupt__":
                return
            if raw_cur.strip():
                try:
                    c_data = json.loads(raw_cur)
                    if isinstance(c_data, dict):
                        c_pid = int(c_data.get("pid", 0))
                        c_time = float(c_data.get("timestamp", 0.0))
                        c_key: Tuple[Any, ...] = (c_pid, str(c_data.get("nonce", "")), c_time)
                        if (
                            c_key != obs_key
                            and self._is_pid_alive(c_pid)
                            and (time.time() - c_time) <= self.stale_timeout_sec
                        ):
                            return
                except (ValueError, json.JSONDecodeError, TypeError):
                    pass
            try:
                self.lock_file.unlink(missing_ok=True)
            except OSError:
                pass
        finally:
            try:
                reap_path.unlink(missing_ok=True)
            except OSError:
                pass

    def acquire(self, timeout_sec: float = -1.0) -> bool:
        """Acquisisce atomicamente il file di lock e recupera lock stantii o orfani."""
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        eff_timeout = (
            (5.0 if self.stale_timeout_sec < 20.0 else 12.0)
            if timeout_sec < 0
            else float(timeout_sec)
        )
        deadline = time.time() + max(0.0, eff_timeout)
        current_pid = os.getpid()
        first_attempt = True

        while first_attempt or time.time() < deadline:
            first_attempt = False
            nonce = uuid.uuid4().hex
            payload = json.dumps(
                {"pid": current_pid, "nonce": nonce, "timestamp": time.time()}
            ).encode("utf-8")
            try:
                open_flags = (
                    os.O_CREAT
                    | os.O_EXCL
                    | os.O_WRONLY
                    | getattr(os, "O_BINARY", 0)
                )
                fd = os.open(
                    str(self.lock_file),
                    open_flags,
                    0o600,
                )
            except PermissionError as exc:
                if (
                    time.time() < deadline
                    and getattr(exc, "winerror", None) in (None, 5, 32, 33)
                ):
                    time.sleep(0.01)
                    continue
                raise
            except FileExistsError:
                obs_key: Optional[Tuple[Any, ...]] = None
                try:
                    content = self.lock_file.read_text(encoding="utf-8")
                    if not content.strip():
                        raise ValueError("Empty PID lock file")
                    lock_data = json.loads(content)
                    if not isinstance(lock_data, dict):
                        raise ValueError("PID lock payload is not a dict")
                    lock_pid = int(lock_data.get("pid", 0))
                    lock_nonce = str(lock_data.get("nonce", ""))
                    lock_time = float(lock_data.get("timestamp", 0.0))

                    is_stale_time = (time.time() - lock_time) > self.stale_timeout_sec
                    is_dead_pid = not self._is_pid_alive(lock_pid)
                    if is_stale_time or is_dead_pid:
                        obs_key = (lock_pid, lock_nonce, lock_time)
                except FileNotFoundError:
                    continue
                except PermissionError:
                    if time.time() < deadline:
                        time.sleep(0.01)
                    continue
                except (ValueError, json.JSONDecodeError, TypeError, OSError):
                    try:
                        st = self.lock_file.stat()
                        grace_sec = max(2.0, min(float(self.stale_timeout_sec), 5.0))
                        if (time.time() - st.st_mtime) > grace_sec:
                            obs_key = ("__corrupt__", st.st_mtime_ns)
                    except OSError:
                        pass

                if obs_key is not None:
                    self._claim_stale_lock(current_pid, obs_key)
                    continue

                if time.time() < deadline:
                    time.sleep(0.01)
                continue

            wrote_ok = False
            try:
                view = memoryview(payload)
                written = 0
                while written < len(view):
                    n_written = os.write(fd, view[written:])
                    if n_written <= 0:
                        raise OSError("Short write creating PID lock file")
                    written += n_written
                wrote_ok = True
            finally:
                os.close(fd)
                if not wrote_ok:
                    try:
                        self.lock_file.unlink(missing_ok=True)
                    except OSError:
                        pass

            self._nonce = nonce
            self.acquired = True
            return True

        return False

    def release(self) -> None:
        """Rilascia ed elimina il file di lock solo se ancora posseduto da (pid, nonce)."""
        if not self.acquired:
            return
        try:
            for attempt in range(8):
                try:
                    if not self.lock_file.exists():
                        break
                    raw = self.lock_file.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        lock_pid = int(data.get("pid", -1))
                        lock_nonce = str(data.get("nonce", ""))
                        if lock_pid == os.getpid() and lock_nonce == self._nonce:
                            self.lock_file.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.01 * (attempt + 1))
                except (ValueError, json.JSONDecodeError, TypeError, OSError):
                    break
        finally:
            self._nonce = ""
            self.acquired = False

    def __enter__(self) -> PIDFileLock:
        if not self.acquire(timeout_sec=self.acquire_timeout_sec):
            raise TimeoutError(f"Impossibile acquisire il lock: {self.lock_file}")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

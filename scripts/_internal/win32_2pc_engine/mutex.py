#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gestore RAII rientrante Win32NamedMutex con fallback POSIX flock."""

from __future__ import annotations

import ctypes
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from _internal.nk_common.win32_mutex import is_win32_handle_valid

from . import constants as _consts
from .constants import (
    Win32LockError,
    Win32LockTimeoutError,
    compute_sha256,
)
from .io_and_paths import get_mutex_name_for_path


def _clear_win32_last_error() -> None:
    """Azzera il codice di errore Win32 thread-local su piattaforme supportate."""
    if hasattr(ctypes, "set_last_error"):
        ctypes.set_last_error(0)


class Win32NamedMutex:
    """Gestore di contesto RAII rientrante per Named Mutex di Windows con fallback POSIX flock."""

    def __init__(
        self,
        name_or_path: Union[str, Path],
        timeout_ms: int = 5000,
        is_path: bool = True,
    ) -> None:
        if is_path:
            self.name = get_mutex_name_for_path(name_or_path)
            self._local_fallback_name = "Local\\" + self.name.split("\\", 1)[1]
        else:
            self.name = str(name_or_path)
            if self.name.startswith("Global\\"):
                self._local_fallback_name = "Local\\" + self.name.split("\\", 1)[1]
            else:
                self._local_fallback_name = self.name

        self.timeout_ms = timeout_ms
        self.handle: Optional[int] = None
        self.acquired: bool = False
        self.abandoned: bool = False
        self.abandoned_recovered: bool = False
        self._owning_thread_id: Optional[int] = None
        self._reentry_depth: int = 0
        self._last_wait_result: Optional[int] = None

    def __enter__(self) -> "Win32NamedMutex":
        self.acquire()
        if self._last_wait_result == _consts.WAIT_ABANDONED_0 or self.abandoned:
            self.abandoned = True
            self.abandoned_recovered = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def _get_posix_held_map(self) -> Dict[str, Tuple[int, int]]:
        held = getattr(_consts._POSIX_HELD_LOCKS, "locks", None)
        if held is None:
            held = {}
            _consts._POSIX_HELD_LOCKS.locks = held
        return held

    def acquire(self) -> None:
        """Acquisisce in modo rientrante l'handle e la proprieta del mutex con verifica thread."""
        k32 = _consts._get_active_kernel32()
        if self.acquired:
            curr_tid = (
                threading.get_ident() if k32 is None else k32.GetCurrentThreadId()
            )
            if self._owning_thread_id is not None and self._owning_thread_id != curr_tid:
                raise Win32LockError(
                    f"Named Mutex thread affinity violation: owned by {self._owning_thread_id}, requested by {curr_tid}."
                )
            self._reentry_depth += 1
            return

        if k32 is None:
            fcntl_mod = _consts._fcntl
            if fcntl_mod is None:
                raise Win32LockError(
                    "Nessun backend mutex disponibile (kernel32/fcntl assenti)."
                )
            current_thread = threading.get_ident()
            held_map = self._get_posix_held_map()
            if self.name in held_map:
                existing_fd, count = held_map[self.name]
                held_map[self.name] = (existing_fd, count + 1)
                self.handle = existing_fd
                self.acquired = True
                self.abandoned = False
                self.abandoned_recovered = False
                self._owning_thread_id = current_thread
                self._reentry_depth = 1
                self._last_wait_result = _consts.WAIT_OBJECT_0
                return

            lock_dir = Path(tempfile.gettempdir()) / "nk_2pc_posix_locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_file = lock_dir / f"{compute_sha256(self.name)}.lock"
            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o600)
            deadline = (
                None
                if self.timeout_ms == _consts.INFINITE
                else (time.monotonic() + max(0.0, float(self.timeout_ms)) / 1000.0)
            )
            while True:
                try:
                    fcntl_mod.flock(fd, fcntl_mod.LOCK_EX | fcntl_mod.LOCK_NB)
                    held_map[self.name] = (fd, 1)
                    self.handle = fd
                    self.acquired = True
                    self.abandoned = False
                    self.abandoned_recovered = False
                    self._owning_thread_id = current_thread
                    self._reentry_depth = 1
                    self._last_wait_result = _consts.WAIT_OBJECT_0
                    return
                except (BlockingIOError, OSError):
                    if deadline is not None and time.monotonic() >= deadline:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                        raise Win32LockTimeoutError(
                            f"Timed out after {self.timeout_ms}ms waiting for mutex '{self.name}'"
                        )
                    time.sleep(0.005)

        current_thread = k32.GetCurrentThreadId()
        _clear_win32_last_error()
        handle = k32.CreateMutexW(None, False, self.name)
        err = _consts._get_win32_last_error()

        if (
            not handle or handle == _consts.INVALID_HANDLE_VALUE
        ) and err == _consts.ERROR_ACCESS_DENIED:
            _clear_win32_last_error()
            handle = k32.CreateMutexW(None, False, self._local_fallback_name)
            err = _consts._get_win32_last_error()

        if not handle or handle == _consts.INVALID_HANDLE_VALUE or not is_win32_handle_valid(handle):
            raise Win32LockError(
                f"Failed to create/open mutex '{self.name}'. Win32 Error: {err}"
            )

        self.handle = handle
        _clear_win32_last_error()
        wait_res = k32.WaitForSingleObject(
            self.handle,
            ctypes.c_uint32(self.timeout_ms),
        )
        self._last_wait_result = wait_res

        if wait_res == _consts.WAIT_OBJECT_0:
            self.acquired = True
            self.abandoned = False
            self.abandoned_recovered = False
            self._owning_thread_id = current_thread
            self._reentry_depth = 1
        elif wait_res == _consts.WAIT_ABANDONED_0:
            self.acquired = True
            self.abandoned = True
            self.abandoned_recovered = True
            self._owning_thread_id = current_thread
            self._reentry_depth = 1
        elif wait_res == _consts.WAIT_TIMEOUT:
            self._cleanup_handle()
            raise Win32LockTimeoutError(
                f"Timed out after {self.timeout_ms}ms waiting for mutex '{self.name}'"
            )
        else:
            last_err = _consts._get_win32_last_error()
            self._cleanup_handle()
            raise Win32LockError(
                f"WaitForSingleObject failed on mutex '{self.name}' with code {wait_res}. Win32 Error: {last_err}"
            )

    def release(self) -> None:
        """Rilascia il mutex verificando la profondita di rientranza e l'affinita del thread."""
        k32 = _consts._get_active_kernel32()
        fcntl_mod = _consts._fcntl
        if self.handle is not None:
            if k32 is None:
                current_thread = threading.get_ident()
                if self.acquired:
                    if (
                        self._owning_thread_id is not None
                        and self._owning_thread_id != current_thread
                    ):
                        raise Win32LockError(
                            f"Named Mutex thread affinity violation: acquired by thread {self._owning_thread_id} "
                            f"but released by thread {current_thread}."
                        )
                    if self._reentry_depth > 1:
                        self._reentry_depth -= 1
                        return
                    held_map = self._get_posix_held_map()
                    fd_entry = held_map.get(self.name)
                    try:
                        if fd_entry is not None and fd_entry[1] > 1:
                            held_map[self.name] = (fd_entry[0], fd_entry[1] - 1)
                        else:
                            held_map.pop(self.name, None)
                            if fcntl_mod is not None:
                                try:
                                    fcntl_mod.flock(self.handle, fcntl_mod.LOCK_UN)
                                except OSError:
                                    pass
                            try:
                                os.close(self.handle)
                            except OSError:
                                pass
                    finally:
                        self.acquired = False
                        self._reentry_depth = 0
                        self._owning_thread_id = None
                        self.handle = None
                else:
                    try:
                        os.close(self.handle)
                    except OSError:
                        pass
                    self.handle = None
                return

            current_thread = k32.GetCurrentThreadId()
            if self.acquired:
                if (
                    self._owning_thread_id is not None
                    and self._owning_thread_id != current_thread
                ):
                    raise Win32LockError(
                        f"Win32 Named Mutex thread affinity violation: acquired by thread {self._owning_thread_id} "
                        f"but released by thread {current_thread}."
                    )
                if self._reentry_depth > 1:
                    self._reentry_depth -= 1
                    return
                try:
                    k32.ReleaseMutex(self.handle)
                finally:
                    self.acquired = False
                    self._reentry_depth = 0
                    self._owning_thread_id = None
                    self._cleanup_handle()
            else:
                self._cleanup_handle()

    def _cleanup_handle(self) -> None:
        """Chiude l'handle nativo del kernel."""
        k32 = _consts._get_active_kernel32()
        if k32 is not None and self.handle and self.handle != _consts.INVALID_HANDLE_VALUE:
            k32.CloseHandle(self.handle)
            self.handle = None

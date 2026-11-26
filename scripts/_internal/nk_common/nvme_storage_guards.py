# -*- coding: utf-8 -*-
"""Guardie NVMe Win32, rilevamento cloud-mount e Named Mutex fail-closed (pure stdlib)."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Union

from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import create_or_open_named_mutex, release_win32_mutex

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None

_CSIDL_LOCAL_APPDATA = 0x001C
_DRIVE_REMOTE = 4
_CLOUD_MOUNT_SEGMENTS = frozenset(
    {"il mio drive", "my drive", "google drive", "googledrive", "onedrive", "dropbox", "icloud", "iclouddrive"}
)
_CLOUD_VOL_MARKERS = ("google", "drivefs", "rclone", "webdav")


def _win32_shell_local_appdata() -> Optional[Path]:
    try:
        buf = ctypes.create_unicode_buffer(260)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        hr = shell32.SHGetFolderPathW(None, _CSIDL_LOCAL_APPDATA, None, 0, buf)
        if hr == 0 and buf.value.strip():
            cand = Path(buf.value.strip()).resolve()
            return None if is_cloud_mount_path(cand) else cand
    except (OSError, AttributeError, ValueError):
        return None
    return None


def resolve_local_appdata_dir() -> Path:
    if sys.platform == "win32":
        shell_dir = _win32_shell_local_appdata()
        if shell_dir is not None:
            return shell_dir
    env_la = os.environ.get("LOCALAPPDATA", "").strip()
    if env_la:
        cand = Path(env_la).expanduser().resolve()
        if not is_cloud_mount_path(cand):
            return cand
    return Path(tempfile.gettempdir()).resolve()


def _win32_drive_is_cloud(drive_root: str) -> bool:
    if sys.platform != "win32" or not drive_root:
        return False
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        k32.GetDriveTypeW.restype = ctypes.c_uint32
        if int(k32.GetDriveTypeW(drive_root)) == _DRIVE_REMOTE:
            return True
        vol_name, fs_name = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        if k32.GetVolumeInformationW(drive_root, vol_name, 261, None, None, None, fs_name, 261):
            combined = f"{vol_name.value} {fs_name.value}".lower()
            return any(tok in combined for tok in _CLOUD_VOL_MARKERS)
    except (OSError, AttributeError, ValueError):
        return False
    return False


def is_cloud_mount_path(path: Union[str, Path]) -> bool:
    raw = str(path or "").strip()
    if not raw:
        return False
    try:
        parts_low = [p.lower().strip() for p in Path(raw).parts if p]
    except Exception:
        parts_low = []
    if any(seg in _CLOUD_MOUNT_SEGMENTS for seg in parts_low):
        return True
    low_norm = raw.replace("\\", "/").lower()
    if "google/drivefs" in low_norm or "onedrive -" in low_norm:
        return True
    if sys.platform == "win32":
        drive, _ = os.path.splitdrive(os.path.abspath(raw))
        if drive and _win32_drive_is_cloud(drive + "\\"):
            return True
    return False


def ensure_nvme_local_dir(preferred: Union[str, Path], fallback_subdir: str) -> Path:
    """Verifica reparse prima di resolve() e redirige cloud-mount su LOCALAPPDATA/nk_hub."""
    raw_pref = Path(preferred).expanduser()
    if is_reparse_entry(raw_pref) or is_reparse_entry(raw_pref.parent):
        raise OSError(f"Reparse point vietato su directory NVMe: {raw_pref}")
    pref_path = raw_pref.resolve()
    target = (
        (resolve_local_appdata_dir() / "nk_hub" / fallback_subdir).resolve()
        if is_cloud_mount_path(pref_path)
        else pref_path
    )
    if is_reparse_entry(target.parent) or is_reparse_entry(target):
        raise OSError(f"Reparse point vietato su directory NVMe: {target}")
    target.mkdir(parents=True, exist_ok=True)
    if is_reparse_entry(target):
        raise OSError(f"Reparse point rilevato dopo mkdir: {target}")
    return target


class FailClosedNamedMutex:
    """Context manager Named Mutex Win32 (o flock POSIX) rigorosamente fail-closed."""

    def __init__(self, mutex_name: str, *, wait_ms: int = 3000) -> None:
        self.mutex_name = str(mutex_name)
        self.wait_ms = max(0, int(wait_ms))
        self._handle: Optional[int] = None
        self._posix_fd: Optional[int] = None
        self._acquired = False

    def _acquire_posix(self) -> None:
        lock_dir = Path(tempfile.gettempdir()) / "nk_locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        h16 = hashlib.sha256(self.mutex_name.lower().encode("utf-8")).hexdigest()[:16]
        fd = os.open(str(lock_dir / f"{h16}.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        if _fcntl is None:
            self._posix_fd = fd
            self._acquired = True
            return
        deadline = time.monotonic() + (self.wait_ms / 1000.0)
        while True:
            try:
                _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                self._posix_fd = fd
                self._acquired = True
                return
            except OSError as exc:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TimeoutError(f"Mutex timeout POSIX: {self.mutex_name}") from exc
                time.sleep(0.01)

    def acquire(self) -> "FailClosedNamedMutex":
        if sys.platform != "win32":
            self._acquire_posix()
            return self
        handle, ok, err = create_or_open_named_mutex(self.mutex_name, wait_ms=self.wait_ms)
        if ok and handle is not None:
            self._handle = int(handle)
            self._acquired = True
            return self
        if err == "timeout":
            raise TimeoutError(f"Timeout acquisizione mutex {self.mutex_name} ({self.wait_ms}ms)")
        raise OSError(f"Errore mutex Win32 {self.mutex_name}: {err or 'unknown'}")

    def release(self) -> None:
        if sys.platform != "win32":
            if self._posix_fd is not None:
                try:
                    if _fcntl is not None:
                        _fcntl.flock(self._posix_fd, _fcntl.LOCK_UN)
                finally:
                    os.close(self._posix_fd)
                    self._posix_fd = None
            self._acquired = False
            return
        if self._handle is not None:
            release_win32_mutex(self._handle)
            self._handle = None
        self._acquired = False

    def __enter__(self) -> "FailClosedNamedMutex":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

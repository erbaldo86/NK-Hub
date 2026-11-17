# -*- coding: utf-8 -*-
"""Operazioni atomiche di scrittura e rimozione su filesystem Win32/POSIX con long-path."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Tuple, Union

_RETRY_WINERRORS = frozenset((5, 32, 33))
_RETRY_ERRNOS = frozenset((11, 13, 16))
_DEFAULT_IO_DELAYS: Tuple[float, ...] = (0.01, 0.02, 0.04, 0.08, 0.16)


def win_long_path(path: Union[str, Path]) -> Path:
    """Applica il prefisso esteso Win32 \\\\?\\ ai percorsi Windows lunghi (>= 240 char)."""
    path_obj = Path(path)
    raw_str = str(path_obj)
    if os.name != "nt":
        return path_obj
    if raw_str.startswith("\\\\?\\"):
        return path_obj
    try:
        resolved_str = str(path_obj.resolve())
    except Exception:
        resolved_str = os.path.abspath(raw_str)
    if resolved_str.startswith("\\\\?\\"):
        return Path(resolved_str)
    if len(resolved_str) >= 240 or len(raw_str) >= 240:
        if resolved_str.startswith("\\\\"):
            return Path("\\\\?\\UNC\\" + resolved_str.lstrip("\\"))
        return Path("\\\\?\\" + resolved_str)
    return path_obj


def _is_retryable_os_error(exc: OSError) -> bool:
    """Verifica se un OSError appartiene agli errori transienti Win32/POSIX ritentabili."""
    winerr = getattr(exc, "winerror", None)
    if winerr in _RETRY_WINERRORS:
        return True
    if winerr is None:
        return isinstance(exc, PermissionError) or getattr(exc, "errno", None) in _RETRY_ERRNOS
    return False


def unlink_with_retry(
    path: Union[str, Path],
    delays: Sequence[float] = (0.025, 0.025, 0.025, 0.025, 0.025),
    *,
    raise_on_error: bool = False,
) -> bool:
    """Elimina un file con retry su errori transienti Win32/POSIX."""
    target_lp = win_long_path(path)
    last_exc: Optional[OSError] = None
    max_attempts = max(1, len(delays) + 1)
    for attempt in range(max_attempts):
        try:
            if not target_lp.exists() and not target_lp.is_symlink():
                return True
            target_lp.unlink(missing_ok=True)
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            last_exc = exc
            if not _is_retryable_os_error(exc) or attempt >= len(delays):
                break
            time.sleep(max(0.0, float(delays[attempt])))
    still_exists = target_lp.exists() or target_lp.is_symlink()
    if not still_exists:
        return True
    if raise_on_error and last_exc is not None:
        raise last_exc
    return False


def atomic_write_bytes(
    target_path: Union[str, Path],
    payload: bytes,
    *,
    ensure_parent: bool = True,
    fsync_data: bool = True,
    reparse_check: Optional[Callable[[Path], bool]] = None,
    delays: Sequence[float] = _DEFAULT_IO_DELAYS,
) -> Tuple[bool, Optional[str]]:
    """Scrive atomicamente byte su file tramite .tmp.<pid>.<ns> O_EXCL, fsync e os.replace."""
    t_obj = Path(target_path)
    parent_dir = t_obj.parent
    if reparse_check is not None:
        if (parent_dir and reparse_check(parent_dir)) or reparse_check(t_obj):
            return False, "reparse_guard"
    if ensure_parent:
        try:
            win_long_path(parent_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"mkdir_error:{exc}"
        if reparse_check is not None and parent_dir and reparse_check(parent_dir):
            return False, "reparse_guard"

    target_lp = win_long_path(t_obj)
    tmp_obj: Optional[Path] = None
    tmp_lp: Optional[Path] = None
    fd: Optional[int] = None
    for _ in range(4):
        cand_obj = parent_dir / f".{t_obj.name}.tmp.{os.getpid()}.{time.time_ns()}.{uuid.uuid4().hex[:6]}"
        if reparse_check is not None and reparse_check(cand_obj):
            return False, "reparse_guard"
        cand_lp = win_long_path(cand_obj)
        try:
            open_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_BINARY", 0)
            )
            fd = os.open(str(cand_lp), open_flags, 0o600)
            tmp_obj = cand_obj
            tmp_lp = cand_lp
            break
        except FileExistsError:
            continue
        except OSError as exc:
            return False, f"open_tmp_error:{exc}"

    if fd is None or tmp_obj is None or tmp_lp is None:
        return False, "tmp_allocation_exhausted"

    moved_ok = False
    try:
        try:
            view = memoryview(payload)
            written = 0
            while written < len(view):
                n_written = os.write(fd, view[written:])
                if n_written <= 0:
                    raise OSError("Short write on temporary staging file")
                written += n_written
            if fsync_data:
                os.fsync(fd)
        finally:
            os.close(fd)

        last_exc: Optional[OSError] = None
        total_attempts = max(1, len(delays) + 1)
        for attempt in range(total_attempts):
            try:
                if reparse_check is not None and reparse_check(t_obj):
                    return False, "reparse_guard"
                os.replace(str(tmp_lp), str(target_lp))
                moved_ok = True
                return True, None
            except OSError as exc:
                last_exc = exc
                if _is_retryable_os_error(exc) and attempt < len(delays):
                    time.sleep(max(0.0, float(delays[attempt])))
                    continue
                if getattr(exc, "winerror", None) in _RETRY_WINERRORS:
                    return False, f"winerror_exhausted:{exc}"
                return False, f"io_error:{exc}"
        return False, f"winerror_exhausted:{last_exc}"
    except Exception as exc:
        return False, f"io_error:{exc}"
    finally:
        if not moved_ok and tmp_lp is not None:
            try:
                if reparse_check is None or not reparse_check(tmp_obj):
                    os.unlink(str(tmp_lp))
            except OSError:
                pass


def atomic_write_text(
    target_path: Union[str, Path],
    content: str,
    *,
    encoding: str = "utf-8",
    ensure_parent: bool = True,
    fsync_data: bool = True,
    reparse_check: Optional[Callable[[Path], bool]] = None,
    delays: Sequence[float] = _DEFAULT_IO_DELAYS,
) -> Tuple[bool, Optional[str]]:
    """Codifica il testo e lo scrive atomicamente tramite atomic_write_bytes."""
    return atomic_write_bytes(
        target_path,
        content.encode(encoding),
        ensure_parent=ensure_parent,
        fsync_data=fsync_data,
        reparse_check=reparse_check,
        delays=delays,
    )


def atomic_write_json(
    target_path: Union[str, Path],
    payload: Any,
    *,
    indent: Optional[int] = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    separators: Optional[Tuple[str, str]] = None,
    ensure_parent: bool = True,
    fsync_data: bool = True,
    reparse_check: Optional[Callable[[Path], bool]] = None,
    delays: Sequence[float] = _DEFAULT_IO_DELAYS,
) -> Tuple[bool, Optional[str]]:
    """Serializza il payload in JSON UTF-8 e lo scrive atomicamente su disco."""
    serialized = json.dumps(
        payload,
        indent=indent,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        separators=separators,
    )
    return atomic_write_text(
        target_path,
        serialized,
        encoding="utf-8",
        ensure_parent=ensure_parent,
        fsync_data=fsync_data,
        reparse_check=reparse_check,
        delays=delays,
    )

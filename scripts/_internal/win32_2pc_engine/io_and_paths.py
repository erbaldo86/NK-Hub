#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Operazioni I/O Win32 long-path, canonicalizzazione percorsi e sicurezza reparse point."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import List, Optional, Set, Union

from _internal.nk_common.io import (
    atomic_write_bytes as _common_atomic_write_bytes,
    unlink_with_retry as _common_unlink_with_retry,
    win_long_path as _common_win_long_path,
)
from _internal.nk_common.paths import resolve_workspace_root

from . import constants as _consts
from .constants import TwoPhaseCommitError


def _win_long_path(p: Union[str, Path]) -> Path:
    """Applica il prefisso esteso Win32 \\\\?\\ tramite nk_common.io."""
    return _common_win_long_path(p)


def _replace_with_retry(
    src: Path,
    dst: Path,
    retries: int = _consts.RETRY_ATTEMPTS_IO,
    delay_sec: float = _consts.RETRY_DELAY_SEC_IO,
) -> None:
    """Esegue os.replace con retry e backoff progressivo su errori WinError (5, 32, 33)."""
    src_lp = _win_long_path(src)
    dst_lp = _win_long_path(dst)
    last_exc: Optional[BaseException] = None
    attempts = max(1, int(retries))
    base_delay = max(0.0, float(delay_sec))
    max_backoff = max(base_delay, 1.5)
    for attempt in range(attempts):
        try:
            os.replace(src_lp, dst_lp)
            return
        except OSError as exc:
            last_exc = exc
            winerr = getattr(exc, "winerror", None)
            is_retryable = (winerr in (5, 32, 33)) or (
                winerr is None
                and (
                    isinstance(exc, PermissionError)
                    or getattr(exc, "errno", None) in (11, 13, 16)
                )
            )
            if not is_retryable:
                raise
            if attempt + 1 < attempts:
                backoff = min(max_backoff, base_delay * (2**attempt))
                time.sleep(backoff)
    if last_exc is not None:
        raise last_exc


def _unlink_with_retry(
    target: Path,
    retries: int = _consts.RETRY_ATTEMPTS_IO,
    delay_sec: float = _consts.RETRY_DELAY_SEC_IO,
) -> None:
    """Elimina un file con retry deterministico delegando a nk_common.io."""
    attempts = max(1, int(retries))
    delays = [max(0.0, float(delay_sec))] * max(0, attempts - 1)
    _common_unlink_with_retry(target, delays=delays, raise_on_error=True)


def _atomic_write_bytes(target_path: Path, data: bytes) -> None:
    """Scrive atomicamente i byte sul target tramite nk_common.io.atomic_write_bytes."""
    ok, err = _common_atomic_write_bytes(
        target_path, data, ensure_parent=True, fsync_data=True
    )
    if not ok:
        raise OSError(err or f"Atomic write failed for {target_path}")


def _get_repo_hash16(root: Union[str, Path]) -> str:
    """Calcola il prefisso SHA-256 a 16 caratteri della root canonica."""
    norm_root = os.path.realpath(str(root)).lower().replace("/", "\\").rstrip("\\")
    return hashlib.sha256(norm_root.encode("utf-8")).hexdigest()[:16]


def get_mutex_name_for_path(file_path: Union[str, Path]) -> str:
    """Deriva il nome deterministico del mutex Win32 dal percorso file canonico."""
    norm_path = os.path.realpath(str(file_path)).lower().replace("/", "\\")
    path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()
    return f"Global\\NK_FileLock_{path_hash}"


def get_repo_batch_mutex_name(root: Union[str, Path]) -> str:
    """Deriva il nome deterministico del mutex batch di repository dalla root canonica."""
    norm_root = os.path.realpath(str(root)).lower().replace("/", "\\").rstrip("\\")
    root_hash16 = hashlib.sha256(norm_root.encode("utf-8")).hexdigest()[:16]
    return f"Global\\NK_RepoBatchLock_{root_hash16}"


def _is_reparse_point(path_obj: Path) -> bool:
    """Rileva symlink o Win32 junction/reparse point (FILE_ATTRIBUTE_REPARSE_POINT 0x400)."""
    try:
        if path_obj.is_symlink():
            return True
    except OSError:
        pass
    lp_str = str(_win_long_path(path_obj))
    k32 = _consts._get_active_kernel32()
    if k32 is not None:
        attrs = k32.GetFileAttributesW(lp_str)
        if (
            attrs != _consts.INVALID_FILE_ATTRIBUTES
            and (attrs & _consts.FILE_ATTRIBUTE_REPARSE_POINT) != 0
        ):
            return True
    try:
        st = os.lstat(lp_str)
        file_attrs = getattr(st, "st_file_attributes", 0)
        if (file_attrs & _consts.FILE_ATTRIBUTE_REPARSE_POINT) != 0:
            return True
    except OSError:
        pass
    return False


def _assert_no_external_reparse(
    path_obj: Path,
    real_root: Path,
    stop_at: Optional[Path] = None,
) -> None:
    """Rifiuta symlink o junction che puntino fuori dalla root canonica del repository."""
    curr = Path(path_obj)
    stop_resolved = Path(stop_at) if stop_at is not None else real_root
    visited: Set[str] = set()
    while True:
        curr_key = str(curr)
        if curr_key in visited:
            break
        visited.add(curr_key)
        if _is_reparse_point(curr):
            real_target = Path(os.path.realpath(str(curr)))
            if real_target != real_root and real_root not in real_target.parents:
                raise TwoPhaseCommitError(
                    f"Reparse point o junction esterna a root rilevata ({curr} -> {real_target})"
                )
        if curr == stop_resolved or curr.parent == curr:
            break
        curr = curr.parent


def _validate_win32_canonical_rel_path(rel_raw: Union[str, Path]) -> str:
    """Rifiuta ADS (:), traversal (..) e componenti con punti o spazi finali Win32."""
    raw_str = str(rel_raw)
    if not raw_str or "\x00" in raw_str:
        raise TwoPhaseCommitError(
            f"Percorso relativo vuoto o null-byte rilevato: {rel_raw!r}"
        )
    if ":" in raw_str:
        raise TwoPhaseCommitError(
            f"Alternate Data Stream (ADS) o ':' vietato nel percorso: {rel_raw!r}"
        )
    parts = raw_str.replace("\\", "/").split("/")
    cleaned: List[str] = []
    for comp in parts:
        if comp in ("", "."):
            continue
        if comp == "..":
            raise TwoPhaseCommitError(
                f"Path traversal '..' vietato nel percorso: {rel_raw!r}"
            )
        if comp != comp.rstrip(". "):
            raise TwoPhaseCommitError(
                f"Componente percorso Win32 con punto o spazio finale vietato ({comp!r} in {rel_raw!r})"
            )
        cleaned.append(comp)
    if not cleaned:
        raise TwoPhaseCommitError(
            f"Percorso relativo privo di componenti validi: {rel_raw!r}"
        )
    return "/".join(cleaned)


def _extract_patch_notes_headers(text: str) -> List[str]:
    """Estrae tutte le intestazioni storiche ## [...] dal contenuto di PATCH_NOTES.md."""
    return [m.strip() for m in _consts._PATCH_NOTES_HEADER_RE.findall(text)]


def _resolve_repo_root(repo_root: Optional[Union[str, Path]] = None) -> Path:
    """Risolve in modo deterministico la radice del repository tramite nk_common.paths."""
    if repo_root:
        return Path(repo_root).resolve()
    return Path(resolve_workspace_root(__file__)).resolve()

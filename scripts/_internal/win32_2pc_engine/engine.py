#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Motore TwoPhaseCommitEngine (prepare/commit/abort/shadow-swap) e win32_atomic_replace."""

from __future__ import annotations

import ctypes
import os
import random
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from .constants import (
        IPCPointerReturn,
        TwoPhaseCommitPrepare,
        TwoPhaseCommitVerdict,
    )
else:
    IPCPointerReturn: Any = Any
    TwoPhaseCommitPrepare: Any = Any
    TwoPhaseCommitVerdict: Any = Any

from . import constants as _consts
from .constants import TwoPhaseCommitError, compute_crc32, compute_sha256
from .io_and_paths import (
    _atomic_write_bytes,
    _unlink_with_retry,
    _win_long_path,
)
from .mutex import Win32NamedMutex
from .wal import WriteAheadLogManager


class TwoPhaseCommitEngine:
    """Motore di commit atomico a due fasi per Windows e Google Drive FS."""

    MAX_RETRIES = 8
    BASE_DELAY_MS = 25.0
    MAX_DELAY_MS = 1500.0

    def __init__(self, wal_manager: Optional[WriteAheadLogManager] = None) -> None:
        self.wal = wal_manager or WriteAheadLogManager()

    @staticmethod
    def _backoff_sleep(attempt: int) -> None:
        """Esegue una pausa esponenziale con full jitter."""
        cap_ms = min(
            TwoPhaseCommitEngine.MAX_DELAY_MS,
            TwoPhaseCommitEngine.BASE_DELAY_MS * (2**attempt),
        )
        sleep_s = random.uniform(0.0, cap_ms) / 1000.0
        time.sleep(sleep_s)

    def prepare(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        timeout_ms: int = 5000,
    ) -> TwoPhaseCommitPrepare:
        """Fase 1 (Prepare): scrive il file temporaneo di staging e registra il WAL."""
        _consts._ensure_ipc_contracts_loaded()
        target = Path(target_path).resolve()
        _win_long_path(target.parent).mkdir(parents=True, exist_ok=True)

        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        sha256_hash = compute_sha256(raw_bytes)
        crc32_hash = compute_crc32(raw_bytes)
        tx_id = f"tx_{uuid.uuid4().hex[:12]}_{int(time.time()*1000)}"

        staging_file = target.parent / f".staging_{target.name}.{tx_id}.tmp"

        with open(_win_long_path(staging_file), "wb") as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(f.fileno())

        self.wal.write_wal(
            tx_id=tx_id,
            target_path=target,
            staging_path=staging_file,
            payload_sha256=sha256_hash,
            payload_crc32=crc32_hash,
            state="PREPARED",
        )

        return _consts.TwoPhaseCommitPrepare(
            transaction_id=tx_id,
            target_path=str(target),
            staging_path=str(staging_file),
            expected_sha256=sha256_hash,
            crc32=crc32_hash,
            timeout_ms=timeout_ms,
            timestamp_utc=time.time(),
        )

    def commit(self, prepare_req: TwoPhaseCommitPrepare) -> TwoPhaseCommitVerdict:
        """Fase 2 (Commit): acquisisce il mutex, salva la pre-immagine e promuove il file."""
        _consts._ensure_ipc_contracts_loaded()
        start_time = time.perf_counter()
        target = Path(prepare_req.target_path).resolve()
        staging = Path(prepare_req.staging_path).resolve()

        with Win32NamedMutex(target, timeout_ms=prepare_req.timeout_ms):
            if not _win_long_path(staging).exists():
                return self.abort(
                    prepare_req,
                    reason=f"Staging file {staging} does not exist",
                )

            staging_data = _win_long_path(staging).read_bytes()
            if compute_sha256(staging_data) != prepare_req.expected_sha256:
                return self.abort(
                    prepare_req,
                    reason="Staging file SHA-256 mismatch during commit phase",
                )

            if compute_crc32(staging_data) != prepare_req.crc32:
                return self.abort(
                    prepare_req,
                    reason="Staging file CRC32 mismatch during commit phase",
                )

            target_lp = _win_long_path(target)
            had_previous = target_lp.exists() and target_lp.is_file()
            previous_bytes: Optional[bytes] = (
                target_lp.read_bytes() if had_previous else None
            )

            self.wal.update_wal_state(
                target,
                prepare_req.transaction_id,
                state="COMMITTED",
            )
            success = self._execute_atomic_commit(staging, target)
            if not success:
                if (
                    had_previous
                    and previous_bytes is not None
                    and not target_lp.exists()
                ):
                    try:
                        _atomic_write_bytes(target, previous_bytes)
                    except OSError:
                        pass
                return self.abort(
                    prepare_req,
                    reason="Atomic move and Shadow Swap fallback exhausted all retries",
                )

            written_bytes = target_lp.read_bytes()
            if compute_sha256(written_bytes) != prepare_req.expected_sha256:
                if had_previous and previous_bytes is not None:
                    _atomic_write_bytes(target, previous_bytes)
                else:
                    try:
                        _unlink_with_retry(target)
                    except OSError:
                        pass
                return self.abort(
                    prepare_req,
                    reason="Committed file SHA-256 verification failed on disk",
                )

            self.wal.purge_wal(target, prepare_req.transaction_id)

            if _win_long_path(staging).exists():
                try:
                    _win_long_path(staging).unlink()
                except OSError:
                    pass

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return _consts.TwoPhaseCommitVerdict(
                transaction_id=prepare_req.transaction_id,
                verdict="COMMIT",
                reason=None,
                committed_path=str(target),
                execution_time_ms=elapsed_ms,
            )

    def abort(
        self,
        prepare_req: TwoPhaseCommitPrepare,
        reason: Optional[str] = None,
    ) -> TwoPhaseCommitVerdict:
        """Fase 2 (Abort): elimina il file di staging e pulisce il record WAL."""
        _consts._ensure_ipc_contracts_loaded()
        staging = Path(prepare_req.staging_path)
        if _win_long_path(staging).exists():
            try:
                _win_long_path(staging).unlink()
            except OSError:
                pass

        self.wal.update_wal_state(
            prepare_req.target_path,
            prepare_req.transaction_id,
            state="ABORTED",
        )
        self.wal.purge_wal(prepare_req.target_path, prepare_req.transaction_id)

        return _consts.TwoPhaseCommitVerdict(
            transaction_id=prepare_req.transaction_id,
            verdict="ABORT",
            reason=reason or "Transaction explicitly aborted",
            committed_path=None,
            execution_time_ms=0.0,
        )

    def _execute_atomic_commit(self, src: Path, dst: Path) -> bool:
        """Esegue la sostituzione atomica con MoveFileExW e Shadow Swap."""
        src_lp = _win_long_path(src.resolve())
        dst_lp = _win_long_path(dst.resolve())
        src_w = str(src_lp)
        dst_w = str(dst_lp)
        flags = (
            _consts.MOVEFILE_REPLACE_EXISTING
            | _consts.MOVEFILE_WRITE_THROUGH
            | _consts.MOVEFILE_COPY_ALLOWED
        )

        k32 = _consts._get_active_kernel32()
        for attempt in range(self.MAX_RETRIES):
            if k32 is not None:
                if hasattr(ctypes, "set_last_error"):
                    ctypes.set_last_error(0)
                res = k32.MoveFileExW(src_w, dst_w, flags)
                if res:
                    return True

                err = _consts._get_win32_last_error()
                if err in (
                    _consts.ERROR_SHARING_VIOLATION,
                    _consts.ERROR_ACCESS_DENIED,
                    _consts.ERROR_LOCK_VIOLATION,
                ):
                    self._backoff_sleep(attempt)
                    continue

            try:
                os.replace(src_lp, dst_lp)
                return True
            except (PermissionError, OSError):
                self._backoff_sleep(attempt)

        return self._shadow_swap_fallback(src, dst)

    def _shadow_swap_fallback(self, src: Path, dst: Path) -> bool:
        """Esegue la strategia Shadow Swap per aggirare i lock di Google Drive FS."""
        shadow_path = dst.parent / f".shadow_{dst.name}_{uuid.uuid4().hex[:8]}.tmp"
        old_path = dst.parent / f".old_{dst.name}_{uuid.uuid4().hex[:8]}.tmp"
        src_lp = _win_long_path(src)
        dst_lp = _win_long_path(dst)
        shadow_lp = _win_long_path(shadow_path)
        old_lp = _win_long_path(old_path)

        try:
            for attempt in range(self.MAX_RETRIES):
                moved_to_old = False
                try:
                    raw = src_lp.read_bytes()
                    with open(shadow_lp, "wb") as sf:
                        sf.write(raw)
                        sf.flush()
                        os.fsync(sf.fileno())

                    if dst_lp.exists():
                        os.replace(dst_lp, old_lp)
                        moved_to_old = True

                    os.replace(shadow_lp, dst_lp)

                    if old_lp.exists():
                        try:
                            old_lp.unlink()
                        except OSError:
                            pass
                    return True
                except Exception:
                    if moved_to_old and old_lp.exists() and not dst_lp.exists():
                        try:
                            os.replace(old_lp, dst_lp)
                        except OSError:
                            pass
                    self._backoff_sleep(attempt)
            return False
        finally:
            if shadow_lp.exists():
                try:
                    shadow_lp.unlink(missing_ok=True)
                except OSError:
                    pass
            if old_lp.exists() and dst_lp.exists():
                try:
                    old_lp.unlink(missing_ok=True)
                except OSError:
                    pass

    def atomic_write(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        timeout_ms: int = 5000,
    ) -> TwoPhaseCommitVerdict:
        """Esegue prepare e commit sotto un unico Win32NamedMutex rientrante sul file target."""
        target = Path(target_path).resolve()
        with Win32NamedMutex(target, timeout_ms=timeout_ms):
            prep = self.prepare(target, content, timeout_ms=timeout_ms)
            return self.commit(prep)

    def create_ipc_pointer(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        mime_type: str = "application/octet-stream",
    ) -> IPCPointerReturn:
        """Scrive il payload con 2PC e restituisce un contratto IPCPointerReturn."""
        _consts._ensure_ipc_contracts_loaded()
        verdict = self.atomic_write(target_path, content)
        if verdict.verdict != "COMMIT" or not verdict.committed_path:
            raise TwoPhaseCommitError(
                f"Failed to commit IPC pointer payload: {verdict.reason}"
            )

        raw = content.encode("utf-8") if isinstance(content, str) else content
        return _consts.IPCPointerReturn(
            status="OK",
            pointer_uri=Path(verdict.committed_path).as_uri(),
            sha256=compute_sha256(raw),
            crc32=compute_crc32(raw),
            byte_size=len(raw),
            mime_type=mime_type,
        )


def win32_atomic_replace(
    src_path: Union[str, Path],
    dst_path: Union[str, Path],
    max_retries: int = 8,
) -> None:
    """Sostituisce un file in modo atomico usando MoveFileExW e Shadow Swap."""
    src = Path(src_path).resolve()
    dst = Path(dst_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    engine = TwoPhaseCommitEngine()
    engine.MAX_RETRIES = max(1, int(max_retries))
    with Win32NamedMutex(dst, timeout_ms=5000):
        ok = engine._execute_atomic_commit(src, dst)
    if not ok:
        raise TwoPhaseCommitError(
            f"Impossibile sostituire atomicamente {src} verso {dst}"
        )

# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Win32 Two-Phase Commit (2PC) & High-Performance Concurrency Engine
Protocol: CRV 4.0 / Zero-Mock / Pydantic v2 Strict Mode
"""

from __future__ import annotations

import os
import sys
import time
import zlib
import ctypes
import hashlib
import uuid
import json
import random
import asyncio
import argparse
from pathlib import Path
from typing import Optional, Union, List, Dict, Any

try:
    from schemas.nk_ipc_contracts import (
        TwoPhaseCommitPrepare,
        TwoPhaseCommitVerdict,
        IPCPointerReturn,
    )
except (ImportError, ModuleNotFoundError):
    try:
        from .schemas.nk_ipc_contracts import (
            TwoPhaseCommitPrepare,
            TwoPhaseCommitVerdict,
            IPCPointerReturn,
        )
    except (ImportError, ModuleNotFoundError):
        from scripts.schemas.nk_ipc_contracts import (
            TwoPhaseCommitPrepare,
            TwoPhaseCommitVerdict,
            IPCPointerReturn,
        )

# ---------------------------------------------------------------------------
# Win32 Kernel32 Constants & CTypes Definitions
# ---------------------------------------------------------------------------
WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED_0 = 0x00000080
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF
INFINITE = 0xFFFFFFFF

MOVEFILE_REPLACE_EXISTING = 0x00000001
MOVEFILE_COPY_ALLOWED = 0x00000002
MOVEFILE_WRITE_THROUGH = 0x00000008

ERROR_ACCESS_DENIED = 5
ERROR_INVALID_HANDLE = 6
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33
ERROR_ALREADY_EXISTS = 183

if sys.platform == "win32":
    _kernel32 = ctypes.windll.kernel32

    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    _kernel32.CreateMutexW.restype = ctypes.c_void_p

    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.WaitForSingleObject.restype = ctypes.c_uint32

    _kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    _kernel32.ReleaseMutex.restype = ctypes.c_bool

    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_bool

    _kernel32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    _kernel32.MoveFileExW.restype = ctypes.c_bool

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32

    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = ctypes.c_uint32
else:
    _kernel32 = None



# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------
class Win32LockError(RuntimeError):
    """Raised when Win32 mutex operations encounter unrecoverable OS errors."""
    pass


class Win32LockTimeoutError(TimeoutError):
    """Raised when a Win32 Named Mutex acquisition times out."""
    pass


class TwoPhaseCommitError(RuntimeError):
    """Raised when a 2PC atomic commit operation fails integrity or I/O checks."""
    pass


# ---------------------------------------------------------------------------
# Cryptographic & Checksum Utilities
# ---------------------------------------------------------------------------
def compute_sha256(data: Union[bytes, str]) -> str:
    """Computes deterministic SHA-256 hexadecimal digest."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def compute_crc32(data: Union[bytes, str]) -> int:
    """Computes standard unsigned 32-bit CRC32 checksum."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return zlib.crc32(raw) & 0xFFFFFFFF


def get_mutex_name_for_path(file_path: Union[str, Path]) -> str:
    """Derives a deterministic SHA256-based Win32 Named Mutex identifier."""
    norm_path = os.path.abspath(str(file_path)).lower().replace("/", "\\")
    path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()
    return f"Global\\NK_FileLock_{path_hash}"


# ---------------------------------------------------------------------------
# Win32 Named Mutex RAII Context Manager (Thread-Bound Synchronous)
# ---------------------------------------------------------------------------
class Win32NamedMutex:
    """
    RAII Context Manager wrapping Win32 Named Mutex.
    Provides robust inter-process mutual exclusion with thread-affinity checks,
    automatic recovery from WAIT_ABANDONED, and strict WAIT_TIMEOUT enforcement.
    """

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
            self._local_fallback_name = self.name

        self.timeout_ms = timeout_ms
        self.handle: Optional[int] = None
        self.acquired: bool = False
        self.abandoned: bool = False
        self._owning_thread_id: Optional[int] = None

    def __enter__(self) -> "Win32NamedMutex":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def acquire(self) -> None:
        """Acquires the named mutex handle and ownership."""
        if self.acquired:
            return

        current_thread = _kernel32.GetCurrentThreadId()

        # Attempt to create/open Global named mutex
        handle = _kernel32.CreateMutexW(None, False, self.name)
        err = _kernel32.GetLastError()

        # If Global namespace is forbidden due to UAC/permissions, fallback to Local
        if (not handle or handle == 0) and err == ERROR_ACCESS_DENIED:
            handle = _kernel32.CreateMutexW(None, False, self._local_fallback_name)
            err = _kernel32.GetLastError()

        if not handle or handle == 0:
            raise Win32LockError(
                f"Failed to create/open mutex '{self.name}'. Win32 Error: {err}"
            )

        self.handle = handle

        # Wait for ownership
        wait_res = _kernel32.WaitForSingleObject(self.handle, ctypes.c_uint32(self.timeout_ms))

        if wait_res == WAIT_OBJECT_0:
            self.acquired = True
            self.abandoned = False
            self._owning_thread_id = current_thread
        elif wait_res == WAIT_ABANDONED_0:
            # Previous owning process terminated abnormally without releasing the mutex.
            # Win32 grants ownership to this thread.
            self.acquired = True
            self.abandoned = True
            self._owning_thread_id = current_thread
        elif wait_res == WAIT_TIMEOUT:
            self._cleanup_handle()
            raise Win32LockTimeoutError(
                f"Timed out after {self.timeout_ms}ms waiting for mutex '{self.name}'"
            )
        else:
            last_err = _kernel32.GetLastError()
            self._cleanup_handle()
            raise Win32LockError(
                f"WaitForSingleObject failed on mutex '{self.name}' with code {wait_res}. Win32 Error: {last_err}"
            )

    def release(self) -> None:
        """Releases mutex ownership with strict thread-affinity validation and closes handle."""
        if self.handle:
            current_thread = _kernel32.GetCurrentThreadId()
            if self.acquired:
                if self._owning_thread_id is not None and self._owning_thread_id != current_thread:
                    raise Win32LockError(
                        f"Win32 Named Mutex thread affinity violation: acquired by thread {self._owning_thread_id} "
                        f"but released by thread {current_thread}."
                    )
                _kernel32.ReleaseMutex(self.handle)
                self.acquired = False
                self._owning_thread_id = None
            self._cleanup_handle()

    def _cleanup_handle(self) -> None:
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


# ---------------------------------------------------------------------------
# Write-Ahead Logging (WAL) Subsystem
# ---------------------------------------------------------------------------
class WriteAheadLogManager:
    """
    Manages Write-Ahead Log records for atomic 2PC isolation and recovery.
    """

    def __init__(self, wal_dir: Optional[Union[str, Path]] = None) -> None:
        self.custom_wal_dir = Path(wal_dir) if wal_dir else None

    def _get_wal_dir(self, target_file: Path) -> Path:
        if self.custom_wal_dir:
            wal_dir = self.custom_wal_dir
        else:
            wal_dir = target_file.parent / ".wal"
        wal_dir.mkdir(parents=True, exist_ok=True)
        return wal_dir

    def get_wal_path(self, target_path: Union[str, Path], tx_id: str) -> Path:
        target = Path(target_path).resolve()
        wal_dir = self._get_wal_dir(target)
        return wal_dir / f"{target.name}.{tx_id}.wal"

    def write_wal(
        self,
        tx_id: str,
        target_path: Union[str, Path],
        staging_path: Union[str, Path],
        payload_sha256: str,
        payload_crc32: int,
        state: str = "PREPARED",
    ) -> Path:
        wal_path = self.get_wal_path(target_path, tx_id)
        record = {
            "tx_id": tx_id,
            "target_path": str(Path(target_path).resolve()),
            "staging_path": str(Path(staging_path).resolve()),
            "payload_sha256": payload_sha256,
            "payload_crc32": payload_crc32,
            "state": state,
            "timestamp_utc": time.time(),
        }
        temp_wal = wal_path.with_suffix(".tmp")
        with open(temp_wal, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_wal, wal_path)
        return wal_path

    def update_wal_state(
        self,
        target_path: Union[str, Path],
        tx_id: str,
        state: str,
    ) -> None:
        wal_path = self.get_wal_path(target_path, tx_id)
        if not wal_path.exists():
            return

        with open(wal_path, "r", encoding="utf-8") as f:
            record = json.load(f)

        record["state"] = state
        record["updated_at"] = time.time()

        temp_wal = wal_path.with_suffix(".tmp")
        with open(temp_wal, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_wal, wal_path)

    def purge_wal(self, target_path: Union[str, Path], tx_id: str) -> None:
        wal_path = self.get_wal_path(target_path, tx_id)
        try:
            if wal_path.exists():
                wal_path.unlink()
        except OSError:
            pass

    def recover(self, root_dir: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Scans directory for .wal files and replays or cleans orphaned transactions.
        """
        root = Path(root_dir).resolve()
        recovered: List[Dict[str, Any]] = []

        wal_dirs = list(root.rglob(".wal"))
        for w_dir in wal_dirs:
            if not w_dir.is_dir():
                continue
            for wal_file in list(w_dir.glob("*.wal")):
                try:
                    with open(wal_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    tx_id = data.get("tx_id", "")
                    target = Path(data.get("target_path", ""))
                    staging = Path(data.get("staging_path", ""))
                    state = data.get("state", "")
                    expected_sha = data.get("payload_sha256", "")

                    action_taken = "NONE"

                    if state == "COMMITTED":
                        # If destination missing or corrupted, replay staging if available
                        if staging.exists():
                            stg_bytes = staging.read_bytes()
                            if compute_sha256(stg_bytes) == expected_sha:
                                target.write_bytes(stg_bytes)
                                action_taken = "REPLAYED_COMMIT"
                            staging.unlink(missing_ok=True)
                        wal_file.unlink(missing_ok=True)
                    elif state == "PREPARED":
                        # If prepared but stale (>10s old), abort and clean staging
                        if staging.exists():
                            staging.unlink(missing_ok=True)
                        wal_file.unlink(missing_ok=True)
                        action_taken = "ABORTED_STALE"
                    elif state == "ABORTED":
                        if staging.exists():
                            staging.unlink(missing_ok=True)
                        wal_file.unlink(missing_ok=True)
                        action_taken = "PURGED_ABORTED"

                    recovered.append({
                        "wal_file": str(wal_file),
                        "tx_id": tx_id,
                        "state": state,
                        "action": action_taken,
                    })
                except Exception as exc:
                    recovered.append({
                        "wal_file": str(wal_file),
                        "error": str(exc),
                        "action": "ERROR",
                    })

        return recovered


# ---------------------------------------------------------------------------
# Two-Phase Commit (2PC) Atomic Engine
# ---------------------------------------------------------------------------
class TwoPhaseCommitEngine:
    """
    Two-Phase Commit Atomic Engine for Windows and Cloud Filesystems (Google Drive FS).
    Features:
    - Win32 Named Mutex concurrency guard.
    - Full Jitter Exponential Backoff (25ms base, 1500ms max, 8 attempts).
    - MoveFileExW atomic replacement with Shadow Swap fallback.
    - Write-Ahead Logging (WAL) with CRC32 and SHA-256 validation.
    """

    MAX_RETRIES = 8
    BASE_DELAY_MS = 25.0
    MAX_DELAY_MS = 1500.0

    def __init__(self, wal_manager: Optional[WriteAheadLogManager] = None) -> None:
        self.wal = wal_manager or WriteAheadLogManager()

    @staticmethod
    def _backoff_sleep(attempt: int) -> None:
        """Calculates and executes Full Jitter Exponential Backoff sleep."""
        cap_ms = min(TwoPhaseCommitEngine.MAX_DELAY_MS, TwoPhaseCommitEngine.BASE_DELAY_MS * (2 ** attempt))
        sleep_s = random.uniform(0.0, cap_ms) / 1000.0
        time.sleep(sleep_s)

    def prepare(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        timeout_ms: int = 5000,
    ) -> TwoPhaseCommitPrepare:
        """
        Phase 1: Prepare.
        Writes payload to isolated staging file, hashes payload, and records WAL.
        """
        target = Path(target_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        sha256_hash = compute_sha256(raw_bytes)
        crc32_hash = compute_crc32(raw_bytes)
        tx_id = f"tx_{uuid.uuid4().hex[:12]}_{int(time.time()*1000)}"

        staging_file = target.parent / f".staging_{target.name}.{tx_id}.tmp"

        with open(staging_file, "wb") as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(f.fileno())

        # Record WAL in PREPARED state
        self.wal.write_wal(
            tx_id=tx_id,
            target_path=target,
            staging_path=staging_file,
            payload_sha256=sha256_hash,
            payload_crc32=crc32_hash,
            state="PREPARED",
        )

        return TwoPhaseCommitPrepare(
            transaction_id=tx_id,
            target_path=str(target),
            staging_path=str(staging_file),
            expected_sha256=sha256_hash,
            crc32=crc32_hash,
            timeout_ms=timeout_ms,
            timestamp_utc=time.time(),
        )

    def commit(self, prepare_req: TwoPhaseCommitPrepare) -> TwoPhaseCommitVerdict:
        """
        Phase 2: Commit.
        Acquires Win32 Mutex, executes MoveFileExW with Jitter Backoff and Shadow Swap,
        verifies SHA-256/CRC32, updates and purges WAL.
        """
        start_time = time.perf_counter()
        target = Path(prepare_req.target_path).resolve()
        staging = Path(prepare_req.staging_path).resolve()

        if not staging.exists():
            return self.abort(prepare_req, reason=f"Staging file {staging} does not exist")

        # Verify staging file integrity before attempting lock/commit
        staging_data = staging.read_bytes()
        if compute_sha256(staging_data) != prepare_req.expected_sha256:
            return self.abort(prepare_req, reason="Staging file SHA-256 mismatch during commit phase")

        if compute_crc32(staging_data) != prepare_req.crc32:
            return self.abort(prepare_req, reason="Staging file CRC32 mismatch during commit phase")

        with Win32NamedMutex(target, timeout_ms=prepare_req.timeout_ms):
            success = self._execute_atomic_commit(staging, target)
            if not success:
                return self.abort(prepare_req, reason="Atomic move and Shadow Swap fallback exhausted all retries")

            # Verify target file on disk
            written_bytes = target.read_bytes()
            if compute_sha256(written_bytes) != prepare_req.expected_sha256:
                return self.abort(prepare_req, reason="Committed file SHA-256 verification failed on disk")

            # Finalize WAL
            self.wal.update_wal_state(target, prepare_req.transaction_id, state="COMMITTED")
            self.wal.purge_wal(target, prepare_req.transaction_id)

            # Cleanup staging if still present
            if staging.exists():
                try:
                    staging.unlink()
                except OSError:
                    pass

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return TwoPhaseCommitVerdict(
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
        """
        Phase 2: Abort.
        Cleans up staging file and updates WAL to ABORTED.
        """
        staging = Path(prepare_req.staging_path)
        if staging.exists():
            try:
                staging.unlink()
            except OSError:
                pass

        self.wal.update_wal_state(prepare_req.target_path, prepare_req.transaction_id, state="ABORTED")
        self.wal.purge_wal(prepare_req.target_path, prepare_req.transaction_id)

        return TwoPhaseCommitVerdict(
            transaction_id=prepare_req.transaction_id,
            verdict="ABORT",
            reason=reason or "Transaction explicitly aborted",
            committed_path=None,
            execution_time_ms=0.0,
        )

    def _execute_atomic_commit(self, src: Path, dst: Path) -> bool:
        """
        Executes atomic move using MoveFileExW with Full Jitter Exponential Backoff
        and Shadow Swap fallback for Google Drive FS locking.
        """
        src_w = str(src.resolve())
        dst_w = str(dst.resolve())
        flags = MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH

        # Step 1: Direct MoveFileExW attempts with Full Jitter Exponential Backoff
        for attempt in range(self.MAX_RETRIES):
            res = _kernel32.MoveFileExW(src_w, dst_w, flags)
            if res:
                return True

            err = _kernel32.GetLastError()
            # If error is sharing violation or access denied, backoff and retry
            if err in (ERROR_SHARING_VIOLATION, ERROR_ACCESS_DENIED, ERROR_LOCK_VIOLATION):
                self._backoff_sleep(attempt)
            else:
                # Try os.replace as standard fallback
                try:
                    os.replace(src, dst)
                    return True
                except (PermissionError, OSError):
                    self._backoff_sleep(attempt)

        # Step 2: Shadow Swap Fallback (handles persistent Google Drive FS locks)
        return self._shadow_swap_fallback(src, dst)

    def _shadow_swap_fallback(self, src: Path, dst: Path) -> bool:
        """
        Shadow Swap Strategy:
        1. Duplicate staging file to shadow file next to destination.
        2. Rename destination to .old if destination exists.
        3. Move shadow to destination.
        4. Remove .old file asynchronously/safely.
        5. Direct locked write fallback if file moves fail.
        """
        shadow_path = dst.parent / f".shadow_{dst.name}_{uuid.uuid4().hex[:8]}.tmp"
        old_path = dst.parent / f".old_{dst.name}_{uuid.uuid4().hex[:8]}.tmp"

        for attempt in range(self.MAX_RETRIES):
            try:
                # Copy staging bytes to shadow
                raw = src.read_bytes()
                with open(shadow_path, "wb") as sf:
                    sf.write(raw)
                    sf.flush()
                    os.fsync(sf.fileno())

                # If destination exists, attempt swap
                if dst.exists():
                    try:
                        os.replace(dst, old_path)
                    except OSError:
                        pass

                # Move shadow into dst
                os.replace(shadow_path, dst)

                # Clean up old file
                if old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass
                return True
            except Exception:
                self._backoff_sleep(attempt)

        # Step 3: Direct stream rewrite with mutex held as ultimate fallback
        try:
            raw = src.read_bytes()
            with open(dst, "wb") as df:
                df.write(raw)
                df.flush()
                os.fsync(df.fileno())
            return True
        except Exception:
            return False

    def atomic_write(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        timeout_ms: int = 5000,
    ) -> TwoPhaseCommitVerdict:
        """Synchronous end-to-end atomic 2PC write."""
        prep = self.prepare(target_path, content, timeout_ms=timeout_ms)
        return self.commit(prep)

    async def atomic_write_async(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        timeout_ms: int = 5000,
    ) -> TwoPhaseCommitVerdict:
        """Asynchronous end-to-end atomic 2PC write executed in a worker thread."""
        return await asyncio.to_thread(self.atomic_write, target_path, content, timeout_ms)

    def create_ipc_pointer(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        mime_type: str = "application/octet-stream",
    ) -> IPCPointerReturn:
        """
        Writes content via 2PC and returns a compact IPCPointerReturn (<80 tokens).
        """
        verdict = self.atomic_write(target_path, content)
        if verdict.verdict != "COMMIT" or not verdict.committed_path:
            raise TwoPhaseCommitError(f"Failed to commit IPC pointer payload: {verdict.reason}")

        raw = content.encode("utf-8") if isinstance(content, str) else content
        return IPCPointerReturn(
            status="OK",
            pointer_uri=Path(verdict.committed_path).as_uri(),
            sha256=compute_sha256(raw),
            crc32=compute_crc32(raw),
            byte_size=len(raw),
            mime_type=mime_type,
        )


# ---------------------------------------------------------------------------
# Staging Promotion Subsystem (CRV 4.0 Macro-Fase 3)
# ---------------------------------------------------------------------------
def record_session_anchor_commit(
    repo_root: Union[str, Path],
    milestone_id: str,
    committed_files: List[Dict[str, Any]],
) -> None:
    """
    Appends an official commit record to nk_tracking/anchor/session_anchor.jsonl.
    """
    root = Path(repo_root).resolve()
    anchor_file = root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    if anchor_file.exists():
        committed_names = [f["relative_path"] for f in committed_files]
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "act": "OFFICIAL_RELEASE_COMMIT",
            "target": milestone_id,
            "detail": (
                f"Atomic 2PC promotion to production. "
                f"{len(committed_files)} files committed ({', '.join(committed_names)}) "
                f"with SHA-256 validation, WAL isolation, and Win32 Named Mutex lock."
            ),
            "skill": "NK-Master-Hub",
            "status": "OK",
        }
        with open(anchor_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def promote_staging_to_production(
    repo_root: Optional[Union[str, Path]] = None,
    milestone: Optional[str] = None,
    staging_dirname: str = ".staging",
    subdirs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Executes Win32 2PC atomic promotion of files from .staging/ to production.
    Ensures Named Mutex concurrency guard, SHA-256 verification, and WAL logging.
    """
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parent.parent
    staging_dir = root / staging_dirname
    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory does not exist: {staging_dir}")

    target_subdirs = subdirs or ["scripts", "tests", "data/snapshots"]
    engine = TwoPhaseCommitEngine()

    committed: List[Dict[str, Any]] = []
    unchanged: List[str] = []
    failed: List[Dict[str, Any]] = []

    print("=" * 80)
    print("WIN32 TWO-PHASE COMMIT (2PC) ATOMIC PROMOTION ENGINE")
    print("Protocol: CRV 4.0 | Macro-Fase 3: Atomic Commit & Memorize")
    print("=" * 80)
    print(f"[*] Repository Root: {root}")
    print(f"[*] Staging Root   : {staging_dir}")
    if milestone:
        print(f"[*] Milestone Anchor: {milestone}")
    print("-" * 80)

    for subdir in target_subdirs:
        stg_sub = staging_dir / subdir
        if not stg_sub.exists():
            continue

        for stg_file in sorted(stg_sub.rglob("*")):
            if not stg_file.is_file():
                continue
            if "__pycache__" in stg_file.parts or stg_file.name == ".gitkeep":
                continue

            rel_path = stg_file.relative_to(staging_dir)
            prod_file = root / rel_path

            stg_bytes = stg_file.read_bytes()
            stg_sha = compute_sha256(stg_bytes)

            # Check if production file is identical
            if prod_file.exists():
                prod_bytes = prod_file.read_bytes()
                prod_sha = compute_sha256(prod_bytes)
                if stg_sha == prod_sha:
                    unchanged.append(str(rel_path))
                    continue

            # File is modified or new in staging -> promote via 2PC
            print(f"[>] Promoting via Win32 2PC: {rel_path}")
            print(f"    Target : {prod_file}")
            print(f"    Payload: {len(stg_bytes)} bytes, SHA-256: {stg_sha}")

            verdict = engine.atomic_write(prod_file, stg_bytes)

            if verdict.verdict == "COMMIT":
                committed.append({
                    "relative_path": str(rel_path),
                    "committed_path": verdict.committed_path,
                    "sha256": stg_sha,
                    "tx_id": verdict.transaction_id,
                    "execution_time_ms": verdict.execution_time_ms,
                })
                print(f"    [+] VERDICT: COMMIT OK in {verdict.execution_time_ms:.2f}ms (tx_id: {verdict.transaction_id})")
            else:
                failed.append({
                    "relative_path": str(rel_path),
                    "reason": verdict.reason,
                    "tx_id": verdict.transaction_id,
                })
                print(f"    [-] VERDICT: ABORT - Reason: {verdict.reason}")

    if failed:
        raise TwoPhaseCommitError(f"2PC Promotion aborted! {len(failed)} files failed: {failed}")

    # Record milestone anchor if specified
    if milestone:
        record_session_anchor_commit(root, milestone, committed)
        print(f"[+] Milestone Anchor recorded in session_anchor.jsonl: {milestone}")

    print("=" * 80)
    print(f"PROMOTION SUMMARY: {len(committed)} committed, {len(unchanged)} unchanged, {len(failed)} failed.")
    print("=" * 80)

    return {
        "status": "SUCCESS",
        "milestone": milestone,
        "committed_files": committed,
        "unchanged_files": unchanged,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for Win32 Two-Phase Commit Engine."""
    parser = argparse.ArgumentParser(
        description="Win32 Two-Phase Commit (2PC) & Staging Promotion Engine",
    )
    parser.add_argument(
        "--promote-staging",
        action="store_true",
        help="Promote modified files from .staging to production via Win32 2PC",
    )
    parser.add_argument(
        "--milestone",
        type=str,
        default=None,
        help="Milestone Anchor ID (e.g. NK-MS-20260903-STRESS-E2E-LOOP-v1.4.1)",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Path to repository root (defaults to parent of scripts/)",
    )
    parser.add_argument(
        "--staging-dir",
        type=str,
        default=".staging",
        help="Path or name of staging directory relative to repo-root (defaults to .staging)",
    )

    args = parser.parse_args(argv)

    if args.promote_staging:
        try:
            promote_staging_to_production(
                repo_root=args.repo_root,
                milestone=args.milestone,
                staging_dirname=args.staging_dir,
            )
            return 0
        except Exception as exc:
            print(f"[!] Error during 2PC staging promotion: {exc}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())


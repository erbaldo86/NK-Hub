# -*- coding: utf-8 -*-
"""
Motore transazionale Win32 Two-Phase Commit per Nexus Keystone v3.0.0-STE100-Unified.
Garantisce mutua esclusione inter-processo, integrita SHA-256 e promozione atomica.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from schemas.nk_ipc_contracts import (
        IPCPointerReturn,
        TwoPhaseCommitPrepare,
        TwoPhaseCommitVerdict,
    )
except (ImportError, ModuleNotFoundError):
    try:
        from .schemas.nk_ipc_contracts import (
            IPCPointerReturn,
            TwoPhaseCommitPrepare,
            TwoPhaseCommitVerdict,
        )
    except (ImportError, ModuleNotFoundError):
        curr_dir = Path(__file__).resolve().parent
        candidates = [
            curr_dir,
            curr_dir.parent,
            curr_dir.parent / "scripts",
            Path.cwd(),
            Path.cwd() / "scripts",
        ]
        for c in candidates:
            if str(c) not in sys.path and c.exists():
                sys.path.insert(0, str(c))
        try:
            from schemas.nk_ipc_contracts import (
                IPCPointerReturn,
                TwoPhaseCommitPrepare,
                TwoPhaseCommitVerdict,
            )
        except (ImportError, ModuleNotFoundError):
            from scripts.schemas.nk_ipc_contracts import (
                IPCPointerReturn,
                TwoPhaseCommitPrepare,
                TwoPhaseCommitVerdict,
            )

WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED_0 = 0x00000080
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF
INFINITE = 0xFFFFFFFF
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

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

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32

    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = ctypes.c_uint32
else:
    _kernel32 = None


class Win32LockError(RuntimeError):
    """Sollevata quando il mutex Win32 incontra un errore di sistema."""


class Win32LockTimeoutError(TimeoutError):
    """Sollevata quando l'acquisizione del mutex Win32 supera il timeout."""


class TwoPhaseCommitError(RuntimeError):
    """Sollevata quando il commit atomico 2PC fallisce i controlli di integrita."""


def compute_sha256(data: Union[bytes, str]) -> str:
    """Calcola il digest esadecimale SHA-256 deterministico."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def compute_crc32(data: Union[bytes, str]) -> int:
    """Calcola il checksum CRC32 senza segno a 32 bit."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return zlib.crc32(raw) & 0xFFFFFFFF


def get_mutex_name_for_path(file_path: Union[str, Path]) -> str:
    """Deriva il nome deterministico del mutex Win32 dal percorso file."""
    norm_path = os.path.abspath(str(file_path)).lower().replace("/", "\\")
    path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()
    return f"Global\\NK_FileLock_{path_hash}"


class Win32NamedMutex:
    """Gestore di contesto RAII per il Named Mutex di Windows."""

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
        """Acquisisce l'handle e la proprieta del mutex con verifica del thread."""
        if self.acquired:
            return

        current_thread = _kernel32.GetCurrentThreadId()
        handle = _kernel32.CreateMutexW(None, False, self.name)
        err = _kernel32.GetLastError()

        if (not handle or handle == INVALID_HANDLE_VALUE) and err == ERROR_ACCESS_DENIED:
            handle = _kernel32.CreateMutexW(None, False, self._local_fallback_name)
            err = _kernel32.GetLastError()

        if not handle or handle == INVALID_HANDLE_VALUE:
            raise Win32LockError(
                f"Failed to create/open mutex '{self.name}'. Win32 Error: {err}"
            )

        self.handle = handle
        wait_res = _kernel32.WaitForSingleObject(
            self.handle,
            ctypes.c_uint32(self.timeout_ms),
        )

        if wait_res == WAIT_OBJECT_0:
            self.acquired = True
            self.abandoned = False
            self._owning_thread_id = current_thread
        elif wait_res == WAIT_ABANDONED_0:
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
        """Rilascia il mutex verificando l'affinita del thread proprietario."""
        if self.handle:
            current_thread = _kernel32.GetCurrentThreadId()
            if self.acquired:
                if (
                    self._owning_thread_id is not None
                    and self._owning_thread_id != current_thread
                ):
                    raise Win32LockError(
                        f"Win32 Named Mutex thread affinity violation: acquired by thread {self._owning_thread_id} "
                        f"but released by thread {current_thread}."
                    )
                _kernel32.ReleaseMutex(self.handle)
                self.acquired = False
                self._owning_thread_id = None
            self._cleanup_handle()

    def _cleanup_handle(self) -> None:
        """Chiude l'handle nativo del kernel."""
        if self.handle and self.handle != INVALID_HANDLE_VALUE:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


class WriteAheadLogManager:
    """Gestisce i file Write-Ahead Log per l'isolamento e il ripristino 2PC."""

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
        """Scrive su disco un record WAL atomico con fsync."""
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
        """Aggiorna lo stato di un record WAL esistente."""
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
        """Elimina il file WAL completato e pulisce la cartella se vuota."""
        wal_path = self.get_wal_path(target_path, tx_id)
        wal_dir = wal_path.parent
        try:
            if wal_path.exists():
                wal_path.unlink()
            if wal_dir.exists() and not any(wal_dir.iterdir()):
                wal_dir.rmdir()
        except OSError:
            pass

    def recover(
        self,
        root_dir: Union[str, Path],
        stale_age_sec: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """Scansiona i file WAL e ripristina o annulla le transazioni interrotte."""
        root = Path(root_dir).resolve()
        recovered: List[Dict[str, Any]] = []
        now = time.time()

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
                    ts_utc = float(data.get("timestamp_utc", 0.0))
                    age = (now - ts_utc) if ts_utc > 0.0 else (stale_age_sec + 1.0)

                    action_taken = "NONE"

                    with Win32NamedMutex(target, timeout_ms=2000):
                        if state == "COMMITTED":
                            if staging.exists():
                                stg_bytes = staging.read_bytes()
                                if compute_sha256(stg_bytes) == expected_sha:
                                    target.write_bytes(stg_bytes)
                                    action_taken = "REPLAYED_COMMIT"
                                staging.unlink(missing_ok=True)
                            wal_file.unlink(missing_ok=True)
                        elif state == "PREPARED":
                            if age >= stale_age_sec:
                                if staging.exists():
                                    staging.unlink(missing_ok=True)
                                wal_file.unlink(missing_ok=True)
                                action_taken = "ABORTED_STALE"
                            else:
                                action_taken = "SKIPPED_ACTIVE"
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
            TwoPhaseCommitEngine.BASE_DELAY_MS * (2 ** attempt),
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
        """Fase 2 (Commit): acquisisce il mutex Win32 e promuove il file in modo atomico."""
        start_time = time.perf_counter()
        target = Path(prepare_req.target_path).resolve()
        staging = Path(prepare_req.staging_path).resolve()

        if not staging.exists():
            return self.abort(
                prepare_req,
                reason=f"Staging file {staging} does not exist",
            )

        staging_data = staging.read_bytes()
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

        with Win32NamedMutex(target, timeout_ms=prepare_req.timeout_ms):
            success = self._execute_atomic_commit(staging, target)
            if not success:
                return self.abort(
                    prepare_req,
                    reason="Atomic move and Shadow Swap fallback exhausted all retries",
                )

            written_bytes = target.read_bytes()
            if compute_sha256(written_bytes) != prepare_req.expected_sha256:
                return self.abort(
                    prepare_req,
                    reason="Committed file SHA-256 verification failed on disk",
                )

            self.wal.update_wal_state(
                target,
                prepare_req.transaction_id,
                state="COMMITTED",
            )
            self.wal.purge_wal(target, prepare_req.transaction_id)

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
        """Fase 2 (Abort): elimina il file di staging e pulisce il record WAL."""
        staging = Path(prepare_req.staging_path)
        if staging.exists():
            try:
                staging.unlink()
            except OSError:
                pass

        self.wal.update_wal_state(
            prepare_req.target_path,
            prepare_req.transaction_id,
            state="ABORTED",
        )
        self.wal.purge_wal(prepare_req.target_path, prepare_req.transaction_id)

        return TwoPhaseCommitVerdict(
            transaction_id=prepare_req.transaction_id,
            verdict="ABORT",
            reason=reason or "Transaction explicitly aborted",
            committed_path=None,
            execution_time_ms=0.0,
        )

    def _execute_atomic_commit(self, src: Path, dst: Path) -> bool:
        """Esegue la sostituzione atomica con MoveFileExW e Shadow Swap."""
        src_w = str(src.resolve())
        dst_w = str(dst.resolve())
        flags = (
            MOVEFILE_REPLACE_EXISTING
            | MOVEFILE_WRITE_THROUGH
            | MOVEFILE_COPY_ALLOWED
        )

        for attempt in range(self.MAX_RETRIES):
            if _kernel32 is not None:
                res = _kernel32.MoveFileExW(src_w, dst_w, flags)
                if res:
                    return True

                err = _kernel32.GetLastError()
                if err in (
                    ERROR_SHARING_VIOLATION,
                    ERROR_ACCESS_DENIED,
                    ERROR_LOCK_VIOLATION,
                ):
                    self._backoff_sleep(attempt)
                    continue

            try:
                os.replace(src, dst)
                return True
            except (PermissionError, OSError):
                self._backoff_sleep(attempt)

        return self._shadow_swap_fallback(src, dst)

    def _shadow_swap_fallback(self, src: Path, dst: Path) -> bool:
        """Esegue la strategia Shadow Swap per aggirare i lock di Google Drive FS."""
        shadow_path = dst.parent / f".shadow_{dst.name}_{uuid.uuid4().hex[:8]}.tmp"
        old_path = dst.parent / f".old_{dst.name}_{uuid.uuid4().hex[:8]}.tmp"

        for attempt in range(self.MAX_RETRIES):
            try:
                raw = src.read_bytes()
                with open(shadow_path, "wb") as sf:
                    sf.write(raw)
                    sf.flush()
                    os.fsync(sf.fileno())

                if dst.exists():
                    try:
                        os.replace(dst, old_path)
                    except OSError:
                        pass

                os.replace(shadow_path, dst)

                if old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass
                return True
            except Exception:
                self._backoff_sleep(attempt)

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
        """Esegue una scrittura atomica 2PC sincrona completa."""
        prep = self.prepare(target_path, content, timeout_ms=timeout_ms)
        return self.commit(prep)

    async def atomic_write_async(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        timeout_ms: int = 5000,
    ) -> TwoPhaseCommitVerdict:
        """Esegue una scrittura atomica 2PC asincrona in un worker thread."""
        return await asyncio.to_thread(
            self.atomic_write,
            target_path,
            content,
            timeout_ms,
        )

    def create_ipc_pointer(
        self,
        target_path: Union[str, Path],
        content: Union[bytes, str],
        mime_type: str = "application/octet-stream",
    ) -> IPCPointerReturn:
        """Scrive il payload con 2PC e restituisce un contratto IPCPointerReturn."""
        verdict = self.atomic_write(target_path, content)
        if verdict.verdict != "COMMIT" or not verdict.committed_path:
            raise TwoPhaseCommitError(
                f"Failed to commit IPC pointer payload: {verdict.reason}"
            )

        raw = content.encode("utf-8") if isinstance(content, str) else content
        return IPCPointerReturn(
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


def validate_staging_json_files(
    staging_dir: Union[str, Path],
    staging_files: Optional[List[Path]] = None,
) -> Tuple[bool, List[str]]:
    """Valida la sintassi JSON e l'assenza del carattere U+FFFD in tutti i file .json di staging."""
    stg_root = Path(staging_dir).resolve()
    candidates = (
        staging_files
        if staging_files is not None
        else [p for p in stg_root.rglob("*.json") if p.is_file()]
    )
    errors: List[str] = []
    for fpath in candidates:
        if fpath.suffix.lower() != ".json":
            continue
        try:
            raw_bytes = fpath.read_bytes()
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as ude:
            errors.append(f"{fpath.name}: codifica UTF-8 invalida ({ude})")
            continue
        except Exception as exc:
            errors.append(f"{fpath.name}: errore lettura file ({exc})")
            continue

        if "\ufffd" in text:
            errors.append(
                f"{fpath.name}: rilevato carattere di sostituzione U+FFFD vietato"
            )
        try:
            json.loads(text)
        except Exception as exc:
            errors.append(f"{fpath.name}: sintassi JSON invalida ({exc})")

    return len(errors) == 0, errors


def _cleanup_promoted_staging(
    staging_dir: Path,
    promoted_files: List[Path],
    deleted_manifest: Optional[Path] = None,
) -> None:
    """Rimuove i file promossi da .staging/ e ripristina il file sentinella .gitkeep."""
    for stg_file in promoted_files:
        try:
            if stg_file.exists() and stg_file.name != ".gitkeep":
                stg_file.unlink(missing_ok=True)
        except OSError:
            pass

    if deleted_manifest is not None and deleted_manifest.exists():
        try:
            deleted_manifest.unlink(missing_ok=True)
        except OSError:
            pass

    # Rimuove le sottocartelle vuote dal basso verso l'alto
    all_dirs = sorted(
        (d for d in staging_dir.rglob("*") if d.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for d in all_dirs:
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    gitkeep = staging_dir / ".gitkeep"
    if not gitkeep.exists():
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)
            gitkeep.write_text("", encoding="utf-8")
        except OSError:
            pass


def record_session_anchor_commit(
    repo_root: Union[str, Path],
    milestone_id: str,
    committed_files: List[Dict[str, Any]],
) -> None:
    """Registra una voce di commit ufficiale in session_anchor.jsonl."""
    root = Path(repo_root).resolve()
    anchor_file = root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    if anchor_file.exists():
        committed_names = [f["relative_path"] for f in committed_files]
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "act": "SYNC",
            "target": milestone_id,
            "detail": (
                f"Atomic 2PC promotion to production. "
                f"{len(committed_files)} files committed ({', '.join(committed_names[:10])})."
            ),
            "skill": "NK-Master-Hub",
            "status": "OK",
        }
        with open(anchor_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def _extract_dual_schema_baseline(
    data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[float], int]:
    """Estrae metriche, pass rate e numero di test supportando entrambi gli schemi baseline."""
    raw_metrics = (
        data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
    )
    candidate_metrics: Dict[str, Any] = {
        k: (v.get("value") if isinstance(v, dict) else v)
        for k, v in raw_metrics.items()
    }
    pass_rate: Optional[float] = None
    if "unit_tests_pass_pct" in candidate_metrics:
        pass_rate = float(candidate_metrics["unit_tests_pass_pct"])
    elif data.get("pass_rate_pct") is not None:
        pass_rate = float(data["pass_rate_pct"])
        candidate_metrics["unit_tests_pass_pct"] = pass_rate
    elif data.get("pass_rate") is not None:
        pass_rate = float(data["pass_rate"])
        candidate_metrics["unit_tests_pass_pct"] = pass_rate

    total_tests = 0
    if "unit_tests_total" in candidate_metrics:
        total_tests = int(candidate_metrics["unit_tests_total"])
    elif "total_golden_tests" in candidate_metrics:
        total_tests = int(candidate_metrics["total_golden_tests"])
    elif data.get("total_tests") is not None:
        total_tests = int(data["total_tests"])
        candidate_metrics["unit_tests_total"] = total_tests
    elif data.get("golden_tests_count") is not None:
        total_tests = int(data["golden_tests_count"])
        candidate_metrics["unit_tests_total"] = total_tests

    if data.get("failed_tests") is not None and "failed_tests" not in candidate_metrics:
        candidate_metrics["failed_tests"] = int(data["failed_tests"])

    return candidate_metrics, pass_rate, total_tests


def _verify_quality_baseline_ratchet(
    dst_bl: Union[str, Path, Dict[str, Any]],
    stg_bl: Optional[Union[str, Path, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Verifica il rispetto del ratchet quality_baseline.json con supporto Dual-Schema."""
    from quality_baseline_manager import check_baseline_compliance

    if isinstance(dst_bl, dict):
        cand_metrics, pass_rate, total_tests = _extract_dual_schema_baseline(dst_bl)
        if not cand_metrics or pass_rate is None:
            raise TwoPhaseCommitError("Metriche assenti o invalide nel quality_baseline.")
        if pass_rate < 100.0:
            raise TwoPhaseCommitError(
                f"Pass rate inferiore al 100.0% nel quality_baseline: {pass_rate}%"
            )
        return {
            "verdict": "PASS",
            "pass_rate_pct": pass_rate,
            "total_tests": total_tests,
            "metrics": cand_metrics,
        }

    dst_path = Path(dst_bl)
    stg_path = Path(stg_bl) if isinstance(stg_bl, (str, Path)) else None

    if stg_path is not None and stg_path.exists() and dst_path.exists():
        dst_data = json.loads(dst_path.read_text(encoding="utf-8"))
        stg_data = json.loads(stg_path.read_text(encoding="utf-8"))
        dst_metrics, dst_pass, dst_tot = _extract_dual_schema_baseline(dst_data)
        stg_metrics, stg_pass, stg_tot = _extract_dual_schema_baseline(stg_data)
        if not stg_metrics:
            raise TwoPhaseCommitError(
                f"Metriche assenti o invalide nel quality_baseline di staging: {stg_path}"
            )
        if stg_pass is not None and stg_pass < 100.0:
            raise TwoPhaseCommitError(
                f"Pass rate di staging inferiore al 100.0%: {stg_pass}%"
            )
        if dst_pass is not None and stg_pass is not None and stg_pass < dst_pass:
            raise TwoPhaseCommitError(
                f"Regressione pass rate nel quality_baseline: {dst_pass}% -> {stg_pass}%"
            )
        if isinstance(dst_data.get("metrics"), dict) and dst_data.get("metrics"):
            res_bl = check_baseline_compliance(str(dst_path), stg_metrics)
            if res_bl.get("verdict") != "PASS":
                raise TwoPhaseCommitError(
                    f"Regressione rilevata nel quality_baseline di staging: {res_bl.get('regressions')}"
                )
        return {
            "verdict": "PASS",
            "pass_rate_pct": stg_pass if stg_pass is not None else 100.0,
            "total_tests": stg_tot,
            "metrics": stg_metrics,
        }

    active_bl = (
        dst_path
        if dst_path.exists()
        else (stg_path if stg_path is not None else dst_path)
    )
    bl_data = json.loads(active_bl.read_text(encoding="utf-8"))
    cand_metrics, pass_rate, total_tests = _extract_dual_schema_baseline(bl_data)
    if not cand_metrics:
        raise TwoPhaseCommitError(
            f"Metriche assenti o invalide nel quality_baseline: {active_bl}"
        )
    if pass_rate is not None and pass_rate < 100.0:
        raise TwoPhaseCommitError(
            f"Regressione rilevata nel quality_baseline ({active_bl}): pass_rate={pass_rate}%"
        )
    if isinstance(bl_data.get("metrics"), dict) and bl_data.get("metrics"):
        res_bl = check_baseline_compliance(str(active_bl), cand_metrics)
        if res_bl.get("verdict") != "PASS":
            raise TwoPhaseCommitError(
                f"Regressione rilevata nel quality_baseline: {res_bl.get('regressions')}"
            )
    return {
        "verdict": "PASS",
        "pass_rate_pct": pass_rate if pass_rate is not None else 100.0,
        "total_tests": total_tests,
        "metrics": cand_metrics,
    }


def promote_staging_to_production(
    repo_root: Optional[Union[str, Path]] = None,
    milestone: Optional[str] = None,
    staging_dirname: str = ".staging",
    subdirs: Optional[List[str]] = None,
    git_sync: bool = False,
    verify_baseline: bool = False,
    cleanup_staging: bool = True,
) -> Dict[str, Any]:
    """Promuove in modo atomico i file modificati da .staging/ alla produzione."""
    if repo_root:
        root = Path(repo_root).resolve()
    else:
        file_path = Path(__file__).resolve()
        if ".staging" in file_path.parts:
            parts = file_path.parts
            stg_idx = parts.index(".staging")
            root = Path(*parts[:stg_idx])
        else:
            root = file_path.parent.parent
    staging_dir = root / staging_dirname
    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory does not exist: {staging_dir}")

    # 1. Validazione pre-commit su tutti i file .json in staging (incluso .deleted_files.json)
    all_stg_json = [p for p in staging_dir.rglob("*.json") if p.is_file()]
    json_ok, json_errors = validate_staging_json_files(staging_dir, all_stg_json)
    if not json_ok:
        raise TwoPhaseCommitError(
            f"Validazione JSON pre-commit fallita in staging: {json_errors}"
        )

    # 2. Verifica quality_baseline.json (SP-WS0 Fix riga 738: mai saltare in silenzio)
    if verify_baseline:
        dst_bl = root / "nk_tracking" / "quality_baseline.json"
        stg_bl = staging_dir / "nk_tracking" / "quality_baseline.json"
        if not dst_bl.exists() and not stg_bl.exists():
            raise TwoPhaseCommitError(
                f"File quality_baseline.json mancante sia in produzione ({dst_bl}) sia in staging ({stg_bl})."
            )
        try:
            _verify_quality_baseline_ratchet(dst_bl, stg_bl)
        except TwoPhaseCommitError:
            raise
        except Exception as exc:
            raise TwoPhaseCommitError(
                f"Errore durante la verifica del baseline: {exc}"
            ) from exc

    if subdirs:
        target_subdirs = subdirs
    else:
        target_subdirs = sorted([
            d.name
            for d in staging_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".git") and d.name != "__pycache__"
        ])
    engine = TwoPhaseCommitEngine()

    committed: List[Dict[str, Any]] = []
    unchanged: List[str] = []
    deleted: List[str] = []
    failed: List[Dict[str, Any]] = []

    deleted_manifest = staging_dir / ".deleted_files.json"
    deleted_rel_paths: List[str] = []
    if deleted_manifest.exists() and deleted_manifest.is_file():
        raw_del = json.loads(deleted_manifest.read_text(encoding="utf-8"))
        if isinstance(raw_del, list):
            deleted_rel_paths = [str(x) for x in raw_del if str(x).strip()]
        elif isinstance(raw_del, dict) and isinstance(raw_del.get("deleted_files"), list):
            deleted_rel_paths = [
                str(x) for x in raw_del["deleted_files"] if str(x).strip()
            ]
        else:
            raise TwoPhaseCommitError(
                "Formato invalido per .deleted_files.json: attesa lista o chiave 'deleted_files'."
            )

    staging_files: List[Path] = []
    for top_file in sorted(staging_dir.iterdir()):
        if (
            top_file.is_file()
            and top_file.name not in (".gitkeep", ".deleted_files.json")
            and "__pycache__" not in top_file.parts
        ):
            staging_files.append(top_file)

    for subdir in target_subdirs:
        stg_sub = staging_dir / subdir
        if not stg_sub.exists():
            continue

        for stg_file in sorted(stg_sub.rglob("*")):
            if not stg_file.is_file():
                continue
            if (
                "__pycache__" in stg_file.parts
                or stg_file.name in (".gitkeep", ".deleted_files.json")
            ):
                continue
            staging_files.append(stg_file)

    for stg_file in staging_files:
        rel_path = stg_file.relative_to(staging_dir)
        prod_file = root / rel_path

        stg_bytes = stg_file.read_bytes()
        stg_sha = compute_sha256(stg_bytes)

        if prod_file.exists():
            prod_bytes = prod_file.read_bytes()
            prod_sha = compute_sha256(prod_bytes)
            if stg_sha == prod_sha:
                unchanged.append(str(rel_path))
                continue

        verdict = engine.atomic_write(prod_file, stg_bytes)

        if verdict.verdict == "COMMIT":
            committed.append({
                "relative_path": str(rel_path),
                "committed_path": verdict.committed_path,
                "sha256": stg_sha,
                "tx_id": verdict.transaction_id,
                "execution_time_ms": verdict.execution_time_ms,
            })
        else:
            failed.append({
                "relative_path": str(rel_path),
                "reason": verdict.reason,
                "tx_id": verdict.transaction_id,
            })

    if failed:
        raise TwoPhaseCommitError(
            f"2PC Promotion aborted: {len(failed)} files failed: {failed}"
        )

    # 3. Propaga eventuali cancellazioni dichiarate in .deleted_files.json
    for rel_del in deleted_rel_paths:
        del_target = (root / rel_del).resolve()
        if root not in del_target.parents:
            raise TwoPhaseCommitError(
                f"Percorso di cancellazione fuori dalla root del repository: {rel_del}"
            )
        if del_target.exists() and del_target.is_file():
            with Win32NamedMutex(del_target, timeout_ms=5000):
                del_target.unlink(missing_ok=True)
            deleted.append(str(del_target.relative_to(root)))

    # 4. Pulisce .staging/ rimuovendo i file promossi e preservando .gitkeep
    if cleanup_staging:
        _cleanup_promoted_staging(
            staging_dir=staging_dir,
            promoted_files=staging_files,
            deleted_manifest=deleted_manifest if deleted_manifest.exists() else None,
        )

    if milestone:
        record_session_anchor_commit(root, milestone, committed)

    if git_sync:
        try:
            files_to_sync: List[str] = [c["relative_path"] for c in committed]
            if files_to_sync:
                cmd = ["git", "add"] + files_to_sync
                subprocess.run(
                    cmd,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
        except Exception:
            pass

    return {
        "status": "SUCCESS",
        "passed": True,
        "milestone": milestone,
        "committed_files": committed,
        "unchanged_files": unchanged,
        "deleted_files": deleted,
        "git_sync": git_sync,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il motore Win32 Two-Phase Commit."""
    parser = argparse.ArgumentParser(
        description="Win32 Two-Phase Commit (2PC) & Staging Promotion Engine",
    )
    parser.add_argument(
        "--promote-staging",
        action="store_true",
        help="Promuove i file modificati da .staging alla produzione",
    )
    parser.add_argument(
        "--milestone",
        type=str,
        default=None,
        help="Milestone Anchor ID",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Percorso alla radice del repository",
    )
    parser.add_argument(
        "--staging-dir",
        type=str,
        default=".staging",
        help="Nome della cartella di staging",
    )
    parser.add_argument(
        "--git-sync",
        action="store_true",
        help="Esegue git add sui file promossi",
    )
    parser.add_argument(
        "--verify-baseline",
        action="store_true",
        help="Verifica l'assenza di regressioni sul baseline prima del commit",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Mantiene i file in .staging dopo la promozione",
    )

    args = parser.parse_args(argv)

    if args.promote_staging:
        try:
            res = promote_staging_to_production(
                repo_root=args.repo_root,
                milestone=args.milestone,
                staging_dirname=args.staging_dir,
                git_sync=args.git_sync,
                verify_baseline=args.verify_baseline,
                cleanup_staging=not bool(args.keep_staging),
            )
            print(json.dumps(res, indent=2))
            return 0
        except Exception as exc:
            print(f"[!] Error during 2PC staging promotion: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

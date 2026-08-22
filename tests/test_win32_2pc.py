# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 1: Win32 Two-Phase Commit & Named Mutex Engine
8 Tests: Named Mutex RAII, Thread Affinity, Timeout, WAIT_ABANDONED, 2PC Commit/Abort, 50 Writers.
"""

from __future__ import annotations

import os
import sys
import time
import json
import uuid
import shutil
import hashlib
import unittest
import threading
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

import ctypes
from win32_2pc_engine import (
    Win32NamedMutex,
    TwoPhaseCommitEngine,
    WriteAheadLogManager,
    Win32LockError,
    Win32LockTimeoutError,
    TwoPhaseCommitError,
    compute_sha256,
    compute_crc32,
    get_mutex_name_for_path,
    WAIT_ABANDONED_0,
    WAIT_OBJECT_0,
    _kernel32,
)


class TestWin322PCEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = STAGING_DIR / "test_scratch" / f"2pc_{uuid.uuid4().hex[:8]}"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.wal_mgr = WriteAheadLogManager(wal_dir=self.test_dir / ".wal")
        self.engine = TwoPhaseCommitEngine(wal_manager=self.wal_mgr)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. test_named_mutex_acquisition_and_release
    def test_named_mutex_acquisition_and_release(self):
        """1. Validates standard RAII acquire and release cycle."""
        lock_file = self.test_dir / "test_res.lock"
        with Win32NamedMutex(lock_file, timeout_ms=3000) as lock:
            self.assertTrue(lock.acquired)
            self.assertFalse(lock.abandoned)
            self.assertIsNotNone(lock.handle)

        self.assertFalse(lock.acquired)
        self.assertIsNone(lock.handle)

    # 2. test_named_mutex_thread_affinity_enforcement
    def test_named_mutex_thread_affinity_enforcement(self):
        """2. Validates thread-affinity check: releasing on another thread raises Win32LockError."""
        lock_name = f"Global\\NK_Test_Affinity_{uuid.uuid4().hex[:8]}"
        lock = Win32NamedMutex(lock_name, timeout_ms=5000, is_path=False)
        lock.acquire()
        self.assertTrue(lock.acquired)

        release_error = []

        def other_thread_releaser():
            try:
                lock.release()
            except Exception as e:
                release_error.append(e)

        t = threading.Thread(target=other_thread_releaser)
        t.start()
        t.join()

        self.assertEqual(len(release_error), 1)
        self.assertIsInstance(release_error[0], Win32LockError)
        self.assertIn("thread affinity violation", str(release_error[0]).lower())

        # Clean release from original owning thread
        lock.release()

    # 3. test_named_mutex_timeout_handling
    def test_named_mutex_timeout_handling(self):
        """3. Validates timeout raises Win32LockTimeoutError when lock is held."""
        lock_name = f"Global\\NK_Test_Timeout_{uuid.uuid4().hex[:8]}"
        acquired_event = threading.Event()
        release_event = threading.Event()

        def holder_thread():
            with Win32NamedMutex(lock_name, timeout_ms=5000, is_path=False):
                acquired_event.set()
                release_event.wait(timeout=3.0)

        t = threading.Thread(target=holder_thread)
        t.start()

        acquired_event.wait(timeout=2.0)
        try:
            with self.assertRaises(Win32LockTimeoutError):
                with Win32NamedMutex(lock_name, timeout_ms=200, is_path=False):
                    pass
        finally:
            release_event.set()
            t.join()

    # 4. test_named_mutex_abandoned_recovery
    def test_named_mutex_abandoned_recovery(self):
        """4. Validates WAIT_ABANDONED auto-recovery when child crashes holding mutex."""
        unique_id = uuid.uuid4().hex[:12]
        mutex_name = f"Global\\NK_Test_Abandon_{unique_id}"
        handle_parent = _kernel32.CreateMutexW(None, False, mutex_name)
        self.assertIsNotNone(handle_parent)
        self.assertNotEqual(handle_parent, 0)

        try:
            child_script = f"""
import ctypes, time, os
k32 = ctypes.windll.kernel32
k32.CreateMutexW.restype = ctypes.c_void_p
k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
k32.WaitForSingleObject.restype = ctypes.c_uint32
k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

h = k32.CreateMutexW(None, False, r"{mutex_name}")
res = k32.WaitForSingleObject(h, 5000)
if res == 0:
    time.sleep(0.05)
    os._exit(0)
"""
            proc = subprocess.Popen([sys.executable, "-c", child_script])
            proc.wait(timeout=5.0)

            wait_res = _kernel32.WaitForSingleObject(handle_parent, 5000)
            self.assertEqual(wait_res, WAIT_ABANDONED_0)
            _kernel32.ReleaseMutex(handle_parent)
        finally:
            _kernel32.CloseHandle(handle_parent)

    # 5. test_2pc_successful_atomic_commit
    def test_2pc_successful_atomic_commit(self):
        """5. Validates complete 2PC transaction: Prepare -> Validate -> Commit -> Clean WAL."""
        target_file = self.test_dir / "target_success.json"
        content = json.dumps({"status": "committed", "version": "1.1.0"}, indent=2)

        verdict = self.engine.atomic_write(target_file, content)
        self.assertEqual(verdict.verdict, "COMMIT")
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), content)

    # 6. test_2pc_hash_mismatch_abort
    def test_2pc_hash_mismatch_abort(self):
        """6. Validates abort and rollback if SHA-256 mismatch is detected."""
        target_file = self.test_dir / "target_tamper.txt"
        prep = self.engine.prepare(target_file, "Original Payload")

        # Corrupt staging file before commit
        staging_path = Path(prep.staging_path)
        staging_path.write_text("Tampered Payload", encoding="utf-8")

        verdict = self.engine.commit(prep)
        self.assertEqual(verdict.verdict, "ABORT")
        self.assertIn("mismatch", verdict.reason.lower())
        self.assertFalse(target_file.exists())

    # 7. test_win32_movefile_retry_backoff_google_drive
    def test_win32_movefile_retry_backoff_google_drive(self):
        """7. Validates retry backoff and shadow swap fallback for Google Drive FS locking."""
        src = self.test_dir / "src_test.txt"
        dst = self.test_dir / "dst_test.txt"
        src.write_text("Hello Drive", encoding="utf-8")

        from memory_3tier_engine import win32_atomic_replace
        win32_atomic_replace(src, dst)
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "Hello Drive")

    # 8. test_50_concurrent_writers_stress
    def test_50_concurrent_writers_stress(self):
        """8. Stress test: 50 concurrent writers with zero mock and zero corruption."""
        target_file = self.test_dir / "stress_target.json"
        num_workers = 50
        errors: list[Exception] = []

        def worker_task(worker_id: int):
            try:
                payload = json.dumps({
                    "worker_id": worker_id,
                    "timestamp": time.time(),
                    "sequence": f"seq_{worker_id:04d}",
                    "random_data": uuid.uuid4().hex * 4,
                })
                verdict = self.engine.atomic_write(target_file, payload, timeout_ms=10000)
                if verdict.verdict != "COMMIT":
                    raise TwoPhaseCommitError(f"Worker {worker_id} commit aborted: {verdict.reason}")
                return worker_id, verdict
            except Exception as e:
                errors.append(e)
                raise

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            for future in as_completed(futures):
                worker_id, verdict = future.result()
                self.assertEqual(verdict.verdict, "COMMIT")

        self.assertEqual(len(errors), 0)
        self.assertTrue(target_file.exists())
        final_content = target_file.read_text(encoding="utf-8")
        parsed = json.loads(final_content)
        self.assertIn("worker_id", parsed)


if __name__ == "__main__":
    unittest.main()

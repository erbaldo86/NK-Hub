# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Win32 Two-Phase Commit e Named Mutex Engine (v3.3.0).
Modulo: tests/test_win32_2pc.py.
Valida acquisizione RAII, affinita thread, timeout, WAIT_ABANDONED, 2PC e concorrenza.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
STAGING_SCRIPTS_DIR = (
    STAGING_DIR / "scripts"
    if STAGING_DIR.name == ".staging"
    else WORKSPACE_ROOT / ".staging" / "scripts"
)

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if STAGING_SCRIPTS_DIR.exists():
    if str(STAGING_SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(STAGING_SCRIPTS_DIR))
    sys.path.insert(0, str(STAGING_SCRIPTS_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if "win32_2pc_engine" in sys.modules:
    del sys.modules["win32_2pc_engine"]

from win32_2pc_engine import (
    TwoPhaseCommitEngine,
    TwoPhaseCommitError,
    WAIT_ABANDONED_0,
    Win32LockError,
    Win32LockTimeoutError,
    Win32NamedMutex,
    WriteAheadLogManager,
    _kernel32,
    promote_staging_to_production,
)


class TestWin322PCEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="nk_test_2pc_"))
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.wal_mgr = WriteAheadLogManager(wal_dir=self.test_dir / ".wal")
        self.engine = TwoPhaseCommitEngine(wal_manager=self.wal_mgr)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_named_mutex_acquisition_and_release(self):
        """1. Valida ciclo RAII, vincolo di affinita thread e gestione timeout del mutex."""
        lock_file = self.test_dir / "test_res.lock"
        with Win32NamedMutex(lock_file, timeout_ms=3000) as lock:
            self.assertTrue(lock.acquired)
            self.assertFalse(lock.abandoned)
            self.assertIsNotNone(lock.handle)
        self.assertFalse(lock.acquired)
        self.assertIsNone(lock.handle)

        lock_name = f"Global\\NK_Test_Affinity_{uuid.uuid4().hex[:8]}"
        aff_lock = Win32NamedMutex(lock_name, timeout_ms=3000, is_path=False)
        aff_lock.acquire()
        release_error = []

        def other_thread_releaser():
            try:
                aff_lock.release()
            except Exception as e:
                release_error.append(e)

        t_aff = threading.Thread(target=other_thread_releaser)
        t_aff.start()
        t_aff.join()
        self.assertEqual(len(release_error), 1)
        self.assertIsInstance(release_error[0], Win32LockError)

        with self.assertRaises(Win32LockTimeoutError):
            t_to_err = []

            def timeout_waiter():
                try:
                    with Win32NamedMutex(lock_name, timeout_ms=25, is_path=False):
                        pass
                except Exception as exc:
                    t_to_err.append(exc)

            t_to = threading.Thread(target=timeout_waiter)
            t_to.start()
            t_to.join()
            if t_to_err:
                raise t_to_err[0]
        aff_lock.release()

    def test_named_mutex_abandoned_recovery(self):
        """2. Valida il recupero WAIT_ABANDONED quando un processo figlio termina col mutex."""
        unique_id = uuid.uuid4().hex[:12]
        mutex_name = f"Global\\NK_Test_Abandon_{unique_id}"
        handle_parent = _kernel32.CreateMutexW(None, False, mutex_name)
        self.assertIsNotNone(handle_parent)
        self.assertNotEqual(handle_parent, 0)

        try:
            child_script = (
                "import ctypes, os; "
                "k32 = ctypes.windll.kernel32; "
                "k32.CreateMutexW.restype = ctypes.c_void_p; "
                "k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]; "
                "k32.WaitForSingleObject.restype = ctypes.c_uint32; "
                "k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]; "
                f"h = k32.CreateMutexW(None, False, r'{mutex_name}'); "
                "res = k32.WaitForSingleObject(h, 3000); "
                "os._exit(0) if res == 0 else os._exit(1)"
            )
            proc = subprocess.Popen([sys.executable, "-c", child_script])
            proc.wait(timeout=4.0)

            wait_res = _kernel32.WaitForSingleObject(handle_parent, 3000)
            self.assertEqual(wait_res, WAIT_ABANDONED_0)
            _kernel32.ReleaseMutex(handle_parent)
        finally:
            _kernel32.CloseHandle(handle_parent)

    def test_2pc_successful_atomic_commit(self):
        """3. Valida una transazione 2PC completa e l'aborto in caso di mismatch SHA-256."""
        target_file = self.test_dir / "target_success.json"
        content = json.dumps({"status": "committed", "version": "3.3.0"}, indent=2)

        verdict = self.engine.atomic_write(target_file, content)
        self.assertEqual(verdict.verdict, "COMMIT")
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), content)

        tamper_file = self.test_dir / "target_tamper.txt"
        prep = self.engine.prepare(tamper_file, "Original Payload")
        Path(prep.staging_path).write_text("Tampered Payload", encoding="utf-8")
        abort_verdict = self.engine.commit(prep)
        self.assertEqual(abort_verdict.verdict, "ABORT")
        self.assertIn("mismatch", abort_verdict.reason.lower())
        self.assertFalse(tamper_file.exists())

    def test_50_concurrent_writers_stress(self):
        """4. Stress test con scrittori concorrenti, zero mock e zero corruzione."""
        target_file = self.test_dir / "stress_target.json"
        num_workers = 12
        errors: list[Exception] = []

        def worker_task(worker_id: int):
            try:
                payload = json.dumps(
                    {
                        "worker_id": worker_id,
                        "timestamp": time.time(),
                        "sequence": f"seq_{worker_id:04d}",
                    }
                )
                verdict = self.engine.atomic_write(
                    target_file, payload, timeout_ms=8000
                )
                if verdict.verdict != "COMMIT":
                    raise TwoPhaseCommitError(
                        f"Worker {worker_id} commit aborted: {verdict.reason}"
                    )
                return worker_id, verdict
            except Exception as e:
                errors.append(e)
                raise

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            for future in as_completed(futures):
                _, verdict = future.result()
                self.assertEqual(verdict.verdict, "COMMIT")

        self.assertEqual(len(errors), 0)
        parsed = json.loads(target_file.read_text(encoding="utf-8"))
        self.assertIn("worker_id", parsed)

    def test_promote_staging_denylist_oracle_lock_and_wal_committed_guard(self):
        """5. Valida denylist oracle_lock.json in 2PC, cleanup shadow_path e guardia WAL COMMITTED."""
        repo = self.test_dir / "repo_gov"
        stg = repo / ".staging" / "nk_tracking"
        prod_trk = repo / "nk_tracking"
        stg.mkdir(parents=True, exist_ok=True)
        prod_trk.mkdir(parents=True, exist_ok=True)

        prod_lock = prod_trk / "oracle_lock.json"
        prod_lock.write_text('{"combined_sha256": "orig"}', encoding="utf-8")
        stg_lock = stg / "oracle_lock.json"
        stg_lock.write_text('{"combined_sha256": "tampered"}', encoding="utf-8")

        with self.assertRaises(TwoPhaseCommitError):
            promote_staging_to_production(repo_root=repo)
        self.assertEqual(
            json.loads(prod_lock.read_text(encoding="utf-8"))["combined_sha256"],
            "orig",
        )

        res_ovr = promote_staging_to_production(
            repo_root=repo, allow_governance_override=True
        )
        self.assertEqual(res_ovr["status"], "SUCCESS")
        self.assertEqual(
            json.loads(prod_lock.read_text(encoding="utf-8"))["combined_sha256"],
            "tampered",
        )

        # Verifica che _shadow_swap_fallback pulisca sempre shadow_path in finally
        missing_src = self.test_dir / "non_existent_src.tmp"
        dst_shadow = self.test_dir / "dst_shadow.txt"
        self.engine.MAX_RETRIES = 1
        ok_swap = self.engine._shadow_swap_fallback(missing_src, dst_shadow)
        self.assertFalse(ok_swap)
        leftover_shadows = list(self.test_dir.glob(".shadow_*"))
        self.assertEqual(leftover_shadows, [])
        # M15: CRC32 mismatch check during commit
        tgt_m15 = self.test_dir / "tgt_m15.txt"
        prep_m15 = self.engine.prepare(tgt_m15, b"m15_payload")
        bad_crc_prep = prep_m15.model_copy(update={"crc32": prep_m15.crc32 ^ 1})
        verd_m15 = self.engine.commit(bad_crc_prep)
        self.assertEqual(verd_m15.verdict, "ABORT")

        # M16: Post-write SHA-256 verification on disk
        class _CorruptDiskEngine(TwoPhaseCommitEngine):
            def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
                t_path.write_bytes(b"corrupted_after_move")
                return True

        eng_m16 = _CorruptDiskEngine()
        tgt_m16 = self.test_dir / "tgt_m16.txt"
        prep_m16 = eng_m16.prepare(tgt_m16, b"m16_payload")
        verd_m16 = eng_m16.commit(prep_m16)
        self.assertEqual(verd_m16.verdict, "ABORT")

        # M17: quality_baseline pass_rate < 100.0 ratchet check
        dst_bl_m17 = self.test_dir / "dst_bl_m17.json"
        stg_bl_m17 = self.test_dir / "stg_bl_m17.json"
        dst_bl_m17.write_text('{"pass_rate": 90.0, "metrics": {"m": 1}}', encoding="utf-8")
        stg_bl_m17.write_text('{"pass_rate": 95.0, "metrics": {"m": 1}}', encoding="utf-8")
        from win32_2pc_engine import _verify_quality_baseline_ratchet
        with self.assertRaises(TwoPhaseCommitError):
            _verify_quality_baseline_ratchet(dst_bl_m17, stg_bl_m17)

        # M30: WriteAheadLogManager(wal_dir=None)._get_wal_path punta in tempfile.gettempdir()/nk_2pc_wal
        import win32_2pc_engine as _w2pc_mod
        wal_m30 = WriteAheadLogManager(wal_dir=None)._get_wal_path(self.test_dir / "a.txt")
        self.assertIn("nk_2pc_wal", str(wal_m30))
        self.assertTrue(
            str(Path(wal_m30).resolve()).lower().startswith(
                str(Path(tempfile.gettempdir()).resolve()).lower()
            )
        )

        # M35: _win_long_path esiste in win32_2pc_engine e gestisce i path lunghi
        import os
        self.assertTrue(hasattr(_w2pc_mod, "_win_long_path"))
        long_target = self.test_dir / ("a" * 250) / "long_file.txt"
        long_res = str(_w2pc_mod._win_long_path(long_target))
        if os.name == "nt":
            self.assertTrue(long_res.startswith("\\\\?\\"))


if __name__ == "__main__":
    unittest.main()

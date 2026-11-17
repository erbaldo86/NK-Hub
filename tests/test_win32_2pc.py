# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Win32 Two-Phase Commit e Named Mutex Engine (v6.4.0-Carbon).
Modulo: tests/test_win32_2pc.py.
Valida acquisizione RAII, affinita thread, timeout, WAIT_ABANDONED, CRIT-04 rollback, WAL e CLI.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zlib

import pytest

try:
    from conftest import SCRIPTS_DIR, STAGING_SCRIPTS_DIR, call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import SCRIPTS_DIR, STAGING_SCRIPTS_DIR, call_script_main_captured, load_nk_script_module

_w2pc_mod = load_nk_script_module("win32_2pc_engine")
TwoPhaseCommitEngine = _w2pc_mod.TwoPhaseCommitEngine
TwoPhaseCommitError = _w2pc_mod.TwoPhaseCommitError
WAIT_ABANDONED_0 = _w2pc_mod.WAIT_ABANDONED_0
Win32LockError = _w2pc_mod.Win32LockError
Win32LockTimeoutError = _w2pc_mod.Win32LockTimeoutError
Win32NamedMutex = _w2pc_mod.Win32NamedMutex
WriteAheadLogManager = _w2pc_mod.WriteAheadLogManager
_kernel32 = _w2pc_mod._kernel32
_verify_quality_baseline_ratchet = _w2pc_mod._verify_quality_baseline_ratchet
compute_crc32 = _w2pc_mod.compute_crc32
compute_sha256 = _w2pc_mod.compute_sha256
promote_staging_to_production = _w2pc_mod.promote_staging_to_production
win32_atomic_replace = _w2pc_mod.win32_atomic_replace


@pytest.mark.usefixtures("isolated_nk_env")
class TestWin322PCEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="nk_test_2pc_"))
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.wal_mgr = WriteAheadLogManager(wal_dir=self.test_dir / ".wal")
        self.engine = TwoPhaseCommitEngine(wal_manager=self.wal_mgr)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @pytest.mark.fast
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

    @pytest.mark.integration
    def test_named_mutex_abandoned_recovery(self):
        """2. Valida il recupero WAIT_ABANDONED su Win32 o rilascio flock POSIX su processo terminato."""
        unique_id = uuid.uuid4().hex[:12]
        mutex_name = f"Global\\NK_Test_Abandon_{unique_id}"
        if sys.platform == "win32":
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
        else:
            child_script = (
                "import os, sys; "
                f"sys.path[:0] = [{str(STAGING_SCRIPTS_DIR)!r}, {str(SCRIPTS_DIR)!r}]; "
                "from win32_2pc_engine import Win32NamedMutex; "
                f"m = Win32NamedMutex({mutex_name!r}, timeout_ms=3000, is_path=False); "
                "m.acquire(); "
                "sys.stdout.write('LOCKED\\n'); sys.stdout.flush(); "
                "sys.stdin.read(1); "
                "os._exit(0)"
            )
            proc = subprocess.Popen(
                [sys.executable, "-B", "-u", "-c", child_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                ready_line = proc.stdout.readline().strip() if proc.stdout else ""
                self.assertEqual(ready_line, "LOCKED")
                with self.assertRaises(Win32LockTimeoutError):
                    with Win32NamedMutex(mutex_name, timeout_ms=40, is_path=False):
                        pass
                if proc.stdin:
                    proc.stdin.close()
                rc = proc.wait(timeout=4.0)
                self.assertEqual(rc, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=2.0)
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()

            with Win32NamedMutex(mutex_name, timeout_ms=3000, is_path=False) as recovered:
                self.assertTrue(recovered.acquired)
                self.assertFalse(recovered.abandoned)
            self.assertFalse(recovered.acquired)

    @pytest.mark.fast
    def test_2pc_successful_atomic_commit(self):
        """3. Valida una transazione 2PC completa e l'aborto in caso di mismatch SHA-256."""
        target_file = self.test_dir / "target_success.json"
        content = json.dumps({"status": "committed", "version": "6.0.0-Carbon"}, indent=2)

        verdict = self.engine.atomic_write(target_file, content)
        self.assertEqual(verdict.verdict, "COMMIT")
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), content)
        self.assertEqual(
            compute_crc32(b"nexus-2pc-payload"),
            zlib.crc32(b"nexus-2pc-payload") & 0xFFFFFFFF,
        )
        self.assertGreater(compute_crc32(b"nexus-2pc-payload"), 0)
        self.assertNotEqual(compute_crc32(b"a"), compute_crc32(b"b"))

        tamper_file = self.test_dir / "target_tamper.txt"
        prep = self.engine.prepare(tamper_file, "Original Payload")
        Path(prep.staging_path).write_text("Tampered Payload", encoding="utf-8")
        abort_verdict = self.engine.commit(prep)
        self.assertEqual(abort_verdict.verdict, "ABORT")
        self.assertIn("mismatch", abort_verdict.reason.lower())
        self.assertFalse(tamper_file.exists())

    @pytest.mark.fast
    def test_crit04_single_commit_preimage_rollback_and_patch_notes_prepend_only(self):
        """6. Valida CRIT-04: ripristino pre-immagine su commit() fallito e guardia prepend-only PATCH_NOTES.md."""

        class _UnlinkFailCommitEngine(TwoPhaseCommitEngine):
            def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
                t_path.unlink(missing_ok=True)
                return False

        class _CorruptPostWriteCommitEngine(TwoPhaseCommitEngine):
            def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
                t_path.write_bytes(b"PARTIAL_CORRUPT_WRITE")
                return True

        existing_target = self.test_dir / "existing_prod.py"
        existing_target.write_text("PRE_IMAGE = 'INTACT'\n", encoding="utf-8")
        fail_eng = _UnlinkFailCommitEngine(wal_manager=self.wal_mgr)
        prep_fail = fail_eng.prepare(existing_target, "PRE_IMAGE = 'CHANGED'\n")
        verd_fail = fail_eng.commit(prep_fail)
        self.assertEqual(verd_fail.verdict, "ABORT")
        self.assertEqual(existing_target.read_text(encoding="utf-8"), "PRE_IMAGE = 'INTACT'\n")

        corrupt_eng = _CorruptPostWriteCommitEngine(wal_manager=self.wal_mgr)
        prep_corrupt = corrupt_eng.prepare(existing_target, "PRE_IMAGE = 'CHANGED_2'\n")
        verd_corrupt = corrupt_eng.commit(prep_corrupt)
        self.assertEqual(verd_corrupt.verdict, "ABORT")
        self.assertEqual(existing_target.read_text(encoding="utf-8"), "PRE_IMAGE = 'INTACT'\n")

        repo_pn = self.test_dir / "repo_patch_notes"
        (repo_pn / "nk_genome").mkdir(parents=True, exist_ok=True)
        (repo_pn / ".staging" / "nk_genome").mkdir(parents=True, exist_ok=True)
        prod_pn = repo_pn / "nk_genome" / "PATCH_NOTES.md"
        stg_pn = repo_pn / ".staging" / "nk_genome" / "PATCH_NOTES.md"
        orig_pn = "# PATCH NOTES\n\n## [v4.9.0]\n* Nota storica immutabile.\n"
        prod_pn.write_text(orig_pn, encoding="utf-8")
        stg_pn.write_text("# PATCH NOTES\n\n## [v6.0.0-Carbon]\n* Nuova.\n", encoding="utf-8")

        with self.assertRaises(TwoPhaseCommitError):
            promote_staging_to_production(repo_root=repo_pn)
        self.assertEqual(prod_pn.read_text(encoding="utf-8"), orig_pn)

        valid_prepend = (
            "# PATCH NOTES\n\n## [v6.0.0-Carbon]\n* Rilascio Carbon.\n\n"
            "## [v4.9.0]\n* Nota storica immutabile.\n"
        )
        stg_pn.write_text(valid_prepend, encoding="utf-8")
        res_ok = promote_staging_to_production(repo_root=repo_pn)
        self.assertEqual(res_ok["status"], "SUCCESS")
        self.assertEqual(prod_pn.read_text(encoding="utf-8"), valid_prepend)

    @pytest.mark.fast
    def test_50_concurrent_writers_stress(self):
        """4. Stress test con scrittori concorrenti, zero mock e zero corruzione."""
        target_file = self.test_dir / "stress_target.json"
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
                verdict = self.engine.atomic_write(target_file, payload, timeout_ms=8000)
                if verdict.verdict != "COMMIT":
                    raise TwoPhaseCommitError(f"Worker {worker_id} abort: {verdict.reason}")
                return worker_id, verdict
            except Exception as e:
                errors.append(e)
                raise

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(worker_task, i) for i in range(3)]
            for future in as_completed(futures):
                _, verdict = future.result()
                self.assertEqual(verdict.verdict, "COMMIT")

        self.assertEqual(len(errors), 0)
        self.assertIn("worker_id", json.loads(target_file.read_text(encoding="utf-8")))

    @pytest.mark.fast
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
        self.assertEqual(json.loads(prod_lock.read_text(encoding="utf-8"))["combined_sha256"], "orig")

        res_ovr = promote_staging_to_production(repo_root=repo, allow_governance_override=True)
        self.assertEqual(res_ovr["status"], "SUCCESS")
        self.assertEqual(json.loads(prod_lock.read_text(encoding="utf-8"))["combined_sha256"], "tampered")

        missing_src = self.test_dir / "non_existent_src.tmp"
        dst_shadow = self.test_dir / "dst_shadow.txt"
        self.engine.MAX_RETRIES = 1
        self.assertFalse(self.engine._shadow_swap_fallback(missing_src, dst_shadow))
        self.assertEqual(list(self.test_dir.glob(".shadow_*")), [])

        tgt_m15 = self.test_dir / "tgt_m15.txt"
        prep_m15 = self.engine.prepare(tgt_m15, b"m15_payload")
        verd_m15 = self.engine.commit(prep_m15.model_copy(update={"crc32": prep_m15.crc32 ^ 1}))
        self.assertEqual(verd_m15.verdict, "ABORT")

        class _CorruptDiskEngine(TwoPhaseCommitEngine):
            def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
                t_path.write_bytes(b"corrupted_after_move")
                return True

        eng_m16 = _CorruptDiskEngine()
        prep_m16 = eng_m16.prepare(self.test_dir / "tgt_m16.txt", b"m16_payload")
        self.assertEqual(eng_m16.commit(prep_m16).verdict, "ABORT")

        dst_bl_m17 = self.test_dir / "dst_bl_m17.json"
        stg_bl_m17 = self.test_dir / "stg_bl_m17.json"
        dst_bl_m17.write_text('{"pass_rate": 90.0, "metrics": {"m": 1}}', encoding="utf-8")
        stg_bl_m17.write_text('{"pass_rate": 95.0, "metrics": {"m": 1}}', encoding="utf-8")
        with self.assertRaises(TwoPhaseCommitError):
            _verify_quality_baseline_ratchet(dst_bl_m17, stg_bl_m17)

        wal_m30 = WriteAheadLogManager(wal_dir=None)._get_wal_path(self.test_dir / "a.txt")
        self.assertIn("nk_2pc_wal", str(wal_m30))
        if os.name == "nt":
            self.assertTrue(str(_w2pc_mod._win_long_path(self.test_dir / ("a" * 250) / "f.txt")).startswith("\\\\?\\"))


@pytest.mark.fast
def test_wal_recover_replay_quarantine_and_local_wal(
    tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """7. Verifica replay COMMITTED, quarantena WAL corrotti, SKIPPED_ACTIVE, ABORTED e NK_WAL_IN_TEMP=0."""
    assert isolated_nk_env.is_dir()
    monkeypatch.setenv("NK_WAL_IN_TEMP", "0")
    wal_local = WriteAheadLogManager()
    assert wal_local._get_wal_dir(tmp_path / "f.txt") == (tmp_path / ".wal")
    wal_local.update_wal_state(tmp_path / "missing.txt", "tx_none", "COMMITTED")

    wal_dir = tmp_path / ".wal"
    wal_mgr = WriteAheadLogManager(wal_dir=wal_dir)
    tgt_com = tmp_path / "replayed.txt"
    stg_com = tmp_path / "replayed.stg"
    stg_com.write_bytes(b"COMMITTED_BYTES")
    wal_mgr.write_wal("tx_com", tgt_com, stg_com, compute_sha256(b"COMMITTED_BYTES"), 0, state="COMMITTED")

    tgt_prep = tmp_path / "active.txt"
    stg_prep = tmp_path / "active.stg"
    stg_prep.write_bytes(b"PENDING")
    wal_mgr.write_wal("tx_act", tgt_prep, stg_prep, compute_sha256(b"PENDING"), 0, state="PREPARED")

    tgt_ab = tmp_path / "aborted.txt"
    stg_ab = tmp_path / "aborted.stg"
    stg_ab.write_bytes(b"ABORT_ME")
    wal_mgr.write_wal("tx_ab", tgt_ab, stg_ab, compute_sha256(b"ABORT_ME"), 0, state="ABORTED")

    bad_wal = wal_dir / "corrupt.wal"
    bad_wal.write_text("{bad json", encoding="utf-8")
    (wal_dir / "quarantine").mkdir(parents=True, exist_ok=True)
    (wal_dir / "quarantine" / "corrupt.wal").write_text("existing", encoding="utf-8")

    actions = wal_mgr.recover(tmp_path, stale_age_sec=60.0)
    by_action = {item.get("action") for item in actions}
    assert {"REPLAYED_COMMIT", "SKIPPED_ACTIVE", "PURGED_ABORTED", "QUARANTINED_CORRUPT"}.issubset(by_action)
    assert tgt_com.read_bytes() == b"COMMITTED_BYTES"
    assert not stg_ab.exists()


@pytest.mark.fast
def test_2pc_missing_staging_ipc_pointer_atomic_replace_and_cli(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """8. Verifica abort staging assente, create_ipc_pointer, win32_atomic_replace e CLI main."""
    assert isolated_nk_env.is_dir()
    eng = TwoPhaseCommitEngine(wal_manager=WriteAheadLogManager(wal_dir=tmp_path / ".wal"))
    prep = eng.prepare(tmp_path / "miss.txt", b"hello")
    Path(prep.staging_path).unlink()
    assert eng.commit(prep).verdict == "ABORT"

    ipc_ptr = eng.create_ipc_pointer(tmp_path / "ipc.json", '{"k": 1}', mime_type="application/json")
    assert ipc_ptr.status == "OK" and ipc_ptr.byte_size == 8

    src = tmp_path / "rep_src.txt"
    dst = tmp_path / "rep_dst.txt"
    src.write_text("REPLACED", encoding="utf-8")
    win32_atomic_replace(src, dst, max_retries=2)
    assert dst.read_text(encoding="utf-8") == "REPLACED"

    with pytest.raises(TwoPhaseCommitError):
        win32_atomic_replace(tmp_path / "absent.txt", dst, max_retries=1)

    rc_help, out_help, _ = call_script_main_captured(_w2pc_mod, [])
    assert rc_help == 0 and "Win32 Two-Phase Commit" in out_help

    repo = tmp_path / "cli_repo"
    (repo / ".staging").mkdir(parents=True)
    (repo / ".staging" / "demo.txt").write_text("hi", encoding="utf-8")
    rc_q, out_q, _ = call_script_main_captured(_w2pc_mod, ["--quarantine-staging", "--repo-root", str(repo)])
    q_payload = json.loads(out_q)
    assert rc_q == 0 and q_payload["status"] == "SUCCESS"
    assert q_payload["quarantined_count"] == 1 and q_payload["quarantined_files"] == ["demo.txt"]
    assert not (repo / ".staging" / "demo.txt").exists()

    rc_bad, _, err_bad = call_script_main_captured(
        _w2pc_mod, ["--promote-staging", "--repo-root", str(tmp_path / "no_repo")]
    )
    assert rc_bad == 1 and "2PC" in err_bad


@pytest.mark.fast
def test_p0_bug_04_journal_preserves_preimages_on_transient_rollback_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica P0-BUG-04: OSError durante rollback preserva preimages/ e consente retry riuscito."""
    from _internal.win32_2pc_engine import journal as journal_mod

    repo = tmp_path / "repo_journal_retry"
    repo.mkdir(parents=True)
    target_a = repo / "alpha.txt"
    target_a.write_text("ALPHA_ORIGINAL", encoding="utf-8")

    batch_id, journal_root, batch_dir = journal_mod.BatchJournalV2.begin_batch(
        repo, [("alpha.txt", target_a)]
    )
    assert batch_id.startswith("batch_")
    assert (journal_root / "active_batch.json").is_file()
    assert list((batch_dir / "preimages").glob("*.bin"))

    target_a.write_text("ALPHA_CORRUPTED_MID_BATCH", encoding="utf-8")

    def _raise_sharing_violation(*_args, **_kwargs) -> None:
        raise OSError("Simulated Win32 ERROR_SHARING_VIOLATION during rollback")

    monkeypatch.setattr(journal_mod, "_atomic_write_bytes", _raise_sharing_violation)
    res_err, norms_err = journal_mod.BatchJournalV2.recover_crashed_batches(repo)
    assert res_err and res_err[0]["action"] == "ERROR"
    assert norms_err
    assert (journal_root / "active_batch.json").is_file()
    assert (batch_dir / "preimages").is_dir()
    assert len(list((batch_dir / "preimages").glob("*.bin"))) == 1

    monkeypatch.undo()
    res_ok, _ = journal_mod.BatchJournalV2.recover_crashed_batches(repo)
    assert res_ok and res_ok[0]["action"] == "ROLLED_BACK_BATCH"
    assert target_a.read_text(encoding="utf-8") == "ALPHA_ORIGINAL"
    assert not (journal_root / "active_batch.json").exists()
    assert not batch_dir.exists()


@pytest.mark.integration
def test_p0_bug_05_task_ledger_multiprocess_concurrent_hash_chain(
    tmp_path: Path,
) -> None:
    """Verifica P0-BUG-05: scrittori multi-processo concorrenti su TaskLedger preservano la catena SHA-256."""
    from schemas.dual_ledgers import TaskLedger

    ledger_path = tmp_path / "mp_task_dag.jsonl"
    worker_code = (
        "import sys, time; "
        f"sys.path[:0] = [{str(STAGING_SCRIPTS_DIR)!r}, {str(SCRIPTS_DIR)!r}]; "
        "from schemas.dual_ledgers import TaskLedger; "
        "lp, wid, cnt = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); "
        "tl = TaskLedger(lp); "
        "[tl.add_task(f'W{wid}_T{i}', 'BUILD', 'NK-Builder', payload={'w': wid, 'i': i}) for i in range(cnt)]"
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", worker_code, str(ledger_path), str(w), "4"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for w in range(4)
    ]
    for p in procs:
        out, err = p.communicate(timeout=15.0)
        assert p.returncode == 0, f"Worker failed: {out}\n{err}"

    verified = TaskLedger(ledger_path)
    tasks = verified.list_tasks()
    assert len(tasks) == 16
    assert len({t.task_id for t in tasks}) == 16
    ok_dag, msg_dag = verified.verify_dag()
    assert ok_dag is True, msg_dag

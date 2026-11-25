# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Win32 Two-Phase Commit e Named Mutex Engine.
Modulo: tests/test_win32_2pc.py.
Valida RAII, CRIT-04 preimage rollback, WAL 6-state recovery, promoter, ratchet, HMAC governance e git sync.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import zlib

import pytest

try:
    from conftest import SCRIPTS_DIR, STAGING_SCRIPTS_DIR, call_script_main, call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import SCRIPTS_DIR, STAGING_SCRIPTS_DIR, call_script_main, call_script_main_captured, load_nk_script_module

_w2pc_mod = load_nk_script_module("win32_2pc_engine")
_w2pc_consts = importlib.import_module("_internal.win32_2pc_engine.constants")
TwoPhaseCommitEngine = _w2pc_mod.TwoPhaseCommitEngine
TwoPhaseCommitError = _w2pc_mod.TwoPhaseCommitError
Win32NamedMutex = _w2pc_mod.Win32NamedMutex
WriteAheadLogManager = _w2pc_mod.WriteAheadLogManager
_verify_quality_baseline_ratchet = _w2pc_mod._verify_quality_baseline_ratchet
compute_crc32 = _w2pc_mod.compute_crc32
compute_sha256 = _w2pc_mod.compute_sha256
ensure_governance_hmac_key = _w2pc_mod.ensure_governance_hmac_key
mint_governance_token = _w2pc_mod.mint_governance_token
promote_staging_to_production = _w2pc_mod.promote_staging_to_production
verify_governance_token = _w2pc_mod.verify_governance_token
win32_atomic_replace = _w2pc_mod.win32_atomic_replace


def _assert_crit04_preimage_and_patch_notes(tmp_path: Path, wal_mgr: Any) -> None:
    class _UnlinkFailCommitEngine(TwoPhaseCommitEngine):
        def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
            t_path.unlink(missing_ok=True)
            return False

    class _CorruptPostWriteCommitEngine(TwoPhaseCommitEngine):
        def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
            t_path.write_bytes(b"PARTIAL_CORRUPT_WRITE")
            return True

    existing_target = tmp_path / "existing_prod.py"
    existing_target.write_text("PRE_IMAGE = 'INTACT'\n", encoding="utf-8")
    fail_eng = _UnlinkFailCommitEngine(wal_manager=wal_mgr)
    assert (fail_eng.commit(fail_eng.prepare(existing_target, "PRE_IMAGE = 'CHANGED'\n")).verdict, existing_target.read_text(encoding="utf-8")) == ("ABORT", "PRE_IMAGE = 'INTACT'\n")
    corrupt_eng = _CorruptPostWriteCommitEngine(wal_manager=wal_mgr)
    assert (corrupt_eng.commit(corrupt_eng.prepare(existing_target, "PRE_IMAGE = 'CHANGED_2'\n")).verdict, existing_target.read_text(encoding="utf-8")) == ("ABORT", "PRE_IMAGE = 'INTACT'\n")

    repo_pn = tmp_path / "repo_patch_notes"
    (repo_pn / "nk_genome").mkdir(parents=True)
    (repo_pn / ".staging" / "nk_genome").mkdir(parents=True)
    prod_pn, stg_pn = repo_pn / "nk_genome" / "PATCH_NOTES.md", repo_pn / ".staging" / "nk_genome" / "PATCH_NOTES.md"
    orig_pn = "# PATCH NOTES\n\n## [v4.9.0]\n* Nota storica immutabile.\n"
    prod_pn.write_text(orig_pn, encoding="utf-8")
    stg_pn.write_text("# PATCH NOTES\n\n## [v6.0.0-Carbon]\n* Nuova.\n", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError):
        promote_staging_to_production(repo_root=repo_pn)
    assert prod_pn.read_text(encoding="utf-8") == orig_pn
    valid_prepend = "# PATCH NOTES\n\n## [v6.0.0-Carbon]\n* Rilascio Carbon.\n\n## [v4.9.0]\n* Nota storica immutabile.\n"
    stg_pn.write_text(valid_prepend, encoding="utf-8")
    assert (promote_staging_to_production(repo_root=repo_pn)["status"], prod_pn.read_text(encoding="utf-8")) == ("SUCCESS", valid_prepend)


@pytest.mark.integration
def test_2pc_atomic_commit_concurrent_crc_and_tamper(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Valida commit 2PC, CRC32, tamper SHA-256, writer concorrenti, CRIT-04 preimage e PATCH_NOTES."""
    _ = isolated_nk_env
    wal_mgr = WriteAheadLogManager(wal_dir=tmp_path / ".wal")
    engine = TwoPhaseCommitEngine(wal_manager=wal_mgr)

    target_file = tmp_path / "target_success.json"
    content = json.dumps({"status": "committed", "version": "6.0.0-Carbon"}, indent=2)
    verdict = engine.atomic_write(target_file, content)
    assert (verdict.verdict, target_file.read_text(encoding="utf-8")) == ("COMMIT", content)
    assert (compute_crc32(b"nexus-2pc-payload") == (zlib.crc32(b"nexus-2pc-payload") & 0xFFFFFFFF) > 0, compute_crc32(b"a") != compute_crc32(b"b")) == (True, True)

    tamper_file = tmp_path / "target_tamper.txt"
    prep = engine.prepare(tamper_file, "Original Payload")
    Path(prep.staging_path).write_text("Tampered Payload", encoding="utf-8")
    abort_verdict = engine.commit(prep)
    assert (abort_verdict.verdict, "mismatch" in (abort_verdict.reason or "").lower(), tamper_file.exists()) == ("ABORT", True, False)

    stress_file = tmp_path / "stress_target.json"

    def worker_task(worker_id: int) -> str:
        payload = json.dumps({"worker_id": worker_id, "timestamp": time.time(), "sequence": f"seq_{worker_id:04d}"})
        return engine.atomic_write(stress_file, payload, timeout_ms=8000).verdict

    with ThreadPoolExecutor(max_workers=3) as executor:
        assert [f.result() for f in as_completed([executor.submit(worker_task, i) for i in range(3)])] == ["COMMIT"] * 3
    assert "worker_id" in json.loads(stress_file.read_text(encoding="utf-8"))
    _assert_crit04_preimage_and_patch_notes(tmp_path, wal_mgr)


def _assert_engine_crc_shadow_and_ratchet(tmp_path: Path) -> None:
    eng = TwoPhaseCommitEngine(wal_manager=WriteAheadLogManager(wal_dir=tmp_path / ".wal_g"))
    eng.MAX_RETRIES = 1
    assert (eng._shadow_swap_fallback(tmp_path / "non_existent_src.tmp", tmp_path / "dst_shadow.txt"), list(tmp_path.glob(".shadow_*"))) == (False, [])
    prep_m15 = eng.prepare(tmp_path / "tgt_m15.txt", b"m15_payload")
    assert eng.commit(prep_m15.model_copy(update={"crc32": prep_m15.crc32 ^ 1})).verdict == "ABORT"

    class _CorruptDiskEngine(TwoPhaseCommitEngine):
        def _execute_atomic_commit(self, s_path: Path, t_path: Path) -> bool:
            t_path.write_bytes(b"corrupted_after_move")
            return True

    eng_m16 = _CorruptDiskEngine()
    assert eng_m16.commit(eng_m16.prepare(tmp_path / "tgt_m16.txt", b"m16_payload")).verdict == "ABORT"

    dst_bl, stg_bl = tmp_path / "dst_bl_m17.json", tmp_path / "stg_bl_m17.json"
    dst_bl.write_text('{"pass_rate": 90.0, "metrics": {"m": 1}}', encoding="utf-8")
    stg_bl.write_text('{"pass_rate": 95.0, "metrics": {"m": 1}}', encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError):
        _verify_quality_baseline_ratchet(dst_bl, stg_bl)
    assert "nk_2pc_wal" in str(WriteAheadLogManager(wal_dir=None)._get_wal_path(tmp_path / "a.txt"))
    if os.name == "nt":
        assert str(_w2pc_mod._win_long_path(tmp_path / ("a" * 250) / "f.txt")).startswith("\\\\?\\")


@pytest.mark.integration
def test_promote_staging_denylist_oracle_lock_and_wal_committed_guard(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Valida denylist oracle_lock.json + override audit firmato SHA-256, CRC/corruzione e long-path."""
    _ = isolated_nk_env
    repo = tmp_path / "repo_gov"
    stg, prod_trk = repo / ".staging" / "nk_tracking", repo / "nk_tracking"
    stg.mkdir(parents=True)
    prod_trk.mkdir(parents=True)
    prod_lock, stg_lock = prod_trk / "oracle_lock.json", stg / "oracle_lock.json"
    prod_lock.write_text('{"combined_sha256": "orig"}', encoding="utf-8")
    stg_lock.write_text('{"combined_sha256": "tampered"}', encoding="utf-8")

    with pytest.raises(TwoPhaseCommitError):
        promote_staging_to_production(repo_root=repo)
    assert json.loads(prod_lock.read_text(encoding="utf-8"))["combined_sha256"] == "orig"

    key_p = tmp_path / "gov_hmac_307.key"
    with pytest.MonkeyPatch.context() as mp_gov:
        mp_gov.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_p))
        ensure_governance_hmac_key(key_p)
        tok = mint_governance_token("wave0_test_audit_override", key_path=key_p)
        res_ovr = promote_staging_to_production(repo_root=repo, allow_governance_override=True, governance_override_reason="wave0_test_audit_override", governance_token=tok)
    assert (res_ovr["status"], bool(res_ovr["governance_override_recorded"]), json.loads(prod_lock.read_text(encoding="utf-8"))["combined_sha256"]) == ("SUCCESS", True, "tampered")
    anchor_lines = (prod_trk / "anchor" / "session_anchor.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"GOVERNANCE_OVERRIDE"' in ln and '"audit_sha256"' in ln for ln in anchor_lines)
    _assert_engine_crc_shadow_and_ratchet(tmp_path)


def _assert_wal_consts_abort_and_purge(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _w2pc_mod.get_repo_batch_mutex_name(repo) == _w2pc_mod.get_repo_batch_mutex_name(str(repo))
    assert "NK_RepoBatchLock_" in _w2pc_mod.get_repo_batch_mutex_name(repo)
    eng = TwoPhaseCommitEngine(wal_manager=WriteAheadLogManager(wal_dir=tmp_path / ".wal_abort"))
    assert (eng.abort(eng.prepare(tmp_path / "target_doc.txt", "hello_2pc"), reason="unit_abort").verdict, _w2pc_consts._get_facade_attr("NONEXISTENT_ATTR_XYZ", "fallback")) == ("ABORT", "fallback")
    if sys.platform == "win32":
        ctypes.set_last_error(5)
        assert _w2pc_consts._get_win32_last_error() == 5
        ctypes.set_last_error(0)
    with monkeypatch.context() as mp_k:
        mp_k.setattr(_w2pc_consts, "_get_active_kernel32", lambda: None)
        assert _w2pc_consts._get_win32_last_error() == 0
    clean_repo = tmp_path / "wal_clean_repo"
    (clean_repo / ".wal").mkdir(parents=True)
    wal_loc_r = WriteAheadLogManager(wal_dir=clean_repo / ".wal")
    wal_loc_r.write_wal("tx_s", clean_repo / "active.txt", tmp_path / "stg_s.txt", "0", 0, state="PREPARED")
    wal_loc_r.purge_wal(clean_repo / "active.txt", "tx_s")
    assert wal_loc_r.recover(clean_repo, stale_age_sec=0.0) == []


@pytest.mark.integration
def test_wal_recover_replay_quarantine_and_6_states(
    tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica 6 stati WAL recover, NK_WAL_IN_TEMP=0, quarantine collision, constants e abort/ipc."""
    _ = isolated_nk_env
    monkeypatch.setenv("NK_WAL_IN_TEMP", "0")
    wal_local = WriteAheadLogManager()
    tgt_local = tmp_path / "repo_w" / "a.txt"
    tgt_local.parent.mkdir(parents=True)
    assert (wal_local._get_wal_dir(tmp_path / "f.txt"), wal_local.get_wal_path(tgt_local, "tx0").parent) == (tmp_path / ".wal", tgt_local.parent / ".wal")
    wal_local.update_wal_state(tmp_path / "missing.txt", "tx_none", "COMMITTED")

    q_dir = tmp_path / "q_wal"
    (q_dir / "quarantine").mkdir(parents=True)
    (q_dir / "quarantine" / "dup.wal").write_text("old", encoding="utf-8")
    dup_w = q_dir / "dup.wal"
    dup_w.write_text("corrupt", encoding="utf-8")
    q_res = WriteAheadLogManager._quarantine_corrupt_wal(dup_w, q_dir)
    assert (q_res.parent.name, q_res.name != "dup.wal", q_res.exists()) == ("quarantine", True, True)

    repo = tmp_path / "wal_rec_repo"
    (repo / ".wal").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    custom_w = tmp_path / "custom_wal_dir"
    custom_w.mkdir()
    wal_mgr = WriteAheadLogManager(custom_w)
    (repo / ".wal" / "01_list.wal").write_text("[1, 2]", encoding="utf-8")
    (repo / ".wal" / "02_badstate.wal").write_text(json.dumps({"target_path": str(repo / "scripts" / "x.py"), "state": "INVALID"}), encoding="utf-8")
    stg_c, payload_c = tmp_path / "stg_comm.tmp", b"COMMITTED_BYTES = 1\n"
    stg_c.write_bytes(payload_c)
    tgt_c = repo / "scripts" / "replayed.py"
    wal_mgr.write_wal("tx_c", tgt_c, stg_c, compute_sha256(payload_c), 0, state="COMMITTED")
    stg_ps = tmp_path / "stg_prep.tmp"
    stg_ps.write_bytes(b"TEMP")
    (repo / ".wal" / "04_prep_stale.wal").write_text(json.dumps({"tx_id": "tx_ps", "target_path": str(repo / "scripts" / "ps.py"), "staging_path": str(stg_ps), "state": "PREPARED", "timestamp_utc": time.time() - 120.0}), encoding="utf-8")
    (repo / ".wal" / "05_prep_active.wal").write_text(json.dumps({"tx_id": "tx_pa", "target_path": str(repo / "scripts" / "pa.py"), "state": "PREPARED", "timestamp_utc": time.time()}), encoding="utf-8")
    stg_a = tmp_path / "stg_ab.tmp"
    stg_a.write_bytes(b"AB")
    (custom_w / "06_aborted.wal").write_text(json.dumps({"tx_id": "tx_ab", "target_path": str(repo / "scripts" / "ab.py"), "staging_path": str(stg_a), "state": "ABORTED", "timestamp_utc": time.time() - 30.0}), encoding="utf-8")
    actions = {r.get("action") for r in wal_mgr.recover(repo, stale_age_sec=10.0)}
    assert (tgt_c.read_bytes(), {"QUARANTINED_CORRUPT", "REPLAYED_COMMIT", "ABORTED_STALE", "SKIPPED_ACTIVE", "PURGED_ABORTED"}.issubset(actions), stg_a.exists()) == (payload_c, True, False)
    _assert_wal_consts_abort_and_purge(tmp_path, repo, monkeypatch)


def _assert_2pc_retries_and_cli_quarantine(tmp_path: Path, eng: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    eng_mod = importlib.import_module("_internal.win32_2pc_engine.engine")
    fake_k32 = SimpleNamespace(MoveFileExW=lambda *_a: 0, GetLastError=lambda: _w2pc_consts.ERROR_SHARING_VIOLATION)
    src_f, dst_f = tmp_path / "src_f.txt", tmp_path / "dst_f.txt"
    src_f.write_text("v2", encoding="utf-8")
    dst_f.write_text("v1", encoding="utf-8")
    real_replace = os.replace
    with monkeypatch.context() as mp:
        mp.setattr(eng_mod._consts, "_get_active_kernel32", lambda: fake_k32)
        mp.setattr(eng_mod._consts, "_get_win32_last_error", lambda: _w2pc_consts.ERROR_SHARING_VIOLATION)
        mp.setattr(eng_mod.os, "replace", lambda s, d: (_ for _ in ()).throw(PermissionError("locked")) if Path(d) == dst_f and ".shadow_" in Path(s).name else real_replace(s, d))
        assert (eng._execute_atomic_commit(src_f, dst_f), dst_f.read_text(encoding="utf-8")) == (False, "v1")

    monkeypatch.setattr(eng_mod.TwoPhaseCommitEngine, "_execute_atomic_commit", lambda _self, _s, _d: False)
    with pytest.raises(TwoPhaseCommitError):
        eng.create_ipc_pointer(dst_f, "fail_ipc")
    with pytest.raises(TwoPhaseCommitError):
        eng_mod.win32_atomic_replace(src_f, dst_f, max_retries=1)

    rc_help, out_help, _ = call_script_main_captured(_w2pc_mod, [])
    assert (rc_help, "Win32 Two-Phase Commit" in out_help) == (0, True)
    repo = tmp_path / "cli_repo"
    (repo / ".staging").mkdir(parents=True)
    (repo / ".staging" / "demo.txt").write_text("hi", encoding="utf-8")
    rc_q, out_q, _ = call_script_main_captured(_w2pc_mod, ["--quarantine-staging", "--repo-root", str(repo)])
    q_payload = json.loads(out_q)
    assert (rc_q, q_payload["status"], q_payload["quarantined_count"], q_payload["quarantined_files"], (repo / ".staging" / "demo.txt").exists()) == (0, "SUCCESS", 1, ["demo.txt"], False)
    rc_bad, _, err_bad = call_script_main_captured(_w2pc_mod, ["--promote-staging", "--repo-root", str(tmp_path / "no_repo")])
    assert (rc_bad, "2PC" in err_bad) == (1, True)
    capsys.readouterr()
    monkeypatch.setattr(_w2pc_mod, "quarantine_staging", lambda **_k: (_ for _ in ()).throw(RuntimeError("q_boom")))
    assert call_script_main(_w2pc_mod, ["--quarantine-staging", "--repo-root", str(repo)], monkeypatch) == 1


@pytest.mark.integration
def test_2pc_missing_staging_engine_retries_ipc_and_cli(
    tmp_path: Path, isolated_nk_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica abort/retry/shadow-swap, create_ipc_pointer, win32_atomic_replace e CLI error paths."""
    _ = isolated_nk_env
    eng_mod = importlib.import_module("_internal.win32_2pc_engine.engine")
    eng = eng_mod.TwoPhaseCommitEngine(wal_manager=WriteAheadLogManager(wal_dir=tmp_path / ".wal"))
    eng.MAX_RETRIES = 2
    monkeypatch.setattr(eng_mod.TwoPhaseCommitEngine, "_backoff_sleep", staticmethod(lambda _a: None))

    prep = eng.prepare(tmp_path / "miss.txt", b"hello")
    Path(prep.staging_path).unlink()
    assert eng.commit(prep).verdict == "ABORT"

    tgt = tmp_path / "doc.txt"
    prep_sha = eng.prepare(tgt, "abc")
    Path(prep_sha.staging_path).write_text("xyz", encoding="utf-8")
    assert "SHA-256 mismatch" in (eng.commit(prep_sha).reason or "")

    prep_crc = eng.prepare(tgt, "abc")
    eng.commit(eng_mod._consts.TwoPhaseCommitPrepare(
        transaction_id=prep_crc.transaction_id, target_path=prep_crc.target_path, staging_path=prep_crc.staging_path,
        expected_sha256=prep_crc.expected_sha256, crc32=999999999, timeout_ms=1000, timestamp_utc=time.time(),
    ))
    assert not Path(prep_crc.staging_path).exists()

    ipc_ptr = eng.create_ipc_pointer(tmp_path / "ipc.json", '{"k": 1}', mime_type="application/json")
    assert (ipc_ptr.status, ipc_ptr.byte_size) == ("OK", 8)
    src, dst = tmp_path / "rep_src.txt", tmp_path / "rep_dst.txt"
    src.write_text("REPLACED", encoding="utf-8")
    win32_atomic_replace(src, dst, max_retries=2)
    assert dst.read_text(encoding="utf-8") == "REPLACED"
    with pytest.raises(TwoPhaseCommitError):
        win32_atomic_replace(tmp_path / "absent.txt", dst, max_retries=1)
    _assert_2pc_retries_and_cli_quarantine(tmp_path, eng, monkeypatch, capsys)


def _assert_wave0_rollback_keeps_preimages(tmp_path: Path, journal_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    rb_repo = tmp_path / "w0_rollback_keep"
    (rb_repo / "scripts").mkdir(parents=True)
    (rb_repo / "scripts" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (rb_repo / "scripts" / "blocker").write_text("block_dir", encoding="utf-8")
    (rb_repo / ".staging" / "scripts" / "blocker").mkdir(parents=True)
    (rb_repo / ".staging" / "scripts" / "keep.py").write_text("KEEP = 2\n", encoding="utf-8")
    (rb_repo / ".staging" / "scripts" / "blocker" / "c.py").write_text("C = 3\n", encoding="utf-8")

    orig_rb = journal_mod.BatchJournalV2.rollback_from_manifest
    monkeypatch.setattr(journal_mod.BatchJournalV2, "rollback_from_manifest", lambda *_a, **_k: (_ for _ in ()).throw(OSError("Simulated WinError 32")))
    with pytest.raises(OSError, match="WinError 32"):
        promote_staging_to_production(repo_root=rb_repo)
    assert (journal_mod.BatchJournalV2.get_journal_root(rb_repo) / "active_batch.json").is_file()
    monkeypatch.setattr(journal_mod.BatchJournalV2, "rollback_from_manifest", orig_rb)
    rec, _ = journal_mod.BatchJournalV2.recover_crashed_batches(rb_repo)
    assert (bool(rec), rec[0]["action"], (rb_repo / "scripts" / "keep.py").read_text(encoding="utf-8")) == (True, "ROLLED_BACK_BATCH", "KEEP = 1\n")


@pytest.mark.integration
def test_p0_bug_04_journal_and_wave0_rollback_preserves_preimages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Verifica P0-BUG-04 e Wave 0: conservazione preimages/ e journal se rollback fallisce."""
    _ = isolated_nk_env
    from _internal.win32_2pc_engine import journal as journal_mod

    repo = tmp_path / "repo_journal_retry"
    repo.mkdir(parents=True)
    target_a = repo / "alpha.txt"
    target_a.write_text("ALPHA_ORIGINAL", encoding="utf-8")
    batch_id, journal_root, batch_dir = journal_mod.BatchJournalV2.begin_batch(repo, [("alpha.txt", target_a)])
    assert (batch_id.startswith("batch_"), (journal_root / "active_batch.json").is_file(), bool(list((batch_dir / "preimages").glob("*.bin")))) == (True, True, True)
    target_a.write_text("ALPHA_CORRUPTED_MID_BATCH", encoding="utf-8")

    with monkeypatch.context() as mp_j:
        mp_j.setattr(journal_mod, "_atomic_write_bytes", lambda *_a, **_k: (_ for _ in ()).throw(OSError("Simulated ERROR_SHARING_VIOLATION")))
        res_err, norms_err = journal_mod.BatchJournalV2.recover_crashed_batches(repo)
        assert (bool(res_err), res_err[0]["action"], bool(norms_err), (journal_root / "active_batch.json").is_file(), len(list((batch_dir / "preimages").glob("*.bin")))) == (True, "ERROR", True, True, 1)
    res_ok, _ = journal_mod.BatchJournalV2.recover_crashed_batches(repo)
    assert (bool(res_ok), res_ok[0]["action"], target_a.read_text(encoding="utf-8"), batch_dir.exists()) == (True, "ROLLED_BACK_BATCH", "ALPHA_ORIGINAL", False)
    _assert_wave0_rollback_keeps_preimages(tmp_path, journal_mod, monkeypatch)


def _assert_promoter_baseline_ratchet_gates(tmp_path: Path) -> None:
    repo_miss = tmp_path / "repo_no_bl"
    (repo_miss / ".staging" / "scripts").mkdir(parents=True)
    (repo_miss / ".staging" / "scripts" / "a.py").write_text("A = 1\n", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="quality_baseline.json mancante"):
        promote_staging_to_production(repo_root=repo_miss, verify_baseline=True)

    base_m = {"total_golden_tests": {"value": 100, "direction": "higher_is_better"}, "unit_tests_total": {"value": 100, "direction": "higher_is_better"}, "unit_tests_passed": {"value": 100, "direction": "higher_is_better"}, "pass_rate_pct": {"value": 100.0, "direction": "higher_is_better"}, "failed_tests": {"value": 0, "direction": "lower_is_better"}, "tests_skipped": {"value": 0, "direction": "lower_is_better"}, "pytest_duration_s": {"value": 20.0, "direction": "lower_is_better"}}
    reg_m = dict(base_m, unit_tests_total={"value": 95, "direction": "higher_is_better"})
    good_m = dict(base_m, total_golden_tests={"value": 105, "direction": "higher_is_better"}, unit_tests_total={"value": 105, "direction": "higher_is_better"}, unit_tests_passed={"value": 105, "direction": "higher_is_better"}, pytest_duration_s={"value": 15.0, "direction": "lower_is_better"})
    (repo_miss / "nk_tracking").mkdir(parents=True)
    (repo_miss / ".staging" / "nk_tracking").mkdir(parents=True)
    (repo_miss / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": base_m}), encoding="utf-8")
    (repo_miss / ".staging" / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": reg_m}), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="Regressione"):
        promote_staging_to_production(repo_root=repo_miss, verify_baseline=True)
    (repo_miss / ".staging" / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": good_m}), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="RULE-ORACLE-LOCK"):
        promote_staging_to_production(repo_root=repo_miss, verify_baseline=True)
    key_bl = tmp_path / "gov_bl_w1.key"
    with pytest.MonkeyPatch.context() as mp_bl:
        mp_bl.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_bl))
        ensure_governance_hmac_key(key_bl)
        tok_bl = mint_governance_token("wave1_baseline_upgrade_audit", key_path=key_bl)
        assert promote_staging_to_production(repo_root=repo_miss, verify_baseline=True, allow_governance_override=True, governance_override_reason="wave1_baseline_upgrade_audit", governance_token=tok_bl)["status"] == "SUCCESS"


@pytest.mark.integration
def test_win32_2pc_promoter_deletions_json_rollback_and_baseline(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Esercita promoter.py su invariati, pruning, keep_staging, errori JSON, rollback batch e verify_baseline."""
    _ = isolated_nk_env
    repo = tmp_path / "repo_promote"
    (repo / "scripts" / "sub").mkdir(parents=True)
    (repo / "custom_pkg" / "deep").mkdir(parents=True)
    (repo / ".staging" / "scripts").mkdir(parents=True)
    (repo / "scripts" / "same.py").write_text("SAME = 1\n", encoding="utf-8")
    (repo / ".staging" / "scripts" / "same.py").write_text("SAME = 1\n", encoding="utf-8")
    (repo / ".staging" / "scripts" / "added.py").write_text("ADDED = 2\n", encoding="utf-8")
    (repo / "scripts" / "sub" / "old_sub.py").write_text("OLD = 1\n", encoding="utf-8")
    (repo / "custom_pkg" / "deep" / "old_deep.py").write_text("DEEP = 1\n", encoding="utf-8")
    (repo / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["scripts/sub/old_sub.py", "custom_pkg/deep/old_deep.py"]}), encoding="utf-8")

    res = promote_staging_to_production(repo_root=repo, milestone="MS-PROMOTE-01", cleanup_staging=False, git_sync=False)
    assert (res["status"], "scripts/same.py" in [Path(p).as_posix() for p in res["unchanged_files"]]) == ("SUCCESS", True)
    assert ((repo / "scripts" / "sub").exists(), (repo / "custom_pkg").exists(), (repo / "scripts").is_dir(), (repo / ".staging" / "scripts" / "added.py").is_file()) == (False, False, True, True)

    with pytest.raises(FileNotFoundError):
        promote_staging_to_production(repo_root=tmp_path / "no_staging_repo")
    repo_json = tmp_path / "repo_bad_json"
    (repo_json / ".staging" / "config").mkdir(parents=True)
    (repo_json / ".staging" / "config" / "bad.json").write_text("{invalid json", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="JSON"):
        promote_staging_to_production(repo_root=repo_json)

    repo_rb = tmp_path / "repo_rollback"
    (repo_rb / "scripts").mkdir(parents=True)
    (repo_rb / "scripts" / "blocker").write_text("regular_file_blocks_subdir", encoding="utf-8")
    (repo_rb / "scripts" / "a_first.py").write_text("ORIG_FIRST = 1\n", encoding="utf-8")
    (repo_rb / ".staging" / "scripts" / "blocker").mkdir(parents=True)
    (repo_rb / ".staging" / "scripts" / "a_first.py").write_text("NEW_FIRST = 2\n", encoding="utf-8")
    (repo_rb / ".staging" / "scripts" / "blocker" / "child.py").write_text("CHILD = 1\n", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="rolled back"):
        promote_staging_to_production(repo_root=repo_rb)
    assert (repo_rb / "scripts" / "a_first.py").read_text(encoding="utf-8") == "ORIG_FIRST = 1\n"
    _assert_promoter_baseline_ratchet_gates(tmp_path)


def _assert_promoter_quarantine_and_hmac_deletions(tmp_path: Path, phelp_mod: Any) -> Path:
    empty_repo = tmp_path / "repo_q_empty"
    empty_repo.mkdir()
    res_empty = phelp_mod.quarantine_staging(repo_root=empty_repo)
    assert (res_empty["quarantined_count"], (empty_repo / ".staging" / ".gitkeep").is_file()) == (0, True)

    full_repo = tmp_path / "repo_q_full"
    (full_repo / ".staging" / "nested").mkdir(parents=True)
    (full_repo / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    (full_repo / ".staging" / "nested" / "orphan.py").write_text("X = 1\n", encoding="utf-8")
    res_full = phelp_mod.quarantine_staging(repo_root=full_repo)
    assert (res_full["quarantined_count"], res_full["quarantined_files"], (full_repo / ".staging" / "nested").exists()) == (1, ["nested/orphan.py"], False)

    gov_repo = tmp_path / "repo_del_gov"
    (gov_repo / "nk_genome").mkdir(parents=True)
    (gov_repo / "nk_tracking").mkdir(parents=True)
    (gov_repo / "nk_genome" / "PATCH_NOTES.md").write_text("## [v1.0.0]\n", encoding="utf-8")
    (gov_repo / "nk_tracking" / "checkpoint_01.json").write_text("{}", encoding="utf-8")
    return gov_repo


def _assert_governance_override_and_git_sync(tmp_path: Path, gov_repo: Path, manifest: Path, phelp_mod: Any) -> None:
    manifest.write_text(json.dumps(["nk_tracking/checkpoint_01.json"]), encoding="utf-8")
    overridden_del: list[str] = []
    key_del = tmp_path / "gov_del_w1.key"
    with pytest.MonkeyPatch.context() as mp_del:
        mp_del.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_del))
        with pytest.raises(TwoPhaseCommitError, match="override-reason"):
            phelp_mod.collect_validated_deletions(manifest, gov_repo, gov_repo.resolve(), True)
        with pytest.raises(TwoPhaseCommitError, match="Token governance"):
            phelp_mod.collect_validated_deletions(manifest, gov_repo, gov_repo.resolve(), True, governance_override_reason="wave0_test_del_override")
        ensure_governance_hmac_key(key_del)
        tok_del = mint_governance_token("wave0_test_del_override", key_path=key_del)
        allowed = phelp_mod.collect_validated_deletions(manifest, gov_repo, gov_repo.resolve(), True, governance_override_reason="wave0_test_del_override", overridden_out=overridden_del, governance_token=tok_del)
        mp_del.setattr(shutil, "which", lambda _n: None)
        assert (len(allowed), overridden_del, phelp_mod.run_git_sync(gov_repo, [], [])) == (1, ["delete:nk_tracking/checkpoint_01.json"], False)



@pytest.mark.integration
def test_win32_2pc_quarantine_deletions_denylist_and_git_sync(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Esercita promoter_helpers.py su quarantine_staging, collect_validated_deletions e run_git_sync."""
    _ = isolated_nk_env
    from _internal.win32_2pc_engine import promoter_helpers as phelp_mod

    gov_repo = _assert_promoter_quarantine_and_hmac_deletions(tmp_path, phelp_mod)
    manifest = gov_repo / ".deleted_files.json"
    manifest.write_text('{"wrong": []}', encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="Formato invalido"):
        phelp_mod.collect_validated_deletions(manifest, gov_repo, gov_repo.resolve(), False)
    manifest.write_text(json.dumps(["nk_genome/PATCH_NOTES.md"]), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="RULE-ORACLE-LOCK"):
        phelp_mod.collect_validated_deletions(manifest, gov_repo, gov_repo.resolve(), False)

    _assert_governance_override_and_git_sync(tmp_path, gov_repo, manifest, phelp_mod)


@pytest.mark.fast
def test_win32_2pc_ratchet_dual_schema_and_oracle_coherence(tmp_path: Path) -> None:
    """Esercita guards_ratchet.py su dual-schema, regressione, oracle_lock e _scan_staging_canonical."""
    from _internal.win32_2pc_engine import guards_ratchet as gr_mod

    m1, p1, t1 = gr_mod._extract_dual_schema_baseline({"pass_rate_pct": 100.0, "total_tests": 95, "failed_tests": 0})
    m2, p2, t2 = gr_mod._extract_dual_schema_baseline({"metrics": {"total_golden_tests": {"value": 98}}, "pass_rate": 100.0})
    _, _, t3 = gr_mod._extract_dual_schema_baseline({"golden_tests_count": 94, "pass_rate": 100.0})
    assert (p1, t1, m1["failed_tests"], p2, t2, m2["unit_tests_pass_pct"], t3) == (100.0, 95, 0, 100.0, 98, 100.0, 94)

    assert _verify_quality_baseline_ratchet({"pass_rate_pct": 100.0, "total_tests": 95})["verdict"] == "PASS"
    for bad_d in ({"total_tests": 95}, {"pass_rate_pct": 98.0, "total_tests": 95}):
        with pytest.raises(TwoPhaseCommitError):
            _verify_quality_baseline_ratchet(bad_d)

    single_bl, bad_single = tmp_path / "single_bl.json", tmp_path / "bad_single.json"
    single_bl.write_text(json.dumps({"pass_rate_pct": 100.0, "total_tests": 100}), encoding="utf-8")
    bad_single.write_text(json.dumps({"pass_rate_pct": 95.0, "total_tests": 100}), encoding="utf-8")
    assert _verify_quality_baseline_ratchet(single_bl)["verdict"] == "PASS"
    with pytest.raises(TwoPhaseCommitError):
        _verify_quality_baseline_ratchet(bad_single)

    ws = tmp_path / "ws_ratchet"
    (ws / "nk_tracking").mkdir(parents=True)
    bl_file = ws / "nk_tracking" / "quality_baseline.json"
    bl_file.write_text(json.dumps({"metrics": {"unit_tests_pass_pct": {"value": 100.0}, "unit_tests_total": {"value": 96}}}), encoding="utf-8")
    (ws / "nk_tracking" / "oracle_lock.json").write_text("{corrupt", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="Regressione"):
        _verify_quality_baseline_ratchet(bl_file)

    stg = ws / ".staging"
    (stg / "scripts").mkdir(parents=True)
    (stg / "docs").mkdir(parents=True)
    (stg / "scripts" / "valid.py").write_text("X = 1\n", encoding="utf-8")
    (stg / "scripts" / "skip.tmp").write_text("tmp", encoding="utf-8")
    (stg / "docs" / "note.md").write_text("# Doc\n", encoding="utf-8")
    assert [p.name for p in gr_mod._scan_staging_canonical(stg, ws.resolve(), subdirs=["scripts"])] == ["valid.py"]

    raw_trail = Path(("\\\\?\\" + str((stg / "scripts").resolve() / "bad_name ")) if os.name == "nt" else str(stg / "scripts" / "bad_name "))
    raw_trail.write_text("x", encoding="utf-8")
    try:
        with pytest.raises(TwoPhaseCommitError, match="Win32"):
            gr_mod._scan_staging_canonical(stg, ws.resolve())
    finally:
        raw_trail.unlink(missing_ok=True)


@pytest.mark.fast
def test_win32_2pc_staging_guards_dast_fail_and_dryrun(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Esercita staging_guards.py su JSON, cleanup, purge, DAST failed status e dry-run gate."""
    _ = isolated_nk_env
    from _internal.win32_2pc_engine import staging_guards as sg_mod

    stg = tmp_path / ".staging"
    (stg / "sub" / "__pycache__").mkdir(parents=True)
    ok_json, non_json = stg / "ok_bom.json", stg / "readme.txt"
    ok_json.write_bytes(b"\xef\xbb\xbf" + b'{"ok": true}')
    non_json.write_text("hello", encoding="utf-8")
    assert sg_mod.validate_staging_json_files(stg, [ok_json, non_json]) == (True, [])

    bad_utf8, ufffd_json, syntax_json, missing_json = stg / "bad_utf8.json", stg / "ufffd.json", stg / "syntax.json", stg / "missing.json"
    bad_utf8.write_bytes(b"\xff\xfe\x00")
    ufffd_json.write_text('{"bad": "\ufffd"}', encoding="utf-8")
    syntax_json.write_text("{bad", encoding="utf-8")
    ok_all, errs_all = sg_mod.validate_staging_json_files(stg, [bad_utf8, ufffd_json, syntax_json, missing_json])
    assert ok_all is False and len(errs_all) == 4

    (stg / "sub" / "residual.tmp").write_text("tmp", encoding="utf-8")
    (stg / "sub" / "__pycache__" / "x.pyc").write_bytes(b"0")
    del_m = stg / ".deleted_files.json"
    del_m.write_text("[]", encoding="utf-8")
    sg_mod._cleanup_promoted_staging(stg, [ok_json, non_json, bad_utf8, ufffd_json, syntax_json], del_m)
    assert (stg / ".gitkeep").is_file() and not del_m.exists()

    prod_root = tmp_path / "prod_purge"
    (prod_root / "scripts" / "__pycache__").mkdir(parents=True)
    (prod_root / "scripts" / "__pycache__" / "mod.pyc").write_bytes(b"pyc")
    (prod_root / "scripts" / "orphan.pyo").write_bytes(b"pyo")
    sg_mod._purge_production_bytecode(prod_root)
    assert not (prod_root / "scripts" / "__pycache__").exists() and not (prod_root / "scripts" / "orphan.pyo").exists()

    valid_rep = tmp_path / "valid_dast.json"
    valid_rep.write_text(json.dumps({"status": "PASS", "is_dry_run": False}), encoding="utf-8")
    sg_mod.validate_sandbox_report_not_dry_run(valid_rep)
    with pytest.raises(TwoPhaseCommitError):
        sg_mod.validate_sandbox_report_not_dry_run(tmp_path / "absent_dast.json")
    with pytest.raises(TwoPhaseCommitError):
        sg_mod.validate_sandbox_report_not_dry_run({"status": "DRY_RUN_PASS", "is_dry_run": True})

    # Folded from test_wave1_dast_report_failed_status_blocks_promotion
    repo_fail = tmp_path / "repo_dast_fail"
    (repo_fail / ".staging" / "scripts").mkdir(parents=True)
    (repo_fail / ".staging" / "scripts" / "target.py").write_text("X = 1\n", encoding="utf-8")
    for bad_payload in (
        {"status": "PASS", "is_dry_run": False, "passed": False},
        {"status": "FAIL", "is_dry_run": False},
        {"status": "FAILED", "is_dry_run": False},
        {"status": "ERROR", "is_dry_run": False},
        {"status": "EXPLOIT_CONFIRMED", "is_dry_run": False},
    ):
        with pytest.raises(TwoPhaseCommitError, match="fallito"):
            promote_staging_to_production(repo_root=repo_fail, sandbox_report=bad_payload)
        assert not (repo_fail / "scripts" / "target.py").exists()
    (repo_fail / ".staging" / "nk_tracking").mkdir(parents=True)
    (repo_fail / ".staging" / "nk_tracking" / "dast_report_w1.json").write_text(json.dumps({"status": "PASS", "is_dry_run": False, "passed": False}), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="fallito"):
        promote_staging_to_production(repo_root=repo_fail)
    assert not (repo_fail / "scripts" / "target.py").exists()


def _assert_hmac_hook_hardening_and_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str, valid_tok: str) -> None:
    from _internal.win32_2pc_engine.governance_auth import resolve_governance_hmac_key_path

    hook_mod = load_nk_script_module("nk_hook_gate")
    monkeypatch.setenv("NK_ALLOW_GOVERNANCE_OVERRIDE", "1")
    ws = tmp_path / "ws_w1_hook"
    (ws / "scripts").mkdir(parents=True)
    cmd_no_tok = "python scripts/win32_2pc_engine.py --promote-staging --allow-governance-override"
    assert (
        hook_mod._classify_protected_target("", cmd_no_tok, ws)["decision"],
        hook_mod._classify_protected_target("", f"{cmd_no_tok} --override-reason {reason} --governance-token bad_tok", ws)["decision"],
        hook_mod._classify_protected_target("", "$env:NK_ALLOW_GOVERNANCE_OVERRIDE='1'; python scripts/win32_2pc_engine.py --promote-staging", ws)["decision"],
        hook_mod._classify_protected_target("", f'{cmd_no_tok} --override-reason "{reason}" --governance-token "{valid_tok}"', ws),
    ) == ("deny", "deny", "deny", {})

    monkeypatch.delenv("NK_GOVERNANCE_HMAC_KEY_PATH", raising=False)
    local_app = tmp_path / "local_app"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app))
    assert resolve_governance_hmac_key_path() == (local_app / "nk_hub" / "governance_hmac.key").resolve()
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert resolve_governance_hmac_key_path() == (Path(tempfile.gettempdir()) / "nk_hub" / "governance_hmac.key").resolve()


@pytest.mark.integration
def test_wave1_governance_hmac_key_fallback_and_hook_hardening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Valida token HMAC fail-closed, CLI token, fallback LOCALAPPDATA/tempdir e hook hardening."""
    _ = isolated_nk_env
    key_p = tmp_path / "ext_auth" / "gov_hmac.key"
    monkeypatch.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_p))
    monkeypatch.delenv("NK_GOVERNANCE_TOKEN", raising=False)
    with pytest.raises(TwoPhaseCommitError, match="assente"):
        verify_governance_token("v1:1700000000:abcd:" + ("0" * 64), "valid_reason_123")

    assert (ensure_governance_hmac_key(), key_p.is_file()) == (key_p.resolve(), True)
    reason = "wave1_cli_override_reason"
    valid_tok = mint_governance_token(reason)
    assert verify_governance_token(valid_tok, reason)["valid"] is True
    now_s = int(time.time())
    for bad_tok in ("", "invalid", "v1:abc:123:" + ("a" * 64), mint_governance_token(reason, ts=now_s - 1000), mint_governance_token(reason, ts=now_s + 60), valid_tok[:-1] + ("0" if valid_tok[-1] != "0" else "1")):
        with pytest.raises(TwoPhaseCommitError):
            verify_governance_token(bad_tok, reason)
    with pytest.raises(TwoPhaseCommitError):
        verify_governance_token(valid_tok, "different_override_reason")

    repo = tmp_path / "repo_hmac_deny"
    (repo / "nk_tracking").mkdir(parents=True)
    (repo / ".staging" / "nk_tracking").mkdir(parents=True)
    (repo / "nk_tracking" / "oracle_lock.json").write_text('{"combined_sha256": "orig"}', encoding="utf-8")
    (repo / ".staging" / "nk_tracking" / "oracle_lock.json").write_text('{"combined_sha256": "w1"}', encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="Token governance"):
        promote_staging_to_production(repo_root=repo, allow_governance_override=True, governance_override_reason=reason, cleanup_staging=False)
    rc_cli, out_cli, _ = call_script_main_captured(_w2pc_mod, ["--promote-staging", "--repo-root", str(repo), "--allow-governance-override", "--override-reason", reason, "--governance-token", valid_tok])
    assert (rc_cli, json.loads(out_cli)["governance_override_recorded"], json.loads((repo / "nk_tracking" / "oracle_lock.json").read_text(encoding="utf-8"))["combined_sha256"]) == (0, True, "w1")
    _assert_hmac_hook_hardening_and_fallback(tmp_path, monkeypatch, reason, valid_tok)


def _assert_oracle_holdout_lock_cli_cycle(tmp_path: Path, tr_mod: Any, capsys: pytest.CaptureFixture[str]) -> None:
    ws_lock = tmp_path / "ws_lock_w1"
    hold_dir = ws_lock / "nk_tracking" / "oracle_holdout"
    hold_dir.mkdir(parents=True)
    hold_f = hold_dir / "h1.json"
    hold_f.write_text('{"id": "h1"}\n', encoding="utf-8")
    capsys.readouterr()
    assert tr_mod.main(["oracle-lock", "freeze", "--root", str(ws_lock), "--target", "nk_tracking/oracle_holdout", "--lock-file", "nk_tracking/oracle_lock_holdout.json"]) == 0
    assert (json.loads(capsys.readouterr().out)["status"], (ws_lock / "nk_tracking" / "oracle_lock_holdout.json").is_file()) == ("LOCKED", True)
    assert tr_mod.main(["oracle-lock", "verify", "--root", str(ws_lock), "--lock-file", "nk_tracking/oracle_lock_holdout.json"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    hold_f.write_text('{"id": "tampered"}\n', encoding="utf-8")
    assert tr_mod.main(["oracle-lock", "verify", "--root", str(ws_lock), "--lock-file", "nk_tracking/oracle_lock_holdout.json"]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False


@pytest.mark.fast
def test_wave1_compliance_unified_parser_and_oracle_lock_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Valida protezione .md governance, correlazione multi-call e --lock-file su oracle-lock."""
    tr_mod, comp_mod = load_nk_script_module("nk_transcript_tools"), load_nk_script_module("nk_compliance_checker")
    assert (comp_mod._is_production_code_write(".agents/AGENTS.md"), comp_mod._is_production_code_write(".agents/skills/NK-Security-Auditor/SKILL.md"), comp_mod._is_production_code_write("docs/notes.md")) == (True, True, False)

    tp_pending = tmp_path / "pending_multi.jsonl"
    tp_pending.write_text(
        "\n".join([
            json.dumps({"step_index": 1, "source": "USER_EXPLICIT", "content": "Verifica multi call"}),
            json.dumps({"step_index": 2, "source": "MODEL", "tool_calls": [{"id": "c1", "name": "read_file"}, {"id": "c2", "name": "run_command", "arguments": {"CommandLine": "python scripts/rsi_convergence_engine.py"}}]}),
            json.dumps({"step_index": 3, "source": "MODEL", "tool_calls": [{"id": "c3", "name": "read_file"}]}),
            json.dumps({"step_index": 4, "source": "TOOL", "tool_call_id": "c1", "status": "ERROR", "content": "FileNotFoundError: missing"}),
            json.dumps({"step_index": 5, "source": "TOOL", "tool_call_id": "c2", "content": "The command exited with code 0\nCONVERGED_OPTIMAL"}),
            json.dumps({"step_index": 6, "source": "MODEL", "content": "Stato: CONVERGED_OPTIMAL con EXIT CODE 0."}),
        ]) + "\n",
        encoding="utf-8",
    )
    events = tr_mod.parse_transcript_events(tp_pending)
    ev_res, ev_rc = tr_mod.check_evidence(tp_pending)
    assert (events[3]["corr_tool"], events[4]["corr_tool"], ev_rc, ev_res["verified_exit_zero"]) == ("read_file", "run_command", 0, True)
    assert (tr_mod.analyze_compliance(tp_pending)["blind_read_errors"], comp_mod.NKComplianceChecker(workspace_root=tmp_path).audit_transcript(tp_pending)["metrics"]["blind_read_errors"]) == (1, 1)
    _assert_oracle_holdout_lock_cli_cycle(tmp_path, tr_mod, capsys)


@pytest.mark.integration
def test_p0_bug_05_task_ledger_multiprocess_concurrent_hash_chain(tmp_path: Path) -> None:
    """Verifica scrittori multi-processo concorrenti su TaskLedger con integrita catena SHA-256."""
    from schemas.dual_ledgers import TaskLedger

    ledger_path = tmp_path / "mp_task_dag.jsonl"
    worker_code = (
        "import sys; "
        f"sys.path[:0] = [{str(STAGING_SCRIPTS_DIR)!r}, {str(SCRIPTS_DIR)!r}]; "
        "from schemas.dual_ledgers import TaskLedger; "
        "lp, wid, cnt = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); "
        "tl = TaskLedger(lp); "
        "[tl.add_task(f'W{wid}_T{i}', 'BUILD', 'NK-Builder', payload={'w': wid, 'i': i}) for i in range(cnt)]"
    )
    procs = [subprocess.Popen([sys.executable, "-B", "-c", worker_code, str(ledger_path), str(w), "4"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for w in range(4)]
    for p in procs:
        out, err = p.communicate(timeout=15.0)
        assert p.returncode == 0, f"{out}\n{err}"
    verified = TaskLedger(ledger_path)
    tasks = verified.list_tasks()
    ok_dag, msg_dag = verified.verify_dag()
    assert len(tasks) == 16 and len({t.task_id for t in tasks}) == 16 and ok_dag is True, msg_dag


def _promote_with_fresh_or_replay_token(
    repo: Path, key_path: Path, reason: str, first_tok: str, idx: int, *, set_env: bool = False
) -> None:
    """Verifica blocco anti-replay al riuso e promozione riuscita con token fresco."""
    with pytest.MonkeyPatch.context() as mp_ext:
        if set_env:
            mp_ext.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_path))
        if idx == 1:
            with pytest.raises(TwoPhaseCommitError, match="Replay rilevato"):
                promote_staging_to_production(repo_root=repo, allow_governance_override=True, governance_override_reason=reason, governance_token=first_tok, cleanup_staging=False)
        tok_i = first_tok if idx == 0 else mint_governance_token(reason, key_path=key_path)
        res_ok = promote_staging_to_production(repo_root=repo, allow_governance_override=True, governance_override_reason=reason, governance_token=tok_i, cleanup_staging=True)
    assert (res_ok["status"], res_ok["governance_override_recorded"]) == ("SUCCESS", True)


def _assert_wave0_extended_denylist_loop(tmp_path: Path, key_path: Path, tok: str) -> None:
    repo = tmp_path / "w0_repo"
    for idx, rel in enumerate(("scripts/win32_2pc_engine.py", "scripts/_internal/win32_2pc_engine/promoter.py", "scripts/nk_hook_gate.py", "nk_tracking/benchmark_suite/tasks_v1.json", "nk_tracking/oracle_lock_holdout.json")):
        stg_f = repo / ".staging" / rel
        stg_f.parent.mkdir(parents=True, exist_ok=True)
        stg_f.write_text("{}" if rel.endswith(".json") else "X = 1\n", encoding="utf-8")
        with pytest.raises(TwoPhaseCommitError, match="RULE-ORACLE-LOCK"):
            promote_staging_to_production(repo_root=repo, cleanup_staging=False)
        with pytest.raises(TwoPhaseCommitError, match="override-reason"):
            promote_staging_to_production(repo_root=repo, allow_governance_override=True, cleanup_staging=False)
        _promote_with_fresh_or_replay_token(repo, key_path, "wave0_extended_denylist_audit", tok, idx, set_env=True)


def _assert_wave0_ratchet_and_dry_run(tmp_path: Path, key_path: Path) -> None:
    bl_repo = tmp_path / "w0_auto_ratchet"
    (bl_repo / "nk_tracking").mkdir(parents=True)
    (bl_repo / ".staging" / "nk_tracking").mkdir(parents=True)
    base_m = {"total_golden_tests": {"value": 120, "direction": "higher_is_better"}, "unit_tests_total": {"value": 120, "direction": "higher_is_better"}, "unit_tests_passed": {"value": 120, "direction": "higher_is_better"}, "pass_rate_pct": {"value": 100.0, "direction": "higher_is_better"}, "failed_tests": {"value": 0, "direction": "lower_is_better"}, "tests_skipped": {"value": 0, "direction": "lower_is_better"}, "pytest_duration_s": {"value": 20.0, "direction": "lower_is_better"}}
    reg_m = dict(base_m, total_golden_tests={"value": 100, "direction": "higher_is_better"}, unit_tests_total={"value": 100, "direction": "higher_is_better"}, unit_tests_passed={"value": 100, "direction": "higher_is_better"})
    (bl_repo / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": base_m}), encoding="utf-8")
    (bl_repo / ".staging" / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": reg_m}), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="Regressione"):
        promote_staging_to_production(repo_root=bl_repo, verify_baseline=False)
    with pytest.MonkeyPatch.context() as mp_rat:
        mp_rat.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_path))
        mp_rat.setenv("NK_GOVERNANCE_TOKEN", mint_governance_token("wave0_ratchet_down_audit_test", key_path=key_path))
        assert promote_staging_to_production(repo_root=bl_repo, verify_baseline=False, allow_governance_override=True, governance_override_reason="wave0_ratchet_down_audit_test")["governance_override_recorded"] is True

    dry_repo = tmp_path / "w0_dry_repo"
    (dry_repo / ".staging" / "scripts").mkdir(parents=True)
    (dry_repo / ".staging" / "scripts" / "ok.py").write_text("OK = 1\n", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="dry-run"):
        promote_staging_to_production(repo_root=dry_repo, sandbox_report={"status": "DRY_RUN", "is_dry_run": True})
    (dry_repo / ".staging" / "nk_tracking").mkdir(parents=True)
    (dry_repo / ".staging" / "nk_tracking" / "dast_report_w0.json").write_text('{"status": "PASS", "dry_run": true}', encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="dry-run"):
        promote_staging_to_production(repo_root=dry_repo)
    assert not (dry_repo / "scripts" / "ok.py").exists()


@pytest.mark.integration
def test_wave0_2pc_extended_denylist_auto_ratchet_and_dry_run(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Wave 0: valida denylist estesa, auto-ratchet baseline e blocco dry-run sandbox."""
    _ = isolated_nk_env
    key_path = tmp_path / "gov_w0_hmac.key"
    ensure_governance_hmac_key(key_path)
    tok = mint_governance_token("wave0_extended_denylist_audit", key_path=key_path)
    _assert_wave0_extended_denylist_loop(tmp_path, key_path, tok)
    _assert_wave0_ratchet_and_dry_run(tmp_path, key_path)
    assert tok.startswith("v1:")


@pytest.mark.integration
def test_wave1_protected_paths_ast_rsi_tests_and_deleted_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Wave 1: nuovi path protetti e tombstone .deleted_files.json protetti tramite HMAC anti-replay."""
    _ = isolated_nk_env
    key_p = tmp_path / "gov_w1_paths.key"
    monkeypatch.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(key_p))
    ensure_governance_hmac_key(key_p)
    reason = "wave1_protected_paths_audit"
    tok_first = mint_governance_token(reason, key_path=key_p)

    protected_rels = (
        "scripts/ast_guard_validator.py", "scripts/_internal/ast_guard_validator/validator.py",
        "scripts/rsi_convergence_engine.py", "scripts/_internal/rsi_convergence_engine/profiles.py",
        "tests/test_sample_protected.py", "nk_tracking/quality_baseline.json",
        "nk_tracking/governance_lock.json", "nk_tracking/oracle_lock_holdout.json",
    )
    repo = tmp_path / "repo_w1_paths"
    for idx, rel in enumerate(protected_rels):
        stg_f = repo / ".staging" / rel
        stg_f.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"metrics": {"unit_tests_pass_pct": {"value": 100.0}, "unit_tests_total": {"value": 100}}}) if rel.endswith("quality_baseline.json") else ("{}" if rel.endswith(".json") else f"W1_VAL = {idx}\n")
        stg_f.write_text(body, encoding="utf-8")
        with pytest.raises(TwoPhaseCommitError, match="RULE-ORACLE-LOCK"):
            promote_staging_to_production(repo_root=repo, cleanup_staging=False)
        with pytest.raises(TwoPhaseCommitError, match="Token governance"):
            promote_staging_to_production(repo_root=repo, allow_governance_override=True, governance_override_reason=reason, cleanup_staging=False)
        _promote_with_fresh_or_replay_token(repo, key_p, reason, tok_first, idx, set_env=False)

    del_repo = tmp_path / "repo_w1_del_manifest"
    (del_repo / ".staging").mkdir(parents=True)
    (del_repo / ".deleted_files.json").write_text("[]", encoding="utf-8")
    (del_repo / ".staging" / ".deleted_files.json").write_text(json.dumps([".deleted_files.json"]), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="RULE-ORACLE-LOCK"):
        promote_staging_to_production(repo_root=del_repo, cleanup_staging=False)
    tok_del = mint_governance_token(reason, key_path=key_p)
    assert ".deleted_files.json" in promote_staging_to_production(repo_root=del_repo, allow_governance_override=True, governance_override_reason=reason, governance_token=tok_del)["deleted_files"]


@pytest.mark.integration
def test_git_sync_2pc_and_handoff_stash_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Migrated: 2PC git_sync con cancellazioni e handoff git stash su repository git reale."""
    _ = isolated_nk_env
    hand_mod = load_nk_script_module("nk_session_handoff")
    pr_mod = load_nk_script_module("platform_runner")

    git_ws = tmp_path / "git_2pc_ws"
    for d in (".staging/scripts", "scripts", "nk_tracking"):
        (git_ws / d).mkdir(parents=True)
    obsolete_f, tracked_f = git_ws / "scripts" / "obsolete_mod.py", git_ws / "scripts" / "tracked_mod.py"
    obsolete_f.write_text("OLD = 1\n", encoding="utf-8")
    tracked_f.write_text("V = 1\n", encoding="utf-8")
    git_exe = hand_mod._resolve_git_executable()
    disc_tp = hand_mod._discover_default_transcript()
    assert disc_tp is None or disc_tp == "" or disc_tp.endswith(".jsonl")
    pr_mod.safe_subprocess_run([git_exe, "init"], cwd=str(git_ws))
    pr_mod.safe_subprocess_run([git_exe, "add", "scripts/obsolete_mod.py", "scripts/tracked_mod.py"], cwd=str(git_ws))
    pr_mod.safe_subprocess_run([git_exe, "-c", "user.email=nk@example.com", "-c", "user.name=NK Test", "commit", "-m", "init"], cwd=str(git_ws))
    tracked_f.write_text("V = 2\n", encoding="utf-8")
    is_dirty, stash_patch = hand_mod._check_git_dirty_fast(git_ws, git_exe, stash_output_dir=str(tmp_path / "handoff_stash_out"))
    assert is_dirty is True and stash_patch is not None and Path(stash_patch).is_file()
    if Path(git_exe).is_file():
        monkeypatch.setenv("PATH", f"{Path(git_exe).parent}{os.pathsep}{os.environ.get('PATH', '')}")
    (git_ws / ".staging" / "scripts" / "promoted_new.py").write_text("PROMOTED = 42\n", encoding="utf-8")
    (git_ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["scripts/obsolete_mod.py"]), encoding="utf-8")
    prom_res = promote_staging_to_production(repo_root=git_ws, verify_baseline=False, cleanup_staging=True, git_sync=True, milestone="NK-MS-TEST-GIT-SYNC")
    assert prom_res["status"] == "SUCCESS" and not obsolete_f.exists() and (git_ws / "scripts" / "promoted_new.py").exists()

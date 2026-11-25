# -*- coding: utf-8 -*-
"""Burst test @pytest.mark.fast per governance, mutex, io_and_paths, journal, compliance e resilience."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import time
from typing import Any, Dict, List
import pytest

from _internal.nk_compliance_checker import rules_evaluator as re_mod
from _internal.nk_transcript_tools import oracle_and_grounding as og_mod
from _internal.win32_2pc_engine import constants as consts_mod, governance_auth as gauth, io_and_paths as iop, staging_guards as sg_mod

try:
    from conftest import WORKSPACE_ROOT as _WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT as _WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module

_w2pc_mod = load_nk_script_module("win32_2pc_engine")
TwoPhaseCommitError = _w2pc_mod.TwoPhaseCommitError
Win32LockError = _w2pc_mod.Win32LockError
Win32LockTimeoutError = _w2pc_mod.Win32LockTimeoutError
Win32NamedMutex = _w2pc_mod.Win32NamedMutex
BatchJournalV2 = _w2pc_mod.BatchJournalV2

hook_mod = load_nk_script_module("nk_hook_gate")
comp_mod = load_nk_script_module("nk_compliance_checker")
clean_mod = load_nk_script_module("safe_cleanup_dev_servers")
cache_mod = load_nk_script_module("deterministic_api_cache")
map_mod = load_nk_script_module("ast_repo_mapper")
idx_mod = load_nk_script_module("nk_registry_indexer")
mem_mod = load_nk_script_module("memory_3tier_engine")
pre_mod = load_nk_script_module("preflight_health_check")
boot_mod = load_nk_script_module("nk_session_bootstrap")
rsi_mod = load_nk_script_module("rsi_convergence_engine")
sentry_mod = load_nk_script_module("nk_context_sentry")
hand_mod = load_nk_script_module("nk_session_handoff")
qbm_mod = load_nk_script_module("quality_baseline_manager")


class _FakeFcntl:
    """Stub deterministico POSIX fcntl per flock senza syscall reali."""

    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

    def __init__(self, fail_once: bool = False, always_block: bool = False) -> None:
        self.fail_once, self.always_block, self.ops = fail_once, always_block, []

    def flock(self, _fd: int, op: int) -> None:
        self.ops.append(op)
        if op & self.LOCK_UN:
            return
        if self.always_block:
            raise BlockingIOError("busy")
        if self.fail_once:
            self.fail_once = False
            raise BlockingIOError("retry_once")


class _FakeKernel32:
    """Stub deterministico Win32 kernel32 per handle, fallback Local e timeout."""

    def __init__(self, wait_code: int = 0, access_denied_global: bool = False, bad_handle: bool = False) -> None:
        self.wait_code, self.access_denied_global, self.bad_handle = wait_code, access_denied_global, bad_handle
        self.created: List[str] = []
        self.closed: List[int] = []
        self.released: List[int] = []
        self.tid = 101

    def GetCurrentThreadId(self) -> int:
        return self.tid

    def GetLastError(self) -> int:
        return 5 if self.access_denied_global else 0

    def CreateMutexW(self, _sa: Any, _own: bool, name: str) -> int:
        self.created.append(name)
        if self.bad_handle:
            return consts_mod.INVALID_HANDLE_VALUE
        if self.access_denied_global and name.startswith("Global\\"):
            return 0
        return 777

    def WaitForSingleObject(self, _h: int, _ms: int) -> int:
        return self.wait_code

    def ReleaseMutex(self, handle: int) -> bool:
        self.released.append(handle)
        return True

    def CloseHandle(self, handle: int) -> bool:
        self.closed.append(handle)
        return True

    def GetFileAttributesW(self, _path: str) -> int:
        return consts_mod.FILE_ATTRIBUTE_REPARSE_POINT


def _base_compliance_counters() -> Dict[str, Any]:
    return {
        "total_steps": 5, "total_tool_calls": 10, "polling_calls": 0, "subagents_invoked": 1,
        "subagents_polled": 0, "write_calls": 0, "code_write_calls": 0, "external_unstage_writes": 0,
        "ast_guard_executed": True, "healing_loop_executed": True, "win32_2pc_executed": True,
        "bootstrap_executed": True, "meta_prompt_gate_executed": True, "has_non_exempt_user_turn": True,
        "max_direct_tool_calls_streak": 0, "blind_read_errors": 0, "write_burst_steps": 0,
        "command_error_steps": 0, "error_steps": 0,
    }


@pytest.mark.fast
def test_w1_mutex_posix_reentrant_timeout_and_missing_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre rami POSIX flock, rientranza map, cross-thread, timeout zero-sleep e idle release."""
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: None)
    monkeypatch.setattr(consts_mod, "_fcntl", None)
    monkeypatch.setattr(time, "sleep", lambda _sec: None)

    plain = Win32NamedMutex("PlainLocal", timeout_ms=20, is_path=False)
    assert plain._local_fallback_name == "PlainLocal"
    with pytest.raises(Win32LockError, match="Nessun backend"):
        plain.acquire()

    fake_fcntl = _FakeFcntl(fail_once=True)
    monkeypatch.setattr(consts_mod, "_fcntl", fake_fcntl)
    with Win32NamedMutex("Global\\W1Posix", timeout_ms=consts_mod.INFINITE, is_path=False) as outer:
        assert outer.acquired is True
        outer.acquire()
        inner = Win32NamedMutex("Global\\W1Posix", timeout_ms=100, is_path=False)
        inner.acquire()
        outer._owning_thread_id = -999
        with pytest.raises(Win32LockError, match="affinity"):
            outer.acquire()
        with pytest.raises(Win32LockError, match="affinity"):
            outer.release()
        outer._owning_thread_id = inner._owning_thread_id
        inner.release()
        outer.release()
    assert fake_fcntl.LOCK_UN in fake_fcntl.ops

    idle_posix = Win32NamedMutex("W1IdlePosix", is_path=False)
    idle_posix.handle = os.open(str(tmp_path / "idle.lock"), os.O_CREAT | os.O_RDWR)
    idle_posix.release()
    assert idle_posix.handle is None

    monkeypatch.setattr(consts_mod, "_fcntl", _FakeFcntl(always_block=True))
    ticks = iter([1.0, 1.0, 5.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks, 5.0))
    with pytest.raises(Win32LockTimeoutError):
        Win32NamedMutex("Global\\W1Timeout", timeout_ms=5, is_path=False).acquire()


@pytest.mark.fast
def test_w1_mutex_win32_branches_abandoned_timeout_fallback_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre rami Win32: Local fallback, WAIT_ABANDONED, WAIT_TIMEOUT, affinity e cleanup."""
    k32_ab = _FakeKernel32(wait_code=consts_mod.WAIT_ABANDONED_0, access_denied_global=True)
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: k32_ab)
    with Win32NamedMutex("Global\\W1WinFallback", timeout_ms=50, is_path=False) as mtx:
        assert mtx.abandoned is True
        assert mtx.abandoned_recovered is True
        assert any(n.startswith("Local\\") for n in k32_ab.created)
        mtx.acquire()
        mtx.release()
        k32_ab.tid = 202
        with pytest.raises(Win32LockError, match="affinity"):
            mtx.release()
        k32_ab.tid = 101
    assert 777 in k32_ab.released and 777 in k32_ab.closed

    k32_to = _FakeKernel32(wait_code=consts_mod.WAIT_TIMEOUT)
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: k32_to)
    with pytest.raises(Win32LockTimeoutError):
        Win32NamedMutex("W1WinTO", timeout_ms=5, is_path=False).acquire()
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: _FakeKernel32(wait_code=999))
    with pytest.raises(Win32LockError, match="WaitForSingleObject failed"):
        Win32NamedMutex("W1WinErr", timeout_ms=5, is_path=False).acquire()
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: _FakeKernel32(bad_handle=True))
    with pytest.raises(Win32LockError, match="Failed to create"):
        Win32NamedMutex("W1WinBad", timeout_ms=5, is_path=False).acquire()

    idle = Win32NamedMutex("W1Idle", is_path=False)
    idle.handle = 555
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: k32_to)
    idle.release()
    assert idle.handle is None


@pytest.mark.fast
def test_w1_governance_auth_key_verify_and_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre key dir/vuota, mint validation e verifica HMAC fail-closed con override."""
    dir_key = tmp_path / "dir_not_file"
    dir_key.mkdir()
    with pytest.raises(TwoPhaseCommitError, match="assente"):
        gauth.verify_governance_token("v1:1700000000:abcd:" + ("a" * 64), "valid_reason_1", key_path=dir_key)
    empty_key = tmp_path / "empty.key"
    empty_key.write_text("   \n", encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="vuota"):
        gauth.verify_governance_token("v1:1700000000:abcd:" + ("a" * 64), "valid_reason_1", key_path=empty_key)

    key_p = tmp_path / "ext" / "gov.key"
    assert gauth.ensure_governance_hmac_key(key_p) == key_p.resolve()
    assert gauth.ensure_governance_hmac_key(key_p) == key_p.resolve()
    with pytest.raises(TwoPhaseCommitError, match="Override reason"):
        gauth.mint_governance_token("   ", key_path=key_p)
    with pytest.raises(TwoPhaseCommitError, match="Timestamp"):
        gauth.mint_governance_token("valid_reason_1", key_path=key_p, ts=True)  # type: ignore[arg-type]
    with pytest.raises(TwoPhaseCommitError, match="Nonce"):
        gauth.mint_governance_token("valid_reason_1", key_path=key_p, nonce="zz!")

    auto_key = tmp_path / "auto_mint.key"
    tok = gauth.mint_governance_token("valid_reason_1", key_path=auto_key, nonce="AB12")
    assert gauth.verify_governance_token(tok, "valid_reason_1", key_path=auto_key)["valid"] is True

    now_s = int(time.time())
    expired_tok = gauth.mint_governance_token("valid_reason_1", key_path=auto_key, ts=now_s - 1000)
    future_tok = gauth.mint_governance_token("valid_reason_1", key_path=auto_key, ts=now_s + 60)
    altered_tok = tok[:-1] + ("1" if tok.endswith("0") else "0")
    for bad in ("v2:1:aa:" + ("0" * 64), "v1:1:zz:" + ("0" * 64), "v1:1:ab:short", "v1:1:ab:" + ("z" * 64), expired_tok, future_tok, altered_tok):
        with pytest.raises(TwoPhaseCommitError):
            gauth.verify_governance_token(bad, "valid_reason_1", key_path=auto_key)
    with pytest.raises(TwoPhaseCommitError, match="TTL"):
        gauth.verify_governance_token(tok, "valid_reason_1", key_path=auto_key, ttl_sec=0)
    with pytest.raises(TwoPhaseCommitError, match="Override reason"):
        gauth.verify_governance_token(tok, "", key_path=auto_key)
    monkeypatch.setenv("NK_GOVERNANCE_TOKEN", tok)
    assert gauth.authorize_governance_override("valid_reason_1", None, "ctx.json", key_path=auto_key)["valid"] is True


@pytest.mark.fast
def test_w1_io_and_paths_retries_reparse_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre _replace_with_retry, _atomic_write_bytes, reparse esterno e canonicalizzazione."""
    sleeps: List[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    attempts = {"n": 0}

    def _flaky_replace(_src: Path, _dst: Path) -> None:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", _flaky_replace)
    iop._replace_with_retry(tmp_path / "a", tmp_path / "b", retries=3, delay_sec=0.01)
    assert attempts["n"] == 3 and len(sleeps) == 2

    def _hard_err(_src: Path, _dst: Path) -> None:
        raise FileNotFoundError(2, "missing")

    monkeypatch.setattr(os, "replace", _hard_err)
    with pytest.raises(FileNotFoundError):
        iop._replace_with_retry(tmp_path / "a", tmp_path / "b", retries=3)
    monkeypatch.setattr(iop, "_common_atomic_write_bytes", lambda *_a, **_k: (False, "disk_err"))
    with pytest.raises(OSError, match="disk_err"):
        iop._atomic_write_bytes(tmp_path / "out.bin", b"data")

    assert iop._extract_patch_notes_headers("## [v1.0.0]\ntext") == ["## [v1.0.0]"]
    assert iop._resolve_repo_root(None).is_dir()
    for bad_rel in ("", "sub/a:ads", "a/../b", "sub/bad ", "./"):
        with pytest.raises(TwoPhaseCommitError):
            iop._validate_win32_canonical_rel_path(bad_rel)

    real_root = tmp_path.resolve()
    monkeypatch.setattr(consts_mod, "_get_active_kernel32", lambda: _FakeKernel32(access_denied_global=True))
    assert consts_mod._get_win32_last_error() == 5
    outside = Path("C:/outside_target/file.py")
    monkeypatch.setattr(os.path, "realpath", lambda _p, strict=False: str(outside))
    with pytest.raises(TwoPhaseCommitError, match="junction esterna"):
        iop._assert_no_external_reparse(tmp_path / "sub" / "f.py", real_root)


@pytest.mark.fast
def test_w1_journal_dedup_cleanup_corrupt_and_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre BatchJournalV2: dedup, preimage_rel, SHA mismatch, cleanup retry e crash recovery."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    repo = tmp_path / "repo_j"
    (repo / "scripts").mkdir(parents=True)
    target_a = repo / "scripts" / "a.py"
    target_b = repo / "scripts" / "b_new.py"
    target_a.write_text("OLD = 1\n", encoding="utf-8")
    assert BatchJournalV2.recover_crashed_batches(repo) == ([], set())
    assert BatchJournalV2.rollback_from_manifest({"entries": "bad"}) == []

    _, j_root, b_dir = BatchJournalV2.begin_batch(repo, [("scripts/a.py", target_a), ("scripts/a.py", target_a), ("scripts/b_new.py", target_b)])
    leftover = repo / "scripts" / ".shadow_a.py_999.tmp"
    leftover.write_text("leftover", encoding="utf-8")
    target_a.write_text("MUTATED\n", encoding="utf-8")
    target_b.write_text("CREATED\n", encoding="utf-8")

    manifest = json.loads((j_root / "active_batch.json").read_text(encoding="utf-8"))
    manifest["entries"].insert(0, "skip_me")
    restored = BatchJournalV2.rollback_from_manifest(manifest, b_dir)
    assert len(restored) == 2 and not leftover.exists()
    assert target_a.read_text(encoding="utf-8") == "OLD = 1\n" and not target_b.exists()

    rel_entry = {"target_path": str(target_a), "existed_before": True, "preimage_rel": manifest["entries"][1]["preimage_rel"], "preimage_sha256": manifest["entries"][1]["preimage_sha256"]}
    assert BatchJournalV2.rollback_from_manifest({"entries": [rel_entry]}, b_dir) == [str(target_a)]
    with pytest.raises(TwoPhaseCommitError, match="Corruzione SHA-256"):
        BatchJournalV2.rollback_from_manifest({"entries": [dict(rel_entry, preimage_sha256="0" * 64)]}, b_dir)
    with pytest.raises(TwoPhaseCommitError, match="mancante"):
        BatchJournalV2.rollback_from_manifest({"entries": [{"target_path": str(target_a), "existed_before": True, "preimage_file": str(tmp_path / "no.bin")}]})

    (j_root / "active_batch.json").write_text("{bad_json", encoding="utf-8")
    err_rec, _ = BatchJournalV2.recover_crashed_batches(repo)
    assert err_rec and err_rec[0]["action"] == "ERROR"

    orig_rmtree = shutil.rmtree
    rm_calls = {"n": 0}

    def _retry_rmtree(path: Any, ignore_errors: bool = False) -> None:
        rm_calls["n"] += 1
        if rm_calls["n"] > 1:
            orig_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(shutil, "rmtree", _retry_rmtree)
    BatchJournalV2.cleanup_journal(j_root, b_dir)
    monkeypatch.setattr(shutil, "rmtree", orig_rmtree)
    (j_root / "orphan_only").mkdir(parents=True, exist_ok=True)
    rec_clean, _ = BatchJournalV2.recover_crashed_batches(repo)
    assert rm_calls["n"] == 2 and rec_clean == [] and not j_root.exists()


def _assert_cold_audit_sandbox_and_locks(ws: Path) -> None:
    for bad in (
        ["not_dict"], {}, {"status": "UNKNOWN"}, {"status": "PASS", "passed": True, "outcome": "TIMEOUT"},
        {"status": "TIMED_OUT", "passed": True}, {"status": "OOM", "passed": True}, {"status": "UNMEASURED", "passed": True},
        {"status": "PASS", "dast_passed": False}, {"status": "PASS", "success": False}, {"status": "PASS", "timed_out": True},
        {"status": "PASS", "memory_exceeded": True}, {"status": "PASS", "exit_code": 1}, {"outcome": "DRY_RUN_PASS", "passed": True},
    ):
        with pytest.raises(TwoPhaseCommitError):
            sg_mod.validate_sandbox_report_not_dry_run(bad)  # type: ignore[arg-type]
    for good in ({"status": "PASS", "is_dry_run": False}, {"outcome": "BENIGN", "exit_code": True}, {"dast_passed": True}):
        sg_mod.validate_sandbox_report_not_dry_run(good)
    assert (consts_mod.is_protected_governance_path("nk_tracking/tests_holdout_lock.json"), consts_mod.is_protected_governance_path("sub/tests_holdout_lock.json")) == (True, True)
    for tgt in ("tests_holdout_lock.json", "tests/test_x.py", "nk_tracking/oracle_holdout/h1.json", "nk_tracking/benchmark_suite/b.json"):
        assert hook_mod._classify_protected_target(tgt, "", ws)["decision"] == "deny"
    assert hook_mod._classify_protected_target(".staging/tests/test_x.py", "", ws) == {}
    for lf in ("oracle_lock_holdout.json", "tests_holdout_lock.json", "governance_lock.json"):
        assert hook_mod._classify_protected_target("", f"echo x > nk_tracking/{lf}", ws)["decision"] == "deny"


def _assert_cold_qbm_and_external_checks(tmp_path: Path, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "nk_tracking" / "tests_holdout_lock.json").write_text("{}", encoding="utf-8")
    (ws / "nk_tracking" / "keep.json").write_text("{}", encoding="utf-8")
    hashed = og_mod._hash_target_files(ws / "nk_tracking")
    assert ("tests_holdout_lock.json" not in hashed, "keep.json" in hashed) == (True, True)
    manifest = ws / "manifest.json"
    manifest.write_text(json.dumps({"scripts_index": {"./scripts/ok_w1.py": {}, ".hidden_w1.py": {}}}), encoding="utf-8")
    basenames, rels = og_mod._collect_grounding_valid_scripts(ws, manifest)
    assert (".hidden_w1.py" in basenames, "hidden_w1.py" not in basenames, "scripts/ok_w1.py" in rels) == (True, True, True)
    for prot in ("rules/r.md", "skills/s/SKILL.md", "plugins/p/n.md", "nk_tracking/oracle_lock.json", "nk_tracking/tests_holdout_lock.json", "nk_tracking/quality_baseline.json", "nk_tracking/oracle_holdout/a.json", "nk_tracking/benchmark_suite/b.json", "nk_tracking/checkpoint_01.json"):
        assert comp_mod._is_production_code_write(prot) is True
    for ex in (".staging/nk_tracking/oracle_lock.json", "nk_tracking/active_context.md", "nk_tracking/rsi_telemetry.jsonl", "nk_tracking/reports_and_briefs/brief.md", "docs/notes.md", "docs/agents_guide.md"):
        assert comp_mod._is_production_code_write(ex) is False

    b_path = tmp_path / "qbm_cli_baseline.json"
    b_raw = (_WORKSPACE_ROOT / "nk_tracking" / "quality_baseline.json").read_text(encoding="utf-8")
    b_path.write_text(b_raw, encoding="utf-8")
    b_metrics = json.loads(b_raw)["metrics"]
    cur_tot = int(b_metrics["unit_tests_total"]["value"])
    ok_qbm_metrics = {
        "total_golden_tests": cur_tot, "unit_tests_total": cur_tot, "unit_tests_passed": cur_tot,
        "unit_tests_pass_pct": 100.0, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0,
        "pytest_duration_s": 10.0, "statement_coverage_pct": float(b_metrics["statement_coverage_pct"]["value"]),
        "true_branch_coverage_pct": float(b_metrics["true_branch_coverage_pct"]["value"]),
        "combined_coverage_pct": float(b_metrics["combined_coverage_pct"]["value"]),
        "sast_critical_violations": int(b_metrics.get("sast_critical_violations", {}).get("value", 0)),
    }
    bad_qbm_metrics = {**ok_qbm_metrics, "total_golden_tests": cur_tot - 1, "unit_tests_total": cur_tot - 1, "unit_tests_passed": cur_tot - 1}
    assert call_script_main(qbm_mod, ["unknown_verb"], monkeypatch) == 1
    assert call_script_main(qbm_mod, ["check", "--file", str(b_path), "--metrics", "{bad"], monkeypatch) == 1
    assert call_script_main(qbm_mod, ["check", "--file", str(b_path)], monkeypatch) == 1
    assert call_script_main(qbm_mod, ["check", "--file", str(b_path), "--metrics", json.dumps(ok_qbm_metrics)], monkeypatch) == 0
    assert call_script_main(qbm_mod, ["check", "--file", str(b_path), "--metrics", json.dumps(bad_qbm_metrics)], monkeypatch) == 1
    assert call_script_main(qbm_mod, ["recalibrate", "--file", str(b_path), "--target-tests", "70"], monkeypatch) == 1


@pytest.mark.integration
def test_w1_cold_audit_guards_compliance_and_qbm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Cold GT-14: valida payload sandbox, holdout locks, hook/oracle/compliance e CLI QBM."""
    ws = tmp_path / "ws_cold"
    (ws / ".staging" / "tests").mkdir(parents=True)
    _assert_cold_audit_sandbox_and_locks(ws)
    _assert_cold_qbm_and_external_checks(tmp_path, ws, monkeypatch)

    assert (
        comp_mod._is_external_unstage_write("", is_command=False),
        comp_mod._is_external_unstage_write("NK_External_Projects/App/.staging/a.py", is_command=False),
        comp_mod._is_external_unstage_write("NK_External_Projects/App/src_app/a.py", is_command=False),
        comp_mod._is_external_unstage_write("python -m pytest NK_External_Projects/App/tests -q", is_command=True),
        comp_mod._is_external_unstage_write("Set-Content NK_External_Projects/App/src_app/main.py 'x'", is_command=True),
    ) == (False, False, True, False, True)
    assert comp_mod._is_exempt_diagnostic_nonzero('{"status": "FAIL", "scores": {}, "procedural_score": 50}') == "EXEMPT_EXTERNAL_AUDIT"
    assert comp_mod._is_exempt_diagnostic_nonzero('{"status": "REFINING", "delta_k": 5}') == "INTERMEDIATE_REFINING"
    assert comp_mod._is_exempt_diagnostic_nonzero("Traceback: ValueError") == "REAL_ERROR"


def _assert_rules_eval_scoring_and_telemetry(tmp_path: Path) -> tuple[Path, Path]:
    assert re_mod.extract_session_identifier(None) == ""
    assert re_mod.extract_session_identifier(tmp_path / "brain" / "cid_b" / "logs" / "transcript.jsonl") == "cid_b"
    assert re_mod.extract_session_identifier(tmp_path / "cid_s" / "transcript.jsonl") == "cid_s"
    assert re_mod.extract_session_identifier(tmp_path / "sub" / "other.jsonl") == ""
    assert (re_mod.valid_numeric_score(True), re_mod.valid_numeric_score(float("nan")), re_mod.valid_numeric_score(float("inf")), re_mod.valid_numeric_score("5"), re_mod.valid_numeric_score(85)) == (None, None, None, None, 85.0)
    assert (re_mod.score_from_rsi_record([]), re_mod.score_from_rsi_record({"fitness_q": True}), re_mod.score_from_rsi_record({"fitness_q": 150})) == (0, 0, 100.0)  # type: ignore[arg-type]
    assert (re_mod.score_from_rsi_record({"delta_k": None}), re_mod.score_from_rsi_record({"delta_k": 0, "verdict": "FAIL"}), re_mod.score_from_rsi_record({"delta_k": 0, "verdict": "PASS"})) == (0, 0, 100)

    j_p = tmp_path / "recs.jsonl"
    j_p.write_text('\n[1, 2]\n{bad\n{"a": 1}\n{"b": 2}\n', encoding="utf-8")
    assert re_mod.read_jsonl_dicts_reversed(j_p) == [{"b": 2}, {"a": 1}]
    sess_dir = tmp_path / "brain" / "sess_ok"
    sess_dir.mkdir(parents=True)
    tp = sess_dir / "transcript.jsonl"
    tp.write_text('{"step": 1}\n', encoding="utf-8")
    (sess_dir / "rsi_telemetry.jsonl").write_text(
        json.dumps({"session_id": "other_sess", "delta_k": 0, "verdict": "PASS"}) + "\n" + json.dumps({"session_id": "sess_ok", "fitness_q": 92.4}) + "\n",
        encoding="utf-8",
    )
    assert re_mod.lookup_rsi_telemetry_score(tmp_path, tp) == (True, 92.4)
    ws_tele = tmp_path / "ws_tele"
    (ws_tele / "nk_tracking").mkdir(parents=True)
    tp_ws = ws_tele / "cid_anon" / "transcript.jsonl"
    tp_ws.parent.mkdir(parents=True)
    tp_ws.write_text('{"step": 1}\n', encoding="utf-8")
    ws_tel_file = ws_tele / "nk_tracking" / "rsi_telemetry.jsonl"
    ws_tel_file.write_text(
        json.dumps({"session_id": "wrong_id", "fitness_q": 10}) + "\n" + json.dumps({"delta_k": 0, "verdict": "PASS", "timestamp": time.time() - 999999}) + "\n" + json.dumps({"delta_k": 0, "verdict": "PASS", "timestamp": time.time()}) + "\n",
        encoding="utf-8",
    )
    assert re_mod.lookup_rsi_telemetry_score(ws_tele, tp_ws) == (True, 100)
    return ws_tele, tp_ws


@pytest.mark.integration
def test_w1_compliance_rules_evaluator_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre rami mancanti di nk_compliance_checker/rules_evaluator.py."""
    ws_tele, tp_ws = _assert_rules_eval_scoring_and_telemetry(tmp_path)
    tp_skew = tmp_path / "skew" / "transcript.jsonl"
    tp_skew.parent.mkdir()
    tp_skew.write_text("{}", encoding="utf-8")
    os.utime(ws_tele / "nk_tracking" / "rsi_telemetry.jsonl", (time.time() - 500000, time.time() - 500000))
    assert re_mod.lookup_rsi_telemetry_score(ws_tele, tp_skew) == (False, 0)

    checker = comp_mod.NKComplianceChecker(workspace_root=ws_tele)
    statuses = iter(["WARN", "YELLOW", "RED"])

    class _FakeSentry:
        def __init__(self, workspace_root: Path, profile: str) -> None:
            _ = (workspace_root, profile)

        def analyze_transcript(self, _tf: Path, profile: str = "", preloaded_records: Any = None) -> Dict[str, Any]:
            _ = (profile, preloaded_records)
            st = next(statuses, "RED")
            return {"status": st, "step_count": 4, "estimated_tokens": 1200, "actual_context_tokens": 2048, "max_consecutive_direct_audit": 0, "swarm_hygiene_violations_count": 2 if st == "RED" else 0}

    monkeypatch.setattr(re_mod, "_resolve_context_sentry_cls", lambda: _FakeSentry)
    res_warn = re_mod.evaluate_compliance_scores(checker, tp_ws, [], _base_compliance_counters())
    res_yellow = re_mod.evaluate_compliance_scores(checker, tp_ws, [], _base_compliance_counters())
    c_red = _base_compliance_counters()
    c_red.update({
        "polling_calls": 4, "total_tool_calls": 10, "max_direct_tool_calls_streak": checker.DDI_DIRECT_STREAK_LIMIT + 2,
        "code_write_calls": 1, "win32_2pc_executed": False, "ast_guard_executed": False,
        "meta_prompt_gate_executed": False, "external_unstage_writes": 2,
    })
    res_red = re_mod.evaluate_compliance_scores(checker, tp_ws, [], c_red)
    c_mono = _base_compliance_counters()
    c_mono.update({"code_write_calls": 11, "subagents_invoked": 0})
    res_mono = re_mod.evaluate_compliance_scores(checker, tp_ws, [], c_mono)
    monkeypatch.setattr(re_mod, "_resolve_context_sentry_cls", lambda: None)
    res_none = re_mod.evaluate_compliance_scores(checker, tp_ws, [], _base_compliance_counters())
    assert (res_warn["warn_advisory"], "WARN status" in res_warn["advisories"][0]) == (True, True)
    assert any("YELLOW" in p for p in res_yellow["penalties"]) and res_red["status"] == "FAIL" and len(res_red["penalties"]) >= 7
    assert any("Monolithic write pattern" in p for p in res_mono["penalties"]) and (res_none["status"], res_none["metrics"]["context_sentry_status"]) == ("FAIL", "UNMEASURED")


@pytest.mark.fast
def test_w1_cleanup_dev_servers_and_deterministic_api_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Migrated: safe_cleanup_dev_servers (zero subprocess) e DeterministicApiCache."""
    assert clean_mod.parse_ports_arg("8001, 8002, invalid") == [8001, 8002]
    ws_target = tmp_path / "ws_clean"
    ws_target.mkdir()
    cim_payload = json.dumps([
        {"ProcessId": 4242, "Name": "python.exe", "CommandLine": f"python {ws_target}/srv.py", "ExecutablePath": ""},
        {"ProcessId": 999999, "Name": "notepad.exe", "CommandLine": "notepad.exe", "ExecutablePath": ""},
    ])
    monkeypatch.delenv("NK_FORCE_NETWORK_REFRESH", raising=False)
    fake_sub = SimpleNamespace(
        DEVNULL=-3,
        PIPE=-1,
        STDOUT=-2,
        run=lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=cim_payload, stderr=""),
        check_output=lambda *_a, **_k: "  TCP    127.0.0.1:59998   0.0.0.0:0   LISTENING   4242\n",
    )
    monkeypatch.setattr(clean_mod, "_HAS_PSUTIL", False)
    monkeypatch.setattr(clean_mod, "subprocess", fake_sub)
    assert (clean_mod.is_target_workspace_process(999999, ws_target), clean_mod.is_target_workspace_process(4242, ws_target)) == (False, True)
    assert call_script_main(clean_mod, ["--dry-run", "--ports", "59998", "--workspace-root", str(ws_target), "--json"], monkeypatch) == 0

    with cache_mod.DeterministicApiCache(db_path=tmp_path / "api_cache.sqlite3", ttl_seconds=60.0) as api_cache:
        api_cache.set("/v1/ep", 200, '{"result": "cached_val"}', method="GET", params={"k": 1}, headers={"Content-Type": "application/json"})
        hit = api_cache.get("/v1/ep", method="GET", params={"k": 1})
        assert hit is not None and hit[0] == 200 and "cached_val" in hit[1]
        assert (api_cache.get("/v1/ep", method="GET", params={"k": 1}, force_refresh=True), api_cache.get("/v1/missing", method="GET", params={})) == (None, None)
        assert (api_cache.get_stats()["entries"], api_cache.clear()) == (1, 1)


def _assert_mapper_and_indexer_filters(tmp_path: Path) -> None:
    poly_repo = tmp_path / "poly_web"
    poly_repo.mkdir()
    (poly_repo / "styles.css").write_text(".card { padding: 8px; } #nav { top: 0; }\n", encoding="utf-8")
    (poly_repo / "view.html").write_text('<main id="app"><button id="cta">Go</button></main>\n', encoding="utf-8")
    (poly_repo / "big_mod.py").write_text("\n".join(f"def focal_fn_{i}(x: int, y: int) -> int:\n    val = x + y\n    return val + {i}\n" for i in range(3)), encoding="utf-8")
    assert "REPO-MAP" in map_mod.RepoMapGenerator.generate(poly_repo).content
    sl_res = map_mod.KarpathySurgicalSlicer.slice_module((poly_repo / "big_mod.py").read_text(encoding="utf-8"), focal_symbol_names=[f"focal_fn_{i}" for i in range(3)], module_path="big_mod.py", max_tokens=20)
    assert sl_res.token_count >= 1
    comp_sig = map_mod.RepoMapGenerator._compact_sig_for_ste100("async def super_long_fn(a: int, b: str, c: float, d: bool, e: list, f: dict) -> int: ...", max_words=6)
    assert ("super_long_fn(" in comp_sig, ": int" in comp_sig) == (True, False)
    rich_repo = tmp_path / "rich_tier_repo"
    rich_repo.mkdir()
    (rich_repo / "cls_methods.py").write_text("class MegaService:\n" + "".join(f"    def m_{i}(self) -> int:\n        return {i}\n" for i in range(5)), encoding="utf-8")
    (rich_repo / "many_fns.py").write_text("".join(f"def util_fn_{i}(x: int) -> int:\n    return x + {i}\n" for i in range(5)), encoding="utf-8")
    (rich_repo / "only_consts.py").write_text("GLOBAL_FLAG = True\nMAX_CAP = 42\n", encoding="utf-8")
    assert "REPO-MAP" in map_mod.RepoMapGenerator.generate(rich_repo, config=map_mod.RepoMapConfig(max_tokens=128, polyglot=True)).content

    ws_flt = tmp_path / "flt_ws"
    ws_flt.mkdir()
    assert idx_mod.NKRegistryIndexer(workspace_root=ws_flt, global_config_dir=tmp_path / "no_gcfg").apply_global_filter()["applied"] is False
    ext_gcfg = tmp_path / "ext_readonly_gcfg"
    (ext_gcfg / "skills" / idx_mod.NKRegistryIndexer.GCP_DATA_SKILLS[0]).mkdir(parents=True)
    ro_res = idx_mod.NKRegistryIndexer(workspace_root=ws_flt, global_config_dir=ext_gcfg).apply_global_filter()
    assert (ro_res["applied"], ro_res["read_only"]) == (True, True)
    in_gcfg = ws_flt / "local_gcfg"
    (in_gcfg / "skills" / idx_mod.NKRegistryIndexer.GCP_DATA_SKILLS[0]).mkdir(parents=True)
    (in_gcfg / "plugins" / "science").mkdir(parents=True)
    (in_gcfg / "config.json").write_text("{corrupt_cfg", encoding="utf-8")
    assert idx_mod.NKRegistryIndexer(workspace_root=ws_flt, global_config_dir=in_gcfg).apply_global_filter()["applied"] is True


def _assert_memory_3tier_resilience(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m_root = tmp_path / "m_root_ws"
    (m_root / "nk_tracking" / "memory_3tier").mkdir(parents=True)
    cap_out = tmp_path / "cap_tier1.json"
    assert "token_cap" in mem_mod.sync_tier1_capsule(base_dir=m_root / "nk_tracking" / "memory_3tier", output_path=cap_out, profile="argon") and cap_out.exists()
    for bad_thr in (True, 1.8):
        with pytest.raises(ValueError):
            mem_mod.consolidate_similar_episodes("ARCH", threshold=bad_thr)
    assert mem_mod.consolidate_similar_episodes("ARCH", threshold=0.9, root=m_root)["passed"] is True
    src_m, dst_m = tmp_path / "mem_src.txt", tmp_path / "mem_dst.txt"
    src_m.write_text("payload_v1", encoding="utf-8")
    dst_m.write_text("old_v0", encoding="utf-8")
    monkeypatch.setattr(mem_mod, "_win32_2pc_atomic_replace", None)
    mem_mod.win32_atomic_replace(src_m, dst_m, max_retries=2)
    assert dst_m.read_text(encoding="utf-8") == "payload_v1"
    trk_ep = tmp_path / "nk_tracking" / "memory_3tier" / "ARCH" / "episodes.jsonl"
    monkeypatch.setenv("NK_MEMORY_BACKUP_DIR", str(tmp_path / "custom_bkp"))
    assert mem_mod._resolve_external_backup_dir(trk_ep) == (tmp_path / "custom_bkp" / "ARCH")
    monkeypatch.delenv("NK_MEMORY_BACKUP_DIR", raising=False)
    bkp_default = mem_mod._resolve_external_backup_dir(trk_ep)
    assert bkp_default is not None and bkp_default.name == "ARCH"
    assert mem_mod._resolve_external_backup_dir(tmp_path / "plain" / "episodes.jsonl") is None


@pytest.mark.integration
def test_w1_preflight_mapper_indexer_and_memory_resilience(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Migrated: ast_repo_mapper, NKRegistryIndexer.apply_global_filter, memory_3tier e PreflightHealthChecker."""
    _assert_mapper_and_indexer_filters(tmp_path)
    _assert_memory_3tier_resilience(tmp_path, monkeypatch)

    ph_ws = tmp_path / "preflight_dirty_ws"
    for d in (".commit_ready", ".sandbox_tmp", "nk_tracking/handoff/stashes", "nk_tracking/anchor", ".wal", "scripts/.wal", "nk_tracking/reports_and_briefs/sub"):
        (ph_ws / d).mkdir(parents=True)
    (ph_ws / "nk_tracking" / "handoff" / "stashes" / "old.patch").write_text("diff\n", encoding="utf-8")
    (ph_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl").write_text('{"event": "ok"}\nnot_valid_json\n', encoding="utf-8")
    (ph_ws / "session_anchor.jsonl").write_text('{"rogue": 1}\n', encoding="utf-8")
    old_ts = time.time() - 300.0
    stale_w = ph_ws / ".wal" / "stale_uncommitted.wal"
    stale_w.write_text('{"state": "PREPARED"}\n', encoding="utf-8")
    os.utime(stale_w, (old_ts, old_ts))
    comm_w1 = ph_ws / ".wal" / "comm_single.wal"
    comm_w1.write_text('{"state": "COMMITTED"}\n', encoding="utf-8")
    os.utime(comm_w1, (old_ts, old_ts))
    comm_w2 = ph_ws / ".wal" / "comm_multi.wal_2pc.jsonl"
    comm_w2.write_text('{"state": "PREPARED"}\n{"state": "COMMITTED"}\n', encoding="utf-8")
    os.utime(comm_w2, (old_ts, old_ts))
    for idx in range(5):
        (ph_ws / "nk_tracking" / "reports_and_briefs" / f"audit_rep_{idx}.json").write_text("{}", encoding="utf-8")
    (ph_ws / "nk_tracking" / "reports_and_briefs" / "sub" / "nested.md").write_text("# Ok\n", encoding="utf-8")
    (ph_ws / "nk_tracking" / "quality_baseline.json.bak_1").write_text("{}", encoding="utf-8")
    ph = pre_mod.PreflightHealthChecker(workspace_root=ph_ws)
    assert len(ph.run_full_check(auto_fix=False)["issues_detected"]) >= 2
    assert (len(ph._collect_report_files_shallow()) >= 6, len(ph._collect_tracking_bak_files_shallow()) >= 1) == (True, True)
    assert ph.run_full_check(auto_fix=True)["checks"]["staging_hygiene"]["passed"] is True
    assert (stale_w.exists(), comm_w1.exists(), comm_w2.exists()) == (False, True, True)


def _assert_bootstrap_wal_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    b_ws = tmp_path / "wal_boot_ws"
    (b_ws / ".wal").mkdir(parents=True)
    bs = boot_mod.NKSessionBootstrap(workspace_root=b_ws)
    w_cor1 = b_ws / ".wal" / "bad.wal"
    w_cor1.write_text("not_json_at_all", encoding="utf-8")
    assert bs._inspect_wal_state(w_cor1) == "CORRUPTED"
    q1 = bs._quarantine_corrupted_wal(w_cor1)
    assert q1 is not None and q1.exists()
    w_cor1.write_text("still_bad", encoding="utf-8")
    q2 = bs._quarantine_corrupted_wal(w_cor1)
    assert (q2 is not None, q2.exists() if q2 else False, q2 != q1) == (True, True, True)

    poll_ws = tmp_path / "polluted_hub_ws"
    for d in ("scripts", ".agents", "nk_genome", "src_app", ".wal"):
        (poll_ws / d).mkdir(parents=True)
    (poll_ws / "src_app" / "app_rogue.py").write_text("X = 1\n", encoding="utf-8")
    (poll_ws / "orphan_root.py").write_text("Y = 2\n", encoding="utf-8")
    wal_samples = {
        "empty.wal": "   ", "list.wal": "[1, 2]", "pend.wal": '{"state": "PREPARED"}', "comm.wal": '{"state": "COMMITTED"}',
        "jcomm.wal_2pc.jsonl": '{"state": "PREPARED"}\n{"state": "COMMITTED"}\n',
        "comm_prep.wal_2pc.jsonl": '{"state": "COMMITTED"}\n{"state": "PREPARED"}\n',
        "comm_bad.wal_2pc.jsonl": '{"state": "COMMITTED"}\n{bad_json\n',
    }
    for name, body in wal_samples.items():
        (poll_ws / ".wal" / name).write_text(body, encoding="utf-8")
    bs_poll = boot_mod.NKSessionBootstrap(workspace_root=poll_ws, conversation_id="conv-poll")
    assert (bs_poll._inspect_wal_state(poll_ws / ".wal" / "empty.wal"), bs_poll._inspect_wal_state(poll_ws / ".wal" / "pend.wal")) == ("CORRUPTED", "VALID_PENDING")
    assert (bs_poll._is_committed_wal_file(poll_ws / ".wal" / "jcomm.wal_2pc.jsonl"), bs_poll._is_committed_wal_file(poll_ws / ".wal" / "comm_prep.wal_2pc.jsonl")) == (True, False)
    assert bs_poll.run_bootstrap(fast_stat=False)["checks"]["project_isolation"]["passed"] is False


def _assert_rsi_canary_and_cli(tmp_path: Path) -> None:
    can_dir = tmp_path / "canary_dir"
    can_dir.mkdir()
    assert rsi_mod.evaluate_canary_holdout(holdout_path=can_dir)["passed"] is True
    assert rsi_mod.evaluate_canary_holdout(holdout_path=tmp_path / "missing_sub" / "c.json")["passed"] is True
    mini_ws = tmp_path / "rsi_cli_ws"
    for d in (".agents", "nk_tracking", ".staging"):
        (mini_ws / d).mkdir(parents=True)
    (mini_ws / ".agents" / "guide.md").write_text("# Titolo\n\nFrase breve valida.\n", encoding="utf-8")
    rc_vc1, out_vc1, _ = call_script_main_captured(rsi_mod, ["--root", str(mini_ws), "--vibe-check", "."])
    assert (rc_vc1, "RSI-VIBE-CHECK" in out_vc1) == (0, True)
    (mini_ws / ".staging" / "mod.py").write_text("VAL = 1\n", encoding="utf-8")
    rc_vc2, out_vc2, _ = call_script_main_captured(rsi_mod, ["--root", str(mini_ws), "--vibe-check", ".", "--json"])
    assert (rc_vc2, json.loads(out_vc2)["passed"]) == (0, True)
    rc_sv, out_sv, _ = call_script_main_captured(rsi_mod, ["--root", str(mini_ws), "--verify", "--strict-verify"])
    assert (rc_sv, "RSI" in out_sv) == (2, True)
    rc_tel, out_tel, _ = call_script_main_captured(rsi_mod, ["--root", str(mini_ws), "--verify", "--persist-telemetry"])
    assert (rc_tel in (0, 2), "RSI" in out_tel, (mini_ws / "nk_tracking" / "rsi_telemetry.jsonl").is_file()) == (True, True, True)


@pytest.mark.integration
def test_w1_bootstrap_wal_matrix_rsi_cli_and_sentry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Migrated: bootstrap WAL quarantine + 7-state matrix, RSI canary/CLI, context_sentry e handoff >32KB."""
    _assert_bootstrap_wal_matrix(tmp_path, monkeypatch)
    _assert_rsi_canary_and_cli(tmp_path)

    guard_ws = tmp_path / "wal_mutex_fail_closed"
    (guard_ws / ".wal").mkdir(parents=True)
    stale_guard = guard_ws / ".wal" / "stale_guard.wal"
    stale_guard.write_text('{"state": "PREPARED"}\n', encoding="utf-8")
    os.utime(stale_guard, (time.time() - 300.0, time.time() - 300.0))
    bs_guard = boot_mod.NKSessionBootstrap(workspace_root=guard_ws, conversation_id="conv-guard")
    with monkeypatch.context() as mp_m:
        mp_m.setattr(sys, "platform", "win32")
        mp_m.setattr(bs_guard, "_try_acquire_2pc_mutex_nonblocking", lambda _root=None: -1)
        assert (bs_guard._purge_stale_wal_files(ttl_seconds=10.0)["mutex_error"], stale_guard.exists()) == (True, True)

    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"usage": {"prompt_tokens": 4096}}) == 4096
    capsys.readouterr()
    assert call_script_main(sentry_mod, ["--verbose"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() != ""
    big_tp = tmp_path / "big_tp.jsonl"
    big_tp.write_text("".join(f'{{"step": {i}, "content": "{"x" * 80}"}}\n' for i in range(450)), encoding="utf-8")
    assert hand_mod._read_transcript_summary_fast(str(big_tp))[1] > 32768

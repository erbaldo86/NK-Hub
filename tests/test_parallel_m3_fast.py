# -*- coding: utf-8 -*-
"""Suite @pytest.mark.fast zero-mock per Milestone 3 NK-GEN-4.0.3 (Commit Train, Goldilocks, Integrita, Tool Isolation)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Tuple

import pytest

pytestmark = pytest.mark.fast

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _make_repo(tmp_path: Path, *, git_dir: bool = False) -> Tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "scripts" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / ".agents").mkdir(parents=True)
    (repo / "nk_tracking" / "tensor_sessions" / "lanes").mkdir(parents=True)
    (repo / "nk_genome" / "changelog.d").mkdir(parents=True)
    (repo / "scripts" / "pkg" / "mod_a.py").write_text("def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8")
    (repo / "nk_genome" / "PATCH_NOTES.md").write_text("# Patch Notes\n\n## `[1.0.0]` Init\n- base\n", encoding="utf-8")
    if git_dir:
        (repo / ".git").mkdir(parents=True)
    key_p = tmp_path / "keys" / "commit_train_hmac.key"
    return repo, key_p


def _mint_active_tensor_slot(repo: Path, stg_dir: Path, key_path: Path, *, lane_id: str) -> None:
    from _internal.nk_common.staging_manifest import canonical_json_bytes, compute_staging_manifest_sha256

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(b"tensor_secret_key_for_m3_tests_0123456789abcdef")
    now = time.time()
    body = {
        "session_id": f"TS_{lane_id}",
        "lane_id": lane_id,
        "accepted": True,
        "issued_at": now - 1.0,
        "expires_at": now + 600.0,
        "staging_manifest_sha256": compute_staging_manifest_sha256(stg_dir, exclude_lanes=False),
    }
    body["hmac_sha256"] = hmac.new(key_path.read_bytes(), canonical_json_bytes(body), hashlib.sha256).hexdigest()
    slot_p = repo / "nk_tracking" / "tensor_sessions" / "lanes" / f"{lane_id}.json"
    slot_p.write_text(json.dumps(body, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Contracts & Store Hash-Chain
# ---------------------------------------------------------------------------

def test_commit_train_contracts_strict_validation() -> None:
    from pydantic import ValidationError
    from _internal.nk_common.commit_train_contracts import (
        CommitLogEntryV1,
        CommitTrainHeadV1,
        CommitTrainOutcomeV1,
        CommitTrainQueueItemV1,
        DeltaReGateResultV1,
        LaneBaseSnapshotV1,
        OCCConflictReportV1,
    )

    h64 = "a" * 64
    snap = LaneBaseSnapshotV1(lane_id="l1", repo_hash12="0123456789ab", base_seq=0, base_head_hash=h64, captured_at=1.0, write_set=["a.py"])
    entry = CommitLogEntryV1(seq=1, batch_id="b_001", lane_id="l1", milestone="M3", timestamp_utc=1.0, staging_manifest_sha256=h64, prev_hash="0" * 64, record_hash=h64, hmac_sha256=h64)
    head = CommitTrainHeadV1(repo_hash12="0123456789ab", seq=1, last_batch_id="b_001", last_lane_id="l1", last_record_hash=h64, updated_at=1.0, hmac_sha256=h64)
    q_item = CommitTrainQueueItemV1(ticket_id="tk_1", lane_id="l1", pid=os.getpid(), enqueued_at=1.0)
    occ = OCCConflictReportV1(passed=True, status="OK", base_seq=0, head_seq=0)
    reg = DeltaReGateResultV1(passed=True, status="PASS", validated_seq=1, ast_passed=True, pytest_passed=True, ecosystem_passed=True, baseline_passed=True)
    out = CommitTrainOutcomeV1(passed=True, status="COMMITTED", lane_id="l1", committed_seq=1)
    assert (snap.base_seq, entry.seq, head.seq, q_item.priority_barrier, occ.passed, reg.passed, out.committed_seq) == (0, 1, 1, False, True, True, 1)

    with pytest.raises(ValidationError):
        CommitTrainOutcomeV1(passed=True, status="COMMITTED", lane_id="l1", unexpected_field=1)  # type: ignore[call-arg]


def test_commit_train_store_chain_idempotency_and_tamper(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import (
        GENESIS_HASH,
        append_commit_train_entry,
        casefold_win32_rel,
        compute_changed_files_range,
        ensure_commit_train_hmac_key,
        read_commit_train_head,
        verify_commit_train_chain,
    )

    repo, key_p = _make_repo(tmp_path)
    gen = read_commit_train_head(repo, verify_hmac=True, key_path=key_p)
    assert gen["seq"] == 0 and gen["last_record_hash"] == GENESIS_HASH
    assert casefold_win32_rel("./Scripts\\Mod_A.PY") == "scripts/mod_a.py"

    ensure_commit_train_hmac_key(key_p)
    e1, h1 = append_commit_train_entry(
        repo, batch_id="b1", lane_id="la", milestone="M3",
        committed_files=["Scripts/Pkg/Mod_A.py"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=key_p,
    )
    e1_dup, _ = append_commit_train_entry(
        repo, batch_id="b1", lane_id="la", milestone="M3",
        committed_files=["Scripts/Pkg/Mod_A.py"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=key_p,
    )
    assert e1["record_hash"] == e1_dup["record_hash"] and h1["seq"] == 1

    e2, h2 = append_commit_train_entry(
        repo, batch_id="b2", lane_id="lb", milestone="M3",
        committed_files=["scripts/pkg/mod_b.py"], deleted_files=["scripts/old.py"], staging_manifest_sha256="b" * 64, key_path=key_p,
    )
    assert e2["prev_hash"] == e1["record_hash"] and h2["seq"] == 2
    ok_chain, entries, errs = verify_commit_train_chain(repo, key_path=key_p)
    assert ok_chain and len(entries) == 2 and not errs

    changed_cf, canon = compute_changed_files_range(repo, 1, 2, key_path=key_p)
    assert "scripts/pkg/mod_b.py" in changed_cf and "scripts/old.py" in changed_cf
    assert canon["scripts/pkg/mod_b.py"] == "scripts/pkg/mod_b.py"


def test_commit_train_store_tamper_rejected(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import (
        append_commit_train_entry,
        compute_changed_files_range,
        ensure_commit_train_hmac_key,
        verify_commit_train_chain,
    )

    repo, key_p = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(key_p)
    append_commit_train_entry(
        repo, batch_id="b1", lane_id="la", milestone="M3",
        committed_files=["Scripts/Pkg/Mod_A.py"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=key_p,
    )
    hist_p = repo / "nk_tracking" / "commit_train" / "history.jsonl"
    tampered = json.loads(hist_p.read_text(encoding="utf-8").splitlines()[0])
    tampered["milestone"] = "TAMPERED"
    hist_p.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    ok_bad, _, bad_errs = verify_commit_train_chain(repo, key_path=key_p)
    assert not ok_bad and any("record_hash" in e for e in bad_errs)
    with pytest.raises(ValueError, match="non valida"):
        compute_changed_files_range(repo, 0, 1, key_path=key_p)


def test_commit_train_cross_repo_hash12_rejected(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_contracts import CommitLogEntryV1
    from _internal.nk_common.commit_train_store import append_commit_train_entry, ensure_commit_train_hmac_key, read_commit_train_head, verify_commit_train_chain

    repo_a, key_p = _make_repo(tmp_path / "a")
    repo_b, _ = _make_repo(tmp_path / "b")
    ensure_commit_train_hmac_key(key_p)
    entry, _ = append_commit_train_entry(repo_a, batch_id="b_xrepo", lane_id="la", milestone="M3", committed_files=["scripts/a.py"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=key_p)
    assert CommitLogEntryV1(**entry).repo_hash12 == entry["repo_hash12"]

    dst_dir = repo_b / "nk_tracking" / "commit_train"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for fn in ("head.json", "history.jsonl"):
        (dst_dir / fn).write_text((repo_a / "nk_tracking" / "commit_train" / fn).read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="repo_hash12"):
        read_commit_train_head(repo_b, verify_hmac=True, key_path=key_p)
    ok_b, _, errs_b = verify_commit_train_chain(repo_b, key_path=key_p)
    assert not ok_b and any("repo_hash12" in e for e in errs_b)


# ---------------------------------------------------------------------------
# 2. Subdirs Guard, JournalV3, Queue & OCC
# ---------------------------------------------------------------------------

def test_subdirs_blocked_when_tensor_session_active_and_git_sync_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.promoter import promote_staging_to_production
    from _internal.win32_2pc_engine.tensor_session_guard import build_namespaced_stash_ref, run_git_sync

    repo, _ = _make_repo(tmp_path, git_dir=True)
    t_key = tmp_path / "keys" / "tensor.key"
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(t_key))
    stg_l = repo / ".staging" / "lanes" / "lx"
    (stg_l / "scripts" / "pkg").mkdir(parents=True)
    (stg_l / "scripts" / "pkg" / "f.py").write_text("x = 1\n", encoding="utf-8")
    _mint_active_tensor_slot(repo, stg_l, t_key, lane_id="lx")

    with pytest.raises(TwoPhaseCommitError, match="subdirs vietata"):
        promote_staging_to_production(repo_root=repo, lane_id="lx", subdirs=["scripts"])

    ref = build_namespaced_stash_ref("lx")
    assert ref.startswith("nk_2pc_lx_")
    idx_lock = repo / ".git" / "index.lock"
    idx_lock.write_text("locked", encoding="utf-8")
    # Verifica fail-closed senza mai rimuovere index.lock vivo
    orig_wait = __import__("_internal.win32_2pc_engine.tensor_session_guard", fromlist=["_wait_git_index_unlocked"])._wait_git_index_unlocked
    monkeypatch.setattr("_internal.win32_2pc_engine.tensor_session_guard._wait_git_index_unlocked", lambda r, max_wait_s=0.05: orig_wait(r, max_wait_s=0.05))
    assert run_git_sync(repo, [{"relative_path": "scripts/pkg/mod_a.py"}], []) is False
    assert idx_lock.is_file()


def test_multi_batch_journal_v3_states_and_recovery(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.journal_multi import MultiBatchJournalV3

    repo, _ = _make_repo(tmp_path)
    tgt_p = repo / "scripts" / "pkg" / "mod_a.py"
    orig_txt = tgt_p.read_text(encoding="utf-8")

    # 1) Crash in PREPARED -> rollback ripristina pre-immagine
    b1, jf1, _bd1 = MultiBatchJournalV3.begin_batch(repo, [("scripts/pkg/mod_a.py", tgt_p)], lane_id="la", milestone="M3")
    tgt_p.write_text("# corrupted before commit\n", encoding="utf-8")

    # 2) Crash in COMMITTED_FS -> roll-forward NON ripristina i byte vecchi e invoca callback idempotente
    tgt_cf = repo / "scripts" / "pkg" / "mod_cf.py"
    tgt_cf.write_text("v = 2\n", encoding="utf-8")
    b2, jf2, _bd2 = MultiBatchJournalV3.begin_batch(repo, [("scripts/pkg/mod_cf.py", tgt_cf)], lane_id="lb", milestone="M3")
    MultiBatchJournalV3.transition_state(jf2, "COMMITTED_FS")
    with pytest.raises(TwoPhaseCommitError, match="non valida"):
        MultiBatchJournalV3.transition_state(jf2, "PREPARED")

    rolled_forward_ids: list[str] = []
    outcomes = MultiBatchJournalV3.recover_all_batches(repo, roll_forward_cb=lambda m: rolled_forward_ids.append(m["batch_id"]))
    actions = {o["batch_id"]: o["action"] for o in outcomes}
    assert actions[b1] == "ROLLED_BACK_PREPARED" and actions[b2] == "ROLLED_FORWARD_COMMITTED_FS"
    assert tgt_p.read_text(encoding="utf-8") == orig_txt
    assert tgt_cf.read_text(encoding="utf-8") == "v = 2\n"
    assert rolled_forward_ids == [b2]
    assert not jf1.exists() and not jf2.exists()


def test_commit_train_queue_barrier_and_dead_pid_reap(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.commit_train_queue import (
        dequeue_lane,
        enqueue_lane,
        is_lane_turn,
        list_queue_items,
        record_rebase_and_promote_barrier,
    )

    repo, _ = _make_repo(tmp_path)
    qp = tmp_path / "queue.json"
    enqueue_lane(repo, "dead_lane", pid=99999999, queue_path=qp)
    enqueue_lane(repo, "lane_1", pid=os.getpid(), queue_path=qp)
    enqueue_lane(repo, "lane_2", pid=os.getpid(), queue_path=qp)

    live_ids = [it["lane_id"] for it in list_queue_items(repo, queue_path=qp)]
    assert live_ids == ["lane_1", "lane_2"]

    record_rebase_and_promote_barrier(repo, "lane_2", barrier_threshold=2, queue_path=qp)
    assert is_lane_turn(repo, "lane_1", queue_path=qp)[0] is True
    record_rebase_and_promote_barrier(repo, "lane_2", barrier_threshold=2, queue_path=qp)
    ok_l1, blocker = is_lane_turn(repo, "lane_1", queue_path=qp)
    ok_l2, _ = is_lane_turn(repo, "lane_2", queue_path=qp)
    assert (ok_l1, blocker, ok_l2) == (False, "lane_2", True)

    assert dequeue_lane(repo, "lane_2", queue_path=qp) is True
    assert is_lane_turn(repo, "lane_1", queue_path=qp)[0] is True


def test_occ_write_conflict_and_ast_signature_drift(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry
    from _internal.win32_2pc_engine.occ_and_ast_gate import (
        capture_public_signatures_snapshot,
        evaluate_occ_and_ast_gate,
    )

    repo, key_p = _make_repo(tmp_path)
    t0_sigs = capture_public_signatures_snapshot(repo, ["scripts/pkg/mod_a.py"])
    assert "greet" in t0_sigs["scripts/pkg/mod_a.py"]

    stg_a = repo / ".staging" / "lanes" / "l_occ"
    (stg_a / "scripts" / "pkg").mkdir(parents=True)
    (stg_a / "scripts" / "pkg" / "Mod_A.py").write_text("def greet(name: str) -> str:\n    return name\n", encoding="utf-8")

    # Fast-path T0 == head
    assert evaluate_occ_and_ast_gate(repo, stg_a, base_seq=0, base_signatures=t0_sigs, key_path=key_p)["status"] == "OK"

    # Lane B modifica scripts/pkg/mod_a.py in T1 (rompe anche firma pubblica)
    (repo / "scripts" / "pkg" / "mod_a.py").write_text("def greet(name: str, formal: bool) -> str:\n    return name\n", encoding="utf-8")
    append_commit_train_entry(repo, batch_id="b_other", lane_id="l_b", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="d" * 64, key_path=key_p)

    # 1) Overlap -> OCC_WRITE_CONFLICT case-folded con unified diff
    occ_res = evaluate_occ_and_ast_gate(repo, stg_a, base_seq=0, base_signatures=t0_sigs, key_path=key_p)
    assert not occ_res["passed"] and occ_res["status"] == "OCC_WRITE_CONFLICT" and "unified_diff" in occ_res

    # 2) Non-overlap su altro file ma firma pubblica T0->T1 rotta -> AST_CONTRACT_DRIFT
    stg_disjoint = repo / ".staging" / "lanes" / "l_disjoint"
    (stg_disjoint / "scripts" / "pkg").mkdir(parents=True)
    (stg_disjoint / "scripts" / "pkg" / "mod_c.py").write_text("def call_g() -> int:\n    return 1\n", encoding="utf-8")
    drift_res = evaluate_occ_and_ast_gate(repo, stg_disjoint, base_seq=0, base_signatures=t0_sigs, key_path=key_p)
    assert not drift_res["passed"] and drift_res["status"] == "AST_CONTRACT_DRIFT"
    assert "scripts/pkg/mod_a.py::greet" in drift_res["ast_drift_symbols"]


# ---------------------------------------------------------------------------
# 3. Quality Baseline CAS Guard & Hook Integrity VALID_ADVANCED / Cache
# ---------------------------------------------------------------------------

def test_quality_baseline_cas_guard_detects_concurrent_update(tmp_path: Path) -> None:
    from _internal.quality_baseline_manager.cas_guard import BASELINE_CAS_CONFLICT, compute_baseline_file_sha256
    from _internal.quality_baseline_manager.ratchet_core import update_baseline_metrics

    repo, _ = _make_repo(tmp_path)
    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    base_metrics = {
        "total_golden_tests": 100, "unit_tests_total": 100, "unit_tests_passed": 100,
        "unit_tests_pass_pct": 100.0, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0,
        "pytest_duration_s": 5.0, "statement_coverage_pct": 92.0, "true_branch_coverage_pct": 85.0,
        "combined_coverage_pct": 90.0, "sast_critical_violations": 0,
    }
    assert update_baseline_metrics(str(bl_p), base_metrics)["verdict"] == "PASS"
    sha_t0 = compute_baseline_file_sha256(bl_p)

    # Prima update CAS riesce
    m1 = {**base_metrics, "total_golden_tests": 105, "unit_tests_total": 105, "unit_tests_passed": 105}
    r1 = update_baseline_metrics(str(bl_p), m1, expected_baseline_sha256=sha_t0)
    assert r1["verdict"] == "PASS"

    # Seconda update con sha_t0 stantio fallisce BASELINE_CAS_CONFLICT
    m2 = {**base_metrics, "total_golden_tests": 108, "unit_tests_total": 108, "unit_tests_passed": 108}
    r2 = update_baseline_metrics(str(bl_p), m2, expected_baseline_sha256=sha_t0)
    assert r2["verdict"] == "FAIL" and r2.get("error_code") == BASELINE_CAS_CONFLICT


def test_hook_integrity_valid_advanced_5_points_and_session_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry, ensure_commit_train_hmac_key
    from _internal.nk_hook_gate.integrity_and_fasttrack import _handle_integrity
    from _internal.nk_hook_gate.integrity_anchor_sync import compute_or_load_session_start_snapshot
    from _internal.win32_2pc_engine.post_commit_consolidator import compute_live_chain_anchor_sha256

    repo, ct_key = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(ct_key)
    monkeypatch.setenv("NK_COMMIT_TRAIN_HMAC_KEY_PATH", str(ct_key))
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "nk_hooks_tmp"))
    (repo / ".agents" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")

    # SessionStart HMAC cache miss -> poi hit entro TTL su sub-repo separato
    cache_repo, _ = _make_repo(tmp_path / "cache_sub")
    (cache_repo / ".agents" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")
    calls = {"c": 0}
    def _build() -> dict:
        calls["c"] += 1
        return {"root": cache_repo.as_posix(), "oracle_lock_sha256": hashlib.sha256(b"").hexdigest()}

    _, hit1 = compute_or_load_session_start_snapshot(cache_repo, _build, key_path=ct_key)
    _, hit2 = compute_or_load_session_start_snapshot(cache_repo, _build, key_path=ct_key)
    assert (hit1, hit2, calls["c"]) == (False, True, 1)

    res_init, rc_init = _handle_integrity("conv_m3", repo, init_mode=True, check_mode=False, use_start_cache=True)
    assert (res_init["status"], rc_init) == ("INITIALIZED", 0)

    # Un'altra lane modifica scripts/ e registra un commit train autenticato con chain_anchor aggiornato -> VALID_ADVANCED
    (repo / "scripts" / "pkg" / "mod_a.py").write_text("def greet(name: str) -> str:\n    return name.upper()\n", encoding="utf-8")
    live_anchor = compute_live_chain_anchor_sha256(repo)
    append_commit_train_entry(
        repo, batch_id="b_adv", lane_id="lb", milestone="M3",
        committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="f" * 64,
        chain_anchor_sha256=live_anchor, key_path=ct_key,
    )
    res_adv, rc_adv = _handle_integrity("conv_m3", repo, init_mode=False, check_mode=True)
    assert (res_adv["status"], res_adv["passed"], rc_adv, res_adv["advanced_to_seq"]) == ("VALID_ADVANCED", True, 0, 1)

    # Out-of-band edit a hooks.json senza commit_train -> VIOLATION fail-closed
    (repo / ".agents" / "hooks.json").write_text('{"hooks":{"tampered":true}}', encoding="utf-8")
    res_viol, rc_viol = _handle_integrity("conv_m3", repo, init_mode=False, check_mode=True)
    assert (res_viol["status"], res_viol["passed"], rc_viol) == ("VIOLATION", False, 1)


def test_hook_cache_nested_edit_invalidates_and_patch_notes_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry, ensure_commit_train_hmac_key
    from _internal.nk_hook_gate.integrity_and_fasttrack import _handle_integrity
    from _internal.nk_hook_gate.integrity_anchor_sync import compute_or_load_session_start_snapshot, verify_valid_advanced_anchor
    from _internal.win32_2pc_engine.post_commit_consolidator import compute_live_chain_anchor_sha256

    repo, ct_key = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(ct_key)
    monkeypatch.setenv("NK_COMMIT_TRAIN_HMAC_KEY_PATH", str(ct_key))
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hooks_nested"))
    (repo / ".agents" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")

    # 1) Nested in-place file edit in scripts/pkg/mod_a.py MUST invalidate SessionStart cache immediately
    _, hit1 = compute_or_load_session_start_snapshot(repo, lambda: {"oracle_lock_sha256": hashlib.sha256(b"").hexdigest()}, key_path=ct_key)
    (repo / "scripts" / "pkg" / "mod_a.py").write_text("def greet(name: str) -> str:\n    return f'yo {name}'\n", encoding="utf-8")
    _, hit2 = compute_or_load_session_start_snapshot(repo, lambda: {"oracle_lock_sha256": hashlib.sha256(b"").hexdigest()}, key_path=ct_key)
    assert (hit1, hit2) == (False, False)

    # 2) VALID_ADVANCED preserves patch_notes metadata so later destructive overwrite -> VIOLATION
    _handle_integrity("c_pn", repo, init_mode=True, check_mode=False)
    (repo / "scripts" / "pkg" / "mod_a.py").write_text("def greet(name: str) -> str:\n    return 'z'\n", encoding="utf-8")
    live_a = compute_live_chain_anchor_sha256(repo)
    append_commit_train_entry(repo, batch_id="b_pn", lane_id="lb", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="a" * 64, chain_anchor_sha256=live_a, key_path=ct_key)
    adv, rc_adv = _handle_integrity("c_pn", repo, init_mode=False, check_mode=True)
    assert (adv["status"], rc_adv) == ("VALID_ADVANCED", 0)
    (repo / "nk_genome" / "PATCH_NOTES.md").write_text("# Wiped\n", encoding="utf-8")
    viol, rc_v = _handle_integrity("c_pn", repo, init_mode=False, check_mode=True)
    assert (viol["status"], rc_v) == ("VIOLATION", 1)

    # 3) Negative saved_seq and missing hooks_json_sha256 fail closed
    ok_neg, _, err_neg = verify_valid_advanced_anchor(repo, {"commit_train_seq": -1, "hooks_json_sha256": "a" * 64}, adv, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
    ok_hk, _, err_hk = verify_valid_advanced_anchor(repo, {"commit_train_seq": 0, "commit_train_head_hash": "0" * 64}, adv, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
    assert (ok_neg, ok_hk) == (False, False)
    assert "invalid saved commit_train_seq" in err_neg["reason"] and "missing hooks_json_sha256" in err_hk["reason"]


# ---------------------------------------------------------------------------
# 4. Lane Lease Probe (_scan_dirty_orphans) + Integrity
# ---------------------------------------------------------------------------

def test_lane_lease_probe_only_exempts_live_leased_2pc_dot_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.lane_lease_probe import is_active_2pc_dot_tmp
    from _internal.nk_common.lane_leases import register_runtime_lease
    from _internal.nk_common.lane_registry import register_lane
    from _internal.rsi_convergence_engine.ecosystem_verify import _scan_dirty_orphans

    repo, _ = _make_repo(tmp_path)
    monkeypatch.setenv("TEMP", str(tmp_path / "nvme_temp"))
    reg_path = tmp_path / "leases.json"

    register_lane(repo, "l_active", "cid_12345678", declared_write_set=["scripts/pkg/mod_a.py"])
    register_runtime_lease(repo, lane_id="l_active", conversation_id="cid_12345678", pid=os.getpid(), registry_path=reg_path)

    dot_live = repo / "scripts" / ".staging_pkg_f.tx_123.tmp"
    # Nota: mod_a.py sta in scripts/pkg/, proviamo uno in scripts/ registrato e uno non registrato
    register_lane(repo, "l_root_scr", "cid_12345678", declared_write_set=["scripts/live_target.py"])
    register_runtime_lease(repo, lane_id="l_root_scr", conversation_id="cid_12345678", pid=os.getpid(), registry_path=reg_path)
    live_tmp = repo / "scripts" / ".staging_live_target.py.tx_abc.tmp"
    live_tmp.write_text("x", encoding="utf-8")
    bak_f = repo / "scripts" / ".staging_live_target.py.tx_abc.bak"
    bak_f.write_text("x", encoding="utf-8")
    unleased_tmp = repo / "scripts" / "orphan_foo.tmp"
    unleased_tmp.write_text("x", encoding="utf-8")
    stale_tmp = repo / "scripts" / ".shadow_live_target.py_aabbccdd.tmp"
    stale_tmp.write_text("x", encoding="utf-8")
    os.utime(stale_tmp, (time.time() - 30.0, time.time() - 30.0))

    assert is_active_2pc_dot_tmp(live_tmp, repo, max_age_sec=15.0, registry_path=reg_path) is True
    assert is_active_2pc_dot_tmp(bak_f, repo, max_age_sec=15.0, registry_path=reg_path) is False
    assert is_active_2pc_dot_tmp(unleased_tmp, repo, max_age_sec=15.0, registry_path=reg_path) is False
    assert is_active_2pc_dot_tmp(stale_tmp, repo, max_age_sec=15.0, registry_path=reg_path) is False
    assert is_active_2pc_dot_tmp(dot_live, repo, max_age_sec=15.0, registry_path=reg_path) is False

    # Verifica _scan_dirty_orphans esenta live_tmp se nel registro default (LOCALAPPDATA)
    register_runtime_lease(repo, lane_id="l_root_scr", conversation_id="cid_12345678", pid=os.getpid())
    orphans = _scan_dirty_orphans(repo)
    assert "scripts/.staging_live_target.py.tx_abc.tmp" not in orphans
    assert "scripts/orphan_foo.tmp" in orphans and "scripts/.staging_live_target.py.tx_abc.bak" in orphans


def test_commit_train_store_edge_and_error_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import (
        append_commit_train_entry,
        ensure_commit_train_hmac_key,
        read_commit_train_head,
        resolve_commit_train_hmac_key_path,
        verify_commit_train_chain,
    )

    repo, key_p = _make_repo(tmp_path)
    monkeypatch.setenv("NK_COMMIT_TRAIN_HMAC_KEY_PATH", str(key_p))
    assert resolve_commit_train_hmac_key_path() == key_p.resolve()
    ensure_commit_train_hmac_key()
    append_commit_train_entry(repo, batch_id="b1", lane_id="la", milestone="M3", committed_files=["scripts/a.py"], deleted_files=[], staging_manifest_sha256="a" * 64)

    head_p = repo / "nk_tracking" / "commit_train" / "head.json"
    hist_p = repo / "nk_tracking" / "commit_train" / "history.jsonl"
    orig_head = head_p.read_text(encoding="utf-8")

    # Bad HMAC on head.json -> ValueError & verify_commit_train_chain False
    bad_h = json.loads(orig_head)
    bad_h["hmac_sha256"] = "0" * 64
    head_p.write_text(json.dumps(bad_h), encoding="utf-8")
    with pytest.raises(ValueError, match="HMAC"):
        read_commit_train_head(repo, verify_hmac=True)
    assert verify_commit_train_chain(repo)[0] is False

    # seq mismatch between head and history
    bad_h2 = json.loads(orig_head)
    bad_h2["seq"] = 99
    head_p.write_text(json.dumps(bad_h2), encoding="utf-8")
    assert verify_commit_train_chain(repo)[0] is False

    # Broken prev_hash and non-monotonic seq in history
    head_p.write_text(orig_head, encoding="utf-8")
    e_raw = json.loads(hist_p.read_text(encoding="utf-8").splitlines()[0])
    e_raw["seq"] = 2
    e_raw["prev_hash"] = "1" * 64
    hist_p.write_text(json.dumps(e_raw) + "\n", encoding="utf-8")
    ok_b, _, errs_b = verify_commit_train_chain(repo)
    assert not ok_b and len(errs_b) >= 2


def test_anchor_sync_expiry_and_hooks_committed_advance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry, ensure_commit_train_hmac_key
    from _internal.nk_hook_gate.integrity_and_fasttrack import _handle_integrity
    from _internal.nk_hook_gate.integrity_anchor_sync import (
        compute_or_load_session_start_snapshot,
        verify_valid_advanced_anchor,
    )
    from _internal.win32_2pc_engine.post_commit_consolidator import compute_live_chain_anchor_sha256

    repo, ct_key = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(ct_key)
    monkeypatch.setenv("NK_COMMIT_TRAIN_HMAC_KEY_PATH", str(ct_key))
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hooks_t"))
    (repo / ".agents" / "hooks.json").write_text('{"v":1}', encoding="utf-8")

    # TTL expiration forces recompute
    _, hit_a = compute_or_load_session_start_snapshot(repo, lambda: {"oracle_lock_sha256": hashlib.sha256(b"").hexdigest()}, ttl_sec=10.0, key_path=ct_key, now_ts=1000.0)
    _, hit_exp = compute_or_load_session_start_snapshot(repo, lambda: {"oracle_lock_sha256": hashlib.sha256(b"").hexdigest()}, ttl_sec=10.0, key_path=ct_key, now_ts=1500.0)
    assert (hit_a, hit_exp) == (False, False)

    res_init, _ = _handle_integrity("c_adv", repo, init_mode=True, check_mode=False)
    assert res_init["status"] == "INITIALIZED"

    # Another lane legitimately edits .agents/hooks.json AND commits via Commit Train -> VALID_ADVANCED
    (repo / ".agents" / "hooks.json").write_text('{"v":2}', encoding="utf-8")
    live_anc = compute_live_chain_anchor_sha256(repo)
    append_commit_train_entry(
        repo, batch_id="b_hooks", lane_id="lb", milestone="M3",
        committed_files=[".agents/hooks.json"], deleted_files=[], staging_manifest_sha256="9" * 64,
        chain_anchor_sha256=live_anc, key_path=ct_key,
    )
    res_adv, rc_adv = _handle_integrity("c_adv", repo, init_mode=False, check_mode=True)
    assert (res_adv["status"], rc_adv) == ("VALID_ADVANCED", 0)

    # verify_valid_advanced_anchor rejects non-empty history violations or stale seq
    assert verify_valid_advanced_anchor(repo, {"commit_train_seq": 1}, res_adv, oracle_lock_violations=["err"], history_violations=[], key_path=ct_key)[0] is False
    assert verify_valid_advanced_anchor(repo, {"commit_train_seq": 5}, res_adv, oracle_lock_violations=[], history_violations=[], key_path=ct_key)[0] is False


# ---------------------------------------------------------------------------
# 5. Copertura rami residui M3 (queue, journal, anchor, CLI)
# ---------------------------------------------------------------------------


def test_commit_train_queue_default_path_update_and_malformed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import _internal.win32_2pc_engine.commit_train_queue as ctq

    repo, _ = _make_repo(tmp_path)
    nvme_q = tmp_path / "nvme_q"
    nvme_q.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ctq.tempfile, "gettempdir", lambda: str(nvme_q))
    def_qp = ctq.resolve_commit_train_queue_path(repo, None)
    assert def_qp.name == "commit_train_queue.json" and "nk_parallel" in def_qp.parts

    qp = tmp_path / "custom_q.json"
    qp.write_text("[]", encoding="utf-8")
    assert ctq.list_queue_items(repo, queue_path=qp) == []

    rec1 = ctq.enqueue_lane(repo, "lane_upd", staging_manifest_sha256="a" * 64, queue_path=qp)
    rec2 = ctq.enqueue_lane(repo, "lane_upd", staging_manifest_sha256="b" * 64, queue_path=qp)
    assert rec1["ticket_id"] == rec2["ticket_id"] and rec2["staging_manifest_sha256"] == "b" * 64

    qp.write_text(json.dumps({"version": 1, "items": ["bad", {"pid": 0}, {"lane_id": "dead_x", "pid": 99999999}]}), encoding="utf-8")
    assert ctq.is_lane_turn(repo, "lane_a", queue_path=qp) == (True, None)

    qp.write_text(json.dumps({"version": 1, "items": [{"lane_id": "dead_y", "pid": 99999999}]}), encoding="utf-8")
    assert ctq.list_queue_items(repo, queue_path=qp) == []
    assert json.loads(qp.read_text(encoding="utf-8"))["items"] == []


def test_multi_batch_journal_v3_dedup_new_file_and_edge_states(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.journal_multi import MultiBatchJournalV3

    repo, _ = _make_repo(tmp_path)
    assert MultiBatchJournalV3.recover_all_batches(repo) == []

    tgt_p = repo / "scripts" / "pkg" / "mod_a.py"
    new_p = repo / "scripts" / "pkg" / "new_f.py"
    _b1, jf1, _bd1 = MultiBatchJournalV3.begin_batch(
        repo, [("scripts/pkg/mod_a.py", tgt_p), ("scripts/pkg/mod_a.py", tgt_p), ("scripts/pkg/new_f.py", new_p)],
        lane_id="la", milestone="M3",
    )
    entries = json.loads(jf1.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == 2 and entries[1]["existed_before"] is False
    new_p.write_text("tmp = 1\n", encoding="utf-8")
    outcomes_rb = MultiBatchJournalV3.recover_all_batches(repo)
    assert outcomes_rb[0]["action"] == "ROLLED_BACK_PREPARED" and not new_p.exists()

    b2, jf2, _bd2 = MultiBatchJournalV3.begin_batch(repo, [("scripts/pkg/mod_a.py", tgt_p)], lane_id="lb", milestone="M3")
    MultiBatchJournalV3.transition_state(jf2, "COMMITTED_FS", extra={"tag": "m3"})
    MultiBatchJournalV3.transition_state(jf2, "FINALIZED")
    act_dir = MultiBatchJournalV3.get_active_batches_dir(repo)
    (act_dir / "mystery.json").write_text(json.dumps({"batch_id": "b_mys", "state": "MYSTERY"}), encoding="utf-8")
    (act_dir / "corrupt.json").write_text("{bad", encoding="utf-8")

    res_edge = {o.get("batch_id", Path(o.get("journal_file", "")).name): o["action"] for o in MultiBatchJournalV3.recover_all_batches(repo)}
    assert res_edge[b2] == "CLEANED_FINALIZED"
    assert res_edge["b_mys"] == "UNKNOWN_STATE_ERROR"
    assert res_edge["corrupt.json"] == "ERROR"
    (act_dir / "mystery.json").unlink()
    (act_dir / "corrupt.json").unlink()


def test_integrity_anchor_sync_error_and_oob_hooks_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import GENESIS_HASH, append_commit_train_entry, ensure_commit_train_hmac_key
    from _internal.nk_common.win32_mutex import repo_path_hash12
    from _internal.nk_hook_gate.integrity_and_fasttrack import _handle_integrity
    from _internal.nk_hook_gate.integrity_anchor_sync import (
        _scan_dir_fingerprint,
        attach_commit_train_anchor_fields,
        collect_watched_tree_mtimes,
        compute_or_load_session_start_snapshot,
        resolve_hooks_config_sha256,
        verify_valid_advanced_anchor,
    )
    from _internal.nk_hook_gate.json_io import _get_hooks_temp_dir
    from _internal.win32_2pc_engine.post_commit_consolidator import compute_live_chain_anchor_sha256

    repo, ct_key = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(ct_key)
    hooks_tmp = tmp_path / "hooks_edge"
    monkeypatch.setenv("NK_COMMIT_TRAIN_HMAC_KEY_PATH", str(ct_key))
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))
    (repo / ".agents" / "hooks.json").write_text('{"v":1}', encoding="utf-8")

    assert verify_valid_advanced_anchor(repo, {"commit_train_seq": 0}, {}, oracle_lock_violations=[], history_violations=[], key_path=ct_key)[0] is False

    real_hooks_dir = _get_hooks_temp_dir()
    real_hooks_dir.mkdir(parents=True, exist_ok=True)
    cache_p = real_hooks_dir / f"session_start_cache_{repo_path_hash12(repo)}.json"
    cache_p.write_text("{corrupt", encoding="utf-8")
    _, hit_c = compute_or_load_session_start_snapshot(repo, lambda: {"oracle_lock_sha256": GENESIS_HASH}, key_path=ct_key)
    assert hit_c is False
    bad_hmac = json.loads(cache_p.read_text(encoding="utf-8"))
    bad_hmac["hmac_sha256"] = "0" * 64
    cache_p.write_text(json.dumps(bad_hmac), encoding="utf-8")
    _, hit_b = compute_or_load_session_start_snapshot(repo, lambda: {"oracle_lock_sha256": GENESIS_HASH}, key_path=ct_key)
    assert hit_b is False

    head_p = repo / "nk_tracking" / "commit_train" / "head.json"
    head_p.parent.mkdir(parents=True, exist_ok=True)
    head_p.write_text("{bad_head", encoding="utf-8")
    att = attach_commit_train_anchor_fields(repo, {})
    assert att["commit_train_seq"] == 0 and att["commit_train_head_hash"] == GENESIS_HASH
    head_p.unlink()

    res_init, _ = _handle_integrity("conv_edge", repo, init_mode=True, check_mode=False)
    assert res_init["status"] == "INITIALIZED"
    (repo / "scripts" / "pkg" / "mod_a.py").write_text("def greet(name: str) -> str:\n    return name.lower()\n", encoding="utf-8")
    live_a1 = compute_live_chain_anchor_sha256(repo)
    append_commit_train_entry(repo, batch_id="b_e1", lane_id="lb", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="a" * 64, chain_anchor_sha256=live_a1, key_path=ct_key)

    hooks_h1 = resolve_hooks_config_sha256(repo)
    ok_anc, _, info_anc = verify_valid_advanced_anchor(repo, {"commit_train_seq": 0, "commit_train_head_hash": GENESIS_HASH, "hooks_json_sha256": hooks_h1}, {"chain_anchor_sha256": "1" * 64, "hooks_json_sha256": hooks_h1}, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
    assert not ok_anc and "chain_anchor_sha256" in info_anc["reason"]


def test_integrity_anchor_sync_oob_hooks_and_dir_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import GENESIS_HASH, append_commit_train_entry, ensure_commit_train_hmac_key
    from _internal.nk_hook_gate.integrity_anchor_sync import (
        _scan_dir_fingerprint,
        collect_watched_tree_mtimes,
        resolve_hooks_config_sha256,
        verify_valid_advanced_anchor,
    )
    from _internal.win32_2pc_engine.post_commit_consolidator import compute_live_chain_anchor_sha256

    repo, ct_key = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(ct_key)
    monkeypatch.setenv("NK_COMMIT_TRAIN_HMAC_KEY_PATH", str(ct_key))
    (repo / ".agents" / "hooks.json").write_text('{"v":1}', encoding="utf-8")
    hooks_h1 = resolve_hooks_config_sha256(repo)

    live_a1 = compute_live_chain_anchor_sha256(repo)
    append_commit_train_entry(repo, batch_id="b_e1", lane_id="lb", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="a" * 64, chain_anchor_sha256=live_a1, key_path=ct_key)
    (repo / ".agents" / "hooks.json").write_text('{"v":99}', encoding="utf-8")
    live_a2 = compute_live_chain_anchor_sha256(repo)
    append_commit_train_entry(repo, batch_id="b_e2", lane_id="lb", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="b" * 64, chain_anchor_sha256=live_a2, key_path=ct_key)

    ok_hm, _, info_hm = verify_valid_advanced_anchor(repo, {"commit_train_seq": 1, "commit_train_head_hash": "0" * 64, "hooks_json_sha256": hooks_h1}, {"chain_anchor_sha256": live_a2}, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
    assert not ok_hm and "mismatch" in info_hm["reason"]
    ok_oob, _, info_oob = verify_valid_advanced_anchor(repo, {"commit_train_seq": 0, "commit_train_head_hash": GENESIS_HASH, "hooks_json_sha256": "0" * 64}, {"chain_anchor_sha256": live_a2, "hooks_json_sha256": "1" * 64}, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
    assert not ok_oob and "hooks.json" in info_oob["reason"]

    for bad_seq in (True, -1):
        ok_bs, st_bs, info_bs = verify_valid_advanced_anchor(repo, {"commit_train_seq": bad_seq, "commit_train_head_hash": GENESIS_HASH, "hooks_json_sha256": hooks_h1}, {"chain_anchor_sha256": live_a2}, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
        assert not ok_bs and st_bs == "VIOLATION" and "invalid saved commit_train_seq" in info_bs["reason"]
    ok_mh, st_mh, info_mh = verify_valid_advanced_anchor(repo, {"commit_train_seq": 0, "commit_train_head_hash": GENESIS_HASH}, {"chain_anchor_sha256": live_a2}, oracle_lock_violations=[], history_violations=[], key_path=ct_key)
    assert not ok_mh and st_mh == "VIOLATION" and "missing hooks_json_sha256" in info_mh["reason"]
    assert _scan_dir_fingerprint(repo / "missing_dir") == [-1, -1, -1]
    (repo / "scripts" / "__pycache__").mkdir(exist_ok=True)
    fp_before = collect_watched_tree_mtimes(repo)["scripts"]
    (repo / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01")
    assert collect_watched_tree_mtimes(repo)["scripts"] == fp_before


def test_m3_cli_and_consolidator_extra_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import win32_2pc_engine as w2pc_cli
    import _internal.nk_acs_fastguard.evaluator as fg_eval
    from _internal.nk_common.commit_train_store import append_commit_train_entry
    from _internal.nk_transcript_tools import cli as tt_cli
    from _internal.quality_baseline_manager import cli as qbm_cli
    from _internal.quality_baseline_manager.cas_guard import compute_baseline_file_sha256
    from _internal.quality_baseline_manager.ratchet_core import update_baseline_metrics
    from _internal.win32_2pc_engine.commit_train_orchestrator import run_commit_train_promote
    from _internal.win32_2pc_engine.post_commit_consolidator import compute_live_chain_anchor_sha256

    repo, key_p = _make_repo(tmp_path)
    qp = tmp_path / "cli_q.json"

    # 1) Orchestrator OCC fail-fast return
    stg_occ = repo / ".staging" / "lanes" / "l_occ_cli"
    (stg_occ / "scripts" / "pkg").mkdir(parents=True)
    (stg_occ / "scripts" / "pkg" / "mod_a.py").write_text("x = 2\n", encoding="utf-8")
    append_commit_train_entry(repo, batch_id="b_prev", lane_id="l_prev", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="c" * 64, key_path=key_p)
    out_occ = run_commit_train_promote(repo, lane_id="l_occ_cli", base_seq=0, key_path=key_p, queue_path=qp)
    assert not out_occ.passed and out_occ.status == "OCC_WRITE_CONFLICT"

    # 2) post_commit_consolidator rsi_telemetry.jsonl tail hash
    anc_before = compute_live_chain_anchor_sha256(repo)
    (repo / "nk_tracking" / "rsi_telemetry.jsonl").write_text('{"session_id":"s1"}\n', encoding="utf-8")
    assert compute_live_chain_anchor_sha256(repo) != anc_before

    # 3) CLI endpoints (--commit-train fail, qbm CAS update, report-conflict --lane-id)
    assert w2pc_cli.main(["--commit-train", "--repo-root", str(repo), "--lane-id", ""]) == 1
    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    m_base = {
        "total_golden_tests": 100, "unit_tests_total": 100, "unit_tests_passed": 100,
        "unit_tests_pass_pct": 100.0, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0,
        "pytest_duration_s": 5.0, "statement_coverage_pct": 92.0, "true_branch_coverage_pct": 85.0,
        "combined_coverage_pct": 90.0, "sast_critical_violations": 0,
    }
    assert update_baseline_metrics(str(bl_p), m_base)["verdict"] == "PASS"
    sha0 = compute_baseline_file_sha256(bl_p)
    m_up = {**m_base, "total_golden_tests": 101, "unit_tests_total": 101, "unit_tests_passed": 101}
    monkeypatch.setattr(sys, "argv", ["qbm", "update", "--file", str(bl_p), "--expected-baseline-sha256", sha0, "--metrics", json.dumps(m_up), "--json"])
    assert qbm_cli.main() == 0
    monkeypatch.setattr(sys, "argv", ["qbm", "update", "--file", str(bl_p), "--expected-baseline-sha256", sha0, "--metrics", json.dumps(m_up), "--json"])
    assert qbm_cli.main() == 1
    assert tt_cli.main(["report-conflict", "--root", str(repo), "--lane-id", "la", "--test-a", "ta", "--test-b", "tb", "--reason", "r", "--json"]) == 0
    assert (repo / "nk_tracking" / "epistemic_conflicts" / "lane_la.json").is_file()

    # 4) Fastguard unlocked persist guard + 5) Nonce store reparse guard
    import _internal.win32_2pc_engine.nonce_store as ns
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError

    sf = tmp_path / "fg_unlocked.json"
    monkeypatch.setattr(fg_eval, "is_fastguard_mutex_acquired", lambda: False)
    fg_eval._safe_persist_state(str(sf), {"steps": 1}, None)
    assert not sf.exists()

    rep_nonces = tmp_path / "rep_nonces.json"
    monkeypatch.setattr(ns, "is_reparse_entry", lambda p: Path(p) == rep_nonces)
    with pytest.raises(TwoPhaseCommitError, match="Reparse"):
        ns.resolve_governance_nonce_store_path(rep_nonces)


def test_m3_mutation_guard_store_and_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import _internal.nk_common.lane_lease_probe as llp
    from _internal.nk_common.commit_train_store import (
        append_commit_train_entry,
        compute_changed_files_range,
        ensure_commit_train_hmac_key,
    )
    from _internal.nk_common.lane_registry import register_lane

    repo, key_p = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(key_p)

    # 1) commit_train_store defaults + to_seq bound
    e1, _ = append_commit_train_entry(
        repo, batch_id="bm1", lane_id="la", milestone="M3",
        committed_files=["scripts/a.py"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=key_p,
    )
    e2, _ = append_commit_train_entry(
        repo, batch_id="bm2", lane_id="", milestone="",
        committed_files=["scripts/b.py"], deleted_files=[], staging_manifest_sha256="b" * 64, key_path=key_p,
    )
    assert (e1["lane_id"], e1["milestone"], e2["lane_id"], e2["milestone"]) == ("la", "M3", "legacy", "2PC_PROMOTE")
    cf_all, _ = compute_changed_files_range(repo, 0, to_seq=None, key_path=key_p)
    cf_cap, _ = compute_changed_files_range(repo, 0, to_seq=1, key_path=key_p)
    assert {"scripts/a.py", "scripts/b.py"}.issubset(cf_all)
    assert "scripts/a.py" in cf_cap
    assert "scripts/b.py" not in cf_cap

    # 2) lane_lease_probe empty/dead lease returns empty set
    register_lane(repo, "l_probe", "cid_12345678", declared_write_set=["scripts/p.py"])
    assert llp._active_leased_write_sets(repo, tmp_path / "missing_leases.json") == set()
    monkeypatch.setattr(llp, "list_active_leases", lambda *_a, **_kw: [{"lane_id": "l_probe", "pid": 99999999}])
    assert llp._active_leased_write_sets(repo, None) == set()


def test_m3_mutation_guard_cas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import _internal.quality_baseline_manager.cas_guard as cg

    repo, _key_p = _make_repo(tmp_path)
    ok_em, _, err_em = cg.check_baseline_cas(tmp_path / "missing_bl.json", "")
    assert not ok_em
    assert err_em is not None
    assert "<empty>" in err_em["message"]
    assert "<missing>" in err_em["message"]
    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    bl_p.write_text("{}", encoding="utf-8")
    actual = cg.compute_baseline_file_sha256(bl_p)
    ok_ne, _, err_ne = cg.check_baseline_cas(bl_p, "f" * 64)
    assert not ok_ne
    assert err_ne is not None
    assert ("f" * 64) in err_ne["message"]
    assert actual in err_ne["message"]
    assert "<empty>" not in err_ne["message"]
    assert "<missing>" not in err_ne["message"]
    monkeypatch.setattr(cg, "is_reparse_entry", lambda p: Path(p) == bl_p)
    with pytest.raises(OSError, match="Reparse"):
        cg.compute_baseline_file_sha256(bl_p)


def test_m3_mutation_guard_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import _internal.win32_2pc_engine.journal_multi as jm
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError

    c1 = tmp_path / "c1"
    c1.mkdir()
    jf_none = c1 / "j_none.json"
    jf_none.write_text("{}", encoding="utf-8")
    jm.MultiBatchJournalV3.cleanup_batch(jf_none, batch_dir=None)
    assert not jf_none.exists()

    sleeps: list[float] = []
    monkeypatch.setattr(jm.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(jm._consts, "RETRY_ATTEMPTS_IO", 2)
    c2 = tmp_path / "c2"
    c2.mkdir()
    jf_ok = c2 / "j_ok.json"
    jf_ok.write_text("{}", encoding="utf-8")
    bd_ok = tmp_path / "bd_ok"
    bd_ok.mkdir()
    jm.MultiBatchJournalV3.cleanup_batch(jf_ok, batch_dir=bd_ok)
    assert not bd_ok.exists()
    assert sleeps == []

    c3 = tmp_path / "c3"
    c3.mkdir()
    jf_st = c3 / "j_st.json"
    jf_st.write_text("{}", encoding="utf-8")
    bd_st = tmp_path / "bd_st"
    bd_st.mkdir()
    monkeypatch.setattr(jm, "safe_rmtree", lambda *_a, **_kw: None)
    jm.MultiBatchJournalV3.cleanup_batch(jf_st, batch_dir=bd_st)
    assert len(sleeps) == 1

    bd_rep = tmp_path / "bd_rep"
    bd_rep.mkdir()
    c4 = tmp_path / "c4"
    c4.mkdir()
    jf_rep = c4 / "j_rep.json"
    jf_rep.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(jm, "is_reparse_entry", lambda p: Path(p) == bd_rep)
    with pytest.raises(TwoPhaseCommitError, match="Reparse"):
        jm.MultiBatchJournalV3.cleanup_batch(jf_rep, batch_dir=bd_rep)
    monkeypatch.undo()

    repo_j, _ = _make_repo(tmp_path / "j_esc")
    act_dir = jm.MultiBatchJournalV3.get_active_batches_dir(repo_j)
    act_dir.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside_victim"
    outside_dir.mkdir()
    (outside_dir / "keep.txt").write_text("safe", encoding="utf-8")
    (act_dir / "esc_out.json").write_text(json.dumps({"batch_id": "b_esc_out", "state": "FINALIZED", "batch_dir": str(outside_dir)}), encoding="utf-8")
    (act_dir / "esc_self.json").write_text(json.dumps({"batch_id": "b_esc_self", "state": "FINALIZED", "batch_dir": str(act_dir)}), encoding="utf-8")
    esc_outcomes = {Path(o["journal_file"]).name: o["action"] for o in jm.MultiBatchJournalV3.recover_all_batches(repo_j)}
    assert esc_outcomes["esc_out.json"] == "ERROR"
    assert esc_outcomes["esc_self.json"] == "ERROR"
    assert (outside_dir / "keep.txt").is_file()
    (act_dir / "esc_out.json").unlink()
    (act_dir / "esc_self.json").unlink()


def test_m3_mutation_guard_queue_and_occ(tmp_path: Path) -> None:
    from _internal.win32_2pc_engine.commit_train_queue import enqueue_lane, record_rebase_and_promote_barrier
    from _internal.win32_2pc_engine.occ_and_ast_gate import _detect_signature_drift, collect_staged_write_set

    repo, _ = _make_repo(tmp_path)
    qp = tmp_path / "q_mut.json"
    rec_a = enqueue_lane(repo, "l_sha", staging_manifest_sha256="a" * 64, queue_path=qp)
    assert rec_a["staging_manifest_sha256"] == "a" * 64
    rb = record_rebase_and_promote_barrier(repo, "l_rb_new", barrier_threshold=2, queue_path=qp)
    assert isinstance(rb, dict)
    assert rb["lane_id"] == "l_rb_new"
    assert rb["rebase_count"] == 1

    assert collect_staged_write_set(tmp_path / "missing_stg") == (set(), {})
    stg = repo / ".staging"
    for rel in ("scripts/ok.py", "scripts/.gitkeep", "scripts/__pycache__/x.pyc", "lanes/lx/sub.py"):
        fp = stg / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("x = 1\n", encoding="utf-8")
    ws_ex, _ = collect_staged_write_set(stg, exclude_lanes=True)
    ws_in, _ = collect_staged_write_set(stg, exclude_lanes=False)
    assert ws_ex == {"scripts/ok.py"}
    assert "lanes/lx/sub.py" in ws_in
    drift = _detect_signature_drift(
        repo, {"README.md", "scripts/pkg/untracked.py"}, {}, {"scripts/pkg/mod_a.py": {"greet": {}}},
    )
    assert drift == ([], "")


def test_m3_mutation_guard_regate_and_consolidator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import types
    import ast_guard_validator as ast_mod
    import quality_baseline_manager
    import rsi_convergence_engine
    import _internal.win32_2pc_engine.delta_regate as dr
    from _internal.win32_2pc_engine.post_commit_consolidator import materialize_changelog_fragments

    repo, key_p = _make_repo(tmp_path)
    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    bl_p.write_text('{"schema_version":2,"metrics":{}}', encoding="utf-8")
    stg_l = repo / ".staging" / "lanes" / "l_dr"
    (stg_l / "scripts" / "pkg").mkdir(parents=True)
    (stg_l / "scripts" / "pkg" / "f.py").write_text("x = 1\n", encoding="utf-8")

    eco_st = {"ok": True}
    bl_st = {"verdict": "PASS"}
    captured: dict = {}

    def _bl_cap(_p: str, m: dict) -> dict:
        captured.update(m)
        return {"verdict": bl_st["verdict"], "details": "bl_fail"}

    monkeypatch.setattr(ast_mod.ASTGuardValidator, "validate_code_edit", classmethod(lambda *_a, **_kw: types.SimpleNamespace(is_valid=True, violations=[], metrics={"sast_violations_count": 3})))
    monkeypatch.setattr(dr, "run_detached_pytest", lambda *_a, **_kw: {"exit_code": 0, "metrics": {"passed": 98, "failed": 0, "errors": 1, "skipped": 1, "duration_s": 0.7}})
    monkeypatch.setattr(rsi_convergence_engine.RSIConvergenceEngine, "verify_ecosystem", lambda *_a, **_kw: {"passed": eco_st["ok"], "violations": ["eco_warn"]})
    monkeypatch.setattr(quality_baseline_manager, "check_baseline_compliance", _bl_cap)

    res1 = dr.run_delta_regate(repo, stg_l, lane_id="l_dr", run_gates_fn=None, key_path=key_p)
    assert res1["passed"] is True
    assert res1["violations"] == []
    assert captured["unit_tests_total"] == 100 and captured["failed_tests"] == 1
    assert captured["tests_skipped"] == 1 and captured["sast_critical_violations"] == 6 and captured["pytest_duration_s"] == 0.7
    bl_st["verdict"] = "FAIL"
    eco_st["ok"] = False
    res2 = dr.run_delta_regate(repo, stg_l, lane_id="l_dr", run_gates_fn=None, key_path=key_p)
    assert res2["passed"] is False and "eco_warn" in res2["violations"]

    pn = repo / "nk_genome" / "PATCH_NOTES.md"
    cd = repo / "nk_genome" / "changelog.d"
    pn.write_text("# Patch Notes\n   \n## `[1.0.0]` Init\n- base\n", encoding="utf-8")
    (cd / "f1.md").write_text("## `[4.0.3]` M3\n- ok", encoding="utf-8")
    materialize_changelog_fragments(repo)
    txt_a = pn.read_text(encoding="utf-8")
    assert txt_a.startswith("# Patch Notes")
    assert "\n\n## `[4.0.3]` M3\n- ok\n\n## `[1.0.0]` Init" in txt_a

    pn.write_text("# Patch Notes\n## `[1.0.0]` Init\n- base\n", encoding="utf-8")
    (cd / "f2.md").write_text("## `[4.0.4]` M4\n- ok", encoding="utf-8")
    materialize_changelog_fragments(repo)
    txt_b = pn.read_text(encoding="utf-8")
    assert txt_b.index("## `[4.0.4]`") < txt_b.index("## `[1.0.0]`")

    pn.write_text("## `[1.0.0]` Init\n- base\n", encoding="utf-8")
    (cd / "f3.md").write_text("## `[4.0.5]` M5\n- ok", encoding="utf-8")
    materialize_changelog_fragments(repo)
    assert pn.read_text(encoding="utf-8").startswith("## `[4.0.5]` M5")


def test_m3_mutation_guard_anchor_scan_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import contextlib
    import types
    import _internal.nk_hook_gate.integrity_anchor_sync as ias

    assert ias._scan_dir_entries(str(tmp_path / "missing_dir"), []) == (0, -1, 0)

    scan_dir = tmp_path / "scan_real"
    (scan_dir / "sub").mkdir(parents=True)
    (scan_dir / "__pycache__").mkdir()
    (scan_dir / "__pycache__" / "skip.pyc").write_bytes(b"zzz")
    (scan_dir / "a.py").write_bytes(b"12345")
    (scan_dir / "b.py").write_bytes(b"1234567")
    (scan_dir / "c.pyc").write_bytes(b"999")
    stack: list[str] = []
    cnt, mt, sz = ias._scan_dir_entries(str(scan_dir), stack)
    assert cnt == 2 and sz == 12 and mt > 0
    assert stack == [str(scan_dir / "sub")]

    def _mk_entry(name: str, *, sym: bool, attrs: int, size: int, mtime: int) -> types.SimpleNamespace:
        st = types.SimpleNamespace(st_file_attributes=attrs, st_mtime_ns=mtime, st_size=size)
        return types.SimpleNamespace(
            name=name,
            path=str(scan_dir / name),
            stat=lambda follow_symlinks=False: st,
            is_symlink=lambda: sym,
            is_dir=lambda follow_symlinks=False: False,
            is_file=lambda follow_symlinks=False: True,
        )

    entries = [
        _mk_entry("sym.py", sym=True, attrs=0, size=50, mtime=100),
        _mk_entry("junc.py", sym=False, attrs=0x400, size=60, mtime=200),
        _mk_entry("ok.py", sym=False, attrs=0, size=11, mtime=300),
    ]
    monkeypatch.setattr(ias.os, "scandir", lambda _p: contextlib.nullcontext(entries))
    assert ias._scan_dir_entries("synthetic_dir", []) == (1, 300, 11)


def test_m3_mutation_guard_delta_regate_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import types
    import ast_guard_validator as ast_mod
    import rsi_convergence_engine
    import _internal.win32_2pc_engine.delta_regate as dr

    assert dr._audit_scripts_tree(tmp_path / "empty_mirror") == {
        "passed": True,
        "violations": [],
        "sast_critical": 0,
    }

    mir = tmp_path / "many_viols"
    sdir = mir / "scripts"
    sdir.mkdir(parents=True)
    for idx in range(7):
        (sdir / f"bad_{idx}.py").write_text("x = 1\n", encoding="utf-8")

    scanned = {"n": 0}

    def _fail_ast(_cls: object, _old: str, _new: str, **_kw: object) -> types.SimpleNamespace:
        scanned["n"] += 1
        return types.SimpleNamespace(
            is_valid=False,
            violations=[types.SimpleNamespace(message=f"v{scanned['n']}")],
            metrics={"sast_violations_count": 1},
        )

    monkeypatch.setattr(ast_mod.ASTGuardValidator, "validate_code_edit", classmethod(_fail_ast))
    audit_rep = dr._audit_scripts_tree(mir)
    assert audit_rep["passed"] is False
    assert scanned["n"] == 5
    assert audit_rep["sast_critical"] == 5
    assert len(audit_rep["violations"]) == 5

    monkeypatch.setattr(
        ast_mod.ASTGuardValidator,
        "validate_code_edit",
        classmethod(lambda *_a, **_kw: types.SimpleNamespace(is_valid=True, violations=[], metrics={"sast_violations_count": 0})),
    )
    monkeypatch.setattr(
        dr,
        "run_detached_pytest",
        lambda *_a, **_kw: {"exit_code": 0, "metrics": {"passed": 10, "failed": 0, "errors": 0, "skipped": 0, "duration_s": 0.2}},
    )
    monkeypatch.setattr(
        rsi_convergence_engine.RSIConvergenceEngine,
        "verify_ecosystem",
        lambda *_a, **_kw: {"passed": True, "violations": []},
    )

    monkeypatch.setattr(dr, "_eval_regate_baseline", lambda *_a, **_kw: (True, "ignored_note"))
    ok_res = dr._default_regate_checks(mir, tmp_path, tmp_path, "l_edge", 1)
    assert ok_res["passed"] is True and ok_res["violations"] == []

    monkeypatch.setattr(dr, "_eval_regate_baseline", lambda *_a, **_kw: (False, ""))
    fail_res = dr._default_regate_checks(mir, tmp_path, tmp_path, "l_edge", 1)
    assert fail_res["passed"] is False and fail_res["violations"] == []




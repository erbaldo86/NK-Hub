# -*- coding: utf-8 -*-
"""Suite CLI, Promoter, Orchestrator e Hook Security per Milestone 3 NK-GEN-4.0.3 (eseguita in suite completa e DAST)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import pytest

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
    return repo, (tmp_path / "keys" / "commit_train_hmac.key")


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


def test_goldilocks_nonce_no_burn_on_cas_abort_and_burns_pre_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.governance_auth import ensure_governance_hmac_key, mint_governance_token
    from _internal.win32_2pc_engine.promoter import promote_staging_to_production
    from _internal.win32_2pc_engine.tensor_session_guard import compute_staging_manifest_sha256

    repo, ct_key = _make_repo(tmp_path)
    gov_key = ensure_governance_hmac_key(tmp_path / "keys" / "gov_hmac.key")
    nonce_store = tmp_path / "keys" / "nonces.json"
    monkeypatch.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(gov_key))
    monkeypatch.setenv("NK_GOVERNANCE_NONCE_STORE_PATH", str(nonce_store))

    lane_stg = repo / ".staging" / "lanes" / "la"
    (lane_stg / "scripts" / "_internal" / "win32_2pc_engine").mkdir(parents=True, exist_ok=True)
    (lane_stg / "scripts" / "_internal" / "win32_2pc_engine" / "new_gov.py").write_text("def x() -> int:\n    return 1\n", encoding="utf-8")
    reason = "Test Goldilocks nonce M3"
    tok = mint_governance_token(reason, key_path=gov_key, token_version="v2", staging_manifest_sha256=compute_staging_manifest_sha256(lane_stg, exclude_lanes=False))

    append_commit_train_entry(repo, batch_id="other_b", lane_id="lb", milestone="M3", committed_files=["scripts/x.py"], deleted_files=[], staging_manifest_sha256="c" * 64, key_path=ct_key)
    with pytest.raises(TwoPhaseCommitError, match="COMMIT_TRAIN_CAS_CONFLICT"):
        promote_staging_to_production(
            repo_root=repo, milestone="M3", lane_id="la", allow_governance_override=True,
            governance_override_reason=reason, governance_token=tok, expected_head_seq=0,
            commit_train_key_path=ct_key, cleanup_staging=False,
        )
    assert not nonce_store.exists() or json.loads(nonce_store.read_text(encoding="utf-8")) == {}

    res = promote_staging_to_production(
        repo_root=repo, milestone="M3", lane_id="la", allow_governance_override=True,
        governance_override_reason=reason, governance_token=tok, expected_head_seq=1,
        use_multi_journal=True, post_commit_consolidate=True, commit_train_key_path=ct_key,
    )
    assert res["passed"] is True and res["committed_seq"] == 2
    assert (repo / "scripts" / "_internal" / "win32_2pc_engine" / "new_gov.py").is_file()

    (lane_stg / "scripts" / "_internal" / "win32_2pc_engine").mkdir(parents=True, exist_ok=True)
    (lane_stg / "scripts" / "_internal" / "win32_2pc_engine" / "new_gov.py").write_text("def x() -> int:\n    return 2\n", encoding="utf-8")
    tok2_sha = compute_staging_manifest_sha256(lane_stg, exclude_lanes=False)
    assert tok2_sha != compute_staging_manifest_sha256(repo / ".staging", exclude_lanes=True)
    tok_same_content = mint_governance_token(reason, key_path=gov_key, nonce="deadbeef" * 4, token_version="v2", staging_manifest_sha256=tok2_sha)
    promote_staging_to_production(repo_root=repo, milestone="M3", lane_id="la", allow_governance_override=True, governance_override_reason=reason, governance_token=tok_same_content, cleanup_staging=False)
    with pytest.raises(TwoPhaseCommitError, match="Replay rilevato"):
        promote_staging_to_production(repo_root=repo, milestone="M3", lane_id="la", allow_governance_override=True, governance_override_reason=reason, governance_token=tok_same_content)


def test_delta_regate_seqlock_and_commit_train_orchestrator(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry, read_commit_train_head
    from _internal.win32_2pc_engine.commit_train_orchestrator import run_commit_train_promote
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.delta_regate import build_seqlock_consistent_mirror

    repo, key_p = _make_repo(tmp_path)
    (repo / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"schema_version": 2, "metrics": {"total_golden_tests": {"value": 100}, "unit_tests_total": {"value": 100}, "unit_tests_passed": {"value": 100}, "unit_tests_pass_pct": {"value": 100.0}, "pass_rate_pct": {"value": 100.0}, "failed_tests": {"value": 0}, "tests_skipped": {"value": 0}, "pytest_duration_s": {"value": 1.0}, "statement_coverage_pct": {"value": 95.0}, "true_branch_coverage_pct": {"value": 90.0}, "combined_coverage_pct": {"value": 92.0}, "sast_critical_violations": {"value": 0}}}),
        encoding="utf-8",
    )
    lane_stg = repo / ".staging" / "lanes" / "l_orch"
    (lane_stg / "scripts" / "pkg").mkdir(parents=True)
    (lane_stg / "scripts" / "pkg" / "feature_m3.py").write_text("def run() -> int:\n    return 42\n", encoding="utf-8")
    (lane_stg / "nk_genome" / "changelog.d").mkdir(parents=True)
    (lane_stg / "nk_genome" / "changelog.d" / "M3.md").write_text("## `[4.0.3]` Milestone 3\n- Serialized Commit Train.", encoding="utf-8")

    calls = {"n": 0}
    qp = tmp_path / "orch_q.json"

    def _gates_fn(_mirror: Path, val_seq: int) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            append_commit_train_entry(repo, batch_id="race_b", lane_id="l_race", milestone="M3", committed_files=["scripts/pkg/disjoint.py"], deleted_files=[], staging_manifest_sha256="e" * 64, key_path=key_p)
        return {"passed": True, "status": "PASS", "validated_seq": val_seq}

    out = run_commit_train_promote(
        repo, lane_id="l_orch", base_seq=0, milestone="NK-GEN-4.0.3",
        barrier_threshold=1, run_gates_fn=_gates_fn, key_path=key_p, queue_path=qp,
    )
    assert out.passed is True and out.rebase_attempts == 1 and out.priority_barrier_used is True and out.committed_seq == 2
    assert (repo / "scripts" / "pkg" / "feature_m3.py").is_file()
    pn_txt = (repo / "nk_genome" / "PATCH_NOTES.md").read_text(encoding="utf-8")
    assert "## `[4.0.3]` Milestone 3" in pn_txt and "## `[1.0.0]` Init" in pn_txt
    assert not (repo / "nk_genome" / "changelog.d" / "M3.md").exists()
    assert int(read_commit_train_head(repo, key_path=key_p)["seq"]) == 2

    with pytest.raises(TwoPhaseCommitError, match="SEQLOCK_RETRIES_EXHAUSTED"):
        import _internal.win32_2pc_engine.delta_regate as dr

        seq_vals = iter([0, 1, 1, 2])
        orig_read = dr.read_commit_train_head
        dr.read_commit_train_head = lambda *_a, **_kw: {"seq": next(seq_vals)}  # type: ignore[assignment]
        try:
            build_seqlock_consistent_mirror(repo, lane_stg, lane_id="l_orch", max_seqlock_retries=2, key_path=key_p)
        finally:
            dr.read_commit_train_head = orig_read  # type: ignore[assignment]


def test_tool_isolation_and_m2_p2_hardening(tmp_path: Path) -> None:
    from _internal.auto_heal_pipeline.rsi_bridge_helpers import _resolve_prod_baseline_code, _resolve_telemetry_target
    from _internal.auto_heal_pipeline.runner import AutoHealPipeline
    from _internal.healing_snapshot_rollback.manager_and_cli import HealingSnapshotManager
    from _internal.nk_acs_fastguard.state_rmw import is_fastguard_mutex_acquired
    from _internal.nk_common.nvme_storage_guards import ensure_nvme_local_dir
    from _internal.nk_transcript_tools.oracle_and_grounding import handle_report_conflict
    from _internal.rsi_convergence_engine.ecosystem_gates_ext import _has_active_epistemic_conflict

    repo, _ = _make_repo(tmp_path)
    base_s = tmp_path / "heal_snaps"
    mgr_a = HealingSnapshotManager(base_temp_dir=base_s, lane_id="la", repo_root=repo)
    mgr_b = HealingSnapshotManager(base_temp_dir=base_s, lane_id="lb", repo_root=repo)
    sid_a = mgr_a.create_snapshot([repo / "scripts" / "pkg" / "mod_a.py"])
    mgr_b.create_snapshot([repo / "nk_genome" / "PATCH_NOTES.md"])
    mgr_a.cleanup(snapshot_id=sid_a)
    assert mgr_b.manifest_path.is_file() and len(mgr_b._read_disk_manifest_unlocked()) == 1

    lane_file = repo / ".staging" / "lanes" / "la" / "scripts" / "pkg" / "mod_a.py"
    lane_file.parent.mkdir(parents=True, exist_ok=True)
    lane_file.write_text("def greet(name: str) -> str:\n    return 'x'\n", encoding="utf-8")
    assert "def greet" in _resolve_prod_baseline_code(lane_file)
    tel_la = _resolve_telemetry_target(repo, lane_id="la")
    assert ".staging" not in tel_la.parts and "nk_auto_heal_telemetry" in tel_la.parts
    pipe = AutoHealPipeline(cwd=repo, lane_id="la")
    assert pipe.snapshot_mgr.lane_id == "la" and pipe.bridge.lane_id == "la"

    payload_c, rc_c = handle_report_conflict(root=repo, test_a="t1", test_b="t2", reason="conflict", lane_id="la")
    assert rc_c == 0 and payload_c["lane_id"] == "la"
    assert _has_active_epistemic_conflict(repo, {}, lane_id="la") is True
    assert _has_active_epistemic_conflict(repo, {}, lane_id="lb") is False

    target_dir = tmp_path / "real_nvme"
    assert ensure_nvme_local_dir(target_dir, "m3_sub").is_dir()
    assert is_fastguard_mutex_acquired() is True


def test_orchestrator_failure_paths_and_cas_consolidator(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry
    from _internal.nk_common.lane_lease_probe import resolve_epistemic_conflict_paths
    from _internal.quality_baseline_manager.cas_guard import check_baseline_cas, compute_baseline_file_sha256
    from _internal.win32_2pc_engine.commit_train_orchestrator import run_commit_train_promote
    from _internal.win32_2pc_engine.commit_train_queue import dequeue_lane, enqueue_lane, record_rebase_and_promote_barrier
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.occ_and_ast_gate import collect_staged_write_set, extract_public_signatures
    from _internal.win32_2pc_engine.post_commit_consolidator import consolidate_post_commit, materialize_changelog_fragments

    repo, key_p = _make_repo(tmp_path)
    qp = tmp_path / "fail_q.json"
    assert resolve_epistemic_conflict_paths(repo, lane_id=None)[0].name == "epistemic_conflict_report.json"
    assert extract_public_signatures("") == {}

    assert run_commit_train_promote(repo, lane_id="", key_path=key_p, queue_path=qp).status == "INVALID_LANE"

    stg_l = repo / ".staging" / "lanes" / "l_fail"
    (stg_l / "scripts" / "pkg").mkdir(parents=True)
    (stg_l / "scripts" / "pkg" / "mod_z.py").write_text("z = 1\n", encoding="utf-8")
    (stg_l / ".deleted_files.json").write_text('["scripts/old_del.py"]', encoding="utf-8")
    ws_set, _ = collect_staged_write_set(stg_l, exclude_lanes=False)
    assert "scripts/old_del.py" in ws_set
    res_rg = run_commit_train_promote(repo, lane_id="l_fail", run_gates_fn=lambda *_a: {"passed": False, "violations": ["boom"]}, key_path=key_p, queue_path=qp)
    assert not res_rg.passed and res_rg.status == "REGATE_FAILED"

    enqueue_lane(repo, "l_vip", pid=os.getpid(), rebase_count=2, barrier_threshold=2, queue_path=qp)
    res_blk = run_commit_train_promote(repo, lane_id="l_fail", run_gates_fn=lambda _m, s: {"passed": True, "validated_seq": s}, key_path=key_p, queue_path=qp)
    assert res_blk.status == "BLOCKED_BY_PRIORITY_BARRIER"
    dequeue_lane(repo, "l_vip", queue_path=qp)
    assert dequeue_lane(repo, "missing_lane", queue_path=qp) is False
    record_rebase_and_promote_barrier(repo, "l_new_rb", barrier_threshold=2, queue_path=qp)
    dequeue_lane(repo, "l_new_rb", queue_path=qp)

    res_max = run_commit_train_promote(
        repo, lane_id="l_fail", base_seq=0, max_rebases=0,
        run_gates_fn=lambda _m, s: (append_commit_train_entry(repo, batch_id="adv_0", lane_id="lx", milestone="M3", committed_files=["scripts/x2.py"], deleted_files=[], staging_manifest_sha256="1" * 64, key_path=key_p), {"passed": True, "validated_seq": s})[1],
        key_path=key_p, queue_path=qp,
    )
    assert res_max.status == "MAX_REBASES_EXCEEDED"

    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    assert compute_baseline_file_sha256(bl_p) == ""
    assert check_baseline_cas(bl_p, None)[0] is True
    assert materialize_changelog_fragments(repo) == []
    (repo / "nk_genome" / "changelog.d" / "dup.md").write_text("## `[1.0.0]` Init\n- dup", encoding="utf-8")
    (repo / "nk_genome" / "changelog.d" / "empty.md").write_text("   \n", encoding="utf-8")
    assert set(materialize_changelog_fragments(repo)) == {"dup.md", "empty.md"}
    with pytest.raises(TwoPhaseCommitError, match="BASELINE_CAS_CONFLICT"):
        consolidate_post_commit(
            repo, batch_id="b_cas_err", lane_id="l_fail", milestone="M3",
            committed_files=[], deleted_files=[], staging_manifest_sha256="2" * 64,
            baseline_metrics_update={
                "total_golden_tests": 100, "unit_tests_total": 100, "unit_tests_passed": 100,
                "unit_tests_pass_pct": 100.0, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0,
                "pytest_duration_s": 1.0, "statement_coverage_pct": 92.0, "true_branch_coverage_pct": 85.0,
                "combined_coverage_pct": 90.0, "sast_critical_violations": 0,
            },
            expected_baseline_sha256="0" * 64, key_path=key_p,
        )


def test_h2_hook_blocks_commit_train_cli_inline_and_artifacts(tmp_path: Path) -> None:
    from _internal.nk_hook_gate.write_gate import _handle_write_gate
    from _internal.win32_2pc_engine.constants import is_protected_governance_path

    repo, _ = _make_repo(tmp_path)
    (repo / ".agents" / "skills").mkdir(parents=True)
    stg_l = repo / ".staging" / "lanes" / "la"
    (stg_l / "scripts" / "pkg").mkdir(parents=True)
    (stg_l / "scripts" / "pkg" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "nk_tracking" / "tensor_sessions" / "lanes" / "la.json").write_text(json.dumps({"accepted": False}), encoding="utf-8")

    res_cli = _handle_write_gate({"tool": "run_command", "args": {}}, repo, False, "", f"python scripts/win32_2pc_engine.py --commit-train --lane-id la --base-seq 0 --repo-root {repo}", "")
    assert res_cli.get("decision") == "deny" and res_cli.get("reason_code") == "ACTIVE_TENSOR_SESSION_UNAPPROVED"

    for inline_cmd in (
        "python -c \"from _internal.win32_2pc_engine.commit_train_orchestrator import run_commit_train_promote; run_commit_train_promote('.')\"",
        "python -c \"from _internal.nk_common.commit_train_store import append_commit_train_entry; append_commit_train_entry('.')\"",
        "python -c \"from _internal.win32_2pc_engine.post_commit_consolidator import consolidate_post_commit; consolidate_post_commit('.')\"",
        "python -c \"from _internal.win32_2pc_engine.post_commit_consolidator import consolidate_post_commit as f; f('.')\"",
        "python -c \"from _internal.win32_2pc_engine.tensor_session_guard import close_active_tensor_session_post_commit; close_active_tensor_session_post_commit('.')\"",
        "python -c \"from _internal.win32_2pc_engine.post_commit_consolidator import materialize_changelog_fragments; materialize_changelog_fragments('.')\"",
        "python -c \"from _internal.nk_common.lane_registry import release_lane; release_lane('.', 'la')\"",
        "python -c \"from _internal.quality_baseline_manager.ratchet_core import update_baseline_metrics; update_baseline_metrics('x', {})\"",
    ):
        res_in = _handle_write_gate({"tool": "run_command", "args": {}}, repo, False, "", inline_cmd, "")
        assert res_in.get("decision") == "deny" and res_in.get("reason_code") == "INLINE_2PC_FORBIDDEN"

    res_env_ps = _handle_write_gate({"tool": "run_command", "args": {}}, repo, False, "", "$env:NK_COMMIT_TRAIN_HMAC_KEY_PATH='C:/tmp/k'", "")
    res_env_py = _handle_write_gate({"tool": "run_command", "args": {}}, repo, False, "", "python -c \"import os; os.environ['NK_COMMIT_TRAIN_HMAC_KEY_PATH']='x'\"", "")
    assert res_env_ps.get("decision") == "deny" and res_env_py.get("decision") == "deny"

    res_f = _handle_write_gate({"tool": "write_file", "args": {}}, repo, False, str(repo / "nk_tracking" / "commit_train" / "head.json"), "", "")
    res_sh = _handle_write_gate({"tool": "run_command", "args": {}}, repo, False, "", "Set-Content nk_tracking/commit_train/head.json '{}'", "")
    assert res_f.get("decision") == "deny" and res_sh.get("decision") == "deny"
    assert is_protected_governance_path("nk_tracking/commit_train/head.json", repo_root=repo) is True


def test_h3_promoter_pre_swap_baseline_cas_and_startup_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.nk_common.commit_train_store import ensure_commit_train_hmac_key, verify_commit_train_chain
    from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
    from _internal.win32_2pc_engine.governance_auth import ensure_governance_hmac_key, mint_governance_token
    from _internal.win32_2pc_engine.journal import BatchJournalV2
    from _internal.win32_2pc_engine.journal_multi import MultiBatchJournalV3
    from _internal.win32_2pc_engine.promoter import promote_staging_to_production
    from _internal.win32_2pc_engine.tensor_session_guard import compute_staging_manifest_sha256

    repo, ct_key = _make_repo(tmp_path)
    ensure_commit_train_hmac_key(ct_key)
    gov_key = ensure_governance_hmac_key(tmp_path / "keys" / "gov_hmac.key")
    nonce_store = tmp_path / "keys" / "nonces_h3.json"
    monkeypatch.setenv("NK_GOVERNANCE_HMAC_KEY_PATH", str(gov_key))
    monkeypatch.setenv("NK_GOVERNANCE_NONCE_STORE_PATH", str(nonce_store))

    lane_stg = repo / ".staging" / "lanes" / "l_h3"
    (lane_stg / "scripts" / "_internal" / "win32_2pc_engine").mkdir(parents=True, exist_ok=True)
    (lane_stg / "scripts" / "_internal" / "win32_2pc_engine" / "cas_tgt.py").write_text("v = 1\n", encoding="utf-8")
    tok = mint_governance_token("H3 baseline CAS test", key_path=gov_key, token_version="v2", staging_manifest_sha256=compute_staging_manifest_sha256(lane_stg, exclude_lanes=False))

    bl_metrics = {
        "total_golden_tests": 100, "unit_tests_total": 100, "unit_tests_passed": 100,
        "unit_tests_pass_pct": 100.0, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0,
        "pytest_duration_s": 1.0, "statement_coverage_pct": 95.0, "true_branch_coverage_pct": 90.0,
        "combined_coverage_pct": 92.0, "sast_critical_violations": 0,
    }
    with pytest.raises(TwoPhaseCommitError, match="BASELINE_CAS_CONFLICT"):
        promote_staging_to_production(
            repo_root=repo, milestone="M3", lane_id="l_h3", allow_governance_override=True,
            governance_override_reason="H3 baseline CAS test", governance_token=tok,
            post_commit_consolidate=True, baseline_metrics_update=bl_metrics, expected_baseline_sha256="0" * 64,
            commit_train_key_path=ct_key, cleanup_staging=False,
        )
    assert not (repo / "scripts" / "_internal" / "win32_2pc_engine" / "cas_tgt.py").exists()
    assert not nonce_store.exists()

    mod_a = repo / "scripts" / "pkg" / "mod_a.py"
    orig_mod_a = mod_a.read_text(encoding="utf-8")
    _b_prep, _jf_p, _bd_p = MultiBatchJournalV3.begin_batch(repo, [("scripts/pkg/mod_a.py", mod_a)], lane_id="la", milestone="M3")
    mod_a.write_text("# stale crash byte\n", encoding="utf-8")
    _b_cf, jf_cf, _bd_cf = MultiBatchJournalV3.begin_batch(repo, [], lane_id="lb", milestone="M3")
    MultiBatchJournalV3.transition_state(
        jf_cf, "COMMITTED_FS",
        extra={"post_consolidate": True, "committed_files": ["scripts/pkg/rf.py"], "deleted_files": [], "staging_manifest_sha256": "e" * 64},
    )
    _b_leg, jf_leg, _bd_leg = MultiBatchJournalV3.begin_batch(repo, [], lane_id=None, milestone="M3")
    MultiBatchJournalV3.transition_state(
        jf_leg, "COMMITTED_FS",
        extra={"post_consolidate": True, "committed_files": ["scripts/pkg/rf_leg.py"], "deleted_files": [], "staging_manifest_sha256": "f" * 64},
    )
    (repo / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").write_text(json.dumps({"accepted": True, "session_id": "s_leg"}), encoding="utf-8")
    BatchJournalV2.recover_crashed_batches(repo)
    assert jf_cf.is_file() and jf_leg.is_file()

    bad_jf = MultiBatchJournalV3.get_active_batches_dir(repo) / "bad_unknown.json"
    bad_jf.write_text(json.dumps({"batch_id": "b_unknown", "state": "MYSTERY_STATE"}), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError, match="Recovery MultiBatchJournalV3 fallito"):
        promote_staging_to_production(
            repo_root=repo, milestone="M3", lane_id="l_h3", allow_governance_override=True,
            governance_override_reason="H3 baseline CAS test", governance_token=tok,
            commit_train_key_path=ct_key,
        )
    bad_jf.unlink()

    promote_staging_to_production(
        repo_root=repo, milestone="M3", lane_id="l_h3", allow_governance_override=True,
        governance_override_reason="H3 baseline CAS test", governance_token=tok,
        commit_train_key_path=ct_key,
    )
    assert mod_a.read_text(encoding="utf-8") == orig_mod_a
    assert not jf_leg.is_file()
    ok_c, entries, _ = verify_commit_train_chain(repo, key_path=ct_key)
    all_committed = {f for e in entries for f in e.get("committed_files", [])}
    assert ok_c and len(entries) == 2 and {"scripts/pkg/rf.py", "scripts/pkg/rf_leg.py"} <= all_committed


def _patch_default_regate_checks(monkeypatch: pytest.MonkeyPatch, state: dict, eco_kwargs: Optional[dict] = None) -> object:
    import types
    import ast_guard_validator as ast_mod
    import quality_baseline_manager
    import rsi_convergence_engine
    import _internal.win32_2pc_engine.delta_regate as dr

    def _fake_val(_cls: object, *_a: object, **_kw: object) -> object:
        viols = [] if state["ok"] else [types.SimpleNamespace(message="ast_err")]
        return types.SimpleNamespace(is_valid=state["ok"], violations=viols, metrics={"sast_violations_count": 0 if state["ok"] else 2})

    def _fake_pytest(*_a: object, **_kw: object) -> dict:
        ok = state["ok"]
        return {"exit_code": 0 if ok else 1, "passed": 100 if ok else 99, "failed": 0 if ok else 1, "errors": 0, "skipped": 0, "duration_s": 1.2}

    def _fake_eco(_self: object, *_a: object, **kw: object) -> dict:
        if eco_kwargs is not None:
            eco_kwargs.clear()
            eco_kwargs.update(kw)
        return {"passed": state["ok"], "violations": [] if state["ok"] else ["eco_err"]}

    def _fake_bl(_p: str, _m: dict) -> dict:
        return {"verdict": "PASS" if state["ok"] else "FAIL", "details": "" if state["ok"] else "bl_err"}

    monkeypatch.setattr(ast_mod.ASTGuardValidator, "validate_code_edit", classmethod(_fake_val))
    monkeypatch.setattr(dr, "run_detached_pytest", _fake_pytest)
    monkeypatch.setattr(rsi_convergence_engine.RSIConvergenceEngine, "verify_ecosystem", _fake_eco)
    monkeypatch.setattr(quality_baseline_manager, "check_baseline_compliance", _fake_bl)
    return dr


def _assert_regate_injected_report(rep: object, *, expect_ok: bool) -> None:
    from _internal.rsi_convergence_engine.report_sanitizers import injected_check_passed_ext, parse_injected_counts_ext

    assert isinstance(rep, dict)
    ok_p, _, counts = parse_injected_counts_ext(rep)
    if expect_ok:
        assert (rep["status"], rep["passed"], rep["tests_total"], rep["exit_code"]) == ("PASS", True, 100, 0)
        assert (ok_p, counts, injected_check_passed_ext(counts, rep["tests_total"])) == (True, (100, 0, 0, 0, 0), (True, 100))
    else:
        assert (rep["status"], ok_p) == ("FAIL", False)


def test_delta_regate_default_checks_pass_and_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, key_p = _make_repo(tmp_path)
    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    bl_p.write_text(json.dumps({"schema_version": 2, "metrics": {}}), encoding="utf-8")
    stg_l = repo / ".staging" / "lanes" / "l_def"
    (stg_l / "scripts" / "pkg").mkdir(parents=True)
    (stg_l / "scripts" / "pkg" / "f.py").write_text("x = 1\n", encoding="utf-8")

    state = {"ok": True}
    eco_kw: dict = {}
    dr = _patch_default_regate_checks(monkeypatch, state, eco_kwargs=eco_kw)
    res_ok = dr.run_delta_regate(repo, stg_l, lane_id="l_def", run_gates_fn=None, key_path=key_p)
    assert (res_ok["passed"], res_ok["status"], res_ok["violations"], eco_kw.get("strict_verify")) == (True, "PASS", [], False)
    _assert_regate_injected_report(eco_kw.get("test_report"), expect_ok=True)

    state["ok"] = False
    res_fail = dr.run_delta_regate(repo, stg_l, lane_id="l_def", run_gates_fn=None, key_path=key_p)
    assert (res_fail["passed"], res_fail["status"]) == (False, "FAIL")
    assert len(res_fail["violations"]) >= 4
    _assert_regate_injected_report(eco_kw.get("test_report"), expect_ok=False)

    state["ok"] = True
    bl_p.unlink()
    res_no_bl = dr.run_delta_regate(repo, stg_l, lane_id="l_def", run_gates_fn=None, key_path=key_p)
    assert (res_no_bl["passed"], res_no_bl["baseline_passed"]) == (True, True)


def test_m3_delta_regate_real_baseline_and_fast_invariants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import types
    import ast_guard_validator as ast_mod
    import rsi_convergence_engine
    import _internal.win32_2pc_engine.delta_regate as dr
    from _internal.rsi_convergence_engine.report_sanitizers import parse_injected_counts_ext

    repo, key_p = _make_repo(tmp_path)
    bl_p = repo / "nk_tracking" / "quality_baseline.json"
    stg_l = repo / ".staging" / "lanes" / "l_real"
    (stg_l / "scripts" / "pkg").mkdir(parents=True)
    (stg_l / "scripts" / "pkg" / "f.py").write_text("x = 1\n", encoding="utf-8")

    sast_st = {"count": 0}
    py_st: dict = {
        "payload": {
            "exit_code": 0, "passed": 100, "failed": 0, "errors": 0, "skipped": 0, "duration_s": 1.5,
            "coverage": {"statement_coverage_pct": 95.0, "true_branch_coverage_pct": 90.0, "combined_coverage_pct": 92.0},
        }
    }
    eco_cap: dict = {}
    def _cap_eco(_self: object, *_a: object, **kw: object) -> dict:
        eco_cap.clear()
        eco_cap.update(kw)
        return {"passed": True, "violations": []}
    monkeypatch.setattr(ast_mod.ASTGuardValidator, "validate_code_edit", classmethod(lambda *_a, **_kw: types.SimpleNamespace(is_valid=True, violations=[], metrics={"sast_violations_count": sast_st["count"]})))
    monkeypatch.setattr(dr, "run_detached_pytest", lambda *_a, **_kw: dict(py_st["payload"]))
    monkeypatch.setattr(rsi_convergence_engine.RSIConvergenceEngine, "verify_ecosystem", _cap_eco)

    bl_12 = {
        "schema_version": 2,
        "metrics": {
            "total_golden_tests": {"value": 100, "direction": "higher_is_better"},
            "unit_tests_total": {"value": 100, "direction": "higher_is_better"},
            "unit_tests_passed": {"value": 100, "direction": "higher_is_better"},
            "unit_tests_pass_pct": {"value": 100.0, "direction": "higher_is_better"},
            "pass_rate_pct": {"value": 100.0, "direction": "higher_is_better"},
            "failed_tests": {"value": 0, "direction": "lower_is_better"},
            "tests_skipped": {"value": 0, "direction": "lower_is_better"},
            "pytest_duration_s": {"value": 8.0, "direction": "lower_is_better"},
            "statement_coverage_pct": {"value": 90.0, "direction": "higher_is_better"},
            "true_branch_coverage_pct": {"value": 85.0, "direction": "higher_is_better"},
            "combined_coverage_pct": {"value": 88.0, "direction": "higher_is_better"},
            "sast_critical_violations": {"value": 0, "direction": "lower_is_better"},
        },
    }
    bl_p.write_text(json.dumps(bl_12), encoding="utf-8")
    assert dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)["passed"] is True
    assert eco_cap["test_report"]["statement_coverage_pct"] == 95.0
    assert parse_injected_counts_ext(eco_cap["test_report"])[0] is True
    py_st["payload"] = {
        "exit_code": 0, "passed": 100, "failed": 0, "errors": 0, "skipped": 0, "duration_s": 1.5,
        "coverage": {"statement_coverage_pct": 80.0, "true_branch_coverage_pct": 90.0, "combined_coverage_pct": 92.0},
    }
    assert dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)["baseline_passed"] is False

    py_st["payload"] = {"exit_code": 0, "passed": 100, "failed": 0, "errors": 0, "skipped": 0, "duration_s": 1.5}
    assert dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)["baseline_passed"] is True
    assert "statement_coverage_pct" not in eco_cap["test_report"]
    py_st["payload"] = {"exit_code": 0, "passed": 99, "failed": 0, "errors": 0, "skipped": 1, "duration_s": 1.5}
    assert dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)["baseline_passed"] is False
    py_st["payload"] = {"exit_code": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "duration_s": 1.5}
    assert dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)["baseline_passed"] is False
    py_st["payload"] = {"exit_code": 0, "passed": 100, "failed": 0, "errors": 0, "skipped": 0, "duration_s": 1.5}
    sast_st["count"] = 1
    assert dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)["baseline_passed"] is False

    bl_p.write_text("{bad", encoding="utf-8")
    res_corrupt = dr.run_delta_regate(repo, stg_l, lane_id="l_real", run_gates_fn=None, key_path=key_p)
    assert not res_corrupt["passed"] and any("Baseline illeggibile" in v for v in res_corrupt["violations"])


def test_m3_mutation_guard_orchestrator(tmp_path: Path) -> None:
    from _internal.nk_common.commit_train_store import append_commit_train_entry
    from _internal.win32_2pc_engine.commit_train_orchestrator import run_commit_train_promote

    repo, key_p = _make_repo(tmp_path)
    qp = tmp_path / "orch_mut_q.json"
    assert run_commit_train_promote(repo, lane_id="   ", key_path=key_p, queue_path=qp).status == "INVALID_LANE"

    s1 = repo / ".staging" / "lanes" / "l_o1"
    (s1 / "scripts" / "pkg").mkdir(parents=True)
    (s1 / "scripts" / "pkg" / "mod_a.py").write_text("x = 2\n", encoding="utf-8")
    append_commit_train_entry(repo, batch_id="b_o1", lane_id="lx", milestone="M3", committed_files=["scripts/pkg/mod_a.py"], deleted_files=[], staging_manifest_sha256="a" * 64, key_path=key_p)
    out_occ = run_commit_train_promote(repo, lane_id="l_o1", base_seq=0, key_path=key_p, queue_path=qp)
    assert out_occ.status == "OCC_WRITE_CONFLICT"
    assert "---" in out_occ.message

    s2 = repo / ".staging" / "lanes" / "l_o2"
    (s2 / "scripts" / "pkg").mkdir(parents=True)
    (s2 / "scripts" / "pkg" / "mod_new.py").write_text("y = 1\n", encoding="utf-8")
    out_rg = run_commit_train_promote(repo, lane_id="l_o2", base_seq=1, run_gates_fn=lambda *_a: {"passed": False, "violations": ["boom_detail"]}, key_path=key_p, queue_path=qp)
    assert out_rg.status == "REGATE_FAILED"
    assert "boom_detail" in out_rg.message

    calls = {"n": 0}
    def _adv(_m: Path, s: int) -> dict:
        calls["n"] += 1
        append_commit_train_entry(repo, batch_id=f"b_{calls['n']}", lane_id="ly", milestone="M3", committed_files=["scripts/z.py"], deleted_files=[], staging_manifest_sha256="b" * 64, key_path=key_p)
        return {"passed": True, "validated_seq": s}

    out_max = run_commit_train_promote(repo, lane_id="l_o2", base_seq=1, max_rebases=0, run_gates_fn=_adv, key_path=key_p, queue_path=qp)
    assert out_max.status == "MAX_REBASES_EXCEEDED"
    assert calls["n"] == 1

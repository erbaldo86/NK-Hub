# -*- coding: utf-8 -*-
"""
Suite di test Zero-Mock Fast per isolamento Multi-Lane NK-GEN-4.0.2 (M2).
Verifica ciclo di vita lane_paths/lane_registry, slot Tensor HMAC, mirror NVMe, DAST, 2PC e CLI.
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Tuple

import pytest

try:
    from conftest import load_nk_script_module
except ImportError:
    from tests.conftest import load_nk_script_module

from _internal.ast_guard_validator import overlay_helpers as agv_overlay
from _internal.dast_sandbox_runner import staging_overlay as dast_stg_ov
from _internal.nk_common import isolated_test_runner as itr
from _internal.nk_common import lane_paths as lp
from _internal.nk_common import lane_registry as lreg
from _internal.tensor_rsi import active_slot_io as slot_io
from _internal.tensor_rsi.ticket_auth import TicketAuthError


def _seed_mini_repo(root: Path) -> Tuple[Path, Path]:
    """Crea un mini-repository deterministico con file base e .staging legacy/lane."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "nk_tracking" / "tensor_sessions").mkdir(parents=True, exist_ok=True)
    base_py = root / "scripts" / "core_mod.py"
    base_py.write_text("VAL = 1\n", encoding="utf-8")
    (root / "tests" / "test_base.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return base_py, root / ".staging"


@pytest.mark.fast
def test_m2_lane_paths_resolution_and_conflict(tmp_path: Path) -> None:
    """Valida normalizzazione lane_paths e blocco conflitto tra lane_id e staging_dir."""
    repo = tmp_path / "repo_m2_lp"
    _seed_mini_repo(repo)
    assert lp.validate_lane_id(" Lane_Alpha-01 ") == "lane_alpha-01"
    stg_lane, norm = lp.resolve_staging_dir(repo, lane_id="Lane_Alpha-01")
    assert norm == "lane_alpha-01"
    assert stg_lane == (repo / ".staging" / "lanes" / "lane_alpha-01").resolve()

    with pytest.raises(ValueError):
        lp.resolve_staging_dir(repo, lane_id="lane_a", staging_dir=".staging/lanes/lane_b")


@pytest.mark.fast
def test_m2_lane_registry_register_claim_release(tmp_path: Path) -> None:
    """Verifica il ciclo completo register, claim child_cid, access check e release."""
    repo = tmp_path / "repo_m2_lr"
    _seed_mini_repo(repo)
    cid_parent = "cid-parent-001"
    cid_child = "cid-child-002"
    try:
        reg = lreg.register_lane(repo, "lane_alpha-01", cid_parent, declared_write_set=["scripts/a.py"])
        assert reg["owner_cid"] == cid_parent
        assert len(reg["claim_secret"]) == 32
        assert lreg.verify_lane_access(repo, "lane_alpha-01", cid_parent) == (True, "owner")
        assert lreg.verify_lane_access(repo, "lane_alpha-01", cid_child) == (False, "foreign_cid_denied")

        claimed = lreg.claim_lane(repo, "lane_alpha-01", cid_child, reg["claim_secret"], parent_cid=cid_parent)
        assert claimed["claimed_by"] == cid_child
        assert claimed["claim_secret_sha256"] == ""
        assert lreg.verify_lane_access(repo, "lane_alpha-01", cid_child) == (True, "authorized_child")
        assert "lane_alpha-01" in lreg.list_active_lanes(repo)

        with pytest.raises(PermissionError):
            lreg.release_lane(repo, "lane_alpha-01", "cid-foreign-999")
        assert lreg.release_lane(repo, "lane_alpha-01", cid_child) is True
        assert lreg.list_active_lanes(repo) == {}
    finally:
        lreg.release_lane(repo, "lane_alpha-01", cid_parent, force=True)


@pytest.mark.fast
def test_m2_active_slot_isolation_and_anti_swap(tmp_path: Path) -> None:
    """Verifica isolamento HMAC, mutex e file per-lane rispetto allo slot ACTIVE legacy."""
    repo = tmp_path / "repo_slots"
    _seed_mini_repo(repo)
    leg_p = slot_io.resolve_active_slot_path(repo)
    la_p = slot_io.resolve_active_slot_path(repo, lane_id="lane_a")
    lb_p = slot_io.resolve_active_slot_path(repo, lane_id="lane_b")
    assert leg_p.name == "ACTIVE.json"
    assert la_p != lb_p and la_p.parent.name == "lanes"
    assert slot_io.resolve_active_slot_mutex_name(repo, "lane_a") != slot_io.resolve_active_slot_mutex_name(repo, None)

    slot_io.claim_active_session_slot(repo, "sess-leg", phase="EVALUATE", staging_manifest_sha256="0" * 64)
    slot_io.claim_active_session_slot(repo, "sess-a", lane_id="lane_a", phase="INTAKE", staging_manifest_sha256="a" * 64)
    slot_io.claim_active_session_slot(repo, "sess-b", lane_id="lane_b", phase="INTAKE", staging_manifest_sha256="b" * 64)

    assert slot_io.read_active_slot(repo)["session_id"] == "sess-leg"
    assert slot_io.read_active_slot(repo, lane_id="lane_a")["lane_id"] == "lane_a"
    assert slot_io.read_active_slot(repo, lane_id="lane_b")["session_id"] == "sess-b"

    with pytest.raises(TicketAuthError):
        slot_io.ensure_slot_available(repo, session_id="sess-foreign", lane_id="lane_a")

    lb_p.write_text(la_p.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(TicketAuthError):
        slot_io.read_active_slot(repo, lane_id="lane_b")

    slot_io.close_active_slot(repo, "sess-a", lane_id="lane_a")
    slot_io.close_active_slot(repo, "sess-leg")
    assert slot_io.read_active_slot(repo, lane_id="lane_a") is None
    assert slot_io.read_active_slot(repo) is None


@pytest.mark.fast
def test_m2_nvme_mirror_and_dast_snapshot_isolation(tmp_path: Path) -> None:
    """Verifica mirror NVMe per-lane, port allocation, report per-lane e marker snapshot DAST."""
    repo = tmp_path / "repo_mirror"
    _seed_mini_repo(repo)
    (repo / ".staging" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".staging" / "scripts" / "legacy_only.py").write_text("X = 'legacy'\n", encoding="utf-8")
    (repo / ".staging" / "lanes" / "lane_x" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".staging" / "lanes" / "lane_x" / "scripts" / "lane_mod.py").write_text("X = 'lane_x'\n", encoding="utf-8")
    (repo / ".staging" / "lanes" / "lane_y" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".staging" / "lanes" / "lane_y" / "scripts" / "other.py").write_text("X = 'lane_y'\n", encoding="utf-8")

    m_lane = itr.mirror_workspace_to_nvme(repo, apply_overlay=True, lane_id="lane_x")
    m_leg = itr.mirror_workspace_to_nvme(repo, apply_overlay=True)
    try:
        assert (m_lane / "scripts" / "lane_mod.py").is_file()
        assert not (m_lane / "scripts" / "legacy_only.py").exists()
        assert not (m_lane / "scripts" / "other.py").exists()
        assert (m_leg / "scripts" / "legacy_only.py").is_file()
        assert not (m_leg / ".staging" / "lanes").exists()
    finally:
        itr.safe_rmtree(m_lane.parent)
        itr.safe_rmtree(m_leg.parent)

    port_x = dast_stg_ov.allocate_dast_port("lane_x")
    assert 18000 <= port_x <= 28999
    assert dast_stg_ov.resolve_dast_lane_report_path(tmp_path, "lane_x").name == "dast_last_report_lane_x.json"
    assert dast_stg_ov.resolve_dast_lane_report_path(tmp_path, None).name == "dast_last_report.json"

    with dast_stg_ov.nvme_staging_snapshot_ctx(repo / ".staging" / "lanes" / "lane_x", "lane_x") as snap_stg:
        assert (snap_stg.parents[2] / ".nk_dast_snapshot_marker").is_file()
        prod_r, stg_r = agv_overlay._resolve_explicit_overlay_roots(repo, str(snap_stg), None)
        assert prod_r == repo.resolve()
        assert stg_r == snap_stg.resolve()
        snap_root_ref = snap_stg.parents[2]
    assert not snap_root_ref.exists()


@pytest.mark.fast
def test_m2_tensor_and_2pc_lane_promotion_quarantine(tmp_path: Path) -> None:
    """Verifica claim Tensor + promozione/quarantena 2PC per lane senza toccare .staging legacy."""
    w2pc = load_nk_script_module("win32_2pc_engine")
    from _internal.win32_2pc_engine.tensor_session_guard import compute_staging_manifest_sha256

    repo = tmp_path / "repo_2pc"
    _seed_mini_repo(repo)
    (repo / ".staging" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / ".staging" / "scripts" / "legacy_keep.py").write_text("KEEP = True\n", encoding="utf-8")

    lane_stg = repo / ".staging" / "lanes" / "lane_p"
    (lane_stg / "scripts").mkdir(parents=True, exist_ok=True)
    (lane_stg / "scripts" / "promoted_mod.py").write_text("PROMOTED = 42\n", encoding="utf-8")
    manifest_sha = compute_staging_manifest_sha256(lane_stg, exclude_lanes=False)
    slot_io.claim_active_session_slot(
        repo,
        "sess-lane-p",
        lane_id="lane_p",
        phase="DECIDE",
        accepted=True,
        staging_manifest_sha256=manifest_sha,
    )
    res_p = w2pc.promote_staging_to_production(
        repo_root=repo,
        milestone="NK-GEN-4.0.2",
        lane_id="lane_p",
        verify_baseline=False,
        cleanup_staging=True,
        enforce_nonce_replay=True,
    )
    assert res_p["passed"] is True
    assert res_p["lane_id"] == "lane_p"
    assert (repo / "scripts" / "promoted_mod.py").read_text(encoding="utf-8") == "PROMOTED = 42\n"
    assert (repo / ".staging" / "scripts" / "legacy_keep.py").is_file()
    assert slot_io.read_active_slot(repo, lane_id="lane_p") is None

    q_stg = repo / ".staging" / "lanes" / "lane_q"
    (q_stg / "scripts").mkdir(parents=True, exist_ok=True)
    (q_stg / "scripts" / "q_file.py").write_text("Q = 1\n", encoding="utf-8")
    q_res = w2pc.quarantine_staging(repo_root=repo, lane_id="lane_q")
    assert q_res["passed"] is True
    assert q_res["quarantined_count"] == 1
    assert (repo / ".staging" / "scripts" / "legacy_keep.py").is_file()
    if q_res.get("quarantine_dir"):
        itr.safe_rmtree(Path(q_res["quarantine_dir"]))


@pytest.mark.fast
def test_m2_cli_lane_id_flags() -> None:
    """Verifica parsing --lane-id sulle CLI aggiornate per isolamento multi-lane."""
    from _internal.dast_sandbox_runner.cli import _build_cli_parser as dast_parser
    from _internal.quality_baseline_manager.cli import _build_cli_parser as qbm_parser
    from _internal.rsi_convergence_engine.engine import _build_rsi_parser

    qbm_mod = load_nk_script_module("quality_baseline_manager")
    rsi_mod = load_nk_script_module("rsi_convergence_engine")
    w2pc_mod = load_nk_script_module("win32_2pc_engine")
    trsi_mod = load_nk_script_module("tensor_rsi")

    assert (
        "--lane-id" in qbm_mod._CLI_FLAGS,
        any(f == "--lane-id" for f, _ in rsi_mod._HELP_CLI_STR_FLAGS),
        dast_parser().parse_args(["--lane-id", "la"]).lane_id,
        qbm_parser().parse_args(["check", "--lane-id", "lb"]).lane_id,
        _build_rsi_parser().parse_args(["--lane-id", "lc"]).lane_id,
        w2pc_mod._build_cli_parser().parse_args(["--lane-id", "ld"]).lane_id,
        trsi_mod._build_cli_parser().parse_args(["--step", "status", "--lane-id", "le"]).lane_id,
    ) == (True, True, "la", "lb", "lc", "ld", "le")


@pytest.mark.fast
def test_m2_materializer_nvme_eval(tmp_path: Path) -> None:
    """Verifica valutazione NVMe lock-free del materializer per lane senza mutare .staging/."""
    from _internal.tensor_rsi import materializer as tmat

    repo = tmp_path / "repo_mat"
    _seed_mini_repo(repo)
    assert tmat._staging_mutex_name(repo, "lane_m") != tmat._staging_mutex_name(repo, None)
    lane_stg = repo / ".staging" / "lanes" / "lane_m"
    (lane_stg / "scripts").mkdir(parents=True, exist_ok=True)
    sid, cid = "sess-mat-m2", "cand-m2"
    cand_dir = tmat.resolve_candidate_dir(sid, cid)
    try:
        tmat._write_candidate_payloads(cand_dir, {"scripts/new_ok.py": b"VAL = 99\n"})
        eval_res, cand_sha, meta = tmat.materialize_and_evaluate(
            repo, sid, cid, lambda: {"passed": True}, eval_in_nvme=True, lane_id="lane_m",
        )
        assert (eval_res["passed"], meta["nvme_lock_free"], meta["lane_id"], len(cand_sha)) == (
            True, True, "lane_m", 64,
        )
        assert not (lane_stg / "scripts" / "new_ok.py").exists()
    finally:
        itr.safe_rmtree(cand_dir)
    assert hmac.compare_digest(
        tmat.compute_staging_manifest_sha256(lane_stg),
        tmat.compute_staging_manifest_sha256(lane_stg, lane_id="lane_m"),
    )

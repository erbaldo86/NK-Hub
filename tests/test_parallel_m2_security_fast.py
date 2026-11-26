# -*- coding: utf-8 -*-
"""
Suite di falsificazione Zero-Mock & Mutation-Killing M2 (NK-GEN-4.0.2):
lane_write_guard, F1..F4, H1..H3 e guardie P2.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Tuple

import pytest

from _internal.ast_guard_validator import overlay_helpers as agv_overlay
from _internal.nk_common import lane_paths as lp
from _internal.nk_common import lane_registry as lreg
from _internal.nk_common import nvme_base_cache as nbc
from _internal.nk_hook_gate import ast_inline_guard as aig
from _internal.nk_hook_gate import lane_write_guard as lwg
from _internal.nk_hook_gate import path_safety as ps
from _internal.nk_hook_gate import write_gate as wg
from _internal.tensor_rsi import active_slot_io as sio
from _internal.tensor_rsi import materializer as tmat
from _internal.tensor_rsi import step_handlers as tsh
from _internal.tensor_rsi.policy_tensor import build_policy_cell
from _internal.tensor_rsi.ticket_auth import TicketAuthError
from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
from _internal.win32_2pc_engine.tensor_session_guard import compute_staging_manifest_sha256, verify_active_tensor_session
from rsi_convergence_engine import RSIConvergenceEngine


def _seed_sec_repo(root: Path) -> Tuple[Path, Path]:
    """Crea un mini-repository isolato per test di sicurezza e RSI."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "nk_tracking" / "tensor_sessions" / "lanes").mkdir(parents=True, exist_ok=True)
    (root / ".staging" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "base_mod.py").write_text("X = 1\n", encoding="utf-8")
    return root / ".staging", root / ".staging" / "lanes"


@pytest.mark.fast
def test_lwg_promote_flag_parsers() -> None:
    """Copre flag spoof --milestone --lane-id=ok, last-wins e conflitti su promote."""
    assert (
        lwg.extract_promote_lane_id(["--promote-staging", "--milestone", "--lane-id=ok"]),
        lwg.extract_promote_lane_id(["--promote-staging", "--lane-id"]),
        lwg.extract_promote_lane_id(["--promote-staging", "--lane-id", "ok", "--lane-id", "evil"]),
        lwg.extract_promote_lane_id(["--promote-staging", "--lane-id=l9"]),
        lwg.extract_promote_lane_and_staging(["--promote-staging", "--staging-dir", ".staging/lanes/x"]),
        lwg.extract_promote_lane_and_staging(["--promote-staging", "--stage-dir=.staging/lanes/y", "--lane-id=y"]),
    ) == (None, None, "evil", "l9", (None, ".staging/lanes/x"), ("y", ".staging/lanes/y"))

    with pytest.raises(ValueError):
        lwg.extract_promote_lane_and_staging(["--lane-id", "ok", "--lane-id", "evil"])
    with pytest.raises(ValueError):
        lwg.extract_promote_lane_and_staging(["--staging-dir", "a", "--staging-dir=b"])


@pytest.mark.fast
def test_lwg_verify_promote_targets_and_inline(tmp_path: Path) -> None:
    """Verifica blocco promote su --staging-dir lane, duplicati e pass su lane approvata."""
    repo = tmp_path / "repo_lwg_prom"
    _seed_sec_repo(repo)
    assert lwg.verify_promote_targets_with_lanes("python -B -u scripts/status.py", repo, False, lambda _w, r: [r]) == {}

    evil_stg = repo / ".staging" / "lanes" / "evil" / "scripts"
    evil_stg.mkdir(parents=True, exist_ok=True)
    (evil_stg / "e.py").write_text("E = 1\n", encoding="utf-8")
    sio.claim_active_session_slot(repo, "sess-evil", lane_id="evil", phase="INTAKE", accepted=False, staging_manifest_sha256="0" * 64)
    assert (
        lwg.verify_promote_targets_with_lanes("python -B -u scripts/win32_2pc_engine.py --promote-staging --staging-dir .staging/lanes/evil", repo, False, lambda _w, r: [r])["reason_code"],
        lwg.verify_promote_targets_with_lanes("python -B -u scripts/win32_2pc_engine.py --promote-staging --lane-id ok --lane-id evil", repo, False, lambda _w, r: [r])["reason_code"],
    ) == ("ACTIVE_TENSOR_SESSION_UNAPPROVED", "ACTIVE_TENSOR_SESSION_UNAPPROVED")
    sio.close_active_slot(repo, "sess-evil", lane_id="evil")

    ok_stg = repo / ".staging" / "lanes" / "ok"
    (ok_stg / "scripts").mkdir(parents=True, exist_ok=True)
    (ok_stg / "scripts" / "m.py").write_text("M = 1\n", encoding="utf-8")
    sha_ok = compute_staging_manifest_sha256(ok_stg, exclude_lanes=False)
    sio.claim_active_session_slot(repo, "sess-ok", lane_id="ok", phase="DECIDE", accepted=True, staging_manifest_sha256=sha_ok)
    assert (
        lwg.verify_promote_targets_with_lanes("python -B -u scripts/win32_2pc_engine.py --promote-staging --lane-id ok", repo, False, lambda _w, r: [r]),
        lwg.verify_promote_targets_with_lanes("python -B -u scripts/win32_2pc_engine.py --promote-staging --lane-id ok && echo --lane-id evil", repo, False, lambda _w, r: [r]),
        lwg.verify_promote_targets_with_lanes("promote_staging_to_production()", repo, True, lambda _w, r: [r]),
    ) == ({}, {}, {})
    sio.close_active_slot(repo, "sess-ok", lane_id="ok")


@pytest.mark.fast
def test_lwg_ownership_and_shell_cross_lane(tmp_path: Path) -> None:
    """Verifica ownership check, write_gate su spazi, backtick e python -c split/dinamici."""
    repo = tmp_path / "Il mio Drive" / "NK_Hub"
    _seed_sec_repo(repo)
    cid_own, cid_bad = "cid-owner-01", "cid-foreign-99"
    try:
        lreg.register_lane(repo, "victim", cid_own)
        vic_file = repo / ".staging" / "lanes" / "victim" / "scripts" / "x.py"
        assert (
            lwg.check_lane_write_authorization(repo / ".staging" / "scripts" / "ok.py", repo, cid_bad),
            lwg.check_lane_write_authorization(vic_file, repo, cid_own),
            lwg.check_lane_write_authorization(vic_file, repo, cid_bad)["reason_code"],
            lwg.check_lane_write_authorization(vic_file, repo, "default_123")["reason_code"],
        ) == ({}, {}, "LANE_OWNERSHIP_DENIED", "LANE_OWNERSHIP_DENIED")

        space_cmd = f'python -c "open(\'dummy\',\'r\')" ; Set-Content "{vic_file}" "BAD"'
        bt_cmd = "echo hi > .staging/la`nes/victim/scripts/bt.py"
        concat_cmd = "python -c \"open('.staging/'+'lanes/victim/scripts/c.py','w').write('x')\""
        dyn_cmd = "python -c \"v='victim'; open(f'.staging/lanes/{v}/scripts/d.py','w')\""
        for bad_c in (space_cmd, bt_cmd, concat_cmd, dyn_cmd):
            assert lwg.check_shell_lane_write_authorization(bad_c, repo, cid_bad)["decision"] == "deny"

        assert (
            lwg.check_shell_lane_write_authorization("python -c \"open('.staging/'+'lanes/victim/scripts/c.py','w').write('x')\"", repo, cid_own),
            lwg.check_shell_lane_write_authorization("echo hello world", repo, cid_bad),
            wg._handle_write_gate({"tool_name": "run_command", "tool_input": {"CommandLine": bt_cmd}}, repo, True, "", "", "", conv_id=cid_bad)["decision"],
            aig.inspect_python_source_mutations("open('.staging/'+'lanes/victim/scripts/c.py','w')", repo, conv_id=cid_bad)["reason_code"],
        ) == ({}, {}, "deny", "LANE_OWNERSHIP_DENIED")
    finally:
        lreg.release_lane(repo, "victim", cid_own, force=True)


@pytest.mark.fast
def test_m2_h2_nvme_eval_catches_defective_candidate(tmp_path: Path) -> None:
    """Falsifica EVAL-BYPASS (H2): candidato rotto su lane pulita viene valutato e respinto."""
    repo = tmp_path / "repo_h2"
    _seed_sec_repo(repo)
    lane_scr = repo / ".staging" / "lanes" / "lane_h2" / "scripts"
    lane_scr.mkdir(parents=True, exist_ok=True)
    clean_file = lane_scr / "ok.py"
    clean_file.write_text('"""Doc."""\nVAL = 1\n', encoding="utf-8")

    sid, cid = "sess-h2-eval", "cand-h2-bad"
    cand_dir = tmat.resolve_candidate_dir(sid, cid)
    cell = build_policy_cell(repo, "IMPROVEMENT", model_tier="neon", acs_zone="Z0")
    try:
        tmat._write_candidate_payloads(cand_dir, {"scripts/ok.py": b'"""Doc."""\nRES = eval("1+1")\n'})
        (snap, ast_ok), cand_sha, meta = tmat.materialize_and_evaluate(
            repo, sid, cid, lambda staging_dir=None: tsh._eval_ro_from_input(repo, cell, {"run_pytest": False}, lane_id="lane_h2", staging_dir=staging_dir),
            lane_id="lane_h2", eval_in_nvme=True,
        )
        assert (snap.sast_critical >= 1, ast_ok, meta["nvme_lock_free"], len(cand_sha) == 64) == (True, False, True, True)
        assert clean_file.read_text(encoding="utf-8") == '"""Doc."""\nVAL = 1\n'
    finally:
        from _internal.nk_common.nvme_mirror_helpers import safe_rmtree

        safe_rmtree(cand_dir.parent)


@pytest.mark.fast
def test_m2_f4_h3_rsi_verify_targets_lane_only(tmp_path: Path) -> None:
    """Falsifica F4/H3: verify_ecosystem(..., lane_id) isola la lane dal legacy .staging/."""
    repo = tmp_path / "repo_f4"
    _seed_sec_repo(repo)
    (repo / ".staging" / "scripts" / "clean.py").write_text('"""Clean."""\nVAL = 1\n', encoding="utf-8")
    bad_scr = repo / ".staging" / "lanes" / "lane_bad" / "scripts"
    bad_scr.mkdir(parents=True, exist_ok=True)
    (bad_scr / "bad.py").write_text('"""Bad."""\nOUT = eval("x")\n', encoding="utf-8")

    eng = RSIConvergenceEngine(workspace_root=repo, root=repo)
    lane_res = eng.verify_ecosystem(repo, profile="vibe_sprint_micro_rsi", lane_id="lane_bad")
    leg_res = eng.verify_ecosystem(repo, profile="vibe_sprint_micro_rsi")
    assert (lane_res.get("lane_id"), lane_res["passed"], lane_res["checks"]["sast_and_mojibake"]["sast_critical"] >= 1, leg_res["checks"]["sast_and_mojibake"]["sast_critical"]) == (
        "lane_bad", False, True, 0
    )


@pytest.mark.fast
def test_m2_p2_dast_marker_boundary_and_cross_repo_slot(tmp_path: Path) -> None:
    """Falsifica P2: marker DAST fuori TEMP respinto e slot HMAC cross-repo respinto."""
    fake_non_temp = tmp_path.parent / "non_temp_hub"
    assert agv_overlay._is_dast_snapshot_root(("G:\\", "Il mio Drive", "Antigravity", ".staging"), 3) is False
    assert (fake_non_temp / ".nk_dast_snapshot_marker").exists() is False

    repo_a, repo_b = tmp_path / "repo_a", tmp_path / "repo_b"
    _seed_sec_repo(repo_a)
    _seed_sec_repo(repo_b)
    (repo_b / ".staging" / "lanes" / "la").mkdir(parents=True, exist_ok=True)
    sio.claim_active_session_slot(repo_a, "sess-ra", lane_id="la", accepted=True, staging_manifest_sha256="a" * 64)
    src_slot = sio.resolve_active_slot_path(repo_a, "la").read_text(encoding="utf-8")
    dst_slot = sio.resolve_active_slot_path(repo_b, "la")
    dst_slot.parent.mkdir(parents=True, exist_ok=True)
    dst_slot.write_text(src_slot, encoding="utf-8")

    with pytest.raises(TicketAuthError):
        sio.read_active_slot(repo_b, lane_id="la")
    with pytest.raises(TwoPhaseCommitError):
        verify_active_tensor_session(repo_b, repo_b / ".staging" / "lanes" / "la", precomputed_sha="a" * 64, lane_id="la")
    sio.close_active_slot(repo_a, "sess-ra", lane_id="la")


@pytest.mark.integration
def test_m2_f1_pre_resolve_junctions_integration(tmp_path: Path) -> None:
    """Falsifica F1 pre-.resolve(): junction su .staging, lane, intra-lane e cache NVMe."""
    if os.name != "nt":
        return
    repo = tmp_path / "repo_junc"
    _seed_sec_repo(repo)
    tgt_dir = tmp_path / "j_outside"
    tgt_dir.mkdir(parents=True)
    cache_j, cache_tgt = tmp_path / "cache_j", tmp_path / "cache_real"
    cache_tgt.mkdir(parents=True)
    lane_a = repo / ".staging" / "lanes" / "la"
    victim = repo / ".staging" / "lanes" / "victim"
    lane_a.mkdir(parents=True, exist_ok=True)
    victim.mkdir(parents=True, exist_ok=True)
    intra_j = lane_a / "escape_to_victim"

    subprocess.run(["cmd", "/c", "mklink", "/J", str(intra_j), str(victim)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(cache_j), str(cache_tgt)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert (
            ps._has_ancestor_reparse_escape(".staging/lanes/la/escape_to_victim/x.py", repo),
            ps._is_valid_staging_path(intra_j / "x.py", repo),
            wg._handle_write_gate({"tool_name": "write_to_file", "tool_input": {"TargetFile": str(intra_j / "x.py"), "CodeContent": "X=1"}}, repo, True, "", "", "")["decision"],
        ) == (True, False, "deny")
        with pytest.raises(OSError):
            nbc.sync_nvme_base_cache(repo, ("scripts",), lambda _d, _n: set(), lambda _p: False, lambda _a, _b: True, cache_root=cache_j)
    finally:
        os.rmdir(intra_j)
        os.rmdir(cache_j)

    repo_s = tmp_path / "repo_stg_j"
    (repo_s / ".staging" / "lanes").mkdir(parents=True)
    j_lane = repo_s / ".staging" / "lanes" / "jl"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(j_lane), str(tgt_dir)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with pytest.raises(OSError):
            lp.resolve_staging_dir(repo_s, lane_id="jl")
        with pytest.raises(OSError):
            lp.resolve_staging_dir(repo_s, staging_dir=".staging/lanes/jl")
    finally:
        os.rmdir(j_lane)

    repo_root_j = tmp_path / "repo_root_stg_j"
    repo_root_j.mkdir()
    j_root_stg = repo_root_j / ".staging"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(j_root_stg), str(tgt_dir)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with pytest.raises(OSError):
            lp.resolve_staging_dir(repo_root_j)
    finally:
        os.rmdir(j_root_stg)

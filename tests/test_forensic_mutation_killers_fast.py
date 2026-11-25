# -*- coding: utf-8 -*-
"""
Test Zero-Mock ad alta letalita mutazionale (<150ms) per chiusura survivor Step 2.
Modulo: tests/test_forensic_mutation_killers_fast.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sys
from typing import Any, Dict

import pytest

from _internal.dast_sandbox_runner import e2e_and_audit as dast_e2e
from _internal.nk_common.staging_manifest import canonical_json_bytes
from _internal.rsi_convergence_engine import gt14_probes as rsi_gt14, report_sanitizers as rsi_rs, sast_scanner as rsi_sast
from _internal.tensor_rsi import (
    materializer as tr_mat, pareto_gate as tr_par, ticket_auth as tr_auth,
)
from _internal.tensor_rsi.schemas import MetricSnapshot, PrimaryInvariantVector, SecondaryQualityVector
from _internal.win32_2pc_engine import tensor_session_guard as w2_tsg
from _internal.win32_2pc_engine.constants import TwoPhaseCommitError

pytestmark = pytest.mark.fast


def _sign_active(key_bytes: bytes, body: Dict[str, Any]) -> Dict[str, Any]:
    sig = hmac.new(key_bytes, canonical_json_bytes(body), hashlib.sha256).hexdigest()
    return {**body, "hmac_sha256": sig}


@pytest.mark.fast
def test_kill_ticket_auth_parts_and_hex_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uccide mutanti BoolOpFlip su parti e firma HMAC di verify_ticket_signature."""
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(tmp_path / "ta_kill.key"))
    with pytest.raises(tr_auth.TicketAuthError, match="Formato"):
        tr_auth.verify_ticket_signature("trsi1.onlytwo")
    with pytest.raises(tr_auth.TicketAuthError, match="Formato"):
        tr_auth.verify_ticket_signature(f"bad.abc.{'0' * 64}")
    for bad_t in (f"trsi1..{'0' * 64}", "trsi1.abc.short", f"trsi1.abc.{'z' * 64}"):
        with pytest.raises(tr_auth.TicketAuthError, match="malformata"):
            tr_auth.verify_ticket_signature(bad_t)


@pytest.mark.fast
def test_kill_pareto_gate_nonfinite_and_epsilon_band(tmp_path: Path) -> None:
    """Uccide mutanti BoolOpFlip/BinOp/Boundary su _t1_pair_deltas e band_violations."""
    assert tr_par._t1_pair_deltas((("m", 0.5),), (("m", float("nan")),))[0] == ["m:non_finite"]
    assert tr_par._t1_pair_deltas((("m", float("inf")),), (("m", 0.5),))[0] == ["m:non_finite"]
    eps, _, _, _, _ = tr_par._load_track_rules("CODE_TRACK", "IMPROVEMENT", tmp_path)
    p1 = PrimaryInvariantVector(p_pass=1.0, k_mut=0.90, c_branch=0.90)
    b = MetricSnapshot(
        intent_track="CODE_TRACK", g_hard=1, q_v2=98.0, certification_tier="STATIC_PASS", state_hash="a" * 64,
        primary=p1, secondary=SecondaryQualityVector(v_sec_hyg=0.80, v_qual=0.80, v_eff=0.80, v_ste100=0.80), tests_total=10,
    )
    edge = b.model_copy(update={"secondary": SecondaryQualityVector(v_sec_hyg=round(0.80 - eps[0], 6), v_qual=0.90, v_eff=0.80, v_ste100=round(0.80 - eps[3], 6))})
    res_edge = tr_par.evaluate_pareto_decision(b, edge, "IMPROVEMENT", workspace_root=tmp_path)
    assert (res_edge.accepted, res_edge.band_violations) == (True, ())
    viol = b.model_copy(update={"secondary": SecondaryQualityVector(v_sec_hyg=0.80, v_qual=0.95, v_eff=0.80, v_ste100=round(0.80 - eps[3] - 0.01, 6))})
    res_viol = tr_par.evaluate_pareto_decision(b, viol, "IMPROVEMENT", workspace_root=tmp_path)
    assert (res_viol.verdict, res_viol.accepted) == ("REJECT_TIER2_EPSILON_BAND", False)


@pytest.mark.fast
def test_kill_materializer_cleanup_targets_and_gitkeep(tmp_path: Path) -> None:
    """Uccide mutanti cleanup targets e creazione selettiva .gitkeep."""
    stg = tmp_path / "ws_cln" / ".staging"
    (stg / "keep_d").mkdir(parents=True)
    (stg / "del_d").mkdir(parents=True)
    f_keep, f_del, f_miss = stg / "keep_d" / "k.py", stg / "del_d" / "d.py", stg / "miss.py"
    f_keep.write_text("k", encoding="utf-8")
    f_del.write_text("d", encoding="utf-8")
    tr_mat._cleanup_created_staging_targets(stg, [f_keep, f_del, f_miss], {str(f_keep.resolve()): True})
    assert (f_keep.is_file(), f_del.exists(), (stg / "del_d").exists(), (stg / ".gitkeep").is_file()) == (True, False, False, True)
    (stg / ".gitkeep").write_text("KEEP", encoding="utf-8")
    tr_mat._cleanup_created_staging_targets(stg, [], {})
    assert (stg / ".gitkeep").read_text(encoding="utf-8") == "KEEP"


@pytest.mark.fast
def test_kill_materializer_eval_and_commit_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uccide mutanti newly_created e snapshot_base_dir su rollback materialize/commit."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lapp"))
    ws = tmp_path / "ws_mat_rb"
    (ws / ".staging").mkdir(parents=True)
    (ws / ".staging" / "exist.py").write_text("OLD", encoding="utf-8")
    cand = tr_mat.resolve_candidate_dir("S_RB", "C_RB")
    cand.mkdir(parents=True)
    (cand / "exist.py").write_text("NEW", encoding="utf-8")
    (cand / "fresh.py").write_text("ADD", encoding="utf-8")
    snap_eval, snap_com = tmp_path / "snap_ev", tmp_path / "snap_cm"
    with pytest.raises(RuntimeError, match="abort"):
        tr_mat.materialize_and_evaluate(ws, "S_RB", "C_RB", lambda: (_ for _ in ()).throw(RuntimeError("abort")), snapshot_base_dir=snap_eval)
    assert ((ws / ".staging" / "exist.py").read_text(encoding="utf-8"), (ws / ".staging" / "fresh.py").exists(), snap_eval.is_dir()) == ("OLD", False, True)
    with pytest.raises(ValueError, match="mismatch"):
        tr_mat.commit_accepted_candidate(ws, "S_RB", "C_RB", "0" * 64, snapshot_base_dir=snap_com)
    assert ((ws / ".staging" / "exist.py").read_text(encoding="utf-8"), (ws / ".staging" / "fresh.py").exists(), snap_com.is_dir()) == ("OLD", False, True)


@pytest.mark.fast
def test_kill_gt14_load_probe_module_overlay_and_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uccide mutanti _load_probe_module su precedenza .staging, cache e fallback stdlib."""
    mod_name = "nk_tmp_probe_kill_xyz"
    monkeypatch.delitem(sys.modules, mod_name, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert rsi_gt14._load_probe_module(tmp_path / "empty_ws", "json") is json
    ws = tmp_path / "ws_probe_ld"
    (ws / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "scripts" / f"{mod_name}.py").write_text("VAL = 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / f"{mod_name}.py").write_text("VAL = 2\n", encoding="utf-8")
    m1 = rsi_gt14._load_probe_module(ws, mod_name)
    m2 = rsi_gt14._load_probe_module(ws, mod_name)
    assert (m1.VAL, m2 is m1, str(ws / ".staging" / "scripts") in sys.path) == (2, True, True)


@pytest.mark.fast
def test_kill_gt14_run_dast_probe_paths(tmp_path: Path) -> None:
    """Uccide mutanti _run_dast_probe con connettore locale senza mock."""
    class _DummyDast:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._p = payload

        def run_staging_shadow_verification(self, **_kw: Any) -> Dict[str, Any]:
            return self._p

    ext_res, ext_tr = rsi_gt14._run_dast_probe(tmp_path, tmp_path, False, lambda _r, _n: None, {"status": "PASS", "passed": True})
    assert (ext_res["source"], ext_res["passed"], ext_tr) == ("external_dast_report", True, None)
    _, tr_no_exec = rsi_gt14._run_dast_probe(tmp_path, tmp_path, True, lambda _r, _n: _DummyDast({"passed": True, "pytest": {"executed": False}}))
    assert tr_no_exec is None
    res_ok, tr_ok = rsi_gt14._run_dast_probe(
        tmp_path, tmp_path, True,
        lambda _r, _n: _DummyDast({"passed": True, "pytest": {"executed": True, "tests_passed": 5, "tests_total": 5, "duration_s": 0.4, "branch_coverage_pct": None}}),
    )
    assert (res_ok["passed"], tr_ok is not None and tr_ok["duration_s"] == 0.4, tr_ok is not None and "branch_coverage_pct" not in tr_ok) == (True, True, True)


@pytest.mark.fast
def test_kill_report_sanitizers_dast_blockers() -> None:
    """Uccide tutti i mutanti _has_dast_blockers su timeout, dry_run, status e passed."""
    assert rsi_rs._has_dast_blockers({"timed_out": True, "status": "PASS", "passed": True}, "PASS") is True
    assert rsi_rs._has_dast_blockers({"timed_out": False, "memory_exceeded": None, "status": "PASS", "passed": True}, "PASS") is True
    assert rsi_rs._has_dast_blockers({"timed_out": False, "is_dry_run": True, "status": "PASS", "passed": True}, "PASS") is True
    assert rsi_rs._has_dast_blockers({"dry_run": True, "status": "PASS", "passed": True}, "PASS") is True
    assert rsi_rs._has_dast_blockers({"status": "DRY_RUN", "passed": True}, "DRY_RUN") is True
    assert rsi_rs._has_dast_blockers({"status": None, "passed": True}, "PASS") is True
    assert rsi_rs._has_dast_blockers({"status": "FAIL", "passed": True}, "FAIL") is True
    assert rsi_rs._has_dast_blockers({"status": "PASS", "passed": False}, "PASS") is True
    assert rsi_rs._has_dast_blockers({"timed_out": False, "is_dry_run": False, "dry_run": False, "status": "PASS", "passed": True}, "PASS") is False


@pytest.mark.fast
def test_kill_tensor_session_guard_hmac_and_skew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uccide mutanti _verify_active_hmac_and_ttl su HMAC, expires_at, issued_at e skew."""
    key_b = b"secret-tensor-guard-key-material!"
    kp = tmp_path / "tsg.key"
    kp.write_bytes(key_b)
    monkeypatch.setenv("NK_TENSOR_RSI_HMAC_KEY_PATH", str(kp))
    w2_tsg._verify_active_hmac_and_ttl(_sign_active(key_b, {"issued_at": 1030.0, "expires_at": 1000.0}), now_ts=1000.0)
    bad_sig = _sign_active(key_b, {"issued_at": 1000.0, "expires_at": 2000.0})
    bad_sig["hmac_sha256"] = ("1" if bad_sig["hmac_sha256"][0] == "0" else "0") + bad_sig["hmac_sha256"][1:]
    cases = [
        ({"expires_at": 2000.0}, "mancante"),
        (bad_sig, "verifica firma"),
        (_sign_active(key_b, {"expires_at": 0.0}), "expires_at"),
        (_sign_active(key_b, {"expires_at": 1000.0}), "scaduta"),
        (_sign_active(key_b, {"issued_at": 0.0, "expires_at": 2000.0}), "issued_at"),
        (_sign_active(key_b, {"issued_at": 1031.0, "expires_at": 2000.0}), "issued_at"),
    ]
    for payload, msg in cases:
        with pytest.raises(TwoPhaseCommitError, match=msg):
            w2_tsg._verify_active_hmac_and_ttl(payload, now_ts=1001.0 if msg == "scaduta" else 1000.0)


@pytest.mark.fast
def test_kill_tensor_session_guard_try_remove_empty_dir(tmp_path: Path) -> None:
    """Uccide mutanti _try_remove_empty_dir su assenza, file regolare, dir piena e vuota."""
    f_reg = tmp_path / "reg.txt"
    f_reg.write_text("x", encoding="utf-8")
    d_full = tmp_path / "d_full"
    d_full.mkdir()
    (d_full / "child.txt").write_text("c", encoding="utf-8")
    d_empty = tmp_path / "d_empty"
    d_empty.mkdir()
    assert w2_tsg._try_remove_empty_dir(tmp_path / "absent_dir") is True
    assert w2_tsg._try_remove_empty_dir(f_reg) is False
    assert w2_tsg._try_remove_empty_dir(d_full) is False
    assert (w2_tsg._try_remove_empty_dir(d_empty), d_empty.exists(), d_full.is_dir()) == (True, False, True)


@pytest.mark.fast
def test_kill_dast_ast_guard_staging_routing(tmp_path: Path) -> None:
    """Verifica routing NVMe su .staging vuoto e attivazione su file staged."""
    assert dast_e2e._has_staged_changes(None) is False
    stg = tmp_path / ".staging"
    assert dast_e2e._has_staged_changes(stg) is False
    stg.mkdir()
    (stg / ".gitkeep").write_text("", encoding="utf-8")
    assert dast_e2e._has_staged_changes(stg) is False
    gs = tmp_path / "scripts" / "ast_guard_validator.py"
    oh = tmp_path / "scripts" / "_internal" / "ast_guard_validator" / "overlay_helpers.py"
    oh.parent.mkdir(parents=True)
    gs.write_text("# stub\n", encoding="utf-8")
    oh.write_text("# stub\n", encoding="utf-8")
    sb_dir = tmp_path / "nvme_sb"
    cmd_empty, cwd_empty = dast_e2e._build_ast_guard_cmd(gs, sb_dir, tmp_path, stg, sys)
    assert (cwd_empty, "--overlay-staging" in cmd_empty) == (sb_dir, False)
    (stg / "mod.py").write_text("X = 1\n", encoding="utf-8")
    assert dast_e2e._has_staged_changes(stg) is True
    cmd_full, cwd_full = dast_e2e._build_ast_guard_cmd(gs, sb_dir, tmp_path, stg, sys)
    assert (cwd_full, "--overlay-staging" in cmd_full) == (tmp_path, True)


@pytest.mark.fast
def test_kill_sast_scanner_staged_subpkg_merge(tmp_path: Path) -> None:
    """Verifica fusione flag CLI _internal/<stem> tra produzione e staging."""
    ws = tmp_path / "ws_sast_flags"
    p_sub = ws / "scripts" / "_internal" / "demo_fac"
    s_scr = ws / ".staging" / "scripts"
    s_sub = s_scr / "_internal" / "demo_fac"
    p_sub.mkdir(parents=True)
    s_sub.mkdir(parents=True)
    (p_sub / "cli.py").write_text('p = ["--prod-only-flag"]\n', encoding="utf-8")
    (s_scr / "demo_fac.py").write_text("X = 1\n", encoding="utf-8")
    (s_sub / "extra.py").write_text('q = ["--stg-only-flag"]\n', encoding="utf-8")
    flags = rsi_sast.extract_script_supported_flags_impl(s_scr / "demo_fac.py")
    assert {"--prod-only-flag", "--stg-only-flag"}.issubset(flags)

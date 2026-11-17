# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Matrice Resilienza, WAL 2PC, SAST Call ed Epistemic Canary.
Modulo: tests/test_sovereign_carbon_cli_resilience_matrix.py.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import (
    WORKSPACE_ROOT as _WORKSPACE_ROOT,
    call_script_main as _call_main,
    call_script_main_captured as _call_main_captured,
    load_script_by_relpath as _load_mod,
)

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
guard_mod = _load_mod("ast_guard_validator", "scripts/ast_guard_validator.py")
dast_mod = _load_mod("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
router_mod = _load_mod("vibe_sprint_router", "scripts/vibe_sprint_router.py")
tr_mod = _load_mod("nk_transcript_tools", "scripts/nk_transcript_tools.py")
rsi_mod = _load_mod("rsi_convergence_engine", "scripts/rsi_convergence_engine.py")
idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")
mem_mod = _load_mod("memory_3tier_engine", "scripts/memory_3tier_engine.py")
map_mod = _load_mod("ast_repo_mapper", "scripts/ast_repo_mapper.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
hand_mod = _load_mod("nk_session_handoff", "scripts/nk_session_handoff.py")
pre_mod = _load_mod("preflight_health_check", "scripts/preflight_health_check.py")
comp_mod = _load_mod("nk_compliance_checker", "scripts/nk_compliance_checker.py")
ipc_mod = _load_mod("nk_ipc_contracts", "scripts/schemas/nk_ipc_contracts.py")
pr_mod = _load_mod("platform_runner", "scripts/platform_runner.py")
qbm_mod = _load_mod("quality_baseline_manager", "scripts/quality_baseline_manager.py")
sentry_mod = _load_mod("nk_context_sentry", "scripts/nk_context_sentry.py")
heal_mod = _load_mod("auto_heal_pipeline", "scripts/auto_heal_pipeline.py")


@pytest.mark.fast
def test_resilience_matrix_contracts_guards_wal_and_dast(
    tmp_path: Path, monkeypatch: Any, capsys: Any, isolated_nk_env: Path
) -> None:
    """Verifica contratti IPC RSI, STT self-correction e role conflict detectors."""
    assert ipc_mod.RSIDefectVector(tests_passed=5, tests_total=5).effective_totals() == (5, 5)
    assert ipc_mod.RSIDefectVector(tests_passed=3, tests_failed=1, tests_total=0).effective_totals() == (3, 4)
    assert ipc_mod.RSIDefectVector(tests_passed=0, tests_failed=0, tests_total=0).effective_totals() == (0, 0)
    eng_dv = rsi_mod.RSIDefectVector(tests_passed=4, tests_total=4)
    rec1 = ipc_mod.RSIIterationRecord(iteration=0, defects={"tests_passed": 4, "tests_total": 4})
    rec2 = ipc_mod.RSIIterationRecord(iteration=1, defects=eng_dv)
    eng_rec = rsi_mod.RSIIterationRecord(
        session_id="S-COV", iteration=2, defects=eng_dv, delta_k=0, fitness_q=100.0, state_hash="a" * 64, verdict="CONVERGED_OPTIMAL"
    )
    sess = ipc_mod.RSISessionReport(session_id="S-COV", history=[rec1, {"iteration": 1}, eng_rec])
    assert len(sess.history) == 3 and rec2.iteration == 1
    assert router_mod._extract_primary_stt_clause("") == ""
    assert router_mod._extract_primary_stt_clause("Apri il file subito") == "Apri il file subito"
    assert "audit" in router_mod._extract_primary_stt_clause("Crea app meteo, anzi no esegui audit di sicurezza SAST").lower()
    assert router_mod._detect_prompt_role_conflicts("") == []
    assert len(router_mod._detect_prompt_role_conflicts("Opera come NK-Security-Auditor e NK-Orchestrator: implementa subito il codice.")) >= 1
    assert len(router_mod._detect_prompt_role_conflicts("Usa NK-RSI-Auditor e modifica subito scripts/a.py senza delegare.")) >= 1
    lint_p = (
        "!diretto\nFase 1: scrivi src_app/a.py.\nFase 2: usa NK-Builder-Agent su Holdout Set B.\n"
        "Fase 3: ripeti finche 100% PASS ed esegui rsi_convergence_engine.py --verify su NK_External_Projects/X.\n"
        "Puoi usare /goal manualmente e leggi canary_v1.json.\n"
    )
    l_res = router_mod.lint_nk_prompt(lint_p)
    assert l_res["passed"] is False and len(l_res["violations"]) >= 5


@pytest.mark.fast
def test_resilience_mapper_wal_memory_and_l3_helpers(
    tmp_path: Path, isolated_nk_env: Path
) -> None:
    """Verifica mapper CSS/HTML, bootstrap WAL quarantine, memory_3tier e Oracle L3 guard."""
    poly_repo = tmp_path / "poly_web"
    poly_repo.mkdir()
    (poly_repo / "styles.css").write_text(".card { padding: 8px; } #nav { top: 0; }\n", encoding="utf-8")
    (poly_repo / "view.html").write_text('<main id="app"><button id="cta">Go</button></main>\n', encoding="utf-8")
    (poly_repo / "big_mod.py").write_text(
        "\n".join(f"def focal_fn_{i}(x: int, y: int) -> int:\n    val = x + y\n    return val + {i}\n" for i in range(3)),
        encoding="utf-8",
    )
    assert "REPO-MAP" in map_mod.RepoMapGenerator.generate(poly_repo).content
    sl_res = map_mod.KarpathySurgicalSlicer.slice_module(
        (poly_repo / "big_mod.py").read_text(encoding="utf-8"), focal_symbol_names=[f"focal_fn_{i}" for i in range(3)], module_path="big_mod.py", max_tokens=20
    )
    assert sl_res.token_count >= 1
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
    assert q2 is not None and q2.exists() and q2 != q1
    m_root = tmp_path / "m_root_ws"
    (m_root / "nk_tracking" / "memory_3tier").mkdir(parents=True)
    cap_out = tmp_path / "cap_tier1.json"
    cap_res = mem_mod.sync_tier1_capsule(base_dir=m_root / "nk_tracking" / "memory_3tier", output_path=cap_out, profile="argon")
    assert cap_out.exists() and "token_cap" in cap_res
    for bad_thr in (True, 1.8):
        with pytest.raises(ValueError):
            mem_mod.consolidate_similar_episodes("ARCH", threshold=bad_thr)
    assert mem_mod.consolidate_similar_episodes("ARCH", threshold=0.9, root=m_root)["passed"] is True
    assert l3_mod._looks_like_disallowed_file_reference("C:\\Windows\\win.ini") is True
    assert l3_mod._looks_like_disallowed_file_reference("../secret.html") is True
    assert l3_mod._looks_like_disallowed_file_reference("secret.env") is True
    assert l3_mod._looks_like_disallowed_file_reference("<div>Ciao mondo</div>") is False
    ev = l3_mod.DOMOracleEvaluator()
    assert ev.evaluate_deltas('<div><img id="logo" src="a.png"/><br/></div>', '<div><img id="logo" src="a.png"/><br/></div>').verdict == "PASS"


@pytest.mark.fast
def test_resilience_hook_fasttrack_stop_and_ast_guard_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica fasttrack >12, stop-evidence fail-closed/verified, e CLI ast_guard fail-closed."""
    assert hook_mod._has_non_readonly_open('open("f.txt", "w")') is True
    assert hook_mod._has_non_readonly_open("open('f.txt', dyn_mode)") is True
    assert hook_mod._has_non_readonly_open('open("f.txt", "r")') is False
    proj = tmp_path / "hg_full_proj"
    for d in (".staging/scripts", "scripts"):
        (proj / d).mkdir(parents=True)
    rc_wg_ok, out_wg_ok, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--project-root", str(proj)],
        stdin_text=json.dumps({"tool_name": "run_command", "tool_input": {"CommandLine": "python -c \"print(1)\" > %TEMP%\\out.txt"}}),
    )
    assert rc_wg_ok == 0 and json.loads(out_wg_ok) == {}
    (hook_mod._get_hooks_temp_dir() / "fasttrack_c_ft.json").write_text(json.dumps({"streak": 14}), encoding="utf-8")
    rc_ft1, out_ft1, _ = _call_main_captured(
        hook_mod, ["fasttrack", "--conversation-id", "c_ft", "--event", "PreToolUse", "--native-contract", "--shadow"], stdin_text="{}"
    )
    assert rc_ft1 == 0 and "injectSteps" in json.loads(out_ft1)
    rc_ft2, out_ft2, _ = _call_main_captured(
        hook_mod,
        ["fasttrack", "--conversation-id", "c_ft2", "--event", "PostToolUse", "--native-contract"],
        stdin_text=json.dumps({"tool_name": "read_file", "tool_input": {"Path": "a.py"}}),
    )
    assert rc_ft2 == 0 and json.loads(out_ft2) == {}
    for _ in range(2):
        monkeypatch.setattr(sys, "stdin", io.StringIO("{malformed_json"))
        assert _call_main(hook_mod, ["stop-evidence", "--conversation-id", "c_mal", "--enforce-stop"], monkeypatch) == 0
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "continue"
    unver_in = json.dumps({"message": "Stato finale CONVERGED_OPTIMAL certificato.", "verifiedExitZero": False})
    for _ in range(2):
        monkeypatch.setattr(sys, "stdin", io.StringIO(unver_in))
        assert _call_main(hook_mod, ["stop-evidence", "--conversation-id", "c_uv", "--enforce-stop"], monkeypatch) == 0
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "continue"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"last_assistant_message": "Stato finale 100% PASS.", "verifiedExitZero": True})))
    assert _call_main(hook_mod, ["stop-evidence", "--conversation-id", "c_uv", "--enforce-stop", "--native-contract"], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "allow"
    err_j = tmp_path / "ag_err.json"
    assert _call_main(guard_mod, ["--target", str(tmp_path / "missing_dir"), "--output-json", str(err_j), "--json"], monkeypatch) == 2
    assert json.loads(capsys.readouterr().out)["passed"] is False
    some_f = tmp_path / "not_a_dir.py"
    some_f.write_text("x: int | str | None = 1\n", encoding="utf-8")
    assert _call_main(guard_mod, ["--stage-dir", str(some_f)], monkeypatch) == 2
    assert "ERROR" in capsys.readouterr().out
    assert guard_mod.ASTGuardValidator().validate_code_edit(
        "def f(a: int | str) -> int | None:\n    x: int | str = 1\n    return 1\n",
        "def f(a: int | str) -> int | None:\n    x: int | str = 2\n    return 2\n",
        target_file="scripts/u.py",
    ).is_valid is True


@pytest.mark.fast
def test_resilience_wal_6_states_and_indexer_global_filter(tmp_path: Path) -> None:
    """Verifica i 6 stati WriteAheadLogManager.recover, apply_global_filter e HealingSnapshotManager."""
    repo = tmp_path / "wal_rec_repo"
    (repo / ".wal").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    custom_w = tmp_path / "custom_wal_dir"
    custom_w.mkdir()
    wal_mgr = w2pc_mod.WriteAheadLogManager(custom_w)
    (repo / ".wal" / "01_list.wal").write_text("[1, 2]", encoding="utf-8")
    (repo / ".wal" / "02_badstate.wal").write_text(json.dumps({"target_path": str(repo / "scripts" / "x.py"), "state": "INVALID"}), encoding="utf-8")
    stg_c, payload_c = tmp_path / "stg_comm.tmp", b"COMMITTED_BYTES = 1\n"
    stg_c.write_bytes(payload_c)
    tgt_c = repo / "scripts" / "replayed.py"
    (repo / ".wal" / "03_comm.wal").write_text(json.dumps({"tx_id": "tx_c", "target_path": str(tgt_c), "staging_path": str(stg_c), "payload_sha256": w2pc_mod.compute_sha256(payload_c), "state": "COMMITTED", "timestamp_utc": time.time() - 50.0}), encoding="utf-8")
    stg_p = tmp_path / "stg_prep.tmp"
    stg_p.write_bytes(b"TEMP")
    (repo / ".wal" / "04_prep_stale.wal").write_text(json.dumps({"tx_id": "tx_ps", "target_path": str(repo / "scripts" / "ps.py"), "staging_path": str(stg_p), "state": "PREPARED", "timestamp_utc": time.time() - 120.0}), encoding="utf-8")
    (repo / ".wal" / "05_prep_active.wal").write_text(json.dumps({"tx_id": "tx_pa", "target_path": str(repo / "scripts" / "pa.py"), "state": "PREPARED", "timestamp_utc": time.time()}), encoding="utf-8")
    stg_a = tmp_path / "stg_ab.tmp"
    stg_a.write_bytes(b"AB")
    (custom_w / "06_aborted.wal").write_text(json.dumps({"tx_id": "tx_ab", "target_path": str(repo / "scripts" / "ab.py"), "staging_path": str(stg_a), "state": "ABORTED", "timestamp_utc": time.time() - 30.0}), encoding="utf-8")
    actions = {r.get("action") for r in wal_mgr.recover(repo, stale_age_sec=10.0)}
    assert tgt_c.read_bytes() == payload_c and {"QUARANTINED_CORRUPT", "REPLAYED_COMMIT", "ABORTED_STALE", "SKIPPED_ACTIVE", "PURGED_ABORTED"}.issubset(actions)
    ws_flt = tmp_path / "flt_ws"
    ws_flt.mkdir()
    assert idx_mod.NKRegistryIndexer(workspace_root=ws_flt, global_config_dir=tmp_path / "no_gcfg").apply_global_filter()["applied"] is False
    ext_gcfg = tmp_path / "ext_readonly_gcfg"
    (ext_gcfg / "skills" / idx_mod.NKRegistryIndexer.GCP_DATA_SKILLS[0]).mkdir(parents=True)
    ro_res = idx_mod.NKRegistryIndexer(workspace_root=ws_flt, global_config_dir=ext_gcfg).apply_global_filter()
    assert ro_res["applied"] is True and ro_res["read_only"] is True
    in_gcfg = ws_flt / "local_gcfg"
    (in_gcfg / "skills" / idx_mod.NKRegistryIndexer.GCP_DATA_SKILLS[0]).mkdir(parents=True)
    (in_gcfg / "plugins" / "science").mkdir(parents=True)
    (in_gcfg / "config.json").write_text("{corrupt_cfg", encoding="utf-8")
    assert idx_mod.NKRegistryIndexer(workspace_root=ws_flt, global_config_dir=in_gcfg).apply_global_filter()["applied"] is True
    sm = heal_mod.HealingSnapshotManager(base_temp_dir=tmp_path / "snaps")
    f_ex, f_new = tmp_path / "tracked_ex.py", tmp_path / "tracked_created_later.py"
    f_ex.write_bytes(b"ORIG = 1\n")
    sid = sm.create_snapshot([f_ex, f_new])
    f_ex.write_bytes(b"MOD = 2\n")
    f_new.write_bytes(b"NEW = 3\n")
    sm.active_snapshots.clear()
    if sm.manifest_path.exists():
        sm.manifest_path.unlink()
    assert all(sm.rollback(sid).values()) and f_ex.read_bytes() == b"ORIG = 1\n" and not f_new.exists()
    assert sm.evaluate_fitness(5, 0, 4, 1, exit_code=0).verdict == heal_mod.FitnessVerdict.PASSED
    assert sm.evaluate_fitness(4, 1, 3, 2, exit_code=1).verdict == heal_mod.FitnessVerdict.IMPROVED
    assert sm.evaluate_fitness(5, 0, 5, 0, exit_code=2).verdict == heal_mod.FitnessVerdict.REGRESSION
    assert sm.evaluate_fitness(3, 2, 3, 2, exit_code=1).verdict == heal_mod.FitnessVerdict.NEUTRAL
    sm.cleanup(sid)


@pytest.mark.fast
def test_resilience_matrix_epistemic_cli_sast_and_bootstrap(
    tmp_path: Path, monkeypatch: Any, capsys: Any, isolated_nk_env: Path
) -> None:
    """Verifica conflitto epistemico base e integrita canary con firma originale."""
    del monkeypatch, capsys, isolated_nk_env
    assert (
        rsi_mod._detect_assertion_epistemic_conflict(
            "20 == compute_tax(100)", "compute_tax(100) == 30"
        )
        == "HALT_EPISTEMIC_CONFLICT"
    )
    can_f = tmp_path / "canary.json"
    can_f.write_text(
        json.dumps({"tasks": [{"task_id": "CAN-1", "test_a": "x == 1", "test_b": "x == 2"}]}),
        encoding="utf-8",
    )
    assert rsi_mod.evaluate_canary_holdout(holdout_path=can_f)["passed"] is True


@pytest.mark.fast
@pytest.mark.parametrize(
    ("a1", "a2", "expected"),
    [
        ("20 == compute_tax(100)", "compute_tax(100) == 30", "HALT_EPISTEMIC_CONFLICT"),
        ("10 < compute_tax(100)", "compute_tax(100) < 5", "HALT_EPISTEMIC_CONFLICT"),
        ("compute_tax(100) == 5", "compute_tax(100) > 10", "HALT_EPISTEMIC_CONFLICT"),
        ("compute_tax(100) >= 10", "compute_tax(100) < 10", "HALT_EPISTEMIC_CONFLICT"),
        ("compute_tax(100) == True", "compute_tax(100) == 1", "HALT_EPISTEMIC_CONFLICT"),
        ("compute_tax(100) == None", "compute_tax(100) == 5", "HALT_EPISTEMIC_CONFLICT"),
        ("compute_tax(100) == y", "compute_tax(100) != y", "HALT_EPISTEMIC_CONFLICT"),
        ("compute_tax(100) == 10", "compute_tax(100) != 10", "HALT_EPISTEMIC_CONFLICT"),
        ("fn_a(1) == 2", "fn_b(1) == 3", "CONSISTENT_NO_CONFLICT"),
        ("x in [1, 2]", "x == 1", "UNRESOLVED_CONFLICT"),
        ("def invalid_syntax(", "x == 1", "UNRESOLVED_CONFLICT"),
    ],
)
def test_resilience_epistemic_conflict_matrix(
    a1: str, a2: str, expected: str
) -> None:
    """Verifica matrice conflitti epistemici AST di rsi_convergence_engine."""
    assert rsi_mod._detect_assertion_epistemic_conflict(a1, a2) == expected


@pytest.mark.fast
def test_resilience_canary_rsi_cli_memory_and_mapper_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica canary holdout, RSI CLI persist-telemetry, memory backup fallback e RepoMap 3-tier."""
    can_dir = tmp_path / "canary_dir"
    can_dir.mkdir()
    assert rsi_mod.evaluate_canary_holdout(holdout_path=can_dir)["passed"] is True
    assert rsi_mod.evaluate_canary_holdout(holdout_path=tmp_path / "missing_sub" / "c.json")["passed"] is True
    mini_ws = tmp_path / "rsi_cli_ws"
    for d in (".agents", "nk_tracking", ".staging"):
        (mini_ws / d).mkdir(parents=True)
    (mini_ws / ".agents" / "guide.md").write_text("# Titolo\n\nFrase breve valida.\n", encoding="utf-8")
    rc_vc1, out_vc1, _ = _call_main_captured(rsi_mod, ["--root", str(mini_ws), "--vibe-check", "."])
    assert rc_vc1 == 0 and "RSI-VIBE-CHECK" in out_vc1
    (mini_ws / ".staging" / "mod.py").write_text("VAL = 1\n", encoding="utf-8")
    rc_vc2, out_vc2, _ = _call_main_captured(rsi_mod, ["--root", str(mini_ws), "--vibe-check", ".", "--json"])
    assert rc_vc2 == 0 and json.loads(out_vc2)["passed"] is True
    rc_sv, out_sv, _ = _call_main_captured(rsi_mod, ["--root", str(mini_ws), "--verify", "--strict-verify"])
    assert rc_sv == 2 and "RSI" in out_sv
    rc_tel, out_tel, _ = _call_main_captured(rsi_mod, ["--root", str(mini_ws), "--verify", "--persist-telemetry"])
    assert rc_tel in (0, 2) and "RSI" in out_tel and (mini_ws / "nk_tracking" / "rsi_telemetry.jsonl").is_file()
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
    comp_sig = map_mod.RepoMapGenerator._compact_sig_for_ste100("async def super_long_fn(a: int, b: str, c: float, d: bool, e: list, f: dict) -> int: ...", max_words=6)
    assert "super_long_fn(" in comp_sig and ": int" not in comp_sig
    rich_repo = tmp_path / "rich_tier_repo"
    rich_repo.mkdir()
    (rich_repo / "cls_methods.py").write_text("class MegaService:\n" + "".join(f"    def m_{i}(self) -> int:\n        return {i}\n" for i in range(5)), encoding="utf-8")
    (rich_repo / "many_fns.py").write_text("".join(f"def util_fn_{i}(x: int) -> int:\n    return x + {i}\n" for i in range(5)), encoding="utf-8")
    (rich_repo / "only_consts.py").write_text("GLOBAL_FLAG = True\nMAX_CAP = 42\n", encoding="utf-8")
    assert "REPO-MAP" in map_mod.RepoMapGenerator.generate(rich_repo, config=map_mod.RepoMapConfig(max_tokens=128, polyglot=True)).content


@pytest.mark.fast
def test_resilience_preflight_auto_fix_and_wal_preservation(tmp_path: Path) -> None:
    """Verifica PreflightHealthChecker check-only vs auto_fix su WAL/stashes/anchor/reports."""
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
    assert len(ph._collect_report_files_shallow()) >= 6 and len(ph._collect_tracking_bak_files_shallow()) >= 1
    assert ph.run_full_check(auto_fix=True)["checks"]["staging_hygiene"]["passed"] is True
    assert not stale_w.exists() and comm_w1.exists() and comm_w2.exists()


@pytest.mark.integration
def test_resilience_git_sync_handoff_stash_and_dast_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica 2PC git_sync con cancellazioni, handoff git stash e DAST trace_coverage."""
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
    prom_res = w2pc_mod.promote_staging_to_production(repo_root=git_ws, verify_baseline=False, cleanup_staging=True, git_sync=True, milestone="NK-MS-TEST-GIT-SYNC")
    assert prom_res["status"] == "SUCCESS" and not obsolete_f.exists() and (git_ws / "scripts" / "promoted_new.py").exists()
    runner2 = dast_mod.DASTSandboxRunner(dast_mod.SandboxConfig(profile="default", trace_coverage=True, timeout_sec=15.0))
    with dast_mod.ShadowSandbox() as sb2:
        (sb2.sandbox_dir / "main_entry.py").write_text("A = 1\n", encoding="utf-8")
        (sb2.sandbox_dir / "alt_entry.py").write_text("B = 2\nprint(B)\n", encoding="utf-8")
        assert asyncio.run(runner2.run_in_sandbox(sb2, ["alt_entry.py", "--flag"], target_script_name="main_entry.py")).exit_code == 0


@pytest.mark.fast
def test_resilience_qbm_compliance_heal_and_patch_notes_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica QBM CLI check/recalibrate, compliance unstage, heal helpers e PATCH_NOTES chunks."""
    b_path = tmp_path / "qbm_cli_baseline.json"
    b_raw = (_WORKSPACE_ROOT / "nk_tracking" / "quality_baseline.json").read_text(encoding="utf-8")
    b_path.write_text(b_raw, encoding="utf-8")
    cur_tot = int(json.loads(b_raw)["metrics"]["unit_tests_total"]["value"])
    assert _call_main(qbm_mod, ["unknown_verb"], monkeypatch) == 1
    assert _call_main(qbm_mod, ["check", "--file", str(b_path), "--metrics", "{bad"], monkeypatch) == 1
    assert _call_main(qbm_mod, ["check", "--file", str(b_path)], monkeypatch) == 1
    assert _call_main(qbm_mod, ["check", "--file", str(b_path), "--metrics", json.dumps({"unit_tests_total": cur_tot, "unit_tests_passed": cur_tot, "unit_tests_pass_pct": 100.0})], monkeypatch) == 0
    assert _call_main(qbm_mod, ["check", "--file", str(b_path), "--metrics", json.dumps({"unit_tests_total": cur_tot - 1, "unit_tests_passed": cur_tot - 1, "unit_tests_pass_pct": 100.0})], monkeypatch) == 1
    assert _call_main(qbm_mod, ["recalibrate", "--file", str(b_path), "--target-tests", "70"], monkeypatch) == 1
    assert comp_mod._is_external_unstage_write("", is_command=False) is False
    assert comp_mod._is_external_unstage_write("NK_External_Projects/App/.staging/a.py", is_command=False) is False
    assert comp_mod._is_external_unstage_write("NK_External_Projects/App/src_app/a.py", is_command=False) is True
    assert comp_mod._is_external_unstage_write("python -m pytest NK_External_Projects/App/tests -q", is_command=True) is False
    assert comp_mod._is_external_unstage_write("Set-Content NK_External_Projects/App/src_app/main.py 'x'", is_command=True) is True
    assert comp_mod._is_exempt_diagnostic_nonzero('{"status": "FAIL", "scores": {}, "procedural_score": 50}') == "EXEMPT_EXTERNAL_AUDIT"
    assert comp_mod._is_exempt_diagnostic_nonzero('{"status": "REFINING", "delta_k": 5}') == "INTERMEDIATE_REFINING"
    assert comp_mod._is_exempt_diagnostic_nonzero("Traceback: ValueError") == "REAL_ERROR"
    assert heal_mod.classify_failure("TimeoutExpired: 5s") == "TIMEOUT_ERROR" and heal_mod.classify_failure("ok", exit_code=0) == "NONE"
    dv_target = tmp_path / "dv_mod.py"
    dv_target.write_text("def f(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    assert heal_mod._build_defect_vector(dv_target, "def f(x: int) -> int:\n    return x\n", 4, 1).tests_passed == 4
    pn_proj = tmp_path / "pn_chunks_proj"
    (pn_proj / ".staging" / "nk_genome").mkdir(parents=True)
    pn_file = pn_proj / ".staging" / "nk_genome" / "PATCH_NOTES.md"
    pn_file.write_text("# CHANGELOG\n\n## [v6.0.0-Carbon] : 2026-11-11\n* Nota corrente.\n\n## [v4.9.0] : 2026-11-08\n* Storico.\n", encoding="utf-8")
    rc_pn, out_pn, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--project-root", str(pn_proj)],
        stdin_text=json.dumps({"tool_name": "multi_replace_file_content", "tool_input": {"TargetFile": str(pn_file), "ReplacementChunks": [{"TargetContent": "* Nota corrente.", "ReplacementContent": "* Aggiornata."}]}}),
    )
    assert rc_pn == 0 and json.loads(out_pn) == {}


@pytest.mark.fast
def test_resilience_sast_call_matrix_and_router_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica matrice SAST visit_Call, lint handoff AP-12/13, router CLI e stdin BOM hook_gate."""
    t_mock, t_umock = "Magic" + "Mock", "unittest." + "mock"
    sast_matrix_src = "\n".join([
        "import marshal, os, pathlib, pickle, subprocess, yaml",
        f"from yaml import SafeLoader\nfrom operator import attrgetter\nfrom {t_umock} import {t_mock}, patch",
        "def probe(s, b, kw, dyn_name, obj):",
        "    subprocess.getoutput('ls'); subprocess.run(['ls'], **kw)",
        "    subprocess.Popen('a', 0, None, None, None, None, None, False, True)",
        "    yaml.unsafe_load(s); yaml.full_load(s); yaml.load(s)",
        "    yaml.load(s, yaml.SafeLoader); yaml.load(s, Loader=SafeLoader)",
        "    open('../secret.txt'); pathlib.Path('../secret.txt'); os.path.join('dir', '../secret.txt')",
        "    attrgetter('lave'[::-1]); attrgetter('__subclasses__')",
        "    __import__('so'[::-1]); __import__('subprocess')",
        "    getattr(os, dyn_name); getattr(obj, 'lave'[::-1]); getattr(globals(), 'x')",
        f"    os.execv('/bin/sh', ['sh']); pickle.loads(b); marshal.loads(b); patch('a.b')\n    return {t_mock}()",
    ])
    assert len(guard_mod.ASTGuardValidator.check_sast_constructs(sast_matrix_src)) >= 14
    err_out_json = tmp_path / "guard_err" / "err.json"
    single_clean_py = tmp_path / "single_clean.py"
    single_clean_py.write_text("def add_two(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    assert _call_main(guard_mod, ["--target", "   ", "--output-json", str(err_out_json)], monkeypatch) == 2 and err_out_json.is_file()
    assert _call_main(guard_mod, ["--stage-dir", str(single_clean_py), "--json"], monkeypatch) == 2
    assert _call_main(guard_mod, [str(single_clean_py)], monkeypatch) == 0
    assert "PASS" in capsys.readouterr().out
    h_codes = {v["code"] for v in router_mod.lint_nk_prompt("VIETATO usare mock.\nINTRINSIC_GOAL ora.\nScegli Pista 1A oppure Pista 1B.\n", mode="state-handoff")["violations"]}
    assert "AP-12" in h_codes and "AP-13" in h_codes
    pf = tmp_path / "cli_prompt.txt"
    pf.write_text("Spiega la struttura di scripts/vibe_sprint_router.py", encoding="utf-8")
    assert _call_main_captured(router_mod, ["--prompt-file", str(pf), "--json"])[0] == 0
    assert _call_main_captured(router_mod, ["--stdin", "--json"], stdin_text="Mostra stato indice O(1)")[0] == 0
    rc_rt, out_rt, _ = _call_main_captured(router_mod, ["Analizza", "indice", "registro", "--json"])
    assert rc_rt == 0 and "recommended_mode" in json.loads(out_rt)

    class _BinStdin:
        def __init__(self, data: bytes) -> None: self.buffer = io.BytesIO(data)
        def isatty(self) -> bool: return False

    monkeypatch.setattr(sys, "stdin", _BinStdin(b'\xef\xbb\xbf{"tool_name": "read_file"}'))
    assert hook_mod._read_stdin_payload_ex() == ({"tool_name": "read_file"}, False)


@pytest.mark.fast
def test_resilience_bootstrap_wal_matrix_and_transcript_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica matrice WAL bootstrap, fail-closed mutex, sentry, handoff >32KB e transcript_tools."""
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
    assert bs_poll._inspect_wal_state(poll_ws / ".wal" / "empty.wal") == "CORRUPTED"
    assert bs_poll._inspect_wal_state(poll_ws / ".wal" / "pend.wal") == "VALID_PENDING"
    assert bs_poll._is_committed_wal_file(poll_ws / ".wal" / "jcomm.wal_2pc.jsonl") is True
    assert bs_poll._is_committed_wal_file(poll_ws / ".wal" / "comm_prep.wal_2pc.jsonl") is False
    assert bs_poll.run_bootstrap(fast_stat=False)["checks"]["project_isolation"]["passed"] is False
    guard_ws = tmp_path / "wal_mutex_fail_closed"
    (guard_ws / ".wal").mkdir(parents=True)
    stale_guard = guard_ws / ".wal" / "stale_guard.wal"
    stale_guard.write_text('{"state": "PREPARED"}\n', encoding="utf-8")
    os.utime(stale_guard, (time.time() - 300.0, time.time() - 300.0))
    bs_guard = boot_mod.NKSessionBootstrap(workspace_root=guard_ws, conversation_id="conv-guard")
    with monkeypatch.context() as mp_m:
        mp_m.setattr(sys, "platform", "win32")
        mp_m.setattr(bs_guard, "_try_acquire_2pc_mutex_nonblocking", lambda _root=None: -1)
        assert bs_guard._purge_stale_wal_files(ttl_seconds=10.0)["mutex_error"] is True and stale_guard.exists()
    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"usage": {"prompt_tokens": 4096}}) == 4096
    assert _call_main(sentry_mod, ["--verbose"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() != ""
    big_tp = tmp_path / "big_tp.jsonl"
    big_tp.write_text("".join(f'{{"step": {i}, "content": "{"x" * 80}"}}\n' for i in range(450)), encoding="utf-8")
    assert hand_mod._read_transcript_summary_fast(str(big_tp))[1] > 32768
    assert tr_mod.verify_ste100_compliance("<yaml_metadata_card>\nx\n</yaml_metadata_card>\nFrase attiva valida.\n")["passed"] is True
    (poll_ws / "tests").mkdir(exist_ok=True)
    (poll_ws / "tests" / "test_mini.py").write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")
    assert tr_mod.handle_oracle_lock("freeze", poll_ws / "tests", tmp_path / "olock.json")[1] == 0

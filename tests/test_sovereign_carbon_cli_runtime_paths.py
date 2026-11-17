# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Percorsi Runtime CLI, Handoff, Memory e Preflight.
Modulo: tests/test_sovereign_carbon_cli_runtime_paths.py.
"""

from __future__ import annotations

import ast
import gzip
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import (
    call_script_main as _call_main,
    call_script_main_captured as _call_main_captured,
    load_script_by_relpath as _load_mod,
)

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
guard_mod = _load_mod("ast_guard_validator", "scripts/ast_guard_validator.py")
dast_mod = _load_mod("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
router_mod = _load_mod("vibe_sprint_router", "scripts/vibe_sprint_router.py")
tr_mod = _load_mod("nk_transcript_tools", "scripts/nk_transcript_tools.py")
rsi_mod = _load_mod("rsi_convergence_engine", "scripts/rsi_convergence_engine.py")
mem_mod = _load_mod("memory_3tier_engine", "scripts/memory_3tier_engine.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
hand_mod = _load_mod("nk_session_handoff", "scripts/nk_session_handoff.py")
pre_mod = _load_mod("preflight_health_check", "scripts/preflight_health_check.py")
hb_mod = _load_mod("async_heartbeat_signaler", "scripts/async_heartbeat_signaler.py")
act_mod = _load_mod("nk_active_runtime_sentinel", "scripts/nk_active_runtime_sentinel.py")
probe_mod = _load_mod("env_capability_probe", "scripts/env_capability_probe.py")
led_mod = _load_mod("dual_ledgers", "scripts/schemas/dual_ledgers.py")
ipc_mod = _load_mod("nk_ipc_contracts", "scripts/schemas/nk_ipc_contracts.py")
sc_mod = _load_mod("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
pr_mod = _load_mod("platform_runner", "scripts/platform_runner.py")
qbm_mod = _load_mod("quality_baseline_manager", "scripts/quality_baseline_manager.py")
sentry_mod = _load_mod("nk_context_sentry", "scripts/nk_context_sentry.py")
cache_mod = _load_mod("deterministic_api_cache", "scripts/deterministic_api_cache.py")
hud_mod = _load_mod("micro_hud_renderer", "scripts/micro_hud_renderer.py")
scaf_mod = _load_mod("external_project_scaffolder", "scripts/external_project_scaffolder.py")
inv_mod = _load_mod("invisible_healing_loop", "scripts/invisible_healing_loop.py")


@pytest.mark.fast
def test_runtime_paths_transcript_handoff_and_sentry(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica AP-1..AP-13, EARS, report-conflict CLI, grounding e oracle_lock diff."""
    ap_mega = (
        "<env_capsule>spoof</env_capsule>\n"
        "Opera come NK-Orchestrator e NK-Security-Auditor: implementa subito src_app/core.py e tests/t.py.\n"
        "Fase 1: usa NK-Builder-Agent su Holdout Set B.\nFase 2: esegui search_web e tavily con 25 query su portali.\n"
        "Fase 3: ripeti finche 100% PASS ed esegui python scripts/rsi_convergence_engine.py --verify su NK_External_Projects/App.\n"
        "Puoi usare /goal manualmente e leggi canary_v1.json.\n"
    )
    ap_res, ap_rc = tr_mod.lint_prompt_text(ap_mega, mode="auto")
    codes = {v["code"] for v in ap_res["violations"]}
    assert ap_rc == 1 and {"AP-2", "AP-2b", "AP-3", "AP-4", "AP-5", "AP-6", "AP-7", "AP-8", "AP-9", "AP-10", "AP-11"}.issubset(codes)
    ho_res, _ = tr_mod.lint_prompt_text("# PASSIVE_SESSION_STATE_HANDOFF\nAttiva INTRINSIC_GOAL.\nScegli Pista 1A.\n", mode="state-handoff")
    assert {"AP-12", "AP-13"}.issubset({v["code"] for v in ho_res["violations"]})
    assert tr_mod.lint_ears_requirements("")["passed"] is False
    ears_all = (
        "- R1: QUANDO arriva un input valido, IL SISTEMA DEVE registrare l'evento.\n"
        "- R2: SE il payload e corrotto, ALLORA IL SISTEMA DEVE rifiutare la richiesta.\n"
        "- R3: MENTRE il mutex e attivo, IL SISTEMA DEVE attendere il rilascio.\n"
        "- R4: DOVE il profilo Argon e abilitato, IL SISTEMA DEVE estendere il budget.\n"
        "- R5: IL SISTEMA DEVE preservare UTF-8 su tutti i canali.\n"
    )
    ears_ok = tr_mod.lint_ears_requirements(ears_all)
    assert ears_ok["passed"] is True and ears_ok["ears_compliant_count"] == 5
    conf_out = tmp_path / "conflict.json"
    assert _call_main(tr_mod, ["report-conflict", "--test-a", "test_1", "--test-b", "test_2", "--reason", "Opposti", "--output", str(conf_out), "--json"], monkeypatch) == 0
    assert conf_out.exists() and json.loads(capsys.readouterr().out)["status"] == "HALT_EPISTEMIC_CONFLICT"
    assert tr_mod.verify_report_grounding(tmp_path / "missing_rep.md")["passed"] is False
    rep_neg = tmp_path / "negated.md"
    rep_neg.write_text("Lo script inesistente `scripts/nk_2pc_promoter.py` e vietato nella denylist.\n", encoding="utf-8")
    assert tr_mod.verify_report_grounding(rep_neg)["passed"] is True
    rep_hal = tmp_path / "hallucinated.md"
    rep_hal.write_text("| 1 | `scripts/nk_2pc_promoter.py` |\nEsegui `python scripts/nk_ast_guard.py`.\n", encoding="utf-8")
    assert tr_mod.verify_report_grounding(rep_hal)["passed"] is False
    t_dir = tmp_path / "ol_tests"
    t_dir.mkdir()
    (t_dir / "test_one.py").write_text("def test_1(): assert True\n", encoding="utf-8")
    (t_dir / "test_two.py").write_text("def test_2(): assert True\n", encoding="utf-8")
    ol_f = tmp_path / "oracle_lock.json"
    tr_mod.handle_oracle_lock("freeze", t_dir, ol_f)
    (t_dir / "test_one.py").write_text("def test_1(): assert False\n", encoding="utf-8")
    (t_dir / "test_two.py").unlink()
    (t_dir / "test_three.py").write_text("def test_3(): assert True\n", encoding="utf-8")
    ol_res, ol_rc = tr_mod.handle_oracle_lock("verify", t_dir, ol_f)
    assert ol_rc == 1 and len(ol_res["mismatches"]) == 3


@pytest.mark.fast
def test_runtime_handoff_preflight_anchor_and_memory_gz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica CLI handoff, preflight sanitize anchor, memory .gz, sentinel e DualLedgers."""
    ws = tmp_path / "ho_ws"
    (ws / "nk_tracking" / "anchor").mkdir(parents=True)
    (ws / "nk_genome").mkdir(parents=True)
    (ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"unit_tests_total": 138, "pass_rate_pct": 100.0}), encoding="utf-8")
    tr_ho = tmp_path / "ho_tr.jsonl"
    tr_ho.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Completa WP-7"}) + "\n", encoding="utf-8")
    out_ho = tmp_path / "ho_out"
    assert _call_main(hand_mod, ["--root", str(ws), "--checkpoint-turn", "2", "--gate-status", "PASS", "--milestone-id", "MS-CARBON"], monkeypatch) == 0
    assert _call_main(hand_mod, ["--root", str(ws), "--resume-from-anchor"], monkeypatch) == 0
    assert _call_main(hand_mod, ["--project-root", str(ws), "--transcript", str(tr_ho), "--generate-active-context", "--profile", "argon"], monkeypatch) == 0
    assert _call_main(hand_mod, ["--project-root", str(ws), "--transcript", str(tr_ho), "--output-dir", str(out_ho), "--compile-state-handoff"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() != ""
    pre_ws = tmp_path / "pre_anchor_ws"
    (pre_ws / "nk_tracking" / "anchor").mkdir(parents=True)
    anch_p = pre_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    anch_p.write_text('{"valid": 1}\n{corrupt_line\n', encoding="utf-8")
    pf_res = pre_mod.PreflightHealthChecker(workspace_root=pre_ws).run_full_check(auto_fix=True)
    assert pf_res["checks"]["ssot_anchor"]["passed"] is True and len(anch_p.read_text(encoding="utf-8").splitlines()) == 1
    mem_dir = tmp_path / "mem_store"
    mem_eng = mem_mod.ThreeTierMemoryEngine(base_dir=mem_dir)
    canon_dom = mem_mod.resolve_domain("ARCH")
    mem_eng._archive_to_tier3(canon_dom, [mem_mod.MemoryEpisode(episode_id="ep_k1", domain=canon_dom, title="Architettura 2PC", content="Commit atomico Win32 con journal v2", tags=["2pc", "wal"])])
    with gzip.open(mem_dir / canon_dom / "archive.cold.jsonl.gz", "ab") as gf:
        gf.write(b"{bad_json_line\n")
    assert len(mem_eng.get_tier3_episodes("ARCH")) == 1 and len(mem_eng.recall_hybrid("ARCH", "Architettura 2PC atomico", top_k=3)) >= 1
    assert _call_main(act_mod, ["--steps", "85", "--profile", "standard"], monkeypatch) == 2
    assert _call_main(act_mod, ["--transcript", str(tr_ho), "--profile", "standard", "--json"], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "GREEN"
    assert _call_main(probe_mod, ["--check-module", "json", "--json"], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["available"] is True
    pl = led_mod.ProgressLedger(tmp_path / "prog.jsonl")
    pl.append_event("E0", "T0", 1, "STARTED", {"k": 1})
    assert len(pl.read_events("T0")) == 1
    assert ipc_mod.IPCPointerReturn(status="OK", pointer_uri="file:///tmp/x.bin", sha256="a" * 64, crc32=12345, byte_size=10).status == "OK"


@pytest.mark.integration
def test_runtime_heartbeat_thread_watchdog(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Verifica ciclo thread AsyncHeartbeatSignaler con watchdog e reset_step."""
    hb_log = tmp_path / "hb.jsonl"
    sig = hb_mod.AsyncHeartbeatSignaler(step_name="cov_step", cadence_sec=0.005, watchdog_sec=0.012, telemetry_file=hb_log)
    sig.last_beat_time = time.time() - 1.0
    sig.start()
    time.sleep(0.012)
    sig.reset_step("phase_2")
    sig.stop()
    assert hb_log.exists() and sig.pulse_count >= 1


@pytest.mark.fast
def test_runtime_transcript_cli_and_sentry_mss_blind_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica CLI compliance/evidence con --conversation-id e rami MSS/blind-read/corrupt in sentry."""
    brain = tmp_path / "cli_brain"
    c_logs = brain / "conv_ok" / ".system_generated" / "logs"
    c_logs.mkdir(parents=True)
    tp = c_logs / "transcript.jsonl"
    tp.write_text(
        json.dumps({"source": "USER", "type": "USER_INPUT", "content": "avvia nk hub"}) + "\n"
        + json.dumps({"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Fatto.", "tool_calls": [{"name": "read_file", "arguments": {"Path": "missing.py"}}]}) + "\n"
        + json.dumps({"source": "TOOL", "type": "TOOL_RESULT", "status": "ERROR", "content": "file does not exist"}) + "\n",
        encoding="utf-8",
    )
    assert _call_main_captured(tr_mod, ["compliance", "--conversation-id", "nope", "--brain-dir", str(brain)])[0] != 0
    assert _call_main_captured(tr_mod, ["evidence", "--conversation-id", "nope", "--brain-dir", str(brain)])[0] != 0
    rc_comp, out_comp, _ = _call_main_captured(tr_mod, ["compliance", "--conversation-id", "conv_ok", "--brain-dir", str(brain)])
    assert rc_comp in (0, 1) and "max_consecutive_direct_tools" in json.loads(out_comp)
    rc_ev, out_ev, _ = _call_main_captured(tr_mod, ["evidence", "--conversation-id", "conv_ok", "--brain-dir", str(brain)])
    assert rc_ev == 0 and out_ev.strip() != ""
    sentry = sentry_mod.NKContextSentry()
    corrupt_tr = tmp_path / "corrupt_only.jsonl"
    corrupt_tr.write_text("not_json_line_1\nnot_json_line_2\n", encoding="utf-8")
    assert sentry.analyze_transcript(corrupt_tr)["status"] == "ERROR"
    swarm_tr = tmp_path / "swarm_heavy.jsonl"
    long_msg = "[Message] sender=w1 " + ("parola " * 350)
    swarm_records = [
        {"step_index": 0, "type": "USER_INPUT", "content": "Analizza"},
        {"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": long_msg},
        {"step_index": 2, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file", "arguments": {"Path": "missing_x.py"}}]},
        {"step_index": 3, "source": "TOOL", "type": "TOOL_RESULT", "status": "ERROR", "content": "file does not exist"},
        {"step_index": 4, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "invoke_subagent", "arguments": {"Role": "Auditor"}}]},
    ]
    swarm_tr.write_text("\n".join(json.dumps(r) for r in swarm_records) + "\n", encoding="utf-8")
    rep_sw = sentry.analyze_transcript(swarm_tr)
    assert rep_sw["swarm_hygiene_violations_count"] >= 1 and rep_sw["blind_read_errors"] >= 1
    assert _call_main(sentry_mod, ["--transcript", str(swarm_tr), "--json"], monkeypatch) in (0, 1, 2)
    assert json.loads(capsys.readouterr().out)["status"] in ("GREEN", "YELLOW", "RED")
    assert _call_main(sentry_mod, ["--transcript", str(swarm_tr)], monkeypatch) in (0, 1, 2)
    assert capsys.readouterr().out.strip() != ""


@pytest.mark.fast
def test_runtime_transcript_brain_discovery_and_ste100(tmp_path: Path) -> None:
    """Verifica discover_active_main_transcript (>25 dir), count_transcript_steps e tabelle STE100."""
    brain = tmp_path / "fake_brain"
    brain.mkdir()
    assert tr_mod.discover_active_main_transcript(brain_dir=tmp_path / "missing_b") is None
    assert tr_mod.discover_active_main_transcript(brain_dir=brain) is None
    for i in range(26):
        cdir = brain / f"conv_sub_{i:02d}" / ".system_generated" / "logs"
        cdir.mkdir(parents=True)
        if i == 25:
            (cdir / "transcript.jsonl").write_text(json.dumps({"source": "SYSTEM", "content": "<Agent System Instructions> <subagent_reminder>"}) + "\n", encoding="utf-8")
    main_tp = brain / "conv_main_active" / ".system_generated" / "logs" / "transcript.jsonl"
    main_tp.parent.mkdir(parents=True)
    main_tp.write_text(json.dumps({"source": "USER", "step_index": 0, "content": "avvia nk hub"}) + "\n" + json.dumps({"source": "MODEL", "step_index": 1, "content": "OK"}) + "\n", encoding="utf-8")
    found = tr_mod.discover_active_main_transcript(brain_dir=brain, max_age_seconds=300.0)
    assert found is not None and found.resolve() == main_tp.resolve()
    assert tr_mod.count_transcript_steps(main_tp)[:2] == (2, 2) and tr_mod.count_transcript_steps(tmp_path / "no_tr.jsonl") == (0, 0, 0)
    rich_md = "---\ntitle: Specifica\nversion: 6.0.0-Carbon\n---\n# Intestazione\n| Colonna | Valore |\n| --- | --- |\n| Stato | Attivo |\n\n* Voce breve con `span`.\nFrase attiva valida.\n"
    assert tr_mod.verify_ste100_compliance(rich_md)["passed"] is True


@pytest.mark.fast
def test_runtime_paths_dast_2pc_preflight_and_baseline(
    tmp_path: Path, monkeypatch: Any, capsys: Any, isolated_nk_env: Path
) -> None:
    """Verifica DAST RSS/fallback e guardie promote_staging_to_production."""
    cur_pid = os.getpid()
    rss_first = dast_mod._get_process_memory_rss(cur_pid, p_process=None)
    assert rss_first >= 0 and dast_mod._get_process_memory_rss(cur_pid, p_process=None) == rss_first
    assert dast_mod._terminate_process_tree_fallback(0) == 0
    rep_dir = tmp_path / "dast_rep_dir"
    rep_dir.mkdir()
    p_dir = dast_mod.resolve_dast_report_path(rep_dir, explicit_output=rep_dir)
    assert p_dir.parent == rep_dir and p_dir.name.startswith("dast_report_")
    assert dast_mod.write_atomic_dast_report({"ok": True}, rep_dir).exists()
    repo = tmp_path / "prom_repo"
    repo.mkdir()
    with pytest.raises(FileNotFoundError):
        w2pc_mod.promote_staging_to_production(repo_root=repo)
    stg = repo / ".staging"
    stg.mkdir()
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=repo, verify_baseline=True)
    (stg / ".deleted_files.json").write_text("123", encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=repo)
    (repo / "nk_tracking").mkdir(parents=True)
    (repo / "nk_tracking" / "oracle_lock.json").write_text("{}", encoding="utf-8")
    (stg / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["nk_tracking/oracle_lock.json"]}), encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=repo)
    (stg / ".deleted_files.json").unlink()
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "same.py").write_text("SAME = 1\n", encoding="utf-8")
    (repo / "scripts" / "to_del.py").write_text("DEL = 1\n", encoding="utf-8")
    (stg / "scripts").mkdir(parents=True)
    (stg / "scripts" / "same.py").write_text("SAME = 1\n", encoding="utf-8")
    (stg / "scripts" / "brand_new.py").write_text("NEW = 2\n", encoding="utf-8")
    (stg / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["scripts/to_del.py"]}), encoding="utf-8")
    res = w2pc_mod.promote_staging_to_production(repo_root=repo, milestone="MS-PROM-TEST", git_sync=False, cleanup_staging=True)
    assert res["status"] == "SUCCESS" and len(res["unchanged_files"]) == 1 and not (repo / "scripts" / "to_del.py").exists() and (repo / "scripts" / "brand_new.py").exists()


@pytest.mark.fast
def test_runtime_preflight_wal_tombstones_qbm_and_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica preflight WAL monotonic, tombstones P1-1, QBM anomalies e router transcript tail."""
    is_comm = pre_mod.PreflightHealthChecker._is_committed_wal
    wal_cases = {
        "e.wal": ("", False), "c.wal": ('{"state": "COMMITTED"}', True),
        "j.wal": ('{"state": "PREPARED"}\n{"state": "COMMITTED"}\n', True), "p.wal": ('{"state": "PREPARED"}', False),
        "cp.wal": ('{"state": "COMMITTED"}\n{"state": "PREPARED"}\n', False),
        "cb.wal": ('{"state": "COMMITTED"}\n{bad_json\n', False), "ca.wal": ('{"state": "COMMITTED"}\n[1, 2]\n', False),
    }
    for fname, (body, exp) in wal_cases.items():
        p = tmp_path / fname
        p.write_text(body, encoding="utf-8")
        assert is_comm(p) is exp
    ov_ws = tmp_path / "ov_tombstone_ws"
    ver = str(pre_mod.VERSION)
    for d in (".agents/skills/KeepSkill", ".agents/skills/DelSkill", ".staging", "nk_tracking", "nk_genome"):
        (ov_ws / d).mkdir(parents=True)
    (ov_ws / ".agents" / "AGENTS.md").write_text(f"# NK v{ver}\n## [RULE-01] Base\n", encoding="utf-8")
    (ov_ws / ".agents" / "skills" / "KeepSkill" / "SKILL.md").write_text(f'---\nname: Keep\nversion: "{ver}"\n---\nOk [RULE-01].\n', encoding="utf-8")
    (ov_ws / ".agents" / "skills" / "DelSkill" / "SKILL.md").write_text('---\nname: Del\nversion: "0.0.1-Old"\n---\nOld.\n', encoding="utf-8")
    (ov_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"version": ver, "summary": {"total_skills": 1}}), encoding="utf-8")
    (ov_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"_version": ver, "metrics": {"skills_audited": {"value": 1}, "crv_macro_phases": {"value": 4}, "unit_tests_pass_pct": {"value": 100.0}}}), encoding="utf-8")
    (ov_ws / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": [".agents/skills/DelSkill/SKILL.md"]}), encoding="utf-8")
    ov_chk = pre_mod.PreflightHealthChecker(workspace_root=ov_ws)
    ov_map = ov_chk._collect_agents_overlay()
    assert "skills/DelSkill/SKILL.md" not in ov_map and "skills/KeepSkill/SKILL.md" in ov_map and ov_chk._last_tombstone_error is None
    assert ov_chk._check_ssot_governance()["passed"] is True
    (ov_ws / ".staging" / ".deleted_files.json").write_text("{corrupt_tombstone", encoding="utf-8")
    assert ov_chk._collect_agents_overlay() and bool(ov_chk._last_tombstone_error)
    assert ov_chk._check_ssot_governance()["passed"] is False and bool(ov_chk._check_ssot_governance()["tombstone_error"])
    (ov_ws / ".staging" / ".deleted_files.json").write_text("123", encoding="utf-8")
    assert ov_chk._collect_agents_overlay() and "list" in str(ov_chk._last_tombstone_error)
    assert ov_chk._check_ssot_governance()["passed"] is False


@pytest.mark.fast
def test_runtime_qbm_anomalies_and_router_transcript_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica QBM corrupt/oracle_lock anomalies, preflight purge stale WAL e router >131KB tail."""
    p_ws = tmp_path / "pre_wal_ws"
    (p_ws / ".wal").mkdir(parents=True)
    stale_f = p_ws / ".wal" / "old_tx.wal"
    stale_f.write_text('{"state": "PREPARED"}', encoding="utf-8")
    os.utime(stale_f, (time.time() - 300.0, time.time() - 300.0))
    w_res = pre_mod.PreflightHealthChecker(workspace_root=p_ws)._check_and_purge_stale_wals(auto_fix=True, ttl_seconds=10.0)
    assert w_res["passed"] is True and w_res["purged_count"] == 1
    qb_ws = tmp_path / "qb_ws"
    (qb_ws / "nk_tracking").mkdir(parents=True)
    bl_f = qb_ws / "nk_tracking" / "quality_baseline.json"
    bl_f.write_text("{corrupt_json", encoding="utf-8")
    assert qbm_mod._evaluate_baseline_compliance(str(bl_f), {"unit_tests_passed": 93})[0]["verdict"] == "FAIL"
    assert qbm_mod._evaluate_baseline_compliance(str(bl_f), {"unit_tests_passed": 93}, preloaded_baseline={"metrics": "not_a_dict"})[0]["verdict"] == "FAIL"
    assert qbm_mod._evaluate_baseline_compliance(str(bl_f), {"golden_tests_68": {"passed": 93, "total": 93, "pass_rate_pct": 100.0}}, preloaded_baseline={"unit_tests_passed": 93, "pass_rate_pct": 100.0})[0]["verdict"] == "PASS"
    ol_f = qb_ws / "nk_tracking" / "oracle_lock.json"
    ol_f.write_text("[1, 2, 3]", encoding="utf-8")
    assert len(qbm_mod._verify_oracle_lock_coherence(str(bl_f))) == 1
    ol_f.write_text(json.dumps({"locked_files": ["tests/missing_a.py"], "files": {"tests/missing_b.py": "0" * 64}}), encoding="utf-8")
    assert len(qbm_mod._verify_oracle_lock_coherence(str(bl_f))) == 2
    ol_f.write_text("{bad_lock", encoding="utf-8")
    assert len(qbm_mod._verify_oracle_lock_coherence(str(bl_f))) == 1
    big_tr = tmp_path / "big_transcript.jsonl"
    big_tr.write_text((json.dumps({"type": "MODEL", "content": "x" * 1024}) + "\n") * 140 + json.dumps({"type": "USER_INPUT", "content": "Implementa modulo 2PC"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("NK_TRANSCRIPT_PATH", str(big_tr))
    assert router_mod._read_latest_user_input_from_transcript() == "Implementa modulo 2PC"
    ng_repo = tmp_path / "non_git_ws"
    (ng_repo / ".staging").mkdir(parents=True)
    (ng_repo / ".staging" / "dirty.py").write_text("X = 1\n", encoding="utf-8")
    assert hand_mod._check_git_dirty_fast(ng_repo, "git") == (True, None)
    assert sc_mod.parse_ports_arg("8080, 8081") == [8080, 8081]


@pytest.mark.fast
def test_runtime_paths_bootstrap_heartbeat_and_hook_gate(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica _infer_active_conversation_id, subagent head e _handle_integrity tamper."""
    hooks_d = tmp_path / "boot_hooks"
    hooks_d.mkdir()
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_d))
    assert boot_mod.NKSessionBootstrap._infer_active_conversation_id(60.0) == ""
    (hooks_d / "probe_default.jsonl").write_text("{}", encoding="utf-8")
    (hooks_d / "probe_cid_alpha.jsonl").write_text("{}", encoding="utf-8")
    p_beta = hooks_d / "cid_beta_integrity.json"
    p_beta.write_text("{}", encoding="utf-8")
    now = time.time()
    os.utime(hooks_d / "probe_cid_alpha.jsonl", (now - 10.0, now - 10.0))
    os.utime(p_beta, (now, now))
    assert boot_mod.NKSessionBootstrap._infer_active_conversation_id(60.0) == "cid_beta"
    is_sub = boot_mod.NKSessionBootstrap._is_subagent_transcript_head
    assert is_sub(b"") is False and is_sub(b"   \n") is False
    assert is_sub(b'{"source": "SYSTEM", "content": "init"}\n') is True
    assert is_sub(b'{"source": "USER", "content": "<Agent System Instructions> <subagent_reminder>"}\n') is True
    assert is_sub(b'{"role": "assistant", "text": "[Message] sender=a <env_capsule>"}\n') is True
    assert is_sub(b'{"source": "USER", "content": "procedi"}\n') is False
    assert is_sub(b'not_json <Agent System Instructions> <subagent_reminder>\n') is True
    assert is_sub(b'not_json "source": "USER"\n') is False and is_sub(b'not_json "source": "SYSTEM"\n') is True
    brain = tmp_path / "b_root"
    old_tp = brain / "c_old" / ".system_generated" / "logs" / "transcript.jsonl"
    old_tp.parent.mkdir(parents=True)
    old_tp.write_text("{}", encoding="utf-8")
    os.utime(old_tp, (now - 30.0, now - 30.0))
    assert boot_mod.NKSessionBootstrap._has_newer_brain_directory(old_tp, 60.0) is False
    (brain / "c_new").mkdir(parents=True)
    os.utime(brain / "c_new", (now, now))
    assert boot_mod.NKSessionBootstrap._has_newer_brain_directory(old_tp, 60.0) is True
    root = tmp_path / "int_hub"
    for d in ("nk_tracking", "nk_genome", "tests"):
        (root / d).mkdir(parents=True)
    cp_f, pn_f, ol_f, tf_f = root / "nk_tracking" / "checkpoint_01.json", root / "nk_genome" / "PATCH_NOTES.md", root / "nk_tracking" / "oracle_lock.json", root / "tests" / "test_a.py"
    cp_f.write_text('{"step": 1}', encoding="utf-8")
    pn_f.write_text("## [v4.9.0]\n* Storico immutabile\n", encoding="utf-8")
    ol_f.write_text('{"lock": 1}', encoding="utf-8")
    tf_f.write_text("def test_a(): assert True\n", encoding="utf-8")
    assert hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)[0]["status"] == "UNINITIALIZED"
    (hook_mod._get_hooks_temp_dir() / "c_int_integrity.json").write_text("{corrupt", encoding="utf-8")
    assert hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)[0]["status"] == "CORRUPTED_SNAPSHOT"
    assert hook_mod._handle_integrity("c_int", root, init_mode=True, check_mode=False)[1] == 0
    assert hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)[1] == 0
    cp_f.write_text('{"step": 999}', encoding="utf-8")
    pn_f.write_text("## [v9.9.9]\n* Sovrascritto\n", encoding="utf-8")
    ol_f.write_text('{"lock": 2}', encoding="utf-8")
    tf_f.write_text("def test_a(): assert False\n", encoding="utf-8")
    r_viol, rc_v = hook_mod._handle_integrity("c_int", root, init_mode=False, check_mode=True)
    assert rc_v == 1 and len(r_viol["violations"]) == 4


@pytest.mark.fast
def test_runtime_hb_cli_pidlock_and_hook_ast_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica CLI heartbeat, PIDFileLock crash/preempt, TaskLedger, write-gate e _eval_const_str_expr."""
    assert _call_main(hb_mod, ["--once", "--task-id", "t_json", "--json"], monkeypatch) == 0
    assert _call_main(hb_mod, ["--once", "--task-id", "t_txt"], monkeypatch) == 0
    assert _call_main(hb_mod, ["--max-beats", "2", "--interval", "0.01", "--json"], monkeypatch) == 0
    assert _call_main(hb_mod, ["--max-beats", "1"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() != ""
    assert led_mod.PIDFileLock._is_pid_alive(-1) is False and led_mod.PIDFileLock._is_pid_alive(os.getpid()) is True and led_mod.PIDFileLock._is_pid_alive(99999999) is False
    lf = tmp_path / "stale.lock"
    lf.write_text(json.dumps({"pid": 99999999, "timestamp": time.time() - 120.0}), encoding="utf-8")
    with led_mod.PIDFileLock(lf, stale_timeout_sec=1.0) as lk:
        assert lk.acquired is True
    assert not lf.exists()
    lf_zero = tmp_path / "zero_orphan.lock"
    lf_zero.write_bytes(b"")
    os.utime(lf_zero, (time.time() - 10.0, time.time() - 10.0))
    with led_mod.PIDFileLock(lf_zero, stale_timeout_sec=1.0) as lk_z:
        assert lk_z.acquired is True and "nonce" in json.loads(lf_zero.read_text(encoding="utf-8"))
    lf_pre = tmp_path / "preempt.lock"
    lk_pre = led_mod.PIDFileLock(lf_pre, stale_timeout_sec=0.05)
    assert lk_pre.acquire(timeout_sec=1.0) is True
    lf_pre.write_text(json.dumps({"pid": os.getpid(), "nonce": "other-owner-nonce", "timestamp": time.time() + 60.0}), encoding="utf-8")
    lk_pre.release()
    assert lf_pre.exists() and json.loads(lf_pre.read_text(encoding="utf-8"))["nonce"] == "other-owner-nonce"
    tl = led_mod.TaskLedger(tmp_path / "tasks_dag.jsonl")
    n1 = tl.add_task("T1", "bootstrap", "NK-Orchestrator")
    tl.add_task("T2", "verify", "NK-RSI-Auditor", parent_ids=[n1.task_id])
    assert tl.verify_dag()[0] is True
    proj = tmp_path / "hg_cli_proj"
    for d in (".staging/scripts", "scripts", "nk_tracking"):
        (proj / d).mkdir(parents=True)
    rc_wg1, out_wg1, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--project-root", str(proj)],
        stdin_text=json.dumps({"tool_input": {"Path": str(proj / ".staging" / "scripts" / "a.py")}}),
    )
    assert rc_wg1 == 0 and json.loads(out_wg1) == {}
    rc_bad, out_bad, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--project-root", str(proj)],
        stdin_text=json.dumps({"tool_input": {"Path": str(proj / "scripts" / "prod.py")}}),
    )
    assert rc_bad != 0 or json.loads(out_bad)["decision"] == "deny"
    rc_wg2, out_wg2, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--project-root", str(proj)],
        stdin_text=json.dumps({"tool_input": {"Path": str(tmp_path / "brain" / "conv1" / "scratch" / "note.py")}}),
    )
    assert rc_wg2 == 0 and json.loads(out_wg2) == {}
    checker = guard_mod.SASTConstructChecker("src/expr.py", [])
    checker._const_str_vars["PART"] = "ev"
    expected_map = [
        ("PART + 'al'", "eval"), ("''.join(['e', 'v', 'a', 'l'])", "eval"),
        ("''.join(reversed('lave'))", "eval"), ("f'{PART}al'", "eval"),
        ("'%sal' % ('ev',)", None), ("'xxal'.replace('xx', 'ev')", None),
        ("'lave'[::-1]", "eval"), ("chr(101) + 'val'", "eval"),
    ]
    for ce, exp_str in expected_map:
        assert checker._eval_const_str_expr(ast.parse(ce, mode="eval").body) == exp_str


@pytest.mark.fast
def test_runtime_paths_memory_rsi_and_platform_cli(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica consolidate_similar_episodes, rotate_circular_backups, .bak_1 e RSI fallback."""
    mem_dir = tmp_path / "mem_cons"
    eng = mem_mod.ThreeTierMemoryEngine(base_dir=mem_dir)
    for bad_t in (True, 1.5):
        with pytest.raises(ValueError):
            eng.consolidate_similar_episodes("ARCH", threshold=bad_t)
    canon = mem_mod.resolve_domain("ARCH")
    d_dir = mem_dir / canon
    d_dir.mkdir(parents=True, exist_ok=True)
    t2_f = d_dir / "episodes.jsonl"
    e1 = mem_mod.MemoryEpisode(episode_id="id_1", domain=canon, title="Protocollo 2PC Win32", content="Scrittura atomica con MoveFileExW e journal", tags=["2pc"], metadata={"source_url": "https://example.com/1"})
    e2 = mem_mod.MemoryEpisode(episode_id="id_2", domain=canon, title="Protocollo 2PC Win32", content="Scrittura atomica con MoveFileExW e journal esteso", tags=["wal"], metadata={"evidence_quote": "MoveFileExW"})
    e3 = mem_mod.MemoryEpisode(episode_id="id_3", domain=canon, title="Parser DOM L3", content="Confronto strutturale HTML deterministico", tags=["dom"])
    t2_f.write_text("\n".join(ep.model_dump_json() for ep in (e1, e2, e3)) + "\n", encoding="utf-8")
    assert eng.consolidate_similar_episodes("ARCH", threshold=0.75)["merged_count"] >= 1
    mem_mod.rotate_circular_backups(t2_f, depth=2, backup_dir=d_dir)
    mem_mod.rotate_circular_backups(t2_f, depth=2, backup_dir=d_dir)
    t2_f.write_text("{corrupt_only_line\n", encoding="utf-8")
    assert len(eng._load_tier2_raw(t2_f)) >= 1
    md_good = "---\nname: Test\n---\n# Titolo\n```python\nx = 1 — 2\n```\n| Col1 | Col2 |\n| --- | --- |\n| Val | Ok |\n- Elenco attivo.\nFrase breve conforme.\n"
    assert rsi_mod._fallback_verify_ste100_compliance(md_good)["passed"] is True
    md_bad = "Frase — trattino spaziato.\n" + " ".join(f"p{i}" for i in range(25)) + ".\n"
    fb_bad = rsi_mod._fallback_verify_ste100_compliance(md_bad)
    assert fb_bad["passed"] is False and len(fb_bad["violations"]) >= 2
    ws = tmp_path / "bench_ws"
    (ws / "tests").mkdir(parents=True)
    (ws / ".staging" / "tests").mkdir(parents=True)
    miss_res = rsi_mod.RSIConvergenceEngine(workspace_root=ws, root=ws).run_benchmark_suite(ws / "nonexistent_suite", root_dir=ws)
    assert miss_res["executed"] is False and miss_res["passed"] is False


@pytest.mark.integration
def test_runtime_platform_cache_hud_scaffolder_and_heal_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica platform_runner error/subprocess, api_cache, micro_hud, scaffolder e invisible_healing."""
    rc_nf, _, err_nf = pr_mod.safe_subprocess_run(["nonexistent_binary_xyz_999"])
    assert rc_nf == 127 and "FILE_NOT_FOUND" in err_nf
    rc_ctl, _, err_ctl = pr_mod.safe_subprocess_run("echo hi\necho bye", use_shell=True)
    assert rc_ctl == 1 and "EXECUTION_ERROR" in err_ctl
    assert _call_main(pr_mod, ["--cmd", "nonexistent_cmd_999"], monkeypatch) == 127
    assert _call_main(pr_mod, ["--cmd", f'"{sys.executable}" -B -c "print(42)"', "--no-capture"], monkeypatch) == 0
    with cache_mod.DeterministicApiCache(db_path=tmp_path / "api_cache.db") as dc:
        assert dc.health_check() is True and dc.get_stats()["wal_healthy"] is True and dc.clear() == 0
    assert _call_main(cache_mod, ["--stats"], monkeypatch) == 0
    hud = hud_mod.MicroHUDRenderer(ascii_mode=False)
    hud.set_progress(75)
    hud.set_mutex("LOCKED")
    hud.set_agent_context("NK-Builder-Agent", "DOM-03")
    assert "NK-HUD" in hud.render(include_extras=True, ascii_mode=False)
    assert "NK-HUD" in hud.render(include_extras=True, ascii_mode=True)
    assert _call_main(hud_mod, ["--percent", "90", "--ascii"], monkeypatch) == 0
    assert _call_main(hud_mod, ["--percent", "100", "--json"], monkeypatch) == 0
    with pytest.raises(ValueError):
        scaf_mod.ExternalProjectScaffolder("../bad", tmp_path / "NK_External_Projects" / "Bad")
    ext_target = tmp_path / "NK_External_Projects" / "DemoCrm"
    (ext_target / "genome").mkdir(parents=True)
    (ext_target / "genome" / "concept_map.md").write_text("# Legacy Concept\n", encoding="utf-8")
    scaffolder = scaf_mod.ExternalProjectScaffolder("DemoCrm", ext_target)
    assert len(scaffolder.scaffold(dry_run=True)["created_files"]) >= 5
    assert len(scaffolder.scaffold(dry_run=False)["created_files"]) >= 5
    assert (ext_target / "nk_genome" / "concept_map.md").read_text(encoding="utf-8") == "# Legacy Concept\n"
    assert len(scaffolder.retrofit(dry_run=False)["skipped_existing"]) >= 5
    t_py = tmp_path / "ok_heal_target.py"
    t_py.write_text("X = 10\n", encoding="utf-8")
    pass_cmd = f'"{sys.executable}" -B -c "print(\'1 passed in 0.01s\')"'
    rc_inv, out_inv, _ = _call_main_captured(
        inv_mod, ["--test-cmd", pass_cmd, "--target-file", str(t_py), "--cwd", str(tmp_path), "--json"]
    )
    assert rc_inv == 0 and json.loads(out_inv)["success"] is True

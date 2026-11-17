# -*- coding: utf-8 -*-
"""
Helper Fase 2 Gap Closure v6.4.0-Carbon (prefisso _ per singola collezione pytest).
Modulo: tests/_carbon_gap_closure_helpers.py.
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import (
    call_script_main as _call_main,
    call_script_main_captured as _call_main_cap,
    load_script_by_relpath as _load_mod,
)

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
dast_mod = _load_mod("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
clean_mod = _load_mod("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
scaf_mod = _load_mod(
    "external_project_scaffolder", "scripts/external_project_scaffolder.py"
)
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
heal_mod = _load_mod("auto_heal_pipeline", "scripts/auto_heal_pipeline.py")
snap_mod = _load_mod(
    "healing_snapshot_rollback", "scripts/healing_snapshot_rollback.py"
)
bridge_mod = _load_mod("sbfl_pytest_bridge", "scripts/sbfl_pytest_bridge.py")
router_mod = _load_mod("vibe_sprint_router", "scripts/vibe_sprint_router.py")
tr_mod = _load_mod("nk_transcript_tools", "scripts/nk_transcript_tools.py")
idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")
reg_mod = idx_mod
mem_mod = _load_mod("memory_3tier_engine", "scripts/memory_3tier_engine.py")
map_mod = _load_mod("ast_repo_mapper", "scripts/ast_repo_mapper.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
hand_mod = _load_mod("nk_session_handoff", "scripts/nk_session_handoff.py")
pre_mod = _load_mod("preflight_health_check", "scripts/preflight_health_check.py")
pref_mod = pre_mod
comp_mod = _load_mod("nk_compliance_checker", "scripts/nk_compliance_checker.py")
sent_mod = _load_mod("nk_context_sentry", "scripts/nk_context_sentry.py")
hud_mod = _load_mod("micro_hud_renderer", "scripts/micro_hud_renderer.py")
base_mod = _load_mod("quality_baseline_manager", "scripts/quality_baseline_manager.py")
swarm_mod = _load_mod("nk_swarm_messenger", "scripts/nk_swarm_messenger.py")
hb_mod = _load_mod("async_heartbeat_signaler", "scripts/async_heartbeat_signaler.py")


def _gap_transcript_and_backup_checks(tmp_path: Path) -> Path:
    """Verifica parsing exit code, discovery brain dir e rotazione backup memoria."""
    assert tr_mod.extract_command_exit_code('{"exit_code": 2}') == 2
    assert tr_mod.extract_command_exit_code("Command exited with code 3.") == 3
    assert (
        tr_mod.extract_command_exit_code("Exit code: 0", correlated_tool="other_tool")
        is None
    )
    assert tr_mod._has_missing_path_error("ERROR", "") is True
    assert tr_mod._has_missing_path_error("", "File Path: `file:///a.py`") is False
    assert tr_mod._has_missing_path_error("", "FileNotFoundError: missing") is True
    assert tr_mod.count_transcript_steps(tmp_path / "no_steps.jsonl") == (0, 0, 0)
    assert tr_mod.load_transcript_records(tmp_path / "no_recs.jsonl") == []

    br_dir = tmp_path / "brain_disc"
    for idx_b in range(27):
        d_b = br_dir / f"conv_{idx_b}" / ".system_generated" / "logs"
        d_b.mkdir(parents=True)
        if idx_b == 25:
            (d_b / "transcript.jsonl").write_text(
                "\n[]\n"
                + json.dumps({"step_index": 0, "content": "<SYSTEM_MESSAGE> sender=parent"})
                + "\n",
                encoding="utf-8",
            )
        elif idx_b == 26:
            (d_b / "transcript.jsonl").write_text(
                '{"step_index": 0, "content": "main"}\n', encoding="utf-8"
            )
    found_tp = tr_mod.discover_active_main_transcript(
        brain_dir=br_dir, max_age_seconds=300.0
    )
    assert found_tp is not None and found_tp.name == "transcript.jsonl"
    assert tr_mod.discover_active_main_transcript(brain_dir=tmp_path / "no_brain") is None

    bkp_src = tmp_path / "nk_tracking" / "sub_m" / "ep.jsonl"
    bkp_src.parent.mkdir(parents=True)
    bkp_src.write_text('{"id": 1}\n', encoding="utf-8")
    ext_bkp = mem_mod._resolve_external_backup_dir(bkp_src)
    assert ext_bkp is not None and ext_bkp.name == "sub_m"
    rot_dir = tmp_path / "rot_bkp"
    for _ in range(3):
        mem_mod.rotate_circular_backups(bkp_src, depth=3, backup_dir=rot_dir)
    assert (rot_dir / "ep.jsonl.bak_1").exists()
    return br_dir


def _gap_router_handoff_and_intent_checks() -> None:
    """Verifica validazione handoff passivo e matrice intento di scrittura Router."""
    h_valid = (
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n"
        "Template 12: PASSIVE_SESSION_STATE_HANDOFF\n"
        "### 1. Stato\n"
        "```\nrm -rf /tmp/x\n```\n"
        "Non modificare nulla.\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]"
    )
    assert router_mod.is_passive_state_handoff("") is False
    assert router_mod.is_passive_state_handoff("ciao") is False
    assert (
        router_mod.is_passive_state_handoff(
            "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\nciao"
        )
        is False
    )
    assert (
        router_mod.is_passive_state_handoff(
            "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\nPASSIVE_SESSION_STATE_HANDOFF sha256 bad"
        )
        is False
    )
    assert router_mod.is_passive_state_handoff(h_valid + "\nextra") is False
    assert router_mod.is_passive_state_handoff(h_valid) is True
    assert (
        router_mod.is_passive_state_handoff(
            h_valid.replace("Non modificare nulla.", "modifica subito il file")
        )
        is False
    )

    intent_cases = (
        ("", (False, False)),
        ("rm -rf /tmp/x", (True, False)),
        ("non scrivere in .staging mai", (False, True)),
        ("non toccare ma modifica subito", (True, False)),
        ("valuta refactoring modulo", (False, False)),
        ("non fare la modifica", (False, True)),
        ("esegui la modifica", (False, False)),
        ("fai la modifica", (True, False)),
    )
    for wi_txt, exp_pair in intent_cases:
        assert router_mod._analyze_write_intent(wi_txt) == exp_pair


def _gap_registry_and_repomap_cli_checks(
    tmp_path: Path, monkeypatch: Any, poly_ws: Path
) -> None:
    """Verifica exit code e output CLI per NKRegistryIndexer e ASTRepoMapper."""
    reg_ws = tmp_path / "reg_cli_ws"
    (reg_ws / "scripts").mkdir(parents=True)
    (reg_ws / "nk_genome").mkdir(parents=True)
    (reg_ws / ".agents" / "skills" / "S1").mkdir(parents=True)
    (reg_ws / "scripts" / "s1.py").write_text(
        '"""@domain_id: DOM-03\nS1.\n"""\nX = 1\n', encoding="utf-8"
    )
    (reg_ws / "scripts" / "skip.bak").write_text("bak", encoding="utf-8")
    (reg_ws / "scripts" / "skip.pyc").write_bytes(b"00")
    (reg_ws / ".agents" / "skills" / "S1" / "SKILL.md").write_text(
        "---\nname: S1\ndescription: s1\n---\nBody.\n", encoding="utf-8"
    )
    reg_cases = (
        (["--root", str(reg_ws), "--sync", "--json"], 0),
        (["--root", str(reg_ws), "--build-release-zip", str(tmp_path / "r1.zip")], 0),
        (["--root", str(reg_ws), "--generate-tas-matrix"], 0),
        (["--root", str(reg_ws), "--apply-global-filter"], 0),
        (["--root", str(reg_ws), "--apply-global-filter", "--json"], 0),
        (["--root", str(reg_ws), "--lookup", "DOM-03"], 0),
        (["--root", str(tmp_path / "empty_reg_v"), "--json"], 1),
        (["--root", str(tmp_path / "empty_reg_v")], 1),
    )
    for reg_args, exp_rc in reg_cases:
        assert _call_main(reg_mod, reg_args, monkeypatch) == exp_rc

    rc_sym, out_sym, _ = _call_main_cap(
        map_mod, ["--root", str(poly_ws), "--symbol", "target_fn"]
    )
    assert rc_sym == 0 and "target_fn" in out_sym
    rc_rm, out_rm, _ = _call_main_cap(
        map_mod, ["--root", str(poly_ws), "--max-tokens", "128", "--repo-map"]
    )
    assert rc_rm == 0 and len(out_rm.strip()) > 0
    rc_snap, out_snap, _ = _call_main_cap(
        map_mod,
        ["--root", str(poly_ws), "--snapshot-out", str(tmp_path / "m_snap.md"), "--json"],
    )
    snap_data = json.loads(out_snap[out_snap.index("{") :])
    assert rc_snap == 0 and snap_data["files_scanned"] >= 1 and (tmp_path / "m_snap.md").is_file()


def _gap_router_cli_and_bootstrap_binary_checks(
    tmp_path: Path, monkeypatch: Any, emp_tp: Path, b_ws: Path
) -> Path:
    """Verifica coda transcript 140KB, CLI router e binary tail bootstrap."""
    big_tp = tmp_path / "big_140k.jsonl"
    pad_ln = json.dumps({"source": "MODEL", "content": "x" * 900}) + "\n"
    ckpt_ln = (
        json.dumps(
            {"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction"}
        )
        + "\n"
    )
    usr_ln = json.dumps({"source": "USER", "type": "USER_INPUT", "content": "input finale coda"}) + "\n"
    big_tp.write_text(
        (pad_ln * 80) + ckpt_ln + (pad_ln * 75) + "not_json\n{bad\n" + usr_ln,
        encoding="utf-8",
    )
    monkeypatch.setenv("NK_TRANSCRIPT_PATH", str(big_tp))
    assert router_mod._read_latest_user_input_from_transcript(None) == "input finale coda"
    monkeypatch.delenv("NK_TRANSCRIPT_PATH", raising=False)

    pf_rel_ws = tmp_path / "pf_rel_ws"
    pf_rel_ws.mkdir()
    (pf_rel_ws / "rel_p.txt").write_text("spiega architettura", encoding="utf-8")
    assert _call_main(
        router_mod, ["--prompt-file", str(pf_rel_ws / "rel_p.txt"), "--json"], monkeypatch
    ) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO("spiega codice"))
    assert _call_main(router_mod, ["--stdin", "--json"], monkeypatch) == 0
    assert _call_main(router_mod, ["--classify-prompt", "spiega codice", "--json"], monkeypatch) == 0

    assert boot_mod.NKSessionBootstrap._count_lines_binary_64kb(emp_tp, 0) == 0
    big_sz = big_tp.stat().st_size
    assert boot_mod.NKSessionBootstrap._count_lines_binary_64kb(big_tp, big_sz) >= 100
    assert boot_mod.NKSessionBootstrap._count_post_compaction_binary(emp_tp, 0) == (0, 0)
    st_c, pb_c = boot_mod.NKSessionBootstrap._count_post_compaction_binary(big_tp, big_sz)
    assert st_c >= 1 and pb_c > 0

    sb_cs = boot_mod.NKSessionBootstrap(
        workspace_root=b_ws, conversation_id="conv_cs", transcript_path=big_tp
    )
    cs1 = sb_cs._verify_context_sentry(use_fast_cache=False)
    assert cs1["passed"] is True
    c_exact = {
        "conversation_id": "conv_cs",
        "last_transcript_path": str(big_tp),
        "active_profile": sb_cs.model_profile,
        "transcript_mtime": cs1["transcript_mtime"],
        "transcript_size": big_sz,
        "checks": {"context_sentry": {"passed": True, "status": "GREEN", "step_count": 5, "estimated_tokens": 500}},
    }
    assert sb_cs._verify_context_sentry(use_fast_cache=True, cached=c_exact)["status"] == "GREEN"
    c_delta = dict(c_exact, transcript_size=big_sz - 64, last_transcript_size=big_sz - 64, last_step_count=10)
    assert sb_cs._verify_context_sentry(use_fast_cache=True, cached=c_delta)["passed"] is True
    tail_est = sb_cs._fast_tail_estimate(big_tp, big_sz, c_delta)
    assert tail_est["status"] in ("GREEN", "YELLOW", "ORANGE", "RED") and tail_est["step_count"] >= 10
    return big_tp


def _gap_memory_cold_and_transcript_loc_checks(
    tmp_path: Path, m3_dir: Path, m3_g: Any, big_tp: Path, br_dir: Path
) -> None:
    """Verifica FTS5 guards, transcript locator, STE-100, compliance e oracle lock."""
    assert m3_g.get_tier3_episodes("01_Bug_Diagnostics") == []
    assert mem_mod.sync_tier1_capsule(base_dir=m3_dir, profile="carbon")["profile"] == "carbon"
    for bad_th in (True, "bad", 0.0, 1.5):
        with pytest.raises(ValueError):
            mem_mod.consolidate_similar_episodes(threshold=bad_th, base_dir=m3_dir)
    assert mem_mod.consolidate_similar_episodes(root=m3_dir, threshold=0.8)["passed"] is True

    assert tr_mod.locate_transcript(transcript_arg=str(big_tp))[1] == 0
    assert tr_mod.locate_transcript(transcript_arg=str(tmp_path / "no_loc.jsonl"))[1] == 2
    assert tr_mod.locate_transcript(conversation_id="conv_26", brain_dir=br_dir)[1] == 0
    assert tr_mod.locate_transcript(conversation_id="no_cid", brain_dir=br_dir)[1] == 2
    assert tr_mod.locate_transcript()[1] == 2

    ste_md = (
        "\n---\nname: x\n---\n"
        "<yaml_metadata_card>\nk: v\n</yaml_metadata_card>\n"
        "<!-- multi\nline -->\n```python\nx = 1 - 2\n```\n---\n"
        "https://example.org/test\n| Col1 | Col2 |\n| --- | --- |\n"
        "| Frase breve valida. | Testo - inciso vietato |\n"
        "Questa frase supera ampiamente il limite massimo consentito di venti parole "
        "previsto dallo standard tecnico italiano attivo per la documentazione sovrana attuale.\n"
    )
    ste_r = tr_mod.verify_ste100_compliance(ste_md, max_sentence_words=20)
    assert ste_r["passed"] is False and ste_r["violations_count"] >= 2

    comp_tp = tmp_path / "forensic_tp.jsonl"
    comp_recs = [
        {"source": "USER", "type": "USER_INPUT", "content": "start"},
        {"source": "MODEL", "content": "", "tool_calls": [{"name": "ask_question", "args": {}}]},
        {"source": "MODEL", "content": "IB-20261111-ABCDEF12", "tool_calls": [{"name": "ask_question", "args": {}}]},
        {"source": "MODEL", "content": "poll", "tool_calls": [
            {"name": "manage_task", "args": {"Action": "status"}},
            {"name": "manage_task", "args": {"Action": "status"}},
            {"name": "send_message", "args": {"Message": "x" * 1900}},
            {"name": "write_file", "args": {"Path": "C:/outside/evil.py"}},
            {"name": "read_file", "args": {"Path": "missing.py"}},
        ]},
        {"source": "TOOL", "status": "ERROR", "output": "FileNotFoundError: missing.py"},
    ]
    comp_tp.write_text("\n".join(json.dumps(r) for r in comp_recs) + "\n", encoding="utf-8")
    ac_res = tr_mod.analyze_compliance(comp_tp)
    assert ac_res["passed"] is False and ac_res["oversized_swarm_messages"] == 1

    lk_dir = tmp_path / "lk_dir"
    lk_dir.mkdir()
    (lk_dir / "a.py").write_text("A = 1\n", encoding="utf-8")
    (lk_dir / "b.py").write_text("B = 2\n", encoding="utf-8")
    lk_file = tmp_path / "oracle_lock.json"
    assert tr_mod.handle_oracle_lock("EMPTY", tmp_path / "no_lk", lk_file)[1] == 1
    assert tr_mod.handle_oracle_lock("verify", lk_dir, lk_file)[1] == 1
    assert tr_mod.handle_oracle_lock("create", lk_dir, lk_file)[1] == 0
    (lk_dir / "a.py").write_bytes(b"A = 1\r\n")
    assert tr_mod.handle_oracle_lock("verify", lk_dir, lk_file)[1] == 0
    (lk_dir / "b.py").unlink()
    (lk_dir / "a.py").write_text("A = 99\n", encoding="utf-8")
    (lk_dir / "c.py").write_text("C = 3\n", encoding="utf-8")
    assert tr_mod.handle_oracle_lock("verify", lk_dir, lk_file)[1] == 1


def _gap_handoff_state_and_cli_checks(
    tmp_path: Path, monkeypatch: Any, big_tp: Path
) -> float:
    """Verifica handoff FSM, memo SHA-256, active context e CLI session handoff."""
    settled_ts = time.time() - 10.0
    t12_min = tmp_path / "t12_min"
    t12_min.mkdir(exist_ok=True)
    assert "Template 11" in hand_mod.compile_template_11_prompt(str(t12_min), "MS-1", '{"a": 1}')
    assert "Template 12" in hand_mod.compile_template_12_state_handoff(str(t12_min), "MS-2", '{"b": 2}')
    assert len(hand_mod._compute_workspace_state_sha256(tmp_path / "no_ho_ws")) == 64

    ho_ws = tmp_path / "ho_ws"
    for sub_h in ("pkg", "nk_tracking/handoff", "nk_tracking/anchor", ".staging"):
        (ho_ws / sub_h).mkdir(parents=True)
    for idx_h in range(2):
        hf = ho_ws / "pkg" / f"f_{idx_h}.txt"
        hf.write_text(f"val_{idx_h}", encoding="utf-8")
        os.utime(hf, (settled_ts, settled_ts))
    (ho_ws / "nk_tracking" / "handoff" / "skip.txt").write_text("s", encoding="utf-8")
    (ho_ws / "nk_tracking" / "active_context.md").write_text("ctx", encoding="utf-8")
    (ho_ws / "fast_bootstrap_cache.json").write_text("{}", encoding="utf-8")
    (ho_ws / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    assert hand_mod._has_dirty_staging_inprocess(ho_ws) is False
    (ho_ws / ".staging" / "dirty.txt").write_text("d", encoding="utf-8")
    assert hand_mod._has_dirty_staging_inprocess(ho_ws) is True
    assert hand_mod._check_git_dirty_fast(ho_ws, "git")[0] is True

    hand_mod._FILE_HASH_MEMO.clear()
    h_sha1 = hand_mod._compute_workspace_state_sha256(ho_ws)
    h_sha2 = hand_mod._compute_workspace_state_sha256(ho_ws)
    hand_mod._FILE_HASH_MEMO.clear()
    h_sha3 = hand_mod._compute_workspace_state_sha256(ho_ws)
    assert h_sha1 == h_sha2 == h_sha3

    assert hand_mod.resume_from_anchor(root=ho_ws)["gate_status"] == "MISSING"
    anc_f = ho_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    for bad_anc in ("{bad\n", "[]\n", '{"turn": true, "state_sha256": "x"}\n', '{"turn": 9, "state_sha256": "x"}\n'):
        anc_f.write_text(bad_anc, encoding="utf-8")
        assert hand_mod.resume_from_anchor(root=ho_ws)["passed"] is False
    for bad_t in (True, "bad", 0, 6):
        with pytest.raises(ValueError):
            hand_mod.record_fsm_checkpoint(bad_t, "PASS", root=ho_ws)  # type: ignore[arg-type]
    cp_ok = hand_mod.record_fsm_checkpoint(2, "PASS", milestone_id="MS-HO", root=ho_ws)
    assert cp_ok["passed"] is True and hand_mod.resume_from_anchor(root=ho_ws)["status"] == "RESUMED"
    with pytest.raises(ValueError):
        hand_mod.generate_active_context_view(root=ho_ws, output_path=tmp_path / "outside_ctx.md")
    assert hand_mod.generate_active_context_view(root=ho_ws, profile="carbon")["passed"] is True
    assert hand_mod.generate_active_context_view(root=ho_ws, profile="standard")["passed"] is True

    for ho_args in (
        ["--root", str(ho_ws), "--checkpoint-turn", "3", "--gate-status", "PASS"],
        ["--root", str(ho_ws), "--resume-from-anchor"],
        ["--root", str(ho_ws), "--generate-active-context", "--profile", "carbon"],
        ["--project-root", str(ho_ws), "--output-dir", str(tmp_path / "ho_out1"),
         "--persist-brief-id", "20261111-TEST0001", "--prompt-text", "Brief test.", "--compile-template-11"],
        ["--project-root", str(ho_ws), "--output-dir", str(tmp_path / "ho_out2"),
         "--transcript", str(big_tp), "--compile-state-handoff"],
    ):
        assert _call_main(hand_mod, ho_args, monkeypatch) == 0
    return settled_ts


def _gap_preflight_and_dast_overlay_checks(
    tmp_path: Path, monkeypatch: Any, settled_ts: float
) -> None:
    """Verifica Preflight baseline/CLI e DAST staging shadow overlay."""
    pf_ws = tmp_path / "pf_cov_ws"
    for sub_pf in ("nk_tracking/anchor", ".wal/quarantine", ".staging/nk_genome"):
        (pf_ws / sub_pf).mkdir(parents=True)
    (pf_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl").write_text(
        '{"ok": 1}\n\n{"ok": 1}\n{bad\n', encoding="utf-8"
    )
    (pf_ws / "session_anchor.jsonl").write_text('{"rogue": 1}\n', encoding="utf-8")
    (pf_ws / ".wal" / "quarantine" / "q.wal").write_text("q", encoding="utf-8")
    for wf_p in (pf_ws / ".wal" / "stale.wal", pf_ws / "root_stale.wal"):
        wf_p.write_text("stale", encoding="utf-8")
        os.utime(wf_p, (settled_ts - 120.0, settled_ts - 120.0))
    (pf_ws / ".staging" / "nk_genome" / "nk_registry_manifest.json").write_text(
        '{"summary": {"total_skills": 4}}', encoding="utf-8"
    )
    pfc_cov = pre_mod.PreflightHealthChecker(workspace_root=pf_ws)
    assert pfc_cov._check_baseline_alignment()["passed"] is False
    qb_pf = pf_ws / "nk_tracking" / "quality_baseline.json"
    for bad_qb in (
        "[]",
        "{bad",
        '{"metrics": {"skills_audited": {"value": 2}, "crv_macro_phases": {"value": 3}, "unit_tests_pass_pct": {"value": 90.0}}}',
    ):
        qb_pf.write_text(bad_qb, encoding="utf-8")
        assert pfc_cov._check_baseline_alignment()["passed"] is False
    qb_pf.write_text(
        '{"metrics": {"skills_audited": 4, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}',
        encoding="utf-8",
    )
    assert pfc_cov._check_baseline_alignment()["passed"] is True
    assert _call_main(pre_mod, ["--root", str(pf_ws), "--check-only", "--json"], monkeypatch) == 1
    rc_pf, out_pf, _ = _call_main_cap(pre_mod, ["--root", str(pf_ws), "--json"])
    pf_rep = json.loads(out_pf)
    assert rc_pf == (0 if pf_rep["status"] in ("PASS", "HEALTHY_GREEN") else 1)
    assert pf_rep["checks"]["ssot_anchor"]["passed"] is True
    assert "Sanitized session_anchor.jsonl." in pf_rep["checks"]["ssot_anchor"]["details"]

    ov_ws = tmp_path / "ov_ws"
    for sub_ov in ("custom_pkg", ".staging/data", ".staging/custom_pkg"):
        (ov_ws / sub_ov).mkdir(parents=True)
    (ov_ws / "README.md").write_text("# Doc\n", encoding="utf-8")
    (ov_ws / "custom_pkg" / "m.py").write_text("M = 1\n", encoding="utf-8")
    (ov_ws / ".staging" / "data" / "d.json").write_text("{}", encoding="utf-8")
    (ov_ws / ".staging" / "custom_pkg" / "m2.py").write_text("M2 = 2\n", encoding="utf-8")
    (ov_ws / ".staging" / ".deleted_files.json").write_text(
        '{"deleted_files": ["README.md"]}', encoding="utf-8"
    )
    ov_r = dast_mod.run_staging_shadow_verification(
        repo_root=ov_ws, run_ast_guard=False, run_pytest=False, profile="builder"
    )
    assert ov_r["passed"] is True and "README.md" in ov_r["deleted_files"]


def _gap_2pc_ratchet_and_promote_checks(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica ratchet dual-schema Win32 2PC, promote e quarantine CLI."""
    assert (
        w2pc_mod._verify_quality_baseline_ratchet(
            {"pass_rate_pct": 100.0, "total_tests": 5, "failed_tests": 0}
        )["verdict"]
        == "PASS"
    )
    assert (
        w2pc_mod._verify_quality_baseline_ratchet(
            {"pass_rate": 100.0, "golden_tests_count": 5}
        )["verdict"]
        == "PASS"
    )
    for bad_bl_d in ({}, {"metrics": {"total_golden_tests": 5}, "pass_rate": 90.0}):
        with pytest.raises(w2pc_mod.TwoPhaseCommitError):
            w2pc_mod._verify_quality_baseline_ratchet(bad_bl_d)

    bl_d1 = tmp_path / "bl_d1.json"
    bl_s1 = tmp_path / "bl_s1.json"
    bl_d1.write_text('{"pass_rate_pct": 100.0, "total_tests": 5}', encoding="utf-8")
    for bad_s in ("{}", '{"pass_rate_pct": 95.0, "total_tests": 5}'):
        bl_s1.write_text(bad_s, encoding="utf-8")
        with pytest.raises(w2pc_mod.TwoPhaseCommitError):
            w2pc_mod._verify_quality_baseline_ratchet(bl_d1, bl_s1)
    bl_s1.write_text('{"pass_rate_pct": 100.0, "total_tests": 6}', encoding="utf-8")
    assert w2pc_mod._verify_quality_baseline_ratchet(bl_d1, bl_s1)["verdict"] == "PASS"
    assert w2pc_mod._verify_quality_baseline_ratchet(bl_d1)["verdict"] == "PASS"

    pr_ws = tmp_path / "pr_2pc_ws"
    for sub_pr in (".staging", "nk_genome"):
        (pr_ws / sub_pr).mkdir(parents=True)
    (pr_ws / "nk_genome" / "PATCH_NOTES.md").write_text("## [1.0]\n- ok\n", encoding="utf-8")
    (pr_ws / "same.txt").write_text("same", encoding="utf-8")
    (pr_ws / "old_rm.txt").write_text("rm", encoding="utf-8")
    (pr_ws / ".staging" / "same.txt").write_text("same", encoding="utf-8")
    (pr_ws / ".staging" / "mod.txt").write_text("new", encoding="utf-8")
    (pr_ws / ".staging" / ".deleted_files.json").write_text('{"bad": 1}', encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=pr_ws)
    (pr_ws / ".staging" / ".deleted_files.json").write_text('["old_rm.txt"]', encoding="utf-8")
    assert _call_main(
        w2pc_mod, ["--promote-staging", "--repo-root", str(pr_ws), "--milestone", "MS-2PC"], monkeypatch
    ) == 0
    (pr_ws / ".staging" / "q_file.txt").write_text("q", encoding="utf-8")
    assert _call_main(w2pc_mod, ["--quarantine-staging", "--repo-root", str(pr_ws)], monkeypatch) == 0
    assert not (pr_ws / ".staging" / "q_file.txt").exists()
    assert _call_main(w2pc_mod, [], monkeypatch) == 0


def _gap_memory_archive_autoheal_and_cleanup_checks(
    tmp_path: Path, monkeypatch: Any, m3_dir: Path, m3_g: Any
) -> None:
    """Verifica archivio cold Tier3, shadow cache, AutoHeal CLI, Cleanup e DAST RSS."""
    cold_ep = mem_mod.MemoryEpisode(
        episode_id="cold_1", domain="01_Bug_Diagnostics", title="Cold", content="Archivio freddo"
    )
    m3_g._archive_to_tier3("01_Bug_Diagnostics", [])
    m3_g._archive_to_tier3("01_Bug_Diagnostics", [cold_ep])
    assert len(m3_g.get_tier3_episodes("01_Bug_Diagnostics")) >= 1
    t2_rec = tmp_path / "t2_rec" / "episodes.jsonl"
    t2_rec.parent.mkdir()
    t2_rec.write_text("{bad\n", encoding="utf-8")
    t2_rec.with_name("episodes.jsonl.bak_1").write_text(
        cold_ep.model_dump_json() + "\n", encoding="utf-8"
    )
    assert len(m3_g._load_tier2_raw(t2_rec)) == 1
    (m3_dir / "01_Bug_Diagnostics" / "episodes.jsonl").write_text(
        cold_ep.model_dump_json() + "\n", encoding="utf-8"
    )
    m3_g._update_shadow_cache("01_Bug_Diagnostics", [cold_ep])
    assert m3_g._read_shadow_cache("01_Bug_Diagnostics") is not None
    for mem_args in (
        ["--base-dir", str(m3_dir), "--append", "--domain", "OPS", "--title", "T1", "--content", "C1", "--tags", "a,b"],
        ["--base-dir", str(m3_dir), "--tier1-sync"],
        ["--base-dir", str(m3_dir), "--consolidate", "--threshold", "0.9"],
        ["--base-dir", str(m3_dir), "--recall", "--domain", "OPS", "--query", "T1"],
        ["--base-dir", str(m3_dir)],
        ["--base-dir", str(m3_dir), "--json"],
    ):
        assert _call_main(mem_mod, mem_args, monkeypatch) == 0

    for err_s, exp_c in (
        ("TimeoutExpired", "TIMEOUT_ERROR"),
        ("SyntaxError", "SYNTAX_ERROR"),
        ("ModuleNotFoundError", "IMPORT_ERROR"),
        ("AssertionError", "ASSERTION_ERROR"),
        ("Boom", "RUNTIME_ERROR"),
    ):
        assert heal_mod.classify_failure(err_s, exit_code=1) == exp_c
    assert heal_mod.classify_failure("ok", exit_code=0) == "NONE"
    assert "-m pytest" in str(heal_mod.normalize_test_command("pytest"))
    assert "-q" in str(heal_mod.normalize_test_command("pytest -q"))
    assert heal_mod.normalize_test_command("python -m pytest") == "python -m pytest"
    assert heal_mod.normalize_test_command(["pytest", "-q"])[1:4] == ["-m", "pytest", "-q"]
    assert heal_mod.normalize_test_command(["python", "-m", "pytest"]) == ["python", "-m", "pytest"]
    sast_t = tmp_path / "sast_h.py"
    sast_t.write_text("import subprocess\nsubprocess.Popen('x', shell=True)\n", encoding="utf-8")
    d_k, q_k = heal_mod._compute_rsi_metrics(1, 1, sast_t, "X = 1\n")
    assert d_k > 0 and q_k >= 0.0

    assert clean_mod.parse_ports_arg(None) == clean_mod.TARGET_PORTS
    assert 8081 in clean_mod.parse_ports_arg("8000,bad,70000,8000,8081")
    assert clean_mod.parse_ports_arg([8000, 8000, 99999]) == [8000]
    assert clean_mod.parse_ports_arg("bad") == clean_mod.TARGET_PORTS
    assert clean_mod._is_subpath_str("", "C:\\a") is False
    assert clean_mod._is_subpath_str("C:\\a\\b", "C:\\a") is True
    assert clean_mod.is_target_workspace_process(0) is False
    assert clean_mod.is_target_workspace_process(os.getpid()) is False
    assert clean_mod.is_target_workspace_process(99999999) is False
    assert clean_mod.kill_pid_tree(-1) is False and clean_mod.kill_pid_tree(os.getpid()) is False

    rss_st = dast_mod._RSSMonitorState()
    rss_st.record_sample(2048)
    rss_st.record_sample(512)
    assert rss_st.get_peak() == 2048
    assert dast_mod._assign_pid_to_job(0, 0) is False
    assert dast_mod._resume_process_primary_thread(0) is False


def _gap_repomap_hud_scaffold_swarm_sbfl_checks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica RepoMap tight cap, Snapshot rollback, HUD, Scaffolder, Swarm e SBFL bridge."""
    tight_ws = tmp_path / "tight_map"
    for idx_tm in range(8):
        tm_dir = tight_ws / f"pkg_{idx_tm % 4}"
        tm_dir.mkdir(parents=True, exist_ok=True)
        (tm_dir / f"mod_{idx_tm}.py").write_text(
            "\n".join(
                f"class Cls{idx_tm}_{c}:\n    def m{c}(self, a: int, b: str) -> int:\n        return a\n"
                for c in range(3)
            ),
            encoding="utf-8",
        )
    tm_res = map_mod.RepoMapGenerator.generate(
        tight_ws, map_mod.RepoMapConfig(max_tokens=128, cache_enabled=False)
    )
    assert tm_res.token_count <= 128

    snap_f = tmp_path / "snap_t.txt"
    snap_mod._atomic_write_bytes(snap_f, b"v1")
    snap_mod._atomic_write_text(snap_f, "v2")
    assert _call_main(snap_mod, ["--create", str(snap_f)], monkeypatch) == 0
    sid_s = snap_mod.HealingSnapshotManager().create_snapshot([snap_f])
    snap_f.write_text("mut", encoding="utf-8")
    assert _call_main(snap_mod, ["--rollback", sid_s], monkeypatch) == 0
    assert snap_f.read_text(encoding="utf-8") == "v2"
    assert _call_main(snap_mod, ["--cleanup"], monkeypatch) == 0
    assert _call_main(snap_mod, [], monkeypatch) == 0

    _NoEnc = type("_NoEnc", (), {"encoding": None})()
    _AsciiEnc = type("_AsciiEnc", (), {"encoding": "ascii"})()
    assert hud_mod.is_unicode_stream_supported(_AsciiEnc) is False
    assert hud_mod.is_unicode_stream_supported(_NoEnc) is True
    hud_r = hud_mod.MicroHUDRenderer(ascii_mode=False)
    hud_r.set_progress(55).set_gate("G1", "PASSED", "ok").set_gate("G_NEW", "BLOCKED", "blk")
    hud_r.set_mutex("LOCKED").set_agent_context("NK-Builder-Agent", "DOM-03").set_rsi_metrics(1.5, 92.0)
    hud_r.state.tier1_tokens_used = 120
    hud_r.state.elapsed_seconds = 1.25
    assert hud_r.to_ipc_state().progress_pct == 55.0
    assert "RSI:" in hud_r.render(include_extras=True, ascii_mode=False)
    assert "RSI:" in hud_r.render(include_extras=True, ascii_mode=True)
    assert _call_main(hud_mod, ["--percent", "80", "--ascii"], monkeypatch) == 0
    assert _call_main(hud_mod, ["--percent", "80", "--json"], monkeypatch) == 0

    for bad_sc_n in ("", "../bad", "a:b", "bad. "):
        with pytest.raises(ValueError):
            scaf_mod.ExternalProjectScaffolder(bad_sc_n, tmp_path / "ext_p")
    with pytest.raises(ValueError):
        scaf_mod.ExternalProjectScaffolder("ValidP", Path("C:/temp/ads:stream"))
    ext_t = tmp_path / "ext_scaf_proj"
    (ext_t / "genome").mkdir(parents=True)
    (ext_t / "genome" / "concept_map.md").write_text("# Legacy Concept\n", encoding="utf-8")
    scaf_mod.ExternalProjectScaffolder("ExtApp", ext_t).scaffold(force=True)
    assert (ext_t / "nk_genome" / "concept_map.md").exists()

    pf_sw = tmp_path / "sw_msg.txt"
    pf_sw.write_text("x" * 2100, encoding="utf-8")
    assert _call_main(
        swarm_mod, ["--sender", "w1", "--recipient", "p1", "--payload-file", str(pf_sw)], monkeypatch
    ) == 0
    assert _call_main(swarm_mod, ["--payload", "short"], monkeypatch) == 0

    (tmp_path / "pkg_br").mkdir()
    (tmp_path / "pkg_br" / "bug.py").write_text("def fn():\n    return 1 / 0\n", encoding="utf-8")
    br_inst = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    sum_f = br_inst.parse_pytest_output(
        "pkg_br/bug.py:2: in fn\n    return 1 / 0\nE   ZeroDivisionError: div0\n1 failed, 2 passed in 0.10s\n",
        "", 1, 0.1,
    )
    loc_a = br_inst.extract_failure_location(sum_f, passed_line_counts={("bug.py", 2): 1})
    loc_b = br_inst.extract_failure_location(sum_f, target_file_hint="missing_h.py", passed_line_counts=None)
    assert loc_a.line_number == 2 and loc_b.file_path == "missing_h.py" and loc_b.line_number == 1 and len(loc_a.render_payload_json()) < 320


def _gap_bootstrap_transcript_and_baseline_checks(
    tmp_path: Path, b_ws: Path, sb_fp: Any, tp_fp: Path
) -> None:
    """Verifica transcript discovery e schemi quality_baseline di bootstrap."""
    sb_disc = boot_mod.NKSessionBootstrap(workspace_root=b_ws, conversation_id="")
    assert sb_disc._find_recent_transcript(tmp_path / "no_brain_x") is None
    bd_s = tmp_path / "bd_scan"
    c_sub = bd_s / "c1" / ".system_generated" / "logs"
    c_sub.mkdir(parents=True)
    (c_sub / "transcript.jsonl").write_text(
        '{"source": "SYSTEM", "content": "<Agent System Instructions> <subagent_reminder>"}\n',
        encoding="utf-8",
    )
    c_main = bd_s / "c2" / ".system_generated" / "logs"
    c_main.mkdir(parents=True)
    (c_main / "transcript.jsonl").write_text('{"source": "USER", "content": "hi"}\n', encoding="utf-8")
    assert sb_disc._find_recent_transcript(bd_s, max_age_seconds=120.0) == c_main / "transcript.jsonl"
    old_ts = time.time() - 5.0
    os.utime(c_sub / "transcript.jsonl", (old_ts, old_ts))
    os.utime(c_main / "transcript.jsonl", (old_ts, old_ts))
    (bd_s / "c3_unflushed").mkdir(parents=True)
    assert sb_disc._find_recent_transcript(bd_s, max_age_seconds=120.0) is None
    assert (
        sb_fp._verify_context_sentry(
            use_fast_cache=True,
            cached={"conversation_id": "conv_fp", "last_transcript_path": str(tp_fp)},
        )["passed"]
        is True
    )
    qb_b = b_ws / "nk_tracking" / "quality_baseline.json"
    qb_b.parent.mkdir(parents=True, exist_ok=True)
    for qb_raw, exp_ok in (
        ('{"pass_rate_pct": 100.0, "total_tests": 5}', True),
        ('{"pass_rate": 95.0, "golden_tests_count": 4}', False),
        ("{bad", False),
    ):
        qb_b.write_text(qb_raw, encoding="utf-8")
        assert sb_fp._verify_baseline()["passed"] is exp_ok


def _gap_compliance_rsi_l3_baseline_checks(
    tmp_path: Path, monkeypatch: Any, rsi_eng: Any
) -> None:
    """Verifica compliance telemetry, RSI verify_ecosystem, Oracle L3 CLI e QBM."""

    cc_ws = tmp_path / "cc_ws_tele"
    (cc_ws / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (cc_ws / "logs").mkdir(parents=True, exist_ok=True)
    cc_tp = cc_ws / "logs" / "tp.jsonl"
    cc_tp.write_text('{"source": "USER", "type": "USER_INPUT", "content": "go"}\n', encoding="utf-8")
    (cc_ws / "nk_tracking" / "rsi_telemetry.jsonl").write_text(
        "{bad\n[]\n"
        + json.dumps({"session_id": "other", "delta_k": 5, "fitness_q": 80.0})
        + "\n"
        + json.dumps({"delta_k": 0, "fitness_q": 100.0, "verdict": "CONVERGED_OPTIMAL"})
        + "\n",
        encoding="utf-8",
    )
    chk_g = comp_mod.NKComplianceChecker(workspace_root=cc_ws)
    assert chk_g.audit_transcript(cc_tp)["total_steps"] >= 1
    (cc_ws / "logs" / "rsi_telemetry.jsonl").write_text(
        "{bad\n" + json.dumps({"delta_k": 0, "fitness_q": 100.0, "verdict": "CONVERGED_OPTIMAL"}) + "\n",
        encoding="utf-8",
    )
    assert chk_g.audit_transcript(cc_tp)["total_steps"] >= 1

    eco_r = rsi_eng.verify_ecosystem(
        False, test_report={"tests_passed": 1, "tests_failed": 0, "tests_total": 1}
    )
    assert eco_r["passed"] is True and "violations" in eco_r
    eco_fail = rsi_eng.verify_ecosystem(
        False, test_report={"tests_passed": 0, "tests_failed": 1, "tests_total": 1}
    )
    assert eco_fail["passed"] is False and eco_fail["delta_k"] > 0

    ev_l3 = l3_mod.DOMOracleEvaluator()
    rep_d1 = ev_l3.evaluate_deltas(
        "<div><p>a</p><span>b</span><b>c</b></div>", "<div><h1>x</h1><span>b</span></div>"
    )
    rep_d2 = ev_l3.evaluate_deltas(
        "<div><span>b</span></div>", "<div><h1>x</h1><i>y</i><span>b</span><u>z</u></div>"
    )
    assert rep_d1.verdict == "FAIL" and rep_d2.verdict == "FAIL"
    assert _call_main(l3_mod, ["--expected", "<div>a</div>"], monkeypatch) == 2
    assert _call_main(l3_mod, ["--actual", "<div>a</div>"], monkeypatch) == 2
    assert _call_main(
        l3_mod, ["--expected-file", str(tmp_path / "no_l3.html"), "--actual", "<div/>"], monkeypatch
    ) == 2

    assert base_mod._resolve_workspace_root_from_baseline(
        str(tmp_path / "nk_tracking" / "quality_baseline.json")
    ) == tmp_path.resolve()
    assert base_mod._resolve_workspace_root_from_baseline(
        str(tmp_path / ".staging" / "nk_tracking" / "quality_baseline.json")
    ) == tmp_path.resolve()
    exp_mod_root = Path(base_mod.__file__).resolve().parent.parent
    if exp_mod_root.name == ".staging":
        exp_mod_root = exp_mod_root.parent
    elif exp_mod_root.name == "scripts":
        exp_mod_root = exp_mod_root.parent
    assert (
        base_mod._resolve_workspace_root_from_baseline(str(tmp_path / "other.json"))
        == exp_mod_root
    )
    assert base_mod.measure_live_pytest_metrics(tmp_path / "empty_qb_ws")["unit_tests_total"] == 0
    assert _call_main(sent_mod, ["--conversation-id", "nonexistent_conv_xyz", "--verbose"], monkeypatch) == 0


def _gap_heartbeat_fast_clock_check(monkeypatch: Any) -> None:
    """Verifica async_heartbeat_signaler CLI --test con clock deterministico."""
    _hb_real_sleep = time.sleep
    _hb_clk = [time.time()]
    _hb_bg_ticks = [0]
    _hb_main_tid = threading.get_ident()

    def _fast_hb_sleep(sec: float) -> None:
        if threading.get_ident() != _hb_main_tid:
            _hb_bg_ticks[0] += 1
            _hb_clk[0] += float(sec)
            _hb_real_sleep(0.002)
            return
        target_ticks = _hb_bg_ticks[0] + (3 if float(sec) >= 1.0 else 1)
        deadline = time.monotonic() + 1.5
        while _hb_bg_ticks[0] < target_ticks and time.monotonic() < deadline:
            _hb_real_sleep(0.002)

    _fast_hb_time = type(
        "_FastHbTime",
        (),
        {
            "time": staticmethod(lambda: _hb_clk[0]),
            "sleep": staticmethod(_fast_hb_sleep),
            "strftime": staticmethod(time.strftime),
            "gmtime": staticmethod(time.gmtime),
        },
    )()
    with monkeypatch.context() as mp_hb:
        mp_hb.setattr(hb_mod, "time", _fast_hb_time)
        assert _call_main(hb_mod, ["--test"], monkeypatch) == 0


def _run_gap_closure_phase2(
    tmp_path: Path,
    monkeypatch: Any,
    m3_dir: Path,
    m3_g: Any,
    poly_ws: Path,
    emp_tp: Path,
    b_ws: Path,
    sb_fp: Any,
    tp_fp: Path,
    rsi_ws: Path,
    rsi_eng: Any,
) -> None:
    """Coordina i micro-helper della Fase 2 di gap closure in blocchi modulari <= 80 LOC."""
    del rsi_ws
    br_dir = _gap_transcript_and_backup_checks(tmp_path)
    _gap_router_handoff_and_intent_checks()
    _gap_registry_and_repomap_cli_checks(tmp_path, monkeypatch, poly_ws)
    big_tp = _gap_router_cli_and_bootstrap_binary_checks(tmp_path, monkeypatch, emp_tp, b_ws)
    _gap_memory_cold_and_transcript_loc_checks(tmp_path, m3_dir, m3_g, big_tp, br_dir)
    settled_ts = _gap_handoff_state_and_cli_checks(tmp_path, monkeypatch, big_tp)
    _gap_preflight_and_dast_overlay_checks(tmp_path, monkeypatch, settled_ts)
    _gap_2pc_ratchet_and_promote_checks(tmp_path, monkeypatch)
    _gap_memory_archive_autoheal_and_cleanup_checks(tmp_path, monkeypatch, m3_dir, m3_g)
    _gap_repomap_hud_scaffold_swarm_sbfl_checks(tmp_path, monkeypatch)
    _gap_bootstrap_transcript_and_baseline_checks(tmp_path, b_ws, sb_fp, tp_fp)
    _gap_compliance_rsi_l3_baseline_checks(tmp_path, monkeypatch, rsi_eng)
    _gap_heartbeat_fast_clock_check(monkeypatch)

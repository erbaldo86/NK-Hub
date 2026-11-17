# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Matrice Gap Closure (split 4/4).
Modulo: tests/test_sovereign_carbon_branch_gap_closure.py.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

import _carbon_gap_closure_helpers as _gch
from conftest import (
    call_script_main as _call_main,
    load_script_by_relpath as _load_mod,
)

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
guard_mod = _load_mod("ast_guard_validator", "scripts/ast_guard_validator.py")
dast_mod = _load_mod("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
clean_mod = _load_mod("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
heal_mod = _load_mod("auto_heal_pipeline", "scripts/auto_heal_pipeline.py")
router_mod = _load_mod("vibe_sprint_router", "scripts/vibe_sprint_router.py")
rsi_mod = _load_mod("rsi_convergence_engine", "scripts/rsi_convergence_engine.py")
idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")
mem_mod = _load_mod("memory_3tier_engine", "scripts/memory_3tier_engine.py")
map_mod = _load_mod("ast_repo_mapper", "scripts/ast_repo_mapper.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
hand_mod = _load_mod("nk_session_handoff", "scripts/nk_session_handoff.py")
pre_mod = _load_mod("preflight_health_check", "scripts/preflight_health_check.py")
comp_mod = _load_mod("nk_compliance_checker", "scripts/nk_compliance_checker.py")
base_mod = _load_mod("quality_baseline_manager", "scripts/quality_baseline_manager.py")


@pytest.mark.fast
def test_carbon_inprocess_exact_branch_gap_closure(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Chiude i rami residui su Win32 2PC long-path, validazione percorsi e pre-image rollback."""
    del isolated_nk_env
    assert str(w2pc_mod._win_long_path("\\\\?\\C:\\abc")).startswith("\\\\?\\")
    assert str(w2pc_mod._win_long_path("C:\\" + ("a" * 245))).startswith("\\\\?\\")
    with monkeypatch.context() as mp_smb:
        def _raise_smb(*_args: Any, **_kwargs: Any) -> Path:
            raise OSError("smb_disabled_in_test")

        mp_smb.setattr(Path, "resolve", _raise_smb)
        assert "UNC" in str(w2pc_mod._win_long_path("\\\\srv\\share\\" + ("b" * 245)))
    with pytest.raises(OSError):
        w2pc_mod._replace_with_retry(
            tmp_path / "no_s", tmp_path / "no_d", retries=2, delay_sec=0.001
        )
    for bad_rel in ("", "a:b", "../x", "dir./x", "."):
        with pytest.raises(w2pc_mod.TwoPhaseCommitError):
            w2pc_mod._validate_win32_canonical_rel_path(bad_rel)

    bj_root = tmp_path / "bj_repo"
    bj_root.mkdir()
    bj_t = bj_root / "t.txt"
    bj_t.write_text("v1", encoding="utf-8")
    bj_n = bj_root / "new.txt"
    _, j_root, _ = w2pc_mod.BatchJournalV2.begin_batch(
        bj_root, [("t.txt", bj_t), ("t.txt", bj_t), ("new.txt", bj_n)]
    )
    assert w2pc_mod.BatchJournalV2.rollback_from_manifest({"entries": "bad"}) == []
    assert w2pc_mod.BatchJournalV2.rollback_from_manifest({"entries": ["bad", {}]}) == []
    (bj_root / ".staging_t.txt.1.tmp").write_text("tmp", encoding="utf-8")
    bj_n.write_text("created", encoding="utf-8")
    rec_list, _ = w2pc_mod.BatchJournalV2.recover_crashed_batches(bj_root)
    assert len(rec_list) == 1 and not bj_n.exists()

    j_root.mkdir(parents=True, exist_ok=True)
    (j_root / "orphan_b").mkdir()
    (j_root / "active_batch.json").write_text("{corrupt", encoding="utf-8")
    rec_err, _ = w2pc_mod.BatchJournalV2.recover_crashed_batches(bj_root)
    assert rec_err[0]["action"] == "ERROR"

    _, j_root2, b_dir2 = w2pc_mod.BatchJournalV2.begin_batch(bj_root, [("t.txt", bj_t)])
    man2 = json.loads((j_root2 / "active_batch.json").read_text(encoding="utf-8"))
    pre_p = Path(man2["entries"][0]["preimage_file"])
    pre_p.write_bytes(b"tampered")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.BatchJournalV2.rollback_from_manifest(man2, b_dir2)
    pre_p.unlink()
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.BatchJournalV2.rollback_from_manifest(man2, None)
    w2pc_mod.BatchJournalV2.cleanup_journal(j_root2, b_dir2)

    err_p_root = tmp_path / "err_p_repo"
    (err_p_root / ".staging").mkdir(parents=True)
    (err_p_root / ".staging" / "bad.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=err_p_root)


@pytest.mark.integration
def test_carbon_gap_win32_mutex_thread_contention() -> None:
    """Verifica contesa thread-affinity e timeout sul Win32NamedMutex."""
    mx_name = f"CustomLocalMutex_NK6_{os.getpid()}"
    mx_loc = w2pc_mod.Win32NamedMutex(mx_name, timeout_ms=50, is_path=False)
    mx_loc.acquire()
    thread_errs: List[str] = []

    def _worker_mutex_conflicts() -> None:
        try:
            mx_loc.acquire()
        except w2pc_mod.Win32LockError:
            thread_errs.append("acq_affinity")
        try:
            mx_loc.release()
        except w2pc_mod.Win32LockError:
            thread_errs.append("rel_affinity")
        try:
            w2pc_mod.Win32NamedMutex(mx_name, timeout_ms=5, is_path=False).acquire()
        except (w2pc_mod.Win32LockError, w2pc_mod.Win32LockTimeoutError):
            thread_errs.append("timeout")

    try:
        t_mx = threading.Thread(target=_worker_mutex_conflicts)
        t_mx.start()
        t_mx.join(timeout=5.0)
    finally:
        mx_loc.release()
    assert thread_errs == ["acq_affinity", "rel_affinity", "timeout"]


@pytest.mark.fast
def test_carbon_gap_dast_helpers_and_shadow_sandbox(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica DAST Job Object, RSS Toolhelp32, ShadowSandbox e CLI overlay mancante."""
    assert dast_mod._assign_pid_to_job(0, 0) is False
    assert dast_mod._resume_process_primary_thread(0) is False
    assert dast_mod._assign_to_kill_on_close_job(0) is None
    assert dast_mod._assign_to_kill_on_close_job(99999999) is None
    for bad_sb in ("", "C:/abs", "../esc", "."):
        with pytest.raises(ValueError):
            dast_mod._resolve_confined_sandbox_path(tmp_path, bad_sb)
    env_s = dast_mod._build_sanitized_sandbox_env(
        {"NK_ALLOW_GOVERNANCE_OVERRIDE": "1", "SAFE_VAR": "1"}
    )
    assert "NK_ALLOW_GOVERNANCE_OVERRIDE" not in env_s and env_s["SAFE_VAR"] == "1"
    assert dast_mod.resolve_dast_report_path(
        tmp_path, explicit_output=str(tmp_path) + "/"
    ).name.startswith("dast_report_")
    assert dast_mod._terminate_process_tree_fallback(0) == 0
    assert dast_mod._terminate_process_tree_fallback(99999999) == 0
    rss_st = dast_mod._RSSMonitorState()
    r1 = dast_mod._get_process_memory_rss(os.getpid(), p_process=None, rss_state=rss_st)
    r2 = dast_mod._get_process_memory_rss(os.getpid(), p_process=None, rss_state=rss_st)
    assert (r1 > 0 if sys.platform == "win32" else r1 >= 0) and r2 == r1

    sb_u = dast_mod.ShadowSandbox()
    sb_u.write_file("bin/raw.bin", b"123")
    src_cp = tmp_path / "cp_me.py"
    src_cp.write_text("Z = 1\n", encoding="utf-8")
    sb_u.copy_file(src_cp, "sub_d/")
    sb_u.copy_file(src_cp, "sub_d")
    with pytest.raises(FileNotFoundError):
        sb_u.copy_file(tmp_path / "missing_cp.py")
    sb_u.cleanup()
    sb_u.cleanup()

    async def _sb_async() -> None:
        async with dast_mod.ShadowSandbox() as asb:
            assert asb.sandbox_dir.is_dir()

    asyncio.run(_sb_async())
    assert _call_main(
        dast_mod,
        ["--overlay-staging", str(tmp_path / "no_ov"), "--report-to-tracking"],
        monkeypatch,
    ) == 1


@pytest.mark.fast
def test_carbon_gap_memory_3tier_and_repo_mapper(
    tmp_path: Path
) -> None:
    """Verifica Memory 3-Tier recall hybrid/consolidate e AST Repo Mapper polyglot."""
    m3_dir = tmp_path / "m3_gap"
    m3_g = mem_mod.ThreeTierMemoryEngine(base_dir=m3_dir, sliding_window_max=3)
    for idx in range(4):
        m3_g.append_episode(
            mem_mod.MemoryEpisode(
                episode_id=f"ep_g_{idx}",
                domain="01_Bug_Diagnostics",
                title="Win32 Mutex Contention Analysis",
                content=f" Analisi dettagliata blocco mutex su file condiviso {idx % 2}",
                tags=["win32", "mutex", "diagnostics"],
                metadata={
                    "source_url": "https://learn.microsoft.com/windows/win32",
                    "evidence_quote": "WaitForSingleObject returns WAIT_OBJECT_0",
                },
            )
        )
    assert m3_g.recall_hybrid("01_Bug_Diagnostics", "", top_k=3) == []
    assert m3_g.recall_hybrid("01_Bug_Diagnostics", "!", top_k=3) == []
    hyb_g = m3_g.recall_hybrid(
        "01_Bug_Diagnostics",
        "win32 mutex contention alpha beta gamma delta epsilon",
        top_k=3,
        adaptive=True,
    )
    assert len(hyb_g) >= 1
    m3_g.sync_tier1_capsule(profile="carbon")
    m3_g.sync_tier1_capsule(profile="standard")
    assert mem_mod.ThreeTierMemoryEngine._char_trigram_cosine("", "a") == 0.0
    assert mem_mod.ThreeTierMemoryEngine._char_trigram_cosine("abcd", "abcd") == 1.0
    cons_res = mem_mod.consolidate_similar_episodes(
        domain="01_Bug_Diagnostics", threshold=0.5, base_dir=m3_dir
    )
    assert cons_res["merged_count"] >= 1
    t2_f = m3_dir / "01_Bug_Diagnostics" / "episodes.jsonl"
    t2_f.write_text("\n", encoding="utf-8")
    assert len(m3_g._load_tier2_raw(t2_f)) >= 1
    for mf in m3_g.cache_dir.glob("*_meta.json"):
        mf.write_text('{"size": -1, "mtime_ns": 0}', encoding="utf-8")
    assert m3_g._read_shadow_cache("01_Bug_Diagnostics") is None

    gsa = map_mod.GraduatedSkillAdapter
    assert gsa.get_token_budget("NK-Scribe-Memory") == 0
    assert gsa.get_token_budget("NK-Ideator", "carbon_mode_c") == 512
    assert gsa.get_token_budget("NK-Ideator", "carbon_mode_b") == 1500
    assert gsa.get_token_budget("NK-Ideator", "carbon_mode_a") == 4000
    assert gsa.get_token_budget("NK-Ideator", "mode_c") == 256
    assert gsa.get_token_budget("NK-Ideator", "mode_b") == 512
    assert gsa.get_token_budget("NK-Ideator", "mode_a") == 1024

    poly_ws = _build_polyglot_repo_ws(tmp_path / "poly_map")
    snap_res = map_mod.export_markdown_snapshot(
        poly_ws, tmp_path / "out_map" / "repo_map.md", max_tokens=128
    )
    assert snap_res.token_count > 0
    assert map_mod.query_symbol_subgraph("", root_dir=poly_ws)["found"] is False
    sg1 = map_mod.query_symbol_subgraph("target_fn", root_dir=poly_ws)
    sg2 = map_mod.query_symbol_subgraph("target_fn", root_dir=poly_ws)
    assert sg1["found"] is True and sg2["found"] is True


def _build_polyglot_repo_ws(poly_ws: Path) -> Path:
    """Costruisce un repository polyglot minimo per testare ASTRepoMapper."""
    for p_sub in ("pkg_a", "pkg_b", "pkg_c", ".staging"):
        (poly_ws / p_sub).mkdir(parents=True)
    (poly_ws / "pkg_a" / "empty_cls.py").write_text("class EmptyC:\n    pass\n", encoding="utf-8")
    (poly_ws / "pkg_a" / "const_cls.py").write_text("class ConstC:\n    K_VAL = 1\n", encoding="utf-8")
    (poly_ws / "pkg_a" / "only_const.py").write_text("GLOBAL_CONST = 99\n", encoding="utf-8")
    (poly_ws / "pkg_a" / "core_target.py").write_text(
        "def helper_fn() -> int:\n    return 1\n\ndef target_fn() -> int:\n    return helper_fn()\n",
        encoding="utf-8",
    )
    for idx in range(4):
        sub_n = "pkg_b" if idx < 2 else "pkg_c"
        (poly_ws / sub_n / f"mod_{idx}.py").write_text(
            f"class Svc{idx}:\n    def run(self) -> int:\n        return {idx}\n",
            encoding="utf-8",
        )
    (poly_ws / ".staging" / "ui.ts").write_text(
        "export function tsCaller(): number { return target_fn(); }\n",
        encoding="utf-8",
    )
    return poly_ws


@pytest.mark.fast
def test_carbon_gap_router_rsi_and_snapshot_manager(tmp_path: Path) -> None:
    """Verifica Router STT/exempt/transcript, RSI A/B benchmark e HealingSnapshotManager."""
    vr_g = router_mod.VibeSprintRouter(workspace_root=tmp_path)
    assert vr_g.normalize_voice_stt_input("")["cleaned_prompt"] == ""
    stt_r = vr_g.normalize_voice_stt_input(
        "Usa `codice` !diretto !raw salta gate MioSimbolo scusa anzi crea file_nuovo.py praticamente ora"
    )
    assert stt_r["bypass_requested"] is True and len(stt_r["voice_corrections_applied"]) >= 1
    for ex_p in ("", "<env_capsule>x</env_capsule>", "!diretto vai", "procedi pure"):
        assert vr_g.is_gate_exempt(ex_p) is True
    assert vr_g.is_gate_exempt("rm -rf /tmp/x") is False and vr_g.is_gate_exempt("z" * 300) is False
    assert (
        router_mod._extract_user_text_from_record(
            {"source": "USER", "type": "USER_INPUT", "content": ["<CONTEXT_SUMMARY>x"]}
        )
        is None
    )
    tp_u = tmp_path / "u_in.jsonl"
    tp_u.write_text(
        json.dumps({"source": "USER", "type": "USER_INPUT", "content": "prompt da transcript"}) + "\n",
        encoding="utf-8",
    )
    assert router_mod._read_latest_user_input_from_transcript(str(tp_u)) == "prompt da transcript"

    assert rsi_mod._extract_sast_report_count(None) == 0
    sr_f = tmp_path / "sast_r.json"
    sr_f.write_text('{"metrics": {"sast_violations_count": 3}}', encoding="utf-8")
    assert rsi_mod._extract_sast_report_count(sr_f) == 3
    sr_f.write_text('{"violations": [1, 2]}', encoding="utf-8")
    assert rsi_mod._extract_sast_report_count(sr_f) == 2
    sr_f.write_text("{bad", encoding="utf-8")
    assert rsi_mod._extract_sast_report_count(sr_f) == 0
    ab_miss = rsi_mod.run_ab_benchmark(workspace_root=tmp_path / "no_ab", repetitions=1)
    assert ab_miss["passed"] is False and "tasks_total" in ab_miss

    ab_ws = _build_ab_benchmark_ws(tmp_path / "ab_ws")
    ab_ok = rsi_mod.run_ab_benchmark(workspace_root=ab_ws, repetitions=1)
    assert ab_ok["passed"] is True and ab_ok["tasks_total"] == 12

    hsm = heal_mod.HealingSnapshotManager(base_temp_dir=tmp_path / "h_snaps")
    tf_h = tmp_path / "h_target.py"
    tf_h.write_text("A = 1\n", encoding="utf-8")
    sid_h = hsm.create_snapshot([tf_h, tmp_path / "h_new.py"])
    hsm2 = heal_mod.HealingSnapshotManager(base_temp_dir=tmp_path / "h_snaps")
    assert sid_h in hsm2.active_snapshots


def _build_ab_benchmark_ws(ab_ws: Path) -> Path:
    """Crea una benchmark suite RSI minima con 12 task validi."""
    (ab_ws / "nk_tracking" / "benchmark_suite").mkdir(parents=True)
    (ab_ws / "m.py").write_text("X = 1\n", encoding="utf-8")
    (ab_ws / "nk_tracking" / "benchmark_suite" / "tasks_v1.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": f"T{i}",
                        "module": "m.py",
                        "source_url": "https://example.org",
                        "evidence_quote": "evidenza valida lunga",
                        "expected": True,
                    }
                    for i in range(12)
                ]
            }
        ),
        encoding="utf-8",
    )
    return ab_ws


@pytest.mark.fast
def test_carbon_gap_hook_baseline_handoff_and_bootstrap_wal(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica Hook Stop/Sanitize, Baseline Gate, Handoff capsule e Bootstrap WAL."""
    for bad_m in (
        "not_dict",
        {"total_golden_tests": 10},
        {"total_golden_tests": 100, "unit_tests_passed": 90},
        {"pass_rate_pct": 95.0},
        {"failed_tests": 2},
    ):
        gate_r = base_mod._validate_legitimate_update_gate(bad_m)
        assert gate_r is not None and gate_r["verdict"] == "FAIL"

    assert hook_mod._is_safe_redirection_target("nk_diagnostics/out.json", tmp_path) is True
    assert hook_mod._is_safe_redirection_target("scripts/nk_diagnostics/evil.json", tmp_path) is False
    assert hook_mod._is_safe_redirection_target("%APPDATA%/evil.txt", tmp_path) is False
    san_out = hook_mod._sanitize_staged_tokens_in_cmd(
        'python ".staging/../evil.py" "scripts/.staging/x.py" "%temp%/../x" "c:/users/u/appdata/local/temp/ok.txt"'
    )
    assert "__temp_safe__" in san_out and "evil.py" in san_out

    stop_bad = json.dumps(
        {"conversationId": f"c_stop_{os.getpid()}", "response": "Status: CONVERGED_OPTIMAL", "verifiedExitZero": False}
    )
    for stop_flags in (
        ["--event", "Stop", "--shadow"],
        ["--event", "Stop", "--enforce-stop"],
        ["--event", "Stop", "--native-contract"],
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(stop_bad))
        assert _call_main(hook_mod, stop_flags, monkeypatch) == 0
    stop_ok = json.dumps(
        {"conversationId": f"c_stop_ok_{os.getpid()}", "response": "Status: CONVERGED_OPTIMAL", "verifiedExitZero": True}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(stop_ok))
    assert _call_main(hook_mod, ["--event", "Stop", "--enforce-stop"], monkeypatch) == 0

    cap_txt = hand_mod._format_safe_capsule_lines(
        ["", "not_json_" + ("x" * 250), json.dumps({"custom_only": 1}), json.dumps({"step": 1, "content": "y" * 200})],
        max_chars=260,
    )
    assert "custom_only" in cap_txt
    assert hand_mod._read_transcript_summary_fast(str(tmp_path / "no_tp.jsonl")) == (0, 0, "")
    emp_tp = tmp_path / "emp_tp.jsonl"
    emp_tp.write_text("", encoding="utf-8")
    assert hand_mod._read_transcript_summary_fast(str(emp_tp)) == (0, 0, "{}")
    sm_tp = tmp_path / "sm_tp.jsonl"
    sm_tp.write_text('{"step": 1, "content": "ok"}\n', encoding="utf-8")
    steps_sm, chars_sm, cap_sm = hand_mod._read_transcript_summary_fast(str(sm_tp))
    assert steps_sm == 1 and chars_sm > 0 and "ok" in cap_sm


@pytest.mark.fast
def test_carbon_gap_bootstrap_wal_quarantine_and_purge(tmp_path: Path) -> None:
    """Verifica ispezione stati WAL, quarantena duplicata e purge TTL bootstrap."""
    for raw_b in (b"", b"{bad", b"[]", b'{"source": "MODEL", "content": "x"}'):
        assert boot_mod.NKSessionBootstrap._extract_user_prompt_from_line(raw_b) is None
    b_ws = tmp_path / "boot_wal_ws"
    (b_ws / ".wal").mkdir(parents=True)
    sb_x = boot_mod.NKSessionBootstrap(workspace_root=b_ws)
    wal_cases = (
        (b"\xff\xfe", "CORRUPTED"),
        (b"   ", "CORRUPTED"),
        (b"[]", "CORRUPTED"),
        (b'{"state": "INIT"}\n{"state": "PREPARED"}\n', "VALID_PENDING"),
        (b"not_json\nstill_bad\n", "CORRUPTED"),
    )
    for idx_w, (w_bytes, exp_state) in enumerate(wal_cases):
        wf = b_ws / ".wal" / f"w_{idx_w}.wal"
        wf.write_bytes(w_bytes)
        assert sb_x._inspect_wal_state(wf) == exp_state
    q_src1 = b_ws / ".wal" / "dup.wal"
    q_src1.write_text("{bad1", encoding="utf-8")
    assert sb_x._quarantine_corrupted_wal(q_src1) is not None
    q_src1.write_text("{bad2", encoding="utf-8")
    assert sb_x._quarantine_corrupted_wal(q_src1) is not None
    wt_old = b_ws / ".wal" / "old.wal_tmp"
    wt_old.write_text("tmp", encoding="utf-8")
    old_ts = time.time() - 3600
    os.utime(wt_old, (old_ts, old_ts))
    purge_r = sb_x._purge_stale_wal_files(ttl_seconds=1.0)
    assert purge_r["passed"] is True and purge_r["stale_wals_purged"] >= 1


@pytest.mark.fast
def test_carbon_gap_ast_guard_dast_heavy_registry_and_preflight(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica AST Guard rich constructs, DAST heavy-data, Registry, Auto-Heal e Preflight."""
    rich_py = (
        "import os as _os\nfrom contextlib import nullcontext as nc\n"
        "type AliasInt = int\nclass GenBox[T]:\n    pass\n"
        "for _i in (1,):\n    pass\nwith nc(1) as _w:\n    pass\n"
        "try:\n    pass\nexcept Exception as _err:\n    pass\n"
        "async def rich_af(a: int, *va: int, kw: int = 1, **ka: str) -> int:\n"
        "    async with nc(1) as _aw:\n        pass\n    return a\n"
    )
    assert guard_mod.ASTGuardValidator().validate_code_edit(rich_py, rich_py, target_file="rich.py").is_valid is True
    sast_expr_py = (
        "import builtins\nimport subprocess as sp\nPFX = 'ev'\n"
        "getattr(builtins, f'{PFX}al'[0:4:1])('1')\n"
        "getattr(builtins, ''.join(['e', 'v', 'a', 'l']))('1')\n"
        "getattr(builtins, ''.join(reversed('lave')))('1')\n"
        "getattr(builtins, chr(101) + 'val')('1')\n"
        "sp.Popen('cmd', shell=(not [] and not {} and bool(-1) and bool(~0) and (True if True else False)))\n"
    )
    assert len(guard_mod.ASTGuardValidator.check_sast_constructs(sast_expr_py, target_file="sast_e.py")) >= 4
    assert _call_main(
        guard_mod, ["--target", "", "--output-json", str(tmp_path / "ag_out.json")], monkeypatch
    ) == 2
    f_not_dir = tmp_path / "single_f.py"
    f_not_dir.write_text("X = 1\n", encoding="utf-8")
    assert _call_main(guard_mod, ["--stage-dir", str(f_not_dir), "--json"], monkeypatch) == 2
    scan_cwd = tmp_path / "scan_cwd_ws"
    (scan_cwd / "scripts").mkdir(parents=True)
    (scan_cwd / "scripts" / "clean_m.py").write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    prev_cwd = Path.cwd()
    try:
        os.chdir(scan_cwd)
        assert _call_main(guard_mod, ["--json"], monkeypatch) == 0
    finally:
        os.chdir(prev_cwd)

    assert dast_mod.run_staging_shadow_verification(tmp_path / "no_dast_root")["passed"] is False
    hv_ws = tmp_path / "hv_ws"
    (hv_ws / "data" / "nested").mkdir(parents=True)
    (hv_ws / "data" / "nested" / "heavy.bin").write_bytes(b"x" * (5 * 1024 * 1024 + 64))
    (hv_ws / "data" / "big_top.bin").write_bytes(b"y" * (5 * 1024 * 1024 + 64))
    (hv_ws / ".staging").mkdir()
    assert dast_mod.run_staging_shadow_verification(hv_ws, run_pytest=False, run_ast_guard=False)["passed"] is True
    assert dast_mod.DASTSandboxRunner().kill_process_tree() is True

    _check_registry_heal_and_preflight_edges(tmp_path, monkeypatch)


def _check_registry_heal_and_preflight_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica parsing metadata Registry, AutoHeal normalize CLI e Preflight retention."""
    sk_md = (
        "---\nname: TSkill\ndescription: d\ntools: read_file, edit_file\n---\n"
        "<yaml_metadata_card>\nrole_identity: \"R1\"\ndomain_id: \"DOM-03\"\n"
        "version: \"6.0.0-Carbon\"\nsector: \"S1\"\ntools: [read_file]\n</yaml_metadata_card>\n"
        "See [doc](references/guide.md) and [res](resources/tpl.md).\n"
    )
    meta_sk = idx_mod.NKRegistryIndexer._parse_skill_metadata(sk_md)
    assert "references/guide.md" in meta_sk["auxiliary_links"]
    sc_no_arg = tmp_path / "sc_const_flags.py"
    sc_no_arg.write_text(
        '"""@domain_id: DOM-03\nDescrizione pulita modulo.\n"""\nFLAGS = ("--alpha-flag", "--beta-flag")\n',
        encoding="utf-8",
    )
    assert "--alpha-flag" in str(idx_mod.NKRegistryIndexer._extract_script_metadata(sc_no_arg))

    assert heal_mod.classify_failure("TimeoutExpired") == "TIMEOUT_ERROR"
    assert heal_mod.classify_failure("SyntaxError") == "SYNTAX_ERROR"
    assert heal_mod.classify_failure("ModuleNotFoundError") == "IMPORT_ERROR"
    assert heal_mod.classify_failure("AssertionError") == "ASSERTION_ERROR"
    assert heal_mod.classify_failure("", exit_code=0) == "NONE"
    assert "-m pytest" in str(heal_mod.normalize_test_command("pytest"))
    assert "-q" in str(heal_mod.normalize_test_command("pytest -q"))
    assert heal_mod.normalize_test_command(["pytest", "-q"])[1:4] == ["-m", "pytest", "-q"]
    assert _call_main(heal_mod, ["--cwd", str(tmp_path / "clean_h_ws"), "--json"], monkeypatch) == 0
    assert _call_main(heal_mod, ["--cwd", str(tmp_path / "clean_h_ws")], monkeypatch) == 0

    for name_w, body_w, exp_cm in (
        ("w_emp.wal", "", False),
        ("w_cm1.wal", '{"state": "COMMITTED"}', True),
        ("w_cm2.wal", '\n{"state": "PREPARED"}\n{"state": "COMMITTED"}\n', True),
    ):
        wf = tmp_path / name_w
        wf.write_text(body_w, encoding="utf-8")
        assert pre_mod.PreflightHealthChecker._is_committed_wal(wf) is exp_cm

    pf_ws = tmp_path / "pf_ws"
    rep_d = pf_ws / "nk_tracking" / "reports_and_briefs"
    (rep_d / "sub").mkdir(parents=True)
    for fn_r in ("FORENSIC_INSPECTOR_old.md", "IB-20261111-alpha.md", "sub/custom_20261111.md"):
        (rep_d / fn_r).write_text("x", encoding="utf-8")
    for idx_r in range(3):
        (rep_d / f"TAS_Report_{idx_r}.md").write_text("x", encoding="utf-8")
    (pf_ws / "nk_tracking" / "stale.bak").write_text("bak", encoding="utf-8")
    (pf_ws / "nk_genome").mkdir(parents=True)
    (pf_ws / "nk_genome" / "nk_registry_manifest.json").write_text('{"summary": {"total_skills": 16}}', encoding="utf-8")
    (pf_ws / "nk_tracking" / "quality_baseline.json").write_text("[]", encoding="utf-8")
    pfc_g = pre_mod.PreflightHealthChecker(workspace_root=pf_ws)
    assert pfc_g._enforce_report_retention(auto_fix=True, max_per_target=1)["pruned_count"] >= 2
    assert pfc_g._check_baseline_alignment()["passed"] is False


@pytest.mark.fast
def test_carbon_gap_bootstrap_fastpass_hook_stdin_and_rsi_scan(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica Bootstrap fast-pass/mutex, Hook stdin/canonical UNC e RSI mojibake/suite."""
    b_ws = tmp_path / "boot_fp_ws"
    (b_ws / ".wal").mkdir(parents=True)
    sb_fp = boot_mod.NKSessionBootstrap(workspace_root=b_ws, conversation_id="conv_fp")
    now_ep = time.time()
    r_mt = sb_fp._get_root_mtime()
    s_mt = sb_fp._get_staging_mtime()
    tp_fp = tmp_path / "fp_tp.jsonl"
    tp_fp.write_text('{"step": 1}\n', encoding="utf-8")
    for bad_cache in (
        {}, {"timestamp_epoch": 0.0}, {"timestamp_epoch": now_ep, "status": "FAIL"},
        {"timestamp_epoch": now_ep, "status": "PASS", "root_hygiene_violations": ["x.py"]},
        {"timestamp_epoch": now_ep, "status": "PASS", "root_mtime": -1.0},
        {"timestamp_epoch": now_ep, "status": "PASS", "root_mtime": r_mt, "staging_mtime": -1.0},
        {"timestamp_epoch": now_ep, "status": "PASS", "root_mtime": r_mt, "staging_mtime": s_mt,
         "conversation_id": "conv_fp", "last_transcript_path": str(tp_fp), "last_transcript_size": 999999},
    ):
        assert sb_fp._can_fast_pass(cached=bad_cache) is False

    old_ts = time.time() - 3600
    (b_ws / "orphan_old.tmp").write_text("x", encoding="utf-8")
    os.utime(b_ws / "orphan_old.tmp", (old_ts, old_ts))
    assert sb_fp._has_root_file_pollution_quick(is_hub_root=False) is True
    (b_ws / "orphan_old.tmp").unlink()
    (b_ws / "conftest.py").write_text("X = 1\n", encoding="utf-8")
    assert sb_fp._has_root_file_pollution_quick(is_hub_root=True) is True
    h_2pc = boot_mod.NKSessionBootstrap._try_acquire_2pc_mutex_nonblocking(b_ws)
    boot_mod.NKSessionBootstrap._release_2pc_mutex(h_2pc)
    boot_mod.NKSessionBootstrap._release_2pc_mutex(None)

    for raw_in, exp_err in (("", False), ("\ufeff   ", False), ("[]", True), ("{bad", True)):
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw_in))
        assert hook_mod._read_stdin_payload_ex() == ({}, exp_err)
    with monkeypatch.context() as mp_unc:
        mp_unc.setattr(os.path, "realpath", os.path.abspath)
        unc_p = hook_mod._canonical_path("\\\\?\\UNC\\127.0.0.1\\no_share_nk\\sub\\f.txt")
        assert str(unc_p).startswith("\\\\127.0.0.1")
    deep_p = hook_mod._canonical_path("\\\\?\\" + str(tmp_path / "deep" / "f.txt"))
    assert "\\\\?\\" not in str(deep_p) and deep_p.name == "f.txt"

    ab_ws = _build_ab_benchmark_ws(tmp_path / "ab_rsi_ws")
    rsi_ws = tmp_path / "rsi_scan_ws"
    (rsi_ws / ".staging" / "bench").mkdir(parents=True)
    (rsi_ws / "bad_m.md").write_text("ok \ufffd mojibake", encoding="utf-8")
    (rsi_ws / "bad_j.json").write_text("{bad", encoding="utf-8")
    (rsi_ws / "bad_s.py").write_text("import subprocess\nsubprocess.Popen('x', shell=True)\n", encoding="utf-8")
    shutil.copy2(ab_ws / "nk_tracking" / "benchmark_suite" / "tasks_v1.json", rsi_ws / ".staging" / "bench" / "tasks_v1.json")
    rsi_eng = rsi_mod.RSIConvergenceEngine(workspace_root=rsi_ws)
    scan_r = rsi_eng._scan_sast_and_mojibake(rsi_ws)
    assert scan_r["passed"] is False and scan_r["mojibake_count"] >= 1
    assert rsi_eng.run_benchmark_suite("bench", root_dir=rsi_ws)["executed"] is True
    assert rsi_eng.run_benchmark_suite("missing_suite_xyz", root_dir=rsi_ws)["passed"] is False


@pytest.mark.fast
def test_carbon_gap_phase2_orchestrated_matrix(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Esegue la Fase 2 modulare su stato condiviso Memory 3-Tier, RepoMap, Bootstrap e RSI."""
    m3_dir = tmp_path / "m3_p2"
    m3_g = mem_mod.ThreeTierMemoryEngine(base_dir=m3_dir, sliding_window_max=3)
    m3_g.append_episode(
        mem_mod.MemoryEpisode(episode_id="p2_1", domain="01_Bug_Diagnostics", title="Seed", content="Seed ep")
    )
    poly_ws = _build_polyglot_repo_ws(tmp_path / "poly_p2")
    emp_tp = tmp_path / "emp_p2.jsonl"
    emp_tp.write_text("", encoding="utf-8")
    b_ws = tmp_path / "b_p2_ws"
    (b_ws / ".wal").mkdir(parents=True)
    sb_fp = boot_mod.NKSessionBootstrap(workspace_root=b_ws, conversation_id="conv_fp")
    tp_fp = tmp_path / "fp_p2.jsonl"
    tp_fp.write_text('{"step": 1}\n', encoding="utf-8")
    rsi_ws = tmp_path / "rsi_p2_ws"
    (rsi_ws / ".staging").mkdir(parents=True)
    rsi_eng = rsi_mod.RSIConvergenceEngine(workspace_root=rsi_ws)
    _gch._run_gap_closure_phase2(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        m3_dir=m3_dir,
        m3_g=m3_g,
        poly_ws=poly_ws,
        emp_tp=emp_tp,
        b_ws=b_ws,
        sb_fp=sb_fp,
        tp_fp=tp_fp,
        rsi_ws=rsi_ws,
        rsi_eng=rsi_eng,
    )


@pytest.mark.integration
def test_carbon_gap_dast_shadow_pytest_and_watchdog_timeout(tmp_path: Path) -> None:
    """Copre esecuzione pytest nella Shadow Sandbox (pass/fail/empty) e timeout watchdog."""
    ws_pass = tmp_path / "dast_pt_pass"
    (ws_pass / "tests").mkdir(parents=True)
    (ws_pass / ".staging").mkdir()
    (ws_pass / "tests" / "test_ok.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    res_ok = dast_mod.run_staging_shadow_verification(
        repo_root=ws_pass, run_ast_guard=False, run_pytest=True, timeout_sec=15.0
    )
    assert res_ok["passed"] is True and res_ok["pytest"]["tests_passed"] == 1

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            dast_mod,
            "_run_job_isolated_subprocess",
            lambda *_a, **_kw: SimpleNamespace(returncode=5, stdout="collected 0 items\n", stderr=""),
        )
        ws_empty = tmp_path / "dast_pt_empty"
        (ws_empty / "tests").mkdir(parents=True)
        (ws_empty / ".staging").mkdir()
        (ws_empty / "tests" / "empty.txt").write_text("none", encoding="utf-8")
        res_emp = dast_mod.run_staging_shadow_verification(
            repo_root=ws_empty, run_ast_guard=False, run_pytest=True, timeout_sec=15.0
        )
        assert res_emp["passed"] is False and res_emp["pytest"]["no_tests_collected"] is True

        ws_miss = tmp_path / "dast_pt_miss"
        (ws_miss / "tests").mkdir(parents=True)
        (ws_miss / ".staging").mkdir()
        (ws_miss / "tests" / "test_rm.py").write_text("def test_rm():\n    assert True\n", encoding="utf-8")
        (ws_miss / ".staging" / ".deleted_files.json").write_text('{"deleted_files": ["tests/test_rm.py"]}', encoding="utf-8")
        res_miss = dast_mod.run_staging_shadow_verification(
            repo_root=ws_miss, run_ast_guard=False, run_pytest=True, timeout_sec=10.0
        )
        assert res_miss["pytest"]["no_tests_collected"] is True

    runner = dast_mod.DASTSandboxRunner(
        dast_mod.SandboxConfig(timeout_sec=0.15, poll_interval_sec=0.02, trace_coverage=False)
    )
    with dast_mod.ShadowSandbox() as sb_to:
        rep_to = asyncio.run(
            runner.run_in_sandbox(sb_to, [sys.executable, "-c", "import time; time.sleep(2.0)"])
        )
    assert rep_to.timed_out is True and rep_to.success is False

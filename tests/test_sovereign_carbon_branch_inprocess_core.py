# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Matrice In-Process Core (split 2/4).
Modulo: tests/test_sovereign_carbon_branch_inprocess_core.py.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib
import io
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
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
clean_mod = _load_mod("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
cache_mod = _load_mod("deterministic_api_cache", "scripts/deterministic_api_cache.py")
scaf_mod = _load_mod(
    "external_project_scaffolder", "scripts/external_project_scaffolder.py"
)
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
heal_mod = _load_mod("auto_heal_pipeline", "scripts/auto_heal_pipeline.py")
snap_mod = _load_mod(
    "healing_snapshot_rollback", "scripts/healing_snapshot_rollback.py"
)
inv_mod = _load_mod("invisible_healing_loop", "scripts/invisible_healing_loop.py")
sbfl_mod = _load_mod("sbfl_engine", "scripts/sbfl_engine.py")
bridge_mod = _load_mod("sbfl_pytest_bridge", "scripts/sbfl_pytest_bridge.py")
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
sent_mod = _load_mod("nk_context_sentry", "scripts/nk_context_sentry.py")
hud_mod = _load_mod("micro_hud_renderer", "scripts/micro_hud_renderer.py")
probe_mod = _load_mod("env_capability_probe", "scripts/env_capability_probe.py")
base_mod = _load_mod("quality_baseline_manager", "scripts/quality_baseline_manager.py")
led_mod = _load_mod("dual_ledgers", "scripts/schemas/dual_ledgers.py")
act_mod = _load_mod(
    "nk_active_runtime_sentinel", "scripts/nk_active_runtime_sentinel.py"
)
ipc_mod = _load_mod("nk_ipc_contracts", "scripts/schemas/nk_ipc_contracts.py")


@pytest.mark.fast
def test_carbon_inprocess_sbfl_compliance_sentinel_and_dast_helpers(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre validazioni matrice SBFL, formule Ochiai/Tarantula/DStar, tri-pass e bridge JSON."""
    for args in (
        (["s1", "s2"], ["t1"], [[1]], [0]),
        (["s1"], ["t1"], [[2]], [0]),
        (["s1"], ["t1"], [[1]], [2]),
    ):
        with pytest.raises(ValueError):
            sbfl_mod.CoverageMatrix(*args)
    cm = sbfl_mod.CoverageMatrix(["s1"], ["t1"], [[1]], [0])
    assert list(cm.statements) == ["s1"] and list(cm.test_ids) == ["t1"] and cm.num_statements == 1
    assert len(cm.matrix) == 1 and list(cm.outcomes) == [0]
    with pytest.raises(KeyError):
        cm.get_spectrum("missing_stmt")
    mon_flag, mon_exec = sbfl_mod.collect_statements_with_monitoring(lambda: None)
    assert isinstance(mon_flag, bool) and isinstance(mon_exec, set)

    z_ef = sbfl_mod.SpectrumCounts(n_ef=0, n_ep=1, n_nf=0, n_np=1)
    assert sbfl_mod.calculate_ochiai(sbfl_mod.SpectrumCounts(n_ef=0, n_ep=0, n_nf=0, n_np=1)) == 0.0
    assert sbfl_mod.calculate_tarantula(z_ef) == 0.0
    assert sbfl_mod.calculate_tarantula(sbfl_mod.SpectrumCounts(n_ef=2, n_ep=0, n_nf=0, n_np=0)) == 1.0
    assert sbfl_mod.calculate_tarantula(sbfl_mod.SpectrumCounts(n_ef=0, n_ep=0, n_nf=1, n_np=1)) == 0.0
    assert sbfl_mod.calculate_dstar(sbfl_mod.SpectrumCounts(n_ef=0, n_ep=1, n_nf=1, n_np=1)) == 0.0
    assert sbfl_mod.calculate_dstar(sbfl_mod.SpectrumCounts(n_ef=2, n_ep=0, n_nf=0, n_np=1)) > 1000.0
    assert sbfl_mod.calibrate_coincidental_correctness(z_ef, def_use_weight=0.5) == 0.0
    assert sbfl_mod.calibrate_coincidental_correctness(
        sbfl_mod.SpectrumCounts(n_ef=2, n_ep=2, n_nf=0, n_np=2), def_use_weight=0.8
    ) > 0.0
    with pytest.raises(ValueError):
        sbfl_mod.tri_pass_voting_filter([[]])

    run_a = [
        sbfl_mod.CoverageRecord(test_id="T_PASS", passed=True, executed_statements=["m.py:1"]),
        sbfl_mod.CoverageRecord(test_id="T_FAIL", passed=False, executed_statements=["m.py:2"]),
        sbfl_mod.CoverageRecord(test_id="T_FLAKY", passed=True, executed_statements=["m.py:1"]),
    ]
    run_b = run_a[:2] + [sbfl_mod.CoverageRecord(test_id="T_FLAKY", passed=False, executed_statements=["m.py:1"])]
    tp_res = sbfl_mod.tri_pass_voting_filter([run_a, run_b, run_a])
    assert len(tp_res.retained_records) == 2 and tp_res.flaky_test_ids == ["T_FLAKY"]

    sb_eng = sbfl_mod.SBFLEngine()
    assert sb_eng.generate_diagnostic_payload([]).top_fault == "NONE:0"
    long_recs = [
        sbfl_mod.CoverageRecord(
            test_id="TF", passed=False,
            executed_statements=[f"pkg_mod_long_name_{i}_" + ("x" * 75) + f".py:{i + 1}" for i in range(5)],
        )
    ]
    trunc_pl = sb_eng.generate_diagnostic_payload(sb_eng.analyze(sbfl_mod.CoverageMatrix.from_records(long_recs)), top_k=5)
    assert len(trunc_pl.top_candidates) == 1
    assert _call_main(sbfl_mod, [], monkeypatch) == 0

    loc_long = bridge_mod.OchiaiBridgeLocation(
        file_path="very/deep/nested/folder/module_alpha_target_long_name.py",
        line_number=12, suspiciousness=0.91,
        error_type="CustomRuntimeException" + ("X" * 240),
        error_message="M" * 140, failing_line_content="C" * 140,
    )
    assert '"score":0.91' in loc_long.render_payload_json()
    br = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    sum_ok = br.parse_pytest_output("2 passed in 0.02s\n", "", exit_code=0)
    assert sum_ok.passed_count == 2 and br.extract_failure_location(sum_ok) is None
    err_mod = tmp_path / "mod_err.py"
    err_mod.write_text("x = 1\ny = 2\nraise RuntimeError('boom')\n", encoding="utf-8")
    sum_fail = br.parse_pytest_output(
        f"{err_mod.as_posix()}:3: in run\nE   plain failure without colon\n1 failed, 2 passed in 0.03s\n", "", exit_code=1,
    )
    ext_loc = br.extract_failure_location(sum_fail, target_file_hint="mod_err.py", passed_line_counts=None)
    assert ext_loc is not None and ext_loc.error_type == "AssertionError" and "RuntimeError" in ext_loc.failing_line_content


@pytest.mark.fast
def test_carbon_core_compliance_checker_audit(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica correlazione ID, streak DDI, polling e external write su NKComplianceChecker."""
    assert comp_mod._parse_record_epoch(1700000000) == 1700000000.0
    parsed_iso = comp_mod._parse_record_epoch("2026-11-11T12:00:00Z")
    assert parsed_iso is not None and parsed_iso > 1700000000.0
    assert comp_mod._parse_record_epoch("not-a-date") is None
    assert comp_mod._parse_record_epoch(True) is None
    assert comp_mod._extract_call_correlation_id({"tool_response": {"call_id": "cid_9"}}) == "cid_9"
    assert comp_mod._pop_correlated_tool_call([{"id": "c1"}, {"id": "c2"}], {"call_id": "c2"})["id"] == "c2"

    sess_tp = tmp_path / "brain" / "sess_xyz" / "transcript.jsonl"
    sess_tp.parent.mkdir(parents=True, exist_ok=True)
    assert comp_mod.NKComplianceChecker._extract_session_identifier(sess_tp) == "sess_xyz"
    assert comp_mod.NKComplianceChecker._extract_session_identifier(None) == ""
    (sess_tp.parent / "rsi_telemetry.jsonl").write_text(
        json.dumps({"fitness_q": 91.5, "delta_k": 2}) + "\n", encoding="utf-8"
    )
    tr_events = [
        {"type": "USER_INPUT", "content": "Esegui audit"},
        {"type": "MODEL", "tool_calls": [{"id": "p1", "name": "manage_task", "args": {"Action": "status"}}]},
        {"type": "TOOL", "call_id": "p1", "content": "running"},
        {"type": "MODEL", "tool_calls": [
            {"id": "w1", "name": "write_file", "args": {"Path": "NK_External_Projects/App/src_app/a.py"}},
            {"id": "r1", "name": "run_command", "args": {"CommandLine": "Set-Content NK_External_Projects/App/src_app/b.py '1'"}},
        ]},
        {"type": "TOOL", "call_id": "w1", "content": "ok"},
        {"type": "TOOL", "call_id": "r1", "content": 'Command exited with code 1\n{"status": "REFINING", "delta_k": 2}'},
    ]
    for idx_s in range(13):
        cid = f"rd_{idx_s}"
        tr_events.append({"type": "MODEL", "tool_calls": [{"id": cid, "name": "read_file", "args": {"Path": "README.md"}}]})
        tr_events.append({"type": "TOOL", "call_id": cid, "content": "Command exited with code 1\ncrash"})
    sess_tp.write_text("\n".join(json.dumps(e) for e in tr_events) + "\n", encoding="utf-8")
    checker = comp_mod.NKComplianceChecker(workspace_root=tmp_path)
    assert checker.audit_transcript(tmp_path / "missing.jsonl")["status"] == "ERROR"
    aud = checker.audit_transcript(sess_tp)
    assert aud["status"] == "FAIL" and aud["scores"]["composite_score"] < 99
    assert _call_main(comp_mod, ["--transcript", str(sess_tp), "--min-score", "99"], monkeypatch) == 1


@pytest.mark.fast
def test_carbon_core_active_sentinel_dast_and_ast_guard(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre nk_active_runtime_sentinel, helper RSS/ShadowSandbox e pattern matching AST Guard."""
    assert act_mod._is_compaction_checkpoint("{}", {"compacted": True}) is True
    assert act_mod._is_compaction_checkpoint(
        "{}", {"type": "SYSTEM_MESSAGE", "content": "[Message] sender=w1 <CONTEXT_SUMMARY>"}
    ) is False
    assert act_mod._count_steps_since_compaction(tmp_path / "none.jsonl") == (0, 0, 0)
    bad_tr = tmp_path / "bad_only.jsonl"
    bad_tr.write_text("\n{invalid_json\n[1, 2]\n", encoding="utf-8")
    assert act_mod.run_sentinel(str(bad_tr), profile="carbon")["steps"] == 2
    red_tr = tmp_path / "red_std.jsonl"
    red_tr.write_text('{"type": "USER", "content": "x"}\n' * 105, encoding="utf-8")
    assert _call_main(act_mod, ["--transcript", str(red_tr), "--profile", "standard", "--json", "--check"], monkeypatch) == 1

    rss_st = dast_mod._RSSMonitorState()
    assert rss_st.record_sample(2048) == 2048 and rss_st.get_peak() == 2048
    rss1 = dast_mod._get_process_memory_rss(os.getpid(), p_process=None, rss_state=rss_st)
    rss2 = dast_mod._get_process_memory_rss(os.getpid(), p_process=None, rss_state=rss_st)
    assert (rss1 > 0 if sys.platform == "win32" else rss1 >= 0) and rss2 == rss1
    assert dast_mod._assign_pid_to_job(0, 0) is False and dast_mod._resume_process_primary_thread(0) is False
    assert dast_mod.CoverageTraceItem(file_name="m.py", line_number=4, execution_count=1).statement_id == "m.py:4"

    src_sample = tmp_path / "sample_copy.py"
    src_sample.write_text("VAL = 7\n", encoding="utf-8")
    with dast_mod.ShadowSandbox() as sb:
        sb.write_file("raw.bin", b"\x01\x02")
        with pytest.raises(FileNotFoundError):
            sb.copy_file(tmp_path / "nope_src.py")
        d1 = sb.copy_file(src_sample, "nested_dir/")
        d2 = sb.copy_file(src_sample, "nested_dir")
        d3 = sb.copy_file(src_sample, "nested_dir/renamed.py")
        assert d1.is_file() and d2.is_file() and d3.is_file()

    norm_fn = guard_mod._normalize_type_annotation
    assert norm_fn(None) is None and norm_fn("") == ""
    assert norm_fn("Optional[List[int]]") == "list[int] | None"
    assert norm_fn("Union[str, int, None]") == "int | str | None"
    assert norm_fn("typing.Dict[str, NoneType]") == "dict[str, None]"
    assert norm_fn("'int | None'") == "int | None" and norm_fn("invalid_syntax[") == "invalid_syntax["

    rich_code = (
        "from pathlib import Path\nimport sys\nGLOBAL_X: int = 10\na, *b = [1, 2, 3]\n"
        "def outer(val: int | str, items: list[int]) -> int:\n    global GLOBAL_X\n    counter = 0\n"
        "    def inner() -> int:\n        nonlocal counter\n        counter += 1\n        return counter\n"
        "    comp = [y for z in items if (y := z + 1) > 0]\n    dcomp = {k: k * 2 for k in comp}\n"
        "    match val:\n        case [first, *rest]:\n            res = len(rest) + int(first)\n"
        "        case {'k': v, **extra}:\n            res = len(extra) + int(v)\n"
        "        case 1 | 2 as matched if matched > 0:\n            res = matched + len(dcomp)\n"
        "        case _:\n            res = inner()\n"
        "    bad_p = Path('base') / '../escape'\n    tag = 'NK_External_Projects/demo'\n    byp = 'ORACLE_BYPASS'\n"
        "    _ = sys.modules.get('os')\n    return res + len(str(bad_p)) + len(tag) + len(byp)\n"
    )
    rep = guard_mod.ASTGuardValidator.validate_code_edit(
        "def old_fn(x: int) -> int:\n    return x\n", rich_code, target_file="src_app/service.py"
    )
    assert rep.is_valid is False and len(rep.violations) >= 3


@pytest.mark.fast
def test_carbon_core_win32_2pc_rel_path_json_ratchet(tmp_path: Path) -> None:
    """Verifica canonical path 2PC, validate_staging_json_files, ratchet, atomic replace e purge."""
    for bad_rel in ("", "a\x00b", "a:ads", "../escape.py", "bad./file.py", "."):
        with pytest.raises(w2pc_mod.TwoPhaseCommitError):
            w2pc_mod._validate_win32_canonical_rel_path(bad_rel)
    assert w2pc_mod._validate_win32_canonical_rel_path("scripts\\sub\\ok.py") == "scripts/sub/ok.py"
    long_sub = tmp_path / ("d" * 120) / ("e" * 120) / "leaf.txt"
    if os.name == "nt":
        assert "\\\\?\\" in str(w2pc_mod._win_long_path(long_sub))
    else:
        assert w2pc_mod._win_long_path(long_sub) == long_sub

    jdir = tmp_path / "json_stg"
    jdir.mkdir(parents=True)
    (jdir / "bom_ok.json").write_bytes(b"\xef\xbb\xbf" + b'{"ok": true}')
    assert w2pc_mod.validate_staging_json_files(jdir)[0] is True
    (jdir / "bad_utf8.json").write_bytes(b"\xff\xfe\x00")
    (jdir / "bad_fffd.json").write_text('{"k": "\ufffd"}', encoding="utf-8")
    (jdir / "bad_syn.json").write_text("{broken", encoding="utf-8")
    ok_j, errs_j = w2pc_mod.validate_staging_json_files(jdir)
    assert ok_j is False and len(errs_j) == 3

    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod._verify_quality_baseline_ratchet({})
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod._verify_quality_baseline_ratchet({"pass_rate": 95.0, "golden_tests_count": 50})
    r_dict = w2pc_mod._verify_quality_baseline_ratchet(
        {"pass_rate_pct": 100.0, "total_tests": 175, "failed_tests": 0}
    )
    assert r_dict["verdict"] == "PASS" and r_dict["total_tests"] == 175

    dst_bl, stg_bl = tmp_path / "dst_qb.json", tmp_path / "stg_qb.json"
    dst_bl.write_text(json.dumps({"pass_rate_pct": 100.0, "total_tests": 170}), encoding="utf-8")
    stg_bl.write_text(json.dumps({"pass_rate_pct": 100.0, "total_tests": 175}), encoding="utf-8")
    assert w2pc_mod._verify_quality_baseline_ratchet(dst_bl, stg_bl)["verdict"] == "PASS"
    stg_bl.write_text(json.dumps({"pass_rate_pct": 92.0, "total_tests": 175}), encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod._verify_quality_baseline_ratchet(dst_bl, stg_bl)

    src_at, dst_at = tmp_path / "at_src.txt", tmp_path / "at_dst.txt"
    src_at.write_text("v2", encoding="utf-8")
    dst_at.write_text("v1", encoding="utf-8")
    w2pc_mod.win32_atomic_replace(src_at, dst_at)
    assert dst_at.read_text(encoding="utf-8") == "v2"

    bc_root = tmp_path / "bc_repo"
    (bc_root / "scripts" / "__pycache__").mkdir(parents=True)
    (bc_root / "scripts" / "__pycache__" / "mod.cpython-312.pyc").write_bytes(b"\x00\x01")
    w2pc_mod._purge_production_bytecode(bc_root)
    assert not (bc_root / "scripts" / "__pycache__").exists()


@pytest.mark.fast
def test_carbon_inprocess_shadow_overlay_socket_hook_rsi_and_mapper(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Copre in-process run_staging_shadow_verification con deleted files ed overlay builder."""
    del monkeypatch, isolated_nk_env
    miss_ov = dast_mod.run_staging_shadow_verification(
        tmp_path / "no_such_repo_xyz", run_pytest=False, run_ast_guard=False
    )
    assert miss_ov["passed"] is False

    mini_repo = tmp_path / "mini_repo"
    for rel_d in ("scripts", "tests/evals", "data", "custom_pkg", ".staging/scripts", ".staging/data"):
        (mini_repo / rel_d).mkdir(parents=True)
    (mini_repo / "README.md").write_text("# Mini\n", encoding="utf-8")
    (mini_repo / "oracle_lock.json").write_text("{}", encoding="utf-8")
    (mini_repo / "tests" / "evals" / "holdout.json").write_text("{}", encoding="utf-8")
    (mini_repo / "scripts" / "old_s.py").write_text("OLD = 1\n", encoding="utf-8")
    (mini_repo / "data" / "small.json").write_text('{"k": 1}', encoding="utf-8")
    (mini_repo / "custom_pkg" / "mod_c.py").write_text("C = 2\n", encoding="utf-8")
    (mini_repo / ".staging" / "scripts" / "new_s.py").write_text("NEW = 3\n", encoding="utf-8")
    (mini_repo / ".staging" / "data" / "ov.json").write_text('{"ov": true}', encoding="utf-8")
    (mini_repo / ".staging" / ".deleted_files.json").write_text(
        json.dumps(["scripts/old_s.py"]), encoding="utf-8"
    )
    ov_res = dast_mod.run_staging_shadow_verification(
        mini_repo, run_pytest=False, run_ast_guard=False, profile="builder"
    )
    assert ov_res["passed"] is True and "scripts/old_s.py" in ov_res["deleted_files"]


@pytest.mark.integration
def test_carbon_core_cleanup_tcp_socket_listener() -> None:
    """Verifica safe_cleanup_dev_servers su socket TCP reale in ascolto su loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv_sock:
        srv_sock.bind(("127.0.0.1", 0))
        srv_sock.listen(1)
        bound_port = int(srv_sock.getsockname()[1])
        live_pids = clean_mod.get_pids_listening_on_ports(
            ports=[bound_port], workspace_root=_WORKSPACE_ROOT
        )
        assert os.getpid() not in live_pids and isinstance(live_pids, set)


@pytest.mark.fast
def test_carbon_core_registry_mirrors_and_hook_gate_cli(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica sync plugin mirrors, CLI subcommands nk_hook_gate e target redirezione."""
    idx_ws = tmp_path / "idx_ws"
    for p in (
        ".staging/.agents/plugins/nk-gate/agents",
        ".staging/.agents/plugins/nk-gate/rules",
        ".agents/plugins/nk-gate/agents",
        ".agents/plugins/nk-gate/rules",
        ".agents/agents/NK-Builder-Agent",
        ".agents/rules",
    ):
        (idx_ws / p).mkdir(parents=True)
    (idx_ws / ".agents" / "agents" / "NK-Builder-Agent" / "agent.md").write_text("# Ag\n", encoding="utf-8")
    (idx_ws / ".agents" / "rules" / "anti_crash_rules.md").write_text("# Rule\n", encoding="utf-8")
    idx_inst = idx_mod.NKRegistryIndexer(workspace_root=idx_ws)
    assert len(idx_inst._sync_nk_gate_plugin_mirrors(True, idx_ws / "nk_genome")) == 2
    assert len(idx_inst._sync_nk_gate_plugin_mirrors(False, idx_ws / "nk_genome")) == 2
    assert idx_inst._sync_nk_gate_plugin_mirrors(False, tmp_path / "outside_genome") == []

    hooks_tmp = tmp_path / "hooks_state"
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _call_main(hook_mod, ["probe", "--conversation-id", "c_h1"], monkeypatch) == 0
    assert _call_main(hook_mod, ["session-start", "--conversation-id", "c_h1", "--native-contract"], monkeypatch) == 0
    assert _call_main(hook_mod, ["session-start", "--conversation-id", "c_h1"], monkeypatch) == 0
    assert _call_main(
        hook_mod, ["write-gate", "--event", "PreToolUse", "--shadow", "--native-contract", "--conversation-id", "c_h1"], monkeypatch
    ) == 0
    (hooks_tmp / "nk_hooks").mkdir(parents=True, exist_ok=True)
    (hooks_tmp / "nk_hooks" / "fasttrack_c_h1.json").write_text('{"streak": 15}', encoding="utf-8")
    assert _call_main(
        hook_mod, ["fasttrack", "--event", "PreInvocation", "--native-contract", "--shadow", "--conversation-id", "c_h1"], monkeypatch
    ) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO("{malformed"))
    assert _call_main(hook_mod, ["stop-evidence", "--enforce-stop", "--conversation-id", "c_h2"], monkeypatch) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"verifiedExitZero": true, "content": "done"}'))
    assert _call_main(hook_mod, ["stop-evidence", "--conversation-id", "c_h3"], monkeypatch) == 0

    redirs = hook_mod._extract_redirection_targets_single(
        """echo 'a > b' "c \\" `> d" -> x >= 1 2>&1 > "%TEMP%\\nk_diagnostics\\r.json" >>"""
    )
    assert "__empty_redirect__" in redirs
    assert hook_mod._is_safe_redirection_target("NUL", tmp_path) is True
    assert hook_mod._is_safe_redirection_target("%TEMP%/out.txt", tmp_path) is True
    assert hook_mod._is_safe_redirection_target("C:/Users/u/AppData/Local/Temp/x.txt", tmp_path) is True
    assert hook_mod._is_safe_redirection_target("%APPDATA%/x.txt", tmp_path) is False
    assert hook_mod._is_safe_redirection_target("../escape.txt", tmp_path) is False


@pytest.mark.fast
def test_carbon_core_transcript_quarantine_rsi_mapper_and_bootstrap(tmp_path: Path) -> None:
    """Copre transcript tools, quarantine_staging, RSI verify_convergence, RepoMap e Bootstrap."""
    assert tr_mod.clean_tool_path(None) == ""
    assert tr_mod.clean_tool_path('"\\"a/b.py\\""') == "a/b.py"
    assert tr_mod.clean_tool_str(None) == ""
    assert tr_mod.clean_tool_str("'hello'") == "hello" and tr_mod.clean_tool_str('"bad\\u"') == "bad\\u"
    assert tr_mod.extract_tool_name("not_dict") == ""  # type: ignore[arg-type]
    assert tr_mod.extract_tool_args({"arguments": '{"k": 5}'}) == {"k": 5}
    assert tr_mod.extract_tool_args({"arguments": "{bad"}) == {}
    assert tr_mod._extract_call_id({"tool_result": {"call_id": "tr_1"}}) == "tr_1"
    assert tr_mod._extract_call_id({"tool_results": [{"id": "tr_2"}]}) == "tr_2"

    q_empty = tmp_path / "q_empty_repo"
    q_empty.mkdir(parents=True)
    assert w2pc_mod.quarantine_staging(q_empty)["quarantined_count"] == 0
    (q_empty / ".staging" / "scripts").mkdir(parents=True, exist_ok=True)
    (q_empty / ".staging" / "scripts" / "dirty.py").write_text("D = 1\n", encoding="utf-8")
    assert w2pc_mod.quarantine_staging(q_empty)["quarantined_count"] >= 1

    mini_hub = tmp_path / "mini_hub"
    for sub in (".agents/rules", ".agents/skills/NK-Demo", ".agents/agents/NK-Worker", "nk_genome", "scripts"):
        (mini_hub / sub).mkdir(parents=True)
    (mini_hub / ".agents" / "AGENTS.md").write_text("# Costituzione [RULE-STE100]\nUsa frasi attive.\n", encoding="utf-8")
    (mini_hub / ".agents" / "rules" / "anti_crash_rules.md").write_text("# Regole\nChiudi i file.\n", encoding="utf-8")
    (mini_hub / ".agents" / "skills" / "NK-Demo" / "SKILL.md").write_text(
        "---\nname: NK-Demo\nversion: '6.0.0-Carbon'\ndomain_id: DOM-03\ntools: ['read_file']\n---\n# Skill v6.0.0-Carbon\n",
        encoding="utf-8",
    )
    (mini_hub / ".agents" / "agents" / "NK-Worker" / "agent.md").write_text("# Worker\nOpera bene.\n", encoding="utf-8")
    (mini_hub / "nk_genome" / "PATCH_NOTES.md").write_text("# Patch\n## [v6.0.0-Carbon]\n", encoding="utf-8")
    (mini_hub / "scripts" / "broken.json").write_text("{bad", encoding="utf-8")
    (mini_hub / "scripts" / "moj.md").write_text("bad \ufffd char\n", encoding="utf-8")
    assert rsi_mod.RSIConvergenceEngine(workspace_root=mini_hub, root=mini_hub).verify_convergence(
        root_dir=mini_hub, run_pytest=False, profile="ste100_rsi"
    )["passed"] is False

    map_ws = tmp_path / "map_ws"
    (map_ws / "pkg_a").mkdir(parents=True)
    (map_ws / "pkg_b").mkdir(parents=True)
    (map_ws / "pkg_a" / "big_mod.py").write_text(
        "class AlphaSvc:\n    def m1(self): return 1\n    def m2(self): return 2\nclass BetaSvc:\n    pass\n",
        encoding="utf-8",
    )
    for idx_m in range(4):
        (map_ws / "pkg_b" / f"sub_{idx_m}.py").write_text(
            f"from pkg_a.big_mod import AlphaSvc\ndef call_{idx_m}():\n    return AlphaSvc().m1()\n",
            encoding="utf-8",
        )
    res_map = map_mod.RepoMapGenerator.generate(map_ws, map_mod.RepoMapConfig(max_tokens=128, cache_enabled=False))
    assert res_map.files_scanned >= 5 and len(res_map.content) > 10
    assert map_mod.query_symbol_subgraph("", root_dir=map_ws)["found"] is False
    assert map_mod.query_symbol_subgraph("AlphaSvc", root_dir=map_ws)["found"] is True


@pytest.mark.fast
def test_carbon_core_bootstrap_fast_tail_and_router_ast_risk(tmp_path: Path) -> None:
    """Verifica NKSessionBootstrap transcript tail e VibeSprintRouter intent/risk/capsule."""
    boot_ws = tmp_path / "boot_ws"
    (boot_ws / ".staging").mkdir(parents=True)
    (boot_ws / ".staging" / "x.py").write_text("X = 1\n", encoding="utf-8")
    (boot_ws / "polluted.tmp").write_text("tmp", encoding="utf-8")
    sb_b = boot_mod.NKSessionBootstrap(workspace_root=boot_ws)
    assert sb_b._check_root_hygiene(use_fast_cache=False)["passed"] is False
    assert sb_b._find_recent_transcript(tmp_path / "no_brain") is None

    fake_brain = tmp_path / "fake_brain"
    c_sub = fake_brain / "conv_sub" / ".system_generated" / "logs"
    c_main = fake_brain / "conv_main" / ".system_generated" / "logs"
    c_sub.mkdir(parents=True)
    c_main.mkdir(parents=True)
    (c_sub / "transcript.jsonl").write_text(
        '{"source": "SYSTEM", "content": "[Message] sender=p <env_capsule>"}\n', encoding="utf-8"
    )
    main_tp = c_main / "transcript.jsonl"
    main_tp.write_text('{"source": "USER", "type": "USER_INPUT", "content": "Ciao"}\n' * 12, encoding="utf-8")
    assert sb_b._find_recent_transcript(fake_brain) == main_tp
    assert boot_mod.NKSessionBootstrap(workspace_root=boot_ws, conversation_id="conv_main")._find_recent_transcript(fake_brain) == main_tp
    assert sb_b._count_lines_binary_64kb(main_tp, 0) == 0
    assert sb_b._count_lines_binary_64kb(main_tp, main_tp.stat().st_size) >= 12
    assert sb_b._count_post_compaction_binary(main_tp, 0) == (0, 0)
    tail_est = sb_b._fast_tail_estimate(
        main_tp, main_tp.stat().st_size,
        cached={"last_transcript_size": 10, "last_step_count": 1, "last_transcript_path": str(main_tp), "checks": {"context_sentry": {"estimated_tokens": 5}}},
        sentry=sent_mod.NKContextSentry(),
    )
    assert tail_est["step_count"] >= 1

    assert router_mod._has_destructive_shell_command("") is False
    assert router_mod._has_destructive_shell_command("rm -rf /tmp/demo") is True
    assert router_mod._has_destructive_shell_command("del modulo.py") is True
    assert router_mod._has_destructive_shell_command("del sistema?") is False
    assert router_mod._has_destructive_shell_command("echo ok; del target.py") is True
    assert router_mod._analyze_write_intent("") == (False, False)
    assert router_mod._analyze_write_intent("non toccare .staging, modifica .staging") == (True, True)
    assert router_mod._analyze_write_intent("fai il refactoring del modulo") == (True, False)
    assert router_mod._analyze_write_intent("valuta il refactoring del modulo")[0] is False
    assert router_mod._analyze_write_intent("spiega come modificare il file")[0] is False

    r_ws = tmp_path / "router_ws"
    (r_ws / "nk_tracking" / "memory").mkdir(parents=True)
    (r_ws / "nk_tracking" / "memory" / "tier1_active_capsule.json").write_text(
        json.dumps({"domains": {"ARCH": {"total_tokens": 20, "context": "raw", "summary": "ok"}}, "lessons": [{"lesson": "Usa contratti tipizzati."}]}),
        encoding="utf-8",
    )
    vr = router_mod.VibeSprintRouter(workspace_root=r_ws)
    assert vr.compute_ast_risk_score("body { color: red; }\n", filename="app.css")["max_depth"] == 0
    assert vr.compute_ast_risk_score("def broken(:\n", filename="bad.py")["recommended_mode"] == "mode_a"
    med_py = "\n".join(f"class C{i}:\n    def f(self):\n        return {i}\n" for i in range(6))
    assert vr.compute_ast_risk_score(med_py, filename="med.py")["classes"] == 6
    comp_cap = vr.load_prewarmed_capsule(compact=True)
    assert "ARCH" in comp_cap["domains"] and "context" not in comp_cap["domains"]["ARCH"]
    assert "Tier-1 Capsule:" in vr.generate_inline_micro_spec("a.py", "aggiorna", {"risk_score": 0.1, "loc": 8, "max_depth": 1})
    assert "<env_capsule>" in router_mod.generate_env_capsule(workspace_root=r_ws)
    assert "domain_id" in router_mod.resolve_domain_from_manifest("win32 2pc", workspace_root=_WORKSPACE_ROOT)
    assert "intrinsic_protocols" in router_mod.resolve_intrinsic_vibe_protocols("/plan x", workspace_root=_WORKSPACE_ROOT)
    gate_r = router_mod.evaluate_meta_prompt_gate("analizza codice", workspace_root=_WORKSPACE_ROOT)
    assert "gate_mode" in gate_r and gate_r["enabled"] is True
    assert "passed" in router_mod.validate_generated_prompt("Prompt valido", workspace_root=_WORKSPACE_ROOT)
    assert router_mod._extract_user_text_from_record({"type": "MODEL"}) is None
    assert router_mod._extract_user_text_from_record({"type": "USER_INPUT", "content": [{"text": "Input strutturato"}]}) == "Input strutturato"


@pytest.mark.fast
def test_carbon_core_probe_cache_heal_preflight_and_ipc(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre probe, cache, auto_heal, QBM, Preflight, handoff, memory zlib, IPC e TaskLedger."""
    assert "available" in probe_mod.check_module_availability("pywin32")
    assert probe_mod.check_module_availability("missing_mod_nk_999")["available"] is False
    assert _call_main(probe_mod, ["--check-module", "missing_mod_nk_999"], monkeypatch) == 1
    monkeypatch.setenv("NK_FORCE_NETWORK_REFRESH", "0")
    assert _call_main(cache_mod, ["--force-refresh"], monkeypatch) == 0
    monkeypatch.delenv("NK_FORCE_NETWORK_REFRESH", raising=False)
    assert _call_main(cache_mod, ["--clear"], monkeypatch) == 0
    assert _call_main(cache_mod, [], monkeypatch) == 0

    for msg, exp_c in (
        ("TimeoutExpired", "TIMEOUT_ERROR"),
        ("SyntaxError: invalid", "SYNTAX_ERROR"),
        ("ModuleNotFoundError: x", "IMPORT_ERROR"),
        ("AssertionError: bad", "ASSERTION_ERROR"),
    ):
        assert heal_mod.classify_failure(msg) == exp_c
    assert heal_mod.classify_failure("boom", exit_code=1) == "RUNTIME_ERROR"
    assert "-m pytest" in str(heal_mod.normalize_test_command("pytest"))
    assert "-m" in list(heal_mod.normalize_test_command(["pytest", "-q"]))
    clean_t = tmp_path / "clean_heal_target.py"
    clean_t.write_text("def ok_fn(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    dk, qk = heal_mod._compute_rsi_metrics(4, 1, target_path=clean_t)
    assert dk > 0 and qk < 100.0
    empty_heal_ws = tmp_path / "empty_heal_ws"
    empty_heal_ws.mkdir()
    assert _call_main(heal_mod, ["--cwd", str(empty_heal_ws)], monkeypatch) == 0
    assert base_mod.recalibrate_baseline(str(tmp_path / "b.json"), target_golden_tests=10)["status"] == "REJECTED"
    bad_bl = tmp_path / "corrupt_bl.json"
    bad_bl.write_text("{corrupt", encoding="utf-8")
    assert base_mod.update_baseline_metrics(str(bad_bl), {"failed_tests": 1})["status"] == "REJECTED"
    assert base_mod._resolve_default_baseline_path().endswith("quality_baseline.json")

    pf_ws = tmp_path / "pf_ws"
    (pf_ws / "nk_tracking" / "anchor").mkdir(parents=True)
    (pf_ws / "nk_tracking" / "reports_and_briefs" / "sub").mkdir(parents=True)
    (pf_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl").write_text("\n{bad_jsonl\n", encoding="utf-8")
    (pf_ws / "session_anchor.jsonl").write_text("{}", encoding="utf-8")
    (pf_ws / "nk_tracking" / "old.bak").write_text("b", encoding="utf-8")
    (pf_ws / "nk_tracking" / "reports_and_briefs" / "sub" / "nested.md").write_text("# R\n", encoding="utf-8")
    pfc = pre_mod.PreflightHealthChecker(workspace_root=pf_ws)
    assert pfc._check_ssot_anchor(auto_fix=False)["passed"] is False
    assert pfc.run_full_check(auto_fix=False)["status"] == "FAIL"
    rep_fix = pfc.run_full_check(auto_fix=True)
    assert rep_fix["checks"]["staging_hygiene"]["passed"] is True
    assert pfc._collect_tracking_bak_files_shallow() == []
    assert len(pfc._collect_report_files_shallow()) == 1
    wal_ml = tmp_path / "ml.wal"
    wal_ml.write_text('{"state": "PREPARED"}\n{"state": "COMMITTED"}\n', encoding="utf-8")
    assert pfc._is_committed_wal(wal_ml) is True


@pytest.mark.fast
def test_carbon_core_handoff_memory_zlib_ipc_and_task_ledger(tmp_path: Path) -> None:
    """Verifica Handoff summary, Memory Tier3 zlib recovery, IPC contracts e TaskLedger."""
    h_ws = tmp_path / "hand_ws"
    (h_ws / "nk_tracking").mkdir(parents=True)
    (h_ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"total_tests": 180, "pass_rate_pct": 100.0}), encoding="utf-8"
    )
    assert hand_mod._read_baseline_tests_count(h_ws) == 180
    assert hand_mod._read_baseline_pass_rate(h_ws) == 100.0
    big_htp = tmp_path / "big_hand.jsonl"
    big_htp.write_text(('{"step": 1, "content": "' + ("Z" * 380) + '"}\n') * 110, encoding="utf-8")
    st_cnt, _, cap_s = hand_mod._read_transcript_summary_fast(str(big_htp))
    assert st_cnt >= 100 and len(cap_s) > 2
    assert hand_mod.persist_intent_brief("20261111-COV", "Intent di test", project_root=str(h_ws)).is_file()

    m3_base = tmp_path / "m3_zlib"
    m3 = mem_mod.ThreeTierMemoryEngine(base_dir=m3_base)
    ep_saved = mem_mod.MemoryEpisode(
        episode_id="ep_zlib_01", domain="01_Bug_Diagnostics", title="Pydantic Strict",
        content="Validazione rigorosa contratti", tags=["pydantic", "ipc"],
    )
    m3.append_episode(ep_saved)
    cold_gz = m3_base / "01_Bug_Diagnostics" / "archive.cold.jsonl.gz"
    cold_gz.parent.mkdir(parents=True, exist_ok=True)
    valid_gz_member = gzip.compress((ep_saved.model_dump_json() + "\n").encode("utf-8"))
    cold_gz.write_bytes(valid_gz_member + b"\x1f\x8b\x08\x00truncated_corrupt_tail")
    assert len(m3.get_tier3_episodes("01_Bug_Diagnostics")) == 1
    assert len(mem_mod.HybridRRFSearchEngine(k_rrf=60.0).search("pydantic alpha", episodes=[ep_saved], top_k=3)) == 1

    eng_def = rsi_mod.RSIDefectVector(tests_passed=10, tests_failed=0, tests_total=10)
    eng_rec = rsi_mod.RSIIterationRecord(
        session_id="S-COV", iteration=1, defects=eng_def, delta_k=0,
        fitness_q=100.0, state_hash="a" * 64, verdict="CONVERGED_OPTIMAL",
    )
    ipc_rec = ipc_mod.RSIIterationRecord(
        session_id="S-COV", iteration=1, defects=eng_def, delta_k=0,
        fitness_q=100.0, state_hash="a" * 64, verdict="CONVERGED_OPTIMAL",
    )
    assert len(ipc_mod.RSISessionReport(session_id="S-COV", history=[eng_rec, ipc_rec, ipc_rec.model_dump()]).history) == 3

    t_led_f = tmp_path / "dag_ledger.jsonl"
    tl1 = led_mod.TaskLedger(t_led_f)
    tl1.add_task("T1", "BUILD", "NK-Builder-Agent")
    with pytest.raises(ValueError):
        tl1.add_task("T1", "BUILD", "NK-Builder-Agent")
    with pytest.raises(ValueError):
        tl1.add_task("T2", "BUILD", "NK-Builder-Agent", parent_ids=["NOPE"])
    assert "T1" in led_mod.TaskLedger(t_led_f)._nodes
    stale_lk = tmp_path / "stale.lock"
    stale_lk.write_text(json.dumps({"pid": 99999999, "timestamp": 1.0}), encoding="utf-8")
    with led_mod.PIDFileLock(stale_lk, stale_timeout_sec=0.01) as plk:
        assert plk.acquired is True


@pytest.mark.fast
def test_carbon_core_ast_guard_expr_eval_and_cli_gates(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica SAST constant/truthy/namespace obfuscation e rami CLI fail-closed AST Guard."""
    tok_pyt = "PY" + "TEST_CURRENT_TEST"
    expr_py = (
        "import sys\nPREF = 'PY'\nSUFF = 'TEST_CURRENT_TEST'\n"
        "def sample(obj: object) -> int:\n"
        "    s1 = 'abcdef'[1:4:1]\n    s2 = ''.join(['a', 'b'])\n    s3 = ''.join(reversed('cba'))\n    s4 = chr(65)\n"
        f"    c_cat = PREF + SUFF\n    c_fstr = f'{{PREF}}{tok_pyt[2:]}'\n"
        "    b1 = (not []) and (not {}) and bool(-1) and bool(~0)\n    b2 = (False or True) and (1 if True else 0)\n"
        "    ns = getattr(obj, '__builtins__', None)\n    m_p = sys.modules['pytest']\n"
        "    return len(s1 + s2 + s3 + s4 + c_cat + c_fstr) + int(bool(b1 and b2)) + int(ns is None and m_p is None)\n"
    )
    rep = guard_mod.ASTGuardValidator.validate_code_edit("", expr_py, target_file="src_app/mod_sast.py")
    assert rep.is_valid is False and len(rep.violations) >= 3

    out_err = tmp_path / "ag_missing.json"
    assert _call_main(
        guard_mod, ["--stage-dir", str(tmp_path / "no_stage_dir"), "--output-json", str(out_err), "--json"], monkeypatch
    ) == 2
    assert out_err.is_file()
    not_a_dir = tmp_path / "single.py"
    not_a_dir.write_text("X = 1\n", encoding="utf-8")
    assert _call_main(guard_mod, ["--stage-dir", str(not_a_dir)], monkeypatch) == 2
    assert _call_main(guard_mod, ["--target", "   "], monkeypatch) == 2
    clean_dir = tmp_path / "clean_scan_dir"
    clean_dir.mkdir()
    (clean_dir / "ok_mod.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    assert _call_main(guard_mod, [str(clean_dir)], monkeypatch) == 0


@pytest.mark.fast
def test_carbon_inprocess_migrated_unit_edges(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
    session_router: Any,
    session_indexer: Any,
    isolated_nk_env: Path,
) -> None:
    """Consolida verifica Preflight dirty check & auto-fix su workspace popolato."""
    del capsys, session_router, session_indexer, isolated_nk_env
    ws = tmp_path / "dirty_ws"
    for p in (".commit_ready", "handoff/stashes", "nk_tracking/reports_and_briefs", "nk_tracking/anchor", "scripts/__pycache__", ".wal", "nk_genome"):
        (ws / p).mkdir(parents=True)
    (ws / "handoff" / "stashes" / "old.patch").write_text("diff", encoding="utf-8")
    (ws / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    stale_wal = ws / ".wal" / "stale_tx.wal"
    stale_wal.write_text('{"state": "COMMITTED"}', encoding="utf-8")
    old_ts = time.time() - 3600.0
    os.utime(stale_wal, (old_ts, old_ts))
    rep_dir = ws / "nk_tracking" / "reports_and_briefs"
    (rep_dir / "FORENSIC_INSPECTOR_temp.md").write_text("tmp", encoding="utf-8")
    for idx in range(5):
        (rep_dir / f"TAS_Report_20261110_0{idx}.md").write_text(f"# Report {idx}\n", encoding="utf-8")
    (ws / "nk_tracking" / "old_state.json.bak").write_text("{}", encoding="utf-8")
    (ws / "session_anchor.jsonl").write_text("{}\n", encoding="utf-8")
    (ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"skills_index": {"S1": {}, "S2": {}}}), encoding="utf-8")
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"_version": "6.0.0-Carbon", "metrics": {"skills_audited": {"value": 2}, "crv_macro_phases": {"value": 4}, "unit_tests_pass_pct": {"value": 100.0}}}),
        encoding="utf-8",
    )
    checker_ro = pre_mod.PreflightHealthChecker(workspace_root=ws)
    assert len(checker_ro.run_full_check(auto_fix=False)["issues_detected"]) >= 1
    rc_pf, out_pf, _ = _call_main_captured(pre_mod, ["--root", str(ws), "--json"])
    assert rc_pf == 0 and json.loads(out_pf)["status"] in ("PASS", "HEALTHY_GREEN")
    assert not (ws / ".commit_ready").exists() and not (rep_dir / "FORENSIC_INSPECTOR_temp.md").exists()
    assert len(list(rep_dir.glob("TAS_Report_*.md"))) <= 3


@pytest.mark.fast
def test_carbon_core_rsi_ste100_numeric_bounds_ab_strict(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica RSI fallback STE100, _numeric_bounds_disjoint, ab_benchmark e strict_verify."""
    good_md = (
        "---\ntitle: 'Titolo lungo oltre venti parole ignorato nel blocco YAML frontmatter iniziale'\n---\n"
        "Questa frase tecnica attiva usa esattamente otto parole.\n\n"
        "```python\nval = 'riga — con trattino spaziato e venticinque parole ignorata'\n```\n"
    )
    assert rsi_mod._fallback_verify_ste100_compliance(good_md, max_sentence_words=20)["passed"] is True
    bad_md = (
        "Questa frase contiene un trattino — spaziato vietato.\n"
        "Questa seconda frase supera decisamente il limite massimo consentito di venti parole totali "
        "aggiungendo termini ridondanti e prolissi nella documentazione tecnica italiana corrente.\n"
    )
    res_bad = rsi_mod._fallback_verify_ste100_compliance(bad_md, max_sentence_words=20)
    assert res_bad["passed"] is False and res_bad["violations_count"] >= 2
    nb = rsi_mod._numeric_bounds_disjoint
    for case_args in (("LT", 5.0, "GTE", 5.0), ("LTE", 4.0, "GT", 4.0), ("GT", 8.0, "LT", 3.0),
                      ("EQ", 3.0, "GT", 3.0), ("EQ", 3.0, "GTE", 5.0), ("EQ", 5.0, "LT", 3.0),
                      ("EQ", 5.0, "LTE", 3.0), ("GT", 3.0, "EQ", 2.0)):
        assert nb(*case_args) is True
    assert nb("LTE", 10.0, "GTE", 5.0) is False

    empty_suite = tmp_path / "empty_tasks.json"
    empty_suite.write_text('{"tasks": []}', encoding="utf-8")
    assert rsi_mod.run_ab_benchmark(workspace_root=tmp_path, suite_path=empty_suite)["passed"] is False

    ab_ws = tmp_path / "valid_ab"
    (ab_ws / "scripts").mkdir(parents=True)
    (ab_ws / "nk_tracking" / "benchmark_suite").mkdir(parents=True)
    (ab_ws / "scripts" / "core_mod.py").write_text("X = 1\n", encoding="utf-8")
    tasks_payload = {
        "tasks": [
            {"task_id": f"AB-{idx:02d}", "module": "scripts/core_mod.py", "source_url": "https://docs.python.org/3/library/ast.html",
             "evidence_quote": "Abstract Syntax Trees deterministic parsing reference.", "expected": True}
            for idx in range(12)
        ]
    }
    (ab_ws / "nk_tracking" / "benchmark_suite" / "tasks_v1.json").write_text(json.dumps(tasks_payload), encoding="utf-8")
    assert _call_main(rsi_mod, ["--ab-benchmark", "--root", str(ab_ws)], monkeypatch) == 0

    strict_ws = tmp_path / "strict_ws"
    (strict_ws / ".agents").mkdir(parents=True)
    (strict_ws / ".staging").mkdir(parents=True)
    (strict_ws / ".agents" / "AGENTS.md").write_text("# Regola Breve\nUsa frasi attive.\n", encoding="utf-8")
    (strict_ws / ".staging" / "note.md").write_text("# Staged\nFrase conforme e chiara.\n", encoding="utf-8")
    sast_f = tmp_path / "sast_rep.json"
    sast_f.write_text(json.dumps({"violations": [{"rule": "SAST-01"}]}), encoding="utf-8")
    assert _call_main(rsi_mod, ["--vibe-check", ".", "--root", str(strict_ws), "--sast-report", str(sast_f)], monkeypatch) == 1
    unmeasured = rsi_mod.RSIConvergenceEngine(workspace_root=strict_ws, root=strict_ws).verify_ecosystem(
        root_dir=strict_ws, strict_verify=True
    )
    assert unmeasured["status"] == "UNMEASURED" and unmeasured["passed"] is False


@pytest.mark.fast
def test_carbon_core_ast_guard_obfuscated_signatures_and_scope(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica SAST obfuscated constructs, firma CLI --allowed-mutations e rich scope AST Guard."""
    dunder_glob = "__" + "globals" + "__"
    subp, pck, ossys = "sub" + "process", "pick" + "le", "os." + "system"
    bad_src = (
        f"import sys, os, {pck}, {subp}\n"
        f"c = getattr(object, '{dunder_glob}')\nd = sys.modules.get('{subp}')\n"
        f"{ossys}('echo 1')\n{pck}.loads(b'x')\n{subp}.Popen('cmd', shell=True)\nflag_t = True\n"
        "if [1] and {1: 2} and (not []) and (not {}) and (-1) and (~0) and bool(1) and f'x' and flag_t:\n    pass\n"
        "if (1 if True else 0) or (0 if False else 1):\n    pass\n"
    )
    rep_g = guard_mod.ASTGuardValidator().validate_code_edit("", bad_src, target_file="src/obfuscated_mod.py")
    assert rep_g.is_valid is False and len(rep_g.violations) >= 3
    assert guard_mod.ASTGuardValidator().validate_code_edit("", "def broken(:\n    pass\n", target_file="src/syn.py").is_valid is False

    sig_ws = tmp_path / "sig_ws"
    (sig_ws / "scripts").mkdir(parents=True)
    (sig_ws / ".staging" / "scripts").mkdir(parents=True)
    pre_code = "def compute(a: int, b: int = 1) -> int:\n    return a + b\n\ndef helper_keep() -> bool:\n    return True\n"
    post_code = "def compute(a: int) -> int:\n    return a\n"
    (sig_ws / "scripts" / "api.py").write_text(pre_code, encoding="utf-8")
    (sig_ws / ".staging" / "scripts" / "api.py").write_text(post_code, encoding="utf-8")
    assert guard_mod.ASTGuardValidator().validate_code_edit(pre_code, post_code, target_file="scripts/api.py").is_valid is False
    out_j = tmp_path / "guard_out.json"
    assert _call_main(
        guard_mod, ["--stage-dir", str(sig_ws / ".staging"), "--allowed-mutations", "compute,helper_keep", "--output-json", str(out_j)], monkeypatch
    ) == 0

    rich_scope_src = (
        "GLOBAL_X = 5\nclass Sample:\n    ATTR = 1\n"
        "async def async_flow(mgr, aiter):\n    async with mgr as ctx:\n        async for item in aiter:\n            _ = item\n        else:\n            _ = ctx\n"
        "def sync_flow(mgr, seq):\n    fn = lambda v=1, *, k=2: v + k\n"
        "    try:\n        with mgr as h:\n            for el in seq:\n                _ = fn(el)\n            else:\n                _ = h\n"
        "    except ValueError as err:\n        _ = str(err)\n    undef_counter += 1\n    val = 10\n    del val\n    return val\n"
    )
    assert len(guard_mod.ASTGuardValidator().validate_code_edit("", rich_scope_src, target_file="scripts/scope_err.py").violations) >= 2


@pytest.mark.fast
def test_carbon_core_bootstrap_wal_states_hygiene_and_router_cli(
    tmp_path: Path, monkeypatch: Any, session_router: Any
) -> None:
    """Verifica WAL states, subagent transcript head, Router lint/STT/risk e CLI flags."""
    for fname, raw, exp_s in (
        ("empty.wal", b"", "CORRUPTED"), ("bin.wal", b"\xff\xfe\xfd", "CORRUPTED"),
        ("comm.wal", b'{"state": "COMMITTED"}', "COMMITTED"), ("pend.wal", b'{"state": "PREPARED"}', "VALID_PENDING"),
        ("lines.wal", b'{"state": "PREPARED"}\n{"state": "COMMITTED"}\n', "COMMITTED"),
        ("bad_lines.wal", b'{"state": "PREPARED"}\n{broken\n', "CORRUPTED"),
    ):
        p_w = tmp_path / fname
        p_w.write_bytes(raw)
        assert boot_mod.NKSessionBootstrap._inspect_wal_state(p_w) == exp_s

    dirty_proj = tmp_path / "ext_proj"
    dirty_proj.mkdir()
    (dirty_proj / "rogue.tmp").write_text("x", encoding="utf-8")
    (dirty_proj / "backup.bak").write_text("y", encoding="utf-8")
    assert "rogue.tmp" in boot_mod.NKSessionBootstrap(workspace_root=dirty_proj)._check_root_hygiene(use_fast_cache=False)["violations"]

    chk_head = boot_mod.NKSessionBootstrap._is_subagent_transcript_head
    sub_sys = b'{"step_index": 0, "source": "SYSTEM", "content": "init"}\n'
    main_head = b'{"step_index": 0, "source": "USER", "content": "avvia"}\n'
    assert chk_head(b"") is False and chk_head(sub_sys) is True
    assert chk_head(b'{"step_index": 0, "content": "<Agent System Instructions> <subagent_reminder>"}\n') is True
    assert chk_head(b'{"step_index": 0, "content": "[Message] sender=parent <env_capsule>"}\n') is True
    assert chk_head(main_head) is False and chk_head(b'{broken_json "source": "USER"\n') is False
    assert chk_head(b'{broken_json "source": "SYSTEM"\n') is True

    brain = tmp_path / "brain_ue"
    (brain / "conv_sub" / ".system_generated" / "logs").mkdir(parents=True)
    (brain / "conv_main" / ".system_generated" / "logs").mkdir(parents=True)
    (brain / "conv_sub" / ".system_generated" / "logs" / "transcript.jsonl").write_bytes(sub_sys)
    (brain / "conv_main" / ".system_generated" / "logs" / "transcript.jsonl").write_bytes(main_head)
    found_b = boot_mod.NKSessionBootstrap(workspace_root=_WORKSPACE_ROOT, conversation_id="")._find_recent_transcript(brain, max_age_seconds=300.0)
    assert found_b is not None and "conv_main" in str(found_b)
    assert _call_main(boot_mod, ["--force-full", "--json"], monkeypatch) == 0

    assert "passed" in router_mod.lint_nk_prompt("fai tutto tu velocemente senza test e usa mock ovunque", mode="mode_b")
    assert "cleaned_prompt" in session_router.normalize_voice_stt_input("avvia paitest su en key hub")
    risk_r = session_router.compute_ast_risk_score(
        "import asyncio\nclass Worker:\n    async def execute(self, items: list[int]) -> int:\n        return sum(x for x in items if x > 0)\n",
        filename="worker.py",
    )
    assert "risk_score" in risk_r and risk_r["loc"] >= 4
    assert _call_main(router_mod, ["--files", "scripts/vibe_sprint_router.py", "--changed-lines", "250", "--prompt", "Rifattorizza il parser CLI", "--no-gate", "--json"], monkeypatch) == 0
    tr_log = tmp_path / "logs_r" / "transcript.jsonl"
    tr_log.parent.mkdir()
    tr_log.write_text(json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Spiega il funzionamento del registro in sola lettura"}) + "\n", encoding="utf-8")
    assert "sola lettura" in str(router_mod._read_latest_user_input_from_transcript(str(tr_log)))
    pf_r = tmp_path / "prompt.txt"
    pf_r.write_text("Elenca i moduli del dominio DOM-01", encoding="utf-8")
    assert _call_main(router_mod, ["--test"], monkeypatch) == 0
    assert _call_main(router_mod, ["--prompt-file", str(pf_r), "--classify-prompt", "--json"], monkeypatch) == 0
    assert _call_main(router_mod, ["--capsule", "--prompt", "Elenca i moduli", "--no-gate", "--json"], monkeypatch) == 0


@pytest.mark.fast
def test_carbon_core_hook_gate_write_fasttrack_and_integrity(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica PATCH_NOTES/ADS su write-gate, _handle_fasttrack, probe e integrity init/check."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hooks_state"))
    proj_hg = tmp_path / "proj_hg"
    (proj_hg / "nk_genome").mkdir(parents=True)
    pn = proj_hg / "nk_genome" / "PATCH_NOTES.md"
    pn.write_text("# Patch Notes\n\n## v4.9.0\n- Initial entry\n", encoding="utf-8")

    rc1, out1, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj_hg)],
        stdin_text=json.dumps({"toolName": "write_file", "toolInput": {"Path": str(pn), "Content": "# Wiped\n"}}),
    )
    assert rc1 == 0 and json.loads(out1.strip().splitlines()[-1])["decision"] == "deny"

    good_pn = json.dumps({"toolName": "write_file", "toolInput": {"Path": str(pn), "Content": "# Patch Notes\n\n## v6.0.0-Carbon\n- New\n\n## v4.9.0\n- Initial entry\n"}})
    rc2, out2, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj_hg)],
        stdin_text=good_pn,
    )
    assert rc2 == 0 and json.loads(out2.strip().splitlines()[-1])["decision"] == "allow"

    rc3, out3, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--event", "PreToolUse", "--native-contract", "--shadow", "--project-root", str(proj_hg)],
        stdin_text=json.dumps({"toolName": "write_file", "toolInput": {"Path": str(proj_hg / "file.txt:hidden")}}),
    )
    assert rc3 == 0 and json.loads(out3.strip().splitlines()[-1])["decision"] == "allow"

    for exempt_nm in ("read_file", "swarm_wait", "ask_question"):
        assert hook_mod._handle_fasttrack("conv_ft", {"toolName": exempt_nm}) == {}
    res_ft: dict[str, Any] = {}
    for _ in range(13):
        res_ft = hook_mod._handle_fasttrack("conv_ft", {"toolName": "write_file"})
    assert res_ft.get("streak", 0) == 13 and "ephemeralMessage" in res_ft
    assert hook_mod._handle_fasttrack("conv_ft", {"toolName": "swarm"}) == {}
    assert hook_mod._handle_fasttrack("conv_ft", {"toolName": "write_file"}) == {}
    assert hook_mod._handle_fasttrack("conv_ft", {"toolName": "post_message"}) == {}
    assert hook_mod._handle_fasttrack("conv_ft", {"toolName": "invoke_subagent"}) == {}

    tr_pl = tmp_path / "planner_tr.jsonl"
    tr_pl.write_text('{"type":"GENERIC","source":"MODEL","content":"skip"}\n{"type":"PLANNER_RESPONSE","source":"MODEL","content":"Ultimo messaggio planner"}\n', encoding="utf-8")
    assert hook_mod._extract_last_planner_message(tr_pl) == "Ultimo messaggio planner"
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"ping": 1}'))
    assert _call_main(hook_mod, ["probe", "--event", "PreToolUse"], monkeypatch) == 0

    int_proj = tmp_path / "int_proj"
    (int_proj / "tests").mkdir(parents=True)
    (int_proj / "nk_tracking").mkdir(parents=True)
    tf_int = int_proj / "tests" / "test_core.py"
    tf_int.write_text("def test_a():\n    assert True\n", encoding="utf-8")
    (int_proj / "nk_tracking" / "oracle_lock.json").write_text('{"v": 1}', encoding="utf-8")
    assert _call_main(hook_mod, ["integrity", "--init", "--conversation-id", "c_int", "--project-root", str(int_proj)], monkeypatch) == 0
    tf_int.write_text("def test_a():\n    assert True  # tampered\n", encoding="utf-8")
    assert _call_main(hook_mod, ["integrity", "--check", "--conversation-id", "c_int", "--project-root", str(int_proj)], monkeypatch) == 1


@pytest.mark.fast
def test_carbon_core_2pc_wal_replay_mutex_and_ratchet_fail(tmp_path: Path) -> None:
    """Verifica WAL replay/abort/skip, mutex rientrante Win32 e blocco ratchet su promote."""
    wal_dir = tmp_path / ".wal"
    wal_dir.mkdir(parents=True)
    wal_mgr = w2pc_mod.WriteAheadLogManager(wal_dir=wal_dir)
    eng_2pc = w2pc_mod.TwoPhaseCommitEngine(wal_manager=wal_mgr)
    dst_2pc = tmp_path / "committed_doc.txt"
    assert eng_2pc.commit(eng_2pc.prepare(dst_2pc, "contenuto_atomico_carbon")).verdict == "COMMIT"

    wal_dir.mkdir(parents=True, exist_ok=True)
    stg_c, stg_p, stg_a = tmp_path / "stg_commit.tmp", tmp_path / "stg_stale.tmp", tmp_path / "stg_abort.tmp"
    stg_c.write_bytes(b"REPLAY_OK")
    stg_p.write_bytes(b"STALE")
    stg_a.write_bytes(b"ABORT")
    tgt_c = tmp_path / "replayed.txt"
    (wal_dir / "tx_comm.wal").write_text(json.dumps({"tx_id": "tx_c", "target_path": str(tgt_c), "staging_path": str(stg_c), "payload_sha256": hashlib.sha256(b"REPLAY_OK").hexdigest(), "state": "COMMITTED", "timestamp_utc": time.time() - 60.0}), encoding="utf-8")
    (wal_dir / "tx_stale.wal").write_text(json.dumps({"tx_id": "tx_ps", "target_path": str(tmp_path / "t_ps.txt"), "staging_path": str(stg_p), "state": "PREPARED", "timestamp_utc": time.time() - 120.0}), encoding="utf-8")
    (wal_dir / "tx_fresh.wal").write_text(json.dumps({"tx_id": "tx_pf", "target_path": str(tmp_path / "t_pf.txt"), "state": "PREPARED", "timestamp_utc": time.time() + 60.0}), encoding="utf-8")
    (wal_dir / "tx_abort.wal").write_text(json.dumps({"tx_id": "tx_ab", "target_path": str(tmp_path / "t_ab.txt"), "staging_path": str(stg_a), "state": "ABORTED", "timestamp_utc": time.time() - 30.0}), encoding="utf-8")
    actions = {r.get("action") for r in wal_mgr.recover(tmp_path, stale_age_sec=5.0)}
    assert {"REPLAYED_COMMIT", "ABORTED_STALE", "SKIPPED_ACTIVE", "PURGED_ABORTED"}.issubset(actions) and tgt_c.read_bytes() == b"REPLAY_OK"

    m_name = w2pc_mod.get_repo_batch_mutex_name(tmp_path)
    with w2pc_mod.Win32NamedMutex(m_name, timeout_ms=2000), w2pc_mod.Win32NamedMutex(m_name, timeout_ms=2000):
        pass

    r_repo = tmp_path / "ratchet_repo"
    (r_repo / "nk_tracking").mkdir(parents=True)
    (r_repo / ".staging" / "nk_tracking").mkdir(parents=True)
    (r_repo / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_total": {"value": 100, "direction": "higher_is_better"}}}), encoding="utf-8")
    (r_repo / ".staging" / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_total": {"value": 50, "direction": "higher_is_better"}}}), encoding="utf-8")
    with pytest.raises(w2pc_mod.TwoPhaseCommitError):
        w2pc_mod.promote_staging_to_production(repo_root=r_repo, verify_baseline=True, allow_governance_override=False)


@pytest.mark.fast
def test_carbon_core_dast_dom_transcript_and_sbfl_bridge(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre DAST shadow without pytest, L3 DOM deltas, transcript CLI e SBFL bridge."""
    mini_dast = tmp_path / "empty_tests_hub"
    for p in ("scripts", "tests", ".staging/scripts"):
        (mini_dast / p).mkdir(parents=True)
    (mini_dast / "scripts" / "dead.py").write_text("X = 1\n", encoding="utf-8")
    (mini_dast / ".staging" / "scripts" / "ok.py").write_text("Y = 2\n", encoding="utf-8")
    (mini_dast / ".staging" / ".deleted_files.json").write_text(json.dumps(["scripts/dead.py"]), encoding="utf-8")
    assert dast_mod.run_staging_shadow_verification(repo_root=mini_dast, run_pytest=False, run_ast_guard=False, profile="builder")["sandbox_cleaned"] is True

    rep_dom = l3_mod.DOMOracleEvaluator().evaluate_deltas(
        "<section id='main' class='card'><h1>Titolo</h1><table><thead><tr><th>A<th>B<tbody><tr><td>1<td>2</table><dl><dt>K<dd>V</dl><span>ExtraExp</span></section>",
        "<section id='main' class='card-diff'><h2>Titolo Diverso</h2><table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table><dl><dt>K</dt><dd>V</dd></dl><div>AddedNode</div></section>",
    )
    assert rep_dom.verdict == "FAIL" and "ATTRIBUTE_MISMATCH" in {d.change_type for d in rep_dom.deltas}

    ears_txt = "WHEN l'utente invia un comando valido, THE Router SHALL classificare il rischio in 50ms.\nIl sistema forse dovrebbe fare qualcosa di vago.\n"
    assert _call_main(tr_mod, ["lint-ears", "--text", ears_txt, "--json"], monkeypatch) == 0
    assert _call_main(tr_mod, ["lint-ste100", "--text", "Frase tecnica conforme e attiva.", "--json"], monkeypatch) == 0
    assert _call_main(tr_mod, ["lint-prompt", "--text", "Aggiorna .staging/scripts/x.py e lancia pytest.", "--json"], monkeypatch) == 0
    rep_md = tmp_path / "grounded_report.md"
    rep_md.write_text("Verifica completata su `scripts/nk_transcript_tools.py`.\n", encoding="utf-8")
    assert _call_main(tr_mod, ["verify-grounding", "--report", str(rep_md), "--manifest", str(_WORKSPACE_ROOT / "nk_genome" / "nk_registry_manifest.json"), "--json"], monkeypatch) == 0

    bad_tr = tmp_path / "poll_transcript.jsonl"
    bad_tr.write_text("\n".join(json.dumps({"step_index": i, "source": "MODEL", "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "command_status", "arguments": {"TaskId": "t1"}}]}) for i in range(5)) + "\n", encoding="utf-8")
    comp_out = tr_mod.analyze_compliance(bad_tr)
    assert comp_out["passed"] is True and comp_out["polling_list_calls"] == 0
    tr_comp = tmp_path / "non_compliant.jsonl"
    tr_comp.write_text("\n".join(json.dumps(e) for e in [{"step_index": 0, "type": "USER_INPUT", "content": "modifica subito il file"}, {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "Fatto: 100/100 PASS e CONVERGED_OPTIMAL", "tool_calls": [{"name": "write_file", "arguments": {"Path": "scripts/direct_prod.py"}}]}]) + "\n", encoding="utf-8")
    aud_comp = comp_mod.NKComplianceChecker().audit_transcript(tr_comp)
    assert "scores" in aud_comp and aud_comp["status"] == "FAIL"

    p1 = [sbfl_mod.CoverageRecord(test_id="T_stable", passed=False, executed_statements=["a.py:10"]), sbfl_mod.CoverageRecord(test_id="T_flaky", passed=False, executed_statements=["a.py:20"])]
    p2 = [sbfl_mod.CoverageRecord(test_id="T_stable", passed=False, executed_statements=["a.py:10"]), sbfl_mod.CoverageRecord(test_id="T_flaky", passed=True, executed_statements=["a.py:20"])]
    assert "T_flaky" in sbfl_mod.tri_pass_voting_filter([p1, p2, p2]).flaky_test_ids
    br_s = bridge_mod.SBFLPytestBridge(cwd=_WORKSPACE_ROOT)
    sum_b = br_s.parse_pytest_output("tests/test_alpha.py::test_ok PASSED\ntests/test_alpha.py::test_boom FAILED\ng:/Il mio Drive/Antigravity/NK_Hub/scripts/sample_mod.py:42: AssertionError: err\n1 failed, 1 passed in 0.12s\n", "", exit_code=1, duration_sec=0.12)
    loc_b = br_s.extract_failure_location(sum_b, target_file_hint="sample_mod.py", passed_line_counts={("sample_mod.py", 42): 1})
    assert loc_b is not None and loc_b.line_number == 42 and len(json.dumps(loc_b.to_compact_payload(), separators=(",", ":"))) < 320 and bridge_mod.compute_ochiai(0, 0, 0) == 0.0


@pytest.mark.integration
def test_carbon_core_qbm_live_pytest_and_oracle_coherence(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica measure_live_pytest_metrics, CLI check/update QBM e coerenza oracle_lock."""
    qb_ws = tmp_path / "qb_ws"
    (qb_ws / "nk_tracking").mkdir(parents=True)
    (qb_ws / "tests").mkdir(parents=True)
    (qb_ws / "tests" / "test_k.py").write_text("def test_k():\n    assert True\n", encoding="utf-8")
    qb_p = qb_ws / "nk_tracking" / "quality_baseline.json"
    assert tr_mod.handle_oracle_lock("freeze", qb_ws / "tests", qb_ws / "nk_tracking" / "oracle_lock.json")[1] == 0
    with monkeypatch.context() as _mp_noplug:
        _mp_noplug.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
        assert base_mod.measure_live_pytest_metrics(qb_ws)["unit_tests_passed"] == 1
    assert _call_main(base_mod, ["check", str(qb_p), json.dumps({"unit_tests_total": 95, "unit_tests_passed": 95, "unit_tests_pass_pct": 100.0})], monkeypatch) == 0
    assert _call_main(base_mod, ["update", str(qb_p), json.dumps({"unit_tests_total": 105, "unit_tests_passed": 105, "unit_tests_pass_pct": 100.0})], monkeypatch) == 0
    assert _call_main(base_mod, ["check", str(qb_p), json.dumps({"unit_tests_total": 80, "unit_tests_passed": 80, "unit_tests_pass_pct": 100.0})], monkeypatch) == 1
    assert base_mod._verify_oracle_lock_coherence(str(qb_p)) == []


@pytest.mark.fast
def test_carbon_core_repomap_handoff_ledger_scaffolder_and_memory(
    tmp_path: Path, monkeypatch: Any, session_indexer: Any
) -> None:
    """Verifica RepoMap budget, intent brief, TaskLedger cycle, scaffolder, sentry, lookup e mem CLI."""
    map_b_repo = tmp_path / "map_budget_repo"
    (map_b_repo / "scripts").mkdir(parents=True)
    for idx in range(4):
        (map_b_repo / "scripts" / f"svc_{idx}.py").write_text(
            f"def dec(fn):\n    return fn\n\nclass Worker{idx}:\n    @dec\n    async def process(self, pos_only: int, /, *args: str, flag: bool = True, **kw: float) -> int:\n        return len(args)\n",
            encoding="utf-8",
        )
    for m_name in ("mode_a", "mode_b", "mode_c", "argon_mode_a"):
        assert map_mod.GraduatedSkillAdapter.get_token_budget(m_name) >= 256
    assert map_mod.RepoMapGenerator.generate(map_b_repo, config=map_mod.RepoMapConfig(max_tokens=128)).files_scanned == 4
    assert map_mod.query_symbol_subgraph("non_existent_symbol_999", root=map_b_repo)["found"] is False

    hand_ws = tmp_path / "hand_ws"
    (hand_ws / "nk_tracking" / "reports_and_briefs").mkdir(parents=True)
    assert Path(hand_mod.persist_intent_brief("IB-20261111-TEST01", "Completa validazione modulo.", project_root=str(hand_ws))).exists()
    tl_c = led_mod.TaskLedger(tmp_path / "cyc.jsonl")
    tl_c.add_task("A", "step_a", "Ag")
    tl_c.add_task("B", "step_b", "Ag", parent_ids=["A"])
    tl_c._nodes["A"] = tl_c._nodes["A"].model_copy(update={"parent_ids": ["B"]})
    assert tl_c.verify_dag()[0] is False
    assert _call_main(cache_mod, ["--health"], monkeypatch) == 0
    assert clean_mod._is_subpath_str("", "") is False and clean_mod._is_subpath_str("c:\\ws\\sub", "c:\\ws") is True
    assert clean_mod._is_subpath_str("c:\\ws_other", "c:\\ws") is False

    ext_root = tmp_path / "NK_External_Projects"
    assert _call_main(scaf_mod, ["--name", "ValidIsoApp", "--target", str(ext_root / "ValidIsoApp"), "--json"], monkeypatch) == 0
    assert (ext_root / "ValidIsoApp" / "nk_genome").exists() and hasattr(inv_mod, "InvisibleHealingLoop")
    big_tr = tmp_path / "big_ctx.jsonl"
    big_tr.write_text('{"step_index": 0, "content": "' + ("A" * 4000) + '"}\n', encoding="utf-8")
    rc_s, out_s, _ = _call_main_captured(sent_mod, ["--transcript", str(big_tr), "--profile", "standard", "--actual-context-tokens", "195000", "--json"])
    st_s = json.loads(out_s)["status"]
    assert rc_s == (0 if st_s in ("GREEN", "YELLOW", "WARN") else 1)

    for q, exp_found in (("rsi", True), ("sbfl ochiai causa radice", True), ("non_existent_query_xyz_98765", False)):
        assert session_indexer.lookup(q)["found"] is exp_found
    legacy_md = "# Legacy Skill\n<yaml_metadata_card>\nname: NK-Legacy\ndomain_id: DOM-02\ntools:\n  - read_file\n</yaml_metadata_card>\n"
    assert session_indexer._parse_skill_metadata(legacy_md).get("domain_id") == "DOM-02"
    mem_h = tmp_path / "mem_human"
    assert _call_main(mem_mod, ["--base-dir", str(mem_h), "--append", "--domain", "ARCH", "--title", "Architettura Modulare", "--content", "Usa interfacce tipizzate Pydantic v2 per ogni contratto IPC."], monkeypatch) == 0
    assert _call_main(mem_mod, ["--base-dir", str(mem_h), "--recall", "--query", "contratti Pydantic IPC"], monkeypatch) == 0


@pytest.mark.fast
def test_carbon_inprocess_preflight_ssot_retention_and_cli_branches(tmp_path: Path) -> None:
    """Copre rami SSOT rotto di preflight_health_check: tombstone, duplicate rules e retention."""
    bad_ws = tmp_path / "ssot_bad"
    for p in (".agents/skills/S1", ".agents/skills/S2", ".agents/skills/DelSkill", ".staging/.agents/skills/S3",
              "nk_tracking/handoff/stashes", "nk_tracking/reports_and_briefs/sub", "nk_genome"):
        (bad_ws / p).mkdir(parents=True)
    (bad_ws / ".staging" / ".deleted_files.json").write_text(json.dumps([".agents/skills/DelSkill/SKILL.md"]), encoding="utf-8")
    (bad_ws / ".agents" / "AGENTS.md").write_text("# Nexus Keystone\n## [RULE-01] Regola A\n## [RULE-01] Duplicata\n", encoding="utf-8")
    (bad_ws / ".agents" / "skills" / "S1" / "SKILL.md").write_text('---\nname: S1\nversion: "0.0.1-Old"\n---\nUsa [RULE-01] e [RULE-99].\n', encoding="utf-8")
    (bad_ws / ".agents" / "skills" / "S2" / "SKILL.md").write_text("---\nname: S2\n---\nSenza versione.\n", encoding="utf-8")
    (bad_ws / ".agents" / "skills" / "DelSkill" / "SKILL.md").write_text("---\nname: Del\n---\nCancellata.\n", encoding="utf-8")
    (bad_ws / ".staging" / ".agents" / "skills" / "S3" / "SKILL.md").write_text("---\nname: S3\n---\nStaged senza versione.\n", encoding="utf-8")
    (bad_ws / "nk_tracking" / "quality_baseline.json").write_text("{corrupt_json", encoding="utf-8")
    (bad_ws / "nk_genome" / "nk_registry_manifest.json").write_text("{corrupt_manifest", encoding="utf-8")
    (bad_ws / "nk_tracking" / "handoff" / "stashes" / "orphan.patch").write_text("diff\n", encoding="utf-8")
    (bad_ws / "nk_tracking" / "reports_and_briefs" / "FORENSIC_INSPECTOR_1.md").write_text("tmp", encoding="utf-8")
    (bad_ws / "nk_tracking" / "reports_and_briefs" / "sub" / "IB-20261115-ABCD.md").write_text("ib", encoding="utf-8")
    for idx_t in range(4):
        (bad_ws / "nk_tracking" / "reports_and_briefs" / f"TAS_Report_{idx_t}.md").write_text("rep", encoding="utf-8")
    (bad_ws / "nk_tracking" / "old.bak").write_text("bak", encoding="utf-8")

    ph_bad = pre_mod.PreflightHealthChecker(workspace_root=bad_ws)
    ssot_bad = ph_bad._check_ssot_governance()
    assert ssot_bad["passed"] is False and ssot_bad["duplicate_rule_ids"] == ["RULE-01"]
    assert "RULE-99" in ssot_bad["orphan_rule_refs"] and len(ssot_bad["version_mismatches"]) >= 4
    assert ph_bad._check_staging_and_temp(auto_fix=False)["passed"] is False
    assert ph_bad._check_report_retention(auto_fix=False, max_per_target=2)["passed"] is False
    assert ph_bad._check_baseline_alignment()["passed"] is False
    assert ph_bad._check_staging_and_temp(auto_fix=True)["passed"] is True
    assert ph_bad._check_report_retention(auto_fix=True, max_per_target=2)["pruned_count"] >= 3


@pytest.mark.fast
def test_carbon_core_preflight_missing_and_valid_ssot_cli(tmp_path: Path) -> None:
    """Verifica missing manifest/baseline non-dict, SSOT valido e preflight CLI --check-only."""
    ver = str(pre_mod.VERSION)
    miss_ws = tmp_path / "ssot_missing"
    (miss_ws / ".agents" / "skills" / "S1").mkdir(parents=True)
    (miss_ws / ".agents" / "AGENTS.md").write_text(f"# Nexus Keystone v{ver}\n## [RULE-01] Base\n", encoding="utf-8")
    (miss_ws / ".agents" / "skills" / "S1" / "SKILL.md").write_text(f'---\nname: S1\nversion: "{ver}"\n---\nBody [RULE-01].\n', encoding="utf-8")
    (miss_ws / "nk_tracking").mkdir(parents=True)
    assert pre_mod.PreflightHealthChecker(workspace_root=miss_ws)._check_ssot_governance()["passed"] is False
    (miss_ws / "nk_tracking" / "quality_baseline.json").write_text("[1, 2]", encoding="utf-8")
    assert pre_mod.PreflightHealthChecker(workspace_root=miss_ws)._check_baseline_alignment()["passed"] is False

    (miss_ws / "nk_genome").mkdir(parents=True)
    (miss_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"version": ver, "summary": {"total_skills": 1}}), encoding="utf-8")
    (miss_ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"_version": ver, "metrics": {"skills_audited": {"value": 1}, "crv_macro_phases": {"value": 4}, "unit_tests_pass_pct": {"value": 100.0}}}),
        encoding="utf-8",
    )
    (miss_ws / ".wal").mkdir(parents=True)
    assert pre_mod.PreflightHealthChecker._is_committed_wal(miss_ws / ".wal" / "missing.wal") is False
    assert _call_main_captured(pre_mod, ["--root", str(miss_ws), "--check-only", "--json"])[0] == 1
    assert _call_main_captured(pre_mod, ["--root", str(miss_ws), "--json"])[0] == 0
    assert _call_main_captured(pre_mod, ["--root", str(miss_ws), "--check-only", "--json"])[0] == 0


@pytest.mark.fast
def test_carbon_inprocess_2pc_promoter_io_sbfl_and_qbm_cli_branches(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Copre promoter (_prune_deleted_parent_dirs/rollback) e io_and_paths retry/reparse."""
    del isolated_nk_env
    from _internal.win32_2pc_engine import io_and_paths as iop

    prom_ws = tmp_path / "prom_prune"
    (prom_ws / "scripts" / "deep" / "sub").mkdir(parents=True)
    (prom_ws / ".staging" / "scripts").mkdir(parents=True)
    (prom_ws / "nk_tracking").mkdir(parents=True)
    (prom_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"unit_tests_total": 93, "unit_tests_passed": 93, "pass_rate_pct": 100.0}), encoding="utf-8")
    (prom_ws / "scripts" / "deep" / "sub" / "dead.py").write_text("DEAD = 1\n", encoding="utf-8")
    (prom_ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["scripts/deep/sub/dead.py"]), encoding="utf-8")
    (prom_ws / ".staging" / "scripts" / "live_mod.py").write_text("LIVE = 1\n", encoding="utf-8")
    pr_ok = w2pc_mod.promote_staging_to_production(repo_root=prom_ws, verify_baseline=False)
    assert pr_ok["status"] == "SUCCESS" and (prom_ws / "scripts" / "live_mod.py").is_file()
    assert not (prom_ws / "scripts" / "deep").exists() and (prom_ws / "scripts").is_dir()

    rb_ws = tmp_path / "prom_rollback"
    for p in (".staging/scripts", "scripts", "nk_tracking"):
        (rb_ws / p).mkdir(parents=True)
    (rb_ws / ".staging" / "scripts" / "f1.py").write_text("A = 1\n", encoding="utf-8")
    with monkeypatch.context() as mp_rb:
        def _fail_atomic(_self: Any, _target: Any, _data: Any) -> Any:
            raise OSError("simulated_disk_full")

        mp_rb.setattr(w2pc_mod.TwoPhaseCommitEngine, "atomic_write", _fail_atomic)
        with pytest.raises(w2pc_mod.TwoPhaseCommitError):
            w2pc_mod.promote_staging_to_production(repo_root=rb_ws, verify_baseline=False)

    src_r, dst_r = tmp_path / "rep_src.txt", tmp_path / "rep_dst.txt"
    src_r.write_text("new", encoding="utf-8")
    orig_replace, attempts_rep = os.replace, {"n": 0}

    def _flaky_replace(s: Any, d: Any) -> None:
        attempts_rep["n"] += 1
        if attempts_rep["n"] == 1:
            err = PermissionError(13, "busy")
            err.winerror = 5
            raise err
        orig_replace(s, d)

    with monkeypatch.context() as mp_io:
        mp_io.setattr(os, "replace", _flaky_replace)
        iop._replace_with_retry(src_r, dst_r, retries=3, delay_sec=0.001)
    assert dst_r.read_text(encoding="utf-8") == "new" and attempts_rep["n"] == 2
    assert iop._resolve_repo_root(None).is_dir()
    iop._assert_no_external_reparse(dst_r, tmp_path.resolve(), stop_at=tmp_path.resolve())


@pytest.mark.integration
def test_carbon_core_sbfl_matrix_and_bridge_subprocess_cli(tmp_path: Path) -> None:
    """Copre sbfl_engine matrix exceptions/CLI e sbfl_pytest_bridge subprocess CLI."""
    long_loc = sbfl_mod.SBFLLocation(
        file_path="pkg/deep_mod.py", line_number=12, suspiciousness=0.95,
        error_type="RuntimeError", error_message="Errore " + ("x" * 160),
        failing_line_content="result = compute_value(" + ("a, " * 55) + ")",
    )
    assert len(long_loc.render_payload_json()) < 400
    for bad_args in ((["a"], ["t1", "t2"], [[1]], [1]), (["a"], ["t1"], [[1, 0]], [1]), (["a"], ["t1"], [[2]], [1]), (["a"], ["t1"], [[1]], [2])):
        with pytest.raises(ValueError):
            sbfl_mod.CoverageMatrix(*bad_args)
    assert sbfl_mod.SBFLEngine.extract_from_exception(ValueError("bare_exc")).file_path == "unknown"
    rec_json = tmp_path / "sbfl_recs.json"
    rec_json.write_text(json.dumps([{"test_id": "t1", "passed": False, "executed_statements": ["x.py:5"]}]), encoding="utf-8")
    assert _call_main_captured(sbfl_mod, ["--records-file", str(rec_json), "--json"])[0] == 0

    src_m = tmp_path / "m.py"
    src_m.write_text("def boom():\n    return 1 / 0\n", encoding="utf-8")
    br_inst = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    sum_fail = br_inst.parse_pytest_output(
        "FAILED m.py::test_boom\nm.py:2: in boom\n>   return 1 / 0\nE   ZeroDivisionError: division by zero\n", "", 1, 0.02
    )
    loc_fail = br_inst.extract_failure_location(sum_fail, target_file_hint="m.py", passed_line_counts={("m.py", 2): 1})
    assert loc_fail is not None and loc_fail.line_number == 2
    rc_ok, out_ok, _ = _call_main_captured(bridge_mod, ["--test-cmd", f'"{sys.executable}" -B -c "print(\'1 passed in 0.01s\')"', "--cwd", str(tmp_path)])
    assert rc_ok == 0 and "PASSED" in out_ok
    rc_f, out_f, _ = _call_main_captured(
        bridge_mod,
        ["--test-cmd", f'"{sys.executable}" -B -c "import sys; print(\'FAILED m.py::t1\\nm.py:2: in boom\\nE   AssertionError: x\'); sys.exit(1)"',
         "--target-file", "m.py", "--cwd", str(tmp_path)],
    )
    assert rc_f == 1 and "SBFL-OCHIAI" in out_f


@pytest.mark.integration
def test_carbon_core_qbm_cli_check_update_and_recalibrate_live(tmp_path: Path) -> None:
    """Copre quality_baseline_manager CLI check/update/recalibrate --live e allow_ratchet_down."""
    qb_dir = tmp_path / "qbm_cli"
    (qb_dir / "nk_tracking").mkdir(parents=True)
    bl_f = qb_dir / "nk_tracking" / "quality_baseline.json"
    bl_f.write_text(
        json.dumps({"_version": "6.4.0-Carbon", "unit_tests_total": 93, "metrics": {
            "unit_tests_total": {"value": 93, "direction": "higher_is_better"},
            "unit_tests_passed": {"value": 93, "direction": "higher_is_better"},
            "unit_tests_pass_pct": {"value": 100.0, "direction": "higher_is_better"},
            "skills_audited": {"value": 16, "direction": "higher_is_better"},
        }}),
        encoding="utf-8",
    )
    assert _call_main_captured(base_mod, ["check", "--file", str(bl_f), "--metrics", "{bad"])[0] == 1
    assert _call_main_captured(base_mod, ["check", "--file", str(bl_f)])[0] == 1
    assert _call_main_captured(
        base_mod, ["check", "--file", str(bl_f), "--metrics", '{"unit_tests_total": 93, "unit_tests_passed": 93, "unit_tests_pass_pct": 100.0}']
    )[0] == 0
    upd_payload = json.dumps({"_recalibrated": True, "unit_tests_total": 130, "unit_tests_passed": 130, "unit_tests_pass_pct": 100.0, "pass_rate_pct": 100.0})
    assert _call_main_captured(base_mod, ["update", "--file", str(bl_f), "--update", upd_payload])[0] == 0
    assert "_recalibrated" not in json.loads(bl_f.read_text(encoding="utf-8"))
    assert _call_main_captured(base_mod, ["recalibrate", "--file", str(bl_f), "--live"])[0] == 1
    assert base_mod.check_baseline_compliance(str(bl_f), {"skills_audited": 14, "unit_tests_pass_pct": 100.0}, allow_ratchet_down=True)["verdict"] == "PASS"


@pytest.mark.fast
def test_carbon_core_rsi_bav_edges_and_snapshot_rollback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre _internal.rsi_convergence_engine.benchmark_and_vibe ed HealingSnapshotManager."""
    from _internal.nk_common import io as _common_io_cov
    bav_mod = importlib.import_module("_internal.rsi_convergence_engine.benchmark_and_vibe")
    vibe_ws = tmp_path / "vibe_bav_ws"
    (vibe_ws / "scripts").mkdir(parents=True, exist_ok=True)
    rsi_eng = rsi_mod.RSIConvergenceEngine(workspace_root=vibe_ws)
    assert bav_mod.run_vibe_check_impl(rsi_eng, vibe_ws / "missing_target")["passed"] is False
    assert bav_mod.run_benchmark_suite_impl(rsi_eng, vibe_ws / "missing_suite", root_dir=vibe_ws)["passed"] is False

    bad_py = vibe_ws / "bad_syntax.py"
    bad_py.write_text("def broken(:\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(bav_mod, "get_ast_guard_validator", lambda: None)
        assert bav_mod.run_vibe_check_impl(rsi_eng, bad_py)["passed"] is False

    ok_py = vibe_ws / "ok_single.py"
    ok_py.write_text('"""Ok."""\nx = 1\n', encoding="utf-8")
    sast_bad = vibe_ws / "sast_bad.json"
    sast_bad.write_text(json.dumps({"verdict": "FAIL"}), encoding="utf-8")
    assert "passed" in bav_mod.run_vibe_check_impl(rsi_eng, ok_py, sast_report=sast_bad)

    vibe_dir = vibe_ws / "pkg"
    vibe_dir.mkdir(parents=True, exist_ok=True)
    (vibe_dir / "bad_bytes.py").write_bytes(b"\xff\xfe\x00broken")
    (vibe_dir / "bad_json.json").write_text("{bad json", encoding="utf-8")
    (vibe_dir / "long_ste.md").write_text("# H\n" + " ".join(["word"] * 26) + ".\n", encoding="utf-8")
    (vibe_dir / "fffd_char.md").write_text("# F\nVal \ufffd.\n", encoding="utf-8")
    (vibe_dir / "clean.py").write_text('"""Ok."""\nVAL = 1\n', encoding="utf-8")
    assert bav_mod.run_vibe_check_impl(rsi_eng, vibe_dir, profile="vibe_sprint_micro_rsi", sast_report=vibe_ws / "no_sast.json")["passed"] is False

    atomic_t = tmp_path / "atomic_t.bin"
    snap_mod._atomic_write_bytes(atomic_t, b"v1")
    assert atomic_t.read_bytes() == b"v1"
    with monkeypatch.context() as mp:
        mp.setattr(_common_io_cov.os, "replace", lambda _s, _d: (_ for _ in ()).throw(PermissionError("locked")))
        with pytest.raises(OSError):
            snap_mod._atomic_write_bytes(atomic_t, b"v2")
    assert atomic_t.read_bytes() == b"v1"

    snap_mgr = snap_mod.HealingSnapshotManager(base_temp_dir=tmp_path / "snap_cov_dir")
    sf1 = tmp_path / "snap_f1.py"
    sf1.write_text("alpha = 1\n", encoding="utf-8")
    sid = snap_mgr.create_snapshot([sf1, tmp_path / "missing_snap.py"])
    sf1.write_text("alpha = 2\n", encoding="utf-8")
    assert all(snap_mgr.rollback(sid).values()) and sf1.read_text(encoding="utf-8") == "alpha = 1\n"
    with pytest.raises(KeyError):
        snap_mgr.rollback("nonexistent_snap_id")
    assert snap_mgr.evaluate_fitness(0, 0, 0, 0, 1).verdict == snap_mod.FitnessVerdict.REGRESSION
    assert snap_mgr.evaluate_fitness(1, 0, 2, 0, 0).verdict == snap_mod.FitnessVerdict.REGRESSION
    assert snap_mgr.evaluate_fitness(3, 0, 2, 0, 0).verdict == snap_mod.FitnessVerdict.PASSED
    snap_mgr.cleanup(sid)
    snap_mgr.cleanup()


@pytest.mark.fast
def test_carbon_core_sandbox_confine_l3_sources_and_sentinel_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre confinamento sandbox DAST, SpectrumCounts, L3 source guards e fallback sentinel."""
    from _internal.nk_common import io as _common_io_cov

    sb_dir = tmp_path / "sb_confined"
    sb_dir.mkdir(parents=True, exist_ok=True)
    for bad_rel in ("", "a\x00b", str(sb_dir.resolve()), "../escape", "."):
        with pytest.raises(ValueError):
            dast_mod._resolve_confined_sandbox_path(sb_dir, bad_rel)
    with monkeypatch.context() as mp:
        mp.setattr(dast_mod, "_HAS_PSUTIL", False)
        r1 = dast_mod._get_process_memory_rss(os.getpid(), p_process=None)
        r2 = dast_mod._get_process_memory_rss(os.getpid(), p_process=None)
    assert (r1 > 0 if sys.platform == "win32" else r1 >= 0) and r2 >= 0

    sc = sbfl_mod.SpectrumCounts(n_ef=2, n_ep=1, n_nf=3, n_np=4)
    assert (sc.total_failed, sc.total_passed, sc.total_executed, sc.total_tests) == (5, 5, 3, 10)

    hp_target = tmp_path / "demo_hp.py"
    hp_target.write_text("VAL = 1\n", encoding="utf-8")
    html_f = tmp_path / "cov_page.html"
    html_f.write_text("<html><body>ok</body></html>", encoding="utf-8")
    assert l3_mod.resolve_html_source("") == "" and l3_mod.resolve_html_source("<div>inline</div>") == "<div>inline</div>"
    assert "ok" in l3_mod.resolve_html_source(str(html_f)) and l3_mod.resolve_html_source("plain_no_angle") == "plain_no_angle"
    for bad_src in ("foo/../bar.html", str(hp_target)):
        with pytest.raises(ValueError):
            l3_mod.resolve_html_source(bad_src)
    with pytest.raises(FileNotFoundError):
        l3_mod.resolve_html_source(str(tmp_path / "missing_page.html"))

    for exp_in in ('{"nodes": []}', "{bad", "```html\n<div></div>\n```", "- item\n", "plain_no_angle", ""):
        txt, kind = l3_mod.resolve_expected_source(exp_in)
        assert isinstance(txt, str) and kind in ("html", "md", "json")
    for exp_bad in ("foo/../bar.html", str(hp_target)):
        with pytest.raises(ValueError):
            l3_mod.resolve_expected_source(exp_bad)
    with pytest.raises(FileNotFoundError):
        l3_mod.resolve_expected_source(str(tmp_path / "missing_exp.html"))

    state_f = tmp_path / "sentinel_state_cov.json"
    orig_replace, rep_calls = _common_io_cov.os.replace, [0]

    def _flaky_replace(src: Any, dst: Any) -> Any:
        rep_calls[0] += 1
        if rep_calls[0] == 1:
            raise PermissionError("transient lock")
        return orig_replace(src, dst)

    with monkeypatch.context() as mp:
        mp.setattr(act_mod, "_get_kernel32_mutex_api", lambda: None)
        mp.setattr(_common_io_cov.os, "replace", _flaky_replace)
        with act_mod._SentinelNamedMutex("fallback_mx_cov", timeout_ms=50) as acq:
            assert acq is False
        act_mod._write_state_atomic_win32(str(state_f), {"state": "GREEN", "steps": 1})
    assert rep_calls[0] == 0 and not state_f.exists()
    with monkeypatch.context() as mp_io:
        if sys.platform != "win32":
            mp_io.setattr(act_mod, "_get_kernel32_mutex_api", lambda: object())
            mp_io.setattr(act_mod, "create_or_open_named_mutex", lambda name, wait_ms=1000, k32=None: (101, True, None))
            mp_io.setattr(act_mod, "release_win32_mutex", lambda h, k32=None: None)
        mp_io.setattr(_common_io_cov.os, "replace", _flaky_replace)
        act_mod._write_state_atomic_win32(str(state_f), {"state": "GREEN", "steps": 1})
    assert rep_calls[0] >= 2 and state_f.is_file()


@pytest.mark.fast
def test_carbon_core_compliance_tele_ast_scope_and_router_domains(tmp_path: Path) -> None:
    """Copre compliance stale telemetry, scope AST Guard profondo, domain_matcher e RSI docs."""
    c_ws = tmp_path / "comp_rsi_ws"
    (c_ws / "nk_tracking").mkdir(parents=True, exist_ok=True)
    tp_dir = tmp_path / "brain" / "sess-cov-01"
    tp_dir.mkdir(parents=True, exist_ok=True)
    tp_cov = tp_dir / "transcript.jsonl"
    tp_cov.write_text('{"step_index": 1, "source": "USER_EXPLICIT", "content": "hi"}\n', encoding="utf-8")
    tel = c_ws / "nk_tracking" / "rsi_telemetry.jsonl"
    tel.write_text(json.dumps({"session_id": "sess-cov-01", "verdict": "CONVERGED_OPTIMAL", "delta_k": 0}) + "\n", encoding="utf-8")
    old_t = time.time() - 99999.0
    os.utime(tel, (old_t, old_t))
    checker = comp_mod.NKComplianceChecker(workspace_root=c_ws)
    assert "scores" in checker.audit_transcript(tp_cov)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    tel.write_text("\n".join(["{bad_json", "[]", json.dumps({"session_id": "other-sess", "verdict": "FAIL", "delta_k": 3}), json.dumps({"timestamp": now_iso, "fitness_q": 92.5, "delta_k": 1}), json.dumps({"session_id": "sess-cov-01", "verdict": "CONVERGED_OPTIMAL", "delta_k": 0})]) + "\n", encoding="utf-8")
    assert checker.audit_transcript(tp_cov)["total_steps"] >= 1

    scope_py = (
        "a, b, c = 1, 2, 3\ndel (a, [b, c])\ndel obj_cov.attr\ndel arr_cov[0]\n"
        "x_ann: int = 1\nobj_cov.attr: int = 2\ndv = 1\ndel dv\ndv += 1\nundef_aug += 1\nobj_cov.attr += 1\n"
        "type AliasCov[X] = list[X]\nclass GenCov[T]:\n    cls_ann: int = 1\n"
        "fn_l = lambda a, /, b=1, *va, k=2, **kw: a + b + k\nasync def af_cov(cm_cov):\n"
        "    async for _i in [1]:\n        pass\n    else:\n        pass\n    async with cm_cov() as _c:\n        pass\n"
        "    try:\n        pass\n    except Exception:\n        pass\n    val = {'k': 1}\n    match val:\n"
        "        case {'k': mv, **rm} if mv > 0:\n            _ = mv\n        case [*sm]:\n            _ = sm\n        case ClsCov(1, x=pb) | 99:\n            _ = pb\n"
        "    return [y for _x in [1] if (y := _x) > 0]\n"
    )
    assert len(guard_mod.ASTGuardValidator().validate_code_edit(scope_py, scope_py, target_file="cov_scope.py").violations) >= 1
    sast_cov_py = (
        "import builtins, subprocess as sp, sys\ngetattr(builtins, 'eval'[0:4:0])('1')\n"
        "getattr(builtins, chr(9999999) + 'x')('1')\nsp.Popen('c', shell=not [1])\nsp.Popen('c', shell=not {'a': 1})\n"
        "sp.Popen('c', shell=f\"{'a'}b\")\nsp.Popen('c', shell=bool([1]))\nsp.Popen('c', shell=(+1 and ~0 and -1))\n"
        "sp.Popen('c', shell=('' if False else 'x'))\ngetattr(globals(), '__builtins__')\nsys.modules.get('ctypes')\n"
    )
    assert len(guard_mod.ASTGuardValidator.check_sast_constructs(sast_cov_py, target_file="cov_sast.py")) >= 4

    dm_cov = _load_mod("domain_matcher_cov", "scripts/_internal/vibe_sprint_router/domain_matcher.py")
    assert dm_cov._token_matches_keyword("build.py", "run build.py now", None) is True
    assert dm_cov._token_matches_keyword("alpha$", "use alpha$", {"alpha$"}) is True
    assert dm_cov._token_matches_keyword("build", ("x " * 16000) + " build", None) is True
    assert dm_cov._token_matches_keyword("build", ("x " * 16000) + " miss", None) is False
    assert dm_cov._resolve_native_subagent("DOM-01", "NK-Agent-Instruction-Forge", "forge") == "NK-Builder-Agent"
    assert dm_cov._resolve_native_subagent("DOM-02", "NK-Ideator", "x") == "NK-Arch-Specifier"
    assert dm_cov._resolve_native_subagent("DOM-02", "NK-System-Architect", "x") == "NK-Specifier-Agent"
    assert dm_cov._resolve_native_subagent("DOM-04", "NK-Orchestrator", "x") == "Orchestrator-Direct"
    assert dm_cov._resolve_native_subagent("DOM-03", "NK-Oracle-Evaluator", "x") == "NK-RSI-Auditor"
    assert dm_cov._resolve_native_subagent("DOM-03", None, "rsi convergence telemetry") == "NK-RSI-Auditor"

    eco1, eco2 = tmp_path / "eco_cov1", tmp_path / "eco_cov2"
    (eco1 / ".agents" / "skills" / "demo").mkdir(parents=True, exist_ok=True)
    (eco1 / ".agents" / "skills" / "demo" / "SKILL.md").write_text("[RULE-STE100] " + ("word " * 25) + ". [x](resources/missing.md)\n", encoding="utf-8")
    assert rsi_mod.RSIConvergenceEngine(workspace_root=eco1).verify_ecosystem(profile="ste100_rsi")["passed"] is False
    (eco2 / "docs").mkdir(parents=True, exist_ok=True)
    (eco2 / "docs" / "guide.md").write_text("[RULE-STE100] " + ("word " * 25) + ". [ext](https://example.com) [loc](missing_doc.md)\n", encoding="utf-8")
    assert rsi_mod.RSIConvergenceEngine(workspace_root=eco2).verify_ecosystem(profile="ste100_rsi")["passed"] is False


@pytest.mark.fast
def test_carbon_core_hook_stop_evidence_json_io_and_tac_edges(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre _internal.nk_hook_gate.{stop_evidence, json_io} e _internal.vibe_sprint_router.transcript_and_cli."""
    se_cov = importlib.import_module("_internal.nk_hook_gate.stop_evidence")
    se_tmp = tmp_path / "se_cov_tmp"
    (se_tmp / "nk_hooks").mkdir(parents=True, exist_ok=True)
    tp_se = se_tmp / "tp_se.jsonl"
    tp_se.write_bytes(b'{"step_index": 0}\n\xff\xfe\n\n{bad\n[]\n{"type": "COMPACTION", "compacted": true}\n{"type": "MODEL", "usage": {"input_tokens": 500}}\n{"partial_no_nl": 1')
    (se_tmp / "nk_hooks" / "fastguard_cid_se.json").write_text(json.dumps({"byte_offset": 0, "last_actual_tokens": 10, "steps": 1, "compaction_epoch": 0}), encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(se_tmp))
        mp.setenv("TEMP", str(se_tmp))
        mp.setenv("TMP", str(se_tmp))
        toks, stps, ep = se_cov._stop_read_tokens_and_epoch(tp_se, "cid_se")
    assert toks >= 500 and stps >= 1 and ep >= 1
    wal_ws = tmp_path / "se_wal_ws"
    (wal_ws / ".wal").mkdir(parents=True, exist_ok=True)
    (wal_ws / ".wal" / "active.wal").write_text("LOCKED", encoding="utf-8")
    assert se_cov._stop_is_batch_mutex_or_wal_busy([wal_ws]) is True

    jio = importlib.import_module("_internal.nk_hook_gate.json_io")
    jtmp = tmp_path / "jio_cov_dir"
    jtmp.mkdir(parents=True, exist_ok=True)
    _BadTty = type("_BadTty", (), {"buffer": type("_SB", (), {"read": staticmethod(lambda: "\ufeff  {} ")})(), "isatty": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("no tty")))})
    _ErrIn = type("_ErrIn", (), {"buffer": None, "isatty": staticmethod(lambda: False), "read": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("boom")))})
    with monkeypatch.context() as mp:
        mp.delenv("NK_HOOKS_TEMP_DIR", raising=False)
        mp.setenv("TEMP", str(jtmp))
        mp.setenv("TMP", str(jtmp))
        assert jio._get_hooks_temp_dir().is_dir()
        mp.setattr(sys, "stdin", _BadTty())
        assert jio._read_stdin_payload_ex() == ({}, False)
        mp.setattr(sys, "stdin", _ErrIn())
        assert jio._read_stdin_payload_ex() == ({}, True)
        mp.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False, buffer=io.BytesIO(b"\xef\xbb\xbf[1, 2]")))
        assert jio._read_stdin_payload_ex() == ({}, True)
    assert jio._resolve_conv_id("bad/cid", {"conversation_id": "conv_cov_1"}) == "conv_cov_1"
    assert jio._resolve_conv_id("a\x00b", {"conversationId": ".."}).startswith("default_")
    j_bad = jtmp / "bad.json"
    j_bad.write_text("[1, 2]", encoding="utf-8")
    assert jio._read_json_safe(j_bad) is None
    j_bad.write_text("{broken", encoding="utf-8")
    assert jio._read_json_safe(j_bad) is None

    j_tgt = jtmp / "atomic_cov.json"
    with monkeypatch.context() as mp:
        mp.setattr(jio.os, "lstat", lambda _p: SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400))
        assert jio._is_path_reparse_point(j_tgt) is True
        mp.setattr(jio.os, "lstat", lambda _p: (_ for _ in ()).throw(OSError("no access")))
        assert jio._is_path_reparse_point(j_tgt) is False
        mp.setattr(jio.time, "sleep", lambda _d: None)
        def _deny_win5(_s: Any, _d: Any) -> None:
            e = OSError("sharing")
            e.winerror = 5
            raise e
        mp.setattr(jio.os, "replace", _deny_win5)
        jio._write_json_atomic_safe(j_tgt, {"ok": 1})
        mp.setattr(jio, "_is_path_reparse_point", lambda p: p == jtmp)
        jio._write_json_atomic_safe(j_tgt, {"ok": 2})
        mp.setattr(jio, "_is_path_reparse_point", lambda p: p.name.endswith(".tmp"))
        jio._write_json_atomic_safe(j_tgt, {"ok": 3})
    assert jio._extract_first_section("plain a\nplain b") == "plain a\nplain b"
    assert len(jio._extract_historical_headers("## V1\nx\n## V2\n")) == 2
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(jtmp))
        jio._log_shadow_decision("cid_cov", "pre", "PreInvocation", {"ephemeralMessage": "warn"})


@pytest.mark.fast
def test_carbon_core_router_tac_and_transcript_tools_edges(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Copre transcript_and_cli e tutte le funzioni helper/compliance di nk_transcript_tools."""
    tac = importlib.import_module("_internal.vibe_sprint_router.transcript_and_cli")
    assert tac._extract_user_text_from_record({"type": "MODEL", "content": "skip"}) is None
    assert tac._extract_user_text_from_record({"type": "USER_INPUT", "content": "<CONTEXT_SUMMARY> skip"}) is None
    assert tac._extract_user_text_from_record({"type": "USER_INPUT", "content": [" ", {"text": "list ok"}]}) == "list ok"
    assert tac._extract_user_text_from_record({"type": "USER_INPUT", "content": [{"text": "<CONTEXT_SUMMARY> skip"}]}) is None
    tp_empty, tp_tail = tmp_path / "empty.jsonl", tmp_path / "tail.jsonl"
    tp_empty.write_text("", encoding="utf-8")
    tp_tail.write_text('{bad\n{"type": "USER_INPUT", "content": "tail msg"}\n', encoding="utf-8")
    assert tac._read_latest_user_input_from_transcript(str(tp_empty)) is None
    assert tac._read_latest_user_input_from_transcript(str(tp_tail)) == "tail msg"
    (tmp_path / "pf_cov.txt").write_text("from file", encoding="utf-8")
    assert tac._resolve_effective_cli_prompt(SimpleNamespace(prompt_file="pf_cov.txt"), workspace_root=tmp_path) == "from file"
    with monkeypatch.context() as mp:
        mp.setattr(sys, "stdin", io.StringIO("from stdin"))
        assert tac._resolve_effective_cli_prompt(SimpleNamespace(prompt_file=None, stdin=True)) == "from stdin"
    assert tac._resolve_effective_cli_prompt(SimpleNamespace(prompt_file=None, stdin=False, classify_prompt=None, prompt="Vibe Sprint Change", positional_prompt=["fix", "bug"])) == "fix bug"
    assert tac.run_test() == 0

    assert tr_mod.clean_tool_str(None) == "" and tr_mod.clean_tool_str('"ok"') == "ok" and tr_mod.clean_tool_str('"\\q"') == "\\q"
    assert tr_mod.clean_tool_str("'single'") == "single" and tr_mod.clean_tool_str("plain") == "plain"
    assert tr_mod.extract_tool_name(None) == "" and tr_mod.extract_tool_name({"toolName": "read_file"}) == "read_file"
    assert tr_mod.extract_tool_args(None) == {} and tr_mod.extract_tool_args({"arguments": '{"k": 1}'}) == {"k": 1} and tr_mod.extract_tool_args({"arguments": "{bad"}) == {}
    assert tr_mod._extract_call_id(None) == "" and tr_mod._extract_call_id({"tool_result": {"call_id": "c1"}}) == "c1"
    assert tr_mod._extract_call_id({"tool_results": [{"toolCallId": "c2"}]}) == "c2"
    assert tr_mod._pop_correlated_tool_call([], {}) == {}
    assert tr_mod._pop_correlated_tool_call([{"id": "x"}, {"id": "y"}], {"id": "y"}) == {"id": "y"}
    assert tr_mod._pop_correlated_tool_call([{"id": "x"}], {"id": "z"}) == {"id": "x"}
    assert tr_mod.classify_transcript_record("bad") == "OTHER" and tr_mod.classify_transcript_record({"type": "PLANNER_RESPONSE"}) == "MODEL"
    assert tr_mod.classify_transcript_record({"tool_output": "ok"}) == "TOOL" and tr_mod.classify_transcript_record({"x": 1}) == "OTHER"
    assert tr_mod.is_read_file_output("") is False and tr_mod.is_read_file_output("File Path: `file:///a`") is True
    assert tr_mod.extract_command_exit_code("ok", "read_file") is None and tr_mod.extract_command_exit_code('"exit_code": 2', "run_command") == 2
    assert tr_mod.extract_command_exit_code("Command exited with code 7.", "run_command") == 7
    assert tr_mod._has_missing_path_error("ERROR", "x") is True and tr_mod._has_missing_path_error("DONE", "File Path: `file:///a`") is False
    assert tr_mod._has_missing_path_error("DONE", "filenotfounderror") is True


@pytest.mark.fast
def test_carbon_core_prompt_linter_all_anti_patterns() -> None:
    """Chiude i rami AP-1..AP-13 e AP-2b in _internal.nk_common.prompt_linter_core."""
    plc = importlib.import_module("_internal.nk_common.prompt_linter_core")
    bad_prompt = (
        "!diretto Fase 1 modifica src_app/x.py\nFase 2 usa NK-Builder-Agent\nFase 3 verifica finche 100% pass\n"
        "Opera come NK-Oracle-Evaluator e NK-Orchestrator e avvia server senza safe_cleanup.\n"
        "Usa rsi_convergence_engine.py --verify sulla repo.\n"
        "Esegui SIA la ricerca web normale sia search_web e tavily per 15 query.\n"
        "Includi holdout set b e canary_v1.json e avviando il server.\n"
        "Puoi usare manualmente /goal per questo prompt.\n"
    )
    res_bad = plc.evaluate_ap_rules(bad_prompt, mode="auto")
    codes = {v["code"] for v in res_bad["violations"]}
    assert res_bad["passed"] is False and {"AP-1", "AP-2", "AP-2b", "AP-3", "AP-4", "AP-5", "AP-6", "AP-7", "AP-8", "AP-10", "AP-11"}.issubset(codes)
    ap9_codes = {v["code"] for v in plc.evaluate_ap_rules("<env_capsule> opera come nk-orchestrator", mode="auto")["violations"]}
    assert "AP-9" in ap9_codes

    handoff_bad = (
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n"
        "### FASE 1\ninvoke_subagent ora\nPista 1A: scegli cosa fare\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]"
    )
    res_ho = plc.evaluate_ap_rules(handoff_bad, mode="auto")
    ho_codes = {v["code"] for v in res_ho["violations"]}
    assert res_ho["passed"] is False and {"AP-12", "AP-13"}.issubset(ho_codes)
    assert plc.evaluate_ap_rules("Analizza architettura in sola lettura.", mode="auto")["passed"] is True


@pytest.mark.integration
def test_carbon_core_autoheal_improved_passed_and_lazy_pydantic(tmp_path: Path) -> None:
    """Copre AutoHealPipeline IMPROVED/PASSED/failure senza mock e lazy pydantic su --help."""
    hp_ws = tmp_path / "hp_cov_ws"
    (hp_ws / ".staging" / "scripts").mkdir(parents=True, exist_ok=True)
    hp_target = hp_ws / ".staging" / "scripts" / "demo_hp.py"
    hp_target.write_text("VAL = 0\n", encoding="utf-8")

    # Runner reale su file locale: VAL==0 -> 2 failed, VAL==1 -> 1 passed 1 failed (IMPROVED), VAL==2 -> 2 passed (PASSED)
    probe_cmd = (
        f'"{Path(sys.executable).as_posix()}" -B -c '
        '"import pathlib, sys; v=pathlib.Path(sys.argv[1]).read_text(); '
        'c = 2 if \'VAL = 2\' in v else (1 if \'VAL = 1\' in v else 0); '
        'print(\'m.py:1: in f\\nE   AssertionError: val\'); '
        'print(f\'{c} passed, {2-c} failed in 0.01s\'); sys.exit(0 if c==2 else 1)" '
        f'"{hp_target.as_posix()}"'
    )
    hp_ok = heal_mod.AutoHealPipeline(cwd=hp_ws, max_cycles=3).run_pipeline(
        probe_cmd, hp_target,
        repair_callback=lambda _loc, cyc: hp_target.write_text(f"VAL = {cyc}\n", encoding="utf-8"),
    )
    assert hp_ok.success is True and hp_ok.cycles_used == 2 and hp_ok.final_failed == 0

    hp_target.write_text("VAL = 0\n", encoding="utf-8")
    hp_fail = heal_mod.AutoHealPipeline(cwd=hp_ws, max_cycles=1).run_pipeline(
        f'"{Path(sys.executable).as_posix()}" -B -c "import sys; sys.exit(1)"',
        hp_target,
        repair_callback=lambda _loc, _cyc: (_ for _ in ()).throw(RuntimeError("cb boom")),
    )
    assert hp_fail.success is False and hp_fail.rolled_back is True

    rsi_p = _WORKSPACE_ROOT / ".staging" / "scripts" / "rsi_convergence_engine.py"
    if not rsi_p.is_file():
        rsi_p = _WORKSPACE_ROOT / "scripts" / "rsi_convergence_engine.py"
    probe = (
        "import runpy, sys\n"
        f"sys.argv = [{str(rsi_p)!r}, '--help']\n"
        "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit:\n    pass\n"
        "assert 'pydantic' not in sys.modules\n"
    )
    proc_rsi = subprocess.run(
        [sys.executable, "-B", "-c", probe], cwd=str(_WORKSPACE_ROOT), capture_output=True, text=True, timeout=20.0, shell=False
    )
    assert proc_rsi.returncode == 0, proc_rsi.stderr or proc_rsi.stdout

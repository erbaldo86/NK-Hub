# -*- coding: utf-8 -*-
"""
Suite piattaforma DOM-03/DOM-04: Oracle L3, Preflight, QBM, Sentry/Memory e Cleanup.
Modulo: tests/test_platform_oracle_and_cleanup.py.
"""

from __future__ import annotations

import ast
import gzip
import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

try:
    from conftest import WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module, load_script_by_relpath
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, call_script_main, call_script_main_captured, load_nk_script_module, load_script_by_relpath

oracle_mod = load_nk_script_module("oracle_evaluator_l3")
preflight_mod = load_nk_script_module("preflight_health_check")
PreflightHealthChecker = preflight_mod.PreflightHealthChecker
cleanup_mod = load_nk_script_module("safe_cleanup_dev_servers")
heartbeat_mod = load_nk_script_module("async_heartbeat_signaler")
qbm_mod = load_nk_script_module("quality_baseline_manager")
router_mod = load_nk_script_module("vibe_sprint_router")
boot_mod = load_nk_script_module("nk_session_bootstrap")
sentry_mod = load_nk_script_module("nk_context_sentry")
mem_mod = load_nk_script_module("memory_3tier_engine")


def _resolve_doc(rel_path: str) -> Path:
    """Risolve un file di documentazione o overlay dando priorita a .staging/."""
    stg = WORKSPACE_ROOT / ".staging" / rel_path
    return stg if stg.exists() else WORKSPACE_ROOT / rel_path


def _mk_dirs(root: Path, *subs: str) -> Path:
    """Crea root e le sottodirectory specificate sotto root."""
    root.mkdir(parents=True, exist_ok=True)
    for s in subs:
        (root / s).mkdir(parents=True, exist_ok=True)
    return root


def _make_clean_hub(hub_dir: Path) -> Path:
    """Crea una radice NK_Hub minimale conforme ai controlli Fast-Stat."""
    _mk_dirs(hub_dir, "scripts", ".agents", "nk_tracking", ".wal")
    (hub_dir / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8"
    )
    return hub_dir


def _assert_oracle_conf10_and_lfi(tmp_path: Path) -> None:
    """Verifica CONF-10 expected .json/.md/.html, LFI guard e exit code CLI 2."""
    actual_html = "<!DOCTYPE html><html><body><main><h1>Dashboard Principale</h1><button id='submit_btn' class='btn primary'>Invia</button></main></body></html>"
    actual_file = tmp_path / "actual.html"
    actual_file.write_text(actual_html, encoding="utf-8")
    exp_json, exp_j_fail = tmp_path / "expected.json", tmp_path / "expected_missing.json"
    exp_json.write_text(json.dumps({"required_tags": ["main", "button"], "required_ids": ["submit_btn"], "required_classes": ["btn", "primary"], "required_texts": ["Dashboard Principale", "Invia"]}), encoding="utf-8")
    exp_j_fail.write_text(json.dumps({"required_ids": ["submit_btn", "missing_ctrl"]}), encoding="utf-8")
    exp_md, exp_md_f, exp_fenced = tmp_path / "expected_spec.md", tmp_path / "expected_spec_fail.md", tmp_path / "expected_fenced.md"
    exp_md.write_text('# Dashboard Principale\n- <button>\n- #submit_btn\n- "Invia"\n', encoding="utf-8")
    exp_md_f.write_text("# Titolo Inesistente\n- #non_existent_id\n", encoding="utf-8")
    exp_fenced.write_text(f"```html\n{actual_html}\n```\n", encoding="utf-8")
    ev = oracle_mod.DOMOracleEvaluator()
    assert [ev.evaluate_deltas(src, act).verdict for src, act in ((str(exp_json), str(actual_file)), (str(exp_j_fail), str(actual_file)), (str(exp_md), str(actual_file)), (str(exp_fenced), actual_html))] == ["PASS", "FAIL", "PASS", "PASS"]
    assert ev.evaluate_deltas(str(exp_md_f), str(actual_file)).discrepancy_count >= 2
    secret_env = tmp_path / "secret.env"
    secret_env.write_text("SECRET_TOKEN=12345\n", encoding="utf-8")
    assert (oracle_mod.resolve_expected_source(str(exp_md))[1], oracle_mod.resolve_expected_source(str(exp_json))[1]) == ("md", "json")
    with pytest.raises(ValueError):
        oracle_mod.resolve_html_source(str(exp_json))
    for flag_exp, src_exp in (("--expected-file", exp_md), ("--expected", exp_json)):
        rc_p, out_p, _ = call_script_main_captured(oracle_mod, [flag_exp, str(src_exp), "--actual-file", str(actual_file), "--json"])
        assert (rc_p, json.loads(out_p)["verdict"]) == (0, "PASS")
        for bad_act in (str(exp_md), str(exp_json), str(secret_env), f"{'.' + '.'}/secret.html"):
            with pytest.raises(ValueError):
                oracle_mod.resolve_html_source(bad_act)
            assert [call_script_main_captured(oracle_mod, [flag_exp, str(src_exp), fa, bad_act, "--json"])[0] for fa in ("--actual", "--actual-file")] == [2, 2]


def _assert_oracle_deltas_and_cli(tmp_path: Path) -> None:
    """Verifica delta DOM, HTML5 implicito e CLI oracle_evaluator_l3."""
    ev = oracle_mod.DOMOracleEvaluator()
    for bad_json in ("{bad", "[1, 2]"):
        with pytest.raises(ValueError):
            ev.evaluate_deltas(bad_json, "<div></div>", expected_kind="json")
    assert ev.evaluate_deltas(json.dumps({"html": "<div><p id='a'>Hi</p></div>", "required_ids": ["a"]}), "<div><p id='a'>Hi</p></div>", expected_kind="json").verdict == "PASS"
    deltas = ev.evaluate_deltas("<div><p id='k1' class='a'>One</p><span data-key='k2'>Two</span><b id='k3'>Del</b><em id='k5'>Sub</em></div>", "<div><p id='k1' class='b'>Changed</p><i data-key='k2'>Two</i><em id='k5'>Sub</em><u id='k6'>Add</u></div>").deltas
    assert {"ATTRIBUTE_MISMATCH", "TEXT_MISMATCH", "TAG_MISMATCH", "REMOVED", "ADDED"}.issubset({d.change_type for d in deltas})
    assert ev.count_nodes(ev.parse_html("<ul><li>A<li>B</ul><p>P1<div>D</div><dl><dt>T1<dd>D1<dt>T2</dl><select><optgroup label='g'><option>1<option>2<optgroup label='g2'><option>3</select><table><tbody><tr><td>1<th>2<tr><td>3<tfoot><tr><td>4</table><br/></br><input/>")) >= 15
    exp_f, act_f, secret_txt = tmp_path / "exp.html", tmp_path / "act.html", tmp_path / "secret.txt"
    exp_f.write_text("<div><span>Ok</span></div>", encoding="utf-8")
    act_f.write_text("<div><span>Ok</span></div>", encoding="utf-8")
    secret_txt.write_text("secret", encoding="utf-8")
    for argv, exp_rc in (([], 2), (["--html-file", str(act_f)], 2), (["--expected-file", str(exp_f)], 2), (["--actual-file", str(act_f)], 2), (["--expected-file", str(tmp_path / "missing.html"), "--actual-file", str(act_f)], 2)):
        assert call_script_main_captured(oracle_mod, argv)[0] == exp_rc
    rc_f, out_f, _ = call_script_main_captured(oracle_mod, ["--expected", "<div>A</div>", "--actual", "<div>B</div>"])
    rc_bj, out_bj, _ = call_script_main_captured(oracle_mod, ["--expected-file", str(secret_txt), "--actual", "<div></div>", "--json"])
    assert ("PASS" in call_script_main_captured(oracle_mod, ["--expected-file", str(exp_f), "--actual-file", str(act_f)])[1], rc_f, "FAIL" in out_f, rc_bj, "DOM source error" in out_bj) == (True, 1, True, 2, True)


@pytest.mark.integration
def test_oracle_l3_dom_conf10_and_cli(tmp_path: Path) -> None:
    """Verifica void tag, CONF-10, delta DOM, HTML5 implicito e CLI oracle_evaluator_l3."""
    p1 = _mk_dirs(tmp_path / "l3_void")
    html_file = p1 / "index.html"
    html_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><link rel='stylesheet' href='a.css'></head><body><main><img src='logo.png' alt='logo'><br><input type='text' id='q'><button id='submit_btn'>Invia</button></main></body></html>"
    html_file.write_text(html_content, encoding="utf-8")
    spec_arg = f"{html_file}:#submit_btn:Invia"
    assert ("<!DOCTYPE html>" in oracle_mod.resolve_html_source(spec_arg), oracle_mod.DOMOracleEvaluator().evaluate_deltas(spec_arg, html_content).verdict) == (True, "PASS")
    _assert_oracle_conf10_and_lfi(_mk_dirs(tmp_path / "l3_conf10"))
    _assert_oracle_deltas_and_cli(tmp_path)


def _assert_preflight_pep562_and_ro(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica baseline corrotta, --check-only read-only e PEP 562 lazy exports."""
    corrupt_root = _mk_dirs(tmp_path / "corrupt_ws", ".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests", ".staging")
    ro_root = _mk_dirs(tmp_path / "readonly_ws", ".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests")
    (corrupt_root / "nk_tracking" / "quality_baseline.json").write_text("{CORRUPTED_JSON_PAYLOAD", encoding="utf-8")
    rep = PreflightHealthChecker(workspace_root=corrupt_root).run_full_check(auto_fix=True)
    (ro_root / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"_version": "6.0.0-Carbon", "metrics": {"skills_audited": 16, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}), encoding="utf-8")
    assert (rep["status"], rep["checks"]["baseline_alignment"]["passed"], call_script_main(preflight_mod, ["--root", str(ro_root), "--check-only"], monkeypatch), (ro_root / ".staging").exists()) == ("FAIL", False, 1, False)

    facade_path = Path(preflight_mod.__file__).resolve()
    tree = ast.parse(facade_path.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("_phc_pep562_probe", facade_path)
    fresh = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(fresh)  # type: ignore[union-attr]
    assert (any((n.module or "").startswith("_internal.preflight_health_check") for n in tree.body if isinstance(n, ast.ImportFrom)), {"__getattr__", "__dir__", "main"}.issubset({n.name for n in tree.body if isinstance(n, ast.FunctionDef)}), "PreflightHealthChecker" not in fresh.__dict__, callable(getattr(fresh, "PreflightHealthChecker"))) == (False, True, True, True)
    with pytest.raises(AttributeError):
        getattr(fresh, "nonexistent_preflight_attr")


@pytest.mark.fast
def test_preflight_baseline_pep562_and_anchor_hygiene(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verifica fail-closed baseline, PEP 562 lazy exports, anchor sanitize, WAL e CLI preflight."""
    _assert_preflight_pep562_and_ro(tmp_path, monkeypatch)
    ws = _mk_dirs(tmp_path / "preflight_branch_ws", ".agents/skills", "nk_genome", "nk_tracking/anchor", "nk_tracking/handoff/stashes", ".wal", ".staging", "scripts", "tests", ".sandbox_tmp", ".commit_ready")
    ro_f = ws / ".commit_ready" / "ro.txt"
    ro_f.write_text("locked", encoding="utf-8")
    os.chmod(ro_f, stat.S_IREAD)
    assert (preflight_mod.safe_remove_dir(ro_f.parent), ro_f.parent.exists()) == (True, False)
    (ws / "nk_tracking" / "handoff" / "stashes" / "leftover.patch").write_text("diff", encoding="utf-8")
    (ws / "session_anchor.jsonl").write_text("{}\n", encoding="utf-8")
    anch_p = ws / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    anch_p.write_text('{"event": "A"}\n\n{bad\n{"event": "A"}\n', encoding="utf-8")
    for wf, wb in (("old_commit.wal", '{"state": "COMMITTED"}\n'), ("corrupt.wal", "{bad\n")):
        w = ws / ".wal" / wf
        w.write_text(wb, encoding="utf-8")
        os.utime(w, (time.time() - 300.0, time.time() - 300.0))
    checker = PreflightHealthChecker(workspace_root=ws)
    assert checker.run_full_check(auto_fix=False)["status"] == "FAIL"
    rep_fix = checker.run_full_check(auto_fix=True)
    assert (rep_fix["checks"]["staging_hygiene"]["passed"], rep_fix["checks"]["ssot_anchor"]["passed"], len(anch_p.read_text(encoding="utf-8").splitlines()), (ws / "session_anchor.jsonl").exists()) == (True, True, 1, False)
    rc_pre, out_pre, _ = call_script_main_captured(preflight_mod, ["--root", str(ws), "--json"])
    assert (rc_pre, "status" in json.loads(out_pre)) == (1, True)

    p_ws = _mk_dirs(tmp_path / "pre_wal_ws", ".wal")
    stale_f = p_ws / ".wal" / "old_tx.wal"
    stale_f.write_text('{"state": "PREPARED"}', encoding="utf-8")
    os.utime(stale_f, (time.time() - 300.0, time.time() - 300.0))
    w_res = PreflightHealthChecker(workspace_root=p_ws)._check_and_purge_stale_wals(auto_fix=True, ttl_seconds=10.0)
    assert (w_res["passed"], w_res["purged_count"]) == (True, 1)


def _assert_ssot_tombstone_and_bridge(tmp_path: Path) -> None:
    """Verifica tombstones P1-1, ssot_governance e errori bridge padre."""
    from _internal.preflight_health_check import ssot_governance as sg

    ver = str(preflight_mod.VERSION)
    ov_ws = _mk_dirs(tmp_path / "ov_tomb_ws", ".agents/skills/KeepSkill", ".agents/skills/DelSkill", ".staging", "nk_tracking", "nk_genome")
    (ov_ws / ".agents" / "AGENTS.md").write_text(f"# NK v{ver}\n## [RULE-01] Base\n", encoding="utf-8")
    (ov_ws / ".agents" / "skills" / "KeepSkill" / "SKILL.md").write_text(f'---\nname: Keep\nversion: "{ver}"\n---\nOk [RULE-01].\n', encoding="utf-8")
    (ov_ws / ".agents" / "skills" / "DelSkill" / "SKILL.md").write_text('---\nname: Del\nversion: "0.0.1-Old"\n---\nOld.\n', encoding="utf-8")
    (ov_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"version": ver, "summary": {"total_skills": 1}}), encoding="utf-8")
    (ov_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"_version": ver, "metrics": {"skills_audited": {"value": 1}, "crv_macro_phases": {"value": 4}, "unit_tests_pass_pct": {"value": 100.0}}}), encoding="utf-8")
    (ov_ws / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": [".agents/skills/DelSkill/SKILL.md"]}), encoding="utf-8")
    ov_chk = PreflightHealthChecker(workspace_root=ov_ws)
    ov_map = ov_chk._collect_agents_overlay()
    assert ("skills/DelSkill/SKILL.md" in ov_map, "skills/KeepSkill/SKILL.md" in ov_map, ov_chk._check_ssot_governance()["passed"]) == (False, True, True)
    for bad_t in ("{corrupt", "123", json.dumps({"deleted_files": [99]})):
        (ov_ws / ".staging" / ".deleted_files.json").write_text(bad_t, encoding="utf-8")
        ov_chk._collect_agents_overlay()
        assert (ov_chk._last_tombstone_error is not None, ov_chk._check_ssot_governance()["passed"]) == (True, False)

    parent = _mk_dirs(tmp_path / "Antigravity", ".agents")
    hub = _mk_dirs(parent / "NK_Hub", ".agents/skills/NK-S1", ".agents/rules", ".staging/.agents/skills/NK-S1", "nk_genome", "nk_tracking", "scripts")
    (hub / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps({"summary": {"total_skills": 7}}), encoding="utf-8")
    assert (sg.get_expected_skills_count(hub), sg.normalize_tombstone_rel(r".\.agents\rules\x.md")) == (7, ".agents/rules/x.md")
    (hub / "nk_genome" / "nk_registry_manifest.json").write_text("{bad", encoding="utf-8")
    assert sg.get_expected_skills_count(hub) == 11
    (hub / ".staging" / ".deleted_files.json").write_text(json.dumps([".agents/rules/old.md"]), encoding="utf-8")
    (hub / ".agents" / "rules" / "old.md").write_text("old", encoding="utf-8")
    (hub / ".agents" / "AGENTS.md").write_text("# Costituzione\n## [RULE-01] Uno\n## [RULE-01] Dup\nVedi [RULE-99].\n", encoding="utf-8")
    (hub / ".staging" / ".agents" / "skills" / "NK-S1" / "SKILL.md").write_text("version: 0.0.1\n", encoding="utf-8")
    (hub / ".agents" / "agent.md").write_text("# No version\n", encoding="utf-8")
    (hub / "nk_tracking" / "quality_baseline.json").write_text("[]", encoding="utf-8")
    (parent / ".agents" / "AGENTS.md").write_text("# Bridge incompleto\n", encoding="utf-8")
    chk = PreflightHealthChecker(workspace_root=hub)
    gov_bad = sg.check_ssot_governance(chk)
    assert (chk._check_baseline_alignment()["passed"], gov_bad["passed"], gov_bad["duplicate_rule_ids"], "RULE-99" in gov_bad["orphan_rule_refs"], gov_bad["root_bridge_synced"]) == (False, False, ["RULE-01"], True, False)


@pytest.mark.integration
def test_preflight_ssot_governance_tombstones_and_retention(tmp_path: Path) -> None:
    """Esercita ssot_governance, WAL monotonic, tombstones P1-1, retention e auto-ancoraggio."""
    for fname, body, exp in (("e.wal", "", False), ("c.wal", '{"state": "COMMITTED"}', True), ("j.wal", '{"state": "PREPARED"}\n{"state": "COMMITTED"}\n', True), ("p.wal", '{"state": "PREPARED"}', False), ("cp.wal", '{"state": "COMMITTED"}\n{"state": "PREPARED"}\n', False), ("cb.wal", '{"state": "COMMITTED"}\n{bad_json\n', False), ("ca.wal", '{"state": "COMMITTED"}\n[1, 2]\n', False)):
        (tmp_path / fname).write_text(body, encoding="utf-8")
        assert PreflightHealthChecker._is_committed_wal(tmp_path / fname) is exp
    _assert_ssot_tombstone_and_bridge(tmp_path)

    ret_ws = _make_clean_hub(tmp_path / "ret_ws")
    rep_dir = _mk_dirs(ret_ws / "nk_tracking" / "reports_and_briefs", "nested")
    (ret_ws / "nk_tracking" / "anchor").mkdir()
    (ret_ws / "nk_tracking" / "anchor" / "session_anchor.jsonl").write_text('{"event": "OK"}\n', encoding="utf-8")
    (ret_ws / "nk_tracking" / "old.bak_1").write_text("bak", encoding="utf-8")
    (rep_dir / "FORENSIC_INSPECTOR_1.md").write_text("tmp", encoding="utf-8")
    for idx in range(5):
        (rep_dir / f"IB-20261122-0{idx}.md").write_text(f"ib {idx}", encoding="utf-8")
        (rep_dir / "nested" / f"TAS_Report_{idx}.md").write_text(f"tas {idx}", encoding="utf-8")
    ret_chk = PreflightHealthChecker(workspace_root=ret_ws)
    assert (PreflightHealthChecker().workspace_root.is_dir(), ret_chk._normalize_tombstone_rel("a\\b.md"), ret_chk._resolve_overlay_file("nk_tracking/quality_baseline.json") is not None) == (True, "a/b.md", True)
    assert (ret_chk.run_full_check(auto_fix=False)["checks"]["report_retention"]["passed"], ret_chk.run_full_check(auto_fix=True)["checks"]["report_retention"]["pruned_count"] >= 4, (ret_ws / "nk_tracking" / "old.bak_1").exists()) == (False, True, False)

    sim_p = tmp_path / "AntigravitySim"
    _mk_dirs(sim_p / "test")
    (sim_p / "test" / "keep.txt").write_text("SIBLING_TEST_INTACT", encoding="utf-8")
    sim_hub = _mk_dirs(_make_clean_hub(sim_p / "NK_Hub"), ".staging", "nk_genome")
    (sim_hub / "nk_genome" / "nk_registry_manifest.json").write_text('{"skills_index": {"NK-S1": {}}}', encoding="utf-8")
    (sim_hub / "nk_tracking" / "quality_baseline.json").write_text('{"metrics": {"skills_audited": 1, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}', encoding="utf-8")
    acs_mod, hook_mod = load_script_by_relpath("nk_acs_fastguard_iso", "scripts/nk_acs_fastguard.py"), load_script_by_relpath("nk_hook_gate_iso", "scripts/nk_hook_gate.py")
    assert (acs_mod._resolve_eff_root({"cwd": str(sim_p)}, str(sim_p)), hook_mod._resolve_effective_hub_root(sim_p), PreflightHealthChecker(workspace_root=sim_hub).run_full_check(auto_fix=True)["status"], (sim_p / "test" / "keep.txt").read_text(encoding="utf-8")) == (os.path.realpath(str(sim_hub)), sim_hub.resolve(), "HEALTHY_GREEN", "SIBLING_TEST_INTACT")


@pytest.mark.integration
def test_qbm_anomalies_router_tail_and_agents_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica QBM corrupt/oracle_lock anomalies, router >131KB tail e allineamento doc Generation."""
    qb_ws = _mk_dirs(tmp_path / "qb_ws", "nk_tracking")
    bl_f, ol_f = qb_ws / "nk_tracking" / "quality_baseline.json", qb_ws / "nk_tracking" / "oracle_lock.json"
    bl_f.write_text("{corrupt_json", encoding="utf-8")
    assert [qbm_mod._evaluate_baseline_compliance(str(bl_f), {"unit_tests_passed": 93})[0]["verdict"], qbm_mod._evaluate_baseline_compliance(str(bl_f), {"unit_tests_passed": 93}, preloaded_baseline={"metrics": "not_a_dict"})[0]["verdict"], qbm_mod._evaluate_baseline_compliance(str(bl_f), {"golden_tests_68": {"passed": 93, "total": 93, "pass_rate_pct": 100.0}}, preloaded_baseline={"unit_tests_passed": 93, "pass_rate_pct": 100.0})[0]["verdict"]] == ["FAIL", "FAIL", "PASS"]
    for payload, exp_len in (("[1, 2, 3]", 1), (json.dumps({"locked_files": ["tests/missing_a.py"], "files": {"tests/missing_b.py": "0" * 64}}), 2), ("{bad_lock", 1)):
        ol_f.write_text(payload, encoding="utf-8")
        assert len(qbm_mod._verify_oracle_lock_coherence(str(bl_f))) == exp_len
    big_tr = tmp_path / "big_transcript.jsonl"
    big_tr.write_text((json.dumps({"type": "MODEL", "content": "x" * 1024}) + "\n") * 140 + json.dumps({"type": "USER_INPUT", "content": "Implementa modulo 2PC"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("NK_TRANSCRIPT_PATH", str(big_tr))
    assert router_mod._read_latest_user_input_from_transcript() == "Implementa modulo 2PC"

    content, hub_content = _resolve_doc(".agents/AGENTS.md").read_text(encoding="utf-8"), _resolve_doc(".agents/skills/NK-Orchestrator/SKILL.md").read_text(encoding="utf-8")
    scribe_skill = _resolve_doc(".agents/skills/NK-Scribe-Memory/SKILL.md").read_text(encoding="utf-8")
    assert ("[RULE-00.5]" in content, "fast-stat" in content.lower(), "10. UNIFIED_ONBOARDING_COMPLIANCE" in hub_content, all(f"[{i}]" in hub_content for i in range(10)), boot_mod.NKSessionBootstrap(workspace_root=WORKSPACE_ROOT).run_bootstrap(fast_stat=True).get("status")) == (True, True, True, True, "PASS")
    assert ("quality_baseline_manager.py --check-only --live" in scribe_skill, "ast_repo_mapper.py --snapshot-out .staging/nk_genome/repo_map.md" in scribe_skill, _resolve_doc(".agents/agents/NK-Scribe-Agent/agent.md").read_bytes() == _resolve_doc(".agents/plugins/nk-gate/agents/NK-Scribe-Agent.md").read_bytes()) == (True, True, True)
    for rel in (".agents/skills/NK-Orchestrator/references/handoff_and_swarm_templates.md", ".agents/skills/NK-Orchestrator/references/hub_execution_protocols.md"):
        md_text = _resolve_doc(rel).read_text(encoding="utf-8")
        assert ("platform_runner.py --pytest-isolated" in md_text, "python -B -m pytest" in md_text) == (True, False)


@pytest.mark.integration
def test_context_sentry_and_memory_3tier_runtime_paths(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verifica rami corrupt/MSS/blind-read/CLI di nk_context_sentry e Tier1/Tier2/Tier3.gz di memory_3tier."""
    sentry = sentry_mod.NKContextSentry()
    corrupt_tr, swarm_tr = tmp_path / "corrupt_only.jsonl", tmp_path / "swarm_heavy.jsonl"
    corrupt_tr.write_text("not_json_line_1\nnot_json_line_2\n", encoding="utf-8")
    swarm_tr.write_text("\n".join(json.dumps(r) for r in ({"step_index": 0, "type": "USER_INPUT", "content": "Analizza"}, {"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "[Message] sender=w1 " + ("parola " * 350)}, {"step_index": 2, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file", "arguments": {"Path": "missing_x.py"}}]}, {"step_index": 3, "source": "TOOL", "type": "TOOL_RESULT", "status": "ERROR", "content": "file does not exist"}, {"step_index": 4, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "invoke_subagent", "arguments": {"Role": "Auditor"}}]})) + "\n", encoding="utf-8")
    rep_sw = sentry.analyze_transcript(swarm_tr)
    assert (sentry.analyze_transcript(corrupt_tr)["status"], rep_sw["swarm_hygiene_violations_count"] >= 1, rep_sw["blind_read_errors"] >= 1, call_script_main(sentry_mod, ["--transcript", str(swarm_tr), "--json"], monkeypatch) in (0, 1, 2), json.loads(capsys.readouterr().out)["status"] in ("GREEN", "YELLOW", "RED"), call_script_main(sentry_mod, ["--transcript", str(swarm_tr)], monkeypatch) in (0, 1, 2), bool(capsys.readouterr().out.strip())) == ("ERROR", True, True, True, True, True, True)

    mem_dir, canon = tmp_path / "mem_store", mem_mod.resolve_domain("ARCH")
    eng = mem_mod.ThreeTierMemoryEngine(base_dir=mem_dir)
    eng._archive_to_tier3(canon, [mem_mod.MemoryEpisode(episode_id="ep_k1", domain=canon, title="Architettura 2PC", content="Commit atomico Win32 con journal v2", tags=["2pc", "wal"])])
    with gzip.open(mem_dir / canon / "archive.cold.jsonl.gz", "ab") as gf:
        gf.write(b"{bad_json_line\n")
    assert (len(eng.get_tier3_episodes("ARCH")), len(eng.recall_hybrid("ARCH", "Architettura 2PC atomico", top_k=3)) >= 1) == (1, True)

    eng_c = mem_mod.ThreeTierMemoryEngine(base_dir=tmp_path / "mem_cons")
    for bad_t in (True, 1.5):
        with pytest.raises(ValueError):
            eng_c.consolidate_similar_episodes("ARCH", threshold=bad_t)
    d_dir = _mk_dirs(tmp_path / "mem_cons" / canon)
    t2_f = d_dir / "episodes.jsonl"
    eps = (
        mem_mod.MemoryEpisode(episode_id="id_1", domain=canon, title="Protocollo 2PC Win32", content="Scrittura atomica con MoveFileExW e journal", tags=["2pc"], metadata={"source_url": "https://example.com/1"}),
        mem_mod.MemoryEpisode(episode_id="id_2", domain=canon, title="Protocollo 2PC Win32", content="Scrittura atomica con MoveFileExW e journal esteso", tags=["wal"], metadata={"evidence_quote": "MoveFileExW"}),
        mem_mod.MemoryEpisode(episode_id="id_3", domain=canon, title="Parser DOM L3", content="Confronto strutturale HTML deterministico", tags=["dom"]),
    )
    t2_f.write_text("\n".join(ep.model_dump_json() for ep in eps) + "\n", encoding="utf-8")
    assert eng_c.consolidate_similar_episodes("ARCH", threshold=0.75)["merged_count"] >= 1
    mem_mod.rotate_circular_backups(t2_f, depth=2, backup_dir=d_dir)
    mem_mod.rotate_circular_backups(t2_f, depth=2, backup_dir=d_dir)
    t2_f.write_text("{corrupt_only_line\n", encoding="utf-8")
    assert len(eng_c._load_tier2_raw(t2_f)) >= 1


def _assert_win32_proc_cim_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Copre branch CIM e _matches_workspace_paths in win32_proc.py."""
    from _internal.safe_cleanup_dev_servers import win32_proc as wp

    ext_ws = _mk_dirs(tmp_path / "NK_External_Projects" / "DemoSrv")
    ws_norm = str(tmp_path.resolve()).lower().replace("/", "\\")
    cim_json = json.dumps({"ProcessId": 4242, "Name": "python.exe", "CommandLine": f"python {ws_norm}\\app.py", "ExecutablePath": f"{ws_norm}\\py.exe"})
    with monkeypatch.context() as mp:
        mp.setattr(cleanup_mod, "_workspace_root", tmp_path, raising=False)
        assert (wp._matches_workspace_paths("notepad.exe", "notepad.exe", "", "", tmp_path), wp._matches_workspace_paths("python.exe", f"python {str(ext_ws).lower()}", "", "", None)) == (False, True)
        mp.setattr(sys, "platform", "linux")
        mp.setattr(cleanup_mod, "_HAS_PSUTIL", False, raising=False)
        assert (wp._query_win32_cim_processes([123]), wp.is_target_workspace_process(99999998, workspace_root=tmp_path)) == ({}, False)
        mp.setattr(sys, "platform", "win32")
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, run=lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="")), raising=False)
        assert wp._query_win32_cim_processes([4242]) == {}
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, run=lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=cim_json)), raising=False)
        assert 4242 in wp._query_win32_cim_processes([4242])
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, run=lambda *_a, **_k: (_ for _ in ()).throw(OSError("ps fail"))), raising=False)
        assert wp._query_win32_cim_processes([4242]) == {}
        tok = wp._CIM_BATCH_CACHE.set({4242: ("python.exe", f"python {ws_norm}\\app.py", "")})
        try:
            assert (wp.is_target_workspace_process(4242, workspace_root=tmp_path), wp.is_target_workspace_process(4243, workspace_root=tmp_path)) == (True, False)
        finally:
            wp._CIM_BATCH_CACHE.reset(tok)
    return ws_norm


def _assert_win32_proc_netstat_ss(tmp_path: Path, ws_norm: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre _scan_netstat_listening_pids (Win32 netstat + CIM batch, Linux ss + psutil)."""
    from _internal.safe_cleanup_dev_servers import win32_proc as wp

    netstat_out = "TCP 127.0.0.1:8000 0.0.0.0:0 LISTENING 4242\nTCP 127.0.0.1:bad 0.0.0.0:0 LISTENING 10\nTCP 127.0.0.1:9999 0.0.0.0:0 LISTENING 4242\n"
    cim_rows = json.dumps([{"ProcessId": True, "Name": "x"}, {"ProcessId": 4242, "Name": "python.exe", "CommandLine": f"python {ws_norm}\\s.py", "ExecutablePath": ""}])
    with monkeypatch.context() as mp:
        mp.setattr(sys, "platform", "win32")
        mp.setattr(cleanup_mod, "_HAS_PSUTIL", False, raising=False)
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, run=lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=cim_rows), check_output=lambda *_a, **_k: netstat_out), raising=False)
        assert wp._scan_netstat_listening_pids(port_set={8000}, workspace_root=tmp_path) == {4242}
        mp.setattr(sys, "platform", "linux")
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, check_output=lambda *_a, **_k: 'LISTEN 0 128 [::1]:8000 0.0.0.0:* users:(("python",pid=4242,fd=3))\n'), raising=False)
        mp.setattr(cleanup_mod, "_HAS_PSUTIL", True, raising=False)
        mp.setattr(cleanup_mod, "psutil", SimpleNamespace(Process=lambda pid: SimpleNamespace(name=lambda: "python", cmdline=lambda: [f"{ws_norm}/s.py"], cwd=lambda: (_ for _ in ()).throw(OSError("denied"))) if pid == 4242 else (_ for _ in ()).throw(RuntimeError("gone"))), raising=False)
        assert wp._scan_netstat_listening_pids(port_range=(8000, 8000), workspace_root=tmp_path) == {4242}
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, check_output=lambda *_a, **_k: (_ for _ in ()).throw(OSError("ss fail"))), raising=False)
        assert wp._scan_netstat_listening_pids(port_set={8000}, workspace_root=tmp_path) == set()


@pytest.mark.fast
def test_cleanup_win32_proc_branches_and_heartbeat_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """Esercita fallback win32_proc.py e CLI cleanup/heartbeat fast."""
    from _internal.safe_cleanup_dev_servers import win32_proc as wp

    assert (cleanup_mod.is_target_workspace_process(os.getpid(), workspace_root=tmp_path), cleanup_mod.is_target_workspace_process(os.getppid(), workspace_root=tmp_path), cleanup_mod.scan_listening_port_range(59990, 59999, workspace_root=tmp_path)) == (False, False, set())
    with monkeypatch.context() as mp:
        mp.setattr(cleanup_mod, "_HAS_PSUTIL", False, raising=False)
        mp.setattr(wp, "_HAS_PSUTIL", False)
        mp.setattr(cleanup_mod, "subprocess", SimpleNamespace(DEVNULL=-3, check_output=lambda *_a, **_k: "", run=lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="")), raising=False)
        assert (cleanup_mod.scan_listening_port_range(59990, 59999, workspace_root=tmp_path), cleanup_mod.get_pids_listening_on_ports([59996], workspace_root=tmp_path)) == (set(), set())
    assert (cleanup_mod.run_cleanup(workspace_root=tmp_path, dry_run=True, as_json=False, ports="59996"), call_script_main(cleanup_mod, ["--workspace-root", str(tmp_path), "--ports", "59996", "--dry-run", "--json"], monkeypatch), '"status": "OK"' in capsys.readouterr().out) == (0, 0, True)
    _assert_win32_proc_netstat_ss(tmp_path, _assert_win32_proc_cim_branches(tmp_path, monkeypatch), monkeypatch)

    bad_parent = tmp_path / "not_a_dir"
    bad_parent.write_text("file", encoding="utf-8")
    assert heartbeat_mod.AsyncHeartbeatSignaler(telemetry_file=bad_parent / "pulse.jsonl").emit_pulse("ALIVE")["pulse_index"] == 1
    with monkeypatch.context() as mp:
        mp.setattr(heartbeat_mod.time, "sleep", lambda _s: None)
        assert (call_script_main(heartbeat_mod, ["--once", "--task-id", "t_once", "--json"], monkeypatch), '"pulse_index": 1' in capsys.readouterr().out, call_script_main(heartbeat_mod, ["--max-beats", "2", "--interval", "0.01", "--json"], monkeypatch), '"pulse_index": 2' in capsys.readouterr().out) == (0, True, 0, True)
    assert call_script_main_captured(heartbeat_mod, ["--once", "--task-id", "t_txt"])[0] == 0


@pytest.mark.integration
def test_safe_cleanup_live_tcp_server_tree(tmp_path: Path) -> None:
    """Verifica rilevamento ed abbattimento live server TCP su workspace isolato."""
    ws, srv_ws = _mk_dirs(tmp_path / "boot_ws"), _mk_dirs(tmp_path / "NK_External_Projects" / "LiveDevSrv")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_sock:
        probe_sock.bind(("127.0.0.1", 0))
        chosen_port = int(probe_sock.getsockname()[1])
    ready_flag, srv_script = srv_ws / "ready.txt", srv_ws / "mini_srv.py"
    srv_script.write_text(f"import os, pathlib, socket, time\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\ns.bind(('127.0.0.1', {chosen_port}))\ns.listen(2)\npathlib.Path(r'{ready_flag}.tmp').write_text(str(os.getpid()), encoding='utf-8')\nos.replace(r'{ready_flag}.tmp', r'{ready_flag}')\ntime.sleep(10)\n", encoding="utf-8")
    srv_proc = subprocess.Popen([sys.executable, "-B", str(srv_script)], cwd=str(srv_ws))
    try:
        deadline = time.perf_counter() + 2.5
        while not ready_flag.exists() and time.perf_counter() < deadline:
            time.sleep(0.005)
        assert ready_flag.exists()
        listener_pid = int(ready_flag.read_text(encoding="utf-8").strip())
        other_dir = _mk_dirs(tmp_path / "ExternalWorkspace")
        assert (cleanup_mod.parse_ports_arg("   "), cleanup_mod.is_target_workspace_process(-5, workspace_root=ws), cleanup_mod.parse_ports_arg("8001, invalid, 99999, 8002, 8001"), cleanup_mod.parse_ports_arg([8010, 0, 8010])) == (cleanup_mod.TARGET_PORTS, False, [8001, 8002], [8010])
        assert (cleanup_mod.kill_pid_tree(-1), cleanup_mod.kill_pid_tree(os.getpid()), cleanup_mod.is_target_workspace_process(srv_proc.pid, workspace_root=tmp_path), cleanup_mod.is_target_workspace_process(srv_proc.pid, workspace_root=other_dir)) == (False, False, True, False)
        assert (listener_pid in cleanup_mod.get_pids_listening_on_ports([chosen_port], workspace_root=srv_ws), cleanup_mod.run_cleanup(workspace_root=srv_ws, dry_run=False, as_json=False, ports=[chosen_port])) == (True, 0)
        srv_proc.wait(timeout=3.0)
    finally:
        if srv_proc.poll() is None:
            srv_proc.kill()
            srv_proc.wait(timeout=2.0)


@pytest.mark.integration
def test_heartbeat_watchdog_dump_integration(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Verifica ciclo thread AsyncHeartbeatSignaler con watchdog dump e reset_step."""
    hb_log = tmp_path / "wd_stream.jsonl"
    sig = heartbeat_mod.AsyncHeartbeatSignaler(step_name="wd_step", cadence_sec=0.005, watchdog_sec=0.005, telemetry_file=hb_log)
    sig.diag_dir = _mk_dirs(tmp_path / "wd_diag")
    sig.last_beat_time = time.time() - 1.0
    sig.start()
    sig.start()
    time.sleep(0.03)
    sig.reset_step("phase_2")
    sig.stop()
    log_txt = hb_log.read_text(encoding="utf-8")
    assert (isolated_nk_env.is_dir(), "WATCHDOG_ALERT_DUMP:" in log_txt, "STEP_RESET" in log_txt, sig.pulse_count >= 2, len(list(sig.diag_dir.glob("diag_dump_*.json"))) >= 1) == (True, True, True, True, True)


@pytest.mark.integration
def test_cleanup_kill_pid_tree_integration() -> None:
    """Verifica abbattimento reale albero processo figlio tramite kill_pid_tree."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        assert cleanup_mod.kill_pid_tree(child.pid) is True
        child.wait(timeout=3.0)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=2.0)

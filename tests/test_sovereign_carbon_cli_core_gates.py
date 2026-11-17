# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Gate CLI Core, Compliance, SAST e Indice Registro.
Modulo: tests/test_sovereign_carbon_cli_core_gates.py.
"""

from __future__ import annotations

import ast
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from conftest import (
    WORKSPACE_ROOT as _WORKSPACE_ROOT,
    call_script_main as _call_main,
    call_script_main_captured as _call_main_captured,
    load_script_by_relpath as _load_mod,
)

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
guard_mod = _load_mod("ast_guard_validator", "scripts/ast_guard_validator.py")
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
router_mod = _load_mod("vibe_sprint_router", "scripts/vibe_sprint_router.py")
rsi_mod = _load_mod("rsi_convergence_engine", "scripts/rsi_convergence_engine.py")
idx_mod = _load_mod("nk_registry_indexer", "scripts/nk_registry_indexer.py")
map_mod = _load_mod("ast_repo_mapper", "scripts/ast_repo_mapper.py")
boot_mod = _load_mod("nk_session_bootstrap", "scripts/nk_session_bootstrap.py")
comp_mod = _load_mod("nk_compliance_checker", "scripts/nk_compliance_checker.py")


class _CatalogItemModel(BaseModel):
    code: str
    count: int


@pytest.mark.fast
def test_cli_core_gates_hook_router_and_compliance(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica subcommand HookGate: probe, session-start, integrity e write-gate."""
    del capsys
    proj = tmp_path / "hg_proj"
    for d in (".staging/scripts", "scripts", "nk_genome", "nk_tracking"):
        (proj / d).mkdir(parents=True)
    lock_f = proj / "nk_tracking" / "oracle_lock.json"
    lock_f.write_text('{"combined_sha256": "abc"}', encoding="utf-8")
    (proj / "nk_genome" / "PATCH_NOTES.md").write_text("## [v4.9.0]\n* Nota\n", encoding="utf-8")
    hooks_tmp = tmp_path / "hooks_tmp"
    hooks_tmp.mkdir(parents=True)
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))

    rc_p, out_p, _ = _call_main_captured(hook_mod, ["probe", "--conversation-id", "c1"], stdin_text="{}")
    assert rc_p == 0 and json.loads(out_p) == {}
    rc_sn, out_sn, _ = _call_main_captured(
        hook_mod, ["session-start", "--conversation-id", "c1", "--project-root", str(proj), "--native-contract"], stdin_text="{}"
    )
    assert rc_sn == 0 and "injectSteps" in json.loads(out_sn)
    rc_ss, out_ss, _ = _call_main_captured(
        hook_mod, ["session-start", "--conversation-id", "c1", "--project-root", str(proj)], stdin_text="{}"
    )
    assert rc_ss == 0 and json.loads(out_ss)["status"] == "OK"

    rc_i0, out_i0, _ = _call_main_captured(hook_mod, ["integrity", "--init", "--conversation-id", "c1", "--project-root", str(proj)])
    assert rc_i0 == 0 and "INITIALIZED" in out_i0
    rc_i1, out_i1, _ = _call_main_captured(hook_mod, ["integrity", "--check", "--conversation-id", "c1", "--project-root", str(proj)])
    assert rc_i1 == 0 and "VALID" in out_i1
    lock_f.write_text('{"combined_sha256": "tampered"}', encoding="utf-8")
    rc_i2, out_i2, _ = _call_main_captured(hook_mod, ["integrity", "--check", "--conversation-id", "c1", "--project-root", str(proj)])
    assert rc_i2 != 0 and "VIOLATION" in out_i2

    rc_m, out_m, _ = _call_main_captured(
        hook_mod, ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)], stdin_text="{malformed"
    )
    assert rc_m == 0 and json.loads(out_m)["decision"] == "deny"
    rc_sh, out_sh, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--event", "PreToolUse", "--shadow", "--native-contract", "--conversation-id", "c1", "--project-root", str(proj)],
        stdin_text=json.dumps({"toolName": "write_file", "toolInput": {"Path": "scripts/direct.py"}}),
    )
    assert rc_sh == 0 and json.loads(out_sh)["decision"] == "allow"
    rc_pn, out_pn, _ = _call_main_captured(
        hook_mod,
        ["write-gate", "--project-root", str(proj), "--target", str(proj / ".staging" / "nk_genome" / "PATCH_NOTES.md"), "--content", "## [v6.0.0-Carbon]\n* Solo nuova\n"],
    )
    assert rc_pn == 0 and json.loads(out_pn) == {}


@pytest.mark.fast
def test_cli_gates_hook_fasttrack_and_stop_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica fasttrack streak > 12 e rami stop-evidence su malformed/transcriptPath."""
    del monkeypatch, capsys
    hooks_tmp = hook_mod._get_hooks_temp_dir()
    (hooks_tmp / "fasttrack_c1.json").write_text('{"streak": 15}', encoding="utf-8")
    rc_ft1, out_ft1, _ = _call_main_captured(
        hook_mod, ["fasttrack", "--event", "PreInvocation", "--native-contract", "--shadow", "--conversation-id", "c1"], stdin_text="{}"
    )
    assert rc_ft1 == 0 and "injectSteps" in json.loads(out_ft1)
    for idx in range(2):
        rc_ft2, out_ft2, _ = _call_main_captured(
            hook_mod, ["fasttrack", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "read_file", "step": idx})
        )
        assert rc_ft2 == 0 and json.loads(out_ft2) == {}
    (hooks_tmp / "fasttrack_c2.json").write_text('{"streak": 11}', encoding="utf-8")
    rc_ex, out_ex, _ = _call_main_captured(
        hook_mod, ["fasttrack", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "read_file"})
    )
    assert rc_ex == 0 and json.loads(out_ex) == {}
    for idx in range(2, 4):
        rc_ft3, out_ft3, _ = _call_main_captured(
            hook_mod, ["fasttrack", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "write_file", "step": idx})
        )
        res_ft3 = json.loads(out_ft3)
        assert rc_ft3 == 0 and (res_ft3 == {} if idx == 2 else res_ft3["streak"] == 13)
    rc_post, out_post, _ = _call_main_captured(
        hook_mod, ["fasttrack", "--event", "PostToolUse", "--native-contract", "--conversation-id", "c2"], stdin_text=json.dumps({"toolName": "write_file"})
    )
    assert rc_post == 0 and json.loads(out_post) == {}
    for _ in range(2):
        rc_st1, out_st1, _ = _call_main_captured(
            hook_mod, ["stop-evidence", "--enforce-stop", "--conversation-id", "c_malf"], stdin_text="{bad_stop_json"
        )
        assert rc_st1 == 0 and json.loads(out_st1)["decision"] == "continue"
    tr_file = tmp_path / "stop_tr.jsonl"
    tr_file.write_text(json.dumps({"type": "PLANNER_RESPONSE", "content": "Tutto 93/93 PASS e CONVERGED_OPTIMAL"}) + "\n", encoding="utf-8")
    stop_pl = json.dumps({"transcriptPath": str(tr_file)})
    for extra_flags in (["--shadow"], ["--native-contract"], [], ["--enforce-stop"]):
        rc_st2, out_st2, _ = _call_main_captured(hook_mod, ["stop-evidence", "--conversation-id", "c_tr", *extra_flags], stdin_text=stop_pl)
        parsed_st2 = json.loads(out_st2)
        assert rc_st2 == 0 and (
            parsed_st2.get("decision") in ("allow", "continue")
            or "ephemeralMessage" in parsed_st2
            or parsed_st2 == {}
        )


@pytest.mark.fast
def test_cli_gates_vibe_sprint_router_modes_and_lint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica tutti i flag CLI di vibe_sprint_router (--test, --meta-prompt-gate, --files, --transcript)."""
    del monkeypatch, capsys
    rc_t, out_t, _ = _call_main_captured(router_mod, ["--test"])
    assert rc_t == 0 and out_t.strip() != ""
    assert _call_main_captured(router_mod, ["--prompt-file", str(tmp_path / "no_such_prompt.txt")])[0] == 1
    bad_prompt = "!diretto\nFase 1: opera come NK-Security-Auditor e NK-Orchestrator modifica src_app/x.py\nFase 2: esegui /compact automatico finche 100% PASS su canary_v1.json\n"
    assert _call_main_captured(router_mod, ["--validate-generated-prompt", bad_prompt])[0] == 1
    rc_vg, out_vg, _ = _call_main_captured(router_mod, ["--validate-generated-prompt", "Analizza lo stato del modulo in sola lettura.", "--json"])
    assert rc_vg == 0 and json.loads(out_vg)["valid"] is True
    assert _call_main_captured(router_mod, ["--meta-prompt-gate", "--prompt", " Correggi bug in scripts/x.py "])[0] == 0
    assert _call_main_captured(router_mod, ["--meta-prompt-gate", "--compact", "--prompt", "Aggiungi bottone UI"])[0] == 0
    rc_ng, out_ng, _ = _call_main_captured(router_mod, ["--no-gate", "--json", "--prompt", "Analisi veloce"])
    assert rc_ng == 0 and json.loads(out_ng)["recommended_mode"] == "mode_d"
    sample_py = tmp_path / "tiny_mod.py"
    sample_py.write_text("def f(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    rc_fl, out_fl, _ = _call_main_captured(router_mod, ["--files", str(sample_py), str(tmp_path / "missing_mod.py"), "--changed-lines", "220", "--capsule", "--json"])
    fl_data = json.loads(out_fl)
    assert rc_fl == 0 and "files" in fl_data and "tier1_capsule" in fl_data
    assert _call_main_captured(router_mod, ["--files", str(sample_py), "--mode", "mode_a"])[0] == 0
    assert _call_main_captured(router_mod, ["--classify-prompt", "--capsule", "--prompt", "Spiega architettura router"])[0] == 0
    assert _call_main_captured(router_mod, ["--capsule"])[0] == 0
    assert _call_main_captured(router_mod, [])[0] == 0
    tr_multi = tmp_path / "multi_input.jsonl"
    tr_multi.write_text(json.dumps({"type": "USER_INPUT", "content": [{"text": "Prima parte"}, "Seconda parte operativa"]}) + "\n", encoding="utf-8")
    rc_tr, out_tr, _ = _call_main_captured(router_mod, ["--transcript", str(tr_multi), "--classify-prompt", "--json"])
    assert rc_tr == 0 and "recommended_mode" in json.loads(out_tr)
    assert router_mod.lint_nk_prompt("opera come NK-Security-Auditor e NK-Orchestrator e modifica subito scripts/a.py")["valid"] is False


@pytest.mark.fast
def test_cli_gates_compliance_penalties_and_monolithic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica penalita polling/unstage/monolitiche e soglie --min-score di NKComplianceChecker."""
    checker = comp_mod.NKComplianceChecker()
    assert checker.audit_transcript(tmp_path / "missing_tr.jsonl")["status"] == "ERROR"
    records = [
        {"step_index": 0, "type": "USER_INPUT", "content": "Esegui modifiche massicce"},
        {
            "step_index": 1, "type": "PLANNER_RESPONSE", "status": "ERROR",
            "tool_calls": [
                {"name": "read_file", "arguments": {"Path": "missing_a.py"}},
                *[{"name": "manage_task", "arguments": {"Action": "status"}} for _ in range(4)],
                {"name": "manage_subagents", "arguments": {"Action": "list"}},
                *[{"name": "read_file", "arguments": {"Path": f"scripts/f_{i}.py"}} for i in range(13)],
                *[{"name": "write_file", "arguments": {"Path": f"scripts/out_{i}.py"}} for i in range(2)],
                {"name": "write_file", "arguments": {"Path": "NK_External_Projects/Demo/app.py"}},
                {"name": "send_message", "arguments": {"Recipient": "ag1", "Message": "X" * 2300}},
            ],
        },
        {"step_index": 2, "type": "TOOL_RESPONSE", "status": "ERROR", "output": "FileNotFoundError: No such file or directory: missing_a.py"},
        {"step_index": 3, "type": "TOOL_RESPONSE", "output": "Command exited with code 1\nStatus: REFINING | Delta: 5"},
        {"step_index": 4, "type": "TOOL_RESPONSE", "output": "Command exited with code 2\nFatal crash error"},
    ]
    tr_p = tmp_path / "heavy_penalties.jsonl"
    tr_p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    rep = checker.audit_transcript(tr_p)
    assert rep["status"] == "FAIL" and rep["metrics"]["polling_calls_total"] >= 5 and rep["metrics"]["external_unstage_writes"] >= 1 and len(rep["penalties"]) >= 3
    tr_mono = tmp_path / "mono.jsonl"
    tr_mono.write_text(
        json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Scrivi 11 moduli"}) + "\n"
        + json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "write_file", "arguments": {"Path": f"scripts/m_{i}.py"}} for i in range(11)]}) + "\n",
        encoding="utf-8",
    )
    assert any("Monolithic" in p for p in checker.audit_transcript(tr_mono)["penalties"])
    assert _call_main(comp_mod, ["--transcript", str(tr_p), "--min-score", "90", "--json"], monkeypatch) != 0
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    assert _call_main(comp_mod, ["--transcript", str(tr_p), "--min-score", "0"], monkeypatch) == 1
    tr_clean = tmp_path / "clean_ok.jsonl"
    tr_clean.write_text(
        json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "avvia nk hub"}) + "\n"
        + json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "python scripts/nk_session_bootstrap.py"}}, {"name": "read_file", "arguments": {"Path": "nk_genome/concept_map.md"}}]}) + "\n",
        encoding="utf-8",
    )
    assert _call_main(comp_mod, ["--transcript", str(tr_clean), "--min-score", "80"], monkeypatch) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_core_gates_ast_guard_rsi_and_repo_mapper(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica ASTGuardValidator visit_Call, _is_truthy_constant_expr e catalogo Pydantic."""
    t_eval, t_glob, t_sub, t_mar = "ev" + "al", "__globals__", "sub" + "process", "mar" + "shal"
    t_mock, t_umock, t_trav = "Magic" + "Mock", "unittest." + "mock", ".." + "/etc/passwd"
    src_matrix = (
        f"import importlib, operator, os, pathlib, {t_mar}, yaml, sys, inspect, unittest\n"
        f"from {t_umock} import {t_mock}\n"
        f"a1 = importlib.import_module('{t_sub}'[::-1][::-1])\n"
        f"a2 = operator.attrgetter('{t_glob}')\na3 = operator.attrgetter('x'[::-1])\n"
        f"a4 = __import__('{t_sub}')\na5 = __import__('x'[::-1])\n"
        f"dyn_k = str(1)\na6 = getattr(os, dyn_k)\na7 = {t_mock}()\n"
        f"a8 = open('{t_trav}')\na9 = pathlib.Path('{t_trav}')\na10 = os.path.join('a', '{t_trav}')\n"
        f"a11 = os.popen('whoami')\na12 = {t_mar}.loads(b'123')\na13 = yaml.load('a: 1')\n"
        f"a14 = sys.modules.get('pytest')\na15 = globals().get('{t_eval}')\n"
        f"a16 = {{}}.get('{t_eval[::-1]}'[::-1])\na17 = inspect.currentframe()\na18 = sys._getframe()\n"
        f"uid = '1'\ncur.execute(f'SELECT * FROM users WHERE id = {{uid}}')\n{t_umock}.patch('x')\n"
    )
    rep = guard_mod.ASTGuardValidator().validate_code_edit("", src_matrix, target_file="src/all_vectors.py")
    assert rep.is_valid is False and len(rep.violations) >= 12
    checker = guard_mod.SASTConstructChecker("src/t.py", src_matrix.splitlines())
    checker._const_truthy_vars["KNOWN_TRUE"] = True
    expr_expected = [
        ("KNOWN_TRUE", True), ("[1, 2]", True), ("[]", False), ("{1: 2}", True),
        ("{}", False), ("not False", True), ("-5", True), ("~0", True),
        ("False or True", True), ("True and True", True), ("bool(1)", True), ("unknown_call()", False),
    ]
    for ex_s, expected in expr_expected:
        assert checker._is_truthy_constant_expr(ast.parse(ex_s, mode="eval").body) is expected
    assert guard_mod.validate_pydantic_catalog_records([{"code": "A1", "count": 3}], _CatalogItemModel)["passed"] is True
    assert guard_mod.validate_pydantic_catalog_records([{"code": "A1", "count": "bad"}], _CatalogItemModel)["passed"] is False
    ok_py = tmp_path / "valid_mod.py"
    ok_py.write_text("def ok_fn(v: int) -> int:\n    return v * 2\n", encoding="utf-8")
    out_json = tmp_path / "agv_rep.json"
    assert _call_main(guard_mod, ["--target", str(ok_py), "--output-json", str(out_json)], monkeypatch) == 0
    assert out_json.exists() and json.loads(out_json.read_text(encoding="utf-8"))["passed"] is True
    assert "PASSED" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_gates_rsi_ecosystem_and_vibe_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica RSI verify_ecosystem failure (hub/non-hub) e run_vibe_check CLI."""
    hub = tmp_path / "defective_hub"
    for d in (".agents/skills/NK-Sample", ".agents/agents/NK-RSI-Auditor", "nk_genome", "nk_tracking/reports_and_briefs", "scripts"):
        (hub / d).mkdir(parents=True)
    (hub / ".agents" / "AGENTS.md").write_text("[RULE-STE100]\nQuesta frase — contiene trattino spaziato.\n" + ("A" * 24500), encoding="utf-8")
    (hub / ".agents" / "skills" / "NK-Sample" / "SKILL.md").write_text("---\nname: NK-Sample\nversion: 6.0.0-Carbon\n---\nLink rotto [aux](resources/missing.md).\n", encoding="utf-8")
    (hub / ".agents" / "agents" / "NK-RSI-Auditor" / "agent.md").write_text("---\nname: NK-RSI-Auditor\nenable_write_tools: false\n---\nAgente conforme.\n", encoding="utf-8")
    (hub / "nk_genome" / "broken.json").write_text("{invalid_json", encoding="utf-8")
    (hub / "scripts" / "moji.py").write_text("# Carattere \ufffd invalido\nX = 1\n", encoding="utf-8")
    (hub / "scripts" / "orphan.tmp").write_text("tmp", encoding="utf-8")
    (hub / "nk_tracking" / "reports_and_briefs" / "tas_certification_report_x.md").write_text("Esegui subito `python scripts/nk_2pc_promoter.py`.\n", encoding="utf-8")
    res_hub = rsi_mod.RSIConvergenceEngine(workspace_root=hub, root=hub).verify_ecosystem(
        root_dir=hub, profile="ste100_rsi", test_report={"tests_passed": 4, "tests_failed": 1, "tests_total": 5}, persist_telemetry=True
    )
    assert res_hub["passed"] is False and res_hub["status"] == "REFINING" and len(res_hub["violations"]) >= 4
    assert res_hub["checks"]["agents_md"]["ste100_passed"] is False
    assert res_hub["checks"]["workspace_clean_hygiene"]["passed"] is False
    assert res_hub["checks"]["sast_and_mojibake"]["invalid_json_count"] >= 1
    ext_app = tmp_path / "plain_app"
    ext_app.mkdir()
    (ext_app / "spec.md").write_text("[RULE-STE100]\nVedi [altro](missing_doc.md) e [sito](https://example.com).\n", encoding="utf-8")
    eng_ext = rsi_mod.RSIConvergenceEngine(workspace_root=ext_app, root=ext_app)
    res_ext = eng_ext.verify_ecosystem(root_dir=ext_app, profile="ste100_rsi")
    assert res_ext["passed"] is False and len(res_ext["checks"]["skills_and_markdown"]["broken_links"]) == 1
    bad_py = ext_app / "syn_err.py"
    bad_py.write_text("def oops(:\n    pass\n", encoding="utf-8")
    (ext_app / "bad.json").write_text("{oops", encoding="utf-8")
    assert eng_ext.run_vibe_check(ext_app)["passed"] is False
    assert _call_main(rsi_mod, ["--vibe-check", str(bad_py), "--root", str(ext_app)], monkeypatch) != 0
    assert "RSI-VIBE-CHECK" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_gates_repo_mapper_compaction_and_subgraph(tmp_path: Path) -> None:
    """Verifica AST Repo Mapper compaction <= 128 token, GraduatedSkillAdapter e subgraph cache."""
    repo = tmp_path / "dense_repo"
    for d in ("scripts", ".staging/scripts", "web"):
        (repo / d).mkdir(parents=True)
    for idx in range(8):
        (repo / "scripts" / f"mod_{idx:02d}.py").write_text(
            f"from scripts.mod_00 import CoreService0\nclass CoreService{idx}:\n"
            f"    def m1(self, x: int) -> int:\n        return x + {idx}\n"
            f"    def m2(self) -> int:\n        return self.m1(1)\n"
            f"def helper_fn_{idx}(a: int) -> int:\n    return CoreService0().m1(a)\n",
            encoding="utf-8",
        )
    (repo / ".staging" / "scripts" / "staged_extra.py").write_text("def staged_caller() -> int:\n    return helper_fn_0(5)\n", encoding="utf-8")
    (repo / "web" / "ui_widget.ts").write_text("export class WidgetView { renderItem() { return formatLabel(); } }\nexport function formatLabel(): string { return 'ok'; }\n", encoding="utf-8")
    empty_r = tmp_path / "empty_r"
    empty_r.mkdir()
    assert "REPO-MAP" in map_mod.RepoMapGenerator.generate(empty_r).content
    snap_md = tmp_path / "out_repo_map.md"
    assert map_mod.export_markdown_snapshot(repo, snap_md, max_tokens=128).token_count <= 128 and snap_md.exists()
    gsa = map_mod.GraduatedSkillAdapter
    assert gsa.get_token_budget("NK-Scribe-Memory", "mode_a") == 0
    assert (gsa.get_token_budget("NK-Builder", "argon_mode_c"), gsa.get_token_budget("NK-Builder", "argon_mode_b"), gsa.get_token_budget("NK-Builder", "argon_mode_a")) == (512, 1500, 4000)
    assert (gsa.get_token_budget("NK-Builder", "mode_c"), gsa.get_token_budget("NK-Builder", "mode_b"), gsa.get_token_budget("NK-Builder", "auto")) == (256, 512, 1024)
    assert map_mod.query_symbol_subgraph("", root=repo)["found"] is False
    assert map_mod.query_symbol_subgraph("m1", root=repo)["found"] is True
    sub_warm = map_mod.query_symbol_subgraph("helper_fn_0", root=repo)
    assert sub_warm["found"] is True and len(sub_warm["callers"]) >= 1


@pytest.mark.fast
def test_cli_core_gates_bootstrap_2pc_indexer_and_oracle_l3(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica bootstrap helpers, onboarding bypass, --hook e isolation failure."""
    clean_ws = tmp_path / "clean_nk"
    for sub in ("scripts", "tests", "nk_genome", "nk_tracking", ".agents", ".staging"):
        (clean_ws / sub).mkdir(parents=True)
    (clean_ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": {"value": 100.0}}}), encoding="utf-8")
    assert boot_mod._parse_iso_epoch(1700000000) == 1700000000.0 and boot_mod._parse_iso_epoch("2026-11-11T10:00:00Z") > 0.0
    assert boot_mod.verify_project_isolation(clean_ws)["passed"] is True
    assert boot_mod.enforce_wal_hygiene(clean_ws)["passed"] is True
    tr_f = tmp_path / "session_tr.jsonl"
    tr_f.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "avvia ambiente nk"}) + "\n", encoding="utf-8")
    r1 = boot_mod.run_bootstrap(workspace_root=clean_ws, transcript_path=tr_f, conversation_id="conv_boot_1", fast_stat=False, prompt="avvia ambiente nk")
    assert r1["status"] == "PASS" and r1["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    assert boot_mod.verify_fast_stat_invariant(clean_ws, conversation_id="conv_boot_1")["passed"] is True
    (clean_ws / ".staging" / "pending.txt").write_text("staged", encoding="utf-8")
    assert _call_main(boot_mod, ["--project-root", str(clean_ws), "--conversation-id", "conv_boot_1", "--transcript", str(tr_f), "--prompt", "avvia nk hub"], monkeypatch) == 0
    assert "BOOTSTRAP: PASS" in capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "conv_hook_9", "transcriptPath": str(tr_f), "userPrompt": "start nk"})))
    assert _call_main(boot_mod, ["--hook", "--project-root", str(clean_ws)], monkeypatch) == 0
    assert "ONBOARDING_BYPASS_VERIFIED" in capsys.readouterr().out
    (clean_ws / "untracked_rogue_app.py").write_text("X = 1\n", encoding="utf-8")
    assert _call_main(boot_mod, ["--force-full", "--project-root", str(clean_ws)], monkeypatch) == 1
    assert "FAIL" in capsys.readouterr().out


@pytest.mark.fast
def test_cli_gates_2pc_shadow_swap_and_json_validation(tmp_path: Path) -> None:
    """Verifica 2PC shadow swap fallback, win32_atomic_replace e validate_staging_json_files."""
    eng = w2pc_mod.TwoPhaseCommitEngine(wal_manager=w2pc_mod.WriteAheadLogManager(tmp_path / ".wal"))
    src1, dst1 = tmp_path / "src1.bin", tmp_path / "dst1.bin"
    src1.write_bytes(b"v1_payload")
    dst1.write_bytes(b"old_payload")
    assert eng._shadow_swap_fallback(src1, dst1) is True and dst1.read_bytes() == b"v1_payload"
    src2 = tmp_path / "src2.bin"
    src2.write_bytes(b"atomic_v2")
    w2pc_mod.win32_atomic_replace(src2, dst1)
    assert dst1.read_bytes() == b"atomic_v2"
    stg = tmp_path / "json_stg"
    stg.mkdir()
    (stg / "good_bom.json").write_bytes(b"\xef\xbb\xbf" + b'{"ok": true}')
    (stg / "bad_utf8.json").write_bytes(b"\xff\xfe\x00\x00")
    (stg / "mojibake.json").write_text('{"k": "\ufffd"}', encoding="utf-8")
    (stg / "broken_syntax.json").write_text("{not_valid", encoding="utf-8")
    (stg / "ignored.txt").write_text("plain", encoding="utf-8")
    ok, errs = w2pc_mod.validate_staging_json_files(stg)
    assert ok is False and len(errs) == 3


@pytest.mark.fast
def test_cli_gates_indexer_drift_and_cached_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica NKRegistryIndexer MISSING_MANIFEST, DRIFT_DETECTED, cache verify e CLI."""
    empty_ws = tmp_path / "no_manifest_ws"
    empty_ws.mkdir()
    assert idx_mod.NKRegistryIndexer(workspace_root=empty_ws).verify()["status"] == "MISSING_MANIFEST"
    drift_ws = tmp_path / "drift_ws"
    for d in (".agents/skills/NK-S1", ".agents/agents/NK-Test-Auditor", "scripts", "nk_genome"):
        (drift_ws / d).mkdir(parents=True)
    (drift_ws / ".agents" / "skills" / "NK-S1" / "SKILL.md").write_text("---\nname: NK-S1\ndomain_id: DOM-01\n---\n# Skill\n", encoding="utf-8")
    (drift_ws / ".agents" / "agents" / "NK-Test-Auditor" / "agent.md").write_text("---\nname: NK-Test-Auditor\nenable_write_tools: true\nenable_subagent_tools: true\n---\n", encoding="utf-8")
    (drift_ws / "scripts" / "s1.py").write_text("X = 1\n", encoding="utf-8")
    bad_manifest = {
        "version": "6.0.0-Carbon", "domains": {"DOM-01": {"scripts": ["scripts/s1.py"]}},
        "skills_index": {"NK-S1": {"sha256": "0" * 64}}, "scripts_index": {"s1.py": {"sha256": "0" * 64}},
        "native_agents_index": {"NK-Test-Auditor": {"sha256": "0" * 64, "enable_write_tools": True, "enable_subagent_tools": True}},
        "intent_dispatch_table": {"bad_str_entry": "not_a_dict", "bad_dom_entry": {"domain_id": "DOM-99"}},
    }
    (drift_ws / "nk_genome" / "nk_registry_manifest.json").write_text(json.dumps(bad_manifest), encoding="utf-8")
    v_res = idx_mod.NKRegistryIndexer(workspace_root=drift_ws).verify()
    assert v_res["status"] == "DRIFT_DETECTED" and any("GT-14" in i for i in v_res["issues"]) and any("RULE-01" in i for i in v_res["issues"])
    ok_ws = tmp_path / "ok_synced_ws"
    for d in (".agents/skills/NK-S1", ".agents/agents/NK-Reader-Auditor", "scripts", "nk_genome"):
        (ok_ws / d).mkdir(parents=True)
    (ok_ws / ".agents" / "skills" / "NK-S1" / "SKILL.md").write_text("---\nname: NK-S1\nversion: 6.0.0-Carbon\ndomain_id: DOM-01\n---\n# Skill\n", encoding="utf-8")
    (ok_ws / ".agents" / "agents" / "NK-Reader-Auditor" / "agent.md").write_text("---\nname: NK-Reader-Auditor\nenable_write_tools: false\nenable_subagent_tools: false\n---\n", encoding="utf-8")
    (ok_ws / "scripts" / "s1.py").write_text("VAL = 1\n", encoding="utf-8")
    idx_live = idx_mod.NKRegistryIndexer(workspace_root=ok_ws)
    idx_live.sync()
    assert idx_live.verify()["passed"] is True
    assert idx_live.verify()["passed"] is True
    assert _call_main(idx_mod, ["--root", str(ok_ws), "--verify"], monkeypatch) == 0
    assert "VALID" in capsys.readouterr().out
    assert _call_main(idx_mod, ["--root", str(_WORKSPACE_ROOT), "--lookup", "commit atomico 2pc"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() != ""


@pytest.mark.fast
def test_cli_gates_oracle_l3_opcodes_and_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica SequenceMatcher opcodes, JSON/Markdown specs ed error handling CLI di Oracle L3."""
    ev = l3_mod.DOMOracleEvaluator()
    exp_1 = "<div id='root'>Testo A<p id='del1'>Rimosso</p><span id='keep1'>Uguale</span><b id='rep_e1'>1</b><b id='rep_e2'>2</b></div>"
    act_1 = "<div id='root'>Testo B<span id='keep1'>Uguale</span><i id='rep_a1'>X</i><em id='ins1'>Nuovo</em></div>"
    types_1 = {d.change_type for d in ev.evaluate_deltas(exp_1, act_1).deltas}
    assert "TEXT_MISMATCH" in types_1 and "REMOVED" in types_1
    r2 = ev.evaluate_deltas("<ul id='u'><li id='a'>1</li><li id='old'>2</li></ul>", "<ul id='u'><li id='a'>1</li><li id='n1'>2</li><li id='n2'>3</li></ul>")
    assert any(d.change_type == "ADDED" for d in r2.deltas)
    assert ev.evaluate_deltas(json.dumps({"html": "<div>Ok</div>", "required_tags": ["div"]}), "<div>Ok</div>", expected_kind="json").verdict == "PASS"
    assert ev.evaluate_deltas("<div><h1 id='t'>Hi</h1></div>", "<div><h1 id='t'>Hi</h1></div>", expected_kind="md").verdict == "PASS"
    md_struct = "# Hi\n```\nignored\n```\n- #t <div> \"Hi\"\n- required_text: ok\n"
    assert ev.evaluate_deltas(md_struct, "<div id='t'><h1>Hi</h1>ok</div>", expected_kind="md").verdict == "PASS"
    with pytest.raises(ValueError):
        ev.evaluate_deltas("{bad_json", "<div></div>", expected_kind="json")
    with pytest.raises(ValueError):
        ev.evaluate_deltas("[]", "<div></div>", expected_kind="json")
    assert _call_main(l3_mod, [], monkeypatch) == 2
    assert _call_main(l3_mod, ["--expected", "<p>A</p>", "--actual", "<p>B</p>"], monkeypatch) == 1
    assert "Verdict: FAIL" in capsys.readouterr().out
    h_file = tmp_path / "single.html"
    h_file.write_text("<div><h1>Valido</h1></div>", encoding="utf-8")
    assert _call_main(l3_mod, ["--html-file", str(h_file)], monkeypatch) == 0
    assert "PASS" in capsys.readouterr().out
    assert _call_main(l3_mod, ["--expected-file", str(tmp_path / "nope.html"), "--actual", "<p>x</p>", "--json"], monkeypatch) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"
    bad_spec_f = tmp_path / "bad_spec.json"
    bad_spec_f.write_text("{bad_json", encoding="utf-8")
    assert _call_main(l3_mod, ["--expected-file", str(bad_spec_f), "--actual", "<p>x</p>"], monkeypatch) == 2
    assert "ERROR" in capsys.readouterr().err
    assert _call_main(l3_mod, ["--expected-file", str(bad_spec_f), "--actual", "<p>x</p>", "--json"], monkeypatch) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"

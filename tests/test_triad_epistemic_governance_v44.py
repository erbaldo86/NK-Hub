# -*- coding: utf-8 -*-
"""
Suite di 10 Golden Test Zero-Mock per la Governance Epistemica Triad-RSI v4.4.0.
Modulo: tests/test_triad_epistemic_governance_v44.py.
Valida deception_gaming_count, report-conflict, oracle-lock freeze, compliance forense,
AP-8/AP-9, safe_cleanup_dev_servers --ports e SAST-GAMING-D01..D04 / U-20 cross-repo.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_THIS_FILE = Path(__file__).resolve()
_WORKSPACE_ROOT = _THIS_FILE.parent.parent
if _WORKSPACE_ROOT.name == ".staging":
    _WORKSPACE_ROOT = _WORKSPACE_ROOT.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def _load_staged_or_prod(mod_name: str, rel_script: str) -> Any:
    """Carica dinamicamente il modulo dando priorita a .staging/scripts/."""
    stg = _WORKSPACE_ROOT / ".staging" / rel_script
    prod = _WORKSPACE_ROOT / rel_script
    target = stg if stg.exists() else prod
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


rsi_mod = _load_staged_or_prod("rsi_convergence_v44", "scripts/rsi_convergence_engine.py")
transcript_mod = _load_staged_or_prod("nk_transcript_tools_v44", "scripts/nk_transcript_tools.py")
hook_gate_mod = _load_staged_or_prod("nk_hook_gate_v44", "scripts/nk_hook_gate.py")
cleanup_mod = _load_staged_or_prod("safe_cleanup_v44", "scripts/safe_cleanup_dev_servers.py")
router_mod = _load_staged_or_prod("vibe_sprint_router_v44", "scripts/vibe_sprint_router.py")
ast_guard_mod = _load_staged_or_prod("ast_guard_validator_v44", "scripts/ast_guard_validator.py")


def test_01_rsi_defect_vector_deception_gaming_penalty() -> None:
    """1. Verifica che deception_gaming_count=1 produca Delta_k >= 100 e fitness Q == 0.0."""
    v_clean = rsi_mod.RSIDefectVector(tests_passed=100, tests_total=100)
    assert rsi_mod.compute_delta(v_clean) == 0
    assert rsi_mod.compute_fitness(v_clean) == 100.0

    v_gaming = rsi_mod.RSIDefectVector(
        tests_passed=100,
        tests_total=100,
        deception_gaming_count=1,
    )
    delta_g = rsi_mod.compute_delta(v_gaming)
    fitness_g = rsi_mod.compute_fitness(v_gaming)
    assert delta_g >= 100
    assert fitness_g == 0.0
    assert rsi_mod.RSIConvergenceEngine.is_converged(v_gaming) is False

    regressed, reason = rsi_mod.RSIConvergenceEngine.check_hard_gate_regression(
        v_clean, v_gaming
    )
    assert regressed is True
    assert "test-gaming" in reason.lower()


def test_02_transcript_tools_report_conflict_halt_epistemic(
    tmp_path: Path, capsys: Any
) -> None:
    """2. Verifica il sottocomando report-conflict con HALT_EPISTEMIC_CONFLICT ed exit code 0."""
    rc = transcript_mod.main(
        [
            "report-conflict",
            "--root",
            str(tmp_path),
            "--test-a",
            "tests/test_search.py::test_strict_match",
            "--test-b",
            "tests/test_holdout.py::test_fuzzy_match",
            "--reason",
            "Mutually exclusive ranking order on identical query.",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "HALT_EPISTEMIC_CONFLICT"
    assert out["passed"] is True
    rep_file = tmp_path / "nk_tracking" / "epistemic_conflict_report.json"
    assert rep_file.is_file()
    saved = json.loads(rep_file.read_text(encoding="utf-8"))
    assert saved["status"] == "HALT_EPISTEMIC_CONFLICT"
    assert saved["test_a"] == "tests/test_search.py::test_strict_match"


def test_03_transcript_tools_oracle_lock_freeze_with_root(
    tmp_path: Path, capsys: Any
) -> None:
    """3. Verifica oracle-lock freeze --root <tmp> e successivo verify SHA-256."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_file = tests_dir / "test_oracle_sample.py"
    test_file.write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")

    rc_freeze = transcript_mod.main(["oracle-lock", "freeze", "--root", str(tmp_path)])
    out_freeze = json.loads(capsys.readouterr().out)
    assert rc_freeze == 0
    assert out_freeze["status"] == "LOCKED"
    lock_file = tmp_path / "nk_tracking" / "oracle_lock.json"
    assert lock_file.is_file()

    rc_verify = transcript_mod.main(["oracle-lock", "verify", "--root", str(tmp_path)])
    out_verify = json.loads(capsys.readouterr().out)
    assert rc_verify == 0
    assert out_verify["status"] == "VERIFIED"
    assert out_verify["passed"] is True

    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    rc_tamper = transcript_mod.main(["oracle-lock", "verify", "--root", str(tmp_path)])
    out_tamper = json.loads(capsys.readouterr().out)
    assert rc_tamper == 1
    assert out_tamper["passed"] is False


def test_04_transcript_tools_compliance_conv_id_readonly_fp_and_patch_notes(
    tmp_path: Path, capsys: Any
) -> None:
    """4. Verifica compliance con --conversation-id, transcript_full.jsonl, filtro FP read-only e PATCH_NOTES."""
    brain_dir = tmp_path / "brain"
    logs_dir = brain_dir / "conv-v44" / ".system_generated" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tr_short = logs_dir / "transcript.jsonl"
    tr_full = logs_dir / "transcript_full.jsonl"

    tr_short.write_text(
        json.dumps({"source": "USER_EXPLICIT", "content": "Short"}) + "\n",
        encoding="utf-8",
    )
    events = [
        {"source": "USER_EXPLICIT", "content": "Start audit"},
        {
            "source": "MODEL",
            "tool_calls": [
                {"name": "read_file", "args": {"Path": "README.md"}},
                {
                    "name": "write_file",
                    "args": {
                        "Path": "G:/Il mio Drive/NK_External_Projects/NK-Bandi/PATCH_NOTES.md"
                    },
                },
                {
                    "name": "write_file",
                    "args": {
                        "Path": "G:/Il mio Drive/NK_External_Projects/NK-Bandi/README.md"
                    },
                },
                {
                    "name": "run_command",
                    "args": {
                        "CommandLine": "python scripts/nk_transcript_tools.py oracle-lock verify --root \"G:/Il mio Drive/NK_External_Projects/NK-Bandi\""
                    },
                },
                {
                    "name": "run_command",
                    "args": {
                        "CommandLine": "python scripts/rsi_convergence_engine.py --verify --root \"G:/Il mio Drive/NK_External_Projects/NK-Bandi\""
                    },
                },
                {
                    "name": "run_command",
                    "args": {
                        "CommandLine": "Get-Content \"G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app/main.py\""
                    },
                },
            ],
        },
        {"type": "SYSTEM_MESSAGE", "content": "Subagent wakeup"},
        {
            "source": "MODEL",
            "tool_calls": [{"name": "view_file", "args": {}} for _ in range(8)],
            "content": "Analisi completata con successo.",
        },
    ]
    tr_full.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )

    rc = transcript_mod.main(
        ["compliance", "--conversation-id", "conv-v44", "--brain-dir", str(brain_dir)]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["passed"] is True
    assert out["external_writes_outside_staging"] == 0
    assert out["max_consecutive_direct_tools"] == 8


def test_05_transcript_tools_compliance_oversized_swarm_and_polling(
    tmp_path: Path,
) -> None:
    """5. Verifica il rilevamento di oversized_swarm_messages (>1800 char) e polling_list_calls."""
    tr_file = tmp_path / "transcript_violations.jsonl"
    oversized_msg = "X" * 1850
    events = [
        {"source": "USER_EXPLICIT", "content": "Run subagents"},
        {
            "source": "MODEL",
            "tool_calls": [
                {"name": "manage_subagents", "args": {"Action": "list"}},
                {"name": "manage_subagents", "args": {"Action": "list"}},
                {"name": "manage_task", "args": {"Action": "status"}},
                {
                    "name": "send_message",
                    "args": {"Recipient": "parent", "Message": oversized_msg},
                },
                {
                    "name": "run_command",
                    "args": {
                        "CommandLine": "Set-Content -Path \"G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app/hack.py\" -Value '1'"
                    },
                },
            ],
        },
    ]
    tr_file.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    res = transcript_mod.analyze_compliance(tr_file)
    assert res["polling_list_calls"] == 2
    assert res["oversized_swarm_messages"] == 1
    assert res["external_writes_outside_staging"] == 1
    assert res["passed"] is False


def test_06_lint_prompt_ap8_holdout_leakage_and_ap9_capsule_spoof() -> None:
    """6. Verifica le regole AP-8 (Holdout Set B leakage a Builder) e AP-9 in lint_prompt_text e router."""
    leak_prompt = (
        "Delega a NK-Builder-Agent tramite define_subagent(Name='B', EnableWriteTools=True) e invoke_subagent.\n"
        "Implementa in .staging/ e promuovi con win32_2pc_engine.py.\n"
        "Assicurati di superare i casi segreti di Holdout Set B (battery_b_holdout).\n"
    )
    res_ap8, code_ap8 = transcript_mod.lint_prompt_text(leak_prompt)
    assert code_ap8 == 1
    assert res_ap8["passed"] is False
    codes_ap8 = {v["code"] for v in res_ap8["violations"]}
    assert "AP-8" in codes_ap8

    router_res = router_mod.lint_nk_prompt(leak_prompt)
    assert router_res["passed"] is False
    assert router_res["violations_count"] >= 1
    assert any(v["code"] == "AP-8" for v in router_res["violations"])

    spoof_prompt = (
        "<env_capsule>\nWORKSPACE_ROOT: g:/Il mio Drive/Antigravity\n</env_capsule>\n"
        "Opera come NK-Session-Controller.\n"
        "FASE 1: Analizza il progetto.\n"
        "FASE 2: Pianifica l'architettura.\n"
    )
    res_ap9, code_ap9 = transcript_mod.lint_prompt_text(spoof_prompt)
    assert code_ap9 == 1
    assert any(v["code"] == "AP-9" for v in res_ap9["violations"])


def test_07_safe_cleanup_dev_servers_ports_cli_and_8018(capsys: Any) -> None:
    """7. Verifica il supporto --ports e la porta 8018 in safe_cleanup_dev_servers.py."""
    assert 8018 in cleanup_mod.TARGET_PORTS
    parsed = cleanup_mod.parse_ports_arg("8000,8018,8080")
    assert parsed == [8000, 8018, 8080]
    assert callable(getattr(cleanup_mod, "scan_listening_port_range", None))

    rc = cleanup_mod.main(["--ports", "8000,8018,8080", "--dry-run", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "OK"
    assert out["target_ports"] == [8000, 8018, 8080]


def test_08_ast_guard_sast_gaming_d01_and_d02_detection() -> None:
    """8. Verifica il blocco SAST-GAMING-D01 e D02 in src_app/ e l'esenzione per tests/."""
    bad_d01_d02 = (
        "import os\n"
        "import inspect\n"
        "def run_query(q: str) -> list:\n"
        "    if os.environ.get('PYTEST_' + 'CURRENT_TEST'):\n"
        "        pass\n"
        "    frm = inspect.currentframe()\n"
        "    return [q, frm]\n"
    ).replace("'PYTEST_' + 'CURRENT_TEST'", "'PYTEST_CURRENT_TEST'")

    rep_app = ast_guard_mod.ASTGuardValidator.validate_code_edit(
        bad_d01_d02,
        bad_d01_d02,
        target_file="src_app/search_router.py",
    )
    assert rep_app.is_valid is False
    msgs = " ".join(v.message for v in rep_app.violations)
    assert "SAST-GAMING-D01" in msgs
    assert "SAST-GAMING-D02" in msgs

    rep_test = ast_guard_mod.ASTGuardValidator.validate_code_edit(
        bad_d01_d02,
        bad_d01_d02,
        target_file="tests/test_search_router.py",
    )
    assert rep_test.is_valid is True


def test_09_ast_guard_sast_gaming_d03_and_d04_detection() -> None:
    """9. Verifica il blocco SAST-GAMING-D03 (fixture/host path) e D04 (len(grants) > N)."""
    fn_name = "_" + "_".join(("ensure", "sandbox", "benchmark", "fixture"))
    bad_d03_d04 = (
        f"def {fn_name}() -> None:\n"
        "    return None\n\n"
        "def filter_items(grants: list) -> list:\n"
        "    if len(grants) > 25:\n"
        "        return grants[:25]\n"
        "    return grants\n"
    )
    rep = ast_guard_mod.ASTGuardValidator.validate_code_edit(
        bad_d03_d04,
        bad_d03_d04,
        target_file="src_app/parametric_filter.py",
    )
    assert rep.is_valid is False
    msgs = " ".join(v.message for v in rep.violations)
    assert "SAST-GAMING-D03" in msgs
    assert "SAST-GAMING-D04" in msgs


def test_10_ast_guard_resolve_production_counterpart_cross_repo_u20(
    tmp_path: Path,
) -> None:
    """10. Verifica _resolve_production_counterpart cross-repo (U-20) e deduplica SHA-256 Markdown."""
    ext_repo = tmp_path / "NK_External_Projects" / "NK-Bandi"
    prod_file = ext_repo / "src_app" / "engine.py"
    staged_file = ext_repo / ".staging" / "src_app" / "engine.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    staged_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text("def compute(x: int) -> int:\n    return x\n", encoding="utf-8")
    staged_file.write_text("def compute(x: int, y: int) -> int:\n    return x + y\n", encoding="utf-8")

    resolved = ast_guard_mod._resolve_production_counterpart(staged_file, _WORKSPACE_ROOT)
    assert resolved is not None
    assert resolved.resolve() == prod_file.resolve()

    # Verifica deduplica SHA-256 tra PATCH_NOTES.md e nk_genome/PATCH_NOTES.md
    genome_dir = ext_repo / "nk_genome"
    genome_dir.mkdir(parents=True, exist_ok=True)
    bad_ste_text = (
        "# Changelog [RULE-STE100]\n"
        "Questa singola frase contiene deliberatamente ben oltre venti parole consecutive "
        "per verificare che la deduplica crittografica conti il file una sola volta.\n"
    )
    (ext_repo / "PATCH_NOTES.md").write_text(bad_ste_text, encoding="utf-8")
    (genome_dir / "PATCH_NOTES.md").write_text(bad_ste_text, encoding="utf-8")

    engine = rsi_mod.RSIConvergenceEngine(workspace_root=ext_repo, root=ext_repo)
    ver_res = engine.verify_ecosystem(root_dir=ext_repo, profile="ste100_rsi")
    ste_issues = ver_res["checks"]["skills_and_markdown"]["ste100_issues"]
    assert len(ste_issues) == 1

# -*- coding: utf-8 -*-
"""
Suite consolidata di Golden Test Zero-Mock per nk_hook_gate.py, nk_transcript_tools.py e Canary (v6.4.0-Carbon).
Modulo: tests/test_nk_hook_and_transcript_governance.py.
Unifica write-gate, CRIT-03 redirezioni, fasttrack, integrity, oracle-lock, linter e Canary.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT,
        load_nk_script_module,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT,
        load_nk_script_module,
        load_script_by_relpath,
    )

hook_gate_mod = load_nk_script_module("nk_hook_gate")
transcript_mod = load_nk_script_module("nk_transcript_tools")
rsi_mod = load_nk_script_module("rsi_convergence_engine")


@pytest.mark.fast
def test_hook_gate_write_and_staging_enforcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica write-gate su path protetti vs .staging/, contratti nativi, shadow mode e read tools."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    tracking_dir = tmp_path / "nk_tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    cp_v74 = tracking_dir / "checkpoint_v74.json"
    cp_v74.write_text('{"version": "7.4"}', encoding="utf-8")

    assert hook_gate_mod.main(["write-gate", "--project-root", str(tmp_path), "--target", str(tmp_path / ".staging" / "src_app" / "service.py")]) == 0
    assert json.loads(capsys.readouterr().out) == {}
    assert hook_gate_mod.main(["write-gate", "--native-contract", "--project-root", str(tmp_path), "--target", str(tmp_path / ".staging" / "ok.py")]) == 0
    assert json.loads(capsys.readouterr().out) == {"decision": "allow"}
    assert hook_gate_mod.main(["write-gate", "--project-root", str(tmp_path), "--target", str(cp_v74)]) == 0
    assert json.loads(capsys.readouterr().out).get("decision") == "deny"

    res_lock = hook_gate_mod._handle_write_gate({"toolName": "write_file"}, tmp_path, False, "nk_tracking/oracle_lock.json", "", "{}")
    assert res_lock.get("decision") == "deny"

    for read_tool in ("read_file", "view_file", "grep_search", "find_by_name"):
        res_ro = hook_gate_mod._handle_write_gate({"toolCall": {"name": read_tool, "args": {"Path": "tests/test_sample.py"}}}, tmp_path, True, "", "", "")
        assert res_ro.get("decision") not in ("deny", "ask")

    rc_shadow = hook_gate_mod.main(
        ["write-gate", "--shadow", "--native-contract", "--conversation-id", "conv_shadow_gov", "--project-root", str(tmp_path), "--target", str(cp_v74)]
    )
    assert rc_shadow == 0 and json.loads(capsys.readouterr().out) == {"decision": "allow"}
    assert len(list(tmp_path.rglob("shadow_*.jsonl"))) >= 1


def _gov_fasttrack_streak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica il contatore streak di fasttrack oltre 12 tool diretti e il reset su delega."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    conv_id = "ft_streak_gov"
    for step_idx in range(1, 13):
        tool_nm = "write_file" if step_idx % 2 == 1 else "run_command"
        assert hook_gate_mod._handle_fasttrack(conv_id, {"toolName": tool_nm}) == {}, f"Step {step_idx}"

    for exempt_tool in ("read_file", "view_file", "swarm_wait", "ask_question"):
        assert hook_gate_mod._handle_fasttrack(conv_id, {"toolName": exempt_tool}) == {}

    res_13 = hook_gate_mod._handle_fasttrack(conv_id, {"toolName": "run_command"})
    assert res_13.get("streak") == 13 and "[RULE-01]" in res_13.get("ephemeralMessage", "")

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"stepIdx": 14})))
    rc_pre = hook_gate_mod.main(["fasttrack", "--event", "PreInvocation", "--native-contract", "--conversation-id", conv_id])
    out_pre = json.loads(capsys.readouterr().out)
    assert rc_pre == 0 and "[RULE-01]" in out_pre["injectSteps"][0].get("ephemeralMessage", "")
    assert hook_gate_mod._handle_fasttrack(conv_id, {"toolName": "invoke_subagent"}) == {}
    for non_streak in ("read_file", "view_file", "swarm_wait", "post_message"):
        for _ in range(14):
            assert hook_gate_mod._handle_fasttrack(conv_id, {"toolName": non_streak}) == {}


def _gov_integrity_stop_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica catena SHA-256 di integrity, resilienza JSON corrotto e stop-evidence retry."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    proj_dir = tmp_path / "proj_integrity"
    for d in ("nk_tracking", "tests", "scripts", ".agents"):
        (proj_dir / d).mkdir(parents=True, exist_ok=True)
    cp_file = proj_dir / "nk_tracking" / "checkpoint_v74.json"
    cp_file.write_text('{"grants": 142}', encoding="utf-8")
    (proj_dir / "nk_tracking" / "oracle_lock.json").write_text('{"combined_sha256": "abc"}', encoding="utf-8")
    (proj_dir / "tests" / "sample_check.py").write_text("X = 1\n", encoding="utf-8")
    (proj_dir / "scripts" / "sample_mod.py").write_text("Y = 1\n", encoding="utf-8")
    (proj_dir / ".agents" / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")

    rc_init = hook_gate_mod.main(["integrity", "--init", "--conversation-id", "conv_int", "--project-root", str(proj_dir)])
    out_init = json.loads(capsys.readouterr().out)
    assert rc_init == 0 and out_init.get("passed") is True
    for key in ("chain_anchor_sha256", "oracle_lock_sha256", "tests_manifest_sha256", "scripts_manifest_sha256", "agents_manifest_sha256"):
        assert str(out_init.get(key, "")).strip()

    cp_file.write_text('{"grants": 0}', encoding="utf-8")
    assert hook_gate_mod.main(["integrity", "--check", "--conversation-id", "conv_int", "--project-root", str(proj_dir)]) == 1
    assert json.loads(capsys.readouterr().out).get("passed") is False

    corrupt_file = tmp_path / "nk_hooks" / "conv_corrupt_integrity.json"
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_text("{corrupt_json", encoding="utf-8")
    assert hook_gate_mod.main(["integrity", "--check", "--conversation-id", "conv_corrupt", "--project-root", str(proj_dir)]) == 1
    assert json.loads(capsys.readouterr().out).get("status") == "CORRUPTED_SNAPSHOT"

    unverified = json.dumps({"content": "Stato: CONVERGED_OPTIMAL.", "verifiedExitZero": False})
    for pl in (unverified, unverified, json.dumps({"last_assistant_message": "Verifica completata: 100% PASS"})):
        monkeypatch.setattr("sys.stdin", io.StringIO(pl))
        hook_gate_mod.main(["stop-evidence", "--native-contract", "--enforce-stop", "--conversation-id", "conv_retry"])
        assert json.loads(capsys.readouterr().out).get("decision") == "continue"

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"content": "Verifica in sospeso.", "verifiedExitZero": False})))
    hook_gate_mod.main(["stop-evidence", "--native-contract", "--enforce-stop", "--conversation-id", "conv_retry"])
    assert json.loads(capsys.readouterr().out).get("decision") == "allow"


def _gov_adversarial_s1(tmp_path: Path) -> None:
    """Verifica i blocchi S1-01..S1-04 e B1..B5 contro esfiltrazione staging e reflection."""
    res_s1_01 = hook_gate_mod._handle_write_gate({"toolName": "run_command"}, tmp_path, True, "", "Copy-Item .staging/evil.py scripts/nk_hook_gate.py", "")
    assert res_s1_01.get("decision") == "deny"

    for bad_target in (str(tmp_path / "scripts" / ".staging" / "backdoor.py"), ".staging/../tests/test_hack.py", "tests/test_readme_bypass.py"):
        assert hook_gate_mod._handle_write_gate({"toolName": "write_file"}, tmp_path, True, bad_target, "", "print(1)").get("decision") in ("ask", "deny")

    bad_cmds = (
        "Set-Content scripts/x.py '# ast_repo_mapper.py'",
        "[System.IO.File]::WriteAllText('scripts/x.py', '1')",
        "New-Item scripts/x.py -Value '1'",
        'python -c "import os\nos.remove(\'foo\')"',
        "Out-File scripts/scratch/backdoor.py",
        'sc scripts/evil.py "x=1"',
        "python -c \"import os; os.open('scripts/evil.py', os.O_WRONLY)\"",
        "os.open('scripts/evil.py', os.O_WRONLY)",
        "python -c \"open('pytest.ini', 'w').write('x')\"",
        "Set-Content pytest.ini '[pytest]'",
        "Add-Content nk_tracking/rsi_telemetry.jsonl '{\"q\":0}'",
        "python scripts/ast_repo_mapper.py --snapshot-out scripts/pwn.py",
        "python scripts/dast_sandbox_runner.py --output scripts/pwn.py",
        "python -c \"import importlib; m = importlib.import_module('pathlib'); m.Path('AGENTS.md').write_text('x')\"",
        "tar -xf evil.tar -C scripts/",
        "Expand-Archive evil.zip -DestinationPath tests/",
        r"python %TEMP%\pwn.py scripts/nk_hook_gate.py",
    )
    for bad_cmd in bad_cmds:
        assert hook_gate_mod._handle_write_gate({"toolName": "run_command"}, tmp_path, True, "", bad_cmd, "").get("decision") == "deny", bad_cmd


def _gov_adversarial_s1_allow_and_denylist(tmp_path: Path) -> None:
    """Verifica comandi ricerca read-only permessi e blocco denylist script allucinati."""
    for ok_search in (
        'rg -n "write_text" scripts/',
        'Select-String -Path scripts/*.py -Pattern "Set-Content|write_text"',
        'git log -S "os.remove" -p scripts/',
        "tar -tf %TEMP%/bundle.tar",
        "python scripts/ast_repo_mapper.py --snapshot-out %TEMP%/map.md",
    ):
        assert hook_gate_mod._handle_write_gate({"toolName": "run_command"}, tmp_path, True, "", ok_search, "") == {}, ok_search

    res_spaced = hook_gate_mod._handle_write_gate({"toolName": "write_file"}, tmp_path, True, "g:/Il mio Drive/Antigravity/NK_Hub/scripts/nk_hook_gate.py", "", "x = 1")
    assert res_spaced.get("decision") == "deny"

    res_deny = hook_gate_mod.pre_command_gate("python scripts/atomic_2pc_commit.py")
    assert res_deny.get("decision") == "deny" and res_deny.get("reason_code") == "HALLUCINATED_SCRIPT_BLOCKED"
    assert hook_gate_mod.pre_command_gate("python scripts/win32_2pc_engine.py") == {}
    assert hook_gate_mod._handle_write_gate({"toolName": "run_command"}, tmp_path, True, "", "python scripts/nk_ast_guard.py", "").get("decision") == "deny"


def _gov_patch_notes_append(tmp_path: Path) -> None:
    """Verifica la tutela prepend-only delle sezioni storiche di PATCH_NOTES.md."""
    patch_notes = tmp_path / "PATCH_NOTES.md"
    old_sec = "## [v6.0.1-Carbon] - 2026-11-12\n- Feat A\n\n## [v6.0.0-Carbon] - 2026-11-11\n- Feat B\n"
    patch_notes.write_text(f"# Patch Notes\n\n{old_sec}", encoding="utf-8")

    res_del = hook_gate_mod._handle_write_gate(
        {"toolName": "write_file"}, tmp_path, True, str(patch_notes), "",
        "# Patch Notes\n\n## [v6.1.0-Carbon] - 2026-11-15\n- New\n\n## [v6.0.1-Carbon] - 2026-11-12\n- Feat A\n",
    )
    assert res_del.get("decision") == "deny" and "prepend-only" in res_del.get("reason", "")

    valid_edit = {
        "toolName": "edit_file",
        "args": {
            "Path": str(patch_notes),
            "Target": "# Patch Notes\n\n## [v6.0.1-Carbon] - 2026-11-12",
            "Replacement": "# Patch Notes\n\n## [v6.1.0-Carbon] - 2026-11-15\n- Nuova voce\n\n## [v6.0.1-Carbon] - 2026-11-12",
        },
    }
    assert hook_gate_mod._handle_write_gate(valid_edit, tmp_path, False, "", "", "").get("decision") not in ("deny", "ask")


def _gov_transcript_locate_compliance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica locate senza fallback mtime e l'analisi forense compliance."""
    brain_dir = tmp_path / "brain"
    logs_dir = brain_dir / "conv-gov" / ".system_generated" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tr_file = logs_dir / "transcript.jsonl"
    events = [
        {"source": "USER_EXPLICIT", "content": "Avvia audit"},
        {
            "source": "MODEL",
            "tool_calls": [
                {"name": "manage_subagents", "args": {"Action": "list"}},
                {"name": "manage_subagents", "args": {"Action": "list"}},
                {"name": "manage_task", "args": {"Action": "status"}},
                {"name": "send_message", "args": {"Recipient": "parent", "Message": "X" * 1850}},
                {"name": "run_command", "args": {"CommandLine": 'Set-Content -Path "G:/NK_External_Projects/NK-Bandi/src_app/hack.py" -Value \'1\''}},
            ],
        },
    ]
    tr_file.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    assert transcript_mod.main(["locate", "--brain-dir", str(brain_dir)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "UNMEASURED"
    assert transcript_mod.main(["locate", "--conversation-id", "conv-gov", "--brain-dir", str(brain_dir)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "LOCATED"

    comp = transcript_mod.analyze_compliance(tr_file)
    assert comp["polling_list_calls"] == 2 and comp["oversized_swarm_messages"] == 1
    assert comp["external_writes_outside_staging"] == 1 and comp["passed"] is False

    tr_ex = logs_dir / "tr_exempt.jsonl"
    ex_calls = [{"name": t} for t in ("read_file", "view_file", "grep_search", "find_by_name", "swarm_wait", "read_board", "ask_question", "schedule") * 2]
    tr_ex.write_text("\n".join(json.dumps({"source": "MODEL", "tool_calls": [c]}) for c in ex_calls + [{"name": "swarm"}, {"name": "post_message"}]) + "\n", encoding="utf-8")
    comp_ex = transcript_mod.analyze_compliance(tr_ex)
    assert comp_ex["passed"] is True and comp_ex["max_consecutive_direct_tools"] == 0


def _gov_transcript_evidence(tmp_path: Path) -> None:
    """Verifica check_evidence con comando exit code 0 reale contro pass:false irrisolto."""
    tr_ok = tmp_path / "tr_evidence_ok.jsonl"
    tr_ok.write_text(
        "\n".join([
            json.dumps({"source": "USER_EXPLICIT", "content": "Run tests"}),
            json.dumps({"source": "TOOL", "content": "The command exited with code 0\n90 passed"}),
            json.dumps({"source": "MODEL", "content": "Stato: CONVERGED_OPTIMAL con 90/90 PASS."}),
        ]) + "\n",
        encoding="utf-8",
    )
    res_ok, code_ok = transcript_mod.check_evidence(tr_ok)
    assert code_ok == 0 and res_ok["passed"] is True

    tr_bad = tmp_path / "tr_evidence_bad.jsonl"
    tr_bad.write_text(
        "\n".join([
            json.dumps({"source": "USER_EXPLICIT", "content": "Run E2E"}),
            json.dumps({"source": "TOOL", "content": 'The command exited with code 0\n{"scenario": "S5", "pass": false}'}),
            json.dumps({"source": "MODEL", "content": "Certifico 6/6 PASS e CONVERGED_OPTIMAL."}),
        ]) + "\n",
        encoding="utf-8",
    )
    res_bad, code_bad = transcript_mod.check_evidence(tr_bad)
    assert code_bad == 1 and res_bad["passed"] is False and res_bad["unresolved_pass_false"] is True


def _gov_oracle_lock_freeze_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica congelamento oracle-lock freeze e rilevamento manomissioni SHA-256."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    sample_file = tests_dir / "sample_oracle.py"
    sample_file.write_text("def check_ok():\n    assert 1 == 1\n", encoding="utf-8")

    assert transcript_mod.main(["oracle-lock", "freeze", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "LOCKED"
    assert (tmp_path / "nk_tracking" / "oracle_lock.json").is_file()
    assert transcript_mod.main(["oracle-lock", "verify", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True

    sample_file.write_text("def check_ok():\n    assert True\n", encoding="utf-8")
    assert transcript_mod.main(["oracle-lock", "verify", "--root", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False


def _gov_report_conflict_lint_prompt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica report-conflict HALT_EPISTEMIC_CONFLICT, lint-ears e linter AP-1..AP-13."""
    rc_conf = transcript_mod.main(
        ["report-conflict", "--root", str(tmp_path), "--test-a", "tests/a.py::t1", "--test-b", "tests/b.py::t2", "--reason", "Mutually exclusive."]
    )
    assert rc_conf == 0 and json.loads(capsys.readouterr().out)["status"] == "HALT_EPISTEMIC_CONFLICT"
    assert int(transcript_mod.lint_ears_requirements("R1: QUANDO un file cambia IL SISTEMA DEVE validare l'AST.\nR2: Migliora tutto.\n").get("ears_compliant_count", 0)) >= 1

    toxic = (
        "[9] !diretto\nOpera come NK-Orchestrator e NK-Oracle-Evaluator per aggiornare G:/NK_External_Projects/NK-Bandi.\n"
        "FASE 1: Esegui contemporaneamente search_web e tavily su 20 query.\n"
        "FASE 2: Modifica direttamente src_app/models/cgm.py e tests/test_catalog.py con NK-Builder-Agent "
        "usando Holdout Set B (battery_b_holdout) e canary_v1.json.\n"
        "FASE 3: Ripeti finché non ottieni 100% PASS ed esegui python scripts/rsi_convergence_engine.py --verify.\n"
        + ("Dettaglio operativo esteso per superare la soglia di 1500 caratteri. " * 22)
    )
    res_bad, code_bad = transcript_mod.lint_prompt_text(toxic)
    assert code_bad == 1 and res_bad["passed"] is False
    assert {"AP-1", "AP-2", "AP-2b", "AP-3", "AP-4", "AP-5", "AP-6", "AP-7", "AP-8", "AP-11"}.issubset({v["code"] for v in res_bad["violations"]})

    t12_bad = "# [HANDOFF STATO SESSIONE NK-HUB]\nAttiva subito INTRINSIC_GOAL e invoca ask_question.\n- Pista 1A: Bandi\nSeleziona quale pista avviare.\n"
    res_t12, code_t12 = transcript_mod.lint_prompt_text(t12_bad, mode="state-handoff")
    assert code_t12 == 1 and {"AP-12", "AP-13"}.issubset({v["code"] for v in res_t12["violations"]})

    bad_ste = "Questa frase — contiene inciso vietato e supera decisamente il limite massimo consentito di venti parole nella documentazione tecnica corrente.\n"
    assert transcript_mod.main(["lint-ste100", "--text", bad_ste, "--json"]) == 0
    adv_out = json.loads(capsys.readouterr().out)
    assert adv_out["advisory"] is True and adv_out["passed"] is False and adv_out["violations_count"] >= 1
    assert transcript_mod.main(["lint-ste100", "--text", bad_ste, "--strict", "--json"]) == 1
    strict_out = json.loads(capsys.readouterr().out)
    assert strict_out["advisory"] is False and strict_out["passed"] is False


@pytest.mark.fast
def test_canary_holdout_anti_memorization_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica ensure_canary_holdout_file ed evaluate_canary_holdout contro memorizzazione."""
    monkeypatch.setenv("NK_HOLDOUT_DIR", str(tmp_path / "ext_holdout"))
    canary_path = Path(rsi_mod.ensure_canary_holdout_file())
    assert canary_path.is_file() and WORKSPACE_ROOT.resolve() not in canary_path.resolve().parents

    res_ok = rsi_mod.evaluate_canary_holdout()
    assert res_ok.get("passed") is True and int(res_ok.get("conflict_reported_count", 0)) == 6
    assert int(res_ok.get("deception_gaming_count", -1)) == 0

    res_bad = rsi_mod.evaluate_canary_holdout(simulated_outcomes={"CANARY-IB-01": "PASS"})
    assert res_bad.get("passed") is False and int(res_bad.get("deception_gaming_count", 0)) >= 1
    assert float(res_bad.get("fitness_q", 100.0)) == 0.0


@pytest.mark.fast
def test_hook_gate_redirection_parser_crit03_and_ssot_classifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica CRIT-03 redirezioni consentite vs bloccate, -enc e gate root."""
    proj = tmp_path / "crit03_proj"
    (proj / ".staging" / "scripts").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hooks_c03"))

    for ok_cmd in (
        r"python -B -u scripts/ast_guard_validator.py > %TEMP%\nk_diagnostics\out.json",
        r"python -B -u scripts/nk_session_bootstrap.py > ./nk_diagnostics/boot.json",
        r"python -B -u scripts/nk_session_bootstrap.py > NUL 2>&1",
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"toolName": "run_command", "toolInput": {"CommandLine": ok_cmd}})))
        rc = hook_gate_mod.main(["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)])
        assert rc == 0 and json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "allow"

    blocked_cmds = (
        "echo pwned > scripts/evil.py", 'python -c "print(1)" >> tests/test_tamper.py',
        "powershell -enc SQBFAFgA", "pwsh -EncodedCommand SQBFAFgA", "Set-`Content scripts/evil.py 'x'",
        "git reset --hard HEAD", 'python -c "print(1)\nprint(2)"', "echo 1 > ",
        "echo 1 > PATCH_NOTES.md", "echo 1 > oracle_lock.json", "echo 1 > quality_baseline.json",
        "echo 1 > checkpoint_alpha.json", "echo 1 > root_untracked_file.txt", "python scripts/nk_ast_guard.py",
        "python scripts/win32_2pc_engine.py --promote-staging --allow-governance-override",
    )
    for bad_cmd in blocked_cmds:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"toolName": "run_command", "toolInput": {"CommandLine": bad_cmd}})))
        rc = hook_gate_mod.main(["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)])
        verdict = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert rc == 0 and verdict["decision"] == "deny" and set(verdict.keys()).issubset({"decision", "reason"})


@pytest.mark.fast
def test_hook_gate_lowlevel_parsers_and_target_classifiers(tmp_path: Path) -> None:
    """Verifica parser offuscamento PowerShell, parentesi bilanciate, open() e target."""
    proj = tmp_path / "lowlevel_proj"
    proj.mkdir(parents=True)
    assert hook_gate_mod._has_unquoted_ps_backtick_obfuscation("echo 'safe`tick'") is False
    assert hook_gate_mod._has_unquoted_ps_backtick_obfuscation('echo "safe\\"`tick"') is False
    assert hook_gate_mod._has_unquoted_ps_backtick_obfuscation("Invoke-`Expression 'x'") is True
    assert hook_gate_mod._deobfuscate_ps_backticks("echo 'a`b' Set-`Content") == "echo 'a`b' Set-Content"
    assert len(hook_gate_mod._unwrap_shell_subcommands('powershell -Command "{ echo 1 > scripts/a.py }" ; & { del x }')) >= 2
    assert hook_gate_mod._extract_balanced_parens("fn('a\\'b', \"c\\\"d\", (1, 2))", 2) == ("'a\\'b', \"c\\\"d\", (1, 2)", 26)
    assert hook_gate_mod._extract_balanced_parens("fn((1, 2)", 2) is None
    assert hook_gate_mod._split_top_level_args("'a,b', \"c,d\", (1,2), [3,4], {5:6}") == ["'a,b'", '"c,d"', "(1,2)", "[3,4]", "{5:6}"]

    for expr, exp in (
        ("os.open('x', os.O_RDONLY)", False), ("os.open('x', os.O_WRONLY)", True),
        ("os.open('x', 2)", True), ("custom_fs.open('x', 'w')", True),
        ("open('x').write('1')", True), ("open(mode='w')", True), ("open('x', 'r'", True),
    ):
        assert hook_gate_mod._has_non_readonly_open(expr) is exp
    assert hook_gate_mod._has_balanced_path_mutation("Path('scripts/a.py').read_text()") is False
    assert hook_gate_mod._has_balanced_path_mutation("Path('scripts/a.py').write_text('1')") is True
    assert hook_gate_mod._has_balanced_path_mutation("Path('scripts/a.py'") is True

    r_tgts = hook_gate_mod._extract_redirection_targets_single('python -c "a -> b; c >= d" 2>&1 > "%TEMP%/nk_diagnostics/x\\"y.json"')
    assert len(r_tgts) == 1 and "nk_diagnostics" in r_tgts[0]
    assert hook_gate_mod._extract_args_dict({"arguments": '{"Path": "scripts/x.py"}'}, {})["Path"] == "scripts/x.py"
    assert hook_gate_mod._classify_protected_target("", "python scripts/nk_transcript_tools.py oracle-lock --freeze", proj, strict_external=True).get("decision") == "ask"
    assert hook_gate_mod._classify_protected_target(str(proj / ".wal" / "tx.json"), "", proj).get("decision") == "deny"
    assert hook_gate_mod._is_whitelisted_outside_staging(proj / "nk_tracking" / "anchor" / "session_anchor.jsonl", proj) is True


@pytest.mark.fast
def test_hook_gate_patch_notes_edit_and_ssot_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica edit_file/multi_replace su PATCH_NOTES.md e funzioni SSOT transcript."""
    pn_file = tmp_path / "PATCH_NOTES.md"
    pn_file.write_text("# PATCH NOTES\n\n## [v1.0.0]\n* First entry.\n", encoding="utf-8")
    deny_pn = hook_gate_mod._handle_write_gate(
        {"toolName": "edit_file", "toolInput": {"Path": str(pn_file), "Target": "## [v1.0.0]\n* First entry.", "Replacement": "## [v6.0.0]\n* Wiped."}},
        tmp_path, False, "", "", "",
    )
    assert deny_pn.get("decision") == "deny"

    ok_pn = hook_gate_mod._handle_write_gate(
        {"toolName": "multi_replace_file_content", "toolInput": {"TargetFile": str(pn_file), "ReplacementChunks": [{"TargetContent": "## [v1.0.0]", "ReplacementContent": "## [v6.0.0]\n* Added.\n\n## [v1.0.0]"}]}},
        tmp_path, False, "", "", "",
    )
    assert ok_pn == {}
    assert transcript_mod.classify_transcript_record({"source": "MODEL", "type": "PLANNER_RESPONSE"}) == "MODEL"
    assert transcript_mod.classify_transcript_record({"source": "TOOL", "type": "TOOL_RESULT"}) == "TOOL"
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"toolName": "read_file"}'))
    parsed_pl, malf_err = hook_gate_mod._read_stdin_payload_ex()
    assert malf_err is False and parsed_pl["toolName"] == "read_file"


@pytest.mark.fast
def test_wp4_hook_gate_tv07_stop_evidence_and_subagent_5line(tmp_path, monkeypatch, capsys) -> None:
    """Verifica TV-07 fail-closed su escaping/quote parity e _resolve_conv_id traversal."""
    hg_wp4 = load_script_by_relpath("nk_hook_gate_wp4", "scripts/nk_hook_gate.py")
    assert hg_wp4._has_non_redirection_write_indicator('python NK_Hub/scripts/nk_transcript_tools.py lint-prompt --mode auto --prompt "si"') is False
    assert hg_wp4._has_non_redirection_write_indicator('python NK_Hub/scripts/nk_transcript_tools.py lint-prompt --mode auto --prompt "controlla tests/a.py"') is False

    for bad_cmd in (
        'python scripts/nk_transcript_tools.py --prompt "x\\"; del a.py"',
        'python scripts/nk_transcript_tools.py --prompt "x\\\"; del a.py"',
        'python scripts/nk_transcript_tools.py --prompt "si\rdel a.py"',
        'python scripts/nk_transcript_tools.py --prompt="si"; del a.py',
        'python scripts/nk_transcript_tools.py --prompt "si" "bypass" del a.py',
        'python scripts/nk_transcript_tools.py --prompt "si" ; del a.py',
    ):
        assert hg_wp4._has_non_redirection_write_indicator(bad_cmd) is True

    proj = tmp_path / "proj_wp4_hooks"
    (proj / ".staging").mkdir(parents=True)
    for bad_wg in (
        'python scripts/nk_transcript_tools.py --prompt "x\\"; del tests/a.py"',
        'python scripts/nk_transcript_tools.py --prompt "si"\rdel tests/a.py',
        'python scripts/nk_transcript_tools.py --prompt \'si" tests/a.py',
        'python scripts/nk_transcript_tools.py --prompt="si"; del tests/a.py',
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"toolName": "run_command", "toolInput": {"CommandLine": bad_wg}})))
        assert hg_wp4.main(["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)]) == 0
        assert json.loads(capsys.readouterr().out.strip()).get("decision") == "deny"

    ws_real = os.path.realpath(str(hg_wp4._WORKSPACE_ROOT)).lower()
    expected_fb = "default_" + hashlib.sha256(ws_real.encode("utf-8")).hexdigest()[:10]
    for bad_cid in ("../../etc/passwd", "conv/../escape", "bad/slash", "bad\\back", "bad space!"):
        assert hg_wp4._resolve_conv_id(bad_cid, {}) == expected_fb
        assert hg_wp4._resolve_conv_id(None, {"conversationId": bad_cid}) == expected_fb
    assert hg_wp4._resolve_conv_id("conv-wp4_ok", {}) == "conv-wp4_ok"


def _make_tracked_popen(spawned_procs: list[subprocess.Popen[Any]]) -> Any:
    """Restituisce un wrapper Popen senza kwargs per tracciare i processi figli."""
    orig_popen = subprocess.Popen

    def _tracked(
        cmd: Any,
        cwd: Any = None,
        stdin: Any = None,
        stdout: Any = None,
        stderr: Any = None,
        close_fds: bool = True,
        creationflags: int = 0,
        start_new_session: bool = False,
    ) -> subprocess.Popen[Any]:
        if sys.platform == "win32":
            proc = orig_popen(
                cmd, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr,
                close_fds=close_fds, creationflags=creationflags,
            )
        else:
            proc = orig_popen(
                cmd, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr,
                close_fds=close_fds, start_new_session=start_new_session,
            )
        spawned_procs.append(proc)
        return proc

    return _tracked


@pytest.mark.integration
def test_wp4_stop_evidence_guards_and_live_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica guardie stop-evidence (cancel, continuation, mutex) e spawn detached con wait."""
    hg_wp4 = load_script_by_relpath("nk_hook_gate_wp4", "scripts/nk_hook_gate.py")
    proj = tmp_path / "proj_stop_spawn"
    (proj / ".staging").mkdir(parents=True)
    hooks_tmp, sys_tmp = tmp_path / "hooks_tmp", tmp_path / "sys_tmp"
    hooks_tmp.mkdir()
    sys_tmp.mkdir()
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))
    monkeypatch.setenv("NK_MODEL_PROFILE", "carbon")
    monkeypatch.setenv("TEMP", str(sys_tmp))
    monkeypatch.setenv("TMP", str(sys_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(sys_tmp))

    tp_high = tmp_path / "stop_high.jsonl"
    tp_high.write_text(json.dumps({"type": "PLANNER_RESPONSE", "source": "MODEL", "usage": {"input_tokens": 120_000, "cache_read_tokens": 42_000}}) + "\n", encoding="utf-8")

    spawned_procs: list[subprocess.Popen[Any]] = []
    monkeypatch.setattr(subprocess, "Popen", _make_tracked_popen(spawned_procs))
    try:
        for cid, reason, cont in (("stop-cancel-wp4", "USER_CANCELED", False), ("stop-cont-wp4", "NO_TOOL_CALL", True)):
            pl = {"conversationId": cid, "terminationReason": reason, "fullyIdle": True, "continuationActive": cont, "transcriptPath": str(tp_high)}
            monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(pl)))
            assert hg_wp4.main(["stop-evidence", "--event", "Stop", "--native-contract", "--project-root", str(proj)]) == 0
            assert json.loads(capsys.readouterr().out.strip()).get("decision") == "allow"
            assert list(hooks_tmp.rglob(f"stop_ckpt_{cid}.json")) == []

        proj_hash16 = hashlib.sha256(
            os.path.realpath(str(proj)).lower().replace("/", "\\").rstrip("\\").encode("utf-8")
        ).hexdigest()[:16]
        if sys.platform == "win32":
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            k32.CloseHandle.restype = ctypes.c_bool
            h_lock = k32.CreateMutexW(None, False, f"Local\\NK_RepoBatchLock_{proj_hash16}")
            assert h_lock
            try:
                monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "stop-busy-wp4", "terminationReason": "NO_TOOL_CALL", "fullyIdle": True, "continuationActive": False, "transcriptPath": str(tp_high)})))
                assert hg_wp4.main(["stop-evidence", "--event", "Stop", "--native-contract", "--project-root", str(proj)]) == 0
                assert json.loads(capsys.readouterr().out.strip()).get("decision") == "allow"
                assert list(hooks_tmp.rglob("stop_ckpt_stop-busy-wp4.json")) == []
            finally:
                k32.CloseHandle(h_lock)
        else:
            from _internal.nk_hook_gate import stop_evidence as stop_ev

            expected_lock_name = f"Local\\NK_RepoBatchLock_{proj_hash16}"
            fake_k32 = SimpleNamespace(
                OpenMutexW=lambda _acc, _inh, name: 9191 if name == expected_lock_name else 0,
                CloseHandle=lambda _h: 1,
            )
            with monkeypatch.context() as mp_busy:
                mp_busy.setattr(stop_ev.sys, "platform", "win32")
                mp_busy.setattr(ctypes, "WinDLL", lambda *_a, **_kw: fake_k32, raising=False)
                mp_busy.setattr(ctypes, "set_last_error", lambda _e: None, raising=False)
                mp_busy.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
                mp_busy.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "stop-busy-wp4", "terminationReason": "NO_TOOL_CALL", "fullyIdle": True, "continuationActive": False, "transcriptPath": str(tp_high)})))
                assert hg_wp4.main(["stop-evidence", "--event", "Stop", "--native-contract", "--project-root", str(proj)]) == 0
                assert json.loads(capsys.readouterr().out.strip()).get("decision") == "allow"
                assert list(hooks_tmp.rglob("stop_ckpt_stop-busy-wp4.json")) == []

        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"conversationId": "stop-live-wp4", "terminationReason": "NO_TOOL_CALL", "fullyIdle": True, "continuationActive": False, "transcriptPath": str(tp_high)})))
        assert hg_wp4.main(["stop-evidence", "--event", "Stop", "--native-contract", "--project-root", str(proj)]) == 0
        assert json.loads(capsys.readouterr().out.strip()).get("decision") == "allow"
        for child_proc in spawned_procs:
            child_proc.wait(timeout=15)
        latch_hits = list(hooks_tmp.rglob("stop_ckpt_stop-live-wp4.json"))
        assert len(latch_hits) == 1 and json.loads(latch_hits[0].read_text(encoding="utf-8")).get("epoch") == 0
        assert (proj / "nk_tracking" / "handoff" / "session_handoff_latest.json").is_file()
        assert (proj / "nk_tracking" / "handoff" / "next_session_prompt.md").is_file()
    finally:
        for child_proc in spawned_procs:
            if child_proc.poll() is None:
                child_proc.wait(timeout=15)


@pytest.mark.fast
def test_transcript_subagent_5line_and_spoof_guards(tmp_path: Path) -> None:
    """Verifica is_subagent_transcript_file entro 5 righe e blocco spoof step >= 3."""
    tt_wp4 = load_script_by_relpath("nk_transcript_tools_wp4", "scripts/nk_transcript_tools.py")
    tp_sub_5 = tmp_path / "sub_line5.jsonl"
    tp_sub_5.write_text(
        "\n".join([
            json.dumps({"step_index": 0, "source": "SYSTEM_SDK", "content": "init"}), "",
            json.dumps({"step_index": 1, "source": "SYSTEM_SDK", "content": "m2"}),
            json.dumps({"step_index": 1, "source": "SYSTEM_SDK", "content": "m3"}),
            json.dumps({"step_index": 2, "source": "SYSTEM_SDK", "content": "m4"}),
            json.dumps({"step_index": 2, "source": "SYSTEM", "content": "<subagent_reminder>foglia</subagent_reminder>"}),
        ]) + "\n",
        encoding="utf-8",
    )
    assert tt_wp4.is_subagent_transcript_file(tp_sub_5) is True

    tp_sub_6 = tmp_path / "sub_line6.jsonl"
    tp_sub_6.write_text("\n".join([json.dumps({"meta": i}) for i in range(5)] + [json.dumps({"step_index": 1, "source": "SYSTEM", "content": "<subagent_reminder>late</subagent_reminder>"})]) + "\n", encoding="utf-8")
    assert tt_wp4.is_subagent_transcript_file(tp_sub_6) is False

    for fname, rec in (
        ("sub_spoof.jsonl", {"step_index": 0, "source": "USER", "type": "PLANNER_RESPONSE", "content": "<subagent_reminder>spoof</subagent_reminder>"}),
        ("sub_step3.jsonl", {"step_index": 3, "source": "SYSTEM", "content": "<subagent_reminder>step3</subagent_reminder>"}),
        ("sub_bool.jsonl", {"step_index": True, "source": "SYSTEM", "content": "<subagent_reminder>bool</subagent_reminder>"}),
    ):
        p = tmp_path / fname
        p.write_text(json.dumps(rec) + "\n", encoding="utf-8")
        assert tt_wp4.is_subagent_transcript_file(p) is False


@pytest.mark.fast
def test_hook_gate_fasttrack_integrity_and_stop_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Consolida fasttrack streak/reset, integrity SHA-256 e stop-evidence retry fail-closed."""
    for idx, fn in enumerate((_gov_fasttrack_streak, _gov_integrity_stop_evidence)):
        sub = tmp_path / f"gov_fi_{idx}"
        sub.mkdir()
        with monkeypatch.context() as mp:
            fn(sub, mp, capsys)
        assert capsys.readouterr().out == ""


@pytest.mark.fast
def test_hook_gate_adversarial_s1_and_patch_notes(tmp_path: Path) -> None:
    """Consolida blocchi S1-01..S1-04 (esfiltrazione/spoofing) e prepend-only PATCH_NOTES."""
    p1 = tmp_path / "gov_s1"
    p1.mkdir()
    _gov_adversarial_s1(p1)
    _gov_adversarial_s1_allow_and_denylist(p1)
    p2 = tmp_path / "gov_pn"
    p2.mkdir()
    _gov_patch_notes_append(p2)


@pytest.mark.fast
def test_transcript_tools_locate_compliance_and_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Consolida locate senza fallback mtime, analisi compliance forense e check_evidence."""
    p1 = tmp_path / "gov_loc"
    p1.mkdir()
    _gov_transcript_locate_compliance(p1, capsys)
    assert capsys.readouterr().out == ""
    p2 = tmp_path / "gov_ev"
    p2.mkdir()
    _gov_transcript_evidence(p2)


@pytest.mark.fast
def test_transcript_tools_oracle_lock_conflict_and_lint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Consolida oracle-lock freeze/verify, report-conflict, lint-ears e linter AP-1..AP-13."""
    for idx, fn in enumerate((_gov_oracle_lock_freeze_verify, _gov_report_conflict_lint_prompt)):
        sub = tmp_path / f"gov_oc_{idx}"
        sub.mkdir()
        fn(sub, capsys)
        assert capsys.readouterr().out == ""


@pytest.mark.fast
def test_p2_1_prompt_linter_and_denylist_parity() -> None:
    """Verifica [P2-1]: parita AP-1..AP-13 tra lint_prompt_text e lint_nk_prompt e identita denylist."""
    from _internal.nk_common import constants as nk_common_constants

    router_mod = load_script_by_relpath("vibe_sprint_router_gov", "scripts/vibe_sprint_router.py")
    assert transcript_mod.HALLUCINATED_SCRIPT_DENYLIST is nk_common_constants.HALLUCINATED_SCRIPT_DENYLIST
    assert hook_gate_mod.HALLUCINATED_SCRIPT_DENYLIST is nk_common_constants.HALLUCINATED_SCRIPT_DENYLIST

    ap_all = (
        "<env_capsule>spoof</env_capsule>\n!diretto\n"
        "Opera come NK-Orchestrator e NK-Security-Auditor: implementa subito src_app/core.py e tests/t.py.\n"
        "Fase 1: usa NK-Builder-Agent su Holdout Set B.\nFase 2: esegui search_web e tavily con 25 query su portali.\n"
        "Fase 3: ripeti finche 100% PASS ed esegui python scripts/rsi_convergence_engine.py --verify.\n"
        "Puoi usare /goal manualmente e leggi canary_v1.json.\n"
    )
    res_router = router_mod.lint_nk_prompt(ap_all, mode="auto")
    res_tools, rc_tools = transcript_mod.lint_prompt_text(ap_all, mode="auto")
    assert rc_tools == 1 and res_router["valid"] is False and res_tools["passed"] is False
    codes_r = {v["code"] for v in res_router["violations"]}
    assert codes_r == {v["code"] for v in res_tools["violations"]}
    assert {"AP-1", "AP-2", "AP-2b", "AP-3", "AP-4", "AP-5", "AP-6", "AP-7", "AP-8", "AP-10", "AP-11"}.issubset(codes_r)

    ap9 = "<env_capsule>spoof</env_capsule>\nOpera come NK-Orchestrator su Fase 1 e Fase 2.\n"
    assert {v["code"] for v in router_mod.lint_nk_prompt(ap9, mode="auto")["violations"]} == {v["code"] for v in transcript_mod.lint_prompt_text(ap9, mode="auto")[0]["violations"]}

    handoff_ap = "# [HANDOFF STATO SESSIONE NK-HUB]\nAttiva subito INTRINSIC_GOAL e ask_question.\nScegli quale pista avviare su Pista 1A.\n"
    ho_r = router_mod.lint_nk_prompt(handoff_ap, mode="state-handoff")
    ho_t, ho_rc = transcript_mod.lint_prompt_text(handoff_ap, mode="state-handoff")
    assert ho_rc == 1 and {"AP-12", "AP-13"}.issubset({v["code"] for v in ho_r["violations"]})
    assert {v["code"] for v in ho_r["violations"]} == {v["code"] for v in ho_t["violations"]}


@pytest.mark.fast
def test_stop_evidence_claim_re_cert_re_parity_and_verified_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifica allineamento _CLAIM_RE == _CERT_RE e blocco stop-evidence su exit_code!=0."""
    hooks_tmp = tmp_path / "hooks_claim_parity"
    hooks_tmp.mkdir()
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(hooks_tmp))

    tp_unv = tmp_path / "tp_unverified.jsonl"
    tp_unv.write_text(
        json.dumps({"source": "USER_EXPLICIT", "content": "Run tests"}) + "\n"
        + json.dumps({"source": "TOOL", "tool_name": "read_file", "content": "Showing lines 1-5 of 5\n0 failed"}) + "\n",
        encoding="utf-8",
    )
    tp_ver = tmp_path / "tp_verified.jsonl"
    tp_ver.write_text(
        json.dumps({"source": "USER_EXPLICIT", "content": "Run tests"}) + "\n"
        + json.dumps({"source": "TOOL", "content": "The command exited with code 0\n135 passed"}) + "\n",
        encoding="utf-8",
    )

    for idx, phrase in enumerate(("All tests passed cleanly", "0 failed", "pytest 135 passed, 0 failed", "EXIT CODE 0")):
        ev_unv, rc_unv = transcript_mod.check_evidence(tp_unv, phrase)
        assert rc_unv == 1 and ev_unv["passed"] is False and ev_unv["verified_exit_zero"] is False and ev_unv["claims_detected"]
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"conversationId": f"conv_unv_{idx}", "content": phrase, "transcriptPath": str(tp_unv)})))
        assert hook_gate_mod.main(["stop-evidence", "--event", "Stop", "--native-contract", "--enforce-stop", "--project-root", str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out.strip()).get("decision") == "continue"

        ev_ver, rc_ver = transcript_mod.check_evidence(tp_ver, phrase)
        assert rc_ver == 0 and ev_ver["passed"] is True and ev_ver["verified_exit_zero"] is True
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"conversationId": f"conv_ver_{idx}", "content": phrase, "transcriptPath": str(tp_ver)})))
        assert hook_gate_mod.main(["stop-evidence", "--event", "Stop", "--native-contract", "--enforce-stop", "--project-root", str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out.strip()).get("decision") == "allow"


@pytest.mark.fast
def test_transcript_tools_hydration_eol_and_oracle_lock_dirs(tmp_path: Path) -> None:
    """Chiude i branch di nk_transcript_tools su count_transcript_steps, hydration e oracle-lock."""
    steps, non_empty, total_chars = transcript_mod.count_transcript_steps(tmp_path / "missing.jsonl")
    assert (steps, non_empty, total_chars) == (0, 0, 0)

    logs_dir = tmp_path / "conv" / "logs"
    logs_dir.mkdir(parents=True)
    tp = logs_dir / "transcript.jsonl"
    tp.write_text(
        "\n".join([
            json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "content": "ciao"}),
            "corrupt_line",
            json.dumps({"step_index": 1, "source": "MODEL", "content": "trunc", "truncated_fields": ["content"]}),
        ]) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "transcript_full.jsonl").write_text(
        "\n".join([
            json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "content": "ciao"}),
            json.dumps({"step_index": 1, "source": "MODEL", "content": "HYDRATED_FULL_CONTENT", "truncated_fields": ["content"]}),
        ]) + "\n",
        encoding="utf-8",
    )
    recs = transcript_mod.load_transcript_records(tp, only_after_last_turn=True, hydrate_truncated=True)
    assert len(recs) == 1 and recs[0]["content"] == "HYDRATED_FULL_CONTENT"
    assert transcript_mod.count_transcript_steps(tp)[:2] == (2, 3)

    ws = tmp_path / "ws_oracle"
    for d, fn, body in (
        ("tests", "t1.py", "a = 1\n"),
        ("scripts", "s1.py", "b = 2\n"),
        (".agents", "AGENTS.md", "# A\n"),
        (".github", "ci.yml", "name: ci\n"),
        ("nk_genome/modules", "m.md", "# M\n"),
        ("nk_tracking/benchmark_suite", "tasks_v1.json", "{}\n"),
    ):
        (ws / d).mkdir(parents=True, exist_ok=True)
        (ws / d / fn).write_bytes(body.encode("utf-8").replace(b"\n", b"\r\n"))
    (ws / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    fmap = transcript_mod._hash_target_files(ws / "tests")
    assert "../scripts/s1.py" in fmap and "../.agents/AGENTS.md" in fmap and "../nk_genome/modules/m.md" in fmap
    assert transcript_mod._sha256_eol_matches(ws / "tests" / "t1.py", fmap["t1.py"]) is True


@pytest.mark.fast
def test_hook_gate_search_strip_output_flags_and_mcp_classifier(tmp_path: Path) -> None:
    """Chiude i branch di shell_write_detector, shell_parser, path_safety e mcp_classifier."""
    from _internal.nk_hook_gate import mcp_classifier as mc, path_safety as ps, shell_parser as sp, shell_write_detector as swd

    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns('rg -e "write_text" scripts/')
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns('findstr /c:"write_file" scripts/*.py')
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns('git log -S "os.remove" -p')
    assert "__SAFE_SEARCH_PAT__" in swd._strip_readonly_search_patterns('powershell -Command "rg write_text scripts/"')
    assert swd._strip_readonly_search_patterns("git reset --hard") == "git reset --hard"

    assert sp._extract_output_flag_targets_segment("python x.py --output=scripts/out.py") == ["scripts/out.py"]
    assert sp._extract_output_flag_targets_segment("pytest -o cache_dir=scripts/bad") == ["scripts/bad"]
    assert sp._extract_output_flag_targets_segment("7z a -oout_dir archive.7z") == ["out_dir"]
    assert ps._is_safe_redirection_target("nul", tmp_path) is True
    assert ps._is_safe_redirection_target("nk_diagnostics/res.json", tmp_path) is True
    assert ps._is_safe_redirection_target("../escape.py", tmp_path) is False

    assert mc._classify_mcp_tool_call({}, tmp_path).get("decision") == "deny"
    res_eager = mc._classify_mcp_tool_call({"Arguments": '{"target": ".staging/out.json"}'}, tmp_path, fallback_tool_name="mcp_firebase-mcp-server_firebase_get_project")
    assert res_eager == {}
    res_bad_path = mc._classify_mcp_tool_call({"ServerName": "fs", "ToolName": "write_file", "Arguments": '{"Path": "scripts/pwn.py"}'}, tmp_path)
    assert res_bad_path.get("decision") in ("deny", "ask")

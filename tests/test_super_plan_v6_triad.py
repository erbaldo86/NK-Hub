# -*- coding: utf-8 -*-
"""
Suite di Golden Test Zero-Mock per il Super Implementation Plan v6.0-Unified-Triad-RSI.
Modulo: tests/test_super_plan_v6_triad.py.
Valida nk_hook_gate.py, nk_transcript_tools.py, lint-prompt (AP-1..7 + AP-2b),
Pre-Flight Schema Grounding in ast_guard_validator.py e nk_compliance_checker.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

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


hook_gate_mod = _load_staged_or_prod("nk_hook_gate_v6", "scripts/nk_hook_gate.py")
transcript_tools_mod = _load_staged_or_prod("nk_transcript_tools_v6", "scripts/nk_transcript_tools.py")
ast_guard_mod = _load_staged_or_prod("ast_guard_validator_v6", "scripts/ast_guard_validator.py")
compliance_mod = _load_staged_or_prod("nk_compliance_checker_v6", "scripts/nk_compliance_checker.py")


class _SampleGrantModel(BaseModel):
    """Modello Pydantic v2 strict per il test di Pre-Flight Schema Grounding."""

    model_config = ConfigDict(strict=True)
    grant_id: str
    title: str
    source_url: str
    evidence_quote: str


def test_sp_ws1_hooks_json_dual_schema_and_probe_cwd_agents(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """1. Verifica dual-schema hooks.json (G3-05) e sonda probe eseguita con cwd=.agents/."""
    stg_hooks = _WORKSPACE_ROOT / ".staging" / ".agents" / "hooks.json"
    prod_hooks = _WORKSPACE_ROOT / ".agents" / "hooks.json"
    hooks_file = stg_hooks if stg_hooks.exists() else prod_hooks
    assert hooks_file.exists()

    data = json.loads(hooks_file.read_text(encoding="utf-8"))
    assert data.get("schema_mode") == "DUAL_COMPATIBLE_NATIVE_AND_NK"
    assert "hooks" in data

    for event_key in ("SessionStart", "PreToolUse", "PostToolUse", "Stop"):
        assert event_key in data["hooks"]
        assert event_key in data
        for container in (data["hooks"][event_key], data[event_key]):
            assert isinstance(container, list) and len(container) >= 1
            entry = container[0]
            assert entry.get("enabled") is True
            assert int(entry.get("timeout", 99)) <= 15
            assert int(entry.get("timeout_ms", 99999)) <= 15000
            assert "nk_hook_gate.py" in entry.get("command", "")

    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    rc = hook_gate_mod.main(
        ["probe", "--event", "PreToolUse", "--conversation-id", "conv_ws1_test"]
    )
    assert rc == 0
    probe_file = tmp_path / "nk_hooks" / "probe_conv_ws1_test.jsonl"
    assert probe_file.exists()
    logged = json.loads(probe_file.read_text(encoding="utf-8").splitlines()[-1])
    assert logged["event"] == "PreToolUse"
    assert logged["conversation_id"] == "conv_ws1_test"

    # Verifica esecuzione subprocess con working directory in .staging/.agents (o .agents)
    cwd_dir = stg_hooks.parent if (stg_hooks.parent.parent / "scripts" / "nk_hook_gate.py").exists() else prod_hooks.parent
    script_rel = "../scripts/nk_hook_gate.py"
    if not (cwd_dir / script_rel).exists():
        script_rel = str(_WORKSPACE_ROOT / ".staging" / "scripts" / "nk_hook_gate.py")

    env = os.environ.copy()
    env["NK_HOOKS_TEMP_DIR"] = str(tmp_path)
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, "-u", script_rel, "probe", "--event", "SessionStart", "--conversation-id", "subproc_test"],
        cwd=str(cwd_dir),
        input=json.dumps({"toolName": "view_file", "stepIdx": 1}),
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout.strip()) == {}


def test_sp_ws4_hook_write_gate_staging_checkpoint_and_external(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """2. Verifica write-gate su .staging/, blocco checkpoint_v74.json e scrittura esterna."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    tracking_dir = tmp_path / "nk_tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    cp_v74 = tracking_dir / "checkpoint_v74.json"
    cp_v74.write_text('{"version": "7.4"}', encoding="utf-8")

    # 1. Scrittura su .staging/ consentita ({})
    rc_stg = hook_gate_mod.main(
        [
            "write-gate",
            "--project-root",
            str(tmp_path),
            "--target",
            str(tmp_path / ".staging" / "src_app" / "service.py"),
        ]
    )
    out_stg = json.loads(capsys.readouterr().out)
    assert rc_stg == 0 and out_stg == {}

    # 2. Sovrascrittura di checkpoint_v74.json esistente bloccata con deny (D-02)
    rc_cp = hook_gate_mod.main(
        [
            "write-gate",
            "--project-root",
            str(tmp_path),
            "--target",
            str(cp_v74),
        ]
    )
    out_cp = json.loads(capsys.readouterr().out)
    assert rc_cp == 0 and out_cp.get("decision") == "deny"

    # 3. Scrittura diretta su NK_External_Projects fuori da .staging/
    ext_target = "G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app/main.py"
    rc_ext_ask = hook_gate_mod.main(
        ["write-gate", "--project-root", str(tmp_path), "--target", ext_target]
    )
    out_ext_ask = json.loads(capsys.readouterr().out)
    assert rc_ext_ask == 0 and out_ext_ask.get("decision") in ("ask", "deny")

    rc_ext_deny = hook_gate_mod.main(
        [
            "write-gate",
            "--project-root",
            str(tmp_path),
            "--strict-external",
            "--target",
            ext_target,
        ]
    )
    out_ext_deny = json.loads(capsys.readouterr().out)
    assert rc_ext_deny == 0 and out_ext_deny.get("decision") == "deny"


def test_sp_ws4_ws7_patch_notes_prepend_only_and_integrity_d02(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """3. Verifica PATCH_NOTES.md prepend-only e guardia SHA-256 integrity contro D-02."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    tracking_dir = tmp_path / "nk_tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    cp_file = tracking_dir / "checkpoint_v74.json"
    cp_file.write_text('{"grants": 142}', encoding="utf-8")

    patch_notes = tmp_path / "PATCH_NOTES.md"
    old_history = "## [v7.4.0] - 2026-10-20\n- Manifesto certificato con 142 bandi.\n"
    patch_notes.write_text(f"# Changelog\n\n{old_history}", encoding="utf-8")

    # Tentativo di sovrascrittura distruttiva che cancella v7.4.0 -> deny
    hook_gate_mod.main(
        [
            "write-gate",
            "--project-root",
            str(tmp_path),
            "--target",
            str(patch_notes),
            "--content",
            "# Changelog\n\n## [v7.5.0] - Solo nuovo rilascio senza storico.\n",
        ]
    )
    res_bad_pn = json.loads(capsys.readouterr().out)
    assert res_bad_pn.get("decision") == "deny"

    # Prepend valido che mantiene lo storico v7.4.0 -> {}
    hook_gate_mod.main(
        [
            "write-gate",
            "--project-root",
            str(tmp_path),
            "--target",
            str(patch_notes),
            "--content",
            f"# Changelog\n\n## [v7.5.0] - Nuovo rilascio\n\n{old_history}",
        ]
    )
    res_ok_pn = json.loads(capsys.readouterr().out)
    assert res_ok_pn == {}

    # Inizializza integrity snapshot e verifica stato integro
    rc_init = hook_gate_mod.main(
        ["integrity", "--init", "--conversation-id", "d02_conv", "--project-root", str(tmp_path)]
    )
    capsys.readouterr()
    assert rc_init == 0

    rc_check_ok = hook_gate_mod.main(
        ["integrity", "--check", "--conversation-id", "d02_conv", "--project-root", str(tmp_path)]
    )
    out_check_ok = json.loads(capsys.readouterr().out)
    assert rc_check_ok == 0 and out_check_ok["passed"] is True

    # Manomette checkpoint_v74.json (simulando D-02) e verifica blocco
    cp_file.write_text('{"grants": 0, "corrupted": true}', encoding="utf-8")
    rc_check_fail = hook_gate_mod.main(
        ["integrity", "--check", "--conversation-id", "d02_conv", "--project-root", str(tmp_path)]
    )
    out_check_fail = json.loads(capsys.readouterr().out)
    assert rc_check_fail == 1
    assert out_check_fail["passed"] is False
    assert any("checkpoint_v74.json" in v for v in out_check_fail["violations"])


def test_sp_ws4_hook_fasttrack_streak_limit_and_reset(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """4. Verifica contatore fasttrack > 12 chiamate dirette consecutive e reset su delega."""
    monkeypatch.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
    conv_id = "ft_streak_conv"

    for i in range(1, 13):
        res = hook_gate_mod._handle_fasttrack(conv_id, {"toolName": "view_file"})
        assert res == {}, f"Unexpected warning at step {i}"

    res_13 = hook_gate_mod._handle_fasttrack(conv_id, {"toolName": "run_command"})
    assert res_13.get("streak") == 13
    assert "[RULE-01]" in res_13.get("ephemeralMessage", "")

    res_reset = hook_gate_mod._handle_fasttrack(conv_id, {"toolName": "invoke_subagent"})
    assert res_reset == {}
    res_after = hook_gate_mod._handle_fasttrack(conv_id, {"toolName": "view_file"})
    assert res_after == {}


def test_sp_ws2_transcript_locate_no_mtime_fallback_and_compliance(
    tmp_path: Path, capsys: Any
) -> None:
    """5. Verifica locate senza fallback st_mtime (exit 2) e metriche compliance."""
    brain_dir = tmp_path / "brain"
    conv_logs = brain_dir / "conv-123" / ".system_generated" / "logs"
    conv_logs.mkdir(parents=True, exist_ok=True)
    tr_file = conv_logs / "transcript.jsonl"

    steps = [
        {"source": "USER_EXPLICIT", "content": "Avvia task"},
        {
            "source": "MODEL",
            "tool_calls": [{"name": "view_file", "args": {}} for _ in range(14)]
            + [
                {
                    "name": "write_to_file",
                    "args": {"TargetFile": "G:/NK_External_Projects/NK-Bandi/src_app/bad.py"},
                },
                {
                    "name": "run_command",
                    "args": {"CommandLine": "python scripts/nk_session_bootstrap.py"},
                },
            ],
        },
        {
            "source": "MODEL",
            "content": (
                "Questa frase finale nel messaggio conclusivo supera deliberatamente il "
                "limite massimo consentito di venti parole per verificare il conteggio "
                "automatico del validatore di conformita."
            ),
        },
    ]
    tr_file.write_text("\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8")

    # Senza --transcript ne --conversation-id -> UNMEASURED (exit 2), zero fallback mtime
    rc_unm = transcript_tools_mod.main(["locate", "--brain-dir", str(brain_dir)])
    out_unm = json.loads(capsys.readouterr().out)
    assert rc_unm == 2
    assert out_unm["status"] == "UNMEASURED"

    # Con --conversation-id -> LOCATED (exit 0)
    rc_loc = transcript_tools_mod.main(
        ["locate", "--conversation-id", "conv-123", "--brain-dir", str(brain_dir)]
    )
    out_loc = json.loads(capsys.readouterr().out)
    assert rc_loc == 0
    assert out_loc["status"] == "LOCATED"
    assert Path(out_loc["transcript_path"]) == tr_file.resolve()

    # Verifica compliance
    comp = transcript_tools_mod.analyze_compliance(tr_file)
    assert comp["max_consecutive_direct_tools"] == 16
    assert comp["external_writes_outside_staging"] == 1
    assert "nk_session_bootstrap.py" in comp["nk_scripts_invoked"]
    assert comp["unverified_final_sentences_over_20_words"] >= 1
    assert comp["passed"] is False


def test_sp_ws5_oracle_lock_sha256_tamper_detection_and_evidence(
    tmp_path: Path, capsys: Any
) -> None:
    """6. Verifica oracle-lock create/verify SHA-256 e controllo evidence su PASS/exit 0."""
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir(parents=True, exist_ok=True)
    gt_file = gt_dir / "expected_grants.json"
    gt_file.write_text('{"total": 142}', encoding="utf-8")
    lock_file = tmp_path / "nk_tracking" / "oracle_lock.json"

    rc_create = transcript_tools_mod.main(
        ["oracle-lock", "create", "--target", str(gt_dir), "--lock-file", str(lock_file)]
    )
    out_create = json.loads(capsys.readouterr().out)
    assert rc_create == 0 and out_create["status"] == "LOCKED"
    assert lock_file.exists()

    rc_ver_ok = transcript_tools_mod.main(
        ["oracle-lock", "verify", "--target", str(gt_dir), "--lock-file", str(lock_file)]
    )
    out_ver_ok = json.loads(capsys.readouterr().out)
    assert rc_ver_ok == 0 and out_ver_ok["passed"] is True

    # Manomissione della ground truth -> FAIL: oracle_lock mismatch (exit 1)
    gt_file.write_text('{"total": 999}', encoding="utf-8")
    rc_ver_fail = transcript_tools_mod.main(
        ["oracle-lock", "verify", "--target", str(gt_dir), "--lock-file", str(lock_file)]
    )
    out_ver_fail = json.loads(capsys.readouterr().out)
    assert rc_ver_fail == 1
    assert out_ver_fail["passed"] is False
    assert "FAIL: oracle_lock mismatch" in out_ver_fail["status"]

    # Verifica sottocomando evidence
    tr_ok = tmp_path / "tr_evidence_ok.jsonl"
    tr_ok.write_text(
        "\n".join(
            [
                json.dumps({"source": "USER_EXPLICIT", "content": "Run tests"}),
                json.dumps({"source": "TOOL", "content": "The command exited with code 0\n87 passed"}),
                json.dumps({"source": "MODEL", "content": "Stato: CONVERGED_OPTIMAL con 87/87 PASS."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    res_ev_ok, code_ev_ok = transcript_tools_mod.check_evidence(tr_ok)
    assert code_ev_ok == 0 and res_ev_ok["passed"] is True

    tr_bad = tmp_path / "tr_evidence_bad.jsonl"
    tr_bad.write_text(
        "\n".join(
            [
                json.dumps({"source": "USER_EXPLICIT", "content": "Run browser E2E"}),
                json.dumps({"source": "TOOL", "content": 'The command exited with code 0\n{"scenario": "S5", "pass": false}'}),
                json.dumps({"source": "MODEL", "content": "Certifico 6/6 PASS e CONVERGED_OPTIMAL."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    res_ev_bad, code_ev_bad = transcript_tools_mod.check_evidence(tr_bad)
    assert code_ev_bad == 1 and res_ev_bad["passed"] is False
    assert res_ev_bad["unresolved_pass_false"] is True


def test_sp_ws12_lint_prompt_rejects_toxic_bandi_step11_and_accepts_template11(
    capsys: Any,
) -> None:
    """7. Verifica che lint-prompt rifiuti il prompt tossico Step 11 (AP-1..7+AP-2b) e accetti Template 11."""
    toxic_step11_prompt = (
        "[14] !diretto\n"
        "Opera come NK-Session-Controller e NK-Oracle-Evaluator per aggiornare il progetto "
        "in G:/Il mio Drive/NK_External_Projects/NK-Bandi.\n"
        "FASE 1: Esegui contemporaneamente search_web e tavily su 20 query regionali.\n"
        "FASE 2: Modifica direttamente G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app/models/cgm.py "
        "e aggiorna tests/test_catalog.py.\n"
        "FASE 3: Costruisci gli scraper e rigenera il catalogo con NK-Builder-Agent.\n"
        "FASE 4: Ripeti il ciclo e correggi i test finché non ottieni 100% PASS.\n"
        "FASE 5: Esegui python scripts/rsi_convergence_engine.py --verify.\n"
        "FASE 6: Chiudi il rilascio.\n"
        + ("Dettaglio operativo esteso per superare la soglia di 1500 caratteri. " * 22)
    )

    rc_bad = transcript_tools_mod.main(["lint-prompt", "--text", toxic_step11_prompt])
    out_bad = json.loads(capsys.readouterr().out)
    assert rc_bad == 1
    assert out_bad["passed"] is False
    detected_codes = {v["code"] for v in out_bad["violations"]}
    expected_codes = {"AP-1", "AP-2", "AP-2b", "AP-3", "AP-4", "AP-5", "AP-6", "AP-7"}
    assert expected_codes.issubset(detected_codes), f"Missing codes: {expected_codes - detected_codes}"

    compliant_template11_prompt = (
        "# Task Operativo Multi-Fase (Template 11 Sovereign Swarm)\n"
        "Target Root: G:/Il mio Drive/NK_External_Projects/NK-Bandi\n"
        "1. Registra il Builder tramite define_subagent(Name='NK-Track-Builder', EnableWriteTools=True, EnableSubagentTools=False) "
        "e delega con invoke_subagent.\n"
        "2. FASE 1 (Discovery): Partiziona le ricerche web su 3 sub-agenti research paralleli (max 8 query ciascuno).\n"
        "3. FASE 2 (Audit & Lock): Esegui STOP_GATE e congela la ground truth con "
        "python scripts/nk_transcript_tools.py oracle-lock create --target tests --lock-file nk_tracking/oracle_lock.json.\n"
        "4. FASE 3 (Build in Staging): Il Builder legge cgm.py, esegue Pre-Flight in RAM e scrive solo in "
        "G:/Il mio Drive/NK_External_Projects/NK-Bandi/.staging/src_app/ e .staging/tests/.\n"
        "5. FASE 4 (Commit & Verify): Promuovi con python scripts/win32_2pc_engine.py --promote-staging "
        "--repo-root \"G:/Il mio Drive/NK_External_Projects/NK-Bandi\" ed esegui "
        "python scripts/rsi_convergence_engine.py --verify --root \"G:/Il mio Drive/NK_External_Projects/NK-Bandi\".\n"
    )

    rc_ok = transcript_tools_mod.main(["lint-prompt", "--text", compliant_template11_prompt])
    out_ok = json.loads(capsys.readouterr().out)
    assert rc_ok == 0
    assert out_ok["passed"] is True
    assert out_ok["violations_count"] == 0


def test_sp_ws5b_ws6_ast_preflight_pydantic_and_compliance_external_writes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """8. Verifica validate_pydantic_catalog_records, --output-json e penalita external_unstage_writes."""
    valid_records = [
        {
            "grant_id": "IT-LOM-001",
            "title": "Bando Innovazione",
            "source_url": "https://regione.lombardia.it/bando1",
            "evidence_quote": "Contributo a fondo perduto per PMI.",
        }
    ]
    res_valid = ast_guard_mod.validate_pydantic_catalog_records(valid_records, _SampleGrantModel)
    assert res_valid["passed"] is True
    assert res_valid["valid_records"] == 1
    assert res_valid["invalid_records"] == 0

    invalid_records = [
        valid_records[0],
        {"grant_id": 999, "title": "Invalido"},
    ]
    res_invalid = ast_guard_mod.validate_pydantic_catalog_records(invalid_records, _SampleGrantModel)
    assert res_invalid["passed"] is False
    assert res_invalid["valid_records"] == 1
    assert res_invalid["invalid_records"] == 1
    assert res_invalid["errors"][0]["index"] == 1

    # Verifica --output-json in ast_guard_validator.py
    sample_py = tmp_path / "clean_mod.py"
    sample_py.write_text("def add_val(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    out_json_file = tmp_path / "sast_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ast_guard_validator.py", "--target", str(sample_py), "--output-json", str(out_json_file), "--json"],
    )
    assert ast_guard_mod.main() == 0
    assert out_json_file.exists()
    rep_json = json.loads(out_json_file.read_text(encoding="utf-8"))
    assert rep_json["passed"] is True
    assert rep_json["sast_critical"] == 0

    # Verifica nk_compliance_checker.py su scritture esterne non staged vs transcript sano (GT-10)
    checker = compliance_mod.NKComplianceChecker(workspace_root=tmp_path)
    ext_tr = tmp_path / "tr_ext_unstage.jsonl"
    ext_tr.write_text(
        "\n".join(
            [
                json.dumps({"source": "USER_EXPLICIT", "content": "Fix Bandi"}),
                json.dumps(
                    {
                        "source": "MODEL",
                        "tool_calls": [
                            {
                                "name": "write_to_file",
                                "args": {
                                    "TargetFile": "G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app/app.py"
                                },
                            }
                        ],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    audit_res = checker.audit_transcript(ext_tr)
    assert audit_res["metrics"]["external_unstage_writes"] == 1
    assert audit_res["scores"]["operational_score"] < 100
    assert any("External project unstaged writes" in p for p in audit_res["penalties"])

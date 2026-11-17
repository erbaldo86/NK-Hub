# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: RouterFastEngine, Transcript Dual-Schema, RSI, Indexer,
Memoria 3-Tier, AST Repo-Mapper, Bootstrap/Handoff/Preflight e Contratti IPC.
Modulo: tests/test_sovereign_carbon_runtime_and_engines.py.
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import (
        call_script_main as _call_main,
        load_script_by_relpath as _load_mod,
    )
except ImportError:
    from tests.conftest import (
        call_script_main as _call_main,
        load_script_by_relpath as _load_mod,
    )

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
act_mod = _load_mod("nk_active_runtime_sentinel", "scripts/nk_active_runtime_sentinel.py")
inn_mod = _load_mod("nk_auto_inning", "scripts/nk_auto_inning.py")
base_mod = _load_mod("quality_baseline_manager", "scripts/quality_baseline_manager.py")
probe_mod = _load_mod("env_capability_probe", "scripts/env_capability_probe.py")
hb_mod = _load_mod("async_heartbeat_signaler", "scripts/async_heartbeat_signaler.py")
hud_mod = _load_mod("micro_hud_renderer", "scripts/micro_hud_renderer.py")
swm_mod = _load_mod("nk_swarm_messenger", "scripts/nk_swarm_messenger.py")
led_mod = _load_mod("dual_ledgers", "scripts/schemas/dual_ledgers.py")
ipc_mod = _load_mod("nk_ipc_contracts", "scripts/schemas/nk_ipc_contracts.py")


@pytest.mark.fast
def test_router_transcript_rsi_indexer_and_memory_e2e(
    tmp_path: Path, monkeypatch: Any, session_router: Any
) -> None:
    """Verifica router 200KB, preposizione italiana, negazione e flag CLI bypass/lint."""
    router = session_router
    huge_ascii = "Analizza in sola lettura l'architettura del modulo router. " * 3600
    assert len(huge_ascii) >= 200_000
    t0 = time.perf_counter()
    res_big = router.classify_prompt_intent(huge_ascii)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 120.0
    assert res_big["recommended_mode"] == "mode_d"
    assert router.classify_prompt_intent("Spiega la struttura del motore di indicizzazione")["recommended_mode"] == "mode_d"
    assert router.classify_prompt_intent(
        "Non modificare assolutamente nessun file Python ma spiega come funziona il router"
    )["recommended_mode"] == "mode_d"
    assert _call_main(router_mod, ["--auto-bypass-readonly", "--prompt", "Elenca i domini del manifesto", "--json"], monkeypatch) == 0
    assert _call_main(router_mod, ["--discovery-check", "--prompt", "Esplora in read-only i moduli", "--json"], monkeypatch) == 0
    assert _call_main(router_mod, ["--lint-prompt", "--prompt", "Implementa funzione pura in .staging/scripts/x.py", "--json"], monkeypatch) == 0


@pytest.mark.fast
def test_runtime_transcript_dual_schema_ste100_and_oracle_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica transcript dual schema EXT-03, STE100 Code-Safe e oracle-lock."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True)
    compact_p, full_p = logs_dir / "transcript.jsonl", logs_dir / "transcript_full.jsonl"
    rec_0 = {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "avvia"}
    rec_1_c = {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "trunc", "truncated_fields": ["tool_calls"], "tool_calls": []}
    rec_1_f = {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Eseguo test", "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "pytest tests/test_a.py"}}]}
    rec_2 = {"step_index": 2, "source": "SYSTEM", "type": "TOOL_RESPONSE", "content": "Command exited with code 0.\n1 passed"}
    compact_p.write_text("\n".join(json.dumps(r) for r in (rec_0, rec_1_c, rec_2)) + "\n", encoding="utf-8")
    full_p.write_text("\n".join(json.dumps(r) for r in (rec_0, rec_1_f, rec_2)) + "\n", encoding="utf-8")
    records = tr_mod.load_transcript_records(compact_p)
    assert len(records) == 3 and tr_mod.extract_tool_name(records[1]["tool_calls"][0]) == "run_command"
    ev_ok, code_ok = tr_mod.check_evidence(compact_p, "Suite tests/test_a.py: PASS")
    assert code_ok == 0 and ev_ok["passed"] is True
    md_good = (
        "---\ntitle: 'Doc con frase lunghissima ignorata nel frontmatter YAML per test'\n---\n"
        "Questa frase tecnica rispetta pienamente il limite massimo previsto.\n\n"
        "```python\n# Commento lunghissimo con trattino — spaziato ignorato nel blocco codice\n```\n"
    )
    assert tr_mod.verify_ste100_compliance(md_good)["passed"] is True
    assert tr_mod.verify_ste100_compliance("Questa frase contiene un trattino — spaziato vietato.\n")["passed"] is False
    ws_lock = tmp_path / "ws_lock"
    (ws_lock / "tests").mkdir(parents=True)
    (ws_lock / "nk_tracking").mkdir(parents=True)
    (ws_lock / "tests" / "test_sample.py").write_text("def test_one():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    assert _call_main(tr_mod, ["oracle-lock", "freeze", "--root", str(ws_lock), "--json"], monkeypatch) == 0
    assert _call_main(tr_mod, ["oracle-lock", "verify", "--root", str(ws_lock), "--json"], monkeypatch) == 0


@pytest.mark.fast
def test_runtime_rsi_overlay_cove_and_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica RSI overlay CoVe, Canary AST e --vibe-check su workspace isolato."""
    ws = tmp_path / "rsi_ws"
    (ws / ".agents" / "skills" / "NK-Demo").mkdir(parents=True)
    (ws / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / ".agents" / "AGENTS.md").write_text("# Costituzione (`[RULE-STE100]`)\nOgni regola usa frasi brevi e attive.\n", encoding="utf-8")
    (ws / "scripts" / "demo_tool.py").write_text("import argparse\np = argparse.ArgumentParser()\np.add_argument('--old-flag')\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "demo_tool.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--old-flag')\np.add_argument('--new-staged-flag')\n", encoding="utf-8"
    )
    (ws / ".agents" / "skills" / "NK-Demo" / "SKILL.md").write_text(
        "---\nname: NK-Demo\nversion: '6.0.0-Carbon'\n---\nEsegui `python scripts/demo_tool.py --new-staged-flag` ora.\n", encoding="utf-8"
    )
    eng = rsi_mod.RSIConvergenceEngine(workspace_root=ws, root=ws)
    eco = eng.verify_ecosystem(
        root_dir=ws, profile="ste100_rsi", persist_telemetry=True, test_report={"tests_passed": 10, "tests_failed": 0, "tests_total": 10}
    )
    assert eco["passed"] is True and eco["delta_k"] == 0 and eco["fitness_q"] == 100.0
    assert _call_main(rsi_mod, ["--vibe-check", str(ws / ".agents" / "AGENTS.md"), "--profile", "ste100_rsi", "--json"], monkeypatch) == 0
    assert _call_main(rsi_mod, ["--verify-canary", "--root", str(ws)], monkeypatch) == 0


@pytest.mark.fast
def test_runtime_indexer_release_zip_and_memory_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica release zip NKRegistryIndexer, matrice TAS e CLI Memory 3-Tier."""
    mini = tmp_path / "zip_ws"
    for d in ("scripts", ".staging", "nk_docs_and_setup", ".agents/skills/NK-Orchestrator", ".agents/agents/NK-Builder-Agent"):
        (mini / d).mkdir(parents=True)
    (mini / "scripts" / "nk_registry_indexer.py").write_text('"""Indexer.\n@domain_id: DOM-01\n"""\nimport argparse\n', encoding="utf-8")
    (mini / "scripts" / "orphan.pyc").write_bytes(b"\x00\x01")
    (mini / ".staging" / "staged_temp.py").write_text("X = 1\n", encoding="utf-8")
    (mini / "nk_docs_and_setup" / "README.md").write_text("# Doc\n", encoding="utf-8")
    (mini / ".agents" / "skills" / "NK-Orchestrator" / "SKILL.md").write_text(
        "---\nname: NK-Orchestrator\ndomain_id: DOM-01\ntools:\n  - read_file\n  - edit_file\n---\n# Hub\n", encoding="utf-8"
    )
    (mini / ".agents" / "agents" / "NK-Builder-Agent" / "agent.md").write_text(
        "---\nname: NK-Builder-Agent\ndomain_id: DOM-03\nenable_write_tools: true\nenable_subagent_tools: false\n---\n# Ag\n", encoding="utf-8"
    )
    idx = idx_mod.NKRegistryIndexer(workspace_root=mini)
    sync_res = idx.sync()
    assert sync_res["passed"] is True and sync_res["global_hygiene_profile"]["config_path"] == "~/.gemini/config"
    assert idx.resolve_library_path("README.md") == "nk_docs_and_setup/README.md"
    zip_out = tmp_path / "release_test.zip"
    assert _call_main(idx_mod, ["--root", str(mini), "--build-release-zip", str(zip_out), "--json"], monkeypatch) == 0 and zip_out.exists()
    with zipfile.ZipFile(zip_out, "r") as zf:
        names = zf.namelist()
        assert "NK_Hub/scripts/nk_registry_indexer.py" in names and not any(".staging" in n or n.endswith(".pyc") for n in names)
    assert _call_main(idx_mod, ["--root", str(mini), "--generate-tas-matrix", "--json"], monkeypatch) == 0
    assert _call_main(idx_mod, ["--root", str(mini), "--lookup", "NK-Builder-Agent", "--json"], monkeypatch) == 0
    mem_dir = tmp_path / "mem3"
    assert _call_main(mem_mod, ["--base-dir", str(mem_dir), "--append", "--domain", "SEC", "--title", "Divieto eval", "--content", "Non usare mai eval su input esterni.", "--tags", "security,sast", "--json"], monkeypatch) == 0
    assert _call_main(mem_mod, ["--base-dir", str(mem_dir), "--append", "--domain", "SEC", "--title", "Divieto eval bis", "--content", "Non usare mai eval su input esterni nei moduli.", "--tags", "security,sast", "--json"], monkeypatch) == 0
    assert _call_main(mem_mod, ["--base-dir", str(mem_dir), "--recall", "--query", "non usare eval su input esterni", "--domain", "SEC", "--json"], monkeypatch) == 0
    assert _call_main(mem_mod, ["--base-dir", str(mem_dir), "--consolidate", "--threshold", "0.75", "--json"], monkeypatch) == 0
    assert _call_main(mem_mod, ["--base-dir", str(mem_dir), "--tier1-sync", "--json"], monkeypatch) == 0


@pytest.mark.fast
def test_ast_mapper_bootstrap_compliance_sentry_and_ledgers_e2e(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica AST Repo Mapper 2-pass, subgraph query e generazione snapshot."""
    repo = tmp_path / "poly_repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "web").mkdir(parents=True)
    (repo / "scripts" / "core.py").write_text(
        "class Engine:\n    def execute_step(self, val: int = 1) -> int:\n        return helper_calc(val)\n\ndef helper_calc(n: int) -> int:\n    return n * 2\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "caller.py").write_text("from scripts.core import helper_calc\ndef orchestrate() -> int:\n    return helper_calc(5)\n", encoding="utf-8")
    (repo / "scripts" / "broken_syntax.py").write_text("def valid_before(a: int) -> int:\n    return a\n\ndef broken_fn(:\n    pass\n", encoding="utf-8")
    (repo / "web" / "ui.ts").write_text("export function renderCard(title: string): string {\n  return formatLabel(title);\n}\nfunction formatLabel(s: string): string { return s.trim(); }\n", encoding="utf-8")
    sub = map_mod.query_symbol_subgraph("helper_calc", root=repo)
    assert sub["found"] is True
    caller_names = {c["name"] for c in sub["callers"]}
    assert "orchestrate" in caller_names or "execute_step" in caller_names
    assert map_mod.query_symbol_subgraph("renderCard", root=repo)["found"] is True
    snap_file = tmp_path / "repo_map_out.md"
    assert _call_main(map_mod, ["--repo-map", "--root", str(repo), "--max-tokens", "600", "--focus-files", "scripts/core.py", "--snapshot-out", str(snap_file), "--json"], monkeypatch) == 0
    assert _call_main(map_mod, ["--root", str(repo), "--symbol", "helper_calc"], monkeypatch) == 0
    assert snap_file.exists()


@pytest.mark.fast
def test_runtime_bootstrap_handoff_preflight_and_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica bootstrap, handoff checkpoint/T11, preflight e compliance/sentinel/baseline."""
    ws = tmp_path / "NK_Hub"
    for sub in (".agents/skills/NK-Orchestrator", "scripts", "nk_genome", "nk_tracking/anchor", ".staging"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (ws / ".agents" / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    (ws / "nk_genome" / "nk_registry_manifest.json").write_text(
        json.dumps({"version": "6.0.0-Carbon", "summary": {"total_skills": 1, "total_domains": 5, "total_scripts": 1}, "skills_index": {"NK-Orchestrator": {"domain_id": "DOM-01"}}}),
        encoding="utf-8",
    )
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"_version": "6.0.0-Carbon", "metrics": {"skills_audited": 1, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )
    assert _call_main(boot_mod, ["--project-root", str(ws), "--prompt", "avvia nk hub", "--json"], monkeypatch) == 0
    out_h = tmp_path / "handoff_out"
    assert _call_main(hand_mod, ["--root", str(ws), "--checkpoint-turn", "3", "--gate-status", "G1_PASS", "--milestone-id", "MS-H1"], monkeypatch) == 0
    assert _call_main(hand_mod, ["--root", str(ws), "--output-dir", str(out_h), "--compile-template-11", "--prompt-text", "Completa la verifica finale."], monkeypatch) == 0
    assert _call_main(pre_mod, ["--root", str(ws), "--check-only", "--json"], monkeypatch) == 0
    tr_file = tmp_path / "transcript.jsonl"
    records = [
        {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "procedi"},
        {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "Avvio", "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "python scripts/nk_session_bootstrap.py"}}]},
        {"step_index": 2, "source": "SYSTEM", "type": "TOOL_RESPONSE", "content": "Command exited with code 0.\n[BOOTSTRAP: PASS]"},
    ]
    tr_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    assert _call_main(comp_mod, ["--transcript", str(tr_file), "--min-score", "50", "--json"], monkeypatch) == 0
    assert _call_main(sent_mod, ["--transcript", str(tr_file), "--profile", "carbon", "--actual-context-tokens", "12000", "--json"], monkeypatch) == 0
    assert act_mod.run_sentinel(str(tr_file), profile="carbon")["state"] == "GREEN"
    bl_file = tmp_path / "qb.json"
    assert _call_main(base_mod, ["check", str(bl_file), json.dumps({"unit_tests_total": 95, "unit_tests_passed": 95, "unit_tests_pass_pct": 100.0}), "--json"], monkeypatch) == 0 and bl_file.exists()


@pytest.mark.fast
@pytest.mark.parametrize(
    ("steps", "profile", "expected"),
    [
        (10, "carbon", "GREEN"),
        (150, "carbon", "CAUTION"),
        (200, "carbon", "CRITICAL"),
        (260, "carbon", "RED"),
        (150, "argon", "CAUTION"),
        (200, "argon", "CRITICAL"),
        (260, "argon", "RED"),
        (70, "standard", "CAUTION"),
        (90, "standard", "CRITICAL"),
        (110, "standard", "RED"),
    ],
)
def test_runtime_sentinel_calculate_state_matrix(steps: int, profile: str, expected: str) -> None:
    """Verifica matrice soglie GREEN/CAUTION/CRITICAL/RED per i tre profili."""
    assert act_mod.calculate_state(steps, profile=profile) == expected


@pytest.mark.fast
def test_runtime_sentinel_edge_branches_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Copre rami non coperti in nk_active_runtime_sentinel (JSON thresholds, TV-08 escape, CLI)."""
    thr_json = tmp_path / "thr.json"
    thr_json.write_text(json.dumps({"profiles": {"custom": {"runtime_sentinel": {"green_max_steps": 40}}}}), encoding="utf-8")
    parsed_j = act_mod.load_saturation_thresholds(thresholds_path=thr_json)
    assert parsed_j["profiles"]["custom"]["runtime_sentinel"]["green_max_steps"] == 40
    bad_json = tmp_path / "empty_bad.json"
    bad_json.write_text("{corrupt", encoding="utf-8")
    assert act_mod.load_saturation_thresholds(thresholds_path=bad_json) == {}
    assert act_mod._is_compaction_checkpoint("{}", ["not", "dict"]) is False  # type: ignore[arg-type]
    assert act_mod._is_compaction_checkpoint(r'{"content":"\u003cCONTEXT_SUMMARY\u003e"}', {"content": 123}) is False
    tp_arr = tmp_path / "only_arrays.jsonl"
    tp_arr.write_text("[1, 2]\n{bad\n", encoding="utf-8")
    assert act_mod.run_sentinel(str(tp_arr), profile="standard")["steps"] == 2
    assert act_mod.run_sentinel(str(tmp_path / "missing.jsonl"), profile="standard")["steps"] == 0
    monkeypatch.setattr(act_mod, "discover_active_main_transcript", lambda: None)
    assert act_mod._discover_active_transcript() is None
    assert _call_main(act_mod, ["--profile", "standard", "--json"], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["steps"] == 0
    red_tp = tmp_path / "red.jsonl"
    red_tp.write_text(json.dumps({"source": "MODEL", "input_tokens": 210000}) + "\n", encoding="utf-8")
    assert _call_main(act_mod, ["--transcript", str(red_tp), "--profile", "carbon", "--check"], monkeypatch) == 1
    monkeypatch.setattr(act_mod, "atomic_write_text", lambda *_a, **_k: (False, "disk_err"))
    with pytest.raises(OSError, match="disk_err"):
        act_mod._write_state_atomic_win32(str(tmp_path / "s.json"), {"steps": 1})


@pytest.mark.fast
def test_runtime_swarm_messenger_and_auto_inning_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Copre tutti i rami residui di nk_swarm_messenger e nk_auto_inning."""
    assert "[Swarm-Envelope: A -> B]" in swm_mod.process_payload("breve messaggio", sender="A", recipient="B")
    assert "[Swarm-Envelope: OnlyS -> parent]" in swm_mod.process_payload("msg", sender="OnlyS")
    assert "[Swarm-Envelope: subagent -> OnlyR]" in swm_mod.process_payload("msg", recipient="OnlyR")
    assert "TRUNCATED" in swm_mod.process_payload("X" * 2400, sender="Worker", recipient="Hub")
    p_file = tmp_path / "msg.txt"
    p_file.write_text("contenuto da file", encoding="utf-8")
    assert _call_main(swm_mod, ["--payload-file", str(p_file), "--sender", "S1"], monkeypatch) == 0
    assert "contenuto da file" in capsys.readouterr().out
    assert _call_main(swm_mod, ["--payload", "inline_msg"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() == "inline_msg"
    assert _call_main(swm_mod, [], monkeypatch) == 0
    assert capsys.readouterr().out.strip() == ""
    with monkeypatch.context() as mp_swm:
        mp_swm.setattr(swm_mod, "atomic_write_text", lambda *_a, **_k: (False, "spill_err"))
        with pytest.raises(OSError, match="spill_err"):
            swm_mod.process_payload("Z" * 2000)
    tp_inn = tmp_path / "inn.jsonl"
    tp_inn.write_text('{"step": 1}\n{"step": 2}\n', encoding="utf-8")
    tun_f = tmp_path / "tuning.json"

    class _FakeProc:
        def __init__(self, out: str) -> None:
            self.stdout = out

    monkeypatch.setattr(
        inn_mod.subprocess,
        "run",
        lambda *_a, **_k: _FakeProc(json.dumps({"status": "PASS", "total_tool_calls": 3, "scores": {"composite_score": 98.5}})),
    )
    assert _call_main(inn_mod, ["--transcript", str(tp_inn), "--tuning-file", str(tun_f), "--json"], monkeypatch) == 0
    d_ok = json.loads(capsys.readouterr().out)
    assert d_ok["steps"] == 2 and d_ok["compliance_score"] == 98.5 and d_ok["ratchet_verified"] is True
    monkeypatch.setattr(inn_mod.subprocess, "run", lambda *_a, **_k: _FakeProc("{bad_json"))
    assert _call_main(inn_mod, ["--transcript", str(tmp_path / "miss.jsonl"), "--tuning-file", str(tun_f)], monkeypatch) == 0
    assert json.loads(tun_f.read_text(encoding="utf-8"))["steps"] == 0
    monkeypatch.setattr(inn_mod, "atomic_write_text", lambda *_a, **_k: (False, "tun_err"))
    with pytest.raises(OSError, match="tun_err"):
        _call_main(inn_mod, ["--transcript", str(tp_inn), "--tuning-file", str(tun_f)], monkeypatch)


@pytest.mark.integration
def test_runtime_env_probe_heartbeat_and_microhud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica env_capability_probe, AsyncHeartbeatSignaler (thread) e MicroHUDRenderer."""
    assert probe_mod.check_module_availability("json")["available"] is True
    assert probe_mod.check_module_availability("non_existent_pkg_xyz_999")["available"] is False
    assert _call_main(probe_mod, ["--check-module", "sqlite3", "--json"], monkeypatch) == 0
    hb_log = tmp_path / "hb.jsonl"
    hb = hb_mod.AsyncHeartbeatSignaler(step_name="wp7_step", cadence_sec=0.02, watchdog_sec=5.0, telemetry_file=hb_log)
    hb.diag_dir = tmp_path / "diag"
    hb.diag_dir.mkdir(parents=True, exist_ok=True)
    hb.start()
    hb.reset_step("wp7_phase2")
    dump_p = hb.dump_diagnostics()
    hb.stop()
    assert hb_log.exists() and dump_p.exists()
    assert _call_main(hb_mod, ["--once", "--step-name", "cli_beat", "--json"], monkeypatch) == 0
    hud = hud_mod.MicroHUDRenderer(ascii_mode=True)
    hud.set_progress(85)
    assert _call_main(hud_mod, ["--percent", "90", "--agent", "NK-Builder-Agent", "--domain", "DOM-03", "--ascii", "--json"], monkeypatch) == 0


@pytest.mark.fast
def test_runtime_dual_ledgers_pid_lock_and_ipc_contracts(tmp_path: Path) -> None:
    """Verifica TaskLedger DAG, ProgressLedger, PIDFileLock e contratti RSI IPC."""
    t_ledger = led_mod.TaskLedger(tmp_path / "tasks.jsonl")
    n1 = t_ledger.add_task("T1", "bootstrap", "NK-Orchestrator")
    n2 = t_ledger.add_task("T2", "build", "NK-Builder-Agent", parent_ids=["T1"])
    ok_dag, dag_msg = t_ledger.verify_dag()
    assert ok_dag is True and "valid" in dag_msg.lower()
    assert len(t_ledger.get_roots()) == 1 and len(t_ledger.get_leaves()) == 1
    assert n1.task_id == "T1" and n2.task_id == "T2"
    p_ledger = led_mod.ProgressLedger(tmp_path / "progress.jsonl")
    p_ledger.append_event("E1", "T1", 1, "STARTED", {"info": "go"})
    assert len(p_ledger.read_events("T1")) == 1
    with led_mod.PIDFileLock(tmp_path / "test.lock"):
        assert (tmp_path / "test.lock").exists()
    dv = ipc_mod.RSIDefectVector(tests_passed=100, tests_total=100)
    rec = ipc_mod.RSIIterationRecord(
        session_id="S-1", iteration=1, mode="mode_c", defects=dv, delta_k=0, fitness_q=100.0, state_hash="a" * 64, verdict="CONVERGED_OPTIMAL"
    )
    rep = ipc_mod.RSISessionReport(
        session_id="S-1", mode="mode_c", iterations_used=1, final_status="CONVERGED_OPTIMAL", final_delta=0, final_fitness_q=100.0, history=[rec]
    )
    assert rep.final_fitness_q == 100.0


@pytest.mark.fast
def test_rsi_ste100_advisory_non_blocking_with_strict_unit_helper(tmp_path: Path) -> None:
    """Verifica che STE100 emetta ste100_warnings non bloccanti preservando verify_ste100_compliance."""
    long_bad = (
        "[RULE-STE100]\n"
        "Questa frase intenzionalmente molto lunga supera nettamente il limite massimo di venti parole "
        "previsto dallo standard con un trattino — spaziato vietato.\n"
    )
    assert rsi_mod.verify_ste100_compliance(long_bad)["passed"] is False

    ws = tmp_path / "adv_ste_ws"
    (ws / ".agents" / "skills" / "NK-Demo").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / ".agents" / "AGENTS.md").write_text(long_bad, encoding="utf-8")
    (ws / ".agents" / "skills" / "NK-Demo" / "SKILL.md").write_text(
        "---\nname: NK-Demo\nversion: '6.4.0-Carbon'\n---\n" + long_bad, encoding="utf-8"
    )
    eng = rsi_mod.RSIConvergenceEngine(workspace_root=ws, root=ws)
    eco = eng.verify_ecosystem(
        root_dir=ws, profile="ste100_rsi", test_report={"tests_passed": 5, "tests_failed": 0, "tests_total": 5}
    )
    assert eco["passed"] is True and eco["delta_k"] == 0 and eco["violations"] == []
    assert len(eco["checks"]["agents_md"]["ste100_warnings"]) >= 1
    assert len(eco["checks"]["skills_and_markdown"]["ste100_warnings"]) >= 1
    assert len(eco["ste100_warnings"]) >= 2

    vibe_res = eng.run_vibe_check(ws / ".agents" / "AGENTS.md", profile="ste100_rsi")
    assert vibe_res["passed"] is True and vibe_res["delta_k"] == 0 and vibe_res["violations"] == []
    assert len(vibe_res["ste100_warnings"]) >= 1


@pytest.mark.fast
def test_dynamic_active_context_and_router_tiebreak_fixes(tmp_path: Path) -> None:
    """Verifica active_context.md dinamico entro budget e fix instradamento router."""
    ws = tmp_path / "ctx_dyn_ws"
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "nk_tracking" / "handoff").mkdir(parents=True)
    (ws / "nk_tracking" / "anchor").mkdir(parents=True)
    for idx_f in range(18):
        (ws / ".staging" / "scripts" / f"mod_{idx_f:02d}_extra_long_name_for_budget.py").write_text("X=1\n", encoding="utf-8")
    (ws / "nk_tracking" / "handoff" / "session_handoff_latest.json").write_text(
        json.dumps({"last_summary": "Audit completato", "pending_actions": ["Promuovi 2PC"], "last_failed_checks": ["check_x"]}),
        encoding="utf-8",
    )
    res_std = hand_mod.generate_active_context_view(root=ws, profile="standard")
    res_carb = hand_mod.generate_active_context_view(root=ws, profile="carbon")
    assert res_std["passed"] is True and res_std["estimated_tokens"] <= 350
    assert res_carb["passed"] is True and "## Delta & Stato Operativo Corrente" in res_carb["content"]
    assert "Audit completato" in res_carb["content"] and "Promuovi 2PC" in res_carb["content"]
    assert ".staging/scripts/mod_00_extra_long_name_for_budget.py" in res_carb["content"]
    assert ".staging/scripts/mod_15_extra_long_name_for_budget.py" not in res_carb["content"]
    with pytest.raises(ValueError):
        hand_mod.generate_active_context_view(root=ws, output_path=tmp_path / "escape_ctx.md")

    router = router_mod.VibeSprintRouter()
    r1 = router.classify_prompt_intent("[1]")
    assert r1["primary_agent"] == "NK-System-Architect" and r1["read_only"] is False
    r_dk = router.classify_prompt_intent("Verifica il delta_k di convergenza")
    assert r_dk["primary_agent"] == "NK-Oracle-Evaluator"
    r_be = router.classify_prompt_intent("Progetta architettura backend con DAG di Kahn, schema API e modello dati Pydantic")
    assert r_be["primary_agent"] == "NK-System-Architect" and r_be["native_subagent"] == "NK-Specifier-Agent"
    r_ux = router.classify_prompt_intent("Progetta interfaccia generative ui con design system")
    assert r_ux["primary_agent"] == "NK-System-Architect"
    r_tet = router.classify_prompt_intent("Implementa funzione async leggendo implementation_plan.md")
    assert r_tet["primary_agent"] != "NK-Oracle-Evaluator"


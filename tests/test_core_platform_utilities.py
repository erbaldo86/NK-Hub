# -*- coding: utf-8 -*-
"""
Suite consolidata delle utilita core di piattaforma per NK Hub Generation 1.0.0-Generation.
Modulo: tests/test_core_platform_utilities.py.
Unifica utilita piattaforma, invisible_healing_loop, preflight, handoff, bootstrap e cleanup.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

try:
    from conftest import WORKSPACE_ROOT, call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, call_script_main_captured, load_nk_script_module

cache_mod = load_nk_script_module("deterministic_api_cache")
DeterministicApiCache = cache_mod.DeterministicApiCache
probe_mod = load_nk_script_module("env_capability_probe")
probe_environment = probe_mod.probe_environment
check_module_availability = probe_mod.check_module_availability
STANDARD_MODULES_TO_PROBE = probe_mod.STANDARD_MODULES_TO_PROBE
THIRD_PARTY_MODULES_TO_PROBE = probe_mod.THIRD_PARTY_MODULES_TO_PROBE
scaffolder_mod = load_nk_script_module("external_project_scaffolder")
ExternalProjectScaffolder = scaffolder_mod.ExternalProjectScaffolder
oracle_mod = load_nk_script_module("oracle_evaluator_l3")
hud_mod = load_nk_script_module("micro_hud_renderer")
runner_mod = load_nk_script_module("platform_runner")
_normalize_python_command = runner_mod._normalize_python_command
safe_subprocess_run = runner_mod.safe_subprocess_run
reconfigure_streams = runner_mod.reconfigure_streams
preflight_mod = load_nk_script_module("preflight_health_check")
PreflightHealthChecker = preflight_mod.PreflightHealthChecker
cleanup_mod = load_nk_script_module("safe_cleanup_dev_servers")
heartbeat_mod = load_nk_script_module("async_heartbeat_signaler")
is_target_workspace_process = cleanup_mod.is_target_workspace_process


def _util_api_cache_wal(tmp_path: Path) -> None:
    """Verifica connessione WAL persistente, force_refresh, scadenza TTL ed eviction."""
    db_path = tmp_path / "wal_persistent.db"
    with DeterministicApiCache(db_path=db_path, ttl_seconds=0.008) as cache:
        assert cache.health_check() is True
        conn_initial = cache._conn
        assert conn_initial is not None
        cache.set("https://example.org/v1", 200, '{"ok": true}', method="POST", params={"q": "nk"})
        hit = cache.get("https://example.org/v1", method="POST", params={"q": "nk"})
        assert hit is not None and hit[0] == 200 and cache._conn is conn_initial
        assert cache.get("https://example.org/v1", method="POST", params={"q": "nk"}, force_refresh=True) is None
        time.sleep(0.012)
        assert cache.get("https://example.org/v1", method="POST", params={"q": "nk"}) is None
        cache.set("https://example.org/v2", 200, '{"ephemeral": 2}')
        assert cache.clear() == 1
    assert cache._conn is None


def _util_env_probe_gt09(tmp_path: Path) -> None:
    """Verifica separazione moduli core Hub e opzionali con total_probed=15 (GT-09)."""
    exp_f = tmp_path / "probe_exp.json"
    rc_probe, _, _ = call_script_main_captured(probe_mod, ["--export", str(exp_f)])
    assert rc_probe == 0 and exp_f.is_file()
    data = json.loads(exp_f.read_text(encoding="utf-8"))
    assert data["python"]["version_major"] == 3 and data["python"]["executable"] == sys.executable
    assert data["standard_modules"]["sqlite3"]["available"] is True
    assert len(probe_mod.format_human_readable(data)) > 40
    assert check_module_availability("fictitious_module_xyz_nonexistent_98765")["available"] is False
    expected_total = len(STANDARD_MODULES_TO_PROBE) + len(THIRD_PARTY_MODULES_TO_PROBE)
    assert data["summary"]["total_probed"] == expected_total == 15
    assert all(k in data["core_hub_modules"] for k in ("pydantic", "pytest", "psutil"))
    assert "fastapi" in data["optional_app_modules"]
    assert data["summary"]["all_core_hub_available"] is True and data["summary"]["status"] == "PASS"


def _util_scaffolder_reject() -> None:
    """Verifica che un percorso interno a NK-Hub sollevi immediatamente ValueError."""
    forbidden_target = WORKSPACE_ROOT / f"forbidden_internal_app_{uuid.uuid4().hex[:6]}"
    with pytest.raises(ValueError) as exc_info:
        ExternalProjectScaffolder(project_name="ForbiddenApp", target_dir=forbidden_target)
    assert "RULE-PROJECT-ISOLATION" in str(exc_info.value) and not forbidden_target.exists()


def _util_scaffolder_full(tmp_path: Path) -> None:
    """Verifica la creazione completa dell'albero DDD e della Pentad Sovrana."""
    ext_dir = tmp_path / "ExternalCleanProject"
    report = ExternalProjectScaffolder(project_name="ExternalCleanProject", target_dir=ext_dir).scaffold()
    assert report["status"] == "SUCCESS"
    for f in ("concept_map.md", "structural_tree.md", "implementation_plan.md", "repo_map.md"):
        assert (ext_dir / "nk_genome" / f).exists()
    assert (ext_dir / "src" / "core" / "__init__.py").exists()
    assert (ext_dir / "src" / "api" / "__init__.py").exists()
    assert (ext_dir / "tests" / "test_ast_purity.py").exists()


def _util_oracle_void_tags_hud(tmp_path: Path) -> None:
    """Verifica void tag HTML5, percorsi Windows e rendering Micro-HUD."""
    html_file = tmp_path / "index.html"
    html_content = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><link rel='stylesheet' href='a.css'></head>"
        "<body><main><img src='logo.png' alt='logo'><br><input type='text' id='q'>"
        "<button id='submit_btn'>Invia</button></main></body></html>"
    )
    html_file.write_text(html_content, encoding="utf-8")
    spec_arg = f"{html_file}:#submit_btn:Invia"
    assert "<!DOCTYPE html>" in oracle_mod.resolve_html_source(spec_arg)
    dom_res = oracle_mod.DOMOracleEvaluator().evaluate_deltas(spec_arg, html_content)
    assert dom_res.verdict == "PASS" and dom_res.discrepancy_count == 0

    hud = hud_mod.MicroHUDRenderer(version="v6.0.0-Carbon", ascii_mode=True)
    hud.set_progress(100)
    hud.set_agent_context("NK-Oracle-Evaluator", "ARCH")
    hud.set_rsi_metrics(delta_k=0.0, fitness_q=100.0)
    line = hud.render(include_extras=True)
    assert "100%" in line and "NK-Oracle-Evaluator" in line
    ipc_state = hud.to_ipc_state(session_id="test_sess")
    assert ipc_state.session_id == "test_sess" and ipc_state.progress_pct == 100.0


def _util_oracle_conf10(tmp_path: Path) -> None:
    """Verifica CONF-10: supporto expected .json/.md/.html senza regressioni."""
    actual_html = "<!DOCTYPE html><html><body><main><h1>Dashboard Principale</h1><button id='submit_btn' class='btn primary'>Invia</button></main></body></html>"
    actual_file = tmp_path / "actual.html"
    actual_file.write_text(actual_html, encoding="utf-8")

    exp_json = tmp_path / "expected.json"
    exp_json.write_text(json.dumps({"required_tags": ["main", "button"], "required_ids": ["submit_btn"], "required_classes": ["btn", "primary"], "required_texts": ["Dashboard Principale", "Invia"]}), encoding="utf-8")
    evaluator = oracle_mod.DOMOracleEvaluator()
    assert evaluator.evaluate_deltas(str(exp_json), str(actual_file)).verdict == "PASS"

    exp_json_fail = tmp_path / "expected_missing.json"
    exp_json_fail.write_text(json.dumps({"required_ids": ["submit_btn", "missing_ctrl"]}), encoding="utf-8")
    assert evaluator.evaluate_deltas(str(exp_json_fail), str(actual_file)).verdict == "FAIL"

    exp_md = tmp_path / "expected_spec.md"
    exp_md.write_text('# Dashboard Principale\n- <button>\n- #submit_btn\n- "Invia"\n', encoding="utf-8")
    assert evaluator.evaluate_deltas(str(exp_md), str(actual_file)).verdict == "PASS"

    exp_md_missing = tmp_path / "expected_spec_fail.md"
    exp_md_missing.write_text("# Titolo Inesistente\n- #non_existent_id\n", encoding="utf-8")
    assert evaluator.evaluate_deltas(str(exp_md_missing), str(actual_file)).discrepancy_count >= 2

    exp_md_fenced = tmp_path / "expected_fenced.md"
    exp_md_fenced.write_text(f"```html\n{actual_html}\n```\n", encoding="utf-8")
    assert evaluator.evaluate_deltas(str(exp_md_fenced), actual_html).verdict == "PASS"
    _util_oracle_conf10_cli_guard(tmp_path, actual_file, exp_json, exp_md)


def _util_oracle_conf10_cli_guard(
    tmp_path: Path, actual_file: Path, exp_json: Path, exp_md: Path
) -> None:
    """Verifica LFI guard HTML-only su actual e exit code CLI 2."""
    with pytest.raises(ValueError):
        oracle_mod.resolve_html_source(str(exp_json))
    secret_env = tmp_path / "secret.env"
    secret_env.write_text("SECRET_TOKEN=12345\n", encoding="utf-8")
    assert oracle_mod.resolve_expected_source(str(exp_md))[1] == "md"
    assert oracle_mod.resolve_expected_source(str(exp_json))[1] == "json"

    traversal_ref = f"{'.' + '.'}/secret.html"
    for flag_exp, src_exp in (("--expected-file", exp_md), ("--expected", exp_json)):
        rc_pass, out_pass, _ = call_script_main_captured(oracle_mod, [flag_exp, str(src_exp), "--actual-file", str(actual_file), "--json"])
        assert rc_pass == 0 and json.loads(out_pass)["verdict"] == "PASS"
        for bad_actual in (str(exp_md), str(exp_json), str(secret_env), traversal_ref):
            with pytest.raises(ValueError):
                oracle_mod.resolve_html_source(bad_actual)
            for flag_act in ("--actual", "--actual-file"):
                rc_bad, _, _ = call_script_main_captured(oracle_mod, [flag_exp, str(src_exp), flag_act, bad_actual, "--json"])
                assert rc_bad == 2


def _util_platform_unbuffered() -> None:
    """Verifica l'iniezione del flag -u su liste e stringhe e valida pytest.ini."""
    reconfigure_streams()
    assert str(_normalize_python_command('python -c "print(42)"')).startswith("python -u ")
    assert " -u " in str(_normalize_python_command(f'"{sys.executable}" -c "print(42)"'))
    assert _normalize_python_command([sys.executable, "-c", "print(1)"])[1] == "-u"
    assert "-m pytest -q" in str(_normalize_python_command("pytest -q"))
    assert _normalize_python_command(["pytest", "-q"])[:4] == [sys.executable, "-u", "-m", "pytest"]
    runner_mod._kill_process_tree_sync(0)
    assert runner_mod._tokenize_command_no_shell('python -c "a \\"b\\""') == ["python", "-c", 'a "b"']
    for bad_tok in ("cmd\x00x", "echo a & echo b", "echo $(whoami)", 'python "unterminated'):
        with pytest.raises(ValueError):
            runner_mod._tokenize_command_no_shell(bad_tok)
    for bad_argv in ([], ["   "], ["py\nthon"], ["python", "a\x00b"], ["run.bat", "x&y"]):
        with pytest.raises(ValueError):
            runner_mod._prepare_argv_no_shell(bad_argv, {})
    ini_text = (WORKSPACE_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "[pytest]" in ini_text and "testpaths" in ini_text and ".staging" in ini_text


def _util_platform_tree_kill_utf8() -> None:
    """Verifica cattura UTF-8, comandi non validi e tree-kill su timeout."""
    rc_ok, out_ok, err_ok = safe_subprocess_run([sys.executable, "-c", "import sys; sys.stdout.write('NK_UTF8_🚀_€\\n')"])
    assert rc_ok == 0 and "🚀" in out_ok and "€" in out_ok and err_ok == ""
    rc_inv, out_inv, _ = safe_subprocess_run(["non_existent_binary_nk_987654321"])
    assert rc_inv != 0 and out_inv == ""
    rc, _, stderr = safe_subprocess_run([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    assert rc == -1 and "timed out" in stderr.lower()


@pytest.mark.fast
def test_preflight_corrupted_baseline_fails_even_with_autofix(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica il blocco fail-closed su baseline corrotta e il flag --check-only."""
    corrupt_root = tmp_path / "corrupt_ws"
    for d in (".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests", ".staging"):
        (corrupt_root / d).mkdir(parents=True, exist_ok=True)
    baseline_file = corrupt_root / "nk_tracking" / "quality_baseline.json"
    baseline_file.write_text("{CORRUPTED_JSON_PAYLOAD", encoding="utf-8")

    report = PreflightHealthChecker(workspace_root=corrupt_root).run_full_check(auto_fix=True)
    assert report["status"] == "FAIL" and report["checks"]["baseline_alignment"]["passed"] is False
    assert baseline_file.read_text(encoding="utf-8") == "{CORRUPTED_JSON_PAYLOAD"

    readonly_root = tmp_path / "readonly_ws"
    for d in (".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests"):
        (readonly_root / d).mkdir(parents=True, exist_ok=True)
    (readonly_root / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"_version": "6.0.0-Carbon", "metrics": {"skills_audited": 16, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["preflight_health_check.py", "--root", str(readonly_root), "--check-only"])
    assert preflight_mod.main() == 1
    assert not (readonly_root / ".staging").exists()
    assert not (readonly_root / "nk_tracking" / "anchor" / "session_anchor.jsonl").exists()


def _util_safe_cleanup_filter(tmp_path: Path) -> None:
    """Verifica il filtro CWD/cmdline del workspace e protezione PID corrente."""
    assert is_target_workspace_process(os.getpid(), workspace_root=tmp_path) is False
    assert is_target_workspace_process(os.getppid(), workspace_root=tmp_path) is False


def _util_heartbeat_cleanup_cli(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Verifica l'esecuzione CLI deterministica di heartbeat e safe_cleanup."""
    monkeypatch.setattr(sys, "argv", ["async_heartbeat_signaler.py", "--once", "--task-id", "test_hb", "--json"])
    assert heartbeat_mod.main() == 0 and '"pulse_index": 1' in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["safe_cleanup_dev_servers.py", "--workspace-root", str(tmp_path), "--ports", "59996", "--dry-run", "--json"])
    assert cleanup_mod.main() == 0 and '"status": "OK"' in capsys.readouterr().out


def _resolve_doc(rel_path: str) -> Path:
    """Risolve un file di documentazione dando priorita a .staging/."""
    stg = WORKSPACE_ROOT / ".staging" / rel_path
    return stg if stg.exists() else WORKSPACE_ROOT / rel_path


def _util_agents_rule_00_5() -> None:
    """Verifica la codifica GT-08 in AGENTS.md e NK-Orchestrator."""
    content = _resolve_doc(".agents/AGENTS.md").read_text(encoding="utf-8")
    assert "[RULE-00.5]" in content and "UNIFIED_ONBOARDING_DASHBOARD_MANDATE" in content
    content_lower = content.lower()
    for trigger in ("avvia ambiente nk", "avvia nk hub", "avvia nk", "avvia hub", "start nk", "start hub", "attiva nk", "attiva ambiente nk"):
        assert trigger in content_lower
    assert "fast-stat" in content_lower and "120" in content and "[0]" in content and "[9]" in content

    hub_content = _resolve_doc(".agents/skills/NK-Orchestrator/SKILL.md").read_text(encoding="utf-8")
    for i in range(10):
        assert f"[{i}]" in hub_content
    hub_lower = hub_content.lower()
    assert "selezione rapida" in hub_lower or "modalità diretta" in hub_lower or "modalita' diretta" in hub_lower
    assert "goal-driven" in hub_lower or "linguaggio naturale" in hub_lower
    assert "10. UNIFIED_ONBOARDING_COMPLIANCE" in hub_content


def _util_session_bootstrap_fast_stat() -> None:
    """Esegue programmaticamente scripts/nk_session_bootstrap.py e verifica PASS."""
    mod = load_nk_script_module("nk_session_bootstrap")
    inst = mod.NKSessionBootstrap(workspace_root=WORKSPACE_ROOT)
    assert inst.model_profile == "generation"
    result = inst.run_bootstrap(fast_stat=True)
    assert isinstance(result, dict) and result.get("status") == "PASS" and "checks" in result


@pytest.mark.fast
def test_bootstrap_carbon_compaction_reset_and_safe_cleanup_live_tcp(tmp_path: Path) -> None:
    """Verifica reset post-compattazione in nk_session_bootstrap e mancato reset su spoof."""
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    ws = tmp_path / "boot_carbon_ws"
    for d in ("nk_tracking", ".wal", "scripts", ".agents"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8"
    )

    tp_ckpt = tmp_path / "boot_compaction_ckpt.jsonl"
    ckpt_records = [
        *[{"step_index": i, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-11T10:00:00Z", "input_tokens": 220_000, "output_tokens": 7500, "tool_calls": [{"name": "write_file"} for _ in range(4)], "content": "x" * 1000} for i in range(260)],
        {"source": "SYSTEM", "type": "CHECKPOINT", "content": "# Resuming from a compaction checkpoint"},
        {"step_index": 261, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-11T10:01:00Z", "content": "continua"},
        {"step_index": 262, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-11T10:01:05Z", "input_tokens": 14_000, "content": "ok"},
    ]
    tp_ckpt.write_text("\n".join(json.dumps(r) for r in ckpt_records) + "\n", encoding="utf-8")
    boot_c = boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="conv-ckpt-ok", transcript_path=tp_ckpt)
    assert boot_c.model_profile == "generation" and boot_c.run_bootstrap(fast_stat=False)["checks"]["context_sentry"]["status"] == "GREEN"
    tail_ckpt = boot_mod._inspect_tail_resilience_risks(tp_ckpt, t_size=tp_ckpt.stat().st_size, est_tokens=2000)
    assert tail_ckpt["rpc_stream_burst_risk"] is False and tail_ckpt["effective_context_tokens"] == 14_000

    tp_spoof = tmp_path / "boot_compaction_spoof.jsonl"
    spoof_records = [
        *[{"step_index": i, "source": "MODEL", "type": "PLANNER_RESPONSE", "input_tokens": 215_000, "tool_calls": [{"name": "write_file"} for _ in range(3)], "content": "step"} for i in range(255)],
        {"step_index": 256, "source": "MODEL", "type": "PLANNER_RESPONSE", "content": "<CONTEXT_SUMMARY> fake"},
        {"step_index": 257, "source": "MODEL", "type": "GENERIC", "content": "<CONTEXT_SUMMARY> generico"},
    ]
    tp_spoof.write_text("\n".join(json.dumps(r) for r in spoof_records) + "\n", encoding="utf-8")
    assert boot_mod.NKSessionBootstrap(workspace_root=ws, conversation_id="conv-ckpt-spoof", transcript_path=tp_spoof).run_bootstrap(fast_stat=False)["checks"]["context_sentry"]["status"] == "RED"


@pytest.mark.integration
def test_safe_cleanup_live_tcp_server_tree(tmp_path: Path) -> None:
    """Verifica rilevamento ed abbattimento live server TCP su workspace isolato."""
    ws = tmp_path / "boot_ws"
    ws.mkdir()
    assert cleanup_mod.parse_ports_arg("   ") == cleanup_mod.TARGET_PORTS
    assert cleanup_mod.is_target_workspace_process(-5, workspace_root=ws) is False

    srv_ws = tmp_path / "NK_External_Projects" / "LiveDevSrv"
    srv_ws.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_sock:
        probe_sock.bind(("127.0.0.1", 0))
        chosen_port = int(probe_sock.getsockname()[1])

    ready_flag, srv_script = srv_ws / "ready.txt", srv_ws / "mini_srv.py"
    srv_script.write_text(
        f"import os, pathlib, socket, time\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\ns.bind(('127.0.0.1', {chosen_port}))\ns.listen(2)\npathlib.Path(r'{ready_flag}.tmp').write_text(str(os.getpid()), encoding='utf-8')\nos.replace(r'{ready_flag}.tmp', r'{ready_flag}')\ntime.sleep(10)\n",
        encoding="utf-8",
    )
    srv_proc = subprocess.Popen([sys.executable, "-B", str(srv_script)], cwd=str(srv_ws))
    try:
        deadline = time.perf_counter() + 2.5
        while not ready_flag.exists() and time.perf_counter() < deadline:
            time.sleep(0.005)
        assert ready_flag.exists()
        listener_pid = int(ready_flag.read_text(encoding="utf-8").strip())
        assert cleanup_mod.parse_ports_arg(None) == list(cleanup_mod.TARGET_PORTS)
        assert cleanup_mod.parse_ports_arg("8001, invalid, 99999, 8002, 8001") == [8001, 8002]
        assert cleanup_mod.parse_ports_arg([8010, 0, 8010]) == [8010]
        assert cleanup_mod.kill_pid_tree(-1) is False and cleanup_mod.kill_pid_tree(os.getpid()) is False
        other_dir = tmp_path / "ExternalWorkspace"
        other_dir.mkdir()
        assert cleanup_mod.is_target_workspace_process(srv_proc.pid, workspace_root=tmp_path) is True
        assert cleanup_mod.is_target_workspace_process(listener_pid, workspace_root=tmp_path) is True
        assert cleanup_mod.is_target_workspace_process(srv_proc.pid, workspace_root=other_dir) is False
        assert listener_pid in cleanup_mod.get_pids_listening_on_ports([chosen_port], workspace_root=srv_ws)
        assert cleanup_mod.run_cleanup(workspace_root=srv_ws, dry_run=False, as_json=False, ports=[chosen_port]) == 0
        srv_proc.wait(timeout=3.0)
    finally:
        if srv_proc.poll() is None:
            srv_proc.kill()
            srv_proc.wait(timeout=2.0)


def _util_healing_retry(tmp_path: Path) -> None:
    """Verifica SBFLLocation, budget token SBFL, KarpathySlicer e DSPyTelemetryHook."""
    ihl_mod = load_nk_script_module("invisible_healing_loop")
    faulty = tmp_path / "faulty_module.py"
    faulty.write_text("def compute_ratio(a: int, b: int) -> float:\n    return a / b\n", encoding="utf-8")
    code_slice = ihl_mod.KarpathySlicer.slice_file(faulty, target_line=2, window=2)
    assert code_slice.target_line == 2 and "return a / b" in code_slice.content
    loc = ihl_mod.SBFLLocation(file_path=str(faulty), line_number=2, suspiciousness=1.0, error_type="ZeroDivisionError", error_message="division by zero", failing_line_content="    return a / b")
    rendered_json = loc.render_payload_json()
    assert ihl_mod.estimate_token_count(rendered_json) <= ihl_mod.SBFL_MAX_TOKEN_BUDGET
    telemetry_file = tmp_path / "healing_telemetry.jsonl"
    loop = ihl_mod.InvisibleHealingLoop(telemetry_log_path=telemetry_file, max_cycles=3)
    loop._record_telemetry(run_id="heal_test_01", task_name="test_retry_heal", cycles_total=1, status="HEALED", history=[ihl_mod.HealingCycleLog(cycle_index=1, sbfl_payload=rendered_json, fault_slice=code_slice.content, repair_action="GUARD_ZERO_DIVISOR", repair_success=True, duration_ms=12.5)])
    assert json.loads(telemetry_file.read_text(encoding="utf-8").splitlines()[0])["final_status"] == "HEALED"


def _util_healing_escalate(tmp_path: Path) -> None:
    """Verifica SBFLEngine.extract_from_exception e registrazione ESCALATED."""
    ihl_mod = load_nk_script_module("invisible_healing_loop")
    telemetry_file = tmp_path / "escalation_telemetry.jsonl"
    loop = ihl_mod.InvisibleHealingLoop(telemetry_log_path=telemetry_file, max_cycles=2)
    try:
        raise ValueError("Errore persistente non riparabile automaticamente")
    except ValueError as exc:
        captured_loc = ihl_mod.SBFLEngine.extract_from_exception(exc, relevant_file_hint="test_core_platform_utilities")
    assert captured_loc is not None and captured_loc.error_type == "ValueError"
    history = [ihl_mod.HealingCycleLog(cycle_index=idx, sbfl_payload=captured_loc.render_payload_json(), fault_slice=captured_loc.failing_line_content, repair_action="ATTEMPT_FAILED", repair_success=False, duration_ms=5.0, error_details="ValueError") for idx in (1, 2)]
    res = ihl_mod.HealingResult(success=False, cycles_used=2, max_cycles=2, history=history, output=None, final_error="ValueError")
    loop._record_telemetry(run_id="heal_esc_02", task_name="test_unrecoverable_escalation", cycles_total=res.cycles_used, status="ESCALATED", history=res.history)
    assert res.success is False and json.loads(telemetry_file.read_text(encoding="utf-8").splitlines()[0])["final_status"] == "ESCALATED"


@pytest.mark.fast
def test_session_bootstrap_fast_stat_pollution_baseline_wal_and_isolation(tmp_path: Path) -> None:
    """Verifica Fast-Stat, rilevamento file spurii in root e bonifica WAL scaduto."""
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    ws_root = tmp_path / "isolated_hub_ws"
    for sub in ("nk_tracking", ".wal", "scripts", ".agents"):
        (ws_root / sub).mkdir(parents=True, exist_ok=True)
    (ws_root / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8")

    boot = boot_mod.NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-alpha")
    assert boot.run_bootstrap(fast_stat=False)["status"] == "PASS"
    res_fast = boot.run_bootstrap(fast_stat=True)
    assert res_fast["status"] == "PASS" and "fast_stat" in res_fast["checks"]

    saved_mtime = boot._get_root_mtime()
    tmp_polluter = ws_root / "rogue_artifact.tmp"
    tmp_polluter.write_text("temp pollution", encoding="utf-8")
    try:
        os.utime(ws_root, (saved_mtime, saved_mtime))
    except OSError:
        pass
    assert boot._has_root_file_pollution_quick(is_hub_root=False) is True
    hygiene_fast = boot._check_root_hygiene(use_fast_cache=True, cached={"root_mtime": boot._get_root_mtime(), "timestamp_epoch": time.time(), "root_hygiene_violations": []})
    assert hygiene_fast["passed"] is False and "rogue_artifact.tmp" in hygiene_fast["violations"]
    assert boot.run_bootstrap(fast_stat=True)["checks"]["project_isolation"]["passed"] is False

    tmp_polluter.unlink(missing_ok=True)
    assert boot.run_bootstrap(fast_stat=False)["status"] == "PASS"

    stale_wal = ws_root / ".wal" / "expired_tx.wal"
    stale_wal.write_text('{"state": "PREPARE"}', encoding="utf-8")
    old_ts = time.time() - 180.0
    os.utime(stale_wal, (old_ts, old_ts))
    res_wal = boot.run_bootstrap(fast_stat=True)
    assert res_wal["status"] == "PASS" and not stale_wal.exists() and res_wal["checks"]["wal_hygiene"]["stale_wals_purged"] >= 1


@pytest.mark.fast
def test_session_bootstrap_baseline_onboarding_and_recent_transcript(tmp_path: Path) -> None:
    """Verifica baseline 50% fail, onboarding bypass, transcript recente e resilienza tail."""
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    NKSessionBootstrap = boot_mod.NKSessionBootstrap
    ws_root = tmp_path / "onboarding_ws"
    for sub in ("nk_tracking", ".wal", "scripts", ".agents"):
        (ws_root / sub).mkdir(parents=True, exist_ok=True)
    baseline_file = ws_root / "nk_tracking" / "quality_baseline.json"
    baseline_file.write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 50.0, "unit_tests_total": 100}}), encoding="utf-8")

    boot_base = NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-base")
    res_bad = boot_base.run_bootstrap(fast_stat=True)
    assert res_bad["status"] == "FAIL" and res_bad["checks"]["quality_baseline"]["unit_pass_pct"] == 50.0

    tp_err = tmp_path / "transcript_err.jsonl"
    tp_err.write_text(json.dumps({"source": "USER", "content": "Analizza il bug per cui avvia nk hub mostra un errore"}) + "\n", encoding="utf-8")
    assert NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-ob-1", transcript_path=tp_err)._resolve_onboarding_and_gate_mode() == ("NONE", "CONFIRM")

    tp_ok = tmp_path / "transcript_ok.jsonl"
    tp_ok.write_text(json.dumps({"source": "USER", "content": "Avvia NK Hub!"}) + "\n", encoding="utf-8")
    assert NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-ob-2", transcript_path=tp_ok)._resolve_onboarding_and_gate_mode() == ("ONBOARDING_BYPASS_VERIFIED", "BYPASSED")

    baseline_file.write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8")
    fake_brain = tmp_path / "brain"
    conv_old = fake_brain / "conv-old-red" / ".system_generated" / "logs"
    conv_old.mkdir(parents=True, exist_ok=True)
    tp_red = conv_old / "transcript.jsonl"
    tp_red.write_text("".join(json.dumps({"step_index": i, "source": "USER", "content": "x" * 1200}) + "\n" for i in range(260)), encoding="utf-8")
    assert NKSessionBootstrap(workspace_root=ws_root, conversation_id="conv-old-red", transcript_path=tp_red).run_bootstrap(fast_stat=False)["checks"]["context_sentry"]["status"] == "RED"

    boot_anon = NKSessionBootstrap(workspace_root=ws_root, conversation_id="")
    stale_300s = time.time() - 300.0
    os.utime(tp_red, (stale_300s, stale_300s))
    assert boot_anon._find_recent_transcript(fake_brain) is None
    now_ts = time.time()
    os.utime(tp_red, (now_ts, now_ts))
    assert boot_anon.run_bootstrap(fast_stat=True)["checks"]["context_sentry"]["status"] != "RED"
    _verify_bootstrap_resilience_invariants(tmp_path)


def _verify_bootstrap_resilience_invariants(tmp_path: Path) -> None:
    """Verifica la guardia O(1) kv_cache_cold_risk e rpc_stream_burst_risk."""
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    sentry_mod = load_nk_script_module("nk_context_sentry")
    assert sentry_mod.NKContextSentry._extract_actual_tokens_from_record({"input_tokens": 5582, "cache_read_tokens": 55484}) == 61066

    tp_res = tmp_path / "transcript_resilience.jsonl"
    lines = [
        json.dumps({"step_index": 56, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-09T18:45:49Z", "input_tokens": 5582, "cache_read_tokens": 55484, "content": "Analisi."}),
        json.dumps({"step_index": 57, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-09T18:50:13Z", "content": "Procedi."}),
        json.dumps({"step_index": 84, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-09T18:50:15Z", "input_tokens": 62615, "cache_read_tokens": 0, "output_tokens": 7136, "tool_calls": [{"name": "write_file"} for _ in range(4)], "content": "Write."}),
    ]
    tp_res.write_text("\n".join(lines) + "\n", encoding="utf-8")
    risks = boot_mod._inspect_tail_resilience_risks(tp_res, t_size=tp_res.stat().st_size, est_tokens=15000)
    assert risks["kv_cache_cold_risk"] is True and risks["rpc_stream_burst_risk"] is True
    assert risks["idle_gap_seconds"] >= 264.0 and risks["effective_context_tokens"] >= 62615
    rep = sentry_mod.NKContextSentry(workspace_root=tmp_path, profile="argon").analyze_transcript(tp_res)
    assert rep["kv_cache_cold_risk"] is True and rep["rpc_stream_burst_risk"] is True


@pytest.mark.fast
def test_api_cache_wal_and_env_probe_gt09(tmp_path: Path) -> None:
    """Verifica cache SQLite WAL persistente e sonda capacita env GT-09."""
    c_dir = tmp_path / "cache"
    c_dir.mkdir()
    _util_api_cache_wal(c_dir)
    _util_env_probe_gt09(tmp_path)


@pytest.mark.fast
def test_external_scaffolder_isolation_and_tetralogy(tmp_path: Path) -> None:
    """Verifica isolamento path interno Hub e generazione DDD/Pentad esterna."""
    _util_scaffolder_reject()
    s_dir = tmp_path / "scaffolder"
    s_dir.mkdir()
    _util_scaffolder_full(s_dir)


@pytest.mark.fast
def test_oracle_l3_void_tags_conf10_and_micro_hud(tmp_path: Path) -> None:
    """Verifica void tag HTML5, CONF-10 expected .json/.md + LFI guard e Micro-HUD."""
    p1 = tmp_path / "l3_void"
    p1.mkdir()
    _util_oracle_void_tags_hud(p1)
    p2 = tmp_path / "l3_conf10"
    p2.mkdir()
    _util_oracle_conf10(p2)


@pytest.mark.integration
def test_platform_runner_unbuffered_tree_kill_and_utf8() -> None:
    """Verifica normalizzazione -u, cattura UTF-8, errori e tree-kill timeout."""
    _util_platform_unbuffered()
    _util_platform_tree_kill_utf8()


@pytest.mark.fast
def test_safe_cleanup_filter_and_async_heartbeat_cli(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifica filtro CWD/cmdline dev server e CLI heartbeat/cleanup deterministici."""
    p1 = tmp_path / "sc_filter"
    p1.mkdir()
    _util_safe_cleanup_filter(p1)
    p2 = tmp_path / "hb_cli"
    p2.mkdir()
    with monkeypatch.context() as mp:
        _util_heartbeat_cleanup_cli(p2, mp, capsys)
    assert capsys.readouterr().out == ""


@pytest.mark.fast
def test_agents_rule_00_5_and_session_bootstrap_fast_stat() -> None:
    """Verifica [RULE-00.5] in AGENTS/skills e bootstrap Fast-Stat PASS."""
    _util_agents_rule_00_5()
    _util_session_bootstrap_fast_stat()


@pytest.mark.fast
def test_invisible_healing_loop_retry_and_escalation(tmp_path: Path) -> None:
    """Verifica KarpathySlicer, token budget SBFL, telemetria HEALED ed ESCALATED."""
    p1, p2 = tmp_path / "heal_ok", tmp_path / "heal_esc"
    p1.mkdir()
    p2.mkdir()
    _util_healing_retry(p1)
    _util_healing_escalate(p2)


@pytest.mark.fast
def test_p1_3_bootstrap_conv_inference_workspace_cache_and_nk_common(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Regressione [P1-3]: cache workspace-keyed, inferenza conv_id e invalidazione tail."""
    boot_mod = load_nk_script_module("nk_session_bootstrap")
    NKSessionBootstrap = boot_mod.NKSessionBootstrap
    ws_a, ws_b = tmp_path / "ws_alpha", tmp_path / "ws_beta"
    for ws in (ws_a, ws_b):
        for sub in ("nk_tracking", ".wal", "scripts", ".agents"):
            (ws / sub).mkdir(parents=True, exist_ok=True)
        (ws / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8")

    boot_a = NKSessionBootstrap(workspace_root=ws_a, conversation_id="conv-a")
    boot_b = NKSessionBootstrap(workspace_root=ws_b, conversation_id="conv-b")
    assert boot_a.fast_cache_file != boot_b.fast_cache_file and boot_a.state_file != boot_b.state_file
    assert ".bootstrap_fast_cache_" in boot_a.fast_cache_file.name
    assert boot_a.run_bootstrap(fast_stat=False)["status"] == "PASS" and boot_b.run_bootstrap(fast_stat=False)["status"] == "PASS"
    assert json.loads(boot_a.fast_cache_file.read_text(encoding="utf-8"))["workspace_root"] == str(ws_a.resolve())

    hooks_dir = isolated_nk_env / "nk_hooks_env"
    (hooks_dir / "probe_cli_conv_99.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("NK_CONVERSATION_ID", raising=False)
    assert NKSessionBootstrap(workspace_root=boot_mod.HUB_ROOT, hook_mode=False).conversation_id == "cli_conv_99"
    assert NKSessionBootstrap(workspace_root=ws_a, hook_mode=False).conversation_id == ""

    ws_c = tmp_path / "ws_gamma"
    for sub in ("nk_tracking", ".wal", "scripts", ".agents"):
        (ws_c / sub).mkdir(parents=True, exist_ok=True)
    (ws_c / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 100}}), encoding="utf-8")
    tp_c = tmp_path / "tp_p13.jsonl"
    tp_c.write_text(json.dumps({"step_index": 1, "source": "USER", "content": "ciao"}) + "\n", encoding="utf-8")
    boot_c = NKSessionBootstrap(workspace_root=ws_c, conversation_id="conv-c", transcript_path=tp_c)
    assert boot_c.run_bootstrap(fast_stat=False)["onboarding_bypass"] == "NONE"

    with tp_c.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"step_index": 2, "source": "MODEL", "content": "ok"}) + "\n")
    assert boot_c._can_fast_pass() is True
    assert "fast_stat" in boot_c.run_bootstrap(fast_stat=True)["checks"]
    disk_c = json.loads(boot_c.fast_cache_file.read_text(encoding="utf-8"))
    assert disk_c["last_transcript_size"] == tp_c.stat().st_size and disk_c["last_step_count"] == 2 and disk_c["latest_user_prompt"] == "ciao"

    with tp_c.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"step_index": 3, "source": "USER", "type": "USER_INPUT", "content": "avvia nk hub"}) + "\n")
    assert boot_c._can_fast_pass() is False
    assert boot_c.run_bootstrap(fast_stat=True)["onboarding_bypass"] == "ONBOARDING_BYPASS_VERIFIED"
    boot_c.explicit_prompt = "analizza bug"
    assert boot_c._can_fast_pass() is False
    assert boot_c.run_bootstrap(fast_stat=True, prompt="analizza bug")["onboarding_bypass"] == "NONE"


@pytest.mark.fast
def test_nk_common_primitives_paths_io_mutex_guards_linter(tmp_path: Path) -> None:
    """Verifica diretta delle primitive _internal.nk_common senza mock."""
    from _internal.nk_common import constants as nc_consts, io as nc_io, paths as nc_paths, prompt_linter_core as nc_lint, transcript_guards as nc_guards, win32_mutex as nc_mutex

    assert len(nc_consts.HALLUCINATED_SCRIPT_DENYLIST) == 32
    assert Path(nc_paths.resolve_scripts_dir(str(WORKSPACE_ROOT / ".staging" / "scripts" / "_internal" / "nk_common" / "paths.py"))).name == "scripts"
    assert Path(nc_paths.resolve_workspace_root(str(WORKSPACE_ROOT / ".staging" / "scripts" / "nk_session_bootstrap.py"))) == WORKSPACE_ROOT.resolve()
    assert Path(nc_paths.resolve_workspace_root(str(WORKSPACE_ROOT / "scripts" / "_internal" / "nk_common" / "paths.py"))) == WORKSPACE_ROOT.resolve()

    io_target = tmp_path / "nc_io_test.json"
    ok_w, err_w = nc_io.atomic_write_json(io_target, {"status": "OK", "count": 2})
    assert ok_w is True and err_w is None and json.loads(io_target.read_text(encoding="utf-8")) == {"status": "OK", "count": 2}
    assert nc_io.unlink_with_retry(io_target) is True and not io_target.exists()
    assert nc_mutex.is_win32_handle_valid(None) is (sys.platform != "win32")
    assert nc_mutex.is_win32_handle_valid(-1) is (sys.platform != "win32") and nc_mutex.is_win32_handle_valid(42) is True
    assert nc_guards.has_compaction_candidate_bytes(b'{"type": "CHECKPOINT"}') is True
    assert nc_guards.is_verified_compaction({"source": "SYSTEM", "type": "CHECKPOINT"}) is True
    assert nc_guards.is_verified_compaction({"source": "MODEL", "type": "CHECKPOINT"}) is False
    sub_tp = tmp_path / "nc_sub.jsonl"
    sub_tp.write_text(json.dumps({"step_index": 0, "source": "SYSTEM", "content": "<subagent_reminder>ok"}) + "\n", encoding="utf-8")
    assert nc_guards.is_subagent_transcript_head(sub_tp, max_non_empty=5) is True

    lint_out = nc_lint.evaluate_ap_rules("!diretto\nFase 1: modifica src_app/x.py\nFase 2: continua\n")
    assert lint_out["passed"] is False and lint_out["valid"] is False and lint_out["violation_count"] == len(lint_out["violations"])
    assert all({"code", "id", "severity", "message", "msg"}.issubset(v.keys()) for v in lint_out["violations"])


@pytest.mark.fast
def test_preflight_anchor_rogue_stashes_wal_quarantine_and_cli(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Chiude i branch di preflight_health_check su anchor corrotto, stashes, WAL e CLI."""
    ws = tmp_path / "preflight_branch_ws"
    for d in (".agents/skills", "nk_genome", "nk_tracking/anchor", "nk_tracking/handoff/stashes", ".wal", ".staging", "scripts", "tests"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    ro_file = ws / ".commit_ready" / "ro.txt"
    ro_file.parent.mkdir(parents=True)
    ro_file.write_text("locked", encoding="utf-8")
    os.chmod(ro_file, stat.S_IREAD)
    assert preflight_mod.safe_remove_dir(ro_file.parent) is True and not ro_file.parent.exists()

    (ws / ".sandbox_tmp").mkdir()
    (ws / "nk_tracking" / "handoff" / "stashes" / "leftover.patch").write_text("diff", encoding="utf-8")
    (ws / "session_anchor.jsonl").write_text("{}\n", encoding="utf-8")
    (ws / "nk_tracking" / "anchor" / "session_anchor.jsonl").write_text('{"event": "A"}\n\n{bad\n{"event": "A"}\n', encoding="utf-8")
    (ws / ".wal" / "old_commit.wal").write_text('{"state": "COMMITTED"}\n', encoding="utf-8")
    (ws / ".wal" / "corrupt.wal").write_text("{bad\n", encoding="utf-8")
    for w in (ws / ".wal" / "old_commit.wal", ws / ".wal" / "corrupt.wal"):
        os.utime(w, (time.time() - 300.0, time.time() - 300.0))

    assert PreflightHealthChecker._is_committed_wal(ws / ".wal" / "old_commit.wal") is True
    assert PreflightHealthChecker._is_committed_wal(ws / ".wal" / "corrupt.wal") is False
    checker = PreflightHealthChecker(workspace_root=ws)
    assert checker.run_full_check(auto_fix=False)["status"] == "FAIL"
    rep_fix = checker.run_full_check(auto_fix=True)
    assert rep_fix["checks"]["staging_hygiene"]["passed"] is True
    assert not (ws / "session_anchor.jsonl").exists()

    monkeypatch.setattr(sys, "argv", ["preflight_health_check.py", "--root", str(ws), "--json"])
    assert preflight_mod.main() == 1 and "status" in json.loads(capsys.readouterr().out)


@pytest.mark.fast
def test_session_handoff_cursor_cache_incremental_and_pending_line(tmp_path: Path) -> None:
    """Chiude i branch di cache cursore incrementale in nk_session_handoff.py."""
    handoff_mod = load_nk_script_module("nk_session_handoff")
    tp = tmp_path / "handoff_cursor.jsonl"
    tp.write_text(json.dumps({"step_index": 1, "source": "USER", "content": "start"}) + "\n", encoding="utf-8")
    s1, b1, t1, _ = handoff_mod._inspect_transcript_fast(str(tp))
    assert s1 == 1 and b1 > 0 and "start" in t1
    # Cache hit esatto a dimensione invariata
    assert handoff_mod._inspect_transcript_fast(str(tp))[0] == 1

    # Delta committato + riga parziale senza newline finale + checkpoint successivo
    with tp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"step_index": 2, "source": "MODEL", "input_tokens": 1200, "content": "mid"}) + "\n")
        fh.write(json.dumps({"step_index": 3, "source": "MODEL", "content": "pending_tail"}))
    s2, _, t2, tok2 = handoff_mod._inspect_transcript_fast(str(tp))
    assert s2 == 3 and tok2 == 1200 and "pending_tail" in t2

    with tp.open("a", encoding="utf-8") as fh:
        fh.write("\n" + json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "content": "SYSTEM CHECKPOINT"}) + "\n")
        fh.write(json.dumps({"step_index": 4, "source": "MODEL", "input_tokens": 300, "content": "post_ckpt"}))
    s3, _, t3, tok3 = handoff_mod._inspect_transcript_fast(str(tp))
    assert s3 == 2 and tok3 == 300 and "post_ckpt" in t3


@pytest.mark.fast
def test_bootstrap_wal_hygiene_and_root_hygiene_branches(tmp_path: Path) -> None:
    """Chiude i branch di wal_hygiene.py e root_hygiene.py in nk_session_bootstrap."""
    from _internal.nk_session_bootstrap import root_hygiene as rh, wal_hygiene as wh

    load_nk_script_module("nk_session_bootstrap")
    boot = load_nk_script_module("nk_session_bootstrap").NKSessionBootstrap(workspace_root=tmp_path)
    (tmp_path / ".wal" / "quarantine").mkdir(parents=True)
    assert wh.has_actionable_wal_entries(boot) is False
    tx_wal = tmp_path / ".wal" / "tx.wal"
    tx_wal.write_text('{"state": "PREPARE"}\n{"state": "COMMITTED"}\n', encoding="utf-8")
    assert wh.has_actionable_wal_entries(boot) is True
    assert wh.inspect_wal_state(tx_wal) == "COMMITTED"

    empty_wal = tmp_path / ".wal" / "empty.wal"
    empty_wal.write_text("", encoding="utf-8")
    bad_utf8 = tmp_path / ".wal" / "bin.wal"
    bad_utf8.write_bytes(b"\xff\xfe\xfd")
    list_wal = tmp_path / ".wal" / "list.wal"
    list_wal.write_text("[1, 2]", encoding="utf-8")
    assert wh.inspect_wal_state(empty_wal) == "CORRUPTED"
    assert wh.inspect_wal_state(bad_utf8) == "CORRUPTED" and wh.inspect_wal_state(list_wal) == "CORRUPTED"

    (tmp_path / ".staging").mkdir()
    (tmp_path / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    assert rh.is_staging_dirty(boot) is False
    stg_mt = rh.get_staging_mtime(boot)
    assert rh.is_staging_dirty(boot, cached={"staging_mtime": stg_mt, "staging_dirty_warning": True}) is True
    (tmp_path / ".staging" / "dirty.py").write_text("x = 1\n", encoding="utf-8")
    boot._cached_staging_mtime = None
    assert rh.is_staging_dirty(boot) is True

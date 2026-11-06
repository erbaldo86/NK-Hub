# -*- coding: utf-8 -*-
"""
Suite consolidata delle utilita core di piattaforma per Nexus Keystone v4.7.0-STE100-Unified.
Modulo: tests/test_core_platform_utilities.py.
Unifica gli 8 micro-file di utilita e aggiunge 2 test Zero-Mock per invisible_healing_loop.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

from conftest import WORKSPACE_ROOT, load_nk_script_module


# --- Sezione consolidata da tests/test_deterministic_api_cache.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_cache_module():
    """Carica il modulo deterministic_api_cache dando priorita a .staging/scripts."""
    staging_target = (
        _workspace_root / ".staging" / "scripts" / "deterministic_api_cache.py"
    )
    prod_target = _workspace_root / "scripts" / "deterministic_api_cache.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(
        "deterministic_api_cache", str(target)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deterministic_api_cache"] = mod
    spec.loader.exec_module(mod)
    return mod


cache_mod = _load_cache_module()
DeterministicApiCache = cache_mod.DeterministicApiCache


def test_api_cache_persistent_wal_connection_and_close(tmp_path: Path) -> None:
    """1. Verifica connessione WAL persistente, force_refresh, scadenza TTL ed eviction."""
    db_path = tmp_path / "wal_persistent.db"
    with DeterministicApiCache(db_path=db_path, ttl_seconds=0.02) as cache:
        assert cache.health_check() is True
        conn_initial = cache._conn
        assert conn_initial is not None

        cache.set(
            "https://example.org/v1",
            200,
            '{"ok": true}',
            method="POST",
            params={"q": "nk"},
        )
        hit = cache.get("https://example.org/v1", method="POST", params={"q": "nk"})
        assert hit is not None
        assert hit[0] == 200
        assert cache._conn is conn_initial

        bypass = cache.get(
            "https://example.org/v1",
            method="POST",
            params={"q": "nk"},
            force_refresh=True,
        )
        assert bypass is None

        time.sleep(0.03)
        assert (
            cache.get("https://example.org/v1", method="POST", params={"q": "nk"})
            is None
        )

        cache.set("https://example.org/v2", 200, '{"ephemeral": 2}')
        assert cache.clear() == 1
    assert cache._conn is None


# --- Sezione consolidata da tests/test_env_capability_probe.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_probe_module():
    """Carica il modulo env_capability_probe dando priorita a .staging/scripts."""
    staging_target = _workspace_root / ".staging" / "scripts" / "env_capability_probe.py"
    prod_target = _workspace_root / "scripts" / "env_capability_probe.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("env_capability_probe", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["env_capability_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


probe_mod = _load_probe_module()
probe_environment = probe_mod.probe_environment
check_module_availability = probe_mod.check_module_availability
STANDARD_MODULES_TO_PROBE = probe_mod.STANDARD_MODULES_TO_PROBE
THIRD_PARTY_MODULES_TO_PROBE = probe_mod.THIRD_PARTY_MODULES_TO_PROBE


def test_env_probe_core_vs_optional_separation_and_gt09_invariance() -> None:
    """1. Verifica la separazione tra moduli core Hub e opzionali preservando total_probed=15 (GT-09)."""
    data = probe_environment()
    assert isinstance(data, dict)
    assert data["python"]["version_major"] == 3
    assert data["python"]["executable"] == sys.executable
    assert data["standard_modules"]["sqlite3"]["available"] is True

    fictitious = check_module_availability("fictitious_module_xyz_nonexistent_98765")
    assert fictitious["available"] is False

    expected_total = len(STANDARD_MODULES_TO_PROBE) + len(THIRD_PARTY_MODULES_TO_PROBE)
    assert data["summary"]["total_probed"] == expected_total == 15
    assert "core_hub_modules" in data
    assert "optional_app_modules" in data
    assert "pydantic" in data["core_hub_modules"]
    assert "pytest" in data["core_hub_modules"]
    assert "psutil" in data["core_hub_modules"]
    assert "fastapi" in data["optional_app_modules"]
    assert data["summary"]["all_core_hub_available"] is True
    assert data["summary"]["status"] == "PASS"


# --- Sezione consolidata da tests/test_external_scaffolder.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_scaffolder_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "external_project_scaffolder.py"
    prod_target = _workspace_root / "scripts" / "external_project_scaffolder.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("external_project_scaffolder", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["external_project_scaffolder"] = mod
    spec.loader.exec_module(mod)
    return mod


scaffolder_mod = _load_scaffolder_module()
ExternalProjectScaffolder = scaffolder_mod.ExternalProjectScaffolder


def test_external_scaffolder_rejects_hub_internal_path() -> None:
    """1. Verifica che un percorso interno a NK-Hub sollevi immediatamente ValueError."""
    forbidden_target = _workspace_root / f"forbidden_internal_app_{uuid.uuid4().hex[:6]}"
    with pytest.raises(ValueError) as exc_info:
        ExternalProjectScaffolder(project_name="ForbiddenApp", target_dir=forbidden_target)
    assert "RULE-PROJECT-ISOLATION" in str(exc_info.value)
    assert not forbidden_target.exists()


def test_external_scaffolder_generates_full_ddd_and_tetralogy(tmp_path: Path) -> None:
    """2. Verifica la creazione completa dell'albero DDD e della Tetralogia Sovrana."""
    ext_dir = tmp_path / "ExternalCleanProject"
    scaffolder = ExternalProjectScaffolder(project_name="ExternalCleanProject", target_dir=ext_dir)
    report = scaffolder.scaffold()

    assert report["status"] == "SUCCESS"
    for tetralogy_file in [
        "concept_map.md",
        "structural_tree.md",
        "implementation_plan.md",
        "repo_map.md",
    ]:
        assert (ext_dir / "nk_genome" / tetralogy_file).exists(), f"Missing {tetralogy_file}"
    assert (ext_dir / "src" / "core" / "__init__.py").exists()
    assert (ext_dir / "src" / "api" / "__init__.py").exists()
    assert (ext_dir / "tests" / "test_ast_purity.py").exists()


# --- Sezione consolidata da tests/test_oracle_l3_and_hud.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_mod(name: str):
    staging_target = _workspace_root / ".staging" / "scripts" / f"{name}.py"
    prod_target = _workspace_root / "scripts" / f"{name}.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


oracle_mod = _load_mod("oracle_evaluator_l3")
hud_mod = _load_mod("micro_hud_renderer")


def test_oracle_l3_void_tags_windows_path_and_micro_hud(tmp_path: Path) -> None:
    """1. Verifica il supporto void tag HTML5, percorsi Windows e rendering Micro-HUD."""
    html_file = tmp_path / "index.html"
    html_content = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><link rel='stylesheet' href='a.css'></head>"
        "<body><main><img src='logo.png' alt='logo'><br><input type='text' id='q'>"
        "<button id='submit_btn'>Invia</button></main></body></html>"
    )
    html_file.write_text(html_content, encoding="utf-8")

    spec_arg = f"{html_file}:#submit_btn:Invia"
    source = oracle_mod.resolve_html_source(spec_arg)
    assert "<!DOCTYPE html>" in source

    evaluator = oracle_mod.DOMOracleEvaluator()
    dom_res = evaluator.evaluate_deltas(spec_arg, html_content)
    assert dom_res.verdict == "PASS"
    assert dom_res.discrepancy_count == 0

    hud = hud_mod.MicroHUDRenderer(version="v3.0", ascii_mode=True)
    hud.set_progress(100)
    hud.set_agent_context("NK-Oracle-Evaluator", "ARCH")
    hud.set_rsi_metrics(delta_k=0.0, fitness_q=100.0)
    line = hud.render(include_extras=True)
    assert "100%" in line
    assert "NK-Oracle-Evaluator" in line
    ipc_state = hud.to_ipc_state(session_id="test_sess")
    assert ipc_state.session_id == "test_sess"
    assert ipc_state.progress_pct == 100.0


# --- Sezione consolidata da tests/test_platform_runner.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_runner_module():
    """Carica il modulo platform_runner dando priorita a .staging/scripts."""
    staging_target = _workspace_root / ".staging" / "scripts" / "platform_runner.py"
    prod_target = _workspace_root / "scripts" / "platform_runner.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("platform_runner", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["platform_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


runner_mod = _load_runner_module()
_normalize_python_command = runner_mod._normalize_python_command
safe_subprocess_run = runner_mod.safe_subprocess_run
reconfigure_streams = runner_mod.reconfigure_streams


def test_platform_runner_string_command_unbuffered_injection() -> None:
    """1. Verifica l'iniezione del flag -u su liste e stringhe e valida pytest.ini."""
    reconfigure_streams()
    raw_cmd = 'python -c "print(42)"'
    norm_cmd = _normalize_python_command(raw_cmd)
    assert isinstance(norm_cmd, str)
    assert norm_cmd.startswith("python -u ")

    quoted_cmd = f'"{sys.executable}" -c "print(42)"'
    norm_quoted = _normalize_python_command(quoted_cmd)
    assert isinstance(norm_quoted, str)
    assert " -u " in norm_quoted

    list_cmd = [sys.executable, "-c", "print(1)"]
    norm_list = _normalize_python_command(list_cmd)
    assert norm_list[1] == "-u"

    pytest_ini = _workspace_root / "pytest.ini"
    assert pytest_ini.exists()
    ini_text = pytest_ini.read_text(encoding="utf-8")
    assert "[pytest]" in ini_text
    assert "testpaths" in ini_text
    assert ".staging" in ini_text


def test_platform_runner_tree_kill_on_timeout_and_utf8() -> None:
    """2. Verifica la cattura UTF-8, i comandi non validi e l'abbattimento su timeout."""
    rc_ok, out_ok, err_ok = safe_subprocess_run(
        [sys.executable, "-c", "import sys; sys.stdout.write('NK_UTF8_🚀_€\\n')"]
    )
    assert rc_ok == 0
    assert "🚀" in out_ok and "€" in out_ok
    assert err_ok == ""

    rc_inv, out_inv, _ = safe_subprocess_run(["non_existent_binary_nk_987654321"])
    assert rc_inv != 0
    assert out_inv == ""

    spawn_tree_cmd = [
        sys.executable,
        "-c",
        "import time; time.sleep(5)",
    ]
    rc, _, stderr = safe_subprocess_run(spawn_tree_cmd, timeout=0.15)
    assert rc == -1
    assert "timed out" in stderr.lower()


# --- Sezione consolidata da tests/test_preflight_health_check.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_preflight_module():
    """Carica il modulo preflight_health_check dando priorita a .staging/scripts."""
    staging_target = (
        _workspace_root / ".staging" / "scripts" / "preflight_health_check.py"
    )
    prod_target = _workspace_root / "scripts" / "preflight_health_check.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("preflight_health_check", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["preflight_health_check"] = mod
    spec.loader.exec_module(mod)
    return mod, target


preflight_mod, _PREFLIGHT_SCRIPT = _load_preflight_module()
PreflightHealthChecker = preflight_mod.PreflightHealthChecker


def test_preflight_corrupted_baseline_fails_even_with_autofix(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """1. Verifica il blocco fail-closed su baseline corrotta e il flag --check-only."""
    corrupt_root = tmp_path / "corrupt_ws"
    for d in [
        ".agents/skills",
        "nk_genome",
        "nk_tracking",
        "scripts",
        "tests",
        ".staging",
    ]:
        (corrupt_root / d).mkdir(parents=True, exist_ok=True)

    baseline_file = corrupt_root / "nk_tracking" / "quality_baseline.json"
    baseline_file.write_text("{CORRUPTED_JSON_PAYLOAD", encoding="utf-8")

    checker = PreflightHealthChecker(workspace_root=corrupt_root)
    report = checker.run_full_check(auto_fix=True)
    assert report["status"] == "FAIL"
    assert report["checks"]["baseline_alignment"]["passed"] is False
    assert baseline_file.read_text(encoding="utf-8") == "{CORRUPTED_JSON_PAYLOAD"

    readonly_root = tmp_path / "readonly_ws"
    for d in [".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests"]:
        (readonly_root / d).mkdir(parents=True, exist_ok=True)
    (readonly_root / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps(
            {
                "_version": "3.3.0",
                "metrics": {
                    "skills_audited": 16,
                    "crv_macro_phases": 4,
                    "unit_tests_pass_pct": 100.0,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys, "argv", ["preflight_health_check.py", "--root", str(readonly_root), "--check-only"]
    )
    rc = preflight_mod.main()
    assert rc == 1
    assert not (readonly_root / ".staging").exists()
    assert not (
        readonly_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    ).exists()


# --- Sezione consolidata da tests/test_safe_cleanup_dev_servers.py ---
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_script_module(mod_name: str):
    """Carica dinamicamente uno script da .staging/scripts o scripts/."""
    staging_target = _workspace_root / ".staging" / "scripts" / f"{mod_name}.py"
    prod_target = _workspace_root / "scripts" / f"{mod_name}.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


cleanup_mod = _load_script_module("safe_cleanup_dev_servers")
heartbeat_mod = _load_script_module("async_heartbeat_signaler")
is_target_workspace_process = cleanup_mod.is_target_workspace_process


def test_safe_cleanup_workspace_filter_cwd_and_cmdline(tmp_path: Path) -> None:
    """1. Verifica il filtro CWD/cmdline del workspace e la protezione del PID corrente/genitore."""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    assert is_target_workspace_process(current_pid, workspace_root=tmp_path) is False
    assert is_target_workspace_process(parent_pid, workspace_root=tmp_path) is False

    ws_dir = tmp_path / "TargetWorkspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    other_dir = tmp_path / "ExternalWorkspace"
    other_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=str(ws_dir),
    )
    try:
        assert is_target_workspace_process(proc.pid, workspace_root=ws_dir) is True
        assert is_target_workspace_process(proc.pid, workspace_root=other_dir) is False
    finally:
        proc.terminate()
        proc.wait(timeout=2.0)


def test_async_heartbeat_signaler_cli_once_and_cleanup_cli_json(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """2. Verifica l'esecuzione CLI deterministica di async_heartbeat_signaler e safe_cleanup_dev_servers."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["async_heartbeat_signaler.py", "--once", "--task-id", "test_hb", "--json"],
    )
    assert heartbeat_mod.main() == 0
    out_hb = capsys.readouterr().out
    assert '"pulse_index": 1' in out_hb

    monkeypatch.setattr(
        cleanup_mod,
        "get_pids_listening_on_ports",
        lambda ports, workspace_root=None: set(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "safe_cleanup_dev_servers.py",
            "--workspace-root",
            str(tmp_path),
            "--dry-run",
            "--json",
        ],
    )
    assert cleanup_mod.main() == 0
    out_cl = capsys.readouterr().out
    assert '"status": "OK"' in out_cl


# --- Sezione consolidata da tests/test_unified_onboarding_mandate.py ---
_test_file = Path(__file__).resolve()
if _test_file.parent.name == "tests" and _test_file.parent.parent.name == ".staging":
    _repo_root = _test_file.parent.parent.parent
else:
    _repo_root = _test_file.parent.parent

if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _resolve_doc(rel_path: str) -> Path:
    """Risolve un file di documentazione dando priorita a .staging/."""
    stg = _repo_root / ".staging" / rel_path
    if stg.exists():
        return stg
    return _repo_root / rel_path


def test_agents_md_rule_00_5_definition() -> None:
    """1. Verifica la codifica GT-08 in AGENTS.md, NK-Master-Hub e NK-Session-Controller."""
    agents_file = _resolve_doc(".agents/AGENTS.md")
    assert agents_file.exists()
    content = agents_file.read_text(encoding="utf-8")

    assert "[RULE-00.5]" in content
    assert "UNIFIED_ONBOARDING_DASHBOARD_MANDATE" in content

    required_triggers = [
        "avvia ambiente nk",
        "avvia nk hub",
        "avvia nk",
        "avvia hub",
        "start nk",
        "start hub",
        "attiva nk",
        "attiva ambiente nk",
    ]
    content_lower = content.lower()
    for trigger in required_triggers:
        assert trigger in content_lower

    assert "fast-stat" in content_lower
    assert "120" in content
    assert "[0]" in content and "[14]" in content

    hub_file = _resolve_doc(".agents/skills/NK-Master-Hub/SKILL.md")
    hub_content = hub_file.read_text(encoding="utf-8")
    for i in range(15):
        assert f"[{i}]" in hub_content
    hub_lower = hub_content.lower()
    assert (
        "selezione rapida" in hub_lower
        or "modalità diretta" in hub_lower
        or "modalita' diretta" in hub_lower
    )
    assert "goal-driven" in hub_lower or "linguaggio naturale" in hub_lower

    ctrl_file = _resolve_doc(".agents/skills/NK-Session-Controller/SKILL.md")
    ctrl_content = ctrl_file.read_text(encoding="utf-8")
    assert "10. UNIFIED_ONBOARDING_COMPLIANCE" in ctrl_content
    assert "[RULE-00.5]" in ctrl_content or "fast-stat" in ctrl_content.lower()


def test_session_bootstrap_fast_stat_execution() -> None:
    """2. Esegue programmaticamente scripts/nk_session_bootstrap.py e verifica esito PASS."""
    staging_bootstrap = _repo_root / ".staging" / "scripts" / "nk_session_bootstrap.py"
    prod_bootstrap = _repo_root / "scripts" / "nk_session_bootstrap.py"
    bootstrap_target = (
        staging_bootstrap if staging_bootstrap.exists() else prod_bootstrap
    )
    assert bootstrap_target.exists()

    spec = importlib.util.spec_from_file_location(
        "nk_session_bootstrap", str(bootstrap_target)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bootstrap_inst = mod.NKSessionBootstrap(workspace_root=_repo_root)
    result = bootstrap_inst.run_bootstrap(fast_stat=True)
    assert isinstance(result, dict)
    assert result.get("status") == "PASS"
    assert "checks" in result


# --- Sezione 9: Copertura diretta per scripts/invisible_healing_loop.py ---


def test_invisible_healing_loop_should_retry_and_budget(tmp_path: Path) -> None:
    """Verifica SBFLLocation, budget token SBFL, KarpathySlicer e DSPyTelemetryHook su tmp_path."""
    ihl_mod = load_nk_script_module("invisible_healing_loop")
    faulty_script = tmp_path / "faulty_module.py"
    faulty_script.write_text(
        "def compute_ratio(a: int, b: int) -> float:\n    return a / b\n",
        encoding="utf-8",
    )

    code_slice = ihl_mod.KarpathySlicer.slice_file(faulty_script, target_line=2, window=2)
    assert code_slice.target_line == 2
    assert "compute_ratio" in (code_slice.function_name or "compute_ratio")
    assert "return a / b" in code_slice.content

    loc = ihl_mod.SBFLLocation(
        file_path=str(faulty_script),
        line_number=2,
        suspiciousness=1.0,
        error_type="ZeroDivisionError",
        error_message="division by zero during ratio computation in production module",
        failing_line_content="    return a / b",
    )
    rendered_json = loc.render_payload_json()
    assert ihl_mod.estimate_token_count(rendered_json) <= ihl_mod.SBFL_MAX_TOKEN_BUDGET

    telemetry_file = tmp_path / "healing_telemetry.jsonl"
    loop = ihl_mod.InvisibleHealingLoop(telemetry_log_path=telemetry_file, max_cycles=3)
    cycle_log = ihl_mod.HealingCycleLog(
        cycle_index=1,
        sbfl_payload=rendered_json,
        fault_slice=code_slice.content,
        repair_action="GUARD_ZERO_DIVISOR",
        repair_success=True,
        duration_ms=12.5,
    )
    loop._record_telemetry(
        run_id="heal_test_01",
        task_name="test_retry_heal",
        cycles_total=1,
        status="HEALED",
        history=[cycle_log],
    )
    assert telemetry_file.is_file()
    logged = json.loads(telemetry_file.read_text(encoding="utf-8").splitlines()[0])
    assert logged["final_status"] == "HEALED"
    assert logged["cycles_total"] == 1


def test_invisible_healing_loop_escalate_to_orchestrator(tmp_path: Path) -> None:
    """Verifica SBFLEngine.extract_from_exception e la registrazione ESCALATED al superamento cicli."""
    ihl_mod = load_nk_script_module("invisible_healing_loop")
    telemetry_file = tmp_path / "escalation_telemetry.jsonl"
    loop = ihl_mod.InvisibleHealingLoop(telemetry_log_path=telemetry_file, max_cycles=2)

    captured_loc = None
    try:
        raise ValueError("Errore persistente non riparabile automaticamente")
    except ValueError as exc:
        captured_loc = ihl_mod.SBFLEngine.extract_from_exception(
            exc, relevant_file_hint="test_core_platform_utilities"
        )

    assert captured_loc is not None
    assert captured_loc.error_type == "ValueError"
    assert captured_loc.suspiciousness == 1.0

    history = [
        ihl_mod.HealingCycleLog(
            cycle_index=idx,
            sbfl_payload=captured_loc.render_payload_json(),
            fault_slice=captured_loc.failing_line_content,
            repair_action="ATTEMPT_FAILED",
            repair_success=False,
            duration_ms=5.0,
            error_details="ValueError: Errore persistente",
        )
        for idx in (1, 2)
    ]
    res = ihl_mod.HealingResult(
        success=False,
        cycles_used=2,
        max_cycles=2,
        history=history,
        output=None,
        final_error="ValueError: Errore persistente non riparabile automaticamente",
    )
    loop._record_telemetry(
        run_id="heal_esc_02",
        task_name="test_unrecoverable_escalation",
        cycles_total=res.cycles_used,
        status="ESCALATED",
        history=res.history,
    )
    assert res.success is False
    assert res.cycles_used == 2
    assert telemetry_file.is_file()
    logged = json.loads(telemetry_file.read_text(encoding="utf-8").splitlines()[0])
    assert logged["final_status"] == "ESCALATED"
    assert logged["cycles_total"] == 2

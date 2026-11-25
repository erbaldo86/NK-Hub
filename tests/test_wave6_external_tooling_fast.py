# -*- coding: utf-8 -*-
"""Test di regressione Wave 6 per i 4 vincoli tooling esterni in NK_Hub."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from _internal.dast_sandbox_runner.holdout_verify import (
    _check_oracle_holdout_assets,
    _check_required_holdout_assets,
    _is_external_app_repo,
    verify_sandbox_holdouts,
)
from _internal.nk_common.oracle_lock import compute_combined_sha256, compute_lf_sha256
from _internal.nk_common.pytest_parallel import (
    _build_worker_command,
    detect_async_pytest_needed,
    resolve_coverage_source,
)
from _internal.nk_hook_gate.constants import _AUTH_SCRIPT_RE
from _internal.nk_hook_gate.shell_write_detector import _is_authorized_script_invocation
from _internal.preflight_health_check.ssot_governance import check_baseline_alignment
from _internal.rsi_convergence_engine.constants import RSIDefectVector
from _internal.rsi_convergence_engine.ecosystem_verify import (
    _compute_ecosystem_q_v2,
    _has_python_diff_signal,
)


def _mk_dirs(root: Path, *rels: str) -> Path:
    """Crea le sottodirectory specificate dentro root e restituisce root."""
    for rel in rels:
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def _run_bl(ws: Path, payload: dict) -> dict:
    """Scrive quality_baseline.json temporaneo ed esegue check_baseline_alignment."""
    bl = _mk_dirs(ws, "nk_tracking") / "nk_tracking" / "quality_baseline.json"
    bl.write_text(json.dumps(payload), encoding="utf-8")
    return check_baseline_alignment(SimpleNamespace(workspace_root=ws, baseline_file=bl, _get_expected_skills_count=lambda: 11))


@pytest.mark.fast
def test_w6_fix1_hook_gate_authorizes_builder_mutation_gate(tmp_path: Path) -> None:
    """Fix 1: builder_mutation_gate e autorizzato senza catena shell o script ignoti."""
    assert _AUTH_SCRIPT_RE.match("python -B -u NK_Hub/scripts/builder_mutation_gate.py --check")
    assert _AUTH_SCRIPT_RE.match("python -B -u .staging/scripts/builder_mutation_gate.py --check")
    assert _AUTH_SCRIPT_RE.match("python -B -u NK_Hub/scripts/unknown_gate.py --check") is None
    ws = _mk_dirs(tmp_path / "hub", "scripts", ".staging/scripts")
    assert _is_authorized_script_invocation("python -B -u scripts/builder_mutation_gate.py --check", project_root=ws) is True
    assert _is_authorized_script_invocation("python -B -u scripts/builder_mutation_gate.py --check && echo x", project_root=ws) is False


@pytest.mark.fast
def test_w6_fix2_resolve_coverage_source(tmp_path: Path) -> None:
    """Fix 2a: resolve_coverage_source seleziona src_app su app esterne e scripts su NK_Hub."""
    assert resolve_coverage_source(_mk_dirs(tmp_path / "ext", "src_app", "scripts")) == "src_app"
    assert resolve_coverage_source(_mk_dirs(tmp_path / "hub", "src_app", "scripts", ".agents/skills")) == "scripts"
    assert resolve_coverage_source(_mk_dirs(tmp_path / "app_only", "app")) == "app"
    assert resolve_coverage_source(_mk_dirs(tmp_path / "empty")) == "scripts"


@pytest.mark.fast
def test_w6_fix2_detect_async_pytest_needed(tmp_path: Path) -> None:
    """Fix 2b: detect_async_pytest_needed distingue repo sync da repo con pytest-asyncio/anyio."""
    sync_ws = _mk_dirs(tmp_path / "sync_repo", "tests")
    (sync_ws / "pytest.ini").write_text("[pytest]\naddopts = -q\n", encoding="utf-8")
    (sync_ws / "tests" / "test_sync.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    assert detect_async_pytest_needed(sync_ws, ["tests/test_sync.py", "tests/missing.py"]) is False
    (sync_ws / "pytest.ini").write_text("[pytest]\n" + "asyncio" + "_mode = strict\n", encoding="utf-8")
    assert detect_async_pytest_needed(sync_ws, ["tests/test_sync.py"]) is True
    pyproj_ws = _mk_dirs(tmp_path / "pyproj_repo", "tests")
    (pyproj_ws / "pyproject.toml").write_text('[tool.pytest]\nreq = "' + 'pytest_' + 'asyncio"\n', encoding="utf-8")
    assert detect_async_pytest_needed(pyproj_ws, []) is True
    mark_ws = _mk_dirs(tmp_path / "mark_repo", "tests")
    (mark_ws / "tests" / "test_async.py").write_text("import pytest\n@pytest.mark." + "asyncio\n" + "async " + "def " + "test_sample():\n    assert True\n", encoding="utf-8")
    assert detect_async_pytest_needed(mark_ws, ["tests/test_async.py"]) is True


@pytest.mark.fast
def test_w6_fix2_worker_command_flags(tmp_path: Path) -> None:
    """Fix 2c: _build_worker_command applica cov_source e plugin async dinamicamente."""
    cmd_sync = _build_worker_command(["tests/t.py"], tmp_path / "bt", tmp_path / "j.xml", [], True, {}, cov_source="scripts", disable_async_plugins=True)
    assert "no:anyio" in cmd_sync
    assert "no:asyncio" in cmd_sync
    assert "--cov=scripts" in cmd_sync
    cmd_ext = _build_worker_command(["tests/t.py"], tmp_path / "bt", tmp_path / "j.xml", [], True, {}, cov_source="src_app", disable_async_plugins=False)
    assert "no:anyio" not in cmd_ext
    assert "no:asyncio" not in cmd_ext
    assert "--cov=src_app" in cmd_ext
    cmd_nocov = _build_worker_command(["tests/t.py"], tmp_path / "bt", tmp_path / "j.xml", [], False, {})
    assert not any(a.startswith("--cov=") for a in cmd_nocov)


@pytest.mark.fast
def test_w6_fix3_external_rsi_q_v2(tmp_path: Path) -> None:
    """Fix 3a: Q_v2 restituisce STATIC_PASS su app esterne e UNMEASURED su NK_Hub senza mutation."""
    ext_ws = _mk_dirs(tmp_path / "ext_rsi", "src_app", "scripts")
    hub_ws = _mk_dirs(tmp_path / "hub_rsi", "scripts", ".agents/skills")
    defects = RSIDefectVector(tests_passed=10, tests_total=10)
    assert _has_python_diff_signal(ext_ws, "code_rsi", None) is False
    q_ext = _compute_ecosystem_q_v2(ext_ws, "code_rsi", defects, {}, [], [])
    assert q_ext["has_python_diff"] is False
    assert q_ext["certification_tier"] == "STATIC_PASS"
    assert q_ext["g_hard"] == 1
    (_mk_dirs(ext_ws, ".staging/src_app") / ".staging/src_app/mod.py").write_text("x = 1\n", encoding="utf-8")
    assert _has_python_diff_signal(ext_ws, "code_rsi", None) is True
    assert _has_python_diff_signal(hub_ws, "code_rsi", None) is True
    assert _compute_ecosystem_q_v2(hub_ws, "code_rsi", defects, {}, [], [])["certification_tier"] == "UNMEASURED"


@pytest.mark.fast
def test_w6_fix3_preflight_baseline_schemas(tmp_path: Path) -> None:
    """Fix 3b: check_baseline_alignment supporta schema flat, metrics e NK_Hub classico."""
    r_flat = _run_bl(_mk_dirs(tmp_path / "bl_flat", "src_app"), {"total_tests": 264, "failed_tests": 0, "pass_rate_pct": 100.0})
    assert r_flat["passed"] is True
    assert r_flat["external_app"] is True
    assert r_flat["tests_total"] == 264
    r_met = _run_bl(_mk_dirs(tmp_path / "bl_met", "src_app"), {"tests_total": 133, "metrics": {"unit_tests_pass_pct": {"value": 100.0}, "tests_total": {"value": 133}}})
    assert r_met["passed"] is True
    assert r_met["tests_total"] == 133
    assert _run_bl(_mk_dirs(tmp_path / "bl_fail", "src_app"), {"total_tests": 10, "failed_tests": 1, "pass_rate_pct": 90.0})["passed"] is False
    r_hub = _run_bl(tmp_path / "bl_hub_ok", {"_version": "1.0.0-Generation", "metrics": {"skills_audited": 11, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}})
    assert r_hub["passed"] is True
    assert "external_app" not in r_hub
    assert _run_bl(tmp_path / "bl_hub_bad", {"metrics": {"skills_audited": 10, "crv_macro_phases": 4, "unit_tests_pass_pct": 100.0}})["passed"] is False


@pytest.mark.fast
def test_w6_fix4_dast_holdout_external_app(tmp_path: Path) -> None:
    """Fix 4a: verify_sandbox_holdouts esenta asset Hub su app esterne ma valida oracle_lock."""
    root = _mk_dirs(tmp_path / "ext_root", "src_app", "tests", "nk_tracking")
    sb = _mk_dirs(tmp_path / "ext_sb", "src_app", "tests", "nk_tracking")
    (root / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (sb / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    f_map = {"test_app.py": compute_lf_sha256(root / "tests" / "test_app.py")}
    lock_json = json.dumps({"target": str(root / "tests"), "files": f_map, "combined_sha256": compute_combined_sha256(f_map)})
    (root / "nk_tracking" / "oracle_lock.json").write_text(lock_json, encoding="utf-8")
    (sb / "nk_tracking" / "oracle_lock.json").write_text(lock_json, encoding="utf-8")

    ok_res = verify_sandbox_holdouts(root, sb, "evaluator", [], [])
    assert ok_res["passed"] is True
    assert ok_res["verified_locked_count"] == 1
    assert ok_res["errors"] == []
    assert ok_res["mismatches"] == []

    (sb / "tests" / "test_app.py").write_text("def test_tampered():\n    assert False\n", encoding="utf-8")
    assert verify_sandbox_holdouts(root, sb, "evaluator", [], [])["passed"] is False


@pytest.mark.fast
def test_w6_fix4_dast_holdout_missing_lock_and_hub(tmp_path: Path) -> None:
    """Fix 4b: app esterna senza oracle_lock fallisce; Hub senza src_app richiede holdout."""
    root = _mk_dirs(tmp_path / "r2", "src_app", "tests", "nk_tracking")
    sb = _mk_dirs(tmp_path / "s2", "src_app", "tests", "nk_tracking")
    assert _is_external_app_repo(sb, root) is True
    miss_res = verify_sandbox_holdouts(root, sb, "evaluator", [], [])
    assert miss_res["passed"] is False
    assert any("oracle_lock.json" in e for e in miss_res["errors"])
    assert _is_external_app_repo(_mk_dirs(tmp_path / "hub_marked", "src_app", ".agents/skills")) is False
    empty_sb = _mk_dirs(tmp_path / "empty_sb")
    assert len(_check_required_holdout_assets(empty_sb)) >= 3
    assert _check_oracle_holdout_assets(_mk_dirs(tmp_path / "empty_root"), empty_sb)

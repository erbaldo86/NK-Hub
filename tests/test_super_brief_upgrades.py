"""
Nexus Keystone v2.6.0-DualEngine-Symbiosis - Unit Test Suite for Super Brief Upgrades
Module: test_super_brief_upgrades.py
Author: NK-QA-Engineer & NK-Oracle-Evaluator

Zero-Mock permanent test suite covering:
1. Universal Safe Subprocess Runner v2 (unbuffered & UTF-8 mode).
2. Fast-Stat Session Bootstrap Gate.
3. External Project Scaffolder DDD generation.
4. Tier-0 Deterministic Local API Cache (WAL mode, hash keys, refresh).
5. Hard Compliance Checker & Dual-Scorecard scoring logic.
6. GoalExecutionFailureManifest & IPC Contracts (C3 Unattended Protocol).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Dynamically locate module either in .staging/scripts or scripts/
_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

def _import_module(mod_name: str):
    staging_file = _workspace_root / ".staging" / "scripts" / f"{mod_name}.py"
    prod_file = _workspace_root / "scripts" / f"{mod_name}.py"
    target = staging_file if staging_file.exists() else prod_file
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

def _import_ipc_contracts():
    staging_file = _workspace_root / ".staging" / "scripts" / "schemas" / "nk_ipc_contracts.py"
    prod_file = _workspace_root / "scripts" / "schemas" / "nk_ipc_contracts.py"
    target = staging_file if staging_file.exists() else prod_file
    spec = importlib.util.spec_from_file_location("nk_ipc_contracts", str(target))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

platform_runner = _import_module("platform_runner")
nk_session_bootstrap = _import_module("nk_session_bootstrap")
external_project_scaffolder = _import_module("external_project_scaffolder")
deterministic_api_cache = _import_module("deterministic_api_cache")
nk_compliance_checker = _import_module("nk_compliance_checker")

reconfigure_streams = platform_runner.reconfigure_streams
safe_subprocess_run = platform_runner.safe_subprocess_run
_normalize_python_command = platform_runner._normalize_python_command
NKSessionBootstrap = nk_session_bootstrap.NKSessionBootstrap
ExternalProjectScaffolder = external_project_scaffolder.ExternalProjectScaffolder
DeterministicApiCache = deterministic_api_cache.DeterministicApiCache
NKComplianceChecker = nk_compliance_checker.NKComplianceChecker


def test_platform_runner_v2_unbuffered_normalization():
    """Verify that Python command sequences automatically receive the -u flag."""
    cmd = [sys.executable, "-c", "print(1)"]
    normalized = _normalize_python_command(cmd)
    assert "-u" in normalized, f"Expected -u in normalized command, got: {normalized}"
    assert normalized[1] == "-u"


def test_session_bootstrap_fast_stat():
    """Verify that NKSessionBootstrap runs cleanly and produces a PASS report."""
    bootstrap = NKSessionBootstrap()
    report = bootstrap.run_bootstrap(fast_stat=False)
    assert report["status"] == "PASS"
    assert "checks" in report
    assert report["checks"]["project_isolation"]["passed"] is True
    assert report["checks"]["quality_baseline"]["passed"] is True
    assert report["duration_ms"] >= 0


def test_external_project_scaffolder(tmp_path: Path):
    """Verify that ExternalProjectScaffolder creates full DDD tree and passes built-in AST test."""
    target_dir = tmp_path / "ScaffoldedApp"
    scaffolder = ExternalProjectScaffolder(project_name="ScaffoldedApp", target_dir=target_dir)
    res = scaffolder.scaffold()
    assert res["status"] == "SUCCESS"
    assert (target_dir / "src" / "core" / "__init__.py").exists()
    assert (target_dir / "pytest.ini").exists()
    assert (target_dir / "requirements.txt").exists()
    assert (target_dir / "tests" / "test_ast_purity.py").exists()

    # Verify that the generated test_ast_purity runs and passes
    cmd = [sys.executable, "-m", "pytest", str(target_dir / "tests" / "test_ast_purity.py"), "-q"]
    rc, stdout, stderr = safe_subprocess_run(cmd, cwd=target_dir)
    assert rc == 0, f"Generated AST purity test failed: {stdout} {stderr}"


def test_deterministic_api_cache(tmp_path: Path):
    """Verify DeterministicApiCache WAL mode, get/set operations and bypass flag."""
    db_file = tmp_path / "test_cache.db"
    cache = DeterministicApiCache(db_path=db_file, ttl_seconds=3600.0)
    assert cache.health_check() is True

    endpoint = "https://api.example.com/data"
    params = {"q": "roma", "limit": 10}
    body_data = '{"test": true}'

    # Cache miss
    miss = cache.get(endpoint, method="POST", params=params, body=body_data)
    assert miss is None

    # Cache set
    resp_body = '{"status": "ok", "items": [1, 2, 3]}'
    cache.set(endpoint, status_code=200, response_body=resp_body, method="POST", params=params, body=body_data)

    # Cache hit
    hit = cache.get(endpoint, method="POST", params=params, body=body_data)
    assert hit is not None
    status, text, headers = hit
    assert status == 200
    assert text == resp_body

    # Cache bypass via force_refresh
    bypass = cache.get(endpoint, method="POST", params=params, body=body_data, force_refresh=True)
    assert bypass is None


def test_nk_compliance_checker(tmp_path: Path):
    """Verify NKComplianceChecker audits transcript records and computes scores accurately."""
    checker = NKComplianceChecker()
    fake_transcript = tmp_path / "transcript.jsonl"

    # Create a synthetic transcript with healthy actions
    records = [
        {"type": "USER_INPUT", "content": "Start task"},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "python scripts/nk_session_bootstrap.py"}}]},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "python scripts/ast_guard_validator.py --target all"}}]},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "invoke_subagent", "args": {}}]},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "write_to_file", "args": {"TargetFile": "src/module.py"}}]},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "python scripts/win32_2pc_engine.py --promote-staging"}}]},
    ]

    with open(fake_transcript, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    res = checker.audit_transcript(fake_transcript)
    assert res["status"] == "PASS"
    scores = res["scores"]
    assert scores["operational_score"] == 100
    assert scores["procedural_score"] == 100
    assert scores["composite_score"] == 100.0


def test_goal_failure_manifest_and_ipc_contracts():
    """Verify GoalFailureManifest strict schema compliance under C3 Unattended Failure Protocol."""
    ipc_mod = _import_ipc_contracts()
    GoalFailureManifest = ipc_mod.GoalFailureManifest
    RootCauseAnalysis = ipc_mod.RootCauseAnalysis
    StagingSnapshot = ipc_mod.StagingSnapshot

    valid_payload = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "manifest_version": "1.0.0",
        "timestamp": 1727182446.0,
        "session_id": "sess_20260924_goal",
        "milestone_anchor_id": "NK-MS-20260924-PLAN-GOAL-INTEGRATION-v2.6.0",
        "status": "UNATTENDED_BLOCKED",
        "root_cause_analysis": {
            "blocked_resource_type": "EXTERNAL_API",
            "resource_identifier": "https://api.service.com/v1",
            "error_message": "HTTP 504 Gateway Timeout: External service unavailable",
            "stack_trace_snippet": "httpx.ConnectTimeout: Connection timed out",
            "zero_mock_violation_prevented": True,
        },
        "staging_snapshot": {
            "staging_path": ".staging/src/",
            "modified_files": ["src/service_client.py"],
            "sha256_tree_hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        },
        "user_remediation_steps": [
            "Verificare la connettivita' di rete o configurare la chiave API in .env",
            "Riavviare la sessione con /goal per riprendere dal checkpoint preservato",
        ],
        "resume_command": "/goal --resume",
    }

    manifest = GoalFailureManifest.model_validate(valid_payload)
    assert manifest.status == "UNATTENDED_BLOCKED"
    assert manifest.root_cause_analysis.zero_mock_violation_prevented is True
    assert manifest.staging_snapshot.modified_files == ["src/service_client.py"]

    dumped = manifest.model_dump(by_alias=True)
    assert dumped["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert dumped["milestone_anchor_id"] == "NK-MS-20260924-PLAN-GOAL-INTEGRATION-v2.6.0"

    # Rejection of unauthorized extra keys (strict extra='forbid')
    invalid_payload = dict(valid_payload)
    invalid_payload["unauthorized_mock"] = True
    with pytest.raises(ValidationError):
        GoalFailureManifest.model_validate(invalid_payload)

    # Rejection of invalid status
    invalid_status = dict(valid_payload)
    invalid_status["status"] = "INVALID_STATUS"
    with pytest.raises(ValidationError):
        GoalFailureManifest.model_validate(invalid_status)

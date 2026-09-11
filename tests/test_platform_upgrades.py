"""
Nexus Keystone v1.1.0-Universal - Unit Tests for Platform Upgrades
Module: test_platform_upgrades.py
Author: NK-Platform-Builder

Zero-mock test suite validating:
- env_capability_probe discovery, module auditing, and CLI execution.
- platform_runner safe subprocess execution and UTF-8 stream robustness.
- pytest.ini configuration invariants.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from scripts.env_capability_probe import (
    STANDARD_MODULES_TO_PROBE,
    THIRD_PARTY_MODULES_TO_PROBE,
    check_module_availability,
    probe_environment,
)
from scripts.platform_runner import reconfigure_streams, safe_subprocess_run


def test_env_capability_probe() -> None:
    """
    Verifica che probe_environment() rilevi correttamente Python 3,
    la presenza di sqlite3 e l'assenza di moduli fittizi.
    """
    probe_data = probe_environment()

    # 1. Structure validation
    assert isinstance(probe_data, dict), "Probe output must be a dictionary"
    assert "python" in probe_data
    assert "os" in probe_data
    assert "encoding" in probe_data
    assert "cpu" in probe_data
    assert "standard_modules" in probe_data
    assert "third_party_modules" in probe_data
    assert "summary" in probe_data

    # 2. Python 3 detection
    python_info = probe_data["python"]
    assert python_info["version_major"] == 3, f"Expected Python 3, got: {python_info['version_major']}"
    assert python_info["executable"] == sys.executable
    assert isinstance(python_info["is_64bit"], bool)

    # 3. Presence of sqlite3
    std_mods = probe_data["standard_modules"]
    assert "sqlite3" in std_mods, "sqlite3 must be present in standard_modules probe list"
    assert std_mods["sqlite3"]["available"] is True, "sqlite3 must be reported as available"

    # Verify check_module_availability directly for sqlite3
    sqlite_check = check_module_availability("sqlite3")
    assert sqlite_check["available"] is True
    assert sqlite_check["module"] == "sqlite3"

    # 4. Absence of fictitious modules
    fictitious_name = "fictitious_module_xyz_nonexistent_98765"
    fictitious_check = check_module_availability(fictitious_name)
    assert fictitious_check["available"] is False, "Fictitious module must not be available"
    assert fictitious_check["module"] == fictitious_name
    assert fictitious_name not in probe_data["standard_modules"]
    assert fictitious_name not in probe_data["third_party_modules"]

    # 5. OS and Encoding verification
    assert probe_data["os"]["system"] != ""
    assert probe_data["encoding"]["default_encoding"].lower().replace("-", "") in (
        "utf8",
        "utf_8",
        "ascii",
        "cp1252",
    )

    # 6. Summary metrics verification
    summary = probe_data["summary"]
    assert summary["total_probed"] == len(STANDARD_MODULES_TO_PROBE) + len(THIRD_PARTY_MODULES_TO_PROBE)
    assert summary["available_count"] >= 7  # All standard modules should be available


def test_platform_runner_safe_run() -> None:
    """
    Esegue un comando che stampa caratteri UTF-8 ed emoji senza sollevare UnicodeDecodeError.
    """
    reconfigure_streams()

    # 1. UTF-8 & Emoji output execution
    utf8_payload = "Nexus Keystone UTF-8 Test: 🚀 ✅ ⚡ — áéíóú €"
    cmd = [
        sys.executable,
        "-c",
        f"import sys; sys.stdout.write({utf8_payload!r} + '\\n'); sys.stdout.flush()",
    ]

    rc, stdout, stderr = safe_subprocess_run(cmd)
    assert rc == 0, f"Expected returncode 0, got {rc}. Stderr: {stderr}"
    assert "🚀" in stdout, "Emoji 🚀 must be present in captured stdout"
    assert "✅" in stdout, "Emoji ✅ must be present in captured stdout"
    assert "€" in stdout, "Euro symbol € must be present in captured stdout"
    assert "áéíóú" in stdout, "Accented characters must be preserved in stdout"
    assert stderr == "", f"Stderr should be empty, got: {stderr}"

    # 2. Timeout handling test
    sleep_cmd = [
        sys.executable,
        "-c",
        "import time; time.sleep(10)",
    ]
    rc_timeout, stdout_timeout, stderr_timeout = safe_subprocess_run(sleep_cmd, timeout=0.5)
    assert rc_timeout == -1, f"Expected returncode -1 on timeout, got {rc_timeout}"
    assert "timed out" in stderr_timeout.lower(), "Timeout error message expected in stderr"

    # 3. Invalid command handling test
    invalid_cmd = ["non_existent_binary_nk_987654321"]
    rc_inv, stdout_inv, stderr_inv = safe_subprocess_run(invalid_cmd)
    assert rc_inv != 0, "Invalid command must return non-zero exit code"
    assert stdout_inv == ""


def test_pytest_ini_content() -> None:
    """
    Verifica che pytest.ini contenga testpaths e norecursedirs.
    """
    workspace_root = Path(__file__).resolve().parent.parent
    pytest_ini_path = workspace_root / "pytest.ini"

    # If test is run before promotion or in staging, check root or staging
    if not pytest_ini_path.exists():
        staging_ini = workspace_root / ".staging" / "pytest.ini"
        if staging_ini.exists():
            pytest_ini_path = staging_ini

    assert pytest_ini_path.exists(), f"pytest.ini must exist: {pytest_ini_path}"

    content = pytest_ini_path.read_text(encoding="utf-8")

    # Invariant checks
    assert "[pytest]" in content, "pytest.ini must contain [pytest] section header"
    assert "testpaths" in content, "pytest.ini must contain 'testpaths'"
    assert "tests" in content, "pytest.ini must configure 'tests' in testpaths"
    assert "norecursedirs" in content, "pytest.ini must contain 'norecursedirs'"
    assert ".staging" in content, "pytest.ini must exclude '.staging' in norecursedirs"
    assert "filterwarnings" in content, "pytest.ini must configure 'filterwarnings'"


def test_platform_cli_integration(tmp_path: Path) -> None:
    """
    Test CLI integration for both scripts: env_capability_probe and platform_runner.
    """
    workspace_root = Path(__file__).resolve().parent.parent

    probe_script = workspace_root / "scripts" / "env_capability_probe.py"
    if not probe_script.exists():
        probe_script = workspace_root / ".staging" / "scripts" / "env_capability_probe.py"

    # 1. Test env_capability_probe CLI with --json
    rc, stdout, stderr = safe_subprocess_run([sys.executable, str(probe_script), "--json"])
    assert rc == 0, f"env_capability_probe CLI failed: {stderr}"
    data = json.loads(stdout)
    assert data["python"]["version_major"] == 3

    # 2. Test env_capability_probe CLI with --export
    export_target = tmp_path / "probe_export.json"
    rc_exp, stdout_exp, stderr_exp = safe_subprocess_run(
        [sys.executable, str(probe_script), "--export", str(export_target)]
    )
    assert rc_exp == 0, f"Export CLI failed: {stderr_exp}"
    assert export_target.exists(), "Export file should have been created"
    exported_data = json.loads(export_target.read_text(encoding="utf-8"))
    assert exported_data["summary"]["total_probed"] > 0

    # 3. Test platform_runner CLI with --cmd
    runner_script = workspace_root / "scripts" / "platform_runner.py"
    if not runner_script.exists():
        runner_script = workspace_root / ".staging" / "scripts" / "platform_runner.py"

    cli_cmd = f'{sys.executable} -c "print(\'CLI_RUNNER_SUCCESS_🚀\')"'
    rc_runner, stdout_runner, stderr_runner = safe_subprocess_run(
        [sys.executable, str(runner_script), "--cmd", cli_cmd]
    )
    assert rc_runner == 0, f"platform_runner CLI failed: {stderr_runner}"
    assert "CLI_RUNNER_SUCCESS_🚀" in stdout_runner

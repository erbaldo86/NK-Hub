# -*- coding: utf-8 -*-
"""
Test Zero-Mock per isolamento Pytest su NVMe, PIDFileLock timeout e guardia hook Drive FS.
Modulo: tests/test_isolated_pytest_runner.py.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

try:
    from conftest import (
        WORKSPACE_ROOT,
        call_script_main_captured,
        load_nk_script_module,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        WORKSPACE_ROOT,
        call_script_main_captured,
        load_nk_script_module,
        load_script_by_relpath,
    )

iso_mod = load_script_by_relpath("isolated_test_runner", "scripts/_internal/nk_common/isolated_test_runner.py")
lio_mod = load_script_by_relpath("ledger_lock_io", "scripts/_internal/nk_common/ledger_lock_io.py")
pr_mod = load_nk_script_module("platform_runner")
hook_mod = load_nk_script_module("nk_hook_gate")
load_nk_script_module("nk_registry_indexer")
load_nk_script_module("vibe_sprint_router")
from _internal.nk_common import pytest_parallel as pp_mod, tas_ssot_io as tas_io_mod  # noqa: E402
from _internal.nk_hook_gate import target_classifier as tc_mod  # noqa: E402
from _internal.nk_registry_indexer import shards_rehydrate as sh_mod  # noqa: E402
from _internal.vibe_sprint_router import domain_matcher as dm_mod  # noqa: E402


def _build_mini_hub_ws(root: Path) -> Path:
    """Crea un mini workspace Hub con produzione, .staging e tombstone."""
    ws = root / "MiniHub"
    for sub in ("scripts", "tests/old_dir", ".agents", "nk_tracking/sessions", "nk_tracking/handoff", ".staging/tests", ".git"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (ws / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (ws / "README.md").write_text("# MiniHub\n", encoding="utf-8")
    (ws / ".coverage.stale").write_text("x", encoding="utf-8")
    (ws / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (ws / "scripts" / "calc.py").write_text("def inc(x: int) -> int:\n    return x + 1 if x >= 0 else 0\n", encoding="utf-8")
    (ws / "tests" / "test_old.py").write_text("def test_old():\n    assert 1 == 2\n", encoding="utf-8")
    (ws / "tests" / "old_dir" / "test_sub.py").write_text("def test_sub():\n    assert 2 == 3\n", encoding="utf-8")
    (ws / "tests" / "test_keep.py").write_text("from scripts.calc import inc\n\ndef test_keep():\n    assert inc(1) == 2 and inc(-1) == 0\n", encoding="utf-8")
    (ws / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    (ws / ".staging" / "tests" / "test_staged.py").write_text("def test_staged():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["tests/test_old.py", "tests/old_dir"]}), encoding="utf-8")
    (ws / "nk_tracking" / "sessions" / "skip.json").write_text("{}", encoding="utf-8")
    (ws / "nk_tracking" / "handoff" / "skip_h.json").write_text("{}", encoding="utf-8")
    (ws / ".git" / "HEAD").write_text("ref: main\n", encoding="utf-8")
    return ws


def _assert_mirror_dirs_and_exclusions(mirror_no_ov: Path) -> None:
    """Verifica _MIRROR_DIRS ed esclusioni non-NK senza aumentare la CC del test."""
    assert {"scripts", "tests", ".agents", "nk_genome", "deploy", "static", "templates", "frontend", "migrations"}.issubset(set(iso_mod._MIRROR_DIRS))
    assert mirror_no_ov.name == "MiniHub" and (mirror_no_ov / "pytest.ini").is_file()
    assert (mirror_no_ov / "README.md").is_file() and not (mirror_no_ov / ".coverage.stale").exists()
    assert not (mirror_no_ov / ".env").exists()
    assert (mirror_no_ov / ".staging" / "tests" / "test_staged.py").is_file()
    assert not (mirror_no_ov / ".git").exists() and not (mirror_no_ov / "nk_tracking" / "sessions").exists()


def _assert_missing_bin_and_kill_tree() -> None:
    """Verifica codice 127 su binario assente e tree-kill reale."""
    assert (pr_mod.safe_subprocess_run("nonexistent_nk_bin_xyz")[0], iso_mod._kill_detached_tree(999999)) == (127, None)


@pytest.mark.integration
def test_run_detached_pytest_and_platform_runner_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica run_detached_pytest, --pytest-isolated CLI, binary missing 127 e tree-kill reali."""
    _assert_missing_bin_and_kill_tree()
    ws = _build_mini_hub_ws(tmp_path)
    cli_tmp = tmp_path / "cli_tmp"
    cli_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TEMP", str(cli_tmp))
    monkeypatch.setenv("TMP", str(cli_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(cli_tmp))

    rc_help, out_help, _ = call_script_main_captured(pr_mod, ["--help"])
    assert rc_help == 0 and "--pytest-isolated" in out_help

    rc_ok, out_ok, _ = call_script_main_captured(
        pr_mod,
        [
            "--pytest-isolated",
            "--workspace-root",
            str(ws),
            "--targets",
            "tests/test_keep.py",
            "tests/test_staged.py",
            "--overlay-staging",
            "--pytest-args",
            "--import-mode=prepend -q",
            "--json",
        ],
    )
    res_ok = json.loads(out_ok)
    assert rc_ok == 0 and res_ok["success"] is True and res_ok["exit_code"] == 0 and res_ok["passed"] == 2
    assert res_ok["mirror_cleaned"] is True and (cli_tmp / "nk_diagnostics" / "pytest_iso_last.json").is_file()

    (ws / ".staging" / "tests" / "test_hang.py").write_text("import time\n\ndef test_hang():\n    time.sleep(1.5)\n", encoding="utf-8")
    res_to = iso_mod.run_detached_pytest(
        workspace_root=ws,
        targets=("tests/test_hang.py",),
        timeout_sec=0.3,
        log_dir=cli_tmp / "diag",
    )
    assert res_to["timed_out"] is True and res_to["success"] is False and res_to["status"] == "TIMEOUT" and res_to["mirror_cleaned"] is True


def _assert_hook_gate_win32_rules(tmp_path: Path) -> None:
    """Verifica blocco pytest su Drive FS vs esenzione runner isolati e %TEMP%."""
    temp_tok = "%" + "TEMP%"
    drive_ws = Path("G:/Il mio Drive/Antigravity/NK_Hub")
    for blocked_cmd in (
        "pytest tests/test_platform_locks_and_utils.py",
        "python -m pytest -q",
        'python -m pytest "g:/Il mio Drive/Antigravity/NK_Hub/tests/test_a.py"',
        'python scripts/platform_runner.py --cmd "pytest tests/"',
        'python scripts/platform_runner.py --cmd="pytest -q"',
        "python -m pytest --basetemp=" + temp_tok + "/bt tests/test_a.py",
    ):
        res = hook_mod._handle_write_gate(
            {"toolName": "run_command", "toolInput": {"CommandLine": blocked_cmd}}, drive_ws, False, "", "", "",
        )
        assert (res.get("decision"), "[RULE-WIN32-ISOLATED-PYTEST]" in res.get("reason", "")) == ("deny", True), blocked_cmd

    res_in_tmp_cloud = hook_mod._handle_write_gate(
        {"toolName": "run_command", "toolInput": {"CommandLine": 'python -m pytest "Google Drive/NK_Hub/tests"'}}, tmp_path, False, "", "", "",
    )
    assert res_in_tmp_cloud.get("decision") == "deny"

    for allowed_cmd in (
        "python -B -u .staging/scripts/platform_runner.py --pytest-isolated --targets tests/test_a.py",
        "python -B -u scripts/dast_sandbox_runner.py --overlay-staging .",
        "python -B -u scripts/quality_baseline_manager.py --live",
        "python -B -u scripts/rsi_convergence_engine.py --verify",
        "python -B -u scripts/sbfl_pytest_bridge.py --help",
        f"python -B -u -m pytest {temp_tok}/nk_pytest_iso_123/NK_Hub/tests/test_a.py",
        'Select-String -Path scripts/*.py -Pattern "pytest"',
        'rg "pytest" scripts/',
    ):
        assert hook_mod._handle_write_gate(
            {"toolName": "run_command", "toolInput": {"CommandLine": allowed_cmd}}, drive_ws, False, "", "", "",
        ) == {}, allowed_cmd

    assert (WORKSPACE_ROOT / ".staging" / ".agents" / "rules" / "anti_crash_rules.md").is_file() or (WORKSPACE_ROOT / ".agents" / "rules" / "anti_crash_rules.md").is_file()
    assert (WORKSPACE_ROOT / ".staging" / ".agents" / "plugins" / "nk-gate" / "rules" / "AGENTS.md").is_file() or (WORKSPACE_ROOT / ".agents" / "plugins" / "nk-gate" / "rules" / "AGENTS.md").is_file()


def _assert_target_classifier_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre _is_temp_root_path, _segment_targets_temp_isolated e TEMP proj_is_temp."""
    temp_low = ("%" + "temp%").lower()
    assert tc_mod._classify_isolated_pytest_violation("pytest tests/test_a.py", "pytest tests/test_a.py", tmp_path) is None
    assert tc_mod._segment_targets_temp_isolated(f"python -m pytest --rootdir={temp_low}/nk_pytest_iso_1 {temp_low}/nk_pytest_iso_1/tests/test_a.py", "/tmp") is True
    assert tc_mod._segment_targets_temp_isolated(f"python -m pytest --rootdir=g:/bad {temp_low}/nk_pytest_iso_1/tests/test_a.py", "/tmp") is False
    assert tc_mod._segment_targets_temp_isolated("python -m pytest -k tests/foo -o junit=x --basetemp /tmp/bt --cov scripts basetemp=/tmp/bt /tmp/tests/test_a.py", "/tmp") is True
    assert (tc_mod._segment_targets_temp_isolated("python -m pytest tests/test_a.py", "/tmp"), tc_mod._segment_targets_temp_isolated("python -m pytest -q", "/tmp")) == (False, False)
    custom_td = tmp_path / "tc_td"
    custom_td.mkdir()
    with monkeypatch.context() as mp:
        for k in ("TEMP", "TMP", "LOCALAPPDATA"):
            mp.setenv(k, "")
        mp.setenv("TMPDIR", str(custom_td))
        assert (tc_mod._is_temp_root_path(custom_td / "sub"), tc_mod._is_temp_root_path(Path("C:/outside_non_temp_proj"))) == (True, False)


@pytest.mark.integration
def test_hook_gate_rule_win32_isolated_pytest_and_classifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica blocco pytest su Drive FS, esenzione runner isolati e classifier edges."""
    _assert_hook_gate_win32_rules(tmp_path)
    _assert_target_classifier_edges(tmp_path, monkeypatch)


def _assert_detached_flags_and_mirror(tmp_path: Path) -> None:
    """Verifica costanti detached Win32, _MIRROR_DIRS e mirror_workspace_to_nvme."""
    expected_flags = (0x00000200 | 0x08000000) if sys.platform == "win32" else 0
    assert (iso_mod.WIN32_CREATE_NEW_PROCESS_GROUP, iso_mod.WIN32_CREATE_NO_WINDOW, iso_mod.WIN32_DETACHED_FLAGS, iso_mod.win32_detached_flags(0x4)) == (0x00000200, 0x08000000, expected_flags, (expected_flags | 0x4) if sys.platform == "win32" else 0)
    ws_m = _build_mini_hub_ws(tmp_path / "ov_ws")
    mirror_no_ov = iso_mod.mirror_workspace_to_nvme(ws_m, apply_overlay=False)
    try:
        _assert_mirror_dirs_and_exclusions(mirror_no_ov)
    finally:
        assert iso_mod.safe_rmtree(mirror_no_ov.parent) is True
    mirror_no_stg = iso_mod.mirror_workspace_to_nvme(ws_m, staging_dir=tmp_path / "missing_stg")
    try:
        assert not (mirror_no_stg / ".staging").exists()
    finally:
        assert iso_mod.safe_rmtree(mirror_no_stg.parent) is True


@pytest.mark.fast
def test_isolated_runner_unit_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre costanti detached, mirror overlay, is_temp_workspace, safe_rmtree, tombstone e metriche."""
    _assert_detached_flags_and_mirror(tmp_path)
    assert iso_mod.is_temp_workspace(tmp_path) is True and iso_mod.is_temp_workspace(Path("C:/outside_non_temp_nk_ws")) is False
    custom_td = tmp_path / "custom_td"
    custom_td.mkdir()
    with monkeypatch.context() as mp:
        mp.setenv("TMPDIR", str(custom_td))
        assert iso_mod.is_temp_workspace(custom_td / "sub") is True
        mp.setattr(iso_mod.sys, "platform", "linux")
        assert iso_mod.win32_detached_flags(0x4) == 0

    assert iso_mod.safe_rmtree(tmp_path / "missing_rm_dir") is True
    ro_dir = tmp_path / "ro_dir"
    ro_dir.mkdir()
    ro_file = ro_dir / "ro.txt"
    ro_file.write_text("ro", encoding="utf-8")
    os.chmod(ro_file, stat.S_IREAD)
    assert iso_mod.safe_rmtree(ro_dir) is True

    busy_dir = tmp_path / "busy_dir"
    busy_dir.mkdir()
    with monkeypatch.context() as mp:
        mp.setattr(iso_mod.shutil, "rmtree", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("busy")))
        mp.setattr(iso_mod.time, "sleep", lambda _s: None)
        assert iso_mod.safe_rmtree(busy_dir) is False

    stg_d = tmp_path / "stg_del"
    stg_d.mkdir()
    assert iso_mod._load_deleted_set(stg_d) == set()
    for raw, exp in (('["tests/a.py", ""]', {"tests/a.py"}), ("{bad", set()), ("123", set())):
        (stg_d / ".deleted_files.json").write_text(raw, encoding="utf-8")
        assert iso_mod._load_deleted_set(stg_d) == exp

    ws_ref = tmp_path / "MiniHub"
    assert iso_mod._resolve_mirror_targets(ws_ref, ws_ref, ()) == ["tests"]
    assert iso_mod._resolve_mirror_targets(ws_ref, ws_ref, ("", "   ")) == ["tests"]
    assert iso_mod._resolve_mirror_targets(ws_ref, ws_ref, (f"{ws_ref.as_posix()}/tests/test_keep.py", "MiniHub/tests/test_x.py", "./.staging/tests/test_s.py", "./.staging/scripts/x.py")) == ["tests/test_keep.py", "tests/test_x.py", "tests/test_s.py", ".staging/scripts/x.py"]
    assert iso_mod._resolve_mirror_targets(Path("/tmp/MiniHub"), Path("/tmp/MiniHub"), ("./", "/tmp/MiniHub/tests/test_pos.py")) == ["tests/test_pos.py"]

    assert iso_mod._extract_pytest_metrics("", None)["passed"] == 0
    cnt = iso_mod._extract_pytest_metrics("3 passed, 1 failed, 1 error, 2 skipped, 1 xfailed", None)
    assert (cnt["passed"], cnt["failed"], cnt["errors"], cnt["skipped"], cnt["xfailed"]) == (3, 1, 1, 2, 1)

    cov_p = tmp_path / "cov.json"
    cov_p.write_text(json.dumps({"totals": {"num_statements": 10, "covered_lines": 8, "num_branches": 4, "covered_branches": 3}}), encoding="utf-8")
    m_fb = iso_mod._extract_pytest_metrics("1 passed", cov_p)["coverage"]
    assert m_fb["statement_coverage_pct"] == 80.0 and m_fb["true_branch_coverage_pct"] == 75.0
    cov_p.write_text(json.dumps({"totals": {"num_statements": 0, "num_branches": 0}}), encoding="utf-8")
    assert iso_mod._extract_pytest_metrics("1 passed", cov_p)["coverage"]["true_branch_coverage_pct"] == 0.0
    cov_p.write_text("{bad", encoding="utf-8")
    assert "coverage" not in iso_mod._extract_pytest_metrics("1 passed", cov_p)
    iso_mod._kill_detached_tree(0)
    monkeypatch.setattr(iso_mod.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=1))
    iso_mod._kill_detached_tree(999999)


def _check_runner_cli_formatting(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica rami CLI --pytest-isolated (text/json/fail/error) e --cmd senza spawn reali."""
    import _internal.nk_common.isolated_test_runner as itr_pkg

    seen_calls: List[dict] = []

    def _stub_detached(**kw: object) -> dict:
        seen_calls.append(dict(kw))
        tgts = kw.get("targets", ())
        is_fail = any("nonexistent" in str(t) for t in tgts)
        return {
            "status": "FAIL" if is_fail else "PASS",
            "success": not is_fail,
            "exit_code": 1 if is_fail else 0,
            "passed": 0 if is_fail else 1,
            "failed": 0,
            "errors": 1 if is_fail else 0,
            "skipped": 0,
            "duration_s": 0.01,
            "log_file": str(ws / "iso.log"),
            "tail": "missing target" if is_fail else "",
        }

    with monkeypatch.context() as mp:
        mp.setattr(itr_pkg, "run_detached_pytest", _stub_detached)
        mp.setattr(iso_mod, "run_detached_pytest", _stub_detached)
        rc_j, out_j, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/test_keep.py", "--overlay-staging", "--json"])
        assert rc_j == 0 and json.loads(out_j)["passed"] == 1
        rc_t, out_t, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/test_keep.py", "--pytest-args", "-v --tb=short"])
        assert rc_t == 0 and "[NK-PYTEST-ISO] status=PASS" in out_t and seen_calls[-1]["extra_args"] == ("-v", "--tb=short")
        rc_m, out_m, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/nonexistent_tgt.py", "--timeout", "15"])
        assert rc_m == 1 and "[NK-PYTEST-ISO] status=FAIL" in out_m and "missing target" in out_m


@pytest.mark.fast
def test_platform_runner_isolated_cli_and_tokenizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Copre CLI --pytest-isolated (text/json/--pytest-args/error), tokenizer e subprocess senza spawn extra."""
    assert isolated_nk_env.is_dir()
    ws = _build_mini_hub_ws(tmp_path)
    assert call_script_main_captured(pr_mod, [])[0] == 2
    _check_runner_cli_formatting(ws, monkeypatch)

    assert pr_mod._normalize_python_command([sys.executable, "-B", "a.py"]) == [sys.executable, "-u", "-B", "a.py"]
    assert pr_mod._normalize_python_command([sys.executable, "-u", "a.py"]) == [sys.executable, "-u", "a.py"]
    assert pr_mod._normalize_python_command(f'"{sys.executable}" -B a.py') == f'"{sys.executable}" -u -B a.py'
    assert pr_mod._normalize_python_command(f'"{sys.executable}" -u a.py') == f'"{sys.executable}" -u a.py'
    assert pr_mod._tokenize_command_no_shell(r'''echo "a\"b" 'c' ''') == ["echo", 'a"b', "c"] and pr_mod._tokenize_command_no_shell("   ") == []
    for bad_cmd in ("echo \x00", "echo $(bad)", "echo a&b"):
        with pytest.raises(ValueError):
            pr_mod._tokenize_command_no_shell(bad_cmd)
    for bad_argv in ("", ["py\n", "a"], ["python", "x\x00y"]):
        with pytest.raises(ValueError):
            pr_mod._prepare_argv_no_shell(bad_argv, {})
    assert pr_mod._decode_stream_output(b"ok") == "ok" and pr_mod._decode_stream_output(None) == ""

    with monkeypatch.context() as mp:
        mp.setattr(pr_mod.sys, "platform", "linux")
        assert pr_mod._win32_detached_flags() == 0
        seen_shell: List[object] = []
        mp.setattr(
            subprocess,
            "Popen",
            lambda tgt, **_kw: (
                seen_shell.append(tgt)
                or SimpleNamespace(returncode=0, pid=0, communicate=lambda timeout=None: ("posix ok\n", "e\n"))
            ),
        )
        rc_px, out_px, err_px = pr_mod.safe_subprocess_run(["echo", "posix sh"], env={"NK_SUB_TEST": "1"}, use_shell=True)
        assert rc_px == 0 and out_px == "posix ok\n" and err_px == "e\n" and seen_shell == ["echo 'posix sh'"]
        rc_cmd, out_cmd, err_cmd = call_script_main_captured(pr_mod, ["--cmd", "echo hello"])
        assert rc_cmd == 0 and "posix ok" in out_cmd and "e\n" in err_cmd


def _assert_bounded_lock_timeout(tmp_path: Path) -> None:
    """Verifica che PIDFileLock(..., acquire_timeout_sec=0.1) fallisca rapidamente."""
    busy_p = tmp_path / "bounded.lock"
    busy_p.write_text(json.dumps({"pid": os.getpid(), "nonce": "busy", "timestamp": time.time()}), encoding="utf-8")
    t0 = time.perf_counter()
    with pytest.raises(TimeoutError):
        with lio_mod.PIDFileLock(busy_p, stale_timeout_sec=10.0, acquire_timeout_sec=0.1):
            pytest.fail("TimeoutError expected")
    assert (time.perf_counter() - t0) < 1.5


@pytest.mark.fast
def test_ledger_lock_shards_and_domain_matcher_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre edge di ledger_lock_io (incluso bounded acquire timeout), shards_rehydrate e domain_matcher."""
    _assert_bounded_lock_timeout(tmp_path)
    assert lio_mod.PIDFileLock._is_pid_alive(0) is False
    corrupt_p = tmp_path / "corrupt.lock"
    corrupt_p.write_text("{bad", encoding="utf-8")
    assert lio_mod.PIDFileLock(corrupt_p, stale_timeout_sec=10.0).acquire(timeout_sec=0.0) is False
    perm_err = PermissionError("non-retryable")
    perm_err.winerror = 999
    with monkeypatch.context() as mp:
        mp.setattr(lio_mod.os, "open", lambda *_a, **_kw: (_ for _ in ()).throw(perm_err))
        with pytest.raises(PermissionError):
            lio_mod.PIDFileLock(tmp_path / "p.lock").acquire(timeout_sec=0.0)

    lk_rel = lio_mod.PIDFileLock(tmp_path / "rel.lock")
    assert lk_rel.acquire(timeout_sec=0.0) is True
    (tmp_path / "rel.lock").write_text(json.dumps({"pid": os.getpid(), "nonce": "other"}), encoding="utf-8")
    lk_rel.release()
    assert (tmp_path / "rel.lock").exists()
    for content, delete_it in (("{corrupt", False), ("{}", True)):
        lk_rel.acquired = True
        if delete_it:
            (tmp_path / "rel.lock").unlink(missing_ok=True)
        else:
            (tmp_path / "rel.lock").write_text(content, encoding="utf-8")
        lk_rel.release()

    ws = tmp_path / "ws_sh_dm"
    (ws / ".staging" / "nk_genome").mkdir(parents=True)
    (ws / "nk_genome" / "shards").mkdir(parents=True)
    man_stg = ws / ".staging" / "nk_genome" / "nk_registry_manifest.json"
    (ws / "nk_genome" / "shards" / "DOM-00.json").write_text(json.dumps({"global_hygiene_profile": {"ok": True}, "docs_and_setup_index": {"README.md": {"sha": "a"}}, "milestone_anchor_id": "M1"}), encoding="utf-8")
    (ws / "nk_genome" / "shards" / "DOM-06.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
    (ws / "nk_genome" / "shards" / "DOM-01.json").write_text(json.dumps({
        "domain": {"domain_id": "DOM-01", "name": "GOV", "primary_skill": "NK-Orchestrator", "keywords": ["gov"]},
        "skills_index": {"NK-Orchestrator": {"sector": "GOV"}}, "scripts_index": {"s.py": {}},
        "native_agents_index": {"NK-Specifier-Agent": {}},
        "intent_dispatch_table": {"_routes": [["NK-Orchestrator", "mode_b", ["route_kw"]]], "str_kw": "mode_c", "dict_kw": {"domain_id": "DOM-01", "recommended_mode": "mode_a"}},
    }), encoding="utf-8")
    (ws / "nk_genome" / "shards" / "DOM-02.json").write_text("{bad", encoding="utf-8")
    (ws / "nk_genome" / "shards" / "DOM-03.json").write_text("[]", encoding="utf-8")
    slim = {"domains": {"DOM-09": {"name": "KEEP"}}, "shards": {"DOM-00": "shards/DOM-00.json", "DOM-01": "shards/DOM-01.json", "DOM-02": "shards/DOM-02.json", "DOM-03": "shards/DOM-03.json", "DOM-04": "shards/missing.json", "DOM-06": "shards/DOM-06.json"}}
    man_stg.write_text(json.dumps(slim), encoding="utf-8")
    rehyd = sh_mod.rehydrate_manifest_from_shards(man_stg, slim)
    assert rehyd["milestone_anchor_id"] == "M1" and rehyd["release_meta"]["version"] == "1.0.0" and "route_kw" in rehyd["intent_dispatch_table"]

    router_stub = SimpleNamespace(staging_dir=ws / ".staging", workspace_root=ws, DISCOVERY_KEYWORDS=("scoperta",))
    router_stub._load_registry_manifest = lambda: dm_mod.load_registry_manifest_impl(router_stub)
    with monkeypatch.context() as mp:
        mp.setattr(dm_mod, "_ROUTER_MANIFEST_CACHE", {})
        loaded_1 = dm_mod.load_registry_manifest_impl(router_stub)
        loaded_2 = dm_mod.load_registry_manifest_impl(router_stub)
        assert loaded_1 is loaded_2 and "route_kw" in loaded_1["intent_dispatch_table"]
        assert dm_mod.resolve_domain_from_manifest_impl(router_stub, "route_kw")["domain_id"] == "DOM-01"
        assert dm_mod.resolve_domain_from_manifest_impl(router_stub, "scoperta")["domain_id"] == "DOM-02"
        assert dm_mod.resolve_domain_from_manifest_impl(router_stub, "audit forense s.py")["domain_id"] == "DOM-04"


@pytest.mark.integration
def test_isolated_runner_mirrors_web_deploy_dirs_and_external_siblings(tmp_path: Path) -> None:
    """Verifica replica directory web/deploy, mirror sorelle e isolamento overlay_siblings."""
    ext_root = tmp_path / "NK_External_Projects"
    app_main = ext_root / "AppMain"
    for rel_f in ("deploy/docker-compose.yml", "static/app.css", "templates/index.html", "frontend/main.ts", "migrations/001_init.sql", "scripts/main.py"):
        fp = app_main / rel_f
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("# asset\n", encoding="utf-8")
    (app_main / ".staging" / "scripts").mkdir(parents=True)
    (app_main / ".staging" / "scripts" / "main.py").write_text("# staged\n", encoding="utf-8")
    ignored_nm = app_main / "frontend" / "node_modules" / "pkg.js"
    ignored_nm.parent.mkdir(parents=True, exist_ok=True)
    ignored_nm.write_text("// ignore\n", encoding="utf-8")

    sib_api = ext_root / "SiblingApi"
    (sib_api / "scripts").mkdir(parents=True)
    (sib_api / "deploy").mkdir(parents=True)
    (sib_api / ".staging" / "scripts").mkdir(parents=True)
    (sib_api / "scripts" / "api.py").write_text("VER = 1\n", encoding="utf-8")
    (sib_api / "deploy" / "k8s.yaml").write_text("kind: Deployment\n", encoding="utf-8")
    (sib_api / ".staging" / "scripts" / "api.py").write_text("VER = 2\n", encoding="utf-8")
    (sib_api / "README.md").write_text("# SiblingApi\n", encoding="utf-8")
    (sib_api / ".env").write_text("SECRET=1\n", encoding="utf-8")
    hidden_sib = ext_root / ".hidden_meta" / "scripts"
    hidden_sib.mkdir(parents=True)
    (hidden_sib / "skip.py").write_text("X = 0\n", encoding="utf-8")

    m_dir = iso_mod.mirror_workspace_to_nvme(app_main, apply_overlay=True, mirror_siblings=True)
    try:
        assert all((m_dir / d).is_file() for d in ("deploy/docker-compose.yml", "static/app.css", "templates/index.html", "frontend/main.ts", "migrations/001_init.sql"))
        assert (m_dir / "scripts" / "main.py").read_text(encoding="utf-8") == "# staged\n"
        assert not (m_dir / "frontend" / "node_modules").exists() and not (m_dir.parent / ".hidden_meta").exists()
        sib_m = m_dir.parent / "SiblingApi"
        assert (sib_m / "deploy" / "k8s.yaml").is_file() and (sib_m / "README.md").is_file()
        assert (sib_m / "scripts" / "api.py").read_text(encoding="utf-8") == "VER = 1\n" and not (sib_m / ".env").exists()
    finally:
        iso_mod.safe_rmtree(m_dir.parent)

    m_ov_sib = iso_mod.mirror_workspace_to_nvme(app_main, apply_overlay=True, mirror_siblings=True, overlay_siblings=True)
    try:
        assert (m_ov_sib.parent / "SiblingApi" / "scripts" / "api.py").read_text(encoding="utf-8") == "VER = 2\n"
    finally:
        iso_mod.safe_rmtree(m_ov_sib.parent)

    m_no_sib = iso_mod.mirror_workspace_to_nvme(app_main, apply_overlay=True, mirror_siblings=False)
    try:
        assert not (m_no_sib.parent / "SiblingApi").exists()
    finally:
        iso_mod.safe_rmtree(m_no_sib.parent)


def _assert_tombstone_and_local_dir_guards(tmp_path: Path) -> None:
    """Verifica _is_safe_local_dir e blocco tombstone rel_del='.' su mirror_dir."""
    parent = tmp_path / "ext_root"
    child, outside, file_entry = parent / "app_a", tmp_path / "outside", parent / "readme.txt"
    child.mkdir(parents=True)
    outside.mkdir(parents=True)
    file_entry.write_text("ok\n", encoding="utf-8")

    assert iso_mod._is_safe_local_dir(child, parent) is True
    assert iso_mod._is_safe_local_dir(parent / ".", parent) is False
    assert iso_mod._is_safe_local_dir(Path(os.path.join(str(parent), os.pardir)), parent) is False
    assert iso_mod._is_safe_local_dir(outside, parent) is False
    assert iso_mod._is_safe_local_dir(file_entry, parent) is False
    assert iso_mod._is_safe_local_dir(parent / "missing", parent) is False

    ws = tmp_path / "ws_tombstone"
    (ws / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "scripts" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (ws / "scripts" / "drop.py").write_text("DROP = 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "added.py").write_text("ADD = 1\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(
        json.dumps({"deleted_files": [".", "./", "../outside", "scripts/drop.py"]}),
        encoding="utf-8",
    )
    m_dir = iso_mod.mirror_workspace_to_nvme(ws, apply_overlay=True, mirror_siblings=False)
    try:
        assert (m_dir / "scripts" / "keep.py").is_file() and (m_dir / "scripts" / "added.py").is_file()
        assert not (m_dir / "scripts" / "drop.py").exists() and outside.is_dir()
    finally:
        iso_mod.safe_rmtree(m_dir.parent)


def _create_dir_reparse_link(link_path: Path, target_dir: Path, created_links: List[Path]) -> bool:
    """Crea symlink o junction Win32 verso target_dir senza skip e registra per cleanup."""
    try:
        link_path.symlink_to(target_dir, target_is_directory=True)
        created_links.append(link_path)
        return True
    except OSError:
        if sys.platform == "win32":
            import _winapi

            with contextlib.suppress(OSError):
                _winapi.CreateJunction(str(target_dir), str(link_path))
                created_links.append(link_path)
                return True
    return False


def _verify_symlink_mirror_exclusion(
    app_main: Path, ext_root: Path, evil_sib: Path, file_link_created: bool
) -> None:
    """Verifica esclusione dei link reparse da _is_safe_local_dir e dal mirror NVMe."""
    assert iso_mod._is_safe_local_dir(evil_sib, ext_root) is False
    assert iso_mod._is_safe_local_dir(app_main, ext_root) is True
    ignored_names = iso_mod._build_mirror_ignore(app_main)(str(app_main / "scripts"), ["safe.py", "sub_escape"])
    assert "sub_escape" in ignored_names and "safe.py" not in ignored_names

    m_dir = iso_mod.mirror_workspace_to_nvme(app_main, apply_overlay=True, mirror_siblings=True)
    try:
        assert (m_dir / "scripts" / "safe.py").is_file()
        assert not (m_dir.parent / "EvilSibling").exists()
        assert not (m_dir / "scripts" / "sub_escape").exists()
        assert not (m_dir / "stg_escape").exists()
        if file_link_created:
            assert not (m_dir / "leak_file.md").exists()
    finally:
        iso_mod.safe_rmtree(m_dir.parent)


def _cleanup_reparse_links(created_links: List[Path]) -> None:
    """Rimuove in ordine inverso symlink e junction creati durante il test."""
    for lp in reversed(created_links):
        with contextlib.suppress(OSError):
            if lp.is_symlink():
                lp.unlink(missing_ok=True)
            elif lp.exists() or getattr(lp, "is_junction", lambda: False)():
                lp.rmdir()


@pytest.mark.fast
def test_isolated_runner_local_dir_tombstone_and_symlink_guards(tmp_path: Path) -> None:
    """Verifica _is_safe_local_dir, tombstone root guard ed esclusione symlink/junction reparse."""
    _assert_tombstone_and_local_dir_guards(tmp_path)

    outside = tmp_path / "outside_secret"
    (outside / "scripts").mkdir(parents=True)
    (outside / "scripts" / "leak.py").write_text("SECRET = 1\n", encoding="utf-8")
    (outside / "secret.md").write_text("# secret\n", encoding="utf-8")

    ext_root = tmp_path / "NK_External_Projects"
    app_main = ext_root / "AppMain"
    (app_main / "scripts").mkdir(parents=True)
    (app_main / ".staging" / "scripts").mkdir(parents=True)
    (app_main / "scripts" / "safe.py").write_text("OK = 1\n", encoding="utf-8")

    created_links: List[Path] = []
    evil_sib = ext_root / "EvilSibling"
    assert _create_dir_reparse_link(evil_sib, outside, created_links) is True
    assert _create_dir_reparse_link(app_main / "scripts" / "sub_escape", outside, created_links) is True
    assert _create_dir_reparse_link(app_main / ".staging" / "stg_escape", outside, created_links) is True

    file_link_created = False
    with contextlib.suppress(OSError):
        (app_main / "leak_file.md").symlink_to(outside / "secret.md")
        created_links.append(app_main / "leak_file.md")
        file_link_created = True

    try:
        _verify_symlink_mirror_exclusion(app_main, ext_root, evil_sib, file_link_created)
    finally:
        _cleanup_reparse_links(created_links)


def _setup_parallel_mirror_tests(mirror_dir: Path) -> List[str]:
    """Crea 4 file test di peso distinto piu un file __pycache__ ignorato."""
    (mirror_dir / "tests" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (mirror_dir / "tests" / "__pycache__" / "test_ignored.py").write_text("def test_i(): assert False\n", encoding="utf-8")
    specs = (("test_a.py", 400), ("test_b.py", 300), ("test_c.py", 200), ("test_d.py", 100))
    rels: List[str] = []
    for name, sz in specs:
        p = mirror_dir / "tests" / name
        p.write_text("# " + ("x" * max(1, sz - 2)), encoding="utf-8")
        rels.append(f"tests/{name}")
    return rels


def _assert_worker_count_and_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Tuple[Path, List[str]]:
    """Verifica resolve_worker_count e should_use_parallel_shards."""
    assert (pp_mod.resolve_worker_count(1, {}), pp_mod.resolve_worker_count(8, {"NK_PYTEST_WORKERS": "1"})) == (1, 1)
    assert (pp_mod.resolve_worker_count(8, {"NK_PYTEST_WORKERS": "20"}), pp_mod.resolve_worker_count(20, {"NK_PYTEST_WORKERS": "15"})) == (8, 12)
    monkeypatch.setattr(pp_mod.os, "cpu_count", lambda: 1)
    assert pp_mod.resolve_worker_count(5, {"NK_PYTEST_WORKERS": "bad"}) == 2
    monkeypatch.setattr(pp_mod.os, "cpu_count", lambda: 8)
    assert pp_mod.resolve_worker_count(10, {}) == 8
    assert pp_mod.resolve_worker_count(2, {}) == 2
    assert pp_mod._has_disqualifying_shard_args(["tests"], (), {"NK_PYTEST_WORKERS": "1"}) is True
    assert pp_mod._has_disqualifying_shard_args(["tests/test_a.py::test_x"], (), {}) is True
    assert pp_mod._has_disqualifying_shard_args(["tests"], ("-q",), {}) is False

    mirror_dir = tmp_path / "mirror"
    expected_rels = _setup_parallel_mirror_tests(mirror_dir)
    for tgts, extra, env in (
        (["tests/test_a.py::test_x"], (), {}),
        (["tests"], ("--collect-only",), {}),
        (["tests"], ("--maxfail=1",), {}),
        (["tests"], (), {"NK_PYTEST_WORKERS": "1"}),
        (["tests/test_a.py", "tests/test_b.py"], (), {}),
    ):
        assert pp_mod.should_use_parallel_shards(tgts, extra, mirror_dir, env) == []
    assert pp_mod.should_use_parallel_shards(["tests", "tests/test_a.py"], (), mirror_dir, {}) == expected_rels
    return mirror_dir, expected_rels


def _assert_lpt_and_junit_merge(
    tmp_path: Path, mirror_dir: Path, expected_rels: List[str]
) -> None:
    """Verifica partition_files_lpt, strip_junitxml_args e merge_junit_xml_files."""
    shards = pp_mod.partition_files_lpt(expected_rels, mirror_dir, 2)
    flat = sorted(f for sh in shards for f in sh)
    assert (len(shards), flat) == (2, expected_rels)
    assert len(pp_mod.partition_files_lpt(["tests/miss1.py", "tests/miss2.py"], mirror_dir, 4)) == 2
    assert pp_mod.strip_junitxml_args(["-q", "--junitxml=a.xml", "-m", "fast", "--junitxml", "b.xml"]) == ["-q", "-m", "fast"]

    ent_xml = tmp_path / "ent.xml"
    ent_xml.write_text('<!DOCTYPE foo [<!ENTITY xxe "bad">]><testsuite tests="1"/>', encoding="utf-8")
    with pytest.raises(ValueError, match="ENTITY"):
        pp_mod.merge_junit_xml_files([ent_xml], tmp_path / "bad.xml", 0.1)
    assert pp_mod.merge_junit_xml_files([tmp_path / "absent.xml"], tmp_path / "none.xml", 0.1) is None

    w0_xml, w1_xml = tmp_path / "w0.xml", tmp_path / "w1.xml"
    w0_xml.write_text('<testsuites><testsuite name="s0" tests="2" failures="1" errors="0" skipped="0" time="0.1"><testcase classname="c0" name="t_fail"><failure message="boom">tb</failure></testcase><testcase classname="c0" name="t_ok"/></testsuite></testsuites>', encoding="utf-8")
    w1_xml.write_text('<testsuite name="s1" tests="3" failures="0" errors="0" skipped="1" time="0.2"><testcase classname="c1" name="t_skip"><skipped message="s"/></testcase></testsuite>', encoding="utf-8")
    dest_xml = tmp_path / "out" / "merged.xml"
    assert pp_mod.merge_junit_xml_files([w0_xml, w1_xml], dest_xml, 0.42) == dest_xml
    assert "<failure" in dest_xml.read_text(encoding="utf-8")
    summary = tas_io_mod.parse_junit_xml_summary(dest_xml)
    assert (summary["total"], summary["passed"], summary["failed"], summary["skipped"]) == (5, 3, 1, 1)


def _assert_timing_guided_lpt(
    tmp_path: Path, mirror_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica cache tempi shard in %TEMP% e ordinamento timing-guided di partition_files_lpt."""
    tim_tmp = tmp_path / "timings_env"
    tim_tmp.mkdir()
    monkeypatch.setenv("TEMP", str(tim_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(tim_tmp))
    assert pp_mod._load_timing_weights() == {}
    assert pp_mod._classname_to_rel_path("other.pkg.test_x") is None

    w_tim = tmp_path / "w_tim.xml"
    w_tim.write_text(
        '<testsuite name="t" tests="3" failures="0" errors="0" skipped="0" time="5.26">'
        '<testcase classname="tests.test_d.TestD" name="t1" time="5.000"/>'
        '<testcase classname="tests.test_a.TestA" name="t2" time="0.010"/>'
        '<testcase classname="tests.stress.test_real_sandbox_stress" name="t3" time="0.250"/>'
        "</testsuite>",
        encoding="utf-8",
    )
    pp_mod.merge_junit_xml_files([w_tim], tmp_path / "out" / "tim_merged.xml", 5.26, record_timings=True)
    weights = pp_mod._load_timing_weights()
    assert (weights["tests/test_d.py"], weights["tests/test_a.py"], weights["tests/stress/test_real_sandbox_stress.py"]) == (5000, 10, 250)
    t_shards = pp_mod.partition_files_lpt(["tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_d.py"], mirror_dir, 2)
    assert t_shards[0] == ["tests/test_d.py"]
    w_cov = tmp_path / "w_cov.xml"
    w_cov.write_text(
        '<testsuite name="c" tests="1" failures="0" errors="0" skipped="0" time="1.5">'
        '<testcase classname="tests.test_a.TestA" name="t_cov" time="1.500"/></testsuite>',
        encoding="utf-8",
    )
    pp_mod.merge_junit_xml_files([w_tim], tmp_path / "out" / "fast.xml", 5.26, record_timings=True, profile="fast")
    pp_mod.merge_junit_xml_files([w_cov], tmp_path / "out" / "cov.xml", 1.50, record_timings=True, profile="cov")
    assert pp_mod._load_timing_weights("fast")["tests/test_a.py"] == 10
    assert pp_mod._load_timing_weights("cov")["tests/test_a.py"] == 1500
    assert "tests/test_d.py" not in pp_mod._load_timing_weights("cov")
    assert pp_mod._timing_profile_key(["-m", "fast"], False) == "fast"
    assert pp_mod._timing_profile_key(["-m", "fast"], True) == "cov"


@pytest.mark.fast
def test_pytest_parallel_sharding_lpt_worker_count_and_junit_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica resolve_worker_count, should_use_parallel_shards, LPT, strip_junitxml e merge XML."""
    mirror_dir, expected_rels = _assert_worker_count_and_discovery(tmp_path, monkeypatch)
    _assert_lpt_and_junit_merge(tmp_path, mirror_dir, expected_rels)
    _assert_timing_guided_lpt(tmp_path, mirror_dir, monkeypatch)


def _install_fake_shard_popen(monkeypatch: pytest.MonkeyPatch, rc_by_idx: Dict[int, int], *, hang: bool = False) -> None:
    """Sostituisce subprocess.Popen con uno stub deterministico per shard index."""

    def _fake_popen(cmd: List[str], **kw: Any) -> SimpleNamespace:
        xml_arg = next((str(a).split("=", 1)[1] for a in cmd if str(a).startswith("--junitxml=")), "")
        w_idx = int(Path(xml_arg).parent.name.split("_", 1)[1]) if xml_arg else 0
        rc_val = int(rc_by_idx.get(w_idx, 0))
        stdout_fh = kw.get("stdout")
        if stdout_fh is not None:
            stdout_fh.write(f"worker {w_idx} rc={rc_val}\n")
        return SimpleNamespace(
            pid=5000 + w_idx,
            poll=(lambda: None) if hang else (lambda: rc_val),
            kill=lambda: None,
            wait=lambda timeout=None: -1,
        )

    monkeypatch.setattr(pp_mod.subprocess, "Popen", _fake_popen)


@pytest.mark.integration
def test_pytest_parallel_rc5_empty_shard_and_combine_coverage_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica aggregazione rc (0+5->0, tutti 5->5, 1->1, timeout->-1) e combine_worker_coverage fail-closed."""
    mirror_dir = tmp_path / "m_run"
    test_files = _setup_parallel_mirror_tests(mirror_dir)
    base_env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}

    _install_fake_shard_popen(monkeypatch, {0: 0, 1: 5})
    r_mix = pp_mod.run_parallel_pytest_shards(mirror_dir, tmp_path / "r_mix", test_files, base_env, ("-m", "fast"), 5.0, False, workers=2)
    assert (r_mix["rc"], r_mix["timed_out"], r_mix["workers_used"]) == (0, False, 2)

    _install_fake_shard_popen(monkeypatch, {0: 5, 1: 5})
    r_empty = pp_mod.run_parallel_pytest_shards(mirror_dir, tmp_path / "r_empty", test_files, base_env, ("-m", "fast"), 5.0, False, workers=2)
    assert (r_empty["rc"], r_empty["timed_out"]) == (5, False)

    _install_fake_shard_popen(monkeypatch, {0: 0, 1: 1})
    r_fail = pp_mod.run_parallel_pytest_shards(mirror_dir, tmp_path / "r_fail", test_files, base_env, ("-q",), 5.0, False, workers=2)
    assert (r_fail["rc"], r_fail["timed_out"]) == (1, False)

    killed_pids: List[int] = []
    _install_fake_shard_popen(monkeypatch, {0: 0, 1: 0}, hang=True)
    r_to = pp_mod.run_parallel_pytest_shards(
        mirror_dir, tmp_path / "r_to", test_files, base_env, ("-q",), 0.05, False,
        workers=2, kill_tree_fn=killed_pids.append,
    )
    assert (r_to["rc"], r_to["timed_out"], len(killed_pids)) == (-1, True, 2)

    empty_cov = tmp_path / "empty_cov"
    assert pp_mod.combine_worker_coverage(empty_cov, mirror_dir, tmp_path / "cov.json") is False
    empty_cov.mkdir()
    assert pp_mod.combine_worker_coverage(empty_cov, mirror_dir, tmp_path / "cov.json") is False
    (empty_cov / ".coverage.w0").write_bytes(b"corrupt-sqlite-coverage-bytes")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert pp_mod.combine_worker_coverage(empty_cov, mirror_dir, tmp_path / "cov.json") is False

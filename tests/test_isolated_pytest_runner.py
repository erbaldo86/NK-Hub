# -*- coding: utf-8 -*-
"""
Test Zero-Mock per isolamento Pytest su NVMe, PIDFileLock timeout e guardia hook Drive FS.
Modulo: tests/test_isolated_pytest_runner.py.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

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
    (ws / "scripts" / "calc.py").write_text("def inc(x: int) -> int:\n    return x + 1 if x >= 0 else 0\n", encoding="utf-8")
    (ws / "tests" / "test_old.py").write_text("def test_old():\n    assert True\n", encoding="utf-8")
    (ws / "tests" / "old_dir" / "test_sub.py").write_text("def test_sub():\n    assert True\n", encoding="utf-8")
    (ws / "tests" / "test_keep.py").write_text("from scripts.calc import inc\n\ndef test_keep():\n    assert inc(1) == 2 and inc(-1) == 0\n", encoding="utf-8")
    (ws / ".staging" / ".gitkeep").write_text("", encoding="utf-8")
    (ws / ".staging" / "tests" / "test_staged.py").write_text("def test_staged():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["tests/test_old.py", "tests/old_dir"]}), encoding="utf-8")
    (ws / "nk_tracking" / "sessions" / "skip.json").write_text("{}", encoding="utf-8")
    (ws / "nk_tracking" / "handoff" / "skip_h.json").write_text("{}", encoding="utf-8")
    (ws / ".git" / "HEAD").write_text("ref: main\n", encoding="utf-8")
    return ws


@pytest.mark.fast
def test_win32_detached_flags_and_mirror_overlay(tmp_path: Path) -> None:
    """Verifica costanti detached Win32 e copia/overlay mirror_workspace_to_nvme."""
    assert iso_mod.WIN32_CREATE_NEW_PROCESS_GROUP == 0x00000200 and iso_mod.WIN32_CREATE_NO_WINDOW == 0x08000000
    expected_flags = (0x00000200 | 0x08000000) if sys.platform == "win32" else 0
    assert iso_mod.WIN32_DETACHED_FLAGS == expected_flags
    assert iso_mod.win32_detached_flags(0x4) == ((expected_flags | 0x4) if sys.platform == "win32" else 0)

    ws = _build_mini_hub_ws(tmp_path)
    mirror_no_ov = iso_mod.mirror_workspace_to_nvme(ws, apply_overlay=False)
    try:
        assert mirror_no_ov.name == "MiniHub" and (mirror_no_ov / "pytest.ini").is_file()
        assert (mirror_no_ov / "README.md").is_file() and not (mirror_no_ov / ".coverage.stale").exists()
        assert (mirror_no_ov / ".staging" / "tests" / "test_staged.py").is_file()
        assert not (mirror_no_ov / ".git").exists() and not (mirror_no_ov / "nk_tracking" / "sessions").exists()
    finally:
        assert iso_mod.safe_rmtree(mirror_no_ov.parent) is True

    mirror_ov = iso_mod.mirror_workspace_to_nvme(ws, apply_overlay=True)
    try:
        assert (mirror_ov / "tests" / "test_staged.py").is_file() and not (mirror_ov / ".gitkeep").exists()
        assert not (mirror_ov / "tests" / "test_old.py").exists() and not (mirror_ov / "tests" / "old_dir").exists()
    finally:
        assert iso_mod.safe_rmtree(mirror_ov.parent) is True

    mirror_no_stg = iso_mod.mirror_workspace_to_nvme(ws, staging_dir=tmp_path / "missing_stg")
    try:
        assert not (mirror_no_stg / ".staging").exists()
    finally:
        assert iso_mod.safe_rmtree(mirror_no_stg.parent) is True


@pytest.mark.integration
def test_run_detached_pytest_and_platform_runner_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica run_detached_pytest, --pytest-isolated CLI, --help, coverage e cleanup mirror."""
    ws = _build_mini_hub_ws(tmp_path)
    diag_dir = tmp_path / "diag"
    res_ok = iso_mod.run_detached_pytest(
        workspace_root=ws, targets=("tests/test_keep.py", "tests/test_staged.py"),
        extra_args=("--import-mode=prepend", "-q"), timeout_sec=30.0,
        coverage=True, apply_overlay=True, log_dir=diag_dir, keep_mirror=True,
    )
    try:
        assert res_ok["success"] is True and res_ok["exit_code"] == 0 and res_ok["passed"] == 2
        assert res_ok["mirror_cleaned"] is False and Path(res_ok["mirror_dir"]).is_dir()
        assert res_ok["coverage"]["true_branch_coverage_pct"] > 0.0 and (diag_dir / "pytest_iso_last.json").is_file()
    finally:
        assert iso_mod.safe_rmtree(Path(res_ok["mirror_dir"]).parent) is True

    res_sync_miss = iso_mod.run_detached_pytest(
        workspace_root=ws, targets=("tests/missing_only.py",), timeout_sec=30.0, apply_overlay=False, log_dir=diag_dir
    )
    assert res_sync_miss["success"] is False and res_sync_miss["status"] == "FAIL" and res_sync_miss["mirror_cleaned"] is True

    (ws / ".staging" / "tests" / "test_hang.py").write_text("import time\n\ndef test_hang():\n    time.sleep(5)\n", encoding="utf-8")
    res_to = iso_mod.run_detached_pytest(workspace_root=ws, targets=("tests/test_hang.py",), timeout_sec=0.35, log_dir=diag_dir)
    assert res_to["timed_out"] is True and res_to["success"] is False and res_to["mirror_cleaned"] is True

    monkeypatch.setenv("TEMP", str(tmp_path / "cli_tmp"))
    monkeypatch.setenv("TMP", str(tmp_path / "cli_tmp"))
    rc_help, out_help, _ = call_script_main_captured(pr_mod, ["--help"])
    assert rc_help == 0 and "--pytest-isolated" in out_help

    proc_cli = subprocess.run(
        [sys.executable, "-B", "-u", str(Path(pr_mod.__file__).resolve()), "--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/test_keep.py", "--overlay-staging", "--json"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45, check=False,
    )
    assert proc_cli.returncode == 0 and json.loads(proc_cli.stdout)["passed"] == 1


@pytest.mark.fast
def test_pid_file_lock_bounded_acquire_timeout(tmp_path: Path) -> None:
    """Verifica che PIDFileLock(..., acquire_timeout_sec=0.15) fallisca rapidamente."""
    lock_p = tmp_path / "bounded.lock"
    lock_p.write_text(json.dumps({"pid": os.getpid(), "nonce": "busy", "timestamp": time.time()}), encoding="utf-8")
    lk = lio_mod.PIDFileLock(lock_p, stale_timeout_sec=10.0, acquire_timeout_sec=0.15)
    t0 = time.perf_counter()
    with pytest.raises(TimeoutError):
        with lk:
            assert False
    assert (time.perf_counter() - t0) < 1.5


@pytest.mark.fast
def test_hook_gate_rule_win32_isolated_pytest(tmp_path: Path) -> None:
    """Verifica blocco pytest su Drive FS vs esenzione runner isolati e %TEMP%."""
    temp_tok = "%" + "TEMP%"
    drive_ws = Path("G:/Il mio Drive/Antigravity/NK_Hub")
    for blocked_cmd in (
        "pytest tests/test_core_platform_utilities.py",
        "python -m pytest -q",
        'python -m pytest "g:/Il mio Drive/Antigravity/NK_Hub/tests/test_a.py"',
        'python scripts/platform_runner.py --cmd "pytest tests/"',
        'python scripts/platform_runner.py --cmd="pytest -q"',
        "python -m pytest --basetemp=" + temp_tok + "/bt tests/test_a.py",
    ):
        res = hook_mod._handle_write_gate(
            {"toolName": "run_command", "toolInput": {"CommandLine": blocked_cmd}}, drive_ws, False, "", "", "",
        )
        assert res.get("decision") == "deny" and "[RULE-WIN32-ISOLATED-PYTEST]" in res.get("reason", ""), blocked_cmd

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


@pytest.mark.fast
def test_isolated_runner_unit_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre is_temp_workspace, safe_rmtree readonly/retry, tombstone, target e metriche."""
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
    assert iso_mod._resolve_mirror_targets(ws_ref, ws_ref, (f"{ws_ref.as_posix()}/tests/test_keep.py", "MiniHub/tests/test_x.py", "./.staging/tests/test_s.py")) == ["tests/test_keep.py", "tests/test_x.py", "staging/tests/test_s.py"]
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
    iso_mod._kill_detached_tree(999999)


@pytest.mark.integration
def test_platform_runner_isolated_cli_and_tokenizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Copre CLI --pytest-isolated (text/json/--pytest-args/error), tokenizer e subprocess."""
    assert isolated_nk_env.is_dir()
    ws = _build_mini_hub_ws(tmp_path)
    assert call_script_main_captured(pr_mod, [])[0] == 2
    rc_j, out_j, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/test_keep.py", "--overlay-staging", "--json"])
    assert rc_j == 0 and json.loads(out_j)["passed"] == 1
    rc_t, out_t, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/test_keep.py", "--overlay-staging", "--pytest-args", "-v --tb=short"])
    assert rc_t == 0 and "[NK-PYTEST-ISO] status=PASS" in out_t
    rc_m, out_m, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(ws), "--targets", "tests/nonexistent_tgt.py", "--timeout", "15"])
    assert rc_m != 0 and "[NK-PYTEST-ISO] status=FAIL" in out_m

    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()
    rc_e, out_e, _ = call_script_main_captured(pr_mod, ["--pytest-isolated", "--workspace-root", str(empty_ws)])
    assert rc_e != 0 and "[NK-PYTEST-ISO] status=FAIL" in out_e

    rc_se, _, err_se = call_script_main_captured(pr_mod, ["--cmd", f'"{sys.executable}" -c "import sys; sys.stderr.write(\'e\')"'])
    assert rc_se == 0 and "e\n" in err_se
    assert pr_mod.safe_subprocess_run("nonexistent_nk_bin_xyz")[0] == 127
    assert pr_mod.safe_subprocess_run([sys.executable, "-c", "print('ok')"], env={"NK_SUB_TEST": "1"}, use_shell=True)[0] == 0
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
        seen_shell: list[object] = []
        mp.setattr(
            subprocess,
            "Popen",
            lambda tgt, **_kw: (
                seen_shell.append(tgt)
                or SimpleNamespace(returncode=0, communicate=lambda timeout=None: ("posix ok\n", ""))
            ),
        )
        rc_px, out_px, _ = pr_mod.safe_subprocess_run(["echo", "posix sh"], use_shell=True)
        assert rc_px == 0 and out_px == "posix ok\n" and seen_shell == ["echo 'posix sh'"]


@pytest.mark.fast
def test_ledger_lock_shards_and_domain_matcher_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre edge di ledger_lock_io, shards_rehydrate e domain_matcher."""
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


@pytest.mark.fast
def test_target_classifier_isolated_pytest_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre _is_temp_root_path, _segment_targets_temp_isolated e TEMP proj_is_temp."""
    temp_low = ("%" + "temp%").lower()
    assert tc_mod._classify_isolated_pytest_violation("pytest tests/test_a.py", "pytest tests/test_a.py", tmp_path) is None
    assert tc_mod._segment_targets_temp_isolated(f"python -m pytest --rootdir={temp_low}/nk_pytest_iso_1 {temp_low}/nk_pytest_iso_1/tests/test_a.py", "/tmp") is True
    assert tc_mod._segment_targets_temp_isolated(f"python -m pytest --rootdir=g:/bad {temp_low}/nk_pytest_iso_1/tests/test_a.py", "/tmp") is False
    assert tc_mod._segment_targets_temp_isolated("python -m pytest -k tests/foo -o junit=x --basetemp /tmp/bt --cov scripts basetemp=/tmp/bt /tmp/tests/test_a.py", "/tmp") is True
    assert tc_mod._segment_targets_temp_isolated("python -m pytest tests/test_a.py", "/tmp") is False
    assert tc_mod._segment_targets_temp_isolated("python -m pytest -q", "/tmp") is False

    custom_td = tmp_path / "tc_td"
    custom_td.mkdir()
    with monkeypatch.context() as mp:
        for k in ("TEMP", "TMP", "LOCALAPPDATA"):
            mp.setenv(k, "")
        mp.setenv("TMPDIR", str(custom_td))
        assert tc_mod._is_temp_root_path(custom_td / "sub") is True
        assert tc_mod._is_temp_root_path(Path("C:/outside_non_temp_proj")) is False

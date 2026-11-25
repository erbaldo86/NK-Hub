# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per DAST Sandbox Runner e Line Tracer.
Modulo: tests/test_dast_sandbox.py.
Valida ciclo di vita sandbox, confinamento CRIT-05, junction NTFS, holdout v1/v2, Job Win32 e CLI.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import uuid
from typing import Any, List

import pytest

try:
    from conftest import load_nk_script_module, load_script_by_relpath
except ImportError:
    from tests.conftest import load_nk_script_module, load_script_by_relpath

dast_mod = load_nk_script_module("dast_sandbox_runner")
runner_mod = load_nk_script_module("platform_runner")
DASTSandboxRunner = dast_mod.DASTSandboxRunner
SandboxConfig = dast_mod.SandboxConfig
ShadowSandbox = dast_mod.ShadowSandbox
_build_sanitized_sandbox_env = dast_mod._build_sanitized_sandbox_env
_get_process_memory_rss = dast_mod._get_process_memory_rss
_resolve_confined_sandbox_path = dast_mod._resolve_confined_sandbox_path
resolve_dast_report_path = dast_mod.resolve_dast_report_path
run_staging_shadow_verification = dast_mod.run_staging_shadow_verification
write_atomic_dast_report = dast_mod.write_atomic_dast_report

from _internal.dast_sandbox_runner import (  # noqa: E402
    cli as dast_cli,
    constants as dast_const,
    e2e_and_audit as dast_e2e,
    fuzzer as dast_fuzzer,
    holdout_verify as dast_holdout,
    process_runner as dast_proc,
    sandbox_fs as dast_fs,
    staging_overlay as dast_overlay,
    win32_job as dast_job,
)
from _internal.nk_common import isolated_test_runner as itr_mod  # noqa: E402
from _internal.nk_common.oracle_lock import (  # noqa: E402
    compute_combined_sha256,
    compute_lf_sha256,
)

load_script_by_relpath("dast_runner_sync", "scripts/platform_runner.py")


def _seed_holdout_tree(base_dir: Path, mod_rel_key: str) -> None:
    """Inizializza albero holdout minimo con oracle_lock e suite v1/v2."""
    files = {
        base_dir / "tests" / "evals" / "skill_golden_eval_set.json": '{"skills": []}\n',
        base_dir / "tests" / "test_locked.py": "def test_locked():\n    assert (1 + 1) == 2\n",
        base_dir / "scripts" / "mod.py": "VALUE = 1\n",
        base_dir / "nk_tracking" / "benchmark_suite" / "tasks_v1.json": '{"tasks": []}\n',
        base_dir / "nk_tracking" / "benchmark_suite" / "tasks_builder_v2.json": '{"tasks": []}\n',
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    fmap = {
        "evals/skill_golden_eval_set.json": compute_lf_sha256(base_dir / "tests" / "evals" / "skill_golden_eval_set.json"),
        "test_locked.py": compute_lf_sha256(base_dir / "tests" / "test_locked.py"),
        mod_rel_key: compute_lf_sha256(base_dir / "scripts" / "mod.py"),
    }
    (base_dir / "nk_tracking" / "oracle_lock.json").write_text(
        json.dumps({"target": (base_dir / "tests").resolve().as_posix(), "files": fmap, "combined_sha256": compute_combined_sha256(fmap)}),
        encoding="utf-8",
    )


def _assert_sandbox_fs_pkg_and_truncate(tmp_path: Path) -> None:
    assert dast_fs._truncate_utf8_bytes("abcd", 0) == ""
    assert len(dast_fs._truncate_utf8_bytes("è" * 10, 5).encode("utf-8")) <= 5
    pkg_ws = tmp_path / "pkg_ctx_ws"
    (pkg_ws / "mypkg" / "sub").mkdir(parents=True)
    (pkg_ws / "mypkg" / "__init__.py").write_text("", encoding="utf-8")
    (pkg_ws / "mypkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (pkg_ws / "mypkg" / "sub" / "entry.py").write_text("X = 1\n", encoding="utf-8")
    (pkg_ws / "mypkg" / "sub" / "extra.py").write_text("Y = 2\n", encoding="utf-8")
    (pkg_ws / "empty_dir").mkdir()
    (pkg_ws / "py_only_dir").mkdir()
    (pkg_ws / "py_only_dir" / "mod.py").write_text("Z = 3\n", encoding="utf-8")
    assert (dast_fs._should_copy_child_pkg(pkg_ws / "tests"), dast_fs._should_copy_child_pkg(pkg_ws / "empty_dir"), dast_fs._should_copy_child_pkg(pkg_ws / "py_only_dir")) == (False, False, True)
    with ShadowSandbox() as sb_pkg:
        rel_entry, py_roots = dast_fs.copy_script_package_context(sb_pkg, pkg_ws / "mypkg" / "sub" / "entry.py", overwrite=False)
        assert (rel_entry, str(sb_pkg.sandbox_dir) in py_roots) == ("mypkg/sub/entry.py", True)
        assert (dast_fs._copy_tree_to_sandbox(sb_pkg, pkg_ws / "mypkg", "mypkg", overwrite=False, max_files=1), dast_fs._copy_tree_to_sandbox(sb_pkg, pkg_ws / "mypkg", "dup_pkg", overwrite=True, max_files=1)) == (0, 1)


def _assert_sandbox_copy_and_traversal(tmp_path: Path) -> None:
    src_f = tmp_path / "src_mod.py"
    src_f.write_text("V = 1\n", encoding="utf-8")
    with ShadowSandbox() as sb:
        assert (sb.write_file("sub/safe_mod.py", "SAFE = 1\n").is_file(), sb.copy_file(src_f, "").is_file(), sb.copy_file(src_f, "sub_dir/").name, sb.copy_file(src_f, "sub_dir").is_file(), sb.copy_file(src_f, "custom/renamed.py").name) == (True, True, "src_mod.py", True, "renamed.py")
        with pytest.raises(FileNotFoundError):
            sb.copy_file(tmp_path / "missing.py")
        for escaped in ("", "   ", "a\x00b", ".", "../escape.py", "sub/../../escape.py", "C:/Windows/Temp/evil.py", "/abs/evil.py", "sub/evil.txt:ads", "//server/share/evil.py", "\\\\server\\share\\file.py", "D:rel.py"):
            with pytest.raises(ValueError):
                _resolve_confined_sandbox_path(sb.sandbox_dir, escaped)
        assert _resolve_confined_sandbox_path(sb.sandbox_dir, "ok.py") == (sb.sandbox_dir / "ok.py").resolve()
    assert not sb.sandbox_dir.exists()


@pytest.mark.fast
def test_dast_sandbox_env_copy_confinement_and_ids(tmp_path: Path, isolated_nk_env: Path) -> None:
    """Verifica sanificazione env, copy_file, CRIT-05 traversal, ID confinamento e sandbox_fs helpers."""
    assert isolated_nk_env.is_dir()
    env = _build_sanitized_sandbox_env({"API_TOKEN": "keep_extra_token", "NK_ALLOW_GOVERNANCE_OVERRIDE": "1", "CUSTOM_VAR": "ok"})
    assert ("NK_ALLOW_GOVERNANCE_OVERRIDE" not in env, env["CUSTOM_VAR"], env["PYTHONDONTWRITEBYTECODE"]) == (True, "ok", "1")
    assert (dast_fs._validate_sandbox_id("nk_ok-01"), dast_fs._validate_sandbox_id(None).startswith("nk_sandbox_")) == ("nk_ok-01", True)
    for bad_id in ("", "../escape", "sub/dir", "sub\\dir", "bad id", "a" * 81):
        with pytest.raises(ValueError):
            dast_fs._validate_sandbox_id(bad_id)

    base_dir, sibling = tmp_path / "base", tmp_path / "outside"
    good_sb = base_dir / "sb_one"
    good_sb.mkdir(parents=True)
    sibling.mkdir()
    assert dast_fs._assert_sandbox_dir_confined(base_dir, good_sb) == good_sb.resolve()
    for outside in (base_dir, sibling, base_dir.parent):
        with pytest.raises(ValueError):
            dast_fs._assert_sandbox_dir_confined(base_dir, outside)

    _assert_sandbox_copy_and_traversal(tmp_path)
    explicit_file = tmp_path / "explicit.json"
    assert (resolve_dast_report_path(tmp_path, str(tmp_path) + "/").name.startswith("dast_report_"), resolve_dast_report_path(tmp_path, "sub/").parent.name, write_atomic_dast_report({"ok": True}, tmp_path, explicit_output=explicit_file), explicit_file.is_file()) == (True, "sub", explicit_file, True)
    _assert_sandbox_fs_pkg_and_truncate(tmp_path)


@pytest.mark.fast
def test_s0_env_sanitization_and_deleted_manifest_schema(tmp_path: Path) -> None:
    """Verifica sanitizzazione segreti + override governance e schema .deleted_files.json."""
    clean = dast_fs._build_sanitized_sandbox_env(
        {"MY_API_KEY": "secret-val", "APP_SECRET": "hidden", "SERVICE_AUTH_TOKEN": "tok-123", "DB_PASSWORD": "pw", "AWS_CREDENTIAL": "cred", "NK_ALLOW_GOVERNANCE_OVERRIDE": "1", "NK_SAFE_MARKER": "green"}
    )
    for blocked in ("MY_API_KEY", "APP_SECRET", "SERVICE_AUTH_TOKEN", "DB_PASSWORD", "AWS_CREDENTIAL", "NK_ALLOW_GOVERNANCE_OVERRIDE"):
        assert blocked not in clean
    assert (clean.get("NK_SAFE_MARKER"), clean.get("PYTHONDONTWRITEBYTECODE")) == ("green", "1")

    list_m, dict_m, bad_s, bad_e = tmp_path / "del_list.json", tmp_path / "del_dict.json", tmp_path / "bad_schema.json", tmp_path / "bad_empty.json"
    list_m.write_text('["scripts/old.py"]', encoding="utf-8")
    dict_m.write_text('{"deleted_files": ["scripts/two.py"]}', encoding="utf-8")
    bad_s.write_text('{"unexpected": ["scripts/x.py"]}', encoding="utf-8")
    bad_e.write_text('{"deleted_files": [""]}', encoding="utf-8")
    assert (dast_overlay._parse_deleted_files_manifest(list_m), dast_overlay._parse_deleted_files_manifest(dict_m)) == (["scripts/old.py"], ["scripts/two.py"])
    with pytest.raises(ValueError):
        dast_overlay._parse_deleted_files_manifest(bad_s)
    with pytest.raises(ValueError):
        dast_overlay._parse_deleted_files_manifest(bad_e)


def _assert_holdout_v1_v2_overlay_and_evaluator(tmp_path: Path) -> None:
    ws = tmp_path / "ws_ov"
    stg = ws / ".staging"
    (ws / "scripts").mkdir(parents=True)
    (ws / "scripts" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (ws / "scripts" / "obsolete.py").write_text("OLD = 1\n", encoding="utf-8")
    for rel_p in dast_const._BUILDER_STRIP_PATHS:
        target = ws / rel_p
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel_p.endswith(".json"):
            target.write_text('{"files": {}}\n', encoding="utf-8")
        else:
            (target / "holdout.json").parent.mkdir(parents=True, exist_ok=True)
            (target / "holdout.json").write_text('{"canary": 1}\n', encoding="utf-8")
    (stg / "scripts").mkdir(parents=True)
    (stg / "scripts" / "added.py").write_text("ADDED = 2\n", encoding="utf-8")
    (stg / ".deleted_files.json").write_text('{"deleted_files": ["scripts/obsolete.py"]}', encoding="utf-8")

    uid = uuid.uuid4().hex[:8]
    with ShadowSandbox(sandbox_id=f"nk_s0_bldr_{uid}") as sb_bldr:
        ov, deleted, stripped = dast_overlay.prepare_staging_overlay(ws, stg, sb_bldr, norm_prof="builder")
        assert ("scripts/added.py" in ov, "scripts/obsolete.py" in deleted, (sb_bldr.sandbox_dir / "scripts" / "obsolete.py").exists(), set(stripped) == set(dast_const._BUILDER_STRIP_PATHS)) == (True, True, False, True)
    with ShadowSandbox(sandbox_id=f"nk_s0_eval_{uid}") as sb_eval:
        _, _, eval_stripped = dast_overlay.prepare_staging_overlay(ws, stg, sb_eval, norm_prof="evaluator")
        assert (eval_stripped, all((sb_eval.sandbox_dir / rel_p).exists() for rel_p in dast_const._BUILDER_STRIP_PATHS)) == ([], True)


@pytest.mark.integration
def test_s0_and_wave1a_holdout_verify_protects_v1_and_v2_suites(tmp_path: Path) -> None:
    """Verifica strip holdout builder vs evaluator, evals, test bloccati, tasks_v1 e tasks_builder_v2."""
    _assert_holdout_v1_v2_overlay_and_evaluator(tmp_path)
    root, sb_dir = tmp_path / "prod_hub", tmp_path / "sb_hub"
    mod_key = f"{chr(46) * 2}/scripts/mod.py"
    _seed_holdout_tree(root, mod_key)
    _seed_holdout_tree(sb_dir, mod_key)
    (sb_dir / "tests" / "test_brand_new.py").write_text("def test_new():\n    assert (2 + 2) == 4\n", encoding="utf-8")
    ok_res = dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", ["scripts/mod.py", "tests/test_brand_new.py"], [])
    assert (ok_res["passed"], "scripts/mod.py" in ok_res["overlaid_locked_files"]) == (True, True)
    for blocked_rel in ("tests/evals/skill_golden_eval_set.json", "tests/test_locked.py", "nk_tracking/benchmark_suite/tasks_v1.json", "nk_tracking/benchmark_suite/tasks_builder_v2.json"):
        assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [blocked_rel], [])["passed"] is False


@pytest.mark.fast
def test_wave1a_e2e_ast_guard_uses_prod_copy_and_cli_resolves_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica e2e ignora ast_guard in sandbox/.staging e cli risolve repo_root da .staging."""
    hub_root = tmp_path / "HubRoot"
    prod_guard, stg_facade = hub_root / "scripts" / "ast_guard_validator.py", hub_root / ".staging" / "scripts" / "dast_sandbox_runner.py"
    prod_guard.parent.mkdir(parents=True)
    stg_facade.parent.mkdir(parents=True)
    prod_guard.write_text("# prod guard\n", encoding="utf-8")
    stg_facade.write_text("# staged facade\n", encoding="utf-8")

    sb_dir = tmp_path / "sb_run"
    (sb_dir / "scripts").mkdir(parents=True)
    (sb_dir / "scripts" / "ast_guard_validator.py").write_text("# tampered\n", encoding="utf-8")
    recorded_cmds: List[List[str]] = []
    monkeypatch.setattr(dast_mod, "__file__", str(stg_facade))
    ast_res = dast_e2e._run_ast_guard_on_sandbox(sb_dir, {}, 5.0, lambda cmd, **_k: recorded_cmds.append(list(cmd)) or subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr=""), sys)
    assert ast_res["passed"] is True and Path(recorded_cmds[0][2]).resolve() == prod_guard.resolve() and Path(recorded_cmds[0][2]).resolve() != (sb_dir / "scripts" / "ast_guard_validator.py").resolve()
    monkeypatch.setattr(dast_cli, "__file__", str(hub_root / ".staging" / "scripts" / "_internal" / "dast_sandbox_runner" / "cli.py"))
    assert dast_cli._resolve_hub_repo_root() == hub_root.resolve()


def _assert_dast_cli_mount_and_pythonpath(tmp_path: Path) -> None:
    ov_root = tmp_path / "ov_mount"
    stg_dir = ov_root / ".staging"
    (ov_root / "nk_tracking" / "oracle_holdout").mkdir(parents=True)
    (ov_root / "scripts").mkdir(parents=True)
    (stg_dir / "scripts").mkdir(parents=True)
    hold_py, prod_py, stg_py, ext_py = ov_root / "nk_tracking" / "oracle_holdout" / "h.py", ov_root / "scripts" / "p.py", stg_dir / "scripts" / "s.py", tmp_path / "collision.py"
    for p in (hold_py, prod_py, stg_py, ext_py):
        p.write_text("X = 1\n", encoding="utf-8")
    with ShadowSandbox() as sb_m:
        sb_m.write_file("collision.py", "ORIG = 1\n")
        (sb_m.sandbox_dir / "src").mkdir(exist_ok=True)
        (sb_m.sandbox_dir / "src_app").mkdir(exist_ok=True)
        assert dast_cli._mount_script_into_overlay(sb_m, stg_py, ov_root, stg_dir, "builder", dast_fs.copy_script_package_context, dast_const._BUILDER_STRIP_PATHS)[0] == "scripts/s.py"
        assert dast_cli._mount_script_into_overlay(sb_m, prod_py, ov_root, stg_dir, "builder", dast_fs.copy_script_package_context, dast_const._BUILDER_STRIP_PATHS)[0] == "scripts/p.py"
        with pytest.raises(ValueError, match="holdout vietato"):
            dast_cli._mount_script_into_overlay(sb_m, hold_py, ov_root, stg_dir, "builder", dast_fs.copy_script_package_context, dast_const._BUILDER_STRIP_PATHS)
        poc_rel, _ = dast_cli._mount_script_into_overlay(sb_m, ext_py, ov_root, stg_dir, "builder", dast_fs.copy_script_package_context, dast_const._BUILDER_STRIP_PATHS)
        pp = dast_cli._compose_sandbox_pythonpath(sb_m.sandbox_dir, [], prod_py, "evaluator", False)
        assert (poc_rel.startswith("_nk_poc_"), str(sb_m.sandbox_dir / "src_app") in pp, str(prod_py.parent.parent) in pp) == (True, True, True)


@pytest.mark.fast
def test_dast_cli_help_missing_and_holdout_guards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Esercita cli.py su help, script/overlay mancante, guardie holdout, _mount_script e pythonpath."""
    assert (dast_cli.main([]), "usage:" in capsys.readouterr().out.lower()) == (0, True)
    monkeypatch.setattr(dast_cli, "__file__", str(tmp_path / "prod_hub" / "scripts" / "_internal" / "dast_sandbox_runner" / "cli.py"))
    assert dast_cli._resolve_hub_repo_root() == (tmp_path / "prod_hub").resolve()
    assert (dast_cli.main(["--script", str(tmp_path / "absent.py")]), "non trovato" in capsys.readouterr().err.lower()) == (1, True)
    assert (dast_cli.main(["--verify-holdout", "--profile", "builder", "--json"]), json.loads(capsys.readouterr().out)["passed"]) == (1, False)
    assert (dast_cli.main(["--verify-holdout", "--profile", "builder"]), "[FAIL]" in capsys.readouterr().err) == (1, True)

    dummy_script = tmp_path / "ok_dummy.py"
    dummy_script.write_text("print(1)\n", encoding="utf-8")
    assert (dast_cli.main(["--script", str(dummy_script), "--overlay-staging", str(tmp_path / "no_ov"), "--json"]), json.loads(capsys.readouterr().out)["outcome"]) == (1, "HARNESS_ERROR")
    assert (dast_cli.main(["--script", str(dummy_script), "--overlay-staging", str(tmp_path / "no_ov")]), "[FAIL]" in capsys.readouterr().err) == (1, True)
    _assert_dast_cli_mount_and_pythonpath(tmp_path)


@pytest.mark.fast
def test_dast_staging_overlay_heavy_data_and_manifest_errors(tmp_path: Path) -> None:
    """Esercita staging_overlay.py su heavy data bytes, ignore_fn e manifest scalari invalidi."""
    ws = tmp_path / "ov_heavy_bytes"
    (ws / "data" / "heavy_sub").mkdir(parents=True)
    (ws / "data" / "small.txt").write_text("ok", encoding="utf-8")
    (ws / "data" / "heavy_sub" / "big.bin").write_bytes(b"X" * 200)
    assert len(dast_overlay._iter_safe_walk_files(ws / "data")) == 2
    assert dast_overlay._dir_exceeds_bytes(ws / "data", 50) is True and dast_overlay._dir_exceeds_bytes(ws / "data", 5000) is False
    ign = dast_overlay._build_sandbox_ignore_fn(ws, max_heavy_bytes=50)
    ignored_names = ign(str(ws / "data"), ["small.txt", "heavy_sub", "__pycache__"])
    assert "heavy_sub" in ignored_names and "__pycache__" in ignored_names and dast_overlay._is_blocked_reparse(tmp_path / "no_such_entry", tmp_path.resolve()) is False
    scalar_manifest = tmp_path / "scalar.json"
    scalar_manifest.write_text("123", encoding="utf-8")
    with pytest.raises(ValueError):
        dast_overlay._parse_deleted_files_manifest(scalar_manifest)


@pytest.mark.fast
def test_dast_staging_overlay_extra_dirs_root_files_and_missing_tombstone(tmp_path: Path) -> None:
    """Esercita prepare_staging_overlay su dir custom, file root filtrati, data staged e tombstone assente."""
    ws = tmp_path / "ov_extra_ws"
    for d in ("scripts", "custom_pkg", ".staging/data", ".staging/scripts"):
        (ws / d).mkdir(parents=True)
    (ws / "scripts" / "keep.py").write_text("K = 1\n", encoding="utf-8")
    (ws / "custom_pkg" / "extra.py").write_text("E = 2\n", encoding="utf-8")
    (ws / "README.md").write_text("# Docs\n", encoding="utf-8")
    (ws / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (ws / "dump.db").write_text("sqlite", encoding="utf-8")
    (ws / ".staging" / "data" / "staged.txt").write_text("stg", encoding="utf-8")
    (ws / ".staging" / "scripts" / "new_mod.py").write_text("N = 3\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text('{"deleted_files": ["scripts/non_existent.py"]}', encoding="utf-8")

    with ShadowSandbox() as sb:
        ov_files, del_applied, stripped = dast_overlay.prepare_staging_overlay(ws, ws / ".staging", sb, norm_prof="evaluator")
        assert ("scripts/new_mod.py" in ov_files, del_applied, stripped) == (True, [], [])
        assert ((sb.sandbox_dir / "custom_pkg" / "extra.py").is_file(), (sb.sandbox_dir / "README.md").is_file(), (sb.sandbox_dir / "data" / "staged.txt").is_file(), (sb.sandbox_dir / ".env").exists(), (sb.sandbox_dir / "dump.db").exists()) == (True, True, True, False, False)


def _assert_holdout_suite_and_sb_diffs(tmp_path: Path) -> Path:
    miss_suite, empty_suite, bad_suite = tmp_path / "miss_s", tmp_path / "empty_s", tmp_path / "bad_s"
    empty_suite.mkdir()
    bad_suite.mkdir()
    (bad_suite / "t.json").write_text("{bad", encoding="utf-8")
    assert (dast_holdout._validate_suite_dir(miss_suite, has_oh=True), len(dast_holdout._validate_suite_dir(miss_suite, has_oh=False))) == ([], 1)
    assert (dast_holdout._validate_suite_dir(empty_suite, has_oh=True), len(dast_holdout._validate_suite_dir(empty_suite, has_oh=False))) == ([], 1)
    assert any("corrotto" in e for e in dast_holdout._validate_suite_dir(bad_suite, has_oh=False))

    prod_oh, sb_oh = tmp_path / "p_oh", tmp_path / "s_oh"
    prod_oh.mkdir()
    sb_oh.mkdir()
    pf = prod_oh / "h.txt"
    pf.write_text("orig", encoding="utf-8")
    assert "mancante" in (dast_holdout._compare_prod_holdout_file(pf, prod_oh, sb_oh)[1] or "")
    (sb_oh / "h.txt").write_text("altered", encoding="utf-8")
    assert "alterato" in (dast_holdout._compare_prod_holdout_file(pf, prod_oh, sb_oh)[1] or "")
    extra_f = sb_oh / "extra.json"
    extra_f.write_text('{"x": 1}', encoding="utf-8")
    assert any("non autorizzato" in e for e in dast_holdout._check_extra_sb_holdout_files([extra_f], sb_oh, set(), prod_exists=True))
    return sb_oh


def _assert_holdout_extra_and_prod_lock_checks(tmp_path: Path) -> None:
    sb_oh = _assert_holdout_suite_and_sb_diffs(tmp_path)
    assert (dast_holdout._resolve_lock_rel_target("oracle_lock.json", "/other/ws/scripts", tmp_path, sb_oh), dast_holdout._resolve_lock_rel_target("governance_lock.json", f"/other/{tmp_path.name}", tmp_path, sb_oh)) == (Path("scripts"), Path("."))
    prod_lk = tmp_path / "governance_lock.json"
    (tmp_path / "item.txt").write_text("abc", encoding="utf-8")
    assert "Mismatch produzione" in (dast_holdout._verify_prod_extra_lock("governance_lock.json", prod_lk, tmp_path, {"files": {"item.txt": "0" * 64}, "combined_sha256": "0" * 64}, Path(".")) or "")
    good_sha = compute_lf_sha256(tmp_path / "item.txt")
    assert "combined_sha256" in (dast_holdout._verify_prod_extra_lock("governance_lock.json", prod_lk, tmp_path, {"files": {"item.txt": good_sha}, "combined_sha256": "0" * 64}, Path(".")) or "")


@pytest.mark.fast
def test_dast_holdout_profile_and_asset_corruption_checks(tmp_path: Path) -> None:
    """Esercita holdout_verify.py su asset mancanti/corrotti, extra holdout e _resolve_lock_rel_target."""
    bad_prof = run_staging_shadow_verification(repo_root=tmp_path, run_pytest=False, run_ast_guard=False, profile="builder", verify_holdout=True)
    assert (bad_prof["passed"], "evaluator" in bad_prof["error"]) == (False, True)

    broken_sb = tmp_path / "broken_holdout_sb"
    (broken_sb / "nk_tracking" / "benchmark_suite").mkdir(parents=True)
    (broken_sb / "tests" / "evals").mkdir(parents=True)
    (broken_sb / "nk_tracking" / "oracle_lock.json").write_text("{bad", encoding="utf-8")
    (broken_sb / "tests" / "evals" / "skill_golden_eval_set.json").write_text("{bad", encoding="utf-8")
    holdout_err = dast_holdout.verify_sandbox_holdouts(broken_sb, broken_sb, "evaluator", ["tests/evals/skill_golden_eval_set.json"], ["tests/t.py"])
    assert (holdout_err["passed"], len(holdout_err["errors"]) >= 3) == (False, True)
    assert dast_holdout.verify_sandbox_holdouts(broken_sb, broken_sb, "builder", [], [])["passed"] is False
    _assert_holdout_extra_and_prod_lock_checks(tmp_path)


def _assert_traced_cmd_extra_variants(tmp_path: Path, sb: Path, env: Dict[str, str], cov_out: Path) -> None:
    for bad_cmd in ([sys.executable, "C:/Windows/Temp/evil.py"], [sys.executable, "/outside/evil.py"], [sys.executable, "../evil.py"], [sys.executable, "../target.py"], ["../evil.py"], ["C:/Windows/Temp/evil.py"]):
        with pytest.raises(ValueError):
            dast_proc.build_traced_command(sb, bad_cmd, "target.py", True, env, cov_out)
    outside_txt = tmp_path / "outside.txt"
    outside_txt.write_text("ok", encoding="utf-8")
    assert dast_proc.build_traced_command(sb, [sys.executable, str(outside_txt), "--x"], "target.py", True, env, cov_out)[-3:] == [str((sb / "target.py").resolve()), str(outside_txt), "--x"]
    assert dast_proc.build_traced_command(sb, [sys.executable, "runner_no_ext", "--y"], "target.py", True, env, cov_out)[-2:] == [str((sb / "runner_no_ext").resolve()), "--y"]
    assert dast_proc.build_traced_command(sb, [sys.executable, "-B"], "target.py", True, env, cov_out)[-1] == str((sb / "target.py").resolve())
    assert dast_proc.build_traced_command(sb, [sys.executable, "no_such_cmd", "--z"], "target.py", True, env, cov_out)[-3:] == [str((sb / "target.py").resolve()), "no_such_cmd", "--z"]
    assert dast_proc.build_traced_command(sb, [sys.executable, str(sb), "--w"], "target.py", True, env, cov_out)[-3:] == [str((sb / "target.py").resolve()), str(sb), "--w"]
    assert dast_proc.build_traced_command(sb, [], "target.py", True, env, cov_out)[-1] == str((sb / "target.py").resolve())
    assert dast_proc.build_traced_command(sb, ["python", "target.py", "--p"], "target.py", True, env, cov_out)[-2:] == [str((sb / "target.py").resolve()), "--p"]


@pytest.mark.fast
def test_dast_process_runner_paths_and_traced_cmd_confinement(tmp_path: Path) -> None:
    """Valida resolve_dast_report_path, build_traced_command e confinamento entrypoint."""
    rep_dir = tmp_path / "reports"
    rep_dir.mkdir(parents=True)
    assert (resolve_dast_report_path(tmp_path, rep_dir).parent, resolve_dast_report_path(tmp_path, str(tmp_path / "sub") + "/").name.startswith("dast_report_"), resolve_dast_report_path(tmp_path, tmp_path / "exact.json"), resolve_dast_report_path(tmp_path, "   ").name.startswith("dast_report_")) == (rep_dir, True, tmp_path / "exact.json", True)

    sb = (tmp_path / "sb_trace").resolve()
    sb.mkdir(parents=True)
    for fn, txt in (("target.py", "print('t')\n"), ("other.py", "print('o')\n"), ("runner_no_ext", "print('n')\n")):
        (sb / fn).write_text(txt, encoding="utf-8")
    cov_out, env = sb / "cov.json", {}
    assert dast_proc.build_traced_command(sb, ["echo"], "target.py", False, env, cov_out) == ["echo"]
    assert dast_proc.build_traced_command(sb, [sys.executable, "-B", "target.py", "--a"], "target.py", True, env, cov_out)[-2:] == [str((sb / "target.py").resolve()), "--a"]
    assert dast_proc.build_traced_command(sb, [sys.executable, "other.py", "--b"], "target.py", True, env, cov_out)[-2:] == [str((sb / "other.py").resolve()), "--b"]
    assert dast_proc.build_traced_command(sb, [sys.executable, "--c"], "target.py", True, env, cov_out)[-1] == "--c"
    assert dast_proc.build_traced_command(sb, ["target.py", "--d"], "target.py", True, env, cov_out)[-2:] == [str((sb / "target.py").resolve()), "--d"]
    assert dast_proc.build_traced_command(sb, ["other.py", "--e"], "target.py", True, env, cov_out)[-2:] == [str((sb / "other.py").resolve()), "--e"]
    assert dast_proc.build_traced_command(sb, ["--f"], "target.py", True, env, cov_out)[-1] == "--f"
    _assert_traced_cmd_extra_variants(tmp_path, sb, env, cov_out)


@pytest.mark.fast
def test_p2_hardening_oracle_holdout_protection(tmp_path: Path) -> None:
    """Valida la protezione completa degli asset nk_tracking/oracle_holdout in verify_sandbox_holdouts."""
    for prot in ("nk_tracking/oracle_holdout", "nk_tracking/oracle_holdout/canary.json", "tests/evals"):
        assert dast_holdout._is_protected_holdout_path(prot, include_all_tests=False) is True
        assert dast_holdout._is_protected_holdout_path(prot, include_all_tests=True) is True

    root, sb_dir = tmp_path / "prod_oh_hub", tmp_path / "sb_oh_hub"
    mod_key = f"{chr(46) * 2}/scripts/mod.py"
    _seed_holdout_tree(root, mod_key)
    _seed_holdout_tree(sb_dir, mod_key)
    (root / "nk_tracking" / "oracle_holdout" / "sub").mkdir(parents=True)
    (sb_dir / "nk_tracking" / "oracle_holdout" / "sub").mkdir(parents=True)
    (root / "nk_tracking" / "oracle_holdout" / "h1.json").write_text('{"id": "h1"}\n', encoding="utf-8")
    (sb_dir / "nk_tracking" / "oracle_holdout" / "h1.json").write_text('{"id": "h1"}\n', encoding="utf-8")
    (root / "nk_tracking" / "oracle_holdout" / "notes.txt").write_text("ok\n", encoding="utf-8")
    (sb_dir / "nk_tracking" / "oracle_holdout" / "notes.txt").write_text("ok\n", encoding="utf-8")

    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is True
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", ["nk_tracking/oracle_holdout/h1.json"], [])["passed"] is False
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], ["nk_tracking/oracle_holdout/h1.json"])["passed"] is False
    (sb_dir / "nk_tracking" / "oracle_holdout" / "h1.json").write_text('{"id": "tampered"}\n', encoding="utf-8")
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is False
    (sb_dir / "nk_tracking" / "oracle_holdout" / "h1.json").write_text("{bad", encoding="utf-8")
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is False
    (sb_dir / "nk_tracking" / "oracle_holdout" / "h1.json").unlink()
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is False
    shutil.rmtree(sb_dir / "nk_tracking" / "oracle_holdout")
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is False
    shutil.rmtree(root / "nk_tracking" / "oracle_holdout")
    (sb_dir / "nk_tracking" / "oracle_holdout").mkdir(parents=True)
    (sb_dir / "nk_tracking" / "oracle_holdout" / "good.json").write_text('{"ok": true}\n', encoding="utf-8")
    (sb_dir / "nk_tracking" / "oracle_holdout" / "bad.json").write_text("{bad", encoding="utf-8")
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is False


@pytest.mark.fast
def test_wave1_fail_closed_holdout_without_tasks_v1_and_poc_classification(tmp_path: Path) -> None:
    """Valida holdout fail-closed senza tasks_v1.json in produzione e classificazione DAST PoC."""
    root = tmp_path / "no_v1_hub"
    sb_dir = tmp_path / "no_v1_sb"
    for base in (root, sb_dir):
        (base / "tests" / "evals").mkdir(parents=True)
        (base / "nk_tracking" / "benchmark_suite").mkdir(parents=True)
        (base / "tests" / "evals" / "skill_golden_eval_set.json").write_text('{"skills": []}\n', encoding="utf-8")
        (base / "nk_tracking" / "benchmark_suite" / "tasks_builder_v2.json").write_text('{"tasks": []}\n', encoding="utf-8")
        fmap = {"evals/skill_golden_eval_set.json": compute_lf_sha256(base / "tests" / "evals" / "skill_golden_eval_set.json")}
        (base / "nk_tracking" / "oracle_lock.json").write_text(
            json.dumps({"target": (base / "tests").resolve().as_posix(), "files": fmap, "combined_sha256": compute_combined_sha256(fmap)}),
            encoding="utf-8",
        )

    assert dast_holdout._check_required_holdout_assets(sb_dir) == []
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is True
    (sb_dir / "nk_tracking" / "benchmark_suite" / "tasks_builder_v2.json").unlink()
    assert dast_holdout.verify_sandbox_holdouts(root, sb_dir, "evaluator", [], [])["passed"] is False

    assert dast_cli.classify_poc_outcome(0, "ok", "") == "REFUTED"
    assert dast_cli.classify_poc_outcome(1, "", "ModuleNotFoundError: No module named 'x'") == "HARNESS_ERROR"
    assert dast_cli.classify_poc_outcome(1, "", "SyntaxError: invalid syntax") == "HARNESS_ERROR"
    assert dast_cli.classify_poc_outcome(1, "", "AssertionError: exploit") == "EXPLOIT_CONFIRMED"
    assert dast_cli.classify_poc_outcome(0, "", "", timed_out=True) == "EXPLOIT_CONFIRMED"
    assert dast_cli.classify_poc_outcome(0, "", "", memory_exceeded=True) == "EXPLOIT_CONFIRMED"


def _assert_win32_job_k32_and_psapi_branches(monkeypatch: pytest.MonkeyPatch, closed_h: List[Any], killed_pids: List[tuple[int, int]]) -> None:
    monkeypatch.setattr(dast_mod, "sys", SimpleNamespace(platform="win32"))
    k32_invalid = SimpleNamespace(
        CreateJobObjectW=lambda *_a: dast_const.INVALID_HANDLE_VALUE,
        CreateToolhelp32Snapshot=lambda *_a: dast_const.INVALID_HANDLE_VALUE,
    )
    monkeypatch.setattr(dast_mod, "_kernel32", k32_invalid)
    assert (dast_job._create_kill_on_close_job(), dast_job._resume_process_primary_thread(77)) == (None, False)

    k32_fail_set = SimpleNamespace(CreateJobObjectW=lambda *_a: 42, SetInformationJobObject=lambda *_a: 0, CloseHandle=lambda h: closed_h.append(h))
    monkeypatch.setattr(dast_mod, "_kernel32", k32_fail_set)
    assert (dast_job._create_kill_on_close_job(), len(closed_h)) == (None, 1)

    k32_assign_fail = SimpleNamespace(
        CreateJobObjectW=lambda *_a: 99, SetInformationJobObject=lambda *_a: 1, OpenProcess=lambda *_a: 0,
        CloseHandle=lambda h: closed_h.append(h), CreateToolhelp32Snapshot=lambda *_a: 11, Process32First=lambda *_a: 0,
        K32GetProcessMemoryInfo=lambda *_a: (_ for _ in ()).throw(OSError("no_k32_mem")),
    )
    psapi_calls: List[int] = []
    monkeypatch.setattr(dast_mod, "_kernel32", k32_assign_fail)
    monkeypatch.setattr(dast_mod, "_psapi", SimpleNamespace(GetProcessMemoryInfo=lambda *_a: psapi_calls.append(1) or 0))
    monkeypatch.setattr(dast_mod, "_HAS_PSUTIL", False)
    assert (dast_job._assign_to_kill_on_close_job(77), dast_job._terminate_process_tree_fallback(77), killed_pids) == (None, 2, [(77, 9), (77, 9)])

    monkeypatch.setattr(dast_mod, "_kernel32", SimpleNamespace(CreateToolhelp32Snapshot=lambda *_a: 11, Process32First=lambda *_a: 0, OpenProcess=lambda *_a: 55, CloseHandle=lambda h: closed_h.append(h), K32GetProcessMemoryInfo=lambda *_a: 0))
    assert (dast_job._get_process_memory_rss(77, rss_state=dast_const._RSSMonitorState()), psapi_calls) == (0, [1])


@pytest.mark.fast
def test_dast_win32_job_mocked_handles_and_rss_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre win32_job.py con fake kernel32/psapi/psutil deterministici e RSS fallback."""
    assert (dast_mod._assign_to_kill_on_close_job(0), dast_mod._terminate_process_tree_fallback(0), dast_job._resume_process_primary_thread(0)) == (None, 0, False)

    closed_h: List[Any] = []
    killed_pids: List[tuple[int, int]] = []
    monkeypatch.setattr(dast_mod, "time", SimpleNamespace(perf_counter=lambda: 1.0, sleep=lambda _s: None))
    monkeypatch.setattr(dast_mod, "os", SimpleNamespace(kill=lambda p, s: killed_pids.append((p, s))))
    monkeypatch.setattr(dast_mod, "sys", SimpleNamespace(platform="linux"))
    assert (dast_job._create_kill_on_close_job(), dast_job._assign_pid_to_job(42, 77), dast_job._resume_process_primary_thread(77), dast_job._terminate_process_tree_fallback(77)) == (None, False, False, 0)

    _assert_win32_job_k32_and_psapi_branches(monkeypatch, closed_h, killed_pids)
    monkeypatch.setattr(dast_mod, "_HAS_PSUTIL", True)
    fake_p = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=1000),
        children=lambda recursive=True: [SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=500))],
    )
    assert dast_job._get_process_memory_rss(77, p_process=fake_p) == 1500


async def _run_watchdog_cases() -> tuple[bool, bool, bool]:
    with ShadowSandbox() as sb:
        sb.write_file("hang.py", "import time\nwhile True:\n    time.sleep(0.02)\n")
        rep_to = await DASTSandboxRunner(SandboxConfig(timeout_sec=0.09, poll_interval_sec=0.01)).run_in_sandbox(sb, [sys.executable, "hang.py"])
        sb.write_file("mem.py", 'import time\nb = bytearray(b"X" * (70 * 1024 * 1024))\ntime.sleep(0.03)\n')
        rep_mem = await DASTSandboxRunner(SandboxConfig(timeout_sec=2.0, max_memory_mb=25.0, poll_interval_sec=0.01)).run_in_sandbox(sb, [sys.executable, "mem.py"])
        sb.write_file("tree.py", 'import subprocess, sys, time\nsubprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])\ntime.sleep(5)\n')
        rep_tree = await DASTSandboxRunner(SandboxConfig(timeout_sec=0.10, poll_interval_sec=0.01)).run_in_sandbox(sb, [sys.executable, "tree.py"])
        return (rep_to.timed_out and not rep_to.success, bool(rep_mem.memory_exceeded or not rep_mem.success), bool(rep_tree.timed_out or not rep_tree.success))


@pytest.mark.integration
def test_dast_watchdog_timeout_memory_and_taskkill_integration() -> None:
    """Valida interruzione timeout, tetto memoria e taskkill /F /T albero figli in sandbox reale."""
    assert asyncio.run(_run_watchdog_cases()) == (True, True, True)


@pytest.mark.integration
def test_wave1a_ntfs_junction_reparse_entry_blocked(tmp_path: Path) -> None:
    """Verifica blocco reale NTFS junction / reparse point con _is_reparse_entry."""
    outside = tmp_path / "outside_target"
    outside.mkdir()
    (outside / "secret.py").write_text("SECRET = 1\n", encoding="utf-8")
    stg = tmp_path / "ws" / ".staging"
    stg.mkdir(parents=True)
    junction = stg / "evil_junction"
    if sys.platform == "win32":
        assert subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, text=True, check=False).returncode == 0
    else:
        junction.symlink_to(outside, target_is_directory=True)
    try:
        assert itr_mod._is_reparse_entry(junction) is True and dast_overlay._is_blocked_reparse(junction, stg.resolve()) is True
        with pytest.raises(ValueError, match="junction|Symlink"):
            dast_overlay._collect_safe_staging_files(stg, stg.resolve())
    finally:
        if junction.exists() or itr_mod._is_reparse_entry(junction):
            if sys.platform == "win32" and junction.is_dir() and not junction.is_symlink():
                os.rmdir(junction)
            else:
                junction.unlink(missing_ok=True)


@pytest.mark.integration
def test_wave1a_process_runner_closes_win32_job_handle_without_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica _close_handle_ref idempotente e chiusura handle Job Object Win32 senza leak."""
    closed_ids: List[int] = []
    ref: List[int | None] = [77]
    dast_proc._close_handle_ref(ref, closed_ids.append)
    dast_proc._close_handle_ref(ref, closed_ids.append)
    assert ref == [None] and closed_ids == [77]

    created_handles, closed_handles = [], []
    orig_create, orig_close = dast_job._create_kill_on_close_job, dast_job._close_job_handle_safe
    monkeypatch.setattr(dast_mod, "_create_kill_on_close_job", lambda: (h := orig_create(), created_handles.append(h) if h is not None else None)[0], raising=False)
    monkeypatch.setattr(dast_mod, "_close_job_handle_safe", lambda h: (closed_handles.append(h), orig_close(h))[1], raising=False)
    res = dast_proc._run_job_isolated_subprocess([sys.executable, "-B", "-c", "print('job_ok')"], cwd=tmp_path, env=dict(os.environ), timeout_sec=5.0)
    assert res.returncode == 0 and "job_ok" in res.stdout and closed_handles == created_handles


def _assert_dast_cli_script_and_overlay_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    script_ws = tmp_path / "cli_script_ws"
    (script_ws / "scripts").mkdir(parents=True)
    tiny_py = script_ws / "scripts" / "tiny_run.py"
    tiny_py.write_text("import sib_mod\nprint('cli_script_ok', sib_mod.VAL)\n", encoding="utf-8")
    (script_ws / "scripts" / "sib_mod.py").write_text("VAL = 7\n", encoding="utf-8")
    out_rep = tmp_path / "script_rep.json"
    capsys.readouterr()
    assert (dast_cli.main(["--script", str(tiny_py), "--profile", "builder", "--output", str(out_rep), "--json"]), json.loads(capsys.readouterr().out)["success"], out_rep.is_file()) == (0, True, True)
    assert (dast_cli.main(["--script", str(tiny_py), "--profile", "evaluator", "--report-to-tracking"]), "[DAST-SANDBOX] Success: True" in capsys.readouterr().out, bool(list((script_ws / "nk_tracking").glob("dast_report_*.json")))) == (0, True, True)

    fast_hub = tmp_path / "fast_guard_hub"
    (fast_hub / "scripts").mkdir(parents=True)
    (fast_hub / "scripts" / "ast_guard_validator.py").write_text("import sys; print('PASS'); sys.exit(0)\n", encoding="utf-8")
    monkeypatch.setattr(dast_mod, "__file__", str(fast_hub / "scripts" / "dast_sandbox_runner.py"))
    ov_ws = tmp_path / "cli_ov_ws"
    (ov_ws / "scripts").mkdir(parents=True)
    (ov_ws / ".staging" / "scripts").mkdir(parents=True)
    (ov_ws / "scripts" / "clean.py").write_text("def ok(x: int) -> int:\n    return x\n", encoding="utf-8")
    (ov_ws / ".staging" / "scripts" / "clean.py").write_text("def ok(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    ov_out = tmp_path / "ov_rep.json"
    assert (dast_cli.main(["--overlay-staging", str(ov_ws), "--staging-dir", str(ov_ws / ".staging"), "--profile", "builder", "--output", str(ov_out), "--json"]), json.loads(capsys.readouterr().out)["passed"]) == (0, True)
    assert (dast_cli.main(["--overlay-staging", str(tmp_path / "absent_ov"), "--profile", "evaluator"]), "[DAST-OVERLAY-STAGING] Status: FAIL" in capsys.readouterr().out) == (1, True)


@pytest.mark.integration
def test_dast_cli_script_overlay_and_rss_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica RSS cache, CLI --script / --overlay-staging su builder/evaluator e Shadow Verification."""
    assert isolated_nk_env.is_dir()
    rss_state = dast_mod._RSSMonitorState()
    rss1 = _get_process_memory_rss(os.getpid(), rss_state=rss_state)
    assert (rss1 >= 0, _get_process_memory_rss(os.getpid(), rss_state=rss_state), rss_state.record_sample(1234)) == (True, rss1, max(rss_state.get_peak(), 1234))
    assert (DASTSandboxRunner().kill_process_tree(proc=None, parent=None), run_staging_shadow_verification(tmp_path / "nonexistent_root")["status"]) == (True, "FAIL")

    mini_repo = tmp_path / "mini_repo"
    (mini_repo / "scripts").mkdir(parents=True)
    (mini_repo / ".staging" / "scripts").mkdir(parents=True)
    (mini_repo / "scripts" / "old.py").write_text("OLD = 1\n", encoding="utf-8")
    (mini_repo / ".staging" / "scripts" / "new.py").write_text("NEW = 2\n", encoding="utf-8")
    (mini_repo / ".staging" / ".deleted_files.json").write_text('{"deleted_files": ["scripts/old.py"]}', encoding="utf-8")
    ver_res = run_staging_shadow_verification(repo_root=mini_repo, run_pytest=False, run_ast_guard=True, profile="builder")
    assert (ver_res["passed"], "scripts/new.py" in ver_res["overlay_files"], "scripts/old.py" in ver_res["deleted_files"], Path(ver_res["sandbox_dir"]).exists()) == (True, True, True, False)
    _assert_dast_cli_script_and_overlay_flags(tmp_path, monkeypatch, capsys)


def _assert_dast_fuzzer_cov_and_alt_entry(tmp_path: Path) -> None:
    assert dast_fuzzer._parse_coverage_traces(tmp_path / "missing.json") == ([], [])
    bad_cov, good_cov = tmp_path / "bad_cov.json", tmp_path / "good_cov.json"
    bad_cov.write_text("{corrupt", encoding="utf-8")
    good_cov.write_text(json.dumps([{"file_name": "b.py", "line_number": 5, "execution_count": 1}, {"file_name": "a.py", "line_number": 2, "execution_count": 3}]), encoding="utf-8")
    traces, stmts = dast_fuzzer._parse_coverage_traces(good_cov)
    assert (dast_fuzzer._parse_coverage_traces(bad_cov), [t.file_name for t in traces], stmts) == (([], []), ["a.py", "b.py"], ["a.py:2", "b.py:5"])

    with ShadowSandbox() as sb2:
        (sb2.sandbox_dir / "main_entry.py").write_text("A = 1\n", encoding="utf-8")
        (sb2.sandbox_dir / "alt_entry.py").write_text("B = 2\nprint(B)\n", encoding="utf-8")
        assert asyncio.run(DASTSandboxRunner(SandboxConfig(profile="default", trace_coverage=True, timeout_sec=15.0)).run_in_sandbox(sb2, ["alt_entry.py", "--flag"], target_script_name="main_entry.py")).exit_code == 0


def _assert_dast_e2e_ast_and_pytest_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _time

    empty_hub = tmp_path / "no_guard_hub"
    (empty_hub / "scripts").mkdir(parents=True)
    with monkeypatch.context() as mp_e2e:
        mp_e2e.setattr(dast_mod, "__file__", str(empty_hub / "scripts" / "dast_sandbox_runner.py"))
        assert dast_e2e._run_ast_guard_on_sandbox(tmp_path, {}, 2.0, subprocess.run, sys) == {"executed": False, "passed": True}
        (empty_hub / "scripts" / "ast_guard_validator.py").write_text("import sys\nprint('- [SYNTAX_ERROR] L1: bad')\nsys.exit(1)\n", encoding="utf-8")
        mini_ws = tmp_path / "e2e_fail_ws"
        (mini_ws / "scripts").mkdir(parents=True)
        (mini_ws / ".staging" / "scripts").mkdir(parents=True)
        (mini_ws / ".staging" / "scripts" / "broken_ast.py").write_text("def bad(:\n", encoding="utf-8")
        rep_fail = run_staging_shadow_verification(repo_root=mini_ws, run_pytest=False, run_ast_guard=True, profile="builder")
        assert (rep_fail["passed"], rep_fail["ast_guard"]["passed"], "stderr_tail" in rep_fail) == (False, False, True)

    no_tests_res = dast_e2e._run_pytest_on_sandbox(tmp_path / "empty_sb", {}, 2.0, dast_proc._run_job_isolated_subprocess, sys, _time)
    sb_with_tests = tmp_path / "sb_tests_only"
    (sb_with_tests / "tests").mkdir(parents=True)
    assert (no_tests_res["passed"], no_tests_res["exit_code"]) == (False, 5)
    assert dast_e2e._run_pytest_on_sandbox(sb_with_tests, {}, 2.0, lambda cmd, **_k: subprocess.CompletedProcess(args=cmd, returncode=0, stdout=".. [100%]\n", stderr=""), sys, _time)["tests_passed"] == 2
    assert dast_e2e._run_pytest_on_sandbox(sb_with_tests, {}, 2.0, lambda cmd, **_k: subprocess.CompletedProcess(args=cmd, returncode=5, stdout="", stderr=""), sys, _time)["no_tests_collected"] is True


@pytest.mark.integration
def test_dast_fuzzer_trace_and_e2e_audit_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Esercita trace_coverage, lifecycle/mirroring, fuzzer evaluator e e2e_and_audit su AST/pytest."""
    with ShadowSandbox() as sb_life:
        assert "nk_sandbox_" in str(sb_life.sandbox_dir)
        assert sb_life.write_file("nested/module.py", "X = 42\n").read_text(encoding="utf-8") == "X = 42\n"
        sb_life.write_file("calc_test.py", "def calc(a, b):\n    return a + b\ncalc(10, 20)\n")
        rep_life = asyncio.run(DASTSandboxRunner(SandboxConfig(timeout_sec=3.0, trace_coverage=True)).run_in_sandbox(sb_life, [sys.executable, "calc_test.py"], target_script_name="calc_test.py"))
        assert rep_life.success and len(rep_life.executed_statements) > 0
    assert not sb_life.sandbox_dir.exists()

    helper_dir = tmp_path / "eval_pkg"
    helper_dir.mkdir()
    (helper_dir / "eval_helper.py").write_text("VAL = 99\n", encoding="utf-8")
    runner_eval = DASTSandboxRunner(SandboxConfig(timeout_sec=3.0, trace_coverage=False, profile="evaluator", env_vars={"PYTHONPATH": str(helper_dir)}))
    with ShadowSandbox() as sb_e:
        rep_e = asyncio.run(runner_eval.run_in_sandbox(sb_e, [sys.executable, "-B", "-c", "import eval_helper; print(eval_helper.VAL)"]))
        assert (rep_e.success, "99" in rep_e.stdout) == (True, True)
    done_proc = subprocess.Popen([sys.executable, "-B", "-c", "pass"])
    done_proc.wait(timeout=3.0)
    assert runner_eval.kill_process_tree(proc=None, parent=done_proc) is True
    _assert_dast_fuzzer_cov_and_alt_entry(tmp_path)
    _assert_dast_e2e_ast_and_pytest_audit(tmp_path, monkeypatch)

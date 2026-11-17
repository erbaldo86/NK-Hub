# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Sicurezza, 2PC, HookGateV2, ASTGuard, Sandbox e SBFL.
Modulo: tests/test_sovereign_carbon_security_and_2pc.py.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

from conftest import (
    WORKSPACE_ROOT as _WORKSPACE_ROOT,
    call_script_main as _call_main,
    call_script_main_captured as _call_main_captured,
    load_script_by_relpath as _load_mod,
)

w2pc_mod = _load_mod("win32_2pc_engine", "scripts/win32_2pc_engine.py")
w2pc_consts = _load_mod("win32_2pc_constants", "scripts/_internal/win32_2pc_engine/constants.py")
hook_mod = _load_mod("nk_hook_gate", "scripts/nk_hook_gate.py")
guard_mod = _load_mod("ast_guard_validator", "scripts/ast_guard_validator.py")
dast_mod = _load_mod("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
clean_mod = _load_mod("safe_cleanup_dev_servers", "scripts/safe_cleanup_dev_servers.py")
cache_mod = _load_mod("deterministic_api_cache", "scripts/deterministic_api_cache.py")
l3_mod = _load_mod("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
heal_mod = _load_mod("auto_heal_pipeline", "scripts/auto_heal_pipeline.py")
snap_mod = _load_mod("healing_snapshot_rollback", "scripts/healing_snapshot_rollback.py")
inv_mod = _load_mod("invisible_healing_loop", "scripts/invisible_healing_loop.py")
sbfl_mod = _load_mod("sbfl_engine", "scripts/sbfl_engine.py")
bridge_mod = _load_mod("sbfl_pytest_bridge", "scripts/sbfl_pytest_bridge.py")


@pytest.mark.integration
def test_batch_journal_v2_os_exit_9_crash_recovery_5_files(tmp_path: Path) -> None:
    """Oracolo 3a: verifica ripristino atomico su batch di 5 file interrotto da os._exit(9)."""
    repo = tmp_path / "crash_repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".staging" / "scripts").mkdir(parents=True)
    originals = {}
    for idx in range(4):
        rel = f"scripts/mod_{idx}.py"
        orig_bytes = f"# original_v{idx}\nVALUE = {idx}\n".encode("utf-8")
        (repo / rel).write_bytes(orig_bytes)
        originals[rel] = orig_bytes
    crash_driver = tmp_path / "crash_driver.py"
    w2pc_file = Path(w2pc_mod.__file__).resolve()
    crash_driver.write_text(
        "import importlib.util, os, pathlib\n"
        f"spec = importlib.util.spec_from_file_location('w2pc', r'{w2pc_file}')\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"root = pathlib.Path(r'{repo}')\n"
        "targets = [(f'scripts/mod_{i}.py', root / f'scripts/mod_{i}.py') for i in range(5)]\n"
        "m.BatchJournalV2.begin_batch(root, targets)\n"
        "for i in range(3):\n"
        "    (root / f'scripts/mod_{i}.py').write_bytes(b'# CORRUPTED_PARTIAL_WRITE\\n')\n"
        "(root / 'scripts/mod_4.py').write_bytes(b'# ORPHAN_UNCREATED_PRE_BATCH\\n')\n"
        "os._exit(9)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_WORKSPACE_ROOT)
    proc = subprocess.run([sys.executable, "-B", str(crash_driver)], env=env, capture_output=True, timeout=15, check=False)
    assert proc.returncode == 9
    assert (repo / "scripts/mod_0.py").read_bytes() != originals["scripts/mod_0.py"]
    assert (repo / "scripts/mod_4.py").exists()
    rec_list, rolled_set = w2pc_mod.BatchJournalV2.recover_crashed_batches(repo)
    assert len(rec_list) >= 1 and len(rolled_set) == 5
    for rel, expected in originals.items():
        assert (repo / rel).read_bytes() == expected
    assert not (repo / "scripts/mod_4.py").exists()


@pytest.mark.fast
def test_win32_2pc_hook_guard_dast_l3_and_heal_e2e(
    tmp_path: Path, monkeypatch: Any, capsys: Any, isolated_nk_env: Path
) -> None:
    """Verifica quarantena 2PC, WAL recovery/corrupt quarantine e create_ipc_pointer."""
    repo = tmp_path / "repo_2pc"
    for d in ("scripts", "nk_tracking", ".staging/scripts", ".staging/nk_tracking"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "obsolete.py").write_text("OLD = 1\n", encoding="utf-8")
    (repo / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_total": {"value": 93}, "unit_tests_passed": {"value": 93}, "unit_tests_pass_pct": {"value": 100.0}}}),
        encoding="utf-8",
    )
    (repo / ".staging" / "scripts" / "leftover.py").write_text("Y = 2\n", encoding="utf-8")
    assert w2pc_mod.get_repo_batch_mutex_name(repo) == w2pc_mod.get_repo_batch_mutex_name(str(repo))
    assert "NK_RepoBatchLock_" in w2pc_mod.get_repo_batch_mutex_name(repo)
    assert _call_main(w2pc_mod, ["--quarantine-staging", "--repo-root", str(repo)], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["quarantined_count"] == 1
    assert not (repo / ".staging" / "scripts" / "leftover.py").exists()
    wal_dir = tmp_path / ".wal"
    wal_mgr = w2pc_mod.WriteAheadLogManager(wal_dir=wal_dir)
    eng = w2pc_mod.TwoPhaseCommitEngine(wal_manager=wal_mgr)
    prep = eng.prepare(tmp_path / "target_doc.txt", "hello_2pc")
    assert eng.abort(prep, reason="unit_abort").verdict == "ABORT"
    ptr = eng.create_ipc_pointer(tmp_path / "blob.bin", b"binary_payload")
    assert ptr.status == "OK" and ptr.pointer_uri.startswith("file:///") and ptr.byte_size == 14
    bad_wal = wal_dir / "corrupt_entry.wal"
    bad_wal.parent.mkdir(parents=True, exist_ok=True)
    bad_wal.write_text("{broken_json", encoding="utf-8")
    rec_res = wal_mgr.recover(tmp_path, stale_age_sec=0.0)
    assert any(item.get("action") == "QUARANTINED_CORRUPT" for item in rec_res)
    assert not bad_wal.exists()


@pytest.mark.fast
def test_sec_hook_gate_evasion_and_staging_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica blocco vettori evasivi S2, allow in .staging e fail-closed JSON invalido."""
    proj = tmp_path / "nk_proj"
    for d in (".staging/scripts", "scripts", "nk_genome", "nk_tracking"):
        (proj / d).mkdir(parents=True)
    (proj / "nk_genome" / "PATCH_NOTES.md").write_text("# Notes\n", encoding="utf-8")
    (proj / "nk_tracking" / "oracle_lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("NK_ALLOW_GOVERNANCE_OVERRIDE", raising=False)
    evasion_cmds = [
        "Set-Content -Path scripts/evil.py -Value '1'",
        "Write-Output a,b > scripts/out.txt",
        "Remove-Item scripts/important.py",
        "iex 'New-Item prod.py'",
        "powershell -EncodedCommand ZWNobyBoZWxsbw==",
        "cmd /c copy scratch\\a.py scripts\\b.py",
        "robocopy scratch scripts evil.py",
        "python -c \"import io; io.FileIO('scripts/x.py', 'w')\"",
        "[System.IO.StreamWriter]::new('scripts/s.py')",
        "Set-Item -Path scripts/evil2.py -Value 'x'",
        "python scripts/win32_2pc_engine.py --promote-staging --allow-governance-override",
    ]
    for cmd_str in evasion_cmds:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"toolName": "run_command", "toolInput": {"CommandLine": cmd_str}})))
        rc = _call_main(hook_mod, ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)], monkeypatch)
        out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert rc == 0 and out["decision"] == "deny", f"Failed to block: {cmd_str}"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "write_file", "tool_input": {"Path": str(proj / ".staging" / "scripts" / "ok.py")}})))
    assert _call_main(hook_mod, ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "allow"
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not_valid_json"))
    assert _call_main(hook_mod, ["write-gate", "--event", "PreToolUse", "--native-contract", "--project-root", str(proj)], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "deny"


@pytest.mark.fast
def test_sec_hook_gate_session_start_integrity_and_stop_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica SessionStart native contract, integrity check e stop-evidence."""
    proj = tmp_path / "nk_proj_ss"
    (proj / ".staging" / "scripts").mkdir(parents=True)
    (proj / "scripts").mkdir(parents=True)
    spawned: List[subprocess.Popen[Any]] = []
    real_popen = subprocess.Popen

    def _track_popen(
        cmd: Any,
        cwd: Any = None,
        stdin: Any = None,
        stdout: Any = None,
        stderr: Any = None,
        close_fds: bool = True,
        creationflags: int = 0,
        start_new_session: bool = False,
    ) -> subprocess.Popen[Any]:
        if sys.platform == "win32":
            p = real_popen(
                cmd,
                cwd=cwd,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                close_fds=close_fds,
                creationflags=creationflags,
            )
        else:
            p = real_popen(
                cmd,
                cwd=cwd,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                close_fds=close_fds,
                start_new_session=start_new_session,
            )
        spawned.append(p)
        return p

    monkeypatch.setattr(subprocess, "Popen", _track_popen)
    try:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        assert _call_main(hook_mod, ["session-start", "--event", "SessionStart", "--native-contract", "--conversation-id", "conv_carbon_t1", "--project-root", str(proj)], monkeypatch) == 0
        assert "systemMessage" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["injectSteps"][0]
        assert _call_main(hook_mod, ["integrity", "--check", "--conversation-id", "conv_carbon_t1", "--project-root", str(proj)], monkeypatch) == 0
        int_out = capsys.readouterr().out
        assert "PASS" in int_out or "OK" in int_out or "status" in int_out.lower()
        for _ in range(2):
            monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"content": "Status: CONVERGED_OPTIMAL", "verifiedExitZero": False})))
            assert _call_main(hook_mod, ["stop-evidence", "--event", "Stop", "--native-contract", "--enforce-stop", "--conversation-id", "conv_carbon_stop", "--project-root", str(proj)], monkeypatch) == 0
            assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "continue"
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"last_assistant_message": "Status: 100% PASS", "verifiedExitZero": True})))
        assert _call_main(hook_mod, ["stop-evidence", "--event", "Stop", "--native-contract", "--enforce-stop", "--conversation-id", "conv_carbon_stop", "--project-root", str(proj)], monkeypatch) == 0
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["decision"] == "allow"
    finally:
        for proc in spawned:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)


@pytest.mark.fast
def test_sec_ast_guard_dast_cleanup_and_api_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], isolated_nk_env: Path
) -> None:
    """Verifica AST Guard CLI, DAST overlay/script, safe_cleanup e DeterministicApiCache."""
    assert _call_main_captured(guard_mod, ["--stage-dir", str(tmp_path / "missing_stg")])[0] == 2
    clean_stg = tmp_path / "clean_staging"
    (clean_stg / "scripts").mkdir(parents=True)
    (clean_stg / "scripts" / "pure.py").write_text("def compute(x: int) -> int:\n    fn = lambda v: v + 1\n    return fn(x)\n", encoding="utf-8")
    rc_ag, out_ag, _ = _call_main_captured(guard_mod, ["--stage-dir", str(clean_stg), "--json"])
    assert rc_ag == 0 and json.loads(out_ag)["passed"] is True
    bad_dir = tmp_path / "src"
    bad_dir.mkdir(parents=True)
    tok_ev, tok_pytest = "ev" + "al", "PYTEST_" + "CURRENT_TEST"
    (bad_dir / "bad_app.py").write_text(
        f"import os\nx = os.environ.get('{tok_pytest}')\ngrants = [1, 2]\nif len(grants) >= 12:\n    pass\nk = '{tok_ev[::-1]}'[::-1]\n",
        encoding="utf-8",
    )
    assert _call_main(guard_mod, ["--target", str(bad_dir)], monkeypatch) != 0
    mini = tmp_path / "mini_hub"
    for d in ("scripts", "data", "tests/evals", "nk_tracking", ".staging/scripts"):
        (mini / d).mkdir(parents=True)
    (mini / "nk_tracking" / "oracle_lock.json").write_text("{}", encoding="utf-8")
    (mini / "tests" / "evals" / "secret.json").write_text("{}", encoding="utf-8")
    (mini / "scripts" / "obsolete.py").write_text("OLD = 1\n", encoding="utf-8")
    (mini / ".staging" / ".deleted_files.json").write_text('["scripts/obsolete.py"]', encoding="utf-8")
    (mini / "scripts" / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    (mini / ".staging" / "scripts" / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b + 0\n", encoding="utf-8")
    (mini / "tests" / "test_calc.py").write_text("from scripts.calc import add\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    res = dast_mod.run_staging_shadow_verification(repo_root=mini, run_pytest=False, run_ast_guard=False, profile="builder", timeout_sec=30.0)
    assert res["passed"] is True and res["sandbox_cleaned"] is True and len(res["stripped_holdouts"]) >= 1
    hello_script = tmp_path / "tiny_script.py"
    hello_script.write_text("print('OK_SANDBOX')\n", encoding="utf-8")
    out_rep = tmp_path / "dast_out.json"
    assert _call_main(dast_mod, ["--script", str(hello_script), "--profile", "builder", "--output", str(out_rep), "--json"], monkeypatch) == 0 and out_rep.exists()
    assert clean_mod.parse_ports_arg("8001, 8002, invalid") == [8001, 8002]
    monkeypatch.setattr(clean_mod, "_HAS_PSUTIL", False)
    assert clean_mod.is_target_workspace_process(999999, tmp_path) is False
    assert _call_main(clean_mod, ["--dry-run", "--ports", "59998", "--workspace-root", str(tmp_path), "--json"], monkeypatch) == 0
    with cache_mod.DeterministicApiCache(db_path=tmp_path / "api_cache.sqlite3", ttl_seconds=60.0) as api_cache:
        api_cache.set("/v1/ep", 200, '{"result": "cached_val"}', method="GET", params={"k": 1}, headers={"Content-Type": "application/json"})
        hit = api_cache.get("/v1/ep", method="GET", params={"k": 1})
        assert hit is not None and hit[0] == 200 and "cached_val" in hit[1]
        assert api_cache.get("/v1/ep", method="GET", params={"k": 1}, force_refresh=True) is None
        assert api_cache.get("/v1/missing", method="GET", params={}) is None
        assert api_cache.get_stats()["entries"] == 1 and api_cache.clear() == 1


@pytest.mark.fast
def test_sec_oracle_l3_auto_heal_snapshots_and_sbfl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Verifica Oracle L3 LFI/HTML5, HealingSnapshotManager, normalize_test_command e SBFL."""
    secret_cfg = tmp_path / "secret.json"
    secret_cfg.write_text('{"token":"x"}', encoding="utf-8")
    with pytest.raises(ValueError):
        l3_mod._read_validated_html_file(str(secret_cfg))
    with pytest.raises(ValueError):
        l3_mod._read_validated_html_file(".." + "/outside.html")
    exp_html, act_html = tmp_path / "expected.html", tmp_path / "actual.html"
    exp_html.write_text("<main><p>Alpha</p><p>Beta</p><ul><li>One</li><li>Two</li></ul></main>", encoding="utf-8")
    act_html.write_text("<main><p>Alpha<p>Beta<ul><li>One<li>Two</ul></main>", encoding="utf-8")
    assert _call_main(l3_mod, ["--expected-file", str(exp_html), "--actual-file", str(act_html), "--json"], monkeypatch) == 0
    orig_trace = sys.gettrace()
    try:
        target_py = tmp_path / "buggy_mod.py"
        raw_bin = b"# -*- coding: utf-8 -*-\ndef f(x):\n    return x + 1\n"
        target_py.write_bytes(raw_bin)
        snap_mgr = snap_mod.HealingSnapshotManager(base_temp_dir=tmp_path / "snaps")
        uncreated_py = tmp_path / "uncreated_mod.py"
        snap_id = snap_mgr.create_snapshot([target_py, uncreated_py])
        target_py.write_bytes(b"def f(x):\n    return 0\n")
        uncreated_py.write_text("TEMP = 1\n", encoding="utf-8")
        snap_mgr.rollback(snap_id)
        assert target_py.read_bytes() == raw_bin and not uncreated_py.exists()
        assert snap_mgr.evaluate_fitness(10, 0, 9, 1, 0).verdict.value == "PASSED"
        assert snap_mgr.evaluate_fitness(8, 1, 9, 1, 1).verdict.value == "REGRESSION"
        assert snap_mgr.evaluate_fitness(9, 2, 9, 1, 1).verdict.value == "REGRESSION"
        assert snap_mgr.evaluate_fitness(10, 1, 9, 2, 1).verdict.value == "IMPROVED"
        assert snap_mgr.evaluate_fitness(9, 1, 9, 1, 1).verdict.value == "NEUTRAL"
        snap_mgr.cleanup(snap_id)
        snap_mgr.cleanup()
        assert heal_mod.classify_failure("SyntaxError: invalid syntax") == "SYNTAX_ERROR"
        assert len(heal_mod.normalize_test_command("pytest tests/test_x.py")) >= 2
        spec_cnt = sbfl_mod.SpectrumCounts(n_ef=4, n_ep=1, n_nf=0, n_np=10)
        assert sbfl_mod.calculate_ochiai(spec_cnt) > 0.7 and sbfl_mod.calculate_tarantula(spec_cnt) > 0.7 and sbfl_mod.calculate_dstar(spec_cnt) > 1.0
        rec_file = tmp_path / "spectrum.json"
        rec_file.write_text(
            json.dumps([
                {"test_id": "T_fail_1", "passed": False, "executed_statements": ['mod"quote.py:12', "other.py:4"]},
                {"test_id": "T_pass_1", "passed": True, "executed_statements": ["other.py:4"]},
            ]),
            encoding="utf-8",
        )
        assert _call_main(sbfl_mod, ["--records-file", str(rec_file), "--json"], monkeypatch) == 0
        if orig_trace is not None:
            assert sys.gettrace() is orig_trace
    finally:
        if sys.gettrace() is None and orig_trace is not None:
            sys.settrace(orig_trace)


@pytest.mark.fast
def test_sec_win32_2pc_wal_constants_and_cli_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Copre rami WAL (NK_WAL_IN_TEMP=0, replay, stale, quarantine collision), constants e CLI error."""
    monkeypatch.setenv("NK_WAL_IN_TEMP", "0")
    wal_mgr = w2pc_mod.WriteAheadLogManager()
    tgt_local = tmp_path / "repo_w" / "a.txt"
    tgt_local.parent.mkdir(parents=True)
    assert wal_mgr.get_wal_path(tgt_local, "tx0").parent == tgt_local.parent / ".wal"
    wal_mgr.update_wal_state(tgt_local, "no_tx", "ABORTED")
    q_dir = tmp_path / "q_wal"
    q_dir.mkdir()
    (q_dir / "quarantine").mkdir()
    (q_dir / "quarantine" / "dup.wal").write_text("old", encoding="utf-8")
    dup_w = q_dir / "dup.wal"
    dup_w.write_text("corrupt", encoding="utf-8")
    q_res = w2pc_mod.WriteAheadLogManager._quarantine_corrupt_wal(dup_w, q_dir)
    assert q_res.parent.name == "quarantine" and q_res.name != "dup.wal" and q_res.exists()
    repo = tmp_path / "wal_rec_repo"
    repo.mkdir()
    wal_r = w2pc_mod.WriteAheadLogManager(wal_dir=repo / ".wal")
    stg_c = tmp_path / "stg_c.txt"
    stg_c.write_text("replayed_ok", encoding="utf-8")
    tgt_c = repo / "committed.txt"
    wal_r.write_wal("tx_c", tgt_c, stg_c, w2pc_consts.compute_sha256(b"replayed_ok"), 0, state="COMMITTED")
    stg_s = tmp_path / "stg_s.txt"
    stg_s.write_text("active", encoding="utf-8")
    wal_r.write_wal("tx_s", repo / "active.txt", stg_s, "0", 0, state="PREPARED")
    stg_a = tmp_path / "stg_a.txt"
    stg_a.write_text("aborted", encoding="utf-8")
    wal_r.write_wal("tx_a", repo / "aborted.txt", stg_a, "0", 0, state="ABORTED")
    (repo / ".wal" / "arr.wal").write_text("[1, 2]", encoding="utf-8")
    (repo / ".wal" / "bad_state.wal").write_text(json.dumps({"target_path": str(tgt_c), "state": "BOGUS"}), encoding="utf-8")
    recs = wal_r.recover(repo, stale_age_sec=9999.0)
    actions = {r.get("action") for r in recs}
    assert {"REPLAYED_COMMIT", "SKIPPED_ACTIVE", "PURGED_ABORTED", "QUARANTINED_CORRUPT"}.issubset(actions)
    assert tgt_c.read_text(encoding="utf-8") == "replayed_ok"
    wal_r.purge_wal(repo / "active.txt", "tx_s")
    assert wal_r.recover(repo, stale_age_sec=0.0) == []
    assert w2pc_consts._get_facade_attr("NONEXISTENT_ATTR_XYZ", "fallback") == "fallback"
    if sys.platform == "win32":
        ctypes.set_last_error(5)
        assert w2pc_consts._get_win32_last_error() == 5
        ctypes.set_last_error(0)
    else:
        err_state = {"code": 0}

        def _fake_set_err(code: int) -> None:
            err_state["code"] = int(code)

        with monkeypatch.context() as mp_err:
            mp_err.setattr(w2pc_consts.ctypes, "set_last_error", _fake_set_err, raising=False)
            mp_err.setattr(w2pc_consts.ctypes, "get_last_error", lambda: err_state["code"], raising=False)
            mp_err.setattr(w2pc_consts, "_get_active_kernel32", lambda: SimpleNamespace(GetLastError=lambda: 0))
            w2pc_consts.ctypes.set_last_error(5)
            assert w2pc_consts._get_win32_last_error() == 5
            w2pc_consts.ctypes.set_last_error(0)
            assert w2pc_consts._get_win32_last_error() == 0
    monkeypatch.setattr(w2pc_consts, "_get_active_kernel32", lambda: None)
    assert w2pc_consts._get_win32_last_error() == 0
    monkeypatch.setattr(w2pc_mod, "quarantine_staging", lambda **_k: (_ for _ in ()).throw(RuntimeError("q_boom")))
    assert _call_main(w2pc_mod, ["--quarantine-staging", "--repo-root", str(repo)], monkeypatch) == 1


@pytest.mark.fast
def test_sec_win32_2pc_engine_commit_abort_and_retry_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path
) -> None:
    """Copre rami abort/mismatch/retry/shadow-swap in win32_2pc_engine/engine.py."""
    import importlib

    eng_mod = importlib.import_module("_internal.win32_2pc_engine.engine")
    wal_mgr = w2pc_mod.WriteAheadLogManager(wal_dir=tmp_path / ".wal_e")
    eng = eng_mod.TwoPhaseCommitEngine(wal_manager=wal_mgr)
    eng.MAX_RETRIES = 2
    monkeypatch.setattr(eng_mod.TwoPhaseCommitEngine, "_backoff_sleep", staticmethod(lambda _a: None))
    tgt = tmp_path / "doc.txt"
    prep_miss = eng.prepare(tgt, "abc")
    Path(prep_miss.staging_path).unlink()
    assert "does not exist" in (eng.commit(prep_miss).reason or "")
    prep_sha = eng.prepare(tgt, "abc")
    Path(prep_sha.staging_path).write_text("xyz", encoding="utf-8")
    assert "SHA-256 mismatch" in (eng.commit(prep_sha).reason or "")
    prep_crc = eng.prepare(tgt, "abc")
    eng.commit(eng_mod._consts.TwoPhaseCommitPrepare(
        transaction_id=prep_crc.transaction_id, target_path=prep_crc.target_path, staging_path=prep_crc.staging_path,
        expected_sha256=prep_crc.expected_sha256, crc32=999999999, timeout_ms=1000, timestamp_utc=time.time(),
    ))
    assert not Path(prep_crc.staging_path).exists()
    fake_k32 = SimpleNamespace(MoveFileExW=lambda *_a: 0, GetLastError=lambda: w2pc_consts.ERROR_SHARING_VIOLATION)
    src_f, dst_f = tmp_path / "src_f.txt", tmp_path / "dst_f.txt"
    src_f.write_text("v2", encoding="utf-8")
    dst_f.write_text("v1", encoding="utf-8")
    real_replace = os.replace
    with monkeypatch.context() as mp:
        mp.setattr(eng_mod._consts, "_get_active_kernel32", lambda: fake_k32)
        mp.setattr(eng_mod._consts, "_get_win32_last_error", lambda: w2pc_consts.ERROR_SHARING_VIOLATION)
        mp.setattr(
            eng_mod.os,
            "replace",
            lambda s, d: (_ for _ in ()).throw(PermissionError("locked"))
            if Path(d) == dst_f and ".shadow_" in Path(s).name
            else real_replace(s, d),
        )
        assert eng._execute_atomic_commit(src_f, dst_f) is False and dst_f.read_text(encoding="utf-8") == "v1"
    monkeypatch.setattr(eng_mod.TwoPhaseCommitEngine, "_execute_atomic_commit", lambda _self, _s, _d: False)
    with pytest.raises(eng_mod._consts.TwoPhaseCommitError):
        eng.create_ipc_pointer(dst_f, "fail_ipc")
    with pytest.raises(eng_mod._consts.TwoPhaseCommitError):
        eng_mod.win32_atomic_replace(src_f, dst_f, max_retries=1)


@pytest.mark.fast
def test_sec_auto_heal_and_invisible_loop_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Copre rami CLI di auto_heal_pipeline e InvisibleHealingLoop."""
    ws = tmp_path / "heal_ws"
    (ws / ".staging").mkdir(parents=True)
    assert _call_main(heal_mod, ["--cwd", str(ws), "--json"], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["cycles_used"] == 0
    assert _call_main(heal_mod, ["--cwd", str(ws)], monkeypatch) == 0
    assert "Clean staging" in capsys.readouterr().out
    stg_py = ws / ".staging" / "demo.py"
    stg_py.write_text("X = 1\n", encoding="utf-8")
    ok_rep = heal_mod.AutoHealSessionReport(
        success=True, cycles_used=1, max_cycles=3, initial_failed=1, final_failed=0, patch_note_line="- Fixed demo.", message="All fixed."
    )
    fail_rep = heal_mod.AutoHealSessionReport(
        success=False, cycles_used=3, max_cycles=3, initial_failed=1, final_failed=1, fault_location="demo.py:1", error_type="AssertionError", message="Failed."
    )
    monkeypatch.setattr(heal_mod.AutoHealPipeline, "run_pipeline", lambda self, **_k: ok_rep)
    assert _call_main(heal_mod, ["--cwd", str(ws)], monkeypatch) == 0
    out_ok = capsys.readouterr().out
    assert "PATCH-NOTE" in out_ok and "Fixed demo" in out_ok
    monkeypatch.setattr(heal_mod.AutoHealPipeline, "run_pipeline", lambda self, **_k: fail_rep)
    assert _call_main(heal_mod, ["--cwd", str(ws), "--target-file", str(stg_py)], monkeypatch) == 1
    assert "demo.py:1" in capsys.readouterr().out
    tel_p = tmp_path / "inv_tel.jsonl"
    loop_no_hook = inv_mod.InvisibleHealingLoop()
    loop_no_hook._record_telemetry("r0", "t0", 1, "PASSED", [])
    loop_with_hook = inv_mod.InvisibleHealingLoop(telemetry_log_path=tel_p)
    loop_with_hook._record_telemetry("r1", "t1", 1, "PASSED", [])
    assert tel_p.is_file() and "r1" in tel_p.read_text(encoding="utf-8")
    monkeypatch.setattr(inv_mod.AutoHealPipeline, "run_pipeline", lambda self, **_k: ok_rep)
    assert _call_main(inv_mod, ["--test-cmd", "pytest -q", "--target-file", str(stg_py), "--cwd", str(ws), "--json"], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["success"] is True
    assert _call_main(inv_mod, ["--test-cmd", "pytest -q", "--target-file", str(stg_py)], monkeypatch) == 0
    assert "All fixed." in capsys.readouterr().out


@pytest.mark.fast
def test_sec_sbfl_monitoring_and_bridge_cover_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre collect_statements_with_monitoring e collect_passed_line_counts in-process."""
    monkeypatch.setattr(sbfl_mod, "is_monitoring_conflict_active", lambda: False)
    callbacks: List[Any] = []
    fake_mon = SimpleNamespace(
        events=SimpleNamespace(LINE=1),
        get_tool=lambda tid: None if tid == 4 else "busy",
        use_tool_id=lambda _tid, _name: None,
        register_callback=lambda _tid, _ev, cb: callbacks.append(cb),
        set_events=lambda _tid, _ev: None,
        free_tool_id=lambda _tid: None,
    )
    monkeypatch.setattr(sbfl_mod, "sys", SimpleNamespace(monitoring=fake_mon))
    def _exercise() -> None:
        cb = callbacks[0]
        cb(SimpleNamespace(co_filename=str(tmp_path / "skip.py")), 5)
        cb(SimpleNamespace(co_filename=str(tmp_path / "target_mod.py")), 12)
    ran, exec_lines = sbfl_mod.collect_statements_with_monitoring(_exercise, target_filename_filter="target_mod.py")
    assert ran is True and any(line.endswith("target_mod.py:12") for line in exec_lines)
    monkeypatch.setattr(bridge_mod, "is_monitoring_conflict_active", lambda: False)
    def _fake_subproc(cmd: List[str], **_k: Any) -> tuple[int, str, str]:
        cov_dir = Path(cmd[cmd.index("-C") + 1])
        (cov_dir / "pkg.target_mod.cover").write_text("    0: def f():\n    3:     return 1\n", encoding="utf-8")
        (cov_dir / "pkg.other_mod.cover").write_text("    1: x = 2\n", encoding="utf-8")
        return 0, "", ""
    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", _fake_subproc)
    br = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    counts = br.collect_passed_line_counts(["tests/test_a.py::test_1"], target_file_hint="target_mod.py")
    assert counts == {("target_mod.py", 2): 1}


@pytest.mark.fast
def test_sec_oracle_l3_implicit_html5_and_lfi_edge_branches(tmp_path: Path) -> None:
    """Copre LFI guards, estensioni bloccate e chiusura implicita HTML5 in oracle_evaluator_l3."""
    assert l3_mod._looks_like_disallowed_file_reference("") is False
    assert l3_mod._looks_like_disallowed_file_reference("a\nb") is False
    assert l3_mod._looks_like_disallowed_file_reference(".env") is True
    assert l3_mod._looks_like_disallowed_file_reference("dir/file") is True
    assert l3_mod._looks_like_disallowed_file_reference("C:\\tmp\\file") is True
    for bad_html in ("", "../bad.html", "note.txt", str(tmp_path / "missing.html")):
        with pytest.raises((ValueError, FileNotFoundError)):
            l3_mod._read_validated_html_file(bad_html)
    for bad_exp in ("", "../bad.md", "secret.py", str(tmp_path / "missing.json")):
        with pytest.raises((ValueError, FileNotFoundError)):
            l3_mod._read_validated_expected_file(bad_exp)
    html_p = tmp_path / "page.html"
    html_p.write_text("<div><span>ok</span></div>", encoding="utf-8")
    assert "<span>ok</span>" in l3_mod.resolve_html_source(str(html_p))
    with pytest.raises(FileNotFoundError):
        l3_mod.resolve_html_source(str(tmp_path / "nope.html"))
    py_p = tmp_path / "evil.py"
    py_p.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        l3_mod.resolve_html_source(str(py_p))
    rich_html = (
        "<ul><li>a<li>b</ul><dl><dt>k1<dt>k2<dd>v1<dd>v2</dl>"
        '<select><optgroup label="g1"><option>1<option>2<optgroup label="g2"><option>3</select>'
        "<table><thead><tr><th>h1<th>h2<tbody><tr><td>c1<td>c2<tfoot><tr><td>f1</table>"
        '<div><p>intro<h1>heading</h1><img src="x"/></br></div>'
    )
    ev = l3_mod.DOMOracleEvaluator()
    assert ev.evaluate_deltas(rich_html, rich_html).verdict == "PASS"


@pytest.mark.fast
def test_sec_snapshot_rollback_manifest_corrupt_and_dast_helpers(tmp_path: Path) -> None:
    """Copre Recovery/Fitness/Rollback in healing_snapshot_rollback e helper DAST di confine/PID."""
    snap_dir = tmp_path / "snap_root"
    snap_dir.mkdir()
    man_p = snap_dir / "snapshot_manifest.json"
    man_p.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt snapshot manifest"):
        snap_mod.HealingSnapshotManager(base_temp_dir=snap_dir)
    man_p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt snapshot manifest"):
        snap_mod.HealingSnapshotManager(base_temp_dir=snap_dir)
    mgr = snap_mod.HealingSnapshotManager(base_temp_dir=tmp_path / "snap_ok")
    f_ex = tmp_path / "existing.txt"
    f_ex.write_text("orig_data", encoding="utf-8")
    f_new = tmp_path / "created_later.txt"
    sid = mgr.create_snapshot([f_ex, f_new])
    f_ex.write_text("mutated", encoding="utf-8")
    f_new.write_text("cleanup_me", encoding="utf-8")
    mgr.active_snapshots[sid].files[str(f_ex.resolve())].content_b64 = ""
    mgr.active_snapshots.clear()
    st_rb = mgr.rollback(sid)
    assert st_rb[str(f_ex.resolve())] is True and f_ex.read_text(encoding="utf-8") == "orig_data"
    assert st_rb[str(f_new.resolve())] is True and not f_new.exists()
    assert mgr.evaluate_fitness(3, 1, 2, 2, 1).verdict == snap_mod.FitnessVerdict.IMPROVED
    assert mgr.evaluate_fitness(2, 0, 2, 0, 1).verdict == snap_mod.FitnessVerdict.REGRESSION
    assert mgr.evaluate_fitness(2, 1, 2, 1, 1).verdict == snap_mod.FitnessVerdict.NEUTRAL
    mgr.cleanup(sid)
    assert sid not in mgr.active_snapshots

    rss_st = dast_mod._RSSMonitorState()
    assert rss_st.record_sample(128) == 128 and rss_st.get_peak() == 128
    sb = tmp_path / "sb_dir"
    sb.mkdir()
    for bad_rel in ("", "bad\x00x", str(sb / "abs.py"), "../escape.py", "."):
        with pytest.raises(ValueError):
            dast_mod._resolve_confined_sandbox_path(sb, bad_rel)
    assert dast_mod._resolve_confined_sandbox_path(sb, "ok.py") == (sb / "ok.py").resolve()
    assert dast_mod.resolve_dast_report_path(tmp_path, "sub/").parent.name == "sub"
    assert dast_mod._assign_to_kill_on_close_job(0) is None
    assert dast_mod._terminate_process_tree_fallback(0) == 0

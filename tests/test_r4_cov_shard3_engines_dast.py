# -*- coding: utf-8 -*-
"""
Suite di copertura rami Round 4 Shard 3 (DAST, Memory 3-Tier, QBM, Oracle L3, Healing, RSI, RepoMap).
Modulo: tests/test_r4_cov_shard3_engines_dast.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import typing
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

try:
    from conftest import call_script_main_captured, load_script_by_relpath
except ImportError:
    from tests.conftest import call_script_main_captured, load_script_by_relpath

_dast_mod = load_script_by_relpath("dast_sandbox_runner", "scripts/dast_sandbox_runner.py")
_mem_mod = load_script_by_relpath("memory_3tier_engine", "scripts/memory_3tier_engine.py")
_qbm_mod = load_script_by_relpath("quality_baseline_manager", "scripts/quality_baseline_manager.py")


@pytest.mark.fast
def test_r4_s3_dast_win32_job_and_thread_fallbacks(monkeypatch: Any) -> None:
    """Copre rami di errore Win32 JobObject e Thread32 in dast_sandbox_runner."""
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.sys, "platform", "linux")
        assert _dast_mod._create_kill_on_close_job() is None
        assert _dast_mod._assign_pid_to_job(1, 2) is False
        assert _dast_mod._resume_process_primary_thread(2) is False
    closed: List[Any] = []
    fake_k32 = SimpleNamespace(
        CreateJobObjectW=lambda _a, _b: 0,
        SetInformationJobObject=lambda *_a: 0,
        CloseHandle=lambda h: closed.append(h),
        OpenProcess=lambda *_a: 0,
        AssignProcessToJobObject=lambda *_a: 1,
        CreateToolhelp32Snapshot=lambda *_a: _dast_mod.INVALID_HANDLE_VALUE,
        Thread32First=lambda *_a: False,
        Thread32Next=lambda *_a: False,
        OpenThread=lambda *_a: 0,
        ResumeThread=lambda *_a: _dast_mod.RESUME_THREAD_ERROR,
    )
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.sys, "platform", "win32")
        mp.setattr(_dast_mod, "_kernel32", fake_k32)
        assert _dast_mod._create_kill_on_close_job() is None
        fake_k32.CreateJobObjectW = lambda _a, _b: 123
        assert _dast_mod._create_kill_on_close_job() is None
        assert len(closed) == 1
        fake_k32.CreateJobObjectW = lambda *_a: (_ for _ in ()).throw(OSError("job"))
        assert _dast_mod._create_kill_on_close_job() is None
        fake_k32.OpenProcess = lambda *_a: (_ for _ in ()).throw(OSError("op"))
        assert _dast_mod._assign_pid_to_job(10, 20) is False
        assert _dast_mod._resume_process_primary_thread(20) is False
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: 55
        def _t32_first(_s: Any, te_ptr: Any) -> bool:
            te_ptr._obj.th32OwnerProcessID = 20
            te_ptr._obj.th32ThreadID = 77
            return True
        fake_k32.Thread32First = _t32_first
        fake_k32.OpenThread = lambda *_a: 88
        assert _dast_mod._resume_process_primary_thread(20) is False
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: (_ for _ in ()).throw(OSError("snap"))
        assert _dast_mod._resume_process_primary_thread(20) is False
        assert _dast_mod._assign_to_kill_on_close_job(20) is None
        fake_k32.CreateJobObjectW = lambda _a, _b: 123
        fake_k32.SetInformationJobObject = lambda *_a: 1
        fake_k32.CloseHandle = lambda _h: (_ for _ in ()).throw(OSError("close"))
        assert _dast_mod._assign_to_kill_on_close_job(20) is None
        _dast_mod._close_job_handle_safe(123)
        fake_k32.CloseHandle = lambda _h: None
        fake_k32.OpenProcess = lambda *_a: 99
        assert _dast_mod._assign_to_kill_on_close_job(20) == 123


@pytest.mark.fast
def test_r4_s3_dast_path_readonly_and_report_io(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre symlink esterno, rimozione readonly con errore e report DAST atomico fallito."""
    sb_dir = tmp_path / "sb"
    sb_dir.mkdir()
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    orig_is_sym = Path.is_symlink
    orig_resolve = Path.resolve
    with monkeypatch.context() as mp:
        mp.setattr(Path, "is_symlink", lambda self: True if self.name == "evil_link" else orig_is_sym(self))
        mp.setattr(Path, "resolve", lambda self, strict=False: outside if self.name == "evil_link" else orig_resolve(self, strict=strict))
        with pytest.raises(ValueError, match="Symlink esterno"):
            _dast_mod._resolve_confined_sandbox_path(sb_dir, "evil_link/secret.txt")
    ro_file = tmp_path / "ro.txt"
    ro_file.write_text("x", encoding="utf-8")
    os.chmod(ro_file, 0o444)
    _dast_mod._handle_remove_readonly(os.unlink, str(ro_file), None)
    assert not ro_file.exists()
    _dast_mod._handle_remove_readonly(lambda _p: (_ for _ in ()).throw(OSError("fail")), str(tmp_path / "missing"), None)
    rep_p = _dast_mod.resolve_dast_report_path(tmp_path, "   ")
    assert rep_p.parent == tmp_path and rep_p.name.startswith("dast_report_")
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod, "atomic_write_json", lambda *_a, **_kw: (False, "disk_full"))
        with pytest.raises(OSError, match="disk_full"):
            _dast_mod.write_atomic_dast_report({"ok": True}, tmp_path)


@pytest.mark.fast
def test_r4_s3_dast_job_subprocess_and_kill_fallbacks(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre i rami fallback di _run_job_isolated_subprocess inclusi assign/resume/timeout."""
    spawn_calls: List[int] = []
    def _fake_popen(*_a: Any, **kwargs: Any) -> Any:
        spawn_calls.append(int(kwargs.get("creationflags", 0)))
        return SimpleNamespace(
            pid=9101,
            returncode=0,
            communicate=lambda timeout=None: ("out", "err"),
            kill=lambda: None,
            wait=lambda timeout=None: 0,
        )
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.subprocess, "Popen", _fake_popen)
        mp.setattr(_dast_mod, "_create_kill_on_close_job", lambda: None)
        res_nojob = _dast_mod._run_job_isolated_subprocess(["cmd"], tmp_path, {}, 2.0)
        assert res_nojob.returncode == 0
        mp.setattr(_dast_mod, "_create_kill_on_close_job", lambda: 500)
        mp.setattr(_dast_mod, "_assign_pid_to_job", lambda _j, _p: False)
        mp.setattr(_dast_mod, "_resume_process_primary_thread", lambda _p: False)
        mp.setattr(_dast_mod, "_close_job_handle_safe", lambda _j: None)
        res_fb = _dast_mod._run_job_isolated_subprocess(["cmd"], tmp_path, {}, 2.0)
        assert res_fb.stdout == "out" and len(spawn_calls) == 3

    fb_killed: List[int] = []
    def _timeout_popen(*_a: Any, **_kw: Any) -> Any:
        return SimpleNamespace(
            pid=9202,
            returncode=None,
            communicate=lambda timeout=None: (_ for _ in ()).throw(subprocess.TimeoutExpired("cmd", 1.0)),
            kill=lambda: (_ for _ in ()).throw(OSError("no_kill")),
            wait=lambda timeout=None: 0,
        )
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.sys, "platform", "win32")
        mp.setattr(_dast_mod, "_create_kill_on_close_job", lambda: None)
        mp.setattr(_dast_mod.subprocess, "Popen", _timeout_popen)
        mp.setattr(_dast_mod.subprocess, "run", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("no_tk")))
        mp.setattr(_dast_mod, "_terminate_process_tree_fallback", lambda pid: fb_killed.append(pid) or 1)
        with pytest.raises(subprocess.TimeoutExpired):
            _dast_mod._run_job_isolated_subprocess(["cmd"], tmp_path, {}, 1.0)
    assert fb_killed == [9202]


@pytest.mark.fast
def test_r4_s3_dast_terminate_tree_and_rss_branches(monkeypatch: Any) -> None:
    """Copre _terminate_process_tree_fallback e tutti i rami Win32/psutil di _get_process_memory_rss."""
    entries = [(100, 1), (200, 100)]
    idx_state = {"i": 0}
    def _p_first(_s: Any, pe_ptr: Any) -> bool:
        idx_state["i"] = 0
        pe_ptr._obj.th32ProcessID, pe_ptr._obj.th32ParentProcessID = entries[0]
        return True
    def _p_next(_s: Any, pe_ptr: Any) -> bool:
        idx_state["i"] += 1
        if idx_state["i"] >= len(entries):
            return False
        pe_ptr._obj.th32ProcessID, pe_ptr._obj.th32ParentProcessID = entries[idx_state["i"]]
        return True
    fake_k32 = SimpleNamespace(
        CreateToolhelp32Snapshot=lambda *_a: _dast_mod.INVALID_HANDLE_VALUE,
        Process32First=lambda *_a: False,
        Process32Next=lambda *_a: False,
        CloseHandle=lambda _h: None,
        OpenProcess=lambda *_a: 0,
    )
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.sys, "platform", "win32")
        mp.setattr(_dast_mod, "_kernel32", fake_k32)
        mp.setattr(_dast_mod.os, "kill", lambda p, _s: (_ for _ in ()).throw(OSError("no")) if p == 999 else None)
        assert _dast_mod._terminate_process_tree_fallback(999) == 0
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: 77
        assert _dast_mod._terminate_process_tree_fallback(100) == 2
        fake_k32.Process32First, fake_k32.Process32Next = _p_first, _p_next
        assert _dast_mod._terminate_process_tree_fallback(100) == 4
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: (_ for _ in ()).throw(OSError("boom"))
        assert _dast_mod._terminate_process_tree_fallback(100) == 0

    bad_child = SimpleNamespace(memory_info=lambda: (_ for _ in ()).throw(OSError("dead")))
    p_proc = SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=1024), children=lambda recursive=True: [bad_child])
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod, "_HAS_PSUTIL", True)
        assert _dast_mod._get_process_memory_rss(100, p_proc) == 1024
        p_proc.memory_info = lambda: (_ for _ in ()).throw(OSError("gone"))
        mp.setattr(_dast_mod.sys, "platform", "linux")
        assert _dast_mod._get_process_memory_rss(100, p_proc) == 0
        mp.setattr(_dast_mod.sys, "platform", "win32")
        mp.setattr(_dast_mod, "_kernel32", fake_k32)
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: _dast_mod.INVALID_HANDLE_VALUE
        assert _dast_mod._get_process_memory_rss(100) == 0
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: 77
        fake_k32.OpenProcess = lambda *_a: 55
        fake_k32.K32GetProcessMemoryInfo = lambda *_a: (_ for _ in ()).throw(OSError("k32"))
        fake_psapi = SimpleNamespace(GetProcessMemoryInfo=lambda _h, ptr, _cb: setattr(ptr._obj, "WorkingSetSize", 4096) or 1)
        mp.setattr(_dast_mod, "_psapi", fake_psapi)
        assert _dast_mod._get_process_memory_rss(100) == 8192
        fake_psapi.GetProcessMemoryInfo = lambda *_a: (_ for _ in ()).throw(OSError("psapi"))
        assert _dast_mod._get_process_memory_rss(100) == 0
        fake_k32.CreateToolhelp32Snapshot = lambda *_a: (_ for _ in ()).throw(OSError("snap"))
        assert _dast_mod._get_process_memory_rss(100) == 0


@pytest.mark.fast
def test_r4_s3_dast_runner_sandbox_and_watchdog_edges(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Copre ShadowSandbox lazy create/cleanup retry e i rami command/watchdog di run_in_sandbox."""
    del isolated_nk_env
    src_f = tmp_path / "mod.py"
    src_f.write_text("X = 1\n", encoding="utf-8")
    sb_copy = _dast_mod.ShadowSandbox()
    copied = sb_copy.copy_file(src_f)
    assert copied.exists()
    rm_calls = {"n": 0}
    orig_rmtree = _dast_mod.shutil.rmtree
    def _flaky_rmtree(p: Any, onerror: Any = None) -> None:
        rm_calls["n"] += 1
        if rm_calls["n"] == 1:
            raise PermissionError("busy")
        orig_rmtree(p, onerror=onerror)
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.shutil, "rmtree", _flaky_rmtree)
        mp.setattr(_dast_mod.time, "sleep", lambda _s: None)
        sb_copy.cleanup()
    assert rm_calls["n"] == 2

    async def _exercise_runner() -> None:
        sb = _dast_mod.ShadowSandbox()
        runner = _dast_mod.DASTSandboxRunner(
            _dast_mod.SandboxConfig(profile="evaluator", trace_coverage=True, env_vars={"PYTHONPATH": "extra_p"})
        )
        seen_cmds: List[List[str]] = []
        async def _fake_exec(*cmd: str, **_kw: Any) -> Any:
            seen_cmds.append(list(cmd))
            async def _comm() -> tuple[bytes, bytes]:
                raise RuntimeError("comm_err")
            async def _wait() -> int:
                return 0
            return SimpleNamespace(pid=3333, returncode=0, communicate=_comm, wait=_wait, kill=lambda: None)
        with monkeypatch.context() as mp:
            mp.setattr(_dast_mod.asyncio, "create_subprocess_exec", _fake_exec)
            mp.setattr(_dast_mod, "_create_kill_on_close_job", lambda: 700)
            mp.setattr(_dast_mod, "_assign_pid_to_job", lambda _j, _p: False)
            mp.setattr(_dast_mod, "_resume_process_primary_thread", lambda _p: False)
            mp.setattr(_dast_mod, "_close_job_handle_safe", lambda _j: None)
            mp.setattr(_dast_mod, "psutil", SimpleNamespace(Process=lambda _p: (_ for _ in ()).throw(OSError("no_p"))))
            mp.setattr(_dast_mod, "_HAS_PSUTIL", True)
            sb.write_file("target.py", "print(1)\n")
            sb.write_file("other.py", "print(2)\n")
            sb.write_file("_nk_coverage_out.json", "{corrupt")
            await runner.run_in_sandbox(sb, [sys.executable, "-B", "other.py"], target_script_name="target.py")
            await runner.run_in_sandbox(sb, [sys.executable, "arg1"], target_script_name="target.py")
            await runner.run_in_sandbox(sb, ["target.py", "--x"], target_script_name="target.py")
            await runner.run_in_sandbox(sb, ["other.py", "--y"], target_script_name="target.py")
            rep = await runner.run_in_sandbox(sb, ["arg_only"], target_script_name="target.py")
            assert rep.statement_traces == [] and len(seen_cmds) >= 5
        sb.cleanup()

    asyncio.run(_exercise_runner())


@pytest.mark.fast
def test_r4_s3_dast_overlay_and_cli_edges(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Copre _kill_process_tree, run_staging_shadow_verification (data>5MB, error paths) e main()."""
    del isolated_nk_env
    runner = _dast_mod.DASTSandboxRunner()
    parent_fake = SimpleNamespace(pid=4444, kill=lambda: (_ for _ in ()).throw(OSError("pk")))
    proc_fake = SimpleNamespace(pid=None, returncode=None, kill=lambda: (_ for _ in ()).throw(OSError("k")))
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.subprocess, "run", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("tk")))
        mp.setattr(_dast_mod, "_terminate_process_tree_fallback", lambda _p: 0)
        mp.setattr(_dast_mod, "_HAS_PSUTIL", True)
        runner._kill_process_tree(proc=proc_fake, parent=parent_fake)
        mp.setattr(runner, "_kill_process_tree", lambda **_kw: (_ for _ in ()).throw(OSError("outer")))
        assert runner.kill_process_tree() is True

    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "s.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "data" / "sub").mkdir(parents=True)
    (repo / "data" / "sub" / "big.bin").write_bytes(b"\x00" * (5 * 1024 * 1024 + 10))
    (repo / ".staging" / "data").mkdir(parents=True)
    (repo / ".staging" / "data" / "stg_big.bin").write_bytes(b"\x00" * (5 * 1024 * 1024 + 10))
    (repo / ".staging" / ".deleted_files.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError):
        _dast_mod.run_staging_shadow_verification(repo, run_pytest=False, run_ast_guard=False)
    (repo / ".staging" / ".deleted_files.json").write_text("[]", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod, "_run_job_isolated_subprocess", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("sub_err")))
        mp.setattr(_dast_mod, "write_atomic_dast_report", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("diag")))
        res = _dast_mod.run_staging_shadow_verification(repo, run_pytest=True, run_ast_guard=True)
        assert res["passed"] is False and res["ast_guard"]["exit_code"] == -1
        mp.setattr(_dast_mod, "_run_job_isolated_subprocess", lambda *_a, **_kw: SimpleNamespace(returncode=1, stdout="- [ERR] fail", stderr="err_line"))
        res2 = _dast_mod.run_staging_shadow_verification(repo, run_pytest=False, run_ast_guard=True)
        assert res2["ast_guard"]["stderr_tail"] == "err_line"
        mp.setattr(_dast_mod, "run_staging_shadow_verification", lambda **_kw: {"status": "PASS", "passed": True, "overlay_files_count": 0})
        mp.setattr(_dast_mod, "write_atomic_dast_report", lambda payload, td, explicit_output=None: Path(td) / "rep.json")
        rc_ov, out_ov, _ = call_script_main_captured(_dast_mod, ["--overlay-staging", str(repo), "--report-to-tracking", "--json"])
        assert rc_ov == 0 and "tracking_report_file" in json.loads(out_ov)

    scr_dir = tmp_path / "many_scripts"
    scr_dir.mkdir()
    for i in range(52):
        (scr_dir / f"sib_{i:02d}.py").write_text(f"V = {i}\n", encoding="utf-8")
    main_s = scr_dir / "main_entry.py"
    main_s.write_text("print('ok')\n", encoding="utf-8")
    rc_s, out_s, _ = call_script_main_captured(_dast_mod, ["--script", str(main_s), "--profile", "evaluator", "--report-to-tracking"])
    assert rc_s == 0 and "[DAST-SANDBOX] Success: True" in out_s


@pytest.mark.fast
def test_r4_s3_memory_win32_replace_and_mutex_fallbacks(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre fallback import win32_2pc_engine, _get_kernel32, win32_atomic_replace e backup prod."""
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "win32_2pc_engine", None)
        mp.setitem(sys.modules, "scripts.win32_2pc_engine", None)
        mp.setattr(_mem_mod, "_Win32NamedMutex", _mem_mod._UNSET)
        mp.setattr(_mem_mod, "_win32_2pc_atomic_replace", _mem_mod._UNSET)
        with _mem_mod._acquire_memory_file_mutex(tmp_path / "m.lock") as ctx_val:
            assert ctx_val is None
        mp.setattr(_mem_mod.os, "name", "posix")
        mp.setattr(_mem_mod, "_kernel32", _mem_mod._UNSET)
        assert _mem_mod._get_kernel32() is None

    src_p, dst_p = tmp_path / "src.txt", tmp_path / "dst.txt"
    src_p.write_text("new", encoding="utf-8")
    dst_p.write_text("old", encoding="utf-8")
    err_codes = iter([32, 999])
    fake_k32 = SimpleNamespace(MoveFileExW=lambda *_a: False, GetLastError=lambda: next(err_codes, 32))
    orig_replace = _mem_mod.os.replace
    rep_calls = {"n": 0}
    def _flaky_replace(s: str, d: str) -> None:
        rep_calls["n"] += 1
        if rep_calls["n"] <= 2:
            raise PermissionError("locked")
        orig_replace(s, d)
    with monkeypatch.context() as mp:
        mp.setattr(_mem_mod, "_win32_2pc_atomic_replace", None)
        mp.setattr(_mem_mod, "_Win32NamedMutex", None)
        mp.setattr(_mem_mod.os, "name", "nt")
        mp.setattr(_mem_mod, "_kernel32", fake_k32)
        mp.setattr(_mem_mod.time, "sleep", lambda _s: None)
        mp.setattr(_mem_mod.os, "replace", _flaky_replace)
        _mem_mod.win32_atomic_replace(src_p, dst_p, max_retries=2)
    assert dst_p.read_text(encoding="utf-8") == "new"
    prod_sub = _mem_mod._workspace_root / "nk_tracking" / "01_Bug_Diagnostics" / "episodes.jsonl"
    ext_bkp = _mem_mod._resolve_external_backup_dir(prod_sub)
    assert ext_bkp is not None and ext_bkp.name == "01_Bug_Diagnostics"


@pytest.mark.fast
def test_r4_s3_memory_embedder_rrf_and_trigram_edges() -> None:
    """Copre collisione norma zero in DenseEmbedder, query vuota RRF e trigrammi vuoti."""
    zero_tok = ""
    for i in range(64):
        cand = f"t{i}"
        dig = hashlib.sha256(cand.encode("utf-8")).digest()
        if (dig[8] & 0x01) != (dig[17] & 0x01):
            zero_tok = cand
            break
    assert zero_tok
    vec = _mem_mod.DenseEmbedder.vector_from_text(zero_tok, dim=1)
    assert vec == [1.0]
    assert _mem_mod.HybridRRFSearchEngine().search("", []) == []
    assert _mem_mod.ThreeTierMemoryEngine._char_trigram_cosine("!!!", "abc") == 0.0


@pytest.mark.fast
def test_r4_s3_memory_cold_archive_fts_and_corrupt_recovery(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre recupero archivio cold corrotto multi-membro e errori SQLite FTS5."""
    eng = _mem_mod.ThreeTierMemoryEngine(base_dir=tmp_path / "mem")
    assert eng._read_cold_archive(tmp_path / "nope.gz") == []

    ep1 = _mem_mod.MemoryEpisode(episode_id="c1", domain="OPS", title="Alpha", content="running tests fast")
    ep2 = _mem_mod.MemoryEpisode(episode_id="c2", domain="OPS", title="Beta", content="second member item")
    cold = tmp_path / "mem" / "01_Bug_Diagnostics" / "archive.cold.jsonl.gz"
    cold.parent.mkdir(parents=True, exist_ok=True)
    m1 = gzip.compress((ep1.model_dump_json() + "\n\n").encode("utf-8"))
    m2 = gzip.compress((ep2.model_dump_json() + "\nbad_json\n").encode("utf-8")) + b"\x1f\x8b\x08\x00trunc"
    cold.write_bytes(m1 + m2)
    recovered = eng._read_cold_archive(cold)
    assert [e.episode_id for e in recovered] == ["c1", "c2"]

    empty_gz = tmp_path / "empty.gz"
    with gzip.open(empty_gz, "wb") as gz_f:
        gz_f.write(b"")
    with contextlib.closing(sqlite3.connect(str(eng._cold_fts_db_path))) as conn:
        eng._sync_cold_fts5_index(empty_gz, conn)
        eng._sync_cold_fts5_index(cold, conn)
        gz_key = os.path.realpath(str(cold)).lower()
        with conn:
            conn.execute("INSERT INTO cold_episodes VALUES (?, 99, 'bad', '{bad')", (gz_key,))
            conn.execute("INSERT INTO cold_episodes_fts VALUES (?, 'bad', '{bad', 'running', 'running', '')", (gz_key,))
    assert len(eng._get_cached_cold_episodes(cold)) == 2
    assert len(eng._search_cold_fts5(cold, "running")) == 1
    with monkeypatch.context() as mp:
        mp.setattr(_mem_mod.sqlite3, "connect", lambda *_a, **_kw: (_ for _ in ()).throw(sqlite3.Error("db_err")))
        assert len(eng._get_cached_cold_episodes(cold)) == 2
        assert len(eng._search_cold_fts5(cold, "running")) == 2


@pytest.mark.fast
def test_r4_s3_memory_tier2_cache_consolidation_and_helpers(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre recall_hybrid edge, consolidamento provenance, backup .bak_1 e shadow cache."""
    eng = _mem_mod.ThreeTierMemoryEngine(base_dir=tmp_path / "mem_root")
    assert eng.recall_hybrid("OPS", "missing_topic") == []
    ep_a = _mem_mod.MemoryEpisode(
        episode_id="e1", domain="OPS", title="Cache lock", content="fix lock error",
        vector=[1.0, 0.0], metadata={"source_url": "https://example.org/doc"}
    )
    ep_b = _mem_mod.MemoryEpisode(
        episode_id="e2", domain="OPS", title="Cache lock", content="fix lock error now",
        vector=[1.0, 0.0], metadata={}
    )
    eng.append_episode(ep_a)
    eng.append_episode(ep_b)
    assert eng.recall_hybrid("OPS", "zzz_no_overlap") == []
    assert len(eng.recall_hybrid("OPS", "cache", adaptive=False)) >= 1
    cons_res = eng.consolidate_similar_episodes(threshold=0.9)
    assert cons_res["merged_count"] == 1
    kept_eps = eng.get_tier2_episodes("OPS")
    assert kept_eps[0].metadata.get("source_url") == "https://example.org/doc"

    t2_file = eng.base_dir / "01_Bug_Diagnostics" / "episodes.jsonl"
    bak1 = t2_file.with_name("episodes.jsonl.bak_1")
    bak1.write_text("\n{bad\n" + ep_a.model_dump_json() + "\n", encoding="utf-8")
    t2_file.write_text("{corrupt\n", encoding="utf-8")
    assert len(eng._load_tier2_raw(t2_file)) == 1
    meta_f = eng.cache_dir / f"{eng._project_cache_id}_01_Bug_Diagnostics_meta.json"
    meta_f.write_text(json.dumps({"size": t2_file.stat().st_size, "mtime_ns": -1}), encoding="utf-8")
    assert eng._read_shadow_cache("01_Bug_Diagnostics") is None
    meta_f.write_text(json.dumps({"size": t2_file.stat().st_size, "mtime": -1.0}), encoding="utf-8")
    assert eng._read_shadow_cache("01_Bug_Diagnostics") is None
    meta_f.write_text("{bad", encoding="utf-8")
    assert eng._read_shadow_cache("01_Bug_Diagnostics") is None
    with monkeypatch.context() as mp:
        mp.setattr(Path, "write_text", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("ro")))
        eng._update_shadow_cache("01_Bug_Diagnostics", [ep_a])
    ws_root = tmp_path / "ws_proj"
    (ws_root / "nk_tracking" / "memory_3tier").mkdir(parents=True)
    assert _mem_mod.consolidate_similar_episodes(root=ws_root)["merged_count"] == 0
    assert _mem_mod.consolidate_similar_episodes(root=tmp_path / "empty_ws")["merged_count"] == 0


@pytest.mark.fast
def test_r4_s3_qbm_extract_cov_and_load_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre errori load_baseline, create_default_baseline dict, scrittura fallita e _extract_coverage_totals."""
    bad_bl = tmp_path / "list.json"
    bad_bl.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="dizionario"):
        _qbm_mod.load_baseline(str(bad_bl))
    dflt = _qbm_mod.create_default_baseline("Proj", {"custom": {"value": 5, "direction": "higher_is_better"}})
    assert dflt["metrics"]["custom"]["value"] == 5
    with monkeypatch.context() as mp:
        mp.setattr(_qbm_mod, "atomic_write_json", lambda *_a, **_kw: (False, "eperm"))
        with pytest.raises(PermissionError, match="eperm"):
            _qbm_mod._atomic_write_baseline(str(tmp_path / "b.json"), dflt)
    assert _qbm_mod._extract_coverage_totals(tmp_path / "missing.json") == {}
    cov_j = tmp_path / "cov.json"
    cov_j.write_text("{bad", encoding="utf-8")
    assert _qbm_mod._extract_coverage_totals(cov_j) == {}
    cov_j.write_text("{}", encoding="utf-8")
    assert _qbm_mod._extract_coverage_totals(cov_j) == {}
    cov_j.write_text(json.dumps({"totals": {"num_statements": 10, "covered_lines": 5, "num_branches": 4, "covered_branches": 2}}), encoding="utf-8")
    tot = _qbm_mod._extract_coverage_totals(cov_j)
    assert tot["statement_coverage_pct"] == 50.0 and tot["combined_coverage_pct"] == 50.0


@pytest.mark.fast
def test_r4_s3_qbm_measure_live_pytest_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre measure_live_pytest_metrics con overlay .staging, tombstone, skills e failure fallback."""
    ws = tmp_path / "ws"
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_prod.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    (ws / ".staging" / "tests").mkdir(parents=True)
    (ws / ".staging" / "tests" / "test_stg.py").write_text("def test_b(): assert True\n", encoding="utf-8")
    (ws / ".staging" / ".agents" / "skills" / "demo").mkdir(parents=True)
    (ws / ".staging" / ".agents" / "skills" / "demo" / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["tests/test_prod.py"]), encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setenv("PYTHONPATH", "extra_pp")
        mp.setattr(_qbm_mod.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=1, stdout="2 passed", stderr=""))
        res = _qbm_mod.measure_live_pytest_metrics(workspace_root=ws, with_coverage=False)
        assert res["failed_tests"] == 1 and res["skills_audited"] == 1
        mp.delenv("PYTHONPATH", raising=False)
        (ws / ".staging" / ".deleted_files.json").write_text("{bad", encoding="utf-8")
        res2 = _qbm_mod.measure_live_pytest_metrics(workspace_root=ws, with_coverage=False)
        assert res2["failed_tests"] == 1


@pytest.mark.fast
def test_r4_s3_qbm_oracle_lock_and_compliance_edges(tmp_path: Path) -> None:
    """Copre _verify_oracle_lock_coherence, gt68 nested e rami update_baseline_metrics."""
    ws = tmp_path / "qbm_ws"
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)
    tf = ws / "tests" / "t_one.py"
    tf.write_text("X = 1\n", encoding="utf-8")
    tf2 = ws / "tests" / "t_two.py"
    tf2.write_text("Y = 2\n", encoding="utf-8")
    sha = hashlib.sha256(tf.read_bytes()).hexdigest()
    lock_p = ws / "nk_tracking" / "oracle_lock.json"
    lock_p.write_text(
        json.dumps({
            "target": str(tmp_path / "outside"),
            "locked_files": {"t_one.py": sha},
            "files": ["t_two.py"],
            "combined_sha256": sha,
        }),
        encoding="utf-8",
    )
    bl_p = ws / "nk_tracking" / "quality_baseline.json"
    assert _qbm_mod._verify_oracle_lock_coherence(str(bl_p)) == []
    lock_p.write_text(json.dumps({"files": {"t_one.py": sha, "missing.py": sha}, "combined_sha256": sha}), encoding="utf-8")
    anom = _qbm_mod._verify_oracle_lock_coherence(str(bl_p))
    assert any("missing.py" in a["message"] for a in anom)
    lock_p.unlink()

    up_init = _qbm_mod.update_baseline_metrics(str(bl_p), {"total_golden_tests": 100, "unit_tests_passed": 100, "pass_rate_pct": 100.0, "skills_audited": 14})
    assert up_init["status"] == "INITIALIZED"
    comp, _ = _qbm_mod._evaluate_baseline_compliance(
        str(bl_p),
        {"golden_tests_68": {"passed": 100, "total": 100, "pass_rate_pct": 100.0}, "skills_audited": 10},
        allow_ratchet_down=True,
    )
    assert comp["verdict"] == "PASS"
    up_ok = _qbm_mod.update_baseline_metrics(str(bl_p), {"total_golden_tests": 100, "unit_tests_passed": 100, "pass_rate_pct": 100.0})
    assert up_ok["status"] == "UPDATED"


@pytest.mark.fast
def test_r4_s3_qbm_cli_modes_and_recalibrate(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre action invalida, recalibrate --live pass/fail e check --live gate fail."""
    bl_p = tmp_path / "nk_tracking" / "quality_baseline.json"
    bl_p.parent.mkdir(parents=True)
    _qbm_mod.update_baseline_metrics(str(bl_p), {"total_golden_tests": 95, "unit_tests_passed": 95, "pass_rate_pct": 100.0})
    rc_bad, out_bad, _ = call_script_main_captured(_qbm_mod, ["bogus_cmd", str(bl_p)])
    assert rc_bad == 1 and "ERROR" in out_bad

    with monkeypatch.context() as mp:
        mp.setattr(_qbm_mod, "measure_live_pytest_metrics", lambda *_a, **_kw: {"unit_tests_passed": 50, "unit_tests_total": 51, "failed_tests": 1, "pass_rate_pct": 98.0})
        rc_rf, out_rf, _ = call_script_main_captured(_qbm_mod, ["recalibrate", "--file", str(bl_p), "--live"])
        assert rc_rf == 1 and "REJECTED" in out_rf
        mp.setattr(_qbm_mod, "measure_live_pytest_metrics", lambda *_a, **_kw: {"unit_tests_passed": 96, "unit_tests_total": 96, "failed_tests": 0, "pass_rate_pct": 100.0})
        rc_rp, out_rp, _ = call_script_main_captured(_qbm_mod, ["recalibrate", "--file", str(bl_p), "--live"])
        assert rc_rp == 0 and "live_metrics" in json.loads(out_rp)
        mp.setattr(_qbm_mod, "measure_live_pytest_metrics", lambda *_a, **_kw: {"total_golden_tests": 50, "unit_tests_passed": 50, "pass_rate_pct": 100.0})
        rc_cf, out_cf, _ = call_script_main_captured(_qbm_mod, ["check", "--file", str(bl_p), "--live"])
        assert rc_cf == 1 and json.loads(out_cf)["verdict"] == "FAIL"


_l3_mod = load_script_by_relpath("oracle_evaluator_l3", "scripts/oracle_evaluator_l3.py")
_heal_mod = load_script_by_relpath("auto_heal_pipeline", "scripts/auto_heal_pipeline.py")
_sbfl_mod = load_script_by_relpath("sbfl_engine", "scripts/sbfl_engine.py")
_snap_mod = load_script_by_relpath("healing_snapshot_rollback", "scripts/healing_snapshot_rollback.py")
_inv_mod = load_script_by_relpath("invisible_healing_loop", "scripts/invisible_healing_loop.py")
_rsi_mod = load_script_by_relpath("rsi_convergence_engine", "scripts/rsi_convergence_engine.py")
_map_mod = load_script_by_relpath("ast_repo_mapper", "scripts/ast_repo_mapper.py")


@pytest.mark.fast
def test_r4_s3_oracle_l3_html5_implicit_tags_and_lfi() -> None:
    """Copre LFI drive-letter, resolve_expected_source e chiusure implicite HTML5 in oracle_evaluator_l3."""
    assert _l3_mod._looks_like_disallowed_file_reference("C:\\secret.txt") is True
    assert _l3_mod.resolve_expected_source("plain text") == ("plain text", "html")
    ev = _l3_mod.DOMOracleEvaluator()
    html_sample = (
        "<ul><li>a<li>b</ul><div><li>x</ul>"
        "<dl><dt>t1<dd>d1<dt>t2<dd>d2</dl><div><dt>y</dl>"
        "<table><thead><tr><th>h<td>c<tr><td>x<tbody><tr><td>y</table>"
        "<div><td>a<tr>b<tbody>c</div>"
        "<select><optgroup><option>1<option>2<optgroup><option>3</select>"
        "<td><p>x<div>y</div></td><br/><img src='a'/></div>"
    )
    root = ev.parse_html(html_sample)
    assert ev.count_nodes(root) >= 15


@pytest.mark.fast
def test_r4_s3_oracle_l3_markdown_json_and_sequence_diff() -> None:
    """Copre parser Markdown, vincoli JSON/MD mancanti, SequenceMatcher replace e CLI."""
    ev = _l3_mod.DOMOracleEvaluator()
    md_spec = "###   \n# Heading\n- #id1 #id1 <div> <div> \"q1\" \"q1\"\n- #onlyid\n- bullet text\n"
    rep_md = ev.evaluate_deltas(md_spec, "<div>plain</div>", expected_kind="md")
    assert rep_md.verdict == "FAIL" and rep_md.discrepancy_count >= 3
    rep_empty = ev.evaluate_deltas("{}", "<div></div>", expected_kind="json")
    assert rep_empty.verdict == "FAIL"
    rep_cls = ev.evaluate_deltas(
        json.dumps({"html": "<div></div>", "required_classes": ["missing_c"]}),
        "<div></div>",
        expected_kind="json",
    )
    assert rep_cls.verdict == "FAIL"
    rep_seq = ev.evaluate_deltas("<div><span>a</span><b>b</b><i>c</i></div>", "<div><em>x</em></div>", expected_kind="html")
    assert any(d.change_type == "REMOVED" for d in rep_seq.deltas)
    rep_ins = ev.evaluate_deltas("<div><span>a</span></div>", "<div><span>a</span><p>x</p></div>", expected_kind="html")
    assert any(d.change_type == "ADDED" for d in rep_ins.deltas)
    rc_ok, out_ok, _ = call_script_main_captured(_l3_mod, ["--expected", "<div>a</div>", "--actual", "<div>a</div>"])
    assert rc_ok == 0 and "[ORACLE-DOM-L3] Verdict: PASS" in out_ok
    rc_err, _, err_out = call_script_main_captured(_l3_mod, ["--expected", "C:\\no_such.html", "--actual", "<div>a</div>"])
    assert rc_err == 2 and "ERROR" in err_out


@pytest.mark.fast
def test_r4_s3_auto_heal_helpers_and_lazy_loaders(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre loader lazy con fallback, KarpathySlicer su funzioni <=30 righe e _build_defect_vector."""
    with monkeypatch.context() as mp:
        mp.setattr(_heal_mod, "OchiaiBridgeLocation", _heal_mod._UNSET)
        mp.setattr(_heal_mod, "SBFLPytestBridge", _heal_mod._UNSET)
        mp.setitem(sys.modules, "sbfl_pytest_bridge", None)
        _heal_mod._ensure_sbfl_bridge_loaded()
        assert _heal_mod.SBFLPytestBridge is not None
        mp.setattr(_heal_mod, "RSIConvergenceEngine", _heal_mod._UNSET)
        mp.setattr(_heal_mod, "RSIDefectVector", _heal_mod._UNSET)
        mp.setattr(_heal_mod, "RSIIterationRecord", _heal_mod._UNSET)
        mp.setattr(_heal_mod, "compute_delta", _heal_mod._UNSET)
        mp.setattr(_heal_mod, "compute_fitness", _heal_mod._UNSET)
        mp.setitem(sys.modules, "rsi_convergence_engine", None)
        mp.setitem(sys.modules, "scripts.rsi_convergence_engine", None)
        _heal_mod._ensure_rsi_loaded()
        assert _heal_mod.RSIConvergenceEngine is None
        mp.setattr(_heal_mod, "ASTGuardValidator", _heal_mod._UNSET)
        mp.setitem(sys.modules, "ast_guard_validator", None)
        mp.setitem(sys.modules, "scripts.ast_guard_validator", None)
        _heal_mod._ensure_ast_guard_loaded()
        assert _heal_mod.ASTGuardValidator is None

    sl = _heal_mod.KarpathySlicer.slice_source("def f():\n    x = 1\n    return x\n", target_line=2, window=2)
    assert sl.function_name == "f"
    assert _heal_mod.normalize_test_command(["python", "-m", "pytest"]) == ["python", "-m", "pytest"]
    assert _heal_mod.normalize_test_command("pytest -q").endswith("-m pytest -q")
    assert _heal_mod.normalize_test_command(123) == 123  # type: ignore[arg-type]

    bad_py = tmp_path / "bad.py"
    bad_py.write_text("def broken(:\n    pass\n", encoding="utf-8")
    _heal_mod._ensure_rsi_loaded()
    _heal_mod._ensure_ast_guard_loaded()
    vec = _heal_mod._build_defect_vector(bad_py, "", 1, 1)
    assert vec is not None and vec.contract_violations > 0
    with monkeypatch.context() as mp:
        mp.setattr(_heal_mod.ASTGuardValidator, "validate_code_edit", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("agv")))
        vec2 = _heal_mod._build_defect_vector(bad_py, "", 1, 0)
        assert vec2 is not None and vec2.contract_violations == 0


@pytest.mark.fast
def test_r4_s3_auto_heal_pipeline_cycles_and_cli(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre run_pipeline IMPROVED/ROLLED_BACK/PASSED, errore RSI e main() con --json/testo."""
    target_f = tmp_path / "app.py"
    target_f.write_text("X = 1\n", encoding="utf-8")
    _heal_mod._ensure_sbfl_bridge_loaded()
    loc1 = _heal_mod.OchiaiBridgeLocation(
        file_path=str(target_f), line_number=1, suspiciousness=0.9,
        error_type="AssertionError", error_message="bad", failing_line_content="X = 1",
    )
    outcomes = iter([
        (SimpleNamespace(passed_count=1, failed_count=2, exit_code=1), loc1),
        (SimpleNamespace(passed_count=2, failed_count=1, exit_code=1), None),
        (SimpleNamespace(passed_count=0, failed_count=3, exit_code=1), loc1),
        (SimpleNamespace(passed_count=3, failed_count=0, exit_code=0), None),
    ])
    pipe = _heal_mod.AutoHealPipeline(cwd=tmp_path, max_cycles=3)
    with monkeypatch.context() as mp:
        mp.setattr(pipe.bridge, "run_and_diagnose", lambda **_kw: next(outcomes))
        if pipe.rsi_engine is not None:
            mp.setattr(pipe.rsi_engine, "append_telemetry_record", lambda _r: (_ for _ in ()).throw(OSError("tel")))
        rep = pipe.run_pipeline(
            "pytest -q",
            target_f,
            repair_callback=lambda _loc, _cyc: (_ for _ in ()).throw(RuntimeError("cb")),
        )
        assert rep.success is True and rep.cycles_used == 3

    with monkeypatch.context() as mp:
        fake_rep = _heal_mod.AutoHealSessionReport(
            success=False, cycles_used=1, max_cycles=1, initial_failed=1, final_failed=1,
            fault_location="app.py:1", error_type="AssertionError", message="failed",
        )
        mp.setattr(_heal_mod, "AutoHealPipeline", lambda **_kw: SimpleNamespace(run_pipeline=lambda **_k: fake_rep))
        rc_j, out_j, _ = call_script_main_captured(_heal_mod, ["--cwd", str(tmp_path), "--target-file", "app.py", "--json"])
        assert rc_j == 1 and json.loads(out_j)["fault_location"] == "app.py:1"
        rc_t, out_t, _ = call_script_main_captured(_heal_mod, ["--cwd", str(tmp_path), "--target-file", "app.py"])
        assert rc_t == 1 and "Last detected fault" in out_t
        fake_ok = _heal_mod.AutoHealSessionReport(
            success=True, cycles_used=1, max_cycles=1, initial_failed=1, final_failed=0,
            patch_note_line="- fixed", message="ok",
        )
        mp.setattr(_heal_mod, "AutoHealPipeline", lambda **_kw: SimpleNamespace(run_pipeline=lambda **_k: fake_ok))
        rc_ok, out_ok, _ = call_script_main_captured(_heal_mod, ["--cwd", str(tmp_path), "--target-file", "app.py"])
        assert rc_ok == 0 and "[PATCH-NOTE]" in out_ok


@pytest.mark.fast
def test_r4_s3_sbfl_monitoring_and_payload_edges(monkeypatch: Any) -> None:
    """Copre is_monitoring_conflict_active, sys.monitoring callback, token trim e localize hint."""
    assert _sbfl_mod.estimate_token_count("") == 0
    loc = _sbfl_mod.SBFLLocation(
        file_path="a-b/c-d/e-f/g-h/i-j.py", line_number=5, suspiciousness=0.8,
        error_type="E-T-N-A-B-C-D-E",
        error_message="a.b.c.d.e.f.g.h.i.j.k.l.m.n.o.p.q.r.s.t.u.v",
        failing_line_content="x+y+z+w+u+v+a+b+c+d+e+f+g+h+i+j+k+l+m+n",
    )
    rendered = json.loads(loc.render_payload_json())
    assert len(rendered["ctx"]) <= 20 and len(rendered["err"]) <= 30

    with monkeypatch.context() as mp:
        busy_mon = SimpleNamespace(get_tool=lambda tid: "tool" if tid == 1 else (_ for _ in ()).throw(ValueError("no")))
        fake_sys = SimpleNamespace(gettrace=lambda: lambda *_a: None, modules={}, monitoring=busy_mon)
        mp.setattr(_sbfl_mod, "sys", fake_sys)
        assert _sbfl_mod.is_monitoring_conflict_active() is True
        fake_sys.gettrace = lambda: None
        mp.delenv("COV_CORE_SOURCE", raising=False)
        assert _sbfl_mod.is_monitoring_conflict_active() is True
        fake_sys.monitoring = None
        assert _sbfl_mod.is_monitoring_conflict_active() is False
        ok_none, ex_none = _sbfl_mod.collect_statements_with_monitoring(lambda: None)
        assert ok_none is False and ex_none == set()
        mp.setattr(_sbfl_mod, "is_monitoring_conflict_active", lambda: False)
        cb_holder: Dict[str, Any] = {}
        def _reg_cb(_tid: int, _ev: int, fn: Any) -> None:
            if fn is not None:
                cb_holder["fn"] = fn
        def _get_t(tid: int) -> Any:
            return (_ for _ in ()).throw(ValueError("bad")) if tid == 4 else ("busy" if tid == 3 else None)
        fake_mon = SimpleNamespace(
            events=SimpleNamespace(LINE=1), get_tool=_get_t, use_tool_id=lambda *_a: None,
            register_callback=_reg_cb, set_events=lambda *_a: None,
            free_tool_id=lambda _t: (_ for _ in ()).throw(ValueError("free")),
        )
        fake_sys.monitoring = fake_mon
        def _body() -> None:
            cb_holder["fn"](SimpleNamespace(co_filename="other.py"), 10)
            cb_holder["fn"](SimpleNamespace(co_filename="target.py"), 0)
            cb_holder["fn"](SimpleNamespace(co_filename="target.py"), 12)
        ok_mon, ex_mon = _sbfl_mod.collect_statements_with_monitoring(_body, target_filename_filter="target.py")
        assert ok_mon is True and "target.py:12" in ex_mon
        fake_mon.get_tool = lambda _t: "busy"
        ok_busy, _ = _sbfl_mod.collect_statements_with_monitoring(lambda: None)
        assert ok_busy is False

    eng = _sbfl_mod.SBFLEngine()
    try:
        raise ValueError("boom")
    except ValueError as exc:
        loc_hit = eng.extract_from_exception(exc, relevant_file_hint="test_r4_cov_shard3")
        loc_miss = eng.extract_from_exception(exc, relevant_file_hint="no_such_hint")
        assert "test_r4_cov_shard3" in loc_hit.file_path and loc_miss.line_number >= 1


@pytest.mark.fast
def test_r4_s3_snapshot_rollback_and_invisible_loop(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre rami errori HealingSnapshotManager e annotazioni lazy/dir in invisible_healing_loop."""
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    (snap_dir / "snapshot_manifest.json").write_text("{corrupt", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_snap_mod.os, "replace", lambda *_a: (_ for _ in ()).throw(OSError("lock")))
        with pytest.raises(ValueError, match="Corrupt snapshot manifest"):
            _snap_mod.HealingSnapshotManager(base_temp_dir=snap_dir)
    (snap_dir / "snapshot_manifest.json").unlink()

    mgr = _snap_mod.HealingSnapshotManager(base_temp_dir=snap_dir)
    assert mgr.evaluate_fitness(1, 0, 2, 0, 0).verdict == _snap_mod.FitnessVerdict.REGRESSION
    tgt = tmp_path / "f.py"
    tgt.write_text("A = 1\n", encoding="utf-8")
    sid = mgr.create_snapshot([tgt])
    mgr.active_snapshots[sid].files[str(tgt.resolve())].content_b64 = ""
    tgt.write_text("A = 2\n", encoding="utf-8")
    assert mgr.rollback(sid)[str(tgt.resolve())] is True and tgt.read_text(encoding="utf-8") == "A = 1\n"
    for p in Path(mgr.active_snapshots[sid].temp_backup_dir).glob("*_f.py"):
        p.unlink()
    tgt.write_text("A = 3\n", encoding="utf-8")
    assert mgr.rollback(sid)[str(tgt.resolve())] is True and tgt.read_text(encoding="utf-8") == "A = 1\n"
    with monkeypatch.context() as mp:
        mp.setattr(_snap_mod, "_atomic_write_bytes", lambda *_a: (_ for _ in ()).throw(OSError("ro")))
        assert mgr.rollback(sid)[str(tgt.resolve())] is False
        mp.setattr(Path, "unlink", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("busy")))
        mgr.cleanup()

    assert "AutoHealPipeline" in dir(_inv_mod)
    loop = _inv_mod.InvisibleHealingLoop()
    assert loop.result_model is _heal_mod.HealingResult
    hints = typing.get_type_hints(_inv_mod.InvisibleHealingLoop.run_cli_pipeline)
    hints_rec = typing.get_type_hints(_inv_mod.InvisibleHealingLoop._record_telemetry)
    assert hints.get("return") is _heal_mod.AutoHealSessionReport
    assert hints_rec.get("return") is type(None) and "history" in hints_rec
    assert loop._record_telemetry("r0", "t0", 0, "CLEAN", []) is None
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "sbfl_engine", SimpleNamespace(SBFL_MAX_TOKEN_BUDGET=80))
        assert _inv_mod._load_lazy_symbol("SBFL_MAX_TOKEN_BUDGET") == 80


@pytest.mark.fast
def test_r4_s3_rsi_facade_lazy_and_cli_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre loader lazy di rsi_convergence_engine e rami CLI (--vibe-check, --verify UNMEASURED)."""
    with monkeypatch.context() as mp:
        mp.setattr(_rsi_mod, "_LAZY_HEALING_SNAPSHOT_LOADED", False)
        mp.setattr(_rsi_mod, "_LAZY_HEALING_SNAPSHOT_CLS", None)
        mp.setitem(sys.modules, "healing_snapshot_rollback", None)
        assert _rsi_mod._get_healing_snapshot_manager_cls() is not None
        mp.setattr(_rsi_mod, "_LAZY_AST_GUARD_LOADED", False)
        mp.setattr(_rsi_mod, "_LAZY_AST_GUARD_CLS", None)
        mp.setitem(sys.modules, "ast_guard_validator", SimpleNamespace())
        assert hasattr(_rsi_mod._get_ast_guard_validator(), "check_sast_constructs")
        mp.setattr(_rsi_mod, "_LAZY_AST_GUARD_LOADED", False)
        mp.setitem(sys.modules, "ast_guard_validator", None)
        mp.setitem(sys.modules, "scripts.ast_guard_validator", None)
        assert _rsi_mod._get_ast_guard_validator() is None
        mp.setattr(_rsi_mod, "_LAZY_STE100_FN", None)
        mp.setattr(_rsi_mod, "_LAZY_GROUNDING_FN", None)
        mp.setitem(sys.modules, "nk_transcript_tools", None)
        mp.setitem(sys.modules, "scripts.nk_transcript_tools", None)
        assert callable(_rsi_mod._get_ste100_validator())
        assert callable(_rsi_mod._get_report_grounding_validator())
        mp.setattr(_rsi_mod, "_LAZY_STE100_FN", None)
        mp.setattr(_rsi_mod, "_load_ntt_module", lambda: None)
        with pytest.raises(RuntimeError, match="non disponibile"):
            _rsi_mod._get_ste100_validator()

    empty_root = tmp_path / "empty_rsi"
    empty_root.mkdir()
    rc_v, out_v, _ = call_script_main_captured(_rsi_mod, ["--vibe-check", ".", "--root", str(empty_root)])
    assert rc_v == 0 and "[RSI-VIBE-CHECK]" in out_v
    rc_u, out_u, _ = call_script_main_captured(_rsi_mod, ["--verify", "--strict-verify", "--root", str(empty_root)])
    assert rc_u == 2 and "UNMEASURED" in out_u
    bundle_out = tmp_path / "gt14_cli.json"
    rc_b, out_b, _ = call_script_main_captured(_rsi_mod, ["--emit-gt14-bundle", "--root", str(empty_root), "--bundle-output", str(bundle_out)])
    assert rc_b in (0, 1) and "[GT14-BUNDLE]" in out_b


@pytest.mark.fast
def test_r4_s3_rsi_lazy_bridge_and_constants(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre lazy_bridge fallback e rami constants (_get_ipc_contracts, overlay .staging, AST cache)."""
    _rsi_mod._ensure_exports_loaded()
    lb = importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge")
    const_m = importlib.import_module("_internal.rsi_convergence_engine.constants")

    with monkeypatch.context() as mp:
        mp.setattr(lb, "_HOOKS", {})
        mp.setattr(lb, "_FALLBACK_STATE", {
            "streams_reconfigured": False, "hsm_cls": None, "hsm_loaded": False,
            "agv_cls": None, "agv_loaded": False, "ste100_fn": None, "grounding_fn": None,
        })
        mp.setattr(lb.sys, "stdout", SimpleNamespace(encoding="ascii"))
        lb.get_reconfigure_streams()
        lb.fallback_reconfigure_streams()
        assert lb.get_healing_snapshot_manager_cls() is not None
        assert lb.get_healing_snapshot_manager_cls() is not None
        mp.setitem(sys.modules, "ast_guard_validator", SimpleNamespace())
        assert hasattr(lb.get_ast_guard_validator(), "check_sast_constructs")
        assert lb.get_ast_guard_validator() is not None
        assert callable(lb.get_ste100_validator()) and callable(lb.get_ste100_validator())
        assert callable(lb.get_report_grounding_validator()) and callable(lb.get_report_grounding_validator())

    assert const_m.DefectVector is const_m.RSIDefectVector
    assert const_m.RSISessionReport is not None
    bad_py = tmp_path / "syn_err.py"
    bad_py.write_text("def x(:\n", encoding="utf-8")
    src_t, tree = const_m._get_cached_file_and_ast(bad_py)
    assert "def x" in src_t and tree is None
    stg_root = tmp_path / "repo_c" / ".staging"
    (stg_root.parent / ".agents").mkdir(parents=True)
    (stg_root.parent / ".agents" / "a.md").write_text("# A\n", encoding="utf-8")
    (stg_root / ".agents").mkdir(parents=True)
    (stg_root / ".agents" / "b.md").write_text("# B\n", encoding="utf-8")
    (stg_root / ".deleted_files.json").write_text(json.dumps([".agents/a.md"]), encoding="utf-8")
    assert [p.name for p in const_m._collect_overlay_md_files(stg_root, ".agents")] == ["b.md"]
    assert const_m.resolve_candidate_impl(stg_root, ".agents/a.md").parent.parent.name == "repo_c"
    rep_j = tmp_path / "sast_rep.json"
    rep_j.write_text(json.dumps({"metrics": {"sast_violations_count": 3}}), encoding="utf-8")
    assert const_m._extract_sast_report_count(rep_j) == 3
    rep_j.write_text(json.dumps({"violations": [1, 2]}), encoding="utf-8")
    assert const_m._extract_sast_report_count(rep_j) == 2
    assert const_m.load_staging_deleted_set_impl(stg_root.parent) == {".agents/a.md"}


@pytest.mark.fast
def test_r4_s3_rsi_benchmark_and_vibe_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre run_vibe_check_impl (errori lettura/ast/json) e run_benchmark_suite_impl (overlay/empty/err)."""
    _rsi_mod._ensure_exports_loaded()
    bv = importlib.import_module("_internal.rsi_convergence_engine.benchmark_and_vibe")
    eng = _rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path)

    ws = tmp_path / "vibe_ws"
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "bad.json").write_text("{bad", encoding="utf-8")
    (ws / ".staging").mkdir(parents=True)
    (ws / ".staging" / "bad.py").write_text("def x(:\n", encoding="utf-8")
    (ws / ".staging" / "bad.md").write_text("# H\n" + "word " * 30 + ".\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(bv, "get_ast_guard_validator", lambda: None)
        res_v = bv.run_vibe_check_impl(eng, ws)
        assert res_v["passed"] is False and len(res_v["violations"]) >= 2 and len(res_v["ste100_warnings"]) >= 1
        mp.setattr(Path, "read_text", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("unreadable")))
        res_err = bv.run_vibe_check_impl(eng, ws / ".staging" / "bad.py")
        assert not res_err["passed"] and "Errore lettura file" in res_err["violations"][0]

    b_ws = tmp_path / "bench_ws"
    (b_ws / "tests").mkdir(parents=True)
    (b_ws / "tests" / "test_one.py").write_text("def test_1(): assert True\n", encoding="utf-8")
    (b_ws / ".staging" / "tests").mkdir(parents=True)
    (b_ws / ".staging" / "tests" / "test_two.py").write_text("def test_2(): assert True\n", encoding="utf-8")
    (b_ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["tests/test_one.py"]), encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(bv.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout="collected 0 items", stderr=""))
        r_empty = bv.run_benchmark_suite_impl(eng, b_ws / "tests", root_dir=b_ws)
        assert r_empty["passed"] is False and "0 test" in r_empty["details"]
        (b_ws / ".staging" / ".deleted_files.json").write_text("{bad", encoding="utf-8")
        mp.delenv("PYTHONPATH", raising=False)
        mp.setattr(bv.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=1, stdout="1 passed", stderr=""))
        r_fail = bv.run_benchmark_suite_impl(eng, b_ws / "tests", root_dir=b_ws)
        assert r_fail["passed"] is False and r_fail["tests_failed"] >= 1
        mp.setattr(bv.subprocess, "run", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("sub")))
        r_exc = bv.run_benchmark_suite_impl(eng, "tests/test_two.py", root_dir=b_ws)
        assert r_exc["executed"] is False


@pytest.mark.fast
def test_r4_s3_rsi_loop_and_cove_edges(tmp_path: Path) -> None:
    """Copre tutte le guardie hard di loop_and_cove, telemetria corrotta, cycle/rollback e CoVe CLI."""
    _rsi_mod._ensure_exports_loaded()
    lc = importlib.import_module("_internal.rsi_convergence_engine.loop_and_cove")
    const_m = importlib.import_module("_internal.rsi_convergence_engine.constants")
    DV = const_m.RSIDefectVector

    base = DV(tests_passed=5, tests_failed=0, sast_critical=0, contract_violations=0, high_findings=0,
              poc_confirmed_exploits=0, semantic_drift_findings=0, deception_gaming_count=0, hallucinated_refs=0)
    for field in ("tests_failed", "sast_critical", "contract_violations", "high_findings",
                  "poc_confirmed_exploits", "semantic_drift_findings", "deception_gaming_count", "hallucinated_refs"):
        reg, _ = lc.check_hard_gate_regression_impl(base, base.model_copy(update={field: 1}))
        assert reg is True
    assert lc.check_hard_gate_regression_impl(base.model_copy(update={"doc_drift": 1}), base.model_copy(update={"doc_drift": 1}), strict_monotonic=True)[0] is True
    assert len(lc.compute_files_state_hash_impl([tmp_path / "missing_file.py"])) == 64

    eng = _rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path)
    eng.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    eng.telemetry_path.write_text("\n{bad\n", encoding="utf-8")
    assert lc.get_last_telemetry_hash_impl(eng) == "0" * 64
    assert lc.verify_telemetry_chain_impl(eng)[0] is False
    rec_good = eng.append_telemetry_record(const_m.RSIIterationRecord(
        session_id="S1", iteration=0, mode="mode_a", defects=base, delta_k=0, fitness_q=100.0, state_hash="a" * 64, verdict="PASS"
    ))
    raw_rec = json.loads(rec_good.model_dump_json())
    raw_rec["prev_hash"] = "f" * 64
    eng.telemetry_path.write_text("\n" + json.dumps(raw_rec) + "\n", encoding="utf-8")
    assert "prev_hash" in lc.verify_telemetry_chain_impl(eng)[2]
    raw_rec["prev_hash"] = "0" * 64
    raw_rec["record_hash"] = "e" * 64
    eng.telemetry_path.write_text(json.dumps(raw_rec) + "\n", encoding="utf-8")
    assert "record_hash" in lc.verify_telemetry_chain_impl(eng)[2]

    tfile = tmp_path / "scripts" / "tracked.py"
    tfile.parent.mkdir(parents=True, exist_ok=True)
    tfile.write_text("V = 0\n", encoding="utf-8")
    rep_cyc = lc.run_convergence_loop_impl(eng, lambda _k: base.model_copy(update={"doc_drift": 1}), target_files=[tfile], mode="mode_c")
    assert rep_cyc.final_status == "HALTED_CYCLE_DETECTED"
    step_f = {"n": 0}
    def _ref_change(_k: int, _d: Any) -> bool:
        step_f["n"] += 1
        tfile.write_text(f"V = {step_f['n']}\n", encoding="utf-8")
        return True
    rep_max = lc.run_convergence_loop_impl(
        eng,
        lambda k: base.model_copy(update={"doc_drift": 1, "sast_critical": 1 if k == 1 else 0}),
        refine_fn=_ref_change, target_files=[tfile], mode="mode_c",
    )
    assert rep_max.rollbacks_count == 1 and rep_max.final_status == "ROLLED_BACK_HARD_GATE"
    assert lc.extract_script_supported_flags_impl(tmp_path / "no_script.py") == set()
    tfile.write_text("import sys\n_x = '--demo' in sys.argv\n", encoding="utf-8")
    assert "--demo" in lc.extract_script_supported_flags_impl(tfile)
    (tmp_path / "doc.md").write_text("Run scripts/tracked.py --demo\n", encoding="utf-8")
    assert lc.verify_cli_flags_cove_impl(eng, root_dir=tmp_path)["passed"] is True


@pytest.mark.fast
def test_r4_s3_rsi_gt14_bundle_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre _load_probe_module e i rami with_dast, ast_guard violazioni/errori e cleanup di gt14_bundle."""
    _rsi_mod._ensure_exports_loaded()
    gb = importlib.import_module("_internal.rsi_convergence_engine.gt14_bundle")
    eng = _rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path)

    custom_p = tmp_path / "scripts" / "custom_probe_x.py"
    custom_p.parent.mkdir(parents=True)
    custom_p.write_text("PROBE_VAL = 7\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.delitem(sys.modules, "custom_probe_x", raising=False)
        assert gb._load_probe_module(tmp_path, "custom_probe_x").PROBE_VAL == 7
        assert gb._load_probe_module(tmp_path, "json").__name__ == "json"

    (tmp_path / ".agents" / "skills" / "sk1").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "sk1" / "SKILL.md").write_text("# SK1\n", encoding="utf-8")
    (tmp_path / ".staging" / "scripts").mkdir(parents=True)
    (tmp_path / ".staging" / "scripts" / "bad_sast.py").write_text("eval('1')\n", encoding="utf-8")
    (tmp_path / "nk_tracking").mkdir(parents=True)
    (tmp_path / "nk_tracking" / "quality_baseline.json").write_text(json.dumps({"metrics": {"unit_tests_passed": {"value": 1, "direction": "higher_is_better"}}}), encoding="utf-8")

    fake_dast = SimpleNamespace(run_staging_shadow_verification=lambda **_kw: {
        "passed": True,
        "pytest": {"executed": True, "tests_passed": 5, "tests_failed": 0, "tests_skipped": 0, "tests_total": 5, "duration_s": 0.5, "branch_coverage_pct": 99.0},
    })
    orig_loader = gb._load_probe_module
    with monkeypatch.context() as mp:
        mp.setattr(gb, "_load_probe_module", lambda r, n: fake_dast if n == "dast_sandbox_runner" else (
            (_ for _ in ()).throw(RuntimeError(n)) if n in ("nk_registry_indexer", "preflight_health_check") else orig_loader(r, n)
        ))
        res_b = gb.emit_gt14_bundle_impl(eng, workspace_root=tmp_path, with_dast=True, output_path=tmp_path / "out_bundle.json")
        assert res_b["probes"]["ast_guard"]["passed"] is False
        assert res_b["probes"]["quality_baseline"]["live_tests_measured"] is True
        mp.setattr(gb, "_load_probe_module", lambda r, n: (_ for _ in ()).throw(RuntimeError(n)))
        mp.setattr(eng, "verify_ecosystem", lambda **_kw: (_ for _ in ()).throw(RuntimeError("eco")))
        res_err = gb.emit_gt14_bundle_impl(eng, workspace_root=tmp_path, with_dast=True, output_path=tmp_path / "out_err.json")
        assert res_err["probes"]["dast_overlay"]["status"] == "ERROR" and res_err["probes"]["rsi_verify"]["status"] == "ERROR"


@pytest.mark.fast
def test_r4_s3_rsi_ecosystem_verify_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre _audit_markdown_docs, _audit_gt14_governance fallback e verify_ecosystem_impl."""
    _rsi_mod._ensure_exports_loaded()
    ev = importlib.import_module("_internal.rsi_convergence_engine.ecosystem_verify")
    eng = _rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path)

    (tmp_path / ".agents").mkdir(parents=True)
    (tmp_path / ".agents" / "AGENTS.md").write_text("[RULE-STE100]\n" + "long sentence " * 1900, encoding="utf-8")
    (tmp_path / ".agents" / "skills" / "demo").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").write_text("[link](resources/missing.txt)\n", encoding="utf-8")
    (tmp_path / "dirty.tmp").write_text("x", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "nk_registry_indexer", None)
        mp.setitem(sys.modules, "scripts.nk_registry_indexer", None)
        res = ev.verify_ecosystem_impl(eng, root_dir=tmp_path, strict_verify=True)
        assert res["passed"] is False and any("AGENTS.md" in v for v in res["violations"])

    flat_root = tmp_path / "flat_md"
    flat_root.mkdir()
    (flat_root / "a.md").write_text("[ok](https://example.com) [broken](no_file.md)\n", encoding="utf-8")
    (flat_root / "b.md").write_text("[ok](https://example.com) [broken](no_file.md)\n", encoding="utf-8")
    md_chk = ev._audit_markdown_docs(eng, flat_root, "code_rsi", [], [])
    assert md_chk["passed"] is False and len(md_chk["broken_links"]) == 1

    gt_root = tmp_path / "gt_only"
    (gt_root / ".agents" / "skills" / "s").mkdir(parents=True)
    (gt_root / ".agents" / "skills" / "s" / "SKILL.md").write_text("# S\n", encoding="utf-8")
    (gt_root / "scripts").mkdir(parents=True)
    (gt_root / "scripts" / "nk_registry_indexer.py").write_text(
        "class NKRegistryIndexer:\n"
        "    def __init__(self, workspace_root=None): pass\n"
        "    def verify_gt14_crit01_governance(self): return {'passed': False, 'issues': []}\n",
        encoding="utf-8",
    )
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "nk_registry_indexer", None)
        mp.setitem(sys.modules, "scripts.nk_registry_indexer", None)
        issues, _ = ev._audit_gt14_governance(gt_root, [], [])
        assert len(issues) == 1
        (gt_root / "scripts" / "nk_registry_indexer.py").write_text("raise RuntimeError('nri_err')\n", encoding="utf-8")
        issues_err, gt_err = ev._audit_gt14_governance(gt_root, [], [])
        assert gt_err["passed"] is False and len(issues_err) == 1


@pytest.mark.fast
def test_r4_s3_repo_mapper_facade_and_symbol_extractor(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre ast_repo_mapper main CLI e rami SymbolExtractor (default unparse err, posonly, CALL, TYPE_REFERENCE)."""
    _map_mod._ensure_exports_loaded()
    se_mod = importlib.import_module("_internal.ast_repo_mapper.symbol_extractor")
    rm_models = importlib.import_module("_internal.ast_repo_mapper.models")

    hub_parent = tmp_path / "hub_parent"
    (hub_parent / "NK_Hub" / "scripts").mkdir(parents=True)
    (hub_parent / "NK_Hub" / "scripts" / "m.py").write_text("def hello() -> None:\n    pass\n", encoding="utf-8")
    snap_out = tmp_path / "snap_map.md"
    with monkeypatch.context() as mp:
        mp.chdir(hub_parent)
        mp.setattr(_map_mod.sys, "argv", ["ast_repo_mapper.py", "--root", ".", "--snapshot-out", str(snap_out)])
        mp.setattr(_map_mod.sys, "stdout", SimpleNamespace(encoding=None, write=lambda _s: 0, flush=lambda: None))
        _map_mod.main()
        assert snap_out.exists()
        mp.setattr(_map_mod.sys, "argv", ["ast_repo_mapper.py", "--root", str(hub_parent / "NK_Hub"), "--symbol", "hello"])
        _map_mod.main()

    src = (
        "class Base:\n    pass\n\n"
        "class Child(Base):\n"
        "    def m(self, a: int, /, b: int = 1, *, c: Base = None) -> Base:\n"
        "        self.helper()\n        return Base()\n"
        "    def helper(self) -> None:\n        pass\n"
    )
    lines = src.splitlines(keepends=True)
    import ast as _ast
    tree = _ast.parse(src)
    ext = se_mod.SymbolExtractor(module_path="m.py", source_lines=lines)
    ext.visit(tree)
    assert any(e.edge_type == rm_models.EdgeType.INHERITANCE for e in ext.graph.edges)
    assert any(e.edge_type == rm_models.EdgeType.TYPE_REFERENCE for e in ext.graph.edges)
    assert any(e.edge_type == rm_models.EdgeType.CALL for e in ext.graph.edges)
    with monkeypatch.context() as mp:
        fn_node = [n for n in tree.body[1].body if isinstance(n, _ast.FunctionDef)][0]
        fail_nodes = {fn_node.returns, *fn_node.args.defaults, *fn_node.args.kw_defaults}
        orig_unparse = se_mod.ast.unparse
        mp.setattr(se_mod.ast, "unparse", lambda n: (_ for _ in ()).throw(ValueError("u")) if n in fail_nodes else orig_unparse(n))
        sig = ext._format_signature(fn_node)
        assert "=..." in sig


@pytest.mark.fast
def test_r4_s3_repo_mapper_polyglot_and_cache(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre PolyglotExtractor (HTM, arrow TS, TSX JSX, duplicate edges/CSS/HTML) e AtomicCacheManager."""
    _map_mod._ensure_exports_loaded()
    pc = importlib.import_module("_internal.ast_repo_mapper.polyglot_and_cache")

    assert pc.PolyglotExtractor.extract_symbols("note.txt", "hello") == []
    htm_nodes = pc.PolyglotExtractor.extract_symbols("p.htm", "<div id='a'></div><span id='a'></span>")
    assert len(htm_nodes) == 1
    assert pc.PolyglotExtractor._extract_css("a.css", ".btn { }\n.btn { }\n")[0].name == ".btn"
    ts_src = (
        "export const arrowFn = (x: number) => {\n"
        "  Widget();\n  Widget();\n  return <Widget />;\n};\n"
        "function multilineNoBrace(\n  a,\n  b)\n"
        "function Widget() {\n  return 1;\n}\n"
    )
    nodes = pc.PolyglotExtractor.extract_symbols("app.tsx", ts_src)
    edges, calls = pc.PolyglotExtractor.extract_call_edges("app.tsx", ts_src, nodes=nodes)
    assert len(edges) == 1 and "Widget" in calls["app.tsx:arrowFn"]
    assert pc.PolyglotExtractor.extract_call_edges("empty.ts", "// empty") == ([], {})

    cache_p = tmp_path / "cache.json"
    with monkeypatch.context() as mp:
        mp.setattr(pc, "atomic_write_json", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("wr")))
        assert pc.AtomicCacheManager.save_atomic({"a": 1}, cache_p) is False
        cache_p.write_text("{bad", encoding="utf-8")
        mp.setattr(pc.time, "sleep", lambda _s: None)
        assert pc.AtomicCacheManager.load_safe(cache_p, max_retries=2) is None
        mp.setattr(pc.json, "load", lambda _f: (_ for _ in ()).throw(OSError("io")))
        assert pc.AtomicCacheManager.load_safe(cache_p, max_retries=2) is None


@pytest.mark.fast
def test_r4_s3_repo_mapper_rendering_and_ranking(tmp_path: Path) -> None:
    """Copre map_rendering (budget stretto, solo costanti, hard_cap) e ranking_and_slicing (PPR & Karpathy)."""
    _map_mod._ensure_exports_loaded()
    mr = importlib.import_module("_internal.ast_repo_mapper.map_rendering")
    rs = importlib.import_module("_internal.ast_repo_mapper.ranking_and_slicing")
    rm_models = importlib.import_module("_internal.ast_repo_mapper.models")

    assert mr.compact_sig_for_ste100_impl("def fn(a, b, c) -> VeryLongReturnTypeAnnotationName:", max_words=4) == "def fn(a, b, c)"
    priv_cls = rm_models.SymbolNode(id="m.py:C", name="C", symbol_type=rm_models.SymbolType.CLASS, module_path="m.py", line_start=1, line_end=2)
    priv_methods = [
        rm_models.SymbolNode(id=f"m.py:C._m{i}", name=f"_m{i}", symbol_type=rm_models.SymbolType.METHOD, module_path="m.py", parent_id="m.py:C", line_start=i + 2, line_end=i + 2)
        for i in range(9)
    ]
    pub_fns = [
        rm_models.SymbolNode(id=f"m.py:f{i}", name=f"f{i}", symbol_type=rm_models.SymbolType.FUNCTION, module_path="m.py", line_start=i + 15, line_end=i + 15)
        for i in range(9)
    ]
    const_only = rm_models.SymbolNode(id="c.py:K", name="K", symbol_type=rm_models.SymbolType.CONSTANT, module_path="c.py", line_start=1, line_end=1)
    assert "_m0" in mr.render_inline_compact_module_impl("m.py", [priv_cls, *priv_methods, *pub_fns])
    assert "symbols" in mr.render_inline_compact_module_impl("c.py", [const_only])

    graph = rm_models.SymbolGraph()
    for i in range(13):
        mod = f"scripts/mod_{i:02d}.py"
        nid = f"{mod}:K" if i == 12 else f"{mod}:fn_{i}"
        ntype = rm_models.SymbolType.CONSTANT if i == 12 else rm_models.SymbolType.FUNCTION
        graph.add_node(rm_models.SymbolNode(id=nid, name=nid.split(":")[1], symbol_type=ntype, module_path=mod, line_start=1, line_end=1))
    graph.add_node(rm_models.SymbolNode(id="tests/test_x.py:test_x", name="test_x", symbol_type=rm_models.SymbolType.FUNCTION, module_path="tests/test_x.py", line_start=1, line_end=1))
    graph.add_edge(rm_models.SymbolEdge(source_id="ghost:1", target_id="scripts/mod_00.py:fn_0", edge_type=rm_models.EdgeType.CALL))
    graph.add_edge(rm_models.SymbolEdge(source_id="scripts/mod_00.py:fn_0", target_id="ghost:2", edge_type=rm_models.EdgeType.CALL))
    ppr = rs.PersonalizedPageRank.compute(graph, target_symbol_ids={"scripts/mod_00.py:fn_0", "ghost:3"}, max_iter=1)
    rendered_tight, _ = mr.render_two_tier_map_impl(tmp_path, graph, ppr.scores, set(), max_tokens=50)
    rendered_prod, _ = mr.render_two_tier_map_impl(tmp_path, graph, ppr.scores, set(), max_tokens=1024)
    assert "REPO-MAP" in rendered_tight and "REPO-MAP" in rendered_prod

    py_src = "K = 1\nclass Empty:\n    pass\nclass Box:\n    def keep(self):\n        return 1\n    def drop(self):\n        return 2\n"
    sl = rs.KarpathySurgicalSlicer.slice_module(py_src, ["module.py:Box.keep"], max_tokens=22)
    assert "Box" in sl.sliced_code or "# " in sl.sliced_code
    sl_tiny = rs.KarpathySurgicalSlicer.slice_module(py_src, ["keep", "drop", "Empty"], max_tokens=5)
    assert sl_tiny.sliced_code.strip() != ""


@pytest.mark.fast
def test_r4_s3_dast_extra_branch_edges(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Chiude ulteriori rami su Thread32, symlink interno, cleanup fallito, watchdog e overlay DAST."""
    del isolated_nk_env
    fake_k32 = SimpleNamespace(
        CreateToolhelp32Snapshot=lambda *_a: 77,
        Thread32First=lambda *_a: False,
        Thread32Next=lambda *_a: False,
        Process32First=lambda *_a: False,
        Process32Next=lambda *_a: False,
        OpenThread=lambda *_a: 0,
        ResumeThread=lambda *_a: 2,
        OpenProcess=lambda *_a: 55,
        CloseHandle=lambda _h: None,
    )
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod.sys, "platform", "win32")
        mp.setattr(_dast_mod, "_kernel32", fake_k32)
        assert _dast_mod._resume_process_primary_thread(10) is False
        res_cnt = {"n": 0}
        def _t32_first(_s: Any, te_ptr: Any) -> bool:
            te_ptr._obj.th32OwnerProcessID, te_ptr._obj.th32ThreadID = 10, 88
            return True
        def _resume(_h: Any) -> int:
            res_cnt["n"] += 1
            return 2 if res_cnt["n"] == 1 else 1
        fake_k32.Thread32First = _t32_first
        fake_k32.ResumeThread = _resume
        assert _dast_mod._resume_process_primary_thread(10) is False
        fake_k32.OpenThread = lambda *_a: 99
        assert _dast_mod._resume_process_primary_thread(10) is True
        mp.setattr(_dast_mod, "_get_process_memory_rss", _dast_mod._get_process_memory_rss)
        mp.setattr(_dast_mod, "_psapi", None)
        assert _dast_mod._get_process_memory_rss(10) == 0

    sb = _dast_mod.ShadowSandbox()
    sb.create()
    inner = sb.sandbox_dir / "link_in"
    inner.mkdir()
    orig_is_sym = Path.is_symlink
    with monkeypatch.context() as mp:
        mp.setattr(Path, "is_symlink", lambda self: True if self.name == "link_in" else orig_is_sym(self))
        assert _dast_mod._resolve_confined_sandbox_path(sb.sandbox_dir, "link_in/f.py") == (inner / "f.py").resolve()
        mp.setattr(_dast_mod.shutil, "rmtree", lambda *_a, **_kw: (_ for _ in ()).throw(PermissionError("locked")))
        mp.setattr(_dast_mod.time, "sleep", lambda _s: None)
        sb.cleanup()
    sb._is_active = True
    sb.cleanup()

    async def _run_empty() -> None:
        sb2 = _dast_mod.ShadowSandbox()
        cfg = _dast_mod.SandboxConfig(timeout_sec=2.0, poll_interval_sec=0.005, trace_coverage=True)
        runner = _dast_mod.DASTSandboxRunner(cfg)
        async def _ok_exec(*_cmd: str, **_kw: Any) -> Any:
            async def _comm() -> tuple[bytes, bytes]:
                await asyncio.sleep(0.02)
                return b"", b""
            return SimpleNamespace(pid=5555, returncode=0, communicate=_comm, wait=lambda: asyncio.sleep(0), kill=lambda: None)
        with monkeypatch.context() as mp:
            mp.setattr(_dast_mod.asyncio, "create_subprocess_exec", _ok_exec)
            mp.setattr(_dast_mod, "_create_kill_on_close_job", lambda: None)
            mp.setattr(_dast_mod, "_HAS_PSUTIL", False)
            sb2.write_file("t.py", "X = 1\n")
            rep1 = await runner.run_in_sandbox(sb2, [sys.executable], target_script_name="t.py")
            rep2 = await runner.run_in_sandbox(sb2, [], target_script_name="t.py")
            assert rep1.success and rep2.success
        sb2.cleanup()
    asyncio.run(_run_empty())


@pytest.mark.fast
def test_r4_s3_dast_overlay_symlinks_and_main_branches(
    tmp_path: Path, monkeypatch: Any, isolated_nk_env: Path
) -> None:
    """Copre rami overlay symlink esterni, data/__pycache__, ast_guard multipli e main CLI."""
    del isolated_nk_env
    repo = tmp_path / "repo_ov"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "data" / "__pycache__").mkdir(parents=True)
    (repo / "data" / "__pycache__" / "c.pyc").write_bytes(b"123")
    (repo / "data" / "nested").mkdir(parents=True)
    (repo / "data" / "nested" / "small.bin").write_bytes(b"abc")
    (repo / "ext_dir").mkdir()
    outside = tmp_path / "out_link"
    outside.mkdir()
    orig_sym, orig_res = Path.is_symlink, Path.resolve
    with monkeypatch.context() as mp:
        mp.setattr(Path, "is_symlink", lambda self: True if self.name in ("scripts", "ext_dir") else orig_sym(self))
        mp.setattr(Path, "resolve", lambda self, strict=False: outside if self.name in ("scripts", "ext_dir") else orig_res(self, strict=strict))
        res_no_stg = _dast_mod.run_staging_shadow_verification(repo, run_pytest=False, run_ast_guard=False)
        assert res_no_stg["passed"] is True

    (repo / ".staging").mkdir()
    (repo / ".staging" / "ext.py").write_text("Y = 2\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(Path, "is_symlink", lambda self: True if self.name == "ext.py" else orig_sym(self))
        mp.setattr(Path, "resolve", lambda self, strict=False: outside / "ext.py" if self.name == "ext.py" else orig_res(self, strict=strict))
        with pytest.raises(ValueError, match="Symlink esterno"):
            _dast_mod.run_staging_shadow_verification(repo, run_pytest=False, run_ast_guard=False)
    (repo / ".staging" / "ext.py").unlink()
    (repo / ".staging" / ".deleted_files.json").write_text(json.dumps(["missing_del.py"]), encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_dast_mod, "_run_job_isolated_subprocess", lambda *_a, **_kw: SimpleNamespace(returncode=2, stdout="", stderr=""))
        res_ag = _dast_mod.run_staging_shadow_verification(repo, run_pytest=False, run_ast_guard=True)
        assert res_ag["ast_guard"]["passed"] is False and res_ag["ast_guard"]["exit_code"] == 2
        mp.setattr(_dast_mod, "run_staging_shadow_verification", lambda **_kw: {"status": "PASS", "passed": True, "overlay_files_count": 0})
        rc_plain, out_plain, _ = call_script_main_captured(_dast_mod, ["--overlay-staging", str(repo)])
        assert rc_plain == 0 and "[DAST-OVERLAY-STAGING]" in out_plain

    one_scr = tmp_path / "one_scr"
    one_scr.mkdir()
    (one_scr / "run.py").write_text("print('hi')\n", encoding="utf-8")
    rc_one, out_one, _ = call_script_main_captured(_dast_mod, ["--script", str(one_scr / "run.py")])
    assert rc_one == 0 and "[DAST-SANDBOX]" in out_one


@pytest.mark.fast
def test_r4_s3_auto_heal_and_memory_remaining_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Chiude rami residui in auto_heal_pipeline, memory_3tier_engine, sbfl_engine e qbm."""
    with monkeypatch.context() as mp:
        mp.setattr(_heal_mod, "RSIDefectVector", None)
        mp.setattr(_heal_mod, "ASTGuardValidator", None)
        assert _heal_mod._build_defect_vector(None, "", 1, 0) is None
        _heal_mod._ensure_rsi_loaded()
        _heal_mod._ensure_ast_guard_loaded()
    assert _heal_mod.KarpathySlicer.slice_source("x = 1\ny = 2\n", target_line=1).function_name is None
    long_fn = "def big():\n" + "    a = 1\n" * 35
    assert _heal_mod.KarpathySlicer.slice_source("def small():\n    return 1\n\n" + long_fn, target_line=10).function_name == "big"

    target_f = tmp_path / "t.py"
    target_f.write_text("X = 1\n", encoding="utf-8")
    pipe = _heal_mod.AutoHealPipeline(cwd=tmp_path, max_cycles=2)
    pipe.rsi_engine = None
    seq = iter([
        (SimpleNamespace(passed_count=1, failed_count=2, exit_code=1), None),
        (SimpleNamespace(passed_count=2, failed_count=1, exit_code=1), None),
        (SimpleNamespace(passed_count=0, failed_count=3, exit_code=1), None),
    ])
    real_sid = pipe.snapshot_mgr.create_snapshot([target_f])
    pipe.snapshot_mgr.active_snapshots["same_snap"] = pipe.snapshot_mgr.active_snapshots[real_sid]
    with monkeypatch.context() as mp:
        mp.setattr(pipe.bridge, "run_and_diagnose", lambda **_kw: next(seq))
        mp.setattr(pipe.snapshot_mgr, "create_snapshot", lambda _f: "same_snap")
        rep = pipe.run_pipeline("pytest -q", target_f)
        assert rep.success is False
    with monkeypatch.context() as mp:
        fake_fail = _heal_mod.AutoHealSessionReport(success=False, cycles_used=1, max_cycles=1, initial_failed=1, final_failed=1, message="no_loc")
        mp.setattr(_heal_mod, "AutoHealPipeline", lambda **_kw: SimpleNamespace(run_pipeline=lambda **_k: fake_fail))
        rc_nf, out_nf, _ = call_script_main_captured(_heal_mod, ["--cwd", str(tmp_path), "--target-file", "t.py"])
        assert rc_nf == 1 and "no_loc" in out_nf
        fake_ok = _heal_mod.AutoHealSessionReport(success=True, cycles_used=0, max_cycles=1, initial_failed=0, final_failed=0, patch_note_line="", message="clean")
        mp.setattr(_heal_mod, "AutoHealPipeline", lambda **_kw: SimpleNamespace(run_pipeline=lambda **_k: fake_ok))
        rc_ok, out_ok, _ = call_script_main_captured(_heal_mod, ["--cwd", str(tmp_path), "--target-file", "t.py"])
        assert rc_ok == 0 and "[PATCH-NOTE]" not in out_ok

    assert _mem_mod._extract_significant_terms("ab") == set()
    with monkeypatch.context() as mp:
        mp.setattr(_mem_mod, "_win32_2pc_atomic_replace", None)
        mp.setattr(_mem_mod.os, "name", "posix")
        s_p, d_p = tmp_path / "ms.txt", tmp_path / "md.txt"
        s_p.write_text("v1", encoding="utf-8")
        _mem_mod.win32_atomic_replace(s_p, d_p, max_retries=1)
        assert d_p.read_text(encoding="utf-8") == "v1"
    eng_m = _mem_mod.ThreeTierMemoryEngine(base_dir=tmp_path / "m3")
    bad_gz = tmp_path / "no_magic.gz"
    bad_gz.write_bytes(b"not_gzip_at_all")
    assert eng_m._read_cold_archive(bad_gz) == []
    ep_pos = _mem_mod.MemoryEpisode(episode_id="p1", domain="OPS", title="Alpha", content="sharedtoken", vector=[1.0] * 64, metadata={"source_url": "", "evidence_quote": ""})
    ep_neg = _mem_mod.MemoryEpisode(episode_id="p2", domain="OPS", title="Alpha", content="sharedtoken", vector=[-1.0] * 64, metadata={"source_url": "u", "evidence_quote": "q"})
    eng_m.append_episode(ep_pos)
    eng_m.append_episode(ep_neg)
    q_vec = _mem_mod.DenseEmbedder.vector_from_text("sharedtoken")
    eng_m.append_episode(_mem_mod.MemoryEpisode(episode_id="p3", domain="OPS", title="Zero", content="sharedtoken", vector=[-x for x in q_vec]))
    assert isinstance(eng_m.recall_hybrid("OPS", "sharedtoken"), list)
    assert eng_m.consolidate_similar_episodes("OPS", threshold=0.9)["merged_count"] >= 1
    assert _mem_mod.sync_tier1_capsule(base_dir=eng_m.base_dir, profile="   ")["token_cap"] > 0


@pytest.mark.fast
def test_r4_s3_qbm_oracle_sbfl_remaining_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Chiude rami residui di quality_baseline_manager, oracle_evaluator_l3 e sbfl_engine."""
    ws = tmp_path / "qws"
    (ws / "tests" / "__pycache__").mkdir(parents=True)
    (ws / "tests" / "__pycache__" / "test_skip.py").write_text("x=1\n", encoding="utf-8")
    (ws / ".staging" / "tests" / "__pycache__").mkdir(parents=True)
    (ws / ".staging" / "tests" / "__pycache__" / "test_skip2.py").write_text("x=1\n", encoding="utf-8")
    (ws / ".staging" / "tests" / "test_ok.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": "not_list"}), encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_qbm_mod.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout="1 passed", stderr=""))
        res_q = _qbm_mod.measure_live_pytest_metrics(workspace_root=ws)
        assert res_q["unit_tests_passed"] == 1

    (ws / "nk_tracking").mkdir(parents=True)
    bl_p = ws / "nk_tracking" / "quality_baseline.json"
    (ws / "nk_tracking" / "oracle_lock.json").write_text(json.dumps({"files": "bad_type"}), encoding="utf-8")
    assert _qbm_mod._verify_oracle_lock_coherence(str(bl_p)) == []
    (ws / "nk_tracking" / "oracle_lock.json").unlink()
    _qbm_mod.update_baseline_metrics(str(bl_p), {"total_golden_tests": 100, "unit_tests_passed": 100, "pass_rate_pct": 100.0, "skills_audited": 10})
    comp_g, _ = _qbm_mod._evaluate_baseline_compliance(str(bl_p), {"golden_tests_68": {}, "skills_audited": 0}, allow_ratchet_down=True)
    assert comp_g["verdict"] == "FAIL"
    bl_low = tmp_path / "low_bl.json"
    bl_low.write_text(json.dumps({"metrics": {"unit_tests_passed": {"value": 40, "direction": "higher_is_better"}}}), encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_qbm_mod, "measure_live_pytest_metrics", lambda *_a, **_kw: {"total_golden_tests": 50, "unit_tests_passed": 50, "pass_rate_pct": 100.0})
        rc_lg, out_lg, _ = call_script_main_captured(_qbm_mod, ["--file", str(bl_low), "--live"])
        assert rc_lg == 1 and "live_metrics" in out_lg

    ev = _l3_mod.DOMOracleEvaluator()
    assert _l3_mod.resolve_expected_source("{not_json") == ("{not_json", "html")
    assert ev.evaluate_deltas(json.dumps({"html": "<div></div>"}), "<div></div>", expected_kind="json").verdict == "PASS"
    assert ev.evaluate_deltas("# `\n- #only\n", "<div></div>", expected_kind="md").verdict == "FAIL"
    assert ev.evaluate_deltas(json.dumps({"required_tags": ["   "]}), "<div></div>", expected_kind="json").verdict == "PASS"

    try:
        raise KeyError("k")
    except KeyError as exc:
        assert _sbfl_mod.SBFLEngine.extract_from_exception(exc, relevant_file_hint=None).line_number >= 1
    with monkeypatch.context() as mp:
        fake_sys = SimpleNamespace(gettrace=lambda: None, modules={}, monitoring=SimpleNamespace(get_tool=lambda _t: None))
        mp.setattr(_sbfl_mod, "sys", fake_sys)
        assert _sbfl_mod.is_monitoring_conflict_active() is False
        fake_sys.monitoring = SimpleNamespace()
        assert _sbfl_mod.is_monitoring_conflict_active() is False


@pytest.mark.fast
def test_r4_s3_rsi_remaining_submodules_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Chiude rami residui nei sottomoduli RSI (benchmark, loop, gt14, ecosystem, lazy_bridge, constants)."""
    _rsi_mod._ensure_exports_loaded()
    bv = importlib.import_module("_internal.rsi_convergence_engine.benchmark_and_vibe")
    lc = importlib.import_module("_internal.rsi_convergence_engine.loop_and_cove")
    gb = importlib.import_module("_internal.rsi_convergence_engine.gt14_bundle")
    ev = importlib.import_module("_internal.rsi_convergence_engine.ecosystem_verify")
    lb = importlib.import_module("_internal.rsi_convergence_engine.lazy_bridge")
    const_m = importlib.import_module("_internal.rsi_convergence_engine.constants")
    eng = _rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path)

    r_ag = tmp_path / "only_ag"
    (r_ag / ".agents").mkdir(parents=True)
    (r_ag / ".agents" / "x.md").write_text("# Ok\n", encoding="utf-8")
    assert bv.run_vibe_check_impl(eng, r_ag)["passed"] is True
    r_st = tmp_path / "only_st"
    (r_st / ".staging").mkdir(parents=True)
    (r_st / ".staging" / "x.md").write_text("# Ok\n", encoding="utf-8")
    assert bv.run_vibe_check_impl(eng, r_st)["passed"] is True
    t_json = r_st / "tasks_v1.json"
    t_json.write_text(json.dumps({"tasks": []}), encoding="utf-8")
    assert bv.run_benchmark_suite_impl(eng, "tasks_v1.json", root_dir=r_st)["executed"] is True
    (r_st / ".staging" / "rel_s").mkdir(parents=True)
    (r_st / ".staging" / "rel_s" / "test_a.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setenv("PYTHONPATH", "p1")
        mp.setattr(bv.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout="1 passed", stderr=""))
        assert bv.run_benchmark_suite_impl(eng, "rel_s", root_dir=r_st)["passed"] is True
        (r_st / "tests").mkdir()
        (r_st / ".staging" / "tests" / "__pycache__").mkdir(parents=True)
        (r_st / ".staging" / "tests" / "__pycache__" / "test_p.py").write_text("x=1\n", encoding="utf-8")
        (r_st / ".staging" / "tests" / "test_real.py").write_text("def test_r(): assert True\n", encoding="utf-8")
        assert bv.run_benchmark_suite_impl(eng, r_st / "tests", root_dir=r_st)["passed"] is True

    dv0 = const_m.RSIDefectVector(tests_passed=5, tests_total=5)
    assert lc.check_hard_gate_regression_impl(dv0, dv0, strict_monotonic=True)[0] is False
    with monkeypatch.context() as mp:
        mp.setattr(eng, "snapshot_mgr", None)
        assert lc.run_convergence_loop_impl(eng, lambda k: dv0 if k >= 1 else dv0.model_copy(update={"doc_drift": 1}), mode="mode_c").converged is True
    plain_py = tmp_path / "plain.py"
    plain_py.write_text("X = 1\n", encoding="utf-8")
    assert lc.extract_script_supported_flags_impl(plain_py) == set()
    (tmp_path / "cove.md").write_text("scripts/plain.py\nscripts/plain.py --x\nscripts/plain.py --x\n", encoding="utf-8")
    assert lc.verify_cli_flags_cove_impl(eng, root_dir=tmp_path)["checked_flags_count"] >= 2

    res_gt = gb.emit_gt14_bundle_impl(eng, workspace_root=r_ag, with_dast=False, strict_verify=False, output_path=tmp_path / "gb2.json")
    assert res_gt["probes"]["quality_baseline"]["status"] == "MISSING"
    with monkeypatch.context() as mp:
        mp.setattr(lb, "_HOOKS", {})
        mp.setattr(lb.sys, "stdout", SimpleNamespace(encoding="utf-8"))
        mp.setattr(lb.sys, "stderr", SimpleNamespace(encoding="utf-8"))
        mp.setitem(lb._FALLBACK_STATE, "streams_reconfigured", False)
        lb.fallback_reconfigure_streams()
        mp.setitem(sys.modules, "nk_transcript_tools", None)
        mp.setitem(sys.modules, "scripts.nk_transcript_tools", None)
        mp.setitem(lb._FALLBACK_STATE, "ste100_fn", None)
        mp.setitem(lb._FALLBACK_STATE, "grounding_fn", None)
        assert callable(lb.get_ste100_validator()) and callable(lb.get_report_grounding_validator())

    ev_root = tmp_path / "ev_r"
    (ev_root / "nk_tracking").mkdir(parents=True)
    (ev_root / "nk_tracking" / "rsi_telemetry.jsonl").write_text("{corrupt\n", encoding="utf-8")
    assert ev.verify_ecosystem_impl(eng, root_dir=ev_root)["checks"]["telemetry_chain"]["passed"] is False


@pytest.mark.fast
def test_r4_s3_repo_mapper_remaining_edges(tmp_path: Path, monkeypatch: Any) -> None:
    """Chiude rami residui nei moduli ast_repo_mapper (CLI, SymbolExtractor, Polyglot, Rendering, Slicing)."""
    _map_mod._ensure_exports_loaded()
    se_mod = importlib.import_module("_internal.ast_repo_mapper.symbol_extractor")
    pc = importlib.import_module("_internal.ast_repo_mapper.polyglot_and_cache")
    mr = importlib.import_module("_internal.ast_repo_mapper.map_rendering")
    rs = importlib.import_module("_internal.ast_repo_mapper.ranking_and_slicing")
    rm_models = importlib.import_module("_internal.ast_repo_mapper.models")

    (tmp_path / "mini_repo").mkdir()
    (tmp_path / "mini_repo" / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_map_mod.sys, "argv", ["ast_repo_mapper.py", "--root", str(tmp_path / "mini_repo"), "--json"])
        _map_mod.main()

    import ast as _ast
    ext_src = "class Child(ExtBase):\n    def f(self, *, kw: int):\n        self.f()\n        funcs[0]()\n"
    ext = se_mod.SymbolExtractor(module_path="x.py", source_lines=ext_src.splitlines(keepends=True))
    ext.visit(_ast.parse(ext_src))
    assert "kw" in ext.graph.nodes["x.py:Child.f"].signature

    js_edge = "function m(a)\n{\n  helper();\n}\nfunction helper() {}\n"
    edges_js, _ = pc.PolyglotExtractor.extract_call_edges("m.jsx", js_edge)
    assert len(edges_js) == 1
    assert pc.PolyglotExtractor._compute_js_block_end(["a", "b"], 5, 1) == 1

    assert mr.compact_sig_for_ste100_impl("def f(a) -> int:", max_words=10) == "def f(a) -> int:"
    priv_fns = [
        rm_models.SymbolNode(id=f"p.py:_f{i}", name=f"_f{i}", symbol_type=rm_models.SymbolType.FUNCTION, module_path="p.py", line_start=i + 1, line_end=i + 1)
        for i in range(9)
    ]
    assert "_f0" in mr.render_inline_compact_module_impl("p.py", priv_fns)
    imp_only = rm_models.SymbolNode(id="i.py:imp", name="os", symbol_type=rm_models.SymbolType.IMPORT, module_path="i.py", line_start=1, line_end=1)
    assert "symbols" not in mr.render_inline_compact_module_impl("i.py", [imp_only])

    g = rm_models.SymbolGraph()
    g.add_node(rm_models.SymbolNode(id="a.py:BigFn", name="BigFn", symbol_type=rm_models.SymbolType.FUNCTION, module_path="a.py", line_start=1, line_end=1, signature="def BigFn(a, b, c, d): ..."))
    txt_0, _ = mr.render_two_tier_map_impl(tmp_path, g, {}, set(), max_tokens=0)
    assert txt_0 == "\n"
    txt_trim, _ = mr.render_two_tier_map_impl(tmp_path, g, {}, set(), max_tokens=20)
    assert "REPO-MAP" in txt_trim

    doc_src = (
        "K = 1\n"
        "def helper():\n    '''Helper doc'''\n    return 1\n"
        "class Box:\n    '''Box doc'''\n"
        "    def focus(self):\n        return helper()\n"
        "    def other(self):\n        '''Other doc'''\n        return 2\n"
    )
    sl_doc = rs.KarpathySurgicalSlicer.slice_module(doc_src, ["Box.focus"], max_tokens=500)
    assert "Other doc" in sl_doc.sliced_code and "K = ..." in sl_doc.sliced_code
    sl_syn = rs.KarpathySurgicalSlicer.slice_module("def broken(:\n", ["broken"], max_tokens=50)
    assert sl_syn.token_count >= 0
    txt_mf, _, _ = rs.KarpathySurgicalSlicer._multi_focal_compress(g, {"a.py:BigFn"}, max_tokens=500)
    assert "def BigFn" in txt_mf

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suite Zero-Mock v6.4.0-Carbon: Copertura rami Shard 1 (Hook Gate, ACS FastGuard, AST Guard, Dual Ledgers, IO, 2PC).
Modulo: tests/test_r4_cov_shard1_hooks_sast.py.
"""

from __future__ import annotations

import ast
import ctypes
import io
import json
import os
import pkgutil
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

try:
    from conftest import (
        call_script_main_captured,
        load_script_by_relpath,
    )
except ImportError:
    from tests.conftest import (
        call_script_main_captured,
        load_script_by_relpath,
    )

_FG_MOD = load_script_by_relpath("nk_acs_fastguard", "scripts/nk_acs_fastguard.py")
_DL_MOD = load_script_by_relpath("dual_ledgers", "scripts/schemas/dual_ledgers.py")
_AST_MOD = load_script_by_relpath("ast_guard_validator", "scripts/ast_guard_validator.py")
_HOOK_MOD = load_script_by_relpath("nk_hook_gate", "scripts/nk_hook_gate.py")
_W2PC_MOD = load_script_by_relpath("win32_2pc_engine", "scripts/win32_2pc_engine.py")

from _internal.ast_guard_validator import (
    reexports as _ast_reexports,
    sast_call_checks as _ast_call_checks,
    sast_checker as _ast_sast_checker,
    sast_eval as _ast_sast_eval,
    scope_checker as _ast_scope_checker,
    signature_collector as _ast_sig_col,
    validator_helpers as _ast_val_helpers,
)
from _internal.nk_common import io as _nk_io
from _internal.nk_hook_gate import (
    json_io as _hg_json_io,
    path_safety as _hg_path_safety,
    shell_parser as _hg_shell_parser,
    shell_write_detector as _hg_write_det,
    stop_evidence as _hg_stop_ev,
    target_classifier as _hg_target_cls,
)
from _internal.win32_2pc_engine import (
    constants as _w2pc_consts,
    staging_guards as _w2pc_guards,
)


@pytest.mark.fast
def test_win32_2pc_constants_facade_and_lazy_ipc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Copre facade resolver, reload lazy IPC contracts, kernel32 fallback e hash."""
    assert _w2pc_consts._resolve_scripts_dir().name == "scripts"
    assert _w2pc_consts.compute_crc32("abc") == 0x352441C2
    assert len(_w2pc_consts.compute_sha256(b"abc")) == 64

    facade_stub = SimpleNamespace(
        IPCPointerReturn=None,
        TwoPhaseCommitPrepare=None,
        TwoPhaseCommitVerdict=None,
        _kernel32=SimpleNamespace(GetLastError=lambda: 7),
    )
    same_k32_facade = SimpleNamespace(_kernel32=_w2pc_consts._kernel32)
    empty_facade = SimpleNamespace(other_attr=1)
    monkeypatch.setattr(_w2pc_consts, "_FACADE_MODULES", [empty_facade, same_k32_facade, facade_stub])
    _w2pc_consts._register_facade_module(None)
    _w2pc_consts._register_facade_module(facade_stub)
    assert _w2pc_consts._get_facade_attr("_kernel32") is facade_stub._kernel32
    assert _w2pc_consts._get_facade_attr("Win32NamedMutex", None) is _W2PC_MOD.Win32NamedMutex
    assert _w2pc_consts._get_facade_attr("missing_attr_z9", "fb") == "fb"
    assert _w2pc_consts._get_active_kernel32() is facade_stub._kernel32

    monkeypatch.setattr(_w2pc_consts, "_FACADE_MODULES", [same_k32_facade])
    assert _w2pc_consts._get_active_kernel32() is _w2pc_consts._kernel32

    monkeypatch.setattr(_w2pc_consts, "IPCPointerReturn", _w2pc_consts._UNSET)
    monkeypatch.setattr(_w2pc_consts, "TwoPhaseCommitPrepare", _w2pc_consts._UNSET)
    monkeypatch.setattr(_w2pc_consts, "TwoPhaseCommitVerdict", _w2pc_consts._UNSET)
    monkeypatch.setattr(_w2pc_consts, "_FACADE_MODULES", [facade_stub, empty_facade])
    stdlib_dir = str(Path(pkgutil.__file__).parent)
    monkeypatch.setattr(sys, "path", [stdlib_dir])
    monkeypatch.delitem(sys.modules, "schemas.nk_ipc_contracts", raising=False)
    monkeypatch.delitem(sys.modules, "schemas", raising=False)
    _w2pc_consts._ensure_ipc_contracts_loaded()
    assert _w2pc_consts.IPCPointerReturn is not _w2pc_consts._UNSET
    assert facade_stub.TwoPhaseCommitPrepare is _w2pc_consts.TwoPhaseCommitPrepare
    assert facade_stub.TwoPhaseCommitVerdict is _w2pc_consts.TwoPhaseCommitVerdict
    if sys.platform != "win32":
        last_err_state = {"val": 0}
        monkeypatch.setattr(
            _w2pc_consts.ctypes,
            "set_last_error",
            lambda v: last_err_state.__setitem__("val", int(v)),
            raising=False,
        )
        monkeypatch.setattr(
            _w2pc_consts.ctypes,
            "get_last_error",
            lambda: int(last_err_state["val"]),
            raising=False,
        )
    _w2pc_consts.ctypes.set_last_error(0)
    assert _w2pc_consts._get_win32_last_error() == 7
    _w2pc_consts.ctypes.set_last_error(5)
    assert _w2pc_consts._get_win32_last_error() == 5
    _w2pc_consts.ctypes.set_last_error(0)
    monkeypatch.setattr(_w2pc_consts, "_get_active_kernel32", lambda: None)
    assert _w2pc_consts._get_win32_last_error() == 0


@pytest.mark.fast
def test_win32_2pc_staging_guards_cleanup_and_purge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre validate_staging_json_files, _cleanup_promoted_staging e _purge_production_bytecode."""
    stg = tmp_path / ".staging"
    nested = stg / "sub" / "empty_leaf"
    nested.mkdir(parents=True)
    pc_dir = stg / "__pycache__"
    pc_dir.mkdir()
    pyc_f = pc_dir / "mod.pyc"
    pyc_f.write_bytes(b"123")
    tmp_f = stg / "artifact.tmp"
    tmp_f.write_text("tmp", encoding="utf-8")
    promoted_f = stg / "keep_promoted.txt"
    promoted_f.write_text("ok", encoding="utf-8")
    del_man = stg / ".deleted_files.json"
    del_man.write_text("[]", encoding="utf-8")
    bad_utf8 = stg / "bad_utf8.json"
    bad_utf8.write_bytes(b"\xff\xfe")
    ufffd_json = stg / "ufffd.json"
    ufffd_json.write_text('{"k": "\ufffd"}', encoding="utf-8")

    ok_val, errs = _w2pc_guards.validate_staging_json_files(
        stg,
        staging_files=[
            stg / "ignore.txt",
            stg / "missing_unreadable.json",
            bad_utf8,
            ufffd_json,
        ],
    )
    assert ok_val is False and len(errs) >= 3

    _w2pc_guards._cleanup_promoted_staging(
        stg, [promoted_f, stg / ".gitkeep", stg / "gone.txt"], deleted_manifest=del_man
    )
    assert (stg / ".gitkeep").is_file()
    assert not pyc_f.exists() and not tmp_f.exists() and not del_man.exists()

    repo = tmp_path / "repo_purge"
    for sub in ("scripts", "tests"):
        pc = repo / sub / "__pycache__"
        pc.mkdir(parents=True)
        (pc / "x.pyc").write_bytes(b"0")
        (repo / sub / "y.pyo").write_bytes(b"1")
    orig_rmtree = shutil.rmtree
    calls = {"n": 0}

    def _flaky_rmtree(p: Any, ignore_errors: bool = False) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            return
        orig_rmtree(p, ignore_errors=ignore_errors)

    monkeypatch.setattr(shutil, "rmtree", _flaky_rmtree)
    _w2pc_guards._purge_production_bytecode(repo)
    assert calls["n"] >= 2 and not (repo / "scripts" / "__pycache__").exists()


@pytest.mark.fast
def test_win32_2pc_staging_guards_ratchet(tmp_path: Path) -> None:
    """Copre tutti i rami di _verify_quality_baseline_ratchet."""
    dst_bl = tmp_path / "nk_tracking" / "quality_baseline.json"
    stg_bl = tmp_path / ".staging" / "nk_tracking" / "quality_baseline.json"
    dst_bl.parent.mkdir(parents=True)
    stg_bl.parent.mkdir(parents=True)

    dst_bl.write_text(
        json.dumps({"pass_rate_pct": 105.0, "metrics": {"unit_tests_pass_pct": 105.0}}),
        encoding="utf-8",
    )
    stg_bl.write_text(
        json.dumps({"pass_rate_pct": 100.0, "metrics": {"unit_tests_pass_pct": 100.0}}),
        encoding="utf-8",
    )
    with pytest.raises(_w2pc_consts.TwoPhaseCommitError):
        _w2pc_guards._verify_quality_baseline_ratchet(dst_bl, stg_bl)

    dst_bl.write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 50}}),
        encoding="utf-8",
    )
    stg_bl.write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": 100.0, "unit_tests_total": 10}}),
        encoding="utf-8",
    )
    with pytest.raises(_w2pc_consts.TwoPhaseCommitError):
        _w2pc_guards._verify_quality_baseline_ratchet(dst_bl, stg_bl, allow_ratchet_down=False)

    empty_bl = tmp_path / "empty_bl.json"
    empty_bl.write_text("{}", encoding="utf-8")
    with pytest.raises(_w2pc_consts.TwoPhaseCommitError):
        _w2pc_guards._verify_quality_baseline_ratchet(empty_bl)

    low_bl = tmp_path / "low_bl.json"
    low_bl.write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 80.0}}), encoding="utf-8")
    with pytest.raises(_w2pc_consts.TwoPhaseCommitError):
        _w2pc_guards._verify_quality_baseline_ratchet(low_bl)

    bad_lock_dir = tmp_path / "lock_chk"
    bad_lock_dir.mkdir()
    (bad_lock_dir / "oracle_lock.json").write_text("[]", encoding="utf-8")
    good_bl = bad_lock_dir / "quality_baseline.json"
    good_bl.write_text(json.dumps({"metrics": {"unit_tests_pass_pct": 100.0}}), encoding="utf-8")
    with pytest.raises(_w2pc_consts.TwoPhaseCommitError):
        _w2pc_guards._verify_quality_baseline_ratchet(good_bl)


@pytest.mark.fast
def test_win32_2pc_staging_guards_scan_and_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _scan_staging_canonical, reparse point esterno e record_session_anchor_commit."""
    scan_root = tmp_path / "scan_repo"
    stg_dir = scan_root / ".staging"
    (stg_dir / "scripts").mkdir(parents=True)
    (stg_dir / "ignored_dir").mkdir(parents=True)
    (stg_dir / ".git").mkdir(parents=True)
    (stg_dir / "scripts" / "ok.py").write_text("x=1\n", encoding="utf-8")
    (stg_dir / "scripts" / "skip.bak").write_text("b", encoding="utf-8")
    (stg_dir / "scripts" / ".deleted_files.json").write_text("[]", encoding="utf-8")
    (stg_dir / "ignored_dir" / "other.py").write_text("y=2\n", encoding="utf-8")

    orig_scandir = os.scandir
    sc_cnt = {"n": 0}

    def _scandir_once_err(p: Any) -> Any:
        sc_cnt["n"] += 1
        if sc_cnt["n"] == 1:
            raise OSError("unc_fail")
        return orig_scandir(p)

    with monkeypatch.context() as mp:
        mp.setattr(os, "scandir", _scandir_once_err)
        found = _w2pc_guards._scan_staging_canonical(stg_dir, scan_root, subdirs=["scripts"])
        assert [p.name for p in found] == ["ok.py"]

    _w2pc_guards.record_session_anchor_commit(
        scan_root, "MS-1", [{"relative_path": "scripts/ok.py"}], ["old.py"]
    )
    assert (scan_root / "nk_tracking" / "anchor" / "session_anchor.jsonl").is_file()

    monkeypatch.setattr(_w2pc_guards, "_is_reparse_point", lambda _p: False)
    monkeypatch.setattr(_w2pc_guards, "_assert_no_external_reparse", lambda *_a: None)

    class _FakeStat:
        st_file_attributes = _w2pc_consts.FILE_ATTRIBUTE_REPARSE_POINT

    class _FakeEntry:
        name = "link.py"

        def is_symlink(self) -> bool:
            return True

        def stat(self, follow_symlinks: bool = False) -> Any:
            return _FakeStat()

        def is_dir(self, follow_symlinks: bool = False) -> bool:
            raise OSError("stat fail")

        def is_file(self, follow_symlinks: bool = False) -> bool:
            raise OSError("stat fail")

    class _FakeCtx:
        def __enter__(self) -> List[Any]:
            return [_FakeEntry()]

        def __exit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(os, "scandir", lambda _p: _FakeCtx())
    monkeypatch.setattr(
        os.path,
        "realpath",
        lambda _p, *_a, **_kw: str(tmp_path / "outside_target.py"),
    )
    with pytest.raises(_w2pc_consts.TwoPhaseCommitError):
        _w2pc_guards._scan_staging_canonical(stg_dir, scan_root)


@pytest.mark.fast
def test_nk_common_io_long_path_and_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre win_long_path posix/resolved e unlink_with_retry su errori/FileNotFound."""
    p_obj = tmp_path / "sample.txt"
    with monkeypatch.context() as mp:
        mp.setattr(_nk_io.os, "name", "posix")
        res_posix = _nk_io.win_long_path(str(p_obj))
        assert not str(res_posix).startswith("\\\\?\\")

    with monkeypatch.context() as mp:
        if os.name != "nt":
            mp.setattr(_nk_io.os, "name", "nt")
        mp.setattr(Path, "resolve", lambda self: Path("\\\\?\\C:\\fake_resolved"))
        assert str(_nk_io.win_long_path(p_obj)).startswith("\\\\?\\")

    target_f = tmp_path / "locked.txt"
    target_f.write_text("data", encoding="utf-8")
    with monkeypatch.context() as mp:
        def _raise_fnf(self: Path, missing_ok: bool = False) -> None:
            raise FileNotFoundError("gone")

        mp.setattr(Path, "unlink", _raise_fnf)
        assert _nk_io.unlink_with_retry(target_f, delays=(0.0,)) is True

    with monkeypatch.context() as mp:
        def _raise_perm(self: Path, missing_ok: bool = False) -> None:
            raise PermissionError("busy")

        mp.setattr(Path, "unlink", _raise_perm)
        assert _nk_io.unlink_with_retry(target_f, delays=(0.0,), raise_on_error=False) is False
        with pytest.raises(PermissionError):
            _nk_io.unlink_with_retry(target_f, delays=(0.0,), raise_on_error=True)

    with monkeypatch.context() as mp:
        def _raise_other(self: Path, missing_ok: bool = False) -> None:
            raise OSError("fatal")

        mp.setattr(Path, "unlink", _raise_other)
        assert _nk_io.unlink_with_retry(target_f, delays=(0.0,), raise_on_error=False) is False


@pytest.mark.fast
def test_nk_common_io_atomic_write_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre tutti i rami di errore e reparse guard di atomic_write_bytes."""
    ok_rp, err_rp = _nk_io.atomic_write_bytes(
        tmp_path / "sub" / "a.bin", b"1", reparse_check=lambda _p: True
    )
    assert not ok_rp and err_rp == "reparse_guard"

    blocking_file = tmp_path / "not_a_dir"
    blocking_file.write_text("x", encoding="utf-8")
    ok_mk, err_mk = _nk_io.atomic_write_bytes(blocking_file / "child.bin", b"1")
    assert not ok_mk and err_mk is not None and err_mk.startswith("mkdir_error:")

    for trigger_call in (3, 4, 5):
        calls_chk = {"n": 0}

        def _nth_reparse(_p: Path, limit: int = trigger_call) -> bool:
            calls_chk["n"] += 1
            return calls_chk["n"] >= limit

        ok_nth, err_nth = _nk_io.atomic_write_bytes(
            tmp_path / f"late_{trigger_call}" / "b.bin", b"1", reparse_check=_nth_reparse
        )
        assert not ok_nth and err_nth == "reparse_guard"

    with monkeypatch.context() as mp:
        mp.setattr(_nk_io.os, "open", lambda *_a, **_kw: (_ for _ in ()).throw(FileExistsError("dup")))
        ok_ex, err_ex = _nk_io.atomic_write_bytes(tmp_path / "dup.bin", b"1")
        assert not ok_ex and err_ex == "tmp_allocation_exhausted"

    with monkeypatch.context() as mp:
        mp.setattr(_nk_io.os, "open", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("open_err")))
        ok_oe, err_oe = _nk_io.atomic_write_bytes(tmp_path / "oe.bin", b"1")
        assert not ok_oe and err_oe is not None and err_oe.startswith("open_tmp_error:")

    with monkeypatch.context() as mp:
        mp.setattr(_nk_io.os, "write", lambda _fd, _buf: 0)
        ok_sw, err_sw = _nk_io.atomic_write_bytes(tmp_path / "sw.bin", b"abc")
        assert not ok_sw and err_sw is not None and "Short write" in err_sw

    with monkeypatch.context() as mp:
        def _winerr_32(*_a: Any) -> None:
            e = OSError("sharing")
            e.winerror = 32
            raise e

        mp.setattr(_nk_io.os, "replace", _winerr_32)
        ok_w32, err_w32 = _nk_io.atomic_write_bytes(
            tmp_path / "w32.bin", b"abc", delays=(0.0, 0.0)
        )
        assert not ok_w32 and err_w32 is not None and err_w32.startswith("winerror_exhausted:")

    with monkeypatch.context() as mp:
        mp.setattr(_nk_io.os, "replace", lambda *_a: (_ for _ in ()).throw(OSError("generic")))
        ok_io, err_io = _nk_io.atomic_write_bytes(tmp_path / "ioe.bin", b"abc", delays=(0.0,))
        assert not ok_io and err_io is not None and err_io.startswith("io_error:")


@pytest.mark.fast
def test_dual_ledgers_integrity_and_pid_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copre TaskDAGNode.verify_integrity e PIDFileLock._is_pid_alive (POSIX e Win32)."""
    node = _DL_MOD.TaskDAGNode.create("t1", "BUILD", "NK-Orchestrator", payload={"k": 1})
    assert node.verify_integrity("0" * 64) is True
    assert node.verify_integrity("1" * 64) is False
    bad_payload = node.model_copy(update={"payload": {"k": 2}})
    assert bad_payload.verify_integrity("0" * 64) is False

    with monkeypatch.context() as mp:
        mp.setattr(_DL_MOD.os, "name", "posix")
        mp.setattr(_DL_MOD.os, "kill", lambda _pid, _sig: None, raising=False)
        assert _DL_MOD.PIDFileLock._is_pid_alive(1234) is True
        mp.setattr(
            _DL_MOD.os,
            "kill",
            lambda _pid, _sig: (_ for _ in ()).throw(PermissionError("deny")),
            raising=False,
        )
        assert _DL_MOD.PIDFileLock._is_pid_alive(1234) is True
        mp.setattr(
            _DL_MOD.os,
            "kill",
            lambda _pid, _sig: (_ for _ in ()).throw(OSError("dead")),
            raising=False,
        )
        assert _DL_MOD.PIDFileLock._is_pid_alive(1234) is False

    fake_k32_denied = SimpleNamespace(
        OpenProcess=lambda *_a: 0,
        GetLastError=lambda: _DL_MOD.ERROR_ACCESS_DENIED,
    )
    with monkeypatch.context() as mp:
        if os.name != "nt":
            mp.setattr(_DL_MOD.os, "name", "nt")
        mp.setattr(_DL_MOD, "_kernel32", fake_k32_denied)
        mp.setattr(_DL_MOD.ctypes, "get_last_error", lambda: 0, raising=False)
        assert _DL_MOD.PIDFileLock._is_pid_alive(555) is True

    fake_k32_bad_exit = SimpleNamespace(
        OpenProcess=lambda *_a: 123,
        GetExitCodeProcess=lambda *_a: False,
        CloseHandle=lambda _h: True,
    )
    with monkeypatch.context() as mp:
        if os.name != "nt":
            mp.setattr(_DL_MOD.os, "name", "nt")
        mp.setattr(_DL_MOD, "_kernel32", fake_k32_bad_exit)
        assert _DL_MOD.PIDFileLock._is_pid_alive(555) is False


@pytest.mark.fast
def test_dual_ledgers_stale_claim_and_lock_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _claim_stale_lock, acquire timeout/short-write e release."""
    lock_path = tmp_path / "lck" / "task.lock"
    lock_path.parent.mkdir(parents=True)
    lk = _DL_MOD.PIDFileLock(lock_path, stale_timeout_sec=10.0, acquire_timeout_sec=0.15)
    lk.release()
    lk._claim_stale_lock(os.getpid(), (999999, "n0", 0.0))

    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "nonce": "live", "timestamp": time.time()}),
        encoding="utf-8",
    )
    lk._claim_stale_lock(os.getpid(), (999999, "old", 0.0))
    assert lock_path.exists()
    assert lk.acquire(timeout_sec=0.0) is False
    with pytest.raises(TimeoutError):
        with lk:
            assert False

    lock_path.write_text("[]", encoding="utf-8")
    assert lk.acquire(timeout_sec=0.05) is False

    lock_path.write_text("corrupt{json", encoding="utf-8")
    lk._claim_stale_lock(os.getpid(), ("__corrupt__", 1))
    assert not lock_path.exists()

    with monkeypatch.context() as mp:
        mp.setattr(_DL_MOD.os, "write", lambda _fd, _b: 0)
        with pytest.raises(OSError):
            lk.acquire(timeout_sec=0.0)
    assert not lock_path.exists()


@pytest.mark.fast
def test_dual_ledgers_dag_and_progress_filtering(tmp_path: Path) -> None:
    """Copre TaskLedger blank lines/diamond DAG e ProgressLedger missing/blank/filter."""
    prog_path = tmp_path / "progress.jsonl"
    prog = _DL_MOD.ProgressLedger(prog_path)
    assert prog.read_events() == []
    prog.append_event("e1", "t1", 0, "STARTED", {"ok": True})
    prog.append_event("e2", "t2", 1, "CHECKPOINT", {"ok": True})
    with open(prog_path, "a", encoding="utf-8") as fh:
        fh.write("\n   \n")
    assert len(prog.read_events("t1")) == 1
    assert len(prog.read_events()) == 2

    dag_path = tmp_path / "tasks.jsonl"
    dag = _DL_MOD.TaskLedger(dag_path)
    dag.add_task("root", "INIT", "NK-Ideator")
    dag.add_task("left", "PLAN", "NK-Architect", parent_ids=["root"])
    dag.add_task("right", "AUDIT", "NK-Auditor", parent_ids=["root"])
    dag.add_task("join", "MERGE", "NK-Orchestrator", parent_ids=["left", "right"])
    with open(dag_path, "a", encoding="utf-8") as fh:
        fh.write("\n   \n")
    reloaded = _DL_MOD.TaskLedger(dag_path)
    ok_dag, msg = reloaded.verify_dag()
    assert ok_dag is True and "acyclic" in msg
    assert len(reloaded.get_roots()) == 1
    assert [n.task_id for n in reloaded.get_leaves()] == ["join"]


@pytest.mark.fast
def test_ast_guard_reexports_and_catalog_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre validate_pydantic_catalog_records e tutti i rami reexports."""
    class _PlainRow:
        def __init__(self, val: int) -> None:
            if val < 0:
                raise ValueError("neg")
            self.val = val

    rep_ok = _ast_reexports.validate_pydantic_catalog_records(
        [{"val": 1}, {"val": -1}], _PlainRow
    )
    assert rep_ok["passed"] is False and rep_ok["valid_records"] == 1

    hub = tmp_path / "hub"
    stg_scripts = hub / ".staging" / "scripts"
    prod_scripts = hub / "scripts"
    pkg_dir = prod_scripts / "pkg"
    stg_pkg = stg_scripts / "pkg"
    pkg_dir.mkdir(parents=True)
    stg_pkg.mkdir(parents=True)
    (stg_scripts / "a.py").write_text("def fa(): pass\n", encoding="utf-8")
    (prod_scripts / "a.py").write_text("def fa(): pass\n", encoding="utf-8")
    (hub / ".staging" / "direct.py").write_text("x = 1\n", encoding="utf-8")
    (pkg_dir / "star.py").write_text(
        "class PubCls:\n    def m(self): pass\nclass _PrivCls: pass\n"
        "def pub_fn(): pass\ndef _priv_fn(): pass\nPUB_G = 1\n_PRIV_G = 2\n",
        encoding="utf-8",
    )
    (pkg_dir / "bad.py").write_text("def broken(:\n", encoding="utf-8")

    with monkeypatch.context() as mp:
        mp.setattr(Path, "resolve", lambda self: (_ for _ in ()).throw(OSError("res")))
        roots_err, _ = _ast_reexports._resolve_local_import_roots(str(stg_scripts / "a.py"))
        assert isinstance(roots_err, list)

    roots_stg, cur_stg = _ast_reexports._resolve_local_import_roots(str(stg_scripts / "a.py"))
    assert prod_scripts.resolve() in roots_stg and cur_stg is not None
    roots_prod, _ = _ast_reexports._resolve_local_import_roots(str(prod_scripts / "a.py"))
    assert stg_scripts.resolve() in roots_prod
    roots_direct, _ = _ast_reexports._resolve_local_import_roots(
        str(hub / ".staging" / "direct.py")
    )
    assert stg_scripts.resolve() in roots_direct

    try_tree = ast.parse("try:\n    from pkg.star import *\nexcept Exception:\n    from pkg.bad import x\n")
    imps = _ast_reexports._iter_top_level_import_from(try_tree)
    assert len(imps) == 2

    assert _ast_reexports._resolve_import_from_module_file(ast.parse("from . import a").body[0], roots_prod, None) is None
    assert _ast_reexports._resolve_import_from_module_file(ast.parse("from . import a").body[0], [stg_scripts], tmp_path) is None
    assert _ast_reexports._resolve_import_from_module_file(ast.parse("from . import *").body[0], roots_prod, pkg_dir, alias_name="*") is None
    raw_imp = ast.ImportFrom(module=None, names=[ast.alias(name="x", asname=None)], level=0)
    assert _ast_reexports._resolve_import_from_module_file(raw_imp, roots_prod, pkg_dir) is None

    cache: Dict[Path, Any] = {}
    c_star = _ast_reexports._collect_resolved_module(pkg_dir / "star.py", roots_prod, True, set(), cache)
    assert _ast_reexports._collect_resolved_module(pkg_dir / "star.py", roots_prod, False, set(), cache) is c_star
    dst = _ast_sig_col.SignatureCollector()
    _ast_reexports._merge_symbol_from_collector(c_star, "*", "*", dst)
    assert "PubCls" in dst.classes and "_PrivCls" not in dst.classes
    assert "pub_fn" in dst.signatures and "_priv_fn" not in dst.signatures
    assert "PUB_G" in dst.defined_globals and "_PRIV_G" not in dst.defined_globals


@pytest.mark.fast
def test_ast_guard_signature_collector_and_helpers() -> None:
    """Copre SignatureCollector (nested class, type_params, AsyncFor/With, TypeAlias, *args/**kwargs) e validator_helpers."""
    code = (
        "from typing import Any\n"
        "type AliasT[T] = list[T]\n"
        "class Box[U]:\n    pass\n"
        "async def outer_fn(*args: int, **kwargs: str) -> None:\n"
        "    import json\n"
        "    from os import path\n"
        "    class Inner:\n        pass\n"
        "    type LocalT = int\n"
        "async for item in aiter_x:\n    pass\n"
        "with ctx():\n    pass\n"
        "async with actx() as res:\n    pass\n"
    )
    col = _ast_sig_col.SignatureCollector()
    col.visit(ast.parse(code))
    assert "AliasT" in col.defined_globals
    assert "Box" in col.classes and "Inner" not in col.classes
    assert "item" in col.defined_globals and "res" in col.defined_globals
    assert col.signatures["outer_fn"].annotations["args"] == "int"
    assert col.signatures["outer_fn"].annotations["kwargs"] == "str"

    col_plain = _ast_sig_col.SignatureCollector()
    col_plain.visit_TypeAlias(SimpleNamespace(_fields=(), name="StrAlias"))
    col_plain.visit_TypeAlias(SimpleNamespace(_fields=(), name=123))
    assert "StrAlias" in col_plain.defined_globals

    violations: List[Any] = []
    _ast_val_helpers.verify_classes_impl(
        {
            "AllowedCls": [],
            "SignatureDriftDetector": [],
            "_PrivCls": [],
            "PublicDeleted": [],
            "SubCls": ["BaseA"],
        },
        {"SubCls": ["object"]},
        {"AllowedCls"},
        violations,
        target_file="scripts/ast_guard_validator.py",
    )
    v_syms = {v.symbol_name for v in violations}
    assert "PublicDeleted" in v_syms and "SubCls" in v_syms
    assert "_PrivCls" not in v_syms and "SignatureDriftDetector" not in v_syms


@pytest.mark.fast
def test_ast_guard_validator_helpers_signatures_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre verify_signatures_impl, _resolve_production_counterpart e _write_json_atomic error."""
    pre_code = (
        "async def f_async(a: int, /, b: str = 'x', *args: int, k: int = 1, **kw: Any) -> int:\n    return 1\n"
        "def f_pos(a: int, b: int = 1) -> None:\n    pass\n"
        "def f_def(a: int = 1) -> None:\n    pass\n"
        "def f_same(a: int = 1) -> None:\n    pass\n"
    )
    post_code = (
        "def f_async(a: int, b: str = 'x', *, k: int = 1) -> int:\n    return 1\n"
        "def f_pos(x: int, y: int = 1) -> None:\n    pass\n"
        "def f_def(a: int) -> None:\n    pass\n"
        "def f_same(a: int = 1, b: int = 2) -> None:\n    pass\n"
    )
    c1 = _ast_sig_col.SignatureCollector()
    c1.visit(ast.parse(pre_code))
    c2 = _ast_sig_col.SignatureCollector()
    c2.visit(ast.parse(post_code))
    violations: List[Any] = []
    _ast_val_helpers.verify_signatures_impl(c1.signatures, c2.signatures, set(), violations)
    msgs = " | ".join(v.message for v in violations)
    assert "Async modifier altered" in msgs
    assert "Positional-only arguments changed" in msgs
    assert "Variadic positional (*args) changed" in msgs
    assert "Variadic keyword (**kwargs) changed" in msgs
    assert "Positional arguments changed" in msgs
    assert "Default parameter count changed" in msgs

    ws = tmp_path / "ws"
    ext_stg = tmp_path / "other" / ".staging" / "scripts" / "m.py"
    ext_stg.parent.mkdir(parents=True)
    ext_stg.write_text("x=1\n", encoding="utf-8")
    ws_prod = ws / "scripts" / "m.py"
    ws_prod.parent.mkdir(parents=True)
    ws_prod.write_text("x=0\n", encoding="utf-8")
    assert _ast_val_helpers._resolve_production_counterpart(ext_stg, ws) == ws_prod
    assert _ast_val_helpers._resolve_production_counterpart(ws_prod, ws) is None

    monkeypatch.setattr(_ast_val_helpers, "atomic_write_json", lambda *_a, **_kw: (False, "disk_full"))
    with pytest.raises(OSError, match="disk_full"):
        _ast_val_helpers._write_json_atomic(tmp_path / "rep.json", {"ok": True})


@pytest.mark.fast
def test_ast_guard_scope_checker_patterns_typealias_and_comps() -> None:
    """Copre ScopeIntegrityChecker su Match, TypeAlias, nested comprehensions e walrus."""
    code = (
        "type Vec[T] = list[T]\n"
        "def f(items, subj, *extra):\n"
        "    match subj:\n"
        "        case [a, *rest] if a > 0:\n            pass\n"
        "        case [b, *_]:\n            pass\n"
        "        case {'k': mv, **mk}:\n            pass\n"
        "        case int(p) | str(p):\n            pass\n"
        "        case (1 | 2) as ma:\n            pass\n"
        "    res1 = [x for row in items for x in row if x]\n"
        "    res2 = {k: v for k, v in [(y := 1, y + 1)]}\n"
        "    res3 = {z for z in items}\n"
        "    res4 = (w for w in items)\n"
        "    return res1, res2, res3, res4\n"
    )
    sc = _ast_scope_checker.ScopeIntegrityChecker({"items", "subj"})
    sc._extract_pattern_bindings(None, set())
    sc.visit_TypeAlias(SimpleNamespace(_fields=(), name="PlainTA", type_params=[]))
    sc.visit_TypeAlias(SimpleNamespace(_fields=(), name=123, type_params=[]))
    sc.scope_future_locals = []
    sc._bind_name_in_current_scope("tmp_n")
    sc.deleted_stack = []
    assert "tmp_n" in sc._current_visible_names()

    sc2 = _ast_scope_checker.ScopeIntegrityChecker(set())
    sc2.visit(ast.parse(code))
    assert sc2.violations == []


@pytest.mark.fast
def test_ast_guard_scope_checker_funcs_classes_and_del() -> None:
    """Copre ScopeIntegrityChecker su decorators, PEP695, with/async with, except, lambda e del."""
    code = (
        "def dec(fn): return fn\n"
        "class Meta(type): pass\n"
        "class Base: pass\n"
        "@dec\n"
        "class C[T](Base, metaclass=Meta):\n"
        "    x: int\n"
        "@dec\n"
        "def outer[U](a=1, *, b=2, c=3):\n"
        "    import os, json as j\n"
        "    from sys import argv\n"
        "    global g_var\n"
        "    nonlocal_x = 0\n"
        "    def inner():\n"
        "        nonlocal nonlocal_x\n"
        "        with open('x') as fh:\n            pass\n"
        "        with open('y'):\n            pass\n"
        "        return fh, nonlocal_x\n"
        "    async def ainner():\n"
        "        async with a_ctx() as ac:\n            pass\n"
        "        async with a_ctx():\n            pass\n"
        "        return ac\n"
        "    try:\n        pass\n    except:\n        pass\n"
        "    fn = lambda p=1, *, q=2, r=3: p + q + r\n"
        "    u, v = 1, 2\n"
        "    del (u, v)\n"
        "    return fn, inner, ainner, os, j, argv\n"
    )
    sc = _ast_scope_checker.ScopeIntegrityChecker({"g_var", "a_ctx"})
    sc.visit(ast.parse(code))
    assert sc.violations == []


@pytest.mark.fast
def test_ast_guard_sast_eval_symbols_slices_and_truthy() -> None:
    """Copre tutte le funzioni di sast_eval su cicli, f-string, join, truthy, traversal, env e grant."""
    checker = _ast_sast_checker.SASTConstructChecker("src_app/mod.py")
    checker._symbol_aliases = {"a": "b", "b": "a"}
    assert _ast_sast_eval.resolve_symbol_expr(checker, ast.Name(id="a")) == "a"
    checker._symbol_aliases = {f"n{i}": f"n{i+1}" for i in range(9)}
    assert _ast_sast_eval.resolve_symbol_expr(checker, ast.Name(id="n0")) == "n8"

    _ast_sast_eval.bind_value_to_name(checker, "s_val", ast.Constant(value="abc"))
    _ast_sast_eval.bind_value_to_name(checker, "zero", ast.Constant(value=0))
    _ast_sast_eval.bind_value_to_name(checker, "expr", ast.BinOp(left=ast.Constant(1), op=ast.Add(), right=ast.Constant(2)))
    assert checker._const_str_vars["s_val"] == "abc"
    assert "zero" not in checker._const_truthy_vars

    assert _ast_sast_eval.eval_int_or_none(ast.parse("-2", mode="eval").body) == (True, -2)
    assert _ast_sast_eval.eval_int_or_none(ast.parse("'x'", mode="eval").body) == (False, None)
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.parse("123[1:2]", mode="eval").body) is None
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.parse("'abc'[foo():]", mode="eval").body) is None
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.parse("f'{unknown_v}'", mode="eval").body) is None
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.JoinedStr(values=[ast.Constant(value="ab")])) == "ab"
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.JoinedStr(values=[ast.Name(id="bad_part")])) is None
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.parse("''.join(['a', unk])", mode="eval").body) is None
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.parse("''.join(reversed('lave'))", mode="eval").body) == "eval"
    assert _ast_sast_eval.eval_const_str_expr(checker, ast.parse("''.join(reversed(unk))", mode="eval").body) is None

    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("not {}", mode="eval").body) is True
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("-1", mode="eval").body) is True
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("+0", mode="eval").body) is False
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("~0", mode="eval").body) is True
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("False or False", mode="eval").body) is False
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("True and False", mode="eval").body) is False
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("1 if cond else 0", mode="eval").body) is False
    assert _ast_sast_eval.is_truthy_constant_expr(checker, ast.parse("bool(1)", mode="eval").body) is True

    checker._imported_aliases["sys"] = "sys"
    assert _ast_sast_eval.is_namespace_expr(checker, ast.parse("sys.modules['lave'[::-1]]", mode="eval").body) is True
    assert _ast_sast_eval.is_namespace_expr(checker, ast.parse("d['__builtins__']", mode="eval").body) is True
    assert _ast_sast_eval.has_traversal_in_node(checker, ast.parse("f'{d}/../x'", mode="eval").body) is True
    assert _ast_sast_eval.has_traversal_in_node(checker, ast.parse("f'{d}/ok'", mode="eval").body) is False
    env_fstr = ast.parse("f'{d}/" + "%TEMP%/x'", mode="eval").body
    assert _ast_sast_eval.find_literal_env_token_in_node(checker, env_fstr) == "%TEMP%"
    assert _ast_sast_eval.find_literal_env_token_in_node(checker, ast.parse("f'{d}/ok'", mode="eval").body) is None
    checker._symbol_aliases["g_alias"] = "grants"
    assert _ast_sast_eval.is_grant_or_snapshot_expr(checker, ast.parse("self.grants", mode="eval").body) is True
    assert _ast_sast_eval.is_grant_or_snapshot_expr(checker, ast.Name(id="g_alias")) is True
    assert _ast_sast_eval.is_grant_or_snapshot_expr(checker, ast.parse("1 + 2", mode="eval").body) is False


@pytest.mark.fast
def test_ast_guard_sast_call_checks_imports_yaml_mock_and_gaming() -> None:
    """Copre sast_call_checks su import_module, yaml, getattr, attrgetter, makedirs, sql e gaming."""
    src = (
        "import importlib, yaml, ctypes, operator, os, subprocess, inspect, sys\n"
        "from mod_x import _ensure_sandbox_benchmark_fixture, currentframe\n"
        "importlib.import_module()\n"
        "importlib.import_module('json')\n"
        "yaml.dump({'a': 1})\n"
        "yaml.load('a: 1', Loader=yaml.CSafeLoader, dummy=1)\n"
        "yaml.load('a: 1', Loader=get_l().SafeLoader)\n"
        "yaml.load('a: 1', Loader=get_l().Unsafe)\n"
        "open('safe/file.txt')\n"
        "getattr(ctypes, 'windll')\n"
        "getattr(inspect, 'currentframe')\n"
        "getattr(sys, 'modules')\n"
        "operator.attrgetter('safe_field')\n"
        "__import__('json')\n"
        "os.makedirs('%TEMP%/sub')\n"
        "os.path.exists('ok')\n"
        "subprocess.CompletedProcess([], 0)\n"
        "currentframe()\n"
        "_ensure_sandbox_benchmark_fixture()\n"
        "sys.__getattribute__('modules')\n"
        "sys.modules.get('json')\n"
        "cur.execute('SELECT 1')\n"
        "cur.execute(f'PING {x}')\n"
        "get_m().MagicMock()\n"
        "d['sys'].modules.get('pytest')\n"
        "obj.currentframe()\n"
        "obj._ensure_sandbox_benchmark_fixture()\n"
        "obj.other_safe()\n"
    )
    chk = _ast_sast_checker.SASTConstructChecker("scripts/prod_mod.py", is_test_file=False)
    chk.visit(ast.parse(src))
    syms = {v.symbol_name for v in chk.violations}
    assert "ctypes.windll" in syms and "os.makedirs" in syms and "yaml.load" in syms
    assert {"SAST-GAMING-D01", "SAST-GAMING-D02", "SAST-GAMING-D03", "MagicMock"}.issubset(syms)
    assert _ast_call_checks._check_getattr_call(chk, ast.parse("getattr(a, 'b')", mode="eval").body) is False


@pytest.mark.fast
def test_ast_guard_sast_checker_non_test_and_self_validator() -> None:
    """Copre SASTConstructChecker wrapper, AnnAssign, JoinedStr, Subscript, Attribute, Def e Import."""
    chk_self = _ast_sast_checker.SASTConstructChecker("scripts/ast_guard_validator.py")
    chk_self.visit(ast.parse("x = ctypes.windll\nopen('../x')\n"))
    assert chk_self.violations == []

    chk = _ast_sast_checker.SASTConstructChecker("src_app/svc.py", is_test_file=False)
    chk._clear_bound_name_state("tmp")
    chk._bind_value_to_name("tmp", ast.Constant("x"))
    assert chk._eval_int_or_none(ast.Constant(5)) == (True, 5)

    src = (
        "import unittest.mock\n"
        "from . import helper\n"
        "from ctypes import windll\n"
        "ann_only: int\n"
        "def _ensure_sandbox_benchmark_fixture(): pass\n"
        "async def _ensure_sandbox_benchmark_fixture(): pass\n"
        "s = f'hello {name}'\n"
        "s2 = f'hello'\n"
        "m1 = sys.modules['json']\n"
        "m2 = obj.__dict__['safe_key']\n"
        "m3 = d['lave'[::-1]]\n"
        "w = windll.kernel32\n"
        "w2 = ctypes.windll\n"
        "mro = obj.__mro__\n"
        "fb = frame.f_back\n"
        "if 'pytest' in obj.modules:\n    pass\n"
        "if 'pytest' in other:\n    pass\n"
    )
    chk.visit(ast.parse("import sys, ctypes\n" + src))
    syms = {v.symbol_name for v in chk.violations}
    assert {"unittest.mock", "ctypes.windll", "SAST-GAMING-D03", "SAST-GAMING-D02", "SAST-GAMING-D01", "__mro__", "eval"}.issubset(syms)


@pytest.mark.fast
def test_nk_hook_gate_json_io_pipes_reparse_and_streaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _get_hooks_temp_dir_str fallback, _is_win_pipe_empty, pipe stdin, reparse e streaks."""
    with monkeypatch.context() as mp:
        for k in ("NK_HOOKS_TEMP_DIR", "TEMP", "TMP", "TMPDIR"):
            mp.delenv(k, raising=False)
        mp.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        assert _hg_json_io._get_hooks_temp_dir_str().endswith("nk_hooks")

    def _posix_get_osfhandle(fd: int) -> int:
        if fd < 0:
            raise OSError("bad file descriptor")
        return int(fd)

    def _posix_peek_named_pipe(handle: int, _size: int) -> tuple[int, int]:
        import select

        r_ready, _, _ = select.select([int(handle)], [], [], 0.0)
        return (1 if r_ready else 0), 0

    with monkeypatch.context() as mp_pipe:
        if sys.platform != "win32":
            mp_pipe.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=_posix_get_osfhandle))
            mp_pipe.setitem(sys.modules, "_winapi", SimpleNamespace(PeekNamedPipe=_posix_peek_named_pipe))
        assert _hg_json_io._is_win_pipe_empty(-1) is False
        r_fd, w_fd = os.pipe()
        try:
            assert _hg_json_io._is_win_pipe_empty(r_fd) is True
            os.write(w_fd, b"x")
            assert _hg_json_io._is_win_pipe_empty(r_fd) is False
        finally:
            os.close(r_fd)
            os.close(w_fd)

    r_fd2, w_fd2 = os.pipe()
    os.write(w_fd2, b'{"toolName": "read_file"}')
    os.close(w_fd2)
    with os.fdopen(r_fd2, "r", encoding="utf-8") as pipe_in:
        with monkeypatch.context() as mp:
            mp.setattr(sys, "stdin", pipe_in)
            parsed, perr = _hg_json_io._read_stdin_payload_ex()
            assert perr is False and parsed.get("toolName") == "read_file"

    with monkeypatch.context() as mp:
        mp.setattr(os.path, "islink", lambda _p: True)
        assert _hg_json_io._is_path_reparse_str(str(tmp_path / "any")) is True

    rep_target = tmp_path / "rep_out.json"
    with monkeypatch.context() as mp:
        mp.setattr(_hg_json_io, "_is_path_reparse_str", lambda p: str(p).endswith("rep_out.json"))
        rep_target.write_text("{}", encoding="utf-8")
        _hg_json_io._write_json_atomic_str(str(rep_target), {"a": 1})

    with monkeypatch.context() as mp:
        mp.setattr(_hg_json_io.os, "replace", lambda *_a: (_ for _ in ()).throw(OSError("nope")))
        _hg_json_io._write_json_atomic_str(str(tmp_path / "fail_atomic.json"), {"a": 1})

    assert _hg_json_io._extract_args_dict({"args": "{bad_json"}, {}) == {"args": "{bad_json"}
    assert _hg_json_io._has_unsafe_readonly_args("not_dict") is True  # type: ignore[arg-type]
    assert _hg_json_io._has_unsafe_readonly_args({"command": []}) is False
    assert _hg_json_io._has_unsafe_readonly_args({"command": ["rm"]}) is True
    assert _hg_json_io._has_unsafe_readonly_args({"command": 123}) is True
    assert _hg_json_io._has_unsafe_readonly_args({"safe": "ok\x00bad"}) is True

    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
        assert _hg_json_io._read_fasttrack_streak("cid_missing") == 0
        ft_path = Path(_hg_json_io._get_hooks_temp_dir_str()) / "fasttrack_cid_bad.json"
        ft_path.write_text(json.dumps({"streak": "nan"}), encoding="utf-8")
        assert _hg_json_io._read_fasttrack_streak("cid_bad") == 0
        _hg_json_io._update_fasttrack_streak("cid_bad", {"toolName": "read_file"})
        assert _hg_json_io._read_fasttrack_streak("cid_bad") == 0
        _hg_json_io._update_fasttrack_streak("cid_bad", {"toolName": "write_file"})
        assert _hg_json_io._read_fasttrack_streak("cid_bad") == 1


@pytest.mark.fast
def test_nk_hook_gate_path_safety_temp_reparse_and_whitelist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre path_safety: temp markers, _canonical_path fallback, reparse escape, redirs e whitelist."""
    assert _hg_path_safety._is_safe_temp_marker_path("scripts/appdata/local/temp/x") is False
    assert _hg_path_safety._is_safe_temp_marker_path("a/../appdata/local/temp/x") is False
    assert _hg_path_safety._is_safe_temp_marker_path("c:/users/u/appdata/local/temp/x") is True

    with monkeypatch.context() as mp:
        mp.setattr(Path, "is_symlink", lambda _self: (_ for _ in ()).throw(OSError("sym")))
        assert _hg_path_safety._canonical_path(tmp_path / "abc").name == "abc"

    parent_hub = tmp_path / "parent_no_track"
    (parent_hub / "NK_Hub").mkdir(parents=True)
    assert _hg_path_safety._resolve_effective_hub_root(parent_hub) == _hg_path_safety._canonical_path(parent_hub)
    (parent_hub / "NK_Hub" / "scripts").mkdir(parents=True)
    assert _hg_path_safety._resolve_target_path("scripts/a.py", parent_hub).parent.parent.name == "NK_Hub"

    assert _hg_path_safety._has_ancestor_reparse_escape("", tmp_path) is False
    assert _hg_path_safety._has_ancestor_reparse_escape("\\\\?\\UNC\\srv\\share\\f", tmp_path) is False
    assert _hg_path_safety._has_ancestor_reparse_escape("\\\\?\\C:\\x", tmp_path) is False
    assert _hg_path_safety._resolve_target_path("\\\\?\\UNC\\srv\\share\\f", tmp_path).name == "f"
    assert _hg_path_safety._resolve_target_path("\\\\?\\C:\\temp_x\\f", tmp_path).name == "f"

    stg_f = tmp_path / ".staging" / "esc" / "a.py"
    stg_f.parent.mkdir(parents=True)
    stg_f.write_text("x=1\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setattr(_hg_path_safety, "_is_path_reparse_point", lambda p: Path(p).name == "esc")
        mp.setattr(os.path, "realpath", lambda p, *_a, **_kw: str(tmp_path / "outside") if "esc" in str(p) else str(p))
        assert _hg_path_safety._has_ancestor_reparse_escape(".staging/esc/a.py", tmp_path) is True
        assert _hg_path_safety._is_safe_redirection_target(".staging/esc/a.py", tmp_path) is False

    assert _hg_path_safety._is_safe_redirection_target("out.txt:stream", tmp_path) is False
    assert _hg_path_safety._is_safe_redirection_target("scripts/nk_diagnostics/x.log", tmp_path) is False
    assert _hg_path_safety._is_safe_redirection_target("%temp%/nk_diagnostics/x.log", tmp_path) is True
    assert _hg_path_safety._is_safe_redirection_target("$unknown/x.log", tmp_path) is False
    assert _hg_path_safety._is_safe_redirection_target(".staging/new.py", tmp_path) is True
    assert _hg_path_safety._is_safe_redirection_target("nk_diagnostics/r.log", tmp_path) is True
    assert _hg_path_safety._is_safe_redirection_target("c:/outside_nk_diagnostics/nk_diagnostics/r.log", tmp_path) is True
    assert _hg_path_safety._is_safe_redirection_target("c:/outside_random/r.log", tmp_path) is False
    assert _hg_path_safety._is_safe_redirection_target(str(Path(tempfile.gettempdir()) / "r.log"), tmp_path) is True

    san = _hg_path_safety._sanitize_staged_tokens_in_cmd(
        "py c:/u/appdata/local/temp/x.py scripts/appdata/local/temp/y.py"
    )
    assert "__temp_safe__" in san and "scripts/appdata/local/temp/y.py" in san
    assert _hg_path_safety._is_whitelisted_outside_staging(Path("c:/u/.gemini/antigravity/brain/conv/a.md"), tmp_path) is True
    assert _hg_path_safety._is_whitelisted_outside_staging(Path(tempfile.gettempdir()) / "x.txt", tmp_path) is True
    assert _hg_path_safety._is_whitelisted_outside_staging(tmp_path, tmp_path) is False
    assert _hg_path_safety._is_whitelisted_outside_staging(tmp_path / "nk_sandbox_1" / "f.py", tmp_path) is True


@pytest.mark.fast
def test_nk_hook_gate_target_classifier_redirs_and_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre target_classifier: candidates, ADS/reparse redirs, overrides e wrapper commands."""
    assert _hg_target_cls._looks_like_write_path_candidate("__staged_safe__") is False
    assert _hg_target_cls._looks_like_write_path_candidate("System::IO") is False
    assert _hg_target_cls._looks_like_write_path_candidate("scripts/a.py") is True

    cands = _hg_target_cls._extract_candidate_write_targets(
        "rg foo scripts/a.py; python -c \"open('x')\"; Set-Content -Value 'v' -Path:scripts/b.py -OutFile 'scripts/c.py' x='scripts/d.py'"
    )
    assert "scripts/b.py" in cands and "scripts/d.py" in cands

    assert _hg_target_cls._classify_redirection_target_violation("a.txt:ads", tmp_path)["decision"] == "deny"
    with monkeypatch.context() as mp:
        mp.setattr(_hg_target_cls, "_has_ancestor_reparse_escape", lambda *_a: True)
        assert _hg_target_cls._classify_redirection_target_violation("x.py", tmp_path)["decision"] == "deny"

    assert _hg_target_cls._classify_redirection_target_violation(".staging/ok.py", tmp_path) is None
    assert _hg_target_cls._classify_redirection_target_violation("nk_diagnostics/ok.log", tmp_path) is None
    assert _hg_target_cls._classify_redirection_target_violation("c:/outside_x/ok.log", tmp_path) is None
    assert _hg_target_cls._classify_non_redirection_write_targets("Set-Content -Path .staging/a.py", tmp_path) is None
    assert _hg_target_cls._classify_non_redirection_write_targets("Set-Content -Path scripts/a.py", tmp_path)["decision"] == "deny"

    assert _hg_target_cls._classify_protected_target("powershell -EncodedCommand AAA", "", tmp_path)["decision"] == "deny"
    with monkeypatch.context() as mp:
        mp.setattr(_hg_target_cls, "_has_ancestor_reparse_escape", lambda *_a: True)
        assert _hg_target_cls._classify_protected_target("scripts/a.py", "", tmp_path)["decision"] == "deny"

    assert _hg_target_cls._classify_protected_target("quality_baseline.json", "", tmp_path)["decision"] == "deny"
    assert _hg_target_cls._classify_protected_target("nk_diagnostics/log.txt", "", tmp_path) == {}
    assert _hg_target_cls._classify_protected_target(
        "", "python scripts/nk_transcript_tools.py oracle-lock freeze", tmp_path, strict_external=True
    )["decision"] == "ask"
    assert _hg_target_cls._classify_protected_target(
        "", "python scripts/nk_transcript_tools.py oracle-lock freeze", tmp_path, strict_external=False
    ) == {}
    assert _hg_target_cls._classify_protected_target("", "Set-Content quality_baseline.json 'x'", tmp_path)["decision"] == "deny"
    assert _hg_target_cls._classify_protected_target("", "Set-Content PATCH_NOTES.md 'x'", tmp_path)["decision"] == "deny"


@pytest.mark.fast
def test_nk_hook_gate_shell_parser_segments_flags_and_archives() -> None:
    """Copre shell_parser: segmenti vuoti, unwrap vuoto, -o flags e archivi tar/unzip/7z/unpack_archive."""
    segs = _hg_shell_parser._split_shell_segments(";; | || && & echo ok")
    assert segs == ["& echo ok"]
    assert _hg_shell_parser._tokenize_shell_tokens("echo a   ") == [("echo", "echo", False), ("a", "a", False)]
    assert _hg_shell_parser._unwrap_shell_subcommands("powershell -c ''") == []
    assert _hg_shell_parser._unwrap_shell_subcommands("& {   }") == []
    assert _hg_shell_parser._split_top_level_args("") == []
    assert _hg_shell_parser._extract_redirection_targets_single("echo >&foo") == ["__empty_redirect__"]
    assert _hg_shell_parser._looks_like_path_token("two words") is False
    assert _hg_shell_parser._looks_like_path_token(".staging") is True
    assert _hg_shell_parser._looks_like_path_token("mod.py") is True

    assert _hg_shell_parser._extract_output_flag_targets_segment("pytest -o junit_family=xunit2") == []
    assert _hg_shell_parser._extract_output_flag_targets_segment("python -m pytest -o log_file=scripts/out.log") == ["scripts/out.log"]
    assert _hg_shell_parser._extract_output_flag_targets_segment("pytest -o") == []
    assert _hg_shell_parser._extract_output_flag_targets_segment("curl -o") == ["__empty_redirect__"]

    assert _hg_shell_parser._extract_archive_targets_segment("unpack_archive('a.zip', extract_dir='out_a')") == ["out_a"]
    assert _hg_shell_parser._extract_archive_targets_segment("unpack_archive('a.zip', 'out_b')") == ["out_b"]
    assert _hg_shell_parser._extract_archive_targets_segment("unpack_archive('a.zip'") == ["."]
    assert _hg_shell_parser._extract_archive_targets_segment("echo tar -xf a.tar") == ["."]
    assert _hg_shell_parser._extract_archive_targets_segment("tar --directory=out_c -xf a.tar") == ["out_c"]
    assert _hg_shell_parser._extract_archive_targets_segment("tar -Cout_d -xf a.tar") == ["out_d"]
    assert _hg_shell_parser._extract_archive_targets_segment("unzip -dout_e a.zip") == ["out_e"]
    assert _hg_shell_parser._extract_archive_targets_segment("7z x a.7z -o out_f") == ["out_f"]
    assert _hg_shell_parser._extract_archive_targets_segment("Expand-Archive a.zip out_g") == ["out_g"]
    assert _hg_shell_parser._extract_archive_targets_segment("tar -xf a.tar") == ["."]


@pytest.mark.fast
def test_nk_hook_gate_write_detector_search_mask_and_open() -> None:
    """Copre _strip_readonly_search_patterns (findstr/git/ps) e _has_non_readonly_open."""
    assert _hg_write_det._strip_readonly_search_patterns("   ") == "   "
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("findstr /c rm file.py")
    assert _hg_write_det._strip_readonly_search_patterns("git --version") == "git --version"
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("git -c=a=1 --git-dir=.git --no-pager grep -e rm")
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("git log -S rm --grep=del -Gmv")
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("git grep --regexp=rm")
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("git grep rm")
    ps_masked = _hg_write_det._strip_readonly_search_patterns('powershell -ExecutionPolicy Bypass -Command "rg rm a.py"')
    assert "__SAFE_SEARCH_PAT__" in ps_masked
    assert _hg_write_det._strip_readonly_search_patterns("powershell -NoProfile run.ps1") == "powershell -NoProfile run.ps1"

    assert _hg_write_det._has_non_readonly_open("obj.open('x', 'w')") is True
    assert _hg_write_det._has_non_readonly_open("obj.open()") is False
    assert _hg_write_det._has_non_readonly_open("open(mode='w')") is True
    assert _hg_write_det._has_non_readonly_open("open(mode='r')") is False
    assert _hg_write_det._has_non_readonly_open(".open('x', 'w')") is True


@pytest.mark.fast
def test_nk_hook_gate_write_detector_prompt_temp_and_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre prompt/si masking, temp/scratch script index, arg target checks e auth override."""
    assert "-EncodedCommand" in _hg_write_det._redact_safe_si_literals(
        "python scripts/a.py -EncodedCommand AAA", "python scripts/a.py -EncodedCommand AAA"
    )
    assert ".." in _hg_write_det._redact_safe_si_literals(
        'python scripts/a.py --prompt "si" ..', 'python scripts/a.py --prompt "si" ..'
    )
    assert "-EncodedCommand" in _hg_write_det._mask_balanced_prompt_payloads(
        "python scripts/a.py -EncodedCommand AAA", "python scripts/a.py -EncodedCommand AAA"
    )
    assert ".." in _hg_write_det._mask_balanced_prompt_payloads(
        'python scripts/a.py --prompt "ok" ..', 'python scripts/a.py --prompt "ok" ..'
    )
    masked = _hg_write_det._mask_balanced_prompt_payloads(
        'python scripts/a.py --prompt "hello \\"rm\\" world"',
        'python scripts/a.py --prompt "hello \\"rm\\" world"',
    )
    assert "__SAFE_PROMPT__" in masked
    unclosed = 'python scripts/a.py --prompt "unclosed'
    assert _hg_write_det._mask_balanced_prompt_payloads(unclosed, unclosed) == unclosed

    assert _hg_write_det._is_temp_or_scratch_script_token("") is False
    assert _hg_write_det._is_temp_or_scratch_script_token(".staging/scripts/a.py") is False
    assert _hg_write_det._is_temp_or_scratch_script_token("scratch/run.py") is True
    assert _hg_write_det._is_temp_or_scratch_script_token(str(Path(tempfile.gettempdir()) / "run.py")) is True

    assert _hg_write_det._arg_targets_protected_outside_staging("", tmp_path) is False
    assert _hg_write_det._arg_targets_protected_outside_staging("--out=scripts/a.py", tmp_path) is True
    assert _hg_write_det._arg_targets_protected_outside_staging("-verbose", tmp_path) is False
    assert _hg_write_det._arg_targets_protected_outside_staging(".staging/scripts/a.py", tmp_path) is False
    assert _hg_write_det._arg_targets_protected_outside_staging("%temp%/x.py", tmp_path) is False
    assert _hg_write_det._arg_targets_protected_outside_staging("pytest.ini", tmp_path) is True
    assert _hg_write_det._arg_targets_protected_outside_staging("orphan.py", tmp_path) is True

    assert _hg_write_det._find_invoked_script_index(["python", "-W", "ignore", "-u", "s.py"], 0, "python") == 4
    assert _hg_write_det._find_invoked_script_index(["pwsh", "-EncodedCommand", "AA"], 0, "pwsh") is None
    assert _hg_write_det._find_invoked_script_index(["pwsh", "-ExecutionPolicy", "Bypass", "-NoLogo", "s.ps1"], 0, "pwsh") == 4
    assert _hg_write_det._find_invoked_script_index(["cmd", "/c", "/y", "s.bat"], 0, "cmd") == 3
    assert _hg_write_det._has_unstaged_temp_script_targeting_protected("python scratch/a.txt scripts/b.py", tmp_path) is False
    assert _hg_write_det._segment_has_write_indicator("importlib.import_module('x')", "importlib.import_module('x')") is True
    assert _hg_write_det._segment_has_write_indicator("tar -xf a.tar", "tar -xf a.tar") is True
    assert _hg_write_det._segment_has_write_indicator("& Set-Content x", "& Set-Content x") is True
    assert _hg_write_det._segment_has_write_indicator("Path('x').unlink()", "Path('x').unlink()") is True
    assert _hg_write_det._has_cmd_write_indicator("", tmp_path) is False
    assert _hg_write_det._has_cmd_write_indicator("python scratch/a.py scripts/b.py", tmp_path) is True
    with monkeypatch.context() as mp:
        mp.delenv("NK_ALLOW_GOVERNANCE_OVERRIDE", raising=False)
        assert _hg_write_det._is_authorized_script_invocation("python scripts/win32_2pc_engine.py --allow-governance-override", tmp_path) is False


@pytest.mark.fast
def test_nk_hook_gate_stop_evidence_tokens_mutex_and_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre stop_evidence: anti-spoof, cache fastguard, mutex/wal, anchor >4KB e spawn."""
    assert _hg_stop_ev._stop_is_verified_compaction({"content": "[Message] sender=a"}) is False
    empty_tp = tmp_path / "empty.jsonl"
    empty_tp.write_text("", encoding="utf-8")
    assert _hg_stop_ev._stop_read_tokens_and_epoch(empty_tp, "cid_se") == (0, 0, 0)

    no_nl_tp = tmp_path / "nonl.jsonl"
    no_nl_tp.write_bytes(b'{"input_tokens": 10}')
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path))
        assert _hg_stop_ev._stop_read_tokens_and_epoch(no_nl_tp, "cid_se") == (0, 0, 0)
        hooks_d = _hg_json_io._get_hooks_temp_dir()
        (hooks_d / "fastguard_cid_se.json").write_text(
            json.dumps({"byte_offset": no_nl_tp.stat().st_size, "last_actual_tokens": 42, "steps": 3, "compaction_epoch": 1}),
            encoding="utf-8",
        )
        assert _hg_stop_ev._stop_read_tokens_and_epoch(no_nl_tp, "cid_se") == (42, 3, 1)

    with monkeypatch.context() as mp:
        if sys.platform != "win32":
            mp.setattr(_hg_stop_ev.sys, "platform", "win32")
        mp.setattr(ctypes, "WinDLL", lambda *_a, **_kw: SimpleNamespace(
            OpenMutexW=lambda *_x: 0, CloseHandle=lambda _h: 1
        ), raising=False)
        mp.setattr(ctypes, "set_last_error", lambda _e: None, raising=False)
        mp.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
        assert _hg_stop_ev._stop_is_batch_mutex_or_wal_busy([tmp_path, tmp_path]) is True

    wal_dir = tmp_path / "wal_r" / ".wal"
    wal_dir.mkdir(parents=True)
    (wal_dir / "active.wal").write_text("{}", encoding="utf-8")
    with monkeypatch.context() as mp:
        if sys.platform != "win32":
            mp.setattr(_hg_stop_ev.sys, "platform", "win32")
        mp.setattr(ctypes, "WinDLL", lambda *_a, **_kw: SimpleNamespace(
            OpenMutexW=lambda *_x: 0, CloseHandle=lambda _h: 1
        ), raising=False)
        mp.setattr(ctypes, "set_last_error", lambda _e: None, raising=False)
        mp.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
        assert _hg_stop_ev._stop_is_batch_mutex_or_wal_busy([tmp_path / "wal_r"]) is True

    anc_root = tmp_path / "anc_r"
    anc_p = anc_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    anc_p.parent.mkdir(parents=True)
    anc_p.write_text(("x" * 4200) + "\n\n" + json.dumps({"milestone_id": "M9", "turn": 3}) + "\n", encoding="utf-8")
    assert _hg_stop_ev._stop_read_anchor_meta([anc_root], {}, conv_id="bad conv!") == ("M9", 3)

    big_tp = tmp_path / "big_se.jsonl"
    big_tp.write_text(json.dumps({"input_tokens": 160000}) + "\n", encoding="utf-8")
    spawned: List[Any] = []
    fake_sp = SimpleNamespace(DEVNULL=-1, Popen=lambda cmd, **_kw: spawned.append(cmd))
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hk2"))
        mp.setattr(_hg_stop_ev, "_SCRIPT_DIR", tmp_path / "no_scripts")
        mp.setattr(_hg_stop_ev, "_stop_is_batch_mutex_or_wal_busy", lambda _r: False)
        mp.setitem(sys.modules, "subprocess", fake_sp)
        mp.setattr(_hg_stop_ev.sys, "platform", "linux")
        _hg_stop_ev._maybe_spawn_stop_idle_checkpoint("conv_ok_1", anc_root, big_tp, {})
        assert len(spawned) == 1


@pytest.mark.fast
def test_nk_acs_fastguard_pipes_reparse_and_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _get_k32, _reconfigure_streams, _win32_stdin_ready, _read_stdin_safe e thresholds."""
    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD.sys, "platform", "linux")
        assert _FG_MOD._get_k32() == (None, None)

    class _BadStream:
        def reconfigure(self, **_kw: Any) -> None:
            raise ValueError("no reconf")

        def write(self, _s: str) -> int:
            raise OSError("err write")

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD.sys, "stdin", None)
        mp.setattr(_FG_MOD.sys, "stdout", _BadStream())
        mp.setattr(_FG_MOD.sys, "stderr", _BadStream())
        _FG_MOD._reconfigure_streams()
        _FG_MOD._warn_stderr("t", "d")
        assert _FG_MOD._read_stdin_safe() == ""

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD.sys, "stdin", SimpleNamespace(isatty=lambda: True))
        assert _FG_MOD._read_stdin_safe() == ""

    with monkeypatch.context() as mp_fg_io:
        if sys.platform != "win32":
            import select
            import stat

            def _fg_posix_get_osfhandle(fd: int) -> int:
                return int(fd)

            def _fg_posix_get_file_type(h_ptr: Any) -> int:
                fd_val = int(getattr(h_ptr, "value", h_ptr))
                try:
                    mode = os.fstat(fd_val).st_mode
                except OSError:
                    return 0
                return _FG_MOD._FILE_TYPE_PIPE if stat.S_ISFIFO(mode) else 1

            def _fg_posix_peek_pipe(
                h_ptr: Any,
                _buf: Any,
                _buf_sz: int,
                _read: Any,
                avail_ref: Any,
                _left: Any,
            ) -> int:
                fd_val = int(getattr(h_ptr, "value", h_ptr))
                r_ready, _, _ = select.select([fd_val], [], [], 0.0)
                avail_ref._obj.value = 1 if r_ready else 0
                return 1

            mp_fg_io.setitem(
                sys.modules,
                "msvcrt",
                SimpleNamespace(get_osfhandle=_fg_posix_get_osfhandle),
            )
            fake_ct = SimpleNamespace(
                c_void_p=lambda v: SimpleNamespace(value=int(v)),
                c_uint32=lambda v: SimpleNamespace(value=int(v)),
                byref=lambda obj: SimpleNamespace(_obj=obj),
                set_last_error=lambda _e: None,
                get_last_error=lambda: 0,
            )
            fake_fg_k32 = SimpleNamespace(
                GetFileType=_fg_posix_get_file_type,
                PeekNamedPipe=_fg_posix_peek_pipe,
            )
            mp_fg_io.setattr(_FG_MOD, "_get_k32", lambda: (fake_ct, fake_fg_k32))

        r_fd, w_fd = os.pipe()
        try:
            with monkeypatch.context() as mp:
                mp.setattr(_FG_MOD.time, "sleep", lambda _s: None)
                assert _FG_MOD._win32_stdin_ready(r_fd) is False
            os.write(w_fd, b"1")
            assert _FG_MOD._win32_stdin_ready(r_fd) is True
        finally:
            os.close(r_fd)
            os.close(w_fd)

        reg_f = tmp_path / "reg.txt"
        reg_f.write_text("hi", encoding="utf-8")
        with open(reg_f, "rb") as fh:
            assert _FG_MOD._win32_stdin_ready(fh.fileno()) is True

    with monkeypatch.context() as mp:
        if sys.platform != "win32":
            mp.setattr(_FG_MOD.sys, "platform", "win32")
        mp.setattr(_FG_MOD.os, "lstat", lambda _p: (_ for _ in ()).throw(OSError("lstat")))
        mp.setattr(_FG_MOD, "_get_k32", lambda: (ctypes, SimpleNamespace(
            GetFileAttributesW=lambda _p: _FG_MOD._FILE_ATTRIBUTE_REPARSE_POINT
        )))
        assert _FG_MOD._is_reparse_or_symlink(reg_f) is True

    assert _FG_MOD._is_safe_dir(str(reg_f)) is False
    assert _FG_MOD._stat_safe_file(str(tmp_path)) is None

    res_rel = tmp_path / "r_root" / "nk_genome" / "configs"
    res_rel.mkdir(parents=True)
    bad_cfg = res_rel / "saturation_thresholds.json"
    bad_cfg.write_text("{bad", encoding="utf-8")
    assert _FG_MOD._load_acs_thresholds([str(tmp_path / "r_root")])["z1_tokens"] == _FG_MOD._Z1_TOKENS
    bad_cfg.write_text(json.dumps({"autonomous_context_shield": {"z1_tokens": 99999}}), encoding="utf-8")
    assert _FG_MOD._load_acs_thresholds([str(tmp_path / "r_root")])["z1_tokens"] == 99999
    assert _FG_MOD._load_acs_thresholds([str(tmp_path / "r_root")])["z1_tokens"] == 99999


@pytest.mark.fast
def test_nk_acs_fastguard_backscan_cursor_wal_and_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre _save_state_atomic errors, _cold_backscan_64kb, _advance_cursor, _has_active_wal e _maybe_spawn_z2."""
    assert _FG_MOD._save_state_atomic(None, {}) == (False, "missing_state_path")
    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD, "_is_reparse_or_symlink", lambda _p: True)
        assert _FG_MOD._save_state_atomic(str(tmp_path / "s.json"), {}) == (False, "reparse_guard")
    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD.os, "open", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("open fail")))
        ok_s, err_s = _FG_MOD._save_state_atomic(str(tmp_path / "s2.json"), {})
        assert not ok_s and err_s is not None and "io_error:" in err_s

    tp_big = tmp_path / "big_tp.jsonl"
    big_filler = "x" * 70000
    lines = [
        json.dumps({"step_index": 1, "input_tokens": 5000}) + "\n",
        json.dumps({"step_index": 2, "note": big_filler, "input_tokens": 8000}) + "\n",
        json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "compacted": True}) + "\n",
        json.dumps({"step_index": 3, "input_tokens": 12000}) + "\n",
    ]
    pad_lines = [json.dumps({"step_index": 4, "note": "y" * 2000}) + "\n" for _ in range(240)]
    tp_big.write_text("".join(lines + pad_lines), encoding="utf-8")

    st = _FG_MOD._default_state()
    _FG_MOD._advance_cursor(str(tp_big), st)
    assert st["compaction_epoch"] >= 1 and st["epoch_baseline_tokens"] == 12000

    st["byte_offset"] = 0
    _FG_MOD._cold_backscan_64kb(str(tp_big), tp_big.stat().st_size, st)
    assert st["compaction_epoch"] >= 1

    st_trunc = _FG_MOD._default_state()
    st_trunc["byte_offset"] = 99999999
    _FG_MOD._advance_cursor(str(tp_big), st_trunc)
    assert st_trunc["byte_offset"] == tp_big.stat().st_size

    wal_root = tmp_path / "wroot"
    (wal_root / ".wal").mkdir(parents=True)
    (wal_root / ".wal" / "skip.txt").write_text("x", encoding="utf-8")
    (wal_root / ".wal" / "live.wal").write_text("x", encoding="utf-8")
    assert _FG_MOD._has_active_wal([str(wal_root)]) is True

    spawn_calls: List[Any] = []
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "subprocess", SimpleNamespace(
            DEVNULL=-1,
            Popen=lambda cmd, **_kw: spawn_calls.append(cmd),
        ))
        mp.setattr(_FG_MOD.sys, "platform", "linux")
        _FG_MOD._maybe_spawn_z2([str(tmp_path)], str(tp_big), "conv_z2", {}, st, cooldown_s=0.0)
        assert len(spawn_calls) == 1
        _FG_MOD._maybe_spawn_z2([str(tmp_path)], str(tp_big), "conv_z2", {}, st, cooldown_s=60.0)
        assert len(spawn_calls) == 1


@pytest.mark.fast
def test_nk_acs_fastguard_cli_main_fallback_and_zones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre nk_acs_fastguard.main(): CLI flags, fallback Z1/Z3, subagent, rehydrate e Z1/Z3 Pre/Post."""
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hk"))
        rc_bad_ev, _, _ = call_script_main_captured(_FG_MOD, ["--event", "InvalidEv"])
        assert rc_bad_ev == 2

        rc_bad_js, out_bad_js, _ = call_script_main_captured(_FG_MOD, ["--event", "PreInvocation"], "{bad")
        assert rc_bad_js == 0 and out_bad_js.strip() == "{}"

        rc_unk_ev, out_unk_ev, _ = call_script_main_captured(
            _FG_MOD, [], json.dumps({"hook_event_name": "OtherEvent"})
        )
        assert rc_unk_ev == 0 and out_unk_ev.strip() == "{}"

        tp_sub = tmp_path / "sub_tp.jsonl"
        tp_sub.write_text(json.dumps({"step_index": 1, "content": "<subagent_reminder>hi</subagent_reminder>"}) + "\n", encoding="utf-8")
        rc_sub, out_sub, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PreInvocation", "--transcript", str(tp_sub)]
        )
        assert rc_sub == 0 and out_sub.strip() == "{}"

        hooks_d = Path(_FG_MOD._get_hooks_temp_dir())
        fb_state = _FG_MOD._default_state()
        fb_state["fallback_steps"] = _FG_MOD._Z1_STEPS - 1
        _FG_MOD._save_state_atomic(str(hooks_d / "fastguard_fb_c1.json"), fb_state)
        rc_fz1, out_fz1, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PreInvocation", "--conversation-id", "fb_c1", "--project-root", str(tmp_path)]
        )
        assert rc_fz1 == 0 and "ACS-Z1" in out_fz1

        fb_state["fallback_steps"] = _FG_MOD._Z3_STEPS - 1
        _FG_MOD._save_state_atomic(str(hooks_d / "fastguard_fb_c2.json"), fb_state)
        rc_fz3, out_fz3, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PreInvocation", "--conversation-id", "fb_c2", "--project-root", str(tmp_path)]
        )
        assert rc_fz3 == 0 and "ACS-Z3" in out_fz3

        mp.setattr(_FG_MOD, "_maybe_spawn_z2", lambda *_a, **_kw: None)
        tp_z = tmp_path / "zones_tp.jsonl"
        tp_z.write_text(
            json.dumps({"source": "SYSTEM", "type": "CHECKPOINT", "compacted": True}) + "\n"
            + json.dumps({"input_tokens": _FG_MOD._Z1_TOKENS + 100}) + "\n",
            encoding="utf-8",
        )
        rc_z1, out_z1, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PreInvocation", "--native-contract", "--conversation-id", "zc1", "--transcript", str(tp_z), "--project-root", str(tmp_path)]
        )
        assert rc_z1 == 0 and "RULE-REHYDRATE" in out_z1 and "ACS-Z1" in out_z1

        with open(tp_z, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"input_tokens": _FG_MOD._Z3_TOKENS + 500}) + "\n")
        rc_z3_pre, out_z3_pre, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PreInvocation", "--conversation-id", "zc1", "--transcript", str(tp_z), "--project-root", str(tmp_path)]
        )
        assert rc_z3_pre == 0 and "ACS-Z3" in out_z3_pre
        rc_z3_post, out_z3_post, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PostInvocation", "--native-contract", "--conversation-id", "zc1", "--transcript", str(tp_z), "--project-root", str(tmp_path)]
        )
        assert rc_z3_post == 0 and "injectSteps" in out_z3_post


@pytest.mark.fast
def test_nk_acs_fastguard_extra_edge_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre rami residui di nk_acs_fastguard: _resolve_eff_root, _candidate_roots, _is_subagent_transcript, mutex e error main."""
    parent_ws = tmp_path / "p_ws"
    (parent_ws / "NK_Hub" / "scripts").mkdir(parents=True)
    assert _FG_MOD._resolve_eff_root({}, str(parent_ws)) == os.path.realpath(str(parent_ws / "NK_Hub"))
    assert _FG_MOD._resolve_eff_root({}, str(tmp_path / "nonexistent")) == _FG_MOD._WORKSPACE_ROOT
    assert _FG_MOD._is_valid_conv_id("") is False
    assert _FG_MOD._is_valid_conv_id("a" * 65) is False

    stg_r = tmp_path / "hub_c" / ".staging"
    stg_r.mkdir(parents=True)
    assert len(_FG_MOD._candidate_roots(str(stg_r))) == 2

    sub_tp = tmp_path / "sub_edge.jsonl"
    sub_tp.write_text(
        "\n" + "{bad\n" + "[]\n"
        + json.dumps({"source": "USER", "content": "spoof"}) + "\n"
        + json.dumps({"step_index": True, "content": "bool"}) + "\n"
        + json.dumps({"step_index": 9, "content": "late"}) + "\n"
        + json.dumps({"step_index": 1, "content": "ok"}) + "\n"
        + json.dumps({"step_index": 1, "content": "<subagent_reminder>"}) + "\n",
        encoding="utf-8",
    )
    assert _FG_MOD._is_subagent_transcript(str(sub_tp)) is False
    assert _FG_MOD._is_subagent_transcript(str(tmp_path / "no_sub.jsonl")) is False

    assert _FG_MOD._is_verified_compaction({"content": "[Message] sender=a"}) is False
    assert _FG_MOD._is_verified_compaction({"source": "SYSTEM_SDK", "content": "<CONTEXT_SUMMARY>"}) is False
    assert _FG_MOD._is_verified_compaction({"source": "SYSTEM", "content": "# Resuming from a compaction"}) is True
    assert _FG_MOD._parse_json_bytes(b"   ") is None

    with monkeypatch.context() as mp:
        ctypes_stub = ctypes if sys.platform == "win32" else SimpleNamespace(
            set_last_error=lambda _e: None, get_last_error=lambda: 0
        )
        mp.setattr(_FG_MOD, "_get_k32", lambda: (ctypes_stub, SimpleNamespace(
            OpenMutexW=lambda *_a: 777, CloseHandle=lambda _h: 1
        )))
        assert _FG_MOD._is_batch_mutex_busy([str(tmp_path), str(tmp_path)]) is True

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD, "_resolve_explicit_conv_id", lambda *_a: (_ for _ in ()).throw(RuntimeError("boom")))
        rc_err, out_err, _ = call_script_main_captured(_FG_MOD, ["--event", "PreInvocation"])
        assert rc_err == 0 and out_err.strip() == "{}"


@pytest.mark.fast
def test_nk_acs_fastguard_stdin_pipes_and_reparse_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre rami residui di _win32_stdin_ready, _read_stdin_safe, _is_reparse_or_symlink, _get_hooks_temp_dir e _resolve_transcript_path."""
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda _fd: -1))
        assert _FG_MOD._win32_stdin_ready(0) is False

    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda _fd: 999))
        mp.setattr(_FG_MOD, "_get_k32", lambda: (None, None))
        assert _FG_MOD._win32_stdin_ready(0) is True

    fake_k32_bad_ft = SimpleNamespace(GetFileType=lambda _h: 0)
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda _fd: 999))
        mp.setattr(_FG_MOD, "_get_k32", lambda: (SimpleNamespace(
            c_void_p=lambda x: x, set_last_error=lambda _e: None, get_last_error=lambda: 6
        ), fake_k32_bad_ft))
        assert _FG_MOD._win32_stdin_ready(0) is False

    fake_k32_bad_peek = SimpleNamespace(
        GetFileType=lambda _h: _FG_MOD._FILE_TYPE_PIPE,
        PeekNamedPipe=lambda *_a: 0,
    )
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda _fd: 999))
        mp.setattr(_FG_MOD, "_get_k32", lambda: (SimpleNamespace(
            c_void_p=lambda x: x,
            c_uint32=lambda v: SimpleNamespace(value=v),
            byref=lambda x: x,
            set_last_error=lambda _e: None,
            get_last_error=lambda: 0,
        ), fake_k32_bad_peek))
        assert _FG_MOD._win32_stdin_ready(0) is False

    r_fd, w_fd = os.pipe()
    os.write(w_fd, b"abc")
    os.close(w_fd)
    with os.fdopen(r_fd, "r", encoding="utf-8") as p_in:
        with monkeypatch.context() as mp:
            mp.setattr(_FG_MOD.sys, "stdin", p_in)
            mp.setattr(_FG_MOD, "_win32_stdin_ready", lambda _fd: False)
            assert _FG_MOD._read_stdin_safe() == ""

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD.sys, "stdin", SimpleNamespace(
            isatty=lambda: False, read=lambda: (_ for _ in ()).throw(OSError("rd"))
        ))
        assert _FG_MOD._read_stdin_safe() == ""

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD.os, "lstat", lambda _p: SimpleNamespace(st_mode=0o120777, st_file_attributes=0))
        assert _FG_MOD._is_reparse_or_symlink(tmp_path / "x") is True
        assert _FG_MOD._is_safe_dir(str(tmp_path / "x")) is False
        assert _FG_MOD._stat_safe_file(str(tmp_path / "x")) is None
        mp.setattr(_FG_MOD.os, "lstat", lambda _p: SimpleNamespace(st_mode=0o100644, st_file_attributes=_FG_MOD._FILE_ATTRIBUTE_REPARSE_POINT))
        assert _FG_MOD._is_reparse_or_symlink(tmp_path / "x") is True

    tp_home = tmp_path / ".gemini" / "antigravity" / "brain" / "cid_u" / ".system_generated" / "logs"
    tp_home.mkdir(parents=True)
    (tp_home / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setenv("USERPROFILE", str(tmp_path))
        assert _FG_MOD._resolve_transcript_path(None, {}, "cid_u") == str(tp_home / "transcript.jsonl")
        for k in ("NK_HOOKS_TEMP_DIR", "TEMP", "TMP"):
            mp.delenv(k, raising=False)
        mp.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        assert _FG_MOD._get_hooks_temp_dir() == str(tmp_path / "nk_hooks")
        mp.setattr(_FG_MOD, "_is_reparse_or_symlink", lambda _p: True)
        assert _FG_MOD._get_hooks_temp_dir() is None


@pytest.mark.fast
def test_nk_acs_fastguard_state_retries_anchors_and_z2_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre corrupt state, winerror=32 retries, subagent >5 righe, anchor session, _maybe_spawn_z2 win32/err e Z2 PostInvocation."""
    corrupt_st = tmp_path / "corrupt_state.json"
    corrupt_st.write_text("{bad_json", encoding="utf-8")
    _, ex_c, rec_c = _FG_MOD._load_state_with_exists(str(corrupt_st))
    assert ex_c is True and rec_c is True

    with monkeypatch.context() as mp:
        def _winerr32(*_a: Any) -> None:
            e = OSError("locked")
            e.winerror = 32
            raise e

        mp.setattr(_FG_MOD.os, "replace", _winerr32)
        mp.setattr(_FG_MOD.time, "sleep", lambda _s: None)
        ok_w, err_w = _FG_MOD._save_state_atomic(str(tmp_path / "retry_s.json"), {"a": 1})
        assert not ok_w and err_w is not None and err_w.startswith("winerror_exhausted:")
        _FG_MOD._persist_state_or_warn(None, {})

    long_sub = tmp_path / "long_sub.jsonl"
    long_sub.write_text("\n".join(json.dumps({"step_index": 0, "content": "ok"}) for _ in range(7)) + "\n", encoding="utf-8")
    assert _FG_MOD._is_subagent_transcript(str(long_sub)) is False

    anc_root = tmp_path / "anc_sess"
    sess_anc = anc_root / "nk_tracking" / "sessions" / "cid_s1" / "session_anchor.jsonl"
    sess_anc.parent.mkdir(parents=True)
    sess_anc.write_text(("z" * 4200) + "\n\n{bad\n" + json.dumps({"milestone_id": "M-S1", "turn": 4}) + "\n", encoding="utf-8")
    assert _FG_MOD._read_anchor_meta([str(anc_root)], {}, conv_id="cid_s1") == ("M-S1", 4)

    st = _FG_MOD._default_state()
    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD, "_is_batch_mutex_busy", lambda _r: True)
        _FG_MOD._maybe_spawn_z2([str(tmp_path)], str(long_sub), "cid_s1", {}, st)

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD, "_is_batch_mutex_busy", lambda _r: False)
        mp.setattr(_FG_MOD, "_has_active_wal", lambda _r: False)
        mp.setattr(_FG_MOD, "_SCRIPT_DIR", str(tmp_path / "no_s"))
        mp.setattr(_FG_MOD, "_WORKSPACE_ROOT", str(tmp_path / "no_ws"))
        _FG_MOD._maybe_spawn_z2([str(tmp_path)], str(long_sub), "cid_s1", {}, st)

    with monkeypatch.context() as mp:
        mp.setattr(_FG_MOD, "_is_batch_mutex_busy", lambda _r: False)
        mp.setattr(_FG_MOD, "_has_active_wal", lambda _r: False)
        mp.setattr(_FG_MOD.sys, "platform", "win32")
        mp.setitem(sys.modules, "subprocess", SimpleNamespace(
            DEVNULL=-1, Popen=lambda *_a, **_kw: (_ for _ in ()).throw(OSError("spawn fail"))
        ))
        _FG_MOD._maybe_spawn_z2([str(tmp_path)], str(long_sub), "cid_s1", {}, st, cooldown_s=0.0)

    tp_z2 = tmp_path / "z2_tp.jsonl"
    tp_z2.write_text(json.dumps({"input_tokens": _FG_MOD._Z2_TOKENS + 100}) + "\n", encoding="utf-8")
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hk_z2"))
        mp.setattr(_FG_MOD, "_maybe_spawn_z2", lambda *_a, **_kw: None)
        rc_z2, out_z2, _ = call_script_main_captured(
            _FG_MOD, ["--event", "PostInvocation", "--conversation-id", "z2_c", "--transcript", str(tp_z2), "--project-root", str(tmp_path)]
        )
        assert rc_z2 == 0 and out_z2.strip() == "{}"


@pytest.mark.fast
def test_nk_hook_gate_stop_evidence_resumed_and_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre stop_evidence: resumed offset, compaction, handle mutex, locate_transcript e win32 Popen."""
    tp = tmp_path / "ev_tp.jsonl"
    prefix_bytes = (json.dumps({"input_tokens": 100}) + "\n").encode("utf-8")
    suffix_bytes = (
        b"\n"
        + b"{bad_json\n"
        + b"[]\n"
        + (json.dumps({"source": "SYSTEM", "type": "CHECKPOINT"}) + "\n").encode("utf-8")
        + (json.dumps({"input_tokens": 250, "cache_read_tokens": 50}) + "\n").encode("utf-8")
    )
    tp.write_bytes(prefix_bytes + suffix_bytes)

    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hk_ev"))
        hooks_d = _hg_json_io._get_hooks_temp_dir()
        (hooks_d / "fastguard_cid_res.json").write_text(
            json.dumps({"byte_offset": len(prefix_bytes), "last_actual_tokens": 100, "steps": 1, "compaction_epoch": 0}),
            encoding="utf-8",
        )
        toks, stps, ep = _hg_stop_ev._stop_read_tokens_and_epoch(tp, "cid_res")
        assert toks == 300 and stps == 1 and ep == 1

    with monkeypatch.context() as mp:
        if sys.platform != "win32":
            mp.setattr(_hg_stop_ev.sys, "platform", "win32")
        mp.setattr(ctypes, "WinDLL", lambda *_a, **_kw: SimpleNamespace(
            OpenMutexW=lambda *_x: 555, CloseHandle=lambda _h: 1
        ), raising=False)
        mp.setattr(ctypes, "set_last_error", lambda _e: None, raising=False)
        mp.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
        assert _hg_stop_ev._stop_is_batch_mutex_or_wal_busy([tmp_path]) is True

    anc_root = tmp_path / "anc_ev"
    sess_anc = anc_root / "nk_tracking" / "sessions" / "cid_res" / "session_anchor.jsonl"
    sess_anc.parent.mkdir(parents=True)
    sess_anc.write_text("{corrupt\n", encoding="utf-8")
    assert _hg_stop_ev._stop_read_anchor_meta([anc_root], {}, conv_id="cid_res") == ("NK-ACS-AUTO", 1)

    big_tp = tmp_path / "big_win.jsonl"
    big_tp.write_text(json.dumps({"input_tokens": 160000}) + "\n", encoding="utf-8")
    win_spawn: List[Any] = []
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hk_win"))
        mp.setitem(sys.modules, "nk_transcript_tools", SimpleNamespace(
            locate_transcript=lambda *_a: ({"transcript_path": str(big_tp)}, 0),
            is_subagent_transcript_file=lambda _p: False,
        ))
        mp.setattr(_hg_stop_ev, "_stop_is_batch_mutex_or_wal_busy", lambda _r: False)
        mp.setattr(_hg_stop_ev.sys, "platform", "win32")
        mp.setitem(sys.modules, "subprocess", SimpleNamespace(DEVNULL=-1, Popen=lambda cmd, **_kw: win_spawn.append(cmd)))
        _hg_stop_ev._maybe_spawn_stop_idle_checkpoint("cid_win_1", anc_root, None, {})
        assert len(win_spawn) == 1


@pytest.mark.fast
def test_nk_hook_gate_json_io_streak_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copre json_io: fasttrack streak >12, _write_json_atomic_str retry WinError 32 e reparse."""
    with monkeypatch.context() as mp:
        mp.setenv("NK_HOOKS_TEMP_DIR", str(tmp_path / "hk_ft"))
        ft_p = _hg_json_io._get_hooks_temp_dir() / "fasttrack_cid_over.json"
        ft_p.write_text(json.dumps({"streak": "bad"}), encoding="utf-8")
        res1 = _hg_json_io._update_fasttrack_streak("cid_over", {"toolName": "write_file"})
        assert res1 == {}
        ft_p.write_text(json.dumps({"streak": 12}), encoding="utf-8")
        res_ro = _hg_json_io._update_fasttrack_streak("cid_over", {"toolName": "read_file"})
        assert res_ro == {} and _hg_json_io._read_fasttrack_streak("cid_over") == 12
        res2 = _hg_json_io._update_fasttrack_streak("cid_over", {"toolName": "write_file"})
        assert "ephemeralMessage" in res2

    orig_rep = os.replace
    rep_tries = {"n": 0}

    def _retry_once_rep(src: str, dst: str) -> None:
        rep_tries["n"] += 1
        if rep_tries["n"] == 1:
            e = OSError("share")
            e.winerror = 32
            raise e
        orig_rep(src, dst)

    with monkeypatch.context() as mp:
        mp.setattr(_hg_json_io.os, "replace", _retry_once_rep)
        mp.setattr(_hg_json_io.time, "sleep", lambda _s: None)
        _hg_json_io._write_json_atomic_str(str(tmp_path / "retry_j.json"), {"ok": True})
    assert rep_tries["n"] == 2


@pytest.mark.fast
def test_nk_hook_gate_write_detector_extra_branches(tmp_path: Path) -> None:
    """Copre rami residui di shell_write_detector (git log/grep, si redact, find_invoked_script_index)."""
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("git log -S rm -- src/")
    assert "__SAFE_SEARCH_PAT__" in _hg_write_det._strip_readonly_search_patterns("git grep -e rm")
    assert _hg_write_det._strip_readonly_search_patterns("git status") == "git status"
    assert _hg_write_det._strip_readonly_search_patterns("cmd /c echo hi") == "cmd /c echo hi"

    assert _hg_write_det._has_non_readonly_open(".open('x')") is True
    assert _hg_write_det._has_non_readonly_open(".open('r')") is False
    assert _hg_write_det._has_non_readonly_open("open('x', 'r', encoding='utf-8')") is False
    assert _hg_write_det._has_non_readonly_open("open('x', encoding='utf-8')") is True

    red = _hg_write_det._redact_safe_si_literals(
        'python scripts/a.py --prompt "si"',
        'python scripts/a.py --prompt "si"',
    )
    assert "__SAFE_SI__" in red
    assert _hg_write_det._redact_safe_si_literals("echo hi", "echo hi") == "echo hi"
    assert _hg_write_det._mask_balanced_prompt_payloads("echo hi", "echo hi") == "echo hi"
    assert _hg_write_det._mask_balanced_prompt_payloads("python scripts/a.py $()", "python scripts/a.py $()") == "python scripts/a.py $()"

    assert _hg_write_det._find_invoked_script_index(["python", "-c", "print(1)"], 0, "python") is None
    assert _hg_write_det._find_invoked_script_index(["python", "-u"], 0, "python") is None
    assert _hg_write_det._find_invoked_script_index(["pwsh", "-File", "s.ps1"], 0, "pwsh") == 2
    assert _hg_write_det._find_invoked_script_index(["pwsh", "-NoLogo"], 0, "pwsh") is None
    assert _hg_write_det._find_invoked_script_index(["cmd", "/q"], 0, "cmd") is None
    assert _hg_write_det._find_invoked_script_index(["bash", "s.sh"], 0, "bash") is None
    assert _hg_write_det._arg_targets_protected_outside_staging("README.md", tmp_path) is True
    assert _hg_write_det._arg_targets_protected_outside_staging("notes.txt", tmp_path) is False

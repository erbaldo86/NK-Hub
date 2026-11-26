# -*- coding: utf-8 -*-
"""Test Zero-Mock mutation killers Milestone 1 NK-GEN-4.0.1."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from _internal.nk_common import lane_leases as ll_mod
from _internal.nk_common import nvme_storage_guards as nsg_mod
from _internal.nk_common import wal_scope as ws_mod
from _internal.nk_common import worker_budget as wb_mod
from _internal.nk_common.nvme_base_cache import sync_nvme_base_cache

pytestmark = pytest.mark.fast


def _make_fake_windll(shell_state: dict[str, Any], drive_state: dict[str, Any]) -> Callable[..., Any]:
    """Costruisce stub WinDLL deterministico per shell32 e kernel32."""

    def _sh_get(_a: Any, _b: Any, _c: Any, _d: Any, buf: Any) -> int:
        buf.value = shell_state["val"]
        return int(shell_state["hr"])

    def _vol_info(_r: Any, vn: Any, _l1: Any, _a: Any, _b: Any, _c: Any, fn: Any, _l2: Any) -> int:
        vn.value = drive_state["vol"]
        fn.value = drive_state["fs"]
        return 1

    def _fake_windll(name: str, **_kw: Any) -> Any:
        if name == "shell32":
            return SimpleNamespace(SHGetFolderPathW=_sh_get)
        return SimpleNamespace(GetDriveTypeW=lambda _p: int(drive_state["dtype"]), GetVolumeInformationW=_vol_info)

    return _fake_windll


def _ignore_tmp_and_pycache(_d: Path, names: list[str]) -> set[str]:
    """Ritorna nomi ignorati per base cache."""
    return set(names).intersection({"__pycache__", "drop.tmp"})


def _is_dir_predicate(candidate: Path, _root: Path) -> bool:
    """Predicato directory semplice per base cache."""
    return candidate.is_dir()


def _never_text(_path: Path) -> bool:
    """Predicato false per file binari/non-text."""
    return False


def _boom_windll(*_a: Any, **_kw: Any) -> Any:
    """Stub WinDLL che fallisce se invocato."""
    raise RuntimeError("must_short_circuit")


def test_m1_nvme_win32_shell_and_drive_guards(tmp_path: Path, monkeypatch: Any) -> None:
    """Kill mutation survival su shell folder, drive type/volume e fallback LOCALAPPDATA."""
    local_ok = tmp_path / "app_local_ok"
    local_ok.mkdir()
    shell_state = {"hr": 1, "val": str(local_ok)}
    drive_state = {"dtype": 3, "vol": "System", "fs": "NTFS"}
    monkeypatch.setattr(nsg_mod.sys, "platform", "win32")
    monkeypatch.setattr(nsg_mod.ctypes, "WinDLL", _make_fake_windll(shell_state, drive_state), raising=False)

    assert nsg_mod._win32_shell_local_appdata() is None
    shell_state["hr"], shell_state["val"] = 0, "   "
    assert nsg_mod._win32_shell_local_appdata() is None
    shell_state["val"] = "G:/Il mio Drive/CloudApp"
    assert nsg_mod._win32_shell_local_appdata() is None
    shell_state["val"] = str(local_ok)
    assert nsg_mod._win32_shell_local_appdata() == local_ok.resolve()

    assert nsg_mod._win32_drive_is_cloud("") is False
    drive_state["dtype"] = 4
    assert nsg_mod._win32_drive_is_cloud("Z:\\") is True
    drive_state["dtype"], drive_state["vol"] = 3, "Google Drive"
    assert nsg_mod._win32_drive_is_cloud("G:\\") is True
    drive_state["vol"] = "Windows"
    assert nsg_mod._win32_drive_is_cloud("C:\\") is False

    monkeypatch.setattr(nsg_mod, "_win32_shell_local_appdata", lambda: None)
    monkeypatch.setenv("LOCALAPPDATA", "G:/Il mio Drive/BadAppData")
    assert not nsg_mod.is_cloud_mount_path(nsg_mod.resolve_local_appdata_dir())
    monkeypatch.setenv("LOCALAPPDATA", str(local_ok))
    assert nsg_mod.resolve_local_appdata_dir() == local_ok.resolve()


def test_m1_wal_scope_fallback_and_safe_dir(tmp_path: Path, monkeypatch: Any) -> None:
    """Kill mutation survival su wal_scope fallback TMP e _is_safe_wal_dir."""
    local_ok = tmp_path / "wal_ok_dir"
    local_ok.mkdir()
    alt_tmp = tmp_path / "alt_tmp_root"
    monkeypatch.setenv("TEMP", "")
    monkeypatch.setenv("TMP", str(alt_tmp))
    assert ws_mod.get_scoped_wal_dirs([tmp_path])[1].parent == (alt_tmp / "nk_2pc_wal")

    sample_f = tmp_path / "wal_f.txt"
    sample_f.write_text("x", encoding="utf-8")
    assert ws_mod._is_safe_wal_dir(tmp_path / "missing_wal") is False
    assert ws_mod._is_safe_wal_dir(sample_f) is False
    assert ws_mod._is_safe_wal_dir(local_ok) is True


def test_m1_nvme_base_cache_ignore_patterns(tmp_path: Path) -> None:
    """Kill mutation survival su ignore filter e discesa subdir in nvme_base_cache."""
    ws_ign = tmp_path / "ws_ign"
    (ws_ign / "scripts" / "__pycache__").mkdir(parents=True)
    (ws_ign / "scripts" / "sub").mkdir(parents=True)
    (ws_ign / "scripts" / "keep.py").write_text("X = 1\n", encoding="utf-8")
    (ws_ign / "scripts" / "sub" / "nested.py").write_text("Z = 2\n", encoding="utf-8")
    (ws_ign / "scripts" / "drop.tmp").write_text("X = 0\n", encoding="utf-8")
    (ws_ign / "scripts" / "__pycache__" / "inside.py").write_text("Y = 0\n", encoding="utf-8")

    base_ign = sync_nvme_base_cache(
        ws_ign,
        ("scripts",),
        _ignore_tmp_and_pycache,
        _never_text,
        _is_dir_predicate,
        cache_root=tmp_path / "bc_ign",
    )
    assert (base_ign / "scripts" / "keep.py").is_file()
    assert (base_ign / "scripts" / "sub" / "nested.py").is_file()
    assert not (base_ign / "scripts" / "drop.tmp").exists()
    assert not (base_ign / "scripts" / "__pycache__" / "inside.py").exists()


def _make_probe_windll(calls: dict[str, int], *, open_handle: int) -> Callable[..., Any]:
    """Stub kernel32 tracciato per verificare short-circuit PID e handle nullo."""

    def _open_proc(_acc: Any, _inh: Any, _pid: int) -> int:
        calls["open"] += 1
        return open_handle

    def _get_times(_h: Any, ct: Any, _et: Any, _kt: Any, _ut: Any) -> int:
        calls["times"] += 1
        ct._obj.value = 133_000_000_000_000_000
        return 1

    def _get_exit(_h: Any, ref: Any) -> int:
        ref._obj.value = 0
        return 1

    def _loader(*_a: Any, **_kw: Any) -> Any:
        return SimpleNamespace(
            OpenProcess=_open_proc,
            GetProcessTimes=_get_times,
            GetExitCodeProcess=_get_exit,
            CloseHandle=lambda _h: 1,
        )

    return _loader


def test_m1_worker_budget_resolve_and_slots(tmp_path: Path) -> None:
    """Kill mutation survival su _resolve_budget_path, _load_slots e fair budget."""
    default_bp = wb_mod._resolve_budget_path(None)
    assert default_bp.name == "worker_budget.json"
    bad_slots = tmp_path / "bad_slots.json"
    bad_slots.write_text('{"slots": []}', encoding="utf-8")
    assert wb_mod._load_slots(bad_slots) == {"version": 1, "slots": {}}
    assert wb_mod.compute_fair_worker_budget(2, 1, cap=12) == 2
    assert wb_mod.compute_fair_worker_budget(1, 4, cap=12) == 1


def test_m1_lane_leases_os_probes_and_guards(tmp_path: Path, monkeypatch: Any) -> None:
    """Kill mutation survival su PID guards, _leases_file_path e Win32 OpenProcess."""
    assert ll_mod._leases_file_path(None).name == "runtime_leases.json"
    assert ll_mod._leases_file_path(tmp_path / "custom.json") == (tmp_path / "custom.json").resolve()
    assert ll_mod.get_process_create_time_epoch(99999991) is None
    assert ll_mod._is_pid_running_os(99999991) is False
    assert ll_mod._is_pid_running_os(os.getpid()) is True

    calls_zero = {"open": 0, "times": 0}
    monkeypatch.setattr(ll_mod.sys, "platform", "win32")
    monkeypatch.setattr(ll_mod.ctypes, "WinDLL", _make_probe_windll(calls_zero, open_handle=0), raising=False)
    assert ll_mod.get_process_create_time_epoch(0) is None
    assert ll_mod.get_process_create_time_epoch(-3) is None
    assert calls_zero["open"] == 0
    assert ll_mod.get_process_create_time_epoch(4242) is None
    assert calls_zero["open"] == 1
    assert calls_zero["times"] == 0


def test_m1_lane_leases_handle_ok_and_short_circuit(monkeypatch: Any) -> None:
    """Kill mutation survival su PID=1 boundary e short-circuit _is_pid_running_os."""
    calls_ok = {"open": 0, "times": 0}
    monkeypatch.setattr(ll_mod.sys, "platform", "win32")
    monkeypatch.setattr(ll_mod.ctypes, "WinDLL", _make_probe_windll(calls_ok, open_handle=123), raising=False)
    assert ll_mod.get_process_create_time_epoch(1) is not None
    assert calls_ok["times"] == 1
    assert ll_mod._is_pid_running_os(4242) is False

    monkeypatch.setattr(ll_mod.ctypes, "WinDLL", _boom_windll, raising=False)
    assert ll_mod._is_pid_running_os(0) is False
    assert ll_mod._is_pid_running_os(-3) is False


def test_m1_nvme_guards_posix_mutex_and_fallbacks(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre branch POSIX flock, timeout/errore Win32 mutex, empty path e reparse guards."""
    assert nsg_mod.is_cloud_mount_path("") is False
    monkeypatch.setattr(nsg_mod, "_win32_shell_local_appdata", lambda: None)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert nsg_mod.resolve_local_appdata_dir().is_dir()

    monkeypatch.setattr(nsg_mod, "_win32_drive_is_cloud", lambda _d: False)
    assert nsg_mod.is_cloud_mount_path("Z:/clean_local/proj") is False
    monkeypatch.setattr(nsg_mod, "is_reparse_entry", lambda _p: True)
    with pytest.raises(OSError):
        nsg_mod.ensure_nvme_local_dir(tmp_path / "rep_a", "fb_a")
    monkeypatch.setattr(nsg_mod, "is_reparse_entry", lambda _p: False)

    monkeypatch.setattr(nsg_mod.sys, "platform", "linux")
    assert nsg_mod.is_cloud_mount_path("/mnt/nvme/proj") is False
    monkeypatch.setattr(nsg_mod, "_fcntl", None)
    with nsg_mod.FailClosedNamedMutex("m1_posix_none", wait_ms=10):
        pass

    def _raise_busy(_fd: int, _op: int) -> None:
        raise BlockingIOError("busy")

    monkeypatch.setattr(nsg_mod, "_fcntl", SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=lambda _fd, _op: None))
    with nsg_mod.FailClosedNamedMutex("m1_posix_ok", wait_ms=10):
        pass
    monkeypatch.setattr(nsg_mod, "_fcntl", SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=_raise_busy))
    with pytest.raises(TimeoutError):
        nsg_mod.FailClosedNamedMutex("m1_posix_to", wait_ms=0).acquire()


def test_m1_nvme_win32_mutex_errors_and_wal_branches(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre errori Win32 mutex timeout/denied, release None e branch wal_scope."""
    monkeypatch.setattr(nsg_mod.sys, "platform", "win32")
    monkeypatch.setattr(nsg_mod, "create_or_open_named_mutex", lambda *_a, **_kw: (None, False, "timeout"))
    with pytest.raises(TimeoutError):
        nsg_mod.FailClosedNamedMutex("m1_w32_to", wait_ms=10).acquire()
    monkeypatch.setattr(nsg_mod, "create_or_open_named_mutex", lambda *_a, **_kw: (None, False, "denied"))
    with pytest.raises(OSError):
        nsg_mod.FailClosedNamedMutex("m1_w32_err", wait_ms=10).acquire()
    nsg_mod.FailClosedNamedMutex("m1_w32_rel").release()

    repo_dup = tmp_path / "repo_dup"
    repo_dup.mkdir()
    temp_w = tmp_path / "twal"
    scoped = ws_mod.get_scoped_wal_dirs([repo_dup, repo_dup], temp_root=temp_w)
    assert len(scoped) == 2
    bucket = temp_w / "nk_2pc_wal" / ws_mod.repo_wal_bucket_hash(repo_dup)
    bucket.mkdir(parents=True)
    (bucket / "ignore.txt").write_text("x", encoding="utf-8")
    stale_wal = bucket / "old.wal"
    stale_wal.write_text("OLD", encoding="utf-8")
    old_ts = 946684800.0
    os.utime(stale_wal, (old_ts, old_ts))
    assert ws_mod.has_scoped_active_wal([repo_dup], max_age_sec=60.0, temp_root=temp_w) is False


def test_m1_worker_budget_cap_and_prune_branches(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre NK_GLOBAL_WORKER_CAP env, slot=1 early exit, JSON corrotto e prune dead."""
    monkeypatch.setenv("NK_GLOBAL_WORKER_CAP", "6")
    assert wb_mod._resolve_global_cap() == 6
    monkeypatch.setenv("NK_GLOBAL_WORKER_CAP", "not_int")
    assert wb_mod._resolve_global_cap() == wb_mod.GLOBAL_WORKER_CAP

    bp = tmp_path / "wb_extra.json"
    with wb_mod.WorkerBudgetSlot(1, budget_path=bp) as s_one:
        assert s_one.workers == 1
    bp.write_text("{corrupt", encoding="utf-8")
    assert wb_mod._load_slots(bp) == {"version": 1, "slots": {}}
    slots_dict: dict[str, Any] = {"bad_entry": "invalid", "stale": {"updated_at": 1.0, "pid": 99999991}}
    wb_mod._prune_dead_slots(slots_dict, now_ts=1_800_000_000.0)
    assert slots_dict == {}


def test_m1_base_cache_prune_and_lease_error_branches(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre prune file stale/dir vuota in base cache, lease malformed store e missing release."""
    ws_p = tmp_path / "ws_prune"
    (ws_p / "scripts" / "sub").mkdir(parents=True)
    f_drop = ws_p / "scripts" / "sub" / "drop.py"
    f_keep = ws_p / "scripts" / "keep.py"
    f_keep.write_text("A = 1\n", encoding="utf-8")
    f_drop.write_text("B = 2\n", encoding="utf-8")
    bc = sync_nvme_base_cache(ws_p, ("scripts",), _ignore_tmp_and_pycache, _never_text, _is_dir_predicate, cache_root=tmp_path / "bc_p")
    f_drop.unlink()
    sync_nvme_base_cache(ws_p, ("scripts",), _ignore_tmp_and_pycache, _never_text, _is_dir_predicate, cache_root=tmp_path / "bc_p")
    assert not (bc / "scripts" / "sub").exists()

    bad_reg = tmp_path / "bad_reg.json"
    bad_reg.write_text("{broken", encoding="utf-8")
    assert ll_mod._read_store(bad_reg) == {"version": 1, "leases": {}}
    bad_reg.write_text("[]", encoding="utf-8")
    assert ll_mod._read_store(bad_reg) == {"version": 1, "leases": {}}
    leases_dict: dict[str, Any] = {"bad": "not_dict"}
    assert ll_mod._prune_stale_leases(leases_dict, 1_800_000_000.0) is True
    assert ll_mod.is_pid_lease_alive(os.getpid(), None) is True
    assert ll_mod.release_runtime_lease("missing_lease_id", registry_path=bad_reg) is False

    reg_x = tmp_path / "reg_x.json"
    ll_mod.register_runtime_lease(tmp_path / "rx", lane_id="lx", pid=os.getpid(), ports=[19355], registry_path=reg_x)
    assert os.getpid() in ll_mod.get_protected_leased_pids(exclude_lane_id=None, exclude_repo_root=tmp_path / "rx", registry_path=reg_x)
    with pytest.raises(OSError):
        ll_mod.allocate_lane_loopback_port("lx", port_min=19355, port_max=19355, registry_path=reg_x)

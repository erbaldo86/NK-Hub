# -*- coding: utf-8 -*-
"""Test Zero-Mock Milestone 1 NK-GEN-4.0.1: isolamento cross-project, NVMe e storage."""

from __future__ import annotations

import json
import os
import socket
import stat
import threading
import time
import typing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from _internal.ast_repo_mapper.generator import RepoMapGenerator
from _internal.ast_repo_mapper.subgraph_query import export_markdown_snapshot
from _internal.dast_sandbox_runner.holdout_assets_helpers import _is_external_app_repo
from _internal.memory_3tier_engine.models import _resolve_external_backup_dir, rotate_circular_backups
from _internal.memory_3tier_engine.sqlite_store import archive_to_tier3_impl, read_cold_archive_impl
from _internal.memory_3tier_engine.tier1_capsule import read_shadow_cache_impl, update_shadow_cache_impl
from _internal.nk_common.lane_leases import (
    allocate_lane_loopback_port,
    get_active_leased_conversation_ids,
    get_process_create_time_epoch,
    get_protected_leased_pids,
    is_pid_lease_alive,
    list_active_leases,
    register_runtime_lease,
    release_runtime_lease,
)
from _internal.nk_common.ledger_lock_io import LedgerMutexLock, PIDFileLock
from _internal.nk_common import nvme_base_cache as nbc_mod
from _internal.nk_common.nvme_base_cache import clone_nvme_base_to_mirror, sync_nvme_base_cache
from _internal.nk_common.nvme_storage_guards import (
    FailClosedNamedMutex,
    ensure_nvme_local_dir,
    is_cloud_mount_path,
    resolve_local_appdata_dir,
)
from _internal.nk_common.parallel_contracts import (
    ParallelLaneLeaseModel,
    ScopedCleanupReportModel,
    WorkerBudgetReceiptModel,
)
from _internal.nk_common.wal_scope import get_scoped_wal_dirs, has_scoped_active_wal, repo_wal_bucket_hash
from _internal.nk_common.win32_mutex import repo_path_hash12
from _internal.nk_common.worker_budget import WorkerBudgetSlot, compute_fair_worker_budget
from _internal.nk_hook_gate.write_gate import (
    _check_tensor_session_promote_gate,
    _extract_promote_root_candidates,
    _handle_write_gate,
)
from _internal.nk_session_bootstrap.bootstrap import NKSessionBootstrap
from _internal.nk_session_handoff.session_state import (
    get_handoff_state_mutex_name,
    prune_session_tracking_dirs,
    resolve_baseline_verification_source,
)
from _internal.rsi_convergence_engine.ecosystem_gates_ext import has_python_diff_signal_ext
from _internal.safe_cleanup_dev_servers import cleanup_cli as sc_cli
from _internal.win32_2pc_engine.constants import is_hub_repository_root, is_protected_governance_path
from _internal.win32_2pc_engine.staging_guards import _purge_production_bytecode
from scripts.deterministic_api_cache import DeterministicApiCache

pytestmark = pytest.mark.fast


def test_m1_nvme_storage_guards_and_wal_scope(tmp_path: Path) -> None:
    """Verifica SHGetFolderPathW, redirect cloud-mount, mutex fail-closed e scope WAL."""
    la = resolve_local_appdata_dir()
    assert la.is_dir() and not is_cloud_mount_path(tmp_path)
    assert is_cloud_mount_path("G:/Il mio Drive/Antigravity/NK_Hub")
    assert is_cloud_mount_path("C:/Users/demo/OneDrive - Org/proj")

    local_sub = ensure_nvme_local_dir(tmp_path / "local_sub", "fallback_a")
    cloud_red = ensure_nvme_local_dir("G:/Il mio Drive/FakeProj/.cache", f"m1_test_{os.getpid()}")
    assert local_sub.is_dir() and cloud_red.is_dir() and not is_cloud_mount_path(cloud_red)

    mname = f"Local\\NK_M1_Test_{os.getpid()}_{time.monotonic_ns()}"
    with FailClosedNamedMutex(mname, wait_ms=1000):
        pass

    repo_a, repo_b = tmp_path / "repo_a", tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()
    temp_wal = tmp_path / "temp_wal"
    scoped_a = get_scoped_wal_dirs([repo_a], temp_root=temp_wal)
    assert len(scoped_a) == 2 and (temp_wal in scoped_a) is False
    bucket_b = temp_wal / "nk_2pc_wal" / repo_wal_bucket_hash(repo_b)
    bucket_b.mkdir(parents=True)
    (bucket_b / "other.wal").write_text("ACTIVE", encoding="utf-8")
    (temp_wal / "nk_2pc_wal" / "global.wal").write_text("ACTIVE", encoding="utf-8")
    assert has_scoped_active_wal([repo_a], max_age_sec=60.0, temp_root=temp_wal) is False
    assert has_scoped_active_wal([repo_b], max_age_sec=60.0, temp_root=temp_wal) is True


def test_m1_lane_leases_and_ports(tmp_path: Path) -> None:
    """Verifica lease lifecycle, anti PID-reuse e allocazione porte loopback."""
    reg_p = tmp_path / "runtime_leases.json"
    my_pid = os.getpid()
    ct = get_process_create_time_epoch(my_pid)
    assert is_pid_lease_alive(my_pid, ct) is True
    if ct is not None:
        assert is_pid_lease_alive(my_pid, ct - 5000.0) is False

    port = allocate_lane_loopback_port("lane_alpha", port_min=19100, port_max=19299, registry_path=reg_p)
    assert 19100 <= port <= 19299
    repo_a, repo_b = tmp_path / "app_a", tmp_path / "app_b"
    rec_a = register_runtime_lease(repo_a, lane_id="lane_a", conversation_id="cid_a", ports=[port], registry_path=reg_p)
    register_runtime_lease(repo_b, lane_id="lane_b", conversation_id="cid_b", pid=my_pid, registry_path=reg_p)
    register_runtime_lease(repo_a, lane_id="dead_lane", conversation_id="cid_dead", pid=99999991, registry_path=reg_p)

    active_a = list_active_leases(repo_a, registry_path=reg_p)
    assert len(active_a) == 1 and active_a[0]["lane_id"] == "lane_a"
    assert get_active_leased_conversation_ids(repo_a, registry_path=reg_p) == {"cid_a"}
    assert my_pid in get_protected_leased_pids(exclude_lane_id="lane_a", exclude_repo_root=repo_a, registry_path=reg_p)
    assert release_runtime_lease(rec_a["lease_id"], registry_path=reg_p) is True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", port))
        port2 = allocate_lane_loopback_port("lane_alpha", port_min=port, port_max=port + 10, registry_path=reg_p)
        assert port2 != port


def test_m1_worker_budget_and_contracts(tmp_path: Path) -> None:
    """Verifica worker budget fairness globale <= 12 e contratti Pydantic parallel M1."""
    b_path = tmp_path / "worker_budget.json"
    repo_a = tmp_path / "app_a"
    assert compute_fair_worker_budget(10, 3, cap=12) == 4
    with WorkerBudgetSlot(8, budget_path=b_path) as s1, WorkerBudgetSlot(8, budget_path=b_path) as s2:
        assert s1.workers <= 12 and s2.workers <= 6 and (s1.workers + s2.workers) >= 4

    lease_m = ParallelLaneLeaseModel(
        lease_id="lease_1",
        repo_root=str(repo_a),
        lane_id="lane_a",
        conversation_id="cid_a",
        pid=os.getpid(),
        ports=[19100],
        updated_at=1700000000.0,
        ttl_sec=120.0,
    )
    assert lease_m.lane_id == "lane_a"
    assert WorkerBudgetReceiptModel(slot_id="s_1", requested=8, allocated=4, active_slots=2, global_cap=12).allocated == 4
    assert ScopedCleanupReportModel(status="OK", workspace_root=str(repo_a)).strict_scope is False
    with pytest.raises(ValidationError):
        WorkerBudgetReceiptModel(slot_id="s_2", requested=8, allocated=13, active_slots=1, global_cap=12)


def test_m1_nvme_base_cache_zero_hardlink(tmp_path: Path) -> None:
    """Verifica base cache RO e clone indipendente con st_ino distinti (zero os.link)."""
    ws, cache_root, mirror = tmp_path / "proj", tmp_path / "base_cache", tmp_path / "mirror"
    (ws / "scripts").mkdir(parents=True)
    src_py = ws / "scripts" / "mod_a.py"
    src_py.write_text("VAL = 1\n", encoding="utf-8")
    (ws / "README.md").write_text("# Proj\n", encoding="utf-8")

    base = sync_nvme_base_cache(
        ws, ("scripts",), lambda _d, _n: set(), lambda p: p.suffix == ".md", lambda c, r: c.is_dir(), cache_root=cache_root
    )
    clone_nvme_base_to_mirror(base, mirror, repo_root_hint=ws)

    base_file, mirror_file = base / "scripts" / "mod_a.py", mirror / "scripts" / "mod_a.py"
    assert base_file.stat().st_ino != mirror_file.stat().st_ino
    assert (base_file.stat().st_mode & stat.S_IWRITE) == 0
    mirror_file.write_text("VAL = 99\n", encoding="utf-8")
    assert base_file.read_text(encoding="utf-8") == "VAL = 1\n"

    src_py.write_text("VAL = 2\n", encoding="utf-8")
    sync_nvme_base_cache(
        ws, ("scripts",), lambda _d, _n: set(), lambda p: p.suffix == ".md", lambda c, r: c.is_dir(), cache_root=cache_root
    )
    assert base_file.read_text(encoding="utf-8") == "VAL = 2\n"


def test_m1_hook_governance_cleanup_and_ext_detection(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    """Verifica root gate, split shell segments, governance ext tests/ e cleanup leased PIDs."""
    hub_like = tmp_path / "NK_Hub"
    ext_repo = tmp_path / "NK Proget" / "Locale" / "MySrcApp"
    (hub_like / ".agents" / "skills").mkdir(parents=True)
    (hub_like / "scripts").mkdir(parents=True)
    (ext_repo / "src").mkdir(parents=True)
    (ext_repo / "tests").mkdir(parents=True)

    cands = _extract_promote_root_candidates(
        ["python", "win32_2pc_engine.py", "--promote-staging", "--repo-root", str(ext_repo)], hub_like
    )
    assert cands == [ext_repo.resolve()]
    assert is_hub_repository_root(hub_like) is True
    assert is_hub_repository_root(ext_repo) is False
    assert is_protected_governance_path("tests/test_app.py", repo_root=ext_repo) is False
    assert is_protected_governance_path("tests/evals/x.json", repo_root=ext_repo) is True
    assert is_protected_governance_path("tests/test_app.py", repo_root=hub_like) is True
    assert _is_external_app_repo(ext_repo) is True
    assert has_python_diff_signal_ext(ext_repo, "code_rsi", None) is False

    seg_res = _handle_write_gate(
        {"toolName": "run_command"},
        hub_like,
        True,
        "",
        "python scripts/nk_session_bootstrap.py; Set-Content -Path src_app/evil.py -Value x",
        "",
    )
    assert seg_res.get("decision") == "deny"

    killed: list[int] = []
    monkeypatch.setattr(sc_cli, "get_pids_listening_on_ports", lambda *_a, **_k: {4101, 4102})
    monkeypatch.setattr(sc_cli, "get_protected_leased_pids", lambda **_k: {4101})
    monkeypatch.setattr(sc_cli, "kill_pid_tree", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(sc_cli, "time", SimpleNamespace(sleep=lambda _s: None))
    sc_cli.run_cleanup(workspace_root=ext_repo, dry_run=False, as_json=True, lane_id="lane_self", strict_scope=True)
    rep = json.loads(capsys.readouterr().out)
    assert rep["detected_pids"] == [4102] and rep["skipped_leased_pids"] == [4101] and killed == [4102]


def test_m1_api_cache_ledger_and_memory(tmp_path: Path) -> None:
    """Verifica API cache RO concurrency, LedgerMutexLock, shadow cache e tier3 cold archive."""
    with DeterministicApiCache(db_path=tmp_path / "api.db", ttl_seconds=60.0) as cache:
        cache.set("https://local/m1", 200, '{"ok":true}')
        errors: list[Exception] = []

        def _reader() -> None:
            try:
                assert cache.get("https://local/m1")[0] == 200
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    with LedgerMutexLock(tmp_path / "ledger.jsonl"):
        pass
    cloud_lock = PIDFileLock(Path("G:/Il mio Drive/FakeProj/l.lock"))
    assert not is_cloud_mount_path(cloud_lock.lock_file)

    mem_base = tmp_path / "mem"
    dom_dir = mem_base / "01_Bug_Diagnostics"
    dom_dir.mkdir(parents=True)
    ep_file = dom_dir / "episodes.jsonl"
    ep_file.write_text('{"episode_id":"1"}\n', encoding="utf-8")
    cache_d = tmp_path / "shadow_cache"
    cache_d.mkdir()
    update_shadow_cache_impl(cache_d, "p1", mem_base, "01_Bug_Diagnostics", ())
    assert read_shadow_cache_impl(cache_d, "p1", mem_base, "01_Bug_Diagnostics") == []
    rotate_circular_backups(ep_file, backup_dir=tmp_path / "bkp")
    assert (tmp_path / "bkp" / "episodes.jsonl.bak_1").is_file()
    assert _resolve_external_backup_dir(tmp_path / "nk_tracking" / "dom" / "episodes.jsonl") is not None

    from _internal.memory_3tier_engine.models import MemoryEpisode
    ep_obj = MemoryEpisode(episode_id="ep1", domain="01_Bug_Diagnostics", title="t", content="c")
    archive_to_tier3_impl(mem_base, "01_Bug_Diagnostics", [ep_obj])
    assert len(read_cold_archive_impl(dom_dir / "archive.cold.jsonl.gz")) == 1


def test_m1_bootstrap_repomap_purge_and_sessions(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifica isolamento bootstrap per conversation_id, repo_map overlay, purge pycache e sessioni."""
    b1 = NKSessionBootstrap(workspace_root=tmp_path, conversation_id="conv_one")
    b2 = NKSessionBootstrap(workspace_root=tmp_path, conversation_id="conv_two")
    assert b1.fast_cache_file != b2.fast_cache_file and "Global\\NK_HandoffState" in get_handoff_state_mutex_name(tmp_path)

    diag = tmp_path / "diag"
    diag.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".staging" / "src").mkdir(parents=True)
    (tmp_path / ".staging" / "src" / "a.py").write_text("def hello_staged():\n    return 2\n", encoding="utf-8")
    snap = export_markdown_snapshot(tmp_path, tmp_path / "repo_map.md")
    assert snap.files_scanned >= 1 and "hello_staged" in (tmp_path / "repo_map.md").read_text(encoding="utf-8")

    touched_py = tmp_path / "scripts" / "x.py"
    touched_pc = touched_py.parent / "__pycache__"
    untouched_pc = tmp_path / "scripts" / "sub" / "__pycache__"
    touched_pc.mkdir(parents=True)
    untouched_pc.mkdir(parents=True)
    (touched_pc / "x.pyc").write_bytes(b"0")
    (untouched_pc / "keep.pyc").write_bytes(b"1")
    _purge_production_bytecode(tmp_path, touched_rel_paths=["scripts/x.py"])
    assert not touched_pc.exists() and untouched_pc.exists()

    repo_scoped = tmp_path / "scoped_repo"
    repo_scoped.mkdir()
    monkeypatch.setenv("NK_DIAGNOSTICS_DIR", str(diag))
    scoped_json = diag / f"pytest_iso_last_{repo_path_hash12(repo_scoped)}.json"
    scoped_json.write_text(json.dumps({"exit_code": 0, "passed": 42, "failed": 0, "errors": 0, "success": True}), encoding="utf-8")
    assert resolve_baseline_verification_source(repo_scoped, "cid_x", session_start_ns=1)[0] == 42

    sess_root = tmp_path / "sess_repo"
    for i in range(7):
        d = sess_root / "nk_tracking" / "sessions" / f"cid_{i}"
        d.mkdir(parents=True)
        (d / "f.txt").write_text("x", encoding="utf-8")
    reg_p2 = tmp_path / "leases_prune.json"
    register_runtime_lease(sess_root, lane_id="l_keep", conversation_id="cid_0", registry_path=reg_p2)
    monkeypatch.setattr(
        "_internal.nk_session_handoff.session_state.get_active_leased_conversation_ids",
        lambda _r: get_active_leased_conversation_ids(sess_root, registry_path=reg_p2),
    )
    prune_session_tracking_dirs(sess_root, active_conversation_id="cid_6", max_sessions=5)
    assert (sess_root / "nk_tracking" / "sessions" / "cid_0").is_dir()


def test_m1_quorum_security_and_scope_regressions(tmp_path: Path, monkeypatch: Any) -> None:
    """Copre anti-spoofing flag, multi-segment 2PC gate, scope cleanup, hints e reparse cache."""
    hub_like = tmp_path / "NK_Hub"
    ext_repo = tmp_path / "NK Proget" / "Locale" / "MySrcApp"
    (hub_like / ".agents" / "skills").mkdir(parents=True)
    (hub_like / "nk_tracking" / "tensor_sessions").mkdir(parents=True)
    (ext_repo / "src").mkdir(parents=True)
    (hub_like / "nk_tracking" / "tensor_sessions" / "ACTIVE.json").write_text('{"accepted": false}', encoding="utf-8")

    spoof_words = ["python", "win32_2pc_engine.py", "--promote-staging", "--milestone", "--repo-root=C:/Temp/ext"]
    assert _extract_promote_root_candidates(spoof_words, hub_like) == [hub_like.resolve()]

    cmd = f"python win32_2pc_engine.py --promote-staging ; python win32_2pc_engine.py --promote-staging --repo-root {ext_repo}"
    assert _check_tensor_session_promote_gate(cmd, cmd.lower(), hub_like).get("decision") == "deny"

    reg_s = tmp_path / "reg_scope.json"
    register_runtime_lease(ext_repo, lane_id="default", pid=os.getpid(), registry_path=reg_s)
    assert os.getpid() in get_protected_leased_pids(exclude_lane_id="default", exclude_repo_root=hub_like, registry_path=reg_s)
    assert os.getpid() in get_protected_leased_pids(exclude_lane_id=None, exclude_repo_root=ext_repo, registry_path=reg_s)
    assert isinstance(typing.get_type_hints(sc_cli._collect_psutil_pids), dict)

    monkeypatch.setattr(nbc_mod, "is_reparse_entry", lambda _p: True)
    with pytest.raises(OSError):
        sync_nvme_base_cache(ext_repo, ("src",), lambda _d, _n: set(), lambda _p: False, lambda c, _r: c.is_dir(), cache_root=tmp_path / "bc_rep")

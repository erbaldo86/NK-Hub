# -*- coding: utf-8 -*-
"""Coda FIFO su NVMe per Commit Train con pruning PID morti e Priority Barrier Ticket."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.lane_leases import get_process_create_time_epoch, is_pid_lease_alive
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex, ensure_nvme_local_dir
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import repo_path_hash12


def resolve_commit_train_queue_path(
    root: Union[str, Path],
    queue_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Restituisce %TEMP%/nk_parallel/<repo12>/commit_train_queue.json o path esplicito."""
    if queue_path is not None:
        cand = Path(queue_path)
        if is_reparse_entry(cand) or is_reparse_entry(cand.parent):
            raise OSError(f"Reparse point vietato su queue_path: {cand}")
        return cand.resolve()
    base_dir = ensure_nvme_local_dir(Path(tempfile.gettempdir()) / "nk_parallel", "nk_parallel")
    repo_dir = base_dir / repo_path_hash12(Path(root).resolve())
    if is_reparse_entry(repo_dir):
        raise OSError(f"Reparse point vietato su {repo_dir}")
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir / "commit_train_queue.json"


def _queue_mutex(root: Union[str, Path]) -> FailClosedNamedMutex:
    h12 = repo_path_hash12(Path(root).resolve())
    return FailClosedNamedMutex(f"Local\\NK_CommitTrainQueue_{h12}", wait_ms=5000)


def _load_queue_unlocked(q_path: Path) -> Dict[str, Any]:
    if is_reparse_entry(q_path):
        raise OSError(f"Reparse point vietato su {q_path}")
    if not q_path.is_file():
        return {"version": 1, "items": []}
    raw = json.loads(q_path.read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        return raw
    return {"version": 1, "items": []}


def _save_queue_unlocked(q_path: Path, data: Dict[str, Any]) -> None:
    ok, err = atomic_write_json(
        q_path, data, indent=2, ensure_ascii=False, ensure_parent=True,
        fsync_data=False, reparse_check=is_reparse_entry,
    )
    if not ok:
        raise OSError(f"Scrittura atomica commit_train_queue fallita: {err}")


def _reap_dead_items(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    kept: List[Dict[str, Any]] = []
    changed = False
    for item in items:
        if not isinstance(item, dict) or not item.get("lane_id"):
            changed = True
            continue
        pid = int(item.get("pid", 0) or 0)
        ctime = item.get("process_create_time_epoch")
        if is_pid_lease_alive(pid, ctime):
            kept.append(item)
        else:
            changed = True
    return kept, changed


def enqueue_lane(
    root: Union[str, Path],
    lane_id: str,
    *,
    rebase_count: int = 0,
    staging_manifest_sha256: str = "",
    pid: Optional[int] = None,
    barrier_threshold: int = 2,
    queue_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Accoda o aggiorna una lane nella coda Commit Train sotto Named Mutex."""
    norm_lane = validate_lane_id(lane_id)
    eff_pid = int(pid if pid is not None else os.getpid())
    q_path = resolve_commit_train_queue_path(root, queue_path)
    ctime = get_process_create_time_epoch(eff_pid)
    with _queue_mutex(root):
        data = _load_queue_unlocked(q_path)
        items, _ = _reap_dead_items(data["items"])
        for existing in items:
            if existing["lane_id"] == norm_lane:
                existing["pid"] = eff_pid
                existing["process_create_time_epoch"] = ctime
                existing["staging_manifest_sha256"] = str(staging_manifest_sha256 or existing.get("staging_manifest_sha256", ""))
                data["items"] = items
                _save_queue_unlocked(q_path, data)
                return dict(existing)
        rc = max(0, int(rebase_count))
        rec: Dict[str, Any] = {
            "ticket_id": f"tk_{uuid.uuid4().hex[:10]}",
            "lane_id": norm_lane,
            "pid": eff_pid,
            "process_create_time_epoch": ctime,
            "enqueued_at": time.time(),
            "rebase_count": rc,
            "priority_barrier": rc >= max(1, int(barrier_threshold)),
            "staging_manifest_sha256": str(staging_manifest_sha256 or ""),
        }
        items.append(rec)
        data["items"] = items
        _save_queue_unlocked(q_path, data)
        return dict(rec)


def record_rebase_and_promote_barrier(
    root: Union[str, Path],
    lane_id: str,
    *,
    barrier_threshold: int = 2,
    queue_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Incrementa rebase_count e attiva priority_barrier oltre threshold anti-starvation."""
    norm_lane = validate_lane_id(lane_id)
    q_path = resolve_commit_train_queue_path(root, queue_path)
    with _queue_mutex(root):
        data = _load_queue_unlocked(q_path)
        items, _ = _reap_dead_items(data["items"])
        for item in items:
            if item["lane_id"] == norm_lane:
                item["rebase_count"] = int(item.get("rebase_count", 0)) + 1
                if item["rebase_count"] >= max(1, int(barrier_threshold)):
                    item["priority_barrier"] = True
                data["items"] = items
                _save_queue_unlocked(q_path, data)
                return dict(item)
    return enqueue_lane(
        root, norm_lane, rebase_count=1, barrier_threshold=barrier_threshold, queue_path=queue_path
    )


def is_lane_turn(
    root: Union[str, Path],
    lane_id: str,
    *,
    queue_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, Optional[str]]:
    """Verifica se lane_id puo avanzare rispettando eventuali Priority Barrier Ticket."""
    norm_lane = validate_lane_id(lane_id)
    q_path = resolve_commit_train_queue_path(root, queue_path)
    with _queue_mutex(root):
        data = _load_queue_unlocked(q_path)
        items, changed = _reap_dead_items(data["items"])
        if changed:
            data["items"] = items
            _save_queue_unlocked(q_path, data)
    if not items:
        return True, None
    barriers = [it for it in items if bool(it.get("priority_barrier", False))]
    if barriers:
        leader = barriers[0]["lane_id"]
        return (leader == norm_lane), (None if leader == norm_lane else leader)
    return True, None


def dequeue_lane(
    root: Union[str, Path],
    lane_id: str,
    *,
    queue_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Rimuove lane_id dalla coda Commit Train al termine o abort definitivo."""
    norm_lane = validate_lane_id(lane_id)
    q_path = resolve_commit_train_queue_path(root, queue_path)
    with _queue_mutex(root):
        data = _load_queue_unlocked(q_path)
        before = len(data["items"])
        data["items"] = [it for it in data["items"] if isinstance(it, dict) and it.get("lane_id") != norm_lane]
        removed = len(data["items"]) < before
        if removed:
            _save_queue_unlocked(q_path, data)
        return removed


def list_queue_items(
    root: Union[str, Path],
    *,
    queue_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Restituisce gli elementi vivi ordinati della coda Commit Train."""
    q_path = resolve_commit_train_queue_path(root, queue_path)
    with _queue_mutex(root):
        data = _load_queue_unlocked(q_path)
        items, changed = _reap_dead_items(data["items"])
        if changed:
            data["items"] = items
            _save_queue_unlocked(q_path, data)
        return [dict(it) for it in items]

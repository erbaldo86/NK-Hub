# -*- coding: utf-8 -*-
"""Budget globale dinamico dei worker pytest/mutation tra sessioni parallele."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.lane_leases import get_process_create_time_epoch, is_pid_lease_alive
from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex, resolve_local_appdata_dir

GLOBAL_WORKER_CAP: int = 12
_BUDGET_MUTEX_NAME = "Local\\NK_WorkerBudget"
_SLOT_TTL_SEC = 360.0


def _resolve_budget_path(budget_path: Optional[Union[str, Path]] = None) -> Path:
    if budget_path is not None:
        return Path(budget_path).resolve()
    return (resolve_local_appdata_dir() / "nk_hub" / "worker_budget.json").resolve()


def _resolve_global_cap() -> int:
    raw = os.environ.get("NK_GLOBAL_WORKER_CAP", "").strip()
    if raw:
        try:
            return max(2, min(GLOBAL_WORKER_CAP, int(raw)))
        except ValueError:
            pass
    return GLOBAL_WORKER_CAP


def compute_fair_worker_budget(requested: int, active_slots: int, cap: int = GLOBAL_WORKER_CAP) -> int:
    """Calcola la quota equa di worker in [2..cap] dato il numero di esecutori attivi."""
    eff_cap = max(2, int(cap))
    req = max(1, int(requested))
    if req == 1:
        return 1
    slots = max(1, int(active_slots))
    fair = max(2, eff_cap // slots)
    return min(req, eff_cap, fair)


def _load_slots(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "slots": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and isinstance(data.get("slots"), dict):
            return data
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    return {"version": 1, "slots": {}}


def _prune_dead_slots(slots: Dict[str, Any], now_ts: float) -> None:
    for sid in list(slots.keys()):
        rec = slots.get(sid)
        if not isinstance(rec, dict):
            slots.pop(sid, None)
            continue
        ts = float(rec.get("updated_at", 0.0) or 0.0)
        pid = int(rec.get("pid", 0) or 0)
        ctime = rec.get("process_create_time_epoch")
        if (now_ts - ts) > _SLOT_TTL_SEC or not is_pid_lease_alive(pid, ctime):
            slots.pop(sid, None)


class WorkerBudgetSlot:
    """Context manager che coordina la concorrenza tra piu run pytest su NVMe."""

    def __init__(
        self,
        requested: int,
        *,
        budget_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.requested = max(1, int(requested))
        self.budget_path = _resolve_budget_path(budget_path)
        self.slot_id = f"wb_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self.workers: int = self.requested
        self._entered = False

    def __enter__(self) -> "WorkerBudgetSlot":
        now_ts = time.time()
        cap = _resolve_global_cap()
        if self.requested == 1:
            self.workers = 1
            self._entered = True
            return self
        with FailClosedNamedMutex(_BUDGET_MUTEX_NAME, wait_ms=2000):
            data = _load_slots(self.budget_path)
            _prune_dead_slots(data["slots"], now_ts)
            pid = os.getpid()
            data["slots"][self.slot_id] = {
                "pid": pid,
                "process_create_time_epoch": get_process_create_time_epoch(pid),
                "requested": self.requested,
                "updated_at": now_ts,
            }
            self.workers = compute_fair_worker_budget(
                self.requested, len(data["slots"]), cap=cap
            )
            atomic_write_json(
                self.budget_path, data, indent=2, ensure_parent=True, fsync_data=False
            )
        self._entered = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._entered or self.requested == 1:
            self._entered = False
            return
        try:
            with FailClosedNamedMutex(_BUDGET_MUTEX_NAME, wait_ms=2000):
                data = _load_slots(self.budget_path)
                if self.slot_id in data["slots"]:
                    data["slots"].pop(self.slot_id, None)
                    atomic_write_json(
                        self.budget_path, data, indent=2, ensure_parent=True, fsync_data=False
                    )
        except (OSError, TimeoutError):
            return None
        finally:
            self._entered = False

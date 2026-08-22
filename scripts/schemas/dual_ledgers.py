"""
Nexus Keystone v1.1.0-Universal: Dual Ledgers Architecture.
Compliant with:
- task_ledger.jsonl: Declarative immutable DAG with SHA-256 hash-chaining and topological validation.
- progress_ledger.jsonl: Append-only event stream protected by PID-aware file locking with stale detection.
- Pydantic v2 in Strict Mode.
- Win32 atomic operations & cross-platform lock fallback.
"""

from __future__ import annotations

import collections
import contextlib
import ctypes
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Literal, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, Field, ConfigDict, JsonValue


TaskStatus = Literal["PENDING", "IN_PROGRESS", "BLOCKED", "COMPLETED", "FAILED", "ROLLED_BACK"]
EventType = Literal[
    "STARTED",
    "CHECKPOINT",
    "HEALING_TRIGGERED",
    "GATE_PASSED",
    "COMPLETED",
    "FAILED",
]


# ----------------------------------------------------------------------
# CANONICAL HASH HELPERS
# ----------------------------------------------------------------------
def canonical_json_bytes(data: Dict[str, Any]) -> bytes:
    """Produces deterministic UTF-8 JSON bytes with sorted keys."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------
# PYDANTIC V2 STRICT MODELS
# ----------------------------------------------------------------------
class TaskDAGNode(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_id: str = Field(description="Unique task identifier in DAG")
    parent_ids: List[str] = Field(default_factory=list, description="Direct upstream task IDs")
    action: str = Field(description="Declarative action verb/type")
    target_agent: str = Field(description="Assigned NK Agent")
    status: TaskStatus = Field(default="PENDING", description="Current DAG node status")
    payload: Dict[str, JsonValue] = Field(default_factory=dict, description="Task configuration and payload")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")
    payload_hash: str = Field(description="SHA-256 of canonical payload JSON")
    prev_hash: str = Field(description="SHA-256 of preceding DAG entry (hash chain link)")
    node_hash: str = Field(description="SHA-256 of full node content")

    @classmethod
    def create(
        cls,
        task_id: str,
        action: str,
        target_agent: str,
        parent_ids: Sequence[str] = (),
        payload: Optional[Dict[str, Any]] = None,
        prev_hash: str = "0" * 64,
        status: TaskStatus = "PENDING",
    ) -> TaskDAGNode:
        p_dict = payload or {}
        p_bytes = canonical_json_bytes(p_dict)
        p_hash = sha256_hex(p_bytes)

        now = time.time()
        core_dict: Dict[str, Any] = {
            "task_id": task_id,
            "parent_ids": list(parent_ids),
            "action": action,
            "target_agent": target_agent,
            "status": status,
            "payload_hash": p_hash,
            "prev_hash": prev_hash,
            "created_at": now,
        }
        n_hash = sha256_hex(canonical_json_bytes(core_dict))

        return cls(
            task_id=task_id,
            parent_ids=list(parent_ids),
            action=action,
            target_agent=target_agent,
            status=status,
            payload=p_dict,
            created_at=now,
            payload_hash=p_hash,
            prev_hash=prev_hash,
            node_hash=n_hash,
        )

    def verify_integrity(self, expected_prev_hash: str) -> bool:
        if self.prev_hash != expected_prev_hash:
            return False
        if sha256_hex(canonical_json_bytes(self.payload)) != self.payload_hash:
            return False
        core_dict: Dict[str, Any] = {
            "task_id": self.task_id,
            "parent_ids": self.parent_ids,
            "action": self.action,
            "target_agent": self.target_agent,
            "status": self.status,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "created_at": self.created_at,
        }
        return sha256_hex(canonical_json_bytes(core_dict)) == self.node_hash


class ProgressEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    event_id: str = Field(description="Unique event ID")
    task_id: str = Field(description="Associated DAG task ID")
    step_index: int = Field(ge=0, description="Sequential step index within task")
    event_type: EventType = Field(description="Lifecycle event category")
    timestamp: float = Field(default_factory=time.time, description="Event emission timestamp")
    details: Dict[str, JsonValue] = Field(default_factory=dict, description="Event payload/metrics")
    pid: int = Field(default_factory=os.getpid, description="Emitting process ID")


# ----------------------------------------------------------------------
# PID-AWARE FILE LOCKING (Win32 + POSIX Fallback)
# ----------------------------------------------------------------------
class PIDFileLock:
    """
    Cooperative lock file storing the owning PID and timestamp.
    Includes stale lock detection (>30s or dead PID).
    """

    def __init__(self, lock_file: Path, stale_timeout_sec: float = 30.0) -> None:
        self.lock_file = lock_file
        self.stale_timeout_sec = stale_timeout_sec
        self.acquired = False

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            # Win32 check via OpenProcess
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def acquire(self, timeout_sec: float = 5.0) -> bool:
        deadline = time.time() + timeout_sec
        current_pid = os.getpid()

        while time.time() < deadline:
            try:
                # O_EXCL | O_CREAT guarantees atomic file creation
                fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"pid": current_pid, "timestamp": time.time()}, f)
                self.acquired = True
                return True
            except FileExistsError:
                # Lock exists - check if stale
                try:
                    content = self.lock_file.read_text(encoding="utf-8")
                    lock_data = json.loads(content)
                    lock_pid = lock_data.get("pid", 0)
                    lock_time = lock_data.get("timestamp", 0)

                    is_stale_time = (time.time() - lock_time) > self.stale_timeout_sec
                    is_dead_pid = not self._is_pid_alive(lock_pid)

                    if is_stale_time or is_dead_pid:
                        # Break stale lock safely
                        try:
                            self.lock_file.unlink()
                        except OSError:
                            pass
                except Exception:
                    pass

                time.sleep(0.02)

        return False

    def release(self) -> None:
        if self.acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except OSError:
                pass
            self.acquired = False

    def __enter__(self) -> PIDFileLock:
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock: {self.lock_file}")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


# ----------------------------------------------------------------------
# TASK LEDGER (Immutable DAG)
# ----------------------------------------------------------------------
class TaskLedger:
    """
    Manages task_dag.jsonl: Declarative immutable DAG with hash-chaining.
    """

    def __init__(self, ledger_path: Path | str) -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._nodes: Dict[str, TaskDAGNode] = {}
        self._last_hash = "0" * 64
        self._load_and_verify()

    def _load_and_verify(self) -> None:
        self._nodes.clear()
        self._last_hash = "0" * 64

        if not self.ledger_path.exists():
            return

        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                node = TaskDAGNode.model_validate(data)

                if not node.verify_integrity(self._last_hash):
                    raise ValueError(
                        f"TaskLedger integrity violation at line {line_idx}: node_id={node.task_id}"
                    )

                self._nodes[node.task_id] = node
                self._last_hash = node.node_hash

    def add_task(
        self,
        task_id: str,
        action: str,
        target_agent: str,
        parent_ids: Sequence[str] = (),
        payload: Optional[Dict[str, Any]] = None,
    ) -> TaskDAGNode:
        if task_id in self._nodes:
            raise ValueError(f"Duplicate task_id: {task_id}")

        for pid in parent_ids:
            if pid not in self._nodes:
                raise ValueError(f"Parent task {pid} does not exist in DAG")

        node = TaskDAGNode.create(
            task_id=task_id,
            action=action,
            target_agent=target_agent,
            parent_ids=parent_ids,
            payload=payload,
            prev_hash=self._last_hash,
            status="PENDING",
        )

        # Append atomically under PID lock
        lock = PIDFileLock(self.ledger_path.with_suffix(".lock"))
        with lock:
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(node.model_dump_json() + "\n")

        self._nodes[node.task_id] = node
        self._last_hash = node.node_hash
        return node

    def get_task(self, task_id: str) -> Optional[TaskDAGNode]:
        return self._nodes.get(task_id)

    def list_tasks(self) -> List[TaskDAGNode]:
        return list(self._nodes.values())

    def verify_dag(self) -> Tuple[bool, str]:
        """
        Validates topological sorting and ensures no cycles exist in DAG.
        """
        in_degree: Dict[str, int] = {k: 0 for k in self._nodes}
        adj: Dict[str, List[str]] = collections.defaultdict(list)

        for tid, node in self._nodes.items():
            for pid in node.parent_ids:
                adj[pid].append(tid)
                in_degree[tid] += 1

        queue = collections.deque([tid for tid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            curr = queue.popleft()
            visited_count += 1
            for child in adj[curr]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if visited_count != len(self._nodes):
            return False, "Cycle detected in Task DAG"
        return True, "DAG is valid and acyclic"

    def get_roots(self) -> List[TaskDAGNode]:
        return [n for n in self._nodes.values() if not n.parent_ids]

    def get_leaves(self) -> List[TaskDAGNode]:
        all_parents: Set[str] = set()
        for n in self._nodes.values():
            all_parents.update(n.parent_ids)
        return [n for n in self._nodes.values() if n.task_id not in all_parents]


# ----------------------------------------------------------------------
# PROGRESS LEDGER (Append-Only Event Stream)
# ----------------------------------------------------------------------
class ProgressLedger:
    """
    Manages progress_ledger.jsonl: High-frequency append-only event stream
    protected by PID-aware file locking.
    """

    def __init__(self, ledger_path: Path | str) -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.ledger_path.with_suffix(".lock")

    def append_event(
        self,
        event_id: str,
        task_id: str,
        step_index: int,
        event_type: EventType,
        details: Optional[Dict[str, Any]] = None,
    ) -> ProgressEvent:
        event = ProgressEvent(
            event_id=event_id,
            task_id=task_id,
            step_index=step_index,
            event_type=event_type,
            details=details or {},
        )

        lock = PIDFileLock(self.lock_file)
        with lock:
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")

        return event

    def read_events(self, task_id: Optional[str] = None) -> List[ProgressEvent]:
        if not self.ledger_path.exists():
            return []

        events: List[ProgressEvent] = []
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = ProgressEvent.model_validate_json(line)
                if task_id is None or ev.task_id == task_id:
                    events.append(ev)

        return events

    def get_latest_event(self, task_id: str) -> Optional[ProgressEvent]:
        events = self.read_events(task_id)
        return events[-1] if events else None

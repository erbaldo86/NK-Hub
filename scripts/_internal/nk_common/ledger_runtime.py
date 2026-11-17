# -*- coding: utf-8 -*-
"""
Runtime I/O e locking Win32/POSIX per i Dual Ledgers di NK Hub Generation 1.0.0-Generation.
Ospita PIDFileLock, TaskLedger e ProgressLedger separati dai DTO L0 (zero cicli Tarjan).
"""

from __future__ import annotations

import collections
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from schemas.dual_ledgers_models import (
    EventType,
    ProgressEvent,
    TaskDAGNode,
)
from _internal.nk_common.ledger_lock_io import (
    ERROR_ACCESS_DENIED,
    INVALID_HANDLE_VALUE,
    PROCESS_QUERY_LIMITED_INFORMATION,
    STILL_ACTIVE,
    PIDFileLock,
    _kernel32,
)

__all__ = [
    "ERROR_ACCESS_DENIED",
    "INVALID_HANDLE_VALUE",
    "PIDFileLock",
    "PROCESS_QUERY_LIMITED_INFORMATION",
    "ProgressLedger",
    "STILL_ACTIVE",
    "TaskLedger",
    "_kernel32",
]


class TaskLedger:
    """Gestisce il registro immutabile dei task con catena crittografica SHA-256."""

    def __init__(self, ledger_path: Path | str) -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._nodes: Dict[str, TaskDAGNode] = {}
        self._last_hash = "0" * 64
        self._load_and_verify()

    def _load_and_verify(self) -> None:
        """Carica i nodi dal disco e verifica la catena di integrita."""
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
        """Aggiunge un nuovo task al DAG con reload atomico, verifica e fsync sotto PID lock."""
        lock = PIDFileLock(self.ledger_path.with_suffix(".lock"))
        with lock:
            # Ricarica lo stato da disco dentro il lock per evitare fork prev_hash tra processi.
            self._load_and_verify()

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

            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(node.model_dump_json() + "\n")
                f.flush()
                os.fsync(f.fileno())

            self._nodes[node.task_id] = node
            self._last_hash = node.node_hash
            return node

    def list_tasks(self) -> List[TaskDAGNode]:
        """Restituisce la lista completa dei nodi nel DAG."""
        return list(self._nodes.values())

    def verify_dag(self) -> Tuple[bool, str]:
        """Esegue l'ordinamento topologico di Kahn e rileva eventuali cicli."""
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
        """Restituisce i nodi radice privi di dipendenze in ingresso."""
        return [n for n in self._nodes.values() if not n.parent_ids]

    def get_leaves(self) -> List[TaskDAGNode]:
        """Restituisce i nodi foglia privi di nodi dipendenti."""
        all_parents: Set[str] = set()
        for n in self._nodes.values():
            all_parents.update(n.parent_ids)
        return [n for n in self._nodes.values() if n.task_id not in all_parents]


class ProgressLedger:
    """Gestisce il flusso append-only degli eventi di avanzamento."""

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
        """Registra un nuovo evento in coda al file protetto da lock e fsync."""
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
                f.flush()
                os.fsync(f.fileno())

        return event

    def read_events(self, task_id: Optional[str] = None) -> List[ProgressEvent]:
        """Legge gli eventi registrati e filtra opzionalmente per task."""
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

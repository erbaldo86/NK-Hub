# -*- coding: utf-8 -*-
"""
Architettura Dual Ledgers per Nexus Keystone v3.0.0-STE100-Unified.
Gestisce il DAG immutabile dei task e il registro eventi protetto da PID lock.
"""

from __future__ import annotations

import collections
import ctypes
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field, JsonValue


TaskStatus = Literal[
    "PENDING",
    "IN_PROGRESS",
    "BLOCKED",
    "COMPLETED",
    "FAILED",
    "ROLLED_BACK",
]
EventType = Literal[
    "STARTED",
    "CHECKPOINT",
    "HEALING_TRIGGERED",
    "GATE_PASSED",
    "COMPLETED",
    "FAILED",
]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

if os.name == "nt":
    _kernel32 = ctypes.windll.kernel32
    _kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    _kernel32.OpenProcess.restype = ctypes.c_void_p

    _kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    _kernel32.GetExitCodeProcess.restype = ctypes.c_bool

    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_bool

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = ctypes.c_uint32
else:
    _kernel32 = None


def canonical_json_bytes(data: Dict[str, Any]) -> bytes:
    """Genera byte JSON UTF-8 deterministici con chiavi ordinate."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Calcola il digest esadecimale SHA-256 dei byte forniti."""
    return hashlib.sha256(data).hexdigest()


class TaskDAGNode(BaseModel):
    """Nodo immutabile del grafo aciclico diretto dei task."""

    model_config = ConfigDict(strict=True, extra="forbid")

    task_id: str = Field(description="Identificatore univoco del task nel DAG")
    parent_ids: List[str] = Field(
        default_factory=list,
        description="Lista degli ID dei task genitori",
    )
    action: str = Field(description="Verbo dichiarativo dell'azione")
    target_agent: str = Field(description="Agente NK assegnato al task")
    status: TaskStatus = Field(default="PENDING", description="Stato corrente del nodo")
    payload: Dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Configurazione e dati del task",
    )
    created_at: float = Field(
        default_factory=time.time,
        description="Timestamp di creazione del nodo",
    )
    payload_hash: str = Field(description="Hash SHA-256 del payload JSON canonico")
    prev_hash: str = Field(description="Hash SHA-256 della voce precedente nel DAG")
    node_hash: str = Field(description="Hash SHA-256 dell'intero contenuto del nodo")

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
        """Crea un nuovo nodo DAG e calcola gli hash crittografici."""
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
        """Verifica la catena di hash SHA-256 del nodo corrente."""
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
    """Evento sequenziale registrato nel Progress Ledger."""

    model_config = ConfigDict(strict=True, extra="forbid")

    event_id: str = Field(description="Identificatore univoco dell'evento")
    task_id: str = Field(description="Identificatore del task associato")
    step_index: int = Field(ge=0, description="Indice sequenziale dello step")
    event_type: EventType = Field(description="Categoria del ciclo di vita")
    timestamp: float = Field(
        default_factory=time.time,
        description="Timestamp di emissione",
    )
    details: Dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Dettagli e metriche dell'evento",
    )
    pid: int = Field(default_factory=os.getpid, description="PID del processo")


class PIDFileLock:
    """Gestisce un file di lock cooperativo con verifica di vitalita del PID."""

    def __init__(self, lock_file: Path, stale_timeout_sec: float = 30.0) -> None:
        self.lock_file = lock_file
        self.stale_timeout_sec = stale_timeout_sec
        self.acquired = False

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Verifica se il processo associato al PID esiste ed e attivo."""
        if pid <= 0:
            return False
        if os.name == "nt" and _kernel32 is not None:
            handle = _kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid,
            )
            if not handle or handle == INVALID_HANDLE_VALUE:
                err = _kernel32.GetLastError()
                if err == ERROR_ACCESS_DENIED:
                    return True
                return False
            try:
                exit_code = ctypes.c_ulong()
                ok = _kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                if not ok:
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                _kernel32.CloseHandle(handle)
        else:
            try:
                os.kill(pid, 0)
                return True
            except PermissionError:
                return True
            except OSError:
                return False

    def acquire(self, timeout_sec: float = 5.0) -> bool:
        """Acquisisce il file di lock e rimuove eventuali lock orfani."""
        deadline = time.time() + timeout_sec
        current_pid = os.getpid()

        while time.time() < deadline:
            try:
                fd = os.open(
                    str(self.lock_file),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"pid": current_pid, "timestamp": time.time()}, f)
                self.acquired = True
                return True
            except FileExistsError:
                try:
                    content = self.lock_file.read_text(encoding="utf-8")
                    lock_data = json.loads(content)
                    lock_pid = int(lock_data.get("pid", 0))
                    lock_time = float(lock_data.get("timestamp", 0.0))

                    is_stale_time = (time.time() - lock_time) > self.stale_timeout_sec
                    is_dead_pid = not self._is_pid_alive(lock_pid)

                    if is_stale_time or is_dead_pid:
                        try:
                            self.lock_file.unlink()
                        except OSError:
                            pass
                except Exception:
                    pass

                time.sleep(0.02)

        return False

    def release(self) -> None:
        """Rilascia ed elimina il file di lock acquisito."""
        if self.acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except OSError:
                pass
            self.acquired = False

    def __enter__(self) -> PIDFileLock:
        if not self.acquire():
            raise TimeoutError(f"Impossibile acquisire il lock: {self.lock_file}")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


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
        """Aggiunge un nuovo task al DAG sotto protezione PID lock."""
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

        lock = PIDFileLock(self.ledger_path.with_suffix(".lock"))
        with lock:
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(node.model_dump_json() + "\n")

        self._nodes[node.task_id] = node
        self._last_hash = node.node_hash
        return node

    def get_task(self, task_id: str) -> Optional[TaskDAGNode]:
        """Restituisce il nodo associato all'identificatore specificato."""
        return self._nodes.get(task_id)

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
        """Registra un nuovo evento in coda al file protetto da lock."""
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

    def get_latest_event(self, task_id: str) -> Optional[ProgressEvent]:
        """Restituisce l'ultimo evento registrato per il task indicato."""
        events = self.read_events(task_id)
        return events[-1] if events else None

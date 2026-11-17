# -*- coding: utf-8 -*-
"""
Contratti L0 puri per i Dual Ledgers di NK Hub Generation 1.0.0-Generation.
Contiene solo DTO Pydantic v2 strict e funzioni di hashing deterministiche (zero I/O, zero Win32).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Literal, Optional, Sequence
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

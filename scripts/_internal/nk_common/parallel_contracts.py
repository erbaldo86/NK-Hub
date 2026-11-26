# -*- coding: utf-8 -*-
"""Contratti Pydantic v2 strict per lease runtime, budget worker e bonifica scoped."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ParallelLaneLeaseModel(BaseModel):
    """Contratto strict per un singolo lease runtime di lane o chat parallela."""

    model_config = ConfigDict(strict=True, extra="forbid")

    lease_id: str = Field(min_length=3, max_length=64)
    repo_root: str = Field(min_length=1)
    lane_id: str = Field(min_length=1, max_length=64)
    conversation_id: str = ""
    pid: int = Field(gt=0)
    process_create_time_epoch: Optional[float] = None
    ports: List[int] = Field(default_factory=list)
    updated_at: float = Field(gt=0.0)
    ttl_sec: float = Field(ge=5.0)


class WorkerBudgetReceiptModel(BaseModel):
    """Contratto strict per l'allocazione equa di worker pytest su NVMe."""

    model_config = ConfigDict(strict=True, extra="forbid")

    slot_id: str = Field(min_length=3, max_length=64)
    requested: int = Field(ge=1)
    allocated: int = Field(ge=1, le=12)
    active_slots: int = Field(ge=1)
    global_cap: int = Field(ge=2, le=12)


class ScopedCleanupReportModel(BaseModel):
    """Contratto strict per l'esito di bonifica scoped dei server di sviluppo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    status: str = Field(min_length=2)
    workspace_root: str = Field(min_length=1)
    lane_id: Optional[str] = None
    strict_scope: bool = False
    dry_run: bool = False
    target_ports: List[int] = Field(default_factory=list)
    detected_pids: List[int] = Field(default_factory=list)
    skipped_leased_pids: List[int] = Field(default_factory=list)
    terminated_pids: List[int] = Field(default_factory=list)

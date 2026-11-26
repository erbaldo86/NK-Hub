# -*- coding: utf-8 -*-
"""Contratti Pydantic v2 strict per Commit Train, OCC, Re-Gate e Audit Chain."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LaneBaseSnapshotV1(BaseModel):
    """Istantanea base T0 catturata all'avvio di una lane isolata."""

    model_config = ConfigDict(strict=True, extra="forbid")

    lane_id: str = Field(min_length=1, max_length=64)
    repo_hash12: str = Field(min_length=12, max_length=12)
    base_seq: int = Field(ge=0)
    base_head_hash: str = Field(min_length=64, max_length=64)
    captured_at: float = Field(gt=0.0)
    write_set: List[str] = Field(default_factory=list)


class CommitLogEntryV1(BaseModel):
    """Singola voce della catena hash-chained history.jsonl del Commit Train."""

    model_config = ConfigDict(strict=True, extra="forbid")

    seq: int = Field(ge=1)
    repo_hash12: str = ""
    batch_id: str = Field(min_length=3, max_length=128)
    lane_id: str = Field(min_length=1, max_length=64)
    milestone: str = Field(min_length=1, max_length=64)
    timestamp_utc: float = Field(gt=0.0)
    committed_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    staging_manifest_sha256: str = Field(min_length=64, max_length=64)
    chain_anchor_sha256: str = ""
    prev_hash: str = Field(min_length=64, max_length=64)
    record_hash: str = Field(min_length=64, max_length=64)
    hmac_sha256: str = Field(min_length=64, max_length=64)


class CommitTrainHeadV1(BaseModel):
    """Testa corrente autenticata head.json del Commit Train del repository."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["CommitTrainHeadV1"] = "CommitTrainHeadV1"
    repo_hash12: str = Field(min_length=12, max_length=12)
    seq: int = Field(ge=0)
    last_batch_id: str = ""
    last_lane_id: str = ""
    last_record_hash: str = Field(min_length=64, max_length=64)
    updated_at: float = Field(ge=0.0)
    hmac_sha256: str = ""


class CommitTrainQueueItemV1(BaseModel):
    """Elemento FIFO in NVMe per la coda serializzata e Priority Barrier Ticket."""

    model_config = ConfigDict(strict=True, extra="forbid")

    ticket_id: str = Field(min_length=3, max_length=64)
    lane_id: str = Field(min_length=1, max_length=64)
    pid: int = Field(gt=0)
    process_create_time_epoch: Optional[float] = None
    enqueued_at: float = Field(gt=0.0)
    rebase_count: int = Field(default=0, ge=0)
    priority_barrier: bool = False
    staging_manifest_sha256: str = ""


class OCCConflictReportV1(BaseModel):
    """Esito della verifica pre-L1 OCC write-set e drift firme pubbliche AST."""

    model_config = ConfigDict(strict=True, extra="forbid")

    passed: bool
    status: Literal["OK", "OCC_WRITE_CONFLICT", "AST_CONTRACT_DRIFT"]
    base_seq: int = Field(ge=0)
    head_seq: int = Field(ge=0)
    conflicting_files: List[str] = Field(default_factory=list)
    ast_drift_symbols: List[str] = Field(default_factory=list)
    unified_diff: str = ""


class DeltaReGateResultV1(BaseModel):
    """Esito del Delta Re-Gate fuori da L1 su mirror Seqlock coerente a T1."""

    model_config = ConfigDict(strict=True, extra="forbid")

    passed: bool
    status: str = Field(min_length=2)
    validated_seq: int = Field(ge=0)
    seqlock_retries: int = Field(default=0, ge=0)
    ast_passed: bool
    pytest_passed: bool
    ecosystem_passed: bool
    baseline_passed: bool
    violations: List[str] = Field(default_factory=list)


class CommitTrainOutcomeV1(BaseModel):
    """Esito finale dell'orchestrazione Commit Train 2PC per una lane."""

    model_config = ConfigDict(strict=True, extra="forbid")

    passed: bool
    status: str = Field(min_length=2)
    lane_id: str = Field(min_length=1, max_length=64)
    batch_id: str = ""
    committed_seq: int = Field(default=0, ge=0)
    rebase_attempts: int = Field(default=0, ge=0)
    priority_barrier_used: bool = False
    committed_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    message: str = ""

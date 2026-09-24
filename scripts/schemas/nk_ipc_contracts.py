# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.6.0-DualEngine-Symbiosis
IPC Contracts & Pydantic v2 Schemas (Strict Mode)
CRV 4.0 Protocol Compliant
"""

from typing import Literal, Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field


class IPCPointerReturn(BaseModel):
    """
    Compact IPC Pointer Return contract (<80 tokens).
    Passes references to atomic storage payloads instead of large inline objects.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    status: Literal["OK", "ERROR"] = "OK"
    pointer_uri: str
    sha256: str
    crc32: int
    byte_size: int
    mime_type: str = "application/octet-stream"


class OchiaiDiagnosticPayload(BaseModel):
    """
    Ochiai Fault Localization Diagnostic Payload (<80 tokens).
    Calculates suspiciousness ranking for localized software components.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    component_id: str
    ochiai_score: float
    failed_tests: int
    passed_tests: int
    total_failed: int
    rank: int


class TwoPhaseCommitPrepare(BaseModel):
    """
    2PC Phase 1 (Prepare) Contract.
    Captures intent, staging paths, and cryptographic integrity hashes.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    transaction_id: str
    target_path: str
    staging_path: str
    expected_sha256: str
    crc32: int
    timeout_ms: int = 5000
    timestamp_utc: float


class TwoPhaseCommitVerdict(BaseModel):
    """
    2PC Phase 2 (Commit/Abort) Verdict Contract.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    transaction_id: str
    verdict: Literal["COMMIT", "ABORT"]
    reason: Optional[str] = None
    committed_path: Optional[str] = None
    execution_time_ms: float = 0.0


class GateEvaluationResult(BaseModel):
    """
    Evaluation verdict from Quality/Security Gates.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    gate_name: str
    passed: bool
    score: float
    threshold: float
    violations: List[str] = Field(default_factory=list)
    timestamp_utc: float


class DASTSandboxReport(BaseModel):
    """
    Dynamic Application Security Testing (DAST) Sandbox Execution Report.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sandbox_id: str
    target: str
    exit_code: int
    violations: List[str] = Field(default_factory=list)
    memory_peak_mb: float = 0.0
    duration_ms: float = 0.0
    clean_exit: bool = True


class RRFSearchQuery(BaseModel):
    """
    Reciprocal Rank Fusion (RRF) Hybrid Search Query Contract.
    Combines vector and BM25 search rank scores.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    query_text: str
    k_constant: int = 60
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    top_k: int = 10


class MicroUIHUDState(BaseModel):
    """
    Real-time State for Micro-UI / Status HUD.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    session_id: str
    hud_status: Literal["IDLE", "RUNNING", "BLOCKED", "ERROR", "COMMITTED"]
    active_task: str
    progress_pct: float = 0.0
    metrics: Dict[str, float] = Field(default_factory=dict)
    updated_at: float


class RootCauseAnalysis(BaseModel):
    """
    RCA metadata for unattended execution blocks (C3 Protocol).
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    blocked_resource_type: str
    resource_identifier: str
    error_message: str
    stack_trace_snippet: Optional[str] = None
    zero_mock_violation_prevented: bool = True


class StagingSnapshot(BaseModel):
    """
    Snapshot of modified staged files prior to unattended block/failure.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    staging_path: str
    modified_files: List[str] = Field(default_factory=list)
    sha256_tree_hash: str


class GoalFailureManifest(BaseModel):
    """
    Goal Execution Failure Manifest (C3 Unattended Failure Protocol).
    Emitted when an unattended /goal execution is blocked by unavailable external resources,
    strictly preventing the generation of fake mocks.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Optional[str] = Field(
        default="https://json-schema.org/draft/2020-12/schema",
        alias="$schema",
    )
    manifest_version: str = "1.0.0"
    timestamp: float
    session_id: str
    milestone_anchor_id: str
    status: Literal["UNATTENDED_BLOCKED", "FAILED", "CIRCUIT_BREAKER_TRIPPED"] = "UNATTENDED_BLOCKED"
    root_cause_analysis: RootCauseAnalysis
    staging_snapshot: StagingSnapshot
    user_remediation_steps: List[str] = Field(default_factory=list)
    resume_command: str = "/goal --resume"

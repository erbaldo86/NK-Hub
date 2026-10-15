# -*- coding: utf-8 -*-
"""
Contratti IPC e schemi Pydantic v2 per Nexus Keystone v3.0.0-STE100-Unified.
Tutti i modelli applicano la validazione rigorosa e vietano campi extra.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class IPCPointerReturn(BaseModel):
    """Contratto compatto di ritorno per puntatori IPC sotto 80 token."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    status: Literal["OK", "ERROR"] = "OK"
    pointer_uri: str
    sha256: str
    crc32: int
    byte_size: int
    mime_type: str = "application/octet-stream"


class OchiaiDiagnosticPayload(BaseModel):
    """Contratto diagnostico Ochiai per la localizzazione dei guasti sotto 80 token."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    component_id: str
    ochiai_score: float
    failed_tests: int
    passed_tests: int
    total_failed: int
    rank: int


class TwoPhaseCommitPrepare(BaseModel):
    """Contratto della Fase 1 (Prepare) per il motore transazionale 2PC."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    transaction_id: str
    target_path: str
    staging_path: str
    expected_sha256: str
    crc32: int
    timeout_ms: int = 5000
    timestamp_utc: float


class TwoPhaseCommitVerdict(BaseModel):
    """Contratto della Fase 2 (Commit o Abort) per il motore transazionale 2PC."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    transaction_id: str
    verdict: Literal["COMMIT", "ABORT"]
    reason: Optional[str] = None
    committed_path: Optional[str] = None
    execution_time_ms: float = 0.0


class GateEvaluationResult(BaseModel):
    """Verdetto di valutazione emesso dai gate di sicurezza e qualita."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    gate_name: str
    passed: bool
    score: float
    threshold: float
    violations: List[str] = Field(default_factory=list)
    timestamp_utc: float


class DASTSandboxReport(BaseModel):
    """Rapporto di esecuzione dinamica generato dalla sandbox DAST."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sandbox_id: str
    target: str
    exit_code: int
    violations: List[str] = Field(default_factory=list)
    memory_peak_mb: float = 0.0
    duration_ms: float = 0.0
    clean_exit: bool = True


class RRFSearchQuery(BaseModel):
    """Contratto di ricerca ibrida basato su Reciprocal Rank Fusion."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    query_text: str
    k_constant: int = 60
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    top_k: int = 10


class MicroUIHUDState(BaseModel):
    """Stato in tempo reale per il renderer telemetrico Micro-HUD."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    session_id: str
    hud_status: Literal["IDLE", "RUNNING", "BLOCKED", "ERROR", "COMMITTED"]
    active_task: str
    progress_pct: float = 0.0
    metrics: Dict[str, float] = Field(default_factory=dict)
    updated_at: float


class RootCauseAnalysis(BaseModel):
    """Metadati RCA per blocchi di esecuzione non presidiata (Protocollo C3)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    blocked_resource_type: str
    resource_identifier: str
    error_message: str
    stack_trace_snippet: Optional[str] = None
    zero_mock_violation_prevented: bool = True


class StagingSnapshot(BaseModel):
    """Snapshot dei file modificati in staging prima di un blocco operativo."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    staging_path: str
    modified_files: List[str] = Field(default_factory=list)
    sha256_tree_hash: str


class GoalFailureManifest(BaseModel):
    """Manifesto di fallimento emesso quando una risorsa esterna blocca il task."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    schema_version: Optional[str] = Field(
        default="https://json-schema.org/draft/2020-12/schema",
        alias="$schema",
    )
    manifest_version: str = "1.0.0"
    timestamp: float
    session_id: str
    milestone_anchor_id: str
    status: Literal[
        "UNATTENDED_BLOCKED",
        "FAILED",
        "CIRCUIT_BREAKER_TRIPPED",
    ] = "UNATTENDED_BLOCKED"
    root_cause_analysis: RootCauseAnalysis
    staging_snapshot: StagingSnapshot
    user_remediation_steps: List[str] = Field(default_factory=list)
    resume_command: str = "/goal --resume"


try:
    from rsi_convergence_engine import (
        RSIDefectVector,
        RSIIterationRecord,
        RSISessionReport,
    )
except Exception:
    try:
        from scripts.rsi_convergence_engine import (
            RSIDefectVector,
            RSIIterationRecord,
            RSISessionReport,
        )
    except Exception:

        class RSIDefectVector(BaseModel):
            """Vettore dei difetti rilevati in una singola iterazione del motore RSI."""

            model_config = ConfigDict(strict=True, extra="forbid")

            sast: int = Field(default=0, ge=0)
            t_fail: int = Field(default=0, ge=0)
            c_violations: int = Field(default=0, ge=0)
            h_violations: int = Field(default=0, ge=0)
            m_gaps: int = Field(default=0, ge=0)
            l_warnings: int = Field(default=0, ge=0)
            g_drift: int = Field(default=0, ge=0)
            t_pass: int = Field(default=0, ge=0)
            t_total: int = Field(default=1, ge=1)

        class RSIIterationRecord(BaseModel):
            """Singolo record crittografico di iterazione per il ledger RSI."""

            model_config = ConfigDict(strict=True, extra="forbid")

            iteration: int = Field(ge=0)
            delta_k: float = Field(ge=0.0)
            fitness_q: float = Field(ge=0.0, le=100.0)
            status: str
            state_hash: str
            prev_hash: str = "0" * 64
            record_hash: str = ""
            timestamp_utc: float = 0.0

        class RSISessionReport(BaseModel):
            """Rapporto finale di convergenza prodotto dal motore RSI."""

            model_config = ConfigDict(strict=True, extra="forbid")

            session_id: str
            mode: Literal["mode_a", "mode_b", "mode_c", "verify"] = "mode_a"
            converged: bool
            final_status: str
            iterations_used: int = Field(ge=0)
            final_delta: float = Field(ge=0.0)
            final_fitness_q: float = Field(ge=0.0, le=100.0)
            records: List[RSIIterationRecord] = Field(default_factory=list)


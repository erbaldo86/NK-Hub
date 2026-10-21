# -*- coding: utf-8 -*-
"""
Contratti IPC e schemi Pydantic v2 per Nexus Keystone v3.2.0-STE100-Unified.
Tutti i modelli applicano la validazione rigorosa e supportano Mode A/B/C/D (OPT-11b).
"""

import time
from typing import Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


ExecutionModeLiteral = Literal["mode_a", "mode_b", "mode_c", "mode_d", "verify"]
MetaPromptFSMStateLiteral = Literal[
    "IDLE",
    "REFINE",
    "AWAIT_CONFIRM",
    "CONFIRMED",
    "BYPASSED",
]
MetaPromptGateModeLiteral = Literal["CONFIRM", "ECHO", "OFF"]


class MetaPromptGateContract(BaseModel):
    """Contratto IPC per il Livello 0 del Super Meta-Prompt Gate (WP13)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    brief_id: str = "IB-DEFAULT"
    fsm_state: MetaPromptFSMStateLiteral = "REFINE"
    gate_mode: MetaPromptGateModeLiteral = "CONFIRM"
    enabled: bool = True
    bypassed: bool = False
    conceptual_mirror: str
    optimized_meta_prompt: str
    requirements_r_ids: List[str] = Field(default_factory=list)
    voice_corrections_applied: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)
    recommended_mode: ExecutionModeLiteral = "mode_c"
    primary_agent: str = "NK-Python-Async-Builder"
    native_subagent: str = "NK-Builder-Agent"
    intent_hash_sha256: str = ""
    ttl_seconds: int = Field(default=1800, ge=60)


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


class RoutingIntentContract(BaseModel):
    """Contratto di classificazione del routing per Mode A, B, C e D (OPT-11b)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    recommended_mode: Literal["mode_a", "mode_b", "mode_c", "mode_d", "verify"] = (
        "mode_c"
    )
    is_discovery: bool = False
    read_only: bool = False
    primary_agent: str = "NK-Python-Async-Builder"


try:
    from rsi_convergence_engine import (
        RSIDefectVector,
        RSIIterationRecord,
    )
except Exception:
    try:
        from scripts.rsi_convergence_engine import (
            RSIDefectVector,
            RSIIterationRecord,
        )
    except Exception:

        class RSIDefectVector(BaseModel):
            """Vettore dei difetti allineato a rsi_convergence_engine (OPT-11b)."""

            model_config = ConfigDict(strict=True, extra="forbid")

            sast_critical: int = Field(default=0, ge=0)
            tests_failed: int = Field(default=0, ge=0)
            tests_passed: int = Field(default=100, ge=0)
            tests_total: int = Field(default=0, ge=0)
            contract_violations: int = Field(default=0, ge=0)
            high_findings: int = Field(default=0, ge=0)
            medium_findings: int = Field(default=0, ge=0)
            low_findings: int = Field(default=0, ge=0)
            doc_drift: int = Field(default=0, ge=0)
            poc_confirmed_exploits: int = Field(default=0, ge=0)
            semantic_drift_findings: int = Field(default=0, ge=0)

            def effective_totals(self) -> Tuple[int, int]:
                """Restituisce la coppia (tests_passed, tests_total) normalizzata."""
                if self.tests_total > 0:
                    return self.tests_passed, self.tests_total
                computed_total = self.tests_passed + self.tests_failed
                if computed_total > 0:
                    return self.tests_passed, computed_total
                return 100, 100

        class RSIIterationRecord(BaseModel):
            """Singolo record crittografico di iterazione per il ledger RSI (OPT-11b)."""

            model_config = ConfigDict(strict=True, extra="forbid")

            session_id: str = "RSI-DEFAULT"
            iteration: int = Field(ge=0)
            mode: Literal["mode_a", "mode_b", "mode_c", "mode_d", "verify"] = "mode_a"
            defects: RSIDefectVector = Field(default_factory=RSIDefectVector)
            delta_k: int = Field(default=0, ge=0)
            fitness_q: float = Field(default=100.0, ge=0.0, le=100.0)
            state_hash: str = ""
            verdict: str = "CONVERGED_OPTIMAL"
            rolled_back: bool = False
            prev_hash: str = "0" * 64
            record_hash: str = ""
            timestamp: float = Field(default_factory=time.time)


class RSISessionReport(BaseModel):
    """Rapporto finale di convergenza RSI con supporto esplicito a mode_d (OPT-11b)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str
    mode: Literal["mode_a", "mode_b", "mode_c", "mode_d", "verify"] = "mode_a"
    max_iterations: int = Field(default=4, ge=1)
    iterations_used: int = Field(default=0, ge=0)
    converged: bool = True
    final_status: str = "CONVERGED_OPTIMAL"
    initial_delta: int = Field(default=0, ge=0)
    final_delta: int = Field(default=0, ge=0)
    initial_fitness_q: float = Field(default=100.0, ge=0.0, le=100.0)
    final_fitness_q: float = Field(default=100.0, ge=0.0, le=100.0)
    rollbacks_count: int = Field(default=0, ge=0)
    cycle_detected: bool = False
    visited_hashes: List[str] = Field(default_factory=list)
    history: List[RSIIterationRecord] = Field(default_factory=list)

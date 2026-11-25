# -*- coding: utf-8 -*-
"""
Contratti IPC e schemi Pydantic v2 per NK Hub Generation 1.0.0-Generation.
Tutti i modelli applicano la validazione rigorosa e supportano Mode A, B, C e D.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACTS_SCHEMA_VERSION: str = "1.0.0-Generation"
ExecutionModeLiteral = Literal["mode_a", "mode_b", "mode_c", "mode_d", "verify"]
MetaPromptFSMStateLiteral = Literal["IDLE", "REFINE", "AWAIT_CONFIRM", "CONFIRMED", "BYPASSED"]
MetaPromptGateModeLiteral = Literal["CONFIRM", "ECHO", "OFF", "BYPASS", "SINGLE_GATE_MODE_D"]


class MetaPromptGateContract(BaseModel):
    """Contratto IPC per il Livello 0 del Meta-Prompt Gate."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    brief_id: str = "IB-DEFAULT"
    fsm_state: MetaPromptFSMStateLiteral = "REFINE"
    gate_mode: MetaPromptGateModeLiteral = "CONFIRM"
    enabled: bool = True
    bypassed: bool = False
    bypass_reason: Optional[str] = Field(default=None, description="Motivo deterministico del bypass L0")
    bypass_scope: Literal["NONE", "L0_GATE_ONLY", "STATE_HANDOFF_STANDBY", "EXECUTE_HANDOFF_SERIALIZE"] = "NONE"
    auto_bypass_eligible: bool = False
    standby_mode: bool = Field(default=False, description="True se il Gate L0 opera in modalita passiva STANDBY")
    conceptual_mirror: str
    optimized_meta_prompt: str
    requirements_r_ids: List[str] = Field(default_factory=list)
    voice_corrections_applied: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)
    recommended_mode: ExecutionModeLiteral = "mode_c"
    primary_agent: str = "NK-Python-Async-Builder"
    native_subagent: str = "NK-Builder-Agent"
    tools_allowed: List[str] = Field(default_factory=list)
    intrinsic_protocols: List[str] = Field(default_factory=list)
    autonomous_slash_equivalence: Dict[str, bool] = Field(default_factory=dict)
    intent_hash_sha256: str = ""
    ttl_seconds: int = Field(default=1800, ge=60)
    classified_track: Optional[Literal["IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC"]] = None
    intent_track: Optional[Literal["IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC"]] = None
    rsi_profile: Optional[str] = None


class IPCPointerReturn(BaseModel):
    """Contratto compatto di ritorno per puntatori IPC sotto 80 token."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    status: Literal["OK", "ERROR"] = "OK"
    pointer_uri: str
    sha256: str
    crc32: int
    byte_size: int
    mime_type: str = "application/octet-stream"


FaultCandidate = Tuple[str, float]


class OchiaiDiagnosticPayload(BaseModel):
    """Payload diagnostico ad alta densita garantito sotto la soglia di 80 token."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", allow_inf_nan=False)

    top_fault: str = Field(description="Identificativo dell'istruzione con massima sospettosita Ochiai")
    ochiai_score: float = Field(ge=0.0, le=1.0)
    spectrum_tuple: Tuple[int, int, int, int] = Field(description="(n_ef, n_ep, n_nf, n_np)")
    top_candidates: List[FaultCandidate] = Field(description="Lista di (statement, score)", max_length=5)
    flaky_filtered_count: int = Field(ge=0, default=0)

    @field_validator("spectrum_tuple", mode="before")
    @classmethod
    def _coerce_spectrum_tuple(cls, val: Any) -> Any:
        """Converte list JSON in tuple preservando la validazione strict sugli elementi."""
        return tuple(val) if isinstance(val, list) else val

    @field_validator("top_candidates", mode="before")
    @classmethod
    def _coerce_top_candidates(cls, val: Any) -> Any:
        """Converte coppie list JSON in tuple preservando la validazione strict sugli elementi."""
        if not isinstance(val, list):
            return val
        return [tuple(item) if isinstance(item, list) else item for item in val]

    def to_compact_json(self) -> str:
        """Restituisce la rappresentazione JSON compatta escapata (< 80 token)."""
        payload_dict: Dict[str, Any] = {
            "flt": self.top_fault,
            "och": round(self.ochiai_score, 4),
            "spec": list(self.spectrum_tuple[:4]),
            "top": [[stmt, round(score, 4)] for stmt, score in self.top_candidates],
            "flk": self.flaky_filtered_count,
        }
        return json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False)

    def estimate_token_count(self) -> int:
        """Stima il conteggio dei token sulla base della lunghezza in caratteri."""
        return math.ceil(len(self.to_compact_json()) / 3.2)


class TwoPhaseCommitPrepare(BaseModel):
    """Contratto della Fase 1 (Prepare) per il motore transazionale 2PC."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    transaction_id: str
    target_path: str
    staging_path: str
    expected_sha256: str
    crc32: int
    timeout_ms: int = 5000
    timestamp_utc: float


class TwoPhaseCommitVerdict(BaseModel):
    """Contratto della Fase 2 (Commit o Abort) per il motore transazionale 2PC."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    transaction_id: str
    verdict: Literal["COMMIT", "ABORT"]
    reason: Optional[str] = None
    committed_path: Optional[str] = None
    execution_time_ms: float = 0.0


class MicroUIHUDState(BaseModel):
    """Stato in tempo reale per il renderer telemetrico Micro-HUD."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    session_id: str
    hud_status: Literal["IDLE", "RUNNING", "BLOCKED", "ERROR", "COMMITTED"]
    active_task: str
    progress_pct: float = 0.0
    metrics: Dict[str, float] = Field(default_factory=dict)
    updated_at: float


class RootCauseAnalysis(BaseModel):
    """Metadati RCA per blocchi di esecuzione non presidiata."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    blocked_resource_type: str
    resource_identifier: str
    error_message: str
    stack_trace_snippet: Optional[str] = None
    zero_mock_violation_prevented: bool = True


class StagingSnapshot(BaseModel):
    """Snapshot dei file modificati in staging prima di un blocco operativo."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    staging_path: str
    modified_files: List[str] = Field(default_factory=list)
    sha256_tree_hash: str


class GoalFailureManifest(BaseModel):
    """Manifesto di fallimento emesso quando una risorsa esterna blocca il task."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, populate_by_name=True, allow_inf_nan=False)

    schema_version: Optional[str] = Field(default="https://json-schema.org/draft/2020-12/schema", alias="$schema")
    manifest_version: str = CONTRACTS_SCHEMA_VERSION
    timestamp: float
    session_id: str
    milestone_anchor_id: str
    status: Literal["UNATTENDED_BLOCKED", "FAILED", "CIRCUIT_BREAKER_TRIPPED"] = "UNATTENDED_BLOCKED"
    root_cause_analysis: RootCauseAnalysis
    staging_snapshot: StagingSnapshot
    user_remediation_steps: List[str] = Field(default_factory=list)
    resume_command: str = "/goal --resume"


class RoutingIntentContract(BaseModel):
    """Contratto di classificazione del routing per Mode A, B, C e D."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    recommended_mode: Literal["mode_a", "mode_b", "mode_c", "mode_d", "verify"] = "mode_c"
    is_discovery: bool = False
    read_only: bool = False
    primary_agent: str = "NK-Python-Async-Builder"
    classified_track: Optional[Literal["IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC"]] = None
    intent_track: Optional[Literal["IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC"]] = None
    rsi_profile: Optional[str] = None


class RSIDefectVector(BaseModel):
    """Vettore dei difetti allineato a rsi_convergence_engine."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    sast_critical: int = Field(default=0, ge=0)
    tests_failed: int = Field(default=0, ge=0)
    tests_passed: int = Field(default=0, ge=0)
    tests_total: int = Field(default=0, ge=0)
    contract_violations: int = Field(default=0, ge=0)
    high_findings: int = Field(default=0, ge=0)
    medium_findings: int = Field(default=0, ge=0)
    low_findings: int = Field(default=0, ge=0)
    doc_drift: int = Field(default=0, ge=0)
    poc_confirmed_exploits: int = Field(default=0, ge=0)
    semantic_drift_findings: int = Field(default=0, ge=0)
    hallucinated_refs: int = Field(default=0, ge=0)
    deception_gaming_count: int = Field(default=0, ge=0)
    measured_components: List[str] = Field(default_factory=list)
    unmeasured_components: List[str] = Field(default_factory=list)

    def effective_totals(self) -> Tuple[int, int]:
        """Restituisce la coppia (tests_passed, tests_total) normalizzata senza default sintetici."""
        if self.tests_total > 0:
            return self.tests_passed, self.tests_total
        computed_total = self.tests_passed + self.tests_failed
        if computed_total > 0:
            return self.tests_passed, computed_total
        return 0, 0


class RSIIterationRecord(BaseModel):
    """Singolo record crittografico di iterazione per il ledger RSI."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    session_id: str = "RSI-DEFAULT"
    iteration: int = Field(ge=0)
    mode: str = "mode_a"
    defects: RSIDefectVector = Field(default_factory=RSIDefectVector)
    delta_k: int = Field(default=0, ge=0)
    fitness_q: float = Field(default=100.0, ge=0.0, le=100.0)
    q_v2: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    g_hard: Optional[int] = Field(default=None, ge=0, le=1)
    delta_hard: Optional[int] = Field(default=None, ge=0)
    certification_tier: Optional[str] = None
    state_hash: str = ""
    verdict: str = "CONVERGED_OPTIMAL"
    rolled_back: bool = False
    prev_hash: str = "0" * 64
    record_hash: str = ""
    timestamp: float = Field(default_factory=time.time)

    @field_validator("defects", mode="before")
    @classmethod
    def _validate_defects(cls, val: Any) -> Any:
        if isinstance(val, RSIDefectVector):
            return val
        if isinstance(val, dict):
            return RSIDefectVector(**val)
        if hasattr(val, "model_dump") and type(val).__name__ == "RSIDefectVector":
            return RSIDefectVector(**val.model_dump())
        return val

    def to_hash_payload(self) -> Dict[str, Any]:
        """Restituisce il dizionario canonico escludendo i campi opzionali None per l'hash chain."""
        return self.model_dump(exclude_none=True)


class RSISessionReport(BaseModel):
    """Rapporto finale di convergenza RSI con supporto esplicito a mode_d."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    session_id: str
    mode: str = "mode_a"
    max_iterations: int = Field(default=4, ge=0)
    iterations_used: int = Field(default=0, ge=0)
    converged: bool = True
    final_status: str = "CONVERGED_OPTIMAL"
    initial_delta: int = Field(default=0, ge=0)
    final_delta: int = Field(default=0, ge=0)
    initial_fitness_q: float = Field(default=100.0, ge=0.0, le=100.0)
    final_fitness_q: float = Field(default=100.0, ge=0.0, le=100.0)
    final_q_v2: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    final_g_hard: Optional[int] = Field(default=None, ge=0, le=1)
    rollbacks_count: int = Field(default=0, ge=0)
    cycle_detected: bool = False
    visited_hashes: List[str] = Field(default_factory=list)
    history: List[RSIIterationRecord] = Field(default_factory=list)

    @field_validator("history", mode="before")
    @classmethod
    def _validate_history(cls, val: Any) -> Any:
        if not isinstance(val, list):
            return val
        coerced: List[Any] = []
        for item in val:
            if isinstance(item, RSIIterationRecord):
                coerced.append(item)
            elif isinstance(item, dict):
                coerced.append(RSIIterationRecord(**item))
            elif hasattr(item, "model_dump") and type(item).__name__ == "RSIIterationRecord":
                coerced.append(RSIIterationRecord(**item.model_dump()))
            else:
                coerced.append(item)
        return coerced


if not __package__:
    _hc_dir = str(Path(__file__).resolve().parent)
    if _hc_dir not in sys.path:
        sys.path.insert(0, _hc_dir)
    from handoff_contracts import (  # type: ignore[import-not-found,no-redef]
        ActiveContinuationPayloadV2, HandoffPayloadV2, ManifestCriticStateV1,
        ManifestPentadPathsV1, ManifestRSIStateV1, ManifestTopologyV1,
        NKHandoffEnvelopeV2, NKHandoffManifestV1, PassiveStandbyPayloadV2,
        PatchNotesHeadV2, RepoSnapshotV2, RequirementClauseV2, Sha256Hex,
        StagingEntryV2, StagingFileDiffV2, StrictCfg, StrictTuple,
        compute_envelope_sha256, verify_envelope_v2_dict,
    )
else:
    from .handoff_contracts import (
        ActiveContinuationPayloadV2, HandoffPayloadV2, ManifestCriticStateV1,
        ManifestPentadPathsV1, ManifestRSIStateV1, ManifestTopologyV1,
        NKHandoffEnvelopeV2, NKHandoffManifestV1, PassiveStandbyPayloadV2,
        PatchNotesHeadV2, RepoSnapshotV2, RequirementClauseV2, Sha256Hex,
        StagingEntryV2, StagingFileDiffV2, StrictCfg, StrictTuple,
        compute_envelope_sha256, verify_envelope_v2_dict,
    )

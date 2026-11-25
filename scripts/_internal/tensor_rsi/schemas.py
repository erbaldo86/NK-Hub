# -*- coding: utf-8 -*-
"""Contratti L0 Pydantic v2 strict per Tensor-RSI Control Plane (DOM-01)."""

from __future__ import annotations

from typing import Annotated, Any, Dict, Literal, Optional, Tuple, TypeVar
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

StrictFrozenCfg = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)
def _to_tuple(v: Any) -> Any:
    return tuple(v) if isinstance(v, list) else v


T = TypeVar("T")
StrictTuple = Annotated[Tuple[T, ...], BeforeValidator(_to_tuple)]
Delta4Tuple = Annotated[Tuple[float, float, float, float], BeforeValidator(_to_tuple)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegInt = Annotated[int, Field(ge=0)]
BinInt = Annotated[int, Field(ge=0, le=1)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]

IntentTrackLiteral = Literal["CODE_TRACK", "DOC_TRACK"]
ClassifiedTrackLiteral = Literal["IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC"]
IntentCategoryLiteral = Literal["CODE_BUILD", "MICRO_VIBE", "SPEC_DOC", "AUDIT_RO"]
ModelTierLiteral = Literal["NEON", "CARBON_GEN", "PRO", "FLASH", "STANDARD"]
ACSZoneLiteral = Literal["Z0", "Z1", "Z2", "Z3"]
PhaseLiteral = Literal["NONE", "INTAKE", "DIAGNOSE", "PROPOSE", "EVALUATE", "DECIDE", "RECORDED", "ABORTED"]
StepLiteral = Literal["intake", "diagnose", "propose", "evaluate", "decide", "record", "status", "abort"]
MacroOperatorLiteral = Literal["SURGICAL_LOCAL_PATCH", "DECOMPOSITION_HELPER_EXTRACT", "TEST_ORACLE_HARDENING", "ISOLATED_SUBAGENT_SLICE", "OP_DOC_ALIGN"]
StatisticalRegimeLiteral = Literal["COLD", "WARM_BANDIT", "CALIBRATED_VOI"]
PytestModeLiteral = Literal["FULL_ISOLATED_COV", "FAST_MARK_ISOLATED", "TARGETED_SLICE", "SKIP_READONLY"]
DecisionVerdictLiteral = Literal[
    "ACCEPT_TIER1_DOMINANT", "ACCEPT_PARETO_STRICT", "ACCEPT_EPSILON_DIRECTIONAL", "CONVERGED_OPTIMAL",
    "REJECT_TIER0_HARD_GATE", "REJECT_TIER1_REGRESSION", "REJECT_TIER2_EPSILON_BAND",
    "REJECT_TIER2_NO_GAIN", "HALT_EPISTEMIC_CONFLICT", "HALT_VOI_EXHAUSTED", "HALT_CONTEXT_BUDGET",
]
GateNameLiteral = Literal[
    "NONE", "GATE_1_SCOPE", "GATE_2_CODE_GROUNDING", "GATE_3_BRIEF_GROUNDING",
    "GATE_4_PRESERVATION", "GATE_5_TRUTH_DAST", "GATE_6_RSI_CONVERGENCE", "ALL_PASSED",
]
REJECT_DECISION_VERDICTS = frozenset({"REJECT_TIER0_HARD_GATE", "REJECT_TIER1_REGRESSION", "REJECT_TIER2_EPSILON_BAND", "REJECT_TIER2_NO_GAIN"})
ACCEPT_DECISION_VERDICTS = frozenset({"ACCEPT_TIER1_DOMINANT", "ACCEPT_PARETO_STRICT", "ACCEPT_EPSILON_DIRECTIONAL", "CONVERGED_OPTIMAL"})
ALLOWED_TRANSITIONS: Dict[Tuple[str, str], PhaseLiteral] = {
    ("NONE", "intake"): "INTAKE", ("INTAKE", "diagnose"): "DIAGNOSE", ("DIAGNOSE", "propose"): "PROPOSE",
    ("PROPOSE", "evaluate"): "EVALUATE", ("EVALUATE", "decide"): "DECIDE", ("DECIDE", "diagnose"): "DIAGNOSE", ("DECIDE", "record"): "RECORDED",
}

class _StrictBase(BaseModel):
    """Base Pydantic v2 strict immutable comune ai contratti Tensor-RSI."""
    model_config = StrictFrozenCfg

class HypothesisCard(_StrictBase):
    """Singola ipotesi falsificabile ancorata a file:line nel Turno 2 (DIAGNOSE)."""
    hypothesis_id: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=320)
    target_ref: str = Field(min_length=1, max_length=240)
    falsification_test: str = Field(min_length=1, max_length=240)

class RSIReasoningFrame(_StrictBase):
    """Frame di diagnosi strutturato con almeno 2 ipotesi falsificabili."""
    defect_ids: StrictTuple[str] = ()
    hypotheses: StrictTuple[HypothesisCard] = Field(min_length=2)
    scope_files: StrictTuple[str] = ()

class PolicyCell(_StrictBase):
    """Cella deterministica del Tensore Policy(Intent, ModelTier, ACSZone)."""
    intent: IntentCategoryLiteral
    intent_track: IntentTrackLiteral
    classified_track: ClassifiedTrackLiteral = "IMPROVEMENT"
    model_tier: ModelTierLiteral
    acs_zone: ACSZoneLiteral
    max_rsi_iterations: int = Field(ge=0, le=4)
    max_in_context_branches: int = Field(ge=0, le=3)
    delegate_subagent_slices: bool
    subagent_slice_token_cap: int = Field(ge=128, le=1200)
    max_subagent_fanout: int = Field(ge=0, le=3)
    pytest_mode: PytestModeLiteral
    recommend_compact: bool = False
    halt_for_handoff: bool = False
    policy_cell_hash: Sha256Hex

    @model_validator(mode="after")
    def _check_invariants(self) -> PolicyCell:
        if self.acs_zone == "Z3" and (self.max_in_context_branches != 0 or not self.halt_for_handoff):
            raise ValueError("Z3 requires max_in_context_branches=0 and halt_for_handoff=True.")
        return self

class PrimaryInvariantVector(_StrictBase):
    """Invarianti primari Tier 1 con ratchet stretto epsilon=0."""
    p_pass: UnitFloat
    k_mut: UnitFloat = 0.0
    c_branch: UnitFloat = 0.0
    critical_count: NonNegInt = 0
    high_count: NonNegInt = 0
    doc_drift_count: NonNegInt = 0
    semantic_drift_count: NonNegInt = 0

class SecondaryQualityVector(_StrictBase):
    """Vettore secondario Tier 2 normalizzato in [0, 1]^4 (higher-is-better)."""
    v_sec_hyg: UnitFloat
    v_qual: UnitFloat
    v_eff: UnitFloat
    v_ste100: UnitFloat

class MetricSnapshot(_StrictBase):
    """Istantanea strutturata estratta in sola lettura dall'Oracolo DOM-04."""
    intent_track: IntentTrackLiteral
    g_hard: BinInt
    failed_hard_gates: StrictTuple[str] = ()
    epistemic_conflict: bool = False
    gaming_penalty: int = Field(default=0, le=0)
    q_v2: float = Field(ge=0.0, le=100.0)
    delta_k: NonNegInt = 0
    certification_tier: Literal["CERTIFIED_PASS", "STATIC_PASS", "UNMEASURED", "FAIL"]
    state_hash: Sha256Hex
    primary: PrimaryInvariantVector
    secondary: SecondaryQualityVector
    tests_total: NonNegInt = 0
    failed_tests: NonNegInt = 0
    tests_skipped: NonNegInt = 0
    xfailed: NonNegInt = 0
    deselected: NonNegInt = 0
    s_taint: NonNegInt = 0
    sast_critical: NonNegInt = 0
    dast_passed: BinInt = 1
    poc_confirmed_exploits: NonNegInt = 0
    deception_gaming_count: NonNegInt = 0
    mock_count: NonNegInt = 0
    f_holdout: NonNegInt = 0
    scope_creep: NonNegInt = 0
    contract_violations: NonNegInt = 0
    hallucinated_refs: NonNegInt = 0
    dry_run: BinInt = 0
    broken_links: NonNegInt = 0
    phantom_scripts: NonNegInt = 0
    invalid_json: NonNegInt = 0
    mojibake: NonNegInt = 0
    gt14_governance_ok: BinInt = 1
    twin_parity_ok: BinInt = 1
    assert_count: NonNegInt = 0
    doc_link_count: NonNegInt = 0
    skill_count: NonNegInt = 0
    unmeasured_reasons: StrictTuple[str] = ()
    flaky_nodeids: StrictTuple[str] = ()

class ParetoDecisionResult(_StrictBase):
    """Verdetto del Gate Gerarchico Tier 0 -> Tier 1 -> Tier 2."""
    verdict: DecisionVerdictLiteral
    accepted: bool
    tier_stopped_at: Literal[0, 1, 2]
    directional_projection: float
    min_effect: float = Field(ge=0.0)
    delta_secondary: Delta4Tuple
    band_violations: StrictTuple[str] = ()
    primary_regressions: StrictTuple[str] = ()
    rationale: str = Field(min_length=1, max_length=240)

class ColdWarmDecision(_StrictBase):
    """Output del Gate Statistico Progressivo (COLD / WARM_BANDIT / CALIBRATED_VOI)."""
    regime: StatisticalRegimeLiteral
    n_samples: NonNegInt
    selected_operator: MacroOperatorLiteral
    allowed_operators: StrictTuple[MacroOperatorLiteral] = Field(min_length=1)
    predicted_accept_prob: UnitFloat
    wilson_lcb_95: UnitFloat
    lcb_90_stochastic: UnitFloat = 0.0
    ucb_score: float = Field(ge=0.0)
    thompson_seed_digest: Optional[str] = None
    brier_score: Optional[UnitFloat] = None
    mae_score: Optional[UnitFloat] = None
    calibration_degraded: bool = False
    voi_ratio: Optional[float] = Field(default=None, ge=0.0)
    voi_should_stop: bool = False

class GateStatusSummary(_StrictBase):
    """Mappa deterministica GATE_1_SCOPE..GATE_6_RSI_CONVERGENCE."""
    last_cold_review_gate: GateNameLiteral
    passed_gates: StrictTuple[str] = ()
    failed_gates: StrictTuple[str] = ()
    gate_details: Dict[str, bool] = Field(default_factory=dict)

class TensorRSIStateTicket(_StrictBase):
    """Payload autenticato HMAC-SHA256 trasportato nel token compatto trsi1."""
    version: Literal["trsi1"] = "trsi1"
    session_id: str = Field(min_length=6, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    step_seq: int = Field(ge=1)
    iteration: int = Field(ge=0, le=4)
    phase: PhaseLiteral
    intent_track: IntentTrackLiteral
    classified_track: ClassifiedTrackLiteral = "IMPROVEMENT"
    policy_cell_hash: Sha256Hex
    baseline_state_sha256: Sha256Hex
    hypothesis_hash_sha256: Sha256Hex = "0" * 64
    selected_operator: Optional[MacroOperatorLiteral] = None
    predicted_accept_prob: Optional[UnitFloat] = None
    thompson_seed_digest: Optional[str] = None
    last_verdict: Optional[DecisionVerdictLiteral] = None
    staging_manifest_sha256: Optional[Sha256Hex] = None
    prev_ticket_sha256: Sha256Hex
    issued_at: int = Field(ge=1)
    ttl_seconds: int = Field(default=1800, ge=60, le=7200)
    nonce_hex: str = Field(min_length=16, max_length=64)

class TensorRSIStepOutput(_StrictBase):
    """Contratto di risposta JSON emesso da scripts/tensor_rsi.py."""
    status: Literal["OK", "HALT", "REJECT", "CONVERGED_OPTIMAL", "ERROR"]
    step: StepLiteral
    phase: PhaseLiteral
    session_id: str
    step_seq: NonNegInt
    iteration: int = Field(ge=0, le=4)
    ticket: Optional[str] = None
    policy_cell: PolicyCell
    cold_warm: Optional[ColdWarmDecision] = None
    pareto_decision: Optional[ParetoDecisionResult] = None
    gate_status: Optional[GateStatusSummary] = None
    summary: str = Field(min_length=1, max_length=320)

class TensorRSILedgerEntry(_StrictBase):
    """Voce append-only concatenata SHA-256 in nk_tracking/tensor_rsi_ledger.jsonl."""
    session_id: str
    clade_id: str
    iteration: NonNegInt
    intent_track: IntentTrackLiteral
    classified_track: ClassifiedTrackLiteral = "IMPROVEMENT"
    model_tier: ModelTierLiteral
    acs_zone: ACSZoneLiteral
    operator: MacroOperatorLiteral
    regime: StatisticalRegimeLiteral
    predicted_accept_prob: UnitFloat
    accepted: bool
    reward: UnitFloat
    directional_projection: float
    q_v2_before: float = Field(ge=0.0, le=100.0)
    q_v2_after: float = Field(ge=0.0, le=100.0)
    dry_run: BinInt = 0
    deception_gaming_count: NonNegInt = 0
    baseline_state_sha256: Sha256Hex
    candidate_state_sha256: Sha256Hex
    prev_hash: Sha256Hex
    record_hash: Sha256Hex
    timestamp_utc: float = Field(ge=0.0)

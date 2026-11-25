# -*- coding: utf-8 -*-
"""
Contratti Pydantic v2 strict (L0) per NKHandoffEngine v2 (1.1.1-Handoff-V2).
@domain_id: DOM-05
ZERO import da _internal/; allineato 1:1 a handoff_anchor_schema.md e session_handoff_latest.json.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated, Any, Dict, Literal, Mapping, Optional, Tuple, TypeVar, Union
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

StrictCfg = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


def _coerce_list_to_tuple(val: Any) -> Any:
    """Converte list JSON in tuple preservando il rifiuto strict su altri tipi."""
    if isinstance(val, list):
        return tuple(val)
    return val


T = TypeVar("T")
StrictTuple = Annotated[Tuple[T, ...], BeforeValidator(_coerce_list_to_tuple)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ManifestTopologyV1(BaseModel):
    """Topologia operativa nel manifesto handoff v1."""

    model_config = StrictCfg

    pattern: Literal["HUB_AND_SPOKE_2_TIER", "SWARM_PARALLEL", "RATCHET_RSI"]
    critic_role: str = "NK-Orchestrator"
    worker_role: str = "[4] NK-Delta-Architect"


class ManifestPentadPathsV1(BaseModel):
    """Percorsi canonici della Pentad Sovrana nel manifesto handoff v1."""

    model_config = StrictCfg

    concept_map: str = "nk_genome/concept_map.md"
    structural_tree: str = "nk_genome/structural_tree.md"
    implementation_plan: str = "nk_genome/implementation_plan.md"
    repo_map: str = "nk_genome/repo_map.md"
    modules_dir: str = "nk_genome/modules"


class ManifestRSIStateV1(BaseModel):
    """Stato di convergenza RSI nel manifesto handoff v1."""

    model_config = StrictCfg

    iteration: int = Field(ge=0)
    delta_k: Union[int, float] = Field(ge=0)
    fitness_q: float = Field(ge=0.0, le=100.0)
    status: Literal[
        "CONVERGED_OPTIMAL",
        "REFINING",
        "ROLLED_BACK",
        "ABORTED_OSCILLATION",
    ]


class ManifestCriticStateV1(BaseModel):
    """Stato FSM e cold-review gate del critico nel manifesto handoff v1."""

    model_config = StrictCfg

    fsm_state: str
    correction_attempts: int = Field(ge=0, le=4)
    last_cold_review_gate: Literal[
        "NONE",
        "GATE_1_SCOPE",
        "GATE_2_CODE_GROUNDING",
        "GATE_3_BRIEF_GROUNDING",
        "GATE_4_PRESERVATION",
        "GATE_5_TRUTH_DAST",
        "GATE_6_RSI_CONVERGENCE",
        "ALL_PASSED",
    ] = "NONE"


class NKHandoffManifestV1(BaseModel):
    """Manifesto handoff canonico allineato 1:1 a handoff_anchor_schema.md."""

    model_config = StrictCfg

    manifest_version: str = Field(
        default="1.0.0-Generation",
        pattern=r"^(?:1\.0\.0-Generation|[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9._-]+)?)$",
    )
    handoff_type: Literal[
        "COMPACT_CHECKPOINT",
        "SESSION_HANDOFF",
        "PASSIVE_STATE_HANDOFF",
        "RSI_CONVERGENCE_CHECKPOINT",
    ]
    timestamp: str
    source_conversation_id: str
    topology: ManifestTopologyV1
    active_mode: Literal[
        "MODE_A_SOVEREIGN",
        "MODE_B_FAST_TRACK",
        "MODE_C_VIBE_SPRINT",
        "MODE_D_DISCOVERY",
    ]
    milestone_anchor_id: str
    pentad_paths: ManifestPentadPathsV1
    rsi_state: ManifestRSIStateV1
    critic_state: ManifestCriticStateV1


class StagingEntryV2(BaseModel):
    """Singolo artefatto rilevato in .staging/ con attribuzione di ownership."""

    model_config = StrictCfg

    rel_path: str
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)
    mtime_ns: int = Field(ge=0)
    ownership: Literal["OWN_SESSION", "EXTERNAL_CONCURRENT"]


class StagingFileDiffV2(BaseModel):
    """Diff di continuazione per un file staged con guardia fail-closed su scrittura concorrente."""

    model_config = StrictCfg

    repo_id: str
    rel_path: str
    sha256: Sha256Hex
    ownership: Literal["OWN_SESSION", "EXTERNAL_CONCURRENT"]
    action_policy: Literal["INCLUDE_FOR_CONTINUATION", "DO_NOT_TOUCH_OR_PROMOTE"]
    diff_patch: Optional[str] = None

    @model_validator(mode="after")
    def _enforce_external_ownership_policy(self) -> StagingFileDiffV2:
        if self.ownership == "EXTERNAL_CONCURRENT":
            if self.diff_patch is not None:
                raise ValueError(
                    "EXTERNAL_CONCURRENT staging diff requires diff_patch is None"
                )
            if self.action_policy != "DO_NOT_TOUCH_OR_PROMOTE":
                raise ValueError(
                    "EXTERNAL_CONCURRENT staging diff requires action_policy == 'DO_NOT_TOUCH_OR_PROMOTE'"
                )
        return self


class PatchNotesHeadV2(BaseModel):
    """Estratto verificato dell'intestazione piu recente di PATCH_NOTES.md."""

    model_config = StrictCfg

    present_on_disk: bool
    rel_path: Optional[str] = None
    patch_notes_sha256: Optional[Sha256Hex] = None
    first_section_title: str = ""
    first_section_excerpt: str = Field(default="", max_length=1500)


class RepoSnapshotV2(BaseModel):
    """Snapshot verificato di un repository nell'ecosistema NK."""

    model_config = StrictCfg

    repo_id: str
    repo_root: str
    is_external: bool
    state_sha256: Sha256Hex
    oracle_lock_status: Literal["PRESENT", "ABSENT_ON_DISK"]
    oracle_lock_sha256: Optional[Sha256Hex] = None
    staging_dirty: bool
    staging_entries: StrictTuple[StagingEntryV2] = ()
    concurrent_writer_detected: bool = False
    concurrent_writer_cids: StrictTuple[str] = ()
    anchor_tail_warning: Optional[str] = None
    tracking_drift_detected: bool = False
    tracking_last_conversation_id: Optional[str] = None
    tests_baseline_count: int = Field(ge=0)
    tests_verified_in_session: bool = False
    verification_source: Literal[
        "LIVE_PYTEST_ARTIFACT",
        "DISK_BASELINE_UNVERIFIED_IN_SESSION",
        "FALLBACK_UNVERIFIED",
    ]
    patch_notes_head: PatchNotesHeadV2
    action_policy_hint: Literal["SAFE", "DO_NOT_TOUCH_OR_PROMOTE"] = "SAFE"

    @model_validator(mode="after")
    def _validate_snapshot_invariants(self) -> RepoSnapshotV2:
        if self.oracle_lock_status == "PRESENT" and self.oracle_lock_sha256 is None:
            raise ValueError(
                "oracle_lock_sha256 is required when oracle_lock_status == 'PRESENT'"
            )
        if self.staging_dirty != (len(self.staging_entries) > 0):
            raise ValueError(
                "staging_dirty must match len(staging_entries) > 0"
            )
        return self


class RequirementClauseV2(BaseModel):
    """Singolo requisito tracciabile R1..Rn per continuazione attiva."""

    model_config = StrictCfg

    req_id: str = Field(pattern=r"^R[1-9]\d*$")
    text: str = Field(min_length=1, max_length=600)
    status: Literal["PENDING", "IN_PROGRESS", "BLOCKED", "VERIFIED_DONE"]


class PassiveStandbyPayloadV2(BaseModel):
    """Payload handoff passivo in sola lettura (STANDBY)."""

    model_config = StrictCfg

    handoff_mode: Literal["PASSIVE_STANDBY"] = "PASSIVE_STANDBY"
    ecosystem_repos: StrictTuple[RepoSnapshotV2] = Field(min_length=1)
    transcript_raw_jsonl_included: Literal[False] = False
    ignored_non_nk_dirs: StrictTuple[str] = ()


class ActiveContinuationPayloadV2(BaseModel):
    """Payload handoff per continuazione attiva ancorata a un Intent Brief."""

    model_config = StrictCfg

    handoff_mode: Literal["ACTIVE_CONTINUATION"] = "ACTIVE_CONTINUATION"
    active_brief_id: str = Field(pattern=r"^IB-\d{8}-[A-Z0-9]{6}$")
    target_repo_ids: StrictTuple[str] = Field(min_length=1)
    ecosystem_repos: StrictTuple[RepoSnapshotV2] = Field(min_length=1)
    requirements: StrictTuple[RequirementClauseV2] = Field(min_length=1)
    staging_diffs: StrictTuple[StagingFileDiffV2] = ()
    failed_reasoning_included: Literal[False] = False


HandoffPayloadV2 = Annotated[
    Union[PassiveStandbyPayloadV2, ActiveContinuationPayloadV2],
    Field(discriminator="handoff_mode"),
]


class NKHandoffEnvelopeV2(BaseModel):
    """Envelope sovrano v2 con retro-compatibilita verso session_handoff_latest.json."""

    model_config = StrictCfg

    schema_version: Literal["2.0.0"] = "2.0.0"
    handoff_id: str
    manifest: NKHandoffManifestV1
    payload: HandoffPayloadV2
    pii_redacted_count: int = Field(default=0, ge=0)
    external_live_calls_prohibited: Literal[True] = True
    canonical_bootstrap_cmd: str
    envelope_sha256: Sha256Hex
    version: str = "1.0.0-Generation"
    milestone: str = ""
    conversation_id: str = ""
    steps: int = 0
    steps_tail_window: int = 0
    tokens: int = 0
    actual_tokens: int = 0
    estimated_tokens: int = 0
    turn: int = 0
    turn_phase: Literal[
        "TURN_1",
        "TURN_2",
        "TURN_3",
        "TURN_4",
        "TURN_5",
        "IDLE_CHECKPOINT",
    ] = "IDLE_CHECKPOINT"
    handoff_template: str = "HANDOFF_V2"
    standby_mode: bool = True
    baseline_tests: int = 0
    baseline_pass_rate_pct: float = 100.0
    prompt_lint: Dict[str, Any] = Field(default_factory=dict)
    state_sha256: Sha256Hex
    staging_state_sha256: Optional[str] = None
    dirty_files: bool = False
    project_root: str = ""
    project_dirty_files: bool = False
    stash_patch: Optional[str] = None
    unverified_claims: StrictTuple[str] = ()
    intent_brief_path: Optional[str] = None
    intent_brief_sha256: Optional[str] = None
    pending_actions: StrictTuple[str] = ()
    last_summary: str = ""
    last_failed_checks: StrictTuple[str] = ()


def compute_envelope_sha256(data: Mapping[str, Any]) -> str:
    """Calcola lo SHA-256 canonico dell'envelope escludendo la chiave envelope_sha256."""
    canonical = {k: v for k, v in data.items() if k != "envelope_sha256"}
    raw = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_envelope_v2_dict(data: Mapping[str, Any]) -> NKHandoffEnvelopeV2:
    """Valida in strict mode il dizionario envelope v2 e verifica envelope_sha256."""
    envelope = NKHandoffEnvelopeV2.model_validate(dict(data))
    expected_sha = compute_envelope_sha256(
        envelope.model_dump(mode="json", exclude_unset=True)
    )
    if not hmac.compare_digest(envelope.envelope_sha256, expected_sha):
        raise ValueError(
            f"envelope_sha256 mismatch: expected {expected_sha}, got {envelope.envelope_sha256}"
        )
    return envelope

# -*- coding: utf-8 -*-
"""Mappa deterministica GATE_1..6, ACTIVE/lane firmato e ledger Tensor-RSI (DOM-01)."""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.io import atomic_write_text, unlink_with_retry  # noqa: F401
from _internal.nk_common.tas_ssot_io import read_last_jsonl_entry
from _internal.tensor_rsi.active_slot_io import (
    _read_slot_unlocked,
    assert_slot_owner_or_idle,
    claim_active_session_slot,
    close_active_slot,
    ensure_slot_available,
    read_active_slot,
    resolve_active_slot_mutex_name,
    resolve_active_slot_path,
    verify_slot_payload_integrity,
)
from _internal.tensor_rsi.config_loader import load_tensor_v3_config
from _internal.tensor_rsi.helper_ops import next_ledger_prev_hash, parse_verified_active_file  # noqa: F401
from _internal.tensor_rsi.schemas import (
    GateNameLiteral, GateStatusSummary, MetricSnapshot, ParetoDecisionResult,
    PolicyCell, RSIReasoningFrame, TensorRSILedgerEntry, TensorRSIStateTicket,
)
from _internal.tensor_rsi.ticket_auth import (
    TicketAuthError, canonical_json_bytes, ensure_tensor_hmac_key,  # noqa: F401
    repo_hash12, strict_json_loads, tensor_named_mutex,
)

_DEFAULT_GATE_ORDER: Tuple[GateNameLiteral, ...] = (
    "GATE_1_SCOPE", "GATE_2_CODE_GROUNDING", "GATE_3_BRIEF_GROUNDING",
    "GATE_4_PRESERVATION", "GATE_5_TRUTH_DAST", "GATE_6_RSI_CONVERGENCE",
)


def _is_g5_truth_ok(snapshot: MetricSnapshot) -> bool:
    return all((
        snapshot.sast_critical == 0, snapshot.dast_passed == 1, snapshot.mock_count == 0,
        snapshot.deception_gaming_count == 0, snapshot.s_taint == 0,
        snapshot.poc_confirmed_exploits == 0, snapshot.f_holdout == 0, snapshot.dry_run == 0,
    ))


def _is_snapshot_measured(snapshot: MetricSnapshot) -> bool:
    return snapshot.certification_tier != "UNMEASURED" and not snapshot.unmeasured_reasons and snapshot.dry_run == 0


def _ordered_gate_names(workspace_root: Optional[Union[str, Path]] = None) -> Tuple[GateNameLiteral, ...]:
    rules = load_tensor_v3_config(workspace_root).get("gate_rules", {})
    valid = set(_DEFAULT_GATE_ORDER)
    items = [(int(v.get("order", 99)), k) for k, v in rules.items() if k in valid and isinstance(v, dict)]
    if len(items) == len(_DEFAULT_GATE_ORDER):
        return tuple(k for _, k in sorted(items))  # type: ignore[return-value]
    return _DEFAULT_GATE_ORDER


def map_gates(
    snapshot: MetricSnapshot,
    *,
    reasoning_frame: Optional[RSIReasoningFrame] = None,
    pareto: Optional[ParetoDecisionResult] = None,
    conservation_ok: bool = True,
    tier1_ok: bool = True,
    ast_ok: Optional[bool] = None,
    staging_confined: bool = True,
    workspace_root: Optional[Union[str, Path]] = None,
) -> GateStatusSummary:
    """Valuta in ordine deterministico i 6 gate canonici restituendo GateStatusSummary."""
    has_hyp = reasoning_frame is None or len(reasoning_frame.hypotheses) >= 2
    g2_ast = snapshot.contract_violations == 0 if ast_ok is None else bool(ast_ok)
    g6_ok = snapshot.g_hard == 1 and _is_snapshot_measured(snapshot) and (pareto is None or pareto.accepted)
    details: Dict[str, bool] = {
        "GATE_1_SCOPE": snapshot.scope_creep == 0 and bool(staging_confined),
        "GATE_2_CODE_GROUNDING": g2_ast and snapshot.hallucinated_refs == 0,
        "GATE_3_BRIEF_GROUNDING": snapshot.contract_violations == 0 and has_hyp,
        "GATE_4_PRESERVATION": bool(conservation_ok and tier1_ok),
        "GATE_5_TRUTH_DAST": _is_g5_truth_ok(snapshot),
        "GATE_6_RSI_CONVERGENCE": g6_ok,
    }
    order = _ordered_gate_names(workspace_root)
    passed_gates = [g for g in order if details[g]]
    failed_gates = [g for g in order if not details[g]]
    last_gate: GateNameLiteral = failed_gates[0] if failed_gates else "ALL_PASSED"  # type: ignore[assignment]
    return GateStatusSummary(
        last_cold_review_gate=last_gate, passed_gates=tuple(passed_gates),
        failed_gates=tuple(failed_gates), gate_details=details,
    )


def _active_session_path(root: Path, lane_id: Optional[str] = None) -> Path:
    return resolve_active_slot_path(root, lane_id=lane_id)


def _active_mutex_name(root: Path, lane_id: Optional[str] = None) -> str:
    return resolve_active_slot_mutex_name(root, lane_id=lane_id)


def _verify_active_hmac(
    payload: Dict[str, Any],
    key_path: Optional[Union[str, Path]],
    *,
    lane_id: Optional[str] = None,
) -> None:
    verify_slot_payload_integrity(payload, lane_id=lane_id, key_path=key_path)


def _read_active_session_payload(
    active_path: Path,
    *,
    key_path: Optional[Union[str, Path]] = None,
    allow_expired: bool = False,
    lane_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return _read_slot_unlocked(active_path, lane_id=lane_id, key_path=key_path, allow_expired=allow_expired)


def _assert_session_owner_or_idle(
    payload: Optional[Dict[str, Any]], session_id: Optional[str], *, strict_owner: bool = False
) -> None:
    assert_slot_owner_or_idle(payload, session_id, strict_owner=strict_owner)


def read_verified_active_session(
    root: Path,
    *,
    key_path: Optional[Union[str, Path]] = None,
    allow_expired: bool = False,
    lane_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Legge e verifica ACTIVE.json o slot lane sotto Mutex nominato."""
    return read_active_slot(root, lane_id=lane_id, key_path=key_path, allow_expired=allow_expired)


def ensure_no_foreign_active_session(
    root: Path,
    session_id: Optional[str] = None,
    *,
    key_path: Optional[Union[str, Path]] = None,
    lane_id: Optional[str] = None,
) -> None:
    """Verifica sotto Mutex che non esista un'altra sessione aperta nello slot ACTIVE/lane."""
    ensure_slot_available(root, session_id=session_id, lane_id=lane_id, key_path=key_path)


def write_active_session(
    root: Path,
    session_id: str,
    phase: str,
    accepted: bool,
    stg_sha: str,
    *,
    key_path: Optional[Union[str, Path]] = None,
    ttl_seconds: int = 1800,
    lane_id: Optional[str] = None,
) -> None:
    """Aggiorna ACTIVE.json o slot lane firmato HMAC con TTL in mutua esclusione."""
    claim_active_session_slot(
        root,
        session_id,
        lane_id=lane_id,
        phase=phase,
        accepted=accepted,
        staging_manifest_sha256=stg_sha,
        key_path=key_path,
        ttl_seconds=ttl_seconds,
        write_file=True,
    )


def close_active_session(
    root: Path,
    session_id: Optional[str] = None,
    *,
    key_path: Optional[Union[str, Path]] = None,
    lane_id: Optional[str] = None,
) -> None:
    """Rimuove ACTIVE.json o slot lane solo se appartiene a session_id o non ci sono conflitti."""
    close_active_slot(root, session_id=session_id, lane_id=lane_id, key_path=key_path)


def _verify_and_read_ledger_unlocked(ledger_p: Path, intent_track: str, clade_id: str) -> Tuple[List[Dict[str, Any]], str]:
    if not ledger_p.is_file():
        return [], "0" * 64
    matched: List[Dict[str, Any]] = []
    expected_prev = "0" * 64
    for idx, raw in enumerate(ledger_p.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        rec = strict_json_loads(raw)
        if not isinstance(rec, dict):
            raise TicketAuthError(f"LEDGER_CHAIN_CORRUPT: riga {idx} non oggetto.")
        try:
            entry = TensorRSILedgerEntry.model_validate(rec, strict=True)
        except Exception as exc:
            raise TicketAuthError(f"LEDGER_CHAIN_CORRUPT: schema riga {idx} ({exc}).") from exc
        if entry.prev_hash != expected_prev:
            raise TicketAuthError(f"LEDGER_CHAIN_CORRUPT: prev_hash mismatch alla riga {idx}.")
        body = {k: v for k, v in rec.items() if k != "record_hash"}
        calc_h = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        if not hmac.compare_digest(calc_h, entry.record_hash):
            raise TicketAuthError(f"LEDGER_CHAIN_CORRUPT: record_hash alterato alla riga {idx}.")
        expected_prev = entry.record_hash
        if entry.intent_track == intent_track and entry.clade_id == clade_id:
            matched.append(rec)
    return matched, expected_prev


def read_tensor_ledger_entries(root: Path, intent_track: str, clade_id: str) -> Tuple[List[Dict[str, Any]], str]:
    """Legge e verifica la catena SHA-256 del ledger sotto Mutex nominato."""
    ledger_p = root / "nk_tracking" / "tensor_rsi_ledger.jsonl"
    with tensor_named_mutex(f"Local\\NK_TensorLedger_{repo_hash12(root)}"):
        return _verify_and_read_ledger_unlocked(ledger_p, intent_track, clade_id)


def _build_ledger_entry(
    state: Dict[str, Any], ticket: TensorRSIStateTicket, cell: PolicyCell, pareto: ParetoDecisionResult,
    cand: MetricSnapshot, base: MetricSnapshot, prev_hash: str,
) -> TensorRSILedgerEntry:
    reward = round(max(0.0, min(1.0, 0.6 + 0.4 * math.tanh(10.0 * pareto.directional_projection))), 6) if pareto.accepted else 0.0
    default_op = "OP_DOC_ALIGN" if cell.intent_track == "DOC_TRACK" else "SURGICAL_LOCAL_PATCH"
    body: Dict[str, Any] = {
        "session_id": ticket.session_id, "clade_id": str(state.get("clade_id", "default")),
        "iteration": ticket.iteration, "intent_track": cell.intent_track, "classified_track": cell.classified_track,
        "model_tier": cell.model_tier, "acs_zone": cell.acs_zone,
        "operator": ticket.selected_operator or default_op, "regime": str((state.get("cold_warm") or {}).get("regime", "COLD")),
        "predicted_accept_prob": float(ticket.predicted_accept_prob if ticket.predicted_accept_prob is not None else 0.5),
        "accepted": pareto.accepted, "reward": reward, "directional_projection": pareto.directional_projection,
        "q_v2_before": base.q_v2, "q_v2_after": cand.q_v2, "dry_run": int(cand.dry_run),
        "deception_gaming_count": int(cand.deception_gaming_count), "baseline_state_sha256": ticket.baseline_state_sha256,
        "candidate_state_sha256": cand.state_hash, "prev_hash": prev_hash, "timestamp_utc": time.time(),
    }
    return TensorRSILedgerEntry(**body, record_hash=hashlib.sha256(canonical_json_bytes(body)).hexdigest())


def append_tensor_ledger_entry(
    root: Path, state: Dict[str, Any], ticket: TensorRSIStateTicket, cell: PolicyCell, pareto: ParetoDecisionResult, cand: MetricSnapshot, base: MetricSnapshot
) -> None:
    """Accoda in mutua esclusione Win32 una voce hash-chained con os.fsync in tensor_rsi_ledger.jsonl."""
    ledger_p = root / "nk_tracking" / "tensor_rsi_ledger.jsonl"
    with tensor_named_mutex(f"Local\\NK_TensorLedger_{repo_hash12(root)}"):
        ledger_p.parent.mkdir(parents=True, exist_ok=True)
        prev_hash = next_ledger_prev_hash(ledger_p, read_last_jsonl_entry, TicketAuthError)
        entry = _build_ledger_entry(state, ticket, cell, pareto, cand, base, prev_hash)
        with open(ledger_p, "a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json(exclude_none=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

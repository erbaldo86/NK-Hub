# -*- coding: utf-8 -*-
"""Co-esecutore FSM T0..T7, ledger Tensor-RSI, slot ACTIVE/lane e proiezione rsi_telemetry.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.paths import reconfigure_streams, resolve_workspace_root
from _internal.tensor_rsi.cold_warm_bandit import (
    NoveltyGate, check_conservation_invariants, select_operator_cold_warm, select_prior_signature,  # noqa: F401
)
from _internal.tensor_rsi.gate_mapper import (
    append_tensor_ledger_entry, claim_active_session_slot, close_active_session, ensure_no_foreign_active_session,  # noqa: F401
    map_gates, read_tensor_ledger_entries, read_verified_active_session, write_active_session,  # noqa: F401
)
from _internal.tensor_rsi.materializer import (
    commit_accepted_candidate, compute_staging_manifest_sha256, materialize_and_evaluate,  # noqa: F401
)
from _internal.tensor_rsi.oracle_bridge import append_v1_telemetry_projection, evaluate_ecosystem_ro  # noqa: F401
from _internal.tensor_rsi.pareto_gate import evaluate_pareto_decision  # noqa: F401
from _internal.tensor_rsi.policy_tensor import allowed_operators_for_cell, build_policy_cell  # noqa: F401
from _internal.tensor_rsi.schemas import (
    ALLOWED_TRANSITIONS, DecisionVerdictLiteral, MacroOperatorLiteral, MetricSnapshot,  # noqa: F401
    ParetoDecisionResult, PhaseLiteral, PolicyCell, REJECT_DECISION_VERDICTS,  # noqa: F401
    RSIReasoningFrame, StepLiteral, TensorRSIStateTicket, TensorRSIStepOutput,  # noqa: F401
)
from _internal.tensor_rsi.step_handlers import (
    _next_ticket, handle_decide, handle_diagnose, handle_evaluate, handle_intake, handle_propose, handle_record,
)
from _internal.tensor_rsi.ticket_auth import (
    TicketAuthError, canonical_json_bytes, commit_session_ticket, load_verified_session_state,  # noqa: F401
    repo_hash12, resolve_tensor_state_path, strict_json_loads, tensor_named_mutex,  # noqa: F401
)
from _internal.vibe_sprint_router.intent_track_classifier import classify_intent_track  # noqa: F401
from rsi_convergence_engine import RSIConvergenceEngine  # noqa: F401

_DEFAULT_WORKSPACE_ROOT = Path(resolve_workspace_root(__file__))
_UNTRUSTED_SNAPSHOT_KEYS = ("baseline_snapshot", "candidate_snapshot")


def _normalize_lane_opt(lane_id: Optional[str]) -> Optional[str]:
    if lane_id is None or not str(lane_id).strip():
        return None
    return validate_lane_id(lane_id)


def _merge_lane_input(inp: Dict[str, Any], lane_id: Optional[str]) -> Dict[str, Any]:
    if lane_id is not None and "lane_id" not in inp:
        return {**inp, "lane_id": lane_id}
    return inp


def _assert_no_untrusted_snapshots(inp: Dict[str, Any]) -> None:
    if any(k in inp for k in _UNTRUSTED_SNAPSHOT_KEYS):
        raise TicketAuthError("ORACLE_BYPASS_BLOCKED: baseline_snapshot/candidate_snapshot vietati nel payload JSON.")


def _verify_decide_staging_toctou(root: Path, prev_tkt: TensorRSIStateTicket, state: Dict[str, Any]) -> str:
    """Verifica integrita pre-decide di staging/lane anche in presenza di candidate_id."""
    lane_id = state.get("lane_id")
    stg_sha = compute_staging_manifest_sha256(root, lane_id=lane_id)
    mat_info = state.get("materializer_info") if isinstance(state.get("materializer_info"), dict) else {}
    cand_id = str(state.get("candidate_id") or "").strip()
    if cand_id:
        pre_sha = str(mat_info.get("pre_staging_sha256") or "")
        if not pre_sha or stg_sha != pre_sha:
            raise TicketAuthError("TOCTOU_STAGING_MISMATCH: .staging/ modificata dopo evaluate (candidato).")
        return pre_sha
    if prev_tkt.staging_manifest_sha256 and stg_sha != prev_tkt.staging_manifest_sha256:
        raise TicketAuthError("TOCTOU_STAGING_MISMATCH: .staging/ modificata dopo evaluate.")
    return stg_sha


def _commit_candidate_fail_closed(
    root: Path, prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], expected_pre_sha: str,
) -> str:
    """Esegue commit candidato in staging/lane convertendo mismatch/errori I/O in TicketAuthError."""
    cand_id = str(state.get("candidate_id") or "").strip()
    try:
        return commit_accepted_candidate(
            root, prev_tkt.session_id, cand_id, str(prev_tkt.staging_manifest_sha256 or ""),
            pre_staging_sha256=expected_pre_sha, lane_id=state.get("lane_id"),
        )
    except (ValueError, OSError, FileNotFoundError) as exc:
        raise TicketAuthError(f"TOCTOU_STAGING_MISMATCH: commit candidato bloccato ({exc}).") from exc


def _handle_abort(root: Path, key_path: Optional[Any], prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell) -> TensorRSIStepOutput:
    close_active_session(root, session_id=prev_tkt.session_id, key_path=key_path, lane_id=state.get("lane_id"))
    tkt = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, phase="ABORTED", cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]))
    raw_tkt, _ = commit_session_ticket(root, tkt, state, key_path=key_path, closed=True, expected_ticket_sha256=str(state["active_ticket_sha256"]))
    return TensorRSIStepOutput(status="HALT", step="abort", phase="ABORTED", session_id=tkt.session_id, step_seq=tkt.step_seq, iteration=tkt.iteration, ticket=raw_tkt, policy_cell=cell, summary=f"Sessione {tkt.session_id} interrotta e chiusa (--step abort).")


def _handle_status_without_ticket(root: Path, key_path: Optional[Any], inp: Dict[str, Any]) -> TensorRSIStepOutput:
    lane_id = _normalize_lane_opt(inp.get("lane_id"))
    active = read_verified_active_session(root, key_path=key_path, allow_expired=True, lane_id=lane_id)
    sid = str((active or {}).get("session_id") or inp.get("session_id") or "").strip()
    if sid:
        st_path = resolve_tensor_state_path(root, sid)
        with tensor_named_mutex(f"Local\\NK_TensorRSI_{repo_hash12(root)}"):
            if st_path.is_file():
                st_data = strict_json_loads(st_path.read_text(encoding="utf-8"))
                cell = PolicyCell.model_validate(st_data["policy_cell"])
                verdict = (st_data.get("pareto_decision") or {}).get("verdict")
                out_st = "CONVERGED_OPTIMAL" if verdict == "CONVERGED_OPTIMAL" else ("HALT" if st_data.get("phase") == "ABORTED" else "OK")
                return TensorRSIStepOutput(status=out_st, step="status", phase=st_data.get("phase", "NONE"), session_id=sid, step_seq=int(st_data.get("active_step_seq", 0)), iteration=int(st_data.get("iteration", 0)), policy_cell=cell, summary=f"Stato sessione {sid}: phase={st_data.get('phase')}, closed={st_data.get('closed')}.")
    return TensorRSIStepOutput(status="HALT", step="status", phase="NONE", session_id=sid or "NONE", step_seq=0, iteration=0, policy_cell=build_policy_cell(root, "CONTROL"), summary="Nessuna sessione Tensor-RSI attiva in ACTIVE.json.")


class TensorRSICoExecutor:
    """Orchestratore co-esecutivo DOM-01 per FSM T0..T7 con State-Ticket trsi1."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        key_path: Optional[Union[str, Path]] = None,
        lane_id: Optional[str] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else _DEFAULT_WORKSPACE_ROOT
        self.key_path = key_path
        self.lane_id = _normalize_lane_opt(lane_id)

    def _dispatch_simple_step(self, step: StepLiteral, t_obj: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell, inp: Dict[str, Any], candidate_snapshot: Optional[MetricSnapshot]) -> TensorRSIStepOutput:
        if step == "evaluate":
            return handle_evaluate(self.workspace_root, self.key_path, t_obj, state, cell, inp, candidate_snapshot=candidate_snapshot)
        if step == "decide":
            return handle_decide(self.workspace_root, self.key_path, t_obj, state, cell, inp, _verify_decide_staging_toctou, _commit_candidate_fail_closed)
        if step == "record":
            return handle_record(self.workspace_root, self.key_path, t_obj, state, cell)
        fn = handle_diagnose if step == "diagnose" else handle_propose
        return fn(self.workspace_root, self.key_path, t_obj, state, cell, inp)

    def _execute_ticket_step(
        self, step: StepLiteral, ticket: Optional[str], inp: Dict[str, Any], candidate_snapshot: Optional[MetricSnapshot],
    ) -> TensorRSIStepOutput:
        if step == "status" and not str(ticket or "").strip():
            return _handle_status_without_ticket(self.workspace_root, self.key_path, inp)
        t_obj, state = load_verified_session_state(
            ticket, self.workspace_root, key_path=self.key_path,
            allow_closed=(step == "status"), allow_expired_if_closed=(step == "status"),
        )
        cell = PolicyCell.model_validate(state["policy_cell"])
        if step == "status":
            verdict = (state.get("pareto_decision") or {}).get("verdict")
            st = "CONVERGED_OPTIMAL" if verdict == "CONVERGED_OPTIMAL" else ("HALT" if t_obj.phase == "ABORTED" else "OK")
            return TensorRSIStepOutput(status=st, step="status", phase=t_obj.phase, session_id=t_obj.session_id, step_seq=t_obj.step_seq, iteration=t_obj.iteration, ticket=ticket, policy_cell=cell, summary=f"Stato sessione {t_obj.session_id}: phase={t_obj.phase}, seq={t_obj.step_seq}.")
        if step == "abort":
            return _handle_abort(self.workspace_root, self.key_path, t_obj, state, cell)
        if (t_obj.phase, step) not in ALLOWED_TRANSITIONS:
            raise TicketAuthError(f"Transizione FSM vietata: {t_obj.phase} --{step}--> ?")
        return self._dispatch_simple_step(step, t_obj, state, cell, inp, candidate_snapshot)

    def execute_step(
        self, step: StepLiteral, *, ticket: Optional[str] = None, input_data: Optional[Dict[str, Any]] = None,
        baseline_snapshot: Optional[MetricSnapshot] = None, candidate_snapshot: Optional[MetricSnapshot] = None,
    ) -> TensorRSIStepOutput:
        eff_inp = _merge_lane_input(input_data or {}, self.lane_id)
        _assert_no_untrusted_snapshots(eff_inp)
        if step == "intake":
            return handle_intake(self.workspace_root, self.key_path, eff_inp, baseline_snapshot=baseline_snapshot)
        return self._execute_ticket_step(step, ticket, eff_inp, candidate_snapshot)


def _load_cli_input(raw_input: Optional[str]) -> Dict[str, Any]:
    if not raw_input:
        return {}
    s = str(raw_input).strip()
    parsed = strict_json_loads(s) if s.startswith("{") else strict_json_loads(Path(s).read_text(encoding="utf-8-sig"))
    if not isinstance(parsed, dict):
        raise ValueError("--input deve rappresentare un oggetto JSON.")
    _assert_no_untrusted_snapshots(parsed)
    return parsed


def run_tensor_cli(argv: Optional[Sequence[str]] = None, parser: Optional[argparse.ArgumentParser] = None) -> int:
    """Dispatcher CLI fail-closed per scripts/tensor_rsi.py."""
    reconfigure_streams()
    if parser is None:
        parser = argparse.ArgumentParser(description="Tensor-RSI Control Plane DOM-01")
        for opt, kw in (
            ("--step", {"required": True, "choices": ("intake", "diagnose", "propose", "evaluate", "decide", "record", "status", "abort")}),
            ("--ticket", {"default": None}),
            ("--input", {"default": None}),
            ("--root", {"default": None}),
            ("--lane-id", {"default": None}),
            ("--json", {"action": "store_true"}),
        ):
            parser.add_argument(opt, **kw)
    args = parser.parse_args(argv)
    try:
        out = TensorRSICoExecutor(workspace_root=args.root, lane_id=getattr(args, "lane_id", None)).execute_step(
            args.step, ticket=args.ticket, input_data=_load_cli_input(args.input)
        )
        print(out.model_dump_json(indent=2) if args.json else f"[{out.status}] step={out.step} phase={out.phase} seq={out.step_seq} | {out.summary}")
        return 0
    except (TicketAuthError, ValueError, OSError) as exc:
        err_payload = {"status": "ERROR", "step": args.step, "error": str(exc)}
        print(json.dumps(err_payload, ensure_ascii=False) if args.json else f"[ERROR] {exc}", file=sys.stdout if args.json else sys.stderr)
        return 2

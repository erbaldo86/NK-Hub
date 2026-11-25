# -*- coding: utf-8 -*-
"""Handler FSM T0..T7 separati per mantenere co_executor.py e step_handlers.py <= 220 LOC."""

from __future__ import annotations

import hashlib, secrets, time, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from _internal.tensor_rsi.cold_warm_bandit import (
    NoveltyGate, check_conservation_invariants, select_operator_cold_warm, select_prior_signature,
)
from _internal.tensor_rsi.config_loader import resolve_profile_for_track
from _internal.tensor_rsi.gate_mapper import (
    append_tensor_ledger_entry, close_active_session, ensure_no_foreign_active_session,
    map_gates, read_tensor_ledger_entries, write_active_session,
)
from _internal.tensor_rsi.materializer import (
    commit_accepted_candidate, compute_staging_manifest_sha256, materialize_and_evaluate,
)
from _internal.tensor_rsi.oracle_bridge import append_v1_telemetry_projection, evaluate_ecosystem_ro
from _internal.tensor_rsi.pareto_gate import evaluate_pareto_decision
from _internal.tensor_rsi.policy_tensor import allowed_operators_for_cell, build_policy_cell
from _internal.tensor_rsi.schemas import (
    DecisionVerdictLiteral, MacroOperatorLiteral, MetricSnapshot, ParetoDecisionResult,
    PhaseLiteral, PolicyCell, REJECT_DECISION_VERDICTS, RSIReasoningFrame,
    TensorRSIStateTicket, TensorRSIStepOutput,
)
from _internal.tensor_rsi.ticket_auth import TicketAuthError, canonical_json_bytes, commit_session_ticket
from _internal.vibe_sprint_router.intent_track_classifier import classify_intent_track
from rsi_convergence_engine import RSIConvergenceEngine

_VALID_TRACKS = ("IMPROVEMENT", "OPTIMIZATION", "CONTROL", "DOC_SPEC")
_ITERATION_EPHEMERAL_KEYS = ("pareto_decision", "candidate_snapshot", "gate_status", "candidate_id", "cold_warm", "materializer_info")

def _next_ticket(
    prev: Optional[TensorRSIStateTicket], *, session_id: str, step_seq: int, iteration: int,
    phase: PhaseLiteral, cell: PolicyCell, baseline_sha: str, prev_tkt_sha: str,
    hyp_sha: str = "0" * 64, op: Optional[MacroOperatorLiteral] = None,
    pred_p: Optional[float] = None, seed_dig: Optional[str] = None,
    verdict: Optional[DecisionVerdictLiteral] = None, stg_sha: Optional[str] = None, reset_iter: bool = False,
) -> TensorRSIStateTicket:
    keep = prev is not None and not reset_iter
    return TensorRSIStateTicket(
        session_id=session_id, step_seq=step_seq, iteration=iteration, phase=phase,
        intent_track=cell.intent_track, classified_track=cell.classified_track, policy_cell_hash=cell.policy_cell_hash,
        baseline_state_sha256=baseline_sha, hypothesis_hash_sha256=hyp_sha if prev is None or hyp_sha != "0" * 64 else prev.hypothesis_hash_sha256,
        selected_operator=op if op is not None else (prev.selected_operator if keep else None),
        predicted_accept_prob=pred_p if pred_p is not None else (prev.predicted_accept_prob if keep else None),
        thompson_seed_digest=seed_dig if seed_dig is not None else (prev.thompson_seed_digest if keep else None),
        last_verdict=verdict if verdict is not None else (prev.last_verdict if keep else None),
        staging_manifest_sha256=stg_sha if stg_sha is not None else (prev.staging_manifest_sha256 if keep else None),
        prev_ticket_sha256=prev_tkt_sha, issued_at=int(time.time()), nonce_hex=secrets.token_hex(16),
    )

def _confine_target_files(root: Path, raw_files: Any) -> List[Path]:
    root_res, confined = root.resolve(), []
    for rel in (raw_files or ()):
        rel_str = str(rel or "").strip()
        if not rel_str or Path(rel_str).is_absolute():
            raise TicketAuthError(f"target_files fuori confine workspace: {rel!r}")
        cand = root_res / rel_str
        if cand.is_symlink() or not cand.resolve().is_relative_to(root_res):
            raise TicketAuthError(f"target_files traversal o symlink vietato: {rel!r}")
        confined.append(cand.resolve())
    return confined

def _eval_ro_from_input(root: Path, cell: PolicyCell, inp: Dict[str, Any]) -> Tuple[MetricSnapshot, bool]:
    snap, raw_res = evaluate_ecosystem_ro(
        root, profile=resolve_profile_for_track(cell.classified_track, root), intent_track=cell.intent_track,
        run_pytest=bool(inp.get("run_pytest", False)), strict_verify=bool(inp.get("strict_verify", False)),
        benchmark_suite=inp.get("benchmark_suite"), sast_report=inp.get("sast_report"), test_report=inp.get("test_report"),
        dast_report=inp.get("dast_report"), mutation_report=inp.get("mutation_report"), coverage_report=inp.get("coverage_report"),
        allowed_files=inp.get("allowed_files"),
        loc_delta=(int(inp["loc_delta"]) if inp.get("loc_delta") is not None else -1),
        assert_count=(int(inp["assert_count"]) if inp.get("assert_count") is not None else -1),
        doc_link_count=(int(inp["doc_link_count"]) if inp.get("doc_link_count") is not None else -1),
    )
    ast_ok = snap.sast_critical == 0 and snap.contract_violations == 0 and snap.invalid_json == 0 and snap.mojibake == 0
    if isinstance(raw_res, dict) and isinstance(raw_res.get("checks"), dict):
        qd_chk = raw_res["checks"].get("quality_diff_and_frontend") or {}
        if isinstance(qd_chk, dict) and qd_chk.get("passed") is False:
            ast_ok = False
    return snap, ast_ok

def _resolve_intake_track(inp: Dict[str, Any]) -> str:
    if "classified_track" in inp and inp["classified_track"] is not None:
        track = str(inp["classified_track"]).strip()
        if track not in _VALID_TRACKS:
            raise TicketAuthError(f"classified_track non valido: {track!r}")
        return track
    return classify_intent_track(str(inp.get("prompt", "Miglioramento codice staging")))

def _resolve_intake_baseline(root: Path, cell: PolicyCell, inp: Dict[str, Any], halted: bool, baseline_snapshot: Optional[MetricSnapshot]) -> Optional[MetricSnapshot]:
    if baseline_snapshot is not None:
        return baseline_snapshot if isinstance(baseline_snapshot, MetricSnapshot) else MetricSnapshot.model_validate(baseline_snapshot)
    return None if halted else _eval_ro_from_input(root, cell, inp)[0]

def handle_intake(root: Path, key_path: Optional[Any], inp: Dict[str, Any], *, baseline_snapshot: Optional[MetricSnapshot] = None) -> TensorRSIStepOutput:
    cell = build_policy_cell(root, _resolve_intake_track(inp), model_tier=inp.get("model_tier"), acs_zone=inp.get("acs_zone"), conversation_id=inp.get("conversation_id"), is_micro=bool(inp.get("is_micro", False)), tokens_override=inp.get("tokens"), steps_override=inp.get("steps"))  # type: ignore[arg-type]
    sid = str(inp.get("session_id") or f"TRSI-{int(time.time())}-{uuid.uuid4().hex[:6]}")
    ensure_no_foreign_active_session(root, sid, key_path=key_path)
    stg_sha = compute_staging_manifest_sha256(root)
    target_files = _confine_target_files(root, inp.get("target_files"))
    base_sha = RSIConvergenceEngine.compute_files_state_hash(target_files) if target_files else stg_sha
    halted = cell.halt_for_handoff or cell.intent == "AUDIT_RO" or cell.max_rsi_iterations == 0
    base_snap = _resolve_intake_baseline(root, cell, inp, halted, baseline_snapshot)
    tkt = _next_ticket(None, session_id=sid, step_seq=1, iteration=0, phase="INTAKE", cell=cell, baseline_sha=base_sha, prev_tkt_sha="0" * 64)
    raw_tkt, _ = commit_session_ticket(root, tkt, {"policy_cell": cell.model_dump(), "clade_id": str(inp.get("clade_id", "default")), "baseline_snapshot": base_snap.model_dump() if base_snap else None, "seen_novelty": []}, key_path=key_path, closed=bool(halted))
    if not halted:
        write_active_session(root, sid, "INTAKE", False, stg_sha, key_path=key_path)
    reason = "HALT_CONTEXT_BUDGET" if (halted and cell.max_rsi_iterations == 0 and cell.intent != "AUDIT_RO") else "OK"
    return TensorRSIStepOutput(status="HALT" if halted else "OK", step="intake", phase="INTAKE", session_id=sid, step_seq=1, iteration=0, ticket=raw_tkt, policy_cell=cell, summary=f"Intake {reason} {cell.classified_track} ({cell.model_tier}/{cell.acs_zone}, max_iter={cell.max_rsi_iterations}).")

def handle_diagnose(root: Path, key_path: Optional[Any], prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell, inp: Dict[str, Any]) -> TensorRSIStepOutput:
    next_iter, clean_state, reset_iter = prev_tkt.iteration, dict(state), False
    if prev_tkt.phase == "DECIDE":
        if prev_tkt.last_verdict not in REJECT_DECISION_VERDICTS or (prev_tkt.iteration + 1) >= cell.max_rsi_iterations:
            raise TicketAuthError("Loop DECIDE->DIAGNOSE non consentito (verdetto non REJECT_TIER* o cap iterazioni raggiunto).")
        next_iter, reset_iter = next_iter + 1, True
        for k in _ITERATION_EPHEMERAL_KEYS:
            clean_state.pop(k, None)
    frame = RSIReasoningFrame.model_validate(inp.get("reasoning_frame") or inp)
    hyp_hash = hashlib.sha256(canonical_json_bytes(frame.model_dump())).hexdigest()
    tkt = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=next_iter, phase="DIAGNOSE", cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]), hyp_sha=hyp_hash, reset_iter=reset_iter)
    raw_tkt, _ = commit_session_ticket(root, tkt, {**clean_state, "reasoning_frame": frame.model_dump()}, key_path=key_path, expected_ticket_sha256=str(state["active_ticket_sha256"]))
    write_active_session(root, tkt.session_id, "DIAGNOSE", False, compute_staging_manifest_sha256(root), key_path=key_path)
    return TensorRSIStepOutput(status="OK", step="diagnose", phase="DIAGNOSE", session_id=tkt.session_id, step_seq=tkt.step_seq, iteration=tkt.iteration, ticket=raw_tkt, policy_cell=cell, summary=f"Diagnosi registrata ({len(frame.hypotheses)} ipotesi, iter={tkt.iteration}).")

def handle_propose(root: Path, key_path: Optional[Any], prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell, inp: Dict[str, Any]) -> TensorRSIStepOutput:
    scope_files = (state.get("reasoning_frame") or {}).get("scope_files") or ()
    allowed_ops = allowed_operators_for_cell(cell, file_count=max(1, len(scope_files)), workspace_root=root)
    if not allowed_ops:
        tkt_c = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, phase=prev_tkt.phase, cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]))
        commit_session_ticket(root, tkt_c, state, key_path=key_path, closed=True, expected_ticket_sha256=str(state["active_ticket_sha256"]))
        close_active_session(root, session_id=prev_tkt.session_id, key_path=key_path)
        return TensorRSIStepOutput(status="HALT", step="propose", phase=prev_tkt.phase, session_id=prev_tkt.session_id, step_seq=tkt_c.step_seq, iteration=prev_tkt.iteration, policy_cell=cell, summary="HALT_CONTEXT_BUDGET: mutazioni bloccate da PolicyCell (Z3/AUDIT_RO).")
    hist, tail_h = read_tensor_ledger_entries(root, cell.intent_track, str(state.get("clade_id", "default")))
    base_s = MetricSnapshot.model_validate(state["baseline_snapshot"]) if isinstance(state.get("baseline_snapshot"), dict) else None
    prior_sig = select_prior_signature(sast_critical=base_s.sast_critical if base_s else 0, tests_failed=base_s.failed_tests if base_s else 0, k_mut=base_s.primary.k_mut if base_s else 1.0, c_branch=base_s.primary.c_branch if base_s else 1.0, acs_zone=cell.acs_zone, file_count=max(1, len(scope_files)), is_doc_track=(cell.intent_track == "DOC_TRACK"))
    cw = select_operator_cold_warm(hist, allowed_ops, prior_sig=prior_sig, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, ledger_tail_hash=tail_h, g_hard=base_s.g_hard if base_s else 1, q_star=base_s.q_v2 if base_s else 0.0, expected_improvement_k=float(inp.get("expected_improvement_k", 5.0)), elapsed_s=float(inp.get("elapsed_s", 0.0)), max_iters=max(1, cell.max_rsi_iterations), key_path=key_path, workspace_root=root)
    tkt = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, phase="PROPOSE", cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]), op=cw.selected_operator, pred_p=cw.predicted_accept_prob, seed_dig=cw.thompson_seed_digest)
    raw_tkt, _ = commit_session_ticket(root, tkt, {**state, "cold_warm": cw.model_dump()}, key_path=key_path, closed=bool(cw.voi_should_stop), expected_ticket_sha256=str(state["active_ticket_sha256"]))
    if cw.voi_should_stop:
        close_active_session(root, session_id=tkt.session_id, key_path=key_path)
    prefix = "HALT_VOI_EXHAUSTED | " if cw.voi_should_stop else ""
    return TensorRSIStepOutput(status="HALT" if cw.voi_should_stop else "OK", step="propose", phase="PROPOSE", session_id=tkt.session_id, step_seq=tkt.step_seq, iteration=tkt.iteration, ticket=raw_tkt, policy_cell=cell, cold_warm=cw, summary=f"{prefix}Regime {cw.regime} (N={cw.n_samples}): operatore {cw.selected_operator}.")

def handle_evaluate(root: Path, key_path: Optional[Any], prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell, inp: Dict[str, Any], *, candidate_snapshot: Optional[MetricSnapshot] = None) -> TensorRSIStepOutput:
    seen_nov = list(state.get("seen_novelty") or [])
    if isinstance(files_map := inp.get("files_map"), dict) and files_map:
        is_nov, fp = NoveltyGate(seen_nov).is_novel({str(k): str(v) for k, v in files_map.items()})
        if not is_nov:
            raise TicketAuthError(f"Patch duplicata scartata da NoveltyGate ({fp[:12]}).")
        seen_nov.append(fp)
    cand_id = str(inp.get("candidate_id") or "").strip() or None
    def _do_eval() -> Tuple[MetricSnapshot, bool]:
        if candidate_snapshot is not None:
            s_obj = candidate_snapshot if isinstance(candidate_snapshot, MetricSnapshot) else MetricSnapshot.model_validate(candidate_snapshot)
            return s_obj, (s_obj.sast_critical == 0 and s_obj.contract_violations == 0)
        return _eval_ro_from_input(root, cell, inp)
    (snap, ast_ok), stg_sha, mat_info = materialize_and_evaluate(root, prev_tkt.session_id, cand_id, _do_eval)
    frame = RSIReasoningFrame.model_validate(state["reasoning_frame"]) if state.get("reasoning_frame") else None
    gates = map_gates(snap, reasoning_frame=frame, ast_ok=ast_ok, workspace_root=root)
    tkt = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, phase="EVALUATE", cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]), stg_sha=stg_sha)
    raw_tkt, _ = commit_session_ticket(root, tkt, {**state, "seen_novelty": seen_nov, "candidate_id": cand_id, "ast_ok": ast_ok, "candidate_snapshot": snap.model_dump(), "gate_status": gates.model_dump(), "materializer_info": mat_info}, key_path=key_path, expected_ticket_sha256=str(state["active_ticket_sha256"]))
    return TensorRSIStepOutput(status="OK", step="evaluate", phase="EVALUATE", session_id=tkt.session_id, step_seq=tkt.step_seq, iteration=tkt.iteration, ticket=raw_tkt, policy_cell=cell, gate_status=gates, summary=f"Evaluate g_hard={snap.g_hard}, q_v2={snap.q_v2}, gate={gates.last_cold_review_gate}.")

def handle_decide(root: Path, key_path: Optional[Any], prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell, inp: Dict[str, Any], toctou_fn: Any, commit_fn: Any) -> TensorRSIStepOutput:
    raw_base = state.get("baseline_snapshot")
    if not isinstance(raw_base, dict):
        raise TicketAuthError("MISSING_BASELINE_SNAPSHOT: baseline_snapshot assente nello stato sessione.")
    cand, base = MetricSnapshot.model_validate(state["candidate_snapshot"]), MetricSnapshot.model_validate(raw_base)
    stg_sha = toctou_fn(root, prev_tkt, state)
    base_c = {"tests_total": base.tests_total, "assert_count": base.assert_count, "doc_link_count": base.doc_link_count, "skill_count": base.skill_count}
    curr_c = {"tests_total": cand.tests_total, "assert_count": cand.assert_count, "doc_link_count": cand.doc_link_count, "skill_count": cand.skill_count}
    cons_ok, dropped = check_conservation_invariants(base_c, curr_c, approved_reduction=bool(inp.get("approved_reduction", False)))
    pareto = evaluate_pareto_decision(base, cand, cell.classified_track, workspace_root=root)
    if not cons_ok and pareto.accepted:
        pareto = ParetoDecisionResult(verdict="REJECT_TIER0_HARD_GATE", accepted=False, tier_stopped_at=0, directional_projection=0.0, min_effect=pareto.min_effect, delta_secondary=pareto.delta_secondary, band_violations=dropped, rationale=f"Violazione conservazione: {dropped}")
    if pareto.accepted and state.get("candidate_id"):
        stg_sha = commit_fn(root, prev_tkt, state, stg_sha)
    write_active_session(root, prev_tkt.session_id, "DECIDE", pareto.accepted, stg_sha, key_path=key_path)
    frame = RSIReasoningFrame.model_validate(state["reasoning_frame"]) if state.get("reasoning_frame") else None
    gates = map_gates(cand, reasoning_frame=frame, pareto=pareto, conservation_ok=cons_ok, tier1_ok=(pareto.verdict != "REJECT_TIER1_REGRESSION"), ast_ok=state.get("ast_ok"), workspace_root=root)
    tkt = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, phase="DECIDE", cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]), verdict=pareto.verdict, stg_sha=stg_sha)
    raw_tkt, _ = commit_session_ticket(root, tkt, {**state, "pareto_decision": pareto.model_dump(), "gate_status": gates.model_dump()}, key_path=key_path, expected_ticket_sha256=str(state["active_ticket_sha256"]))
    out_status = "HALT" if pareto.verdict == "HALT_EPISTEMIC_CONFLICT" else ("CONVERGED_OPTIMAL" if pareto.verdict == "CONVERGED_OPTIMAL" else ("OK" if pareto.accepted else "REJECT"))
    return TensorRSIStepOutput(status=out_status, step="decide", phase="DECIDE", session_id=tkt.session_id, step_seq=tkt.step_seq, iteration=tkt.iteration, ticket=raw_tkt, policy_cell=cell, pareto_decision=pareto, gate_status=gates, summary=pareto.rationale)

def handle_record(root: Path, key_path: Optional[Any], prev_tkt: TensorRSIStateTicket, state: Dict[str, Any], cell: PolicyCell) -> TensorRSIStepOutput:
    raw_base = state.get("baseline_snapshot")
    if not isinstance(raw_base, dict):
        raise TicketAuthError("MISSING_BASELINE_SNAPSHOT: baseline_snapshot assente nello stato sessione.")
    pareto = ParetoDecisionResult.model_validate(state["pareto_decision"])
    cand, base = MetricSnapshot.model_validate(state["candidate_snapshot"]), MetricSnapshot.model_validate(raw_base)
    append_tensor_ledger_entry(root, state, prev_tkt, cell, pareto, cand, base)
    append_v1_telemetry_projection(root, cand, prev_tkt, cell, pareto)
    close_active_session(root, session_id=prev_tkt.session_id, key_path=key_path)
    tkt = _next_ticket(prev_tkt, session_id=prev_tkt.session_id, step_seq=prev_tkt.step_seq + 1, iteration=prev_tkt.iteration, phase="RECORDED", cell=cell, baseline_sha=prev_tkt.baseline_state_sha256, prev_tkt_sha=str(state["active_ticket_sha256"]), verdict=pareto.verdict)
    raw_tkt, _ = commit_session_ticket(root, tkt, state, key_path=key_path, closed=True, expected_ticket_sha256=str(state["active_ticket_sha256"]))
    return TensorRSIStepOutput(status="CONVERGED_OPTIMAL" if pareto.verdict == "CONVERGED_OPTIMAL" else "OK", step="record", phase="RECORDED", session_id=tkt.session_id, step_seq=tkt.step_seq, iteration=tkt.iteration, ticket=raw_tkt, policy_cell=cell, pareto_decision=pareto, summary=f"Record salvato in ledger/telemetria ({pareto.verdict}).")

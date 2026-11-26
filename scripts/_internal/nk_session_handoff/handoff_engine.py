# -*- coding: utf-8 -*-
"""Motore checkpoint FSM, resume da anchor e serializzazione NKHandoffEngine v2."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from _internal.nk_common.epistemic_firewall_rules import redact_pii_deterministic
from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_session_handoff.anchor_store import (  # noqa: F401
    ANCHOR_MAX_LINES, SESSION_RETENTION_LIMIT, Win32NamedMutex, _append_anchor_record, _build_and_append_anchor, _compute_workspace_state_sha256,
    _eff_ws_root, _extract_2pc_promo_candidate, _is_consecutive_idle_duplicate, _parse_checkpoint_turn, _read_latest_2pc_promotion_milestone,
    _resolve_anchor_file_path, _resolve_own_anchor_milestone, _resolve_own_anchor_milestone_with_ts, _scan_last_fsm_checkpoint,
    _write_anchor_line_with_rotation, _write_single_anchor_target, get_repo_batch_mutex_name, prune_session_tracking_dirs,
    record_fsm_checkpoint, record_idle_checkpoint_anchor, record_wave_dispatch_anchor, resume_from_anchor, write_bytes_via_2pc_locked,
)
from _internal.nk_session_handoff.constants import (  # noqa: F401
    DEFAULT_MILESTONE_ID, HANDOFF_VERSION, _PLACEHOLDER_MILESTONES, _drift_response, _extract_patch_notes_milestone, _idle_anchor_state_key,
    _is_fsm_checkpoint_rec, _is_meaningful_milestone, _iter_anchor_lines_reversed, _workspace_root, resolve_session_tracking_dir,
)
from _internal.nk_session_handoff.ecosystem_helpers import _clean_str, _load_json_dict, _read_tail_lines, _scrub_handoff_free_text  # noqa: F401
from _internal.nk_session_handoff.ecosystem_scanner import _scan_ecosystem_snapshots_detailed, build_staging_diffs_for_continuation  # noqa: F401
from _internal.nk_session_handoff.session_state import _compute_staging_state_sha256, _parse_optional_turn, _parse_ts_ns_value, _read_baseline_pass_rate
from _internal.nk_session_handoff.templates_compiler import compile_envelope_v2_markdown
from _internal.nk_session_handoff.transcript_cursor import extract_transcript_telemetry_v2

_FACADES = ("nk_session_handoff", "scripts.nk_session_handoff")
_VALID_RSI_STATUSES = frozenset(("CONVERGED_OPTIMAL", "REFINING", "ROLLED_BACK", "ABORTED_OSCILLATION"))
_BRIEF_ID_V2_RE = re.compile(r"^IB-\d{8}-[A-Z0-9]{6}$")
_FREE_TEXT_SCRUB_KEYS = frozenset(("first_section_title", "first_section_excerpt", "diff_patch", "last_summary"))


def _is_nonneg_num(val: Any, *, int_only: bool = False) -> bool:
    return isinstance(val, (int if int_only else (int, float))) and not isinstance(val, bool) and val >= 0


def _map_rsi_status(
    raw_verdict: Any, dk: Any, fq: Any, fq_ok: bool, *, gates_ok: bool = True
) -> str:
    raw_st = _clean_str(raw_verdict)
    if raw_st == "CONVERGED_OPTIMAL" and not gates_ok:
        return "REFINING"
    if raw_st in _VALID_RSI_STATUSES:
        return raw_st
    up = raw_st.upper()
    if up.startswith(("ROLLED_BACK", "REJECT_TIER0", "FAIL")):
        return "ROLLED_BACK"
    if up.startswith(("HALT", "ABORT", "MAX_ITERATIONS")):
        return "ABORTED_OSCILLATION"
    return "REFINING"


def _record_gates_ok(rec: Dict[str, Any]) -> bool:
    """Valida eventuali gate v2 (g_hard == 1 e q_v2 >= 100.0) quando presenti nel record."""
    if "g_hard" in rec and rec["g_hard"] is not None:
        gh = rec["g_hard"]
        if isinstance(gh, bool) or not isinstance(gh, (int, float)) or int(gh) != 1:
            return False
    if "q_v2" in rec and rec["q_v2"] is not None:
        qv2 = rec["q_v2"]
        if isinstance(qv2, bool) or not isinstance(qv2, (int, float)):
            return False
        qv2_f = float(qv2)
        if qv2_f != qv2_f or qv2_f < 100.0:
            return False
    return True


def _parse_rsi_record_dict(ln: str) -> Optional[Dict[str, Any]]:
    """Parsa una singola riga JSONL rsi_telemetry restituendo un dizionario validato o None."""
    if not ln.strip():
        return None
    try:
        rec = json.loads(ln)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return rec if isinstance(rec, dict) else None


def _coerce_rsi_entry(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizza un record JSONL di telemetria RSI applicando fallback REFINING/0.0 fail-closed."""
    it, dk, fq = rec.get("iteration", 0), rec.get("delta_k", 0), rec.get("fitness_q", 0.0)
    raw_st = rec.get("verdict") if _clean_str(rec.get("verdict")) else rec.get("status")
    fq_ok = _is_nonneg_num(fq) and float(fq) <= 100.0 and float(fq) == float(fq)
    dk_ok = _is_nonneg_num(dk) and float(dk) == float(dk)
    return {
        "iteration": it if _is_nonneg_num(it, int_only=True) else 0,
        "delta_k": dk if dk_ok else 0,
        "fitness_q": float(fq) if fq_ok else 0.0,
        "status": _map_rsi_status(raw_st, dk, fq, fq_ok, gates_ok=_record_gates_ok(rec)),
    }


def _read_rsi_file(tel_p: Path) -> Optional[Dict[str, Any]]:
    try:
        lines = _read_tail_lines(tel_p, max_bytes=32768)
    except OSError:
        return None
    for ln in reversed(lines):
        rec = _parse_rsi_record_dict(ln)
        if rec is not None:
            return _coerce_rsi_entry(rec)
    return None


def _read_rsi_state_dict(hub_root: Path, project_root: Path) -> Dict[str, Any]:
    """Legge l'ultimo stato RSI valido da nk_tracking/rsi_telemetry.jsonl con fallback REFINING."""
    for base_r in (project_root, hub_root):
        if (tel_p := base_r / "nk_tracking" / "rsi_telemetry.jsonl").is_file() and (res := _read_rsi_file(tel_p)) is not None:
            return res
    return {"iteration": 0, "delta_k": 0, "fitness_q": 0.0, "status": "REFINING"}


def build_handoff_manifest_v1(hub_root: Path, project_root: Path, conversation_id: str = "", milestone_id: str = DEFAULT_MILESTONE_ID, handoff_type: str = "PASSIVE_STATE_HANDOFF", active_mode: str = "MODE_D_DISCOVERY", fsm_state: str = "BYPASSED", worker_role: str = "[4] NK-Delta-Architect") -> Dict[str, Any]:
    """Costruisce il dizionario NKHandoffManifestV1 completo a 10 campi."""
    return {
        "manifest_version": HANDOFF_VERSION, "handoff_type": handoff_type, "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_conversation_id": _clean_str(conversation_id), "active_mode": active_mode, "rsi_state": _read_rsi_state_dict(hub_root, project_root),
        "topology": {"pattern": "HUB_AND_SPOKE_2_TIER", "critic_role": "NK-Orchestrator", "worker_role": worker_role}, "milestone_anchor_id": str(milestone_id or DEFAULT_MILESTONE_ID).strip(),
        "pentad_paths": {"concept_map": "nk_genome/concept_map.md", "structural_tree": "nk_genome/structural_tree.md", "implementation_plan": "nk_genome/implementation_plan.md", "repo_map": "nk_genome/repo_map.md", "modules_dir": "nk_genome/modules"},
        "critic_state": {"fsm_state": fsm_state, "correction_attempts": 0, "last_cold_review_gate": "NONE"},
    }


def _redact_obj_strings(obj: Any, _key: str = "") -> Tuple[Any, int]:
    """Applica redact_pii_deterministic, scrub AP-14 libero e sanificazione marker ancora."""
    if isinstance(obj, str):
        red, cnt = redact_pii_deterministic(obj)
        red = _scrub_handoff_free_text(red) if _key in _FREE_TEXT_SCRUB_KEYS else red
        return re.sub(r"\[nk-anchor:", "(nk-anchor:", red, flags=re.IGNORECASE), cnt
    if isinstance(obj, list):
        items = [_redact_obj_strings(it, _key) for it in obj]
        return [v for v, _ in items], sum(c for _, c in items)
    if isinstance(obj, dict):
        out_d, tot = {}, 0
        for k, v in obj.items():
            out_d[k], cnt = _redact_obj_strings(v, k)
            tot += cnt
        return out_d, tot
    return obj, 0


def _find_latest_brief_id(reports_dir: Path) -> str:
    if not reports_dir.is_dir():
        return ""
    cands = sorted((p for p in reports_dir.glob("IB-*.md") if _BRIEF_ID_V2_RE.fullmatch(p.stem)), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    return cands[0].stem if cands else ""


def _read_brief_file_meta(reports_dir: Path, eff_bid: str) -> Tuple[Optional[str], Optional[str]]:
    cand_ib = (reports_dir / f"{eff_bid}.md").resolve()
    if not cand_ib.is_relative_to(reports_dir):
        raise ValueError(f"Percorso Intent Brief fuori da reports_dir vietato: {eff_bid!r}")
    return (str(cand_ib), hashlib.sha256(cand_ib.read_bytes()).hexdigest()) if (cand_ib.is_file() and not cand_ib.is_symlink()) else (None, None)


def _norm_single_req(idx: int, req: Mapping[str, str]) -> Dict[str, str]:
    rid = _clean_str(req.get("req_id") or f"R{idx}")
    txt = _clean_str(req.get("text"))[:600] or f"Requisito {rid}"
    st = _clean_str(req.get("status") or "PENDING").upper()
    return {"req_id": rid, "text": txt, "status": st if st in ("PENDING", "IN_PROGRESS", "BLOCKED", "VERIFIED_DONE") else "PENDING"}


def _normalize_requirements_list(requirements: Optional[Sequence[Dict[str, str]]], prompt_text: Optional[str], milestone_val: str) -> List[Dict[str, str]]:
    if requirements:
        return [_norm_single_req(i, r) for i, r in enumerate(requirements, start=1)]
    p_lines = [ln.strip()[:600] for ln in (prompt_text or "").splitlines() if ln.strip()][:8]
    return [{"req_id": f"R{i}", "text": ln, "status": "PENDING"} for i, ln in enumerate(p_lines, start=1)] or [{"req_id": "R1", "text": f"Riprendere continuazione attiva su {milestone_val}.", "status": "PENDING"}]


def _resolve_brief_and_requirements(proj_res: Path, active_brief_id: Optional[str], cid: str, proj_state_sha: str, requirements: Optional[Sequence[Dict[str, str]]], prompt_text: Optional[str], milestone_val: str, mode: str = "PASSIVE_STANDBY") -> Tuple[str, Optional[str], Optional[str], List[Dict[str, str]]]:
    reports_dir, raw_bid = (proj_res / "nk_tracking" / "reports_and_briefs").resolve(), _clean_str(active_brief_id)
    if raw_bid and not _BRIEF_ID_V2_RE.fullmatch(raw_bid):
        raise ValueError(f"active_brief_id non valido: {raw_bid!r}")
    auto_bid = f"IB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{hashlib.sha256((cid or proj_state_sha).encode('utf-8')).hexdigest()[:6].upper()}"
    if mode == "PASSIVE_STANDBY" and not raw_bid:
        eff_bid, ib_path, ib_sha = auto_bid, None, None
    else:
        eff_bid = raw_bid or _find_latest_brief_id(reports_dir) or auto_bid
        ib_path, ib_sha = _read_brief_file_meta(reports_dir, eff_bid)
    return eff_bid, ib_path, ib_sha, _normalize_requirements_list(requirements, prompt_text, milestone_val)


def _extract_matching_global_turn(rec: Dict[str, Any], cid: str, norm_mode: str, proj_state_sha: str) -> int:
    if _clean_str(rec.get("conversation_id")) != cid:
        return 0
    rt = rec.get("turn", 0)
    if not isinstance(rt, int) or isinstance(rt, bool) or not (1 <= rt <= 5):
        return 0
    saved_sha = _clean_str(rec.get("state_sha256"))
    return rt if (norm_mode == "ACTIVE_CONTINUATION" or (saved_sha and saved_sha == proj_state_sha)) else 0


def _resolve_turn_from_global_anchor(proj_res: Path, cid: str, norm_mode: str, proj_state_sha: str) -> int:
    global_anchor = proj_res / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    if not cid or not global_anchor.is_file():
        return 0
    for raw_ln in _iter_anchor_lines_reversed(global_anchor):
        try:
            rec = json.loads(raw_ln)
        except (ValueError, TypeError, json.JSONDecodeError):
            break
        if isinstance(rec, dict) and _is_fsm_checkpoint_rec(rec):
            return _extract_matching_global_turn(rec, cid, norm_mode, proj_state_sha)
    return 0


def _resolve_turn_val(proj_res: Path, cid: str, norm_mode: str, proj_state_sha: str, explicit_turn: Optional[int], own_res: Optional[Mapping[str, Any]], own_exists: bool) -> int:
    if explicit_turn is not None:
        return explicit_turn
    if own_res is not None and own_res.get("status") in ("RESUMED", "DRIFT_DETECTED") and 1 <= (raw_t := int(own_res.get("turn", 0))) <= 5:
        return raw_t
    return 0 if own_exists else _resolve_turn_from_global_anchor(proj_res, cid, norm_mode, proj_state_sha)


def _is_patch_notes_older(proj_res: Path, pn_head: Mapping[str, Any], latest_ts: int) -> bool:
    try:
        return (proj_res / str(pn_head.get("rel_path") or "nk_genome/PATCH_NOTES.md")).stat().st_mtime_ns < latest_ts
    except OSError:
        return True


def _resolve_latest_ms_and_ts(latest_data: Mapping[str, Any]) -> Tuple[str, int, bool]:
    latest_ms = _clean_str(latest_data.get("milestone"))
    latest_man = latest_data.get("manifest") if isinstance(latest_data.get("manifest"), Mapping) else {}
    latest_ts = _parse_ts_ns_value(latest_man.get("timestamp") or latest_data.get("timestamp"))
    return latest_ms, latest_ts, (_is_meaningful_milestone(latest_ms) and latest_ts > 0)


def _resolve_milestone_from_promo_or_pn(proj_res: Path, primary_snap: Mapping[str, Any], latest_data: Mapping[str, Any]) -> str:
    promo_ms, promo_ts = _read_latest_2pc_promotion_milestone(proj_res)
    pn_head = primary_snap.get("patch_notes_head") if isinstance(primary_snap.get("patch_notes_head"), Mapping) else {}
    pn_ms = _extract_patch_notes_milestone(pn_head)
    latest_ms, latest_ts, latest_ok = _resolve_latest_ms_and_ts(latest_data)
    if promo_ms:
        return latest_ms if (latest_ok and (promo_ts <= 0 or latest_ts > promo_ts)) else promo_ms
    if pn_ms:
        return latest_ms if (latest_ok and _is_patch_notes_older(proj_res, pn_head, latest_ts)) else pn_ms
    return latest_ms if _is_meaningful_milestone(latest_ms) else DEFAULT_MILESTONE_ID


def _prefer_newer_promo(proj_res: Path, cand_ms: str, cand_ts_ns: int) -> str:
    """Restituisce l'ultimo milestone 2PC se piu recente del candidato di sessione."""
    promo_ms, promo_ts = _read_latest_2pc_promotion_milestone(proj_res)
    if promo_ms and promo_ts > 0 and (cand_ts_ns <= 0 or promo_ts > cand_ts_ns):
        return promo_ms
    return cand_ms


def _resolve_turn_and_milestone(proj_res: Path, cid: str, norm_mode: str, proj_state_sha: str, primary_snap: Mapping[str, Any], latest_data: Mapping[str, Any], explicit_ms: Optional[str], explicit_turn: Optional[int]) -> Tuple[int, str, str]:
    """Risolve turno isolato per CID e milestone senza contaminazione da altre sessioni."""
    sess_dir = resolve_session_tracking_dir(proj_res, cid)
    own_anchor = (sess_dir / "session_anchor.jsonl") if sess_dir is not None else None
    own_exists = own_anchor is not None and own_anchor.is_file()
    own_res = resume_from_anchor(root=proj_res, conversation_id=cid, state_sha256_override=proj_state_sha) if own_exists else None
    turn_val = _resolve_turn_val(proj_res, cid, norm_mode, proj_state_sha, explicit_turn, own_res, own_exists)
    turn_phase = f"TURN_{turn_val}" if 1 <= turn_val <= 5 else "IDLE_CHECKPOINT"
    if (exp_ms := _clean_str(explicit_ms)):
        return turn_val, turn_phase, exp_ms
    if own_res is not None and _is_meaningful_milestone(own_res.get("milestone_id")):
        return turn_val, turn_phase, _prefer_newer_promo(proj_res, str(own_res["milestone_id"]).strip(), int(own_res.get("milestone_ts_ns") or 0))
    own_ms, own_ts = _resolve_own_anchor_milestone_with_ts(own_anchor)
    if own_ms:
        return turn_val, turn_phase, _prefer_newer_promo(proj_res, own_ms, own_ts)
    return turn_val, turn_phase, _resolve_milestone_from_promo_or_pn(proj_res, primary_snap, latest_data)


def _load_latest_handoff_json(proj_res: Path) -> Dict[str, Any]:
    latest_p = proj_res / "nk_tracking" / "handoff" / "session_handoff_latest.json"
    if not latest_p.is_file():
        return {}
    try:
        loaded = json.loads(latest_p.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _norm_target_repos(target_repo_ids: Optional[Sequence[str]], proj_name: str) -> List[str]:
    return ([str(r).strip() for r in target_repo_ids if str(r).strip()] if target_repo_ids is not None else [proj_name]) or [proj_name]


def _build_handoff_payload_and_manifest(hub_res: Path, proj_res: Path, cid: str, norm_mode: str, turn_phase: str, milestone_val: str, snaps: List[Dict[str, Any]], ignored_non_nk: List[str], eff_brief_id: str, eff_targets: List[str], norm_reqs: List[Dict[str, str]]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str], str, int, List[str]]:
    failed_checks = [f"CONCURRENT_WRITER:{s['repo_id']}" for s in snaps if s.get("concurrent_writer_detected")] + [f"ANCHOR_WARNING:{s['repo_id']}" for s in snaps if s.get("anchor_tail_warning")]
    if norm_mode == "PASSIVE_STANDBY":
        payload: Dict[str, Any] = {"handoff_mode": "PASSIVE_STANDBY", "ecosystem_repos": snaps, "transcript_raw_jsonl_included": False, "ignored_non_nk_dirs": tuple(ignored_non_nk)}
        manifest = build_handoff_manifest_v1(hub_res, proj_res, cid, milestone_val, "PASSIVE_STATE_HANDOFF", "MODE_D_DISCOVERY", "BYPASSED", "[4] NK-Delta-Architect")
        return payload, manifest, [], f"Handoff V2 PASSIVE_STANDBY serializzato su {len(snaps)} repository.", 0, failed_checks
    diffs, diff_redactions = build_staging_diffs_for_continuation(snaps)
    payload = {"handoff_mode": "ACTIVE_CONTINUATION", "active_brief_id": eff_brief_id, "target_repo_ids": eff_targets, "ecosystem_repos": snaps, "requirements": norm_reqs, "staging_diffs": diffs, "failed_reasoning_included": False}
    manifest = build_handoff_manifest_v1(hub_res, proj_res, cid, milestone_val, "SESSION_HANDOFF", "MODE_A_SOVEREIGN", turn_phase, "[3] NK-Python-Async-Builder")
    return payload, manifest, [f"{r['req_id']}:{r['status']}" for r in norm_reqs[:5]], f"Handoff V2 ACTIVE_CONTINUATION serializzato per {eff_brief_id}.", diff_redactions, failed_checks


def serialize_handoff_v2(hub_root: Path, project_root: Path, mode: str = "PASSIVE_STANDBY", ecosystem_scan: bool = False, conversation_id: Optional[str] = None, transcript_path: Optional[Path] = None, active_brief_id: Optional[str] = None, target_repo_ids: Optional[Sequence[str]] = None, requirements: Optional[Sequence[Dict[str, str]]] = None, prompt_text: Optional[str] = None, milestone_id: Optional[str] = None, turn: Optional[int] = None) -> Dict[str, Any]:
    """Serializza e valida l'envelope HANDOFF_V2 con manifest v1, redazione PII e lint."""
    from schemas.handoff_contracts import NKHandoffEnvelopeV2, compute_envelope_sha256

    if (norm_mode := str(mode or "PASSIVE_STANDBY").strip().upper()) not in ("PASSIVE_STANDBY", "ACTIVE_CONTINUATION"):
        raise ValueError(f"Mode handoff v2 non valido: {mode!r}")
    explicit_turn, hub_res, proj_res, cid = _parse_optional_turn(turn), Path(hub_root).resolve(), Path(project_root).resolve(), _clean_str(conversation_id)
    eff_targets = _norm_target_repos(target_repo_ids, proj_res.name)
    tele = extract_transcript_telemetry_v2(transcript_path, fallback_cid=cid)
    snaps, scan_redactions, ignored_non_nk = _scan_ecosystem_snapshots_detailed(hub_res, proj_res, bool(ecosystem_scan), cid, eff_targets, transcript_path)
    primary_snap = next((s for s in snaps if Path(s["repo_root"]).resolve() == proj_res), snaps[0])
    proj_state_sha, proj_dirty = str(primary_snap["state_sha256"]), bool(primary_snap["staging_dirty"])
    turn_val, turn_phase, milestone_val = _resolve_turn_and_milestone(proj_res, cid, norm_mode, proj_state_sha, primary_snap, _load_latest_handoff_json(proj_res), milestone_id, explicit_turn)
    eff_brief_id, ib_path_str, ib_sha_str, norm_reqs = _resolve_brief_and_requirements(proj_res, active_brief_id, cid, proj_state_sha, requirements, prompt_text, milestone_val, mode=norm_mode)
    payload_dict, manifest_dict, pending_actions, last_summary, diff_redactions, failed_checks = _build_handoff_payload_and_manifest(hub_res, proj_res, cid, norm_mode, turn_phase, milestone_val, snaps, ignored_non_nk, eff_brief_id, eff_targets, norm_reqs)
    hub_norm, proj_norm = str(hub_res).replace("\\", "/"), str(proj_res).replace("\\", "/")
    raw_env: Dict[str, Any] = {
        "schema_version": "2.0.0", "handoff_id": f"HO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{proj_state_sha[:8].upper()}", "manifest": manifest_dict, "payload": payload_dict,
        "pii_redacted_count": 0, "external_live_calls_prohibited": True, "envelope_sha256": "0" * 64, "version": HANDOFF_VERSION, "milestone": milestone_val, "conversation_id": cid,
        "canonical_bootstrap_cmd": f'python -B -u "{hub_norm}/scripts/nk_session_bootstrap.py" --handoff-verify --project-root "{proj_norm}" --handoff-file "{proj_norm}/nk_tracking/handoff/next_session_prompt.md"',
        "steps": tele["steps"], "steps_tail_window": tele["steps_tail_window"], "tokens": tele["tokens"], "actual_tokens": tele["actual_tokens"], "estimated_tokens": tele["estimated_tokens"],
        "turn": turn_val, "turn_phase": turn_phase, "handoff_template": "HANDOFF_V2", "standby_mode": norm_mode == "PASSIVE_STANDBY", "baseline_tests": int(primary_snap["tests_baseline_count"]),
        "baseline_pass_rate_pct": float(_read_baseline_pass_rate(proj_res)), "prompt_lint": {"mode": "state-handoff", "passed": True, "violations_count": 0}, "state_sha256": proj_state_sha,
        "staging_state_sha256": _compute_staging_state_sha256(proj_res), "dirty_files": proj_dirty, "project_root": str(proj_res), "project_dirty_files": proj_dirty if proj_res != hub_res else False,
        "stash_patch": None, "unverified_claims": [], "intent_brief_path": ib_path_str, "intent_brief_sha256": ib_sha_str, "pending_actions": pending_actions, "last_summary": last_summary, "last_failed_checks": failed_checks,
    }
    clean_env, env_redactions = _redact_obj_strings(raw_env)
    clean_env["pii_redacted_count"] = int(scan_redactions + diff_redactions + env_redactions)
    pre_validated = NKHandoffEnvelopeV2.model_validate(json.loads(json.dumps(clean_env, ensure_ascii=False))).model_dump(mode="json")
    pre_validated["envelope_sha256"] = compute_envelope_sha256(pre_validated)
    validated_dict = NKHandoffEnvelopeV2.model_validate(pre_validated).model_dump(mode="json")
    compiled_md = compile_envelope_v2_markdown(validated_dict)
    try:
        from nk_transcript_tools import lint_prompt_text as _default_lint_fn
    except ImportError:
        from scripts.nk_transcript_tools import lint_prompt_text as _default_lint_fn  # type: ignore[no-redef]
    lint_res, lint_rc = resolve_facade_attr(_FACADES, "lint_prompt_text", _default_lint_fn)(compiled_md, mode="state-handoff")
    return {"envelope": validated_dict, "compiled_markdown": compiled_md, "lint_result": {**lint_res, "mode": "state-handoff", "return_code": lint_rc}, "handoff_path": str(proj_res / "nk_tracking" / "handoff" / "next_session_prompt.md"), "latest_json_path": str(proj_res / "nk_tracking" / "handoff" / "session_handoff_latest.json")}

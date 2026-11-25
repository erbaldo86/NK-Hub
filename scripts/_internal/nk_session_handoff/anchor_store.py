# -*- coding: utf-8 -*-
"""Archivio atomico degli anchor JSONL, checkpoint FSM e resume da anchor."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_session_handoff.constants import DEFAULT_MILESTONE_ID, _drift_response, _idle_anchor_state_key, _is_fsm_checkpoint_rec, _is_meaningful_milestone, _iter_anchor_lines_reversed, _workspace_root, resolve_session_tracking_dir
from _internal.nk_session_handoff.ecosystem_helpers import _clean_str, _load_json_dict, _read_tail_lines
from _internal.nk_session_handoff.session_state import SESSION_RETENTION_LIMIT, Win32NamedMutex, _compute_staging_state_sha256, _compute_workspace_state_sha256, _parse_ts_ns_value, get_repo_batch_mutex_name, prune_session_tracking_dirs, write_bytes_via_2pc_locked

_FACADES = ("nk_session_handoff", "scripts.nk_session_handoff")
ANCHOR_MAX_LINES: int = 200


def _eff_ws_root() -> Path:
    return Path(resolve_facade_attr(_FACADES, "_workspace_root", _workspace_root)).resolve()

def _extract_2pc_promo_candidate(raw_ln: str) -> Optional[Tuple[str, int]]:
    rec = _load_json_dict(raw_ln)
    if rec is None or _clean_str(rec.get("event") or rec.get("event_type")) != "2PC_ATOMIC_PROMOTION":
        return None
    ms = _clean_str(rec.get("milestone_id") or rec.get("milestone"))
    if not _is_meaningful_milestone(ms):
        return None
    return ms, _parse_ts_ns_value(rec.get("timestamp") or rec.get("ts") or rec.get("timestamp_ns"))

def _read_latest_2pc_promotion_milestone(target_root: Path) -> Tuple[str, int]:
    """Estrae l'ultimo milestone 2PC_ATOMIC_PROMOTION dalla coda dell'ancora globale."""
    anchor_file = Path(target_root).resolve() / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    best_ms, best_ts, seen_no_ts = "", 0, False
    for raw_ln in reversed(_read_tail_lines(anchor_file, max_bytes=65536)):
        if (cand := _extract_2pc_promo_candidate(raw_ln)) is None:
            continue
        ms, ts_ns = cand
        if ts_ns > best_ts:
            best_ms, best_ts = ms, ts_ns
        elif ts_ns == 0 and not best_ms and not seen_no_ts:
            best_ms, seen_no_ts = ms, True
    return best_ms, best_ts

def _resolve_own_anchor_milestone_with_ts(own_anchor: Optional[Path]) -> Tuple[str, int]:
    """Estrae (milestone_id, timestamp_ns) dell'ultimo record significativo nell'ancora di sessione."""
    if own_anchor is None or not own_anchor.is_file():
        return "", 0
    for raw_ln in reversed(_read_tail_lines(own_anchor, max_bytes=32768)):
        if (rec := _load_json_dict(raw_ln)) is not None and _is_meaningful_milestone(cand_ms := (rec.get("milestone_id") or rec.get("milestone"))):
            return str(cand_ms).strip(), _parse_ts_ns_value(rec.get("timestamp") or rec.get("ts") or rec.get("timestamp_ns"))
    return "", 0

def _resolve_own_anchor_milestone(own_anchor: Optional[Path]) -> str:
    return _resolve_own_anchor_milestone_with_ts(own_anchor)[0]

def _is_consecutive_idle_duplicate(dst: Path, record: Mapping[str, Any]) -> bool:
    """Verifica se l'ultima riga valida di dst e' un auto_checkpoint_idle identico per stato/SHA."""
    if _clean_str(record.get("event") or record.get("event_type")) != "auto_checkpoint_idle":
        return False
    if not (tail_lines := _read_tail_lines(dst, max_bytes=32768)):
        return False
    if (last_rec := _load_json_dict(tail_lines[-1])) is None or _clean_str(last_rec.get("event") or last_rec.get("event_type")) != "auto_checkpoint_idle":
        return False
    return _idle_anchor_state_key(last_rec) == _idle_anchor_state_key(record)

def _write_anchor_line_with_rotation(dst: Path, line_stripped: str, max_lines: int = ANCHOR_MAX_LINES) -> None:
    """Appende line_stripped su dst ruotando atomicamente il file quando raggiunge max_lines."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file():
        existing = [ln for ln in dst.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        if len(existing) >= max_lines:
            write_bytes_via_2pc_locked(dst, ("\n".join(existing[-(max_lines - 1) :] + [line_stripped]) + "\n").encode("utf-8"))
            return
    with open(dst, "a", encoding="utf-8") as fh:
        fh.write(line_stripped + "\n")
        fh.flush()
        os.fsync(fh.fileno())

def _write_single_anchor_target(dst: Path, record: Mapping[str, Any], line_stripped: str) -> bool:
    """Appende il record al singolo file ancora sotto mutex se non e' duplicato consecutivo."""
    with Win32NamedMutex(dst.resolve(), timeout_ms=2000, is_path=True):
        if _is_consecutive_idle_duplicate(dst, record):
            return False
        _write_anchor_line_with_rotation(dst, line_stripped, max_lines=ANCHOR_MAX_LINES)
        return True

def _append_anchor_record(record: Dict[str, Any], target_root: Path, conversation_id: Optional[str]) -> Dict[str, Any]:
    """Appende atomicamente un record JSONL in session_anchor.jsonl con dedup idle, cap 200 e retention sessioni."""
    anchor_file = target_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    sess_dir = resolve_session_tracking_dir(target_root, conversation_id)
    line_stripped = json.dumps(record, ensure_ascii=False)
    targets = [anchor_file] + ([sess_dir / "session_anchor.jsonl"] if sess_dir is not None else [])
    with Win32NamedMutex(get_repo_batch_mutex_name(target_root), timeout_ms=2000, is_path=False):
        wrote_flags = [_write_single_anchor_target(dst, record, line_stripped) for dst in targets]
        prune_session_tracking_dirs(target_root, active_conversation_id=conversation_id, max_sessions=SESSION_RETENTION_LIMIT)
    wrote_any = any(wrote_flags)
    out = {**record, "status": "RECORDED" if wrote_any else "DEDUP_SKIPPED", "deduplicated": not wrote_any, "passed": True, "anchor_path": str(anchor_file)}
    if sess_dir is not None:
        out["session_anchor_path"] = str(sess_dir / "session_anchor.jsonl")
    return out

def _build_and_append_anchor(event_name: str, extra: Dict[str, Any], gate_status: str, milestone_id: str, root: Optional[Path], state_sha256_override: Optional[str], staging_state_sha256: Optional[str], conversation_id: Optional[str]) -> Dict[str, Any]:
    target_root = Path(root).resolve() if root is not None else _eff_ws_root()
    record: Dict[str, Any] = {"event": event_name, "type": event_name, "event_type": event_name, **extra, "gate_status": str(gate_status).strip(), "milestone_id": str(milestone_id or DEFAULT_MILESTONE_ID).strip(), "state_sha256": state_sha256_override or _compute_workspace_state_sha256(target_root), "staging_state_sha256": staging_state_sha256 if staging_state_sha256 is not None else _compute_staging_state_sha256(target_root), "timestamp": datetime.now(timezone.utc).isoformat()}
    if conversation_id:
        record["conversation_id"] = str(conversation_id).strip()
    return _append_anchor_record(record, target_root, conversation_id)

def record_fsm_checkpoint(turn: int, gate_status: str, milestone_id: str = "", root: Optional[Path] = None, state_sha256_override: Optional[str] = None, staging_state_sha256: Optional[str] = None, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Registra un checkpoint del turno FSM protetto da mutex in session_anchor.jsonl."""
    if isinstance(turn, bool):
        raise ValueError(f"Il turno FSM non puo essere booleano: {turn}")
    try:
        turn_val = int(turn)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Il turno FSM deve essere un intero valido (1..5): {turn}") from exc
    if not (1 <= turn_val <= 5):
        raise ValueError(f"Il turno FSM deve essere compreso tra 1 e 5: {turn_val}")
    return _build_and_append_anchor("fsm_checkpoint", {"turn": turn_val}, gate_status, milestone_id, root, state_sha256_override, staging_state_sha256, conversation_id)


def record_idle_checkpoint_anchor(gate_status: str = "PASS", milestone_id: str = "", root: Optional[Path] = None, state_sha256_override: Optional[str] = None, staging_state_sha256: Optional[str] = None, conversation_id: Optional[str] = None, handoff_template: str = "Template 12") -> Dict[str, Any]:
    """Registra una traccia passiva di auto-checkpoint senza promuovere turni FSM attivi."""
    return _build_and_append_anchor("auto_checkpoint_idle", {"turn_phase": "IDLE_CHECKPOINT", "template": str(handoff_template or "Template 12").strip()}, gate_status, milestone_id, root, state_sha256_override, staging_state_sha256, conversation_id)


def _resolve_anchor_file_path(target_root: Path, conversation_id: Optional[str]) -> Path:
    sess_dir = resolve_session_tracking_dir(target_root, conversation_id)
    sess_anchor = (sess_dir / "session_anchor.jsonl") if sess_dir is not None else None
    return sess_anchor if (sess_anchor is not None and sess_anchor.is_file()) else (target_root / "nk_tracking" / "anchor" / "session_anchor.jsonl")

def _scan_last_fsm_checkpoint(anchor_file: Path) -> Tuple[Optional[Dict[str, Any]], bool]:
    if not anchor_file.is_file():
        return None, False
    first_line = True
    for raw_ln in _iter_anchor_lines_reversed(anchor_file):
        try:
            parsed = json.loads(raw_ln)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None, True
        if first_line and not isinstance(parsed, dict):
            return None, True
        first_line = False
        if isinstance(parsed, dict) and _is_fsm_checkpoint_rec(parsed):
            return parsed, False
    return None, False

def _parse_checkpoint_turn(last_cp: Mapping[str, Any]) -> Tuple[int, bool]:
    raw_turn = last_cp.get("turn", 0)
    if isinstance(raw_turn, bool):
        return 0, False
    try:
        parsed_turn = int(raw_turn)
    except (ValueError, TypeError):
        return 0, False
    return parsed_turn, (1 <= parsed_turn <= 5)


def resume_from_anchor(root: Optional[Path] = None, conversation_id: Optional[str] = None, state_sha256_override: Optional[str] = None) -> Dict[str, Any]:
    """Ripristina l'ultimo checkpoint FSM da session_anchor.jsonl via backscan 64KB."""
    target_root = Path(root).resolve() if root is not None else _eff_ws_root()
    last_cp, corrupted = _scan_last_fsm_checkpoint(_resolve_anchor_file_path(target_root, conversation_id))
    if corrupted:
        return _drift_response(gate_status="CORRUPTED")
    if last_cp is None:
        return _drift_response(gate_status="MISSING")
    parsed_turn, valid_turn = _parse_checkpoint_turn(last_cp)
    if not valid_turn:
        return _drift_response(turn=parsed_turn, gate_status="INVALID_TURN", milestone_id=str(last_cp.get("milestone_id", "")))
    current_sha256, saved_sha256 = state_sha256_override or _compute_workspace_state_sha256(target_root), str(last_cp.get("state_sha256", "")).strip()
    verified = bool(saved_sha256) and (current_sha256 == saved_sha256)
    return {
        "status": "RESUMED" if verified else "DRIFT_DETECTED", "passed": verified, "verified": verified, "state_drift": not verified,
        "turn": parsed_turn, "turn_phase": f"TURN_{parsed_turn}", "gate_status": str(last_cp.get("gate_status", "")),
        "milestone_id": str(last_cp.get("milestone_id", "")),
        "milestone_ts_ns": _parse_ts_ns_value(last_cp.get("timestamp") or last_cp.get("ts") or last_cp.get("timestamp_ns")),
        "state_sha256": current_sha256, "expected_state_sha256": saved_sha256,
    }

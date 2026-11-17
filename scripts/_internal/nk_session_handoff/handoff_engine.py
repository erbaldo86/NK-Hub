# -*- coding: utf-8 -*-
"""Motore checkpoint FSM e resume da anchor per nk_session_handoff."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from _internal.nk_session_handoff.constants import (
    DEFAULT_MILESTONE_ID,
    _workspace_root,
    resolve_session_tracking_dir,
)
from _internal.nk_session_handoff.session_state import (
    Win32NamedMutex,
    _compute_staging_state_sha256,
    _compute_workspace_state_sha256,
    get_repo_batch_mutex_name,
)


def record_fsm_checkpoint(
    turn: int,
    gate_status: str,
    milestone_id: str = "",
    root: Optional[Path] = None,
    state_sha256_override: Optional[str] = None,
    staging_state_sha256: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Registra un checkpoint del turno FSM protetto da mutex in session_anchor.jsonl."""
    if isinstance(turn, bool):
        raise ValueError(f"Il turno FSM non puo essere booleano: {turn}")
    try:
        turn_val = int(turn)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Il turno FSM deve essere un intero valido (1..5): {turn}") from exc
    if not (1 <= turn_val <= 5):
        raise ValueError(f"Il turno FSM deve essere compreso tra 1 e 5: {turn_val}")

    target_root = Path(root).resolve() if root is not None else _workspace_root.resolve()
    state_sha256 = state_sha256_override or _compute_workspace_state_sha256(target_root)
    eff_staging_sha = (
        staging_state_sha256
        if staging_state_sha256 is not None
        else _compute_staging_state_sha256(target_root)
    )
    anchor_dir = target_root / "nk_tracking" / "anchor"
    anchor_file = anchor_dir / "session_anchor.jsonl"
    sess_dir = resolve_session_tracking_dir(target_root, conversation_id)

    record: Dict[str, Any] = {
        "event": "fsm_checkpoint",
        "type": "fsm_checkpoint",
        "event_type": "fsm_checkpoint",
        "turn": turn_val,
        "gate_status": str(gate_status).strip(),
        "milestone_id": str(milestone_id or DEFAULT_MILESTONE_ID).strip(),
        "state_sha256": state_sha256,
        "staging_state_sha256": eff_staging_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if conversation_id:
        record["conversation_id"] = str(conversation_id).strip()

    line_payload = json.dumps(record, ensure_ascii=False) + "\n"
    batch_name = get_repo_batch_mutex_name(target_root)
    with Win32NamedMutex(batch_name, timeout_ms=2000, is_path=False):
        with Win32NamedMutex(anchor_file.resolve(), timeout_ms=2000, is_path=True):
            anchor_dir.mkdir(parents=True, exist_ok=True)
            with open(anchor_file, "a", encoding="utf-8") as fh:
                fh.write(line_payload)
                fh.flush()
                os.fsync(fh.fileno())
        if sess_dir is not None:
            sess_anchor = sess_dir / "session_anchor.jsonl"
            with Win32NamedMutex(sess_anchor.resolve(), timeout_ms=2000, is_path=True):
                sess_dir.mkdir(parents=True, exist_ok=True)
                with open(sess_anchor, "a", encoding="utf-8") as sfh:
                    sfh.write(line_payload)
                    sfh.flush()
                    os.fsync(sfh.fileno())

    out = dict(record)
    out["status"] = "RECORDED"
    out["passed"] = True
    out["anchor_path"] = str(anchor_file)
    if sess_dir is not None:
        out["session_anchor_path"] = str(sess_dir / "session_anchor.jsonl")
    return out


def _drift_response(turn: int = 0, gate_status: str = "MISSING", milestone_id: str = "") -> Dict[str, Any]:
    return {
        "status": "DRIFT_DETECTED",
        "passed": False,
        "verified": False,
        "state_drift": True,
        "turn": turn,
        "gate_status": gate_status,
        "milestone_id": milestone_id,
        "state_sha256": "",
    }


def resume_from_anchor(
    root: Optional[Path] = None,
    conversation_id: Optional[str] = None,
    state_sha256_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Ripristina l'ultimo checkpoint FSM da session_anchor.jsonl."""
    target_root = Path(root).resolve() if root is not None else _workspace_root.resolve()
    sess_dir = resolve_session_tracking_dir(target_root, conversation_id)
    sess_anchor = (sess_dir / "session_anchor.jsonl") if sess_dir is not None else None
    legacy_anchor = target_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    anchor_file = sess_anchor if (sess_anchor is not None and sess_anchor.is_file()) else legacy_anchor

    last_cp: Optional[Dict[str, Any]] = None
    if anchor_file.is_file():
        non_empty_lines = [
            ln.strip()
            for ln in anchor_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()
        ]
        if non_empty_lines:
            try:
                tail_parsed = json.loads(non_empty_lines[-1])
            except Exception:
                return _drift_response(gate_status="CORRUPTED")
            if not isinstance(tail_parsed, dict):
                return _drift_response(gate_status="CORRUPTED")
            for raw_ln in reversed(non_empty_lines):
                try:
                    parsed = json.loads(raw_ln)
                except Exception:
                    return _drift_response(gate_status="CORRUPTED")
                if isinstance(parsed, dict) and (
                    parsed.get("event_type") == "fsm_checkpoint"
                    or parsed.get("event") == "fsm_checkpoint"
                    or parsed.get("type") == "fsm_checkpoint"
                    or ("turn" in parsed and "state_sha256" in parsed)
                ):
                    last_cp = parsed
                    break

    if last_cp is None:
        return _drift_response(gate_status="MISSING")

    raw_turn = last_cp.get("turn", 0)
    if isinstance(raw_turn, bool):
        return _drift_response(gate_status="INVALID_TURN", milestone_id=str(last_cp.get("milestone_id", "")))
    try:
        parsed_turn = int(raw_turn)
    except (ValueError, TypeError):
        parsed_turn = 0
    if not (1 <= parsed_turn <= 5):
        return _drift_response(turn=parsed_turn, gate_status="INVALID_TURN", milestone_id=str(last_cp.get("milestone_id", "")))

    current_sha256 = state_sha256_override if state_sha256_override else _compute_workspace_state_sha256(target_root)
    saved_sha256 = str(last_cp.get("state_sha256", "")).strip()
    verified = bool(saved_sha256) and (current_sha256 == saved_sha256)

    return {
        "status": "RESUMED" if verified else "DRIFT_DETECTED",
        "passed": verified,
        "verified": verified,
        "state_drift": not verified,
        "turn": parsed_turn,
        "gate_status": str(last_cp.get("gate_status", "")),
        "milestone_id": str(last_cp.get("milestone_id", "")),
        "state_sha256": current_sha256,
        "expected_state_sha256": saved_sha256,
    }

# -*- coding: utf-8 -*-
"""Gestione atomica per-lane degli slot Tensor-RSI firmati HMAC con protezione anti-swap."""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from _internal.nk_common.io import atomic_write_text, unlink_with_retry
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import get_tensor_active_mutex_name, repo_path_hash12
from _internal.tensor_rsi.helper_ops import parse_verified_active_file
from _internal.tensor_rsi.ticket_auth import (
    TicketAuthError,
    canonical_json_bytes,
    ensure_tensor_hmac_key,
    strict_json_loads,
    tensor_named_mutex,
)


def resolve_active_slot_path(
    workspace_root: Union[str, Path], lane_id: Optional[str] = None
) -> Path:
    """Restituisce ACTIVE.json legacy o nk_tracking/tensor_sessions/lanes/<lane_id>.json."""
    root = Path(workspace_root).resolve()
    sessions_dir = root / "nk_tracking" / "tensor_sessions"
    if lane_id is None:
        return sessions_dir / "ACTIVE.json"
    norm_lane = validate_lane_id(lane_id)
    return sessions_dir / "lanes" / f"{norm_lane}.json"


def resolve_active_slot_mutex_name(
    workspace_root: Union[str, Path], lane_id: Optional[str] = None
) -> str:
    """Restituisce il mutex dedicato alla slot (legacy ACTIVE o per-lane NK_TensorLane)."""
    root = Path(workspace_root).resolve()
    if lane_id is None:
        return get_tensor_active_mutex_name(root)
    norm_lane = validate_lane_id(lane_id)
    return f"Local\\NK_TensorLane_{repo_path_hash12(root)}_{norm_lane}"


def verify_slot_payload_integrity(
    payload: Dict[str, Any],
    *,
    lane_id: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
) -> None:
    """Verifica firma HMAC, campi TTL e legame anti-file-swap con lane e repo_hash12."""
    sig = str(payload.get("hmac_sha256", "")).strip().lower()
    if len(sig) != 64:
        raise TicketAuthError("ACTIVE_SESSION_CONFLICT: hmac_sha256 mancante o invalido.")
    body = {k: v for k, v in payload.items() if k != "hmac_sha256"}
    exp = hmac.new(
        ensure_tensor_hmac_key(key_path), canonical_json_bytes(body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(exp, sig):
        raise TicketAuthError("ACTIVE_SESSION_CONFLICT: firma HMAC ACTIVE/lane non valida.")
    if not all(k in payload for k in ("issued_at", "ttl_seconds", "expires_at")):
        raise TicketAuthError("ACTIVE_SESSION_CONFLICT: metadati TTL assenti nello slot.")
    expected_lane = validate_lane_id(lane_id) if lane_id is not None else None
    stored_lane = payload.get("lane_id")
    if expected_lane is None:
        if stored_lane not in (None, ""):
            raise TicketAuthError(
                f"ACTIVE_SESSION_CONFLICT: lane_id imprevisto ({stored_lane!r}) in ACTIVE.json."
            )
    elif stored_lane != expected_lane:
        raise TicketAuthError(
            f"ACTIVE_SESSION_CONFLICT: file-swap rilevato (atteso lane_id={expected_lane!r}, trovato {stored_lane!r})."
        )
    if workspace_root is not None and "repo_hash12" in payload:
        exp_repo = repo_path_hash12(Path(workspace_root).resolve())
        if str(payload.get("repo_hash12") or "") != exp_repo:
            raise TicketAuthError(
                f"ACTIVE_SESSION_CONFLICT: cross-repo slot swap rilevato ({payload.get('repo_hash12')!r} != {exp_repo!r})."
            )


def _read_slot_unlocked(
    slot_path: Path,
    *,
    lane_id: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
    allow_expired: bool = False,
    workspace_root: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    if slot_path.is_symlink() or is_reparse_entry(slot_path) or is_reparse_entry(slot_path.parent):
        raise TicketAuthError(f"ACTIVE_SESSION_CONFLICT: symlink/reparse vietato su {slot_path}.")
    if not slot_path.exists():
        return None
    return parse_verified_active_file(
        slot_path,
        key_path,
        allow_expired,
        lambda p, kp: verify_slot_payload_integrity(p, lane_id=lane_id, key_path=kp, workspace_root=workspace_root),
        unlink_with_retry,
        strict_json_loads,
        TicketAuthError,
    )


def assert_slot_owner_or_idle(
    payload: Optional[Dict[str, Any]],
    session_id: Optional[str],
    *,
    strict_owner: bool = False,
) -> None:
    """Verifica che lo slot sia libero, accettato o di proprieta di session_id."""
    if payload is None:
        return
    existing_sid = str(payload.get("session_id") or "").strip()
    is_accepted = payload.get("accepted") is True
    if not is_accepted and (not session_id or existing_sid != session_id):
        raise TicketAuthError(
            f"ACTIVE_SESSION_CONFLICT: sessione attiva aperta ({existing_sid or 'UNKNOWN'})."
        )
    if strict_owner and session_id is not None and existing_sid and existing_sid != session_id:
        raise TicketAuthError(
            f"ACTIVE_SESSION_CONFLICT: slot appartiene alla sessione {existing_sid!r}."
        )


def read_active_slot(
    workspace_root: Union[str, Path],
    *,
    lane_id: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
    allow_expired: bool = False,
) -> Optional[Dict[str, Any]]:
    """Legge e verifica uno slot ACTIVE/lane sotto il relativo Mutex nominato."""
    slot_p = resolve_active_slot_path(workspace_root, lane_id=lane_id)
    with tensor_named_mutex(resolve_active_slot_mutex_name(workspace_root, lane_id=lane_id)):
        return _read_slot_unlocked(
            slot_p, lane_id=lane_id, key_path=key_path, allow_expired=allow_expired, workspace_root=workspace_root
        )


def ensure_slot_available(
    workspace_root: Union[str, Path],
    session_id: Optional[str] = None,
    *,
    lane_id: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
) -> None:
    """Verifica sotto Mutex che non esista una sessione straniera non accettata nello slot."""
    slot_p = resolve_active_slot_path(workspace_root, lane_id=lane_id)
    with tensor_named_mutex(resolve_active_slot_mutex_name(workspace_root, lane_id=lane_id)):
        payload = _read_slot_unlocked(slot_p, lane_id=lane_id, key_path=key_path, workspace_root=workspace_root)
        assert_slot_owner_or_idle(payload, session_id)


def _sign_slot_body(body: Dict[str, Any], key_path: Optional[Union[str, Path]]) -> Dict[str, Any]:
    sig = hmac.new(
        ensure_tensor_hmac_key(key_path), canonical_json_bytes(body), hashlib.sha256
    ).hexdigest()
    return {**body, "hmac_sha256": sig}


def claim_active_session_slot(
    workspace_root: Union[str, Path],
    session_id: str,
    *,
    lane_id: Optional[str] = None,
    phase: str = "INTAKE",
    accepted: bool = False,
    staging_manifest_sha256: str = "",
    base_repo_seq: Optional[int] = None,
    key_path: Optional[Union[str, Path]] = None,
    ttl_seconds: int = 1800,
    write_file: bool = True,
) -> Path:
    """Reclama atomicamente lo slot sotto Mutex eliminando race tra check e write (BS-04)."""
    norm_lane = validate_lane_id(lane_id) if lane_id is not None else None
    slot_p = resolve_active_slot_path(workspace_root, lane_id=norm_lane)
    now_ts = int(time.time())
    ttl_i = max(60, min(7200, int(ttl_seconds)))
    body: Dict[str, Any] = {
        "session_id": session_id,
        "phase": phase,
        "accepted": bool(accepted),
        "staging_manifest_sha256": staging_manifest_sha256,
        "repo_hash12": repo_path_hash12(Path(workspace_root).resolve()),
        "issued_at": now_ts,
        "ttl_seconds": ttl_i,
        "expires_at": now_ts + ttl_i,
    }
    if norm_lane is not None:
        body["lane_id"] = norm_lane
    if base_repo_seq is not None:
        body["base_repo_seq"] = int(base_repo_seq)
    payload = _sign_slot_body(body, key_path) if write_file else None
    with tensor_named_mutex(resolve_active_slot_mutex_name(workspace_root, lane_id=norm_lane)):
        existing = _read_slot_unlocked(slot_p, lane_id=norm_lane, key_path=key_path, workspace_root=workspace_root)
        assert_slot_owner_or_idle(existing, session_id)
        if write_file and payload is not None:
            ok, err = atomic_write_text(
                slot_p,
                canonical_json_bytes(payload).decode("utf-8"),
                ensure_parent=True,
                fsync_data=True,
                reparse_check=is_reparse_entry,
            )
            if not ok:
                raise OSError(f"Scrittura slot {slot_p.name} fallita: {err}")
    return slot_p


def close_active_slot(
    workspace_root: Union[str, Path],
    session_id: Optional[str] = None,
    *,
    lane_id: Optional[str] = None,
    key_path: Optional[Union[str, Path]] = None,
) -> None:
    """Rimuove lo slot ACTIVE/lane solo se appartiene a session_id o non ci sono conflitti."""
    slot_p = resolve_active_slot_path(workspace_root, lane_id=lane_id)
    with tensor_named_mutex(resolve_active_slot_mutex_name(workspace_root, lane_id=lane_id)):
        payload = _read_slot_unlocked(
            slot_p, lane_id=lane_id, key_path=key_path, allow_expired=True, workspace_root=workspace_root
        )
        if payload is None:
            return
        assert_slot_owner_or_idle(payload, session_id, strict_owner=True)
        unlink_with_retry(slot_p, raise_on_error=False)

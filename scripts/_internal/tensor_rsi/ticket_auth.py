# -*- coding: utf-8 -*-
"""Autenticazione HMAC-SHA256 State-Ticket trsi1., JSON strict e anti-replay con Mutex Win32."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from _internal.nk_common.io import atomic_write_bytes, atomic_write_text
from _internal.nk_common.staging_manifest import canonical_json_bytes as _cm_canonical_json_bytes
from _internal.nk_common.staging_manifest import no_dup_pairs_hook as _cm_no_dup_pairs_hook
from _internal.nk_common.win32_mutex import create_or_open_named_mutex, release_win32_mutex
from _internal.tensor_rsi.helper_ops import check_state_cas, validate_session_record, write_new_key_exclusive
from _internal.tensor_rsi.schemas import TensorRSIStateTicket

_TICKET_PREFIX = "trsi1"
_MAX_FUTURE_SKEW_SEC = 30
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: Dict[str, threading.RLock] = {}


class TicketAuthError(RuntimeError):
    """Errore fail-closed di firma, formato, scadenza o replay dello State-Ticket."""


def strict_json_loads(raw_json: str) -> Any:
    """Decodifica JSON strict rifiutando chiavi duplicate, NaN e Infinity."""
    def _reject_const(val: str) -> Any:
        raise TicketAuthError(f"Costante JSON non standard vietata: {val!r}")

    try:
        return json.loads(
            raw_json,
            object_pairs_hook=lambda pairs: _cm_no_dup_pairs_hook(pairs, exc_cls=TicketAuthError),
            parse_constant=_reject_const,
        )
    except TicketAuthError:
        raise
    except Exception as exc:
        raise TicketAuthError(f"Payload JSON strict non valido: {exc}") from exc


def canonical_json_bytes(payload: Any) -> bytes:
    """Serializza payload in JSON canonico deterministico privo di NaN/Inf."""
    return _cm_canonical_json_bytes(payload, exc_cls=TicketAuthError)


def resolve_tensor_hmac_key_path(key_path: Optional[Union[str, Path]] = None) -> Path:
    """Risolve il percorso esterno della chiave HMAC fuori dal repository."""
    if key_path is not None and str(key_path).strip():
        return Path(str(key_path).strip()).expanduser().resolve()
    env_path = os.environ.get("NK_TENSOR_RSI_HMAC_KEY_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    base_dir = os.environ.get("LOCALAPPDATA", "").strip() or tempfile.gettempdir()
    return (Path(base_dir) / "nk_hub" / "tensor_rsi_hmac.key").resolve()


def _read_existing_hmac_key(resolved: Path) -> bytes:
    raw = resolved.read_bytes().strip()
    if not raw:
        raise TicketAuthError(f"Chiave HMAC Tensor-RSI vuota: {resolved}")
    return raw


def ensure_tensor_hmac_key(key_path: Optional[Union[str, Path]] = None) -> bytes:
    """Legge o crea atomicamente con Mutex e O_EXCL la chiave HMAC esterna."""
    resolved = resolve_tensor_hmac_key_path(key_path)
    key_sig = hashlib.sha256(str(resolved).lower().encode("utf-8")).hexdigest()[:12]
    with tensor_named_mutex(f"Local\\NK_TensorHMACKey_{key_sig}"):
        if resolved.is_file():
            return _read_existing_hmac_key(resolved)
        return write_new_key_exclusive(resolved, secrets.token_hex(32).encode("ascii"), atomic_write_bytes, TicketAuthError)


def derive_hmac_seed_int(domain_tag: str, key_path: Optional[Union[str, Path]] = None) -> int:
    """Deriva un seed intero a 64 bit riproducibile via HMAC-SHA256."""
    digest = hmac.new(ensure_tensor_hmac_key(key_path), domain_tag.encode("utf-8"), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


@contextmanager
def tensor_named_mutex(mutex_name: str, wait_ms: int = 5000) -> Iterator[None]:
    """Context manager rientrante fail-closed su Win32NamedMutex e RLock locale."""
    with _THREAD_LOCKS_GUARD:
        t_lock = _THREAD_LOCKS.setdefault(mutex_name, threading.RLock())
    h_mutex: Optional[int] = None
    with t_lock:
        if sys.platform == "win32":
            h_mutex, acquired, err = create_or_open_named_mutex(mutex_name, wait_ms=wait_ms)
            if not acquired:
                raise TicketAuthError(f"Timeout/errore Win32NamedMutex {mutex_name}: {err}")
        try:
            yield
        finally:
            release_win32_mutex(h_mutex)


def repo_hash12(workspace_root: Union[str, Path]) -> str:
    """Calcola il prefisso SHA-256 a 12 caratteri del percorso canonico del repo."""
    norm = os.path.realpath(str(workspace_root)).lower().replace("/", "\\").rstrip("\\")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def resolve_tensor_state_path(workspace_root: Union[str, Path], session_id: str) -> Path:
    """Restituisce il percorso stato anti-replay in tempfile.gettempdir()/nk_tensor_rsi/."""
    clean_sid = str(session_id or "").strip()
    if not clean_sid or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in clean_sid):
        raise TicketAuthError(f"Session ID non valido: {session_id!r}")
    return Path(tempfile.gettempdir()) / "nk_tensor_rsi" / repo_hash12(workspace_root) / f"{clean_sid}.json"


def sign_ticket(ticket: TensorRSIStateTicket, key_path: Optional[Union[str, Path]] = None) -> str:
    """Serializza e firma un TensorRSIStateTicket nel formato trsi1.<b64url>.<hmac64>."""
    key_bytes = ensure_tensor_hmac_key(key_path)
    b64_str = base64.urlsafe_b64encode(canonical_json_bytes(ticket.model_dump())).rstrip(b"=").decode("ascii")
    sig_hex = hmac.new(key_bytes, f"{_TICKET_PREFIX}:{b64_str}".encode("ascii"), hashlib.sha256).hexdigest()
    return f"{_TICKET_PREFIX}.{b64_str}.{sig_hex}"


def _check_ticket_time_window(ticket: TensorRSIStateTicket, now_ts: Optional[int], allow_expired: bool) -> None:
    eff_now = int(time.time()) if now_ts is None else int(now_ts)
    if ticket.issued_at - eff_now > _MAX_FUTURE_SKEW_SEC:
        raise TicketAuthError("State-Ticket fuori finestra temporale (skew).")
    if not allow_expired and eff_now - ticket.issued_at > ticket.ttl_seconds:
        raise TicketAuthError("State-Ticket fuori finestra temporale (TTL).")


def verify_ticket_signature(
    raw_ticket: Optional[str], key_path: Optional[Union[str, Path]] = None, *,
    now_ts: Optional[int] = None, allow_expired: bool = False,
) -> TensorRSIStateTicket:
    """Verifica formato, firma HMAC-SHA256, JSON strict e finestra temporale del ticket."""
    parts = str(raw_ticket or "").strip().split(".")
    if len(parts) != 3 or parts[0] != _TICKET_PREFIX:
        raise TicketAuthError("Formato State-Ticket trsi1. non valido.")
    b64_str, sig_hex = parts[1], parts[2].lower()
    if not b64_str or len(sig_hex) != 64 or not all(ch in _HEX_CHARS for ch in sig_hex):
        raise TicketAuthError("Firma HMAC State-Ticket malformata.")
    expected_sig = hmac.new(ensure_tensor_hmac_key(key_path), f"{_TICKET_PREFIX}:{b64_str}".encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig_hex):
        raise TicketAuthError("Verifica firma HMAC State-Ticket fallita.")
    padded = b64_str + "=" * ((-len(b64_str)) % 4)
    try:
        decoded_raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        ticket = TensorRSIStateTicket.model_validate(strict_json_loads(decoded_raw), strict=True)
    except TicketAuthError:
        raise
    except Exception as exc:
        raise TicketAuthError(f"Decodifica/schema State-Ticket non valido: {exc}") from exc
    _check_ticket_time_window(ticket, now_ts, allow_expired)
    return ticket


def load_verified_session_state(
    raw_ticket: Optional[str], workspace_root: Union[str, Path], *,
    key_path: Optional[Union[str, Path]] = None, now_ts: Optional[int] = None,
    allow_closed: bool = False, allow_expired_if_closed: bool = False,
) -> Tuple[TensorRSIStateTicket, Dict[str, Any]]:
    """Verifica firma + anti-replay step_seq/hash dentro Win32NamedMutex."""
    ticket = verify_ticket_signature(raw_ticket, key_path=key_path, now_ts=now_ts, allow_expired=allow_expired_if_closed)
    raw_sha = hashlib.sha256(str(raw_ticket).strip().encode("utf-8")).hexdigest()
    state_path = resolve_tensor_state_path(workspace_root, ticket.session_id)
    eff_now = int(time.time()) if now_ts is None else int(now_ts)
    with tensor_named_mutex(f"Local\\NK_TensorRSI_{repo_hash12(workspace_root)}"):
        state = validate_session_record(state_path, ticket, raw_sha, allow_closed, allow_expired_if_closed, eff_now, strict_json_loads, TicketAuthError)
        return ticket, state


def _persist_session_state(state_path: Path, new_state: Dict[str, Any]) -> None:
    ok, err = atomic_write_text(
        state_path, json.dumps(new_state, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2),
        ensure_parent=True, fsync_data=True,
    )
    if not ok:
        raise TicketAuthError(f"Salvataggio atomico stato sessione fallito: {err}")


def commit_session_ticket(
    workspace_root: Union[str, Path], ticket: TensorRSIStateTicket, session_extra: Dict[str, Any],
    *, key_path: Optional[Union[str, Path]] = None, closed: bool = False,
    expected_ticket_sha256: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Firma il nuovo ticket e salva atomicamente lo stato anti-replay con CAS sotto Mutex."""
    raw_ticket = sign_ticket(ticket, key_path=key_path)
    state_path = resolve_tensor_state_path(workspace_root, ticket.session_id)
    new_state: Dict[str, Any] = {
        **session_extra, "session_id": ticket.session_id, "active_step_seq": ticket.step_seq,
        "active_ticket_sha256": hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest(),
        "phase": ticket.phase, "iteration": ticket.iteration,
        "baseline_state_sha256": ticket.baseline_state_sha256,
        "policy_cell_hash": ticket.policy_cell_hash, "closed": bool(closed),
    }
    with tensor_named_mutex(f"Local\\NK_TensorRSI_{repo_hash12(workspace_root)}"):
        check_state_cas(state_path, ticket.step_seq, ticket.session_id, expected_ticket_sha256, strict_json_loads, TicketAuthError)
        _persist_session_state(state_path, new_state)
    return raw_ticket, new_state

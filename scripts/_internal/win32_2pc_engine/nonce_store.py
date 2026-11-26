# -*- coding: utf-8 -*-
"""
Store persistente anti-replay per nonce HMAC governance sotto Win32NamedMutex (Goldilocks defer).
Modulo: scripts/_internal/win32_2pc_engine/nonce_store.py.
@domain_id: DOM-01
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Set, Tuple, Union

from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
from _internal.win32_2pc_engine.io_and_paths import _replace_with_retry
from _internal.win32_2pc_engine.mutex import Win32NamedMutex

_NONCE_CLOCK_SKEW_SEC = 60
_ACTIVE_BATCH_NONCES: contextvars.ContextVar[Optional[Set[str]]] = contextvars.ContextVar("nk_gov_batch_nonces", default=None)
_ACTIVE_NONCE_ENFORCE: contextvars.ContextVar[bool] = contextvars.ContextVar("nk_gov_nonce_enforce", default=False)
_DEFER_BATCH_NONCE_COMMIT: contextvars.ContextVar[bool] = contextvars.ContextVar("nk_gov_defer_nonce", default=False)
_PENDING_BATCH_NONCES: contextvars.ContextVar[Optional[Dict[str, Tuple[int, Path]]]] = contextvars.ContextVar("nk_gov_pending_nonces", default=None)


def resolve_governance_nonce_store_path(store_path: Optional[Union[str, Path]] = None) -> Path:
    if store_path is not None:
        cand = Path(store_path)
    elif (env_override := os.environ.get("NK_GOVERNANCE_NONCE_STORE_PATH", "").strip()):
        cand = Path(env_override)
    else:
        base_dir = os.environ.get("LOCALAPPDATA", "").strip() or tempfile.gettempdir()
        cand = Path(base_dir) / "nk_hub" / "governance_nonces.json"
    if is_reparse_entry(cand) or is_reparse_entry(cand.parent):
        raise TwoPhaseCommitError(f"Reparse point vietato su store nonce governance: {cand}")
    return cand.resolve()


def is_nonce_replay_enforced(*, token_version: str = "v1", consume_nonce: bool = False, active_session: bool = False) -> bool:
    env_flag = os.environ.get("NK_GOVERNANCE_NONCE_ENFORCE", "").strip() == "1"
    ver = str(token_version or "v1").strip().lower()
    return bool(consume_nonce or ver == "v2" or active_session or _ACTIVE_NONCE_ENFORCE.get() or env_flag)


@contextlib.contextmanager
def governance_batch_nonce_scope(enforce: bool = False, *, defer_commit: bool = False) -> Iterator[None]:
    """Consente riutilizzo controllato nel batch 2PC con commit differito Goldilocks opzionale."""
    tok_nonces = _ACTIVE_BATCH_NONCES.set(set())
    tok_enforce = _ACTIVE_NONCE_ENFORCE.set(bool(enforce) or _ACTIVE_NONCE_ENFORCE.get())
    tok_defer = _DEFER_BATCH_NONCE_COMMIT.set(bool(defer_commit))
    tok_pending = _PENDING_BATCH_NONCES.set({})
    try:
        yield
    finally:
        _PENDING_BATCH_NONCES.reset(tok_pending)
        _DEFER_BATCH_NONCE_COMMIT.reset(tok_defer)
        _ACTIVE_NONCE_ENFORCE.reset(tok_enforce)
        _ACTIVE_BATCH_NONCES.reset(tok_nonces)


def _reject_nonce_json_constant(raw_const: str) -> None:
    raise TwoPhaseCommitError(f"Costante JSON non valida nello store nonce governance: {raw_const!r}")


def _validate_nonce_expiry_entry(k: Any, exp: Any, resolved: Path) -> int:
    if not isinstance(k, str) or isinstance(exp, bool) or not isinstance(exp, (int, float)):
        raise TwoPhaseCommitError(f"Voce nonce governance non valida o corrotta ({resolved}): key={k!r}")
    exp_f = float(exp)
    if not math.isfinite(exp_f):
        raise TwoPhaseCommitError(f"Scadenza nonce non finita ({resolved}): key={k!r}")
    return int(exp_f)


def _load_active_nonces(resolved: Path, now_ts: int) -> Dict[str, int]:
    if not resolved.exists():
        return {}
    try:
        raw_text = resolved.read_text(encoding="utf-8-sig")
        raw_obj = json.loads(raw_text, parse_constant=_reject_nonce_json_constant) if raw_text.strip() else {}
    except TwoPhaseCommitError:
        raise
    except (OSError, ValueError, OverflowError) as exc:
        raise TwoPhaseCommitError(f"Nonce store governance corrotto o illeggibile ({resolved}): {exc}") from exc
    if not isinstance(raw_obj, dict):
        raise TwoPhaseCommitError(f"Formato nonce store governance non valido ({resolved}): atteso oggetto JSON.")
    validated = ((k, _validate_nonce_expiry_entry(k, exp, resolved)) for k, exp in raw_obj.items())
    return {k: exp_i for k, exp_i in validated if exp_i > now_ts}


def _atomic_write_nonces(resolved: Path, records: Dict[str, int]) -> None:
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False)
    fd, tmp_name = tempfile.mkstemp(prefix=".nonce_", suffix=".tmp", dir=str(resolved.parent), text=True)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp_path, resolved)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def flush_pending_batch_nonces() -> int:
    """Consuma su disco i nonce differiti dello scope corrente subito prima dello swap FS."""
    pending = _PENDING_BATCH_NONCES.get()
    if not pending:
        return 0
    by_store: Dict[Path, Dict[str, int]] = {}
    for nonce_hex, (expiry_ts, store_p) in pending.items():
        by_store.setdefault(store_p, {})[nonce_hex] = int(expiry_ts)
    now_ts, burned = int(time.time()), 0
    for resolved, entries in by_store.items():
        with Win32NamedMutex(resolved, timeout_ms=5000, is_path=True):
            active = _load_active_nonces(resolved, now_ts)
            for clean_nonce, exp_ts in entries.items():
                if clean_nonce in active:
                    raise TwoPhaseCommitError(f"Replay rilevato per token governance (nonce {clean_nonce[:8]} gia consumato).")
                active[clean_nonce] = exp_ts
                burned += 1
            _atomic_write_nonces(resolved, active)
    pending.clear()
    return burned


def _record_nonce_consumption(clean_nonce: str, expiry_ts: int, resolved: Path, active: Dict[str, int], batch_seen: Optional[Set[str]]) -> None:
    pending = _PENDING_BATCH_NONCES.get()
    if _DEFER_BATCH_NONCE_COMMIT.get() and pending is not None:
        pending[clean_nonce] = (expiry_ts, resolved)
    else:
        active[clean_nonce] = expiry_ts
        _atomic_write_nonces(resolved, active)
    if batch_seen is not None:
        batch_seen.add(clean_nonce)


def verify_or_consume_governance_nonce(
    nonce_hex: str, ts_int: int, ttl_sec: int, *, check_replay: bool = False,
    consume: bool = False, store_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Verifica o consuma (immediato o differito Goldilocks) il nonce anti-replay HMAC."""
    if not check_replay and not consume:
        return True
    clean_nonce = str(nonce_hex or "").strip().lower()
    if not clean_nonce:
        raise TwoPhaseCommitError("Nonce governance vuoto durante controllo anti-replay.")
    batch_seen = _ACTIVE_BATCH_NONCES.get()
    if batch_seen is not None and clean_nonce in batch_seen:
        return True

    resolved = resolve_governance_nonce_store_path(store_path)
    now_ts = int(time.time())
    expiry_ts = max(now_ts + 1, int(ts_int) + max(1, int(ttl_sec)) + _NONCE_CLOCK_SKEW_SEC)
    with Win32NamedMutex(resolved, timeout_ms=5000, is_path=True):
        active = _load_active_nonces(resolved, now_ts)
        if clean_nonce in active:
            raise TwoPhaseCommitError(f"Replay rilevato per token governance (nonce {clean_nonce[:8]} gia consumato).")
        if consume:
            _record_nonce_consumption(clean_nonce, expiry_ts, resolved, active, batch_seen)
    return True

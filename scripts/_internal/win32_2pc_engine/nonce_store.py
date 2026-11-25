# -*- coding: utf-8 -*-
"""
Store persistente anti-replay per nonce HMAC governance sotto Win32NamedMutex.
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
from typing import Dict, Iterator, Optional, Set, Union

from _internal.win32_2pc_engine.constants import TwoPhaseCommitError
from _internal.win32_2pc_engine.io_and_paths import _replace_with_retry
from _internal.win32_2pc_engine.mutex import Win32NamedMutex

_NONCE_CLOCK_SKEW_SEC = 60
_ACTIVE_BATCH_NONCES: contextvars.ContextVar[Optional[Set[str]]] = contextvars.ContextVar("nk_gov_batch_nonces", default=None)
_ACTIVE_NONCE_ENFORCE: contextvars.ContextVar[bool] = contextvars.ContextVar("nk_gov_nonce_enforce", default=False)


def resolve_governance_nonce_store_path(store_path: Optional[Union[str, Path]] = None) -> Path:
    """Risolve il percorso esterno del registro nonce anti-replay in LOCALAPPDATA o temp."""
    if store_path is not None:
        return Path(store_path).resolve()
    env_override = os.environ.get("NK_GOVERNANCE_NONCE_STORE_PATH", "").strip()
    if env_override:
        return Path(env_override).resolve()
    base_dir = os.environ.get("LOCALAPPDATA", "").strip() or tempfile.gettempdir()
    return (Path(base_dir) / "nk_hub" / "governance_nonces.json").resolve()


def is_nonce_replay_enforced(*, token_version: str = "v1", consume_nonce: bool = False, active_session: bool = False) -> bool:
    """True se anti-replay va attivato per versione v2, flag esplicito, sessione o env."""
    env_flag = os.environ.get("NK_GOVERNANCE_NONCE_ENFORCE", "").strip() == "1"
    ver = str(token_version or "v1").strip().lower()
    return bool(consume_nonce or ver == "v2" or active_session or _ACTIVE_NONCE_ENFORCE.get() or env_flag)


@contextlib.contextmanager
def governance_batch_nonce_scope(enforce: bool = False) -> Iterator[None]:
    """Consente riutilizzo controllato dello stesso nonce solo entro un singolo batch 2PC."""
    tok_nonces = _ACTIVE_BATCH_NONCES.set(set())
    tok_enforce = _ACTIVE_NONCE_ENFORCE.set(bool(enforce) or _ACTIVE_NONCE_ENFORCE.get())
    try:
        yield
    finally:
        _ACTIVE_NONCE_ENFORCE.reset(tok_enforce)
        _ACTIVE_BATCH_NONCES.reset(tok_nonces)


def _reject_nonce_json_constant(raw_const: str) -> None:
    """Rifiuta costanti JSON non standard (NaN, Infinity, -Infinity)."""
    raise TwoPhaseCommitError(f"Costante JSON non valida nello store nonce governance: {raw_const!r}")


def _validate_nonce_expiry_entry(k: Any, exp: Any, resolved: Path) -> int:
    """Convalida una singola coppia (nonce, expiry) rifiutando bool, stringhe e NaN/Inf."""
    if not isinstance(k, str) or isinstance(exp, bool) or not isinstance(exp, (int, float)):
        raise TwoPhaseCommitError(f"Voce nonce governance non valida o corrotta ({resolved}): key={k!r}")
    exp_f = float(exp)
    if not math.isfinite(exp_f):
        raise TwoPhaseCommitError(f"Scadenza nonce non finita ({resolved}): key={k!r}")
    return int(exp_f)


def _load_active_nonces(resolved: Path, now_ts: int) -> Dict[str, int]:
    """Carica i nonce non scaduti dal file JSON in fail-closed."""
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
    """Scrive atomicamente i nonce attivi su file tramite swap sicuro nello stesso parent."""
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


def verify_or_consume_governance_nonce(
    nonce_hex: str, ts_int: int, ttl_sec: int, *, check_replay: bool = False,
    consume: bool = False, store_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Verifica o consuma il nonce anti-replay in LOCALAPPDATA/nk_hub/governance_nonces.json."""
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
            active[clean_nonce] = expiry_ts
            _atomic_write_nonces(resolved, active)
            if batch_seen is not None:
                batch_seen.add(clean_nonce)
    return True

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autenticazione crittografica HMAC-SHA256 esterna per override di governance 2PC."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from _internal.nk_common.staging_manifest import is_valid_sha256_hex

from .constants import TwoPhaseCommitError, validate_override_reason
from .nonce_store import is_nonce_replay_enforced, verify_or_consume_governance_nonce

_TOKEN_VERSION = "v1"
_SUPPORTED_TOKEN_VERSIONS = frozenset(("v1", "v2"))
_DEFAULT_TTL_SEC = 900
_MAX_FUTURE_SKEW_SEC = 30
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def _is_hex_str(val: str) -> bool:
    """Verifica che val sia una stringa esadecimale non vuota."""
    return bool(val) and all(ch in _HEX_CHARS for ch in val)


def resolve_governance_hmac_key_path(key_path: Optional[Union[str, Path]] = None) -> Path:
    """Risolve il percorso esterno della chiave HMAC fuori dal repository."""
    if key_path is not None and str(key_path).strip():
        return Path(str(key_path).strip()).expanduser().resolve()
    env_path = os.environ.get("NK_GOVERNANCE_HMAC_KEY_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    base_dir = os.environ.get("LOCALAPPDATA", "").strip() or tempfile.gettempdir()
    return (Path(base_dir) / "nk_hub" / "governance_hmac.key").resolve()


def _read_hmac_key_bytes(resolved_path: Path) -> bytes:
    """Legge la chiave HMAC fail-closed se assente o vuota."""
    if not resolved_path.exists() or not resolved_path.is_file():
        raise TwoPhaseCommitError(f"Chiave HMAC governance assente: {resolved_path}")
    raw = resolved_path.read_bytes()
    if not raw.strip():
        raise TwoPhaseCommitError(f"Chiave HMAC governance vuota o non valida: {resolved_path}")
    return raw


def ensure_governance_hmac_key(key_path: Optional[Union[str, Path]] = None) -> Path:
    """Crea la chiave HMAC esterna solo su invocazione esplicita dell'operatore."""
    resolved = resolve_governance_hmac_key_path(key_path)
    if resolved.exists():
        _read_hmac_key_bytes(resolved)
        return resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(secrets.token_hex(32).encode("ascii"))
    return resolved


def _validate_nonce_and_ts(ts: Optional[int], nonce: Optional[str]) -> Tuple[int, str]:
    """Normalizza e valida timestamp intero e nonce esadecimale."""
    if ts is None:
        eff_ts = int(time.time())
    elif isinstance(ts, bool):
        raise TwoPhaseCommitError("Timestamp token governance non valido.")
    else:
        eff_ts = int(ts)
    eff_nonce = secrets.token_hex(16) if nonce is None else str(nonce).strip()
    if not _is_hex_str(eff_nonce):
        raise TwoPhaseCommitError("Nonce esadecimale token governance non valido.")
    return eff_ts, eff_nonce.lower()


def _normalize_token_version(token_version: str) -> str:
    """Valida e normalizza la versione del token governance (v1 o v2)."""
    ver = str(token_version or _TOKEN_VERSION).strip().lower()
    if ver not in _SUPPORTED_TOKEN_VERSIONS:
        raise TwoPhaseCommitError(f"Versione token governance non supportata: {ver}")
    return ver

def _build_token_payload(
    ver: str,
    ts_val: int,
    nonce_val: str,
    clean_reason: str,
    manifest_sha256: Optional[str] = None,
) -> bytes:
    """Costruisce il payload canonico da firmare in HMAC-SHA256."""
    if ver == "v1":
        return f"{ts_val}:{nonce_val}:{clean_reason}".encode("utf-8")
    if manifest_sha256:
        return f"{ver}:{ts_val}:{nonce_val}:{clean_reason}:{manifest_sha256}".encode("utf-8")
    return f"{ver}:{ts_val}:{nonce_val}:{clean_reason}".encode("utf-8")


def _normalize_bound_manifest_sha(ver: str, staging_manifest_sha256: Optional[str]) -> Optional[str]:
    """Valida il binding staging_manifest_sha256 per token governance v2."""
    if staging_manifest_sha256 is None:
        return None
    if ver != "v2":
        raise TwoPhaseCommitError("Il binding staging_manifest_sha256 richiede token_version='v2'.")
    if not is_valid_sha256_hex(staging_manifest_sha256):
        raise TwoPhaseCommitError("staging_manifest_sha256 non valido per token governance v2.")
    return staging_manifest_sha256.strip().lower()


def mint_governance_token(
    reason: str,
    key_path: Optional[Union[str, Path]] = None,
    ts: Optional[int] = None,
    nonce: Optional[str] = None,
    token_version: str = "v1",
    staging_manifest_sha256: Optional[str] = None,
) -> str:
    """Genera un token firmato <v1|v2>:<ts>:<nonce_hex>[:<manifest_sha256>]:<hmac_sha256_hex>."""
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        raise TwoPhaseCommitError("Override reason mancante per mint token governance.")
    ver = _normalize_token_version(token_version)
    clean_manifest = _normalize_bound_manifest_sha(ver, staging_manifest_sha256)
    resolved = resolve_governance_hmac_key_path(key_path)
    if not resolved.exists():
        resolved = ensure_governance_hmac_key(resolved)
    eff_ts, eff_nonce = _validate_nonce_and_ts(ts, nonce)
    payload_bytes = _build_token_payload(ver, eff_ts, eff_nonce, clean_reason, clean_manifest)
    sig = hmac.new(_read_hmac_key_bytes(resolved), payload_bytes, hashlib.sha256).hexdigest()
    suffix = f"{clean_manifest}:{sig}" if clean_manifest is not None else sig
    return f"{ver}:{eff_ts}:{eff_nonce}:{suffix}"


def _assert_hex_token_parts(nonce_s: str, sig_s: str) -> None:
    """Valida formato esadecimale di nonce e firma HMAC a 64 caratteri."""
    if not _is_hex_str(nonce_s) or not is_valid_sha256_hex(sig_s):
        raise TwoPhaseCommitError("Token governance HMAC con nonce o firma non valida.")


def _extract_v2_manifest_part(parts: List[str], ver: str) -> Optional[str]:
    """Estrae e convalida l'eventuale quinto campo staging_manifest_sha256 su token v2."""
    if len(parts) != 5:
        return None
    if ver != "v2" or not is_valid_sha256_hex(parts[3]):
        raise TwoPhaseCommitError("Token governance HMAC v2 con binding manifest SHA-256 non valido.")
    return parts[3].lower()


def _parse_token_parts(token: Optional[str]) -> Tuple[str, int, str, Optional[str], str]:
    """Analizza il token <v1|v2>:<ts>:<nonce_hex>[:<manifest_sha256>]:<hmac_sha256_hex> in fail-closed."""
    parts: List[str] = str(token or "").strip().split(":")
    ver = parts[0].lower() if parts else ""
    if len(parts) not in (4, 5) or ver not in _SUPPORTED_TOKEN_VERSIONS or not parts[1].isdigit():
        raise TwoPhaseCommitError("Token governance HMAC assente o malformato (--governance-token).")
    bound_manifest = _extract_v2_manifest_part(parts, ver)
    sig_s = parts[-1].lower()
    _assert_hex_token_parts(parts[2], sig_s)
    return ver, int(parts[1]), parts[2].lower(), bound_manifest, sig_s


def _verify_bound_manifest_match(
    bound_manifest: Optional[str], staging_manifest_sha256: Optional[str]
) -> None:
    """Verifica la corrispondenza fail-closed del binding staging_manifest_sha256 su token v2."""
    if bound_manifest is None:
        return
    exp_m = str(staging_manifest_sha256 or "").strip().lower()
    if not is_valid_sha256_hex(exp_m) or not hmac.compare_digest(bound_manifest, exp_m):
        raise TwoPhaseCommitError("Token governance v2 vincolato a staging_manifest_sha256 diverso o assente.")


def _validate_token_window(ts_int: int, ttl_sec: int) -> None:
    """Verifica finestra temporale TTL e tolleranza clock skew futuro (<= 30s)."""
    if isinstance(ttl_sec, bool) or int(ttl_sec) <= 0:
        raise TwoPhaseCommitError("TTL token governance non valido.")
    now = int(time.time())
    if ts_int - now > _MAX_FUTURE_SKEW_SEC:
        raise TwoPhaseCommitError("Token governance HMAC nel futuro (> 30s).")
    if now - ts_int > int(ttl_sec):
        raise TwoPhaseCommitError("Token governance HMAC scaduto.")


def verify_governance_token(
    token: Optional[str],
    reason: Optional[str],
    key_path: Optional[Union[str, Path]] = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
    consume_nonce: bool = False,
    staging_manifest_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Verifica in fail-closed firma HMAC-SHA256, TTL, eventuale manifest SHA-256 e anti-replay nonce."""
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        raise TwoPhaseCommitError("Override reason mancante per verifica token governance.")
    ver, ts_int, nonce_hex, bound_manifest, sig_hex = _parse_token_parts(token)
    resolved = resolve_governance_hmac_key_path(key_path)
    key_bytes = _read_hmac_key_bytes(resolved)
    _validate_token_window(ts_int, ttl_sec)
    payload_bytes = _build_token_payload(ver, ts_int, nonce_hex, clean_reason, bound_manifest)
    expected_sig = hmac.new(key_bytes, payload_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig_hex):
        raise TwoPhaseCommitError("Firma HMAC token governance non valida.")
    _verify_bound_manifest_match(bound_manifest, staging_manifest_sha256)
    check_replay = is_nonce_replay_enforced(token_version=ver, consume_nonce=consume_nonce)
    verify_or_consume_governance_nonce(nonce_hex, ts_int, ttl_sec, check_replay=check_replay, consume=bool(consume_nonce))
    result: Dict[str, Any] = {"valid": True, "version": ver, "ts": ts_int, "nonce": nonce_hex, "reason": clean_reason, "key_path": str(resolved)}
    return {**result, "staging_manifest_sha256": bound_manifest} if bound_manifest is not None else result


def authorize_governance_override(
    reason: Optional[str],
    token: Optional[str],
    context_path: str,
    key_path: Optional[Union[str, Path]] = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
    consume_nonce: bool = False,
    staging_manifest_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Valida prima motivo >= 8 char e poi token HMAC attivando anti-replay quando richiesto."""
    clean_reason = validate_override_reason(reason, context_path)
    eff_token = os.environ.get("NK_GOVERNANCE_TOKEN") if token is None else token
    tok_ver = str(eff_token or "").strip().split(":", 1)[0].lower()
    return verify_governance_token(
        eff_token,
        clean_reason,
        key_path=key_path,
        ttl_sec=ttl_sec,
        consume_nonce=is_nonce_replay_enforced(token_version=tok_ver, consume_nonce=consume_nonce),
        staging_manifest_sha256=staging_manifest_sha256,
    )

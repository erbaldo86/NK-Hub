# -*- coding: utf-8 -*-
"""
Guardia sessioni Tensor-RSI attive e finalizzazione post-commit per il promoter 2PC.
Modulo: scripts/_internal/win32_2pc_engine/tensor_session_guard.py.
@domain_id: DOM-01
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from _internal.nk_common.staging_manifest import (
    canonical_json_bytes,
    compute_payloads_manifest_sha256,
    compute_staging_manifest_sha256 as _ssot_compute_staging_manifest_sha256,
    is_reparse_entry,
    is_valid_sha256_hex,
    no_dup_pairs_hook,
    safe_finite_float,
)
from _internal.nk_common.win32_mutex import get_tensor_active_mutex_name

from . import constants as _consts
from . import staging_guards as _guards
from .constants import TwoPhaseCommitError
from .io_and_paths import _is_reparse_point, _unlink_with_retry, _win_long_path
from .mutex import Win32NamedMutex

_MAX_ACTIVE_SKEW_SEC = 30
_PROTECTED_PRUNE_DIRS = frozenset({
    "",
    ".",
    ".agents",
    ".agents/plugins",
    ".agents/plugins/nk-gate",
    ".agents/skills",
    ".agents/agents",
    "scripts",
    "tests",
    "nk_tracking",
    "nk_tracking/reports_and_briefs",
    "nk_genome",
})


def compute_staging_manifest_sha256(staging_dir: Path) -> str:
    """Calcola SHA-256 canonico di .staging/ delegando al manifest SSOT e propagando TwoPhaseCommitError."""
    try:
        return _ssot_compute_staging_manifest_sha256(Path(staging_dir), reject_symlinks=True)
    except (OSError, ValueError) as exc:
        raise TwoPhaseCommitError(f"Errore calcolo manifest SHA-256 in staging: {exc}") from exc


def _resolve_tensor_hmac_key_path() -> Path:
    """Risolve il percorso esterno della chiave HMAC Tensor-RSI fuori dal repository."""
    env_path = os.environ.get("NK_TENSOR_RSI_HMAC_KEY_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    base_dir = os.environ.get("LOCALAPPDATA", "").strip() or tempfile.gettempdir()
    return (Path(base_dir) / "nk_hub" / "tensor_rsi_hmac.key").resolve()


def _read_tensor_hmac_key() -> bytes:
    """Legge la chiave HMAC Tensor-RSI fail-closed se assente, symlink o vuota."""
    key_path = _resolve_tensor_hmac_key_path()
    if key_path.is_symlink() or is_reparse_entry(key_path) or not key_path.is_file():
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: chiave HMAC Tensor-RSI assente ({key_path}).")
    raw = key_path.read_bytes().strip()
    if not raw:
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: chiave HMAC Tensor-RSI vuota ({key_path}).")
    return raw


def _reject_active_json_const(val: str) -> Any:
    """Rifiuta costanti JSON non standard (NaN, Infinity) in ACTIVE.json."""
    raise TwoPhaseCommitError(f"Costante JSON non valida in ACTIVE.json: {val!r}")


def _strict_loads_active_json(raw_text: str, active_path: Path) -> Dict[str, Any]:
    """Decodifica ACTIVE.json in modalita strict rifiutando chiavi duplicate e NaN."""
    try:
        payload = json.loads(
            raw_text,
            object_pairs_hook=lambda pairs: no_dup_pairs_hook(pairs, exc_cls=TwoPhaseCommitError),
            parse_constant=_reject_active_json_const,
        )
    except TwoPhaseCommitError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: ACTIVE.json illeggibile ({active_path}): {exc}") from exc
    if not isinstance(payload, dict):
        raise TwoPhaseCommitError("Promozione 2PC bloccata: ACTIVE.json deve contenere un oggetto JSON.")
    return payload


def _assert_active_path_not_reparse(active_path: Path) -> None:
    """Blocca symlink, junction e reparse point su ACTIVE.json o sua parent prima di exists()."""
    if active_path.is_symlink() or is_reparse_entry(active_path) or is_reparse_entry(active_path.parent):
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: symlink o reparse point rilevato su {active_path}.")


def _verify_active_hmac_and_ttl(payload: Dict[str, Any], *, now_ts: Optional[float] = None) -> None:
    """Verifica firma HMAC-SHA256 canonica e scadenza TTL (expires_at) di ACTIVE.json fail-closed."""
    sig_hex = payload.get("hmac_sha256")
    if not is_valid_sha256_hex(sig_hex):
        raise TwoPhaseCommitError("Promozione 2PC bloccata: firma hmac_sha256 mancante o non valida in ACTIVE.json.")
    unsigned_body = {k: v for k, v in payload.items() if k != "hmac_sha256"}
    canon_bytes = canonical_json_bytes(unsigned_body, exc_cls=TwoPhaseCommitError)
    expected_sig = hmac.new(_read_tensor_hmac_key(), canon_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, str(sig_hex).lower()):
        raise TwoPhaseCommitError("Promozione 2PC bloccata: verifica firma HMAC-SHA256 di ACTIVE.json fallita.")

    eff_now = time.time() if now_ts is None else float(now_ts)
    expires_at = safe_finite_float(payload.get("expires_at"), default=-1.0)
    if expires_at <= 0.0:
        raise TwoPhaseCommitError("Promozione 2PC bloccata: campo expires_at mancante o non valido in ACTIVE.json.")
    if eff_now > expires_at:
        raise TwoPhaseCommitError("Promozione 2PC bloccata: sessione Tensor-RSI scaduta (expires_at superato).")
    if "issued_at" in payload:
        issued_at = safe_finite_float(payload.get("issued_at"), default=-1.0)
        if issued_at <= 0.0 or issued_at > eff_now + _MAX_ACTIVE_SKEW_SEC:
            raise TwoPhaseCommitError("Promozione 2PC bloccata: issued_at non valido o nel futuro in ACTIVE.json.")


def _read_active_regular_text(active_path: Path) -> Optional[str]:
    """Verifica symlink/reparse e legge il testo di ACTIVE.json oppure restituisce None se assente."""
    _assert_active_path_not_reparse(active_path)
    active_lp = _win_long_path(active_path)
    if not active_lp.exists():
        return None
    if not active_lp.is_file():
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: ACTIVE.json non e un file regolare ({active_path}).")
    try:
        return active_lp.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: impossibile leggere {active_path}: {exc}") from exc


def _validate_active_session_body(
    raw_text: str, active_path: Path, staging_dir: Path, precomputed_sha: Optional[str]
) -> None:
    """Convalida schema strict, firma HMAC, TTL, accepted e staging_manifest_sha256."""
    payload = _strict_loads_active_json(raw_text, active_path)
    _verify_active_hmac_and_ttl(payload)
    if payload.get("accepted") is not True:
        sess_id = payload.get("session_id") or "UNKNOWN"
        raise TwoPhaseCommitError(f"Promozione 2PC bloccata: sessione Tensor-RSI '{sess_id}' non approvata (accepted != True).")
    expected_sha = str(payload.get("staging_manifest_sha256") or "").strip().lower()
    actual_sha = (precomputed_sha or compute_staging_manifest_sha256(staging_dir)).strip().lower()
    if not is_valid_sha256_hex(expected_sha) or not hmac.compare_digest(expected_sha, actual_sha):
        raise TwoPhaseCommitError("Promozione 2PC bloccata: staging_manifest_sha256 in ACTIVE.json diverso dallo staging corrente.")


def _verify_active_inside_mutex(
    active_path: Path, staging_dir: Path, precomputed_sha: Optional[str]
) -> bool:
    """Legge e verifica ACTIVE.json sotto il lock mutex gia acquisito."""
    raw_text = _read_active_regular_text(active_path)
    if raw_text is None:
        return False
    _validate_active_session_body(raw_text, active_path, staging_dir, precomputed_sha)
    return True


def verify_active_tensor_session(
    root: Path, staging_dir: Path, *, precomputed_sha: Optional[str] = None
) -> bool:
    """Verifica sotto mutex ACTIVE.json (reparse, HMAC, TTL, accepted, manifest SHA-256)."""
    active_path = root / "nk_tracking" / "tensor_sessions" / "ACTIVE.json"
    with Win32NamedMutex(get_tensor_active_mutex_name(root), timeout_ms=5000, is_path=False):
        return _verify_active_inside_mutex(active_path, staging_dir, precomputed_sha)


def verify_staged_payloads_tensor_session(root: Path, payloads_map: Mapping[str, bytes]) -> bool:
    """Verifica anti-TOCTOU che i byte caricati in memoria corrispondano a staging_manifest_sha256 in ACTIVE.json."""
    try:
        in_memory_sha = compute_payloads_manifest_sha256(payloads_map)
    except ValueError as exc:
        raise TwoPhaseCommitError(f"Errore calcolo manifest payload in memoria: {exc}") from exc
    return verify_active_tensor_session(root, root / ".staging", precomputed_sha=in_memory_sha)


def assert_no_active_tensor_session_for_quarantine(root: Path) -> None:
    """Impedisce a quarantine_staging di cancellare .staging/ mentre esiste ACTIVE.json aperto/attivo."""
    active_path = root / "nk_tracking" / "tensor_sessions" / "ACTIVE.json"
    with Win32NamedMutex(get_tensor_active_mutex_name(root), timeout_ms=5000, is_path=False):
        _assert_active_path_not_reparse(active_path)
        if _win_long_path(active_path).exists():
            raise TwoPhaseCommitError(
                "Quarantena staging bloccata: sessione Tensor-RSI aperta in nk_tracking/tensor_sessions/ACTIVE.json; "
                "chiudere o annullare prima la sessione Tensor-RSI."
            )


def close_active_tensor_session_post_commit(root: Path) -> bool:
    """Rimuove ACTIVE.json dopo commit 2PC riuscito sotto Local\\NK_TensorActive_<repo12> evitando stale-lock DoS."""
    active_path = root / "nk_tracking" / "tensor_sessions" / "ACTIVE.json"
    with Win32NamedMutex(get_tensor_active_mutex_name(root), timeout_ms=5000, is_path=False):
        _assert_active_path_not_reparse(active_path)
        active_lp = _win_long_path(active_path)
        if not active_lp.exists():
            return False
        if not active_lp.is_file():
            raise TwoPhaseCommitError(f"Pulizia post-commit bloccata: {active_path} non e un file regolare.")
        _unlink_with_retry(active_path)
        return True


def _resolve_tensor_nonce_enforce(root: Path, staging_dir: Path, enforce_nonce_replay: bool) -> bool:
    """Valida la sessione Tensor attiva e restituisce se attivare l'anti-replay nonce."""
    has_active = verify_active_tensor_session(root, staging_dir)
    return bool(enforce_nonce_replay or has_active)


def _is_safe_prunable_dir(curr: Path, root: Path, real_root: Path) -> bool:
    """Verifica che curr sia interno a root, non protetto e non reparse point."""
    if curr == root or curr == real_root or curr.parent == curr:
        return False
    try:
        rel_dir = curr.relative_to(root).as_posix().lower()
    except ValueError:
        return False
    if rel_dir in _PROTECTED_PRUNE_DIRS or _is_reparse_point(curr):
        return False
    real_curr = Path(os.path.realpath(str(curr)))
    return real_curr != real_root and real_root in real_curr.parents


def _try_remove_empty_dir(curr_lp: Path) -> bool:
    """Rimuove curr_lp solo se esiste come directory reale vuota."""
    if not curr_lp.exists():
        return True
    if not curr_lp.is_dir() or _is_reparse_point(curr_lp):
        return False
    try:
        with os.scandir(curr_lp) as dir_it:
            if next(dir_it, None) is not None:
                return False
        os.rmdir(curr_lp)
    except OSError:
        return False
    return True


def _prune_deleted_parent_dirs(deleted_parents: List[Path], root: Path, real_root: Path) -> None:
    """Rimuove dal basso verso l'alto le cartelle svuotate non protette."""
    for start_parent in sorted(set(deleted_parents), key=lambda p: len(p.parts), reverse=True):
        curr = start_parent
        while _is_safe_prunable_dir(curr, root, real_root):
            if not _try_remove_empty_dir(_win_long_path(curr)):
                break
            curr = curr.parent


def run_git_sync(
    root: Path, committed: List[Dict[str, Any]], deleted: List[str]
) -> bool:
    """Esegue git add e git rm --cached dentro il mutex batch se git e nel PATH."""
    import shutil
    import subprocess

    git_exe = shutil.which("git")
    if not git_exe:
        print(
            "[WARN] Eseguibile 'git' non trovato nel PATH; sincronizzazione Git saltata.",
            file=sys.stderr,
        )
        return False
    try:
        files_to_sync: List[str] = [c["relative_path"] for c in committed]
        if files_to_sync:
            proc_git = subprocess.run(
                [git_exe, "add", "--"] + files_to_sync,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
            )
            ok = proc_git.returncode == 0
        else:
            ok = True
        if deleted:
            subprocess.run(
                [git_exe, "rm", "--cached", "--ignore-unmatch", "--"] + deleted,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
            )
        return ok
    except Exception:
        return False


def _finalize_promotion_records(
    root: Path,
    milestone: Optional[str],
    committed: List[Dict[str, Any]],
    deleted: List[str],
    overridden_paths: List[str],
    governance_override_reason: Optional[str],
    git_sync: bool,
) -> bool:
    """Registra session anchor, eventuale audit override e esegue git sync sotto mutex."""
    tracking_dir = root / "nk_tracking"
    if (tracking_dir.is_dir() or milestone) and (committed or deleted or milestone):
        anchor_fn = _consts._get_facade_attr("record_session_anchor_commit", _guards.record_session_anchor_commit)
        anchor_fn(root, milestone or "2PC_PROMOTE", committed, deleted)

    if overridden_paths:
        audit_fn = _consts._get_facade_attr("record_governance_override_audit", _guards.record_governance_override_audit)
        audit_fn(root, milestone or "2PC_PROMOTE", str(governance_override_reason or ""), overridden_paths)

    return run_git_sync(root, committed, deleted) if git_sync else False

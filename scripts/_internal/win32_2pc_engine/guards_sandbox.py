# -*- coding: utf-8 -*-
"""
Guardie di validazione sandbox e baseline ratchet per il batch 2PC.
Modulo: scripts/_internal/win32_2pc_engine/guards_sandbox.py.
@domain_id: DOM-01
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import constants as _consts
from .constants import TwoPhaseCommitError
from .governance_auth import authorize_governance_override
from .guards_ratchet import _verify_quality_baseline_ratchet
from .io_and_paths import _win_long_path

_BLOCKED_SANDBOX_STATUSES = frozenset(
    ("FAIL", "FAILED", "ERROR", "EXPLOIT_CONFIRMED", "TIMEOUT", "TIMED_OUT", "OOM", "UNMEASURED")
)
_POSITIVE_SANDBOX_STATUSES = frozenset(
    ("PASS", "PASSED", "OK", "CLEAN", "VERIFIED", "CONVERGED_OPTIMAL")
)
_POSITIVE_SANDBOX_OUTCOMES = frozenset(
    ("PASS", "PASSED", "OK", "CLEAN", "BENIGN", "SAFE", "NO_EXPLOIT")
)


def _has_nested_holdout_failure(payload: Dict[str, Any]) -> bool:
    """Valuta l'eventuale sotto-blocco nested holdout_verification del report sandbox."""
    ho = payload.get("holdout_verification")
    if ho is None:
        return False
    if not isinstance(ho, dict):
        return True
    if ho.get("passed") is False or bool(ho.get("mismatches")) or bool(ho.get("errors")):
        return True
    return ho.get("executed") is True and ho.get("passed") is not True


def _has_holdout_failure(payload: Dict[str, Any]) -> bool:
    """Rileva fallimenti holdout in fail-closed (top-level o nested holdout_verification)."""
    if payload.get("holdout_passed") is False or _has_nested_holdout_failure(payload):
        return True
    for key in ("f_holdout", "holdout_failed", "holdout_failures"):
        val = payload.get(key)
        if val is None:
            continue
        if isinstance(val, bool):
            if val:
                return True
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            return True
        if not math.isfinite(num) or num != 0.0:
            return True
    return False


def _has_sandbox_failure_flag(
    payload: Dict[str, Any], status_val: str, outcome_val: str
) -> bool:
    """Rileva flag di fallimento, timeout, OOM, holdout, exit_code != 0 o stati bloccati."""
    if payload.get("passed") is False or payload.get("dast_passed") is False or payload.get("success") is False:
        return True
    if _has_holdout_failure(payload):
        return True
    if payload.get("timed_out") is True or payload.get("memory_exceeded") is True:
        return True
    rc = payload.get("exit_code")
    if isinstance(rc, int) and not isinstance(rc, bool) and rc != 0:
        return True
    return status_val in _BLOCKED_SANDBOX_STATUSES or outcome_val in _BLOCKED_SANDBOX_STATUSES


def _has_positive_sandbox_verdict(
    payload: Dict[str, Any], status_val: str, outcome_val: str
) -> bool:
    """Verifica la presenza di almeno un verdetto positivo esplicito."""
    if payload.get("passed") is True or payload.get("dast_passed") is True or payload.get("success") is True:
        return True
    return status_val in _POSITIVE_SANDBOX_STATUSES or outcome_val in _POSITIVE_SANDBOX_OUTCOMES


def _assert_sandbox_report_payload_valid(payload: Dict[str, Any]) -> None:
    """Verifica che il payload sandbox non sia vuoto, dry-run, fallito o privo di verdetto positivo."""
    if not isinstance(payload, dict) or not payload:
        raise TwoPhaseCommitError("Report sandbox vuoto o non valido: atteso dizionario JSON non vuoto.")
    status_val = str(payload.get("status", "") or "").strip().upper()
    outcome_val = str(payload.get("outcome", "") or "").strip().upper()
    if payload.get("is_dry_run") or payload.get("dry_run") or "DRY_RUN" in status_val or "DRY_RUN" in outcome_val:
        raise TwoPhaseCommitError(
            "Promozione bloccata: report sandbox in modalita dry-run non certificabile."
        )
    if _has_sandbox_failure_flag(payload, status_val, outcome_val) or not _has_positive_sandbox_verdict(payload, status_val, outcome_val):
        raise TwoPhaseCommitError(
            f"Promozione bloccata: report sandbox fallito o privo di verdetto positivo (status={status_val or 'MISSING'})."
        )


def validate_sandbox_report_not_dry_run(
    report: Union[Path, str, Dict[str, Any]],
) -> None:
    """Blocca la promozione 2PC se il report sandbox risulta eseguito in dry-run o fallito."""
    if isinstance(report, (str, Path)):
        report_path = Path(report)
        if not report_path.is_file():
            raise TwoPhaseCommitError(f"Report sandbox assente: {report_path}")
        payload = json.loads(_win_long_path(report_path).read_text(encoding="utf-8-sig"))
    else:
        payload = report

    if not isinstance(payload, dict):
        raise TwoPhaseCommitError("Report sandbox non valido: atteso dizionario JSON.")
    _assert_sandbox_report_payload_valid(payload)


def _validate_sandbox_evidence_in_batch(
    sandbox_report: Optional[Union[str, Path, Dict[str, Any]]],
    staging_files: List[Path],
    staging_dir: Path,
) -> None:
    """Valida l'evidenza sandbox esplicita e gli eventuali report sandbox in staging."""
    dry_run_fn = _consts._get_facade_attr(
        "validate_sandbox_report_not_dry_run",
        validate_sandbox_report_not_dry_run,
    )
    if sandbox_report is not None:
        dry_run_fn(sandbox_report)
    for stg_file in staging_files:
        rel_pos = stg_file.relative_to(staging_dir).as_posix().lower()
        fname = stg_file.name.lower()
        if (
            rel_pos.startswith("nk_tracking/")
            and fname.endswith(".json")
            and (fname.startswith("dast_report") or fname.startswith("sandbox_report"))
        ):
            dry_run_fn(stg_file)


def _build_ratchet_auth_kwargs(
    auth_fn: Any, staging_manifest_sha256: Optional[str]
) -> Dict[str, Any]:
    """Prepara i keyword args opzionali supportati dal delegato authorize_governance_override."""
    if staging_manifest_sha256 is not None and "staging_manifest_sha256" in inspect.signature(auth_fn).parameters:
        return {"staging_manifest_sha256": staging_manifest_sha256}
    return {}


def _enforce_batch_baseline_ratchet(
    root: Path,
    staging_dir: Path,
    staging_files: List[Path],
    verify_baseline: bool,
    allow_governance_override: bool,
    governance_override_reason: Optional[str],
    overridden_paths: List[str],
    governance_token: Optional[str] = None,
    staging_manifest_sha256: Optional[str] = None,
) -> None:
    """Applica il ratchet anti-regressione sul quality_baseline in staging/produzione."""
    stg_bl = staging_dir / "nk_tracking" / "quality_baseline.json"
    has_staged_bl = stg_bl.is_file() and any(
        f.resolve() == stg_bl.resolve() for f in staging_files
    )
    if not verify_baseline and not has_staged_bl:
        return
    dst_bl = root / "nk_tracking" / "quality_baseline.json"
    if not dst_bl.exists() and not stg_bl.exists():
        raise TwoPhaseCommitError(
            f"File quality_baseline.json mancante sia in produzione ({dst_bl}) sia in staging ({stg_bl})."
        )
    ratchet_fn = _consts._get_facade_attr(
        "_verify_quality_baseline_ratchet",
        _verify_quality_baseline_ratchet,
    )
    try:
        if not allow_governance_override:
            ratchet_fn(dst_bl, stg_bl, allow_ratchet_down=False)
            return
        try:
            ratchet_fn(dst_bl, stg_bl, allow_ratchet_down=False)
        except TwoPhaseCommitError:
            auth_fn = _consts._get_facade_attr(
                "authorize_governance_override",
                authorize_governance_override,
            )
            auth_fn(
                governance_override_reason,
                governance_token,
                "nk_tracking/quality_baseline.json",
                **_build_ratchet_auth_kwargs(auth_fn, staging_manifest_sha256),
            )
            ratchet_fn(dst_bl, stg_bl, allow_ratchet_down=True)
            overridden_paths.append("ratchet_down:nk_tracking/quality_baseline.json")
    except TwoPhaseCommitError:
        raise
    except Exception as exc:
        raise TwoPhaseCommitError(
            f"Errore durante la verifica del baseline: {exc}"
        ) from exc

# -*- coding: utf-8 -*-
"""Guardia CAS e Win32 Named Mutex dedicata per nk_tracking/quality_baseline.json."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import repo_path_hash12
from _internal.quality_baseline_manager.constants import _resolve_workspace_root_from_baseline

BASELINE_CAS_CONFLICT: str = "BASELINE_CAS_CONFLICT"


def compute_baseline_file_sha256(baseline_path: Union[str, Path]) -> str:
    """Calcola SHA-256 grezzo di quality_baseline.json o string vuota se assente."""
    target = Path(baseline_path)
    if is_reparse_entry(target) or is_reparse_entry(target.parent):
        raise OSError(f"Reparse point vietato su {target}")
    if not target.exists():
        return ""
    if not target.is_file():
        raise OSError(f"Baseline path non regolare: {target}")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def baseline_mutex(baseline_path: Union[str, Path], *, wait_ms: int = 5000) -> FailClosedNamedMutex:
    """Restituisce il mutex Win32 dedicato Local\\NK_QualityBaseline_<repo12>."""
    ws_root = _resolve_workspace_root_from_baseline(str(baseline_path))
    return FailClosedNamedMutex(f"Local\\NK_QualityBaseline_{repo_path_hash12(ws_root)}", wait_ms=wait_ms)


def check_baseline_cas(
    baseline_path: Union[str, Path],
    expected_baseline_sha256: Optional[str],
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Verifica Compare-And-Swap su quality_baseline.json prima di aggiornare in produzione."""
    actual_sha = compute_baseline_file_sha256(baseline_path)
    if expected_baseline_sha256 is None:
        return True, actual_sha, None
    exp_clean = str(expected_baseline_sha256).strip().lower()
    if actual_sha and exp_clean and hmac.compare_digest(actual_sha.lower(), exp_clean):
        return True, actual_sha, None
    msg = (
        f"{BASELINE_CAS_CONFLICT}: quality_baseline.json modificato concorrentemente "
        f"(atteso={exp_clean or '<empty>'}, attuale={actual_sha or '<missing>'})."
    )
    err_payload: Dict[str, Any] = {
        "status": "REJECTED",
        "verdict": "FAIL",
        "error_code": BASELINE_CAS_CONFLICT,
        "expected_baseline_sha256": exp_clean,
        "actual_baseline_sha256": actual_sha,
        "message": msg,
        "regressions": [
            {
                "metric": "__baseline_cas__",
                "baseline_value": exp_clean,
                "current_value": actual_sha,
                "error_code": BASELINE_CAS_CONFLICT,
                "message": msg,
            }
        ],
    }
    return False, actual_sha, err_payload

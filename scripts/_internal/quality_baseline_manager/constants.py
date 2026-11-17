# -*- coding: utf-8 -*-
"""Costanti, I/O atomico baseline e verifica SHA-256 di oracle_lock.json."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.constants import VERSION
from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.io import atomic_write_json

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_FACADE_MOD_NAMES: Tuple[str, ...] = (
    "quality_baseline_manager",
    "scripts.quality_baseline_manager",
)

BASELINE_FILENAME = "quality_baseline.json"
BASELINE_SCHEMA_VERSION = VERSION
DEFAULT_BASELINE_VERSION = BASELINE_SCHEMA_VERSION
MIN_GOLDEN_TESTS_FLOOR = 93
CONSTITUTIONAL_GOLDEN_FLOOR = MIN_GOLDEN_TESTS_FLOOR

RECALIBRATED_COUNT_KEYS = {
    "total_golden_tests",
    "unit_tests_total",
    "unit_tests_passed",
}

LOWER_IS_BETTER_KEYS = {
    "sast_critical",
    "sast_critical_violations",
    "rsi_residual_delta",
    "failed_tests",
    "tests_failed",
    "delta_k",
    "vulnerabilities",
    "errors",
    "harness_token_overhead_pct",
    "pytest_duration_s",
}


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


def load_baseline(baseline_path: str) -> dict:
    """Carica il file baseline JSON e restituisce None solo se il file non esiste."""
    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(
                "Il contenuto di quality_baseline.json deve essere un dizionario."
            )
        return data
    except FileNotFoundError:
        return None  # type: ignore[return-value]


def create_default_baseline(project_name: str, metrics: dict) -> dict:
    """Crea la struttura iniziale di quality_baseline.json al primo commit."""
    now_iso = datetime.now().isoformat()
    normalized_metrics: Dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            normalized_metrics[k] = v
        else:
            default_dir = (
                "lower_is_better" if k in LOWER_IS_BETTER_KEYS else "higher_is_better"
            )
            normalized_metrics[k] = {"value": v, "direction": default_dir}

    return {
        "_version": DEFAULT_BASELINE_VERSION,
        "project": project_name,
        "baseline_date": now_iso,
        "last_updated": now_iso,
        "metrics": normalized_metrics,
        "ratchet_rule": "no_metric_may_worsen",
        "history": [{"timestamp": now_iso, "metrics": metrics}],
    }


def _atomic_write_baseline(baseline_path: str, data: dict) -> None:
    """Scrive atomicamente quality_baseline.json tramite nk_common.io.atomic_write_json."""
    abs_path = os.path.abspath(baseline_path)
    write_fn = _facade_attr("atomic_write_json", atomic_write_json)
    ok, err_msg = write_fn(abs_path, data, indent=2, ensure_ascii=True)
    if not ok:
        raise PermissionError(
            f"Impossibile scrivere atomicamente {abs_path}: {err_msg}"
        )


def _extract_numeric_metric(metrics: dict, *keys: str) -> Optional[float]:
    """Estrae il primo valore numerico disponibile per una lista di chiavi sinonime."""
    for key in keys:
        if key in metrics:
            raw = metrics[key]
            val = raw.get("value") if isinstance(raw, dict) else raw
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return float(val)
    return None


def _is_valid_gt68_recalibration(current_metrics: dict) -> bool:
    """Disabilita permanentemente ogni esenzione GT-68 o flag _recalibrated."""
    _ = current_metrics
    return False


def _resolve_workspace_root_from_baseline(baseline_path: str) -> Path:
    """Risolve la root del workspace partendo dal percorso di quality_baseline.json."""
    b_file = Path(baseline_path).resolve()
    if b_file.parent.name == "nk_tracking":
        return (
            b_file.parent.parent.parent
            if b_file.parent.parent.name == ".staging"
            else b_file.parent.parent
        )
    s_dir = Path(_facade_attr("_scripts_dir", _scripts_dir)).resolve()
    return s_dir.parent.parent if s_dir.parent.name == ".staging" else s_dir.parent


def _resolve_default_baseline_path() -> str:
    """Risolve il percorso predefinito di quality_baseline.json nel workspace."""
    s_dir = Path(_facade_attr("_scripts_dir", _scripts_dir)).resolve()
    root_dir = s_dir.parent.parent if s_dir.parent.name == ".staging" else s_dir.parent
    staging_cand = root_dir / ".staging" / "nk_tracking" / BASELINE_FILENAME
    prod_cand = root_dir / "nk_tracking" / BASELINE_FILENAME
    if staging_cand.exists():
        return str(staging_cand)
    return str(prod_cand)


def _is_hex_sha256(val: Any) -> bool:
    """Restituisce True se il valore e un digest SHA-256 esadecimale a 64 caratteri."""
    if not isinstance(val, str):
        return False
    return len(val) == 64 and all(c in "0123456789abcdefABCDEF" for c in val)


def _verify_oracle_lock_coherence(baseline_path: str) -> list:
    """Verifica esistenza fisica, digest SHA-256 e combined_sha256 in oracle_lock.json."""
    b_file = Path(baseline_path).resolve()
    if b_file.parent.name == "nk_tracking":
        ws_root = (
            b_file.parent.parent.parent
            if b_file.parent.parent.name == ".staging"
            else b_file.parent.parent
        )
    else:
        ws_root = b_file.parent

    lock_file = None
    for cand in (
        ws_root / "nk_tracking" / "oracle_lock.json",
        b_file.parent / "oracle_lock.json",
    ):
        if cand.is_file():
            lock_file = cand
            break
    if lock_file is None:
        return []

    anomalies = []
    try:
        lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
        if not isinstance(lock_data, dict):
            return [
                {
                    "metric": "oracle_lock_integrity",
                    "baseline_value": "VALID_DICT",
                    "current_value": "INVALID_ROOT",
                    "direction": "higher_is_better",
                    "message": "Il file oracle_lock.json non contiene un dizionario valido.",
                }
            ]

        locked_items: List[Tuple[str, Any]] = []
        raw_locked = lock_data.get("locked_files")
        if isinstance(raw_locked, dict):
            locked_items.extend((str(k), v) for k, v in raw_locked.items())
        elif isinstance(raw_locked, list):
            locked_items.extend((str(item), None) for item in raw_locked)

        raw_files = lock_data.get("files")
        if isinstance(raw_files, dict):
            locked_items.extend((str(k), v) for k, v in raw_files.items())
        elif isinstance(raw_files, list):
            locked_items.extend((str(item), None) for item in raw_files)

        lock_target_raw = lock_data.get("target")
        lock_target: Optional[Path] = None
        if isinstance(lock_target_raw, str) and lock_target_raw.strip():
            cand_lt = Path(lock_target_raw).resolve()
            if cand_lt == ws_root or ws_root in cand_lt.parents:
                lock_target = cand_lt

        cur_effective_map: Dict[str, str] = {}
        had_file_issue = False
        for rel_entry, expected_sha in locked_items:
            raw_cands: List[Path] = []
            if lock_target is not None:
                raw_cands.append((lock_target / rel_entry).resolve())
            raw_cands.extend(
                [
                    (ws_root / "tests" / rel_entry).resolve(),
                    (ws_root / rel_entry).resolve(),
                    (ws_root / ".staging" / rel_entry).resolve(),
                ]
            )
            target_file: Optional[Path] = None
            for cand in raw_cands:
                if (cand == ws_root or ws_root in cand.parents) and cand.is_file():
                    target_file = cand
                    break

            if target_file is None:
                had_file_issue = True
                anomalies.append(
                    {
                        "metric": "oracle_lock_integrity",
                        "baseline_value": "PRESENT",
                        "current_value": "MISSING",
                        "direction": "higher_is_better",
                        "message": f"File registrato in oracle_lock.json mancante su disco: {rel_entry}",
                    }
                )
                continue

            in_files_dict = isinstance(raw_files, dict) and rel_entry in raw_files
            in_locked_dict = isinstance(raw_locked, dict) and rel_entry in raw_locked
            if expected_sha is not None or in_files_dict or in_locked_dict:
                if not _is_hex_sha256(expected_sha):
                    had_file_issue = True
                    anomalies.append(
                        {
                            "metric": "oracle_lock_integrity",
                            "baseline_value": "VALID_64HEX_SHA256",
                            "current_value": repr(expected_sha),
                            "direction": "higher_is_better",
                            "message": f"Digest SHA-256 non valido in oracle_lock.json per {rel_entry}",
                        }
                    )
                else:
                    lf_bytes = target_file.read_bytes().replace(b"\r\n", b"\n")
                    lf_sha = hashlib.sha256(lf_bytes).hexdigest()
                    crlf_sha = hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest()
                    exp_lower = str(expected_sha).lower()
                    if exp_lower not in (lf_sha, crlf_sha):
                        had_file_issue = True
                        anomalies.append(
                            {
                                "metric": "oracle_lock_integrity",
                                "baseline_value": exp_lower,
                                "current_value": lf_sha,
                                "direction": "higher_is_better",
                                "message": f"Mismatch SHA-256 in oracle_lock.json per {rel_entry}",
                            }
                        )
                    elif in_files_dict:
                        cur_effective_map[rel_entry] = str(expected_sha)

        saved_combined = lock_data.get("combined_sha256")
        if isinstance(raw_files, dict) and len(raw_files) > 0 and not had_file_issue:
            if not isinstance(saved_combined, str) or not _is_hex_sha256(saved_combined):
                anomalies.append(
                    {
                        "metric": "oracle_lock_integrity",
                        "field": "combined_sha256",
                        "baseline_value": "VALID_64HEX_SHA256",
                        "current_value": repr(saved_combined),
                        "direction": "higher_is_better",
                        "message": "Campo combined_sha256 mancante o non valido in oracle_lock.json",
                    }
                )
            elif len(cur_effective_map) == len(raw_files):
                computed_combined = hashlib.sha256(
                    json.dumps(cur_effective_map, sort_keys=True).encode("utf-8")
                ).hexdigest()
                if computed_combined != saved_combined.lower():
                    anomalies.append(
                        {
                            "metric": "oracle_lock_integrity",
                            "baseline_value": saved_combined.lower(),
                            "current_value": computed_combined,
                            "direction": "higher_is_better",
                            "message": "Mismatch combined_sha256 in oracle_lock.json",
                        }
                    )
            else:
                anomalies.append(
                    {
                        "metric": "oracle_lock_integrity",
                        "field": "combined_sha256",
                        "baseline_value": len(raw_files),
                        "current_value": len(cur_effective_map),
                        "direction": "higher_is_better",
                        "message": "Copertura mappa SHA-256 incompleta in oracle_lock.json",
                    }
                )
    except Exception as exc:
        anomalies.append(
            {
                "metric": "oracle_lock_integrity",
                "baseline_value": "VALID_JSON",
                "current_value": "CORRUPTED",
                "direction": "higher_is_better",
                "message": f"Errore lettura oracle_lock.json: {exc}",
            }
        )
    return anomalies

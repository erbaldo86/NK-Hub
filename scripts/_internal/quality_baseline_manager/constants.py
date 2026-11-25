# -*- coding: utf-8 -*-
"""Costanti Schema v2, I/O atomico baseline e verifica SHA-256 oracle_lock.json."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from _internal.nk_common.constants import NK_MANDATORY_HUB_LOCKS, VERSION
from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.oracle_lock import verify_oracle_lock_manifest
from _internal.nk_common.staging_manifest import is_valid_sha256_hex

_INTERNAL_PKG_DIR = Path(__file__).resolve().parent
_scripts_dir = _INTERNAL_PKG_DIR.parent.parent
_FACADE_MOD_NAMES: Tuple[str, ...] = ("quality_baseline_manager", "scripts.quality_baseline_manager")

BASELINE_FILENAME = "quality_baseline.json"
BASELINE_SCHEMA_VERSION = VERSION
DEFAULT_BASELINE_VERSION = BASELINE_SCHEMA_VERSION
SCHEMA_VERSION_V2 = 2
MIN_GOLDEN_TESTS_FLOOR = 93
CONSTITUTIONAL_GOLDEN_FLOOR = MIN_GOLDEN_TESTS_FLOOR
MIN_COMBINED_COVERAGE_FLOOR = 85.0
MIN_TRUE_BRANCH_COVERAGE_FLOOR = 75.0
MAX_PYTEST_DURATION_CEIL = 28.0
MAX_PYTEST_FAST_DURATION_CEIL = 8.0

REQUIRED_RATCHET_KEYS: Tuple[str, ...] = (
    "total_golden_tests",
    "unit_tests_total",
    "unit_tests_passed",
    "unit_tests_pass_pct",
    "pass_rate_pct",
    "failed_tests",
    "tests_skipped",
    "pytest_duration_s",
    "statement_coverage_pct",
    "true_branch_coverage_pct",
    "combined_coverage_pct",
    "sast_critical_violations",
)

SCHEMA_V2_LIVE_KEYS: Tuple[str, ...] = REQUIRED_RATCHET_KEYS + ("skills_audited", "crv_macro_phases")

PHANTOM_V1_METRIC_KEYS: FrozenSet[str] = frozenset({
    "pass_rate_percent", "unit_tests_pass_rate", "golden_tests_68",
    "code_duplication_ratio", "cyclomatic_complexity_avg", "anti_crash_rules_enforced",
    "mutation_score_synthetic", "hallucination_rate", "token_efficiency_score",
    "prompt_compliance_score", "agent_alignment_score", "latency_budget_score",
    "synthetic_eval_pass_rate", "doc_drift_score", "vibe_latency_target_ms",
    "legacy_v1_compat_score", "eval_harness_score", "entropy_budget_score",
})

RECALIBRATED_COUNT_KEYS = {"total_golden_tests", "unit_tests_total", "unit_tests_passed"}

LOWER_IS_BETTER_KEYS = {
    "sast_critical", "sast_critical_violations", "rsi_residual_delta",
    "failed_tests", "tests_failed", "tests_skipped", "delta_k",
    "vulnerabilities", "errors", "harness_token_overhead_pct", "pytest_duration_s",
}


def _facade_attr(attr_name: str, default: Any) -> Any:
    """Delega la risoluzione facciata a nk_common.facade_boot.resolve_facade_attr."""
    return resolve_facade_attr(_FACADE_MOD_NAMES, attr_name, default)


def load_baseline(baseline_path: str) -> dict:
    """Carica il baseline JSON (Schema v2 o fallback v1) e restituisce None se assente."""
    try:
        with open(baseline_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Il contenuto di quality_baseline.json deve essere un dizionario.")
        return data
    except FileNotFoundError:
        return None  # type: ignore[return-value]


def extract_baseline_metrics_v1_fallback(baseline: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae la sezione metriche supportando Schema v2 e fallback v1 flat/annidato."""
    if "metrics" in baseline and isinstance(baseline["metrics"], dict):
        return dict(baseline["metrics"])
    return {
        bk: bv
        for bk, bv in baseline.items()
        if isinstance(bv, (int, float, dict))
        and not isinstance(bv, bool)
        and bk not in ("invariants", "metadata", "schema_version", "history")
    }


def _normalize_baseline_entry(k: str, v: Any) -> Any:
    if isinstance(v, dict):
        return v
    default_dir = "lower_is_better" if k in LOWER_IS_BETTER_KEYS else "higher_is_better"
    return {"value": v, "direction": default_dir}


def create_default_baseline(project_name: str, metrics: dict) -> dict:
    """Crea la struttura Schema v2 di quality_baseline.json al primo commit."""
    now_iso = datetime.now().isoformat()
    filtered = {k: v for k, v in metrics.items() if k not in PHANTOM_V1_METRIC_KEYS}
    normalized_metrics = {k: _normalize_baseline_entry(k, v) for k, v in filtered.items()}
    return {
        "_version": DEFAULT_BASELINE_VERSION,
        "schema_version": SCHEMA_VERSION_V2,
        "project": project_name,
        "baseline_date": now_iso,
        "last_updated": now_iso,
        "metrics": normalized_metrics,
        "ratchet_rule": "no_metric_may_worsen",
        "history": [{"timestamp": now_iso, "metrics": filtered}],
    }


def _atomic_write_baseline(baseline_path: str, data: dict) -> None:
    """Scrive atomicamente quality_baseline.json tramite nk_common.io.atomic_write_json."""
    abs_path = os.path.abspath(baseline_path)
    write_fn = _facade_attr("atomic_write_json", atomic_write_json)
    ok, err_msg = write_fn(abs_path, data, indent=2, ensure_ascii=True)
    if not ok:
        raise PermissionError(f"Impossibile scrivere atomicamente {abs_path}: {err_msg}")


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
        return b_file.parent.parent.parent if b_file.parent.parent.name == ".staging" else b_file.parent.parent
    s_dir = Path(_facade_attr("_scripts_dir", _scripts_dir)).resolve()
    return s_dir.parent.parent if s_dir.parent.name == ".staging" else s_dir.parent


def _resolve_default_baseline_path() -> str:
    """Risolve il percorso predefinito di quality_baseline.json nel workspace."""
    s_dir = Path(_facade_attr("_scripts_dir", _scripts_dir)).resolve()
    root_dir = s_dir.parent.parent if s_dir.parent.name == ".staging" else s_dir.parent
    staging_cand = root_dir / ".staging" / "nk_tracking" / BASELINE_FILENAME
    prod_cand = root_dir / "nk_tracking" / BASELINE_FILENAME
    return str(staging_cand if staging_cand.exists() else prod_cand)


_is_hex_sha256 = is_valid_sha256_hex


def _oracle_anom(
    baseline_val: Any, current_val: Any, message: str, field: Optional[str] = None
) -> Dict[str, Any]:
    anom: Dict[str, Any] = {
        "metric": "oracle_lock_integrity",
        "baseline_value": baseline_val,
        "current_value": current_val,
        "direction": "higher_is_better",
        "message": message,
    }
    if field is not None:
        anom["field"] = field
    return anom


def _resolve_locked_target_file(ws_root: Path, lock_target: Optional[Path], rel_entry: str) -> Optional[Path]:
    """Risolve il path fisico bloccato sul disco di produzione senza fallback verso .staging/."""
    cands: List[Path] = []
    if lock_target is not None:
        cands.append((lock_target / rel_entry).resolve())
    cands.extend([
        (ws_root / "tests" / rel_entry).resolve(),
        (ws_root / rel_entry).resolve(),
    ])
    for cand in cands:
        if (cand == ws_root or ws_root in cand.parents) and cand.is_file():
            return cand
    return None


def _check_single_oracle_entry(
    ws_root: Path,
    lock_target: Optional[Path],
    rel_entry: str,
    expected_sha: Any,
    raw_files: Any,
    raw_locked: Any,
    cur_effective_map: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    target_file = _resolve_locked_target_file(ws_root, lock_target, rel_entry)
    if target_file is None:
        return _oracle_anom("PRESENT", "MISSING", f"File registrato in oracle_lock.json mancante su disco: {rel_entry}")
    in_files_dict = isinstance(raw_files, dict) and rel_entry in raw_files
    in_locked_dict = isinstance(raw_locked, dict) and rel_entry in raw_locked
    if expected_sha is None and not in_files_dict and not in_locked_dict:
        return _oracle_anom("VALID_64HEX_SHA256", "MISSING_DIGEST", f"Voce oracle_lock.json priva di digest SHA-256 per {rel_entry}")
    if not _is_hex_sha256(expected_sha):
        return _oracle_anom("VALID_64HEX_SHA256", repr(expected_sha), f"Digest SHA-256 non valido in oracle_lock.json per {rel_entry}")
    lf_bytes = target_file.read_bytes().replace(b"\r\n", b"\n")
    lf_sha = hashlib.sha256(lf_bytes).hexdigest()
    crlf_sha = hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest()
    exp_lower = str(expected_sha).lower()
    if exp_lower not in (lf_sha, crlf_sha):
        return _oracle_anom(exp_lower, lf_sha, f"Mismatch SHA-256 in oracle_lock.json per {rel_entry}")
    if in_files_dict:
        cur_effective_map[rel_entry] = str(expected_sha)
    return None


def _collect_lock_items(lock_data: Dict[str, Any]) -> List[Tuple[str, Any]]:
    items: List[Tuple[str, Any]] = []
    for key in ("locked_files", "files"):
        raw = lock_data.get(key)
        if isinstance(raw, dict):
            items.extend((str(k), v) for k, v in raw.items())
        elif isinstance(raw, list):
            items.extend((str(item), None) for item in raw)
    return items


def _check_combined_lock_sha(
    lock_data: Dict[str, Any], raw_files: Any, cur_effective_map: Dict[str, str], had_file_issue: bool
) -> Optional[Dict[str, Any]]:
    if not (isinstance(raw_files, dict) and len(raw_files) > 0 and not had_file_issue):
        return None
    saved = lock_data.get("combined_sha256")
    if not isinstance(saved, str) or not _is_hex_sha256(saved):
        return _oracle_anom("VALID_64HEX_SHA256", repr(saved), "Campo combined_sha256 mancante o non valido in oracle_lock.json", field="combined_sha256")
    if len(cur_effective_map) != len(raw_files):
        return _oracle_anom(len(raw_files), len(cur_effective_map), "Copertura mappa SHA-256 incompleta in oracle_lock.json", field="combined_sha256")
    computed = hashlib.sha256(json.dumps(cur_effective_map, sort_keys=True).encode("utf-8")).hexdigest()
    if computed != saved.lower():
        return _oracle_anom(saved.lower(), computed, "Mismatch combined_sha256 in oracle_lock.json")
    return None


_MANDATORY_SUB_LOCK_TARGETS: Dict[str, Tuple[str, ...]] = {
    "oracle_lock_holdout.json": ("nk_tracking", "oracle_holdout"),
    "governance_lock.json": ("scripts",),
    "tensor_rsi_lock.json": ("nk_genome", "configs", "tensor_rsi"),
}


def _resolve_lock_target_for_ws(
    lock_name: str, ws_root: Path, raw_target: Any, default_sub: Optional[Path] = None
) -> Optional[Path]:
    """Risolve la directory target del lock entro ws_root tollerando mirror cross-path."""
    if isinstance(raw_target, str) and raw_target.strip():
        cand_lt = Path(raw_target.strip()).resolve()
        if cand_lt == ws_root or ws_root in cand_lt.parents:
            return cand_lt
        raw_low = raw_target.replace("\\", "/").rstrip("/").lower()
        for suf in (
            "nk_tracking/oracle_holdout",
            "nk_genome/configs/tensor_rsi",
            "scripts/_internal/tensor_rsi",
            "tests",
            "scripts",
        ):
            if raw_low.endswith(f"/{suf}") or raw_low == suf:
                cand_mirror = (ws_root / suf).resolve()
                if cand_mirror.exists():
                    return cand_mirror
    sub_parts = _MANDATORY_SUB_LOCK_TARGETS.get(lock_name)
    if sub_parts is not None:
        return ws_root.joinpath(*sub_parts).resolve()
    return default_sub


def _is_full_hub_for_locks(ws_root: Path) -> bool:
    """Riconosce il repo Hub completo per verificare tutti gli NK_MANDATORY_HUB_LOCKS."""
    return (
        (ws_root / ".agents" / "skills").is_dir()
        and (ws_root / "nk_genome").is_dir()
        and (ws_root / "scripts" / "tensor_rsi.py").is_file()
    )


def _read_lock_target_field(lk_path: Path) -> Any:
    """Legge in modo fail-safe il campo opzionale target da un file lock JSON."""
    try:
        raw_obj = json.loads(lk_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return raw_obj.get("target") if isinstance(raw_obj, dict) else None


def _check_mandatory_extra_hub_locks(ws_root: Path) -> List[Dict[str, Any]]:
    """Verifica i manifest aggiuntivi in NK_MANDATORY_HUB_LOCKS tramite verify_oracle_lock_manifest."""
    anoms: List[Dict[str, Any]] = []
    for lock_name in NK_MANDATORY_HUB_LOCKS:
        if lock_name == "oracle_lock.json":
            continue
        lk_path = ws_root / "nk_tracking" / lock_name
        if not lk_path.is_file():
            anoms.append(_oracle_anom("PRESENT", "MISSING", f"File {lock_name} obbligatorio mancante.", field=lock_name))
            continue
        raw_target = _read_lock_target_field(lk_path)
        eff_target = _resolve_lock_target_for_ws(lock_name, ws_root, raw_target, default_sub=ws_root) or ws_root
        res = verify_oracle_lock_manifest(lk_path, eff_target)
        if not res.get("passed"):
            mism = "; ".join(str(x) for x in (res.get("mismatches") or [])[:5])
            anoms.append(_oracle_anom("VERIFIED", str(res.get("status") or "FAIL"), f"Integrita {lock_name} fallita: {mism}", field=lock_name))
    return anoms


def _check_untracked_oracle_files(
    lock_file: Path, lock_data: Dict[str, Any], ws_root: Path, lock_target: Optional[Path]
) -> List[Dict[str, Any]]:
    """Rileva file non tracciati (added:) o escape nel target di oracle_lock.json."""
    raw_files = lock_data.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        return []
    eff_target = lock_target or ((ws_root / "tests") if (ws_root / "tests").is_dir() else ws_root)
    mf_res = verify_oracle_lock_manifest(lock_file, eff_target)
    if mf_res.get("passed"):
        return []
    mism = [str(x) for x in (mf_res.get("mismatches") or []) if str(x).startswith(("added:", "escaped:"))]
    if not mism:
        return []
    return [_oracle_anom("NO_UNTRACKED_FILES", mism[0], f"File non tracciati o escape in oracle_lock.json: {', '.join(mism[:5])}")]


def _collect_missing_lock_anomalies(ws_root: Path, b_file: Path, require_lock: Optional[bool], is_full_hub: bool) -> List[Dict[str, Any]]:
    """Segnala l'assenza di oracle_lock.json e dei lock Hub obbligatori se applicabile."""
    must_exist = require_lock if require_lock is not None else (
        ((ws_root / ".agents" / "AGENTS.md").is_file() or (ws_root / ".agents" / "skills").is_dir()) and (ws_root / "tests").is_dir()
    )
    anoms = [_oracle_anom("PRESENT", "MISSING", "File oracle_lock.json mancante nel workspace sovrano.")] if must_exist else []
    return anoms + (_check_mandatory_extra_hub_locks(ws_root) if is_full_hub else [])


def _verify_oracle_lock_coherence(baseline_path: str, require_lock: Optional[bool] = None) -> list:
    """Verifica fail-closed esistenza fisica, digest SHA-256, added files e lock obbligatori Hub."""
    b_file = Path(baseline_path).resolve()
    ws_root = _resolve_workspace_root_from_baseline(baseline_path) if b_file.parent.name == "nk_tracking" else b_file.parent
    is_full_hub = _is_full_hub_for_locks(ws_root)
    lock_file = next((c for c in (ws_root / "nk_tracking" / "oracle_lock.json", b_file.parent / "oracle_lock.json") if c.is_file()), None)
    if lock_file is None:
        return _collect_missing_lock_anomalies(ws_root, b_file, require_lock, is_full_hub)
    try:
        lock_data = json.loads(lock_file.read_text(encoding="utf-8-sig"))
        if not isinstance(lock_data, dict):
            return [_oracle_anom("VALID_DICT", "INVALID_ROOT", "Il file oracle_lock.json non contiene un dizionario valido.")]
        locked_items = _collect_lock_items(lock_data)
        if not locked_items:
            return [_oracle_anom("NON_EMPTY_LOCK", "EMPTY", "Il file oracle_lock.json non contiene file protetti.")]
        lock_target = _resolve_lock_target_for_ws("oracle_lock.json", ws_root, lock_data.get("target"))
        cur_effective_map: Dict[str, str] = {}
        anomalies: List[Dict[str, Any]] = []
        for rel_entry, expected_sha in locked_items:
            anom = _check_single_oracle_entry(ws_root, lock_target, rel_entry, expected_sha, lock_data.get("files"), lock_data.get("locked_files"), cur_effective_map)
            if anom is not None:
                anomalies.append(anom)
        if (comb_anom := _check_combined_lock_sha(lock_data, lock_data.get("files"), cur_effective_map, bool(anomalies))) is not None:
            anomalies.append(comb_anom)
        if not anomalies:
            anomalies.extend(_check_untracked_oracle_files(lock_file, lock_data, ws_root, lock_target))
        if is_full_hub:
            anomalies.extend(_check_mandatory_extra_hub_locks(ws_root))
        return anomalies
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return [_oracle_anom("VALID_JSON", f"ERROR: {exc}", f"Errore lettura o validazione oracle_lock.json: {exc}")]

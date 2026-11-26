# -*- coding: utf-8 -*-
"""
Helper di validazione asset holdout e manifesti per Shadow Sandbox.
Modulo: scripts/_internal/dast_sandbox_runner/holdout_assets_helpers.py.
@domain_id: DOM-04
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Set, Tuple

from _internal.nk_common.constants import NK_LOCK_FILENAMES
from _internal.nk_common.oracle_lock import (
    compute_lf_sha256,
    sha256_eol_matches,
)

_LOCK_FILENAMES: Tuple[str, ...] = NK_LOCK_FILENAMES
_PROTECTED_EXACT = frozenset(
    {*(f"nk_tracking/{name.lower()}" for name in NK_LOCK_FILENAMES)}
    | {
        "nk_tracking/oracle_holdout",
        "nk_tracking/benchmark_suite",
        "tests/evals",
        "tests/evals/skill_golden_eval_set.json",
    }
)
_PROTECTED_PREFIXES = ("nk_tracking/benchmark_suite/", "nk_tracking/oracle_holdout/")
_HUB_MARKER_DIRS = (
    (".agents", "skills"),
    ("tests", "evals"),
    ("nk_tracking", "benchmark_suite"),
    ("nk_tracking", "oracle_holdout"),
)


def _is_external_app_repo(sb_dir: Path, root: Optional[Path] = None) -> bool:
    """True per repo app esterne con src_app/, src/ o app/ prive di asset holdout Hub-only."""
    roots = (sb_dir, root) if root is not None else (sb_dir,)
    has_app_dir = any((r / d).is_dir() for r in roots for d in ("src_app", "src", "app"))
    return has_app_dir and not any(
        r.joinpath(*p).is_dir() for r in roots for p in _HUB_MARKER_DIRS
    )


def _has_nonempty_holdout_dir(oh_dir: Path) -> bool:
    """True se la directory oracle_holdout esiste e contiene almeno un file."""
    return oh_dir.is_dir() and any(p.is_file() for p in oh_dir.rglob("*"))


def _validate_suite_dir(suite_dir: Path, has_oh: bool) -> List[str]:
    """Verifica i file JSON in benchmark_suite senza richiedere tasks_v1.json se ci sono altri JSON o oracle_holdout."""
    errors: List[str] = []
    if not suite_dir.is_dir():
        if not has_oh:
            errors.append("Directory mancante: nk_tracking/benchmark_suite o nk_tracking/oracle_holdout")
        return errors
    json_suites = sorted(suite_dir.glob("*.json"))
    if not json_suites:
        if not has_oh:
            errors.append("Nessun benchmark JSON presente in nk_tracking/benchmark_suite")
        return errors
    for js_file in json_suites:
        try:
            json.loads(js_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            errors.append(f"Benchmark JSON corrotto ({js_file.name}): {exc}")
    return errors


def _check_required_holdout_assets(sb_dir: Path) -> List[str]:
    """Verifica esistenza e leggibilita JSON degli asset holdout in sandbox."""
    errors: List[str] = []
    lock_file = sb_dir / "nk_tracking" / "oracle_lock.json"
    eval_file = sb_dir / "tests" / "evals" / "skill_golden_eval_set.json"
    suite_dir = sb_dir / "nk_tracking" / "benchmark_suite"
    oh_dir = sb_dir / "nk_tracking" / "oracle_holdout"

    if not lock_file.is_file():
        errors.append("Asset holdout mancante: nk_tracking/oracle_lock.json")
    else:
        try:
            data = json.loads(lock_file.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
                errors.append("Schema non valido per nk_tracking/oracle_lock.json")
        except Exception as exc:
            errors.append(f"JSON corrotto in nk_tracking/oracle_lock.json: {exc}")
    if _is_external_app_repo(sb_dir):
        return errors

    if not eval_file.is_file():
        errors.append("Asset holdout mancante: tests/evals/skill_golden_eval_set.json")
    else:
        try:
            json.loads(eval_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            errors.append(f"JSON corrotto in tests/evals/skill_golden_eval_set.json: {exc}")

    errors.extend(_validate_suite_dir(suite_dir, _has_nonempty_holdout_dir(oh_dir)))
    return errors


def _is_protected_holdout_path(raw_path: str, include_all_tests: bool) -> bool:
    """Verifica se raw_path ricade in asset holdout protetti o benchmark_suite."""
    norm = raw_path.replace("\\", "/").lstrip("/").lower()
    if norm in _PROTECTED_EXACT or norm.startswith(_PROTECTED_PREFIXES):
        return True
    return norm.startswith("tests/" if include_all_tests else "tests/evals/")


def _validate_holdout_json_file(sf: Path, rel: str) -> Optional[str]:
    """Verifica il parsing JSON UTF-8-SIG di un file oracle_holdout."""
    try:
        json.loads(sf.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return f"JSON corrotto in nk_tracking/oracle_holdout/{rel}: {exc}"
    return None


def _compare_prod_holdout_file(pf: Path, prod_oh: Path, sb_oh: Path) -> Tuple[str, Optional[str]]:
    """Confronta un singolo asset oracle_holdout di produzione con la sandbox."""
    rel = pf.relative_to(prod_oh).as_posix()
    sf = sb_oh / rel
    if not sf.is_file():
        return rel, f"Asset oracle_holdout mancante in sandbox: nk_tracking/oracle_holdout/{rel}"
    if not sha256_eol_matches(sf, compute_lf_sha256(pf)):
        return rel, f"Asset oracle_holdout alterato in sandbox: nk_tracking/oracle_holdout/{rel}"
    if sf.suffix.lower() == ".json":
        return rel, _validate_holdout_json_file(sf, rel)
    return rel, None


def _check_extra_sb_holdout_files(
    sb_files: List[Path], sb_oh: Path, prod_rels: Set[str], prod_exists: bool
) -> List[str]:
    """Segnala asset oracle_holdout inattesi o corrotti presenti solo in sandbox."""
    errors: List[str] = []
    for sf in sb_files:
        rel = sf.relative_to(sb_oh).as_posix()
        if rel in prod_rels:
            continue
        if prod_exists:
            errors.append(f"Asset oracle_holdout non autorizzato in sandbox: nk_tracking/oracle_holdout/{rel}")
        elif sf.suffix.lower() == ".json":
            err = _validate_holdout_json_file(sf, rel)
            if err:
                errors.append(err)
    return errors


def _collect_holdout_pair_errors(prod_oh: Path, sb_oh: Path, prod_exists: bool) -> List[str]:
    """Confronta file di produzione e sandbox in oracle_holdout mantenendo CC ridotto."""
    prod_files = [pf for pf in sorted(prod_oh.rglob("*")) if pf.is_file()] if prod_exists else []
    sb_files = [sf for sf in sorted(sb_oh.rglob("*")) if sf.is_file()]
    errors: List[str] = []
    if prod_exists and not prod_files:
        errors.append("Directory holdout vuota in produzione: nk_tracking/oracle_holdout")
    if not sb_files:
        errors.append("Directory holdout vuota in sandbox: nk_tracking/oracle_holdout")
    prod_rels: Set[str] = set()
    for pf in prod_files:
        rel, err = _compare_prod_holdout_file(pf, prod_oh, sb_oh)
        prod_rels.add(rel)
        if err:
            errors.append(err)
    errors.extend(_check_extra_sb_holdout_files(sb_files, sb_oh, prod_rels, prod_exists))
    return errors


def _check_oracle_holdout_assets(root: Path, sb_dir: Path) -> List[str]:
    """Verifica nk_tracking/oracle_holdout quando presente o quando benchmark_suite e assente."""
    prod_oh, sb_oh = root / "nk_tracking" / "oracle_holdout", sb_dir / "nk_tracking" / "oracle_holdout"
    suite_dir = sb_dir / "nk_tracking" / "benchmark_suite"
    has_suite = suite_dir.is_dir() and any(suite_dir.glob("*.json"))
    prod_exists = prod_oh.is_dir()
    if not prod_exists and not sb_oh.is_dir():
        return [] if (has_suite or _is_external_app_repo(sb_dir, root)) else ["Directory holdout mancante in produzione: nk_tracking/oracle_holdout"]
    errors: List[str] = []
    if not prod_exists and not has_suite:
        errors.append("Directory holdout mancante in produzione: nk_tracking/oracle_holdout")
    if not sb_oh.is_dir():
        return errors + ["Directory holdout mancante in sandbox: nk_tracking/oracle_holdout"]
    return errors + _collect_holdout_pair_errors(prod_oh, sb_oh, prod_exists)


def _check_overlay_and_tombstones(overlay_set: Set[str], deleted_applied: List[str]) -> List[str]:
    """Blocca sovrascritture e cancellazioni tombstone sugli asset holdout protetti."""
    errors: List[str] = []
    for ov_p in sorted(overlay_set):
        if _is_protected_holdout_path(ov_p, include_all_tests=False):
            errors.append(f"Staging non puo sovrascrivere asset holdout protetto: {ov_p}")
    for del_p in deleted_applied:
        norm_d = del_p.replace("\\", "/").lstrip("/")
        if _is_protected_holdout_path(del_p, include_all_tests=True):
            errors.append(f"Cancellazione tombstone vietata su asset holdout: {norm_d}")
    return errors

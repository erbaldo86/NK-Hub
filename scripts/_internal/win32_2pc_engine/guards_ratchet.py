#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validatori JSON, cleanup staging, ratchet quality_baseline e scansione canonica."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from . import constants as _consts
from .constants import TwoPhaseCommitError
from .io_and_paths import _assert_no_external_reparse, _is_reparse_point


def _extract_dual_schema_baseline(
    data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[float], int]:
    """Estrae metriche, pass rate e numero di test supportando entrambi gli schemi baseline."""
    raw_metrics = (
        data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
    )
    candidate_metrics: Dict[str, Any] = {
        k: (v.get("value") if isinstance(v, dict) else v)
        for k, v in raw_metrics.items()
    }
    pass_rate: Optional[float] = None
    if "unit_tests_pass_pct" in candidate_metrics:
        pass_rate = float(candidate_metrics["unit_tests_pass_pct"])
    elif data.get("pass_rate_pct") is not None:
        pass_rate = float(data["pass_rate_pct"])
        candidate_metrics["unit_tests_pass_pct"] = pass_rate
    elif data.get("pass_rate") is not None:
        pass_rate = float(data["pass_rate"])
        candidate_metrics["unit_tests_pass_pct"] = pass_rate

    total_tests = 0
    if "unit_tests_total" in candidate_metrics:
        total_tests = int(candidate_metrics["unit_tests_total"])
    elif "total_golden_tests" in candidate_metrics:
        total_tests = int(candidate_metrics["total_golden_tests"])
    elif data.get("total_tests") is not None:
        total_tests = int(data["total_tests"])
        candidate_metrics["unit_tests_total"] = total_tests
    elif data.get("golden_tests_count") is not None:
        total_tests = int(data["golden_tests_count"])
        candidate_metrics["unit_tests_total"] = total_tests

    if (
        data.get("failed_tests") is not None
        and "failed_tests" not in candidate_metrics
    ):
        candidate_metrics["failed_tests"] = int(data["failed_tests"])

    return candidate_metrics, pass_rate, total_tests


def _verify_quality_baseline_ratchet(
    dst_bl: Union[str, Path, Dict[str, Any]],
    stg_bl: Optional[Union[str, Path, Dict[str, Any]]] = None,
    allow_ratchet_down: bool = False,
) -> Dict[str, Any]:
    """Verifica il rispetto del ratchet quality_baseline.json con supporto Dual-Schema."""
    import inspect
    from quality_baseline_manager import (
        _evaluate_baseline_compliance,
        _verify_oracle_lock_coherence,
    )

    if isinstance(dst_bl, dict):
        cand_metrics, pass_rate, total_tests = _extract_dual_schema_baseline(dst_bl)
        if not cand_metrics or pass_rate is None:
            raise TwoPhaseCommitError(
                "Metriche assenti o invalide nel quality_baseline."
            )
        if pass_rate < 100.0:
            raise TwoPhaseCommitError(
                f"Pass rate inferiore al 100.0% nel quality_baseline: {pass_rate}%"
            )
        return {
            "verdict": "PASS",
            "pass_rate_pct": pass_rate,
            "total_tests": total_tests,
            "metrics": cand_metrics,
        }

    dst_path = Path(dst_bl)
    stg_path = Path(stg_bl) if isinstance(stg_bl, (str, Path)) else None

    if (
        stg_path is not None
        and stg_path.exists()
        and dst_path.exists()
        and stg_path.resolve() != dst_path.resolve()
    ):
        dst_data = json.loads(dst_path.read_text(encoding="utf-8-sig"))
        stg_data = (
            stg_bl
            if isinstance(stg_bl, dict)
            else json.loads(stg_path.read_text(encoding="utf-8-sig"))
        )
        _, dst_pass, _ = _extract_dual_schema_baseline(dst_data)
        stg_metrics, stg_pass, stg_tot = _extract_dual_schema_baseline(stg_data)
        if not stg_metrics:
            raise TwoPhaseCommitError(
                f"Metriche assenti o invalide nel quality_baseline di staging: {stg_path}"
            )
        if stg_pass is not None and stg_pass < 100.0:
            raise TwoPhaseCommitError(
                f"Pass rate di staging inferiore al 100.0%: {stg_pass}%"
            )
        if dst_pass is not None and stg_pass is not None and stg_pass < dst_pass:
            raise TwoPhaseCommitError(
                f"Regressione pass rate nel quality_baseline: {dst_pass}% -> {stg_pass}%"
            )
        if isinstance(dst_data.get("metrics"), dict) and dst_data.get("metrics"):
            eval_kwargs: Dict[str, Any] = {"preloaded_baseline": dst_data}
            if (
                allow_ratchet_down
                or "allow_ratchet_down"
                in inspect.signature(_evaluate_baseline_compliance).parameters
            ):
                eval_kwargs["allow_ratchet_down"] = bool(allow_ratchet_down)
            res_bl, _ = _evaluate_baseline_compliance(
                str(dst_path), stg_metrics, **eval_kwargs
            )
            if res_bl.get("verdict") != "PASS":
                raise TwoPhaseCommitError(
                    f"Regressione rilevata nel quality_baseline di staging: {res_bl.get('regressions')}"
                )
        return {
            "verdict": "PASS",
            "pass_rate_pct": stg_pass if stg_pass is not None else 100.0,
            "total_tests": stg_tot,
            "metrics": stg_metrics,
        }

    active_bl = (
        dst_path
        if dst_path.exists()
        else (stg_path if stg_path is not None else dst_path)
    )
    bl_data = json.loads(active_bl.read_text(encoding="utf-8-sig"))
    cand_metrics, pass_rate, total_tests = _extract_dual_schema_baseline(bl_data)
    if not cand_metrics:
        raise TwoPhaseCommitError(
            f"Metriche assenti o invalide nel quality_baseline: {active_bl}"
        )
    if pass_rate is not None and pass_rate < 100.0:
        raise TwoPhaseCommitError(
            f"Regressione rilevata nel quality_baseline ({active_bl}): pass_rate={pass_rate}%"
        )
    if isinstance(bl_data.get("metrics"), dict) and bl_data.get("metrics"):
        lock_anomalies = _verify_oracle_lock_coherence(str(active_bl))
        if lock_anomalies:
            raise TwoPhaseCommitError(
                f"Regressione rilevata nel quality_baseline: {lock_anomalies}"
            )
    return {
        "verdict": "PASS",
        "pass_rate_pct": pass_rate if pass_rate is not None else 100.0,
        "total_tests": total_tests,
        "metrics": cand_metrics,
    }


def _scan_staging_canonical(
    staging_dir: Path,
    real_root: Path,
    subdirs: Optional[List[str]] = None,
) -> List[Path]:
    """Scansiona .staging/ bloccando ADS, punti/spazi finali e junction esterne e ignorando artefatti effimeri."""
    _assert_no_external_reparse(staging_dir, real_root)
    allowed_top_subdirs: Optional[Set[str]] = set(subdirs) if subdirs else None
    collected: List[Path] = []

    def _walk_dir(curr_dir: Path, depth: int) -> None:
        raw_dir = str(curr_dir)
        scan_path = (
            "\\\\?\\" + str(curr_dir.resolve())
            if os.name == "nt" and not raw_dir.startswith("\\\\?\\")
            else raw_dir
        )
        try:
            with os.scandir(scan_path) as it:
                entries = sorted(list(it), key=lambda e: e.name)
        except OSError:
            with os.scandir(raw_dir) as it:
                entries = sorted(list(it), key=lambda e: e.name)

        for entry in entries:
            name = entry.name
            if name in (".", ".."):
                continue
            if "\x00" in name or ":" in name:
                raise TwoPhaseCommitError(
                    f"Alternate Data Stream (ADS) o ':' vietato in staging: {name!r}"
                )
            if name != name.rstrip(". "):
                raise TwoPhaseCommitError(
                    f"Componente percorso Win32 con punto o spazio finale vietato in staging: {name!r}"
                )

            entry_path = curr_dir / name
            is_rep = False
            try:
                if entry.is_symlink():
                    is_rep = True
                else:
                    st_attrs = getattr(
                        entry.stat(follow_symlinks=False), "st_file_attributes", 0
                    )
                    if (st_attrs & _consts.FILE_ATTRIBUTE_REPARSE_POINT) != 0:
                        is_rep = True
            except OSError:
                is_rep = _is_reparse_point(entry_path)

            if is_rep:
                real_target = Path(os.path.realpath(str(entry_path)))
                if real_target != real_root and real_root not in real_target.parents:
                    raise TwoPhaseCommitError(
                        f"Junction o reparse point in staging punta fuori da root: {entry_path} -> {real_target}"
                    )

            if name in (".git", "__pycache__"):
                continue

            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                is_dir = entry_path.is_dir()
                is_file = entry_path.is_file()

            if is_dir:
                if (
                    depth == 0
                    and allowed_top_subdirs is not None
                    and name not in allowed_top_subdirs
                ):
                    continue
                _walk_dir(entry_path, depth + 1)
            elif is_file:
                if name in (".gitkeep", ".deleted_files.json"):
                    continue
                if Path(name).suffix.lower() in _consts.IGNORED_STAGING_SUFFIXES:
                    continue
                collected.append(entry_path)

    _walk_dir(staging_dir, 0)
    return collected

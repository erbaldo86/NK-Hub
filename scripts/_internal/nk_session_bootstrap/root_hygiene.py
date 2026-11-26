#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifiche di igiene della root, rilevamento .staging sporco e validazione baseline."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.nk_common.staging_manifest import is_lane_container_entry

from . import constants as _consts


def get_staging_mtime(self_obj: Any) -> float:
    """Restituisce il timestamp st_mtime di .staging/ in O(1) con memoizzazione per turno."""
    if self_obj._cached_staging_mtime is not None:
        return self_obj._cached_staging_mtime
    staging_dir = self_obj.workspace_root / ".staging"
    try:
        self_obj._cached_staging_mtime = float(os.stat(staging_dir).st_mtime)
    except OSError:
        self_obj._cached_staging_mtime = 0.0
    return self_obj._cached_staging_mtime


def _scan_dir_entry_has_payload(cur_dir: str, stg_str: str, stack: List[str]) -> bool:
    """Ispeziona una directory in .staging/ e accoda sottodirectory saltando lanes/ top-level."""
    is_top = cur_dir == stg_str
    try:
        with os.scandir(cur_dir) as it:
            entries = list(it)
    except OSError:
        return False
    for entry in entries:
        if is_top and is_lane_container_entry((entry.name,)):
            continue
        if entry.is_file(follow_symlinks=False) and entry.name != ".gitkeep":
            return True
        if entry.is_dir(follow_symlinks=False):
            stack.append(entry.path)
    return False


def _dir_has_non_gitkeep_files(staging_dir: Path) -> bool:
    """Scansiona .staging/ saltando .gitkeep e il contenitore lanes/ top-level."""
    stg_str = str(staging_dir)
    stack: List[str] = [stg_str]
    while stack:
        if _scan_dir_entry_has_payload(stack.pop(), stg_str, stack):
            return True
    return False


def is_staging_dirty(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> bool:
    """Restituisce True se .staging/ contiene almeno un file oltre a .gitkeep e lanes/."""
    curr_stg_mtime = self_obj._get_staging_mtime()
    if curr_stg_mtime <= 0.0:
        return False
    if (
        cached is not None
        and cached.get("staging_mtime") is not None
        and float(cached["staging_mtime"]) == curr_stg_mtime
        and "staging_dirty_warning" in cached
    ):
        return bool(cached["staging_dirty_warning"])
    return _dir_has_non_gitkeep_files(self_obj.workspace_root / ".staging")


def get_root_mtime(self_obj: Any) -> float:
    """Restituisce il timestamp massimo di modifica tra radice e percorsi critici del workspace."""
    if self_obj._cached_root_mtime is not None:
        return self_obj._cached_root_mtime
    max_mtime = 0.0
    hub_root = _consts._get_facade_attr("HUB_ROOT", _consts.HUB_ROOT)
    is_hub = self_obj.workspace_root == hub_root
    wal_cand = self_obj.workspace_root / ".wal"
    try:
        mt_wal = float(os.stat(wal_cand).st_mtime)
        self_obj._wal_dir_exists = True
        if mt_wal > max_mtime:
            max_mtime = mt_wal
    except OSError:
        self_obj._wal_dir_exists = False

    for b_cand in (
        self_obj.workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json",
        self_obj.workspace_root / "nk_tracking" / "quality_baseline.json",
    ):
        try:
            bst = os.stat(b_cand)
            if self_obj._cached_baseline_stat is None:
                self_obj._cached_baseline_stat = (b_cand, bst)
            if float(bst.st_mtime) > max_mtime:
                max_mtime = float(bst.st_mtime)
            if is_hub:
                break
        except OSError:
            continue

    extra_cands = (
        (
            self_obj.workspace_root,
            self_obj.workspace_root / "scripts",
            self_obj.workspace_root / ".agents",
        )
        if is_hub
        else (
            self_obj.workspace_root,
            self_obj.workspace_root / "scripts",
            self_obj.workspace_root / ".agents",
            self_obj.workspace_root / "src_app",
        )
    )
    for path_cand in extra_cands:
        try:
            mt = float(os.stat(path_cand).st_mtime)
            if mt > max_mtime:
                max_mtime = mt
        except OSError:
            continue
    self_obj._cached_root_mtime = max_mtime
    return max_mtime


def has_root_file_pollution_quick(self_obj: Any, is_hub_root: bool) -> bool:
    """Verifica rapidamente la presenza di file .py, .tmp o .bak estranei nella root."""
    try:
        with os.scandir(self_obj.workspace_root) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                fname = entry.name
                if fname.startswith(".") or fname.startswith("quality_baseline.json."):
                    continue
                if fname.endswith((".tmp", ".bak")):
                    return True
                if fname.endswith(".py") and (
                    is_hub_root or fname not in ("conftest.py", "setup.py")
                ):
                    return True
    except Exception:
        pass
    return False


def check_root_hygiene(
    self_obj: Any,
    use_fast_cache: bool = False,
    cached: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Verifica l'assenza di cartelle applicative o file .py, .tmp, .bak estranei nella radice."""
    hub_root = _consts._get_facade_attr("HUB_ROOT", _consts.HUB_ROOT)
    fast_ttl = float(
        _consts._get_facade_attr("FAST_CACHE_TTL_SECONDS", _consts.FAST_CACHE_TTL_SECONDS)
    )
    is_hub_root = self_obj.workspace_root.resolve() == hub_root
    staging_dirty = self_obj._is_staging_dirty(
        cached=cached if use_fast_cache else None
    )
    curr_mtime = (
        self_obj._last_root_mtime
        if (use_fast_cache and self_obj._last_root_mtime > 0.0)
        else self_obj._get_root_mtime()
    )
    if use_fast_cache and not self_obj._has_root_file_pollution_quick(is_hub_root):
        if cached is None:
            cached = self_obj._load_fast_cache()
        if (
            cached is not None
            and cached.get("root_mtime") == curr_mtime
            and (time.time() - float(cached.get("timestamp_epoch", 0.0))) <= fast_ttl
        ):
            detected_cached = list(cached.get("root_hygiene_violations", []))
            self_obj._last_root_mtime = curr_mtime
            self_obj._last_root_violations = detected_cached
            passed_cached = len(detected_cached) == 0
            return {
                "passed": passed_cached,
                "status": "PASS" if passed_cached else "FAIL",
                "root_mtime": curr_mtime,
                "staging_dirty_warning": staging_dirty,
                "violations": detected_cached,
                "details": "Workspace root isolated."
                if passed_cached
                else f"Pollution detected in: {detected_cached}",
            }

    forbidden_dirs = ("src_app", "app", "src")
    detected_dirs: List[str] = []
    detected_files: List[str] = []
    dir_check_root = self_obj.workspace_root if is_hub_root else hub_root

    try:
        with os.scandir(dir_check_root) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False) and entry.name in forbidden_dirs:
                    target = Path(entry.path)
                    if any(target.iterdir()):
                        detected_dirs.append(entry.name)
    except Exception:
        for fdir in forbidden_dirs:
            target = dir_check_root / fdir
            if target.exists() and any(target.iterdir()):
                detected_dirs.append(fdir)

    try:
        with os.scandir(self_obj.workspace_root) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                fname = entry.name
                if fname.startswith(".") or fname.startswith("quality_baseline.json."):
                    continue
                if fname.endswith((".tmp", ".bak")):
                    detected_files.append(fname)
                elif fname.endswith(".py") and (
                    is_hub_root or fname not in ("conftest.py", "setup.py")
                ):
                    detected_files.append(fname)
    except Exception:
        for ext_pat in ("*.py", "*.tmp", "*.bak"):
            for root_f in self_obj.workspace_root.glob(ext_pat):
                fname = root_f.name
                if fname.startswith(".") or fname.startswith("quality_baseline.json."):
                    continue
                if (
                    fname.endswith(".py")
                    and not is_hub_root
                    and fname in ("conftest.py", "setup.py")
                ):
                    continue
                detected_files.append(fname)

    ordered_dirs = [d for d in forbidden_dirs if d in detected_dirs]
    detected = ordered_dirs + sorted(detected_files)
    self_obj._last_root_mtime = curr_mtime
    self_obj._last_root_violations = detected

    passed = len(detected) == 0
    return {
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "root_mtime": curr_mtime,
        "is_external_project": not is_hub_root,
        "staging_dirty_warning": staging_dirty,
        "violations": detected,
        "details": "Workspace root isolated."
        if passed
        else f"Pollution detected in: {detected}",
    }


def verify_baseline(
    self_obj: Any, cached: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Verifica che quality_baseline.json esista e abbia pass rate pari a 100%."""
    baseline_path: Optional[Path] = None
    b_stat: Any = None
    if self_obj._cached_baseline_stat is not None:
        baseline_path, b_stat = self_obj._cached_baseline_stat
    else:
        staging_baseline = (
            self_obj.workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json"
        )
        prod_baseline = self_obj.workspace_root / "nk_tracking" / "quality_baseline.json"
        for cand in (staging_baseline, prod_baseline):
            try:
                b_stat = os.stat(cand)
                baseline_path = cand
                self_obj._cached_baseline_stat = (cand, b_stat)
                break
            except OSError:
                continue

    if baseline_path is None or b_stat is None:
        return {"passed": False, "details": "quality_baseline.json missing."}

    if cached is not None:
        cached_b_meta = cached.get("baseline_stat")
        cached_b_chk = cached.get("checks", {}).get("quality_baseline")
        if (
            isinstance(cached_b_meta, list)
            and len(cached_b_meta) == 3
            and cached_b_meta[0] == str(baseline_path)
            and int(cached_b_meta[1]) == b_stat.st_mtime_ns
            and int(cached_b_meta[2]) == b_stat.st_size
            and isinstance(cached_b_chk, dict)
        ):
            import copy

            return copy.deepcopy(cached_b_chk)

    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        metrics = (
            data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
        )
        raw_pct = metrics.get("unit_tests_pass_pct")
        if isinstance(raw_pct, dict) and "value" in raw_pct:
            unit_pass = float(raw_pct["value"])
        elif isinstance(raw_pct, (int, float)):
            unit_pass = float(raw_pct)
        elif data.get("pass_rate_pct") is not None:
            unit_pass = float(data["pass_rate_pct"])
        elif data.get("pass_rate") is not None:
            unit_pass = float(data["pass_rate"])
        else:
            unit_pass = 0.0

        raw_tot = metrics.get("unit_tests_total") or metrics.get("total_golden_tests")
        if isinstance(raw_tot, dict) and "value" in raw_tot:
            total_tests = int(raw_tot["value"])
        elif isinstance(raw_tot, (int, float)):
            total_tests = int(raw_tot)
        else:
            total_tests = int(
                data.get("total_tests")
                or data.get("golden_tests_count")
                or data.get("passed_tests")
                or 0
            )

        passed = unit_pass >= 100.0
        return {
            "passed": passed,
            "unit_pass_pct": unit_pass,
            "total_tests": total_tests,
            "details": f"Baseline pass rate: {unit_pass}%",
        }
    except Exception as exc:
        return {"passed": False, "details": str(exc)}

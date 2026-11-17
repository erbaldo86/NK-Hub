# -*- coding: utf-8 -*-
"""Misurazione metriche Pytest reali e copertura branch con overlay .staging e mirror NVMe."""

from __future__ import annotations

import json
import os
import re
import shutil  # noqa: F401 - preservato per compatibilita export facciata
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.nk_common.isolated_test_runner import (
    is_temp_workspace,
    mirror_workspace_to_nvme,
    safe_rmtree,
    win32_detached_flags,
)
from _internal.quality_baseline_manager.constants import _facade_attr, _scripts_dir


def _count_live_skills_overlay(ws_root: Path, deleted_rel: set[str]) -> int:
    """Conta le skill canoniche con SKILL.md applicando overlay .staging e tombstone."""
    skill_dirs: set[str] = set()
    prod_skills = ws_root / ".agents" / "skills"
    if prod_skills.is_dir():
        for sk_md in prod_skills.glob("*/SKILL.md"):
            rel = f".agents/skills/{sk_md.parent.name}/SKILL.md"
            if rel not in deleted_rel:
                skill_dirs.add(sk_md.parent.name)
    stg_skills = ws_root / ".staging" / ".agents" / "skills"
    if stg_skills.is_dir():
        for sk_md in stg_skills.glob("*/SKILL.md"):
            skill_dirs.add(sk_md.parent.name)
    return len(skill_dirs)


def _extract_coverage_totals(cov_json: Path) -> Dict[str, float]:
    """Estrae statement, true branch e combined coverage dal report JSON di pytest-cov."""
    if not cov_json.is_file():
        return {}
    try:
        cov_data = json.loads(cov_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    totals = cov_data.get("totals") if isinstance(cov_data, dict) else None
    if not isinstance(totals, dict) or not totals:
        return {}

    raw_stmt = totals.get("percent_statements_covered")
    if raw_stmt is None:
        n_stmt = float(totals.get("num_statements", 0) or 0)
        c_line = float(totals.get("covered_lines", 0) or 0)
        raw_stmt = (c_line / n_stmt) * 100.0 if n_stmt > 0 else 0.0

    raw_branch = totals.get("percent_branches_covered")
    if raw_branch is None:
        n_br = float(totals.get("num_branches", 0) or 0)
        c_br = float(totals.get("covered_branches", 0) or 0)
        raw_branch = (c_br / n_br) * 100.0 if n_br > 0 else 0.0

    raw_comb = totals.get("percent_covered")
    if raw_comb is None:
        raw_comb = raw_branch

    return {
        "statement_coverage_pct": round(float(raw_stmt), 2),
        "true_branch_coverage_pct": round(float(raw_branch), 2),
        "combined_coverage_pct": round(float(raw_comb), 2),
    }


def _load_deleted_rel(del_manifest: Path) -> set[str]:
    """Carica il set normalizzato dei percorsi rimossi in .deleted_files.json."""
    if not del_manifest.is_file():
        return set()
    try:
        raw_del = json.loads(del_manifest.read_text(encoding="utf-8"))
        del_items = raw_del.get("deleted_files", []) if isinstance(raw_del, dict) else raw_del
        if isinstance(del_items, list):
            return {str(item).replace("\\", "/").lstrip("/") for item in del_items}
    except Exception:
        return set()
    return set()


def measure_live_pytest_metrics(
    workspace_root: Optional[Path] = None,
    with_coverage: bool = False,
) -> dict:
    """Esegue pytest reale in ambiente NVMe isolato con overlay .staging."""
    if workspace_root is None:
        s_dir = Path(_facade_attr("_scripts_dir", _scripts_dir)).resolve()
        ws_root = s_dir.parent.parent if s_dir.parent.name == ".staging" else s_dir.parent
    else:
        ws_root = Path(workspace_root).resolve()

    prod_tests_dir = ws_root / "tests"
    stg_tests_dir = ws_root / ".staging" / "tests"
    deleted_rel = _load_deleted_rel(ws_root / ".staging" / ".deleted_files.json")

    overlay_tests: Dict[str, Path] = {}
    if prod_tests_dir.is_dir():
        for tf in sorted(prod_tests_dir.rglob("test_*.py")):
            if "__pycache__" not in tf.parts:
                rel_k = tf.relative_to(prod_tests_dir).as_posix()
                if f"tests/{rel_k}" not in deleted_rel:
                    overlay_tests[rel_k] = tf
    if stg_tests_dir.is_dir():
        for tf in sorted(stg_tests_dir.rglob("test_*.py")):
            if "__pycache__" not in tf.parts:
                overlay_tests[tf.relative_to(stg_tests_dir).as_posix()] = tf

    count_fn = _facade_attr("_count_live_skills_overlay", _count_live_skills_overlay)
    skills_cnt = count_fn(ws_root, deleted_rel)

    if not overlay_tests:
        empty_res: Dict[str, Any] = {
            "total_golden_tests": 0, "unit_tests_total": 0, "unit_tests_passed": 0,
            "unit_tests_pass_pct": 0.0, "pass_rate_pct": 0.0, "pass_rate_percent": 0.0,
            "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 0.0,
        }
        if skills_cnt > 0:
            empty_res["skills_audited"] = skills_cnt
        return empty_res

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    for cov_env_k in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"):
        env.pop(cov_env_k, None)

    sub_mod = _facade_attr("subprocess", subprocess)
    cov_metrics: Dict[str, float] = {}
    cov_tmp_dir: Optional[Path] = None
    bt_tmp_dir: Optional[Path] = None
    mirror_dir: Optional[Path] = None
    try:
        if not is_temp_workspace(ws_root):
            mirror_dir = mirror_workspace_to_nvme(ws_root, prefix="nk_qbm_iso_", apply_overlay=True)
            run_cwd = mirror_dir
            pytest_targets = [str(mirror_dir / "tests")]
            env["PYTHONPATH"] = str(mirror_dir)
        else:
            run_cwd = ws_root
            py_paths = [str(ws_root / ".staging")] if (ws_root / ".staging").is_dir() else []
            py_paths.append(str(ws_root))
            if existing_pp := env.get("PYTHONPATH", ""):
                py_paths.append(existing_pp)
            env["PYTHONPATH"] = os.pathsep.join(py_paths)
            pytest_targets = [str(overlay_tests[k]) for k in sorted(overlay_tests)] if stg_tests_dir.is_dir() else [str(prod_tests_dir)]

        if with_coverage:
            cov_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_qbm_cov_"))
            cov_json = cov_tmp_dir / "cov.json"
            cov_basetemp = cov_tmp_dir / "bt"
            cov_basetemp.mkdir(parents=True, exist_ok=True)
            env["COVERAGE_FILE"] = str(cov_tmp_dir / ".coverage")
            cov_plugin_args = ["-p", "pytest_cov"] if env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") else []
            cmd = [
                sys.executable, "-B", "-u", "-m", "pytest", *pytest_targets,
                "-p", "no:cacheprovider", *cov_plugin_args,
                "--cov=scripts", "--cov-branch", f"--cov-report=json:{cov_json.as_posix()}",
                f"--basetemp={cov_basetemp.as_posix()}", "-q", "--tb=no",
            ]
        else:
            bt_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_qbm_bt_"))
            cmd = [
                sys.executable, "-B", "-u", "-m", "pytest", *pytest_targets,
                "-p", "no:cacheprovider", f"--basetemp={bt_tmp_dir.as_posix()}", "-q", "--tb=no",
            ]

        t0 = time.perf_counter()
        proc = sub_mod.run(
            cmd,
            cwd=str(run_cwd),
            env=env,
            stdin=getattr(sub_mod, "DEVNULL", subprocess.DEVNULL),
            creationflags=win32_detached_flags(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300 if with_coverage else 240,
            shell=False,
        )
        duration_s = round(time.perf_counter() - t0, 2)
        if with_coverage:
            ext_cov = _facade_attr("_extract_coverage_totals", _extract_coverage_totals)
            cov_metrics = ext_cov(cov_json)
    finally:
        if cov_tmp_dir is not None:
            safe_rmtree(cov_tmp_dir)
        if bt_tmp_dir is not None:
            safe_rmtree(bt_tmp_dir)
        if mirror_dir is not None:
            safe_rmtree(mirror_dir.parent)

    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    m_pass = re.search(r"(\d+)\s+passed", combined)
    m_fail = re.search(r"(\d+)\s+failed", combined)
    m_err = re.search(r"(\d+)\s+errors?", combined)
    m_skip = re.search(r"(\d+)\s+skipped", combined)
    m_xfail = re.search(r"(\d+)\s+xfailed", combined)

    passed = int(m_pass.group(1)) if m_pass else 0
    skipped = (int(m_skip.group(1)) if m_skip else 0) + (int(m_xfail.group(1)) if m_xfail else 0)
    failed = (int(m_fail.group(1)) if m_fail else 0) + (int(m_err.group(1)) if m_err else 0) + skipped
    if proc.returncode != 0 and failed == 0:
        failed = 1
    total = passed + failed
    pass_rate = round((passed / total) * 100.0, 2) if total > 0 else 0.0

    result: Dict[str, Any] = {
        "total_golden_tests": total, "unit_tests_total": total, "unit_tests_passed": passed,
        "unit_tests_pass_pct": pass_rate, "pass_rate_pct": pass_rate, "pass_rate_percent": pass_rate,
        "failed_tests": failed, "tests_skipped": skipped, "pytest_duration_s": duration_s,
    }
    if skills_cnt > 0:
        result["skills_audited"] = skills_cnt
    if cov_metrics:
        result.update(cov_metrics)
    return result

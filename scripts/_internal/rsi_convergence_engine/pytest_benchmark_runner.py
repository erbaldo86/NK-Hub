# -*- coding: utf-8 -*-
"""Esecutore reale di benchmark Pytest (NVMe isolato) e suite A/B JSON per RSI."""

from __future__ import annotations

import json
import os
import re
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
from _internal.rsi_convergence_engine.ab_benchmark import run_ab_benchmark


def _remap_targets_to_mirror(
    pytest_targets: List[str], base_root: Path, mirror_dir: Path
) -> List[str]:
    """Rimappa i percorsi target dal workspace sorgente al mirror NVMe."""
    stg_root = (base_root / ".staging").resolve()
    base_res = base_root.resolve()
    mapped: List[str] = []
    for raw_t in pytest_targets:
        t_p = Path(raw_t).resolve()
        if t_p.is_relative_to(stg_root):
            mapped.append(str(mirror_dir / t_p.relative_to(stg_root)))
        elif t_p.is_relative_to(base_res):
            mapped.append(str(mirror_dir / t_p.relative_to(base_res)))
        else:
            mapped.append(raw_t)
    return mapped


def run_benchmark_suite_impl(
    engine: Any, benchmark_suite: Path | str, root_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Esegue una suite A/B JSON o Pytest reale (-B, NVMe isolato) restituendo metriche reali."""
    base_root = Path(root_dir).resolve() if root_dir else engine.workspace_root
    suite_path = Path(benchmark_suite)
    if not suite_path.is_absolute():
        stg_cand = base_root / ".staging" / suite_path
        cand = base_root / suite_path
        if cand.exists():
            suite_path = cand.resolve()
        elif stg_cand.exists():
            suite_path = stg_cand.resolve()
        elif (engine.workspace_root / ".staging" / suite_path).exists():
            suite_path = (engine.workspace_root / ".staging" / suite_path).resolve()
        else:
            suite_path = (engine.workspace_root / suite_path).resolve()

    tasks_json_cand: Optional[Path] = None
    if suite_path.is_file() and suite_path.name == "tasks_v1.json":
        tasks_json_cand = suite_path
    elif suite_path.is_dir() and (suite_path / "tasks_v1.json").is_file():
        tasks_json_cand = suite_path / "tasks_v1.json"

    if tasks_json_cand is not None:
        ab_res = run_ab_benchmark(workspace_root=base_root, suite_path=tasks_json_cand)
        return {
            "executed": True, "passed": bool(ab_res["passed"]), "pass_rate_pct": float(ab_res["ab_success_full"]),
            "total": int(ab_res["tasks_total"]), "passed_count": int(ab_res["tasks_passed"]),
            "failed_count": int(ab_res["tasks_failed"]), "tests_failed": int(ab_res["tasks_failed"]),
            "tests_passed": int(ab_res["tasks_passed"]), "tests_total": int(ab_res["tasks_total"]),
            "duration_s": None, "suite_path": str(tasks_json_cand),
            "details": f"Benchmark A/B: {ab_res['tasks_passed']}/{ab_res['tasks_total']} passed.",
        }

    stg_tests_dir = base_root / ".staging" / "tests"
    prod_tests_dir = base_root / "tests"
    pytest_targets: List[str] = []

    if suite_path.is_dir() and suite_path.resolve() in (prod_tests_dir.resolve(), stg_tests_dir.resolve()) and stg_tests_dir.is_dir():
        del_manifest = base_root / ".staging" / ".deleted_files.json"
        deleted_rel: set[str] = set()
        if del_manifest.is_file():
            try:
                raw_del = json.loads(del_manifest.read_text(encoding="utf-8"))
                del_items = raw_del.get("deleted_files", []) if isinstance(raw_del, dict) else raw_del
                if isinstance(del_items, list):
                    deleted_rel = {str(item).replace("\\", "/").lstrip("/") for item in del_items}
            except Exception:
                deleted_rel = set()
        overlay_tests: Dict[str, Path] = {}
        if prod_tests_dir.is_dir():
            for tf in sorted(prod_tests_dir.rglob("test_*.py")):
                if "__pycache__" not in tf.parts:
                    rel_k = tf.relative_to(prod_tests_dir).as_posix()
                    if f"tests/{rel_k}" not in deleted_rel:
                        overlay_tests[rel_k] = tf
        for tf in sorted(stg_tests_dir.rglob("test_*.py")):
            if "__pycache__" not in tf.parts:
                overlay_tests[tf.relative_to(stg_tests_dir).as_posix()] = tf
        pytest_targets = [str(overlay_tests[k]) for k in sorted(overlay_tests)]
    elif suite_path.exists():
        pytest_targets = [str(suite_path)]

    if not pytest_targets:
        return {
            "executed": False, "passed": False, "tests_failed": 1, "tests_passed": 0,
            "tests_total": 1, "duration_s": None, "suite_path": str(suite_path),
            "details": f"Benchmark suite non trovata: {suite_path}",
        }

    env = os.environ.copy()
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})

    bv_mod = sys.modules.get("_internal.rsi_convergence_engine.benchmark_and_vibe")
    sp_mod = getattr(bv_mod, "subprocess", subprocess) if bv_mod is not None else subprocess
    mirror_dir: Optional[Path] = None
    bt_tmp_dir: Optional[Path] = None
    try:
        if not is_temp_workspace(base_root):
            mirror_dir = mirror_workspace_to_nvme(base_root, prefix="nk_rsi_iso_", apply_overlay=True)
            run_cwd = mirror_dir
            run_targets = (
                [str(mirror_dir / "tests")]
                if suite_path.is_dir() and suite_path.resolve() in (prod_tests_dir.resolve(), stg_tests_dir.resolve())
                else _remap_targets_to_mirror(pytest_targets, base_root, mirror_dir)
            )
            env["PYTHONPATH"] = str(mirror_dir)
            basetemp = mirror_dir.parent / "bt"
            basetemp.mkdir(parents=True, exist_ok=True)
        else:
            run_cwd = base_root
            run_targets = pytest_targets
            py_paths = [str(base_root / ".staging")] if (base_root / ".staging").is_dir() else []
            py_paths.append(str(base_root))
            if existing_pp := env.get("PYTHONPATH", ""):
                py_paths.append(existing_pp)
            env["PYTHONPATH"] = os.pathsep.join(py_paths)
            bt_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_rsi_bt_"))
            basetemp = bt_tmp_dir

        t0 = time.perf_counter()
        proc = sp_mod.run(
            [
                sys.executable, "-B", "-u", "-m", "pytest", *run_targets,
                "-p", "no:cacheprovider", f"--basetemp={basetemp.as_posix()}", "-q",
            ],
            cwd=str(run_cwd),
            env=env,
            stdin=getattr(sp_mod, "DEVNULL", subprocess.DEVNULL),
            creationflags=win32_detached_flags(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
            shell=False,
        )
        duration_s = round(time.perf_counter() - t0, 2)
        combined = f"{proc.stdout}\n{proc.stderr}"
        m_fail = re.search(r"(\d+)\s+failed", combined)
        m_err = re.search(r"(\d+)\s+errors?", combined)
        m_pass = re.search(r"(\d+)\s+passed", combined)
        m_skip = re.search(r"(\d+)\s+skipped", combined)
        m_xfail = re.search(r"(\d+)\s+xfailed", combined)
        m_desel = re.search(r"(\d+)\s+deselected", combined)

        t_fail = (int(m_fail.group(1)) if m_fail else 0) + (int(m_err.group(1)) if m_err else 0)
        t_pass = int(m_pass.group(1)) if m_pass else 0
        t_skip = int(m_skip.group(1)) if m_skip else 0
        t_xfail = int(m_xfail.group(1)) if m_xfail else 0
        t_desel = int(m_desel.group(1)) if m_desel else 0
        if proc.returncode != 0 and t_fail == 0:
            t_fail = 1
        t_total = t_pass + t_fail + t_skip

        if t_total == 0:
            return {
                "executed": True, "passed": False, "pass_rate_pct": 0.0, "total": 0,
                "passed_count": 0, "failed_count": 1, "skipped_count": 0, "xfailed_count": 0,
                "deselected_count": t_desel, "tests_failed": 1, "tests_passed": 0, "tests_total": 1,
                "duration_s": duration_s, "suite_path": str(suite_path),
                "details": "Benchmark pytest: 0 test raccolti (suite vuota rifiutata).",
            }

        suite_ok = t_fail == 0 and t_skip == 0 and proc.returncode == 0 and t_pass > 0
        return {
            "executed": True, "passed": suite_ok, "pass_rate_pct": round((float(t_pass) / float(t_total)) * 100.0, 2),
            "total": t_total, "passed_count": t_pass, "failed_count": t_fail, "skipped_count": t_skip,
            "xfailed_count": t_xfail, "deselected_count": t_desel, "tests_failed": t_fail + t_skip,
            "tests_passed": t_pass, "tests_total": t_total, "duration_s": duration_s,
            "suite_path": str(suite_path),
            "details": f"Benchmark pytest: {t_pass} passed, {t_fail} failed, {t_skip} skipped.",
        }
    except Exception as exc:
        return {
            "executed": False, "passed": False, "tests_failed": 1, "tests_passed": 0,
            "tests_total": 1, "duration_s": None, "suite_path": str(suite_path),
            "details": f"Errore esecuzione benchmark suite: {exc}",
        }
    finally:
        if bt_tmp_dir is not None:
            safe_rmtree(bt_tmp_dir)
        if mirror_dir is not None:
            safe_rmtree(mirror_dir.parent)

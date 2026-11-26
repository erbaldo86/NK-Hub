# -*- coding: utf-8 -*-
"""Misurazione metriche Pytest reali (parser SSOT tas_ssot_io) e copertura branch NVMe."""

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
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.isolated_test_runner import (
    _kill_detached_tree,
    is_temp_workspace,
    mirror_workspace_to_nvme,
    safe_rmtree,
    win32_detached_flags,
)
from _internal.nk_common.lane_paths import resolve_staging_dir
from _internal.nk_common.pytest_parallel import resolve_coverage_source, run_parallel_pytest_shards, should_use_parallel_shards
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest, parse_pytest_summary
from _internal.quality_baseline_manager.constants import _facade_attr, _scripts_dir

_ORIG_SUBPROCESS_RUN = subprocess.run
_TESTSUITES_TIME_RE = re.compile(r'<testsuites\b[^>]*\btime="([0-9]+(?:\.[0-9]+)?)"')


def _count_live_skills_overlay(ws_root: Path, deleted_rel: set[str], stg_dir: Optional[Path] = None) -> int:
    """Conta le skill canoniche con SKILL.md applicando overlay .staging/lane e tombstone."""
    eff_stg = stg_dir or (ws_root / ".staging")
    skill_dirs: set[str] = set()
    prod_skills = ws_root / ".agents" / "skills"
    if prod_skills.is_dir():
        for sk_md in prod_skills.glob("*/SKILL.md"):
            if f".agents/skills/{sk_md.parent.name}/SKILL.md" not in deleted_rel:
                skill_dirs.add(sk_md.parent.name)
    stg_skills = eff_stg / ".agents" / "skills"
    if stg_skills.is_dir():
        for sk_md in stg_skills.glob("*/SKILL.md"):
            skill_dirs.add(sk_md.parent.name)
    return len(skill_dirs)


def _extract_coverage_totals(cov_json: Path) -> Dict[str, float]:
    """Estrae statement, true branch e combined coverage dal report JSON di pytest-cov."""
    if not cov_json.is_file():
        return {}
    try:
        cov_data = json.loads(cov_json.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
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
    return {
        "statement_coverage_pct": round(float(raw_stmt), 2),
        "true_branch_coverage_pct": round(float(raw_branch), 2),
        "combined_coverage_pct": round(float(raw_branch if raw_comb is None else raw_comb), 2),
    }


def _load_deleted_rel(del_manifest: Path) -> set[str]:
    """Carica il set normalizzato dei percorsi rimossi tramite parse_deleted_files_manifest."""
    try:
        items = parse_deleted_files_manifest(del_manifest)
    except (OSError, ValueError):
        return set()
    return {str(item).replace("\\", "/").lstrip("/") for item in items if str(item).strip()}


def _collect_overlay_tests(ws_root: Path, deleted_rel: set[str], stg_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Raccoglie i file test_*.py attivi in overlay staging/lane > produzione."""
    prod_tests = ws_root / "tests"
    stg_tests = (stg_dir or (ws_root / ".staging")) / "tests"
    overlay_tests: Dict[str, Path] = {}
    if prod_tests.is_dir():
        for tf in sorted(prod_tests.rglob("test_*.py")):
            if "__pycache__" not in tf.parts:
                rel_k = tf.relative_to(prod_tests).as_posix()
                if f"tests/{rel_k}" not in deleted_rel:
                    overlay_tests[rel_k] = tf
    if stg_tests.is_dir():
        for tf in sorted(stg_tests.rglob("test_*.py")):
            if "__pycache__" not in tf.parts:
                overlay_tests[tf.relative_to(stg_tests).as_posix()] = tf
    return overlay_tests


def _collect_overlay_py_scripts(ws_root: Path, eff_stg: Path, deleted_rel: set[str]) -> Dict[str, Path]:
    """Raccoglie i file Python attivi in scripts/ combinando produzione e staging/lane."""
    prod_scripts, stg_scripts = ws_root / "scripts", eff_stg / "scripts"
    py_map: Dict[str, Path] = {}
    if prod_scripts.is_dir():
        for pf in sorted(prod_scripts.rglob("*.py")):
            if "__pycache__" not in pf.parts:
                rel_k = pf.relative_to(ws_root).as_posix()
                if rel_k not in deleted_rel:
                    py_map[rel_k] = pf
    if stg_scripts.is_dir():
        for pf in sorted(stg_scripts.rglob("*.py")):
            if "__pycache__" not in pf.parts:
                py_map[pf.relative_to(eff_stg).as_posix()] = pf
    return py_map


def _measure_live_sast_violations(ws_root: Path, deleted_rel: set[str], stg_dir: Optional[Path] = None) -> Optional[int]:
    """Conta in sola lettura le violazioni SAST live nei file Python attivi se scripts/ esiste."""
    eff_stg = stg_dir or (ws_root / ".staging")
    if not (ws_root / "scripts").is_dir() and not (eff_stg / "scripts").is_dir():
        return None
    try:
        from ast_guard_validator import ASTGuardValidator
    except ImportError:
        try:
            from scripts.ast_guard_validator import ASTGuardValidator
        except ImportError:
            return 1
    py_map = _collect_overlay_py_scripts(ws_root, eff_stg, deleted_rel)
    sast_cnt = 0
    for pf in py_map.values():
        try:
            txt = pf.read_text(encoding="utf-8-sig", errors="replace")
            sast_cnt += len(ASTGuardValidator.check_sast_constructs(txt, target_file=pf.as_posix()))
        except OSError:
            sast_cnt += 1
    return sast_cnt


def _build_qbm_env() -> Dict[str, str]:
    """Costruisce l'ambiente base UTF-8 con plugin autoload disabilitato e parallelismo NVMe."""
    env = os.environ.copy()
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    env.setdefault("NK_PYTEST_WORKERS", str(min(12, max(2, os.cpu_count() or 4))))
    for cov_env_k in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"):
        env.pop(cov_env_k, None)
    return env


def _extract_junit_wall_s(junit_xml: Path, fallback_s: float) -> float:
    """Estrae il wall-time parallelo reale dal tag root JUnit separandolo dal combine coverage."""
    try:
        head = junit_xml.read_text(encoding="utf-8-sig", errors="ignore")[:512] if junit_xml.is_file() else ""
    except OSError:
        head = ""
    if (match := _TESTSUITES_TIME_RE.search(head)) is not None and (val := float(match.group(1))) > 0.0:
        return round(val, 2)
    return round(float(fallback_s), 2)


def _prepare_qbm_targets(
    ws_root: Path, mirror_dir: Optional[Path], overlay_tests: Dict[str, Path], env: Dict[str, str], stg_dir: Optional[Path] = None,
) -> Tuple[Path, List[str]]:
    """Configura PYTHONPATH e target pytest per mirror NVMe o workspace temporaneo."""
    if mirror_dir is not None:
        env["PYTHONPATH"] = str(mirror_dir)
        return mirror_dir, [str(mirror_dir / "tests")]
    eff_stg = stg_dir or (ws_root / ".staging")
    py_paths = ([str(eff_stg)] if eff_stg.is_dir() else []) + [str(ws_root)]
    if existing_pp := env.get("PYTHONPATH", ""):
        py_paths.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(py_paths)
    stg_tests_dir = eff_stg / "tests"
    tgts = [str(overlay_tests[k]) for k in sorted(overlay_tests)] if stg_tests_dir.is_dir() else [str(ws_root / "tests")]
    return ws_root, tgts


def _can_use_qbm_parallel(is_real_ws: bool, overlay_len: int, sub_mod: Any) -> bool:
    """Abilita lo sharding NVMe solo su workspace reale con >=4 file e subprocess intatto."""
    return is_real_ws and overlay_len >= 4 and sub_mod is subprocess and getattr(sub_mod, "run", None) is _ORIG_SUBPROCESS_RUN


def _run_qbm_parallel_nvme(mirror_dir: Path, env: Dict[str, str], with_coverage: bool) -> Optional[Tuple[Dict[str, Any], Dict[str, float], float, int]]:
    """Esegue pytest parallelo su mirror NVMe restituendo metriche o None per fallback."""
    par_files = should_use_parallel_shards(["tests"], ("-q", "--tb=no"), mirror_dir, env)
    if not par_files:
        return None
    run_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_qbm_par_"))
    try:
        cov_json, junit_xml = (run_tmp_dir / "cov.json") if with_coverage else None, run_tmp_dir / "junit.xml"
        par = run_parallel_pytest_shards(
            mirror_dir=mirror_dir, mirror_root=mirror_dir.parent, test_files=par_files, base_env=env,
            extra_args=("-q", "--tb=no"), timeout_sec=300.0 if with_coverage else 240.0,
            coverage=with_coverage, cov_json=cov_json, junit_xml_path=junit_xml,
            log_file=(run_tmp_dir / "par.log"), kill_tree_fn=_kill_detached_tree, detached_flags=win32_detached_flags(),
        )
        parsed = parse_pytest_summary(par["log_text"], "", junit_xml_path=junit_xml)
        cov_metrics = _facade_attr("_extract_coverage_totals", _extract_coverage_totals)(cov_json) if cov_json is not None else {}
        return parsed, cov_metrics, _extract_junit_wall_s(junit_xml, float(par["duration_s"])), int(par["rc"])
    finally:
        safe_rmtree(run_tmp_dir)


def _run_qbm_single_nvme(run_cwd: Path, pytest_targets: List[str], env: Dict[str, str], with_coverage: bool, sub_mod: Any) -> Tuple[Dict[str, Any], Dict[str, float], float, int]:
    """Esegue pytest single-process tramite sub_mod.run per unit test o fallback."""
    cov_tmp_dir: Optional[Path] = None
    bt_tmp_dir: Optional[Path] = None
    cov_metrics: Dict[str, float] = {}
    try:
        if with_coverage:
            cov_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_qbm_cov_"))
            cov_json, cov_basetemp = cov_tmp_dir / "cov.json", cov_tmp_dir / "bt"
            cov_basetemp.mkdir(parents=True, exist_ok=True)
            env["COVERAGE_FILE"] = str(cov_tmp_dir / ".coverage")
            cov_plugin_args = ["-p", "pytest_cov"] if env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") else []
            cov_src = resolve_coverage_source(run_cwd)
            cmd = [sys.executable, "-B", "-u", "-m", "pytest", *pytest_targets, "-p", "no:cacheprovider", *cov_plugin_args, f"--cov={cov_src}", "--cov-branch", f"--cov-report=json:{cov_json.as_posix()}", f"--basetemp={cov_basetemp.as_posix()}", "-q", "--tb=no"]
        else:
            bt_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_qbm_bt_"))
            cmd = [sys.executable, "-B", "-u", "-m", "pytest", *pytest_targets, "-p", "no:cacheprovider", f"--basetemp={bt_tmp_dir.as_posix()}", "-q", "--tb=no"]
        t0 = time.perf_counter()
        proc = sub_mod.run(cmd, cwd=str(run_cwd), env=env, stdin=getattr(sub_mod, "DEVNULL", subprocess.DEVNULL), creationflags=win32_detached_flags(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300 if with_coverage else 240, shell=False)
        duration_s = round(time.perf_counter() - t0, 2)
        if with_coverage:
            cov_metrics = _facade_attr("_extract_coverage_totals", _extract_coverage_totals)(cov_json)
    finally:
        for tmp_d in (cov_tmp_dir, bt_tmp_dir):
            if tmp_d is not None:
                safe_rmtree(tmp_d)
    return parse_pytest_summary(proc.stdout or "", proc.stderr or ""), cov_metrics, duration_s, int(proc.returncode)


def _compute_qbm_counts(parsed: Dict[str, Any], rc: int) -> Tuple[int, int, int, int, int, int, float]:
    """Calcola (passed, failed, skipped, xfailed, deselected, total, pass_rate) includendo xfailed/deselected."""
    passed = int(parsed.get("passed", 0))
    raw_skipped, xfailed = int(parsed.get("skipped", 0)), int(parsed.get("xfailed", 0))
    deselected = int(parsed.get("deselected", 0))
    skipped = int(parsed.get("tests_skipped", raw_skipped + xfailed))
    if "tests_skipped" in parsed and "skipped" in parsed and "xfailed" in parsed:
        skipped = max(skipped, raw_skipped + xfailed)
    failed = int(parsed.get("failed", 0)) + int(parsed.get("errors", 0))
    failed = 1 if (rc != 0 and failed == 0) else failed
    total = passed + failed + skipped + deselected
    pass_rate = round((passed / total) * 100.0, 2) if total > 0 else 0.0
    return passed, failed, skipped, xfailed, deselected, total, pass_rate


def _format_qbm_live_result(parsed: Dict[str, Any], cov_metrics: Dict[str, float], duration_s: float, rc: int, skills_cnt: int, sast_cnt: Optional[int]) -> Dict[str, Any]:
    """Compone il dizionario metriche Schema v2 dal riepilogo pytest e coverage."""
    passed, failed, skipped, xfailed, deselected, total, pass_rate = _compute_qbm_counts(parsed, rc)
    result: Dict[str, Any] = {
        "total_golden_tests": total, "unit_tests_total": total, "unit_tests_passed": passed,
        "unit_tests_pass_pct": pass_rate, "pass_rate_pct": pass_rate,
        "failed_tests": failed, "tests_skipped": skipped, "pytest_duration_s": duration_s,
    }
    if xfailed > 0:
        result["tests_xfailed"] = xfailed
    if deselected > 0:
        result["tests_deselected"] = deselected
    if skills_cnt > 0:
        result["skills_audited"] = skills_cnt
    if sast_cnt is not None:
        result["sast_critical_violations"] = sast_cnt
    if cov_metrics:
        result.update(cov_metrics)
    return result


def measure_live_pytest_metrics(
    workspace_root: Optional[Path] = None,
    with_coverage: bool = False,
    *,
    lane_id: Optional[str] = None,
    staging_dir: Optional[Path] = None,
) -> dict:
    """Esegue pytest reale NVMe con overlay .staging/[lanes/<id>/] e separa skipped da failed."""
    if workspace_root is None:
        s_dir = Path(_facade_attr("_scripts_dir", _scripts_dir)).resolve()
        ws_root = s_dir.parent.parent if s_dir.parent.name == ".staging" else s_dir.parent
    else:
        ws_root = Path(workspace_root).resolve()

    stg_dir, norm_lane = resolve_staging_dir(ws_root, lane_id=lane_id, staging_dir=staging_dir)
    deleted_rel = _load_deleted_rel(stg_dir / ".deleted_files.json")
    overlay_tests = _collect_overlay_tests(ws_root, deleted_rel, stg_dir=stg_dir)
    skills_cnt = _facade_attr("_count_live_skills_overlay", _count_live_skills_overlay)(ws_root, deleted_rel)
    sast_cnt = _measure_live_sast_violations(ws_root, deleted_rel, stg_dir=stg_dir)
    if not overlay_tests:
        return _format_qbm_live_result({}, {}, 0.0, 0, skills_cnt, sast_cnt)

    env = _build_qbm_env()
    sub_mod = _facade_attr("subprocess", subprocess)
    is_real_ws = not is_temp_workspace(ws_root)
    mirror_dir = mirror_workspace_to_nvme(ws_root, staging_dir=stg_dir, prefix="nk_qbm_iso_", apply_overlay=True, lane_id=norm_lane) if is_real_ws else None
    try:
        run_cwd, pytest_targets = _prepare_qbm_targets(ws_root, mirror_dir, overlay_tests, env, stg_dir=stg_dir)
        can_par = _can_use_qbm_parallel(is_real_ws, len(overlay_tests), sub_mod)
        par_out = _run_qbm_parallel_nvme(mirror_dir, env, with_coverage) if (can_par and mirror_dir is not None) else None
        if par_out is None:
            parsed, cov_metrics, duration_s, rc = _run_qbm_single_nvme(run_cwd, pytest_targets, env, with_coverage, sub_mod)
        else:
            parsed, cov_metrics, duration_s, rc = par_out
    finally:
        if mirror_dir is not None:
            safe_rmtree(mirror_dir.parent)
    return _format_qbm_live_result(parsed, cov_metrics, duration_s, rc, skills_cnt, sast_cnt)

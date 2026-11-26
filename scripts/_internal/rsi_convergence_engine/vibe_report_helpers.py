# -*- coding: utf-8 -*-
"""Audit fail-closed report (SAST/DAST/coverage/mutation) e runner pytest NVMe."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.isolated_test_runner import _kill_detached_tree, is_temp_workspace, mirror_workspace_to_nvme, safe_rmtree, win32_detached_flags
from _internal.nk_common.pytest_parallel import run_parallel_pytest_shards, should_use_parallel_shards
from _internal.nk_common.tas_ssot_io import parse_pytest_summary
from _internal.rsi_convergence_engine.constants import load_staging_deleted_set_impl, normalize_rel_for_root, resolve_effective_staging
from _internal.rsi_convergence_engine.report_sanitizers import (
    _BENCH_COV_KEYS,
    audit_coverage_report_payload,
    audit_dast_report_payload,
    audit_mutation_report_payload,
    audit_sast_report_payload,
    injected_check_passed_ext,
    parse_injected_counts_ext,
)

_STDLIB_SUBPROCESS = subprocess
_STDLIB_DEVNULL = subprocess.DEVNULL
_ORIG_SUBPROCESS_RUN = subprocess.run


def _has_auto_test_files(root: Path, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> bool:
    stg_root = resolve_effective_staging(root, lane_id=lane_id, staging_dir=staging_dir)
    return any(cand.is_dir() and any(cand.rglob("test_*.py")) for cand in (root / "tests", stg_root / "tests"))


def _resolve_benchmark_suite_path(base_root: Path, engine: Any, benchmark_suite: Path | str, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Path:
    raw_p = Path(benchmark_suite)
    if raw_p.is_absolute():
        return raw_p
    norm_rel = normalize_rel_for_root(base_root, str(benchmark_suite))
    stg_root = resolve_effective_staging(base_root, lane_id=lane_id, staging_dir=staging_dir)
    for cand in (stg_root / norm_rel, base_root / norm_rel, engine.workspace_root / ".staging" / norm_rel):
        if cand.exists():
            return cand.resolve()
    return (base_root / norm_rel).resolve()


def _collect_pytest_targets(suite_path: Path, base_root: Path, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> List[str]:
    if suite_path.is_file() and suite_path.suffix == ".py":
        return [str(suite_path.resolve())]
    if not suite_path.is_dir():
        return []
    stg_root = resolve_effective_staging(base_root, lane_id=lane_id, staging_dir=staging_dir)
    stg_tests, prod_tests = stg_root / "tests", base_root / "tests"
    if suite_path.resolve() not in (prod_tests.resolve(), stg_tests.resolve()) or not stg_tests.is_dir():
        return [str(suite_path.resolve())] if any(suite_path.rglob("test_*.py")) else []
    deleted_rel, overlay = load_staging_deleted_set_impl(base_root, lane_id=lane_id, staging_dir=staging_dir), {}
    if prod_tests.is_dir():
        for tf in sorted(prod_tests.rglob("test_*.py")):
            if "__pycache__" not in tf.parts and f"tests/{tf.relative_to(prod_tests).as_posix()}" not in deleted_rel:
                overlay[tf.relative_to(prod_tests).as_posix()] = tf
    for tf in sorted(stg_tests.rglob("test_*.py")):
        if "__pycache__" not in tf.parts:
            overlay[tf.relative_to(stg_tests).as_posix()] = tf
    return [str(overlay[k]) for k in sorted(overlay.keys())]


def _map_mirror_target(t_str: str, base_root: Path, mirror_dir: Path, stg_root: Optional[Path] = None) -> str:
    tp, stg_res = Path(t_str).resolve(), (stg_root if stg_root is not None else (base_root / ".staging")).resolve()
    if tp.is_relative_to(stg_res):
        return str(mirror_dir / tp.relative_to(stg_res))
    return str(mirror_dir / tp.relative_to(base_root.resolve())) if tp.is_relative_to(base_root.resolve()) else t_str


def _build_nvme_mirror_kwargs(stg_root: Path, lane_id: Optional[str], staging_dir: Optional[Path]) -> Dict[str, Any]:
    m_kw: Dict[str, Any] = {"prefix": "nk_rsi_iso_", "apply_overlay": True}
    if staging_dir is not None:
        m_kw["staging_dir"] = stg_root
    elif lane_id is not None:
        m_kw["lane_id"] = lane_id
    return m_kw


def _prepare_pytest_execution(base_root: Path, suite_path: Path, pytest_targets: List[str], env: Dict[str, str], lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Tuple[Path, List[str], Path, Optional[Path], Optional[Path]]:
    stg_root = resolve_effective_staging(base_root, lane_id=lane_id, staging_dir=staging_dir)
    stg_tests, prod_tests = stg_root / "tests", base_root / "tests"
    if not is_temp_workspace(base_root):
        mirror_dir = mirror_workspace_to_nvme(base_root, **_build_nvme_mirror_kwargs(stg_root, lane_id, staging_dir))
        is_tests_dir = suite_path.is_dir() and suite_path.resolve() in (prod_tests.resolve(), stg_tests.resolve())
        targets = [str(mirror_dir / "tests")] if is_tests_dir else [_map_mirror_target(t, base_root, mirror_dir, stg_root=stg_root) for t in pytest_targets]
        env["PYTHONPATH"] = str(mirror_dir)
        basetemp = mirror_dir.parent / "bt"
        basetemp.mkdir(parents=True, exist_ok=True)
        return mirror_dir, targets, basetemp, mirror_dir, None
    py_paths = ([str(stg_root)] if stg_root.is_dir() else []) + [str(base_root)]
    if existing_pp := env.get("PYTHONPATH", ""):
        py_paths.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(py_paths)
    bt_tmp_dir = Path(tempfile.mkdtemp(prefix="nk_rsi_bt_"))
    return base_root, pytest_targets, bt_tmp_dir, None, bt_tmp_dir


def _build_rsi_pytest_env() -> Dict[str, str]:
    """Prepara ambiente UTF-8 isolato senza plugin autoload e senza residui coverage."""
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NK_SKIP_PYTEST_MIRROR_HINT": "1",
    }
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    env.setdefault("NK_PYTEST_WORKERS", str(min(6, max(2, os.cpu_count() or 4))))
    for cov_k in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"):
        env.pop(cov_k, None)
    return env


def _format_parsed_pytest_outcome(parsed: Dict[str, Any], returncode: int, suite_path: Path, duration_s: float) -> Dict[str, Any]:
    """Compone l'esito normalizzato della benchmark suite dal riepilogo pytest."""
    t_pass = int(parsed.get("passed", 0))
    t_skip = int(parsed.get("tests_skipped", parsed.get("skipped", 0)))
    t_xfail, t_desel = int(parsed.get("xfailed", 0)), int(parsed.get("deselected", 0))
    t_fail = int(parsed.get("failed", 0)) + int(parsed.get("errors", 0))
    if returncode != 0 and t_fail == 0:
        t_fail = 1
    t_total = t_pass + t_fail + t_skip
    if t_total == 0:
        return {"executed": True, "executed_pytest": True, "passed": False, "pass_rate_pct": 0.0, "total": 0, "passed_count": 0, "failed_count": 1, "skipped_count": 0, "tests_skipped": 0, "xfailed_count": t_xfail, "deselected_count": t_desel, "tests_failed": 1, "tests_passed": 0, "tests_total": 1, "duration_s": duration_s, "suite_path": str(suite_path), "details": "Benchmark pytest: 0 test raccolti (suite vuota rifiutata)."}
    suite_ok = t_fail == 0 and t_skip == 0 and t_xfail == 0 and t_desel == 0 and returncode == 0 and t_pass > 0
    return {"executed": True, "executed_pytest": True, "passed": suite_ok, "pass_rate_pct": round((float(t_pass) / float(t_total)) * 100.0, 2), "total": t_total, "passed_count": t_pass, "failed_count": t_fail, "skipped_count": t_skip, "tests_skipped": t_skip, "xfailed_count": t_xfail, "deselected_count": t_desel, "tests_failed": t_fail, "tests_passed": t_pass, "tests_total": t_total, "duration_s": duration_s, "suite_path": str(suite_path), "details": f"Benchmark pytest: {t_pass} passed, {t_fail} failed, {t_skip} skipped, {t_xfail} xfailed, {t_desel} deselected."}


def _build_pytest_outcome(proc: Any, suite_path: Path, duration_s: float) -> Dict[str, Any]:
    return _format_parsed_pytest_outcome(parse_pytest_summary(proc.stdout, proc.stderr), int(proc.returncode), suite_path, duration_s)


def _normalize_mirror_rel_targets(mirror_dir: Path, run_targets: List[str]) -> List[str]:
    m_res = mirror_dir.resolve()
    rel_targets: List[str] = []
    for raw_t in run_targets:
        tp = Path(raw_t).resolve()
        rel_targets.append(tp.relative_to(m_res).as_posix() if tp.is_relative_to(m_res) else str(raw_t))
    return rel_targets or ["tests"]


def _run_rsi_parallel_nvme(mirror_dir: Path, run_targets: List[str], env: Dict[str, str], suite_path: Path) -> Optional[Dict[str, Any]]:
    """Esegue la suite pytest con sharding parallelo NVMe quando idoneo."""
    rel_targets = _normalize_mirror_rel_targets(mirror_dir, run_targets)
    par_files = should_use_parallel_shards(rel_targets, ("-q",), mirror_dir, env)
    if not par_files:
        return None
    par_tmp = Path(tempfile.mkdtemp(prefix="nk_rsi_par_"))
    try:
        junit_xml = par_tmp / "junit.xml"
        par = run_parallel_pytest_shards(
            mirror_dir=mirror_dir, mirror_root=mirror_dir.parent, test_files=par_files, base_env=env,
            extra_args=("-q",), timeout_sec=240.0, coverage=False, junit_xml_path=junit_xml,
            log_file=(par_tmp / "par.log"), kill_tree_fn=_kill_detached_tree, detached_flags=win32_detached_flags(),
        )
        parsed = parse_pytest_summary(par["log_text"], "", junit_xml_path=junit_xml)
        return _format_parsed_pytest_outcome(parsed, int(par["rc"]), suite_path, round(float(par["duration_s"]), 2))
    finally:
        safe_rmtree(par_tmp)


def _pick_subprocess_mod() -> Any:
    bv_mod = sys.modules.get("_internal.rsi_convergence_engine.benchmark_and_vibe")
    bv_sub = getattr(bv_mod, "subprocess", None) if bv_mod is not None else None
    return bv_sub if (bv_sub is not None and bv_sub is not _STDLIB_SUBPROCESS) else subprocess


def _execute_prepared_benchmark(
    run_cwd: Path, run_targets: List[str], basetemp: Path, mirror_dir: Optional[Path],
    sp_mod: Any, env: Dict[str, str], suite_path: Path,
) -> Dict[str, Any]:
    """Esegue la suite pytest in NVMe sharded o fallback single-process."""
    if mirror_dir is not None and sp_mod is subprocess and getattr(sp_mod, "run", None) is _ORIG_SUBPROCESS_RUN:
        if (par_res := _run_rsi_parallel_nvme(mirror_dir, run_targets, env, suite_path)) is not None:
            return par_res
    t0 = time.perf_counter()
    proc = sp_mod.run(
        [sys.executable, "-B", "-u", "-m", "pytest", *run_targets, "-p", "no:cacheprovider", "--import-mode=importlib", f"--basetemp={basetemp.as_posix()}", "-q"],
        cwd=str(run_cwd), env=env, stdin=getattr(sp_mod, "DEVNULL", _STDLIB_DEVNULL),
        creationflags=win32_detached_flags(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, shell=False,
    )
    return _build_pytest_outcome(proc, suite_path, round(time.perf_counter() - t0, 2))


def run_benchmark_suite_impl(engine: Any, benchmark_suite: Path | str, root_dir: Optional[Path] = None, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Esegue pytest reale isolato (-B, NVMe) mantenendo tests_skipped separato da tests_failed."""
    base_root = Path(root_dir).resolve() if root_dir else engine.workspace_root
    suite_path = _resolve_benchmark_suite_path(base_root, engine, benchmark_suite, lane_id=lane_id, staging_dir=staging_dir)
    pytest_targets = _collect_pytest_targets(suite_path, base_root, lane_id=lane_id, staging_dir=staging_dir)
    if not pytest_targets:
        return {"executed": False, "executed_pytest": False, "passed": False, "pass_rate_pct": 0.0, "total": 0, "passed_count": 0, "failed_count": 0, "skipped_count": 0, "tests_skipped": 0, "tests_failed": 0, "tests_passed": 0, "tests_total": 0, "duration_s": None, "suite_path": str(suite_path), "details": f"Suite pytest non valida o assente: {suite_path}"}
    env = _build_rsi_pytest_env()
    sp_mod = _pick_subprocess_mod()
    mirror_dir, bt_tmp_dir = None, None
    try:
        run_cwd, run_targets, basetemp, mirror_dir, bt_tmp_dir = _prepare_pytest_execution(base_root, suite_path, pytest_targets, env, lane_id=lane_id, staging_dir=staging_dir)
        return _execute_prepared_benchmark(run_cwd, run_targets, basetemp, mirror_dir, sp_mod, env, suite_path)
    except Exception as exc:
        return {"executed": False, "executed_pytest": False, "passed": False, "tests_failed": 1, "tests_passed": 0, "tests_total": 1, "tests_skipped": 0, "duration_s": None, "suite_path": str(suite_path), "details": f"Errore esecuzione benchmark suite: {exc}"}
    finally:
        if bt_tmp_dir is not None:
            safe_rmtree(bt_tmp_dir)
        if mirror_dir is not None:
            safe_rmtree(mirror_dir.parent)


def _build_injected_check(test_report: Dict[str, Any], counts: Tuple[int, int, int, int, int]) -> Dict[str, Any]:
    b_passed, b_failed, b_skipped, b_xfailed, b_desel = counts
    raw_tot = test_report.get("tests_total", max(0, b_passed + b_failed + b_skipped))
    rep_ok, b_total_i = injected_check_passed_ext(counts, raw_tot)
    bench_cov = {k: test_report[k] for k in _BENCH_COV_KEYS if k in test_report and test_report[k] is not None}
    return {"executed": True, "injected": True, "passed": rep_ok, "tests_passed": b_passed, "tests_failed": b_failed, "tests_skipped": b_skipped, "xfailed_count": b_xfailed, "deselected_count": b_desel, "tests_total": b_total_i, **bench_cov, "details": f"Injected test report: {b_passed}/{b_total_i} passed, {b_skipped} skipped, {b_xfailed} xfailed, {b_desel} deselected."}


def _evaluate_injected_test_report(test_report: Dict[str, Any], measured_components: List[str], checks: Dict[str, Any], violations: List[str]) -> Tuple[int, int, int]:
    """Valuta un test_report iniettato rifiutando status='', campi None o non finiti."""
    valid, bad_label, counts = parse_injected_counts_ext(test_report)
    if not valid or counts is None:
        violations.append(f"Injected test_report incompleto o status invalido ({bad_label}).")
        checks["benchmark_suite"] = {"executed": False, "injected": True, "passed": False, "tests_passed": 0, "tests_failed": 1, "tests_skipped": 0, "xfailed_count": 0, "deselected_count": 0, "tests_total": 0}
        return 1, 0, 0
    measured_components.append("benchmark_suite")
    chk = _build_injected_check(test_report, counts)
    checks["benchmark_suite"] = chk
    if not chk["passed"]:
        violations.append(chk["details"])
    return int(counts[1]), int(counts[0]), int(chk["tests_total"])


def _eval_injected_or_block_strict(
    test_report: Dict[str, Any], strict_verify: bool, allow_injected_in_strict: bool,
    measured_components: List[str], unmeasured_components: List[str], checks: Dict[str, Any], violations: List[str],
) -> Tuple[int, int, int]:
    if strict_verify and not allow_injected_in_strict:
        violations.append("test_report iniettato non consentito con verifica strict CLI.")
        checks["benchmark_suite"] = {"executed": False, "injected": True, "passed": False, "tests_passed": 0, "tests_failed": 1, "tests_skipped": 0, "tests_total": 0}
        unmeasured_components.append("benchmark_suite")
        return 1, 0, 0
    return _evaluate_injected_test_report(test_report, measured_components, checks, violations)


def _call_bench_suite(engine: Any, target: str, root: Path, lane_id: Optional[str], staging_dir: Optional[Path]) -> Dict[str, Any]:
    kw: Dict[str, Any] = {"root_dir": root}
    try:
        params = inspect.signature(engine.run_benchmark_suite).parameters
    except (TypeError, ValueError):
        params = {}
    has_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if lane_id is not None and (has_kw or "lane_id" in params):
        kw["lane_id"] = lane_id
    if staging_dir is not None and (has_kw or "staging_dir" in params):
        kw["staging_dir"] = staging_dir
    return engine.run_benchmark_suite(target, **kw)


def _run_suite_with_strict_fallback(engine: Any, root: Path, benchmark_suite: Optional[str], strict_verify: bool, has_tests: bool, violations: List[str], lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Dict[str, Any]:
    stg_root = resolve_effective_staging(root, lane_id=lane_id, staging_dir=staging_dir)
    prod_tests = root / "tests"
    default_dir = prod_tests if prod_tests.is_dir() else (stg_root / "tests")
    bench_res = _call_bench_suite(engine, benchmark_suite or str(default_dir), root, lane_id, staging_dir)
    if strict_verify and benchmark_suite and not bench_res.get("executed_pytest", False) and has_tests:
        violations.append(bench_res.get("details", "Benchmark suite priva di pytest reale."))
        bench_res = _call_bench_suite(engine, str(default_dir), root, lane_id, staging_dir)
        bench_res["strict_fallback_pytest"] = True
    return bench_res


def evaluate_benchmark_suite_gate(
    engine: Any, root: Path, test_report: Optional[Dict[str, Any]], benchmark_suite: Optional[str],
    should_run_pytest: bool, strict_verify: bool, measured_components: List[str], unmeasured_components: List[str],
    checks: Dict[str, Any], violations: List[str], allow_injected_in_strict: bool = True,
    lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Tuple[int, int, int]:
    """Valuta test_report o suite pytest (CLI strict blocca test_report iniettato)."""
    if isinstance(test_report, dict):
        return _eval_injected_or_block_strict(test_report, strict_verify, allow_injected_in_strict, measured_components, unmeasured_components, checks, violations)
    has_tests = _has_auto_test_files(root, lane_id=lane_id, staging_dir=staging_dir)
    if not (benchmark_suite or should_run_pytest or (strict_verify and has_tests)):
        unmeasured_components.append("benchmark_suite")
        if strict_verify:
            violations.append(f"Nessuna suite di test misurata in modalita --strict-verify per '{root}'.")
        return 0, 0, 0
    bench_res = _run_suite_with_strict_fallback(engine, root, benchmark_suite, strict_verify, has_tests, violations, lane_id=lane_id, staging_dir=staging_dir)
    checks["benchmark_suite"] = bench_res
    target_bucket = measured_components if (bench_res.get("executed_pytest", False) or bench_res.get("executed", False)) else unmeasured_components
    target_bucket.append("benchmark_suite")
    if not bench_res["passed"]:
        violations.append(bench_res["details"])
    return int(bench_res.get("tests_failed", 0)), int(bench_res.get("tests_passed", 0)), int(bench_res.get("tests_total", 0))


__all__ = [
    "audit_coverage_report_payload",
    "audit_dast_report_payload",
    "audit_mutation_report_payload",
    "audit_sast_report_payload",
    "evaluate_benchmark_suite_gate",
    "run_benchmark_suite_impl",
]

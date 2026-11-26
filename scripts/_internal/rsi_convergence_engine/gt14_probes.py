# -*- coding: utf-8 -*-
"""Sonde individuali GT-14 (AST, DAST con verify_holdout=True, Quality Baseline) e bundle."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from _internal.nk_common.epistemic_firewall_rules import strip_l3_persuasive_narrative
from _internal.nk_common.io import atomic_write_text
from _internal.nk_common.isolated_test_runner import is_temp_workspace
from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir
from _internal.rsi_convergence_engine.constants import _scripts_dir, _workspace_root
from _internal.rsi_convergence_engine.ecosystem_verify import verify_ecosystem_impl
from _internal.rsi_convergence_engine.vibe_report_helpers import audit_dast_report_payload


def _is_valid_staged_py(py_file: Path, stg_dir: Path) -> bool:
    if not py_file.is_file() or "__pycache__" in py_file.parts:
        return False
    if stg_dir.name == ".staging":
        rel_parts = py_file.relative_to(stg_dir).parts
        if rel_parts and is_lane_container_entry(rel_parts):
            return False
    return True


def _collect_ast_guard_targets(root: Path, stg_dir: Path) -> Tuple[List[Path], str]:
    """Raccoglie i file .py target da .staging/ o da produzione scripts/ e tests/."""
    staged_py = sorted(p for p in stg_dir.rglob("*.py") if _is_valid_staged_py(p, stg_dir)) if stg_dir.is_dir() else []
    if staged_py:
        return staged_py, "staging"
    prod_py: List[Path] = []
    for sub in ("scripts", "tests"):
        sub_dir = root / sub
        if sub_dir.is_dir():
            prod_py.extend(sorted(p for p in sub_dir.rglob("*.py") if p.is_file() and "__pycache__" not in p.parts))
    return prod_py, "production_scripts_and_tests"


def _count_live_overlay_skills(root: Path, stg_dir: Path) -> int:
    """Conta le skill uniche presenti tra produzione e .staging/."""
    skill_names = set()
    for base in (root / ".agents" / "skills", stg_dir / ".agents" / "skills"):
        if base.is_dir():
            for sk in base.iterdir():
                if sk.is_dir() and (sk / "SKILL.md").is_file():
                    skill_names.add(sk.name)
    return len(skill_names)


def _run_ast_guard_probe(root: Path, stg_dir: Path, load_probe_fn: Callable[[Path, str], Any]) -> Dict[str, Any]:
    """Esegue la sonda AST Guard sui file staged o di produzione."""
    py_targets, ast_scope = _collect_ast_guard_targets(root, stg_dir)
    if not py_targets:
        return {"passed": True, "skipped": True, "files_scanned": 0, "scope": "empty", "reason": "no_python_files_found"}
    try:
        agv_mod = load_probe_fn(root, "ast_guard_validator")
        validator_cls = agv_mod.ASTGuardValidator
        total_v, total_sast, ag_issues = 0, 0, []
        for py_file in py_targets:
            post_code = py_file.read_text(encoding="utf-8")
            prod_counter = agv_mod._resolve_production_counterpart(py_file, root)
            pre_code = prod_counter.read_text(encoding="utf-8") if prod_counter is not None else post_code
            rep = validator_cls.validate_code_edit(pre_code, post_code, target_file=py_file.as_posix())
            total_sast += int(rep.metrics.get("sast_violations_count", 0))
            if not rep.is_valid:
                total_v += len(rep.violations)
                ag_issues.extend(f"{py_file.name}: {v.message}" for v in rep.violations[:5])
        return {
            "passed": total_v == 0, "skipped": False, "scope": ast_scope,
            "files_scanned": len(py_targets), "total_violations": total_v, "sast_critical": total_sast, "issues": ag_issues,
        }
    except Exception as exc:
        return {"passed": False, "skipped": False, "scope": ast_scope, "files_scanned": len(py_targets), "error": f"ast_guard error: {exc}"}


def _audit_external_dast_probe(dast_report: Optional[Union[str, Path]]) -> Dict[str, Any]:
    """Audita un report DAST Shadow Sandbox esterno in modalita fail-closed."""
    if dast_report is None:
        return {"passed": True, "skipped": True}
    ext_res = audit_dast_report_payload(dast_report)
    ext_res["source"] = "external_dast_report"
    return ext_res


def _build_dast_test_report(dast_res: Any) -> Optional[Dict[str, Any]]:
    """Estrae i campi test_report dal dizionario risultato di dast_sandbox_runner."""
    dast_pt = dast_res.get("pytest", {}) if isinstance(dast_res, dict) else {}
    if not (isinstance(dast_pt, dict) and dast_pt.get("executed")):
        return None
    rep: Dict[str, Any] = {
        "tests_passed": int(dast_pt.get("tests_passed", 0)), "tests_failed": int(dast_pt.get("tests_failed", 0)),
        "tests_skipped": int(dast_pt.get("tests_skipped", 0)),
        "xfailed_count": int(dast_pt.get("xfailed_count", dast_pt.get("xfailed", 0))),
        "deselected_count": int(dast_pt.get("deselected_count", dast_pt.get("deselected", 0))),
        "tests_total": int(dast_pt.get("tests_total", 0)),
    }
    for opt_k in ("duration_s", "branch_coverage_pct", "statement_coverage_pct", "true_branch_coverage_pct", "combined_coverage_pct"):
        if opt_k in dast_pt and dast_pt.get(opt_k) is not None:
            rep[opt_k] = dast_pt[opt_k]
    return rep


def _run_dast_probe(
    root: Path, stg_dir: Path, with_dast: bool, load_probe_fn: Callable[[Path, str], Any],
    dast_report: Optional[Union[str, Path]] = None, lane_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Esegue la sonda DAST overlay in shadow sandbox con verify_holdout=True esplicito."""
    if not with_dast:
        return _audit_external_dast_probe(dast_report), None
    try:
        dast_mod = load_probe_fn(root, "dast_sandbox_runner")
        dast_kw: Dict[str, Any] = {"repo_root": root, "staging_dir": stg_dir, "profile": "evaluator", "verify_holdout": True}
        if lane_id is not None and "lane_id" in inspect.signature(dast_mod.run_staging_shadow_verification).parameters:
            dast_kw["lane_id"] = lane_id
        dast_res = dast_mod.run_staging_shadow_verification(**dast_kw)
        return dast_res, _build_dast_test_report(dast_res)
    except Exception as exc:
        return {"passed": False, "status": "ERROR", "error": f"dast_overlay error: {exc}"}, None


def _pick_probe_num(bench_res: Dict[str, Any], dast_report: Optional[Dict[str, Any]], key: str) -> Optional[float]:
    val = bench_res.get(key)
    if val is None and isinstance(dast_report, dict):
        val = dast_report.get(key)
    return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None


def _extract_bench_live_fields(bench_res: Dict[str, Any], dast_test_report: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], float]:
    t_pass, t_fail = int(bench_res.get("tests_passed", 0)), int(bench_res.get("tests_failed", 0))
    t_skip = int(bench_res.get("tests_skipped", bench_res.get("skipped_count", 0)))
    t_tot = int(bench_res.get("tests_total", t_pass + t_fail + t_skip))
    pass_rate = round((float(t_pass) / float(t_tot)) * 100.0, 2) if t_tot > 0 else 0.0
    out: Dict[str, Any] = {
        "total_golden_tests": t_tot, "unit_tests_total": t_tot, "unit_tests_passed": t_pass,
        "unit_tests_pass_pct": pass_rate, "pass_rate_pct": pass_rate, "failed_tests": t_fail, "tests_skipped": t_skip,
    }
    if (dur := _pick_probe_num(bench_res, dast_test_report, "duration_s")) is not None:
        out["pytest_duration_s"] = dur
    for cov_k in ("branch_coverage_pct", "statement_coverage_pct", "true_branch_coverage_pct", "combined_coverage_pct"):
        if (cov_v := _pick_probe_num(bench_res, dast_test_report, cov_k)) is not None:
            out[cov_k] = cov_v
    return out, pass_rate


def _extract_probe_live_metrics(
    root: Path, stg_dir: Path, probes: Dict[str, Any], dast_test_report: Optional[Dict[str, Any]], strict_verify: bool
) -> Tuple[Dict[str, Any], bool, float]:
    """Estrae le metriche live misurate dalle sonde AST/RSI/DAST."""
    rsi_res = probes.get("rsi_verify", {})
    bench_res = rsi_res.get("checks", {}).get("benchmark_suite", {}) if isinstance(rsi_res, dict) else {}
    live_tests_measured = bool(isinstance(bench_res, dict) and bench_res.get("executed"))
    cur_metrics, pass_rate = _extract_bench_live_fields(bench_res, dast_test_report) if live_tests_measured else ({}, 0.0)
    skills_count = _count_live_overlay_skills(root, stg_dir)
    if skills_count > 0:
        cur_metrics["skills_audited"] = skills_count
    if not probes.get("ast_guard", {}).get("skipped", True):
        cur_metrics["sast_critical_violations"] = int(probes["ast_guard"].get("sast_critical", 0))
    if isinstance(rsi_res, dict) and "delta_k" in rsi_res:
        cur_metrics["rsi_residual_delta"] = int(rsi_res.get("delta_k", 0))
        if live_tests_measured or strict_verify:
            cur_metrics["rsi_convergence_score"] = float(rsi_res.get("fitness_q", 0.0))
    return cur_metrics, live_tests_measured, pass_rate


def _run_quality_baseline_probe(
    root: Path, stg_dir: Path, probes: Dict[str, Any], dast_test_report: Optional[Dict[str, Any]],
    load_probe_fn: Callable[[Path, str], Any], strict_verify: bool = False,
) -> Dict[str, Any]:
    """Verifica compliance e metriche live rispetto a quality_baseline.json."""
    try:
        qbm_mod = load_probe_fn(root, "quality_baseline_manager")
        stg_bl, prod_bl = stg_dir / "nk_tracking" / "quality_baseline.json", root / "nk_tracking" / "quality_baseline.json"
        bl_path = stg_bl if stg_bl.is_file() else prod_bl
        if not bl_path.is_file():
            return {"passed": False, "status": "MISSING", "baseline_path": str(bl_path), "details": "quality_baseline.json non trovato."}
        cur_metrics, live_tests_measured, pass_rate = _extract_probe_live_metrics(root, stg_dir, probes, dast_test_report, strict_verify)
        comp_res = qbm_mod.check_baseline_compliance(str(bl_path), cur_metrics, allow_ratchet_down=False)
        qb_passed = bool(live_tests_measured and pass_rate >= 100.0 and comp_res.get("verdict") == "PASS")
        details = comp_res.get("details", "")
        if not live_tests_measured and comp_res.get("verdict") == "PASS":
            details = "Suite test non misurata dal vivo: esegui con --strict-verify o --with-dast."
        return {
            "passed": qb_passed,
            "status": comp_res.get("status", "SUCCESS") if live_tests_measured else "UNMEASURED",
            "verdict": comp_res.get("verdict", "FAIL") if live_tests_measured else "UNMEASURED",
            "baseline_path": str(bl_path), "pass_rate_pct": pass_rate, "live_tests_measured": live_tests_measured,
            "schema_valid": bool(cur_metrics), "metrics_checked": comp_res.get("metrics_checked", 0),
            "regressions": comp_res.get("regressions", []), "details": details,
        }
    except Exception as exc:
        return {"passed": False, "status": "ERROR", "details": f"quality_baseline error: {exc}"}


def _load_probe_module(root: Path, mod_name: str) -> Any:
    """Carica un modulo sonda privilegiando .staging/ rispetto alla produzione."""
    cand_dirs = [root / ".staging" / "scripts", root / "scripts", _scripts_dir, _workspace_root / ".staging" / "scripts", _workspace_root / "scripts"]
    for d in cand_dirs:
        fpath = d / f"{mod_name}.py"
        if not fpath.is_file():
            continue
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
        existing = sys.modules.get(mod_name)
        if existing is not None and getattr(existing, "__file__", None):
            try:
                if Path(str(existing.__file__)).resolve() == fpath.resolve():
                    return existing
            except OSError:
                pass
        spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            return mod
    return importlib.import_module(mod_name)


def _collect_bundle_verify_kwargs(
    root: Path, strict_verify: bool, dast_test_report: Optional[Dict[str, Any]],
    dast_report: Optional[Union[str, Path]], mutation_report: Optional[Any],
    allowed_files: Optional[Union[str, Sequence[str]]], scan_prod_frontend: bool,
    diff_aware: bool, profile: Optional[str], lane_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    v_kwargs: Dict[str, Any] = {
        "root_dir": root, "run_pytest": bool(strict_verify and dast_test_report is None),
        "strict_verify": bool(strict_verify), "test_report": dast_test_report,
    }
    opt_items = (
        ("dast_report", dast_report), ("mutation_report", mutation_report),
        ("allowed_files", allowed_files), ("scan_prod_frontend", True if scan_prod_frontend else None),
        ("diff_aware", True if diff_aware else None), ("profile", profile), ("lane_id", lane_id),
    )
    for opt_k, opt_v in opt_items:
        if opt_v is not None:
            v_kwargs[opt_k] = opt_v
    has_ext = any(k in v_kwargs for k in ("allowed_files", "scan_prod_frontend", "diff_aware", "profile", "lane_id"))
    return v_kwargs, has_ext


def _invoke_rsi_verify_for_bundle(
    engine: Any, root: Path, strict_verify: bool, dast_test_report: Optional[Dict[str, Any]],
    dast_report: Optional[Union[str, Path]], mutation_report: Optional[Any],
    allowed_files: Optional[Union[str, Sequence[str]]], scan_prod_frontend: bool,
    diff_aware: bool = False, profile: Optional[str] = None, lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoca engine.verify_ecosystem o verify_ecosystem_impl propagando i report e flag opzionali."""
    v_kwargs, has_ext = _collect_bundle_verify_kwargs(
        root, strict_verify, dast_test_report, dast_report, mutation_report,
        allowed_files, scan_prod_frontend, diff_aware, profile, lane_id=lane_id,
    )
    if not has_ext:
        return engine.verify_ecosystem(**v_kwargs)
    try:
        v_params = inspect.signature(engine.verify_ecosystem).parameters
    except (TypeError, ValueError):
        v_params = {}
    has_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in v_params.values())
    if has_kw or all(k in v_params for k in ("allowed_files", "scan_prod_frontend", "diff_aware", "profile", "lane_id") if k in v_kwargs):
        return engine.verify_ecosystem(**v_kwargs)
    return verify_ecosystem_impl(engine, **v_kwargs)


def _format_qbm_as_test_report(live: Dict[str, Any]) -> Dict[str, Any]:
    """Converte l'output Schema v2 di measure_live_pytest_metrics in test_report RSI."""
    t_pass, t_fail = int(live.get("unit_tests_passed", 0)), int(live.get("failed_tests", 0))
    t_skip, t_tot = int(live.get("tests_skipped", 0)), int(live.get("unit_tests_total", 0))
    t_xfail = int(live.get("xfailed_count", live.get("xfailed", 0)))
    t_desel = int(live.get("deselected_count", live.get("deselected", 0)))
    all_ok = t_fail == 0 and t_skip == 0 and t_xfail == 0 and t_desel == 0 and t_pass == t_tot
    rep: Dict[str, Any] = {
        "status": "PASS" if all_ok else "FAIL",
        "tests_passed": t_pass, "tests_failed": t_fail, "tests_skipped": t_skip,
        "xfailed_count": t_xfail, "deselected_count": t_desel, "tests_total": t_tot,
    }
    if live.get("pytest_duration_s") is not None:
        rep["duration_s"] = live["pytest_duration_s"]
    for cov_k in ("statement_coverage_pct", "true_branch_coverage_pct", "combined_coverage_pct"):
        if live.get(cov_k) is not None:
            rep[cov_k] = live[cov_k]
    return rep


def _has_cov_metrics(report: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(report, dict):
        return False
    has_br = report.get("true_branch_coverage_pct") is not None or report.get("branch_coverage_pct") is not None
    has_st = report.get("statement_coverage_pct") is not None or report.get("combined_coverage_pct") is not None
    return has_br and has_st


def _needs_live_cov_measure(strict_verify: bool, dast_test_report: Optional[Dict[str, Any]]) -> bool:
    has_cov = _has_cov_metrics(dast_test_report)
    if strict_verify and (dast_test_report is None or not has_cov):
        return True
    return dast_test_report is not None and not has_cov


def _invoke_qbm_live_measure(
    root: Path, load_probe_fn: Callable[[Path, str], Any], lane_id: Optional[str]
) -> Any:
    """Carica quality_baseline_manager ed esegue measure_live_pytest_metrics fail-safe."""
    try:
        qbm_mod = load_probe_fn(root, "quality_baseline_manager")
        measure_fn = getattr(qbm_mod, "measure_live_pytest_metrics", None)
        if not callable(measure_fn):
            return None
        m_kw: Dict[str, Any] = {"workspace_root": root, "with_coverage": True}
        if lane_id is not None and "lane_id" in inspect.signature(measure_fn).parameters:
            m_kw["lane_id"] = lane_id
        return measure_fn(**m_kw)
    except Exception:
        return None


def _measure_strict_bundle_test_report(
    root: Path, strict_verify: bool, dast_test_report: Optional[Dict[str, Any]],
    load_probe_fn: Callable[[Path, str], Any], lane_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Misura pytest NVMe sharded + branch coverage una sola volta su workspace reale."""
    if is_temp_workspace(root) or not _needs_live_cov_measure(strict_verify, dast_test_report):
        return dast_test_report
    live = _invoke_qbm_live_measure(root, load_probe_fn, lane_id)
    if not isinstance(live, dict) or int(live.get("unit_tests_total", 0)) <= 0:
        return dast_test_report
    return _format_qbm_as_test_report(live)


def _pick_effective_dast_report(
    with_dast: bool, dast_res: Any, dast_report: Optional[Union[str, Path]]
) -> Optional[Any]:
    if dast_report is not None:
        return dast_report
    if with_dast and isinstance(dast_res, dict) and (not dast_res.get("skipped") or not dast_res.get("passed", True)):
        return dast_res
    return None


def emit_gt14_bundle_impl(
    engine: Any, workspace_root: Optional[Union[str, Path]] = None, with_dast: bool = False,
    strict_verify: bool = False, output_path: Optional[Union[str, Path]] = None, mutation_report: Optional[Any] = None,
    dast_report: Optional[Union[str, Path]] = None, allowed_files: Optional[Union[str, Sequence[str]]] = None, scan_prod_frontend: bool = False,
    diff_aware: bool = False, profile: Optional[str] = None, lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Esegue in-process le sonde GT-14 (6 -> 1) e salva atomicamente il bundle JSON."""
    t0 = time.perf_counter()
    root = Path(workspace_root).resolve() if workspace_root else engine.workspace_root
    stg_dir, _ = resolve_staging_dir(root, lane_id=lane_id)
    probes: Dict[str, Any] = {}
    try:
        probes["registry_verify"] = _load_probe_module(root, "nk_registry_indexer").NKRegistryIndexer(workspace_root=root).verify()
    except Exception as exc:
        probes["registry_verify"] = {"passed": False, "status": "ERROR", "issues": [f"registry_verify error: {exc}"]}
    try:
        pf_res = _load_probe_module(root, "preflight_health_check").PreflightHealthChecker(workspace_root=root).run_full_check(auto_fix=False)
        pf_out = dict(pf_res)
        pf_out["passed"] = bool(pf_res.get("status") not in ("CRITICAL_FAIL", "FAIL") and not pf_res.get("issues_detected"))
        probes["preflight_check"] = pf_out
    except Exception as exc:
        probes["preflight_check"] = {"passed": False, "status": "ERROR", "issues_detected": [f"preflight_check error: {exc}"]}
    probes["ast_guard"] = _run_ast_guard_probe(root, stg_dir, _load_probe_module)
    dast_res, dast_test_report = _run_dast_probe(root, stg_dir, bool(with_dast), _load_probe_module, dast_report=dast_report, lane_id=lane_id)
    probes["dast_overlay"] = dast_res
    dast_test_report = _measure_strict_bundle_test_report(root, bool(strict_verify), dast_test_report, _load_probe_module, lane_id=lane_id)
    eff_dast_report = _pick_effective_dast_report(bool(with_dast), dast_res, dast_report)
    try:
        probes["rsi_verify"] = _invoke_rsi_verify_for_bundle(
            engine, root, bool(strict_verify), dast_test_report, eff_dast_report,
            mutation_report, allowed_files, scan_prod_frontend, diff_aware=bool(diff_aware), profile=profile, lane_id=lane_id,
        )
    except Exception as exc:
        probes["rsi_verify"] = {"passed": False, "status": "ERROR", "violations": [f"rsi_verify error: {exc}"]}
    probes["quality_baseline"] = _run_quality_baseline_probe(root, stg_dir, probes, dast_test_report, _load_probe_module, strict_verify=bool(strict_verify))
    target_out = Path(output_path).resolve() if output_path is not None else (Path(tempfile.gettempdir()) / "nk_diagnostics" / "gt14_audit_bundle.json")
    all_passed = all(bool(probes[k].get("passed", False)) for k in ("registry_verify", "preflight_check", "ast_guard", "rsi_verify", "quality_baseline", "dast_overlay"))
    raw_bundle: Dict[str, Any] = {
        "passed": all_passed, "status": "PASS" if all_passed else "FAIL", "workspace_root": str(root),
        "with_dast": bool(with_dast), "strict_verify": bool(strict_verify),
        "probes_executed": 5 if dast_res.get("skipped") else 6, "bundle_path": str(target_out),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2), "probes": probes,
    }
    bundle_payload = strip_l3_persuasive_narrative(raw_bundle)
    ok_w, err_w = atomic_write_text(target_out, json.dumps(bundle_payload, indent=2, ensure_ascii=False))
    if not ok_w:
        raise OSError(f"Impossibile scrivere il bundle GT-14 {target_out}: {err_w}")
    return bundle_payload


run_gt14_verification_bundle = emit_gt14_bundle_impl

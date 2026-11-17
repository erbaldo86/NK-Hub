"""Sonde individuali GT-14 (AST, DAST, Quality Baseline) per gt14_bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


def _collect_ast_guard_targets(root: Path, stg_dir: Path) -> Tuple[List[Path], str]:
    """Raccoglie i file .py target da .staging/ o da produzione scripts/ e tests/."""
    staged_py = (
        sorted(
            p
            for p in stg_dir.rglob("*.py")
            if p.is_file() and "__pycache__" not in p.parts
        )
        if stg_dir.is_dir()
        else []
    )
    if staged_py:
        return staged_py, "staging"
    prod_py: List[Path] = []
    for sub in ("scripts", "tests"):
        sub_dir = root / sub
        if sub_dir.is_dir():
            prod_py.extend(
                sorted(
                    p
                    for p in sub_dir.rglob("*.py")
                    if p.is_file() and "__pycache__" not in p.parts
                )
            )
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


def _run_ast_guard_probe(
    root: Path, stg_dir: Path, load_probe_fn: Callable[[Path, str], Any]
) -> Dict[str, Any]:
    """Esegue la sonda AST Guard sui file staged o di produzione."""
    py_targets, ast_scope = _collect_ast_guard_targets(root, stg_dir)
    if not py_targets:
        return {
            "passed": True,
            "skipped": True,
            "files_scanned": 0,
            "scope": "empty",
            "reason": "no_python_files_found",
        }
    try:
        agv_mod = load_probe_fn(root, "ast_guard_validator")
        validator_cls = agv_mod.ASTGuardValidator
        total_v = 0
        total_sast = 0
        ag_issues: List[str] = []
        for py_file in py_targets:
            post_code = py_file.read_text(encoding="utf-8")
            prod_counter = agv_mod._resolve_production_counterpart(py_file, root)
            pre_code = (
                prod_counter.read_text(encoding="utf-8")
                if prod_counter is not None
                else post_code
            )
            rep = validator_cls.validate_code_edit(
                pre_code,
                post_code,
                target_file=py_file.as_posix(),
            )
            total_sast += int(rep.metrics.get("sast_violations_count", 0))
            if not rep.is_valid:
                total_v += len(rep.violations)
                for v in rep.violations[:5]:
                    ag_issues.append(f"{py_file.name}: {v.message}")
        return {
            "passed": total_v == 0,
            "skipped": False,
            "scope": ast_scope,
            "files_scanned": len(py_targets),
            "total_violations": total_v,
            "sast_critical": total_sast,
            "issues": ag_issues,
        }
    except Exception as exc:
        return {
            "passed": False,
            "skipped": False,
            "scope": ast_scope,
            "files_scanned": len(py_targets),
            "error": f"ast_guard error: {exc}",
        }


def _run_dast_probe(
    root: Path,
    stg_dir: Path,
    with_dast: bool,
    load_probe_fn: Callable[[Path, str], Any],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Esegue la sonda DAST overlay in shadow sandbox quando with_dast e attivo."""
    if not with_dast:
        return {"passed": True, "skipped": True}, None
    dast_test_report: Optional[Dict[str, Any]] = None
    try:
        dast_mod = load_probe_fn(root, "dast_sandbox_runner")
        dast_res = dast_mod.run_staging_shadow_verification(
            repo_root=root,
            staging_dir=stg_dir,
            profile="evaluator",
        )
        dast_pt = dast_res.get("pytest", {}) if isinstance(dast_res, dict) else {}
        if isinstance(dast_pt, dict) and dast_pt.get("executed"):
            dast_test_report = {
                "tests_passed": int(dast_pt.get("tests_passed", 0)),
                "tests_failed": int(dast_pt.get("tests_failed", 0)),
                "tests_skipped": int(dast_pt.get("tests_skipped", 0)),
                "tests_total": int(dast_pt.get("tests_total", 0)),
            }
            for opt_k in (
                "duration_s",
                "branch_coverage_pct",
                "statement_coverage_pct",
                "true_branch_coverage_pct",
                "combined_coverage_pct",
            ):
                if opt_k in dast_pt and dast_pt.get(opt_k) is not None:
                    dast_test_report[opt_k] = dast_pt[opt_k]
        return dast_res, dast_test_report
    except Exception as exc:
        return {
            "passed": False,
            "status": "ERROR",
            "error": f"dast_overlay error: {exc}",
        }, None


def _run_quality_baseline_probe(
    root: Path,
    stg_dir: Path,
    probes: Dict[str, Any],
    dast_test_report: Optional[Dict[str, Any]],
    load_probe_fn: Callable[[Path, str], Any],
) -> Dict[str, Any]:
    """Verifica compliance e metriche live rispetto a quality_baseline.json."""
    try:
        qbm_mod = load_probe_fn(root, "quality_baseline_manager")
        stg_bl = stg_dir / "nk_tracking" / "quality_baseline.json"
        prod_bl = root / "nk_tracking" / "quality_baseline.json"
        bl_path = stg_bl if stg_bl.is_file() else prod_bl
        if not bl_path.is_file():
            return {
                "passed": False,
                "status": "MISSING",
                "baseline_path": str(bl_path),
                "details": "quality_baseline.json non trovato.",
            }
        rsi_res = probes.get("rsi_verify", {})
        bench_res = (
            rsi_res.get("checks", {}).get("benchmark_suite", {})
            if isinstance(rsi_res, dict)
            else {}
        )
        cur_metrics: Dict[str, Any] = {}
        live_tests_measured = bool(
            isinstance(bench_res, dict) and bench_res.get("executed")
        )
        pass_rate = 0.0
        if live_tests_measured:
            t_pass = int(bench_res.get("tests_passed", 0))
            t_fail = int(bench_res.get("tests_failed", 0))
            t_skip = int(bench_res.get("tests_skipped", 0))
            t_tot = int(bench_res.get("tests_total", t_pass + t_fail + t_skip))
            pass_rate = (
                round((float(t_pass) / float(t_tot)) * 100.0, 2) if t_tot > 0 else 0.0
            )
            cur_metrics.update(
                {
                    "total_golden_tests": t_tot,
                    "unit_tests_total": t_tot,
                    "unit_tests_passed": t_pass,
                    "unit_tests_pass_pct": pass_rate,
                    "pass_rate_pct": pass_rate,
                    "pass_rate_percent": pass_rate,
                    "failed_tests": t_fail + t_skip,
                }
            )
            raw_dur = bench_res.get("duration_s")
            if raw_dur is None and isinstance(dast_test_report, dict):
                raw_dur = dast_test_report.get("duration_s")
            if isinstance(raw_dur, (int, float)) and not isinstance(raw_dur, bool):
                cur_metrics["pytest_duration_s"] = float(raw_dur)
            for cov_k in (
                "branch_coverage_pct",
                "statement_coverage_pct",
                "true_branch_coverage_pct",
                "combined_coverage_pct",
            ):
                raw_cov = bench_res.get(cov_k)
                if raw_cov is None and isinstance(dast_test_report, dict):
                    raw_cov = dast_test_report.get(cov_k)
                if isinstance(raw_cov, (int, float)) and not isinstance(raw_cov, bool):
                    cur_metrics[cov_k] = float(raw_cov)
        skills_count = _count_live_overlay_skills(root, stg_dir)
        if skills_count > 0:
            cur_metrics["skills_audited"] = skills_count
        if not probes.get("ast_guard", {}).get("skipped", True):
            cur_metrics["sast_critical_violations"] = int(
                probes["ast_guard"].get("sast_critical", 0)
            )
        if isinstance(rsi_res, dict) and "delta_k" in rsi_res:
            cur_metrics["rsi_residual_delta"] = int(rsi_res.get("delta_k", 0))
            cur_metrics["rsi_convergence_score"] = float(rsi_res.get("fitness_q", 0.0))
        comp_res = qbm_mod.check_baseline_compliance(
            str(bl_path), cur_metrics, allow_ratchet_down=False
        )
        qb_passed = bool(
            live_tests_measured
            and pass_rate >= 100.0
            and comp_res.get("verdict") == "PASS"
        )
        details = comp_res.get("details", "")
        if not live_tests_measured and comp_res.get("verdict") == "PASS":
            details = (
                "Suite test non misurata dal vivo: esegui con --strict-verify o --with-dast."
            )
        return {
            "passed": qb_passed,
            "status": comp_res.get("status", "SUCCESS")
            if live_tests_measured
            else "UNMEASURED",
            "verdict": comp_res.get("verdict", "FAIL")
            if live_tests_measured
            else "UNMEASURED",
            "baseline_path": str(bl_path),
            "pass_rate_pct": pass_rate,
            "live_tests_measured": live_tests_measured,
            "schema_valid": bool(cur_metrics),
            "metrics_checked": comp_res.get("metrics_checked", 0),
            "regressions": comp_res.get("regressions", []),
            "details": details,
        }
    except Exception as exc:
        return {
            "passed": False,
            "status": "ERROR",
            "details": f"quality_baseline error: {exc}",
        }

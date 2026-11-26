# -*- coding: utf-8 -*-
"""Delta Re-Gate pre-commit fuori da L1 su mirror NVMe Seqlock-coerente a T1."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from _internal.nk_common.commit_train_store import read_commit_train_head
from _internal.nk_common.isolated_test_runner import mirror_workspace_to_nvme, run_detached_pytest, safe_rmtree

from .constants import TwoPhaseCommitError


def build_seqlock_consistent_mirror(
    root: Path,
    staging_dir: Path,
    *,
    lane_id: Optional[str] = None,
    max_seqlock_retries: int = 3,
    key_path: Optional[Union[str, Path]] = None,
) -> Tuple[Path, int, int]:
    """Costruisce un mirror NVMe overlay garantendo seq_pre == seq_post via Seqlock."""
    res_root = Path(root).resolve()
    attempts = max(1, int(max_seqlock_retries))
    for retry in range(attempts):
        seq_pre = int(read_commit_train_head(res_root, key_path=key_path).get("seq", 0))
        mirror_dir = mirror_workspace_to_nvme(
            res_root,
            staging_dir=staging_dir,
            prefix="nk_regate_",
            apply_overlay=True,
            mirror_siblings=False,
            lane_id=lane_id,
        )
        seq_post = int(read_commit_train_head(res_root, key_path=key_path).get("seq", 0))
        if seq_pre == seq_post:
            return mirror_dir, seq_post, retry
        safe_rmtree(mirror_dir.parent)
    raise TwoPhaseCommitError("SEQLOCK_RETRIES_EXHAUSTED: head.json avanzato durante il mirroring NVMe.")


def _audit_scripts_tree(mirror_dir: Path) -> Dict[str, Any]:
    """Valida SAST/scope sui .py in mirror_dir/scripts tramite ASTGuardValidator."""
    scripts_dir = mirror_dir / "scripts"
    if not scripts_dir.is_dir():
        return {"passed": True, "violations": [], "sast_critical": 0}
    from ast_guard_validator import ASTGuardValidator

    violations: List[str] = []
    sast_crit = 0
    for py_f in sorted(scripts_dir.rglob("*.py")):
        if "__pycache__" in py_f.parts:
            continue
        code = py_f.read_text(encoding="utf-8-sig", errors="replace")
        rep = ASTGuardValidator.validate_code_edit(code, code, target_file=py_f.as_posix())
        m_rep = getattr(rep, "metrics", None)
        if isinstance(m_rep, dict):
            sast_crit += int(m_rep.get("sast_violations_count", 0) or 0)
        if not rep.is_valid:
            violations.extend(f"{py_f.name}: {v.message}" for v in rep.violations[:3])
            if len(violations) >= 5:
                break
    return {"passed": not violations, "violations": violations[:5], "sast_critical": sast_crit}


_COV_KEYS: Tuple[str, str, str] = ("statement_coverage_pct", "true_branch_coverage_pct", "combined_coverage_pct")


def _extract_pytest_metrics(py_res: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae i contatori reali top-level (con fallback metrics) da run_detached_pytest."""
    src = py_res.get("metrics") if isinstance(py_res.get("metrics"), dict) else py_res
    passed = int(src.get("passed", 0) or 0)
    failed = int(src.get("failed", 0) or 0) + int(src.get("errors", 0) or 0)
    skipped = int(src.get("skipped", 0) or 0)
    duration_s = float(src.get("duration_s", py_res.get("duration_s", 0.0)) or 0.0)
    cov = py_res.get("coverage") if isinstance(py_res.get("coverage"), dict) else src.get("coverage")
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": passed + failed + skipped,
        "duration_s": duration_s,
        "coverage": cov if isinstance(cov, dict) else None,
    }


def _build_regate_metrics_dict(pm: Dict[str, Any], pytest_ok: bool, sast_crit: int) -> Dict[str, Any]:
    tot = int(pm["total"])
    pass_pct = (100.0 * int(pm["passed"]) / tot) if (tot > 0 and pytest_ok) else (0.0 if not pytest_ok else 100.0)
    return {
        "total_golden_tests": tot,
        "unit_tests_total": tot,
        "unit_tests_passed": int(pm["passed"]),
        "unit_tests_pass_pct": pass_pct,
        "pass_rate_pct": pass_pct,
        "failed_tests": int(pm["failed"]),
        "tests_skipped": int(pm["skipped"]),
        "pytest_duration_s": float(pm["duration_s"]),
        "sast_critical_violations": int(sast_crit),
    }


def _has_complete_coverage(cov: Any) -> bool:
    return isinstance(cov, dict) and all(
        isinstance(cov.get(k), (int, float)) and not isinstance(cov.get(k), bool) for k in _COV_KEYS
    )


def _run_bl_compliance(check_fn: Any, bl_path: Path, metrics: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    bl_res = check_fn(str(bl_path), metrics)
    if bl_res.get("verdict") == "PASS":
        return True, None
    return False, f"Baseline compliance Re-Gate fallita: {bl_res.get('details', '')}"


def _eval_fast_mode_invariants(pm: Dict[str, Any], pytest_ok: bool, ast_ok: bool, sast_crit: int) -> Tuple[bool, Optional[str]]:
    ok_fast = (
        pytest_ok
        and ast_ok
        and int(pm["passed"]) > 0
        and int(pm["failed"]) == 0
        and int(pm["skipped"]) == 0
        and int(sast_crit) == 0
    )
    return (True, None) if ok_fast else (False, "Baseline fast Re-Gate fallita: test/SAST invariant non rispettato")


def _eval_regate_baseline(
    bl_path: Path, pm: Dict[str, Any], pytest_ok: bool, ast_ok: bool, sast_crit: int,
) -> Tuple[bool, Optional[str]]:
    """Valida il ratchet baseline: full 12-key se coverage presente, invarianti fail-closed se fast."""
    if not bl_path.is_file():
        return True, None
    from quality_baseline_manager import check_baseline_compliance, load_baseline

    metrics = _build_regate_metrics_dict(pm, pytest_ok, sast_crit)
    cov = pm.get("coverage")
    if _has_complete_coverage(cov) and isinstance(cov, dict):
        metrics.update({k: float(cov[k]) for k in _COV_KEYS})
        return _run_bl_compliance(check_baseline_compliance, bl_path, metrics)

    try:
        bl_data = load_baseline(str(bl_path)) or {}
    except Exception as exc:
        return False, f"Baseline illeggibile in Re-Gate: {exc}"
    bl_metrics = bl_data.get("metrics", {}) if isinstance(bl_data, dict) else {}
    if any(k in bl_metrics for k in _COV_KEYS):
        return _eval_fast_mode_invariants(pm, pytest_ok, ast_ok, sast_crit)
    return _run_bl_compliance(check_baseline_compliance, bl_path, metrics)


def _default_regate_checks(
    mirror_dir: Path,
    root: Path,
    staging_dir: Path,
    lane_id: Optional[str],
    validated_seq: int,
) -> Dict[str, Any]:
    """Esegue AST/SAST, pytest isolato NVMe, verify_ecosystem e ratchet compliance live."""
    from rsi_convergence_engine import RSIConvergenceEngine

    _ = staging_dir
    violations: List[str] = []
    ast_rep = _audit_scripts_tree(mirror_dir)
    ast_ok = bool(ast_rep.get("passed", True))
    sast_crit = int(ast_rep.get("sast_critical", 0))
    if not ast_ok:
        violations.extend(str(v) for v in ast_rep.get("violations", [])[:5])

    py_res = run_detached_pytest(mirror_dir, extra_args=["-m", "fast", "-q"], apply_overlay=False, timeout_sec=60.0)
    pytest_ok = int(py_res.get("exit_code", 1)) == 0
    if not pytest_ok:
        violations.append(f"Pytest fast Re-Gate fallito (rc={py_res.get('exit_code')})")

    pm = _extract_pytest_metrics(py_res)
    test_rep: Dict[str, Any] = {
        "status": "PASS" if pytest_ok else "FAIL",
        "passed": pytest_ok,
        "tests_passed": pm["passed"],
        "tests_failed": pm["failed"],
        "tests_skipped": pm["skipped"],
        "xfailed_count": 0,
        "deselected_count": 0,
        "tests_total": pm["total"],
        "exit_code": int(py_res.get("exit_code", 1)),
        "duration_s": pm["duration_s"],
    }
    if _has_complete_coverage(pm.get("coverage")):
        test_rep.update({k: float(pm["coverage"][k]) for k in _COV_KEYS})
    engine = RSIConvergenceEngine(workspace_root=mirror_dir)
    eco = engine.verify_ecosystem(
        root_dir=mirror_dir, run_pytest=False, strict_verify=False, diff_aware=True, lane_id=lane_id, test_report=test_rep,
    )
    eco_ok = bool(eco.get("passed", False))
    if not eco_ok:
        violations.extend(str(v) for v in eco.get("violations", [])[:5])

    baseline_ok, bl_err = _eval_regate_baseline(root / "nk_tracking" / "quality_baseline.json", pm, pytest_ok, ast_ok, sast_crit)
    if not baseline_ok and bl_err:
        violations.append(bl_err)

    passed = ast_ok and pytest_ok and eco_ok and baseline_ok
    return {
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "validated_seq": validated_seq,
        "ast_passed": ast_ok,
        "pytest_passed": pytest_ok,
        "ecosystem_passed": eco_ok,
        "baseline_passed": baseline_ok,
        "violations": violations,
    }


def run_delta_regate(
    root: Path,
    staging_dir: Path,
    *,
    lane_id: Optional[str] = None,
    max_seqlock_retries: int = 3,
    run_gates_fn: Optional[Callable[[Path, int], Dict[str, Any]]] = None,
    key_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Esegue Delta Re-Gate completo su mirror NVMe coerente pulendo TEMP in finally."""
    mirror_dir, validated_seq, retries = build_seqlock_consistent_mirror(
        root, staging_dir, lane_id=lane_id, max_seqlock_retries=max_seqlock_retries, key_path=key_path,
    )
    try:
        if run_gates_fn is not None:
            raw = run_gates_fn(mirror_dir, validated_seq)
        else:
            raw = _default_regate_checks(mirror_dir, root, staging_dir, lane_id, validated_seq)
        passed = bool(raw.get("passed", False))
        return {
            "passed": passed,
            "status": str(raw.get("status") or ("PASS" if passed else "FAIL")),
            "validated_seq": int(raw.get("validated_seq", validated_seq)),
            "seqlock_retries": retries,
            "ast_passed": bool(raw.get("ast_passed", passed)),
            "pytest_passed": bool(raw.get("pytest_passed", passed)),
            "ecosystem_passed": bool(raw.get("ecosystem_passed", passed)),
            "baseline_passed": bool(raw.get("baseline_passed", passed)),
            "violations": list(raw.get("violations", [])),
        }
    finally:
        safe_rmtree(mirror_dir.parent)

# -*- coding: utf-8 -*-
"""Estensioni gate ecosistema: coverage, holdout e scan AST mock/taint in .staging/."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from _internal.nk_common.lane_lease_probe import resolve_epistemic_conflict_paths
from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir  # noqa: F401
from _internal.rsi_convergence_engine.constants import resolve_effective_staging
from _internal.rsi_convergence_engine.eco_audits import (
    audit_quality_and_frontend_impl as _audit_quality_and_frontend, audit_twin_manifest_parity_impl as _audit_twin_manifest_parity,
)
from _internal.rsi_convergence_engine.vibe_report_helpers import (
    audit_coverage_report_payload, audit_dast_report_payload, audit_mutation_report_payload,
)
_MOCK_IMPORT_MODS: Set[str] = {"unittest.mock", "mock", "pytest_mock"}
_MOCK_FROM_NAMES: Set[str] = {"MagicMock", "AsyncMock", "NonCallableMock", "Mock", "patch"}
_MOCK_ATTR_OR_NAMES: Set[str] = {"MagicMock", "AsyncMock", "NonCallableMock"}
_SKIP_SCAN_PARTS: Set[str] = {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache"}

def _build_qd_dispatch_kwargs(
    qd_params: Any, allowed_files: Optional[Union[str, Sequence[str]]], eff_prod: bool, lane_id: Optional[str], staging_dir: Optional[Path]
) -> Dict[str, Any]:
    has_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in qd_params.values())
    kw: Dict[str, Any] = {"allowed_files": allowed_files, "scan_prod_frontend": eff_prod} if (has_var or "allowed_files" in qd_params) else {}
    for k, v in (("lane_id", lane_id), ("staging_dir", staging_dir)):
        if v is not None and (has_var or k in qd_params):
            kw[k] = v
    return kw

def dispatch_quality_frontend_audit_ext(
    root: Path, allowed_files: Optional[Union[str, Sequence[str]]], scan_prod_frontend: bool, profile: str,
    lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Invoca audit_quality_and_frontend propagando allowed_files, frontend e lane/staging."""
    eff_prod = bool(scan_prod_frontend or profile == "ui_ux_rsi")
    try:
        qd_params = inspect.signature(_audit_quality_and_frontend).parameters
    except (TypeError, ValueError):
        qd_params = {}
    kw = _build_qd_dispatch_kwargs(qd_params, allowed_files, eff_prod, lane_id, staging_dir)
    return _audit_quality_and_frontend(root, **kw) if kw else _audit_quality_and_frontend(root)

def record_dast_gate_result_ext(
    dast_report: Optional[Any], measured_components: List[str], checks: Dict[str, Any], violations: List[str],
) -> int:
    """Valuta un eventuale DAST report e restituisce il conteggio high_findings."""
    if dast_report is None:
        return 0
    dast_res = audit_dast_report_payload(dast_report)
    checks["dast_report"] = dast_res
    measured_components.append("dast_report")
    violations.extend(dast_res.get("violations", []))
    return int(dast_res.get("high_findings", 0))

def record_coverage_gate_result_ext(
    coverage_report: Optional[Any], measured_components: List[str],
    unmeasured_components: List[str], checks: Dict[str, Any], violations: List[str],
) -> int:
    """Valuta un eventuale report coverage e registra high_findings fail-closed."""
    if coverage_report is None:
        return 0
    cov_res = audit_coverage_report_payload(coverage_report)
    checks["coverage_report"] = cov_res
    (measured_components if cov_res.get("passed", False) else unmeasured_components).append("coverage_report")
    violations.extend(cov_res.get("violations", []))
    return int(cov_res.get("high_findings", 0))

def _is_non_test_py(fpath: Path, rel_parts: Tuple[str, ...]) -> bool:
    if fpath.suffix != ".py" or any(part in _SKIP_SCAN_PARTS for part in rel_parts) or "tests" in rel_parts:
        return False
    return not (fpath.name.startswith("test_") or fpath.name.endswith("_test.py"))

def _is_dynamic_sql_arg(arg_node: ast.AST) -> bool:
    if isinstance(arg_node, ast.JoinedStr) or (isinstance(arg_node, ast.BinOp) and isinstance(arg_node.op, (ast.Add, ast.Mod))):
        return True
    return isinstance(arg_node, ast.Call) and isinstance(arg_node.func, ast.Attribute) and arg_node.func.attr == "format"

_SP_ALIAS_FUNCS = frozenset(("run", "Popen", "call", "check_output", "check_call"))
_BUILTIN_TAINT_FUNCS = frozenset(("eval", "exec"))

def _reg_import_alias(node: ast.Import, os_mods: set[str], sp_mods: set[str], pk_funcs: set[str]) -> None:
    for al in node.names:
        alias = al.asname or al.name.split(".", 1)[0]
        if al.name == "os":
            os_mods.add(alias)
        elif al.name == "subprocess":
            sp_mods.add(alias)
        elif al.name in ("pickle", "_pickle"):
            pk_funcs.add(f"{alias}.loads")
        elif al.name == "builtins":
            pk_funcs.update((f"{alias}.eval", f"{alias}.exec"))

def _reg_from_alias(node: ast.ImportFrom, os_funcs: set[str], sp_funcs: set[str], pk_funcs: set[str]) -> None:
    mod = node.module or ""
    for al in node.names:
        local = al.asname or al.name
        if mod == "os" and al.name in ("system", "popen"):
            os_funcs.add(local)
        elif mod == "subprocess" and al.name in _SP_ALIAS_FUNCS:
            sp_funcs.add(local)
        elif mod in ("pickle", "_pickle") and al.name == "loads":
            pk_funcs.add(local)
        elif mod == "builtins" and al.name in _BUILTIN_TAINT_FUNCS:
            pk_funcs.add(local)

def _collect_taint_aliases(tree: ast.AST) -> Tuple[set[str], set[str], set[str], set[str], set[str]]:
    os_mods, os_funcs, sp_mods, sp_funcs, pk_funcs = {"os"}, set(), {"subprocess"}, set(), {"pickle.loads", "_pickle.loads", "builtins.eval", "builtins.exec"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _reg_import_alias(node, os_mods, sp_mods, pk_funcs)
        elif isinstance(node, ast.ImportFrom):
            _reg_from_alias(node, os_funcs, sp_funcs, pk_funcs)
    return os_mods, os_funcs, sp_mods, sp_funcs, pk_funcs

def _has_true_shell_kw(node: ast.Call) -> bool:
    return any(kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in node.keywords)

def _attr_call_taint(node: ast.Call, func: ast.Attribute, os_mods: set[str], sp_mods: set[str], pk_funcs: set[str]) -> int:
    base_id = func.value.id if isinstance(func.value, ast.Name) else ""
    if func.attr in ("execute", "executemany") and node.args and _is_dynamic_sql_arg(node.args[0]):
        return 1
    if (func.attr in ("system", "popen") and base_id in os_mods) or (func.attr in ("loads", "eval", "exec") and base_id and f"{base_id}.{func.attr}" in pk_funcs):
        return 1
    return 1 if (func.attr in _SP_ALIAS_FUNCS and (not base_id or base_id in sp_mods) and _has_true_shell_kw(node)) else 0

def _count_call_taint_and_mock(
    node: ast.Call, os_mods: set[str], os_funcs: set[str], sp_mods: set[str], sp_funcs: set[str], pk_funcs: set[str],
) -> Tuple[int, int]:
    func = node.func
    if isinstance(func, ast.Attribute):
        return 0, _attr_call_taint(node, func, os_mods, sp_mods, pk_funcs)
    if isinstance(func, ast.Name):
        if func.id in _MOCK_ATTR_OR_NAMES:
            return 1, 0
        is_taint = func.id in os_funcs or func.id in pk_funcs or func.id in _BUILTIN_TAINT_FUNCS or (func.id in sp_funcs and _has_true_shell_kw(node))
        return 0, int(is_taint)
    return 0, 0

def _count_import_mocks(node: ast.AST) -> int:
    if isinstance(node, ast.Import):
        return sum(1 for al in node.names if al.name in _MOCK_IMPORT_MODS or al.name.startswith("unittest.mock."))
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if mod in _MOCK_IMPORT_MODS or mod.startswith("unittest.mock."):
            return len(node.names)
        if "mock" in mod.lower():
            return sum(1 for al in node.names if al.name in _MOCK_FROM_NAMES)
    return 0

def _scan_py_ast_for_mock_and_taint(tree: ast.AST) -> Tuple[int, int]:
    mocks, taint = 0, 0
    os_mods, os_funcs, sp_mods, sp_funcs, pk_funcs = _collect_taint_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mocks += _count_import_mocks(node)
        elif isinstance(node, ast.Call):
            cm, ct = _count_call_taint_and_mock(node, os_mods, os_funcs, sp_mods, sp_funcs, pk_funcs)
            mocks, taint = mocks + cm, taint + ct
        elif isinstance(node, ast.Attribute) and node.attr in _MOCK_ATTR_OR_NAMES:
            mocks += 1
    return mocks, taint

def _is_active_non_test_py(fpath: Path, stg_root: Path, exclude_lanes: Optional[bool] = None) -> bool:
    rel_parts = fpath.relative_to(stg_root).parts
    is_base = (stg_root.name == ".staging") if exclude_lanes is None else bool(exclude_lanes)
    return not (is_base and rel_parts and is_lane_container_entry(rel_parts)) and _is_non_test_py(fpath, rel_parts)

def _scan_staging_py_entry(fpath: Path, stg_root: Path, flagged: List[str], exclude_lanes: Optional[bool] = None) -> Tuple[int, int, int]:
    if not _is_active_non_test_py(fpath, stg_root, exclude_lanes=exclude_lanes):
        return 0, 0, 0
    rel_str = fpath.relative_to(stg_root).as_posix()
    try:
        tree = ast.parse(fpath.read_text(encoding="utf-8", errors="replace"), filename=str(fpath))
    except SyntaxError as exc:
        flagged.append(f"{rel_str}:L{exc.lineno or 0}")
        return 0, 0, 1
    m_cnt, t_cnt = _scan_py_ast_for_mock_and_taint(tree)
    if m_cnt > 0 or t_cnt > 0:
        flagged.append(rel_str)
    return m_cnt, t_cnt, 0

def _append_ast_scan_violations(
    violations: List[str], flagged: List[str], mock_total: int, taint_total: int, syntax_total: int,
) -> None:
    sample = ", ".join(flagged[:5])
    if mock_total > 0:
        violations.append(f"Mock vietati rilevati in .staging/ non-test: {mock_total} ({sample}).")
    if taint_total > 0:
        violations.append(f"Taint sink non sanitizzati rilevati in .staging/: {taint_total} ({sample}).")
    if syntax_total > 0:
        violations.append(f"SyntaxError AST rilevati in .staging/ non-test: {syntax_total} ({sample}).")

def _resolve_scan_stg_and_excl(root: Path, lane_id: Optional[str], staging_dir: Optional[Path], allow_root_stg: bool = False) -> Tuple[Path, bool]:
    use_root_stg = allow_root_stg and root.name == ".staging" and staging_dir is None and lane_id is None
    stg_root = root if use_root_stg else resolve_effective_staging(root, lane_id=lane_id, staging_dir=staging_dir)
    return stg_root, (lane_id is None and staging_dir is None and stg_root.name == ".staging")

def scan_staging_ast_mock_and_taint_ext(
    root: Path, violations: List[str], lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Scansiona i file .py non-test in .staging/ via AST puro per mock, taint sink e SyntaxError."""
    stg_root, excl_lanes = _resolve_scan_stg_and_excl(root, lane_id, staging_dir, allow_root_stg=True)
    if not stg_root.is_dir():
        return {"passed": True, "skipped": True, "mock_count": 0, "sast_taint": 0, "syntax_errors": 0, "files": []}
    mock_total, taint_total, syntax_total, flagged = 0, 0, 0, []
    for fpath in sorted(stg_root.rglob("*.py")):
        m_cnt, t_cnt, s_cnt = _scan_staging_py_entry(fpath, stg_root, flagged, exclude_lanes=excl_lanes)
        mock_total, taint_total, syntax_total = mock_total + m_cnt, taint_total + t_cnt, syntax_total + s_cnt
    _append_ast_scan_violations(violations, flagged, mock_total, taint_total, syntax_total)
    return {"passed": (mock_total + taint_total + syntax_total) == 0, "skipped": False, "mock_count": mock_total, "sast_taint": taint_total, "syntax_errors": syntax_total, "files": flagged}

def evaluate_holdout_gate_ext(
    engine: Any, root: Path, strict_verify: bool, dast_chk: Any, checks: Dict[str, Any], violations: List[str],
) -> int:
    """Calcola f_holdout da DAST report ed eventuale Canary Holdout in strict_verify."""
    f_holdout = int(dast_chk.get("f_holdout", 0)) if isinstance(dast_chk, dict) else 0
    cand_canary: Optional[Path] = None
    for rel in (".staging/nk_tracking/canary_v1.json", "nk_tracking/canary_v1.json"):
        p = root / rel
        if p.is_file():
            cand_canary = p
            break
    if not (strict_verify or cand_canary is not None):
        return f_holdout
    try:
        c_params = inspect.signature(engine.evaluate_canary_holdout).parameters
    except (TypeError, ValueError):
        c_params = {}
    if strict_verify and ("require_sha256" in c_params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in c_params.values())):
        canary_res = engine.evaluate_canary_holdout(holdout_path=cand_canary, require_sha256=True)
    else:
        canary_res = engine.evaluate_canary_holdout(holdout_path=cand_canary)
    checks["canary_holdout"] = canary_res
    if not canary_res.get("passed", False):
        tot, ok_cnt, decep = int(canary_res.get("total_tasks", 0)), int(canary_res.get("conflict_reported_count", 0)), int(canary_res.get("deception_gaming_count", 0))
        c_fail = max(1, (tot - ok_cnt) + decep)
        f_holdout += c_fail
        violations.append(f"Canary holdout fallito: {c_fail} task non risolti/deception.")
    return f_holdout

def audit_builder_ecosystem_gates_ext(
    root: Path, mutation_report: Optional[Any], measured_components: List[str], unmeasured_components: List[str],
    checks: Dict[str, Any], violations: List[str], *, allowed_files: Optional[Union[str, Sequence[str]]] = None,
    scan_prod_frontend: bool = False, dast_report: Optional[Any] = None,
    coverage_report: Optional[Any] = None, profile: str = "code_rsi",
    lane_id: Optional[str] = None, staging_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """Esegue twin parity, quality-diff AST, frontend, mutation, DAST e coverage gate."""
    twin_res = _audit_twin_manifest_parity(root)
    checks["twin_manifest_parity"] = twin_res
    if not twin_res.get("skipped"):
        measured_components.append("twin_manifest_parity")
    violations.extend(twin_res.get("violations", []))
    qd_res = dispatch_quality_frontend_audit_ext(root, allowed_files, scan_prod_frontend, profile, lane_id=lane_id, staging_dir=staging_dir)
    checks["quality_diff_and_frontend"] = qd_res
    if not qd_res.get("skipped"):
        measured_components.append("quality_diff_and_frontend")
    violations.extend(qd_res.get("violations", []))
    mut_res = audit_mutation_report_payload(mutation_report)
    if mutation_report is not None:
        checks["mutation_gate"] = mut_res
        measured_components.append("mutation_gate")
        violations.extend(mut_res.get("violations", []))
    dast_high = record_dast_gate_result_ext(dast_report, measured_components, checks, violations)
    cov_high = record_coverage_gate_result_ext(coverage_report, measured_components, unmeasured_components, checks, violations)
    checks["ast_mock_and_taint"] = scan_staging_ast_mock_and_taint_ext(root, violations, lane_id=lane_id, staging_dir=staging_dir)
    qd_scope = int(qd_res.get("semantic_drift_findings", 0))
    return {
        "semantic_drift": len(twin_res.get("mismatches", [])) + qd_scope, "scope_creep": qd_scope,
        "high": int(qd_res.get("high_findings", 0)) + int(mut_res.get("high_findings", 0)) + dast_high + cov_high,
        "medium": int(qd_res.get("medium_findings", 0)), "low": int(qd_res.get("low_findings", 0)),
    }

def _as_finite_float(val: Any) -> Optional[float]:
    from _internal.nk_common.staging_manifest import safe_finite_float
    parsed = safe_finite_float(val, default=float("nan"))
    return None if parsed != parsed else parsed

def extract_bench_signals_ext(bench_chk: Any, cov_chk: Any = None) -> Tuple[Optional[float], int, int, int]:
    """Estrae (c_branch_diff, skipped, xfailed, deselected) dai check test e coverage."""
    raw_c, tests_skipped, xfailed_cnt, deselected_cnt = None, 0, 0, 0
    if isinstance(bench_chk, dict):
        tests_skipped, xfailed_cnt, deselected_cnt = int(bench_chk.get("tests_skipped", 0)), int(bench_chk.get("xfailed_count", 0)), int(bench_chk.get("deselected_count", 0))
        cov_num = _as_finite_float(bench_chk.get("true_branch_coverage_pct", bench_chk.get("branch_coverage_pct")))
        raw_c = (cov_num / 100.0) if cov_num is not None else None
    if raw_c is None and isinstance(cov_chk, dict) and cov_chk.get("passed", False):
        cov_ext = _as_finite_float(cov_chk.get("true_branch_coverage_pct"))
        raw_c = (cov_ext / 100.0) if cov_ext is not None else None
    return raw_c, tests_skipped, xfailed_cnt, deselected_cnt

def _allowed_has_py(allowed_files: Optional[Union[str, Sequence[str]]]) -> bool:
    items = [p.strip() for p in allowed_files.split(",")] if isinstance(allowed_files, str) else [str(p).strip() for p in (allowed_files or ())]
    return any(p.lower().endswith(".py") for p in items if p)

def _is_active_staged_py_file(p: Path, stg_root: Path, is_base_stg: bool) -> bool:
    return p.suffix == ".py" and "__pycache__" not in p.parts and not (is_base_stg and is_lane_container_entry(p.relative_to(stg_root).parts))

def _has_staged_python_files(root: Path, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> bool:
    stg_root, is_base_stg = _resolve_scan_stg_and_excl(root, lane_id, staging_dir)
    return stg_root.is_dir() and any(_is_active_staged_py_file(p, stg_root, is_base_stg) for p in stg_root.rglob("*.py"))

def has_python_diff_signal_ext(root: Path, canonical_profile: str, mut_chk: Any, diff_aware: bool = False, allowed_files: Optional[Union[str, Sequence[str]]] = None, lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> bool:
    """Valuta segnali Python diff preservando il comportamento legacy con diff_aware=False."""
    stg_has_py = _has_staged_python_files(root, lane_id=lane_id, staging_dir=staging_dir)
    if diff_aware:
        return bool(stg_has_py or isinstance(mut_chk, dict) or _allowed_has_py(allowed_files))
    is_ext_app = any((root / d).is_dir() for d in ("src_app", "src", "app")) and not (root / ".agents" / "skills").is_dir()
    return bool(stg_has_py or isinstance(mut_chk, dict) or (canonical_profile not in ("ste100_rsi", "spec_rsi") and not is_ext_app and (root / "scripts").is_dir()))

def build_q_v2_kwargs_ext(root: Path, canonical_profile: str, defects: Any, checks: Dict[str, Any], unmeasured_components: List[str], ste100_warnings: List[str], strict_verify: bool, strict_unmeasured_gate: bool, diff_aware: bool, allowed_files: Optional[Union[str, Sequence[str]]], f_holdout: int, scope_creep_override: Optional[int], lane_id: Optional[str] = None, staging_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Assembla i kwargs completi per compute_fitness_v2 senza gonfiare ecosystem_verify."""
    mut_chk, dast_chk, sast_rep_chk, ast_scan = checks.get("mutation_gate"), checks.get("dast_report"), checks.get("sast_report"), checks.get("ast_mock_and_taint")
    has_python_diff = has_python_diff_signal_ext(root, canonical_profile, mut_chk, diff_aware=diff_aware, allowed_files=allowed_files, lane_id=lane_id, staging_dir=staging_dir)
    raw_k = _as_finite_float(mut_chk.get("kill_rate")) if isinstance(mut_chk, dict) else None
    raw_mut_tot = mut_chk.get("mutants_total") if isinstance(mut_chk, dict) else None
    raw_c, skipped, xfailed, deselected = extract_bench_signals_ext(checks.get("benchmark_suite"), checks.get("coverage_report"))
    ste100_score = 1.0 if not ste100_warnings else max(0.0, 1.0 - 0.1 * len(ste100_warnings))
    s_taint = (int(sast_rep_chk.get("sast_taint", 0)) if isinstance(sast_rep_chk, dict) else 0) + (int(ast_scan.get("sast_taint", 0)) if isinstance(ast_scan, dict) else 0)
    mock_cnt = int(ast_scan.get("mock_count", 0)) if isinstance(ast_scan, dict) else 0
    dast_ok = (1 if bool(dast_chk.get("passed", False)) else 0) if isinstance(dast_chk, dict) else (0 if strict_verify and has_python_diff else 1)
    return {
        "has_python_diff": has_python_diff, "k_mut_diff": raw_k, "c_branch_diff": raw_c,
        "mutants_total": int(raw_mut_tot) if isinstance(raw_mut_tot, int) else None, "tests_skipped": skipped, "s_taint": s_taint, "dast_passed": dast_ok,
        "mock_count": mock_cnt, "f_holdout": f_holdout, "scope_creep": int(defects.semantic_drift_findings) if scope_creep_override is None else int(scope_creep_override),
        "dry_run": 1 if "UNMEASURED_DRY_RUN" in unmeasured_components else 0, "ste100_score": ste100_score,
        "report_status": "UNMEASURED" if unmeasured_components else "PASS", "strict_unmeasured_gate": strict_unmeasured_gate, "xfailed_tests": xfailed, "deselected_tests": deselected,
    }

def _has_active_epistemic_conflict(root: Path, q_v2_res: Dict[str, Any], lane_id: Optional[str] = None) -> bool:
    if bool(q_v2_res.get("epistemic_conflict", False)):
        return True
    for rep in resolve_epistemic_conflict_paths(root, lane_id=lane_id):
        if not rep.is_file():
            continue
        try:
            import json as _json
            data = _json.loads(rep.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, ValueError):
            return True
        if isinstance(data, dict) and str(data.get("status", "")).strip().upper() == "HALT_EPISTEMIC_CONFLICT":
            return True
    return False

def _build_verify_governance_fields(
    root: Path, defects: Any, q_v2_res: Dict[str, Any], checks: Dict[str, Any], *, lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    suite_chk, dast_chk = checks.get("benchmark_suite"), checks.get("dast_report")
    twin_chk, gt14_chk = checks.get("twin_manifest_parity"), checks.get("gt14_crit01_governance")
    mismatches = twin_chk.get("mismatches", []) if isinstance(twin_chk, dict) else []
    out: Dict[str, Any] = {
        "failed_hard_gates": list(q_v2_res.get("failed_hard_gates", [])), "unmeasured_reasons": list(q_v2_res.get("unmeasured_reasons", [])),
        "epistemic_conflict": _has_active_epistemic_conflict(root, q_v2_res, lane_id=lane_id),
        "dast_high_findings": int(dast_chk.get("high_findings", 0)) if isinstance(dast_chk, dict) else 0,
        "twin_mismatches_count": len(mismatches) if isinstance(mismatches, list) else 0, "contract_violations_count": int(defects.contract_violations),
        "gt14_governance_ok": 1 if (not isinstance(gt14_chk, dict) or bool(gt14_chk.get("passed", True))) else 0,
        "twin_parity_ok": 1 if (not isinstance(twin_chk, dict) or bool(twin_chk.get("passed", True))) else 0,
    }
    if isinstance(suite_chk, dict) and suite_chk.get("duration_s") is not None:
        out["duration_s"] = suite_chk["duration_s"]
    return out

def finalize_ecosystem_verify_ext(
    engine: Any, root: Path, canonical_profile: str, defects: Any, delta_k: int, fitness_q: float,
    real_state_hash: str, q_v2_res: Dict[str, Any], status_str: str, passed: bool, persist_telemetry: bool,
    measured_components: List[str], unmeasured_components: List[str], checks: Dict[str, Any],
    violations: List[str], ste100_warnings: List[str], record_cls: Any, ts_now: int, *, lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persiste la telemetria opzionale e costruisce il payload finale verify_ecosystem."""
    if persist_telemetry:
        engine.append_telemetry_record(record_cls(
            session_id=f"VERIFY-{ts_now}", iteration=0, mode="mode_a", defects=defects, delta_k=delta_k,
            fitness_q=fitness_q, state_hash=real_state_hash, verdict=status_str, rolled_back=False,
            q_v2=q_v2_res["q_v2"], g_hard=q_v2_res["g_hard"], delta_hard=q_v2_res["delta_hard"], certification_tier=q_v2_res["certification_tier"],
        ))
    out_payload: Dict[str, Any] = {
        "status": status_str, "passed": passed, "scope": str(root), "profile": canonical_profile, "delta_k": delta_k, "fitness_q": fitness_q,
        "q_v2": q_v2_res["q_v2"], "g_hard": q_v2_res["g_hard"], "delta_hard": q_v2_res["delta_hard"],
        "gaming_penalty": q_v2_res["gaming_penalty"], "certification_tier": q_v2_res["certification_tier"], "sort_key": q_v2_res["sort_key"],
        "state_hash": real_state_hash, "grounding_shield_active": True, "measured_components": measured_components,
        "unmeasured_components": unmeasured_components, "checks": checks, "violations": violations, "ste100_warnings": ste100_warnings,
    }
    out_payload.update(_build_verify_governance_fields(root, defects, q_v2_res, checks, lane_id=lane_id))
    return out_payload

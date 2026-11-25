# -*- coding: utf-8 -*-
"""Verifica ecosistema Guardia G6 con Overlay Union, Q_v2(S_k) e gate SAST/DAST/Mutation."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from _internal.rsi_convergence_engine.constants import RSIDefectVector, RSIIterationRecord
from _internal.rsi_convergence_engine.eco_audits import (
    audit_gt14_governance_impl as _audit_gt14_governance,
    audit_markdown_docs_impl as _audit_markdown_docs,
    audit_quality_and_frontend_impl as _audit_quality_and_frontend,
    audit_twin_manifest_parity_impl as _audit_twin_manifest_parity,
    report_is_dry_run_impl as _report_is_dry_run,
)
from _internal.rsi_convergence_engine.ecosystem_gates_ext import (
    audit_builder_ecosystem_gates_ext as _audit_builder_ecosystem_gates,
    build_q_v2_kwargs_ext,
    evaluate_holdout_gate_ext,
    extract_bench_signals_ext,  # noqa: F401
    finalize_ecosystem_verify_ext,
    has_python_diff_signal_ext,
)
from _internal.rsi_convergence_engine.profiles import RSIProfileRegistry, compute_fitness_v2, verify_ste100_compliance
from _internal.rsi_convergence_engine.sast_scanner import audit_tas_reports_impl
from _internal.rsi_convergence_engine.vibe_report_helpers import (
    audit_dast_report_payload,  # noqa: F401
    audit_mutation_report_payload,  # noqa: F401
    audit_sast_report_payload,
    evaluate_benchmark_suite_gate,
)


def _audit_agents_md_budget(
    engine: Any, root: Path, verified_files: List[Path],
    measured_components: List[str], checks: Dict[str, Any], violations: List[str],
) -> None:
    """Verifica il budget byte e conformita STE100 di .agents/AGENTS.md."""
    agents_md = engine._resolve_candidate(root, ".agents/AGENTS.md")
    anti_crash_md = engine._resolve_candidate(root, ".agents/rules/anti_crash_rules.md")
    if not agents_md.exists():
        return
    verified_files.append(agents_md)
    if anti_crash_md.exists():
        verified_files.append(anti_crash_md)
    measured_components.insert(0, "agents_md")
    agents_bytes = agents_md.stat().st_size
    crash_bytes = anti_crash_md.stat().st_size if anti_crash_md.exists() else 0
    combined_bytes = agents_bytes + crash_bytes
    budget_ok = agents_bytes < 24000 and combined_bytes < 26000
    if not budget_ok:
        violations.append(f"AGENTS.md supera il limite di 24000 byte ({agents_bytes} B, combinato {combined_bytes} B).")
    agents_text = agents_md.read_text(encoding="utf-8", errors="replace")
    ste_res = verify_ste100_compliance(agents_text)
    agents_ste_warnings = list(ste_res["violations"][:5]) if "[RULE-STE100]" in agents_text and not ste_res["passed"] else []
    checks["agents_md"] = {
        "passed": budget_ok, "agents_bytes": agents_bytes, "combined_bytes": combined_bytes,
        "ste100_passed": ste_res["passed"], "ste100_warnings": agents_ste_warnings,
    }


def _scan_dirty_orphans(root: Path) -> List[str]:
    """Scansiona file temporanei o backup orfani (*.tmp, *.bak) nel workspace."""
    dirty_orphans: List[str] = []
    for scan_d in (root, root / "nk_genome", root / "scripts", root / ".agents"):
        if not scan_d.is_dir():
            continue
        for pat in ("*.tmp", "*.bak"):
            for fpath in sorted(scan_d.glob(pat)):
                rel_orph = str(fpath.relative_to(root)).replace("\\", "/")
                if rel_orph not in dirty_orphans:
                    dirty_orphans.append(rel_orph)
    return dirty_orphans


def _apply_external_sast_report(
    sast_report: Optional[Path | str], checks: Dict[str, Any], unmeasured_components: List[str],
    violations: List[str], sast_mojibake: Dict[str, Any],
) -> None:
    if sast_report is None:
        return
    sast_rep_chk = audit_sast_report_payload(sast_report)
    checks["sast_report"] = sast_rep_chk
    if sast_rep_chk.get("passed", False):
        return
    unmeasured_components.append("sast_report")
    sast_mojibake["sast_critical"] = max(int(sast_mojibake["sast_critical"]), int(sast_rep_chk.get("sast_critical", 1)))
    for sv in sast_rep_chk.get("violations", []):
        if sv not in violations:
            violations.append(sv)


def _audit_sast_and_telemetry(
    engine: Any, root: Path, sast_report: Optional[Path | str], dast_report: Optional[Path | str],
    test_report: Optional[Dict[str, Any]], verified_files: List[Path], unmeasured_components: List[str],
    checks: Dict[str, Any], violations: List[str],
) -> Tuple[bool, Dict[str, Any]]:
    """Audita catena telemetrica, SAST/mojibake/JSON e report dry-run o malformati."""
    telemetry_file = engine._resolve_candidate(root, "nk_tracking/rsi_telemetry.jsonl")
    if telemetry_file.exists():
        verified_files.append(telemetry_file)
    chain_ok, chain_count, chain_msg = engine.verify_telemetry_chain(telemetry_file)
    if not chain_ok:
        violations.append(chain_msg)
    checks["telemetry_chain"] = {"passed": chain_ok, "records_verified": chain_count, "details": chain_msg}

    sast_mojibake = engine._scan_sast_and_mojibake(root, sast_report=sast_report)
    verified_files.extend(sast_mojibake.pop("scanned_files", []))
    _apply_external_sast_report(sast_report, checks, unmeasured_components, violations, sast_mojibake)
    checks["sast_and_mojibake"] = sast_mojibake

    if _report_is_dry_run(sast_report) or _report_is_dry_run(dast_report) or _report_is_dry_run(test_report):
        unmeasured_components.append("UNMEASURED_DRY_RUN")
        violations.append("Report sandbox eseguito in modalita dry-run non certificabile.")
    for issue in sast_mojibake["sast_issues"]:
        if issue not in violations:
            violations.append(issue)
    violations.extend(f"{fname}: rilevato carattere di sostituzione U+FFFD vietato." for fname in sast_mojibake["mojibake_files"])
    violations.extend(f"JSON invalido: {jerr}" for jerr in sast_mojibake["invalid_json_files"])
    return chain_ok, sast_mojibake


def _has_python_diff_signal(
    root: Path, canonical_profile: str, mut_chk: Any,
    *, diff_aware: bool = False, allowed_files: Optional[Union[str, Sequence[str]]] = None,
) -> bool:
    """Determina se la verifica richiede segnali diff Python (legacy identico con diff_aware=False)."""
    return has_python_diff_signal_ext(root, canonical_profile, mut_chk, diff_aware=diff_aware, allowed_files=allowed_files)


def _compute_ecosystem_q_v2(
    root: Path, canonical_profile: str, defects: RSIDefectVector,
    checks: Dict[str, Any], unmeasured_components: List[str], ste100_warnings: List[str],
    *, strict_verify: bool = False, strict_unmeasured_gate: bool = False,
    diff_aware: bool = False, allowed_files: Optional[Union[str, Sequence[str]]] = None,
    f_holdout: int = 0, scope_creep_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Calcola Q_v2(S_k) lessicografico dai segnali reali di verify_ecosystem."""
    kw = build_q_v2_kwargs_ext(
        root, canonical_profile, defects, checks, unmeasured_components, ste100_warnings,
        strict_verify, strict_unmeasured_gate, diff_aware, allowed_files, f_holdout, scope_creep_override,
    )
    return compute_fitness_v2(defects, **kw)


def _resolve_ecosystem_status_and_pass(
    unmeasured_components: List[str], violations: List[str], delta_k: int,
    fitness_q: float, checks: Dict[str, Any], q_v2_res: Dict[str, Any],
) -> Tuple[str, bool]:
    """Determina status e passed vincolando CONVERGED_OPTIMAL a g_hard==1 e tier certificato."""
    if unmeasured_components:
        return "UNMEASURED", False
    legacy_ok = (not violations) and delta_k == 0 and fitness_q >= 100.0 and bool(checks["workspace_clean_hygiene"]["passed"])
    if not legacy_ok:
        return "REFINING", False
    if int(q_v2_res["g_hard"]) == 1 and q_v2_res["certification_tier"] in ("CERTIFIED_PASS", "STATIC_PASS"):
        return "CONVERGED_OPTIMAL", True
    if q_v2_res["certification_tier"] == "UNMEASURED":
        return "UNMEASURED", False
    return "REFINING", False


def _resolve_canonical_profile(profile: str, strict_profile: bool) -> str:
    return (RSIProfileRegistry.get_strict(profile) if strict_profile else RSIProfileRegistry.get(profile)).name


def verify_ecosystem_impl(
    engine: Any, root_dir: Optional[Path] = None, run_pytest: bool = False,
    profile: str = "code_rsi", benchmark_suite: Optional[str] = None,
    sast_report: Optional[Path | str] = None, strict_verify: bool = False,
    persist_telemetry: bool = False, test_report: Optional[Dict[str, Any]] = None,
    dast_report: Optional[Path | str] = None, mutation_report: Optional[Any] = None,
    allowed_files: Optional[Union[str, Sequence[str]]] = None, scan_prod_frontend: bool = False,
    coverage_report: Optional[Path | str] = None, strict_profile: bool = False,
    diff_aware: bool = False, allow_injected_test_report: bool = True,
    strict_unmeasured_gate: bool = False,
) -> Dict[str, Any]:
    """Esegue la verifica completa Guardia G6 sull'ecosistema con Overlay Union e Q_v2."""
    if isinstance(root_dir, bool):
        should_run_pytest = root_dir or bool(run_pytest)
        root = engine.workspace_root
    else:
        should_run_pytest = bool(run_pytest)
        root = Path(root_dir).resolve() if root_dir else engine.workspace_root

    canonical_profile = _resolve_canonical_profile(profile, strict_profile)
    violations: List[str] = []
    checks: Dict[str, Any] = {}
    verified_files: List[Path] = []
    measured_components: List[str] = ["skills_and_markdown", "cli_flags_cove", "telemetry_chain", "sast_and_mojibake", "workspace_clean_hygiene"]
    unmeasured_components: List[str] = []

    _audit_agents_md_budget(engine, root, verified_files, measured_components, checks, violations)
    md_chk = _audit_markdown_docs(engine, root, canonical_profile, verified_files, violations)
    checks["skills_and_markdown"] = md_chk
    broken_links = md_chk["broken_links"]
    ste100_warnings = list(checks.get("agents_md", {}).get("ste100_warnings", [])) + list(md_chk.get("ste100_warnings", []))

    cove_res = engine.verify_cli_flags_cove(root)
    checks["cli_flags_cove"] = cove_res
    violations.extend(f"Flag CLI non valido: {inv}" for inv in cove_res["invalid_flags"])

    chain_ok, sast_mojibake = _audit_sast_and_telemetry(
        engine, root, sast_report, dast_report, test_report, verified_files, unmeasured_components, checks, violations,
    )
    hallucinated_refs_count, tas_chk = audit_tas_reports_impl(engine, root, verified_files, violations)
    checks["tas_report_grounding"] = tas_chk
    gt14_issues, gt14_chk = _audit_gt14_governance(root, measured_components, violations)
    checks["gt14_crit01_governance"] = gt14_chk

    builder_defects = _audit_builder_ecosystem_gates(
        root, mutation_report, measured_components, unmeasured_components, checks, violations,
        allowed_files=allowed_files, scan_prod_frontend=scan_prod_frontend,
        dast_report=dast_report, coverage_report=coverage_report, profile=canonical_profile,
    )
    f_holdout = evaluate_holdout_gate_ext(engine, root, strict_verify, checks.get("dast_report"), checks, violations)
    dirty_orphans = _scan_dirty_orphans(root)
    checks["workspace_clean_hygiene"] = {"passed": not dirty_orphans, "dirty_files": dirty_orphans}
    if dirty_orphans:
        violations.append(f"File temporanei/orfani rilevati nel workspace: {dirty_orphans}")

    bench_failed, bench_passed, bench_total = evaluate_benchmark_suite_gate(
        engine=engine, root=root, test_report=test_report, benchmark_suite=benchmark_suite,
        should_run_pytest=should_run_pytest, strict_verify=strict_verify, measured_components=measured_components,
        unmeasured_components=unmeasured_components, checks=checks, violations=violations,
        allow_injected_in_strict=allow_injected_test_report,
    )
    ste100_drift = len(ste100_warnings) if strict_verify else 0
    if ste100_drift > 0:
        violations.extend(ste100_warnings)

    defects = RSIDefectVector(
        sast_critical=int(sast_mojibake["sast_critical"]), hallucinated_refs=hallucinated_refs_count,
        tests_failed=bench_failed, tests_passed=bench_passed, tests_total=bench_total,
        contract_violations=(
            len(cove_res["invalid_flags"]) + int(sast_mojibake["mojibake_count"])
            + int(sast_mojibake["invalid_json_count"]) + len(gt14_issues) + len(dirty_orphans) + (0 if chain_ok else 1)
        ),
        high_findings=builder_defects["high"], medium_findings=builder_defects["medium"],
        low_findings=builder_defects["low"], semantic_drift_findings=builder_defects["semantic_drift"],
        doc_drift=len(broken_links) + len(md_chk.get("phantom_scripts", [])) + ste100_drift,
        measured_components=measured_components, unmeasured_components=unmeasured_components,
    )
    delta_k = engine.compute_delta(defects, profile=canonical_profile)
    fitness_q = engine.compute_fitness(defects, delta_k=delta_k, profile=canonical_profile)
    real_state_hash = engine.compute_files_state_hash(verified_files)
    q_v2_res = _compute_ecosystem_q_v2(
        root, canonical_profile, defects, checks, unmeasured_components, ste100_warnings,
        strict_verify=strict_verify, strict_unmeasured_gate=strict_unmeasured_gate,
        diff_aware=diff_aware, allowed_files=allowed_files,
        f_holdout=f_holdout, scope_creep_override=builder_defects.get("scope_creep"),
    )
    status_str, passed = _resolve_ecosystem_status_and_pass(unmeasured_components, violations, delta_k, fitness_q, checks, q_v2_res)
    return finalize_ecosystem_verify_ext(
        engine, root, canonical_profile, defects, delta_k, fitness_q, real_state_hash, q_v2_res,
        status_str, passed, persist_telemetry, measured_components, unmeasured_components, checks,
        violations, ste100_warnings, RSIIterationRecord, int(time.time()),
    )


__all__ = [
    "_audit_gt14_governance",
    "_audit_markdown_docs",
    "_audit_quality_and_frontend",
    "_audit_twin_manifest_parity",
    "_report_is_dry_run",
    "verify_ecosystem_impl",
]

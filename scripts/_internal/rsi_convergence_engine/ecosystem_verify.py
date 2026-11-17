"""Verifica ecosistema Guardia G6 con Overlay Union e STE100 stretto su repo_map.md."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.rsi_convergence_engine.constants import RSIDefectVector, RSIIterationRecord
from _internal.rsi_convergence_engine.eco_audits import (
    audit_gt14_governance_impl as _audit_gt14_governance,
    audit_markdown_docs_impl as _audit_markdown_docs,
    report_is_dry_run_impl as _report_is_dry_run,
)
from _internal.rsi_convergence_engine.profiles import (
    RSIProfileRegistry,
    verify_ste100_compliance,
)
from _internal.rsi_convergence_engine.sast_scanner import audit_tas_reports_impl


def verify_ecosystem_impl(
    engine: Any,
    root_dir: Optional[Path] = None,
    run_pytest: bool = False,
    profile: str = "code_rsi",
    benchmark_suite: Optional[str] = None,
    sast_report: Optional[Path | str] = None,
    strict_verify: bool = False,
    persist_telemetry: bool = False,
    test_report: Optional[Dict[str, Any]] = None,
    dast_report: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Esegue la verifica completa Guardia G6 sull'ecosistema con Overlay Union e metriche reali."""
    if isinstance(root_dir, bool):
        should_run_pytest = root_dir or bool(run_pytest)
        root = engine.workspace_root
    else:
        should_run_pytest = bool(run_pytest)
        root = Path(root_dir).resolve() if root_dir else engine.workspace_root

    canonical_profile = RSIProfileRegistry.get(profile).name
    violations: List[str] = []
    checks: Dict[str, Any] = {}
    verified_files: List[Path] = []
    measured_components: List[str] = [
        "skills_and_markdown",
        "cli_flags_cove",
        "telemetry_chain",
        "sast_and_mojibake",
        "workspace_clean_hygiene",
    ]
    unmeasured_components: List[str] = []

    agents_md = engine._resolve_candidate(root, ".agents/AGENTS.md")
    anti_crash_md = engine._resolve_candidate(
        root, ".agents/rules/anti_crash_rules.md"
    )
    if agents_md.exists():
        verified_files.append(agents_md)
        if anti_crash_md.exists():
            verified_files.append(anti_crash_md)
        measured_components.insert(0, "agents_md")
        agents_bytes = agents_md.stat().st_size
        crash_bytes = anti_crash_md.stat().st_size if anti_crash_md.exists() else 0
        combined_bytes = agents_bytes + crash_bytes
        budget_ok = agents_bytes < 24000 and combined_bytes < 26000
        if not budget_ok:
            violations.append(
                f"AGENTS.md supera il limite di 24000 byte ({agents_bytes} B, combinato {combined_bytes} B)."
            )
        agents_text = agents_md.read_text(encoding="utf-8", errors="replace")
        ste_res = verify_ste100_compliance(agents_text)
        agents_ste_warnings = (
            list(ste_res["violations"][:5])
            if "[RULE-STE100]" in agents_text and not ste_res["passed"]
            else []
        )
        checks["agents_md"] = {
            "passed": budget_ok,
            "agents_bytes": agents_bytes,
            "combined_bytes": combined_bytes,
            "ste100_passed": ste_res["passed"],
            "ste100_warnings": agents_ste_warnings,
        }

    md_chk = _audit_markdown_docs(
        engine, root, canonical_profile, verified_files, violations
    )
    checks["skills_and_markdown"] = md_chk
    broken_links = md_chk["broken_links"]
    ste100_warnings = list(checks.get("agents_md", {}).get("ste100_warnings", [])) + list(
        md_chk.get("ste100_warnings", [])
    )

    cove_res = engine.verify_cli_flags_cove(root)
    checks["cli_flags_cove"] = cove_res
    if not cove_res["passed"]:
        violations.extend(f"Flag CLI non valido: {inv}" for inv in cove_res["invalid_flags"])

    telemetry_file = engine._resolve_candidate(root, "nk_tracking/rsi_telemetry.jsonl")
    if telemetry_file.exists():
        verified_files.append(telemetry_file)
    chain_ok, chain_count, chain_msg = engine.verify_telemetry_chain(telemetry_file)
    if not chain_ok:
        violations.append(chain_msg)
    checks["telemetry_chain"] = {
        "passed": chain_ok,
        "records_verified": chain_count,
        "details": chain_msg,
    }

    sast_mojibake = engine._scan_sast_and_mojibake(root, sast_report=sast_report)
    verified_files.extend(sast_mojibake.pop("scanned_files", []))
    checks["sast_and_mojibake"] = sast_mojibake
    if (
        _report_is_dry_run(sast_report)
        or _report_is_dry_run(dast_report)
        or _report_is_dry_run(test_report)
    ):
        unmeasured_components.append("UNMEASURED_DRY_RUN")
        violations.append("Report sandbox eseguito in modalita dry-run non certificabile.")
    if sast_mojibake["sast_issues"]:
        violations.extend(sast_mojibake["sast_issues"])
    if sast_mojibake["mojibake_files"]:
        violations.extend(
            f"{fname}: rilevato carattere di sostituzione U+FFFD vietato."
            for fname in sast_mojibake["mojibake_files"]
        )
    if sast_mojibake["invalid_json_files"]:
        violations.extend(
            f"JSON invalido: {jerr}" for jerr in sast_mojibake["invalid_json_files"]
        )

    hallucinated_refs_count, tas_chk = audit_tas_reports_impl(
        engine, root, verified_files, violations
    )
    checks["tas_report_grounding"] = tas_chk

    gt14_issues, gt14_chk = _audit_gt14_governance(root, measured_components, violations)
    checks["gt14_crit01_governance"] = gt14_chk

    dirty_orphans: List[str] = []
    for _scan_d in (root, root / "nk_genome", root / "scripts", root / ".agents"):
        if _scan_d.is_dir():
            for _pat in ("*.tmp", "*.bak"):
                for _f in sorted(_scan_d.glob(_pat)):
                    rel_orph = str(_f.relative_to(root)).replace("\\", "/")
                    if rel_orph not in dirty_orphans:
                        dirty_orphans.append(rel_orph)
    checks["workspace_clean_hygiene"] = {
        "passed": len(dirty_orphans) == 0,
        "dirty_files": dirty_orphans,
    }
    if dirty_orphans:
        violations.append(f"File temporanei/orfani rilevati nel workspace: {dirty_orphans}")

    bench_failed, bench_passed, bench_total = 0, 0, 0
    prod_tests_dir = root / "tests"
    stg_tests_dir = root / ".staging" / "tests"
    has_auto_tests = (
        prod_tests_dir.is_dir() and any(prod_tests_dir.rglob("test_*.py"))
    ) or (stg_tests_dir.is_dir() and any(stg_tests_dir.rglob("test_*.py")))

    if isinstance(test_report, dict):
        measured_components.append("benchmark_suite")
        bench_passed = int(test_report.get("tests_passed", test_report.get("passed_count", 0)))
        bench_failed = int(test_report.get("tests_failed", test_report.get("failed_count", 0)))
        bench_skipped = int(test_report.get("tests_skipped", test_report.get("skipped_count", 0)))
        bench_total = int(
            test_report.get("tests_total", max(0, bench_passed + bench_failed + bench_skipped))
        )
        rep_ok = (
            bench_failed == 0
            and bench_skipped == 0
            and bench_passed > 0
            and bench_total > 0
            and bench_passed >= bench_total
        )
        bench_cov = {
            k: test_report[k]
            for k in (
                "duration_s",
                "branch_coverage_pct",
                "statement_coverage_pct",
                "true_branch_coverage_pct",
                "combined_coverage_pct",
            )
            if k in test_report and test_report[k] is not None
        }
        checks["benchmark_suite"] = {
            "executed": True,
            "injected": True,
            "passed": rep_ok,
            "tests_passed": bench_passed,
            "tests_failed": bench_failed,
            "tests_skipped": bench_skipped,
            "tests_total": bench_total,
            **bench_cov,
            "details": (
                f"Injected test report: {bench_passed}/{bench_total} passed, "
                f"{bench_skipped} skipped."
            ),
        }
        if not rep_ok:
            violations.append(checks["benchmark_suite"]["details"])
    elif benchmark_suite or should_run_pytest or (strict_verify and has_auto_tests):
        default_tests_dir = prod_tests_dir if prod_tests_dir.is_dir() else stg_tests_dir
        target_suite = benchmark_suite if benchmark_suite else str(default_tests_dir)
        bench_res = engine.run_benchmark_suite(target_suite, root_dir=root)
        checks["benchmark_suite"] = bench_res
        measured_components.append("benchmark_suite")
        bench_failed = int(bench_res["tests_failed"])
        bench_passed = int(bench_res["tests_passed"])
        bench_total = int(bench_res["tests_total"])
        if not bench_res["passed"]:
            violations.append(bench_res["details"])
    else:
        unmeasured_components.append("benchmark_suite")
        if strict_verify:
            violations.append(
                f"Nessuna suite di test misurata in modalita --strict-verify per '{root}'."
            )

    phantom_scripts = list(md_chk.get("phantom_scripts", []))
    ste100_drift = len(ste100_warnings) if strict_verify else 0
    doc_drift_count = len(broken_links) + len(phantom_scripts) + ste100_drift
    if ste100_drift > 0:
        violations.extend(ste100_warnings)

    defects = RSIDefectVector(
        sast_critical=int(sast_mojibake["sast_critical"]),
        hallucinated_refs=hallucinated_refs_count,
        tests_failed=bench_failed,
        tests_passed=bench_passed,
        tests_total=bench_total,
        contract_violations=len(broken_links)
        + len(cove_res["invalid_flags"])
        + int(sast_mojibake["mojibake_count"])
        + int(sast_mojibake["invalid_json_count"])
        + len(gt14_issues)
        + len(dirty_orphans)
        + (0 if chain_ok else 1),
        doc_drift=doc_drift_count,
        measured_components=measured_components,
        unmeasured_components=unmeasured_components,
    )
    delta_k = engine.compute_delta(defects, profile=canonical_profile)
    fitness_q = engine.compute_fitness(
        defects, delta_k=delta_k, profile=canonical_profile
    )
    real_state_hash = engine.compute_files_state_hash(verified_files)

    if unmeasured_components:
        status_str = "UNMEASURED"
        passed = False
    else:
        passed = (
            len(violations) == 0
            and delta_k == 0
            and fitness_q >= 100.0
            and checks["workspace_clean_hygiene"]["passed"]
        )
        status_str = "CONVERGED_OPTIMAL" if passed else "REFINING"

    if persist_telemetry:
        rec = RSIIterationRecord(
            session_id=f"VERIFY-{int(time.time())}",
            iteration=0,
            mode="mode_a",
            defects=defects,
            delta_k=delta_k,
            fitness_q=fitness_q,
            state_hash=real_state_hash,
            verdict=status_str,
            rolled_back=False,
        )
        engine.append_telemetry_record(rec)

    suite_chk = checks.get("benchmark_suite")
    suite_duration = suite_chk.get("duration_s") if isinstance(suite_chk, dict) else None
    out_payload: Dict[str, Any] = {
        "status": status_str,
        "passed": passed,
        "scope": str(root),
        "profile": canonical_profile,
        "delta_k": delta_k,
        "fitness_q": fitness_q,
        "state_hash": real_state_hash,
        "grounding_shield_active": True,
        "measured_components": measured_components,
        "unmeasured_components": unmeasured_components,
        "checks": checks,
        "violations": violations,
        "ste100_warnings": ste100_warnings,
    }
    if suite_duration is not None:
        out_payload["duration_s"] = suite_duration
    return out_payload


__all__ = [
    "_audit_gt14_governance",
    "_audit_markdown_docs",
    "_report_is_dry_run",
    "verify_ecosystem_impl",
]

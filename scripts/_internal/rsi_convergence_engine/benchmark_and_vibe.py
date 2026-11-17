"""Micro-loop Vibe Check (<500ms) e re-export benchmark suite per RSI."""

from __future__ import annotations

import ast
import json
import subprocess  # noqa: F401 - preservato per monkeypatch test su bv.subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.rsi_convergence_engine.constants import (
    EXCLUDED_SCAN_DIRS,
    RSIDefectVector,
    _extract_sast_report_count,
    _workspace_root,
)
from _internal.rsi_convergence_engine.lazy_bridge import get_ast_guard_validator
from _internal.rsi_convergence_engine.profiles import (
    RSIProfileRegistry,
    compute_delta,
    compute_fitness,
    verify_ste100_compliance,
)
from _internal.rsi_convergence_engine.pytest_benchmark_runner import (
    run_benchmark_suite_impl,
)
from _internal.rsi_convergence_engine.sast_scanner import (
    audit_markdown_doc_references,
)


def _resolve_staging_baseline_text(fpath: Path, fallback_root: Path) -> str:
    """Carica il file baseline di produzione quando fpath risiede dentro .staging/."""
    resolved_f = fpath.resolve()
    parts = resolved_f.parts
    for idx in range(len(parts) - 1, -1, -1):
        if parts[idx] == ".staging":
            stg_base = Path(*parts[: idx + 1])
            prod_root = stg_base.parent
            try:
                rel_after_stg = resolved_f.relative_to(stg_base)
            except ValueError:
                break
            for root_cand in (prod_root, Path(fallback_root).resolve()):
                prod_cand = root_cand / rel_after_stg
                if prod_cand.is_file():
                    try:
                        return prod_cand.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        return ""
            return ""
    return ""


def _resolve_vibe_root(target: Path, fallback_root: Path) -> Path:
    """Risolve la radice workspace per i controlli relativi su link e script."""
    resolved_t = target.resolve()
    parts = resolved_t.parts
    for idx in range(len(parts) - 1, -1, -1):
        if parts[idx] == ".staging":
            return Path(*parts[:idx])
        if parts[idx] in (".agents", "nk_genome", "scripts"):
            parent_d = Path(*parts[:idx])
            return parent_d.parent if parent_d.name == ".staging" else parent_d
    return Path(fallback_root).resolve()


def run_vibe_check_impl(
    engine: Any,
    target_path: Path | str,
    profile: str = "vibe_sprint_micro_rsi",
    sast_report: Optional[Path | str] = None,
    strict_verify: bool = False,
) -> Dict[str, Any]:
    """Esegue il micro-loop Vibe Check statico in-memory (<500ms) senza test sintetici."""
    t0 = time.perf_counter()
    target = Path(target_path).resolve()
    active_profile = RSIProfileRegistry.get(profile).name
    violations: List[str] = []
    ste100_warnings: List[str] = []
    sast_count = _extract_sast_report_count(sast_report)
    contract_count = 0
    drift_count = 0
    vibe_root = _resolve_vibe_root(target, engine.workspace_root)
    deleted_rel = engine._load_staging_deleted_set(vibe_root)

    if not target.exists():
        return {
            "status": "REFINING",
            "passed": False,
            "profile": active_profile,
            "target": str(target),
            "delta_k": 10,
            "fitness_q": 28.5714,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "violations": [f"Target non trovato: {target}"],
            "ste100_warnings": [],
        }

    vibe_excluded = EXCLUDED_SCAN_DIRS - {".staging"}
    if target.is_file():
        files_to_check: List[Path] = [target]
    elif (target == engine.root or target == _workspace_root) and (
        (target / ".agents").exists() or (target / ".staging").exists()
    ):
        roots_to_scan: List[Path] = []
        if (target / ".agents").exists():
            roots_to_scan.append(target / ".agents")
        if (target / ".staging").exists():
            roots_to_scan.append(target / ".staging")
        collected: List[Path] = []
        for s_root in roots_to_scan:
            collected.extend(
                p
                for p in s_root.rglob("*")
                if p.is_file()
                and p.suffix in (".py", ".md", ".json")
                and not any(
                    part in vibe_excluded for part in p.relative_to(s_root).parts
                )
            )
        files_to_check = sorted(list(dict.fromkeys(collected)))
    else:
        files_to_check = sorted(
            [
                p
                for p in target.rglob("*")
                if p.is_file()
                and p.suffix in (".py", ".md", ".json")
                and not any(
                    part in vibe_excluded for part in p.relative_to(target).parts
                )
            ]
        )

    agv_cls: Any = None
    for fpath in files_to_check:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            contract_count += 1
            violations.append(f"{fpath.name}: Errore lettura file ({exc})")
            continue

        if "\ufffd" in text:
            contract_count += 1
            violations.append(
                f"{fpath.name}: Rilevato carattere di sostituzione U+FFFD vietato."
            )

        if fpath.suffix == ".py":
            if agv_cls is None:
                agv_cls = get_ast_guard_validator()
            if agv_cls is not None:
                baseline_text = _resolve_staging_baseline_text(fpath, vibe_root)
                rep = agv_cls.validate_code_edit(
                    baseline_text, text, target_file=fpath.as_posix()
                )
                if not rep.is_valid:
                    sast_in_rep = int(rep.metrics.get("sast_violations_count", 0))
                    sast_count += sast_in_rep
                    contract_count += max(0, len(rep.violations) - sast_in_rep)
                    for v in rep.violations:
                        violations.append(f"{fpath.name}: {v.message}")
            else:
                try:
                    ast.parse(text)
                except SyntaxError as se:
                    contract_count += 1
                    violations.append(f"{fpath.name}: SyntaxError ({se.msg})")
        elif fpath.suffix == ".md":
            ste = verify_ste100_compliance(text, max_sentence_words=20)
            if not ste["passed"]:
                for sv in ste["violations"][:3]:
                    ste100_warnings.append(f"{fpath.name}: {sv}")
            is_active_doc = any(
                part in (".agents", "nk_genome") for part in fpath.parts
            ) and fpath.name not in ("PATCH_NOTES.md", "repo_map.md", "SKILL_INDEX.md")
            if is_active_doc:
                b_links, p_scripts = audit_markdown_doc_references(
                    fpath,
                    text,
                    vibe_root,
                    engine._resolve_candidate,
                    deleted_rel=deleted_rel,
                    check_scripts=True,
                )
                for b_lnk in b_links:
                    violations.append(f"Link interrotto: {b_lnk}")
                for p_sc in p_scripts:
                    violations.append(p_sc)
                drift_count += len(b_links) + len(p_scripts)
        elif fpath.suffix == ".json":
            try:
                json.loads(text)
            except Exception as exc:
                contract_count += 1
                violations.append(f"{fpath.name}: JSON invalido ({exc})")

    if strict_verify and ste100_warnings:
        drift_count += len(ste100_warnings)
        violations.extend(ste100_warnings)

    defects = RSIDefectVector(
        sast_critical=sast_count,
        tests_failed=0,
        tests_passed=0,
        tests_total=0,
        contract_violations=contract_count,
        doc_drift=drift_count,
        measured_components=["sast_ast_guard", "mojibake_utf8", "ste100_markdown"],
        unmeasured_components=["benchmark_suite"],
    )
    d_k = compute_delta(defects, profile=active_profile)
    q_k = compute_fitness(defects, delta_k=d_k, profile=active_profile)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    passed = d_k == 0 and len(violations) == 0

    return {
        "status": "VIBE_STATIC_PASS" if passed else "REFINING",
        "passed": passed,
        "profile": active_profile,
        "target": str(target),
        "delta_0": d_k,
        "delta_k": d_k,
        "fitness_q": q_k,
        "measured_components": defects.measured_components,
        "unmeasured_components": defects.unmeasured_components,
        "elapsed_ms": elapsed_ms,
        "violations": violations,
        "ste100_warnings": ste100_warnings,
    }


__all__ = ["run_benchmark_suite_impl", "run_vibe_check_impl"]

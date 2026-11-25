# -*- coding: utf-8 -*-
"""Micro-loop Vibe Check (<500ms) e re-export benchmark suite per RSI."""

from __future__ import annotations

import ast
import json
import subprocess  # noqa: F401 - preservato per monkeypatch test su bv.subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.rsi_convergence_engine.constants import (
    EXCLUDED_SCAN_DIRS, RSIDefectVector, VIBE_SCAN_SUFFIXES,
    _workspace_root, get_ast_guard_validator, normalize_rel_for_root,
)
from _internal.rsi_convergence_engine.eco_audits import (
    FRONTEND_SUFFIXES, classify_quality_violations, inspect_frontend_file, inspect_python_quality_staged,
)
from _internal.rsi_convergence_engine.profiles import (
    RSIProfileRegistry, compute_delta, compute_fitness, compute_fitness_v2, verify_ste100_compliance,
)
from _internal.rsi_convergence_engine.sast_scanner import audit_markdown_doc_references
from _internal.rsi_convergence_engine.vibe_report_helpers import audit_sast_report_payload, run_benchmark_suite_impl


def _scan_dir_suffixes(base_dir: Path, excluded_dirs: Set[str]) -> List[Path]:
    """Raccoglie ricorsivamente i file supportati escludendo directory vietate."""
    if not base_dir.exists():
        return []
    return [
        p for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in VIBE_SCAN_SUFFIXES and not any(part in excluded_dirs for part in p.relative_to(base_dir).parts)
    ]


def collect_vibe_files(target: Path, engine_root: Path, default_workspace_root: Path, excluded_dirs: Set[str]) -> List[Path]:
    """Raccoglie i file target per Vibe Check includendo moduli frontend e staging."""
    if target.is_file():
        return [target]
    vibe_excluded = excluded_dirs - {".staging"}
    if (target == engine_root or target == default_workspace_root) and ((target / ".agents").exists() or (target / ".staging").exists()):
        collected: List[Path] = []
        for s_root in (target / ".agents", target / ".staging"):
            collected.extend(_scan_dir_suffixes(s_root, vibe_excluded))
        return sorted(list(dict.fromkeys(collected)))
    return sorted(_scan_dir_suffixes(target, vibe_excluded))


def root_root_join(root_cand: Path, rel_after_stg: Path) -> Path:
    """Compone il path di produzione evitando ripetizioni ridondanti NK_Hub/ (P0-02)."""
    return root_cand / normalize_rel_for_root(root_cand, rel_after_stg.as_posix())


def _resolve_staging_baseline_text(fpath: Path, fallback_root: Path) -> str:
    """Carica il file baseline di produzione quando fpath risiede dentro .staging/."""
    resolved_f = fpath.resolve()
    parts = resolved_f.parts
    for idx in range(len(parts) - 1, -1, -1):
        if parts[idx] == ".staging":
            stg_base = Path(*parts[: idx + 1])
            try:
                rel_after_stg = resolved_f.relative_to(stg_base)
            except ValueError:
                break
            for root_cand in (stg_base.parent, Path(fallback_root).resolve()):
                prod_cand = root_root_join(root_cand, rel_after_stg)
                if prod_cand.is_file():
                    try:
                        return prod_cand.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        return ""
            return ""
    return ""


def _resolve_vibe_root(target: Path, fallback_root: Path) -> Path:
    """Risolve la radice workspace per i controlli relativi su link e script."""
    parts = target.resolve().parts
    for idx in range(len(parts) - 1, -1, -1):
        if parts[idx] == ".staging":
            return Path(*parts[:idx])
        if parts[idx] in (".agents", "nk_genome", "scripts"):
            parent_d = Path(*parts[:idx])
            return parent_d.parent if parent_d.name == ".staging" else parent_d
    return Path(fallback_root).resolve()


def _rel_label_for_vibe(fpath: Path, vibe_root: Path) -> str:
    """Restituisce un label relativo POSIX per Quality-Diff preservando path tests/."""
    try:
        rel_p = fpath.resolve().relative_to(vibe_root.resolve()).as_posix()
        return rel_p[len(".staging/") :] if rel_p.startswith(".staging/") else rel_p
    except ValueError:
        return fpath.as_posix()


def _inspect_py_vibe_file(fpath: Path, text: str, vibe_root: Path, agv_cls: Any, state: Dict[str, Any]) -> None:
    """Analizza un singolo file Python per SAST/AST e Quality-Diff differenziale."""
    baseline_text = _resolve_staging_baseline_text(fpath, vibe_root)
    if agv_cls is not None:
        rep = agv_cls.validate_code_edit(baseline_text, text, target_file=fpath.as_posix())
        if not rep.is_valid:
            sast_in_rep = int(rep.metrics.get("sast_violations_count", 0))
            state["sast"] += sast_in_rep
            state["contract"] += max(0, len(rep.violations) - sast_in_rep)
            state["violations"].extend(f"{fpath.name}: {v.message}" for v in rep.violations)
    else:
        try:
            ast.parse(text)
        except SyntaxError as se:
            state["contract"] += 1
            state["violations"].append(f"{fpath.name}: SyntaxError ({se.msg})")

    rel_label = _rel_label_for_vibe(fpath, vibe_root)
    qd_viols = inspect_python_quality_staged(fpath, baseline_text, text, rel_label, vibe_root)
    if ".staging" in fpath.parts:
        state["qd_ran"] = True
    if qd_viols:
        bucket = classify_quality_violations(qd_viols)
        state["semantic"] += bucket["semantic_drift_findings"]
        state["high"] += bucket["high_findings"]
        state["medium"] += bucket["medium_findings"]
        state["low"] += bucket["low_findings"]
        state["violations"].extend(bucket["messages"])


def _is_active_vibe_doc(fpath: Path) -> bool:
    if fpath.name in ("PATCH_NOTES.md", "repo_map.md", "SKILL_INDEX.md"):
        return False
    return ".agents" in fpath.parts or "nk_genome" in fpath.parts


def _maybe_record_ste100_warn(fpath: Path, text: str, state: Dict[str, Any]) -> None:
    if ".agents" not in fpath.parts and ".agents" not in text and "[RULE-STE100]" not in text:
        return
    ste_res = verify_ste100_compliance(text)
    if not ste_res["passed"]:
        state["ste100_warnings"].extend(f"{fpath.name}: {v}" for v in ste_res["violations"][:2])


def _inspect_md_vibe_file(engine: Any, fpath: Path, text: str, vibe_root: Path, deleted_rel: Set[str], state: Dict[str, Any]) -> None:
    """Analizza un singolo file Markdown per link, script fantasma e STE100."""
    b_links, p_scripts = audit_markdown_doc_references(
        fpath, text, vibe_root, engine._resolve_candidate, deleted_rel=deleted_rel, check_scripts=_is_active_vibe_doc(fpath)
    )
    if b_links:
        state["drift"] += len(b_links)
        state["violations"].extend(b_links)
    if p_scripts:
        state["contract"] += len(p_scripts)
        state["violations"].extend(p_scripts)
    _maybe_record_ste100_warn(fpath, text, state)


def _inspect_single_vibe_file(engine: Any, fpath: Path, vibe_root: Path, deleted_rel: Set[str], agv_cls: Any, state: Dict[str, Any]) -> None:
    """Ispeziona un file in base all'estensione aggiornando il contatore difetti."""
    try:
        text = fpath.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        state["contract"] += 1
        state["violations"].append(f"{fpath.name}: Errore lettura file ({exc})")
        return
    if "\ufffd" in text:
        state["contract"] += 1
        state["violations"].append(f"{fpath.name}: Rilevato carattere di sostituzione U+FFFD vietato.")
    suffix = fpath.suffix.lower()
    if suffix == ".py":
        _inspect_py_vibe_file(fpath, text, vibe_root, agv_cls, state)
    elif suffix == ".md":
        _inspect_md_vibe_file(engine, fpath, text, vibe_root, deleted_rel, state)
    elif suffix == ".json":
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            state["contract"] += 1
            state["violations"].append(f"{fpath.name}: JSON invalido ({exc})")
    elif suffix in FRONTEND_SUFFIXES:
        state["fe_ran"] = True
        fe_viols = inspect_frontend_file(fpath, text, _rel_label_for_vibe(fpath, vibe_root), vibe_root)
        if fe_viols:
            bucket = classify_quality_violations(fe_viols)
            state["high"] += bucket["high_findings"]
            state["medium"] += bucket["medium_findings"]
            state["low"] += bucket["low_findings"]
            state["violations"].extend(bucket["messages"])


def _finalize_vibe_result(
    target: Path, active_profile: str, defects: RSIDefectVector, state: Dict[str, Any],
    files_to_check: List[Path], t0: float,
) -> Dict[str, Any]:
    d_k = compute_delta(defects, profile=active_profile)
    q_k = compute_fitness(defects, delta_k=d_k, profile=active_profile)
    ste100_score = 1.0 if not state["ste100_warnings"] else max(0.0, 1.0 - 0.1 * len(state["ste100_warnings"]))
    q_v2_res = compute_fitness_v2(
        defects, has_python_diff=any(p.suffix.lower() == ".py" for p in files_to_check),
        scope_creep=state["semantic"], ste100_score=ste100_score,
    )
    passed = d_k == 0 and not state["violations"]
    return {
        "status": "VIBE_STATIC_PASS" if passed else "REFINING",
        "passed": passed, "profile": active_profile, "target": str(target),
        "delta_0": d_k, "delta_k": d_k, "fitness_q": q_k,
        "q_v2": q_v2_res["q_v2"], "g_hard": q_v2_res["g_hard"],
        "delta_hard": q_v2_res["delta_hard"], "certification_tier": q_v2_res["certification_tier"],
        "vibe_role": "C0_PRECHECK",
        "measured_components": defects.measured_components, "unmeasured_components": defects.unmeasured_components,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "violations": state["violations"], "ste100_warnings": state["ste100_warnings"],
    }


def _resolve_vibe_profile(profile: str, strict_profile: bool) -> str:
    return (RSIProfileRegistry.get_strict(profile) if strict_profile else RSIProfileRegistry.get(profile)).name


def _audit_vibe_sast_init(sast_report: Optional[Path | str]) -> tuple[int, List[str]]:
    if sast_report is None:
        return 0, []
    sast_chk = audit_sast_report_payload(sast_report)
    sast_init = int(sast_chk.get("sast_critical", 0)) + int(sast_chk.get("sast_taint", 0))
    if not sast_chk.get("passed", False):
        return max(1, sast_init), list(sast_chk.get("violations", []))
    return sast_init, []


def run_vibe_check_impl(
    engine: Any, target_path: Path | str, profile: str = "vibe_sprint_micro_rsi",
    sast_report: Optional[Path | str] = None, strict_verify: bool = False,
    strict_profile: bool = False,
) -> Dict[str, Any]:
    """Esegue il micro-loop Vibe Check statico (C0_PRECHECK) in-memory (<500ms)."""
    t0 = time.perf_counter()
    target = Path(target_path).resolve()
    active_profile = _resolve_vibe_profile(profile, strict_profile)
    vibe_root = _resolve_vibe_root(target, engine.workspace_root)
    deleted_rel = engine._load_staging_deleted_set(vibe_root)

    if not target.exists():
        return {
            "status": "REFINING", "passed": False, "profile": active_profile, "target": str(target),
            "delta_k": 10, "fitness_q": 28.5714, "q_v2": 0.0, "g_hard": 0, "delta_hard": 1,
            "certification_tier": "FAIL", "vibe_role": "C0_PRECHECK",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "violations": [f"Target non trovato: {target}"], "ste100_warnings": [],
        }

    files_to_check = collect_vibe_files(target, engine.root, _workspace_root, EXCLUDED_SCAN_DIRS)
    agv_cls = get_ast_guard_validator() if any(p.suffix == ".py" for p in files_to_check) else None
    sast_init, sast_viols = _audit_vibe_sast_init(sast_report)
    state: Dict[str, Any] = {
        "violations": sast_viols, "ste100_warnings": [], "sast": sast_init,
        "contract": 0, "drift": 0, "semantic": 0, "high": 0, "medium": 0, "low": 0,
        "qd_ran": False, "fe_ran": False,
    }
    for fpath in files_to_check:
        _inspect_single_vibe_file(engine, fpath, vibe_root, deleted_rel, agv_cls, state)

    if strict_verify and state["ste100_warnings"]:
        state["drift"] += len(state["ste100_warnings"])
        state["violations"].extend(state["ste100_warnings"])

    measured = ["sast_ast_guard", "mojibake_utf8", "ste100_markdown"]
    if state["qd_ran"]:
        measured.append("quality_diff_ast")
    if state["fe_ran"]:
        measured.append("frontend_static_gate")

    defects = RSIDefectVector(
        sast_critical=state["sast"], contract_violations=state["contract"],
        high_findings=state["high"], medium_findings=state["medium"], low_findings=state["low"],
        doc_drift=state["drift"], semantic_drift_findings=state["semantic"],
        measured_components=measured, unmeasured_components=["benchmark_suite"],
    )
    return _finalize_vibe_result(target, active_profile, defects, state, files_to_check, t0)


__all__ = ["run_benchmark_suite_impl", "run_vibe_check_impl"]

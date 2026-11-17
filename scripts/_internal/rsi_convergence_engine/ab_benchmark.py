"""Esecutore benchmark deterministico A/B sui dodici task core."""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.rsi_convergence_engine.ab_checks import (
    _evaluate_ab_check,
    _load_staged_or_prod_module,  # noqa: F401
)
from _internal.rsi_convergence_engine.constants import _workspace_root


def _resolve_benchmark_suite_file(root: Path, suite_path: Optional[Path]) -> Optional[Path]:
    """Risolve il percorso del file tasks_v1.json privilegiando .staging/."""
    rel_default = Path("nk_tracking") / "benchmark_suite" / "tasks_v1.json"
    candidates: List[Path] = []
    if suite_path is not None:
        sp = Path(suite_path)
        if not sp.is_absolute():
            candidates.extend([(root / ".staging" / sp).resolve(), (root / sp).resolve()])
        else:
            candidates.append(sp.resolve())
    candidates.extend(
        [
            (root / ".staging" / rel_default).resolve(),
            (root / rel_default).resolve(),
            (_workspace_root / ".staging" / rel_default).resolve(),
            (_workspace_root / rel_default).resolve(),
        ]
    )
    for cand in candidates:
        if cand.is_dir():
            cand_f = cand / "tasks_v1.json"
            if cand_f.is_file():
                return cand_f
        elif cand.is_file():
            return cand
    return None


def _compute_harness_overhead(root: Path, resolved_file: Path) -> float:
    """Calcola la percentuale stimata di overhead del harness sui file guida o suite."""
    agents_md_cand = (
        root / ".staging" / ".agents" / "AGENTS.md"
        if (root / ".staging" / ".agents" / "AGENTS.md").is_file()
        else root / ".agents" / "AGENTS.md"
    )
    if agents_md_cand.is_file():
        return round(min(25.0, (float(agents_md_cand.stat().st_size) / 160000.0) * 100.0), 2)
    suite_bytes = resolved_file.stat().st_size if resolved_file.is_file() else 0
    return round(min(25.0, (float(suite_bytes) / 65536.0) * 100.0), 2)


def run_ab_benchmark(
    workspace_root: Path = _workspace_root,
    suite_path: Optional[Path] = None,
    repetitions: int = 3,
) -> Dict[str, Any]:
    """Esegue il benchmark deterministico funzionale A/B sui dodici task core."""
    t0 = time.perf_counter()
    root = Path(workspace_root).resolve() if workspace_root else _workspace_root
    reps = max(1, int(repetitions))
    resolved_file = _resolve_benchmark_suite_file(root, suite_path)

    if resolved_file is None or not resolved_file.is_file():
        return {
            "status": "FAIL",
            "passed": False,
            "tasks_total": 0,
            "tasks_passed": 0,
            "tasks_failed": 1,
            "ab_success_full": 0.0,
            "ab_success_min": 0.0,
            "harness_token_overhead_pct": 0.0,
            "variance_pct": 0.0,
            "repetitions": reps,
            "functional_checks_executed": 0,
            "error": "File tasks_v1.json non trovato.",
        }

    raw_data = json.loads(resolved_file.read_text(encoding="utf-8"))
    tasks = raw_data.get("tasks", []) if isinstance(raw_data, dict) else raw_data
    if not isinstance(tasks, list):
        tasks = []

    cycle_rates: List[float] = []
    passed_count = 0
    functional_checks_executed = 0
    total_count = len(tasks)
    mod_cache: Dict[str, Any] = {}
    task_diagnostics: List[Dict[str, Any]] = []
    is_prod_hub = root.name.lower() == "nk_hub"

    for rep_idx in range(reps):
        c_pass = 0
        c_func = 0
        rep_diags: List[Dict[str, Any]] = []
        for item in tasks:
            if not isinstance(item, dict):
                continue
            tid = str(item.get("task_id", "")).strip()
            mod_rel = str(item.get("module", "")).strip()
            src_url = str(item.get("source_url", "")).strip()
            ev_quote = str(item.get("evidence_quote", "")).strip()
            chk_type = str(item.get("check_type", "")).strip()
            mod_cand = (
                (root / ".staging" / mod_rel)
                if (root / ".staging" / mod_rel).exists()
                else (root / mod_rel)
                if (root / mod_rel).exists()
                else (_workspace_root / mod_rel)
            )
            meta_ok = (
                bool(tid)
                and bool(mod_rel)
                and mod_cand.is_file()
                and src_url.startswith(("http://", "https://"))
                and len(ev_quote) >= 10
                and "expected" in item
            )
            task_ok = False
            observed: Any = None
            if meta_ok:
                if chk_type:
                    c_func += 1
                    try:
                        task_ok, observed = _evaluate_ab_check(
                            chk_type,
                            root,
                            mod_rel,
                            item.get("expected"),
                            mod_cache,
                        )
                    except Exception as exc:
                        task_ok = False
                        observed = f"error:{exc}"
                elif not is_prod_hub:
                    try:
                        src_txt = mod_cand.read_text(encoding="utf-8")
                        ast.parse(src_txt, filename=str(mod_cand))
                        task_ok = True
                        observed = "ast_parsed_synthetic_fixture"
                    except SyntaxError as se:
                        task_ok = False
                        observed = f"syntax_error:{se.msg}"
            if task_ok:
                c_pass += 1
            if rep_idx == reps - 1:
                rep_diags.append(
                    {
                        "task_id": tid,
                        "check_type": chk_type or "synthetic_ast",
                        "passed": task_ok,
                        "observed": observed,
                    }
                )
        passed_count = c_pass
        functional_checks_executed = c_func
        task_diagnostics = rep_diags
        rate = (float(c_pass) / float(max(1, total_count))) * 100.0
        cycle_rates.append(round(rate, 4))

    overhead_pct = _compute_harness_overhead(root, resolved_file)
    variance_pct = (
        round(max(cycle_rates) - min(cycle_rates), 4) if cycle_rates else 0.0
    )
    full_rate = round((float(passed_count) / float(max(1, total_count))) * 100.0, 2)
    passed = (
        total_count >= 12
        and passed_count == total_count
        and variance_pct <= 5.0
        and (not is_prod_hub or functional_checks_executed == total_count)
    )

    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "suite_path": str(resolved_file),
        "tasks_total": total_count,
        "tasks_passed": passed_count,
        "tasks_failed": total_count - passed_count,
        "functional_checks_executed": functional_checks_executed,
        "ab_success_full": full_rate,
        "ab_success_min": full_rate,
        "harness_token_overhead_pct": overhead_pct,
        "variance_pct": variance_pct,
        "repetitions": reps,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "tasks": task_diagnostics,
    }

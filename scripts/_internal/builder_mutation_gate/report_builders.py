# -*- coding: utf-8 -*-
"""Costruttori Pydantic fail-closed dei rapporti per builder_mutation_gate."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Sequence

from pydantic import BaseModel, ConfigDict


class MutantOutcome(BaseModel):
    """Esito dell'esecuzione fail-fast su un singolo mutante AST."""

    model_config = ConfigDict(strict=True, extra="forbid")
    mutant_id: str
    operator: str
    function_name: str
    line_number: int
    killed: bool
    exit_code: int
    timed_out: bool
    crashed: bool = False
    duration_sec: float


class MutationGateReport(BaseModel):
    """Rapporto complessivo del gate di mutation testing differenziale."""

    model_config = ConfigDict(strict=True, extra="forbid")
    status: str = "PASS"
    passed: bool
    baseline_passed: bool
    target_file: str
    touched_functions: List[str]
    mutants_total: int
    mutants_killed: int
    mutants_survived: int
    mutants_timed_out: int = 0
    mutants_crashed: int = 0
    kill_rate: float
    min_kill_rate: float
    budget_exhausted: bool
    elapsed_sec: float
    outcomes: List[MutantOutcome]
    message: str


def _build_missing_target_report(
    ws_root: Path,
    rel_target: str,
    staged_requested: bool,
    min_kill_rate: float,
    t0: float,
) -> MutationGateReport:
    """Costruisce il rapporto fail-closed quando il sorgente target manca."""
    missing_msg = (
        f"Target staged source file not found in staging: {rel_target}"
        if staged_requested and (ws_root / rel_target).is_file()
        else f"Target source file not found: {rel_target}"
    )
    return MutationGateReport(
        status="FAIL",
        passed=False,
        baseline_passed=False,
        target_file=rel_target,
        touched_functions=[],
        mutants_total=0,
        mutants_killed=0,
        mutants_survived=0,
        mutants_timed_out=0,
        mutants_crashed=0,
        kill_rate=0.0,
        min_kill_rate=min_kill_rate,
        budget_exhausted=False,
        elapsed_sec=round(time.perf_counter() - t0, 4),
        outcomes=[],
        message=missing_msg,
    )


def _build_syntax_error_report(
    rel_target: str,
    syntax_exc: SyntaxError,
    min_kill_rate: float,
    t0: float,
) -> MutationGateReport:
    """Costruisce il rapporto fail-closed quando post_code contiene SyntaxError."""
    lineno = getattr(syntax_exc, "lineno", None) or 1
    detail = getattr(syntax_exc, "msg", None) or str(syntax_exc)
    return MutationGateReport(
        status="FAIL",
        passed=False,
        baseline_passed=False,
        target_file=rel_target,
        touched_functions=[],
        mutants_total=0,
        mutants_killed=0,
        mutants_survived=0,
        mutants_timed_out=0,
        mutants_crashed=0,
        kill_rate=0.0,
        min_kill_rate=min_kill_rate,
        budget_exhausted=False,
        elapsed_sec=round(time.perf_counter() - t0, 4),
        outcomes=[],
        message=f"Mutation gate FAIL: SyntaxError in {rel_target} L{lineno}: {detail}",
    )


def _build_baseline_abort_report(
    rel_target: str,
    touched: List[str],
    mutants_count: int,
    min_kill_rate: float,
    elapsed: float,
) -> MutationGateReport:
    """Costruisce il rapporto fail-closed quando i test baseline falliscono in sandbox."""
    return MutationGateReport(
        status="FAIL",
        passed=False,
        baseline_passed=False,
        target_file=rel_target,
        touched_functions=touched,
        mutants_total=mutants_count,
        mutants_killed=0,
        mutants_survived=mutants_count,
        mutants_timed_out=0,
        mutants_crashed=0,
        kill_rate=0.0,
        min_kill_rate=min_kill_rate,
        budget_exhausted=False,
        elapsed_sec=elapsed,
        outcomes=[],
        message="Mutation gate aborted: baseline tests failed in ShadowSandbox.",
    )


def _build_vacuous_pass_report(
    stg_dir: Path,
    rel_target: str,
    touched: List[str],
    min_kill_rate: float,
    elapsed: float,
    executable_diff: bool = False,
) -> MutationGateReport:
    """Restituisce UNMEASURED se esistono diff eseguibili con 0 mutanti, altrimenti PASS non applicabile."""
    if executable_diff:
        return MutationGateReport(
            status="UNMEASURED",
            passed=False,
            baseline_passed=True,
            target_file=rel_target,
            touched_functions=touched,
            mutants_total=0,
            mutants_killed=0,
            mutants_survived=0,
            mutants_timed_out=0,
            mutants_crashed=0,
            kill_rate=0.0,
            min_kill_rate=min_kill_rate,
            budget_exhausted=False,
            elapsed_sec=elapsed,
            outcomes=[],
            message=(
                f"Mutation Gate UNMEASURED: 0 mutants generated on executable Python diff in {rel_target}."
            ),
        )
    if not touched:
        vac_msg = (
            "No touched functions in staged diff (not applicable; kill_rate=0.0)."
            if (stg_dir / rel_target).is_file()
            else "Target not modified in staging; baseline verified (not applicable; kill_rate=0.0)."
        )
    else:
        vac_msg = "No mutable AST operators in touched functions (not applicable; kill_rate=0.0)."
    return MutationGateReport(
        status="PASS",
        passed=True,
        baseline_passed=True,
        target_file=rel_target,
        touched_functions=touched,
        mutants_total=0,
        mutants_killed=0,
        mutants_survived=0,
        mutants_timed_out=0,
        mutants_crashed=0,
        kill_rate=0.0,
        min_kill_rate=min_kill_rate,
        budget_exhausted=False,
        elapsed_sec=elapsed,
        outcomes=[],
        message=vac_msg,
    )


def _build_final_gate_report(
    rel_target: str,
    touched: List[str],
    mutants: Sequence[object] | List[object],
    outcomes: List[MutantOutcome],
    budget_exhausted: bool,
    min_kill_rate: float,
    elapsed: float,
) -> MutationGateReport:
    """Aggrega kill_rate (solo exit_code==1), timeout/crash dedicati e budget_exhausted."""
    killed_cnt = sum(1 for item in outcomes if item.killed)
    timed_out_cnt = sum(1 for item in outcomes if item.timed_out)
    crashed_cnt = sum(1 for item in outcomes if item.crashed)
    total_run = len(outcomes)
    kill_rate = round(killed_cnt / total_run, 4) if total_run > 0 else 0.0
    gate_ok = (
        (not budget_exhausted)
        and total_run == len(mutants)
        and total_run > 0
        and kill_rate >= min_kill_rate
    )
    if gate_ok:
        msg = f"Mutation Gate PASS: kill_rate={kill_rate:.1%} ({killed_cnt}/{total_run})."
    elif budget_exhausted or total_run < len(mutants):
        msg = (
            f"Mutation Gate FAIL: budget exhausted ({total_run}/{len(mutants)} mutants run, "
            f"kill_rate={kill_rate:.1%})."
        )
    else:
        msg = (
            f"Mutation Gate FAIL: kill_rate={kill_rate:.1%} < {min_kill_rate:.1%} "
            f"({killed_cnt}/{total_run}, timed_out={timed_out_cnt}, crashed={crashed_cnt})."
        )
    return MutationGateReport(
        status="PASS" if gate_ok else "FAIL",
        passed=gate_ok,
        baseline_passed=True,
        target_file=rel_target,
        touched_functions=touched,
        mutants_total=total_run,
        mutants_killed=killed_cnt,
        mutants_survived=max(0, total_run - killed_cnt),
        mutants_timed_out=timed_out_cnt,
        mutants_crashed=crashed_cnt,
        kill_rate=kill_rate,
        min_kill_rate=min_kill_rate,
        budget_exhausted=budget_exhausted,
        elapsed_sec=elapsed,
        outcomes=outcomes,
        message=msg,
    )

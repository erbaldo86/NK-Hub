"""
SBFL Engine - Spectrum-Based Fault Localization Module
Nexus Keystone v1.1.0-Universal | Grand Master Brief Node 2

Implements deterministic Spectrum-Based Fault Localization:
- Ochiai, Tarantula, and DStar (alpha=2.0) suspiciousness metrics.
- Binary Coverage Matrix A in {0, 1}^(m x n) and outcome vector e in {0, 1}^m.
- Tri-Pass Voting Filter for flaky test eradication (3/3 deterministic matching).
- Coincidental Correctness Def-Use weighting for suspiciousness calibration.
- Ultra-compact OchiaiDiagnosticPayload (<80 tokens) with Pydantic v2 Strict Mode.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SpectrumCounts(BaseModel):
    """
    Counts of test executions for a specific code statement:
    - n_ef: Number of failing tests that executed the statement.
    - n_ep: Number of passing tests that executed the statement.
    - n_nf: Number of failing tests that did NOT execute the statement.
    - n_np: Number of passing tests that did NOT execute the statement.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    n_ef: int = Field(ge=0, description="Failing tests executing statement")
    n_ep: int = Field(ge=0, description="Passing tests executing statement")
    n_nf: int = Field(ge=0, description="Failing tests not executing statement")
    n_np: int = Field(ge=0, description="Passing tests not executing statement")

    @property
    def total_failed(self) -> int:
        return self.n_ef + self.n_nf

    @property
    def total_passed(self) -> int:
        return self.n_ep + self.n_np

    @property
    def total_executed(self) -> int:
        return self.n_ef + self.n_ep

    @property
    def total_tests(self) -> int:
        return self.n_ef + self.n_ep + self.n_nf + self.n_np


class DefUseWeight(BaseModel):
    """
    Def-Use weighting information for coincidental correctness calibration.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    statement: str
    def_var: str
    use_count: int = Field(ge=0)
    propagation_weight: float = Field(ge=0.0, le=1.0, default=0.5)


class CoverageRecord(BaseModel):
    """
    Coverage trace record for a single test run execution.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    test_id: str
    passed: bool
    executed_statements: List[str] = Field(default_factory=list)


class SBFLScore(BaseModel):
    """
    Calculated SBFL metrics for a single statement.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    statement: str
    ochiai: float = Field(ge=0.0, le=1.0)
    tarantula: float = Field(ge=0.0, le=1.0)
    dstar: float = Field(ge=0.0)
    calibrated_ochiai: float = Field(ge=0.0, le=1.0)
    spectrum: SpectrumCounts
    rank: int = Field(ge=1, default=1)


class OchiaiDiagnosticPayload(BaseModel):
    """
    High-density diagnostic payload formatted for strict token efficiency (<80 tokens).
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    top_fault: str = Field(description="Statement ID with highest Ochiai suspiciousness")
    ochiai_score: float = Field(ge=0.0, le=1.0)
    spectrum_tuple: Tuple[int, int, int, int] = Field(
        description="(n_ef, n_ep, n_nf, n_np)"
    )
    top_candidates: List[Tuple[str, float]] = Field(
        description="List of (statement, score) for top suspicious statements",
        max_length=5
    )
    flaky_filtered_count: int = Field(ge=0, default=0)

    def to_compact_json(self) -> str:
        """
        Returns an ultra-compact JSON representation (<80 tokens).
        """
        candidates_str = ",".join(
            f'["{stmt}",{score:.4f}]' for stmt, score in self.top_candidates
        )
        return (
            f'{{"flt":"{self.top_fault}",'
            f'"och":{self.ochiai_score:.4f},'
            f'"spec":[{self.spectrum_tuple[0]},{self.spectrum_tuple[1]},{self.spectrum_tuple[2]},{self.spectrum_tuple[3]}],'
            f'"top":[{candidates_str}],'
            f'"flk":{self.flaky_filtered_count}}}'
        )

    def estimate_token_count(self) -> int:
        """
        Estimates the token count based on standard BPE tokenization heuristics (~3.5-4 chars/token).
        """
        payload = self.to_compact_json()
        return math.ceil(len(payload) / 3.2)


class TriPassFilterResult(BaseModel):
    """
    Result of the Tri-Pass Voting Filter for flaky test eradication.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    retained_records: List[CoverageRecord]
    flaky_test_ids: List[str]
    total_analyzed: int
    deterministic_ratio: float = Field(ge=0.0, le=1.0)


class CoverageMatrix:
    """
    Binary Coverage Matrix A in {0, 1}^(m x n) and Outcome Vector e in {0, 1}^m.
    - m: number of test cases.
    - n: number of distinct executable statements.
    - A[i][j] = 1 if test i executed statement j, else 0.
    - e[i] = 1 if test i FAILED, 0 if test i PASSED.
    """

    def __init__(
        self,
        statements: Sequence[str],
        test_ids: Sequence[str],
        matrix: Sequence[Sequence[int]],
        outcomes: Sequence[int],
    ) -> None:
        if len(test_ids) != len(matrix) or len(test_ids) != len(outcomes):
            raise ValueError(
                f"Row mismatch: test_ids={len(test_ids)}, matrix={len(matrix)}, outcomes={len(outcomes)}"
            )
        num_cols = len(statements)
        for idx, row in enumerate(matrix):
            if len(row) != num_cols:
                raise ValueError(
                    f"Column mismatch in row {idx}: expected {num_cols}, got {len(row)}"
                )
            for val in row:
                if val not in (0, 1):
                    raise ValueError(f"Matrix elements must be binary (0 or 1), found {val}")
        for out in outcomes:
            if out not in (0, 1):
                raise ValueError(f"Outcome elements must be binary (0=PASS, 1=FAIL), found {out}")

        self._statements = list(statements)
        self._test_ids = list(test_ids)
        self._matrix = [list(r) for r in matrix]
        self._outcomes = list(outcomes)

        self._stmt_to_col: Dict[str, int] = {stmt: i for i, stmt in enumerate(self._statements)}
        self._test_to_row: Dict[str, int] = {t_id: i for i, t_id in enumerate(self._test_ids)}

    @property
    def statements(self) -> List[str]:
        return list(self._statements)

    @property
    def test_ids(self) -> List[str]:
        return list(self._test_ids)

    @property
    def num_tests(self) -> int:
        return len(self._test_ids)

    @property
    def num_statements(self) -> int:
        return len(self._statements)

    @property
    def matrix(self) -> List[List[int]]:
        return [list(r) for r in self._matrix]

    @property
    def outcomes(self) -> List[int]:
        return list(self._outcomes)

    @classmethod
    def from_records(cls, records: Sequence[CoverageRecord]) -> CoverageMatrix:
        """
        Constructs binary coverage matrix A and outcome vector e from CoverageRecords.
        """
        all_stmts_set = set()
        for rec in records:
            all_stmts_set.update(rec.executed_statements)
        statements = sorted(all_stmts_set)

        test_ids = [rec.test_id for rec in records]
        outcomes = [1 if not rec.passed else 0 for rec in records]

        stmt_to_idx = {stmt: idx for idx, stmt in enumerate(statements)}
        matrix: List[List[int]] = []

        for rec in records:
            row = [0] * len(statements)
            for stmt in rec.executed_statements:
                if stmt in stmt_to_idx:
                    row[stmt_to_idx[stmt]] = 1
            matrix.append(row)

        return cls(
            statements=statements,
            test_ids=test_ids,
            matrix=matrix,
            outcomes=outcomes,
        )

    def get_spectrum(self, statement: str) -> SpectrumCounts:
        """
        Computes (n_ef, n_ep, n_nf, n_np) for a specific statement.
        """
        if statement not in self._stmt_to_col:
            raise KeyError(f"Statement '{statement}' not found in coverage matrix")

        col_idx = self._stmt_to_col[statement]
        n_ef = 0
        n_ep = 0
        n_nf = 0
        n_np = 0

        for row_idx in range(self.num_tests):
            executed = self._matrix[row_idx][col_idx] == 1
            failed = self._outcomes[row_idx] == 1

            if executed and failed:
                n_ef += 1
            elif executed and not failed:
                n_ep += 1
            elif not executed and failed:
                n_nf += 1
            else:
                n_np += 1

        return SpectrumCounts(n_ef=n_ef, n_ep=n_ep, n_nf=n_nf, n_np=n_np)


def calculate_ochiai(spectrum: SpectrumCounts) -> float:
    """
    Computes Ochiai suspiciousness metric:
    S_Ochiai = n_ef / sqrt(n_f * (n_ef + n_ep))
    Returns 0.0 if denominator is 0.
    """
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)
    total_exec = float(spectrum.total_executed)

    denominator = math.sqrt(n_f * total_exec)
    if denominator == 0.0:
        return 0.0

    score = n_ef / denominator
    return min(1.0, max(0.0, score))


def calculate_tarantula(spectrum: SpectrumCounts) -> float:
    """
    Computes Tarantula suspiciousness metric:
    S_Tarantula = (n_ef / n_f) / ((n_ef / n_f) + (n_ep / n_p))
    Returns 0.0 if denominator is 0 or no failing tests.
    """
    n_f = float(spectrum.total_failed)
    n_p = float(spectrum.total_passed)

    if n_f == 0.0:
        return 0.0

    fail_ratio = float(spectrum.n_ef) / n_f

    if n_p == 0.0:
        return 1.0 if fail_ratio > 0.0 else 0.0

    pass_ratio = float(spectrum.n_ep) / n_p

    denominator = fail_ratio + pass_ratio
    if denominator == 0.0:
        return 0.0

    score = fail_ratio / denominator
    return min(1.0, max(0.0, score))


def calculate_dstar(spectrum: SpectrumCounts, alpha: float = 2.0) -> float:
    """
    Computes DStar (D*) suspiciousness metric:
    S_DStar = (n_ef ^ alpha) / (n_ep + n_nf)
    If (n_ep + n_nf) == 0 and n_ef > 0, returns high score sentinel (1e6 * n_ef).
    Returns 0.0 if n_ef == 0.
    """
    n_ef = float(spectrum.n_ef)
    if n_ef == 0.0:
        return 0.0

    denominator = float(spectrum.n_ep + spectrum.n_nf)
    if denominator == 0.0:
        return float(1_000_000.0 * (n_ef ** alpha))

    return (n_ef ** alpha) / denominator


def calibrate_coincidental_correctness(
    spectrum: SpectrumCounts,
    def_use_weight: float = 0.0,
    gamma: float = 0.5,
) -> float:
    """
    Calibrates Ochiai suspiciousness score to account for Coincidental Correctness:
    When a buggy statement is executed in passing tests, coincidental correctness
    artificially inflates n_ep. Using def-use data propagation factor, we discount n_ep:
    n_ep_adj = n_ep * (1.0 - gamma * def_use_weight)
    S_calibrated = n_ef / sqrt(n_f * (n_ef + n_ep_adj))
    """
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)

    # Constrain weight and gamma to [0.0, 1.0]
    weight = min(1.0, max(0.0, def_use_weight))
    g = min(1.0, max(0.0, gamma))

    discount = 1.0 - (g * weight)
    n_ep_adj = float(spectrum.n_ep) * discount

    denominator = math.sqrt(n_f * (n_ef + n_ep_adj))
    if denominator == 0.0:
        return 0.0

    score = n_ef / denominator
    return min(1.0, max(0.0, score))


def tri_pass_voting_filter(
    pass_runs: Sequence[Sequence[CoverageRecord]],
) -> TriPassFilterResult:
    """
    Tri-Pass Voting Filter for flaky test eradication (RULE: 3/3 deterministic matching).
    - Requires 3 consecutive passes of the test suite.
    - A test is retained ONLY if outcome is 3/3 unanimous (all PASS or all FAIL).
    - If outcomes fluctuate across the 3 passes, the test is classified as flaky and purged.
    """
    if len(pass_runs) < 3:
        raise ValueError(f"Tri-Pass filter requires exactly 3 run passes, got {len(pass_runs)}")

    # Index records by test_id per pass
    pass_maps: List[Dict[str, CoverageRecord]] = []
    for run in pass_runs[:3]:
        p_map = {rec.test_id: rec for rec in run}
        pass_maps.append(p_map)

    all_test_ids = sorted(
        set(pass_maps[0].keys()) & set(pass_maps[1].keys()) & set(pass_maps[2].keys())
    )

    retained_records: List[CoverageRecord] = []
    flaky_test_ids: List[str] = []

    for t_id in all_test_ids:
        r1 = pass_maps[0][t_id]
        r2 = pass_maps[1][t_id]
        r3 = pass_maps[2][t_id]

        outcomes = (r1.passed, r2.passed, r3.passed)

        if outcomes == (True, True, True):
            # Deterministic PASS: consolidate trace (union of executed statements)
            unified_stmts = sorted(
                set(r1.executed_statements) | set(r2.executed_statements) | set(r3.executed_statements)
            )
            retained_records.append(
                CoverageRecord(test_id=t_id, passed=True, executed_statements=unified_stmts)
            )
        elif outcomes == (False, False, False):
            # Deterministic FAIL: consolidate trace
            unified_stmts = sorted(
                set(r1.executed_statements) | set(r2.executed_statements) | set(r3.executed_statements)
            )
            retained_records.append(
                CoverageRecord(test_id=t_id, passed=False, executed_statements=unified_stmts)
            )
        else:
            # Flaky test detected: discordant outcomes across 3 runs
            flaky_test_ids.append(t_id)

    total = len(all_test_ids)
    det_ratio = float(len(retained_records)) / float(total) if total > 0 else 1.0

    return TriPassFilterResult(
        retained_records=retained_records,
        flaky_test_ids=flaky_test_ids,
        total_analyzed=total,
        deterministic_ratio=det_ratio,
    )


class SBFLEngine:
    """
    Orchestrator for Spectrum-Based Fault Localization diagnostics.
    """

    def __init__(self, alpha: float = 2.0, cc_gamma: float = 0.5) -> None:
        self.alpha = alpha
        self.cc_gamma = cc_gamma

    def analyze(
        self,
        matrix: CoverageMatrix,
        def_use_weights: Optional[Dict[str, float]] = None,
    ) -> List[SBFLScore]:
        """
        Computes Ochiai, Tarantula, DStar and Calibrated Ochiai for all statements in the matrix.
        Returns ranked list of SBFLScore (descending by Ochiai / Calibrated Ochiai).
        """
        weights = def_use_weights or {}
        scores: List[SBFLScore] = []

        for stmt in matrix.statements:
            spectrum = matrix.get_spectrum(stmt)
            och = calculate_ochiai(spectrum)
            tar = calculate_tarantula(spectrum)
            dst = calculate_dstar(spectrum, alpha=self.alpha)

            du_weight = weights.get(stmt, 0.0)
            cal_och = calibrate_coincidental_correctness(
                spectrum=spectrum,
                def_use_weight=du_weight,
                gamma=self.cc_gamma,
            )

            scores.append(
                SBFLScore(
                    statement=stmt,
                    ochiai=round(och, 6),
                    tarantula=round(tar, 6),
                    dstar=round(dst, 6),
                    calibrated_ochiai=round(cal_och, 6),
                    spectrum=spectrum,
                    rank=1,
                )
            )

        # Sort descending by calibrated Ochiai, then Ochiai, then DStar
        scores.sort(
            key=lambda x: (x.calibrated_ochiai, x.ochiai, x.dstar),
            reverse=True,
        )

        # Assign 1-indexed ranks
        ranked_scores: List[SBFLScore] = []
        for rank_idx, s in enumerate(scores, start=1):
            ranked_scores.append(
                SBFLScore(
                    statement=s.statement,
                    ochiai=s.ochiai,
                    tarantula=s.tarantula,
                    dstar=s.dstar,
                    calibrated_ochiai=s.calibrated_ochiai,
                    spectrum=s.spectrum,
                    rank=rank_idx,
                )
            )

        return ranked_scores

    def generate_diagnostic_payload(
        self,
        ranked_scores: Sequence[SBFLScore],
        flaky_filtered_count: int = 0,
        top_k: int = 3,
    ) -> OchiaiDiagnosticPayload:
        """
        Generates ultra-compact diagnostic payload guaranteed to fit under 80 tokens.
        """
        if not ranked_scores:
            return OchiaiDiagnosticPayload(
                top_fault="NONE:0",
                ochiai_score=0.0,
                spectrum_tuple=(0, 0, 0, 0),
                top_candidates=[],
                flaky_filtered_count=flaky_filtered_count,
            )

        top_item = ranked_scores[0]
        spec = top_item.spectrum
        spec_tuple = (spec.n_ef, spec.n_ep, spec.n_nf, spec.n_np)

        top_k_items = ranked_scores[:top_k]
        candidates = [(item.statement, item.ochiai) for item in top_k_items]

        payload = OchiaiDiagnosticPayload(
            top_fault=top_item.statement,
            ochiai_score=top_item.ochiai,
            spectrum_tuple=spec_tuple,
            top_candidates=candidates,
            flaky_filtered_count=flaky_filtered_count,
        )

        # Safety check for token limit (<80 tokens)
        estimated_tokens = payload.estimate_token_count()
        if estimated_tokens > 80:
            # Prune candidates to top 1 if token budget is tight
            payload = OchiaiDiagnosticPayload(
                top_fault=top_item.statement,
                ochiai_score=top_item.ochiai,
                spectrum_tuple=spec_tuple,
                top_candidates=[(top_item.statement, top_item.ochiai)],
                flaky_filtered_count=flaky_filtered_count,
            )

        return payload

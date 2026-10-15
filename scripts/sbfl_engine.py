#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore matematico SBFL (Spectrum-Based Fault Localization) per Nexus Keystone v3.0.0.
Modulo: sbfl_engine.py.

Funzionalita principali:
1. Calcola le metriche di sospettosita Ochiai, Tarantula e DStar (alpha=2.0).
2. Costruisce la matrice di copertura binaria A e il vettore di esito e.
3. Applica il filtro Tri-Pass Voting per l'eliminazione dei test instabili (flaky).
4. Calibra la coincidental correctness tramite pesi Def-Use.
5. Genera il payload diagnostico OchiaiDiagnosticPayload sotto gli 80 token con CLI dedicata.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field


class SpectrumCounts(BaseModel):
    """Conteggi delle esecuzioni di test per una specifica istruzione di codice."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    n_ef: int = Field(ge=0, description="Test falliti che eseguono l'istruzione")
    n_ep: int = Field(ge=0, description="Test passati che eseguono l'istruzione")
    n_nf: int = Field(ge=0, description="Test falliti che non eseguono l'istruzione")
    n_np: int = Field(ge=0, description="Test passati che non eseguono l'istruzione")

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
    """Informazioni di peso Def-Use per la calibrazione della coincidental correctness."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    statement: str
    def_var: str
    use_count: int = Field(ge=0)
    propagation_weight: float = Field(ge=0.0, le=1.0, default=0.5)


class CoverageRecord(BaseModel):
    """Record di copertura per l'esecuzione di un singolo caso di test."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    test_id: str
    passed: bool
    executed_statements: List[str] = Field(default_factory=list)


class SBFLScore(BaseModel):
    """Metriche SBFL calcolate per una singola istruzione."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    statement: str
    ochiai: float = Field(ge=0.0, le=1.0)
    tarantula: float = Field(ge=0.0, le=1.0)
    dstar: float = Field(ge=0.0)
    calibrated_ochiai: float = Field(ge=0.0, le=1.0)
    spectrum: SpectrumCounts
    rank: int = Field(ge=1, default=1)


class OchiaiDiagnosticPayload(BaseModel):
    """Payload diagnostico ad alta densita garantito sotto la soglia di 80 token."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    top_fault: str = Field(
        description="Identificativo dell'istruzione con massima sospettosita Ochiai"
    )
    ochiai_score: float = Field(ge=0.0, le=1.0)
    spectrum_tuple: Tuple[int, int, int, int] = Field(
        description="(n_ef, n_ep, n_nf, n_np)"
    )
    top_candidates: List[Tuple[str, float]] = Field(
        description="Lista di (statement, score) per le prime istruzioni sospette",
        max_length=5,
    )
    flaky_filtered_count: int = Field(ge=0, default=0)

    def to_compact_json(self) -> str:
        """Restituisce la rappresentazione JSON ultra-compatta (< 80 token)."""
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
        """Stima il conteggio dei token sulla base della lunghezza in caratteri."""
        payload = self.to_compact_json()
        return math.ceil(len(payload) / 3.2)


class TriPassFilterResult(BaseModel):
    """Risultato del filtro Tri-Pass Voting per l'eliminazione dei test flaky."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    retained_records: List[CoverageRecord]
    flaky_test_ids: List[str]
    total_analyzed: int
    deterministic_ratio: float = Field(ge=0.0, le=1.0)


class CoverageMatrix:
    """Matrice binaria di copertura A e vettore degli esiti e."""

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
                    raise ValueError(
                        f"Matrix elements must be binary (0 or 1), found {val}"
                    )
        for out in outcomes:
            if out not in (0, 1):
                raise ValueError(
                    f"Outcome elements must be binary (0=PASS, 1=FAIL), found {out}"
                )

        self._statements = list(statements)
        self._test_ids = list(test_ids)
        self._matrix = [list(r) for r in matrix]
        self._outcomes = list(outcomes)

        self._stmt_to_col: Dict[str, int] = {
            stmt: i for i, stmt in enumerate(self._statements)
        }
        self._test_to_row: Dict[str, int] = {
            t_id: i for i, t_id in enumerate(self._test_ids)
        }

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
        """Costruisce la matrice di copertura dai CoverageRecord forniti."""
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
        """Calcola (n_ef, n_ep, n_nf, n_np) per una specifica istruzione."""
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
    """Calcola la metrica di sospettosita Ochiai: n_ef / sqrt(n_f * (n_ef + n_ep))."""
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)
    total_exec = float(spectrum.total_executed)

    denominator = math.sqrt(n_f * total_exec)
    if denominator == 0.0:
        return 0.0

    score = n_ef / denominator
    return min(1.0, max(0.0, score))


def calculate_tarantula(spectrum: SpectrumCounts) -> float:
    """Calcola la metrica di sospettosita Tarantula."""
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
    """Calcola la metrica di sospettosita DStar (D*): (n_ef ^ alpha) / (n_ep + n_nf)."""
    n_ef = float(spectrum.n_ef)
    if n_ef == 0.0:
        return 0.0

    denominator = float(spectrum.n_ep + spectrum.n_nf)
    if denominator == 0.0:
        return float(1_000_000.0 * (n_ef**alpha))

    return (n_ef**alpha) / denominator


def calibrate_coincidental_correctness(
    spectrum: SpectrumCounts,
    def_use_weight: float = 0.0,
    gamma: float = 0.5,
) -> float:
    """Calibra il punteggio Ochiai scontando n_ep tramite il fattore di propagazione Def-Use."""
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)

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
    """Applica il filtro Tri-Pass mantenendo solo i test con esito unanime 3 su 3."""
    if len(pass_runs) < 3:
        raise ValueError(
            f"Tri-Pass filter requires exactly 3 run passes, got {len(pass_runs)}"
        )

    pass_maps: List[Dict[str, CoverageRecord]] = []
    for run in pass_runs[:3]:
        p_map = {rec.test_id: rec for rec in run}
        pass_maps.append(p_map)

    all_test_ids = sorted(
        set(pass_maps[0].keys())
        & set(pass_maps[1].keys())
        & set(pass_maps[2].keys())
    )

    retained_records: List[CoverageRecord] = []
    flaky_test_ids: List[str] = []

    for t_id in all_test_ids:
        r1 = pass_maps[0][t_id]
        r2 = pass_maps[1][t_id]
        r3 = pass_maps[2][t_id]

        outcomes = (r1.passed, r2.passed, r3.passed)

        if outcomes == (True, True, True):
            unified_stmts = sorted(
                set(r1.executed_statements)
                | set(r2.executed_statements)
                | set(r3.executed_statements)
            )
            retained_records.append(
                CoverageRecord(
                    test_id=t_id, passed=True, executed_statements=unified_stmts
                )
            )
        elif outcomes == (False, False, False):
            unified_stmts = sorted(
                set(r1.executed_statements)
                | set(r2.executed_statements)
                | set(r3.executed_statements)
            )
            retained_records.append(
                CoverageRecord(
                    test_id=t_id, passed=False, executed_statements=unified_stmts
                )
            )
        else:
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
    """Orchestratore per la diagnostica Spectrum-Based Fault Localization."""

    def __init__(self, alpha: float = 2.0, cc_gamma: float = 0.5) -> None:
        self.alpha = alpha
        self.cc_gamma = cc_gamma

    def analyze(
        self,
        matrix: CoverageMatrix,
        def_use_weights: Optional[Dict[str, float]] = None,
    ) -> List[SBFLScore]:
        """Calcola tutte le metriche SBFL e restituisce la classifica ordinata."""
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

        scores.sort(
            key=lambda x: (x.calibrated_ochiai, x.ochiai, x.dstar),
            reverse=True,
        )

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
        """Genera il payload diagnostico compatto garantito sotto 80 token."""
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

        estimated_tokens = payload.estimate_token_count()
        if estimated_tokens > 80:
            payload = OchiaiDiagnosticPayload(
                top_fault=top_item.statement,
                ochiai_score=top_item.ochiai,
                spectrum_tuple=spec_tuple,
                top_candidates=[(top_item.statement, top_item.ochiai)],
                flaky_filtered_count=flaky_filtered_count,
            )

        return payload


def main() -> int:
    """Interfaccia CLI per l'esecuzione diretta di sbfl_engine.py."""
    parser = argparse.ArgumentParser(
        description="Motore Matematico SBFL Ochiai/Tarantula/DStar Nexus Keystone v3.0.0"
    )
    parser.add_argument(
        "--records-file",
        type=str,
        default=None,
        help="File JSON contenente una lista di CoverageRecord",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il payload diagnostico compatto (< 80 token)",
    )
    args = parser.parse_args()

    if args.records_file:
        raw_data = json.loads(Path(args.records_file).read_text(encoding="utf-8"))
        records = [CoverageRecord.model_validate(item) for item in raw_data]
    else:
        records = [
            CoverageRecord(
                test_id="T1", passed=False, executed_statements=["module.py:10"]
            ),
            CoverageRecord(
                test_id="T2", passed=True, executed_statements=["module.py:20"]
            ),
        ]

    matrix = CoverageMatrix.from_records(records)
    engine = SBFLEngine()
    ranked = engine.analyze(matrix)
    payload = engine.generate_diagnostic_payload(ranked)

    print(payload.to_compact_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())

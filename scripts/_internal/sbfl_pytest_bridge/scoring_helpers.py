"""Modelli spettro/Tri-Pass e metriche matematiche Ochiai, Tarantula e DStar per SBFL."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field


def compute_ochiai(n_ef: int, n_ep: int, total_failed: int, total_passed: int = 0) -> float:
    """Calcola il coefficiente Ochiai limitando n_ef a total_failed."""
    _ = total_passed
    if total_failed <= 0:
        return 0.0
    n_ef = min(max(0, n_ef), total_failed)
    n_ep = max(0, n_ep)
    denom = math.sqrt(total_failed * (n_ef + n_ep))
    return round(n_ef / denom, 6) if denom > 0.0 else 0.0


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


class CoverageRecord(BaseModel):
    """Record di copertura per l'esecuzione di un singolo caso di test."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    test_id: str
    passed: bool
    executed_statements: List[str] = Field(default_factory=list)


class TriPassFilterResult(BaseModel):
    """Risultato del filtro Tri-Pass Voting per l'eliminazione dei test flaky."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    retained_records: List[CoverageRecord]
    flaky_test_ids: List[str]
    total_analyzed: int
    deterministic_ratio: float = Field(ge=0.0, le=1.0)


def calculate_ochiai(spectrum: SpectrumCounts) -> float:
    """Calcola la metrica di sospettosita Ochiai: n_ef / sqrt(n_f * (n_ef + n_ep))."""
    n_ef = float(spectrum.n_ef)
    denominator = math.sqrt(float(spectrum.total_failed) * float(spectrum.total_executed))
    if denominator == 0.0:
        return 0.0
    return min(1.0, max(0.0, n_ef / denominator))


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
    return min(1.0, max(0.0, fail_ratio / denominator))


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
    spectrum: SpectrumCounts, def_use_weight: float = 0.0, gamma: float = 0.5
) -> float:
    """Calibra il punteggio Ochiai scontando n_ep tramite il fattore di propagazione Def-Use."""
    n_ef = float(spectrum.n_ef)
    n_f = float(spectrum.total_failed)
    weight = min(1.0, max(0.0, def_use_weight))
    g = min(1.0, max(0.0, gamma))
    n_ep_adj = float(spectrum.n_ep) * (1.0 - (g * weight))
    denominator = math.sqrt(n_f * (n_ef + n_ep_adj))
    if denominator == 0.0:
        return 0.0
    return min(1.0, max(0.0, n_ef / denominator))


def tri_pass_voting_filter(pass_runs: Sequence[Sequence[CoverageRecord]]) -> TriPassFilterResult:
    """Applica il filtro Tri-Pass mantenendo solo i test con esito unanime 3 su 3."""
    if len(pass_runs) < 3:
        raise ValueError(f"Tri-Pass filter requires exactly 3 run passes, got {len(pass_runs)}")
    pass_maps: List[Dict[str, CoverageRecord]] = [{rec.test_id: rec for rec in run} for run in pass_runs[:3]]
    all_test_ids = sorted(set(pass_maps[0]) & set(pass_maps[1]) & set(pass_maps[2]))
    retained_records: List[CoverageRecord] = []
    flaky_test_ids: List[str] = []
    for t_id in all_test_ids:
        r1, r2, r3 = pass_maps[0][t_id], pass_maps[1][t_id], pass_maps[2][t_id]
        if (r1.passed, r2.passed, r3.passed) in ((True, True, True), (False, False, False)):
            unified_stmts = sorted(set(r1.executed_statements) | set(r2.executed_statements) | set(r3.executed_statements))
            retained_records.append(CoverageRecord(test_id=t_id, passed=r1.passed, executed_statements=unified_stmts))
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


def split_stmt(stmt: str) -> Tuple[str, int]:
    """Separa 'percorso:riga' in (percorso, numero_riga)."""
    if ":" not in stmt:
        return stmt, 1
    fpath, lno_str = stmt.rsplit(":", 1)
    try:
        return fpath, max(1, int(lno_str))
    except ValueError:
        return stmt, 1


def stmt_matches_hint(stmt: str, norm_hint: Optional[str]) -> bool:
    """Verifica se uno statement appartiene al file target o esclude file di test."""
    fpath, _ = split_stmt(stmt)
    fname = Path(fpath).name
    if norm_hint:
        return os.path.normcase(fname) == os.path.normcase(norm_hint)
    low = fname.lower()
    return low != "conftest.py" and not low.startswith("test_") and not low.endswith("_test.py")


def build_fallback_coverage_records(
    stmt: str,
    total_failed: int,
    n_ef: int,
    total_passed: int,
    n_ep: int,
) -> List[CoverageRecord]:
    """Costruisce CoverageRecord coerenti con lo spettro osservato per CoverageMatrix."""
    records: List[CoverageRecord] = []
    eff_total_failed = max(1, total_failed)
    eff_ef = min(max(0, n_ef), eff_total_failed)
    eff_nf = max(0, eff_total_failed - eff_ef)
    eff_ep = max(0, n_ep)
    eff_np = max(0, max(total_passed, eff_ep) - eff_ep)
    for idx in range(eff_ef):
        records.append(CoverageRecord(test_id=f"F_exec_{idx}", passed=False, executed_statements=[stmt]))
    for idx in range(eff_nf):
        records.append(CoverageRecord(test_id=f"F_miss_{idx}", passed=False, executed_statements=[]))
    for idx in range(eff_ep):
        records.append(CoverageRecord(test_id=f"P_exec_{idx}", passed=True, executed_statements=[stmt]))
    for idx in range(eff_np):
        records.append(CoverageRecord(test_id=f"P_miss_{idx}", passed=True, executed_statements=[]))
    return records

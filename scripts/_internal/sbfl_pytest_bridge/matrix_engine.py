"""Matrice di copertura binaria e motore SBFLEngine unificato in sbfl_pytest_bridge."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from _internal.sbfl_pytest_bridge import _ensure_staging_pkg

_ensure_staging_pkg(Path(__file__).resolve().parent)

from _internal.sbfl_pytest_bridge.models import (
    SBFL_MAX_TOKEN_BUDGET,
    CoverageRecord,
    SBFLLocation,
    SBFLScore,
    SpectrumCounts,
    calculate_dstar,
    calculate_ochiai,
    calculate_tarantula,
    calibrate_coincidental_correctness,
)
from _internal.sbfl_pytest_bridge.scoring_helpers import (
    split_stmt,
    stmt_matches_hint,
)

try:
    from schemas.nk_ipc_contracts import OchiaiDiagnosticPayload
except ImportError:
    from scripts.schemas.nk_ipc_contracts import OchiaiDiagnosticPayload


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
        if estimated_tokens > SBFL_MAX_TOKEN_BUDGET:
            payload = OchiaiDiagnosticPayload(
                top_fault=top_item.statement,
                ochiai_score=top_item.ochiai,
                spectrum_tuple=spec_tuple,
                top_candidates=[(top_item.statement, top_item.ochiai)],
                flaky_filtered_count=flaky_filtered_count,
            )

        return payload

    @staticmethod
    def extract_from_exception(
        exc: BaseException, relevant_file_hint: Optional[str] = None
    ) -> SBFLLocation:
        """Estrae la localizzazione del guasto Ochiai a partire da una eccezione Python."""
        tb = exc.__traceback__
        frames = traceback.extract_tb(tb)
        spectrum = SpectrumCounts(n_ef=1, n_ep=0, n_nf=0, n_np=0)
        ochiai_score = calculate_ochiai(spectrum)
        tar_score = calculate_tarantula(spectrum)
        dst_score = calculate_dstar(spectrum)

        if not frames:
            return SBFLLocation(
                file_path="unknown",
                line_number=1,
                suspiciousness=ochiai_score,
                error_type=type(exc).__name__,
                error_message=str(exc),
                failing_line_content="",
                tarantula=tar_score,
                dstar=dst_score,
            )

        target_frame = frames[-1]
        if relevant_file_hint:
            for f in reversed(frames):
                if relevant_file_hint in f.filename:
                    target_frame = f
                    break

        line_no = target_frame.lineno or 1
        line_code = target_frame.line or ""

        return SBFLLocation(
            file_path=target_frame.filename,
            line_number=line_no,
            suspiciousness=ochiai_score,
            error_type=type(exc).__name__,
            error_message=str(exc),
            failing_line_content=line_code,
            tarantula=tar_score,
            dstar=dst_score,
        )


def _score_matches_pref(score: SBFLScore, pref_file: str, pref_line: int) -> bool:
    """Confronta uno SBFLScore con un frame di traceback normalizzato Win32."""
    s_file, s_line = split_stmt(score.statement)
    if s_line != pref_line:
        return False
    return (
        s_file.replace("\\", "/").lower() == pref_file.replace("\\", "/").lower()
        or Path(s_file).name.lower() == Path(pref_file).name.lower()
    )


def _pick_top_score_with_traceback(
    ranked: Sequence[SBFLScore], preferred_locations: Sequence[Tuple[str, int]]
) -> SBFLScore:
    """Seleziona il top SBFLScore preferendo il frame traceback in caso di parita."""
    top = ranked[0]
    top_key = (top.calibrated_ochiai, top.ochiai, top.dstar)
    tied = [s for s in ranked if (s.calibrated_ochiai, s.ochiai, s.dstar) == top_key]
    if len(tied) <= 1 or not preferred_locations:
        return top
    for pref_file, pref_line in preferred_locations:
        for cand in tied:
            if _score_matches_pref(cand, pref_file, pref_line):
                return cand
    return top


def rank_bridge_coverage(
    records: Sequence[CoverageRecord],
    norm_hint: Optional[str] = None,
    preferred_locations: Optional[Sequence[Tuple[str, int]]] = None,
) -> Tuple[Optional[SBFLScore], List[SBFLScore], OchiaiDiagnosticPayload]:
    """Costruisce CoverageMatrix e classifica con SBFLEngine scegliendo il guasto top."""
    filtered = [
        CoverageRecord(
            test_id=rec.test_id,
            passed=rec.passed,
            executed_statements=[
                stmt for stmt in rec.executed_statements if stmt_matches_hint(stmt, norm_hint)
            ],
        )
        for rec in records
    ]
    matrix = CoverageMatrix.from_records(filtered)
    engine = SBFLEngine()
    if matrix.num_statements == 0:
        return None, [], engine.generate_diagnostic_payload([])
    ranked = engine.analyze(matrix)
    payload = engine.generate_diagnostic_payload(ranked)
    best = _pick_top_score_with_traceback(ranked, preferred_locations or ())
    return best, ranked, payload

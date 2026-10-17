# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per SBFL Fault Localization Engine (v3.3.0).
Modulo: tests/test_sbfl_engine.py.
Valida Ochiai, Tarantula, DStar, coincidental correctness, filtro tri-pass e token cap.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from sbfl_engine import (
    CoverageMatrix,
    CoverageRecord,
    OchiaiDiagnosticPayload,
    SpectrumCounts,
    calculate_dstar,
    calculate_ochiai,
    calculate_tarantula,
    calibrate_coincidental_correctness,
    tri_pass_voting_filter,
)


class TestSBFLEngine(unittest.TestCase):
    def setUp(self):
        self.records = [
            CoverageRecord(
                test_id="T1", passed=False, executed_statements=["s1", "s2"]
            ),
            CoverageRecord(test_id="T2", passed=False, executed_statements=["s1"]),
            CoverageRecord(test_id="T3", passed=True, executed_statements=["s1", "s3"]),
            CoverageRecord(test_id="T4", passed=True, executed_statements=["s2", "s3"]),
            CoverageRecord(test_id="T5", passed=True, executed_statements=["s3"]),
        ]
        self.matrix = CoverageMatrix.from_records(self.records)

    def test_ochiai_mathematical_precision(self):
        """1. Valida la precisione matematica di Ochiai, Tarantula e DStar."""
        spec_s1 = self.matrix.get_spectrum("s1")
        self.assertAlmostEqual(
            calculate_ochiai(spec_s1), 2.0 / math.sqrt(6.0), places=6
        )
        self.assertAlmostEqual(calculate_tarantula(spec_s1), 0.75, places=6)
        self.assertAlmostEqual(calculate_dstar(spec_s1, alpha=2.0), 4.0, places=6)

        spec_s3 = self.matrix.get_spectrum("s3")
        self.assertEqual(calculate_ochiai(spec_s3), 0.0)

    def test_coincidental_correctness_def_use(self):
        """2. Valida la calibrazione Def-Use e le dimensioni della CoverageMatrix."""
        spec = SpectrumCounts(n_ef=2, n_ep=1, n_nf=0, n_np=2)
        base = calculate_ochiai(spec)
        calibrated = calibrate_coincidental_correctness(
            spec, def_use_weight=0.8, gamma=0.7
        )
        self.assertGreater(calibrated, base)
        self.assertEqual(self.matrix.num_tests, 5)
        self.assertEqual(self.matrix.num_statements, 3)
        self.assertEqual(self.matrix.outcomes, [1, 1, 0, 0, 0])

    def test_tri_pass_filter_flaky_removal(self):
        """3. Valida che il filtro tri-pass elimini le tracce di test instabili."""
        p1 = [
            CoverageRecord(test_id="T_STABLE", passed=True, executed_statements=["s1"]),
            CoverageRecord(test_id="T_FLAKY", passed=True, executed_statements=["s2"]),
        ]
        p2 = [
            CoverageRecord(test_id="T_STABLE", passed=True, executed_statements=["s1"]),
            CoverageRecord(test_id="T_FLAKY", passed=False, executed_statements=["s2"]),
        ]
        p3 = [
            CoverageRecord(test_id="T_STABLE", passed=True, executed_statements=["s1"]),
            CoverageRecord(test_id="T_FLAKY", passed=True, executed_statements=["s2"]),
        ]
        res = tri_pass_voting_filter([p1, p2, p3])
        self.assertEqual(len(res.retained_records), 1)
        self.assertEqual(res.retained_records[0].test_id, "T_STABLE")
        self.assertIn("T_FLAKY", res.flaky_test_ids)

    def test_ochiai_diagnostic_payload_token_cap(self):
        """4. Valida il payload diagnostico compatto sotto gli 80 token."""
        payload = OchiaiDiagnosticPayload(
            top_fault="core/engine.py:142",
            ochiai_score=0.9487,
            spectrum_tuple=(12, 1, 0, 85),
            top_candidates=[("core/engine.py:142", 0.9487)],
            flaky_filtered_count=0,
        )
        self.assertLess(payload.estimate_token_count(), 80)


if __name__ == "__main__":
    unittest.main()

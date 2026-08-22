# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 3: SBFL Fault Localization Engine
7 Tests: Ochiai, Tarantula, DStar, Def-Use Discount, Tri-Pass Filter, Token Cap, Coverage Matrix.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from sbfl_engine import (
    CoverageMatrix,
    CoverageRecord,
    OchiaiDiagnosticPayload,
    SBFLEngine,
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
            CoverageRecord(test_id="T1", passed=False, executed_statements=["s1", "s2"]),
            CoverageRecord(test_id="T2", passed=False, executed_statements=["s1"]),
            CoverageRecord(test_id="T3", passed=True, executed_statements=["s1", "s3"]),
            CoverageRecord(test_id="T4", passed=True, executed_statements=["s2", "s3"]),
            CoverageRecord(test_id="T5", passed=True, executed_statements=["s3"]),
        ]
        self.matrix = CoverageMatrix.from_records(self.records)

    # 15. test_ochiai_mathematical_precision
    def test_ochiai_mathematical_precision(self):
        """15. Validates Ochiai formula precision: nef / sqrt(nf * (nef + nep))."""
        spec_s1 = self.matrix.get_spectrum("s1")
        och_s1 = calculate_ochiai(spec_s1)
        expected_s1 = 2.0 / math.sqrt(6.0)
        self.assertAlmostEqual(och_s1, expected_s1, places=6)

        spec_s3 = self.matrix.get_spectrum("s3")
        self.assertEqual(calculate_ochiai(spec_s3), 0.0)

    # 16. test_tarantula_calculation_precision
    def test_tarantula_calculation_precision(self):
        """16. Validates Tarantula formula precision with zero division safeguards."""
        spec_s1 = self.matrix.get_spectrum("s1")
        tar_s1 = calculate_tarantula(spec_s1)
        self.assertAlmostEqual(tar_s1, 0.75, places=6)

    # 17. test_dstar_alpha_scaling
    def test_dstar_alpha_scaling(self):
        """17. Validates DStar formula with alpha=2.0."""
        spec_s1 = self.matrix.get_spectrum("s1")
        dst_s1 = calculate_dstar(spec_s1, alpha=2.0)
        self.assertAlmostEqual(dst_s1, 4.0, places=6)

    # 18. test_coincidental_correctness_def_use
    def test_coincidental_correctness_def_use(self):
        """18. Validates Def-Use coincidental correctness calibration."""
        spec = SpectrumCounts(n_ef=2, n_ep=1, n_nf=0, n_np=2)
        base = calculate_ochiai(spec)
        calibrated = calibrate_coincidental_correctness(spec, def_use_weight=0.8, gamma=0.7)
        self.assertGreater(calibrated, base)

    # 19. test_tri_pass_filter_flaky_removal
    def test_tri_pass_filter_flaky_removal(self):
        """19. Validates tri-pass voting filter eliminates flaky test traces."""
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

    # 20. test_ochiai_diagnostic_payload_token_cap
    def test_ochiai_diagnostic_payload_token_cap(self):
        """20. Validates compact diagnostic payload strictly < 80 tokens."""
        payload = OchiaiDiagnosticPayload(
            top_fault="core/engine.py:142",
            ochiai_score=0.9487,
            spectrum_tuple=(12, 1, 0, 85),
            top_candidates=[("core/engine.py:142", 0.9487)],
            flaky_filtered_count=0,
        )
        self.assertLess(payload.estimate_token_count(), 80)

    # 21. test_coverage_matrix_builder_from_traces
    def test_coverage_matrix_builder_from_traces(self):
        """21. Validates coverage matrix dimensions and outcome vector."""
        self.assertEqual(self.matrix.num_tests, 5)
        self.assertEqual(self.matrix.num_statements, 3)
        self.assertEqual(self.matrix.outcomes, [1, 1, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per SBFL Fault Localization Engine (v6.4.0-Carbon).
Modulo: tests/test_sbfl_engine.py.
Valida Ochiai, Tarantula, DStar, tie-break, matrici vuote e bridge CLI Pytest-SBFL.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import unittest

import pytest

try:
    from conftest import call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import call_script_main_captured, load_nk_script_module

pytestmark = pytest.mark.fast

sbfl_mod = load_nk_script_module("sbfl_engine")
bridge_mod = load_nk_script_module("sbfl_pytest_bridge")

CoverageMatrix = sbfl_mod.CoverageMatrix
CoverageRecord = sbfl_mod.CoverageRecord
OchiaiDiagnosticPayload = sbfl_mod.OchiaiDiagnosticPayload
SBFLEngine = sbfl_mod.SBFLEngine
SBFLLocation = sbfl_mod.SBFLLocation
SpectrumCounts = sbfl_mod.SpectrumCounts
calculate_dstar = sbfl_mod.calculate_dstar
calculate_ochiai = sbfl_mod.calculate_ochiai
calculate_tarantula = sbfl_mod.calculate_tarantula
calibrate_coincidental_correctness = sbfl_mod.calibrate_coincidental_correctness
tri_pass_voting_filter = sbfl_mod.tri_pass_voting_filter


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


def test_sbfl_metrics_zero_edge_cases_and_matrix_validation() -> None:
    """5. Verifica casi limite zero su Ochiai/Tarantula/DStar ed errori CoverageMatrix."""
    assert sbfl_mod.estimate_token_count("") == 0
    zero_fail = SpectrumCounts(n_ef=0, n_ep=2, n_nf=0, n_np=1)
    assert calculate_tarantula(zero_fail) == 0.0
    assert calculate_dstar(zero_fail) == 0.0
    assert calibrate_coincidental_correctness(zero_fail) == 0.0

    only_fail = SpectrumCounts(n_ef=2, n_ep=0, n_nf=0, n_np=0)
    assert calculate_tarantula(only_fail) == 1.0
    assert calculate_dstar(only_fail, alpha=2.0) == 4_000_000.0
    assert calculate_tarantula(SpectrumCounts(n_ef=0, n_ep=0, n_nf=1, n_np=1)) == 0.0
    assert calculate_tarantula(SpectrumCounts(n_ef=0, n_ep=0, n_nf=1, n_np=0)) == 0.0

    with pytest.raises(ValueError, match="Row mismatch"):
        CoverageMatrix(["s1"], ["T1"], [[1], [0]], [1])
    with pytest.raises(ValueError, match="Column mismatch"):
        CoverageMatrix(["s1", "s2"], ["T1"], [[1]], [1])
    with pytest.raises(ValueError, match="binary"):
        CoverageMatrix(["s1"], ["T1"], [[2]], [1])
    with pytest.raises(ValueError, match="Outcome"):
        CoverageMatrix(["s1"], ["T1"], [[1]], [2])

    empty_m = CoverageMatrix.from_records([])
    assert empty_m.statements == []
    assert empty_m.matrix == []
    with pytest.raises(KeyError):
        empty_m.get_spectrum("missing:1")


def test_sbfl_empty_matrix_tie_break_tri_pass_and_cli(tmp_path: Path) -> None:
    """6. Verifica matrice vuota, tie-break Def-Use, tri-pass failure/empty e CLI."""
    engine = SBFLEngine()
    empty_payload = engine.generate_diagnostic_payload([])
    assert empty_payload.top_fault == "NONE:0"
    assert empty_payload.ochiai_score == 0.0

    recs = [
        CoverageRecord(test_id="F1", passed=False, executed_statements=["a:1", "b:2"]),
        CoverageRecord(test_id="P1", passed=True, executed_statements=["a:1", "b:2"]),
    ]
    mat = CoverageMatrix.from_records(recs)
    ranked = engine.analyze(mat, def_use_weights={"b:2": 0.9, "a:1": 0.0})
    assert ranked[0].statement == "b:2"
    assert ranked[0].rank == 1 and ranked[1].rank == 2

    long_ranked = [
        sbfl_mod.SBFLScore(
            statement=f"very_long_module_name_segment_{i}.py:{100 + i}",
            ochiai=0.9,
            tarantula=0.9,
            dstar=4.0,
            calibrated_ochiai=0.9,
            spectrum=SpectrumCounts(n_ef=1, n_ep=0, n_nf=0, n_np=0),
            rank=i + 1,
        )
        for i in range(6)
    ]
    from pydantic import ValidationError

    trimmed_payload = engine.generate_diagnostic_payload(long_ranked, top_k=5)
    assert len(trimmed_payload.top_candidates) == 1
    with pytest.raises(ValidationError):
        engine.generate_diagnostic_payload(long_ranked, top_k=6)

    with pytest.raises(ValueError, match="3 run passes"):
        tri_pass_voting_filter([[]])
    fail_rec = [CoverageRecord(test_id="F_UNAN", passed=False, executed_statements=["x:9"])]
    tri_fail = tri_pass_voting_filter([fail_rec, fail_rec, fail_rec])
    assert len(tri_fail.retained_records) == 1 and tri_fail.retained_records[0].passed is False
    assert tri_pass_voting_filter([[], [], []]).deterministic_ratio == 1.0

    loc_long = SBFLLocation(
        file_path="sub/very_long_filename_beyond_thirty_chars.py",
        line_number=42,
        suspiciousness=0.95,
        error_type="CustomFailureTypeWithVeryLongName",
        error_message="E" * 120,
        failing_line_content="X" * 120,
    )
    assert len(loc_long.render_payload_json()) < 320
    unraised = SBFLEngine.extract_from_exception(RuntimeError("boom"))
    assert unraised.file_path == "unknown" and unraised.line_number == 1

    rec_file = tmp_path / "records.json"
    rec_file.write_text(
        json.dumps([{"test_id": "T1", "passed": False, "executed_statements": ["m.py:7"]}]),
        encoding="utf-8",
    )
    rc_def, out_def, _ = call_script_main_captured(sbfl_mod, ["--json"])
    assert rc_def == 0 and "module.py:10" in out_def
    rc_rf, out_rf, _ = call_script_main_captured(sbfl_mod, ["--records-file", str(rec_file), "--json"])
    assert rc_rf == 0 and "m.py:7" in out_rf


def test_sbfl_pytest_bridge_edge_branches_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """7. Verifica compute_ochiai, parse fallback, n_ep con passed_line_counts e CLI bridge."""
    assert bridge_mod.compute_ochiai(1, 0, 0) == 0.0
    assert bridge_mod.compute_ochiai(5, 2, 2) == round(2.0 / math.sqrt(8.0), 6)
    assert bridge_mod.compute_ochiai(0, 0, 2) == 0.0

    bridge = bridge_mod.SBFLPytestBridge(cwd=tmp_path)
    src_file = tmp_path / "app_mod.py"
    src_file.write_text("x = 1\ny = 1 / 0\n", encoding="utf-8")

    summary_pass = bridge.parse_pytest_output("2 passed in 0.01s", "", exit_code=0, duration_sec=0.01)
    assert summary_pass.passed_count == 2 and summary_pass.error_count == 0
    assert bridge.extract_failure_location(summary_pass) is None

    summary_err = bridge.parse_pytest_output(
        "tests/test_app.py:5: AssertionError\napp_mod.py:2: ZeroDivisionError\nE   AssertionError\n",
        "",
        exit_code=1,
        duration_sec=0.02,
    )
    assert summary_err.error_count == 1
    loc_disk = bridge.extract_failure_location(
        summary_err,
        passed_line_counts={("app_mod.py", 2): 2},
    )
    assert loc_disk is not None
    assert loc_disk.failing_line_content == "y = 1 / 0"
    assert loc_disk.n_ep == 2 and loc_disk.suspiciousness < 1.0

    loc_unk = bridge.extract_failure_location(
        bridge.parse_pytest_output("1 failed", "", exit_code=1)
    )
    assert loc_unk is not None and loc_unk.file_path == "unknown.py"

    over_loc = bridge_mod.OchiaiBridgeLocation(
        file_path="very_long_file_name_for_truncation_check_here.py",
        line_number=99,
        suspiciousness=1.0,
        error_type="ExtremelyLongErrorTypeIdentifier" * 4,
        error_message="M" * 180,
        failing_line_content="C" * 180,
    )
    assert len(over_loc.render_payload_json()) < 320

    monkeypatch.setattr(bridge_mod, "safe_subprocess_run", lambda **kw: (0, "1 passed in 0.01s", ""))
    rc_ok, out_ok, _ = call_script_main_captured(bridge_mod, ["--test-cmd", "pytest", "--json"])
    assert rc_ok == 0 and json.loads(out_ok)["status"] == "PASSED"
    rc_txt, out_txt, _ = call_script_main_captured(bridge_mod, ["--test-cmd", "pytest"])
    assert rc_txt == 0 and "PASSED" in out_txt

    monkeypatch.setattr(
        bridge_mod,
        "safe_subprocess_run",
        lambda **kw: (1, "app_mod.py:2: ZeroDivisionError\nE   ZeroDivisionError: div0\n", ""),
    )
    rc_fl, out_fl, _ = call_script_main_captured(
        bridge_mod,
        ["--test-cmd", "pytest", "--cwd", str(tmp_path), "--collect-pass-coverage", "--json"],
    )
    assert rc_fl == 1 and json.loads(out_fl)["loc"].endswith(":2")

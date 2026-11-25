# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per quality_baseline_manager.py (Schema v2) di NK Hub Generation.
Modulo: tests/test_quality_baseline_manager.py.
Valida BS-02 fail-closed, 12 REQUIRED_RATCHET_KEYS, --check-only read-only, --reason obbligatorio e ceiling W2.3.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Tuple

import pytest
from conftest import (
    WORKSPACE_ROOT,
    call_script_main,
    load_nk_script_module,
    load_script_by_relpath,
)

pytestmark = pytest.mark.fast

baseline_mod = load_nk_script_module("quality_baseline_manager")
ipc_mod = load_script_by_relpath("nk_ipc_contracts", "scripts/schemas/nk_ipc_contracts.py")
rsi_mod = load_nk_script_module("rsi_convergence_engine")
load_baseline = baseline_mod.load_baseline
check_baseline_compliance = baseline_mod.check_baseline_compliance
update_baseline_metrics = baseline_mod.update_baseline_metrics


def _resolve_overlay_file(rel_path: str) -> Path:
    """Risolve un file dando priorita a .staging/ rispetto alla produzione."""
    stg = WORKSPACE_ROOT / ".staging" / rel_path
    return stg if stg.is_file() else (WORKSPACE_ROOT / rel_path)


def _write_sample_lock_ws(tmp_path: Path, name: str = "r0_ws") -> Tuple[Path, Path, Path, Path]:
    """Crea un workspace temporaneo con sample test, oracle_lock.json e quality_baseline.json."""
    ws = tmp_path / name
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)
    sample_test = ws / "tests" / "test_sample.py"
    sample_test.write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")

    file_sha = hashlib.sha256(sample_test.read_bytes()).hexdigest()
    files_map = {"test_sample.py": file_sha}
    valid_lock = {
        "files": files_map,
        "combined_sha256": hashlib.sha256(json.dumps(files_map, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    lock_file = ws / "nk_tracking" / "oracle_lock.json"
    lock_file.write_text(json.dumps(valid_lock, indent=2), encoding="utf-8")

    bl_file = ws / "nk_tracking" / "quality_baseline.json"
    bl_file.write_text(
        json.dumps(
            {
                "schema_version": "6.4.0-Carbon",
                "_recalibrated": True,
                "metrics": {
                    "total_golden_tests": {"value": 120, "direction": "higher_is_better"},
                    "unit_tests_total": {"value": 120, "direction": "higher_is_better"},
                    "unit_tests_passed": {"value": 120, "direction": "higher_is_better"},
                    "sast_critical_violations": {"value": 0, "direction": "lower_is_better"},
                },
                "invariants": {"require_100_percent_test_pass": True},
                "history": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return ws, sample_test, lock_file, bl_file


def test_baseline_fail_closed_corrupted_json_and_lower_is_better_rejection(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """1. Verifica BS-02 fail-closed su JSON corrotto, rifiuto Ratchet SAST/RSI delta e --recalibrate."""
    bad_file = tmp_path / "corrupted_baseline.json"
    bad_file.write_text("{corrupted_baseline: true", encoding="utf-8")
    with pytest.raises(ValueError):
        load_baseline(str(bad_file))
    res = check_baseline_compliance(str(bad_file), {"unit_tests_total": 68})
    assert res["verdict"] == "FAIL" and res["status"] == "ERROR"
    assert bad_file.read_text(encoding="utf-8") == "{corrupted_baseline: true"

    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "6.4.0-Carbon",
        "metrics": {"unit_tests_total": 100, "unit_tests_passed": 100, "unit_tests_pass_rate": 100.0, "sast_critical_violations": 0},
        "invariants": {"require_100_percent_test_pass": True},
        "history": [],
    }
    baseline_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    regressed = {"unit_tests_total": 95, "unit_tests_passed": 95, "unit_tests_pass_rate": 100.0, "sast_critical_violations": 0}
    res_reg = update_baseline_metrics(str(baseline_file), regressed)
    assert res_reg["verdict"] == "FAIL" and res_reg["status"] == "REJECTED"
    assert call_script_main(baseline_mod, ["--file", str(baseline_file), "--update", json.dumps(regressed)], monkeypatch) == 1
    assert call_script_main(baseline_mod, ["--file", str(baseline_file), "--check-only"], monkeypatch) == 1
    ok_metrics = {"unit_tests_total": 100, "unit_tests_passed": 100, "unit_tests_pass_rate": 100.0, "sast_critical_violations": 0}
    assert call_script_main(baseline_mod, ["--file", str(baseline_file), "--check-only", "--metrics", json.dumps(ok_metrics)], monkeypatch) == 0

    bl_lib = tmp_path / "lower_is_better.json"
    bl_lib.write_text(
        json.dumps({
            "schema_version": "6.4.0-Carbon",
            "metrics": {
                "total_golden_tests": 123, "unit_tests_total": 123, "unit_tests_passed": 123,
                "unit_tests_pass_rate": 100.0, "sast_critical_violations": 0, "rsi_residual_delta": 0,
            },
            "invariants": {"require_100_percent_test_pass": True},
            "history": [],
        }),
        encoding="utf-8",
    )
    assert check_baseline_compliance(str(bl_lib), {"total_golden_tests": 123, "unit_tests_total": 123, "unit_tests_passed": 123, "sast_critical_violations": 1, "rsi_residual_delta": 0})["verdict"] == "FAIL"
    assert check_baseline_compliance(str(bl_lib), {"total_golden_tests": 123, "unit_tests_total": 123, "unit_tests_passed": 123, "sast_critical_violations": 0, "rsi_residual_delta": 5})["verdict"] == "FAIL"
    assert call_script_main(baseline_mod, ["--file", str(bl_lib), "--recalibrate"], monkeypatch) == 1
    assert call_script_main(baseline_mod, ["--file", str(bl_lib), "--recalibrate", "--target-tests", "125"], monkeypatch) == 0
    assert load_baseline(str(bl_lib))["metrics"]["total_golden_tests"]["value"] == 125


def test_wp_r0_honesty_recalibrated_strip_and_oracle_lock_sha_mismatch(tmp_path: Path) -> None:
    """2. Verifica gate WP-R0: vettore non misurato < 90, strip _recalibrated e mismatch SHA oracle_lock."""
    assert ipc_mod.RSIDefectVector().effective_totals() == (0, 0)
    unmeasured_rsi = rsi_mod.RSIDefectVector()
    assert unmeasured_rsi.effective_totals() == (0, 0) and rsi_mod.compute_fitness(unmeasured_rsi) < 90.0

    _, sample_test, _, bl_file = _write_sample_lock_ws(tmp_path)
    downward = update_baseline_metrics(str(bl_file), {"_recalibrated": True, "total_golden_tests": 95, "unit_tests_total": 95, "unit_tests_passed": 95})
    assert downward["verdict"] == "FAIL" and downward["status"] == "REJECTED"

    upward = update_baseline_metrics(str(bl_file), {"_recalibrated": True, "total_golden_tests": 121, "unit_tests_total": 121, "unit_tests_passed": 121, "sast_critical_violations": 0})
    assert upward["verdict"] == "PASS" and "_recalibrated" not in load_baseline(str(bl_file))

    sample_test.write_text("def test_ok():\n    assert 1 == 2\n", encoding="utf-8")
    tampered_res = check_baseline_compliance(str(bl_file), {"total_golden_tests": 121, "unit_tests_total": 121, "unit_tests_passed": 121, "sast_critical_violations": 0})
    assert tampered_res["verdict"] == "FAIL"
    assert any(r.get("metric") == "oracle_lock_integrity" for r in tampered_res.get("regressions", []))


def _assert_w0_coherence_matrix(ws: Path, lock_file: Path, bl_file: Path) -> None:
    """Helper per test fail-closed su oracle_lock vuoto, senza digest o assente."""
    for empty_payload in ({}, {"files": {}}, {"locked_files": []}):
        lock_file.write_text(json.dumps(empty_payload), encoding="utf-8")
        anoms = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
        assert len(anoms) == 1 and anoms[0]["current_value"] == "EMPTY"

    lock_file.write_text(json.dumps({"files": ["test_sample.py"]}), encoding="utf-8")
    anoms_nd = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
    assert len(anoms_nd) == 1 and anoms_nd[0]["current_value"] == "MISSING_DIGEST"

    lock_file.unlink()
    assert baseline_mod._verify_oracle_lock_coherence(str(bl_file)) == []
    assert baseline_mod._verify_oracle_lock_coherence(str(bl_file), require_lock=True)[0]["current_value"] == "MISSING"
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    anoms_sov = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
    assert len(anoms_sov) == 1 and anoms_sov[0]["current_value"] == "MISSING"


def _assert_oracle_lock_digest_and_combined(
    lock_file: Path, bl_file: Path, real_sha: str, ok_metrics: Dict[str, Any]
) -> None:
    for bad_digest in ("tampered", "", None, 123, "g" * 64):
        files_bad = {"test_sample.py": bad_digest}
        comb_sha = hashlib.sha256(json.dumps(files_bad, sort_keys=True).encode("utf-8")).hexdigest()
        lock_file.write_text(json.dumps({"files": files_bad, "combined_sha256": comb_sha}), encoding="utf-8")
        anomalies = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
        assert len(anomalies) >= 1 and anomalies[0]["metric"] == "oracle_lock_integrity"
        assert check_baseline_compliance(str(bl_file), ok_metrics)["verdict"] == "FAIL"

    for bad_comb in (None, "", "bad_combined", 999, "f" * 64):
        payload: dict[str, Any] = {"files": {"test_sample.py": real_sha}}
        if bad_comb is not None:
            payload["combined_sha256"] = bad_comb
        lock_file.write_text(json.dumps(payload), encoding="utf-8")
        anomalies = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
        assert len(anomalies) >= 1 and anomalies[0]["metric"] == "oracle_lock_integrity"
        assert check_baseline_compliance(str(bl_file), ok_metrics)["verdict"] == "FAIL"


def test_oracle_lock_fail_closed_and_wave0_coherence_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3. Verifica fail-closed di oracle_lock su non-hex, combined_sha256, {}, added: e mutex."""
    from _internal.nk_common import oracle_lock as ol_mod

    _, sample_test, lock_file, bl_file = _write_sample_lock_ws(tmp_path, "lock_sec")
    real_sha = hashlib.sha256(sample_test.read_bytes()).hexdigest()
    ok_metrics = {"total_golden_tests": 120, "unit_tests_total": 120, "unit_tests_passed": 120, "sast_critical_violations": 0}
    assert baseline_mod._verify_oracle_lock_coherence(str(bl_file)) == []
    _assert_oracle_lock_digest_and_combined(lock_file, bl_file, real_sha, ok_metrics)

    ws_w0, st_w0, lf_w0, bl_w0 = _write_sample_lock_ws(tmp_path, "w0_lock")
    _assert_w0_coherence_matrix(ws_w0, lf_w0, bl_w0)
    (ws_w0 / "scripts").mkdir()
    (ws_w0 / "scripts" / "mod.py").write_text("M = 1\n", encoding="utf-8")
    fmap = {"test_sample.py": ol_mod.compute_lf_sha256(st_w0), "../scripts/mod.py": ol_mod.compute_lf_sha256(ws_w0 / "scripts" / "mod.py")}
    assert ol_mod.write_oracle_lock_manifest(lf_w0, ws_w0 / "tests", fmap)["passed"] is True
    assert lf_w0.is_file()
    assert ol_mod.verify_oracle_lock_manifest(lf_w0, ws_w0 / "tests")["passed"] is True

    (ws_w0 / "tests" / "injected_rogue.py").write_text("def test_r(): assert True\n", encoding="utf-8")
    v_added = ol_mod.verify_oracle_lock_manifest(lf_w0, ws_w0 / "tests")
    assert v_added["passed"] is False and "added:injected_rogue.py" in v_added["mismatches"]
    lf_w0.write_text("{}", encoding="utf-8")
    assert ol_mod.verify_oracle_lock_manifest(lf_w0, ws_w0 / "tests")["passed"] is False

    fail_lock = tmp_path / "mutex_blocked_lock.json"
    monkeypatch.setattr(ol_mod, "_acquire_lock_mutex_state", lambda _p: (None, False, "timeout"))
    assert ol_mod.write_oracle_lock_manifest(fail_lock, ws_w0 / "tests", fmap)["passed"] is False and not fail_lock.exists()


def _stub_cov_pytest_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
    for arg in cmd:
        if isinstance(arg, str) and arg.startswith("--cov-report=json:"):
            Path(arg.split(":", 1)[1]).write_text(
                json.dumps({"totals": {"num_statements": 4, "covered_lines": 4, "num_branches": 2, "covered_branches": 1, "percent_statements_covered": 100.0, "percent_branches_covered": 50.0, "percent_covered": 83.33}}),
                encoding="utf-8",
            )
    return SimpleNamespace(returncode=0, stdout="93 passed in 0.05s\n", stderr="")


def _setup_live_cov_ws(tmp_path: Path) -> Tuple[Path, Path]:
    cov_ws = tmp_path / "cov_ws"
    for d in ("scripts", "tests", "nk_tracking"):
        (cov_ws / d).mkdir(parents=True)
    (cov_ws / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (cov_ws / "scripts" / "sample_calc.py").write_text("def add_pos(x: int) -> int:\n    if x > 0:\n        return x * 2\n    return -x\n", encoding="utf-8")
    (cov_ws / "tests" / "test_sample_calc.py").write_text("def test_pos(): assert True\n", encoding="utf-8")
    bl_file = cov_ws / "nk_tracking" / "quality_baseline.json"
    bl_file.write_text(
        json.dumps({
            "_version": "1.0.0-Generation",
            "metrics": {
                "total_golden_tests": {"value": 93, "direction": "higher_is_better"},
                "unit_tests_total": {"value": 93, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 93, "direction": "higher_is_better"},
                "branch_coverage_pct": {"value": 85.69, "direction": "higher_is_better"},
                "pytest_duration_s": {"value": 10.0, "threshold_max": 28.0, "direction": "lower_is_better"},
            },
        }),
        encoding="utf-8",
    )
    return cov_ws, bl_file


def _assert_live_cov_metrics_and_cli(
    cov_ws: Path, bl_file: Path, monkeypatch: Any, capsys: Any
) -> None:
    sys_tmp = Path(tempfile.gettempdir())
    before_dirs = {p.name for p in sys_tmp.glob("nk_qbm_cov_*")}

    monkeypatch.setattr(baseline_mod, "subprocess", SimpleNamespace(run=_stub_cov_pytest_run))
    monkeypatch.setenv("COV_CORE_SOURCE", "scripts")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    live = baseline_mod.measure_live_pytest_metrics(cov_ws, with_coverage=True)
    assert (live["unit_tests_passed"], live["pass_rate_pct"]) == (93, 100.0)
    assert live["statement_coverage_pct"] > 0.0
    assert 0.0 < live["true_branch_coverage_pct"] < 100.0
    assert live["combined_coverage_pct"] > 0.0
    assert "branch_coverage_pct" not in live

    rc = call_script_main(baseline_mod, ["check", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch)
    cli_out = json.loads(capsys.readouterr().out)
    assert (rc, cli_out["verdict"], cli_out["live_metrics"]["true_branch_coverage_pct"]) == (0, "PASS", live["true_branch_coverage_pct"])
    assert {p.name for p in sys_tmp.glob("nk_qbm_cov_*")} <= before_dirs


def test_measure_live_pytest_metrics_with_coverage_and_cli(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """4. Verifica measure_live_pytest_metrics(..., with_coverage=True) e CLI --with-coverage senza residui."""
    cov_ws, bl_file = _setup_live_cov_ws(tmp_path)
    _assert_live_cov_metrics_and_cli(cov_ws, bl_file, monkeypatch, capsys)


def test_live_with_coverage_fail_closed_and_branch_regression(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """5. Verifica fail-closed su --with-coverage privo di JSON e regressione true_branch_coverage_pct."""
    bl_file = tmp_path / "cov_gate_bl.json"
    bl_file.write_text(
        json.dumps({
            "_version": "1.0.0-Generation",
            "metrics": {
                "total_golden_tests": {"value": 93, "direction": "higher_is_better"},
                "unit_tests_total": {"value": 93, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 93, "direction": "higher_is_better"},
                "true_branch_coverage_pct": {"value": 88.5, "direction": "higher_is_better"},
            },
        }),
        encoding="utf-8",
    )
    no_cov_metrics = {"total_golden_tests": 95, "unit_tests_total": 95, "unit_tests_passed": 95, "pass_rate_pct": 100.0, "failed_tests": 0}
    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: dict(no_cov_metrics))
    assert call_script_main(baseline_mod, ["check", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch) == 1
    out_miss = json.loads(capsys.readouterr().out)
    assert out_miss["verdict"] == "FAIL" and out_miss["status"] == "ERROR"
    assert call_script_main(baseline_mod, ["update", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch) == 1
    out_upd = json.loads(capsys.readouterr().out)
    assert out_upd["verdict"] == "FAIL" and out_upd["status"] == "REJECTED"

    low_cov = dict(no_cov_metrics, true_branch_coverage_pct=82.0)
    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: dict(low_cov))
    assert call_script_main(baseline_mod, ["check", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch) == 1
    out_reg = json.loads(capsys.readouterr().out)
    assert out_reg["verdict"] == "FAIL" and any(r.get("metric") == "true_branch_coverage_pct" for r in out_reg.get("regressions", []))


def _assert_recal_floor_rejections(bl_file: Path, qbm_consts: Any) -> None:
    assert baseline_mod.recalibrate_baseline(str(bl_file), target_golden_tests=110, allow_ratchet_down=False)["verdict"] == "FAIL"
    assert baseline_mod.recalibrate_baseline(str(bl_file), target_golden_tests=92, allow_ratchet_down=True, pytest_duration_s=15.0, combined_coverage_pct=86.0)["verdict"] == "FAIL"
    assert baseline_mod.recalibrate_baseline(str(bl_file), target_golden_tests=110, allow_ratchet_down=True, pytest_duration_s=15.0, combined_coverage_pct=84.9)["verdict"] == "FAIL"
    assert baseline_mod.recalibrate_baseline(str(bl_file), target_golden_tests=110, allow_ratchet_down=True, pytest_duration_s=qbm_consts.MAX_PYTEST_DURATION_CEIL + 0.5, combined_coverage_pct=86.0)["verdict"] == "FAIL"


def test_wave2a_recalibrate_and_allow_ratchet_down_constitutional_floors(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """6. Verifica recalibrate / --allow-ratchet-down: >=93, 100% pass, 0 skip, >=85% cov, <=28s e --reason."""
    from _internal.quality_baseline_manager import constants as qbm_consts

    bl_file = tmp_path / "wave2a_recal.json"
    bl_file.write_text(
        json.dumps({
            "schema_version": "1.0.0-Generation",
            "metrics": {
                "total_golden_tests": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_total": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 150, "direction": "higher_is_better"},
                "pass_rate_pct": {"value": 100.0, "direction": "higher_is_better"},
                "failed_tests": {"value": 0, "direction": "lower_is_better"},
                "tests_skipped": {"value": 0, "direction": "lower_is_better"},
                "combined_coverage_pct": {"value": 90.0, "direction": "higher_is_better"},
                "pytest_duration_s": {"value": 25.0, "threshold_max": 28.0, "direction": "lower_is_better"},
            },
            "history": [],
        }),
        encoding="utf-8",
    )

    _assert_recal_floor_rejections(bl_file, qbm_consts)
    bad_pass = {"total_golden_tests": 110, "unit_tests_total": 110, "unit_tests_passed": 109, "pass_rate_pct": 99.09, "failed_tests": 1, "tests_skipped": 0, "combined_coverage_pct": 86.0, "pytest_duration_s": 15.0}
    assert update_baseline_metrics(str(bl_file), bad_pass, allow_ratchet_down=True)["verdict"] == "FAIL"
    bad_skip = dict(bad_pass, unit_tests_passed=110, pass_rate_pct=100.0, failed_tests=0, tests_skipped=1)
    assert update_baseline_metrics(str(bl_file), bad_skip, allow_ratchet_down=True)["verdict"] == "FAIL"

    ok_recal = baseline_mod.recalibrate_baseline(
        str(bl_file), target_golden_tests=110, allow_ratchet_down=True, pytest_duration_s=24.9, combined_coverage_pct=86.5
    )
    assert (ok_recal["verdict"], ok_recal["status"]) == ("PASS", "UPDATED")
    assert load_baseline(str(bl_file))["metrics"]["total_golden_tests"]["value"] == 110

    cli_bad_cov = dict(bad_skip, tests_skipped=0, total_golden_tests=105, unit_tests_total=105, unit_tests_passed=105, combined_coverage_pct=84.0)
    assert call_script_main(baseline_mod, ["update", "--file", str(bl_file), "--allow-ratchet-down", "--reason", "W1 cov test", "--metrics", json.dumps(cli_bad_cov)], monkeypatch) == 1
    cli_ok = dict(cli_bad_cov, combined_coverage_pct=85.5, pytest_duration_s=24.0)
    assert call_script_main(baseline_mod, ["update", "--file", str(bl_file), "--allow-ratchet-down", "--metrics", json.dumps(cli_ok)], monkeypatch) == 1
    assert call_script_main(baseline_mod, ["update", "--file", str(bl_file), "--allow-ratchet-down", "--reason", "Wave 1 recalibration audit", "--metrics", json.dumps(cli_ok)], monkeypatch) == 0
    assert load_baseline(str(bl_file))["metrics"]["total_golden_tests"]["value"] == 105


def test_benchmark_runner_skill_coverage_and_deleted_helpers(tmp_path: Path) -> None:
    """7. Esercita benchmark_runner._count_live_skills_overlay, _extract_coverage_totals e _load_deleted_rel."""
    from _internal.quality_baseline_manager import benchmark_runner as qbm_bm

    ws = tmp_path / "bm_helpers_ws"
    for rel in (".agents/skills/SK_KEEP/SKILL.md", ".agents/skills/SK_DEL/SKILL.md", ".staging/.agents/skills/SK_STG/SKILL.md"):
        p = ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Skill\n", encoding="utf-8")
    assert qbm_bm._count_live_skills_overlay(ws, {".agents/skills/SK_DEL/SKILL.md"}) == 2

    assert qbm_bm._extract_coverage_totals(tmp_path / "missing_cov.json") == {}
    bad_cov = tmp_path / "bad_cov.json"
    bad_cov.write_bytes(b"{bad")
    assert qbm_bm._extract_coverage_totals(bad_cov) == {}
    empty_cov = tmp_path / "empty_cov.json"
    empty_cov.write_text(json.dumps({"totals": {}}), encoding="utf-8")
    assert qbm_bm._extract_coverage_totals(empty_cov) == {}

    fallback_cov = tmp_path / "fallback_cov.json"
    fallback_cov.write_text(json.dumps({"totals": {"num_statements": 10, "covered_lines": 8, "num_branches": 4, "covered_branches": 3}}), encoding="utf-8")
    assert qbm_bm._extract_coverage_totals(fallback_cov) == {"statement_coverage_pct": 80.0, "true_branch_coverage_pct": 75.0, "combined_coverage_pct": 75.0}

    del_f = tmp_path / "del.json"
    del_f.write_text(json.dumps({"deleted_files": ["tests\\a.py"]}), encoding="utf-8")
    assert qbm_bm._load_deleted_rel(del_f) == {"tests/a.py"}
    del_f.write_text(json.dumps(["/tests/b.py"]), encoding="utf-8")
    assert qbm_bm._load_deleted_rel(del_f) == {"tests/b.py"}
    del_f.write_bytes(b"{bad")
    assert qbm_bm._load_deleted_rel(del_f) == set()
    del_f.write_text(json.dumps({"deleted_files": "bad"}), encoding="utf-8")
    assert qbm_bm._load_deleted_rel(del_f) == set()


def test_benchmark_runner_empty_overlay_and_stdout_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8. Esercita measure_live_pytest_metrics su repo vuoto, tombstone .staging, dot-progress, mirror e xfailed."""
    import subprocess as std_subprocess
    from _internal.quality_baseline_manager import benchmark_runner as qbm_bm

    ws_empty = tmp_path / "bm_empty_ws"
    (ws_empty / ".agents" / "skills" / "S1").mkdir(parents=True)
    (ws_empty / ".agents" / "skills" / "S1" / "SKILL.md").write_text("# S1\n", encoding="utf-8")
    (ws_empty / "scripts").mkdir(parents=True)
    (ws_empty / "tests").mkdir(parents=True)
    (ws_empty / "tests" / "test_gone.py").write_bytes(b"def test_g(): assert True\n")
    (ws_empty / ".staging").mkdir(parents=True)
    (ws_empty / ".staging" / ".deleted_files.json").write_text(json.dumps({"deleted_files": ["tests/test_gone.py"]}), encoding="utf-8")
    monkeypatch.setattr(baseline_mod, "_scripts_dir", ws_empty / "scripts")
    empty_res = qbm_bm.measure_live_pytest_metrics(workspace_root=None, with_coverage=False)
    assert (empty_res["total_golden_tests"], empty_res["skills_audited"]) == (0, 1)

    ws_run = tmp_path / "bm_run_ws"
    (ws_run / "tests" / "__pycache__").mkdir(parents=True)
    (ws_run / ".staging" / "tests" / "__pycache__").mkdir(parents=True)
    (ws_run / "tests" / "test_prod.py").write_bytes(b"def test_p(): assert 1 == 1\n")
    (ws_run / "tests" / "__pycache__" / "test_skip.py").write_bytes(b"")
    (ws_run / ".staging" / "tests" / "test_stg.py").write_bytes(b"def test_s(): assert 2 == 2\n")
    (ws_run / ".staging" / "tests" / "__pycache__" / "test_skip2.py").write_bytes(b"")
    monkeypatch.setattr(qbm_bm.subprocess, "run", lambda cmd, **_kw: std_subprocess.CompletedProcess(cmd, 0, "2 passed in 0.02s\n", ""))
    res_nocov = qbm_bm.measure_live_pytest_metrics(ws_run, with_coverage=False)
    assert (res_nocov["unit_tests_passed"], res_nocov["failed_tests"]) == (2, 0)
    assert "statement_coverage_pct" not in res_nocov and "skills_audited" not in res_nocov

    ws = tmp_path / "bm_parse_ws"
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_unit.py").write_bytes(b"def test_u(): assert 1 == 1\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setattr(qbm_bm, "is_temp_workspace", lambda _p: False)
    monkeypatch.setattr(qbm_bm.subprocess, "run", lambda cmd, **_kw: std_subprocess.CompletedProcess(cmd, 0, "...  [100%]\n", ""))
    res_dots = qbm_bm.measure_live_pytest_metrics(ws, with_coverage=True)
    assert res_dots["unit_tests_passed"] == 3 and "statement_coverage_pct" not in res_dots

    monkeypatch.setattr(qbm_bm, "is_temp_workspace", lambda _p: True)
    monkeypatch.setattr(qbm_bm.subprocess, "run", lambda cmd, **_kw: std_subprocess.CompletedProcess(cmd, 1, "", "boom"))
    res_err = qbm_bm.measure_live_pytest_metrics(ws, with_coverage=False)
    assert (res_err["failed_tests"], res_err["pass_rate_pct"]) == (1, 0.0)

    monkeypatch.setattr(
        qbm_bm.subprocess, "run",
        lambda cmd, **_kw: std_subprocess.CompletedProcess(cmd, 1, "1 passed, 1 failed, 1 error, 2 skipped, 1 xfailed in 0.05s\n", ""),
    )
    res_mix = qbm_bm.measure_live_pytest_metrics(ws, with_coverage=False)
    assert (res_mix["tests_skipped"], res_mix["failed_tests"], res_mix["unit_tests_total"]) == (3, 2, 6)


def _assert_qbm_ratchet_core_edges(tmp_path: Path, qbm_rc: Any) -> None:
    absent_bl = tmp_path / "never_written_bl.json"
    ro_miss = check_baseline_compliance(str(absent_bl), {"unit_tests_total": 100})
    assert (ro_miss["status"], ro_miss["verdict"]) == ("MISSING", "FAIL")
    assert not absent_bl.exists()

    expanded = qbm_rc._sanitize_and_expand_metrics({"_recalibrated": True, "golden_tests_68": {"passed": 95, "total": 95, "pass_rate_pct": 100.0}})
    assert (expanded["unit_tests_passed"], expanded["total_golden_tests"]) == (95, 95)

    bad_metrics_bl = tmp_path / "bad_metrics_bl.json"
    bad_metrics_bl.write_text(json.dumps({"metrics": "invalid"}), encoding="utf-8")
    assert check_baseline_compliance(str(bad_metrics_bl), {"unit_tests_total": 1})["status"] == "ERROR"

    flat_bl = tmp_path / "flat_bl.json"
    flat_bl.write_text(json.dumps({"unit_tests_total": 100}), encoding="utf-8")
    assert check_baseline_compliance(str(flat_bl), {"unit_tests_total": 100, "note": "ignored"})["verdict"] == "PASS"

    for bad_gate in ("invalid", {"total_golden_tests": 50}, {"pass_rate_pct": 99.0}, {"failed_tests": 1}):
        assert qbm_rc._validate_legitimate_update_gate(bad_gate)["status"] == "REJECTED"

    corrupt_bl = tmp_path / "corrupt_upd.json"
    corrupt_bl.write_bytes(b"{bad")
    assert update_baseline_metrics(str(corrupt_bl), {"total_golden_tests": 10})["status"] == "REJECTED"
    init_bl = tmp_path / "init_new_bl.json"
    assert update_baseline_metrics(str(init_bl), {"total_golden_tests": 100, "unit_tests_total": 100, "unit_tests_passed": 100})["status"] == "INITIALIZED"


def test_qbm_constants_cli_errors_and_ratchet_core_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """9. Esercita constants.py, cli.py error paths e ratchet_core (check missing/flat v1/INITIALIZED)."""
    from _internal.quality_baseline_manager import constants as qbm_const, ratchet_core as qbm_rc

    assert load_baseline(str(tmp_path / "absent_bl.json")) is None
    list_bl = tmp_path / "list_bl.json"
    list_bl.write_bytes(b"[1, 2]")
    with pytest.raises(ValueError):
        load_baseline(str(list_bl))

    created = baseline_mod.create_default_baseline("Demo", {"unit_tests_total": 100, "failed_tests": {"value": 0, "direction": "lower_is_better"}})
    assert created["metrics"]["unit_tests_total"]["direction"] == "higher_is_better"
    assert created["schema_version"] == 2
    assert qbm_const._is_valid_gt68_recalibration({}) is False

    stg_bl = tmp_path / "ws" / ".staging" / "nk_tracking" / "quality_baseline.json"
    stg_bl.parent.mkdir(parents=True)
    stg_bl.write_text(json.dumps(created), encoding="utf-8")
    assert qbm_const._resolve_workspace_root_from_baseline(str(stg_bl)) == (tmp_path / "ws").resolve()
    assert qbm_const._resolve_default_baseline_path().endswith("quality_baseline.json")

    for argv_err in (
        ["invalid_cmd", "--file", str(stg_bl)],
        ["check", "--file", str(stg_bl), "--metrics", "{bad"],
        ["check", "--file", str(stg_bl)],
        ["update", "--file", str(stg_bl), "--check-only"],
    ):
        assert call_script_main(baseline_mod, argv_err, monkeypatch) == 1

    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: {"unit_tests_total": 10, "unit_tests_passed": 9, "failed_tests": 1, "pass_rate_pct": 90.0})
    assert call_script_main(baseline_mod, ["recalibrate", "--file", str(stg_bl), "--live"], monkeypatch) == 1
    _assert_qbm_ratchet_core_edges(tmp_path, qbm_rc)


def _assert_schema_v2_real_and_ratchet_keys(qbm_consts: Any) -> None:
    qb_real = json.loads(_resolve_overlay_file("nk_tracking/quality_baseline.json").read_text(encoding="utf-8-sig"))
    assert qb_real["schema_version"] == 2
    assert qb_real["_version"] == "1.0.0-Generation"
    assert qb_real["metrics"]["tests_skipped"]["direction"] == "lower_is_better"
    assert qb_real["metrics"]["pytest_duration_s"]["threshold_max"] == 28.0
    assert len(qb_real["metrics"]) == 14
    assert set(qb_real["metrics"].keys()) == set(qbm_consts.SCHEMA_V2_LIVE_KEYS)
    assert not (set(qb_real["metrics"].keys()) & qbm_consts.PHANTOM_V1_METRIC_KEYS)
    assert "tests_skipped" in baseline_mod.LOWER_IS_BETTER_KEYS
    assert len(qbm_consts.REQUIRED_RATCHET_KEYS) == 12
    assert set(qbm_consts.REQUIRED_RATCHET_KEYS) == {
        "total_golden_tests", "unit_tests_total", "unit_tests_passed", "unit_tests_pass_pct",
        "pass_rate_pct", "failed_tests", "tests_skipped", "pytest_duration_s",
        "statement_coverage_pct", "true_branch_coverage_pct", "combined_coverage_pct", "sast_critical_violations",
    }


def _assert_ratchet_missing_and_coverage_floors(bl_full: Path) -> None:
    omitted_res = check_baseline_compliance(str(bl_full), {"unit_tests_total": 120, "unit_tests_passed": 120})
    missing_codes = {r.get("metric"): r.get("error_code") for r in omitted_res.get("regressions", [])}
    assert omitted_res["verdict"] == "FAIL"
    for k in ("total_golden_tests", "tests_skipped", "pytest_duration_s", "true_branch_coverage_pct", "sast_critical_violations"):
        assert missing_codes.get(k) == "MISSING_REQUIRED_METRIC"
    assert update_baseline_metrics(str(bl_full), {"unit_tests_total": 120, "unit_tests_passed": 120})["status"] == "REJECTED"

    gate_skip = baseline_mod._validate_legitimate_update_gate({"total_golden_tests": 120, "unit_tests_total": 120, "unit_tests_passed": 120, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 1})
    assert gate_skip is not None
    assert (gate_skip["status"], gate_skip["verdict"], gate_skip["regressions"][0]["metric"]) == ("REJECTED", "FAIL", "tests_skipped")

    missing_ratchet = update_baseline_metrics(
        str(bl_full), {"total_golden_tests": 110, "unit_tests_total": 110, "unit_tests_passed": 110, "pass_rate_pct": 100.0, "mutation_active": True}, allow_ratchet_down=True
    )
    assert missing_ratchet["verdict"] == "FAIL"
    assert missing_ratchet["status"] == "REJECTED"
    assert {"failed_tests", "tests_skipped", "pytest_duration_s", "diff_mutation_kill_rate"} <= {reg.get("metric") for reg in missing_ratchet.get("regressions", [])}
    bl_min = bl_full.with_name("floor_min.json")
    bl_min.write_text(json.dumps({"schema_version": 2, "metrics": {"statement_coverage_pct": {"value": 90.95, "threshold_min": 90.5, "direction": "higher_is_better"}}, "history": []}), encoding="utf-8")
    assert check_baseline_compliance(str(bl_min), {"statement_coverage_pct": 90.91})["verdict"] == "PASS"
    assert check_baseline_compliance(str(bl_min), {"statement_coverage_pct": 90.4})["verdict"] == "FAIL"


def _assert_recalibrate_helper_floors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qbm_rh: Any, bl_full: Path) -> None:
    assert qbm_rh._ratchet_allows_coverage_key("true_branch_coverage_pct", 5.0, {"combined_coverage_pct": 90.0}) is False
    assert qbm_rh._ratchet_allows_coverage_key("branch_coverage_pct", 74.9, {"combined_coverage_pct": 90.0}) is False
    assert qbm_rh._ratchet_allows_coverage_key("true_branch_coverage_pct", 75.0, {"combined_coverage_pct": 85.0}) is True
    assert qbm_rh._ratchet_allows_test_count_key(110.0, {"total_golden_tests": 110, "unit_tests_passed": 110, "true_branch_coverage_pct": 74.0}) is False

    base_ok = {
        "total_golden_tests": 110, "unit_tests_total": 110, "unit_tests_passed": 110, "unit_tests_pass_pct": 100.0,
        "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 22.0,
        "statement_coverage_pct": 88.0, "combined_coverage_pct": 90.0, "true_branch_coverage_pct": 5.0, "sast_critical_violations": 0,
    }
    assert update_baseline_metrics(str(bl_full), base_ok, allow_ratchet_down=True)["verdict"] == "FAIL"
    assert update_baseline_metrics(str(bl_full), dict(base_ok, true_branch_coverage_pct=75.0, combined_coverage_pct=85.0), allow_ratchet_down=True)["verdict"] == "PASS"

    init_bl = tmp_path / "recal_helper_bl.json"
    assert qbm_rh._allows_authorized_ratchet_down("skills_audited", 1.0, {}) is True
    assert qbm_rh._allows_authorized_ratchet_down("skills_audited", 0.0, {}) is False
    assert qbm_rh._ratchet_allows_coverage_key("statement_coverage_pct", 90.0, {"combined_coverage_pct": 84.0}) is False
    assert qbm_rh._ratchet_allows_test_count_key(92.0, {}) is False
    assert qbm_rh._ratchet_allows_test_count_key(95.0, {"pass_rate_pct": 99.5}) is False
    assert qbm_rh._ratchet_allows_test_count_key(95.0, {"failed_tests": 1}) is False
    monkeypatch.setattr(baseline_mod, "update_baseline_metrics", None)
    assert qbm_rh._build_and_apply_recalibration(str(init_bl), 95, True, None, None, update_fn=None)["status"] == "REJECTED"
    monkeypatch.setattr(baseline_mod, "update_baseline_metrics", lambda _p, _m: {"status": "UPDATED", "verdict": "PASS"})
    assert qbm_rh._build_and_apply_recalibration(str(init_bl), 95, True, None, None)["status"] == "UPDATED"


def test_wave5b_required_ratchet_keys_schema_v2_and_recalibrate_floors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """10. Verifica Schema v2 live (threshold_max == 28.0), 12 REQUIRED_RATCHET_KEYS e recalibrate_helpers."""
    from _internal.quality_baseline_manager import constants as qbm_consts, recalibrate_helpers as qbm_rh

    _assert_schema_v2_real_and_ratchet_keys(qbm_consts)
    bl_full = tmp_path / "wave5b_full.json"
    bl_full.write_text(
        json.dumps({
            "schema_version": 2,
            "metrics": {
                "total_golden_tests": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_total": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_pass_pct": {"value": 100.0, "direction": "higher_is_better"},
                "pass_rate_pct": {"value": 100.0, "direction": "higher_is_better"},
                "failed_tests": {"value": 0, "direction": "lower_is_better"},
                "tests_skipped": {"value": 0, "direction": "lower_is_better"},
                "pytest_duration_s": {"value": 25.0, "threshold_max": 28.0, "direction": "lower_is_better"},
                "statement_coverage_pct": {"value": 88.0, "direction": "higher_is_better"},
                "combined_coverage_pct": {"value": 90.0, "direction": "higher_is_better"},
                "true_branch_coverage_pct": {"value": 88.0, "direction": "higher_is_better"},
                "branch_coverage_pct": {"value": 88.0, "direction": "higher_is_better"},
                "sast_critical_violations": {"value": 0, "direction": "lower_is_better"},
            },
            "history": [],
        }),
        encoding="utf-8",
    )
    _assert_ratchet_missing_and_coverage_floors(bl_full)
    _assert_recalibrate_helper_floors(tmp_path, monkeypatch, qbm_rh, bl_full)


def _assert_w5b_cli_nodur_and_oracle_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qbm_cli: Any, bl_full: Path
) -> None:
    bl_no_dur = tmp_path / "wave5b_nodur.json"
    bl_no_dur.write_text(json.dumps({"schema_version": 2, "metrics": {"total_golden_tests": {"value": 150, "direction": "higher_is_better"}, "unit_tests_total": {"value": 150, "direction": "higher_is_better"}, "unit_tests_passed": {"value": 150, "direction": "higher_is_better"}}, "history": []}), encoding="utf-8")
    assert call_script_main(baseline_mod, ["recalibrate", "--file", str(bl_no_dur), "--target-tests", "110", "--allow-ratchet-down", "--reason", "W1 nodur audit"], monkeypatch) == 0
    assert load_baseline(str(bl_no_dur))["metrics"]["total_golden_tests"]["value"] == 110

    assert qbm_cli._invoke_recalibrate_fn(lambda _p, t: {"status": "UPDATED", "verdict": "PASS", "target": t}, str(bl_no_dur), 111, True, {"pytest_duration_s": 10.0, "combined_coverage_pct": 87.0})["target"] == 111
    res_kw = qbm_cli._invoke_recalibrate_fn(lambda _p, _c, **kw: {"verdict": "PASS", "kw": kw}, "b.json", 112, True, {"pytest_duration_s": 12.5, "combined_coverage_pct": 87.0})
    assert res_kw["kw"]["allow_ratchet_down"] is True
    assert res_kw["kw"]["pytest_duration_s"] == 12.5
    assert res_kw["kw"]["combined_coverage_pct"] == 87.0

    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: {"total_golden_tests": 112, "unit_tests_total": 112, "unit_tests_passed": 112, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 18.5})
    assert call_script_main(baseline_mod, ["recalibrate", "--file", str(bl_full), "--live", "--with-coverage"], monkeypatch) == 1

    live_pos = {"total_golden_tests": 112, "unit_tests_total": 112, "unit_tests_passed": 112, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 18.5, "combined_coverage_pct": 86.2}
    assert call_script_main(baseline_mod, ["check", str(bl_full), json.dumps(live_pos)], monkeypatch) == 0
    assert call_script_main(baseline_mod, ["recalibrate", str(bl_full)], monkeypatch) == 1

    ws = tmp_path / "w5b_lock"
    (ws / "nk_tracking").mkdir(parents=True)
    bl_path = ws / "nk_tracking" / "quality_baseline.json"
    bl_path.write_text(
        json.dumps(baseline_mod.create_default_baseline("NK_Hub", {"total_golden_tests": 112, "unit_tests_total": 112, "unit_tests_passed": 100, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 25.0, "combined_coverage_pct": 86.0, "true_branch_coverage_pct": 78.0})),
        encoding="utf-8",
    )
    lock_path = ws / "nk_tracking" / "oracle_lock.json"
    lock_path.write_text(json.dumps([1, 2]), encoding="utf-8")
    anoms_bad = baseline_mod._verify_oracle_lock_coherence(str(bl_path))
    assert len(anoms_bad) == 1 and anoms_bad[0]["current_value"] == "INVALID_ROOT"
    lock_path.write_text(json.dumps({"locked_files": ["missing_a.py"], "files": ["missing_b.py"], "target": str(ws)}), encoding="utf-8")
    assert len(baseline_mod._verify_oracle_lock_coherence(str(bl_path))) >= 1
    lock_path.unlink()
    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: {"total_golden_tests": 112, "unit_tests_total": 112, "unit_tests_passed": 110, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 18.0, "combined_coverage_pct": 86.5, "true_branch_coverage_pct": 79.0})
    assert call_script_main(baseline_mod, ["check", "--file", str(bl_path), "--live"], monkeypatch) == 1
    assert call_script_main(baseline_mod, ["update", "--file", str(bl_path), "--metrics", json.dumps({"total_golden_tests": 112, "unit_tests_total": 112, "unit_tests_passed": 112, "pass_rate_pct": 100.0, "failed_tests": 0, "tests_skipped": 2})], monkeypatch) == 1


def test_wave5b_recalibrate_cli_forwarding_and_live_fail_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """11. Verifica forwarding CLI recalibrate con --reason, --live --with-coverage, oracle_lock lista e live fail."""
    from _internal.quality_baseline_manager import cli as qbm_cli

    bl_full = tmp_path / "wave5b_cli_full.json"
    bl_full.write_text(
        json.dumps({
            "schema_version": 2,
            "metrics": {
                "total_golden_tests": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_total": {"value": 150, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 150, "direction": "higher_is_better"},
                "pass_rate_pct": {"value": 100.0, "direction": "higher_is_better"},
                "failed_tests": {"value": 0, "direction": "lower_is_better"},
                "tests_skipped": {"value": 0, "direction": "lower_is_better"},
                "pytest_duration_s": {"value": 25.0, "threshold_max": 28.0, "direction": "lower_is_better"},
                "combined_coverage_pct": {"value": 90.0, "direction": "higher_is_better"},
            },
            "history": [],
        }),
        encoding="utf-8",
    )

    assert call_script_main(baseline_mod, ["recalibrate", "--file", str(bl_full), "--target-tests", "110", "--allow-ratchet-down", "--reason", "W1 fail cov check"], monkeypatch) == 1
    capsys.readouterr()
    assert call_script_main(baseline_mod, ["recalibrate", "--file", str(bl_full), "--target-tests", "110", "--allow-ratchet-down"], monkeypatch) == 1
    capsys.readouterr()

    monkeypatch.setattr(
        baseline_mod, "measure_live_pytest_metrics",
        lambda *_a, **_k: {
            "total_golden_tests": 112, "unit_tests_total": 112, "unit_tests_passed": 112, "pass_rate_pct": 100.0,
            "failed_tests": 0, "tests_skipped": 0, "pytest_duration_s": 18.5,
            "statement_coverage_pct": 88.0, "true_branch_coverage_pct": 79.5, "combined_coverage_pct": 86.2,
        },
    )
    assert call_script_main(baseline_mod, ["recalibrate", "--file", str(bl_full), "--live", "--with-coverage", "--allow-ratchet-down", "--reason", "W1 live cov recalibration"], monkeypatch) == 0
    live_out = json.loads(capsys.readouterr().out)
    assert (live_out["verdict"], live_out["status"]) == ("PASS", "UPDATED")
    saved = load_baseline(str(bl_full))
    assert (saved["metrics"]["total_golden_tests"]["value"], saved["metrics"]["pytest_duration_s"]["value"], saved["metrics"]["combined_coverage_pct"]["value"]) == (112, 18.5, 86.2)
    _assert_w5b_cli_nodur_and_oracle_root(tmp_path, monkeypatch, qbm_cli, bl_full)
    capsys.readouterr()

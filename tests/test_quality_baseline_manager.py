# -*- coding: utf-8 -*-
"""
Test unitari Zero-Mock per quality_baseline_manager.py di NK Hub Generation 1.0.0-Generation.
Modulo: tests/test_quality_baseline_manager.py.
Valida BS-02 fail-closed, rifiuto regressioni Ratchet, coerenza oracle_lock, --with-coverage e skill evals.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Tuple

import pytest
from conftest import (
    WORKSPACE_ROOT,
    call_script_main,
    load_nk_script_module,
    load_script_by_relpath,
)

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


def _write_sample_lock_ws(
    tmp_path: Path, name: str = "r0_ws"
) -> Tuple[Path, Path, Path, Path]:
    """Crea un workspace temporaneo con sample test, oracle_lock.json e quality_baseline.json."""
    ws = tmp_path / name
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)
    sample_test = ws / "tests" / "test_sample.py"
    sample_test.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    file_sha = hashlib.sha256(sample_test.read_bytes()).hexdigest()
    files_map = {"test_sample.py": file_sha}
    valid_lock = {
        "files": files_map,
        "combined_sha256": hashlib.sha256(
            json.dumps(files_map, sort_keys=True).encode("utf-8")
        ).hexdigest(),
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


@pytest.mark.fast
def test_baseline_fail_closed_on_corrupted_json(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """1. Verifica BS-02 fail-closed su JSON corrotto, rifiuto Ratchet e check-only con --metrics."""
    bad_file = tmp_path / "corrupted_baseline.json"
    bad_file.write_text("{corrupted_baseline: true", encoding="utf-8")

    with pytest.raises(ValueError):
        load_baseline(str(bad_file))

    res = check_baseline_compliance(str(bad_file), {"unit_tests_total": 68})
    assert res["verdict"] == "FAIL"
    assert res["status"] == "ERROR"
    assert bad_file.read_text(encoding="utf-8") == "{corrupted_baseline: true"

    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "6.4.0-Carbon",
        "metrics": {
            "unit_tests_total": 100,
            "unit_tests_passed": 100,
            "unit_tests_pass_rate": 100.0,
            "sast_critical_violations": 0,
        },
        "invariants": {"require_100_percent_test_pass": True},
        "history": [],
    }
    baseline_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    regressed = {
        "unit_tests_total": 95,
        "unit_tests_passed": 95,
        "unit_tests_pass_rate": 100.0,
        "sast_critical_violations": 0,
    }
    res_reg = update_baseline_metrics(str(baseline_file), regressed)
    assert res_reg["verdict"] == "FAIL"
    assert res_reg["status"] == "REJECTED"

    assert (
        call_script_main(
            baseline_mod,
            ["--file", str(baseline_file), "--update", json.dumps(regressed)],
            monkeypatch,
        )
        == 1
    )
    assert (
        call_script_main(
            baseline_mod,
            ["--file", str(baseline_file), "--check-only"],
            monkeypatch,
        )
        == 1
    )
    ok_metrics = {
        "unit_tests_total": 100,
        "unit_tests_passed": 100,
        "unit_tests_pass_rate": 100.0,
        "sast_critical_violations": 0,
    }
    assert (
        call_script_main(
            baseline_mod,
            ["--file", str(baseline_file), "--check-only", "--metrics", json.dumps(ok_metrics)],
            monkeypatch,
        )
        == 0
    )


@pytest.mark.fast
def test_baseline_lower_is_better_sast_and_rsi_delta_rejection(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """2. Verifica il rifiuto su SAST/RSI delta e il ratchet monotonically non-decreasing su --recalibrate."""
    baseline_file = tmp_path / "quality_baseline.json"
    initial_data = {
        "schema_version": "6.4.0-Carbon",
        "metrics": {
            "total_golden_tests": 123,
            "unit_tests_total": 123,
            "unit_tests_passed": 123,
            "unit_tests_pass_rate": 100.0,
            "sast_critical_violations": 0,
            "rsi_residual_delta": 0,
        },
        "invariants": {"require_100_percent_test_pass": True},
        "history": [],
    }
    baseline_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    sast_regressed = {
        "unit_tests_total": 123,
        "unit_tests_passed": 123,
        "sast_critical_violations": 1,
        "rsi_residual_delta": 0,
    }
    assert check_baseline_compliance(str(baseline_file), sast_regressed)["verdict"] == "FAIL"

    delta_regressed = {
        "unit_tests_total": 123,
        "unit_tests_passed": 123,
        "sast_critical_violations": 0,
        "rsi_residual_delta": 5,
    }
    assert check_baseline_compliance(str(baseline_file), delta_regressed)["verdict"] == "FAIL"

    assert (
        call_script_main(baseline_mod, ["--file", str(baseline_file), "--recalibrate"], monkeypatch)
        == 1
    )
    assert (
        call_script_main(
            baseline_mod,
            ["--file", str(baseline_file), "--recalibrate", "--target-tests", "125"],
            monkeypatch,
        )
        == 0
    )
    recal_loaded = load_baseline(str(baseline_file))
    assert recal_loaded["metrics"]["total_golden_tests"]["value"] == 125


@pytest.mark.fast
def test_wp_r0_honesty_recalibrated_strip_and_oracle_lock_sha_mismatch(
    tmp_path: Path,
) -> None:
    """3. Verifica gate WP-R0: vettore non misurato < 90, strip _recalibrated e mismatch SHA oracle_lock."""
    unmeasured_ipc = ipc_mod.RSIDefectVector()
    unmeasured_rsi = rsi_mod.RSIDefectVector()
    assert unmeasured_ipc.effective_totals() == (0, 0)
    assert unmeasured_rsi.effective_totals() == (0, 0)
    assert rsi_mod.compute_fitness(unmeasured_rsi) < 90.0

    _, sample_test, _, bl_file = _write_sample_lock_ws(tmp_path)
    downward = update_baseline_metrics(
        str(bl_file),
        {"_recalibrated": True, "total_golden_tests": 95, "unit_tests_total": 95, "unit_tests_passed": 95},
    )
    assert downward["verdict"] == "FAIL" and downward["status"] == "REJECTED"

    upward = update_baseline_metrics(
        str(bl_file),
        {
            "_recalibrated": True,
            "total_golden_tests": 121,
            "unit_tests_total": 121,
            "unit_tests_passed": 121,
            "sast_critical_violations": 0,
        },
    )
    assert upward["verdict"] == "PASS"
    assert "_recalibrated" not in load_baseline(str(bl_file))

    sample_test.write_text("def test_ok():\n    assert False\n", encoding="utf-8")
    tampered_res = check_baseline_compliance(
        str(bl_file),
        {"total_golden_tests": 121, "unit_tests_total": 121, "unit_tests_passed": 121, "sast_critical_violations": 0},
    )
    assert tampered_res["verdict"] == "FAIL"
    assert any(r.get("metric") == "oracle_lock_integrity" for r in tampered_res.get("regressions", []))


@pytest.mark.fast
def test_oracle_lock_fail_closed_on_non_hex_and_missing_combined_sha(
    tmp_path: Path,
) -> None:
    """4. Verifica fail-closed di _verify_oracle_lock_coherence su digest non-64-hex e combined_sha256 assente."""
    _, sample_test, lock_file, bl_file = _write_sample_lock_ws(tmp_path, "lock_sec")
    real_sha = hashlib.sha256(sample_test.read_bytes()).hexdigest()
    ok_metrics = {
        "total_golden_tests": 120,
        "unit_tests_total": 120,
        "unit_tests_passed": 120,
        "sast_critical_violations": 0,
    }
    assert baseline_mod._verify_oracle_lock_coherence(str(bl_file)) == []

    for bad_digest in ("tampered", "", None, 123, "g" * 64):
        files_bad = {"test_sample.py": bad_digest}
        comb_sha = hashlib.sha256(json.dumps(files_bad, sort_keys=True).encode("utf-8")).hexdigest()
        lock_file.write_text(json.dumps({"files": files_bad, "combined_sha256": comb_sha}), encoding="utf-8")
        anomalies = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
        assert len(anomalies) >= 1
        assert anomalies[0]["metric"] == "oracle_lock_integrity"
        assert check_baseline_compliance(str(bl_file), ok_metrics)["verdict"] == "FAIL"

    for bad_comb in (None, "", "bad_combined", 999, "f" * 64):
        payload: dict[str, Any] = {"files": {"test_sample.py": real_sha}}
        if bad_comb is not None:
            payload["combined_sha256"] = bad_comb
        lock_file.write_text(json.dumps(payload), encoding="utf-8")
        anomalies = baseline_mod._verify_oracle_lock_coherence(str(bl_file))
        assert len(anomalies) >= 1
        assert anomalies[0]["metric"] == "oracle_lock_integrity"
        assert check_baseline_compliance(str(bl_file), ok_metrics)["verdict"] == "FAIL"


@pytest.mark.fast
def test_measure_live_pytest_metrics_with_coverage_and_cli(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """5. Verifica measure_live_pytest_metrics(..., with_coverage=True) e CLI --with-coverage senza residui."""
    cov_ws = tmp_path / "cov_ws"
    (cov_ws / "scripts").mkdir(parents=True)
    (cov_ws / "tests").mkdir(parents=True)
    (cov_ws / "nk_tracking").mkdir(parents=True)
    (cov_ws / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (cov_ws / "scripts" / "sample_calc.py").write_text(
        "def add_pos(x: int) -> int:\n    if x > 0:\n        return x * 2\n    return -x\n",
        encoding="utf-8",
    )
    (cov_ws / "tests" / "test_sample_calc.py").write_text(
        "import pytest\nfrom scripts.sample_calc import add_pos\n\n"
        "@pytest.mark.parametrize('n', list(range(1, 94)))\n"
        "def test_pos(n: int) -> None:\n    assert add_pos(n) == n * 2\n",
        encoding="utf-8",
    )
    bl_file = cov_ws / "nk_tracking" / "quality_baseline.json"
    bl_file.write_text(
        json.dumps(
            {
                "_version": "6.4.0-Carbon",
                "metrics": {
                    "total_golden_tests": {"value": 93, "direction": "higher_is_better"},
                    "unit_tests_total": {"value": 93, "direction": "higher_is_better"},
                    "unit_tests_passed": {"value": 93, "direction": "higher_is_better"},
                    "branch_coverage_pct": {"value": 85.69, "direction": "higher_is_better"},
                    "pytest_duration_s": {"value": 10.0, "threshold_max": 60.0, "direction": "lower_is_better"},
                },
            }
        ),
        encoding="utf-8",
    )
    sys_tmp = Path(tempfile.gettempdir())
    before_dirs = {p.name for p in sys_tmp.glob("nk_qbm_cov_*")}

    def _fake_pytest_run(cmd: list[str], **_kw: Any) -> SimpleNamespace:
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith("--cov-report=json:"):
                cov_out = Path(arg.split(":", 1)[1])
                cov_out.write_text(
                    json.dumps(
                        {
                            "totals": {
                                "num_statements": 4,
                                "covered_lines": 4,
                                "num_branches": 2,
                                "covered_branches": 1,
                                "percent_statements_covered": 100.0,
                                "percent_branches_covered": 50.0,
                                "percent_covered": 83.33,
                            }
                        }
                    ),
                    encoding="utf-8",
                )
        return SimpleNamespace(returncode=0, stdout="93 passed in 0.05s\n", stderr="")

    monkeypatch.setattr(baseline_mod, "subprocess", SimpleNamespace(run=_fake_pytest_run))
    monkeypatch.setenv("COV_CORE_SOURCE", "scripts")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    live = baseline_mod.measure_live_pytest_metrics(cov_ws, with_coverage=True)
    assert live["unit_tests_passed"] == 93 and live["pass_rate_pct"] == 100.0
    assert live["statement_coverage_pct"] > 0.0
    assert 0.0 < live["true_branch_coverage_pct"] < 100.0
    assert live["combined_coverage_pct"] > 0.0
    assert "branch_coverage_pct" not in live

    rc = call_script_main(
        baseline_mod,
        ["check", "--file", str(bl_file), "--live", "--with-coverage", "--json"],
        monkeypatch,
    )
    assert rc == 0
    cli_out = json.loads(capsys.readouterr().out)
    assert cli_out["verdict"] == "PASS"
    assert cli_out["live_metrics"]["true_branch_coverage_pct"] == live["true_branch_coverage_pct"]
    assert {p.name for p in sys_tmp.glob("nk_qbm_cov_*")} <= before_dirs


@pytest.mark.fast
def test_live_with_coverage_fail_closed_and_branch_regression(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """6. Verifica fail-closed su --with-coverage privo di JSON e regressione true_branch_coverage_pct."""
    bl_file = tmp_path / "cov_gate_bl.json"
    bl_file.write_text(
        json.dumps(
            {
                "_version": "6.4.0-Carbon",
                "metrics": {
                    "total_golden_tests": {"value": 93, "direction": "higher_is_better"},
                    "unit_tests_total": {"value": 93, "direction": "higher_is_better"},
                    "unit_tests_passed": {"value": 93, "direction": "higher_is_better"},
                    "true_branch_coverage_pct": {"value": 88.5, "direction": "higher_is_better"},
                },
            }
        ),
        encoding="utf-8",
    )
    no_cov_metrics = {
        "total_golden_tests": 95,
        "unit_tests_total": 95,
        "unit_tests_passed": 95,
        "pass_rate_pct": 100.0,
        "failed_tests": 0,
    }
    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: dict(no_cov_metrics))
    assert call_script_main(
        baseline_mod, ["check", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch
    ) == 1
    out_miss = json.loads(capsys.readouterr().out)
    assert out_miss["verdict"] == "FAIL" and out_miss["status"] == "ERROR"
    assert call_script_main(
        baseline_mod, ["update", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch
    ) == 1
    out_upd = json.loads(capsys.readouterr().out)
    assert out_upd["verdict"] == "FAIL" and out_upd["status"] == "REJECTED"

    low_cov = dict(no_cov_metrics, true_branch_coverage_pct=82.0)
    monkeypatch.setattr(baseline_mod, "measure_live_pytest_metrics", lambda *_a, **_k: dict(low_cov))
    assert call_script_main(
        baseline_mod, ["check", "--file", str(bl_file), "--live", "--with-coverage", "--json"], monkeypatch
    ) == 1
    out_reg = json.loads(capsys.readouterr().out)
    assert out_reg["verdict"] == "FAIL"
    assert any(r.get("metric") == "true_branch_coverage_pct" for r in out_reg.get("regressions", []))


@pytest.mark.fast
def test_skills_golden_eval_set_alignment_catalog() -> None:
    """7. Verifica allineamento 11/11 delle skill su skill_golden_eval_set.json 1.0.0-Generation e STE100."""
    eval_path = _resolve_overlay_file("tests/evals/skill_golden_eval_set.json")
    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))

    assert eval_data["schema_version"] == "1.0.0-Generation"
    assert eval_data["milestone_anchor_id"] == "NK-GEN-1.0.0"
    assert eval_data["global_invariants"]["required_version_tag"] == "1.0.0-Generation"
    assert eval_data["global_invariants"]["required_section"] == "<rsi_micro_loop>"
    skills = eval_data["skills"]
    assert len(skills) == 11

    env_tok = "%" + "TEMP%"
    for entry in skills:
        req_subs = entry["required_substrings"]
        assert not any(env_tok in sub for sub in req_subs), f"Literal env path in {entry['name']}"
        skill_file = _resolve_overlay_file(entry["skill_path"])
        assert skill_file.is_file(), f"Missing skill file: {skill_file}"
        text = skill_file.read_text(encoding="utf-8")
        assert "1.0.0-Generation" in text, f"Version tag missing in {entry['name']}"
        for sub in req_subs:
            assert sub in text, f"Missing '{sub}' in {entry['name']}"
        ste_res = rsi_mod.verify_ste100_compliance(text, max_sentence_words=20)
        assert ste_res["passed"] is True, f"STE100 failed in {entry['name']}: {ste_res['violations']}"

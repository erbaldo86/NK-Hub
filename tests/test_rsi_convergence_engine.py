# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per il motore Bounded-RSI e Guardie G1..G6, Q_v2(S_k), P0-01/P0-02.
Modulo: tests/test_rsi_convergence_engine.py.
Valida monotonia Delta_k/Q(S_k), Q_v2(S_k), RSIProfileRegistry, G1..G6, report gate e duration_s.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Tuple

import pytest
from conftest import (
    call_script_main_captured,
    load_nk_script_module,
    load_script_by_relpath,
)

rsi_mod = load_nk_script_module("rsi_convergence_engine")
bav_mod = load_script_by_relpath(
    "rsi_bav_benchmark",
    "scripts/_internal/rsi_convergence_engine/benchmark_and_vibe.py",
)
eco_mod = load_script_by_relpath(
    "rsi_eco_verify",
    "scripts/_internal/rsi_convergence_engine/ecosystem_verify.py",
)
gt14_mod = load_script_by_relpath(
    "rsi_gt14_probes",
    "scripts/_internal/rsi_convergence_engine/gt14_probes.py",
)
from _internal.rsi_convergence_engine import (  # noqa: E402
    constants as rsi_const,
    eco_audits as rsi_eco_aud,
    engine as rsi_engine,
    gt14_probes as rsi_probes,
    loop_and_cove as rsi_loop,
    profiles as rsi_profiles,
    vibe_report_helpers as rsi_vrh,
)

RSIConvergenceEngine = rsi_mod.RSIConvergenceEngine
RSIDefectVector = rsi_mod.RSIDefectVector
compute_delta = rsi_mod.compute_delta
compute_fitness = rsi_mod.compute_fitness
verify_ste100_compliance = rsi_mod.verify_ste100_compliance


def _new_staged_engine(ws_root: Path, monkeypatch: Any) -> Any:
    """Istanzia RSIConvergenceEngine collegato ai moduli .staging/ pre-promozione."""
    engine = RSIConvergenceEngine(workspace_root=ws_root, root=ws_root)
    monkeypatch.setattr(
        engine,
        "run_benchmark_suite",
        lambda suite, root_dir=None: bav_mod.run_benchmark_suite_impl(
            engine, suite, root_dir=root_dir
        ),
    )
    monkeypatch.setattr(
        engine,
        "verify_ecosystem",
        lambda *a, **kw: eco_mod.verify_ecosystem_impl(engine, *a, **kw),
    )
    monkeypatch.setattr(
        engine,
        "emit_gt14_bundle",
        lambda **kw: gt14_mod.emit_gt14_bundle_impl(engine, **kw),
    )
    return engine


def _make_conf11_workspace(tmp_path: Path) -> Path:
    """Crea un workspace minimo con documentazione STE100 conforme e script sano."""
    prof_ws = tmp_path / "conf11_verify_ws"
    (prof_ws / ".agents").mkdir(parents=True)
    (prof_ws / "nk_tracking").mkdir(parents=True)
    (prof_ws / "scripts").mkdir(parents=True)
    (prof_ws / ".agents" / "guide.md").write_text(
        "# Guida Tecnica\n\nQuesta frase attiva rispetta lo standard.\n",
        encoding="utf-8",
    )
    (prof_ws / "scripts" / "ok_mod.py").write_text("VALUE = 42\n", encoding="utf-8")
    return prof_ws


@pytest.mark.fast
def test_rsi_delta_monotonicity_profiles_and_p6() -> None:
    """Verifica monotonia Delta_k/Q(S_k), i profili P1..P5 di RSIProfileRegistry e profilo P6 refactor_rsi."""
    v_high = RSIDefectVector(
        sast_critical=1, tests_failed=2, tests_passed=98, tests_total=100,
        contract_violations=1, high_findings=1, medium_findings=2, low_findings=1, doc_drift=1,
    )
    v_mid = RSIDefectVector(
        sast_critical=0, tests_failed=1, tests_passed=99, tests_total=100,
        high_findings=1, medium_findings=1,
    )
    v_zero = RSIDefectVector(tests_passed=100, tests_total=100)

    d_high = compute_delta(v_high)
    d_mid = compute_delta(v_mid)
    d_zero = compute_delta(v_zero)
    assert d_high > d_mid > d_zero == 0

    q_high = compute_fitness(v_high, d_high)
    q_mid = compute_fitness(v_mid, d_mid)
    q_zero = compute_fitness(v_zero, d_zero)
    assert q_high < q_mid < q_zero == 100.0

    profiles = rsi_mod.RSIProfileRegistry.list_profiles()
    assert {"vibe_sprint_micro_rsi", "code_rsi", "spec_rsi", "ui_ux_rsi", "ste100_rsi"}.issubset(set(profiles))

    v_doc = RSIDefectVector(doc_drift=3, low_findings=2, tests_passed=100, tests_total=100)
    d_code = compute_delta(v_doc, profile="code_rsi")
    d_ste = compute_delta(v_doc, profile="ste100_rsi")
    assert d_ste > d_code > 0

    cfg_p6 = rsi_profiles.RSIProfileRegistry.get("refactor_rsi")
    assert cfg_p6.profile_id == "P6"
    vec_p6 = RSIDefectVector(tests_passed=8, tests_total=8)
    delta_p6 = compute_delta(vec_p6, profile="refactor_rsi")
    assert delta_p6 == 0 and compute_fitness(vec_p6, delta_k=delta_p6, profile="refactor_rsi") == 100.0


@pytest.mark.integration
def test_rsi_guardrails_g1_g2_g3_rollback_and_strict_monotonic(tmp_path: Path) -> None:
    """Verifica arresto immediato G1 (Delta_0==0), cicli G3 e rollback atomico G2 con strict_monotonic."""
    target_g1 = tmp_path / "clean_mod.py"
    target_g1.write_text("X = 1\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"
    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    rep_g1 = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: RSIDefectVector(tests_passed=100, tests_total=100),
        refine_fn=lambda cycle, defects: True,
        target_files=[target_g1], mode="mode_a", session_id="test_g1",
    )
    assert rep_g1.converged is True and rep_g1.iterations_used == 0 and rep_g1.final_status == "CONVERGED_OPTIMAL"

    target_g3 = tmp_path / "module_g3.py"
    target_g3.write_text("STATE = 'A'\n", encoding="utf-8")
    rep_g3 = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: RSIDefectVector(high_findings=2, tests_passed=100, tests_total=100),
        refine_fn=lambda cycle, defects: bool(target_g3.write_text("STATE = 'A'\n", encoding="utf-8")),
        target_files=[target_g3], mode="mode_a", session_id="test_g3",
    )
    assert rep_g3.converged is False and rep_g3.cycle_detected is True and rep_g3.final_status == "HALTED_CYCLE_DETECTED"

    v_prev = RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
    v_curr = RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
    assert RSIConvergenceEngine.check_hard_gate_regression(v_prev, v_curr, strict_monotonic=False)[0] is False
    reg_strict, reason = RSIConvergenceEngine.check_hard_gate_regression(v_prev, v_curr, strict_monotonic=True)
    assert reg_strict is True and "strict_monotonic" in reason

    target_g2 = tmp_path / "module_g2.py"
    target_g2.write_text("VAL = 10\n", encoding="utf-8")
    eng_g2 = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=tmp_path / "rsi_tel_g2.jsonl")

    def eval_regressing(iteration: int = 0) -> RSIDefectVector:
        if iteration == 0:
            return RSIDefectVector(tests_failed=1, tests_passed=99, tests_total=100)
        return RSIDefectVector(sast_critical=1, tests_failed=3, tests_passed=97, tests_total=100)

    report_g2 = eng_g2.run_convergence_loop(
        evaluate_fn=eval_regressing,
        refine_fn=lambda cycle, defects: bool(target_g2.write_text(f"VAL = {990 + cycle}\n", encoding="utf-8")),
        target_files=[target_g2], mode="mode_c", session_id="test_g2",
    )
    assert report_g2.converged is False and report_g2.rollbacks_count >= 1
    assert report_g2.history[-1].verdict == "ROLLED_BACK_HARD_GATE"
    assert target_g2.read_text(encoding="utf-8") == "VAL = 10\n"


@pytest.mark.integration
def test_rsi_guardrail_g4_hash_chain_and_win32_mutex_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica integrita catena SHA-256 G4, rilevamento manomissioni e mutex Win32 fail-closed."""
    target = tmp_path / "module_g4.py"
    target.write_text("V = 1\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"
    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    report = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: (
            RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
            if iteration == 0 else RSIDefectVector(medium_findings=0, tests_passed=100, tests_total=100)
        ),
        refine_fn=lambda cycle, defects: bool(target.write_text("V = 2\n", encoding="utf-8")),
        target_files=[target], mode="mode_a", session_id="test_g4",
    )
    assert report.converged is True
    valid, count, _ = engine.verify_telemetry_chain(telemetry)
    assert valid is True and count >= 2

    lines = telemetry.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["delta_k"] = 999
    lines[0] = json.dumps(tampered)
    telemetry.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert engine.verify_telemetry_chain(telemetry)[0] is False

    tel_p = tmp_path / "rsi_tel_w0.jsonl"
    eng_w0 = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=tel_p)
    assert eng_w0._get_last_telemetry_hash() == "0" * 64
    r1 = eng_w0.append_telemetry_record(rsi_mod.RSIIterationRecord(iteration=0, session_id="w0", state_hash="h0", delta_k=2, fitness_q=80.0, verdict="CONTINUE"))
    r2 = eng_w0.append_telemetry_record(rsi_mod.RSIIterationRecord(iteration=1, session_id="w0", state_hash="h1", delta_k=0, fitness_q=100.0, verdict="CONVERGED"))
    assert r2.prev_hash == r1.record_hash and eng_w0._get_last_telemetry_hash() == r2.record_hash
    assert eng_w0.verify_telemetry_chain(tel_p)[0] is True

    with monkeypatch.context() as mp_mtx:
        mp_mtx.setattr(sys, "platform", "win32")
        mp_mtx.setattr(rsi_loop, "create_or_open_named_mutex", lambda *_a, **_k: (None, False, "timeout"))
        with pytest.raises(RuntimeError, match="mutex Win32"):
            eng_w0.append_telemetry_record(rsi_mod.RSIIterationRecord(iteration=2, session_id="w0", state_hash="h2", delta_k=0, fitness_q=100.0, verdict="CONVERGED"))


def _assert_vibe_check_cove_and_grounding(tmp_path: Path, engine: RSIConvergenceEngine) -> None:
    clean_file = tmp_path / "clean_vibe.py"
    clean_file.write_text('"""Modulo sicuro."""\ndef add_vals(a: int, b: int) -> int:\n    return a + b\n', encoding="utf-8")
    res_ok = engine.run_vibe_check(clean_file)
    assert (res_ok["passed"], res_ok["delta_k"]) == (True, 0)

    bad_file = tmp_path / "unsafe_vibe.py"
    bad_file.write_text("def run_unsafe(x: str):\n    return " + "ev" + "al(x)\n", encoding="utf-8")
    res_bad = engine.run_vibe_check(bad_file)
    assert res_bad["passed"] is False
    assert res_bad["delta_k"] > 0

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    wf_dir = tmp_path / ".agents" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "sample_tool.py").write_text(
        "import argparse\ndef main():\n    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--valid-flag', action='store_true')\n    p.parse_args()\n",
        encoding="utf-8",
    )
    wf_file = wf_dir / "sample.md"
    wf_file.write_text("Esegui `python scripts/sample_tool.py --valid-flag` per verificare.\n", encoding="utf-8")
    assert engine.verify_cli_flags_cove(tmp_path)["passed"] is True

    wf_file.write_text("Esegui `python scripts/sample_tool.py --ghost-flag` per verificare.\n", encoding="utf-8")
    res_cove_bad = engine.verify_cli_flags_cove(tmp_path)
    assert res_cove_bad["passed"] is False
    assert "--ghost-flag" in res_cove_bad["invalid_flags"][0]
    assert compute_delta(RSIDefectVector(poc_confirmed_exploits=1)) >= 20

    rep_dir = tmp_path / "nk_tracking" / "reports_and_briefs"
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / "tas_certification_report_test.md").write_text("| Modulo | Stato |\n| scripts/owasp_sast_scanner.py | CERTIFIED |\n", encoding="utf-8")
    eco_res = engine.verify_ecosystem()
    assert eco_res["checks"]["tas_report_grounding"]["hallucinated_refs"] >= 1
    assert eco_res["checks"]["tas_report_grounding"]["passed"] is False


def _assert_conf11_explicit_profiles_and_target(tmp_path: Path, capsys: Any) -> Path:
    conf_file = tmp_path / "conf11_target.py"
    conf_file.write_text('"""Modulo CONF-11."""\ndef square_val(n: int) -> int:\n    return n * n\n', encoding="utf-8")
    capsys.readouterr()
    assert rsi_mod.main(["--vibe-check", str(conf_file), "--profile", "code_rsi", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["profile"] == "code_rsi"
    assert rsi_mod.main(["--vibe-check", str(conf_file), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["profile"] == "vibe_sprint_micro_rsi"

    prof_ws = _make_conf11_workspace(tmp_path)
    guide_p = prof_ws / ".agents" / "guide.md"
    for explicit_prof in ("ste100_rsi", "code_rsi"):
        assert rsi_mod.main(["--root", str(prof_ws), "--vibe-check", str(guide_p), "--profile", explicit_prof, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["profile"] == explicit_prof
        rc_vp = rsi_mod.main(["--root", str(prof_ws), "--verify", "--profile", explicit_prof, "--json"])
        out_vp = json.loads(capsys.readouterr().out)
        assert (rc_vp, out_vp["status"], out_vp["profile"]) == (2, "UNMEASURED", explicit_prof)

    (prof_ws / ".staging" / "scripts").mkdir(parents=True)
    (prof_ws / ".staging" / "scripts" / "ok_mod.py").write_text("VALUE = 42\n", encoding="utf-8")
    no_stg_ws = tmp_path / "no_stg_cli"
    (no_stg_ws / ".agents").mkdir(parents=True)
    assert rsi_engine._resolve_vibe_target(prof_ws, ".") == str(prof_ws)
    assert rsi_engine._resolve_vibe_target(no_stg_ws, ".") == str(no_stg_ws / ".agents")
    return prof_ws


def _assert_cli_canary_fail_closed(
    tmp_path: Path, prof_ws: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from _internal.rsi_convergence_engine import canary_holdout as _ch

    with monkeypatch.context() as mp_cli:
        canary_dir = tmp_path / "cli_canary"
        mp_cli.setenv("NK_HOLDOUT_DIR", str(canary_dir))
        assert rsi_engine.run_rsi_cli(["--root", str(prof_ws), "--verify-canary"]) == 1
        capsys.readouterr()
        _ch.ensure_canary_holdout_file(holdout_dir=canary_dir)
        assert rsi_engine.run_rsi_cli(["--root", str(prof_ws), "--verify-canary"]) == 0
    capsys.readouterr()


def _assert_cli_canary_ab_retired_and_verify_flags(
    tmp_path: Path, prof_ws: Path, engine: RSIConvergenceEngine, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    _assert_cli_canary_fail_closed(tmp_path, prof_ws, monkeypatch, capsys)

    assert (engine.run_ab_benchmark()["status"], engine.run_ab_benchmark()["passed"]) == ("RETIRED", False)
    ret_mod = rsi_engine.run_ab_benchmark(workspace_root=tmp_path)
    assert (ret_mod["status"], ret_mod["passed"]) == ("RETIRED", False)
    assert "pytest reale" in ret_mod["details"]
    assert rsi_engine.run_rsi_cli(["--root", str(prof_ws), "--ab-benchmark"]) == 1
    ab_cli = json.loads(capsys.readouterr().out)
    assert (ab_cli["status"], ab_cli["passed"]) == ("RETIRED", False)

    assert rsi_engine.run_rsi_cli(["--root", str(prof_ws), "--vibe-check", str(prof_ws / ".staging" / "scripts" / "ok_mod.py")]) == 0
    assert "RSI-VIBE-CHECK" in capsys.readouterr().out
    assert rsi_engine.run_rsi_cli(["--root", str(prof_ws), "--verify", "--scan-prod-frontend"]) in (0, 1, 2)
    assert "RSI-VERIFY" in capsys.readouterr().out
    assert rsi_engine.run_rsi_cli(["--root", str(prof_ws), "--emit-gt14-bundle", "--bundle-output", str(tmp_path / "cli_b.json")]) in (0, 1)
    assert "GT14-BUNDLE" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        rsi_engine.run_rsi_cli(["--unknown-flag-invalid"])


@pytest.mark.integration
def test_rsi_vibe_check_cove_conf11_and_cli_subcommands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Verifica run_vibe_check, CoVe CLI AST, CONF-11, subcommand CLI, AB RETIRED e flag errati."""
    engine = RSIConvergenceEngine(workspace_root=tmp_path)
    _assert_vibe_check_cove_and_grounding(tmp_path, engine)
    prof_ws = _assert_conf11_explicit_profiles_and_target(tmp_path, capsys)
    _assert_cli_canary_ab_retired_and_verify_flags(tmp_path, prof_ws, engine, monkeypatch, capsys)


@pytest.mark.integration
def test_rsi_emit_gt14_bundle_and_probe_loader_fallback(tmp_path: Path) -> None:
    """Verifica struttura offline emit_gt14_bundle, _load_probe_module e fallback verify_ecosystem_impl."""
    bundle_ws = tmp_path / "gt14_bundle_ws"
    (bundle_ws / ".agents").mkdir(parents=True, exist_ok=True)
    bundle_out = tmp_path / "gt14_bundle_out.json"
    engine = RSIConvergenceEngine(workspace_root=bundle_ws, root=bundle_ws)
    bundle_res = engine.emit_gt14_bundle(
        workspace_root=bundle_ws, with_dast=False, strict_verify=False, output_path=bundle_out,
    )
    assert bundle_out.is_file()
    saved_bundle = json.loads(bundle_out.read_text(encoding="utf-8"))
    assert saved_bundle["probes_executed"] == 5 and saved_bundle["with_dast"] is False
    assert set(saved_bundle["probes"].keys()) == {"registry_verify", "preflight_check", "ast_guard", "rsi_verify", "quality_baseline", "dast_overlay"}
    assert saved_bundle["probes"]["dast_overlay"]["skipped"] is True
    assert saved_bundle["probes"]["ast_guard"]["skipped"] is True
    assert bundle_res["bundle_path"] == str(bundle_out.resolve())

    ws = tmp_path / "gt14_loader_ws"
    stg_scripts = ws / ".staging" / "scripts"
    stg_scripts.mkdir(parents=True)
    (stg_scripts / "sample_gt14_probe.py").write_bytes(b"VAL = 77\n")

    sys.modules.pop("sample_gt14_probe", None)
    sys.path = [p for p in sys.path if Path(p).resolve() != stg_scripts.resolve()]
    loaded_first = gt14_mod._load_probe_module(ws, "sample_gt14_probe")
    assert loaded_first.VAL == 77
    assert gt14_mod._load_probe_module(ws, "sample_gt14_probe") is loaded_first
    assert gt14_mod._load_probe_module(ws, "json") is json
    sys.modules.pop("sample_gt14_probe", None)

    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nFrase breve conforme.\n", encoding="utf-8")

    class _NarrowEngine(RSIConvergenceEngine):
        def verify_ecosystem(  # type: ignore[override]
            self, root_dir=None, run_pytest=False, strict_verify=False, test_report=None
        ):
            return super().verify_ecosystem(
                root_dir=root_dir, run_pytest=run_pytest, strict_verify=strict_verify, test_report=test_report
            )

    narrow = _NarrowEngine(workspace_root=ws, root=ws)
    res_fb = gt14_mod._invoke_rsi_verify_for_bundle(
        narrow, ws, False, None,
        {"passed": True, "status": "PASS", "is_dry_run": False},
        {"passed": True, "kill_rate": 1.0, "mutants_killed": 1, "mutants_total": 1},
        ["scripts/*.py"], True,
    )
    assert res_fb["checks"]["dast_report"]["passed"] is True
    assert res_fb["checks"]["mutation_gate"]["passed"] is True


def _assert_eco_prop_and_dry_run(tmp_path: Path, monkeypatch: Any) -> None:
    from _internal.win32_2pc_engine.staging_guards import TwoPhaseCommitError, validate_sandbox_report_not_dry_run

    ws = tmp_path / "eco_prop_ws"
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nFrase breve conforme.\n", encoding="utf-8")
    engine = _new_staged_engine(ws, monkeypatch)

    eco = engine.verify_ecosystem(
        root_dir=ws,
        test_report={
            "tests_passed": 4, "tests_failed": 0, "tests_total": 4,
            "duration_s": 1.37, "branch_coverage_pct": 86.4, "statement_coverage_pct": 91.2,
        },
    )
    assert (eco["duration_s"], eco["checks"]["benchmark_suite"]["duration_s"]) == (1.37, 1.37)
    assert (eco["checks"]["benchmark_suite"]["branch_coverage_pct"], eco["checks"]["benchmark_suite"]["statement_coverage_pct"]) == (86.4, 91.2)
    miss_res = engine.run_benchmark_suite(ws / "missing_tests", root_dir=ws)
    assert (miss_res["executed"], miss_res["duration_s"]) == (False, None)

    with pytest.raises(TwoPhaseCommitError):
        validate_sandbox_report_not_dry_run({"status": "DRY_RUN", "is_dry_run": True})
    dry_report_path = tmp_path / "dast_dry_run.json"
    dry_report_path.write_text(json.dumps({"status": "DRY_RUN", "is_dry_run": True, "passed": True}), encoding="utf-8")
    with pytest.raises(TwoPhaseCommitError):
        validate_sandbox_report_not_dry_run(dry_report_path)
    validate_sandbox_report_not_dry_run({"status": "PASS", "is_dry_run": False})

    eco_dry = eco_mod.verify_ecosystem_impl(engine, root_dir=ws, dast_report=dry_report_path)
    assert "UNMEASURED_DRY_RUN" in eco_dry["unmeasured_components"]
    assert (eco_dry["status"], eco_dry["passed"]) == ("UNMEASURED", False)


def _assert_p2_scope_and_p0_02_root_norm(tmp_path: Path) -> None:
    import inspect
    from _internal.nk_common.thresholds import _safe_pos_int, load_saturation_thresholds

    assert {"allowed_files", "scan_prod_frontend"}.issubset(inspect.signature(RSIConvergenceEngine.verify_ecosystem).parameters.keys())
    expected_bundle_params = {"mutation_report", "dast_report", "allowed_files", "scan_prod_frontend"}
    assert expected_bundle_params.issubset(inspect.signature(RSIConvergenceEngine.emit_gt14_bundle).parameters.keys())
    assert expected_bundle_params.issubset(inspect.signature(rsi_mod.emit_gt14_bundle).parameters.keys())

    scope_ws = tmp_path / "p2_scope_ws"
    (scope_ws / ".agents").mkdir(parents=True)
    (scope_ws / ".agents" / "guide.md").write_text("# Guida\nFrase breve conforme.\n", encoding="utf-8")
    (scope_ws / "scripts").mkdir(parents=True)
    (scope_ws / "scripts" / "allowed.py").write_text("A = 1\n", encoding="utf-8")
    (scope_ws / ".staging" / "scripts").mkdir(parents=True)
    (scope_ws / ".staging" / "scripts" / "unlisted.py").write_text("def extra_fn() -> int:\n    return 2\n", encoding="utf-8")
    (scope_ws / "nk_tracking").mkdir(parents=True)

    eng_scope = RSIConvergenceEngine(workspace_root=scope_ws, root=scope_ws)
    eco_scope = eng_scope.verify_ecosystem(root_dir=scope_ws, allowed_files="scripts/allowed.py", scan_prod_frontend=True)
    assert eco_scope["checks"]["quality_diff_and_frontend"]["semantic_drift_findings"] >= 1
    assert "unlisted.py" in str(eco_scope["checks"]["quality_diff_and_frontend"]["violations"])
    assert "unlisted.py" in str(eco_scope["violations"])

    bundle_scope = rsi_mod.emit_gt14_bundle(
        workspace_root=scope_ws, with_dast=False, strict_verify=False,
        output_path=tmp_path / "p2_gt14_bundle.json", allowed_files="scripts/allowed.py", scan_prod_frontend=True,
    )
    assert bundle_scope["probes"]["rsi_verify"]["checks"]["quality_diff_and_frontend"]["semantic_drift_findings"] >= 1

    hub_ws = tmp_path / "NK_Hub"
    (hub_ws / "scripts").mkdir(parents=True)
    target_py = hub_ws / "scripts" / "target_p02.py"
    target_py.write_text("X = 1\n", encoding="utf-8")
    assert rsi_const.normalize_rel_for_root(hub_ws, "NK_Hub/NK_Hub/scripts/target_p02.py") == "scripts/target_p02.py"
    assert rsi_const.resolve_candidate_impl(hub_ws, "NK_Hub/scripts/target_p02.py") == target_py
    assert bav_mod.root_root_join(hub_ws, Path("NK_Hub/scripts/target_p02.py")) == target_py

    captured_kwargs: dict[str, Any] = {}

    class _FakeDastMod:
        @staticmethod
        def run_staging_shadow_verification(**kwargs: Any) -> dict[str, Any]:
            captured_kwargs.update(kwargs)
            return {"passed": True, "status": "PASS", "is_dry_run": False}

    dast_res, _ = rsi_probes._run_dast_probe(hub_ws, hub_ws / ".staging", True, lambda _r, _n: _FakeDastMod)
    assert (dast_res["passed"], captured_kwargs.get("verify_holdout")) == (True, True)

    cfg_dir = tmp_path / "nk_genome" / "configs"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "saturation_thresholds.json").write_text(json.dumps({"autonomous_context_shield": {"z3_tokens": 100000}}), encoding="utf-8")
    loaded_th = load_saturation_thresholds(workspace_root=tmp_path)
    assert (_safe_pos_int(loaded_th["autonomous_context_shield"]["z3_tokens"], 205000), _safe_pos_int("bad", 205000)) == (100000, 205000)


@pytest.mark.integration
def test_rsi_ecosystem_verify_propagation_dry_run_p2_and_p0_02(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica propagazione duration_s/coverage, blocco dry-run P0-BUG-02, P2 forwarding e fix P0-02."""
    _assert_eco_prop_and_dry_run(tmp_path, monkeypatch)
    _assert_p2_scope_and_p0_02_root_norm(tmp_path)


def _assert_s3b_baseline_and_cove(ws: Path, eng: Any) -> Tuple[Path, str]:
    (ws / "scripts" / "core_api.py").write_text("def keep_api(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "core_api.py").write_text("def other_api() -> int:\n    return 1\n", encoding="utf-8")
    (ws / "scripts" / "_internal" / "pkg" / "mod.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--mode')\np.add_argument('--flag')\n",
        encoding="utf-8",
    )
    (ws / "scripts" / "schemas" / "contracts.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--schema-ok')\n",
        encoding="utf-8",
    )

    res_fix1 = eng.run_vibe_check(ws / ".staging" / "scripts" / "core_api.py")
    assert res_fix1["passed"] is False
    assert res_fix1["delta_k"] > 0
    assert any("keep_api" in v for v in res_fix1["violations"])

    long_ste = (
        "[RULE-STE100]\n"
        "Questa frase intenzionalmente supera il limite massimo di venti parole "
        "previsto dallo standard con un trattino \u2014 spaziato vietato.\n"
    )
    bad_skill = ws / ".agents" / "skills" / "NK-Sample" / "SKILL.md"
    bad_skill.write_text(
        "---\nname: NK-Sample\nversion: '1.0.0-Generation'\n---\n"
        + long_ste
        + 'Esegui `python "dir with spaces/scripts/_internal/pkg/mod.py" --mode=strict --flag`.\n'
        + 'Esegui `python scripts/schemas/contracts.py --schema-ok`.\n',
        encoding="utf-8",
    )
    cove_ok = eng.verify_cli_flags_cove(ws)
    assert cove_ok["passed"] is True
    assert cove_ok["checked_flags_count"] >= 3

    bad_skill.write_text(bad_skill.read_text(encoding="utf-8") + 'Esegui `python "dir with spaces/scripts/_internal/pkg/mod.py" --ghost=1`.\n', encoding="utf-8")
    cove_bad = eng.verify_cli_flags_cove(ws)
    assert cove_bad["passed"] is False
    assert any("--ghost" in f for f in cove_bad["invalid_flags"])
    return bad_skill, long_ste


def _assert_s3b_ste100_links_and_grounding(ws: Path, eng: Any, bad_skill: Path, long_ste: str) -> None:
    (ws / "scripts" / "core_api.py").write_text("def other_api() -> int:\n    return 1\n", encoding="utf-8")
    bad_skill.write_text("---\nname: NK-Sample\nversion: '1.0.0-Generation'\n---\n" + long_ste, encoding="utf-8")
    vibe_adv = eng.run_vibe_check(bad_skill, profile="ste100_rsi", strict_verify=False)
    assert (vibe_adv["passed"], vibe_adv["delta_k"], bool(vibe_adv["ste100_warnings"])) == (True, 0, True)
    vibe_strict = eng.run_vibe_check(bad_skill, profile="ste100_rsi", strict_verify=True)
    assert vibe_strict["passed"] is False
    assert vibe_strict["delta_k"] > 0

    bad_skill.write_text("---\nname: NK-Sample\nversion: '1.0.0-Generation'\n---\nVedi [missing](references/missing_doc.md) e [ok](https://example.com).\n", encoding="utf-8")
    eco_broken = eng.verify_ecosystem(root_dir=ws, profile="code_rsi", test_report={"tests_passed": 2, "tests_failed": 0, "tests_total": 2})
    assert eco_broken["passed"] is False
    assert eco_broken["delta_k"] > 0
    assert bool(eco_broken["checks"]["skills_and_markdown"]["broken_links"])

    tr_mod = load_nk_script_module("nk_transcript_tools")
    (ws / "nk_tracking" / "internal_integrity_index.json").write_text(json.dumps({"files": {"scripts/_internal/indexed/helper.py": "abc"}}), encoding="utf-8")
    rep_md = ws / "grounding_rep.md"
    rep_md.write_text("Moduli: `scripts/_internal/pkg/mod.py`, `scripts/schemas/contracts.py`, `scripts/_internal/indexed/helper.py`.\n", encoding="utf-8")
    gr_ok = tr_mod.verify_report_grounding(rep_md, manifest_path=ws / "nk_genome" / "nk_registry_manifest.json")
    assert gr_ok["passed"] is True
    assert "scripts/_internal/pkg/mod.py" in gr_ok["verified_scripts"]

    rep_bad = ws / "grounding_bad.md"
    rep_bad.write_text("Usa `scripts/_internal/missing_pkg/mod.py`.\n", encoding="utf-8")
    gr_bad = tr_mod.verify_report_grounding(rep_bad, manifest_path=ws / "nk_genome" / "nk_registry_manifest.json")
    assert gr_bad["passed"] is False
    assert "scripts/_internal/missing_pkg/mod.py" in gr_bad["hallucinated_scripts"]


def _assert_s3b_hash_filter_and_oracle_cli(tmp_path: Path, ws: Path, monkeypatch: Any) -> None:
    tr_mod = load_nk_script_module("nk_transcript_tools")
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_ok.py").write_text("def test_ok(): assert 1 + 1 == 2\n", encoding="utf-8")
    (ws / "tests" / "junk.zip").write_bytes(b"PK")
    (ws / "tests" / "junk.tmp").write_text("tmp", encoding="utf-8")
    fmap = tr_mod._hash_target_files(ws / "tests")
    assert ("test_ok.py" in fmap, "junk.zip" not in fmap, "junk.tmp" not in fmap) == (True, True, True)

    ws_cwd = tmp_path / "cwd_oracle_ws"
    (ws_cwd / ".staging" / "scripts" / "_internal" / "nk_transcript_tools").mkdir(parents=True)
    (ws_cwd / "tests").mkdir(parents=True)
    (ws_cwd / "tests" / "test_unit.py").write_text("def test_u(): assert 2 + 2 == 4\n", encoding="utf-8")

    ntt_cli_mod = sys.modules.get("_internal.nk_transcript_tools.cli") or importlib.import_module("_internal.nk_transcript_tools.cli")
    with monkeypatch.context() as mp_o:
        mp_o.chdir(tmp_path)
        mp_o.setattr(ntt_cli_mod, "__file__", str(ws_cwd / ".staging" / "scripts" / "_internal" / "nk_transcript_tools" / "cli.py"))
        rc_frz, out_frz, _ = call_script_main_captured(tr_mod, ["oracle-lock", "freeze"])
        assert (rc_frz, json.loads(out_frz)["status"]) == (0, "LOCKED")
        assert (ws_cwd / "nk_tracking" / "oracle_lock.json").is_file()
        rc_ver, out_ver, _ = call_script_main_captured(tr_mod, ["oracle-lock", "verify"])
        assert (rc_ver, json.loads(out_ver)["passed"]) == (0, True)


@pytest.mark.fast
def test_s3b_rsi_baseline_diff_strict_doc_drift_cove_and_grounding(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica S3-B: baseline diff, doc_drift/link, CoVe e oracle-lock/grounding."""
    ws = tmp_path / "s3b_ws"
    (ws / ".agents" / "skills" / "NK-Sample").mkdir(parents=True)
    (ws / "scripts" / "_internal" / "pkg").mkdir(parents=True)
    (ws / "scripts" / "schemas").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)
    eng = _new_staged_engine(ws, monkeypatch)
    bad_skill, long_ste = _assert_s3b_baseline_and_cove(ws, eng)
    _assert_s3b_ste100_links_and_grounding(ws, eng, bad_skill, long_ste)
    _assert_s3b_hash_filter_and_oracle_cli(tmp_path, ws, monkeypatch)


def _assert_wave2a_import_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as mp_imp:
        mp_imp.setitem(sys.modules, "_internal.ast_guard_validator.quality_diff_checker", None)
        mp_imp.setitem(sys.modules, "_internal.ast_guard_validator.frontend_static_checker", None)

        stg_py = tmp_path / ".staging" / "scripts" / "sample.py"
        stg_py.parent.mkdir(parents=True)
        stg_py.write_text("X = 1\n", encoding="utf-8")
        py_viols = rsi_eco_aud.inspect_python_quality_staged(stg_py, "", "X = 1\n", "scripts/sample.py", tmp_path)
        assert bool(py_viols)
        assert (py_viols[0].rule_id, py_viols[0].severity) == ("QD-IMPORT-FAIL", "HIGH")

        fe_ts = tmp_path / "app.ts"
        fe_ts.write_text("export const x = 1;\n", encoding="utf-8")
        fe_viols = rsi_eco_aud.inspect_frontend_file(fe_ts, "export const x = 1;\n", "app.ts", tmp_path)
        assert bool(fe_viols)
        assert (fe_viols[0].rule_id, fe_viols[0].severity) == ("FE-IMPORT-FAIL", "HIGH")


def _assert_wave2a_skipped_probe_and_q_v2_unmeas(tmp_path: Path) -> None:
    bl_file = tmp_path / "nk_tracking" / "quality_baseline.json"
    bl_file.parent.mkdir(parents=True)
    bl_file.write_text(
        json.dumps({
            "metrics": {
                "unit_tests_total": {"value": 10, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 10, "direction": "higher_is_better"},
                "tests_skipped": {"value": 0, "direction": "lower_is_better"},
            },
            "invariants": {"require_100_percent_test_pass": True},
        }),
        encoding="utf-8",
    )
    probes = {"rsi_verify": {"checks": {"benchmark_suite": {"executed": True, "tests_passed": 8, "tests_failed": 0, "skipped_count": 2, "tests_total": 10}}}}
    qbm = load_nk_script_module("quality_baseline_manager")
    qb_res = rsi_probes._run_quality_baseline_probe(tmp_path, tmp_path / ".staging", probes, None, lambda _r, _n: qbm)
    assert qb_res["verdict"] == "FAIL"
    assert any(r["metric"] == "tests_skipped" and r["current_value"] == 2 for r in qb_res["regressions"])

    prev_v = RSIDefectVector(doc_drift=1, low_findings=0)
    curr_v = RSIDefectVector(doc_drift=0, low_findings=1)
    assert rsi_loop.check_hard_gate_regression_impl(prev_v, curr_v, strict_monotonic=True, profile="code_rsi")[0] is True
    assert rsi_loop.check_hard_gate_regression_impl(prev_v, curr_v, strict_monotonic=True, profile="ste100_rsi")[0] is False

    gaming_unmeas = RSIDefectVector(tests_passed=10, tests_total=10, deception_gaming_count=1)
    res_g = rsi_profiles.compute_fitness_v2(gaming_unmeas, has_python_diff=True, k_mut_diff=None, c_branch_diff=0.9)
    assert (res_g["certification_tier"], res_g["q_v2"], res_g["gaming_penalty"]) == ("FAIL", 0.0, -10000)

    ws = _make_conf11_workspace(tmp_path)
    eng = RSIConvergenceEngine(workspace_root=ws, root=ws)
    eco_unmeas = eco_mod.verify_ecosystem_impl(eng, root_dir=ws, profile="code_rsi", test_report={"tests_passed": 4, "tests_failed": 0, "tests_skipped": 0, "tests_total": 4})
    assert (eco_unmeas["certification_tier"], eco_unmeas["status"], eco_unmeas["passed"]) == ("UNMEASURED", "UNMEASURED", False)

    eco_ghard0 = eco_mod.verify_ecosystem_impl(eng, root_dir=ws, profile="code_rsi", test_report={"tests_passed": 4, "tests_failed": 0, "tests_skipped": 1, "tests_total": 5})
    assert (eco_ghard0["g_hard"], eco_ghard0["passed"]) == (0, False)
    assert eco_ghard0["status"] != "CONVERGED_OPTIMAL"
    assert eco_mod._resolve_ecosystem_status_and_pass([], [], 0, 100.0, {"workspace_clean_hygiene": {"passed": True}}, {"g_hard": 0, "certification_tier": "FAIL"}) == ("REFINING", False)


@pytest.mark.fast
def test_rsi_wave2a_import_error_skipped_count_and_gt14_gaming_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica ImportError fail-closed, skipped_count->tests_skipped e GT-14 gaming/verdict gate."""
    _assert_wave2a_import_fail_closed(tmp_path, monkeypatch)
    _assert_wave2a_skipped_probe_and_q_v2_unmeas(tmp_path)



def _assert_rsi_const_attrs_and_ast_cache(ws: Path) -> None:
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts" / "ok_mod.py").write_text("VALUE = 42\n", encoding="utf-8")

    assert rsi_const.DefectVector is rsi_const.RSIDefectVector
    assert rsi_const.RSIIterationRecord is not None
    with pytest.raises(AttributeError):
        getattr(rsi_const, "MISSING_RSI_CONST_ATTR")

    sample_py = ws / "cached_mod.py"
    sample_py.write_text("VAL = 123\n", encoding="utf-8")
    rsi_const._FILE_AST_CACHE.clear()
    txt1, tree1 = rsi_const._get_cached_file_and_ast(sample_py)
    txt2, tree2 = rsi_const._get_cached_file_and_ast(sample_py)
    assert "VAL = 123" in txt1
    assert tree1 is not None
    assert (txt2, tree2 is tree1) == (txt1, True)

    bad_py = ws / "scripts" / "broken_ast.py"
    bad_py.write_text("def broken(:\n", encoding="utf-8")
    src_txt, parsed_ast = rsi_const._get_cached_file_and_ast(bad_py)
    assert (parsed_ast, rsi_const._get_cached_file_and_ast(bad_py)[0]) == (None, src_txt)


def _assert_rsi_const_deleted_manifest_and_sast_extract(tmp_path: Path, ws: Path) -> None:
    corrupt_del = ws / "corrupt_del.json"
    for raw_txt in ("{bad", "123"):
        corrupt_del.write_text(raw_txt, encoding="utf-8")
        assert rsi_const._parse_deleted_manifest_rels(corrupt_del) == set()
    (ws / ".staging" / ".deleted_files.json").write_text("{bad", encoding="utf-8")
    assert rsi_const.load_staging_deleted_set_impl(ws) == set()

    del_ws = tmp_path / "del_manifest_ws"
    (del_ws / ".agents").mkdir(parents=True)
    (del_ws / ".staging").mkdir(parents=True)
    (del_ws / ".agents" / "gone.md").write_text("# Old\n", encoding="utf-8")
    (del_ws / ".agents" / "kept.md").write_text("# Kept\n", encoding="utf-8")
    manifest = del_ws / ".staging" / ".deleted_files.json"
    manifest.write_text(json.dumps({"deleted_files": [".agents/gone.md"]}), encoding="utf-8")
    assert ".agents/gone.md" in rsi_const.load_staging_deleted_set_impl(del_ws)
    assert [p.name for p in rsi_const._collect_overlay_md_files(del_ws, ".agents")] == ["kept.md"]
    manifest.write_text(json.dumps([".agents/gone.md", "scripts/legacy.py"]), encoding="utf-8")
    assert rsi_const.load_staging_deleted_set_impl(del_ws) == {".agents/gone.md", "scripts/legacy.py"}
    assert [p.name for p in rsi_const._collect_overlay_md_files(del_ws, ".agents")] == ["kept.md"]

    (ws / ".agents" / ".git").mkdir(parents=True)
    (ws / ".agents" / ".git" / "skip.md").write_text("# skip\n", encoding="utf-8")
    assert len(rsi_const._collect_overlay_md_files(ws / ".staging", ".agents")) == 1
    assert rsi_const._is_excluded_rel_path(tmp_path / "outside.py", ws) is False

    sast_f = tmp_path / "sast_r.json"
    for payload, exp_pass, exp_cnt in (
        ('{"sast_violations_count": 3}', False, 3),
        ('{"violations": [1]}', False, 1),
        ('{"status": "PASS", "sast_critical": 0}', True, 0),
        ("{bad", False, 1),
    ):
        sast_f.write_text(payload, encoding="utf-8")
        s_res = rsi_vrh.audit_sast_report_payload(sast_f)
        assert (s_res["passed"], s_res.get("sast_critical", s_res.get("high_findings"))) == (exp_pass, exp_cnt)
    assert rsi_const.resolve_candidate_impl(ws / ".staging", "scripts/broken_ast.py").exists()


def _assert_rsi_const_ntt_loader_and_lazy_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lb_ws = tmp_path / "lb_ws"
    stg_scripts = lb_ws / ".staging" / "scripts"
    stg_scripts.mkdir(parents=True)
    (stg_scripts / "nk_transcript_tools.py").write_text(
        "def verify_ste100_compliance(text, max_sentence_words=20):\n    return {'passed': True, 'violations_count': 0, 'violations': []}\n"
        "def verify_report_grounding(path, manifest_path=None):\n    return {'passed': True}\n",
        encoding="utf-8",
    )
    ntt_loaded = rsi_const.fallback_load_ntt_module(scripts_dir=stg_scripts, workspace_root=lb_ws)
    assert ntt_loaded is not None
    assert ntt_loaded.verify_ste100_compliance("Ok.")["passed"] is True
    assert rsi_const.fallback_load_ntt_module(scripts_dir=tmp_path / "m1", workspace_root=tmp_path / "m2") is None

    with monkeypatch.context() as mp_lb:
        mp_lb.setattr(rsi_const, "_HOOKS", {})
        mp_lb.setitem(rsi_const._FALLBACK_STATE, "reconfigured", False)
        rsi_const.get_reconfigure_streams()
        assert rsi_const._FALLBACK_STATE["reconfigured"] is True

        for k_reset in ("hsm_loaded", "agv_loaded", "ste100_fn", "grounding_fn"):
            mp_lb.setitem(rsi_const._FALLBACK_STATE, k_reset, False if k_reset.endswith("loaded") else None)
        mp_lb.setitem(sys.modules, "auto_heal_pipeline", None)
        mp_lb.setitem(sys.modules, "scripts.auto_heal_pipeline", None)
        assert rsi_const.get_healing_snapshot_manager_cls() is None

        rsi_const.register_lazy_hooks(
            reconfigure_fn=lambda: None, hsm_fn=lambda: None, agv_fn=lambda: None,
            ste100_fn=lambda: (lambda txt, max_sentence_words=20: {"passed": True, "txt": txt}),
            grounding_fn=lambda: None,
        )
        assert rsi_const.get_ste100_validator()("Ok")["passed"] is True
        assert rsi_const.get_report_grounding_validator() is None


@pytest.mark.fast
def test_rsi_constants_lazy_cache_overlay_and_bridge_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Esercita constants.py su lazy attrs, cache AST, .deleted_files.json, overlay .md, NTT loader e hooks."""
    ws = _make_conf11_workspace(tmp_path)
    _assert_rsi_const_attrs_and_ast_cache(ws)
    _assert_rsi_const_deleted_manifest_and_sast_extract(tmp_path, ws)
    _assert_rsi_const_ntt_loader_and_lazy_hooks(tmp_path, monkeypatch)


def _assert_canary_readonly_unchanged(ch: Any, tmp_path: Path, cfile: Path, mtime_before: int, content_before: str) -> None:
    missing_dir = tmp_path / "never_created" / "canary_v1.json"
    assert ch.evaluate_canary_holdout(holdout_path=missing_dir)["passed"] is True and not missing_dir.parent.exists()
    assert ch.evaluate_canary_holdout(holdout_path=cfile)["passed"] is True
    assert (cfile.stat().st_mtime_ns, cfile.read_text(encoding="utf-8")) == (mtime_before, content_before)


@pytest.mark.integration
def test_rsi_canary_holdout_ast_conflict_and_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Esercita canary_holdout.py in sola lettura stretta senza riscrivere canary_v1.json."""
    from _internal.rsi_convergence_engine import canary_holdout as ch

    explicit_dir = tmp_path / "explicit_canary_dir"
    cfile = ch.ensure_canary_holdout_file(holdout_dir=explicit_dir)
    assert cfile.is_file()
    mtime_before, content_before = cfile.stat().st_mtime_ns, cfile.read_text(encoding="utf-8")

    with monkeypatch.context() as mp_can:
        mp_can.delenv("NK_HOLDOUT_DIR", raising=False)
        mp_can.setenv("LOCALAPPDATA", str(tmp_path / "local_app"))
        _assert_canary_readonly_unchanged(ch, tmp_path, cfile, mtime_before, content_before)

    for raw_bad in ("", "# only comment", "def f(): pass", "bad_syntax("):
        assert ch._parse_single_assertion_ast(raw_bad) is None
    assert ch._parse_single_assertion_ast("not ready") is not None

    ast_cases = (
        ("not x", "x is True", "HALT_EPISTEMIC_CONFLICT"),
        ("10 == count", "count == 20", "HALT_EPISTEMIC_CONFLICT"),
        ("x == True", "x == 1", "HALT_EPISTEMIC_CONFLICT"),
        ("x is None", "x == 0", "HALT_EPISTEMIC_CONFLICT"),
        ("x == 5", "x != 5", "HALT_EPISTEMIC_CONFLICT"),
        ("x == y", "x != y", "HALT_EPISTEMIC_CONFLICT"),
        ("x > 10", "x < 5", "HALT_EPISTEMIC_CONFLICT"),
        ("x < 5", "x >= 5", "HALT_EPISTEMIC_CONFLICT"),
        ("x == 5", "x > 5", "HALT_EPISTEMIC_CONFLICT"),
        ("x <= 4", "x == 5", "HALT_EPISTEMIC_CONFLICT"),
        ("x in [1, 2]", "x == 1", "UNRESOLVED_CONFLICT"),
        ("bad(", "x == 1", "UNRESOLVED_CONFLICT"),
        ("a == 1", "b == 2", "CONSISTENT_NO_CONFLICT"),
        ("x >= 5", "x <= 5", "CONSISTENT_NO_CONFLICT"),
    )
    for a_expr, b_expr, expected_verdict in ast_cases:
        assert ch._detect_assertion_epistemic_conflict(a_expr, b_expr) == expected_verdict

    bad_tasks_f = tmp_path / "bad_tasks.json"
    bad_tasks_f.write_text(json.dumps({"tasks": "invalid"}), encoding="utf-8")
    assert ch.evaluate_canary_holdout(holdout_path=bad_tasks_f)["passed"] is False

    mixed_f = tmp_path / "mixed_tasks.json"
    mixed_f.write_text(json.dumps({"tasks": ["skip", {"task_id": "T-UNR", "test_a": "x in [1]", "test_b": "x == 1"}]}), encoding="utf-8")
    assert ch.evaluate_canary_holdout(holdout_path=mixed_f)["tasks"][0]["verdict"] == "UNRESOLVED_CONFLICT"


def _assert_eco_ste100_markdown_docs(tmp_path: Path) -> None:
    clean_doc = "---\ndescription: Frontmatter YAML lungo ignorato dal parser.\n---\n# Specifica\nFrase breve conforme.\n"
    assert verify_ste100_compliance(clean_doc, max_sentence_words=20)["passed"] is True
    bad_doc = "Frase con trattino \u2014 lungo.\n" + ("parola " * 25) + ".\n"
    res_bad = verify_ste100_compliance(bad_doc, max_sentence_words=20)
    assert res_bad["passed"] is False
    assert res_bad["violations_count"] >= 2
    assert verify_ste100_compliance("Vieta ` \u2014 ` e ` \u2013 ` inline.\n", max_sentence_words=20)["passed"] is True

    hub_ws = tmp_path / "eco_hub_ws"
    (hub_ws / ".agents" / "skills" / "NK-Demo").mkdir(parents=True)
    (hub_ws / ".agents" / "agents" / "NK-Demo-Agent").mkdir(parents=True)
    (hub_ws / "nk_genome").mkdir(parents=True)
    (hub_ws / "nk_docs_and_setup").mkdir(parents=True)
    long_line = " ".join(["parola"] * 24) + ".\n"
    (hub_ws / ".agents" / "skills" / "NK-Demo" / "SKILL.md").write_text("v1.0.0\n" + long_line, encoding="utf-8")
    (hub_ws / ".agents" / "agents" / "NK-Demo-Agent" / "agent.md").write_text("# Agent\nFrase breve.\n", encoding="utf-8")
    (hub_ws / "nk_genome" / "PATCH_NOTES.md").write_text("# Patch\nNota breve.\n", encoding="utf-8")
    (hub_ws / "nk_docs_and_setup" / "README.md").write_text("# Readme\nTesto breve.\n", encoding="utf-8")
    res_hub_m = rsi_eco_aud.audit_markdown_docs_impl(RSIConvergenceEngine(workspace_root=hub_ws, root=hub_ws), hub_ws, "code_rsi", [], [])
    assert (res_hub_m["skills_verified"], res_hub_m["agents_verified"]) == (1, 1)
    assert len(res_hub_m["ste100_warnings"]) >= 1

    non_hub = tmp_path / "eco_nonhub_ws"
    (non_hub / ".agents").mkdir(parents=True)
    (non_hub / ".agents" / "dup_a.md").write_text(long_line + "Vedi `scripts/ghost_missing.py`.\n", encoding="utf-8")
    (non_hub / ".agents" / "dup_b.md").write_text(long_line + "Vedi `scripts/ghost_missing.py`.\n", encoding="utf-8")
    res_nh = rsi_eco_aud.audit_markdown_docs_impl(RSIConvergenceEngine(workspace_root=non_hub, root=non_hub), non_hub, "ste100_rsi", [], [])
    assert res_nh["passed"] is False
    assert len(res_nh["phantom_scripts"]) >= 1
    assert len(res_nh["ste100_warnings"]) >= 1


def _assert_eco_dry_run_flags(tmp_path: Path) -> None:
    assert rsi_eco_aud.report_is_dry_run_impl(None) is False
    assert rsi_eco_aud.report_is_dry_run_impl({"dry_run": True}) is True
    assert rsi_eco_aud.report_is_dry_run_impl({"status": "DRY_RUN_DONE"}) is True
    assert rsi_eco_aud.report_is_dry_run_impl(tmp_path / "missing_dast.json") is False
    bad_f = tmp_path / "bad_dast.json"
    bad_f.write_bytes(b"{bad")
    assert rsi_eco_aud.report_is_dry_run_impl(bad_f) is False
    arr_f = tmp_path / "arr_dast.json"
    arr_f.write_bytes(b"[1, 2]")
    assert rsi_eco_aud.report_is_dry_run_impl(arr_f) is False


def _assert_eco_gt14_gov_and_twin_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "eco_gov_ws"
    (ws / ".agents" / "agents" / "NK-Demo").mkdir(parents=True)
    (ws / ".agents" / "plugins" / "nk-gate" / "agents").mkdir(parents=True)
    (ws / "scripts").mkdir(parents=True)
    (ws / ".agents" / "agents" / "NK-Demo" / "agent.md").write_text("# Demo\n", encoding="utf-8")
    (ws / ".agents" / "plugins" / "nk-gate" / "agents" / "NK-Demo.md").write_text("# Drift\n", encoding="utf-8")
    (ws / "scripts" / "nk_registry_indexer.py").write_text(
        "import hashlib\nfrom pathlib import Path\n"
        "class NKRegistryIndexer:\n"
        "    def __init__(self, workspace_root):\n        self.workspace_root = Path(workspace_root)\n        self.stage_dir = self.workspace_root / '.staging'\n"
        "    def verify_gt14_crit01_governance(self): return {'passed': False, 'issues': []}\n"
        "    def _collect_priority_native_agents(self): return {'NK-Demo': (self.workspace_root / '.agents/agents/NK-Demo/agent.md', False)}\n"
        "    def _load_staging_deleted_paths(self): return set()\n"
        "    def _compute_sha256(self, p): return hashlib.sha256(p.read_bytes()).hexdigest()\n"
        "    def _sha256_matches_eol_normalized(self, _p, a, b): return a == b\n",
        encoding="utf-8",
    )
    with monkeypatch.context() as mp_gov:
        mp_gov.setitem(sys.modules, "nk_registry_indexer", None)
        mp_gov.setitem(sys.modules, "scripts.nk_registry_indexer", None)
        viols_g: list[str] = []
        assert (rsi_eco_aud.audit_gt14_governance_impl(ws, [], viols_g)[1]["passed"], len(viols_g)) == (False, 1)
        assert "NK-Demo" in rsi_eco_aud.audit_twin_manifest_parity_impl(ws)["mismatches"]

        (ws / ".staging" / "scripts").mkdir(parents=True)
        (ws / ".staging" / "scripts" / "nk_registry_indexer.py").write_text(
            "class NKRegistryIndexer:\n    def __init__(self, workspace_root): pass\n"
            "    def verify_gt14_crit01_governance(self): raise RuntimeError('gov boom')\n"
            "    def audit_twin_manifest_parity(self): return {'passed': True, 'skipped': False, 'checked_agents': 1, 'mismatches': [], 'violations': []}\n",
            encoding="utf-8",
        )
        assert rsi_eco_aud._load_nk_registry_indexer_cls(ws) is not None
        assert rsi_eco_aud.audit_twin_manifest_parity_impl(ws)["passed"] is True
        gov_err_viols: list[str] = []
        assert (rsi_eco_aud.audit_gt14_governance_impl(ws, [], gov_err_viols)[1]["passed"], len(gov_err_viols)) == (False, 1)

        miss_root = tmp_path / "no_idx_root"
        miss_root.mkdir()
        mp_gov.setattr(rsi_eco_aud, "_scripts_dir", miss_root)
        mp_gov.setattr(rsi_eco_aud, "_workspace_root", miss_root)
        assert rsi_eco_aud._load_nk_registry_indexer_cls(miss_root) is None

        mp_gov.setattr(rsi_eco_aud, "_load_nk_registry_indexer_cls", lambda _r: None)
        assert rsi_eco_aud.audit_gt14_governance_impl(ws, [], [])[1]["skipped"] is True
        assert rsi_eco_aud.audit_twin_manifest_parity_impl(ws)["passed"] is False

    class _MissingTwinIdx:
        workspace_root = ws
        stage_dir = ws / ".staging"

        def _collect_priority_native_agents(self):
            return {"NK-Ghost": (ws / ".agents" / "agents" / "NK-Demo" / "agent.md", False)}

        def _load_staging_deleted_paths(self):
            return set()

    assert "NK-Ghost" in rsi_eco_aud._fallback_twin_parity(_MissingTwinIdx())["mismatches"]


def _assert_eco_sast_scanner_and_dot_del(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from _internal.rsi_convergence_engine import sast_scanner as rsi_sast

    prose = rsi_sast._strip_fenced_code("Ok.\n```md\n[ignored](missing/inside_fence.md)\n```\nDopo.\n")
    assert "inside_fence.md" not in prose
    ws_sast = tmp_path / "sast_ws"
    for d in ("scripts", ".staging/scripts", ".agents", "nk_tracking/reports_and_briefs", ".staging/nk_tracking/reports_and_briefs"):
        (ws_sast / d).mkdir(parents=True)
    outside_md = tmp_path / "outside_doc.md"
    outside_md.write_text("[w](*.md)\nscripts/ghost_a.py scripts/ghost_a.py\nNK_Hub/scripts/nope_hub.py\nowasp_sast_scanner.py owasp_sast_scanner.py\n", encoding="utf-8")
    assert len(rsi_sast.audit_markdown_doc_references(outside_md, outside_md.read_text(encoding="utf-8"), ws_sast, rsi_const.resolve_candidate_impl, check_scripts=True)[1]) >= 3
    (ws_sast / "root_note.md").write_text("Bad \ufffd char\n", encoding="utf-8")
    (ws_sast / "scripts" / "bad.py").write_text("def run(x):\n    return " + "ev" + "al(x)\n", encoding="utf-8")
    (ws_sast / ".staging" / "scripts" / "bad.py").write_text("def run(x):\n    return x\n", encoding="utf-8")
    (ws_sast / ".staging" / "scripts" / "bad.json").write_bytes(b"{invalid")
    (ws_sast / "nk_tracking" / "reports_and_briefs" / "TAS_Report_a.md").write_text("`scripts/missing_tas.py`\n", encoding="utf-8")
    (ws_sast / ".staging" / "nk_tracking" / "reports_and_briefs" / "tas_certification_report_b.md").write_text("`scripts/auto_heal_pipeline.py`\n", encoding="utf-8")
    with monkeypatch.context() as mp_sast:
        mp_sast.setattr(rsi_sast, "_workspace_root", ws_sast)
        eng_sast = RSIConvergenceEngine(workspace_root=ws_sast, root=ws_sast)
        scan1 = rsi_sast.scan_sast_and_mojibake_impl(eng_sast, ws_sast)
        scan2 = rsi_sast.scan_sast_and_mojibake_impl(eng_sast, ws_sast)
        assert (scan1["passed"], scan1["mojibake_count"], scan1["invalid_json_count"], scan2["sast_critical"]) == (False, 1, 1, scan1["sast_critical"])
        assert rsi_sast.audit_tas_reports_impl(eng_sast, ws_sast, [], [])[0] == 1

    assert rsi_sast._normalize_deleted_rel_set({"./.agents/gone.md", "./.deleted_files.json", "scripts/ok.py"}) == {".agents/gone.md", ".deleted_files.json", "scripts/ok.py"}
    ws_dot = tmp_path / "dot_del_ws"
    (ws_dot / ".agents").mkdir(parents=True)
    (ws_dot / ".staging").mkdir(parents=True)
    (ws_dot / ".agents" / "guide.md").write_text("[Ref](./.agents/gone.md)\n", encoding="utf-8")
    (ws_dot / ".agents" / "gone.py").write_text("BROKEN = (\n", encoding="utf-8")
    (ws_dot / ".staging" / ".deleted_files.json").write_text(json.dumps(["./.agents/gone.py"]), encoding="utf-8")
    assert len(rsi_sast.audit_markdown_doc_references(ws_dot / ".agents" / "guide.md", "[Ref](gone.md)\n", ws_dot, rsi_const.resolve_candidate_impl, deleted_rel={"./.agents/gone.md"})[0]) == 1
    assert ".agents/gone.py" not in [p.relative_to(ws_dot).as_posix() for p in rsi_sast.scan_sast_and_mojibake_impl(RSIConvergenceEngine(workspace_root=ws_dot, root=ws_dot), ws_dot)["scanned_files"]]


def _assert_eco_quality_cls_and_fe_scan(tmp_path: Path) -> None:
    cls_res = rsi_eco_aud.classify_quality_violations([
        SimpleNamespace(rule_id="QD-SCOPE-CREEP", severity="HIGH", file_path="a.py", line_number=0, message="scope"),
        SimpleNamespace(rule_id="FE-EVAL", severity="HIGH", file_path="b.ts", line_number=4, message="hi"),
        SimpleNamespace(rule_id="QD-M", severity="MEDIUM", file_path="c.py", line_number=0, message="med"),
        SimpleNamespace(rule_id="QD-L", severity="LOW", file_path="d.py", line_number=2, message="low"),
    ])
    assert (cls_res["semantic_drift_findings"], cls_res["high_findings"], cls_res["medium_findings"], cls_res["low_findings"]) == (1, 1, 1, 1)
    assert rsi_eco_aud.inspect_python_quality_staged(tmp_path / "prod_only.py", "", "X=1\n", "prod_only.py", tmp_path) == []
    assert rsi_eco_aud.inspect_frontend_file(tmp_path / "mod.py", "X=1\n", "mod.py", tmp_path) == []

    fe_ws = tmp_path / "fe_scan_ws"
    (fe_ws / ".staging" / "web").mkdir(parents=True)
    (fe_ws / "web").mkdir(parents=True)
    (fe_ws / "tmp_pytest_skip").mkdir(parents=True)
    (fe_ws / "tmp_pytest_skip" / "skip.ts").write_text("ev" + "al('x');\n", encoding="utf-8")
    (fe_ws / "web" / "prod_app.ts").write_text("export const a = 1;\n", encoding="utf-8")
    stg_ts = fe_ws / ".staging" / "web" / "stg_app.ts"
    stg_ts.write_text("export const b = 2;\n", encoding="utf-8")
    stg_txt = fe_ws / ".staging" / "web" / "note.txt"
    stg_txt.write_text("txt\n", encoding="utf-8")
    fe_viols: list[Any] = []
    assert rsi_eco_aud._scan_staged_entry(fe_ws, fe_ws / ".staging", stg_ts, fe_viols) == 1
    assert rsi_eco_aud._scan_staged_entry(fe_ws, fe_ws / ".staging", stg_txt, fe_viols) == 0
    assert rsi_eco_aud._scan_prod_frontend(fe_ws, set(), set(), fe_viols) == 1


def _assert_cli_gates_rsi_ecosystem_and_vibe_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Migrated from test_sovereign_carbon_cli_core_gates.py::test_cli_gates_rsi_ecosystem_and_vibe_failures
    hub = tmp_path / "defective_hub"
    for d in (".agents/skills/NK-Sample", ".agents/agents/NK-RSI-Auditor", "nk_genome", "nk_tracking/reports_and_briefs", "scripts"):
        (hub / d).mkdir(parents=True)
    (hub / ".agents" / "AGENTS.md").write_text("[RULE-STE100]\nQuesta frase — contiene trattino spaziato.\n" + ("A" * 24500), encoding="utf-8")
    (hub / ".agents" / "skills" / "NK-Sample" / "SKILL.md").write_text("---\nname: NK-Sample\nversion: 6.0.0-Carbon\n---\nLink rotto [aux](resources/missing.md).\n", encoding="utf-8")
    (hub / ".agents" / "agents" / "NK-RSI-Auditor" / "agent.md").write_text("---\nname: NK-RSI-Auditor\nenable_write_tools: false\n---\nAgente conforme.\n", encoding="utf-8")
    (hub / "nk_genome" / "broken.json").write_text("{invalid_json", encoding="utf-8")
    (hub / "scripts" / "moji.py").write_text("# Carattere \ufffd invalido\nX = 1\n", encoding="utf-8")
    (hub / "scripts" / "orphan.tmp").write_text("tmp", encoding="utf-8")
    (hub / "nk_tracking" / "reports_and_briefs" / "tas_certification_report_x.md").write_text("Esegui subito `python scripts/nk_2pc_promoter.py`.\n", encoding="utf-8")
    res_mig = RSIConvergenceEngine(workspace_root=hub, root=hub).verify_ecosystem(
        root_dir=hub, profile="ste100_rsi", test_report={"tests_passed": 4, "tests_failed": 1, "tests_total": 5}, persist_telemetry=True
    )
    assert (res_mig["passed"], res_mig["status"]) == (False, "REFINING")
    assert len(res_mig["violations"]) >= 4
    assert res_mig["checks"]["agents_md"]["ste100_passed"] is False
    assert res_mig["checks"]["workspace_clean_hygiene"]["passed"] is False
    assert res_mig["checks"]["sast_and_mojibake"]["invalid_json_count"] >= 1

    ext_app = tmp_path / "plain_app"
    ext_app.mkdir()
    (ext_app / "spec.md").write_text("[RULE-STE100]\nVedi [altro](missing_doc.md) e [sito](https://example.com).\n", encoding="utf-8")
    eng_ext = RSIConvergenceEngine(workspace_root=ext_app, root=ext_app)
    res_ext = eng_ext.verify_ecosystem(root_dir=ext_app, profile="ste100_rsi")
    assert (res_ext["passed"], len(res_ext["checks"]["skills_and_markdown"]["broken_links"])) == (False, 1)
    bad_py = ext_app / "syn_err.py"
    bad_py.write_text("def oops(:\n    pass\n", encoding="utf-8")
    (ext_app / "bad.json").write_text("{oops", encoding="utf-8")
    assert eng_ext.run_vibe_check(ext_app)["passed"] is False
    capsys.readouterr()
    assert rsi_mod.main(["--vibe-check", str(bad_py), "--root", str(ext_app)]) != 0
    assert "RSI-VIBE-CHECK" in capsys.readouterr().out


@pytest.mark.integration
def test_rsi_eco_audits_ste100_governance_sast_cli_and_missing_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Esercita G6 STE100, eco_audits, sast_scanner, test_cli_gates_rsi_ecosystem_and_vibe_failures e branch eco_audits."""
    _assert_eco_ste100_markdown_docs(tmp_path)
    _assert_eco_dry_run_flags(tmp_path)
    _assert_eco_gt14_gov_and_twin_parity(tmp_path, monkeypatch)
    _assert_eco_sast_scanner_and_dot_del(tmp_path, monkeypatch)
    _assert_eco_quality_cls_and_fe_scan(tmp_path)
    _assert_cli_gates_rsi_ecosystem_and_vibe_failures(tmp_path, capsys)


def _assert_dast_report_dict_cases() -> None:
    from _internal.rsi_convergence_engine.vibe_report_helpers import audit_dast_report_payload

    for bad_payload in (
        {}, {"status": ""}, {"status": None}, {"passed": True, "status": "", "is_dry_run": False},
        {"status": "TIMEOUT"}, {"status": "DRY_RUN", "is_dry_run": True, "passed": True},
        {"passed": True, "timed_out": True}, {"passed": True, "memory_exceeded": True},
        {"passed": True, "exit_code": 1}, {"success": False, "exit_code": 1, "timed_out": False, "memory_exceeded": False},
        {"success": True, "exit_code": 0, "timed_out": True, "memory_exceeded": False},
        {"success": True, "exit_code": 0, "timed_out": False, "memory_exceeded": True},
        {"success": True, "exit_code": 0, "timed_out": None, "memory_exceeded": False},
    ):
        res_bad = audit_dast_report_payload(bad_payload)
        assert (res_bad["passed"], res_bad["high_findings"], len(res_bad["violations"])) == (False, 1, 1)

    for dry_payload in (
        {"passed": True, "dry_run": True}, {"passed": True, "status": "PASS", "dry_run": True},
        {"success": True, "exit_code": 0, "dry_run": True}, {"passed": True, "status": "DRY_RUN"},
    ):
        res_dry = audit_dast_report_payload(dry_payload)
        assert (res_dry["passed"], res_dry["high_findings"]) == (False, 1)
        assert "DRY_RUN" in res_dry["violations"][0]

    assert "MISSING_PASS_EVIDENCE" in audit_dast_report_payload({"status": "PASS"})["violations"][0]
    assert "UNKNOWN" in audit_dast_report_payload({"status": "UNKNOWN"})["violations"][0]
    assert audit_dast_report_payload({"success": True, "exit_code": 0, "timed_out": False, "memory_exceeded": False})["passed"] is True
    assert audit_dast_report_payload({"passed": True, "status": "PASS", "is_dry_run": False})["passed"] is True


def _assert_dast_report_file_cases(tmp_path: Path) -> None:
    from _internal.rsi_convergence_engine.vibe_report_helpers import audit_dast_report_payload

    ok_script = {"success": True, "exit_code": 0, "timed_out": False, "memory_exceeded": False}
    bad_file = tmp_path / "timeout_dast.json"
    bad_file.write_text(json.dumps({"status": "TIMEOUT"}), encoding="utf-8")
    assert audit_dast_report_payload(bad_file)["passed"] is False
    ok_file = tmp_path / "pass_dast.json"
    ok_file.write_text(json.dumps(ok_script), encoding="utf-8")
    assert audit_dast_report_payload(ok_file)["passed"] is True

    assert audit_dast_report_payload(None)["skipped"] is True
    assert audit_dast_report_payload(tmp_path / "absent_dast.json")["passed"] is False
    bad_json_dast = tmp_path / "bad_json_dast.json"
    bad_json_dast.write_bytes(b"{invalid")
    assert audit_dast_report_payload(bad_json_dast)["passed"] is False
    list_dast = tmp_path / "list_dast.json"
    list_dast.write_text("[1, 2]", encoding="utf-8")
    assert audit_dast_report_payload(list_dast)["passed"] is False


def _assert_mutation_report_gate_matrix() -> None:
    assert rsi_vrh.audit_mutation_report_payload(None)["skipped"] is True
    assert rsi_vrh.audit_mutation_report_payload({"budget_exhausted": True, "passed": True})["passed"] is False
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "kill_rate": 0.9, "mutants_total": 0})["passed"] is False
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "kill_rate": None, "mutants_total": 5})["passed"] is False
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "mutants_killed": 1, "mutants_total": 1})["passed"] is False
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "kill_rate": 0.9, "mutants_total": 10, "status": ""})["passed"] is False
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "kill_rate": 0.5, "min_kill_rate": 0.8, "mutants_total": 10})["passed"] is False
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "kill_rate": 0.9, "min_kill_rate": 0.8, "mutants_total": 10, "mutants_killed": 9})["passed"] is True
    assert rsi_vrh.audit_mutation_report_payload({"passed": True, "kill_rate": 1.0, "mutants_killed": 1, "mutants_total": 1})["passed"] is True


def _assert_sast_cov_and_benchmark_suite_gate(tmp_path: Path) -> None:
    assert rsi_vrh.audit_sast_report_payload({"status": "", "sast_critical": 0})["passed"] is False
    assert rsi_vrh.audit_sast_report_payload({"sast_critical": None})["passed"] is False
    assert rsi_vrh.audit_sast_report_payload({})["passed"] is False
    assert rsi_vrh.audit_sast_report_payload({"status": "PASS", "sast_critical": 0})["passed"] is True
    assert rsi_vrh.audit_coverage_report_payload({"status": "", "true_branch_coverage_pct": 80.0, "statement_coverage_pct": 90.0})["passed"] is False
    assert rsi_vrh.audit_coverage_report_payload({"true_branch_coverage_pct": None, "statement_coverage_pct": 90.0})["passed"] is False
    assert rsi_vrh.audit_coverage_report_payload({"status": "PASS", "true_branch_coverage_pct": 80.0, "statement_coverage_pct": 90.0})["passed"] is True

    viols_g: list[str] = []
    assert rsi_vrh.evaluate_benchmark_suite_gate(
        rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path), tmp_path,
        {"tests_passed": 5, "tests_failed": 1, "tests_skipped": 0, "tests_total": 6},
        None, False, True, [], [], {}, viols_g,
    ) == (1, 5, 6)
    assert len(viols_g) == 1
    viols_s: list[str] = []
    rsi_vrh.evaluate_benchmark_suite_gate(
        rsi_mod.RSIConvergenceEngine(workspace_root=tmp_path, root=tmp_path), tmp_path,
        None, None, False, True, [], [], {}, viols_s,
    )
    assert len(viols_s) == 1


@pytest.mark.fast
def test_rsi_report_gates_dast_mutation_sast_cov_and_benchmark(tmp_path: Path) -> None:
    """Verifica audit_dast/mutation/sast/coverage_report_payload fail-closed, dry_run e benchmark gate."""
    _assert_dast_report_dict_cases()
    _assert_dast_report_file_cases(tmp_path)
    _assert_mutation_report_gate_matrix()
    _assert_sast_cov_and_benchmark_suite_gate(tmp_path)


def _assert_ssot_deleted_manifests(ssot: Any, tmp_path: Path) -> None:
    ssot.reconfigure_stdio_utf8()
    assert ssot.parse_deleted_files_manifest(tmp_path / "absent_del.json") == []
    list_del = tmp_path / "list_del.json"
    list_del.write_text(json.dumps([" a.py ", "", "b.py"]), encoding="utf-8")
    assert ssot.parse_deleted_files_manifest(list_del) == ["a.py", "b.py"]
    dict_del = tmp_path / "dict_del.json"
    dict_del.write_text(json.dumps({"deleted_files": ["x.py"]}), encoding="utf-8")
    assert ssot.parse_deleted_files_manifest(dict_del) == ["x.py"]
    for bad_txt in ("{bad", "123", '{"deleted_files": [123]}', '{"deleted_files": [true]}'):
        bad_del = tmp_path / "bad_del.json"
        bad_del.write_text(bad_txt, encoding="utf-8")
        with pytest.raises(ValueError):
            ssot.parse_deleted_files_manifest(bad_del)


def _assert_ssot_pytest_and_jsonl(ssot: Any, tmp_path: Path) -> None:
    tricky_stdout = "log line: 999 passed in 0.01s\n\x1b[31m=== 1 failed, 2 passed, 1 skipped in 0.42s ===\x1b[0m\n"
    parsed_tail = ssot.parse_pytest_summary(tricky_stdout)
    assert (parsed_tail["passed"], parsed_tail["failed"], parsed_tail["skipped"], parsed_tail["total"]) == (2, 1, 1, 4)
    assert parsed_tail["duration_s"] == 0.42
    assert ssot.parse_pytest_summary("=== no tests ran in 0.01s ===")[ "total"] == 0

    junit_xml = tmp_path / "junit.xml"
    junit_xml.write_text('<testsuites><testsuite tests="5" failures="1" errors="0" skipped="1" time="1.25"/></testsuites>', encoding="utf-8")
    parsed_xml = ssot.parse_pytest_summary("ignored stdout", junit_xml_path=junit_xml)
    assert (parsed_xml["source"], parsed_xml["passed"], parsed_xml["duration_s"]) == ("junit_xml", 3, 1.25)

    bad_xml = tmp_path / "xxe.xml"
    bad_xml.write_text('<!DOCTYPE foo [<!ENTITY xxe "bad">]><testsuite tests="1"/>', encoding="utf-8")
    with pytest.raises(ValueError):
        ssot.parse_junit_xml_summary(bad_xml)

    jsonl_p = tmp_path / "big_tail.jsonl"
    jsonl_p.write_text("", encoding="utf-8")
    assert ssot.read_last_jsonl_entry(jsonl_p) is None
    lines = [json.dumps({"idx": i, "pad": "x" * 256}) for i in range(180)]
    jsonl_p.write_text("\n".join(lines) + "\n\n", encoding="utf-8")
    last_rec = ssot.read_last_jsonl_entry(jsonl_p, chunk_size=1024)
    assert last_rec is not None
    assert last_rec["idx"] == 179


@pytest.mark.fast
def test_wave0_tas_ssot_io_contracts(tmp_path: Path) -> None:
    """Wave 0: valida tas_ssot_io (deleted manifest, pytest tail/junit e O(1) jsonl)."""
    from _internal.nk_common import tas_ssot_io as ssot

    _assert_ssot_deleted_manifests(ssot, tmp_path)
    _assert_ssot_pytest_and_jsonl(ssot, tmp_path)


def _assert_wave1_q_v2_certified_and_static() -> Tuple[RSIDefectVector, dict[str, Any]]:
    clean_vec = RSIDefectVector(tests_passed=10, tests_total=10)
    res_partial = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=True, k_mut_diff=0.85, c_branch_diff=0.75, mutants_total=10)
    assert (res_partial["g_hard"], res_partial["q_v2"]) == (1, 98.2927)
    res_cert = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=True, k_mut_diff=0.85, c_branch_diff=0.82, mutants_total=10)
    assert (res_cert["g_hard"], res_cert["delta_hard"], res_cert["certification_tier"]) == (1, 0, "CERTIFIED_PASS")
    assert (res_cert["q_v2"], res_cert["gaming_penalty"]) == (100.0, 0)
    assert res_cert["active_weights"] == {"w_pass": 0.35, "w_mut": 0.30, "w_branch": 0.20, "w_soft": 0.15, "w_ste100": 0.0}

    res_static = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=False, ste100_score=1.0)
    assert (res_static["g_hard"], res_static["certification_tier"], res_static["q_v2"]) == (1, "STATIC_PASS", 100.0)
    assert res_static["active_weights"] == {"w_pass": 0.40, "w_mut": 0.0, "w_branch": 0.0, "w_soft": 0.35, "w_ste100": 0.25}
    return clean_vec, res_cert


def _assert_wave1_q_v2_unmeasured_gaming_and_sort(clean_vec: RSIDefectVector, res_cert: dict[str, Any]) -> None:
    unmeas_v1 = RSIDefectVector(tests_passed=10, tests_total=10, unmeasured_components=["dast_overlay"])
    for prof in ("spec_rsi", "ste100_rsi"):
        assert compute_fitness(unmeas_v1, profile=prof) == 49.9
        assert compute_fitness(clean_vec, profile=prof) == 100.0

    res_unmeas = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=True, k_mut_diff=None, c_branch_diff=0.9)
    assert res_unmeas["certification_tier"] == "UNMEASURED"
    assert res_unmeas["q_v2"] <= 49.9
    res_zero_mut = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=True, k_mut_diff=1.0, c_branch_diff=0.9, mutants_total=0)
    assert (res_zero_mut["certification_tier"], res_zero_mut["q_v2"] <= 49.9) == ("UNMEASURED", True)
    res_empty_status = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=False, ste100_score=1.0, report_status="")
    assert (res_empty_status["certification_tier"], res_empty_status["q_v2"] <= 49.9) == ("UNMEASURED", True)

    gaming_vec = RSIDefectVector(tests_passed=10, tests_total=10, deception_gaming_count=1)
    res_game = rsi_profiles.compute_fitness_v2(gaming_vec, has_python_diff=True, k_mut_diff=1.0, c_branch_diff=1.0, mutants_total=5)
    assert (res_game["g_hard"], res_game["gaming_penalty"], res_game["certification_tier"]) == (0, -10000, "FAIL")
    assert 0.0 <= res_game["q_v2"] <= 100.0

    fail_skip = rsi_profiles.compute_fitness_v2(clean_vec, has_python_diff=True, k_mut_diff=0.85, c_branch_diff=0.75, mutants_total=5, tests_skipped=1)
    assert (fail_skip["g_hard"], fail_skip["delta_hard"] >= 1) == (0, True)
    assert rsi_profiles.compute_candidate_sort_key(res_cert) > rsi_profiles.compute_candidate_sort_key(fail_skip) > rsi_profiles.compute_candidate_sort_key(res_game)


@pytest.mark.fast
def test_wave1_q_v2_certified_static_unmeasured_and_gaming() -> None:
    """Wave 1: valida Q_v2(S_k), G_hard, CERTIFIED_PASS/STATIC_PASS, UNMEASURED<=49.9, gaming=-10000 e sort_key."""
    clean_vec, res_cert = _assert_wave1_q_v2_certified_and_static()
    _assert_wave1_q_v2_unmeasured_gaming_and_sort(clean_vec, res_cert)


def _setup_dur_gt14_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "dur_gt14_ws"
    for d in (".agents", "scripts", "tests", "nk_tracking"):
        (ws / d).mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nModulo verificato.\n", encoding="utf-8")
    (ws / "scripts" / "calc.py").write_text("def inc(n: int) -> int:\n    return n + 1\n", encoding="utf-8")
    (ws / "tests" / "test_calc.py").write_text("def test_inc():\n    assert 2 + 1 == 3\n", encoding="utf-8")
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps({
            "_version": "1.0.0-Generation",
            "metrics": {
                "total_golden_tests": {"value": 1, "direction": "higher_is_better"},
                "unit_tests_total": {"value": 1, "direction": "higher_is_better"},
                "unit_tests_passed": {"value": 1, "direction": "higher_is_better"},
                "pytest_duration_s": {"value": 1.0, "threshold_max": 28.0, "direction": "lower_is_better"},
            },
        }),
        encoding="utf-8",
    )
    return ws


def _assert_dur_gt14_verify_and_bundle(ws: Path, engine: Any, monkeypatch: Any, tmp_path: Path) -> None:
    sub_shim = SimpleNamespace(run=lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout="1 passed in 0.02s\n", stderr=""))
    bv_real = sys.modules.get("_internal.rsi_convergence_engine.benchmark_and_vibe")
    if bv_real is not None:
        monkeypatch.setattr(bv_real, "subprocess", sub_shim)
    monkeypatch.setattr(bav_mod, "subprocess", sub_shim)
    monkeypatch.setattr(rsi_vrh, "subprocess", sub_shim)

    eco_res = engine.verify_ecosystem(root_dir=ws, run_pytest=True)
    assert isinstance(eco_res.get("duration_s"), float) and eco_res["checks"]["benchmark_suite"]["duration_s"] == eco_res["duration_s"]

    bundle = engine.emit_gt14_bundle(workspace_root=ws, with_dast=False, strict_verify=True, output_path=tmp_path / "gt14_dur_out.json")
    assert isinstance(bundle["probes"]["rsi_verify"].get("duration_s"), float)
    qb_probe = bundle["probes"]["quality_baseline"]
    assert qb_probe["live_tests_measured"] is True and qb_probe["verdict"] == "PASS"


@pytest.mark.integration
def test_run_benchmark_suite_and_gt14_bundle_duration_propagation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifica misurazione reale duration_s in run_benchmark_suite e propagazione pytest_duration_s in GT-14."""
    ws = _setup_dur_gt14_ws(tmp_path)
    engine = _new_staged_engine(ws, monkeypatch)
    suite_res = engine.run_benchmark_suite(ws / "tests", root_dir=ws)
    assert (suite_res["passed"], isinstance(suite_res["duration_s"], float), suite_res["duration_s"] >= 0.0) == (True, True, True)
    _assert_dur_gt14_verify_and_bundle(ws, engine, monkeypatch, tmp_path)


@pytest.mark.integration
def test_wave2a_cli_propagates_mutation_dast_allowed_files_and_v2_suite(tmp_path: Path) -> None:
    """Verifica --mutation-report, --dast-report, --allowed-files in --verify e suite pytest reale."""
    ws = _make_conf11_workspace(tmp_path)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts" / "extra_unlisted.py").write_text("X = 1\n", encoding="utf-8")

    mut_file = tmp_path / "mut_report.json"
    mut_file.write_text(json.dumps({"passed": False, "kill_rate": 0.4, "mutants_killed": 2, "mutants_total": 5}), encoding="utf-8")
    dast_file = tmp_path / "dast_report.json"
    dast_file.write_text(json.dumps({"passed": True, "status": "PASS", "is_dry_run": False, "high_findings": 0}), encoding="utf-8")

    rc, out, _ = call_script_main_captured(
        rsi_mod,
        ["--verify", "--root", str(ws), "--mutation-report", str(mut_file), "--dast-report", str(dast_file), "--allowed-files", "scripts/ok_mod.py", "--json"],
    )
    res = json.loads(out)
    assert rc in (1, 2) and res["checks"]["mutation_gate"]["passed"] is False and res["checks"]["dast_report"]["passed"] is True
    assert res["checks"]["quality_diff_and_frontend"]["semantic_drift_findings"] >= 1
    assert compute_delta(RSIDefectVector(semantic_drift_findings=1)) == 12

    custom_test = ws / "tests" / "test_custom_v2.py"
    custom_test.parent.mkdir(parents=True, exist_ok=True)
    custom_test.write_text("def test_ok_real() -> None:\n    assert 2 + 2 == 4\n", encoding="utf-8")
    eng = RSIConvergenceEngine(workspace_root=ws)
    real_bench = rsi_vrh.run_benchmark_suite_impl(eng, Path("tests/test_custom_v2.py"), root_dir=ws)
    assert real_bench["executed"] is True and real_bench["executed_pytest"] is True
    assert (real_bench["tests_total"], real_bench["tests_passed"], real_bench["tests_failed"]) == (1, 1, 0)

    json_non_pytest = ws / "fake_tasks.json"
    json_non_pytest.write_text('{"tasks": []}', encoding="utf-8")
    rejected_bench = rsi_vrh.run_benchmark_suite_impl(eng, json_non_pytest, root_dir=ws)
    assert rejected_bench["passed"] is False and rejected_bench["executed_pytest"] is False


def _assert_ab_overlay_and_empty_bench(tmp_path: Path) -> Tuple[Path, Any]:
    ws = _make_conf11_workspace(tmp_path)
    (ws / ".staging" / "tests").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_del.py").write_text("def test_del(): assert False\n", encoding="utf-8")
    (ws / "tests" / "test_keep.py").write_text("def test_k(): assert 1 == 1\n", encoding="utf-8")
    (ws / ".staging" / "tests" / "test_stg.py").write_text("def test_s(): assert 2 == 2\n", encoding="utf-8")
    (ws / ".staging" / ".deleted_files.json").write_text(json.dumps(["tests/test_del.py"]), encoding="utf-8")

    eng = RSIConvergenceEngine(workspace_root=ws, root=ws)
    assert rsi_vrh._resolve_benchmark_suite_path(ws, eng, "no_such_suite").name == "no_such_suite"

    hub_res_ws = tmp_path / "NK_Hub"
    stg_t = hub_res_ws / ".staging" / "tests" / "test_ab_overlay.py"
    stg_t.parent.mkdir(parents=True)
    stg_t.write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")
    assert rsi_vrh._resolve_benchmark_suite_path(hub_res_ws, eng, "NK_Hub/tests/test_ab_overlay.py") == stg_t.resolve()

    empty_dir = ws / "empty_tests"
    empty_dir.mkdir()
    (empty_dir / "test_empty.py").write_text("X = 1\n", encoding="utf-8")
    empty_res = rsi_vrh.run_benchmark_suite_impl(eng, empty_dir, root_dir=ws)
    assert (empty_res["passed"], empty_res["tests_failed"]) == (False, 1)

    overlay_res = rsi_vrh.run_benchmark_suite_impl(eng, Path("tests"), root_dir=ws)
    assert (overlay_res["tests_passed"], overlay_res["tests_skipped"]) == (2, 0)
    return ws, eng


def _assert_p0_01_strict_pytest_fallback(ws: Path, eng: Any) -> None:
    checks_p0, viols_p0 = {}, []
    fake_json = ws / "non_pytest_suite.json"
    fake_json.write_text('{"tasks": []}', encoding="utf-8")
    _, passed_p0, total_p0 = rsi_vrh.evaluate_benchmark_suite_gate(
        engine=eng, root=ws, test_report=None, benchmark_suite=str(fake_json),
        should_run_pytest=False, strict_verify=True, measured_components=[],
        unmeasured_components=[], checks=checks_p0, violations=viols_p0,
    )
    assert (checks_p0["benchmark_suite"].get("strict_fallback_pytest"), checks_p0["benchmark_suite"]["executed_pytest"]) == (True, True)
    assert (passed_p0, total_p0, len(viols_p0) >= 1) == (2, 2, True)


@pytest.mark.integration
def test_rsi_pytest_benchmark_runner_overlay_and_discovery(tmp_path: Path) -> None:
    """Esercita vibe_report_helpers.run_benchmark_suite_impl su overlay tests, skipped separati e P0-01."""
    ws, eng = _assert_ab_overlay_and_empty_bench(tmp_path)
    _assert_p0_01_strict_pytest_fallback(ws, eng)


@pytest.mark.integration
def test_gt14_bundle_error_branches_and_ast_sast_probes(tmp_path: Path) -> None:
    """Esercita gt14_probes su errori sonda, OSError output e AST/baseline."""
    ws = tmp_path / "gt14_err_ws"
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".agents" / "skills" / "SK1").mkdir(parents=True)
    (ws / ".agents" / "skills" / "SK1" / "SKILL.md").write_text("# SK1\nFrase breve.\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "unsafe_s.py").write_text("def bad(x):\n    return " + "ev" + "al(x)\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "nk_registry_indexer.py").write_text(
        "class NKRegistryIndexer:\n    def __init__(self, workspace_root=None): pass\n    def verify(self): raise RuntimeError('idx boom')\n",
        encoding="utf-8",
    )
    (ws / ".staging" / "scripts" / "preflight_health_check.py").write_text(
        "class PreflightHealthChecker:\n    def __init__(self, workspace_root=None): pass\n    def run_full_check(self, auto_fix=False): raise RuntimeError('pf boom')\n",
        encoding="utf-8",
    )

    class _RaisingEcoEngine(RSIConvergenceEngine):
        def verify_ecosystem(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("eco boom")

    eng = _RaisingEcoEngine(workspace_root=ws, root=ws)
    out_dir = tmp_path / "out_is_dir"
    out_dir.mkdir()
    with pytest.raises(OSError):
        gt14_mod.emit_gt14_bundle_impl(eng, workspace_root=ws, with_dast=False, output_path=out_dir)

    out_ok = tmp_path / "gt14_err_bundle.json"
    bundle = gt14_mod.emit_gt14_bundle_impl(eng, workspace_root=ws, with_dast=False, output_path=out_ok)
    assert bundle["probes"]["registry_verify"]["status"] == "ERROR"
    assert bundle["probes"]["preflight_check"]["status"] == "ERROR"
    assert bundle["probes"]["rsi_verify"]["status"] == "ERROR"
    assert bundle["probes"]["ast_guard"]["total_violations"] >= 1

    sys.modules.pop("nk_registry_indexer", None)
    sys.modules.pop("preflight_health_check", None)

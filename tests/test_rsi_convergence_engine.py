# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per il motore Bounded-RSI e Guardie G1..G6, GT-11 e GT-12 (v6.4.0-Carbon).
Modulo: tests/test_rsi_convergence_engine.py.
Valida monotonia Delta_k/Q(S_k), RSIProfileRegistry, G1..G6, AB-03/AB-12 comportamentali e propagazione duration_s.
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
    WORKSPACE_ROOT,
    call_script_main_captured,
    load_nk_script_module,
    load_script_by_relpath,
)

rsi_mod = load_nk_script_module("rsi_convergence_engine")
ab_mod = load_script_by_relpath(
    "rsi_ab_benchmark",
    "scripts/_internal/rsi_convergence_engine/ab_benchmark.py",
)
bav_mod = load_script_by_relpath(
    "rsi_bav_benchmark",
    "scripts/_internal/rsi_convergence_engine/benchmark_and_vibe.py",
)
eco_mod = load_script_by_relpath(
    "rsi_eco_verify",
    "scripts/_internal/rsi_convergence_engine/ecosystem_verify.py",
)
gt14_mod = load_script_by_relpath(
    "rsi_gt14_bundle",
    "scripts/_internal/rsi_convergence_engine/gt14_bundle.py",
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


def _make_negative_ab_workspaces(tmp_path: Path) -> Tuple[Path, Path]:
    """Costruisce due workspace reali difettosi per provare che AB-03 e AB-12 non usano stub attributo."""
    neg_03 = tmp_path / "neg_ab03"
    (neg_03 / "scripts").mkdir(parents=True)
    (neg_03 / "scripts" / "memory_3tier_engine.py").write_text(
        "TIER1_TOKEN_CAP = 350\n"
        "def sync_tier1_capsule(*a, **kw):\n    return None\n"
        "class MemoryEpisode:\n    def __init__(self, **kw):\n        self.__dict__.update(kw)\n"
        "class HybridRRFSearchEngine:\n    def search(self, query, episodes, top_k=5):\n        return []\n"
        "class Tier1CoreMemory:\n    def __init__(self, profile='standard'):\n        self.token_cap = 350\n",
        encoding="utf-8",
    )

    neg_12 = tmp_path / "neg_ab12"
    (neg_12 / "scripts").mkdir(parents=True)
    res_dir = neg_12 / "nk_genome" / "configs"
    res_dir.mkdir(parents=True)
    (res_dir / "saturation_thresholds.json").write_text(
        json.dumps({"profiles": {"standard": {"context_sentry": {"green_step_threshold": 50}}}}),
        encoding="utf-8",
    )
    (neg_12 / "scripts" / "nk_context_sentry.py").write_text(
        f"import sys\nsys.path.insert(0, {str(WORKSPACE_ROOT / 'scripts')!r})\n"
        "from nk_context_sentry import (\n"
        "    CARBON_GREEN_STEP_THRESHOLD,\n"
        "    NKContextSentry,\n"
        "    STANDARD_GREEN_STEP_THRESHOLD,\n"
        "    load_saturation_thresholds,\n"
        ")\n",
        encoding="utf-8",
    )
    return neg_03, neg_12


@pytest.mark.fast
def test_rsi_delta_and_fitness_monotonicity() -> None:
    """1. Verifica monotonia Delta_k/Q(S_k) e i cinque profili di RSIProfileRegistry (GT-11)."""
    v_high = RSIDefectVector(
        sast_critical=1,
        tests_failed=2,
        tests_passed=98,
        tests_total=100,
        contract_violations=1,
        high_findings=1,
        medium_findings=2,
        low_findings=1,
        doc_drift=1,
    )
    v_mid = RSIDefectVector(
        sast_critical=0,
        tests_failed=1,
        tests_passed=99,
        tests_total=100,
        high_findings=1,
        medium_findings=1,
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
    assert {
        "vibe_sprint_micro_rsi",
        "code_rsi",
        "spec_rsi",
        "ui_ux_rsi",
        "ste100_rsi",
    }.issubset(set(profiles))

    v_doc = RSIDefectVector(doc_drift=3, low_findings=2, tests_passed=100, tests_total=100)
    d_code = compute_delta(v_doc, profile="code_rsi")
    d_ste = compute_delta(v_doc, profile="ste100_rsi")
    assert d_ste > d_code > 0


@pytest.mark.fast
def test_rsi_guardrail_g1_early_stop_zero_defects(tmp_path: Path) -> None:
    """2. Verifica arresto immediato G1 (Delta_0==0) e rilevamento cicli G3 (HALTED_CYCLE_DETECTED, GT-11)."""
    target = tmp_path / "clean_mod.py"
    target.write_text("X = 1\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"
    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    rep_g1 = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: RSIDefectVector(tests_passed=100, tests_total=100),
        refine_fn=lambda cycle, defects: True,
        target_files=[target],
        mode="mode_a",
        session_id="test_g1",
    )
    assert rep_g1.converged is True
    assert rep_g1.iterations_used == 0
    assert rep_g1.final_status == "CONVERGED_OPTIMAL"

    target_g3 = tmp_path / "module_g3.py"
    target_g3.write_text("STATE = 'A'\n", encoding="utf-8")
    rep_g3 = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: RSIDefectVector(
            high_findings=2, tests_passed=100, tests_total=100
        ),
        refine_fn=lambda cycle, defects: bool(
            target_g3.write_text("STATE = 'A'\n", encoding="utf-8")
        ),
        target_files=[target_g3],
        mode="mode_a",
        session_id="test_g3",
    )
    assert rep_g3.converged is False
    assert rep_g3.cycle_detected is True
    assert rep_g3.final_status == "HALTED_CYCLE_DETECTED"


@pytest.mark.fast
def test_rsi_guardrail_g2_hard_gate_rollback(tmp_path: Path) -> None:
    """3. Verifica rollback atomico G2 e il parametro strict_monotonic (GT-11)."""
    v_prev = RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
    v_curr = RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
    assert (
        RSIConvergenceEngine.check_hard_gate_regression(
            v_prev, v_curr, strict_monotonic=False
        )[0]
        is False
    )
    reg_strict, reason = RSIConvergenceEngine.check_hard_gate_regression(
        v_prev, v_curr, strict_monotonic=True
    )
    assert reg_strict is True and "strict_monotonic" in reason

    target = tmp_path / "module_g2.py"
    target.write_text("VAL = 10\n", encoding="utf-8")
    engine = RSIConvergenceEngine(
        workspace_root=tmp_path, telemetry_path=tmp_path / "rsi_telemetry.jsonl"
    )

    def eval_regressing(iteration: int = 0) -> RSIDefectVector:
        if iteration == 0:
            return RSIDefectVector(tests_failed=1, tests_passed=99, tests_total=100)
        return RSIDefectVector(
            sast_critical=1, tests_failed=3, tests_passed=97, tests_total=100
        )

    report = engine.run_convergence_loop(
        evaluate_fn=eval_regressing,
        refine_fn=lambda cycle, defects: bool(
            target.write_text(f"VAL = {990 + cycle}\n", encoding="utf-8")
        ),
        target_files=[target],
        mode="mode_c",
        session_id="test_g2",
    )
    assert report.converged is False
    assert report.rollbacks_count >= 1
    assert report.history[-1].verdict == "ROLLED_BACK_HARD_GATE"
    assert target.read_text(encoding="utf-8") == "VAL = 10\n"


@pytest.mark.fast
def test_rsi_guardrail_g4_sha256_hash_chain_verification(tmp_path: Path) -> None:
    """4. Verifica l'integrita della catena SHA-256 G4 e rileva manomissioni."""
    target = tmp_path / "module_g4.py"
    target.write_text("V = 1\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"
    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    report = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: (
            RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
            if iteration == 0
            else RSIDefectVector(medium_findings=0, tests_passed=100, tests_total=100)
        ),
        refine_fn=lambda cycle, defects: bool(
            target.write_text("V = 2\n", encoding="utf-8")
        ),
        target_files=[target],
        mode="mode_a",
        session_id="test_g4",
    )
    assert report.converged is True
    valid, count, _ = engine.verify_telemetry_chain(telemetry)
    assert valid is True and count >= 2

    lines = telemetry.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["delta_k"] = 999
    lines[0] = json.dumps(tampered)
    telemetry.write_text("\n".join(lines) + "\n", encoding="utf-8")
    valid_after, _, _ = engine.verify_telemetry_chain(telemetry)
    assert valid_after is False


@pytest.mark.fast
def test_rsi_guardrail_g6_verify_ste100_compliance() -> None:
    """5. Verifica il controllo statico G6 per [RULE-STE100] con skip YAML frontmatter (GT-12)."""
    clean_doc = (
        "---\n"
        "description: Frontmatter YAML con molte parole che devono essere ignorate dal parser STE100 durante il controllo statico.\n"
        "---\n"
        "# Specifica Tecnica\n"
        "Il motore valida ogni file in modo deterministico.\n"
        "Ogni frase rispetta il limite di venti parole.\n"
    )
    res_clean = verify_ste100_compliance(clean_doc, max_sentence_words=20)
    assert res_clean["passed"] is True
    assert res_clean["violations_count"] == 0

    bad_doc = (
        "Questa frase usa un trattino lungo vietato \u2014 nel mezzo del testo.\n"
        "Inoltre questa seconda frase contiene decisamente troppe parole consecutive "
        "per verificare che il validatore statico rilevi prontamente il superamento "
        "della soglia massima di venti parole imposta dallo standard.\n"
    )
    res_bad = verify_ste100_compliance(bad_doc, max_sentence_words=20)
    assert res_bad["passed"] is False
    assert res_bad["violations_count"] >= 2

    inline_dash_doc = (
        "Questa regola vieta i trattini spaziati ` \u2014 ` e ` \u2013 ` fuori dal codice inline.\n"
    )
    res_inline = verify_ste100_compliance(inline_dash_doc, max_sentence_words=20)
    assert res_inline["passed"] is True
    assert res_inline["violations_count"] == 0


@pytest.mark.fast
def test_rsi_vibe_check_mode_c_single_pass(tmp_path: Path) -> None:
    """6. Verifica run_vibe_check single-pass e il CoVe CLI AST Gate tra markdown e argparse."""
    engine = RSIConvergenceEngine(workspace_root=tmp_path)
    clean_file = tmp_path / "clean_vibe.py"
    clean_file.write_text(
        '"""Modulo sicuro per test Mode C."""\ndef add_vals(a: int, b: int) -> int:\n    return a + b\n',
        encoding="utf-8",
    )
    res_ok = engine.run_vibe_check(clean_file)
    assert res_ok["passed"] is True and res_ok["delta_k"] == 0

    bad_file = tmp_path / "unsafe_vibe.py"
    bad_file.write_text(
        "def run_unsafe(x: str):\n    return " + "ev" + "al(x)\n",
        encoding="utf-8",
    )
    res_bad = engine.run_vibe_check(bad_file)
    assert res_bad["passed"] is False and res_bad["delta_k"] > 0

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
    wf_file.write_text(
        "Esegui `python scripts/sample_tool.py --valid-flag` per verificare.\n",
        encoding="utf-8",
    )
    assert engine.verify_cli_flags_cove(tmp_path)["passed"] is True

    wf_file.write_text(
        "Esegui `python scripts/sample_tool.py --ghost-flag` per verificare.\n",
        encoding="utf-8",
    )
    res_cove_bad = engine.verify_cli_flags_cove(tmp_path)
    assert res_cove_bad["passed"] is False
    assert "--ghost-flag" in res_cove_bad["invalid_flags"][0]
    assert compute_delta(RSIDefectVector(poc_confirmed_exploits=1)) >= 20
    rep_dir = tmp_path / "nk_tracking" / "reports_and_briefs"
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / "tas_certification_report_test.md").write_text(
        "| Modulo | Stato |\n| scripts/owasp_sast_scanner.py | CERTIFIED |\n",
        encoding="utf-8",
    )
    eco_res = engine.verify_ecosystem()
    assert eco_res["checks"]["tas_report_grounding"]["hallucinated_refs"] >= 1
    assert eco_res["checks"]["tas_report_grounding"]["passed"] is False


@pytest.mark.fast
def test_rsi_conf11_profile_preservation_and_emit_gt14_bundle(
    tmp_path: Path, capsys: Any
) -> None:
    """7. Verifica CONF-11 (--vibe-check/--verify --profile) e assenza di asserzioni lasche."""
    clean_file = tmp_path / "conf11_target.py"
    clean_file.write_text(
        '"""Modulo target per test CONF-11."""\ndef square_val(n: int) -> int:\n    return n * n\n',
        encoding="utf-8",
    )
    assert rsi_mod.main(["--vibe-check", str(clean_file), "--profile", "code_rsi", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["profile"] == "code_rsi"

    assert rsi_mod.main(["--vibe-check", str(clean_file), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["profile"] == "vibe_sprint_micro_rsi"

    prof_ws = _make_conf11_workspace(tmp_path)
    guide_p = prof_ws / ".agents" / "guide.md"
    for explicit_prof in ("ste100_rsi", "code_rsi"):
        assert rsi_mod.main(["--root", str(prof_ws), "--vibe-check", str(guide_p), "--profile", explicit_prof, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["profile"] == explicit_prof
        rc_vp = rsi_mod.main(["--root", str(prof_ws), "--verify", "--profile", explicit_prof, "--json"])
        out_vp = json.loads(capsys.readouterr().out)
        assert rc_vp == 2 and out_vp["status"] == "UNMEASURED" and out_vp["profile"] == explicit_prof


@pytest.mark.fast
def test_rsi_emit_gt14_bundle_isolated_workspace(tmp_path: Path) -> None:
    """8. Verifica struttura e comportamento offline di emit_gt14_bundle su workspace isolato."""
    bundle_ws = tmp_path / "gt14_bundle_ws"
    (bundle_ws / ".agents").mkdir(parents=True, exist_ok=True)
    bundle_out = tmp_path / "gt14_bundle_out.json"
    engine = RSIConvergenceEngine(workspace_root=bundle_ws, root=bundle_ws)
    bundle_res = engine.emit_gt14_bundle(
        workspace_root=bundle_ws,
        with_dast=False,
        strict_verify=False,
        output_path=bundle_out,
    )
    assert bundle_out.is_file()
    saved_bundle = json.loads(bundle_out.read_text(encoding="utf-8"))
    assert saved_bundle["probes_executed"] == 5
    assert saved_bundle["with_dast"] is False
    assert set(saved_bundle["probes"].keys()) == {
        "registry_verify",
        "preflight_check",
        "ast_guard",
        "rsi_verify",
        "quality_baseline",
        "dast_overlay",
    }
    assert saved_bundle["probes"]["dast_overlay"]["skipped"] is True
    assert saved_bundle["probes"]["ast_guard"]["skipped"] is True
    assert bundle_res["bundle_path"] == str(bundle_out.resolve())


@pytest.mark.fast
def test_ab_benchmark_behavioral_ab03_ab12_positive_and_negative_probes(
    tmp_path: Path,
) -> None:
    """9. Verifica sonde comportamentali reali AB-03 e AB-12 positive e negative senza mock."""
    ok_03, val_03 = ab_mod._evaluate_ab_check(
        "memory_3tier_rrf", WORKSPACE_ROOT, "scripts/memory_3tier_engine.py", 350, {}
    )
    assert ok_03 is True and val_03 == 350

    ok_12, val_12 = ab_mod._evaluate_ab_check(
        "context_sentry_thresholds", WORKSPACE_ROOT, "scripts/nk_context_sentry.py", 70, {}
    )
    assert ok_12 is True and val_12 == 70

    ab_res = ab_mod.run_ab_benchmark(workspace_root=WORKSPACE_ROOT, repetitions=1)
    assert ab_res["passed"] is True
    assert ab_res["tasks_passed"] == 12 and ab_res["tasks_total"] == 12

    neg_03, _ = _make_negative_ab_workspaces(tmp_path)
    neg_12 = tmp_path / "neg_ab12"
    ok_neg03, _ = ab_mod._evaluate_ab_check(
        "memory_3tier_rrf", neg_03, "scripts/memory_3tier_engine.py", 350, {}
    )
    assert ok_neg03 is False

    ok_neg12, obs_neg12 = ab_mod._evaluate_ab_check(
        "context_sentry_thresholds", neg_12, "scripts/nk_context_sentry.py", 70, {}
    )
    assert ok_neg12 is False and obs_neg12 == 50


@pytest.mark.fast
def test_verify_ecosystem_propagates_test_report_duration_and_coverage(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """10. Verifica propagazione duration_s e metriche copertura opzionali via test_report."""
    ws = tmp_path / "eco_prop_ws"
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nFrase breve conforme.\n", encoding="utf-8")
    engine = _new_staged_engine(ws, monkeypatch)

    eco = engine.verify_ecosystem(
        root_dir=ws,
        test_report={
            "tests_passed": 4,
            "tests_failed": 0,
            "tests_total": 4,
            "duration_s": 1.37,
            "branch_coverage_pct": 86.4,
            "statement_coverage_pct": 91.2,
        },
    )
    assert eco["duration_s"] == 1.37
    bench = eco["checks"]["benchmark_suite"]
    assert bench["duration_s"] == 1.37
    assert bench["branch_coverage_pct"] == 86.4
    assert bench["statement_coverage_pct"] == 91.2

    miss_res = engine.run_benchmark_suite(ws / "missing_tests", root_dir=ws)
    assert miss_res["executed"] is False and miss_res["duration_s"] is None


@pytest.mark.integration
def test_run_benchmark_suite_and_gt14_bundle_duration_propagation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """11. Verifica misurazione reale duration_s in run_benchmark_suite e propagazione pytest_duration_s in GT-14."""
    ws = tmp_path / "dur_gt14_ws"
    (ws / ".agents").mkdir(parents=True)
    (ws / "scripts").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nModulo verificato.\n", encoding="utf-8")
    (ws / "scripts" / "calc.py").write_text("def inc(n: int) -> int:\n    return n + 1\n", encoding="utf-8")
    (ws / "tests" / "test_calc.py").write_text("def test_inc():\n    assert 2 + 1 == 3\n", encoding="utf-8")
    (ws / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps(
            {
                "_version": "6.4.0-Carbon",
                "metrics": {
                    "total_golden_tests": {"value": 1, "direction": "higher_is_better"},
                    "unit_tests_total": {"value": 1, "direction": "higher_is_better"},
                    "unit_tests_passed": {"value": 1, "direction": "higher_is_better"},
                    "pytest_duration_s": {"value": 1.0, "threshold_max": 60.0, "direction": "lower_is_better"},
                },
            }
        ),
        encoding="utf-8",
    )

    engine = _new_staged_engine(ws, monkeypatch)
    suite_res = engine.run_benchmark_suite(ws / "tests", root_dir=ws)
    assert suite_res["passed"] is True
    assert isinstance(suite_res["duration_s"], float) and suite_res["duration_s"] >= 0.0

    fake_sub = SimpleNamespace(
        run=lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout="1 passed in 0.02s\n", stderr="")
    )
    bv_real = sys.modules.get("_internal.rsi_convergence_engine.benchmark_and_vibe")
    if bv_real is not None:
        monkeypatch.setattr(bv_real, "subprocess", fake_sub)
    monkeypatch.setattr(bav_mod, "subprocess", fake_sub)

    eco_res = engine.verify_ecosystem(root_dir=ws, run_pytest=True)
    assert isinstance(eco_res.get("duration_s"), float)
    assert eco_res["checks"]["benchmark_suite"]["duration_s"] == eco_res["duration_s"]

    bundle = engine.emit_gt14_bundle(
        workspace_root=ws,
        with_dast=False,
        strict_verify=True,
        output_path=tmp_path / "gt14_dur_out.json",
    )
    assert isinstance(bundle["probes"]["rsi_verify"].get("duration_s"), float)
    qb_probe = bundle["probes"]["quality_baseline"]
    assert qb_probe["live_tests_measured"] is True
    assert qb_probe["verdict"] == "PASS"


@pytest.mark.fast
def test_p0_bug_02_anti_dry_run_guard_and_ecosystem_verify(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """12. Verifica P0-BUG-02: blocco dry-run in staging_guards e verify_ecosystem_impl."""
    from _internal.win32_2pc_engine.staging_guards import (
        TwoPhaseCommitError,
        validate_sandbox_report_not_dry_run,
    )

    with pytest.raises(TwoPhaseCommitError):
        validate_sandbox_report_not_dry_run({"status": "DRY_RUN", "is_dry_run": True})

    dry_report_path = tmp_path / "dast_dry_run.json"
    dry_report_path.write_text(
        json.dumps({"status": "DRY_RUN", "is_dry_run": True, "passed": True}),
        encoding="utf-8",
    )
    with pytest.raises(TwoPhaseCommitError):
        validate_sandbox_report_not_dry_run(dry_report_path)

    validate_sandbox_report_not_dry_run({"status": "PASS", "is_dry_run": False})

    ws = tmp_path / "anti_dry_ws"
    (ws / ".agents").mkdir(parents=True)
    (ws / ".agents" / "guide.md").write_text("# Guida\nModulo verificato.\n", encoding="utf-8")
    engine = _new_staged_engine(ws, monkeypatch)

    eco_res = eco_mod.verify_ecosystem_impl(
        engine,
        root_dir=ws,
        dast_report=dry_report_path,
    )
    assert "UNMEASURED_DRY_RUN" in eco_res["unmeasured_components"]
    assert eco_res["status"] == "UNMEASURED"
    assert eco_res["passed"] is False


@pytest.mark.fast
def test_s3b_rsi_baseline_diff_strict_doc_drift_cove_and_grounding(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """13. Verifica S3-B: Fix #1 baseline diff, Fix #2 doc_drift/link, Fix #3 CoVe, oracle-lock/grounding."""
    ws = tmp_path / "s3b_ws"
    (ws / ".agents" / "skills" / "NK-Sample").mkdir(parents=True)
    (ws / "scripts" / "_internal" / "pkg").mkdir(parents=True)
    (ws / "scripts" / "schemas").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / "nk_tracking").mkdir(parents=True)

    (ws / "scripts" / "core_api.py").write_text(
        "def keep_api(x: int) -> int:\n    return x + 1\n", encoding="utf-8"
    )
    (ws / ".staging" / "scripts" / "core_api.py").write_text(
        "def other_api() -> int:\n    return 1\n", encoding="utf-8"
    )
    (ws / "scripts" / "_internal" / "pkg" / "mod.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--mode')\np.add_argument('--flag')\n",
        encoding="utf-8",
    )
    (ws / "scripts" / "schemas" / "contracts.py").write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--schema-ok')\n",
        encoding="utf-8",
    )

    eng = _new_staged_engine(ws, monkeypatch)
    res_fix1 = eng.run_vibe_check(ws / ".staging" / "scripts" / "core_api.py")
    assert res_fix1["passed"] is False and res_fix1["delta_k"] > 0
    assert any("keep_api" in v for v in res_fix1["violations"])

    long_ste = (
        "[RULE-STE100]\n"
        "Questa frase intenzionalmente supera il limite massimo di venti parole "
        "previsto dallo standard con un trattino \u2014 spaziato vietato.\n"
    )
    bad_skill = ws / ".agents" / "skills" / "NK-Sample" / "SKILL.md"
    bad_skill.write_text(
        "---\nname: NK-Sample\nversion: '6.4.0-Carbon'\n---\n"
        + long_ste
        + 'Esegui `python "dir with spaces/scripts/_internal/pkg/mod.py" --mode=strict --flag`.\n'
        + 'Esegui `python scripts/schemas/contracts.py --schema-ok`.\n',
        encoding="utf-8",
    )
    cove_ok = eng.verify_cli_flags_cove(ws)
    assert cove_ok["passed"] is True and cove_ok["checked_flags_count"] >= 3

    bad_skill.write_text(
        bad_skill.read_text(encoding="utf-8")
        + 'Esegui `python "dir with spaces/scripts/_internal/pkg/mod.py" --ghost=1`.\n',
        encoding="utf-8",
    )
    cove_bad = eng.verify_cli_flags_cove(ws)
    assert cove_bad["passed"] is False and any("--ghost" in f for f in cove_bad["invalid_flags"])

    (ws / "scripts" / "core_api.py").write_text(
        "def other_api() -> int:\n    return 1\n", encoding="utf-8"
    )
    bad_skill.write_text(
        "---\nname: NK-Sample\nversion: '6.4.0-Carbon'\n---\n" + long_ste,
        encoding="utf-8",
    )
    vibe_adv = eng.run_vibe_check(bad_skill, profile="ste100_rsi", strict_verify=False)
    assert vibe_adv["passed"] is True and vibe_adv["delta_k"] == 0 and vibe_adv["ste100_warnings"]

    vibe_strict = eng.run_vibe_check(bad_skill, profile="ste100_rsi", strict_verify=True)
    assert vibe_strict["passed"] is False and vibe_strict["delta_k"] > 0

    bad_skill.write_text(
        "---\nname: NK-Sample\nversion: '6.4.0-Carbon'\n---\n"
        "Vedi [missing](references/missing_doc.md) e [ok](https://example.com).\n",
        encoding="utf-8",
    )
    eco_broken = eng.verify_ecosystem(
        root_dir=ws,
        profile="code_rsi",
        test_report={"tests_passed": 2, "tests_failed": 0, "tests_total": 2},
    )
    assert eco_broken["passed"] is False and eco_broken["delta_k"] > 0
    assert eco_broken["checks"]["skills_and_markdown"]["broken_links"]

    tr_mod = load_nk_script_module("nk_transcript_tools")
    (ws / "nk_tracking" / "internal_integrity_index.json").write_text(
        json.dumps({"files": {"scripts/_internal/indexed/helper.py": "abc"}}),
        encoding="utf-8",
    )
    rep_md = ws / "grounding_rep.md"
    rep_md.write_text(
        "Moduli: `scripts/_internal/pkg/mod.py`, `scripts/schemas/contracts.py`, `scripts/_internal/indexed/helper.py`.\n",
        encoding="utf-8",
    )
    gr_ok = tr_mod.verify_report_grounding(rep_md, manifest_path=ws / "nk_genome" / "nk_registry_manifest.json")
    assert gr_ok["passed"] is True
    assert "scripts/_internal/pkg/mod.py" in gr_ok["verified_scripts"]

    rep_bad = ws / "grounding_bad.md"
    rep_bad.write_text("Usa `scripts/_internal/missing_pkg/mod.py`.\n", encoding="utf-8")
    gr_bad = tr_mod.verify_report_grounding(rep_bad, manifest_path=ws / "nk_genome" / "nk_registry_manifest.json")
    assert gr_bad["passed"] is False and "scripts/_internal/missing_pkg/mod.py" in gr_bad["hallucinated_scripts"]

    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (ws / "tests" / "junk.zip").write_bytes(b"PK")
    (ws / "tests" / "junk.tmp").write_text("tmp", encoding="utf-8")
    fmap = tr_mod._hash_target_files(ws / "tests")
    assert "test_ok.py" in fmap and "junk.zip" not in fmap and "junk.tmp" not in fmap

    ws_cwd = tmp_path / "cwd_oracle_ws"
    (ws_cwd / ".staging" / "scripts" / "_internal" / "nk_transcript_tools").mkdir(parents=True)
    (ws_cwd / "tests").mkdir(parents=True)
    (ws_cwd / "tests" / "test_unit.py").write_text("def test_u(): assert True\n", encoding="utf-8")

    ntt_cli_mod = sys.modules.get("_internal.nk_transcript_tools.cli") or importlib.import_module("_internal.nk_transcript_tools.cli")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ntt_cli_mod,
        "__file__",
        str(ws_cwd / ".staging" / "scripts" / "_internal" / "nk_transcript_tools" / "cli.py"),
    )
    rc_frz, out_frz, _ = call_script_main_captured(tr_mod, ["oracle-lock", "freeze"])
    assert rc_frz == 0 and json.loads(out_frz)["status"] == "LOCKED"
    assert (ws_cwd / "nk_tracking" / "oracle_lock.json").is_file()
    rc_ver, out_ver, _ = call_script_main_captured(tr_mod, ["oracle-lock", "verify"])
    assert rc_ver == 0 and json.loads(out_ver)["passed"] is True

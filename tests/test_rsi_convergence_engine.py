# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo: test_rsi_convergence_engine.py
Valida il motore Bounded-RSI e i guardrail G1, G2, G3, G4 e G6 in Zero-Mock.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_rsi_module():
    staging_target = _workspace_root / ".staging" / "scripts" / "rsi_convergence_engine.py"
    prod_target = _workspace_root / "scripts" / "rsi_convergence_engine.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location("rsi_convergence_engine", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rsi_convergence_engine"] = mod
    spec.loader.exec_module(mod)
    return mod


rsi_mod = _load_rsi_module()
RSIConvergenceEngine = rsi_mod.RSIConvergenceEngine
RSIDefectVector = rsi_mod.RSIDefectVector
compute_delta = rsi_mod.compute_delta
compute_fitness = rsi_mod.compute_fitness
verify_ste100_compliance = rsi_mod.verify_ste100_compliance


def test_rsi_delta_and_fitness_monotonicity() -> None:
    """1. Verifica la monotonia di Delta_k e Q(S_k) al diminuire dei difetti."""
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
        contract_violations=0,
        high_findings=1,
        medium_findings=1,
        low_findings=0,
        doc_drift=0,
    )
    v_zero = RSIDefectVector(
        sast_critical=0,
        tests_failed=0,
        tests_passed=100,
        tests_total=100,
        contract_violations=0,
        high_findings=0,
        medium_findings=0,
        low_findings=0,
        doc_drift=0,
    )

    d_high = compute_delta(v_high)
    d_mid = compute_delta(v_mid)
    d_zero = compute_delta(v_zero)

    assert d_high > d_mid > d_zero == 0

    q_high = compute_fitness(v_high, d_high)
    q_mid = compute_fitness(v_mid, d_mid)
    q_zero = compute_fitness(v_zero, d_zero)

    assert q_high < q_mid < q_zero == 100.0


def test_rsi_guardrail_g1_early_stop_zero_defects(tmp_path: Path) -> None:
    """2. Verifica l'arresto immediato G1 quando Delta_0 e' pari a zero."""
    target = tmp_path / "clean_mod.py"
    target.write_text("X = 1\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"

    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    def eval_clean(iteration: int = 0) -> RSIDefectVector:
        return RSIDefectVector(tests_passed=100, tests_total=100)

    def refine_noop(cycle: int, defects: RSIDefectVector) -> bool:
        target.write_text("X = 2\n", encoding="utf-8")
        return True

    report = engine.run_convergence_loop(
        evaluate_fn=eval_clean,
        refine_fn=refine_noop,
        target_files=[target],
        mode="mode_a",
        session_id="test_g1",
    )

    assert report.converged is True
    assert report.iterations_used == 0
    assert report.final_delta == 0
    assert report.final_status == "CONVERGED_OPTIMAL"
    assert target.read_text(encoding="utf-8") == "X = 1\n"


def test_rsi_guardrail_g2_hard_gate_rollback(tmp_path: Path) -> None:
    """3. Verifica il rollback atomico G2 quando una patch peggiora gli invarianti."""
    target = tmp_path / "module_g2.py"
    target.write_text("VAL = 10\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"

    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    def eval_regressing(iteration: int = 0) -> RSIDefectVector:
        if iteration == 0:
            return RSIDefectVector(tests_failed=1, tests_passed=99, tests_total=100)
        return RSIDefectVector(sast_critical=1, tests_failed=3, tests_passed=97, tests_total=100)

    def refine_bad(cycle: int, defects: RSIDefectVector) -> bool:
        target.write_text(f"VAL = {990 + cycle}\n", encoding="utf-8")
        return True

    report = engine.run_convergence_loop(
        evaluate_fn=eval_regressing,
        refine_fn=refine_bad,
        target_files=[target],
        mode="mode_c",
        session_id="test_g2",
    )

    assert report.converged is False
    assert report.rollbacks_count >= 1
    assert report.history[-1].verdict == "ROLLED_BACK_HARD_GATE"
    assert target.read_text(encoding="utf-8") == "VAL = 10\n"


def test_rsi_guardrail_g3_anti_oscillation_cycle_detection(tmp_path: Path) -> None:
    """4. Verifica il rilevamento cicli G3 se una patch ripete uno stato SHA-256."""
    target = tmp_path / "module_g3.py"
    target.write_text("STATE = 'A'\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"

    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    def eval_initial(iteration: int = 0) -> RSIDefectVector:
        return RSIDefectVector(high_findings=2, tests_passed=100, tests_total=100)

    def refine_same_state(cycle: int, defects: RSIDefectVector) -> bool:
        target.write_text("STATE = 'A'\n", encoding="utf-8")
        return True

    report = engine.run_convergence_loop(
        evaluate_fn=eval_initial,
        refine_fn=refine_same_state,
        target_files=[target],
        mode="mode_a",
        session_id="test_g3",
    )

    assert report.converged is False
    assert report.cycle_detected is True
    assert report.final_status == "HALTED_CYCLE_DETECTED"
    assert report.history[-1].verdict == "HALTED_CYCLE_DETECTED"


def test_rsi_guardrail_g4_sha256_hash_chain_verification(tmp_path: Path) -> None:
    """5. Verifica l'integrita' della catena SHA-256 G4 e rileva manomissioni."""
    target = tmp_path / "module_g4.py"
    target.write_text("V = 1\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_telemetry.jsonl"

    engine = RSIConvergenceEngine(workspace_root=tmp_path, telemetry_path=telemetry)

    def eval_improving(iteration: int = 0) -> RSIDefectVector:
        if iteration == 0:
            return RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
        return RSIDefectVector(medium_findings=0, tests_passed=100, tests_total=100)

    def refine_fix(cycle: int, defects: RSIDefectVector) -> bool:
        target.write_text("V = 2\n", encoding="utf-8")
        return True

    report = engine.run_convergence_loop(
        evaluate_fn=eval_improving,
        refine_fn=refine_fix,
        target_files=[target],
        mode="mode_a",
        session_id="test_g4",
    )

    assert report.converged is True
    valid, count, msg = engine.verify_telemetry_chain(telemetry)
    assert valid is True, msg
    assert count >= 2

    lines = telemetry.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["delta_k"] = 999
    lines[0] = json.dumps(tampered)
    telemetry.write_text("\n".join(lines) + "\n", encoding="utf-8")

    valid_after, _, msg_after = engine.verify_telemetry_chain(telemetry)
    assert valid_after is False
    assert "record_hash" in msg_after.lower() or "violazione" in msg_after.lower()


def test_rsi_guardrail_g6_verify_ste100_compliance(tmp_path: Path) -> None:
    """6. Verifica il controllo statico G6 per [RULE-STE100] su frasi e trattini."""
    clean_doc = (
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


def test_rsi_profile_registry_five_profiles_weights_and_fitness() -> None:
    """7. Verifica i cinque profili di RSIProfileRegistry e i pesi differenziati."""
    registry = rsi_mod.RSIProfileRegistry
    profiles = registry.list_profiles()
    expected = {
        "vibe_sprint_micro_rsi",
        "code_rsi",
        "spec_rsi",
        "ui_ux_rsi",
        "ste100_rsi",
    }
    assert expected.issubset(set(profiles))

    v_doc = RSIDefectVector(doc_drift=3, low_findings=2, tests_passed=100, tests_total=100)
    d_code = compute_delta(v_doc, profile="code_rsi")
    d_ste = compute_delta(v_doc, profile="ste100_rsi")
    assert d_ste > d_code > 0

    q_code = compute_fitness(v_doc, d_code, profile="code_rsi")
    q_ste = compute_fitness(v_doc, d_ste, profile="ste100_rsi")
    assert q_ste < q_code < 100.0


def test_rsi_strict_monotonic_hard_gate_regression() -> None:
    """8. Verifica che strict_monotonic rifiuti iterazioni con Delta_k stagnante."""
    v_prev = RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)
    v_curr = RSIDefectVector(medium_findings=2, tests_passed=100, tests_total=100)

    reg_std, _ = RSIConvergenceEngine.check_hard_gate_regression(
        v_prev,
        v_curr,
        strict_monotonic=False,
    )
    assert reg_std is False

    reg_strict, reason = RSIConvergenceEngine.check_hard_gate_regression(
        v_prev,
        v_curr,
        strict_monotonic=True,
    )
    assert reg_strict is True
    assert "strict_monotonic" in reason


def test_rsi_vibe_check_mode_c_single_pass(tmp_path: Path) -> None:
    """9. Verifica il controllo single-pass run_vibe_check su file puliti e insicuri."""
    engine = RSIConvergenceEngine(workspace_root=tmp_path)
    clean_file = tmp_path / "clean_vibe.py"
    clean_file.write_text(
        '"""Modulo sicuro per test Mode C."""\ndef add_vals(a: int, b: int) -> int:\n    return a + b\n',
        encoding="utf-8",
    )
    res_ok = engine.run_vibe_check(clean_file)
    assert res_ok["passed"] is True
    assert res_ok["delta_k"] == 0
    assert res_ok["fitness_q"] == 100.0

    bad_file = tmp_path / "unsafe_vibe.py"
    bad_file.write_text(
        'def run_unsafe(x: str):\n    return eval(x)\n',
        encoding="utf-8",
    )
    res_bad = engine.run_vibe_check(bad_file)
    assert res_bad["passed"] is False
    assert res_bad["delta_k"] > 0


def test_rsi_verify_cli_flags_cove_ast_gate(tmp_path: Path) -> None:
    """10. Verifica il CoVe CLI AST Gate tra workflow markdown e script argparse."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    wf_dir = tmp_path / ".agents" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)

    sample_script = scripts_dir / "sample_tool.py"
    sample_script.write_text(
        "import argparse\n"
        "def main():\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--valid-flag', action='store_true')\n"
        "    p.parse_args()\n",
        encoding="utf-8",
    )

    wf_file = wf_dir / "sample.md"
    wf_file.write_text(
        "Esegui `python scripts/sample_tool.py --valid-flag` per verificare.\n",
        encoding="utf-8",
    )
    engine = RSIConvergenceEngine(workspace_root=tmp_path)
    res_ok = engine.verify_cli_flags_cove(tmp_path)
    assert res_ok["passed"] is True
    assert res_ok["invalid_flags"] == []

    wf_file.write_text(
        "Esegui `python scripts/sample_tool.py --ghost-flag` per verificare.\n",
        encoding="utf-8",
    )
    res_bad = engine.verify_cli_flags_cove(tmp_path)
    assert res_bad["passed"] is False
    assert len(res_bad["invalid_flags"]) == 1
    assert "--ghost-flag" in res_bad["invalid_flags"][0]


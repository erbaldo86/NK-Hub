# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per il motore Bounded-RSI e Guardie G1..G6, GT-11 e GT-12 (v3.3.0).
Modulo: tests/test_rsi_convergence_engine.py.
Valida monotonia Delta_k/Q(S_k), RSIProfileRegistry, G1..G6, vibe-check e CoVe CLI AST Gate.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

_workspace_root = Path(__file__).resolve().parent.parent
if _workspace_root.name == ".staging":
    _workspace_root = _workspace_root.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_rsi_module():
    """Carica il modulo rsi_convergence_engine dando priorita a .staging/scripts."""
    staging_target = (
        _workspace_root / ".staging" / "scripts" / "rsi_convergence_engine.py"
    )
    prod_target = _workspace_root / "scripts" / "rsi_convergence_engine.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(
        "rsi_convergence_engine", str(target)
    )
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

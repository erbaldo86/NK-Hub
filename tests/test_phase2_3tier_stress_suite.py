# -*- coding: utf-8 -*-
"""
Suite di stress test Zero-Mock a 3 livelli per la Fase 2 di Nexus Keystone (WP11).
Modulo: .staging/tests/test_phase2_3tier_stress_suite.py.
Valida integrita strutturale L1, orchestrazione E2E L2 e resilienza avversaria L3.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any

import pytest

_THIS_FILE = Path(__file__).resolve()
_WORKSPACE_ROOT = _THIS_FILE.parent.parent
if _WORKSPACE_ROOT.name == ".staging":
    _WORKSPACE_ROOT = _WORKSPACE_ROOT.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def _load_module(module_name: str, rel_script_path: str) -> Any:
    """Carica un modulo Python dando priorita alla copia presente in staging."""
    staging_candidate = _WORKSPACE_ROOT / ".staging" / rel_script_path
    prod_candidate = _WORKSPACE_ROOT / rel_script_path
    target = staging_candidate if staging_candidate.exists() else prod_candidate
    spec = importlib.util.spec_from_file_location(module_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


indexer_mod = _load_module("nk_registry_indexer_wp11", "scripts/nk_registry_indexer.py")
router_mod = _load_module("vibe_sprint_router_wp11", "scripts/vibe_sprint_router.py")
rsi_mod = _load_module("rsi_convergence_engine_wp11", "scripts/rsi_convergence_engine.py")
ast_guard_mod = _load_module("ast_guard_validator_wp11", "scripts/ast_guard_validator.py")
sentry_mod = _load_module("nk_context_sentry_wp11", "scripts/nk_context_sentry.py")
dual_ledgers_mod = _load_module("dual_ledgers_wp11", "scripts/schemas/dual_ledgers.py")
win32_2pc_mod = _load_module("win32_2pc_engine_wp11", "scripts/win32_2pc_engine.py")


# ============================================================================
# LIVELLO 1: UNIT & STRUCTURAL INTEGRITY (4 TEST)
# ============================================================================


def test_l1_native_agents_manifest_and_gt14_auditor_invariants(tmp_path: Path) -> None:
    """1. Verifica indicizzazione dei 5 sub-agenti nativi e guardia GT-14 sugli Auditor."""
    indexer = indexer_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT)
    manifest = indexer.build_manifest()

    assert len(manifest["skills_index"]) == 16
    assert "native_agents_index" in manifest
    native_idx = manifest["native_agents_index"]
    expected_agents = {
        "NK-Specifier-Agent",
        "NK-Builder-Agent",
        "NK-Security-DAST-Auditor",
        "NK-RSI-Auditor",
        "NK-Scribe-Agent",
    }
    assert expected_agents.issubset(set(native_idx.keys()))
    assert manifest["summary"]["total_native_agents"] == len(native_idx)

    assert native_idx["NK-Security-DAST-Auditor"]["enable_write_tools"] is False
    assert native_idx["NK-RSI-Auditor"]["enable_write_tools"] is False
    assert native_idx["NK-Builder-Agent"]["enable_write_tools"] is True

    lookup_res = indexer.lookup("NK-Builder-Agent")
    assert lookup_res["found"] is True
    assert lookup_res["match_type"] == "native_agent"
    assert lookup_res["domain_id"] == "DOM-03"

    # Verifica guardie GT-14 e RULE-01 (2-Tier) in un workspace isolato
    bad_agent_dir = tmp_path / ".agents" / "agents" / "NK-RSI-Auditor"
    bad_agent_dir.mkdir(parents=True, exist_ok=True)
    bad_agent_file = bad_agent_dir / "agent.md"
    bad_agent_file.write_text(
        "---\n"
        "name: NK-RSI-Auditor\n"
        "description: Sub-Agente Auditor di test per guardie GT-14 e RULE-01.\n"
        "enable_write_tools: true\n"
        "enable_subagent_tools: true\n"
        "enable_mcp_tools: false\n"
        "---\n"
        "Corpo del sub-agente.\n",
        encoding="utf-8",
    )
    isolated_indexer = indexer_mod.NKRegistryIndexer(
        workspace_root=tmp_path,
        stage_dir=tmp_path / ".staging",
    )
    isolated_indexer.sync()
    verify_res = isolated_indexer.verify()
    assert verify_res["passed"] is False
    assert verify_res["status"] == "DRIFT_DETECTED"
    assert any("Violazione GT-14" in msg for msg in verify_res["issues"])
    assert any("Violazione RULE-01 (2-Tier)" in msg for msg in verify_res["issues"])

    # Verifica rilevamento cancellazione di tutti i file agent.md su disco
    bad_agent_file.unlink()
    verify_deleted = isolated_indexer.verify()
    assert verify_deleted["passed"] is False
    assert any("native agents disallineati" in msg for msg in verify_deleted["issues"])


def test_l1_dual_ledger_concurrent_pid_lock_and_sha256_chain(tmp_path: Path) -> None:
    """2. Verifica concorrenza multi-thread su ProgressLedger, PIDFileLock e catena SHA-256."""
    task_ledger_file = tmp_path / "task_ledger.jsonl"
    progress_ledger_file = tmp_path / "progress_ledger.jsonl"

    # Verifica rimozione automatica di un lock orfano con PID inesistente
    stale_lock_file = tmp_path / "stale_test.lock"
    stale_lock_file.write_text(
        json.dumps({"pid": 99999999, "timestamp": 100.0}),
        encoding="utf-8",
    )
    with dual_ledgers_mod.PIDFileLock(stale_lock_file, stale_timeout_sec=1.0) as plock:
        assert plock.acquired is True
    assert not stale_lock_file.exists()

    task_ledger = dual_ledgers_mod.TaskLedger(task_ledger_file)
    progress_ledger = dual_ledgers_mod.ProgressLedger(progress_ledger_file)
    thread_lock = threading.Lock()

    task_ledger.add_task(
        task_id="ROOT-0",
        action="Initialize pipeline",
        target_agent="NK-Master-Hub",
        parent_ids=[],
        payload={"step": 0},
    )

    def _worker(worker_idx: int) -> None:
        tid = f"TASK-{worker_idx}"
        with thread_lock:
            task_ledger.add_task(
                task_id=tid,
                action=f"Execute worker {worker_idx}",
                target_agent="NK-Builder-Agent",
                parent_ids=["ROOT-0"],
                payload={"worker": worker_idx},
            )
        time.sleep(0.04 * worker_idx)
        for step_i in range(4):
            progress_ledger.append_event(
                event_id=f"EV-{worker_idx}-{step_i}",
                task_id=tid,
                step_index=step_i,
                event_type="CHECKPOINT",
                details={"worker": worker_idx, "step": step_i},
            )
            time.sleep(0.005)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_worker, idx) for idx in range(1, 9)]
        for fut in futures:
            fut.result()

    reloaded = dual_ledgers_mod.TaskLedger(task_ledger_file)
    assert len(reloaded.list_tasks()) == 9
    all_events = progress_ledger.read_events()
    assert len(all_events) == 32

    # Verifica rilevamento manomissione della catena SHA-256
    lines = task_ledger_file.read_text(encoding="utf-8").splitlines()
    corrupted = json.loads(lines[-1])
    corrupted["action"] = "Tampered action"
    lines[-1] = json.dumps(corrupted)
    task_ledger_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity violation"):
        dual_ledgers_mod.TaskLedger(task_ledger_file)


def test_l1_kahn_dag_cycle_detection_and_roots_leaves(tmp_path: Path) -> None:
    """3. Verifica l'algoritmo topologico di Kahn su grafi aciclici e con cicli."""
    ledger = dual_ledgers_mod.TaskLedger(tmp_path / "dag_ledger.jsonl")
    ledger.add_task("T0", "Spec", "NK-Specifier-Agent", parent_ids=[])
    ledger.add_task("T1", "Build A", "NK-Builder-Agent", parent_ids=["T0"])
    ledger.add_task("T2", "Build B", "NK-Builder-Agent", parent_ids=["T0"])
    ledger.add_task("T3", "Audit", "NK-RSI-Auditor", parent_ids=["T1", "T2"])

    is_valid, msg = ledger.verify_dag()
    assert is_valid is True
    assert "valid" in msg.lower()
    assert [n.task_id for n in ledger.get_roots()] == ["T0"]
    assert [n.task_id for n in ledger.get_leaves()] == ["T3"]

    # Inietta una dipendenza ciclica T0 -> T3 per verificare il rilevamento di Kahn
    ledger._nodes["T0"].parent_ids.append("T3")
    is_valid_cycle, msg_cycle = ledger.verify_dag()
    assert is_valid_cycle is False
    assert "Cycle detected" in msg_cycle


def test_l1_tetralogy_4of4_alignment_and_2pc_atomic_write(tmp_path: Path) -> None:
    """4. Verifica allineamento Tetralogia 4/4, repo_map.md e scrittura Win32 2PC."""
    tetralogy_docs = (
        "concept_map.md",
        "structural_tree.md",
        "implementation_plan.md",
        "PATCH_NOTES.md",
        "repo_map.md",
    )
    for doc_name in tetralogy_docs:
        candidates = (
            _WORKSPACE_ROOT / ".staging" / "nk_genome" / doc_name,
            _WORKSPACE_ROOT / "nk_genome" / doc_name,
            _WORKSPACE_ROOT / ".staging" / doc_name,
            _WORKSPACE_ROOT / doc_name,
        )
        active_doc = next((c for c in candidates if c.exists()), None)
        assert active_doc is not None, f"Documento Tetralogia mancante: {doc_name}"
        content = active_doc.read_text(encoding="utf-8")
        assert len(content.strip()) > 100

    engine = win32_2pc_mod.TwoPhaseCommitEngine()
    target_file = tmp_path / "atomic_target.json"
    payload_str = json.dumps({"status": "COMMITTED", "version": "3.5.1"}, sort_keys=True)

    verdict = engine.atomic_write(target_file, payload_str)
    assert verdict.verdict == "COMMIT"
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == payload_str

    pointer = engine.create_ipc_pointer(
        tmp_path / "ipc_payload.json",
        payload_str,
        mime_type="application/json",
    )
    assert pointer.status == "OK"
    assert pointer.byte_size == len(payload_str.encode("utf-8"))
    assert pointer.sha256 == win32_2pc_mod.compute_sha256(payload_str)


# ============================================================================
# LIVELLO 2: END-TO-END INTEGRATION & ROUTING (4 TEST)
# ============================================================================


def test_l2_e2e_vibe_sprint_router_modes_a_b_c_d_and_native_subagents() -> None:
    """5. Verifica routing E2E Mode A/B/C/D e tutti i 5 Sub-Agenti Nativi."""
    router = router_mod.VibeSprintRouter(workspace_root=_WORKSPACE_ROOT)

    dom_02 = router.resolve_domain_from_manifest("Esegui discovery architetturale DOM-02")
    assert dom_02["domain_id"] == "DOM-02"
    assert dom_02["native_subagent"] == "NK-Specifier-Agent"

    dom_03 = router.resolve_domain_from_manifest("Implementa codice asincrono DOM-03")
    assert dom_03["domain_id"] == "DOM-03"
    assert dom_03["native_subagent"] == "NK-Builder-Agent"

    dom_04 = router.resolve_domain_from_manifest("Esegui audit sicurezza SAST DOM-04")
    assert dom_04["domain_id"] == "DOM-04"
    assert dom_04["native_subagent"] == "NK-Security-DAST-Auditor"

    dom_rsi = router.resolve_domain_from_manifest(
        "Esegui validazione oracolo e convergenza RSI con NK-Oracle-Evaluator"
    )
    assert dom_rsi["native_subagent"] == "NK-RSI-Auditor"

    dom_05 = router.resolve_domain_from_manifest("Aggiorna memoria e documentazione DOM-05")
    assert dom_05["domain_id"] == "DOM-05"
    assert dom_05["native_subagent"] == "NK-Scribe-Agent"

    intent_d = router.classify_prompt_intent(
        "Fai una ricerca e benchmark comparativo sulle architetture",
        files=None,
    )
    assert intent_d["recommended_mode"] == "mode_d"
    assert intent_d["primary_agent"] == "NK-Ideator"
    assert intent_d["native_subagent"] == "NK-Specifier-Agent"
    assert intent_d["fast_bypass_eligible"] is False

    intent_c = router.classify_prompt_intent(
        "Modifica il modulo python per gestire il timeout",
        files=["scripts/platform_runner.py"],
    )
    assert intent_c["recommended_mode"] == "mode_c"
    assert intent_c["primary_agent"] == "NK-Python-Async-Builder"
    assert intent_c["native_subagent"] in router_mod.DOMAIN_TO_NATIVE_SUBAGENT.values()
    assert intent_c["fast_bypass_eligible"] is True

    low_risk = router.compute_ast_risk_score(
        "def add_numbers(a: int, b: int) -> int:\n    return a + b\n",
        filename="small.py",
    )
    assert low_risk["recommended_mode"] == "mode_c"
    assert low_risk["mode_eligible"] is True
    assert low_risk["fast_bypass_eligible"] is True
    assert low_risk["native_subagent"] == "NK-Builder-Agent"

    high_risk = router.compute_ast_risk_score(
        "def broken_syntax(:\n    pass\n",
        filename="broken.py",
    )
    assert high_risk["recommended_mode"] == "mode_a"
    assert high_risk["mode_eligible"] is False
    assert high_risk["fast_bypass_eligible"] is False
    assert high_risk["native_subagent"] == "NK-Builder-Agent"


def test_l2_e2e_rsi_g2_hard_gate_atomic_rollback(tmp_path: Path) -> None:
    """6. Verifica rollback atomico G2 su regressione dei Gate duri durante il loop RSI."""
    target = tmp_path / "service_module.py"
    original_code = " SAFE_CONST = 42\n"
    target.write_text(original_code, encoding="utf-8")
    telemetry = tmp_path / "rsi_g2.jsonl"
    engine = rsi_mod.RSIConvergenceEngine(
        workspace_root=tmp_path,
        telemetry_path=telemetry,
    )

    def _eval_fn(iteration: int = 0) -> Any:
        if iteration == 0:
            return rsi_mod.RSIDefectVector(
                medium_findings=1,
                tests_passed=50,
                tests_total=50,
            )
        return rsi_mod.RSIDefectVector(
            sast_critical=1,
            tests_failed=2,
            tests_passed=48,
            tests_total=50,
        )

    def _refine_fn(cycle: int, defects: Any) -> bool:
        target.write_text(f"BROKEN_CONST = {cycle}\n", encoding="utf-8")
        return True

    report = engine.run_convergence_loop(
        evaluate_fn=_eval_fn,
        refine_fn=_refine_fn,
        target_files=[target],
        mode="mode_c",
        session_id="wp11_g2_test",
    )
    assert report.converged is False
    assert report.rollbacks_count >= 1
    assert report.history[-1].verdict == "ROLLED_BACK_HARD_GATE"
    assert target.read_text(encoding="utf-8") == original_code


def test_l2_e2e_rsi_g3_oscillation_cycle_breaker(tmp_path: Path) -> None:
    """7. Verifica l'interruttore anti-oscillazione G3 quando l'hash SHA-256 si ripete."""
    target = tmp_path / "oscillating_module.py"
    target.write_text("STATE = 'ALPHA'\n", encoding="utf-8")
    telemetry = tmp_path / "rsi_g3.jsonl"
    engine = rsi_mod.RSIConvergenceEngine(
        workspace_root=tmp_path,
        telemetry_path=telemetry,
    )

    states = ["STATE = 'BETA'\n", "STATE = 'ALPHA'\n"]

    def _refine_oscillate(cycle: int, defects: Any) -> bool:
        idx = (cycle - 1) % len(states)
        target.write_text(states[idx], encoding="utf-8")
        return True

    report = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: rsi_mod.RSIDefectVector(
            low_findings=2,
            tests_passed=40,
            tests_total=40,
        ),
        refine_fn=_refine_oscillate,
        target_files=[target],
        mode="mode_a",
        session_id="wp11_g3_test",
    )
    assert report.converged is False
    assert report.cycle_detected is True
    assert report.final_status == "HALTED_CYCLE_DETECTED"


def test_l2_e2e_rsi_g4_telemetry_chain_and_vibe_check(tmp_path: Path) -> None:
    """8. Verifica convergenza ottima RSI, catena telemetrica G4 e run_vibe_check."""
    target = tmp_path / "converging_module.py"
    target.write_text(
        '"""Modulo iniziale."""\ndef compute_val(x: int) -> int:\n    return x + 1\n',
        encoding="utf-8",
    )
    telemetry = tmp_path / "rsi_g4.jsonl"
    engine = rsi_mod.RSIConvergenceEngine(
        workspace_root=tmp_path,
        telemetry_path=telemetry,
    )

    report = engine.run_convergence_loop(
        evaluate_fn=lambda iteration=0: (
            rsi_mod.RSIDefectVector(medium_findings=1, tests_passed=30, tests_total=30)
            if iteration == 0
            else rsi_mod.RSIDefectVector(tests_passed=30, tests_total=30)
        ),
        refine_fn=lambda cycle, defects: bool(
            target.write_text(
                '"""Modulo convergente."""\ndef compute_val(x: int) -> int:\n    return x + 2\n',
                encoding="utf-8",
            )
        ),
        target_files=[target],
        mode="mode_b",
        session_id="wp11_g4_test",
    )
    assert report.converged is True
    assert report.final_status == "CONVERGED_OPTIMAL"
    assert report.final_fitness_q == 100.0

    valid_chain, records_count, _ = engine.verify_telemetry_chain(telemetry)
    assert valid_chain is True
    assert records_count == 2

    vibe_res = engine.run_vibe_check(target)
    assert vibe_res["passed"] is True
    assert vibe_res["delta_k"] == 0
    assert vibe_res["fitness_q"] == 100.0


# ============================================================================
# LIVELLO 3: ADVERSARIAL RED-TEAM & PERFORMANCE STRESS (4 TEST)
# ============================================================================


def test_l3_adversarial_sast_ast_guard_red_team() -> None:
    """9. Verifica rilevamento avversario SAST L1/L2/L3 e Zero-Mock in ASTGuardValidator."""
    validator = ast_guard_mod.ASTGuardValidator
    vtype_sast = ast_guard_mod.ViolationType.SAST_VIOLATION

    # Costruisce i campioni avversari dinamicamente per preservare la purezza AST del test
    sast_samples = [
        "def bad_one(x: str):\n    return " + "ev" + "al(x)\n",
        "def bad_two(x: str):\n    " + "ex" + "ec(x)\n",
        "import pickle\ndef bad_three(b: bytes):\n    return pickle." + "loads(b)\n",
        "import subprocess\ndef bad_four():\n    subprocess.run('dir', " + "shell=True)\n",
        "from unittest." + "mock import Magic" + "Mock\nm = Magic" + "Mock()\n",
        'def bad_sql(cur, uid: str):\n    cur.execute(f"SELECT * FROM users WHERE id = {uid}")\n',
    ]

    for snippet in sast_samples:
        violations = validator.check_sast_constructs(snippet)
        assert len(violations) >= 1
        assert all(v.violation_type == vtype_sast for v in violations)

    pre_clean = "def process_input(val: int) -> int:\n    return val * 2\n"
    post_mutated_sig = "def process_input(val: int, extra: int) -> int:\n    return val * extra\n"
    rep_sig = validator.validate_code_edit(pre_clean, post_mutated_sig)
    assert rep_sig.is_valid is False
    assert any(
        v.violation_type == ast_guard_mod.ViolationType.SIGNATURE_MUTATION
        for v in rep_sig.violations
    )


def test_l3_adversarial_ste100_em_dash_and_sentence_length_filter() -> None:
    """10. Verifica filtro statico [RULE-STE100] contro trattini lunghi e frasi prolisse."""
    verify_ste100 = rsi_mod.verify_ste100_compliance

    compliant_markdown = (
        "---\n"
        "description: Frontmatter YAML esentato dal conteggio parole con testo descrittivo esteso.\n"
        "---\n"
        "# Playbook Operativo\n"
        "Il sottosistema valida i contratti in tempo reale.\n"
        "Ogni operatore applica la regola con rigore deterministico.\n"
        "```python\n"
        "# Commento nel blocco codice con trattino lungo ignorato \u2014 dal filtro markdown\n"
        "x = 1\n"
        "```\n"
    )
    res_ok = verify_ste100(compliant_markdown, max_sentence_words=20)
    assert res_ok["passed"] is True
    assert res_ok["violations_count"] == 0

    adversarial_markdown = (
        "# Documento Non Conforme\n"
        "Questa frase contiene un trattino lungo proibito \u2014 nel mezzo della riga.\n"
        "Questa seconda frase contiene un trattino medio proibito \u2013 nel testo.\n"
        "Questa terza frase supera intenzionalmente il limite massimo di venti parole "
        "imposto dallo standard tecnico aerospaziale per verificare il blocco immediato "
        "del validatore linguistico.\n"
    )
    res_fail = verify_ste100(adversarial_markdown, max_sentence_words=20)
    assert res_fail["passed"] is False
    assert res_fail["violations_count"] >= 3


def test_l3_adversarial_context_sentry_mss_mtu_and_dual_profile(tmp_path: Path) -> None:
    """11. Verifica soglie MSS/MTU Swarm Hygiene e profili Standard/Argon in NKContextSentry."""
    sentry = sentry_mod.NKContextSentry(workspace_root=tmp_path, profile="standard")

    # Verifica transizioni semaforiche Standard (70/100) vs Argon (150/250)
    assert sentry.get_traffic_light_status(50, 40000, profile="standard")["status"] == "GREEN"
    assert sentry.get_traffic_light_status(80, 40000, profile="standard")["status"] == "YELLOW"
    assert sentry.get_traffic_light_status(105, 40000, profile="standard")["status"] == "RED"

    assert sentry.get_traffic_light_status(120, 150000, profile="argon")["status"] == "GREEN"
    assert sentry.get_traffic_light_status(180, 150000, profile="argon")["status"] == "YELLOW"
    assert sentry.get_traffic_light_status(260, 150000, profile="argon")["status"] == "RED"

    transcript = tmp_path / "transcript.jsonl"
    records = [
        {
            "step_index": 1,
            "source": "SYSTEM",
            "sender": "subagent-clean",
            "content": "<SYSTEM_MESSAGE>content=" + ("R" * 1200) + "</SYSTEM_MESSAGE>",
        },
        {
            "step_index": 2,
            "source": "SYSTEM",
            "sender": "subagent-mss-warn",
            "content": "<SYSTEM_MESSAGE>content=" + ("W" * 1900) + "</SYSTEM_MESSAGE>",
        },
        {
            "step_index": 3,
            "source": "SYSTEM",
            "sender": "subagent-mtu-violation",
            "content": "<SYSTEM_MESSAGE>content=" + ("V" * 2200) + "</SYSTEM_MESSAGE>",
        },
        {
            "step_index": 4,
            "source": "SYSTEM",
            "sender": "task-background-99",
            "content": "Background task finished with result: " + ("B" * 3000),
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )

    report = sentry.analyze_transcript(transcript)
    assert report["swarm_mss_warnings_count"] == 2
    assert report["swarm_hygiene_violations_count"] == 1


def test_l3_benchmark_o1_manifest_lookup_and_router_latency() -> None:
    """12. Verifica che il lookup O(1) del manifesto e il routing rispettino il budget <15ms."""
    indexer = indexer_mod.NKRegistryIndexer(workspace_root=_WORKSPACE_ROOT)
    router = router_mod.VibeSprintRouter(workspace_root=_WORKSPACE_ROOT)

    # Pre-riscalda la cache in memoria del manifesto
    indexer.load_manifest()

    queries = [
        "NK-Builder-Agent",
        "NK-Security-DAST-Auditor",
        "NK-Master-Hub",
        "vibe_sprint_router.py",
        "DOM-04",
    ]

    t0 = time.perf_counter()
    for i in range(100):
        q = queries[i % len(queries)]
        res = indexer.lookup(q)
        assert res["found"] is True
    elapsed_lookup_ms = ((time.perf_counter() - t0) * 1000.0) / 100.0
    assert elapsed_lookup_ms < 15.0

    t1 = time.perf_counter()
    for _ in range(25):
        dom = router.resolve_domain_from_manifest("Esegui audit sicurezza DOM-04")
        assert dom["native_subagent"] == "NK-Security-DAST-Auditor"
    elapsed_router_ms = ((time.perf_counter() - t1) * 1000.0) / 25.0
    assert elapsed_router_ms < 15.0

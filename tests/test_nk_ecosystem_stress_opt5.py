# -*- coding: utf-8 -*-
"""
Suite di stress e performance Zero-Mock per Nexus Keystone v3.3.0 (OPT-1..OPT-12).
Modulo: tests/test_nk_ecosystem_stress_opt5.py.
Contiene 8 test ortogonali ad alta densita su bootstrap, Tensor-RSI, router, compliance e IPC.
"""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_test_file = Path(__file__).resolve()
if _test_file.parent.name == "tests" and _test_file.parent.parent.name == ".staging":
    _workspace_root = _test_file.parent.parent.parent
else:
    _workspace_root = _test_file.parent.parent

if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))


def _load_staged_or_prod(mod_name: str, rel_subpath: str = "scripts"):
    """Carica dinamicamente il modulo dando priorita alla versione in .staging/."""
    staging_target = _workspace_root / ".staging" / rel_subpath / f"{mod_name}.py"
    prod_target = _workspace_root / rel_subpath / f"{mod_name}.py"
    target = staging_target if staging_target.exists() else prod_target
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


boot_mod = _load_staged_or_prod("nk_session_bootstrap")
rsi_mod = _load_staged_or_prod("rsi_convergence_engine")
router_mod = _load_staged_or_prod("vibe_sprint_router")
sentry_mod = _load_staged_or_prod("nk_context_sentry")
comp_mod = _load_staged_or_prod("nk_compliance_checker")
preflight_mod = _load_staged_or_prod("preflight_health_check")
snap_mod = _load_staged_or_prod("healing_snapshot_rollback")
ipc_mod = _load_staged_or_prod("nk_ipc_contracts", rel_subpath="scripts/schemas")

NKSessionBootstrap = boot_mod.NKSessionBootstrap
RSIConvergenceEngine = rsi_mod.RSIConvergenceEngine
RSIDefectVector = rsi_mod.RSIDefectVector
RSIIterationRecord = rsi_mod.RSIIterationRecord
RSIProfileRegistry = rsi_mod.RSIProfileRegistry
compute_delta = rsi_mod.compute_delta
compute_fitness = rsi_mod.compute_fitness
VibeSprintRouter = router_mod.VibeSprintRouter
classify_prompt_intent = router_mod.classify_prompt_intent
NKContextSentry = sentry_mod.NKContextSentry
NKComplianceChecker = comp_mod.NKComplianceChecker
PreflightHealthChecker = preflight_mod.PreflightHealthChecker
HealingSnapshotManager = snap_mod.HealingSnapshotManager


def _in_process_benchmark_runner(
    benchmark_suite: Path | str, root_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Esegue un modulo di test benchmark in-process per azzerare l'overhead subprocess."""
    suite_path = Path(benchmark_suite).resolve()
    if not suite_path.exists():
        return {
            "passed": False,
            "tests_failed": 1,
            "tests_passed": 0,
            "tests_total": 1,
            "suite_path": str(suite_path),
            "details": "Benchmark suite non trovata",
        }
    spec = importlib.util.spec_from_file_location(suite_path.stem, str(suite_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    t_pass = 0
    t_fail = 0
    for name in sorted(dir(mod)):
        if name.startswith("test_") and callable(getattr(mod, name)):
            try:
                getattr(mod, name)()
                t_pass += 1
            except Exception:
                t_fail += 1
    t_total = max(1, t_pass + t_fail)
    return {
        "passed": t_fail == 0,
        "tests_failed": t_fail,
        "tests_passed": t_pass,
        "tests_total": t_total,
        "suite_path": str(suite_path),
        "details": f"Benchmark in-process: {t_pass} passed, {t_fail} failed.",
    }


def test_opt1_bootstrap_warm_cache_hit_latency_under_50ms(tmp_path: Path) -> None:
    """1. Verifica cache calda < 50ms, isolamento root_mtime e salvataggio concorrente (OPT-1 + OPT-8)."""
    bootstrap = NKSessionBootstrap(workspace_root=_workspace_root)
    cold_res = bootstrap.run_bootstrap(fast_stat=False)
    assert cold_res["status"] == "PASS"
    assert bootstrap.fast_cache_file.exists()

    t0 = time.perf_counter()
    warm_res = bootstrap.run_bootstrap(fast_stat=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert warm_res["status"] == "PASS"
    assert elapsed_ms < 50.0

    tracking_dir = tmp_path / "nk_tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    (tracking_dir / "quality_baseline.json").write_text(
        json.dumps({"metrics": {"unit_tests_pass_pct": {"value": 100.0}}}),
        encoding="utf-8",
    )

    tmp_boot = NKSessionBootstrap(workspace_root=tmp_path)
    assert tmp_boot.run_bootstrap(fast_stat=False)["status"] == "PASS"

    def run_warm(_: int) -> str:
        res = tmp_boot.run_bootstrap(fast_stat=True)
        loaded = tmp_boot._load_fast_cache()
        assert loaded is not None and loaded["status"] == "PASS"
        return res["status"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(run_warm, range(12)))
    assert all(s == "PASS" for s in statuses)
    assert len(list(tmp_boot.temp_bootstrap_dir.glob("*.tmp"))) == 0

    (tmp_path / "rogue_script.py").write_text("X = 42\n", encoding="utf-8")
    res_polluted = tmp_boot.run_bootstrap(fast_stat=False)
    assert res_polluted["status"] == "FAIL"
    assert "rogue_script.py" in res_polluted["checks"]["project_isolation"]["details"]


def test_opt2_rsi_profile_propagation_in_verify_and_cli(
    tmp_path: Path, capsys: Any
) -> None:
    """2. Verifica propagazione --profile, marker NK, benchmark suite e catena concorrente (OPT-2 + OPT-9)."""
    doc_file = tmp_path / "README.md"
    doc_file.write_text(
        "# Progetto Esterno\n"
        "Questa frase contiene deliberatamente molte piu di venti parole consecutive "
        "per verificare che il motore ignori i file markdown applicativi esterni durante "
        "il profilo predefinito code_rsi ma li controlli rigorosamente in ste100_rsi.\n",
        encoding="utf-8",
    )

    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "vendor_doc.md").write_text(
        "Frase lunghissima con trattino vietato \u2014 e link rotto [broken](missing.md).\n",
        encoding="utf-8",
    )

    telemetry_file = tmp_path / "nk_tracking" / "rsi_telemetry.jsonl"
    engine = RSIConvergenceEngine(root=tmp_path, telemetry_path=telemetry_file)
    engine.run_benchmark_suite = _in_process_benchmark_runner  # type: ignore[method-assign]

    res_code = engine.verify_ecosystem(profile="code_rsi")
    assert res_code["passed"] is True and res_code["delta_k"] == 0

    res_ste = engine.verify_ecosystem(profile="ste100_rsi")
    assert res_ste["passed"] is False and res_ste["delta_k"] > 0

    rc_cli = rsi_mod.main(
        ["--verify", "--root", str(tmp_path), "--profile", "code_rsi", "--json"]
    )
    cli_payload = json.loads(capsys.readouterr().out)
    assert rc_cli == 0 and cli_payload["profile"] == "code_rsi"

    tests_dir = tmp_path / "bench_tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    pass_test = tests_dir / "test_bench_ok.py"
    pass_test.write_text("def test_ok() -> None:\n    assert 2 + 2 == 4\n", encoding="utf-8")
    fail_test = tests_dir / "test_bench_fail.py"
    fail_test.write_text("def test_fail() -> None:\n    assert 2 + 2 == 5\n", encoding="utf-8")

    assert engine.verify_ecosystem(profile="code_rsi", benchmark_suite=str(pass_test))["passed"] is True
    res_fail = engine.verify_ecosystem(profile="code_rsi", benchmark_suite=str(fail_test))
    assert res_fail["passed"] is False and res_fail["delta_k"] >= 10

    (tmp_path / "SKILL.md").write_text(
        "Questa frase usa un trattino lungo vietato \u2014 dentro un file SKILL.md.\n",
        encoding="utf-8",
    )
    assert engine.verify_ecosystem(profile="code_rsi")["passed"] is False

    def append_worker(idx: int) -> str:
        rec = RSIIterationRecord(
            session_id=f"SESS-{idx}",
            iteration=idx,
            mode="mode_c",
            defects=RSIDefectVector(),
            delta_k=0,
            fitness_q=100.0,
            state_hash=f"hash_{idx}",
            verdict="CONVERGED_OPTIMAL",
        )
        return engine.append_telemetry_record(rec).record_hash

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        hashes = list(pool.map(append_worker, range(16)))
    assert len(hashes) == 16
    chain_ok, count, _ = engine.verify_telemetry_chain(telemetry_file)
    assert chain_ok is True and count == 16


def test_opt3_vibe_sprint_router_mode_d_discovery_classification(
    tmp_path: Path, capsys: Any
) -> None:
    """3. Verifica la classificazione Mode D e la retrocompatibilita Mode A/B/C (OPT-3)."""
    router = VibeSprintRouter(workspace_root=_workspace_root)
    res = router.classify_prompt_intent(
        "Esegui un audit completo e benchmark della copertura bandi regionali"
    )
    assert res["recommended_mode"] == "mode_d"
    assert res["is_discovery"] is True
    assert res["read_only"] is True
    assert res["primary_agent"] == "NK-Ideator"
    assert "call_mcp_tool" in res["tools_allowed"]

    assert classify_prompt_intent("Analizza copertura e benchmark API")["recommended_mode"] == "mode_d"

    rc_d = router_mod.main(
        ["--prompt", "Esegui benchmark e ricerca quanti bandi", "--discovery-check", "--json"]
    )
    out_d = json.loads(capsys.readouterr().out)
    assert rc_d == 0 and out_d["recommended_mode"] == "mode_d"

    py_file = tmp_path / "small_service.py"
    py_file.write_text(
        "def compute_score(x: int) -> int:\n    return x * 2 if x > 0 else 0\n",
        encoding="utf-8",
    )
    intent_files = router.classify_prompt_intent(
        "Analizza e modifica questo modulo", files=[str(py_file)]
    )
    assert intent_files["is_discovery"] is False
    assert intent_files["recommended_mode"] != "mode_d"


def test_opt5_concurrent_stress_tensor_rsi_and_router() -> None:
    """4. Esegue lo stress test concorrente a 16 thread su Tensor-RSI, Router e regole OPT-4/5."""
    router = VibeSprintRouter(workspace_root=_workspace_root)
    profiles = RSIProfileRegistry.list_profiles()

    def worker_task(idx: int) -> Dict[str, Any]:
        prof = profiles[idx % len(profiles)]
        vec = RSIDefectVector(
            sast_critical=idx % 2,
            tests_failed=idx % 3,
            tests_passed=100 - (idx % 3),
            tests_total=100,
            contract_violations=idx % 2,
            doc_drift=idx % 4,
        )
        d_val = compute_delta(vec, profile=prof)
        q_val = compute_fitness(vec, delta_k=d_val, profile=prof)
        if idx % 2 == 0:
            mode = router.classify_prompt_intent(
                f"Task {idx}: esegui benchmark e audit copertura"
            )["recommended_mode"]
        else:
            mode = router.compute_ast_risk_score(
                f"def fn_{idx}(a: int) -> int:\n    return a + {idx}\n",
                filename=f"mod_{idx}.py",
            )["recommended_mode"]
        return {"idx": idx, "delta": d_val, "q": q_val, "mode": mode}

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results: List[Dict[str, Any]] = list(pool.map(worker_task, range(32)))

    assert len(results) == 32
    for r in results:
        assert r["delta"] >= 0 and 0.0 <= r["q"] <= 100.0
        assert r["mode"] == ("mode_d" if r["idx"] % 2 == 0 else "mode_c")


def test_opt6_compliance_checker_generic_exit_code_and_ddi_tool_streak(
    tmp_path: Path,
) -> None:
    """5. Verifica rilevamento exit code != 0 reale, streak DDI > 12 (GT-03) e default 100 (GT-10, OPT-6)."""
    checker = NKComplianceChecker(workspace_root=tmp_path)
    assert checker.DDI_DIRECT_STREAK_LIMIT == 12

    clean_tr = tmp_path / "transcript_clean_gt10.jsonl"
    clean_records = [
        {"type": "USER_INPUT", "content": "Start task"},
        {
            "type": "PLANNER_RESPONSE",
            "tool_calls": [
                {
                    "name": "run_command",
                    "args": {"CommandLine": "python scripts/nk_session_bootstrap.py"},
                }
            ],
        },
    ]
    clean_tr.write_text(
        "\n".join(json.dumps(r) for r in clean_records) + "\n", encoding="utf-8"
    )
    res_clean = checker.audit_transcript(clean_tr)
    assert res_clean["scores"]["operational_score"] == 100
    assert res_clean["scores"]["rsi_convergence_score"] == 100

    transcript_file = tmp_path / "transcript_opt6.jsonl"
    direct_calls = [{"name": "view_file", "args": {}} for _ in range(14)]
    records = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Avvia analisi"},
        {
            "step_index": 2,
            "source": "GENERIC",
            "content": "The command exited with code 1\nOutput: Error",
            "tool_calls": [],
        },
        {
            "step_index": 3,
            "source": "MODEL",
            "content": "Burst di letture dirette senza delega",
            "tool_calls": direct_calls,
        },
    ]
    transcript_file.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    res = checker.audit_transcript(transcript_file)
    assert res["metrics"]["command_error_steps"] == 1
    assert res["scores"]["operational_score"] == 90
    assert res["metrics"]["direct_tool_calls_streak"] == 14
    assert any(
        "Objective DDI violation: 14 consecutive direct tools without delegation" in p
        for p in res["penalties"]
    )


def test_opt7_context_sentry_mss_1800_and_mtu_2000_thresholds(
    tmp_path: Path,
) -> None:
    """6. Verifica il tracciamento distinto di SWARM_MSG_MSS_CAP (1800) e MTU (2000) (OPT-7, GT-04)."""
    sentry = NKContextSentry(workspace_root=tmp_path)
    assert sentry.SWARM_MSG_MSS_CAP == 1800
    assert sentry.SWARM_MSG_HARD_CAP == 2000

    transcript_file = tmp_path / "transcript_opt7.jsonl"
    records = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Start"},
        {
            "step_index": 2,
            "source": "SYSTEM",
            "content": "<SYSTEM_MESSAGE> " + ("b" * 1900) + " </SYSTEM_MESSAGE>",
        },
        {
            "step_index": 3,
            "source": "SYSTEM",
            "content": "<SYSTEM_MESSAGE> " + ("c" * 2200) + " </SYSTEM_MESSAGE>",
        },
    ]
    transcript_file.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    res = sentry.analyze_transcript(transcript_file)
    assert res["swarm_mss_cap"] == 1800
    assert res["swarm_mss_warnings_count"] == 2
    assert res["swarm_hygiene_violations_count"] == 1


def test_opt10_preflight_health_check_pruned_single_walk(tmp_path: Path) -> None:
    """7. Verifica walk potato (.venv escluso), bonifica WAL e snapshot/IPC Mode D (OPT-10 + OPT-11)."""
    for d in [".agents/skills", "nk_genome", "nk_tracking", "scripts", "tests", ".staging"]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / "nk_tracking" / "quality_baseline.json").write_text(
        json.dumps(
            {
                "_version": "3.3.0",
                "metrics": {
                    "skills_audited": 16,
                    "crv_macro_phases": 4,
                    "unit_tests_pass_pct": 100.0,
                },
            }
        ),
        encoding="utf-8",
    )

    venv_wal = tmp_path / ".venv" / "keep_me.wal"
    venv_wal.parent.mkdir(parents=True, exist_ok=True)
    venv_wal.write_text("venv data", encoding="utf-8")
    old_time = time.time() - 300.0
    os.utime(venv_wal, (old_time, old_time))

    stale_wal = tmp_path / "nk_tracking" / "orphan.wal_2pc.jsonl"
    stale_wal.write_text("{}", encoding="utf-8")
    os.utime(stale_wal, (old_time, old_time))

    checker = PreflightHealthChecker(workspace_root=tmp_path)
    report = checker.run_full_check(auto_fix=True)
    assert report["status"] == "HEALTHY_GREEN"
    assert not stale_wal.exists()
    assert venv_wal.exists()

    snap_dir = tmp_path / "snapshots"
    mgr = HealingSnapshotManager(base_temp_dir=snap_dir)
    sample_file = tmp_path / "target.py"
    sample_file.write_text("VALUE = 1\n", encoding="utf-8")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        sids = list(pool.map(lambda _: mgr.create_snapshot([sample_file]), range(8)))
    assert len(sids) == 8
    assert len(list(snap_dir.glob("*.tmp"))) == 0
    mgr.cleanup()

    intent_contract = ipc_mod.RoutingIntentContract(
        recommended_mode="mode_d",
        is_discovery=True,
        read_only=True,
        primary_agent="NK-Ideator",
    )
    assert intent_contract.recommended_mode == "mode_d"


def test_opt12_compliance_checker_2tier_ast_and_refining_exemption(
    tmp_path: Path,
) -> None:
    """8. Verifica esenzione REFINING convergente e rilevamento AST Guard 2-Tier (OPT-12)."""
    checker = NKComplianceChecker(workspace_root=tmp_path)
    transcript_file = tmp_path / "transcript_opt12.jsonl"

    records = [
        {"step_index": 1, "source": "USER_EXPLICIT", "content": "Esegui upgrade"},
        {
            "step_index": 2,
            "source": "MODEL",
            "tool_calls": [
                {
                    "name": "write_to_file",
                    "args": {
                        "TargetFile": "g:/Antigravity/nk_genome/implementation_plan.md"
                    },
                },
                {"name": "invoke_subagent", "args": {}},
            ],
        },
        {
            "step_index": 3,
            "source": "GENERIC",
            "content": (
                "The command exited with code 1\nOutput:\n"
                '{"status": "REFINING", "profile": "vibe_sprint_micro_rsi", "delta_k": 1}'
            ),
        },
        {
            "step_index": 4,
            "source": "GENERIC",
            "content": (
                "The command exited with code 1\nOutput:\n"
                '{"status": "FAIL", "scores": {"procedural_score": 80, "composite_score": 82.0}}'
            ),
        },
        {
            "step_index": 5,
            "source": "SYSTEM",
            "content": (
                "<SYSTEM_MESSAGE> sender=subagent-1 "
                "ast_guard_validator.py --stage-dir .staging: PASS | CONVERGED_OPTIMAL </SYSTEM_MESSAGE>"
            ),
        },
        {
            "step_index": 6,
            "source": "MODEL",
            "tool_calls": [
                {
                    "name": "run_command",
                    "args": {
                        "CommandLine": "python scripts/win32_2pc_engine.py --promote-staging"
                    },
                }
            ],
        },
    ]
    transcript_file.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    res = checker.audit_transcript(transcript_file)
    assert res["status"] == "PASS"
    assert res["metrics"]["ast_guard_executed"] is True
    assert res["metrics"]["command_error_steps"] == 0
    assert res["scores"]["composite_score"] == 100.0
    assert res["penalties"] == []

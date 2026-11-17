"""Sonde funzionali A/B sui dodici task core per rsi_convergence_engine."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

from _internal.rsi_convergence_engine.constants import RSIDefectVector
from _internal.rsi_convergence_engine.profiles import (
    compute_delta,
    compute_fitness,
    verify_ste100_compliance,
)


def _load_staged_or_prod_module(root: Path, mod_rel: str, cache: Dict[str, Any]) -> Any:
    """Carica un modulo privilegiando .staging/ rispetto alla produzione con cache per path."""
    cand_stg = (root / ".staging" / mod_rel).resolve()
    cand_prod = (root / mod_rel).resolve()
    cand = cand_stg if cand_stg.is_file() else cand_prod
    key = str(cand)
    if key in cache:
        return cache[key]
    scripts_dir = cand.parent
    stg_scripts = (root / ".staging" / "scripts").resolve()
    prod_scripts = (root / "scripts").resolve()
    for p in (prod_scripts, stg_scripts, scripts_dir):
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    mod_name = f"_ab_chk_{cand.stem}_{abs(hash(key)) % 100000}"
    spec = importlib.util.spec_from_file_location(mod_name, str(cand))
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossibile caricare modulo {cand}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    cache[key] = mod
    return mod


def _evaluate_ab_check(
    check_type: str,
    root: Path,
    mod_rel: str,
    expected: Any,
    mod_cache: Dict[str, Any],
) -> Tuple[bool, Any]:
    """Esegue un test funzionale reale in-process per ciascun check_type dei 12 task core."""
    if check_type == "rsi_delta_fitness":
        d_ok = compute_delta(RSIDefectVector(tests_passed=10, tests_total=10))
        q_ok = compute_fitness(RSIDefectVector(tests_passed=10, tests_total=10), delta_k=d_ok)
        q_unmeasured = compute_fitness(RSIDefectVector(tests_passed=0, tests_total=0))
        actual = q_ok
        ok = d_ok == 0 and float(actual) == float(expected) and q_unmeasured < 90.0
        return ok, actual

    if check_type == "ste100_sentence_limit":
        good_res = verify_ste100_compliance(
            "# Titolo\nQuesta frase tecnica rispetta il limite previsto.\n",
            max_sentence_words=20,
        )
        long_sentence = " ".join(["parola"] * 24) + "."
        bad_res = verify_ste100_compliance(long_sentence, max_sentence_words=20)
        actual = bool(good_res.get("passed")) and not bool(bad_res.get("passed"))
        return actual == bool(expected), actual

    mod = _load_staged_or_prod_module(root, mod_rel, mod_cache)

    if check_type == "router_classification":
        router = mod.VibeSprintRouter(workspace_root=root)
        res = router.classify_prompt_intent("correggi un typo veloce nella helper", changed_lines=3)
        actual = res.get("recommended_mode")
        return actual == expected, actual

    if check_type == "hook_write_gate":
        payload = {
            "tool_name": "write_file",
            "tool_input": {"file_path": str(root / "scripts" / "x_unstage.py")},
        }
        res = mod.evaluate_write_gate(payload, project_root=root) if hasattr(mod, "evaluate_write_gate") else mod._handle_write_gate(payload, root, False, "", "", "")
        actual = res.get("decision")
        return actual == expected, actual

    if check_type == "memory_3tier_rrf":
        ep_hit = mod.MemoryEpisode(
            episode_id="ab03_1",
            domain="01_Bug_Diagnostics",
            title="SQLite WAL lock",
            content="sql wal atomic commit recovery",
            tags=["wal", "sqlite"],
        )
        ep_miss = mod.MemoryEpisode(
            episode_id="ab03_2",
            domain="04_Prompt_Routing",
            title="CSS Grid",
            content="margin padding layout",
            tags=["css"],
        )
        hits = mod.HybridRRFSearchEngine().search(
            "sqlite wal atomic", [ep_hit, ep_miss], top_k=2
        )
        t_std = mod.Tier1CoreMemory(profile="standard")
        t_carb = mod.Tier1CoreMemory(profile="carbon")
        actual = int(t_std.token_cap)
        ok = (
            bool(hits)
            and hits[0][0].episode_id == "ab03_1"
            and hits[0][1] > 0.0
            and actual == int(expected)
            and int(t_carb.token_cap) == 1200
            and callable(getattr(mod, "sync_tier1_capsule", None))
        )
        return ok, actual

    if check_type == "ast_signature_guard":
        ok_rep = mod.ASTGuardValidator.validate_code_edit(
            "def f(x: int) -> int:\n    return x\n",
            "def f(x: int) -> int:\n    return x + 1\n",
            target_file="sample.py",
        )
        bad_rep = mod.ASTGuardValidator.validate_code_edit(
            "def f(x: int) -> int:\n    return x\n",
            "def f() -> int:\n    return 1\n",
            target_file="sample.py",
        )
        actual = bool(ok_rep.is_valid) and not bool(bad_rep.is_valid)
        return actual == bool(expected), actual

    if check_type == "registry_o1_lookup":
        idx = mod.NKRegistryIndexer(workspace_root=root)
        res = idx.lookup("DOM-01")
        actual = res.get("domain_id")
        return actual == expected, actual

    if check_type == "transcript_evidence_gate":
        rc0 = mod.extract_command_exit_code("Command exited with code 0.", "run_command")
        rc1 = mod.extract_command_exit_code("Command exited with code 1.", "run_command")
        actual = (rc0 == 0) and (rc1 == 1)
        return actual == bool(expected), actual

    if check_type == "win32_2pc_atomic":
        with tempfile.TemporaryDirectory(prefix="nk_ab_2pc_") as td:
            td_p = Path(td)
            src = td_p / "src.txt"
            dst = td_p / "dst.txt"
            src.write_text("payload_ok", encoding="utf-8")
            dst.write_text("old", encoding="utf-8")
            mod.win32_atomic_replace(src, dst)
            actual = dst.read_text(encoding="utf-8") == "payload_ok" and not src.exists()
        return actual == bool(expected), actual

    if check_type == "sqlite_wal_cache":
        with tempfile.TemporaryDirectory(prefix="nk_ab_wal_") as td:
            cache = mod.DeterministicApiCache(db_path=Path(td) / "ab_cache.db")
            try:
                healthy = bool(cache.health_check())
                actual = "wal" if healthy else "error"
            finally:
                try:
                    cache.close()
                except Exception:
                    conn = getattr(cache, "_conn", None)
                    if conn is not None:
                        conn.close()
        return actual == expected, actual

    if check_type == "sbfl_ochiai_suspiciousness":
        actual = round(float(mod.compute_ochiai(n_ef=5, n_ep=0, total_failed=5)), 4)
        zero = round(float(mod.compute_ochiai(n_ef=0, n_ep=5, total_failed=5)), 4)
        return actual == float(expected) and zero == 0.0, actual

    if check_type == "context_sentry_thresholds":
        th_data = mod.load_saturation_thresholds(workspace_root=root)
        sentry = mod.NKContextSentry(workspace_root=root, profile="standard")
        st_std_green = sentry.get_traffic_light_status(69, 100, profile="standard").get("status")
        st_std_yellow = sentry.get_traffic_light_status(70, 100, profile="standard").get("status")
        st_carb_green = sentry.get_traffic_light_status(149, 100, profile="carbon").get("status")
        std_val = int(getattr(mod, "STANDARD_GREEN_STEP_THRESHOLD", 0))
        carb_val = int(getattr(mod, "CARBON_GREEN_STEP_THRESHOLD", 0))
        prof_std = (th_data.get("profiles") or {}).get("standard") or {} if isinstance(th_data, dict) else {}
        cfg_green = (prof_std.get("context_sentry") or {}).get("green_step_threshold", std_val) if isinstance(prof_std, dict) else std_val
        actual = int(cfg_green) if isinstance(cfg_green, int) and not isinstance(cfg_green, bool) else std_val
        ok = (
            isinstance(th_data, dict)
            and actual == int(expected)
            and std_val == int(expected)
            and carb_val >= std_val
            and st_std_green == "GREEN"
            and st_std_yellow == "YELLOW"
            and st_carb_green == "GREEN"
        )
        return ok, actual

    return False, f"unknown_check_type:{check_type}"

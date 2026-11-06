# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)
> **Versione Target:** `v5.0.0-STE100-Unified` (`v4.7.0-STE100-Unified` Compatible)
> **Milestone Anchor ID:** `NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI`

## 📄 scripts/sbfl_engine.py
  class SpectrumCounts: [total_failed, total_passed, total_executed, total_tests]
  class CoverageRecord: []
  class SBFLScore: []
  class OchiaiDiagnosticPayload: [to_compact_json, estimate_token_count]
  class TriPassFilterResult: []
  class CoverageMatrix: [__init__, statements, test_ids, num_tests, num_statements, matrix, outcomes, from_records]
  class CoverageMatrix: [get_spectrum]
  class SBFLEngine: [__init__, analyze, generate_diagnostic_payload]
  functions: [calculate_ochiai, calculate_tarantula, calculate_dstar, calibrate_coincidental_correctness, tri_pass_voting_filter, main]

## 📄 scripts/win32_2pc_engine.py
  class Win32LockError: []
  class Win32LockTimeoutError: []
  class TwoPhaseCommitError: []
  class Win32NamedMutex: [__init__, __enter__, __exit__, acquire, release, _cleanup_handle]
  class WriteAheadLogManager: [__init__, _get_wal_dir, get_wal_path, write_wal, update_wal_state, purge_wal, recover]
  class TwoPhaseCommitEngine: [__init__, _backoff_sleep, prepare, commit, abort, _execute_atomic_commit, _shadow_swap_fallback, atomic_write]
  class TwoPhaseCommitEngine: [create_ipc_pointer]
  functions: [compute_sha256, compute_crc32, _win_long_path, get_mutex_name_for_path, win32_atomic_replace, validate_staging_json_files, _cleanup_promoted_staging, record_session_anchor_commit]
  functions: [_extract_dual_schema_baseline, _verify_quality_baseline_ratchet, promote_staging_to_production, _rollback_batch, main]

## 📄 scripts/nk_auto_inning.py
  def main() -> None

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/*`: rsi_convergence_engine.py, ast_repo_mapper.py, ast_guard_validator.py, oracle_evaluator_l3.py, deterministic_api_cache.py, micro_hud_renderer.py, memory_3tier_engine.py, nk_context_sentry.py
- `scripts/*`: nk_session_bootstrap.py, nk_compliance_checker.py, dast_sandbox_runner.py, vibe_sprint_router.py, invisible_healing_loop.py, nk_registry_indexer.py, healing_snapshot_rollback.py, sbfl_pytest_bridge.py
- `scripts/*`: auto_heal_pipeline.py, preflight_health_check.py, external_project_scaffolder.py, async_heartbeat_signaler.py, platform_runner.py, nk_swarm_messenger.py, env_capability_probe.py, nk_active_runtime_sentinel.py
- `scripts/*`: nk_transcript_tools.py, quality_baseline_manager.py, nk_session_handoff.py, nk_hook_gate.py, safe_cleanup_dev_servers.py
- `scripts/schemas/*`: nk_ipc_contracts.py, dual_ledgers.py, __init__.py
- `tests/stress/*`: test_real_sandbox_stress.py
- `tests/*`

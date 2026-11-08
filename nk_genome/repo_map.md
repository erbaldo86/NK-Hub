# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

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

## 📄 scripts/nk_swarm_messenger.py
  functions: [reconfigure_streams, process_payload, main]

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/schemas/*`: nk_ipc_contracts.py, dual_ledgers.py, __init__.py
- `tests/*`: test_auto_heal_pipeline.py, test_memory_3tier.py, test_win32_2pc.py, test_dast_sandbox.py, test_sbfl_engine.py, test_ast_repo_mapper.py, test_schemas_and_contracts.py, test_ast_guard_validator.py
- `tests/*`: test_vibe_sprint_router.py, test_rsi_convergence_engine.py, test_core_platform_utilities.py, test_nk_registry_indexer.py, conftest.py, test_quality_baseline_manager.py, test_active_sentinel_suite.py, __init__.py
- `tests/*`: test_context_sentry.py, test_nk_hook_and_transcript_governance.py
- `tests/stress/*`: test_real_sandbox_stress.py
- `scripts/*`

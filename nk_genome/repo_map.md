# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

## 📄 scripts/sbfl_engine.py
  class SpectrumCounts: [total_failed, total_passed, total_executed, total_tests]
  class DefUseWeight: []
  class CoverageRecord: []
  class SBFLScore: []
  class OchiaiDiagnosticPayload: [to_compact_json, estimate_token_count]
  class TriPassFilterResult: []
  class CoverageMatrix: [__init__, statements, test_ids, num_tests, num_statements, matrix, outcomes, from_records, get_spectrum]
  class SBFLEngine: [__init__, analyze, generate_diagnostic_payload]
  functions: [calculate_ochiai, calculate_tarantula, calculate_dstar, calibrate_coincidental_correctness, tri_pass_voting_filter, main]

## 📄 scripts/micro_hud_renderer.py
  class GateEntry: []
  class HUDState: []
  class MicroHUDRenderer: [__init__, set_ascii_mode, set_progress, set_gate, set_all_gates, set_mutex, set_tier1_budget, set_agent_context, set_elapsed_time, set_rsi_metrics, to_ipc_state, _build_progress_bar, _build_gates_string, _render_internal, render, render_markdown_block, render_pulse]
  functions: [reconfigure_streams, is_unicode_stream_supported, main]

## 📄 scripts/oracle_evaluator_l3.py
  class DOMNode: []
  class DOMDeltaItem: []
  class DOMEvaluationReport: []
  class _DOMBuilderParser: [__init__, handle_starttag, handle_startendtag, handle_endtag, handle_data]
  class DOMOracleEvaluator: [__init__, parse_html, count_nodes, evaluate_deltas, _compare_nodes, _node_sig]
  functions: [resolve_html_source, main]

## 📄 scripts/nk_swarm_messenger.py
  functions: [reconfigure_streams, process_payload, main]

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/*`: ast_repo_mapper.py, ast_guard_validator.py, rsi_convergence_engine.py, memory_3tier_engine.py, win32_2pc_engine.py, deterministic_api_cache.py, nk_context_sentry.py, nk_compliance_checker.py, nk_session_bootstrap.py, dast_sandbox_runner.py, invisible_healing_loop.py, healing_snapshot_rollback.py, sbfl_pytest_bridge.py, auto_heal_pipeline.py, async_heartbeat_signaler.py, external_project_scaffolder.py, vibe_sprint_router.py, preflight_health_check.py, nk_registry_indexer.py, platform_runner.py, env_capability_probe.py, nk_active_runtime_sentinel.py, quality_baseline_manager.py, safe_cleanup_dev_servers.py, nk_auto_inning.py, nk_session_handoff.py
- `scripts/schemas/*`: dual_ledgers.py, nk_ipc_contracts.py
- `tests/stress/*`: test_real_sandbox_stress.py
- `nk_tracking/cockpit/*`: nk_cockpit.html
- `tests/*`

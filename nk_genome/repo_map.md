# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

## 📄 scripts/sbfl_engine.py
  class SpectrumCounts: `[total_failed, total_passed, total_executed, total_tests]`
  class DefUseWeight: []
  class CoverageRecord: []
  class SBFLScore: []
  class OchiaiDiagnosticPayload: `[to_compact_json, estimate_token_count]`
  class TriPassFilterResult: []
  class CoverageMatrix: `[__init__, statements, test_ids, num_tests, num_statements, matrix, outcomes, from_records, get_spectrum]`
  class SBFLEngine: `[__init__, analyze, generate_diagnostic_payload]`
  functions: `[calculate_ochiai, calculate_tarantula, calculate_dstar, calibrate_coincidental_correctness, tri_pass_voting_filter, main]`

## 📄 scripts/micro_hud_renderer.py
  class GateEntry: []
  class HUDState: []
  class MicroHUDRenderer: `[__init__, set_ascii_mode, set_progress, set_gate, set_all_gates, set_mutex, set_tier1_budget, set_agent_context, set_elapsed_time, set_rsi_metrics, to_ipc_state, _build_progress_bar, _build_gates_string, _render_internal, render, render_markdown_block, render_pulse]`
  functions: `[reconfigure_streams, is_unicode_stream_supported, main]`

## 📄 scripts/ast_repo_mapper.py
  class SymbolType: `[MODULE, CLASS, METHOD, FUNCTION, ASYNC_FUNCTION, CONSTANT, IMPORT, TYPE_ALIAS, JS_COMPONENT, CSS_RULE]`
  class EdgeType: `[CALL, INHERITANCE, TYPE_REFERENCE, IMPORT_USAGE, CONTAINMENT, ATTRIBUTE_ACCESS]`
  class SymbolNode: []
  class SymbolEdge: []
  class SymbolGraph: `[add_node, add_edge, get_node]`
  class PageRankResult: []
  class SliceResult: []
  class RepoMapConfig: []
  class RepoMapResult: []
  class ResilientParser: `[parse_safe, _recover_ast_chunks, _offset_linenos, _extract_stubs_from_broken_block]`
  class SymbolExtractor: `[__init__, _register_name_mapping, _get_raw_source, _format_signature, _format_arguments, visit_Import, visit_ImportFrom, visit_Assign, visit_ClassDef, visit_FunctionDef, visit_AsyncFunctionDef, _process_function, _link_type_references, visit_Call]`
  class PolyglotExtractor: `[extract_symbols, _extract_js_ts, _extract_css, _extract_html]`
  class PersonalizedPageRank: `[compute]`
  class KarpathySurgicalSlicer: `[slice_module, _multi_focal_compress, _render_slice_nodes, _render_node_skeleton]`
  class AtomicCacheManager: `[get_default_cache_path, save_atomic, load_safe]`
  class RepoMapGenerator: `[generate, _link_cross_module_edges, _render_expanded_module, _render_inline_compact_module, _render_two_tier_map]`
  class GraduatedSkillAdapter: `[get_token_budget]`
  functions: `[estimate_tokens, export_markdown_snapshot, main]`

## 📄 scripts/ast_guard_validator.py
  class ViolationType: `[SYNTAX_ERROR, SIGNATURE_MUTATION, UNAUTHORIZED_DELETION, UNDEFINED_NAME, MALFORMED_IMPORT, TYPE_MISMATCH, SAST_VIOLATION]`
  class GuardViolation: []
  class FunctionSignatureSnapshot: []
  class ValidationReport: []
  class SignatureCollector: `[__init__, visit_ClassDef, visit_Import, visit_ImportFrom, _extract_target_names, visit_Assign, visit_AnnAssign, visit_For, visit_AsyncFor, visit_With, visit_AsyncWith, visit_ExceptHandler, visit_TypeAlias, visit_FunctionDef, visit_AsyncFunctionDef, _record_function]`
  class ScopeIntegrityChecker: `[__init__, _current_visible_names, visit_Lambda, visit_ClassDef, visit_FunctionDef, visit_AsyncFunctionDef, _process_func, _extract_target_names, visit_Match, _extract_pattern_bindings, visit_TypeAlias, _visit_comprehension_common, visit_ListComp, visit_SetComp, visit_GeneratorExp, visit_DictComp, visit_kv, visit_NamedExpr, visit_Name]`
  class SASTConstructChecker: `[__init__, _emit_gaming_violation, visit_Constant, visit_Subscript, visit_Attribute, visit_FunctionDef, visit_AsyncFunctionDef, visit_Compare, visit_Import, visit_ImportFrom, visit_Call]`
  class ASTGuardValidator: `[__init__, validate_pydantic_catalog_records, check_sast_constructs, validate_code_edit, _parse_or_report, _verify_signatures]`
  functions: `[validate_pydantic_catalog_records, _resolve_production_counterpart, main]`

## 📄 scripts/rsi_convergence_engine.py
  class RSIDefectVector: `[effective_totals]`
  class RSIIterationRecord: []
  class RSISessionReport: []
  class RSIProfileConfig: []
  class RSIProfileRegistry: `[get, list_profiles]`
  class RSIConvergenceEngine: `[__init__, get_max_iterations, compute_delta, compute_fitness, is_converged, check_hard_gate_regression, compute_files_state_hash, _compute_record_hash, _get_last_telemetry_hash, append_telemetry_record, verify_telemetry_chain, run_convergence_loop, _resolve_candidate, _extract_script_supported_flags, verify_cli_flags_cove, evaluate_stage_directory, run_vibe_check, run_benchmark_suite, _scan_sast_and_mojibake, verify_ecosystem]`
  functions: `[reconfigure_streams, compute_delta, compute_fitness, verify_ste100_compliance, _is_excluded_rel_path, _extract_sast_report_count, main]`

## 📄 scripts/memory_3tier_engine.py
  class MemoryEpisode: `[_validate_and_normalize_domain]`
  class Tier1Item: []
  class Tier1DomainState: []
  class PureBM25: `[__init__, _tokenize, score]`
  class DenseEmbedder: `[vector_from_text, cosine_similarity]`
  class HybridRRFSearchEngine: `[__init__, search]`
  class Tier1CoreMemory: `[__init__, set_item, get_item, get_token_usage, get_context_string, _enforce_budget]`
  class ThreeTierMemoryEngine: `[__init__, _init_storage, append_episode, get_tier2_episodes, get_tier3_episodes, recall_hybrid, sync_tier1_capsule, _archive_to_tier3, _load_tier2_raw, _read_shadow_cache, _update_shadow_cache]`
  functions: `[resolve_domain, win32_atomic_replace, rotate_circular_backups, estimate_tokens, sync_tier1_capsule, main]`

## 📄 scripts/oracle_evaluator_l3.py
  class DOMNode: []
  class DOMDeltaItem: []
  class DOMEvaluationReport: []
  class _DOMBuilderParser: `[__init__, handle_starttag, handle_startendtag, handle_endtag, handle_data]`
  class DOMOracleEvaluator: `[__init__, parse_html, count_nodes, evaluate_deltas, _compare_nodes, _node_sig]`
  functions: `[resolve_html_source, main]`

## 📄 scripts/deterministic_api_cache.py
  class DeterministicApiCache: `[__init__, _get_connection, _open_persistent_connection, _connection, close, __enter__, __exit__, _init_db, compute_hash, get, set, health_check, clear, get_stats]`
  functions: `[main]`

## 📄 scripts/platform_runner.py
  functions: `[reconfigure_streams, _normalize_python_command, _kill_process_tree_sync, safe_subprocess_run, main]`

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/win32_2pc_engine.py`: `[Win32LockError, Win32LockTimeoutError, TwoPhaseCommitError, Win32NamedMutex, WriteAheadLogManager, TwoPhaseCommitEngine]`
- `scripts/schemas/nk_ipc_contracts.py`: `[MetaPromptGateContract, IPCPointerReturn, OchiaiDiagnosticPayload, TwoPhaseCommitPrepare, TwoPhaseCommitVerdict, GateEvaluationResult, DASTSandboxReport, RRFSearchQuery, MicroUIHUDState, RootCauseAnalysis, StagingSnapshot, GoalFailureManifest, RoutingIntentContract, RSIDefectVector, RSIIterationRecord, RSISessionReport]`
- `scripts/nk_context_sentry.py`: `[NKContextSentry, reconfigure_streams, main]`
- `scripts/nk_compliance_checker.py`: `[NKComplianceChecker, reconfigure_streams, _is_subagent_transcript]`
- `scripts/nk_session_bootstrap.py`: `[NKSessionBootstrap, reconfigure_streams, main]`
- `scripts/dast_sandbox_runner.py`: `[IO_COUNTERS, JOBOBJECT_BASIC_LIMIT_INFORMATION, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PROCESSENTRY32, PROCESS_MEMORY_COUNTERS, SandboxConfig, CoverageTraceItem, SandboxTelemetryReport, ShadowSandbox, DASTSandboxRunner]`
- `scripts/schemas/dual_ledgers.py`: `[TaskDAGNode, ProgressEvent, PIDFileLock, TaskLedger, ProgressLedger]`
- `tests/test_auto_heal_pipeline.py`: `[_InProcessPytestBridge, _import_module, test_sbfl_pytest_bridge_parsing_and_ochiai]`
- `scripts/invisible_healing_loop.py`: `[SBFLLocation, CodeSlice, HealingCycleLog, HealingResult, DSPyTelemetryRecord, KarpathySlicer, SBFLEngine, DSPyTelemetryHook, InvisibleHealingLoop]`
- `scripts/vibe_sprint_router.py`: `[_ASTDepthVisitor, VibeSprintRouter, _sanitize_tetralogia_filenames]`
- `scripts/healing_snapshot_rollback.py`: `[FitnessVerdict, FitnessReport, FileSnapshot, SnapshotBundle, HealingSnapshotManager]`
- `tests/test_memory_3tier.py`: `[TestMemory3TierEngine, _load_staging_memory_module]`
- `scripts/sbfl_pytest_bridge.py`: `[PytestRunSummary, OchiaiBridgeLocation, SBFLPytestBridge]`
- `scripts/auto_heal_pipeline.py`: `[AutoHealSessionReport, AutoHealPipeline, normalize_test_command]`
- `scripts/external_project_scaffolder.py`: `[ExternalProjectScaffolder, main]`
- `scripts/async_heartbeat_signaler.py`: `[AsyncHeartbeatSignaler, run_standalone_test, main]`
- `scripts/preflight_health_check.py`: `[PreflightHealthChecker, safe_remove_dir, on_error]`
- `scripts/nk_registry_indexer.py`: `[NKRegistryIndexer, main]`
- `tests/test_dast_sandbox.py`: `[TestDASTSandbox]`
- `tests/test_sbfl_engine.py`: `[TestSBFLEngine]`
- `tests/test_ast_guard_validator.py`: `[TestASTGuardValidator]`
- `tests/test_ast_repo_mapper.py`: `[TestASTRepoMapper]`
- `tests/test_schemas_and_contracts.py`: `[TestSchemasAndContracts]`
- `tests/test_win32_2pc.py`: `[TestWin322PCEngine]`
- `tests/test_super_plan_v6_triad.py`: `[_SampleGrantModel, _load_staged_or_prod, test_sp_ws1_hooks_json_dual_schema_and_probe_cwd_agents]`
- `tests/test_holistic_environment_integrity.py`: `[_resolve_staged_or_prod_path, _load_staged_or_prod_mod, test_01_all_34_indexed_scripts_belong_to_domain_taxonomy]`
- `scripts/nk_swarm_messenger.py`: `[reconfigure_streams, process_payload, main]`
- `tests/test_platform_runner.py`: `[_load_runner_module, test_platform_runner_string_command_unbuffered_injection, test_platform_runner_tree_kill_on_timeout_and_utf8]`
- `tests/test_vibe_sprint_router.py`: `[_load_router_module, test_vibe_sprint_router_real_ast_max_depth_and_routing, test_vibe_sprint_router_load_prewarmed_capsule_and_cli]`
- `scripts/env_capability_probe.py`: `[reconfigure_streams, check_module_availability, probe_environment]`
- `tests/test_rsi_convergence_engine.py`: `[_load_rsi_module, test_rsi_delta_and_fitness_monotonicity, test_rsi_guardrail_g1_early_stop_zero_defects]`
- `tests/test_nk_ecosystem_stress_opt5.py`: `[_load_staged_or_prod, _in_process_benchmark_runner, test_opt1_bootstrap_warm_cache_hit_latency_under_50ms]`
- `tests/test_nk_registry_indexer.py`: `[_load_staging_or_prod_module, test_nk_registry_indexer_sync_generates_manifest_and_skill_index, test_nk_registry_indexer_verify_detects_clean_and_drift]`
- `scripts/nk_active_runtime_sentinel.py`: `[calculate_state, _is_subagent_transcript, _discover_active_transcript]`
- `scripts/quality_baseline_manager.py`: `[load_baseline, create_default_baseline, _is_valid_gt68_recalibration]`
- `tests/test_external_scaffolder.py`: `[_load_scaffolder_module, test_external_scaffolder_rejects_hub_internal_path, test_external_scaffolder_generates_full_ddd_and_tetralogy]`
- `tests/*`: `test_quality_baseline_manager.py, test_unified_onboarding_mandate.py, test_safe_cleanup_dev_servers.py, test_deterministic_api_cache.py, test_env_capability_probe.py, test_preflight_health_check.py, conftest.py, test_platform_upgrades.py, test_super_brief_upgrades.py, test_context_sentry.py, test_active_sentinel_suite.py, test_oracle_l3_and_hud.py, test_phase2_3tier_stress_suite.py, test_triad_epistemic_governance_v44.py`
- `scripts/*`: `safe_cleanup_dev_servers.py, nk_auto_inning.py, nk_transcript_tools.py, nk_hook_gate.py, nk_session_handoff.py`
- `tests/stress/*`: `test_real_sandbox_stress.py`
- `scripts/schemas/*`: `__init__.py`
- `nk_tracking/cockpit/*`: `nk_cockpit.html`

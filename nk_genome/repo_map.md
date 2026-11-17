# REPO-MAP (AST Snapshot)

## 📄 `scripts/rsi_convergence_engine.py`
  `class RSIConvergenceEngine`: `compute_delta, verify_cli_flags_cove, run_benchmark_suite, get_max_iterations, __init__, evaluate_canary_holdout, verify_telemetry_chain, run_convergence_loop`
  `class RSIConvergenceEngine cont`: `compute_fitness, verify_ecosystem, emit_gt14_bundle, run_vibe_check, run_ab_benchmark, is_converged, check_hard_gate_regression, verify_convergence`
  `class RSIConvergenceEngine cont`: `compute_files_state_hash, append_telemetry_record, snapshot_mgr`
  `class RSIProfileRegistry`: `list_profiles, get`
  `class RSIProfileConfig`: `empty`
  `functions`: `reconfigure_streams, main, init_nk_facade, resolve_workspace_root, run_ab_benchmark, ensure_canary_holdout_file, evaluate_canary_holdout, emit_gt14_bundle`
  `functions cont`: `register_lazy_hooks, verify_ste100_compliance, compute_delta, compute_fitness`

## 📄 `scripts/deterministic_api_cache.py`
  `class DeterministicApiCache`: `__init__, close, compute_hash, get, set, health_check, clear, get_stats`
  `functions`: `main`

## 📄 `scripts/memory_3tier_engine.py`
  `class Tier1DomainState`: `empty`
  `class MemoryEpisode`: `empty`
  `class Tier1Item`: `empty`
  `class PureBM25`: `_tokenize, __init__, score`
  `class HybridRRFSearchEngine`: `__init__, search`
  `class DenseEmbedder`: `cosine_similarity, vector_from_text`
  `class Tier1CoreMemory`: `_enforce_budget, set_item, get_token_usage, get_context_string, __init__`
  `class ThreeTierMemoryEngine`: `consolidate_similar_episodes, get_tier2_episodes, sync_tier1_capsule, get_tier3_episodes, recall_hybrid, __init__, append_episode`
  `functions`: `main, init_nk_facade, resolve_domain, rotate_circular_backups, win32_atomic_replace, estimate_tokens, sync_tier1_capsule, consolidate_similar_episodes`

## 📄 `scripts/vibe_sprint_router.py`
  `class _ASTDepthVisitor`: `generic_visit, __init__`
  `class VibeSprintRouter`: `__init__, validate_generated_prompt, build_meta_prompt_envelope, generate_inline_micro_spec, format_compact_env_capsule, evaluate_meta_prompt_gate, normalize_voice_stt_input, generate_env_capsule`
  `class VibeSprintRouter cont`: `load_prewarmed_capsule, compute_ast_risk_score, is_gate_exempt, resolve_intrinsic_vibe_protocols, classify_prompt_intent, is_passive_state_handoff, resolve_domain_from_manifest, format_meta_prompt_markdown`
  `functions`: `main, init_nk_facade, reconfigure_streams, lint_nk_prompt, is_passive_state_handoff, resolve_domain_from_manifest, build_meta_prompt_envelope, resolve_intrinsic_vibe_protocols`
  `functions cont`: `format_compact_env_capsule, evaluate_meta_prompt_gate, classify_prompt_intent, is_gate_exempt, generate_env_capsule, load_prewarmed_capsule, normalize_voice_stt_input, validate_generated_prompt`
  `functions cont`: `format_meta_prompt_markdown, run_test, dispatch_router_cli`

## 📄 `scripts/win32_2pc_engine.py`
  `class Win32LockTimeoutError`: `empty`
  `class TwoPhaseCommitError`: `empty`
  `class Win32LockError`: `empty`
  `class TwoPhaseCommitEngine`: `prepare, abort, commit, atomic_write, create_ipc_pointer, __init__`
  `class BatchJournalV2`: `recover_crashed_batches, cleanup_journal, get_journal_root, begin_batch, rollback_from_manifest, _write_json_fsync`
  `class Win32NamedMutex`: `release, acquire, _cleanup_handle, __enter__, __exit__, __init__, _get_posix_held_map`
  `class WriteAheadLogManager`: `update_wal_state, _quarantine_corrupt_wal, recover, __init__, purge_wal, get_wal_path, _get_wal_dir, write_wal`
  `functions`: `main, init_nk_facade, compute_sha256, compute_crc32, win32_atomic_replace, get_repo_batch_mutex_name, get_mutex_name_for_path, promote_staging_to_production`
  `functions cont`: `quarantine_staging, record_session_anchor_commit, validate_staging_json_files`

## 📄 `scripts/healing_snapshot_rollback.py`
  `class FileSnapshot`: `empty`
  `class FitnessVerdict`: `PASSED, IMPROVED, REGRESSION, NEUTRAL`
  `class FitnessReport`: `empty`
  `class SnapshotBundle`: `empty`
  `class HealingSnapshotManager`: `_save_manifest, evaluate_fitness, create_snapshot, rollback, cleanup, __init__, _load_manifest`
  `functions`: `main, init_nk_facade, atomic_write_text, atomic_write_bytes, reconfigure_streams`

## 📄 `scripts/schemas/nk_ipc_contracts.py`
  `class MetaPromptGateContract`: `empty`
  `class IPCPointerReturn`: `empty`
  `class OchiaiDiagnosticPayload`: `_coerce_spectrum_tuple, _coerce_top_candidates, to_compact_json, estimate_token_count`
  `class TwoPhaseCommitPrepare`: `empty`
  `class TwoPhaseCommitVerdict`: `empty`
  `class MicroUIHUDState`: `empty`
  `class RootCauseAnalysis`: `empty`
  `class StagingSnapshot`: `empty`
  `class GoalFailureManifest`: `empty`
  `class RoutingIntentContract`: `empty`
  `class RSIDefectVector`: `effective_totals`
  `class RSIIterationRecord`: `_validate_defects`
  `class RSISessionReport`: `_validate_history`

## 📄 `scripts/sbfl_engine.py`
  `class SBFLScore`: `empty`
  `class CoverageRecord`: `empty`
  `class SpectrumCounts`: `total_executed, total_failed, total_passed, total_tests`
  `class SBFLLocation`: `to_compact_payload, render_payload_json`
  `class TriPassFilterResult`: `empty`
  `class SBFLEngine`: `generate_diagnostic_payload, __init__, extract_from_exception, analyze`
  `class CoverageMatrix`: `num_statements, get_spectrum, outcomes, num_tests, test_ids, matrix, statements, __init__`
  `class CoverageMatrix cont`: `from_records`
  `functions`: `main, init_nk_facade, estimate_token_count, tri_pass_voting_filter, is_monitoring_conflict_active, calculate_ochiai, calculate_tarantula, calibrate_coincidental_correctness`
  `functions cont`: `calculate_dstar, collect_statements_with_monitoring`

## 📄 `scripts/async_heartbeat_signaler.py`
  `class AsyncHeartbeatSignaler`: `__init__, reset_step, start, stop, emit_pulse, dump_diagnostics, _run_loop`
  `functions`: `run_standalone_test, main, reconfigure_streams`

### Moduli Secondari
- `scripts/nk_compliance_checker.py`: `NKComplianceChecker, main`
- `scripts/nk_active_runtime_sentinel.py`: `_SentinelNamedMutex, calculate_state`
- `scripts/schemas/dual_ledgers_models.py`: `TaskDAGNode, ProgressEvent`
- `scripts/micro_hud_renderer.py`: `GateEntry, HUDState`
- `scripts/nk_registry_indexer.py`: `NKRegistryIndexer, main`
- `scripts/dast_sandbox_runner.py`: `JOBOBJECT_EXTENDED_LIMIT_INFORMATION, CoverageTraceItem`
- `scripts/oracle_evaluator_l3.py`: `DOMNode, DOMEvaluationReport`
- `scripts/preflight_health_check.py`: `PreflightHealthChecker, main`
- `scripts/invisible_healing_loop.py`: `InvisibleHealingLoop, main`
- `scripts/schemas/dual_ledgers.py`: `TaskLedger, ProgressLedger`
- `scripts/nk_session_bootstrap.py`: `NKSessionBootstrap, main`
- `scripts/sbfl_pytest_bridge.py`: `PytestRunSummary, OchiaiBridgeLocation`
- `scripts/nk_context_sentry.py`: `NKContextSentry, main`
- `scripts/external_project_scaffolder.py`: `ExternalProjectScaffolder, main`
- `scripts/auto_heal_pipeline.py`: `KarpathySlicer, HealingCycleLog`
- `scripts/schemas/nk_catalog_contracts.py`: `SkillFrontmatterContract, AgentFrontmatterContract`
- `scripts/nk_hook_gate.py`: `main, init_nk_facade`
- `scripts/nk_swarm_messenger.py`: `process_payload, main`
- `scripts/nk_auto_inning.py`: `main, atomic_write_text`
- `scripts/platform_runner.py`: `reconfigure_streams, safe_subprocess_run`
- `scripts/nk_transcript_tools.py`: `main, init_nk_facade`
- `scripts/*`: `safe_cleanup_dev_servers.py, quality_baseline_manager.py, ast_repo_mapper.py, env_capability_probe.py, nk_session_handoff.py, nk_acs_fastguard.py, ast_guard_validator.py, __init__.py`
- `scripts/schemas/*`: `__init__.py`
- `scripts/_internal/rsi_convergence_engine/*`: `profiles.py, ecosystem_verify.py, benchmark_and_vibe.py, engine.py, lazy_bridge.py, gt14_bundle.py, constants.py, ab_checks.py`
- `scripts/_internal/rsi_convergence_engine/*`: `canary_holdout.py, loop_and_cove.py, cove_and_telemetry.py, pytest_benchmark_runner.py, sast_scanner.py, eco_audits.py, gt14_probes.py, ab_benchmark.py`
- `scripts/_internal/rsi_convergence_engine/*`: `cli.py, __init__.py`
- `scripts/_internal/memory_3tier_engine/*`: `search_bm25_dense.py, engine_core.py, models.py, sqlite_store.py, tier1_capsule.py, cli.py, __init__.py`
- `scripts/_internal/vibe_sprint_router/*`: `ast_risk_and_capsule.py, transcript_and_cli.py, router_core.py, cli_handlers.py, write_intent.py, intent_classifier.py, routing_helpers.py, stt_normalize.py`
- `scripts/_internal/vibe_sprint_router/*`: `prompt_linter.py, envelope_builder.py, domain_matcher.py, constants_core.py, constants_stt.py, write_intent_rules.py, keywords_core.py, __init__.py`
- `scripts/_internal/win32_2pc_engine/*`: `constants.py, mutex.py, engine.py, journal.py, wal.py, io_and_paths.py, staging_guards.py, guards_ratchet.py`
- `scripts/_internal/win32_2pc_engine/*`: `promoter.py, promoter_helpers.py, __init__.py`
- `scripts/_internal/oracle_evaluator_l3/*`: `models_and_dom.py, gate_validators.py, evaluator_core.py, cli.py, __init__.py`
- `scripts/_internal/healing_snapshot_rollback/*`: `models_and_io.py, manager_and_cli.py, __init__.py`
- `scripts/_internal/auto_heal_pipeline/*`: `models_and_slice.py, runner.py, cli.py, __init__.py`
- `scripts/_internal/ast_guard_validator/*`: `sast_checker.py, validator.py, scope_checker.py, models.py, validator_helpers.py, signature_collector.py, reexports.py, sast_eval.py`
- `scripts/_internal/ast_guard_validator/*`: `scope_bindings.py, sast_call_helpers.py, sast_node_checks.py, sast_call_checks.py, sast_constants.py, __init__.py`
- `scripts/_internal/external_project_scaffolder/*`: `scaffolder_cli.py, templates.py, __init__.py`
- `scripts/_internal/sbfl_engine/*`: `models_and_metrics.py, localizer.py, cli.py, __init__.py`
- `scripts/_internal/ast_repo_mapper/*`: `models.py, symbol_extractor.py, subgraph_query.py, polyglot_and_cache.py, generator.py, map_rendering.py, ranking_and_slicing.py, facade_resolver.py`
- `scripts/_internal/ast_repo_mapper/*`: `parser_resilient.py, __init__.py`
- `scripts/_internal/nk_registry_indexer/*`: `indexer.py, hygiene_paths.py, manifest_sync.py, cache_and_skills.py, skills_scan.py, taxonomy.py, scripts_and_agents.py, shards_rehydrate.py`
- `scripts/_internal/nk_registry_indexer/*`: `matrix_and_release.py, governance_and_verify.py, hygiene_filter.py, manifest_builder.py, metadata_extract.py, lookup.py, governance_gt14.py, shards.py`
- `scripts/_internal/nk_registry_indexer/*`: `__init__.py`
- `scripts/_internal/nk_context_sentry/*`: `cli.py, estimator.py, transcript_tail.py, thresholds_proxy.py, __init__.py`
- `scripts/_internal/nk_session_bootstrap/*`: `bootstrap.py, compaction_and_head.py, transcript_prompt.py, resilience_tail.py, wal_hygiene.py, root_hygiene.py, constants.py, bootstrap_checks.py`
- `scripts/_internal/nk_session_bootstrap/*`: `fast_cache.py, context_sentry_bridge.py, __init__.py`
- `scripts/_internal/dast_sandbox_runner/*`: `sandbox_fs.py, constants.py, fuzzer.py, __init__.py, process_runner.py, cli.py, e2e_and_audit.py, win32_job.py`
- `scripts/_internal/dast_sandbox_runner/*`: `staging_overlay.py`
- `scripts/_internal/preflight_health_check/*`: `checker.py, cli.py, ssot_governance.py, cleanup_and_wal.py, __init__.py`
- `scripts/_internal/nk_common/*`: `ledger_lock_io.py, ledger_runtime.py, io.py, facade_boot.py, catalog_loader.py, thresholds.py, prompt_linter_core.py, catalog_routing.py`
- `scripts/_internal/nk_common/*`: `win32_mutex.py, transcript_guards.py, ast_exports.py, oracle_lock.py, paths.py, transcript_io.py, isolated_test_runner.py, catalog.py`
- `scripts/_internal/nk_common/*`: `prompt_linter_rules.py, __init__.py`
- `scripts/_internal/sbfl_pytest_bridge/*`: `bridge_core.py, models.py, runner_and_cli.py, __init__.py`
- `scripts/_internal/nk_compliance_checker/*`: `cli.py, transcript_scan.py, rules_evaluator.py, __init__.py`
- `scripts/_internal/nk_hook_gate/*`: `json_io.py, stop_evidence_cli.py, write_gate.py, cli_dispatch.py, path_safety.py, mcp_classifier.py, shell_write_detector.py, target_classifier.py`
- `scripts/_internal/nk_hook_gate/*`: `ast_inline_guard.py, classifier_redirections.py, shell_ast_paths.py, constants.py, shell_parser.py, shell_tokenize.py, integrity_and_fasttrack.py, stop_evidence.py`
- `scripts/_internal/nk_hook_gate/*`: `shell_search_mask.py, shell_redaction.py, core_env.py, constants_patterns.py, __init__.py`
- `scripts/_internal/nk_session_handoff/*`: `templates_compiler.py, cli.py, session_state.py, constants.py, transcript_cursor.py, context_view.py, handoff_engine.py, __init__.py`
- `scripts/_internal/nk_acs_fastguard/*`: `constants.py, evaluator.py, z2_and_l0.py, state_rmw.py, compaction.py, __init__.py`
- `scripts/_internal/quality_baseline_manager/*`: `constants.py, benchmark_runner.py, cli.py, ratchet_core.py, __init__.py`
- `scripts/_internal/safe_cleanup_dev_servers/*`: `win32_proc.py, cleanup_cli.py, __init__.py`
- `scripts/_internal/nk_transcript_tools/*`: `prompt_and_ste100.py, constants.py, locate_helper.py, cli.py, oracle_and_grounding.py, locate_and_compliance.py, evidence_and_ears.py, __init__.py`
- `scripts/_internal/*`: `__init__.py`

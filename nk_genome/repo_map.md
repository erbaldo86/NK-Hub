# REPO-MAP (AST Snapshot)

## 📄 `scripts/rsi_convergence_engine.py`
  `class RSIConvergenceEngine`: `is_converged, get_max_iterations, run_ab_benchmark, check_hard_gate_regression, append_telemetry_record, run_convergence_loop, compute_fitness_v2, compute_fitness`
  `class RSIConvergenceEngine cont`: `run_benchmark_suite, verify_convergence, emit_gt14_bundle, verify_telemetry_chain, run_vibe_check, __init__, evaluate_canary_holdout, snapshot_mgr`
  `class RSIConvergenceEngine cont`: `verify_cli_flags_cove, compute_files_state_hash, verify_ecosystem, compute_delta`
  `class RSIProfileRegistry`: `get, list_profiles, get_strict, is_legacy_alias`
  `class RSIProfileConfig`: `empty`
  `functions`: `reconfigure_streams, main, init_nk_facade, resolve_workspace_root, run_ab_benchmark, run_rsi_cli, emit_gt14_bundle, ensure_canary_holdout_file`
  `functions cont`: `evaluate_canary_holdout, register_lazy_hooks, compute_fitness, compute_delta, compute_candidate_sort_key, verify_ste100_compliance, compute_fitness_v2, audit_coverage_report_payload`
  `functions cont`: `audit_sast_report_payload`

## 📄 `scripts/deterministic_api_cache.py`
  `class DeterministicApiCache`: `__init__, close, compute_hash, get, set, health_check, clear, get_stats`
  `functions`: `main`

## 📄 `scripts/memory_3tier_engine.py`
  `class Tier1Item`: `empty`
  `class Tier1DomainState`: `empty`
  `class MemoryEpisode`: `empty`
  `class DenseEmbedder`: `vector_from_text, cosine_similarity`
  `class HybridRRFSearchEngine`: `__init__, search`
  `class PureBM25`: `_tokenize, score, __init__`
  `class Tier1CoreMemory`: `_enforce_budget, get_context_string, set_item, __init__, get_token_usage`
  `class ThreeTierMemoryEngine`: `append_episode, sync_tier1_capsule, get_tier3_episodes, get_tier2_episodes, consolidate_similar_episodes, recall_hybrid, __init__`
  `functions`: `main, init_nk_facade, rotate_circular_backups, win32_atomic_replace, estimate_tokens, resolve_domain, sync_tier1_capsule, consolidate_similar_episodes`

## 📄 `scripts/vibe_sprint_router.py`
  `class _ASTDepthVisitor`: `__init__, generic_visit`
  `class VibeSprintRouter`: `format_meta_prompt_markdown, normalize_voice_stt_input, generate_inline_micro_spec, build_meta_prompt_envelope, resolve_domain_from_manifest, evaluate_meta_prompt_gate, is_gate_exempt, __init__`
  `class VibeSprintRouter cont`: `resolve_intrinsic_vibe_protocols, validate_generated_prompt, classify_prompt_intent, compute_ast_risk_score, load_prewarmed_capsule, format_compact_env_capsule, is_passive_state_handoff, generate_env_capsule`
  `functions`: `detect_outbound_handoff_intent, detect_active_continuation_handoff, main, init_nk_facade, reconfigure_streams, lint_nk_prompt, is_passive_state_handoff, format_compact_env_capsule`
  `functions cont`: `classify_prompt_intent, normalize_voice_stt_input, validate_generated_prompt, load_prewarmed_capsule, generate_env_capsule, evaluate_meta_prompt_gate, resolve_domain_from_manifest, format_meta_prompt_markdown`
  `functions cont`: `is_gate_exempt, resolve_intrinsic_vibe_protocols, build_meta_prompt_envelope, detect_active_continuation_handoff_impl, detect_outbound_handoff_intent_impl, dispatch_router_cli, run_test`

## 📄 `scripts/nk_compliance_checker.py`
  `class NKComplianceChecker`: `audit_transcript, _lookup_rsi_telemetry_score, __init__`
  `functions`: `main, init_nk_facade, find_active_transcript, reconfigure_streams`

## 📄 `scripts/platform_runner.py`
  `functions`: `reconfigure_streams, safe_subprocess_run, main`

## 📄 `scripts/__init__.py`
  `init`

### Moduli Secondari
- `scripts/*`: `win32_2pc_engine.py, builder_mutation_gate.py, healing_snapshot_rollback.py, sbfl_pytest_bridge.py, nk_context_sentry.py, async_heartbeat_signaler.py, dast_sandbox_runner.py, auto_heal_pipeline.py`
- `scripts/*`: `preflight_health_check.py, nk_registry_indexer.py, oracle_evaluator_l3.py, external_project_scaffolder.py, nk_session_bootstrap.py, tensor_rsi.py, nk_hook_gate.py, nk_transcript_tools.py`
- `scripts/*`: `quality_baseline_manager.py, safe_cleanup_dev_servers.py, ast_repo_mapper.py, env_capability_probe.py, nk_session_handoff.py, nk_acs_fastguard.py, ast_guard_validator.py`
- `scripts/schemas/*`: `nk_ipc_contracts.py, dual_ledgers_models.py, handoff_contracts.py, dual_ledgers.py, nk_catalog_contracts.py, __init__.py`
- `scripts/_internal/rsi_convergence_engine/*`: `profiles.py, ecosystem_verify.py, benchmark_and_vibe.py, engine.py, report_sanitizers.py, vibe_report_helpers.py, constants.py, gt14_probes.py`
- `scripts/_internal/rsi_convergence_engine/*`: `loop_and_cove.py, sast_scanner.py, eco_audits.py, canary_holdout.py, ecosystem_gates_ext.py, __init__.py`
- `scripts/_internal/memory_3tier_engine/*`: `search_bm25_dense.py, engine_core.py, sqlite_store.py, models.py, tier1_capsule.py, cli.py, __init__.py`
- `scripts/_internal/vibe_sprint_router/*`: `ast_risk_and_capsule.py, transcript_and_cli.py, router_core.py, cli_handlers.py, write_intent.py, intent_classifier.py, intent_track_classifier.py, prompt_linter.py`
- `scripts/_internal/vibe_sprint_router/*`: `envelope_builder.py, stt_normalize.py, routing_helpers.py, constants_core.py, stt_helpers.py, domain_matcher.py, intent_builders.py, envelope_renderers.py`
- `scripts/_internal/vibe_sprint_router/*`: `constants_stt.py, write_intent_rules.py, keywords_core.py, __init__.py`
- `scripts/_internal/tensor_rsi/*`: `schemas.py, ticket_auth.py, gate_mapper.py, oracle_bridge.py, policy_tensor.py, co_executor.py, step_handlers.py, cold_warm_bandit.py`
- `scripts/_internal/tensor_rsi/*`: `pareto_gate.py, materializer.py, config_loader.py, helper_ops.py, __init__.py`
- `scripts/_internal/builder_mutation_gate/*`: `audit_mode.py, __init__.py, mutant_gen.py, report_builders.py, runner.py, target_prep.py, hotspot_audit.py, operators.py`
- `scripts/_internal/sbfl_pytest_bridge/*`: `models.py, scoring_helpers.py, bridge_core.py, matrix_engine.py, pass_tracer.py, runner_and_cli.py, frame_extractor.py, plugin_template.py`
- `scripts/_internal/sbfl_pytest_bridge/*`: `__init__.py`
- `scripts/_internal/win32_2pc_engine/*`: `constants.py, nonce_store.py, mutex.py, engine.py, wal.py, journal.py, io_and_paths.py, tensor_session_guard.py`
- `scripts/_internal/win32_2pc_engine/*`: `governance_auth.py, promoter_helpers.py, promoter.py, guards_sandbox.py, staging_guards.py, guards_ratchet.py, __init__.py`
- `scripts/_internal/healing_snapshot_rollback/*`: `models_and_io.py, manager_and_cli.py, __init__.py`
- `scripts/_internal/oracle_evaluator_l3/*`: `models_and_dom.py, gate_validators.py, expectations.py, evaluator_core.py, cli.py, __init__.py`
- `scripts/_internal/auto_heal_pipeline/*`: `models_and_slice.py, runner.py, schemas.py, diagnose_helper.py, rsi_bridge_helpers.py, cli.py, __init__.py`
- `scripts/_internal/ast_guard_validator/*`: `sast_checker.py, validator.py, models.py, scope_checker.py, validator_helpers.py, quality_diff_rules.py, frontend_static_checker.py, quality_diff_checker.py`
- `scripts/_internal/ast_guard_validator/*`: `signature_collector.py, reexports.py, sast_eval.py, sast_taint_helpers.py, scope_branch_helpers.py, scope_bindings.py, sast_expr_eval.py, sast_call_helpers.py`
- `scripts/_internal/ast_guard_validator/*`: `overlay_helpers.py, sast_node_checks.py, sast_call_checks.py, cli_helpers.py, sast_constants.py, frontend_static_rules.py, __init__.py`
- `scripts/_internal/dast_sandbox_runner/*`: `sandbox_fs.py, constants.py, fuzzer.py, __init__.py, holdout_verify.py, holdout_assets_helpers.py, staging_overlay.py, cli.py`
- `scripts/_internal/dast_sandbox_runner/*`: `process_runner.py, win32_job.py, e2e_and_audit.py`
- `scripts/_internal/external_project_scaffolder/*`: `scaffolder_cli.py, templates.py, __init__.py`
- `scripts/_internal/nk_context_sentry/*`: `cli.py, transcript_tail.py, thresholds_proxy.py, estimator.py, __init__.py`
- `scripts/_internal/*`: `__init__.py`

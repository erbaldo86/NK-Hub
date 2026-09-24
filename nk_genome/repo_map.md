# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

## 📄 scripts/micro_hud_renderer.py
  class GateEntry: []
  class HUDState: []
  class MicroHUDRenderer: [__init__, set_ascii_mode, set_progress, set_gate, set_all_gates, set_mutex, set_tier1_budget, set_agent_context, set_elapsed_time, _build_progress_bar, _build_gates_string, _render_internal, render, render_markdown_block, render_pulse]
  functions: [reconfigure_streams, is_unicode_stream_supported, main]

## 📄 scripts/ast_guard_validator.py
  class ViolationType: [SYNTAX_ERROR, SIGNATURE_MUTATION, UNAUTHORIZED_DELETION, UNDEFINED_NAME, MALFORMED_IMPORT, TYPE_MISMATCH]
  class GuardViolation: []
  class FunctionSignatureSnapshot: []
  class ValidationReport: []
  class SignatureCollector: [__init__, visit_ClassDef, visit_Import, visit_ImportFrom, _extract_target_names, visit_Assign, visit_AnnAssign, visit_For, visit_AsyncFor, visit_With, visit_AsyncWith, visit_ExceptHandler, visit_TypeAlias, visit_FunctionDef, visit_AsyncFunctionDef, _record_function]
  class ScopeIntegrityChecker: [__init__, _current_visible_names, visit_Lambda, visit_ClassDef, visit_FunctionDef, visit_AsyncFunctionDef, _process_func, _extract_target_names, visit_Match, _extract_pattern_bindings, visit_TypeAlias, _visit_comprehension_common, visit_ListComp, visit_SetComp, visit_GeneratorExp, visit_DictComp, visit_kv, visit_NamedExpr, visit_Name]
  class ASTGuardValidator: [validate_code_edit, _parse_or_report, _verify_signatures]
  functions: [main]

## 📄 scripts/nk_active_runtime_sentinel.py
  functions: [calculate_state, run_sentinel, main]

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/*`: ast_repo_mapper.py, sbfl_engine.py, deterministic_api_cache.py, oracle_evaluator_l3.py, memory_3tier_engine.py, dast_sandbox_runner.py, invisible_healing_loop.py, win32_2pc_engine.py, sbfl_pytest_bridge.py, healing_snapshot_rollback.py, preflight_health_check.py, external_project_scaffolder.py, vibe_sprint_router.py, async_heartbeat_signaler.py, nk_compliance_checker.py, auto_heal_pipeline.py, nk_context_sentry.py, nk_session_bootstrap.py, quality_baseline_manager.py, nk_swarm_messenger.py, env_capability_probe.py, platform_runner.py, safe_cleanup_dev_servers.py, nk_auto_inning.py, nk_session_handoff.py
- `scripts/schemas/*`: dual_ledgers.py, nk_ipc_contracts.py
- `.agents/skills/NK-Master-Hub/scripts/*`: run_hub.py, change_router.py, ipc_engine.py, safe_parser.py, test_hub.py
- `google-docs-mcp/*`: server.py, auth.py, cli.py
- `.agents/skills/NK-Oracle-Evaluator/resources/*`: dual_state_visual_comparator.py, runtime_trace_inspector.py
- `.agents/skills/NK-Dynamic-Sandbox-StressTester/resources/*`: phase2_chaos_swarm_runner.py, dynamic_pool_dispatcher.py, phase1_surgical_runner.py
- `.agents/skills/NK-Security-Auditor/resources/l1/*`: peer_review_validator.py, token_weighted_allocator.py, swarm_aggregator.py
- `tests/stress/*`: test_real_sandbox_stress.py
- `tests/*`, `.agents/skills/NK-Oracle-Evaluator/scripts/*`, `nk_tracking/cockpit/*`, `.agents/skills/NK-Bug-Diagnostic-Engine/resources/*`

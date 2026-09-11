# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

## 📄 scripts/ast_repo_mapper.py
  class SymbolType: [MODULE, CLASS, METHOD, FUNCTION, ASYNC_FUNCTION, CONSTANT, IMPORT, TYPE_ALIAS, JS_COMPONENT, CSS_RULE]
  class EdgeType: [CALL, INHERITANCE, TYPE_REFERENCE, IMPORT_USAGE, CONTAINMENT, ATTRIBUTE_ACCESS]
  class SymbolNode: []
  class SymbolEdge: []
  class SymbolGraph: [add_node, add_edge, get_node]
  class PageRankResult: []
  class SliceResult: []
  class RepoMapConfig: []
  class RepoMapResult: []
  class ResilientParser: [parse_safe, _recover_ast_chunks, _offset_linenos, _extract_stubs_from_broken_block]
  class SymbolExtractor: [__init__, _register_name_mapping, _get_raw_source, _format_signature, _format_arguments, visit_Import, visit_ImportFrom, visit_Assign, visit_ClassDef, visit_FunctionDef, visit_AsyncFunctionDef, _process_function, _link_type_references, visit_Call]
  class PolyglotExtractor: [extract_symbols, _extract_js_ts, _extract_css, _extract_html]
  class PersonalizedPageRank: [compute]
  class KarpathySurgicalSlicer: [slice_module, _multi_focal_compress, _render_slice_nodes, _render_node_skeleton]
  class AtomicCacheManager: [get_default_cache_path, save_atomic, load_safe]
  class RepoMapGenerator: [generate, _render_expanded_module, _render_inline_compact_module, _render_two_tier_map]
  class GraduatedSkillAdapter: [get_token_budget]
  functions: [estimate_tokens, export_markdown_snapshot, main]

## 📄 google-docs-mcp/server.py
  class IgnoreValidationErrors: [filter]
  functions: [get_docs_service, read_google_doc, append_to_google_doc]

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/*`: ast_guard_validator.py, micro_hud_renderer.py, sbfl_engine.py, memory_3tier_engine.py, dast_sandbox_runner.py, invisible_healing_loop.py, win32_2pc_engine.py, preflight_health_check.py, vibe_sprint_router.py, async_heartbeat_signaler.py, quality_baseline_manager.py, env_capability_probe.py, platform_runner.py, safe_cleanup_dev_servers.py
- `scripts/schemas/*`: dual_ledgers.py, nk_ipc_contracts.py
- `.agents/skills/NK-Master-Hub/scripts/*`: run_hub.py, change_router.py, ipc_engine.py, safe_parser.py, test_hub.py
- `.agents/skills/NK-Oracle-Evaluator/resources/*`: dual_state_visual_comparator.py, runtime_trace_inspector.py
- `.agents/skills/NK-Dynamic-Sandbox-StressTester/resources/*`: phase2_chaos_swarm_runner.py, dynamic_pool_dispatcher.py, phase1_surgical_runner.py
- `.agents/skills/NK-Security-Auditor/resources/l1/*`: peer_review_validator.py, token_weighted_allocator.py, swarm_aggregator.py
- `tests/*`: test_invisible_healing_loop.py, test_dast_sandbox.py, test_schemas_and_contracts.py, test_sbfl_engine.py, test_ast_guard_validator.py, test_memory_3tier.py, test_win32_2pc.py, test_ast_repo_mapper.py, conftest.py, test_platform_upgrades.py
- `google-docs-mcp/*`: auth.py, cli.py
- `nk_tracking/cockpit/*`: nk_cockpit.html
- `.agents/skills/NK-Oracle-Evaluator/scripts/*`, `.agents/skills/NK-Bug-Diagnostic-Engine/resources/*`

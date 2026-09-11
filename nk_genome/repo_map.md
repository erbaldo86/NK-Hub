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

## 📄 src_app/ui/dashboard.py
  class DashboardRenderer: [_load_asset, get_css, get_js, render_html]

## 📄 google-docs-mcp/auth.py
  functions: [authenticate]

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/*`: ast_guard_validator.py, micro_hud_renderer.py, sbfl_engine.py, memory_3tier_engine.py, dast_sandbox_runner.py, invisible_healing_loop.py, win32_2pc_engine.py, preflight_health_check.py, vibe_sprint_router.py, async_heartbeat_signaler.py, quality_baseline_manager.py, run_concurrency_crosscheck.py, env_capability_probe.py, platform_runner.py, safe_cleanup_dev_servers.py, run_stress_test_80.py, oracle_evaluator_l3.py, run_stress_test_30_dual.py, run_stress_test_40_dual.py
- `src_app/catalog/*`: repository.py, __init__.py
- `scripts/schemas/*`: dual_ledgers.py, nk_ipc_contracts.py
- `.agents/skills/NK-Master-Hub/scripts/*`: run_hub.py, change_router.py, ipc_engine.py, safe_parser.py, test_hub.py
- `src_app/search/*`: parametric_filter.py, ateco_tree.py, nlp_intent_extractor.py, linguistics.py, __init__.py
- `google-docs-mcp/*`: server.py, cli.py
- `src_app/connectors/*`: base.py, p7m_unpacker.py, rest_api.py, html_scraper.py, incentivi_gov.py, unioncamere_federator.py, rss_feed.py, __init__.py
- `src_app/ingestion/*`: throttling.py, base.py, watchdog.py, nightly_scheduler.py, orchestrator.py, p7m_unpacker.py, __init__.py
- `.agents/skills/NK-Oracle-Evaluator/resources/*`: dual_state_visual_comparator.py, runtime_trace_inspector.py
- `src_app/document_processing/*`, `.agents/skills/NK-Dynamic-Sandbox-StressTester/resources/*`, `src_app/ingestion/drivers/*`, `src_app/matching/*`, `.agents/skills/NK-Security-Auditor/resources/l1/*`, `src_app/ingestion/normalizers/*`, `src_app/service/*`, `src_app/models/*`, `tests/*`, `.agents/skills/NK-Oracle-Evaluator/scripts/*`, `src_app/api/*`, `root/*`, `src_app/*`, `src_app/ui/*`, `src_app/core/*`, `src_app/api/routers/*`, `src_app/ui/assets/*`, `src_app/ui/components/*`, `nk_tracking/cockpit/*`, `.agents/skills/NK-Bug-Diagnostic-Engine/resources/*`

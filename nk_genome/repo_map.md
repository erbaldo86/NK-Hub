# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

## 📄 google-docs-mcp/server.py
  class IgnoreValidationErrors(logging.Filter):
    def filter(self, record)
  def get_docs_service()
  def read_google_doc(document_id: str) -> str
  def append_to_google_doc(document_id: str, text_to_append: str) -> str

## 📄 scripts/preflight_health_check.py
  class PreflightHealthChecker: [__init__, run_full_check, _check_ssot_anchor, _check_staging_and_temp, _check_and_purge_caches, _check_and_purge_stale_wals, _enforce_report_retention, _check_baseline_alignment]
  functions: [safe_remove_dir, on_error, safe_remove_file]

## 📄 scripts/win32_2pc_engine.py
  class Win32LockError: []
  class Win32LockTimeoutError: []
  class TwoPhaseCommitError: []
  class Win32NamedMutex: [__init__, __enter__, __exit__, acquire, release, _cleanup_handle]
  class WriteAheadLogManager: [__init__, _get_wal_dir, get_wal_path, write_wal, update_wal_state, purge_wal, recover]
  class TwoPhaseCommitEngine: [__init__, _backoff_sleep, prepare, commit, abort, _execute_atomic_commit, _shadow_swap_fallback, atomic_write, atomic_write_async, create_ipc_pointer]
  functions: [compute_sha256, compute_crc32, get_mutex_name_for_path, record_session_anchor_commit, promote_staging_to_production, main]

## 📄 scripts/micro_hud_renderer.py
  class GateEntry: []
  class HUDState: []
  class MicroHUDRenderer: [__init__, set_progress, set_gate, set_all_gates, set_mutex, set_tier1_budget, set_agent_context, set_elapsed_time, _build_progress_bar, _build_gates_string, render, render_markdown_block, render_pulse]

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/*`: sbfl_engine.py, dast_sandbox_runner.py, ast_repo_mapper.py, ast_guard_validator.py, memory_3tier_engine.py, invisible_healing_loop.py, async_heartbeat_signaler.py, vibe_sprint_router.py, quality_baseline_manager.py, safe_cleanup_dev_servers.py, oracle_evaluator_l3.py, run_stress_test_80.py, run_concurrency_crosscheck.py, run_stress_test_30_dual.py, run_stress_test_40_dual.py, env_capability_probe.py, platform_runner.py
- `tests/*`: test_win32_2pc.py, test_dast_sandbox.py, test_sbfl_engine.py, test_ast_repo_mapper.py, test_ast_guard_validator.py, test_memory_3tier.py, test_invisible_healing_loop.py, test_schemas_and_contracts.py, test_oracle_ground_truth_l3.py, conftest.py, test_bando_connectors.py, test_document_processing_step3.py, test_search_and_matching_step4.py, test_labnk_service_step5.py, test_server_api.py, test_eu_integration.py, test_b2b_excellence_macro1.py, test_platform_upgrades.py
- `src_app/models/*`: cgm.py, __init__.py
- `src_app/connectors/*`: base.py, rest_api.py, rss_feed.py, html_scraper.py, p7m_unpacker.py, incentivi_gov.py, unioncamere_federator.py, __init__.py
- `src_app/document_processing/*`: models.py, pdf_extractor.py, zip_unpacker.py, section_segmenter.py, document_pipeline.py, __init__.py
- `src_app/ui/*`: dashboard.py, __init__.py

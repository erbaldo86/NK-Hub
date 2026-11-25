# Protocolli 2-Tier, CLI e Commit 2PC (`v1.0.0-Generation`)
## 1. Routing 2-Tier, 6 Sub-Agenti e `DOM-01`
|Dominio|Agente|Strumenti|Skill|
|-|-|-|-|
|DOM-01|browser, research, image-generator|Built-in DOM-01|NK-Orchestrator|
|DOM-02|NK-Arch-Specifier|read_file, send_message (no write/mcp)|[0] NK-Ideator|
|DOM-02|NK-Specifier-Agent|read_file, write_file, edit_file, send_message|[1] NK-System-Architect|
|DOM-03|NK-Builder-Agent|read_file, write_file, edit_file, run_command, manage_task, send_message|[2], [3], [4]|
|DOM-04|NK-Security-DAST-Auditor|read_file, send_message (no write/mcp)|[5], [7], [8]|
|DOM-04|NK-RSI-Auditor|read_file, send_message (no write/mcp)|[6] NK-Oracle-Evaluator|
|DOM-05|NK-Scribe-Agent|read_file, write_file, edit_file, run_command, manage_task, send_message|[9] NK-Scribe-Memory|
## 2. Protocollo CLI
1. Bootstrap/L0: `nk_session_bootstrap.py` (`generation`/`carbon`, `hooks.json`), `vibe_sprint_router.py --meta-prompt-gate --prompt "<t>"`.
2. Lookup/Swarm: `nk_registry_indexer.py --lookup "<q>"`, `send_message` (`< 1.800` char).
3. Fast-Bypass: `Mode D` read-only. `Mode C` (`<= 150` LOC): `rsi_convergence_engine.py --vibe-check .staging --profile code_rsi`.
4. Triplo Lock: `nk_transcript_tools.py oracle-lock freeze`; triplo lock `SHA-256`, `HMAC` (`oracle_lock.json`).
5. Dual-Execution (`GT-14`): Auditor (`EnableWriteTools=False`) no `run_command`; sonde `nk_diagnostics/` via `read_file`.
6. Capsule NVMe: `python -B -u scripts/platform_runner.py --pytest-isolated` (`--overlay-staging`); no `read_file` ciechi, batch `<= 3`.
7. Watchdog/Handoff: `150/250` step (`CHECKPOINT`/`<CONTEXT_SUMMARY>`), `nk_session_handoff.py --compile-handoff-prompt` / `--compile-template-11`.
8. Commit 2PC: stop demoni, `win32_2pc_engine.py --promote-staging --repo-root "<r>" --milestone "<id>"`. Verifica `quality_baseline_manager.py --check-only --live --with-coverage` (`Q_v2(S_k)`), `NK-Scribe-Agent`.
9. `/compact`: UI host; `NK_RepoBatchLock`; `nk_tracking/active_context.md` post `CHECKPOINT`.

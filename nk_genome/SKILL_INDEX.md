---
title: "NK Genome: Skill & Script Modular O(1) Index"
version: "4.7.0-STE100-Unified"
release_version: "5.0.0-STE100-Unified"
milestone_anchor_id: "NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI"
rsi_profile: "ste100_rsi"
---

# Indice Tassonomico Modulare O(1) (`SKILL_INDEX.md`)

> **Versione Schema Manifest:** `4.7.0-STE100-Unified` | **Release:** `5.0.0-STE100-Unified`

Questo indice mappa i cinque domini funzionali di Nexus Keystone.
Il registro consente la risoluzione O(1) di skill, script e flag CLI.
Il manifesto traccia `16` skill canoniche e `34` moduli Python.

## 1. Mappa dei 5 Domini Funzionali (`DOM-01..DOM-05`)

| ID Dominio | Nome Dominio | Skill Primaria | Conteggio Skill | Conteggio Script |
| :--- | :--- | :--- | :---: | :---: |
| `DOM-01` | `GOV_AND_ROUTING` | `NK-Master-Hub` | `4` | `9` |
| `DOM-02` | `IDEATION_AND_ARCH` | `NK-Ideator` | `4` | `3` |
| `DOM-03` | `BUILD_AND_HEAL` | `NK-Python-Async-Builder` | `2` | `7` |
| `DOM-04` | `AUDIT_DAST_AND_RCA` | `NK-Security-Auditor` | `4` | `7` |
| `DOM-05` | `MEMORY_TELEMETRY_AND_DOCS` | `NK-Scribe` | `2` | `8` |

## 2. Registro delle Skill Vocazionali

La tabella seguente elenca ogni skill con il relativo dominio e hash SHA-256.

| Skill | Dominio | Sub-Agente Nativo | Livello Thinking | File Ausiliari | LOC | SHA-256 (12 char) |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `NK-Agent-Instruction-Forge` | `DOM-02` | `NK-Builder-Agent` | `HIGH` | `0` | `56` | `55ae7710869b` |
| `NK-App-UX-Architect` | `DOM-02` | `NK-Specifier-Agent` | `HIGH` | `0` | `70` | `2a8e2c7c05d2` |
| `NK-Backend-Architect` | `DOM-02` | `NK-Specifier-Agent` | `HIGH` | `0` | `65` | `05432a9071f8` |
| `NK-Bug-Diagnostic-Engine` | `DOM-04` | `NK-Security-DAST-Auditor` | `HIGH` | `2` | `52` | `390f74e81595` |
| `NK-Delta-Architect` | `DOM-03` | `NK-Builder-Agent` | `HIGH` | `1` | `83` | `1ccfbc165a66` |
| `NK-Dynamic-Sandbox-StressTester` | `DOM-04` | `NK-Security-DAST-Auditor` | `HIGH` | `0` | `67` | `e4663a90eebb` |
| `NK-Episodic-Memory-Engine` | `DOM-05` | `NK-Scribe-Agent` | `HIGH` | `0` | `62` | `8bff6446aa75` |
| `NK-Ideator` | `DOM-02` | `NK-Specifier-Agent` | `HIGH` | `1` | `62` | `97921fc9e758` |
| `NK-Master-Hub` | `DOM-01` | `NK-Specifier-Agent` | `HIGH` | `0` | `185` | `4573bf557987` |
| `NK-Oracle-Evaluator` | `DOM-04` | `NK-RSI-Auditor` | `HIGH` | `2` | `62` | `5077694ef390` |
| `NK-Plan-Aligner` | `DOM-01` | `NK-RSI-Auditor` | `HIGH` | `0` | `59` | `7b94b8377de9` |
| `NK-Python-Async-Builder` | `DOM-03` | `NK-Builder-Agent` | `HIGH` | `0` | `61` | `222f2aec36bb` |
| `NK-Scribe` | `DOM-05` | `NK-Scribe-Agent` | `HIGH` | `2` | `70` | `5cf84bfbf4a3` |
| `NK-Security-Auditor` | `DOM-04` | `NK-Security-DAST-Auditor` | `HIGH` | `4` | `71` | `8229ce9e18de` |
| `NK-Session-Controller` | `DOM-01` | `NK-Specifier-Agent` | `HIGH` | `4` | `103` | `301bf21ac8a7` |
| `NK-State-Router` | `DOM-01` | `NK-RSI-Auditor` | `HIGH` | `0` | `58` | `75d87a18d5c5` |

## 3. Registro degli Script Core, Schemi e Flag CLI

La tabella seguente mappa ogni modulo Python ai flag CLI verificati via AST.

| Script (`scripts/`) | Dominio | Flag CLI Supportati | LOC | SHA-256 (12 char) |
| :--- | :---: | :--- | :---: | :--- |
| `ast_guard_validator.py` | `DOM-04` | `--allowed-mutations`, `--json`, `--output-json`, `--stage-dir`, `--target` | `1759` | `58d372e4a4c0` |
| `ast_repo_mapper.py` | `DOM-02` | `--export`, `--focus-files`, `--json`, `--max-tokens`, `--mode`, `--repo-map`, `--root`, `--snapshot-out`, `--symbol` | `1913` | `b7b7b166c1e1` |
| `async_heartbeat_signaler.py` | `DOM-03` | `--interval`, `--json`, `--max-beats`, `--once`, `--step-name`, `--task-id`, `--test` | `244` | `eb12de020c2f` |
| `auto_heal_pipeline.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `516` | `eed5057f8ff4` |
| `dast_sandbox_runner.py` | `DOM-04` | `--json`, `--overlay-staging`, `--profile`, `--script`, `--staging-dir`, `--timeout` | `1269` | `95218fe5bded` |
| `deterministic_api_cache.py` | `DOM-03` | `--clear`, `--force-refresh`, `--health`, `--stats` | `299` | `bad049f01f82` |
| `env_capability_probe.py` | `DOM-02` | `--check-module`, `--export`, `--json` | `333` | `cee0957e4c68` |
| `external_project_scaffolder.py` | `DOM-02` | `--dry-run`, `--force`, `--json`, `--name`, `--retrofit`, `--target` | `330` | `787e7a9c567e` |
| `healing_snapshot_rollback.py` | `DOM-03` | `--cleanup`, `--create`, `--rollback` | `382` | `61d5efcb7818` |
| `invisible_healing_loop.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `347` | `9ce22fa90ee7` |
| `memory_3tier_engine.py` | `DOM-05` | `--append`, `--base-dir`, `--consolidate`, `--content`, `--domain`, `--json`, `--output`, `--profile`, `--query`, `--recall`, `--tags`, `--threshold`, `--tier1-sync`, `--title` | `1289` | `b0d163d38f58` |
| `micro_hud_renderer.py` | `DOM-05` | `--agent`, `--ascii`, `--domain`, `--json`, `--mutex`, `--percent` | `302` | `a0f671e5099a` |
| `nk_active_runtime_sentinel.py` | `DOM-05` | `--check`, `--json`, `--profile`, `--transcript` | `141` | `a32eb2abef76` |
| `nk_auto_inning.py` | `DOM-05` | `--audit`, `--close-inning`, `--json`, `--transcript`, `--tuning-file` | `107` | `904422703c62` |
| `nk_compliance_checker.py` | `DOM-05` | `--json`, `--min-score`, `--transcript` | `632` | `521750fa9d31` |
| `nk_context_sentry.py` | `DOM-05` | `--actual-context-tokens`, `--json`, `--profile`, `--transcript`, `--verbose` | `457` | `de4f555392ef` |
| `nk_hook_gate.py` | `DOM-01` | `--check`, `--command`, `--content`, `--conversation-id`, `--enforce-stop`, `--event`, `--init`, `--native-contract`, `--project-root`, `--shadow`, `--strict-external`, `--target` | `1025` | `89dde9b04aaf` |
| `nk_registry_indexer.py` | `DOM-01` | `--apply-global-filter`, `--generate-tas-matrix`, `--json`, `--lookup`, `--root`, `--stage-dir`, `--sync`, `--sync-staging`, `--verify` | `2356` | `cca603a53db8` |
| `nk_session_bootstrap.py` | `DOM-01` | `--conversation-id`, `--force-full`, `--hook`, `--json`, `--project-root`, `--transcript` | `1089` | `f3b92c59e661` |
| `nk_session_handoff.py` | `DOM-01` | `--checkpoint-turn`, `--compile-handoff-prompt`, `--compile-state-handoff`, `--compile-task-prompt`, `--compile-template-11`, `--gate-status`, `--generate-active-context`, `--generate-prompt`, `--milestone-id`, `--output-dir`, `--persist-brief-id`, `--profile`, `--project-root`, `--prompt-text`, `--resume-from-anchor`, `--root`, `--transcript` | `893` | `bdafe7e0b14b` |
| `nk_swarm_messenger.py` | `DOM-01` | `--payload`, `--payload-file`, `--recipient`, `--sender` | `97` | `02ad6336c1d5` |
| `nk_transcript_tools.py` | `DOM-04` | `--brain-dir`, `--conversation-id`, `--file`, `--json`, `--lock-file`, `--manifest`, `--message`, `--mode`, `--output`, `--reason`, `--report`, `--root`, `--target`, `--test-a`, `--test-b`, `--text`, `--transcript` | `860` | `2180be471012` |
| `oracle_evaluator_l3.py` | `DOM-04` | `--actual`, `--expected`, `--json` | `404` | `2481dc94adc2` |
| `platform_runner.py` | `DOM-03` | `--cmd`, `--cwd`, `--no-capture`, `--timeout` | `231` | `80313464c8a0` |
| `preflight_health_check.py` | `DOM-05` | `--check-only`, `--json`, `--root` | `593` | `e474fbe2da80` |
| `quality_baseline_manager.py` | `DOM-05` | `--check`, `--check-only`, `--file`, `--json`, `--metrics`, `--recalibrate`, `--update` | `438` | `7e9abc674284` |
| `rsi_convergence_engine.py` | `DOM-04` | `--ab-benchmark`, `--benchmark-suite`, `--json`, `--persist-telemetry`, `--profile`, `--root`, `--sast-report`, `--strict-verify`, `--verify`, `--verify-canary`, `--vibe-check` | `2125` | `e0c0beb4422b` |
| `safe_cleanup_dev_servers.py` | `DOM-03` | `--dry-run`, `--json`, `--ports`, `--workspace-root` | `334` | `b37cc2dc0f98` |
| `sbfl_engine.py` | `DOM-04` | `--json`, `--records-file` | `534` | `4a1dbe5a6574` |
| `sbfl_pytest_bridge.py` | `DOM-04` | `--cwd`, `--json`, `--target-file`, `--test-cmd` | `373` | `64e8531d9d12` |
| `schemas/dual_ledgers.py` | `DOM-01` | `nessuno` | `436` | `e645a07f078f` |
| `schemas/nk_ipc_contracts.py` | `DOM-01` | `nessuno` | `304` | `3b6bb7133b27` |
| `vibe_sprint_router.py` | `DOM-01` | `--auto-bypass-readonly`, `--capsule`, `--changed-lines`, `--classify-prompt`, `--compact`, `--discovery-check`, `--files`, `--json`, `--lint-prompt`, `--meta-prompt-gate`, `--mode`, `--no-gate`, `--prompt`, `--task`, `--test`, `--validate-generated-prompt` | `2677` | `9de386b90040` |
| `win32_2pc_engine.py` | `DOM-01` | `--allow-governance-override`, `--git-sync`, `--keep-staging`, `--milestone`, `--promote-staging`, `--repo-root`, `--staging-dir`, `--verify-baseline` | `1383` | `3cc80a130bb9` |

## 4. Profilo di Igiene del Contesto Globale

Lo scanner ha rilevato `0` skill esterne nella configurazione utente.
Il totale combinato misura `16` skill piatte nel contesto globale.
L'isolamento consigliato disattiva i plugin esterni non richiesti durante le sessioni NK-Hub.

## 5. Comandi Rapidi di Consultazione e Verifica

Usa `scripts/nk_registry_indexer.py --sync` per rigenerare il manifesto in staging.
Usa `scripts/nk_registry_indexer.py --verify` per controllare l'allineamento SHA-256.
Usa `scripts/nk_registry_indexer.py --lookup DOM-01` per interrogare un dominio in O(1).

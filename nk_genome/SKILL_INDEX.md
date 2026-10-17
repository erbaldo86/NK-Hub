---
title: "NK Genome: Skill & Script Modular O(1) Index"
version: "3.5.1-MODULAR-INDEX-RSI2"
milestone_anchor_id: "NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2"
rsi_profile: "ste100_rsi"
---

# Indice Tassonomico Modulare O(1) (`SKILL_INDEX.md`)

Questo indice mappa i cinque domini funzionali di Nexus Keystone.
Il registro consente la risoluzione O(1) di skill, script e flag CLI.
Il manifesto traccia `16` skill canoniche e `32` moduli Python.

## 1. Mappa dei 5 Domini Funzionali (`DOM-01..DOM-05`)

| ID Dominio | Nome Dominio | Skill Primaria | Conteggio Skill | Conteggio Script |
| :--- | :--- | :--- | :---: | :---: |
| `DOM-01` | `GOV_AND_ROUTING` | `NK-Master-Hub` | `4` | `8` |
| `DOM-02` | `IDEATION_AND_ARCH` | `NK-Ideator` | `4` | `3` |
| `DOM-03` | `BUILD_AND_HEAL` | `NK-Python-Async-Builder` | `2` | `7` |
| `DOM-04` | `AUDIT_DAST_AND_RCA` | `NK-Security-Auditor` | `4` | `6` |
| `DOM-05` | `MEMORY_TELEMETRY_AND_DOCS` | `NK-Scribe` | `2` | `8` |

## 2. Registro delle Skill Vocazionali

La tabella seguente elenca ogni skill con il relativo dominio e hash SHA-256.

| Skill | Dominio | Livello Thinking | File Ausiliari | LOC | SHA-256 (12 char) |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `NK-Agent-Instruction-Forge` | `DOM-02` | `HIGH` | `0` | `52` | `fec665367cd9` |
| `NK-App-UX-Architect` | `DOM-02` | `HIGH` | `0` | `67` | `78937c449547` |
| `NK-Backend-Architect` | `DOM-02` | `HIGH` | `0` | `61` | `a02c837d8a9c` |
| `NK-Bug-Diagnostic-Engine` | `DOM-04` | `HIGH` | `2` | `50` | `abe067335e99` |
| `NK-Delta-Architect` | `DOM-03` | `HIGH` | `1` | `77` | `d660d7c05098` |
| `NK-Dynamic-Sandbox-StressTester` | `DOM-04` | `HIGH` | `0` | `54` | `78d323491fe2` |
| `NK-Episodic-Memory-Engine` | `DOM-05` | `HIGH` | `0` | `60` | `b09af87930a2` |
| `NK-Ideator` | `DOM-02` | `HIGH` | `1` | `59` | `467e4c81200b` |
| `NK-Master-Hub` | `DOM-01` | `HIGH` | `0` | `172` | `ffa5072811eb` |
| `NK-Oracle-Evaluator` | `DOM-04` | `HIGH` | `2` | `58` | `cc54481e9152` |
| `NK-Plan-Aligner` | `DOM-01` | `HIGH` | `0` | `58` | `688cbac791d6` |
| `NK-Python-Async-Builder` | `DOM-03` | `HIGH` | `0` | `56` | `6a7a532ab883` |
| `NK-Scribe` | `DOM-05` | `HIGH` | `2` | `67` | `1316eaadbd23` |
| `NK-Security-Auditor` | `DOM-04` | `HIGH` | `4` | `68` | `ff29556f6cc0` |
| `NK-Session-Controller` | `DOM-01` | `HIGH` | `4` | `95` | `210b3317eda6` |
| `NK-State-Router` | `DOM-01` | `HIGH` | `0` | `54` | `ffe20ab81b86` |

## 3. Registro degli Script Core, Schemi e Flag CLI

La tabella seguente mappa ogni modulo Python ai flag CLI verificati via AST.

| Script (`scripts/`) | Dominio | Flag CLI Supportati | LOC | SHA-256 (12 char) |
| :--- | :---: | :--- | :---: | :--- |
| `ast_guard_validator.py` | `DOM-04` | `--allowed-mutations`, `--stage-dir`, `--target` | `1165` | `9c99de2d5c93` |
| `ast_repo_mapper.py` | `DOM-02` | `--export`, `--focus-files`, `--json`, `--max-tokens`, `--mode`, `--repo-map`, `--root`, `--snapshot-out` | `1596` | `35b0d3415f71` |
| `async_heartbeat_signaler.py` | `DOM-03` | `--interval`, `--json`, `--max-beats`, `--once`, `--step-name`, `--task-id`, `--test` | `244` | `eb12de020c2f` |
| `auto_heal_pipeline.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `467` | `8026ea63092d` |
| `dast_sandbox_runner.py` | `DOM-04` | `--json`, `--script`, `--timeout` | `754` | `515d365208e3` |
| `deterministic_api_cache.py` | `DOM-03` | `--clear`, `--force-refresh`, `--health`, `--stats` | `303` | `504dd3f749eb` |
| `env_capability_probe.py` | `DOM-02` | `--check-module`, `--export`, `--json` | `333` | `cee0957e4c68` |
| `external_project_scaffolder.py` | `DOM-02` | `--name`, `--target` | `217` | `81ac179d6b8b` |
| `healing_snapshot_rollback.py` | `DOM-03` | `--cleanup`, `--create`, `--rollback` | `382` | `61d5efcb7818` |
| `invisible_healing_loop.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `440` | `f78599ed86ac` |
| `memory_3tier_engine.py` | `DOM-05` | `--append`, `--base-dir`, `--content`, `--domain`, `--json`, `--output`, `--profile`, `--query`, `--recall`, `--tags`, `--tier1-sync`, `--title` | `923` | `f32b65c8db2a` |
| `micro_hud_renderer.py` | `DOM-05` | `--agent`, `--ascii`, `--domain`, `--json`, `--mutex`, `--percent` | `366` | `2e4ca26b5190` |
| `nk_active_runtime_sentinel.py` | `DOM-05` | `--check`, `--json`, `--profile`, `--transcript` | `141` | `9b4532271bd8` |
| `nk_auto_inning.py` | `DOM-05` | `--audit`, `--close-inning`, `--json`, `--transcript`, `--tuning-file` | `99` | `04228bcf05a2` |
| `nk_compliance_checker.py` | `DOM-05` | `--json`, `--min-score`, `--transcript` | `551` | `d0aca0502bd8` |
| `nk_context_sentry.py` | `DOM-05` | `--json`, `--profile`, `--transcript`, `--verbose` | `356` | `2079bc63f5d7` |
| `nk_registry_indexer.py` | `DOM-01` | `--apply-global-filter`, `--json`, `--lookup`, `--root`, `--stage-dir`, `--sync`, `--verify` | `1396` | `5c3833f8b41b` |
| `nk_session_bootstrap.py` | `DOM-01` | `--force-full`, `--json` | `602` | `671fb5c960b5` |
| `nk_session_handoff.py` | `DOM-01` | `--generate-prompt`, `--output-dir`, `--porcelain`, `--transcript` | `160` | `1055fede72d7` |
| `nk_swarm_messenger.py` | `DOM-01` | `--payload`, `--payload-file`, `--recipient`, `--sender` | `97` | `bcde0726690b` |
| `oracle_evaluator_l3.py` | `DOM-04` | `--actual`, `--expected`, `--json` | `400` | `2234bd46e8e5` |
| `platform_runner.py` | `DOM-03` | `--cmd`, `--cwd`, `--no-capture`, `--timeout` | `231` | `80313464c8a0` |
| `preflight_health_check.py` | `DOM-05` | `--check-only`, `--root` | `491` | `d0861442e840` |
| `quality_baseline_manager.py` | `DOM-05` | `--check`, `--check-only`, `--file`, `--json`, `--metrics`, `--recalibrate`, `--update` | `423` | `8923d50a39b3` |
| `rsi_convergence_engine.py` | `DOM-04` | `--benchmark-suite`, `--help`, `--json`, `--profile`, `--root`, `--verify`, `--vibe-check` | `1343` | `99cd4b1d4d8c` |
| `safe_cleanup_dev_servers.py` | `DOM-03` | `--dry-run`, `--json`, `--workspace-root` | `247` | `aed1388e3fda` |
| `sbfl_engine.py` | `DOM-04` | `--json`, `--records-file` | `545` | `56f8c7e2249b` |
| `sbfl_pytest_bridge.py` | `DOM-04` | `--cwd`, `--json`, `--target-file`, `--test-cmd` | `426` | `0ff0a6c3b252` |
| `schemas/dual_ledgers.py` | `DOM-01` | `nessuno` | `445` | `9154623e74df` |
| `schemas/nk_ipc_contracts.py` | `DOM-01` | `nessuno` | `259` | `7f5fdbf583cf` |
| `vibe_sprint_router.py` | `DOM-01` | `--capsule`, `--discovery-check`, `--files`, `--json`, `--prompt`, `--test` | `544` | `10405a036518` |
| `win32_2pc_engine.py` | `DOM-01` | `--git-sync`, `--milestone`, `--promote-staging`, `--repo-root`, `--staging-dir`, `--verify-baseline` | `919` | `a0a30838d4b2` |

## 4. Profilo di Igiene del Contesto Globale

Lo scanner ha rilevato `0` skill esterne nella configurazione utente.
Il totale combinato misura `16` skill piatte nel contesto globale.
L'isolamento consigliato disattiva i plugin esterni non richiesti durante le sessioni NK-Hub.

## 5. Comandi Rapidi di Consultazione e Verifica

Usa `scripts/nk_registry_indexer.py --sync` per rigenerare il manifesto in staging.
Usa `scripts/nk_registry_indexer.py --verify` per controllare l'allineamento SHA-256.
Usa `scripts/nk_registry_indexer.py --lookup DOM-01` per interrogare un dominio in O(1).

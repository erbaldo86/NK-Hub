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
| `NK-Agent-Instruction-Forge` | `DOM-02` | `HIGH` | `0` | `54` | `e58821e3ea30` |
| `NK-App-UX-Architect` | `DOM-02` | `HIGH` | `0` | `68` | `15f2c815f1f7` |
| `NK-Backend-Architect` | `DOM-02` | `HIGH` | `0` | `63` | `4b920ed1d35e` |
| `NK-Bug-Diagnostic-Engine` | `DOM-04` | `HIGH` | `2` | `50` | `1b3bb0b8a47c` |
| `NK-Delta-Architect` | `DOM-03` | `HIGH` | `1` | `80` | `6f5f86e44ef0` |
| `NK-Dynamic-Sandbox-StressTester` | `DOM-04` | `HIGH` | `0` | `65` | `bc36ac0a3c41` |
| `NK-Episodic-Memory-Engine` | `DOM-05` | `HIGH` | `0` | `60` | `ca3b2f614d25` |
| `NK-Ideator` | `DOM-02` | `HIGH` | `1` | `60` | `02f5b2c2ba22` |
| `NK-Master-Hub` | `DOM-01` | `HIGH` | `0` | `176` | `26459e2e3557` |
| `NK-Oracle-Evaluator` | `DOM-04` | `HIGH` | `2` | `58` | `414c99318d80` |
| `NK-Plan-Aligner` | `DOM-01` | `HIGH` | `0` | `56` | `33d5c1ba6545` |
| `NK-Python-Async-Builder` | `DOM-03` | `HIGH` | `0` | `58` | `19f1fbcce2b4` |
| `NK-Scribe` | `DOM-05` | `HIGH` | `2` | `68` | `6512f2b18da0` |
| `NK-Security-Auditor` | `DOM-04` | `HIGH` | `4` | `68` | `acaec8019278` |
| `NK-Session-Controller` | `DOM-01` | `HIGH` | `4` | `96` | `b9d515f2f149` |
| `NK-State-Router` | `DOM-01` | `HIGH` | `0` | `56` | `ccd64f0dd9ee` |

## 3. Registro degli Script Core, Schemi e Flag CLI

La tabella seguente mappa ogni modulo Python ai flag CLI verificati via AST.

| Script (`scripts/`) | Dominio | Flag CLI Supportati | LOC | SHA-256 (12 char) |
| :--- | :---: | :--- | :---: | :--- |
| `ast_guard_validator.py` | `DOM-04` | `--allowed-mutations`, `--json`, `--stage-dir`, `--target` | `1221` | `6e145586b886` |
| `ast_repo_mapper.py` | `DOM-02` | `--export`, `--focus-files`, `--json`, `--max-tokens`, `--mode`, `--repo-map`, `--root`, `--snapshot-out` | `1596` | `35b0d3415f71` |
| `async_heartbeat_signaler.py` | `DOM-03` | `--interval`, `--json`, `--max-beats`, `--once`, `--step-name`, `--task-id`, `--test` | `244` | `eb12de020c2f` |
| `auto_heal_pipeline.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `506` | `a850481b4909` |
| `dast_sandbox_runner.py` | `DOM-04` | `--json`, `--script`, `--timeout` | `754` | `7f87c1a03ac1` |
| `deterministic_api_cache.py` | `DOM-03` | `--clear`, `--force-refresh`, `--health`, `--stats` | `303` | `504dd3f749eb` |
| `env_capability_probe.py` | `DOM-02` | `--check-module`, `--export`, `--json` | `333` | `cee0957e4c68` |
| `external_project_scaffolder.py` | `DOM-02` | `--name`, `--target` | `223` | `af5a666b5a42` |
| `healing_snapshot_rollback.py` | `DOM-03` | `--cleanup`, `--create`, `--rollback` | `382` | `61d5efcb7818` |
| `invisible_healing_loop.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `440` | `f78599ed86ac` |
| `memory_3tier_engine.py` | `DOM-05` | `--append`, `--base-dir`, `--content`, `--domain`, `--json`, `--output`, `--profile`, `--query`, `--recall`, `--tags`, `--tier1-sync`, `--title` | `934` | `03f2be3a2ec5` |
| `micro_hud_renderer.py` | `DOM-05` | `--agent`, `--ascii`, `--domain`, `--json`, `--mutex`, `--percent` | `366` | `2e4ca26b5190` |
| `nk_active_runtime_sentinel.py` | `DOM-05` | `--check`, `--json`, `--profile`, `--transcript` | `141` | `a32eb2abef76` |
| `nk_auto_inning.py` | `DOM-05` | `--audit`, `--close-inning`, `--json`, `--transcript`, `--tuning-file` | `107` | `904422703c62` |
| `nk_compliance_checker.py` | `DOM-05` | `--json`, `--min-score`, `--transcript` | `561` | `c959ddf0b93b` |
| `nk_context_sentry.py` | `DOM-05` | `--json`, `--profile`, `--transcript`, `--verbose` | `356` | `2079bc63f5d7` |
| `nk_registry_indexer.py` | `DOM-01` | `--apply-global-filter`, `--json`, `--lookup`, `--root`, `--stage-dir`, `--sync`, `--verify` | `1966` | `e73e14b580d2` |
| `nk_session_bootstrap.py` | `DOM-01` | `--force-full`, `--json` | `611` | `bb0650f5497c` |
| `nk_session_handoff.py` | `DOM-01` | `--generate-prompt`, `--output-dir`, `--transcript` | `160` | `1055fede72d7` |
| `nk_swarm_messenger.py` | `DOM-01` | `--payload`, `--payload-file`, `--recipient`, `--sender` | `97` | `bcde0726690b` |
| `oracle_evaluator_l3.py` | `DOM-04` | `--actual`, `--expected`, `--json` | `404` | `2481dc94adc2` |
| `platform_runner.py` | `DOM-03` | `--cmd`, `--cwd`, `--no-capture`, `--timeout` | `231` | `80313464c8a0` |
| `preflight_health_check.py` | `DOM-05` | `--check-only`, `--root` | `491` | `d0861442e840` |
| `quality_baseline_manager.py` | `DOM-05` | `--check`, `--check-only`, `--file`, `--json`, `--metrics`, `--recalibrate`, `--update` | `423` | `8923d50a39b3` |
| `rsi_convergence_engine.py` | `DOM-04` | `--benchmark-suite`, `--json`, `--profile`, `--root`, `--verify`, `--vibe-check` | `1390` | `04274bb9f5c3` |
| `safe_cleanup_dev_servers.py` | `DOM-03` | `--dry-run`, `--json`, `--workspace-root` | `247` | `aed1388e3fda` |
| `sbfl_engine.py` | `DOM-04` | `--json`, `--records-file` | `545` | `56f8c7e2249b` |
| `sbfl_pytest_bridge.py` | `DOM-04` | `--cwd`, `--json`, `--target-file`, `--test-cmd` | `426` | `0ff0a6c3b252` |
| `schemas/dual_ledgers.py` | `DOM-01` | `nessuno` | `445` | `9154623e74df` |
| `schemas/nk_ipc_contracts.py` | `DOM-01` | `nessuno` | `259` | `7f5fdbf583cf` |
| `vibe_sprint_router.py` | `DOM-01` | `--capsule`, `--classify-prompt`, `--discovery-check`, `--files`, `--json`, `--mode`, `--prompt`, `--task`, `--test` | `1050` | `348c813f5135` |
| `win32_2pc_engine.py` | `DOM-01` | `--git-sync`, `--milestone`, `--promote-staging`, `--repo-root`, `--staging-dir`, `--verify-baseline` | `919` | `a0a30838d4b2` |

## 4. Profilo di Igiene del Contesto Globale

Lo scanner ha rilevato `0` skill esterne nella configurazione utente.
Il totale combinato misura `16` skill piatte nel contesto globale.
L'isolamento consigliato disattiva i plugin esterni non richiesti durante le sessioni NK-Hub.

## 5. Comandi Rapidi di Consultazione e Verifica

Usa `scripts/nk_registry_indexer.py --sync` per rigenerare il manifesto in staging.
Usa `scripts/nk_registry_indexer.py --verify` per controllare l'allineamento SHA-256.
Usa `scripts/nk_registry_indexer.py --lookup DOM-01` per interrogare un dominio in O(1).

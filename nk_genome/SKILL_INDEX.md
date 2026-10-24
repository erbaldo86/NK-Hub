---
title: "NK Genome: Skill & Script Modular O(1) Index"
version: "4.5.0-STE100-Unified"
milestone_anchor_id: "NK-MS-20261024-HOLISTIC-SANITATION-v4.5.0-RSI"
rsi_profile: "ste100_rsi"
---

# Indice Tassonomico Modulare O(1) (`SKILL_INDEX.md`)

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

| Skill | Dominio | Livello Thinking | File Ausiliari | LOC | SHA-256 (12 char) |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `NK-Agent-Instruction-Forge` | `DOM-02` | `HIGH` | `0` | `55` | `a8362847fdd9` |
| `NK-App-UX-Architect` | `DOM-02` | `HIGH` | `0` | `69` | `63dd7e32af0c` |
| `NK-Backend-Architect` | `DOM-02` | `HIGH` | `0` | `64` | `1fc6c78130e9` |
| `NK-Bug-Diagnostic-Engine` | `DOM-04` | `HIGH` | `2` | `51` | `eb4c912d0bdc` |
| `NK-Delta-Architect` | `DOM-03` | `HIGH` | `1` | `82` | `a4f1f87b4f60` |
| `NK-Dynamic-Sandbox-StressTester` | `DOM-04` | `HIGH` | `0` | `66` | `f1a6f25035ee` |
| `NK-Episodic-Memory-Engine` | `DOM-05` | `HIGH` | `0` | `61` | `db681d946a9e` |
| `NK-Ideator` | `DOM-02` | `HIGH` | `1` | `61` | `fef5413390f0` |
| `NK-Master-Hub` | `DOM-01` | `HIGH` | `0` | `182` | `d2a72e0899ec` |
| `NK-Oracle-Evaluator` | `DOM-04` | `HIGH` | `2` | `61` | `b5f5bb3eb36c` |
| `NK-Plan-Aligner` | `DOM-01` | `HIGH` | `0` | `58` | `8d5a4ef88d7f` |
| `NK-Python-Async-Builder` | `DOM-03` | `HIGH` | `0` | `60` | `b7641642f822` |
| `NK-Scribe` | `DOM-05` | `HIGH` | `2` | `69` | `d32f5dc200e4` |
| `NK-Security-Auditor` | `DOM-04` | `HIGH` | `4` | `70` | `4c82a444eaa1` |
| `NK-Session-Controller` | `DOM-01` | `HIGH` | `4` | `100` | `f18abe97a494` |
| `NK-State-Router` | `DOM-01` | `HIGH` | `0` | `57` | `e23ce1f9d28a` |

## 3. Registro degli Script Core, Schemi e Flag CLI

La tabella seguente mappa ogni modulo Python ai flag CLI verificati via AST.

| Script (`scripts/`) | Dominio | Flag CLI Supportati | LOC | SHA-256 (12 char) |
| :--- | :---: | :--- | :---: | :--- |
| `ast_guard_validator.py` | `DOM-04` | `--allowed-mutations`, `--json`, `--output-json`, `--stage-dir`, `--target` | `1523` | `c9e5067e5d43` |
| `ast_repo_mapper.py` | `DOM-02` | `--export`, `--focus-files`, `--json`, `--max-tokens`, `--mode`, `--repo-map`, `--root`, `--snapshot-out` | `1596` | `35b0d3415f71` |
| `async_heartbeat_signaler.py` | `DOM-03` | `--interval`, `--json`, `--max-beats`, `--once`, `--step-name`, `--task-id`, `--test` | `244` | `eb12de020c2f` |
| `auto_heal_pipeline.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `506` | `a850481b4909` |
| `dast_sandbox_runner.py` | `DOM-04` | `--json`, `--overlay-staging`, `--script`, `--staging-dir`, `--timeout` | `1131` | `e41a8cf95b7d` |
| `deterministic_api_cache.py` | `DOM-03` | `--clear`, `--force-refresh`, `--health`, `--stats` | `303` | `504dd3f749eb` |
| `env_capability_probe.py` | `DOM-02` | `--check-module`, `--export`, `--json` | `333` | `cee0957e4c68` |
| `external_project_scaffolder.py` | `DOM-02` | `--dry-run`, `--force`, `--json`, `--name`, `--retrofit`, `--target` | `318` | `4401d22cacd2` |
| `healing_snapshot_rollback.py` | `DOM-03` | `--cleanup`, `--create`, `--rollback` | `382` | `61d5efcb7818` |
| `invisible_healing_loop.py` | `DOM-03` | `--cwd`, `--json`, `--max-cycles`, `--target-file`, `--test-cmd` | `440` | `f78599ed86ac` |
| `memory_3tier_engine.py` | `DOM-05` | `--append`, `--base-dir`, `--content`, `--domain`, `--json`, `--output`, `--profile`, `--query`, `--recall`, `--tags`, `--tier1-sync`, `--title` | `934` | `03f2be3a2ec5` |
| `micro_hud_renderer.py` | `DOM-05` | `--agent`, `--ascii`, `--domain`, `--json`, `--mutex`, `--percent` | `366` | `2e4ca26b5190` |
| `nk_active_runtime_sentinel.py` | `DOM-05` | `--check`, `--json`, `--profile`, `--transcript` | `141` | `a32eb2abef76` |
| `nk_auto_inning.py` | `DOM-05` | `--audit`, `--close-inning`, `--json`, `--transcript`, `--tuning-file` | `107` | `904422703c62` |
| `nk_compliance_checker.py` | `DOM-05` | `--json`, `--min-score`, `--transcript` | `618` | `6133d94ca10e` |
| `nk_context_sentry.py` | `DOM-05` | `--actual-context-tokens`, `--json`, `--profile`, `--transcript`, `--verbose` | `437` | `acadbad7c325` |
| `nk_hook_gate.py` | `DOM-01` | `--check`, `--command`, `--content`, `--conversation-id`, `--event`, `--init`, `--project-root`, `--strict-external`, `--target` | `330` | `af510d18e62a` |
| `nk_registry_indexer.py` | `DOM-01` | `--apply-global-filter`, `--json`, `--lookup`, `--root`, `--stage-dir`, `--sync`, `--sync-staging`, `--verify` | `2083` | `2ea90af5439c` |
| `nk_session_bootstrap.py` | `DOM-01` | `--conversation-id`, `--force-full`, `--hook`, `--json`, `--project-root`, `--transcript` | `882` | `f972f6551587` |
| `nk_session_handoff.py` | `DOM-01` | `--compile-task-prompt`, `--generate-prompt`, `--output-dir`, `--persist-brief-id`, `--project-root`, `--prompt-text`, `--transcript` | `356` | `13c1834dd162` |
| `nk_swarm_messenger.py` | `DOM-01` | `--payload`, `--payload-file`, `--recipient`, `--sender` | `97` | `bcde0726690b` |
| `nk_transcript_tools.py` | `DOM-04` | `--brain-dir`, `--conversation-id`, `--file`, `--lock-file`, `--message`, `--output`, `--reason`, `--root`, `--target`, `--test-a`, `--test-b`, `--text`, `--transcript` | `484` | `a8351546b21f` |
| `oracle_evaluator_l3.py` | `DOM-04` | `--actual`, `--expected`, `--json` | `404` | `2481dc94adc2` |
| `platform_runner.py` | `DOM-03` | `--cmd`, `--cwd`, `--no-capture`, `--timeout` | `231` | `80313464c8a0` |
| `preflight_health_check.py` | `DOM-05` | `--check-only`, `--json`, `--root` | `518` | `0df46d7ab4a6` |
| `quality_baseline_manager.py` | `DOM-05` | `--check`, `--check-only`, `--file`, `--json`, `--metrics`, `--recalibrate`, `--update` | `423` | `4349944778c3` |
| `rsi_convergence_engine.py` | `DOM-04` | `--benchmark-suite`, `--json`, `--persist-telemetry`, `--profile`, `--root`, `--sast-report`, `--strict-verify`, `--verify`, `--vibe-check` | `1694` | `ce6415430a21` |
| `safe_cleanup_dev_servers.py` | `DOM-03` | `--dry-run`, `--json`, `--ports`, `--workspace-root` | `334` | `b37cc2dc0f98` |
| `sbfl_engine.py` | `DOM-04` | `--json`, `--records-file` | `545` | `56f8c7e2249b` |
| `sbfl_pytest_bridge.py` | `DOM-04` | `--cwd`, `--json`, `--target-file`, `--test-cmd` | `426` | `0ff0a6c3b252` |
| `schemas/dual_ledgers.py` | `DOM-01` | `nessuno` | `445` | `9154623e74df` |
| `schemas/nk_ipc_contracts.py` | `DOM-01` | `nessuno` | `290` | `0981d31b780f` |
| `vibe_sprint_router.py` | `DOM-01` | `--capsule`, `--changed-lines`, `--classify-prompt`, `--discovery-check`, `--files`, `--json`, `--meta-prompt-gate`, `--mode`, `--no-gate`, `--prompt`, `--task`, `--test`, `--validate-generated-prompt` | `1820` | `b21fa8a7da94` |
| `win32_2pc_engine.py` | `DOM-01` | `--git-sync`, `--keep-staging`, `--milestone`, `--promote-staging`, `--repo-root`, `--staging-dir`, `--verify-baseline` | `1168` | `1566671505b5` |

## 4. Profilo di Igiene del Contesto Globale

Lo scanner ha rilevato `0` skill esterne nella configurazione utente.
Il totale combinato misura `16` skill piatte nel contesto globale.
L'isolamento consigliato disattiva i plugin esterni non richiesti durante le sessioni NK-Hub.

## 5. Comandi Rapidi di Consultazione e Verifica

Usa `scripts/nk_registry_indexer.py --sync` per rigenerare il manifesto in staging.
Usa `scripts/nk_registry_indexer.py --verify` per controllare l'allineamento SHA-256.
Usa `scripts/nk_registry_indexer.py --lookup DOM-01` per interrogare un dominio in O(1).

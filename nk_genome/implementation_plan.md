# NK Genome: Implementation Plan (`v4.0.0-Native-Swarm-Playbooks` / `v3.0.0-STE100-Unified`)

> **Badge di Certificazione:** 🛡️ `[NK-BRIEF-STATUS: AUDITED_AND_CONVERGED 🟢]` | `[RSI-CONVERGENCE: CONVERGED_OPTIMAL (Δ=0, Q=100.0) 🟢]`  
> **Milestone Anchor ID:** `NK-MS-20261018-COLD-TRIAL-v4.0.0-RSI`  
> **Versione Target:** `v4.0.0-Native-Swarm-Playbooks` (`v3.0.0-STE100-Unified` Compatible)  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, frasi `<= 20` parole)  
> **Modalità Esecutiva:** Protocollo CRV 4.0 in `.staging/` con promozione atomica Win32 2PC (`[RULE-00]`)

---

## 1. Sintesi di Convergenza RSI ($\Delta_k = 0$, $Q(S_k) = 100.0$)

Questo piano esecutivo coordina l'evoluzione di Nexus Keystone fino alla release **`v4.0.0-Native-Swarm-Playbooks`**.
Il piano integra l'architettura **Tensor-RSI 2D**, i `5` Sub-Agenti Nativi e i `16` Playbook Procedurali.
Tutte le modifiche preservano il `100%` di successo sugli `86` Golden e Stress Tests certificati.

* **Iterazione 1 ($k=1$):** Verifica empirica sul codice reale e sintesi preliminare ($\Delta_1 = 17$, $Q(S_1) = 83.8095$).
* **Iterazione 2 ($k=2$):** Audit avversariale di `NK-RSI-Auditor` su link, guardie `GT-01..GT-14` e soglia `20` parole.
* **Iterazione 3 ($k=3$):** Raffinamento sintattico ASD-STE100 e certificazione finale ($\Delta_3 = 0$, $Q(S_3) = 100.0000$).

---

## 2. Le 14 Guardie Obbligatorie per i Golden Tests (`GT-01..GT-14`)

Ogni Builder deve rispettare le `14` guardie seguenti per mantenere il `100%` di pass rate:

1. **`GT-01` (`scripts/nk_context_sentry.py`):** Mantieni i default `GREEN_STEP_THRESHOLD = 70` e `RED_STEP_THRESHOLD = 100` (`80000 / 120000` token). Preserva le stringhe di warning e attiva `150 / 250` step con `profile="argon"`.
2. **`GT-02` (`scripts/nk_active_runtime_sentinel.py`):** Mantieni le soglie `60 / 85 / 100` in `calculate_state(steps, profile="standard")`. Attiva `120 / 180 / 250` con `profile="argon"`.
3. **`GT-03` (`scripts/nk_compliance_checker.py`):** Mantieni `DDI_DIRECT_STREAK_LIMIT = 12` e la stringa `"Objective DDI violation: {max_consecutive_direct} consecutive direct tools without delegation"`.
4. **`GT-04` (`scripts/nk_swarm_messenger.py` e `scripts/nk_context_sentry.py`):** Mantieni il taglio a `1800` caratteri (MSS) e `SWARM_MSG_HARD_CAP = 2000` (MTU).
5. **`GT-05` (`scripts/memory_3tier_engine.py`):** Mantieni `TIER1_TOKEN_CAP: int = 350` come default e `TIER1_TOKEN_CAP_ARGON: int = 1200` per `argon`.
6. **`GT-06` (`scripts/ast_repo_mapper.py`):** Mantieni i budget `0`, `256` (`mode_c`), `512` (`mode_b`) e `1024` (`mode_a`). Mantieni `512`, `1500` e `4000` per i profili `argon_mode_*`.
7. **`GT-07` (`scripts/sbfl_pytest_bridge.py`):** Garantire `loc.suspiciousness == 1.0`, il formato `"<file>:<line>"` e `len(payload_str) < 320`.
8. **`GT-08` (`.agents/AGENTS.md`, `NK-Master-Hub`, `NK-Session-Controller`, `nk_compliance_checker.py`):** Preserva in `[RULE-00.5]` tutti gli `8` trigger verbali, `"fast-stat"`, `"120"`, `"[0]"`..`"[14]"` e `"10. UNIFIED_ONBOARDING_COMPLIANCE"`.
9. **`GT-09` (`scripts/env_capability_probe.py`):** Mantieni `STANDARD_MODULES_TO_PROBE`, `THIRD_PARTY_MODULES_TO_PROBE` e la formula di `summary["total_probed"]`.
10. **`GT-10` (`scripts/nk_compliance_checker.py`):** Mantieni il default `100` per `operational_score` e `rsi_convergence_score` su transcript privi di errori.
11. **`GT-11` (`scripts/rsi_convergence_engine.py`):** Mantieni `profile="code_rsi"` in `compute_delta()`, `strict_monotonic: bool = False` in `check_hard_gate_regression()` e `verdict="HALTED_CYCLE_DETECTED"`.
12. **`GT-12` (`scripts/rsi_convergence_engine.py`):** Imposta `max_sentence_words: int = 20` insieme allo skip del frontmatter YAML (`---`) e alla bonifica delle `20` frasi in `.agents/`.
13. **`GT-13` (`scripts/quality_baseline_manager.py`):** Supporta sia `check`/`update` posizionali sia i flag `--file`, `--update` e `--check-only`.
14. **`GT-14` (`[RULE-00.1]`):** Non assegnare mai `write_to_file` sulla produzione né `enable_write_tools: true` agli Auditor (`[6]..[11], NK-RSI-Auditor`).

---

## 3. Piano Esecutivo Atomico in 12 Work Package (`WP1..WP12`)

### WP1: Bonifica dei 14 Script Core e Motore Tensor-RSI (`scripts/`)
1. **`ast_guard_validator.py`:** Aggiungi `--stage-dir` come alias di `--target` e rileva nell'AST `eval()`, `exec()`, `pickle.loads()`, `yaml.load()` e `MagicMock`.
2. **`quality_baseline_manager.py`:** Aggiungi `sast_critical_violations` e `rsi_residual_delta` a `LOWER_IS_BETTER_KEYS` (`EXT-01`) e implementa `argparse` retrocompatibile (`GT-13`).
3. **`memory_3tier_engine.py`:** Importa `win32_atomic_replace` da `win32_2pc_engine.py`, aggiungi la CLI `__main__`, persisti `tier1_active_capsule.json` e aggiungi il recall RRF adattivo.
4. **`rsi_convergence_engine.py`:** Imposta `max_sentence_words = 20` con skip YAML `---`, aggiungi `RSIProfileRegistry` (`5` profili), `--vibe-check` (`< 500 ms`) e il CoVe CLI AST Gate.
5. **`auto_heal_pipeline.py`:** Collega `run_pipeline()` a `RSIConvergenceEngine.run_convergence_loop()`, popola `RSIDefectVector` con `ASTGuardValidator` ed elimina lo snapshot finale ridondante.
6. **`safe_cleanup_dev_servers.py` e `async_heartbeat_signaler.py`:** Imposta `_workspace_root` come default in `run_cleanup()` e aggiungi `argparse` a `async_heartbeat_signaler.py`.
7. **`nk_session_bootstrap.py` e `nk_active_runtime_sentinel.py`:** Salva `mtime`/`size` del transcript nella cache del bootstrap; filtra i sub-agenti e leggi `NK_MODEL_PROFILE` nel Sentinel (`EXT-02`).
8. **`nk_compliance_checker.py` e `nk_auto_inning.py`:** Esenta le sessioni `write_calls == 0` dalla penalità AST, leggi `rsi_telemetry.jsonl` (`GT-10`) e imposta fail-closed in `nk_auto_inning.py`.
9. **Altri 6 Script:** Aggiorna `vibe_sprint_router.py`, `win32_2pc_engine.py`, `deterministic_api_cache.py`, `nk_session_handoff.py` (`EXT-03`) e deduplica `nk_ipc_contracts.py`.

### WP2: Allineamento delle 16 Skill, Regolamento e L3 Meta-RSI (`.agents/`)
1. Aggiungi `[RULE-RSI.1]` in `.agents/AGENTS.md` (preservando `v3.0.0-STE100-Unified` e `GT-08`) e sincronizza `saturation_thresholds.yaml`.
2. Correggi i permessi `tools` nelle 16 skill (`GT-14`) e allinea i 4 domini di memoria. Rinomina inoltre il Turno 5 in `Final Handoff`, uniforma i `6 Gate` e aggiungi `<rsi_micro_loop>`.
3. Riscrivi le `20` frasi oltre `20` parole in `.agents/`, rimuovi il trattino in `NK-Master-Hub/SKILL.md:161` e crea `tests/evals/skill_golden_eval_set.json`.

### WP3: Riallineamento Tetralogia Sovrana 4/4, `nk_tracking/` e CI/CD
1. Crea `nk_genome/idea_canvas.md`, correggi le frasi lunghe in `concept_map.md`, aggiorna `structural_tree.md` e rigenera `repo_map.md` a `4.000` token Argon.
2. Ripara le righe `23-25` di `session_anchor.jsonl`, allinea `quality_baseline.json` e rimuovi i file `.bak_*` e i relitti legacy.
3. Aggiorna `.github/workflows/ci.yml` (`100+ Golden Tests`, `--check-only`, `--verify`), `README.md`, `README.it.md` e `PATCH_NOTES.md`.

### WP4: Espansione a 108 Golden Tests, Verifica TAS e Commit 2PC
1. Correggi il test CLI in `test_quality_baseline_manager.py` e il path in `test_ast_repo_mapper.py`.
2. Aggiungi `8` nuovi test reali Zero-Mock per `async_heartbeat_signaler`, `RSIProfileRegistry`, `--vibe-check`, CoVe CLI AST Gate, `LOWER_IS_BETTER_KEYS` e `tier1_active_capsule.json`.
3. Esegui l'audit TAS completo in `.staging/` (`108/108 PASS`, `ast_guard`, `rsi --verify` con $\Delta=0, Q=100.0$) e promuovi atomicamente via `win32_2pc_engine.py`.

### WP5: Ottimizzazioni Post-Audit Forense (`OPT-1..OPT-11`) e Stress Evaluation Suite (`NK-MS-20261017-OPT5-STRESS-v3.2.0`)
1. **`OPT-1` (`scripts/nk_session_bootstrap.py`):** Ottimizza `_check_root_hygiene` e `_verify_context_sentry` con cache `root_mtime` e lettura tail per scendere sotto `50 ms`.
2. **`OPT-2` (`scripts/rsi_convergence_engine.py`):** Propaga `--profile` in `main()`, isola i `.md` dei progetti esterni in `--root` e supporta `--benchmark-suite`.
3. **`OPT-3` (`scripts/vibe_sprint_router.py` e `NK-Ideator`):** Aggiungi `Mode D (Analytical Discovery & Benchmark)` su `--prompt` e abilita `call_mcp_tool` in `NK-Ideator/SKILL.md`.
4. **`OPT-4` (`NK-Session-Controller/SKILL.md`):** Imponi l'uso dei nomi canonici delle skill in `define_subagent` con obbligo di `.staging/` e commit 2PC.
5. **`OPT-5` (`.agents/AGENTS.md`):** Vieta i one-liner `python -c` multi-riga su PowerShell a favore di script in `scratch/` e integra `Mode D`.
6. **`OPT-6`, `OPT-7` e `OPT-12` (`nk_compliance_checker.py`, `nk_context_sentry.py`):** Rileva exit code `!= 0` reali, esenta `REFINING` e valida `ast_guard` delegato.
7. **`OPT-8` e `OPT-9` (`nk_session_bootstrap.py`, `rsi_convergence_engine.py`):** Elimina la tripla lettura cache usando `os.replace` atomico, sincronizza `append_telemetry_record` ed escludi `.venv`/`.git` da `rglob`.
8. **`OPT-10` e `OPT-11` (`preflight_health_check.py`, `healing_snapshot_rollback.py`, `nk_ipc_contracts.py`):** Unifica `os.walk`, rendi atomico `snapshot_manifest.json` e allinea `mode_d` nei contratti IPC.
9. **Stress Suite (`tests/test_nk_ecosystem_stress_opt5.py`):** Espandi a `15` test Zero-Mock su bootstrap, telemetria concorrente, compliance checker `OPT-12` e router.

### WP6: Riforma Costituzionale `GT-68` Zero-Padding (`NK-MS-20261017-GT68-PARETO-v3.3.0`)
1. **Regola `[RULE-01.10]` (`.agents/AGENTS.md` e `NK-Oracle-Evaluator/SKILL.md`):** Ricalibra il pavimento costituzionale a `68` Golden Tests ortogonali (`>= 60` Core Tests).
2. **Consolidamento Suite (`tests/`):** Elimina `55` test superflui e unifica i sottoprocessi con fixture `scope="module"` (`68/68 PASS` in `< 7 s`).
3. **Ricalibrazione Baseline (`nk_tracking/quality_baseline.json` e `scripts/quality_baseline_manager.py`):** Allinea `total_golden_tests`, `unit_tests_total` e `unit_tests_passed` a `68` (`100.0% PASS`).

### WP7: Rifondazione Neuro-Simbolica TAS v4.0 (`1A + 2C + 3B`)
1. **Opzione 1A (`NK-Security-Auditor`):** Crea in `resources/` le matrici modulari `tas_l1_module_audit.md`, `tas_l2_ipc_contract_audit.md` e `tas_l3_fullstack_system_audit.md`.
2. **Opzione 2C (Ibrido Neuro-Simbolico):** Unisci la sequenza deterministica Python con l'esplorazione probabilistica di Argon validata dal Referee PoC.
3. **Opzione 3B (`scripts/`):** Espandi `SASTConstructChecker` ed esponi `--allowed-mutations` in `ast_guard_validator.py`.
4. **Riparazione Motori Core:** Collega `sbfl_engine.py` in `sbfl_pytest_bridge.py`, ripara i nodi misti in `oracle_evaluator_l3.py` ed estendi `dast_sandbox_runner.py`.
5. **Canali Tensor-RSI v4.0:** Aggiungi `poc_confirmed_exploits` e `semantic_drift_findings` a `RSIDefectVector` in `rsi_convergence_engine.py`.

### WP8: Indice Tassonomico Modulare O(1) e Disaccoppiamento SSOT (`NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2`)
1. **Regola `[RULE-01.14]` (`.agents/AGENTS.md`):** Istituisci il registro modulare O(1) basato su `nk_genome/nk_registry_manifest.json` e `nk_genome/SKILL_INDEX.md`.
2. **Indicizzatore AST (`scripts/nk_registry_indexer.py`):** Mappa `5` domini, `16` skill e `30` script con `--sync`, `--verify` e `--lookup`.
3. **Disaccoppiamento SSOT (`preflight_health_check.py`, `vibe_sprint_router.py`):** Carica skill e domini direttamente dal manifesto JSON eliminando le liste hardcoded.
4. **Dual-Schema Lifecycle (`.agents/hooks.json`):** Espone gli hook sia sotto la chiave `hooks` sia a livello root con `timeout` e `timeout_ms`.

### WP9: Ottimizzazione Vibe-Coding Post-Stress-Test Bandi (`OPT-VIBE-1..5`)
1. **`OPT-VIBE-1` (`rsi_convergence_engine.py`, `vibe_sprint_router.py`):** Rendi `--vibe-check` eseguibile senza argomenti (`< 500 ms`) e aggiungi `--task` e `--mode` nel router.
2. **`OPT-VIBE-2` (`nk_compliance_checker.py`, `nk_active_runtime_sentinel.py`):** Riconosci `step_index in (0, 1)` nei sub-agenti, esenta DDI/AST su report e assegna `argon`.
3. **`OPT-VIBE-3` (`AGENTS.md`, `NK-Session-Controller`, `NK-Master-Hub`):** Imponi `schedule` anti-deadlock dopo avvio sub-agenti e il cap di `100` step per sub-agente.
4. **`OPT-VIBE-4` (`ast_guard_validator.py`, `NK-Python-Async-Builder`, `NK-Delta-Architect`):** Supporta target multipli in `ast_guard_validator.py` e documenta `--promote-staging --repo-root` sui progetti esterni.
5. **`OPT-VIBE-5` (`NK-Session-Controller`, `NK-Master-Hub`):** Inietta `<env_capsule>` nei prompt sub-agenti (`python -m pytest`, divieto `view_file` esplorativo e timeout loop).

### WP10: Fase 1 Bonifica, Validazione e Riconversione Playbook delle 16 Skill (`NK-MS-20261018-SKILL-PLAYBOOK-PHASE1-v3.6.0`)
1. **`BUG-01` e `BUG-02` (`NK-Episodic-Memory-Engine`, `NK-Bug-Diagnostic-Engine`):** Correggi il percorso in `nk_tracking/memory_3tier/` e allinea gli alias `ARCH` (`02`) e `DEVX` (`03`).
2. **`BUG-03` (`NK-Scribe`, `scribe_knowledge.md`, `verification_oracles.md`):** Sostituisci i riferimenti obsoleti a `100` Golden Tests con `68` Golden Tests (`[RULE-01.10]`).
3. **`BUG-04` (`handoff_anchor_schema.md`, `NK-Session-Controller`):** Aggiorna lo schema JSON ai `6` Gate di Cold Review e aggiungi `MODE_D_DISCOVERY`.
4. **`OVERLAP-01..04` (`DOM-01..DOM-05`):** Integra `nk_registry_indexer.py` e `nk_swarm_messenger.py` in `NK-Master-Hub` e specializza `NK-State-Router` sul controllo drift O(1).
5. **`GAP-01` (`NK-Dynamic-Sandbox-StressTester`, `NK-Oracle-Evaluator`):** Integra il playbook di verifica E2E Browser, DOM e Lighthouse tramite `chrome-devtools-mcp` e `puppeteer`.
6. **`GAP-02` (`NK-Delta-Architect`):** Riconverti la skill nel playbook Full-Stack, Frontend UI (`TypeScript`, `React`, `Tailwind`, `generative_ui`) e Surgical Refiner.
7. **`GAP-03` (`NK-Ideator`, `NK-Backend-Architect`, `NK-Agent-Instruction-Forge`):** Integra `tavily-mcp`, `google-docs-mcp`, `firebase-mcp-server`, `env_capability_probe.py`, `external_project_scaffolder.py` e `nk_registry_indexer.py --sync`.

### WP11: Fase 2 Architettura Sub-Agenti Nativi, Router O(1) e Stress Suite a 3 Livelli (`NK-MS-20261018-NATIVE-AGENTS-PHASE2-v3.7.0`)
1. **5 Sub-Agenti Esecutori Nativi (`.agents/agents/*/agent.md`):** Crea `NK-Specifier-Agent`, `NK-Builder-Agent`, `NK-Security-DAST-Auditor` (`enable_write_tools: false`), `NK-Scribe-Agent` e aggiorna `NK-RSI-Auditor` (`enable_write_tools: false`).
2. **Indice O(1) Dual-Layer (`scripts/nk_registry_indexer.py`):** Aggiungi `scan_native_agents()` e la chiave `native_agents_index` in `nk_registry_manifest.json` preservando `len(skills_index) == 16`. Verifica in `--verify` gli hash SHA-256 dei `5` `agent.md` e la guardia hardware `GT-14` (`enable_write_tools: false` sugli Auditor).
3. **Router Nativo e Fast-Bypass (`scripts/vibe_sprint_router.py`):** Mappa ogni dominio/skill al rispettivo `native_subagent` e calcola `fast_bypass_eligible` per `Mode C` (`<= 150` LOC) preservando `primary_agent`.
4. **Allineamento Governance (`.agents/AGENTS.md`, `NK-Master-Hub`, `NK-Session-Controller`):** Documenta i `5` Sub-Agenti Nativi in `.agents/agents/` e il Fast-Bypass `Mode C` rispettando il budget `< 24.000` byte.
5. **Strategia di Stress-Test a 3 Livelli (`tests/test_phase2_3tier_stress_suite.py`):** Valida Livello 1 (Strutturale/Concorrenza 16-thread), Livello 2 (Flussi End-to-End Mode A/B/C/D e Rollback) e Livello 3 (Avversariale SAST/DAST, Boundary e Benchmark Prima/Dopo) con loop RSI fino a $\Delta_k = 0$.

### WP12: Collaudo Avversariale a Freddo (Zero-Bias Cold Trial) e Pulizia Release (`NK-MS-20261018-COLD-TRIAL-v4.0.0-RSI`)
1. **Router O(1) Multi-Skill (`scripts/vibe_sprint_router.py`, `scripts/nk_registry_indexer.py`):** Aggiungi `--classify-prompt` e `SKILL_ROUTING_RULES` per `10/10` di accuratezza sui prompt ibridi. Proteggi i file della Tetralogia dalle collisioni di sottostringa e filtra l'estrazione AST dei flag CLI a `add_argument`.
2. **Raffinamento dei 9 Moduli Core (`scripts/`):** Correggi `rsi_convergence_engine.py` (`<yaml_metadata_card>`, punti interni, asimmetria `w_tfail == 0`, `--vibe-check` su `.staging`), `ast_guard_validator.py` (`--json` e `.staging` assente), `auto_heal_pipeline.py` (snapshot ciclo 1 e flag opzionali), `external_project_scaffolder.py`, `nk_auto_inning.py`, `memory_3tier_engine.py` e `oracle_evaluator_l3.py`.
3. **Ottimizzazione Performance e Pulizia Scorie (`dast_sandbox_runner.py`, `nk_session_bootstrap.py`):** Aggiungi `ignoredirs=[sys.prefix, sys.exec_prefix]` al tracer DAST e filtra i transcript dei sub-agenti con `<env_capsule>`. Rimuovi la cartella duplicata `nk_tracking/episodic_memory/`, i file `.bak_*` e i vecchi report `v1.9..v3.5`.

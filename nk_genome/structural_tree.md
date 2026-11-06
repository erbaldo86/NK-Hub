# NK Genome: Structural Tree Master (`v5.0.0-STE100-Unified` / `v4.8.0-STE100-Unified` / `v4.7.0-STE100-Unified` / `v4.5.1-STE100-Unified` / `v4.5.0-STE100-Unified` / `v4.4.0-STE100-Unified` / `v4.0.0-Native-Swarm-Playbooks` / `v3.0.0-STE100-Unified`)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢] | [RSI-CONVERGENCE: CONVERGED_OPTIMAL (Δ=0, Q=100.0) 🟢]  
> **Milestone Anchor ID:** `NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI` (`NK-MS-20261106-HOLISTIC-CLEANSE-AND-DEAD-CODE-PURGE-v4.8.0-RSI` / `NK-MS-20261031-HOLISTIC-STRESS-AND-TEST-CONSOLIDATION-v4.7.0-RSI` / `NK-MS-20261025-INTRINSIC-VIBE-RSI-REMEDIATION` / `NK-MS-20261024-HOLISTIC-SANITATION-v4.5.0-RSI`)  
> **Versione Target:** `v5.0.0-STE100-Unified` (`v4.8.0-STE100-Unified` / `v4.7.0-STE100-Unified` / `v4.5.1-STE100-Unified` / `v4.5.0-STE100-Unified` / `v4.4.0-STE100-Unified` / `v4.3.0-Super-Plan-Triad-RSI` / `v4.0.0-Native-Swarm-Playbooks` / `v3.0.0-STE100-Unified` Compatible)  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`)  
> **Stato Produzione:** 100% Sola Lettura (`[RULE-00]`)

---

## 1. Albero Strutturale Canonico del Repository `NK-Hub` (`v5.0.0-STE100-Unified`)

L'albero seguente rappresenta la struttura release bonificata di `NK-Hub`. Le cartelle dei progetti esterni risiedono in `G:/Il mio Drive/Antigravity/NK_External_Projects/` (`BS-03`). La cartella duplicata `nk_tracking/episodic_memory/`, i file `.bak_*` e i report legacy sono stati rimossi. I `5` Sub-Agenti, i `16` Playbook e i `34` moduli (`36` file Python) sono in `nk_genome/nk_registry_manifest.json`.

```text
G:/Il mio Drive/Antigravity/NK_Hub/
├── .agents/
│   ├── AGENTS.md                                    # Regolamento Master in ASD-STE100 (v5.0.0-STE100-Unified, formula Delta_k)
│   ├── hooks.json                                   # Hook del ciclo di vita (SessionStart, PostToolUse, Stop)
│   ├── plugins/
│   │   └── nk-gate/                                 # Plugin Hook Nativo (plugin.json e hooks.json map<string, HookSpec>)
│   │       ├── plugin.json
│   │       └── hooks.json
│   ├── agents/                                      # 5 Sub-Agenti Esecutori Nativi Pre-Registrati (v5.0.0)
│   │   ├── NK-Specifier-Agent/
│   │   │   └── agent.md                             # Sub-Agente DOM-02 (Ideazione, UX/UI, Backend, Allineamento 4/4)
│   │   ├── NK-Builder-Agent/
│   │   │   └── agent.md                             # Sub-Agente DOM-03 (Sviluppo Python, Full-Stack UI e .staging/)
│   │   ├── NK-Security-DAST-Auditor/
│   │   │   └── agent.md                             # Sub-Agente DOM-04 Read-Only (SAST L1-L3, DAST, Browser E2E, SBFL)
│   │   ├── NK-RSI-Auditor/
│   │   │   └── agent.md                             # Sub-Agente DOM-04 Read-Only (6 Gate, Convergenza RSI, DAG Kahn)
│   │   └── NK-Scribe-Agent/
│   │       └── agent.md                             # Sub-Agente DOM-05 (Changelog SSOT, Repo-Map, Baseline, Memoria 3-Tier)
│   ├── rules/
│   │   └── anti_crash_rules.md                      # Regole operative Win32, I/O, UTF-8, /compact e Onestà Epistemica
│   └── skills/                                      # 16 Playbook Procedurali + 16 File Ausiliari Verificati e Linkati
│       ├── NK-Master-Hub/                           # [L3] Sovrano Infrastrutturale (2PC Mutex, Routing 2-Tier, Dashboard [0]-[14])
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Rimossi 5 script in scripts/ e 3 YAML in resources/]
│       ├── NK-Ideator/                              # [0] Sintesi Concettuale L0, SCAMPER e /grill-me
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Link esplicito a resources/idea_canvas_template.md]
│       │   └── resources/
│       │       └── idea_canvas_template.md          # [File Ausiliario 01/16: Spostato da NK-Master-Hub/resources/]
│       ├── NK-App-UX-Architect/                     # [1] Architettura UI/UX L3, Design System e Generative UI
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Tetralogia 4/4, generate_image, <agent-embed>]
│       ├── NK-Backend-Architect/                    # [2] Architettura Backend L2, DAG Kahn, Pydantic v2 e OpenAPI
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Tetralogia 4/4, contratti IPC strict]
│       ├── NK-Agent-Instruction-Forge/              # [3] Meta-Ingegneria Skill e Regole (/learn, /boost, [RULE-STE100])
│       │   └── SKILL.md                             # [v3.0.0-STE100 | DOM-02 IDEATION_AND_ARCH, byte-budget e ASD-STE100]
│       ├── NK-Python-Async-Builder/                 # [4] Builder Primario in .staging/ e Fast-Healing Loop
│       │   └── SKILL.md                             # [v3.0.0-STE100 | view_file <= 800 righe, auto_heal + rsi_convergence_engine]
│       ├── NK-Delta-Architect/                      # [5] Playbook Full-Stack, Frontend UI e Surgical Refiner in .staging/
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Link esplicito a resources/delta_brief_template.md]
│       │   └── resources/
│       │       └── delta_brief_template.md          # [File Ausiliario 02/16: Aggiornato con Execution Receipt v3.0]
│       ├── NK-Security-Auditor/                     # [6] Critic Swarm TAS v4.0 Neuro-Simbolico SAST L1/L2/L3 in Sola Lettura
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Protocollo 3 Gate + Cascade L3 -> L2 -> L1 + 4 risorse linkate]
│       │   └── resources/
│       │       ├── audit_checklists_l1_l2_l3.md     # [File Ausiliario 03/16: Matrice di Routing Settoriale e Checklist TAS-Self]
│       │       ├── tas_l1_module_audit.md           # [File Ausiliario 04/16: Matrice Audit Universale Livello 1]
│       │       ├── tas_l2_ipc_contract_audit.md     # [File Ausiliario 05/16: Matrice Audit Contratti IPC Livello 2]
│       │       └── tas_l3_fullstack_system_audit.md # [File Ausiliario 06/16: Matrice Audit Full-Stack e Cascade L3]
│       ├── NK-Oracle-Evaluator/                     # [7] Oracolo Deterministico Cold Audit (Gate 1-6) e /browser
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Rimossi 5 script duplicati in scripts/ e resources/]
│       │   └── references/
│       │       ├── anti_pattern_guards.md           # [File Ausiliario 07/16: Guardie Anti-Mock e Anti-Goodharting]
│       │       └── verification_oracles.md          # [File Ausiliario 08/16: Rubrica di Verifica Deterministica]
│       ├── NK-Dynamic-Sandbox-StressTester/         # [8] Critic Swarm DAST e Browser E2E MCP in %TEMP%\nk_sandbox_<uuid>\
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Integrazione chrome-devtools-mcp e puppeteer]
│       ├── NK-Bug-Diagnostic-Engine/                # [9] Localizzatore RCA e SBFL Ochiai (<320 char JSON, GT-07)
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Rimosso trace_rca_analyzer.py]
│       │   └── resources/
│       │       ├── false_bug_rejection_rules.yaml   # [File Ausiliario 09/16: Regole di Rigetto Falsi Bug]
│       │       └── rca_dual_language_template.md    # [File Ausiliario 10/16: Template RCA Tecnico + Utente]
│       ├── NK-Plan-Aligner/                         # [10] Certificatore Turno 4 della Tetralogia Sovrana 4/4
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Allineamento 4/4 con rsi_convergence_engine.py --verify]
│       ├── NK-State-Router/                         # [11] Verificatore Topologico DAG di Kahn in Sola Lettura
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Verifica SHA-256 di 16 skill, 5 sub-agenti e 34 script]
│       ├── NK-Scribe/                               # [12] Cronista Post-Commit ([RULE-00.2]) e Sincronizzatore SSOT
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Filtro act a 7 stati, [RULE-01.10], sync docs]
│       │   └── resources/
│       │       ├── activity_anchor_schema.md        # [File Ausiliario 11/16: Schema con VALID_ANCHOR_ACTS a 7 valori]
│       │       └── scribe_knowledge.md              # [File Ausiliario 12/16: Regole di Mirroring e Changelog SSOT]
│       ├── NK-Episodic-Memory-Engine/               # [13] Motore Memoria 3-Tier (BM25 + Cosine RRF)
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Alias ARCH/SEC/OPS/DEVX, cap 350 std / 1200 argon]
│       └── NK-Session-Controller/                   # [14] Sovrano Critico di Sessione, Loop RSI e Cold Review a 6 Gate
│           ├── SKILL.md                             # [v3.0.0-STE100 | Rimosso agentic_strategies_reference.md, preserva GT-08]
│           └── resources/
│               ├── clean_handoff_protocol.md        # [File Ausiliario 13/16: Handoff con /compact e nk_session_handoff.py]
│               ├── handoff_anchor_schema.md         # [File Ausiliario 14/16: Schema JSONL Handoff]
│               ├── prompt_templates.md              # [File Ausiliario 15/16: Template 1-12 con capsule epistemiche]
│               └── saturation_thresholds.yaml       # [File Ausiliario 16/16: Soglie Dual-Profile standard vs argon]
├── .github/
│   └── workflows/
│       └── ci.yml                                   # Pipeline CI/CD aggiornata (253 Golden & Stress Tests, --verify)
├── nk_genome/                                       # Tetralogia Sovrana 4/4 + Idea Canvas L0 + Indice O(1) + Changelog SSOT
│   ├── idea_canvas.md                               # [L0] Idea Canvas preliminare (6 sezioni, SCAMPER, STORM, v5.0.0)
│   ├── concept_map.md                               # [1/4] Visione Concettuale e Architettura v5.0.0-STE100-Unified
│   ├── structural_tree.md                           # [2/4] Albero Strutturale Canonico v5.0.0 (5 Sub-Agenti, 16 Playbook, 253 Test)
│   ├── implementation_plan.md                       # [3/4] Piano Esecutivo Atomico WP-V5-1..WP-V5-4 e Guardie GT-01..GT-14
│   ├── repo_map.md                                  # [4/4] Snapshot AST Repo-Map a 4.000 token Argon (34 moduli + 24 moduli di test)
│   ├── SKILL_INDEX.md                               # Indice Tassonomico Modulare O(1) per i 5 Domini DOM-01..DOM-05
│   ├── nk_registry_manifest.json                    # Manifesto SSOT O(1) generato da nk_registry_indexer.py
│   └── PATCH_NOTES.md                               # Single Source of Truth del Changelog in nk_genome/
├── nk_tracking/                                     # Tracciamento, Telemetria, Memoria Episodica 3-Tier e Baseline Ratchet
│   ├── active_context.md                            # Contesto Attivo Sessione e Handoff Passivo Template 12 Puro NK_Hub
│   ├── anchor/
│   │   └── session_anchor.jsonl                     # Registro Eventi (bonificato da righe vuote, duplicati e timestamp fuori ordine)
│   ├── benchmark_suite/                             # Suite Benchmark Comparativa 50 Progetti
│   ├── memory_3tier/                                # Store Canonico a 3 Livelli per i 4 Domini (ARCH, SEC, OPS, DEVX)
│   │   └── tier1_active_capsule.json                # Capsula attiva Tier-1 per Pre-Warming < 2ms
│   ├── manifests/                                   # Manifesti Operativi dell'Hub
│   ├── reports_and_briefs/                          # Report di Audit e Certificazione TAS Grounded v5.0.0
│   │   ├── IB-20261106-82CC73.md                    # Intent Brief Sovereign Clean-Slate Release v5.0.0-STE100-Unified
│   │   └── TAS_Report_NK_Hub_v5_0_0_20261106.md     # Report Certificazione TAS 6 Gate v5.0.0-STE100-Unified
│   ├── oracle_lock.json                             # Sigillo Crittografico SHA-256 della Suite di Test ([RULE-ORACLE-LOCK])
│   ├── quality_baseline.json                        # Ratchet di Non-Regressione (68 pavimento GT-13, 253 test, 100.0% pass rate)
│   └── rsi_telemetry.jsonl                          # Ledger Crittografico SHA-256 delle iterazioni RSI
├── scripts/                                         # 34 Moduli Indicizzati (36 File Python totali inclusi __init__.py e schemas/)
│   ├── __init__.py                                  # [01] Package Marker
│   ├── ast_guard_validator.py                       # [02] Validatore Statico AST (SASTConstructChecker, --stage-dir, --json)
│   ├── ast_repo_mapper.py                           # [03] AST Repo-Mapper PageRank (fix serializzazione edges e GT-06)
│   ├── async_heartbeat_signaler.py                  # [04] Demone Heartbeat e Watchdog 45s (fix timer last_beat_time U-22)
│   ├── auto_heal_pipeline.py                        # [05] Pipeline Fast-Healing collegata a rsi_convergence_engine.py
│   ├── dast_sandbox_runner.py                       # [06] Sandbox Runner Win32 Job Objects (trace ignoredirs e CLI)
│   ├── deterministic_api_cache.py                   # [07] Cache SQLite WAL (fix connessione persistente BS-05)
│   ├── env_capability_probe.py                      # [08] Probe Ambiente (fix core vs optional preservando total_probed GT-09)
│   ├── external_project_scaffolder.py               # [09] Scaffolder Progetti Esterni (--target opzionale e blocco path interno)
│   ├── healing_snapshot_rollback.py                 # [10] Gestore Snapshot e Rollback SHA-256 (fix snapshot_manifest.json U-23)
│   ├── invisible_healing_loop.py                    # [11] Wrapper Compatibile collegato a auto_heal_pipeline.py e sbfl_engine.py
│   ├── memory_3tier_engine.py                       # [12] Motore Memoria 3-Tier (isolamento backup tmp_path, guardia 0-byte e GT-05)
│   ├── micro_hud_renderer.py                        # [13] Renderer Telemetrico UTF-8 allineato a MicroUIHUDState
│   ├── nk_active_runtime_sentinel.py                # [14] Sentinella Step Runtime (soglie default 60/85/100 GT-02 + profilo argon)
│   ├── nk_auto_inning.py                            # [15] Chiusura Inning (flag --transcript, --json e lettura JSON reale U-14)
│   ├── nk_compliance_checker.py                     # [16] Verificatore Conformità (fix DDI 12 GT-03, path GT-08 e default 100 GT-10)
│   ├── nk_context_sentry.py                         # [17] Sentinella Contesto (default 70/100 GT-01, MTU 2000 GT-04, profilo argon)
│   ├── nk_hook_gate.py                              # [18] Gate Runtime Hook stdlib (probe, write-gate, fasttrack, integrity, stop-evidence)
│   ├── nk_registry_indexer.py                       # [19] Indicizzatore Modulare O(1) (MANIFEST_VERSION 4.7.0 + RELEASE_VERSION 5.0.0)
│   ├── nk_session_bootstrap.py                      # [20] Session Bootstrap Gate <50ms (filtro <env_capsule>, auto-profilo argon)
│   ├── nk_session_handoff.py                        # [21] Generatore Handoff (lettura dinamica quality_baseline.json U-49)
│   ├── nk_swarm_messenger.py                        # [22] Formattatore Messaggi Swarm (taglio MSS 1800 char GT-04 e UTF-8)
│   ├── nk_transcript_tools.py                       # [23] Strumenti Forensi Transcript, Oracle-Lock SHA-256 e Linter Prompt AP-1..13
│   ├── oracle_evaluator_l3.py                       # [24] Valutatore DOM L3 (void tag HTML5, FileNotFoundError e split path Windows)
│   ├── platform_runner.py                           # [25] Esecutore Sottoprocessi UTF-8 (fix iniezione -u su stringhe BS-04)
│   ├── preflight_health_check.py                    # [26] Diagnostica Manutenzione (fix falso positivo auto_fix BS-01 e --check-only)
│   ├── quality_baseline_manager.py                  # [27] Gestore Ratchet Baseline (fix fail-closed su errore I/O BS-02 e exit 1)
│   ├── rsi_convergence_engine.py                    # [28] Motore RSI Dual-Metric (Delta_k + Q(S_k), <yaml_metadata_card>, --vibe-check)
│   ├── safe_cleanup_dev_servers.py                  # [29] Pulizia Dev Server (fix filtro psutil per CWD/cmdline U-13)
│   ├── sbfl_engine.py                               # [30] Motore Matematico SBFL Ochiai/Tarantula/DStar (<80 tok payload + CLI)
│   ├── sbfl_pytest_bridge.py                        # [31] Bridge Pytest SBFL (collegato a sbfl_engine.py e suspiciousness 1.0 GT-07)
│   ├── vibe_sprint_router.py                        # [32] Router O(1) Mode A/B/C/D (--classify-prompt e SKILL_ROUTING_RULES)
│   ├── win32_2pc_engine.py                          # [33] Motore Commit Atomico 2PC (cleanup __pycache__ e record_session_anchor_commit)
│   └── schemas/                                     # [34-36] Contratti Pydantic v2 e Dual Ledgers
│       ├── __init__.py                              # [34] Esportazione Schemi
│       ├── dual_ledgers.py                          # [35] TaskLedger e ProgressLedger (fix ctypes 64-bit e ERROR_ACCESS_DENIED U-25)
│       └── nk_ipc_contracts.py                      # [36] Contratti IPC Strict (IPCPointerReturn, GoalFailureManifest, RSISessionReport)
├── tests/                                           # Suite Consolidata Zero-Mock v5.0.0 (253 Golden e Stress Tests in 24 moduli di test, 100.0% PASS)
│   ├── __init__.py
│   ├── conftest.py                                  # Fixtures Pytest session-scoped aggiornate a v5.0.0
│   ├── evals/
│   │   └── skill_golden_eval_set.json               # Set di validazione L3 Meta-RSI per le 16 Skill
│   ├── test_active_sentinel_suite.py                # [Protetto da GT-02 e GT-04]
│   ├── test_ast_guard_validator.py                  # [Validazione AST, SASTConstructChecker e --allowed-mutations]
│   ├── test_ast_repo_mapper.py                      # [Protetto da GT-06]
│   ├── test_auto_heal_pipeline.py                   # [Protetto da GT-07]
│   ├── test_context_sentry.py                       # [Protetto da GT-01]
│   ├── test_core_platform_utilities.py              # [Suite consolidata 14 test utilità core e invisible_healing_loop.py]
│   ├── test_dast_sandbox.py                         # [Validazione Shadow Sandbox e Referee PoC]
│   ├── test_intrinsic_vibe_sandbox_stress.py        # [74 Stress Test Avversariali Protocolli Vibe Intrinseci S1..S5]
│   ├── test_memory_3tier.py                         # [Protetto da GT-05]
│   ├── test_nk_ecosystem_stress_opt5.py             # [Stress suite OPT-1..OPT-12]
│   ├── test_nk_functional_certification_multilevel.py # [17 Test Funzionali ed E2E di Certificazione Multilivello WP18..WP20]
│   ├── test_nk_registry_indexer.py                  # [Validazione Indice Modulare O(1) e Filtro 61 Skill]
│   ├── test_phase2_3tier_stress_suite.py            # [Stress suite a 3 livelli L1/L2/L3 per i 5 Sub-Agenti Nativi]
│   ├── test_quality_baseline_manager.py             # [Protetto da GT-13 e Ratchet 68 Golden Tests]
│   ├── test_rsi_convergence_engine.py               # [Protetto da GT-11, GT-12 e canali TAS v4.0]
│   ├── test_sbfl_engine.py                          # [Validazione SBFL Ochiai/Tarantula/DStar]
│   ├── test_schemas_and_contracts.py                # [Validazione contratti Pydantic v2 strict]
│   ├── test_super_plan_v6_triad.py                  # [Validazione Super Plan v6.0: nk_hook_gate, nk_transcript_tools, lint-prompt]
│   ├── test_triad_epistemic_governance_v44.py       # [Validazione v4.4.0: Anti-Goodhart 100x, SAST-GAMING-D01..04, report-conflict, AP-8/9]
│   ├── test_v460_competitive_integration_suite.py   # [Suite consolidata 30 test competitivi WP-0c..WP-4 v4.6.0]
│   ├── test_v470_holistic_stress_suite.py           # [Suite avversariale 12 test permanenti S1..S6 v4.7.0]
│   ├── test_vibe_sprint_router.py                   # [Validazione Mode A/B/C/D, Gate L0 e AST depth]
│   ├── test_win32_2pc.py                            # [Validazione transazionale Win32 2PC]
│   └── stress/
│       ├── __init__.py
│       └── test_real_sandbox_stress.py              # [Protetto da GT-01 e GT-03]
├── nk_docs_and_setup/                               # Documentazione Utente, Guide, Installer e Configurazione Workspace
│   ├── 00_MAPPA_LIBRERIA_NK.md                      # Mappa strutturale deduplicata della libreria in ASD-STE100
│   ├── README.md                                    # Documentazione Master EN (allineata a v5.0.0 e 253 Golden e Stress Tests)
│   ├── README.it.md                                 # Documentazione Master IT (allineata 1:1 a README.md in ASD-STE100)
│   ├── GUIDA_INSTALLAZIONE.md                       # Guida Setup Bilingue IT+EN aggiornata a v5.0.0-STE100-Unified
│   ├── LICENSE                                      # Licenza del repository
│   ├── install.ps1                                  # Installer PowerShell aggiornato a v5.0.0-STE100-Unified
│   ├── install.sh                                   # Installer Bash aggiornato a v5.0.0-STE100-Unified
│   ├── requirements.txt                             # Dipendenze Core (pydantic>=2.7.0,<3.0.0, psutil>=5.9.8,<8.0.0, pytest>=8.2.0,<10.0.0)
│   └── Antigravity.code-workspace                   # Configurazione Workspace IDE Multi-Root (NK_Hub + NK_External_Projects)
├── pytest.ini                                       # Configurazione Pytest per i 253 test (245 baseline)
└── .gitignore                                       # Esclusioni Git (.staging/*, .wal/, scratch/*, NK_External_Projects/)
```

---

## 2. Matrice Completa dei 34 Moduli Indicizzati in `scripts/` e dei 253 Golden e Stress Tests (`v5.0.0`)

| # | Modulo Core (`scripts/`) | Intervento Chirurgico in `v5.0.0-STE100-Unified` | Guardia di Compatibilità | File di Test (`tests/`) |
| :---: | :--- | :--- | :---: | :--- |
| 1 | `ast_guard_validator.py` | Aggiunge `self.function_depth` (`U-20`), `--stage-dir`, `--allowed-mutations` e `SASTConstructChecker`. Blocca `PYTEST_CURRENT_TEST`, `currentframe` e `f_globals` (`WP16..WP20`). | Nessuna | `test_ast_guard_validator.py` |
| 2 | `ast_repo_mapper.py` | Salva e ricarica `edges` in `%TEMP%\nk_diagnostics\repo_map_cache.json`. Risolve archi cross-modulo e rimuove dead-code residuo (`WP-V5-1`). | **`GT-06`** (`0/256/512/1024`) | `test_ast_repo_mapper.py` |
| 3 | `async_heartbeat_signaler.py` | Rimuove `self.last_beat_time = now` dal ramo `else:` di `_run_loop()` (`U-22`). Mappa i nomi dei thread in `dump_diagnostics()`. | Nessuna | `test_rsi_convergence_engine.py` |
| 4 | `auto_heal_pipeline.py` | Evita snapshot inutili dopo l'ultimo tentativo fallito. Integra il calcolo RSI in `AutoHealSessionReport`. | Nessuna | `test_auto_heal_pipeline.py` |
| 5 | `dast_sandbox_runner.py` | Dichiara `argtypes`/`restype` a 64-bit su `kernel32` (`U-24`). Controlla `INVALID_HANDLE_VALUE` e preserva `command[2:]`. Copia `data/` e `benchmark_empirico_v7/` (`WP16`). | Nessuna | `test_dast_sandbox.py` |
| 9 | `healing_snapshot_rollback.py` | Persiste `snapshot_manifest.json` su disco in modo atomico per supportare `--rollback` e `--cleanup` (`U-23`). | Nessuna | `test_auto_heal_pipeline.py` |
| 10 | `invisible_healing_loop.py` | Delega l'esecuzione reale a `auto_heal_pipeline.py` e `sbfl_engine.py` eliminando la classe duplicata. | Nessuna | `test_schemas_and_contracts.py` |
| 11 | `memory_3tier_engine.py` | Isola i backup `.bak_N` in `tmp_path` e aggiunge la guardia sui file a `0` byte (`WP-V5-1`). Supporta `TIER1_TOKEN_CAP_ARGON = 1200`. | **`GT-05`** (`350` tok default) | `test_memory_3tier.py` |
| 13 | `nk_active_runtime_sentinel.py` | Preserva le soglie `60/85/100` nel profilo `standard` e aggiunge `--profile argon` (`120/180/250`). | **`GT-02`** (`60/85/100`) | `test_active_sentinel_suite.py` |
| 14 | `nk_auto_inning.py` | Passa `["--transcript", args.transcript, "--json"]` a `nk_compliance_checker.py` e legge il vero `composite_score` (`U-14`). | Nessuna | `test_active_sentinel_suite.py` |
| 16 | `nk_context_sentry.py` | Esclude `len(thinking)` in profilo `argon` (`150/250` step). Penalizza `send_message > 2000` solo sui ritorni dai sub-agenti (`U-02`). | **`GT-01`**, **`GT-04`** | `test_context_sentry.py` + `stress` |
| 17 | `nk_hook_gate.py` | Implementa il gate runtime stdlib con `probe`, `write-gate`, `fasttrack`, `integrity` e `stop-evidence` (`WP15..WP20`). | Nessuna | `test_super_plan_v6_triad.py` |
| 18 | `nk_registry_indexer.py` | Mantiene `MANIFEST_VERSION = "4.7.0-STE100-Unified"` e aggiunge `RELEASE_VERSION = "5.0.0-STE100-Unified"` (`WP-V5-1`). | **`GT-14`** | `test_nk_registry_indexer.py` |
| 20 | `nk_session_handoff.py` | Legge `unit_tests_total` da `quality_baseline.json` (`68` pavimento `GT-13`, `253` test) e usa context manager UTF-8 (`U-49`). | Nessuna | `test_active_sentinel_suite.py` |
| 21 | `nk_swarm_messenger.py` | Mantiene il taglio a `1.800` char (MSS), include `sender`/`recipient` e chiama `reconfigure_streams()`. | **`GT-04`** (`< 1800` char) | `test_active_sentinel_suite.py` |
| 22 | `nk_transcript_tools.py` | Implementa `locate`, `compliance`, `evidence`, `oracle-lock`, `report-conflict` e `lint-prompt` (`WP15..WP20`). Onora `--conversation-id` e rileva `AP-8..AP-13`. | Nessuna | `test_triad_epistemic_governance_v44.py` |
| 26 | `quality_baseline_manager.py` | Fallisce in modo sicuro su JSON corrotto senza sovrascrivere il file (`BS-02`). Protegge il pavimento di `68` Golden Tests (`GT-13`). | **`GT-13`** | `test_quality_baseline_manager.py` |
| 27 | `rsi_convergence_engine.py` | Calcola $\Delta_k$ e $Q(S_k)$ includendo `+ 100 * D_k`, `poc_confirmed_exploits` e `semantic_drift_findings`. Applica `G1..G6` e `--verify`. | **`GT-11`**, **`GT-12`** | `test_rsi_convergence_engine.py` |
| 29 | `sbfl_engine.py` | Mantiene `OchiaiDiagnosticPayload.estimate_token_count() < 80` e aggiunge l'interfaccia CLI `__main__`. | Nessuna | `test_sbfl_engine.py` |
| 30 | `sbfl_pytest_bridge.py` | Collega `sbfl_engine.py`, supporta spazi nei path Windows e garantisce `loc.suspiciousness == 1.0` (`U-19`). | **`GT-07`** (`< 320` char) | `test_auto_heal_pipeline.py` |
| 31 | `vibe_sprint_router.py` | Calcola `max_depth` AST, supporta `Mode D`, il Gate L0 (`--meta-prompt-gate`), il bypass `STATE_HANDOFF_STANDBY` e rimuove dead-code (`WP-V5-1`). | Nessuna | `test_vibe_sprint_router.py` + `test_intrinsic_vibe_sandbox_stress.py` |
| 32 | `win32_2pc_engine.py` | Pulisce `__pycache__` in `_cleanup_promoted_staging` e unifica `record_session_anchor_commit` nel flusso 2PC (`WP-V5-1`). | Nessuna | `test_win32_2pc.py` |
| 33 | `schemas/dual_ledgers.py` | Dichiara `c_void_p` su `OpenProcess`/`CloseHandle` e gestisce `TaskLedger` e `ProgressLedger` (`U-25`). | Nessuna | `test_schemas_and_contracts.py` |

---

## 3. Bilancio Finale dei File Ausiliari nelle 16 Skill (`51 -> 16 File`)

* **File Ausiliari Eliminati (`39` file):**
  1. `NK-Security-Auditor/resources/l1/*`, `l2/*`, `l3/*` (`21` file: contengono i 4 nodi `Fixer` che violano `[RULE-00.1]` e script CLI incompleti).
  2. `NK-Master-Hub/scripts/*` (`5` file: `run_hub.py` con `mock_subagent_task` che viola `[RULE-01.2]`, `ipc_engine.py`, `change_router.py`, `safe_parser.py`, `test_hub.py`).
  3. `NK-Master-Hub/resources/*.yaml` (`3` file: `drift_detection_rules.yaml`, `genome_autodiscovery_rules.yaml`, `lifecycle_intent_matrix.yaml` con riferimenti a `NK-Resume-Engine` inesistente).
  4. `NK-Oracle-Evaluator/scripts/*` e `resources/*` (`5` file: `cross_drive_stager.py` che viola `[RULE-00.1]`, `verifier_oracle.py`, `discrepancy_report_generator.py`, `runtime_trace_inspector.py`, `dual_state_visual_comparator.py`).
  5. `NK-Dynamic-Sandbox-StressTester/resources/*` (`3` file: `dynamic_pool_dispatcher.py`, `phase1_surgical_runner.py`, `phase2_chaos_swarm_runner.py` con fuzzer random che viola `[RULE-01.2]`).
  6. `NK-Bug-Diagnostic-Engine/resources/trace_rca_analyzer.py` (`1` file duplicato di `scripts/sbfl_engine.py`).
  7. `NK-Session-Controller/resources/agentic_strategies_reference.md` (`1` file duplicato statico).
* **File Ausiliari Mantenuti, Spostati e Creati (`16` file totali, 100% linkati nei `SKILL.md`):**
  1. `.agents/skills/NK-Ideator/resources/idea_canvas_template.md` *(spostato da `NK-Master-Hub/resources/`)*
  2. `.agents/skills/NK-Delta-Architect/resources/delta_brief_template.md`
  3. `.agents/skills/NK-Security-Auditor/resources/audit_checklists_l1_l2_l3.md` *(Matrice di Routing Settoriale e Checklist `TAS-Self`)*
  4. `.agents/skills/NK-Security-Auditor/resources/tas_l1_module_audit.md` *(Matrice TAS v4.0 Livello 1: Singolo Modulo)*
  5. `.agents/skills/NK-Security-Auditor/resources/tas_l2_ipc_contract_audit.md` *(Matrice TAS v4.0 Livello 2: Contratti IPC)*
  6. `.agents/skills/NK-Security-Auditor/resources/tas_l3_fullstack_system_audit.md` *(Matrice TAS v4.0 Livello 3: Sistema Full-Stack e Cascade)*
  7. `.agents/skills/NK-Oracle-Evaluator/references/anti_pattern_guards.md`
  8. `.agents/skills/NK-Oracle-Evaluator/references/verification_oracles.md`
  9. `.agents/skills/NK-Bug-Diagnostic-Engine/resources/false_bug_rejection_rules.yaml`
  10. `.agents/skills/NK-Bug-Diagnostic-Engine/resources/rca_dual_language_template.md`
  11. `.agents/skills/NK-Scribe/resources/activity_anchor_schema.md`
  12. `.agents/skills/NK-Scribe/resources/scribe_knowledge.md`
  13. `.agents/skills/NK-Session-Controller/resources/clean_handoff_protocol.md`
  14. `.agents/skills/NK-Session-Controller/resources/handoff_anchor_schema.md`
  15. `.agents/skills/NK-Session-Controller/resources/prompt_templates.md`
  16. `.agents/skills/NK-Session-Controller/resources/saturation_thresholds.yaml`

---

## 4. Target Architetturali Consolidati (`WP21`, `WP-C1..WP-C5` e `WP-V5-1..WP-V5-4` in `v5.0.0-STE100-Unified`)

* **Plugin Hook Nativo (`.agents/plugins/nk-gate/`):** Contiene `plugin.json` e `hooks.json` in schema puro `map<string, HookSpec>` senza alterare i `16` file ausiliari delle skill.
* **Invariante 34 Moduli (`scripts/`):** Il runner A/B (`P-06`) risiede come sottocomando `--ab-benchmark` in `scripts/rsi_convergence_engine.py` e `scripts/quality_baseline_manager.py` mantenendo `34` script indicizzati.
* **Isolamento Backup e Holdout (`%LOCALAPPDATA%`):** I backup `.bak_N` di `nk_tracking/` risiedono in `%LOCALAPPDATA%\nk_backups\memory_3tier\`, mentre i canary risiedono in `%LOCALAPPDATA%\nk_holdout\canary_v1.json`.

### Moduli di Test Consolidati (`v5.0.0-STE100-Unified`)
* `tests/test_v460_competitive_integration_suite.py`: `30` test competitivi `WP-0..WP-4` con `GAP-01` sotto `0.20s`.
* `tests/test_core_platform_utilities.py`: `14` test utilita di piattaforma e `invisible_healing_loop.py`.
* `tests/test_v470_holistic_stress_suite.py`: `12` test avversari permanenti `S1..S6` Zero-Mock.
* `tests/test_intrinsic_vibe_sandbox_stress.py`: `74` test di stress sui protocolli intrinseci.
* `tests/test_nk_functional_certification_multilevel.py`: `17` test di certificazione multilivello.

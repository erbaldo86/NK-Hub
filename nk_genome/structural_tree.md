# NK Genome: Structural Tree Master (`v3.5.1-RSI2` / `v3.4.0` / `v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified`)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢] | [RSI-CONVERGENCE: CONVERGED_OPTIMAL (Δ3=0, Q=100.0) 🟢]  
> **Milestone Anchor ID:** `NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2` (`NK-MS-20261015-TENSOR-RSI-v3.1.0`)  
> **Versione Target:** `v3.5.1-RSI2` (`v3.4.0` / `v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified` Compatible)  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`)  
> **Stato Produzione:** 100% Sola Lettura (`[RULE-00]`)

---

## 1. Albero Strutturale Canonico del Repository `NK-Hub` (`v3.5.1-RSI2`)

L'albero seguente rappresenta la struttura target bonificata di `NK-Hub`. Le 3 cartelle di progetti esterni (`Output Business Keystone/`, `Antigravity model/`, `google-docs-mcp/`) sono spostate in `G:/Il mio Drive/NK_External_Projects/` (`BS-03`). I 39 file ausiliari orfani o con mock nelle skill sono rimossi (`C-06`). I 16 file ausiliari validi sono tutti linkati nei rispettivi `SKILL.md`.

```text
G:/Il mio Drive/Antigravity/
├── .agents/
│   ├── AGENTS.md                                    # Regolamento Master in ASD-STE100 (~10.800 B, Dual-Alias, 8 trigger [RULE-00.5])
│   ├── hooks.json                                   # [NUOVO v3.0] Hook del ciclo di vita (SessionStart, PostToolUse, Stop)
│   ├── agents/
│   │   └── NK-RSI-Auditor/
│   │       └── agent.md                             # [NUOVO v3.0] Definizione Sub-Agente Critic/Evaluator Read-Only
│   ├── rules/
│   │   └── anti_crash_rules.md                      # Regole operative Win32, I/O, UTF-8 e /compact in ASD-STE100 (~1.400 B)
│   └── skills/                                      # 16 Skill Vocazionali + 16 File Ausiliari Verificati e Linkati (39 rimossi)
│       ├── NK-Master-Hub/                           # [L3] Sovrano Infrastrutturale (2PC Mutex, Routing 2-Tier, Dashboard [0]-[14])
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Rimossi 5 script in scripts/ e 3 YAML in resources/]
│       ├── NK-Ideator/                              # [0] Sintesi Concettuale L0, SCAMPER e /grill-me
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Link esplicito a resources/idea_canvas_template.md]
│       │   └── resources/
│       │       └── idea_canvas_template.md          # [File Ausiliario 01/16 - Spostato da NK-Master-Hub/resources/]
│       ├── NK-App-UX-Architect/                     # [1] Architettura UI/UX L3, Design System e Generative UI
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Tetralogia 4/4, generate_image, <agent-embed>]
│       ├── NK-Backend-Architect/                    # [2] Architettura Backend L2, DAG Kahn, Pydantic v2 e OpenAPI
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Tetralogia 4/4, contratti IPC strict]
│       ├── NK-Agent-Instruction-Forge/              # [3] Meta-Ingegneria Skill e Regole (/learn, /boost, [RULE-STE100])
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Verifica byte-budget e standard ASD-STE100]
│       ├── NK-Python-Async-Builder/                 # [4] Builder Primario in .staging/ e Fast-Healing Loop
│       │   └── SKILL.md                             # [v3.0.0-STE100 | view_file <= 800 righe, auto_heal + rsi_convergence_engine]
│       ├── NK-Delta-Architect/                      # [5] Surgical Refiner in .staging/ (Topologia 2-Tier a 1 livello)
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Link esplicito a resources/delta_brief_template.md]
│       │   └── resources/
│       │       └── delta_brief_template.md          # [File Ausiliario 02/16 - Aggiornato con Execution Receipt v3.0]
│       ├── NK-Security-Auditor/                     # [6] Critic Swarm TAS v4.0 Neuro-Simbolico SAST L1/L2/L3 in Sola Lettura
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Protocollo 3 Gate + Cascade L3 -> L2 -> L1 + 4 risorse linkate]
│       │   └── resources/
│       │       ├── audit_checklists_l1_l2_l3.md     # [File Ausiliario 03/16 - Matrice di Routing Settoriale e Checklist TAS-Self]
│       │       ├── tas_l1_module_audit.md           # [File Ausiliario 04/16 - NUOVO v3.4 Matrice Audit Universale Livello 1]
│       │       ├── tas_l2_ipc_contract_audit.md     # [File Ausiliario 05/16 - NUOVO v3.4 Matrice Audit Contratti IPC Livello 2]
│       │       └── tas_l3_fullstack_system_audit.md # [File Ausiliario 06/16 - NUOVO v3.4 Matrice Audit Full-Stack e Cascade L3]
│       ├── NK-Oracle-Evaluator/                     # [7] Oracolo Deterministico Cold Audit (Gate 1-6) e /browser
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Rimossi 5 script duplicati in scripts/ e resources/]
│       │   └── references/
│       │       ├── anti_pattern_guards.md           # [File Ausiliario 07/16 - Guardie Anti-Mock e Anti-Hardcoding]
│       │       └── verification_oracles.md          # [File Ausiliario 08/16 - Rubrica di Verifica Deterministica]
│       ├── NK-Dynamic-Sandbox-StressTester/         # [8] Critic Swarm DAST in %TEMP%\nk_sandbox_<uuid>\
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Rimossi i 3 script legacy con fuzzer random in resources/]
│       ├── NK-Bug-Diagnostic-Engine/                # [9] Localizzatore RCA e SBFL Ochiai (<320 char JSON, GT-07)
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Rimosso trace_rca_analyzer.py]
│       │   └── resources/
│       │       ├── false_bug_rejection_rules.yaml   # [File Ausiliario 09/16 - Regole di Rigetto Falsi Bug]
│       │       └── rca_dual_language_template.md    # [File Ausiliario 10/16 - Template RCA Tecnico + Utente]
│       ├── NK-Plan-Aligner/                         # [10] Certificatore Turno 4 della Tetralogia Sovrana 4/4
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Allineamento 4/4 con rsi_convergence_engine.py --verify]
│       ├── NK-State-Router/                         # [11] Verificatore Topologico DAG di Kahn in Sola Lettura
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Rimossa acquisizione lock concorrente al 2PC]
│       ├── NK-Scribe/                               # [12] Cronista Post-Commit ([RULE-00.2]) e Sincronizzatore SSOT
│       │   ├── SKILL.md                             # [v3.0.0-STE100 | Filtro act a 7 stati, [RULE-01.10], sync docs]
│       │   └── resources/
│       │       ├── activity_anchor_schema.md        # [File Ausiliario 11/16 - Schema con VALID_ANCHOR_ACTS a 7 valori]
│       │       └── scribe_knowledge.md              # [File Ausiliario 12/16 - Regole di Mirroring e Changelog SSOT]
│       ├── NK-Episodic-Memory-Engine/               # [13] Motore Memoria 3-Tier (BM25 + Cosine RRF)
│       │   └── SKILL.md                             # [v3.0.0-STE100 | Alias ARCH/SEC/OPS/DEVX, cap 350 std / 1200 argon]
│       └── NK-Session-Controller/                   # [14] Sovrano Critico di Sessione, Loop RSI e Cold Review a 6 Gate
│           ├── SKILL.md                             # [v3.0.0-STE100 | Rimosso agentic_strategies_reference.md, preserva GT-08]
│           └── resources/
│               ├── clean_handoff_protocol.md        # [File Ausiliario 13/16 - Handoff con /compact e nk_session_handoff.py]
│               ├── handoff_anchor_schema.md         # [File Ausiliario 14/16 - Schema JSONL Handoff]
│               ├── prompt_templates.md              # [File Ausiliario 15/16 - Template 8A 2-Tier senza os.replace, [14] corretto]
│               └── saturation_thresholds.yaml       # [File Ausiliario 16/16 - Soglie Dual-Profile standard vs argon]
├── .github/
│   └── workflows/
│       └── ci.yml                                   # Pipeline CI/CD aggiornata (68 Golden Tests, --check-only, --verify)
├── nk_genome/                                       # Tetralogia Sovrana 4/4 + Idea Canvas L0 + Indice O(1) + Changelog SSOT
│   ├── idea_canvas.md                               # [L0] Idea Canvas preliminare (6 sezioni, SCAMPER, STORM)
│   ├── concept_map.md                               # [1/4] Visione Concettuale e Architettura v3.5.1-RSI2 (Tensor-RSI + Indice O(1))
│   ├── structural_tree.md                           # [2/4] Albero Strutturale Canonico v3.5.1-RSI2 (16 File Ausiliari, 68 Golden Tests)
│   ├── implementation_plan.md                       # [3/4] Piano Esecutivo Atomico WP1-WP8 e Guardie GT-01..GT-14
│   ├── repo_map.md                                  # [4/4] Snapshot AST Repo-Map a 4.000 token Argon (34 moduli + test)
│   ├── SKILL_INDEX.md                               # [NUOVO v3.5] Indice Tassonomico Modulare O(1) per i 5 Domini DOM-01..DOM-05
│   ├── nk_registry_manifest.json                    # [NUOVO v3.5] Manifesto SSOT O(1) generato da nk_registry_indexer.py
│   └── PATCH_NOTES.md                               # Single Source of Truth del Changelog (sincronizzato con PATCH_NOTES.md root)
├── nk_tracking/                                     # Tracciamento, Telemetria, Memoria Episodica e Baseline Ratchet
│   ├── anchor/
│   │   └── session_anchor.jsonl                     # Registro Eventi (bonificato da righe vuote, duplicati e timestamp fuori ordine)
│   ├── cockpit/
│   │   └── nk_cockpit.html                          # Dashboard Visuale HTML
│   ├── episodic_memory/                             # Store JSONL a 3 Livelli per i 4 Domini (ARCH, SEC, OPS, DEVX)
│   ├── memory_3tier/
│   │   └── tier1_active_capsule.json                # [NUOVO v3.1] Capsula attiva Tier-1 per Pre-Warming < 2ms
│   ├── handoff/
│   │   └── next_session_prompt.md                   # Stato Handoff generato da scripts/nk_session_handoff.py
│   ├── manifests/                                   # Manifesti Operativi dell'Hub (rimosso il relitto legacy LabNK-Bandi)
│   ├── reports_and_briefs/                          # Report di Audit e Master Brief
│   │   ├── Brief_Unificato_NK_v3_STE100.md          # [v3.0] Brief Unificato in standard ASD-STE100
│   │   └── Super_Brief_Unificato_NK_v3_1_Tensor_RSI.md # [NUOVO v3.1] Super-Brief Tensor-RSI 2D
│   ├── quality_baseline.json                        # Ratchet di Non-Regressione (68 Golden Tests, 100.0% pass rate)
│   ├── rsi_telemetry.jsonl                          # [NUOVO v3.0] Ledger Crittografico SHA-256 delle iterazioni RSI
│   └── tuning/
│       └── session_tuning_params.json               # Telemetria Inning e Punteggio Reale di Conformità
│   # Cache AST esterna: %TEMP%\nk_diagnostics\repo_map_cache.json (scrittura atomica con nodi ed edges)
├── scripts/                                         # 30 Moduli Logici Core (33 File Python totali inclusi __init__.py e schemas/)
│   ├── __init__.py                                  # [01] Package Marker
│   ├── ast_guard_validator.py                       # [02] Validatore Statico AST (SASTConstructChecker, --stage-dir e --allowed-mutations)
│   ├── ast_repo_mapper.py                           # [03] AST Repo-Mapper PageRank (fix serializzazione edges e GT-06)
│   ├── async_heartbeat_signaler.py                  # [04] Demone Heartbeat e Watchdog 45s (fix timer last_beat_time U-22)
│   ├── auto_heal_pipeline.py                        # [05] Pipeline Fast-Healing collegata a rsi_convergence_engine.py
│   ├── dast_sandbox_runner.py                       # [06] Sandbox Runner Win32 Job Objects (fix ctypes 64-bit, command[2:] e CLI)
│   ├── deterministic_api_cache.py                   # [07] Cache SQLite WAL (fix connessione persistente BS-05)
│   ├── env_capability_probe.py                      # [08] Probe Ambiente (fix core vs optional preservando total_probed GT-09)
│   ├── external_project_scaffolder.py               # [09] Scaffolder Progetti Esterni (fix blocco path interno a NK-Hub BS-03)
│   ├── healing_snapshot_rollback.py                 # [10] Gestore Snapshot e Rollback SHA-256 (fix snapshot_manifest.json U-23)
│   ├── invisible_healing_loop.py                    # [11] Wrapper Compatibile collegato a auto_heal_pipeline.py e sbfl_engine.py
│   ├── memory_3tier_engine.py                       # [12] Motore Memoria 3-Tier (fix DOMAIN_ALIAS_MAP e cap 350/1200 GT-05)
│   ├── micro_hud_renderer.py                        # [13] Renderer Telemetrico UTF-8 allineato a MicroUIHUDState
│   ├── nk_active_runtime_sentinel.py                # [14] Sentinella Step Runtime (soglie default 60/85/100 GT-02 + profilo argon)
│   ├── nk_auto_inning.py                            # [15] Chiusura Inning (fix flag --transcript e lettura JSON reale U-14)
│   ├── nk_compliance_checker.py                     # [16] Verificatore Conformità (fix DDI 12 GT-03, path GT-08 e default 100 GT-10)
│   ├── nk_context_sentry.py                         # [17] Sentinella Contesto (default 70/100 GT-01, MTU 2000 GT-04, profilo argon)
│   ├── nk_registry_indexer.py                       # [18] Indicizzatore Modulare O(1) e Manifesto SSOT (DOM-01..DOM-05, [RULE-01.14])
│   ├── nk_session_bootstrap.py                      # [19] Session Bootstrap Gate <50ms (purge .wal, check src/, auto-profilo argon)
│   ├── nk_session_handoff.py                        # [19] Generatore Handoff (lettura dinamica quality_baseline.json U-49)
│   ├── nk_swarm_messenger.py                        # [20] Formattatore Messaggi Swarm (taglio MSS 1800 char GT-04 e UTF-8)
│   ├── oracle_evaluator_l3.py                       # [21] Valutatore DOM L3 (fix void tag HTML5, nodi misti e split path Windows)
│   ├── platform_runner.py                           # [22] Esecutore Sottoprocessi UTF-8 (fix iniezione -u su stringhe BS-04)
│   ├── preflight_health_check.py                    # [23] Diagnostica Manutenzione (fix falso positivo auto_fix BS-01 e --check-only)
│   ├── quality_baseline_manager.py                  # [24] Gestore Ratchet Baseline (fix fail-closed su errore I/O BS-02 e exit 1)
│   ├── rsi_convergence_engine.py                    # [25] Motore RSI Dual-Metric (Delta_k + Q(S_k), poc_confirmed_exploits, semantic_drift_findings)
│   ├── safe_cleanup_dev_servers.py                  # [26] Pulizia Dev Server (fix filtro psutil per CWD/cmdline U-13)
│   ├── sbfl_engine.py                               # [27] Motore Matematico SBFL Ochiai/Tarantula/DStar (<80 tok payload + CLI)
│   ├── sbfl_pytest_bridge.py                        # [28] Bridge Pytest SBFL (collegato a sbfl_engine.py e suspiciousness 1.0 GT-07)
│   ├── vibe_sprint_router.py                        # [29] Router Mode A/B/C/D (fix calcolo AST max_depth e soglia 150 LOC U-10)
│   ├── win32_2pc_engine.py                          # [30] Motore Commit Atomico 2PC (fix ctypes 64-bit, age > 10s e MOVEFILE_COPY_ALLOWED)
│   └── schemas/                                     # [31-33] Contratti Pydantic v2 e Dual Ledgers
│       ├── __init__.py                              # [31] Esportazione Schemi
│       ├── dual_ledgers.py                          # [32] TaskLedger e ProgressLedger (fix ctypes 64-bit e ERROR_ACCESS_DENIED U-25)
│       └── nk_ipc_contracts.py                      # [33] Contratti IPC Strict (IPCPointerReturn, GoalFailureManifest, RSISessionReport)
├── tests/                                           # Suite Consolidata Zero-Padding v3.4.0 (68 Golden Tests ortogonali, 100.0% PASS)
│   ├── __init__.py
│   ├── conftest.py                                  # Fixtures Pytest aggiornate a v3.4.0
│   ├── evals/
│   │   └── skill_golden_eval_set.json               # [NUOVO v3.1] Set di validazione L3 Meta-RSI per le 16 Skill
│   ├── test_active_sentinel_suite.py                # [Protetto da GT-02 e GT-04]
│   ├── test_ast_guard_validator.py                  # [Validazione AST, SASTConstructChecker e --allowed-mutations]
│   ├── test_ast_repo_mapper.py                      # [Protetto da GT-06]
│   ├── test_auto_heal_pipeline.py                   # [Protetto da GT-07]
│   ├── test_context_sentry.py                       # [Protetto da GT-01]
│   ├── test_dast_sandbox.py                         # [Validazione Shadow Sandbox e Referee PoC]
│   ├── test_memory_3tier.py                         # [Protetto da GT-05]
│   ├── test_platform_upgrades.py                    # [Protetto da GT-09]
│   ├── test_sbfl_engine.py                          # [Validazione SBFL Ochiai/Tarantula/DStar]
│   ├── test_schemas_and_contracts.py                # [Validazione contratti Pydantic v2 strict]
│   ├── test_super_brief_upgrades.py                 # [Protetto da GT-08 e GT-10]
│   ├── test_unified_onboarding_mandate.py           # [Protetto da GT-08]
│   ├── test_win32_2pc.py                            # [Validazione transazionale Win32 2PC]
│   ├── test_rsi_convergence_engine.py               # [Protetto da GT-11, GT-12 e canali TAS v4.0]
│   ├── test_preflight_health_check.py               # [Validazione --check-only e fail-closed]
│   ├── test_quality_baseline_manager.py             # [Protetto da GT-13 e Ratchet 68 Golden Tests]
│   ├── test_external_scaffolder.py                  # [Validazione isolamento progetti esterni]
│   ├── test_platform_runner.py                      # [Validazione sottoprocessi UTF-8 e tree-kill]
│   ├── test_deterministic_api_cache.py              # [Validazione SQLite WAL persistente]
│   ├── test_safe_cleanup_dev_servers.py             # [Validazione pulizia dev server per CWD]
│   ├── test_env_capability_probe.py                 # [Protetto da GT-09]
│   ├── test_vibe_sprint_router.py                   # [Validazione Mode A/B/C/D e AST depth]
│   ├── test_oracle_l3_and_hud.py                    # [Validazione DOM L3 void tag, nodi misti e HUD]
│   ├── test_nk_ecosystem_stress_opt5.py             # [Stress suite OPT-1..OPT-12]
│   └── stress/
│       ├── __init__.py
│       └── test_real_sandbox_stress.py              # [Protetto da GT-01 e GT-03]
├── README.md                                        # Documentazione Master EN (allineata a v3.4.0 e 68 Golden Tests)
├── README.it.md                                     # Documentazione Master IT (allineata 1:1 a README.md in ASD-STE100)
├── PATCH_NOTES.md                                   # Mirror Root del Changelog SSOT
├── GUIDA_INSTALLAZIONE.md                           # Guida Setup aggiornata a v3.0.0-STE100-Unified (68 Golden Tests pytest)
├── install.ps1                                      # Installer PowerShell aggiornato a v3.0.0-STE100-Unified
├── install.sh                                       # Installer Bash aggiornato a v3.0.0-STE100-Unified
├── requirements.txt                                 # Dipendenze Core (pydantic>=2.7.0,<3.0.0, psutil>=5.9.8,<8.0.0, pytest>=8.2.0,<10.0.0)
├── pytest.ini                                       # Configurazione Pytest (invariante protetto da test_platform_upgrades.py)
├── .gitignore                                       # Esclusioni Git (.staging/*, .wal/, scratch/*, nk_External_Projects/)
└── Antigravity.code-workspace                       # Configurazione Workspace IDE
```

---

## 2. Matrice Completa dei 30 Moduli Core in `scripts/` e dei 68 Golden Tests (`v3.4.0`)

| # | Modulo Core (`scripts/`) | Intervento Chirurgico in `v3.4.0` (`v3.1.0-Tensor-RSI`) | Guardia di Compatibilità | File di Test (`tests/`) |
| :---: | :--- | :--- | :---: | :--- |
| 1 | `ast_guard_validator.py` | Aggiunge `self.function_depth` (`U-20`), `--stage-dir`, `--allowed-mutations` e `SASTConstructChecker`. | Nessuna | `test_ast_guard_validator.py` |
| 2 | `ast_repo_mapper.py` | Salva e ricarica `edges` in `%TEMP%\nk_diagnostics\repo_map_cache.json`. Risolve archi cross-modulo e ordina PageRank per modulo (`U-21`). Esclude progetti esterni. | **`GT-06`** (`0/256/512/1024`) | `test_ast_repo_mapper.py` |
| 3 | `async_heartbeat_signaler.py` | Rimuove `self.last_beat_time = now` dal ramo `else:` di `_run_loop()` (`U-22`). Mappa i nomi dei thread in `dump_diagnostics()`. | Nessuna | `test_rsi_convergence_engine.py` |
| 4 | `auto_heal_pipeline.py` | Evita snapshot inutili dopo l'ultimo tentativo fallito. Integra il calcolo RSI in `AutoHealSessionReport`. | Nessuna | `test_auto_heal_pipeline.py` |
| 5 | `dast_sandbox_runner.py` | Dichiara `argtypes`/`restype` a 64-bit su `kernel32` (`U-24`). Controlla `INVALID_HANDLE_VALUE` e preserva `command[2:]`. Aggiunge CLI `__main__`. | Nessuna | `test_dast_sandbox.py` |
| 6 | `deterministic_api_cache.py` | Usa una connessione SQLite WAL persistente per istanza ed elimina `_get_connection()` morto (`BS-05`). | Nessuna | `test_deterministic_api_cache.py` |
| 7 | `env_capability_probe.py` | Chiama `reconfigure_streams()` e separa `core_hub_modules` da `optional_app_modules` (`BS-04`, `U-56`). | **`GT-09`** (`total_probed`) | `test_env_capability_probe.py` |
| 8 | `external_project_scaffolder.py` | Rifiuta qualsiasi `target_dir` interno a `NK-Hub` (`BS-03`). Crea la Tetralogia `nk_genome/` nel progetto esterno. | Nessuna | `test_external_scaffolder.py` |
| 9 | `healing_snapshot_rollback.py` | Persiste `snapshot_manifest.json` su disco in modo atomico per supportare `--rollback` e `--cleanup` (`U-23`). | Nessuna | `test_auto_heal_pipeline.py` |
| 10 | `invisible_healing_loop.py` | Delega l'esecuzione reale a `auto_heal_pipeline.py` e `sbfl_engine.py` eliminando la classe duplicata. | Nessuna | `test_schemas_and_contracts.py` |
| 11 | `memory_3tier_engine.py` | Aggiunge `DOMAIN_ALIAS_MAP` (`ARCH`, `SEC`, `OPS`, `DEVX` $\leftrightarrow$ `01_..04_`) (`U-46`). Supporta `TIER1_TOKEN_CAP_ARGON = 1200`. | **`GT-05`** (`350` tok default) | `test_memory_3tier.py` |
| 12 | `micro_hud_renderer.py` | Allinea `HUDState` con `MicroUIHUDState` e supporta la barra di convergenza RSI. | Nessuna | `test_oracle_l3_and_hud.py` |
| 13 | `nk_active_runtime_sentinel.py` | Preserva le soglie `60/85/100` nel profilo `standard` e aggiunge `--profile argon` (`120/180/250`). | **`GT-02`** (`60/85/100`) | `test_active_sentinel_suite.py` |
| 14 | `nk_auto_inning.py` | Passa `["--transcript", args.transcript, "--json"]` a `nk_compliance_checker.py` e legge il vero `composite_score` (`U-14`). | Nessuna | `test_active_sentinel_suite.py` |
| 15 | `nk_compliance_checker.py` | Filtra i sub-agenti in `find_active_transcript()`. Esclude `brain/`, `scratch/`, `nk_genome/`, `nk_tracking/`, `%TEMP%` da `code_write_calls`. | **`GT-03`**, **`GT-08`**, **`GT-10`** | `test_super_brief_upgrades.py` + `stress` |
| 16 | `nk_context_sentry.py` | Esclude `len(thinking)` in profilo `argon` (`150/250` step). Penalizza `send_message > 2000` solo sui ritorni dai sub-agenti (`U-02`). | **`GT-01`**, **`GT-04`** | `test_context_sentry.py` + `stress` |
| 17 | `nk_session_bootstrap.py` | Pulisce `.wal/*.wal`, controlla `src/` e file `.py` estranei su cache hit (`< 50 ms`) e imposta `NK_MODEL_PROFILE=argon`. | Nessuna | `test_unified_onboarding_mandate.py` |
| 18 | `nk_session_handoff.py` | Legge `unit_tests_total` da `quality_baseline.json` (`68` Golden Tests) e usa context manager UTF-8 (`U-49`). | Nessuna | `test_active_sentinel_suite.py` |
| 19 | `nk_swarm_messenger.py` | Mantiene il taglio a `1.800` char (MSS), include `sender`/`recipient` e chiama `reconfigure_streams()`. | **`GT-04`** (`< 1800` char) | `test_active_sentinel_suite.py` |
| 20 | `oracle_evaluator_l3.py` | Ignora i void tag HTML5 nello stack DOM, gestisce nodi misti e corregge lo split `:` sui path Windows (`U-27`). | Nessuna | `test_oracle_l3_and_hud.py` |
| 21 | `platform_runner.py` | Inietta il flag `-u` anche quando il comando Python è passato come stringa (`BS-04`). | Nessuna | `test_platform_runner.py` |
| 22 | `preflight_health_check.py` | Restituisce `FAIL` (`exit 1`) se restano errori dopo `auto_fix=True` (`BS-01`). Aggiunge `--check-only` e valida `session_anchor.jsonl`. | Nessuna | `test_preflight_health_check.py` |
| 23 | `quality_baseline_manager.py` | Fallisce in modo sicuro su JSON corrotto senza sovrascrivere il file (`BS-02`). Allinea il Ratchet a `68` Golden Tests (`v3.4.0`). | **`GT-13`** | `test_quality_baseline_manager.py` |
| 24 | `rsi_convergence_engine.py` | Calcola $\Delta_k$ e $Q(S_k)$ includendo `poc_confirmed_exploits` e `semantic_drift_findings`, applica `G1..G6` e `--verify`. | **`GT-11`**, **`GT-12`** | `test_rsi_convergence_engine.py` |
| 25 | `safe_cleanup_dev_servers.py` | Usa `psutil.net_connections()` e termina solo processi dev con `cwd()` o `cmdline()` nel workspace target (`U-13`). | Nessuna | `test_safe_cleanup_dev_servers.py` |
| 26 | `sbfl_engine.py` | Mantiene `OchiaiDiagnosticPayload.estimate_token_count() < 80` e aggiunge l'interfaccia CLI `__main__`. | Nessuna | `test_sbfl_engine.py` |
| 27 | `sbfl_pytest_bridge.py` | Collega `sbfl_engine.py`, supporta spazi nei path Windows e garantisce `loc.suspiciousness == 1.0` (`U-19`). | **`GT-07`** (`< 320` char) | `test_auto_heal_pipeline.py` |
| 28 | `vibe_sprint_router.py` | Calcola la vera profondità AST `max_depth`, supporta `Mode D` (`--prompt`) e allinea la soglia Mode C a `<= 150` LOC (`U-10`). | Nessuna | `test_vibe_sprint_router.py` |
| 29 | `win32_2pc_engine.py` | Dichiara `argtypes`/`restype` a 64-bit su `CreateMutexW`/`MoveFileExW`, usa `MOVEFILE_COPY_ALLOWED`, verifica `age > 10s` in `recover()`. | Nessuna | `test_win32_2pc.py` |
| 30 | `schemas/dual_ledgers.py` + `nk_ipc_contracts.py` | Dichiara `c_void_p` su `OpenProcess`/`CloseHandle` e tratta `ERROR_ACCESS_DENIED (5)` come processo vivo (`U-25`). Aggiunge `RSISessionReport`. | Nessuna | `test_schemas_and_contracts.py` |

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

# NEXUS KEYSTONE OFFICIAL CHANGELOG E PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v3.5.2-Global-Filter-61-Skills (Global Skill Isolation, Zero Context Overhead & 74 Golden Tests)`  
> **Milestone Anchor:** `NK-MS-20261017-GLOBAL-FILTER-v3.5.2` (`NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2`)  
> **Data Consolidamento:** `2026-10-17`  
> **Stato Release:** `[NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v3.5.2]`

---

## Release v3.5.2-Global-Filter-61-Skills: Isolamento Skill Globali Esterne, Zero Context Overhead e 74 Golden Tests (`2026-10-17`)
1. **Filtro Deterministico delle 61 Skill Globali (`scripts/nk_registry_indexer.py`)**:
   - `nk_registry_indexer.py` espone `--apply-global-filter` per isolare le `61` skill globali esterne in `4` plugin disabilitati.
   - Il filtro riduce le skill globali attive da `61` a `0` e azzera `28.170` byte di overhead (`7.042 -> 0` token/turno).
   - `nk_registry_indexer.py --verify` certifica l'isolamento delle skill globali e aggiorna il manifesto `O(1)`.
2. **Espansione della Suite Permanente a 74 Golden Tests (`tests/test_nk_registry_indexer.py`, `nk_tracking/quality_baseline.json`)**:
   - `test_nk_registry_indexer.py` verifica indice `O(1)`, integrità SHA-256, lookup `< 1 ms`, Hot-Swap e filtro delle `61` skill.
   - La suite Zero-Mock raggiunge `74/74 PASS` in `5.49s` mantenendo il Modularity Score a `100.0/100.0`.

| Area Funzionale | Prima (`v3.4.0`) | Dopo (`v3.5.2`) | Come Si Comporta Adesso |
| :--- | :---: | :---: | :--- |
| **Skill Globali Esterne (`~/.gemini`)** | `61` attive (`28.170` byte) | `0` attive (`61` isolate) | Risparmia `7.042` token ad ogni turno senza inquinare il contesto. |
| **Lookup e Indice Modulare (`DOM-01..05`)** | Scansione `O(N)` (`50.0/100`) | Indice `O(1)` (`100.0/100`) | Risolve dominio, skill primaria e flag CLI in `< 1 ms`. |
| **Registrazione Nuove Skill (Hot-Swap)** | `12+` file da riscrivere | `0` file esterni da toccare | `nk_registry_indexer.py --sync` rileva automaticamente YAML e AST. |
| **Suite Test Zero-Mock (`pytest`)** | `68/68 PASS` | `74/74 PASS` in `5.49s` | Protegge indice `O(1)`, Hot-Swap e isolamento globale al `100%`. |

---

## Release v3.5.0 / v3.5.1-RSI2: Indice Tassonomico Modulare O(1), 5 Domini DOM-01..DOM-05 e Disaccoppiamento SSOT (`2026-10-17`)
1. **Regola Costituzionale `[RULE-01.14]` e Indice Tassonomico O(1) (`nk_genome/nk_registry_manifest.json`, `nk_genome/SKILL_INDEX.md`)**:
   - `.agents/AGENTS.md` introduce `[RULE-01.14]` per la risoluzione O(1) delle skill tramite il manifesto JSON e l'indice Markdown.
   - La tassonomia suddivide `16` skill e `30` script nei `5` domini funzionali `DOM-01..DOM-05`.
   - I frontmatter YAML delle `16` skill integrano i campi `domain_id` e `sector` per l'indicizzazione deterministica.
2. **Motore di Indicizzazione AST e Verifica Crittografica (`scripts/nk_registry_indexer.py`)**:
   - `nk_registry_indexer.py` scansiona le cartelle delle skill e gli AST degli script calcolando gli hash SHA-256.
   - Il modulo espone i flag CLI `--sync`, `--verify`, `--lookup`, `--stage-dir`, `--root` e `--json`.
   - Il comando `--sync` rigenera `nk_registry_manifest.json` e `SKILL_INDEX.md` senza richiedere riscritture manuali.
3. **Disaccoppiamento SSOT di Diagnostica e Router (`scripts/preflight_health_check.py`, `scripts/vibe_sprint_router.py`)**:
   - `preflight_health_check.py` legge l'elenco canonico delle skill direttamente da `nk_registry_manifest.json` eliminando le tuple hardcoded.
   - `vibe_sprint_router.py` risolve il dominio target e la skill primaria in tempo O(1) interrogando il manifesto.
4. **Compatibilità Dual-Schema degli Hook di Ciclo di Vita (`.agents/hooks.json`, `NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2`)**:
   - `.agents/hooks.json` adotta la modalità `DUAL_COMPATIBLE_NATIVE_AND_NK` per supportare sia il runtime nativo sia gli script dell'Hub.
   - Ogni voce definisce `SessionStart`, `PostToolUse` e `Stop` sia in `hooks` sia nella root con `timeout` e `timeout_ms`.

---

## Release v3.4.0-TAS-v4-NeuroSym: Rifondazione Neuro-Simbolica TAS v4.0 (1A + 2C + 3B) (`2026-10-17`)
1. **Tassonomia Modulare SAST e DAST (`NK-Security-Auditor/resources/`, `NK-Security-Auditor/SKILL.md`)**:
   - La skill separa la conoscenza di sicurezza in `4` matrici modulari caricate on demand per stack tecnologico.
   - I nuovi moduli coprono Python, Web, Mobile, AI LLM, IoT, Cloud IaC e protocolli crittografici PQC.
2. **Estensione SAST Deterministica e Controllo Mutazioni (`scripts/ast_guard_validator.py`, `scripts/sbfl_pytest_bridge.py`)**:
   - `ast_guard_validator.py` rileva sink SQL, comandi shell, deserializzazione insicura, XXE, SSRF e template injection.
   - Il flag `--allowed-mutations` blocca le modifiche alle funzioni non elencate nella whitelist di remediation.
   - `sbfl_pytest_bridge.py` delega il calcolo Ochiai a `sbfl_engine.py` con fallback deterministico sulle tracce di stack.
3. **Oracolo DOM L3, Sandbox DAST Win32 e Canali Tensor-RSI (`scripts/oracle_evaluator_l3.py`, `scripts/dast_sandbox_runner.py`, `scripts/rsi_convergence_engine.py`)**:
   - `oracle_evaluator_l3.py` ispeziona attributi ARIA, ruoli semantici e vincoli geometrici su liste DOM eterogenee.
   - `dast_sandbox_runner.py` applica limiti di memoria con Win32 Job Object e inietta `PYTHONPATH` nella sandbox.
   - `rsi_convergence_engine.py` integra `poc_confirmed_exploits` e `semantic_drift_findings` nel calcolo del residuo `Delta_k`.
4. **Bonifica Ciclo 2 RSI per PoC e Drift Semantici (`NK-MS-20261017-TAS-V4-RSI-CYCLE2`)**:
   - `ast_guard_validator.py` e `safe_cleanup_dev_servers.py` sanificano le mutazioni AST fuori funzione e la pulizia dei processi.
   - `dast_sandbox_runner.py`, `oracle_evaluator_l3.py` e `sbfl_pytest_bridge.py` risolvono `POC-01..04` su timeout, metriche DOM e trace.
   - `nk_ipc_contracts.py`, `structural_tree.md` e `concept_map.md` risolvono `DRIFT-01..02` allineando gli schemi IPC e la mappa.

---

## Release v3.3.0-GT68-Pareto: Riforma Costituzionale GT-68 Zero-Padding, Suite Ortogonale in 5 Secondi e OPT-1..OPT-12
1. **Riforma Costituzionale `[RULE-01.10]` e Baseline Ratchet (`scripts/quality_baseline_manager.py`, `nk_tracking/quality_baseline.json`)**:
   - `.agents/AGENTS.md` e `NK-Oracle-Evaluator/SKILL.md` ricalibrano il pavimento costituzionale a `68` Golden Tests ortogonali (`>= 60` Core Tests).
   - `quality_baseline_manager.py` fissa `CONSTITUTIONAL_MIN_TESTS = 60` e allinea `quality_baseline.json` a `68` Golden Tests (`100.0% PASS`).
2. **Consolidamento Pareto Zero-Padding della Suite di Test (`tests/`, `68/68 PASS` in `~5 s`)**:
   - La bonifica rimuove `55` test ridondanti di padding preservando il `100%` di copertura sui `30` moduli core.
   - Le suite unificano i sottoprocessi tramite fixture `scope="module"` riducendo il tempo da `42 s` a `5 s`.

---

## Release v3.2.0-OPT11-Stress-Hardened: Ottimizzazioni Forensi OPT-1..OPT-12, Mode D Discovery e 123 Golden Tests
1. **Accelerazione Bootstrap Sotto 50 ms e Cache Atomica (`OPT-1`, `OPT-8`, `scripts/nk_session_bootstrap.py`)**:
   - `_check_root_hygiene()` memorizza `root_mtime` nella cache per evitare scansioni ripetute su disco.
   - `_verify_context_sentry()` legge gli ultimi byte del transcript per ridurre la latenza sotto `50 ms`.
   - `run_bootstrap()` carica la cache una sola volta e salva lo stato tramite `os.replace` atomico.
2. **Isolamento Progetti Esterni e Concorrenza Telemetrica RSI (`OPT-2`, `OPT-9`, `scripts/rsi_convergence_engine.py`)**:
   - `main()` propaga il flag `--profile` verso `verify_ecosystem()` e `run_convergence_loop()`.
   - Il motore esclude i file Markdown privi di marker NK nelle cartelle esterne e ignora `.venv`.
   - Il flag `--benchmark-suite` integra il pass rate dei benchmark nel calcolo di `Delta_k`.
   - `append_telemetry_record()` usa un lock multi-thread e multi-processo per proteggere `rsi_telemetry.jsonl`.
3. **Mode D Discovery, Governanza Skill e Shell (`OPT-3`, `OPT-4`, `OPT-5`, `scripts/vibe_sprint_router.py`)**:
   - `vibe_sprint_router.py` classifica i prompt analitici e di benchmark in `Mode D` (`read_only: true`).
   - `NK-Ideator` abilita `call_mcp_tool` per interrogare connettori MCP in sola lettura.
   - `NK-Session-Controller` impone i nomi canonici delle skill in `define_subagent` e l'isolamento in `.staging/`.
   - `.agents/AGENTS.md` vieta i comandi `python -c` multi-riga su PowerShell a favore di script dedicati.
4. **Hardening Compliance, Context Sentry, Preflight e IPC (`OPT-6`, `OPT-7`, `OPT-10`, `OPT-11`, `OPT-12`)**:
   - `nk_compliance_checker.py` rileva exit code non nulli nei blocchi `GENERIC` e conta ogni tool diretto per il DDI.
   - `nk_compliance_checker.py` esenta i passi `REFINING` convergenti e riconosce `ast_guard_validator.py` delegato (`OPT-12`).
   - `nk_context_sentry.py` traccia separatamente la soglia `SWARM_MSG_MSS_CAP = 1800` e il tetto `SWARM_MSG_HARD_CAP = 2000`.
   - `preflight_health_check.py` unifica la scansione `os.walk` potando `.venv`, `.git` e `node_modules`.
   - `healing_snapshot_rollback.py` scrive `snapshot_manifest.json` in modo atomico e `nk_ipc_contracts.py` supporta `mode_d`.
5. **Stress Evaluation Suite e Ratchet Permanente a 123 Golden Tests (`tests/test_nk_ecosystem_stress_opt5.py`)**:
   - La nuova suite verifica concorrenza a `16` thread, latenza `< 50 ms`, lock telemetrico e guardie `GT-01..GT-14`.
   - La suite permanente sale da `108` a **123 Golden Tests Zero-Mock** con il `100.0%` di successo.

---

## Release v3.1.0-Tensor-RSI: Architettura Tensor-RSI 2D, Capsule Pre-Warming, CoVe CLI AST e 108 Golden Tests
1. **Architettura Tensor-RSI 2D (`[RULE-RSI.1]` e `RSIProfileRegistry`)**:
   - Il motore `rsi_convergence_engine.py` combina `4` livelli operativi (`L0..L3`) con `5` profili specializzati (`P1..P5`).
   - Il flag `--vibe-check <target>` esegue la verifica rapida di `Mode C` in meno di `500 ms`.
   - Il CoVe CLI AST Gate controlla che ogni flag CLI nei `SKILL.md` esista in `scripts/*.py`.
   - `verify_ste100_compliance()` impone `max_sentence_words = 20` e salta il frontmatter YAML `---` (`GT-12`).
2. **Capsule Pre-Warming e Memoria 3-Tier (`scripts/memory_3tier_engine.py`, `scripts/vibe_sprint_router.py`)**:
   - `memory_3tier_engine.py` importa `win32_atomic_replace` da `win32_2pc_engine.py` ed espone la CLI `__main__`.
   - Il sistema persiste `nk_tracking/memory_3tier/tier1_active_capsule.json` ed esegue il recall RRF adattivo.
   - `vibe_sprint_router.py` inietta le lezioni attive nel prompt Template 8A in meno di `2 ms`.
3. **Bonifica dei 14 Script Core e Guardie `GT-11..GT-14`**:
   - `ast_guard_validator.py` supporta `--stage-dir` e rileva `eval()`, `exec()`, `pickle.loads()`, `yaml.load()` e `MagicMock`.
   - `quality_baseline_manager.py` aggiunge `sast_critical_violations` e `rsi_residual_delta` a `LOWER_IS_BETTER_KEYS` e supporta `argparse` (`GT-13`).
   - `auto_heal_pipeline.py` collega `run_pipeline()` a `RSIConvergenceEngine.run_convergence_loop()` ed elimina lo snapshot ridondante.
   - `nk_compliance_checker.py` esenta le sessioni `write_calls == 0` dalla penalità AST e legge `rsi_telemetry.jsonl` (`GT-10`).
4. **Allineamento delle 16 Skill, Tetralogia 4/4 e 108 Golden Tests**:
   - Tutte le 16 skill includono `<rsi_micro_loop>`, permessi `GT-14` verificati e `tests/evals/skill_golden_eval_set.json`.
   - `nk_genome/` include il nuovo `idea_canvas.md` e `repo_map.md` rigenerata a `4.000` token Argon.
   - La suite permanente sale da `100` a **108 Golden Tests Zero-Mock** con il `100.0%` di successo.

---

## Release v3.0.0-STE100-Unified: Standard ASD-STE100, Motore RSI Continuo, Simbiosi Argon e 100 Golden Tests
1. **Standard Linguistico Obbligatorio `[RULE-STE100]` (`ASD_STE100_TECHNICAL_ITALIAN_MANDATE`)**:
   - L'intero ecosistema adotta l'italiano tecnico ASD-STE100 con frasi di massimo `20` parole e forma attiva.
   - Il peso di `.agents/AGENTS.md` e `.agents/rules/anti_crash_rules.md` scende da `22.084` byte a meno di `10.500` byte (`-53%`).
   - Il sistema elimina gli incisi con trattini e le ripetizioni enfatiche che causavano appiattimento dell'attenzione.
2. **Motore Matematico di Convergenza RSI (`scripts/rsi_convergence_engine.py` e `[RULE-RSI]`)**:
   - Il 30° modulo core implementa i modelli Pydantic v2 `RSIDefectVector`, `RSIIterationRecord` e `RSISessionReport`.
   - Il motore calcola la metrica lineare $\Delta_k$ e la fitness iperbolica $Q(S_k) \in [0, 100]$.
   - Le 6 guardie `G1..G6` impongono lo stop a $\Delta_k == 0$ e $Q(S_k) == 100.0$, il rollback monotono, l'anti-oscillazione SHA-256, la catena hash in `nk_tracking/rsi_telemetry.jsonl` e il validatore `--verify`.
3. **Architettura Dual-Profile (`standard` vs `argon`) e Guardie `GT-01..GT-10`**:
   - Le firme predefinite preservano le soglie `standard` (`70/100` step, `350` token Tier-1, `0/256/512/1024` token Repo-Map) per proteggere i 100 Golden Tests.
   - Lo script `scripts/nk_session_bootstrap.py` imposta automaticamente `NK_MODEL_PROFILE=argon` nelle sessioni operative.
   - Il profilo `argon` esclude `len(thinking)` e attiva le soglie `150/250` step (`250k/500k` token).
4. **Topologia 2-Tier a Singolo Livello, Holistic Fast-Track e Swarm Hygiene**:
   - L'Agente Principale registra i worker con `define_subagent(enable_subagent_tools=False)` ed elimina il deadlock di doppia delega.
   - Il limite `DDI_DIRECT_STREAK_LIMIT` sale a `12` chiamate dirette consecutive (`GT-03`).
   - `nk_context_sentry.py` applica la penalità sui messaggi `> 2000` caratteri solo ai ritorni dai sub-agenti (`U-02`, `GT-04`).
   - Ogni sub-agente salva i report nella propria cartella `brain/<subagent-id>/scratch/` (`U-06`).
5. **Riparazione Chirurgica dei 29 Moduli Core in `scripts/`**:
   - `win32_2pc_engine.py`, `dast_sandbox_runner.py` e `schemas/dual_ledgers.py` dichiarano `argtypes`/`restype` a 64-bit (`c_void_p`) su `kernel32` e gestiscono `ERROR_ACCESS_DENIED (5)`.
   - `deterministic_api_cache.py` mantiene una connessione SQLite WAL persistente per istanza (`BS-05`).
   - `preflight_health_check.py` e `quality_baseline_manager.py` operano in modalità fail-closed su JSON corrotto (`BS-01`, `BS-02`) e supportano `--check-only`.
   - `ast_guard_validator.py` traccia `function_depth` (`U-20`) e `ast_repo_mapper.py` serializza `edges` nella cache (`U-21`).
   - `sbfl_pytest_bridge.py` supporta gli spazi nei path Windows e garantisce `suspiciousness == 1.0` (`GT-07`).
   - `external_project_scaffolder.py` rifiuta qualsiasi percorso target interno a `NK-Hub` (`BS-03`).
   - `platform_runner.py` inietta il flag `-u` anche sui comandi passati come stringa (`BS-04`).
   - `safe_cleanup_dev_servers.py` filtra i processi `psutil` per CWD e cmdline del workspace (`U-13`).
   - `oracle_evaluator_l3.py` ignora i void tag HTML5 e gestisce i path Windows con lettera di unità (`U-27`).
6. **Modernizzazione delle 16 Skill e Pulizia di 39 File Ausiliari (`51 -> 13 File`)**:
   - Tutte le 16 `SKILL.md` adottano la versione `v3.0.0-STE100-Unified`, la Tetralogia Sovrana 4/4 e i 9 comandi slash nativi.
   - Il sistema rimuove 39 file ausiliari orfani, duplicati o contenenti mock e fixer non autorizzati (`C-06`).
   - Tutte le skill linkano esplicitamente i 13 file ausiliari validi (incluso il nuovo `audit_checklists_l1_l2_l3.md`).
7. **Isolamento Progetti Esterni e Ratchet Permanente a 100 Golden Tests**:
   - Il manifesto di bonifica isola le 3 cartelle di progetti esterni in `G:/Il mio Drive/NK_External_Projects/` e rimuove le 4 cartelle relitto.
   - La suite permanente cresce da 79 a **100 Golden Tests Zero-Mock** (`+21` nuovi test in 10 file `tests/test_*.py`) con il `100.0%` di successo.

---

## Release v2.6.1-Controller-Hotfix: Chiusura Risorse SQLite, Snapshot Anti-Collisione e 79 Golden Tests
1. **Chiusura Risorse SQLite (`scripts/deterministic_api_cache.py`)**:
   - Introduce la gestione transazionale atomica per prevenire `ResourceWarning` e lock `[WinError 32]` su Windows.
2. **Snapshot su Disco Anti-Collisione (`scripts/healing_snapshot_rollback.py`)**:
   - Assegna un prefisso SHA-256 a 8 caratteri ai file di backup per evitare collisioni tra file omonimi.
3. **Filtro Task in Background (`scripts/nk_context_sentry.py`)**:
   - Aggiunge `is_background_task_message()` per escludere gli stdout dei task asincroni dal calcolo MTU dei messaggi inter-agente.
4. **Allineamento Ratchet a 79 Golden Tests**:
   - Sincronizza `.agents/AGENTS.md` e `nk_genome/` con i 79 Golden Tests al `100.0%` di successo.

---

## Release v2.6.0-DualEngine-Symbiosis: Integrazione Plan e Goal, 4 Scudi Avversariali e Fast-Healing
1. **Dual-Mirroring Artifact Bridge (`/plan` e `[RULE-01.11]`)**:
   - Sincronizza `nk_genome/implementation_plan.md` con l'artefatto nativo Antigravity dotato di `RequestFeedback: true`.
2. **Autonomous Goal Drive (`/goal` e `[RULE-01.12]`)**:
   - Integra i 4 scudi avversariali `C1` (Target Resolution), `C2` (Context Sentry), `C3` (`Goal_Failure_Manifest.json`) e `C4` (2PC Safety Gate).
3. **Tre Pilastri del Fast-Healing Zero-Mock**:
   - Consolida `auto_heal_pipeline.py`, `sbfl_pytest_bridge.py` (`< 80` token) e `healing_snapshot_rollback.py`.
4. **Bonifica Dead Code e 79 Golden Tests**:
   - Rimuove gli import e le variabili inutilizzate su 28 file ed eleva la suite permanente a 79 Golden Tests.

---

## Release v2.5.2-Hardened: Mandato Dashboard di Onboarding Unificata e Oracolo L3
1. **Mandato `[RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE`**:
   - Codifica gli 8 trigger verbali di avvio, il controllo Fast-Stat `< 120` ms e la Master Dashboard a 15 nodi (`[0]`..`[14]`).
2. **Suite di Test `tests/test_unified_onboarding_mandate.py`**:
   - Verifica la presenza di `[RULE-00.5]`, dei 15 nodi Hub, del vincolo 10 nel Controller e l'esecuzione del bootstrap.
3. **Hardening CP1252 e Oracolo L3 (`scripts/micro_hud_renderer.py`, `scripts/oracle_evaluator_l3.py`)**:
   - Aggiunge il fallback ASCII per console Windows CP1252 e integra il valutatore DOM L3 puro Python.

---

## Release v2.5.1-Hardened: Accelerazione Bootstrap `< 50` ms e 74 Golden Tests
1. **Accelerazione Session Bootstrap Gate (`scripts/nk_session_bootstrap.py`)**:
   - Riduce il tempo di bootstrap a `42-55` ms restringendo la pulizia dei file `.wal` alle cartelle candidate.
2. **Armonizzazione Skill e Ratchet a 74 Golden Tests**:
   - Rimuove i riferimenti residui a `src_app/*` nelle skill e consolida i 74 test permanenti Zero-Mock.

---

## Release v2.5.0: Onboarding Deterministico e Guida Swarm a Due Vie
1. **Introduzione di `[RULE-00.5]` e Guida a Due Vie**:
   - Definisce il flusso di avvio rapido e la doppia modalità d'uso (`Modalità Diretta` e `Modalità Goal-Driven`).

---

## Release v2.4.2-PanoramicMastery: Ripristino Catalogo 16 Skill e Parità Documentale
1. **Catalogo Completo delle 16 Skill e Parità EN/IT**:
   - Documenta tutte le 16 skill vocazionali, i moduli `scripts/` e le formule matematiche in `README.md` e `README.it.md`.

---

## Release v2.4.1 e v2.4.0-ActiveSentinel: Sentinella Runtime, Handoff e Swarm Messenger
1. **Difesa Attiva Runtime (`nk_active_runtime_sentinel.py`, `nk_session_handoff.py`, `nk_swarm_messenger.py`, `nk_auto_inning.py`)**:
   - Introduce il monitoraggio degli step, il generatore di handoff, il taglio MSS a `1.800` caratteri e la chiusura automatica dell'inning.

---

## Release v2.2.0-AntiSaturation, v2.1.0-FastHealing e v2.0.0-Hardened
1. **Prevenzione Saturazione e Fast-Healing (`nk_context_sentry.py`, `auto_heal_pipeline.py`, `platform_runner.py`)**:
   - Introduce `Universal DDI`, `Context Sentry`, la pipeline di auto-riparazione a 3 pilastri, lo scaffolder esterno e la cache API SQLite WAL.

---

## Release v1.9.1, v1.9.0, v1.7.2, v1.7.1, v1.7.0 e v1.6.0
1. **Isolamento Progetti Esterni, AST Repo-Map e Fondamenta CRV 4.0**:
   - Istituisce `[RULE-PROJECT-ISOLATION]`, `env_capability_probe.py`, `ast_repo_mapper.py` (Tetralogia Sovrana), `async_heartbeat_signaler.py`, `vibe_sprint_router.py`, `win32_2pc_engine.py` e `memory_3tier_engine.py`.

# NEXUS KEYSTONE OFFICIAL CHANGELOG E PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v3.1.0-Tensor-RSI (Tensor-RSI 2D Architecture, RSIProfileRegistry, Capsule Pre-Warming, CoVe CLI AST Gate & 108 Golden Tests Ratchet)`  
> **Milestone Anchor:** `NK-MS-20261015-TENSOR-RSI-v3.1.0`  
> **Data Consolidamento:** `2026-10-15`  
> **Stato Release:** `[NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v3.1.0-Tensor-RSI]`

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

# 📜 NEXUS KEYSTONE OFFICIAL CHANGELOG & PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v2.4.2-PanoramicMastery (Full 16-Skill Catalog, Core Engines, Mathematical Rigor & 10/10 EN/IT Documentation Parity)`  
> **Milestone Anchor:** `NK-MS-20260916-PANORAMIC-DOCS-v2.4.2`  
> **Data Consolidamento:** 2026-09-16  
> **Stato Release:** `🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v2.4.2 🟢]`

---

## 🏛️ Release v2.4.2 — Panoramic Mastery & Full Vocational Skills Restoration
La Release **v2.4.2** espande e armonizza la documentazione del repository unendo sintesi rapida e profondità tecnica esaustiva:
1. **Ripristino Integrale del Catalogo Panoramico delle 16 Skill**:
   - Mappatura completa e dettagliata di tutte le 16 skill agentiche (`.agents/skills/*`), suddivise nei 5 tier funzionali (Ideazione/UX, Governance, Builder, Diagnostica/Oracolo, Sicurezza/Memoria), con ruoli, livelli (L0-L3), vincoli operativi e I/O contract.
2. **Architettura Core & Directory Script Esaustiva**:
   - Censimento e documentazione di tutti gli script del framework (`scripts/*.py`) raggruppati per domini (Runtime Defense, Swarm IPC, 2PC Named Mutex, SBFL Ochiai Auto-Healing, Memory 3-Tier, AST Scaffolding).
3. **Formalizzazione Matematica & Rigore Tecnico per Esperti**:
   - Equazioni formali KaTeX per SBFL Ochiai e Reciprocal Rank Fusion (BM25 + Cosine $k=60$).
   - Specifiche algoritmiche per Kahn DAG Topological Sorting, Win32 2PC Named Mutex e EGPWS Active Sentinel FSM.
   - Tabella rigida degli SLA di latenza di sistema.
4. **Onboarding Istantaneo & Flusso Visuale per Principianti (10/10)**:
   - Concetto intuitivo "Torre di Controllo per Agenti AI", Quickstart in 3 comandi e diagramma visuale Mermaid.
5. **Parità Speculare 1:1 Assoluta EN/IT**:
   - Perfetta corrispondenza capitolo per capitolo tra `README.md` e `README.it.md`.
6. **Ratchet Permanente Verificato a 74 Golden Tests (100.0% PASS)**.

---

## 🏛️ Release v2.4.1 — TAS Audit, Sandbox Stress con Auto-Healing & Allineamento GitHub 10/10
La Release **v2.4.1** consolida la difesa attiva a runtime contro l'errore 503 e raggiunge la parità documentale 10/10:
1. **Active Runtime Sentinel (`scripts/nk_active_runtime_sentinel.py`)**:
   - Watchdog EGPWS in streaming (<25 ms) con debouncing a stati discreti: GREEN (<60), CAUTION (60-84), CRITICAL (85-99 con Soft Lock), RED (≥100 con Hard Freeze Exit Code 1).
2. **Deterministic Session Handoff Engine (`scripts/nk_session_handoff.py`)**:
   - Zero-Amnesia Capsule (<800 token) e Stash Guard con snapshot `.patch` anti-data-loss.
   - Generazione prompt turnkey `next_session_prompt.md`.
3. **Swarm Hygiene Physical MTU Gate (`scripts/nk_swarm_messenger.py`)**:
   - Hard-Gate 1.800 car., disk spillover su `%TEMP%\nk_diagnostics\` e compressione Head-Tail (<1.200 car.).
4. **Continuous Auto-Inning & Monotonic Ratchet (`scripts/nk_auto_inning.py`)**:
   - Chiusura formale dell'inning, compliance audit con penalità bloccanti per sessioni RED/DDI bypass, e ratchet monotono.
5. **Collaudo TAS e Stress Test in Shadow Sandbox con Auto-Healing**:
   - Simulazione di saturazione contesto ed EGPWS su progetto target in `%TEMP%`.
   - Bug injection (`ZeroDivisionError`), localizzazione Ochiai SBFL (`sbfl_engine.py`) e auto-patching (`auto_heal_pipeline.py`) verificati al 100% PASS.
6. **Armonizzazione Integrale GitHub (10/10 Parity)**:
   - Allineamento speculare 1:1 tra `README.md` (EN) e `README.it.md` (IT).
   - Valutazione doppia 10/10 certificata per Non-Esperti (Torre di Controllo, Quickstart) ed Esperti (formule Ochiai, RRF $k=60$, Kahn DAG, 2PC, EGPWS, 70 Golden Tests).

---

## 🏛️ Release v2.2.0-AntiSaturation — Universal DDI, Swarm Message Hygiene, Cold Review Isolation & Context Sentry
La Release **v2.2.0-AntiSaturation** risolve alla radice le cause sistemiche di saturazione del contesto e previene i drop di capacità backend `UNAVAILABLE (code 503): No capacity available for model on server` (mascherati a video come *"Error your servers are experiencing high traffic right now"*):
1. **Universal DDI Mandate ([RULE-01] in `AGENTS.md`)**:
   - Estensione della delega obbligatoria a sub-agenti sia per la scrittura codice sia per qualsiasi **Deep Audit o Stress-Testing** (>2 file o comandi di test).
   - Preservata la modalità Fast-Track per micro-check rapidi (≤150 LOC, ≤2 file/comandi).
2. **Swarm Message Hygiene Mandate ([RULE-SWARM-HYGIENE] in `AGENTS.md`)**:
   - Hard cap tassativo a **2.000 caratteri** per i messaggi inter-agente (`send_message`).
   - Obbligo di salvataggio artefatto diagnostico completo su disco (`%TEMP%\nk_diagnostics\` o `scratch/`) e trasmissione della sola sintesi esecutiva con path file.
   - Fallback automatico in-band *Head-Tail* (400 chars contesto + 800 chars traceback con `__cause__`) in caso di eccezioni I/O.
3. **Isolated Cold Review Protocol (`NK-Session-Controller/SKILL.md`)**:
   - Macro-Fase 3 delegata mandatoriamente a sub-agente oracolo isolato in sandbox (`NK-Oracle-Evaluator` o `CriticAuditWorker`), azzerando il carico di letture e comandi nel thread principale.
4. **Context Sentry Guard (`scripts/nk_context_sentry.py`)**:
   - Motore deterministico ad alte prestazioni (<50 ms) con semaforo a 3 livelli: 🟢 GREEN (<70 step), 🟡 YELLOW (70-99 step), 🔴 RED (≥100 step con trigger rollover).
   - Integrato nel Session Bootstrap Gate (`scripts/nk_session_bootstrap.py`) e nel Compliance Checker (`scripts/nk_compliance_checker.py`).
5. **Ratchet Elevato a 66 Golden Tests (100.0% PASS)**:
   - Integrazione della test suite `tests/test_context_sentry.py` (5 test Zero-Mock) portando la baseline permanente a **66/66 test passati in 29.32s**.

---

## 🏛️ Release v2.1.0-FastHealing — 3-Pillar Fast-Healing Pipeline, AST Scope Hardening & 61 Golden Tests
La Release **v2.1.0-FastHealing** introduce l'architettura di riparazione autonoma di nuova generazione e razionalizza la suite di validazione permanente della piattaforma a 61 Golden Tests ad altissima densità:
1. **Universal CLI Auto-Healer Pipeline (`scripts/auto_heal_pipeline.py`)**:
   - Orchestratore universale di auto-riparazione azionabile via CLI con circuit breaker a 3 cicli.
   - Piena conformità a `[RULE-PROJECT-ISOLATION]`: emissione di riga singola per `PATCH_NOTES.md` nel progetto target, con zero inquinamento di memoria o depositi globali promiscui.
2. **Pytest Coverage & SBFL Ochiai Bridge (`scripts/sbfl_pytest_bridge.py`)**:
   - Estrazione deterministica dei frame di fallimento da traceback Pytest ed esecuzione algoritmica di Ochiai su codice reale.
   - Generazione di `OchiaiDiagnosticPayload` ultra-compatto vincolato a `< 80 token` BPE per prevenire token bloat nei prompt LLM.
3. **Staging Snapshot & Transactional Rollback Engine (`scripts/healing_snapshot_rollback.py`)**:
   - Snapshot atomici con hashing SHA-256 e Strict Monotonic Fitness Gate a 4 rami decisionali.
   - Ripristino deterministico atomico su disco in caso di regressione o peggioramento delle metriche di test.
4. **Hardening dello Scope Integrato in AST Guard (`scripts/ast_guard_validator.py`)**:
   - Risolto bug silente: `ScopeIntegrityChecker` ora visita esplicitamente `decorator_list`, default arguments posizionali e keyword arguments nell'enclosing scope prima dell'ingresso nel corpo di funzioni e classi.
   - Supporto completo per default attributes a livello di classe.
5. **Razionalizzazione della Suite Permanente (61 Golden Tests / 100.0% PASS)**:
   - Sostituiti 4 test deboli/in-memory obsoleti (`test_invisible_healing_loop.py`) con i 6 test reali Zero-Mock di `test_auto_heal_pipeline.py`.
   - Eliminate 6 duplicazioni cross-file, compattato lo Slicer Karpathy con test parametrizzati e risolto collo di bottiglia I/O (-93% tempo in `test_memory_3tier.py`).
   - Ratchet di conformità calibrato esattamente su **61/61 test con il 100.0% di PASS**.

---

## 🏛️ Release v2.0.0-Hardened — Super Brief Sistemico, Anti-Polling Watchdog & 66-Test Permanent Suite
La Release **v2.0.0-Hardened** concretizza l'intera sintesi dialettica tra l'analisi empirica e l'audit procedurale dello stress test, trasferendo la governance dai meri soft-constraint di prompt a **Hard Tool Guardrails ed enforcement deterministico**:
1. **Universal Safe Subprocess Runner v2 (`scripts/platform_runner.py`)**:
   - Auto-iniezione forzata di `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8` e `PYTHONUTF8=1` in ogni processo.
   - Auto-flag `-u` sistematico su tutte le invocazioni Python, eliminando i falsi allarmi da buffer vuoto e i file log a 0 byte su Windows.
   - Quoting deterministico ed esecuzione vettorizzata senza `shell=True` per percorsi con spazi (`G:\Il mio Drive\`).
2. **Fast-Stat Session Bootstrap Gate (`scripts/nk_session_bootstrap.py`)**:
   - Primo step obbligatorio di ogni sessione (`[RULE-00.4]`).
   - Verifica invariante ultra-rapida ($< 120$ ms) con cache di stato in `%TEMP%\nk_bootstrap\`, purge dei WAL scaduti (>60s) e validazione di `[RULE-PROJECT-ISOLATION]`.
3. **Watchdog Anti-Polling & Protocollo `[RULE-REACTIVE-SILENCE]`**:
   - Nuova regola costituzionale in `AGENTS.md` che vieta il busy polling su `status` (massimo 1 interrogazione) e impone il silenzio reattivo con sentinella condizionale `schedule(TimerCondition="task-xxx")`.
4. **Deterministic External Project Scaffolder (`scripts/external_project_scaffolder.py`)**:
   - Utility atomica CLI che genera in 1 secondo l'alberatura DDD di progetti esterni fuori da NK-Hub con configurazioni unbuffered e test AST pre-integrati.
5. **Tier-0 Deterministic Local API Cache (`scripts/deterministic_api_cache.py`)**:
   - Cache SQLite WAL in `%TEMP%` che accelera le test suite locali da 101s a $< 4$s e supporta `--force-refresh` in CI per la conformità Zero-Mock al 100%.
6. **Hard Compliance Checker (`scripts/nk_compliance_checker.py`) & Suite Ratchet a 66 Test**:
   - Analizzatore forense post-sessione e in CI che calcola la Doppia Scorecard (Operativo + Procedurale).
   - Test suite permanente espansa a **66/66 test PASSED (100.0%)**.

---

## 🏛️ Release v1.9.1-ForensicClean — Bonifica Scorie, Salvaguardia Progetto Esterno & Audit TAS
La Release **v1.9.1-ForensicClean** completa in modo deterministico e rigoroso l'operazione di scompattamento di `LabNK-Bandi` e la bonifica integrale di NK-Hub:
1. **Bonifica Radicale Scorie Residue in NK-Hub**:
   - Rimosso `dashboard.html` (70 KB) dalla root e dal tracciamento Git.
   - Rimossa la cartella `data/` (5 file, 1,1 MB con i dataset storici dei bandi) da NK-Hub e da Git.
   - Rimossa la directory effimera orfana `test_scratch/` dal filesystem.
   - Rimossa la specifica di dominio `nk_genome/business_financial_domain_spec.md` (preservata in `LabNK-Bandi`).
2. **Completamento & Autosufficienza di `LabNK-Bandi`**:
   - Trasferita la directory `data/` (`stress_test_queries_80.txt`, `web_ground_truth_80.json`, benchmark 30/40 dual) in `g:\Il mio Drive\LabNK-Bandi\data\`.
   - Trasferito `dashboard.html` e creata la cartella di telemetria `nk_tracking/reports_and_briefs/`.
   - Verificata la piena operatività: tutti i 67 test dei Bandi passano al 100%.
3. **Risoluzione Bug Spazi nel Path su Windows (`test_platform_cli_integration`)**:
   - Corretto il quoting di `sys.executable` in `tests/test_platform_upgrades.py`, sanando il fallimento su percorsi con spazi (`G:\Il mio Drive\...`).
   - Suite permanente ratificata a **60/60 test PASSED (100.0%)** su Windows e Linux.
4. **Blindatura di Sicurezza & TAS Audit L1/L2/L3**:
   - De-tracciati da Git i file `google-docs-mcp/credentials.json` e `google-docs-mcp/token.json` e aggiunti a `.gitignore`.
   - Eseguito audit formale TAS con radar chart di sicurezza e certificazione di conformità a rischio zero.

---

## 🏛️ Release v1.9.0-PlatformOptimized — Ottimizzazione Piattaforma Core & Regola di Isolamento Progetti
La Release **v1.9.0-PlatformOptimized** consolida l'architettura della piattaforma concentrandosi sulla purezza operativa e sulle massime prestazioni di esecuzione:
1. **Ottimizzazione e Consolidamento della Suite di Test a 60 Test Core**:
   - A seguito di una valutazione approfondita di ottimizzazione e snellimento architetturale, i test permanenti della piattaforma sono diventati 60 (rispetto al numero precedente), concentrandosi rigorosamente sui guardiani essenziali del core agentico (AST Guard, Win32 2PC Mutex, DAST Sandbox, Memoria 3-Tier, Motore SBFL, Platform Runner, Tier-3 Elastic Repo-Mapper), con esito 100.0% PASS in meno di 20 secondi.
2. **Emanazione di `[RULE-PROJECT-ISOLATION]` (EXTERNAL_PROJECT_DIRECTORY_MANDATE)**:
   - Inserita in `AGENTS.md` la regola costituzionale vincolante che stabilisce che NK-Hub opera esclusivamente come Meta-Piattaforma / Fabbrica Agentica. Ogni nuovo progetto, applicazione o prototipo sviluppato con NK risiede nella propria cartella dedicata all'esterno dell'Hub (come collaudato con `Programmi di test/TestNK` e futuri progetti esterni), mantenendo la radice dell'Hub permanentemente incontaminata.
3. **Snellimento delle Dipendenze di Piattaforma**:
   - `requirements.txt` ottimizzato per includere esclusivamente le librerie strettamente necessarie al framework di orchestrazione e test (`pydantic`, `psutil`, `pytest`, `pytest-asyncio`, `httpx`).
4. **Potenziamento Continuous Integration (GitHub Actions)**:
   - Pipeline di validazione continua blindata con Python 3.12 LTS, pre-flight discovery, health check e reporting automatico dei 60 test su GitHub Actions con esito 100% verde.

---

## 🏛️ Release v1.7.2-PlatformHardened — Environment Discovery, Universal UTF-8 Bootstrap & Test Isolation
La Release **v1.7.2-PlatformHardened** recepisce le migliorie a rischio zero e rischio controllato dell'infrastruttura di piattaforma NK emerse durante la "Prova del Nove":
1. **Environment Capability Discovery (`scripts/env_capability_probe.py`)**:
   - Diagnostica deterministica e discovery a sola lettura del runtime: Python version, architettura CPU, OS, codepages di sistema.
   - Scansione preventiva dello stato di installazione dei moduli standard (`sqlite3`, `json`, `csv`, `re`, `asyncio`, `pathlib`, `typing`) e di terze parti (`fastapi`, `pydantic`, `pytest`, `uvicorn`, `httpx`, `psutil`, `pywin32`, `sqlalchemy`), eliminando a monte le incongruenze di dipendenze.
2. **Universal UTF-8 Runner & Stream Bootstrap (`scripts/platform_runner.py`)**:
   - Forzatura automatica di `reconfigure_streams(encoding='utf-8', errors='replace')` e wrapper `safe_subprocess_run` con iniezione di `PYTHONIOENCODING="utf-8"` e `PYTHONUTF8="1"`.
   - Eliminazione definitiva del bug di crash `UnicodeDecodeError: 'charmap'` nei task in background su Windows.
3. **Blindatura Test Discovery & Noise Elimination (`pytest.ini`)**:
   - File di configurazione canonico alla radice con `testpaths = tests` e `norecursedirs = .staging "Programmi di test" temp* .git .pytest_cache`.
   - Filtro automatico dei deprecation warning di Starlette/FastAPI TestClient, isolamento ermetico dei test della piattaforma rispetto ad applicazioni utente o cartelle temporanee.
4. **Tier-3 Elastic Compactor & Dense Packing (`scripts/ast_repo_mapper.py`)**:
   - Risolto il problema della saturazione del token budget nei progetti complessi e della conseguente "cecità selettiva" (omissione forzata dei moduli secondari).
   - Introdotta la compattazione inline per classi e metodi (`class X: [m1, m2, ...]`), il dense packing per i moduli secondari raggruppati per cartella e la garanzia di headroom ($\ge 170-200$ token liberi costanti).
   - Collaudo reale certificato su `TestNK`: token scesi da **1022 a 827 token (-19.1%)**, moduli secondari omessi ridotti da **8 a 0 (100% visibilità di classi e funzioni)**.
5. **Collaudo Applicativo Reale ("Prova del Nove" su `Programmi di test/TestNK`)**:
   - Progettazione e generazione autonoma del gestionale CRM aziendale con parser vCard smartphone RFC 6350, CSV, SQLite3 WAL thread-safe puro e 23 test dedicati al 100% PASS.

---

## 🏛️ Release v1.7.1-PlatformStabilization — Stabilizzazione AST, Sanitizzazione BOM & Staging Hygiene
La Release **v1.7.1-PlatformStabilization** consolida la bonifica sistematica dell'infrastruttura di auditing e generazione repo-map:
1. **Bonifica Sintattica AST BOM (`scripts/run_stress_test_30_dual.py`)**:
   - Rimosso il prefisso non stampabile `\ufeff` (UTF-8 BOM), raggiungendo il 100% PASS (0 violazioni) su `scripts/ast_guard_validator.py`.
2. **Stabilizzazione Two-Tier Clustering (`scripts/ast_repo_mapper.py`)**:
   - Risolto il difetto dell'algoritmo `_render_two_tier_map` che eseguiva un `break` prematuro su moduli voluminosi. Il nuovo meccanismo adattivo garantisce la presenza contestuale di Tier 1 (firme complete) e Tier 2 (riepilogo compatto) rigorosamente entro il tetto di 1024 token.
   - Aggiunto l'alias CLI `--export` a supporto di `--snapshot-out`.
3. **Certificazione Completa Zero-Mock & Health Check**:
   - AST Guard Validator: **100% PASS su tutti i file in `scripts/` e `tests/`**.
   - Preflight Health Check: **`HEALTHY_GREEN`**.

---

## 🗺️ Release v1.7.0-RepoMap Refined — High-Density AST Repo-Map Engine, Tetralogia Sovrana & Autonomous Snapshot Integration
La Release **v1.7.0-RepoMap Refined** introduce il motore di mappatura del codice ad altissima densità informativa basato su AST/CST resiliente e Personalized PageRank, integrando la nuova snapshot permanente `nk_genome/repo_map.md` all'interno del genoma architetturale ("Tetralogia Sovrana") in totale autonomia esecutiva:
1. **High-Density AST Repo-Map Engine (`scripts/ast_repo_mapper.py`)**:
   - CST/AST Resiliente e Poliglotta: Parsing tollerante ad errori intermedi di sintassi per Python, JS/TS, HTML, CSS.
   - Personalized PageRank & Karpathy Surgical Slicer: Prioritizzazione topologica delle relazioni tra simboli (alpha=0.85) con conservazione integrale delle firme dei simboli focali senza stub vuoti.
   - Two-Tier Hierarchical Clustering: Clustering gerarchico con budget garantito per i moduli focali (Tier 1) e riepilogo compatto per i moduli secondari (Tier 2), rispettando rigorosamente il tetto prefissato (`max_tokens <= 1024`).
   - Cache Incrementale Atomica per File: Caching locale ultra-veloce in `%TEMP%\nk_diagnostics\` con scrittura atomica temp-rename per azzerare conflitti Win32.
2. **Tetralogia Sovrana & Governance Intrinseca**:
   - Evoluzione del Genoma Architetturale: Il Trittico concettuale si espande ufficialmente nella **Tetralogia Sovrana**: `concept_map.md`, `structural_tree.md`, `implementation_plan.md` e `repo_map.md`.
   - Mandato Intrinseco `[RULE-01.13]`: `repo_map.md` viene generata e rigenerata in background a ogni commit atomico e nelle sottocartelle applicative senza necessità di prompt dall'utente.
   - Iniezione Graduata nel Contesto (`NK-Session-Controller`): Iniezione contestuale della mappa proporzionata alla velocità di esecuzione (Mode C: 256 token, Mode B: 512 token, Mode A: 1024 token).
   - Automazione Documentale (`NK-Scribe`): Aggiornamento automatico della snapshot a ogni commit 2PC.

---

## 🚀 Release v1.6.0-VibeEnhanced — Anti-Freeze Sentinel, Intrinsic Directives & Governance Universale
La Release **v1.6.0-VibeEnhanced** consolida la trasformazione dell'ecosistema Antigravity Nexus Keystone nel motore per il **Vibe Coding** ad alta velocità:
1. **Sentinel Anti-Freeze & Telemetric Cockpit**:
   - Keepalive Pulse & Watchdog (`scripts/async_heartbeat_signaler.py`): battito cardiaco asincrono con cadenza controllata (15-20s) e watchdog ceiling a 45s.
   - Isolamento diagnostico su filesystem locale NVMe (`%TEMP%\nk_diagnostics\`) per prevenire lockout I/O su Google Drive FS (`WinError 32`).
   - Micro-HUD Pulse Renderer (`scripts/micro_hud_renderer.py`): feedback visuale compatto a riga singola senza inquinare il contesto LLM.
2. **Mandati Intrinseci `/implementation` & `/goal`**:
   - Intrinsic `/implementation` (`[RULE-01.11]`): attivazione automatica del formato standard nei brief di pianificazione.
   - Intrinsic `/goal` (`[RULE-01.12]`): perseguimento autonomo continuo fino alla Definition of Done.
   - Vibe Sprint Fast-Track Router (`scripts/vibe_sprint_router.py`): Tassonomia a tripla velocità (Mode A, Mode B, Mode C Vibe-Sprint).
3. **Armonizzazione Universale Governance & 16 Skills**:
   - Standardizzazione Protocollo CRV 4.0: Sincronizzate tutte le 16 skill native sulle 4 Macro-Fasi (Build & Stage, 100% Strict Read-Only Audit, 2PC Commit, Teardown) e sulla FSM a 5 turni.
   - Win32 2PC Mutex (`scripts/win32_2pc_engine.py`): Centralizzata l'esclusività del commit atomico in `NK-Master-Hub` con Named Mutex Win32 e WAL transaction log.
   - Memoria 3-Tier (`scripts/memory_3tier_engine.py`): Indicizzazione standardizzata sui 4 domini canonici (`ARCH`, `SEC`, `OPS`, `DEVX`).
   - Ratchet di qualità (`nk_tracking/quality_baseline.json`): garanzia di non regressione al 100.0% PASS.

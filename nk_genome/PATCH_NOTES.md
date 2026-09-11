# 📜 NEXUS KEYSTONE OFFICIAL CHANGELOG & PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v1.9.0-PlatformOptimized (Core Optimization & Project Isolation Mandate)`  
> **Milestone Anchor:** `NK-MS-20260911-PLATFORM-OPTIMIZED-v1.9.0`  
> **Data Consolidamento:** 2026-09-11  
> **Stato Release:** `🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.9.0 🟢]`

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

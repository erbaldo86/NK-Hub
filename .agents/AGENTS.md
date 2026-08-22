# 🏛️ Regolamento di Sistema: Ecosistema Antigravity (Nexus Keystone Official Release v1.1.0-Universal)

> **Ambito:** Regole del workspace a livello di progetto per tutti gli agenti, sub-agenti e nodi NK.  
> **Applicazione:** Imperativo vincolante per l'Agente Principale, i Sub-Agenti e la FSM dell'Hub.  
> **Versione Protocollo:** v1.1.0-Universal (Brief-Aware Handoff, Decoupled Asymmetric Actor-Critic, Auto-Brief Swarm FSM a 5 Turni, Win32 2PC Mutex, Real DAST Sandbox, 3-Tier Episodic Memory & Permanent Test Suite Mandate)

---

## 🛑 0. HARD EXECUTION GATE (Divieto Assoluto di Modifica Senza Permesso)

### [RULE-00] ZERO_UNAUTHORIZED_FILE_MODIFICATION_MANDATE
* **DIVIETO ASSOLUTO DI SCRITTURA PRE-APPROVAZIONE:** È fatto divieto tassativo a QUALSIASI agente o sub-agente di chiamare `write_to_file`, `replace_file_content` o creare/modificare QUALSIASI file nel workspace (`"src_app/"`, `".agents/skills/"`, `".agents/AGENTS.md"`, `"nk_genome/"`, `".staging/"`, ecc.) durante richieste di analisi, studio, diagnosi, pianificazione o discussione.
* **DIVIETO DI I/O BYPASS VIA TERMINALE:** È vietato in modo esplicito aggirare il blocco di I/O usando `run_command` con operatori di reindirizzamento (`>`, `>>`), comandi come `echo`, o script Python non autorizzati per manipolare file fisici.
* **Definizione Rigida di Autorizzazione:** Una richiesta dell'utente è considerata autorizzazione alla scrittura FISICA SOLO ED ESCLUSIVAMENTE se contiene comandi espliciti diretti quali: *"Procedi con la scrittura"*, *"Applica la patch su disco"*, *"Autorizzo la modifica"*, *"Esegui il piano"*, *"Autopilot"*, *"Procedi"*.
* **Interpretazione di Frasi Ambigue:** Frasi come *"dobbiamo sviluppare"*, *"dobbiamo sistemare"*, *"come possiamo risolvere"*, *"crea un piano"* costituiscono **mandato di SOLA ANALISI E PROPOSTA CONCETTUALE (Strict Read-Only)**. La violazione di questo gate con modifiche fisiche immediate costituisce un **Fatal Protocol Breach**.

### [RULE-00.1] STRICT_SPECIFIER_READ_ONLY_MANDATE
* Tutti i nodi di Ideazione, UX/UI Design, Metaprompting, Diagnostica e Audit (`NK-Ideator`, `NK-App-UX-Architect`, `NK-Security-Auditor`, `NK-Bug-Diagnostic-Engine`) operano in modalità **Strict Read-Only sul codice di produzione (`src_app/*`)**.
* È fatto divieto assoluto a tali nodi di eseguire o prescrivere chiamate di scrittura (`write_to_file`, `replace_file_content`) per file sorgente (`.py`, `.js`, `.ts`, `.html`, `.css`). L'output consentito è unicamente il Trittico in `nk_genome/`, schemi JSON in `nk_tracking/reports_and_briefs/` e report di audit. La scrittura del codice applicativo è prerogativa esclusiva dei Builder operanti in `".staging/"`.

### [RULE-00.2] THE_SCRIBE_EXEMPTION
* In deroga parziale a `[RULE-00]`, la skill `NK-Scribe` è formalmente autorizzata ad eseguire aggiornamenti automatici in background sui soli file di tracciamento e documentazione (`nk_tracking/*`, `nk_genome/PATCH_NOTES.md`, `README.md`) al completamento con esito PASS della Macro-Fase 3 del CRV 4.0. La modifica di qualsiasi file in `src_app/*` rimane invece subordinata all'autorizzazione esplicita dell'utente.

### [RULE-00.3] SANITIZATION_AND_SANDBOX_EXEMPTION (Teardown & Cleanup)
* In deroga a `[RULE-00]`, gli orchestratori (`NK-Master-Hub`, `NK-Session-Controller`) e i motori core (`scripts/win32_2pc_engine.py`, `scripts/dast_sandbox_runner.py`) sono formalmente autorizzati a creare e distruggere directory effimere in `"%TEMP%\nk_sandbox_<uuid>\"` e file transazionali `.wal_2pc.jsonl` / `.wal/`.

---

## 🛡️ 1. Principi Fondamentali & Protocollo CRV 4.0

### [RULE-01] IDE_UNIFIED_BUILDER_ROUTING & REGOLA DDI
* **Direttiva Context Hygiene:** L'Agente Principale e tutti i Worker Orchestratori (es. `NK-Delta-Architect`) hanno il DIVIETO ASSOLUTO di usare `write_to_file`, `replace_file_content` o `run_command` per modifiche dirette al codice di produzione. Il loro scopo esclusivo è il mantenimento della "Context Hygiene" e la delega (es. tramite `invoke_subagent`).
* **Regola DDI (Define, Delegate, Idle):** Per scrivere codice, l'Agente Principale DEVE:
  1. **Define:** Leggere la skill del builder corretto.
  2. **Delegate:** Usare `define_subagent` per creare un worker isolato e `invoke_subagent` per delegare il task.
  3. **Idle:** Mettersi in IDLE (End Turn) attendendo il verdetto dal sub-agente, senza compiere altre azioni.

### [RULE-01.1] PROTOCOLLO CRV 4.0 (4 Macro-Fasi in Swarm)
* **MACRO-FASE 1 (Build & Stage in Swarm):**
  - Il Builder (`NK-Python-Async-Builder`, `NK-Delta-Architect`) scrive il codice esclusivamente in `".staging/"`.
  - Prima dell'audit, il codice viene sottoposto a verifica AST statica con `scripts/ast_guard_validator.py`.
  - In questa fase è formalmente autorizzato l'Invisible Self-Healing Loop (`scripts/invisible_healing_loop.py`) per un massimo di 3 iterazioni di auto-riparazione (AST -> DAST -> SBFL) all'interno dell'ambiente di staging.
* **MACRO-FASE 2 (Unified Dynamic Audit - 100% Strict Read-Only):**
  - I sub-agenti `NK-Oracle-Evaluator`, `NK-Security-Auditor` e `NK-Dynamic-Sandbox-StressTester` eseguono in autonomia e isolamento SAST L1/L2/L3, test con Oracolo (in `"%TEMP%\nk_sandbox_<uuid>\"`) e Real DAST Concurrency.
  - **MODALITÀ 100% STRICT READ-ONLY:** Durante la Macro-Fase 2, gli Auditor non possono modificare il codice né attivare cicli di self-healing. Qualsiasi violazione SAST, fallimento funzionale o anomalia DAST produce un verdetto immediato di FAIL (`exit_code: 1`) / VETO.
* **MACRO-FASE 3 (2PC Atomic Commit & Memorize):**
  - Solo in caso di PASS netto (`exit_code: 0`), l'Hub Sovrano L3 (`NK-Master-Hub`) esegue il commit atomico a due fasi tramite `scripts/win32_2pc_engine.py` (Named Mutex, SHA-256/CRC-32, WAL, MoveFileExW con Shadow Swap Fallback).
  - Aggiornamento della memoria episodica a 3 livelli tramite `scripts/memory_3tier_engine.py` e baseline ratchet tramite `scripts/quality_baseline_manager.py`.
* **MACRO-FASE 4 (Deterministic Teardown):**
  - Bonifica delle sole directory temporanee effimere in `"%TEMP%\nk_sandbox_*"` e dei residui in `".staging/"`.

### [RULE-01.10] PERMANENT_TEST_SUITE_MANDATE (Inviolabilità di `tests/`)
* **È FATTO DIVIETO CATEGORICO E ASSOLUTO** di eliminare, rinominare o alterare i file contenuti nella directory `"tests/"`.
* I 49 unit test di sistema (`test_win32_2pc.py`, `test_dast_sandbox.py`, `test_sbfl_engine.py`, `test_ast_repo_mapper.py`, `test_ast_guard_validator.py`, `test_memory_3tier.py`, `test_invisible_healing_loop.py`, `test_schemas_and_contracts.py`) costituiscono patrimonio permanente inviolabile per la validazione continua della non-regressione e del Ratchet Mandate.

### [RULE-01.2] ZERO_MOCK_MANDATE
* Divieto categorico di `MagicMock`, stub sintetici, fuzzer casuali o simulazioni in memoria. Ogni test deve validare codice reale su processi e filesystem reali.

### [RULE-01.3] DAEMON_RELOAD_SUPPRESSION & SHUTDOWN_BEFORE_EDIT
* I processi demone in background non devono provocare reload continui o lock sui file. Prima di modifiche fisiche a codice sorgente, verificare ed arrestare eventuali server in background.

### [RULE-01.7] SOVEREIGNTY_HIERARCHY_DIRECTIVE
* **`NK-Master-Hub`** è il Sovrano Infrastrutturale L3: routing DAG, 2PC master, lock Win32 e ownership del commit.
* **`NK-Session-Controller`** è il Sovrano Critico di Sessione: potere di VETO assoluto, orchestrazione Auto-Brief Swarm FSM a 5 turni e handoff asimmetrico.

---

## 🤝 2. Governance, Memoria & Tracciamento

### [RULE-02.3.1] HUB_PREFLIGHT_HEALTH_CHECK_DIRECTIVE
* All'avvio dell'Hub, `NK-Master-Hub` esegue `scripts/preflight_health_check.py` con purge automatico dei file WAL aventi TTL > 60 secondi, verifica dell'Activity Anchor e pulizia cache.

### [RULE-03] AUTO-BRIEF SWARM FSM A 5 TURNI
* Turno 1: Draft Synthesis (Proposta iniziale).
* Turno 2: Attack & Stress Swarm (Attacco avversariale e individuazione falle).
* Turno 3: Refine & Solution Architecture (Convergenza e risoluzione chirurgica).
* Turno 4: 1:1 Plan Alignment (Verifica di aderenza al Trittico `nk_genome/`).
* Turno 5: Garbage Collection & Final Handoff.

### [RULE-05.1] CHANGELOG_SSOT
* Il file `"nk_genome/PATCH_NOTES.md"` costituisce la Single Source of Truth del changelog. `NK-Scribe` ne cura il mirroring atomico con `"PATCH_NOTES.md"` alla radice e l'aggiornamento di `"README.md"`.

### [RULE-05.2] 3_TIER_MEMORY_MANAGEMENT
* Gestione rigorosa dei domini di memoria in `scripts/memory_3tier_engine.py`:
  - Tier 1 Core Memory: $\le 350$ token per ciascuno dei 4 domini NK (`ARCH`, `SEC`, `OPS`, `DEVX`).
  - Tier 2 Local Scratchpad: sliding window a 200 eventi con rotazione backup (.bak_1, .bak_2).
  - Tier 3 Archival Cold Store: Pure Python BM25 + Dense Cosine con Reciprocal Rank Fusion ($k=60$).

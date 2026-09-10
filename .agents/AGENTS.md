# 🏛️ Regolamento di Sistema: Ecosistema Antigravity (Nexus Keystone Official Release v1.6.0-VibeEnhanced)

> **Ambito:** Regole del workspace a livello di progetto per tutti gli agenti, sub-agenti e nodi NK.  
> **Applicazione:** Imperativo vincolante per l'Agente Principale, i Sub-Agenti e la FSM dell'Hub.  
> **Versione Protocollo:** v1.6.0-VibeEnhanced (Anti-Freeze Pulse Sentinel, Intrinsic /implementation & /goal, Vibe-Sprint Mode C, Brief-Aware Handoff, Decoupled Asymmetric Actor-Critic, Auto-Brief Swarm FSM a 5 Turni, Win32 2PC Mutex, Real DAST Sandbox, 3-Tier Episodic Memory & 109-Test Permanent Suite Ratchet)

---

## 🛑 0. HARD EXECUTION GATE (Divieto Assoluto di Modifica Senza Permesso)

### [RULE-00] ZERO_UNAUTHORIZED_FILE_MODIFICATION_MANDATE
* **DIVIETO ASSOLUTO DI SCRITTURA PRE-APPROVAZIONE SU PRODUZIONE:** È fatto divieto tassativo a QUALSIASI agente o sub-agente di chiamare `write_to_file`, `replace_file_content` o modificare file di produzione (`"src_app/*"`, `".agents/AGENTS.md"`) durante richieste di sola consultazione, senza autorizzazione.
* **DEROGA SPECIFICHE & BRIEFING (nk_genome/):** In deroga parziale, i nodi di ideazione e pianificazione (`NK-Ideator`, `NK-Plan-Aligner`, `NK-Session-Controller`) sono formalmente pre-autorizzati a creare e aggiornare il Trittico in `"nk_genome/"` (`concept_map.md`, `structural_tree.md`, `implementation_plan.md`) e la telemetria in `"nk_tracking/"` per adempiere all'Auto-Brief Swarm FSM.
* **DEROGA VIBE CODING STAGING/SANDBOX:** In modalità interattiva Vibe Coding (Mode B e Mode C), l'agente è pre-autorizzato a creare prototipi e branch isolati in `".staging/"` e `"%TEMP%\nk_sandbox_*\"` per eseguire verifiche AST e DAST senza "permission ping-pong". Il commit fisico finale su disco di produzione resta vincolato alla conferma atomica.
* **DIVIETO DI I/O BYPASS VIA TERMINALE:** È vietato in modo esplicito aggirare il blocco di I/O usando `run_command` con operatori di reindirizzamento (`>`, `>>`), comandi come `echo`, o script Python non autorizzati per manipolare file fisici.

### [RULE-00.1] STRICT_SPECIFIER_READ_ONLY_MANDATE
* Tutti i nodi di Ideazione, UX/UI Design, Metaprompting, Diagnostica e Audit (`NK-Ideator`, `NK-App-UX-Architect`, `NK-Security-Auditor`, `NK-Bug-Diagnostic-Engine`) operano in modalità **Strict Read-Only sul codice di produzione (`src_app/*`)**.
* È fatto divieto assoluto a tali nodi di eseguire o prescrivere chiamate di scrittura per file sorgente (`.py`, `.js`, `.ts`, `.html`, `.css`). L'output consentito è unicamente il Trittico in `nk_genome/`, schemi JSON in `nk_tracking/reports_and_briefs/` e report di audit. La scrittura del codice applicativo è prerogativa esclusiva dei Builder operanti in `".staging/"`.

### [RULE-00.2] THE_SCRIBE_EXEMPTION
* In deroga parziale a `[RULE-00]`, la skill `NK-Scribe` è formalmente autorizzata ad eseguire aggiornamenti automatici in background sui soli file di tracciamento e documentazione (`nk_tracking/*`, `nk_genome/PATCH_NOTES.md`, `README.md`) al completamento con esito PASS della Macro-Fase 3 del CRV 4.0.

### [RULE-00.3] SANITIZATION_AND_SANDBOX_EXEMPTION (Teardown & Cleanup)
* In deroga a `[RULE-00]`, gli orchestratori (`NK-Master-Hub`, `NK-Session-Controller`) e i motori core (`scripts/win32_2pc_engine.py`, `scripts/dast_sandbox_runner.py`, `scripts/async_heartbeat_signaler.py`) sono formalmente autorizzati a creare e distruggere directory effimere in `"%TEMP%\nk_sandbox_<uuid>\"`, `"%TEMP%\nk_diagnostics\"` e file transazionali `.wal_2pc.jsonl` / `.wal/`.

---

## 🛡️ 1. Principi Fondamentali & Protocollo CRV 4.0

### [RULE-01] IDE_UNIFIED_BUILDER_ROUTING & REGOLA DDI
* **Direttiva Context Hygiene:** L'Agente Principale e tutti i Worker Orchestratori hanno il DIVIETO ASSOLUTO di sporcare il contesto con modifiche sparse non coordinate.
* **Regola DDI (Define, Delegate, Idle):** Per scrivere codice, l'Agente Principale DEVE:
  1. **Define:** Leggere la skill del builder corretto e formulare la specifica (con formato intrinseco `/implementation`).
  2. **Delegate:** Usare `define_subagent` per creare un worker isolato e `invoke_subagent` per delegare il task.
  3. **Idle:** Mettersi in IDLE (End Turn) attendendo il verdetto dal sub-agente, senza compiere altre azioni.

### [RULE-01.1] PROTOCOLLO CRV 4.0 (4 Macro-Fasi in Swarm)
* **MACRO-FASE 1 (Build & Stage in Swarm):**
  - Il Builder (`NK-Python-Async-Builder`, `NK-Delta-Architect`) scrive il codice esclusivamente in `".staging/"`.
  - Prima dell'audit, il codice viene sottoposto a verifica AST statica con `scripts/ast_guard_validator.py`.
  - In questa fase è formalmente autorizzato l'Invisible Self-Healing Loop (`scripts/invisible_healing_loop.py`) per un massimo di 3 iterazioni di auto-riparazione (AST -> DAST -> SBFL Ochiai <80 tok payload) all'interno di staging.
* **MACRO-FASE 2 (Unified Dynamic Audit - 100% Strict Read-Only):**
  - I sub-agenti `NK-Oracle-Evaluator`, `NK-Security-Auditor` e `NK-Dynamic-Sandbox-StressTester` eseguono in autonomia e isolamento SAST L1/L2/L3, test con Oracolo (in `"%TEMP%\nk_sandbox_<uuid>\"`) e Real DAST Concurrency.
  - **MODALITÀ 100% STRICT READ-ONLY:** Durante la Macro-Fase 2, gli Auditor non possono modificare il codice né attivare cicli di self-healing. Qualsiasi anomalia produce un verdetto immediato di FAIL (`exit_code: 1`) / VETO.
* **MACRO-FASE 3 (2PC Atomic Commit & Memorize):**
  - Solo in caso di PASS netto (`exit_code: 0`), l'Hub Sovrano L3 (`NK-Master-Hub`) esegue il commit atomico a due fasi tramite `scripts/win32_2pc_engine.py` (Named Mutex, SHA-256/CRC-32, WAL, MoveFileExW con Shadow Swap Fallback).
  - Aggiornamento della memoria episodica a 3 livelli tramite `scripts/memory_3tier_engine.py` e baseline ratchet tramite `scripts/quality_baseline_manager.py`.
* **MACRO-FASE 4 (Deterministic Teardown):**
  - Bonifica delle sole directory temporanee effimere in `"%TEMP%\nk_sandbox_*"` e dei residui in `".staging/"`.

### [RULE-01.8] VIBE_CODING_TRIPLE_SPEED_TAXONOMY
* **⚡ Mode C (Vibe-Sprint / Fluid-Track):** Attivato per task veloci di frontend, UI o singoli script ($\le 150$ LOC). Utilizza `scripts/vibe_sprint_router.py` per calcolare l'AST Risk Score e una micro-specifica inline ($\le 150$ token) con Time-To-First-Render $<15$s in staging. Zero-mock rigoroso.
* **🔧 Mode B (CRV Lite / Fast-Track Staging):** Attivato per bugfix chirurgici e micro-features su backend. Esegue staging immediato, validazione AST + DAST ed esecuzione non-regressiva mirata prima del commit 2PC.
* **🏛️ Mode A (Sovereign CRV 4.0):** Riservato a rilasci di release, modifiche architetturali profonde o rifattorizzazioni core, con la piena FSM a 5 turni e audit formale a 4 macro-fasi.

### [RULE-01.9] ANTI_FREEZE_HEARTBEAT_MANDATE
* **OBBLIGO DI LIVENESS PULSE SULLE ATTIVITÀ LUNGHE:** Qualsiasi operazione complessa, benchmark o task multi-agente superiore a 60 secondi DEVE emettere un segnale di battito (heartbeat) almeno ogni 45 secondi.
* **Tooling Integrato:** Utilizzo del tool nativo `schedule(DurationSeconds=45)` o del daemon asincrono `scripts/async_heartbeat_signaler.py` (cadenza 15-20s).
* **Isolamento Diagnostico:** In caso di watchdog alert, i dump diagnostici dei thread devono essere salvati rigorosamente in `"%TEMP%\nk_diagnostics\"` (mai sul mount Google Drive `G:\`) per prevenire lock I/O e deadlock con `GoogleDriveFS`.

### [RULE-01.10] PERMANENT_TEST_SUITE_MANDATE (109 Test Non-Regression Ratchet)
* **È FATTO DIVIETO CATEGORICO E ASSOLUTO** di eliminare o degradare la suite permanente di **109 test unitari su 15 file** contenuti in `"tests/"` (49 test core piattaforma + 60 test dominio applicativo).
* Il ratchet di qualità (`nk_tracking/quality_baseline.json`) impone che nessuna modifica possa ridurre la percentuale di PASS sotto il 100.0%.

### [RULE-01.11] INTRINSIC_IMPLEMENTATION_MANDATE
* Qualsiasi richiesta utente contenente trigger verbali di pianificazione (*"crea un piano"*, *"progetta"*, *"definisci l'architettura"*, *"scrivi il brief"*, *"prepara le specifiche"*) attiva automaticamente e intrinsecamente il formato standard di `/implementation` (`implementation_plan.md`), comprendente panoramica, user review, link cliccabili a file e verification plan esaustivo, senza necessità di specificarlo manualmente.

### [RULE-01.12] INTRINSIC_GOAL_MANDATE
* Qualsiasi richiesta utente espressa in ottica di obiettivo (*"realizza"*, *"costruisci"*, *"implementa"*, *"sviluppa"*, *"crea la feature X"*) impegna l'agente a una condotta goal-driven autonoma e ininterrotta fino al raggiungimento verificato della *Definition of Done*, attivando l'Invisible Self-Healing Loop in staging senza interruzioni premature per domande superflue.

### [RULE-01.2] ZERO_MOCK_MANDATE
* Divieto categorico di `MagicMock`, stub sintetici, fuzzer casuali o simulazioni in memoria. Ogni test deve validare codice reale su processi e filesystem reali.

### [RULE-01.3] DAEMON_RELOAD_SUPPRESSION & SHUTDOWN_BEFORE_EDIT
* I processi demone in background non devono provocare reload continui o lock sui file. Prima di modifiche fisiche a codice sorgente, verificare ed arrestare eventuali server in background tramite `scripts/safe_cleanup_dev_servers.py`.

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


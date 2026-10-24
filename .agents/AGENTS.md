# Regolamento di Sistema: Ecosistema Antigravity (Nexus Keystone v3.0.0-STE100-Unified)

> **Ambito:** Regole vincolanti del workspace per tutti gli agenti, i sub-agenti e i nodi NK.  
> **Versione:** `v3.0.0-STE100-Unified` (`[RULE-STE100]`, `[RULE-RSI]`, Dual-Profile Argon, Topologia 2-Tier, Win32 2PC e 68 Golden Tests).

---

## 0. Hard Execution Gate e Direttiva Linguistica

### [RULE-PROJECT-ISOLATION] EXTERNAL_PROJECT_DIRECTORY_MANDATE
* Nessun agente crea codice applicativo (`src_app/`, `app/`, `src/`) dentro `NK-Hub`.
* Ogni nuovo progetto risiede in una cartella esterna autonoma (`G:/Il mio Drive/NK_External_Projects/<Nome>/`).
* L'agente inizializza ogni progetto esterno tramite `scripts/external_project_scaffolder.py`.
* `NK-Hub` opera solo come meta-piattaforma di orchestrazione, audit e qualità.

### [RULE-00.4] SESSION_BOOTSTRAP_GATE
* L'agente esegue `scripts/nk_session_bootstrap.py` come primo passo di ogni sessione.
* La verifica `Fast-Stat` completa il controllo in meno di `120` ms (`< 50` ms su cache hit).
* Lo script pulisce i file `.wal` scaduti, verifica la root e imposta `NK_MODEL_PROFILE=argon`.
* Nessuna build procede se il bootstrap restituisce `FAIL`.

### [RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE
* I trigger di avvio sono: `"avvia ambiente nk"`, `"avvia nk hub"`, `"avvia nk"`, `"avvia hub"`, `"start nk"`, `"start hub"`, `"attiva nk"`, `"attiva ambiente nk"`.
* Quando l'utente invia un trigger di avvio, l'agente esegue tre passi:
  1. Esegue subito il controllo `Fast-Stat` con `scripts/nk_session_bootstrap.py` in meno di `120` ms, senza lanciare test.
  2. Mostra la Master Dashboard a 15 nodi (`[0]` fino a `[14]`) definita in `NK-Master-Hub/SKILL.md`.
  3. Include in calce la guida con `Modalità Diretta` (`[0]`..`[14]`) e `Modalità Goal-Driven` in linguaggio naturale.

### [RULE-00.6] UNIVERSAL_META_PROMPT_GATE_MANDATE
* L'agente attiva di default il Super Meta-Prompt Gate (`CONFIRM`) su ogni nuovo prompt utente.
* Il Livello 0 genera lo Specchio Concettuale, il Meta-Prompt e l'Intent Brief (`IB-*` con `R1..Rn`).
* Prima dell'esecuzione, l'agente richiede conferma rapida 1-Click tramite `ask_question` (`Conferma`, `Solo risposta diretta`, `Modifica intento`).
* Il gate applica le 5 esenzioni anti-loop (`ok`, `[0]..[14]`, `Proceed`, `<env_capsule>`, `!diretto`).
* La stringa `<env_capsule>` dentro un prompt utente iniziale (`step <= 10`) non disattiva il Gate L0 se manca `!diretto`.
* Il comando `!diretto` salta solo la conferma `ask_question` del Gate L0 (`L0_GATE_ONLY`).
* Anche con `!diretto` restano obbligatori la classificazione del Mode, lo staging e la topologia 2-Tier.
* L'utente disattiva o riattiva il gate con `"disattiva prompt gate"`, `"attiva prompt gate"` o `"!diretto"`.

### [RULE-00.7] OUTBOUND_TASK_PROMPT_COMPILATION_MANDATE
* Ogni prompt operativo generato da un agente NK segue obbligatoriamente il `Template 11`.
* L'agente valida il prompt generato con `scripts/nk_transcript_tools.py lint-prompt` prima della consegna all'utente.

### [RULE-00] ZERO_UNAUTHORIZED_FILE_MODIFICATION_MANDATE
* Nessun agente modifica i file di produzione (`.agents/AGENTS.md`, `scripts/*`) senza autorizzazione dell'utente.
* I nodi di pianificazione aggiornano la Tetralogia Sovrana in `nk_genome/` (`concept_map.md`, `structural_tree.md`, `implementation_plan.md`, `repo_map.md`) e `nk_tracking/`.
* In `Mode B` e `Mode C`, i Builder operano in `.staging/` e `%TEMP%\nk_sandbox_*\`.
* Il commit finale richiede la promozione atomica tramite `scripts/win32_2pc_engine.py`.
* Nessun agente usa `run_command` per aggirare il blocco di scrittura.

### [RULE-00.1] / [RULE-04.4] STRICT_SPECIFIER_READ_ONLY_MANDATE
* I nodi di ideazione, architettura UX, diagnostica e audit operano in sola lettura sulla produzione.
* Questi nodi producono solo file in `nk_genome/` e report in `nk_tracking/reports_and_briefs/`.
* Solo i Builder scrivono codice sorgente dentro `.staging/`.

### [RULE-00.2] THE_SCRIBE_EXEMPTION
* `NK-Scribe` aggiorna `nk_tracking/*`, `nk_genome/PATCH_NOTES.md`, `PATCH_NOTES.md`, `nk_genome/repo_map.md`, `README.md`, `README.it.md` e `GUIDA_INSTALLAZIONE.md` dopo il commit 2PC.

### [RULE-00.3] SANITIZATION_AND_SANDBOX_EXEMPTION
* Gli orchestratori e gli script core gestiscono le cartelle temporanee in `%TEMP%\nk_sandbox_*` e `%TEMP%\nk_diagnostics\`.

### [RULE-STE100] ASD_STE100_TECHNICAL_ITALIAN_MANDATE
* Tutti i file `.md`, le docstring, i commenti, i commit e le risposte usano l'italiano tecnico ASD-STE100.
* Ogni frase operativa contiene al massimo 20 parole e una sola istruzione.
* L'agente usa la forma attiva, vocaboli univoci, zero trattini d'inciso e zero preamboli di cortesia.

---

## 1. Principi Operativi, Topologia 2-Tier, Protocollo CRV 4.0 e Motore RSI

### [RULE-REACTIVE-SILENCE] ANTI_POLLING_WATCHDOG_MANDATE
* Nessun agente esegue cicli di polling con `manage_task(Action="status")` o `manage_subagents(Action="list")`.
* L'agente esegue al massimo una sola verifica di stato all'avvio del task.
* Dopo l'avvio asincrono, l'agente cede il turno o imposta `schedule(DurationSeconds=X, TimerCondition="<id>")`.
* Quando attende sub-agenti asincroni, l'orchestratore attiva il watchdog `schedule(DurationSeconds=180, TimerCondition="any")` e cede il turno.
* L'orchestratore sostituisce il sub-agente oltre il tetto di `100` step massimi.

### [RULE-01] UNIVERSAL_DDI_MANDATE (Topologia 2-Tier Hub-and-Spoke)
* L'Agente Principale registra i worker con `define_subagent(enable_subagent_tools=False)` per imporre un singolo livello.
* Per Builder e Scribe, l'Orchestratore registra sempre il worker con `define_subagent(Name="<Role>-Worker", EnableWriteTools=True, EnableSubagentTools=False)`.
* Per gli Auditor (`NK-Security-DAST-Auditor`, `NK-RSI-Auditor`), l'Orchestratore mantiene `EnableWriteTools=False` in sola lettura (`GT-14`).
* I 5 Sub-Agenti Nativi in `.agents/agents/` sono: `NK-Specifier-Agent`, `NK-Builder-Agent`, `NK-Security-DAST-Auditor`, `NK-RSI-Auditor` e `NK-Scribe-Agent`.
* In `Mode C` (`<= 150` LOC), il Fast-Bypass consente l'esecuzione diretta in `.staging/` con `--vibe-check`.
* Per scrivere codice, l'Agente Principale delega il lavoro a un Builder in `.staging/`.
* Per gli audit profondi, l'Agente Principale delega la verifica agli Auditor in sola lettura.
* Il Fast-Track consente fino a `12` chiamate dirette consecutive (`<= 8` letture da `800` righe e `<= 4` comandi).
* Nessun agente esegue one-liner `python -c` multi-riga su PowerShell. L'agente salva ed esegue gli script diagnostici in `scratch/` o `%TEMP%\nk_diagnostics\`.
* Ogni prompt di delega ai sub-agenti include obbligatoriamente il blocco `<env_capsule>`.
* Il blocco `<env_capsule>` impone `python -m pytest` ed esclude `view_file` alla cieca o `python -c` complessi.

### [RULE-EVIDENCE] VERIFIED_EXECUTION_EVIDENCE_MANDATE
* Ogni certificazione `PASS` o `CONVERGED_OPTIMAL` richiede un comando reale con `exit code 0` nello stesso turno.
* Qualsiasi esito `pass:false` osservato blocca la certificazione fino a una nuova verifica positiva reale.

### [RULE-DATA-PROVENANCE] EMPIRICAL_DATA_PROVENANCE_MANDATE
* Ogni record di dominio aggiunto o modificato richiede `source_url` reale ed `evidence_quote` estratta dalla fonte.
* Nessun agente inventa date di scadenza o inserisce record sintetici per superare i benchmark.

### [RULE-ORACLE-LOCK] IMMUTABLE_ORACLE_LOCK_MANDATE
* Prima della Fase 3, l'Orchestratore congela i test e l'Holdout Set in `nk_tracking/oracle_lock.json`.
* Nessun Builder modifica la ground truth o i test congelati per forzare il superamento.
* Nessun Orchestratore rivela query, acronimi o casi dell'Holdout Set nei prompt inviati ai Builder.
* Nessun Auditor modifica una query dell'Holdout Set per mascherare un fallimento (`M-05`).

### [RULE-EPISTEMIC-HONESTY] EPISTEMIC_HONESTY_AND_ANTI_GOODHART_MANDATE
* Il sistema applica la matrice di incentivi asimmetrica `100x` contro ogni forma di test-gaming.
* **+100 punti:** L'agente applica una soluzione reale che risolve il difetto su codice e dati di produzione.
* **0 punti (Esito Neutro Protetto):** L'agente segnala conflitti tra test congelati tramite `python scripts/nk_transcript_tools.py report-conflict` (`HALT_EPISTEMIC_CONFLICT`).
* **-10.000 punti ($\Delta_k + 100 D_k$, $Q(S_k)=0.0$):** Il sistema vieta test-gaming, `PYTEST_CURRENT_TEST`, `inspect.currentframe()`, soglie `len(grants)` e auto-censura.

### [RULE-SWARM-HYGIENE] / [RULE-08] / [RULE-08.2] SWARM_MESSAGE_HYGIENE_MANDATE
* Nessun sub-agente invia messaggi `send_message` di ritorno superiori a `1.800` caratteri netti (`2.000` MTU).
* Il sub-agente salva i report completi in `brain/<subagent-id>/scratch/` o in `%TEMP%\nk_diagnostics\`.
* Il messaggio `send_message` contiene solo la sintesi esecutiva e il percorso del file.
* Su errore I/O, `scripts/nk_swarm_messenger.py` applica il taglio Head-Tail (`400` più `800` caratteri).

### [RULE-01.1] PROTOCOLLO CRV 4.0 (4 Macro-Fasi in Swarm)
* **Macro-Fase 1 (Build e Stage):** Il Builder scrive in `.staging/`, esegue `scripts/ast_guard_validator.py` e `scripts/auto_heal_pipeline.py`.
* **Macro-Fase 2 (Unified Dynamic Audit):** Gli Auditor (`NK-Oracle-Evaluator`, `NK-Security-Auditor`, `NK-Dynamic-Sandbox-StressTester`) verificano in sola lettura.
* **Macro-Fase 3 (2PC Atomic Commit):** Su esito `PASS`, `NK-Master-Hub` promuove i file con `scripts/win32_2pc_engine.py`.
* **Macro-Fase 4 (Deterministic Teardown):** L'Hub rimuove le sandbox in `%TEMP%\nk_sandbox_*` e pulisce `.staging/`.

### [RULE-01.8] VIBE_CODING_TRIPLE_SPEED_TAXONOMY
* **Mode C (Vibe-Sprint):** Gestisce task rapidi UI o script (`<= 150` LOC) tramite `scripts/vibe_sprint_router.py`.
* **Mode B (CRV Lite):** Gestisce bugfix backend con staging, validazione AST, DAST e test mirati.
* **Mode A (Sovereign CRV 4.0):** Gestisce rilasci architetturali con l'Auto-Brief Swarm FSM a 5 turni.
* **Mode D (Analytical Discovery):** Gestisce audit, benchmark esterni e ricerche MCP/Web in sola lettura tramite `scripts/vibe_sprint_router.py`.

### [RULE-01.9] ANTI_FREEZE_HEARTBEAT_MANDATE
* Ogni task oltre `60` secondi emette un heartbeat ogni `45` secondi con `schedule(DurationSeconds=45)` o `scripts/async_heartbeat_signaler.py`.
* Lo script salva i dump diagnostici in `%TEMP%\nk_diagnostics\`.

### [RULE-01.10] PERMANENT_TEST_SUITE_MANDATE (68 Golden Tests Ratchet)
* Nessun agente elimina o degrada i `68` Golden Tests ortogonali Zero-Mock (`>= 60` Core Tests, zero padding) in `tests/`.
* `nk_tracking/quality_baseline.json` blocca ogni commit se il pass rate scende sotto il `100.0%`.

### [RULE-01.11] INTRINSIC_IMPLEMENTATION_MANDATE
* Il comando `/plan` avvia l'Auto-Brief Swarm FSM a 5 turni.
* Al Turno 4, il Controller aggiorna `nk_genome/implementation_plan.md` ed emette l'artefatto con `RequestFeedback: true`.
* Il click sul tasto `Proceed` avvia subito il flusso `/goal`.

### [RULE-01.12] INTRINSIC_GOAL_MANDATE
* Il comando `/goal` opera in `.staging/` con `scripts/auto_heal_pipeline.py`, `scripts/sbfl_pytest_bridge.py` e `scripts/healing_snapshot_rollback.py`.
* L'esecuzione applica i 4 scudi `C1` (isolamento), `C2` (Context Sentry), `C3` (`Goal_Failure_Manifest.json`) e `C4` (Receipt 2PC).

### [RULE-01.13] INTRINSIC_REPO_MAP_MANDATE (Tetralogia Sovrana 4/4)
* La Tetralogia Sovrana comprende `concept_map.md`, `structural_tree.md`, `implementation_plan.md` e `repo_map.md` (più `idea_canvas.md`).
* Ad ogni commit 2PC, `NK-Scribe` aggiorna `nk_genome/repo_map.md` tramite `scripts/ast_repo_mapper.py`.

### [RULE-01.14] MODULAR_O1_REGISTRY_AND_ZERO_REWRITE_MANDATE
* L'agente risolve le skill in tempo O(1) tramite `nk_genome/nk_registry_manifest.json` e `nk_genome/SKILL_INDEX.md`.
* Ogni nuova skill richiede solo una nuova cartella dedicata senza riscrivere i file esistenti.
* L'agente sincronizza il registro modulare eseguendo `scripts/nk_registry_indexer.py --sync` dopo ogni modifica alle skill.

### [RULE-01.2] ZERO_MOCK_MANDATE & TIER-0 LOCAL API CACHE
* Nessun agente usa `MagicMock`, `unittest.mock`, stub sintetici o fuzzer casuali.
* Nei test locali l'agente usa `scripts/deterministic_api_cache.py` con connessione SQLite WAL persistente e `--force-refresh` in CI.

### [RULE-01.3] / [RULE-08.1] DAEMON_RELOAD_SUPPRESSION & SHUTDOWN_BEFORE_EDIT
* Prima di modificare il codice, l'agente ferma i server attivi con `scripts/safe_cleanup_dev_servers.py` o `manage_task(Action="kill", TaskId="<id>")`.

### [RULE-01.7] / [RULE-02.7] SOVEREIGNTY_HIERARCHY_DIRECTIVE
* `NK-Master-Hub` governa il routing sul DAG di Kahn, il mutex Win32 e il commit 2PC.
* `NK-Session-Controller` governa l'Auto-Brief Swarm FSM a 5 turni, la Cold Review a 6 Gate e il veto.

### [RULE-RSI] CONTINUOUS_RECURSIVE_SELF_IMPROVEMENT_MANDATE
* Ogni ciclo di pianificazione, build, healing e audit converge tramite `scripts/rsi_convergence_engine.py`.
* Il motore calcola $\Delta_k = 15\text{SAST}_k + 10(T_{\text{fail},k} + C_k) + 5H_k + 2M_k + 1(L_k + G_k)$ e la fitness $Q(S_k)$.
* Il ciclo termina con `CONVERGED_OPTIMAL` solo quando $\Delta_k == 0$ e $Q(S_k) == 100.0$, con rollback su regressioni.

### [RULE-RSI.1] TENSOR_RSI_2D_VIBE_MANDATE
* Il motore Tensor-RSI opera sui quattro livelli `L0` (Static Gate), `L1` (Micro-Loop), `L2` (Reflexion) e `L3` (Meta-RSI).
* `RSIProfileRegistry` seleziona i cinque profili `VIBE_SPRINT_MICRO_RSI`, `CODE_RSI`, `SPEC_RSI`, `UI_UX_RSI` e `STE100_RSI` in base alla skill attiva.
* In `Mode C`, l'agente esegue `scripts/rsi_convergence_engine.py --vibe-check` per completare la convergenza in meno di `500` ms.

---

## 2. Governance, Memoria a 3 Livelli e Tracciamento

### [RULE-02.3.1] / [RULE-05.4] HUB_PREFLIGHT_HEALTH_CHECK_DIRECTIVE
* L'agente esegue `scripts/preflight_health_check.py` solo per manutenzione, CI/CD (`--check-only`) o cold start manuale.
* All'avvio ordinario, l'agente esegue solo `scripts/nk_session_bootstrap.py` (`[RULE-00.4]`).

### [RULE-02.4] / [RULE-04.3] RESEARCH_FIRST_AND_COVE_MANDATE
* In caso di incertezza, l'agente verifica la documentazione aggiornata e applica la Chain-of-Verification (CoVe).

### [RULE-02.5] / [RULE-02.6] TWO_STAGE_GROUNDING_AND_CLEAN_PROMPT
* Prima di modificare il codice, il Builder legge `nk_genome/implementation_plan.md` (Stage A) e i file target (Stage B).
* Tutti i prompt interni usano percorsi assoluti con slash standard e zero comandi slash non supportati.

### [RULE-02.8] CONTEXT_COMPACTION_AND_HANDOFF_MANDATE
* Alla soglia di guardia (`70` step standard, `150` step argon o `200.000` token reali), l'agente raccomanda `/compact` ed esegue `scripts/nk_session_handoff.py`.

### [RULE-03] AUTO_BRIEF_SWARM_FSM_A_5_TURNI
* I 5 turni sono: Turno 1 (Draft Synthesis), Turno 2 (Attack Swarm), Turno 3 (Refine Architecture), Turno 4 (1:1 Plan Alignment) e Turno 5 (Final Handoff).

### [RULE-05.1] CHANGELOG_SSOT
* `nk_genome/PATCH_NOTES.md` è la Single Source of Truth del changelog ed è sincronizzato con `PATCH_NOTES.md`.

### [RULE-05.2] 3_TIER_MEMORY_MANAGEMENT
* `scripts/memory_3tier_engine.py` gestisce `ARCH`, `SEC`, `OPS`, `DEVX` con cap Tier-1 di `350` token (`1.200` argon) e RRF ($k=60$).

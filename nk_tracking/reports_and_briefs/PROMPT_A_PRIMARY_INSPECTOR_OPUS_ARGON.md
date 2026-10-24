@[conversation:"<INSERISCI_QUI_LA_CONVERSAZIONE_STRESS_TEST_NK_BANDI>"]
[MODALITA GOAL-DRIVEN SOVRANA : TEMPLATE 11 | AUDIT FORENSE PRIMARIO & PIANO ARCHITETTURALE]
Progetto Target Ispezionato (`<P>`): `G:/Il mio Drive/NK_External_Projects/NK-Bandi`
Ambiente di Orchestrazione Sotto Esame: `NK-Hub v4.3.0-Super-Plan-Triad-RSI` (`g:/Il mio Drive/Antigravity`)
Conversazione Storica di Baseline (Pre-Cura): `1fe4c8b9-9a66-4010-9d32-b6ee6515d5a1`
Milestone Anchor ID: `NK-MS-20261024-PRIMARY-FORENSIC-INSPECTOR-v4.3.0`

Opera come Ispettore Forense e Architetto di Sistema Indipendente (`Mode D` in sola lettura sulla produzione, Orchestratore Sovrano L3 `NK-Session-Controller`) in topologia 2-Tier Hub-and-Spoke (`[RULE-01]`, massimo 12 chiamate dirette per fase).
Il tuo compito e analizzare a fondo la conversazione allegata — in cui l'ambiente `NK-Hub` potenziato ha eseguito lo Stress-Test Multilivello, il ciclo Tensor-RSI e la Cross-Validation (`Holdout Set B`) su `NK-Bandi` — per verificare come si e comportato l'ambiente, controllare se tutti i problemi storici sono stati realmente risolti o se sono emerse nuove fragilita, e progettare un `implementation_plan.md` completo di potenziamento e bonifica (senza modificare direttamente i file di produzione).

### FASE 0 : BOOTSTRAP, LOCALIZZAZIONE TRANSCRIPT E REGISTRAZIONE AUDITOR ([RULE-00.4] & [RULE-01])
1. Esegui `python scripts/nk_session_bootstrap.py --conversation-id <ID_CORRENTE>`.
2. Localizza il transcript della conversazione allegata (`<ID_CONV_STRESS_BANDI>`) tramite:
   `python scripts/nk_transcript_tools.py locate --conversation-id <ID_CONV_STRESS_BANDI>`.
3. Registra i sub-agenti ispettivi tramite `define_subagent(Name="NK-Primary-Transcript-Auditor", EnableWriteTools=True, EnableSubagentTools=False)` e `define_subagent(Name="NK-Primary-GroundTruth-Auditor", EnableWriteTools=True, EnableSubagentTools=False)` (abilitati a scrivere report in `scratch/` e, in caso di futura esecuzione, in `.staging/` con promozione `win32_2pc_engine.py --promote-staging --repo-root`).

### FASE 1 : INDAGINE FORENSE PARALLELA A 3 SHARD (SOLA LETTURA SULLA PRODUZIONE)
Delega in parallelo via `invoke_subagent` (includendo `<env_capsule>` con `$env:PYTHONUTF8="1"`, `python -m pytest` e limite `< 1.800` caratteri `[RULE-SWARM-HYGIENE]`) 3 sub-agenti in sola lettura sulla produzione e imposta `schedule(DurationSeconds=180, TimerCondition="any")`:

- **Shard 1 — Analisi Forense del Transcript Principale e dei Sub-Agenti (`NK-Primary-Transcript-Auditor`):**
  * Esegui `python scripts/nk_transcript_tools.py compliance --transcript "<PATH_TRANSCRIPT_TARGET>"` e `python scripts/nk_transcript_tools.py evidence --transcript "<PATH_TRANSCRIPT_TARGET>"`.
  * Ispeziona tutti gli step del thread principale e i transcript dei sub-agenti invocati (`invoke_subagent`) verificando:
    1. Saturazione di contesto e numero di step del thread principale (rispetto al tetto di guardia e alla sessione storica `1fe4c8b9`);
    2. Rispetto di `[RULE-REACTIVE-SILENCE]` (zero cicli di polling con `manage_task(Action="status")` o `manage_subagents(Action="list")`);
    3. Rispetto di `[RULE-00]` e funzionamento di `scripts/nk_hook_gate.py` (zero scritture dirette su `src_app/` o `tests/` fuori da `.staging/`);
    4. Corretta registrazione dei worker con `define_subagent(EnableWriteTools=True, EnableSubagentTools=False)` e rispetto del limite `< 1.800` caratteri nei `send_message`;
    5. Uso reale di `scripts/win32_2pc_engine.py --promote-staging --repo-root` per ogni promozione e di `scripts/safe_cleanup_dev_servers.py` per i server;
    6. Eventuali errori di tool, comandi falliti, attriti operativi o deviazioni dalle regole di `AGENTS.md`.
  * Salva l'analisi dettagliata in `scratch/primary_audit_shard1_transcript.md`.

- **Shard 2 — Verifica Ground-Truth di `NK-Bandi` e Valutazione dello Stress-Test + RSI (`NK-Primary-GroundTruth-Auditor`):**
  * Ispeziona lo stato reale del progetto `G:/Il mio Drive/NK_External_Projects/NK-Bandi` al termine dello stress-test:
    1. Esegui `python scripts/nk_transcript_tools.py oracle-lock verify --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" --lock-file "G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/oracle_lock.json"` per verificare che nessun test sia stato manomesso (`[RULE-ORACLE-LOCK]`);
    2. Verifica che il catalogo (`data/snapshots/catalog_snapshot.json` e `src_app/data/catalog_snapshot.json`) abbia `0` date sintetiche `rolling_dates`, `0` record artificiali (`[RULE-DATA-PROVENANCE]`) e `100%` di validazione `CanonicalGrantModel`;
    3. Valuta la qualita dei test generati in `Batteria A` (Livelli 1, 2, 3, 4) e nella batteria differenziale `Holdout Set B`, verificando se le correzioni applicate dal ciclo Tensor-RSI in `src_app/` sono strutturali o superficiali;
    4. Esegui `python scripts/ast_guard_validator.py --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app"`, `python -m pytest "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" -q` e `python scripts/rsi_convergence_engine.py --verify --root "G:/Il mio Drive/NK_External_Projects/NK-Bandi" --benchmark-suite "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests"`.
  * Salva l'analisi in `scratch/primary_audit_shard2_bandi_groundtruth.md`.

- **Shard 3 — Audit Strutturale dell'Ambiente `NK-Hub` (`NK-Primary-GroundTruth-Auditor`):**
  * Valuta come si sono comportati gli script core di `g:/Il mio Drive/Antigravity/scripts/` (`vibe_sprint_router.py`, `nk_hook_gate.py`, `nk_transcript_tools.py`, `win32_2pc_engine.py`, `rsi_convergence_engine.py`, `dast_sandbox_runner.py`, `nk_session_handoff.py`) durante la sessione sotto esame.
  * Individua qualsiasi collo di bottiglia, falso positivo/negativo, lacuna di copertura o opportunita di potenziamento ulteriore per `NK-Hub`.
  * Salva l'analisi in `scratch/primary_audit_shard3_nkhub_architecture.md`.

### STOP_GATE 1 : CONSOLIDAMENTO DIAGNOSI E GENERAZIONE DELL'IMPLEMENTATION PLAN FINALE
1. Unisci le evidenze dei 3 Shard e calcola il vettore difetti $\Delta_{\text{audit}}$ (`RSIDefectVector`).
2. Crea l'artefatto finale `implementation_plan.md` (con `RequestFeedback: true`) strutturato in due piste rigorosamente separate:
   - **Sezione 1 — Pagella Forense Prima/Dopo (`1fe4c8b9` vs Nuova Sessione Stress-Test):** tabella quantitativa e verdetto per ciascuno dei meccanismi di `NK-Hub v4.3.0` (cosa ha funzionato al `100%`, cosa ha mostrato attriti e quali nuovi bug sono stati scoperti e risolti in `NK-Bandi`);
   - **Sezione 2 — Track 1 (`NK-Hub` Enhancements):** piano dettagliato (con file target, diff architetturali e comandi di verifica in `.staging/` + `win32_2pc_engine.py`) per correggere o potenziare qualsiasi debolezza residua dell'ambiente `NK-Hub`;
   - **Sezione 3 — Track 2 (`NK-Bandi` Enhancements):** piano dettagliato per risolvere eventuali fragilita residue emerse dallo stress-test su `NK-Bandi` (con `oracle-lock` e ciclo Tensor-RSI).
3. Presenta all'utente il riepilogo esecutivo completo dell'ispezione e attendi istruzioni (non applicare modifiche ai file di produzione prima dell'approvazione).

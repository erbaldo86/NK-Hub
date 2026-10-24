@[conversation:"<INSERISCI_QUI_LA_CONVERSAZIONE_STRESS_TEST_NK_BANDI>"]
[MODALITA GOAL-DRIVEN SOVRANA : TEMPLATE 11 | AUDIT FORENSE POST-HOC & BENCHMARK PRIMA/DOPO]
Progetto Target Ispezionato (`<P>`): `G:/Il mio Drive/NK_External_Projects/NK-Bandi`
Ambiente Sotto Esame: `NK-Hub v4.3.0-Super-Plan-Triad-RSI` (`g:/Il mio Drive/Antigravity`)
Conversazioni Storiche di Benchmark (Baseline Pre-Cura):
- Sessione Originaria `Bandi` (Pre-Hardening): `1fe4c8b9-9a66-4010-9d32-b6ee6515d5a1` (`144` step, `24` cicli di polling, `22` scritture fuori `.staging/`, `64` date sintetiche `rolling_dates`, `0` commit 2PC).
- Audit Forensi Storici di Riferimento: `Opus` (`fcc613c0-656a-453c-a128-1097ea199eeb`) e `Argon` (`b4992f7f-e45b-4897-b85d-1183c8592965`).
- Super Implementation Plan Applicato: `a29215fb-76ad-40df-940b-a1cab2a64686` (`SP-WS0 .. SP-WS13`).
Milestone Anchor ID: `NK-MS-20261024-FORENSIC-POSTHOC-EVALUATION-v4.3.0`

Opera come Ispettore Forense Esterno Indipendente (`Mode D` / `Mode A` in caso di piano correttivo residuo) in topologia 2-Tier Hub-and-Spoke (`[RULE-01]`, massimo 12 chiamate dirette per fase). Il tuo compito e analizzare a fondo la conversazione allegata (in cui `NK-Hub v4.3.0` ha eseguito lo Stress-Test Multilivello + Loop Tensor-RSI + Holdout Cross-Validation su `NK-Bandi`) e verificare empiricamente se tutti i 15 problemi strutturali rilevati da Opus e Argon sono stati effettivamente eliminati, corretti o potenziati, oppure se sono emerse nuove deviazioni.

### FASE 0 : BOOTSTRAP, LOCALIZZAZIONE TRANSCRIPT E REGISTRAZIONE AUDITOR ([RULE-00.4] & [RULE-01])
1. Esegui `python scripts/nk_session_bootstrap.py --conversation-id <ID_CORRENTE>`.
2. Localizza il transcript della conversazione allegata (`<ID_CONV_TARGET>`) senza usare glob ciechi (`G1-02`), eseguendo:
   `python scripts/nk_transcript_tools.py locate --conversation-id <ID_CONV_TARGET>`.
3. Registra i sub-agenti specializzati tramite `define_subagent(Name="NK-Forensic-Transcript-Auditor", EnableWriteTools=True, EnableSubagentTools=False)`, `define_subagent(Name="NK-Forensic-Codebase-Auditor", EnableWriteTools=True, EnableSubagentTools=False)` e `define_subagent(Name="NK-Forensic-RSI-Builder", EnableWriteTools=True, EnableSubagentTools=False)` (quest'ultimo solo per eventuali patch residue in `.staging/`).

### FASE 1 : ISPEZIONE FORENSE PARALLELA A 3 SHARD (TRANSCRIPT + GROUND-TRUTH + CONFRONTO OPUS/ARGON)
Delega in parallelo via `invoke_subagent` (includendo `<env_capsule>` con `$env:PYTHONUTF8="1"`, `python -m pytest` e limite `< 1.800` caratteri `[RULE-SWARM-HYGIENE]`) 3 sub-agenti di audit in sola lettura sulla produzione e imposta `schedule(DurationSeconds=180, TimerCondition="any")`:

- **Shard 1 — Analisi Telemetrica e Conformita Regole del Transcript (`NK-Forensic-Transcript-Auditor`):**
  * Esegui `python scripts/nk_transcript_tools.py compliance --transcript "<PATH_TRANSCRIPT_TARGET>"` e `python scripts/nk_transcript_tools.py evidence --transcript "<PATH_TRANSCRIPT_TARGET>"`.
  * Analizza anche i transcript dei sub-agenti invocati nella sessione target (`invoke_subagent`) e misura:
    1. Numero totale di step del thread principale (Target: `< 45` step vs `144` della sessione storica `1fe4c8b9`);
    2. Chiamate di polling `manage_task(Action="status")` o `manage_subagents(Action="list")` (Target `[RULE-REACTIVE-SILENCE]`: `0` cicli di polling vs `24` storici);
    3. Scritture dirette con `write_file`/`edit_file` su `src_app/` o `tests/` fuori da `.staging/` (Target `[RULE-00]` + `nk_hook_gate.py`: `0` vs `22` storiche);
    4. Utilizzo effettivo di `define_subagent(EnableWriteTools=True)` (`SP-WS3` / `G3-01`) e rispetto del tetto `< 1.800` caratteri nei `send_message` (`[RULE-SWARM-HYGIENE]`);
    5. Esecuzione reale dei commit atomici con `scripts/win32_2pc_engine.py --promote-staging --repo-root` (`0` bypass);
    6. Assenza di comandi `python -c` multi-riga falliti su PowerShell o `view_file` inesistenti.
  * Salva il report telemetrico in `scratch/forensic_shard1_transcript_telemetry.json`.

- **Shard 2 — Ispezione Ground-Truth di `NK-Bandi` e Integrita Anti-Goodhart (`NK-Forensic-Codebase-Auditor`):**
  * Verifica lo stato fisico post-sessione di `G:/Il mio Drive/NK_External_Projects/NK-Bandi`:
    1. Integrita `oracle_lock.json` (`[RULE-ORACLE-LOCK]`): esegui `python scripts/nk_transcript_tools.py oracle-lock verify --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" --lock-file "G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/oracle_lock.json"` e controlla che nessun test preesistente sia stato indebolito per far passare la suite;
    2. Integrita Dati (`[RULE-DATA-PROVENANCE]`): verifica su `data/snapshots/catalog_snapshot.json` e `src_app/data/catalog_snapshot.json` che ci siano `0` date sintetiche `rolling_dates` (`C-01`), `0` record artificiali (`C-02`) e `100%` di validazione `CanonicalGrantModel`;
    3. Efficacia Reale dello Stress-Test e della Cross-Validation (`Batteria A` vs `Holdout Set B`): controlla i report generati in `nk_tracking/`, i nuovi test in `tests/test_multilevel_stress_battery_a.py` e `tests/test_multilevel_holdout_battery_b.py`, e verifica se i bug scoperti sono stati corretti strutturalmente nel codice di `src_app/`;
    4. Esegui `python scripts/ast_guard_validator.py --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app"`, `python -m pytest "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" -q` e `python scripts/rsi_convergence_engine.py --verify --root "G:/Il mio Drive/NK_External_Projects/NK-Bandi" --benchmark-suite "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests"`.
  * Salva il report in `scratch/forensic_shard2_groundtruth_bandi.json`.

- **Shard 3 — Matrice di Verifica a 15 Dimensioni rispetto a Opus e Argon (`NK-Forensic-Transcript-Auditor`):**
  * Confronta punto per punto i 15 Workstream del Super-Piano (`SP-WS0 .. SP-WS13` + `C-01..D-02`, documentati in `nk_tracking/reports_and_briefs/TAS_Report_NK_Hub_v6_0_20261024.md` e `TAS_Report_NK_Bandi_v76_Remediated_20261024.md`) con il comportamento osservato nella sessione target.
  * Per ciascuna delle 15 dimensioni assegna un verdetto empirico: `RISOLTO_E_VERIFICATO`, `PARZIALE` o `REGRESSIONE`, motivando con citazioni esatte degli step del transcript e dei file.
  * Salva la matrice in `scratch/forensic_shard3_opus_argon_matrix.md`.

### STOP_GATE 1 : VALUTAZIONE VETTORE DIFETTI RESIDUI $\Delta_{\text{audit}}$ E PIANO D'AZIONE
1. Unisci i risultati dei 3 Shard e calcola il vettore difetti forense $\Delta_{\text{audit}}$ (`RSIDefectVector`).
2. Compila l'artefatto `implementation_plan.md` (con `RequestFeedback: true` se $\Delta_{\text{audit}} > 0$) contenente:
   - **Tabella Benchmark Comparativa Prima/Dopo:** `Sessione Storica 1fe4c8b9 (Pre-Cura)` vs `Nuova Sessione Stress-Test (Post-Cura v4.3.0)` su tutti i KPI (step, contesto, polling, isolamento `.staging/`, 2PC, SAST, test, integrita dati);
   - **Pagella dei 15 Punti di Opus & Argon:** quali difetti sono stati definitivamente debellati al `100%` e come hanno reagito i nuovi meccanismi (`nk_hook_gate.py`, `nk_transcript_tools.py`, `oracle-lock`, `Holdout Set B`);
   - **Piano di Potenziamento Ultra-Residuo (se $\Delta_{\text{audit}} > 0$):** specifica chirurgica di eventuali micro-correzioni residue per `NK-Hub` o `NK-Bandi`.

### FASE 2 : EVENTUALE CICLO TENSOR-RSI RESIDUO IN `.staging/` E REPORT FINALE (`[RULE-EVIDENCE]`)
1. Se e solo se $\Delta_{\text{audit}} > 0$ e l'utente approva il piano:
   - Blocca gli oracoli di test con `python scripts/nk_transcript_tools.py oracle-lock create --target "tests" --lock-file "nk_tracking/oracle_lock.json"`;
   - Delega a `NK-Forensic-RSI-Builder` le correzioni esclusivamente in `.staging/`, verifica con `ast_guard_validator.py`, `dast_sandbox_runner.py` e `safe_cleanup_dev_servers.py`, e promuovi con `python scripts/win32_2pc_engine.py --promote-staging --repo-root "<ROOT_TARGET>"`;
   - Verifica la convergenza finale con `python scripts/rsi_convergence_engine.py --verify --root "<ROOT_TARGET>" --benchmark-suite "<ROOT_TARGET>/tests"`.
2. Consegna al termine il **Report Ispettivo Finale Post-Hoc (`TAS_Forensic_PostHoc_Comparison_Report.md`)** con tutti i verdetti e le metriche certificate.

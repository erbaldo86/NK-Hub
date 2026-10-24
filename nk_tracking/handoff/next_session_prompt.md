[MODALITA GOAL-DRIVEN SOVRANA : TEMPLATE 11 | CRV 4.0 & 2-TIER SWARM]
Progetto Target (`<P>`): `G:/Il mio Drive/NK_External_Projects/NK-Bandi`
Stato Attuale Verificato (Handoff Anchor): `v7.6.0-Remediated` (`4.548` bandi validati su `CanonicalGrantModel`, `142/142` test `PASS`, `oracle_lock.json` attivo con SHA-256 `655a577ec748`, `.staging/` pronta).
Milestone Anchor ID: `NK-MS-20261024-BANDI-MULTILEVEL-STRESS-RSI-v7.7.0`

Opera esclusivamente come Orchestratore Sovrano L3 (`NK-Session-Controller` e `NK-Master-Hub`) in topologia 2-Tier Hub-and-Spoke (`[RULE-01]`, massimo 12 chiamate dirette per fase). Non fondere mai nel thread principale i ruoli di Auditor e Builder e mantieni il contesto principale sotto 45 step totali.

### FASE 0 : BOOTSTRAP, GROUNDING HANDOFF E REGISTRAZIONE WORKER ([RULE-00.4] & [RULE-01])
1. Esegui `python scripts/nk_session_bootstrap.py --conversation-id <ID_CORRENTE> --project-root "G:/Il mio Drive/NK_External_Projects/NK-Bandi"`.
2. Leggi il manifesto di handoff `G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/HANDOFF_STRESS_RSI_V76.md` e verifica l'integrita iniziale con:
   `python scripts/nk_transcript_tools.py oracle-lock verify --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" --lock-file "G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/oracle_lock.json"`.
3. Registra subito i sub-agenti operativi tramite `define_subagent(Name="NK-Bandi-Builder", EnableWriteTools=True, EnableSubagentTools=False)` e `define_subagent(Name="NK-Bandi-Stress-Auditor", EnableWriteTools=True, EnableSubagentTools=False)` per montare i tool di shell e scrittura in `.staging/` e `%TEMP%\nk_sandbox_*`.

### FASE 1 : STRESS-TEST MULTILIVELLO A 3 SHARD PARALLELI — BATTERIA A (MISURA ONESTA MEASURE-FIRST)
Delega in parallelo via `invoke_subagent` (includendo `<env_capsule>` con `$env:PYTHONUTF8="1"`, `python -m pytest` e limite messaggio `< 1.800` caratteri `[RULE-SWARM-HYGIENE]`) 3 sub-agenti `NK-Bandi-Stress-Auditor` (in sola lettura sulla produzione di `NK-Bandi`) e imposta `schedule(DurationSeconds=180, TimerCondition="any")`:
- **Shard 1 (Livello 1 Semplici & Edge-Case Lessicali + Livello 2 Ricerche Elaborate Multi-Intento NLP):**
  * *Livello 1 (Ricerche Semplici & Edge-Case Lessicali):* Esegui 20 test su keyword singole, acronimi (`PNRR`, `ISI INAIL`, `ZES`, `Transizione 5.0`, `Nuova Sabatini`, `SIMEST`, `ON Oltre Nuove Imprese`), refusi/typo, maiuscole/minuscole, accenti, query vuote, stringhe molto lunghe, caratteri speciali/Unicode e paginazione limite (`offset`/`limit`).
  * *Livello 2 (Ricerche Elaborate Multi-Intento NLP):* Esegui 20 query complesse in linguaggio naturale con vincoli incrociati (regione + forma societaria + codice ATECO + tipo contributo fondo perduto/tasso agevolato + importo minimo/massimo + stato aperto), sinonimi settoriali e macro-aree geografiche (`Mezzogiorno`, `Nord-Est`, `Centro`, `Isole`).
  * Misura e registra in `G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/stress_wave1_L1_L2_report.json` ogni anomalia di pertinenza, ranking, latenza (`p95 > 250ms`), falsi positivi o mismatch geografico/settoriale.
- **Shard 2 (Livello 3 Multi-Filtro Parametrico, Concorrenza API & Coerenza Matematica):**
  * Esegui in sandbox 25 combinazioni multi-punto a 5-7 filtri simultanei (`regione` + `settore` + `tipo_agevolazione` + `importo` + `stato` + `ente` + `beneficiari`), stress test concorrenti sulle rotte FastAPI (`/api/search`, `/api/grants`, `/api/health`) e verifica di coerenza matematica esatta tra KPI header, elenco filtrato ed esportazione CSV.
  * Verifica che zero bandi con `stato="CHIUSO"` o scadenza passata compaiano tra i bandi attivi e salva il report in `G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/stress_wave1_L3_api_report.json`.
- **Shard 3 (Livello 4 Browser E2E Live, Console, Network & DOM):**
  * Esegui `python scripts/safe_cleanup_dev_servers.py`, avvia il server di `NK-Bandi` con `IsDaemon=true`, verifica `GET /api/health == 200` (`[RULE-EVIDENCE]`) ed esegui i test E2E su UI, modali di dettaglio bando, filtri combinati rapidi, reset stato ed export CSV (`take_snapshot`, `click`, `list_network_requests`, `list_console_messages`).
  * Salva il report in `G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/stress_wave1_L4_e2e_report.json` e ferma il server al termine.

### STOP_GATE 1 : CONSOLIDAMENTO DIFETTI E ORACLE-LOCK (`[RULE-ORACLE-LOCK]` & `[RULE-DATA-PROVENANCE]`)
1. Raccogli i 3 report della Batteria A e calcola il vettore difetti iniziale $\Delta_0$ (`RSIDefectVector`).
2. **Divieto Assoluto Anti-Goodhart (`[RULE-DATA-PROVENANCE]`):** E severamente vietato alterare date di scadenza o inserire bandi sintetici nel catalogo per far passare i test. Ogni bug emerso deve essere tradotto in un test deterministico reale dentro `G:/Il mio Drive/NK_External_Projects/NK-Bandi/.staging/tests/test_multilevel_stress_battery_a.py`, promosso e congelato con:
   `python scripts/nk_transcript_tools.py oracle-lock create --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" --lock-file "G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/oracle_lock.json"`.

### FASE 2 : CICLO TENSOR-RSI DI CORREZIONE IN `.staging/` E COMMIT 2PC (`DOM-03 -> DOM-04 -> DOM-01`)
Se $\Delta_0 > 0$:
1. Delega a `NK-Bandi-Builder` via `invoke_subagent` la correzione strutturale dei bug individuati:
   - Leggi preventivamente `src_app/models/cgm.py` e i moduli target (`[RULE-02.5]`).
   - Scrivi tutte le correzioni esclusivamente dentro `G:/Il mio Drive/NK_External_Projects/NK-Bandi/.staging/src_app/`.
   - Esegui `python scripts/ast_guard_validator.py --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/.staging/src_app"` e lo shadow run con `python scripts/dast_sandbox_runner.py --overlay-staging "G:/Il mio Drive/NK_External_Projects/NK-Bandi"`.
2. Verifica che gli hash dei test non siano stati manomessi con `python scripts/nk_transcript_tools.py oracle-lock verify --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" --lock-file "G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/oracle_lock.json"`.
3. Promuovi atomicamente le correzioni con:
   `python scripts/win32_2pc_engine.py --promote-staging --repo-root "G:/Il mio Drive/NK_External_Projects/NK-Bandi"`.

### FASE 3 : CROSS-VALIDATION CON BATTERIA DIFFERENZIALE INEDITA (HOLDOUT SET B) E RICORSIONE RSI
Per verificare che le correzioni della Fase 2 siano generali, efficienti e prive di overfitting:
1. Delega a una nuova istanza `NK-Bandi-Stress-Auditor` l'esecuzione di una **Batteria Differenziale Inedita (`Holdout Set B`)**, completamente disgiunta dalla Batteria A:
   - Nuove query semplici e acronimi non usati in Fase 1 (`Resto al Sud`, `Smart&Start`, `Brevetti+`, `Marchi+`, `Disegni+`, `Fondo Impresa Femminile`, `FESR`, `FEASR`);
   - Nuove frasi NLP multi-vincolo su regioni, fasce d'importo, forme giuridiche e codici ATECO differenti rispetto alla Batteria A;
   - Nuove combinazioni parametriche a 6 filtri incrociati, casi limite di ordinamento (`scadenza`, `importo`, `rilevanza`) e verifica tempi di risposta.
2. **Regola di Ricorsione RSI (`Max 3 Cicli`):**
   - Se la Batteria Differenziale `Holdout Set B` individua nuovi bug o regressioni ($\Delta_{\text{holdout}} > 0$), aggiungi i nuovi casi di test in `tests/test_multilevel_holdout_battery_b.py`, aggiorna `oracle_lock.json`, riesegui la **Fase 2 (Ciclo Tensor-RSI in `.staging/` + Shadow Run + Commit 2PC)** e ripeti la verifica differenziale fino a convergenza $\Delta_k = 0$ e $Q(S_k) = 100.0$.

### FASE 4 : CONTROLLO FINALE TAS v4.0 E SINCRONIZZAZIONE SCRIBE (`[RULE-EVIDENCE]`)
1. Esegui nel turno finale i comandi reali di certificazione (`exit code 0`):
   - `python scripts/ast_guard_validator.py --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app"`
   - `python -m pytest "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" -q`
   - `python scripts/rsi_convergence_engine.py --verify --root "G:/Il mio Drive/NK_External_Projects/NK-Bandi" --benchmark-suite "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests"`
2. Delega a `NK-Scribe-Agent` l'aggiornamento di `PATCH_NOTES.md` (in prepend), `nk_genome/`, `quality_baseline.json` e la generazione del report finale `TAS_Report_NK_Bandi_v77_Stress_RSI.md`.

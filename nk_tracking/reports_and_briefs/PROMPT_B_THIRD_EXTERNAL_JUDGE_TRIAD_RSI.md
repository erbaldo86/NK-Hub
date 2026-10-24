@[conversation:"Opus"] @[conversation:"Argon"] @[conversation:"Bandi"]
[MODALITA GOAL-DRIVEN SOVRANA : TEMPLATE 11 | TERZO ISPETTORE OBIETTIVO ESTERNO & FUSIONE TRIAD-RSI]
Progetto Target (`<P>`): `g:/Il mio Drive/Antigravity` (`NK-Hub`) & `G:/Il mio Drive/NK_External_Projects/NK-Bandi` (`NK-Bandi`)
Coordinate Esatte delle Conversazioni Allegate (Zero-Glob Grounding):
- **Modello A (`Opus`):** Conversation ID `bcb5d16e-70c2-4918-8457-e3bdc328df68`
  * Brain Dir: `C:/Users/erbal/.gemini/antigravity/brain/bcb5d16e-70c2-4918-8457-e3bdc328df68`
  * Transcript: `C:/Users/erbal/.gemini/antigravity/brain/bcb5d16e-70c2-4918-8457-e3bdc328df68/.system_generated/logs/transcript.jsonl`
- **Modello B (`Argon`):** Conversation ID `406f7652-ea7d-443b-ab45-d290d034fdcd`
  * Brain Dir: `C:/Users/erbal/.gemini/antigravity/brain/406f7652-ea7d-443b-ab45-d290d034fdcd`
  * Transcript: `C:/Users/erbal/.gemini/antigravity/brain/406f7652-ea7d-443b-ab45-d290d034fdcd/.system_generated/logs/transcript.jsonl`
- **Conversazione Oggetto dell'Audit (`Bandi` — Stress-Test Multilivello + RSI):** Conversation ID `191ef988-3771-44e9-8a16-cfdb9da73fc8`
  * Brain Dir: `C:/Users/erbal/.gemini/antigravity/brain/191ef988-3771-44e9-8a16-cfdb9da73fc8`
  * Transcript: `C:/Users/erbal/.gemini/antigravity/brain/191ef988-3771-44e9-8a16-cfdb9da73fc8/.system_generated/logs/transcript.jsonl`
- **Baseline Storiche di Confronto:**
  * Sessione `Bandi` Originaria (Pre-Cura): `1fe4c8b9-9a66-4010-9d32-b6ee6515d5a1`
  * Sessione Super-Plan Round 1: `a29215fb-76ad-40df-940b-a1cab2a64686`
Milestone Anchor ID: `NK-MS-20261024-TRIAD-EXTERNAL-JUDGE-SUPER-PLAN-ROUND2`

In queste due conversazioni (`Opus` `bcb5d16e-70c2-4918-8457-e3bdc328df68` e `Argon` `406f7652-ea7d-443b-ab45-d290d034fdcd`), i due modelli hanno svolto la stessa attivita di ispezione forense sulla conversazione `Bandi` (`191ef988-3771-44e9-8a16-cfdb9da73fc8`).
Tu devi agire come **Terzo Ispettore Obiettivo Esterno e Giudice Arbitro Indipendente** (`NK-Session-Controller`) in topologia 2-Tier Hub-and-Spoke (`[RULE-01]`, massimo 12 chiamate dirette per fase):
1. Prendi, analizza e valuta gli `implementation_plan.md` finali e i report forensi creati da `Opus` (`bcb5d16e`) e da `Argon` (`406f7652`);
2. Verifica oggettivamente sul codice reale (`NK-Hub` e `NK-Bandi`) e sul transcript di `Bandi` (`191ef988`) chi dei due ha ragione su ogni punto;
3. Fai anche tu come Terzo Valutatore le tue valutazioni e considerazioni originali dove servono a migliorare ulteriormente il piano finale;
4. Crea ed esegui un processo deterministico di **Sintesi Triad-RSI** che unisca e migliori tutte le idee, i consigli e i potenziamenti emersi da `Opus` + `Argon` + la tua elaborazione in un unico **Super Implementation Plan (`implementation_plan.md`)**, mantenendo rigorosamente separate l'attivita di `NK-Hub` e l'attivita di `NK-Bandi`;
5. Mostrami alla fine il Super Implementation Plan e un **Report Comparativo Completo** che spieghi per ogni punto da chi e stata scelta l'opzione migliore (`Opus`, `Argon` o `3° Ispettore`) e per quale motivo tecnico.

### FASE 0 : BOOTSTRAP, VERIFICA TRANSCRIPT E REGISTRAZIONE AUDITOR ([RULE-00.4] & [RULE-01])
1. Esegui `python scripts/nk_session_bootstrap.py --conversation-id <ID_CORRENTE>`.
2. Verifica subito la presenza dei tre transcript con:
   - `python scripts/nk_transcript_tools.py locate --conversation-id bcb5d16e-70c2-4918-8457-e3bdc328df68`
   - `python scripts/nk_transcript_tools.py locate --conversation-id 406f7652-ea7d-443b-ab45-d290d034fdcd`
   - `python scripts/nk_transcript_tools.py locate --conversation-id 191ef988-3771-44e9-8a16-cfdb9da73fc8`
3. Registra i sub-agenti tramite `define_subagent(Name="NK-Triad-Plan-Comparator", EnableWriteTools=True, EnableSubagentTools=False)`, `define_subagent(Name="NK-Triad-GroundTruth-Verifier", EnableWriteTools=True, EnableSubagentTools=False)` e `define_subagent(Name="NK-Triad-RSI-Builder", EnableWriteTools=True, EnableSubagentTools=False)` (per eventuale esecuzione futura in `.staging/` con `win32_2pc_engine.py --promote-staging --repo-root`).

### FASE 1 : ANALISI TRIADICA PARALLELA A 3 SHARD (OPUS vs ARGON vs GROUND-TRUTH DI BANDI `191ef988`)
Delega in parallelo via `invoke_subagent` (includendo `<env_capsule>` con `$env:PYTHONUTF8="1"`, `python -m pytest` e limite `< 1.800` caratteri `[RULE-SWARM-HYGIENE]`) 3 sub-agenti in sola lettura sulla produzione e imposta `schedule(DurationSeconds=180, TimerCondition="any")`:

- **Shard 1 — Estrazione e Confronto Diretto `Opus (bcb5d16e)` vs `Argon (406f7652)` (`NK-Triad-Plan-Comparator`):**
  * Leggi integralmente gli artefatti `implementation_plan.md` e i file in `scratch/` dentro `C:/Users/erbal/.gemini/antigravity/brain/bcb5d16e-70c2-4918-8457-e3bdc328df68/` (`Opus`) e `C:/Users/erbal/.gemini/antigravity/brain/406f7652-ea7d-443b-ab45-d290d034fdcd/` (`Argon`), oltre ai rispettivi `transcript.jsonl`.
  * Mappa tutte le diagnosi, i KPI, le critiche e le soluzioni proposte da `Opus` e da `Argon` sia per `NK-Hub` sia per `NK-Bandi`.
  * Evidenzia convergenze, divergenze architetturali e punti ciechi di ciascuno dei due modelli.
  * Salva il report in `scratch/triad_r2_shard1_opus_vs_argon.md`.

- **Shard 2 — Verifica Empirica Ground-Truth su `Bandi (191ef988)`, `NK-Hub` e `NK-Bandi` (`NK-Triad-GroundTruth-Verifier`):**
  * Esegui `python scripts/nk_transcript_tools.py compliance --transcript "C:/Users/erbal/.gemini/antigravity/brain/191ef988-3771-44e9-8a16-cfdb9da73fc8/.system_generated/logs/transcript.jsonl"` e `python scripts/nk_transcript_tools.py evidence --transcript "C:/Users/erbal/.gemini/antigravity/brain/191ef988-3771-44e9-8a16-cfdb9da73fc8/.system_generated/logs/transcript.jsonl"`.
  * Verifica ogni affermazione di `Opus` e `Argon` direttamente sui file reali di `g:/Il mio Drive/Antigravity` (`NK-Hub`) e `G:/Il mio Drive/NK_External_Projects/NK-Bandi` (`NK-Bandi`):
    - `python scripts/nk_transcript_tools.py oracle-lock verify --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests" --lock-file "G:/Il mio Drive/NK_External_Projects/NK-Bandi/nk_tracking/oracle_lock.json"`
    - `python scripts/ast_guard_validator.py --target "G:/Il mio Drive/NK_External_Projects/NK-Bandi/src_app"`
    - `python scripts/rsi_convergence_engine.py --verify --root "G:/Il mio Drive/NK_External_Projects/NK-Bandi" --benchmark-suite "G:/Il mio Drive/NK_External_Projects/NK-Bandi/tests"`
  * Individua i miglioramenti originali di **Terzo Livello (3° Ispettore)** non visti ne da `Opus` ne da `Argon`.
  * Salva il report in `scratch/triad_r2_shard2_groundtruth.md`.

- **Shard 3 — Matrice Decisionale Multicriterio e Sintesi RSI (`NK-Triad-Plan-Comparator`):**
  * Costruisci la matrice comparativa completa valutando ogni opzione di `Opus`, `Argon` e `3° Ispettore` su 4 criteri oggettivi:
    1. *Fedelta Empirica alla Ground-Truth (`[RULE-EVIDENCE]`);*
    2. *Enforcement Deterministico (Prevenzione hard-gate vs sola documentazione);*
    3. *Isolamento Contesto e Rispetto Topologia 2-Tier (`[RULE-01]` + `.staging/` + `2PC`);*
    4. *Assenza di Effetti Collaterali e Zero Regressioni sui Golden Tests (`[RULE-01.10]`).*
  * Salva la matrice in `scratch/triad_r2_shard3_decision_matrix.md`.

### STOP_GATE 1 : MOTORE DI SINTESI TRIAD-RSI E COMPILAZIONE DEL SUPER IMPLEMENTATION PLAN
1. Esegui uno script deterministico di sintesi RSI in `scratch/` (usando `RSIDefectVector`, `compute_delta`, `compute_fitness` da `scripts/rsi_convergence_engine.py` e `safe_cleanup_dev_servers.py` se necessario) che calcoli la convergenza matematica dal piano di `Opus`, dal piano di `Argon` e dalla fusione Triad fino a $\Delta_k = 0$ e $Q(S_k) = 100.0$.
2. Genera l'artefatto finale `implementation_plan.md` (`RequestFeedback: true`) con:
   - **Parte 1 — Verdetto Ispettivo sul Comportamento dell'Ambiente `NK-Hub v4.3.0` nella Sessione `Bandi (191ef988)`:** confronto quantitativo rispetto alla sessione storica `1fe4c8b9` e bilancio dei problemi risolti;
   - **Parte 2 — Matrice Comparativa `Opus (bcb5d16e)` vs `Argon (406f7652)` vs `3° Ispettore`:** per ogni punto analizzato, chi ha vinto e la motivazione tecnica rigorosa della scelta;
   - **Parte 3 — Attivita 1 (Rifinitura `NK-Hub`) e Attivita 2 (Rifinitura `NK-Bandi`) Rigorosamente Separate:** tutte le specifiche tecniche pronte per l'esecuzione in `.staging/` + `oracle-lock` + `win32_2pc_engine.py`.
3. Presenta all'utente il Report Comparativo Completo del Super-Brief e attendi conferma prima di qualsiasi modifica.

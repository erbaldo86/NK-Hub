# Regolamento di Sistema: Ecosistema Antigravity (Nexus Keystone v5.2.0-STE100-Unified / v5.0.0-STE100-Unified / v4.8.0-STE100-Unified / v4.7.0-STE100-Unified / v3.0.0-STE100-Unified Compatible)

> **Ambito:** Regole vincolanti del workspace per tutti gli agenti, i sub-agenti e i nodi NK.  
> **Versione:** `v5.2.0-STE100-Unified` (`v5.2.0-RSI`, `v5.0.0-STE100-Unified`, `v4.8.0-STE100-Unified`, `v3.0.0-STE100-Unified` Compatible, `[RULE-STE100]`, `[RULE-RSI]`, `GT-01..GT-14`, `93/93` in `18` moduli e `68` Golden Tests).  
> **Milestone Anchor:** `NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI`.

---

## 0. Hard Execution Gate e Direttiva Linguistica

### [RULE-PROJECT-ISOLATION] EXTERNAL_PROJECT_DIRECTORY_MANDATE
* Nessun agente crea codice applicativo (`src_app/`, `app/`, `src/`) dentro `NK-Hub`.
* Ogni nuovo progetto risiede in una cartella esterna autonoma (`G:/Il mio Drive/Antigravity/NK_External_Projects/<Nome>/`).
* L'agente inizializza ogni progetto esterno tramite `scripts/external_project_scaffolder.py`.

### [RULE-00.4] SESSION_BOOTSTRAP_GATE
* L'agente esegue `scripts/nk_session_bootstrap.py` come primo passo di ogni sessione.
* La verifica `Fast-Stat` completa il controllo in meno di `120` ms (`< 30` ms su cache hit cross-conversazione `TTL 900s`).
* Lo script pulisce i file `.wal` scaduti, verifica la root, emette `ONBOARDING_BYPASS_VERIFIED` e imposta `NK_MODEL_PROFILE=argon`.
* Nessuna operazione procede se il bootstrap restituisce `FAIL`.

### [RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE
* I trigger di avvio sono: `"avvia ambiente nk"`, `"avvia nk hub"`, `"avvia nk"`, `"avvia hub"`, `"start nk"`, `"start hub"`, `"attiva nk"`, `"attiva ambiente nk"`.
* Quando l'utente invia un trigger di avvio, l'agente esegue un singolo passo CLI:
  1. Esegue il controllo `Fast-Stat` con `scripts/nk_session_bootstrap.py` in meno di `120` ms verificando `ONBOARDING_BYPASS_VERIFIED`.
  2. Mostra subito la Master Dashboard a 15 nodi (`[0]` fino a `[14]`) definita in `NK-Master-Hub/SKILL.md`.
  3. Include in calce la guida con `Modalità Diretta` (`[0]`..`[14]`) e `Modalità Goal-Driven` in linguaggio naturale.

### [RULE-00.6] / [RULE-00.7] / [RULE-01.11] / [RULE-01.12] META_PROMPT_GATE_AND_INTRINSIC_PROTOCOLS
* L'agente esegue `scripts/vibe_sprint_router.py --meta-prompt-gate` (`CONFIRM`) su ogni nuovo prompt utente non esente.
* Lo Specchio Concettuale L0 articola sempre tre sezioni nel campo `content`: Intenzione (`R1..Rn`), Come farlo e Regole.
* Nessun agente stampa il blocco interno `[META-PROMPT L0]` come quarto passaggio o invoca `ask_question` con `content` vuoto.
* Su `AWAIT_CONFIRM`, l'agente richiede conferma 1-Click tramite `ask_question` prima di eseguire il task.
* Dopo la conferma L0, l'agente prepara il Brief e richiede conferma su `nk_genome/implementation_plan.md` (`RequestFeedback: true`).
* Il Gate L0 e il `Template 11` attivano autonomamente `INTRINSIC_GOAL` (`/goal`), `INTRINSIC_BOOST` (`/boost`) e `INTRINSIC_PLAN` (`/plan`, `/implementation`).
* Nessun agente chiede all'utente di digitare manualmente `/goal`, `/boost`, `/plan` o `/implementation` (`AP-10`).
* L'agente valida ogni prompt generato con `scripts/nk_transcript_tools.py lint-prompt` prima della consegna all'utente.
* Le esenzioni anti-loop coprono conferme (`ok`, `procedi`, `Proceed`), `[0]..[14]`, `<env_capsule>`, `!diretto` (`L0_GATE_ONLY`) e trigger di avvio.
* Gli handoff `Template 12` (`PASSIVE_SESSION_STATE_HANDOFF`) attivano `STATE_HANDOFF_STANDBY` in sola lettura, vietando task autonomi (`AP-12`) e piste (`AP-13`).

### [RULE-00] / [RULE-00.1] / [RULE-00.2] / [RULE-00.3] ZERO_UNAUTHORIZED_WRITE_AND_STAGING_MANDATE
* Nessun agente modifica i file di produzione senza autorizzazione; ogni modifica al codice avviene dentro `.staging/` o `%TEMP%\nk_sandbox_*\`.
* I nodi Specifier e Auditor operano in sola lettura sulla produzione e scrivono solo in `nk_genome/` e `nk_tracking/reports_and_briefs/`.
* Il commit finale richiede la promozione atomica tramite `scripts/win32_2pc_engine.py`, seguita dalla sincronizzazione documentale di `NK-Scribe`.

### [RULE-STE100] ASD_STE100_TECHNICAL_ITALIAN_MANDATE
* Tutti i file `.md`, le docstring, i commenti, i commit e le risposte usano l'italiano tecnico ASD-STE100.
* Ogni frase operativa contiene al massimo 20 parole, usa la forma attiva e vieta i trattini d'inciso spaziati.

---

## 1. Topologia 2-Tier, Protocollo CRV 4.0, Onestà Epistemica e Motore RSI

### [RULE-REACTIVE-SILENCE] / [RULE-01.9] ANTI_POLLING_AND_HEARTBEAT_MANDATE
* Nessun agente esegue cicli di polling con `manage_task(Action="status")` o `manage_subagents(Action="list")`.
* Durante l'attesa di sub-agenti asincroni, l'orchestratore imposta `schedule(DurationSeconds=180, TimerCondition="any")` e cede il turno.
* I task oltre `60` secondi emettono un heartbeat ogni `45` secondi con `scripts/async_heartbeat_signaler.py` in `%TEMP%\nk_diagnostics\`.

### [RULE-01] / [RULE-01.7] UNIVERSAL_DDI_MANDATE (Topologia 2-Tier Hub-and-Spoke)
* `NK-Master-Hub` governa il DAG di Kahn e il commit 2PC; `NK-Session-Controller` governa l'Auto-Brief FSM a 5 turni e i 6 Gate.
* L'Orchestratore registra Builder e Scribe con `define_subagent(Name="<Role>-Worker", EnableWriteTools=True, EnableSubagentTools=False)`.
* Gli Auditor (`NK-Security-DAST-Auditor`, `NK-RSI-Auditor`) mantengono `EnableWriteTools=False` in sola lettura (`GT-14`).
* Il Fast-Track consente fino a `12` chiamate dirette consecutive (`<= 8` letture da `800` righe e `<= 4` comandi).
* Ogni delega ai sub-agenti include `<env_capsule>` con `python -m pytest` e vieta one-liner `python -c` multi-riga.

### [RULE-EVIDENCE] / [RULE-DATA-PROVENANCE] / [RULE-ORACLE-LOCK] / [RULE-EPISTEMIC-HONESTY]
* Ogni certificazione `PASS` o `CONVERGED_OPTIMAL` richiede un comando reale con `exit code 0` nello stesso turno (`[RULE-EVIDENCE]`).
* Ogni record di dominio richiede `source_url` reale ed `evidence_quote` verificabile (`[RULE-DATA-PROVENANCE]`).
* Prima della Fase 3, l'Orchestratore congela i test in `nk_tracking/oracle_lock.json` senza rivelare l'Holdout Set ai Builder (`[RULE-ORACLE-LOCK]`).
* La matrice `100x` assegna `+100` al fix reale, `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`) e `-10.000` al test-gaming (`PYTEST_CURRENT_TEST`, `currentframe()`, `len(grants)`).

### [RULE-SWARM-HYGIENE] / [RULE-08] SWARM_MESSAGE_HYGIENE_MANDATE
* Nessun sub-agente invia messaggi `send_message` superiori a `1.800` caratteri netti (`2.000` MTU), salvando i report lunghi su disco.

### [RULE-01.1] / [RULE-01.8] PROTOCOLLO CRV 4.0 E TASSONOMIA VIBE CODING
* **Macro-Fasi CRV 4.0:** 1) Build in `.staging/` (`ast_guard_validator.py`, `auto_heal_pipeline.py`), 2) Audit Read-Only, 3) Commit 2PC, 4) Teardown sandbox.
* **Tassonomia:** `Mode C` (`<= 150` LOC Fast-Sprint), `Mode B` (CRV Lite bugfix), `Mode A` (Sovereign 5 turni), `Mode D` (Discovery Read-Only).

### [RULE-01.10] PERMANENT_TEST_SUITE_MANDATE (Golden Tests Ratchet)
* Nessun agente degrada la suite di `93` Golden Tests Zero-Mock in `18` moduli (pavimento `68` test) in `tests/`.
* `nk_tracking/quality_baseline.json` blocca ogni commit se il pass rate scende sotto il `100.0%`.

### [RULE-01.13] / [RULE-01.14] TETRALOGIA SOVRANA 4/4 E REGISTRO O(1)
* La Tetralogia Sovrana comprende `concept_map.md`, `structural_tree.md`, `implementation_plan.md` e `repo_map.md` (aggiornata con `scripts/ast_repo_mapper.py`).
* L'agente risolve e sincronizza le skill in tempo O(1) tramite `nk_genome/nk_registry_manifest.json` e `scripts/nk_registry_indexer.py --sync`.

### [RULE-01.2] / [RULE-01.3] ZERO_MOCK_AND_SAFE_CLEANUP_MANDATE
* Nessun agente usa `MagicMock` o `unittest.mock`; i test usano fixture reali e `scripts/deterministic_api_cache.py` (SQLite WAL).
* Prima di modificare il codice, l'agente ferma i server attivi con `scripts/safe_cleanup_dev_servers.py`.

### [RULE-RSI] / [RULE-RSI.1] CONTINUOUS_TENSOR_RSI_CONVERGENCE_MANDATE
* Ogni ciclo converge tramite `scripts/rsi_convergence_engine.py` sui profili `VIBE_SPRINT_MICRO_RSI`, `CODE_RSI`, `SPEC_RSI`, `UI_UX_RSI` e `STE100_RSI`.
* Il motore calcola $\Delta_k(p) = 100 D_k + 20 E_{\text{PoC},k} + w_{\text{SAST}}^{(p)}\text{SAST}_k + 12 D_{\text{sem},k} + w_{\text{test}}^{(p)}(T_{\text{fail},k} + C_k) + w_H^{(p)}H_k + w_M^{(p)}M_k + w_L^{(p)}L_k + w_G^{(p)}G_k$.
* Il ciclo termina con `CONVERGED_OPTIMAL` solo quando $\Delta_k == 0$ e $Q(S_k) == 100.0$, con rollback automatico su regressioni.

---

## 2. Governance, Memoria a 3 Livelli e Tracciamento

### [RULE-02.3.1] / [RULE-02.4] / [RULE-02.5] PREFLIGHT, COVE E TWO_STAGE_GROUNDING
* L'agente esegue `scripts/preflight_health_check.py` solo in manutenzione o CI/CD (`--check-only`); all'avvio usa `scripts/nk_session_bootstrap.py`.
* Prima di modificare il codice, il Builder legge `nk_genome/implementation_plan.md` (Stage A) e i file target (Stage B) applicando la CoVe.

### [RULE-02.8] / [RULE-03] / [RULE-05.1] / [RULE-05.2] HANDOFF, FSM 5 TURNI, CHANGELOG E MEMORIA 3-TIER
* Alla soglia di guardia (`70` step standard, `150` step argon), l'agente raccomanda `/compact` ed esegue `scripts/nk_session_handoff.py`.
* I 5 turni dell'Auto-Brief FSM sono: 1) Draft Synthesis, 2) Attack Swarm, 3) Refine Architecture, 4) 1:1 Plan Alignment, 5) Final Handoff.
* `nk_genome/PATCH_NOTES.md` è la Single Source of Truth del changelog; `scripts/memory_3tier_engine.py` gestisce `ARCH`, `SEC`, `OPS`, `DEVX` (`350` token std, `1.200` argon).

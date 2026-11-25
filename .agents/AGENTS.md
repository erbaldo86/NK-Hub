# Regolamento di Sistema: Ecosistema Antigravity (NK Hub Generation v1.0.0-Generation)

> **Ambito:** Costituzione vincolante per tutti gli agenti, sub-agenti e nodi di `NK_Hub`.  
> **Versione:** `v1.0.0-Generation` (`11` skill, `6` sub-agenti foglia, `[RULE-STE100]`, `[RULE-RSI]`, `GT-01..GT-14`, soglie in `nk_tracking/quality_baseline.json`).  
> **Milestone Anchor:** `NK-GEN-1.0.0`.

---

## 0. Hard Execution Gate e Direttiva Linguistica

### [RULE-PROJECT-ISOLATION] EXTERNAL_PROJECT_DIRECTORY_MANDATE
* Nessun agente crea codice applicativo (`src_app/`, `app/`, `src/`) dentro `NK_Hub`.
* Ogni progetto esterno attivo risiede in `NK Proget/Locale/<Nome>/` (compatibile con `NK_External_Projects/<Nome>/`).
* La cartella `NK Proget/Online/` è un mirror di release in sola lettura e blocca ogni scrittura.
* Usa `python -u NK_Hub/scripts/external_project_scaffolder.py --name <Nome> --target <Path>` per creare nuovi progetti in `Locale`.

### [RULE-00.4] SESSION_BOOTSTRAP_GATE
* L'agente esegue `python -u NK_Hub/scripts/nk_session_bootstrap.py` all'inizio di ogni sessione.
* La verifica `Fast-Stat` termina in meno di `120` ms (`< 30` ms su cache `TTL 900s`).
* Lo script pulisce `.wal`, valida la root, imposta `NK_MODEL_PROFILE=generation` (compatibile `carbon`) e blocca tutto su `FAIL`.
* Con handoff ricevuti esegui `python -B -u NK_Hub/scripts/nk_session_bootstrap.py --handoff-verify --project-root "<root>" --handoff-file "<root>/nk_tracking/handoff/next_session_prompt.md" --json`.
* Se l'ultimo `USER_INPUT` manca di marcatori handoff, `--handoff-verify` ripiega su `next_session_prompt.md`.
* La verifica esenta i `conversation_id` di mittente e ricevente. `FAST_STAT_HIT` ispeziona l'intero albero repository con le esclusioni del gateway.
* Ogni `repo_root` esterno al workspace o ai progetti esterni attiva `REPO_OUT_OF_SCOPE`.

### [RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE
* Trigger Legacy: `"avvia ambiente nk"`, `"avvia nk hub"`, `"avvia nk"`, `"avvia hub"`, `"start nk"`, `"start hub"`, `"attiva nk"`, `"attiva ambiente nk"`.
* Trigger Generation: `"avvia generation"`, `"avvia nk generation"`, `"avvia nk hub generation"`, `"avvia ambiente generation"`, `"start generation"`, `"start nk generation"`, `"attiva generation"`, `"attiva ambiente generation"`.
* Su trigger di avvio l'agente esegue `Fast-Stat` in meno di `120` ms verificando `ONBOARDING_BYPASS_VERIFIED`.
* L'agente mostra subito la Dashboard a 10 nodi (`[0]` fino a `[9]`) di `NK-Orchestrator/SKILL.md`.
* In calce espone sempre `Modalità Diretta` (`[0]`..`[9]`) e `Modalità Goal-Driven` in linguaggio naturale.

### [RULE-00.6] / [RULE-00.7] / [RULE-01.11] / [RULE-01.12] META_PROMPT_GATE_AND_FAST_BYPASS
* Su ogni nuovo prompt non esente esegui `python -u NK_Hub/scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>" --conversation-id <id>`.
* Il router non emette `--conversation-id auto`. `MetaPromptGateContract` impone `bypass_scope` e `tools_allowed` strict.
* **Re-Trigger L0 Incrementale:** Se approvi un piano aggiungendo requisiti, riesegui `--meta-prompt-gate` e mostra lo Specchio L0.
* Lo Specchio Concettuale L0 espone tre sezioni: Intenzione (`R1..Rn`), Come farlo e Regole.
* Su `AWAIT_CONFIRM` richiedi conferma 1-Click, poi il Brief e `nk_genome/implementation_plan.md` (`RequestFeedback: true`).
* Attiva intrinsecamente `INTRINSIC_GOAL`, `INTRINSIC_BOOST` e `INTRINSIC_PLAN` senza chiedere comandi slash manuali (`AP-10`).
* Valida i prompt generati con `python -u NK_Hub/scripts/nk_transcript_tools.py lint-prompt --file <path>` prima della consegna.
* Esenzioni anti-loop: conferme brevi (`ok`, `procedi`, `Proceed`), `[0]..[9]`, `<env_capsule>`, `!diretto` e trigger d'avvio.
* **Fast-Bypass `Mode D` e `Mode C`:** `Mode D` opera in sola lettura immediata senza overhead 2PC. `Mode C` (`<= 150` LOC, `max_depth <= 1`) applica modifiche snelle in `.staging/` con `--vibe-check`.
* `HANDOFF_V2` (`PASSIVE_STANDBY` o `ACTIVE_CONTINUATION`) e `Template 12` applicano `STATE_HANDOFF_STANDBY` in sola lettura con firewall `AP-12..AP-16`.

### [RULE-00] / [RULE-00.1] / [RULE-00.2] / [RULE-00.3] STAGING_AND_2PC_MANDATE
* Ogni modifica al codice avviene esclusivamente in `.staging/` o `nk_sandbox_*` nella directory temporanea di sistema con `PYTHONDONTWRITEBYTECODE=1`.
* Usa solo i tool nativi (`read_file`, `write_file`, `edit_file`, `run_command`) con burst controllato (< 4 scritture simultanee).
* Il commit finale usa `python -u NK_Hub/scripts/win32_2pc_engine.py --promote-staging --repo-root "<root>" --milestone "<id>"`, seguito da `NK-Scribe-Memory`.
* Se esiste `nk_tracking/tensor_sessions/ACTIVE.json`, `win32_2pc_engine` e `nk_hook_gate` bloccano `--promote-staging` senza `accepted == True` e `staging_manifest_sha256` corrente.
* I token `v2:` e il CLI `--promote-staging` applicano controllo anti-replay persistente in `nonce_store.py` sotto `Win32NamedMutex`.

### [RULE-STE100] LINEE_GUIDA_CHIAREZZA_TECNICA_ADVISORY
* I file `.md` italiani, le docstring, i commenti e le risposte seguono le linee guida di chiarezza ASD-STE100.
* Preferisci frasi attive brevi (`<= 20` parole) senza trattini spaziati. I controlli emettono solo warning non bloccanti su compliance e RSI (`--strict` opt-in).

---

## 1. Topologia 2-Tier, Protocollo Dual-Execution (`GT-14`), Onestà Epistemica e RSI

### [RULE-REACTIVE-SILENCE] / [RULE-01.9] ANTI_POLLING_AND_HEARTBEAT_MANDATE
* Nessun agente esegue polling in ciclo su `manage_task` o sui sub-agenti attivi.
* Durante l'attesa asincrona imposta `schedule(DurationSeconds=180, TimerCondition="any")` e cedi subito il turno.
* Oltre `60` secondi emetti l'heartbeat ogni `45` secondi con `python -u NK_Hub/scripts/async_heartbeat_signaler.py --task-id <id>`.

### [RULE-01] / [RULE-01.7] TOPOLOGIA_2TIER_AND_DUAL_EXECUTION (`GT-14`)
* `NK-Orchestrator` governa il DAG di Kahn, l'FSM a 5 turni e il commit 2PC in topologia piatta 2-Tier.
* Registra i `6` sub-agenti foglia (`NK-Arch-Specifier`, `NK-Specifier-Agent`, `NK-Builder-Agent`, `NK-Security-DAST-Auditor`, `NK-RSI-Auditor`, `NK-Scribe-Agent`) con `enable_subagent_tools=false` e `enable_mcp_tools=false`.
* Solo `DOM-01 Orchestrator-Direct` invoca i built-in `browser`, `research` e `image-generator`, vietando `python -c` multilinea.
* **Protocollo `Dual-Execution` (`GT-14`):** Gli Auditor read-only usano `read_file` e `send_message`. La ricerca locale RO (`grep_search`, `find_by_name`, `list_dir`) resta ammessa solo se il runtime la espone. Restano vietati `run_command`, `write_file`, `edit_file`, `search_web` e i tool MCP. L'Orchestratore esegue le sonde CLI salvando i JSON in `nk_diagnostics/` nella directory temporanea di sistema.

### [RULE-EVIDENCE] / [RULE-DATA-PROVENANCE] / [RULE-ORACLE-LOCK] / [RULE-EPISTEMIC-HONESTY]
* Ogni verdetto `PASS` o `CONVERGED_OPTIMAL` richiede un'esecuzione reale con `exit code 0` nello stesso turno.
* Ogni record esterno richiede `source_url` reale ed `evidence_quote` verificabile (`[RULE-DATA-PROVENANCE]`).
* Prima della build congela i test con `python -u NK_Hub/scripts/nk_transcript_tools.py oracle-lock freeze` (`[RULE-ORACLE-LOCK]`). Il blocco verifica `oracle_lock.json`, `oracle_lock_holdout.json`, `tests_holdout_lock.json`, `governance_lock.json` e `tensor_rsi_lock.json`.
* `epistemic_firewall_rules.py` rimuove `last_summary`, score storici e narrative `L3` verso `DOM-04` tramite `strip_l3_persuasive_narrative`. `transcript_scan.py` segnala letture holdout o edit test nello stesso turno.
* Matrice `100x`: `+100` al fix reale, `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`), `-10.000` al test-gaming (`PYTEST_CURRENT_TEST`, `currentframe()`, `len(grants)`).

### [RULE-SWARM-HYGIENE] / [RULE-08] / [RULE-01.1] / [RULE-01.10] / [RULE-01.2] / [RULE-01.3]
* Ogni `send_message` resta sotto `1.800` caratteri netti (`2.000` MTU), salvando i report lunghi su disco.
* Macro-Fasi CRV: 1) Build `.staging/`, 2) Dual-Execution Audit Read-Only, 3) Commit 2PC, 4) Teardown sandbox.
* Mantieni intatti tutti i test Zero-Mock (`100.0%` pass rate, pavimento `93`, zero `MagicMock`, soglie in `nk_tracking/quality_baseline.json`). Verifica il ratchet tramite `quality_baseline_manager.py --check-only --live --with-coverage`.
* Prima delle modifiche ferma i server attivi con `python -u NK_Hub/scripts/safe_cleanup_dev_servers.py --workspace-root "<root>"`.

### [RULE-01.13] / [RULE-01.14] / [RULE-RSI] / [RULE-02.5] / [RULE-02.8] / [RULE-03] / [RULE-05.1] / [RULE-05.2]
* La Sovereign Pentad `4+1` comprende `concept_map.md`, `structural_tree.md`, `implementation_plan.md`, `repo_map.md` e `nk_genome/modules/`; sincronizza l'indice O(1) con `python -u NK_Hub/scripts/nk_registry_indexer.py --sync`.
* `NK_Hub/scripts/tensor_rsi.py` e `NK_Hub/scripts/rsi_convergence_engine.py` calcolano `Delta_k(p)`, `G_hard` e `Q_v2(S_k)`. `CONVERGED_OPTIMAL` richiede `G_hard == 1`, `Q_v2(S_k) == 100.0` e `true_branch >= 82.0%` floor. Usa `STATIC_PASS` e `CERTIFIED_PASS`.
* Il Builder esegue Two-Stage Grounding con `read_file` (`<= 800` righe) su `implementation_plan.md` (Stage A) e sui target (Stage B).
* Alla guardia (`70` step `standard`, `150` `generation`/`carbon`) raccomanda `/compact` nella UI host e serializza con `nk_session_handoff.py --serialize --ecosystem-scan`.
* `NKHandoffEngine v2` (`NK-GEN-1.1.1-HANDOFF-V2-HARDENING`) rifiuta `"auto"` in `resolve_session_tracking_dir`. Il wire JSON usa separatori compatti e `canonical_bootstrap_cmd` include `--handoff-file`.
* `PassiveStandbyPayloadV2` riporta `ignored_non_nk_dirs` e `patch_notes_head.first_section_excerpt` limita l'estratto a `280` caratteri e `6` righe.
* I 5 turni FSM sono Draft, Attack Swarm, Refine, 1:1 Align e Final Handoff. `nk_genome/PATCH_NOTES.md` funge da changelog SSOT. `NK_Hub/scripts/memory_3tier_engine.py` gestisce `ARCH`, `SEC`, `OPS` e `DEVX` (`350` tok `standard`, `1.200` `generation`/`carbon`).

### [RULE-REHYDRATE] AUTONOMOUS_CONTEXT_SHIELD_AND_LOCK_QUIESCENCE
* Il comando `/compact` appartiene esclusivamente alla UI host; nessuno script o hook invoca `/compact`.
* Gli hook `PreInvocation`, `PostInvocation` e `Stop` orchestrano `Z1`, `Z2` e `Z3` tramite `saturation_thresholds.json`. I profili attivi sono `generation`, `carbon`, `argon`, `standard`, `neon`, `pro` e `flash`.
* Su soglia `Z2`, il guardiano verifica la quiescenza di `Global/Local NK_RepoBatchLock` prima dello spawn.
* Quando `NK_RepoBatchLock` risulta occupato o nega accesso, il guardiano salta lo spawn evitando collisioni `2PC`.
* Dopo un `CHECKPOINT` reale (`source: "SYSTEM"`), `PreInvocation` inietta `[RULE-REHYDRATE]` una sola volta per evento (`one-shot`).
* Dopo `CHECKPOINT`, se `nk_tracking/active_context.md` esiste, `[RULE-REHYDRATE]` impone `read_file` prima di ogni modifica o bootstrap gate.
* Gli hook e le sentinelle rifiutano marker `CHECKPOINT` o `<CONTEXT_SUMMARY>` emessi da `USER`, `MODEL` o `SYSTEM_SDK`.

---

## 2. Regole di Specifica, Sicurezza I/O e Path

### [RULE-02.4] DOM01_RESEARCH_AND_CLI_DELEGATION
* Solo `DOM-01 Orchestrator-Direct` invoca i tool `research`, `image-generator` e le sonde CLI runtime.
* Applica la CoVe sui flag CLI e verifica ogni dato esterno con prove reali.

### [RULE-02.6] PYDANTIC_V2_STRICTNESS_AND_CLEAN_HANDOFF
* I contratti IPC usano Pydantic v2 strict con `ConfigDict(strict=True, extra="forbid")` e zero wrapper superflui.
* Ogni handoff applica il Clean Handoff Protocol con campi JSON espliciti e validati.
* Il parser handoff rifiuta chiavi JSON duplicate, `NaN` e `Infinity`. Applica `AP-12/13` anche su `ACTIVE_CONTINUATION` e regole stdlib `AP-14..16` su stringhe decodificate.

### [RULE-08.1] WINDOWS_PATH_UTF8_AND_MOJIBAKE_GUARD
* Gestisci i percorsi Windows con spazi usando `pathlib` e racchiudi i traceback letti in `<passive_data_context>`.
* Salva tutti i file in `UTF-8` senza BOM, usa `c_void_p` a 64-bit e blocca il mojibake.

### [RULE-NO-LITERAL-ENV-PATH] DYNAMIC_ENV_PATH_RESOLUTION
* Vieta path letterali di ambiente non espansi per la directory temporanea di sistema nel codice e nei test.
* Risolvi sempre la directory temporanea di sistema tramite `tempfile.gettempdir()` o `os.environ.get()`.

### [RULE-WIN32-ISOLATED-PYTEST] NVME_ISOLATED_PYTEST_MANDATE
* Esegui `pytest` solo su NVMe locale tramite `NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging`.
* Non avviare mai `pytest` diretto su Drive FS (`G:\`) per evitare crash `0xC000013A` su `conhost.exe`.

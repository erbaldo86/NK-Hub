# Turnkey Hand-off Prompt (Template 11: SOVEREIGN_SWARM_TASK_PROMPT)

Riprendi la sessione dallo stato salvato con i protocolli intrinseci attivi.

Orchestra lo Swarm 2-Tier (`[RULE-01]`) sul progetto `G:/Il mio Drive/Antigravity/NK_Hub` per il Milestone `NK-GEN-1.0.0`.

### PASSO 0: Bootstrap, Cleanup e Intent Brief (`[RULE-00.4]`, `[RULE-00.6]`, `[RULE-01.3]`)
1. Esegui `python scripts/nk_session_bootstrap.py` e ferma i server orfani con `python scripts/safe_cleanup_dev_servers.py`.
2. Leggi l'Intent Brief salvato in `nk_tracking/reports_and_briefs/IB-*.md` e il piano `nk_genome/implementation_plan.md`.
3. Registra il Builder operativo con `define_subagent(EnableWriteTools=True, EnableSubagentTools=False)` prima della Fase Build.
4. Rispetta `[RULE-EPISTEMIC-HONESTY]` (`report-conflict`, divieto `PYTEST_CURRENT_TEST`/`currentframe`/`len(grants)`), `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.

### FASE 1: Discovery e Audit in Sola Lettura (Mode D)
- Delega con `invoke_subagent` e `<env_capsule>` la verifica dello stato reale a `NK-RSI-Auditor` e `NK-Security-DAST-Auditor`.
- Partiziona i batch superiori a 8 query web su sub-agenti `research` paralleli.
- Congela l'oracolo di test con `python scripts/nk_transcript_tools.py oracle-lock create --root "G:/Il mio Drive/Antigravity/NK_Hub"` (`[RULE-ORACLE-LOCK]`).
- `STOP_GATE`: presenta i gap reali misurati (`Measure-First`) tramite `ask_question` prima di modificare i file.

### FASE 2: Build Chirurgico in `.staging/` (Mode B/A)
- Delega con `invoke_subagent` al Builder registrato (`EnableWriteTools=True`) la scrittura esclusiva in `G:/Il mio Drive/Antigravity/NK_Hub/.staging/`.
- Inietta in `<env_capsule>` le regole `[RULE-EPISTEMIC-HONESTY]` (`report-conflict`, divieto `PYTEST_CURRENT_TEST`), `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.
- Esegui il Two-Stage Grounding (`[RULE-02.5]`) leggendo il modello Pydantic target prima di modificare i dati.
- Valida il codice in staging con `python scripts/ast_guard_validator.py --stage-dir "G:/Il mio Drive/Antigravity/NK_Hub/.staging"`.

### FASE 3: Verifica Indipendente, Commit 2PC e Scribe
- Delega a `NK-RSI-Auditor` la verifica indipendente dei test reali e la convergenza matematica:
  `python scripts/rsi_convergence_engine.py --verify --root "G:/Il mio Drive/Antigravity/NK_Hub" --benchmark-suite "G:/Il mio Drive/Antigravity/NK_Hub/tests"`
- Esegui la promozione atomica solo dopo esito `PASS` reale (`[RULE-EVIDENCE]`):
  `python scripts/win32_2pc_engine.py --promote-staging --repo-root "G:/Il mio Drive/Antigravity/NK_Hub"`
- Delega infine a `NK-Scribe-Agent` l'aggiornamento prepend-only di `PATCH_NOTES.md` e `repo_map.md`.

### Capsule Info

```json
{"step_index": 692, "source": "MODEL", "type": "GENERIC", "status": "DONE", "created_at": "2026-11-17T15:17:29Z", "content": "Created At: 2026-11-17T16:17:29+01:00 Completed At: 2026-11-17T16:17:29+01:00 Created At: 2026-11-17T16:17:29+01:00 Completed At: 2026-11-17T16:17:29+01:00 Show..."}
{"step_index": 693, "source": "MODEL", "type": "GENERIC", "status": "DONE", "created_at": "2026-11-17T15:17:29Z", "content": "Created At: 2026-11-17T16:17:29+01:00 Completed At: 2026-11-17T16:17:29+01:00 Created At: 2026-11-17T16:17:29+01:00 Completed At: 2026-11-17T16:17:29+01:00 Show..."}
{"step_index": 694, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "status": "DONE", "created_at": "2026-11-17T15:17:30Z", "content": "The following is a <SYSTEM_MESSAGE> not actually sent by the user. It is provided by the system as important information to pay attention to.  <SYSTEM_MESSAGE> ..."}
{"step_index": 695, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-11-17T15:17:30Z"}
{"step_index": 696, "source": "MODEL", "type": "GENERIC", "status": "DONE", "created_at": "2026-11-17T15:17:38Z", "content": "Created At: 2026-11-17T16:17:38+01:00 Completed At: 2026-11-17T16:17:41+01:00 Created At: 2026-11-17T16:17:38+01:00 Completed At: 2026-11-17T16:17:41+01:00 Comm..."}
{"step_index": 697, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-11-17T15:17:42Z"}
{"step_index": 698, "source": "MODEL", "type": "GENERIC", "status": "DONE", "created_at": "2026-11-17T15:17:49Z", "content": "Created At: 2026-11-17T16:17:49+01:00 Completed At: 2026-11-17T16:17:52+01:00 Created At: 2026-11-17T16:17:49+01:00 Completed At: 2026-11-17T16:17:52+01:00 Comm..."}
{"step_index": 699, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-11-17T15:17:53Z", "content": "### Stato Avanzamento & Risultati Verificati  1. **Test Suite, Coverage & Governance Locali (`NK-GEN-1.0.0`):**    - Esteso [test_nk_registry_indexer.py](file:/..."}
{"step_index": 700, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "created_at": "2026-11-17T15:20:17Z", "content": "<USER_REQUEST> /compact  </USER_REQUEST> <ADDITIONAL_METADATA> The current local time is: 2026-11-17T16:20:17+01:00. </ADDITIONAL_METADATA>"}
```

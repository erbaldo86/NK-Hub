# 📝 NK-Session-Controller: Prompt Templates (`v3.0.0-STE100-Unified`)

> **Ambito:** Libreria di template pre-validati per l'orchestrazione 2-Tier Hub-and-Spoke e il loop RSI.  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. AUTO_BRIEF_SWARM_FSM_LOOP (`[RULE-03]`)
```markdown
**[DIRETTIVA ESECUTIVA: RULE-03 AUTO-BRIEF SWARM FSM A 5 TURNI]**
Applica la sequenza concatenata a 5 turni:
1. **Turno 1 (Draft Synthesis):** Definisci la proposta iniziale e il Milestone Anchor ID in `nk_genome/implementation_plan.md`.
2. **Turno 2 (Attack & Stress Swarm):** Invoca via `invoke_subagent` i sub-agenti auditor in parallelo e attendi in IDLE.
3. **Turno 3 (Refine & Solution Architecture):** Risolvi i conflitti e aggiorna la Tetralogia Sovrana 4/4 in `nk_genome/`.
4. **Turno 4 (1:1 Plan Alignment):** Invoca `NK-Plan-Aligner` per certificare l'allineamento 4/4 ed emettere il badge `🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]`.
5. **Turno 5 (Final Handoff):** Compila il prompt Template 8A e avvia l'esecuzione del Builder in `.staging/`.

Contesto operativo:
{{CONTEXT}}
```

---

## 2. DYNAMIC_STRESS_TEST (`[RULE-01.1]` & `[RULE-01.2]`)
```markdown
**[DIRETTIVA ESECUTIVA: REAL DAST & SANDBOX VERIFICATION]**
1. Invoca `NK-Dynamic-Sandbox-StressTester` tramite `invoke_subagent` per eseguire i test in `%TEMP%\nk_sandbox_<uuid>\` con `python scripts/dast_sandbox_runner.py --script <target> --timeout 10 --json`.
2. Cedi il turno in silenzio reattivo (`[RULE-REACTIVE-SILENCE]`) fino alla risposta del sub-agente.
3. Accetta il verdetto solo con `exit_code: 0` reale e zero mock (`[RULE-01.2]`).

Componenti da testare:
{{CONTEXT}}
```

---

## 3. RATCHET_LOOP_BUG_FIX (`[RULE-01.1]` & `[RULE-RSI]`)
```markdown
**[DIRETTIVA ESECUTIVA: RATCHET LOOP BUG FIX IN STAGING]**
1. **Macro-Fase 1 (Build & Stage):** Delega al Builder in `.staging/` la correzione chirurgica e l'auto-riparazione con `python scripts/auto_heal_pipeline.py --test-cmd "<pytest_cmd>" --target-file {{TARGET_FILE}}`.
2. **Macro-Fase 2 (Cold Audit):** Invoca `NK-Oracle-Evaluator` per verificare la patch in `%TEMP%\nk_sandbox_<uuid>\` e controllare $\Delta_k = 0$ con `python scripts/rsi_convergence_engine.py --verify`.
3. **Macro-Fase 3 (2PC Atomic Commit):** Dopo l'esito PASS (`exit_code: 0`), delega a `NK-Master-Hub` il commit atomico tramite `python scripts/win32_2pc_engine.py --promote-staging --milestone "{{MILESTONE_ANCHOR_ID}}"` e registra l'evento in `nk_tracking/anchor/session_anchor.jsonl`.

File impattati:
{{TARGET_FILE}}
```

---

## 4. DATA_MINING_TAXONOMY (`[RULE-02.4]` & `[RULE-08]`)
```markdown
**[DIRETTIVA ESECUTIVA: RICERCA VERIFICATA E VALIDAZIONE PYDANTIC V2]**
1. Raccogli i dati da fonti primarie verificabili tramite `search_web`.
2. Valida ogni record con modelli Pydantic v2 strict (`strict=True, extra="forbid"`).
3. Usa `python scripts/deterministic_api_cache.py --health` (o `--force-refresh` in CI) per la cache locale SQLite WAL.

Requisiti Dati:
{{CONTEXT}}
```

---

## 5. ARCHITECTURAL_CHANGE (`[RULE-01]` & `[RULE-01.13]`)
```markdown
**[DIRETTIVA ESECUTIVA: MODE A SOVEREIGN ARCHITECTURAL CHANGE]**
1. Aggiorna i 4 file della Tetralogia Sovrana (`concept_map.md`, `structural_tree.md`, `implementation_plan.md`, `repo_map.md`) in `nk_genome/`.
2. Invia il prompt Template 8A al Builder operante in `.staging/`.
3. Valida il risultato con `NK-Oracle-Evaluator`, `NK-Security-Auditor` e `python scripts/rsi_convergence_engine.py --verify` prima del commit `python scripts/win32_2pc_engine.py --promote-staging --milestone "{{MILESTONE_ANCHOR_ID}}"`.

Contesto architetturale:
{{CONTEXT}}
```

---

## 6. COMPACT_AND_HANDOFF_PREPARE (`[RULE-02.8]`)
```markdown
**[DIRETTIVA SISTEMA: PREPARAZIONE HANDOFF E COMPACT]**
1. Sincronizza la Tetralogia Sovrana 4/4 in `nk_genome/`.
2. Aggiorna `nk_tracking/anchor/session_anchor.jsonl`.
3. Esegui `python scripts/nk_session_handoff.py --transcript <path> --output-dir nk_tracking/handoff --generate-prompt` per generare `nk_tracking/handoff/next_session_prompt.md`.
4. Consiglia all'utente il comando `/compact` per comprimere il contesto della sessione attiva.
```

---

## 7. CONTROLLER_RESUME_PROMPT (`[RULE-02.8]`)
```markdown
**[RIPRESA SESSIONE: [14] NK-SESSION-CONTROLLER v3.0.0-STE100-UNIFIED]**
Assumi il ruolo di `[14] NK-Session-Controller`.
1. Esegui `python scripts/nk_session_bootstrap.py --json`.
2. Leggi `nk_tracking/handoff/next_session_prompt.md` e `nk_genome/implementation_plan.md` (`view_file <= 800` righe).
3. Riprendi l'orchestrazione dal Milestone Anchor ID `{{MILESTONE_ANCHOR_ID}}`.
```

---

## 8. CLEAN_HANDOFF_ENGINE (Template 8A & 8B `v3.0`)
Specifica completa in [`clean_handoff_protocol.md`](clean_handoff_protocol.md).

### 8A. Prompt per il Builder (`TASK_HANDOFF_4_BLOCKS`)
```markdown
# 📦 [HANDOFF PROMPT FOR BUILDER : v3.0.0-STE100-UNIFIED]

### 🎯 BLOCCO 1: Obiettivo e Brief Anchor Capsule
- **Task Operativo:** {{PROBLEM_DESCRIPTION}}
- **Brief Anchor Capsule (<= 350 token):**
  * **Milestone Anchor ID:** `{{MILESTONE_ANCHOR_ID}}`
  * **Tetralogia Reference:** `nk_genome/implementation_plan.md`

### 📍 BLOCCO 2: Perimetro d'Azione Chirurgico
- **File Autorizzati in `.staging/`:** {{TARGET_FILES_PATHS}}
- **Componenti:** {{TARGET_COMPONENTS}}

### 🔍 BLOCCO 3: Two-Stage Grounding Obbligatorio (`[RULE-02.5]`)
1. **Skill Grounding:** Esegui `view_file` sul `SKILL.md` del tuo nodo.
2. **Stage A (Brief Grounding):** Esegui `view_file` (`<= 800` righe) su `nk_genome/implementation_plan.md`.
3. **Stage B (Code Grounding):** Esegui `view_file` (`<= 800` righe) sui file sorgente target.

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche e Test
1. **Pre-Edit Safety:** Ferma eventuali processi demone con `manage_task(Action="kill", TaskId="<id>")`.
2. **Modifiche in `.staging/`:** {{SURGICAL_INSTRUCTIONS}} (Codifica UTF-8 senza BOM, standard `[RULE-STE100]`).
3. **Verifica:** Esegui `python scripts/ast_guard_validator.py --stage-dir .staging`, `{{VERIFICATION_COMMAND}}` e `python scripts/rsi_convergence_engine.py --verify` (o `--vibe-check <target>` in Mode C), poi restituisci la **Worker Execution Receipt v3.0** (`< 1.800` caratteri).
```

### 8B. Checklist Cold Review (`CRITIC_REVIEW_CHECKLIST`)
```markdown
1. **Gate 1 (Scope):** Modifiche confinate nei soli file autorizzati in `.staging/`?
2. **Gate 2 (Code Grounding):** `view_file` (`<= 800` righe) eseguito sui file target?
3. **Gate 3 (Brief Grounding):** `view_file` eseguito su `nk_genome/implementation_plan.md`?
4. **Gate 4 (Preservation):** Firme pubbliche, tipi e commenti preservati?
5. **Gate 5 (Truth/DAST):** Test pytest e `dast_sandbox_runner.py` superati con `exit_code: 0`?
6. **Gate 6 (RSI Convergence):** `python scripts/rsi_convergence_engine.py --verify` con $\Delta_k = 0$ e $Q(S_k) = 100.0$?
```

---

## 9. WORKER_REFRESH (Template 9 `v3.0`)
```markdown
<!-- ZERO-AMNESIA BOOTSTRAP CAPSULE v3.0 -->
Assumi il ruolo di `[5] NK-Delta-Architect` dell'Ecosistema Nexus Keystone (`v3.0.0-STE100-Unified`).
Esegui `view_file` su `.agents/skills/NK-Delta-Architect/SKILL.md`.
Esegui Stage A (`view_file` su `nk_genome/implementation_plan.md`) e Stage B sui file target prima di scrivere in `.staging/`.
Procedi con il task nei 4 Blocchi:
{{TASK_HANDOFF_4_BLOCKS_PAYLOAD}}
```

---

## 10. CRITIC_SELF_REFRESH (Template 10 `v3.0`)
```markdown
<!-- ZERO-AMNESIA BOOTSTRAP CAPSULE v3.0 -->
Assumi il ruolo di `[14] NK-Session-Controller` (Sovereign Critic & Supervisor) dell'Ecosistema Nexus Keystone (`v3.0.0-STE100-Unified`).
Esegui `view_file` su `.agents/skills/NK-Session-Controller/SKILL.md`.
Leggi `nk_tracking/handoff/next_session_prompt.md`, verifica il Milestone Anchor ID `{{MILESTONE_ANCHOR_ID}}` ed esegui la Cold Review sull'output del Builder.
```

# 🔧 NK-Delta-Architect: Delta Brief Template (`v1.0.0-Generation`)

> **Ambito:** Template a 4 Blocchi conforme al Clean Handoff Protocol `[RULE-02.5 / RULE-02.6]`.  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 📋 Metadati del Task
- **Target Node:** [Nodo del DAG Impattato]
- **Change Scope:** [`BUG_FIX` | `MODIFICATION` | `FEATURE` | `REFACTOR` | `UI_UX`]
- **Milestone Anchor ID:** `[es. NK-GEN-1.0.0]`
- **Circuit Breaker Status:** `[Tentativo X di 3]`

---

### 🎯 BLOCCO 1: Obiettivo e Brief Anchor Capsule (`<= 1200` token profilo `generation`/`carbon`)
- **Problema Reale / Task:** [Descrivi la modifica richiesta in forma attiva]
- **Effetto Collaterale da Evitare:** [Indica le regressioni da prevenire]
- **Brief Anchor Capsule:**
  * **Milestone Anchor ID:** `{{MILESTONE_ANCHOR_ID}}`
  * **Sintesi Requisiti:** `{{BRIEF_SUMMARY_EXTRACT}}`
  * **Pentad Sovrana (4+1):** `nk_genome/concept_map.md`, `nk_genome/structural_tree.md`, `nk_genome/implementation_plan.md`, `nk_genome/repo_map.md`, `nk_genome/idea_canvas.md`

---

### 📍 BLOCCO 2: Perimetro d'Azione Chirurgico
- **File Autorizzati in `.staging/`:** `.staging/{{RELATIVE_PATH}}`
- **Classi e Funzioni Target:** `{{TARGET_SYMBOLS}}`
- **Scope Creep Guard:** Non modificare alcun file o simbolo esterno a questo elenco.

---

### 🔍 BLOCCO 3: Two-Stage Grounding Obbligatorio (`[RULE-02.5]`)
1. **Skill Grounding:** Esegui `read_file` sul `SKILL.md` del nodo assegnato.
2. **Stage A (Brief Grounding):** Esegui `read_file` (`<= 800` righe) su `nk_genome/implementation_plan.md` e verifica il Milestone Anchor ID.
3. **Stage B (Code Grounding):** Esegui `read_file` (`<= 800` righe) sui file sorgente target indicati nel Blocco 2.

---

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche, Test e Ricevuta v3.0
1. **Pre-Edit Safety & Snapshot:** Ferma i demoni con `manage_task(Action="kill", TaskId="<id>")` e crea snapshot con `python -u scripts/healing_snapshot_rollback.py --create <files>`.
2. **Modifiche in `.staging/`:** Applica le modifiche con `write_file` o `edit_file` (`<= 2` per step) in `UTF-8` senza BOM.
3. **Onestà Epistemica:** Rispetta `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]` definiti in `.agents/AGENTS.md`.
4. **Verifica Locale AST e DOM:** Esegui `python -u scripts/ast_guard_validator.py --stage-dir .staging --allowed-mutations "<simboli>"`, `python -u scripts/oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json` e pytest reale.
5. **Consegna:** Salva il report esteso in `scratch/` e invia via `send_message` la **Worker Execution Receipt v3.0** (`< 1.800` caratteri):

````markdown
### 📋 WORKER EXECUTION RECEIPT (v3.0 : CRV 6.0 & RSI Certified)
- **Stage A (Brief Grounding):** `read_file` su `nk_genome/implementation_plan.md` (`{{MILESTONE_ANCHOR_ID}}`).
- **Stage B (Code Grounding):** `read_file` eseguito su `{{FILE_PATH}}` (L{{START}}-L{{END}}).
- **Staging Path:** `.staging/{{TARGET_PATH}}`
- **AST & Test Evidence:** Comando `{{TEST_CMD}}` eseguito con `exit_code: 0` (`[RULE-EVIDENCE]`).
- **DOM / UI Evidence:** Verifica `python -u scripts/oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json` con verdetto `PASS`.
- **RSI Status:** `CONVERGED_OPTIMAL` ($\Delta_k = 0$, $Q(S_k) = 100.0$).
- **Commit Status:** Staging pronto per promozione atomica via `scripts/win32_2pc_engine.py`.
````

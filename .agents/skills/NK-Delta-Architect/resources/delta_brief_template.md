# 🔧 NK-Delta-Architect: Delta Brief Template (`v3.0.0-STE100-Unified`)

> **Ambito:** Template a 4 Blocchi conforme al Clean Handoff Protocol `[RULE-02.5 / RULE-02.6]`.  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 📋 Metadati del Task
- **Target Node:** [Nodo del DAG Impattato]
- **Change Scope:** [`BUG_FIX` | `MODIFICATION` | `FEATURE` | `REFACTOR` | `UI_UX`]
- **Milestone Anchor ID:** `[es. NK-MS-20261014-STE100-UNIFIED-v3.0.0]`
- **Circuit Breaker Status:** `[Tentativo X di 3]`

---

### 🎯 BLOCCO 1: Obiettivo e Brief Anchor Capsule (`<= 350` token)
- **Problema Reale / Task:** [Descrivi la modifica richiesta in forma attiva]
- **Effetto Collaterale da Evitare:** [Indica le regressioni o le rotture da prevenire]
- **Brief Anchor Capsule:**
  * **Milestone Anchor ID:** `{{MILESTONE_ANCHOR_ID}}`
  * **Sintesi Requisiti:** `{{BRIEF_SUMMARY_EXTRACT}}`
  * **Tetralogia Sovrana (4/4):** `nk_genome/concept_map.md`, `nk_genome/structural_tree.md`, `nk_genome/implementation_plan.md`, `nk_genome/repo_map.md`

---

### 📍 BLOCCO 2: Perimetro d'Azione Chirurgico
- **File Autorizzati in `.staging/`:** `.staging/{{RELATIVE_PATH}}`
- **Classi e Funzioni Target:** `{{TARGET_SYMBOLS}}`
- **Scope Creep Guard:** Non modificare alcun file o simbolo esterno a questo elenco.

---

### 🔍 BLOCCO 3: Two-Stage Grounding Obbligatorio (`[RULE-02.5]`)
1. **Skill Grounding:** Esegui `view_file` sul `SKILL.md` del nodo assegnato.
2. **Stage A (Brief Grounding):** Esegui `view_file` (`<= 800` righe) su `nk_genome/implementation_plan.md` e verifica il Milestone Anchor ID.
3. **Stage B (Code Grounding):** Esegui `view_file` (`<= 800` righe per chiamata) sui file sorgente target indicati nel Blocco 2.

---

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche, Test e Ricevuta v3.0
1. **Pre-Edit Safety & Snapshot:** Ferma i processi demone con `manage_task(Action="kill", TaskId="<id>")` e crea uno snapshot con `python scripts/healing_snapshot_rollback.py --create`.
2. **Modifiche in `.staging/`:** Applica le modifiche in `.staging/` con codifica `UTF-8` senza BOM e standard `[RULE-STE100]`.
3. **Onestà Epistemica (`[RULE-EPISTEMIC-HONESTY]`):** Applica `[RULE-EVIDENCE]` (`exit_code: 0`), `[RULE-DATA-PROVENANCE]` (`source_url`, `evidence_quote`) e `[RULE-ORACLE-LOCK]` (`oracle_lock.json`). Assegna `+100` al fix reale e `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`); vieta `PYTEST_CURRENT_TEST`, `currentframe()` e `len(grants)` (`-10.000`).
4. **Verifica Locale AST e DOM:** Esegui `python scripts/ast_guard_validator.py --stage-dir .staging --allowed-mutations`, `python scripts/oracle_evaluator_l3.py --expected --actual --json` e pytest reale.
5. **Consegna:** Salva il report completo in `scratch/` e restituisci via `send_message` la **Worker Execution Receipt v3.0** (`< 1.800` caratteri):

````markdown
### 📋 WORKER EXECUTION RECEIPT (v3.0 : CRV 4.0 & RSI Certified)
- **Stage A (Brief Grounding):** `view_file` su `nk_genome/implementation_plan.md` (`{{MILESTONE_ANCHOR_ID}}`).
- **Stage B (Code Grounding):** `view_file` eseguito su `{{FILE_PATH}}` (L{{START}}-L{{END}}).
- **Staging Path:** `.staging/{{TARGET_PATH}}`
- **AST & Test Evidence:** Comando `{{TEST_CMD}}` eseguito con `exit_code: 0` (`[RULE-EVIDENCE]`).
- **DOM / UI Evidence:** Verifica `scripts/oracle_evaluator_l3.py --expected --actual --json` con verdetto `PASS`.
- **Epistemic Integrity:** Rispettati `[RULE-EPISTEMIC-HONESTY]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.
- **RSI Status:** `CONVERGED_OPTIMAL` ($\Delta_k = 0$, $Q(S_k) = 100.0$).
- **Commit Status:** Staging pronto per promozione atomica via `scripts/win32_2pc_engine.py`.
````

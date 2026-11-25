# 🔧 NK-Delta-Architect: Delta Brief Template (`v1.0.0-Generation`)

> **Ambito:** Template a 4 Blocchi conforme al Clean Handoff Protocol `[RULE-02.5 / RULE-02.6]`.
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 📋 Metadati del Task
- **Target Node:** `[Nodo del DAG Impattato]`
- **Change Scope:** `[BUG_FIX | MODIFICATION | FEATURE | REFACTOR | UI_UX]`
- **Milestone Anchor ID:** `[es. NK-GEN-1.0.0]`
- **Circuit Breaker Status:** `[Tentativo X di 2]`

---

### 🎯 BLOCCO 1: Obiettivo e Brief Anchor Capsule (`<= 1200` token profilo `generation`/`carbon`)
- **Problema Reale o Task:** `[Descrivi la modifica richiesta in forma attiva]`
- **Effetto Collaterale da Evitare:** `[Indica le regressioni da prevenire]`
- **Brief Anchor Capsule:**
  * **Milestone Anchor ID:** `{{MILESTONE_ANCHOR_ID}}`
  * **Sintesi Requisiti:** `{{BRIEF_SUMMARY_EXTRACT}}`
  * **Pentad Sovrana:** `nk_genome/concept_map.md`, `nk_genome/structural_tree.md`, `nk_genome/implementation_plan.md`, `nk_genome/repo_map.md`, `nk_genome/idea_canvas.md`

---

### 📍 BLOCCO 2: Perimetro d'Azione Chirurgico
- **File Autorizzati in `.staging/`:** `.staging/{{RELATIVE_PATH}}`
- **Classi e Funzioni Target:** `{{TARGET_SYMBOLS}}`
- **Scope Creep Guard:** Non modificare alcun file o simbolo esterno a questo elenco.

---

### 🔍 BLOCCO 3: Two-Stage Grounding Obbligatorio (`[RULE-02.5]`)
1. **Skill Grounding:** Esegui `read_file` su `SKILL.md` e su `references/mode_surgical_refactor_checklist.md`.
2. **Stage A (Brief Grounding):** Esegui `read_file` (`<= 800` righe) su `nk_genome/implementation_plan.md` e verifica il Milestone Anchor ID.
3. **Stage B (Code Grounding):** Esegui `read_file` (`<= 800` righe) sui file sorgente target indicati nel Blocco 2.

---

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche, Test e Ricevuta v3.0
1. **Pre-Edit Safety e Snapshot:** Ferma i demoni e crea snapshot con `healing_snapshot_rollback.py --create <files>`.
2. **Modifiche in `.staging/`:** Applica le modifiche con `write_file` o `edit_file` (`<= 2` per step) in `UTF-8` senza BOM.
3. **Onesta Epistemica:** Rispetta `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.
4. **Controlli Statici:** Valida con `ast_guard_validator.py --quality-diff` (`frontend_static_checker` incluso) e `rsi_convergence_engine.py --vibe-check NK_Hub/.staging --profile refactor_rsi --strict-verify --json`.
5. **Pytest, Mutazione ed HTML UI:** Esegui `platform_runner.py --pytest-isolated --overlay-staging`, `--diagnose-slice` solo su failure e `builder_mutation_gate.py` su Python `Mode A/B`. Usa `oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json` solo per HTML e interfacce UI.
6. **Consegna:** Salva il report in `scratch/` e invia via `send_message` la **Worker Execution Receipt** (`< 1.800` caratteri):

````markdown
### 📋 WORKER EXECUTION RECEIPT (v3.0: CRV 6.0 & RSI Certified)
- **Stage A (Brief Grounding):** `read_file` su `nk_genome/implementation_plan.md` (`{{MILESTONE_ANCHOR_ID}}`).
- **Stage B (Code Grounding):** `read_file` eseguito su `{{FILE_PATH}}` (L{{START}}..L{{END}}).
- **Staging Path:** `.staging/{{TARGET_PATH}}`
- **AST & Test Evidence:** `ast_guard_validator.py --quality-diff` e `platform_runner.py --pytest-isolated --overlay-staging` con `exit_code: 0`.
- **HTML UI Evidence (solo se UI):** `oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json` con verdetto `PASS`.
- **RSI Status:** `CONVERGED_OPTIMAL` (`Delta_k = 0`, `G_hard == 1`, `Q_v2(S_k) = 100.0`, profilo `refactor_rsi`).
- **Commit Status:** Staging verificato e pronto per revisione GT-14.
````

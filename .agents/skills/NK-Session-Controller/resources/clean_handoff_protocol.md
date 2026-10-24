# 🏛️ Clean Handoff Protocol & 2-Tier Hub-and-Spoke Specification (`v3.0.0-STE100-Unified`)

> **Ambito:** Comunicazione strutturata tra `NK-Session-Controller` (Sovereign Critic) e i Builder operanti in `.staging/`.  
> **Versione:** `v3.0.0-STE100-Unified` (Topologia 2-Tier a 1 livello, Tetralogia Sovrana 4/4, `/compact` e Convergenza RSI).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 🧭 1. Principi Cardine e Guardie di Sicurezza

1. **Topologia 2-Tier (`[RULE-01]`):** Il Controller delega la scrittura al Builder in `.staging/` e la verifica agli Auditor. I sub-agenti non invocano altri sub-agenti.
2. **Brief Anchor Capsule (`<= 350` token):** Il Blocco 1 contiene il Milestone Anchor ID e i riferimenti alla Tetralogia Sovrana 4/4 in `nk_genome/`.
3. **Two-Stage Grounding (`[RULE-02.5]`):**
   * **Stage A (Brief Grounding):** Lettura di `nk_genome/implementation_plan.md` tramite `view_file` (`<= 800` righe).
   * **Stage B (Code Grounding):** Lettura dei file sorgente target tramite `view_file` (`<= 800` righe per chiamata).
4. **Sicurezza Processi Win32 (`[RULE-01.3]`):** Prima di modificare i file, il Builder ferma i server attivi con `manage_task(Action="kill", TaskId="<id>")` o `scripts/safe_cleanup_dev_servers.py`.
5. **Compattazione e Handoff (`[RULE-02.8]`):** Alla soglia di guardia, il Controller consiglia `/compact` o esegue `scripts/nk_session_handoff.py --transcript <path> --output-dir nk_tracking/handoff --generate-prompt`.
6. **Onestà Epistemica (`[RULE-EPISTEMIC-HONESTY]`):** Applica `[RULE-EVIDENCE]` (`exit_code: 0`), `[RULE-DATA-PROVENANCE]` (`source_url`, `evidence_quote`) e `[RULE-ORACLE-LOCK]` (`oracle_lock.json`). Assegna `+100` al fix reale e `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`); vieta `PYTEST_CURRENT_TEST`, `currentframe()` e `len(grants)` (`-10.000`).

---

## 📦 2. Template 8A: `TASK_HANDOFF_4_BLOCKS` (`v3.0` per il Builder)

````markdown
# 📦 [HANDOFF PROMPT FOR BUILDER : v3.0.0-STE100-UNIFIED]

<env_capsule>
Usa `python -m pytest` per i test. Vieta `view_file` esplorativi alla cieca e `python -c` multi-riga.
Applica `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]` (`exit_code: 0`), `[RULE-DATA-PROVENANCE]` (`source_url`, `evidence_quote`) e `[RULE-ORACLE-LOCK]` (`oracle_lock.json`).
Assegna `+100` al fix reale e `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`); vieta `PYTEST_CURRENT_TEST`, `currentframe()` e `len(grants)` (`-10.000`).
</env_capsule>

### 🎯 BLOCCO 1: Obiettivo e Brief Anchor Capsule
- **Task Operativo:** {{PROBLEM_DESCRIPTION}}
- **Regressioni da Prevenire:** {{SIDE_EFFECT_PREVENTION}}
- **Brief Anchor Capsule (<= 350 token):**
  * **Milestone Anchor ID:** `{{MILESTONE_ANCHOR_ID}}`
  * **Sintesi Architetturale:** {{BRIEF_SUMMARY_EXTRACT}}
  * **Tetralogia Sovrana (4/4):** `nk_genome/concept_map.md`, `nk_genome/structural_tree.md`, `nk_genome/implementation_plan.md`, `nk_genome/repo_map.md`

### 📍 BLOCCO 2: Perimetro Autorizzato in `.staging/`
- **File Target:** `.staging/{{TARGET_RELATIVE_PATHS}}`
- **Simboli Coinvolti:** `{{TARGET_COMPONENTS}}`
- **Scope Creep Guard:** Non modificare alcun file fuori da `.staging/` o esterno a questo elenco.

### 🔍 BLOCCO 3: Two-Stage Grounding Obbligatorio (`[RULE-02.5]`)
1. **Skill Grounding:** Esegui `view_file` sul file `SKILL.md` del tuo nodo.
2. **Stage A (Brief Grounding):** Esegui `view_file` (`<= 800` righe) su `nk_genome/implementation_plan.md` e verifica `{{MILESTONE_ANCHOR_ID}}`.
3. **Stage B (Code Grounding):** Esegui `view_file` (`<= 800` righe) sui file sorgente target.

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche, Test e Ricevuta v3.0
1. **Pre-Edit Safety:** Arresta eventuali processi attivi con `manage_task(Action="kill", TaskId="<id>")`.
2. **Modifiche in `.staging/`:** {{SURGICAL_INSTRUCTIONS}} (Codifica UTF-8 senza BOM, standard `[RULE-STE100]`).
3. **Verifica Locale:** Esegui `{{VERIFICATION_COMMAND}}` e verifica `exit_code: 0`.
4. **Formato Risposta:** Salva il report in `scratch/` e invia via `send_message` la **Worker Execution Receipt v3.0** (`< 1.800` caratteri).
````

---

## 🛡️ 3. Template 8B: `CRITIC_REVIEW_CHECKLIST` (Cold Review sui 6 Gate)

```markdown
### 🛡️ [USO INTERNO CRITICO] Checklist di Cold Review Post-Esecuzione (v3.0)
1. **Gate 1 (Scope):** Il Builder ha scritto solo nei file autorizzati in `.staging/`? *(Se NO -> REJECT_SCOPE_CREEP)*.
2. **Gate 2 (Code Grounding):** Il Builder ha eseguito `view_file` (`<= 800` righe) sui file target? *(Se NO -> REJECTED_BLIND_EXECUTION)*.
3. **Gate 3 (Brief Grounding):** Il Builder ha letto `nk_genome/implementation_plan.md` e verificato il Milestone Anchor ID? *(Se NO -> REJECT_FAKE_BRIEF_GROUNDING)*.
4. **Gate 4 (Preservation):** Firme pubbliche, tipi e docstring esistenti sono preservati? *(Se NO -> REJECT_CLEAN_SLATE)*.
5. **Gate 5 (Truth/DAST):** I test pytest, `dast_sandbox_runner.py` e `oracle_lock.json` riportano `exit_code: 0`? *(Se NO -> REJECT_TEST_FAILED)*.
6. **Gate 6 (RSI Convergence):** `rsi_convergence_engine.py --verify` certifica $\Delta_k = 0$ e $Q(S_k) = 100.0$? *(Se NO -> REJECT_RSI_DIVERGENCE)*.
```

---

## 📋 4. Worker Execution Receipt v3.0

````markdown
### 📋 WORKER EXECUTION RECEIPT (v3.0 : CRV 4.0 & RSI Certified)
- **Stage A (Brief Grounding):** `view_file` su `nk_genome/implementation_plan.md` (`{{MILESTONE_ANCHOR_ID}}`).
- **Stage B (Code Grounding):** `view_file` su `{{FILE_PATH}}` (L{{START_B}}-L{{END_B}}).
- **Staging Evidence:** Modifiche confinate in `.staging/{{TARGET_PATH}}`.
- **Dynamic Test Evidence:** Comando `{{REAL_E2E_TEST_CMD}}` eseguito con `exit_code: 0` (`[RULE-EVIDENCE]`).
- **Epistemic Integrity:** Rispettati `[RULE-EPISTEMIC-HONESTY]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.
- **RSI Convergence:** $\Delta_k = 0$, $Q(S_k) = 100.0$ (`CONVERGED_OPTIMAL`).
- **Commit Status:** Staging completato. Promozione atomica demandata a `NK-Master-Hub` via `scripts/win32_2pc_engine.py`.
````

---

## 🔄 5. Protocollo di Ripresa Sessione (`[RULE-02.8]`)

1. Raccomanda il comando nativo `/compact` per liberare la finestra di contesto senza cambiare conversazione.
2. In alternativa, esegui `python scripts/nk_session_handoff.py --transcript <path> --output-dir nk_tracking/handoff --generate-prompt` per generare `nk_tracking/handoff/next_session_prompt.md`.

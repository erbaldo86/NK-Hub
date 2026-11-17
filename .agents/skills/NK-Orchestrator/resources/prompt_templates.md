# 📝 NK-Orchestrator: Prompt Templates (`0..5`, `v1.0.0-Generation`)

> **Ambito:** Template `0..5` per topologia 2-Tier, `GT-14` e RSI (`generation`/`carbon`, `150/250` step).  
> **Template `6..12`:** [`handoff_and_swarm_templates.md`](../references/handoff_and_swarm_templates.md) | **Standard:** `[RULE-STE100]`.

---

## 0. META_PROMPT_INTENT_BRIEF (`[RULE-00.6]`)
Esegui `python -u scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>"` su ogni nuovo prompt non esente.
Stampa lo Specchio Concettuale L0 in `content` prima della conferma, poi compila `implementation_plan.md`.
```markdown
### 🧭 [LIVELLO 0: SUPER META-PROMPT & INTENT BRIEF GATE]
- **Brief ID:** `{{BRIEF_ID}}` | **Stato FSM:** `AWAIT_CONFIRM`
- **Modalità:** `{{RECOMMENDED_MODE}}` | **Skill:** `{{PRIMARY_AGENT}}` | **Sub-Agente:** `{{NATIVE_SUBAGENT}}`
- **Protocolli Intrinseci:** `{{INTRINSIC_PROTOCOLS}}` (`INTRINSIC_GOAL`, `INTRINSIC_BOOST`, `INTRINSIC_PLAN`)
- **Intent SHA-256:** `{{INTENT_HASH_SHA256}}` | **Specchio:** {{CONCEPTUAL_MIRROR}}
- **Meta-Prompt:** {{OPTIMIZED_META_PROMPT}}
- **Requisiti (`R1..Rn`):** `R1` {{REQ_1}} | `R2` {{REQ_2}}
- **Correzioni vocali:** {{VOICE_CORRECTIONS_APPLIED}} | **Fuori ambito:** {{OUT_OF_SCOPE}} | **Ambiguità:** {{AMBIGUITIES}}
- **Flusso Post-L0:** Brief e `implementation_plan.md` (`RequestFeedback: true`) -> Builder `.staging/` -> Audit `GT-14` e 2PC.
- **Conferma 1-Click:** `1. Conferma ed esegui`, `2. Solo risposta diretta`, `3. Modifica intento`.
```

## 1. AUTO_BRIEF_SWARM_FSM_LOOP (`[RULE-03]`)
```markdown
**[RULE-03 AUTO-BRIEF SWARM FSM A 5 TURNI]**
1. **Turno 1 (Draft):** Definisci la bozza e il Milestone Anchor ID in `nk_genome/implementation_plan.md`.
2. **Turno 2 (Attack Swarm):** Invoca in parallelo gli Auditor read-only (`EnableWriteTools=False`, `GT-14`).
3. **Turno 3 (Refine):** Risolvi i rilievi e aggiorna la Sovereign Pentad `4+1` in `nk_genome/` e `nk_genome/modules/`.
4. **Turno 4 (1:1 Align):** Invoca `NK-RSI-Auditor` (`NK-Oracle-Evaluator`) per certificare `🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]`.
5. **Turno 5 (Final Handoff):** Compila `Template 8A` o `Template 11` (`<= 1200` token) e avvia il Builder in `.staging/`.
```

## 2. DYNAMIC_STRESS_TEST (`[RULE-01.1]` & `GT-14`)
```markdown
**[REAL DAST & SANDBOX VERIFICATION]**
1. Esegui in `nk_sandbox_<uuid>` temporaneo `python -u scripts/dast_sandbox_runner.py --script <target> --timeout 30 --json` con log in `nk_diagnostics/`.
2. Esegui eventuali test Browser E2E tramite il sub-agente `browser` di `DOM-01` salvando i report temporanei in `nk_diagnostics/`.
3. Invoca `NK-Security-DAST-Auditor` (`NK-Dynamic-Sandbox-StressTester`) in sola lettura su `exit_code: 0` reale (`[RULE-01.2]`).
```

## 3. RATCHET_LOOP_BUG_FIX (`[RULE-01.1]` & `[RULE-RSI]`)
```markdown
**[RATCHET LOOP BUG FIX IN STAGING]**
1. **Build:** Delega al Builder in `.staging/` con `python -u scripts/auto_heal_pipeline.py --test-cmd "<pytest_cmd>" --target-file {{TARGET_FILE}}`.
2. **Cold Audit:** Esegui `python -u scripts/rsi_convergence_engine.py --verify --root "<PROJECT_ROOT>"` e invoca `NK-RSI-Auditor` (`NK-Oracle-Evaluator`).
3. **Commit 2PC:** Con `exit_code: 0`, promuovi con `python -u scripts/win32_2pc_engine.py --promote-staging --repo-root "<PROJECT_ROOT>" --milestone "{{MILESTONE_ANCHOR_ID}}"`.
```

## 4. DATA_MINING_TAXONOMY (`[RULE-02.4]` & `[RULE-DATA-PROVENANCE]`)
```markdown
**[RICERCA VERIFICATA E PYDANTIC V2]**
1. Delega a `DOM-01` (`research`) le query su fonti primarie con `source_url` ed `evidence_quote` reali.
2. Valida i record con `ConfigDict(strict=True, extra="forbid")` e gestisci la cache con `python -u scripts/deterministic_api_cache.py --health`.
```

## 5. ARCHITECTURAL_CHANGE (`[RULE-01]` & `[RULE-01.13]`)
```markdown
**[MODE A SOVEREIGN ARCHITECTURAL CHANGE]**
1. Aggiorna la Sovereign Pentad `4+1` (`concept_map.md`, `structural_tree.md`, `implementation_plan.md`, `repo_map.md`, `nk_genome/modules/`) in `nk_genome/`.
2. Invia `Template 8A` o `Template 11` al Builder in `.staging/`, poi verifica con `rsi_convergence_engine.py --verify`, gli Auditor e il commit 2PC.
```

# Prompt Templates (`0..5`, `v1.0.0-Generation`)
> `6..12`: [`handoff_and_swarm_templates.md`](../references/handoff_and_swarm_templates.md). `[RULE-STE100]`.
## 0. META_PROMPT_INTENT_BRIEF (`[RULE-00.6]`)
* `python -u scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>"`.
* Stampa L0 in `content` prima della conferma, poi `implementation_plan.md` (`RequestFeedback: true`).
```markdown
### [LIVELLO 0: INTENT BRIEF]
- Brief: {{BRIEF_ID}} | FSM: AWAIT_CONFIRM | Mode: {{RECOMMENDED_MODE}} | Skill: {{PRIMARY_AGENT}} | Sub: {{NATIVE_SUBAGENT}}
- Protocolli: {{INTRINSIC_PROTOCOLS}} (INTRINSIC_GOAL/BOOST/PLAN) | SHA-256: {{INTENT_HASH_SHA256}}
- Specchio: {{CONCEPTUAL_MIRROR}} | Meta: {{OPTIMIZED_META_PROMPT}} | R1..Rn: {{REQ_1}}, {{REQ_2}}
- Voci: {{VOICE_CORRECTIONS_APPLIED}} | Fuori: {{OUT_OF_SCOPE}} | Ambiguità: {{AMBIGUITIES}}
- Flusso: piano -> .staging/ -> GT-14/2PC | 1. Conferma, 2. Diretta, 3. Modifica.
```
## 1. AUTO_BRIEF_SWARM_FSM_LOOP (`[RULE-03]`)
* T1: `implementation_plan.md` + Milestone. T2: Auditor read-only (`EnableWriteTools=False`, `GT-14`).
* T3: Pentad `nk_genome/`. T4: `NK-RSI-Auditor` -> `[NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED]`.
* T5: `Template 8A`/`11` (`<= 1200` tok) al Builder in `.staging/`.
## 2. DYNAMIC_STRESS_TEST (`GT-14`)
* `nk_sandbox_<uuid>`: `dast_sandbox_runner.py --script <target> --timeout 30 --json` (`nk_diagnostics/`).
* E2E `browser` (`DOM-01`) in `nk_diagnostics/`. Audit `NK-Security-DAST-Auditor` su `exit_code: 0`.
## 3. RATCHET_LOOP_BUG_FIX (`[RULE-RSI]`)
* `.staging/`: `auto_heal_pipeline.py --test-cmd "<pytest_cmd>" --target-file {{TARGET_FILE}}`.
* Audit: `rsi_convergence_engine.py --verify --root "<PROJECT_ROOT>"` + `NK-RSI-Auditor`.
* `2PC`: `win32_2pc_engine.py --promote-staging --repo-root "<PROJECT_ROOT>" --milestone "{{MILESTONE_ANCHOR_ID}}"`.
## 4. DATA_MINING_TAXONOMY (`[RULE-02.4]`)
* `DOM-01` (`research`): `source_url`, `evidence_quote`.
* `ConfigDict(strict=True, extra="forbid")`; `deterministic_api_cache.py --health`.
## 5. ARCHITECTURAL_CHANGE (`[RULE-01]`)
* Pentad (`concept_map.md`, `structural_tree.md`, `implementation_plan.md`, `repo_map.md`, `modules/`) in `nk_genome/`.
* `Template 8A`/`11` in `.staging/`, `rsi_convergence_engine.py --verify`, Auditor, `2PC`.

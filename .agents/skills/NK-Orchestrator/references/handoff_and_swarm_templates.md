# 📦 NK-Orchestrator: Template Handoff & Swarm (`6..12`, `v1.0.0-Generation`)

> **Ambito:** Template `6..12` per `generation`/`carbon` (`150/250` step, `1200` tok), Builder, Cold Review e `STANDBY`.  
> **Template `0..5`:** [`prompt_templates.md`](../resources/prompt_templates.md) | **Standard:** `[RULE-STE100]`.

---

## 6. COMPACT_AND_HANDOFF_PREPARE (`[RULE-02.8]`)
```markdown
**[HANDOFF E COMPACT GENERATION]**
1. Sincronizza la Pentad `4+1` in `nk_genome/` e `nk_tracking/anchor/session_anchor.jsonl`.
2. Esegui `python -u scripts/nk_session_handoff.py --transcript <path> --output-dir nk_tracking/handoff --generate-prompt` (`150/250` step).
3. Usa `/compact` in UI host per azzerare le sentinelle su `CHECKPOINT` o `<CONTEXT_SUMMARY>`.
```

## 7. CONTROLLER_RESUME_PROMPT (`[RULE-02.8]`)
```markdown
**[RIPRESA: NK-ORCHESTRATOR v1.0.0-Generation]**
1. Esegui `python -u scripts/nk_session_bootstrap.py --json` e leggi `nk_tracking/handoff/next_session_prompt.md`.
2. Leggi `nk_genome/implementation_plan.md` (`<= 800` righe) e riprendi da `{{MILESTONE_ANCHOR_ID}}`.
```

## 8. CLEAN_HANDOFF_ENGINE (`8A` & `8B`, [`clean_handoff_protocol.md`](../resources/clean_handoff_protocol.md))
```markdown
# 📦 [BUILDER HANDOFF: TEMPLATE 8A v1.0.0-Generation]
<env_capsule>
Usa `$env:PYTHONDONTWRITEBYTECODE="1"` e `python -B -m pytest`. Vieta `read_file` ciechi, `python -c` multilinea e batch `> 3` `write_file`.
Rispetta `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]` in `.agents/AGENTS.md`.
</env_capsule>
- **BLOCCO 1 (`<= 1200` tok):** {{PROBLEM_DESCRIPTION}} | **Milestone:** `{{MILESTONE_ANCHOR_ID}}`.
- **BLOCCO 2 (`.staging/`):** File {{TARGET_FILES_PATHS}} | Simboli {{TARGET_COMPONENTS}}.
- **BLOCCO 3 (Grounding):** `read_file` su `SKILL.md`, `nk_genome/implementation_plan.md` e target (`<= 800` righe).
- **BLOCCO 4 (Build):** Modifica `.staging/` (`UTF-8` no BOM, `[RULE-STE100]`): {{SURGICAL_INSTRUCTIONS}}. Usa `nk_transcript_tools.py report-conflict` su conflitti, valida `ast_guard_validator.py --stage-dir .staging` e invia **Worker Execution Receipt v3.0** (`< 1.800` char).
```
```markdown
**[TEMPLATE 8B: COLD REVIEW 6 GATE]**
1. **Gate 1 (Scope):** Solo file autorizzati in `.staging/`?
2. **Gate 2/3 (Grounding):** `read_file` (`<= 800` righe) su target e `implementation_plan.md`?
3. **Gate 4 (Preservation):** Firme pubbliche, tipi e commenti preservati?
4. **Gate 5 (Truth/DAST):** `MIN_GOLDEN_TESTS_FLOOR = 93`, `dast_sandbox_runner.py` e `oracle_lock.json` con `exit_code: 0`?
5. **Gate 6 (RSI):** `rsi_convergence_engine.py --verify` con $\Delta_k = 0$ e $Q(S_k) = 100.0$?
```

## 9 & 10. WORKER_REFRESH & CRITIC_SELF_REFRESH
```markdown
<!-- ZERO-AMNESIA BOOTSTRAP CAPSULE v1.0.0-Generation -->
Esegui `read_file` su `SKILL.md`, `nk_genome/implementation_plan.md` e target (`<= 800` righe) rispettando `.agents/AGENTS.md`.
```

## 11. SOVEREIGN_SWARM_TASK_PROMPT (`Template 11`, `[RULE-00.7]`)
Usa `--compile-template-11` per task multi-fase.
```markdown
# 🏛️ [TEMPLATE 11 v1.0.0-Generation]
1. **Passo 0:** Esegui `nk_session_bootstrap.py`, `safe_cleanup_dev_servers.py --workspace-root "<PROJECT_ROOT>"` e `oracle-lock freeze`.
2. **Fase 1 (`GT-14`):** Sonde nella directory temporanea `nk_diagnostics/` e audit read-only (`EnableWriteTools=False`).
3. **Fase 2 (Staging):** Builder in `<PROJECT_ROOT>/.staging/` con `ast_guard_validator.py --stage-dir "<PROJECT_ROOT>/.staging"`.
4. **Fase 3 (2PC):** Verifica `rsi_convergence_engine.py --verify --root "<PROJECT_ROOT>"`, `win32_2pc_engine.py --promote-staging` e `NK-Scribe-Agent`.
```

## 12. PASSIVE_SESSION_STATE_HANDOFF (`Template 12`, `[RULE-02.8]`)
Compila con `--compile-handoff-prompt` e valida con `--mode state-handoff` contro `AP-12` e `AP-13`.
```markdown
# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)
[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]
- **Workspace / Progetto:** `<WORKSPACE_ROOT>` / `<PROJECT_ROOT>` | **Milestone:** `{{MILESTONE_ANCHOR_ID}}`
- **Ricezione:** `STANDBY` (`STATE_HANDOFF_STANDBY` / `READ_ONLY`) | **Versione:** `1.0.0-Generation`
- **Baseline:** `{{BASELINE_TESTS}}` test (`{{PASS_RATE}}%`) | **Tree:** `CLEAN` | **Divieti:** no task/piste (`AP-12`, `AP-13`)
- **Protocollo:** Esegui `python -u scripts/nk_session_bootstrap.py`, acquisisci in sola lettura e attendi in `STANDBY`.
[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]
```

# ⚙️ NK-Orchestrator: Protocolli Esecutivi 2-Tier, CLI e Commit 2PC (`v1.0.0-Generation`)

> **Nodo Proprietario:** `NK-Orchestrator` (`DOM-01`, Topologia 2-Tier Hub-and-Spoke, `Dual-Execution GT-14`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, massimo 20 parole per frase).

---

## 1. Routing 2-Tier, 6 Sub-Agenti Foglia e Built-In `DOM-01`

| Dominio | Sub-Agente Foglia / Built-In | Strumenti e Permessi | Skill Assegnate |
| :--- | :--- | :--- | :--- |
| `DOM-01` | `browser`, `research`, `image-generator` | Built-in nativi esclusivi di `DOM-01 Orchestrator-Direct` | `NK-Orchestrator` |
| `DOM-02` | `NK-Arch-Specifier` | `read_file`, `send_message` (`write=false`, `mcp=false`) | `[0] NK-Ideator` |
| `DOM-02` | `NK-Specifier-Agent` | `read_file`, `write_file`, `edit_file`, `send_message` | `[1] NK-System-Architect` |
| `DOM-03` | `NK-Builder-Agent` | `read_file`, `write_file`, `edit_file`, `run_command`, `manage_task`, `send_message` | `[2]`, `[3]`, `[4]` |
| `DOM-04` | `NK-Security-DAST-Auditor` | `read_file`, `send_message` (`write=false`, `mcp=false`) | `[5]`, `[7]`, `[8]` |
| `DOM-04` | `NK-RSI-Auditor` | `read_file`, `send_message` (`write=false`, `mcp=false`) | `[6] NK-Oracle-Evaluator` |
| `DOM-05` | `NK-Scribe-Agent` | `read_file`, `write_file`, `edit_file`, `run_command`, `manage_task`, `send_message` | `[9] NK-Scribe-Memory` |

---

## 2. Protocollo Esecutivo CLI, Dual-Execution e Fast-Bypass

1. **Bootstrap e L0 Gate (`[RULE-00.5]`, `[RULE-00.6]`):** Avvia la sessione con `python -u scripts/nk_session_bootstrap.py` (`NK_MODEL_PROFILE=generation` / `carbon`, `.agents/plugins/nk-gate/hooks.json`). Valida ogni nuovo prompt non esente con `python -u scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>"`.
2. **Lookup O(1) e Messaggistica Swarm:** Risolvi i domini con `python -u scripts/nk_registry_indexer.py --lookup "<query>"`. Formatta i messaggi con `python -u scripts/nk_swarm_messenger.py --sender Hub --recipient <id> --payload "<msg>"`.
3. **Fast-Bypass `Mode D` / `Mode C`:** Esegui `Mode D` subito in sola lettura. Per `Mode C` (`<= 150` LOC) valida in `.staging/` con `python -u scripts/rsi_convergence_engine.py --vibe-check .staging --profile code_rsi`.
4. **Holdout Freeze (`[RULE-ORACLE-LOCK]`):** Prima della build congela i test con `python -u scripts/nk_transcript_tools.py oracle-lock freeze`.
5. **Dual-Execution (`GT-14`):** Gli Auditor read-only (`EnableWriteTools=False`) non invocano `run_command`. Lancia tu le sonde CLI salvando i report JSON nella directory temporanea `nk_diagnostics/` e passa i path per `read_file`.
6. **Capsule Ambiente e Igiene (`<env_capsule>`):** Usa `python -B -m pytest`, vieta `read_file` esplorativi alla cieca e mantieni batch `<= 3` `write_file` per step.
7. **Watchdog Generation e Handoff:** Monitora il profilo `generation` o `carbon` (`150/250` step, reset su `CHECKPOINT` o `<CONTEXT_SUMMARY>`). Negli handoff usa `python -u scripts/nk_session_handoff.py --compile-handoff-prompt` (`Template 12`) oppure `--compile-template-11` (`Template 11`).
8. **Commit Win32 2PC e Scribe (`[RULE-00]`):** Arresta i demoni attivi. Promuovi da `.staging/` con `python -u scripts/win32_2pc_engine.py --promote-staging --repo-root "<root>" --milestone "<id>"`. Verifica `python -u scripts/quality_baseline_manager.py --check-only --live` e delega a `NK-Scribe-Agent`.
9. **Confine `/compact` e `[RULE-REHYDRATE]`:** Il comando `/compact` appartiene solo alla UI host senza invocazioni automatiche. Gli hook verificano la quiescenza di `Global/Local NK_RepoBatchLock` prima di ogni scrittura `2PC`. Dopo un `CHECKPOINT` reale (`source: "SYSTEM"`), `[RULE-REHYDRATE]` impone la lettura di `nk_tracking/active_context.md`.

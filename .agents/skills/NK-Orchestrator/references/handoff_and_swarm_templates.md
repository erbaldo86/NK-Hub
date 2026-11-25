# Template Handoff & Swarm (`6..12`, `v1.0.0-Generation`)
> `0..5`: [`prompt_templates.md`](../resources/prompt_templates.md) | Schema: [`handoff_anchor_schema.md`](../resources/handoff_anchor_schema.md).
## 6. COMPACT_AND_HANDOFF (`[RULE-02.8]`)
* Pentad `nk_genome/`, `session_anchor.jsonl`; `/compact` UI host.
* V2: `nk_session_handoff.py --serialize --ecosystem-scan --mode PASSIVE_STANDBY --conversation-id <id> --json`. Legacy: `--transcript <path> --generate-prompt`.
## 7. CONTROLLER_RESUME (`[RULE-02.8]`)
* `nk_session_bootstrap.py --handoff-verify --project-root "<PROJECT_ROOT>" --handoff-file "<PROJECT_ROOT>/nk_tracking/handoff/next_session_prompt.md" --json`.
* Leggi `next_session_prompt.md`, `session_handoff_latest.json`, `implementation_plan.md` (`<= 800`) da `{{MILESTONE_ANCHOR_ID}}`.
## 8. CLEAN_HANDOFF_ENGINE (`8A` & `8B`)
```markdown
# [BUILDER HANDOFF: TEMPLATE 8A]
<env_capsule>$env:PYTHONDONTWRITEBYTECODE="1"; python -B -u scripts/platform_runner.py --pytest-isolated. No read_file ciechi, python -c, batch > 3. .agents/AGENTS.md.</env_capsule>
- BLOCCO 1 (<= 1200 tok): {{PROBLEM_DESCRIPTION}} | {{MILESTONE_ANCHOR_ID}}.
- BLOCCO 2 (.staging/): {{TARGET_FILES_PATHS}} | {{TARGET_COMPONENTS}}.
- BLOCCO 3: read_file SKILL.md, implementation_plan.md, target (<= 800).
- BLOCCO 4: .staging/ (UTF-8, [RULE-STE100]): {{SURGICAL_INSTRUCTIONS}}. report-conflict, ast_guard_validator.py --stage-dir .staging, Receipt v3.0 (< 1.800 char).
```
* 8B (`6 Gate`): 1 `.staging/`; 2/3 `<= 800`; 4 Preservation.
* Gate 5/6: `MIN_GOLDEN_TESTS_FLOOR = 93`, `dast_sandbox_runner.py`, `oracle_lock.json` (`exit_code: 0`); `rsi_convergence_engine.py --verify` (`Delta_k = 0`, `Q_v2(S_k) = 100.0`).
## 9 & 10. WORKER & CRITIC_REFRESH
* `<!-- ZERO-AMNESIA -->`: `read_file` `SKILL.md`, `implementation_plan.md`, target (`<= 800`), `.agents/AGENTS.md`.
## 11. SOVEREIGN_SWARM (`Template 11`)
* `--compile-template-11`. P0: `nk_session_bootstrap.py`, `safe_cleanup_dev_servers.py`, `oracle-lock freeze`.
* F1 `GT-14`: `nk_diagnostics/`, read-only. F2: `.staging/`, `ast_guard_validator.py --stage-dir .staging`.
* F3 `2PC`: `rsi_convergence_engine.py --verify`, `win32_2pc_engine.py --promote-staging`, `NK-Scribe-Agent`.
## 12. `HANDOFF_V2` & `Template 12`
* 12A V2: `--serialize --ecosystem-scan --mode PASSIVE_STANDBY --conversation-id <id>` (`ACTIVE_CONTINUATION --target-repos`), `--handoff-verify`.
* Vincoli: `(",",":")` vs indentato; `first_section_excerpt <= 280` (`<= 6` righe); `ignored_non_nk_dirs`, `FAST_STAT_HIT`, `REPO_OUT_OF_SCOPE`, `AP-14/15`.
````markdown
[NK-ANCHOR:START:HANDOFF_V2:PASSIVE_STANDBY]
# [NK-HANDOFF-V2] Mode: PASSIVE_STANDBY
```json
{"canonical_bootstrap_cmd":"--handoff-verify","envelope_sha256":"<SHA256>","handoff_id":"HO-...","payload":{"handoff_mode":"PASSIVE_STANDBY"},"schema_version":"2.0.0"}
```
[NK-ANCHOR:END:HANDOFF_V2:PASSIVE_STANDBY]
````
* 12B Legacy: `--compile-handoff-prompt`, `nk_transcript_tools.py lint-prompt --mode state-handoff`, `[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]`..`END`, `STANDBY`, `CLEAN`.

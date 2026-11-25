# Clean Handoff Protocol v2 (`v1.0.0-Generation`)
> Schema: [`handoff_anchor_schema.md`](handoff_anchor_schema.md) | Template: [`handoff_and_swarm_templates.md`](../references/handoff_and_swarm_templates.md).
## 1. 2-Tier, Grounding e Win32
1. 2-Tier (`[RULE-01]`, `GT-14`): Builder `.staging/`; Auditor read-only (`EnableWriteTools=False`).
2. Two-Stage Grounding (`[RULE-02.5]`): Stage A `implementation_plan.md` (`<= 800` righe); Stage B target.
3. Win32 Shutdown (`[RULE-01.3]`): `manage_task(Action="kill")` o `safe_cleanup_dev_servers.py`.
4. Contesto (`[RULE-02.8]`): `generation`/`carbon` (`150/250`), `/compact` host, `.agents/AGENTS.md`.
## 2. `Template 8A` (Blocchi 1..4) e Receipt v3.0
* BLOCCO 1: Obiettivo, Capsule (`<= 1200` tok `generation`/`carbon`, `<= 350` std).
* BLOCCO 2: Perimetro `.staging/`, simboli target.
* BLOCCO 3: `read_file` `SKILL.md`, `implementation_plan.md`, target.
* BLOCCO 4: `UTF-8` no BOM, `exit_code: 0`, Receipt v3.0 (`< 1.800` char).
## 3. `NKHandoffEngine v2` (`--serialize --ecosystem-scan`, `--handoff-verify`)
1. Routing: `vibe_sprint_router.py --meta-prompt-gate --conversation-id <id>`, `BYPASSED` -> `NK-Scribe-Agent`.
2. Serializza: `nk_session_handoff.py --serialize --ecosystem-scan --mode PASSIVE_STANDBY --conversation-id <id> --json` (`ACTIVE_CONTINUATION`, `--target-repos`).
3. Lock/Firewall: `EXTERNAL_CONCURRENT` (`diff_patch=None`, `DO_NOT_TOUCH_OR_PROMOTE`), `Win32NamedMutex`, `AP-14..16`, `--compile-handoff-prompt`, `--compile-template-11`.
4. Ricezione: `nk_session_bootstrap.py --handoff-verify --project-root "<root>" --handoff-file "<root>/nk_tracking/handoff/next_session_prompt.md" --json` (`FAST_STAT_HIT`).
5. Esiti: fallback `next_session_prompt.md`, CID esenti, `REPO_OUT_OF_SCOPE`; `PASSIVE_STANDBY` -> `STATE_HANDOFF_STANDBY`, `ACTIVE_CONTINUATION` -> `AWAIT_CONFIRM` + L0.

# 🛡️ Report di Certificazione Finale TAS (`v4.8.0-STE100-Unified`)

Certificazione deterministica generata dal manifesto SSOT `nk_genome/nk_registry_manifest.json`.
Stato convergenza: `CONVERGED_OPTIMAL` (`Delta_k = 0`, `Q(S_k) = 100.0`, `H_k = 0`, `Mutants = 35/35`).

# Matrice di Certificazione TAS (34 Script inclusi 2 Schemi, 16 Skill, 5 Sub-Agenti Nativi)

## 1. Script e Schemi Certificati (34 file: 32 Script + 2 Schemi)

| # | Script / Schema | Dominio | Path Relativo | SHA-256 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `ast_guard_validator.py` | `DOM-04` | `scripts/ast_guard_validator.py` | `58d372e4a4c08a9495afbb76a0e3c172a512a0850ab7990165dbcd9c6b6daac9` |
| 2 | `ast_repo_mapper.py` | `DOM-02` | `scripts/ast_repo_mapper.py` | `81c5c7c696c34155e685a55fba4ba46f2600c3ea0161c6829a1a8dadf5e5cca4` |
| 3 | `async_heartbeat_signaler.py` | `DOM-03` | `scripts/async_heartbeat_signaler.py` | `eb12de020c2f55c5eb563ae4cecbe96af389ef8e079b0be069e1033f9aad7ed8` |
| 4 | `auto_heal_pipeline.py` | `DOM-03` | `scripts/auto_heal_pipeline.py` | `271daf7855f6a8680a136ba69b4f8920c88e6f75f8d0fd68cf284c2194d4866e` |
| 5 | `dast_sandbox_runner.py` | `DOM-04` | `scripts/dast_sandbox_runner.py` | `95218fe5bded5b93c2fcd537b5692c2df9062dcde2086382be851de0bd8ee13f` |
| 6 | `deterministic_api_cache.py` | `DOM-03` | `scripts/deterministic_api_cache.py` | `bad049f01f82194fbb5fccd6e188947a0b6782b29821a68953ef661a1128623c` |
| 7 | `env_capability_probe.py` | `DOM-02` | `scripts/env_capability_probe.py` | `cee0957e4c689c78fdf58aa3718fac2d0c13627e406138099a0c85a2b2939e31` |
| 8 | `external_project_scaffolder.py` | `DOM-02` | `scripts/external_project_scaffolder.py` | `787e7a9c567eeaa1182eef7b63d3df1f2b99a1afa7613ba051c484118c189e6a` |
| 9 | `healing_snapshot_rollback.py` | `DOM-03` | `scripts/healing_snapshot_rollback.py` | `61d5efcb7818d8be27de3a72a9f9bae8b3cc803a50df2b9096025613b03c32eb` |
| 10 | `invisible_healing_loop.py` | `DOM-03` | `scripts/invisible_healing_loop.py` | `e45a8c512ebb1bca98e86527a5c83d52023f380310dd3d4da3410e5736913503` |
| 11 | `memory_3tier_engine.py` | `DOM-05` | `scripts/memory_3tier_engine.py` | `7e77080e2428c4cc7d9c5bafb31919d923269f6b589467939fd2a558162fe9ca` |
| 12 | `micro_hud_renderer.py` | `DOM-05` | `scripts/micro_hud_renderer.py` | `a0f671e5099ae39e929688d8eec7abb5f15039d10a56fdda50e2fd06331e5408` |
| 13 | `nk_active_runtime_sentinel.py` | `DOM-05` | `scripts/nk_active_runtime_sentinel.py` | `a32eb2abef767f0cdbdcedd71d4262d2f40b57a945df74a183c12b2ba3bb1b27` |
| 14 | `nk_auto_inning.py` | `DOM-05` | `scripts/nk_auto_inning.py` | `904422703c629d926af9bb14deabd3bc199fa6a5860b03750e21ae015d2aa97e` |
| 15 | `nk_compliance_checker.py` | `DOM-05` | `scripts/nk_compliance_checker.py` | `521750fa9d31936ba292a0e208f95b10a55fa37cdcdc56fd2937547290376465` |
| 16 | `nk_context_sentry.py` | `DOM-05` | `scripts/nk_context_sentry.py` | `de4f555392efc52731aae9e96c39f910508e4deb630c2e9b5678db3c24a5e5ad` |
| 17 | `nk_hook_gate.py` | `DOM-01` | `scripts/nk_hook_gate.py` | `1a84abb92359a328b6c1d2597930295fc321264073c2b89dd59fc9f783eb84a3` |
| 18 | `nk_registry_indexer.py` | `DOM-01` | `scripts/nk_registry_indexer.py` | `e126cf82841c863c1f5788df2e7e67b96f587e11a330153169beb3f9991e079b` |
| 19 | `nk_session_bootstrap.py` | `DOM-01` | `scripts/nk_session_bootstrap.py` | `7710e7d4fe4ba0c34a3f5d58b294f11f3846ba8a7d83eade3c8d2e557dc2bb85` |
| 20 | `nk_session_handoff.py` | `DOM-01` | `scripts/nk_session_handoff.py` | `bdafe7e0b14b97dc8ae01bf9e1f79ed71c91a0f1c8e452436e77aa3e22b5e5fe` |
| 21 | `nk_swarm_messenger.py` | `DOM-01` | `scripts/nk_swarm_messenger.py` | `02ad6336c1d54e8a555f662c59cd109378ad04746728e12031ac6f9cbea19419` |
| 22 | `nk_transcript_tools.py` | `DOM-04` | `scripts/nk_transcript_tools.py` | `faf5ef15cbc5972fb7174837106b000161379baa90e88eac66c66d5dc9f21bed` |
| 23 | `oracle_evaluator_l3.py` | `DOM-04` | `scripts/oracle_evaluator_l3.py` | `2481dc94adc2e3694443ff81580c81c778dc339f13b673638370deae27746ea4` |
| 24 | `platform_runner.py` | `DOM-03` | `scripts/platform_runner.py` | `80313464c8a0a98f6099f5ba63052fa61837071e5c35f3fec23574e8f0cfe3c9` |
| 25 | `preflight_health_check.py` | `DOM-05` | `scripts/preflight_health_check.py` | `ff6db7a6abae4d3d11bf06709378aac6eebac479a68c2a21489ef9ee77ce8a2b` |
| 26 | `quality_baseline_manager.py` | `DOM-05` | `scripts/quality_baseline_manager.py` | `0d5bc5ddd6448b7569ae0d60fe929b428552d9c69847c59f818245496816b2cc` |
| 27 | `rsi_convergence_engine.py` | `DOM-04` | `scripts/rsi_convergence_engine.py` | `ee9b7c4bec6b7b1512b6055cb00719f44e488b830b16d4a6e540c0fbed796d68` |
| 28 | `safe_cleanup_dev_servers.py` | `DOM-03` | `scripts/safe_cleanup_dev_servers.py` | `b37cc2dc0f981fadc69f6099cf8d98012c94427ff706926aafdb171bb7d5cad6` |
| 29 | `sbfl_engine.py` | `DOM-04` | `scripts/sbfl_engine.py` | `4a1dbe5a65748342a64c8d5af6e8f4fe5831da50ee67d8b21c7e394e4dbe4851` |
| 30 | `sbfl_pytest_bridge.py` | `DOM-04` | `scripts/sbfl_pytest_bridge.py` | `a821195eca992ed6ca95a9f381e6c8d4c4c183216cc5b41914f2586cc55208b4` |
| 31 | `schemas/dual_ledgers.py` | `DOM-01` | `scripts/schemas/dual_ledgers.py` | `e645a07f078f7cd333d7fdda017f6790d18f73444980e764c4aba95444901561` |
| 32 | `schemas/nk_ipc_contracts.py` | `DOM-01` | `scripts/schemas/nk_ipc_contracts.py` | `3b6bb7133b2755edbd62531401b0c379ba85f4aeed0f2135feee2b3c3b11060d` |
| 33 | `vibe_sprint_router.py` | `DOM-01` | `scripts/vibe_sprint_router.py` | `37f2f50c8da0185ea2b530ccd35f3ffe8345b3ab9714eb5d35acf88ec3223acf` |
| 34 | `win32_2pc_engine.py` | `DOM-01` | `scripts/win32_2pc_engine.py` | `fdedaef1e37618f9fc0d13a05d8766d219674348b58968505beadf435ccfea97` |

## 2. Skill Modulari Certificate (16 Skill)

| # | Skill | Dominio | Sub-Agente Nativo | Path Relativo | SHA-256 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `NK-Agent-Instruction-Forge` | `DOM-02` | `` | `.agents/skills/NK-Agent-Instruction-Forge/SKILL.md` | `3b44dc28c40b4e6054ea8e225880b0b073f6bb325733d2120f5619ecf0db0c28` |
| 2 | `NK-App-UX-Architect` | `DOM-02` | `` | `.agents/skills/NK-App-UX-Architect/SKILL.md` | `8fe254d94211448a6ca5fd41ec8333d1956109a7a4bf655ea15ca3d6d5632510` |
| 3 | `NK-Backend-Architect` | `DOM-02` | `` | `.agents/skills/NK-Backend-Architect/SKILL.md` | `d80f67c2c77a08c5b60ee4bd6227ff1ea6c4f9e2a44a8afe936a2ead447dd329` |
| 4 | `NK-Bug-Diagnostic-Engine` | `DOM-04` | `` | `.agents/skills/NK-Bug-Diagnostic-Engine/SKILL.md` | `f500c12d5ccc8b2958b9529b1d8f16557275a527e87b6a040e38c69bd660e1ef` |
| 5 | `NK-Delta-Architect` | `DOM-03` | `` | `.agents/skills/NK-Delta-Architect/SKILL.md` | `2a12411d313b7f36704c089a3d484b4c6986b5dd5726080a6c69829db92081c0` |
| 6 | `NK-Dynamic-Sandbox-StressTester` | `DOM-04` | `` | `.agents/skills/NK-Dynamic-Sandbox-StressTester/SKILL.md` | `393f5008cdf4c9ea1335a32ef6e47841ee9a483d64a6ef97797c4cabbb85b8d3` |
| 7 | `NK-Episodic-Memory-Engine` | `DOM-05` | `` | `.agents/skills/NK-Episodic-Memory-Engine/SKILL.md` | `fbda6f5c5bed301675290308d68eb22afb58063904cd08fccbaec24b5da94ebf` |
| 8 | `NK-Ideator` | `DOM-02` | `` | `.agents/skills/NK-Ideator/SKILL.md` | `7db57163394853290bf2d784e6c0b7e533c4161b775aec6ee7bd312668bd5de7` |
| 9 | `NK-Master-Hub` | `DOM-01` | `` | `.agents/skills/NK-Master-Hub/SKILL.md` | `702b1073deccdc494c4a8699d271268ccb3c67581895e8857c14be2bb84fa7d1` |
| 10 | `NK-Oracle-Evaluator` | `DOM-04` | `` | `.agents/skills/NK-Oracle-Evaluator/SKILL.md` | `392fd474512d9741a30076612d31674ea877925074677556a6081f709db00598` |
| 11 | `NK-Plan-Aligner` | `DOM-01` | `` | `.agents/skills/NK-Plan-Aligner/SKILL.md` | `22664362daff2e534eaf84f4b46da15350fe7c3ce96a47dbf4bb6be55304f748` |
| 12 | `NK-Python-Async-Builder` | `DOM-03` | `` | `.agents/skills/NK-Python-Async-Builder/SKILL.md` | `aac392acfae1e6ab0f0adc3e897e4f0295d9c5626f0228a7c64693d97c433e80` |
| 13 | `NK-Scribe` | `DOM-05` | `` | `.agents/skills/NK-Scribe/SKILL.md` | `85fed5aba4a9039ea5046ef99fbb110300c3c7fcb731c0061ca7628def481908` |
| 14 | `NK-Security-Auditor` | `DOM-04` | `` | `.agents/skills/NK-Security-Auditor/SKILL.md` | `3336f174a16da0506556c96a3e74aec87e92aa21935b7f572cda48683922327d` |
| 15 | `NK-Session-Controller` | `DOM-01` | `` | `.agents/skills/NK-Session-Controller/SKILL.md` | `72635c5895bad428b49cceae1bbb33b795155e7d7d9f4ae2a99a42b9a789576a` |
| 16 | `NK-State-Router` | `DOM-01` | `` | `.agents/skills/NK-State-Router/SKILL.md` | `c69a48958054944065bd5776b4631425a8152ced87ed1d17b0d5f336e63b6b22` |

## 3. Sub-Agenti Nativi Certificati (5 Sub-Agenti)

| # | Sub-Agente Nativo | Dominio | Write Tools | Path Relativo | SHA-256 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `NK-Builder-Agent` | `DOM-03` | `true` | `.agents/agents/NK-Builder-Agent/agent.md` | `ebef57280f914ebac6afec67472f39a3df34fd87c93a32d7bf8f420f21d35f45` |
| 2 | `NK-RSI-Auditor` | `DOM-04` | `false` | `.agents/agents/NK-RSI-Auditor/agent.md` | `b1a1f26afb07b9c337abd557783ef3b0b78a2568a98f456db331c3dd02a8eed8` |
| 3 | `NK-Scribe-Agent` | `DOM-05` | `true` | `.agents/agents/NK-Scribe-Agent/agent.md` | `5f931583307a6bdea2f5bc450e916f5fccb05ce4c1ed1439659bf49a837a159d` |
| 4 | `NK-Security-DAST-Auditor` | `DOM-04` | `false` | `.agents/agents/NK-Security-DAST-Auditor/agent.md` | `feba46f6faa8eef88d39e2ad37b1bca371a8f255de7f7ecba4827dbcb7d65635` |
| 5 | `NK-Specifier-Agent` | `DOM-02` | `true` | `.agents/agents/NK-Specifier-Agent/agent.md` | `0fe5db34a52fb7d66f5b7954ea3c2999ae4e33fd8accee59ec13020602cdb8a6` |

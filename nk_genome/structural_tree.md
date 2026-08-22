# 🏛️ NK Genome: Structural Tree Master (Release v1.1.0-Universal)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED_FINAL 🟢]  
> **Milestone Anchor Primaria:** `NK-MS-20260822-UNIVERSAL-STABILIZATION`  
> **Data Consolidamento:** 2026-08-22  
> **Versione Protocollo:** v1.1.0-Universal

---

## 🌳 Mappatura della Topologia del Repository

```
G:/Il mio Drive/Antigravity/
├── .agents/
│   ├── AGENTS.md                                # Costituzione e Governance di Sistema v1.1.0-Universal
│   ├── rules/
│   │   └── anti_crash_rules.md                  # Regole di protezione dai crash & Windows I/O
│   └── skills/                                  # 16 Vocazioni Canoniche NK
│       ├── NK-Agent-Instruction-Forge/
│       ├── NK-App-UX-Architect/
│       ├── NK-Backend-Architect/
│       ├── NK-Bug-Diagnostic-Engine/
│       ├── NK-Delta-Architect/
│       ├── NK-Dynamic-Sandbox-StressTester/
│       ├── NK-Episodic-Memory-Engine/
│       ├── NK-Ideator/
│       ├── NK-Master-Hub/
│       ├── NK-Oracle-Evaluator/
│       ├── NK-Plan-Aligner/
│       ├── NK-Python-Async-Builder/
│       ├── NK-Scribe/
│       ├── NK-Security-Auditor/                 # Bonificato da NK3_Supervisor e db_helper
│       ├── NK-Session-Controller/
│       └── NK-State-Router/
├── nk_genome/                                   # Single Source of Truth Concettuale
│   ├── concept_map.md
│   ├── structural_tree.md
│   ├── implementation_plan.md
│   ├── business_financial_domain_spec.md        # Preservazione Knowledge Base Nodi 0-4
│   └── PATCH_NOTES.md                           # SSOT Changelog Ufficiale
├── nk_tracking/                                 # Tracciamento e Baseline
│   ├── anchor/
│   │   └── session_anchor.jsonl                 # SSOT Activity Anchor
│   ├── quality_baseline.json                    # Ratchet Baseline
│   └── reports_and_briefs/                      # Audit Reports (Rolling Window max 3)
├── scripts/                                     # Motori Core & Infrastruttura di Sistema
│   ├── __init__.py
│   ├── ast_guard_validator.py                   # Static AST Guard (PEP 634/695)
│   ├── ast_repo_mapper.py                       # AST Topology & PageRank
│   ├── dast_sandbox_runner.py                   # Real DAST Sandbox Runner & Line Tracer
│   ├── invisible_healing_loop.py                # Autonomous Triage Fast-Loop (Max 3 cycles)
│   ├── memory_3tier_engine.py                   # 3-Tier Memory Engine (Tier 1 <=350 tok, RRF k=60)
│   ├── micro_hud_renderer.py                    # Micro-HUD Status Interface
│   ├── preflight_health_check.py                # Boot Sanitizer & WAL TTL 60s Purge
│   ├── quality_baseline_manager.py              # Baseline Compliance & Ratchet Check
│   ├── safe_cleanup_dev_servers.py              # Safe Cleanup Dev Servers & Windows Anti-Lock Tool
│   ├── sbfl_engine.py                           # Spectrum-Based Fault Localization (Ochiai/Def-Use)
│   ├── win32_2pc_engine.py                      # Win32 Named Mutex & 2PC Atomic Engine
│   └── schemas/                                 # Pydantic v2 Strict Mode Contracts
│       ├── __init__.py
│       ├── dual_ledgers.py                      # Immutable Task DAG & Append-Only Progress
│       └── nk_ipc_contracts.py                  # Compact IPC Contracts (<80 tok)
├── tests/                                       # Permanent Test Suite (49 Tests Inviolabili)
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_win32_2pc.py                        # 8 Tests
│   ├── test_dast_sandbox.py                     # 6 Tests
│   ├── test_sbfl_engine.py                      # 7 Tests
│   ├── test_ast_repo_mapper.py                  # 6 Tests
│   ├── test_ast_guard_validator.py              # 7 Tests
│   ├── test_memory_3tier.py                     # 6 Tests
│   ├── test_invisible_healing_loop.py           # 4 Tests
│   └── test_schemas_and_contracts.py            # 5 Tests
├── requirements.txt                             # Specifiche di dipendenze deterministiche
├── README.md                                    # Presentazione ufficiale del framework
└── PATCH_NOTES.md                               # Mirroring atomico di nk_genome/PATCH_NOTES.md
```

---

## 🔒 Progetti Esterni e Server Isolati `[EXTERNAL_ISOLATED_PROJECT]`

I seguenti percorsi risiedono nello storage ma sono **completamente isolati e disaccoppiati** dal core runtime di Nexus Keystone:

1. **`Antigravity model/` [EXTERNAL_ISOLATED_PROJECT]**
   - Modello e artefatti di business sviluppati per progetto esterno correlato.
   - Non referenziato dal runtime NK v1.1.0-Universal.
2. **`Output Business Keystone/` [EXTERNAL_ISOLATED_PROJECT]**
   - Repository di output e deliverable di business di progetto esterno correlato.
   - Non referenziato dal runtime NK v1.1.0-Universal.
3. **`google-docs-mcp/` [EXTERNAL_INTEGRATION_SERVER]**
   - Server MCP attivo per integrazione Google Docs / Workspace.

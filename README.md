# Lab NK Hub: Sovereign AI Agentic OS (`v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified`)

> 🌍 **Choose Your Language / Scegli la Lingua:** **[🇬🇧 English (Current)](README.md)** | **[🇮🇹 Leggi in Italiano (README.it.md)](README.it.md)** | **[📦 Guida Installazione (IT)](GUIDA_INSTALLAZIONE.md)**

> **The Sovereign Cognitive Operating System, 2-Tier Swarm Orchestrator & Tensor-RSI 2D Engine for Google Antigravity**

[![Release](https://img.shields.io/badge/Release-v3.1.0--Tensor--RSI-blue)](#part-7-full-changelog-history--certification-matrix-108108-pass)
[![Tests](https://img.shields.io/badge/108_Golden_Tests-100.0%25_PASS-success)](#part-7-full-changelog-history--certification-matrix-108108-pass)
[![RSI](https://img.shields.io/badge/Tensor--RSI_2D-%CE%94%3D0_%7C_Q%3D100.0-brightgreen)](#part-6-mathematical-foundations--tensor-rsi-2d-engine-senior--auditor-section)
[![VibeCheck](https://img.shields.io/badge/Vibe--Check-%3C500ms-brightgreen)](#tutorial-3-ultra-fast-ui--script-tweaks-in--500-ms-mode-c-vibe-sprint)
[![Fast-Stat](https://img.shields.io/badge/Fast--Stat-%3C50ms_Cached-brightgreen)](#tutorial-1-starting-the-environment-in--120-ms-rule-005)
[![STE100](https://img.shields.io/badge/ASD--STE100-20_Words_Max-informational)](#part-5-architectural-protocols--system-regulations-crv-40--tensor-rsi)
[![Win32 2PC Mutex Active](https://img.shields.io/badge/Win32_2PC_Mutex-64bit_Active-orange)](#part-4-core-engine-architecture--scripts-ecosystem-30-logical-modules--33-python-files)
[![Zero-Mock 100% Real OS](https://img.shields.io/badge/Zero--Mock-100%25_Real_OS-red)](#part-7-full-changelog-history--certification-matrix-108108-pass)

---

## 🚀 Why Nexus Keystone Changes Everything (The 60-Second Hook)

Standard AI coding assistants often fail when projects grow beyond a few files.
They saturate their context window, invent non-existent flags, break working code, and hide bugs behind fake mocks.

**Nexus Keystone (`NK-Hub`)** transforms **Google Antigravity** into an autonomous, self-healing software factory.
Instead of a single fragile prompt, you get a coordinated **16-Skill Swarm** governed by deterministic Python engines.

| Common AI Coding Failure | How `NK-Hub v3.1.0-Tensor-RSI` Solves It Deterministically |
| :--- | :--- |
| **Broken Production Files** | Agents never edit production directly (`[RULE-00]`). They build inside `.staging/` and promote via a 64-bit Win32 Named Mutex (`win32_2pc_engine.py`). |
| **Fake Tests Passing on Broken Code** | `[RULE-01.2]` forbids `MagicMock` and synthetic stubs. Every test runs against real OS processes and a persistent SQLite WAL cache. |
| **Endless Trial-and-Error Loops** | When a test fails, `sbfl_pytest_bridge.py` computes the **Ochiai Spectrum** score and pinpoints the exact faulty line in `< 80` tokens. |
| **Context Window Saturation** | A **2-Tier Hub-and-Spoke** topology isolates heavy searches and builds in sub-agents, capping return messages at `1,800` characters (`[RULE-SWARM-HYGIENE]`). |
| **Slow Validation on Small Edits** | The **Tensor-RSI 2D Engine** runs `--vibe-check` in a single process across the Kahn DAG blast radius in `< 500 ms`. |
| **Workspace Contamination** | `[RULE-PROJECT-ISOLATION]` keeps `NK-Hub` 100% pure. All your applications are scaffolded and built in clean external directories. |
| **Amnesia Between Sessions** | A **3-Tier Episodic Memory** (`BM25 + Dense Cosine RRF`) pre-warms active lessons into `tier1_active_capsule.json` with `0 ms` startup latency. |

### 🧭 Choose Your Reading Path

| Reader Profile | Recommended Sections | What You Will Learn |
| :--- | :--- | :--- |
| **🟢 New User / Evaluator** | **[Part 1](#part-1-for-beginners-concepts-glossary--3-command-quickstart)** & **[Part 2](#part-2-interactive-step-by-step-tutorials-4-real-world-examples)** | Plain-language overview, zero-jargon glossary, quickstart, and 4 copy-paste tutorials. |
| **🔵 Product / Workflow Architect** | **[Part 3](#part-3-complete-panoramic-catalog-of-the-16-vocational-skills)** & **[Part 5](#part-5-architectural-protocols--system-regulations-crv-40--tensor-rsi)** | The 16 vocational skills (`[0]`..`[14]`), Auto-Brief Swarm FSM, and Triple-Speed Vibe Coding. |
| **🟣 Senior AI Engineer / Auditor** | **[Part 4](#part-4-core-engine-architecture--scripts-ecosystem-30-logical-modules--33-python-files)**, **[Part 6](#part-6-mathematical-foundations--tensor-rsi-2d-engine-senior--auditor-section)** & **[Part 7](#part-7-full-changelog-history--certification-matrix-108108-pass)** | The 33 Python core scripts, Tensor-RSI 2D equations, SBFL math, SLAs, and the 108 Golden Tests matrix. |

---

## Part 1: For Beginners (Concepts, Glossary & 3-Command Quickstart)

### What is Nexus Keystone in Plain Words?
Think of **Nexus Keystone (`NK-Hub`)** as an automated **Air Traffic Control Tower and Software Factory**.
The applications you want to create are the airplanes.
The Control Tower plans the blueprint, assembles the code inside a protected hangar (`.staging/`), and runs real flight tests.
If a part fails during testing, the diagnostic engine locates the broken line and repairs it automatically.
Once every check reaches `100.0%`, the tower moves the finished code into your external project folder.

### Friendly Zero-Jargon Glossary

| Term in `NK-Hub` | Simple Everyday Meaning | Technical Role in the System |
| :--- | :--- | :--- |
| **`NK-Hub` (Control Tower)** | The master brain that coordinates all specialists. | Meta-orchestration platform enforcing rules, routing, and quality gates. |
| **External Project Folder** | The separate folder where your actual app is created. | Isolated directory (`../NK_External_Projects/<AppName>`) required by `[RULE-PROJECT-ISOLATION]`. |
| **Staging Area (`.staging/`)** | A safe workbench where code is drafted before release. | Pre-production buffer validated by AST Guard and pytest prior to atomic commit. |
| **Vocational Nodes (`[0]`..`[14]`)** | 15 specialized AI experts (Designer, Builder, Auditor, etc.). | Modular skills in `.agents/skills/NK-*/SKILL.md` with strict read/write boundaries. |
| **Sovereign Tetralogy (4/4)** | The 4 living blueprints of your project. | `concept_map.md`, `structural_tree.md`, `implementation_plan.md`, and `repo_map.md` (plus `idea_canvas.md`). |
| **Tensor-RSI 2D** | The self-improvement engine that fixes mistakes until score is `100`. | Coupled metric engine ($\Delta_k = 0, Q(S_k) = 100.0$) across `4` levels and `5` domain profiles. |
| **Win32 2PC Commit** | A crash-proof switch that saves files only when everything works. | 64-bit Windows kernel Named Mutex atomic file promotion with Write-Ahead Log (`.wal`). |

### High-Level Visual Architecture
```mermaid
flowchart TD
    U["User Prompt or Verbal Trigger ('avvia nk')"] --> B["Fast-Stat Bootstrap Gate (<120ms / <50ms cached)"]
    B --> M["Master Dashboard ([0]..[14]) or Goal-Driven Router"]
    M --> P["Auto-Brief Swarm FSM (5 Turns -> Tetralogy 4/4)"]
    P --> S["Staging Builder (.staging/) + AST Guard"]
    S --> R["Tensor-RSI 2D Loop (SBFL Ochiai + Auto-Heal)"]
    R --> A["Read-Only Audit Swarm (SAST + Oracle L3 + Real DAST)"]
    A --> C["Win32 2PC Atomic Commit (64-bit Named Mutex)"]
    C --> E["External App Workspace (../NK_External_Projects/MyApp)"]
```

### Quickstart in 3 Terminal Commands

1. **Run the Fast-Stat Session Bootstrap (`< 120` ms cold / `< 50` ms cached):**
   ```powershell
   python -u scripts/nk_session_bootstrap.py
   ```
2. **Run Read-Only Health & Tensor-RSI Ecosystem Verification:**
   ```powershell
   python -u scripts/preflight_health_check.py --check-only
   python -u scripts/rsi_convergence_engine.py --verify
   ```
3. **Scaffold a New External Application:**
   ```powershell
   python -u scripts/external_project_scaffolder.py --name MyApp --target "../NK_External_Projects/MyApp"
   ```

---

## Part 2: Interactive Step-by-Step Tutorials (4 Real-World Examples)

This section walks you through four real scenarios so you can see how `NK-Hub` operates in practice.

### Tutorial 1: Starting the Environment in `< 120 ms` (`[RULE-00.5]`)

When you open the repository in Google Antigravity, type any of the **8 official verbal triggers**:
> **Verbal Triggers:** `"avvia ambiente nk"`, `"avvia nk hub"`, `"avvia nk"`, `"avvia hub"`, `"start nk"`, `"start hub"`, `"attiva nk"`, `"attiva ambiente nk"`

**What happens automatically in 3 steps:**
1. **Step 1 (Fast-Stat Gate):** The agent runs `scripts/nk_session_bootstrap.py` in `< 120` ms (`< 50` ms on cache hit). It verifies workspace isolation, purges expired `.wal` files, and sets `NK_MODEL_PROFILE=argon`.
2. **Step 2 (15-Node Master Dashboard):** The agent displays the interactive menu of 15 specialists (`[0]` to `[14]`):
   - **`[0] NK-Ideator`**: Conceptual Ideation, SCAMPER, STORM & `/grill-me` (L0).
   - **`[1] NK-App-UX-Architect`**: Macro-Architecture, 8px/HSL Design System & Generative UI (L3).
   - **`[2] NK-Backend-Architect`**: 2-Tier Kahn DAG Topologies, Pydantic v2 & OpenAPI 3.0 (L2).
   - **`[3] NK-Agent-Instruction-Forge`**: L1 Metaprompting & ASD-STE100 Skill Forge (`/learn`, `/boost`).
   - **`[4] NK-Python-Async-Builder`**: Primary Async Python Builder & Fast-Healing in `.staging/` (L2).
   - **`[5] NK-Delta-Architect`**: Surgical Post-Release Refiner in `.staging/` (1-Level Leaf Worker).
   - **`[6] NK-Security-Auditor`**: Read-Only SAST L1/L2/L3 Threat Auditor & CoVe Verifier.
   - **`[7] NK-Oracle-Evaluator`**: Deterministic Cold Evaluator (Gates 1-6) & L3 DOM Inspector (`/browser`).
   - **`[8] NK-Dynamic-Sandbox-StressTester`**: Real DAST Concurrency & Win32 Job Object Sandbox Runner.
   - **`[9] NK-Bug-Diagnostic-Engine`**: Spectrum-Based Fault Localization (SBFL Ochiai `< 80` tok) & RCA.
   - **`[10] NK-Plan-Aligner`**: Turn 4 Sovereign Tetralogy 4/4 Aligner & `--verify` Gate.
   - **`[11] NK-State-Router`**: Read-Only Kahn DAG Topological Verifier & SHA-256 Drift Detector.
   - **`[12] NK-Scribe`**: Post-Commit Documentation Engine, Changelog SSOT & AST Repo-Map Synchronizer.
   - **`[13] NK-Episodic-Memory-Engine`**: 3-Tier Episodic Memory (`ARCH`, `SEC`, `OPS`, `DEVX`) & RRF Retrieval.
   - **`[14] NK-Session-Controller`**: Session Supervisor, Sovereign Critic, Tensor-RSI & 6-Gate Reviewer.
3. **Step 3 (Two-Way Choice):**
   - **Direct Mode (`Modalità Diretta`):** Type a number from **`[0]` to `[14]`** to talk directly to one specialist.
   - **Goal-Driven Mode (`Modalità Goal-Driven`):** Just describe what you want to build in plain language.

---

### Tutorial 2: Building a Complete External App from Scratch (`/plan` $\to$ `/goal`)

Suppose you want to build a new application without writing a single line of boilerplate yourself.

1. **You write in chat:**
   ```text
   /plan Build a FastAPI customer quote manager with SQLite storage and PDF export
   ```
2. **External Isolation (`[RULE-PROJECT-ISOLATION]`):**
   The Hub invokes `scripts/external_project_scaffolder.py` to create `../NK_External_Projects/QuoteManager` with its own DDD tree (`src/core`, `src/api`, `tests/`, `nk_genome/`).
3. **5-Turn Auto-Brief Swarm FSM (`[RULE-03]`):**
   - **Turn 1 (Draft):** `NK-Ideator`, `NK-App-UX-Architect`, and `NK-Backend-Architect` draft `idea_canvas.md`, `concept_map.md`, and `structural_tree.md`.
   - **Turn 2 (Attack Swarm):** `NK-Security-Auditor` and `NK-Dynamic-Sandbox-StressTester` attack the design to expose edge cases early.
   - **Turn 3 (Refine):** The architects resolve all findings and lock the Pydantic v2 data contracts.
   - **Turn 4 (1:1 Alignment):** `NK-Plan-Aligner` certifies `implementation_plan.md` and displays the native plan artifact with a **`Proceed`** button (`[RULE-01.11]`).
   - **Turn 5 (Handoff):** You click **`Proceed`**, which immediately triggers the autonomous `/goal` build pipeline.
4. **Autonomous Build & Promotion (`[RULE-01.12]`):**
   `NK-Python-Async-Builder` writes the code in `.staging/`, runs real tests, converges Tensor-RSI to $\Delta_k = 0$, and promotes all files via `win32_2pc_engine.py`.

---

### Tutorial 3: Ultra-Fast UI & Script Tweaks in `< 500 ms` (`Mode C` Vibe-Sprint)

What if you only want a quick UI adjustment or a small helper function (`<= 150` lines of code)?
You do not wait for a heavy 5-turn architectural ceremony.

1. **You write in chat:**
   ```text
   Add a live status badge and currency formatter to the quote summary card
   ```
2. **Automatic Mode C Triage (`scripts/vibe_sprint_router.py`):**
   ```powershell
   python -u scripts/vibe_sprint_router.py --prompt "Add a live status badge" --files ui_card.py
   ```
   The router inspects the AST depth (`max_depth <= 1`) and line count (`<= 150` LOC), selecting **`MODE_C_VIBE_SPRINT`**.
3. **0 ms Memory Pre-Warming & `< 500 ms` Vibe-Check:**
   - The router injects active lessons from `nk_tracking/memory_3tier/tier1_active_capsule.json` in `< 2 ms`.
   - The builder edits `.staging/` and runs the single-process Tensor-RSI gate:
     ```powershell
     python -u scripts/rsi_convergence_engine.py --vibe-check .staging/scripts/vibe_sprint_router.py --json
     ```
   - AST Guard, SAST construct checks, and STE100 verification complete in **`~65 ms`** (`< 500 ms` SLA).

---

### Tutorial 4: Autonomous Bug Diagnosis & Self-Healing (`Mode B` + SBFL Ochiai)

Suppose an existing backend endpoint throws an unexpected error during testing.

```mermaid
sequenceDiagram
    participant Test as Pytest Runner (.staging/)
    participant Bridge as sbfl_pytest_bridge.py
    participant Heal as auto_heal_pipeline.py
    participant RSI as rsi_convergence_engine.py
    participant Commit as win32_2pc_engine.py
    Test->>Bridge: 1 Test Fails (ZeroDivisionError at line 42)
    Bridge->>Heal: Emits <80 token Ochiai Payload (suspiciousness = 1.0)
    Heal->>Heal: Creates SHA-256 Rollback Snapshot & patches line 42
    Heal->>RSI: Evaluates Delta_k and Q(S_k)
    RSI-->>Commit: Delta_k = 0, Q(S_k) = 100.0 (CONVERGED_OPTIMAL)
    Commit->>Commit: Atomic Win32 2PC Promotion to Production
```

1. **Fault Localization (`< 80` Tokens):**
   Instead of dumping thousands of traceback lines into the LLM context, `sbfl_pytest_bridge.py` emits a compact JSON payload:
   ```json
   {"loc": "src/pricing.py:42", "err": "ZeroDivisionError: division by zero", "ochiai": 1.0}
   ```
2. **Monotonic Snapshot & Rollback Protection:**
   Before applying any fix, `healing_snapshot_rollback.py` saves a SHA-256 snapshot in `snapshot_manifest.json`.
   If a fix attempt increases failures or introduces an AST violation, the engine rolls back instantaneously (`G2`).

### Operating Modes Summary Table

| Mode | Trigger / Condition | Speed & Scope | Active Verification Gates |
| :--- | :--- | :--- | :--- |
| **`Mode C` (Vibe-Sprint)** | `<= 150` LOC, `AST max_depth <= 1`, `0` critical imports | `< 500 ms` check, max `2` RSI retries | `ASTGuardValidator` + `--vibe-check` (`VIBE_SPRINT_MICRO_RSI`) |
| **`Mode B` (CRV Lite)** | Backend bugfix or targeted multi-file refactor | `< 15 s` healing loop, max `3` RSI retries | Staging + `SBFLPytestBridge` + `AutoHealPipeline` (`CODE_RSI`) |
| **`Mode A` (Sovereign CRV 4.0)** | `/plan`, `/goal`, new app or architectural release | Full 5-Turn FSM + 4 Macro-Phases, max `5` RSI retries | Full 6-Gate Cold Audit + SAST L1-L3 + Real DAST + Win32 2PC |

---

## Part 3: Complete Panoramic Catalog of the 16 Vocational Skills

Every skill in `.agents/skills/NK-*/SKILL.md` enforces `[RULE-STE100]`, `[RULE-RSI.1]`, and `GT-14` tool boundaries.

| Skill Name | Node | Role & Architectural Scope | CRV / FSM Phase | Tool Boundary (`GT-14`) | Tensor-RSI Profile (`<rsi_micro_loop>`) | Linked Auxiliary Files |
| :--- | :---: | :--- | :---: | :--- | :--- | :--- |
| [NK-Master-Hub](.agents/skills/NK-Master-Hub/SKILL.md) | L3 | 2-Tier Kahn DAG Router & Win32 2PC Committer | Macro 3 & 4 | Sovereign Committer | `L1` / `CODE_RSI` (`2/3/5`) | None |
| [NK-Ideator](.agents/skills/NK-Ideator/SKILL.md) | `[0]` | Ideation, SCAMPER, STORM & `/grill-me` | FSM Turn 1 | Confined to `nk_genome/` | `L1` / `SPEC_RSI` (`1/2/3`) | `resources/idea_canvas_template.md` |
| [NK-App-UX-Architect](.agents/skills/NK-App-UX-Architect/SKILL.md) | `[1]` | UX/UI 8px/HSL Design System & Generative UI | FSM Turn 1 | Confined to `nk_genome/` | `L1` / `UI_UX_RSI` (`2/2/3`) | None |
| [NK-Backend-Architect](.agents/skills/NK-Backend-Architect/SKILL.md) | `[2]` | 2-Tier Backend DAG, OpenAPI 3.0 & Pydantic v2 | FSM Turn 1 & 3 | Confined to `nk_genome/` | `L1` / `SPEC_RSI` (`1/2/3`) | None |
| [NK-Agent-Instruction-Forge](.agents/skills/NK-Agent-Instruction-Forge/SKILL.md) | `[3]` | ASD-STE100 Skill Forge & Meta-RSI (`/learn`) | FSM Turn 1 & 3 | Staging + Golden Eval | `L3` / `STE100_RSI` (`1/1/2`) | None |
| [NK-Python-Async-Builder](.agents/skills/NK-Python-Async-Builder/SKILL.md) | `[4]` | Primary Async Python Builder in `.staging/` | Macro 1 | `.staging/` Write Only | `L1` / `CODE_RSI` (`2/3/5`) | None |
| [NK-Delta-Architect](.agents/skills/NK-Delta-Architect/SKILL.md) | `[5]` | Surgical 4-Block Refiner in `.staging/` | Macro 1 | `.staging/` Write Only | `L1` / `VIBE_SPRINT` (`2/3/5`) | `resources/delta_brief_template.md` |
| [NK-Security-Auditor](.agents/skills/NK-Security-Auditor/SKILL.md) | `[6]` | SAST L1/L2/L3 Threat Auditor & CoVe Verifier | Macro 2 | 100% Strict Read-Only | `L0` / `CODE_RSI` (`1/2/3`) | `resources/audit_checklists_l1_l2_l3.md` |
| [NK-Oracle-Evaluator](.agents/skills/NK-Oracle-Evaluator/SKILL.md) | `[7]` | Cold Evaluator (Gates 1-6) & L3 DOM Inspector | Macro 2 | 100% Strict Read-Only | `L1` / `UI_UX_RSI` (`1/2/3`) | `references/anti_pattern_guards.md`, `references/verification_oracles.md` |
| [NK-Dynamic-Sandbox-StressTester](.agents/skills/NK-Dynamic-Sandbox-StressTester/SKILL.md) | `[8]` | Real DAST Concurrency in `%TEMP%\nk_sandbox_*` | Macro 2 | 100% Strict Read-Only | `L1` / `CODE_RSI` (`1/2/3`) | None |
| [NK-Bug-Diagnostic-Engine](.agents/skills/NK-Bug-Diagnostic-Engine/SKILL.md) | `[9]` | SBFL Ochiai RCA Localizer & False Bug Gate | Macro 1 & 2 | 100% Strict Read-Only | `L1` / `CODE_RSI` (`1/2/3`) | `resources/false_bug_rejection_rules.yaml`, `resources/rca_dual_language_template.md` |
| [NK-Plan-Aligner](.agents/skills/NK-Plan-Aligner/SKILL.md) | `[10]` | Tetralogy 4/4 Aligner & `--verify` Certifier | FSM Turn 4 | 100% Strict Read-Only | `L1` / `SPEC_RSI` (`1/1/2`) | None |
| [NK-State-Router](.agents/skills/NK-State-Router/SKILL.md) | `[11]` | Read-Only Kahn DAG Verifier & SHA-256 Drift | Macro 3 | 100% Strict Read-Only | `L0` / `CODE_RSI` (`1/1/2`) | None |
| [NK-Scribe](.agents/skills/NK-Scribe/SKILL.md) | `[12]` | Post-Commit SSOT, Repo-Map & Git Publisher | Post-Macro 3 | Doc & Tracking (`[RULE-00.2]`) | `L1` / `STE100_RSI` (`1/1/2`) | `resources/activity_anchor_schema.md`, `resources/scribe_knowledge.md` |
| [NK-Episodic-Memory-Engine](.agents/skills/NK-Episodic-Memory-Engine/SKILL.md) | `[13]` | 3-Tier Memory (`ARCH, SEC, OPS, DEVX`) & Capsule | Post-Macro 3 | Memory Ledger Only | `L2` / `SPEC_RSI` (`1/1/2`) | None |
| [NK-Session-Controller](.agents/skills/NK-Session-Controller/SKILL.md) | `[14]` | Session Supervisor, 5-Turn FSM & Cold Reviewer | FSM Turn 1-5 | Sovereign Critic | `L2` / `SPEC_RSI` (`2/3/5`) | `clean_handoff_protocol.md`, `handoff_anchor_schema.md`, `prompt_templates.md`, `saturation_thresholds.yaml` |

---

## Part 4: Core Engine Architecture & Scripts Ecosystem (`30 Logical Modules / 33 Python Files`)

All `33` Python files in `scripts/` use strict Pydantic v2 contracts and pass `108/108` Zero-Mock Golden Tests.

### 1. Runtime Defense, Session Governance & Tensor-RSI Convergence
- [`scripts/nk_session_bootstrap.py`](scripts/nk_session_bootstrap.py): Fast-Stat gate (`< 50` ms cached via `transcript_mtime` and `transcript_size`), `.wal` purge, root isolation check, and `NK_MODEL_PROFILE=argon` activation.
- [`scripts/rsi_convergence_engine.py`](scripts/rsi_convergence_engine.py): Tensor-RSI 2D engine with `RSIProfileRegistry`, $\Delta_k$ and $Q(S_k)$ math, and `G1..G6` guards. Supports `--vibe-check <target>`, CoVe CLI AST Gate (`verify_cli_flags_cove`), and STE100 validation (`--verify`).
- [`scripts/nk_active_runtime_sentinel.py`](scripts/nk_active_runtime_sentinel.py): Dual-Profile runtime step monitor (`60/85/100` standard, `120/180/250` argon) with subagent transcript filtering (`EXT-02`).
- [`scripts/nk_context_sentry.py`](scripts/nk_context_sentry.py): Dual-Profile token/step sentry (`70/100` standard, `150/250` argon excluding `thinking`) and subagent return MTU gate (`2000` chars).
- [`scripts/nk_compliance_checker.py`](scripts/nk_compliance_checker.py): Transcript auditor with `DDI_DIRECT_STREAK_LIMIT = 12`, `write_calls == 0` AST exemption, live `rsi_telemetry.jsonl` score reading, and `GT-08`/`GT-10` guards.
- [`scripts/preflight_health_check.py`](scripts/preflight_health_check.py): Maintenance diagnostic probe with `--check-only` CI mode and fail-closed baseline verification (`BS-01`).
- [`scripts/platform_runner.py`](scripts/platform_runner.py): Safe subprocess runner with automatic `-u` injection on list and string commands (`BS-04`) and UTF-8 stream normalization.
- [`scripts/env_capability_probe.py`](scripts/env_capability_probe.py): Runtime capability discovery separating `core_hub_modules` from `optional_app_modules` (`GT-09`).

### 2. Swarm IPC, Compaction & Handoff
- [`scripts/nk_swarm_messenger.py`](scripts/nk_swarm_messenger.py): Inter-agent formatter enforcing `1,800`-char MSS payload cap (`GT-04`), Head-Tail (`400 + 800`) fallback, and disk spillover.
- [`scripts/nk_session_handoff.py`](scripts/nk_session_handoff.py): Zero-amnesia handoff generator with workspace-bound `git` calls (`cwd=str(_workspace_root)`), optional `--transcript`/`--output-dir`, and dynamic test totals.
- [`scripts/nk_auto_inning.py`](scripts/nk_auto_inning.py): Inning closer passing `--transcript` and `--json` to `nk_compliance_checker.py` with fail-closed `compliance_score = 0` on exception.
- [`scripts/async_heartbeat_signaler.py`](scripts/async_heartbeat_signaler.py): Background heartbeat daemon and `45`s watchdog supporting `--task-id`, `--interval`, `--max-beats`, and `--once`.

### 3. Atomic Mutation & Win32 2PC Commit
- [`scripts/win32_2pc_engine.py`](scripts/win32_2pc_engine.py): 64-bit `ctypes` Win32 Named Mutex 2PC engine with `MOVEFILE_COPY_ALLOWED`, `age > 10s` recovery guard, and `--verify-baseline` pre-check.
- [`scripts/healing_snapshot_rollback.py`](scripts/healing_snapshot_rollback.py): Persistent `snapshot_manifest.json` manager with 8-char SHA-256 prefix and monotonic rollback gate.
- [`scripts/safe_cleanup_dev_servers.py`](scripts/safe_cleanup_dev_servers.py): Targeted dev server killer defaulting to `_workspace_root` (`--workspace-root`, `--dry-run`, `--json`) and protecting external processes.

### 4. Diagnostics, Verification & Fast-Healing
- [`scripts/sbfl_engine.py`](scripts/sbfl_engine.py): Ochiai, Tarantula, and DStar fault localization engine (`< 80` token diagnostic payload) with AST Def-Use slicing and CLI interface.
- [`scripts/sbfl_pytest_bridge.py`](scripts/sbfl_pytest_bridge.py): Windows space-safe traceback parser guaranteeing `suspiciousness == 1.0` and `< 320` chars (`GT-07`).
- [`scripts/auto_heal_pipeline.py`](scripts/auto_heal_pipeline.py): Multi-cycle healing orchestrator linked to `ASTGuardValidator` and `RSIConvergenceEngine` with telemetry logging in `rsi_telemetry.jsonl`.
- [`scripts/invisible_healing_loop.py`](scripts/invisible_healing_loop.py): Staging healing wrapper delegating to `auto_heal_pipeline.py`.
- [`scripts/oracle_evaluator_l3.py`](scripts/oracle_evaluator_l3.py): Pure Python HTML5 void-tag aware DOM parser and Windows drive path safe evaluator (`U-27`).
- [`scripts/micro_hud_renderer.py`](scripts/micro_hud_renderer.py): Single-line CP1252/UTF-8 safe telemetry renderer aligned with `MicroUIHUDState`.
- [`scripts/dast_sandbox_runner.py`](scripts/dast_sandbox_runner.py): 64-bit Win32 Job Object isolated process runner in `%TEMP%\nk_sandbox_*`.

### 5. Memory, Caching, AST & Schemas
- [`scripts/memory_3tier_engine.py`](scripts/memory_3tier_engine.py): 3-Tier memory with `DOMAIN_ALIAS_MAP` (`ARCH, SEC, OPS, DEVX`), `350`/`1200` token cap (`GT-05`), `tier1_active_capsule.json` sync, and full CLI (`--recall`, `--append`, `--tier1-sync`).
- [`scripts/deterministic_api_cache.py`](scripts/deterministic_api_cache.py): Persistent SQLite WAL connection cache with CLI (`--force-refresh`, `--stats`, `--clear`).
- [`scripts/quality_baseline_manager.py`](scripts/quality_baseline_manager.py): Fail-closed baseline ratchet (`108` Golden Tests) checking `sast_critical_violations` and `rsi_residual_delta` (`--file`, `--update`, `--check-only`).
- [`scripts/ast_guard_validator.py`](scripts/ast_guard_validator.py): Static AST scope checker tracking `function_depth`, supporting `--stage-dir`, and running `SASTConstructChecker` (`eval`, `exec`, `pickle.loads`, `yaml.load`, `MagicMock`).
- [`scripts/ast_repo_mapper.py`](scripts/ast_repo_mapper.py): PageRank AST repo-mapper serializing `edges` and supporting `4,000`-token `argon_mode_a` snapshots (`GT-06`).
- [`scripts/external_project_scaffolder.py`](scripts/external_project_scaffolder.py): External DDD project generator rejecting internal `NK-Hub` target paths (`BS-03`).
- [`scripts/vibe_sprint_router.py`](scripts/vibe_sprint_router.py): Mode A/B/C router computing true AST `max_depth` (`<= 150` LOC) and executing `load_prewarmed_capsule()` in `< 2 ms`.
- [`scripts/schemas/dual_ledgers.py`](scripts/schemas/dual_ledgers.py) & [`scripts/schemas/nk_ipc_contracts.py`](scripts/schemas/nk_ipc_contracts.py): 64-bit PID check (`ERROR_ACCESS_DENIED` safe) and unified Pydantic v2 IPC contracts (`RSIDefectVector`, `OchiaiDiagnosticPayload`).

---

## Part 5: Architectural Protocols & System Regulations (CRV 4.0 & Tensor-RSI)

### Core Binding Mandates (`.agents/AGENTS.md`)
1. **`[RULE-PROJECT-ISOLATION]`**: Application code is forbidden inside `NK-Hub`. Every app resides in `G:/Il mio Drive/NK_External_Projects/<Name>/`.
2. **`[RULE-00.4]` & `[RULE-00.5]`**: Every session starts with `nk_session_bootstrap.py` (`< 120` ms) and renders the 15-node Master Dashboard on verbal triggers.
3. **`[RULE-00]` & `[RULE-00.1]`**: Zero unauthorized edits on production files. Specifiers and Auditors are 100% read-only; Builders write only in `.staging/`.
4. **`[RULE-STE100]`**: Mandatory ASD-STE100 technical language (`<= 20` words per instruction sentence, active voice, zero spaced dashes).
5. **`[RULE-REACTIVE-SILENCE]`**: Polling loops (`manage_task(Action="status")`) are forbidden. Agents yield their turn or set event-driven timers.
6. **`[RULE-01]` & `[RULE-SWARM-HYGIENE]`**: 2-Tier single-level delegation (`enable_subagent_tools=False`), 12-call Fast-Track, and `1,800`-char MSS return limit.
7. **`[RULE-01.2]` & `[RULE-01.10]`**: Zero-Mock OS execution and permanent ratchet protecting all `108` Golden Tests at `100.0%` PASS.
8. **`[RULE-RSI]` & `[RULE-RSI.1]`**: Continuous Tensor-RSI 2D convergence ($\Delta_k = 0, Q(S_k) = 100.0$) across `4` levels and `5` domain profiles.

### Protocol CRV 4.0 (4 Macro-Phases) & 6 Cold Review Gates

| Phase / Gate | Responsible Node | Deterministic Verification Action |
| :--- | :--- | :--- |
| **Macro-Phase 1: Build & Stage** | `NK-Python-Async-Builder` / `NK-Delta-Architect` | Writes in `.staging/`, runs `ast_guard_validator.py --stage-dir` and `auto_heal_pipeline.py`. |
| **Macro-Phase 2: Unified Dynamic Audit** | `NK-Oracle-Evaluator`, `NK-Security-Auditor`, `NK-StressTester` | Executes 6 Cold Review Gates (`Scope`, `Code Grounding`, `Brief Grounding`, `Preservation`, `Truth/DAST`, `RSI Convergence`). |
| **Macro-Phase 3: 2PC Atomic Commit** | `NK-Master-Hub` | Verifies `quality_baseline.json` and promotes `.staging/` to production via `win32_2pc_engine.py`. |
| **Macro-Phase 4: Deterministic Teardown** | `NK-Master-Hub` & `NK-Scribe` | Purges `%TEMP%\nk_sandbox_*`, clears `.staging/`, updates `repo_map.md` (`4000` tok) and `PATCH_NOTES.md`. |

### Dual-Profile Runtime Calibration (`standard` vs `argon`)

| Parameter / Threshold | `standard` Profile (Golden Tests Default) | `argon` Profile (Production Runtime) |
| :--- | :---: | :---: |
| **Context Sentry (`WARN / HARD`)** | `70 / 100` steps (`GT-01`) | `150 / 250` steps (`250k / 500k` tokens, excluding `thinking`) |
| **Active Runtime Sentinel (`GREEN / CAUTION / CRIT / RED`)** | `<60 / 60-84 / 85-99 / >=100` steps (`GT-02`) | `<120 / 120-179 / 180-249 / >=250` steps |
| **Tier-1 Episodic Memory Token Cap** | `350` tokens (`GT-05`) | `1,200` tokens (`tier1_active_capsule.json`) |
| **AST Repo-Map Token Budgets (`Mode C / B / A`)** | `0 / 256 / 512 / 1,024` tokens (`GT-06`) | `0 / 512 / 1,500 / 4,000` tokens |

---

## Part 6: Mathematical Foundations & Tensor-RSI 2D Engine (Senior / Auditor Section)

### 1. Coupled Dual-Metric RSI Convergence ($\Delta_k$ and $Q(S_k)$)
At every iteration $k$, `scripts/rsi_convergence_engine.py` evaluates the defect vector $v_k = (\text{SAST}_k, T_{\text{fail},k}, C_k, H_k, M_k, L_k, G_k)$:

$$\Delta_k(p) = w_{\text{SAST}}^{(p)} \cdot \text{SAST}_k + w_{\text{test}}^{(p)} \cdot (T_{\text{fail},k} + C_k) + w_{H}^{(p)} \cdot H_k + w_{M}^{(p)} \cdot M_k + w_{L}^{(p)} \cdot L_k + w_{G}^{(p)} \cdot G_k$$

$$Q(S_k) = \text{round}\left(60.0 \cdot \frac{T_{\text{pass},k}}{\max(T_{\text{total},k}, 1)} + \frac{40.0}{1.0 + \Delta_k(p) / 25.0},\; 4\right)$$

The loop reaches `CONVERGED_OPTIMAL` exclusively when $\Delta_k(p) == 0$ and $Q(S_k) == 100.0$ (`G1`).
Hard regressions ($\text{SAST}_k > \text{SAST}_{k-1}$ or $T_{\text{fail},k} + C_k > T_{\text{fail},k-1} + C_{k-1}$) trigger immediate snapshot rollback (`G2`).

### 2. The Tensor-RSI 2D Architecture (`4 Levels L0..L3` $\times$ `5 Profiles P1..P5`)

#### Vertical Axis: 4 Operational Time Horizons (`L0..L3`)

| Level | Name | Execution Horizon | Primary Mechanism & Artifact |
| :---: | :--- | :--- | :--- |
| **`L0`** | **Pre-Execution Static Gate** | `< 80 ms` pre-flight check | `ASTGuardValidator` (`SASTConstructChecker`) + `verify_cli_flags_cove()` + `verify_ste100_compliance()`. |
| **`L1`** | **Intra-Task Micro-Loop** | `< 500 ms` (`Mode C`) / `< 15 s` (`Mode B`) | `auto_heal_pipeline.py` + `sbfl_pytest_bridge.py` + `rsi_convergence_engine.py --vibe-check`. |
| **`L2`** | **Inter-Session Reflexion** | Post-commit (`0 ms` next-session load) | `memory_3tier_engine.py --tier1-sync` persists `tier1_active_capsule.json`, pre-warmed by `vibe_sprint_router.py`. |
| **`L3`** | **Meta-RSI Skill Evolution** | Post-mortem audit (`/learn`, `/boost`) | `NK-Agent-Instruction-Forge` validates skill edits against `tests/evals/skill_golden_eval_set.json`. |

#### Horizontal Axis: 5 Domain Profiles in `RSIProfileRegistry` (`P1..P5`)

| Profile ID | Target Domain & Skills | Weights $(w_{\text{SAST}}, w_{\text{test}}, w_H, w_M, w_L, w_G)$ | Max Retries (`Mode C / B / A`) |
| :--- | :--- | :---: | :---: |
| **`CODE_RSI`** (Default `GT-11`) | Backend Python (`[4]`, `[6]`, `[8]`, `[9]`, `[11]`, Hub) | `(15, 10, 5, 2, 1, 1)` | `2 / 3 / 5` |
| **`VIBE_SPRINT_MICRO_RSI`** | Mode C Fast UI & Surgical Refiner (`[5]`, `--vibe-check`) | `(15, 10, 5, 0, 1, 0)` | `2 / 2 / 3` |
| **`SPEC_RSI`** | Architecture & Tetralogy 4/4 (`[0]`, `[2]`, `[10]`, `[13]`, `[14]`) | `(15, 5, 10, 2, 1, 5)` | `1 / 2 / 3` |
| **`UI_UX_RSI`** | Frontend, Design System & DOM L3 (`[1]`, `[7]`) | `(15, 8, 6, 2, 2, 1)` | `2 / 2 / 3` |
| **`STE100_RSI`** | Documentation, Changelog & Skill Forge (`[3]`, `[12]`) | `(15, 5, 8, 1, 3, 5)` | `1 / 1 / 2` |

### 3. Ochiai Spectrum SBFL & Hybrid RRF Memory Formulas
- **Ochiai Fault Localization (`scripts/sbfl_engine.py`):**
  $$S_{\text{Ochiai}}(s) = \frac{e_f(s)}{\sqrt{(e_f(s) + n_f(s)) \cdot (e_f(s) + e_p(s))}}$$
- **Reciprocal Rank Fusion (`scripts/memory_3tier_engine.py`, $k=60$):**
  $$\text{RRF\_Score}(d) = \sum_{m \in \{\text{BM25}, \text{Cosine}\}} \frac{1}{60 + r_m(d)}$$

### 4. Rigid SLA Latency Benchmarks (Measured on Windows 11 64-bit)

| Operation / Engine | Target SLA | Measured `v3.1.0-Tensor-RSI` Performance |
| :--- | :---: | :---: |
| **Fast-Stat Session Bootstrap (`nk_session_bootstrap.py`)** | `< 120 ms` (`< 50 ms` cached) | **`18 ms - 42 ms`** |
| **Mode C Single-Process Vibe-Check (`--vibe-check`)** | `< 500 ms` | **`65 ms`** |
| **Capsule Pre-Warming (`load_prewarmed_capsule`)** | `< 5 ms` | **`< 1.5 ms`** |
| **Full Ecosystem RSI & CoVe Verification (`--verify`)** | `< 2,000 ms` | **`410 ms`** |
| **Win32 2PC Atomic Promotion (`win32_2pc_engine.py`)** | `< 350 ms` | **`85 ms`** |
| **108 Permanent Golden Tests Suite (`pytest tests/ -q`)** | `< 25 s` | **`19.53 s` (`108/108 PASS`)** |

---

## Part 7: Full Changelog History & Certification Matrix (`108/108 PASS`)

### Release History Summary
- **v3.1.0-Tensor-RSI (Current)**: Introduces Tensor-RSI 2D (`[RULE-RSI.1]`), `RSIProfileRegistry` (`5` profiles), `--vibe-check` (`< 500 ms`), CoVe CLI AST Gate, and `tier1_active_capsule.json` pre-warming. Adds `idea_canvas.md`, `4,000`-token `repo_map.md`, `20`-word `[RULE-STE100]` enforcement (`GT-11..GT-14`), and **108 Permanent Golden Tests** (`108/108 PASS`).
- **v3.0.0-STE100-Unified**: Unifies Argon and Opus audits, `[RULE-STE100]`, `[RULE-RSI]`, Dual-Profile (`standard` vs `argon`), and 2-Tier topology. Cleans 39 orphan skill files, repairs all 29 scripts (`GT-01..GT-10`), and expands tests to **100 Golden Tests**.
- **v2.6.1-Controller-Hotfix**: SQLite resource closure, collision-proof snapshots, background task sentry filter, 79 Golden Tests.
- **v2.6.0-DualEngine-Symbiosis**: `/plan` and `/goal` integration, 4 adversarial shields, 3 fast-healing pillars, 79 Golden Tests.
- **v2.5.2-Hardened**: `[RULE-00.5]` Unified Onboarding Dashboard Mandate, `oracle_evaluator_l3.py`, `micro_hud_renderer.py`, 78 Golden Tests.

### Certified Golden Test Suite Matrix (`108/108 PASS`)

| # | Test File (`tests/`) | Tests | Protected Invariants & Guards | Status |
| :---: | :--- | :---: | :--- | :---: |
| 1 | `tests/test_ast_guard_validator.py` | 6 | AST Scope Integrity, `function_depth` (`U-20`), PEP 634/695 | 100.0% PASS |
| 2 | `tests/test_ast_repo_mapper.py` | 10 | PageRank, `edges` cache (`U-21`), Graduated Budgets (`GT-06`) | 100.0% PASS |
| 3 | `tests/test_auto_heal_pipeline.py` | 6 | SBFL Bridge (`GT-07`), Persistent Snapshot Manifest (`U-23`) | 100.0% PASS |
| 4 | `tests/test_active_sentinel_suite.py` | 4 | Sentinel States (`GT-02`), Swarm MSS `1800` (`GT-04`), Auto-Inning | 100.0% PASS |
| 5 | `tests/test_context_sentry.py` | 5 | Traffic Light `70/100` (`GT-01`), Subagent Return Filter (`U-02`) | 100.0% PASS |
| 6 | `tests/test_dast_sandbox.py` | 5 | 64-bit Win32 Job Objects (`U-24`), Process Tree Kill, Watchdog | 100.0% PASS |
| 7 | `tests/test_memory_3tier.py` | 7 | `DOMAIN_ALIAS_MAP` (`U-46`), `tier1_active_capsule.json`, `350` Cap (`GT-05`) | 100.0% PASS |
| 8 | `tests/test_platform_upgrades.py` | 4 | Capability Probe `total_probed` (`GT-09`), Safe Runner, `pytest.ini` | 100.0% PASS |
| 9 | `tests/test_sbfl_engine.py` | 7 | Ochiai/Tarantula/DStar Precision, `< 80` Token Payload, CLI | 100.0% PASS |
| 10 | `tests/test_schemas_and_contracts.py` | 5 | Pydantic v2 Strict Mode, 64-bit PID Check (`U-25`), IPC Contracts | 100.0% PASS |
| 11 | `tests/test_super_brief_upgrades.py` | 6 | Bootstrap, Scaffolder, Cache, Compliance Default `100` (`GT-10`) | 100.0% PASS |
| 12 | `tests/test_unified_onboarding_mandate.py` | 4 | `[RULE-00.5]` 8 Triggers, 15 Hub Nodes, Boundary 10 (`GT-08`) | 100.0% PASS |
| 13 | `tests/test_win32_2pc.py` | 7 | 64-bit Named Mutex, `MOVEFILE_COPY_ALLOWED`, `mkdtemp` Isolation | 100.0% PASS |
| 14 | `tests/stress/test_real_sandbox_stress.py` | 4 | Swarm Flooder, Monolithic Spammer `> 12` (`GT-03`), Escalator (`GT-01`) | 100.0% PASS |
| 15 | `tests/test_rsi_convergence_engine.py` | 11 | `RSIProfileRegistry`, `--vibe-check`, CoVe AST, Heartbeat CLI, `GT-11..12` | 100.0% PASS |
| 16 | `tests/test_preflight_health_check.py` | 2 | Fail-Closed on Corrupt Baseline (`BS-01`) & `--check-only` Mode | 100.0% PASS |
| 17 | `tests/test_quality_baseline_manager.py` | 3 | Corrupt JSON (`BS-02`), `LOWER_IS_BETTER_KEYS`, CLI Flags (`GT-13`) | 100.0% PASS |
| 18 | `tests/test_external_scaffolder.py` | 2 | Internal Hub Path Rejection (`BS-03`) & External `nk_genome/` Tree | 100.0% PASS |
| 19 | `tests/test_platform_runner.py` | 2 | String Command `-u` Injection (`BS-04`) & Timeout Tree-Kill | 100.0% PASS |
| 20 | `tests/test_deterministic_api_cache.py` | 2 | Persistent SQLite WAL Connection (`BS-05`) & TTL Expiration | 100.0% PASS |
| 21 | `tests/test_safe_cleanup_dev_servers.py` | 2 | Workspace CWD/Cmdline Filter (`U-13`) & Current PID Protection | 100.0% PASS |
| 22 | `tests/test_env_capability_probe.py` | 1 | `core_hub_modules` vs `optional_app_modules` & `GT-09` Invariance | 100.0% PASS |
| 23 | `tests/test_vibe_sprint_router.py` | 2 | True AST `max_depth` (`U-10`), Mode A/B/C & Capsule Pre-Warming | 100.0% PASS |
| 24 | `tests/test_oracle_l3_and_hud.py` | 1 | HTML5 Void Tags & Windows Path Split (`U-27`) + Micro-HUD Render | 100.0% PASS |
| **Total** | **24 Permanent Test Files** | **108** | **100% Coverage of All 30 Core Modules (Zero-Mock)** | **108/108 PASS** |

---
*Generated by NK-Scribe | Nexus Keystone Hub (`v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified`)*

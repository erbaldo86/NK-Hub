# 🏛️ NK Genome: Structural Tree & Swarm Topology (Ecosistema NK — Release v1.0)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]  
> **Data Consolidamento:** 2026-08-20  
> **Versione:** v1.0 (Official Baseline Release, Self-Cleaning Ecosystem, Brief-Aware Handoff, Actor-Critic & CRV 4.0 4-Phases)  
> **Target System:** Ecosistema NK Multi-Agent Swarm Runtime

---

## 🌳 1. Struttura del Workspace & File di Governance

```
G:/Il mio Drive/Antigravity/
├── .agents/
│   ├── AGENTS.md                                 # Regolamento Master di Sistema v1.0 (Self-Cleaning)
│   └── skills/                                   # 16 Skill Canoniche Attive (+ 6 Tombstone Stub)
│       ├── NK-Session-Controller/               # Sovereign Critic & Supervisor
│       │   ├── SKILL.md                          # Istruzioni del Critico v2.0
│       │   └── resources/
│       │       ├── clean_handoff_protocol.md     # Specifiche Template 8A/8B/9/10 v2.0
│       │       ├── prompt_templates.md           # Prompt standard v2.0
│       │       └── handoff_anchor_schema.md      # Schema JSON Manifest v2.0
│       ├── NK-Delta-Architect/                   # Grounded Worker post-rilascio
│       │   └── SKILL.md                          # Istruzioni Worker Two-Stage Grounding v2.0
│       ├── NK-Master-Hub/                        # Sovereign L3 Orchestrator & Kahn DAG Router
│       ├── NK-Ideator/                           # L0 Concept Ideation & STORM / SCAMPER
│       ├── NK-App-UX-Architect/                  # L3 UX/UI & Concept Specifier
│       ├── NK-Backend-Architect/                 # L2 Backend Topology & OpenAPI 3.0
│       ├── NK-Agent-Instruction-Forge/           # L1 Unified System Instructions & Prompt Forge
│       ├── NK-Python-Async-Builder/              # L2 Async & Pydantic v2 Builder
│       ├── NK-Security-Auditor/                  # Audit TAS L1/L2/L3 Unificato
│       ├── NK-Oracle-Evaluator/                  # Cold Auditor Deterministico (CRV 4.0)
│       ├── NK-Dynamic-Sandbox-StressTester/      # Real DAST Concurrency Engine
│       ├── NK-Bug-Diagnostic-Engine/             # RCA & False Bug Rejection
│       ├── NK-Plan-Aligner/                      # Audit Allineamento Trittico 1:1 (Turn 4 FSM)
│       ├── NK-State-Router/                      # Sincronizzazione Stato & Backup Circolare
│       ├── NK-Scribe/                            # Manutenzione Changelog & Documentazione
│       └── NK-Episodic-Memory-Engine/            # Memoria Episodica a Lungo Termine
├── scripts/                                      # Script di governance deterministica
│   ├── preflight_health_check.py                 # Pre-Flight Auto-Sanitizer (RULE-02.3.1)
│   ├── quality_baseline_manager.py               # Ratchet Baseline Manager (RULE-01.9)
│   └── semantic_ast_analyzer.py                  # Static AST Syntax Analyzer
├── nk_genome/                                    # Documentazione concettuale (Trittico)
│   ├── concept_map.md                            # Visione & Architettura Concettuale
│   ├── structural_tree.md                        # Mappa Strutturale & Vocazioni
│   └── implementation_plan.md                    # Piano Esecutivo & Milestone Anchor IDs
├── nk_tracking/                                  # Audit, Tracciamento & Memoria
│   ├── anchor/
│   │   └── session_anchor.jsonl                  # Registro deterministico azioni (SSOT)
│   ├── reports_and_briefs/                       # Report di audit e handoff manifest (Rolling Window Max 3)
│   ├── quality_baseline.json                     # Metriche di qualità e non-regressione
│   └── nk_tas_roi.db                             # Database SQLite WAL
├── .staging/                                     # Area di staging isolata (CRV 4.0)
└── src_app/                                      # Codice sorgente applicativo
```

---

## 🐝 2. Swarm Topology & Asymmetric Actor-Critic Architecture

```mermaid
graph TD
    User["Developer / User Interface"] <--> Critic["NK-Session-Controller (Sovereign Critic)"]
    
    subgraph Critic_Council["Critic Cognitive Council"]
        Critic -->|invoke_subagent| DAST["DAST Investigator"]
        Critic -->|invoke_subagent| Arch["Solution Architect"]
        Critic -->|invoke_subagent| Skeptic["Skeptic Devil's Advocate"]
        Critic -->|invoke_subagent| Gatekeeper["Transcript Gatekeeper"]
    end
    
    Critic -->|Template 8A Brief-Aware| Worker["NK-Delta-Architect (Grounded Worker)"]
    
    subgraph Worker_Execution["Worker Isolation & Staging Area"]
        Worker -->|Stage A Grounding| PlanDoc["implementation_plan.md"]
        Worker -->|Stage B Grounding| CodeFiles["Physical Source Files"]
        Worker -->|invoke_subagent| Builder["NK-Agent-Instruction-Forge / Async Builder"]
        Builder -->|Write isolated| Staging[".staging/ Area"]
        Worker -->|invoke_subagent| Oracle["NK-Oracle-Evaluator"]
        Staging --> Oracle
    end
    
    Oracle -->|PASS (exit_code: 0)| Worker
    Worker -->|Worker Execution Receipt v2.0| Critic
    Critic -->|Cold Review 5 Gates PASS| Commit["Atomic Commit (os.replace) via NK-Master-Hub"]
```

---

## ⚙️ 3. Matrice delle Vocazioni & Permessi I/O (16 Skill Canoniche)

| Ruolo / Sub-Agente | Livello / Vocazione | Trigger di Attivazione | Permessi I/O & Sandbox |
| :--- | :--- | :--- | :--- |
| `NK-Session-Controller` | Sovereign Critic & Orchestrator | Avvio sessione, handoff, cold review | Read-Only su codice; Scrittura su `nk_tracking/` e manifest |
| `NK-Master-Hub` | Sovrano Infrastrutturale L3 | Boot IDE, commit atomico, Kahn DAG | Read-Only codice; Commit atomico da `.staging/` a `src_app/` |
| `NK-Delta-Architect` | Grounded Worker & Post-Release Triage | Ricezione Template 8A (v2.0) | Read-Only diretto; Delega builder in `.staging/`; Ricevuta v2.0 |
| `NK-Ideator` | L0 Ideazione & SCAMPER | Avvio ideazione, Turn 1 FSM | Strict Read-Only; Output `nk_genome/idea_canvas.md` |
| `NK-App-UX-Architect` | L3 Macro-UX/UI & Design System | Design Bounded Context, Stitch prompt | Strict Read-Only; Output Trittico e `ui_consolidated_spec.json` |
| `NK-Backend-Architect` | L2 Backend Topology & OpenAPI 3.0 | Progettazione rotte API e DB schemas | Strict Read-Only; Output specifiche tecniche tipizzate |
| `NK-Agent-Instruction-Forge`| L1 Prompt & System Instructions Forge | Creazione e modifica prompt agenti | Scrittura ESCLUSIVAMENTE in `.staging/` |
| `NK-Python-Async-Builder` | L2 Async, API & Pydantic v2 Builder | Sviluppo codice applicativo Python | Scrittura ESCLUSIVAMENTE in `.staging/` |
| `NK-Security-Auditor` | Audit TAS L1/L2/L3 Unificato | Macro-Fase 2 CRV 4.0 / Pre-commit | Strict Read-Only su codice; Scrittura report in `nk_tracking/` |
| `NK-Oracle-Evaluator` | Cold Auditor Deterministico (Gate 4) | Validazione patch pre-commit | Isolamento in `"%TEMP%/sandbox_[UUID]/"` |
| `NK-Dynamic-Sandbox-StressTester` | Real DAST Concurrency Engine | Stress testing dinamico Macro-Fase 2 | Isolamento in `"%TEMP%/sandbox_[UUID]/"` |
| `NK-Bug-Diagnostic-Engine` | RCA Engine & False Bug Rejection | Diagnosi anomalie pre-sviluppo | Strict Read-Only; Report RCA in `nk_tracking/` |
| `NK-Plan-Aligner` | Allineamento 1:1 del Trittico 3/3 | Turn 4 dell'Auto-Brief Swarm FSM | Strict Read-Only su `nk_genome/`; Report in `nk_tracking/` |
| `NK-State-Router` | Unified State Router & Kahn DAG | Rilevamento drift di stato | Sole Owner lock Backup Circolare v5.0 |
| `NK-Scribe` | Tracking Sessione, Patch Notes & Git | Post-Commit Atomico Macro-Fase 3 | Scrittura su `session_anchor.jsonl`, `PATCH_NOTES.md`, `README.md` |
| `NK-Episodic-Memory-Engine`| Memoria Episodica a Lungo Termine | Recall/Index frammenti di memoria | Scrittura in `System_Documentation/NK_Episodic_Memory/` |

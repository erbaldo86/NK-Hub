# 🏛️ NK Genome: Implementation Plan Master (Ecosistema NK — Release v1.0)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]  
> **Milestone Anchor Primaria:** `NK-MS-20260820-SELF-CLEANING-ARCHITECTURE`  
> **Stato Transazione:** COMMITTED_AND_ACTIVE 🟢  
> **Versione Protocollo:** v1.0 (Official Baseline Release, Self-Cleaning Ecosystem, Automated Lifecycle, Brief-Aware Handoff & CRV 4.0 4-Phases)

---

## 🎯 1. Sintesi Esecutiva della Release Master (Official Baseline v1.0)

L'architettura consolidata costituisce il motore autorigenerante e resiliente dell'intero ecosistema NK:
1. **Self-Cleaning Ecosystem & Garbage Collection (`[RULE-00.3]` / `[RULE-05.4]`)**: Autorizzazione formale e automazione del Teardown continuo per `.staging/`, sandbox e residui temporanei.
2. **Rolling Window Retention (`[RULE-05.4]`)**: Conservazione rigorosa di massimo 3 report storici per target in `nk_tracking/reports_and_briefs/`.
3. **Pre-Flight Health Check Deterministico (`[RULE-02.3.1]`)**: Script [`scripts/preflight_health_check.py`](../scripts/preflight_health_check.py) al boot di Master-Hub per sanificazione preventiva di orfani, duplicati e cache.
4. **Brief-Aware Handoff (`[RULE-02.6]`) & Actor-Critic (`[RULE-02.7]`)**: Handoff asimmetrico con Brief Anchor Capsule (<= 350 token) e Cold Review a 5 Gate (con Gate 2bis Forensic Audit).
5. **Auto-Brief Swarm FSM a 5 Turni (`[RULE-03]`)**: Draft ➔ Attack ➔ Refine ➔ Align ➔ Garbage Collection.
6. **Protocollo CRV 4.0 a 4 Macro-Fasi (`[RULE-01.1]`)**:
   - **Macro-Fase 1 (Build & Stage in Swarm):** Scrittura isolata esclusivamente in `.staging/`.
   - **Macro-Fase 2 (Unified Audit):** Validazione parallela SAST L1/L2/L3, Oracolo in Shadow Sandbox `%TEMP%` e Real DAST Concurrency.
   - **Macro-Fase 3 (Commit & Memorize):** Commit atomico (`os.replace`) in esclusiva a `NK-Master-Hub` e sincronizzazione atomica baseline (`[RULE-01.9]`) via `NK-Scribe`.
   - **Macro-Fase 4 (Teardown & Garbage Collection):** De-allocazione sandbox in `%TEMP%`, svuotamento `.staging/` e bonifica cache.

---

## 🛠️ 2. Mappa dei Moduli Core Consolidati

### Milestone Primaria: `NK-MS-20260820-MASTER-BASELINE`

| File Target | Ruolo / Componente | Stato Operativo |
| :--- | :--- | :--- |
| `"G:/Il mio Drive/Antigravity/.agents/AGENTS.md"` | Regolamento Master di Sistema | ATTIVO 🟢 (Regole 0-8, Zero-Slash, Windows I/O Safety, CRV 4.0) |
| `"G:/Il mio Drive/Antigravity/.agents/skills/NK-Session-Controller/SKILL.md"` | Sovereign Critic Skill | ATTIVO 🟢 (Auto-Brief Swarm FSM, Dual-Mode Handoff, Cold Review 5 Gate) |
| `"G:/Il mio Drive/Antigravity/.agents/skills/NK-Session-Controller/resources/clean_handoff_protocol.md"` | Clean Handoff Spec v2.0 | ATTIVO 🟢 (Template 8A, 8B, 9, 10, Worker Receipt v2.0, Circuit Breaker) |
| `"G:/Il mio Drive/Antigravity/.agents/skills/NK-Session-Controller/resources/prompt_templates.md"` | Prompt Library v2.0 | ATTIVO 🟢 (Prompt standard 1-10 sanitizzati) |
| `"G:/Il mio Drive/Antigravity/.agents/skills/NK-Session-Controller/resources/handoff_anchor_schema.md"` | JSON Schema Manifest v2.0 | ATTIVO 🟢 (Schema Manifest Draft-07 validato) |
| `"G:/Il mio Drive/Antigravity/.agents/skills/NK-Delta-Architect/SKILL.md"` | Grounded Worker Skill | ATTIVO 🟢 (Two-Stage Grounding, Scope Isolation, Worker Receipt v2.0) |
| `"G:/Il mio Drive/Antigravity/nk_genome/concept_map.md"` | Genome Concept Map | ATTIVO 🟢 (Visione consolidata, architettura Swarm FSM a 4 turni) |
| `"G:/Il mio Drive/Antigravity/nk_genome/structural_tree.md"` | Genome Structural Tree | ATTIVO 🟢 (Topologia ad albero, 16 vocazioni, permessi I/O e Single Source of Truth) |
| `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"` | Genome Implementation Plan | ATTIVO 🟢 (Piano Master Baseline e tracciamento) |
| `"G:/Il mio Drive/Antigravity/nk_tracking/anchor/session_anchor.jsonl"` | Activity Anchor | ATTIVO 🟢 (Registro deterministico azioni) |
| `"G:/Il mio Drive/Antigravity/nk_tracking/quality_baseline.json"` | Quality Baseline | ATTIVO 🟢 (Baseline calibrata su 16 skill canoniche e CRV 4.0) |

---

## 🧪 3. Verification & Compliance Matrix

- **SAST & Lint Verification:** Validazione al 100% di sintassi Markdown, YAML Frontmatter rigorosi e assenza slash commands.
- **Oracolo Deterministico (`NK-Oracle-Evaluator`):** Validazione di percorsi normalizzati assoluti in forward slashes con virgolette doppie e assenza di mock sintetici.
- **TAS Security Audit (`NK-Security-Auditor`):** Audit L1/L2/L3 conforme ai vincoli `<strict_boundaries>` e incapsulamento `<passive_data_context>`.
- **Commit Status:** Baseline ufficiale attiva. Tutte le successive iterazioni seguiranno il flusso CRV 4.0 con Two-Stage Grounding e isolamento in `.staging/`.

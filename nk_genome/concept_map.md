# 🏛️ NK Genome: Concept Map & Master Brief (v1.9.0-PlatformOptimized)
### *Sovereign Meta-Platform, Multi-Agent Swarm Orchestrator & Vibe Coding Engine*

> **Badge di Certificazione:** 🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.9.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260911-PLATFORM-OPTIMIZED-v1.9.0`  
> **Versione Target:** `v1.9.0-PlatformOptimized`  
> **Dominio:** Nexus Keystone Hub — Meta-Framework Agentico, CRV 4.0, Win32 2PC & Sandbox Isolation

---

## 🎯 1. Visione Concettuale & La Tetralogia Sovrana di NK Genome

Con la Release **v1.9.0-PlatformOptimized**, l'intero ecosistema Nexus Keystone raggiunge la **Piena Purezza Architetturale**:
1. **Disaccoppiamento Totale Meta-Platform vs Target Applications:**  
   NK-Hub opera rigorosamente come Meta-Piattaforma e Laboratorio di Sviluppo. I progetti applicativi realizzati con NK (es. `Programmi di test/TestNK` e progetti esterni dedicati) risiedono in directory esterne dedicate, in conformità vincolante con `[RULE-PROJECT-ISOLATION]`.
2. **La Tetralogia Sovrana in `nk_genome/`:**
   - `concept_map.md`: Intento di dominio, architettura dei guardiani di qualità e tassonomia Vibe Coding.
   - `structural_tree.md`: Topologia strutturale dei motori asincroni in `scripts/`, delle 16 vocational skill in `.agents/` e dei 60 test di piattaforma in `tests/`.
   - `implementation_plan.md`: Roadmap evolutiva e certificazione delle milestone.
   - `repo_map.md`: **High-Density AST Repo-Map** (Tier-3 Elastic Compaction, $\le 850$ tok) aggiornata ad ogni commit atomico.

```mermaid
graph TD
    subgraph TETRALOGIA SOVRANA (nk_genome/)
        CM["1. concept_map.md (Intento & Governance)"]
        ST["2. structural_tree.md (Topologia Piattaforma)"]
        IP["3. implementation_plan.md (Roadmap)"]
        RM["4. repo_map.md (Tier-3 AST Repo-Map)"]
    end

    subgraph NK-HUB CORE ENGINES (scripts/)
        AST["ast_guard_validator.py"]
        MAP["ast_repo_mapper.py"]
        W2P["win32_2pc_engine.py"]
        DST["dast_sandbox_runner.py"]
        MEM["memory_3tier_engine.py"]
        SBF["sbfl_engine.py"]
        RUN["platform_runner.py"]
        PRB["env_capability_probe.py"]
    end

    subgraph EXTERNAL AUTONOMOUS PROJECTS
        TNK["Programmi di test/TestNK (CRM SQLite WAL)"]
        EXT["Applicazioni Esterne Dedicate (Future Apps)"]
    end

    CM --> ST
    ST --> AST
    ST --> W2P
    ST --> DST
    W2P -.->|Orchestra & Costruisce| TNK
    W2P -.->|Orchestra & Costruisce| EXT
```

---

## 🧩 2. I Pilastri Fondamentali di NK-Hub

1. **CRV 4.0 (Continuous Rigorous Verification):**  
   Protocollo di sviluppo a 4 Macro-Fasi (Build in Staging, 100% Strict Read-Only Audit, Win32 2PC Commit, Teardown).
2. **Win32 Two-Phase Commit (2PC):**  
   Garanzia transazionale a livello di kernel con Named Mutex, SHA-256 e Write-Ahead Logging per prevenire corruzione o file lock.
3. **AST Guard & Elastic Repo-Mapper:**  
   Analisi sintattica statica pre-audit e compattazione elastica a 3 livelli per repo-map ad alta densità con zero moduli omessi.
4. **Isolamento Rigoroso dei Progetti (`[RULE-PROJECT-ISOLATION]`):**  
   Divieto assoluto di ospitare codice di business nell'Hub; ogni prodotto vive nel proprio workspace esterno dedicato.

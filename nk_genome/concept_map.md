# 🏛️ NK Genome: Concept Map & Master Brief (v2.1.0-FastHealing)
### *Sovereign Meta-Platform, Multi-Agent Swarm Orchestrator & Fast-Healing Engine*

> **Badge di Certificazione:** 🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v2.1.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260915-FAST-HEALING-v2.1.0`  
> **Versione Target:** `v2.1.0-FastHealing`  
> **Dominio:** Nexus Keystone Hub — Meta-Framework Agentico, CRV 4.0, Win32 2PC, DAST Isolation, 3-Pillar Fast-Healing & 61 Golden Tests

---

## 🎯 1. Visione Concettuale & La Tetralogia Sovrana di NK Genome

Con la Release **v2.1.0-FastHealing**, l'ecosistema Nexus Keystone raggiunge la **Piena Maturità Reattiva e Diagnostica Zero-Mock**:
1. **Disaccoppiamento Totale Meta-Platform vs Target Applications:**  
   NK-Hub opera rigorosamente come Meta-Piattaforma e Laboratorio di Sviluppo. I progetti applicativi realizzati con NK risiedono in directory esterne dedicate, in conformità vincolante con `[RULE-PROJECT-ISOLATION]`.
2. **I 3 Pilastri di Auto-Guarigione Reale (Fast-Healing v2.1.0):**
   - **Universal CLI Auto-Healer Pipeline (`scripts/auto_heal_pipeline.py`):** Orchestratore CLI con limite di 3 cicli e logging conforme per `PATCH_NOTES.md` nel progetto target.
   - **Pytest Coverage & SBFL Ochiai Bridge (`scripts/sbfl_pytest_bridge.py`):** Estrazione automatica della matrice di copertura da traceback Pytest e diagnosi Ochiai `< 80` token BPE.
   - **Staging Snapshot & Transactional Rollback Engine (`scripts/healing_snapshot_rollback.py`):** Snapshot atomico SHA-256 e Strict Monotonic Fitness Gate con ripristino istantaneo in caso di regressione.
3. **Razionalizzazione della Suite Permanente (61 Test Golden Super-Hardened):**
   - Eliminazione dei 4 test obsoleti/deboli in-memory di `test_invisible_healing_loop.py`.
   - Integrazione dei 6 test permanenti Zero-Mock di `test_auto_heal_pipeline.py`.
   - Eliminazione di 6 duplicazioni cross-file e accorpamento dello Slicer Karpathy su soglie parametrizzate.
   - Bugfix critico in `ast_guard_validator.py` per decoratori e default arguments.
   - Latenza complessiva ridotta del 45% (da 24s a <13s).

```mermaid
graph TD
    subgraph TETRALOGIA SOVRANA (nk_genome/)
        CM["1. concept_map.md (Intento & Governance v2.1.0)"]
        ST["2. structural_tree.md (Topologia Piattaforma & 61 Test)"]
        IP["3. implementation_plan.md (Roadmap Fast-Healing)"]
        RM["4. repo_map.md (Tier-3 AST Repo-Map)"]
    end

    subgraph NK-HUB CORE ENGINES (scripts/)
        AST["ast_guard_validator.py (Scope Guard Hardened)"]
        MAP["ast_repo_mapper.py"]
        W2P["win32_2pc_engine.py"]
        DST["dast_sandbox_runner.py"]
        MEM["memory_3tier_engine.py"]
        SBF["sbfl_engine.py"]
        RUN["platform_runner.py (Unbuffered UTF-8)"]
        PRB["env_capability_probe.py"]
        AHP["auto_heal_pipeline.py (Pilastro 1)"]
        SPB["sbfl_pytest_bridge.py (Pilastro 2)"]
        HSR["healing_snapshot_rollback.py (Pilastro 3)"]
    end

    subgraph VERIFICATION & RATINGS (tests/)
        TST["61 Golden Tests (100% PASS Ratchet)"]
    end

    CM --> ST
    ST --> AHP
    AHP --> SPB
    AHP --> HSR
    ST --> TST
```

---

## 🧩 2. I Pilastri Fondamentali di NK-Hub v2.1.0

1. **CRV 4.0 (Continuous Rigorous Verification):**  
   Protocollo di sviluppo a 4 Macro-Fasi (Build in Staging, 100% Strict Read-Only Audit, Win32 2PC Commit, Teardown).
2. **Win32 Two-Phase Commit (2PC):**  
   Garanzia transazionale a livello di kernel con Named Mutex, SHA-256 e Write-Ahead Logging per prevenire corruzione o file lock.
3. **Fast-Healing Loop Zero-Mock:**  
   Ciclo automatico di correzione guidato da SBFL Ochiai su file reali e protetto da Strict Monotonic Fitness Gate con ripristino atomico.
4. **Isolamento Rigoroso dei Progetti (`[RULE-PROJECT-ISOLATION]`):**  
   Divieto assoluto di ospitare codice di business nell'Hub; ogni prodotto vive nel proprio workspace esterno dedicato con changelog isolato.

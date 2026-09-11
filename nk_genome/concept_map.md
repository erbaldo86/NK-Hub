# 🏛️ NK Genome: Concept Map & Master Brief (v1.8.0-ModularStable)
### *Nuova Baseline Stabile Ufficiale & Architettura a Blocchi De-monolitizzata*

> **Badge di Certificazione:** 🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.8.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260911-MODULAR-STABLE-BASELINE-v1.8.0`  
> **Versione Target:** `v1.8.0-ModularStable`  
> **Dominio:** LabNK Bandi Intelligence & Decision Engine — Architettura Modulare DDD, Dual Search Engine & Federated Ingestion

---

## 🎯 1. Visione Concettuale & La Tetralogia Sovrana di NK Genome

Con la Release `v1.8.0-ModularStable`, l'intero ecosistema LabNK e la piattaforma di supporto raggiungono lo stato di **Nuovo Punto di Partenza Stabile Ufficiale**. Tutte le implementazioni e strutture monolitiche precedenti sono formalmente archiviate come legacy, mentre l'architettura a blocchi de-monolitizzata in `src_app/` costituisce la Single Source of Truth (SSOT).

La Tetralogia Sovrana in `nk_genome/` definisce e custodisce le fondamenta del sistema:
1. `concept_map.md`: Intento di dominio, Bounded Contexts, architettura duale di ricerca e requisiti di business.
2. `structural_tree.md`: Topologia strutturale dei 12 moduli DDD di `src_app/`, contratti di interfaccia, motori infrastrutturali e suite di test.
3. `implementation_plan.md`: Certificazione delle macro-fasi completate e roadmap per le future evoluzioni incrementali.
4. `repo_map.md`: **High-Density AST Repo-Map** aggiornata e generata autonomamente (`[RULE-01.13]`), rappresentante il grafo sintattico effettivo dei simboli.

```mermaid
graph TD
    subgraph TETRALOGIA SOVRANA (nk_genome/)
        CM["1. concept_map.md (Intento & Bounded Contexts)"]
        ST["2. structural_tree.md (Topologia 12 Moduli DDD)"]
        IP["3. implementation_plan.md (Roadmap & Status)"]
        RM["4. repo_map.md (High-Density AST Graph)"]
    end

    subgraph CORE APPLICATION ARCHITECTURE (src_app/)
        API["api/ (FastAPI Routers, Schemas & Factory)"]
        CAT["catalog/ (Repository & Seed Loader)"]
        CON["connectors/ (B2B Federated Scrapers & APIs)"]
        ING["ingestion/ (Async Orchestrator & Nightly Scheduler)"]
        SEA["search/ (Linguistics, ATECO & Parametric Engine)"]
        UI["ui/ (Dashboard Renderer, Assets & Modular Components)"]
        SVC["service/ (LabNKBandiService Facade)"]
    end

    CM --> ST
    ST --> API
    ST --> SVC
    SVC --> CAT
    SVC --> SEA
    SVC --> CON
    ING --> CAT
    RM -.->|Auto-Iniezione Graduata| SVC
```

---

## 🧩 2. Bounded Contexts & Principi di Dominio (LabNK v1.8.0)

### 1. Dual-Channel Search Engine (Accessibilità Universale vs Precisione Specialistica)
L'applicazione risolve la dicotomia tra utente inesperto e consulente aziendale tramite due motori cooperanti:
- **Canale Semplificato (NLP Semantica Discorsiva):** Riceve prompt in linguaggio naturale informale (es. *"startup a Napoli per software AI"*), esegue l'estrazione automatica delle entità (regione, importo, settore) e mappa i codici ATECO tramite `src_app/search/linguistics.py` e `src_app/search/ateco_tree.py`.
- **Canale Professionale per Esperti (Parametrico Rigido):** Riceve payload strutturati via `src_app/search/parametric_filter.py` con filtri booleani rigidi su ATECO, Regioni, Tipologie di Beneficiario, Range Finanziario e Tipo di Agevolazione, supportando alias flessibili italiani (`regioni`, `settori`, `agevolazione`).
- **Conformità Duale:** Validato al 100% su 40 scenari reali (80 query) con **Dual Agreement Rate del 100.0%** e latenze medie inferiori a 7 ms.

### 2. Federated B2B Ingestion & Dynamic Scaling
- **Registro Fonti Ufficiali (`sources_registry.json`):** Monitoraggio continuo delle fonti nazionali (MIMIT, Invitalia, GSE, ENEA), regionali (FESR/FSE, Finanziarie regionali in-house), camerali (Unioncamere OpenData) e comunitarie (TED v3, SEDIA EU).
- **Catalogo Doppio Buffer:** 40 bandi seed CGM certificati su disco in `src_app/data/seed_grants.json` + snapshot live scalabile a oltre 835 bandi in `data/snapshots/catalog_snapshot.json`.
- **Double-Buffered Atomic Swap:** L'ingestion asincrona aggiorna il catalogo in memoria tramite lock thread-safe senza impattare la latenza delle query utente.

### 3. Modularità DDD & Clean Architecture
- **Disaccoppiamento Assoluto:** Totale eliminazione dei monoliti legacy (`app.py` e `server.py` ridotti a facciate minimali di orchestratore e runner).
- **Assenza di Import Circolari:** Inizializzazione sicura a freddo garantita con import pigri per i moduli pesanti di document processing e contratti di interfaccia protetti da `if TYPE_CHECKING:`.

---

## 🛡️ 3. Standard di Qualità & Ratchet di Non-Regressione

In conformità a `[RULE-01.10]` e a `nk_tracking/quality_baseline.json`:
- **Suite Permanente Estesa:** **127 test unitari su 18 file** (`pytest tests/`) con vincolo assoluto del 100.0% PASS.
- **Oracolo Deterministico L3:** **95 check di Ground Truth** verificati con tolleranza d'errore zero (`scripts/oracle_evaluator_l3.py`).
- **Benchmark Duale 40 Scenari:** **80 query reali (40 NLP + 40 Parametriche)** con zero deficit (`scripts/run_stress_test_40_dual.py`).
- **AST Guard Static Analysis:** Purezza sintattica PEP 634/695 su tutti i **66 moduli** di `src_app/` (`scripts/ast_guard_validator.py`).
- **Preflight Health Check:** Garanzia permanente di stato `HEALTHY_GREEN` prima di ogni transizione.

# 🏛️ NK Genome: Concept Map & Briefing Master (Release v1.3.0-Universal-Official)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.3.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260902-GAP2-CONTINUOUS-RELEVANCE-E2E-v1.3.0`  
> **Data Consolidamento:** 2026-09-02  
> **Versione Ufficiale:** v1.3.0-Universal-Official (LabNK Bandi Intelligence & Decision Engine)  
> **Dominio:** Modulo Monitoraggio, Ricerca Semantica & Intelligence Bandi Nazionali, Regionali ed Europei

---

## 🎯 1. Visione Concettuale & Architettura Fondamentale (v1.3.0)

**LabNK Bandi Intelligence** è una piattaforma di intelligence decisionale progettata per imprese, startup e consulenti per automatizzare l'identificazione, l'analisi di ammissibilità e il calcolo della compatibilità dei bandi pubblici di finanziamento (nazionali, regionali ed europei), integrando il web harvesting continuo su 31 fonti istituzionali e il doppio motore di ricerca (NLP Intelligente e Parametrico Multidimensionale).

### 🏛️ I 4 Pilastri Architetturali

```mermaid
graph TD
    subgraph INGESTION & HARVESTING
        A["31 Portali Ufficiali (Invitalia, MIMIT, 20 Regioni, UE)"] -->|Driver REST / RSS / Scraper| B["Ingestion Pipeline (src_app/ingestion)"]
        B -->|Canonical Grant Model (CGM)| C["SSOT Sources Registry & Grant Store (364 Bandi)"]
        B -->|Double-Buffered Swap| C
    end

    subgraph INTELLIGENCE & MATCHING
        D["Query Utente NLP / Ricerca Parametrica"] -->|Smart Intent Extractor & Stemming| E["NLP: ATECO, NUTS & Toponimi Provinciali"]
        C --> F["Hybrid Semantic & Lexical Boost Engine"]
        E --> F
        F -->|Verifica De Minimis & Requisiti Dimensionali| G["Risultati Calibrati con 100% Top-1 Precision"]
    end

    subgraph PRESENTATION & GOVERNANCE
        G --> H["FastAPI Sovereign Gateway (src_app/server.py)"]
        H --> I["Dashboard Reattiva Real-time (src_app/ui/dashboard.py)"]
        H --> J["REST API Endpoints per Consulenti (NLP & Parametric)"]
    end
```

---

## 🧩 2. I Moduli Fondamentali di Produzione

1. **Canonical Grant Model (CGM - `src_app/models/cgm.py`):**  
   Modello standard Pydantic v2 a tipizzazione rigida (`extra="forbid"`) con payload crittografici SHA-256 e tracciamento delle fonti istituzionali (Tier 1/2/3).
2. **Registro SSOT Fonti Ufficiali (`src_app/ingestion/sources_registry.json`):**  
   Anagrafica centralizzata e tipizzata di **31 portali istituzionali sovrani** (9 Nazionali, 20 Regionali, 2 Europei).
3. **Smart Intent Extractor & ATECO Tree (`src_app/search/`):**  
   Parser semantico con 20 capoluoghi regionali e 14 toponimi provinciali/aree territoriali, oltre 65 locuzioni composte, estrazione automatica di NUTS-2/3, forme societarie, budget e categorie di spesa.
4. **Hybrid Semantic & Lexical Boost Engine (`src_app/service/bandi_service.py`):**  
   Algoritmo di ranking con scoring lessicale pesato, gestione morfologica delle desinenze singolari/plurali, cutoff dinamico sui risultati spuri e Territorial Boost (+30 pts), Sector Boost (+25 pts) e EU Boost (+30 pts).
5. **Deterministic Match Scoring Engine (`src_app/matching/scoring_engine.py`):**  
   Algoritmo deterministico a 4 fattori pesati con gestione De Minimis (€300k su 3 anni), compatibilità territoriale esplorativa wildcard (`is_profile_all`) e premialità per Startup Innovative (+5%), Giovani (+5%) e Donne (+5%).
6. **Ricerca Parametrica per Consulenti (`src_app/search/parametric_filter.py`):**  
   Filtro multidimensionale per codici ATECO gerarchici, regioni, tipologie di agevolazione normalizzate e percentuale di copertura minima.
7. **FastAPI Sovereign Gateway & Reattiva UI (`src_app/server.py` & `src_app/ui/dashboard.py`):**  
   Server asincrono con parametro `top_k: 20`, HTTP 202 Accepted per l'harvesting, Deep Links istituzionali verificati (`🏛️ Apri Bando Ufficiale ↗`) e latenza reale di calcolo su dashboard.

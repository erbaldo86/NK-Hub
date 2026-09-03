# 📜 NEXUS KEYSTONE OFFICIAL CHANGELOG & PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v1.3.0-Universal-Official`  
> **Milestone Anchor:** `NK-MS-20260902-GAP2-CONTINUOUS-RELEVANCE-E2E-v1.3.0`  
> **Data Consolidamento:** 2026-09-02  
> **Stato Release:** `🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.3.0 🟢]`

---

## 🚀 Release v1.3.0-Universal-Official — LabNK Bandi Intelligence & Decision Engine
La Release **v1.3.0-Universal-Official** rappresenta il traguardo di produzione definitivo per **LabNK Bandi Intelligence**, unificando in una piattaforma snella, robusta e ultra-veloce il monitoraggio continuo dal web su 31 fonti istituzionali, il motore di matching semantico NLP con flessione morfologica italiana, il filtraggio parametrico multidimensionale per consulenti e la certificazione E2E su benchmark reali.

### 🌐 1. Live Harvesting & Ingestion Engine (31 Fonti SSOT & Snapshot Reale)
* **31 Portali Istituzionali Sovrani Censiti (`src_app/ingestion/sources_registry.json`):**  
  Monitoraggio in tempo reale di Invitalia, MIMIT, INAIL, SIMEST, Incentivi.gov.it, OpenCoesione, Unioncamere/PID, CDP, Gazzetta Ufficiale, 20 Regioni Italiane, EU SEDIA ed EIC Accelerator.
* **Volume Live & Snapshot Persistente (`src_app/ingestion/orchestrator.py`):**  
  Scansione parallela asincrona (329 bandi estratti dal web, catalogo consolidato a **364 bandi totali**). Snapshot persistito su disco (`data/snapshots/catalog_snapshot.json`) per garantire boot istantaneo **Offline-First** (<50ms).
* **Double-Buffered Atomic Swap & Concorrenza Sicura:**  
  Protezione thread-safe con `threading.Lock` e swap atomico Copy-on-Write (`swap_grants_atomic`). Concorrenza limitata a 2 richieste per host con Circuit Breaker a 3 stati e timeout a 8s.
* **100% Zero-Mock & DROP_RECORD:**  
  Eliminazione radicale di qualsiasi dato o titolo fittizio. Validazione rigida Pydantic v2 (`extra="forbid"`) e scarto automatico dei record non parsabili (`DROP_RECORD`).

### 🧠 2. Motore Semantico NLP & Gating Territoriale Intelligente
* **Risoluzione Esplorativa Territoriale (`src_app/matching/scoring_engine.py`):**  
  Risolta l'inversione territoriale: le ricerche senza indicazione regionale (`operational_region = "Tutte"`) ammettono bandi regionali a livello esplorativo (`is_profile_all`), premiando al contempo con 25 pt la corrispondenza esatta quando l'utente specifica un territorio mirato.
* **Strict Relevance Filter & Cutoff Dinamico (`src_app/service/bandi_service.py`):**  
  Eliminato il tail noise e il sovraffollamento dei risultati: i bandi con 0 hit lessicali o privi di pertinenza sul core business vengono scartati preventivamente, impedendo la visualizzazione di bandi generici irrilevanti.
* **Stemming Morfologico Italiano & Stopwords Aziendali:**  
  Helper `match_token` con gestione automatica di singolari/plurali e desinenze (*fotovoltaico* $\leftrightarrow$ *fotovoltaici*, *mobilità* $\leftrightarrow$ *mobilita*). Esclusione dalle stopword di termini generici d'impresa e agevolazione (*fondo*, *perduto*, *bando*, *avviso*, *imprese*, *pmi*).
* **Estensione Toponimi Regionali & Provinciali (`src_app/search/nlp_intent_extractor.py`):**  
  Mappati tutti i 20 capoluoghi regionali e 14 toponimi provinciali/aree territoriali (*Cagliari, Genova, Ancona, Perugia, Faenza, Verona, Taranto, Foggia, Prato, Aosta, Udine, Trieste, Mezzogiorno, Sud*).

### 🔍 3. Ricerca Parametrica per Consulenti & Normalizzazione Agevolazioni
* **Multidimensional Filtering (`src_app/search/parametric_filter.py`):**  
  Filtri combinatori per Codici ATECO (con fallback gerarchico a 2 cifre), Regioni, Tipologie Beneficiari, Budget, % Copertura Minima e Testo Libero.
* **Normalizzazione Flessibile Agevolazioni:**  
  Risoluzione sinonimica per *Voucher*, *Fondo perduto*, *Finanziamento a tasso agevolato/zero*, *Credito d'imposta* e *Grant + Blended Equity*.

### ⚡ 4. FastAPI Sovereign Gateway & Dashboard Reattiva
* **FastAPI Server (`src_app/server.py`):**  
  Supporto parametro `top_k: int = 20` su `/api/search/nlp`, endpoint non-bloccante `HTTP 202 Accepted` su `/api/sync/harvest` con telemetria in tempo reale su `/api/sync/status`, LRU Bounded Cache (max 50 report) per i documenti.
* **Dashboard Reattiva (`src_app/ui/dashboard.py`):**  
  Interfaccia moderna HTML5/CSS3/ES6 con latenza di calcolo live in millisecondi, Deep Links istituzionali verificati (`🏛️ Apri Bando Ufficiale ↗`) e sanitizzazione XSS `escapeHTML()`.

### 🛡️ 5. Certificazioni di Qualità, Test Suite & Benchmark E2E
* **Benchmark E2E 60 Query (`scripts/verify_benchmark_60.py`):**  
  **60/60 Superate (100.0%)**: 30/30 query NLP posizionano al 1° posto assoluto (Top-1) il bando corretto; 30/30 query parametriche rispettano al 100% tutti i filtri.
* **Audit Link Istituzionali:**  
  **94.6% di raggiungibilità live reale** su 334 URL testati; 100% dei link canonici privi di errori o troncature.
* **Reliability Benchmark Suite (`scripts/test_reliability_benchmark.py`):**  
  **16/16 Scenari Industriali Superati (100.0% Top-1 Accuracy)** con latenza media di **4.65 ms**.
* **Oracolo Deterministico L3 (`scripts/oracle_evaluator_l3.py`):**  
  **95/95 Controlli Formali PASS (100%)** su ATECO tree, codici NUTS, calcolo De Minimis UE 2023/2831 (€300k) e integrità DOM.
* **Permanent Test Suite (`tests/` — 14 Moduli):**  
  **101/101 Test Unitari e di Integrazione Superati (100% Pass Rate)** su processi e filesystem reali.

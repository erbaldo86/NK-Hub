# 🏛️ NK Genome: Implementation Plan Master (Release v1.7.0-TotalCoverage)
### *Pipeline di Ingestion Adattiva Continua, Espansione a 75+ Fonti SSOT & Auto-Harvesting Notturno*

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.7.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260910-TOTAL-COVERAGE-EXPANSION-V170`  
> **Versione Target:** `v1.7.0-TotalCoverage`  
> **Dominio:** LabNK Bandi Intelligence & Decision Engine

---

## 🎯 1. Panoramica del Progetto & Requisiti Refined

Il progetto realizza l'espansione definitiva della pipeline di ingestion per scalare dall'attuale campionamento di 835 bandi alla **copertura totale del 100% dei bandi e incentivi di agevolazione alle imprese attivi in Italia e nell'Unione Europea** (stima di mercato: **2.500 - 4.500 bandi aperti contemporaneamente**), integrando:
1. **Paginazione Adattiva Continua:** Eliminazione del cap statico `max_pages=3` e scansione continua guidata dalla data di scadenza (`stato == APERTO`) con loop detection.
2. **Espansione Registro Fonti SSOT (da 38 a 75+ Portali):** Inclusione delle Finanziarie Regionali in-house (Finlombarda, Lazio Innova, Puglia Sviluppo, Sviluppo Campania, Finpiemonte, Friulia, Veneto Sviluppo, ART-ER, Sardegna Ricerche), enti energetici nazionali (GSE, ENEA) e la rete OpenData Unioncamere (60 CCIAA).
3. **Full Fetching Comunitario SEDIA EU & TED v3:** Paginazione `pageSize=500` per estrarre tutti i 600-800 topics aperti di Horizon Europe e LIFE, e filtraggio mirato CPV per R&S e tecnologie su TED v3.
4. **Auto-Harvesting Notturno & Double-Buffered Swap:** Scheduler asincrono notturno (ore 02:00 UTC) che aggiorna il catalogo in background senza intaccare la latenza sub-15ms delle API.
5. **Invisible Self-Healing Loop:** Fino a 3 tentativi di auto-riparazione con exponential backoff (1s -> 2s -> 4s) e rotazione User-Agent per gestire rate-limit o WAF governativi.
6. **Ratchet Compliance Rigoroso:** Salvaguardia assoluta dei **109 test permanenti su 15 file**, dell'**Oracolo Deterministico L3** (95/95), dello **Stress Test 80 Scenari** e del nuovo **Benchmark 30 Scenari Duali** al 100.0% PASS.

---

## 🛠️ 2. Fasi Operative di Implementazione (CRV 4.0)

### Fase 1: Build & Staging dei Connettori Adattivi (`.staging/src_app/connectors/`)
- Aggiornamento di `html_scraper.py`: implementazione del generatore `fetch_and_parse` a paginazione aperta con stop condition su date di chiusura pregresse o hash di pagina identici.
- Aggiornamento di `rest_api.py`: paginazione con `pageSize=500` su SEDIA F&T Portal e query su TED v3 ristrette ai codici CPV 73/72/71/38.

### Fase 2: Espansione Anagrafica SSOT (`.staging/src_app/ingestion/sources_registry.json`)
- Inserimento dei record strutturati per le agenzie regionali in-house (9 portali FESR/FSE aggiuntivi).
- Inserimento di GSE (Conto Termico, FER 1/2) ed ENEA.
- Inserimento dell'endpoint aggregatore camerale Unioncamere OpenData.

### Fase 3: Auto-Harvesting Notturno & Self-Healing (`.staging/src_app/ingestion/`)
- Implementazione di `src_app/ingestion/nightly_scheduler.py` agganciato al lifespan di FastAPI con battiti anti-freeze via `scripts/async_heartbeat_signaler.py`.
- Integrazione dell'Invisible Self-Healing Loop in `orchestrator.py` con logging delle anomalie e circuit breaker dinamico.
- Salvataggio incrementale double-buffered su `data/snapshots/catalog_snapshot.json` con deduplicazione hash SHA-256.

### Fase 4: Audit Deterministico & 2PC Atomic Commit
- Esecuzione statica AST Guard (`scripts/ast_guard_validator.py src_app`).
- Validazione Sandbox DAST e test di volume reale (target $\ge 2.500$ bandi validati CGM).
- Esecuzione della suite completa: 109 test permanenti + 95 oracoli + 80 scenari stress test + 30 scenari duali.
- Promozione atomica tramite `scripts/win32_2pc_engine.py --promote-staging`.
- Sincronizzazione della memoria a 3 livelli e aggiornamento changelog SSOT in `PATCH_NOTES.md`.

---

## 🧪 3. Piano di Verifica & Criteri di Successo

| Metrica di Verifica | Target Richiesto | Strumento di Controllo |
| :--- | :--- | :--- |
| **Volume Catalogo Ingestion** | $\ge 2.500$ Bandi CGM Aperti | Test reale di harvesting asincrono |
| **Purity Sintattica AST** | 100% PASS (0 violazioni) | `scripts/ast_guard_validator.py` |
| **Suite Permanente (15 File)** | 109 / 109 PASS (100%) | `python -m pytest tests/ -v` |
| **Oracolo Deterministico L3** | 95 / 95 Check Conformi (100%) | `scripts/oracle_evaluator_l3.py` |
| **Stress Test 80 Scenari** | 80 / 80 Scenari PASS (0 Deficit) | `scripts/run_stress_test_80.py --batch all` |
| **Benchmark 30 Scenari Duali**| 60 / 60 Test PASS (0 Deficit) | `scripts/run_stress_test_30_dual.py` |
| **Latenza Media Query** | $< 15.0$ ms (NLP) / $< 10.0$ ms (Param) | Profiler di latenza benchmark |
| **Preflight Health Check** | `HEALTHY_GREEN` | `scripts/preflight_health_check.py` |
| **Commit Atomico 2PC** | Win32 Named Mutex + WAL SHA-256 | `scripts/win32_2pc_engine.py` |

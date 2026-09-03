# 🏛️ NK Genome: Structural Tree Master (Release v1.3.0-Universal-Official)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.3.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260902-GAP2-CONTINUOUS-RELEVANCE-E2E-v1.3.0`  
> **Data Consolidamento:** 2026-09-02  
> **Versione Ufficiale:** v1.3.0-Universal-Official

---

## 🌳 Mappatura della Topologia del Repository

```
G:/Il mio Drive/Antigravity/
├── .agents/
│   ├── AGENTS.md                                # Regolamento di Sistema v1.1.0-Universal
│   ├── rules/
│   │   └── anti_crash_rules.md                  # Regole di protezione Windows & I/O
│   └── skills/                                  # 16 Vocazioni Canoniche NK
├── data/
│   ├── snapshots/
│   │   └── catalog_snapshot.json                # Snapshot Persistente Offline-First (364 Bandi)
│   └── test_queries_ground_truth.txt            # Ground Truth Benchmark 60 Query SSOT
├── nk_genome/                                   # Single Source of Truth Concettuale
│   ├── concept_map.md                           # Visione Architetturale & Brief Master v1.3.0
│   ├── structural_tree.md                       # Topologia e Albero del Repository v1.3.0
│   ├── implementation_plan.md                   # Piano Operativo & Roadmap Consolidata v1.3.0
│   └── PATCH_NOTES.md                           # Changelog SSOT Ufficiale v1.3.0
├── nk_tracking/                                 # Tracciamento e Baseline
│   ├── anchor/
│   │   └── session_anchor.jsonl                 # SSOT Activity Anchor
│   ├── quality_baseline.json                    # Ratchet Baseline di Qualità
│   └── reports_and_briefs/                      # Audit Reports & Metriche Oracolo L3
├── scripts/                                     # Motori Core & Infrastruttura di Sistema
│   ├── __init__.py
│   ├── ast_guard_validator.py                   # Static AST Guard (PEP 634/695)
│   ├── ast_repo_mapper.py                       # AST Topology & PageRank
│   ├── benchmark_performance.py                 # Profilatore Prestazioni & Latenza End-to-End
│   ├── dast_sandbox_runner.py                   # Real DAST Sandbox Runner & Line Tracer
│   ├── invisible_healing_loop.py                # Autonomous Triage Fast-Loop (Max 3 cycles)
│   ├── memory_3tier_engine.py                   # 3-Tier Memory Engine (Tier 1 <=350 tok, RRF k=60)
│   ├── oracle_evaluator_l3.py                   # Oracolo Deterministico L3 (95 Checks)
│   ├── preflight_health_check.py                # Boot Sanitizer & WAL TTL 60s Purge
│   ├── quality_baseline_manager.py              # Baseline Compliance & Ratchet Check
│   ├── safe_cleanup_dev_servers.py              # Anti-Lock & Server Process Cleanup
│   ├── sbfl_engine.py                           # Spectrum-Based Fault Localization
│   ├── test_reliability_benchmark.py           # Suite Affidabilità (16 Scenari Industriali)
│   ├── verify_benchmark_60.py                   # Benchmark E2E Continuo (60 Query NLP/Param)
│   ├── verify_live_harvesting.py                # Verifica Live Web Harvesting (31 Fonti SSOT)
│   ├── win32_2pc_engine.py                      # Win32 Named Mutex & 2PC Atomic Engine
│   └── schemas/                                 # Contratti Pydantic v2 Strict Mode
├── src_app/                                     # MODULO PRODUTTIVO: LABNK BANDI INTELLIGENCE
│   ├── app.py                                   # Bootstrap Service, CGM Catalog (364 Bandi) & Deep Links
│   ├── server.py                                # FastAPI Sovereign Gateway & REST API Endpoints
│   ├── connectors/                              # Driver di Connessione Multi-Fonte
│   │   ├── base.py                              # BaseConnector, Rate Limiter & Anti-Ban
│   │   ├── html_scraper.py                      # HTML Scraper con ZERO-MOCK DROP_RECORD
│   │   ├── p7m_unpacker.py                      # Buste Digitali P7M/CAdES & ASN.1 Unpacker
│   │   ├── rest_api.py                          # Client REST API (SEDIA EU, TED v3, SODA OpenData)
│   │   └── rss_feed.py                          # RSS/Atom Feeds con ETag & GUID Dedup
│   ├── document_processing/                     # Pipeline Elaborazione Allegati & Bandi
│   │   ├── document_pipeline.py                 # Coordinatore Pipeline Estrazione
│   │   ├── p7m_unpacker.py                      # Unpacker P7M per Buste Amministrative
│   │   ├── pdf_text_extractor.py                # Estrazione Testo PDF & OCR Fallback
│   │   ├── requirements_segmenter.py            # Segmentazione Regole e Vincoli di Spesa
│   │   └── zip_unpacker.py                      # Unpacker Sicuro ZIP con Anti-ZipBomb
│   ├── ingestion/                               # Pipeline di Harvesting & Registri Fonti
│   │   ├── orchestrator.py                      # Orchestratore Double-Buffered Live Harvesting
│   │   └── sources_registry.json                # SSOT 31 Portali Ufficiali (Nazionali, 20 Regioni, UE)
│   ├── matching/                                # Motore di Compatibilità & Scoring
│   │   ├── profile_model.py                     # Modelli Pydantic Profilo Impresa & Score Breakdown
│   │   └── scoring_engine.py                    # MatchScoringEngine (Formula 4 Criteri + De Minimis)
│   ├── models/                                  # Modelli Dati Canonici
│   │   └── cgm.py                               # CanonicalGrantModel (Pydantic v2 extra="forbid")
│   ├── search/                                  # Motori di Ricerca NLP & Parametrici
│   │   ├── ateco_tree.py                        # Albero Gerarchico ATECO 2007/2026 a 6 Cifre
│   │   ├── nlp_intent_extractor.py              # SmartIntentExtractor (34 Toponimi NUTS-2/3)
│   │   └── parametric_filter.py                 # ParametricFilter (Filtri Combinatori & Stemming)
│   ├── service/                                 # Business Logic & Service Provider
│   │   └── bandi_service.py                     # LabNKBandiService (Unified Query Handler & Cache)
│   └── ui/                                      # Frontend Reattivo
│       └── dashboard.py                         # DashboardRenderer (HTML5/CSS3/ES6 Modern UI)
├── tests/                                       # Suite Permanente di Test di Sistema (14 Moduli, 101 Test)
├── requirements.txt                             # Dipendenze Python Bloccate
├── README.md                                    # Presentazione Ufficiale Release v1.3.0
└── PATCH_NOTES.md                               # Mirroring Atomico Changelog v1.3.0
```


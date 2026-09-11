# 🏛️ NK Genome: Structural Tree Master (v1.8.0-ModularStable)
### *Albero Strutturale, Moduli DDD a Blocchi, Contratti & Topologia Ecosistema*

> **Badge di Certificazione:** 🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.8.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260911-MODULAR-STABLE-BASELINE-v1.8.0`  
> **Versione Target:** `v1.8.0-ModularStable`  
> **Dominio:** Architettura Modulare a Blocchi, 12 Package DDD, 127 Test Permanenti & Clean Architecture

---

## 🌳 1. Mappatura della Topologia del Repository

```text
G:/Il mio Drive/Antigravity/
├── .agents/
│   ├── AGENTS.md                                # Regolamento di Sistema v1.7.0-RepoMap Refined
│   ├── rules/
│   │   └── anti_crash_rules.md                  # Regole di protezione Windows, Win32 & I/O
│   └── skills/                                  # 16 Skill Vocazionali Canoniche
│       ├── NK-Master-Hub/                       # Sovrano Infrastrutturale L3 (2PC Mutex & Routing)
│       ├── NK-Session-Controller/               # Sovrano Critico (Repo-Map Graduated Injector)
│       ├── NK-Python-Async-Builder/             # Builder Core (Staging Builder)
│       ├── NK-Delta-Architect/                  # Patch Architect (Two-Stage Grounding)
│       ├── NK-Bug-Diagnostic-Engine/            # RCA Engine (SBFL Ochiai + Call Graph)
│       ├── NK-Security-Auditor/                 # Threat Audit L1/L2/L3
│       ├── NK-Oracle-Evaluator/                 # Oracolo Deterministico Cold Audit
│       ├── NK-App-UX-Architect/                 # UI/UX Architect (Frontend Skeleton)
│       └── ... (altre 8 skill vocazionali)
├── nk_genome/                                   # Single Source of Truth Concettuale (Tetralogia Sovrana)
│   ├── concept_map.md                           # Master Brief & Concept Map v1.8.0-ModularStable
│   ├── structural_tree.md                       # Topologia 12 Moduli DDD & Contratti di Sistema
│   ├── implementation_plan.md                   # Roadmap Operativa & Certificazione Milestone
│   ├── repo_map.md                              # Snapshot Permanente AST Repo-Map ad Altissima Densità
│   └── PATCH_NOTES.md                           # Changelog SSOT Ufficiale
├── nk_tracking/                                 # Tracciamento e Baseline di Qualità
│   ├── anchor/
│   │   └── session_anchor.jsonl                 # SSOT Activity Anchor Transazionale
│   ├── quality_baseline.json                    # Ratchet Baseline di Qualità (127 Test / 100.0% PASS)
│   ├── manifests/                               # Manifesti Formali di Handoff
│   │   └── dual_handoff_manifest_20260911_v180.json # Manifesto Ufficiale Release v1.8.0
│   └── reports_and_briefs/                      # Audit Reports, Benchmarks & Telemetria
├── src_app/                                     # Core Application (12 Moduli De-monolitizzati a Blocchi)
│   ├── __init__.py
│   ├── app.py                                   # Facciata minimale CLI runner e demo offline
│   ├── server.py                                # Facciata minimale ASGI entrypoint (uvicorn)
│   ├── api/                                     # API Gateway & Routing FastAPI
│   │   ├── app_factory.py                       # Factory FastAPI, CORS, middleware, lifespan
│   │   ├── deps.py                              # Dependency Injection e singleton service
│   │   ├── schemas.py                           # Contratti Pydantic per richieste/risposte API
│   │   └── routers/                             # Router modulari disaccoppiati
│   │       ├── documents_router.py              # Upload e processing allegati
│   │       ├── grants_router.py                 # CRUD e consultazione bandi
│   │       ├── health_router.py                 # Health check e status engine
│   │       ├── search_router.py                 # Ricerca NLP e ricerca parametrica
│   │       ├── sync_router.py                   # Sincronizzazione ed harvesting asincrono
│   │       └── ui_router.py                     # Endpoint rendering UI dashboard
│   ├── catalog/                                 # Gestione Catalogo & Storage
│   │   ├── repository.py                        # In-memory GrantRepository thread-safe
│   │   └── seed_loader.py                       # Loader atomico seed e catalog snapshot
│   ├── connectors/                              # Connettori I/O Fonti Esterne Federate
│   │   ├── base.py                              # Protocollo astratto connettore
│   │   ├── html_scraper.py                      # Scraper HTML resiliente con paginazione
│   │   ├── incentivi_gov.py                     # Connettore API MIMIT / Incentivi.gov.it
│   │   ├── unioncamere_federator.py             # Federatore CCIAA e bandi camerali
│   │   ├── rest_api.py                          # Client REST per TED v3 e SEDIA EU
│   │   ├── rss_feed.py                          # Parser feed RSS/Atom regionali
│   │   └── p7m_unpacker.py                      # Estrazione buste crittografiche CAD P7M
│   ├── core/                                    # Bootstrap & Configuration
│   │   ├── config.py                            # Configurazione applicativa Pydantic Settings
│   │   ├── bootstrap.py                         # Inizializzatore live e demo service
│   │   └── catalog_loader.py                    # Risoluzione percorsi dati e fallback
│   ├── data/                                    # Storage Locale Dati Primari
│   │   └── seed_grants.json                     # 40 Bandi Seed CGM Certificati
│   ├── document_processing/                     # Pipeline di Elaborazione Documentale
│   │   ├── document_pipeline.py                 # Coordinatore pipeline multi-formato
│   │   ├── pdf_extractor.py                     # Estrazione testo da PDF
│   │   ├── zip_unpacker.py                      # Unpacker archivi ZIP con Zip-Slip guard
│   │   ├── section_segmenter.py                 # Segmentazione sezioni bando
│   │   └── models.py                            # Modelli Pydantic per documenti
│   ├── ingestion/                               # Motore di Raccolta & Schedulazione Asincrona
│   │   ├── orchestrator.py                      # Orchestratore harvesting multi-fonte
│   │   ├── nightly_scheduler.py                 # Schedulatore notturno (02:00 UTC)
│   │   ├── sources_registry.json                # Registro SSOT delle fonti ufficiali
│   │   ├── throttling.py                        # Rate limiting adattivo
│   │   ├── watchdog.py                          # Watchdog per connettori in timeout
│   │   ├── base.py                              # Driver astratto ingestion
│   │   └── normalizers/                         # Normalizzazione record in CGM
│   ├── matching/                                # Motore di Valutazione e Scoring
│   │   ├── scoring_engine.py                    # Algoritmo pesato per matching bando-impresa
│   │   └── profile_model.py                     # Modello profilo aziendale
│   ├── models/                                  # Modelli di Dominio SSOT
│   │   └── cgm.py                               # Canonical Grant Model (CGM v2.0)
│   ├── search/                                  # Motori di Ricerca Semplificata ed Avanzata
│   │   ├── linguistics.py                       # Matching semantico, n-grammi e stopword
│   │   ├── ateco_tree.py                        # Gerarchia ATECO 2007/2025 e mapping morfologico
│   │   ├── nlp_intent_extractor.py              # Estrazione intenti da linguaggio naturale
│   │   └── parametric_filter.py                 # Filtro parametrico per esperti con alias elastici
│   ├── service/                                 # Application Layer Facade
│   │   └── bandi_service.py                     # LabNKBandiService unificato
│   └── ui/                                      # Interfaccia Utente Modulare
│       ├── dashboard.py                         # DashboardRenderer HTML5 reattivo
│       ├── assets/                              # Risorse statiche
│       │   ├── styles.css                       # Design system CSS3 responsive
│       │   └── dashboard_client.js              # Client interattivo vanilla JS anti-XSS
│       └── components/                          # Componenti HTML modulari
│           ├── header.py                        # Header e status bar
│           ├── kpi_grid.py                      # Griglia metriche e contatori
│           ├── search_sections.py               # Form ricerca NLP e Ricerca Parametrica
│           └── grants_view.py                   # Schede bandi e modal dettagli
├── scripts/                                     # Motori Core & Infrastruttura di Sistema
│   ├── ast_guard_validator.py                   # Static AST Guard (PEP 634/695) su 66 moduli
│   ├── ast_repo_mapper.py                       # High-Density AST Repo-Map Engine (v1.7.2)
│   ├── async_heartbeat_signaler.py              # Anti-Freeze Pulse Sentinel (cadenza 15-20s)
│   ├── dast_sandbox_runner.py                   # Real DAST Sandbox Runner & Line Tracer
│   ├── env_capability_probe.py                  # Probe deterministico dell'ambiente di esecuzione
│   ├── invisible_healing_loop.py                # Autonomous Triage Fast-Loop (Max 3 cicli)
│   ├── memory_3tier_engine.py                   # 3-Tier Memory Engine (Tier 1 <=350 tok)
│   ├── oracle_evaluator_l3.py                   # Oracolo Deterministico L3 (95 check ground truth)
│   ├── platform_runner.py                       # Universal UTF-8 Stream Runner
│   ├── preflight_health_check.py                # Boot Sanitizer, Cache & WAL Purge
│   ├── quality_baseline_manager.py              # Baseline Compliance & Ratchet Check
│   ├── run_stress_test_40_dual.py               # Benchmark Deterministico 40 Scenari Duali
│   ├── run_stress_test_30_dual.py               # Benchmark Deterministico 30 Scenari Duali
│   ├── run_stress_test_80.py                    # Stress Test Storico 80 Scenari
│   ├── safe_cleanup_dev_servers.py              # Anti-Lock & Process Cleanup
│   ├── sbfl_engine.py                           # Spectrum-Based Fault Localization (Ochiai)
│   ├── vibe_sprint_router.py                    # Vibe Coding Triple-Speed Router (Mode C/B/A)
│   └── win32_2pc_engine.py                      # Win32 Named Mutex & 2PC Atomic Commit Engine
├── tests/                                       # Suite Permanente di Piattaforma (127 Test / 18 File)
│   ├── conftest.py
│   ├── test_ast_guard_validator.py              # 4 test conformità sintattica AST
│   ├── test_ast_repo_mapper.py                  # 8 test High-Density Repo-Map
│   ├── test_b2b_excellence_macro1.py            # 7 test connettori B2B federati
│   ├── test_bando_connectors.py                 # 8 test connettori I/O
│   ├── test_dast_sandbox.py                     # 5 test sandbox DAST isolata
│   ├── test_document_processing_step3.py        # 8 test pipeline P7M/PDF/Zip
│   ├── test_eu_integration.py                   # 8 test integrazione TED v3 e SEDIA EU
│   ├── test_invisible_healing_loop.py           # 5 test invisible self-healing loop
│   ├── test_labnk_service_step5.py              # 6 test service layer e facade
│   ├── test_memory_3tier.py                     # 7 test memoria a 3 livelli
│   ├── test_oracle_ground_truth_l3.py           # 6 test oracolo deterministico
│   ├── test_platform_upgrades.py                # 4 test env probe e platform runner
│   ├── test_sbfl_engine.py                      # 6 test localizzazione difetti Ochiai
│   ├── test_schemas_and_contracts.py            # 7 test schemi e contratti Pydantic v2
│   ├── test_search_and_matching_step4.py        # 12 test ricerca NLP ed ATECO matching
│   ├── test_server_api.py                       # 10 test endpoint REST FastAPI
│   └── test_win32_2pc.py                        # 16 test commit atomico e lock Win32
├── data/                                        # Dataset di Benchmark & Snapshots
│   ├── benchmark_40_dual_scenarios.json         # Anagrafica SSOT 40 Scenari Duali (80 Query)
│   ├── benchmark_30_dual_scenarios.json         # Anagrafica SSOT 30 Scenari Duali (60 Query)
│   ├── stress_test_queries_80.txt               # Query storiche di stress test (80 Scenari)
│   └── snapshots/catalog_snapshot.json          # Snapshot live con oltre 835 bandi
├── README.md                                    # Presentazione Master in Inglese
├── README.it.md                                 # Presentazione Master in Italiano
└── requirements.txt                             # Dipendenze con vincoli rigidi
```

---

## 📋 2. Contratti dei Componenti Chiave di `src_app/`

| Modulo / Classe | Metodi Principali | Input / Output | Invariante Architetturale |
| :--- | :--- | :--- | :--- |
| `src_app.core.bootstrap` | `bootstrap_live_service()`, `bootstrap_demo_service()` | None -> `LabNKBandiService` | Inizializzazione deterministica senza dipendenze circolari |
| `src_app.catalog.repository.GrantRepository` | `add()`, `get()`, `list_all()`, `find_by_ateco()` | `CanonicalGrantModel` -> `List[CanonicalGrantModel]` | Thread-safe in-memory O(1) per ID e indicizzazione ATECO |
| `src_app.search.linguistics` | `calculate_semantic_score()`, `extract_entities()` | `query: str`, `grant: CanonicalGrantModel` -> `float` | Score pesato su n-grammi, normalizzazione diacritica e stopword |
| `src_app.search.parametric_filter` | `filter_grants()` | `ParametricFilterRequest`, `List[CanonicalGrantModel]` -> `List[ScoredGrant]` | Matching booleano rigido con normalizzazione automatica alias italiani |
| `src_app.search.ateco_tree` | `resolve_ateco_code()`, `get_children()` | `keyword_or_code: str` -> `List[str]` | Risoluzione gerarchica ATECO 2007/2025 e forme flesse singolare/plurale |
| `src_app.api.app_factory` | `create_app()` | `service: Optional[LabNKBandiService]` -> `FastAPI` | Configurazione router modulari, middleware CORS e Correlation ID |
| `src_app.ui.dashboard.DashboardRenderer` | `render_html()`, `get_css()`, `get_js()` | `service: LabNKBandiService` -> `str` | Rendering componibile HTML5, sanitizzazione anti-XSS `escapeHTML` |
| `src_app.service.bandi_service.LabNKBandiService` | `search_nlp()`, `search_parametric()`, `harvest_live()` | Query / Parametri -> Risultati CGM e ScoredGrants | Facade unificata per API, UI e CLI senza accoppiamento diretto |

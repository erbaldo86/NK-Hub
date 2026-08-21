---
title: "Structural Tree & Architectural Index — Mappa Topologica Moduli ES6 & Backend FastAPI"
version: "0.8.0-GOLDEN-STATE"
date: "2026-08-20"
status: "GOLDEN_STATE_VERIFIED"
author: "Nexus Keystone Architect & Supervisor"
---

# 🌳 Structural Tree & Genome Index: Architettura Modulare Nodo 3

## 🗺️ 1. Mappa ad Albero del Workspace

```
nodo3-ce-sp/
├── nk_genome/                                # 🧬 Root Genome & Indice Architetturale
│   ├── concept_map.md                        # Mappa concettuale, Invarianti (INV-01..INV-08) & Traumi
│   ├── structural_tree.md                    # [QUESTO FILE] Indice vivo, Schemi Pydantic v2 & DAG
│   ├── implementation_plan.md                # Piano operativo & Axiomatic Oracle Test Suite
│   ├── builder_protocol.md                   # Protocollo di sicurezza e lock files
│   ├── release_v0.8.zip                      # 📦 Pacchetto Release Ufficiale v0.8.0 Golden State
│   └── PATCH_NOTES.md                        # Registro cronologico dei rilasci
│
├── nk_tracking/                              # 📜 Activity Anchor & Audit Log
│   ├── anchor/session_anchor.jsonl           # Log immutabile delle transazioni atomiche
│   ├── dual_handoff_manifest_20260820_v08.json # Manifest di salto duale per passaggio consegne
│   └── reports_and_briefs/                   # Report diagnostici e certificazioni TAS
│
├── old/                                      # 📦 Archivio Storico Versioni Precedenti
│   ├── archive_pre_v0.8_full.zip             # Pacchetto compresso di tutte le vecchie release
│   ├── legacy_releases/                      # Vecchi file .zip (v0.6, v0.9, v0.95, v1.0, v1.2)
│   └── legacy_tracking/                      # Vecchi log e manifest storici
│
├── test_suite/                               # ⚖️ Harness di Test Deterministico & Oracoli Assiomatici
│   ├── test_real_downloads_dataset_e2e.py    # E2E Test su 5 file reali ODS, CSV, XML (5/5 PASS)
│   ├── test_hard_file_limiter_e2e.py         # Test Hard Limiter Guard (Cumulativo & All-or-Nothing)
│   ├── test_delta_ledger_replay.py           # Test Delta Ledger, Eviction Chirurgica & Idempotenza
│   ├── run_full_modular_stress_suite.mjs     # Modular Stress Suite (1.000 iterazioni deterministiche)
│   └── node_vm_chaos_fuzzer.js               # In-Memory VM Fuzzer ad alta densità
│
├── src_app/                                  # 💻 Codice Applicativo
│   ├── app.js                                # Monolite di riferimento (Golden Baseline)
│   ├── index.html                            # Frontend Shell, Active Badges & Toolbar On-Demand
│   ├── styles.css                            # CSS Design System (Badge Grid, Limbo, Accordion, Gap Header)
│   │
│   ├── backend/                              # 🐍 Backend FastAPI & Parser NLP
│   │   ├── main_api_server.py                # Server FastAPI, Upload Lock, 50MB Limit & Multi-File Router
│   │   ├── civil_code_math_engine.py         # Motore matematico puro Art. 2424 & 2425 C.C. & Gap Corkscrew
│   │   ├── ingestion_parser_service.py       # Parser universale, Fingerprinting SHA-256 & Delta Merger
│   │   ├── pydantic_schemas.py               # Schemi Pydantic v2 Rigorosi & Delta Ledger Models
│   │   └── universal_subitems_warehouse.json # Catalogo Tassonomia & Sub-voci
│   │
│   └── modules/                              # 📦 MODULI ES6 (Architettura a 3 Livelli)
│       ├── state.js                          # [M1] Store Reattivo, Delta Ledger, Adaptive Timeline & batchUpdate
│       ├── constants.js                      # [M2] Dizionari Tassonomia, Hard Limiter Guards & Costanti
│       ├── financial_engine.js               # [M3] Motore Algebrico CE/SP, Subvoci & QuickFix Istantaneo
│       ├── table_ce.js                       # [M4] Render Tabella CE con Event Delegation su Timeline Reale
│       ├── table_sp.js                       # [M5] Render Tabella SP con Event Delegation & Badge Quadratura
│       ├── kpi_analytics.js                  # [M6] Top KPI Cards, SaaS Metrics & SVG Adaptive Trend
│       ├── modals.js                         # [M7] Modali Sub-items, Limbo Hub, Add Year Modal & Warning
│       ├── ingestion.js                      # [M8] Hard Dropzone Limiter, Multi-File Bridge & Delta Ledger Client
│       ├── export_engine.js                  # [M8.5] Export multi-formato XLSX/CSV/JSON/PDF
│       └── main.js                           # [M9] Orchestratore App, requestAnimationFrame Render Hub
```

---

## 🧭 2. Mappatura Funzionale e Contratti Modulari (9 Moduli ES6 + 4 Backend)

| Modulo | File Path | Responsabilità Principale | Nuove Funzioni / Export Chiave | Invarianti Gestiti |
| :--- | :--- | :--- | :--- | :--- |
| **M1: State Store** | `src_app/modules/state.js` | Single Source of Truth; gestione Delta Ledger; rilevamento anni con dati reali (`getActiveDataYears`); timeline adattiva; aggiunta/rimozione anni on-demand (`addTimelineYear`, `removeTimelineYear`). | `getState()`, `setState()`, `getActiveDataYears()`, `getTimelineYears()`, `addTimelineYear()`, `removeTimelineYear()`, `batchUpdate()` | **INV-03**, **INV-04**, **INV-06** |
| **M2: Constants** | `src_app/modules/constants.js` | Limiti di sistema, tassonomie contabili C.C., etichette e costanti. | `MAX_ACTIVE_FILES = 4`, `CE_KEYS`, `SP_KEYS`, `formatEuro`, `formatPercent` | **INV-06** |
| **M3: Financial Engine** | `src_app/modules/financial_engine.js` | Calcolo algebrico civilistico puro (Art. 2424 & 2425 C.C.), aggregazione sub-voci e quadratura SP automatica. | `recalculateFinancials()`, `aggregateSubitemsForYear()`, `balanceSPQuickFix()` | **INV-01**, **INV-02**, **INV-07** |
| **M4: Table CE** | `src_app/modules/table_ce.js` | Rendering HTML Conto Economico sulle sole colonne attive con Event Delegation su `#ceTableContainer`. | `renderCETable()`, `setupCETableEventDelegation()` | **DAST-REQ-02** |
| **M5: Table SP** | `src_app/modules/table_sp.js` | Rendering HTML Stato Patrimoniale sulle sole colonne attive con Event Delegation su `#spTableContainer`. | `renderSPTables()`, `setupSPTableEventDelegation()` | **INV-01**, **DAST-REQ-02** |
| **M6: KPI Analytics** | `src_app/modules/kpi_analytics.js` | Top KPI Cards, SaaS metrics e grafici SVG allineati agli anni reali. | `renderKpiCards()`, `renderCharts()` | Protezione da vettori vuoti |
| **M7: Modals & UI** | `src_app/modules/modals.js` | Modali Sub-items, Limbo Hub, Reset Confirm, Aggiungi Anno Toolbar. | `openSubitemModal()`, `showToast()` | UI Safety |
| **M8: Ingestion** | `src_app/modules/ingestion.js` | Hard File Limiter (Max 4 cumulativo), All-or-Nothing snapshot e Delta Ledger Client. | `handleFileSelect()`, `processUserUploadedFiles()`, `removeUploadedFile()` | **INV-05**, **INV-06** |
| **M9: Main Orchestrator** | `src_app/modules/main.js` | Bootstrap ES6, coordinamento requestAnimationFrame e binding retrocompatibile window. | `bootstrap()`, `promptAddTimelineYear()` | **DAST-REQ-03** |

---

## 🔄 3. DAG di Kahn (Grafo Aciclico Diretto)
Sequenza Topologica: `[M2 (constants), P_SCHEMAS, M1 (state), MATH_ENG, PARSER_SRV, M3 (financial_engine), API_SRV, M7 (modals), M4 (table_ce), M5 (table_sp), M6 (kpi_analytics), M8 (ingestion), M9 (main)]`  
Verdetto: 0 Cicli (Aciclicità 100%).

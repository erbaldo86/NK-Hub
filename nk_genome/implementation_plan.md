# 🏛️ NK Genome: Implementation Plan Master (Release v2.1.0-FastHealing)
### *Fast-Healing Engine, 61 Golden Tests Permanente & Scope Integrity Hardening*

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v2.1.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260915-FAST-HEALING-v2.1.0`  
> **Versione Target:** `v2.1.0-FastHealing`  
> **Dominio:** Nexus Keystone Hub — Meta-Framework Agentico, CRV 4.0, Win32 2PC, 3-Pillar Fast-Healing & 61 Golden Tests

---

## 🎯 1. Consolidamento Baseline Piattaforma Core (Stato: CERTIFIED 🟢)

A seguito di una valutazione forense test-per-test sui 72 test della piattaforma, la suite permanente di test di NK-Hub è stata razionalizzata e snellita a **61 Test Golden Super-Hardened**, eliminando i test mock in-memory, le duplicazioni cross-file e i colli di bottiglia I/O. È stato inoltre integrato il motore universale di auto-guarigione a 3 pilastri in conformità vincolante con `[RULE-PROJECT-ISOLATION]`.

### Matrice di Certificazione di Piattaforma:
| Dimensione di Collaudo | Obiettivo | Risultato Conseguito | Stato |
| :--- | :---: | :---: | :---: |
| **Suite Permanente (`pytest tests/`)** | $\ge 61$ Golden Tests di Piattaforma | **61 / 61 Test PASSED (100.0%)** | 🟢 **CERTIFIED** |
| **Tempo di Esecuzione Suite** | SLA $< 15.0$ s (-40% rispetto ai 24s) | **~12 - 14 s** | ⚡ **ECCELLENTE** |
| **AST Guard Static Analysis** | Scope & Decorator Hardened | **33 / 33 Moduli PASSED (0 Violazioni)** | 🟢 **CERTIFIED** |
| **Tier-3 Elastic Repo-Map** | Budget $\le 850$ tok | **$\le 850$ tok, 0 moduli omessi** | 🟢 **CERTIFIED** |
| **Win32 2PC Named Mutex** | Concurrency safety su Windows | **Verificato con SHA-256 e Shadow Swap** | 🟢 **CERTIFIED** |
| **Fast-Healing Pipeline Zero-Mock** | Rollback atomico & Fitness Gate | **Verificato con Pytest Bridge (<80 tok)** | 🟢 **CERTIFIED** |
| **Session Bootstrap Gate** | Fast-stat $< 120$ ms | **7.33 ms** | 🟢 **CERTIFIED** |
| **GitHub Actions CI (Python 3.12 LTS)** | Continuous Verification | **Workflow 100% Green / Success** | 🟢 **CERTIFIED** |

---

## 🛠️ 2. Roadmap di Evoluzione della Meta-Piattaforma (v2.1.0)

### Iterazione 1: 3-Pillar Fast-Healing Integration
- **Universal CLI Auto-Healer Pipeline (`scripts/auto_heal_pipeline.py`)**: 3 cicli di auto-riparazione protetti da Circuit Breaker.
- **Pytest Coverage & SBFL Ochiai Bridge (`scripts/sbfl_pytest_bridge.py`)**: Diagnosi automatica riga per riga $< 80$ token.
- **Staging Snapshot & Rollback Engine (`scripts/healing_snapshot_rollback.py`)**: Strict Monotonic Fitness Gate atomico.

### Iterazione 2: AST Guard Scope Integrity Bugfix
- Riparazione di `_process_func` e `visit_ClassDef` in `scripts/ast_guard_validator.py` per visitare esplicitamente `decorator_list` e default arguments nel frame genitore.

### Iterazione 3: Test Suite Rationalization (61 Golden Tests)
- Rimozione di 4 test obsoleti in `test_invisible_healing_loop.py`.
- Promozione di 6 test Zero-Mock in `test_auto_heal_pipeline.py`.
- Risoluzione dei colli di bottiglia I/O (-93% tempo in `test_memory_3tier.py`) e dei test duplicati.

---

## 🧪 3. Invarianti di Governance & Salvaguardia Ratchet

1. **Ratchet Rule (`[RULE-01.10]`):** Nessuna modifica successiva potrà ridurre il numero di test permanenti al di sotto di **61** o il pass rate al di sotto del **100.0%**.
2. **Project Isolation Mandate (`[RULE-PROJECT-ISOLATION]`):** È vietato creare codice applicativo di prodotto all'interno di NK-Hub. Ogni progetto esterno vive nella propria directory dedicata con il proprio file `PATCH_NOTES.md`.
3. **Zero-Mock Mandate (`[RULE-01.2]`):** Ogni nuovo motore o guardiano di piattaforma deve essere validato con test su filesystem e processi reali.
4. **High-Density Repo-Map (`[RULE-01.13]`):** A ogni commit atomico di release, `scripts/ast_repo_mapper.py` aggiorna automaticamente `nk_genome/repo_map.md`.

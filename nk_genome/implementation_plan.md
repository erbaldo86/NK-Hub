# 🏛️ NK Genome: Implementation Plan Master (Release v1.8.0-ModularStable)
### *Nuova Baseline Stabile Ufficiale, Architettura a Blocchi & Roadmap Evolutiva*

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v1.8.0 🟢]  
> **Milestone Anchor:** `NK-MS-20260911-MODULAR-STABLE-BASELINE-v1.8.0`  
> **Versione Target:** `v1.8.0-ModularStable`  
> **Dominio:** LabNK Bandi Intelligence & Decision Engine

---

## 🎯 1. Consolidamento Baseline Stabile Ufficiale (Stato: COMPLETATO 🟢)

La fase di de-monolitizzazione e stabilizzazione dell'ecosistema è formalmente completata e certificata. I 4 macro-monoliti originali sono stati disarticolati in 12 moduli verticali DDD autonomi in `src_app/`. I bug identificati durante l'audit a freddo (import circolare su avvio a freddo e alias bypass nella ricerca parametrica) sono stati bonificati tramite auto-healing deterministico.

### Matrice di Certificazione di Baseline:
| Dimensione di Collaudo | Obiettivo | Risultato Conseguito | Stato |
| :--- | :---: | :---: | :---: |
| **De-monolitizzazione `src_app/`** | 12 Moduli DDD modulari | 66 Moduli autonomi, zero import circolari | 🟢 **CERTIFIED** |
| **Suite Permanente (`pytest tests/`)** | $\ge 115$ Test Unitari | **127 / 127 Test PASSED (100.0%)** | 🟢 **CERTIFIED** |
| **Oracolo Deterministico L3** | 95 Controlli Ground Truth | **95 / 95 Check PASSED (100.0%)** | 🟢 **CERTIFIED** |
| **Stress Test 40 Scenari Duali** | 80 Query Simulate (NLP + Param) | **80 / 80 PASS (100.0%, 0 Deficit)** | 🟢 **CERTIFIED** |
| **Latenza Media Ricerca Semplificata** | SLA $< 25.0$ ms | **6.99 ms** | ⚡ **ECCELLENTE** |
| **Latenza Media Ricerca Esperti** | SLA $< 15.0$ ms | **4.10 ms** | ⚡ **ECCELLENTE** |
| **AST Guard Static Analysis** | Purity PEP 634/695 | **66 / 66 Moduli PASSED (0 Violazioni)** | 🟢 **CERTIFIED** |
| **Preflight Health Check** | Zero WAL orfani, cache pulita | **`HEALTHY_GREEN`** | 🟢 **CERTIFIED** |
| **High-Density AST Repo-Map** | Generazione automatica | **Snapshot `nk_genome/repo_map.md` attivo** | 🟢 **CERTIFIED** |

---

## 🛠️ 2. Roadmap di Evoluzione Incrementale (Post-Baseline v1.8.0)

A partire da questa nuova versione di base pulita e snella, gli sviluppi futuri seguiranno cicli incrementali disciplinati dal Protocollo CRV 4.0:

### Iterazione 1: Mass Ingestion Crawler & Clustering Continuo
- Espansione dei connettori a paginazione aperta sui portali regionali FESR/FSE (target: 1.500+ bandi live).
- Deduplicazione clusterizzata su base temporale e semantica con fingerprint SHA-256.
- Double-buffered atomic swap notturno ad impatto zero sulla memoria runtime.

### Iterazione 2: Profilazione Aziendale Multi-Tenant per Consulenti
- Gestione anagrafiche imprese con multipli codici ATECO secondari e indicatori finanziari (ULA, Fatturato, Attivo).
- Matching pesato multi-criterio automatico per portfolio clienti commercialisti.

### Iterazione 3: Document AI RAG per Allegati Tecnici P7M/PDF
- Indicizzazione semantica a chunk dei disciplinari di gara e moduli di domanda estratti da buste P7M e PDF vettoriali.
- Generazione automatica di schede di sintesi e checklist documentale per la presentazione della domanda.

---

## 🧪 3. Invarianti di Governance & Salvaguardia Ratchet

1. **Ratchet Rule (`[RULE-01.10]`):** Nessuna modifica successiva potrà ridurre il numero di test permanenti al di sotto di **127** o il pass rate al di sotto del **100.0%**.
2. **Zero-Mock Mandate (`[RULE-01.2]`):** Ogni nuovo connettore o algoritmo di ricerca dovrà essere validato con test su filesystem e processi reali.
3. **High-Density Repo-Map (`[RULE-01.13]`):** A ogni commit atomico di release, `scripts/ast_repo_mapper.py` aggiornerà automaticamente `nk_genome/repo_map.md`.

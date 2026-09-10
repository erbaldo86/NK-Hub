# 🏛️ NK Genome: Concept Map & Master Brief (v1.7.0-RepoMap Refined)
### *High-Density AST Repo-Map Engine & Cross-Skill Context Injection for Nexus Keystone*

> **Badge di Certificazione:** 🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]  
> **Milestone Anchor:** `NK-MS-20260910-AST-REPOMAP-V170`  
> **Versione Target:** `v1.7.0-RepoMap`  
> **Dominio:** Intelligence Sintattica Globale, Compressione AST a Due Livelli, Incremental Caching & Integrazione Graduata 16 Skill

---

## 🎯 1. Visione Concettuale & La Tetralogia Sovrana di NK Genome

L'integrazione del **High-Density AST Repo-Map Engine** eleva l'infrastruttura del Genoma da "Trittico" a **"Tetralogia Sovrana"**:
1. `concept_map.md`: Intento di dominio, Bounded Contexts, logica di business e requisiti utente.
2. `structural_tree.md`: Topologia strutturale dei moduli, ruoli dei file, contratti e dipendenze Kahn DAG.
3. `implementation_plan.md`: Roadmap operativa, verifica delle fasi e cancelli di approvazione.
4. `repo_map.md`: **Snapshot Permanente ad Altissima Densità** del grafo sintattico reale (classi, metodi, firme, tipi e PageRank).

In piena conformità alla direttiva dell'utente, questo sistema opera in **completa autonomia (`[RULE-01.13] INTRINSIC_REPO_MAP_MANDATE`)**:
- **Nessun promemoria umano:** Il sistema genera, aggiorna e consulta la Repo-Map in modo silente e deterministico.
- **Auto-Aggiornamento a Fine Rilascio:** In Macro-Fase 3, `NK-Scribe` genera e memorizza atomicamente `nk_genome/repo_map.md` (e il corrispettivo `repo_map.md` in qualsiasi applicazione esterna creata dall'Hub).
- **Auto-Consumo nelle Skill:** `NK-Session-Controller` inietta autonomamente la mappa graduata nel preambolo dei builder per azzerare le allucinazioni sulle firme.

### 🏛️ I 5 Pilastri Architetturali Raffinati

```mermaid
graph TD
    subgraph SORGENTI & INCREMENTAL CACHE
        FS["Filesystem (Python + Frontend JS/TS/CSS)"] -->|File Hash / mtime Check| IFC["Incremental Per-File Symbol Cache (%TEMP%)"]
        IFC -->|Delta Update < 15ms| SG["SymbolGraph (Nodes, Edges, Containment, Calls)"]
    end

    subgraph ENGINE AST REPO-MAP (scripts/ast_repo_mapper.py)
        SG --> PPR["Personalized PageRank (d=0.85, Multi-Focal Teleport)"]
        PPR --> TTC["Two-Tier Clustering & Multi-Focal Slicer"]
        TTC --> ARW["Atomic Temp-Rename Cache Manager (uuid.tmp -> os.replace)"]
    end

    subgraph GRADUATED SKILL INJECTION (Context-Aware)
        TTC -->|Mode C: Micro-Scoped <= 256 tok| MC["Mode C Builders & NK-App-UX-Architect"]
        TTC -->|Mode B: Cluster-Scoped <= 512 tok| MB["Mode B Backend Builders & NK-Bug-Diagnostic-Engine"]
        TTC -->|Mode A: Full Topology <= 1024/2048 tok| MA["NK-Session-Controller & NK-Master-Hub"]
        TTC -.->|EXCLUDED (Token Hygiene)| EX["NK-Scribe & NK-Episodic-Memory-Engine"]
    end
```

---

## 🧩 2. Le Risoluzioni Chirurgiche alle 7 Vulnerabilità Avversariali

### 1. Two-Tier Hierarchical Clustering (Anti-Diluizione su Grandi Codebase)
Per evitare che un tetto di 1024 token tagli il 95% del codice e nasconda i moduli foglia di business logic:
- **Cluster di 1° Grado (Focale e Adiacenti):** Mostra le firme complete dei metodi, parametri e annotazioni di tipo (`def calculate_grant_score(grant_id: str, ula: float) -> float: ...`).
- **Cluster di 2° Grado (Infrastruttura Lontana):** Viene compresso a livello di cartella/modulo con sommario simbolico:
  ```python
  # src_app/models/ (3 ORM Models: CGM, GrantDetail, SourceMetadata)
  # src_app/connectors/ (5 Connectors: REST, RSS, Scraper, P7M, Base)
  ```
  Questo azzera il rischio che l'LLM creda che un file non esista e ne duplichi le funzioni.

### 2. Multi-Focal AST Slicer Corretto (Risoluzione Bug Linea 851)
- Eliminato il collo di bottiglia `focal_node = focal_nodes[0]`: l'algoritmo itera su **tutti** i simboli focali indicati (`--focus-files "fileA.py,fileB.py"`).
- Compressione a livelli: se il budget stringe, vengono compressi prima i docstring e i corpi interni, ma le **firme e i parametri di tutti i simboli focali rimangono sempre intatti al 100%**, senza mai spezzare la sintassi a metà riga.

### 3. Concorrenza Sicura NVMe con Atomic Temp-Rename
- Per azzerare i conflitti `WinError 32` o `JSONDecodeError` tra subagenti concorrenti nella Macro-Fase 2:
  - Scrittura atomica via file effimero univoco: `%TEMP%\nk_diagnostics\repo_map_cache.<uuid>.tmp` seguita da `os.replace` atomico.
  - Lettura resiliente con backoff esponenziale (3 tentativi, 10-50ms) in caso di lock transitorio del filesystem.

### 4. Incremental Per-File Symbol Cache (Latenza $< 15$ms in Mode C)
- Memorizzazione dello stato di parsing a livello di singolo file (`{path: {"mtime": ..., "hash": ..., "nodes": [...]}}`).
- Quando uno sviluppatore o un builder modifica un file in Mode C, **solo quel singolo file viene ri-parsato**, aggiornando i collegamenti nel grafo dei simboli in meno di 15 millisecondi senza bloccare l'interfaccia.

### 5. Parser Resiliente Senza Allucinazioni da Stub `()`
- Se un file è a metà scrittura durante il Vibe Coding (es. `def create_user(username: str, email:` con parentesi aperta), il parser non genera uno stub fasullo a zero argomenti `def create_user(): pass`.
- Preserva i parametri parzialmente definiti, segnalando esplicitamente `# [signature incomplete during live edit]` per evitare che i subagenti generino chiamate a zero argomenti.

### 6. Graduazione Context-Aware per le 16 Skill NK
- **⚡ Mode C (Vibe-Sprint):** Payload compatto $\le 256$ token (solo target file + contratti DOM e import diretti).
- **🔧 Mode B (Fast-Track):** Payload cluster $\le 512$ token (target + chiamanti/chiamati di 1° grado).
- **🏛️ Mode A (Sovereign):** Mappa globale $\le 1024\text{--}2048$ token (riservata a Session Controller e Master Hub).
- **Blacklist Esplicita:** Disattivata l'iniezione per `NK-Scribe` (changelog), `NK-Episodic-Memory-Engine` (memoria 350 tok cap) e `NK-Agent-Instruction-Forge` per non sporcare il contesto.

### 7. Rispetto Rigoroso del Ratchet Permanente (109 Test / 15 File)
- La suite di validazione permanente dell'ecosistema è e rimane categoricamente di **109 test unitari su 15 file** al 100.0% PASS, in piena conformità a `[RULE-01.10]` e a `nk_tracking/quality_baseline.json`.

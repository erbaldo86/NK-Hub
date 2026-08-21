# 03 - Guida al Ciclo di Vita Post-Rilascio & Day-2 Operations (NK Release v1.0)

Questa guida illustra il funzionamento dell'infrastruttura **Post-Release & Day-2** dell'Ecosistema Nexus Keystone (NK Release v1.0). Il sistema integra **Memoria Episodica Semantica**, **Two-Stage Grounding**, **CRV 4.0 a 4 Macro-Fasi** e **Ratchet di Non-Regressione**, garantendo il tracciamento sicuro, l'audit costante e l'auto-riparazione deterministica delle anomalie in produzione.

---

## 1. Architettura Day-2 & Dual-Track Routing

L'ecosistema utilizza un approccio **Dual-Track** gestito dal `NK-Master-Hub` e `NK-Session-Controller`:
- **Fast-Track (Mode B - Fix Rapidi ≤100 LOC):** Per correzioni chirurgiche e anomalie puntuali con impatto zero sui boundaries, il ticket di bug viene indirizzato a `NK-Python-Async-Builder` o builder di competenza con validazione AST <200ms.
- **Deep-Track (Mode A - Refactoring & Feature >100 LOC):** Per sviluppi strutturali o modifiche che impattano l'architettura, la richiesta transita attraverso `NK-Delta-Architect`, che esegue il **Two-Stage Grounding** (Stage A su `implementation_plan.md` + Stage B su codice) e richiede l'approvazione di `NK-Plan-Aligner` su tutti e 3 i documenti del Trittico.

### Gate `FALSE_BUG_REJECTION`
Il sub-agente `NK-Bug-Diagnostic-Engine` analizza i report utente ed esegue un'interrogazione alla memoria episodica (`01_Bug_Diagnostics`). Se un bug segnalato si rivela essere una richiesta per una nuova feature mascherata, il gate `FALSE_BUG_REJECTION` la reindirizza automaticamente al Deep-Track (`NK-Delta-Architect`) o notifica l'utente della classificazione errata.

---

## 2. Lo State Router & Structural Tree SSOT (`NK-State-Router`)

### Mappatura e Single Source of Truth
`NK-State-Router` mantiene lo stato autoritativo dell'intero ecosistema centralizzato nel file:
- **`nk_genome/structural_tree.md`**: Topologia ad albero unica con tag `<llm_structural_anchor>` e checksum SHA-256 integrati.

### Drift Detection (Rilevamento Deriva)
`NK-State-Router` verifica ciclicamente o all'avvio la corrispondenza dei checksum SHA-256 dei file fisici contro `structural_tree.md`. Qualora file siano stati modificati bypassando l'Ecosistema NK, viene rilevata una deriva (Drift), innescando l'aggiornamento controllato del DAG di Kahn.

---

## 3. Memoria Episodica Semantica (`NK-Episodic-Memory-Engine`)

La memoria a lungo termine è strutturata in `System_Documentation/NK_Episodic_Memory/` su 4 domini JSONL:
1. `01_Bug_Diagnostics/`: Pattern di guasto, RCA storiche e fix verificati.
2. `02_Development_Patterns/`: Snippet architetturali, Pydantic v2 e contratti OpenAPI 3.0.
3. `03_Ideation_and_Decisions/`: Decisioni UX, compromessi architetturali e pivot.
4. `04_Governance_and_Rules/`: Evoluzione del regolamento e vincoli di audit.

---

## 4. Gestione dei Backup e Rollback (Circular Backup System v5.0)

Prima di applicare qualsiasi modifica architetturale o rimozione di nodi, il sistema esegue una snapshot circolare controllata da `NK-State-Router`:
- Stato precedente salvato in backup circolare con ownership esclusiva dei lock fisici.
- Questo meccanismo di fallback assicura che qualsiasi errore nel ricalcolo del DAG inneschi un rollback istantaneo dello stato senza perdita di dati.

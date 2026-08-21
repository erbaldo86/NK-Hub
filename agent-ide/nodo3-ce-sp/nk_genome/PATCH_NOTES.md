# 📜 PATCH NOTES — Nodo 3 (Chronos & Kairos - CE & SP Engine)

## [v0.8.0-GOLDEN-STATE] — 2026-08-20
### 🏛️ Nuova Baseline Ufficiale di Progetto (Punto di Partenza Immutabile)

#### 1. Adaptive Data-Driven Viewport & On-Demand Expansion:
- **Vista Pulita Senza Zeri Spuri**: Le tabelle del Conto Economico e dello Stato Patrimoniale mostrano di base **esclusivamente gli anni in cui sono presenti dati reali estratti dai file** (es. 2 colonne per bilanci 2024-2025).
- **Toolbar Anni Intelligente**: Rimossi i vecchi selettori statici (1, 2, 3, 5 Anni). Inseriti i badge degli anni attivi e il pulsante compatto **`➕ Aggiungi Anno`** (`promptAddTimelineYear`).
- **Aggiunta e Rimozione On-Demand**: L'utente può aggiungere un anno forecast o storico per simulazioni manuali e rimuoverlo con l'icona **`🗑️`** presente nell'intestazione di colonna.

#### 2. Hard File Limiter Guard (Max 4 File):
- **Protezione Anti-Saturazione**: Limite rigido sia lato frontend (Dropzone disabilitata a saturazione con toast esplicativo) che lato backend FastAPI (`HTTP 422 Unprocessable Entity`).
- **Protezione Cumulativa Multi-Batch**: Impossibile superare i 4 file attivi totali tramite upload successivi (es. 3 file + 2 file bloccati a monte).

#### 3. Delta Ledger Replay Engine & Rimozione Chirurgica:
- **Ortogonalità CE + SP**: Caricando un file di Conto Economico e successivamente uno di Stato Patrimoniale, i dati si uniscono senza cancellarsi o sovrascriversi.
- **Rollback Atomico del Singolo File (❌)**: La rimozione di un file badge rigenera lo stato applicando deterministicamente solo i file rimanenti dallo stato vergine, eliminando al 100% qualsiasi residuo fantasma (**INV-03**).
- **Riconciliazione Automatica nello SP**: Eventuali discrepanze di utile tra fonti eterogenee vengono assorbite in una riserva di riconciliazione nello Stato Patrimoniale, garantendo sempre **`|Attivo - PassivoNetto| = €0.00`** (**INV-01**).

#### 4. Event Delegation Permanente & Prestazioni:
- Zero memory leak su rigenerazione DOM grazie alla delega eventi su `#ceTableContainer` e `#spTableContainer`.
- Render debounced con `requestAnimationFrame` e mutazioni aggregate tramite `batchUpdate()`.

#### 5. Certificazione Test Suite Reale:
- 100% test superati a runtime su 5 bilanci aziendali e universitari reali (`test_real_downloads_dataset_e2e.py`, `test_hard_file_limiter_e2e.py`, `test_delta_ledger_replay.py`).
- Vecchie versioni archiviate in `/old/`.

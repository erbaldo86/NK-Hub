# Piano di Implementazione & Baseline di Sistema — v0.8.0 Golden State

## Standard Operativo: Protocollo CRV 4.0 (Nexus Keystone 3.0)

Questo documento certifica lo stato dell'applicazione al raggiungimento della **Golden Baseline v0.8.0**, punto di partenza immutabile per tutti i successivi sviluppi del Nodo 3 (CE & SP Engine).

---

## 🛡️ Invarianti di Sistema Certificati (100% PASS)

1. **Adaptive Data-Driven Viewport**: Le tabelle CE e SP mostrano esclusivamente le colonne relative agli anni con dati contabili effettivi (es. [2024, 2025]). Nessuna colonna fittizia con zeri.
2. **On-Demand Column Expansion**: Possibilità per l'utente di aggiungere dinamicamente anni storici o forecast (`➕ Aggiungi Anno`) con icona di rimozione (`🗑️`).
3. **Hard File Limiter Guard (Max 4 File)**: Rifiuto categorico di qualsiasi batch o combinazione cumulativa > 4 file (client toast e server HTTP 422).
4. **Delta Ledger Replay Engine**: Ingestione ortogonale CE + SP e rimozione chirurgica del singolo file badge con rigenerazione atomica dello stato senza residui fantasma (INV-03).
5. **Axiomatic Statutory Math**: Quadratura algebrica perfetta Art. 2424 e 2425 C.C. (Delta = €0.00) verificata sui 5 bilanci reali di test.

---

## 📊 Stato della Test Suite Deterministica

- `test_real_downloads_dataset_e2e.py`: **5/5 PASS 🟢** (10 file .json e .csv convertiti generati in `Downloads/Test/Risultato/`).
- `test_hard_file_limiter_e2e.py`: **3/3 PASS 🟢** (422 su batch overflow, 422 su cumulativo 3+2, 413 su >50MB).
- `test_delta_ledger_replay.py`: **3/3 PASS 🟢** (4 file sequenziali, eviction chirurgica, reset totale).

---

## 🏁 Roadmap per le Prossime Iterazioni

- [ ] Modulo Scenari e Sensitività Avanzata (Nodo 4 Bridge).
- [ ] Esportatore PDF Relazione di Gestione con Grafici Integrati.
- [ ] Connettore Cloud Google Drive per sincronizzazione automatica cartelle ERP.

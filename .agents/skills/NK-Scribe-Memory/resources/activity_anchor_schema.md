# 📋 Activity Anchor Schema (`nk_tracking/anchor/session_anchor.jsonl`)

> **Nodo Proprietario:** `[9] NK-Scribe-Memory` e `scripts/preflight_health_check.py` (`v1.0.0-Generation`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Struttura JSONL Obbligatoria

Ogni riga di `nk_tracking/anchor/session_anchor.jsonl` contiene un oggetto JSON valido su singola riga senza righe vuote:

```json
{
  "ts": "2026-11-15T12:00:00Z",
  "act": "MODIFY",
  "target": "scripts/rsi_convergence_engine.py",
  "detail": "Allineamento motore RSI alla release v1.0.0-Generation",
  "skill": "NK-Python-Async-Builder",
  "status": "OK"
}
```

## 2. I 7 Codici Azione Canonici (`VALID_ANCHOR_ACTS`)

Il campo `act` accetta esclusivamente uno dei seguenti 7 valori:
1. `CREATE`: Creazione di nuovi moduli, skill, regole o file di test.
2. `MODIFY`: Aggiornamento chirurgico di codice o configurazioni esistenti.
3. `DELETE`: Rimozione di file obsoleti, duplicati o orfani.
4. `REFACTOR`: Ristrutturazione interna del codice a parità di comportamento esterno.
5. `AUDIT`: Esecuzione di verifiche SAST, DAST, Oracolo o allineamento Pentad Sovrana 4+1.
6. `FIX`: Correzione di bug localizzati tramite SBFL o Fast-Healing.
7. `SYNC`: Sincronizzazione di `PATCH_NOTES.md`, `repo_map.md`, `README.md` o memoria 3-Tier.

## 3. Codici di Stato (`status`)
- `OK`: Operazione completata e verificata con successo.
- `WARN`: Operazione completata con avviso non bloccante.
- `FAIL`: Operazione fallita o annullata tramite rollback.

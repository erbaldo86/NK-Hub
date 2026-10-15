# 📋 Activity Anchor Schema (`nk_tracking/anchor/session_anchor.jsonl`)

> **Nodo Proprietario:** `NK-Scribe` e `scripts/preflight_health_check.py` (`v3.0.0-STE100-Unified`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Struttura JSONL Obbligatoria

Ogni riga del file `nk_tracking/anchor/session_anchor.jsonl` deve contenere un oggetto JSON valido su singola riga (zero righe vuote e timestamp monotoni):

```json
{
  "ts": "2026-10-14T20:00:00Z",
  "act": "MODIFY",
  "target": "scripts/rsi_convergence_engine.py",
  "detail": "Allineamento motore RSI alla release v3.0.0-STE100-Unified",
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
5. `AUDIT`: Esecuzione di verifiche SAST, DAST, Oracolo o allineamento Tetralogia.
6. `FIX`: Correzione di bug localizzati tramite SBFL o Fast-Healing.
7. `SYNC`: Sincronizzazione di `PATCH_NOTES.md`, `repo_map.md`, `README.md` o memoria 3-Tier.

## 3. Codici di Stato (`status`)
- `OK`: Operazione completata e verificata con successo.
- `WARN`: Operazione completata con avviso non bloccante.
- `FAIL`: Operazione fallita o annullata tramite rollback.

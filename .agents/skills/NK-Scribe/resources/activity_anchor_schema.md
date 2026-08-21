# 📋 Activity Anchor Schema (`session_anchor.jsonl`)

Ogni riga del file `session_anchor.jsonl` deve essere un oggetto JSON valido con i seguenti campi compatti:

```json
{
  "ts": "19:20:00",
  "act": "CREATE",
  "target": "skills/NK-Scribe/SKILL.md",
  "detail": "Creazione ufficiale skill NK-Scribe post-approvazione Super-Brief",
   "skill": "NK-System-Instruction-Builder",
  "status": "OK"
}
```

### Codici Azione Standardizzati (`act`):
- `CREATE`: Creazione di nuovi file, skill o moduli.
- `MODIFY`: Modifica di codice o configurazioni esistenti.
- `DELETE`: Rimoziode di file o file ridondanti.
- `REFACTOR`: Ristrutturazione o pulizia codice.
- `AUDIT`: Esecuzione di audit (Brief, Plan, SAST, DAST, Swarm).
- `FIX`: Correzione di bug o anomalie.
- `SYNC`: Sincronizzazione file, documentazione o repository Git.

# 📍 Knowledge Base: NK-Scribe Engine

## 1. Regola di Consolidamento Giornaliero ([RULE-05.1])
1. Data corrente: Formato `YYYY-MM-DD` (es. `2026-08-20`).
2. Regex di ricerca blocco odierno: `###\s*\[PATCH\s+v[\d\.]+\]\s*-\s*YYYY-MM-DD`
3. Se presente:
   - Individua la fine dell'elenco puntato del blocco odierno.
   - Inserisci le nuove modifiche come sotto-punti o nuovi bullet point.
4. Se assente:
   - Calcola la nuova versione incrementando il minor/patch number.
   - Inserisci il nuovo blocco subito sotto `## 🚀 Rilascio Corrente`.

## 2. Parsing Activity Anchor (`nk_tracking/anchor/session_anchor.jsonl`)
File JSONL contenente righe con i campi:
- `ts`: Timestamp ISO / HH:MM:SS
- `act`: Codice azione (es. `CREATE`, `MODIFY`, `DELETE`, `REFACTOR`, `AUDIT`, `FIX`, `SYNC`)
- `target`: File o componente impattato
- `detail`: Descrizione sintetica
- `skill`: Skill utilizzata
- `status`: OK / FAIL / WARN

## 3. Git Command Sequence (Safe Execution)
1. `git status` -> Verifica stato working tree.
2. `git add <target_files>` -> Staging mirato o globale.
3. `git commit -m "<commit_message>"` -> Commit atomico.
4. `git push origin main` -> Push su branch sovrano remoto.

## 4. Separazione Documentale Sovrana
- `PATCH_NOTES.md` alla radice è l'UNICO file canonico in cui vengono registrate le Patch Notes storiche e di release.
- `README.md` alla radice è la guida architetturale permanente ufficiale dell'ecosistema.
- `nk_tracking/quality_baseline.json` è la Single Source of Truth per i punteggi di qualità e conformità Ratchet (aggiornato atomicamente in Macro-Fase 3).

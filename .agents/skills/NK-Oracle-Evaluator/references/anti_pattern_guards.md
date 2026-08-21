# 🛡️ Regole Anti-Pattern Guards (CRV 2.0)

## 1. Anti-Mocking Guard
- **Definizione:** L'agente Writer ha il divieto di inserire nello script di test o nel codice di produzione linee che sovrascrivono forzatamente lo stato runtime (es. `state.fullData.ce = [...]`).
- **Verifica AST:** La scansione AST rigetta qualsiasi patch contenente riassegnazioni dirette a oggetti di stato globale prima delle funzioni di parsing.

## 2. Anti-Hardcoding Guard
- **Definizione:** L'agente Writer ha il divieto di inserire valori numerici fissi o costanti empiriche nel parser per far quadrare i test di uno specifico documento (es. `if val == 16920282.47`).
- **Verifica AST:** Ispezione dei nodi `ast.If` e `ast.Compare` per intercettare confronti con literal numerici a molti decimali.

## 3. Anti-Oscillation Guard (SHA-256 Patch Hashing)
- **Definizione:** Per ogni tentativo di correzione, viene calcolato l'hash SHA-256 del diff.
- **Blocco Ciclico:** Se l'hash corrisponde a quello di una patch precedentemente bocciata nel medesimo task, il ciclo viene immediatamente interrotto con eccezione `PATCH_OSCILLATION_DETECTED`.

## 4. Zero-Hallucination Audit Claim
- **Definizione:** Nessuna metric di successo (es. "eseguite 2000 simulazioni Monte Carlo") può essere riportata nel verdetto se non esiste la traccia deterministica esplicita dei log e degli exit code.

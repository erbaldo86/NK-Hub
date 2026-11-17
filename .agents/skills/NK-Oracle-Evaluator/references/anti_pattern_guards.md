# 🛡️ Regole Anti-Pattern Guards (CRV 6.0 : `v1.0.0-Generation`)

> **Nodo Proprietario:** `NK-Oracle-Evaluator` (`[RULE-01.1]`, `[RULE-01.2]`, `Dual-Execution GT-14`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Guardia Anti-Mocking (`[RULE-01.2]`)
1. **Regola:** Il Builder non usa mai `unittest.mock.MagicMock`, `@patch`, `jest.fn()` o mock sintetici nel codice.
2. **Verifica:** La scansione AST rigetta qualsiasi file che importi o istanzi oggetti mock sintetici.

## 2. Guardia Anti-Hardcoding
1. **Regola:** Il Builder non inserisce costanti ad-hoc o condizioni fittizie per superare un singolo test.
2. **Verifica:** L'Oracolo ispeziona i nodi `ast.If` e `ast.Compare` per rilevare confronti sospetti con letterali di test.

## 3. Guardia Anti-Oscillazione SHA-256 (`Guardia G3 RSI`)
1. **Regola:** Ogni iterazione calcola l'hash SHA-256 combinato dei file in `.staging/`.
2. **Verifica:** Se l'hash coincide con uno stato visitato, `scripts/rsi_convergence_engine.py` arresta il ciclo con `HALTED_CYCLE_DETECTED` (`GT-11`).

## 4. Guardia Anti-Mojibake e Integrità UTF-8 (`[RULE-08.1]`)
1. **Regola:** Tutti i file sorgente e gli output usano la codifica `UTF-8` senza BOM.
2. **Verifica:** La presenza del carattere `U+FFFD` o di sequenze byte corrotte provoca il verdetto immediato `FAIL` (`exit_code: 1`).

## 5. Guardia Zero-Hallucination e Anti-Goodharting (`[RULE-EVIDENCE]`, `[RULE-EPISTEMIC-HONESTY]`)
1. **Regola:** Ogni verdetto richiede esecuzione reale con `exit_code: 0`, `oracle_lock.json` integro e `source_url` / `evidence_quote` reali.
2. **Verifica:** Assegna `+100` al fix reale, `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`) e `-10.000` al test-gaming (`PYTEST_CURRENT_TEST`, `currentframe()`, `len(grants)`).

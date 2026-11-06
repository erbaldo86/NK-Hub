# 🛡️ Regole Anti-Pattern Guards (CRV 4.0 : `v3.0.0-STE100-Unified`)

> **Nodo Proprietario:** `NK-Oracle-Evaluator` (`[RULE-01.1]`, `[RULE-01.2]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Guardia Anti-Mocking (`[RULE-01.2]`)
1. **Regola:** Il Builder non può mai usare `unittest.mock.MagicMock`, `@patch`, `jest.fn()` o mock sintetici nel codice.
2. **Verifica:** La scansione AST e l'ispezione del codice rigettano qualsiasi file che importi o istanzi oggetti mock sintetici.

## 2. Guardia Anti-Hardcoding
1. **Regola:** Il Builder non può inserire costanti ad-hoc o condizioni fittizie per superare un singolo test.
2. **Verifica:** L'Oracolo ispeziona i nodi `ast.If` e `ast.Compare` per rilevare confronti sospetti con valori letterali di test.

## 3. Guardia Anti-Oscillazione SHA-256 (`Guardia G3 RSI`)
1. **Regola:** Ogni iterazione calcola l'hash SHA-256 combinato dei file in `.staging/`.
2. **Verifica:** Se l'hash coincide con uno stato già visitato in `visited_hashes`, `scripts/rsi_convergence_engine.py` arresta il ciclo con `HALTED_CYCLE_DETECTED` (`GT-11`).

## 4. Guardia Anti-Mojibake e Integrità UTF-8 (`[RULE-08.1]`)
1. **Regola:** Tutti i file sorgente e gli output devono usare la codifica `UTF-8` senza BOM.
2. **Verifica:** La presenza del carattere di sostituzione `U+FFFD` o di sequenze byte corrotte provoca il verdetto immediato di `FAIL` (`exit_code: 1`).

## 5. Guardia Zero-Hallucination Audit Claim (`[RULE-EVIDENCE]`)
1. **Regola:** Nessun verdetto può dichiarare test superati senza l'esecuzione reale del sottoprocesso e la registrazione dell'`exit_code: 0`.

## 6. Guardia Anti-Goodharting e Onestà Epistemica (`[RULE-EPISTEMIC-HONESTY]`, `[RULE-ORACLE-LOCK]`, `[RULE-DATA-PROVENANCE]`)
1. **Regola:** Applica `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]` (`exit_code: 0`), `[RULE-DATA-PROVENANCE]` (`source_url`, `evidence_quote`) e `[RULE-ORACLE-LOCK]` (`oracle_lock.json`).
2. **Verifica:** Assegna `+100` al fix reale e `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`); vieta `PYTEST_CURRENT_TEST`, `currentframe()` e `len(grants)` (`-10.000`).

# 🔬 Specifiche degli Oracoli Deterministici (CRV 6.0 : `v1.0.0-Generation`)

> **Nodo Proprietario:** `NK-Oracle-Evaluator` (`[RULE-01.1]`, `[RULE-RSI]`, `Dual-Execution GT-14`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. AST & Sandbox Oracle (`python -u scripts/ast_guard_validator.py --stage-dir .staging`)
1. **Scopo:** Verifica la validità sintattica (`ast.parse`), la preservazione delle firme e la telemetria temporanea in `nk_diagnostics/`.
2. **Timeout:** `30` secondi con terminazione ricorsiva dell'albero processi tramite `psutil`.
3. **Criterio di Superamento:** `exit_code: 0` e zero violazioni strutturali rilevate.

## 2. DOM & UI Structure Oracle (`python -u scripts/oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json`)
1. **Scopo:** Valida la struttura DOM HTML5 (ignorando i void tag) e la telemetria del sub-agente nativo `browser` (`DOM-01`).
2. **Timeout:** `20` secondi.
3. **Criterio di Superamento:** Assenza di tag non chiusi, zero errori console e presenza dei selettori richiesti.

## 3. Math Ground Truth & Ratchet Oracle (`python -u scripts/quality_baseline_manager.py --check-only`)
1. **Scopo:** Valida `MIN_GOLDEN_TESTS_FLOOR = 93` sui moduli `test_*.py` Zero-Mock Generation (`[RULE-01.10]`, `GT-13`) contro `nk_tracking/quality_baseline.json`.
2. **Criterio di Superamento:** Pass rate pari al `100.0%`, `branch coverage >= 85%` e zero regressioni rispetto alla baseline registrata.

## 4. RSI Convergence Oracle (`python -u scripts/rsi_convergence_engine.py --verify`)
1. **Scopo:** Verifica che $\Delta_k$ sia pari a `0` e che la fitness $Q(S_k)$ sia `100.0`.
2. **Criterio di Superamento:** Stato finale `CONVERGED_OPTIMAL` e conformità verificata allo standard `[RULE-STE100]`.

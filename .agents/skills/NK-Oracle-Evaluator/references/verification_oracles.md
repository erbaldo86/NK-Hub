# 🔬 Specifiche degli Oracoli Deterministici (CRV 4.0 : `v3.0.0-STE100-Unified`)

> **Nodo Proprietario:** `NK-Oracle-Evaluator` (`[RULE-01.1]`, `[RULE-RSI]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. AST & Sandbox Oracle (`scripts/ast_guard_validator.py --stage-dir .staging`)
1. **Scopo:** Verifica la validità sintattica (`ast.parse`), la preservazione delle firme e l'esecuzione dei test unitari in `%TEMP%\nk_sandbox_<uuid>\`.
2. **Timeout:** 30 secondi con terminazione ricorsiva dell'albero processi tramite `psutil`.
3. **Criterio di Superamento:** `exit_code: 0` e zero violazioni strutturali rilevate.

## 2. DOM & UI Structure Oracle (`scripts/oracle_evaluator_l3.py --expected --actual --json`)
1. **Scopo:** Valida la struttura DOM HTML5 (ignorando i void tag HTML5) e ispeziona il rendering tramite `chrome-devtools-mcp` e `puppeteer`.
2. **Timeout:** 20 secondi.
3. **Criterio di Superamento:** Assenza di tag non chiusi, zero errori nella console browser e presenza dei selettori richiesti.

## 3. Math Ground Truth & Ratchet Oracle (`scripts/quality_baseline_manager.py --check-only`)
1. **Scopo:** Confronta i risultati numerici e la percentuale di superamento dei 68 Golden Tests (`[RULE-01.10]`) contro `nk_tracking/quality_baseline.json`.
2. **Criterio di Superamento:** Pass rate pari al `100.0%` sui 68 Golden Tests e zero regressioni rispetto alla baseline registrata.

## 4. RSI Convergence Oracle (`scripts/rsi_convergence_engine.py --verify`)
1. **Scopo:** Verifica che $\Delta_k$ sia pari a `0` e che la fitness $Q(S_k)$ sia `100.0`.
2. **Criterio di Superamento:** Stato finale `CONVERGED_OPTIMAL` e conformità verificata allo standard `[RULE-STE100]`.

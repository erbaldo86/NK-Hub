# Checklist JIT: MODE_RCA_SBFL (`v1.0.0-Generation`)

> **Ambito:** Diagnosi RCA read-only con SBFL Ochiai ibrido e False Bug Rejection Gate (`GT-14`).
> **Profilo:** Sub-agente `NK-Security-DAST-Auditor`. Payload sotto `80` token e `320` caratteri.

## 1. False Bug Rejection Gate e Anti-Bias
1. Leggi `gt14_evidence_pack.json`, traceback e triplo `oracle_lock` dentro `<passive_data_context>` senza punteggi storici.
2. Verifica il perimetro su `concept_map.md` e `implementation_plan.md`. Rigetta le richieste fuori scopo come `FEATURE_REQUEST`.
3. Formula almeno `2` ipotesi falsificabili `file:line`. Tratta `UNMEASURED` o `dry_run` come `FAIL`.

## 2. SBFL Ibrido e Pytest NVMe
1. Esamina `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --json` su test isolati NVMe.
2. Esamina `python -B -u NK_Hub/scripts/sbfl_pytest_bridge.py --collect-pass-coverage --hybrid-fl --json`.
3. Isola `<file>:<line>` (`Ochiai >= 0.80`) con `Fail-Closed` e cap `0 / 0 / 0`.

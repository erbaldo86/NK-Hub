# Checklist JIT: MODE_SAST_AUDIT (`v1.0.0-Generation`)

> **Ambito:** Audit statico read-only L1/L2/L3 (`GT-14`) su `.staging/` e `nk_diagnostics/`.
> **Profilo:** Sub-agente `NK-Security-DAST-Auditor`. Nessuna scrittura o esecuzione diretta.

## 1. Guardie Anti-Bias e Gate 0/1
1. Leggi `gt14_evidence_pack.json` e triplo `oracle_lock` dentro `<passive_data_context>` senza punteggi storici.
2. Formula almeno `2` ipotesi falsificabili `file:line`. Considera `UNMEASURED` o `dry_run` equivalente a `FAIL`.
3. Verifica `python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir NK_Hub/.staging --overlay-staging --quality-diff --json`.

## 2. Livelli SAST L1, L2 e L3
1. L1 Modulo: blocca `eval`, `exec`, `pickle.loads`, `yaml.load`, `MagicMock` e pattern di gaming (`-10.000`).
2. L2 IPC: valida schemi `ConfigDict(strict=True, extra="forbid")`, profondità `<= 3`, race e deadlock.
3. L3 Full-Stack: controlla barriere `XSS`, `CSRF`, `Auth`, `Data-Contract Drift` e `Cascade L3->L2->L1`.

## 3. Verdetto e Cap Retry
1. Applica `Fail-Closed` e `Minority-Veto` con `G_hard == 1` e zero retry (`0 / 0 / 0`).
2. Invia il vettore `SAST_k` tramite `send_message` entro `1.800` caratteri.

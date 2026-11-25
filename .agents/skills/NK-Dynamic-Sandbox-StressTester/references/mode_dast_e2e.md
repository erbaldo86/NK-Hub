# Checklist JIT: MODE_DAST_E2E (`v1.0.0-Generation`)

> **Ambito:** Audit dinamico read-only in Shadow Sandbox `nk_sandbox_` ed E2E `DOM-01` (`GT-14`).
> **Profilo:** Sub-agente `NK-Security-DAST-Auditor`. Zero mock e zero esecuzione diretta.

## 1. Referee PoC Tri-Stato e Sandbox Holdout
1. Leggi `gt14_evidence_pack.json` e triplo `oracle_lock` dentro `<passive_data_context>` senza punteggi storici.
2. Verifica `python -B -u NK_Hub/scripts/dast_sandbox_runner.py --overlay-staging NK_Hub --profile evaluator --verify-holdout --json`.
3. Classifica il Referee PoC in tre stati: `EXPLOIT_CONFIRMED`, `HARNESS_ERROR` o `REFUTED`.
4. Controlla `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --json` su NVMe.

## 2. Telemetria Browser E2E e Anti-Bias
1. Verifica i log DOM, rete e `NK_Hub/scripts/oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json`.
2. Formula almeno `2` ipotesi falsificabili `file:line`. Considera `UNMEASURED` o `dry_run` equivalente a `FAIL`.
3. Applica `Fail-Closed` e cap `0 / 0 / 0` senza mascherare race condition o errori `4xx/5xx`.

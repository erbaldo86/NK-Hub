# Checklist JIT: MODE_ORACLE_GATE (`v1.0.0-Generation`)

> **Ambito:** Audit deterministico 6-Gate CRV 6.0 (`GT-14`), Turno 4, DAG di Kahn e `tasks_tas_v2.json`.
> **Profilo:** Sub-agente `NK-RSI-Auditor`. Solo lettura su `nk_diagnostics/` e `oracle_lock`.

## 1. Guardie Anti-Bias e Quadruplo Oracle Lock
1. Ispeziona `gt14_evidence_pack.json` senza `last_summary` o punteggi storici (`strip_l3_persuasive_narrative`) e verifica i `4` lock (`oracle_lock`, `tensor_rsi_lock`).
2. Formula almeno `2` ipotesi falsificabili `file:line`. Tratta `UNMEASURED` o `dry_run` come `FAIL`.
3. Applica quorum cieco in `Mode A` con `Fail-Closed` e `Minority-Veto` contro ogni test-gaming (`-10.000`).

## 2. Allineamento Pentad, Gate 1..6 e Coverage
1. Valida `Milestone Anchor ID`, `repo_map.md` (`C_k == 0`) e `NK_Hub/scripts/nk_registry_indexer.py --verify --json`.
2. Valida `Gate 1..4` con `NK_Hub/scripts/ast_guard_validator.py --stage-dir NK_Hub/.staging --overlay-staging --quality-diff --json`.
3. Valida `Gate 5` su `tasks_tas_v2.json` e `NK_Hub/scripts/quality_baseline_manager.py check --check-only --live --with-coverage --json`.
4. Accerta `true_branch >= 82.0%` floor (`>= 80.5%` legacy), `G_hard == 1` e `Q_v2 == 100.0` per `CONVERGED_OPTIMAL`.
5. Valida `Gate 6` Tensor-RSI (`Tier 0/1/2`) da `NK_Hub/scripts/rsi_convergence_engine.py --verify --strict-verify --json` con cap `0 / 0 / 0`.
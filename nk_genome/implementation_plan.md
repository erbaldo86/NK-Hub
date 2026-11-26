# Implementation Plan: `NK-Parallel Sovereign v3` (`NK-GEN-4.0.1` .. `NK-GEN-4.0.4`)

> **Brief ID:** `IB-20261125-4EF84F` | **Stato:** `COMPLETED_M4` | **Standard:** `[RULE-STE100]` | **Profilo:** `generation`  
> **Origine:** Sintesi 3-Way (`Neon` + `Carbon` + `Piano C`) con audit Swarm (`DOM-04` Red-Team e RSI).  
> **Perimetro:** Esecuzione parallela multi-progetto, multi-chat e multi-builder swarm senza degrado qualitativo.

---

## 1. Sintesi Esecutiva e Architettura a `3` Strati Parallelizzati

**NK-Parallel Sovereign v3** trasforma `NK_Hub` in un ambiente multi-lane isolato con zero contention e ratchet integrale.
Il codice mantiene budget strict sui manifesti (`+0 B` su `nk_registry_manifest.json` e `DOM-04.json`) e regole Win32 NVMe.

| Milestone | Scope Operativo | Moduli Chiave (`_internal/`) | Stato |
| :--- | :--- | :--- | :--- |
| **`NK-GEN-4.0.1` (`M1`)** | Isolamento Cross-Project, NVMe Storage e Pytest Speed | `nvme_storage_guards`, `wal_scope`, `lane_leases`, `worker_budget`, `nvme_base_cache`, `parallel_contracts` | `COMPLETED` |
| **`NK-GEN-4.0.2` (`M2`)** | Multi-Lane `.staging/lanes/<id>/`, Claim `child_cid`, Router L0, Tensor-RSI e DAST | `lane_paths`, `lane_registry`, `active_slot_io`, hook gates `-S` | `COMPLETED` |
| **`NK-GEN-4.0.3` (`M3`)** | Commit Train 2PC Serializzato, Goldilocks Nonce, Integrita e Tool Isolation | `commit_train_*`, `journal_multi`, `occ_and_ast_gate`, `delta_regate`, `cas_guard`, `integrity_anchor_sync` | `COMPLETED` |
| **`NK-GEN-4.0.4` (`M4`)** | Kahn DAG Wave Scheduler, Sub-Lane Swarm, Frontend `fe_shadow/` e Sync SSOT | `dag_wave_scheduler`, `preflight_conflict_predictor`, `sublane_consolidator`, `fe_shadow` | `COMPLETED` |

---

## 2. Invarianti Non Negoziabili e Budget

1. **Zero Nuovi Script Top-Level (`+0 B`):** Tutte le nuove librerie risiedono in `scripts/_internal/nk_common/` o `scripts/_internal/win32_2pc_engine/`.
2. **Storage Anti-Lock e Zero `os.link`:** La base NVMe in `%TEMP%/nk_nvme_base_cache/` usa file read-only. Ogni copia NVMe usa shutil senza hardlink.
3. **Purezza `-S` sugli Hook:** I moduli importati da `nk_acs_fastguard` e `nk_hook_gate` restano pure stdlib senza `pydantic`.
4. **Two-Phase Lock Protocol (`R3[P0]`):** I manifesti `nk_tracking/*_lock*.json` restano intatti durante la build e vengono congelati post-2PC.
5. **Qualita e Complessita:** Moduli `<= 250` LOC, `0` cicli Tarjan, classi univoche, true branch `>= 86%` e zero mock.

---

## 3. Matrice di Verifica `NK-GEN-4.0.1` (`M1`)

| Controllo | Comando Canonico (`NVMe` / `.staging/`) | Soglia |
| :--- | :--- | :--- |
| **AST + Quality-Diff** | `python -B -u NK_Hub/scripts/ast_guard_validator.py --target NK_Hub/.staging --quality-diff` | `0` violazioni, `0` `QD-CC-REGRESSION` |
| **Isolated Pytest Fast** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --pytest-args "-m fast -q"` | `100%` PASS, `<= 8.0s` |
| **Live Full + Coverage** | `python -B -u NK_Hub/scripts/quality_baseline_manager.py check --check-only --live --with-coverage` | `<= 28.0s`, branch `>= 83.43%`, combined `>= 88.95%` |
| **Holdout & DAST** | `python -B -u NK_Hub/scripts/dast_sandbox_runner.py --profile evaluator --verify-holdout --json` | `passed: True`, `4` lock verificati |
| **GT-14 Bundle + Quorum** | `python -B -u NK_Hub/scripts/rsi_convergence_engine.py --emit-gt14-bundle --strict-verify --with-dast --json` | `G_hard == 1`, `Q_v2 == 100.0`, doppio `APPROVE` `DOM-04` |

---

## 4. Matrice di Verifica `NK-GEN-4.0.2` (`M2`)

Ogni controllo seguente valida l'isolamento multi-lane di `M2` in `.staging/`.
Nessun test usa mock o modifica file di lock fuori `.staging/`.

| Controllo | Comando Canonico (`NVMe` / `.staging/`) | Soglia |
| :--- | :--- | :--- |
| **1. AST + Quality-Diff** | `python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir NK_Hub/.staging --overlay-staging --quality-diff --json` | `0` violazioni, `0` `QD-CC-REGRESSION` |
| **2. Purezza Stdlib `-S`** | `python -B -S -c "... import lane_paths, lane_registry, nvme_mirror_helpers, state_rmw, z2_and_l0; assert 'pydantic' not in sys.modules"` | `STDLIB_S_PASS`, zero `pydantic` |
| **3. Pytest Fast Isolato** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --pytest-args "-m fast -q"` | `100%` PASS, `<= 8.0s` |
| **4. Coverage Branch M2** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --coverage --json` | `100%` PASS, branch `>= 86%` sui `4` moduli M2 |
| **5. Mutation Gate M2** | `python -B -u NK_Hub/scripts/builder_mutation_gate.py --stage-dir NK_Hub/.staging --min-kill-rate 0.85 --max-mutants 8` | `kill_rate >= 0.85` sui `4` moduli M2 |
| **6. Baseline & Budget** | `quality_baseline_manager.py check --check-only --live --with-coverage`, `nk_registry_indexer.py --verify`, `preflight_health_check.py --check-only` | `PASS`, manifesti `+0 B` dentro budget |
| **7. Holdout & DAST Lane** | `python -B -u NK_Hub/scripts/dast_sandbox_runner.py --overlay-staging NK_Hub --profile evaluator --verify-holdout --json` | `passed: True`, `f_holdout == 0` |
| **8. GT-14 Bundle + Quorum** | `python -B -u NK_Hub/scripts/rsi_convergence_engine.py --emit-gt14-bundle --strict-verify --with-dast --mutation-report m2_mut_report.json --json` | `G_hard == 1`, `Q_v2 == 100.0`, doppio `APPROVE` `DOM-04` |

---

## 5. Matrice di Verifica `NK-GEN-4.0.3` (`M3`)

Ogni controllo seguente valida Commit Train 2PC, Goldilocks Nonce, integrita `VALID_ADVANCED` e isolamento tool di `M3`.
Nessun test usa mock o modifica file di lock fuori `.staging/`.

| Controllo | Comando Canonico (`NVMe` / `.staging/`) | Soglia |
| :--- | :--- | :--- |
| **1. AST + Quality-Diff** | `python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir NK_Hub/.staging --overlay-staging --quality-diff --json` | `0` violazioni, `0` cicli Tarjan |
| **2. Purezza Stdlib `-S`** | `python -B -S -c "... import commit_train_store, lane_lease_probe, nvme_storage_guards, integrity_anchor_sync, state_rmw, evaluator"` | `STDLIB_S_PASS`, zero `pydantic` |
| **3. Pytest Fast Isolato** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --pytest-args "-m fast -q"` | `100%` PASS, `<= 8.0s` |
| **4. Coverage Branch M3** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --coverage --json` | `100%` PASS, branch `>= 86%` sui nuovi moduli M3 |
| **5. Mutation Gate M3** | `python -B -u NK_Hub/scripts/builder_mutation_gate.py --stage-dir NK_Hub/.staging --min-kill-rate 0.85 --max-audit-mutants 12` | `kill_rate >= 0.85` sui nuovi moduli M3 |
| **6. Baseline & Budget** | `quality_baseline_manager.py check --check-only --live --with-coverage`, `nk_registry_indexer.py --verify`, `preflight_health_check.py --check-only` | `PASS`, manifesti `+0 B` dentro budget |
| **7. Holdout & DAST Lane** | `python -B -u NK_Hub/scripts/dast_sandbox_runner.py --overlay-staging NK_Hub --profile evaluator --verify-holdout --json` | `passed: True`, `f_holdout == 0` |
| **8. GT-14 Bundle + Quorum** | `python -B -u NK_Hub/scripts/rsi_convergence_engine.py --emit-gt14-bundle --strict-verify --with-dast --mutation-report m3_mut_report.json --json` | `G_hard == 1`, `Q_v2 == 100.0`, doppio `APPROVE` `DOM-04` |

---

## 6. Matrice di Verifica `NK-GEN-4.0.4` (`M4`)

Ogni controllo valida Scheduler Kahn, Pre-Flight AST Predictor, Sub-Lane Consolidator e `fe_shadow/`. Valida anche il fix frontmatter e l'ownership dei piani.

| Controllo | Comando Canonico (`NVMe` / `.staging/`) | Soglia |
| :--- | :--- | :--- |
| **1. AST + Quality-Diff** | `python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir .staging --overlay-staging --quality-diff --json` | `0` violazioni, `0` cicli Tarjan |
| **2. Purezza Stdlib `-S`** | `python -B -S -c "... import lane_paths, lane_registry, constants_patterns, path_safety, lane_write_guard, write_gate"` | `STDLIB_S_PASS`, zero `pydantic` |
| **3. Pytest Fast Isolato** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --pytest-args "-m fast -q"` | `100%` PASS, `<= 8.0s` |
| **4. Coverage Branch M4** | `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --targets tests/test_parallel_m4_fast.py --coverage --json` | `100%` PASS, branch `>= 86%` sui `4` moduli M4 |
| **5. Mutation Gate M4** | `python -B -u NK_Hub/scripts/builder_mutation_gate.py --stage-dir .staging --audit-full-module --max-audit-mutants 12 --min-kill-rate 0.85` | `kill_rate >= 0.85` sui `4` moduli M4 |
| **6. Baseline & Budget** | `platform_runner.py --pytest-isolated --overlay-staging --coverage`, `nk_registry_indexer.py --verify`, `4` lock freeze post-2PC | `<= 28.0s`, `DOM-01/04 <= 4700 B`, manifest `<= 3150 B` |
| **7. Holdout & DAST Lane** | `python -B -u NK_Hub/scripts/dast_sandbox_runner.py --overlay-staging NK_Hub --profile evaluator --verify-holdout --json` | `passed: True`, `f_holdout == 0` |
| **8. GT-14 Bundle + Quorum** | `python -B -u NK_Hub/scripts/rsi_convergence_engine.py --emit-gt14-bundle --strict-verify --with-dast --mutation-report m4_mut_report.json --json` | `G_hard == 1`, `Q_v2 == 100.0`, doppio `APPROVE` `DOM-04` |

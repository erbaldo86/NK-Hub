---
title: "NK Genome: Registro Ufficiale Patch Notes"
version: "1.0.0-Generation"
milestone_anchor_id: "NK-GEN-1.0.0"
rsi_profile: "ste100_rsi"
---

# Registro Ufficiale Patch Notes (`NK_Hub`)

> **Politica SSOT:** Registro append-in-testa (`prepend-only`) certificato post-commit `Win32 2PC` a $\Delta_k = 0$.  
> **Standard:** Italiano Tecnico ASD-STE100 (`[RULE-STE100]`, frasi attive `<= 20` parole).

---

## [NK-GEN-3.0.2-GITHUB-RELEASE] (2026-11-25)

* **Vetrina GitHub `v3.0.2-Generation`:** Aggiorna `.github/README.md` in parità bilingue IT/EN con badge `NK-GEN-3.0.2-FORENSIC-HARDENING-CLEAN` e `Core ABI 1.0.0-Generation`.
* **Sezione Upgrade Qualitativo:** Espone il confronto `v1.0.0-Generation` vs `v3.0.2-Generation` con `Tensor-RSI v3`, `Q_v2 = 100.0` e `quality_baseline.json`.
* **Manuali `nk_docs_and_setup/` e CI:** Allinea `README.md`, `README.it.md`, `GUIDA_INSTALLAZIONE.md`, `00_MAPPA_LIBRERIA_NK.md` e l'intestazione `.github/workflows/ci.yml`.
* **Sigillo `oracle_lock.json` e Pacchetto ZIP:** Verifica i `4` sigilli `SHA-256` e rigenera `NK_Hub_OneClick_Package.zip` senza PII né file temporanei.

## [NK-GEN-3.0.2-FORENSIC-HARDENING-CLEAN] (2026-11-24)

* **Allineamento `GT-14` e Sharding `RSI`:** Propaga `--diff-aware` e `--profile` in `engine.py` e `gt14_probes.py` su `.staging/` vuota. Isola `vibe_report_helpers.py` con sharding `NVMe` a `6` worker (`385/385` `PASS`).
* **Hardening Forense `Wave 0..3`:** Applica clamp `NaN/Inf`, Jeffreys `LCB90` e filtro gaming su `tensor_rsi`. Aggiunge `--step status/abort`, `TTL/CAS`, blocco env tamper, `ACTIVE_CONTINUATION` `AP-12` e `--with-dast` forwarding (`tests/test_forensic_hardening_fast.py`).
* **Runner NVMe e Piramide CI:** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` isola `platform_runner.py` e `quality_baseline_manager`. Estrae il wall-time da JUnit XML mantenendo `tier 1 -m fast <= 8.0s` e `tier 1+2 <= 28.0s`.
* **Potatura Orfani (`.deleted_files.json`):** Rimuove `checkpoint_v1_0_0_generation.json`, `IB-20261123-894C79.md` e `16` file orfani di sessione in `nk_tracking/sessions/`.
* **Allineamento Docs, CI e `4` Lock:** Sincronizza `.github/workflows/ci.yml` (`88.0% / 82.0%`) e i `4` sigilli `SHA-256`. Aggiorna `NK Proget/Locale/` + `Online/` RO, profili installer e `nk_genome/`.
* **Precedenza Milestone Post-Compattazione:** Riallinea `z2_and_l0.py`, `anchor_store.py`, `handoff_engine.py`, `context_view.py` e `cli.py` su `2PC_ATOMIC_PROMOTION` più recente. Aggiunge test fast anti-regressione in `tests/test_wave6_bootstrap_handoff_fast.py`.
* **Risoluzione Root Workspace Padre:** Riallinea `state_rmw.py`, `stop_evidence_cli.py` e `path_safety.py` privilegiando `scripts/` rispetto a `.staging/`. Aggiunge test fast anti-regressione in `tests/test_wave6_bootstrap_handoff_fast.py` portando la suite a `384/384` (`20.0s`).

## [NK-GEN-3.0.1-PROGET-MIGRATION] (2026-11-24)

* **Sola Lettura `NK Proget/Online/` (`CRIT-01`):** `nk_hook_gate` (`target_classifier.py`, `mcp_classifier.py`), `win32_2pc_engine.py` e `scaffolder_cli.py` bloccano scritture, `cd && redir` e path MCP `NK Proget/`.
* **Allineamento `NK Proget/Locale/` (`CRIT-02`, `HIGH-03..07`):** Abilita `.staging/` in `Locale/` e aggiorna `isolated_test_runner.py`, `ecosystem_scanner.py`, `handoff_verify.py`, `win32_proc.py` e `scaffolder_cli.py`.
* **Migrazione Applicativi `4/4` e `CWE-78`:** Supera `526/526` test `PASS` (`NK-Bandi` `264`, `NK-Studio-CRM` `128`, `NK-Cloud-Platform` `133` incl. fix `deploy_module.ps1`, `NK-Studio-Lab-Progettazione` `1`).
* **Suite `NK_Hub`, Copertura e Sigilli:** `tests/test_nk_proget_locale_online_governance.py` porta la suite a `362/362` test (`26.445s <= 28.0s`), `stmt 91.44%`, `branch 83.69%`, `combined 89.18%`, `ast_guard` `0/352`. Sincronizza `oracle_lock.json`, `governance_lock.json`, `quality_baseline.json` e `nk_registry_manifest.json`.

## [NK-GEN-3.0.0-TENSOR-CORE] (2026-11-24)

* **Control Plane `Tensor-RSI v3`:** `scripts/tensor_rsi.py` espone `5` flag CLI e ticket `trsi1` HMAC con `Win32NamedMutex` ([arXiv:2605.21384v1](https://arxiv.org/abs/2605.21384v1)). I moduli interni gestiscono `IntentTrack`, `PolicyTensor`, `ParetoGate` (`Tier 0/1/2`), `CladeBandit` (`K=4`), `VoI` e profili `neon`, `pro`, `flash` ([arXiv:2512.00930v1](https://arxiv.org/abs/2512.00930v1), [arXiv:2507.19457](https://arxiv.org/abs/2507.19457), [arXiv:2505.22954](https://arxiv.org/abs/2505.22954)).
* **Hardening `2PC` e Hook Gate:** `nonce_store.py` applica anti-replay persistente sotto `Win32NamedMutex` in `LOCALAPPDATA/nk_hub/governance_nonces.json` per token `v2:` e `--promote-staging`. `tensor_session_guard.py` e `nk_hook_gate` bloccano `--promote-staging` senza `ACTIVE.json` (`accepted == True`, `staging_manifest_sha256` valido, [arXiv:2506.13131](https://arxiv.org/abs/2506.13131)). `constants.py` protegge `tensor_rsi` e `guards_ratchet.py` verifica `oracle_lock` su dict, v1 e staging.
* **Epistemic Firewall e Monitor:** `epistemic_firewall_rules.py` estende `AP-12/13` a `ACTIVE_CONTINUATION` e aggiunge `strip_l3_persuasive_narrative(bundle)` (`last_summary`, score storici, narrative `L3`, [arXiv:2610.12822](https://arxiv.org/abs/2610.12822)). `holdout_verify.py` verifica `tensor_rsi_lock.json` e `transcript_scan.py` rileva letture holdout o edit test nello stesso turno ([arXiv:2410.20285](https://arxiv.org/abs/2410.20285), [OpenAI CoT Monitoring](https://openai.com/index/chain-of-thought-monitoring/), [Anthropic Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
* **Oracolo `DOM-04` e Skill Sync:** `rsi_convergence_engine` richiede `G_hard == 1` e `Q_v2 == 100.0` per `CONVERGED_OPTIMAL`, applica cap `49.9` su `FAIL` e `MIN_KILL_RATE_FLOOR = 0.80`. Le `11` skill, `AGENTS.md`, `tensor_rsi_v3_protocol.md`, i gemelli `nk-gate` (`6/6`) e `nk_genome/` recepiscono il floor `82.0%`.
* **Promozione e Baseline (`quality_baseline.json`):** `NK-GEN-3.0.0-TENSOR-CORE` promuove `75` file atomici via `Win32 2PC`. La suite supera `355/355` test `PASS` (`17.3s`, `stmt 91.41%`, `branch 83.6%`, `combined 89.14%`).

## [NK-GEN-2.1.0-W6] (2026-11-23)

* **Milestone e Promozione `Win32 2PC`:** `NK-GEN-2.1.0-W6` promuove `36` file in modo atomico. Mantiene `10` file invariati, `0` rimossi e `GOVERNANCE_OVERRIDE` su `6` percorsi protetti.
* **Refactoring Modulare `Wave 5`:** Estrae `23` file Python in `builder_mutation_gate`, `vibe_sprint_router`, `nk_session_handoff`, `nk_session_bootstrap` ed `nk_acs_fastguard`. Ogni modulo rispetta `303 <= 350` LOC con `0` cicli Tarjan SCC.
* **Mutation Audit Reale:** `builder_mutation_gate.py` attiva la modalita reale `--audit-full-module`. La suite permanente `tests/test_wave5_mutation_audit.py` verifica il gate completo.
* **Piramide Test `Wave 6`:** Aggiunge `4` nuove suite zero-mock `@pytest.mark.fast` (`test_wave6_vibe_router_fast.py`, `test_wave6_acs_fast.py`, `test_wave6_bootstrap_handoff_fast.py`, `test_wave6_mutation_gate_fast.py`). Il registro indicizza `33` suite in `DOM-06.json` e `298` file totali.
* **Suite e Tempi Certificati (`quality_baseline.json`):** La suite supera `319/319` test (`100.0%`, `0` failed, `0` skipped) in `20.14s` (`19.62s` `GT-14`, `<= 28.0s`). Il profilo `-m fast` chiude `243/243` test in `7.983s <= 8.0s`.
* **Copertura e Mutation Audit (`Wave 5` + `Wave 6`):** La copertura raggiunge `91.21%` stmt, `83.38%` branch e `88.91%` combined. Il mutation audit supera `21/21` moduli al `97.22%` (`245/252` killed, `0` sotto `0.85`).
* **Sicurezza `DAST`, `GT-14` e Blind Quorum:** `DAST Shadow Sandbox` emette `PASS` su `327` file con `0` violazioni. `GT-14` certifica `6/6` probe `CERTIFIED_PASS` (`Q_v2=100.0`, `delta_k=0`, `gaming_penalty=0`) con doppio `APPROVE` `DOM-04`.

## [NK-GEN-2.0.0-W3] (2026-11-23)

* **Milestone:** `NK-GEN-2.0.0-W3` consolida profili `DOM-04` Gemini 4, sharding `JIT`, indicizzazione `O(1)` ed aggiornamento `quality_baseline.json` `Schema v2` in `.staging/`.
* **Agenti `DOM-04` (`patch_version: 12`):** `NK-RSI-Auditor` e `NK-Security-DAST-Auditor` usano solo `read_file` e `send_message` con `4` guardie Anti-Bias e `6/6` gemelli `nk-gate`.
* **Skill Compresse e Riferimenti `JIT`:** Le `4` `SKILL.md` di `DOM-04` scendono a `37..38` righe (`<= 40`). I `4` `references/mode_*.md` restano entro `14..18` righe (`<= 25`).
* **Allineamento `[8]` e Ritiro Legacy:** `NK-Bug-Diagnostic-Engine` passa a `L0 / Producer` con `retry_caps [0, 0, 0]` in `skill_golden_eval_set.json`. `.deleted_files.json` ritira `9` asset legacy `DOM-04`.
* **Cinque Fix `nk_registry_indexer`:** `hygiene_filter.py` filtra keyword `<= 32` caratteri. `taxonomy.py` espone `SKILL_PRIMARY_SCRIPTS` e `SCRIPT_SKILL_MAP`. `shards.py` compatta `DOM-04.json` a `4484` B (`7` shard `<= 4700` B). `shards_rehydrate.py` allega gli script primari. `lookup.py` risolve step `2b`, `3`, `4a` e `4c`, mentre `manifest_builder.py` aggiorna `SKILL_INDEX.md` (`5` domini, `7` shard, `11` skill, `33` script).
* **Suite Aggiuntiva Step 4:** `tests/test_nk_registry_indexer_w3.py` e `tests/test_skill_evals.py` estendono la suite a `286/286` test senza regressioni. La sotto-suite `not stress` supera `257/257` test in `15.942s`.
* **Baseline Live Certificata (`quality_baseline.json`):** Registra `286/286` test (`100.0%`, `0` failed, `0` skipped) in `20.95s <= 28.0s`. Copertura `statement_coverage_pct: 90.94%`, `true_branch_coverage_pct: 83.0%`, `combined_coverage_pct: 88.59%` con `0` violazioni SAST/AST su `311` file.

## [NK-GEN-2.0.0-W2] (2026-11-23)

* **Milestone:** `NK-GEN-2.0.0-W2` (`NK-GEN-2.0.0-W2-SUBMODULAR-PYRAMID`) promuove `46` file con `7` rimozioni tramite `Win32 2PC`.
* **Piramide Test e Sharding NVMe:** `pytest.ini` attiva i marker `fast`, `integration` e `stress`. `tests/conftest.py` aggiunge `[FAST-GUARD]`, `safe_rmtree` e `.deleted_files.json`, affiancato da `pytest_parallel.py` LPT.
* **Holdout Reali e Ritiro Sintetici:** Ritira `5` suite monolitiche e `2` benchmark sintetici (`tasks_v1.json`, `tasks_builder_v2.json`). Introduce `tasks_tas_v2.json` (`16` task), `tas_behavioral_v2.json` e `tests/test_wave2_holdout_and_pyramid.py` (`k=3`).
* **Ratchet Schema `v2`, Triplo Lock e CI:** `quality_baseline_manager.py` impone `14` metriche, `12` `REQUIRED_RATCHET_KEYS` e ceiling `28.0s` / `8.0s`. Sigilla `oracle_lock.json`, `oracle_lock_holdout.json` e `governance_lock.json`, aggiornando `.github/workflows/ci.yml`.
* **Baseline Live Certificata (`quality_baseline.json`):** Registra `274` test su `274` (`100.0%`, `0` failed, `0` skipped) in `22.03s`. Copertura `statement 90.92%`, `true_branch 82.94%`, `combined 88.55%` e `0` SAST critici.

## [NK-GEN-2.0.0-W1] (2026-11-22)

* **Milestone:** `NK-GEN-2.0.0-W1` (`NK-GEN-2.0.0-W1-TAS-MODERNIZATION`) promuove `110` file ed elimina `10` sottomoduli obsoleti di `rsi_convergence_engine` via `Win32 2PC`.
* **Motore `RSI v2` e Sicurezza `2PC`:** Introduce `Q_v2(S_k)`, `14` gate `G_hard` e penalita `-10.000`. Aggiunge `governance_auth.py` (`HMAC-SHA256` esterno), blocco `dry_run` e `--hybrid-fl` (`<= 80` tok) in `sbfl_pytest_bridge.py`.
* **Hardening Analisi, DAST e Mutation:** Potenzia `ast_guard_validator`, `dast_sandbox_runner`, `oracle_evaluator_l3`, `builder_mutation_gate` (`UNMEASURED`) ed `nk_common`.
* **Baseline Live Certificata (`quality_baseline.json`):** Registra `522` test su `522` (`100.0%`, `0` failed, `0` skipped) in `70.43s`. Copertura `statement 89.29%`, `true_branch 80.09%`, `combined 86.56%` e `0` SAST critici.

## [NK-GEN-2.0.0-W0] (2026-11-22)

* **Milestone:** `NK-GEN-2.0.0-W0` promuove `12` file di fondazione per `Win32 2PC`, `oracle_lock.py`, `tas_ssot_io.py`, costanti `quality_baseline_manager` e telemetria `rsi_convergence_engine`.
* **Copertura Test Iniziale:** Aggiorna `tests/test_quality_baseline_manager.py`, `tests/test_rsi_convergence_engine.py` e `tests/test_win32_2pc.py`.

## [NK-GEN-1.3.1-P2-HARDENING] (2026-11-22)

* **Milestone:** `NK-GEN-1.3.1-P2-HARDENING` consolida `5` moduli critici tramite promozione atomica `Win32 2PC`.
* **DAST Fail-Closed (`vibe_report_helpers.py`):** `scripts/_internal/rsi_convergence_engine/vibe_report_helpers.py` applica `dry_run=True` fail-closed prioritario in `_dast_report_passed` e `_dast_flag_fail_reason`.
* **Sandbox Path Confinement (`process_runner.py`):** `scripts/_internal/dast_sandbox_runner/process_runner.py` confina l'entrypoint `build_traced_command` tramite `_resolve_confined_sandbox_path`.
* **Holdout Integrity (`holdout_verify.py`):** `scripts/_internal/dast_sandbox_runner/holdout_verify.py` protegge e verifica `nk_tracking/oracle_holdout` e `tests/evals`.
* **Soglie Dinamiche (`ab_benchmark.py`):** `scripts/_internal/rsi_convergence_engine/ab_benchmark.py` carica `autonomous_context_shield.z3_tokens` da `nk_genome/configs/saturation_thresholds.json`. Il fallback usa `205000.0`.
* **Inoltro 1:1 (`engine.py`):** `scripts/_internal/rsi_convergence_engine/engine.py` inoltra `mutation_report`, `dast_report`, `allowed_files` e `scan_prod_frontend`. I parametri raggiungono `verify_ecosystem` ed `emit_gt14_bundle`.
* **Suite Zero-Mock:** La suite esegue `470` test con `100.0%` pass (`0` failed, `0` skipped). Aggiunge `5` test `@pytest.mark.fast` in `tests/test_dast_sandbox.py` e `tests/test_rsi_convergence_engine.py`.
* **Baseline e Copertura (`quality_baseline.json`):** Registra `statement_coverage_pct: 88.83%`, `true_branch_coverage_pct: 79.35%` e `branch_coverage_pct: 79.35%`. Raggiunge `combined_coverage_pct: 86.03%`, `pytest_duration_s: 61.64s` e `harness_token_overhead_pct: 2.51%`.
* **Benchmark A/B e Sigillo Oracle:** `tasks_v1.json` supera `12/12` task e `tasks_builder_v2.json` supera `16/16`. `oracle_lock.json` blocca `376` file (`combined_sha256: ef26205fbb9a4ecf85ef48f2d8e4597f326ce65596255fc3c2d0d3b9992b01f3`).
* **Audit `GT-14`:** `NK-Security-DAST-Auditor` e `NK-RSI-Auditor` emettono doppio `APPROVE` con `0` `P0` e `0` `P1`.

## [NK-GEN-1.3.0-EXTERNAL-AUDIT-RSI-PURGE] (2026-11-22)

* **Milestone e Brief:** `NK-GEN-1.3.0-EXTERNAL-AUDIT-RSI-PURGE` (`IB-20261122-57E514`) chiude l'audit esterno con hardening `RSI` e potatura suite.
* **Debloat CLI e Limite Righe:** Gli script top-level scendono da `39` a `33`. Tutti i moduli `.py` sotto `scripts/` rispettano il limite `<= 400` righe.
* **Script Ritirati e Unificati:** Ritirati `invisible_healing_loop.py`, `nk_auto_inning.py`, `micro_hud_renderer.py`, `nk_active_runtime_sentinel.py` e `nk_swarm_messenger.py`. Il modulo `sbfl_engine.py` confluisce in `sbfl_pytest_bridge.py`.
* **Catalogo Ecosistema:** Il registro certifica `5` domini, `11` skill, `6` agenti nativi e `10` file `Docs & Setup`.
* **5 Fix P1 `GT-14` (`P1-A..P1-E`):** `P1-A` chiude fail-closed DAST in `vibe_report_helpers.py`. `P1-B` chiude fail-closed `rsi_bridge_helpers.py`. `P1-C` aggiunge forward CLI in `quality_baseline_manager/cli.py`. `P1-D` impone `true_branch >= 75.0%` e chiavi obbligatorie. `P1-E` certifica audit RO governance `Mode D`/`DOM-04` in `intent_classifier.py`.
* **Suite Zero-Mock:** La suite esegue `465 passed, 0 failed, 0 skipped` (`-23.14%` rispetto a `605`, pass rate `100.0%`).
* **Tempi Pytest e DAST:** Il runner DAST impiega `54.372s` su pytest (`57.46s` in `quality_baseline_manager --live`, `67.8104s` holdout `--verify-holdout` completo). I tempi pre-audit erano `131.38s` live e `139.82s` timeout DAST `FAIL`.
* **Copertura Baseline (`quality_baseline.json`):** La misurazione registra `statement` `88.81%`, `true_branch` `79.32%` e `branch` `79.32%`. La copertura combinata raggiunge `86.01%`.
* **Benchmark A/B `v1` e `v2`:** `tasks_v1.json` supera `12/12` task (`ab_success_full: 100.0%`). L'overhead scende a `harness_token_overhead_pct: 2.51%` rispetto al precedente `5.75%`. `tasks_builder_v2.json` supera `16/16` task incluso `B2-09` `Ochiai`.
* **Sigilli e Guardie Statiche:** `oracle-lock verify` risulta `VERIFIED` su `376` file (`combined_sha256: f1d2b45a4ed76866774639339b0456b3c922d7f945cfb9e6f6dbbb0101dc8d7e`). `nk_registry_indexer --verify` segna `VALID`. AST Guard in DAST holdout valida `304` file (`276` scripts + `28` tests) con `0` violazioni.

## `[NK-GEN-1.2.0-BUILDER-RSI-EVOLUTION]` (2026-11-22)

* **Milestone e Brief:** `NK-GEN-1.2.0-BUILDER-RSI-EVOLUTION` (`IB-20261121-2A14F2`) potenzia il dominio `DOM-03` tramite promozione atomica `Win32 2PC`.
* **Skill e Profilo Builder:** `NK-Builder-Agent` e le skill `[2]`, `[3]`, `[4]` unificano le modalità operative. Aggiungono shard locali e parità gemella.
* **Pipeline, Rollback e SBFL:** `auto_heal_pipeline` introduce `--diagnose-slice` con calibrazione `pass_tracer`. `healing_snapshot_rollback` aggiunge lo stato `REFACTOR_EQUIVALENT`.
* **Qualità Differenziale e Frontend:** `quality_diff_checker`, `frontend_static_checker` e i re-export simmetrici rafforzano `ast_guard_validator` senza falsi positivi legacy.
* **Mutation Gate e Holdout:** `builder_mutation_gate` elimina `8/8` mutanti (`100.0%`, `0` survived). `holdout_verify` isola i benchmark ciechi in sandbox `NVMe`.
* **Benchmark A/B `v1` e `v2`:** `ab_checks_builder` supera `12/12` task `v1` e `16/16` su `tasks_builder_v2.json`. Registra `100.0%` full/min, varianza `0.0%` e overhead token `5.53%`.
* **AST Guard e Registro:** `ast_guard_validator` (`--target all --quality-diff`) verifica `333` file con `0` violazioni e `0` SAST critical. Il registro segna `VALID` (`5` domini, `11` skill, `39` script, `6` agenti nativi, `0` issues).
* **Convergenza RSI e Oracle Lock:** Il motore RSI segna `CONVERGED_OPTIMAL` (`delta_k: 0`, `fitness_q: 100.0`, `state_hash: 61a371c710ebdac3daad27b253456fbc9b4c0a40d6a1940ba20e7161d9fc080a`). `oracle_lock.json` certifica `404` file `VERIFIED` (`combined_sha256: e33d66b918ecc7c2a7fc5fd2c2270fd7317e013eff5ba3ffd15c399ded3b43db`).
* **Suite Zero-Mock e Copertura:** `test_builder_120_coverage_part1.py` e `test_builder_120_coverage_part2.py` portano la suite a `605/605 PASS` (`100.0%`, `0` failed, `0` skipped, `115.12s`). La copertura raggiunge `statement 94.68%`, `true_branch 89.73%` e `branch 89.32%` e `combined 93.22%`.

## `[NK-MS-20261120-SOVEREIGN-STRESS-DUALMODE-TAS-V2]` (2026-11-20)

* **Milestone e Brief:** `NK-MS-20261120-SOVEREIGN-STRESS-DUALMODE-TAS-V2` (`IB-20261120-06B7E3`, `v6.2.0-PreRelease-RSI`). Certifica l'ecosistema federato prima del rilascio.
* **Stress `S0..S7` e Dual-Mode `M1/M2/M3`:** Supera tutte le fasi `S0..S7` su `M1` standalone, `M2` federato e `M3` slot 3 (`8005`). Il matching `500x2743` scende a `351.5ms` `P95` (`1531.11ms -> 351.5ms`).
* **USL `S3`, Thrash `S4`, Chaos `S5` e Soak `S7`:** Il throughput a `25` concorrenti raggiunge `274.61` RPS (`0` errori USL). `S4` registra `0` leak canary su `192` letture e `30/30` PDF in `173.42ms`. `S5` supera DAST `403`/`400`/`413`/`429` e CB; `S7` chiude con `0` errori sotto budget RSS.
* **Audit Browser E2E `S6` (`1440x900` e `390x844`):** Copre `/platform/login`, `/platform/hub`, `/crm/` e `/bandi/` su `http://127.0.0.1:8000`. Registra `20` toggle tema, NLP `12-13ms`, `0` errori console e `0` HTTP `>= 400`.
* **Suite Cross-Repo `487/487` e Convergenza TAS/CRV:** Certifica `95/95` (`NK-Cloud-Platform`), `128/128` (`NK-Studio-CRM`) e `264/264` (`NK-Bandi`) su NVMe. `rsi_vibe_after.json` conferma `VIBE_STATIC_PASS` (`delta_k: 0`, `sast_critical: 0`) sui tre repository.

## `[NK-GEN-1.1.1-HANDOFF-V2-HARDENING]` (2026-11-19)

* **Milestone e Brief:** `NK-GEN-1.1.1-HANDOFF-V2-HARDENING` (`IB-20261119-73404C`) bonifica `v1.1.0-HANDOFF-V2`. Il rilascio chiude `9` blocker `P0`, `5` difetti `P1` e `2` `P2` dell'audit esterno stratificato.
* **Epistemic Firewall Pure-Stdlib:** `scripts/_internal/nk_common/epistemic_firewall_patterns.py` ed `epistemic_firewall_rules.py` applicano parsing `JSON` strict e whitelist di `35` chiavi `V2`. I filtri scansionano chiavi e valori decodificati e capsule `T12`. Bloccano backslash e userinfo `URL`, rilevano `bearer` case-insensitive e applicano lo split delle clausole proibitive.
* **Bootstrap Fast-Stat (`handoff_verify.py`):** la verifica attiva invalidazione full-tree e contenimento `REPO_OUT_OF_SCOPE`. Il modulo sanitizza `sender_cid`, esegue check tiered `PASSIVE_STANDBY` e blocca `DUPLICATE_REPO_ID`.
* **Isolamento Sessione ed Ecosistema:** il motore isola turno e milestone (`LIVE-1`). Esclude directory non-NK e legge `tests_total` (`LIVE-2`).
* **Router, `2-CID` e Concorrenza:** il flusso gestisce `2-CID` e propaga `--conversation-id` nel router (`C3`, `C4`). Le scritture di stato adottano primitiva atomica `Win32` e lock concorrenti.
* **Suite Zero-Mock e Copertura:** `tests/test_unified_handoff_v2_hardening.py` porta la suite a `544/544` test `PASS` (`+12`). La copertura certificata raggiunge `statement 94.58%`, `true_branch 89.71%` e `combined 93.14%`.

## `[NK-GEN-1.1.0-HANDOFF-V2]` (2026-11-19)

* **Milestone e Brief:** `NK-GEN-1.1.0-HANDOFF-V2` (`IB-20261119-A9C110`) introduce `NKHandoffEngine v2` tramite promozione atomica `Win32 2PC`.
* **Contratti `L0` Strict:** `scripts/schemas/handoff_contracts.py` definisce `NKHandoffManifestV1` e `NKHandoffEnvelopeV2`. `scripts/schemas/nk_ipc_contracts.py` aggiorna `MetaPromptGateContract` (`EXECUTE_HANDOFF_SERIALIZE`) con re-export `handoff_contracts`.
* **Epistemic Firewall (`AP-14..16`):** `scripts/_internal/nk_common/epistemic_firewall_rules.py` opera senza `pydantic`. Implementa `extract_t12_scan_lines`, `scan_fences_strict` e `redact_pii_deterministic`.
* **Serializzatore Ecosistema:** `scripts/nk_session_handoff.py` serializza `PASSIVE_STANDBY` e `ACTIVE_CONTINUATION`. Il pacchetto `_internal/nk_session_handoff/` include `handoff_engine.py`, `ecosystem_scanner.py`, `templates_compiler.py`, `session_state.py`, `context_view.py`, `transcript_cursor.py`, `cli.py` e `constants.py`.
* **Ownership `.staging/`:** `ecosystem_scanner.py` marca ogni artefatto concorrente come `EXTERNAL_CONCURRENT` (`DO_NOT_TOUCH_OR_PROMOTE`), bloccando diff e promozioni improprie.
* **Router L0 Deterministico:** `scripts/vibe_sprint_router.py` e `_internal/vibe_sprint_router/` (`stt_normalize.py`, `envelope_builder.py`, `prompt_linter.py`, `keywords_core.py`) instradano l'handoff su `NK-Scribe-Agent`.
* **Ricezione `1` Step e FastGuard:** `scripts/nk_session_bootstrap.py` (`handoff_verify.py`, `bootstrap.py`, `bootstrap_checks.py`, `transcript_prompt.py`) verifica `HANDOFF_V2` e `T12`. Supportano il flusso `_internal/nk_acs_fastguard/z2_and_l0.py` e `state_rmw.py`.
* **Documentazione e Shard SSOT:** aggiornate le skill `NK-Orchestrator` e `NK-Scribe-Memory`, i protocolli handoff e i moduli `DOM-01` e `DOM-05` (`nk_genome/modules/`).
* **Suite e Convergenza Verificata:** `tests/test_unified_handoff_v2.py` porta la suite a `532` test su `532` su NVMe (`exit_code: 0`). `ast_guard` segna `0/27` in staging con `6/6` sonde `GT-14` in `PASS` (`delta_k: 0`, `fitness_q: 100.0`). `NK-RSI-Auditor` e `NK-Security-DAST-Auditor` emettono `PASS`.

## `[NK-GEN-1.0.3-RSI]` (2026-11-18)

* **Milestone:** `NK-GEN-1.0.3-RSI` isola il mirror NVMe da interferenze `.staging/` dei repository fratelli tramite `Win32 2PC`.
* **Isolamento Sibling:** `isolated_test_runner.py` imposta `overlay_siblings: bool = False` per bloccare overlay `.staging/` di progetti fratelli.
* **Suite Permanente:** la suite completa supera `527` test su `527` in stato `PASS` (`run_id: 51ba4f1f47`).

## `[NK-GEN-1.0.2-RSI]` (2026-11-18)

* **Milestone:** `NK-GEN-1.0.2-RSI` consolida sicurezza mirror NVMe, scansione SAST esplicita e test di regressione tramite `Win32 2PC`.
* **Mirror NVMe Isolato:** `isolated_test_runner.py` include `deploy/`, rileva sibling `NK_External_Projects` e blocca symlink, junction e tombstone root.
* **Scanner SAST:** `sast_scanner.py` risolve i moduli tramite percorso esplicito `NK_Hub/scripts/...` senza ambiguità di directory.
* **Suite Permanente:** la suite completa supera `527` test su `527` in stato `PASS` (`run_id: 174b8eb3ef`).

## `[NK-GEN-1.0.1-RSI]` (2026-11-18)

* **Milestone:** `NK-GEN-1.0.1-RSI` consolida il Lotto 1 tramite promozione atomica `Win32 2PC`.
* **Sicurezza `HookGateV2`:** il modulo `HookGateV2` rafforza i filtri anti-smuggling e anti-spoofing su shell e redazione.
* **Router e Apici Italiani:** `vibe_sprint_router` risolve la scansione degli intenti di scrittura con apici italiani.
* **Mirror NVMe SBFL:** il ponte SBFL esegue la diagnostica dentro un mirror isolato su NVMe locale.
* **Handoff e Scaffolder:** il sistema allinea Template 11 e Template 12 tra handoff e scaffolder.
* **Guardia `gt14_probes.py`:** `gt14_probes.py` blocca false regressioni quando la verifica omette il flag `--strict-verify`.
* **Coerenza Scribe e `AP-2b`:** il profilo Scribe e il linter `AP-2b` allineano i confini operativi.
* **Suite Permanente:** la suite completa supera tutti i `523` test su `523` (`PASS` su NVMe).

## `[v1.0.0-Generation] - 2026-11-17`

* **Milestone:** `NK-GEN-1.0.0` (rilascio inaugurale `NK Hub Generation v1.0.0-Generation`, promozione atomica `Win32 2PC`).
* **Topologia Sovrana:** attiva `11` skill JIT, `6` sub-agenti nativi `GT-14` e la dashboard a `10` nodi `[0]..[9]`.
* **Onboarding e Profili:** supporta `16` trigger di avvio e il profilo nativo `generation` con alias `carbon`.
* **Isolamento Windows e Test Runner:** esegue `pytest` detached su NVMe `%TEMP%` tramite `platform_runner.py --pytest-isolated` (`[RULE-WIN32-ISOLATED-PYTEST]`).
* **Architettura `3-Tier` e Sicurezza:** separa `Dual-Execution GT-14`, confina le scritture in `.staging/` e sigilla `oracle_lock.json`.
* **Baseline e Igiene SSOT:** azzera lo storico pregresso in `quality_baseline.json`, `memory_3tier/`, `active_context.md`, `rsi_telemetry.jsonl` e `session_anchor.jsonl`.

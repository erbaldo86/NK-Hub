# NK Genome: Implementation Plan (`v3.1.0-Tensor-RSI`)

> **Badge di Certificazione:** 🛡️ `[NK-BRIEF-STATUS: AUDITED_AND_CONVERGED 🟢]` | `[RSI-CONVERGENCE: CONVERGED_OPTIMAL (Δ3=0, Q=100.0) 🟢]`  
> **Milestone Anchor ID:** `NK-MS-20261015-TENSOR-RSI-v3.1.0`  
> **Versione Target:** `v3.1.0-Tensor-RSI` (`v3.0.0-STE100-Unified` Compatible)  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, frasi `<= 20` parole)  
> **Modalità Esecutiva:** Protocollo CRV 4.0 in `.staging/` con promozione atomica Win32 2PC (`[RULE-00]`)

---

## 1. Sintesi di Convergenza RSI ($\Delta_3 = 0$, $Q(S_3) = 100.0$)

Questo piano esecutivo unifica i rilievi post-refactoring di `Opus` (`030a38dc`) e `Argon` (`c9fe96c8`) con `7` innovazioni inedite (`EXT-01..EXT-07`).
Il piano integra l'architettura **Tensor-RSI 2D** (`4` livelli verticali `L0..L3` per `5` profili di dominio `RSIProfileRegistry`).
Tutte le modifiche preservano il `100%` di successo sui `100` Golden Tests esistenti e aggiungono `8` nuovi test (`108` totali).

* **Iterazione 1 ($k=1$):** Verifica empirica sul codice reale e sintesi preliminare ($\Delta_1 = 17$, $Q(S_1) = 83.8095$).
* **Iterazione 2 ($k=2$):** Audit avversariale di `NK-RSI-Auditor` su link, guardie `GT-01..GT-14` e soglia `20` parole.
* **Iterazione 3 ($k=3$):** Raffinamento sintattico ASD-STE100 e certificazione finale ($\Delta_3 = 0$, $Q(S_3) = 100.0000$).

---

## 2. Le 14 Guardie Obbligatorie per i Golden Tests (`GT-01..GT-14`)

Ogni Builder deve rispettare le `14` guardie seguenti per mantenere il `100%` di pass rate:

1. **`GT-01` (`scripts/nk_context_sentry.py`):** Mantieni i default `GREEN_STEP_THRESHOLD = 70` e `RED_STEP_THRESHOLD = 100` (`80000 / 120000` token). Preserva le stringhe di warning e attiva `150 / 250` step con `profile="argon"`.
2. **`GT-02` (`scripts/nk_active_runtime_sentinel.py`):** Mantieni le soglie `60 / 85 / 100` in `calculate_state(steps, profile="standard")`. Attiva `120 / 180 / 250` con `profile="argon"`.
3. **`GT-03` (`scripts/nk_compliance_checker.py`):** Mantieni `DDI_DIRECT_STREAK_LIMIT = 12` e la stringa `"Objective DDI violation: {max_consecutive_direct} consecutive direct tools without delegation"`.
4. **`GT-04` (`scripts/nk_swarm_messenger.py` e `scripts/nk_context_sentry.py`):** Mantieni il taglio a `1800` caratteri (MSS) e `SWARM_MSG_HARD_CAP = 2000` (MTU).
5. **`GT-05` (`scripts/memory_3tier_engine.py`):** Mantieni `TIER1_TOKEN_CAP: int = 350` come default e `TIER1_TOKEN_CAP_ARGON: int = 1200` per `argon`.
6. **`GT-06` (`scripts/ast_repo_mapper.py`):** Mantieni i budget `0`, `256` (`mode_c`), `512` (`mode_b`) e `1024` (`mode_a`). Mantieni `512`, `1500` e `4000` per i profili `argon_mode_*`.
7. **`GT-07` (`scripts/sbfl_pytest_bridge.py`):** Garantire `loc.suspiciousness == 1.0`, il formato `"<file>:<line>"` e `len(payload_str) < 320`.
8. **`GT-08` (`.agents/AGENTS.md`, `NK-Master-Hub`, `NK-Session-Controller`, `nk_compliance_checker.py`):** Preserva in `[RULE-00.5]` tutti gli `8` trigger verbali, `"fast-stat"`, `"120"`, `"[0]"`..`"[14]"` e `"10. UNIFIED_ONBOARDING_COMPLIANCE"`.
9. **`GT-09` (`scripts/env_capability_probe.py`):** Mantieni `STANDARD_MODULES_TO_PROBE`, `THIRD_PARTY_MODULES_TO_PROBE` e la formula di `summary["total_probed"]`.
10. **`GT-10` (`scripts/nk_compliance_checker.py`):** Mantieni il default `100` per `operational_score` e `rsi_convergence_score` su transcript privi di errori.
11. **`GT-11` (`scripts/rsi_convergence_engine.py`):** Mantieni `profile="code_rsi"` in `compute_delta()`, `strict_monotonic: bool = False` in `check_hard_gate_regression()` e `verdict="HALTED_CYCLE_DETECTED"`.
12. **`GT-12` (`scripts/rsi_convergence_engine.py`):** Imposta `max_sentence_words: int = 20` insieme allo skip del frontmatter YAML (`---`) e alla bonifica delle `20` frasi in `.agents/`.
13. **`GT-13` (`scripts/quality_baseline_manager.py`):** Supporta sia `check`/`update` posizionali sia i flag `--file`, `--update` e `--check-only`.
14. **`GT-14` (`[RULE-00.1]`):** Non assegnare mai `write_to_file` sulla produzione né `enable_write_tools: true` agli Auditor (`[6]..[11], NK-RSI-Auditor`).

---

## 3. Piano Esecutivo Atomico in 4 Work Package (`WP1..WP4`)

### WP1: Bonifica dei 14 Script Core e Motore Tensor-RSI (`scripts/`)
1. **`ast_guard_validator.py`:** Aggiungi `--stage-dir` come alias di `--target` e rileva nell'AST `eval()`, `exec()`, `pickle.loads()`, `yaml.load()` e `MagicMock`.
2. **`quality_baseline_manager.py`:** Aggiungi `sast_critical_violations` e `rsi_residual_delta` a `LOWER_IS_BETTER_KEYS` (`EXT-01`) e implementa `argparse` retrocompatibile (`GT-13`).
3. **`memory_3tier_engine.py`:** Importa `win32_atomic_replace` da `win32_2pc_engine.py`, aggiungi la CLI `__main__`, persisti `tier1_active_capsule.json` e aggiungi il recall RRF adattivo.
4. **`rsi_convergence_engine.py`:** Imposta `max_sentence_words = 20` con skip YAML `---`, aggiungi `RSIProfileRegistry` (`5` profili), `--vibe-check` (`< 500 ms`) e il CoVe CLI AST Gate.
5. **`auto_heal_pipeline.py`:** Collega `run_pipeline()` a `RSIConvergenceEngine.run_convergence_loop()`, popola `RSIDefectVector` con `ASTGuardValidator` ed elimina lo snapshot finale ridondante.
6. **`safe_cleanup_dev_servers.py` e `async_heartbeat_signaler.py`:** Imposta `_workspace_root` come default in `run_cleanup()` e aggiungi `argparse` a `async_heartbeat_signaler.py`.
7. **`nk_session_bootstrap.py` e `nk_active_runtime_sentinel.py`:** Salva `mtime`/`size` del transcript nella cache del bootstrap; filtra i sub-agenti e leggi `NK_MODEL_PROFILE` nel Sentinel (`EXT-02`).
8. **`nk_compliance_checker.py` e `nk_auto_inning.py`:** Esenta le sessioni `write_calls == 0` dalla penalità AST, leggi `rsi_telemetry.jsonl` (`GT-10`) e imposta fail-closed in `nk_auto_inning.py`.
9. **Altri 6 Script:** Aggiorna `vibe_sprint_router.py`, `win32_2pc_engine.py`, `deterministic_api_cache.py`, `nk_session_handoff.py` (`EXT-03`) e deduplica `nk_ipc_contracts.py`.

### WP2: Allineamento delle 16 Skill, Regolamento e L3 Meta-RSI (`.agents/`)
1. Aggiungi `[RULE-RSI.1]` in `.agents/AGENTS.md` (preservando `v3.0.0-STE100-Unified` e `GT-08`) e sincronizza `saturation_thresholds.yaml`.
2. Correggi i permessi `tools` nelle 16 skill (`GT-14`) e allinea i 4 domini di memoria. Rinomina inoltre il Turno 5 in `Final Handoff`, uniforma i `6 Gate` e aggiungi `<rsi_micro_loop>`.
3. Riscrivi le `20` frasi oltre `20` parole in `.agents/`, rimuovi il trattino in `NK-Master-Hub/SKILL.md:161` e crea `tests/evals/skill_golden_eval_set.json`.

### WP3: Riallineamento Tetralogia Sovrana 4/4, `nk_tracking/` e CI/CD
1. Crea `nk_genome/idea_canvas.md`, correggi le frasi lunghe in `concept_map.md`, aggiorna `structural_tree.md` e rigenera `repo_map.md` a `4.000` token Argon.
2. Ripara le righe `23-25` di `session_anchor.jsonl`, allinea `quality_baseline.json` e rimuovi i file `.bak_*` e i relitti legacy.
3. Aggiorna `.github/workflows/ci.yml` (`100+ Golden Tests`, `--check-only`, `--verify`), `README.md`, `README.it.md` e `PATCH_NOTES.md`.

### WP4: Espansione a 108 Golden Tests, Verifica TAS e Commit 2PC
1. Correggi il test CLI in `test_quality_baseline_manager.py` e il path in `test_ast_repo_mapper.py`.
2. Aggiungi `8` nuovi test reali Zero-Mock per `async_heartbeat_signaler`, `RSIProfileRegistry`, `--vibe-check`, CoVe CLI AST Gate, `LOWER_IS_BETTER_KEYS` e `tier1_active_capsule.json`.
3. Esegui l'audit TAS completo in `.staging/` (`108/108 PASS`, `ast_guard`, `rsi --verify` con $\Delta=0, Q=100.0$) e promuovi atomicamente via `win32_2pc_engine.py`.

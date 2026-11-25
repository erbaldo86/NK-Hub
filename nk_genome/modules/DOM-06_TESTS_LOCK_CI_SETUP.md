# DOM-06: Test Suite, Runner NVMe Isolato e Governance (`v1.0.0-Generation`)

## 1. Perimetro Integrita e Baseline Schema v2 (`DOM-06`)

Il dominio `DOM-06` presidia integrita anti-manomissione, piramide `tests/` Zero-Mock, sharding isolato NVMe e governance CI (`NK-GEN-3.0.2`).
Tutti i conteggi correnti di test, copertura e timing risiedono in [quality_baseline.json](../../nk_tracking/quality_baseline.json) ed [oracle_lock.json](../../nk_tracking/oracle_lock.json).

| ID | Asset Reale (`NK_Hub`) | Percorso Canonico | Funzione Operativa |
| :--- | :--- | :--- | :--- |
| `G-01` | Baseline Ratchet SSOT | [quality_baseline.json](../../nk_tracking/quality_baseline.json) | Schema `v2` con `14` metriche live e `12` `REQUIRED_RATCHET_KEYS` |
| `G-02` | Quadruplo Sigillo SHA-256 | [oracle_lock.json](../../nk_tracking/oracle_lock.json), [oracle_lock_holdout.json](../../nk_tracking/oracle_lock_holdout.json), [governance_lock.json](../../nk_tracking/governance_lock.json), [tensor_rsi_lock.json](../../nk_tracking/tensor_rsi_lock.json) | Protegge `tests/`, `nk_tracking/oracle_holdout/`, `scripts/` e `nk_genome/configs/tensor_rsi/` |
| `G-03` | Piramide Permanente `tests/` | `tests/conftest.py`, `tests/test_*.py` | Marker `fast`/`integration`/`stress`, `test_nk_proget_locale_online_governance.py`, `test_forensic_hardening_fast.py` |
| `G-04` | Eval Set e Holdout Reali | `tests/evals/skill_golden_eval_set.json`, `nk_tracking/oracle_holdout/` | Verifica `11` skill (`retry_caps [0, 0, 0]` `DOM-04`), `tasks_tas_v2.json` e `tas_behavioral_v2.json` |
| `G-05` | Sharding NVMe Parallelo | `scripts/_internal/nk_common/isolated_test_runner.py`, `pytest_parallel.py` | Mirror `%TEMP%` con LPT, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, compat `Locale/` vs `Online/` |
| `G-06` | Workflow CI e Config | `.github/workflows/ci.yml`, `pytest.ini`, `scripts/platform_runner.py` | Matrice cross-OS con `-m fast <= 8.0s`, `<= 28.0s` e floor `88.0% / 82.0%` |

## 2. Architettura Piramide Test e Sharding NVMe

La guardia `[RULE-WIN32-ISOLATED-PYTEST]` vieta ogni esecuzione diretta di `pytest` su Google Drive FS (`G:\`).

1. **Piramide e `[FAST-GUARD]`:** `pytest.ini` separa `fast`, `integration` e `stress`.
   `tests/conftest.py` blocca sottoprocessi e `time.sleep > 0.05s` durante `-m fast`, gestisce `safe_rmtree` ed applica `.deleted_files.json`.
2. **Holdout Reali `TAS v2`:** `tests/test_wave2_holdout_and_pyramid.py` esegue `tasks_tas_v2.json` (`16` task `TAS-01..TAS-16`), `tas_behavioral_v2.json` e il valutatore `k=3`.
3. **Suite Governance & Forense:** `test_nk_proget_locale_online_governance.py` certifica `NK Proget/Locale/` vs `Online/` RO. `test_forensic_hardening_fast.py` valida `NaN/Inf` clamp, bandit `LCB90`, CLI `status`/`abort`/CAS, `hook_gate` e `QBM`.
4. **Potatura Orfani (`.deleted_files.json`):** Rimuove asset e checkpoint di sessione obsoleti (`checkpoint_v1_0_0_generation.json`, brief e sessioni scadute) mantenendo il workspace pulito.
5. **Mirror NVMe, LPT e JUnit Wall-Time:** `isolated_test_runner.py` e `pytest_parallel.py` replicano su `%TEMP%` ignorando `NK Proget/Online/`. `benchmark_runner.py` attiva `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` ed estrae il wall-time dal XML JUnit.
6. **Processi Detached e Lock:** `WIN32_DETACHED_FLAGS` isola i worker da `conhost.exe`, mentre `PIDFileLock` evita deadlock su file condivisi.

## 3. Quality Baseline Manager, Quadruplo Lock e Governance CI

| ID | Modulo Python (`scripts/`) | Funzione Critica |
| :--- | :--- | :--- |
| `Q-01` | `scripts/quality_baseline_manager.py` | Schema `v2` (`14` metriche), ceiling `28.0s`/`8.0s`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `--check-only` RO |
| `Q-02` | `scripts/nk_transcript_tools.py` | Esegue `lint-ste100 --strict`, grounding e verifica quadruplo `oracle-lock` EOL-tollerante |
| `Q-03` | `scripts/preflight_health_check.py` | Controlla allineamento dinamico `nk_common.catalog`, SemVer, baseline e `4` lock |
| `Q-04` | `scripts/nk_registry_indexer.py` | Emette `--verify` sulle `5` aree `DOM-01..05` e `7` shard JSON |

1. **Ratchet Fail-Closed:** `--check-only` vieta scritture; `guards_ratchet.py` rifiuta `pass_rate` booleani, `None` o `NaN`. `--allow-ratchet-down` esige `--reason` esplicito.
2. **Quadruplo Sigillo SHA-256:** `oracle_lock.json` blocca `tests/`, `oracle_lock_holdout.json` blocca `nk_tracking/oracle_holdout/`, `governance_lock.json` blocca `scripts/` e `tensor_rsi_lock.json` blocca `nk_genome/configs/tensor_rsi/`.
3. **Matrice CI (`.github/workflows/ci.yml`):** Verifica `-m fast <= 8.0s`, `-m "not stress" <= 28.0s`, **`combined >= 88.0%`**, **`true_branch >= 82.0%`**, tutti i `4` sigilli e `rsi_convergence_engine.py --verify --strict-verify`.
4. **Riferimenti shard:** [DOM-06.json](../shards/DOM-06.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

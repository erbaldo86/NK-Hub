# TAS Report: Deep Dead-Code Purge, Performance Optimization & GitHub CI Alignment (v5.2.0-RSI)

* **Milestone:** `NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI`
* **Versione Target:** `v5.2.0-STE100-Unified` (`v5.2.0-RSI`)
* **Data Certificazione Analitica:** `2026-11-08`
* **Metodologia:** Triangolazione indipendente multi-agente su `Micro-Step 1.1` (AST Audit), `Micro-Step 1.2` (Redundancy Audit) e `Micro-Step 1.3` (CI Sandbox RCA).

---

## 1. Sintesi Triangolata dei 5 Cluster Operativi (`CP-01..CP-05`)

| Cluster ID | Ambito Tecnico | Evidenza Incrociata (`1.1` + `1.2` + `1.3`) | Azione Correttiva in `.staging/` |
| :--- | :--- | :--- | :--- |
| **`CP-01`** | **Scorie Test Suite e `pytest.ini`** | `pytest.ini` contiene la cartella inesistente `"Programmi di test"`. `tests/conftest.py` espone versione `4.7.0` e helper non utilizzati. `tests/test_core_platform_utilities.py` contiene 5 import inutilizzati, 2 costanti morte, 7 loader duplicati e 8 commenti orfani. Altre scorie presenti in `test_active_sentinel_suite.py`, `test_quality_baseline_manager.py`, `test_win32_2pc.py`, `test_ast_guard_validator.py`, `test_vibe_sprint_router.py`. | Pulizia integrale di import morti, costanti orfane, loader duplicati e commenti residui nei file di test e in `pytest.ini`. |
| **`CP-02`** | **Dead Code e Ridondanze in `scripts/`** | Refuso `' sys'` e import/alias ridondanti in `ast_guard_validator.py`. Ramo `else` identico a `if` in `external_project_scaffolder.py`. Doppio clamp `min()` in `sbfl_pytest_bridge.py`. 4 import `os` locali e doppio `verify()` in `nk_registry_indexer.py`. Alias/metodi morti e 4 ricalcoli `_get_root_mtime()` in `nk_session_bootstrap.py`. Typo `compare_Against_baseline` e doppio `load_baseline()` in `quality_baseline_manager.py`. Regex compilate in loop in `rsi_convergence_engine.py`. | Rimozione scorie interne, unificazione helper SAST, pre-compilazione regex STE100 e caching `_get_root_mtime()` per singola esecuzione. |
| **`CP-03`** | **Ottimizzazione Latenza Suite Pytest** | Il profiling in sandbox (`Micro-Step 1.3`) dimostra che i primi 4 test (`test_dast_sandbox.py` e `test_core_platform_utilities.py`) assorbono `5.72s` su `11.59s` per via di `sleep`/`timeout` lunghi nei sottoprocessi di test. | Riduzione calibrata dei timeout/sleep nei test di watchdog e tree-kill mantenendo processi reali e Mutation Score `100.0%`. |
| **`CP-04`** | **Fix Fallimento GitHub Actions CI (`Run #41`)** | L'API GitHub (`Run #41` `42288408680`) certifica il fallimento su `nk_registry_indexer.py --verify` (`DRIFT_DETECTED`) causato da 5 file con terminatori misti `CRLF`+`LF` che su checkout GitHub (`core.autocrlf false`, `LF` puro) cambiano SHA-256 sia nel registro sia in `oracle_lock.json`. | Normalizzazione `CRLF -> LF` nel calcolo SHA-256 di `nk_registry_indexer.py`, `nk_transcript_tools.py` (`oracle-lock`) e `nk_hook_gate.py`, più normalizzazione `LF` di tutti i file testuali del repo e aggiornamento di `.github/workflows/ci.yml`. |
| **`CP-05`** | **Allineamento GitHub, Patch Notes e Zip Download** | `nk_genome/repo_map.md` è troncato a `67` byte. `.github/README.md`, `GUIDA_INSTALLAZIONE.md` e `00_MAPPA_LIBRERIA_NK.md` riportano ancora `v5.0.0` e `253` test. `NK_Hub_OneClick_Package.zip` contiene la vecchia build `v5.0.0`. | Rigenerazione `repo_map.md`, allineamento globale a `v5.2.0-STE100-Unified` (`93` Golden Tests in `18` moduli, `34` script), sezione Patch Notes di transizione da GitHub `v5.0.0` a `v5.2.0-RSI`, rebuild di `NK_Hub_OneClick_Package.zip` e push verificato su GitHub. |

---

## 2. Tracciabilità Requisiti e Gate di Convergenza

* Ogni modifica al codice viene eseguita in `.staging/` e promossa tramite `scripts/win32_2pc_engine.py`.
* I 6 Gate di convergenza (`G1..G6`) richiedono `93/93` test `PASS`, `0` violazioni SAST/AST, invarianza `CRLF`/`LF` e CI verde.

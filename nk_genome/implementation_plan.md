# Implementation Plan: Clean, Performant & Optimized Checkpoint Release (`v5.2.0-STE100-Unified` / `v5.2.0-RSI`)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢] | [RSI-CONVERGENCE: CONVERGED_OPTIMAL (Δ=0, Q=100.0) 🟢]  
> **Milestone:** `NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI`  
> **Brief ID:** `IB-20261108-60FFD7`  
> **Target Version:** `v5.2.0-STE100-Unified` (`v5.2.0-RSI`)  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, frasi `<= 20` parole)

---

## 1. Obiettivo Architetturale
Consolidare il checkpoint `v5.2.0-STE100-Unified` (`v5.2.0-RSI`) eliminando scorie, dead-code e ridondanze su `34` script e `93` test in `18` moduli.
Risolvere inoltre il fallimento GitHub Actions CI (`Lab NK Hub Continuous Verification`) e aggiornare documentazione, patch notes e pacchetto ZIP.

---

## 2. Work Packages Esecutivi (`Macro-Attività 3`)

### Micro-Step 3.1 (`WP-CLEAN-1`: Pulizia Scorie e Ottimizzazione `scripts/` + `tests/` + `pytest.ini`)
* [pytest.ini](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/pytest.ini): rimuovere `"Programmi di test"` da `norecursedirs`.
* [conftest.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/conftest.py): aggiornare `CONFTEST_VERSION = "5.2.0-STE100-Unified"`.
* [test_core_platform_utilities.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_core_platform_utilities.py): rimuovere import/costanti inutilizzati, commenti orfani e i `7` loader duplicati usando `load_nk_script_module`.
* [test_active_sentinel_suite.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_active_sentinel_suite.py), [test_quality_baseline_manager.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_quality_baseline_manager.py), [test_win32_2pc.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_win32_2pc.py), [test_ast_guard_validator.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_ast_guard_validator.py), [test_vibe_sprint_router.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_vibe_sprint_router.py), [test_dast_sandbox.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/tests/test_dast_sandbox.py): rimuovere asserzioni duplicate, import ridondanti e ottimizzare i timeout dei test.
* [ast_guard_validator.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/ast_guard_validator.py), [external_project_scaffolder.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/external_project_scaffolder.py), [sbfl_pytest_bridge.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/sbfl_pytest_bridge.py), [nk_session_bootstrap.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/nk_session_bootstrap.py), [rsi_convergence_engine.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/rsi_convergence_engine.py), [quality_baseline_manager.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/quality_baseline_manager.py), [win32_2pc_engine.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/win32_2pc_engine.py), [preflight_health_check.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/preflight_health_check.py), [nk_session_handoff.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/nk_session_handoff.py): eliminare dead-code, pre-compilare regex STE100 e memorizzare `_get_root_mtime()`.

### Micro-Step 3.2 (`WP-CLEAN-2`: Invarianza EOL `CRLF`/`LF` e Correzione Workflow GitHub Actions CI)
* [nk_registry_indexer.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/nk_registry_indexer.py): normalizzare `CRLF -> LF` in `_compute_sha256` e aggiornare le costanti di versione a `5.2.0-STE100-Unified`.
* [nk_transcript_tools.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/nk_transcript_tools.py) e [nk_hook_gate.py](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/scripts/nk_hook_gate.py): normalizzare `CRLF -> LF` in `_hash_target_files` (`oracle-lock`) e `_sha256_file` (`integrity`).
* [ci.yml](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/.github/workflows/ci.yml): aggiornare lo step test a `93 Golden Tests in 18 modules, v5.2.0-RSI` con verifiche `--verify` e `oracle-lock verify`.

### Micro-Step 3.3 (`WP-CLEAN-3`: Cold Review, Promozione Win32 2PC, Normalizzazione EOL, Tetralogia e Convergenza RSI)
* Rigenerare [repo_map.md](file:///g:/Il%20mio%20Drive/Antigravity/NK_Hub/nk_genome/repo_map.md) tramite `ast_repo_mapper.py`.
* Aggiornare conteggi (`93` test in `18` moduli, `34` script) e Patch Notes (`v5.0.0 -> v5.2.0-RSI`) su README, guide e Tetralogia.
* Promuovere da `.staging/` con `win32_2pc_engine.py`, normalizzare a `LF` i file testuali e rigenerare `NK_Hub_OneClick_Package.zip`.
* Congelare `oracle_lock.json`, `quality_baseline.json`, `.nk_hook_integrity.json` e `nk_registry_manifest.json`.
* Certificare i 6 Gate con `rsi_convergence_engine.py --verify` (`CONVERGED_OPTIMAL`, $\Delta_k = 0$, $Q = 100.0$) e simulazione CI `LF`.

### Micro-Step 3.4 (`WP-CLEAN-4`: Push GitHub, Aggiornamento Release/Download e Verifica CI Verde)
* Eseguire commit e push su `origin/main` (`https://github.com/erbaldo86/NK-Hub.git`).
* Aggiornare la Release su GitHub e verificare tramite API che `Lab NK Hub Continuous Verification` completi con `success`.

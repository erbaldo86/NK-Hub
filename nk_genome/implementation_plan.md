---
title: "Implementation Plan: NK Hub Generation"
version: "1.0.0-Generation"
tier: "Tier-1"
profile: "generation"
milestone: "NK-GEN-1.0.0"
standard: "ASD-STE100"
---

# `Implementation Plan`: Architettura e Protocollo (`v1.0.0-Generation`)

> **Milestone:** `NK-GEN-1.0.0` (`11` skill, `6` sub-agenti nativi, `10` nodi dashboard).  
> **Ancore SSOT:** [quality_baseline.json](../nk_tracking/quality_baseline.json) e [oracle_lock.json](../nk_tracking/oracle_lock.json).  
> **Profilo Attivo:** `generation` con alias compatibile `carbon` (`160k/185k/205k` token, `120/150/180` step, `1200` tier1).

## 1. Obiettivi Architetturali Non Volatili

1. Garantire topologia Python aciclica (`scc_cycle_count = 0`) con contratti Pydantic `strict=True` in `scripts/schemas/`.
2. Mantenere tutti i sottomoduli in `scripts/_internal/` (incluso `nk_common`) entro `500` LOC per file.
3. Conservare la `Pentad Sovrana 4+1` in `nk_genome/` libera da numeri volatili, delegando i contatori live a [quality_baseline.json](../nk_tracking/quality_baseline.json).
4. Alimentare `nk_common.catalog` e gli shard `DOM-00..06.json` dai frontmatter YAML `SKILL.md` tramite `nk_registry_indexer.py --sync`.
5. Certificare ogni rilascio tramite audit Dual-Execution `GT-14`, DAST reale, test NVMe isolati, promozione `2PC` e sigillo SHA-256.

## 2. Architettura Anti-Crash Windows (`0xC000013A`) e Test Runner NVMe (`%TEMP%`)

La guardia `[RULE-WIN32-ISOLATED-PYTEST]` vieta ogni avvio diretto di `pytest` su Google Drive FS (`G:\`).
Questa architettura previene il crash `0xC000013A` su `conhost.exe` e i lock `[WinError 32]` su file condivisi.

| Componente Reale | Percorso Canonico | Meccanismo Tecnico | Garanzia Operativa |
| :--- | :--- | :--- | :--- |
| `isolated_test_runner.py` | `scripts/_internal/nk_common/` | `mirror_workspace_to_nvme()`, `run_detached_pytest()` | Clona `NK_Hub` su NVMe `%TEMP%` con overlay `.staging/` |
| `platform_runner.py` | `scripts/platform_runner.py` | Flag `--pytest-isolated` e `--overlay-staging` | Entry point unico CLI con output JSON atomico |
| `WIN32_DETACHED_FLAGS` | `isolated_test_runner.py` | Flag Win32 detached (`0x00000200`, `0x08000000`) | Isola i processi figli da `conhost.exe` |
| `Pytest Zero-Cache` | `run_detached_pytest()` | Flag `-p no:cacheprovider`, `--import-mode=importlib` | Azzera cache su Drive FS ed elimina conflitti import |
| `PIDFileLock` | `scripts/_internal/nk_common/ledger_lock_io.py` | `PIDFileLock(acquire_timeout_sec)` e `OpenProcess` | Previene deadlock cooperativi con recupero lock stantii |

Flusso permanente del test runner isolato su Windows:
1. `mirror_workspace_to_nvme()` replica `scripts/`, `tests/`, `.agents/`, `nk_genome/` e `.staging/` in `%TEMP%` applicando `.deleted_files.json`.
2. `_sync_staging_tests_for_pytest()` allinea `.staging/tests` nel mirror evitando errori `ImportPathMismatch`.
3. `run_detached_pytest()` usa `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` con `--basetemp` e tree-kill sicuro su timeout.
4. Il runner salva il verdetto atomico in `%TEMP%/nk_diagnostics/pytest_iso_last.json` e rimuove il mirror temporaneo nel blocco `finally`.

## 3. Protocollo di Esecuzione e Verifica (`NK-GEN-1.0.0`)

1. **Staging Isolato (`[RULE-00]`):** ogni modifica a `.py`, `.md` e `.json` nasce esclusivamente dentro `.staging/`.
2. **Validazione Statica e Pytest Isolato:** esegui `scripts/ast_guard_validator.py --stage-dir` e `scripts/platform_runner.py --pytest-isolated --overlay-staging`.
3. **Audit Unificato `GT-14`:** `scripts/rsi_convergence_engine.py --emit-gt14-bundle --with-dast` verifica STE100, link, CoVe CLI e DAST.
4. **Promozione Atomica `2PC`:** `scripts/win32_2pc_engine.py --promote-staging` promuove gli artefatti sotto `Win32NamedMutex` e `PIDFileLock(acquire_timeout_sec)`.
5. **Chiusura `NK-Scribe-Memory`:** `NK-Scribe-Agent` aggiorna [SKILL_INDEX.md](SKILL_INDEX.md), [repo_map.md](repo_map.md), [PATCH_NOTES.md](PATCH_NOTES.md) e il sigillo finale.

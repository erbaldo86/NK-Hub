---
title: "Structural Tree: NK Hub Generation"
version: "1.0.0-Generation"
tier: "Tier-1"
profile: "generation"
standard: "ASD-STE100"
---

# `Structural Tree`: Topologia `3-Tier` e Moduli (`v1.0.0-Generation`)

## 1. Perimetro Strutturale `NK_Hub`

Il sistema separa `.agents/`, `nk_genome/` e `scripts/`.
I contatori live di suite e coperture (`combined >= 88.0%`, `true_branch >= 82.0%` in CI) risiedono in [quality_baseline.json](../nk_tracking/quality_baseline.json).

| ID | Cartella Canonica | Ruolo Strutturale | Riferimento |
| :--- | :--- | :--- | :--- |
| DIR-01 | `Antigravity/.agents/` | Bridge zero-discovery verso `NK_Hub` | `AGENTS.md`, `plugins.json`, `skills.json` |
| DIR-02 | `NK_Hub/.agents/` | Costituzione, `11` skill JIT, `6` agenti, `nk-gate` | `AGENTS.md`, `plugins/nk-gate/hooks.json` |
| DIR-03 | `NK_Hub/nk_genome/` | Genoma `3-Tier`: indice, `Pentad 4+1`, `shards/` | `00_GENOME_INDEX.md`, `nk_registry_manifest.json` |
| DIR-04 | `NK_Hub/nk_genome/modules/` | `8` moduli `DOM-00..06` e grafi `DAG/DSM/RTM` | `SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md` |
| DIR-05 | `NK_Hub/scripts/` | Facciate CLI, `_internal/` (`<= 500` LOC), `5` `schemas/` | `tensor_rsi.py`, `schemas/`, `_internal/` |
| DIR-06 | `NK_Hub/tests/` | Piramide Zero-Mock (`fast <= 8.0s`, `<= 28.0s`) NVMe | `tests/conftest.py`, `isolated_test_runner.py` |
| DIR-07 | `NK_Hub/nk_tracking/` | Telemetria RSI, baseline `v2`, `4` lock e holdout | `quality_baseline.json`, `tensor_rsi_lock.json` |
| DIR-08 | `NK_Hub/.staging/` | Area isolata per mutazioni atomiche `2PC` | `scripts/win32_2pc_engine.py` |
| DIR-09 | `NK_Hub/nk_docs_and_setup/` | Guide utente, workspace e installer `7` profili | `00_MAPPA_LIBRERIA_NK.md`, `README.md` |

## 2. Albero Canonico Multi-Radice (`v1.0.0-Generation`)

```text
Root Padre (es. Il mio Drive/)
+-- NK Proget/
|   +-- Locale/<Nome>/ [App utente sviluppate in .staging/ + 2PC]
|   +-- Online/<Nome>/ [Mirror rilascio RO bloccato da hook e 2PC]
+-- Antigravity/
    +-- .agents/ [AGENTS.md, plugins.json, skills.json]
    +-- NK_External_Projects/<Nome>/ [Percorso compatibile legacy]
    +-- NK_Hub/ [NK Hub Generation v1.0.0-Generation]
        +-- .agents/ [AGENTS.md, rules/, 6 agents/, 11 skills/, plugins/nk-gate/]
        +-- nk_genome/ [00_GENOME_INDEX.md, Pentad 4+1, PATCH_NOTES.md, configs/, shards/, modules/]
        +-- scripts/
        |   +-- schemas/ [5 foglie L0 strict + __init__.py]
        |   +-- _internal/ [Sottopacchetti aciclici <= 500 LOC]
        |   +-- [Facciate CLI top-level inclusa tensor_rsi.py]
        +-- tests/ [conftest.py, evals/, stress/, test_*.py]
        +-- nk_tracking/
            +-- quality_baseline.json, oracle_lock.json, oracle_lock_holdout.json
            +-- governance_lock.json, tensor_rsi_lock.json, tensor_sessions/
            +-- oracle_holdout/, memory_3tier/, anchor/, manifests/, sessions/
```

## 3. Regole di Igiene Workspace

1. **Separazione App:** Le nuove app risiedono in `NK Proget/Locale/<Nome>/` (`compat NK_External_Projects/`). `NK Proget/Online/` resta in sola lettura.
2. **Runner NVMe Isolato:** Ogni esecuzione `pytest` usa `--pytest-isolated` su `%TEMP%` con `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` e sharding LPT.
3. **Topologia e Quadruplo Lock:** `scripts/schemas/` funge da foglia aciclica `L0`. I `4` sigilli bloccano `tests/`, `oracle_holdout/`, `scripts/` e `configs/tensor_rsi/`.
4. **Ritiro Atomico:** Le rimozioni usano `.deleted_files.json` su mirror NVMe e `Win32 2PC`.
   Le verifiche live aggiornano [oracle_lock.json](../nk_tracking/oracle_lock.json).

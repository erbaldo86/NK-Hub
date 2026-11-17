---
title: "Structural Tree: NK Hub Generation"
version: "1.0.0-Generation"
tier: "Tier-1"
profile: "generation"
standard: "ASD-STE100"
---

# `Structural Tree`: Topologia `3-Tier` e Moduli (`v1.0.0-Generation`)

## 1. Perimetro Strutturale `NK_Hub`

Il sistema separa `.agents/`, il Genoma `3-Tier` in `nk_genome/` e i moduli `scripts/`.
I contatori live (`11` skill, `6` sub-agenti nativi, `10` nodi dashboard, test e coverage) risiedono in [quality_baseline.json](../nk_tracking/quality_baseline.json).

| ID | Cartella Canonica | Ruolo Strutturale | Riferimento |
| :--- | :--- | :--- | :--- |
| DIR-01 | `Antigravity/.agents/` | Bridge zero-discovery verso `NK_Hub` | `AGENTS.md`, `plugins.json`, `skills.json` |
| DIR-02 | `NK_Hub/.agents/` | Costituzione, `11` skill JIT, `6` agenti, `nk-gate` | `AGENTS.md`, `plugins/nk-gate/hooks.json` |
| DIR-03 | `NK_Hub/nk_genome/` | Genoma `3-Tier`: indice, `Pentad Sovrana 4+1`, `shards/` | `00_GENOME_INDEX.md`, `nk_registry_manifest.json` |
| DIR-04 | `NK_Hub/nk_genome/modules/` | `8` shard `DOM-00..06` e grafi `DAG/DSM/RTM` | `SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md` |
| DIR-05 | `NK_Hub/scripts/` | Facciate CLI, `_internal/` e `schemas/` `<= 500` LOC | `scripts/schemas/`, `scripts/_internal/` |
| DIR-06 | `NK_Hub/tests/` | Suite verifica Zero-Mock isolata su NVMe `%TEMP%` | `tests/conftest.py`, `isolated_test_runner.py` |
| DIR-07 | `NK_Hub/nk_tracking/` | Telemetria RSI, ancore, baseline e lock | `quality_baseline.json`, `oracle_lock.json` |
| DIR-08 | `NK_Hub/.staging/` | Area isolata per mutazioni atomiche `2PC` | `scripts/win32_2pc_engine.py` |
| DIR-09 | `NK_Hub/nk_docs_and_setup/` | Documentazione utente e installer OS | `00_MAPPA_LIBRERIA_NK.md`, `README.md` |

## 2. Albero Canonico `NK_Hub` (`v1.0.0-Generation`)

```text
Antigravity/
+-- .agents/ [AGENTS.md, plugins.json, skills.json]
+-- NK_External_Projects/<Nome>/ [Progetti app utente isolati]
+-- NK_Hub/ [NK Hub Generation 1.0.0-Generation]
    +-- .agents/
    |   +-- AGENTS.md, plugins.json, skills.json
    |   +-- rules/anti_crash_rules.md [Regole Windows I/O e SAST]
    |   +-- agents/<6_foglie>/agent.md [enable_subagent_tools: false]
    |   +-- skills/<11_skill>/SKILL.md [JIT <= 1.200 tok per shard]
    |   +-- plugins/nk-gate/ [hooks.json -S -B -u, plugin.json, agents/, rules/AGENTS.md]
    +-- nk_genome/
    |   +-- 00_GENOME_INDEX.md [Tier-0 <= 950 tok]
    |   +-- idea_canvas.md, concept_map.md, structural_tree.md, implementation_plan.md, repo_map.md
    |   +-- configs/saturation_thresholds.json [SSOT soglie ACS generation/carbon]
    |   +-- PATCH_NOTES.md [Changelog prepend-only STE100]
    |   +-- nk_registry_manifest.json [Facciata <= 800 tok]
    |   +-- SKILL_INDEX.md [Facciata <= 800 tok]
    |   +-- shards/DOM-00..06.json [Shard JSON <= 1.200 tok]
    |   +-- modules/ [DOM-00..06 e SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md]
    +-- scripts/
    |   +-- schemas/ [__init__.py, dual_ledgers.py, nk_catalog_contracts.py, nk_ipc_contracts.py]
    |   +-- _internal/nk_common/ [isolated_test_runner.py, ledger_lock_io.py, catalog.py, thresholds.py]
    |   +-- _internal/<pacchetti_interni>/*.py [Sottomoduli <= 500 LOC]
    |   +-- <facciate_cli>.py [Facciate CLI compatibili]
    +-- tests/ [conftest.py e suite test_*.py]
    +-- nk_tracking/
        +-- quality_baseline.json, oracle_lock.json, rsi_telemetry.jsonl
        +-- sessions/<conversation_id>/ [Handoff e anchor isolati]
```

## 3. Regole di Igiene Workspace

1. **Separazione App:** i progetti applicativi restano sempre sotto `../NK_External_Projects/<Nome>/`.
2. **Zero File Residui:** ogni esecuzione `pytest` usa `--pytest-isolated` su NVMe `%TEMP%` evitando cache in `Antigravity/`.
3. **Topologia Aciclica:** `scripts/schemas/` funge da nodo foglia `L0` privo di import ascendenti verso i motori superiori.

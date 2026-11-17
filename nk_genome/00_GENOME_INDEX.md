---
title: "Genome Index O(1) Tier-0"
version: "1.0.0-Generation"
tier: "Tier-0"
standard: "ASD-STE100"
---

# `00_GENOME_INDEX`: Router `O(1)` Tier-0 (`v1.0.0-Generation`)

Questo indice guida il caricamento progressivo entro `950` token al Turno `0`.

## 1. Mappa Genoma (`nk_genome/`)

| ID | Tier | Artefatto Target | Ambito | Budget |
| --- | --- | --- | --- | --- |
| GN-00 | T0 | `00_GENOME_INDEX.md` | Router `O(1)` | `<= 950` tok |
| GN-01 | T1 | [idea_canvas.md](idea_canvas.md) | Visione `Generation` e requisiti EARS | `<= 1.100` tok |
| GN-02 | T1 | [concept_map.md](concept_map.md) | Architettura C4 `2-Tier`, `GT-14` e `2PC` | `<= 1.100` tok |
| GN-03 | T1 | [structural_tree.md](structural_tree.md) | Topologia modulare e architettura `3-Tier` | `<= 1.100` tok |
| GN-04 | T1 | [implementation_plan.md](implementation_plan.md) | Piano `NK Hub Generation` e runner NVMe | `<= 1.100` tok |
| GN-05 | T1 | [repo_map.md](repo_map.md) | Snapshot AST completo | `<= 1.100` tok |
| GN-06 | T0 | [nk_registry_manifest.json](nk_registry_manifest.json) | Facciata JSON per `shards/` | `<= 800` tok |
| GN-07 | T0 | [SKILL_INDEX.md](SKILL_INDEX.md) | Registro `11` skill `DOM-01..05` | `<= 800` tok |

## 2. Shard Modulari (`Tier-2`, `1` per Task)

* [DOM-00](modules/DOM-00_BRIDGE_HOOKS_PLUGIN.md): Bridge root, `hooks.json`, shortcut e plugin `nk-gate`.
* [DOM-01](modules/DOM-01_GOV_ROUTING_2PC_ACS.md): Routing `Single-Gate`, `16` shortcut, `Win32 2PC` e `ACS`.
* [DOM-02](modules/DOM-02_SPEC_ARCH_GT14.md): Specifiche `GT-14`, `Pentad Sovrana 4+1`, `ast_repo_mapper.py` e scaffolder.
* [DOM-03](modules/DOM-03_BUILD_HEAL_FORGE.md): Build `.staging/`, healing e `platform_runner.py`.
* [DOM-04](modules/DOM-04_AUDIT_DAST_RSI_ORACLE.md): Audit SAST, DAST, SBFL, Oracolo e RSI.
* [DOM-05](modules/DOM-05_MEMORY_SCRIBE_SSOT.md): Memoria `3-Tier`, `Scribe` e SSOT.
* [DOM-06](modules/DOM-06_TESTS_LOCK_CI_SETUP.md): Test Zero-Mock, runner NVMe isolato e governance CI.
* [Graphs](modules/SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md): Grafo `DAG`, `DSM`, matrice `RTM` e heatmap.

## 3. Shard Dati (`shards/`) e Runtime

* [DOM-00.json](shards/DOM-00.json): Bridge root, `hooks.json` e igiene plugin.
* [DOM-01.json](shards/DOM-01.json) .. [DOM-05.json](shards/DOM-05.json): `11` skill, script, CLI, classi e intent `DOM-01..05`.
* [DOM-06.json](shards/DOM-06.json): Suite `tests/` e puntatori verifica.
* [quality_baseline.json](../nk_tracking/quality_baseline.json): Sorgente unica per metriche test e timing live.
* [oracle_lock.json](../nk_tracking/oracle_lock.json): Sigillo SHA-256 sui file protetti.

## 4. Caricamento Lazy Generation (`3-Tier`)

1. Leggi solo `00_GENOME_INDEX.md` prima di instradare il task.
2. Apri un solo file della `Pentad Sovrana 4+1` `Tier-1` e un solo shard `Tier-2`.
3. Interroga il registro via `nk_registry_indexer.py --lookup` e leggi `_internal/` sotto `800` righe.

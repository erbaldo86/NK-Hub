---
title: "NK Genome: Skill Index O(1)"
version: "1.0.0-Generation"
release_version: "1.0.0-Generation"
rsi_profile: "ste100_rsi"
---

# Indice Skill O(1) (`SKILL_INDEX.md`)

Manifesto `1.0.0-Generation` sharded su `7` domini, `11` skill e `37` script.

## 1. Domini Funzionali (`DOM-01..DOM-05`)

| ID | Nome | Skill Primaria | Skill | Script | Shard |
| --- | --- | --- | --- | --- | --- |
| DOM-01 | GOV_AND_ROUTING | NK-Orchestrator | 1 | 12 | `shards/DOM-01.json` |
| DOM-02 | IDEATION_AND_ARCH | NK-Ideator | 2 | 3 | `shards/DOM-02.json` |
| DOM-03 | BUILD_AND_HEAL | NK-Python-Async-Builder | 3 | 7 | `shards/DOM-03.json` |
| DOM-04 | AUDIT_DAST_AND_RCA | NK-Security-Auditor | 4 | 7 | `shards/DOM-04.json` |
| DOM-05 | MEMORY_TELEMETRY_AND_DOCS | NK-Scribe-Memory | 1 | 8 | `shards/DOM-05.json` |

## 2. Skill Canoniche

| Skill | Dominio | Sub-Agente | Livello | SHA-256 |
| --- | --- | --- | --- | --- |
| NK-Agent-Instruction-Forge | DOM-03 | NK-Builder-Agent | HIGH | 407a6c94 |
| NK-Bug-Diagnostic-Engine | DOM-04 | NK-Security-DAST-Auditor | HIGH | 3c2a7888 |
| NK-Delta-Architect | DOM-03 | NK-Builder-Agent | HIGH | 830c7188 |
| NK-Dynamic-Sandbox-StressTester | DOM-04 | NK-Security-DAST-Auditor | HIGH | 99e4e383 |
| NK-Ideator | DOM-02 | NK-Arch-Specifier | HIGH | b845ef5f |
| NK-Oracle-Evaluator | DOM-04 | NK-RSI-Auditor | HIGH | 19973b1d |
| NK-Orchestrator | DOM-01 | Orchestrator-Direct | HIGH | 94fa85bb |
| NK-Python-Async-Builder | DOM-03 | NK-Builder-Agent | HIGH | 24130ad1 |
| NK-Scribe-Memory | DOM-05 | NK-Scribe-Agent | HIGH | 0753ad6c |
| NK-Security-Auditor | DOM-04 | NK-Security-DAST-Auditor | HIGH | 8982be4a |
| NK-System-Architect | DOM-02 | NK-Specifier-Agent | HIGH | 74b0356e |

## 3. Script, Igiene e Lookup

Igiene globale: `1` skill esterne attive su `12` totali.
Dettagli CLI e SHA script risiedono in `shards/DOM-00.json`..`DOM-06.json`.
Usa `nk_registry_indexer.py --lookup DOM-01` o `--verify` per controllo O(1).

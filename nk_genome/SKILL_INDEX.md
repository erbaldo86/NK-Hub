---
title: "NK Genome: Skill Index O(1)"
version: "1.0.0-Generation"
release_version: "1.0.0-Generation"
rsi_profile: "ste100_rsi"
---

# Indice Skill O(1) (`SKILL_INDEX.md`)

Manifesto `1.0.0-Generation` con `5` domini (`7` shard), `11` skill e `34` script.

## 1. Domini Funzionali (`DOM-01..DOM-05`)

| ID | Nome | Skill Primaria | Skill | Script | Shard |
| --- | --- | --- | --- | --- | --- |
| DOM-01 | GOV_AND_ROUTING | NK-Orchestrator | 1 | 12 | `shards/DOM-01.json` |
| DOM-02 | IDEATION_AND_ARCH | NK-Ideator | 2 | 3 | `shards/DOM-02.json` |
| DOM-03 | BUILD_AND_HEAL | NK-Python-Async-Builder | 3 | 7 | `shards/DOM-03.json` |
| DOM-04 | AUDIT_DAST_AND_RCA | NK-Security-Auditor | 4 | 6 | `shards/DOM-04.json` |
| DOM-05 | MEMORY_TELEMETRY_AND_DOCS | NK-Scribe-Memory | 1 | 6 | `shards/DOM-05.json` |

## 2. Skill Canoniche

| Skill | Dominio | Sub-Agente | Livello | SHA-256 |
| --- | --- | --- | --- | --- |
| NK-Agent-Instruction-Forge | DOM-03 | NK-Builder-Agent | HIGH | 8aa3c7ce |
| NK-Bug-Diagnostic-Engine | DOM-04 | NK-Security-DAST-Auditor | HIGH | 3b0d6798 |
| NK-Delta-Architect | DOM-03 | NK-Builder-Agent | HIGH | 8f967456 |
| NK-Dynamic-Sandbox-StressTester | DOM-04 | NK-Security-DAST-Auditor | HIGH | 9368c5d8 |
| NK-Ideator | DOM-02 | NK-Arch-Specifier | HIGH | 9ff97286 |
| NK-Oracle-Evaluator | DOM-04 | NK-RSI-Auditor | HIGH | d880a945 |
| NK-Orchestrator | DOM-01 | Orchestrator-Direct | HIGH | 87158000 |
| NK-Python-Async-Builder | DOM-03 | NK-Builder-Agent | HIGH | 2a1b75a8 |
| NK-Scribe-Memory | DOM-05 | NK-Scribe-Agent | HIGH | 662b83e1 |
| NK-Security-Auditor | DOM-04 | NK-Security-DAST-Auditor | HIGH | 0ae10a1d |
| NK-System-Architect | DOM-02 | NK-Specifier-Agent | HIGH | 9a73cdd2 |

## 3. Script, Igiene e Lookup

Igiene globale: `33` skill esterne attive su `44` totali.
Dettagli CLI e SHA script risiedono in `shards/DOM-00.json`..`DOM-06.json`.
Usa `nk_registry_indexer.py --lookup DOM-01` o `--verify` per controllo O(1).

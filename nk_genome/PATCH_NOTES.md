---
title: "NK Genome: Registro Ufficiale Patch Notes"
version: "1.0.0-Generation"
milestone_anchor_id: "NK-GEN-1.0.0"
rsi_profile: "ste100_rsi"
---

# Registro Ufficiale Patch Notes (`NK_Hub`)

> **Politica SSOT:** Registro append-in-testa (`prepend-only`) certificato post-commit `Win32 2PC` a $\Delta_k = 0$.  
> **Standard:** Italiano Tecnico ASD-STE100 (`[RULE-STE100]`, frasi attive `<= 20` parole).

---

## `[v1.0.0-Generation] - 2026-11-17`

* **Milestone:** `NK-GEN-1.0.0` (rilascio inaugurale `NK Hub Generation v1.0.0-Generation`, promozione atomica `Win32 2PC`).
* **Topologia Sovrana:** attiva `11` skill JIT, `6` sub-agenti nativi `GT-14` e la dashboard a `10` nodi `[0]..[9]`.
* **Onboarding e Profili:** supporta `16` trigger di avvio e il profilo nativo `generation` con alias `carbon`.
* **Isolamento Windows e Test Runner:** esegue `pytest` detached su NVMe `%TEMP%` tramite `platform_runner.py --pytest-isolated` (`[RULE-WIN32-ISOLATED-PYTEST]`).
* **Architettura `3-Tier` e Sicurezza:** separa `Dual-Execution GT-14`, confina le scritture in `.staging/` e sigilla `oracle_lock.json`.
* **Baseline e Igiene SSOT:** azzera lo storico pregresso in `quality_baseline.json`, `memory_3tier/`, `active_context.md`, `rsi_telemetry.jsonl` e `session_anchor.jsonl`.

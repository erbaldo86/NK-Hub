---
title: "Matrice di Accoppiamento e Disordine: Audit Baseline Pre-Ristrutturazione v3.5.0"
version: "3.5.0"
milestone_anchor_id: "NK-MS-20261017-MODULAR-INDEX-v3.5.0"
status: "COMPLETED"
---

# 🔬 Fase 1: Matrice di Accoppiamento e Baseline Pre-Ristrutturazione (`v3.5.0`)

> **Milestone Anchor ID:** `NK-MS-20261017-MODULAR-INDEX-v3.5.0`  
> **Sorgente Telemetrica:** `%TEMP%\nk_diagnostics\nk_modularity_scan_baseline_pre_v350.json`  
> **Punteggio Iniziale Modularità e Indicizzazione:** `50.0 / 100.0`

---

## 1. Metriche Quantitative Pre-Ristrutturazione (`Baseline Pre-v3.5.0`)

Lo scanner AST ha misurato lo stato iniziale dell'ambiente `NK-Hub` in `902.17 ms`.

| Metrica Misurata | Valore Baseline (`Pre-v3.5.0`) | Target Post-Ristrutturazione (`v3.5.0`) |
| :--- | :---: | :---: |
| **Skill `NK-*` con Metadati di Dominio (`domain_id`, `sector`)** | `0 / 16` (`0.0%`) | `16 / 16` (`100.0%`) |
| **Manifesto SSOT `O(1)` (`nk_genome/nk_registry_manifest.json`)** | `Assente` (`false`) | `Presente` (`5` Domini, `16` Skill, `31+` Script) |
| **Indice Rapido Markdown (`nk_genome/SKILL_INDEX.md`)** | `Assente` (`false`) | `Presente` (`< 350` token, `CONVERGED_OPTIMAL`) |
| **Accoppiamenti Hardcoded ("Shotgun Surgery" negli Script)** | `2` script cablati (`preflight`, `vibe_sprint_router`) | `0` script cablati senza SSOT (`100%` collegati al Manifesto) |
| **Stato Schema `.agents/hooks.json`** | `LEGACY_WRAPPER_ONLY` | `DUAL_COMPATIBLE_NATIVE_AND_NK` |
| **Skill Globali Esterne (`~/.gemini/config/`)** | `61` skill (`28.170` byte frontmatter, `~7.042` token/turno) | Censite e profilate nel Manifesto di Igiene Globale |
| **Modularity & Indexing Score Complessivo** | **`50.0 / 100.0`** | **`100.0 / 100.0`** |

---

## 2. Mappa dei Punti di Accoppiamento ("Shotgun Surgery") Identificati

1. **`scripts/preflight_health_check.py`:** Verifica il numero di skill cablando `skills_audited == 16` invece di interrogare il manifesto SSOT.
2. **`scripts/vibe_sprint_router.py`:** Risolve il routing in modo statico senza restituire il dominio funzionale (`DOM-01..DOM-05`) dal registro centrale.
3. **`.agents/skills/*/SKILL.md`:** Le `16` skill risiedono in una lista piatta senza dichiarare il proprio settore nel frontmatter YAML.
4. **`.agents/hooks.json`:** Usa solo il contenitore legacy `"hooks"` senza esporre gli eventi al livello radice per Antigravity 2.0.

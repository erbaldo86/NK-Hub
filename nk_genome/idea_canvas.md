---
title: "Idea Canvas: NK Hub Generation"
version: "1.0.0-Generation"
tier: "Tier-1"
profile: "generation"
standard: "ASD-STE100"
---

# `Idea Canvas`: Visione e Requisiti EARS (`v1.0.0-Generation`)

## 1. Identita, Problema e Visione `Generation-Native`

`NK Hub Generation` attua un sistema multi-agente deterministico per Windows e Drive FS.
Il profilo `generation` con alias `carbon` estende il contesto operativo senza saturazione (`neon`, `pro`, `flash`, `argon`, `standard`).
Il modello `3-Tier` elimina il carico monolitico al Turno `0` e preserva i moduli Python.
La `Pentad Sovrana 4+1` separa i pilastri concettuali stabili (`Why`) dalla topologia `AST` (`What`).
I contatori live di skill, sub-agenti e baseline risiedono in [quality_baseline.json](../nk_tracking/quality_baseline.json).

## 2. Pilastri Ingegneristici Invarianti

| ID | Pilastro | Meccanismo Principale | Modulo Attuatore | Vincolo Chiave |
| :--- | :--- | :--- | :--- | :--- |
| `PIL-01` | Confinamento I/O | Scritture in `.staging/` e promozione atomica | `scripts/win32_2pc_engine.py` | Named Mutex (`[RULE-00]`) |
| `PIL-02` | Topologia `2-Tier` | Unico Hub `DOM-01` e `6` foglie | `scripts/vibe_sprint_router.py` | Zero sub-orchestratori |
| `PIL-03` | Isolamento App | App in `NK Proget/Locale/`, blocco `Online/` | `scripts/external_project_scaffolder.py` | Compat `NK_External_Projects/` |
| `PIL-04` | Processi e Pytest | Runner UTF-8 detached su NVMe `%TEMP%` | `scripts/platform_runner.py` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` |
| `PIL-05` | Onesta Epistemica | `4` lock SHA-256 e `report-conflict` | `scripts/nk_transcript_tools.py` | Evidenza reale verificabile |

## 3. Requisiti EARS Non Volatili (`v1.0.0-Generation`)

* **R1:** `IL SISTEMA DEVE` esporre al Turno `0` un solo indice `Tier-0` entro `950` token stimati.
* **R2:** `IL SISTEMA DEVE` mantenere `idea_canvas.md`, `concept_map.md` e `structural_tree.md` entro `1.100` token.
* **R3:** `QUANDO` gli hook girano sotto `python -S`, `IL SISTEMA DEVE` leggere `saturation_thresholds.json` via `json` stdlib.
* **R4:** `MENTRE` opera `generation` o `carbon`, `IL SISTEMA DEVE` applicare soglie ACS `160k/185k/205k` token e `120/150/180` step.
* **R5:** `QUANDO` sessioni parallele usano Drive FS, `IL SISTEMA DEVE` isolare lo stato in `nk_tracking/sessions/<conversation_id>/`.
* **R6:** `QUANDO` esegue `pytest` su Windows, `IL SISTEMA DEVE` isolare il mirror su NVMe via `--pytest-isolated`.
* **R7:** `SE` uno script usa path temp non espansi, `IL SISTEMA DEVE` bloccarlo con `[RULE-NO-LITERAL-ENV-PATH]`.
* **R8:** `QUANDO` riceve un prompt `Mode D`, `IL SISTEMA DEVE` attivare `Single-Gate` senza conferme doppie.
* **R9:** `IL SISTEMA DEVE` separare `NK-Arch-Specifier` read-only `GT-14` dal writer confinato `NK-Specifier-Agent`.
* **R10:** `IL SISTEMA DEVE` garantire grafo Python aciclico (`C_k = 0`), zero classi duplicate e file `<= 500` LOC.
* **R11:** `IL SISTEMA DEVE` coordinare `Tensor-RSI` via `scripts/tensor_rsi.py` e impedire scritture su `NK Proget/Online/`.

## 4. Target Architetturali `SSOT` (`Non Volatili`)

| ID | Ambito Target | Specifica `v1.0.0-Generation` | Verifica Deterministica |
| :--- | :--- | :--- | :--- |
| `SLA-01` | Budget Contesto | `Tier-0 <= 950`, `Tier-1 <= 1.100`, memory `tier1 <= 1.200` tok | `scripts/ast_repo_mapper.py` |
| `SLA-02` | Topologia Moduli | Zero cicli Tarjan (`C_k = 0`) e file `<= 500` LOC | `scripts/ast_guard_validator.py` |
| `SLA-03` | Piramide CI | `-m fast <= 8.0s`, `tier 1+2 <= 28.0s`, floor `88.0% / 82.0%` | `scripts/quality_baseline_manager.py` |
| `SLA-04` | Quadruplo Sigillo | `oracle_lock.json`, holdout, governance e [tensor_rsi_lock.json](../nk_tracking/tensor_rsi_lock.json) | `scripts/nk_transcript_tools.py` |
| `SLA-05` | Convergenza RSI | Stato `Delta_k = 0` con `G_hard == 1` e `Q_v2 == 100.0` | `scripts/rsi_convergence_engine.py` |

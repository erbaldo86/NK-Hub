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
Il profilo `generation` con alias `carbon` estende il contesto operativo senza errori di saturazione.
Il modello `3-Tier` elimina il carico monolitico al Turno `0` e preserva i moduli Python.
La `Pentad Sovrana 4+1` separa i pilastri concettuali stabili (`Why`) dalla topologia `AST` (`What`).
I contatori live di `11` skill, `6` sub-agenti nativi e `10` nodi risiedono in [quality_baseline.json](../nk_tracking/quality_baseline.json).

## 2. Pilastri Ingegneristici Invarianti

| ID | Pilastro | Meccanismo Principale | Modulo Attuatore | Vincolo Chiave |
| :--- | :--- | :--- | :--- | :--- |
| `PIL-01` | Confinamento I/O | Scritture in `.staging/` e promozione atomica | `scripts/win32_2pc_engine.py` | Named Mutex (`[RULE-00]`) |
| `PIL-02` | Topologia `2-Tier` | Unico Hub `DOM-01` e `6` foglie | `scripts/vibe_sprint_router.py` | Zero sub-orchestratori |
| `PIL-03` | Isolamento App | Progetti utente fuori da `NK_Hub/` | `scripts/external_project_scaffolder.py` | Target `NK_External_Projects/` |
| `PIL-04` | Processi e Pytest | Runner UTF-8 detached su NVMe `%TEMP%` | `scripts/platform_runner.py` | `[RULE-WIN32-ISOLATED-PYTEST]` |
| `PIL-05` | Onesta Epistemica | Holdout lock e blocco `HALT_EPISTEMIC_CONFLICT` | `scripts/nk_transcript_tools.py` | Evidenza reale verificabile |

## 3. Requisiti EARS Non Volatili (`v1.0.0-Generation`)

* **R1:** `IL SISTEMA DEVE` esporre al Turno `0` un solo indice `Tier-0` entro `950` token stimati.
* **R2:** `IL SISTEMA DEVE` mantenere ogni file della `Pentad Sovrana 4+1` entro `1.100` token senza contatori transitori.
* **R3:** `QUANDO` gli hook girano sotto `python -S`, `IL SISTEMA DEVE` leggere `saturation_thresholds.json` via `json` stdlib.
* **R4:** `MENTRE` opera il profilo `generation` con alias `carbon`, `IL SISTEMA DEVE` applicare soglie `160k/185k/205k` token e `120/150/180` step.
* **R5:** `QUANDO` sessioni parallele usano Drive FS, `IL SISTEMA DEVE` isolare lo stato in `nk_tracking/sessions/<conversation_id>/`.
* **R6:** `QUANDO` esegue suite `pytest` su Windows, `IL SISTEMA DEVE` isolare il mirror su NVMe locale via `--pytest-isolated`.
* **R7:** `SE` uno script usa path temp letterali non espansi, `IL SISTEMA DEVE` bloccarlo con `[RULE-NO-LITERAL-ENV-PATH]`.
* **R8:** `QUANDO` riceve un prompt `Mode D` o `"procedi*"`, `IL SISTEMA DEVE` attivare `Single-Gate` senza conferme doppie.
* **R9:** `IL SISTEMA DEVE` separare `NK-Arch-Specifier` read-only `GT-14` dal writer confinato `NK-Specifier-Agent`.
* **R10:** `IL SISTEMA DEVE` garantire grafo Python aciclico (`C_k = 0`), zero classi duplicate e file `<= 500` LOC.
* **R11:** `IL SISTEMA DEVE` supportare `.md`/`.json` in `scripts/oracle_evaluator_l3.py` senza override silenziosi in `scripts/rsi_convergence_engine.py`.

## 4. Target Architetturali `SSOT` (`Non Volatili`)

| ID | Ambito Target | Specifica `v1.0.0-Generation` | Verifica Deterministica |
| :--- | :--- | :--- | :--- |
| `SLA-01` | Budget Contesto | `Tier-0 <= 950`, `Tier-1 <= 1.100`, memory `tier1 <= 1.200` tok | `scripts/ast_repo_mapper.py` |
| `SLA-02` | Topologia Moduli | Zero cicli Tarjan (`C_k = 0`) e file `<= 500` LOC | `scripts/ast_guard_validator.py` |
| `SLA-03` | Suite e Copertura | Metriche live misurate in [quality_baseline.json](../nk_tracking/quality_baseline.json) | `scripts/quality_baseline_manager.py` |
| `SLA-04` | Sigillo Integrita | Copertura multi-root verificata su [oracle_lock.json](../nk_tracking/oracle_lock.json) | `scripts/nk_transcript_tools.py` |
| `SLA-05` | Convergenza RSI | Stato `Delta_k = 0` certificato da bundle `GT-14` unificato | `scripts/rsi_convergence_engine.py` |

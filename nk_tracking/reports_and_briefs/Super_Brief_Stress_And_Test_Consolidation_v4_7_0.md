# Super Brief Unificato: Stress Test Olistico e Consolidamento Suite di Test (`v4.7.0-RSI`)

> **Milestone Anchor ID:** `NK-MS-20261031-HOLISTIC-STRESS-AND-TEST-CONSOLIDATION-v4.7.0-RSI`  
> **Intent Brief ID:** `IB-20261031-907169`  
> **Conversazione di Origine:** `9dc0b0f2-35bf-401c-a2f8-7608e457edf6`  
> **Obiettivo:** Eseguire uno stress test avversariale completo sull'ambiente Nexus Keystone (`v4.6.0-Unified`) e ottimizzare la suite di `236` test (`38` file `test_*.py`, `43` file bloccati in `oracle_lock.json`, `7.918` LOC) eliminando ridondanze, file vuoti, colli di bottiglia I/O su Google Drive e assert ossificati.

---

## 1. Diagnosi Preliminare sulla Suite Attuale (`236` Test in `38` File Python)

L'inventario AST eseguito su `tests/` rivela la seguente distribuzione reale:

| Categoria di Test | File `test_*.py` | Funzioni `def test_*` | Item Pytest Eseguiti | Linee di Codice (LOC) | Problema Principale Rilevato |
| :--- | :-: | :-: | :-: | :-: | :--- |
| **1. Core Unit Module** | `25` | `82` | `86` | `3.814` | Include `2` file stub con `0` test (`test_platform_upgrades.py`, `test_super_brief_upgrades.py`) e `3` micro-file da `1` solo test. |
| **2. Stress & DAST Sandbox** | `4` | `31` | `97` | `1.549` | `test_intrinsic_vibe_sandbox_stress.py` espande `8` funzioni in `74` item parametrizzati con letture disco ripetute. |
| **3. Certificazioni Storiche** | `2` | `23` | `23` | `938` | Contiene assert ossificati (`_version == "4.5.2-STE100-Unified"`, `unit_tests_total == 206`, `.agents/hooks.json[0]`) che bloccano la pulizia evolutiva. |
| **4. Incrementali `v4.6.0`** | `7` | `30` | `30` | `1.617` | Frammentati in `7` file separati (`test_v460_wp0c..wp4`) creati uno per Work Package, con helper di caricamento duplicati `7` volte. |
| **TOTALE ATTUALE** | **`38`** (`43` in lock) | **`166`** | **`236`** | **`7.918`** | **Tempo medio: `~17-24 s` su Google Drive; alta ridondanza I/O.** |

---

## 2. Architettura Multi-Agente Anti-Bias e 4 Livelli Tensor-RSI

Per evitare il bias del creatore, il lavoro separa chi analizza, chi attacca in sandbox e chi modifica il codice:

* **Livello `L0` (Static & Contract Gate):** Validazione immediata tramite `ast_guard_validator.py --stage-dir .staging` e controllo `ASD-STE100` (`verify_ste100_compliance`).
* **Livello `L1` (Micro-Loop Funzionale):** Riparazione chirurgica in `.staging/` di ogni anomalia emersa nei test o nello stress test DAST fino a `exit_code: 0`.
* **Livello `L2` (Reflexion & Anti-Bias Audit):** Doppio audit incrociato in sola lettura (`NK-Security-DAST-Auditor` + `NK-RSI-Auditor`) con calcolo di $\Delta_k = 0$ e $Q(S_k) = 100.0$.
* **Livello `L3` (Meta-RSI & Pareto Optimization):** Confronto prima/dopo su tempo di esecuzione (`pytest`), linee di codice (`LOC`), numero di file, `ab_success_full` (`100.0%`) e `harness_token_overhead_pct` (`<= 8.5%`), con rollback automatico via `healing_snapshot_rollback.py` in caso di regressione.

---

## 3. Piano Operativo Proposto in 5 Step Sequenziali (Rielaborabile e Migliorabile)

### Step 1 · Radiografia Analitica dei 236 Test e Matrice di Ortogonalità (Sola Lettura)
* Analizza tutti i `38` file `test_*.py` mappando quali funzioni dei `34` script vengono realmente esercitate da ciascun test.
* Classifica ogni test in `5` categorie: `KEEP_CORE`, `MERGE_SUITE` (es. i `7` file `test_v460_wp*.py` e i micro-file da `1` test), `PRUNE_STUB_OR_REDUNDANT` (es. `test_platform_upgrades.py` e `test_super_brief_upgrades.py`), `MODERNIZE_ASSERT` (es. `test_l2_09`) e `CACHE_SESSION_IO` (fixture `conftest.py` con `scope="session"`).

### Step 2 · Super Stress Test Avversariale E2E in Sandbox (`S1..S5`)
* Esegui in `%TEMP%\nk_sandbox_*\` 5 batterie di stress test reali:
  1. `S1` (Hook Gate & Shell Torture su `nk_hook_gate.py`).
  2. `S2` (Win32 2PC & Crash Recovery Torture su `win32_2pc_engine.py`).
  3. `S3` (Memoria 3-Tier, SQLite WAL & Consolidamento Coseno `--consolidate` su `memory_3tier_engine.py`).
  4. `S4` (AST Mapper `--symbol`, Guard Validator & Transcript Tools `lint-ears` / `lint-prompt`).
  5. `S5` (Motore RSI `--strict-verify`, `--ab-benchmark`, `--verify-canary` e Session Handoff FSM `1..5`).

### Step 3 · Potenziamento e Ottimizzazione degli Script Core in `.staging/scripts/`
* Risolve ogni anomalia o collo di bottiglia emerso dallo Step 2 preservando l'invariante di `34` script in `scripts/`.

### Step 4 · Consolidamento, Potatura e Velocizzazione della Suite in `.staging/tests/`
* Introduce `conftest.py` (`scope="session"`), unifica i file frammentati, rimuove i file vuoti, aggiorna gli assert ossificati e integra i nuovi test di stress ad alto valore diagnostico mantenendo sempre `>= 68` Golden Tests ortogonali Zero-Mock (`[RULE-01.10]`).

### Step 5 · Promozione Atomica Win32 2PC, Re-Freeze Crittografico e Certificazione Finale Scribe
* Promuove `.staging/` con `win32_2pc_engine.py`, aggiorna `oracle_lock.json`, `nk_registry_manifest.json`, `quality_baseline.json`, `repo_map.md` e `PATCH_NOTES.md`, e certifica `CONVERGED_OPTIMAL` (`Delta: 0`, `Q: 100.0`).

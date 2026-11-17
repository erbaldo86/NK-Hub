# 📐 Allineamento 1:1 Turno 4, DAG di Kahn e Drift SHA-256 (`v1.0.0-Generation`)

> **Nodo Proprietario:** `[6] NK-Oracle-Evaluator` (`NK-RSI-Auditor`, `Dual-Execution GT-14`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, massimo 20 parole per frase).

---

## 1. Checklist Allineamento 1:1 Turno 4 (`[RULE-01.13]`, `[RULE-03]`)

1. **Ingestione Pentad Sovrana `4+1`:** Leggi con `read_file` (`<= 800` righe) `concept_map.md`, `structural_tree.md`, `implementation_plan.md`, `repo_map.md` e `nk_genome/modules/` in `Mode A`.
2. **Modalità Snelle:** In `Mode B` e `Mode C` leggi il Fast-Spec in `nk_genome/implementation_plan.md` e `nk_genome/repo_map.md`.
3. **Tracciabilità `R1..Rn`:** Accerta la presenza di `Milestone Anchor ID`, la copertura `100%` dei requisiti `R1..Rn` e le guardie `GT-01..GT-14`.
4. **Isolamento e STE100:** Verifica l'assenza di codice applicativo in `NK_Hub` (`[RULE-PROJECT-ISOLATION]`) e l'esito di `python -u scripts/rsi_convergence_engine.py --vibe-check nk_genome --profile ste100_rsi`.
5. **Certificazione Turno 4:** Con allineamento completo emetti il badge `🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]` via `send_message` (`< 1.800` caratteri) per l'artefatto `RequestFeedback: true`.

---

## 2. Checklist DAG di Kahn e Integrità SHA-256 (`[RULE-01.14]`, `GT-14`)

1. **Telemetria Registro e Preflight:** Ispeziona nella directory temporanea `nk_diagnostics/` gli output dell'Orchestratore da `python -u scripts/nk_registry_indexer.py --verify` e `python -u scripts/preflight_health_check.py --check-only`.
2. **Allineamento Strutturale:** Confronta `nk_genome/structural_tree.md` e `nk_genome/nk_registry_manifest.json`, segnalando file mancanti, orfani o disallineati.
3. **Ordinamento DAG di Kahn (`C_k == 0`):** Costruisci il grafo dagli archi in `nk_diagnostics/repo_map_cache.json` temporaneo e calcola `in_degree`. Blocca ogni ciclo con `CircularDependencyError`.
4. **Blast Radius e Checksum SHA-256:** Calcola in sola lettura il `blast_radius` sul DAG e verifica gli hash SHA-256 per `--vibe-check`.
5. **Separazione Lock Win32 (`[RULE-01.7]`):** Non acquisire mutex Win32. I Named Mutex e i commit 2PC appartengono a `NK-Orchestrator` (`scripts/win32_2pc_engine.py`).

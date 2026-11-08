# NEXUS KEYSTONE OFFICIAL CHANGELOG E PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v5.2.0-STE100-Unified` (`v5.2.0-RSI` / `v5.1.1-RSI` / `v5.1.0-Lean-Sovereign-RSI` / `v5.0.0-STE100-Unified` / `v4.8.0-STE100-Unified` / `v4.7.0-STE100-Unified` / `v3.0.0-STE100-Unified` Compatible)  
> **Milestone Anchor:** `NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI`  
> **Data Consolidamento:** `2026-11-08`  
> **Stato Release:** `[NK-SUPER-BRIEF-STATUS: AUDITED_AND_CERTIFIED_v5.2.0_CLEAN_OPTIMIZED_CHECKPOINT]`

---

## [v5.2.0-RSI] : 2026-11-08 (Milestone: NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI)

### Pulizia Scorie, Ottimizzazione Performance, Fix GitHub Actions CI (`CRLF`/`LF`) e Allineamento `v5.0.0 -> v5.2.0-RSI` (`WP-CLEAN-1..4`, `CP-01..CP-05`)
* **Cluster `CP-01` (`pytest.ini`, `tests/`, `WP-CLEAN-1`):** Rimuove la cartella inesistente da `pytest.ini` e aggiorna `CONFTEST_VERSION` a `5.2.0-STE100-Unified`. Elimina import morti, costanti orfane e `7` loader duplicati nei `18` moduli di test.
* **Cluster `CP-02` (`scripts/`, `WP-CLEAN-1`):** Elimina dead-code interno in `9` moduli core e pre-compila le regex STE100 in `rsi_convergence_engine.py`. Introduce il caching intra-run di `_get_root_mtime()` in `nk_session_bootstrap.py` e rimuove le doppie letture JSON.
* **Cluster `CP-03` (`tests/test_dast_sandbox.py`, `tests/test_core_platform_utilities.py`, `WP-CLEAN-1`):** Ottimizza i timeout e le attese dei sottoprocessi di test per watchdog e tree-kill. Riduce la latenza complessiva della suite mantenendo processi reali e `Mutation Score 100.0%` (`5/5 KILLED`).
* **Cluster `CP-04` (`nk_registry_indexer.py`, `nk_transcript_tools.py`, `nk_hook_gate.py`, `.github/workflows/ci.yml`, `WP-CLEAN-2`):** Normalizza `CRLF -> LF` nel calcolo SHA-256 del registro O(1), di `oracle-lock` e di `integrity`. Risolve il drift `Run #41` su GitHub Actions CI (`Lab NK Hub Continuous Verification`) e converte i file testuali a `LF`.
* **Cluster `CP-05` (Transizione `v5.0.0 -> v5.2.0-RSI`, `WP-CLEAN-3..4`):** Rigenera `repo_map.md` e allinea manuali e Tetralogia a `v5.2.0-STE100-Unified` (`93` test in `18` moduli). Documenta il passaggio da GitHub `v5.0.0` (`253` test) a `v5.2.0-RSI` (`93` test ad alta densità, `-63%` overhead) e aggiorna `NK_Hub_OneClick_Package.zip`.

---

## [v5.1.1-RSI] : 2026-11-08 (Milestone: NK-MS-20261108-EXTERNAL-ANTIBIAS-HARDENING-v5.1.1-RSI)

### Hardening Anti-Bias Esterno, Chiusura Evasioni SAST e Scrittura Atomica 2PC (`WP-ANTIBIAS-1..4`, `CL-01..CL-05`)
* **Cluster `CL-01` (`nk_hook_gate.py`, `WP-ANTIBIAS-1`):** Corregge `target -> cmd` su path con spazi (`L564`) e la sanitizzazione dei token temporanei (`L321`). Blocca gli alias PowerShell (`sc`, `ac`, `ni`, `ri`), `os.open` e rimuove l'asserzione tautologica.
* **Cluster `CL-02` (`nk_session_bootstrap.py`, `WP-ANTIBIAS-2`):** Calcola `_get_root_mtime` multi-percorso (`.wal`, `quality_baseline.json`, `scripts`, `.agents`, `src_app`). Verifica baseline e purge `.wal` su Fast-Pass, normalizza `ONBOARDING_TRIGGERS` e isola `conversation_id`.
* **Cluster `CL-03` (`vibe_sprint_router.py`, `WP-ANTIBIAS-2`):** Ripristina l'asserzione `recommended_mode` su `PROMPT_CORPUS_30` e valida il confine `MODE_C_MAX_LOC == 150`. Blocca i falsi bypass L0 (`<env_capsule>`, `salta gate`, `Vai`/`Confermo` su frasi tecniche).
* **Cluster `CL-04` (`ast_guard_validator.py`, `WP-ANTIBIAS-3`):** Chiude 6 vettori SAST (`JoinedStr`, `"".join`, `__builtins__[...]`, `builtins.__dict__[...]`, `importlib.import_module`, `operator.attrgetter`, `os.exec*`/`os.spawn*`). Aggiunge inoltre il supporto completo per `global` e `nonlocal`.
* **Cluster `CL-05` (`win32_2pc_engine.py`, `quality_baseline_manager.py`, `nk_session_handoff.py`, `preflight_health_check.py`, `WP-ANTIBIAS-4`):** Applica `_atomic_write_bytes` in `recover()`/`_rollback_batch()` e valida `oracle_lock.json` (`SHA256: 7154aee1f6408de54d8157f4f7d9c2f905c44c425650117fdb5ba53446272413`). Rimuove i path git cablati e protegge i file `.bak` in `memory_3tier`.
* **Metriche Certificazione (`WP-ANTIBIAS-1..4`):** Certifica `93/93 PASS` (`100.0%`) in `17` moduli di test e Mutation Score `5/5 KILLED` (`100.0%`). Garantisce inoltre `0` bypass su guardia SAST e Hook Gate.

---

## [v5.1.0-Lean-Sovereign-RSI] - 2026-11-08 (Milestone: NK-MS-20261108-LEAN-FASTBOOT-AND-TEST-CONSOLIDATION-v5.1.0-RSI)

### Fast-Boot Multilivello, Consolidamento Suite Ortogonale e Compattazione Costituzionale (`WP-LEAN-1..WP-LEAN-4`)
* **Fast-Boot (`WP-LEAN-1`):** Attiva il bridge `.agents/AGENTS.md`, `ONBOARDING_BYPASS_VERIFIED` e la cache `TTL=900s` (`< 30ms`).
* **Suite Ortogonale (`WP-LEAN-2`):** Consolida `253` item (`24` file) in `90` Golden Test Zero-Mock (`17` moduli, `< 7s`).
* **Compattazione (`WP-LEAN-3`):** Compatta `.agents/AGENTS.md` (`-38%` righe) con zero perdita di regole.
* **Ratchet e Lock (`WP-LEAN-4`):** Ricalibra `quality_baseline.json` (`90/90 PASS`) e ricongela `oracle_lock.json`.

---

## [v5.0.0-STE100-Unified] - 2026-11-06 (Milestone: NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI)

### Consolidamento Sovrano Clean-Slate, Allineamento Costituzionale e Bonifica Telemetria (`WP-V5-1..WP-V5-4`)
* **Allineamento Motore Esecutivo (`WP-V5-1`):** Allinea i `34` script Python core in `scripts/` alla versione `v5.0.0-STE100-Unified` preservando la compatibilità contrattuale.
* **Allineamento Costituzionale (`.agents/`, `WP-V5-2`):** Aggiorna `AGENTS.md`, `anti_crash_rules.md`, le `16` skill, `prompt_templates.md`, i `5` sub-agenti nativi e `plugin.json` a `v5.0.0-STE100-Unified`.
* **Bonifica Olistica Telemetria (`nk_tracking/`, `WP-V5-3`):** Rimuove `8` report obsoleti, bonifica `session_anchor.jsonl` e `active_context.md`, e sincronizza `quality_baseline.json` (`253/253 PASS`).
* **Allineamento Documentale e Setup (`WP-V5-4`):** Aggiorna `README.md`, `README.it.md`, `GUIDA_INSTALLAZIONE.md`, `00_MAPPA_LIBRERIA_NK.md`, `install.ps1` e `install.sh` a `v5.0.0-STE100-Unified`.

---

## [v4.8.0-RSI-Cleanse] : 2026-11-06 (NK-MS-20261106-HOLISTIC-CLEANSE-AND-DEAD-CODE-PURGE-v4.8.0-RSI)

### Purga Codice Morto, Allineamento Playbook GT-14 e Bonifica Telemetria (`WP-C1..WP-C5`)
* **Purga Codice Morto (`WP-C1`, `WP-C2`):** Rimuove `if False:`, import inutilizzati e costanti orfane in 13 moduli `scripts/`.
* **Conformità `GT-14` Playbook (`WP-C3`):** Allinea `NK-Plan-Aligner` e `NK-Backend-Architect` ai vincoli lessicali e strutturali `STE100_RSI`.
* **Bonifica Telemetria e Report (`WP-C4`, `WP-C5`):** Ripulisce `session_anchor.jsonl`, aggiorna `quality_baseline.json` ed elimina il report duplicato `v4_7_1`.

---

## [v4.8.0-Library-Reorg] : 2026-10-31 (NK-MS-20261031-LIBRARY-REORG-v4.8.0)

### Riorganizzazione Libreria, De-Duplicazione Totale e Pacchetto ZIP 1-Click
* **Ripristino GitHub Actions CI (`WP24`, `IB-20261031-FDC71E`):** Allinea `.github/workflows/ci.yml` su `core.autocrlf false`, `nk_docs_and_setup/requirements.txt` e directory runtime tracciate.
* **Tolleranza Hash Cross-OS (`WP24`):** Accetta varianti `CRLF` e `LF` in `nk_registry_indexer.py` e `nk_transcript_tools.py`, tracciando `nk_tracking/manifests/.gitkeep`.
* **Specchio Concettuale L0 (`WP23`, `IB-20261031-A94277`):** Vincola `nk_guidance` a preparare Brief e `implementation_plan.md` confermato prima del Builder.
* **Protezione `INTRINSIC_PLAN` (`WP23`):** Protegge le conferme brevi (`procedi`, `ok`, `confermo`) e aggiunge test Zero-Mock in `test_vibe_sprint_router.py`.
* **Architettura a Due Cartelle (`NK_Hub` e `NK_External_Projects`):** Riunisce il motore in `NK_Hub/` ed elimina i duplicati dalla radice.
* **Nuova Cartella `nk_docs_and_setup/`:** Centralizza manuali, guide di installazione, script di setup e file workspace.
* **Ottimizzazione `OPT-11 Fast-Stat` (`scripts/nk_registry_indexer.py`):** Riduce la verifica dell'indice da `173.95 ms` a `24.94 ms` (`-85.6%`).
* **Pacchetto `NK_Hub_OneClick_Package.zip`:** Fornisce l'archivio ZIP scaricabile con un click completo di guida bilingue.

---

## [v4.7.0-STE100-Unified] : 2026-10-31 (NK-MS-20261031-HOLISTIC-STRESS-AND-TEST-CONSOLIDATION-v4.7.0-RSI)

### Hardening Avversario Multi-Livello (Batterie S1..S6) e Consolidamento a 245 Test
* **Write-Gate Anti-Esfiltrazione (`S1-01..S1-06`):** `scripts/nk_hook_gate.py` blocca copie non autorizzate da `.staging/` e scritture `.NET` PowerShell.
* **Rollback Transazionale 2PC (`S2-01..S2-03`):** `scripts/win32_2pc_engine.py` valida `.deleted_files.json` prima del commit e ripristina il batch su errore.
* **Concorrenza Memoria e Guardia SAST (`S3..S4`):** `scripts/memory_3tier_engine.py` usa lock thread-safe e `scripts/ast_guard_validator.py` blocca `__import__` e `BinOp`.
* **Suite Consolidata (`24` Moduli, `245/245 PASS`):** Unifica i test su tutti i `34` script e accelera il grafo AST.

---

## [v4.6.0-Unified] : 2026-10-30 (NK-MS-20261030-COMPETITIVE-INTEGRATION-v4.6.0-RSI)

### Hook Nativo a Doppio Binario, Continuità FSM e Ricerca Simbolo AST (`WP-0..WP-4`)
* **Plugin Nativo `nk-gate` (`WP-0a..WP-0d`):** Introduce `--native-contract`, la telemetria `--shadow` e la rotazione backup esterna.
* **Checkpoint FSM Persistente (`WP-3`):** Implementa `record_fsm_checkpoint`, `resume_from_anchor` e `generate_active_context_view` in `scripts/nk_session_handoff.py`.
* **Consolidamento Memoria e Filtro `--symbol` (`WP-4`):** Aggiunge `consolidate_similar_episodes`, l'estrazione AST per simbolo e il validatore `lint-ears`.

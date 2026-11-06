# NEXUS KEYSTONE OFFICIAL CHANGELOG E PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v5.0.0-STE100-Unified` (`v4.8.0-STE100-Unified` / `v4.7.0-STE100-Unified` / `v3.0.0-STE100-Unified` Compatible)  
> **Milestone Anchor:** `NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI`  
> **Data Consolidamento:** `2026-11-06`  
> **Stato Release:** `[NK-SUPER-BRIEF-STATUS: AUDITED_AND_CERTIFIED_v5.0.0_SOVEREIGN]`

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

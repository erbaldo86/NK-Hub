# Nexus Keystone Hub (NK-Hub v5.2.0-STE100-Unified / v5.2.0-RSI)
## Mappa della Libreria Nexus Keystone (`v5.2.0-STE100-Unified` : `2026-11-08`)

> 📦 **Download 1-Click Pacchetto Completo (`.zip`, build `2026-11-08`):** **[Scarica NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/releases/download/v5.2.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** *(oppure [Download Diretto dal Repository](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip))*

Questo documento descrive la struttura deduplicata della libreria in `G:/Il mio Drive/Antigravity/`.
Ogni file possiede una sola copia fisica reale sul disco (`NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI`).

## 1. Cartelle Principali di `Antigravity/`

* **`NK_Hub/`:** Contiene il motore con `5` sub-agenti, `16` skill, `34` script e `93` test in `18` moduli.
* **`NK_External_Projects/`:** Contiene i progetti applicativi esterni isolati dall'Hub.

## 2. Struttura Interna di `NK_Hub/`

1. **`.agents/`:** Contiene `AGENTS.md`, i `5` sub-agenti nativi, le `16` skill sovrane e gli hook.
2. **`.github/`:** Contiene la presentazione bilingue `README.md` (`v5.2.0-STE100-Unified`) e il workflow CI `ci.yml`.
3. **`.staging/`:** Area transazionale isolata per la preparazione delle modifiche prima del commit 2PC.
4. **`.vscode/`:** Configurazione dell'interprete Python per l'ambiente di sviluppo.
5. **`nk_docs_and_setup/`:** Raccoglie `README.it.md`, `README.md`, `GUIDA_INSTALLAZIONE.md`, `00_MAPPA_LIBRERIA_NK.md`, `LICENSE`, gli installer, `requirements.txt` e `NK_Hub_OneClick_Package.zip`.
6. **`nk_genome/`:** Custodisce la Tetralogia Sovrana (`v5.2.0-RSI`), il manifesto O(1) (`< 1.0 ms` in cache) e `PATCH_NOTES.md`.
7. **`nk_tracking/`:** Archivia la memoria a tre livelli (`ws_<sha256_12>`), la telemetria RSI, i benchmark e la baseline (`93/93 PASS`).
8. **`scripts/`:** Contiene i `34` moduli Python indicizzati del motore esecutivo (`36` file Python inclusi gli schemi IPC).
9. **`tests/`:** Contiene i `93` Golden & Stress Tests Zero-Mock (`93/93 PASS`, `Mutation Score 100.0%`) distribuiti in `18` moduli.

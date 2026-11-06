# Nexus Keystone Hub (NK-Hub v5.0.0-STE100-Unified)
## Mappa della Libreria Nexus Keystone (`v5.0.0-STE100-Unified`)

> 📦 **Download 1-Click Pacchetto Completo (`.zip`):** **[Scarica NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/releases/download/v5.0.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** *(oppure [Download Diretto dal Repository](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip))*

Questo documento descrive la struttura deduplicata della libreria in `G:/Il mio Drive/Antigravity/`.
Ogni file possiede una sola copia fisica reale sul disco (`NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI`).

## 1. Cartelle Principali di `Antigravity/`

* **`NK_Hub/`:** Contiene il framework di orchestrazione, gli agenti, gli script e i test.
* **`NK_External_Projects/`:** Contiene i progetti applicativi esterni isolati dall'Hub.

## 2. Struttura Interna di `NK_Hub/`

1. **`.agents/`:** Contiene `AGENTS.md`, i cinque sub-agenti nativi, le sedici skill e gli hook.
2. **`.github/`:** Contiene la presentazione bilingue `README.md` e le configurazioni GitHub.
3. **`.staging/`:** Area transazionale isolata per la preparazione delle modifiche prima del commit 2PC.
4. **`.vscode/`:** Configurazione dell'interprete Python per l'ambiente di sviluppo.
5. **`nk_docs_and_setup/`:** Raccoglie `README.it.md`, `README.md`, `GUIDA_INSTALLAZIONE.md`, `00_MAPPA_LIBRERIA_NK.md`, `LICENSE`, gli installer, `requirements.txt` e `NK_Hub_OneClick_Package.zip`.
6. **`nk_genome/`:** Custodisce la Tetralogia Sovrana, il manifesto O(1) (`< 1.0 ms` in cache) e `PATCH_NOTES.md`.
7. **`nk_tracking/`:** Archivia la memoria a tre livelli (`ws_<sha256_12>`), la telemetria RSI, i benchmark e la baseline.
8. **`scripts/`:** Contiene i trentaquattro moduli Python del motore esecutivo.
9. **`tests/`:** Contiene i test permanenti Zero-Mock (`253/253 PASS`, baseline contrattuale `245`) in ventiquattro moduli.

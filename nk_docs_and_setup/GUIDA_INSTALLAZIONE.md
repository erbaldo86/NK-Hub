# Guida Rapida all'Installazione 1-Click (`NK Hub Generation v3.0.2-Generation`)

> **Versione Pacchetto:** `v3.0.2-Generation`  
> **Milestone Anchor ID:** `NK-GEN-3.0.2-FORENSIC-HARDENING-CLEAN`  
> **Core Engine ABI:** `1.0.0-Generation`  
> **Profilo Modello Predefinito:** `NK_MODEL_PROFILE=generation` (fallback `carbon`; supporta `neon`, `pro`, `flash`, `argon`, `standard`)  
> **Download Diretto ZIP:** **[Scarica NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip)**  
> **Manuali Collegati:** **[🇮🇹 README Italiano](README.it.md)** | **[🇬🇧 English README](README.md)** | **[🗺️ Mappa Libreria](00_MAPPA_LIBRERIA_NK.md)** | **[📋 Patch Notes](../nk_genome/PATCH_NOTES.md)**

---

## 1. Requisiti di Sistema

* **Sistema Operativo:** Windows 10/11, Linux oppure macOS.
* **Runtime Python:** Python `3.11+` (`3.12` consigliato) disponibile nel `PATH`.
* **Ambiente IDE:** Google Antigravity 2.0 (compatibile con workspace VS Code tramite [`Antigravity.code-workspace`](Antigravity.code-workspace)).

---

## 2. Installazione in 3 Passi

### Passo 1: Scarica ed Estrai il Pacchetto ZIP
Scarica **[NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip)** ed estrailo nella cartella di lavoro (ad esempio `Antigravity/`).
* `.agents/` contiene il bridge di scoperta immediata zero-discovery (`AGENTS.md`, `plugins.json`, `skills.json`).
* `NK_Hub/` ospita il motore multi-agente `v3.0.2-Generation` (`Core Engine ABI 1.0.0-Generation`) con `Pentad Sovrana 4+1`, `Tensor-RSI v3`, `11` skill e `6` sub-agenti nativi `GT-14`.
* `NK Proget/Locale/` ospita tutte le applicazioni locali (compatibile con `NK_External_Projects/`). `NK Proget/Online/` resta un mirror di rilascio in sola lettura.

### Passo 2: Esegui lo Script di Installazione Automatica
Apri il terminale dentro `NK_Hub/` ed esegui l'installer corrispondente al tuo sistema operativo.

**Su Windows (PowerShell):**
```powershell
cd NK_Hub
.\nk_docs_and_setup\install.ps1
```

**Su Linux o macOS (Bash):**
```bash
cd NK_Hub
bash ./nk_docs_and_setup/install.sh
```
*(In alternativa esegui `chmod +x ./nk_docs_and_setup/install.sh && ./nk_docs_and_setup/install.sh`.)*

Lo script imposta `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1` e `NK_MODEL_PROFILE=generation` (con fallback `carbon`).
Supporta anche `neon`, `pro`, `flash`, `argon` e `standard`.
Installa [`requirements.txt`](requirements.txt), sincronizza `../.agents/AGENTS.md` da [`root_bridge_AGENTS.md`](root_bridge_AGENTS.md) ed esegue `--verify` e `--strict-verify`.

### Passo 3: Apri il Workspace e Avvia `NK Hub Generation`
Apri [`nk_docs_and_setup/Antigravity.code-workspace`](Antigravity.code-workspace) in Google Antigravity 2.0. Scrivi in chat uno dei `16` trigger di avvio (`8` legacy più `8` `Generation`):
* **Trigger legacy (`8`):** `"avvia ambiente nk"`, `"avvia nk hub"`, `"avvia nk"`, `"avvia hub"`, `"start nk"`, `"start hub"`, `"attiva nk"`, `"attiva ambiente nk"`.
* **Trigger Generation (`8`):** `"avvia generation"`, `"avvia nk generation"`, `"avvia nk hub generation"`, `"avvia ambiente generation"`, `"start generation"`, `"start nk generation"`, `"attiva generation"`, `"attiva ambiente generation"`.

In poche decine di millisecondi si apre la **Dashboard a `10` Nodi (`[0]`..`[9]`)** pronta all'uso.

---

## 3. Diagnostica Rapida Post-Installazione (`--strict-verify` & Pytest NVMe)

Per verificare l'integrità completa dell'installazione esegui i comandi seguenti dalla cartella `NK_Hub/`:

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
$env:PYTHONUTF8="1"
$env:NK_MODEL_PROFILE="generation"
python -B -u scripts/preflight_health_check.py --check-only
python -B -u scripts/nk_session_bootstrap.py
python -B -u scripts/nk_registry_indexer.py --verify
python -B -u scripts/ast_guard_validator.py --target all
python -B -u scripts/nk_transcript_tools.py oracle-lock verify
python -B -u scripts/nk_transcript_tools.py oracle-lock verify --lock-file nk_tracking/oracle_lock_holdout.json --target nk_tracking/oracle_holdout
python -B -u scripts/nk_transcript_tools.py oracle-lock verify --lock-file nk_tracking/governance_lock.json --target scripts
python -B -u scripts/nk_transcript_tools.py oracle-lock verify --lock-file nk_tracking/tensor_rsi_lock.json --target nk_genome/configs/tensor_rsi
python -B -u scripts/rsi_convergence_engine.py --verify --strict-verify
python -B -u scripts/platform_runner.py --pytest-isolated
```

Su Linux o macOS esegui la stessa sequenza sostituendo `$env:CHIAVE="VALORE"` con `export CHIAVE="VALORE"`.
Su Windows `scripts/platform_runner.py --pytest-isolated` clona il codice in `%TEMP%` su NVMe con `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
Questo evita crash `0xC000013A` su Drive FS (`[RULE-WIN32-ISOLATED-PYTEST]`).
Verifica `tier 1 -m fast <= 8.0s` e `tier 1+2 <= 28.0s` sui `4` sigilli `SHA-256`.
I conteggi correnti di suite e coperture (`384/384` in `20.0s`, `stmt 91.25%`, `true_branch 83.43%`, `combined 88.98%`) risiedono in [`nk_tracking/quality_baseline.json`](../nk_tracking/quality_baseline.json).

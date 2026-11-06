# Nexus Keystone Hub (NK-Hub v5.0.0-STE100-Unified)
## 🇮🇹 Guida di Installazione dallo ZIP (1-Click) | 🇬🇧 1-Click ZIP Installation Guide

> 🌍 **Lingua / Language:** **[🇮🇹 Italiano](#-guida-di-installazione-in-italiano-pacchetto-zip-1-click)** | **[🇬🇧 English](#-english-installation-guide-1-click-zip-package)** | **[🇮🇹 Presentazione Completa (README.it.md)](README.it.md)** | **[🇬🇧 Full Presentation (README.md)](README.md)**
>
> 📦 **Download 1-Click Pacchetto Completo (`.zip`):** **[Scarica NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/releases/download/v5.0.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** *(oppure [Download Diretto dal Repository](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip))*

---

# 🇮🇹 Guida di Installazione in Italiano (Pacchetto ZIP 1-Click)

Questa guida spiega passo dopo passo come installare e avviare **Nexus Keystone Hub (`NK-Hub v5.0.0-STE100-Unified`)** partendo dal file **`NK_Hub_OneClick_Package.zip`**.
Non serve alcuna configurazione manuale complessa: l'archivio contiene già la libreria ordinata e lo script automatico di installazione.

## 1. Requisiti Minimi
* **Sistema Operativo:** Windows 10 o Windows 11 a 64-bit (oppure Linux/macOS).
* **Python:** versione `3.11`, `3.12` o `3.14` installata nel computer.
* **Ambiente di Sviluppo:** **Google Antigravity** (IDE o CLI).

## 2. Cosa Trovi Dentro il Pacchetto ZIP
Quando apri `NK_Hub_OneClick_Package.zip`, trovi una libreria ordinata divisa in due sole cartelle principali:
```text
📦 Archivio Estratto (dentro la tua cartella di lavoro Antigravity/)
├── 📄 GUIDA_INSTALLAZIONE.md        # Questa guida rapida subito pronta alla lettura
├── 📄 00_MAPPA_LIBRERIA_NK.md       # Mappa descrittiva di tutte le cartelle
├── 📁 NK_Hub/                       # Motore principale dell'ambiente Nexus Keystone
│   ├── 📁 nk_docs_and_setup/        # Manuali (README), installer (install.ps1/.sh) e workspace
│   ├── 📁 nk_genome/                # Piani architetturali, indice O(1) e PATCH_NOTES.md
│   ├── 📁 nk_tracking/              # Memoria a 3 livelli, telemetria RSI e sigillo dei test
│   ├── 📁 scripts/                  # 34 moduli Python del motore (routing, sicurezza, 2PC)
│   ├── 📁 tests/                    # 253 test reali Zero-Mock (baseline 245, in 24 moduli)
│   └── 📁 .agents/                  # 5 Sub-Agenti Nativi e 16 Playbook SKILL.md
└── 📁 NK_External_Projects/         # Cartella dedicata a tutti i progetti creati con NK
```

## 3. Installazione Guidata in 3 Passi Semplici

### Passo 1: Estrai il File ZIP
1. Crea o apri la tua cartella di lavoro principale (ad esempio `Antigravity`).
2. Estrai tutto il contenuto di `NK_Hub_OneClick_Package.zip` al suo interno.

### Passo 2: Lancia l'Installazione Automatica
Apri il terminale **PowerShell** dentro la cartella `NK_Hub` ed esegui questi due comandi:
```powershell
cd NK_Hub
.\nk_docs_and_setup\install.ps1
```
*(Su Linux o macOS esegui: `cd NK_Hub && chmod +x nk_docs_and_setup/install.sh && ./nk_docs_and_setup/install.sh`).*

**Cosa fa lo script automatico per te:**
1. Controlla la presenza di Python e installa le librerie da `nk_docs_and_setup/requirements.txt`.
2. Sincronizza e verifica l'indice O(1) con cache `Fast-Stat` in `< 1.0 ms`.
3. Esegue i `253` test di sicurezza e qualità (`253/253 PASS`, baseline contrattuale `>= 245`).

**Cosa vedrai a schermo a fine installazione (Conferma che tutto è OK):**
```text
🟢 [NK-REGISTRY-VERIFY] Status: VALID | Skills: 16 | Scripts: 34
253 passed (245 baseline)
[SUCCESS] Nexus Keystone Hub v5.0.0-STE100-Unified installato e certificato con successo!
```

> **Alternativa Manuale (se preferisci lanciare i singoli comandi uno alla volta):**
> ```powershell
> cd NK_Hub
> pip install -r nk_docs_and_setup/requirements.txt
> python -u scripts/nk_session_bootstrap.py
> python -u scripts/nk_registry_indexer.py --verify
> python -u -m pytest tests/ -q
> ```

### Passo 3: Avvia l'Ambiente in Google Antigravity
1. Apri **Google Antigravity** sulla cartella (oppure fai doppio click su `NK_Hub/nk_docs_and_setup/Antigravity.code-workspace`).
2. Scrivi nella chat:
   ```text
   avvia ambiente nk
   ```
3. In meno di `50 ms` apparirà il **Centro di Controllo a 15 Nodi (`[0]`..`[14]`)**: da quel momento puoi scrivere in italiano cosa vuoi creare o modificare.

---

# 🇬🇧 English Installation Guide (1-Click ZIP Package)

This guide explains step by step how to install and launch **Nexus Keystone Hub (`NK-Hub v5.0.0-STE100-Unified`)** from **`NK_Hub_OneClick_Package.zip`**.
No complex manual setup is required: the archive contains the organized library and automated installer scripts.

## 1. Minimum Requirements
* **Operating System:** Windows 10 or Windows 11 64-bit (or Linux/macOS).
* **Python:** version `3.11`, `3.12`, or `3.14` installed on your computer.
* **Agent IDE:** **Google Antigravity** (IDE or CLI).

## 2. What Is Inside the ZIP Package
When you extract `NK_Hub_OneClick_Package.zip`, you get a clean two-folder workspace layout:
```text
📦 Extracted Archive (inside your Antigravity/ workspace folder)
├── 📄 GUIDA_INSTALLAZIONE.md        # This quick installation guide
├── 📄 00_MAPPA_LIBRERIA_NK.md       # Complete directory map
├── 📁 NK_Hub/                       # Core Nexus Keystone engine
│   ├── 📁 nk_docs_and_setup/        # Manuals (README), installers (install.ps1/.sh) & workspace
│   ├── 📁 nk_genome/                # Architecture plans, O(1) manifest & PATCH_NOTES.md
│   ├── 📁 nk_tracking/              # 3-Tier memory, RSI telemetry & test oracle lock
│   ├── 📁 scripts/                  # 34 core Python modules (routing, security, 2PC)
│   ├── 📁 tests/                    # 253 Zero-Mock tests (245 baseline) across 24 test modules
│   └── 📁 .agents/                  # 5 Native Sub-Agents & 16 SKILL.md Playbooks
└── 📁 NK_External_Projects/         # Isolated folder for all applications built with NK
```

## 3. 3-Step Guided Setup

### Step 1: Extract the ZIP Archive
1. Open or create your main workspace directory (for example `Antigravity`).
2. Extract the entire contents of `NK_Hub_OneClick_Package.zip` into that folder.

### Step 2: Run the Automated Installer
Open **PowerShell** inside the `NK_Hub` folder and run:
```powershell
cd NK_Hub
.\nk_docs_and_setup\install.ps1
```
*(On Linux or macOS run: `cd NK_Hub && chmod +x nk_docs_and_setup/install.sh && ./nk_docs_and_setup/install.sh`).*

**What you will see on screen when setup finishes:**
```text
🟢 [NK-REGISTRY-VERIFY] Status: VALID | Skills: 16 | Scripts: 34
253 passed (245 baseline)
[SUCCESS] Nexus Keystone Hub v5.0.0-STE100-Unified installed and certified!
```

### Step 3: Start the Environment in Google Antigravity
1. Open **Google Antigravity** (or double-click `NK_Hub/nk_docs_and_setup/Antigravity.code-workspace`).
2. Type in the chat:
   ```text
   start nk
   ```
   *(or in Italian: `"avvia ambiente nk"`).*
3. In under `50 ms`, the agent displays the **15-Node Control Dashboard (`[0]`..`[14]`)**: describe your goal in plain language or select a node number to begin.

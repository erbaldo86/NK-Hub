# Nexus Keystone Hub (`v4.5.0-STE100-Unified` / `v4.4.0-STE100-Unified` / `v3.0.0-STE100-Unified`)
## 🇮🇹 Guida di Installazione Rapida e Avvio | 🇬🇧 Quick Installation and Startup Guide

> 🌍 **Lingua / Language:** **[🇮🇹 Italiano](#-sezione-italiana-guida-di-installazione-rapida-v450-ste100-unified)** | **[🇬🇧 English](#-english-section-quick-installation-and-startup-guide-v450-ste100-unified)** | **[🇮🇹 Manuale (README.it.md)](README.it.md)** | **[🇬🇧 Manual (README.md)](README.md)**

---

# 🇮🇹 Sezione Italiana: Guida di Installazione Rapida (`v4.5.0-STE100-Unified`)

Questa guida illustra l'installazione e l'avvio di **Nexus Keystone Hub (`NK-Hub`)** per **Google Antigravity**.
L'architettura include `5` Sub-Agenti Nativi, `16` Playbook, `34` Moduli Indicizzati (`36` file Python) e `115` test.

## 1. Requisiti di Sistema (IT)
* Sistema operativo **Windows 10 o Windows 11** a 64-bit (oppure Linux/macOS per esecuzione POSIX).
* Interprete **Python 3.11, 3.12 o 3.14** registrato nella variabile `PATH`.
* Ambiente **Google Antigravity 2.0** (IDE o CLI).

## 2. Procedura di Installazione in 4 Passi (IT)

### Passo 1: Verifica della Struttura del Workspace
1. Posiziona la cartella del repository nel percorso desiderato del computer o di Google Drive.
2. Verifica la presenza della struttura principale del repository (`v4.5.0-STE100-Unified`):
   ```text
   ├── .agents/                 # AGENTS.md, hooks.json, 5 Sub-Agenti Nativi e 16 Playbook SKILL.md
   ├── nk_genome/               # Tetralogia 4/4, idea_canvas.md, nk_registry_manifest.json e PATCH_NOTES.md
   ├── nk_tracking/             # Activity Anchor, telemetria RSI, oracle_lock.json, memoria 3-Tier e baseline
   ├── scripts/                 # 34 Moduli Indicizzati (36 file Python totali inclusi schemas/)
   ├── tests/                   # Suite di 115 Golden e Stress Tests Zero-Mock in 34 file (68 pavimento GT-13)
   ├── requirements.txt         # Dipendenze Python della piattaforma
   ├── README.md                # Manuale tecnico e tutorial completo (EN)
   ├── README.it.md             # Manuale tecnico e tutorial completo in ASD-STE100 (IT)
   ├── PATCH_NOTES.md           # Mirror root del Changelog ufficiale
   └── GUIDA_INSTALLAZIONE.md   # Guida bilingue di installazione (IT + EN)
   ```

### Passo 2: Installazione delle Dipendenze Python
Apri il terminale **PowerShell** nella radice del repository ed esegui il comando seguente:
```powershell
pip install -r requirements.txt
```
In alternativa, esegui l'installer automatico `.\install.ps1` su Windows oppure `./install.sh` su Linux/macOS.

### Passo 3: Esecuzione del Bootstrap, Indice O(1) e Diagnostica
Esegui il controllo di avvio sessione (`< 120` ms), la verifica dell'indice O(1) e la convergenza RSI:
```powershell
python -u scripts/nk_session_bootstrap.py
python -u scripts/nk_registry_indexer.py --verify
python -u scripts/preflight_health_check.py --check-only
python -u scripts/rsi_convergence_engine.py --verify
```

### Passo 4: Esecuzione dei 115 Golden e Stress Tests Zero-Mock
Esegui la suite completa di `115` test permanenti Zero-Mock in `34` file tramite `pytest`:
```powershell
python -u -m pytest tests/ -q
```
> **Esito atteso:** `115 passed` (`100.0% PASS`, pavimento costituzionale di `68` Golden Tests `GT-13`).

## 3. Avvio Operativo in Google Antigravity (IT)
1. Apri la cartella del repository in **Google Antigravity**.
2. Scrivi in chat uno dei trigger verbali di avvio (esempio: `"avvia nk hub"` oppure `"start nk"`).
3. Il sistema esegue `scripts/nk_session_bootstrap.py` ed espone la Master Dashboard a 15 nodi (`[0]`..`[14]`).
4. Scegli la **Modalità Diretta** digitando un numero tra `[0]` e `[14]`.
5. In alternativa, usa la **Modalità Goal-Driven** descrivendo il tuo obiettivo in linguaggio naturale.
6. Per creare una nuova applicazione esterna, esegui lo scaffolder deterministico:
   ```powershell
   python -u scripts/external_project_scaffolder.py --name NomeApp --target "../NK_External_Projects/NomeApp"
   ```

---

# 🇬🇧 English Section: Quick Installation and Startup Guide (`v4.5.0-STE100-Unified`)

This guide explains how to install and start **Nexus Keystone Hub (`NK-Hub`)** for **Google Antigravity**.
The architecture includes `5` Native Sub-Agents, `16` Playbooks, `34` Indexed Modules (`36` Python files), and `115` tests.

## 1. System Requirements (EN)
* **Windows 10 or Windows 11** 64-bit operating system (or Linux/macOS for POSIX execution).
* **Python 3.11, 3.12, or 3.14** interpreter registered in the `PATH` variable.
* **Google Antigravity 2.0** environment (IDE or CLI).

## 2. 4-Step Installation Procedure (EN)

### Step 1: Verify the Workspace Structure
1. Place the repository folder in the desired path on your computer or Google Drive.
2. Verify the main repository directory structure (`v4.5.0-STE100-Unified`).

### Step 2: Install Python Dependencies
Open the **PowerShell** or **Bash** terminal in the repository root and run the following command:
```powershell
pip install -r requirements.txt
```
Alternatively, run the automated installer `.\install.ps1` on Windows or `./install.sh` on Linux/macOS.

### Step 3: Run Bootstrap, O(1) Registry Indexer, and Diagnostics
Run the fast session bootstrap check (`< 120` ms), the O(1) registry verification, and the RSI check:
```powershell
python -u scripts/nk_session_bootstrap.py
python -u scripts/nk_registry_indexer.py --verify
python -u scripts/preflight_health_check.py --check-only
python -u scripts/rsi_convergence_engine.py --verify
```

### Step 4: Run the 115 Zero-Mock Golden and Stress Tests
Run the complete suite of `115` permanent Zero-Mock tests across `34` test files using `pytest`:
```powershell
python -u -m pytest tests/ -q
```
> **Expected outcome:** `115 passed` (`100.0% PASS`, constitutional floor of `68` Golden Tests `GT-13`).

## 3. Operational Startup in Google Antigravity (EN)
1. Open the repository folder in **Google Antigravity**.
2. Type one of the startup triggers in the chat (for example: `"start nk"` or `"avvia nk hub"`).
3. The system runs `scripts/nk_session_bootstrap.py` and displays the 15-node Master Dashboard (`[0]`..`[14]`).
4. Select **Direct Mode** by typing a node number between `[0]` and `[14]`.
5. Alternatively, use **Goal-Driven Mode** by describing your objective in natural language.
6. To initialize a new external application, run the deterministic project scaffolder:
   ```powershell
   python -u scripts/external_project_scaffolder.py --name AppName --target "../NK_External_Projects/AppName"
   ```

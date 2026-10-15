# Nexus Keystone Hub (`v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified`)
## Guida di Installazione Rapida e Avvio per Google Antigravity

> 🌍 **Lingua / Language:** **[🇮🇹 Guida Installazione (IT)](GUIDA_INSTALLAZIONE.md)** | **[🇮🇹 Manuale Completo (README.it.md)](README.it.md)** | **[🇬🇧 Full Manual (README.md)](README.md)**

Questa guida illustra la procedura di installazione e avvio di **Nexus Keystone Hub (`NK-Hub`)** per **Google Antigravity**.

---

## 1. Requisiti di Sistema
* Sistema operativo **Windows 10 o Windows 11** a 64-bit (oppure Linux/macOS per esecuzione POSIX).
* Interprete **Python 3.11, 3.12 o 3.14** registrato nella variabile `PATH`.
* Ambiente **Google Antigravity 2.0** (IDE o CLI).

---

## 2. Procedura di Installazione in 4 Passi

### Passo 1: Apertura del Workspace
1. Posiziona la cartella del repository nel percorso desiderato del tuo computer o di Google Drive.
2. Verifica la presenza della struttura principale del repository:
   ```text
   ├── .agents/                 # Regolamento AGENTS.md, hooks.json, NK-RSI-Auditor e 16 Skill
   ├── nk_genome/               # Tetralogia Sovrana 4/4, idea_canvas.md e PATCH_NOTES.md (SSOT)
   ├── nk_tracking/             # Activity Anchor, telemetria RSI, memoria 3-Tier e baseline
   ├── scripts/                 # 30 Moduli Logici Core (33 file Python totali)
   ├── tests/                   # Suite permanente di 108 Golden Tests Zero-Mock + evals/
   ├── requirements.txt         # Dipendenze Python della piattaforma
   ├── README.md                # Manuale tecnico e tutorial completo (EN)
   ├── README.it.md             # Manuale tecnico e tutorial completo in ASD-STE100 (IT)
   ├── PATCH_NOTES.md           # Mirror root del Changelog ufficiale
   └── GUIDA_INSTALLAZIONE.md   # Questa guida di installazione
   ```

### Passo 2: Installazione delle Dipendenze Python
Apri il terminale **PowerShell** nella radice del repository ed esegui il comando seguente:
```powershell
pip install -r requirements.txt
```

### Passo 3: Esecuzione del Bootstrap e della Diagnostica
Esegui il controllo rapido di avvio sessione (`< 120` ms) e la verifica di salute in sola lettura:
```powershell
python -u scripts/nk_session_bootstrap.py
python -u scripts/preflight_health_check.py --check-only
python -u scripts/rsi_convergence_engine.py --verify
```

### Passo 4: Esecuzione dei 108 Golden Tests
Esegui la suite completa di `108` test permanenti Zero-Mock tramite `pytest`:
```powershell
python -u -m pytest tests/ -q
```
> **Esito atteso:** `108 passed` (`100.0% PASS`).

---

## 3. Avvio Operativo in Google Antigravity

1. Apri la cartella del repository in **Google Antigravity**.
2. Scrivi in chat uno dei trigger verbali di avvio (esempio: `"avvia nk hub"` oppure `"start nk"`).
3. Il sistema esegue `scripts/nk_session_bootstrap.py` ed espone la Master Dashboard a 15 nodi (`[0]`..`[14]`).
4. Scegli la **Modalità Diretta** digitando un numero tra `[0]` e `[14]`.
5. In alternativa, usa la **Modalità Goal-Driven** descrivendo il tuo obiettivo in linguaggio naturale.
6. Per creare una nuova applicazione esterna, esegui lo scaffolder deterministico:
   ```powershell
   python -u scripts/external_project_scaffolder.py --name NomeApp --target "../NK_External_Projects/NomeApp"
   ```

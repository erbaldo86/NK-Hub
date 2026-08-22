# 📦 Nexus Keystone Hub (v1.1.0-Universal)
## 🚀 Guida di Installazione Rapida & Avvio per Google Antigravity

Benvenuto nel pacchetto di distribuzione di **Nexus Keystone Hub (NK-Hub)**!  
Questa guida spiega in modo semplice e diretto come installare e attivare l\'ecosistema all\'interno del tuo ambiente **Google Antigravity** su Windows.

---

## 📋 1. Requisiti di Sistema
Prima di iniziare, assicurati di avere installato:
- **Windows 10 o Windows 11** (64-bit).
- **Python 3.11, 3.12 o 3.14** (con Python aggiunto al PATH di sistema).
- **Google Antigravity** (IDE o CLI).

---

## 🛠️ 2. Procedura di Installazione in 4 Passaggi

### Passo 1: Estrazione del file ZIP nel Workspace
1. Estrai il contenuto di questo archivio ZIP nella cartella principale che intendi utilizzare come **Workspace di Google Antigravity** (può essere sia una cartella locale sul tuo PC, sia una cartella sincronizzata su **Google Drive** o **OneDrive**).
2. La cartella conterrà la seguente struttura pronta all\'uso:
   `
   ├── .agents/                 # Le 16 Skill e la Costituzione di sistema
   ├── nk_genome/               # Trittico di specifiche architetturali (SSOT)
   ├── nk_tracking/             # Activity Anchor e baseline di qualità
   ├── scripts/                 # I 10 Motori Asincroni Core (2PC, DAST, SBFL, AST, Memoria)
   ├── tests/                   # Suite permanente di 49 unit test Zero-Mock
   ├── requirements.txt         # Dipendenze Python minime
   ├── README.md                # Presentazione completa e manuale tecnico
   ├── PATCH_NOTES.md           # Changelog ufficiale
   └── GUIDA_INSTALLAZIONE.md   # Questa guida
   `

---

### Passo 2: Installazione delle Dipendenze Python
Apri il terminale **PowerShell** all\'interno della cartella estratta ed esegui:
`powershell
pip install -r requirements.txt
`
*(Le dipendenze includono solo librerie standard e collaudate: pydantic, psutil, pytest, pytest-asyncio)*.

---

### Passo 3: Verifica e Collaudo Automatico (Preflight Check)
Esegui lo script di autodiagnosi per verificare che l\'ambiente sia integro e pronto:
`powershell
python scripts/preflight_health_check.py
`
> **Esito atteso:** Riceverai lo stato HEALTHY_GREEN che conferma la perfetta igiene del workspace e l\'allineamento di tutte le 16 skill.

---

### Passo 4: Esecuzione dei Test di Sistema
Verifica che tutti i 49 test di sistema passino al 100%:
`powershell
python -m unittest discover tests -v
`
> **Esito atteso:** Ran 49 tests ... OK (100% PASS).

---

## 💡 3. Come Usare Nexus Keystone Hub in Antigravity

Una volta aperta la cartella in **Google Antigravity**:
1. **Riconoscimento Automatico:** Antigravity caricherà automaticamente le regole di governance contenute in .agents/AGENTS.md e le **16 Vocational Skills** presenti in .agents/skills/.
2. **Hard Execution Gate:** Nessun agente modificherà mai i tuoi file sorgente di produzione senza autorizzazione esplicita. Tutto viene sviluppato in .staging/ e collaudato in sandbox effimere prima del commit.
3. **Flusso Autopilot in Sciame:** Puoi chiedere all\'agente di pianificare, sviluppare o manutenere progetti software complessi: l\'Hub coordinerà automaticamente i nodi specializzati (Ideator, UX Architect, Security Auditor, Builder asincrono, Oracle Evaluator).
4. **Documentazione Completa:** Per tutti i dettagli su architettura, formule matematiche SBFL e memoria a 3 livelli, fai riferimento al file **README.md**.

---
*Nexus Keystone Hub v1.1.0-Universal — Ingegnerizzato per l\'Affidabilità Assoluta.*

# 🏛️ Lab NK Hub — Sovereign AI Agentic OS (v1.6.0-VibeEnhanced)
### *Il Sistema Operativo Cognitivo Sovrano, Orchestratore di Sciami Multi-Agente & Motore di Vibe Coding per Google Antigravity*

<p align="center">
  <a href="README.md">🇬🇧 <b>English</b></a> &nbsp;•&nbsp; 
  <a href="README.it.md">🇮🇹 <b>Italiano (Attuale)</b></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Release-v1.6.0--VibeEnhanced-0052FF?style=for-the-badge&logo=shield&logoColor=white" alt="Release Badge" />
  <img src="https://img.shields.io/badge/Standard-CRV_4.0_Universal-00C853?style=for-the-badge&logo=checkmarx&logoColor=white" alt="CRV 4.0 Standard" />
  <img src="https://img.shields.io/badge/Zero--Mock-100%25_Real_Certified-FF6D00?style=for-the-badge&logo=databricks&logoColor=white" alt="Zero-Mock Certified" />
  <img src="https://img.shields.io/badge/Platform_Core_Tests-100%25_PASS-success?style=for-the-badge&logo=pytest&logoColor=white" alt="Platform Tests" />
  <img src="https://img.shields.io/badge/Anti--Freeze-Pulse_Sentinel_Active-brightgreen?style=for-the-badge&logo=prometheus&logoColor=white" alt="Anti-Freeze Sentinel" />
  <img src="https://img.shields.io/badge/Vibe_Coding-Triple--Speed_Mode_C%2FB%2FA-9C27B0?style=for-the-badge&logo=speedtest&logoColor=white" alt="Triple Speed Vibe Coding" />
  <img src="https://img.shields.io/badge/Commit_Lock-Win32_2PC_Named_Mutex-E91E63?style=for-the-badge&logo=windows&logoColor=white" alt="Win32 2PC Mutex" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License MIT" />
</p>

---

## ⚡ Patch Notes & Novità v1.6.0-VibeEnhanced (Cosa è Migliorato e Potenziato)

> **In Primo Piano:** Se conosci già la versione precedente (**v1.1.0-Universal**), ecco il riassunto esecutivo delle modifiche, dei potenziamenti e delle ottimizzazioni introdotte in **v1.6.0-VibeEnhanced**:

### 1. 💓 Anti-Freeze Pulse Sentinel ([`scripts/async_heartbeat_signaler.py`](scripts/async_heartbeat_signaler.py))
- **Cosa c'era prima:** Durante task molto lunghe, benchmark o cicli complessi (>45 secondi), l'assenza di output continuo faceva congelare l'ambiente o l'interprete dell'agente. Inoltre, scrivere log diagnostici nella root sincronizzata da Google Drive scatenava errori `WinError 32` / `WinError 5` (Sharing Violation) e deadlock I/O.
- **Cosa è stato potenziato:** Implementato un generatore di battito asincrono continuo (15-20s) con watchdog hard ceiling a 45s. Tutti i dump diagnostici e i file di stato transitori sono ora **rigorosamente isolati sul disco fisico locale in `%TEMP%\nk_diagnostics\`**, azzerando qualsiasi freeze o lock su filesystem cloud virtuali.

### 2. ⚡ Tassonomia a Tripla Velocità per il Vibe Coding ([`scripts/vibe_sprint_router.py`](scripts/vibe_sprint_router.py))
- **Cosa c'era prima:** L'*Hard Execution Gate* (`[RULE-00]`) era monolitico: richiedeva approvazione manuale preventiva per qualsiasi operazione di scrittura, rallentando pesantemente i task veloci di frontend, UI o piccoli script.
- **Cosa è stato potenziato:** Introdotto il router a 3 velocità graduate:
  - **⚡ Mode C (Vibe-Sprint / Fluid-Track):** Per modifiche UI, frontend o singoli script $\le 150$ LOC (AST Risk Score $\le 0.3$). Time-To-First-Render $<15$s in staging senza burocrazia e senza permission ping-pong.
  - **🔧 Mode B (Fast-Track Staging):** Per bugfix chirurgici e micro-features su backend con validazione mirata pre-commit.
  - **🏛️ Mode A (Sovereign CRV 4.0):** Per rilasci di release o modifiche architetturali profonde, con la piena FSM a 5 turni e audit formale a 4 macro-fasi.

### 3. 🎯 Mandati Intrinseci `/implementation` e `/goal`
- **`[RULE-01.11]` Intrinsic Implementation:** I trigger verbali di pianificazione (*"crea un piano"*, *"progetta"*, *"definisci l'architettura"*, *"scrivi il brief"*) attivano automaticamente il formato standard `/implementation` (`concept_map.md`, `structural_tree.md`, `implementation_plan.md`) senza bisogno di istruzioni manuali.
- **`[RULE-01.12]` Intrinsic Goal:** Quando l'utente assegna un obiettivo (*"realizza"*, *"costruisci"*, *"implementa"*), l'agente attiva la condotta goal-driven ininterrotta e il self-healing loop in staging fino al raggiungimento verificato della *Definition of Done*.

### 4. 👥 Armonizzazione Universale delle 16 Skill Vocazionali
- Sincronizzate tutte le 16 skill vocazionali sullo standard universale **CRV 4.0** (4 Macro-Fasi: Build & Stage, 100% Strict Read-Only Audit, 2PC Commit, Teardown) e sulla **Swarm FSM a 5 Turni** (Draft, Attack, Refine, Alignment, Commit).
- Formalizzata la gerarchia di sovranità: `NK-Session-Controller` detiene il potere di VETO logico, `NK-Master-Hub` è il proprietario esclusivo del commit su disco con Named Mutex Win32.

### 5. 🛡️ Correzione Quality Ratchet & Bonifica Totale delle Scorie
- **Correzione Inverted Ratchet (`nk_tracking/quality_baseline.json`):** Risolto il bug storico che impostava `"higher_is_better": true` sul tasso di fallimento dei test. Ora il ratchet impone che nessuna modifica possa degradare la qualità sotto il 100.0% PASS.
- **Compatibilità Estensioni Binarie Windows / Dokan (`sitecustomize.py`):** Risolto il crash `WinError 998: Invalid access to memory location` generato da Python 3.14 quando caricava librerie native C/Rust (`.pyd`) da volumi virtuali cloud, tramite caching trasparente su storage locale NVMe.
- **Separazione Netta Hub vs Creazioni:** Rimossa qualsiasi scoria legacy di vecchie applicazioni o benchmark orfani. Lab NK Hub è ora focalizzato al 100% come sistema operativo di sviluppo agentico.

---

## 🧩 La Filosofia Fondamentale: "L'Hub è la Fabbrica, le Applicazioni sono i Prodotti"

Uno dei principi cardine di **Lab NK Hub** è la **netta separazione tra l'infrastruttura di orchestrazione e le creazioni software prodotte**:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                LAB NK HUB (La Fabbrica)                                 │
│  .agents/ (16 Skill)  │  scripts/ (14 Motori)  │  nk_genome/ (SSOT)  │  nk_tracking/    │
└────────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                       Crea, Collauda, Certifica & Archivia
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              LE CREAZIONI (I Prodotti)                                  │
│                                                                                         │
│   📁 Programmi di test/TestNK/     ──► Gestionale Imprese, ATECO & UE Size (Archiviato) │
│   📁 Future Applicazioni / App X   ──► Portali, Microservizi, Bot (Cartelle Separate)   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

* **Lab NK Hub** risiede nel repository GitHub: è la piattaforma che contiene le regole, le skill, i motori asincroni, i compilatori AST e i sistemi di sandboxing.
* **Le Creazioni** (come il gestionale `TestNK` testato con 29 test e archiviato nella cartella `Programmi di test`, o future applicazioni) sono i prodotti finiti generati dall'Hub. Vengono collaudate in sandbox e archiviate nei rispettivi depositi dedicati, mantenendo l'Hub sempre pulito, leggero e pronto per nuove sfide.

---

## 📖 Indice dei Contenuti
1. [🌟 Che cos'è Lab NK Hub?](#-1-che-cosè-lab-nk-hub)
2. [⚙️ Come Funziona e Come NON Funziona](#-2-come-funziona-e-come-non-funziona)
3. [👥 Mappa Completa delle 16 Skill Vocazionali](#-3-mappa-completa-delle-16-skill-vocazionali)
4. [🛠️ Guida Pratica: Come Bisognerebbe Utilizzarla](#-4-guida-pratica-come-bisognerebbe-utilizzarla)
5. [🔄 Scenario di Esempio End-to-End: Come NK Hub Crea un'Applicazione](#-5-scenario-di-esempio-end-to-end-come-nk-hub-crea-unapplicazione)
6. [🚀 Installazione Rapida & Verifiche di Piattaforma](#-6-installazione-rapida--verifiche-di-piattaforma)
7. [📊 Matrice Ufficiale di Certificazione](#-7-matrice-ufficiale-di-certificazione)

---

# 🌟 1. Che cos'è Lab NK Hub?

**Lab NK Hub (Nexus Keystone)** è un **Sistema Operativo Agentico Deterministico (Agentic OS)** progettato per governare gli assistenti di intelligenza artificiale (come Google Antigravity e Claude) quando scrivono, modificano e collaudano codice software reale.

Quando si lavora con modelli LLM avanzati nel coding quotidiano, si manifestano frequentemente 4 grandi problemi:
1. **Scritture Selvaggie & Allucinazioni:** L'agente modifica direttamente file di produzione prima ancora di aver compreso a fondo l'architettura o testato il codice, rompendo funzionalità esistenti.
2. **Crash da File Lock su Cloud Storage:** Modifiche concorrenti su cartelle sincronizzate (Google Drive, Dropbox, OneDrive) generano collisioni `WinError 32` / `WinError 5` che corrompono i sorgenti.
3. **Falsi Positivi da "Mock":** I test generati dall'AI usano spesso `MagicMock` e fuzzer in memoria che simulano il successo, ma quando il codice viene avviato su processi e database reali fallisce miseramente.
4. **Saturazione & Amnesia di Contesto:** Task lunghe saturano la finestra di contesto (token context limit), facendo dimenticare all'agente le specifiche iniziali o congelando l'interfaccia.

**Lab NK Hub risolve questi problemi alla radice**, trasformando l'AI da semplice "generatore di testo" a un'**equipe ingegneristica autonoma e disciplinata**.

---

# ⚙️ 2. Come Funziona e Come NON Funziona

### 🟢 Come Funziona (I 5 Pilastri Sovrani)
1. **Staging Isolato Obbligatorio (`.staging/`):** Nessun builder scrive mai direttamente nei sorgenti di produzione. Il codice viene generato in un'area di staging isolata e sottoposto a controllo sintattico AST ([`scripts/ast_guard_validator.py`](scripts/ast_guard_validator.py)).
2. **Invisible Self-Healing Loop:** Se il codice in staging presenta errori, l'Hub attiva un ciclo di auto-riparazione a 3 iterazioni con localizzazione matematica del guasto (**SBFL Ochiai / Tarantula**, [`scripts/sbfl_engine.py`](scripts/sbfl_engine.py)), correggendo il bug prima che chiunque se ne accorga.
3. **Audit Dinamico 100% Strict Read-Only:** Nella Macro-Fase 2, gli auditor di sicurezza e l'Oracolo ([`scripts/oracle_evaluator_l3.py`](scripts/oracle_evaluator_l3.py)) eseguono i test in sandbox temporanee (`%TEMP%\nk_sandbox_*`). Durante l'audit è vietato modificare il codice: se c'è un errore, scatta il VETO immediato.
4. **Commit Atomico a 2 Fasi con Win32 Named Mutex:** Solo se tutti i test hanno esito PASS (100%), [`NK-Master-Hub`](.agents/skills/NK-Master-Hub/SKILL.md) acquisisce un Named Mutex di Windows a livello di kernel (`scripts/win32_2pc_engine.py`), scrive il Write-Ahead Log (WAL) crittografico SHA-256 e promuove i file con rename atomico `MoveFileExW` con Shadow Swap Fallback per dischi cloud.
5. **Memoria Episodica a 3 Livelli:** Gestita da [`scripts/memory_3tier_engine.py`](scripts/memory_3tier_engine.py) su 4 domini (`ARCH`, `SEC`, `OPS`, `DEVX`), mantiene la memoria di lavoro entro un cap di 350 token per dominio, garantendo coerenza a lungo termine senza sovraccaricare il contesto.

### 🔴 Come NON Funziona (I Divieti Tassativi del Regolamento)
- ❌ **NON consente scritture non autorizzate (`[RULE-00]`):** Divieto assoluto di toccare file di produzione senza autorizzazione o senza passare per il ciclo di staging.
- ❌ **NON accetta mock o simulazioni sintetiche (`[RULE-01.2]`):** Divieto categorico di `MagicMock`. Ogni test deve girare su processi reali, database reali su disco e connessioni HTTP reali.
- ❌ **NON impone burocrazia su task veloci (`[RULE-01.8]`):** Per modifiche UI rapide o frontend, l'agente non fa "permission ping-pong" ad ogni riga, ma usa Mode C con Time-To-First-Render $<15$s.
- ❌ **NON permette regressioni qualitative (`[RULE-01.10]`):** Nessuna modifica può abbassare il superamento della suite di test di piattaforma sotto il 100.0%.

---

# 👥 3. Mappa Completa delle 16 Skill Vocazionali

L'Hub orchestra uno sciame di **16 esperti vocazionali**, ciascuno confinato al proprio ruolo:

| Skill | Ruolo & Vocazione | Macro-Fase CRV | Turno FSM | Modalità Operativa |
| :--- | :--- | :---: | :---: | :--- |
| [`NK-Master-Hub`](.agents/skills/NK-Master-Hub/SKILL.md) | **Sovrano Infrastrutturale L3.** Central Change Router, Kahn DAG, Named Mutex Win32 e titolarità esclusiva del commit atomico 2PC. | Macro 3 | Turno 5 | Sovereign Committer |
| [`NK-Session-Controller`](.agents/skills/NK-Session-Controller/SKILL.md) | **Sovrano Critico di Sessione.** Regista della Swarm FSM a 5 turni, gestore trigger `/implementation` e `/goal`, potere di VETO assoluto. | Tutte | Turno 1-5 | Strict Read-Only |
| [`NK-Ideator`](.agents/skills/NK-Ideator/SKILL.md) | **Ideatore Concettuale (L0).** Tecniche SCAMPER, benchmark analysis, stress concettuale e stesura del Concept Map in `nk_genome/`. | Macro 1 | Turno 1 | Spec Writer |
| [`NK-Plan-Aligner`](.agents/skills/NK-Plan-Aligner/SKILL.md) | **Allineatore 1:1.** Verifica corrispondenza perfetta tra Brief, Albero Strutturale e Piano di Implementazione prima della scrittura. | Macro 1 | Turno 4 | Strict Read-Only |
| [`NK-Python-Async-Builder`](.agents/skills/NK-Python-Async-Builder/SKILL.md) | **Costruttore Core Backend.** Generatore di codice asincrono Python, Pydantic v2, FastAPI e sandboxing nativo. Scrive solo in `.staging/`. | Macro 1 | Turno 3 | Staging Builder |
| [`NK-Delta-Architect`](.agents/skills/NK-Delta-Architect/SKILL.md) | **Architetto di Modifica & Patch.** Riceve prompt a 4 blocchi, esegue Two-Stage Grounding e guida il self-healing loop in staging. | Macro 1 | Turno 3 | Staging Builder |
| [`NK-Backend-Architect`](.agents/skills/NK-Backend-Architect/SKILL.md) | **Progettista Topologie & API.** Modella schemi database relazionali, contratti OpenAPI e architetture scalabili. | Macro 1 | Turno 1-3 | API Specifier |
| [`NK-App-UX-Architect`](.agents/skills/NK-App-UX-Architect/SKILL.md) | **Architetto UX/UI & Frontend.** Progetta interfacce responsive, dashboard accessibili e contratti DOM. | Macro 1 | Turno 1-3 | UI Specifier |
| [`NK-Oracle-Evaluator`](.agents/skills/NK-Oracle-Evaluator/SKILL.md) | **Oracolo Deterministico.** Cold Auditor per validazione patch in sandbox effimera, composite scoring triple-sample e verifiche formali. | Macro 2 | Turno 4 | Cold Auditor (100% RO) |
| [`NK-Security-Auditor`](.agents/skills/NK-Security-Auditor/SKILL.md) | **Auditor di Sicurezza Full-Stack.** Analisi vulnerabilità SAST/DAST L1/L2/L3, Dual-Shield Cascade e rilascio report di audit TAS. | Macro 2 | Turno 2 | Security Auditor (100% RO) |
| [`NK-Dynamic-Sandbox-StressTester`](.agents/skills/NK-Dynamic-Sandbox-StressTester/SKILL.md) | **Stress Tester Runtime.** Esegue pen-testing isolato, carichi concorrenti e DAST dinamico in sandbox temporanee. | Macro 2 | Turno 2 | Sandbox Runner |
| [`NK-Bug-Diagnostic-Engine`](.agents/skills/NK-Bug-Diagnostic-Engine/SKILL.md) | **Motore Diagnostico RCA.** Localizzazione matematica del guasto SBFL (Ochiai, Tarantula) e scarto di falsi bug. | Macro 1 | Turno 2 | Strict Read-Only |
| [`NK-State-Router`](.agents/skills/NK-State-Router/SKILL.md) | **Gestore di Stato & Drift Detection.** Rilevamento drift del codice sorgente, manutenzione del DAG e backup di consistenza. | Macro 1-3 | Tutte | State Engine |
| [`NK-Episodic-Memory-Engine`](.agents/skills/NK-Episodic-Memory-Engine/SKILL.md) | **Motore Memoria a Lungo Termine.** Indicizzazione vettoriale, archiviazione JSONL e recupero semantico per i 4 domini NK. | Macro 3 | Turno 5 | Memory Engine |
| [`NK-Agent-Instruction-Forge`](.agents/skills/NK-Agent-Instruction-Forge/SKILL.md) | **Fonderia Agenti.** Generatore formale di istruzioni di sistema e manifest YAML per nuovi sotto-agenti specializzati. | Utility | On Demand | Specifier |
| [`NK-Scribe`](.agents/skills/NK-Scribe/SKILL.md) | **Cronista & Documentatore.** Aggiorna il changelog SSOT (`PATCH_NOTES.md`), i registri di sessione e sincronizza la documentazione. | Macro 3 | Turno 5 | Doc Writer (Post-Pass) |

---

# 🛠️ 4. Guida Pratica: Come Bisognerebbe Utilizzarla

### 👶 Per l'Utente Non Esperto (Linguaggio Naturale)
Non devi conoscere i dettagli dei Mutex Win32 o della localizzazione Ochiai. Parla semplicemente con il tuo assistente:

1. **Creare un nuovo software o prototipo:**
   > *"Voglio realizzare un'applicazione per gestire i preventivi dei clienti, con calcolo automatico dell'IVA e generazione di report in PDF."*  
   *Comportamento di NK Hub:* Comprende l'obiettivo, attiva `/implementation` e `/goal`, definisce il piano, scrive il codice in staging isolato, collauda i calcoli in sandbox e ti notifica quando l'applicazione è funzionante e archiviata.
2. **Riparare un bug:**
   > *"Quando inserisco un importo negativo il programma va in crash invece di mostrare un errore."*  
   *Comportamento di NK Hub:* Isola il punto esatto del codice difettoso tramite SBFL, applica la patch correttiva in sandbox e la promuove solo se tutti i test passano.
3. **Modifiche grafiche veloci (Vibe Coding):**
   > *"Aggiungi una modalità scura alla dashboard e metti un pulsante verde per esportare in CSV."*  
   *Comportamento di NK Hub:* Riconosce una modifica frontend veloce ($\le 150$ LOC), attiva Mode C e applica il cambiamento in meno di 15 secondi senza bloccarti con continue conferme.

---

### 👨‍💻 Per lo Sviluppatore Esperto (Controllo Architetturale & CLI)
Per gli ingegneri software che desiderano governare le verifiche da terminale:

* **Preflight Health Check:**
  ```powershell
  & ".\.venv\Scripts\python.exe" scripts/preflight_health_check.py
  ```
  Verifica lo stato di salute dell'Hub, pulisce i file transazionali WAL aventi TTL $>60$s e verifica l'integrità della Session Anchor.
* **Controllo Sintattico & AST Guard su Tutti i File:**
  ```powershell
  & ".\.venv\Scripts\python.exe" scripts/ast_guard_validator.py --target all
  ```
* **Esecuzione Suite di Test Permanente:**
  ```powershell
  & ".\.venv\Scripts\pytest.exe" tests/ -v
  ```
* **Verifica Baseline di Qualità & Ratchet Non-Regressivo:**
  ```powershell
  & ".\.venv\Scripts\python.exe" scripts/quality_baseline_manager.py --check
  ```

---

# 🔄 5. Scenario di Esempio End-to-End: Come NK Hub Crea un'Applicazione

Ecco la ricostruzione dettagliata di come Lab NK Hub ha gestito una richiesta reale di sviluppo: la creazione da zero del gestionale **`TestNK`** (anagrafica imprese, validazione P.IVA Luhn, codici ATECO e calcolo dimensione UE 2003/361/CE):

```mermaid
sequenceDiagram
    autonumber
    actor User as Utente
    participant SC as NK-Session-Controller
    participant ID as NK-Ideator / Architetti
    participant BL as NK-Python-Async-Builder
    participant OR as NK-Oracle & Security-Auditor
    participant MH as NK-Master-Hub
    participant FS as Deposito Creazioni (Programmi di test)

    User->>SC: "Crea un gestionale anagrafica con ATECO, dimensione UE e bridge bandi"
    Note over SC: [Turno 1: Draft] Attiva /implementation intrinseco
    SC->>ID: Genera concept_map, structural_tree e piano
    ID-->>SC: Specifiche Bounded Context e modelli dati pronti
    Note over SC: [Turno 2: Attack & Stress]
    SC->>OR: Analisi avversariale su lock concorrenziali e memory leak
    OR-->>SC: Identificati requisiti di compatibilità e validazione Luhn
    Note over SC: [Turno 3: Build & Self-Healing]
    SC->>BL: Sviluppa in .staging/ con database SQLite reale
    Note over BL: Rilevato crash encoding CP1252 e DLL Dokan WinError 998
    Note over BL: Self-Healing: genera sitecustomize.py e safe logging
    BL-->>SC: Build completata con AST Guard PASS (100%)
    Note over SC: [Turno 4: 1:1 Alignment & Cold Audit]
    SC->>OR: Esegui 29 test reali in sandbox effimera (Strict Read-Only)
    OR-->>SC: VERDETTO: PASS (29/29 test, zero-mock verificato)
    Note over SC: [Turno 5: Commit Atomico & Archiviazione]
    SC->>MH: Esegui commit Win32 2PC Mutex
    Note over MH: Acquisizione Named Mutex -> WAL crittografico SHA-256
    MH->>FS: Archivia l'app in "Programmi di test/TestNK" con README dedicato
    Note over MH: Bonifica la cartella di staging e rimuove i residui dall'Hub
    MH-->>User: ✅ Applicazione creata, collaudata e archiviata! L'Hub rimane pulito.
```

Questo flusso dimostra plasticamente la potenza dell'Hub:
1. Ha gestito l'intero ciclo di vita senza intasare la conversazione principale;
2. Ha risolto autonomamente problemi reali di compatibilità Windows a basso livello;
3. Ha archiviato il software finito nella cartella dedicata [`Programmi di test/TestNK`](file:///G:/Il%20mio%20Drive/Programmi%20di%20test/TestNK/), lasciando il workspace di Lab NK Hub pulito, leggero e pronto per la prossima creazione.

---

# 🚀 6. Installazione Rapida & Verifiche di Piattaforma

### Prerequisiti
* **Sistema Operativo:** Windows 10 / 11 (64-bit) con PowerShell 7 o Windows PowerShell standard.
* **Python:** Versione 3.10, 3.11, 3.12 o 3.14 (supporto nativo CTypes e Win32 API).
* **Git:** Installato e configurato su PATH.

### Installazione in 3 Passaggi

```powershell
# 1. Clona il repository ufficiale di Lab NK Hub
git clone https://github.com/erbaldo86/NK-Hub.git Antigravity
cd Antigravity

# 2. Esegui lo script di configurazione automatica dell'ambiente
powershell -ExecutionPolicy Bypass -File .\install.ps1

# 3. Verifica l'allineamento e la salute del sistema
& ".\.venv\Scripts\python.exe" scripts/preflight_health_check.py
```

Se il comando restituisce `{"status": "HEALTHY_GREEN"}`, la piattaforma è perfettamente operativa.

---

# 📊 7. Matrice Ufficiale di Certificazione

| Controllo / Invariante | Metodo di Verifica | Esito Certificato |
| :--- | :--- | :---: |
| **Suite Test Motori Piattaforma** | `pytest tests/test_win32_2pc.py tests/test_dast_sandbox.py ...` | 🟢 **PASS (100.0%)** |
| **AST Syntactic & Scope Purity** | `scripts/ast_guard_validator.py --target all` | 🟢 **PASS (0 violazioni)** |
| **Preflight Health Check** | `scripts/preflight_health_check.py` | 🟢 **HEALTHY_GREEN** |
| **Quality Baseline Ratchet** | `scripts/quality_baseline_manager.py --check` | 🟢 **ZERO REGRESSIONS** |
| **Anti-Freeze Pulse Sentinel** | Keepalive cadenzato (15-20s) e watchdog (45s) | 🟢 **ATTIVO (%TEMP% ISOLATED)** |
| **Win32 Named Mutex 2PC** | Commit atomico a livello di kernel con WAL SHA-256 | 🟢 **VERIFICATO SU DISCO** |
| **Zero Mock Mandate** | Divieto assoluto di mock o simulazioni in memoria | 🟢 **100% PROCESSI REALI** |

---

<p align="center">
  <b>Lab NK Hub (Nexus Keystone v1.6.0-VibeEnhanced)</b> — <i>Sovereign Agentic Operating System.</i><br>
  Costruito per governare l'AI, testato sul campo, ottimizzato per il vero Vibe Coding.
</p>

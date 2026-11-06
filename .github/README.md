# Nexus Keystone Hub (NK-Hub v5.0.0-STE100-Unified)
## L'Ambiente di Sviluppo Multi-Agente Ordinato, Sicuro e Autonomo per Google Antigravity

> 🌍 **Lingua / Language:** **[🇮🇹 Italiano (Qui sotto)](#-1-presentazione-veloce-in-90-secondi-lhook-perch%C3%A9-nasce-e-cosa-fa)** | **[🇬🇧 English Version (Below)](#-english-version--nexus-keystone-hub-nk-hub-v500-ste100-unified)** | **[📖 Guida Installazione ZIP](../nk_docs_and_setup/GUIDA_INSTALLAZIONE.md)** | **[🗺️ Mappa Libreria](../nk_docs_and_setup/00_MAPPA_LIBRERIA_NK.md)**
>
> 📦 **SCARICA CON 1 CLICK L'AMBIENTE COMPLETO (`.ZIP` CON GUIDA INCLUSA):**  
> 👉 **[Scarica NK_Hub_OneClick_Package.zip (Release Ufficiale v5.0.0-STE100-Unified)](https://github.com/erbaldo86/NK-Hub/releases/download/v5.0.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** *(oppure [Download Diretto dal Repository](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip))*

---

## ⚡ 1. Presentazione Veloce in 90 Secondi (L'Hook: Perché Nasce e Cosa Fa)

### Perché è stato sviluppato `NK-Hub`?
Creare un programma con l'IA è facile nei primi minuti. Appena il progetto cresce, però, nascono tre problemi ricorrenti:
1. **Cartelle nel caos:** file di sistema, script, test e progetti finiscono mescolati o duplicati nella stessa cartella.
2. **Modifiche che rompono ciò che funzionava:** l'agente modifica direttamente i tuoi file buoni senza prima provarli in un'area separata.
3. **Perdita di memoria e "falsi positivi":** nelle sessioni lunghe l'IA dimentica le regole. Spesso riduce i controlli nei test pur di superarli.

**`NK-Hub` nasce esattamente per eliminare questi tre problemi.** Trasforma Google Antigravity in una cabina di regia ordinata con `5` Sub-Agenti specializzati. La squadra progetta, costruisce e collauda il codice in `.staging/`. Promuove il lavoro solo quando ogni controllo reale è superato al `100%`.

### 💬 Esempio Reale in 30 Secondi: Come Dialoghi con `NK-Hub`
> 1. **Tu scrivi in chat (o detti col microfono):**  
>    *"Crea un'applicazione web per gestire i preventivi dei clienti ed esportarli in PDF."*
> 2. **`NK-Hub` ti mostra subito lo Specchio di Conferma (`Gate L0`):**  
>    *"Ho capito l'obiettivo: creerò la nuova app isolata in `NK_External_Projects/PreventiviApp`. Preparerò database, interfaccia e generatore PDF in collaudo. Confermi con 1 click?"*
> 3. **Tu clicchi su `Conferma`:**  
>    La squadra di agenti costruisce l'applicazione in `.staging/` ed esegue i test di sicurezza. Ripara gli errori in autonomia e promuove il progetto finito nella tua cartella.

### I Benefici Immediati a Colpo d'Occhio

| Cosa Succede di Solito con un Agente AI Standard | Cosa Succede con `NK-Hub` |
| :--- | :--- |
| File sparsi e confusione tra motore e progetti | **Libreria Ordinata:** solo `NK_Hub/` (il motore) e `NK_External_Projects/` (le tue app) |
| L'IA parte subito e a volte fraintende la richiesta | **Gate L0 a 1 Click:** riassume l'obiettivo prima di iniziare e parte solo col tuo OK |
| Modifiche dirette sui file buoni con rischio di rottura | **Collaudo in `.staging/` + Salvataggio Atomico:** i file buoni non vengono mai corrotti |
| Un solo agente fa tutto e perde il filo | **Squadra di 5 Sub-Agenti Nativi:** chi scrive il codice è separato da chi controlla la sicurezza |
| Rischio che l'IA "addolcisca" i test per farli passare | **Sigillo `oracle-lock` Anti-Trucco:** i test sono bloccati e nessuno può manometterli |

---

## 📦 2. Guida Rapida all'Installazione (Per Chi Scarica lo ZIP con 1 Click)

Il file **[NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/releases/download/v5.0.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** contiene già l'intera libreria pronta all'uso e la [GUIDA_INSTALLAZIONE.md](../nk_docs_and_setup/GUIDA_INSTALLAZIONE.md).

### Installazione in 3 Passi Semplici
1. **Estrai lo ZIP:** scarica `NK_Hub_OneClick_Package.zip` ed estrailo nella tua cartella di lavoro (ad esempio `Antigravity/`). Otterrai due cartelle pulite: `NK_Hub` e `NK_External_Projects`.
2. **Avvia l'Installer Automatico:** apri PowerShell dentro `NK_Hub` ed esegui:
   ```powershell
   cd NK_Hub
   .\nk_docs_and_setup\install.ps1
   ```
   *(Su Linux/macOS esegui `./nk_docs_and_setup/install.sh`. Lo script installa i pacchetti da `nk_docs_and_setup/requirements.txt`, verifica l'indice in `< 1.0 ms` ed esegue i `253` test certificati).*
3. **Accendi il Motore in Antigravity:** apri la cartella in Google Antigravity e scrivi in chat:
   ```text
   avvia ambiente nk
   ```
   Si aprirà subito il **Centro di Controllo a 15 Nodi (`[0]`..`[14]`)** pronto a ricevere le tue istruzioni.

---

## 🎯 3. Due Modi di Viverlo: Utente Vibe Coding vs Utente Esperto + I 6 Punti Cardine

`NK-Hub` è progettato su due livelli complementari. È guidato in superficie per chi crea senza tecnicismi e rigoroso per chi cerca garanzie ingegneristiche.

### 🧑‍💻 A. Per l'Utente Poco Esperto (Puro Vibe Coding Senza Complicazioni)
Non serve saper programmare né ricordare comandi da terminale. Ecco come si usa nella vita di tutti i giorni:

| Cosa Vuoi Fare Tu | Cosa Ti Basta Scrivere nella Chat di Antigravity | Cosa Fa `NK-Hub` in Automatico per Te |
| :--- | :--- | :--- |
| **Accendere l'ambiente** | `"avvia ambiente nk"` | Controlla che tutto sia in ordine in `< 1.0 ms` e ti mostra il menù interattivo. |
| **Creare un nuovo programma** | *"Voglio creare un'app per gestire le scadenze dei bandi"* | Crea una cartella pulita in `NK_External_Projects/`, progetta grafica e database e costruisce l'app. |
| **Fare una modifica veloce** | *"Aggiungi un pulsante verde per scaricare la tabella in Excel"* | Attiva la corsia rapida (`Mode C`), modifica il file in meno di mezzo secondo e lo verifica. |
| **Sistemare un problema** | *"Quando clicco su Salva esce un errore, puoi sistemarlo?"* | Trova la riga esatta del difetto, la ripara nell'area di prova e aggiorna il programma. |

* **Parli col microfono:** se la dettatura unisce due parole, il normalizzatore vocale le corregge prima del lavoro.
* **Non puoi mai rovinare l'ambiente:** i progetti vivono separati in `NK_External_Projects/` e ogni modifica viene provata prima in `.staging/`.

---

### 🛠️ B. Per l'Utente Molto Esperto / Senior Architect (Cosa Ha in Più `NK-Hub`)
Se sei uno sviluppatore esperto o un architetto software, ecco i vantaggi di `NK-Hub` rispetto a un agente AI standard:

| Limite Tecnico degli Agenti AI Standard | Soluzione Architetturale Implementata in `NK-Hub` |
| :--- | :--- |
| **Contesto Monolitico e Degrado (*Context Rot*)** | **Topologia 2-Tier Hub-and-Spoke:** `5` Sub-Agenti Nativi isolati con finestre di contesto indipendenti e filtro automatico delle skill esterne (`-7.042` token/turno). |
| **Auto-Valutazione e *Reward Hacking* (*Goodhart's Law*)** | **Separazione Hardware `GT-14` + `oracle-lock`:** gli Auditor operano con `enable_write_tools: false` e i test sono sigillati in `SHA-256` prima della fase di build. |
| **Scritture Parziali e Corruzione del Working Tree** | **Transazioni Atomiche `Win32 2PC`:** promozione da `.staging/` protetta da Named Mutex Kernel a 64-bit con rollback immediato dell'intero batch su errore. |
| **Latenza Elevata sulle Micro-Modifiche** | **Fast-Bypass `Mode C` (`< 500 ms`) e Cache `OPT-11` (`< 1.0 ms`):** analisi AST della profondità (`max_depth <= 1`, `<= 150` LOC) con risparmio del `71.9%` dei token. |
| **Traceback Prolissi nel Contesto di Debug** | **Fault Localization `SBFL Ochiai` (`< 80` Token):** localizzazione spettrale della riga guasta con taglio AST Def-Use e snapshot SHA-256 monotono. |

---

### 🌟 C. I 6 Punti Cardine di `NK-Hub` (I Pilastri per Cui Sceglierlo)

1. **Libreria Ordinata e De-Duplicata (`NK_Hub` + `NK_External_Projects` + `nk_docs_and_setup`):**
   Ogni file possiede una sola copia fisica. Guide e setup risiedono in `nk_docs_and_setup/`, genoma in `nk_genome/`, telemetria in `nk_tracking/`, motore in `scripts/` e progetti in `NK_External_Projects/`.
2. **Separazione Hardware tra Chi Scrive e Chi Controlla (`GT-14`):**
   I `5` Sub-Agenti Nativi applicano vincoli hardware nel manifesto. Gli Auditor hanno `enable_write_tools: false` e tutti i sub-agenti impongono `enable_subagent_tools: false` (`RULE-01`).
3. **Gate L0 a 1 Click e Corsia Veloce `Mode C` (`< 500 ms`, `-71.9%` Token):**
   Prima di eseguire, il router compila un contratto Pydantic v2 (`MetaPromptGateContract`) con hash `SHA-256`. Per le modifiche entro `150` righe attiva il Fast-Bypass con validazione statica in `~65 ms`.
4. **Onestà Epistemica $100\times$ e Guardie Statiche `SAST-GAMING-D01..D04`:**
   Il validatore AST blocca `PYTEST_CURRENT_TEST` (`D01`) e l'ispezione dello stack frame a runtime (`D02`). Blocca inoltre fixture cablate (`D03`) e ramificazioni sulla lunghezza dei dati di test (`D04`).
5. **Convergenza Matematica Tensor-RSI ($\Delta_k = 0, Q(S_k) = 100.0$) e Commit `Win32 2PC`:**
   Ad ogni iterazione $k$, il motore calcola il vettore di difetto $\Delta_k(p)$ e la fitness $Q(S_k)$:
   $$\Delta_k(p) = 100 D_k + 20 E_{\text{PoC},k} + w_{\text{SAST}}^{(p)} \text{SAST}_k + 12 D_{\text{sem},k} + w_{\text{test}}^{(p)} (T_{\text{fail},k} + C_k) + w_{H}^{(p)} H_k + w_{M}^{(p)} M_k + w_{L}^{(p)} L_k + w_{G}^{(p)} G_k$$
   Il codice viene promosso da `.staging/` alla produzione tramite `win32_2pc_engine.py` solo quando $\Delta_k = 0$ e $Q(S_k) = 100.0$.
6. **Prestazioni Misurate su Windows 11 64-bit (`OPT-1..OPT-11`):**
   * **Avvio Bootstrap Fast-Stat (`nk_session_bootstrap.py`):** `18..28 ms` (target `< 50 ms`).
   * **Verifica Registro O(1) con Cache `OPT-11` (`nk_registry_indexer.py --verify`):** `< 1.0 ms` in cache (`41.8 ms` cold).
   * **Lookup Tassonomico e Routing L0 (`vibe_sprint_router.py`):** `1.08..2.12 ms` (target `< 15 ms`).
   * **Suite Completa di `253` Test Reali Zero-Mock (`245` baseline, `24` moduli in `tests/`):** `100.0% PASS` (`253/253`).

---

## 🚀 4. Caso Studio Reale: Come NK-Hub Ha Progettato e Costruito un Gestionale Completo in una Sola Notte

Questo caso studio reale mostra come `NK-Hub` trasforma un'idea complessa in un software pronto all'uso. L'esperienza documenta la nascita di `NK-Studio-Lab-Progettazione` e la costruzione autonoma del gestionale `NK-Studio-CRM`.

### Fase 1: Co-Progettazione Interattiva Utente + `NK-Hub`
Prima di scrivere codice, l'utente dialoga in modo interattivo con `NK-Hub`. Attraverso scambi guidati con `NK-Ideator`, `NK-App-UX-Architect`, `NK-Backend-Architect` e `NK-Plan-Aligner`, il modello elabora l'intero impianto progettuale:
* **Analisi di Mercato Fiscale e Legale (`TAX` e `LEGAL`):** definisce i flussi reali per studi professionali multidisciplinari.
* **Architettura a `4` Scatole Strategiche:** separa anagrafica unificata, motore di importazione, comunicazioni rapide e sicurezza dati.
* **Design System `NK Clarity v2.0`:** stabilisce la gerarchia visiva ad alta leggibilità con tema `Calm Daylight` e `Dark Switcher`.
* **Blueprint per `5` Futuri Add-On:** predispone le prese per `Bandi Bridge`, `Parcelle`, `Scadenze`, `Antiriciclaggio/GDPR` e `Circolari/PEC`.

### Fase 2: L'Invio sul Gate L0 e la Costruzione Autonoma in un'Unica Sessione Notturna
Approvato il piano sul `Gate L0` con un click, la squadra dei `5` Sub-Agenti Nativi (`Mode A`) entra in azione. Il team lavora in totale autonomia durante la notte in un'unica sessione continua dentro `.staging/`:
1. **Backend e Database Corazzato:** costruisce il backend `FastAPI` e il database `SQLite3 WAL`. Integra il radar conflitto di interessi e la cassaforte di backup `.zip`.
2. **Motori Intelligenti e Connettori:** realizza i modelli polimorfici `Pydantic v2` e il motore `SmartMergeEngine` (`.vcf` Apple/Google, `.csv`, `XML FatturaPA`). Collega inoltre i connettori 1-Click (`Gmail`, `Outlook`, `PEC`, `WhatsApp`, `.ics`) e il bus eventi a `5` prese Add-On.
3. **Interfaccia Web e Collaudo Zero-Mock:** crea l'interfaccia web `NK Clarity v2.0` (`Calm Daylight` e `Dark Switcher`). Supera infine **`36/36` test automatici Zero-Mock** (`unit`, `E2E`, stress `S1..S4`) e consegna al mattino il gestionale pronto con `start_crm.bat`.

---

## 🔬 5. Sezione Tecnica Dedicata: Come Lavorano Agenti, 16 Skill e 34 Script

```mermaid
flowchart LR
    U["Richiesta Utente (Testo / Voce)"] --> R["Gate L0 + Router O(1) (1.19 ms)"]
    R -->|"Mode C <= 150 LOC"| FB["Fast-Bypass .staging/ + Vibe-Check (<500 ms)"]
    R -->|"Mode A / B / D"| S["5 Sub-Agenti Nativi + 16 Playbook SKILL.md"]
    FB --> C["Commit Atomico Win32 2PC (Delta_k = 0, Q = 100.0)"]
    S --> A["Cold Audit 6 Gate + Oracle-Lock SHA-256"]
    A --> C
```

### 5.1 Le 4 Modalità Automatiche di Lavoro (`scripts/vibe_sprint_router.py`)

| Modalità | Quando Si Attiva | Chi Interviene | Controlli Applicati |
| :--- | :--- | :--- | :--- |
| **`Mode D` (Analisi e Ricerca)** | Domande, analisi, audit o ricerche web/MCP | `NK-Specifier-Agent` / `NK-RSI-Auditor` (Sola Lettura) | Lookup O(1) in `< 1.0 ms` + Connettori MCP |
| **`Mode C` (Vibe-Sprint Rapido)** | Piccole modifiche UI o script (`<= 150` righe) | Fast-Bypass o `NK-Builder-Agent` in `.staging/` | Guardia AST (`D01..D04`) + `--vibe-check` (`< 500 ms`) |
| **`Mode B` (Riparazione / Refactor)** | Correzione bug o modifiche su più file | `NK-Builder-Agent` + `NK-Security-DAST-Auditor` | Staging + `oracle-lock` + Localizzatore `SBFL Ochiai` |
| **`Mode A` (Progetto Completo)** | Nuova app da zero o grande evoluzione architetturale | Squadra Completa dei `5` Sub-Agenti Nativi | Piano a 5 Turni + Cold Review a 6 Gate + Commit 2PC |

### 5.2 I 5 Sub-Agenti Nativi (`.agents/agents/*/agent.md`)

| Sub-Agente Nativo | Dominio | Permessi Hardware (`GT-14`) | Cosa Fa e Dove Può Scrivere |
| :--- | :---: | :--- | :--- |
| **[NK-Specifier-Agent](../.agents/agents/NK-Specifier-Agent/agent.md)** | `DOM-02` | `write: true`, `mcp: true` | Progetta idee, interfacce UX/UI, architetture backend e piani in `nk_genome/*`. |
| **[NK-Builder-Agent](../.agents/agents/NK-Builder-Agent/agent.md)** | `DOM-03` | `write: true`, `mcp: false` | Scrive e ripara codice Python, React/Next.js e skill esclusivamente dentro `.staging/*`. |
| **[NK-Security-DAST-Auditor](../.agents/agents/NK-Security-DAST-Auditor/agent.md)** | `DOM-04` | **`write: false`** (Sola Lettura) | Esegue controlli SAST anti-trucco, test in sandbox DAST, test Browser E2E e diagnosi bug. |
| **[NK-RSI-Auditor](../.agents/agents/NK-RSI-Auditor/agent.md)** | `DOM-04` | **`write: false`** (Sola Lettura) | Valuta i 6 Gate di qualità, l'integrità del grafo DAG e la convergenza matematica $\Delta_k = 0$. |
| **[NK-Scribe-Agent](../.agents/agents/NK-Scribe-Agent/agent.md)** | `DOM-05` | `write: true`, `mcp: false` | Aggiorna la documentazione, la mappa del repository (`repo_map.md`) e la memoria a 3 livelli. |

### 5.3 Catalogo delle 16 Skill Playbook (`.agents/skills/NK-*/SKILL.md`)

Quando avvii l'ambiente con `"avvia ambiente nk"`, puoi richiamare direttamente qualsiasi nodo da `[0]` a `[14]`:

| Nodo | Nome Playbook Skill | Dominio | Sub-Agente Esecutore | Compito Specifico del Playbook |
| :---: | :--- | :---: | :--- | :--- |
| **Hub** | [NK-Master-Hub](../.agents/skills/NK-Master-Hub/SKILL.md) | `DOM-01` | Regista Principale | Coordina il routing a 2 livelli, il sigillo `oracle-lock` e il commit finale Win32 2PC. |
| **`[0]`** | [NK-Ideator](../.agents/skills/NK-Ideator/SKILL.md) | `DOM-02` | `NK-Specifier-Agent` | Sviluppa l'idea iniziale (`idea_canvas.md`), analisi SCAMPER e ricerche web `tavily-mcp`. |
| **`[1]`** | [NK-App-UX-Architect](../.agents/skills/NK-App-UX-Architect/SKILL.md) | `DOM-02` | `NK-Specifier-Agent` | Progetta l'esperienza utente, il Design System 8px/HSL e i componenti interattivi. |
| **`[2]`** | [NK-Backend-Architect](../.agents/skills/NK-Backend-Architect/SKILL.md) | `DOM-02` | `NK-Specifier-Agent` | Disegna l'architettura backend, gli schemi Pydantic v2, le API e `firebase-mcp-server`. |
| **`[3]`** | [NK-Agent-Instruction-Forge](../.agents/skills/NK-Agent-Instruction-Forge/SKILL.md) | `DOM-02` | `NK-Builder-Agent` | Crea e aggiorna nuove skill e istruzioni agente in formato tecnico ASD-STE100. |
| **`[4]`** | [NK-Python-Async-Builder](../.agents/skills/NK-Python-Async-Builder/SKILL.md) | `DOM-03` | `NK-Builder-Agent` | Sviluppa backend Python asincrono, database SQLite WAL e cicli di auto-riparazione. |
| **`[5]`** | [NK-Delta-Architect](../.agents/skills/NK-Delta-Architect/SKILL.md) | `DOM-03` | `NK-Builder-Agent` | Realizza applicazioni Full-Stack, interfacce Frontend (`React/Next/Tailwind`) e modifiche rapide. |
| **`[6]`** | [NK-Security-Auditor](../.agents/skills/NK-Security-Auditor/SKILL.md) | `DOM-04` | `NK-Security-DAST-Auditor` | Ispeziona la sicurezza statica SAST (`L1/L2/L3`) e verifica i flag CLI (`CoVe`). |
| **`[7]`** | [NK-Oracle-Evaluator](../.agents/skills/NK-Oracle-Evaluator/SKILL.md) | `DOM-04` | `NK-RSI-Auditor` | Controlla i 6 Gate di revisione a freddo, l'Holdout Set B e la struttura DOM HTML5. |
| **`[8]`** | [NK-Dynamic-Sandbox-StressTester](../.agents/skills/NK-Dynamic-Sandbox-StressTester/SKILL.md) | `DOM-04` | `NK-Security-DAST-Auditor` | Esegue stress test dinamici in sandbox isolata e test Browser E2E con `chrome-devtools-mcp`. |
| **`[9]`** | [NK-Bug-Diagnostic-Engine](../.agents/skills/NK-Bug-Diagnostic-Engine/SKILL.md) | `DOM-04` | `NK-Security-DAST-Auditor` | Localizza la causa radice dei bug con formula SBFL Ochiai e filtra i falsi positivi. |
| **`[10]`** | [NK-Plan-Aligner](../.agents/skills/NK-Plan-Aligner/SKILL.md) | `DOM-01` | `NK-Specifier-Agent` | Verifica l'allineamento 1:1 dei 4 documenti di progetto prima dell'avvio dei lavori. |
| **`[11]`** | [NK-State-Router](../.agents/skills/NK-State-Router/SKILL.md) | `DOM-01` | `NK-RSI-Auditor` | Controlla l'assenza di cicli nel grafo delle attività (DAG di Kahn) e gli hash SHA-256. |
| **`[12]`** | [NK-Scribe](../.agents/skills/NK-Scribe/SKILL.md) | `DOM-05` | `NK-Scribe-Agent` | Mantiene aggiornati i manuali, la mappa del codice, le patch notes e i rilasci Git. |
| **`[13]`** | [NK-Episodic-Memory-Engine](../.agents/skills/NK-Episodic-Memory-Engine/SKILL.md) | `DOM-05` | `NK-Scribe-Agent` | Gestisce la memoria a 3 livelli (`ARCH`, `SEC`, `OPS`, `DEVX`) e il recupero ibrido RRF. |
| **`[14]`** | [NK-Session-Controller](../.agents/skills/NK-Session-Controller/SKILL.md) | `DOM-01` | Regista Principale | Supervisiona la sessione, il passaggio di consegne zero-amnesia e la convergenza RSI. |

### 5.4 Architettura dei 34 Script del Motore (`scripts/`) e Suite di Test (`253/253 PASS`)

I `34` moduli indicizzati in `scripts/` (`36` file Python inclusi gli schemi IPC) sono raggruppati in 5 aree operative:
1. **Avvio, Routing e Governance (`DOM-01`):** `nk_session_bootstrap.py`, `nk_registry_indexer.py`, `vibe_sprint_router.py`, `nk_hook_gate.py` e `win32_2pc_engine.py`. Include inoltre `nk_context_sentry.py`, `nk_active_runtime_sentinel.py`, `nk_compliance_checker.py` e `nk_swarm_messenger.py`.
2. **Mappatura e Progetti Esterni (`DOM-02`):** `external_project_scaffolder.py` crea nuove app isolate in `NK_External_Projects/`. Include `ast_repo_mapper.py` e `env_capability_probe.py`.
3. **Costruzione, Riparazione e Cache (`DOM-03`):** `auto_heal_pipeline.py`, `healing_snapshot_rollback.py`, `invisible_healing_loop.py`, `platform_runner.py`, `safe_cleanup_dev_servers.py`, `deterministic_api_cache.py`, `async_heartbeat_signaler.py`.
4. **Sicurezza, Sandbox e Convergenza RSI (`DOM-04`):** `ast_guard_validator.py`, `rsi_convergence_engine.py` e `nk_transcript_tools.py`. Include `dast_sandbox_runner.py`, `sbfl_engine.py`, `sbfl_pytest_bridge.py` e `oracle_evaluator_l3.py`.
5. **Memoria, Baseline e Passaggio di Consegne (`DOM-05`):** `memory_3tier_engine.py`, `quality_baseline_manager.py`, `preflight_health_check.py` e `nk_session_handoff.py`. Include `nk_auto_inning.py`, `micro_hud_renderer.py` e i contratti in `scripts/schemas/`.
6. **253 Test Reali Zero-Mock (`245` Baseline in `tests/`):** `24` moduli verificano ogni script, confine hardware, guardia SAST e rollback 2PC. La suite certifica il **`100.0%` (`253/253 PASS`)**.

---

## 📈 6. Cosa Cambia dalla Versione 4 alla Release v5.0.0-STE100-Unified (I Miglioramenti Strutturali)

La release `v5.0.0-STE100-Unified` rappresenta il consolidamento Clean-Slate dell'architettura rispetto alla serie `4.x`:

| Area Architetturale | Versione 4.x (`v4.7.0` / `v4.8.0`) | Release `v5.0.0-STE100-Unified` |
| :--- | :--- | :--- |
| **Suite di Test Permanenti** | `245` test di baseline con possibili attriti sui workspace temporanei | **`253/253 PASS` (`100.0%`)** su `24` moduli e `14` invarianti `GT-01..GT-14` |
| **Backup Memoria a 3 Livelli** | Backup `.bak_N` condivisi nella cartella locale del motore | **Isolamento Crittografico (`ws_<sha256_12>`)** tra produzione e sandbox di test |
| **Verifica Manifesto e Cache O(1)** | Verifica `Fast-Stat` in `~24.94..41.8 ms` e versione unica | **Separazione Schema vs Release** e verifica **`< 1.0 ms` in cache** su Google Drive |
| **Igiene `.staging/` post-Commit** | Possibili cartelle `__pycache__` residue dopo i test in staging | **Auto-Pulizia Bytecode `.pyc`** integrata nel commit atomico `Win32 2PC` |
| **Purezza AST e Telemetria** | Presenza di helper inutilizzati e vecchi report di progetti esterni | **Zero Dead-Code (`63/63 PASS`)** e `nk_tracking/` bonificato al `100%` |
| **Allineamento Costituzionale** | Riferimenti di versione distribuiti tra `v4.6.0`, `v4.7.0` e `v4.8.0` | **Unificazione `1:1` a `v5.0.0`** su `16` skill, `5` sub-agenti, Genoma e pacchetto `.zip` |

### I 6 Miglioramenti Strutturali nel Dettaglio
1. **Suite Permanente al `100%` (`253/253 PASS` su `24` moduli):** elimina ogni regressione e copre i `14` invarianti `GT-01..GT-14`.
2. **Isolamento Crittografico dei Backup Memoria (`ws_<sha256_12>`):** separa i backup di produzione dalle sandbox con guardia sui file vuoti.
3. **Separazione Contratto Schema vs Release e Cache `O(1)` (`< 1.0 ms`):** distingue `MANIFEST_VERSION` e `RELEASE_VERSION` con verifica istantanea (`< 1 ms` vs `41.8 ms`).
4. **Auto-Pulizia Bytecode `.pyc` nel Commit Atomico `Win32 2PC`:** rimuove le cartelle `__pycache__` e lascia `.staging/` immacolata (`.gitkeep`).
5. **Zero Dead-Code (`63/63 PASS` su `ast_guard_validator.py`) e Bonifica `nk_tracking/`:** elimina i simboli morti in `scripts/` e rimuove i riferimenti esterni.
6. **Unificazione Costituzionale `v5.0.0` ($\Delta_k = 0, Q = 100.0$):** allinea `1:1` le `16` skill, i `5` sub-agenti, il Genoma e `NK_Hub_OneClick_Package.zip`.

---
*Nexus Keystone Hub (`v5.0.0-STE100-Unified`) | Certificato `253/253 PASS` (`245` Baseline) Zero-Mock | $\Delta_k = 0, Q(S_k) = 100.0$*

---

# 🇬🇧 English Version : Nexus Keystone Hub (NK-Hub v5.0.0-STE100-Unified)
## The Organized, Safe, and Autonomous Multi-Agent Development Environment for Google Antigravity

> 🌍 **Language / Lingua:** **[🇮🇹 Vai alla Versione Italiana](#-1-presentazione-veloce-in-90-secondi-lhook-perch%C3%A9-nasce-e-cosa-fa)** | **[📖 1-Click ZIP Install Guide](../nk_docs_and_setup/GUIDA_INSTALLAZIONE.md)** | **[🗺️ Library Map](../nk_docs_and_setup/00_MAPPA_LIBRERIA_NK.md)**
>
> 📦 **1-CLICK DOWNLOAD OF THE COMPLETE ENVIRONMENT (`.ZIP` WITH INSTALL GUIDE):**  
> 👉 **[Download NK_Hub_OneClick_Package.zip (Official Release v5.0.0-STE100-Unified)](https://github.com/erbaldo86/NK-Hub/releases/download/v5.0.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** *(or [Direct Download from Repository](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip))*

---

## ⚡ 1. 90-Second Quick Look (The Hook: Why It Was Built & How It Works)

### Why was `NK-Hub` created?
When you build software with AI (Vibe Coding), the first few minutes feel effortless. As soon as a project grows, however, three recurring problems slow everything down:
1. **Messy folders:** system files, scripts, tests, and user projects end up scattered or duplicated in the same folder.
2. **Edits that break working code:** the AI modifies your live files directly without testing them in a safe area first.
3. **Context loss and fake test passes:** during long sessions, the AI forgets rules. It may also weaken tests to make them turn green.

**`NK-Hub` was built to eliminate all three problems.** It turns Google Antigravity into an organized control center with `5` specialized Sub-Agents. The team plans, builds, and tests code inside `.staging/`. It promotes changes only when `100%` of real checks pass.

### 💬 30-Second Live Example: How You Interact with `NK-Hub`
> 1. **You type in chat (or speak via voice dictation):**  
>    *"Create a web application to manage customer quotes and export them as PDF."*
> 2. **`NK-Hub` immediately shows the L0 Confirmation Mirror (`Gate L0`):**  
>    *"Goal understood: I will scaffold the isolated app in `NK_External_Projects/QuoteApp`. Next, I will build the database, UI, and PDF exporter in staging. Confirm with 1 click?"*
> 3. **You click `Confirm`:**  
>    The agent team builds the application in `.staging/` and runs security tests. It heals errors automatically and delivers the verified project into your folder.

### Immediate Benefits at a Glance

| What Usually Happens with a Standard AI Agent | What Happens with `NK-Hub` |
| :--- | :--- |
| Cluttered root folder mixing engine and user apps | **Clean Two-Folder Library:** `NK_Hub/` (the engine) and `NK_External_Projects/` (your apps) |
| The AI starts immediately and may misunderstand intent | **1-Click L0 Gate:** summarizes requirements upfront and starts only on your confirmation |
| Direct edits on live files risk breaking working code | **Isolated `.staging/` + Atomic Commit:** live files are never left in a half-broken state |
| One single agent tries to do everything and loses focus | **5 Native Sub-Agents:** the agent that writes code is separated from the agents that audit it |
| Risk of the AI weakening tests to fake success | **Anti-Gaming `oracle-lock` Seal:** tests are cryptographically locked against tampering |

---

## 📦 2. Quick Installation Guide (For 1-Click ZIP Users)

The **[NK_Hub_OneClick_Package.zip](https://github.com/erbaldo86/NK-Hub/releases/download/v5.0.0-STE100-Unified/NK_Hub_OneClick_Package.zip)** archive includes the entire organized environment and the bilingual [GUIDA_INSTALLAZIONE.md](../nk_docs_and_setup/GUIDA_INSTALLAZIONE.md).

### Setup in 3 Easy Steps
1. **Extract the ZIP:** download `NK_Hub_OneClick_Package.zip` and extract it into your main workspace folder (for example `Antigravity/`). You will see two clean folders: `NK_Hub` and `NK_External_Projects`.
2. **Run the Automated Installer:** open PowerShell inside `NK_Hub` and run:
   ```powershell
   cd NK_Hub
   .\nk_docs_and_setup\install.ps1
   ```
   *(On Linux/macOS run `./nk_docs_and_setup/install.sh`. The script installs dependencies from `nk_docs_and_setup/requirements.txt`, verifies the O(1) index in `< 1.0 ms`, and runs the `253` certified tests).*
3. **Launch the Engine in Antigravity:** open the folder in Google Antigravity and type in chat:
   ```text
   start nk
   ```
   *(or `"avvia ambiente nk"`).* The **15-Node Control Dashboard (`[0]`..`[14]`)** will appear in under `50 ms`.

---

## 🎯 3. Designed for Two Audiences: Vibe Coders vs. Expert Engineers + 6 Core Pillars

`NK-Hub` is built on two levels. It is effortless on the surface for creators and mathematically rigorous underneath for senior engineers.

### 🧑‍💻 A. For Non-Technical / Vibe Coding Users (Effortless Creation)
You do not need programming experience or terminal commands. Here is how you use it every day:

| What You Want to Do | What You Type in Antigravity Chat | What `NK-Hub` Does Automatically for You |
| :--- | :--- | :--- |
| **Start the environment** | `"start nk"` or `"avvia ambiente nk"` | Verifies system health in `< 1.0 ms` and opens the interactive 15-node dashboard. |
| **Create a brand-new app** | *"I want an app to track grant deadlines and alerts"* | Creates a clean folder in `NK_External_Projects/`, designs UI and database, and builds the app. |
| **Make a quick visual tweak** | *"Add a green button to export the table to Excel"* | Activates the fast lane (`Mode C`), stages and verifies the edit in under half a second. |
| **Fix an error** | *"Clicking Save shows an error, can you fix it?"* | Pinpoints the exact faulty line, repairs it in `.staging/`, and updates your app safely. |

* **Speak or type naturally:** if voice dictation merges words together, the built-in voice normalizer fixes them before routing.
* **Zero risk of breaking the engine:** your projects always live inside `NK_External_Projects/`, and every edit is tested in `.staging/` first.

---

### 🛠️ B. For Experienced Developers & Senior Architects (Why Use `NK-Hub`?)
If you are an experienced engineer wondering what `NK-Hub` adds over a standard AI coding assistant:

| Standard AI Coding Assistant Limitation | Deterministic Solution Engineered in `NK-Hub` |
| :--- | :--- |
| **Monolithic Context & Context Rot** | **2-Tier Hub-and-Spoke Topology:** `5` isolated Native Sub-Agents with independent context windows and automatic external skill filtering (`-7,042` tokens/turn). |
| **Self-Grading & Reward Hacking (*Goodhart's Law*)** | **Hardware `GT-14` Boundary + `oracle-lock`:** Auditors run with `enable_write_tools: false` and test suites are sealed in `SHA-256` before build execution. |
| **Partial Writes & Working Tree Corruption** | **Atomic `Win32 2PC` Transactions:** promotion from `.staging/` is guarded by a 64-bit Kernel Named Mutex with full batch rollback on failure. |
| **High Latency on Small Edits** | **`Mode C` Fast-Bypass (`< 500 ms`) & `OPT-11` Cache (`< 1.0 ms`):** AST depth triage (`max_depth <= 1`, `<= 150` LOC) saving `71.9%` of tokens. |
| **Massive Traceback Dumps in Debugging** | **`SBFL Ochiai` Fault Localization (`< 80` Tokens):** spectral fault localization with AST Def-Use slicing and monotonic SHA-256 snapshots. |

---

### 🌟 C. The 6 Core Pillars of `NK-Hub` (Key Engineering Advantages)

1. **Clean Physical Library Layout (`NK_Hub` + `NK_External_Projects` + `nk_docs_and_setup`):**
   Every file has a single physical copy and logical home. Manuals live in `nk_docs_and_setup/`, plans in `nk_genome/`, telemetry in `nk_tracking/`, scripts in `scripts/`, and user apps in `NK_External_Projects/`.
2. **Hardware Separation Between Builders and Auditors (`GT-14`):**
   The `5` Native Sub-Agents enforce strict YAML permissions: `NK-Security-DAST-Auditor` and `NK-RSI-Auditor` run with `enable_write_tools: false`, and all sub-agents enforce `enable_subagent_tools: false` (`RULE-01`).
3. **1-Click L0 Gate & `Mode C` Fast-Bypass (`< 500 ms`, `-71.9%` Token Usage):**
   Before execution, the router compiles a strict Pydantic v2 contract (`MetaPromptGateContract`) with a `SHA-256` intent hash. Edits under `150` lines run via Fast-Bypass in `~65 ms`.
4. **$100\times$ Epistemic Honesty & `SAST-GAMING-D01..D04` Static Guards:**
   The AST validator blocks reading `PYTEST_CURRENT_TEST` (`D01`) or inspecting runtime stack frames (`D02`). It also blocks hardcoded host fixtures (`D03`) and branching on test dataset size (`D04`).
5. **Mathematical Tensor-RSI Convergence ($\Delta_k = 0, Q(S_k) = 100.0$) & `Win32 2PC` Commit:**
   At each iteration $k$, the engine evaluates the defect vector $\Delta_k(p)$ and fitness $Q(S_k)$:
   $$\Delta_k(p) = 100 D_k + 20 E_{\text{PoC},k} + w_{\text{SAST}}^{(p)} \text{SAST}_k + 12 D_{\text{sem},k} + w_{\text{test}}^{(p)} (T_{\text{fail},k} + C_k) + w_{H}^{(p)} H_k + w_{M}^{(p)} M_k + w_{L}^{(p)} L_k + w_{G}^{(p)} G_k$$
   Code is promoted from `.staging/` to production via `win32_2pc_engine.py` exclusively when $\Delta_k = 0$ and $Q(S_k) = 100.0$.
6. **Measured SLA Benchmarks on Windows 11 64-bit (`OPT-1..OPT-11`):**
   * **Fast-Stat Session Bootstrap (`nk_session_bootstrap.py`):** `18..28 ms` (target `< 50 ms`).
   * **O(1) Registry Verification with `OPT-11` Cache (`nk_registry_indexer.py --verify`):** `< 1.0 ms` cached (`41.8 ms` cold).
   * **Taxonomic Lookup & L0 Routing (`vibe_sprint_router.py`):** `1.08..2.12 ms` (target `< 15 ms`).
   * **Full Suite of `253` Real Zero-Mock Tests (`245` baseline, `24` modules in `tests/`):** `100.0% PASS` (`253/253`).

---

## 🚀 4. Real-World Case Study: How NK-Hub Co-Designed and Built a Full ERP/CRM in a Single Overnight Session

This real-world case study demonstrates how `NK-Hub` turns a complex vision into production-ready software. It documents the interactive design in `NK-Studio-Lab-Progettazione` and the autonomous build of `NK-Studio-CRM`.

### Phase 1: Interactive Co-Design with the User (`User` + `NK-Hub`)
Before writing code, the user collaborates interactively with `NK-Hub`. Through guided exchanges with `NK-Ideator`, `NK-App-UX-Architect`, `NK-Backend-Architect`, and `NK-Plan-Aligner`, the model co-designs the full blueprint:
* **Tax and Legal Market Analysis (`TAX` and `LEGAL`):** maps real operational workflows for multidisciplinary professional firms.
* **4-Box Strategic Architecture:** separates unified directory, smart import engine, instant communications, and data vault.
* **`NK Clarity v2.0` Design System:** defines a high-readability visual hierarchy featuring `Calm Daylight` and `Dark Switcher` modes.
* **Blueprint for `5` Future Add-Ons:** prepares clean extension sockets for `Bandi Bridge`, `Parcelle`, `Scadenze`, `Antiriciclaggio/GDPR`, and `Circolari/PEC`.

### Phase 2: 1-Click Confirmation and Autonomous Overnight Build
Once the user approves the `Gate L0` plan with one click, the `5` Native Sub-Agents (`Mode A`) take over. The team works autonomously in a single continuous overnight session inside `.staging/`:
1. **Backend and Hardened Database:** builds the `FastAPI` backend and `SQLite3 WAL` database. Includes a conflict-of-interest radar and a `.zip` backup vault.
2. **Smart Engines and 1-Click Connectors:** implements polymorphic `Pydantic v2` models and the `SmartMergeEngine` (`.vcf` Apple/Google, `.csv`, `XML FatturaPA`). Adds 1-Click connectors (`Gmail`, `Outlook`, `PEC`, `WhatsApp`, `.ics`) and the 5-socket Add-On event bus.
3. **Web UI and Zero-Mock Certification:** builds the `NK Clarity v2.0` web interface (`Calm Daylight` and `Dark Switcher`). Passes **`36/36` automated Zero-Mock tests** (`unit`, `E2E`, stress `S1..S4`) and delivers the complete ERP/CRM ready via `start_crm.bat`.

---

## 🔬 5. Dedicated Technical Reference: Agents, 16 Skills & 34 Core Scripts

```mermaid
flowchart LR
    U["User Prompt (Text / Voice)"] --> R["L0 Gate + O(1) Router (1.19 ms)"]
    R -->|"Mode C <= 150 LOC"| FB["Fast-Bypass .staging/ + Vibe-Check (<500 ms)"]
    R -->|"Mode A / B / D"| S["5 Native Sub-Agents + 16 SKILL.md Playbooks"]
    FB --> C["Atomic Win32 2PC Commit (Delta_k = 0, Q = 100.0)"]
    S --> A["6-Gate Cold Audit + SHA-256 Oracle-Lock"]
    A --> C
```

### 5.1 The 4 Automatic Operating Modes (`scripts/vibe_sprint_router.py`)

| Mode | Trigger Condition | Active Execution Lane | Verification Gates |
| :--- | :--- | :--- | :--- |
| **`Mode D` (Discovery & Audit)** | Read-only questions, audits, benchmarks, MCP search | `NK-Specifier-Agent` / `NK-RSI-Auditor` (Read-Only) | O(1) Lookup (`< 1.0 ms`) + MCP Connectors |
| **`Mode C` (Vibe-Sprint Fast Lane)** | Quick UI or script tweaks (`<= 150` LOC) | Fast-Bypass or `NK-Builder-Agent` in `.staging/` | AST Guard (`D01..D04`) + `--vibe-check` (`< 500 ms`) |
| **`Mode B` (CRV Lite Bugfix)** | Targeted backend bugfix or multi-file refactor | `NK-Builder-Agent` + `NK-Security-DAST-Auditor` | Staging + `oracle-lock` + `SBFL Ochiai` Auto-Heal |
| **`Mode A` (Sovereign Full-Stack)** | New external app or major architectural evolution | Full 5-Agent Native Swarm (`DOM-02..DOM-05`) | 5-Turn Plan + 6-Gate Cold Audit + Win32 2PC |

### 5.2 The 5 Pre-Registered Native Sub-Agents (`.agents/agents/*/agent.md`)

| Native Sub-Agent | Domain | Hardware Permissions (`GT-14`) | Role & Authorized Write Perimeter |
| :--- | :---: | :--- | :--- |
| **[NK-Specifier-Agent](../.agents/agents/NK-Specifier-Agent/agent.md)** | `DOM-02` | `write: true`, `mcp: true` | Designs concepts, UX/UI systems, backend architectures, and plans inside `nk_genome/*`. |
| **[NK-Builder-Agent](../.agents/agents/NK-Builder-Agent/agent.md)** | `DOM-03` | `write: true`, `mcp: false` | Writes and heals Python backend, React/Next.js UI, and skills strictly inside `.staging/*`. |
| **[NK-Security-DAST-Auditor](../.agents/agents/NK-Security-DAST-Auditor/agent.md)** | `DOM-04` | **`write: false`** (Read-Only) | Runs SAST anti-gaming checks, DAST sandbox stress tests, Browser E2E checks, and SBFL RCA. |
| **[NK-RSI-Auditor](../.agents/agents/NK-RSI-Auditor/agent.md)** | `DOM-04` | **`write: false`** (Read-Only) | Verifies the 6 Cold Review Gates, Kahn DAG integrity, and mathematical convergence ($\Delta_k = 0$). |
| **[NK-Scribe-Agent](../.agents/agents/NK-Scribe-Agent/agent.md)** | `DOM-05` | `write: true`, `mcp: false` | Updates SSOT documentation, `repo_map.md`, `PATCH_NOTES.md`, and the 3-Tier memory store. |

### 5.3 Catalog of the 16 Procedural Skill Playbooks (`.agents/skills/NK-*/SKILL.md`)

| Node | Playbook Skill Name | Domain | Executing Sub-Agent | Procedural Responsibility |
| :---: | :--- | :---: | :--- | :--- |
| **Hub** | [NK-Master-Hub](../.agents/skills/NK-Master-Hub/SKILL.md) | `DOM-01` | Main Agent (Hub) | Orchestrates 2-Tier routing, `oracle-lock` sealing, and final Win32 2PC promotion. |
| **`[0]`** | [NK-Ideator](../.agents/skills/NK-Ideator/SKILL.md) | `DOM-02` | `NK-Specifier-Agent` | Conceptual ideation (`idea_canvas.md`), SCAMPER analysis, and `tavily-mcp` discovery. |
| **`[1]`** | [NK-App-UX-Architect](../.agents/skills/NK-App-UX-Architect/SKILL.md) | `DOM-02` | `NK-Specifier-Agent` | UX/UI macro-architecture, 8px/HSL Design System, and interactive widgets. |
| **`[2]`** | [NK-Backend-Architect](../.agents/skills/NK-Backend-Architect/SKILL.md) | `DOM-02` | `NK-Specifier-Agent` | Backend DAG topology, Pydantic v2 contracts, OpenAPI 3.0, and `firebase-mcp-server`. |
| **`[3]`** | [NK-Agent-Instruction-Forge](../.agents/skills/NK-Agent-Instruction-Forge/SKILL.md) | `DOM-02` | `NK-Builder-Agent` | Authors and updates ASD-STE100 skills and agent definitions with `--sync`. |
| **`[4]`** | [NK-Python-Async-Builder](../.agents/skills/NK-Python-Async-Builder/SKILL.md) | `DOM-03` | `NK-Builder-Agent` | Builds async Python backends, SQLite WAL persistence, and self-healing loops in `.staging/`. |
| **`[5]`** | [NK-Delta-Architect](../.agents/skills/NK-Delta-Architect/SKILL.md) | `DOM-03` | `NK-Builder-Agent` | Builds Full-Stack apps, Frontend UIs (`React/Next/Tailwind`), and surgical refines. |
| **`[6]`** | [NK-Security-Auditor](../.agents/skills/NK-Security-Auditor/SKILL.md) | `DOM-04` | `NK-Security-DAST-Auditor` | Performs L1/L2/L3 static security audits and CoVe CLI flag verification. |
| **`[7]`** | [NK-Oracle-Evaluator](../.agents/skills/NK-Oracle-Evaluator/SKILL.md) | `DOM-04` | `NK-RSI-Auditor` | Evaluates Cold Review Gates 1-6, Blind Holdout Set B, and L3 HTML5 DOM compliance. |
| **`[8]`** | [NK-Dynamic-Sandbox-StressTester](../.agents/skills/NK-Dynamic-Sandbox-StressTester/SKILL.md) | `DOM-04` | `NK-Security-DAST-Auditor` | Runs isolated DAST sandbox stress tests and live Browser E2E via `chrome-devtools-mcp`. |
| **`[9]`** | [NK-Bug-Diagnostic-Engine](../.agents/skills/NK-Bug-Diagnostic-Engine/SKILL.md) | `DOM-04` | `NK-Security-DAST-Auditor` | Pinpoints root causes via SBFL Ochiai (`< 80` tokens) and filters false bug reports. |
| **`[10]`** | [NK-Plan-Aligner](../.agents/skills/NK-Plan-Aligner/SKILL.md) | `DOM-01` | `NK-Specifier-Agent` | Certifies 1:1 alignment across the 4 genome planning documents before build handoff. |
| **`[11]`** | [NK-State-Router](../.agents/skills/NK-State-Router/SKILL.md) | `DOM-01` | `NK-RSI-Auditor` | Verifies Kahn DAG topological order and detects SHA-256 file drift. |
| **`[12]`** | [NK-Scribe](../.agents/skills/NK-Scribe/SKILL.md) | `DOM-05` | `NK-Scribe-Agent` | Synchronizes SSOT documentation, AST `repo_map.md`, `PATCH_NOTES.md`, and Git releases. |
| **`[13]`** | [NK-Episodic-Memory-Engine](../.agents/skills/NK-Episodic-Memory-Engine/SKILL.md) | `DOM-05` | `NK-Scribe-Agent` | Manages 3-Tier episodic memory (`ARCH`, `SEC`, `OPS`, `DEVX`) and hybrid RRF recall. |
| **`[14]`** | [NK-Session-Controller](../.agents/skills/NK-Session-Controller/SKILL.md) | `DOM-01` | Main Agent (Hub) | Supervises session lifecycle, zero-amnesia handoff, and Tensor-RSI convergence. |

### 5.4 Overview of the 34 Indexed Python Modules (`scripts/`) & Certified Test Suite (`253/253 PASS`)

1. **Governance, Routing & Atomic 2PC (`DOM-01`):** `nk_session_bootstrap.py`, `nk_registry_indexer.py`, `vibe_sprint_router.py`, `nk_hook_gate.py`, and `win32_2pc_engine.py`. Also includes `nk_context_sentry.py`, `nk_active_runtime_sentinel.py`, `nk_compliance_checker.py`, and `nk_swarm_messenger.py`.
2. **Architecture & Project Scaffolding (`DOM-02`):** `external_project_scaffolder.py` (scaffolds isolated apps in `NK_External_Projects/`), `ast_repo_mapper.py` (PageRank AST mapper & `< 0.20s` `--symbol` query), `env_capability_probe.py`.
3. **Build, Self-Healing & Caching (`DOM-03`):** `auto_heal_pipeline.py`, `healing_snapshot_rollback.py`, `invisible_healing_loop.py`, `platform_runner.py`, `safe_cleanup_dev_servers.py`, `deterministic_api_cache.py`, `async_heartbeat_signaler.py`.
4. **Security, DAST Sandbox & Tensor-RSI (`DOM-04`):** `ast_guard_validator.py`, `rsi_convergence_engine.py`, and `nk_transcript_tools.py`. Also includes `dast_sandbox_runner.py`, `sbfl_engine.py`, `sbfl_pytest_bridge.py`, and `oracle_evaluator_l3.py`.
5. **3-Tier Memory, Baseline & Handoff (`DOM-05`):** `memory_3tier_engine.py`, `quality_baseline_manager.py`, `preflight_health_check.py`, `nk_session_handoff.py`, `nk_auto_inning.py`, `micro_hud_renderer.py`, and Pydantic v2 contracts in `scripts/schemas/`.
6. **253 Zero-Mock Tests (`245` Baseline in `tests/`):** `24` orthogonal test modules verify every script, sub-agent boundary, SAST guard, and 2PC rollback. The suite passes at **`253/253 PASS` (`100.0%`)**.

---

## 📈 6. What Changed from Version 4 to Release v5.0.0-STE100-Unified (Structural Improvements)

Release `v5.0.0-STE100-Unified` delivers the Clean-Slate consolidation of the framework over the `4.x` series:

| Architectural Area | Version 4.x (`v4.7.0` / `v4.8.0`) | Release `v5.0.0-STE100-Unified` |
| :--- | :--- | :--- |
| **Permanent Test Suite** | `245` baseline tests with occasional temp-workspace friction | **`253/253 PASS` (`100.0%`)** across `24` modules and `14` invariants `GT-01..GT-14` |
| **3-Tier Memory Backups** | Shared `.bak_N` backups inside the local engine folder | **Cryptographic Isolation (`ws_<sha256_12>`)** between production and test sandboxes |
| **Manifest & O(1) Cache** | `Fast-Stat` check in `~24.94..41.8 ms` with single version field | **Schema vs Release Separation** and **`< 1.0 ms` cached check** on Google Drive |
| **Post-Commit `.staging/` Hygiene** | Possible leftover `__pycache__` folders after staging tests | **Automatic `.pyc` Bytecode Purge** inside `Win32 2PC` atomic commit |
| **AST Purity & Telemetry** | Residual unused helpers and legacy external project reports | **Zero Dead-Code (`63/63 PASS`)** and `100%` sanitized `nk_tracking/` |
| **Constitutional Alignment** | Version strings split across `v4.6.0`, `v4.7.0`, and `v4.8.0` | **1:1 `v5.0.0` Unification** across `16` skills, `5` sub-agents, Genome, and `.zip` bundle |

### The 6 Structural Improvements in Detail
1. **`100%` Permanent Test Suite (`253/253 PASS` across `24` modules):** eliminates all regressions and covers the `14` invariants `GT-01..GT-14`.
2. **Cryptographic Isolation of Memory Backups (`ws_<sha256_12>`):** separates production backups from test sandboxes and guards against `0`-byte overwrites.
3. **Schema vs Release Separation & `O(1)` Cache (`< 1.0 ms`):** decouples `MANIFEST_VERSION` from `RELEASE_VERSION` with `< 1.0 ms` cached verification.
4. **Automatic `.pyc` Bytecode Cleanup in `Win32 2PC` Atomic Commit:** purges `__pycache__` folders during promotion so `.staging/` stays immaculate.
5. **Zero Dead-Code (`63/63 PASS` on `ast_guard_validator.py`) & `nk_tracking/` Sanitization:** removes dead symbols in `scripts/` and purges external project artifacts.
6. **`v5.0.0` Constitutional Unification ($\Delta_k = 0, Q = 100.0$):** aligns `1:1` all `16` skills, `5` sub-agents, the Genome, and `NK_Hub_OneClick_Package.zip`.

---
*Nexus Keystone Hub (`v5.0.0-STE100-Unified`) | Certified `253/253 PASS` (`245` Baseline) Zero-Mock | $\Delta_k = 0, Q(S_k) = 100.0$*
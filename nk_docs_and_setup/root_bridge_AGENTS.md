# Bridge di Scoperta Root: Ecosistema Antigravity (NK Hub Generation v1.0.0-Generation)

> **Ambito:** File ponte di livello superiore per l'instradamento immediato verso `NK_Hub`.  
> **Root Sovrana:** `NK_Hub` (dentro il workspace corrente).  
> **Costituzione Completa:** `NK_Hub/.agents/AGENTS.md`.  
> **Milestone Anchor:** `NK-GEN-1.0.0` | **Profilo:** `NK_MODEL_PROFILE=generation` (fallback `carbon`).  
> **Standard Linguistico:** Italiano Tecnico ASD-STE100 (`[RULE-STE100]`, frasi `<= 20` parole).

---

## 1. Indirizzamento Immediato Zero-Discovery (`O1`)
* La root operativa sovrana di `NK_Hub` risiede nella cartella `NK_Hub/` del workspace.
* La costituzione completa del sistema risiede in `NK_Hub/.agents/AGENTS.md`.
* I manifesti `.agents/skills.json` e `.agents/plugins.json` montano 11 skill, 6 sub-agenti nativi e `nk-gate`.
* Gli 11 playbook risiedono in `NK_Hub/.agents/skills/`.
* I `6` sub-agenti nativi risiedono in `NK_Hub/.agents/agents/` e nel plugin `nk-gate`.
* I progetti applicativi attivi risiedono in `NK Proget/Locale/<Nome>/` (compatibile con `NK_External_Projects/<Nome>/`).
* La cartella `NK Proget/Online/` è un mirror di release in sola lettura.
* Nessun agente esegue scansioni esplorative nella directory padre prima del bootstrap.

## 2. Bootstrap Fast-Stat e Onboarding Single-Pass (`O2` + `O3`)

### [RULE-00.4] SESSION_BOOTSTRAP_ENFORCEMENT
* All'inizio del turno esegui `python -B -u NK_Hub/scripts/nk_session_bootstrap.py`.
* Imposta `NK_MODEL_PROFILE=generation` con fallback automatico su `carbon` per compatibilità.
* La verifica `Fast-Stat` valida la root con cache cross-conversazione (`TTL 900s` su `root_mtime` invariato).
* Nessuna operazione procede se lo script di bootstrap restituisce stato `FAIL`.

### [RULE-00.5] UNIFIED_ONBOARDING_DASHBOARD_MANDATE
* I `16` trigger di avvio attivano `ONBOARDING_BYPASS_VERIFIED` in un singolo passaggio CLI.
* Trigger legacy (`8`): `"avvia ambiente nk"`, `"avvia nk hub"`, `"avvia nk"`, `"avvia hub"`, `"start nk"`, `"start hub"`, `"attiva nk"`, `"attiva ambiente nk"`.
* Trigger Generation (`8`): `"avvia generation"`, `"avvia nk generation"`, `"avvia nk hub generation"`, `"avvia ambiente generation"`, `"start generation"`, `"start nk generation"`, `"attiva generation"`, `"attiva ambiente generation"`.
* Dopo `ONBOARDING_BYPASS_VERIFIED`, esponi subito la dashboard `NK-Orchestrator` a 10 nodi (`[0]` fino a `[9]`).
* Non invocare un secondo round-trip CLI su `vibe_sprint_router.py` per i trigger di avvio.
* Includi sempre in calce la guida `Modalità Diretta` (`[0]`..`[9]`) e `Modalità Goal-Driven`.

## 3. Regole Invarianti e Sicurezza I/O Windows
* Per prompt operativi non esenti esegui `python -B -u NK_Hub/scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>"`.
* Se approvi un piano aggiungendo nuovi requisiti, riesegui `--meta-prompt-gate` e mostra lo Specchio L0.
* Opera in `NK_Hub/.staging/` per ogni modifica e promuovi con `NK_Hub/scripts/win32_2pc_engine.py` (`[RULE-00]`).
* Rispetta la topologia `2-Tier Hub-and-Spoke` (`[RULE-01]`) e lo standard ASD-STE100 (`[RULE-STE100]`).

### [RULE-WIN32-ISOLATED-PYTEST] NVME_ISOLATED_PYTEST_MANDATE
* Esegui `pytest` solo su NVMe locale tramite `python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated` su `%TEMP%`.
* Non avviare mai `pytest` diretto su Drive FS per evitare crash `0xC000013A` su `conhost.exe`.

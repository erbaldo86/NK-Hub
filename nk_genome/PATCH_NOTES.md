# NEXUS KEYSTONE OFFICIAL CHANGELOG E PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Release Ufficiale:** `v4.3.0-Super-Plan-Triad-RSI` (`v4.0.0-Native-Swarm-Playbooks` / `v3.0.0-STE100-Unified`)  
> **Milestone Anchor:** `NK-MS-20261024-SUPER-PLAN-TRIAD-v6.0.0-RSI`  
> **Data Consolidamento:** `2026-10-24`  
> **Stato Release:** `[NK-SUPER-BRIEF-STATUS: AUDITED_AND_CERTIFIED_v4.3.0_SOVEREIGN]`

---

## 🛡️ Release v4.3.0-Super-Plan-Triad-RSI (`SP-WS0..SP-WS13` : Super Implementation Plan v6.0-Unified-Triad-RSI) (`2026-10-24`)

La release **`v4.3.0-Super-Plan-Triad-RSI`** unifica i workstream `SP-WS0..SP-WS13` del **Super Implementation Plan v6.0-Unified-Triad-RSI**.

1. **Runtime Hook Gate e Dual-Schema Lifecycle (`scripts/nk_hook_gate.py`, `.agents/hooks.json`):**
   - Introduce il gate stdlib con sottocomandi `probe`, `write-gate`, `fasttrack`, `integrity` SHA-256 e `stop-check` sotto `50 ms`.
   - Blocca con `decision: deny` la sovrascrittura dei checkpoint in `nk_tracking/` e le modifiche distruttive a `PATCH_NOTES.md`.
   - Preserva il dual-schema in `.agents/hooks.json` su `SessionStart`, `PreToolUse`, `PostToolUse` e `Stop` con timeout entro `15` secondi.
2. **Strumenti Forensi, Oracle-Lock SHA-256 e Linter Prompt (`scripts/nk_transcript_tools.py`, `Template 11`):**
   - Implementa `locate` senza fallback cieco `st_mtime` (exit `2` `UNMEASURED`), `compliance`, `evidence`, `oracle-lock` e `lint-prompt`.
   - Valida con `lint-prompt` i prompt generati dall'IA bloccando gli anti-pattern `AP-1..AP-7` più `AP-2b` (`[RULE-00.7]`).
   - Congela e verifica gli hash SHA-256 della ground truth in `nk_tracking/oracle_lock.json` prima della fase Build (`[RULE-ORACLE-LOCK]`).
3. **Riparazione Bootstrap, Pre-Flight Schema Grounding e Suite a 98 Test (`scripts/`, `tests/test_super_plan_v6_triad.py`):**
   - Ripara `nk_session_bootstrap.py`, `nk_context_sentry.py` e `nk_active_runtime_sentinel.py` eliminando il falso allarme `RED (523 steps)`.
   - Aggiunge `validate_pydantic_catalog_records()` e `--output-json` in `ast_guard_validator.py` più la penalità `external_unstage_writes` in `nk_compliance_checker.py`.
   - Espande la suite permanente Zero-Mock a `98/98 PASS` (`100.0%`) su `26` file di test con $\Delta_k = 0$.

---

## 🛡️ Release v4.1.0-Super-Meta-Prompt-Gate (`WP13-UNIFIED` : Opus + Argon + Terza Parte) (`2026-10-21`)

La release **`v4.1.0-Super-Meta-Prompt-Gate`** unifica i brief di **Opus**, **Argon** e l'**Arbitrato di Terza Parte** nel nuovo **Livello 0 (`[RULE-00.6]`)**.

1. **Regola Costituzionale `[RULE-00.6]` e Conferma Vocale 1-Click (`AGENTS.md`, `prompt_templates.md`):**
   - Attiva di default il Gate Meta-Prompt (`CONFIRM`) su ogni comando utente con conferma 1-Click tramite `ask_question`.
   - Separa il **Livello 0 (Meta-Prompt e Intent Brief `IB-*`)** dal **Livello 1-4 (`implementation_plan.md` tecnico)**.
   - Include nel Template `0` i requisiti `R1..Rn`, `Correzioni vocali recepite`, `Fuori ambito` e `intent_hash_sha256`.
2. **Motore Morfologico STT, FSM Anti-Loop e Contratto IPC (`vibe_sprint_router.py`, `nk_ipc_contracts.py`):**
   - Introduce `MetaPromptGateContract` (`strict=True, extra="forbid", frozen=True`) con `5` stati FSM e TTL `1.800` secondi.
   - Ripara il falso positivo alla riga `626` di `vibe_sprint_router.py` escludendo i sostantivi astratti (`implementazione`, `valutazione`).
   - Aggiunge `normalize_voice_stt_input()` per separare i token `CamelCase` fusi (`primaLa`) e `is_gate_exempt()` per `5` esenzioni.
3. **Bootstrap Fast-Stat, Tracciabilità `R1..Rn` e Suite a 90 Test (`nk_session_bootstrap.py`, `tests/`):**
   - Verifica `meta_prompt_gate_enabled: true` in `nk_session_bootstrap.py` (`< 25 ms`) e `session_tuning_params.json`.
   - Impone la copertura `100%` di `R1..Rn` in `NK-Plan-Aligner` e l'indicizzazione lessicale `DEVX` in `NK-Episodic-Memory-Engine`.
   - Espande la suite Zero-Mock a `90/90 PASS` (`100.0%`) preservando `16` skill, `32` script e `hooks.json` (`WP8.4`).

---

## 🏛️ Release v4.0.0-Native-Swarm-Playbooks: Da Ibrido "Persona-Skill" a Router + 5 Sub-Agenti Nativi + 16 Playbook (`2026-10-18`)

La versione **`v4.0.0-Native-Swarm-Playbooks`** introduce una rifondazione architetturale completa dell'ecosistema **Nexus Keystone (`NK-Hub`)** per **Google Antigravity**. Il sistema abbandona il precedente modello ibrido per adottare la separazione netta tra **Motore Esecutivo** e **Manuale Procedurale**.

---

### 1. Cosa è Cambiato: Il Salto Architetturale (`v3.5.x` vs `v4.0.0`)

1. **Introduzione dei 5 Sub-Agenti Esecutori Nativi Pre-Registrati (`.agents/agents/*/agent.md`):**
   - Nelle versioni `v3.5.x` esisteva un solo sub-agente nativo su disco (`NK-RSI-Auditor`).
   - Gli altri nodi venivano simulati nel contesto principale o creati a runtime tramite `define_subagent`.
   - La release `v4.0.0` registra stabilmente `5` Sub-Agenti Nativi dedicati ai domini operativi `DOM-02..DOM-05`.
   - I `5` sub-agenti sono: `NK-Specifier-Agent`, `NK-Builder-Agent`, `NK-Security-DAST-Auditor`, `NK-RSI-Auditor` e `NK-Scribe-Agent`.
   - Il server Antigravity avvia ogni sub-agente in un processo isolato con finestra di contesto indipendente.
   - Questa architettura elimina il `100%` delle chiamate `define_subagent` a runtime e azzera la saturazione del contesto principale.

2. **Riconversione delle 16 Skill in Playbook Procedurali Puri (`.agents/skills/*/SKILL.md`):**
   - Nelle versioni precedenti le `16` skill contenevano istruzioni identitarie ("Sei l'agente X") mescolate a procedure operative.
   - Nella `v4.0.0` tutte le `16` skill e i `16` file ausiliari diventano Playbook Procedurali deterministici privi di conflitti.
   - Ogni Sub-Agente Nativo monta dinamicamente solo il Playbook `SKILL.md` richiesto dal task attivo.

3. **Blocco Hardware in Sola Lettura (`GT-14`) e Guardia Topologica 2-Tier (`[RULE-01]`):**
   - Gli Auditor `NK-Security-DAST-Auditor` e `NK-RSI-Auditor` impongono `enable_write_tools: false` direttamente nel manifesto YAML.
   - Il server Antigravity rimuove fisicamente gli strumenti di scrittura da questi sub-agenti prima dell'inferenza.
   - Tutti i `5` Sub-Agenti Nativi impongono `enable_subagent_tools: false` per garantire la Topologia 2-Tier Hub-and-Spoke.
   - `scripts/nk_registry_indexer.py --verify` controlla queste due invarianti hardware ad ogni avvio e dopo ogni commit.

4. **Nuove Capacità Full-Stack UI, Browser E2E MCP e Connettori Cloud (`GAP-01`, `GAP-02`, `GAP-03`):**
   - `NK-Dynamic-Sandbox-StressTester` integra il testing E2E Browser live tramite `chrome-devtools-mcp` e `puppeteer`.
   - `NK-Delta-Architect` espande il dominio `DOM-03` allo sviluppo Full-Stack e Frontend (`TypeScript`, `React`, `Next.js`, `Tailwind`, `generative_ui`).
   - `NK-Ideator` e `NK-Backend-Architect` integrano i connettori MCP `tavily-mcp`, `google-docs-mcp` e `firebase-mcp-server`.

5. **Fast-Bypass in `Mode C` (`<= 150` LOC) e Cache In-Memory Ultra-Rapida (`< 1.2 ms`):**
   - `scripts/vibe_sprint_router.py` introduce `_ROUTER_MANIFEST_CACHE` e calcola `native_subagent` e `fast_bypass_eligible`.
   - Per modifiche rapide sotto `150` righe (`Mode C`), il Regista esegue il Fast-Bypass in `.staging/` con `--vibe-check`.
   - Questa corsia rapida riduce il consumo di token del `71.9%` (da `~18.500` a `~5.200` token).

6. **Suite di Stress-Test a 3 Livelli (`L1`, `L2`, `L3`) e 86 Golden Tests (`100.0% PASS`):**
   - Il nuovo modulo `tests/test_phase2_3tier_stress_suite.py` aggiunge `12` test ortogonali Zero-Mock divisi su `3` livelli.
   - Il Livello 1 verifica l'indice `native_agents_index`, le guardie `GT-14`/`RULE-01`, la concorrenza `PIDFileLock` a 8 thread e il DAG di Kahn.
   - Il Livello 2 verifica il routing `Mode A/B/C/D` sui `5` sub-agenti nativi e il rollback atomico RSI (`G2`, `G3`, `G4`).
   - Il Livello 3 verifica la difesa Red-Team SAST, il filtro STE100 a `20` parole, il Context Sentry e gli SLA `< 15 ms`.

---

### 2. Come è Cambiato il Funzionamento Operativo (`Prima` vs `Dopo`)

| Dimensione Operativa | Come Funzionava Prima (`v3.5.x`) | Come Funziona Adesso (`v4.0.0-Native-Swarm-Playbooks`) |
| :--- | :--- | :--- |
| **Avvio e Routing del Task** | Il modello leggeva le skill nel contesto principale o creava sub-agenti temporanei con `define_subagent`. | `vibe_sprint_router.py` risolve in `1.19 ms` la modalità (`Mode A/B/C/D`), la skill primaria e il `native_subagent` pre-registrato. |
| **Esecuzione Veloce (`Mode C <= 150` LOC)** | Richiedeva passaggi multipli di delega anche per piccole modifiche UI o script (`~18.500` token). | Attiva `fast_bypass_eligible: true` in `.staging/` con verifica `--vibe-check` in `< 500 ms` (`~5.200` token, `-71.9%`). |
| **Sviluppo Complesso (`Mode A` e `Mode B`)** | Le skill agivano come finte "persone" generando possibili conflitti con le regole globali dell'Hub. | Il Regista invoca con `invoke_subagent` il Sub-Agente Nativo (`NK-Builder-Agent`), che esegue il Playbook procedurale in `.staging/`. |
| **Audit di Sicurezza, DAST e RSI** | Solo `NK-RSI-Auditor` era nativo; mancava il blocco hardware su tutti gli altri nodi di controllo. | `NK-Security-DAST-Auditor` e `NK-RSI-Auditor` operano con blocco hardware `enable_write_tools: false` certificato da `GT-14`. |
| **Collaudo Frontend e Full-Stack** | Limitato al backend Python; i server `chrome-devtools-mcp` e `puppeteer` non erano collegati ai playbook. | `NK-Delta-Architect` costruisce UI moderne e `NK-Dynamic-Sandbox-StressTester` valida DOM, console, network e Lighthouse live. |
| **Indice Modulare O(1) (`nk_registry_manifest.json`)** | Indicizzava solo le `16` skill (`skills_index`) e i `32` script Python (`scripts_index`). | Indicizza separatamente `skills_index` (`16` Playbook) e `native_agents_index` (`5` Sub-Agenti) con lookup medio di `1.08 ms`. |
| **Certificazione Test e Contratti CLI** | `74` Golden Tests (`100% PASS`) e `111` flag CLI controllati dal CoVe AST Gate. | **`86` Golden e Stress Tests (`100% PASS` in `7.08 s`)** e **`152` flag CLI** verificati con $\Delta_k = 0$ e $Q(S_k) = 100.0\%$. |

---

### 3. Mappa Operativa dei 5 Sub-Agenti Nativi e dei 16 Playbook Procedurali

| Sub-Agente Nativo (`.agents/agents/`) | Dominio | Permessi Hardware YAML | Playbook Procedurali Associati (`.agents/skills/`) |
| :--- | :---: | :--- | :--- |
| **Regista Principale (Main Agent)** | `DOM-01` | Orchestrator & 2PC Committer | `NK-Master-Hub`, `[14] NK-Session-Controller` |
| **`NK-Specifier-Agent`** | `DOM-02` | `write: true`, `subagent: false`, `mcp: true` | `[0] NK-Ideator`, `[1] NK-App-UX-Architect`, `[2] NK-Backend-Architect`, `[10] NK-Plan-Aligner` |
| **`NK-Builder-Agent`** | `DOM-03` | `write: true`, `subagent: false`, `mcp: false` | `[4] NK-Python-Async-Builder`, `[5] NK-Delta-Architect`, `[3] NK-Agent-Instruction-Forge` |
| **`NK-Security-DAST-Auditor`** | `DOM-04` | **`write: false`**, `subagent: false`, `mcp: true` | `[6] NK-Security-Auditor`, `[8] NK-Dynamic-Sandbox-StressTester`, `[9] NK-Bug-Diagnostic-Engine` |
| **`NK-RSI-Auditor`** | `DOM-04` | **`write: false`**, `subagent: false`, `mcp: false` | `[7] NK-Oracle-Evaluator`, `[11] NK-State-Router`, `rsi_convergence_engine.py` |
| **`NK-Scribe-Agent`** | `DOM-05` | `write: true`, `subagent: false`, `mcp: false` | `[12] NK-Scribe`, `[13] NK-Episodic-Memory-Engine` |

---

### 4. Collaudo Avversariale a Freddo (Zero-Bias Cold Trial) e Pulizia Release (`NK-MS-20261018-COLD-TRIAL-v4.0.0-RSI`)

1. **Stress Test del Router O(1) e Lookup Multi-Skill (`10/10 PASS`):**
   - `scripts/vibe_sprint_router.py` introduce il flag `--classify-prompt` e la matrice `SKILL_ROUTING_RULES`.
   - Il router protegge i nomi file della Tetralogia Sovrana dalle collisioni lessicali di sottostringa (`"implementa"` e `"repo_map"`).
   - `scripts/nk_registry_indexer.py` filtra l'estrazione AST dei flag CLI alle sole chiamate `add_argument` (`152` flag reali).

2. **Raffinamento Chirurgico dei Moduli Core e dei Manifesti Sub-Agente (`15` Fix RSI):**
   - `scripts/rsi_convergence_engine.py` ignora i blocchi `<yaml_metadata_card>`, protegge i punti interni (`v3.0.0`) e allinea `w_tfail == 0`.
   - `scripts/ast_guard_validator.py` supporta `--json` e gestisce `.staging/` assente senza falsi errori.
   - `scripts/auto_heal_pipeline.py` elimina lo snapshot duplicato al ciclo 1 e rende opzionali `--test-cmd` e `--target-file`.
   - `scripts/external_project_scaffolder.py` imposta il percorso predefinito `../NK_External_Projects/<name>` quando `--target` è omesso.
   - `scripts/memory_3tier_engine.py` sincronizza sempre gli ultimi 5 episodi Tier-2 in `sync_tier1_capsule` e legge `NK_MODEL_PROFILE`.
   - `scripts/oracle_evaluator_l3.py` solleva `FileNotFoundError` su percorsi `.html` inesistenti e `nk_auto_inning.py` espone `--json`.

3. **Ottimizzazione Prestazioni e Pulizia Scorie Legacy (`-43.5%` Tempo Suite Test):**
   - `scripts/dast_sandbox_runner.py` esclude `sys.prefix` e `sys.exec_prefix` dal tracciamento `trace.Trace` nella Shadow Sandbox.
   - `scripts/nk_session_bootstrap.py` filtra i transcript dei sub-agenti tramite `<env_capsule>` privilegiando la conversazione principale.
   - Rimossa la cartella duplicata `nk_tracking/episodic_memory/`, i file `.bak_*` e i `18` report obsoleti `v1.9..v3.5`.
   - Il tempo di esecuzione degli `86` Golden e Stress Tests scende da `12.54 s` a **`7.08 s` (`100.0% PASS`)**.


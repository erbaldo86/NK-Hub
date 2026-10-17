# NK Genome: Concept Map e Master Brief (`v3.5.1-RSI2` / `v3.4.0` / `v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified`)

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢] | [RSI-CONVERGENCE: CONVERGED_OPTIMAL (Δ3=0, Q=100.0) 🟢]  
> **Milestone Anchor ID:** `NK-MS-20261017-MODULAR-INDEX-v3.5.1-RSI2` (`NK-MS-20261015-TENSOR-RSI-v3.1.0`)  
> **Versione Target:** `v3.5.1-RSI2` (`v3.4.0` / `v3.1.0-Tensor-RSI` / `v3.0.0-STE100-Unified` Compatible)  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`)  
> **Stato Produzione:** 100% Sola Lettura (`[RULE-00]`)

---

## 1. Visione Concettuale e Simbiosi con Gemini 4 Argon (High)

L'architettura `v3.4.0` (`v3.1.0-Tensor-RSI`) unifica i rilievi forensi di Argon e Opus con il motore Tensor-RSI 2D (`[RULE-RSI.1]`). Il sistema trasforma Nexus Keystone in una piattaforma di miglioramento ricorsivo continuo (`[RULE-RSI]`). Questa architettura opera con **Gemini 4 Argon (High)** e protegge i `68` Golden Tests tramite `GT-01..GT-14`.

1. **Direttiva Linguistica Universale (`[RULE-STE100]`):**
   * Tutto l'ecosistema adotta lo standard **ASD-STE100 Italiano Tecnico**.
   * Ogni frase operativa contiene al massimo 20 parole e una sola istruzione.
   * Tutte le regole usano la forma attiva, vocaboli univoci e zero incisi con trattini.
   * Il peso di `.agents/AGENTS.md` e `.agents/rules/anti_crash_rules.md` resta confinato entro il budget costituzionale.
2. **Architettura Dual-Profile (`standard` vs `argon`) con Auto-Attivazione (`GT-01..GT-06`):**
   * Le firme predefinite dei moduli Python mantengono le soglie `standard` (`70/100` step, `350` token Tier-1, `0/256/512/1024` token Repo-Map). Questa scelta protegge i `68` Golden Tests ortogonali.
   * Lo script `scripts/nk_session_bootstrap.py` imposta automaticamente `NK_MODEL_PROFILE=argon` nelle sessioni operative.
   * Il profilo `argon` esclude `len(thinking)` dal conteggio token e innalza le soglie a `150/250` step (`250k/500k` token).
3. **Topologia 2-Tier Hub-and-Spoke a Singolo Livello (`U-01`, `MC-01`):**
   * L'Agente Principale (`NK-Master-Hub` e `NK-Session-Controller`) registra i worker con `define_subagent(enable_subagent_tools=False)`.
   * L'Agente Principale invoca direttamente i Builder in `.staging/` e successivamente gli Auditor in sola lettura.
   * Questa topologia elimina il deadlock di doppia delega in cui `NK-Delta-Architect` non poteva invocare i sub-agenti.
4. **Holistic Fast-Track (`GT-03`, `U-05`) e Swarm Message Hygiene (`GT-04`, `U-02`, `U-06`):**
   * Il limite di chiamate dirette consecutive sale a `DDI_DIRECT_STREAK_LIMIT = 12` (`<= 8` letture da `800` righe e `<= 4` comandi). Lo stress test a 15 chiamate continua a scattare regolarmente.
   * `nk_swarm_messenger.py` mantiene il payload a `1.800` caratteri (MSS) entro la busta di `2.000` caratteri (MTU).
   * `nk_context_sentry.py` applica la penalità di `-15` punti solo ai messaggi di ritorno dei sub-agenti.
   * Ogni sub-agente salva i propri report nella propria cartella `brain/<subagent-id>/scratch/`.
5. **Integrazione dei 9 Comandi Slash Nativi di Antigravity 2.0:**
   * Il sistema integra i 9 comandi reali: `/plan`, `/goal`, `/compact`, `/grill-me`, `/teamwork-preview`, `/learn`, `/boost`, `/schedule`, `/browser`.
   * Il sistema rimuove tutti i comandi inesistenti (`/implementation`, `/start`, `/board`, `/novice`, `/expert`, `/playtest`).
   * Il comando nativo `/compact` e `scripts/nk_session_handoff.py` sostituiscono il vecchio handoff manuale a doppia chat.

---

## 2. Architettura del Motore RSI Continuo (`[RULE-RSI]`)

Il motore deterministico `scripts/rsi_convergence_engine.py` governa il ciclo di convergenza neuro-simbolico su tutte le attività dell'Hub.

```mermaid
flowchart TD
    subgraph TETRALOGIA["Tetralogia Sovrana 4/4 (nk_genome/)"]
        CM["1. concept_map.md (Visione v3.4.0 / v3.0.0-STE100-Unified)"]
        ST["2. structural_tree.md (30 Script, 16 Skill, 16 File Ausiliari, 68 Test)"]
        IP["3. implementation_plan.md (Piano Esecutivo WP1-WP7 e Guardie GT-01..14)"]
        RM["4. repo_map.md (Mappa AST PageRank Pura senza Progetti Esterni)"]
    end

    subgraph RSI_LOOP["Motore Deterministico RSI (scripts/rsi_convergence_engine.py)"]
        SNAP["Snapshot Transazionale SHA-256 (HealingSnapshotManager)"]
        ACT["1. ACTOR: Sintesi Piano, Codice in .staging/, Audit o Patch Skill"]
        CRIT["2. CRITIC SWARM (Sola Lettura): Security, Oracle, StressTester, Bug-Engine"]
        EVAL["3. EVALUATOR: Calcolo Delta_k e Fitness Q(S_k) + Guardie G1..G6"]
        REF["4. REFINER: Correzione Chirurgica in .staging/ o nk_genome/"]
        ROLL["Rollback Atomico SHA-256 a S_best"]
        CONV["CONVERGED_OPTIMAL (Delta_k = 0 e Q(S_k) = 100.0)"]
    end

    subgraph COMMIT["Commit Atomico e Memoria"]
        W2P["win32_2pc_engine.py (Mutex Win32 + Commit 2PC)"]
        MEM["memory_3tier_engine.py (Alias ARCH, SEC, OPS, DEVX)"]
    end

    CM --> ST --> IP --> RM
    RM --> SNAP
    SNAP --> ACT --> CRIT --> EVAL
    EVAL -- "Regressione Hard (G2) o Ciclo SHA-256 (G3)" --> ROLL
    EVAL -- "Delta_k > 0 e Monotono" --> REF --> SNAP
    EVAL -- "Delta_k == 0 e Q(S_k) == 100.0 (G1)" --> CONV
    CONV --> MEM --> W2P
```

### Formula Dual-Metric e Guardie del Motore RSI
1. **Doppia Metrica Accoppiata ($\Delta_k$ e $Q(S_k)$) con Canali TAS v4.0:**
   $$\Delta_k = 20 \cdot E_{\text{PoC},k} + 15 \cdot \text{SAST}_k + 12 \cdot D_{\text{sem},k} + 10 \cdot (T_{\text{fail},k} + C_k) + 5 \cdot H_k + 2 \cdot M_k + 1 \cdot (L_k + G_k)$$
   $$Q(S_k) = \text{round}\left(60.0 \cdot \frac{T_{\text{pass},k}}{T_{\text{total},k}} + \frac{40.0}{1.0 + \Delta_k / 25.0},\; 4\right)$$
   * Il termine `20 E_{PoC,k}` (`poc_confirmed_exploits`) penalizza gli exploit confermati dal Referee PoC nella Shadow Sandbox.
   * Il termine `12 D_{sem,k}` (`semantic_drift_findings`) penalizza il drift semantico tra specifica, UI, API e database.
2. **Sei Guardie Invarianti (`G1..G6`):**
   * **G1 (`Zero-Delta Stop`):** Il ciclo termina con `CONVERGED_OPTIMAL` solo quando `Delta_k == 0` e `Q(S_k) == 100.0`.
   * **G2 (`Strict Monotonic Hard Gate`):** Esegue il rollback via `HealingSnapshotManager` se peggiorano test, SAST, PoC o contratti.
   * **G3 (`Anti-Oscillation Guard`):** Salva gli hash SHA-256 in `visited_hashes` e blocca i cicli con `HALTED_CYCLE_DETECTED`.
   * **G4 (`Tamper-Evident Ledger`):** Registra ogni iterazione in `nk_tracking/rsi_telemetry.jsonl` con catena SHA-256 (`prev_hash` e `record_hash`).
   * **G5 (`Iteration Cap`):** Applica i limiti `K_max = 2` (`Mode C`), `3` (`Mode B`) e `4` (`Mode A`).
   * **G6 (`Validatore CLI`):** Il flag `--verify` valida i `16` file ausiliari, i `68` test e `[RULE-STE100]`.

---

## 3. Mappa delle 16 Skill Vocazionali e dei 16 File Ausiliari (`v3.0.0-STE100-Unified`)

| Indice | Skill (`.agents/skills/`) | Ruolo nella Topologia 2-Tier e nel Loop RSI | Allineamento `v3.4.0` (`v3.0.0-STE100-Unified`) |
| :---: | :--- | :--- | :--- |
| **L3** | **`NK-Master-Hub`** | Orchestratore Infrastrutturale e Committer 2PC | Preserva i nodi `[0]`..`[14]` e il footer a due vie (`GT-08`). Usa `ask_question` e `manage_task(Action="kill", TaskId="<id>")`. Elimina gli 8 file legacy in `scripts/` e `resources/`. |
| **`[0]`** | **`NK-Ideator`** | Actor L0 per Sintesi Concettuale | Usa `/grill-me` e `ask_question`. Scrive `concept_map.md` e `idea_canvas.md`. Linka `resources/idea_canvas_template.md` (`01/16`). |
| **`[1]`** | **`NK-App-UX-Architect`** | Actor L3 per UX, Design System e UI | Usa la Tetralogia 4/4 (rimosso `ui_design.md`). Integra `generate_image`, `<agent-embed>` (`generative_ui`) e `thinking_level: "HIGH"`. |
| **`[2]`** | **`NK-Backend-Architect`** | Actor L2 per DAG Backend e Contratti IPC | Valida schemi Pydantic v2 e contratti OpenAPI 3.0. Allinea l'output alla Tetralogia 4/4 in `nk_genome/`. |
| **`[3]`** | **`NK-Agent-Instruction-Forge`** | Meta-Refiner per Skill e Regole (`/learn`, `/boost`) | Applica lo standard `[RULE-STE100]` e verifica il budget di byte su `.agents/AGENTS.md` e sui 16 `SKILL.md`. |
| **`[4]`** | **`NK-Python-Async-Builder`** | Builder Primario e Refiner in `.staging/` | Legge fino a `800` righe per chiamata. Esegue `auto_heal_pipeline.py` e `rsi_convergence_engine.py` fino a $\Delta_k = 0$. |
| **`[5]`** | **`NK-Delta-Architect`** | Refiner Chirurgico in `.staging/` (1 Livello) | Opera come worker foglia (`enable_subagent_tools=False`). Linka `resources/delta_brief_template.md` (`02/16`) con Receipt v3.0. |
| **`[6]`** | **`NK-Security-Auditor`** | Critic Swarm TAS v4.0 SAST L1/L2/L3 (Sola Lettura) | Elimina i 21 file coi 4 nodi `Fixer`. Linka le 4 matrici modulari in `resources/` (`03/16..06/16`: routing, `L1`, `L2`, `L3`). |
| **`[7]`** | **`NK-Oracle-Evaluator`** | Critic Swarm e Oracolo Cold Audit (Gate 1-6) | Integra `/browser` (`chrome-devtools-mcp`) e `scripts/oracle_evaluator_l3.py`. Linka i 2 file in `references/` (`07/16..08/16`). |
| **`[8]`** | **`NK-Dynamic-Sandbox-StressTester`** | Critic Swarm DAST in `%TEMP%\nk_sandbox_<uuid>\` | Invoca `scripts/dast_sandbox_runner.py`. Elimina i 3 script legacy con fuzzer casuale in `resources/`. |
| **`[9]`** | **`NK-Bug-Diagnostic-Engine`** | Critic Swarm e Localizzatore RCA (SBFL Ochiai) | Invoca `scripts/sbfl_engine.py` e `scripts/sbfl_pytest_bridge.py` (`< 320` char, `GT-07`). Linka i 2 file in `resources/` (`09/16..10/16`). |
| **`[10]`** | **`NK-Plan-Aligner`** | Certificatore Turno 4 della Tetralogia 4/4 | Verifica l'allineamento 1:1 di `concept_map.md`, `structural_tree.md`, `implementation_plan.md` e `repo_map.md` con `rsi_convergence_engine.py --verify`. |
| **`[11]`** | **`NK-State-Router`** | Verificatore Topologico DAG di Kahn (Sola Lettura) | Opera come verificatore in sola lettura per `NK-Master-Hub`. Non acquisisce lock concorrenti al motore 2PC. |
| **`[12]`** | **`NK-Scribe`** | Cronista Post-Commit (`[RULE-00.2]`) | Usa il filtro `act` completo (`CREATE, MODIFY, DELETE, REFACTOR, AUDIT, FIX, SYNC`). Linka i 2 file in `resources/` (`11/16..12/16`). |
| **`[13]`** | **`NK-Episodic-Memory-Engine`** | Gestore Memoria 3-Tier (`ARCH`, `SEC`, `OPS`, `DEVX`) | Usa `DOMAIN_ALIAS_MAP` in `scripts/memory_3tier_engine.py` con cap `350` token standard (`GT-05`) e `1.200` token in profilo `argon`. |
| **`[14]`** | **`NK-Session-Controller`** | Sovrano Critico di Sessione e Cold Reviewer | Guida l'Auto-Brief FSM con convergenza RSI ($\Delta_k = 0$), la Cold Review a 6 Gate e `/compact`. Linka i 4 file validi in `resources/` (`13/16..16/16`). |

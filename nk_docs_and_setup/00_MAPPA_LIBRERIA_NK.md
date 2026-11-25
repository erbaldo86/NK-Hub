# Mappa Ufficiale della Libreria `NK Hub Generation` (`v3.0.2-Generation`)

> **Ambito:** Mappa architetturale per l'ecosistema `NK Hub Generation` (`v3.0.2-Generation`) su Google Antigravity 2.0.  
> **Milestone Anchor ID:** `NK-GEN-3.0.2-FORENSIC-HARDENING-CLEAN`  
> **Core Engine ABI:** `1.0.0-Generation`  
> **Profilo Modello Attivo:** `NK_MODEL_PROFILE=generation` (fallback `carbon`; supporta `neon`, `pro`, `flash`, `argon`, `standard`)  
> **Documenti Collegati:** **[🇮🇹 Manuale Italiano](README.it.md)** | **[🇬🇧 English Manual](README.md)** | **[📖 Guida Installazione ZIP](GUIDA_INSTALLAZIONE.md)** | **[📋 Patch Notes](../nk_genome/PATCH_NOTES.md)**

---

## 1. Isolamento Fisico multi-radice (`[RULE-PROJECT-ISOLATION]`)

L'archivio [`NK_Hub_OneClick_Package.zip`](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip) e il workspace separano il bridge radice, la libreria motore e le applicazioni utente:

```text
Root Workspace Padre (es. Workspace/)
├── NK Proget/
│   ├── Locale/<Nome>/                <-- [PROGETTI UTENTE] App locali sviluppate in .staging/ via 2PC
│   └── Online/<Nome>/                <-- [MIRROR SOLA LETTURA] Mirror di rilascio bloccato in scrittura
└── Antigravity/                      <-- Cartella principale di lavoro (Workspace Root)
    ├── .agents/                      <-- [BRIDGE] Scoperta immediata Zero-Discovery
    │   ├── AGENTS.md
    │   ├── plugins.json
    │   └── skills.json
    ├── NK_Hub/                       <-- [LIBRERIA SOVRANA] Motore v3.0.2-Generation (Core ABI 1.0.0-Generation)
    │   ├── .agents/                  <-- Costituzione, 6 Sub-Agenti GT-14, plugin nk-gate e 11 Skill
    │   ├── .github/                  <-- Presentazione GitHub, CI cross-OS e template issue
    │   ├── .staging/                 <-- Sandbox transazionale per modifiche prima del commit 2PC
    │   ├── nk_docs_and_setup/        <-- Manuali, installer 1-Click, workspace e pacchetto ZIP
    │   ├── nk_genome/                <-- Pentad Sovrana 4+1, SKILL_INDEX.md, repo_map.md e PATCH_NOTES.md
    │   ├── nk_tracking/              <-- Tensor-RSI v3, NKHandoffEngine v2, memoria 3-Tier e 4 sigilli SHA-256
    │   ├── scripts/                  <-- 34 moduli su 5 domini, 5 schemi L0 e sottopacchetti _internal/
    │   └── tests/                    <-- 40 suite Zero-Mock (384/384 su NVMe: fast, integration, stress)
    └── NK_External_Projects/         <-- [COMPAT] Percorso legacy compatibile per app isolate
```

`NK Proget/Locale/` ospita tutte le app attive (`compat NK_External_Projects/`, `526/526` test applicativi su `4/4` repository).
`NK Proget/Online/` funge da mirror di rilascio in sola lettura bloccato da `nk_hook_gate.py`, `win32_2pc_engine.py` e `external_project_scaffolder.py`.

---

## 2. Dettaglio delle Cartelle di `NK_Hub/`

### 2.1 `.agents/`: Costituzione, Plugin `nk-gate`, `6` Sub-Agenti e `11` Skill
* **[AGENTS.md](../.agents/AGENTS.md):** Costituzione operativa con `Core Engine ABI 1.0.0-Generation`, regole `RULE-00..RULE-STE100`, `[RULE-WIN32-ISOLATED-PYTEST]` e profilo `generation`.
* **[plugins.json](../.agents/plugins.json) e [hooks.json](../.agents/plugins/nk-gate/hooks.json):** Unico manifesto hook `nk-gate` in `python -S -B -u` per `nk_hook_gate.py` e `nk_acs_fastguard.py`.
* **I `6` Sub-Agenti Nativi (`GT-14`, `.agents/agents/*/agent.md`):** Tutti operano senza sub-agenti né MCP diretti (`enable_subagent_tools: false`, `enable_mcp_tools: false`). Solo `DOM-01 Orchestrator-Direct` esegue `research`, `browser` (`chrome-devtools-mcp`) e `image-generator`:
  * **[NK-Arch-Specifier](../.agents/agents/NK-Arch-Specifier/agent.md)** (`DOM-02`, **`write: false`**): Ideazione `L0`, `SCAMPER` e discovery `Mode D` senza scrivere DAG o OpenAPI.
  * **[NK-Specifier-Agent](../.agents/agents/NK-Specifier-Agent/agent.md)** (`DOM-02`, `write: true`): UX/UI `8px/HSL`, `Generative UI`, DAG di Kahn, OpenAPI `3.0` e `Pentad Sovrana 4+1` in `.staging/nk_genome/`.
  * **[NK-Builder-Agent](../.agents/agents/NK-Builder-Agent/agent.md)** (`DOM-03`, `write: true`): Backend Python async, React/Next.js/Tailwind e skill in `.staging/`.
  * **[NK-Security-DAST-Auditor](../.agents/agents/NK-Security-DAST-Auditor/agent.md)** (`DOM-04`, **`write: false`**): Audit `SAST L1/L2/L3`, DAST sandbox, telemetria Browser E2E e RCA `SBFL Ochiai`.
  * **[NK-RSI-Auditor](../.agents/agents/NK-RSI-Auditor/agent.md)** (`DOM-04`, **`write: false`**): Critic per `6` Gate `CRV`, allineamento `1:1`, DAG di Kahn e $\Delta_k = 0$.
  * **[NK-Scribe-Agent](../.agents/agents/NK-Scribe-Agent/agent.md)** (`DOM-05`, `write: true`): Sincronizzazione SSOT, `Pentad 4+1`, `repo_map.md`, `PATCH_NOTES.md`, ratchet e memoria `3-Tier`.
* **`skills/NK-*/SKILL.md` (`11` Playbook JIT):** [NK-Orchestrator](../.agents/skills/NK-Orchestrator/SKILL.md) e i `10` nodi `[0]`..`[9]` attivabili dai `16` trigger (`8` legacy più `8` `Generation`).

### 2.2 `nk_genome/`: Genoma Sovrano `3-Tier` e Indice `O(1)`
* **[00_GENOME_INDEX.md](../nk_genome/00_GENOME_INDEX.md) (`Tier-0`):** Router `O(1)` (`<= 950` token) per caricamento progressivo.
* **`Pentad Sovrana 4+1` (`Tier-1` + `Tier-2`):** Include [idea_canvas.md](../nk_genome/idea_canvas.md), [concept_map.md](../nk_genome/concept_map.md), [structural_tree.md](../nk_genome/structural_tree.md), [implementation_plan.md](../nk_genome/implementation_plan.md) e [repo_map.md](../nk_genome/repo_map.md). Contiene gli `8` moduli in `nk_genome/modules/` incluso [SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md](../nk_genome/modules/SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md).
* **Registro, Soglie e Cronologia:** [nk_registry_manifest.json](../nk_genome/nk_registry_manifest.json), [SKILL_INDEX.md](../nk_genome/SKILL_INDEX.md), `shards/DOM-00..06.json`, [saturation_thresholds.json](../nk_genome/configs/saturation_thresholds.json), `configs/tensor_rsi/` e [PATCH_NOTES.md](../nk_genome/PATCH_NOTES.md).

### 2.3 `nk_tracking/`: `Tensor-RSI v3`, `NKHandoffEngine v2` e `4` Sigilli `SHA-256`
* **Controllo e Baseline `Schema v2`:** `active_context.md`, `rsi_telemetry.jsonl` e [quality_baseline.json](../nk_tracking/quality_baseline.json) (`384/384` in `20.0s`, `stmt 91.25%`, `true_branch 83.43%`, `combined 88.98%`).
* **`4` Sigilli `SHA-256`:** [oracle_lock.json](../nk_tracking/oracle_lock.json) (`tests/`), [oracle_lock_holdout.json](../nk_tracking/oracle_lock_holdout.json) (`oracle_holdout/`), [governance_lock.json](../nk_tracking/governance_lock.json) (`scripts/`) e [tensor_rsi_lock.json](../nk_tracking/tensor_rsi_lock.json) (`nk_genome/configs/tensor_rsi`).
* **Control Plane e Continuità:** `Tensor-RSI v3` gestisce `ACTIVE.json`, `trsi1` HMAC e `nonce_store.py`. `NKHandoffEngine v2` applica whitelist `35` chiavi ed `Epistemic Firewall` su `anchor/`, `handoff/` e `manifests/`.
* **Memoria `3-Tier`:** `memory_3tier/tier1_active_capsule.json` (`1.200` token su `generation` o `carbon`) con ricerca ibrida `BM25 + Cosine RRF`.

### 2.4 `scripts/`, `tests/` e `nk_docs_and_setup/`: Motori, Piramide Test e Setup
* **`scripts/` (`34` Moduli):** `29` facciate CLI e `5` schemi `L0` (`handoff_contracts.py` in `DOM-05`) su `5` domini (`_internal/` `<= 500` LOC). I contatori ufficiali risiedono in [nk_registry_manifest.json](../nk_genome/nk_registry_manifest.json).
* **`tests/` e Piramide CI (`40` Suite):** Suite Zero-Mock (`DOM-06.json`) con profili `tier 1 -m fast <= 8.0s` e `tier 1+2 <= 28.0s` (`384/384` in `20.0s`). La CI in [ci.yml](../.github/workflows/ci.yml) impone floor `combined >= 88.0%` e `true_branch >= 82.0%`.
* **Isolamento NVMe Windows (`--pytest-isolated`):** `scripts/platform_runner.py --pytest-isolated` replica i test su `%TEMP%` (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`) evitando crash `conhost.exe`.
* **`nk_docs_and_setup/`:** Ospita [README.it.md](README.it.md), [README.md](README.md), [GUIDA_INSTALLAZIONE.md](GUIDA_INSTALLAZIONE.md), [install.ps1](install.ps1), [install.sh](install.sh), [requirements.txt](requirements.txt), [Antigravity.code-workspace](Antigravity.code-workspace), [root_bridge_AGENTS.md](root_bridge_AGENTS.md) e `NK_Hub_OneClick_Package.zip`.

---

## 3. Regola d'Oro per l'Utente

1. Non modificare manualmente i file interni di `NK_Hub/.agents/` o `NK_Hub/scripts/` durante una sessione attiva.
2. Apri [`Antigravity.code-workspace`](Antigravity.code-workspace) e avvia la sessione scrivendo `"avvia generation"` o `"avvia ambiente nk"` in chat.
3. Verifica l'ecosistema eseguendo `python -B -u scripts/rsi_convergence_engine.py --verify --strict-verify` e `python -B -u scripts/platform_runner.py --pytest-isolated`.

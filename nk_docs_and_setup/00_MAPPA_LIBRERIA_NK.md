# Mappa Ufficiale della Libreria `NK Hub Generation` (`v1.0.0-Generation`)

> **Ambito:** Mappa architetturale di riferimento per l'ecosistema `NK Hub Generation` su Google Antigravity 2.0.  
> **Milestone Anchor ID:** `NK-GEN-1.0.0`  
> **Profilo Modello Attivo:** `NK_MODEL_PROFILE=generation` (fallback `carbon`)  
> **Documenti Collegati:** **[🇮🇹 Manuale Italiano](README.it.md)** | **[🇬🇧 English Manual](README.md)** | **[📖 Guida Installazione ZIP](GUIDA_INSTALLAZIONE.md)** | **[📋 Patch Notes](../nk_genome/PATCH_NOTES.md)**

---

## 1. Isolamento Fisico a Tre Radici (`[RULE-PROJECT-ISOLATION]`)

L'archivio [`NK_Hub_OneClick_Package.zip`](https://github.com/erbaldo86/NK-Hub/raw/main/nk_docs_and_setup/NK_Hub_OneClick_Package.zip) e il workspace separano il bridge radice, la libreria motore e le applicazioni utente:

```text
Antigravity/                          <-- Cartella principale di lavoro (Workspace Root)
│
├── .agents/                          <-- [BRIDGE] Scoperta immediata Zero-Discovery
│   ├── AGENTS.md
│   ├── plugins.json
│   └── skills.json
│
├── NK_Hub/                           <-- [LIBRERIA SOVRANA] Motore multi-agente v1.0.0-Generation
│   ├── .agents/                      <-- Costituzione, 6 Sub-Agenti GT-14, plugin nk-gate e 11 Skill
│   ├── .github/                      <-- Presentazione GitHub, CI cross-OS e template issue
│   ├── .staging/                     <-- Sandbox transazionale per modifiche prima del commit 2PC
│   ├── nk_docs_and_setup/            <-- Manuali, installer 1-Click, workspace e pacchetto ZIP
│   ├── nk_genome/                    <-- Pentad Sovrana 4+1, SKILL_INDEX.md, repo_map.md e PATCH_NOTES.md
│   ├── nk_tracking/                  <-- Memoria 3-Tier, telemetria RSI, handoff e sigillo oracle_lock.json
│   ├── scripts/                      <-- 34 file top-level (37 moduli indicizzati, 260 .py con _internal/)
│   └── tests/                        <-- Suite Zero-Mock (513/513 PASS su 41 moduli test_*.py, 45 .py)
│
└── NK_External_Projects/             <-- [PROGETTI UTENTE] Ogni app esterna vive in una sottocartella isolata
```

---

## 2. Dettaglio delle Cartelle di `NK_Hub/`

### 2.1 `.agents/`: Costituzione, Plugin `nk-gate`, `6` Sub-Agenti e `11` Skill
* **[AGENTS.md](../.agents/AGENTS.md):** Costituzione operativa con regole `RULE-00..RULE-STE100`, `[RULE-WIN32-ISOLATED-PYTEST]` e profilo `generation`.
* **[plugins.json](../.agents/plugins.json) e [hooks.json](../.agents/plugins/nk-gate/hooks.json):** Unico manifesto hook `nk-gate` in `python -S -B -u` per `nk_hook_gate.py` e `nk_acs_fastguard.py`.
* **I `6` Sub-Agenti Nativi (`GT-14`, `.agents/agents/*/agent.md`):** Tutti operano senza sub-agenti né MCP diretti (`enable_subagent_tools: false`, `enable_mcp_tools: false`, `CRIT-01`). Solo `DOM-01 Orchestrator-Direct` esegue `research`, `browser` (`chrome-devtools-mcp`) e `image-generator`:
  * **[NK-Arch-Specifier](../.agents/agents/NK-Arch-Specifier/agent.md)** (`DOM-02`, **`write: false`**): ideazione `L0`, `SCAMPER` e discovery `Mode D` (NON scrive DAG/OpenAPI).
  * **[NK-Specifier-Agent](../.agents/agents/NK-Specifier-Agent/agent.md)** (`DOM-02`, `write: true`): UX/UI `8px/HSL`, `Generative UI`, DAG di Kahn, OpenAPI `3.0` / Pydantic v2 e `Pentad Sovrana 4+1` in `.staging/nk_genome/`.
  * **[NK-Builder-Agent](../.agents/agents/NK-Builder-Agent/agent.md)** (`DOM-03`, `write: true`): backend Python async, React/Next.js/Tailwind e skill in `.staging/`.
  * **[NK-Security-DAST-Auditor](../.agents/agents/NK-Security-DAST-Auditor/agent.md)** (`DOM-04`, **`write: false`**): audit `SAST L1/L2/L3`, DAST sandbox, telemetria Browser E2E e RCA `SBFL Ochiai`.
  * **[NK-RSI-Auditor](../.agents/agents/NK-RSI-Auditor/agent.md)** (`DOM-04`, **`write: false`**): critic per `6` Gate `CRV`, allineamento `1:1`, DAG di Kahn e $\Delta_k = 0$.
  * **[NK-Scribe-Agent](../.agents/agents/NK-Scribe-Agent/agent.md)** (`DOM-05`, `write: true`): sincronizzazione SSOT, `Pentad 4+1`, `repo_map.md`, `PATCH_NOTES.md`, ratchet e memoria `3-Tier`.
* **`skills/NK-*/SKILL.md` (`11` Playbook JIT):** [NK-Orchestrator](../.agents/skills/NK-Orchestrator/SKILL.md) e i `10` nodi della dashboard `[0]`..`[9]` attivabili dai `16` trigger (`8` legacy + `8` `Generation`).

### 2.2 `nk_genome/`: Genoma Sovrano `3-Tier` e Indice `O(1)`
* **[00_GENOME_INDEX.md](../nk_genome/00_GENOME_INDEX.md) (`Tier-0`):** router `O(1)` (`<= 950` token) per caricamento progressivo.
* **`Pentad Sovrana 4+1` (`Tier-1` + `Tier-2`):** include [idea_canvas.md](../nk_genome/idea_canvas.md), [concept_map.md](../nk_genome/concept_map.md), [structural_tree.md](../nk_genome/structural_tree.md), [implementation_plan.md](../nk_genome/implementation_plan.md) e [repo_map.md](../nk_genome/repo_map.md). Contiene inoltre gli `8` moduli in `nk_genome/modules/` incluso [SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md](../nk_genome/modules/SYSTEM_GRAPHS_DAG_DSM_RTM_HEATMAP.md).
* **Registro, Soglie e Cronologia:** [nk_registry_manifest.json](../nk_genome/nk_registry_manifest.json), [SKILL_INDEX.md](../nk_genome/SKILL_INDEX.md), `shards/DOM-00..06.json`, [saturation_thresholds.json](../nk_genome/configs/saturation_thresholds.json) e [PATCH_NOTES.md](../nk_genome/PATCH_NOTES.md).

### 2.3 `nk_tracking/`: Memoria Episodica `3-Tier` e Telemetria
* **Controllo e Audit:** `active_context.md`, `rsi_telemetry.jsonl`, [quality_baseline.json](../nk_tracking/quality_baseline.json) e [oracle_lock.json](../nk_tracking/oracle_lock.json) (`373` file sigillati in `SHA-256`).
* **Continuità e Checkpoint:** `anchor/session_anchor.jsonl`, `handoff/`, `manifests/` e `reports_and_briefs/`.
* **Memoria `3-Tier`:** `memory_3tier/tier1_active_capsule.json` (`1.200` token su `generation` o `carbon`) con ricerca ibrida `BM25 + Cosine RRF`.

### 2.4 `scripts/`, `tests/` e `nk_docs_and_setup/`: Motori, Suite Zero-Mock e Setup
* **`scripts/`:** `34` file top-level e `37` moduli indicizzati su `5` domini `DOM-01..DOM-05` (`4` schemi `scripts/schemas/`). Totale `260` file `.py` con `_internal/` aciclici sotto `500` LOC.
* **`tests/`:** `513/513 PASS` (`0` skipped) su `41` moduli `test_*.py` (`45` `.py` totali). Copertura in [quality_baseline.json](../nk_tracking/quality_baseline.json): `89.32%` branch, `94.39%` statement e `92.89%` combined.
* **Isolamento NVMe Windows (`--pytest-isolated`):** `scripts/platform_runner.py --pytest-isolated` replica i test su `%TEMP%` (`~68.3s`) senza crash `conhost.exe`. Supporta la CI cross-OS in [ci.yml](../.github/workflows/ci.yml).
* **`nk_docs_and_setup/`:** ospita [README.it.md](README.it.md), [README.md](README.md), [GUIDA_INSTALLAZIONE.md](GUIDA_INSTALLAZIONE.md), [install.ps1](install.ps1), [install.sh](install.sh), [requirements.txt](requirements.txt), [Antigravity.code-workspace](Antigravity.code-workspace), [root_bridge_AGENTS.md](root_bridge_AGENTS.md) e [NK_Hub_OneClick_Package.zip](NK_Hub_OneClick_Package.zip).

---

## 3. Regola d'Oro per l'Utente

1. Non modificare manualmente i file interni di `NK_Hub/.agents/` o `NK_Hub/scripts/` durante una sessione attiva.
2. Apri [`Antigravity.code-workspace`](Antigravity.code-workspace) e avvia la sessione scrivendo `"avvia generation"` o `"avvia ambiente nk"` in chat.
3. Verifica l'ecosistema locale eseguendo `python -B -u scripts/rsi_convergence_engine.py --verify --strict-verify` e `python -B -u scripts/platform_runner.py --pytest-isolated`.

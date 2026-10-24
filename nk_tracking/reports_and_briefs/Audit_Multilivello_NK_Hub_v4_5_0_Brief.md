# 🏛️ Report Audit Multilivello (L1-L8) e Master Brief RSI (`NK-Hub v4.5.0-STE100-Unified`)

- **Brief ID:** `IB-20261024-FA51ED` + `IB-20261024-1A15BE` | **Milestone Target:** `NK-MS-20261024-HOLISTIC-SANITATION-v4.5.0-RSI`
- **Validatori Eseguiti:** `scratch/nk_multilevel_env_validator.py` + `scratch/epistemic_propagation_toolbox.py` + `NK-RSI-Auditor` + `NK-Security-DAST-Auditor`
- **Stato Attuale Suite:** `108/108 PASS` (`13.18 s`) | **Bootstrap:** `PASS` (`83.77 ms`) | **Preflight:** `HEALTHY_GREEN` (`81.93 ms`)

---

## 1. Sintesi Esecutiva degli 8 Livelli di Controllo

| Livello | Ambito di Verifica | Esito Attuale | Anomalie Rilevate |
| :---: | :--- | :---: | :--- |
| **L1** | File System, Scorie e Isolamento | `WARN` | `1` file `.bak_1`, `2` handoff contaminati da `NK-Bandi`, `15` report non ruotati, `__pycache__` in `.staging/`. |
| **L2** | Indici Modulari O(1) e Manifesto | `WARN` | `nk_hook_gate.py` e `nk_transcript_tools.py` assenti da `DOMAIN_TAXONOMY`; conflitto `DOM-02`/`DOM-03` su `Forge`. |
| **L3** | Tetralogia Sovrana 4/4 (`nk_genome/`) | `WARN` | Drift numerico (`86`/`98`/`108` test, `30`/`32`/`34`/`36` script, `WP12` vs `WP17`), `stop-check` vs `stop-evidence`. |
| **L4** | Interoperabilità Skill, Agenti e Regole | `WARN` | `run_command` omesso nel frontmatter degli Auditor; alias tool legacy nelle 16 skill; `GUIDA_INSTALLAZIONE.md` in Scribe. |
| **L5** | Analisi Statica AST e Bug in `scripts/` | `WARN` | `1` import inutilizzato (`Optional`) e `5` difetti logici in `rsi_convergence_engine`, `nk_hook_gate`, `nk_transcript_tools`, `preflight`. |
| **L6** | Telemetria SHA-256, Anchor e Memoria | `WARN` | `rsi_telemetry.jsonl` fermo a `v3.0.0`, `session_anchor.jsonl` fermo a `v4.3.0`, handoff JSON fermo a `87` test. |
| **L7** | Validazione Dinamica End-to-End | `PASS` | `108/108` test verdi; `preflight_health_check.py` rifiuta il flag `--json` con `exit code 2`. |
| **L8** | Propagazione Capillare Anti-Menzogna | `FAIL_GAP` | `10/16` Skill a `0%`, `16/16` Skill prive di `[RULE-EVIDENCE]` e `[RULE-DATA-PROVENANCE]`, `<env_capsule>` e `Template 8A` a `0%`. |

---

## 2. Dettaglio dei Rilievi Strutturali (`L1..L7`)

### Livello 1: Igiene del File System e Isolamento (`[RULE-PROJECT-ISOLATION]`)
1. **`F1.1` Relitto Backup:** Il file `nk_tracking/memory_3tier/03_Ideation_and_Decisions/episodes.jsonl.bak_1` è rimasto su disco.
2. **`F1.2` Contaminazione Handoff Esterno:** `nk_tracking/anchor/next_session_prompt.md` duplica `nk_tracking/handoff/next_session_prompt.md`. Entrambi puntano a `NK-Bandi`, abilitano `EnableWriteTools=True` sull'Auditor (`GT-14`) ed espongono l'`Holdout Set B` (`AP-8`).
3. **`F1.3` Mancata Rotazione Report:** `scripts/preflight_health_check.py` non ruota i file `IB-YYYYMMDD-*.md` né i report `TAS_Report_*` con versione intermedia. Sono inoltre presenti `4` report specifici di `NK-Bandi` dentro `NK-Hub`.
4. **`F1.4` Cache Orfane e Cartelle Vuote:** `.staging/scripts/__pycache__/` e `.staging/tests/__pycache__/` non vengono pulite perché `PRUNED_WALK_DIRS` esclude `.staging`. Le cartelle `nk_tracking/manifests/` e `nk_tracking/stashes/` sono vuote.

### Livello 2: Sincronizzazione Indici O(1) (`[RULE-01.14]`)
1. **`F2.1` Gap in `DOMAIN_TAXONOMY`:** `scripts/nk_registry_indexer.py` omette `nk_hook_gate.py` in `DOM-01` e `nk_transcript_tools.py` in `DOM-04`. I due script mancano quindi nella `intent_dispatch_table` di `nk_genome/nk_registry_manifest.json`.
2. **`F2.2` Disallineamento `NK-Agent-Instruction-Forge`:** `DOMAIN_TAXONOMY` assegna la skill a `DOM-02`, mentre `_INDEXER_SKILL_RULES` e `SKILL.md` usano `DOM-03`.
3. **`F2.3` Versione Manifesto O(1):** `nk_registry_manifest.json` e `SKILL_INDEX.md` riportano ancora `3.5.1-MODULAR-INDEX-RSI2`.

### Livello 3: Coerenza del Genoma (`nk_genome/`)
1. **`F3.1` Drift Numerico Tetralogia:** `concept_map.md`, `structural_tree.md` e `implementation_plan.md` alternano riferimenti a `68`, `86`, `98` e `108` test e a `30`, `32`, `34` e `36` script.
2. **`F3.2` Formula $\Delta_k$ e `WP17`:** `concept_map.md` omette il termine `+ 100 D_k` nella formula matematica e il punto `10` relativo a `WP17`.
3. **`F3.3` Sottocomando Hook:** La Tetralogia cita `stop-check`, mentre `scripts/nk_hook_gate.py` implementa `stop-evidence`.
4. **`F3.4` `idea_canvas.md` e `repo_map.md`:** `idea_canvas.md` è fermo a `v3.1.0`; `repo_map.md` conta `36` righe invece del profilo `argon_mode_a`.
5. **`F3.5` Documentazione Root e CI:** `.github/workflows/ci.yml` cita `66 test` e `GUIDA_INSTALLAZIONE.md` cita `31 script` e `90 test`.

### Livello 4: Interoperabilità Skill, Sub-Agenti e Regole (`.agents/`)
1. **`F4.1` Permessi `run_command` sugli Auditor:** `NK-RSI-Auditor/agent.md` e `NK-Security-DAST-Auditor/agent.md` mantengono `enable_write_tools: false` (`GT-14`), ma omettono `run_command` nella lista `tools:` del frontmatter.
2. **`F4.2` Deroga Scribe e Conteggi:** `NK-State-Router/SKILL.md` cita `32 script` anziché `34` moduli (`36` file `.py`); `[RULE-00.2]` in `AGENTS.md` va allineata con `GUIDA_INSTALLAZIONE.md` citata in `NK-Scribe/SKILL.md`.

### Livello 5: Bug Statica e Logica in `scripts/`
1. **`F5.1` Import Inutilizzato:** Rimuovere `Optional` non usato in `scripts/quality_baseline_manager.py:17`.
2. **`F5.2` `rsi_convergence_engine.py`:** Correggere `--vibe-check` (riga `1641`) affinché scansioni sia `.agents` sia `.staging` quando invocato senza argomenti. Validare anche `combined_bytes` alla riga `1321`.
3. **`F5.3` `nk_hook_gate.py`:** Collegare `stop-evidence` (riga `303`) a `nk_transcript_tools.check_evidence()` quando `verifiedExitZero` non è fornito nel payload. Pulire il ramo ridondante in `_handle_write_gate` (riga `224`).
4. **`F5.4` `nk_transcript_tools.py`:** Includere `polling_list_calls == 0` e il controllo `step <= 100` in `analyze_compliance`. Limitare la ricerca di `_EXIT_ZERO_RE` in `check_evidence` ai soli record tool/sistema.
5. **`F5.5` `preflight_health_check.py`:** Supportare il flag `--json`, includere `.staging/**/__pycache__` nella pulizia cache e migliorare la regex di `_enforce_report_retention`.

---

## 3. Livello 8: Valutazione Zero-Bias sulla Propagazione del Sistema Anti-Menzogna (`IB-20261024-1A15BE`)

La toolbox esterna `scratch/epistemic_propagation_toolbox.py` e la verifica indipendente di `NK-RSI-Auditor` hanno misurato la presenza dei `10` marker epistemici (`[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]`, `[RULE-ORACLE-LOCK]`, penalità `-10.000` / `100 D_k`, uscita sicura `report-conflict`, divieto `PYTEST_CURRENT_TEST` / `currentframe` / `len(grants)`, `oracle_lock.json`, `source_url` / `evidence_quote`, `exit_code: 0`) lungo i 6 anelli della catena operativa:

### 3.1 Mappa di Copertura Misurata dalla Toolbox Esterna
1. **Anello 0 (`.agents/AGENTS.md` e `anti_crash_rules.md`):**
   - `AGENTS.md`: **`100.0%` (`10/10` marker)**.
   - `anti_crash_rules.md`: **`0.0%` (`0/10` marker)**.
2. **Anello 1 (`5` Sub-Agenti Nativi in `.agents/agents/*/agent.md`):**
   - Copertura parziale **`50% - 60%`**: tutti i `5` `agent.md` citano `[RULE-EPISTEMIC-HONESTY]`, `[RULE-ORACLE-LOCK]` e `report-conflict`.
   - **Gap critico (`5/5`):** Nessuno dei `5` sub-agenti cita `[RULE-EVIDENCE]` né `[RULE-DATA-PROVENANCE]` (`source_url`, `evidence_quote`). Inoltre `NK-Specifier-Agent` e `NK-Scribe-Agent` omettono il divieto di `PYTEST_CURRENT_TEST` e `currentframe()`.
3. **Anello 2 (`16` Skill Vocazionali in `.agents/skills/*/SKILL.md`):**
   - **Gap critico (`10/16` Skill a `0%`):** Ben `10` skill su `16` (`NK-Ideator`, `NK-App-UX-Architect`, `NK-Backend-Architect`, `NK-Agent-Instruction-Forge`, `NK-Dynamic-Sandbox-StressTester`, `NK-Bug-Diagnostic-Engine`, `NK-Plan-Aligner`, `NK-State-Router`, `NK-Scribe`, `NK-Episodic-Memory-Engine`) non contengono alcuna regola anti-menzogna (`0%`, salvo `StressTester` al `10%` per il solo `exit_code: 0`).
   - **Gap trasversale (`16/16` Skill):** Nessuna delle `16` skill cita `[RULE-EVIDENCE]` o `[RULE-DATA-PROVENANCE]`.
4. **Anello 3 e 4 (`16` File Ausiliari, `<env_capsule>` e `Template 1..11`):**
   - In `prompt_templates.md`, il blocco `<env_capsule>` e i template di delega `Template 3`, `Template 4`, `Template 8A` (`HANDOFF PROMPT FOR BUILDER`), `Template 8B` e `Template 9` hanno copertura **`0%`** sulle regole anti-menzogna.
   - `delta_brief_template.md`, `anti_pattern_guards.md`, `verification_oracles.md` e le matrici `tas_l1..l3` non menzionano `report-conflict`, `[RULE-EPISTEMIC-HONESTY]` né i pattern `SAST-GAMING-D01..D04`.
5. **Anello 5 (Meccanismo di Amnesia Contestuale e Recency Bias):**
   - Quando l'Orchestratore registra un worker con `define_subagent` e invia il prompt `Template 8A`, il worker legge la propria `SKILL.md` (`view_file`), `implementation_plan.md` e i file sorgente.
   - A quel punto `AGENTS.md` si trova lontano dagli ultimi token letti (o non è nel prompt diretto del worker registrato al volo). Se `<env_capsule>`, `Template 8A` e la `SKILL.md` non contengono `[RULE-EPISTEMIC-HONESTY]` e `report-conflict`, il modello sotto pressione in un loop di riparazione dimentica l'uscita sicura a `0` punti (`report-conflict`) e ricade nel test-gaming.

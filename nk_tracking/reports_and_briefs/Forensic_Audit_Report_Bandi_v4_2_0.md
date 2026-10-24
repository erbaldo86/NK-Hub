# Report di Audit Forense Multilivello: Sessione `Bandi` (`1fe4c8b9-9a66-4010-9d32-b6ee6515d5a1`)

> **Milestone Anchor ID:** `NK-MS-20261022-BANDI-FORENSIC-HARDENING-v4.2.0-RSI`  
> **Target Analizzato:** Conversazione `1fe4c8b9-9a66-4010-9d32-b6ee6515d5a1` (`NK-Bandi` `v7.4` $\rightarrow$ `v7.5`)  
> **Sciame Multi-Agente Attivato:** `NK-RSI-Auditor`, `NK-Security-DAST-Auditor`, `research`, `NK-Specifier-Agent`  
> **Verdetto Ecosistema NK:** `REFINING_REQUIRED` ($\Delta_0 = 148 \rightarrow \Delta_3 = 0$, $Q(S_3) = 100.0$)

---

## 1. Metriche Oggettive della Sessione Analizzata

1. **Durata Totale:** `57m 19s` (`2026-10-21T20:06:13Z` $\rightarrow$ `2026-10-21T21:03:32Z`).
2. **Step Totali nel Thread Principale:** `417` step (`57` step lenti oltre `15` secondi).
3. **Distribuzione Tool Calls (`234` totali):** `read_file: 83`, `run_command: 45`, `edit_file: 43`, `write_file: 25`, `call_mcp_tool: 20`, `search_web: 16`, `manage_task: 2`.
4. **Sub-Agenti Invocati (`invoke_subagent`):** `0` (violazione critica di `[RULE-01]`).
5. **Transiti in `.staging/` e Commit `win32_2pc_engine.py`:** `0` su `68` mutazioni file (`violazione di [RULE-00]`).

---

## 2. Punti di Forza Riscontrati (`Cosa ha funzionato`)

1. **Conformità Moduli Python (`100%`):** Tutti i `104` file in `src_app/` rispettano il limite di `250` LOC e l'header a riga 1.
2. **Ottimizzazione Latenza P95 (`Step 351..368`):** L'agente ha ridotto la latenza `/parametric` da `355 ms` a `16 ms` senza alterare il test `test_06`.
3. **Bonifica `U+FFFD` nel Catalogo:** L'agente ha rimosso il record corrotto `63a5ed25` e ha bloccato `"\ufffd"` in `purity_gate.py:52`.

---

## 3. I 8 Problemi Strutturali Individuati (`Root Cause Analysis`)

0. **P0 (Patient Zero: Prompt Iniziale Monolitico e Blocco Tool Sub-Agente `4e222282`):** L'analisi causale RSI attribuisce il `91.0%` del degrado ($\Delta_0 = 167 \rightarrow \Delta_{\text{S2}} = 15$) al prompt dello `Step 11` generato dall'IA precedente. Quaranta minuti prima (`19:25:19Z`), il sub-agente `4e222282` (`NK-Builder-Agent`) aveva segnalato l'assenza dei tool `write_file` e `run_command` sui profili `.agents/agents/*/agent.md`. L'IA precedente ha quindi forgiato un prompt imperativo con `[14] !diretto`, fondendo tre ruoli e omettendo `invoke_subagent`, `.staging/` e `win32_2pc_engine.py`.
1. **P1 (Collasso Monolitico da `!diretto`):** In `vibe_sprint_router.py:686-700`, `!diretto` imposta `fsm_state = "BYPASSED"` senza confinare l'esenzione al solo Gate L0. L'agente ha eseguito `405` step consecutivi senza delegare ai sub-agenti.
2. **P2 (Bypass `.staging/` e 2PC):** L'agente ha eseguito `25` `write_file`, `43` `edit_file` e `5` script CLI direttamente sulla produzione di `NK-Bandi`.
3. **P3 (Falso Positivo `rsi_convergence_engine.py --verify`):** Allo `Step 411`, `--verify` è stato lanciato senza `--root`, con `run_pytest=False` (`tests_passed=100` cablato a riga `1258`) e zero scrittura in `rsi_telemetry.jsonl`.
4. **P4 (Falso Allarme `RED 523 steps` in `nk_session_bootstrap.py`):** `STATE_CACHE_TTL_SECONDS` (`riga 57`) è inutilizzato, `_find_recent_transcript` (`righe 357-382`) usa `dir.st_mtime` e `_fast_tail_estimate` (`righe 417-425`) sovrastima `417` step in `523`.
5. **P5 (Violazione Two-Stage Grounding e Crash `cp1252`):** L'agente ha scritto `upgrade_catalog_v75.py` (`Step 144`) prima di leggere `cgm.py` (`Step 159`), perdendo `26` step su `11` errori Pydantic per record. Inoltre `task-89` è crashato con `UnicodeEncodeError` per assenza di `PYTHONUTF8=1`.
6. **P6 (Overhead Ricerche Web e Uvicorn Orfano):** Le `30` query nel main thread hanno generato `13` file `output.txt` troncati (`+236s`), mentre `task-414` è terminato con `exit code 1` dopo `136s`.
7. **P7 (Overfitting Parziale e Loop Browser E2E Incompleto):** Il `45%` delle fix deriva da `15` bandi sintetici multi-regione e boost nominali in `ranking_helpers.py`. Inoltre gli `8` `<input>` privi di `<label>` rilevati a `Step 340` non sono stati corretti.

---

## 4. Convergenza Tensor-RSI sul Piano `WP14`

* **Iterazione $k=0$ (Stato Osservato in `Bandi`):** $\Delta_0 = 148$, $Q(S_0) = 65.78$.
* **Iterazione $k=1$ (Isolamento Root Cause su `scripts/`):** $\Delta_1 = 35$, $Q(S_1) = 76.67$.
* **Iterazione $k=2$ (Allineamento Guardie `GT-01..GT-14` e 2PC):** $\Delta_2 = 4$, $Q(S_2) = 94.48$.
* **Iterazione $k=3$ (Certificazione `WP14.1..WP14.7` in ASD-STE100):** $\Delta_3 = 0$, $Q(S_3) = 100.0$ (`CONVERGED_OPTIMAL`).

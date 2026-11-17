# DOM-04: Audit, Sicurezza SAST/DAST, RSI e Oracolo (`v1.0.0-Generation`)

## 1. Perimetro e Consolidamento Audit (`DOM-04`)

Il dominio `DOM-04` esegue validazione statica SAST, sandbox DAST, localizzazione guasti SBFL, `6` Gate CRV e convergenza RSI.
Tutti gli auditor lavorano in isolamento read-only con `enable_write_tools: false`, `enable_mcp_tools: false` ed `enable_subagent_tools: false`.

| ID | Asset `DOM-04` | Tipo | Perimetro `v1.0.0-Generation` (`NK-GEN-1.0.0`) |
| :--- | :--- | :--- | :--- |
| `S-01` | `NK-Security-Auditor` | Skill (`[5]`) | Audit TAS Neuro-Simbolico SAST L1/L2/L3 e CoVe in sola lettura |
| `S-02` | `NK-Oracle-Evaluator` | Skill (`[6]`) | Unifica `6` Gate CRV, Alligner Turno `4`, DAG Kahn e drift SHA-256 |
| `S-03` | `NK-Dynamic-Sandbox-StressTester` | Skill (`[7]`) | Stress test DAST in Shadow Sandbox Windows e audit telemetria |
| `S-04` | `NK-Bug-Diagnostic-Engine` | Skill (`[8]`) | RCA con Ochiai SBFL e False Bug Rejection Gate |
| `A-01` | `NK-RSI-Auditor` | Agente Nativo | Valutatore deterministico `Delta_k = 0` sotto orchestrazione `NK-Orchestrator` |
| `A-02` | `NK-Security-DAST-Auditor` | Agente Nativo | Auditor SAST/DAST read-only senza tool MCP diretti (`CRIT-01`) |

## 2. Facciate e Moduli `DOM-04`

| ID | Modulo Python (`scripts/`) | Facciata / `_internal/` | Funzioni Critiche |
| :--- | :--- | :--- | :--- |
| `M-01` | `scripts/ast_guard_validator.py` | `_internal/ast_guard_validator/` (`<= 500` LOC) | SAST AST, firme ricorsive re-export e `[RULE-NO-LITERAL-ENV-PATH]` |
| `M-02` | `scripts/rsi_convergence_engine.py` | `_internal/rsi_convergence_engine/` (`<= 500` LOC) | Bundle `--emit-gt14-bundle`, STE100 stretto, CoVe CLI e blocco `UNMEASURED_DRY_RUN` |
| `M-03` | `scripts/dast_sandbox_runner.py` | `_internal/dast_sandbox_runner/` (`JobObject`) | `--overlay-staging`, `_BUILDER_STRIP_PATHS`, `is_dry_run: False` e stress concorrente |
| `M-04` | `scripts/oracle_evaluator_l3.py` | `_internal/oracle_evaluator_l3/` (`CONF-10`) | Verifica `6` Gate CRV con supporto `.md`/`.json` sull'atteso |
| `M-05` | `scripts/sbfl_engine.py`, `scripts/sbfl_pytest_bridge.py` | `_internal/sbfl_engine/` + Bridge Pytest | SSOT `SBFLEngine`/`SBFLLocation` e bridge metriche Ochiai |
| `M-06` | `scripts/nk_transcript_tools.py` | `_internal/nk_transcript_tools/` | `verify_ste100_compliance`, `verify_report_grounding`, lock e transcript |

## 3. Protocollo `Dual-Execution` e Bundle `GT-14`

1. L'Orchestratore invoca `scripts/rsi_convergence_engine.py --emit-gt14-bundle --with-dast` salvando il JSON nella directory temporanea di sistema.
2. `NK-RSI-Auditor` e `NK-Security-DAST-Auditor` leggono il bundle tramite `read_file` verificando `total_violations == 0`, `scc_cycle_count == 0` e zero link rotti.
3. Nessun file `.md` sotto `nk_genome/` gode di esenzione STE100, incluso `repo_map.md`.
4. Riferimenti shard: [DOM-04.json](../shards/DOM-04.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

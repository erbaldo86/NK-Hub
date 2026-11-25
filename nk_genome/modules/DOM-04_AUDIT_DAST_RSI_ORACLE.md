# DOM-04: Audit, Sicurezza SAST/DAST, RSI e Oracolo (`v1.0.0-Generation`)

## 1. Perimetro e Consolidamento Gemini 4 (`DOM-04`)

Il dominio `DOM-04` esegue validazione statica SAST `L1..L3`, sandbox DAST tri-stato, localizzazione SBFL, `6` Gate CRV e convergenza `Q_v2`.
Tutti gli auditor lavorano in isolamento read-only con `enable_write_tools: false`, `enable_mcp_tools: false` ed `enable_subagent_tools: false`.
Ogni skill `DOM-04` usa `SKILL.md` compresso (`<= 40` righe) e carica `references/mode_*.md` (`<= 25` righe) JIT.

| ID | Asset `DOM-04` | Tipo | Perimetro (`patch_version: 12`, `retry_caps [0, 0, 0]`) |
| :--- | :--- | :--- | :--- |
| `S-01` | `NK-Security-Auditor` | Skill (`[5]`, `L0 + L2`, `Producer`) | Audit SAST `L1..L3` e CoVe (`37` righe) con [mode_sast_audit.md](../../.agents/skills/NK-Security-Auditor/references/mode_sast_audit.md) (`18` righe) |
| `S-02` | `NK-Oracle-Evaluator` | Skill (`[6]`, `L0`, `Producer`) | `6` Gate CRV, `4` lock SHA-256 (`38` righe) con [mode_oracle_gate.md](../../.agents/skills/NK-Oracle-Evaluator/references/mode_oracle_gate.md) (`16` righe) |
| `S-03` | `NK-Dynamic-Sandbox-StressTester` | Skill (`[7]`, `L0`, `Producer`) | Sandbox DAST tri-stato ed E2E (`37` righe) con [mode_dast_e2e.md](../../.agents/skills/NK-Dynamic-Sandbox-StressTester/references/mode_dast_e2e.md) (`15` righe) |
| `S-04` | `NK-Bug-Diagnostic-Engine` | Skill (`[8]`, `L0`, `Producer`) | RCA Ochiai e False Bug Gate (`37` righe) con [mode_rca_sbfl.md](../../.agents/skills/NK-Bug-Diagnostic-Engine/references/mode_rca_sbfl.md) (`14` righe) |
| `A-01` | `NK-RSI-Auditor` | Agente Nativo (`RO GT-14`) | Verificatore `6` Gate, `Q_v2 == 100.0`, `G_hard == 1`, floor `82.0%` e gemello `nk-gate` |
| `A-02` | `NK-Security-DAST-Auditor` | Agente Nativo (`RO GT-14`) | Auditor SAST, DAST tri-stato e SBFL con gemello `nk-gate` SHA-256 |

## 2. Guardie Anti-Bias, Hardening Forense e Registro `O(1)`

Entrambi i sub-agenti nativi (`NK-RSI-Auditor`, `NK-Security-DAST-Auditor`) applicano `4` guardie Anti-Bias prima di emettere qualsiasi verdetto:
1. **`EVIDENCE-FIRST`:** Leggono `gt14_evidence_pack.json` (dopo `strip_l3_persuasive_narrative`) e i `4` sigilli `SHA-256` dentro `<passive_data_context>` senza punteggi storici.
2. **`MANDATORY FALSIFICATION`:** Formulano almeno `2` ipotesi falsificabili `file:line`.
3. **`ANTI-CHECKLIST THEATER`:** Trattano `UNMEASURED`, `NaN`, `Inf` o `dry_run` come `FAIL`.
4. **`FAIL-CLOSED E MINORITY-VETO`:** Applicano quorum cieco in `Mode A` ed emettono `gaming_penalty: -10.000` su test-gaming.

L'indicizzazione `O(1)` (`scripts/_internal/nk_registry_indexer/`) garantisce igiene e lookup deterministico:
1. **`hygiene_filter.py`:** Filtra keyword dispatch lunghe oltre `32` caratteri preservando le chiavi canoniche di dominio.
2. **`taxonomy.py`:** Definisce `SKILL_PRIMARY_SCRIPTS` e `SCRIPT_SKILL_MAP` includendo `tensor_rsi.py` in `DOM-01`.
3. **`shards.py` e `shards_rehydrate.py`:** Eseguono `_pack_intents_grouped` mantenendo tutti i `7` shard sotto `4.700` B con reidratazione degli script.
4. **`lookup.py`:** Risolve sub-agenti `DOM-04`, mapping script verso skill e lookup sanitizzato della Pentad.
5. **`manifest_builder.py`:** Emette intestazione STE100 (`5` domini, `7` shard, `11` skill) in `SKILL_INDEX.md`.

## 3. Facciate, Moduli e Protocollo `Dual-Execution` `GT-14`

| ID | Modulo Python (`scripts/`) | Facciata / `_internal/` | Funzioni Critiche |
| :--- | :--- | :--- | :--- |
| `M-01` | `scripts/ast_guard_validator.py` | `_internal/ast_guard_validator/` | SAST AST, `--quality-diff`, scope creep e `[RULE-NO-LITERAL-ENV-PATH]` |
| `M-02` | `scripts/rsi_convergence_engine.py` | `_internal/rsi_convergence_engine/` | `Q_v2(S_k)`, `G_hard`, `FAIL` cap `49.9`, `MIN_KILL_RATE_FLOOR = 0.80`, `--with-dast` forwarding, sanitizer holdout annidati |
| `M-03` | `scripts/dast_sandbox_runner.py` | `_internal/dast_sandbox_runner/` | `--overlay-staging`, `--verify-holdout` su `4` lock (`tensor_rsi_lock.json` incluso), case check Windows |
| `M-04` | `scripts/oracle_evaluator_l3.py` | `_internal/oracle_evaluator_l3/` | Verifica `6` Gate CRV, floor CI `88.0%` combined / `82.0%` true branch, blocco UNC Win32 |
| `M-05` | `scripts/sbfl_pytest_bridge.py` | `_internal/sbfl_pytest_bridge/` | Spettri Ochiai `--collect-pass-coverage` e `--hybrid-fl` sotto `80` token |
| `M-06` | `scripts/nk_transcript_tools.py` | `_internal/nk_transcript_tools/` | `lint-ste100`, `report-conflict`, grounding, `4` lock `SHA-256` e `transcript_scan.py` |

1. L'Orchestratore esegue `scripts/rsi_convergence_engine.py --emit-gt14-bundle --with-dast` salvando in `%TEMP%`.
2. `NK-RSI-Auditor` e `NK-Security-DAST-Auditor` leggono il bundle via `read_file` ed emettono verdetti sotto `1.800` caratteri.
3. Riferimenti shard: [DOM-04.json](../shards/DOM-04.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

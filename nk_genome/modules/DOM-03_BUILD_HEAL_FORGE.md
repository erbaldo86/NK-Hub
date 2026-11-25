# DOM-03: Build, Fast-Healing, Runtime e Instruction Forge (`v1.0.0-Generation`)

## 1. Perimetro e Asset `DOM-03` (`NK-GEN-1.0.0`)

Il dominio `DOM-03` gestisce sviluppo in `.staging/`, regole `L1`, runtime Windows e Fast-Healing.
Solo `DOM-01 Orchestrator-Direct` delega media o built-in; `NK-Builder-Agent` opera confinato in `.staging/`.

| ID | Asset `DOM-03` | Tipo | Ruolo Operativo |
| :--- | :--- | :--- | :--- |
| `C-01` | `NK-Agent-Instruction-Forge` | Skill (`[2]`) | Costruisce regole e skill STE100 con sharding JIT `<= 1.200` tok |
| `C-02` | `NK-Python-Async-Builder` | Skill (`[3]`) | Backend Python async, Pydantic `v2` strict, SQLite WAL e Fast-Healing |
| `C-03` | `NK-Delta-Architect` | Skill (`[4]`) | Modifiche incrementali full-stack, React, Tailwind e `generative_ui` |
| `C-04` | `NK-Builder-Agent` | Agente Nativo | Esegue implementazioni e test in `.staging/` (`NK_Hub` e `NK Proget/Locale/`) via `platform_runner.py` |

## 2. Topologia Aciclica (`C_k = 0`) e Consolidamento Classi

La topologia modulare elimina cicli Tarjan (`C_k = 0`) e consolida ogni classe in un unico `SSOT`:

1. **Estrazione DTO `L0`:** `RSIDefectVector`, `RSIIterationRecord`, `RSISessionReport` e `OchiaiDiagnosticPayload` vivono in `scripts/schemas/nk_ipc_contracts.py`.
2. **Consolidamento SSOT:** `HealingSnapshotManager` risiede solo in `scripts/healing_snapshot_rollback.py`, mentre `KarpathySlicer` resta unico in `scripts/auto_heal_pipeline.py`.
3. **Zero archi retrogradi:** Ogni import ascendente verso `rsi_convergence_engine.py` resta vietato garantendo `scc_cycle_count = 0`.
4. **Confinamento Sibling NVMe:** `isolated_test_runner.py` rileva sibling sotto `NK Proget/Locale/` e `NK_External_Projects/`, ignorando sempre `NK Proget/Online/`.

## 3. Moduli Runtime e Auto-Healing (`DOM-03`)

| ID | Modulo Python (`scripts/`) | Simboli Chiave | Garanzia Operativa |
| :--- | :--- | :--- | :--- |
| `W-01` | `scripts/auto_heal_pipeline.py` | `AutoHealPipeline`, `HealingCycleLog` | Ciclo Fast-Healing confinato con rollback automatico |
| `W-02` | `scripts/healing_snapshot_rollback.py` | `HealingSnapshotManager`, `_atomic_write_bytes` | Snapshot e ripristino atomico multi-file |
| `W-03` | `scripts/builder_mutation_gate.py` | `MutationGateReport`, `MutantSpec`, `SharedBaseNVMeWorkerPool` | Gate AST differenziale e modalita reale `--audit-full-module` con moduli `<= 303` LOC (`0` cicli SCC) |
| `W-04` | `scripts/platform_runner.py` | `safe_subprocess_run`, `_run_pytest_isolated_cli` | Processi `-B -u`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, piramide `-m fast <= 8.0s` / `<= 28.0s` |
| `W-05` | `scripts/deterministic_api_cache.py` | `DeterministicApiCache` | Cache SQLite WAL persistente con retry backoff |
| `W-06` | `scripts/safe_cleanup_dev_servers.py` | `scan_listening_port_range`, `kill_pid_tree` | Libera porte orfane in `NK Proget/Locale/` ignorando `Online/` contro `WinError 32` |
| `W-07` | `scripts/async_heartbeat_signaler.py` | `AsyncHeartbeatSignaler` | Segnalatore heartbeat asincrono per task lunghi |

Tutti gli shard di dominio e flag CLI sono indicizzati in [DOM-03.json](../shards/DOM-03.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

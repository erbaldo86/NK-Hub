# DOM-01: Governance, Routing, Win32 2PC e ACS (`v1.0.0-Generation`)

## 1. Perimetro e Facciate `DOM-01` (`NK-GEN-1.0.0`)

Il dominio `DOM-01` governa routing `Single-Gate`, `16` shortcut, bootstrap veloce, `Win32 2PC`, schemi IPC e sentinella `ACS`.
Tutti i moduli `DOM-01` operano come facciate CLI sotto `500` LOC appoggiate su `scripts/_internal/`.

| ID | Asset `DOM-01` | Tipo | Perimetro Reale |
| :--- | :--- | :--- | :--- |
| `G-01` | `NK-Orchestrator` | Skill (`Hub`) | Orchestrazione `2-Tier` (`11` skill, `6` foglie, `10` nodi), `Single-Gate` e `ACS` |
| `G-02` | `scripts/vibe_sprint_router.py` | Facciata CLI | `_internal/vibe_sprint_router/`: Gate, `16` shortcut, STT e `shards/` |
| `G-03` | `scripts/nk_registry_indexer.py` | Facciata CLI | `_internal/nk_registry_indexer/`: `--sync`, `--verify` e shard `DOM-00..06` |
| `G-04` | `scripts/nk_hook_gate.py` | Facciata CLI | `_internal/nk_hook_gate/`: Write-Gate shell, `--prompt` e MCP guard |
| `G-05` | `scripts/win32_2pc_engine.py` | Facciata CLI | `_internal/win32_2pc_engine/`: `Win32NamedMutex`, `BatchJournalV2`, WAL |
| `G-06` | `scripts/nk_session_bootstrap.py` | Facciata CLI | `_internal/nk_session_bootstrap/`: Fast-Stat `TTL 900s`, shortcut e WAL |
| `G-07` | `scripts/nk_acs_fastguard.py` | Facciata CLI | Soglie `160k/185k/205k` JSON stdlib e isolamento per `conversation_id` |
| `G-08` | `scripts/preflight_health_check.py`, `scripts/nk_swarm_messenger.py` | Moduli Core | Igiene preflight baseline, retention report e validazione messaggi |
| `G-09` | `scripts/schemas/` (`nk_ipc_contracts.py`, `nk_catalog_contracts.py`, `dual_ledgers.py`) | Foglie `L0` | Contratti Pydantic `strict=True`, `TaskLedger`, `ProgressLedger` e `PIDFileLock` |
| `G-10` | `scripts/_internal/nk_common/` (`isolated_test_runner`, `ledger_lock_io`, `catalog`, `thresholds`, `constants`) | Runtime Condiviso | Mirror NVMe pytest, lock PID bounded, catalogo SSOT e costanti gate |

## 2. Shortcut Onboarding (`16` Trigger) e Runner Isolato NVMe

`scripts/_internal/nk_common/constants.py` definisce `ONBOARDING_TRIGGERS` unendo `8` shortcut legacy e `8` shortcut `Generation`:

* **8 Shortcut Legacy:** `avvia ambiente nk`, `avvia nk hub`, `avvia nk`, `avvia hub`, `start nk`, `start hub`, `attiva nk`, `attiva ambiente nk`.
* **8 Shortcut Generation:** `avvia generation`, `avvia nk generation`, `avvia nk hub generation`, `avvia ambiente generation`, `start generation`, `start nk generation`, `attiva generation`, `attiva ambiente generation`.

Il runtime condiviso `nk_common` integra la difesa anti-crash Windows (`0xC000013A`):
1. `scripts/_internal/nk_common/isolated_test_runner.py` replica il workspace su NVMe in `%TEMP%` tramite `mirror_workspace_to_nvme()`.
2. `scripts/platform_runner.py --pytest-isolated` invoca `run_detached_pytest()` con `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` e `-p no:cacheprovider`.
3. `PIDFileLock(acquire_timeout_sec)` in `scripts/_internal/nk_common/ledger_lock_io.py` garantisce lock cooperativo senza deadlock su Drive FS.

## 3. Hardening `ACS`, Compilatore SSOT e Contratti `L0`

Sotto `python -S`, `scripts/nk_acs_fastguard.py` carica `nk_genome/configs/saturation_thresholds.json` via `json` stdlib.
Il profilo `generation` con alias `carbon` imposta `160k/185k/205k` token, `120/150/180` step e `1200` token tier1.
Il compilatore SSOT estrae `SKILL_ROUTING_RULES` e `DASHBOARD_NODE_MAP` dai frontmatter `SKILL.md` tramite `nk_common.catalog`.

1. **Isolamento sessioni:** checkpoint salvati in `nk_tracking/sessions/<conversation_id>/fastguard_<conv_id>.json`.
2. **Coerenza post-compattazione:** traccia `epoch_baseline_tokens` e `fallback_steps` dopo `/compact`.
3. **Surface CLI pulita:** `scripts/nk_acs_fastguard.py` espone esattamente `6` flag CLI verificati via AST.
4. **Foglie acicliche `L0`:** `scripts/schemas/nk_ipc_contracts.py` detiene i `DTO` condivisi senza import ascendenti.
5. **Compatibilita facciate:** ogni facciata preserva i re-export `ast.ImportFrom` e il routing in `nk_genome/shards/`.

Dati operativi e hash SHA-256 risiedono in [DOM-01.json](../shards/DOM-01.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

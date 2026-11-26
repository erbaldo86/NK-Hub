# DOM-01: Governance, Routing, Win32 2PC e ACS (`v1.0.0-Generation`)

## 1. Perimetro e Facciate `DOM-01` (`NK-GEN-1.0.0`)

Il dominio `DOM-01` governa routing `Single-Gate`, `16` shortcut, bootstrap veloce, `Win32 2PC`, schemi IPC, `Tensor-RSI` e sentinella `ACS`.
Tutti i moduli operano come facciate CLI sotto `500` LOC appoggiate su `scripts/_internal/`.

| ID | Asset `DOM-01` | Tipo | Perimetro Reale |
| :--- | :--- | :--- | :--- |
| `G-01` | `NK-Orchestrator` | Skill (`Hub`) | Orchestrazione `2-Tier` (`11` skill, `6` foglie, `10` nodi), `Single-Gate` e `ACS` |
| `G-02` | `scripts/vibe_sprint_router.py` | Facciata CLI | `_internal/vibe_sprint_router/`: Gate, `16` shortcut, `EXECUTE_HANDOFF_SERIALIZE`, `IntentTrackClassifier` |
| `G-03` | `scripts/nk_registry_indexer.py` | Facciata CLI | `_internal/nk_registry_indexer/`: `--sync`, `--verify` e `7` shard `DOM-00..06` |
| `G-04` | `scripts/nk_hook_gate.py` | Facciata CLI | `_internal/nk_hook_gate/`: Write-Gate, ownership `plans/<lane_id>.md`, blocco `Online/`, prompt `ask` `oracle-lock freeze`, `ACTIVE.json` |
| `G-05` | `scripts/win32_2pc_engine.py` | Facciata CLI | `_internal/win32_2pc_engine/`: `Win32NamedMutex`, `--consolidate-sublanes --parent-lane`, `sublane_consolidator`, `nonce_store` `v2` |
| `G-06` | `scripts/nk_session_bootstrap.py` | Facciata CLI | `_internal/nk_session_bootstrap/`: Fast-Stat `TTL 900s`, `--handoff-verify`, WAL |
| `G-07` | `scripts/nk_acs_fastguard.py` | Facciata CLI | Soglie `160k/185k/205k` e `last_velocity_delta` Z3 su `generation`, `carbon`, `neon`, `pro`, `flash`, `argon`, `standard` |
| `G-08` | `scripts/preflight_health_check.py` | Modulo Core | Igiene preflight baseline Schema `v2`, `4` lock e sanitizzazione WAL |
| `G-09` | `scripts/schemas/` (`dual_ledgers.py`, `dual_ledgers_models.py`, `handoff_contracts.py`, `nk_catalog_contracts.py`, `nk_ipc_contracts.py`) | `5` Foglie `L0` | Contratti `strict=True`, `TaskDAGNode` M4 (`lane_id`, `declared_write_set`, `target_repo_root`), `TaskLedger` |
| `G-10` | `scripts/_internal/nk_common/` (`isolated_test_runner`, `dag_wave_scheduler`, `preflight_conflict_predictor`, `epistemic_firewall_rules`) | Runtime | Mirror NVMe pytest, onde Kahn disgiunte, pre-flight AST, Firewall `AP-12..16` |
| `G-11` | `scripts/tensor_rsi.py` | Facciata CLI | `_internal/tensor_rsi/`: `5` flag CLI, `8` step (`status`/`abort`), ticket `trsi1` HMAC, `TTL <= 1800s`, CAS, clamp `NaN/Inf` |

## 2. Shortcut Onboarding (`16` Trigger) e Runner Isolato NVMe

`scripts/_internal/nk_common/constants.py` definisce `ONBOARDING_TRIGGERS` (`8` legacy più `8` Generation):
* **Legacy:** `avvia ambiente nk`, `avvia nk hub`, `avvia nk`, `avvia hub`, `start nk`, `start hub`, `attiva nk`, `attiva ambiente nk`.
* **Generation:** `avvia generation`, `avvia nk generation`, `avvia nk hub generation`, `avvia ambiente generation`, `start generation`, `start nk generation`, `attiva generation`, `attiva ambiente generation`.

La difesa anti-crash Windows (`0xC000013A`) usa `mirror_workspace_to_nvme()` in `%TEMP%`, `scripts/platform_runner.py --pytest-isolated` e `PIDFileLock`.

## 3. Hardening `ACS`, `Tensor-RSI v3` e Contratti `L0`

Sotto `python -S`, `scripts/nk_acs_fastguard.py` carica `nk_genome/configs/saturation_thresholds.json` (`160k/185k/205k` token, `120/150/180` step, `1200` tok tier1).
Il compilatore SSOT estrae `SKILL_ROUTING_RULES` e `DASHBOARD_NODE_MAP` via `nk_common.catalog`.

1. **Isolamento sessioni:** Salva checkpoint in `nk_tracking/sessions/<conversation_id>/fastguard_<conv_id>.json` e aggiorna `last_velocity_delta`.
2. **Coerenza `Tensor-RSI`:** `scripts/tensor_rsi.py` supporta `intake`, `diagnose`, `propose`, `evaluate`, `decide`, `record`, `status`, `abort` su [tensor_rsi_lock.json](../../nk_tracking/tensor_rsi_lock.json).
3. **Hardening Bandit e Ratchet:** Filtra record `dry_run` e `deception_gaming_count`, applica Jeffreys `LCB90` e classificazione `flaky` su `3/3` rerun.
4. **Foglie acicliche `L0`:** I `5` moduli `scripts/schemas/` prevengono cicli Tarjan e validano payload senza `NaN` o `Inf`.
5. **Compatibilità facciate:** Ogni facciata preserva re-export `ast.ImportFrom` e routing `nk_genome/shards/`.

## 4. Routing L0 `NKHandoffEngine v2` e Ricezione in `1` Step

1. **Trigger `EXECUTE_HANDOFF_SERIALIZE`:** `scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>"` instrada l'handoff verso `NK-Scribe-Agent` (`DOM-05`).
2. **Comando Serializzatore:** Il router emette `scripts/nk_session_handoff.py --serialize --ecosystem-scan` in `PASSIVE_STANDBY` o `ACTIVE_CONTINUATION`.
3. **Verifica `1` Step (`< 60 ms`):** `scripts/nk_session_bootstrap.py --handoff-verify --project-root "<root>"` valida `envelope_sha256` e `.staging/` via `FAST_STAT_HIT`.
4. **Firewall (`AP-12..16`):** `scripts/_internal/nk_common/epistemic_firewall_rules.py` applica `AP-12/13` su `ACTIVE_CONTINUATION`, esegue `strip_l3_persuasive_narrative` e blocca `AP-14..16`.
5. **Ricezione L0:** `PASSIVE_STANDBY` attiva `STATE_HANDOFF_STANDBY` (`BYPASSED`). `ACTIVE_CONTINUATION` impone `AWAIT_CONFIRM` con requisiti `R1..Rn`.

Dati operativi e SHA-256 risiedono in [DOM-01.json](../shards/DOM-01.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

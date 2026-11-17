# DOM-05: Memoria Episodica, Scribe e SSOT (`v1.0.0-Generation`)

## 1. Perimetro e Genoma a `3` Tier (`DOM-05`)

Il dominio `DOM-05` gestisce memoria episodica `3-Tier`, indicizzazione AST, telemetry HUD e coerenza documentale SSOT (`NK-GEN-1.0.0`).
Tutti i contatori live di test, coverage e dimensioni risiedono in [quality_baseline.json](../../nk_tracking/quality_baseline.json).

| ID | Asset `DOM-05` | Ruolo | Funzione Target `v1.0.0-Generation` |
| :--- | :--- | :--- | :--- |
| `S-01` | `NK-Scribe-Memory` | Skill (`[9]`) | Unifica Genoma `3-Tier`, `repo_map.md` completo, `PATCH_NOTES.md` e memoria RRF |
| `A-01` | `NK-Scribe-Agent` | Agente Nativo | Esegue sync SSOT in `.staging/`, baseline ratchet e commit Git |
| `T-00` | [00_GENOME_INDEX.md](../00_GENOME_INDEX.md) | `Tier-0` | Router `O(1)` (`<= 950` tok) verso `Pentad Sovrana 4+1` e shard JSON |
| `T-01` | [repo_map.md](../repo_map.md) e `Pentad Sovrana 4+1` | `Tier-1` | Cinque file canonici (`<= 1.100` tok) privi di numeri volatili |
| `T-02` | `modules/` e `shards/DOM-00..06.json` | `Tier-2` | Moduli dominio e `7` shard JSON compatti (`<= 1.200` tok ciascuno) |

## 2. Moduli Python Reali e Facciate `_internal/`

| ID | Modulo Python (`scripts/`) | Facciata / `_internal/` | Responsabilita Principale |
| :--- | :--- | :--- | :--- |
| `M-01` | `scripts/memory_3tier_engine.py` | `_internal/memory_3tier_engine/` | Ricerca `HybridRRFSearchEngine` e `Tier1CoreMemory` (`1.200` tok `generation`/`carbon`) |
| `M-02` | `scripts/nk_registry_indexer.py` | `_internal/nk_registry_indexer/` | `--sync`, `--verify`, facciate `<= 800` tok e reidratazione shard |
| `M-03` | `scripts/ast_repo_mapper.py` | `_internal/ast_repo_mapper/` | Snapshot backticked completo (`scripts/`, `_internal/`, `schemas/`, `tests/`) STE100 |
| `M-04` | `scripts/nk_transcript_tools.py` | `_internal/nk_transcript_tools/` | `verify_ste100_compliance`, `verify_report_grounding` e `oracle_lock.json` |
| `M-05` | `scripts/quality_baseline_manager.py` | Core Ratchet | `--check-only` su [quality_baseline.json](../../nk_tracking/quality_baseline.json) |
| `M-06` | `scripts/nk_context_sentry.py`, `scripts/micro_hud_renderer.py` | `_internal/nk_context_sentry/` + HUD | Monitoraggio contesto `NKContextSentry` su `saturation_thresholds.json` |
| `M-07` | `scripts/nk_session_handoff.py`, `scripts/nk_compliance_checker.py`, `scripts/nk_auto_inning.py`, `scripts/nk_active_runtime_sentinel.py` | Core Sessione | Ancore `session_anchor.jsonl`, handoff e sentinel runtime (`120/150/180` step) |

## 3. Protocollo `NK-Scribe-Memory` e Reidratazione `O(1)`

1. **Facciate compatibili (`<= 800` tok):** [nk_registry_manifest.json](../nk_registry_manifest.json) e [SKILL_INDEX.md](../SKILL_INDEX.md) restano compatti in `nk_genome/`.
2. **Reidratazione trasparente:** `nk_registry_indexer.py` e `vibe_sprint_router.py` caricano i dettagli completi dai `7` shard in `nk_genome/shards/`.
3. **Staging obbligatorio:** `NK-Scribe-Agent` scrive solo dentro `.staging/` e aggiorna `PATCH_NOTES.md` sempre in testa (`prepend-only`).
4. **Riferimenti shard:** [DOM-05.json](../shards/DOM-05.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

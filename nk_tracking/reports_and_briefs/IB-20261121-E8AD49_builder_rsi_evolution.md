# Intent Brief: Evoluzione Analitica e Anti-Bias Builder DOM-03 (`NK-GEN-1.2.0`)

> **Brief ID:** `IB-20261121-E8AD49` (conferma `IB-20261121-D6265B`).  
> **Milestone:** `NK-GEN-1.2.0-BUILDER-RSI-EVOLUTION`.  
> **Modalita:** `mode_a` (`Opzione 2: Massimo Rigore Analitico`).  
> **Stato:** Analisi `S0..S2` in attesa di approvazione utente pre-torneo `S3`.  
> **Ancore Genoma:** [implementation_plan.md](../../nk_genome/implementation_plan.md) e [quality_baseline.json](../quality_baseline.json).

## R1..R8 Requisiti EARS Verificabili

1. **R1.** IL SISTEMA DEVE analizzare i Builder `DOM-03` aumentando efficienza e rigore implementativo.
2. **R2.** QUANDO scrive codice o refactoring, IL SISTEMA DEVE validare, misurare e approvare ogni modifica.
3. **R3.** IL SISTEMA DEVE prevenire creator bias, anchoring legacy e mirroring tra codice e test.
4. **R4.** IL SISTEMA DEVE valorizzare i tre playbook originali dentro un unico sub-agente `2-Tier`.
5. **R5.** QUANDO riscrive moduli `_internal/`, IL SISTEMA DEVE preservare le firme ed i re-export.
6. **R6.** IL SISTEMA DEVE confrontare ipotesi falsificabili per esclusione mediante ablazione oggettiva `RSI`.
7. **R7.** PRIMA di modificare codice Builder, IL SISTEMA DEVE presentare un piano stratificato approvabile.
8. **R8.** QUANDO testa ipotesi candidate, IL SISTEMA DEVE eseguire prove `ShadowSandbox` e `NVMe` Zero-Mock.

## Sintesi Swarm Ortogonale `S1` (3 Lenti Indipendenti)

1. **Lente 1 (`NK-Arch-Specifier`).** Il profilo unificato comprime i tre playbook ed omette i riferimenti di rollback e `NVMe`.
   Il validatore in `scripts/_internal/ast_guard_validator/validator.py` salta i re-export sull'albero pre-modifica occultando simboli rimossi.
2. **Lente 2 (`NK-Security-DAST-Auditor`).** Il flusso attuale soffre di ancoraggio, ricevute auto-compilate, dead-loop senza callback e `n_ep` nullo.
   Il confronto in `scripts/_internal/auto_heal_pipeline/runner.py` legge lo stesso file invece della baseline.
3. **Lente 3 (`NK-RSI-Auditor`).** Il gestore in `scripts/_internal/healing_snapshot_rollback/manager_and_cli.py` rigetta i refactoring equivalenti e ignora codici di uscita errati.
   La metrica `tests_skipped` in [quality_baseline.json](../quality_baseline.json) inverte il verso ottimo e `ab_success_min` copia l'ultimo ciclo.

## Catalogo Ipotesi Falsificabili (`H0_rejected` e `H1..H6`)

| ID | Ipotesi Operativa | Moduli Target Principali | Criterio Hard-Kill di Esclusione |
| :--- | :--- | :--- | :--- |
| `H0_rejected` | Tre sub-agenti Builder separati | Topologia `DOM-03` | Viola `[RULE-01]` e moltiplica overhead token |
| `H1` | Routing modale + shard JIT anti-bias | Gemelli `NK-Builder-Agent`, tre `SKILL.md` | Viola `skill_golden_eval_set.json` o cresce overhead |
| `H2` | Gate fitness refactoring-aware e baseline | `manager_and_cli.py`, `runner.py` | Accetta `exit_code != 0` oppure rollback ingiusto |
| `H3` | Diagnosi single-pass `--diagnose-slice` e `SBFL` | `auto_heal_pipeline/cli.py`, `bridge_core.py` | Riduzione latenza sotto soglia oppure `n_ep` nullo |
| `H4` | Guardia AST simmetrica e metriche | `ast_guard_validator/validator.py` | Manca re-export rimosso o supera limite righe |
| `H5` | Torneo doppio profilo `builder` vs `evaluator` | `staging_overlay.py`, suite benchmark | Leak holdout o fallimento su test ciechi |
| `H6` | Fix ratchet, `ab_success_min` e overhead | `quality_baseline.json`, `ab_benchmark.py` | Peggiora qualsiasi metrica del ratchet `RSI` |

## Protocollo di Torneo e Ablazione (`S3..S5`)

1. **Fase S3 (Esclusione).** Esegui screening individuale, combinazione dei superstiti ed ablazione `Leave-One-Out` secondo il Rasoio di Occam.
2. **Fase S4 (Audit 6 Gate).** Valida `.staging/` con `scripts/ast_guard_validator.py` e bundle completo `GT-14` con `DAST` reale.
3. **Fase S5 (Promozione).** Promuovi solo dopo approvazione utente via `scripts/win32_2pc_engine.py` e aggiorna memoria `3-Tier` con le esclusioni.

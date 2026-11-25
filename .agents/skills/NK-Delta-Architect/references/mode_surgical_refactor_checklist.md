# Checklist JIT: MODE_SURGICAL_REFACTOR (`v1.0.0-Generation`)

> **Ambito:** Refactoring chirurgico multi-file e sviluppo Frontend in `.staging/`.
> **Bilancio:** Carica questa checklist solo per estrazioni moduli, UI o modifiche mirate.

## 1. Snapshot Preventivo e Perimetro Blocco 2
1. Leggi `nk_genome/implementation_plan.md` e i file target prima di ogni modifica.
2. Verifica lo stato equivalente ed isola i file autorizzati dal Blocco 2.
3. Crea uno snapshot preventivo con `healing_snapshot_rollback.py --create <files>` e non toccare simboli esterni.

## 2. Controlli Statici Python e Frontend (`frontend_static_checker`)
1. Limita ogni batch di scrittura o modifica a 2 file in `.staging/`.
2. Valida AST, `frontend_static_checker` e convergenza `refactor_rsi` in `.staging/`:

```powershell
python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir NK_Hub/.staging --quality-diff --allowed-files "<files>" --allowed-mutations "<simboli>" --json
python -B -u NK_Hub/scripts/rsi_convergence_engine.py --vibe-check NK_Hub/.staging --profile refactor_rsi --strict-verify --json
```

3. Usa `oracle_evaluator_l3.py --expected <spec> --actual <html_file> --json` solo per HTML e interfacce UI.

## 3. Verifica Equivalenza, Mutazione e Circuit Breaker 2-Strike
1. Esegui pytest isolato su NVMe e `builder_mutation_gate.py` su modifiche Python `Mode A/B`:

```powershell
python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --workspace-root NK_Hub --targets <test_files> --json
python -B -u NK_Hub/scripts/builder_mutation_gate.py --target-file <rel_py> --test-targets <test_files> --stage-dir NK_Hub/.staging --workspace-root NK_Hub --json
```

2. Solo in caso di failure pytest usa `auto_heal_pipeline.py --diagnose-slice`.
3. Dopo 2 tentativi falliti esegui `healing_snapshot_rollback.py --rollback <snap_id>` e segnala `2-Strike`.
4. Non promuovere file da `.staging/` alla produzione durante il refactoring.

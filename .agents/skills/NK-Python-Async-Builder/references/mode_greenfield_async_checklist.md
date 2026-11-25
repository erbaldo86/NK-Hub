# Checklist JIT: MODE_GREENFIELD_ASYNC (`v1.0.0-Generation`)

> **Ambito:** Sviluppo moduli Python asincroni in `.staging/` secondo stile Contract-First.
> **Bilancio:** Carica questa checklist per nuovi moduli backend, Pydantic v2 e SQLite WAL.

## 1. Contract-First ed Igiene I/O
1. Leggi il piano e il modulo target con `read_file` prima di scrivere.
2. Progetta prima i modelli `BaseModel` con `ConfigDict(strict=True, extra="forbid")`.
3. Scrivi funzioni singole brevi e modulari entro 500 righe totali per file.
4. Gestisci la persistenza con una singola connessione SQLite WAL tramite `deterministic_api_cache.py`.
5. Chiudi sempre i server attivi con `safe_cleanup_dev_servers.py` e vieta ogni `MagicMock`.

## 2. Cancelli Diff, Pytest NVMe e Mutazione
1. Limita ogni batch a 2 file scritti in `NK_Hub/.staging/`.
2. Valida diff AST, suite NVMe e mutation gate su `Mode A/B`:

```powershell
python -B -u NK_Hub/scripts/ast_guard_validator.py --stage-dir NK_Hub/.staging --quality-diff --allowed-files "<files>" --json
python -B -u NK_Hub/scripts/platform_runner.py --pytest-isolated --overlay-staging --workspace-root NK_Hub --targets <tests> --json
python -B -u NK_Hub/scripts/builder_mutation_gate.py --target-file <rel_py> --test-targets <tests> --stage-dir NK_Hub/.staging --workspace-root NK_Hub --json
```

## 3. Circuit Breaker 2-Strike e Diagnostica
1. Solo in caso di failure pytest diagnostica con `auto_heal_pipeline.py --diagnose-slice --target-file <file> --test-cmd "<cmd>" --cwd NK_Hub --json`.
2. Dopo 2 tentativi falliti sullo stesso guasto fermati ed invia segnalazione `2-Strike`.
3. Segnala test congelati contraddittori con `nk_transcript_tools.py report-conflict` (`0` punti onesti).

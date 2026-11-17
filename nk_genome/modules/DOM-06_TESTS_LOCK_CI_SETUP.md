# DOM-06: Test Suite, Runner NVMe Isolato e Governance (`v1.0.0-Generation`)

## 1. Perimetro Integrita e Baseline Live (`DOM-06`)

Il dominio `DOM-06` presidia integrita anti-manomissione, suite `tests/` Zero-Mock, esecuzione isolata NVMe e governance CI (`NK-GEN-1.0.0`).
Tutti i conteggi correnti di test, copertura e timing risiedono in [quality_baseline.json](../../nk_tracking/quality_baseline.json) e [oracle_lock.json](../../nk_tracking/oracle_lock.json).

| ID | Asset Reale (`NK_Hub`) | Percorso Canonico | Funzione Operativa |
| :--- | :--- | :--- | :--- |
| `G-01` | Baseline Ratchet SSOT | [quality_baseline.json](../../nk_tracking/quality_baseline.json) | Sorgente unica per test passati, branch coverage e soglie |
| `G-02` | Sigillo Anti-Manomissione | [oracle_lock.json](../../nk_tracking/oracle_lock.json) | Verifica hash SHA-256 sui moduli `scripts/` e `tests/` |
| `G-03` | Suite Permanente `tests/` | `tests/conftest.py` e `tests/test_*.py` | Caricamento condiviso e verifica comportamentale Zero-Mock |
| `G-04` | Runner Detached NVMe | `scripts/_internal/nk_common/isolated_test_runner.py` | Clona il workspace in `%TEMP%` prevenendo crash `0xC000013A` |
| `G-05` | Workflow Governance CI | `.github/workflows/ci.yml` | Controllo automatico lint, static analysis e test suite |
| `G-06` | Configurazione Pytest | `pytest.ini`, `scripts/platform_runner.py` | Flag `--pytest-isolated` e `-p no:cacheprovider` senza cache Drive FS |

## 2. Architettura Anti-Crash Windows (`0xC000013A`) e `--pytest-isolated`

La guardia `[RULE-WIN32-ISOLATED-PYTEST]` vieta ogni esecuzione diretta di `pytest` su Google Drive FS (`G:\`).

1. **Mirror NVMe:** `mirror_workspace_to_nvme()` replica codice, `.agents/`, `nk_genome/` e `.staging/` dentro `%TEMP%`.
2. **Overlay e Tombstones:** `run_detached_pytest()` supporta `--overlay-staging`, sincronizza `.staging/tests` e applica `.deleted_files.json`.
3. **Processi Detached:** `WIN32_DETACHED_FLAGS` combina `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` isolando i sottoprocessi da `conhost.exe`.
4. **Zero Cache su Disco:** `platform_runner.py --pytest-isolated` passa `-p no:cacheprovider`, `--import-mode=importlib` e `--basetemp`.
5. **Lock Cooperativo:** `PIDFileLock(acquire_timeout_sec)` in `scripts/_internal/nk_common/ledger_lock_io.py` evita deadlock su file condivisi.

## 3. Moduli di Controllo Qualita e Igiene Workspace

| ID | Modulo Python (`scripts/`) | Funzione Critica |
| :--- | :--- | :--- |
| `Q-01` | `scripts/preflight_health_check.py` | Controlla allineamento dinamico `nk_common.catalog`, SemVer, baseline e lock |
| `Q-02` | `scripts/nk_transcript_tools.py` | Esegue `lint-ste100`, audit grounding e verifica `oracle_lock.json` |
| `Q-03` | `scripts/quality_baseline_manager.py` | Blocca regressioni (`ratchet`) sulle metriche certificate in CI |
| `Q-04` | `scripts/nk_registry_indexer.py` | Emette `--verify` sulle `5` aree `DOM-01..05` e `7` shard |

1. **Loader unificato (`tests/conftest.py`):** centralizza il caricamento dinamico tra tutte le suite `tests/test_*.py`.
2. **Estensione Lock:** `oracle_lock.json` protegge i sorgenti multi-root escludendo file volatili come `PATCH_NOTES.md` e `repo_map.md`.
3. **Pulizia parent directory:** zero cache `.pytest_cache/`, file `.tmp` o log scritti dentro `Antigravity/` e `NK_Hub/`.
4. **Riferimenti shard:** [DOM-06.json](../shards/DOM-06.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

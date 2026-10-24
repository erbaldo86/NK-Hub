# Regolamento Operativo: Anti-Crash e Sicurezza I/O Windows (`v3.0.0-STE100-Unified`)

> **Ambito:** Regole tecniche operative per tutti gli agenti e i sottoprocessi su Windows e Google Drive FS.  
> **Standard:** Italiano Tecnico ASD-STE100 (`[RULE-STE100]`).

---

## 1. Sicurezza I/O Windows e Prevenzione Lock (`[WinError 32]`)
* Prima di modificare il codice, ferma i server attivi con `scripts/safe_cleanup_dev_servers.py` o `manage_task(Action="kill", TaskId="<id>")`.
* Esegui tutte le promozioni da `.staging/` a produzione tramite `scripts/win32_2pc_engine.py` con Named Mutex Win32.
* Mantieni una singola connessione SQLite WAL persistente per istanza in `scripts/deterministic_api_cache.py`.

## 2. Esecuzione Sottoprocessi, UTF-8 e Controllo Asincrono
* Esegui i sottoprocessi tramite `scripts/platform_runner.py` con `reconfigure_streams()` e il flag Python `-u` unbuffered.
* Avvia ogni comando shell o script Python in modalità non interattiva per prevenire blocchi su `stdin`.
* Imposta sempre `WaitMsBeforeAsync <= 5000` nelle chiamate `run_command` e usa `schedule()` per i timer di attesa.

## 3. Lettura File, Igiene Contesto e Compattazione
* Usa `view_file` con blocchi di massimo `800` righe tramite i parametri `StartLine` ed `EndLine`.
* Quando la sessione supera la soglia di guardia, raccomanda il comando `/compact` ed esegui `scripts/nk_session_handoff.py`.

## 4. Onestà Epistemica, Evidenza Reale e Holdout Lock
* Applica `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]` (`exit_code: 0`), `[RULE-DATA-PROVENANCE]` (`source_url`, `evidence_quote`) e `[RULE-ORACLE-LOCK]` (`oracle_lock.json`).
* Assegna `+100` al fix reale e `0` a `report-conflict` (`HALT_EPISTEMIC_CONFLICT`); vieta `PYTEST_CURRENT_TEST`, `currentframe()` e `len(grants)` (`-10.000`).

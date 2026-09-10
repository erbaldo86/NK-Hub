# 🏛️ Regolamento di Sistema: Anti-Crash & Windows I/O Safety (Nexus Keystone)

> **Ambito:** Applicato a tutte le conversazioni, agenti principali, sub-agenti e nodi di lavoro dell'ecosistema Antigravity.
> **Scopo:** Prevenire in modo proattivo e deterministico qualsiasi crash, freeze, lock di I/O (WinError 32), stallo di terminale o sovraccarico di contesto.

---

## 🛡️ 1. Windows I/O Safety & File Locking Prevention

### [GLOBAL-RULE-01] SHUTDOWN_BEFORE_EDIT
* **Direttiva Mandatoria:** Prima di applicare modifiche fisiche a file di codice sorgente (`.py`, `.js`, `.ts`, `.html`, `.css`) o a schemi/dati, è fatto divieto assoluto di mantenere server/processi demone attivi in background con `reload=True` o file watcher aperti.
* **Azione:** Verificare ed arrestare i processi attivi tramite `manage_task` (action: `kill`) o eseguire lo script di pulizia `scripts/safe_cleanup_dev_servers.py` prima dell'editing, per azzerare i conflitti `[WinError 32]` tipici del filesystem Windows NTFS e Google Drive virtuale.

### [GLOBAL-RULE-02] STAGING_AND_2PC_ATOMIC_COMMIT
* **Direttiva:** Per file critici o modifiche a codice, utilizzare il pattern di commit atomico a due fasi tramite `scripts/win32_2pc_engine.py` con buffer `.staging/`, Named Mutex Win32 e retry a backoff esponenziale con full jitter (8 tentativi), garantendo zero corruzione anche su Google Drive virtuale.

---

## 📄 2. Contesto & Large File Slicing

### [GLOBAL-RULE-03] LARGE_FILE_SLICING
* **Direttiva Mandatoria:** Sui file di grandi dimensioni (>50 KB o >800 righe), è fatto divieto agli agenti di caricare l'intero file in memoria senza range di righe o eseguire sostituzioni massive non delimitate.
* **Azione:** Utilizzare sempre `view_file` con `StartLine` ed `EndLine` focalizzati su blocchi contestuali ed applicare modifiche chirurgiche atomiche con `replace_file_content`.


---

## ⌨️ 3. Esecuzione Terminale & Zero Interactive Deadlock

### [GLOBAL-RULE-04] ZERO_INTERACTIVE_STDIN
* **Direttiva Mandatoria:** È vietato eseguire script Python o comandi shell in modalità interattiva in attesa di input da tastiera (`input()`, prompt `stdin`).
* **Azione:** Tutti gli script e comandi devono essere eseguiti in modalità non-interattiva (`--non-interactive`, `--batch`, `--yes`, `-y`) o con parametri passati direttamente da riga di comando.

---

## 💬 4. Standard Handoff & Anti-Crash Clean Prompt

### [GLOBAL-RULE-05] NK_CLEAN_PROMPT_FORMAT
* **Direttiva:** Tutti i prompt di handoff, istruzioni tra agenti, o comandi di delega devono rispettare il formato `NK-Clean-Prompt`:
  1. **Zero Comandi Slash nei Testi:** Divieto assoluto di usare prefissi slash non supportati (es. `/system_command`) nei prompt interni per evitare crash del parser dell'interfaccia utente.
  2. **Formato Lineare e Pulito:** Testo piano, istruzioni numerate e percorsi racchiusi in virgolette doppie standard `""` con slashes in avanti `G:/...`.

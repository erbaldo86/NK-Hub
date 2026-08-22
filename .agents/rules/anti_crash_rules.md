# 🏛️ Regolamento di Sistema: Anti-Crash & Windows I/O Safety (Nexus Keystone)

> **Ambito:** Applicato a tutte le conversazioni, agenti principali, sub-agenti e nodi di lavoro dell'ecosistema Antigravity.
> **Scopo:** Prevenire in modo proattivo e deterministico qualsiasi crash, freeze, lock di I/O (WinError 32), stallo di terminale o sovraccarico di contesto.

---

## 🛡️ 1. Windows I/O Safety & File Locking Prevention

### [GLOBAL-RULE-01] SHUTDOWN_BEFORE_EDIT
* **Direttiva Mandatoria:** Prima di applicare modifiche fisiche a file di codice sorgente (`.py`, `.js`, `.ts`, `.html`, `.css`) o a schemi/dati, è fatto divieto assoluto di mantenere server/processi demone attivi in background con `reload=True` o file watcher aperti.
* **Azione:** Verificare ed arrestare i processi attivi tramite `manage_task` (action: `kill`) o eseguire lo script di pulizia `scripts/safe_cleanup_dev_servers.py` prima dell'editing, per azzerare i conflitti `[WinError 32]` tipici del filesystem Windows NTFS e Google Drive virtuale.

### [GLOBAL-RULE-02] STAGING_AND_ATOMIC_REPLACE
* **Direttiva:** Per file critici o sensibili, utilizzare un pattern di scrittura atomica con staging buffer (`.staging/` o directory temporanea `%TEMP%`) e `os.replace` con retry a backoff esponenziale (max 3 tentativi, 100ms/300ms/1000ms), gestendo le latenze di sincronizzazione del client Google Drive.

---

## 📄 2. Contesto & Large File Slicing

### [GLOBAL-RULE-03] LARGE_FILE_SLICING
* **Direttiva Mandatoria:** Sui file di dimensioni superiori a 50 KB o con più di 800 righe (es. `app.js`), è fatto divieto tassativo agli agenti di:
  1. Caricare l'intero file in memoria senza range di righe.
  2. Eseguire sostituzioni massive o globali che riscrivono l'intero file.
* **Azione:** Utilizzare sempre `view_file` con `StartLine` ed `EndLine` focalizzati su blocchi <= 100 righe ed applicare modifiche chirurgiche atomiche con `replace_file_content` o `multi_replace_file_content`.

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

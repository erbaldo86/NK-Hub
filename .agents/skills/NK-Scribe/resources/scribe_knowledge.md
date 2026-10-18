# 📍 Knowledge Base Operativa: NK-Scribe (`v3.0.0-STE100-Unified`)

> **Ambito:** Regole di mirroring documentale, changelog SSOT e staging Git sicuro (`[RULE-00.2]`, `[RULE-05.1]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Consolidamento Giornaliero del Changelog (`[RULE-05.1]`)
1. Il file `nk_genome/PATCH_NOTES.md` costituisce la Single Source of Truth (SSOT) del changelog.
2. Verifica la presenza di un blocco con la data odierna `YYYY-MM-DD`.
3. Se il blocco odierno esiste, inserisci le nuove voci come punti elenco sotto l'intestazione esistente.
4. Se il blocco odierno non esiste, crea una nuova sezione con la versione semantica aggiornata.
5. Esegui sempre il mirroring atomico di `nk_genome/PATCH_NOTES.md` su `PATCH_NOTES.md` nella radice dell'Hub.

## 2. Sincronizzazione della Tetralogia e dei File Root
1. Rigenera `nk_genome/repo_map.md` tramite `python scripts/ast_repo_mapper.py --snapshot-out nk_genome/repo_map.md` (`[RULE-01.13]`).
2. Allinea `README.md` e `README.it.md` al numero reale di moduli (`30` logici, `33` file Python) e ai 68 Golden Tests (`[RULE-01.10]`).
3. Verifica il ratchet dei 68 Golden Tests in `nk_tracking/quality_baseline.json` tramite `scripts/quality_baseline_manager.py check` (`[RULE-01.10]`).
4. Verifica l'allineamento post-commit del registro O(1) tramite `python scripts/nk_registry_indexer.py --verify` (`[RULE-01.14]`).

## 3. Sequenza Git Sicura con Staging Esplicito (`U-52`)
1. Esegui `git status --short` per ispezionare lo stato dell'albero di lavoro.
2. Esegui `git add <file1> <file2>` specificando esplicitamente i soli file autorizzati. Non usare mai `git add .` per evitare l'inclusione di file temporanei o segreti.
3. Esegui `git commit -m "<messaggio in standard ASD-STE100>"`.
4. Esegui `git push origin main` solo se l'utente ha autorizzato esplicitamente la sincronizzazione remota.

# 📍 Knowledge Base Operativa: NK-Scribe-Memory (`v1.0.0-Generation`)

> **Ambito:** Regole di allineamento documentale, changelog SSOT e staging Git sicuro (`[RULE-00.2]`, `[RULE-05.1]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Consolidamento Prepend-Only del Changelog (`[RULE-05.1]`)
1. Il file `nk_genome/PATCH_NOTES.md` costituisce l'unica Single Source of Truth (SSOT) del changelog.
2. Verifica la presenza di un blocco con la data odierna `YYYY-MM-DD`.
3. Se il blocco odierno esiste, inserisci le nuove voci come punti elenco sotto l'intestazione esistente.
4. Se il blocco non esiste, anteponi in testa `## [vX.Y.Z] - YYYY-MM-DD` preservando integralmente tutte le sezioni storiche.

## 2. Sincronizzazione della Pentad Sovrana 4+1 e dei Manuali
1. Rigenera `.staging/nk_genome/repo_map.md` tramite `python -u scripts/ast_repo_mapper.py --snapshot-out .staging/nk_genome/repo_map.md` (`[RULE-01.13]`).
2. Allinea `nk_docs_and_setup/README.md`, `README.it.md` e `GUIDA_INSTALLAZIONE.md` ai moduli certificati e a `nk_tracking/quality_baseline.json`.
3. Verifica il ratchet Schema `v2` su `quality_baseline.json` (`MIN_GOLDEN_TESTS_FLOOR = 93`, `no_metric_may_worsen`). Esegui `python -u scripts/quality_baseline_manager.py --check-only --live --with-coverage` (`[RULE-01.10]`).
4. Verifica l'integrità post-commit del registro O(1) tramite `python -u scripts/nk_registry_indexer.py --verify` (`[RULE-01.14]`).

## 3. Sequenza Git Sicura con Staging Esplicito (`U-52`)
1. Esegui `git status --short` per ispezionare lo stato dell'albero di lavoro.
2. Esegui `git add <file1> <file2>` specificando esplicitamente i soli file verificati, senza usare mai `git add .` o `git add -A`.
3. Esegui `git commit -m "<messaggio in standard ASD-STE100>"`.
4. Esegui `git push origin main` solo su autorizzazione esplicita dell'utente.

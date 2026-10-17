# 🌐 Matrice TAS Livello 3: Audit Sistema Full-Stack e Cascade (`tas_l3_fullstack_system_audit.md`)

> **Ambito Operativo:** Sistema generale Full-Stack completo (`UI`, `API`, `Database`), sicurezza end-to-end e isolamento.  
> **Nodo Proprietario:** `NK-Security-Auditor` (`v3.0.0-STE100-Unified`, 100% Sola Lettura `GT-14`).  
> **Architettura:** Verifica Deterministica Full-Stack + Scenari Multi-Step (`stresser_free_scenarios`) e `Cascade L3 -> L2 -> L1`.

---

## 1. Fase A Deterministica (UI-API-DB, DAG Database e Sicurezza Web)

1. **Rilevamento `Data-Contract Drift` tra UI, API e Database:**
   * Verifica la coerenza dei nomi dei campi, dei tipi di dato e dei vincoli di obbligatorietà lungo l'intera catena `UI -> API -> DB`.
   * Esegui `python scripts/oracle_evaluator_l3.py --expected <atteso> --actual <effettivo> --json` per validare la struttura DOM L3.
2. **Invariante Topologico Database (`is_strict_dag_db`):**
   * Verifica che il grafo delle chiavi esterne (Foreign Key) del database formi un DAG rigoroso (`is_strict_dag_db == True`).
   * Rileva e blocca qualsiasi ciclo di dipendenza tra tabelle che possa causare deadlock in inserimento o cancellazione.
3. **Controlli Deterministici XSS, CSRF, Auth e Segreti:**
   * Verifica la sanitizzazione degli output HTML nel DOM per prevenire vulnerabilità Cross-Site Scripting (XSS).
   * Verifica la presenza di protezioni Cross-Site Request Forgery (CSRF) e di controlli di autorizzazione su ogni endpoint mutante.
   * Verifica l'assenza di segreti hardcoded (`credentials.json`, `token.json`, chiavi API) e di vulnerabilità Path Traversal.

---

## 2. Fase B Probabilistica (`stresser_free_scenarios` e `Cascade L3 -> L2 -> L1`)

1. **Scenari di Attacco Multi-Step (`stresser_free_scenarios`):**
   * Progetta catene di attacco end-to-end che combinano sequenze di input utente, chiamate API fuori ordine e manipolazioni di stato.
   * Valida empiricamente gli scenari nella Shadow Sandbox tramite `python scripts/dast_sandbox_runner.py --script --json`.
   * Promuovi gli scenari che violano le invarianti di sicurezza in `poc_confirmed_exploits` e registra il drift in `semantic_drift_findings`.
2. **Attivazione della Modalità `Cascade L3 -> L2 -> L1`:**
   * Quando un test o scenario `L3` fallisce, attiva immediatamente la discesa diagnostica `Cascade L3 -> L2 -> L1`.
   * **Passo 1 (`L3 -> L2`):** Ispeziona il contratto IPC o API intermedio usando [`tas_l2_ipc_contract_audit.md`](tas_l2_ipc_contract_audit.md) per isolare il payload difettoso.
   * **Passo 2 (`L2 -> L1`):** Localizza il modulo e la riga esatta del difetto usando [`tas_l1_module_audit.md`](tas_l1_module_audit.md).
   * Esporta la traccia completa della cascata in `%TEMP%\nk_diagnostics\` e invia il report sintetico via `send_message`.

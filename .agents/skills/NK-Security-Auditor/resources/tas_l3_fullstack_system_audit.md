# 🌐 Matrice TAS Livello 3: Audit Sistema Full-Stack e Cascade (`tas_l3_fullstack_system_audit.md`)

> **Ambito Operativo:** Sistema generale Full-Stack completo (`UI`, `API`, `Database`), sicurezza end-to-end e isolamento.  
> **Nodo Proprietario:** `NK-Security-Auditor` (`v1.0.0-Generation`, 100% Sola Lettura `GT-14`).  
> **Architettura:** Verifica Deterministica Dual-Execution + Scenari Multi-Step (`stresser_free_scenarios`) e `Cascade L3 -> L2 -> L1`.

---

## 1. Fase A Deterministica (UI-API-DB, DAG Database e Sicurezza Web)

1. **Rilevamento `Data-Contract Drift` tra UI, API e Database:**
   * Verifica la coerenza di campi, tipi e vincoli obbligatori lungo la catena `UI -> API -> DB`.
   * Valuta l'esito di `python -u scripts/oracle_evaluator_l3.py --expected <atteso> --actual <effettivo> --json` e il DOM browser.
2. **Invariante Topologico Database (`is_strict_dag_db`):**
   * Verifica che il grafo delle chiavi esterne formi un DAG rigoroso (`is_strict_dag_db == True`) senza cicli.
3. **Controlli Deterministici XSS, CSRF, Auth e Segreti:**
   * Verifica sanitizzazione HTML anti-XSS, protezioni CSRF, autorizzazione endpoint mutanti, assenza di segreti hardcoded e Path Traversal.

---

## 2. Fase B Probabilistica (`stresser_free_scenarios` e `Cascade L3 -> L2 -> L1`)

1. **Scenari di Attacco Multi-Step (`stresser_free_scenarios`):**
   * Progetta catene di attacco end-to-end combinando input utente, chiamate API fuori ordine e manipolazioni di stato.
   * Valuta gli scenari eseguiti dall'Orchestratore con `python -u scripts/dast_sandbox_runner.py --script <poc_py> --timeout 30 --json`.
   * Registra gli exploit confermati in `poc_confirmed_exploits` e il drift in `semantic_drift_findings`.
2. **Attivazione della Modalità `Cascade L3 -> L2 -> L1`:**
   * Quando uno scenario `L3` fallisce, attiva subito la discesa diagnostica verso [`tas_l2_ipc_contract_audit.md`](tas_l2_ipc_contract_audit.md) e [`tas_l1_module_audit.md`](tas_l1_module_audit.md).
   * Invia il report sintetico della cascata (`< 1.800` caratteri) via `send_message` leggendo la telemetria temporanea in `nk_diagnostics/`.

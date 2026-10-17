# 🔗 Matrice TAS Livello 2: Audit Contratti IPC e Multi-Agente (`tas_l2_ipc_contract_audit.md`)

> **Ambito Operativo:** Interazioni tra moduli, contratti IPC, schemi API REST/RPC e handoff dello sciame multi-agente.  
> **Nodo Proprietario:** `NK-Security-Auditor` (`v3.0.0-STE100-Unified`, 100% Sola Lettura `GT-14`).  
> **Architettura:** Allineamento Topologico Deterministico (`TOPOLOGICAL_IPC_ALIGNMENT`) + Analisi Concorrenza Probabilistica.

---

## 1. Fase A Deterministica (`TOPOLOGICAL_IPC_ALIGNMENT`)

1. **Allineamento Tripartito Mermaid, OpenAPI/JSON e Pydantic:**
   * Verifica la corrispondenza esatta (`TOPOLOGICAL_IPC_ALIGNMENT`) tra i diagrammi architetturali Mermaid, gli schemi OpenAPI/JSON e le classi Pydantic v2.
   * Segnala come `contract_violations` qualsiasi campo presente nello schema API ma assente nel modello di validazione.
2. **Rigidità dei Contratti Pydantic v2 (`scripts/schemas/nk_ipc_contracts.py`):**
   * Verifica che ogni modello adotti `model_config = ConfigDict(strict=True, extra="forbid")`.
   * Verifica l'assenza del tipo `Any` non vincolato nei payload scambiati tra processi o agenti.
   * Verifica che la profondità massima di annidamento dei payload JSON sia `<= 3` livelli (`max_json_depth <= 3`).
3. **Limiti di Payload e Trasporto Swarm (`[RULE-SWARM-HYGIENE]`):**
   * Verifica il rispetto della soglia MSS di `1.800` caratteri e dell'Hard Cap MTU di `2.000` caratteri (`GT-04`).
   * Verifica l'integrità delle scritture atomiche 2PC tramite `win32_atomic_replace` e lock di sincronizzazione.

---

## 2. Fase B Probabilistica (Concorrenza, Handoff e Referee Gate 2)

1. **Caccia a Race Condition e Corruzione di Stato Condiviso:**
   * Analizza accessi concorrenti a file `.jsonl`, cache condivise o variabili globali privi di `threading.Lock` o mutex Win32.
   * Verifica possibili finestre TOCTOU (Time-of-Check to Time-of-Use) durante la creazione o promozione dei file in `.staging/`.
2. **Analisi di Cascading Failure e Deadlock:**
   * Individua attese circolari tra task, assenza di timeout espliciti nelle chiamate IPC e mancata propagazione degli errori.
   * Verifica che il fallimento di un nodo L1 non blocchi indefinitamente l'orchestratore L2 (`[RULE-REACTIVE-SILENCE]`).
3. **Violazioni di Stato negli Handoff Multi-Agente:**
   * Controlla perdite di contesto (`semantic_drift_findings`), desincronizzazione degli identificativi di sessione e replay di messaggi obsoleti.
   * Verifica nel Referee Sandbox (`python scripts/dast_sandbox_runner.py --script`) la riproducibilità delle race condition sospette.
   * Registra ogni difetto confermato in `%TEMP%\nk_diagnostics\` incrementando `contract_violations` o `poc_confirmed_exploits`.

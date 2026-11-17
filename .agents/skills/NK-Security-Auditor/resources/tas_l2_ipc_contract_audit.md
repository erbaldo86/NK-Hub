# 🔗 Matrice TAS Livello 2: Audit Contratti IPC e Multi-Agente (`tas_l2_ipc_contract_audit.md`)

> **Ambito Operativo:** Interazioni tra moduli, contratti IPC, schemi API REST/RPC e handoff dello sciame multi-agente.  
> **Nodo Proprietario:** `NK-Security-Auditor` (`v1.0.0-Generation`, 100% Sola Lettura `GT-14`).  
> **Architettura:** Allineamento Topologico (`TOPOLOGICAL_IPC_ALIGNMENT`) + Analisi Concorrenza Dual-Execution.

---

## 1. Fase A Deterministica (`TOPOLOGICAL_IPC_ALIGNMENT`)

1. **Allineamento Tripartito Mermaid, OpenAPI/JSON e Pydantic:**
   * Verifica la corrispondenza 1:1 tra i diagrammi Mermaid, gli schemi OpenAPI/JSON e le classi Pydantic v2.
   * Segnala come `contract_violations` ogni campo presente nello schema API ma assente nel modello di validazione.
2. **Rigidità dei Contratti Pydantic v2 (`scripts/schemas/nk_ipc_contracts.py`):**
   * Verifica `model_config = ConfigDict(strict=True, extra="forbid")`, assenza di `Any` e profondità JSON `<= 3`.
3. **Limiti di Payload e Trasporto Swarm (`[RULE-SWARM-HYGIENE]`):**
   * Verifica la soglia MSS di `1.800` caratteri, l'Hard Cap MTU di `2.000` caratteri (`GT-04`) e l'atomicità 2PC.

---

## 2. Fase B Probabilistica (Concorrenza, Handoff e Referee Gate 2)

1. **Race Condition e Stato Condiviso:**
   * Analizza accessi concorrenti a file `.jsonl` o cache privi di `threading.Lock` o mutex Win32 e finestre TOCTOU.
2. **Cascading Failure e Deadlock:**
   * Individua attese circolari, assenza di timeout IPC e blocchi sull'orchestratore (`[RULE-REACTIVE-SILENCE]`).
3. **Handoff Multi-Agente e Referee Gate 2:**
   * Controlla `semantic_drift_findings` e valuta il Referee con `python -u scripts/dast_sandbox_runner.py --script <poc_py> --timeout 30 --json`. L'Orchestratore salva l'output nella directory temporanea `nk_diagnostics/`.

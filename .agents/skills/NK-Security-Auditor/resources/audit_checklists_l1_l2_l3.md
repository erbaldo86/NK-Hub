# 🛡️ Matrice di Routing Settoriale Universale e Checklist TAS-Self (`v3.0.0-STE100-Unified`)

> **Nodo Proprietario:** `NK-Security-Auditor` (Macro-Fase 2 del Protocollo CRV 4.0).  
> **Modalità Operativa:** 100% Sola Lettura (`[RULE-00.1 / RULE-04.4]`). Nessun nodo Fixer opera durante l'audit (`GT-14`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, massimo 20 parole per frase).

---

## 1. Matrice di Routing Settoriale Universale (`L1`, `L2`, `L3`)

| Livello TAS | Dominio Target | Matrice Modulare Dedicata | Modalità Neuro-Simbolica |
| :--- | :--- | :--- | :--- |
| **Livello 1 (`L1`)** | Singolo modulo Python, funzione backend, prompt o `SKILL.md` | [`tas_l1_module_audit.md`](tas_l1_module_audit.md) | Fase A Deterministica + Fase B PoC Locale |
| **Livello 2 (`L2`)** | Contratti IPC, API REST/RPC, handoff multi-agente e Win32 | [`tas_l2_ipc_contract_audit.md`](tas_l2_ipc_contract_audit.md) | `TOPOLOGICAL_IPC_ALIGNMENT` + Concorrenza |
| **Livello 3 (`L3`)** | Sistema Full-Stack completo (`UI`, `API`, `Database`) | [`tas_l3_fullstack_system_audit.md`](tas_l3_fullstack_system_audit.md) | `Data-Contract Drift` + `Cascade L3 -> L2 -> L1` |
| **Auto-Audit (`TAS-Self`)** | Governance interna, regole core e skill di `NK-Hub` | Sezione 2 di questo documento | Guardie `GT-01..GT-14` + CoVe CLI AST Gate |

---

## 2. Protocollo Ibrido a 3 Gate (`Opzione 1A + 2C`)

1. **Gate 0 e Gate 1 (Sequenza Deterministica):** Esegui i controlli sintattici, strutturali e SAST senza alcuna discrezionalità.
2. **Esplorazione Probabilistica (`heuristic_findings`):** Formula ipotesi di vulnerabilità logiche o architetturali non coperte da regole statiche.
3. **Gate 2 (Referee PoC Deterministico):** Esegui uno script Proof-of-Concept nella Shadow Sandbox (`scripts/dast_sandbox_runner.py --script`).
4. **Regola di Promozione Difetti:** Converti un sospetto euristico in `poc_confirmed_exploits` solo quando il Referee PoC dimostra il fallo.

---

## 3. Checklist `TAS-Self` (Igiene Interna di `NK-Hub`)

### 3.1 Conformità Prompt, Regole e `SKILL.md`
1. **Frontmatter YAML:** Verifica la presenza di `name`, `description`, `version: "3.0.0-STE100-Unified"` e `thinking_level: "HIGH"`.
2. **Confinamento `<strict_boundaries>`:** Controlla che ogni skill dichiari i vincoli operativi e il divieto di scrittura per gli Auditor (`GT-14`).
3. **Standard ASD-STE100 (`[RULE-STE100]`):**
   * Verifica che tutte le frasi contengano al massimo 20 parole.
   * Verifica l'assenza totale di trattini lunghi, medi o spaziati nel testo.
   * Verifica l'uso del termine canonico *"Tetralogia Sovrana"* (`4/4`).
4. **Integrità Link e CoVe CLI Gate:**
   * Verifica che ogni file in `resources/` o `references/` sia linkato nel proprio `SKILL.md`.
   * Verifica che ogni flag CLI citato nei file Markdown esista nell'AST dello script Python corrispondente.
5. **Passive Data Tagging (`[RULE-08]`):** Verifica che gli input non fidati siano racchiusi nel tag `<passive_data_context>`.

### 3.2 Sicurezza Win32, Zero-Mock e Isolamento
1. **Puntatori Win32 a 64-bit (`ctypes`):** Verifica che `CreateMutexW`, `OpenProcess`, `CloseHandle` e `MoveFileExW` dichiarino `argtypes` e `restype` (`ctypes.c_void_p`).
2. **Guardia Zero-Mock (`[RULE-01.2]`):** Verifica l'assenza di `unittest.mock.MagicMock`, `@patch` o stub fittizi nella suite di test.
3. **Isolamento Progetti Esterni (`[RULE-PROJECT-ISOLATION]`):** Verifica l'assenza di codice applicativo esterno nella radice di `NK-Hub`.
4. **Calcolo Vettore Difetti RSI ($\text{SAST}_k$):** Registra ogni violazione in `%TEMP%\nk_diagnostics\` e restituisci `FAIL` (`exit_code: 1`) se $\text{SAST}_k > 0$.

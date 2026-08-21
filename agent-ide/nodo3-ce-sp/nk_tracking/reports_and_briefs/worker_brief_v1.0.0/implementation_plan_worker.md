# 📋 Implementation Plan: Timeline Bi-Direzionale Perno-Centrata (Worker Brief v1.0.0)

🛡️ [NK-ASSIST - NK-App-Concept-Architect]

> [!NOTE]
> **Ambito Architetturale:** Piano attuativo operativo atomico e strategie di testing per l'implementazione della Timeline Bi-Direzionale Perno-Centrata nel **Nodo 3 (CE & SP Engine)**.
> **Stato:** PROPOSTA WORKER INDIPENDENTE (Zero-Bias Briefing)

---

## 🎯 1. Fasi Operative Atomiche (CRV 3.0 Protocol Compliant)

L'implementazione verrà suddivisa in 5 lotti operativi atomici, ciascuno subordinato al superamento dei test e dei Gate del protocollo CRV 3.0:

### 📦 LOTTO 1: Backend DTO & Ingestion Intelligence Multi-Anno
- **Task 1.1**: Modifica DTO Pydantic v2 in [`pydantic_schemas.py`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/backend/pydantic_schemas.py) per supportare `pivot_year` e il dizionario esteso degli anni rilevati (`detected_years`).
- **Task 1.2**: Aggiornamento di `create_ingestion_result` in [`ingestion_parser_service.py`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/backend/ingestion_parser_service.py) per includere il mapping di tutti gli anni presenti nel documento ERP/ODS.
- **Gate Check**: Esecuzione SAST `fast_sast_engine.py` e unit test backend in Shadow Sandbox.

### 📦 LOTTO 2: Frontend State Engine & Re-Pivoting Core
- **Task 2.1**: Estensione dell'oggetto `state` in [`app.js`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/app.js) (`pivotYear`, `scopePastYears`, `scopeFutureYears`).
- **Task 2.2**: Scrittura helper deterministici: `setPivotYear(y0)`, `getTimelineYears()`, `shiftPivot(delta)`.
- **Task 2.3**: Aggiornamento meccanismi di sincronizzazione dati tra `state.records[year]` e gli schemi CE/SP.
- **Gate Check**: Ispezione dello stato JS via console DevTools senza regressione sui dati caricati.

### 📦 LOTTO 3: Modale Ingestion HITL per Elezione Anno Perno ($Y_0$)
- **Task 3.1**: Aggiornamento del markup in [`index.html`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/index.html) per la modale `#pivotYearSelectionModal` con carte opzioni visive.
- **Task 3.2**: Event handling in `app.js` (`showPivotYearSelectionModal`, `confirmPivotSelection`).
- **Gate Check**: Simulazione upload file multi-anno (es. `Conto Economico 2025.ods` e `Stato Patrimoniale 2025.ods`) e verifica dell'intercettazione HITL.

### 📦 LOTTO 4: Riprogettazione dei 4 Moduli UI
- **Task 4.1 (Modulo 1 - KPI Toolbar)**: Scrittura di `renderKpiToolbar()` con pulsanti $Y_{-k}$, $\star Y_0$, $Y_{+k}$ e azioni dinamiche.
- **Task 4.2 (Modulo 2 - Orizzonte Visibile)**: Aggiunta controlli Scope per l'espansione indipendente di $m_{past}$ e $m_{future}$.
- **Task 4.3 (Modulo 3 - Intestazioni Tabelle)**: Aggiornamento rendering header in `renderCETable()` e `renderSPTables()` con doppio badge ($Y$ relativo + Anno solare).
- **Task 4.4 (Modulo 4 - Ratio Dropdown)**: Ancoraggio dei ratios ad $Y_0$ in `renderKpiCards()`.
- **Task 4.5 (Design System CSS)**: Definizione token e classi CSS in [`styles.css`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/styles.css).
- **Gate Check**: Ispezione rendering HTML e verifica assenza di flickering o sovrapposizioni grafiche.

### 📦 LOTTO 5: E2E Testing, Zero Data Loss Audit & Teardown
- **Task 5.1**: Esecuzione suite di test [`test_statutory_ingestion_verification.py`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/backend/test_statutory_ingestion_verification.py).
- **Task 5.2**: Esecuzione simulazione Pareto [`run_3tier_hitl_simulation.py`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/test_suite/run_3tier_hitl_simulation.py).
- **Task 5.3**: Audit di non-regressione ed inserimento Proof-of-Work in `session_anchor.jsonl`.
- **Task 5.4**: Bonifica e chiusura di tutti i processi server di test.

---

## 🧪 2. Strategia di Validazione & Testing

| Tipo Test | Target File / Componente | Verdetto Atteso |
| :--- | :--- | :--- |
| **Backend Unit Verification** | `test_statutory_ingestion_verification.py` | Exit Code 0, 3/3 Test Passed |
| **3-Tier Simulation & Quadratura** | `run_3tier_hitl_simulation.py` | Read Rate 100%, SP Diff €0.00 |
| **Dynamic Re-Pivoting Test** | Ingestion file multi-anno + click cambio $Y_0$ | Aggiornamento reattivo senza ricaricamento |
| **Anti-Regression Math Engine** | `civil_code_math_engine.py` | 0 modifiche, 100% retrocompatibilità |

---

## 🛡️ 3. Mitigazione Rischi e Sicurezza

1. **Zero Data Loss Guarantee**: Nessun valore numerico viene troncato o modificato durante il re-indexing relativo.
2. **Backward Compatibility**: I file JSON salvati con versioni precedenti (senza `pivot_year`) assumono automaticamente $Y_0 = \text{base\_year}$ (default $2025$).
3. **No main_api_server Breakage**: L'interfaccia OpenAPI resta stabile con contratti retrocompatibili.

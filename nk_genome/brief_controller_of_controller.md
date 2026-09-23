# 🏛️ BRIEF STRATEGICO: "CONTROLLORE DEL CONTROLLORE" (NK v2.5.2)

> **Ambito:** Allineamento Normativo, Stress-Testing e Auto-Healing Sistemico  
> **Target:** Audit e riparazione dell'operato di Conversazione 2 (`6796d3ec-96b9-4183-8370-9bf4e30244a0`) e ripristino dell'integrità del workspace `NK-Hub`.  
> **Status:** APPROVED FOR AUTOPILOT EXECUTION  

---

## 1. Obiettivi e Scopo della Missione
1. **Analisi Critica (RCA):** Ispezionare la catena di decisioni di Conv 2 che ha portato a un ritardo di avvio (11+ min), all'omissione della Master Dashboard canonica, al bypass di `.staging/` e del commit 2PC, all'assenza di test per `[RULE-00.5]` e all'inversione cronologica del versioning in `PATCH_NOTES.md`.
2. **Stress-Testing Multidimensionale:** Sottoporre a stress sia i flussi normativi (`[RULE-00.5]`), sia i componenti di core (`scripts/micro_hud_renderer.py`, `scripts/auto_heal_pipeline.py`, `scripts/win32_2pc_engine.py`, `scripts/oracle_evaluator_l3.py`).
3. **Cicli di Auto-Healing Chirurgico:** Qualsiasi anomalia riscontrata deve essere riparata via Builder operante in `.staging/`, sottoposta a validazione AST Guard e test oracolo, prima del commit atomico.
4. **Trasparenza e Reporting "Prima vs Dopo":** Fornire all'utente un quadro oggettivo dello stato del sistema prima dell'intervento e dopo il ripristino completo della conformità NK.

---

## 2. Matrice delle Regole NK Coinvolte
- **`[RULE-PROJECT-ISOLATION]`:** Mantenere NK-Hub incontaminato da codice applicativo esterno.
- **`[RULE-00]` ZERO_UNAUTHORIZED_FILE_MODIFICATION_MANDATE:** Tutte le modifiche di codice devono passare da `.staging/`.
- **`[RULE-00.4]` SESSION_BOOTSTRAP_GATE:** Tempo di avvio garantito $< 120$ ms.
- **`[RULE-00.5]` UNIFIED_ONBOARDING_DASHBOARD_MANDATE:** Invariante deterministica per tutti i trigger di avvio sessione con 15 nodi canonici e guida a due vie.
- **`[RULE-01]` UNIVERSAL_DDI_MANDATE:** Delegare test e modifiche profonde a subagenti; preservare la pulizia del contesto.
- **`[RULE-01.1]` PROTOCOLLO CRV 4.0:** Flusso a 4 macrofasi: Staging -> Audit Read-Only -> 2PC Atomic Commit -> Teardown.
- **`[RULE-01.10]` PERMANENT_TEST_SUITE_MANDATE:** 100% test pass rate permanente.
- **`[RULE-05.1]` CHANGELOG_SSOT:** Consolidamento semantico delle release.

---

## 3. Strategia di Esecuzione Multi-Agentica
1. **Auditor / Stress-Tester Worker (`CriticAuditWorker`):** Esegue test di carico, verifica i trigger di onboarding ed evidenzia failure points dei componenti core.
2. **Builder Worker (`NK-Python-Async-Builder`):** Riceve le specifiche di riparazione, opera unicamente in `.staging/` e produce codice rigorosamente conforme a Pydantic v2 e typing moderno.
3. **Ratchet & 2PC Orchestrator (`NK-Master-Hub`):** Convalida l'AST Guard, esegue `win32_2pc_engine.py --promote-staging`, sincronizza il working tree git e consolida la baseline di qualità al 100%.

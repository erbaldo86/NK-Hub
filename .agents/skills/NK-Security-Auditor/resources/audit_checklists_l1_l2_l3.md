# 🛡️ Matrice di Routing Settoriale Universale e Checklist TAS-Self (`v1.0.0-Generation`)

> **Nodo Proprietario:** `NK-Security-Auditor` (Macro-Fase 2 CRV 6.0, `Dual-Execution GT-14`).  
> **Modalità Operativa:** 100% Sola Lettura (`EnableWriteTools=False`, zero `write_file`, `edit_file` o `run_command` diretti).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, massimo 20 parole per frase).

---

## 1. Matrice di Routing Settoriale Universale (`L1`, `L2`, `L3`)

| Livello TAS | Dominio Target | Matrice Modulare Dedicata | Modalità Neuro-Simbolica |
| :--- | :--- | :--- | :--- |
| **Livello 1 (`L1`)** | Singolo modulo Python, funzione backend, prompt o `SKILL.md` | [`tas_l1_module_audit.md`](tas_l1_module_audit.md) | Fase A Deterministica + Fase B PoC Locale |
| **Livello 2 (`L2`)** | Contratti IPC, API REST/RPC, handoff multi-agente e Win32 | [`tas_l2_ipc_contract_audit.md`](tas_l2_ipc_contract_audit.md) | `TOPOLOGICAL_IPC_ALIGNMENT` + Concorrenza |
| **Livello 3 (`L3`)** | Sistema Full-Stack completo (`UI`, `API`, `Database`) | [`tas_l3_fullstack_system_audit.md`](tas_l3_fullstack_system_audit.md) | `Data-Contract Drift` + `Cascade L3 -> L2 -> L1` |
| **Auto-Audit (`TAS-Self`)** | Governance interna, regole core e skill di `NK_Hub` | Sezione 3 di questo documento | Guardie `GT-01..GT-14` + CoVe CLI AST Gate |

---

## 2. Protocollo Ibrido Dual-Execution a 3 Gate

1. **Gate 0 e Gate 1:** Analizza i risultati sintattici e SAST dell'Orchestratore nella directory temporanea `nk_diagnostics/`.
2. **Esplorazione Probabilistica (`heuristic_findings`):** Formula ipotesi di vulnerabilità logiche o architetturali non coperte da regole statiche.
3. **Gate 2 (Referee PoC):** Valuta l'esito del PoC eseguito dall'Orchestratore con `python -u scripts/dast_sandbox_runner.py --script <poc_py> --timeout 30 --json`.
4. **Promozione Difetti:** Converti un sospetto in `poc_confirmed_exploits` solo quando il Referee PoC dimostra il fallo reale.

---

## 3. Checklist `TAS-Self` (Igiene Interna di `NK_Hub`)

1. **Frontmatter YAML Unificato:** Verifica `name`, `description`, `version: "1.0.0-Generation"`, `role_identity`, `domain_id`, `tools` e zero card YAML duplicate.
2. **Confinamento `GT-14` e Isolamento Foglia:** Vieta scritture sugli Auditor read-only. Imposta `enable_subagent_tools: false` ed `enable_mcp_tools: false` sui sub-agenti foglia senza tool fantasma.
3. **Standard ASD-STE100:** Verifica frasi attive `<= 20` parole, zero trattini spaziati e link validi verso `resources/` e `references/`.
4. **CoVe CLI e Win32:** Verifica i flag CLI sull'AST di `scripts/*.py` e `ctypes.c_void_p` a 64-bit. Vieta ogni `MagicMock` e isola le app esterne.

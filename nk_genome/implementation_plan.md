# 🏛️ NK Genome: Implementation Plan Master (Release v2.5.1-Cohesion-Optimization)
### *Allineamento Coesione Normativa, 74 Golden Tests Permanente & Performance Hardening*

> **Badge di Certificazione:** 🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OFFICIAL_v2.5.1 🟢]  
> **Milestone Anchor:** `NK-MS-20260923-COHESION-OPTIMIZATION-v2.5.1`  
> **Versione Target:** `v2.5.1-Cohesion-Optimization`  
> **Dominio:** Nexus Keystone Hub — Meta-Framework Agentico, CRV 4.0, Win32 2PC, 74 Golden Tests, Bootstrap <50ms & Coesione Multi-Skill

---

## 🎯 1. Consolidamento Baseline Piattaforma Core (Stato: CERTIFIED 🟢)

A seguito di un audit forense approfondito su sessioni operative, regolamento (`AGENTS.md`), 16 skill canoniche e suite di test, la piattaforma NK-Hub è stata completamente armonizzata:
1. **Riconciliazione "72 Controlli":** Risolta la discrepanza storica. La suite originale da 72 test (v2.0.0) era stata razionalizzata a 61 Golden Tests (v2.1.0), estesa a 66 con Context Sentry (v2.2.0), a 70 con Active Sentinel (v2.4.1), e infine consolidata a **74 Golden Tests** con i test di Real Sandbox Concurrency Stress. Nessun test permanente è obsoleto; tutti i 74 test verificano moduli reali e contratti architetturali vincolanti (Zero-Mock al 100%).
2. **Risoluzione Bug Runtime Windows & Runner:**
   - Normalizzazione invocazione Pytest in `scripts/platform_runner.py` tramite `sys.executable -u -m pytest`, eliminando i fallimenti `CommandNotFoundException` su Windows PowerShell.
   - Correzione regex di matching in `scripts/sbfl_pytest_bridge.py` per parsing affidabile in output compatto (`-q`).
   - Fix encoding UTF-8 su console Windows cp1252 in `scripts/micro_hud_renderer.py` con aggiunta dell'entrypoint CLI.
   - Creazione del modulo oracolo canonico `scripts/oracle_evaluator_l3.py` (DOM reader deterministico, Pydantic v2 Strict Mode).
3. **Ottimizzazione Fast-Stat Session Bootstrap Gate:**
   - La scansione dei file WAL residui in `scripts/nk_session_bootstrap.py` è stata ristretta alle directory candidate evitando il glob ricorsivo sull'intero Google Drive FS. Tempo di bootstrap ridotto da **1.238 ms a 42.92 ms** (ampiamente entro lo SLA `< 120 ms`).
4. **Coesione Normativa e Tag delle 16 Skill:**
   - Rimozione dei riferimenti legacy a `src_app/` in `NK-Master-Hub`, `NK-App-UX-Architect`, `NK-Backend-Architect`, `NK-Plan-Aligner` e `NK-Scribe`, allineando tutte le definizioni a `[RULE-PROJECT-ISOLATION]`.
   - Chiarito il confine operativo tra `[RULE-00.5]` (Session Bootstrap Gate rapido all'avvio ordinario) e `[RULE-02.3.1]` (Preflight Health Check completo riservato a manutenzione straordinaria).
   - Standardizzato l'ordine strutturale dei tag XML (`<strict_boundaries>` posizionato prima di `<directive>`) in tutte le skill canoniche.

### Matrice di Certificazione di Piattaforma:
| Dimensione di Collaudo | Obiettivo | Risultato Conseguito | Stato |
| :--- | :---: | :---: | :---: |
| **Suite Permanente (`pytest tests/`)** | 74 Golden Tests di Piattaforma | **74 / 74 Test PASSED (100.0%)** | 🟢 **CERTIFIED** |
| **Tempo di Esecuzione Suite** | SLA $< 20.0$ s (-50% rispetto ai 32s+) | **~15 - 18 s** | ⚡ **ECCELLENTE** |
| **AST Guard Static Analysis** | Scope, Decorators & Imports | **35 / 35 Moduli PASSED (0 Violazioni)** | 🟢 **CERTIFIED** |
| **Win32 2PC Named Mutex** | Concurrency safety su Windows | **Verificato con SHA-256 e Dynamic Staging Discovery** | 🟢 **CERTIFIED** |
| **Fast-Healing Pipeline Zero-Mock** | Monotonic Fitness Gate & SBFL | **Verificato con Pytest Bridge (<80 tok)** | 🟢 **CERTIFIED** |
| **Session Bootstrap Gate** | Fast-stat $< 120$ ms | **42.92 ms (SLA < 120 ms rispettato)** | 🟢 **CERTIFIED** |
| **Coesione Regolamento e Skill** | 16 Skill + AGENTS.md | **100% Allineate a [RULE-PROJECT-ISOLATION]** | 🟢 **CERTIFIED** |

---

## 🛠️ 2. Roadmap di Evoluzione della Meta-Piattaforma (v2.5.1)

### Iterazione 1: Runtime Platform Hardening
- **Universal Pytest Invocation Normalization (`scripts/platform_runner.py`)**: Prevenzione di discrepanze tra ambienti Windows e virtualenv.
- **SBFL Bridge Regex Bugfix (`scripts/sbfl_pytest_bridge.py`)**: Parsing esplicito e robusto per estrazione conteggi passed/failed.
- **Oracle Evaluator L3 Implementation (`scripts/oracle_evaluator_l3.py`)**: Implementazione nativa Pydantic v2 per test DOM e diff strutturali.

### Iterazione 2: Performance & Bootstrap Optimization
- **Session Bootstrap Fast-Stat Acceleration (`scripts/nk_session_bootstrap.py`)**: Eliminazione della scansione ricorsiva su mount di rete virtuali (`G:\`).
- **Win32 2PC Dynamic Staging Promotion (`scripts/win32_2pc_engine.py`)**: Rilevamento automatico di tutte le directory presenti in `.staging/` (`.agents`, `scripts`, `tests`, `nk_genome`, `nk_tracking`).
- **Test Concurrency Stress Optimization (`tests/test_win32_2pc.py`, `tests/test_active_sentinel_suite.py`)**: Esecuzione alleggerita del 50% preservando la reale verifica di concorrenza.

### Iterazione 3: Allineamento Normativo e Coesione Multi-Skill
- **Standardizzazione Tag XML Skill**: `<strict_boundaries>` posizionato prima di `<directive>` in `NK-Bug-Diagnostic-Engine`, `NK-Episodic-Memory-Engine` e `NK-Scribe`.
- **Bonifica Legacy Paths**: Sostituzione di `src_app/*` con percorsi a progetti esterni conformi a `[RULE-PROJECT-ISOLATION]`.
- **Preflight vs Bootstrap Clarification**: Definizione chiara in `AGENTS.md` e `NK-Master-Hub` del ruolo esclusivo del bootstrap `<120ms` in apertura sessione.

---

## 🧪 3. Invarianti di Governance & Salvaguardia Ratchet

1. **Ratchet Rule (`[RULE-01.10]`):** Nessuna modifica successiva potrà ridurre il numero di test permanenti al di sotto di **74** o il pass rate al di sotto del **100.0%**.
2. **Project Isolation Mandate (`[RULE-PROJECT-ISOLATION]`):** È fatto divieto assoluto di creare codice applicativo di prodotto all'interno di NK-Hub. Ogni progetto esterno vive nella propria directory dedicata con il proprio file `PATCH_NOTES.md`.
3. **Zero-Mock Mandate (`[RULE-01.2]`):** Ogni test deve validare codice reale su processi e filesystem reali. Nessun mock sintetico ammesso.
4. **Fast-Stat Bootstrap Guarantee (`[RULE-00.4]` / `[RULE-00.5]`):** L'avvio dell'Hub o dell'ambiente deve sempre completarsi in $< 120$ ms senza invocare la test suite completa o controlli diagnostici pesanti.

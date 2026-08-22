# 📜 NEXUS KEYSTONE OFFICIAL CHANGELOG & PATCH NOTES (SSOT)

> **Single Source of Truth (SSOT):** `nk_genome/PATCH_NOTES.md`  
> **Stato Release:** `🛡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED_FINAL 🟢]`  
> **Milestone Anchor:** `NK-MS-20260822-UNIVERSAL-STABILIZATION`

---

## 🧹 Versione 1.1.0-Cleanup & Consolidation (2026-08-22) — Bonifica Chirurgica & Consolidamento Ecosistema

### 🗑️ 1. Bonifica Dead Code & Disaccoppiamento
- **Eliminazione Directory Legacy:** Rimozione fisica completa delle cartelle non attive: `agent-ide/` (prototipo monolitico dismesso), `open_deep_research/` (dump esterno non integrato), `custom-workflows/` (cartella disaccoppiata orfana), `test_scratch/` (scratch temporaneo).
- **Preservazione Google Docs MCP:** Mantenimento intatto e operativo del server attivo `google-docs-mcp/`.

### 🔒 2. Isolamento Progetti Business Esterni `[EXTERNAL_ISOLATED_PROJECT]`
- **Isolamento Modelli & Output Business:** Formalizzazione dello status di `Antigravity model/` e `Output Business Keystone/` come progetti esterni isolati.
- **Zero Dipendenze Incrociate:** Rimozione di qualsiasi dipendenza interna da NK verso i progetti esterni, documentati formalmente come entità isolate nel Genome.

### ⚙️ 3. Consolidamento Script Core & Rimozione Residui CRV 3.0
- **Consolidamento Watchdog:** Spostamento di `safe_cleanup_dev_servers.py` dalla radice in `scripts/safe_cleanup_dev_servers.py` per centralizzare tutti gli strumenti di manutenzione di sistema.
- **Eliminazione Script Legacy:** Rimozione definitiva dei 3 file legacy CRV 3.0 ormai sostituiti dai motori v1.1.0: `scripts/sast_pattern_scanner.py`, `scripts/semantic_ast_analyzer.py`, `scripts/visual_diff_engine.py`.

### 🛡️ 4. Sanificazione NK-Security-Auditor
- **Rimozione Duplicato L3:** Eliminazione del file duplicato `.agents/skills/NK-Security-Auditor/resources/l3/NK3_Supervisor_System_Instruction.md`.
- **Dismissione Database Ad-Hoc:** Eliminazione di `db_helper.py` e riallineamento di `SKILL.md` e `resources/l1/supervisor.md` per l'archiviazione standard dei report JSON in `nk_tracking/reports_and_briefs/` e l'indicizzazione nella memoria episodica Tier 1-3 (`scripts/memory_3tier_engine.py`).

### 🧪 5. Baseline di Qualità & Suite Permanente Zero-Mock
- **49/49 Unit Tests 100% PASS:** Esecuzione e convalida della suite permanente di 49 unit test in `tests/` con tempo di risposta sub-20s.
- **Preflight Health Check HEALTHY_GREEN:** Validazione della conformità dell'ecosistema, igiene cache e assenza di lock/WAL orfani.

---

## 🚀 Versione 1.1.0-Universal (2026-08-22) — Stabilizzazione Globale & Core Engines

### 🛡️ 1. Garanzie Fisiche ACID, Win32 2PC & Google Drive Concurrency
- **Win32 Named Mutex Thread-Bound:** Risoluzione della violazione di thread affinity OS. `Win32NamedMutex` adotta semantica context manager sincrona con `_owning_thread_id = GetCurrentThreadId()`, prevenendo `ERROR_NOT_OWNER` (Codice 288). L'asincronia è incapsulata a monte in `atomic_write_async` tramite worker thread dedicato.
- **MoveFileExW con Win64 CTypes & Full Jitter Exponential Backoff:** Dichiarazione esplicita di `.argtypes` e `.restype` su kernel32. Algoritmo di retry a 8 tentativi con backoff esponenziale ($1.6^{\text{attempt}}$) e jitter (10-80ms) per neutralizzare lock Google Drive (`WinError 32`/`WinError 5`).
- **Shadow Swap Fallback:** Procedura automatica di swap a 4 stadi su file `.shadow` e `.old` in caso di lock prolungato da client di sincronizzazione cloud.
- **Streaming Copy:** Sostituzione della lettura in-memory con streaming a livello OS tramite `shutil.copy2` per rotazione backup circolari (.bak_1, .bak_2).

### 🔍 2. Real DAST Sandbox & Spectrum-Based Fault Localization (SBFL)
- **Watchdog Pre-Kill Inversion:** Inversione della sequenza di abbattimento processi: esecuzione di `taskkill /F /T /PID <pid>` **PRIMA** di `proc.kill()`, garantendo l'abbattimento atomico di alberi di processi complessi ed evitando orfanizzazione su Windows.
- **Line Tracer Deterministico:** Tracciamento istruzione per istruzione via `trace.Trace` nativo in `%TEMP%\nk_sandbox_<uuid>\`.
- **Formule Matematiche SBFL:** Implementazione di Ochiai, Tarantula e DStar ($\alpha=2.0$) con calibrazione Def-Use anti-coincidental correctness (fattore di sconto $\gamma=0.7$).
- **Tri-Pass Voting Filter:** Filtro di replicabilità a 3 passaggi per l'eliminazione dei test flaky.
- **Payload Diagnostico Ultra-Compatto:** Output strutturato `OchiaiDiagnosticPayload` con footprint rigorosamente $<80$ token.

### 🌳 3. AST Structural Mapping & Guard Validation Pre-Commit
- **Supporto Python Moderno (PEP 634, PEP 695, Walrus):** Riprogettazione del Visitor AST: estrazione ricorsiva dei pattern binding (`MatchAs`, `MatchStar`, `MatchMapping`), supporto a `type_params` su funzioni/classi, registrazione globale di `TypeAlias` e gestione degli scope lessicali interni per comprensioni e walrus operator (`:=`).
- **Personalized PageRank & Karpathy Slicing:** Calcolo blast radius ($\alpha=0.85$, $\epsilon=10^{-6}$) e binary search per slicing di moduli monolitici entro budget token prefissati.

### 🧠 4. 3-Tier Episodic Memory Engine
- **Tier 1 (Core Memory):** Hard cap vincolante $\le 350$ token per ciascuno dei 4 domini NK (`ARCH`, `SEC`, `OPS`, `DEVX`).
- **Tier 2 (Local Recall JSONL):** Sliding window a 200 eventi con compattazione rolling a 10 snapshot deterministici.
- **Tier 3 (Archival Cold Store):** Ricerca ibrida Pure Python BM25 + Dense Cosine con Reciprocal Rank Fusion ($k=60$).
- **Shadow Read Cache:** Cache di lettura in memoria temporanea con verifica di invalidazione mtime/SHA-256 ($<1$ms).

### 🏛️ 5. Governance, Normativa & Permanent Test Suite
- **Permanent Test Suite Mandate (`[RULE-01.10]`):** Suite permanente completa di 49 unit test Zero-Mock suddivisa su 8 file in `tests/`, con divieto assoluto di cancellazione durante il teardown.
- **Perimetro Self-Healing Blindato:** Invisible Self-Healing Loop (`scripts/invisible_healing_loop.py`) autorizzato esclusivamente nella Macro-Fase 1 (Build & Stage). In Macro-Fase 2, gli Auditor operano in modalità **100% Strict Read-Only e Zero-Mock inviolabile**.
- **WAL TTL 60s Auto-Purge:** Scansione e pulizia automatica al boot di file `.wal` con età $> 60$ secondi in `scripts/preflight_health_check.py`.
- **Bonifica Legacy:** Sostituzione integrale di `NK3_Supervisor` con `NK-Security-Auditor` e allineamento semantico di tutte le 16 skill canoniche.

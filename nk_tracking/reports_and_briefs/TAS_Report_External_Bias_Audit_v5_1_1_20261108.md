# 🛡️ Report di Audit Esterno Multi-Agente, Analisi Bias del Creatore e Valutazione Incrociata (`v5.1.1-AntiBias-RSI`)

> **Documento:** `nk_tracking/reports_and_briefs/TAS_Report_External_Bias_Audit_v5_1_1_20261108.md`  
> **Conversazione Esaminata:** `Controllo` (`88cd4d7c-8476-496e-b601-fe24fc2ac69a`, Milestone `v5.1.0-Lean-Sovereign-RSI`)  
> **Intent Brief ID:** `IB-20261108-7F1D58` (`SHA256: 7f1d58fc2ed94e4a8de0c17aeba3bab2bbe6d7a42fb6f10bc68441325824c198`)  
> **Metodologia:** Triangolazione Multi-Agente a 3 Livelli Ortogonali (`Forensic Bias Audit` + `SAST/Contract Audit` + `Sandbox Fuzzing & Mutation Testing`)  
> **Diagnostica Grezza Sandbox:** `%TEMP%\nk_diagnostics\macro1_sandbox_probe_report.json`  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`, frasi `<= 20` parole)

---

## 🔬 1. Sintesi Esecutiva della Macro-Attività 1 (Analitica in 3 Micro-Step)

L'audit esterno indipendente non ha ripetuto passivamente i `90` test esistenti, ma ha incrociato tre metodologie ortogonali:
1. **Micro-Step 1.1 (`NK-RSI-Auditor-Worker`, Sola Lettura `GT-14`):** Analisi forense delle scelte e dei tagli (`253 -> 90` test) effettuati in `Controllo`.
2. **Micro-Step 1.2 (`NK-Security-DAST-Auditor-Worker`, Sola Lettura `GT-14`):** Ispezione statica SAST/AST e verifica dei contratti sui `34` script in `scripts/`.
3. **Micro-Step 1.3 (`NK-Sandbox-Probe-Worker`, Sandbox `%TEMP%\nk_sandbox_audit_macro1`):** Fuzzing avversario (`Tests 2A..2D`), `5` test di mutazione (`Probe 3`) e censimento AST (`Probe 4`).

### Risultati Misurati nei Probe Ortogonali (`macro1_sandbox_probe_report.json`)
* **Mutation Score sui 5 Test Consolidati Chiave (`Probe 3`):** **`0/5 KILLED` (`0.0%`, `5/5 SURVIVED`)**. Tutte le 5 mutazioni semantiche iniettate nei moduli core sono sopravvissute ai test consolidati in `WP-LEAN-2`.
* **Vettori di Bypass Hook Gate (`Probe 2D`):** **`9` bypass confermati** su `scripts/nk_hook_gate.py`.
* **Vettori di Bypass SAST Guard (`Probe 2D`):** **`6` bypass confermati** su `scripts/ast_guard_validator.py`.
* **Copertura Simboli Pubblici AST (`Probe 4`):** **`185/350` funzioni pubbliche (`52.86%`)** referenziate direttamente nei `17` moduli di test (`122` funzioni di dominio prive di test diretto).

---

## ⚖️ 2. Macro-Attività 2: Matrice di Valutazione Incrociata e Bias del Creatore (`Micro-Step 2.1`)

La tabella seguente incrocia le evidenze dei tre sub-agenti per isolare i **5 Cluster di Bias del Creatore e Bug Reali**:

| ID Cluster | Tipologia di Bias / Errore | Evidenza Micro-Step 1.1 (Forensic) | Evidenza Micro-Step 1.2 (Static SAST) | Evidenza Micro-Step 1.3 (Sandbox & Mutation) | Severità |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`CL-01`** (`nk_hook_gate.py`) | **Bias Ambientale (`tmp_path` senza spazi vs `Il mio Drive`) e Token Spoofing** | `test_nk_hook_and_transcript_governance.py:196` usa `assert rc in (0, 1)` tautologico. | `L516`: `" " in target` sposta `target` in `cmd`; `L304`: sanitizer maschera `scratch/` e `/temp/` ovunque; mancano alias PowerShell (`sc`, `ac`, `ni`). | **Confermato Live:** `write_file` su `g:/Il mio Drive/.../scripts/nk_hook_gate.py` restituisce `allow`! `Out-File scripts/scratch/backdoor.py` restituisce `allow`! `MUT-05` sopravvive (`SURVIVED`). | **CRITICA (`P0`)** |
| **`CL-02`** (`nk_session_bootstrap.py`) | **Bias di Ottimizzazione (`WP-LEAN-1` Cache Cieca `900s` e Bleed Cross-Sessione)** | `L243`: `_get_root_mtime` legge solo `workspace_root.st_mtime`; `L331`: emette `ONBOARDING_BYPASS_VERIFIED` senza `--transcript`; `L328`: match sottostringa. | `L471`: `not self.conversation_id` riusa la cache della conversazione precedente (`273 steps RED`). | **Confermato Live (`2A`, `2B`, `2C`, `MUT-03`):** Corrompendo `.wal/` o `quality_baseline.json` entro `900s`, il Fast-Pass restituisce falso `PASS`. `"Analizza il bug per cui avvia nk hub..."` attiva falso bypass. `MUT-03` sopravvive. | **CRITICA (`P0`)** |
| **`CL-03`** (`vibe_sprint_router.py` & test) | **Bias di Conferma nel Consolidamento Test (`WP-LEAN-2`) e Bypass Gate L0** | `test_vibe_sprint_router.py:581` decomprime `_expected_mode` con underscore e **non lo verifica mai** (perché `L432` falliva!). | `L1365,1372,1388`: `is_gate_exempt` usa sottostringhe su `<env_capsule>`, `salta gate` e prefissi `Vai `/`Confermo ` (`<=5` parole). | **Confermato Live (`2C`, `MUT-01`):** `"Spiega come funziona <env_capsule>..."` e `"Vai a controllare i log"` bypassano il Gate L0. `MUT-01` (`MODE_C_MAX_LOC=1500`) sopravvive! | **ALTA (`P1`)** |
| **`CL-04`** (`ast_guard_validator.py`) | **Bias dell'Attaccante Noto (Overfitting sui soli vettori `S1..S4` del creatore)** | I test verificano solo `eval`/`exec` diretti e `getattr` con stringa costante. | `L739`: `_eval_const_str_expr` ignora `JoinedStr` e `"".join`; `L962`: `SASTConstructChecker` ignora `Subscript` (`__builtins__["eval"]`), `importlib`, `operator.attrgetter`, `os.exec*`; `L515`: `ScopeIntegrityChecker` ignora `global`/`nonlocal`. | **Confermato Live (`2D`, `MUT-02`):** `6` vettori SAST bypassano il validatore; `MUT-02` (rimozione di `'compile'` dalla tupla SAST) sopravvive (`SURVIVED`)! | **ALTA (`P1`)** |
| **`CL-05`** (`win32_2pc_engine.py`, `quality_baseline_manager.py`, `preflight_health_check.py`, `nk_session_handoff.py`) | **Bias dell'Oracolo Autoreferenziale, Rollback Non-Atomico e Drift Versioni** | `quality_baseline_manager.py:434`: `check` senza `--metrics` confronta il file con se stesso. | `win32_2pc_engine.py:428,1174`: `recover()` e `_rollback_batch()` usano `write_bytes` non atomico; `nk_session_handoff.py:48` ha path hardcoded `C:/Users/erbal/...`; `preflight_health_check.py:468` cancella i `.bak` di `memory_3tier_engine.py`; `9` versioni eterogenee. | **Confermato Live (`Probe 1`, `MUT-04`):** `MUT-04` (`compute_crc32` costante `0`) sopravvive (`SURVIVED`) in `test_win32_2pc.py`! | **MEDIA-ALTA (`P1`)** |

---

## 🛠️ 3. Strategia di Eccellenza RSI per la Macro-Attività 3 (Implementazione in Micro-Step)

Per eliminare ogni bias rilevato e portare il Mutation Score da `0/5` (`0.0%`) a `5/5` (`100.0%` `KILLED`), la **Macro-Attività 3** è frazionata in **4 Micro-Step Esecutivi in `.staging/`**:

1. **Micro-Step 3.1 (`WP-ANTIBIAS-1` — Hardening `nk_hook_gate.py` e `ast_guard_validator.py`):**
   * Rimuove la riassegnazione `if " " in target: cmd = target; target = ""` in `nk_hook_gate.py:516` quando `target` è un path valido su filesystem (come `G:\Il mio Drive\...`).
   * Corregge `_sanitize_staged_tokens_in_cmd` per accettare solo prefissi realmente confinati in `.staging/`, `%TEMP%` o `brain/<id>/scratch/`.
   * Aggiunge il blocco per gli alias PowerShell di scrittura (`sc`, `ac`, `ni`, `ri`) e per `os.open(..., os.O_WRONLY | os.O_CREAT | os.O_RDWR)`.
   * Estende `SASTConstructChecker` e `_eval_const_str_expr` in `ast_guard_validator.py` per intercettare `JoinedStr`, `"".join`, `__builtins__[...]`/`__dict__[...]`, `importlib.import_module`, `operator.attrgetter`, `os.exec*`/`os.spawn*`, e supporta `global`/`nonlocal` in `ScopeIntegrityChecker`.
2. **Micro-Step 3.2 (`WP-ANTIBIAS-2` — Correzione Fast-Boot `nk_session_bootstrap.py` e Router `vibe_sprint_router.py`):**
   * In `nk_session_bootstrap.py`, calcola un fingerprint multi-directory (`root`, `scripts/`, `.agents/`, `nk_tracking/quality_baseline.json`, `.wal/`), esegue sempre `_purge_stale_wal_files()`, emette `ONBOARDING_BYPASS_VERIFIED` solo su match esatto del prompt di avvio e impedisce il bleed di transcript di conversazioni chiuse.
   * In `vibe_sprint_router.py`, restringe `is_gate_exempt` per evitare falsi bypass quando `<env_capsule>`, `salta gate` o prefissi brevi (`Vai `, `Confermo `) compaiono dentro frasi tecniche analitiche.
3. **Micro-Step 3.3 (`WP-ANTIBIAS-3` — Integrità Atomica `win32_2pc_engine.py`, Ratchet Reale e Rimozione Hardcoding):**
   * Rende atomiche le scritture di ripristino in `win32_2pc_engine.py` (`recover()` e `_rollback_batch()`) con file `.tmp` + `fsync` + `os.replace`.
   * In `quality_baseline_manager.py`, arricchisce `check` per verificare anche l'esistenza reale dei moduli in `oracle_lock.json`.
   * Rimuove il path hardcoded `C:/Users/erbal/...` da `nk_session_handoff.py:48` e protegge i file `.bak` di `memory_3tier_engine.py` in `preflight_health_check.py`.
4. **Micro-Step 3.4 (`WP-ANTIBIAS-4` — Rafforzamento Suite Golden Tests, Uccisione Mutazioni `5/5` e Commit 2PC):**
   * Ripristina l'asserzione mancante `assert res["recommended_mode"] == expected_mode` in `tests/test_vibe_sprint_router.py:581`, elimina la tautologia `assert rc_corrupt in (0, 1)` in `tests/test_nk_hook_and_transcript_governance.py:196` e aggiunge i test avversari per uccidere tutte le mutazioni `MUT-01..MUT-05` (`5/5 KILLED = 100%`).
   * Esegue la Cold Review (`NK-RSI-Auditor-Worker` + `NK-Security-DAST-Auditor-Worker`), verifica `CONVERGED_OPTIMAL` ($\Delta_k = 0$, $Q = 100.0$), promuove con `win32_2pc_engine.py` e aggiorna `oracle_lock.json`, `quality_baseline.json` e `PATCH_NOTES.md`.

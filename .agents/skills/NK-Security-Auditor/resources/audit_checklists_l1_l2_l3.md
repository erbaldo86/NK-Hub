# 🛡️ Checklist Unificata di Audit SAST L1 / L2 / L3 (`v3.0.0-STE100-Unified`)

> **Nodo Proprietario:** `NK-Security-Auditor` (Macro-Fase 2 del Protocollo CRV 4.0).  
> **Modalità Operativa:** 100% Sola Lettura (`[RULE-00.1 / RULE-04.4]`). Nessun nodo Fixer è autorizzato durante l'audit.  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Checklist Livello 1 (SAST L1 : Regole, Prompt e `SKILL.md`)

1. **Conformità Frontmatter YAML:** Verifica la presenza di `name`, `description`, `version: "3.0.0-STE100-Unified"` e `thinking_level: "HIGH"`.
2. **Integrità `<strict_boundaries>`:** Controlla che ogni skill dichiari i vincoli di confinamento e gli ID regola di `.agents/AGENTS.md`.
3. **Standard ASD-STE100 (`[RULE-STE100]`):**
   * Verifica che le frasi operative contengano al massimo 20 parole.
   * Verifica l'assenza di incisi con trattini lunghi o medi.
   * Verifica l'uso del termine canonico *"Tetralogia Sovrana"* (4/4).
4. **Controllo Link Ausiliari:** Verifica che ogni file in `resources/` o `references/` sia linkato nel proprio `SKILL.md`.
5. **Passive Data Tagging (`[RULE-08]`):** Verifica che gli input non fidati siano racchiusi in `<passive_data_context>`.

---

## 2. Checklist Livello 2 (SAST L2 : Moduli Python, IPC e Concorrenza Win32)

1. **Validazione AST (`scripts/ast_guard_validator.py`):**
   * Verifica zero errori di sintassi (`SyntaxError`) e zero costrutti vietati (`eval`, `exec`, `pickle.loads` non sanitizzati).
   * Verifica la preservazione delle firme delle funzioni e delle classi pubbliche rispetto alla baseline di produzione.
2. **Contratti Pydantic v2 (`scripts/schemas/`):**
   * Verifica l'uso di `ConfigDict(strict=True, extra="forbid")`.
   * Verifica l'assenza del tipo `Any` nei contratti IPC.
3. **Sicurezza Puntatori Win32 a 64-bit (`ctypes`):**
   * Verifica che `CreateMutexW`, `OpenProcess`, `CreateJobObjectW`, `CloseHandle` e `MoveFileExW` definiscano esplicitamente `argtypes` e `restype` (`ctypes.c_void_p`, `wintypes.BOOL`, `wintypes.DWORD`).
   * Verifica la gestione corretta di `ERROR_ACCESS_DENIED (5)` e `INVALID_HANDLE_VALUE`.
4. **Esecuzione Sottoprocessi (`scripts/platform_runner.py`):**
   * Verifica l'iniezione del flag `-u` e la codifica `UTF-8` (`PYTHONUTF8=1`) su tutte le invocazioni Python.

---

## 3. Checklist Livello 3 (SAST L3 : Full-Stack, Isolamento e Segreti)

1. **Isolamento Progetti Esterni (`[RULE-PROJECT-ISOLATION]`):**
   * Verifica l'assenza di cartelle applicative (`src/`, `app/`) o progetti esterni dentro la radice di `NK-Hub`.
2. **Assenza di Segreti e Credenziali:**
   * Verifica che nessun file contenga token OAuth2 (`token.json`, `credentials.json`), chiavi API in chiaro o password.
3. **Guardia Zero-Mock (`[RULE-01.2]`):**
   * Verifica l'assenza totale di `unittest.mock.MagicMock`, `@patch`, stub fittizi o generatori casuali nei test.
4. **Calcolo Vettore Difetti RSI ($\text{SAST}_k$):**
   * Registra ogni violazione confermata nel contatore $\text{SAST}_k$ (peso `15` nella formula $\Delta_k$).
   * Qualsiasi valore $\text{SAST}_k > 0$ produce immediatamente il verdetto `FAIL` (`exit_code: 1`).

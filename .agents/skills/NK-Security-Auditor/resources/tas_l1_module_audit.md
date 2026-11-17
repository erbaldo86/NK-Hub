# 🔍 Matrice TAS Livello 1: Audit Universale Singolo Modulo (`tas_l1_module_audit.md`)

> **Ambito Operativo:** Singolo modulo Python, componente backend isolato, script CLI o file `SKILL.md`.  
> **Nodo Proprietario:** `NK-Security-Auditor` (`v1.0.0-Generation`, 100% Sola Lettura `GT-14`).  
> **Architettura:** Protocollo Dual-Execution a 2 Fasi (Fase A Deterministica + Fase B Referee PoC).

---

## 1. Fase A Deterministica (Gate 0 e Gate 1 Obbligatori)

1. **Purezza Sintattica e Firme AST:**
   * Analizza l'output di `python -u scripts/ast_guard_validator.py --stage-dir .staging` nella directory temporanea `nk_diagnostics/`.
   * Verifica zero errori `SYNTAX_ERROR`, `UNAUTHORIZED_DELETION`, `SIGNATURE_MUTATION` e `UNDEFINED_NAME`.
2. **Controllo Tipi e Annotazioni Rigorose:**
   * Verifica che le funzioni pubbliche dichiarino annotazioni di tipo complete e modifiche retrocompatibili.
3. **Scansione SAST Locale (`SASTConstructChecker`):**
   * Verifica l'assenza di `eval()`, `exec()`, `compile()`, `pickle.loads()`, `yaml.load()` insicuro, `shell=True`, `os.system()` e `MagicMock`.
4. **Invarianti Documentali (`[RULE-STE100]`):**
   * Per i file `.md`, verifica l'esito di `python -u scripts/rsi_convergence_engine.py --vibe-check <target> --profile ste100_rsi`.

---

## 2. Fase B Probabilistica (`heuristic_findings` + Referee Gate 2)

1. **Caccia a Bug Logici ed Edge Case:**
   * Analizza collezioni vuote, valori `None`, divisioni per zero, off-by-one e path Unicode con spazi.
2. **Analisi della Gestione Errori:**
   * Individua blocchi `except Exception: pass` silenziosi e verifica il rilascio di handle e lock nei blocchi `finally`.
3. **Validazione Referee PoC (Gate 2):**
   * Valuta la verifica isolata eseguita dall'Orchestratore con `python -u scripts/dast_sandbox_runner.py --script <poc_py> --timeout 30 --json`.
   * Se il PoC dimostra il guasto (`exit_code != 0`), promuovi il rilievo in `poc_confirmed_exploits` nella directory temporanea `nk_diagnostics/`.

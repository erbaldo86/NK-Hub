# 🔍 Matrice TAS Livello 1: Audit Universale Singolo Modulo (`tas_l1_module_audit.md`)

> **Ambito Operativo:** Singolo modulo Python, componente backend isolato, script CLI o file `SKILL.md`.  
> **Nodo Proprietario:** `NK-Security-Auditor` (`v3.0.0-STE100-Unified`, 100% Sola Lettura `GT-14`).  
> **Architettura:** Protocollo Neuro-Simbolico a 2 Fasi (Fase A Deterministica + Fase B Probabilistica con Referee PoC).

---

## 1. Fase A Deterministica (Gate 0 e Gate 1 Obbligatori)

1. **Purezza Sintattica e Conservazione Firme AST:**
   * Esegui `python scripts/ast_guard_validator.py --stage-dir .staging` sul modulo target.
   * Verifica zero errori `SYNTAX_ERROR`, `UNAUTHORIZED_DELETION` e `SIGNATURE_MUTATION` non autorizzate.
   * Verifica che tutte le variabili globali e locali rispettino lo scope di modulo (`UNDEFINED_NAME == 0`).
2. **Controllo Tipi e Annotazioni Rigorose:**
   * Verifica che tutte le funzioni pubbliche dichiarino annotazioni di tipo complete per parametri e ritorno.
   * Verifica che le modifiche alle firme esistenti siano solo estensioni opzionali retrocompatibili.
3. **Scansione SAST Locale (`SASTConstructChecker`):**
   * Verifica l'assenza di invocazioni dirette a `eval()`, `exec()` e `compile()` su stringhe dinamiche.
   * Verifica l'assenza di deserializzazioni insicure tramite `pickle.loads()` o `yaml.load()` senza `SafeLoader`.
   * Verifica l'assenza di `subprocess.run(..., shell=True)` e di `os.system()` con input non sanitizzati.
   * Verifica l'assenza di costrutti `unittest.mock.MagicMock` o `@patch` (`[RULE-01.2]`).
4. **Invarianti Documentali e Prompt (`[RULE-STE100]`):**
   * Per i file `.md`, verifica che ogni frase contenga al massimo 20 parole tramite `scripts/rsi_convergence_engine.py --vibe-check`.
   * Verifica l'assenza di trattini d'inciso e la validità di tutti i link relativi.

---

## 2. Fase B Probabilistica (`heuristic_findings` + Referee Gate 2)

1. **Caccia a Bug Logici ed Edge Case:**
   * Analizza le condizioni al contorno su collezioni vuote, valori `None`, divisioni per zero e overflow numerici.
   * Identifica off-by-one error nei cicli, mutazioni involontarie di argomenti di default e cattiva gestione di path Unicode.
2. **Analisi della Gestione Errori:**
   * Individua blocchi `except Exception: pass` silenziosi che mascherano corruzioni di stato o fallimenti critici.
   * Verifica il rilascio garantito di file handle, lock e risorse temporanee nei blocchi `finally` o context manager.
3. **Sintesi e Validazione Referee PoC (Gate 2):**
   * Per ogni anomalia logica individuata in `heuristic_findings`, progetta un input minimale che innesca il bug.
   * Esegui la verifica isolata nella Shadow Sandbox tramite `python scripts/dast_sandbox_runner.py --script`.
   * Se lo script PoC dimostra il guasto (`exit_code != 0`), promuovi il rilievo in `poc_confirmed_exploits`.
   * Salva l'evidenza diagnostica in `%TEMP%\nk_diagnostics\` senza mai modificare i file sorgente (`GT-14`).

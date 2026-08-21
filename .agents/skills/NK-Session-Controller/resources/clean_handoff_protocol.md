# 🏛️ Clean Handoff Protocol & Decoupled Actor-Critic Specification (v2.0 / CRV 4.2)

> **Ambito:** Ecosistema Nexus Keystone (NK) — Standard di comunicazione asimmetrica disaccoppiata tra Sovereign Critic (`NK-Session-Controller`) e Worker (`NK-Delta-Architect` o builder specialistici).  
> **Versione:** v2.0 (Brief-Aware Handoff, Decoupled Asymmetric Actor-Critic & Two-Stage Grounding)

---

## 🧭 1. Principi Cardine & Guardrail di Sicurezza

1. **Strict One-Way Asymmetry & Isolamento:** Il Lavoratore è all'oscuro dell'esistenza del Critico. Il Critico non inserisce MAI checklist di revisione, criteri di Cold Review o riferimenti alla chat del Critico all'interno dei prompt per il Lavoratore.
2. **Brief-Aware Handoff:** Il Blocco 1 del prompt per il Lavoratore integra la **Brief Anchor Capsule (<= 350 token)**, contenente il Milestone Anchor ID, gli estratti chiave del piano e il legame strategico con il Trittico.
3. **Two-Stage Grounding Mandate (Anti-Blind Execution):**
   - **Stage A (Conceptual Brief Grounding):** Lettura obbligatoria di `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"` (slice <= 60 righe) per ancorarsi ai requisiti e verificare il Milestone Anchor ID.
   - **Stage B (Physical Code Grounding):** Ispezione fisica del codice sorgente su disco (`view_file` con `StartLine`/`EndLine` <= 100 righe per blocco).
4. **Dual-Mode Execution Switch:**
   - **Mode A (Trittico-Driven):** Per feature complesse, refactoring o modifiche >100 LOC. Obbligo di Two-Stage Grounding completo (Stage A + Stage B).
   - **Mode B (Fast-Track):** Per bug fix puntuali (LOC <= 100, zero boundary impact). Obbligo di Grounding Stage B su codice.
5. **Zero Slash Commands (RULE-02.5):** Divieto assoluto di usare prefissi slash nei prompt per i Worker, per evitare crash del parser di interfaccia.
6. **Sanitizzazione Passive Data Context:** In modalità Chat Isolata (priva di tool di filesystem), il contesto sorgente deve essere racchiuso nel tag `<passive_data_context>` con hard-cap di **150 righe** per prevenire context overflow e prompt injection.
7. **Win32 I/O Safety & Exponential Backoff:** Prima di qualsiasi edit chirurgico su Windows, i processi server/demoni attivi devono essere arrestati (`manage_task` con action: `'kill'`). In caso di lock I/O (`WinError 32`), applicare backoff esponenziale (1s, 2s, 4s).

---

## 📦 2. Template 8A: `TASK_HANDOFF_4_BLOCKS` (v2.0 Brief-Aware Prompt per il Lavoratore)

*Racchiuso in blocco fenced ` ```markdown ... ``` ` pronto per il passaggio al Lavoratore (via `invoke_subagent` o incollaggio dello sviluppatore).*

````markdown
# 📦 [HANDOFF PROMPT FOR WORKER - v2.0 BRIEF-AWARE]

### 🎯 BLOCCO 1: Obiettivo, Perché & Brief Anchor Capsule
- **Problema Reale / Task:** {{PROBLEM_DESCRIPTION}}
- **Effetto Collaterale da Evitare:** {{SIDE_EFFECT_PREVENTION}}
- **Brief Anchor Capsule (<= 350 token):**
  * **Milestone Anchor ID:** `{{MILESTONE_ANCHOR_ID}}`
  * **Brief & Architecture Summary:** {{BRIEF_SUMMARY_EXTRACT}}
  * **Trittico Reference:** `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"`

### 📍 BLOCCO 2: Perimetro d'Azione Chirurgico
- **File Target:** {{TARGET_FILES_ABSOLUTE_PATHS}}
- **Classi/Funzioni:** {{TARGET_COMPONENTS}}
- **Scope Creep Guard:** Vietato toccare qualsiasi file, classe o funzione non esplicitamente inclusi in questo perimetro.

### 🔍 BLOCCO 3: Direttiva di Two-Stage Grounding Obbligatorio (Anti-Blind Execution)
> [!IMPORTANT]
> **TWO-STAGE GROUNDING MANDATE:**
> 1. **Stage A (Conceptual Brief Grounding):** Esegui `view_file` su `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"` (slice <= 60 righe) per estrarre le specifiche e confermare il Milestone Anchor ID `{{MILESTONE_ANCHOR_ID}}`. *(In Mode B Fast-Track, passa direttamente a Stage B)*.
> 2. **Stage B (Physical Code Grounding):** Prima di qualsiasi modifica, esegui `view_file` con `StartLine` ed `EndLine` (<= 100 righe per blocco) sui file target di codice indicati nel Blocco 2.
> *(In Modalità Chat Isolata senza tool: Analizza lo snippet racchiuso in `<passive_data_context>` - max 150 righe).*

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche, Criteri di Accettazione & Test
- **MANDATO DDI OBBLIGATORIO:** Delega la scrittura a builder specializzati in `.staging/` e i test all'Oracolo indipendente tramite `invoke_subagent`. Vietata la modifica diretta dei file di produzione da parte dell'orchestratore.
- **Pre-Edit Safety:** Esegui `manage_task(action: 'list')` e arresta eventuali processi attivi con `manage_task(action: 'kill')` per prevenire lock I/O Windows (`WinError 32`).
- **Modifiche Richieste:** {{SURGICAL_INSTRUCTIONS}}
- **Vincoli Tecnici:** {{TECHNICAL_CONSTRAINTS}} (No clean-slate, codifica UTF-8 strict, `replace_file_content` in `.staging/` con retry su backoff esponenziale).
- **Test di Verifica:** Esegui {{VERIFICATION_COMMAND}} e includi l'exit code e l'output empirico nella ricevuta finale.
- **Formato Risposta:** Compila e restituisci obbligatoriamente la **Worker Execution Receipt v2.0** standard.
````

---

## 🛡️ 3. Template 8B: `CRITIC_REVIEW_CHECKLIST` (Checklist Interna a 5 Gate per il Critico)

*Uso interno esclusivo per la chat del Critico — MAI condivisa con il Lavoratore.*

```markdown
### 🛡️ [USO INTERNO CRITICO] Checklist di Cold Review Post-Esecuzione (v2.0 - 5 Gate)
1. **Gate 1 - Scope Audit:** Il diff tocca SOLO i file e le funzioni autorizzati nel Blocco 2? *(Se NO -> REJECT_SCOPE_CREEP)*.
2. **Gate 2 - Code Grounding Audit:** Nel transcript del Worker è presente la chiamata `view_file` reale sui range di codice corretti? *(Se NO -> REJECTED_BLIND_EXECUTION)*.
3. **Gate 2bis - Brief Grounding Forensic Audit:** Nel transcript del Worker è presente l'ispezione reale di `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"` con Milestone Anchor ID validato? *(Se NO -> REJECT_FAKE_BRIEF_GROUNDING)*.
4. **Gate 3 - Preservation Guard:** I tipi, le interfacce, i commenti e il contesto limitrofo sono intatti? *(Se NO -> REJECT_CLEAN_SLATE)*.
5. **Gate 4 - Truth Verification:** I test dinamici/DAST riportano exit code 0 e output reale verificabile da oracolo indipendente? *(Se NO -> REJECT_TEST_FAILED)*.
6. **Gate 5 - Delegation Audit:** Nel transcript del Worker è presente `invoke_subagent` per Builder ed Oracolo, con assenza di comandi di edit diretti? *(Se NO -> REJECT_SUBAGENT_BYPASS)*.

> [!CAUTION]
> **Circuit Breaker:** Tentativo {{CORRECTION_ATTEMPT}} di 3. Se = 3 e uno o più Gate falliscono, ARRESTA il loop, salva `status: CORRECTION_FAILED` nel manifest e richiedi l'intervento dell'utente.
```

---

## 📋 4. Worker Execution Receipt (v2.0 Formato di Risposta Standard del Lavoratore)

Ogni Lavoratore deve strutturare l'output finale in sezioni deterministiche certificate:

````markdown
### 📋 WORKER EXECUTION RECEIPT (v2.0 — CRV 4.0 Certified)
- **🔍 Two-Stage Grounding Summary:**
  * **Stage A (Brief Grounding):** `view_file` su `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"` (L{{START_A}}-L{{END_A}}). Milestone Anchor ID: `{{MILESTONE_ANCHOR_ID}}` (Verificato).
  * **Stage B (Code Grounding):** `view_file` su `{{FILE_PATH}}` (L{{START_B}}-L{{END_B}}). Checksum pre-edit validato.
- **🏗️ Staging Evidence:** Modifiche applicate esclusivamente in `".staging/{{TARGET_PATH}}"`. Nessun file di produzione toccato pre-audit.
- **🤖 Sub-Agent Invocation Evidence:**
  * Builder Subagent: `{{BUILDER_CONVERSATION_ID}}` (Exit Code 0).
  * Oracle Subagent: `{{ORACLE_CONVERSATION_ID}}` (PASS certificato).
- **🧪 Dynamic Test & DAST Evidence:**
  * Comando eseguito: `{{REAL_E2E_TEST_CMD}}`
  * Exit Code: `0`
  * Runtime DOM / API Check: `{{RUNTIME_VERIFICATION_SUMMARY}}` (Zero errori console, dati renderizzati verificati).
- **🚀 Commit Status:** Atomic commit (`os.replace`) eseguito con successo in produzione.
````

---

## 🔄 5. Protocollo di Dual Refresh & Bootstrap

### 📦 Template 9: `WORKER_REFRESH` (Bootstrap Nuova Chat Lavoratore v2.0)

```markdown
<!-- ZERO-AMNESIA BOOTSTRAP CAPSULE v2.0 -->
Assumi il ruolo di [5] NK-Delta-Architect (Lavoratore / Post-Release Triage) dell'Ecosistema Nexus Keystone.
Esegui view_file su "G:/Il mio Drive/Antigravity/.agents/skills/NK-Delta-Architect/SKILL.md".

VINCOLI DI GOVERNANCE NK:
1. NO SLASH COMMANDS: Non usare comandi slash interni (RULE-02.5).
2. TWO-STAGE GROUNDING: Esegui SEMPRE view_file su implementation_plan.md (Stage A) e sui file target (Stage B) prima di qualsiasi edit.
3. SURGICAL EDIT: Delega ai Builder per modificare in .staging/ tramite replace_file_content (no clean-slate, codifica UTF-8).
4. WINDOWS SAFETY: Verifica e arresta server attivi (manage_task kill) prima dell'edit.

CONTESTO PROGETTO & STATO LAVORI:
- Workspace Root: "{{WORKSPACE_ROOT}}"
- Milestone Anchor Attiva: `{{MILESTONE_ANCHOR_ID}}`
- Task Completati: {{COMPLETED_TASKS_SUMMARY}}
- Anti-Pattern da Evitare: {{LEARNED_ANTI_PATTERNS}}
- File Critici con Checksum: {{CRITICAL_FILES_TABLE}}

AUTO-TRIGGER TASK:
Non inviare saluti né attendere conferme. Procedi immediatamente con il seguente task nei 4 Blocchi:
{{TASK_HANDOFF_4_BLOCKS_PAYLOAD}}
```

### 📦 Template 10: `CRITIC_SELF_REFRESH` (Bootstrap Nuova Chat Critico v2.0)

```markdown
<!-- ZERO-AMNESIA BOOTSTRAP CAPSULE v2.0 -->
Assumi il ruolo di [4] NK-Session-Controller (Sovereign Critic & Supervisor) dell'Ecosistema Nexus Keystone.
Esegui view_file su "G:/Il mio Drive/Antigravity/.agents/skills/NK-Session-Controller/SKILL.md".

CONTESTO OPERATIVO:
- Workspace Root: "{{WORKSPACE_ROOT}}"
- Manifest di Ripresa: "{{MANIFEST_FILE_PATH}}"
- Conversation Pointer Worker: {{NEW_WORKER_CONVERSATION_ID}}
- Milestone Anchor Attiva: `{{MILESTONE_ANCHOR_ID}}`
- Snapshot Decisionale (≤200 token): {{DECISIONS_COMPACT_SUMMARY}}
- Circuit Breaker State: Tentativi di correzione attivi = {{CORRECTION_ATTEMPTS}} di 3

AZIONE IMMEDIATA:
Inizializza la FSM nello stato ACTIVE_SUPERVISION, leggi il manifest di ripresa e attendi l'output del Worker per eseguire la Cold Review a 5 Gate.
```

---

## 🛡️ 6. Matrice Decisionale di Cold Review & Tabella Codici di Scarto

| Codice Errore | Causa Scarto | Azione Correttiva del Critico |
| :--- | :--- | :--- |
| `REJECT_SCOPE_CREEP` | Modifiche a file o funzioni fuori dal perimetro del Blocco 2 | Rigenera Template 8A restringendo il perimetro e imponendo il ripristino dei file non autorizzati. |
| `REJECTED_BLIND_EXECUTION` | Modifica tentata senza preventiva lettura (`view_file`) sul codice sorgente | Rigenera Template 8A imponendo il Grounding Stage B come pre-condizione bloccante. |
| `REJECT_FAKE_BRIEF_GROUNDING` | Transcript privo di lettura reale di `implementation_plan.md` o Milestone Anchor ID non verificato | Rigetta immediatamente il task e impone l'esecuzione dello Stage A sul piano di implementazione prima di qualsiasi operazione. |
| `REJECT_CLEAN_SLATE` | Sovrascrittura massiva o cancellazione di commenti, tipi o interfacce preesistenti | Richiedi l'uso esclusivo di `replace_file_content` preservando intatto il contesto circostante. |
| `REJECT_TEST_FAILED` | Test con exit code != 0, test non eseguiti o evidenza empirica assente/falsificata | Fornisci l'analisi RCA dell'errore di test nel Blocco 1 del nuovo Template 8A e richiedi nuovo ciclo oracolo. |
| `REJECT_SUBAGENT_BYPASS` | `invoke_subagent` assente o esecuzione diretta di tool di scrittura/terminale da parte dell'orchestratore | Rigetta immediatamente il task: violazione grave della regola DDI e del protocollo di isolamento. |

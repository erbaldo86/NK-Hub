# 📚 Knowledge Base: Pattern Agentici in Antigravity

Questo documento è il riferimento per il modulo `[SC-MOD-02] NK Rule Engine` per identificare e suggerire le migliori strategie agentiche e architetturali durante il monitoraggio di un Worker o durante l'orchestrazione.

## 🔗 FAMIGLIA 1: Pattern Sequenziali

### [SEQ-01] Sequential Chain (Catena Lineare)
* **Descrizione**: Esecuzione di task complessi dividendoli in step sequenziali rigidi, dove l'output dello step N è l'input dello step N+1.
* **Trigger**: Task lineari senza grandi biforcazioni decisionali.
* **Anti-Pattern**: Usarlo quando gli step sono indipendenti (collo di bottiglia) o quando c'è alto rischio di errore a cascata.
* **Implementazione NK**: Uso di `session_anchor.jsonl` per marcare gli step. Il Controller passa i contesti sequenzialmente.

### [SEQ-02] Pipeline con Gate di Qualità
* **Descrizione**: Catena lineare dove tra uno step e l'altro esiste un nodo (umano o oracolo) che deve validare il risultato prima di procedere.
* **Trigger**: Creazione brief, validazione architettura.
* **Implementazione NK**: `[RULE-01.1-CHECKLIST]` (5 Execution Gates). Richiede il comando `/board` o l'invocazione di validatori isolati.

### [SEQ-03] Strangler Fig (Migrazione Incrementale)
* **Descrizione**: Sostituzione graduale di un componente legacy con un nuovo componente, facendo routing del traffico/uso finché il vecchio non è dismesso.
* **Trigger**: Refactoring profondo, rimozione debito tecnico, riscrittura backend. (Vedi caso "Opus controllore").
* **Anti-Pattern**: Riscrittura da zero ("Clean Slate") su sistemi funzionanti.
* **Implementazione NK**: Mantenere i vecchi file, creare i nuovi (es. `.new.py`), usare `NK-Delta-Architect`.

## ⚡ FAMIGLIA 2: Pattern Paralleli & Concorrenti

### [PAR-01] Parallel Fan-Out / Fan-In
* **Descrizione**: Un task viene diviso in sotto-task indipendenti eseguiti in parallelo (Fan-Out), e poi i risultati vengono aggregati (Fan-In).
* **Trigger**: Analisi di file multipli, scraping concorrente.
* **Implementazione NK**: `invoke_subagent` multipli con modello `flash`. Il nodo chiamante attende e aggrega.

### [PAR-02] MapReduce (Partizionamento + Aggregazione)
* **Descrizione**: Versione strutturata del Fan-Out/Fan-In per volumi di dati.
* **Trigger**: Ingestione dati massiva (es. `[RULE-08]`).
* **Implementazione NK**: Chunking dei dati, assegnazione ai worker in `branch` workspace, aggregazione finale e scrittura a DB.

### [PAR-03] Swarm Competitivo
* **Descrizione**: N agenti ricevono lo stesso prompt per risolvere lo stesso problema. L'output migliore viene selezionato da un giudice.
* **Trigger**: Ideazione L0, esplorazione opzioni algoritmiche complesse.
* **Implementazione NK**: `invoke_subagent` paralleli. Il Controller o `NK-Ideator` (via `/board`) funge da giudice.

### [PAR-04] Swarm Cooperativo (Majority Vote)
* **Descrizione**: Molteplici agenti valutano un output. L'esito finale è deciso a maggioranza o tramite sistema di scoring composito.
* **Trigger**: `[RULE-01.2] COMPOSITE_BOOLEAN_SCORING_DIRECTIVE`. Elevata incertezza o rischio di bias.

## 🔄 FAMIGLIA 3: Pattern Iterativi & Auto-Correttivi

### [ITER-01] Reflection Loop (Self-Critique)
* **Descrizione**: L'agente genera un output, poi critica il suo stesso output, poi lo corregge.
* **Trigger**: Generazione codice complessa, affinamento prompt.
* **Anti-Pattern**: Quando l'output richiede un oracolo deterministico o quando l'agente è vittima di allucinazione confermativa.
* **Implementazione NK**: CoVe (Chain-of-Verification) per System Instructions (`[RULE-04.7]`).

### [ITER-02] Debate (Tesi vs Antitesi → Sintesi)
* **Descrizione**: Un agente propone, un altro critica attivamente, un terzo fa la sintesi.
* **Trigger**: Decisioni architetturali (L2), bilanciamento trade-off (L0/L3).
* **Implementazione NK**: `NK-Ideator` o `NK-Master-Hub` in modalità `/novice` o `/expert`.

### [ITER-03] Ratchet Loop CRV 2.0
* **Descrizione**: Loop di correzione guidato da test deterministici, senza intervento umano, con circuit breaker dopo N fallimenti.
* **Trigger**: Bug fixing, test dinamici, compilazione fallita (`[RULE-01.1 RATCHET LOOP]`).
* **Implementazione NK**: Delega a `NK-Oracle-Evaluator` (Oracolo) in `%TEMP%` sandbox. Exit Code 0 obbligatorio.

### [ITER-04] STORM Persona Interviews
* **Descrizione**: Agenti assumono il ruolo di esperti/utenti simulati per intervistare o testare l'idea/app.
* **Trigger**: Ideazione concettuale (`[RULE-02.2]`), comandi `/playtest`.

## 🛡️ FAMIGLIA 4: Pattern di Resilienza & Governance

### [RES-01] Circuit Breaker
* **Descrizione**: Interruzione forzata di un loop o di una catena se le condizioni di errore persistono oltre una soglia.
* **Trigger**: Prevenzione di loop infiniti o spreco di token.
* **Implementazione NK**: Limite `loop_breaker_max: 3` nei file `SKILL.md`. Il Controller impone l'Halt.

### [RES-02] Checkpoint-Resume (Stato Persistente)
* **Descrizione**: Salvataggio del contesto a intervalli regolari per permettere il recupero post-crash.
* **Trigger**: Processi lunghi, rate limit, disconnessioni utente.
* **Implementazione NK**: `NK-Resume-Engine`, file `.nk` e l'architettura a `session_anchor.jsonl`. Usato durante il `Two-Phase Handoff Protocol`.

### [RES-03] Hierarchical Delegation (Manager → Specialist)
* **Descrizione**: Il Controller orchestra l'esecuzione, allocando i task agli agenti specializzati (Worker).
* **Trigger**: Orchestrazione multi-livello (L0, L1, L2, L3).
* **Implementazione NK**: Architettura nativa `NK-Master-Hub`.

### [RES-04] Cold Auditor Isolation (Zero-Bias Esterno)
* **Descrizione**: L'agente che genera il codice/brief non può essere lo stesso che lo valuta o esegue il test.
* **Trigger**: Audit di sicurezza (TAS), Validazione Sandbox, Audit Brief.
* **Implementazione NK**: `[RULE-04.5] ISOLAMENTO & STRATIFICAZIONE AUDIT TAS`. Uso obbligatorio di sub-agenti remoti o asincroni (`NK-Oracle-Evaluator`).

---

## MATRICE DECISIONALE (Per il Controller)

Il Controller usa questa logica per consigliare le strategie all'utente o generare i prompt per il Worker:

```yaml
decision_matrix:
  bug_fix:
    complexity: high
    pattern: "[ITER-03] Ratchet Loop CRV 2.0"
    action: "Usa NK-Oracle-Evaluator e isola in Sandbox."
  
  brief_improvement:
    bias_risk: high
    pattern: "[RES-04] Cold Auditor Isolation + [PAR-01] Fan-Out"
    action: "Usa NK-Plan-Aligner e auditor isolati per la RULE-03.1."
  
  data_ingestion:
    volume: large
    pattern: "[PAR-02] MapReduce + [ITER-03] Taxonomy Loop"
    action: "Applica RULE-08. Dividi il dataset e usa ricerca deterministica."
  
  code_refactor:
    risk: destructive
    pattern: "[SEQ-03] Strangler Fig + [RES-01] Circuit Breaker"
    action: "VIETATO il Clean Slate. Applica modifiche atomiche. Verifica la RULE-01."
  
  exploration:
    options: multiple
    pattern: "[PAR-03] Swarm Competitivo"
    action: "Genera N alternative e usa un giudice per valutarle."
```

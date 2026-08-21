# 🛡️ Protocollo Operativo Costruttore (Builder Protocol)

**Questo file è la legge locale che forza l'applicazione delle Skill NK.**
Ogni prompt dato al Costruttore DEVE includere l'ordine di leggere questo file e le relative skill.

---

## REGOLA 1: Git Checkpoint Pre-Modifica (Promozione da Tip a Mandatoria)

*Deriva da: **NK-Master-Hub** (Auto-Commit Tip, L154)*

Prima di ogni batch di modifiche, il Costruttore esegue **obbligatoriamente**:
```powershell
cd "G:\Il mio Drive\Antigravity\agent-ide\nodo3-ce-sp"
git add -A
git commit -m "NK-CHECKPOINT: pre-[descrizione breve]"
```
Se qualcosa va storto, il rollback è un singolo comando (`git checkout HEAD~1 -- src_app/`).
**Non è negoziabile. Nessuna modifica senza checkpoint.**

---

## REGOLA 2: File Lock (Append-Only)

*Deriva da: **NK-Master-Hub** (`Preservation Lock`, L343)*

I file di frontend e backend vitali sono firmati con `[LOCK] NK-PRESERVATION-LOCK` in testa.
- ❌ VIETATO usare `write_to_file(Overwrite=true)` su questi file.
- ✅ PERMESSO solo patch chirurgiche (diff) tramite `replace_file_content` o file isolati `.new`.

Dopo ogni modifica, si verifica che il file non sia stato troncato:
```powershell
Get-Item "src_app\app.js","src_app\index.html","src_app\styles.css" | Select-Object Name, Length
```

---

## REGOLA 3: GET Before PUT (Rafforzamento Zero Self-Certification & Grounding)

*Deriva da: **NK-Oracle-Evaluator** (`Zero Self-Certification`) e **NK-Master-Hub** (`HARD_COMMIT_INTERCEPTION_GUARD`)*

Prima di modificare qualsiasi riga, il Costruttore DEVE:
1. Usare `view_file` (GET) per leggere il blocco esatto di righe target (Two-Stage Grounding Stage B).
2. Verificare che l'AST e la sintassi attuali siano come attesi.
3. Solo dopo, applicare la modifica chirurgica (PUT).

Se il contenuto non corrisponde alle aspettative (es. un altro agente lo ha alterato) → **FERMATI e segnala**. Non sovrascrivere "alla cieca".

---

## REGOLA 4: Handoff Strutturato (Clean Handoff Protocol v2.0)

*Deriva da: **NK-State-Router** & **NK-Session-Controller** (`TASK_HANDOFF_4_BLOCKS`)*

Ogni task delegato dal Supervisore/Critico al Costruttore/Lavoratore deve essere conforme al Clean Handoff Protocol v2.0 a 4 Blocchi (Blocco 1 Obiettivo & Brief Anchor Capsule, Blocco 2 Perimetro Chirurgico, Blocco 3 Two-Stage Grounding, Blocco 4 Criteri di Accettazione & Test).

---

## Come Usare Questo File (Template Prompt per il Costruttore)

Ogni volta che invochi un costruttore (es. NK-Python-Async-Builder, T-Builder, Lavoratore), usa **TASSATIVAMENTE** questa intestazione:

```markdown
🛡️ **ATTENZIONE COSTRUTTORE**: 
Sei tenuto a rispettare le regole NK (NK-Master-Hub, NK-Oracle-Evaluator, NK-Security-Auditor).
PRIMA DI FARE QUALSIASI COSA, leggi il manifesto operativo:
`view_file("G:\Il mio Drive\Antigravity\agent-ide\nodo3-ce-sp\nk_genome\builder_protocol.md")`

I file `app.js`, `index.html` e `styles.css` hanno la firma `[LOCK] NK-PRESERVATION-LOCK`.
Qualsiasi modifica deve passare per patch diff (surgical_replace) e MAI tramite sovrascrittura totale. Esegui SEMPRE un Git Checkpoint prima di agire.
```

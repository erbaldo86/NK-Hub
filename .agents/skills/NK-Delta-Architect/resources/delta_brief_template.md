# 🔧 NK-Delta-Architect: Delta Brief Template (v2.0 Brief-Aware)

> **Ambito:** Template di specifica incrementale conforme al Clean Handoff Protocol a 4 Blocchi `[RULE-02.6]`.

---

## 📋 Metadati del Task
- **Target Node:** [Nodo del DAG Impattato]
- **Change Scope:** [BUG_FIX | MODIFICATION | FEATURE | DEPRECATION]
- **Source Files SHA-256:** [Checksum dei file coinvolti]
- **Circuit Breaker Status:** [Tentativo X di 3]

---

### 🎯 BLOCCO 1: Obiettivo, Perché & Brief Anchor Capsule (Anti-Side Effect)
- **Problema Reale / Intent:** [Descrizione chiara del delta da applicare]
- **Effetto Collaterale da Evitare:** [Comportamenti regressivi o rotture da prevenire]
- **Brief Anchor Capsule (<= 350 token):**
  - *Visione / Obiettivo:* [Sintesi semantica dei requisiti]
  - *Milestone Anchor ID:* `[es. M-03-BUILDER-PYTHON-01]`
  - *Documenti Trittico:* `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"`

---

### 📍 BLOCCO 2: Perimetro d'Azione Chirurgico
- **File Target (Percorsi Assoluti Normalizzati):** `"G:/Il mio Drive/Antigravity/[path_relativo]"`
- **Classi / Funzioni:** `[Classe.metodo]` o `[funzione()]`
- **Nodi Discendenti Impattati (DAG Stale Status):** `[Nodo A]`, `[Nodo B]`
- **Scope Creep Guard:** Vietato toccare qualsiasi file o funzione non elencati in questo blocco.

---

### 🔍 BLOCCO 3: Direttiva di Two-Stage Grounding Obbligatorio (Anti-Blind Execution)
> [!IMPORTANT]
> **OBBLIGO DI TWO-STAGE GROUNDING:**
> 1. **Stage A (Brief Grounding):** Esegui `view_file` su `"G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md"` (slice <= 60 righe) per validare i requisiti ed estrarre il Milestone Anchor ID.
> 2. **Stage B (Code Grounding):** Esegui `view_file` con `StartLine` ed `EndLine` (slice <= 100 righe) sui file target sopra specificati.
> *(In Modalità Chat Isolata: Analizza lo snippet racchiuso in `<passive_data_context>` - max 150 righe).*

---

### ⚙️ BLOCCO 4: Istruzioni Chirurgiche, Criteri di Accettazione & Test
- **Pre-Edit Safety:** Arresta server/processi in background (`manage_task action='kill'`) per prevenire lock I/O `WinError 32` (`[RULE-01.3]`).
- **Modifiche Richieste:** [Dettaglio chirurgico delle modifiche]
- **Vincoli Tecnici:** Codifica UTF-8 strict, `replace_file_content` (no clean-slate), retry su backoff esponenziale.
- **Comando di Test:** `[Comando di test deterministico es. python -m pytest tests/...]`
- **Criterio di Accettazione:** Exit code 0 e output reale verificabile dall'Oracolo.

---

### 📋 Worker Execution Receipt v2.0 (Output Finale)
````markdown
### 📋 ESITO ESECUZIONE WORKER (Receipt v2.0)
- **🔍 Stage A (Brief Grounding):** `view_file` su `nk_genome/implementation_plan.md` confermato (Milestone Anchor ID: `{{ANCHOR_ID}}`).
- **🔍 Stage B (Code Grounding):** `view_file` eseguito su `{{FILE_PATH}}` (L{{START}}-L{{END}}).
- **🛠️ Surgical Diff:**
```diff
- {{OLD_CODE}}
+ {{NEW_SURGICAL_CODE}}
```
- **🧪 Test Evidence:** Comando `{{TEST_CMD}}` eseguito. Exit Code: `0`. Log: `{{TEST_OUTPUT_SUMMARY}}`.
- **Stato Finale:** `COMPLETED_SUCCESS` | `BLOCKED_NEED_INFO`
````


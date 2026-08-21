# 🛠️ Guida all'Installazione, Verifica & Convivenza Regole (NK-Hub Release v1.0)

> **Guida Ufficiale Passo-Passo** per installare tramite script automatico 1-Click o procedura manuale, gestire la convivenza delle regole in progetti esistenti ed avviare l'Ecosistema Multi-Agente NK-Hub in Antigravity 2.0.

---

## 💻 1. Requisiti di Sistema

Prima di iniziare, assicurati di avere installato:
- **Antigravity 2.0 (AGY / Google Antigravity)**.
- **Python 3.10+** (gestito automaticamente dai moduli standard `ast`, `json`, `psutil`).
- **Nessuna Chiave API Esterna Obbligatoria**: NK-Hub funziona out-of-the-box sfruttando il runtime di Antigravity 2.0.

---

## 📦 2. Installazione in 3 Passaggi (2 Metodi Disponibili)

### Passo 1: Clona o Apri il Workspace
- Apri il repository o la cartella root del tuo workspace in **Antigravity 2.0 (AGY)**.
- Assicurati che le cartelle `.agents/`, `scripts/`, `nk_genome/` e `nk_tracking/` siano presenti.

---

### ⚡ Metodo A: Installazione Automatica 1-Click (CONSIGLIATO)

All'interno dello zip troverai due script di installazione automatizzati `install.ps1` ed `install.sh`:

- 🪟 **Su Windows**: Apri PowerShell nella cartella del progetto ed esegui:
  ```powershell
  .\install.ps1
  ```
  **oppure** fai tasto destro sul file `install.ps1` ➔ **"Esegui con PowerShell"**.

- 🏎️ **Su macOS / Linux**: Apri il Terminale nella cartella ed esegui:
  ```bash
  chmod +x install.sh && ./install.sh
  ```

✅ **Cosa fa lo script**: Rende subito visibile la cartella nascosta `.agents/`, verifica le regole di governance in `AGENTS.md` e conferma che NK-Hub è pronto!

---

### 🛠️ Metodo B: Installazione Manuale

Se preferisci verificare le cartelle manualmente:
1. **Mostra elementi nascosti**: Su Windows attiva "Elementi nascosti" in Esplora File. Su Mac premi `Cmd + Shift + .`.
2. **Verifica Regole**: Assicurati che `.agents/AGENTS.md` sia presente nella root.

---

## 🤝 3. Gestione e Convivenza delle Regole in Progetti Esistenti

Se stai integrando NK-Hub in un progetto che possiede già un file `.agents/AGENTS.md` con regole personalizzate (linter, convenzioni DB, stack):
1. **Non sovrascrivere il tuo file**: Mantieni le tue regole preesistenti.
2. **Unisci le Regole NK**: Copia il blocco delle regole NK-Hub (`[RULE-01]`...`[RULE-10]`) ed appendilo in fondo al tuo file `AGENTS.md`.
3. **Convivenza Senza Conflitti**: Le regole NK-Hub governano l'orchestrazione dei sub-agenti ed il disaccoppiamento dei Builder, mentre le tue regole personalizzate continueranno a dettare lo stile del codice.

---

## 🧪 4. Test di Attivazione & Verifica

Per verificare che le regole NK-Hub e le tue regole preesistenti stiano convivendo in armonia, apri Antigravity 2.0 e copia/incolla questo prompt:

```text
Ciao! Ho appena installato NK-Hub nel workspace. Esegui un test di verifica dell'Ecosistema NK e dei nodi TAS, controlla la coerenza delle regole e guidami passo-passo per iniziare il nostro primo progetto.
```

Se l'agente avvia i sub-agenti di audit, registra l'ancora `session_anchor.jsonl` e risponde con il badge `🝡️ [NK-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]`, **le regole sono attive ed il workspace è configurato alla perfezione**!

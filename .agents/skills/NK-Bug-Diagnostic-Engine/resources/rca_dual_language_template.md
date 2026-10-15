# 🐞 Report Root Cause Analysis (RCA Dual-Language : `v3.0.0-STE100-Unified`)

> **Nodo Autore:** `NK-Bug-Diagnostic-Engine` (`100% Sola Lettura [RULE-00.1]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 1. Sintesi Esecutiva per l'Utente (Linguaggio Chiaro)
- **Sintomo Osservato:** [Descrivi il problema riscontrato in una frase attiva di massimo 20 parole]
- **Causa Principale:** [Spiega perché si verifica l'anomalia senza gergo superfluo]
- **Impatto Operativo:** [`BLOCCANTE` | `DEGRADATO` | `MINORE`]

---

## 2. Payload Tecnico per il Builder (SBFL Ochiai `< 80` token)
- **Componente Impattato:** `{{FILE_PATH}}:{{LINE_NUMBER}}`
- **Punteggio Ochiai (`suspiciousness`):** `{{OCHIAI_SCORE}}` (range `0.0` .. `1.0`)
- **Eccezione e Traceback Sintetico:**
  ```text
  {{COMPACT_TRACEBACK}}
  ```
- **Istruzione Chirurgica per `.staging/`:** [Indica la modifica esatta richiesta al Builder]
- **Comando Pytest di Verifica:** `python -m pytest {{TEST_FILE}} -q`

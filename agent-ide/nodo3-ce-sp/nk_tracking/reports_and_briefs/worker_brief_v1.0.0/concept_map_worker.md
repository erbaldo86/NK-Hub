# 🧠 Concept Map: Timeline Bi-Direzionale Perno-Centrata (Worker Brief v1.0.0)

🛡️ [NK-ASSIST - NK-App-Concept-Architect]

> [!NOTE]
> **Ambito Architetturale:** Riprogettazione della gestione temporale e del modello di rappresentazione multi-anno del **Nodo 3 (Chronos & Kairos - CE & SP Engine)**.
> **Stato:** PROPOSTA WORKER INDIPENDENTE (Zero-Bias Briefing)

---

## 🎯 1. Visione Generale & Valore di Business

La gestione temporale del Nodo 3 viene evoluta dal modello sequenziale monolitico/rigido (es. "Anno 1 / FY25", "Anno 2 / FY26") al nuovo paradigma di **Timeline Bi-Direzionale Perno-Centrata ($Y_0$-Centered Timeline)**.

### 💡 Il Problema Attuale
- Le diciture statiche `"Anno 1"`, `"Anno 2"`, `"FY25"`, `"FY26"` risultano fuorvianti quando l'utente carica bilanci storici di anni precedenti (es. 2023 vs 2024) o quando applica simulazioni previsionali pluriennali.
- L'assenza di un'ancora temporale chiara ($Y_0$) rende ambigua la distinzione tra **Dati Storici Consolidati ($Y_{-k}$)** e **Proiezioni Futura/Forecast ($Y_{+k}$)**.

### 🚀 La Soluzione Architetturale
- **Anno Perno ($Y_0$)**: Unico anno solare di riferimento centrale (es. $2025$), eletto dall'utente o dall'ingestion intelligence.
- **Espansione Bi-Direzionale**:
  - **A Sinistra ($Y_{-k}$)**: Esercizi storici precedenti a scendere ($Y_{-1} = 2024, Y_{-2} = 2023, \dots$).
  - **A Destra ($Y_{+k}$)**: Proiezioni e simulazioni future a salire ($Y_{+1} = 2026, Y_{+2} = 2027, \dots$).
- **Indicizzazione Relativa Coordinata**: Tutte le viste UI (KPI Toolbar, Header Tabelle, Dropdown Ratio, Ingestion Modal) calcolano le proprie etichette in modo dinamico rispetto a $Y_0$, mostrando contestualmente sia l'offset relativo ($Y_0, Y_{-1}, Y_{+1}$) sia il badge dell'anno solare effettivo ($2025, 2024, 2026$).

---

## 🔄 2. Flusso di Ingestion & Modale di Elezione Perno ($Y_0$)

Quando un documento multi-anno (es. ODS/XML/CSV contenente sia il 2025 sia il 2024) viene caricato dal Parser ERP:

```mermaid
flowchart TD
    A[📄 Ingestion File ERP / ODS / XML] --> B[🔍 Ingestion Parser Service]
    B --> C{Rilevati Più Anni?}
    C -- No (Single Year) --> D[Setta Y0 = Target Year]
    C -- Sì (es. 2025 & 2024) --> E[📊 Ingestion Multi-Anno Modal]
    
    E --> F[👤 Selezione Utente HITL]
    F -->|Scegli 2025 come Perno| G1[Setta Y0 = 2025<br/>2024 -> Y-1 Storico]
    F -->|Scegli 2024 come Perno| G2[Setta Y0 = 2024<br/>2025 -> Y+1 Forecast]
    
    G1 --> H[🧠 Dynamic MultiYearModel Engine]
    G2 --> H
    D --> H
    
    H --> I[🎨 Render UI Bi-Direzionale]
    I --> I1[Toolbar KPI Centrata Y0]
    I --> I2[Intestazioni Tabelle Y-1 | Y0 | Y+1]
    I --> I3[Dropdown Financial Ratios Anchored to Y0]
```

---

## 🏛️ 3. Riprogettazione dei 4 Moduli UI

### 🎛️ Modulo 1: Toolbar KPI Superiore (Pulsantiera Bi-Direzionale)
- **Visual Layout**:
  - `[ ⬅️ +1 Anno Storico (Y-2) ]` `[ 📄 Y-1 (2024) ]` `[ ★ Y0 (2025) - PERNO ]` `[ 📈 Y+1 (2026) ]` `[ +1 Anno Proiezione (Y+2) ➡️ ]`
- **Comportamento**:
  - Facendo click su qualsiasi badge anno, si seleziona l'anno attivo per l'ispezione analitica dei KPI.
  - Facendo click con pulsante destro o icona $\star$, l'utente può **Riassegnare il Perno ($Y_0$)** a qualsiasi anno presente in timeline con un solo click.

### 📐 Modulo 2: Orizzonte Anni Visibili (Scope Control)
- **Scope Dinamico**: $[Y_0 - m_{past}, Y_0 + m_{future}]$.
- **Controlli di Espansione**:
  - Spostamento indipendente della finestra visibile a sinistra ($m_{past}$) e a destra ($m_{future}$).
  - Filtro toggle rapido: *Solo Perno ($Y_0$)*, *Confronto Storico ($Y_{-1} \text{ vs } Y_0$)*, *Timeline Completa ($Y_{-k} \dots Y_0 \dots Y_{+k}$)*.

### 📊 Modulo 3: Intestazioni Tabelle CE & SP (Relative Dynamic Headers)
- Ogni colonna della griglia finanziaria reca un **Doppio Badge**:
  - **Badge Superiore Relativo**: 
    - Storico: `<span class="pivot-badge Y-prev">Y-1 (Storico)</span>`
    - Perno: `<span class="pivot-badge Y-pivot">★ Y0 (Perno)</span>`
    - Proiezione: `<span class="pivot-badge Y-next">Y+1 (Forecast)</span>`
  - **Badge Inferiore Solare**: `<span class="calendar-badge">2025</span>`
  - **Tag Tipo Dato**: `actual` (Consolidato), `forecast` (Previsionale), `budget` (Budget).

### 📋 Modulo 4: Dropdown SaaS & Financial Ratios
- Tutti i calcoli dei quozienti (DSCR, Solvency Ratio, Working Capital, Runway Cassa, Margini Margin %) si ancorano primariamente ad **$Y_0$**, con selettore rapido per l'analisi dei delta ($\Delta Y_0 - Y_{-1}$ o $\Delta Y_{+1} - Y_0$).

---

## 🎨 4. Design System & Palette Cromatiche

Per massimizzare la chiarezza visiva e prevenire errori di interpretazione nel vibe coding e nell'uso operativo:

| Dominio Temporale | Simbolo | Colore UI Token | Esadecimale / HSL | Significato Contabile |
| :--- | :---: | :--- | :--- | :--- |
| **Anno Perno ($Y_0$)** | `★ Y0` | `var(--accent-amber)` | `#f59e0b` / Glowing Gold | Anno di riferimento centrale attivo |
| **Anni Storici ($Y_{-k}$)** | `📄 Y-k` | `var(--accent-cyan)` | `#06b6d4` / Slate Cyan | Dati consuntivi e bilanci d'esercizio chiusi |
| **Proiezioni ($Y_{+k}$)** | `📈 Y+k` | `var(--accent-green)` | `#10b981` / Emerald Green | Stime economico-patrimoniali e forecast |
| **Scostamento ($\Delta$)** | `📊 Δ` | `var(--accent-purple)` | `#a855f7` / Deep Purple | Delta algebrico e percentuale tra esercizi |

---

## 💡 5. Intuizioni Originali & Gestione Edge Cases

### 1. Handling Anni Non Consecutivi (Gap Temporal Detection)
- **Edge Case**: L'utente carica un bilancio 2025 ($Y_0$) ed un bilancio 2022 ($Y_{-3}$), senza dati per il 2023 e 2024.
- **Soluzione Architetturale**: L'engine inserisce colonne placeholder per gli anni mancanti con badge `⚠️ GAP STORICO (Dati Mancanti)` ed attiva il supporto per il calcolo delle variazioni pluriennali aggregate senza spezzare la struttura matriciale.

### 2. Single-Click Dynamic Re-Pivoting
- L'utente può cliccare su qualsiasi intestazione di colonna per trasformare quell'anno nel nuovo $Y_0$. L'intera UI ricalcola istantaneamente tutti i badge relativi ($Y_{-1}, Y_{+1}$) ed aggiorna i KPI senza ricaricare la pagina.

### 3. Preservazione Compatibilità Engine Deterministico
- [`civil_code_math_engine.py`](file:///G:/Il%20mio%20Drive/Antigravity/agent-ide/nodo3-ce-sp/src_app/backend/civil_code_math_engine.py) opera su chiavi intere assolute (es. `2024`, `2025`, `2026`). Il mapping bidirezionale avverrà esclusivamente a livello di schema di presentazione ed orchestrazione stateful nel frontend e nei DTO Pydantic v2, lasciando l'engine matematico esente da modifiche (Zero Breakage Guarantee).

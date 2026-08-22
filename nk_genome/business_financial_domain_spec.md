# 🏛️ NK Genome: Business & Financial Engineering Domain Specification (v1.1.0-Universal)

> **Badge di Certificazione:** 🛡️ [NK-DOMAIN-STATUS: PRESERVED_AND_MIGRATED 🟢]  
> **Milestone Anchor:** `NK-MS-20260822-BUSINESS-DOMAIN-MIGRATION`  
> **Fonte Originaria:** Nodi Business NK (0: Brainstormer, 1A: Pitch Strutturale, 2: Financial Architect, 3: CE e SP, 4: Scenario Planner)

---

## 🎯 1. Visione del Dominio Economico-Finanziario

La presente specifica consolida e preserva le regole di business, i modelli algebrici ed i vincoli contabili italiani (Codice Civile art. 2424 e 2425) originariamente implementati nei Nodi Business 0-4 del Vecchio Modello NK, garantendone l'accessibilità da parte dei motori del Nuovo Modello v1.1.0-Universal.

---

## 📐 2. Regole Fiscali e Contabili Italiane (Codice Civile CEE)

### 2.1 Costo del Personale & Oneri Sociali
- **TFR (Trattamento di Fine Rapporto):** Quota TFR = Retribuzione Annua Lorda (RAL) * 7.41%.
- **Oneri Previdenziali & Assicurativi (INPS / INAIL):** Stima ordinaria pari al 30% sulla RAL.
- **Costo Aziendale Totale:** Costo Personale = RAL + Oneri Sociali (30%) + TFR (7.41%).

### 2.2 Dinamiche di Cassa, IVA & CCN
- **Aliquota IVA Ordinaria:** 22% applicata su costi operativi e ricavi per lo scorporo dei flussi finanziari netti.
- **Capitale Circolante Netto (CCN):**
  - **DSO (Days Sales Outstanding):** Tempo medio di incasso clienti (es. 60 giorni).
  - **DPO (Days Payable Outstanding):** Tempo medio di pagamento fornitori (es. 90 giorni).
  - **CCC (Cash Conversion Cycle):** Sfasamento temporale espresso in giorni per determinare l'assorbimento di liquidità.

### 2.3 CapEx & Piano di Ammortamento Lineare
- **Software / Licenze / Brevetti:** Aliquota del 20% annuo (durata ammortamento: 5 anni).
- **Macchinari / Attrezzature / Hardware:** Aliquota del 10% annuo (durata ammortamento: 10 anni).
- **Relazione EBIT / EBITDA:** EBIT = EBITDA - Ammortamenti.

### 2.4 Imposte e Oneri Finanziari
- **Oneri Finanziari (Anti-Loop Constraint):** Gli interessi passivi DEVONO essere calcolati TASSATIVAMENTE sul Debito Finanziario dell'Esercizio Precedente (N-1):  
  Oneri_N = Debito_{N-1} * (Euribor 3M + Spread)  
  (Parametri base 2026: Euribor 3M = 3.0%, Spread bancario = 2.0%, Tasso totale = 5.0%).
- **Aliquota Fiscale Aggregata (IRES + IRAP):** 27.9% (24.0% IRES + 3.9% IRAP base) calcolata su EBT > 0.
- **Loss Pool Tax Shielding:** Eventuali perdite pregresse (Loss_Pool_Residuo) decurtano l'imponibile EBT prima dell'applicazione delle imposte.

---

## 🧮 3. Scheletro Contabile Infallibile (CE e SP)

### 3.1 Conto Economico a Valore Aggiunto
- A) Valore della Produzione (Ricavi Netto IVA)
- B) Costi della Produzione (OpEx + Costo Personale)
- [=] EBITDA = A - B
- [-] Ammortamenti (CapEx Lineare)
- [=] EBIT = EBITDA - Ammortamenti
- [-] Oneri Finanziari (Tasso * Debito_{N-1})
- [=] EBT = EBIT - Oneri Finanziari
- [-] Imposte sul Reddito (27.9% * max(0, EBT - Loss Pool))
- [=] UTILE NETTO = EBT - Imposte

### 3.2 Posizione Finanziaria Netta (PFN)
PFN = Debiti Finanziari Totali - Cassa e Disponibilità Liquide

---

## 📊 4. KPI Engine Tiers

| Tier | Nome | Metriche Incluse |
| :--- | :--- | :--- |
| **T1** | **Essentials** | Gross Margin (%), EBITDA, EBITDA Margin (%), Burn Rate Mensile, Runway (mesi), Breakeven Point (BEP), Utile Netto. |
| **T2** | **VC & SaaS** | Metriche T1 + MRR/ARR, Churn Rate, CAC, LTV, LTV/CAC (>3x), CAC Payback Period (mesi), ARPU. |
| **T3** | **Corporate & Credit** | Metriche T2 + EBIT, EBT, PFN, Leva Finanziaria (PFN/EBITDA), Interest Coverage Ratio, Debt Capacity, DSCR. |
| **T4** | **Apex / Omnia** | Metriche T3 + Free Cash Flow (FCF), Cash Conversion Cycle (CCC), ROE (Return on Equity). |

> **Safeguard Divisione per Zero:** Se divisore = 0, contrassegnare la cella con [N/A - Zero Div].

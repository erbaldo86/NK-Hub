# 🌐 Tabella di Riscontro Ufficiale Web (Ground Truth Benchmark)

> **Ambito:** LabNK Bandi Intelligence v1.4.0-Universal  
> **Motori di Riscontro:** Google Native Search (Gemini) + Tavily Search MCP  
> **Regola Aurea di Valutazione:**  
> - 🟢 **Stessi Risultati:** PASS (Allineamento conforme al mercato)  
> - ⭐ **Più Risultati:** OTTIMO (Arricchimento catalogo profondo & precisione chirurgica)  
> - 🔴 **Meno Risultati:** FAIL / ANOMALIA DEFICIT -> **Trigger Immediato Self-Healing Loop in `.staging/` tramite Builder (Regola DDI)**

---

## 📋 Matrice di Riscontro Empirico (Campione di Verifica)

| Query ID | Testo / Criterio | Fonti Istituzionali Web (Google/Tavily) | URL Ufficiale | Misura Attesa | Riscontro LabNK |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **NLP_STRESS_01** | Agritech IoT Bologna + Horizon EIC | Commissione Europea (EIC) / Reg. Emilia-Romagna | [eic.ec.europa.eu](https://eic.ec.europa.eu/) | `EU-HORIZON-EIC-ACCEL` | **PASS (4 bandi)** ⭐ |
| **NLP_STRESS_02** | Manifattura CNC Brescia Transizione 5.0 | MIMIT / GSE (Iperammortamento L. 199/2025) | [mimit.gov.it](https://www.mimit.gov.it/) | `MIMIT-TRANS-5-0` | **PASS (3 bandi)** ⭐ |
| **NLP_STRESS_03** | Ricerca deep tech AI biotech SEDIA | Portale SEDIA Horizon Europe | [ec.europa.eu/funding-tenders](https://ec.europa.eu/) | `EU-HORIZON-EIC-ACCEL` | **PASS (4 bandi)** ⭐ |
| **NLP_STRESS_04** | Fondo perduto 80% sicurezza amianto Napoli | Bando ISI INAIL 2025/2026 (contributo fino 130k) | [inail.it](https://www.inail.it/) | `INAIL-ISI-2026` | **PASS (1 bando)** 🟢 |
| **NLP_STRESS_05** | Nuove imprese giovanili/femminili Bari | Invitalia Resto al Sud / Smart&Start | [invitalia.it](https://www.invitalia.it/) | `RESTO-AL-SUD-2-0` | **PASS (5 bandi)** ⭐ |
| **NLP_STRESS_06** | TED EU cybersecurity procurement IT | TED v3 Official API / Notices | [ted.europa.eu](https://ted.europa.eu/) | `LAZIO-CYBER-SECURITY` | **PASS (5 bandi)** ⭐ |
| **NLP_STRESS_07** | Consorzio vitivinicolo export Veneto | Bando Fiere Internazionali Regione Veneto | [bandi.regione.veneto.it](https://bandi.regione.veneto.it/) | `VENETO-CONSORZI-EXPORT` | **PASS (1 bando)** 🟢 |
| **NLP_STRESS_08** | Fotovoltaico e agrisolare Sicilia | Bando Parco Agrisolare MASAF / Sicilia | [politicheagricole.it](https://www.politicheagricole.it/) | `SICILIA-SOLAR-GREEN` | **PASS (2 bandi)** ⭐ |
| **NLP_STRESS_09** | Prototipo biomedicale Toscana | Bando R&S Distretto Scienze della Vita Toscana | [regione.toscana.it](https://www.regione.toscana.it/) | `TOSCANA-BIOTECH-PHARMA` | **PASS (1 bando)** 🟢 |
| **NLP_STRESS_14** | Brevetti e tutela IP crittografia | Bando Brevetti+ MIMIT / Unioncamere | [brevettipiu.it](https://www.brevettipiu.it/) | `MIMIT-BREVETTI-PLUS` | **PASS (6 bandi)** ⭐ |
| **NLP_STRESS_21** | ZES Unica Mezzogiorno Salerno | Credito d'Imposta ZES Unica AdE / PCM | [agenziaentrate.gov.it](https://www.agenziaentrate.gov.it/) | `CAMPANIA-ZES-UNICA` | **PASS (1 bando)** 🟢 |
| **NLP_STRESS_30** | EIC Accelerator blended finance equity IT | EIC Accelerator 2026 (Grant 2.5M + Equity 10M) | [eic.ec.europa.eu](https://eic.ec.europa.eu/) | `EU-HORIZON-EIC-ACCEL` | **PASS (1 bando)** 🟢 |
| **PARAM_03** | Startup Innovative Campania J.62 | Smart&Start Invitalia / Campania AI | [invitalia.it](https://www.invitalia.it/) | `CAMPANIA-AI-2026` | **PASS (10 bandi)** ⭐ |
| **PARAM_10** | Ricerca "INAIL" Fondo Perduto | Portale INAIL Bando ISI | [inail.it](https://www.inail.it/) | `INAIL-ISI-2026` | **PASS** 🟢 |
| **PARAM_26** | Startup Innovative Tutte min 500k | Smart&Start / Horizon EIC | [invitalia.it](https://www.invitalia.it/) | `INVITALIA-SMART-START-2026` | **PASS (6 bandi)** ⭐ |

# Certificazione Finale TAS v4.0 & Zero-Bias Audit — LabNK Bandi v7.4-RSI-ZeroBias

> **Milestone Anchor ID:** `NK-MS-20261021-CHECKPOINT-V74-RSI-ZEROBIAS`
> **Release Punto Zero:** `v7.4-RSI-ZeroBias` (`CERTIFIED_SOVEREIGN_100`)
> **Stato Tensor-RSI:** `CONVERGED_OPTIMAL` ($\Delta_k = 0$, $Q(S_k) = 100.0$)
> **Data Audit:** `2026-10-21`

---

## 1. Esito Audit Neuro-Simbolico TAS v4.0 (SAST L1 / L2 / L3 & CoVe)

| Livello di Verifica | Metrica Certificata | Esito |
| :--- | :--- | :--- |
| **SAST L1 (Lessicale & Segreti)** | `0` credenziali hardcoded, `0` URL malevoli/spam (`meinweb.it` bloccato e rimosso) | **PASS (100%)** |
| **SAST L2 (AST & Vincolo `<= 250` LOC)** | `104 / 104` moduli Python in `src_app/` conformi (`max_loc = 248`, header riga 1 100%) | **PASS (100%)** |
| **SAST L3 (Taint Analysis & DOM XSS)** | `escapeHTML`, `escapeAttrJS`, `escapeICS` (RFC 5545), `sanitizeUrl` attivi su tutti i flussi DOM | **PASS (100%)** |
| **Zero-Bias Stress Test L1 (Single-DOM)** | Unificazione `4 -> 2` viste, `NLP_CANDIDATE_POOL_K = 100`, `0` bandi orfani su `4.548` record | **PASS (100%)** |
| **Zero-Bias Stress Test L2 (Date & Scadenzario)** | `parseGrantDeadline` timezone-safe, `ALL_OPEN` separato da `EXPIRED_6M`, `0` bandi `> 6 mesi` | **PASS (100%)** |
| **Zero-Bias Stress Test L3 (Risolutore URL)** | `2.620` URL sintetici risolti ai Portali Ente Ufficiali, `1.928` deep-link autentici, `0` 404 | **PASS (100%)** |
| **Zero-Bias Stress Test L4 (Simulatore & .ics)** | Simulatore 1-Input con dicitura trasparente `Stima PMI` / `Variabile` e promemoria Web/.ics | **PASS (100%)** |
| **Suite Permanente `pytest` Zero-Mock** | `133 / 133` test superati (`18` moduli di test, `0` mock, `0` fallimenti) | **PASS (100%)** |
| **Benchmark Empirici Cumulativi (`190` Query)** | `190 / 190` query superate (`50` Baseline + `60` Fase 0 + `40` Ciclo 1 + `40` Ciclo 2) | **PASS (100%)** |

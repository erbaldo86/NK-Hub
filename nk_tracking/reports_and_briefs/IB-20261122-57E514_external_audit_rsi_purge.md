# Brief Esecutivo (`IB-20261122-57E514`): Audit Esterno, Hardening RSI e Potatura Suite

> **Milestone:** `NK-GEN-1.3.0-EXTERNAL-AUDIT-RSI-PURGE` | **Brief:** `IB-20261122-57E514` | **Standard:** `[RULE-STE100]`

## 1. Sintesi Valutazione Esterna su `Build 1 a+b`
L'audit indipendente ha valutato `Build 1 a+b` (`NK-GEN-1.2.0`) con sonde CLI reali e quattro agenti Swarm.
La verifica ha confermato progressi reali su `REFACTOR_EQUIVALENT`, isolamento `reexports` e qualità differenziale.
L'audit ha però rilevato sei bias metrologici, undici difetti critici `P0`, dieci cluster `P1` e auto-DoS sui test.

## 2. Evidenze Empiriche Prima della Bonifica
* **Auto-DoS Golden Test:** `dast_sandbox_runner --profile evaluator --verify-holdout` fallisce per timeout oltre `120` secondi su `605` test (`131.38s` in NVMe).
* **Bias e Metric Gaming:** `ab_benchmark` confronta byte su `205000` token (`5.53%`), ripete tre volte e gonfia `B2-09..11`.
* **Difetti `P0` Sicurezza e Motore:** Leak `os.environ` in `platform_runner`, budget mutation aperto, bypass `is_self_validator`, junction Win32 ed SBFL rotto.
* **Dead Code e Padding:** Diciannove file padding contengono `297` test su `605` e quindici classi stub camuffate.

## 3. Obiettivi Approvati (`A1 + A2 + A3`)
1. **Ondata 1 (`P0/P1` Core):** Chiudere tutte le falle di sicurezza, isolamento sandbox, rollback per-ID, `2-Strike` reale ed SBFL `n_ep > 0`.
2. **Ondata 2 (`RSI` Onesto):** Cablare canali CLI `mutation`/`dast`/`allowed-files`, proteggere `benchmark_suite/*.json`, fissare `ratchet_core` e `ab_benchmark`.
3. **Ondata 3 (`OCCAM` & Debloat):** Ritirare cinque script inermi, unificare `sbfl_engine` in `sbfl_pytest_bridge`, snellire skill `DOM-03` e tracking.
4. **Ondata 4 (`Golden Purge`):** Salvare quattro test unici, potare diciannove file `TIER-3`, consolidare `TIER-2` verso `<= 45s` e `>= 86%` coverage.
5. **Ondata 5 (`GT-14` & `2PC`):** Self-audit anti-residui, verifica fredda `NK-Security-DAST-Auditor` e `NK-RSI-Auditor`, promozione atomica e sync `NK-Scribe-Agent`.

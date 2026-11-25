# Protocollo Operativo Tensor-RSI v3 (`v1.0.0-Generation`)

> **Ambito:** Control Plane `DOM-01` (`scripts/tensor_rsi.py`), Policy ACS, `epsilon`-Pareto Gate, Bandit e Commit `2PC`.
> **Standard:** Italiano Tecnico ASD-STE100 (`[RULE-STE100]`, frasi `<= 20` parole).

## 1. Control Plane `DOM-01` e Ticket HMAC
1. Esegui ogni transizione via `NK_Hub/scripts/tensor_rsi.py` usando solo i `5` flag CLI ammessi (`--step`, `--ticket`, `--input`, `--root`, `--json`).
2. Firma i ticket `trsi1.<payload>.<hmac>` con chiave HMAC esterna fuori repository e anti-replay `step_seq` sotto `Win32NamedMutex`.
3. Classifica l'intento ortogonale su `4` track: `IMPROVEMENT`, `OPTIMIZATION`, `CONTROL`, `DOC_SPEC`.

## 2. Policy Tensor ACS e `epsilon`-Pareto Gate
1. Leggi `fastguard_<cid>.json` (`Z0..Z3`): riduci branching (`3 -> 1` su `Z1/Z2`), rispetta i slice cap e blocca mutazioni su `Z3`.
2. Valuta `Tier 0` disgiunto (`G_hard_code` / `G_hard_doc`), `Tier 1` a regressione zero (`epsilon = 0`) e `Tier 2` banda `epsilon`-Pareto.
3. Emetti `CONVERGED_OPTIMAL` solo con `g_hard == 1` e `q_v2 == 100.0`.
4. Rimuovi `last_summary`, score storici e narrative persuasive L3 via `strip_l3_persuasive_narrative(bundle)` prima dell'audit `DOM-04`.

## 3. Bandit `COLD / WARM / CALIBRATED` e Blocco `2PC`
1. Gestisci `ParetoArchive <= 12`, `NoveltyGate`, `CladeBandit` (`K=4`) su probe stocastici e stop `VoI` (`g_hard == 1`, `k >= 2`).
2. `win32_2pc_engine.py` e `nk_hook_gate` bloccano `--promote-staging` se `nk_tracking/tensor_sessions/ACTIVE.json` non ha `accepted == True` o `staging_manifest_sha256` corrente.
3. I token `v2:` e `--promote-staging` CLI applicano anti-replay in `nonce_store.py` sotto `Win32NamedMutex`.
4. L'oracolo esige copertura `true_branch >= 82.0%` floor (`>= 80.5%` target legacy, `>= 82.0%` live), `tensor_rsi_lock.json` integro e tracciamento holdout in `transcript_scan.py`.

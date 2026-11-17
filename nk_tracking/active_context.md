# Contesto Operativo Attivo NK Hub Generation

## Stato Corrente della Sessione
1. **Versione Attiva:** `1.0.0-Generation`.
2. **Profilo Modello:** `generation`.
3. **Milestone Attivo:** `NK-GEN-1.0.0`.
4. **Ultimo Turno FSM:** `1` con stato `PASS`.
5. **Baseline Test:** `513` test con pass rate `100.0%`.

## Regole Operative Prioritarie
1. Esegui tutte le modifiche esclusivamente nella directory `.staging/`.
2. Valida ogni modifica con `ast_guard_validator.py` prima della promozione.
3. Verifica la convergenza matematica con `rsi_convergence_engine.py`.
4. Promuovi i file in produzione tramite `win32_2pc_engine.py`.

## Delta & Stato Operativo Corrente
- **File in .staging/:** nessuno.

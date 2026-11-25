# Checklist JIT: MODE_FORGE_L1 (`v1.0.0-Generation`)

> **Ambito:** Forgiatura e allineamento file `.md` e regole L1 in `.staging/.agents/`.
> **Bilancio:** Carica questa checklist solo quando modifichi `SKILL.md`, `agent.md` o regole.

## 1. Grounding ed Integrita Documentale
1. Leggi `nk_genome/implementation_plan.md` prima di scrivere qualsiasi istruzione.
2. Verifica i flag CLI reali negli script sorgente Python prima di citarli.
3. Conserva i blocchi `<rsi_micro_loop>` ed i tag `1.0.0-Generation` richiesti da `skill_golden_eval_set.json`.
4. Imposta `enable_subagent_tools: false` ed `enable_mcp_tools: false` sui subagent foglia.

## 2. Regole ASD-STE100 e Qualita Lessicale
1. Scrivi frasi attive brevi sotto le 20 parole.
2. Vieta qualsiasi trattino spaziato nel testo Markdown fuori dai blocchi di codice.
3. Mantieni ogni checklist JIT sotto 1.200 token effettivi.
4. Esegui `nk_transcript_tools.py lint-ste100 --file <file> --strict --json` sui file modificati.

## 3. Allineamento Gemelli, 2-Strike e Verifica Finale
1. Sincronizza i manifesti gemelli e verifica la convergenza `ste100_rsi`:

```powershell
python -B -u NK_Hub/scripts/nk_registry_indexer.py --sync --sync-staging --json
python -B -u NK_Hub/scripts/rsi_convergence_engine.py --vibe-check NK_Hub/.staging --profile ste100_rsi --strict-verify --json
```

2. Verifica `Q_v2(S_k) = 100.0`, `G_hard == 1` e stato `STATIC_PASS` nell'output JSON (`STE100_RSI`).
3. Limita la sequenza di modifica a 2 file per batch e applica il blocco `2-Strike`.
4. Segnala ogni conflitto nei test congelati con `nk_transcript_tools.py report-conflict`.

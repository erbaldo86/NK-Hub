# DOM-00: Bridge Root, Plugin, Hook e Regole di Sistema (`v1.0.0-Generation`)

## 1. Perimetro e Stato `DOM-00`

Il dominio `DOM-00` governa il bootstrap zero-discovery, il plugin `nk-gate`, gli hook runtime e le regole anti-crash (`NK-GEN-1.0.0`).
I path operativi risiedono in `../00_GENOME_INDEX.md`, `shards/DOM-00.json` e `.agents/plugins/nk-gate/`.

| ID | Componente Reale | Percorso Canonico | Funzione Chiave |
| :--- | :--- | :--- | :--- |
| `B-01` | Bridge Root | `../.agents/AGENTS.md` | Instrada verso `NK_Hub` con `[RULE-00.4]` e `[RULE-00.5]` |
| `B-02` | Manifest Root | `.agents/plugins.json`, `.agents/skills.json` | Montano `nk-gate` e il catalogo `11` skill JIT |
| `B-03` | Costituzione Hub | `.agents/AGENTS.md` | Regole `[RULE-00]`..`[RULE-WIN32-ISOLATED-PYTEST]` per Topologia `2-Tier` |
| `B-04` | Guardie Windows | `.agents/rules/anti_crash_rules.md` | I/O Windows, `[RULE-WIN32-ISOLATED-PYTEST]` e `[RULE-NO-LITERAL-ENV-PATH]` |
| `B-05` | Plugin Hook & Mount | `.agents/plugins/nk-gate/` | Monta `6/6` sub-agenti foglia e `rules/AGENTS.md` senza frontmatter |
| `B-06` | Hook Runtime | `.agents/plugins/nk-gate/hooks.json` | Esegue `5` hook con `python -S -B -u` senza `site-packages` |

## 2. Hardening Hook (`nk_hook_gate.py` e `nk_acs_fastguard.py`)

Tutti gli hook in `.agents/plugins/nk-gate/hooks.json` usano `python -S -B -u` per avvio istantaneo deterministico.

| ID | Modulo Python (`scripts/`) | Facciata / `_internal/` | Garanzia Operativa |
| :--- | :--- | :--- | :--- |
| `H-01` | `scripts/nk_hook_gate.py` | `_internal/nk_hook_gate/` (`<= 500` LOC) | Guard `PreToolUse` su shell e `call_mcp_tool`, fail-closed |
| `H-02` | `scripts/nk_acs_fastguard.py` | `_internal/nk_acs_fastguard/` (`<= 500` LOC) | Legge `saturation_thresholds.json` stdlib, isola `sessions/` |

Vincoli operativi attivi per `DOM-00`:
1. **Guard `PreToolUse`:** `nk_hook_gate.py` blocca redirezioni non quotate, mutazioni fuori `.staging/` e `call_mcp_tool` di scrittura.
2. **Re-Trigger L0 Incrementale:** `[RULE-00.6]` forza `--meta-prompt-gate` prima di ogni scrittura e `l0_gate_<cid>.json` sblocca l'hook.
3. **Baseline `--enforce-stop`:** registra il delta token intermedio evitando falsi blocchi con evidenza valida.
4. **Onboarding a `16` Shortcut:** `[RULE-00.5]` riconosce `8` trigger legacy e `8` trigger `Generation` in singolo passaggio CLI.

## 3. Flusso Single-Gate e Criteri di Verifica

```text
Prompt / Comando --> Hook (python -S -B -u) --> nk_acs_fastguard + nk_hook_gate
                 --> PreToolUse Guard       --> Blocca scritture fuori .staging/ e MCP
                 --> VibeSprintRouter       --> Single-Gate Mode D o 16 shortcut avvio
```

1. Il plugin `nk-gate` espone `6/6` sub-agenti in `agents/*.md` e `rules/AGENTS.md` verificati da `nk_registry_indexer.py --verify`.
2. Tutti i `5` hook girano sotto `python -S -B -u` con import di sola libreria standard.
3. Puntatore dati: [DOM-00.json](../shards/DOM-00.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

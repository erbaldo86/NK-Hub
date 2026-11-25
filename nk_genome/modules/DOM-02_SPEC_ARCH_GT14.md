# DOM-02: Specifica, Architettura e Confine GT-14 (`v1.0.0-Generation`)

## 1. Perimetro e Obiettivo `DOM-02` (`NK-GEN-1.0.0`)

Il dominio `DOM-02` governa ideazione, architettura backend, UX/UI di specifica, mappa AST e controllo `GT-14`.
La separazione netta tra lettura (`NK-Arch-Specifier`) e scrittura confinata (`NK-Specifier-Agent`) chiude il difetto `CRIT-01`.

| ID | Asset `DOM-02` | Tipo | Perimetro `v1.0.0-Generation` |
| :--- | :--- | :--- | :--- |
| `S-01` | `NK-Ideator` | Skill (`[0]`) | Ideazione `SCAMPER`, discovery `Mode D` automatico e Turno `1` FSM |
| `S-02` | `NK-System-Architect` | Skill (`[1]`) | `Pentad Sovrana 4+1`, UX/UI `8px/HSL`, DAG di Kahn, OpenAPI `3.0` e Pydantic `v2` |
| `S-03` | `NK-Arch-Specifier` | Agente Read-Only | Foglia `GT-14` con `enable_write_tools: false` e zero MCP |
| `S-04` | `NK-Specifier-Agent` | Agente Writer | Confina scritture a `.staging/nk_genome/` e `NK Proget/Locale/<Nome>/.staging/` (`Online/` RO) |

## 2. Enforcement `GT-14`, `CRIT-01` e Isolamento `NK Proget`

1. **`NK-Arch-Specifier` (`RO`):** Analizza architettura, contratti `L0` e DAG tramite `read_file` e `send_message`.
   I tool locali RO (`grep_search`, `find_by_name`, `list_dir`) restano ammessi solo se il runtime li espone.
2. **`NK-Specifier-Agent` (`Writer`):** Aggiorna `.staging/nk_genome/` senza `run_command`, `search_web`, `generate_image` o `mcp_*`.
3. **Chiusura `CRIT-01`:** Tutti i manifesti di dominio disabilitano `enable_mcp_tools: false` e `enable_subagent_tools: false`.
4. **Bundle unico `GT-14`:** `scripts/rsi_convergence_engine.py --emit-gt14-bundle --with-dast` genera l'evidenza unica per gli auditor.
5. **Isolamento `NK Proget/Locale/` e `Online/` RO:** Le nuove app nascono in `NK Proget/Locale/<Nome>/` (compat `NK_External_Projects/<Nome>/`), bloccando `NK Proget/Online/`.

## 3. Moduli Python `DOM-02`

| ID | Modulo Python | Funzione / `_internal/` | Ruolo Operativo |
| :--- | :--- | :--- | :--- |
| `P-01` | `scripts/ast_repo_mapper.py` | `_internal/ast_repo_mapper/` (`<= 500` LOC) | Genera `repo_map.md` completo (`scripts/`, `_internal/`, `schemas/`, `tests/`) STE100 |
| `P-02` | `scripts/external_project_scaffolder.py` | `ExternalProjectScaffolder` | Crea app in `NK Proget/Locale/<Nome>/` (compat `NK_External_Projects/`), blocca `NK Proget/Online/` (`[NK_PROGET_ONLINE_READONLY]`) |
| `P-03` | `scripts/env_capability_probe.py` | `probe_environment` | Espone probe deterministico librerie e runtime |

## 4. Criteri di Verifica `DOM-02`

1. `NK-Arch-Specifier` mantiene permessi read-only e zero invocazioni shell o MCP.
2. `ast_repo_mapper.py --repo-map` copre `scripts/`, `_internal/`, `schemas/` e `tests/` con zero violazioni STE100.
3. `external_project_scaffolder.py` rifiuta ogni target sotto `NK Proget/Online/`.
4. I dettagli completi di skill e moduli risiedono in [DOM-02.json](../shards/DOM-02.json) e [00_GENOME_INDEX.md](../00_GENOME_INDEX.md).

# 🏛️ Clean Handoff Protocol & 2-Tier Hub-and-Spoke Specification (`v1.0.0-Generation`)

> **Ambito:** Comunicazione strutturata tra `NK-Orchestrator` e i Builder in `.staging/`.  
> **Versione:** `v1.0.0-Generation` (Topologia 2-Tier, Dual-Execution `GT-14`, profilo `generation`/`carbon` `150/250` step e `1200` token).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

---

## 🧭 1. Principi Cardine e Guardie di Sicurezza

1. **Topologia 2-Tier (`[RULE-01]`, `GT-14`):** Delega la scrittura al Builder in `.staging/`. Affida l'audit agli Auditor read-only (`EnableWriteTools=False`).
2. **Two-Stage Grounding (`[RULE-02.5]`):** Stage A legge `nk_genome/implementation_plan.md` (`read_file <= 800` righe). Stage B legge i file target.
3. **Sicurezza Processi Win32 (`[RULE-01.3]`):** Prima delle modifiche arresta i demoni con `manage_task(Action="kill", TaskId="<id>")` o `scripts/safe_cleanup_dev_servers.py`.
4. **Compattazione Contesto (`[RULE-02.8]`):** Su `NK_MODEL_PROFILE=generation` o `carbon` (`150/250` step) usa `/compact` nella UI host ed esegui `scripts/nk_session_handoff.py`.
5. **Onestà Epistemica:** Rispetta `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]` definiti in `.agents/AGENTS.md`.

---

## 📦 2. Template 8A e Worker Execution Receipt v3.0

Il formato canonico di `Template 8A`, `Template 8B` e **Worker Execution Receipt v3.0** risiede in [`handoff_and_swarm_templates.md`](../references/handoff_and_swarm_templates.md).

- **BLOCCO 1:** Obiettivo e Capsule (`<= 1200` token profilo `generation`/`carbon`, `<= 350` standard).
- **BLOCCO 2:** Perimetro chirurgico in `.staging/` e simboli target.
- **BLOCCO 3:** `read_file` obbligatorio (`SKILL.md`, `implementation_plan.md`, file sorgente).
- **BLOCCO 4:** Modifica `UTF-8` senza BOM, verifica `exit_code: 0` e consegna **Worker Execution Receipt v3.0** (`< 1.800` caratteri).

---

## 🔄 3. Protocollo Passive State Handoff (`Template 12`, `[RULE-02.8]`)

1. Raccomanda `/compact` nella UI host per comprimere il contesto e azzerare le sentinelle su `CHECKPOINT` o `<CONTEXT_SUMMARY>`.
2. Genera il `Template 12` (`<= 1200` token profilo `generation`/`carbon`) con `python -u scripts/nk_session_handoff.py --compile-handoff-prompt`, riservando `--compile-template-11` ai task operativi.
3. Valida il file con `python -u scripts/nk_transcript_tools.py lint-prompt --file <path> --mode state-handoff` contro `AP-12` e `AP-13`.
4. Su `[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]`, `python -u scripts/vibe_sprint_router.py --meta-prompt-gate --prompt "<testo>"` imposta `STATE_HANDOFF_STANDBY` in sola lettura.

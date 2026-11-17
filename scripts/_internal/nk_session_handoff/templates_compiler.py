# -*- coding: utf-8 -*-
"""Compilatore Intent Brief, Template 11 e Template 12 per nk_session_handoff."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Optional

from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_session_handoff.constants import (
    _FILE_HASH_MEMO,
    _dynamic_code_fence,
    _workspace_root,
)
from _internal.nk_session_handoff.session_state import (
    _compute_workspace_state_sha256,
    _read_baseline_pass_rate,
    _read_baseline_tests_count,
)
from _internal.nk_session_handoff.transcript_cursor import _format_safe_capsule_lines


def _resolve_eff_workspace_root() -> Path:
    """Risolve _workspace_root rispettando eventuali monkeypatch sulla facciata."""
    return Path(
        resolve_facade_attr(
            ("nk_session_handoff", "scripts.nk_session_handoff"),
            "_workspace_root",
            _workspace_root,
        )
    )


def persist_intent_brief(brief_id: str, prompt_text: str, project_root: str = "") -> Path:
    """Salva l'Intent Brief integrale con validazione percorso, code-fence dinamico e SHA-256."""
    raw_id = (brief_id or "").strip()
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_id).strip("_-")
    if not safe_id:
        safe_id = f"IB-{time.strftime('%Y%m%d')}-AUTO"
    clean_id = safe_id if safe_id.startswith("IB-") else f"IB-{safe_id}"

    eff_ws_root = _resolve_eff_workspace_root()
    target_root = eff_ws_root.resolve()
    if project_root and project_root.strip():
        cand_root = Path(project_root.strip())
        if cand_root.exists() and cand_root.is_dir():
            target_root = cand_root.resolve()

    reports_dir = (target_root / "nk_tracking" / "reports_and_briefs").resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    ib_file = (reports_dir / f"{clean_id}.md").resolve()
    if not ib_file.is_relative_to(reports_dir):
        raise ValueError(f"Percorso Intent Brief fuori da reports_dir vietato: {brief_id!r}")

    effective_proj = str(target_root).replace("\\", "/")
    clean_prompt = (prompt_text or "").strip()
    fence = _dynamic_code_fence(clean_prompt, min_len=3)
    prompt_block = f"{fence}text\n{clean_prompt}\n{fence}"
    block_sha256 = hashlib.sha256(prompt_block.encode("utf-8")).hexdigest()

    content = (
        f"# Intent Brief Persistito: `{clean_id}`\n\n"
        f"- **Brief ID:** `{clean_id}`\n"
        f"- **Timestamp UTC:** `{int(time.time())}`\n"
        f"- **Project Root:** `{effective_proj}`\n"
        f"- **Prompt Block SHA-256:** `{block_sha256}`\n\n"
        f"## Prompt Integrale e Vincoli Operativi\n\n"
        f"{prompt_block}\n"
    )
    raw_bytes = content.encode("utf-8")
    ib_file.write_bytes(raw_bytes)
    try:
        st = ib_file.stat()
        _FILE_HASH_MEMO[str(ib_file)] = (
            st.st_mtime_ns,
            st.st_size,
            hashlib.sha256(raw_bytes).hexdigest(),
        )
    except OSError:
        pass
    return ib_file


def compile_template_11_prompt(
    project_root: str = "",
    milestone_id: str = "Auto-Saved Milestone",
    capsule: str = "",
) -> str:
    """Compila un prompt strutturato conforme al Template 11 e STE100."""
    proj_norm = (project_root or str(_resolve_eff_workspace_root())).replace("\\", "/")
    pytest_env_tok = "_".join(("PYTEST", "CURRENT", "TEST"))
    safe_cap = _format_safe_capsule_lines(capsule.splitlines()) if capsule else "{}"
    fence = _dynamic_code_fence(safe_cap, min_len=3)
    return (
        "# Turnkey Hand-off Prompt (Template 11: SOVEREIGN_SWARM_TASK_PROMPT)\n\n"
        "Riprendi la sessione dallo stato salvato con i protocolli intrinseci attivi.\n\n"
        f"Orchestra lo Swarm 2-Tier (`[RULE-01]`) sul progetto `{proj_norm}` per il Milestone `{milestone_id}`.\n\n"
        "### PASSO 0: Bootstrap, Cleanup e Intent Brief (`[RULE-00.4]`, `[RULE-00.6]`, `[RULE-01.3]`)\n"
        "1. Esegui `python scripts/nk_session_bootstrap.py` e ferma i server orfani con `python scripts/safe_cleanup_dev_servers.py`.\n"
        "2. Leggi l'Intent Brief salvato in `nk_tracking/reports_and_briefs/IB-*.md` e il piano `nk_genome/implementation_plan.md`.\n"
        "3. Registra il Builder operativo con `define_subagent(EnableWriteTools=True, EnableSubagentTools=False)` prima della Fase Build.\n"
        f"4. Rispetta `[RULE-EPISTEMIC-HONESTY]` (`report-conflict`, divieto `{pytest_env_tok}`/`currentframe`/`len(grants)`), `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.\n\n"
        "### FASE 1: Discovery e Audit in Sola Lettura (Mode D)\n"
        "- Delega con `invoke_subagent` e `<env_capsule>` la verifica dello stato reale a `NK-RSI-Auditor` e `NK-Security-DAST-Auditor`.\n"
        "- Partiziona i batch superiori a 8 query web su sub-agenti `research` paralleli.\n"
        f"- Congela l'oracolo di test con `python scripts/nk_transcript_tools.py oracle-lock create --root \"{proj_norm}\"` (`[RULE-ORACLE-LOCK]`).\n"
        "- `STOP_GATE`: presenta i gap reali misurati (`Measure-First`) tramite `ask_question` prima di modificare i file.\n\n"
        "### FASE 2: Build Chirurgico in `.staging/` (Mode B/A)\n"
        f"- Delega con `invoke_subagent` al Builder registrato (`EnableWriteTools=True`) la scrittura esclusiva in `{proj_norm}/.staging/`.\n"
        f"- Inietta in `<env_capsule>` le regole `[RULE-EPISTEMIC-HONESTY]` (`report-conflict`, divieto `{pytest_env_tok}`), `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.\n"
        "- Esegui il Two-Stage Grounding (`[RULE-02.5]`) leggendo il modello Pydantic target prima di modificare i dati.\n"
        f"- Valida il codice in staging con `python scripts/ast_guard_validator.py --stage-dir \"{proj_norm}/.staging\"`.\n\n"
        "### FASE 3: Verifica Indipendente, Commit 2PC e Scribe\n"
        "- Delega a `NK-RSI-Auditor` la verifica indipendente dei test reali e la convergenza matematica:\n"
        f"  `python scripts/rsi_convergence_engine.py --verify --root \"{proj_norm}\" --benchmark-suite \"{proj_norm}/tests\"`\n"
        "- Esegui la promozione atomica solo dopo esito `PASS` reale (`[RULE-EVIDENCE]`):\n"
        f"  `python scripts/win32_2pc_engine.py --promote-staging --repo-root \"{proj_norm}\"`\n"
        "- Delega infine a `NK-Scribe-Agent` l'aggiornamento prepend-only di `PATCH_NOTES.md` e `repo_map.md`.\n\n"
        "### Capsule Info\n\n"
        f"{fence}json\n{safe_cap}\n{fence}\n"
    )


def compile_template_12_state_handoff(
    project_root: str = "",
    milestone_id: str = "Auto-Saved Milestone",
    capsule: str = "",
    completed_summary: str = "Sessione precedente chiusa con stato verificato.",
    open_context: str = "Nessun task attivo pre-assegnato. In attesa di direttive utente.",
    state_sha256_override: Optional[str] = None,
) -> str:
    """Compila un handoff passivo dello stato di sessione conforme al Template 12."""
    eff_ws_root = _resolve_eff_workspace_root()
    target_root = Path(project_root).resolve() if project_root else eff_ws_root.resolve()
    proj_norm = str(target_root).replace("\\", "/")
    hub_norm = str(eff_ws_root.resolve()).replace("\\", "/")
    total_tests = _read_baseline_tests_count(target_root)
    pass_rate = _read_baseline_pass_rate(target_root)
    state_sha256 = state_sha256_override or _compute_workspace_state_sha256(target_root)
    safe_cap = _format_safe_capsule_lines(capsule.splitlines()) if capsule else "{}"
    fence = _dynamic_code_fence(safe_cap, min_len=3)
    clean_summary = (completed_summary or "Sessione precedente chiusa con stato verificato.").strip()
    clean_open = (open_context or "Nessun task attivo pre-assegnato. In attesa di direttive utente.").strip()
    return (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n"
        "Modalità: [PASSIVE STATE HANDOFF / STANDBY MODE]\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n\n"
        "### 1. Identità e Percorsi Operativi\n"
        "- **Ruolo Ricevente:** `NK-Orchestrator` in modalità passiva `STANDBY`.\n"
        f"- **Hub Root:** `{hub_norm}`.\n"
        f"- **Project Root:** `{proj_norm}`.\n"
        f"- **Milestone Anchor:** `{milestone_id}`.\n\n"
        "### 2. Stato Tecnico Verificato\n"
        f"- **Baseline Test Certificati:** `{total_tests}` test totali con pass rate `{pass_rate:.1f}%`.\n"
        f"- **Workspace State SHA-256:** `{state_sha256}`.\n"
        "- **Modalità Iniziale Gate L0:** `BYPASSED` (`STATE_HANDOFF_STANDBY`, `mode_d` sola lettura).\n\n"
        "### 3. Ultima Attività Conclusa\n"
        f"- **Sintesi Attività:** {clean_summary}\n\n"
        f"{fence}json\n"
        f"{safe_cap}\n"
        f"{fence}\n\n"
        "### 4. Contesto Aperto Neutrale e Vincoli Costituzionali\n"
        f"- **Stato Aperto:** {clean_open}\n"
        "- **Invarianti Attivi:** Rispetta `[RULE-00]`, `[RULE-01]`, `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.\n"
        "- **Neutralità Cognitiva (`AP-13`):** Il presente handoff non impone alcuna pista prescrittiva e preserva la piena libertà analitica.\n\n"
        "### 5. Protocollo Ricezione Standby\n"
        "1. Esegui `python scripts/nk_session_bootstrap.py` e leggi passivamente `nk_genome/`.\n"
        "2. Conferma in modo sintetico l'acquisizione dello stato oggettivo.\n"
        "3. Vietato attivare `INTRINSIC_GOAL`, `INTRINSIC_PLAN`, invocare `ask_question` per proporre task autonomi o generare `implementation_plan.md`.\n"
        "4. Rimani in stato passivo `STANDBY` in attesa delle decisioni dell'utente.\n\n"
        "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]\n"
    )

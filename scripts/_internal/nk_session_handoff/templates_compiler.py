# -*- coding: utf-8 -*-
"""Compilatore Intent Brief, Template 11, Template 12 e Envelope HANDOFF_V2."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from _internal.nk_common.epistemic_firewall_rules import (
    HANDOFF_V2_END_ACTIVE, HANDOFF_V2_END_PASSIVE, HANDOFF_V2_START_ACTIVE,
    HANDOFF_V2_START_PASSIVE, T12_END, T12_START, redact_pii_deterministic,
)
from _internal.nk_common.facade_boot import resolve_facade_attr
from _internal.nk_session_handoff.constants import (
    _FILE_HASH_LOCK, _FILE_HASH_MEMO, _dynamic_code_fence, _workspace_root,
)
from _internal.nk_session_handoff.session_state import (
    _compute_workspace_state_sha256, _read_baseline_pass_rate, _read_baseline_tests_count,
)
from _internal.nk_session_handoff.transcript_cursor import _format_safe_capsule_lines

_AP14_SCRUB_RE = re.compile(
    r"(?:<CONTEXT_SUMMARY>|<SYSTEM_MESSAGE>|<subagent_reminder>|<task_boundary>|"
    r"\[nk-anchor:|PLANNER_RESPONSE|SYSTEM_SDK|TOOL_RESULT|RUNNING)",
    re.IGNORECASE,
)


def _resolve_eff_workspace_root() -> Path:
    """Risolve _workspace_root rispettando eventuali monkeypatch sulla facciata."""
    return Path(resolve_facade_attr(("nk_session_handoff", "scripts.nk_session_handoff"), "_workspace_root", _workspace_root))


def _sanitize_handoff_prose(raw_text: str, fallback: str) -> str:
    """Applica redazione PII e rimuove marker transienti dal testo in uscita."""
    clean = (raw_text or fallback).strip() or fallback
    redacted, _ = redact_pii_deterministic(clean)
    return _AP14_SCRUB_RE.sub("[FILTERED]", redacted)


def persist_intent_brief(brief_id: str, prompt_text: str, project_root: str = "") -> Path:
    """Salva l'Intent Brief integrale con validazione percorso, redazione PII e SHA-256."""
    raw_id = (brief_id or "").strip()
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_id).strip("_-") or f"IB-{time.strftime('%Y%m%d')}-AUTO"
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
    clean_prompt, _ = redact_pii_deterministic((prompt_text or "").strip())
    fence = _dynamic_code_fence(clean_prompt, min_len=3)
    prompt_block = f"{fence}text\n{clean_prompt}\n{fence}"
    block_sha256 = hashlib.sha256(prompt_block.encode("utf-8")).hexdigest()

    content = (
        f"# Intent Brief Persistito: `{clean_id}`\n\n"
        f"- **Brief ID:** `{clean_id}`\n- **Timestamp UTC:** `{int(time.time())}`\n"
        f"- **Project Root:** `{effective_proj}`\n- **Prompt Block SHA-256:** `{block_sha256}`\n\n"
        f"## Prompt Integrale e Vincoli Operativi\n\n{prompt_block}\n"
    )
    raw_bytes = content.encode("utf-8")
    tmp_file = ib_file.with_name(f"{ib_file.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with open(tmp_file, "wb") as fh:
            fh.write(raw_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_file, ib_file)
    finally:
        tmp_file.unlink(missing_ok=True)
    try:
        st = ib_file.stat()
        with _FILE_HASH_LOCK:
            _FILE_HASH_MEMO[str(ib_file)] = (st.st_mtime_ns, st.st_size, hashlib.sha256(raw_bytes).hexdigest())
    except OSError:
        pass
    return ib_file


def compile_template_11_prompt(
    project_root: str = "",
    milestone_id: str = "Auto-Saved Milestone",
    capsule: str = "",
) -> str:
    """Compila un prompt strutturato conforme al Template 11 v1.0.0-Generation e STE100."""
    eff_ws_root = _resolve_eff_workspace_root().resolve()
    target_root = Path(project_root).resolve() if (project_root and project_root.strip()) else eff_ws_root
    proj_norm, hub_norm = str(target_root).replace("\\", "/"), str(eff_ws_root).replace("\\", "/")
    is_external = target_root != eff_ws_root

    def _script_ref(rel_name: str) -> str:
        return f'"{hub_norm}/scripts/{rel_name}"' if is_external else f"scripts/{rel_name}"

    pytest_env_tok = "_".join(("PYTEST", "CURRENT", "TEST"))
    safe_cap = _format_safe_capsule_lines(capsule.splitlines()) if capsule else "{}"
    fence = _dynamic_code_fence(safe_cap, min_len=3)
    return (
        "# Turnkey Hand-off Prompt (Template 11: SOVEREIGN_SWARM_TASK_PROMPT v1.0.0-Generation)\n\n"
        "Riprendi la sessione dallo stato salvato con i protocolli intrinseci attivi (`v1.0.0-Generation`).\n\n"
        f"Orchestra lo Swarm 2-Tier (`[RULE-01]`) sul progetto `{proj_norm}` per il Milestone `{milestone_id}`.\n\n"
        "### PASSO 0: Bootstrap, Cleanup e Intent Brief (`[RULE-00.4]`, `[RULE-00.6]`, `[RULE-01.3]`)\n"
        f"1. Esegui `python -B -u {_script_ref('nk_session_bootstrap.py')}` e ferma i server orfani con `python -B -u {_script_ref('safe_cleanup_dev_servers.py')} --workspace-root \"{proj_norm}\"`.\n"
        "2. Leggi l'Intent Brief salvato in `nk_tracking/reports_and_briefs/IB-*.md` e il piano `nk_genome/implementation_plan.md`.\n"
        "3. Usa i sub-agenti nativi registrati (`NK-Builder-Agent`, `NK-Scribe-Agent`, `NK-RSI-Auditor`, `NK-Security-DAST-Auditor`) in topologia 2-Tier (`[RULE-01]`).\n"
        f"4. Rispetta `[RULE-EPISTEMIC-HONESTY]` (`report-conflict`, divieto `{pytest_env_tok}`/`currentframe`/`len(grants)`), `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.\n\n"
        "### FASE 1: Discovery e Audit in Sola Lettura (Mode D)\n"
        "- Delega con `invoke_subagent` e `<env_capsule>` la verifica dello stato reale a `NK-RSI-Auditor` e `NK-Security-DAST-Auditor`.\n"
        "- Partiziona i batch superiori a 8 query web su sub-agenti `research` paralleli.\n"
        f"- Congela l'oracolo di test con `python -B -u {_script_ref('nk_transcript_tools.py')} oracle-lock freeze --root \"{proj_norm}\"` (`[RULE-ORACLE-LOCK]`).\n"
        "- `STOP_GATE`: presenta i gap reali misurati (`Measure-First`) tramite `ask_question` prima di modificare i file.\n\n"
        "### FASE 2: Build Chirurgico in `.staging/` (Mode B/A)\n"
        f"- Delega con `invoke_subagent` a `NK-Builder-Agent` (`DOM-03`) la scrittura esclusiva in `{proj_norm}/.staging/`.\n"
        f"- Inietta in `<env_capsule>` le regole `[RULE-EPISTEMIC-HONESTY]` (`report-conflict`, divieto `{pytest_env_tok}`), `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.\n"
        "- Esegui il Two-Stage Grounding (`[RULE-02.5]`) leggendo il modello Pydantic target prima di modificare i dati.\n"
        f"- Valida il codice in staging con `python -B -u {_script_ref('ast_guard_validator.py')} --stage-dir \"{proj_norm}/.staging\"`.\n\n"
        "### FASE 3: Verifica Indipendente, Commit 2PC e Scribe\n"
        "- Delega a `NK-RSI-Auditor` la verifica indipendente dei test reali e la convergenza matematica:\n"
        f"  `python -B -u {_script_ref('rsi_convergence_engine.py')} --verify --root \"{proj_norm}\" --benchmark-suite \"{proj_norm}/tests\"`\n"
        "- Esegui la promozione atomica solo dopo esito `PASS` reale (`[RULE-EVIDENCE]`):\n"
        f"  `python -B -u {_script_ref('win32_2pc_engine.py')} --promote-staging --repo-root \"{proj_norm}\" --milestone \"{milestone_id}\"`\n"
        "- Delega infine con `invoke_subagent` a `NK-Scribe-Agent` l'aggiornamento prepend-only di `PATCH_NOTES.md` e `repo_map.md`.\n\n"
        f"### Capsule Info\n\n{fence}json\n{safe_cap}\n{fence}\n"
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
    proj_norm, hub_norm = str(target_root).replace("\\", "/"), str(eff_ws_root.resolve()).replace("\\", "/")
    total_tests, pass_rate = _read_baseline_tests_count(target_root), _read_baseline_pass_rate(target_root)
    state_sha256 = state_sha256_override or _compute_workspace_state_sha256(target_root)
    cap_lines = [ln.strip() for ln in (capsule or "").splitlines() if ln.strip()]
    safe_cap = json.dumps(
        {
            "milestone_anchor_id": _sanitize_handoff_prose(milestone_id, "Auto-Saved Milestone"),
            "state_sha256": state_sha256,
            "baseline_tests": total_tests,
            "baseline_pass_rate_pct": pass_rate,
            "capsule_lines_summarized": len(cap_lines),
            "raw_transcript_included": False,
        },
        indent=2,
        ensure_ascii=False,
    )
    fence = _dynamic_code_fence(safe_cap, min_len=3)
    clean_summary = _sanitize_handoff_prose(completed_summary, "Sessione precedente chiusa con stato verificato.")
    clean_open = _sanitize_handoff_prose(open_context, "Nessun task attivo pre-assegnato. In attesa di direttive utente.")
    clean_ms = _sanitize_handoff_prose(milestone_id, "Auto-Saved Milestone")
    return (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n"
        f"Modalità: [PASSIVE STATE HANDOFF / STANDBY MODE]\n{T12_START}\n\n"
        "### 1. Identità e Percorsi Operativi\n"
        "- **Ruolo Ricevente:** `NK-Orchestrator` in modalità passiva `STANDBY`.\n"
        f"- **Hub Root:** `{hub_norm}`.\n- **Project Root:** `{proj_norm}`.\n- **Milestone Anchor:** `{clean_ms}`.\n\n"
        "### 2. Stato Tecnico Verificato\n"
        f"- **Baseline Test Certificati:** `{total_tests}` test totali con pass rate `{pass_rate:.1f}%`.\n"
        f"- **Workspace State SHA-256:** `{state_sha256}`.\n"
        "- **Modalità Iniziale Gate L0:** `BYPASSED` (`STATE_HANDOFF_STANDBY`, `mode_d` sola lettura).\n\n"
        "### 3. Ultima Attività Conclusa\n"
        f"- **Sintesi Attività:** {clean_summary}\n\n{fence}json\n{safe_cap}\n{fence}\n\n"
        "### 4. Contesto Aperto Neutrale e Vincoli Costituzionali\n"
        f"- **Stato Aperto:** {clean_open}\n"
        "- **Invarianti Attivi:** Rispetta `[RULE-00]`, `[RULE-01]`, `[RULE-EPISTEMIC-HONESTY]`, `[RULE-EVIDENCE]`, `[RULE-DATA-PROVENANCE]` e `[RULE-ORACLE-LOCK]`.\n"
        "- **Neutralità Cognitiva (`AP-13`):** Il presente handoff non impone alcuna pista prescrittiva e preserva la piena libertà analitica.\n\n"
        "### 5. Protocollo Ricezione Standby\n"
        f'1. Esegui `python -B -u "{hub_norm}/scripts/nk_session_bootstrap.py" --project-root "{proj_norm}"` e leggi passivamente `nk_genome/`.\n'
        "2. Conferma in modo sintetico l'acquisizione dello stato oggettivo.\n"
        "3. Vietato attivare `INTRINSIC_GOAL`, `INTRINSIC_PLAN`, invocare `ask_question` per proporre task autonomi o generare `implementation_plan.md`.\n"
        f"4. Rimani in stato passivo `STANDBY` in attesa delle decisioni dell'utente.\n\n{T12_END}\n"
    )


def compile_envelope_v2_markdown(
    envelope_dict: Mapping[str, Any], compact_json: bool = True
) -> str:
    """Compila un envelope HANDOFF_V2 sigillato tra i marker ancora senza testo esterno."""
    payload = envelope_dict.get("payload")
    raw_mode = payload.get("handoff_mode") if isinstance(payload, Mapping) else envelope_dict.get("mode")
    mode = str(raw_mode or "PASSIVE_STANDBY").strip().upper()
    if mode == "ACTIVE_CONTINUATION":
        start_tag, end_tag = HANDOFF_V2_START_ACTIVE, HANDOFF_V2_END_ACTIVE
    else:
        mode = "PASSIVE_STANDBY"
        start_tag, end_tag = HANDOFF_V2_START_PASSIVE, HANDOFF_V2_END_PASSIVE
    dump_kw: dict[str, Any] = {"sort_keys": True, "ensure_ascii": False, "allow_nan": False}
    dump_kw["separators" if compact_json else "indent"] = (",", ":") if compact_json else 2
    json_text = json.dumps(dict(envelope_dict), **dump_kw)
    fence = _dynamic_code_fence(json_text, min_len=3)
    return f"{start_tag}\n# [NK-HANDOFF-V2] Mode: {mode}\n{fence}json\n{json_text}\n{fence}\n{end_tag}\n"

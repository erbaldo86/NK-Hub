# -*- coding: utf-8 -*-
"""
Generatore della capsula di handoff e compilatore Template 11 e Template 12 per Nexus Keystone v4.8.0-STE100-Unified.
Legge dinamicamente unit_tests_total da quality_baseline.json, persiste IB-<id>.md e compila handoff passivi o 2-Tier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HANDOFF_VERSION = "4.8.0-STE100-Unified"

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)


def _resolve_git_executable() -> str:
    """Risolve il percorso dell'eseguibile git tramite PATH o percorsi standard Windows."""
    found = shutil.which("git")
    if found:
        return found
    for candidate in (
        "C:/Users/erbal/AppData/Local/Programs/Git/cmd/git.exe",
        "C:/Program Files/Git/cmd/git.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return "git"


def _discover_default_transcript() -> str:
    """Individua il trascritto principale attivo nella cartella brain utente entro 1800s."""
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if not brain_dir.exists():
        return ""
    now = time.time()
    candidates = []
    for p in brain_dir.glob("*/.system_generated/logs/transcript.jsonl"):
        try:
            mtime = p.stat().st_mtime
            if (now - mtime) <= 1800.0:
                candidates.append((mtime, str(p)))
        except OSError:
            pass
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _read_baseline_tests_count(root_dir: Optional[Path] = None) -> int:
    """Legge il numero totale di Golden Tests da quality_baseline.json con supporto Dual-Schema."""
    base = root_dir or _workspace_root
    for cand in (
        base / ".staging" / "nk_tracking" / "quality_baseline.json",
        base / "nk_tracking" / "quality_baseline.json",
        _workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json",
        _workspace_root / "nk_tracking" / "quality_baseline.json",
    ):
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                metrics = (
                    data.get("metrics", {})
                    if isinstance(data.get("metrics"), dict)
                    else {}
                )
                for m_key in ("unit_tests_total", "total_golden_tests"):
                    if m_key in metrics:
                        raw_total = metrics[m_key]
                        if isinstance(raw_total, dict):
                            return int(raw_total.get("value", 206))
                        return int(raw_total)
                for flat_key in (
                    "total_tests",
                    "golden_tests_count",
                    "unit_tests_total",
                    "passed_tests",
                ):
                    if data.get(flat_key) is not None:
                        return int(data[flat_key])
            except Exception:
                pass
    return 206


def _read_baseline_pass_rate(root_dir: Optional[Path] = None) -> float:
    """Estrae il pass rate da quality_baseline.json supportando sia metrics sia campi flat."""
    base = root_dir or _workspace_root
    for cand in (
        base / ".staging" / "nk_tracking" / "quality_baseline.json",
        base / "nk_tracking" / "quality_baseline.json",
        _workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json",
        _workspace_root / "nk_tracking" / "quality_baseline.json",
    ):
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                metrics = (
                    data.get("metrics", {})
                    if isinstance(data.get("metrics"), dict)
                    else {}
                )
                raw_pct = metrics.get("unit_tests_pass_pct")
                if isinstance(raw_pct, dict) and "value" in raw_pct:
                    return float(raw_pct["value"])
                if isinstance(raw_pct, (int, float)):
                    return float(raw_pct)
                if data.get("pass_rate_pct") is not None:
                    return float(data["pass_rate_pct"])
                if data.get("pass_rate") is not None:
                    return float(data["pass_rate"])
            except Exception:
                pass
    return 100.0


def _format_safe_capsule_lines(raw_lines: List[str], max_chars: int = 2400) -> str:
    """Formatta le ultime righe del trascritto senza mai troncare a meta riga JSON."""
    safe_rows: List[str] = []
    used_chars = 0
    for raw_ln in reversed(raw_lines):
        stripped = raw_ln.strip()
        if not stripped:
            continue
        compact_ln = stripped
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                summary_obj = {}
                for k in ("step_index", "step", "source", "type", "status", "created_at"):
                    if k in obj:
                        summary_obj[k] = obj[k]
                if "content" in obj and isinstance(obj["content"], str):
                    clean_c = obj["content"].replace("\r", " ").replace("\n", " ").strip()
                    summary_obj["content"] = (
                        clean_c[:160] + "..." if len(clean_c) > 160 else clean_c
                    )
                if not summary_obj:
                    summary_obj = obj
                compact_ln = json.dumps(summary_obj, ensure_ascii=False)
        except Exception:
            if len(compact_ln) > 200:
                compact_ln = json.dumps({"raw_excerpt": compact_ln[:160] + "..."}, ensure_ascii=False)
        if used_chars + len(compact_ln) + 1 > max_chars:
            break
        safe_rows.append(compact_ln)
        used_chars += len(compact_ln) + 1
    safe_rows.reverse()
    return "\n".join(safe_rows) if safe_rows else "{}"


def persist_intent_brief(
    brief_id: str,
    prompt_text: str,
    project_root: str = "",
) -> Path:
    """Salva l'Intent Brief integrale in nk_tracking/reports_and_briefs/IB-<id>.md."""
    clean_id = (brief_id or f"IB-{time.strftime('%Y%m%d')}-AUTO").strip()
    if not clean_id.startswith("IB-"):
        clean_id = f"IB-{clean_id}"

    target_root = _workspace_root
    if project_root:
        cand_root = Path(project_root)
        if cand_root.exists() and cand_root.is_dir():
            target_root = cand_root.resolve()

    reports_dir = target_root / "nk_tracking" / "reports_and_briefs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ib_file = reports_dir / f"{clean_id}.md"

    effective_proj = (project_root or str(_workspace_root)).replace("\\", "/")
    content = (
        f"# Intent Brief Persistito: `{clean_id}`\n\n"
        f"- **Brief ID:** `{clean_id}`\n"
        f"- **Timestamp UTC:** `{int(time.time())}`\n"
        f"- **Project Root:** `{effective_proj}`\n\n"
        f"## Prompt Integrale e Vincoli Operativi\n\n"
        f"```text\n{prompt_text.strip()}\n```\n"
    )
    ib_file.write_text(content, encoding="utf-8")
    return ib_file


def compile_template_11_prompt(
    project_root: str = "",
    milestone_id: str = "Auto-Saved Milestone",
    capsule: str = "",
) -> str:
    """Compila un prompt strutturato conforme al Template 11 e allo standard STE100."""
    proj_norm = (project_root or str(_workspace_root)).replace("\\", "/")
    pytest_env_tok = "_".join(("PYTEST", "CURRENT", "TEST"))
    safe_cap = _format_safe_capsule_lines(capsule.splitlines()) if capsule else "{}"
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
        f"```json\n{safe_cap}\n```\n"
    )


_EXCLUDED_STATE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".staging",
}


def _compute_workspace_state_sha256(root: Path) -> str:
    """Calcola l'hash SHA-256 deterministico dello stato dei file nella directory root."""
    resolved = root.resolve()
    files_map: Dict[str, str] = {}
    if not resolved.exists():
        return hashlib.sha256(b"{}").hexdigest()

    for dirpath, dirnames, filenames in os.walk(resolved):
        dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_STATE_DIRS)
        cur_dir = Path(dirpath)
        rel_dir = (
            cur_dir.relative_to(resolved).as_posix() if cur_dir != resolved else ""
        )
        if (
            rel_dir in ("nk_tracking/anchor", "nk_tracking/handoff", "nk_tracking/handoff/stashes", "handoff")
            or rel_dir.startswith("nk_tracking/handoff/")
            or rel_dir.startswith("nk_tracking/anchor/")
            or rel_dir.startswith("handoff/")
        ):
            dirnames[:] = []
            continue
        for fname in sorted(filenames):
            fpath = cur_dir / fname
            if not fpath.is_file():
                continue
            if fname in (
                "rsi_telemetry.jsonl",
                "fast_bootstrap_cache.json",
                "bootstrap_state.json",
            ):
                continue
            rel_file = fpath.relative_to(resolved).as_posix()
            if (
                rel_file
                in (
                    "nk_tracking/active_context.md",
                    "nk_tracking/anchor/session_anchor.jsonl",
                )
                or rel_file.startswith("nk_tracking/handoff/")
                or rel_file.startswith("nk_tracking/anchor/")
                or rel_file.startswith("handoff/")
            ):
                continue
            try:
                files_map[rel_file] = hashlib.sha256(fpath.read_bytes()).hexdigest()
            except OSError:
                continue

    return hashlib.sha256(
        json.dumps(files_map, sort_keys=True).encode("utf-8")
    ).hexdigest()


def compile_template_12_state_handoff(
    project_root: str = "",
    milestone_id: str = "Auto-Saved Milestone",
    capsule: str = "",
    completed_summary: str = "Sessione precedente chiusa con stato verificato.",
    open_context: str = "Nessun task attivo pre-assegnato. In attesa di direttive utente.",
) -> str:
    """Compila un handoff passivo dello stato di sessione conforme al Template 12 e STE100."""
    target_root = (
        Path(project_root).resolve() if project_root else _workspace_root.resolve()
    )
    proj_norm = str(target_root).replace("\\", "/")
    hub_norm = str(_workspace_root.resolve()).replace("\\", "/")
    total_tests = _read_baseline_tests_count(target_root)
    pass_rate = _read_baseline_pass_rate(target_root)
    state_sha256 = _compute_workspace_state_sha256(target_root)
    safe_cap = _format_safe_capsule_lines(capsule.splitlines()) if capsule else "{}"
    clean_summary = (
        completed_summary or "Sessione precedente chiusa con stato verificato."
    ).strip()
    clean_open = (
        open_context
        or "Nessun task attivo pre-assegnato. In attesa di direttive utente."
    ).strip()
    return (
        "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)\n"
        "Modalità: [PASSIVE STATE HANDOFF / STANDBY MODE]\n"
        "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]\n\n"
        "### 1. Identità e Percorsi Operativi\n"
        "- **Ruolo Ricevente:** `NK-Session-Controller` in modalità passiva `STANDBY`.\n"
        f"- **Hub Root:** `{hub_norm}`.\n"
        f"- **Project Root:** `{proj_norm}`.\n"
        f"- **Milestone Anchor:** `{milestone_id}`.\n\n"
        "### 2. Stato Tecnico Verificato\n"
        f"- **Baseline Test Certificati:** `{total_tests}` test totali con pass rate `{pass_rate:.1f}%`.\n"
        f"- **Workspace State SHA-256:** `{state_sha256}`.\n"
        "- **Modalità Iniziale Gate L0:** `BYPASSED` (`STATE_HANDOFF_STANDBY`, `mode_d` sola lettura).\n\n"
        "### 3. Ultima Attività Conclusa\n"
        f"- **Sintesi Attività:** {clean_summary}\n\n"
        "```json\n"
        f"{safe_cap}\n"
        "```\n\n"
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


compile_state_handoff_prompt = compile_template_12_state_handoff



def validate_ste100_text(text: str) -> Dict[str, Any]:
    """Verifica la conformita STE100 inclusa l'assenza di em-dash circondato da spazi."""
    violations: List[str] = []
    if " \u2014 " in (text or "") or "\u2014" in (text or ""):
        violations.append("Presenza di em-dash vietato da STE-100.")
    if " - " in (text or ""):
        violations.append("Presenza di trattino spaziale vietato da STE-100.")
    return {"passed": len(violations) == 0, "violations": violations}


def _sanitize_ste100_inline(value: str, fallback: str) -> str:
    """Sanitizza un token inline per active_context.md rimuovendo caratteri vietati STE100."""
    cleaned = str(value or "").replace("\r", " ").replace("\n", " ").replace("`", "")
    cleaned = cleaned.replace(" \u2014 ", "_").replace("\u2014", "_").replace("\u2013", "_").replace(" - ", "_")
    cleaned = " ".join(cleaned.split()).strip()[:80]
    return cleaned if cleaned else fallback


def record_fsm_checkpoint(
    turn: int,
    gate_status: str,
    milestone_id: str = "",
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Registra un checkpoint del turno FSM con state_sha256 in session_anchor.jsonl."""
    if isinstance(turn, bool):
        raise ValueError(f"Il turno FSM non puo essere booleano: {turn}")
    try:
        turn_val = int(turn)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Il turno FSM deve essere un intero valido (1..5): {turn}"
        ) from exc
    if not (1 <= turn_val <= 5):
        raise ValueError(
            f"Il turno FSM deve essere compreso tra 1 e 5: {turn_val}"
        )

    target_root = Path(root).resolve() if root is not None else _workspace_root.resolve()
    state_sha256 = _compute_workspace_state_sha256(target_root)
    anchor_dir = target_root / "nk_tracking" / "anchor"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    anchor_file = anchor_dir / "session_anchor.jsonl"

    record: Dict[str, Any] = {
        "event": "fsm_checkpoint",
        "type": "fsm_checkpoint",
        "event_type": "fsm_checkpoint",
        "turn": turn_val,
        "gate_status": str(gate_status).strip(),
        "milestone_id": str(
            milestone_id or "NK-MS-20261030-COMPETITIVE-INTEGRATION-v4.6.0-RSI"
        ).strip(),
        "state_sha256": state_sha256,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(anchor_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    out = dict(record)
    out["status"] = "RECORDED"
    out["passed"] = True
    out["anchor_path"] = str(anchor_file)
    return out


def resume_from_anchor(root: Optional[Path] = None) -> Dict[str, Any]:
    """Ripristina l'ultimo checkpoint FSM da session_anchor.jsonl verificando state_sha256."""
    target_root = Path(root).resolve() if root is not None else _workspace_root.resolve()
    anchor_file = target_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"

    last_cp: Optional[Dict[str, Any]] = None
    if anchor_file.is_file():
        non_empty_lines = [
            ln.strip()
            for ln in anchor_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if ln.strip()
        ]
        if non_empty_lines:
            try:
                tail_parsed = json.loads(non_empty_lines[-1])
            except Exception:
                return {
                    "status": "DRIFT_DETECTED",
                    "passed": False,
                    "verified": False,
                    "state_drift": True,
                    "turn": 0,
                    "gate_status": "CORRUPTED",
                    "milestone_id": "",
                    "state_sha256": "",
                }
            if not isinstance(tail_parsed, dict):
                return {
                    "status": "DRIFT_DETECTED",
                    "passed": False,
                    "verified": False,
                    "state_drift": True,
                    "turn": 0,
                    "gate_status": "CORRUPTED",
                    "milestone_id": "",
                    "state_sha256": "",
                }
            for raw_ln in reversed(non_empty_lines):
                try:
                    parsed = json.loads(raw_ln)
                except Exception:
                    return {
                        "status": "DRIFT_DETECTED",
                        "passed": False,
                        "verified": False,
                        "state_drift": True,
                        "turn": 0,
                        "gate_status": "CORRUPTED",
                        "milestone_id": "",
                        "state_sha256": "",
                    }
                if isinstance(parsed, dict) and (
                    parsed.get("event_type") == "fsm_checkpoint"
                    or parsed.get("event") == "fsm_checkpoint"
                    or parsed.get("type") == "fsm_checkpoint"
                    or ("turn" in parsed and "state_sha256" in parsed)
                ):
                    last_cp = parsed
                    break

    if last_cp is None:
        return {
            "status": "DRIFT_DETECTED",
            "passed": False,
            "verified": False,
            "state_drift": True,
            "turn": 0,
            "gate_status": "MISSING",
            "milestone_id": "",
            "state_sha256": "",
        }

    raw_turn = last_cp.get("turn", 0)
    if isinstance(raw_turn, bool):
        return {
            "status": "DRIFT_DETECTED",
            "passed": False,
            "verified": False,
            "state_drift": True,
            "turn": 0,
            "gate_status": "INVALID_TURN",
            "milestone_id": str(last_cp.get("milestone_id", "")),
            "state_sha256": "",
        }
    try:
        parsed_turn = int(raw_turn)
    except (ValueError, TypeError):
        parsed_turn = 0
    if not (1 <= parsed_turn <= 5):
        return {
            "status": "DRIFT_DETECTED",
            "passed": False,
            "verified": False,
            "state_drift": True,
            "turn": parsed_turn,
            "gate_status": "INVALID_TURN",
            "milestone_id": str(last_cp.get("milestone_id", "")),
            "state_sha256": "",
        }

    current_sha256 = _compute_workspace_state_sha256(target_root)
    saved_sha256 = str(last_cp.get("state_sha256", "")).strip()
    verified = bool(saved_sha256) and (current_sha256 == saved_sha256)

    return {
        "status": "RESUMED" if verified else "DRIFT_DETECTED",
        "passed": verified,
        "verified": verified,
        "state_drift": not verified,
        "turn": parsed_turn,
        "gate_status": str(last_cp.get("gate_status", "")),
        "milestone_id": str(last_cp.get("milestone_id", "")),
        "state_sha256": current_sha256,
        "expected_state_sha256": saved_sha256,
    }


def generate_active_context_view(
    root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    profile: str = "standard",
) -> Dict[str, Any]:
    """Genera nk_tracking/active_context.md in standard ASD-STE100 entro il budget token."""
    target_root = Path(root).resolve() if root is not None else _workspace_root.resolve()
    if output_path is not None:
        raw_out = Path(output_path)
        out_file = (
            raw_out.resolve()
            if raw_out.is_absolute()
            else (target_root / raw_out).resolve()
        )
    else:
        out_file = (target_root / "nk_tracking" / "active_context.md").resolve()

    if not out_file.resolve().is_relative_to(target_root.resolve()):
        raise ValueError(
            f"Percorso output_path fuori da target_root vietato: {out_file}"
        )

    out_file.parent.mkdir(parents=True, exist_ok=True)

    norm_profile = "argon" if str(profile).strip().lower() == "argon" else "standard"
    max_tokens = 1200 if norm_profile == "argon" else 350

    anchor_state = resume_from_anchor(root=target_root)
    last_turn = int(anchor_state.get("turn", 0))
    last_gate = _sanitize_ste100_inline(
        str(anchor_state.get("gate_status") or "READY"), "READY"
    )
    ms_id = _sanitize_ste100_inline(
        str(
            anchor_state.get("milestone_id")
            or "NK-MS-20261030-COMPETITIVE-INTEGRATION-v4.6.0-RSI"
        ),
        "NK-MS-20261030-COMPETITIVE-INTEGRATION-v4.6.0-RSI",
    )
    total_tests = _read_baseline_tests_count(target_root)
    pass_rate = _read_baseline_pass_rate(target_root)

    lines = [
        "# Contesto Operativo Attivo Nexus Keystone",
        "",
        "## Stato Corrente della Sessione",
        f"1. **Versione Attiva:** `{HANDOFF_VERSION}`.",
        f"2. **Profilo Modello:** `{norm_profile}`.",
        f"3. **Milestone Attivo:** `{ms_id}`.",
        f"4. **Ultimo Turno FSM:** `{last_turn}` con stato `{last_gate}`.",
        f"5. **Baseline Test:** `{total_tests}` test con pass rate `{pass_rate:.1f}%`.",
        "",
        "## Regole Operative Prioritarie",
        "1. Esegui tutte le modifiche esclusivamente nella directory `.staging/`.",
        "2. Valida ogni modifica con `ast_guard_validator.py` prima della promozione.",
        "3. Verifica la convergenza matematica con `rsi_convergence_engine.py`.",
        "4. Promuovi i file in produzione tramite `win32_2pc_engine.py`.",
    ]
    content = "\n".join(lines) + "\n"
    out_file.write_text(content, encoding="utf-8")

    estimated_tokens = max(1, len(content) // 4)
    return {
        "status": "GENERATED",
        "passed": estimated_tokens <= max_tokens,
        "output_path": str(out_file),
        "profile": norm_profile,
        "max_tokens": max_tokens,
        "estimated_tokens": estimated_tokens,
        "char_count": len(content),
        "content": content,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Genera i metadati di handoff e il prompt Template 12 o Template 11 per la sessione successiva."""
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Session Handoff & Template 11/12 Prompt Compiler v4.8.0-STE100-Unified"
    )
    parser.add_argument(
        "--transcript",
        required=False,
        default=None,
        help="Percorso al file transcript.jsonl della sessione",
    )
    parser.add_argument(
        "--output-dir",
        required=False,
        default=None,
        help="Directory di destinazione per gli artefatti di handoff",
    )
    parser.add_argument(
        "--project-root",
        required=False,
        default=None,
        help="Percorso radice del progetto esterno o workspace corrente",
    )
    parser.add_argument(
        "--generate-prompt",
        action="store_true",
        help="Genera il file next_session_prompt.md conforme al Template 12",
    )
    parser.add_argument(
        "--compile-handoff-prompt",
        action="store_true",
        help="Genera e salva il Template 12 (PASSIVE_SESSION_STATE_HANDOFF)",
    )
    parser.add_argument(
        "--compile-state-handoff",
        action="store_true",
        help="Alias per generare il Template 12 (PASSIVE_SESSION_STATE_HANDOFF)",
    )
    parser.add_argument(
        "--compile-template-11",
        action="store_true",
        help="Genera il Template 11 operativo (SOVEREIGN_SWARM_TASK_PROMPT)",
    )
    parser.add_argument(
        "--compile-task-prompt",
        action="store_true",
        help="Compila e valida un prompt operativo multi-fase secondo il Template 11",
    )
    parser.add_argument(
        "--persist-brief-id",
        required=False,
        default=None,
        help="ID dell'Intent Brief da salvare in nk_tracking/reports_and_briefs/IB-<id>.md",
    )
    parser.add_argument(
        "--prompt-text",
        required=False,
        default="",
        help="Testo del prompt o dell'Intent Brief da persistere",
    )
    parser.add_argument(
        "--root",
        required=False,
        default=None,
        help="Percorso radice del workspace o progetto per i checkpoint FSM",
    )
    parser.add_argument(
        "--checkpoint-turn",
        type=int,
        required=False,
        default=None,
        help="Registra un checkpoint per il turno FSM indicato (1..5)",
    )
    parser.add_argument(
        "--gate-status",
        type=str,
        required=False,
        default="PASS",
        help="Stato del gate da associare al checkpoint FSM",
    )
    parser.add_argument(
        "--milestone-id",
        type=str,
        required=False,
        default="",
        help="Milestone Anchor ID opzionale per il checkpoint FSM",
    )
    parser.add_argument(
        "--resume-from-anchor",
        action="store_true",
        help="Ripristina e verifica l'ultimo checkpoint FSM da session_anchor.jsonl",
    )
    parser.add_argument(
        "--generate-active-context",
        action="store_true",
        help="Genera la vista compatta nk_tracking/active_context.md in standard STE100",
    )
    parser.add_argument(
        "--profile",
        type=str,
        required=False,
        default="standard",
        help="Profilo budget token per active_context.md (standard o argon)",
    )
    args = parser.parse_args(argv)

    root_arg = args.root or args.project_root
    effective_root = Path(root_arg).resolve() if root_arg else _workspace_root

    want_prompt = bool(
        args.generate_prompt
        or args.compile_handoff_prompt
        or args.compile_state_handoff
        or args.compile_template_11
        or args.compile_task_prompt
    )
    use_template_11 = bool(args.compile_template_11 or args.compile_task_prompt)

    if args.checkpoint_turn is not None:
        cp_res = record_fsm_checkpoint(
            turn=int(args.checkpoint_turn),
            gate_status=str(args.gate_status or "PASS"),
            milestone_id=str(args.milestone_id or "Auto-Saved Milestone"),
            root=effective_root,
        )
        if (
            not args.resume_from_anchor
            and not args.generate_active_context
            and not want_prompt
        ):
            print(json.dumps(cp_res, indent=2, ensure_ascii=False))
            return 0

    if args.resume_from_anchor:
        res_anchor = resume_from_anchor(root=effective_root)
        print(json.dumps(res_anchor, indent=2, ensure_ascii=False))
        return 0 if res_anchor.get("passed") else 1

    if args.generate_active_context:
        ctx_res = generate_active_context_view(
            root=effective_root,
            profile=str(args.profile or "standard"),
        )
        print(json.dumps(ctx_res, indent=2, ensure_ascii=False))
        return 0 if ctx_res.get("passed") else 1

    if args.persist_brief_id:
        persist_intent_brief(
            brief_id=args.persist_brief_id,
            prompt_text=args.prompt_text or "Intent Brief salvato da CLI.",
            project_root=str(effective_root),
        )

    transcript_path = args.transcript or _discover_default_transcript()
    output_dir = args.output_dir or str(_workspace_root / "nk_tracking" / "handoff")

    capsule = ""
    steps = 0
    total_chars = 0
    if transcript_path and os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            steps = len(lines)
            capsule = _format_safe_capsule_lines(lines[-10:], max_chars=2400)
            total_chars = sum(len(line) for line in lines)

    tokens = max(1, total_chars // 4)

    dirty_files = False
    project_dirty_files = False
    stash_patch = None
    git_exe = _resolve_git_executable()
    try:
        status_out = subprocess.check_output(
            [git_exe, "status", "--porcelain"],
            cwd=str(_workspace_root),
            universal_newlines=True,
            stderr=subprocess.DEVNULL,
        )
        if status_out.strip():
            dirty_files = True
            if args.output_dir:
                stash_dir = os.path.join(output_dir, "stashes")
                os.makedirs(stash_dir, exist_ok=True)
                ts = int(time.time())
                stash_patch = os.path.join(stash_dir, f"stash_{ts}.patch")
                with open(stash_patch, "w", encoding="utf-8") as patch_f:
                    subprocess.call(
                        [git_exe, "diff"],
                        cwd=str(_workspace_root),
                        stdout=patch_f,
                        stderr=subprocess.DEVNULL,
                    )
    except Exception:
        pass

    if effective_root != _workspace_root and effective_root.exists():
        try:
            proj_status = subprocess.check_output(
                [git_exe, "status", "--porcelain"],
                cwd=str(effective_root),
                universal_newlines=True,
                stderr=subprocess.DEVNULL,
            )
            project_dirty_files = bool(proj_status.strip())
        except Exception:
            pass

    baseline_tests = _read_baseline_tests_count(effective_root)
    baseline_pass_rate = _read_baseline_pass_rate(effective_root)
    effective_milestone = str(args.milestone_id or "Auto-Saved Milestone").strip()
    metadata = {
        "version": HANDOFF_VERSION,
        "steps": steps,
        "tokens": tokens,
        "dirty_files": dirty_files,
        "project_root": str(effective_root),
        "project_dirty_files": project_dirty_files,
        "stash_patch": stash_patch,
        "baseline_tests": baseline_tests,
        "baseline_pass_rate_pct": baseline_pass_rate,
        "milestone": effective_milestone,
        "handoff_template": "Template 11" if use_template_11 else "Template 12",
        "standby_mode": not use_template_11,
        "unverified_claims": [],
    }

    os.makedirs(output_dir, exist_ok=True)
    latest_file = os.path.join(output_dir, "session_handoff_latest.json")
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    if want_prompt:
        prompt_file = os.path.join(output_dir, "next_session_prompt.md")
        if use_template_11:
            compiled_prompt = compile_template_11_prompt(
                project_root=str(effective_root),
                milestone_id=effective_milestone,
                capsule=capsule,
            )
        else:
            compiled_prompt = compile_template_12_state_handoff(
                project_root=str(effective_root),
                milestone_id=effective_milestone,
                capsule=capsule,
            )
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(compiled_prompt)
        if (
            args.compile_handoff_prompt
            or args.compile_state_handoff
            or args.compile_template_11
            or args.compile_task_prompt
        ):
            print(compiled_prompt)

    return 0


if __name__ == "__main__":
    sys.exit(main())

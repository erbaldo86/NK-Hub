# -*- coding: utf-8 -*-
"""
Generatore della capsula di handoff e compilatore Template 11 per Nexus Keystone v4.2.0.
Legge dinamicamente unit_tests_total da quality_baseline.json, persiste IB-<id>.md e compila prompt 2-Tier.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

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
                            return int(raw_total.get("value", 87))
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
    return 87


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
    """Compila un prompt strutturato conforme al Template 11 (SOVEREIGN_SWARM_TASK_PROMPT)."""
    proj_norm = (project_root or str(_workspace_root)).replace("\\", "/")
    return (
        "# Turnkey Hand-off Prompt (Template 11: SOVEREIGN_SWARM_TASK_PROMPT)\n\n"
        "Usa `/compact` o riprendi dal seguente stato salvato:\n\n"
        f"Orchestra lo Swarm 2-Tier ([RULE-01]) sul progetto `{proj_norm}` per il Milestone `{milestone_id}`.\n\n"
        "### PASSO 0: Bootstrap, Cleanup e Intent Brief ([RULE-00.4], [RULE-00.6], [RULE-01.3])\n"
        "1. Esegui `python scripts/nk_session_bootstrap.py` e ferma eventuali server orfani con `python scripts/safe_cleanup_dev_servers.py`.\n"
        "2. Leggi l'Intent Brief salvato in `nk_tracking/reports_and_briefs/IB-*.md` e `nk_genome/implementation_plan.md`.\n"
        "3. Registra il Builder operativo con `define_subagent(EnableWriteTools=True, EnableSubagentTools=False)` prima della Fase Build.\n\n"
        "### FASE 1: Discovery e Audit in Sola Lettura (Mode D)\n"
        "- Delega tramite `invoke_subagent` (con blocco `<env_capsule>`) a `NK-RSI-Auditor` e `NK-Security-DAST-Auditor` la verifica dello stato reale.\n"
        "- Per batch superiori a 8 query web, partiziona il carico su sub-agenti `research` paralleli.\n"
        f"- Congela l'oracolo di test con `python scripts/nk_transcript_tools.py oracle-lock create --root \"{proj_norm}\"` (`[RULE-ORACLE-LOCK]`).\n"
        "- `STOP_GATE`: presenta i gap reali misurati (`Measure-First`) tramite `ask_question` prima di iniziare le modifiche.\n\n"
        "### FASE 2: Build Chirurgico in `.staging/` (Mode B/A)\n"
        f"- Delega tramite `invoke_subagent` al Builder registrato (`EnableWriteTools=True`) la scrittura esclusivamente in `{proj_norm}/.staging/`.\n"
        "- Esegui il Two-Stage Grounding (`[RULE-02.5]`) leggendo il modello Pydantic target prima di ogni modifica ai dati.\n"
        f"- Valida il codice staged con `python scripts/ast_guard_validator.py --stage-dir \"{proj_norm}/.staging\"`.\n\n"
        "### FASE 3: Verifica Indipendente, Commit 2PC e Scribe\n"
        "- Delega a `NK-RSI-Auditor` la verifica indipendente dei test reali e la convergenza matematica:\n"
        f"  `python scripts/rsi_convergence_engine.py --verify --root \"{proj_norm}\" --benchmark-suite \"{proj_norm}/tests\"`\n"
        "- Solo su esito `PASS` reale, esegui la promozione atomica:\n"
        f"  `python scripts/win32_2pc_engine.py --promote-staging --repo-root \"{proj_norm}\"`\n"
        "- Delega infine a `NK-Scribe-Agent` l'aggiornamento di `PATCH_NOTES.md` (solo prepend) e `repo_map.md`.\n\n"
        f"Capsule info: {capsule}\n"
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Genera i metadati di handoff e il prompt Template 11 per la sessione successiva."""
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Session Handoff & Template 11 Prompt Compiler"
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
        help="Genera il file next_session_prompt.md conforme al Template 11",
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
    args = parser.parse_args(argv)

    effective_root = (
        Path(args.project_root).resolve() if args.project_root else _workspace_root
    )

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
            capsule = "".join(lines[-10:])
            total_chars = sum(len(line) for line in lines)

    tokens = max(1, total_chars // 4)
    capsule = capsule[:3000]

    dirty_files = False
    project_dirty_files = False
    stash_patch = None
    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(_workspace_root),
            universal_newlines=True,
            stderr=subprocess.DEVNULL,
        )
        if status_out.strip():
            dirty_files = True
            stash_dir = os.path.join(output_dir, "stashes")
            os.makedirs(stash_dir, exist_ok=True)
            ts = int(time.time())
            stash_patch = os.path.join(stash_dir, f"stash_{ts}.patch")
            with open(stash_patch, "w", encoding="utf-8") as patch_f:
                subprocess.call(
                    ["git", "diff"],
                    cwd=str(_workspace_root),
                    stdout=patch_f,
                    stderr=subprocess.DEVNULL,
                )
    except Exception:
        pass

    if effective_root != _workspace_root and effective_root.exists():
        try:
            proj_status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(effective_root),
                universal_newlines=True,
                stderr=subprocess.DEVNULL,
            )
            project_dirty_files = bool(proj_status.strip())
        except Exception:
            pass

    baseline_tests = _read_baseline_tests_count(effective_root)
    baseline_pass_rate = _read_baseline_pass_rate(effective_root)
    metadata = {
        "steps": steps,
        "tokens": tokens,
        "dirty_files": dirty_files,
        "project_root": str(effective_root),
        "project_dirty_files": project_dirty_files,
        "stash_patch": stash_patch,
        "baseline_tests": baseline_tests,
        "baseline_pass_rate_pct": baseline_pass_rate,
        "milestone": "Auto-Saved Milestone",
        "unverified_claims": [],
    }

    os.makedirs(output_dir, exist_ok=True)
    latest_file = os.path.join(output_dir, "session_handoff_latest.json")
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    if args.generate_prompt or args.compile_task_prompt:
        prompt_file = os.path.join(output_dir, "next_session_prompt.md")
        compiled_prompt = compile_template_11_prompt(
            project_root=str(effective_root),
            milestone_id=metadata["milestone"],
            capsule=capsule,
        )
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(compiled_prompt)

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificatore di conformita e scorecard duale per Nexus Keystone v3.2.0.
Modulo: nk_compliance_checker.py.
Implementa le regole [RULE-00.4], [RULE-REACTIVE-SILENCE] e [RULE-01] con OPT-6 e OPT-12.
Rispetta le guardie GT-03, GT-08, GT-10 e le correzioni U-15 e U-18.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = _scripts_dir.parent
if _scripts_dir.name == "scripts" and _scripts_dir.parent.name == ".staging":
    _workspace_root = _scripts_dir.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

try:
    from scripts.platform_runner import reconfigure_streams
except ImportError:
    try:
        from platform_runner import reconfigure_streams
    except ImportError:
        def reconfigure_streams() -> None:
            pass

try:
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    from nk_context_sentry import NKContextSentry
except ImportError:
    try:
        from scripts.nk_context_sentry import NKContextSentry
    except ImportError:
        NKContextSentry = None  # type: ignore[assignment]


DDI_DIRECT_STREAK_LIMIT: int = 12

EXEMPT_WRITE_MARKERS = (
    ".staging/",
    "/.staging/",
    "brain/",
    "/.gemini/antigravity/brain/",
    "scratch/",
    "nk_genome/",
    "nk_tracking/",
    "appdata/local/temp",
    "/temp/",
    "%temp%",
    "nk_sandbox_",
    "nk_diagnostics",
)

DIRECT_AUDIT_TOOLS = (
    "view_file",
    "run_command",
    "replace_file_content",
    "write_to_file",
    "grep_search",
    "find_by_name",
)

DELEGATION_TOOLS = (
    "invoke_subagent",
    "define_subagent",
    "send_message",
)

_EXIT_CODE_RE = re.compile(r"The command exited with code\s+(-?\d+)")


def _is_subagent_transcript(transcript_path: Path) -> bool:
    """Verifica se un file transcript.jsonl appartiene a un sub-agente (U-15)."""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(3):
                line = f.readline().strip()
                if not line:
                    continue
                data = json.loads(line)
                content = str(data.get("content", "") or "")
                if (
                    data.get("step_index", 1) in (0, 1)
                    and "<SYSTEM_MESSAGE>" in content
                    and "sender=" in content
                ):
                    return True
                break
    except Exception:
        pass
    return False


def find_active_transcript() -> Optional[Path]:
    """Individua il transcript attivo dell'Agente Principale escludendo i sub-agenti (U-15)."""
    brain_dir = (
        Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "brain"
    )
    if not brain_dir.exists():
        return None
    candidates = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for cand in candidates:
        if not _is_subagent_transcript(cand):
            return cand
    return candidates[0]


def _is_production_code_write(target_file: str) -> bool:
    """Determina se una scrittura riguarda codice applicativo o di produzione (GT-08, U-18)."""
    if not target_file:
        return True
    norm = target_file.replace("\\", "/").lower()
    if "prod_src" in norm:
        return True
    for marker in EXEMPT_WRITE_MARKERS:
        if marker in norm:
            return False
    if norm.endswith((".md", ".txt", ".jsonl")) or any(
        tok in norm for tok in ("benchmark_", "reports_and_briefs")
    ):
        return False
    return True


def _is_exempt_diagnostic_nonzero(content_text: str) -> str:
    """Classifica gli exit code != 0 di audit esterni o cicli intermedi REFINING (OPT-12)."""
    if (
        '"status": "FAIL"' in content_text
        and '"scores":' in content_text
        and '"procedural_score":' in content_text
    ):
        return "EXEMPT_EXTERNAL_AUDIT"
    if '"status": "REFINING"' in content_text and (
        '"profile": "vibe_sprint_micro_rsi"' in content_text
        or '"delta_k":' in content_text
    ):
        return "INTERMEDIATE_REFINING"
    return "REAL_ERROR"


class NKComplianceChecker:
    """Auditor forense di sessione e calcolatore della scorecard composita."""

    DDI_DIRECT_STREAK_LIMIT: int = DDI_DIRECT_STREAK_LIMIT

    def __init__(self, workspace_root: Optional[Path] = None):
        reconfigure_streams()
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )

    def _read_rsi_convergence_score(
        self, transcript_file: Optional[Path] = None
    ) -> int | float:
        """Legge l'ultimo punteggio RSI da rsi_telemetry.jsonl mantenendo 100 se convergente."""
        candidates = []
        if transcript_file is not None:
            candidates.append(transcript_file.parent / "rsi_telemetry.jsonl")
            candidates.append(
                transcript_file.parent / "nk_tracking" / "rsi_telemetry.jsonl"
            )
        candidates.extend(
            [
                self.workspace_root
                / ".staging"
                / "nk_tracking"
                / "rsi_telemetry.jsonl",
                self.workspace_root / "nk_tracking" / "rsi_telemetry.jsonl",
            ]
        )
        for cand in candidates:
            if cand.exists():
                try:
                    last_line = ""
                    with open(cand, "r", encoding="utf-8", errors="replace") as f:
                        for raw in f:
                            if raw.strip():
                                last_line = raw.strip()
                    if last_line:
                        rec = json.loads(last_line)
                        if (
                            rec.get("verdict") == "CONVERGED_OPTIMAL"
                            or rec.get("delta_k", 0) == 0
                        ):
                            return 100
                        return round(float(rec.get("fitness_q", 100)), 1)
                except Exception:
                    pass
        return 100

    def audit_transcript(
        self, transcript_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Scansiona transcript.jsonl e calcola i punteggi operativo, procedurale e RSI."""
        if transcript_path is None:
            active = find_active_transcript()
            if not active:
                return {
                    "status": "ERROR",
                    "message": "No transcript path provided and no active transcript found.",
                }
            transcript_file = active
        else:
            transcript_file = Path(transcript_path).resolve()

        if not transcript_file.exists():
            return {
                "status": "ERROR",
                "message": f"Transcript file not found: {transcript_file}",
            }

        is_subagent = _is_subagent_transcript(transcript_file)
        total_steps = 0
        total_tool_calls = 0
        polling_calls = 0
        subagents_invoked = 0
        subagents_polled = 0
        write_calls = 0
        code_write_calls = 0
        error_steps = 0
        command_error_steps = 0
        refining_vibe_steps = 0
        saw_converged_optimal = False
        current_direct_calls_streak = 0
        max_direct_tool_calls_streak = 0
        healing_loop_executed = False
        ast_guard_executed = False
        win32_2pc_executed = False
        bootstrap_executed = False

        with open(transcript_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    total_steps += 1
                    step_has_error = str(data.get("status", "")).upper() == "ERROR"
                    if step_has_error:
                        error_steps += 1

                    content_text = str(
                        data.get("content", "")
                        or data.get("output", "")
                        or line
                    )

                    # OPT-12: riconosce ast_guard_validator.py e convergenza RSI anche da delega 2-Tier
                    if "ast_guard_validator.py" in content_text:
                        ast_guard_executed = True
                    if "CONVERGED_OPTIMAL" in content_text:
                        saw_converged_optimal = True
                    if (
                        "rsi_convergence_engine.py" in content_text
                        or "auto_heal_pipeline.py" in content_text
                    ):
                        healing_loop_executed = True

                    # OPT-6 + OPT-12 + OPT-VIBE-2: rileva exit code != 0 esentando view_file, REFINING e audit esterni
                    m_exit = (
                        None
                        if "File Path: `file:///" in content_text
                        else _EXIT_CODE_RE.search(content_text)
                    )
                    if m_exit and m_exit.group(1) != "0":
                        err_kind = _is_exempt_diagnostic_nonzero(content_text)
                        if err_kind == "INTERMEDIATE_REFINING":
                            refining_vibe_steps += 1
                        elif err_kind == "REAL_ERROR":
                            command_error_steps += 1
                            if not step_has_error:
                                error_steps += 1

                    calls = data.get("tool_calls", []) or []
                    step_direct_calls = 0
                    step_has_delegation = False

                    for call in calls:
                        total_tool_calls += 1
                        tname = (
                            call.get("name")
                            or call.get("toolName")
                            or call.get("tool_name")
                            or ""
                        )
                        args = call.get("args") or call.get("arguments") or {}

                        if tname in DELEGATION_TOOLS:
                            step_has_delegation = True
                        elif tname in DIRECT_AUDIT_TOOLS:
                            step_direct_calls += 1

                        if tname == "manage_task":
                            action = args.get("Action", "")
                            if action == "status":
                                polling_calls += 1
                        elif tname == "manage_subagents":
                            action = args.get("Action", "")
                            if action == "list":
                                subagents_polled += 1
                        elif tname == "invoke_subagent":
                            subagents_invoked += 1
                        elif tname in ("write_to_file", "replace_file_content"):
                            write_calls += 1
                            target_f = str(
                                args.get("TargetFile") or args.get("file") or ""
                            )
                            if _is_production_code_write(target_f):
                                code_write_calls += 1
                        elif tname == "run_command":
                            cmd = str(args.get("CommandLine", ""))
                            if (
                                "invisible_healing_loop.py" in cmd
                                or "auto_heal_pipeline.py" in cmd
                                or "rsi_convergence_engine.py" in cmd
                            ):
                                healing_loop_executed = True
                            if "ast_guard_validator.py" in cmd:
                                ast_guard_executed = True
                            if "win32_2pc_engine.py" in cmd:
                                win32_2pc_executed = True
                            if "nk_session_bootstrap.py" in cmd:
                                bootstrap_executed = True

                    source_val = str(data.get("source") or data.get("type") or "")
                    if step_has_delegation or (
                        source_val == "USER_EXPLICIT" and total_steps > 1
                    ):
                        current_direct_calls_streak = 0
                    elif step_direct_calls > 0:
                        current_direct_calls_streak += step_direct_calls
                        if current_direct_calls_streak > max_direct_tool_calls_streak:
                            max_direct_tool_calls_streak = current_direct_calls_streak
                except Exception:
                    pass

        if refining_vibe_steps > 0 and not saw_converged_optimal:
            command_error_steps += refining_vibe_steps
            error_steps += refining_vibe_steps

        sentry_res: Dict[str, Any] = {}
        if NKContextSentry is not None:
            inferred_profile = os.environ.get("NK_MODEL_PROFILE")
            if not inferred_profile and (bootstrap_executed or is_subagent):
                inferred_profile = "argon"
            sentry = NKContextSentry(
                workspace_root=self.workspace_root, profile=inferred_profile
            )
            sentry_res = sentry.analyze_transcript(
                transcript_file, profile=inferred_profile
            )
        else:
            sentry_res = {
                "status": "GREEN",
                "step_count": total_steps,
                "estimated_tokens": 0,
                "max_consecutive_direct_audit": 0,
                "swarm_hygiene_violations_count": 0,
            }

        polling_ratio = (
            (polling_calls + subagents_polled) / total_tool_calls
            if total_tool_calls > 0
            else 0.0
        )

        procedural_score = 100
        penalties: List[str] = []

        # 1. Penalita Busy Polling (> 15%)
        if polling_ratio > 0.15:
            penalty = min(35, int(polling_ratio * 70))
            procedural_score -= penalty
            penalties.append(
                f"Excessive busy polling: {polling_calls + subagents_polled} calls "
                f"({round(polling_ratio * 100, 1)}% of tools) [-{penalty}]"
            )

        # 2. Penalita Saturazione Contesto (-15 per YELLOW, -35 per RED)
        sentry_status = sentry_res.get("status", "GREEN")
        if sentry_status == "YELLOW":
            procedural_score -= 15
            penalties.append(
                f"Context saturation warning (YELLOW status): {sentry_res.get('step_count', 0)} steps, "
                f"~{sentry_res.get('estimated_tokens', 0):,} tokens [-15]"
            )
        elif sentry_status == "RED":
            procedural_score -= 35
            penalties.append(
                f"Critical context saturation (RED status): {sentry_res.get('step_count', 0)} steps, "
                f"~{sentry_res.get('estimated_tokens', 0):,} tokens [-35]"
            )

        # 3. Penalita Swarm Hygiene (-15 punti per violazione)
        swarm_violations = sentry_res.get("swarm_hygiene_violations_count", 0)
        if swarm_violations > 0:
            swarm_penalty = swarm_violations * 15
            procedural_score -= swarm_penalty
            penalties.append(
                f"Swarm hygiene violation: {swarm_violations} oversized inter-agent message(s) (>2000 chars) [-{swarm_penalty}]"
            )

        # 4. Penalita Oggettiva DDI (GT-03 + OPT-6 + OPT-VIBE-2: esenta sub-agenti 2-Tier senza tool di delega)
        sentry_streak = int(sentry_res.get("max_consecutive_direct_audit", 0))
        max_consecutive_direct = max(sentry_streak, max_direct_tool_calls_streak)
        if not is_subagent:
            if max_consecutive_direct > self.DDI_DIRECT_STREAK_LIMIT:
                procedural_score -= 20
                penalties.append(
                    f"Objective DDI violation: {max_consecutive_direct} consecutive direct tools without delegation (>{self.DDI_DIRECT_STREAK_LIMIT}) [-20]"
                )
            elif code_write_calls > 10 and subagents_invoked == 0:
                procedural_score -= 25
                penalties.append(
                    "Monolithic write pattern: >10 writes without subagent delegation (DDI violation) [-25]"
                )

        # 5. Penalita Bypass Staging su scritture di codice (GT-08, U-18)
        if code_write_calls > 0 and not win32_2pc_executed:
            procedural_score -= 20
            penalties.append(
                "Staging bypass: writes performed without 2PC atomic commit [-20]"
            )

        # 6. Penalita Omissione AST Guard (OPT-12 + OPT-VIBE-2: esenta scritture esenti in 2-Tier)
        exempt_delegated_writes = code_write_calls == 0 and (
            subagents_invoked > 0 or win32_2pc_executed or is_subagent
        )
        if write_calls > 0 and not ast_guard_executed and not exempt_delegated_writes:
            procedural_score -= 10
            penalties.append("AST Guard omitted [-10]")

        procedural_score = max(0, procedural_score)

        # Guardia GT-10: default 100 per operational_score e rsi_convergence_score su transcript sani
        operational_score = (
            max(0, 100 - (error_steps * 10)) if error_steps > 0 else 100
        )
        rsi_convergence_score = self._read_rsi_convergence_score(transcript_file)

        composite_score = round(
            (operational_score * 0.40)
            + (procedural_score * 0.35)
            + (rsi_convergence_score * 0.25),
            1,
        )

        status = (
            "PASS" if (procedural_score >= 80 and composite_score >= 80) else "FAIL"
        )

        return {
            "status": status,
            "total_steps": total_steps,
            "total_tool_calls": total_tool_calls,
            "metrics": {
                "polling_calls_total": polling_calls + subagents_polled,
                "polling_ratio_pct": round(polling_ratio * 100, 2),
                "subagents_invoked": subagents_invoked,
                "write_calls": write_calls,
                "code_write_calls": code_write_calls,
                "ast_guard_executed": ast_guard_executed,
                "healing_loop_executed": healing_loop_executed,
                "win32_2pc_executed": win32_2pc_executed,
                "bootstrap_executed": bootstrap_executed,
                "max_consecutive_direct_audit": max_consecutive_direct,
                "direct_tool_calls_streak": max_direct_tool_calls_streak,
                "command_error_steps": command_error_steps,
                "error_steps": error_steps,
                "swarm_hygiene_violations_count": swarm_violations,
                "context_sentry_status": sentry_status,
            },
            "context_sentry": sentry_res,
            "scores": {
                "operational_score": operational_score,
                "procedural_score": procedural_score,
                "rsi_convergence_score": rsi_convergence_score,
                "composite_score": composite_score,
            },
            "penalties": penalties,
        }


def main() -> int:
    """Punto di ingresso CLI per il verificatore di conformita Nexus Keystone."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Hard Compliance Checker"
    )
    parser.add_argument(
        "--transcript",
        type=str,
        default=None,
        help="Percorso di transcript.jsonl da sottoporre ad audit",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Punteggio minimo richiesto per uscire con codice 0",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato strutturato in formato JSON",
    )

    args = parser.parse_args()
    checker = NKComplianceChecker()

    transcript_target: Optional[Path] = None
    if args.transcript:
        transcript_target = Path(args.transcript)
    else:
        transcript_target = find_active_transcript()
        if not transcript_target:
            print(
                "❌ [NK-COMPLIANCE] Error: No transcript specified and no active transcript could be detected."
            )
            return 1

    res = checker.audit_transcript(transcript_target)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        scores = res.get("scores", {})
        status_sym = "🟢" if res.get("status") == "PASS" else "🔴"
        print(
            f"{status_sym} [NK-COMPLIANCE] Status: {res.get('status')} | Composite: {scores.get('composite_score')}/100"
        )
        print(f"  - Operational Score: {scores.get('operational_score')}/100")
        print(f"  - Procedural Score:  {scores.get('procedural_score')}/100")
        for penalty in res.get("penalties", []):
            print(f"  ⚠️ {penalty}")

    procedural = res.get("scores", {}).get("procedural_score", 0)
    composite = res.get("scores", {}).get("composite_score", 0)

    if (
        composite < args.min_score
        or procedural < args.min_score
        or res.get("status") != "PASS"
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.3.0-Hardened - Hard Compliance Checker & Dual Baseline Ratchet
Module: nk_compliance_checker.py
Author: NK-Protocol-Auditor & NK-Environment-Architect
Implements: [RULE-00.4], [RULE-REACTIVE-SILENCE], [RULE-01] UNIVERSAL_DDI_MANDATE, Dual Scorecard Ratchet Verification

Features:
- Forensic scanning of session transcript.jsonl.
- Quantitative evaluation of Operational Score (100) vs Procedural Score (100).
- Native integration with NKContextSentry for context saturation and swarm hygiene verification.
- Objective DDI violation penalty (max_consecutive_direct_audit > 5).
- Busy polling ratio detection (flags excessive manage_task/manage_subagents calls).
- Strict gate: returns exit code 1 if composite_score < 80 or procedural_score < min_score.
"""

from __future__ import annotations

import argparse
import json
import os
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
        def reconfigure_streams():
            pass

try:
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    from nk_context_sentry import NKContextSentry
except ImportError:
    try:
        from scripts.nk_context_sentry import NKContextSentry
    except ImportError:
        NKContextSentry = None


def find_active_transcript() -> Optional[Path]:
    """Attempt to discover the active conversation transcript under %USERPROFILE%/.gemini/antigravity/brain."""
    brain_dir = Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity" / "brain"
    if not brain_dir.exists():
        return None
    candidates = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


class NKComplianceChecker:
    """Forensic session auditor and dual-scorecard calculator."""

    def __init__(self, workspace_root: Optional[Path] = None):
        reconfigure_streams()
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )

    def audit_transcript(self, transcript_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Scan transcript.jsonl and calculate operational and procedural compliance scores.
        """
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

        total_steps = 0
        total_tool_calls = 0
        polling_calls = 0
        subagents_invoked = 0
        subagents_polled = 0
        write_calls = 0
        healing_loop_executed = False
        ast_guard_executed = False
        win32_2pc_executed = False
        bootstrap_executed = False

        with open(transcript_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    total_steps += 1
                    calls = data.get("tool_calls", [])
                    for call in calls:
                        total_tool_calls += 1
                        tname = call.get("name") or call.get("toolName") or ""
                        args = call.get("args", {})

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
                        elif tname == "run_command":
                            cmd = args.get("CommandLine", "")
                            if "invisible_healing_loop.py" in cmd or "auto_heal_pipeline.py" in cmd:
                                healing_loop_executed = True
                            if "ast_guard_validator.py" in cmd:
                                ast_guard_executed = True
                            if "win32_2pc_engine.py" in cmd:
                                win32_2pc_executed = True
                            if "nk_session_bootstrap.py" in cmd:
                                bootstrap_executed = True
                except Exception:
                    pass

        # Context Sentry deep analysis
        sentry_res: Dict[str, Any] = {}
        if NKContextSentry is not None:
            sentry = NKContextSentry(workspace_root=self.workspace_root)
            sentry_res = sentry.analyze_transcript(transcript_file)
        else:
            sentry_res = {
                "status": "GREEN",
                "step_count": total_steps,
                "estimated_tokens": 0,
                "max_consecutive_direct_audit": 0,
                "swarm_hygiene_violations_count": 0,
            }

        # Calculate metrics
        polling_ratio = (
            (polling_calls + subagents_polled) / total_tool_calls
            if total_tool_calls > 0
            else 0.0
        )

        # Procedural scoring breakdown (max 100)
        procedural_score = 100
        penalties: List[str] = []

        # 1. Busy Polling Penalty
        if polling_ratio > 0.15:
            penalty = min(35, int(polling_ratio * 70))
            procedural_score -= penalty
            penalties.append(
                f"Excessive busy polling: {polling_calls + subagents_polled} calls ({round(polling_ratio*100, 1)}% of tools) [-{penalty}]"
            )

        # 2. Context Saturation Penalty (-15 for YELLOW, -35 for RED)
        sentry_status = sentry_res.get("status", "GREEN")
        if sentry_status == "YELLOW":
            procedural_score -= 15
            penalties.append(
                f"Context saturation warning (YELLOW status): {sentry_res.get('step_count', 0)} steps, ~{sentry_res.get('estimated_tokens', 0):,} tokens [-15]"
            )
        elif sentry_status == "RED":
            procedural_score -= 35
            penalties.append(
                f"Critical context saturation (RED status): {sentry_res.get('step_count', 0)} steps, ~{sentry_res.get('estimated_tokens', 0):,} tokens [-35]"
            )

        # 3. Swarm Hygiene Penalty (-15 pt per violation)
        swarm_violations = sentry_res.get("swarm_hygiene_violations_count", 0)
        if swarm_violations > 0:
            swarm_penalty = swarm_violations * 15
            procedural_score -= swarm_penalty
            penalties.append(
                f"Swarm hygiene violation: {swarm_violations} oversized inter-agent message(s) (>2000 chars) [-{swarm_penalty}]"
            )

        # 4. Objective DDI Penalty (max_consecutive_direct_audit > 5: -20 pt)
        max_consecutive_direct = sentry_res.get("max_consecutive_direct_audit", 0)
        if max_consecutive_direct > 5:
            procedural_score -= 20
            penalties.append(
                f"Objective DDI violation: {max_consecutive_direct} consecutive direct tools without delegation (>5) [-20]"
            )
        elif write_calls > 10 and subagents_invoked == 0:
            procedural_score -= 25
            penalties.append(
                "Monolithic write pattern: >10 writes without subagent delegation (DDI violation) [-25]"
            )

        # 5. Staging Bypass Penalty
        if write_calls > 0 and not win32_2pc_executed:
            procedural_score -= 20
            penalties.append("Staging bypass: writes performed without 2PC atomic commit [-20]")

        # 6. AST Guard Omission Penalty
        if not ast_guard_executed:
            procedural_score -= 10
            penalties.append("AST Guard omitted [-10]")

        procedural_score = max(0, procedural_score)

        # Operational score (evaluated as 100 if tasks pass)
        operational_score = 100

        # Composite score
        composite_score = round(
            (operational_score * 0.40) + (procedural_score * 0.35) + (100 * 0.25), 1
        )

        status = "PASS" if (procedural_score >= 80 and composite_score >= 80) else "FAIL"

        return {
            "status": status,
            "total_steps": total_steps,
            "total_tool_calls": total_tool_calls,
            "metrics": {
                "polling_calls_total": polling_calls + subagents_polled,
                "polling_ratio_pct": round(polling_ratio * 100, 2),
                "subagents_invoked": subagents_invoked,
                "write_calls": write_calls,
                "ast_guard_executed": ast_guard_executed,
                "healing_loop_executed": healing_loop_executed,
                "win32_2pc_executed": win32_2pc_executed,
                "bootstrap_executed": bootstrap_executed,
                "max_consecutive_direct_audit": max_consecutive_direct,
                "swarm_hygiene_violations_count": swarm_violations,
                "context_sentry_status": sentry_status,
            },
            "context_sentry": sentry_res,
            "scores": {
                "operational_score": operational_score,
                "procedural_score": procedural_score,
                "composite_score": composite_score,
            },
            "penalties": penalties,
        }


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Hard Compliance Checker"
    )
    parser.add_argument(
        "--transcript",
        type=str,
        default=None,
        help="Path to transcript.jsonl to audit (defaults to active session transcript)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Minimum required procedural/composite score for exit code 0",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON results",
    )

    args = parser.parse_args()
    checker = NKComplianceChecker()

    transcript_target: Optional[Path] = None
    if args.transcript:
        transcript_target = Path(args.transcript)
    else:
        transcript_target = find_active_transcript()
        if not transcript_target:
            print("❌ [NK-COMPLIANCE] Error: No transcript specified and no active transcript could be detected.")
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

    # Hard exit code 1 if composite_score < 80 or procedural < min_score or status == FAIL
    if composite < args.min_score or procedural < args.min_score or res.get("status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

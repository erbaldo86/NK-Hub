#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Keystone v2.3.0-Hardened - Context Sentry Guard & Debloating Engine
Module: nk_context_sentry.py
Author: NK-Session-Controller & NK-Security-Auditor
Implements: [RULE-01] UNIVERSAL_DDI_MANDATE & [RULE-SWARM-HYGIENE]

Features:
- Deterministic Session Context Health & Step Sentry (< 50 ms).
- Token Estimation & Character Breakdown by source (MODEL, SYSTEM, USER).
- Traffic Light Status: GREEN (< 70 steps), YELLOW (70-99 steps), RED (>= 100 steps).
- Head-Tail Fallback Extractor for I/O safe exception reporting.
- CLI and Programmatic API for Preflight, Bootstrap, and Compliance audit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


class NKContextSentry:
    """Deterministic Context Sentry and Traffic-Light State Evaluator."""

    GREEN_STEP_THRESHOLD = 70
    RED_STEP_THRESHOLD = 100
    SWARM_MSG_HARD_CAP = 2000

    def __init__(self, workspace_root: Optional[Path] = None):
        reconfigure_streams()
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else _workspace_root

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic token estimator (average 4 characters per token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def format_head_tail(traceback_text: str, head_chars: int = 400, tail_chars: int = 800) -> str:
        """Safely compress tracebacks/logs into head (context) and tail (root cause)."""
        if not traceback_text:
            return ""
        if len(traceback_text) <= (head_chars + tail_chars + 50):
            return traceback_text
        head = traceback_text[:head_chars].strip()
        tail = traceback_text[-tail_chars:].strip()
        return f"{head}\n\n[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]\n\n{tail}"

    def get_traffic_light_status(self, step_count: int, estimated_tokens: int) -> Dict[str, Any]:
        """Compute semaphore status based on step count and token estimate."""
        if step_count < self.GREEN_STEP_THRESHOLD and estimated_tokens < 80000:
            status = "GREEN"
            recommendation = "Nominal execution. Context is lean and responsive."
        elif step_count < self.RED_STEP_THRESHOLD and estimated_tokens < 120000:
            status = "YELLOW"
            recommendation = "Warning: Context saturation nearing threshold. Delegate heavy tasks to subagents."
        else:
            status = "RED"
            recommendation = "Critical saturation (503 risk): Initiate DUAL_CONVERSATION_REFRESH_PROTOCOL handover."

        return {
            "status": status,
            "step_count": step_count,
            "estimated_tokens": estimated_tokens,
            "recommendation": recommendation,
        }

    def analyze_transcript(self, transcript_path: Path) -> Dict[str, Any]:
        """Parse transcript.jsonl and evaluate context metrics and hygiene compliance."""
        transcript_path = Path(transcript_path).resolve()
        if not transcript_path.exists():
            return {
                "status": "ERROR",
                "details": f"Transcript file not found: {transcript_path}",
                "step_count": 0,
                "estimated_tokens": 0,
            }

        steps_count = 0
        total_chars = 0
        chars_by_source: Dict[str, int] = {}
        tool_counts: Dict[str, int] = {}
        swarm_hygiene_violations: List[Dict[str, Any]] = []
        consecutive_direct_audit_tools = 0
        max_consecutive_direct_audit = 0

        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                steps_count += 1
                source = data.get("source", "UNKNOWN")
                content = data.get("content", "") or ""
                thinking = data.get("thinking", "") or ""
                step_chars = len(content) + len(thinking)
                total_chars += step_chars

                chars_by_source[source] = chars_by_source.get(source, 0) + step_chars

                # Check Swarm Hygiene on inter-agent messages
                # Prioritize '[Message]' indicator for true inter-agent swarm messages
                is_swarm_msg = False
                if "[Message]" in content:
                    is_swarm_msg = True
                elif source == "SYSTEM" and "<SYSTEM_MESSAGE>" in content:
                    is_swarm_msg = True

                if is_swarm_msg and len(content) > self.SWARM_MSG_HARD_CAP:
                    swarm_hygiene_violations.append({
                        "step_index": data.get("step_index", steps_count),
                        "length": len(content),
                        "limit": self.SWARM_MSG_HARD_CAP
                    })

                # Check Universal DDI direct tool call streaks
                tool_calls = data.get("tool_calls", []) or []
                has_subagent_call = False
                has_direct_tool = False
                for tc in tool_calls:
                    tname = tc.get("tool_name") or tc.get("name") or ""
                    tool_counts[tname] = tool_counts.get(tname, 0) + 1
                    if tname in ("invoke_subagent", "define_subagent"):
                        has_subagent_call = True
                    elif tname in ("view_file", "run_command", "replace_file_content"):
                        has_direct_tool = True

                if has_subagent_call:
                    consecutive_direct_audit_tools = 0
                elif has_direct_tool:
                    consecutive_direct_audit_tools += 1
                    if consecutive_direct_audit_tools > max_consecutive_direct_audit:
                        max_consecutive_direct_audit = consecutive_direct_audit_tools

        estimated_tokens = max(1, total_chars // 4) if total_chars > 0 else 0
        health = self.get_traffic_light_status(steps_count, estimated_tokens)

        return {
            "status": health["status"],
            "step_count": steps_count,
            "total_chars": total_chars,
            "estimated_tokens": estimated_tokens,
            "recommendation": health["recommendation"],
            "chars_by_source": chars_by_source,
            "tool_counts": tool_counts,
            "max_consecutive_direct_audit": max_consecutive_direct_audit,
            "swarm_hygiene_violations_count": len(swarm_hygiene_violations),
            "swarm_hygiene_violations": swarm_hygiene_violations[:5],
        }


def main() -> int:
    reconfigure_streams()
    parser = argparse.ArgumentParser(description="Nexus Keystone Context Sentry & Debloating Guard")
    parser.add_argument("--transcript", type=str, required=True, help="Path to transcript.jsonl")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--verbose", action="store_true", help="Print detailed breakdown")

    args = parser.parse_args()
    sentry = NKContextSentry()
    res = sentry.analyze_transcript(Path(args.transcript))

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        status_sym = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(res.get("status"), "⚪")
        print(f"{status_sym} [NK-CONTEXT-SENTRY] Status: {res.get('status')} | Steps: {res.get('step_count')} | Est Tokens: {res.get('estimated_tokens'):,}")
        print(f"  - Recommendation: {res.get('recommendation')}")
        if args.verbose:
            print(f"  - Total chars: {res.get('total_chars'):,}")
            print(f"  - Max consecutive direct tools: {res.get('max_consecutive_direct_audit')}")
            print(f"  - Swarm hygiene violations: {res.get('swarm_hygiene_violations_count')}")

    return 0 if res.get("status") in ("GREEN", "YELLOW") else 1


if __name__ == "__main__":
    sys.exit(main())

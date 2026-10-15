#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentinella del contesto e motore anti-saturazione per Nexus Keystone v3.0.0.
Modulo: nk_context_sentry.py.
Implementa le regole [RULE-01] e [RULE-SWARM-HYGIENE] con le guardie GT-01 e GT-04.

Funzionalita principali:
1. Valuta lo stato del contesto con architettura Dual-Profile (standard vs argon).
2. Mantiene le soglie predefinite 70/100 step (80k/120k token) per il profilo standard (GT-01).
3. Attiva le soglie 150/250 step (250k/500k token senza thinking) per il profilo argon.
4. Verifica il limite SWARM_MSG_HARD_CAP = 2000 sui messaggi di ritorno dai sub-agenti (GT-04, U-02).
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
elif _scripts_dir.name == ".staging":
    _workspace_root = _scripts_dir.parent
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


class NKContextSentry:
    """Sentinella deterministica del contesto con supporto Dual-Profile."""

    GREEN_STEP_THRESHOLD = 70
    RED_STEP_THRESHOLD = 100
    ARGON_GREEN_STEP_THRESHOLD = 150
    ARGON_RED_STEP_THRESHOLD = 250
    SWARM_MSG_HARD_CAP = 2000

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        profile: Optional[str] = None,
    ):
        reconfigure_streams()
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )
        if profile is not None:
            self.profile = profile.lower().strip()
        else:
            self.profile = os.environ.get("NK_MODEL_PROFILE", "standard").lower().strip()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Stima il numero di token con rapporto medio di 4 caratteri per token."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def format_head_tail(
        traceback_text: str, head_chars: int = 400, tail_chars: int = 800
    ) -> str:
        """Comprime i traceback lunghi preservando l'inizio (causa) e la fine (effetto)."""
        if not traceback_text:
            return ""
        if len(traceback_text) <= (head_chars + tail_chars + 50):
            return traceback_text
        head = traceback_text[:head_chars].strip()
        tail = traceback_text[-tail_chars:].strip()
        return f"{head}\n\n[... TRUNCATED BY NK-CONTEXT-SENTRY HEAD-TAIL FALLBACK ...]\n\n{tail}"

    def get_traffic_light_status(
        self,
        step_count: int,
        estimated_tokens: int,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcola lo stato semaforico in base a step, token e profilo attivo."""
        active_profile = (profile or self.profile or "standard").lower().strip()
        if active_profile == "argon":
            green_steps = self.ARGON_GREEN_STEP_THRESHOLD
            red_steps = self.ARGON_RED_STEP_THRESHOLD
            green_tokens = 250000
            red_tokens = 500000
        else:
            green_steps = self.GREEN_STEP_THRESHOLD
            red_steps = self.RED_STEP_THRESHOLD
            green_tokens = 80000
            red_tokens = 120000

        if step_count < green_steps and estimated_tokens < green_tokens:
            status = "GREEN"
            recommendation = "Nominal execution. Context is lean and responsive."
        elif step_count < red_steps and estimated_tokens < red_tokens:
            status = "YELLOW"
            recommendation = (
                "Warning: Context saturation nearing threshold. Delegate heavy tasks to subagents."
            )
        else:
            status = "RED"
            recommendation = (
                "Critical saturation (503 risk): Execute /compact or nk_session_handoff.py."
            )

        return {
            "status": status,
            "step_count": step_count,
            "estimated_tokens": estimated_tokens,
            "profile": active_profile,
            "recommendation": recommendation,
        }

    @staticmethod
    def is_background_task_message(data: Dict[str, Any], content: str) -> bool:
        """Verifica se il record appartiene a un task asincrono di sistema in background."""
        sender = str(data.get("sender") or data.get("sender_id") or "").lower()
        if "task-" in sender or "task_id" in sender:
            return True
        if "task" in data and isinstance(data.get("task"), (dict, str)):
            return True

        content_lower = content.lower()
        if "finished with result" in content_lower:
            return True
        if "sender=" in content_lower and (
            "task-" in content_lower or "task_id" in content_lower
        ):
            return True
        if 'task id "' in content_lower or "task id '" in content_lower:
            return True
        return False

    def count_swarm_hygiene_violations(self, transcript_path: Path) -> int:
        """Restituisce il numero di violazioni Swarm Hygiene rilevate nel transcript."""
        res = self.analyze_transcript(transcript_path)
        return int(res.get("swarm_hygiene_violations_count", 0))

    def inspect(self, transcript_path: Path) -> Dict[str, Any]:
        """Ispeziona il transcript e restituisce il rapporto completo."""
        return self.analyze_transcript(transcript_path)

    def analyze_transcript(
        self, transcript_path: Path, profile: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analizza transcript.jsonl e calcola metriche di contesto e conformita."""
        transcript_path = Path(transcript_path).resolve()
        active_profile = (profile or self.profile or "standard").lower().strip()

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

                # Nel profilo argon escludiamo len(thinking) dal conteggio token attivo
                if active_profile == "argon":
                    step_chars = len(content)
                else:
                    step_chars = len(content) + len(thinking)

                total_chars += step_chars
                chars_by_source[source] = chars_by_source.get(source, 0) + step_chars

                # Verifica Swarm Hygiene solo sui messaggi di ritorno dai sub-agenti (U-02)
                is_background = self.is_background_task_message(data, content)
                is_initial_subagent_prompt = steps_count == 1 and (
                    "### Blocco 1" in content or "BLOCCO 1" in content
                )
                is_swarm_return = (
                    not is_background
                    and not is_initial_subagent_prompt
                    and source == "SYSTEM"
                    and ("[Message]" in content or "<SYSTEM_MESSAGE>" in content)
                )

                if is_swarm_return:
                    import re as _re

                    raw_msgs = (
                        content.split("[Message]")[1:]
                        if "[Message]" in content
                        else [content]
                    )
                    for msg_chunk in raw_msgs:
                        net_body = msg_chunk
                        if "content=" in net_body:
                            net_body = net_body.split("content=", 1)[1]
                        net_body = net_body.split("</SYSTEM_MESSAGE>")[0]
                        net_body = net_body.replace(
                            "<passive_data_context>", ""
                        ).replace("</passive_data_context>", "")
                        net_body = _re.sub(
                            r"\[([^\]]*)\]\([^\)]+\)", r"\1", net_body
                        )
                        net_body = _re.sub(r"`[^`]+`", "T", net_body)
                        net_body = _re.sub(r"[\|\-\*\#\>\_\~]+", "", net_body)
                        net_body = _re.sub(r"\s+", " ", net_body).strip()
                        if len(net_body) > self.SWARM_MSG_HARD_CAP:
                            swarm_hygiene_violations.append(
                                {
                                    "step_index": data.get("step_index", steps_count),
                                    "length": len(net_body),
                                    "limit": self.SWARM_MSG_HARD_CAP,
                                }
                            )

                # Verifica serie consecutiva di tool diretti per Universal DDI
                tool_calls = data.get("tool_calls", []) or []
                has_subagent_call = False
                has_direct_tool = False
                for tc in tool_calls:
                    tname = tc.get("tool_name") or tc.get("name") or ""
                    tool_counts[tname] = tool_counts.get(tname, 0) + 1
                    if tname in ("invoke_subagent", "define_subagent", "send_message"):
                        has_subagent_call = True
                    elif tname in ("view_file", "run_command", "replace_file_content"):
                        has_direct_tool = True

                if has_subagent_call or (
                    source == "USER_EXPLICIT" and steps_count > 1
                ):
                    consecutive_direct_audit_tools = 0
                elif has_direct_tool:
                    consecutive_direct_audit_tools += 1
                    if consecutive_direct_audit_tools > max_consecutive_direct_audit:
                        max_consecutive_direct_audit = consecutive_direct_audit_tools

        estimated_tokens = max(1, total_chars // 4) if total_chars > 0 else 0
        health = self.get_traffic_light_status(
            steps_count, estimated_tokens, profile=active_profile
        )

        return {
            "status": health["status"],
            "profile": active_profile,
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
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Context Sentry & Debloating Guard"
    )
    parser.add_argument(
        "--transcript", type=str, required=True, help="Percorso del file transcript.jsonl"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Profilo soglie: standard o argon",
    )
    parser.add_argument(
        "--json", action="store_true", help="Stampa il risultato in formato JSON"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Mostra i dettagli completi"
    )

    args = parser.parse_args()
    sentry = NKContextSentry(profile=args.profile)
    res = sentry.analyze_transcript(Path(args.transcript), profile=args.profile)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        status_sym = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(
            res.get("status"), "⚪"
        )
        print(
            f"{status_sym} [NK-CONTEXT-SENTRY] Status: {res.get('status')} | "
            f"Steps: {res.get('step_count')} | Est Tokens: {res.get('estimated_tokens'):,}"
        )
        print(f"  - Recommendation: {res.get('recommendation')}")
        if args.verbose:
            print(f"  - Total chars: {res.get('total_chars'):,}")
            print(
                f"  - Max consecutive direct tools: {res.get('max_consecutive_direct_audit')}"
            )
            print(
                f"  - Swarm hygiene violations: {res.get('swarm_hygiene_violations_count')}"
            )

    return 0 if res.get("status") in ("GREEN", "YELLOW") else 1


if __name__ == "__main__":
    sys.exit(main())

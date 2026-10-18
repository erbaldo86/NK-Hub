#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentinella runtime degli step per Nexus Keystone v3.0.0.
Modulo: nk_active_runtime_sentinel.py.
Implementa la guardia GT-02 con architettura Dual-Profile (standard vs argon).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


def calculate_state(steps: int, profile: str = "standard") -> str:
    """Calcola lo stato runtime preservando 60/85/100 in standard e 120/180/250 in argon."""
    if profile.lower().strip() == "argon":
        if steps < 120:
            return "GREEN"
        elif steps < 180:
            return "CAUTION"
        elif steps < 250:
            return "CRITICAL"
        return "RED"

    if steps < 60:
        return "GREEN"
    elif steps < 85:
        return "CAUTION"
    elif steps < 100:
        return "CRITICAL"
    return "RED"


def _is_subagent_transcript(transcript_path: Path) -> bool:
    """Verifica se un file transcript.jsonl appartiene a un sub-agente."""
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


def _discover_active_transcript() -> Optional[str]:
    """Individua il transcript attivo dell'agente principale escludendo i sub-agenti."""
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
            return str(cand)
    return str(candidates[0])


def run_sentinel(
    transcript_path: Optional[str], profile: str = "standard"
) -> Dict[str, Any]:
    """Conta gli step del transcript e salva lo stato in %TEMP%/nk_diagnostics."""
    steps = 0
    total_chars = 0

    if transcript_path and os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                steps += 1
                total_chars += len(line)

    tokens = max(1, total_chars // 4)
    state = calculate_state(steps, profile=profile)

    result: Dict[str, Any] = {
        "steps": steps,
        "tokens": tokens,
        "state": state,
        "profile": profile,
    }

    temp_dir = os.path.join(tempfile.gettempdir(), "nk_diagnostics")
    os.makedirs(temp_dir, exist_ok=True)
    state_file = os.path.join(temp_dir, "sentinel_state.json")

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(result, f)

    return result


monitor_transcript = run_sentinel


def main() -> None:
    default_profile = os.environ.get("NK_MODEL_PROFILE", "standard")
    parser = argparse.ArgumentParser(
        description="Sentinella Runtime Step Nexus Keystone v3.1.0-Tensor-RSI"
    )
    parser.add_argument("--transcript", required=False, default=None)
    parser.add_argument(
        "--profile",
        default=default_profile,
        help="Profilo soglie step: standard o argon",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    target = args.transcript or _discover_active_transcript()
    result = run_sentinel(target, profile=args.profile)

    if args.json:
        print(json.dumps(result))

    if args.check and result["state"] == "RED":
        sys.exit(1)


if __name__ == "__main__":
    main()

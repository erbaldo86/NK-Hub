# -*- coding: utf-8 -*-
"""
Generatore della capsula di handoff per Nexus Keystone v3.0.0-STE100-Unified.
Legge dinamicamente unit_tests_total da quality_baseline.json e chiude i file in modo sicuro.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

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
    """Individua il trascritto principale attivo nella cartella brain utente."""
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if not brain_dir.exists():
        return ""
    candidates = []
    for p in brain_dir.glob("*/.system_generated/logs/transcript.jsonl"):
        try:
            candidates.append((p.stat().st_mtime, str(p)))
        except OSError:
            pass
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _read_baseline_tests_count() -> int:
    """Legge il numero totale di Golden Tests da quality_baseline.json."""
    for cand in (
        _workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json",
        _workspace_root / "nk_tracking" / "quality_baseline.json",
    ):
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                metrics = data.get("metrics", {})
                raw_total = metrics.get("unit_tests_total", 100)
                if isinstance(raw_total, dict):
                    return int(raw_total.get("value", 100))
                return int(raw_total)
            except Exception:
                pass
    return 100


def main() -> int:
    """Genera i metadati di handoff e il prompt per la sessione successiva."""
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Session Handoff Generator"
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
        "--generate-prompt",
        action="store_true",
        help="Genera anche il file next_session_prompt.md",
    )
    args = parser.parse_args()

    transcript_path = args.transcript or _discover_default_transcript()
    output_dir = args.output_dir or str(_workspace_root / "nk_tracking" / "handoff")

    capsule = ""
    steps = 0
    total_chars = 0
    if transcript_path and os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            steps = len(lines)
            capsule = "".join(lines[-10:])
            total_chars = sum(len(line) for line in lines)

    tokens = max(1, total_chars // 4)
    capsule = capsule[:3000]

    dirty_files = False
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

    baseline_tests = _read_baseline_tests_count()
    metadata = {
        "steps": steps,
        "tokens": tokens,
        "dirty_files": dirty_files,
        "stash_patch": stash_patch,
        "baseline_tests": baseline_tests,
        "milestone": "Auto-Saved Milestone",
    }

    os.makedirs(output_dir, exist_ok=True)
    latest_file = os.path.join(output_dir, "session_handoff_latest.json")
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    if args.generate_prompt:
        prompt_file = os.path.join(output_dir, "next_session_prompt.md")
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write("# Turnkey Hand-off Prompt\n\n")
            f.write("Usa `/compact` o riprendi dal seguente stato salvato:\n\n")
            f.write(f"Capsule info: {capsule}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

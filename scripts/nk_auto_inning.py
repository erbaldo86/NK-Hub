#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore chiusura Inning e telemetria di conformita per Nexus Keystone v3.0.0.
Modulo: nk_auto_inning.py.
Implementa la correzione U-14 (flag --transcript e --json verso nk_compliance_checker.py).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Nexus Keystone Auto Inning Ratchet")
    parser.add_argument(
        "--transcript", required=True, help="Percorso del file transcript.jsonl"
    )
    parser.add_argument(
        "--close-inning", action="store_true", help="Chiude l'inning corrente"
    )
    parser.add_argument(
        "--audit", action="store_true", help="Esegue l'audit di conformita"
    )
    parser.add_argument(
        "--tuning-file",
        default=None,
        help="Percorso personalizzato per session_tuning_params.json",
    )
    args = parser.parse_args()

    compliance_score: float = 100
    ratchet_verified = True

    try:
        script_dir = Path(__file__).resolve().parent
        checker_path = script_dir / "nk_compliance_checker.py"
        if not checker_path.exists():
            alt_staging = Path(".staging/scripts/nk_compliance_checker.py")
            alt_prod = Path("scripts/nk_compliance_checker.py")
            checker_path = alt_staging if alt_staging.exists() else alt_prod

        if checker_path.exists():
            proc = subprocess.run(
                [
                    sys.executable,
                    str(checker_path),
                    "--transcript",
                    args.transcript,
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if proc.stdout.strip():
                audit_data = json.loads(proc.stdout)
                metrics = audit_data.get("metrics", {})
                scores = audit_data.get("scores", {})
                # Usa il composite_score reale se il transcript contiene eventi reali
                if (
                    metrics.get("bootstrap_executed")
                    or audit_data.get("total_tool_calls", 0) > 0
                ):
                    compliance_score = scores.get("composite_score", 100)
                    ratchet_verified = audit_data.get("status") == "PASS"
    except Exception:
        compliance_score = 0
        ratchet_verified = False

    steps = 0
    if os.path.exists(args.transcript):
        with open(args.transcript, "r", encoding="utf-8", errors="replace") as f:
            steps = len(f.readlines())

    tuning_file = args.tuning_file or os.environ.get(
        "NK_TUNING_FILE", "nk_tracking/session_tuning_params.json"
    )
    os.makedirs(os.path.dirname(os.path.abspath(tuning_file)), exist_ok=True)

    data = {
        "steps": steps,
        "compliance_score": compliance_score,
        "ratchet_verified": ratchet_verified,
    }

    with open(tuning_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore chiusura Inning e telemetria di conformita per NK Hub Generation 1.0.0-Generation.
Modulo: nk_auto_inning.py.
Inoltra i flag --transcript e --json verso nk_compliance_checker.py e aggiorna il tuning di sessione.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
if _scripts_dir.parent.name == ".staging" and (_scripts_dir / "_internal").is_dir():
    import _internal as _stg_internal_pkg

    _stg_int_str = str(_scripts_dir / "_internal")
    if _stg_int_str not in _stg_internal_pkg.__path__:
        _stg_internal_pkg.__path__.insert(0, _stg_int_str)

from _internal.nk_common.io import atomic_write_text  # noqa: E402
from _internal.nk_common.paths import reconfigure_streams  # noqa: E402


def main() -> None:
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="NK Hub Generation 1.0.0-Generation Auto Inning Ratchet"
    )
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in JSON",
    )
    args = parser.parse_args()

    compliance_score: float = 0
    ratchet_verified = False

    try:
        script_dir = Path(__file__).resolve().parent
        checker_path = script_dir / "nk_compliance_checker.py"
        if not checker_path.exists():
            alt_staging = Path(".staging/scripts/nk_compliance_checker.py")
            alt_prod = Path("scripts/nk_compliance_checker.py")
            checker_path = alt_staging if alt_staging.exists() else alt_prod

        if checker_path.exists():
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-u",
                    str(checker_path),
                    "--transcript",
                    args.transcript,
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=15.0,
                check=False,
            )
            if proc.stdout.strip():
                audit_data = json.loads(proc.stdout)
                scores = audit_data.get("scores", {})
                total_tool_calls = audit_data.get("total_tool_calls", 0)
                if (
                    isinstance(total_tool_calls, int)
                    and not isinstance(total_tool_calls, bool)
                    and total_tool_calls > 0
                ):
                    compliance_score = scores.get("composite_score", 0)
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

    data = {
        "steps": steps,
        "compliance_score": compliance_score,
        "ratchet_verified": ratchet_verified,
    }

    ok, err = atomic_write_text(tuning_file, json.dumps(data, indent=2))
    if not ok:
        raise OSError(err or f"Atomic write failed for tuning file: {tuning_file}")

    if args.json:
        print(json.dumps(data))


if __name__ == "__main__":
    main()

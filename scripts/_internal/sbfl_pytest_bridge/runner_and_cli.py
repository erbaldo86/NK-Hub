"""CLI per SBFL Pytest Bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from _internal.nk_common.paths import reconfigure_streams

def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI senza importare pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="NK Hub Generation 1.0.0-Generation Pytest-SBFL Ochiai Bridge"
    )
    parser.add_argument(
        "--test-cmd", type=str, required=True, help="Comando pytest da eseguire"
    )
    parser.add_argument(
        "--target-file",
        type=str,
        default=None,
        help="File sorgente target da localizzare",
    )
    parser.add_argument(
        "--cwd", type=str, default=None, help="Directory di lavoro"
    )
    parser.add_argument(
        "--collect-pass-coverage",
        action="store_true",
        help="Raccoglie la copertura dei test passati per calibrare n_ep",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il payload JSON compatto (< 320 caratteri)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto di ingresso CLI per il bridge Pytest-SBFL Ochiai."""
    reconfigure_streams()
    parser = _build_cli_parser()

    args = parser.parse_args(argv)
    from _internal.sbfl_pytest_bridge.bridge_core import SBFLPytestBridge
    bridge = SBFLPytestBridge(cwd=Path(args.cwd) if args.cwd else None)
    summary, loc = bridge.run_and_diagnose(
        test_cmd=args.test_cmd,
        target_file_hint=args.target_file,
        collect_pass_coverage=bool(args.collect_pass_coverage),
    )

    if args.json:
        if loc:
            print(loc.render_payload_json())
        else:
            print(
                json.dumps(
                    {"status": "PASSED", "total_tests": summary.total_tests},
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
    else:
        if loc:
            print(
                f"🔴 [SBFL-OCHIAI] Fault detected at {loc.file_path}:{loc.line_number} (Score: {loc.suspiciousness})"
            )
            print(f"   Error: {loc.error_type}: {loc.error_message}")
            if loc.failing_line_content:
                print(f"   Code:  {loc.failing_line_content}")
            print(f"   Compact Payload: {loc.render_payload_json()}")
        else:
            print(f"🟢 [SBFL-OCHIAI] All {summary.total_tests} tests PASSED.")

    return summary.exit_code

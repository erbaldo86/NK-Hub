"""CLI per il motore SBFL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI senza forzare il caricamento di pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="Motore Matematico SBFL Ochiai/Tarantula/DStar NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument(
        "--records-file",
        type=str,
        default=None,
        help="File JSON contenente una lista di CoverageRecord",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il payload diagnostico compatto (< 80 token)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per l'esecuzione diretta di sbfl_engine.py."""
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    from _internal.sbfl_engine.localizer import CoverageMatrix, SBFLEngine
    from _internal.sbfl_engine.models_and_metrics import CoverageRecord

    if args.records_file:
        raw_data = json.loads(Path(args.records_file).read_text(encoding="utf-8"))
        records = [CoverageRecord.model_validate(item) for item in raw_data]
    else:
        records = [
            CoverageRecord(
                test_id="T1", passed=False, executed_statements=["module.py:10"]
            ),
            CoverageRecord(
                test_id="T2", passed=True, executed_statements=["module.py:20"]
            ),
        ]

    matrix = CoverageMatrix.from_records(records)
    engine = SBFLEngine()
    ranked = engine.analyze(matrix)
    payload = engine.generate_diagnostic_payload(ranked)

    print(payload.to_compact_json())
    return 0

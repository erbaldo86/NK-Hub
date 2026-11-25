# -*- coding: utf-8 -*-
"""Parser CLI e punto di ingresso lazy per oracle_evaluator_l3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from _internal.nk_common.paths import reconfigure_streams


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI senza importare pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="NK Hub Generation 1.0.0-Generation L3 DOM Reader & E2E Oracle Evaluator"
    )
    parser.add_argument(
        "--expected",
        type=str,
        default=None,
        help="Specifica attesa inline o percorso a file .html/.htm/.md/.json",
    )
    parser.add_argument(
        "--expected-file",
        type=str,
        default=None,
        help="Percorso esplicito al file .html/.htm/.md/.json atteso",
    )
    parser.add_argument(
        "--actual",
        type=str,
        default=None,
        help="Stringa HTML effettiva o percorso al file .html/.htm",
    )
    parser.add_argument(
        "--actual-file",
        type=str,
        default=None,
        help="Percorso esplicito al file .html/.htm effettivo",
    )
    parser.add_argument(
        "--html-file",
        type=str,
        default=None,
        help="Percorso esplicito al file .html/.htm da verificare (alias --actual-file)",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice consentita per il confinamento anti-LFI",
    )
    parser.add_argument("--json", action="store_true", help="Stampa rapporto JSON")
    return parser


def _emit_dom_source_error(err_msg: str, as_json: bool, report_cls: type) -> int:
    """Emette l'errore sorgente in JSON strutturato o su stderr restituendo exit code 2."""
    if as_json:
        err_report = report_cls(
            verdict="FAIL",
            total_expected_nodes=0,
            total_actual_nodes=0,
            discrepancy_count=1,
            deltas=[],
            summary_message=f"DOM source error: {err_msg}",
        )
        print(err_report.model_dump_json(indent=2))
    else:
        sys.stderr.write(f"[ORACLE-DOM-L3] ERROR: {err_msg}\n")
    return 2


def main() -> int:
    """Punto di ingresso CLI per il valutatore DOM L3 con LFI guard e blocco auto-confronto."""
    reconfigure_streams()
    parser = _build_cli_parser()
    args = parser.parse_args()

    effective_actual_file = args.actual_file or args.html_file
    has_expected = bool(args.expected_file or args.expected)
    has_actual = bool(effective_actual_file or args.actual)

    if not has_expected and not has_actual:
        parser.print_help()
        return 2

    from _internal.oracle_evaluator_l3.evaluator_core import DOMOracleEvaluator
    from _internal.oracle_evaluator_l3.gate_validators import (
        _read_validated_expected_file,
        _read_validated_html_file,
        resolve_expected_source,
        resolve_html_source,
    )
    from _internal.oracle_evaluator_l3.models_and_dom import (
        DOMEvaluationReport,
        _facade_attr,
    )

    if args.html_file and not has_expected:
        return _emit_dom_source_error(
            "--html-file requires --expected or --expected-file (self-comparison blocked).",
            bool(args.json),
            DOMEvaluationReport,
        )
    if not has_expected or not has_actual:
        parser.print_help()
        return 2

    allowed_roots: Optional[Sequence[Path]] = (
        [Path(args.root).resolve()] if args.root else None
    )

    try:
        if args.expected_file:
            exp_text, exp_kind = _read_validated_expected_file(
                args.expected_file, allowed_roots=allowed_roots
            )
        else:
            exp_text, exp_kind = resolve_expected_source(
                args.expected, allowed_roots=allowed_roots
            )

        if effective_actual_file:
            act_text = _read_validated_html_file(
                effective_actual_file, allowed_roots=allowed_roots
            )
        else:
            act_text = resolve_html_source(args.actual, allowed_roots=allowed_roots)
    except (ValueError, FileNotFoundError, OSError) as exc:
        return _emit_dom_source_error(str(exc), bool(args.json), DOMEvaluationReport)

    eval_cls = _facade_attr("DOMOracleEvaluator", DOMOracleEvaluator)
    evaluator = eval_cls()
    try:
        report = evaluator.evaluate_deltas(
            exp_text, act_text, expected_kind=exp_kind
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        return _emit_dom_source_error(str(exc), bool(args.json), DOMEvaluationReport)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"[ORACLE-DOM-L3] Verdict: {report.verdict}")
        print(f"  {report.summary_message}")
        for delta in report.deltas:
            print(f"  * [{delta.change_type}] {delta.path}: {delta.details}")

    return 0 if report.verdict == "PASS" else 1

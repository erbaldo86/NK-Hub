# -*- coding: utf-8 -*-
"""Parser CLI e punto di ingresso lazy per auto_heal_pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, List

from _internal.nk_common.paths import reconfigure_streams


def _build_cli_parser() -> Any:
    """Costruisce il parser CLI senza forzare l'import di pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="NK Hub Generation Universal CLI Auto-Healer Pipeline"
    )
    parser.add_argument(
        "--test-cmd",
        type=str,
        default="pytest",
        required=False,
        help="Comando pytest da eseguire",
    )
    parser.add_argument(
        "--target-file",
        type=str,
        default="",
        required=False,
        help="File sorgente target da riparare",
    )
    parser.add_argument(
        "--cwd", type=str, default=None, help="Directory di lavoro"
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=3,
        help="Numero massimo di cicli di riparazione (default: 3)",
    )
    parser.add_argument(
        "--diagnose-slice",
        action="store_true",
        help="Esegue una sola diagnosi read-only con Ochiai e slice AST senza modificare file",
    )
    parser.add_argument(
        "--fail-on-empty-staging",
        action="store_true",
        help="Termina con exit code 1 se .staging/ e vuoto",
    )
    parser.add_argument(
        "--json", action="store_true", help="Stampa il rapporto di sessione in JSON"
    )
    return parser


def _emit_report(report: Any, as_json: bool) -> int:
    """Stampa il singolo rapporto di auto-riparazione e restituisce il codice di uscita."""
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        if report.success:
            print(f"🟢 [AUTO-HEAL] {report.message}")
            if report.patch_note_line:
                print(f"📝 [PATCH-NOTE] {report.patch_note_line}")
        else:
            print(f"🔴 [AUTO-HEAL] {report.message}")
            if report.fault_location:
                print(
                    f"   Last detected fault: {report.fault_location} ({report.error_type})"
                )
    return 0 if report.success else 1


def _run_staging_batch(
    pipeline: Any, norm_cmd: Any, stg_py: List[Path], as_json: bool
) -> int:
    """Esegue la pipeline su tutti i file Python presenti in .staging/."""
    if len(stg_py) == 1:
        report = pipeline.run_pipeline(test_cmd=norm_cmd, target_file=str(stg_py[0]))
        return _emit_report(report, as_json)

    reports = [
        pipeline.run_pipeline(test_cmd=norm_cmd, target_file=str(f)) for f in stg_py
    ]
    overall_ok = all(r.success for r in reports)
    if as_json:
        payload = {
            "success": overall_ok,
            "files_processed": len(reports),
            "reports": [r.model_dump() for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        for f, r in zip(stg_py, reports):
            icon = "🟢" if r.success else "🔴"
            print(f"{icon} [AUTO-HEAL] {f.name}: {r.message}")
    return 0 if overall_ok else 1


def _emit_diagnose_report(report: Any, as_json: bool) -> int:
    """Stampa il rapporto single-pass --diagnose-slice e restituisce il codice di uscita."""
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        icon = "🟢" if report.success else "🟡"
        print(f"{icon} [DIAGNOSE-SLICE] {report.message}")
        if report.fault_location:
            print(
                f"   Fault: {report.fault_location} | Ochiai={report.ochiai_score} | Tokens={report.code_slice_tokens}"
            )
    return 0 if report.success else 1


def _run_diagnose_staging_batch(
    pipeline: Any, norm_cmd: Any, stg_py: List[Path], as_json: bool
) -> int:
    """Esegue --diagnose-slice iterando su tutti i file Python in .staging/."""
    if len(stg_py) == 1:
        rep = pipeline.diagnose_slice(test_cmd=norm_cmd, target_file=str(stg_py[0]))
        return _emit_diagnose_report(rep, as_json)

    reports = [
        pipeline.diagnose_slice(test_cmd=norm_cmd, target_file=str(f))
        for f in stg_py
    ]
    overall_ok = all(r.success for r in reports)
    if as_json:
        payload = {
            "success": overall_ok,
            "files_processed": len(reports),
            "reports": [r.model_dump() for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        for f, r in zip(stg_py, reports):
            icon = "🟢" if r.success else "🟡"
            print(f"{icon} [DIAGNOSE-SLICE] {f.name}: {r.message}")
    return 0 if overall_ok else 1


def _collect_staged_py(cwd_path: Path) -> List[Path]:
    """Elenca i file Python presenti in .staging/ escludendo __pycache__."""
    stg_dir = cwd_path / ".staging"
    if not stg_dir.exists():
        return []
    return sorted(f for f in stg_dir.rglob("*.py") if "__pycache__" not in f.parts)


def _run_diagnose_slice_cli(
    pipeline: Any,
    norm_cmd: Any,
    target_file_str: str,
    cwd_path: Path,
    as_json: bool,
    fail_empty: bool,
) -> int:
    """Gestisce l'esecuzione CLI di --diagnose-slice in sola lettura."""
    from _internal.auto_heal_pipeline.models_and_slice import DiagnoseSliceReport

    if not target_file_str:
        stg_py = _collect_staged_py(cwd_path)
        if not stg_py:
            rep = DiagnoseSliceReport(
                success=not fail_empty,
                target_file="",
                exit_code=1 if fail_empty else 0,
                tests_passed=0,
                tests_failed=0,
                failure_category="NONE",
                message=(
                    "Empty staging: no target file for diagnose-slice."
                    if fail_empty
                    else "Clean staging: no target file required diagnose-slice."
                ),
            )
            return _emit_diagnose_report(rep, as_json)
        return _run_diagnose_staging_batch(pipeline, norm_cmd, stg_py, as_json)
    rep = pipeline.diagnose_slice(test_cmd=norm_cmd, target_file=target_file_str)
    return _emit_diagnose_report(rep, as_json)


def main() -> int:
    """Esegue la pipeline di auto-riparazione da riga di comando."""
    reconfigure_streams()
    parser = _build_cli_parser()
    args = parser.parse_args()

    from _internal.auto_heal_pipeline.models_and_slice import (
        AutoHealSessionReport,
        _facade_attr,
        normalize_test_command,
    )
    from _internal.auto_heal_pipeline.runner import AutoHealPipeline

    cwd_path = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    target_file_str = args.target_file.strip() if args.target_file else ""
    pipe_cls = _facade_attr("AutoHealPipeline", AutoHealPipeline)
    norm_fn = _facade_attr("normalize_test_command", normalize_test_command)
    norm_cmd = norm_fn(args.test_cmd)
    pipeline = pipe_cls(
        cwd=Path(args.cwd) if args.cwd else None, max_cycles=args.max_cycles
    )
    fail_empty = bool(getattr(args, "fail_on_empty_staging", False))
    if getattr(args, "diagnose_slice", False):
        return _run_diagnose_slice_cli(
            pipeline, norm_cmd, target_file_str, cwd_path, args.json, fail_empty
        )

    if not target_file_str:
        stg_py = _collect_staged_py(cwd_path)
        if not stg_py:
            report = AutoHealSessionReport(
                success=not fail_empty,
                cycles_used=0,
                max_cycles=args.max_cycles,
                initial_failed=0,
                final_failed=0,
                message=(
                    "Empty staging: no target Python files found (--fail-on-empty-staging)."
                    if fail_empty
                    else "Clean staging: no target file required healing."
                ),
            )
            return _emit_report(report, args.json)
        return _run_staging_batch(pipeline, norm_cmd, stg_py, args.json)

    report = pipeline.run_pipeline(test_cmd=norm_cmd, target_file=target_file_str)
    return _emit_report(report, args.json)

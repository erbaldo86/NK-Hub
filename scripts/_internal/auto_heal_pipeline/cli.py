# -*- coding: utf-8 -*-
"""Parser CLI e punto di ingresso lazy per auto_heal_pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _internal.nk_common.paths import reconfigure_streams


def _build_cli_parser() -> Any:
    """Costruisce il parser CLI senza forzare l'import di pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="NK Hub Generation Universal CLI Auto-Healer Pipeline"
    )
    parser.add_argument(
        "--test-cmd",
        type=str,
        default="pytest -q",
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
        "--json", action="store_true", help="Stampa il rapporto di sessione in JSON"
    )
    return parser


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
    if not target_file_str:
        stg_dir = cwd_path / ".staging"
        stg_py = (
            sorted(f for f in stg_dir.rglob("*.py") if "__pycache__" not in f.parts)
            if stg_dir.exists()
            else []
        )
        if stg_py:
            target_file_str = str(stg_py[0])
        else:
            report = AutoHealSessionReport(
                success=True,
                cycles_used=0,
                max_cycles=args.max_cycles,
                initial_failed=0,
                final_failed=0,
                message="Clean staging: no target file required healing.",
            )
            if args.json:
                print(report.model_dump_json(indent=2))
            else:
                print(f"🟢 [AUTO-HEAL] {report.message}")
            return 0

    pipe_cls = _facade_attr("AutoHealPipeline", AutoHealPipeline)
    norm_fn = _facade_attr("normalize_test_command", normalize_test_command)
    pipeline = pipe_cls(
        cwd=Path(args.cwd) if args.cwd else None, max_cycles=args.max_cycles
    )
    norm_cmd = norm_fn(args.test_cmd)
    report = pipeline.run_pipeline(test_cmd=norm_cmd, target_file=target_file_str)

    if args.json:
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

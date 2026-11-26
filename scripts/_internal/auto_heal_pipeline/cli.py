# -*- coding: utf-8 -*-
"""Parser CLI e punto di ingresso lazy per auto_heal_pipeline con supporto lane."""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any, List, Optional

from _internal.nk_common.lane_paths import is_lane_container_entry, resolve_staging_dir
from _internal.nk_common.paths import reconfigure_streams


def _build_cli_parser() -> Any:
    """Costruisce il parser CLI senza forzare l'import di pydantic su --help."""
    parser = argparse.ArgumentParser(description="NK Hub Generation Universal CLI Auto-Healer Pipeline")
    parser.add_argument("--test-cmd", type=str, default="pytest", required=False, help="Comando pytest da eseguire")
    parser.add_argument("--target-file", type=str, default="", required=False, help="File sorgente target da riparare")
    parser.add_argument("--cwd", type=str, default=None, help="Directory di lavoro")
    parser.add_argument("--stage-dir", type=str, default=None, help="Cartella staging opzionale")
    parser.add_argument("--lane-id", type=str, default=None, help="ID lane isolata in .staging/lanes/<id>/")
    parser.add_argument("--max-cycles", type=int, default=3, help="Numero massimo di cicli di riparazione (default: 3)")
    parser.add_argument("--diagnose-slice", action="store_true", help="Diagnosi read-only Ochiai e slice AST")
    parser.add_argument("--fail-on-empty-staging", action="store_true", help="Termina con exit code 1 se .staging/ e vuoto")
    parser.add_argument("--json", action="store_true", help="Stampa il rapporto di sessione in JSON")
    return parser


def _emit_report(report: Any, as_json: bool) -> int:
    if as_json:
        print(report.model_dump_json(indent=2))
    elif report.success:
        print(f"🟢 [AUTO-HEAL] {report.message}")
        if report.patch_note_line:
            print(f"📝 [PATCH-NOTE] {report.patch_note_line}")
    else:
        print(f"🔴 [AUTO-HEAL] {report.message}")
        if report.fault_location:
            print(f"   Last detected fault: {report.fault_location} ({report.error_type})")
    return 0 if report.success else 1


def _run_staging_batch(pipeline: Any, norm_cmd: Any, stg_py: List[Path], as_json: bool) -> int:
    if len(stg_py) == 1:
        return _emit_report(pipeline.run_pipeline(test_cmd=norm_cmd, target_file=str(stg_py[0])), as_json)
    reports = [pipeline.run_pipeline(test_cmd=norm_cmd, target_file=str(f)) for f in stg_py]
    overall_ok = all(r.success for r in reports)
    if as_json:
        print(json.dumps({"success": overall_ok, "files_processed": len(reports), "reports": [r.model_dump() for r in reports]}, indent=2))
    else:
        for f, r in zip(stg_py, reports):
            print(f"{'🟢' if r.success else '🔴'} [AUTO-HEAL] {f.name}: {r.message}")
    return 0 if overall_ok else 1


def _emit_diagnose_report(report: Any, as_json: bool) -> int:
    if as_json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"{'🟢' if report.success else '🟡'} [DIAGNOSE-SLICE] {report.message}")
        if report.fault_location:
            print(f"   Fault: {report.fault_location} | Ochiai={report.ochiai_score} | Tokens={report.code_slice_tokens}")
    return 0 if report.success else 1


def _run_diagnose_staging_batch(pipeline: Any, norm_cmd: Any, stg_py: List[Path], as_json: bool) -> int:
    if len(stg_py) == 1:
        return _emit_diagnose_report(pipeline.diagnose_slice(test_cmd=norm_cmd, target_file=str(stg_py[0])), as_json)
    reports = [pipeline.diagnose_slice(test_cmd=norm_cmd, target_file=str(f)) for f in stg_py]
    overall_ok = all(r.success for r in reports)
    if as_json:
        print(json.dumps({"success": overall_ok, "files_processed": len(reports), "reports": [r.model_dump() for r in reports]}, indent=2))
    else:
        for f, r in zip(stg_py, reports):
            print(f"{'🟢' if r.success else '🟡'} [DIAGNOSE-SLICE] {f.name}: {r.message}")
    return 0 if overall_ok else 1


def _filter_staged_py_entries(stg_dir: Path, excl_lanes: bool) -> List[Path]:
    return sorted(
        f for f in stg_dir.rglob("*.py")
        if "__pycache__" not in f.parts and not (excl_lanes and is_lane_container_entry(f.relative_to(stg_dir).parts))
    )


def _collect_staged_py(cwd_path: Path, *, stage_dir: Optional[str] = None, lane_id: Optional[str] = None) -> List[Path]:
    """Elenca i file Python in .staging/[lanes/<id>/] escludendo __pycache__ e lanes/ in legacy."""
    if lane_id is not None or stage_dir is not None:
        stg_dir, norm_lane = resolve_staging_dir(cwd_path, lane_id=lane_id, staging_dir=stage_dir)
    else:
        stg_dir, norm_lane = cwd_path / ".staging", None
    if not stg_dir.exists():
        return []
    return _filter_staged_py_entries(stg_dir, norm_lane is None and stg_dir.name == ".staging")


def _run_diagnose_slice_cli(
    pipeline: Any, norm_cmd: Any, target_file_str: str, cwd_path: Path, as_json: bool, fail_empty: bool,
    *, stage_dir: Optional[str] = None, lane_id: Optional[str] = None,
) -> int:
    from _internal.auto_heal_pipeline.models_and_slice import DiagnoseSliceReport

    if not target_file_str:
        stg_py = _collect_staged_py(cwd_path, stage_dir=stage_dir, lane_id=lane_id)
        if not stg_py:
            rep = DiagnoseSliceReport(
                success=not fail_empty, target_file="", exit_code=1 if fail_empty else 0,
                tests_passed=0, tests_failed=0, failure_category="NONE",
                message="Empty staging: no target file for diagnose-slice." if fail_empty else "Clean staging: no target file required diagnose-slice.",
            )
            return _emit_diagnose_report(rep, as_json)
        return _run_diagnose_staging_batch(pipeline, norm_cmd, stg_py, as_json)
    return _emit_diagnose_report(pipeline.diagnose_slice(test_cmd=norm_cmd, target_file=target_file_str), as_json)


def _instantiate_pipeline(pipe_cls: Any, args: argparse.Namespace) -> Any:
    kw: dict[str, Any] = {"cwd": Path(args.cwd) if args.cwd else None, "max_cycles": args.max_cycles}
    try:
        params = inspect.signature(pipe_cls).parameters
        has_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        for k, v in (("lane_id", getattr(args, "lane_id", None)), ("stage_dir", Path(args.stage_dir) if getattr(args, "stage_dir", None) else None)):
            if v is not None and (has_var or k in params):
                kw[k] = v
    except (TypeError, ValueError):
        pass
    return pipe_cls(**kw)


def main() -> int:
    """Esegue la pipeline di auto-riparazione da riga di comando."""
    reconfigure_streams()
    args = _build_cli_parser().parse_args()

    from _internal.auto_heal_pipeline.models_and_slice import AutoHealSessionReport, _facade_attr, normalize_test_command
    from _internal.auto_heal_pipeline.runner import AutoHealPipeline

    cwd_path = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    target_file_str = args.target_file.strip() if args.target_file else ""
    pipe_cls = _facade_attr("AutoHealPipeline", AutoHealPipeline)
    norm_cmd = _facade_attr("normalize_test_command", normalize_test_command)(args.test_cmd)
    pipeline = _instantiate_pipeline(pipe_cls, args)
    fail_empty = bool(getattr(args, "fail_on_empty_staging", False))
    lane_id, stage_dir = getattr(args, "lane_id", None), getattr(args, "stage_dir", None)
    if getattr(args, "diagnose_slice", False):
        return _run_diagnose_slice_cli(pipeline, norm_cmd, target_file_str, cwd_path, args.json, fail_empty, stage_dir=stage_dir, lane_id=lane_id)

    if not target_file_str:
        stg_py = _collect_staged_py(cwd_path, stage_dir=stage_dir, lane_id=lane_id)
        if not stg_py:
            report = AutoHealSessionReport(
                success=not fail_empty, cycles_used=0, max_cycles=args.max_cycles, initial_failed=0, final_failed=0,
                message="Empty staging: no target Python files found (--fail-on-empty-staging)." if fail_empty else "Clean staging: no target file required healing.",
            )
            return _emit_report(report, args.json)
        return _run_staging_batch(pipeline, norm_cmd, stg_py, args.json)

    return _emit_report(pipeline.run_pipeline(test_cmd=norm_cmd, target_file=target_file_str), args.json)

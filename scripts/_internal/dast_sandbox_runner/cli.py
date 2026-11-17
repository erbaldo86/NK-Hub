"""Parser e dispatch CLI pure-stdlib per dast_sandbox_runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence


def _build_cli_parser() -> argparse.ArgumentParser:
    """Costruisce il parser CLI senza importare pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="NK Hub Generation DAST Shadow Sandbox Runner",
    )
    parser.add_argument(
        "--script", type=str, help="Percorso dello script Python da eseguire"
    )
    parser.add_argument(
        "--overlay-staging",
        type=str,
        default=None,
        help="Percorso radice su cui eseguire la Shadow Run sovrapponendo .staging/",
    )
    parser.add_argument(
        "--staging-dir",
        type=str,
        default=None,
        help="Percorso opzionale alla cartella .staging/ per --overlay-staging",
    )
    parser.add_argument(
        "--profile",
        type=str,
        choices=("evaluator", "builder"),
        default="builder",
        help="Profilo di isolamento della sandbox (default fail-safe: builder)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Percorso file JSON esplicito o cartella nk_tracking per il report DAST",
    )
    parser.add_argument(
        "--report-to-tracking",
        action="store_true",
        help="Salva il report automatico atomico dast_report_<uuid8>.json in nk_tracking/",
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="Timeout in secondi"
    )
    parser.add_argument("--json", action="store_true", help="Stampa il report in JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per l'esecuzione isolata in Shadow Sandbox."""
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    from .constants import SandboxConfig, SandboxTelemetryReport, _facade_attr
    from .e2e_and_audit import run_staging_shadow_verification
    from .fuzzer import DASTSandboxRunner
    from .process_runner import write_atomic_dast_report
    from .sandbox_fs import ShadowSandbox, _strip_builder_holdouts_from_sandbox

    sys_mod = _facade_attr("sys", sys)
    asyncio_mod = _facade_attr("asyncio", asyncio)
    write_rep_fn = _facade_attr("write_atomic_dast_report", write_atomic_dast_report)

    if args.overlay_staging:
        shadow_timeout = max(float(args.timeout), 120.0)
        overlay_root = Path(args.overlay_staging)
        overlay_fn = _facade_attr(
            "run_staging_shadow_verification", run_staging_shadow_verification
        )
        res = overlay_fn(
            repo_root=overlay_root,
            staging_dir=Path(args.staging_dir) if args.staging_dir else None,
            timeout_sec=shadow_timeout,
            profile=args.profile,
        )
        if args.output or args.report_to_tracking:
            tracking_base = overlay_root.resolve() / "nk_tracking"
            saved_rep = write_rep_fn(
                res,
                tracking_base,
                explicit_output=args.output,
            )
            res["tracking_report_file"] = str(saved_rep)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"[DAST-OVERLAY-STAGING] Status: {res['status']} | "
                f"Overlay Files: {res.get('overlay_files_count', 0)} | "
                f"Cleaned: {res.get('sandbox_cleaned', False)} ({res.get('duration_sec', 0.0)} s)"
            )
        return 0 if res.get("passed") else 1

    if not args.script:
        parser.print_help()
        return 0

    src_script = Path(args.script).resolve()
    if not src_script.exists():
        sys_mod.stderr.write(f"Script non trovato: {src_script}\n")
        return 1

    sandbox_cls = _facade_attr("ShadowSandbox", ShadowSandbox)
    cfg_cls = _facade_attr("SandboxConfig", SandboxConfig)
    runner_cls = _facade_attr("DASTSandboxRunner", DASTSandboxRunner)
    strip_fn = _facade_attr(
        "_strip_builder_holdouts_from_sandbox", _strip_builder_holdouts_from_sandbox
    )

    async def _run() -> SandboxTelemetryReport:
        with sandbox_cls() as sb:
            sb.copy_file(src_script)
            sibling_py = [
                p
                for p in src_script.parent.glob("*.py")
                if p.is_file() and p.resolve() != src_script
            ]
            if len(sibling_py) <= 50:
                for sib in sibling_py:
                    sb.copy_file(sib)
            if args.profile == "builder":
                strip_fn(sb.sandbox_dir)
                py_paths = str(sb.sandbox_dir)
            else:
                py_paths = f"{src_script.parent}{os.pathsep}{src_script.parent.parent}"
            cfg = cfg_cls(
                timeout_sec=args.timeout,
                env_vars={"PYTHONPATH": py_paths},
                profile=args.profile,
            )
            runner = runner_cls(cfg)
            return await runner.run_in_sandbox(
                sb,
                [sys_mod.executable, src_script.name],
                target_script_name=src_script.name,
            )

    report = asyncio_mod.run(_run())
    if args.output or args.report_to_tracking:
        default_tracking = src_script.parent.parent / "nk_tracking"
        write_rep_fn(
            report.model_dump(),
            default_tracking,
            explicit_output=args.output,
        )
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"[DAST-SANDBOX] Success: {report.success} | Exit: {report.exit_code}")
    return 0 if report.success else 1

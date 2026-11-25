"""Parser e dispatch CLI pure-stdlib per dast_sandbox_runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HARNESS_ERR_RE = re.compile(
    r"(?:^|\n)\s*(?:ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError)(?::|\s|$)"
)


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
        "--verify-holdout",
        action="store_true",
        help="Verifica fail-closed gli holdout protetti in sandbox (richiede --profile evaluator)",
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


def _resolve_hub_repo_root() -> Path:
    """Risolve la root del repository gestendo sia esecuzione da scripts/ sia da .staging/."""
    scripts_dir = Path(__file__).resolve().parents[2]
    if scripts_dir.parent.name == ".staging":
        return scripts_dir.parent.parent
    return scripts_dir.parent


def classify_poc_outcome(
    exit_code: int,
    stdout: str,
    stderr: str,
    timed_out: bool = False,
    memory_exceeded: bool = False,
) -> str:
    """Classifica l'esito del Referee PoC: EXPLOIT_CONFIRMED, HARNESS_ERROR o REFUTED."""
    if exit_code == 0 and not timed_out and not memory_exceeded:
        return "REFUTED"
    primary_err = stderr if stderr.strip() else stdout
    if not timed_out and not memory_exceeded and _HARNESS_ERR_RE.search(primary_err):
        return "HARNESS_ERROR"
    return "EXPLOIT_CONFIRMED"


def _prepare_verify_holdout_args(args: Any, sys_mod: Any) -> Optional[int]:
    """Verifica prerequisiti e risolve workspace root quando --verify-holdout e attivo."""
    if not args.verify_holdout or args.overlay_staging:
        return None
    norm_profile = args.profile.strip().lower()
    if norm_profile != "evaluator":
        fail_payload = {
            "status": "FAIL",
            "passed": False,
            "profile": norm_profile,
            "error": "--verify-holdout richiede --profile evaluator",
        }
        if args.json:
            print(json.dumps(fail_payload, indent=2, ensure_ascii=False))
        else:
            sys_mod.stderr.write(f"[FAIL] {fail_payload['error']}\n")
        return 1
    args.overlay_staging = str(_resolve_hub_repo_root())
    return None


def _run_overlay_cli(
    args: Any, overlay_fn: Any, write_rep_fn: Any
) -> int:
    """Esegue la verifica DAST Shadow Sandbox in modalita --overlay-staging."""
    shadow_timeout = max(float(args.timeout), 120.0)
    overlay_root = Path(args.overlay_staging)
    call_kwargs: Dict[str, Any] = {
        "repo_root": overlay_root,
        "staging_dir": Path(args.staging_dir) if args.staging_dir else None,
        "timeout_sec": shadow_timeout,
        "profile": args.profile,
    }
    if args.verify_holdout:
        call_kwargs["verify_holdout"] = True
    res = overlay_fn(**call_kwargs)
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


def _mount_script_into_overlay(
    sb: Any,
    src_script: Path,
    overlay_root: Path,
    stg_dir: Path,
    norm_prof: str,
    copy_pkg_fn: Any,
    strip_paths: Sequence[str],
) -> Tuple[str, List[str]]:
    """Monta lo script Referee PoC dentro una sandbox gia popolata con l'overlay."""
    if stg_dir.exists() and src_script.is_relative_to(stg_dir):
        rel = src_script.relative_to(stg_dir)
        rel_posix = rel.as_posix()
        if not (sb.sandbox_dir / rel).is_file():
            sb.copy_file(src_script, rel_posix)
        return rel_posix, [str(sb.sandbox_dir), str((sb.sandbox_dir / rel).parent)]

    if src_script.is_relative_to(overlay_root):
        rel = src_script.relative_to(overlay_root)
        rel_posix = rel.as_posix()
        if norm_prof == "builder" and any(
            rel_posix == p or rel_posix.startswith(f"{p}/") for p in strip_paths
        ):
            raise ValueError(f"Script holdout vietato in profilo builder: {rel_posix}")
        if not (sb.sandbox_dir / rel).is_file():
            sb.copy_file(src_script, rel_posix)
        return rel_posix, [str(sb.sandbox_dir), str((sb.sandbox_dir / rel).parent)]

    target_rel = src_script.name
    if (sb.sandbox_dir / target_rel).exists():
        target_rel = f"_nk_poc_{uuid.uuid4().hex[:8]}.py"
        sb.copy_file(src_script, target_rel)
        return target_rel, [str(sb.sandbox_dir)]
    return copy_pkg_fn(sb, src_script, overwrite=False)


def _compose_sandbox_pythonpath(
    sb_dir: Path,
    py_roots: Sequence[str],
    src_script: Path,
    norm_prof: str,
    has_overlay: bool,
) -> str:
    """Compone PYTHONPATH con la radice overlay e i sub-root package confinati."""
    ordered: List[str] = [str(sb_dir)]
    for sub_name in ("scripts", "src", "src_app", "app"):
        cand = sb_dir / sub_name
        if cand.is_dir():
            ordered.append(str(cand))
    for r in py_roots:
        if r not in ordered:
            ordered.append(r)
    if norm_prof != "builder" and not has_overlay:
        for fallback in (str(src_script.parent), str(src_script.parent.parent)):
            if fallback not in ordered:
                ordered.append(fallback)
    return os.pathsep.join(ordered)


def _save_compact_poc_report(
    report: Any,
    outcome: str,
    src_script: Path,
    target_rel: str,
    overlay_root: Optional[Path],
    overlay_files_count: int,
    norm_prof: str,
    write_rep_fn: Any,
) -> Path:
    """Salva atomicamente il report JSON compatto in %TEMP%/nk_diagnostics/dast_poc_<uuid8>.json."""
    diag_dir = Path(tempfile.gettempdir()) / "nk_diagnostics"
    poc_path = diag_dir / f"dast_poc_{uuid.uuid4().hex[:8]}.json"
    compact_payload: Dict[str, Any] = {
        "sandbox_id": report.sandbox_id,
        "script": str(src_script),
        "target_rel": target_rel,
        "overlay_root": str(overlay_root) if overlay_root is not None else None,
        "profile": norm_prof,
        "outcome": outcome,
        "exit_code": report.exit_code,
        "success": report.success,
        "timed_out": report.timed_out,
        "memory_exceeded": report.memory_exceeded,
        "duration_sec": report.duration_sec,
        "peak_memory_bytes": report.peak_memory_bytes,
        "overlay_files_count": overlay_files_count,
        "stdout": report.stdout,
        "stderr": report.stderr,
    }
    return write_rep_fn(compact_payload, diag_dir, explicit_output=poc_path)


def _run_script_cli(
    args: Any,
    sys_mod: Any,
    asyncio_mod: Any,
    write_rep_fn: Any,
) -> int:
    """Esegue --script (con o senza --overlay-staging) con alberi package completi e report PoC."""
    from .constants import SandboxConfig, SandboxTelemetryReport, _BUILDER_STRIP_PATHS, _facade_attr
    from .fuzzer import DASTSandboxRunner
    from .sandbox_fs import (
        ShadowSandbox,
        _strip_builder_holdouts_from_sandbox,
        copy_script_package_context,
    )
    from .staging_overlay import prepare_staging_overlay

    src_script = Path(args.script).resolve()
    if not src_script.is_file():
        sys_mod.stderr.write(f"Script non trovato: {src_script}\n")
        return 1

    norm_prof = args.profile.strip().lower()
    overlay_root = Path(args.overlay_staging).resolve() if args.overlay_staging else None
    if overlay_root is not None and not overlay_root.is_dir():
        err_msg = f"Root overlay non trovata: {overlay_root}"
        if args.json:
            print(json.dumps({"status": "FAIL", "passed": False, "outcome": "HARNESS_ERROR", "error": err_msg}, indent=2))
        else:
            sys_mod.stderr.write(f"[FAIL] {err_msg}\n")
        return 1

    stg_dir = (
        Path(args.staging_dir).resolve()
        if args.staging_dir
        else ((overlay_root / ".staging").resolve() if overlay_root is not None else None)
    )
    sandbox_cls = _facade_attr("ShadowSandbox", ShadowSandbox)
    cfg_cls = _facade_attr("SandboxConfig", SandboxConfig)
    runner_cls = _facade_attr("DASTSandboxRunner", DASTSandboxRunner)
    strip_fn = _facade_attr("_strip_builder_holdouts_from_sandbox", _strip_builder_holdouts_from_sandbox)
    overlay_prep_fn = _facade_attr("prepare_staging_overlay", prepare_staging_overlay)
    copy_pkg_fn = _facade_attr("copy_script_package_context", copy_script_package_context)

    async def _run() -> Tuple[SandboxTelemetryReport, int, str]:
        with sandbox_cls() as sb:
            ov_count = 0
            if overlay_root is not None and stg_dir is not None:
                ov_files, _, _ = overlay_prep_fn(overlay_root, stg_dir, sb, norm_prof)
                ov_count = len(ov_files)
                target_rel, py_roots = _mount_script_into_overlay(
                    sb, src_script, overlay_root, stg_dir, norm_prof, copy_pkg_fn, _BUILDER_STRIP_PATHS
                )
            else:
                target_rel, py_roots = copy_pkg_fn(sb, src_script, overwrite=True)
                if norm_prof == "builder":
                    strip_fn(sb.sandbox_dir)

            py_paths = _compose_sandbox_pythonpath(
                sb.sandbox_dir, py_roots, src_script, norm_prof, overlay_root is not None
            )
            cfg = cfg_cls(
                timeout_sec=float(args.timeout),
                env_vars={"PYTHONPATH": py_paths},
                profile=norm_prof,
            )
            rep = await runner_cls(cfg).run_in_sandbox(
                sb, [sys_mod.executable, target_rel], target_script_name=target_rel
            )
            return rep, ov_count, target_rel

    report, ov_count, target_rel = asyncio_mod.run(_run())
    outcome = classify_poc_outcome(
        report.exit_code, report.stdout, report.stderr, report.timed_out, report.memory_exceeded
    )
    poc_path = _save_compact_poc_report(
        report, outcome, src_script, target_rel, overlay_root, ov_count, norm_prof, write_rep_fn
    )
    payload = report.model_dump()
    payload["outcome"] = outcome
    payload["poc_report_file"] = str(poc_path)
    if overlay_root is not None:
        payload["overlay_root"] = str(overlay_root)
        payload["overlay_files_count"] = ov_count

    if args.output or args.report_to_tracking:
        base_trk = (overlay_root / "nk_tracking") if overlay_root is not None else (src_script.parent.parent / "nk_tracking")
        write_rep_fn(payload, base_trk, explicit_output=args.output)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"[DAST-SANDBOX] Success: {report.success} | Exit: {report.exit_code} | Outcome: {outcome}")
    return 0 if report.success else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per l'esecuzione isolata in Shadow Sandbox."""
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    from .constants import _facade_attr
    from .e2e_and_audit import run_staging_shadow_verification
    from .process_runner import write_atomic_dast_report

    sys_mod = _facade_attr("sys", sys)
    asyncio_mod = _facade_attr("asyncio", asyncio)
    write_rep_fn = _facade_attr("write_atomic_dast_report", write_atomic_dast_report)

    holdout_err = _prepare_verify_holdout_args(args, sys_mod)
    if holdout_err is not None:
        return holdout_err

    if args.script:
        return _run_script_cli(args, sys_mod, asyncio_mod, write_rep_fn)

    if args.overlay_staging:
        overlay_fn = _facade_attr("run_staging_shadow_verification", run_staging_shadow_verification)
        return _run_overlay_cli(args, overlay_fn, write_rep_fn)

    parser.print_help()
    return 0

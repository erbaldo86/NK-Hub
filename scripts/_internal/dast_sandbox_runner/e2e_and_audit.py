"""Verifica end-to-end in Shadow Sandbox con overlay .staging/, AST Guard e pytest."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import DAST_MAX_OUTPUT_BYTES, _facade_attr
from .holdout_verify import verify_sandbox_holdouts
from .process_runner import _run_job_isolated_subprocess, write_atomic_dast_report
from .sandbox_fs import ShadowSandbox, _build_sanitized_sandbox_env, _truncate_utf8_bytes
from .staging_overlay import prepare_staging_overlay


def _resolve_prod_ast_guard_path(staging_dir: Optional[Path] = None) -> Path:
    """Risolve ast_guard_validator.py privilegiando lo staged del Hub se completo, altrimenti produzione."""
    facade_file = _facade_attr("__file__", None)
    raw_scripts_root = (
        Path(facade_file).resolve().parent if facade_file else Path(__file__).resolve().parents[2]
    )
    if raw_scripts_root.parent.name == ".staging":
        stg_guard = raw_scripts_root / "ast_guard_validator.py"
        if stg_guard.is_file() and (
            raw_scripts_root / "_internal" / "ast_guard_validator" / "overlay_helpers.py"
        ).is_file():
            return stg_guard
        return raw_scripts_root.parent.parent / "scripts" / "ast_guard_validator.py"
    if staging_dir is not None:
        ext_stg = staging_dir / "scripts" / "ast_guard_validator.py"
        if ext_stg.is_file() and (
            staging_dir / "scripts" / "_internal" / "ast_guard_validator" / "overlay_helpers.py"
        ).is_file():
            return ext_stg
    return raw_scripts_root / "ast_guard_validator.py"


def _has_staged_changes(staging_dir: Optional[Path]) -> bool:
    """True se staging_dir contiene file staged o tombstone oltre a .gitkeep."""
    if staging_dir is None or not staging_dir.is_dir():
        return False
    return any(p.name != ".gitkeep" for p in staging_dir.iterdir())


def _build_ast_guard_cmd(
    guard_script: Path,
    sb_dir: Path,
    repo_root: Optional[Path],
    staging_dir: Optional[Path],
    sys_mod: Any,
) -> Tuple[List[str], Path]:
    """Compone il comando singolo di ast_guard_validator con --overlay-staging --quality-diff se disponibile."""
    has_overlay_guard = (
        guard_script.parent / "_internal" / "ast_guard_validator" / "overlay_helpers.py"
    ).is_file()
    if has_overlay_guard and _has_staged_changes(staging_dir) and repo_root is not None:
        cmd = [
            sys_mod.executable,
            "-B",
            str(guard_script),
            "--target",
            "all",
            "--overlay-staging",
            "--stage-dir",
            str(staging_dir),
            "--quality-diff",
            "--json",
        ]
        return cmd, repo_root
    return [sys_mod.executable, "-B", str(guard_script), "--target", "all", "--json"], sb_dir


def _parse_ast_guard_output(returncode: int, raw_out: str, raw_err: str) -> Dict[str, Any]:
    """Interpreta il report JSON (o testo di fallback) emesso da ast_guard_validator."""
    stripped = raw_out.strip()
    parsed_json: Optional[Dict[str, Any]] = None
    if stripped.startswith("{"):
        try:
            cand = json.loads(stripped)
            if isinstance(cand, dict):
                parsed_json = cand
        except ValueError:
            parsed_json = None

    if parsed_json is not None:
        passed = (returncode == 0) and bool(parsed_json.get("passed", False))
        files_checked = int(parsed_json.get("files_scanned", 0))
        violations = int(parsed_json.get("total_violations", 0))
        if not passed and violations == 0:
            violations = 1
    else:
        passed = returncode == 0
        fail_lines = [ln for ln in raw_out.splitlines() if ln.strip().startswith("- [")]
        violations = 0 if passed else max(1, len(fail_lines))
        files_checked = 0

    return {
        "executed": True,
        "passed": passed,
        "exit_code": returncode,
        "files_checked": files_checked,
        "violations": violations,
        "stdout": _truncate_utf8_bytes(raw_out, DAST_MAX_OUTPUT_BYTES),
        "stderr": _truncate_utf8_bytes(raw_err, DAST_MAX_OUTPUT_BYTES),
    }


def _run_ast_guard_on_sandbox(
    sb_dir: Path,
    env: Dict[str, str],
    timeout_sec: float,
    run_sub_fn: Any,
    sys_mod: Any,
    repo_root: Optional[Path] = None,
    staging_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Esegue una singola chiamata AST Guard in 1 passata (--overlay-staging --quality-diff o --target all)."""
    guard_script = _resolve_prod_ast_guard_path(staging_dir=staging_dir)
    if not guard_script.is_file():
        return {"executed": False, "passed": True}

    cmd, run_cwd = _build_ast_guard_cmd(guard_script, sb_dir, repo_root, staging_dir, sys_mod)
    try:
        proc_ast = run_sub_fn(
            cmd,
            cwd=run_cwd,
            env=env,
            timeout_sec=min(timeout_sec, 150.0),
        )
        return _parse_ast_guard_output(
            proc_ast.returncode, proc_ast.stdout or "", proc_ast.stderr or ""
        )
    except Exception as exc:
        err_str = str(exc)
        return {
            "executed": True,
            "passed": False,
            "exit_code": -1,
            "files_checked": 0,
            "violations": 1,
            "error": err_str,
            "stdout": "",
            "stderr": _truncate_utf8_bytes(err_str, DAST_MAX_OUTPUT_BYTES),
        }


def _extract_re_int(pattern: str, text: str) -> int:
    """Estrae un contatore intero da pattern regex o restituisce 0."""
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def _count_dot_progress(pt_combined: str) -> int:
    """Conta i test superati espressi con progresso compatto a punti pytest."""
    return sum(
        m.group(1).count(".")
        for m in re.finditer(r"^([.sxXFE]+)\s+\[\s*\d+%\]", pt_combined.replace("\r\n", "\n"), flags=re.MULTILINE)
    )


def _build_pytest_metrics(
    returncode: int, raw_out: str, raw_err: str, duration: float
) -> Dict[str, Any]:
    """Estrae conteggi pytest ed applica gate anti-gaming su zero test o skip."""
    pt_combined = f"{raw_out}\n{raw_err}"
    pt_passed_cnt = _extract_re_int(r"(\d+)\s+passed", pt_combined)
    if pt_passed_cnt == 0 and returncode == 0:
        pt_passed_cnt = _count_dot_progress(pt_combined)
    pt_skipped_cnt = _extract_re_int(r"(\d+)\s+skipped", pt_combined) + _extract_re_int(r"(\d+)\s+xfailed", pt_combined)
    pt_failed_cnt = _extract_re_int(r"(\d+)\s+failed", pt_combined) + _extract_re_int(r"(\d+)\s+errors?", pt_combined) + pt_skipped_cnt
    if returncode != 0 and pt_failed_cnt == 0:
        pt_failed_cnt = 1
    pt_total_cnt = pt_passed_cnt + pt_failed_cnt
    no_tests = returncode == 5 or pt_total_cnt == 0
    pt_passed = returncode == 0 and not no_tests and pt_skipped_cnt == 0 and pt_passed_cnt > 0
    res: Dict[str, Any] = {
        "executed": True, "passed": pt_passed, "exit_code": returncode, "no_tests_collected": no_tests,
        "tests_passed": pt_passed_cnt, "tests_failed": pt_failed_cnt, "tests_skipped": pt_skipped_cnt,
        "tests_total": pt_total_cnt, "duration_s": round(duration, 3),
        "stdout": _truncate_utf8_bytes(raw_out, DAST_MAX_OUTPUT_BYTES),
        "stderr": _truncate_utf8_bytes(raw_err, DAST_MAX_OUTPUT_BYTES),
    }
    if no_tests:
        res["error"] = "Pytest exit code 5: nessun test raccolto (anti-gaming gate)"
    return res


def _run_pytest_on_sandbox(
    sb_dir: Path,
    env: Dict[str, str],
    timeout_sec: float,
    run_sub_fn: Any,
    sys_mod: Any,
    time_mod: Any,
) -> Dict[str, Any]:
    """Esegue pytest isolato nella sandbox con gate fail-closed su tests/ assente o zero test."""
    if not (sb_dir / "tests").is_dir():
        return {
            "executed": True, "passed": False, "exit_code": 5, "no_tests_collected": True,
            "error": "Cartella tests mancante o rimossa (exit code 5)", "stdout": "", "stderr": "",
        }
    try:
        pt_t0 = time_mod.perf_counter()
        proc_pt = run_sub_fn(
            [sys_mod.executable, "-B", "-m", "pytest", "tests", "-p", "no:cacheprovider", "-q", "--tb=short"],
            cwd=sb_dir, env=env, timeout_sec=timeout_sec,
        )
        return _build_pytest_metrics(
            proc_pt.returncode, proc_pt.stdout or "", proc_pt.stderr or "", time_mod.perf_counter() - pt_t0
        )
    except Exception as exc:
        err_str = str(exc)
        return {
            "executed": True, "passed": False, "exit_code": -1, "error": err_str,
            "stdout": "", "stderr": _truncate_utf8_bytes(err_str, DAST_MAX_OUTPUT_BYTES),
        }


def _reject_invalid_holdout_profile(
    root: Path, norm_prof: str, t0: float, time_mod: Any
) -> Dict[str, Any]:
    """Costruisce il payload fail-closed quando --verify-holdout non usa profilo evaluator."""
    holdout_fail = verify_sandbox_holdouts(root, root, norm_prof, [], [])
    return {
        "status": "FAIL",
        "passed": False,
        "is_dry_run": False,
        "profile": norm_prof,
        "repo_root": str(root),
        "error": holdout_fail.get("error", "--verify-holdout richiede profilo evaluator"),
        "holdout_verification": holdout_fail,
        "duration_sec": round(time_mod.perf_counter() - t0, 4),
    }


def _persist_diagnostic_report(report_payload: Dict[str, Any], write_rep_fn: Any) -> None:
    """Salva il report diagnostico DAST in tempdir isolata."""
    try:
        diag_dir = Path(tempfile.gettempdir()) / "nk_diagnostics"
        unique_diag_path = write_rep_fn(report_payload, diag_dir)
        report_payload["report_file"] = str(unique_diag_path)
        write_rep_fn(report_payload, diag_dir, explicit_output=diag_dir / "dast_last_report.json")
    except OSError as exc:
        report_payload["diagnostic_warning"] = str(exc)


def _format_holdout_error_summary(holdout_res: Dict[str, Any]) -> str:
    """Formatta i primi messaggi di errore holdout senza aumentare la complessita del chiamante."""
    holdout_errs = holdout_res.get("errors")
    if isinstance(holdout_errs, list) and holdout_errs:
        return "; ".join(str(e) for e in holdout_errs[:5])
    return ""


def _attach_failure_tails(
    report_payload: Dict[str, Any],
    ast_guard_res: Dict[str, Any],
    pytest_res: Dict[str, Any],
    holdout_res: Dict[str, Any],
) -> None:
    """Allega la coda stderr (<= 2048 byte) senza duplicare stdout nei report di fallimento."""
    parts = (
        str(ast_guard_res.get("stderr", "")),
        str(ast_guard_res.get("error", "")),
        str(pytest_res.get("stderr", "")),
        str(pytest_res.get("error", "")),
        str(holdout_res.get("error", "")),
        _format_holdout_error_summary(holdout_res),
    )
    combined_stderr = "\n".join(p for p in parts if p)
    report_payload["stderr_tail"] = _truncate_utf8_bytes(combined_stderr, DAST_MAX_OUTPUT_BYTES)


def _build_shadow_probe_env(env_fn: Any, hooks_iso_dir: str, sb_dir: Path) -> Dict[str, str]:
    """Costruisce env sanitizzato isolato per i sottoprocessi AST Guard e pytest."""
    env = env_fn()
    env.pop("NK_CONVERSATION_ID", None)
    env.pop("ANTIGRAVITY_CONVERSATION_ID", None)
    env["NK_HOOKS_TEMP_DIR"] = hooks_iso_dir
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(sb_dir)
    return env


def run_staging_shadow_verification(
    repo_root: Path | str,
    staging_dir: Optional[Path | str] = None,
    timeout_sec: float = 120.0,
    run_pytest: bool = True,
    run_ast_guard: bool = True,
    profile: str = "builder",
    verify_holdout: bool = False,
) -> Dict[str, Any]:
    """Copia il progetto in Shadow Sandbox, sovrappone .staging/ ed esegue AST Guard, pytest e holdout check."""
    time_mod = _facade_attr("time", time)
    sys_mod = _facade_attr("sys", sys)
    sandbox_cls = _facade_attr("ShadowSandbox", ShadowSandbox)
    run_sub_fn = _facade_attr("_run_job_isolated_subprocess", _run_job_isolated_subprocess)
    write_rep_fn = _facade_attr("write_atomic_dast_report", write_atomic_dast_report)
    env_fn = _facade_attr("_build_sanitized_sandbox_env", _build_sanitized_sandbox_env)

    t0 = time_mod.perf_counter()
    root = Path(repo_root).resolve()
    norm_prof = profile.strip().lower()
    if not root.exists():
        return {
            "status": "FAIL", "passed": False, "repo_root": str(root),
            "error": f"Root directory non trovata: {root}", "duration_sec": 0.0,
        }
    if verify_holdout and norm_prof != "evaluator":
        return _reject_invalid_holdout_profile(root, norm_prof, t0, time_mod)

    stg = Path(staging_dir).resolve() if staging_dir is not None else (root / ".staging").resolve()
    ast_guard_res: Dict[str, Any] = {"executed": False, "passed": True}
    pytest_res: Dict[str, Any] = {"executed": False, "passed": True}
    holdout_res: Dict[str, Any] = {"executed": False, "passed": True}
    sb_id, sb_dir_str = "", ""
    overlay_files, deleted_applied, stripped_holdouts = [], [], []

    with sandbox_cls() as sb, tempfile.TemporaryDirectory(prefix="nk_dast_hooks_") as hooks_iso_dir:
        sb_id, sb_dir_str = sb.sandbox_id, str(sb.sandbox_dir)
        overlay_files, deleted_applied, stripped_holdouts = prepare_staging_overlay(
            root, stg, sb, norm_prof
        )
        if verify_holdout:
            holdout_res = verify_sandbox_holdouts(
                root, sb.sandbox_dir, norm_prof, overlay_files, deleted_applied
            )

        env = _build_shadow_probe_env(env_fn, hooks_iso_dir, sb.sandbox_dir)

        if run_ast_guard:
            ast_guard_res = _run_ast_guard_on_sandbox(
                sb.sandbox_dir, env, timeout_sec, run_sub_fn, sys_mod, repo_root=root, staging_dir=stg
            )
        tests_dir = sb.sandbox_dir / "tests"
        if run_pytest and (tests_dir.exists() or (root / "tests").exists()):
            pytest_res = _run_pytest_on_sandbox(
                sb.sandbox_dir, env, timeout_sec, run_sub_fn, sys_mod, time_mod
            )

    sandbox_cleaned = not Path(sb_dir_str).exists()
    overall_passed = (
        bool(ast_guard_res.get("passed", True))
        and bool(pytest_res.get("passed", True))
        and bool(holdout_res.get("passed", True))
        and sandbox_cleaned
    )
    report_payload: Dict[str, Any] = {
        "status": "PASS" if overall_passed else "FAIL",
        "passed": overall_passed,
        "is_dry_run": False,
        "profile": norm_prof,
        "sandbox_id": sb_id,
        "sandbox_dir": sb_dir_str,
        "sandbox_cleaned": sandbox_cleaned,
        "repo_root": str(root),
        "staging_dir": str(stg),
        "overlay_files_count": len(overlay_files),
        "overlay_files": overlay_files,
        "deleted_files": deleted_applied,
        "stripped_holdouts": stripped_holdouts,
        "ast_guard": ast_guard_res,
        "pytest": pytest_res,
        "duration_sec": round(time_mod.perf_counter() - t0, 4),
    }
    _attach_holdout_verdict(report_payload, holdout_res, verify_holdout)
    if not overall_passed:
        _attach_failure_tails(report_payload, ast_guard_res, pytest_res, holdout_res)

    _persist_diagnostic_report(report_payload, write_rep_fn)
    return report_payload


def _attach_holdout_verdict(
    report_payload: Dict[str, Any], holdout_res: Dict[str, Any], verify_holdout: bool
) -> None:
    """Allega esito nested e top-level holdout_passed/f_holdout quando verify_holdout e attivo."""
    if not verify_holdout:
        return
    ho_ok = bool(holdout_res.get("passed", False))
    report_payload["holdout_verification"] = holdout_res
    report_payload["holdout_passed"] = ho_ok
    report_payload["f_holdout"] = 0 if ho_ok else 1

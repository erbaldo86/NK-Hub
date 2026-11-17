"""Verifica end-to-end in Shadow Sandbox con overlay .staging/, AST Guard e pytest."""

from __future__ import annotations

import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import _facade_attr
from .process_runner import _run_job_isolated_subprocess, write_atomic_dast_report
from .sandbox_fs import ShadowSandbox, _build_sanitized_sandbox_env
from .staging_overlay import prepare_staging_overlay


def _run_ast_guard_on_sandbox(
    sb_dir: Path,
    env: Dict[str, str],
    timeout_sec: float,
    run_sub_fn: Any,
    sys_mod: Any,
) -> Dict[str, Any]:
    """Esegue AST Guard su tutti i directory target Python presenti nella sandbox."""
    facade_file = _facade_attr("__file__", None)
    scripts_root = (
        Path(facade_file).resolve().parent
        if facade_file
        else Path(__file__).resolve().parents[2]
    )
    hub_ast_guard = scripts_root / "ast_guard_validator.py"
    sb_ast_guard = sb_dir / "scripts" / "ast_guard_validator.py"
    guard_script = sb_ast_guard if sb_ast_guard.exists() else hub_ast_guard

    code_targets = [
        sb_dir / d
        for d in ("scripts", "src", "src_app", "app", "tests")
        if (sb_dir / d).exists()
        and (sb_dir / d).is_dir()
        and any((sb_dir / d).rglob("*.py"))
    ]
    targets_for_guard = code_targets if code_targets else [sb_dir]
    if not guard_script.exists():
        return {"executed": False, "passed": True}

    try:
        agg_passed = True
        agg_exit = 0
        agg_files_checked = 0
        agg_violations = 0
        agg_stdout_parts: List[str] = []
        agg_stderr_parts: List[str] = []
        agg_target_summaries: Dict[str, Dict[str, Any]] = {}

        for t_dir in targets_for_guard:
            py_count = len(
                [f for f in t_dir.rglob("*.py") if "__pycache__" not in f.parts]
            )
            proc_ast = run_sub_fn(
                [sys_mod.executable, "-B", str(guard_script), "--target", str(t_dir)],
                cwd=sb_dir,
                env=env,
                timeout_sec=min(timeout_sec, 60.0),
            )
            agg_files_checked += py_count
            t_passed = proc_ast.returncode == 0
            if not t_passed:
                agg_passed = False
                if agg_exit == 0:
                    agg_exit = proc_ast.returncode
                fail_lines = [
                    ln
                    for ln in (proc_ast.stdout or "").splitlines()
                    if ln.strip().startswith("- [")
                ]
                agg_violations += max(1, len(fail_lines))
            t_out = proc_ast.stdout or ""
            agg_target_summaries[t_dir.name] = {
                "passed": t_passed,
                "exit_code": proc_ast.returncode,
                "files_checked": py_count,
                "stdout_tail": t_out[-2000:],
            }
            if t_out:
                agg_stdout_parts.append(f"[{t_dir.name}] {t_out}")
            if proc_ast.stderr:
                agg_stderr_parts.append(proc_ast.stderr)

        combined_out = "\n".join(agg_stdout_parts)
        combined_err = "\n".join(agg_stderr_parts)
        return {
            "executed": True,
            "passed": agg_passed,
            "exit_code": agg_exit,
            "files_checked": agg_files_checked,
            "violations": agg_violations,
            "targets_scanned": [str(t) for t in targets_for_guard],
            "target_summaries": agg_target_summaries,
            "stdout": combined_out[-4000:],
            "stderr": combined_err[-1500:],
            "stdout_tail": combined_out[-4000:],
            "stderr_tail": combined_err[-1500:],
        }
    except Exception as exc:
        return {
            "executed": True,
            "passed": False,
            "exit_code": -1,
            "files_checked": 0,
            "violations": 1,
            "error": str(exc),
            "stdout_tail": "",
            "stderr_tail": str(exc)[-1500:],
        }


def _run_pytest_on_sandbox(
    sb_dir: Path,
    env: Dict[str, str],
    timeout_sec: float,
    run_sub_fn: Any,
    sys_mod: Any,
    time_mod: Any,
) -> Dict[str, Any]:
    """Esegue pytest isolato nella sandbox con gate anti-gaming su zero test raccolti."""
    tests_dir = sb_dir / "tests"
    if not tests_dir.exists():
        return {
            "executed": True,
            "passed": False,
            "exit_code": 5,
            "no_tests_collected": True,
            "error": "Cartella tests rimossa o nessun test raccolto (exit code 5)",
            "stdout_tail": "",
            "stderr_tail": "",
        }
    try:
        pt_t0 = time_mod.perf_counter()
        proc_pt = run_sub_fn(
            [
                sys_mod.executable,
                "-B",
                "-m",
                "pytest",
                "tests",
                "-p",
                "no:cacheprovider",
                "-q",
                "--tb=short",
            ],
            cwd=sb_dir,
            env=env,
            timeout_sec=timeout_sec,
        )
        pt_duration = time_mod.perf_counter() - pt_t0
        pt_combined = f"{proc_pt.stdout or ''}\n{proc_pt.stderr or ''}"
        m_pass = re.search(r"(\d+)\s+passed", pt_combined)
        m_fail = re.search(r"(\d+)\s+failed", pt_combined)
        m_err = re.search(r"(\d+)\s+errors?", pt_combined)
        m_skip = re.search(r"(\d+)\s+skipped", pt_combined)
        m_xfail = re.search(r"(\d+)\s+xfailed", pt_combined)
        pt_passed_cnt = int(m_pass.group(1)) if m_pass else 0
        pt_skipped_cnt = (int(m_skip.group(1)) if m_skip else 0) + (
            int(m_xfail.group(1)) if m_xfail else 0
        )
        pt_failed_cnt = (
            (int(m_fail.group(1)) if m_fail else 0)
            + (int(m_err.group(1)) if m_err else 0)
            + pt_skipped_cnt
        )
        if proc_pt.returncode != 0 and pt_failed_cnt == 0:
            pt_failed_cnt = 1
        pt_total_cnt = pt_passed_cnt + pt_failed_cnt
        no_tests = proc_pt.returncode == 5 or pt_total_cnt == 0
        pt_passed = (
            proc_pt.returncode == 0
            and not no_tests
            and pt_skipped_cnt == 0
            and pt_passed_cnt > 0
        )
        res: Dict[str, Any] = {
            "executed": True,
            "passed": pt_passed,
            "exit_code": proc_pt.returncode,
            "no_tests_collected": no_tests,
            "tests_passed": pt_passed_cnt,
            "tests_failed": pt_failed_cnt,
            "tests_skipped": pt_skipped_cnt,
            "tests_total": pt_total_cnt,
            "duration_s": round(pt_duration, 3),
            "stdout": proc_pt.stdout[-2000:],
            "stderr": proc_pt.stderr[-1000:],
            "stdout_tail": proc_pt.stdout[-1500:],
            "stderr_tail": proc_pt.stderr[-1500:],
        }
        if no_tests:
            res["error"] = (
                "Pytest exit code 5: nessun test raccolto (anti-gaming gate)"
            )
        return res
    except Exception as exc:
        return {
            "executed": True,
            "passed": False,
            "exit_code": -1,
            "error": str(exc),
            "stdout_tail": "",
            "stderr_tail": str(exc)[-1500:],
        }


def run_staging_shadow_verification(
    repo_root: Path | str,
    staging_dir: Optional[Path | str] = None,
    timeout_sec: float = 120.0,
    run_pytest: bool = True,
    run_ast_guard: bool = True,
    profile: str = "builder",
) -> Dict[str, Any]:
    """Copia il progetto in Shadow Sandbox, sovrappone .staging/ ed esegue AST Guard e pytest."""
    time_mod = _facade_attr("time", time)
    sys_mod = _facade_attr("sys", sys)
    sandbox_cls = _facade_attr("ShadowSandbox", ShadowSandbox)
    run_sub_fn = _facade_attr(
        "_run_job_isolated_subprocess", _run_job_isolated_subprocess
    )
    write_rep_fn = _facade_attr("write_atomic_dast_report", write_atomic_dast_report)
    env_fn = _facade_attr("_build_sanitized_sandbox_env", _build_sanitized_sandbox_env)

    t0 = time_mod.perf_counter()
    root = Path(repo_root).resolve()
    if not root.exists():
        return {
            "status": "FAIL",
            "passed": False,
            "repo_root": str(root),
            "error": f"Root directory non trovata: {root}",
            "duration_sec": 0.0,
        }

    stg = (
        Path(staging_dir).resolve()
        if staging_dir is not None
        else (root / ".staging").resolve()
    )
    ast_guard_res: Dict[str, Any] = {"executed": False, "passed": True}
    pytest_res: Dict[str, Any] = {"executed": False, "passed": True}
    sb_id = ""
    sb_dir_str = ""
    norm_prof = profile.strip().lower()
    overlay_files: List[str] = []
    deleted_applied: List[str] = []
    stripped_holdouts: List[str] = []

    with sandbox_cls() as sb:
        sb_id = sb.sandbox_id
        sb_dir_str = str(sb.sandbox_dir)
        overlay_files, deleted_applied, stripped_holdouts = prepare_staging_overlay(
            root, stg, sb, norm_prof
        )

        env = env_fn()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(sb.sandbox_dir)

        if run_ast_guard:
            ast_guard_res = _run_ast_guard_on_sandbox(
                sb.sandbox_dir, env, timeout_sec, run_sub_fn, sys_mod
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
    if not overall_passed:
        combined_stdout = "\n".join(
            p
            for p in (
                str(ast_guard_res.get("stdout", "")),
                str(pytest_res.get("stdout", "")),
            )
            if p
        )
        combined_stderr = "\n".join(
            p
            for p in (
                str(ast_guard_res.get("stderr", "")),
                str(ast_guard_res.get("error", "")),
                str(pytest_res.get("stderr", "")),
                str(pytest_res.get("error", "")),
            )
            if p
        )
        report_payload["stdout_tail"] = combined_stdout[-1500:]
        report_payload["stderr_tail"] = combined_stderr[-1500:]

    try:
        diag_dir = Path(tempfile.gettempdir()) / "nk_diagnostics"
        unique_diag_path = write_rep_fn(report_payload, diag_dir)
        report_payload["report_file"] = str(unique_diag_path)
        write_rep_fn(
            report_payload,
            diag_dir,
            explicit_output=diag_dir / "dast_last_report.json",
        )
    except Exception:
        pass

    return report_payload

"""Esecuzione sottoprocessi Job-isolated, scrittura atomica report e trace harness."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from _internal.nk_common.io import atomic_write_json

from .constants import CREATE_SUSPENDED, _facade_attr, win32_detached_flags
from .sandbox_fs import _resolve_confined_sandbox_path
from .win32_job import (
    _assign_pid_to_job,
    _close_job_handle_safe,
    _create_kill_on_close_job,
    _resume_process_primary_thread,
    _terminate_process_tree_fallback,
)


def resolve_dast_report_path(
    target_dir: Path | str, explicit_output: Optional[Path | str] = None
) -> Path:
    """Risolve il percorso del report usando dast_report_<uuid8>.json quando non esplicito."""
    if explicit_output is not None:
        raw_str = str(explicit_output).strip()
        if raw_str:
            out_p = Path(raw_str)
            if (out_p.exists() and out_p.is_dir()) or raw_str.endswith(("/", "\\")):
                return out_p / f"dast_report_{uuid.uuid4().hex[:8]}.json"
            return out_p
    return Path(target_dir) / f"dast_report_{uuid.uuid4().hex[:8]}.json"


def write_atomic_dast_report(
    payload: Dict[str, Any],
    target_dir: Path | str,
    explicit_output: Optional[Path | str] = None,
) -> Path:
    """Scrive atomicamente il report JSON DAST prevenendo collisioni concorrenti."""
    final_path = resolve_dast_report_path(target_dir, explicit_output=explicit_output)
    write_fn = _facade_attr("atomic_write_json", atomic_write_json)
    ok, err_msg = write_fn(final_path, payload, indent=2, ensure_ascii=False)
    if not ok:
        raise OSError(f"Scrittura report DAST fallita su {final_path}: {err_msg}")
    return final_path


def _run_job_isolated_subprocess(
    cmd: Sequence[str],
    cwd: Path,
    env: Dict[str, str],
    timeout_sec: float,
) -> subprocess.CompletedProcess[str]:
    """Esegue un sottoprocesso sincrono con CREATE_SUSPENDED e Job Object Win32 detached."""
    sys_mod = _facade_attr("sys", sys)
    sub_mod = _facade_attr("subprocess", subprocess)
    create_job_fn = _facade_attr("_create_kill_on_close_job", _create_kill_on_close_job)
    assign_job_fn = _facade_attr("_assign_pid_to_job", _assign_pid_to_job)
    resume_fn = _facade_attr("_resume_process_primary_thread", _resume_process_primary_thread)
    close_job_fn = _facade_attr("_close_job_handle_safe", _close_job_handle_safe)
    term_fallback_fn = _facade_attr("_terminate_process_tree_fallback", _terminate_process_tree_fallback)

    is_win = sys_mod.platform == "win32"
    detached_flags = win32_detached_flags() if is_win else 0
    suspended_flags = win32_detached_flags(CREATE_SUSPENDED) if is_win else 0
    devnull_in = getattr(sub_mod, "DEVNULL", subprocess.DEVNULL)

    job_handle = create_job_fn() if is_win else None
    if job_handle is not None:
        proc = sub_mod.Popen(
            list(cmd), cwd=str(cwd), env=env, stdin=devnull_in,
            stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=suspended_flags,
        )
        assigned = bool(proc.pid and assign_job_fn(job_handle, proc.pid))
        if not assigned:
            close_job_fn(job_handle)
            job_handle = None
        resumed = bool(proc.pid and resume_fn(proc.pid))
        if not resumed:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass
            close_job_fn(job_handle)
            job_handle = None
            proc = sub_mod.Popen(
                list(cmd), cwd=str(cwd), env=env, stdin=devnull_in,
                stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=detached_flags,
            )
    else:
        proc = sub_mod.Popen(
            list(cmd), cwd=str(cwd), env=env, stdin=devnull_in,
            stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=detached_flags,
        )

    try:
        out_str, err_str = proc.communicate(timeout=timeout_sec)
        return sub_mod.CompletedProcess(
            args=list(cmd),
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=out_str,
            stderr=err_str,
        )
    except sub_mod.TimeoutExpired:
        if is_win and proc.pid:
            try:
                sub_mod.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdin=devnull_in,
                    stdout=sub_mod.DEVNULL,
                    stderr=sub_mod.DEVNULL,
                    creationflags=detached_flags,
                    timeout=2.0,
                )
            except Exception:
                term_fallback_fn(proc.pid)
        try:
            proc.kill()
        except Exception:
            pass
        raise
    finally:
        close_job_fn(job_handle)


def _generate_trace_harness_script() -> str:
    """Genera lo script Python per la raccolta deterministica delle tracce di riga."""
    return '''"""
Harness di tracciamento deterministico per NK Hub Generation.
"""
import os
import sys
import json
import trace
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: python _nk_trace_harness.py <coverage_out_json> <target_script> [args...]\\n")
        sys.exit(1)

    cov_out_path = Path(sys.argv[1]).resolve()
    target_script = Path(sys.argv[2]).resolve()
    target_args = sys.argv[2:]

    sys.argv = target_args
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])

    try:
        with open(target_script, "rb") as f:
            code = compile(f.read(), str(target_script), "exec")

        global_dict = {"__name__": "__main__", "__file__": str(target_script)}
        tracer.runctx(code, global_dict, global_dict)
    finally:
        results = tracer.results()
        counts = results.counts

        trace_data = []
        target_name = os.environ.get("_NK_TRACE_TARGET_NAME") or target_script.name

        for (filename, lineno), count in counts.items():
            fpath = Path(filename).resolve()
            if fpath == target_script or fpath.name == target_name:
                trace_data.append({
                    "file_name": fpath.name,
                    "line_number": int(lineno),
                    "execution_count": int(count)
                })

        cov_out_path.write_text(json.dumps(trace_data), encoding="utf-8")

if __name__ == "__main__":
    main()
'''


def build_traced_command(
    sandbox_dir: Path,
    raw_cmd: List[str],
    target_script_name: Optional[str],
    trace_coverage: bool,
    env: Dict[str, str],
    cov_out_file: Path,
) -> List[str]:
    """Avvolge il comando nell'harness trace.Trace quando trace_coverage e target sono attivi."""
    if not (trace_coverage and target_script_name):
        return list(raw_cmd)

    sys_mod = _facade_attr("sys", sys)
    resolve_fn = _facade_attr("_resolve_confined_sandbox_path", _resolve_confined_sandbox_path)
    gen_fn = _facade_attr("_generate_trace_harness_script", _generate_trace_harness_script)

    is_py_cmd = False
    py_arg_idx = 0
    if raw_cmd:
        first_norm = os.path.normcase(raw_cmd[0])
        py_norm = os.path.normcase(sys_mod.executable)
        is_py_cmd = first_norm == py_norm or Path(raw_cmd[0]).stem.lower().startswith("python")
        if is_py_cmd:
            py_arg_idx = 1
            while py_arg_idx < len(raw_cmd) and raw_cmd[py_arg_idx] in ("-u", "-B", "-O", "-E", "-s", "-S", "-I"):
                py_arg_idx += 1

    harness_path = resolve_fn(sandbox_dir, "_nk_trace_harness.py")
    if not harness_path.exists():
        harness_path.write_text(gen_fn(), encoding="utf-8")

    env["_NK_TRACE_TARGET_NAME"] = Path(target_script_name).name
    entry_script_path = resolve_fn(sandbox_dir, target_script_name)
    extra_args: List[str] = []

    if is_py_cmd:
        tail_args = raw_cmd[py_arg_idx:]
        if tail_args:
            cand_first = tail_args[0]
            cand_sb = sandbox_dir / cand_first
            if cand_first == target_script_name or Path(cand_first).name == Path(target_script_name).name:
                extra_args = tail_args[1:]
            elif cand_first.endswith(".py") or cand_sb.is_file():
                entry_script_path = Path(cand_first) if Path(cand_first).is_absolute() else resolve_fn(sandbox_dir, cand_first)
                extra_args = tail_args[1:]
            else:
                extra_args = tail_args
    elif raw_cmd:
        if raw_cmd[0] == target_script_name or Path(raw_cmd[0]).name == Path(target_script_name).name:
            extra_args = raw_cmd[1:]
        elif raw_cmd[0].endswith(".py"):
            entry_script_path = Path(raw_cmd[0]) if Path(raw_cmd[0]).is_absolute() else resolve_fn(sandbox_dir, raw_cmd[0])
            extra_args = raw_cmd[1:]
        else:
            extra_args = raw_cmd

    return [sys_mod.executable, "-B", str(harness_path), str(cov_out_file), str(entry_script_path)] + extra_args

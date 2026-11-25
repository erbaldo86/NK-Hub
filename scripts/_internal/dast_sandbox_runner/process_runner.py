"""Esecuzione sottoprocessi Job-isolated, scrittura atomica report e trace harness."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


def _close_handle_ref(handle_ref: List[Optional[int]], close_job_fn: Any) -> None:
    """Chiude l'handle Job Object Win32 una sola volta azzerando il riferimento."""
    h_job = handle_ref[0]
    if h_job is not None:
        handle_ref[0] = None
        close_job_fn(h_job)


def _spawn_job_isolated_proc(
    cmd: Sequence[str],
    cwd: Path,
    env: Dict[str, str],
    handle_ref: List[Optional[int]],
    sub_mod: Any,
    devnull_in: Any,
    assign_job_fn: Any,
    resume_fn: Any,
    close_job_fn: Any,
    detached_flags: int,
    suspended_flags: int,
) -> Any:
    """Avvia il sottoprocesso in Job Object Win32 con fallback detached sicuro."""
    if handle_ref[0] is None:
        return sub_mod.Popen(
            list(cmd), cwd=str(cwd), env=env, stdin=devnull_in,
            stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=detached_flags,
        )

    proc = sub_mod.Popen(
        list(cmd), cwd=str(cwd), env=env, stdin=devnull_in,
        stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=suspended_flags,
    )
    try:
        assigned = bool(proc.pid and assign_job_fn(handle_ref[0], proc.pid))
        if not assigned:
            _close_handle_ref(handle_ref, close_job_fn)
        resumed = bool(proc.pid and resume_fn(proc.pid))
    except Exception:
        try:
            proc.kill()
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
            pass
        raise

    if not resumed:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
            pass
        _close_handle_ref(handle_ref, close_job_fn)
        return sub_mod.Popen(
            list(cmd), cwd=str(cwd), env=env, stdin=devnull_in,
            stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=detached_flags,
        )
    return proc


def _kill_timed_out_job_proc(
    proc: Any,
    is_win: bool,
    sub_mod: Any,
    devnull_in: Any,
    detached_flags: int,
    term_fallback_fn: Any,
) -> None:
    """Termina l'albero di processi in caso di TimeoutExpired."""
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
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
            term_fallback_fn(proc.pid)
    try:
        proc.kill()
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        pass


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

    handle_ref: List[Optional[int]] = [None]
    proc: Any = None
    completed = False
    try:
        handle_ref[0] = create_job_fn() if is_win else None
        proc = _spawn_job_isolated_proc(
            cmd, cwd, env, handle_ref, sub_mod, devnull_in,
            assign_job_fn, resume_fn, close_job_fn,
            detached_flags, suspended_flags,
        )
        out_str, err_str = proc.communicate(timeout=timeout_sec)
        completed = True
        return sub_mod.CompletedProcess(
            args=list(cmd),
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=out_str,
            stderr=err_str,
        )
    except sub_mod.TimeoutExpired:
        if proc is not None:
            _kill_timed_out_job_proc(
                proc, is_win, sub_mod, devnull_in, detached_flags, term_fallback_fn
            )
        raise
    finally:
        if not completed and proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        _close_handle_ref(handle_ref, close_job_fn)


def _generate_trace_harness_script() -> str:
    """Genera lo script Python con PEP 669 sys.monitoring (e fallback trace.Trace < 3.12)."""
    return '''"""Harness di tracciamento deterministico NK Hub (PEP 669 + fallback trace.Trace)."""
import json, os, sys
from pathlib import Path

def _run_with_monitoring(code, global_dict, target_script, target_exact, sandbox_root, counts):
    mon = getattr(sys, "monitoring", None)
    if mon is None or sys.version_info < (3, 12):
        return False
    tool_id = None
    for cand in (4, 3, 5, 1, 2):
        try:
            if mon.get_tool(cand) is None:
                mon.use_tool_id(cand, "nk_dast_trace")
                tool_id = cand
                break
        except ValueError:
            continue
    if tool_id is None:
        return False
    name_cache, disable_tok = {}, getattr(mon, "DISABLE", None)
    def _on_line(code_obj, lineno):
        fn = getattr(code_obj, "co_filename", "")
        matched = name_cache.get(fn, False)
        if matched is False:
            try:
                fpath = Path(fn).resolve() if (fn and not fn.startswith("<")) else None
                matched = fpath.relative_to(sandbox_root).as_posix() if (fpath is not None and fpath.is_relative_to(sandbox_root) and fpath in (target_exact, target_script)) else None
            except OSError:
                matched = None
            name_cache[fn] = matched
        if matched is not None and isinstance(lineno, int) and lineno >= 1:
            key = (matched, lineno)
            counts[key] = counts.get(key, 0) + 1
            return None
        return disable_tok
    try:
        mon.register_callback(tool_id, mon.events.LINE, _on_line)
        mon.set_events(tool_id, mon.events.LINE)
        exec(code, global_dict, global_dict)
    finally:
        for fn_call in (
            lambda: mon.set_events(tool_id, 0),
            lambda: mon.register_callback(tool_id, mon.events.LINE, None),
            lambda: mon.free_tool_id(tool_id),
        ):
            try:
                fn_call()
            except Exception:
                pass
    return True

def _run_with_trace(code, global_dict, target_script, target_exact, sandbox_root, counts):
    import trace
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    try:
        tracer.runctx(code, global_dict, global_dict)
    finally:
        for (filename, lineno), count in tracer.results().counts.items():
            try:
                fpath = Path(filename).resolve() if (filename and not filename.startswith("<")) else None
            except OSError:
                continue
            if fpath is not None and fpath.is_relative_to(sandbox_root) and fpath in (target_exact, target_script):
                key = (fpath.relative_to(sandbox_root).as_posix(), int(lineno))
                counts[key] = counts.get(key, 0) + int(count)

def main():
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: python _nk_trace_harness.py <coverage_out_json> <target_script> [args...]\\n")
        sys.exit(1)
    cov_out_path, target_script = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    sys.argv = sys.argv[2:]
    raw_sb, raw_tgt = os.environ.pop("_NK_TRACE_SANDBOX_ROOT", ""), os.environ.pop("_NK_TRACE_TARGET_PATH", "")
    sandbox_root = Path(raw_sb).resolve() if raw_sb else target_script.parent
    cand_tgt = Path(raw_tgt).resolve() if raw_tgt else target_script
    target_exact = cand_tgt if cand_tgt.is_relative_to(sandbox_root) else target_script
    if not target_script.is_relative_to(sandbox_root):
        target_script = target_exact
    dumps_fn, out_writer, counts = json.dumps, cov_out_path.write_text, {}
    with open(target_script, "rb") as f:
        code = compile(f.read(), str(target_script), "exec")
    global_dict = {"__name__": "__main__", "__file__": str(target_script)}
    try:
        if not _run_with_monitoring(code, global_dict, target_script, target_exact, sandbox_root, counts):
            _run_with_trace(code, global_dict, target_script, target_exact, sandbox_root, counts)
    finally:
        trace_data = [
            {"file_name": fname, "line_number": int(lineno), "execution_count": int(cnt)}
            for (fname, lineno), cnt in sorted(counts.items())
            if int(cnt) >= 1
        ]
        out_writer(dumps_fn(trace_data), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


def _resolve_traced_entry_arg(sandbox_dir: Path, raw_arg: str, resolve_fn: Any) -> Path:
    """Confina sempre lo script di ingresso del trace harness dentro sandbox_dir."""
    cand = Path(raw_arg)
    if cand.is_absolute():
        sb_root = sandbox_dir.resolve()
        cand_resolved = cand.resolve()
        if cand_resolved.is_relative_to(sb_root) and cand_resolved != sb_root:
            return resolve_fn(sandbox_dir, cand_resolved.relative_to(sb_root).as_posix())
    return resolve_fn(sandbox_dir, raw_arg)


def _extract_traced_entry_and_args(
    sandbox_dir: Path,
    args_seq: List[str],
    default_entry: Path,
    target_script_name: str,
    check_existing: bool,
    resolve_fn: Any,
) -> Tuple[Path, List[str]]:
    """Estrae e confina lo script di ingresso dagli argomenti del comando tracciato."""
    if not args_seq:
        return default_entry, []
    first = args_seq[0]
    if first.startswith("-"):
        return default_entry, args_seq
    if first == target_script_name:
        return default_entry, args_seq[1:]
    if first.endswith(".py"):
        return _resolve_traced_entry_arg(sandbox_dir, first, resolve_fn), args_seq[1:]
    if check_existing:
        try:
            cand_resolved = _resolve_traced_entry_arg(sandbox_dir, first, resolve_fn)
        except ValueError:
            return default_entry, args_seq
        if cand_resolved.is_file():
            return cand_resolved, args_seq[1:]
    return default_entry, args_seq


def build_traced_command(
    sandbox_dir: Path,
    raw_cmd: List[str],
    target_script_name: Optional[str],
    trace_coverage: bool,
    env: Dict[str, str],
    cov_out_file: Path,
) -> List[str]:
    """Avvolge il comando nell'harness PEP 669/trace.Trace quando trace_coverage e target sono attivi."""
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

    target_exact = resolve_fn(sandbox_dir, target_script_name).resolve()
    env["_NK_TRACE_TARGET_PATH"] = str(target_exact)
    env["_NK_TRACE_SANDBOX_ROOT"] = str(sandbox_dir.resolve())
    entry_script_path = resolve_fn(sandbox_dir, target_script_name)
    extra_args: List[str] = []

    if is_py_cmd:
        entry_script_path, extra_args = _extract_traced_entry_and_args(
            sandbox_dir, raw_cmd[py_arg_idx:], entry_script_path, target_script_name, True, resolve_fn,
        )
    elif raw_cmd:
        entry_script_path, extra_args = _extract_traced_entry_and_args(
            sandbox_dir, raw_cmd, entry_script_path, target_script_name, False, resolve_fn,
        )

    return [sys_mod.executable, "-B", str(harness_path), str(cov_out_file), str(entry_script_path)] + extra_args

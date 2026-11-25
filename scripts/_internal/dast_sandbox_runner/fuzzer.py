"""Runner asincrono DASTSandboxRunner con Job Object Win32 e watchdog RSS."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, List, Optional, Sequence

from .constants import (
    CREATE_SUSPENDED,
    DAST_MAX_OUTPUT_BYTES,
    CoverageTraceItem,
    SandboxConfig,
    SandboxTelemetryReport,
    _RSSMonitorState,
    _facade_attr,
    win32_detached_flags,
)
from .process_runner import build_traced_command
from .sandbox_fs import (
    ShadowSandbox,
    _build_sanitized_sandbox_env,
    _strip_builder_holdouts_from_sandbox,
    _truncate_utf8_bytes,
)
from .win32_job import (
    _HAS_PSUTIL,
    _assign_pid_to_job,
    _close_job_handle_safe,
    _create_kill_on_close_job,
    _get_process_memory_rss,
    _resume_process_primary_thread,
    _terminate_process_tree_fallback,
    psutil,
)


def _parse_coverage_traces(
    cov_out_file: Any,
) -> tuple[List[CoverageTraceItem], List[str]]:
    """Carica e ordina in modo deterministico le tracce coverage emesse dall'harness."""
    if not cov_out_file.exists():
        return [], []
    statement_traces: List[CoverageTraceItem] = []
    executed_statements: List[str] = []
    try:
        raw_cov = json.loads(cov_out_file.read_text(encoding="utf-8"))
        for item in raw_cov:
            trace_item = CoverageTraceItem(
                file_name=item["file_name"],
                line_number=item["line_number"],
                execution_count=item["execution_count"],
            )
            statement_traces.append(trace_item)
            executed_statements.append(trace_item.statement_id)
        executed_statements = sorted(set(executed_statements))
        statement_traces.sort(key=lambda x: (x.file_name, x.line_number))
    except Exception:
        return [], []
    return statement_traces, executed_statements


def _resolve_sandbox_pythonpath(
    sandbox_dir: Path,
    existing_pypath: str,
    is_builder_profile: bool,
) -> str:
    """Costruisce PYTHONPATH includendo la radice sandbox e preservando solo path confinati in builder."""
    sandbox_path_str = str(sandbox_dir)
    if not is_builder_profile:
        return (
            f"{sandbox_path_str}{os.pathsep}{existing_pypath}"
            if existing_pypath
            else sandbox_path_str
        )
    sb_resolved = sandbox_dir.resolve()
    confined_parts: List[str] = [sandbox_path_str]
    for raw_part in existing_pypath.split(os.pathsep):
        part = raw_part.strip()
        if not part:
            continue
        try:
            p_res = Path(part).resolve()
        except OSError:
            continue
        if p_res == sb_resolved or p_res.is_relative_to(sb_resolved):
            p_str = str(p_res)
            if p_str not in confined_parts:
                confined_parts.append(p_str)
    return os.pathsep.join(confined_parts)


class DASTSandboxRunner:
    """Esegue codice reale dentro una ShadowSandbox con controllo di tempo e memoria."""

    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        self.config = config or SandboxConfig()
        self._rss_lock = threading.Lock()
        self._last_peak_memory_bytes: int = 0

    async def run_in_sandbox(
        self,
        sandbox: ShadowSandbox,
        command: Sequence[str],
        target_script_name: Optional[str] = None,
    ) -> SandboxTelemetryReport:
        """Avvia il comando nella sandbox e raccoglie le metriche isolate di esecuzione."""
        if not sandbox._is_active:
            sandbox.create()

        sys_mod = _facade_attr("sys", sys)
        asyncio_mod = _facade_attr("asyncio", asyncio)
        time_mod = _facade_attr("time", time)
        has_psutil = _facade_attr("_HAS_PSUTIL", _HAS_PSUTIL)
        psutil_mod = _facade_attr("psutil", psutil)
        create_job_fn = _facade_attr("_create_kill_on_close_job", _create_kill_on_close_job)
        assign_job_fn = _facade_attr("_assign_pid_to_job", _assign_pid_to_job)
        resume_fn = _facade_attr("_resume_process_primary_thread", _resume_process_primary_thread)
        close_job_fn = _facade_attr("_close_job_handle_safe", _close_job_handle_safe)
        get_rss_fn = _facade_attr("_get_process_memory_rss", _get_process_memory_rss)
        strip_fn = _facade_attr("_strip_builder_holdouts_from_sandbox", _strip_builder_holdouts_from_sandbox)
        env_fn = _facade_attr("_build_sanitized_sandbox_env", _build_sanitized_sandbox_env)

        is_builder_profile = self.config.profile.strip().lower() == "builder"
        if is_builder_profile:
            strip_fn(sandbox.sandbox_dir)

        env = env_fn(self.config.env_vars)
        env["PYTHONPATH"] = _resolve_sandbox_pythonpath(
            sandbox.sandbox_dir, env.get("PYTHONPATH", ""), is_builder_profile
        )

        raw_cmd = list(command)
        cov_out_file = sandbox.sandbox_dir / "_nk_coverage_out.json"
        actual_cmd = build_traced_command(
            sandbox.sandbox_dir, raw_cmd, target_script_name, self.config.trace_coverage, env, cov_out_file,
        )

        start_time = time_mod.perf_counter()
        rss_state = _RSSMonitorState()
        timed_out = False
        memory_exceeded = False

        is_win = sys_mod.platform == "win32"
        detached_flags = win32_detached_flags() if is_win else 0
        suspended_flags = win32_detached_flags(CREATE_SUSPENDED) if is_win else 0
        devnull_in = getattr(asyncio_mod.subprocess, "DEVNULL", subprocess.DEVNULL)

        job_handle = create_job_fn() if is_win else None
        if job_handle is not None:
            proc = await asyncio_mod.create_subprocess_exec(
                *actual_cmd, cwd=str(sandbox.sandbox_dir), stdin=devnull_in,
                stdout=asyncio_mod.subprocess.PIPE, stderr=asyncio_mod.subprocess.PIPE,
                env=env, creationflags=suspended_flags,
            )
            pid = proc.pid
            assigned = bool(pid and assign_job_fn(job_handle, pid))
            if not assigned:
                close_job_fn(job_handle)
                job_handle = None
            resumed = bool(pid and resume_fn(pid))
            if not resumed:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                close_job_fn(job_handle)
                job_handle = None
                start_time = time_mod.perf_counter()
                proc = await asyncio_mod.create_subprocess_exec(
                    *actual_cmd, cwd=str(sandbox.sandbox_dir), stdin=devnull_in,
                    stdout=asyncio_mod.subprocess.PIPE, stderr=asyncio_mod.subprocess.PIPE,
                    env=env, creationflags=detached_flags,
                )
        else:
            proc = await asyncio_mod.create_subprocess_exec(
                *actual_cmd, cwd=str(sandbox.sandbox_dir), stdin=devnull_in,
                stdout=asyncio_mod.subprocess.PIPE, stderr=asyncio_mod.subprocess.PIPE,
                env=env, creationflags=detached_flags,
            )

        pid = proc.pid
        max_bytes = int(self.config.max_memory_mb * 1024 * 1024)
        watchdog_active = True

        async def _watchdog() -> None:
            nonlocal timed_out, memory_exceeded, watchdog_active
            p_process = None
            if has_psutil and psutil_mod is not None and pid:
                try:
                    p_process = psutil_mod.Process(pid)
                except Exception:
                    p_process = None

            while watchdog_active:
                await asyncio_mod.sleep(self.config.poll_interval_sec)
                if not watchdog_active:
                    break
                if has_psutil and psutil_mod is not None and p_process is None and pid:
                    try:
                        p_process = psutil_mod.Process(pid)
                    except Exception:
                        p_process = None

                elapsed = time_mod.perf_counter() - start_time
                if elapsed > self.config.timeout_sec:
                    timed_out = True
                    self._kill_process_tree(proc, p_process)
                    break

                current_mem = get_rss_fn(pid or 0, p_process, rss_state=rss_state)
                rss_state.record_sample(current_mem)
                if current_mem > max_bytes:
                    memory_exceeded = True
                    self._kill_process_tree(proc, p_process)
                    break

        watchdog_task = asyncio_mod.create_task(_watchdog())
        stdout_bytes, stderr_bytes = b"", b""
        try:
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception:
            try:
                p_proc = psutil_mod.Process(pid) if (has_psutil and psutil_mod is not None and pid) else None
                self._kill_process_tree(proc, p_proc)
            except Exception:
                p_proc = None
        finally:
            watchdog_active = False
            if not watchdog_task.done():
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio_mod.CancelledError:
                    watchdog_active = False
            close_job_fn(job_handle)

        peak_memory_bytes = rss_state.get_peak()
        with self._rss_lock:
            self._last_peak_memory_bytes = peak_memory_bytes

        duration_sec = round(time_mod.perf_counter() - start_time, 6)
        exit_code = proc.returncode if proc.returncode is not None else -1
        statement_traces, executed_statements = _parse_coverage_traces(cov_out_file)
        success = (exit_code == 0) and not timed_out and not memory_exceeded

        return SandboxTelemetryReport(
            sandbox_id=sandbox.sandbox_id, sandbox_dir=str(sandbox.sandbox_dir), command=actual_cmd,
            exit_code=exit_code, duration_sec=duration_sec, peak_memory_bytes=peak_memory_bytes,
            timed_out=timed_out, memory_exceeded=memory_exceeded,
            stdout=_truncate_utf8_bytes(stdout_bytes, DAST_MAX_OUTPUT_BYTES),
            stderr=_truncate_utf8_bytes(stderr_bytes, DAST_MAX_OUTPUT_BYTES),
            executed_statements=executed_statements, statement_traces=statement_traces, success=success,
        )

    def _kill_process_tree(
        self,
        proc: Optional[asyncio.subprocess.Process] = None,
        parent: Optional[Any] = None,
        children: Optional[List[Any]] = None,
    ) -> None:
        """Termina l'intero albero dei processi partendo da taskkill /F /T."""
        sys_mod = _facade_attr("sys", sys)
        sub_mod = _facade_attr("subprocess", subprocess)
        has_psutil = _facade_attr("_HAS_PSUTIL", _HAS_PSUTIL)
        psutil_mod = _facade_attr("psutil", psutil)
        term_fallback_fn = _facade_attr("_terminate_process_tree_fallback", _terminate_process_tree_fallback)

        target_pid = None
        if proc is not None and proc.pid:
            target_pid = proc.pid
        elif parent is not None and hasattr(parent, "pid"):
            target_pid = parent.pid

        if sys_mod.platform == "win32" and target_pid:
            try:
                sub_mod.run(
                    ["taskkill", "/F", "/T", "/PID", str(target_pid)],
                    stdin=getattr(sub_mod, "DEVNULL", subprocess.DEVNULL),
                    stdout=sub_mod.DEVNULL,
                    stderr=sub_mod.DEVNULL,
                    creationflags=win32_detached_flags(),
                    timeout=2.0,
                )
            except Exception:
                term_fallback_fn(target_pid)
                target_pid = None

        if has_psutil and psutil_mod is not None and parent is not None:
            for p in (children or []) + [parent]:
                try:
                    p.kill()
                except Exception:
                    continue

        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except (ProcessLookupError, PermissionError, OSError, Exception):
                return

    def kill_process_tree(
        self,
        proc: Optional[asyncio.subprocess.Process] = None,
        parent: Optional[Any] = None,
        children: Optional[List[Any]] = None,
    ) -> bool:
        """Termina in modo idempotente l'albero dei processi gestendo gli errori di sistema."""
        try:
            self._kill_process_tree(proc=proc, parent=parent, children=children)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        return True

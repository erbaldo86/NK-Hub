"""
DAST Sandbox Runner - Isolated Shadow Sandbox & Zero-Mock Dynamic Execution
Nexus Keystone v1.1.0-Universal | Grand Master Brief Node 2

Implements:
- Isolated Shadow Sandbox allocator in %TEMP%\\nk_sandbox_<uuid>\\
- Zero-Mock real test runner execution in isolated environment.
- Asynchronous psutil watchdog with recursive process-tree termination on timeout (hard ceiling 10.0s).
- Taskkill /F /T pre-kill sequence to eliminate zombie descendant trees.
- Comprehensive telemetry collection: exit code, duration, peak memory RSS, statement trace coverage.
- Pydantic v2 Strict Mode reporting.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False
from pydantic import BaseModel, ConfigDict, Field


class SandboxConfig(BaseModel):
    """
    Configuration options for Shadow Sandbox execution.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    timeout_sec: float = Field(default=10.0, gt=0.0, le=60.0, description="Hard ceiling timeout in seconds")
    poll_interval_sec: float = Field(default=0.025, gt=0.0, le=0.5, description="Watchdog polling interval in seconds")
    max_memory_mb: float = Field(default=512.0, gt=0.0, description="Maximum RSS memory threshold in MB")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    trace_coverage: bool = Field(default=True, description="Enable statement-level trace coverage collection")


class CoverageTraceItem(BaseModel):
    """
    Statement execution trace item.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    file_name: str
    line_number: int = Field(ge=1)
    execution_count: int = Field(ge=1)

    @property
    def statement_id(self) -> str:
        return f"{self.file_name}:{self.line_number}"


class SandboxTelemetryReport(BaseModel):
    """
    Deterministic telemetry report for DAST execution.
    """
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    sandbox_id: str
    sandbox_dir: str
    command: List[str]
    exit_code: int
    duration_sec: float = Field(ge=0.0)
    peak_memory_bytes: int = Field(ge=0)
    timed_out: bool
    memory_exceeded: bool
    stdout: str
    stderr: str
    executed_statements: List[str] = Field(default_factory=list)
    statement_traces: List[CoverageTraceItem] = Field(default_factory=list)
    success: bool


def _handle_remove_readonly(func: Any, path: str, exc_info: Any) -> None:
    """
    Error handler for shutil.rmtree on Windows to remove read-only attributes.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _get_process_memory_rss(pid: int, p_process: Optional[Any] = None) -> int:
    """Queries process RSS memory for the root PID and all child processes."""
    if _HAS_PSUTIL and p_process is not None:
        try:
            mem = p_process.memory_info().rss
            for child in p_process.children(recursive=True):
                try:
                    mem += child.memory_info().rss
                except Exception:
                    pass
            return mem
        except Exception:
            pass

    if sys.platform == "win32" and pid:
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260),
                ]

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pids_to_check = {pid}
            TH32CS_SNAPPROCESS = 0x00000002
            snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snap:
                try:
                    pe = PROCESSENTRY32()
                    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
                    entries = []
                    if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(pe)):
                        while True:
                            entries.append((pe.th32ProcessID, pe.th32ParentProcessID))
                            if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(pe)):
                                break
                    changed = True
                    while changed:
                        changed = False
                        for c_pid, p_pid in entries:
                            if p_pid in pids_to_check and c_pid not in pids_to_check:
                                pids_to_check.add(c_pid)
                                changed = True
                finally:
                    ctypes.windll.kernel32.CloseHandle(snap)

            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            total_rss = 0

            for p in pids_to_check:
                h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, p)
                if h:
                    try:
                        counters = PROCESS_MEMORY_COUNTERS()
                        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                        try:
                            res = ctypes.windll.kernel32.K32GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb)
                        except Exception:
                            res = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb)
                        if res:
                            total_rss += int(counters.WorkingSetSize)
                    finally:
                        ctypes.windll.kernel32.CloseHandle(h)

            return total_rss
        except Exception:
            pass

    return 0


class ShadowSandbox:
    """
    Manages an isolated temporary sandbox directory in %TEMP%\\nk_sandbox_<uuid>\\.
    Ensures safe creation, isolation, file staging, and complete teardown.
    """

    def __init__(self, sandbox_id: Optional[str] = None) -> None:
        self.sandbox_id = sandbox_id or f"nk_sandbox_{uuid.uuid4().hex}"
        self.base_temp_dir = Path(tempfile.gettempdir())
        self.sandbox_dir = self.base_temp_dir / self.sandbox_id
        self._is_active = False

    def create(self) -> Path:
        """
        Creates the isolated sandbox directory.
        """
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self._is_active = True
        return self.sandbox_dir

    def write_file(self, rel_path: str, content: str | bytes, encoding: str = "utf-8") -> Path:
        """
        Writes a file into the isolated sandbox.
        """
        if not self._is_active:
            self.create()

        target_path = self.sandbox_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            target_path.write_bytes(content)
        else:
            target_path.write_text(content, encoding=encoding)

        return target_path

    def copy_file(self, src_path: Path | str, dst_rel_path: str = "") -> Path:
        """
        Copies a source file into the sandbox.
        """
        if not self._is_active:
            self.create()

        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        if dst_rel_path:
            dst = self.sandbox_dir / dst_rel_path
            if dst.is_dir() or dst_rel_path.endswith(("/", "\\")):
                dst.mkdir(parents=True, exist_ok=True)
                dst = dst / src.name
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
        else:
            dst = self.sandbox_dir / src.name

        shutil.copy2(src, dst)
        return dst

    def copy_tree(self, src_dir: Path | str, dst_rel_path: str = "") -> Path:
        """
        Recursively copies a directory tree into the sandbox.
        """
        if not self._is_active:
            self.create()

        src = Path(src_dir)
        if not src.is_dir():
            raise NotADirectoryError(f"Source directory not found: {src}")

        dst = self.sandbox_dir / dst_rel_path if dst_rel_path else self.sandbox_dir
        dst.mkdir(parents=True, exist_ok=True)

        for item in src.iterdir():
            dest_item = dst / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)

        return dst

    def cleanup(self) -> None:
        """
        Robust teardown with retries for Windows file locking.
        """
        if not self.sandbox_dir.exists():
            self._is_active = False
            return

        for attempt in range(5):
            try:
                shutil.rmtree(self.sandbox_dir, onerror=_handle_remove_readonly)
                break
            except Exception:
                time.sleep(0.05 * (attempt + 1))

        self._is_active = False

    def __enter__(self) -> ShadowSandbox:
        self.create()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    async def __aenter__(self) -> ShadowSandbox:
        self.create()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()


def _generate_trace_harness_script() -> str:
    """
    Generates python execution tracer harness code to capture real line traces deterministically.
    """
    return '''"""
NK Trace Harness - Deterministic Line Tracer
"""
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

    # Prepare sys.argv for the target script
    sys.argv = target_args

    # Setup tracer
    tracer = trace.Trace(count=True, trace=False)

    try:
        with open(target_script, "rb") as f:
            code = compile(f.read(), str(target_script), "exec")
        
        # Execute target under trace
        global_dict = {"__name__": "__main__", "__file__": str(target_script)}
        tracer.runctx(code, global_dict)
    finally:
        # Extract statement counts
        results = tracer.results()
        counts = results.counts  # Dict[(filename, lineno), count]
        
        trace_data = []
        target_name = target_script.name
        
        for (filename, lineno), count in counts.items():
            fpath = Path(filename).resolve()
            # Include files belonging to the sandbox / target script
            if fpath == target_script or fpath.name == target_name:
                trace_data.append({
                    "file_name": target_name,
                    "line_number": int(lineno),
                    "execution_count": int(count)
                })
        
        cov_out_path.write_text(json.dumps(trace_data), encoding="utf-8")

if __name__ == "__main__":
    main()
'''


class DASTSandboxRunner:
    """
    DAST Runner that executes real code/tests inside a ShadowSandbox with an asynchronous watchdog.
    """

    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        self.config = config or SandboxConfig()

    async def run_in_sandbox(
        self,
        sandbox: ShadowSandbox,
        command: Sequence[str],
        target_script_name: Optional[str] = None,
    ) -> SandboxTelemetryReport:
        """
        Executes command in sandbox with async psutil watchdog and telemetry capture.
        """
        if not sandbox._is_active:
            sandbox.create()

        env = os.environ.copy()
        env.update(self.config.env_vars)
        # Ensure python unbuffered
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        actual_cmd = list(command)
        cov_out_file = sandbox.sandbox_dir / "_nk_coverage_out.json"

        # If trace_coverage is requested and command executes Python script
        if self.config.trace_coverage and target_script_name:
            harness_path = sandbox.sandbox_dir / "_nk_trace_harness.py"
            if not harness_path.exists():
                harness_path.write_text(_generate_trace_harness_script(), encoding="utf-8")

            # Rewrite command to invoke tracer harness
            python_exe = sys.executable
            actual_cmd = [
                python_exe,
                str(harness_path),
                str(cov_out_file),
                str(sandbox.sandbox_dir / target_script_name),
            ]

        start_time = time.perf_counter()
        peak_memory_bytes = 0
        timed_out = False
        memory_exceeded = False

        # Launch subprocess
        proc = await asyncio.create_subprocess_exec(
            *actual_cmd,
            cwd=str(sandbox.sandbox_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        pid = proc.pid
        max_bytes = int(self.config.max_memory_mb * 1024 * 1024)

        # Polling Watchdog
        watchdog_active = True

        async def _watchdog() -> None:
            nonlocal peak_memory_bytes, timed_out, memory_exceeded, watchdog_active
            p_process = None
            if _HAS_PSUTIL and psutil is not None:
                try:
                    p_process = psutil.Process(pid)
                except Exception:
                    p_process = None

            while watchdog_active:
                await asyncio.sleep(self.config.poll_interval_sec)
                if not watchdog_active:
                    break

                if _HAS_PSUTIL and psutil is not None and p_process is None:
                    try:
                        p_process = psutil.Process(pid)
                    except Exception:
                        p_process = None

                elapsed = time.perf_counter() - start_time
                if elapsed > self.config.timeout_sec:
                    timed_out = True
                    self._kill_process_tree(proc, p_process)
                    break

                current_mem = _get_process_memory_rss(pid, p_process)
                if current_mem > peak_memory_bytes:
                    peak_memory_bytes = current_mem

                if current_mem > max_bytes:
                    memory_exceeded = True
                    self._kill_process_tree(proc, p_process)
                    break

        watchdog_task = asyncio.create_task(_watchdog())

        # Wait for process completion
        stdout_bytes, stderr_bytes = b"", b""
        try:
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception:
            try:
                p_proc = psutil.Process(pid) if (_HAS_PSUTIL and psutil is not None) else None
                self._kill_process_tree(proc, p_proc)
            except Exception:
                pass
        finally:
            watchdog_active = False
            if not watchdog_task.done():
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass

        duration_sec = round(time.perf_counter() - start_time, 6)
        exit_code = proc.returncode if proc.returncode is not None else -1

        # Decode output
        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        # Parse coverage trace if available
        statement_traces: List[CoverageTraceItem] = []
        executed_statements: List[str] = []

        if cov_out_file.exists():
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
                # Sort for deterministic output
                executed_statements = sorted(set(executed_statements))
                statement_traces.sort(key=lambda x: (x.file_name, x.line_number))
            except Exception:
                pass

        success = (exit_code == 0) and not timed_out and not memory_exceeded

        return SandboxTelemetryReport(
            sandbox_id=sandbox.sandbox_id,
            sandbox_dir=str(sandbox.sandbox_dir),
            command=actual_cmd,
            exit_code=exit_code,
            duration_sec=duration_sec,
            peak_memory_bytes=peak_memory_bytes,
            timed_out=timed_out,
            memory_exceeded=memory_exceeded,
            stdout=stdout_str,
            stderr=stderr_str,
            executed_statements=executed_statements,
            statement_traces=statement_traces,
            success=success,
        )

    def _kill_process_tree(
        self,
        proc: Optional[asyncio.subprocess.Process] = None,
        parent: Optional[Any] = None,
        children: Optional[List[Any]] = None,
    ) -> None:
        """
        Recursively terminates and kills process and all its children.
        Directiva 2: Inversione della sequenza con Taskkill /F /T pre-kill per eliminare
        l'intero albero di processi OS su Windows prima di proc.kill().
        """
        # Step 1: Pre-Kill via taskkill /F /T on Windows to terminate entire process tree atomically
        target_pid = None
        if proc is not None and proc.pid:
            target_pid = proc.pid
        elif parent is not None and hasattr(parent, "pid"):
            target_pid = parent.pid

        if sys.platform == "win32" and target_pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(target_pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                )
            except Exception:
                pass

        # Step 2: Terminate/Kill psutil processes
        if _HAS_PSUTIL and psutil is not None and parent is not None:
            all_procs = (children or []) + [parent]
            for p in all_procs:
                try:
                    p.kill()
                except Exception:
                    pass

        # Step 3: Ensure asyncio process handle is terminated
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass

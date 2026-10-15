# -*- coding: utf-8 -*-
"""
Esecutore DAST in Shadow Sandbox per Nexus Keystone v3.0.0-STE100-Unified.
Esegue codice reale in una cartella temporanea isolata con watchdog asincrono.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
from ctypes import wintypes
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010


class PROCESSENTRY32(ctypes.Structure):
    """Struttura Win32 per l'enumerazione dei processi nel snapshot di sistema."""

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
    """Struttura Win32 per la lettura dei contatori di memoria RSS del processo."""

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


if sys.platform == "win32":
    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p

    _kernel32.Process32First.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(PROCESSENTRY32),
    ]
    _kernel32.Process32First.restype = wintypes.BOOL

    _kernel32.Process32Next.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(PROCESSENTRY32),
    ]
    _kernel32.Process32Next.restype = wintypes.BOOL

    _kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = ctypes.c_void_p

    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = wintypes.BOOL
else:
    _kernel32 = None


class SandboxConfig(BaseModel):
    """Opzioni di configurazione per l'esecuzione nella Shadow Sandbox."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    timeout_sec: float = Field(default=10.0, gt=0.0, le=60.0)
    poll_interval_sec: float = Field(default=0.025, gt=0.0, le=0.5)
    max_memory_mb: float = Field(default=512.0, gt=0.0)
    env_vars: Dict[str, str] = Field(default_factory=dict)
    trace_coverage: bool = Field(default=True)


class CoverageTraceItem(BaseModel):
    """Singolo elemento di tracciamento dell'esecuzione per riga di codice."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    file_name: str
    line_number: int = Field(ge=1)
    execution_count: int = Field(ge=1)

    @property
    def statement_id(self) -> str:
        """Restituisce l'identificatore canonico nel formato file:riga."""
        return f"{self.file_name}:{self.line_number}"


class SandboxTelemetryReport(BaseModel):
    """Rapporto telemetrico deterministico per l'esecuzione DAST."""

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
    """Rimuove l'attributo di sola lettura durante la pulizia della sandbox."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _get_process_memory_rss(pid: int, p_process: Optional[Any] = None) -> int:
    """Calcola la memoria RSS totale per il processo radice e i suoi figli."""
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

    if sys.platform == "win32" and pid and _kernel32 is not None:
        try:
            pids_to_check = {pid}
            snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snap and snap != INVALID_HANDLE_VALUE:
                try:
                    pe = PROCESSENTRY32()
                    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
                    entries = []
                    if _kernel32.Process32First(snap, ctypes.byref(pe)):
                        while True:
                            entries.append((pe.th32ProcessID, pe.th32ParentProcessID))
                            if not _kernel32.Process32Next(snap, ctypes.byref(pe)):
                                break
                    changed = True
                    while changed:
                        changed = False
                        for c_pid, p_pid in entries:
                            if p_pid in pids_to_check and c_pid not in pids_to_check:
                                pids_to_check.add(c_pid)
                                changed = True
                finally:
                    _kernel32.CloseHandle(snap)

            total_rss = 0
            for p in pids_to_check:
                h = _kernel32.OpenProcess(
                    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                    False,
                    p,
                )
                if h and h != INVALID_HANDLE_VALUE:
                    try:
                        counters = PROCESS_MEMORY_COUNTERS()
                        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                        try:
                            res = _kernel32.K32GetProcessMemoryInfo(
                                h,
                                ctypes.byref(counters),
                                counters.cb,
                            )
                        except Exception:
                            res = ctypes.windll.psapi.GetProcessMemoryInfo(
                                h,
                                ctypes.byref(counters),
                                counters.cb,
                            )
                        if res:
                            total_rss += int(counters.WorkingSetSize)
                    finally:
                        _kernel32.CloseHandle(h)

            return total_rss
        except Exception:
            pass

    return 0


class ShadowSandbox:
    """Gestisce una cartella temporanea isolata in %TEMP%\\nk_sandbox_<uuid>\\."""

    def __init__(self, sandbox_id: Optional[str] = None) -> None:
        self.sandbox_id = sandbox_id or f"nk_sandbox_{uuid.uuid4().hex}"
        self.base_temp_dir = Path(tempfile.gettempdir())
        self.sandbox_dir = self.base_temp_dir / self.sandbox_id
        self._is_active = False

    def create(self) -> Path:
        """Crea la cartella isolata della sandbox su disco."""
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self._is_active = True
        return self.sandbox_dir

    def write_file(
        self,
        rel_path: str,
        content: str | bytes,
        encoding: str = "utf-8",
    ) -> Path:
        """Scrive un file all'interno della sandbox isolata."""
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
        """Copia un file sorgente dentro la sandbox."""
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
        """Copia ricorsivamente un albero di cartelle dentro la sandbox."""
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
        """Rimuove la cartella temporanea gestendo eventuali lock su Windows."""
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
    """Genera lo script Python per la raccolta deterministica delle tracce di riga."""
    return '''"""
Harness di tracciamento deterministico per Nexus Keystone.
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

    sys.argv = target_args
    tracer = trace.Trace(count=True, trace=False)

    try:
        with open(target_script, "rb") as f:
            code = compile(f.read(), str(target_script), "exec")

        global_dict = {"__name__": "__main__", "__file__": str(target_script)}
        tracer.runctx(code, global_dict)
    finally:
        results = tracer.results()
        counts = results.counts

        trace_data = []
        target_name = target_script.name

        for (filename, lineno), count in counts.items():
            fpath = Path(filename).resolve()
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
    """Esegue codice reale dentro una ShadowSandbox con controllo di tempo e memoria."""

    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        self.config = config or SandboxConfig()

    async def run_in_sandbox(
        self,
        sandbox: ShadowSandbox,
        command: Sequence[str],
        target_script_name: Optional[str] = None,
    ) -> SandboxTelemetryReport:
        """Avvia il comando nella sandbox e raccoglie le metriche di esecuzione."""
        if not sandbox._is_active:
            sandbox.create()

        env = os.environ.copy()
        env.update(self.config.env_vars)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        actual_cmd = list(command)
        cov_out_file = sandbox.sandbox_dir / "_nk_coverage_out.json"

        if self.config.trace_coverage and target_script_name:
            harness_path = sandbox.sandbox_dir / "_nk_trace_harness.py"
            if not harness_path.exists():
                harness_path.write_text(
                    _generate_trace_harness_script(),
                    encoding="utf-8",
                )

            python_exe = sys.executable
            extra_args = list(command[2:]) if len(command) > 2 else []
            actual_cmd = [
                python_exe,
                str(harness_path),
                str(cov_out_file),
                str(sandbox.sandbox_dir / target_script_name),
            ] + extra_args

        start_time = time.perf_counter()
        peak_memory_bytes = 0
        timed_out = False
        memory_exceeded = False

        proc = await asyncio.create_subprocess_exec(
            *actual_cmd,
            cwd=str(sandbox.sandbox_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        pid = proc.pid
        max_bytes = int(self.config.max_memory_mb * 1024 * 1024)
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

        stdout_bytes, stderr_bytes = b"", b""
        try:
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception:
            try:
                p_proc = (
                    psutil.Process(pid)
                    if (_HAS_PSUTIL and psutil is not None)
                    else None
                )
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

        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

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
        """Termina l'intero albero dei processi partendo da taskkill /F /T."""
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

        if _HAS_PSUTIL and psutil is not None and parent is not None:
            all_procs = (children or []) + [parent]
            for p in all_procs:
                try:
                    p.kill()
                except Exception:
                    pass

        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> int:
    """Interfaccia CLI per l'esecuzione isolata in Shadow Sandbox."""
    parser = argparse.ArgumentParser(
        description="Nexus Keystone DAST Shadow Sandbox Runner",
    )
    parser.add_argument("--script", type=str, help="Percorso dello script Python da eseguire")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout in secondi")
    parser.add_argument("--json", action="store_true", help="Stampa il report in JSON")
    args = parser.parse_args()

    if not args.script:
        parser.print_help()
        return 0

    src_script = Path(args.script).resolve()
    if not src_script.exists():
        sys.stderr.write(f"Script non trovato: {src_script}\n")
        return 1

    async def _run() -> SandboxTelemetryReport:
        with ShadowSandbox() as sb:
            sb.copy_file(src_script)
            runner = DASTSandboxRunner(SandboxConfig(timeout_sec=args.timeout))
            return await runner.run_in_sandbox(
                sb,
                [sys.executable, src_script.name],
                target_script_name=src_script.name,
            )

    report = asyncio.run(_run())
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"[DAST-SANDBOX] Success: {report.success} | Exit: {report.exit_code}")
    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())

"""Costanti, strutture Win32, stato RSS e modelli Pydantic DAST."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.isolated_test_runner import (
    WIN32_CREATE_NEW_PROCESS_GROUP,
    WIN32_CREATE_NO_WINDOW,
    WIN32_DETACHED_FLAGS,
    win32_detached_flags,
)

from . import _facade_attr  # noqa: F401


INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
CREATE_SUSPENDED = 0x00000004
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
RESUME_THREAD_ERROR = 0xFFFFFFFF
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

_BUILDER_STRIP_PATHS = (
    "nk_tracking/oracle_lock.json",
    "nk_tracking/oracle_holdout",
    "nk_tracking/benchmark_suite",
    "tests/evals",
)

_SENSITIVE_ENV_TOKENS = ("KEY", "SECRET", "TOKEN")
_BLOCKED_ENV_KEYS = {"NK_ALLOW_GOVERNANCE_OVERRIDE"}


class IO_COUNTERS(ctypes.Structure):
    """Struttura Win32 per i contatori di I/O del Job Object."""

    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """Struttura Win32 per i limiti base di un Job Object."""

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    """Struttura Win32 per i limiti estesi con JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE."""

    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class PROCESSENTRY32(ctypes.Structure):
    """Struttura Win32 per l'enumerazione dei processi nello snapshot di sistema."""

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


class THREADENTRY32(ctypes.Structure):
    """Struttura Win32 per l'enumerazione dei thread nello snapshot di sistema."""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", ctypes.c_long),
        ("tpDeltaPri", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
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


class _RSSMonitorState:
    """Stato locale protetto da lock per il campionamento RSS di una singola esecuzione."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.peak_memory_bytes: int = 0
        self.last_scan_ts: float = 0.0
        self.rss_cache: Dict[int, int] = {}

    def record_sample(self, rss_bytes: int) -> int:
        """Aggiorna in modo thread-safe il picco RSS osservato."""
        with self.lock:
            if rss_bytes > self.peak_memory_bytes:
                self.peak_memory_bytes = rss_bytes
            return self.peak_memory_bytes

    def get_peak(self) -> int:
        """Restituisce in modo thread-safe il picco RSS registrato."""
        with self.lock:
            return self.peak_memory_bytes


class SandboxConfig(BaseModel):
    """Opzioni di configurazione per l'esecuzione nella Shadow Sandbox."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    timeout_sec: float = Field(default=10.0, gt=0.0, le=60.0)
    poll_interval_sec: float = Field(default=0.025, gt=0.0, le=0.5)
    max_memory_mb: float = Field(default=512.0, gt=0.0)
    env_vars: Dict[str, str] = Field(default_factory=dict)
    trace_coverage: bool = Field(default=True)
    profile: str = Field(default="builder")


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

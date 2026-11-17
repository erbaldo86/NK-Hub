# -*- coding: utf-8 -*-
"""
Facciata DAST Shadow Sandbox Runner per NK Hub Generation 1.0.0-Generation.
Modulo: dast_sandbox_runner.py.
Delega la logica ai sottomoduli _internal.dast_sandbox_runner.* mantenendo --help zero-pydantic.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import pkgutil
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts" if _SCRIPT_DIR.parent.name == ".staging" else _SCRIPT_DIR
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
    _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")
from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402

init_nk_facade(__file__, pkg="dast_sandbox_runner")
importlib.import_module("_internal.dast_sandbox_runner").register_facade_module(__name__)


def _build_cli_parser() -> Any:
    """Costruisce il parser CLI senza importare pydantic su --help."""
    return importlib.import_module("_internal.dast_sandbox_runner.cli")._build_cli_parser()


if __name__ == "__main__" and any(arg in ("-h", "--help") for arg in sys.argv[1:]):
    _build_cli_parser().parse_args()
    raise SystemExit(0)

_LAZY_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "INVALID_HANDLE_VALUE": ("_internal.dast_sandbox_runner.constants", "INVALID_HANDLE_VALUE"),
    "CREATE_SUSPENDED": ("_internal.dast_sandbox_runner.constants", "CREATE_SUSPENDED"),
    "TH32CS_SNAPPROCESS": ("_internal.dast_sandbox_runner.constants", "TH32CS_SNAPPROCESS"),
    "TH32CS_SNAPTHREAD": ("_internal.dast_sandbox_runner.constants", "TH32CS_SNAPTHREAD"),
    "THREAD_SUSPEND_RESUME": ("_internal.dast_sandbox_runner.constants", "THREAD_SUSPEND_RESUME"),
    "RESUME_THREAD_ERROR": ("_internal.dast_sandbox_runner.constants", "RESUME_THREAD_ERROR"),
    "PROCESS_QUERY_INFORMATION": ("_internal.dast_sandbox_runner.constants", "PROCESS_QUERY_INFORMATION"),
    "PROCESS_VM_READ": ("_internal.dast_sandbox_runner.constants", "PROCESS_VM_READ"),
    "PROCESS_SET_QUOTA": ("_internal.dast_sandbox_runner.constants", "PROCESS_SET_QUOTA"),
    "PROCESS_TERMINATE": ("_internal.dast_sandbox_runner.constants", "PROCESS_TERMINATE"),
    "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE": ("_internal.dast_sandbox_runner.constants", "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE"),
    "JobObjectExtendedLimitInformation": ("_internal.dast_sandbox_runner.constants", "JobObjectExtendedLimitInformation"),
    "_BUILDER_STRIP_PATHS": ("_internal.dast_sandbox_runner.constants", "_BUILDER_STRIP_PATHS"),
    "_SENSITIVE_ENV_TOKENS": ("_internal.dast_sandbox_runner.constants", "_SENSITIVE_ENV_TOKENS"),
    "_BLOCKED_ENV_KEYS": ("_internal.dast_sandbox_runner.constants", "_BLOCKED_ENV_KEYS"),
    "IO_COUNTERS": ("_internal.dast_sandbox_runner.constants", "IO_COUNTERS"),
    "JOBOBJECT_BASIC_LIMIT_INFORMATION": ("_internal.dast_sandbox_runner.constants", "JOBOBJECT_BASIC_LIMIT_INFORMATION"),
    "JOBOBJECT_EXTENDED_LIMIT_INFORMATION": ("_internal.dast_sandbox_runner.constants", "JOBOBJECT_EXTENDED_LIMIT_INFORMATION"),
    "PROCESSENTRY32": ("_internal.dast_sandbox_runner.constants", "PROCESSENTRY32"),
    "THREADENTRY32": ("_internal.dast_sandbox_runner.constants", "THREADENTRY32"),
    "PROCESS_MEMORY_COUNTERS": ("_internal.dast_sandbox_runner.constants", "PROCESS_MEMORY_COUNTERS"),
    "_RSSMonitorState": ("_internal.dast_sandbox_runner.constants", "_RSSMonitorState"),
    "SandboxConfig": ("_internal.dast_sandbox_runner.constants", "SandboxConfig"),
    "CoverageTraceItem": ("_internal.dast_sandbox_runner.constants", "CoverageTraceItem"),
    "SandboxTelemetryReport": ("_internal.dast_sandbox_runner.constants", "SandboxTelemetryReport"),
    "_HAS_PSUTIL": ("_internal.dast_sandbox_runner.win32_job", "_HAS_PSUTIL"),
    "psutil": ("_internal.dast_sandbox_runner.win32_job", "psutil"),
    "_kernel32": ("_internal.dast_sandbox_runner.win32_job", "_kernel32"),
    "_psapi": ("_internal.dast_sandbox_runner.win32_job", "_psapi"),
    "_create_kill_on_close_job": ("_internal.dast_sandbox_runner.win32_job", "_create_kill_on_close_job"),
    "_assign_pid_to_job": ("_internal.dast_sandbox_runner.win32_job", "_assign_pid_to_job"),
    "_resume_process_primary_thread": ("_internal.dast_sandbox_runner.win32_job", "_resume_process_primary_thread"),
    "_assign_to_kill_on_close_job": ("_internal.dast_sandbox_runner.win32_job", "_assign_to_kill_on_close_job"),
    "_close_job_handle_safe": ("_internal.dast_sandbox_runner.win32_job", "_close_job_handle_safe"),
    "_terminate_process_tree_fallback": ("_internal.dast_sandbox_runner.win32_job", "_terminate_process_tree_fallback"),
    "_get_process_memory_rss": ("_internal.dast_sandbox_runner.win32_job", "_get_process_memory_rss"),
    "_resolve_confined_sandbox_path": ("_internal.dast_sandbox_runner.sandbox_fs", "_resolve_confined_sandbox_path"),
    "_handle_remove_readonly": ("_internal.dast_sandbox_runner.sandbox_fs", "_handle_remove_readonly"),
    "_strip_builder_holdouts_from_sandbox": ("_internal.dast_sandbox_runner.sandbox_fs", "_strip_builder_holdouts_from_sandbox"),
    "_build_sanitized_sandbox_env": ("_internal.dast_sandbox_runner.sandbox_fs", "_build_sanitized_sandbox_env"),
    "ShadowSandbox": ("_internal.dast_sandbox_runner.sandbox_fs", "ShadowSandbox"),
    "atomic_write_json": ("_internal.nk_common.io", "atomic_write_json"),
    "resolve_dast_report_path": ("_internal.dast_sandbox_runner.process_runner", "resolve_dast_report_path"),
    "write_atomic_dast_report": ("_internal.dast_sandbox_runner.process_runner", "write_atomic_dast_report"),
    "_run_job_isolated_subprocess": ("_internal.dast_sandbox_runner.process_runner", "_run_job_isolated_subprocess"),
    "_generate_trace_harness_script": ("_internal.dast_sandbox_runner.process_runner", "_generate_trace_harness_script"),
    "DASTSandboxRunner": ("_internal.dast_sandbox_runner.fuzzer", "DASTSandboxRunner"),
    "run_staging_shadow_verification": ("_internal.dast_sandbox_runner.e2e_and_audit", "run_staging_shadow_verification"),
}


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORT_MAP))


def __getattr__(name: str) -> Any:
    spec = _LAZY_EXPORT_MAP.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(spec[0]), spec[1])


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Interfaccia CLI per l'esecuzione isolata in Shadow Sandbox."""
    return importlib.import_module("_internal.dast_sandbox_runner.cli").main(argv=argv)


if __name__ == "__main__":
    sys.exit(main())

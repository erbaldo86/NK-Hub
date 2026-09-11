"""
Nexus Keystone v1.1.0-Universal - Universal Platform Runner & UTF-8 Stream Manager
Module: platform_runner.py
Author: NK-Platform-Builder

Features:
- UTF-8 stream reconfiguration for Windows and cross-platform environments.
- Safe subprocess execution with robust timeout, exception, and encoding handling.
- CLI execution mode for protected command evaluation.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union


def reconfigure_streams() -> None:
    """
    Force sys.stdout and sys.stderr (and sys.stdin if applicable) to UTF-8
    with replacement error handling, eliminating UnicodeEncodeError/UnicodeDecodeError.
    """
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def safe_subprocess_run(
    cmd: Union[str, Sequence[str]],
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
    capture: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    """
    Execute a subprocess safely with forced UTF-8 encoding and robust error handling.

    Args:
        cmd: Command string or sequence of arguments.
        cwd: Working directory for execution.
        timeout: Execution timeout in seconds.
        capture: Whether to capture stdout and stderr (default: True).
        env: Additional or override environment variables.

    Returns:
        Tuple of (returncode, stdout, stderr).
    """
    # Enforce stream UTF-8 configuration
    reconfigure_streams()

    # Construct child environment forcing Python UTF-8 mode
    run_env = dict(os.environ)
    if env is not None:
        run_env.update(env)
    run_env["PYTHONIOENCODING"] = "utf-8"
    run_env["PYTHONUTF8"] = "1"

    cwd_str = str(cwd) if cwd is not None else None
    use_shell = isinstance(cmd, str)

    stdout_pipe = subprocess.PIPE if capture else None
    stderr_pipe = subprocess.PIPE if capture else None

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd_str,
            timeout=timeout,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
            shell=use_shell,
        )
        return (
            proc.returncode,
            proc.stdout if proc.stdout is not None else "",
            proc.stderr if proc.stderr is not None else "",
        )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = exc.stdout
        raw_stderr = exc.stderr

        out_str = (
            raw_stdout
            if isinstance(raw_stdout, str)
            else (raw_stdout.decode("utf-8", errors="replace") if raw_stdout else "")
        )
        err_str = (
            raw_stderr
            if isinstance(raw_stderr, str)
            else (raw_stderr.decode("utf-8", errors="replace") if raw_stderr else "")
        )
        timeout_msg = f"[TIMEOUT] Command timed out after {timeout} seconds: {exc}"
        combined_err = f"{err_str}\n{timeout_msg}".strip() if err_str else timeout_msg
        return (-1, out_str, combined_err)
    except FileNotFoundError as exc:
        return (127, "", f"[FILE_NOT_FOUND] {exc}")
    except Exception as exc:
        return (1, "", f"[EXECUTION_ERROR] {type(exc).__name__}: {exc}")


def main() -> int:
    """
    CLI interface for platform runner.
    Usage: python scripts/platform_runner.py --cmd "command to run"
    """
    reconfigure_streams()

    parser = argparse.ArgumentParser(
        description="Nexus Keystone Universal Platform Runner",
    )
    parser.add_argument(
        "--cmd",
        type=str,
        required=True,
        help="Command to execute in a protected UTF-8 environment",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="Optional working directory",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Optional execution timeout in seconds",
    )
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="Disable stdout/stderr capturing and stream directly",
    )

    args = parser.parse_args()

    rc, stdout, stderr = safe_subprocess_run(
        cmd=args.cmd,
        cwd=args.cwd,
        timeout=args.timeout,
        capture=not args.no_capture,
    )

    if stdout:
        sys.stdout.write(stdout)
        if not stdout.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    if stderr:
        sys.stderr.write(stderr)
        if not stderr.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.flush()

    return rc


if __name__ == "__main__":
    sys.exit(main())

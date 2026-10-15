# -*- coding: utf-8 -*-
"""
Esecutore sicuro di sottoprocessi e gestore stream UTF-8 per Nexus Keystone v3.0.0-STE100-Unified.
Inietta il flag -u anche nei comandi stringa Python ed esegue tree-kill su timeout.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False


def reconfigure_streams() -> None:
    """Configura sys.stdout, sys.stderr e sys.stdin con codifica UTF-8 sicura."""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _normalize_python_command(
    cmd: Union[str, Sequence[str]],
) -> Union[str, List[str]]:
    """Aggiunge il flag -u alle invocazioni Python sia in formato lista sia stringa."""
    if isinstance(cmd, (list, tuple)):
        cmd_list = list(cmd)
        if len(cmd_list) > 0 and (
            "python" in str(cmd_list[0]).lower()
            or str(cmd_list[0]) == sys.executable
        ):
            if "-u" not in cmd_list[1:3]:
                cmd_list.insert(1, "-u")
        elif len(cmd_list) > 0 and str(cmd_list[0]).lower() == "pytest":
            cmd_list = [sys.executable, "-u", "-m", "pytest"] + cmd_list[1:]
        return cmd_list
    if isinstance(cmd, str):
        clean = cmd.strip()
        if clean == "pytest" or clean.startswith("pytest "):
            rest = clean[6:].strip()
            return f'"{sys.executable}" -u -m pytest {rest}'.strip()

        exe_escaped = re.escape(sys.executable)
        pattern = rf'^("{exe_escaped}"|{exe_escaped}|python3(?:\.exe)?|python(?:\.exe)?)\s+(?!-u\b)(.+)$'
        match = re.match(pattern, clean, flags=re.IGNORECASE)
        if match:
            prefix = match.group(1)
            rest = match.group(2)
            return f"{prefix} -u {rest}"
    return cmd


def _kill_process_tree_sync(pid: int) -> None:
    """Termina ricorsivamente il processo indicato e tutti i suoi figli."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
        except Exception:
            pass

    if _HAS_PSUTIL and psutil is not None:
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
        except Exception:
            pass


def safe_subprocess_run(
    cmd: Union[str, Sequence[str]],
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
    capture: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    """Esegue un sottoprocesso con codifica UTF-8, modalita unbuffered e tree-kill su timeout."""
    reconfigure_streams()

    run_env = dict(os.environ)
    if env is not None:
        run_env.update(env)
    run_env["PYTHONIOENCODING"] = "utf-8"
    run_env["PYTHONUTF8"] = "1"
    run_env["PYTHONUNBUFFERED"] = "1"

    normalized_cmd = _normalize_python_command(cmd)
    cwd_str = str(cwd) if cwd is not None else None
    use_shell = isinstance(normalized_cmd, str)

    stdout_pipe = subprocess.PIPE if capture else None
    stderr_pipe = subprocess.PIPE if capture else None

    proc: Optional[subprocess.Popen] = None
    try:
        proc = subprocess.Popen(
            normalized_cmd,
            cwd=cwd_str,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
            shell=use_shell,
        )
        stdout_str, stderr_str = proc.communicate(timeout=timeout)
        return (
            proc.returncode if proc.returncode is not None else 0,
            stdout_str if stdout_str is not None else "",
            stderr_str if stderr_str is not None else "",
        )
    except subprocess.TimeoutExpired as exc:
        if proc is not None and proc.pid:
            _kill_process_tree_sync(proc.pid)
            try:
                proc.kill()
            except Exception:
                pass
            try:
                rem_out, rem_err = proc.communicate(timeout=1.0)
            except Exception:
                rem_out, rem_err = "", ""
        else:
            rem_out, rem_err = "", ""

        raw_stdout = exc.stdout or rem_out
        raw_stderr = exc.stderr or rem_err

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
    """Interfaccia CLI per l'esecuzione protetta di comandi."""
    reconfigure_streams()

    parser = argparse.ArgumentParser(
        description="Nexus Keystone Universal Platform Runner v3",
    )
    parser.add_argument(
        "--cmd",
        type=str,
        required=True,
        help="Comando da eseguire in ambiente protetto UTF-8 unbuffered",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="Cartella di lavoro opzionale",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Timeout di esecuzione in secondi",
    )
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="Disabilita la cattura di stdout e stderr",
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

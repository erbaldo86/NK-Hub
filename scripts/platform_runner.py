# -*- coding: utf-8 -*-
"""
Esecutore sicuro di sottoprocessi e gestore stream UTF-8 per NK Hub Generation 1.0.0-Generation.
Inietta -u nei comandi Python, supporta pytest NVMe detached e tree-kill su timeout.
"""

from __future__ import annotations

import json
import os
import pkgutil
import re
import shlex
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union


def _ensure_nk_common_paths() -> None:
    """Configura sys.path e pkgutil.extend_path per risolvere _internal.nk_common."""
    script_dir = Path(__file__).resolve().parent
    prod_scripts = script_dir.parent.parent / "scripts" if script_dir.parent.name == ".staging" else script_dir
    for cand in (str(prod_scripts), str(script_dir)):
        if cand not in sys.path:
            sys.path.insert(0, cand)
    if script_dir != prod_scripts and (script_dir / "_internal" / "nk_common").is_dir():
        import _internal as _stg_int
        import _internal.nk_common as _stg_nkc

        _stg_int.__path__ = pkgutil.extend_path(_stg_int.__path__, "_internal")
        _stg_nkc.__path__ = pkgutil.extend_path(_stg_nkc.__path__, "_internal.nk_common")


def _win32_detached_flags() -> int:
    """Restituisce i flag Win32 per isolare il sottoprocesso da conhost.exe."""
    if sys.platform != "win32":
        return 0
    try:
        _ensure_nk_common_paths()
        from _internal.nk_common.isolated_test_runner import WIN32_DETACHED_FLAGS

        return int(WIN32_DETACHED_FLAGS)
    except ImportError:
        return 0x00000200 | 0x08000000


def reconfigure_streams() -> None:
    """Configura sys.stdout, sys.stderr e sys.stdin con codifica UTF-8 sicura."""
    _ensure_nk_common_paths()
    from _internal.nk_common.paths import reconfigure_streams as _nk_reconfigure

    _nk_reconfigure(include_stdin=True)


def _normalize_python_command(
    cmd: Union[str, Sequence[str]],
) -> Union[str, List[str]]:
    """Aggiunge il flag -u alle invocazioni Python sia in formato lista sia stringa."""
    if isinstance(cmd, (list, tuple)):
        cmd_list = list(cmd)
        if len(cmd_list) > 0 and ("python" in str(cmd_list[0]).lower() or str(cmd_list[0]) == sys.executable):
            if "-u" not in cmd_list[1:3]:
                cmd_list.insert(1, "-u")
        elif len(cmd_list) > 0 and str(cmd_list[0]).lower() == "pytest":
            cmd_list = [sys.executable, "-u", "-m", "pytest"] + cmd_list[1:]
        return cmd_list
    if isinstance(cmd, str):
        clean = cmd.strip()
        if clean == "pytest" or clean.startswith("pytest "):
            return f'"{sys.executable}" -u -m pytest {clean[6:].strip()}'.strip()
        exe_escaped = re.escape(sys.executable)
        pattern = rf'^("{exe_escaped}"|{exe_escaped}|python3(?:\.exe)?|python(?:\.exe)?)\s+(?!-u\b)(.+)$'
        match = re.match(pattern, clean, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1)} -u {match.group(2)}"
    return cmd


def _kill_process_tree_sync(pid: int) -> None:
    """Termina ricorsivamente il processo indicato e tutti i suoi figli."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        import subprocess

        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_win32_detached_flags(),
                timeout=2.0,
            )
        except Exception:
            pass

    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
        except Exception:
            pass


_UNQUOTED_SHELL_METACHARS = frozenset({"&", "|", ";", ">", "<", "`", "\n", "\r", "\x00"})
_BATCH_ARG_METACHARS = frozenset({"&", "|", ">", "<", "`", "\n", "\r", "\x00"})


def _tokenize_command_no_shell(cmd_str: str) -> List[str]:
    """Suddivide una stringa comando senza shell preservando percorsi Windows, parentesi e .exe."""
    if "\x00" in cmd_str:
        raise ValueError("Null byte rilevato nel comando.")
    tokens: List[str] = []
    buf: List[str] = []
    quote_char: Optional[str] = None
    in_token = False
    i = 0
    n = len(cmd_str)

    while i < n:
        ch = cmd_str[i]
        if quote_char is not None:
            if ch == "\\" and quote_char == '"' and (i + 1) < n and cmd_str[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            if ch == quote_char:
                quote_char = None
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue

        if ch in ('"', "'"):
            quote_char = ch
            in_token = True
            i += 1
            continue
        if ch in _UNQUOTED_SHELL_METACHARS:
            raise ValueError(f"Metacarattere shell non quotato vietato ({ch!r}) con use_shell=False.")
        if ch == "$" and (i + 1) < n and cmd_str[i + 1] == "(":
            raise ValueError("Sostituzione comando '$()' vietata con use_shell=False.")
        if ch.isspace():
            if in_token:
                tokens.append("".join(buf))
                buf.clear()
                in_token = False
            i += 1
            continue

        in_token = True
        buf.append(ch)
        i += 1

    if quote_char is not None:
        raise ValueError("Virgolette non bilanciate nella stringa comando.")
    if in_token:
        tokens.append("".join(buf))
    return tokens


def _prepare_argv_no_shell(
    normalized_cmd: Union[str, Sequence[str]],
    run_env: Dict[str, str],
) -> List[str]:
    """Valida e risolve l'eseguibile tramite shutil.which senza forzare shell=True su .bat/.cmd."""
    argv = _tokenize_command_no_shell(normalized_cmd) if isinstance(normalized_cmd, str) else [str(part) for part in normalized_cmd]
    if not argv or not argv[0].strip():
        raise ValueError("Comando vuoto non valido.")

    exe = argv[0]
    if any(c in exe for c in ("\x00", "\n", "\r")):
        raise ValueError("Caratteri di controllo vietati in cmd[0].")

    if not Path(exe).is_file():
        import shutil

        resolved_exe = shutil.which(exe, path=run_env.get("PATH"))
        if resolved_exe:
            argv[0] = resolved_exe

    for arg in argv[1:]:
        if "\x00" in arg:
            raise ValueError("Null byte vietato negli argomenti del comando.")

    if argv[0].lower().endswith((".bat", ".cmd")):
        for arg in argv[1:]:
            if any(mc in arg for mc in _BATCH_ARG_METACHARS):
                raise ValueError("Metacaratteri potenzialmente pericolosi rilevati negli argomenti per script .bat/.cmd.")

    return argv


def _decode_stream_output(raw: Union[str, bytes, None]) -> str:
    """Decodifica lo stream stdout/stderr in stringa UTF-8."""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace") if raw else ""


def safe_subprocess_run(
    cmd: Union[str, Sequence[str]],
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
    capture: bool = True,
    env: Optional[Dict[str, str]] = None,
    use_shell: bool = False,
) -> Tuple[int, str, str]:
    """Esegue un sottoprocesso con codifica UTF-8, modalita unbuffered e tree-kill su timeout."""
    import subprocess

    reconfigure_streams()
    run_env = dict(os.environ)
    if env is not None:
        run_env.update(env)
    run_env["PYTHONIOENCODING"] = "utf-8"
    run_env["PYTHONUTF8"] = "1"
    run_env["PYTHONUNBUFFERED"] = "1"

    normalized_cmd = _normalize_python_command(cmd)
    cwd_str = str(cwd) if cwd is not None else None
    effective_shell = bool(use_shell)
    stdout_pipe = subprocess.PIPE if capture else None
    stderr_pipe = subprocess.PIPE if capture else None

    proc: Optional[subprocess.Popen[str]] = None
    try:
        if effective_shell:
            raw_shell_str = (
                normalized_cmd
                if isinstance(normalized_cmd, str)
                else (
                    subprocess.list2cmdline([str(x) for x in normalized_cmd])
                    if sys.platform == "win32"
                    else shlex.join([str(x) for x in normalized_cmd])
                )
            )
            if any(c in raw_shell_str for c in ("\x00", "\n", "\r")):
                raise ValueError("Caratteri di controllo vietati in modalita shell.")
            popen_target: Union[str, List[str]] = raw_shell_str
        else:
            popen_target = _prepare_argv_no_shell(normalized_cmd, run_env)

        proc = subprocess.Popen(
            popen_target, cwd=cwd_str, stdin=subprocess.DEVNULL, stdout=stdout_pipe, stderr=stderr_pipe,
            text=True, encoding="utf-8", errors="replace", env=run_env, shell=effective_shell, creationflags=_win32_detached_flags(),
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

        out_str = _decode_stream_output(exc.stdout or rem_out)
        err_str = _decode_stream_output(exc.stderr or rem_err)
        timeout_msg = f"[TIMEOUT] Command timed out after {timeout} seconds: {exc}"
        combined_err = f"{err_str}\n{timeout_msg}".strip() if err_str else timeout_msg
        return (-1, out_str, combined_err)
    except FileNotFoundError as exc:
        return (127, "", f"[FILE_NOT_FOUND] {exc}")
    except Exception as exc:
        return (1, "", f"[EXECUTION_ERROR] {type(exc).__name__}: {exc}")


def _run_pytest_isolated_cli(args: object) -> int:
    """Delega l'esecuzione pytest isolata su NVMe al runner detached."""
    _ensure_nk_common_paths()
    from _internal.nk_common.isolated_test_runner import run_detached_pytest

    script_dir = Path(__file__).resolve().parent
    default_ws = script_dir.parent.parent if script_dir.parent.name == ".staging" else script_dir.parent
    ws_arg = getattr(args, "workspace_root", None)
    ws_root = Path(ws_arg).resolve() if ws_arg else default_ws
    raw_extra = getattr(args, "pytest_args", None)
    extra_args = tuple(shlex.split(raw_extra)) if raw_extra else ("-q", "--tb=short")
    timeout_val = getattr(args, "timeout", None)
    res = run_detached_pytest(
        workspace_root=ws_root,
        targets=tuple(getattr(args, "targets", None) or ("tests",)),
        extra_args=extra_args,
        timeout_sec=float(timeout_val) if timeout_val is not None else 180.0,
        coverage=bool(getattr(args, "coverage", False)),
        apply_overlay=bool(getattr(args, "overlay_staging", False)),
    )
    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(
            f"[NK-PYTEST-ISO] status={res['status']} passed={res['passed']} "
            f"failed={res['failed']} errors={res['errors']} skipped={res['skipped']} "
            f"duration_s={res['duration_s']} log={res['log_file']}\n"
        )
        if not res["success"] and res.get("tail"):
            sys.stdout.write(str(res["tail"]) + "\n")
    sys.stdout.flush()
    return int(res.get("exit_code", 1))


def main() -> int:
    """Interfaccia CLI per l'esecuzione protetta di comandi e pytest NVMe isolati."""
    import argparse

    reconfigure_streams()
    parser = argparse.ArgumentParser(description="NK Hub Generation Universal Platform Runner 1.0.0-Generation")
    parser.add_argument("--cmd", type=str, required=False, default=None, help="Comando da eseguire in ambiente UTF-8 unbuffered")
    parser.add_argument("--cwd", type=str, default=None, help="Cartella di lavoro opzionale")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout di esecuzione in secondi")
    parser.add_argument("--no-capture", action="store_true", help="Disabilita la cattura di stdout e stderr")
    parser.add_argument("--pytest-isolated", action="store_true", help="Esegue pytest in mirror NVMe detached su TEMP")
    parser.add_argument("--targets", nargs="+", default=["tests"], help="Percorsi target pytest da eseguire in isolamento")
    parser.add_argument("--workspace-root", type=str, default=None, help="Radice del workspace da replicare su NVMe")
    parser.add_argument("--coverage", action="store_true", help="Abilita la raccolta coverage con pytest-cov")
    parser.add_argument("--overlay-staging", action="store_true", help="Sovrappone .staging/ su produzione nel mirror")
    parser.add_argument("--pytest-args", type=str, default=None, help="Argomenti extra passati a pytest")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato isolato in formato JSON")
    args = parser.parse_args()
    if args.pytest_isolated:
        return _run_pytest_isolated_cli(args)
    if not args.cmd:
        parser.error("--cmd e' obbligatorio quando --pytest-isolated non e' attivo.")
    rc, stdout, stderr = safe_subprocess_run(cmd=args.cmd, cwd=args.cwd, timeout=args.timeout, capture=not args.no_capture)
    if stdout:
        sys.stdout.write(stdout if stdout.endswith("\n") else stdout + "\n")
        sys.stdout.flush()
    if stderr:
        sys.stderr.write(stderr if stderr.endswith("\n") else stderr + "\n")
        sys.stderr.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main())

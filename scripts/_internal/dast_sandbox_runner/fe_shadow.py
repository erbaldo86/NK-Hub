# -*- coding: utf-8 -*-
"""Shadow Sandbox Frontend con junction NTFS sicura, porte isolate e guardia node_modules."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from _internal.nk_common.lane_leases import (
    allocate_lane_loopback_port,
    register_runtime_lease,
    release_runtime_lease,
)
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.nvme_mirror_helpers import safe_rmtree
from _internal.nk_common.staging_manifest import is_reparse_entry

from .constants import DAST_MAX_OUTPUT_BYTES
from .process_runner import _run_job_isolated_subprocess
from .sandbox_fs import _truncate_utf8_bytes

_MUTATING_PKG_ACTIONS: Dict[str, Tuple[str, ...]] = {
    "npm": ("install", "i", "ci", "update", "up", "uninstall", "remove", "rm", "add", "link", "rebuild"),
    "yarn": ("install", "add", "remove", "upgrade", "up", "link"),
    "pnpm": ("install", "i", "add", "remove", "rm", "update", "up", "link"),
    "bun": ("install", "i", "add", "remove", "rm", "update", "link"),
}
_PKG_WRAPPERS = frozenset(("npx", "pnpx", "bunx", "corepack"))
_SHELL_WRAPPERS = frozenset(("cmd", "powershell", "pwsh", "sh", "bash"))
_PKG_VALUE_FLAGS = frozenset((
    "--prefix", "-c", "--cwd", "--dir", "--config", "--registry",
    "--cache", "--workspace", "-w", "--userconfig", "--globalconfig", "--filter",
))
_SAFE_SCRIPT_VERBS = frozenset(("run", "run-script", "test", "t", "exec", "x"))
_FE_TEST_EXTS = frozenset((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
_SHELL_SPLIT_RE = re.compile(r"(?:&&|\|\||[;|&])")


def _split_cmd_tokens(seg: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(seg, str):
        return [tok.strip("\"'") for tok in shlex.split(seg, posix=False) if tok.strip("\"'")]
    return [str(tok).strip("\"'") for tok in seg if str(tok).strip("\"'")]


def _norm_bin_name(tok: str) -> str:
    base = tok.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".exe", ".cmd", ".bat"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    return base


def _collect_pkg_positionals(rest: Sequence[str]) -> List[str]:
    positionals: List[str] = []
    skip_next = False
    for raw in rest:
        if skip_next:
            skip_next = False
            continue
        low = raw.lower()
        if low == "--":
            break
        if low.startswith("-"):
            if "=" not in low and low in _PKG_VALUE_FLAGS:
                skip_next = True
            continue
        positionals.append(low)
    return positionals


def _check_shell_wrapper(rest: Sequence[str]) -> None:
    non_flags = [a for a in rest if not a.startswith(("-", "/"))]
    if len(non_flags) > 1:
        assert_no_node_modules_mutation_cmd(" ".join(non_flags))
    for arg in non_flags:
        assert_no_node_modules_mutation_cmd(arg)


def _check_exec_tail(pos: Sequence[str], tail: Sequence[str], raw_str: str) -> None:
    if not pos or pos[0] not in ("exec", "x"):
        return
    after = tail[tail.index("--") + 1 :] if "--" in tail else list(pos[1:])
    _check_segment_node_mutation(after, raw_str)


def _check_segment_node_mutation(seg: Union[str, Sequence[str]], raw_str: str) -> None:
    toks = _split_cmd_tokens(seg)
    if not toks:
        return
    idx = 0
    while idx < len(toks) and _norm_bin_name(toks[idx]) in _PKG_WRAPPERS:
        idx += 1
    if idx >= len(toks):
        return
    verb = _norm_bin_name(toks[idx])
    if verb in _SHELL_WRAPPERS:
        _check_shell_wrapper(toks[idx + 1 :])
        return
    if verb not in _MUTATING_PKG_ACTIONS:
        return
    pos = _collect_pkg_positionals(toks[idx + 1 :])
    if verb == "yarn" and not pos:
        raise ValueError(f"NODE_MODULES_MUTATION_FORBIDDEN: bare yarn install ({raw_str})")
    if pos and pos[0] not in _SAFE_SCRIPT_VERBS:
        bad = next((a for a in pos if a in _MUTATING_PKG_ACTIONS[verb]), None)
        if bad is not None:
            raise ValueError(f"NODE_MODULES_MUTATION_FORBIDDEN: {verb} {bad} ({raw_str})")
    _check_exec_tail(pos, toks[idx + 1 :], raw_str)


def assert_no_node_modules_mutation_cmd(cmd: Union[str, Sequence[str]]) -> None:
    """Vieta comandi npm/yarn/pnpm/bun che mutano node_modules condivisi."""
    raw_str = cmd if isinstance(cmd, str) else " ".join(str(x) for x in cmd)
    segments = _SHELL_SPLIT_RE.split(cmd) if isinstance(cmd, str) else [cmd]
    for seg in segments:
        _check_segment_node_mutation(seg, raw_str)


def remove_junction_safely(junction_path: Path) -> bool:
    """Scollega una junction NTFS o symlink senza cancellare i file della directory target."""
    if not (junction_path.exists() or junction_path.is_symlink() or is_reparse_entry(junction_path)):
        return True
    if not (is_reparse_entry(junction_path) or junction_path.is_symlink()):
        raise ValueError(f"Rifiuto remove_junction_safely su directory reale non reparse: {junction_path}")
    try:
        os.rmdir(junction_path)
    except OSError:
        os.unlink(junction_path)
    return not (junction_path.exists() or is_reparse_entry(junction_path))


def _count_e2e_test_files(project_dir: Path) -> Tuple[bool, int]:
    has_e2e = False
    count = 0
    for dname in ("e2e", "playwright"):
        sub = project_dir / dname
        if not sub.is_dir() or is_reparse_entry(sub):
            continue
        has_e2e = True
        for w_root, dirs, files in os.walk(sub, followlinks=False):
            w_p = Path(w_root)
            dirs[:] = [d for d in dirs if not is_reparse_entry(w_p / d)]
            for fn in files:
                fp = w_p / fn
                if not is_reparse_entry(fp) and fp.suffix.lower() in _FE_TEST_EXTS:
                    count += 1
    return has_e2e, count


def detect_frontend_project(project_dir: Path) -> Dict[str, Any]:
    """Rileva progetto Frontend Node/TS-JS ed eventuali cartelle e2e vuote."""
    pkg_file = project_dir / "package.json"
    pkg_present = pkg_file.is_file() and not is_reparse_entry(pkg_file)
    scripts: Dict[str, str] = {}
    if pkg_present:
        try:
            loaded = json.loads(pkg_file.read_text(encoding="utf-8", errors="replace"))
            if isinstance(loaded, dict) and isinstance(loaded.get("scripts"), dict):
                scripts = {str(k): str(v) for k, v in loaded["scripts"].items()}
        except (OSError, ValueError):
            pkg_present = False
    has_e2e, e2e_count = _count_e2e_test_files(project_dir)
    return {
        "is_frontend": pkg_present, "package_json_present": pkg_present, "scripts": scripts,
        "has_e2e_dir": has_e2e, "e2e_test_files_count": e2e_count, "empty_e2e_dir": has_e2e and e2e_count == 0,
    }


class FrontendShadowSandbox:
    """Sandbox isolata per suite frontend con porte dedicata, lease e junction NTFS sicura."""

    def __init__(
        self, repo_root: Union[str, Path], *, lane_id: str = "fe_default",
        conversation_id: str = "", host_node_modules: Optional[Path] = None,
        lease_registry_path: Optional[Path] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.lane_id = validate_lane_id(lane_id)
        self.conversation_id = conversation_id
        self.host_node_modules = Path(host_node_modules).resolve() if host_node_modules else None
        self.lease_registry_path = lease_registry_path
        self.shadow_dir: Optional[Path] = None
        self.junction_path: Optional[Path] = None
        self.fe_port: int = 0
        self.be_port: int = 0
        self.lease_id: str = ""

    def __enter__(self) -> FrontendShadowSandbox:
        self.shadow_dir = Path(tempfile.mkdtemp(prefix=f"nk_fe_shadow_{self.lane_id}_")).resolve()
        self.fe_port = allocate_lane_loopback_port(f"{self.lane_id}_fe", registry_path=self.lease_registry_path)
        self.be_port = allocate_lane_loopback_port(f"{self.lane_id}_be", registry_path=self.lease_registry_path)
        if self.be_port == self.fe_port:
            self.be_port = allocate_lane_loopback_port(f"{self.lane_id}_be2", port_min=self.fe_port + 1, registry_path=self.lease_registry_path)
        lease = register_runtime_lease(
            self.repo_root, lane_id=self.lane_id, conversation_id=self.conversation_id,
            ports=(self.fe_port, self.be_port), registry_path=self.lease_registry_path,
        )
        self.lease_id = str(lease["lease_id"])

        if self.host_node_modules is not None and self.host_node_modules.is_dir():
            j_path = self.shadow_dir / "node_modules"
            if sys.platform == "win32":
                proc = _run_job_isolated_subprocess(
                    ["cmd", "/c", "mklink", "/J", str(j_path), str(self.host_node_modules)],
                    cwd=self.shadow_dir, env=os.environ.copy(), timeout_sec=15.0,
                )
                if proc.returncode != 0:
                    raise OSError(f"Creazione NTFS junction fallita: {proc.stderr or proc.stdout}")
            else:
                os.symlink(self.host_node_modules, j_path, target_is_directory=True)
            self.junction_path = j_path
        return self

    def run_command(
        self, cmd: Sequence[str], *, env: Optional[Dict[str, str]] = None,
        timeout_sec: float = 60.0, run_sub_fn: Any = None,
    ) -> Any:
        """Esegue un comando test frontend validando il blocco mutazione node_modules."""
        if self.shadow_dir is None:
            raise RuntimeError("FrontendShadowSandbox non attivo")
        assert_no_node_modules_mutation_cmd(cmd)
        run_env = dict(env) if env is not None else os.environ.copy()
        run_env["PORT"], run_env["API_PORT"] = str(self.fe_port), str(self.be_port)
        fn = run_sub_fn or _run_job_isolated_subprocess
        return fn(list(cmd), cwd=self.shadow_dir, env=run_env, timeout_sec=timeout_sec)

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        try:
            if self.junction_path is not None and (self.junction_path.exists() or is_reparse_entry(self.junction_path)):
                remove_junction_safely(self.junction_path)
        finally:
            try:
                if self.shadow_dir is not None:
                    safe_rmtree(self.shadow_dir)
            finally:
                if self.lease_id:
                    release_runtime_lease(self.lease_id, registry_path=self.lease_registry_path)


def evaluate_frontend_test_suite(
    sb_dir: Path, env: Dict[str, str], timeout_sec: float, run_sub_fn: Any,
    *, lane_id: Optional[str] = None, cmd_override: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Esegue e valuta una suite test TS/JS in Shadow Sandbox senza falsi verdi."""
    info = detect_frontend_project(sb_dir)
    if info["empty_e2e_dir"]:
        return {"executed": True, "passed": False, "exit_code": 5, "runner": "frontend", "error": "Cartella e2e/ o playwright/ vuota (anti-false-green gate)", "stdout": "", "stderr": ""}
    cmd = list(cmd_override) if cmd_override is not None else (["npm", "test", "--", "--run"] if "test" in info["scripts"] else [])
    if not cmd:
        return {"executed": True, "passed": False, "exit_code": 5, "runner": "frontend", "error": "Nessuno script test configurato in package.json", "stdout": "", "stderr": ""}
    try:
        assert_no_node_modules_mutation_cmd(cmd)
    except ValueError as exc:
        return {"executed": True, "passed": False, "exit_code": 2, "runner": "frontend", "error": str(exc), "stdout": "", "stderr": str(exc)}
    fe_env = dict(env)
    fe_env["NK_FE_PORT"] = str(allocate_lane_loopback_port(f"fe-{validate_lane_id(lane_id)}" if lane_id else "fe-legacy"))
    t0 = time.perf_counter()
    proc = run_sub_fn(cmd, cwd=sb_dir, env=fe_env, timeout_sec=timeout_sec)
    return {
        "executed": True, "passed": proc.returncode == 0, "exit_code": proc.returncode, "runner": "frontend",
        "duration_s": round(time.perf_counter() - t0, 3),
        "stdout": _truncate_utf8_bytes(proc.stdout or "", DAST_MAX_OUTPUT_BYTES),
        "stderr": _truncate_utf8_bytes(proc.stderr or "", DAST_MAX_OUTPUT_BYTES),
    }

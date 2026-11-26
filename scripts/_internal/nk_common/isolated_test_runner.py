# -*- coding: utf-8 -*-
"""Runner isolato NVMe per esecuzione pytest detached anti-crash Win32."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.lane_paths import resolve_staging_dir
from _internal.nk_common.nvme_base_cache import (  # noqa: F401
    clone_nvme_base_to_mirror, sync_nvme_base_cache,
)
from _internal.nk_common.nvme_mirror_helpers import (
    _apply_staging_overlay_to_mirror, _build_mirror_ignore, _is_mirror_ignored_name,
    _is_mirror_root_file, _is_safe_local_dir, _is_sibling_projects_parent,
    _iter_mirror_subdir_names, _load_deleted_set, _MIRROR_DIRS, _MIRROR_EXCLUDED_SUFFIXES,
    _mirror_project_base, _resolve_mirror_targets, _ROOT_ALLOWED_SUFFIXES, _ROOT_FILES,
    _sync_staging_tests_for_pytest, safe_rmtree,
)
from _internal.nk_common.paths import (  # noqa: F401
    is_nk_proget_locale_path, normalize_rel_path,
)
from _internal.nk_common.pytest_parallel import (
    resolve_coverage_source, run_parallel_pytest_shards, should_use_parallel_shards,
)
from _internal.nk_common.staging_manifest import is_reparse_entry as _is_reparse_entry
from _internal.nk_common.tas_ssot_io import (  # noqa: F401
    parse_deleted_files_manifest, parse_pytest_summary,
)
from _internal.nk_common.win32_mutex import repo_path_hash12

WIN32_CREATE_NEW_PROCESS_GROUP: int = 0x00000200
WIN32_CREATE_NO_WINDOW: int = 0x08000000
WIN32_DETACHED_FLAGS: int = (WIN32_CREATE_NEW_PROCESS_GROUP | WIN32_CREATE_NO_WINDOW) if sys.platform == "win32" else 0

__all__ = [
    "WIN32_CREATE_NEW_PROCESS_GROUP", "WIN32_CREATE_NO_WINDOW", "WIN32_DETACHED_FLAGS",
    "_MIRROR_DIRS", "_ROOT_FILES", "_ROOT_ALLOWED_SUFFIXES", "_MIRROR_EXCLUDED_SUFFIXES",
    "_is_safe_local_dir", "_is_mirror_ignored_name", "_build_mirror_ignore",
    "_apply_staging_overlay_to_mirror", "_sync_staging_tests_for_pytest",
    "_iter_mirror_subdir_names", "_is_sibling_projects_parent", "_is_mirror_root_file",
    "_mirror_project_base", "_load_deleted_set", "_resolve_mirror_targets",
    "win32_detached_flags", "is_temp_workspace", "safe_rmtree",
    "mirror_workspace_to_nvme", "run_detached_pytest",
]


def win32_detached_flags(extra_flags: int = 0) -> int:
    """Restituisce i flag Win32 detached combinati con eventuali flag extra."""
    return (WIN32_DETACHED_FLAGS | int(extra_flags)) if sys.platform == "win32" else 0


def is_temp_workspace(path: Path) -> bool:
    """Verifica se un percorso risiede dentro una cartella temporanea locale."""
    cand = Path(path).resolve()
    roots = [Path(tempfile.gettempdir()).resolve()] + [
        Path(v).resolve()
        for k in ("TEMP", "TMP", "TMPDIR")
        if (v := os.environ.get(k, "").strip())
    ]
    if la := os.environ.get("LOCALAPPDATA", "").strip():
        roots.append((Path(la) / "Temp").resolve())
    return any(cand == r or cand.is_relative_to(r) for r in roots)


def _copy_staging_to_mirror(
    mirror_dir: Path, ws_root: Path, staging_dir: Optional[Path], apply_overlay: bool, lane_id: Optional[str]
) -> None:
    """Copia o sovrappone .staging/ (o lane) nel mirror NVMe."""
    stg_src, norm_lane = resolve_staging_dir(ws_root, lane_id=lane_id, staging_dir=staging_dir) if (lane_id is not None or staging_dir is not None) else ((ws_root / ".staging").resolve(), None)
    excl_lanes = norm_lane is None and stg_src.name == ".staging"
    if not (stg_src.exists() and not _is_reparse_entry(stg_src) and stg_src.is_dir()):
        return
    stg_res = stg_src.resolve()
    if apply_overlay:
        _apply_staging_overlay_to_mirror(mirror_dir, stg_res, ws_root, exclude_lanes=excl_lanes)
    else:
        shutil.copytree(stg_res, mirror_dir / ".staging", ignore=_build_mirror_ignore(ws_root, exclude_lanes=excl_lanes, stg_dir=stg_res), dirs_exist_ok=True)


def _mirror_sibling_projects(
    mirror_root: Path, ws_root: Path, apply_overlay: bool, overlay_siblings: bool
) -> None:
    """Clona i progetti fratelli sicuri dentro mirror_root se applicabile."""
    if not _is_sibling_projects_parent(ws_root.parent):
        return
    for sib in ws_root.parent.iterdir():
        if sib != ws_root and not sib.name.startswith(".") and _is_safe_local_dir(sib, ws_root.parent):
            sib_dst = mirror_root / sib.name
            _mirror_project_base(sib, sib_dst)
            sib_stg = sib / ".staging"
            if apply_overlay and overlay_siblings and _is_safe_local_dir(sib_stg, sib):
                _apply_staging_overlay_to_mirror(sib_dst, sib_stg.resolve(), sib, exclude_lanes=True)


def mirror_workspace_to_nvme(
    workspace_root: Path,
    staging_dir: Optional[Path] = None,
    prefix: str = "nk_pytest_iso_",
    apply_overlay: bool = False,
    mirror_siblings: bool = False,
    overlay_siblings: bool = False,
    *,
    lane_id: Optional[str] = None,
) -> Path:
    """Crea una copia isolata del workspace su NVMe in TEMP restituendo mirror_dir."""
    ws_root = Path(workspace_root).resolve()
    mirror_root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    mirror_dir = mirror_root / (ws_root.name or "NK_Hub")
    _mirror_project_base(ws_root, mirror_dir)
    _copy_staging_to_mirror(mirror_dir, ws_root, staging_dir, apply_overlay, lane_id)
    if mirror_siblings:
        _mirror_sibling_projects(mirror_root, ws_root, apply_overlay, overlay_siblings)
    return mirror_dir


def _kill_detached_tree(pid: int) -> None:
    """Termina processo figlio e discendenti su timeout senza bloccare conhost."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=win32_detached_flags(),
                timeout=2.0,
            )
        except Exception:
            pass
    try:
        import psutil

        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        pass


def _extract_pytest_metrics(
    log_text: str, cov_json: Optional[Path], junit_xml: Optional[Path] = None
) -> Dict[str, Any]:
    """Estrae conteggi Pytest tramite SSOT JUnit XML/bottom-up e metriche coverage JSON."""
    try:
        summary = parse_pytest_summary(log_text, "", junit_xml_path=junit_xml)
    except (OSError, ValueError):
        summary = parse_pytest_summary(log_text, "", junit_xml_path=None)
    metrics: Dict[str, Any] = {
        "passed": int(summary.get("passed", 0)),
        "failed": int(summary.get("failed", 0)),
        "errors": int(summary.get("errors", 0)),
        "skipped": int(summary.get("skipped", 0)),
        "xfailed": int(summary.get("xfailed", 0)),
    }
    if cov_json is not None and cov_json.is_file():
        try:
            tot = json.loads(cov_json.read_text(encoding="utf-8")).get("totals", {})
            if isinstance(tot, dict) and tot:
                ns = float(tot.get("num_statements", 0) or 0)
                cl = float(tot.get("covered_lines", 0) or 0)
                nb = float(tot.get("num_branches", 0) or 0)
                cb = float(tot.get("covered_branches", 0) or 0)
                sp, bp, cp = (
                    tot.get("percent_statements_covered"),
                    tot.get("percent_branches_covered"),
                    tot.get("percent_covered"),
                )
                metrics["coverage"] = {
                    "statement_coverage_pct": round(
                        float(sp if sp is not None else ((cl / ns) * 100.0 if ns else 0.0)), 2
                    ),
                    "true_branch_coverage_pct": round(
                        float(bp if bp is not None else ((cb / nb) * 100.0 if nb else 0.0)), 2
                    ),
                    "combined_coverage_pct": round(float(cp if cp is not None else 0.0), 2),
                }
        except (OSError, ValueError, TypeError):
            pass
    return metrics


def _resolve_junit_flag_path(
    extra_args: Sequence[str], default_junit: Path
) -> Tuple[List[str], Optional[Path]]:
    """Prepara --junitxml se non gia specificato in extra_args evitando duplicazioni."""
    for idx, arg in enumerate(extra_args):
        s_arg = str(arg)
        if s_arg.startswith("--junitxml="):
            return [], Path(s_arg.split("=", 1)[1])
        if s_arg == "--junitxml" and idx + 1 < len(extra_args):
            return [], Path(str(extra_args[idx + 1]))
    return [f"--junitxml={default_junit.as_posix()}"], default_junit


def _prepare_detached_env(mirror_dir: Path, apply_overlay: bool) -> Dict[str, str]:
    """Prepara ambiente UTF-8 isolato e PYTHONPATH per esecuzione pytest su mirror."""
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )
    for k in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"):
        env.pop(k, None)
    has_conftest = (mirror_dir / "tests" / "conftest.py").is_file()
    py_parts = (
        [str(mirror_dir)]
        if (has_conftest or apply_overlay or not (mirror_dir / ".staging").is_dir())
        else [str(mirror_dir / ".staging"), str(mirror_dir)]
    )
    env["PYTHONPATH"] = os.pathsep.join(py_parts)
    return env


def _run_single_detached_proc(
    cmd: List[str], mirror_dir: Path, env: Dict[str, str], log_file: Path, timeout_sec: float
) -> Tuple[int, bool, float, str]:
    """Esegue un singolo processo pytest detached nel mirror NVMe con gestione timeout."""
    timed_out, rc = False, 1
    t0, deadline = time.perf_counter(), time.perf_counter() + max(0.05, float(timeout_sec))
    with open(log_file, "w", encoding="utf-8", errors="replace") as log_fh:
        proc = subprocess.Popen(
            cmd,
            cwd=str(mirror_dir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            creationflags=win32_detached_flags(),
            shell=False,
        )
        while (polled := proc.poll()) is None:
            if time.perf_counter() >= deadline:
                timed_out, rc = True, -1
                _kill_detached_tree(proc.pid)
                try:
                    proc.kill()
                    proc.wait(timeout=2.0)
                except (OSError, subprocess.SubprocessError, ValueError):
                    rc = -1
                break
            time.sleep(0.05)
        else:
            rc = int(polled)
    return (
        rc,
        timed_out,
        round(time.perf_counter() - t0, 3),
        (log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else ""),
    )


def _build_single_pytest_cmd(
    norm_targets: List[str], basetemp: Path, junit_flags: List[str], extra_args: Sequence[str],
    coverage: bool, cov_json: Optional[Path], mirror_root: Path, mirror_dir: Path, env: Dict[str, str],
) -> List[str]:
    """Costruisce la riga di comando pytest single-process su mirror NVMe."""
    imp_args = [] if any(str(a).startswith("--import-mode") for a in extra_args) else ["--import-mode=importlib"]
    cmd: List[str] = [
        sys.executable, "-B", "-u", "-m", "pytest", *norm_targets,
        "-p", "no:cacheprovider", *imp_args, f"--basetemp={basetemp.as_posix()}",
        *junit_flags, *list(extra_args),
    ]
    if coverage and cov_json is not None:
        env["COVERAGE_FILE"] = str(mirror_root / ".coverage")
        cov_p = ["-p", "pytest_cov"] if env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") else []
        cmd.extend(cov_p + [f"--cov={resolve_coverage_source(mirror_dir)}", "--cov-branch", f"--cov-report=json:{cov_json.as_posix()}"])
    return cmd


def _assemble_detached_pytest_result(
    run_id: str, rc: int, timed_out: bool, duration_s: float, parsed: Dict[str, Any],
    norm_targets: List[str], mirror_dir: Path, mirror_cleaned: bool, log_file: Path,
    status_file: Path, repo_last_file: Path, last_file: Path, log_text: str,
) -> Dict[str, Any]:
    """Assemblea e salva atomicamente il verdetto detached pytest."""
    passed_ok = (rc == 0) and (not timed_out) and parsed["failed"] == 0 and parsed["errors"] == 0
    result: Dict[str, Any] = {
        "run_id": run_id, "status": "PASS" if passed_ok else ("TIMEOUT" if timed_out else "FAIL"),
        "success": passed_ok, "exit_code": rc, "timed_out": timed_out,
        "passed": parsed["passed"], "failed": parsed["failed"], "errors": parsed["errors"],
        "skipped": parsed["skipped"], "xfailed": parsed["xfailed"], "duration_s": duration_s,
        "targets": norm_targets, "mirror_dir": str(mirror_dir), "mirror_cleaned": mirror_cleaned,
        "log_file": str(log_file), "status_file": str(status_file), "tail": "\n".join(log_text.splitlines()[-40:]),
    }
    if "coverage" in parsed:
        result["coverage"] = parsed["coverage"]
    for out_p in (status_file, repo_last_file, last_file):
        atomic_write_json(out_p, result, indent=2, ensure_ascii=False)
    return result


def run_detached_pytest(
    workspace_root: Path,
    targets: Sequence[str] = ("tests",),
    extra_args: Sequence[str] = ("-q", "--tb=short"),
    timeout_sec: float = 180.0,
    coverage: bool = False,
    apply_overlay: bool = False,
    staging_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
    keep_mirror: bool = False,
    *,
    lane_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Esegue pytest in mirror NVMe su TEMP con sharding parallelo o fallback single-process."""
    ws_root, run_id = Path(workspace_root).resolve(), uuid.uuid4().hex[:10]
    diag_dir = Path(log_dir).resolve() if log_dir is not None else (Path(tempfile.gettempdir()) / "nk_diagnostics")
    diag_dir.mkdir(parents=True, exist_ok=True)
    lane_sfx = f"_{lane_id}" if lane_id else ""
    log_file, status_file = diag_dir / f"pytest_iso_{run_id}.log", diag_dir / f"pytest_iso_{run_id}_status.json"
    last_file, repo_last_file = diag_dir / "pytest_iso_last.json", diag_dir / f"pytest_iso_last_{repo_path_hash12(ws_root)}{lane_sfx}.json"
    mirror_dir = mirror_workspace_to_nvme(ws_root, staging_dir=staging_dir, apply_overlay=apply_overlay, lane_id=lane_id)
    if not apply_overlay and (mirror_dir / ".staging").is_dir():
        _sync_staging_tests_for_pytest(mirror_dir, ws_root)
    mirror_root, basetemp = mirror_dir.parent, mirror_dir.parent / "basetemp"
    basetemp.mkdir(parents=True, exist_ok=True)
    norm_targets = _resolve_mirror_targets(mirror_dir, ws_root, targets)
    cov_json: Optional[Path] = (mirror_root / "cov.json") if coverage else None
    junit_flags, junit_xml_path = _resolve_junit_flag_path(extra_args, mirror_root / f"junit_{run_id}.xml")
    env = _prepare_detached_env(mirror_dir, apply_overlay)
    parallel_files = should_use_parallel_shards(norm_targets, extra_args, mirror_dir, env)
    timed_out, rc, duration_s, mirror_cleaned, log_text = False, 1, 0.0, False, ""
    parsed: Dict[str, Any] = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0}
    try:
        if parallel_files:
            par = run_parallel_pytest_shards(
                mirror_dir=mirror_dir, mirror_root=mirror_root, test_files=parallel_files, base_env=env,
                extra_args=extra_args, timeout_sec=timeout_sec, coverage=coverage, cov_json=cov_json,
                junit_xml_path=junit_xml_path, log_file=log_file, kill_tree_fn=_kill_detached_tree,
                detached_flags=win32_detached_flags(),
            )
            rc, timed_out, duration_s, log_text = int(par["rc"]), bool(par["timed_out"]), float(par["duration_s"]), str(par["log_text"])
        else:
            cmd = _build_single_pytest_cmd(norm_targets, basetemp, junit_flags, extra_args, coverage, cov_json, mirror_root, mirror_dir, env)
            rc, timed_out, duration_s, log_text = _run_single_detached_proc(cmd, mirror_dir, env, log_file, timeout_sec)
        parsed = _extract_pytest_metrics(log_text, cov_json, junit_xml=junit_xml_path)
    finally:
        if not keep_mirror:
            mirror_cleaned = safe_rmtree(mirror_root)
    return _assemble_detached_pytest_result(
        run_id, rc, timed_out, duration_s, parsed, norm_targets, mirror_dir,
        mirror_cleaned, log_file, status_file, repo_last_file, last_file, log_text,
    )

# -*- coding: utf-8 -*-
"""Runner isolato NVMe per esecuzione pytest detached anti-crash Win32."""

from __future__ import annotations

import json, os, re, shutil, stat, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_common.io import atomic_write_json
from _internal.nk_common.paths import is_nk_proget_locale_path, normalize_rel_path
from _internal.nk_common.pytest_parallel import resolve_coverage_source, run_parallel_pytest_shards, should_use_parallel_shards
from _internal.nk_common.staging_manifest import is_reparse_entry as _is_reparse_entry
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest, parse_pytest_summary

WIN32_CREATE_NEW_PROCESS_GROUP: int = 0x00000200
WIN32_CREATE_NO_WINDOW: int = 0x08000000
WIN32_DETACHED_FLAGS: int = (WIN32_CREATE_NEW_PROCESS_GROUP | WIN32_CREATE_NO_WINDOW) if sys.platform == "win32" else 0
_MIRROR_DIRS: Sequence[str] = ("scripts", "tests", ".agents", "nk_genome", "nk_docs_and_setup", "nk_tracking", "src", "src_app", "app", "config", "deploy", "static", "templates", "frontend", "migrations")
_NUMBERED_BLUEPRINT_DIR_RE = re.compile(r"^\d{2}_[A-Za-z0-9_]+$")
_ROOT_FILES: Set[str] = {"pytest.ini", "pyproject.toml", "setup.cfg", "VERSION", ".gitignore"}
_ROOT_ALLOWED_SUFFIXES: Tuple[str, ...] = (".md", ".json", ".bat", ".cmd", ".sh", ".txt", ".ini", ".cfg", ".toml", ".yml", ".yaml")
_ROOT_EXCLUDED_SUFFIXES: Tuple[str, ...] = (".db", ".sqlite", ".sqlite3", ".env", ".zip", ".wal", ".shm", ".key")
_MIRROR_EXCLUDED_SUFFIXES: Tuple[str, ...] = (".pyc", ".pyo", ".zip", ".key", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3")
_IGNORED: Set[str] = {"__pycache__", ".pytest_cache", ".git", ".venv", "venv", "node_modules", ".wal"}


def win32_detached_flags(extra_flags: int = 0) -> int:
    """Restituisce i flag Win32 detached combinati con eventuali flag extra."""
    return (WIN32_DETACHED_FLAGS | int(extra_flags)) if sys.platform == "win32" else 0


def is_temp_workspace(path: Path) -> bool:
    """Verifica se un percorso risiede dentro una cartella temporanea locale."""
    cand = Path(path).resolve()
    roots = [Path(tempfile.gettempdir()).resolve()] + [Path(v).resolve() for k in ("TEMP", "TMP", "TMPDIR") if (v := os.environ.get(k, "").strip())]
    if la := os.environ.get("LOCALAPPDATA", "").strip():
        roots.append((Path(la) / "Temp").resolve())
    return any(cand == r or cand.is_relative_to(r) for r in roots)


def _handle_rm_readonly(func: Any, path: str, _exc: Any) -> None:
    """Rimuove il bit sola lettura su Windows durante la pulizia."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def safe_rmtree(target_dir: Path) -> bool:
    """Elimina ricorsivamente una cartella gestendo errori e lock Windows."""
    if not target_dir.exists():
        return True
    kw: Dict[str, Any] = {"onexc": _handle_rm_readonly} if sys.version_info >= (3, 12) else {"onerror": _handle_rm_readonly}
    for attempt in range(5):
        try:
            shutil.rmtree(target_dir, **kw)
            return True
        except OSError:
            time.sleep(0.04 * (attempt + 1))
    return not target_dir.exists()


def _load_deleted_set(staging_dir: Path) -> Set[str]:
    """Carica i percorsi relativi marcati per rimozione in .deleted_files.json tramite SSOT."""
    try:
        items = parse_deleted_files_manifest(staging_dir / ".deleted_files.json")
    except (OSError, ValueError):
        return set()
    return {norm for raw in items if (norm := normalize_rel_path(raw))}


def _is_safe_local_dir(cand: Path, parent_dir: Path) -> bool:
    """Verifica che cand sia sottocartella reale diretta di parent_dir senza escape."""
    try:
        if ".." in [seg for seg in cand.parts if seg not in ("\\", "/")] or _is_reparse_entry(cand) or not cand.exists() or not cand.is_dir():
            return False
        p_res, c_res = Path(parent_dir).resolve(), Path(cand).resolve()
        return c_res != p_res and c_res.parent == p_res and c_res.is_relative_to(p_res)
    except OSError:
        return False


def _is_mirror_ignored_name(name: str, src_p: Path, in_trk: bool) -> bool:
    """Verifica se un nome entry deve essere escluso dal mirror NVMe."""
    low = name.lower()
    return (
        name in _IGNORED or low.endswith(_MIRROR_EXCLUDED_SUFFIXES)
        or low == ".env" or low.startswith((".env.", ".coverage"))
        or (in_trk and name in ("sessions", "handoff")) or _is_reparse_entry(src_p / name)
    )


def _build_mirror_ignore(ws_root: Path) -> Callable[[str, List[str]], Set[str]]:
    """Esclude cache, .git, zip/segreti/db, reparse point e tracking di sessione."""
    trk_root = (ws_root / "nk_tracking").resolve()

    def _ignore(src_dir: str, names: List[str]) -> Set[str]:
        src_p = Path(src_dir).resolve()
        in_trk = src_p == trk_root or trk_root in src_p.parents
        return {n for n in names if _is_mirror_ignored_name(n, src_p, in_trk)}

    return _ignore


def _copy_tree_overlay(src_dir: Path, dst_dir: Path, ignore_fn: Callable[[str, List[str]], Set[str]]) -> None:
    """Copia ricorsivamente i file da src_dir a dst_dir sovrascrivendo i file esistenti."""
    for root, dirs, files in os.walk(src_dir, followlinks=False):
        rel_root = Path(root).relative_to(src_dir)
        ignored = ignore_fn(root, list(dirs) + list(files))
        dirs[:] = [d for d in dirs if d not in ignored and not _is_reparse_entry(Path(root) / d)]
        for fname in files:
            if fname in ignored or fname in (".gitkeep", ".deleted_files.json") or _is_reparse_entry(Path(root) / fname):
                continue
            dst_f = dst_dir / rel_root / fname
            dst_f.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(root) / fname, dst_f)


def _apply_staging_overlay_to_mirror(mirror_dir: Path, stg_dir: Path, ws_root: Path) -> None:
    """Sovrappone i file staged sul mirror e applica i tombstone da .deleted_files.json."""
    _copy_tree_overlay(stg_dir, mirror_dir, _build_mirror_ignore(ws_root))
    m_res = mirror_dir.resolve()
    for rel_del in _load_deleted_set(stg_dir):
        cand = (mirror_dir / rel_del).resolve()
        if cand != m_res and cand.is_relative_to(m_res):
            if cand.is_dir():
                safe_rmtree(cand)
            elif cand.is_file() or cand.is_symlink():
                cand.unlink(missing_ok=True)


def _sync_staging_tests_for_pytest(mirror_dir: Path, ws_root: Path) -> None:
    """Allinea mirror_dir/tests con .staging/tests evitando conflitti ImportPathMismatch."""
    stg_dir = mirror_dir / ".staging"
    if (stg_tests := stg_dir / "tests").is_dir():
        _copy_tree_overlay(stg_tests, mirror_dir / "tests", _build_mirror_ignore(ws_root))
    t_res = (mirror_dir / "tests").resolve()
    for rel_del in _load_deleted_set(stg_dir):
        if rel_del.startswith("tests/"):
            cand = (mirror_dir / rel_del).resolve()
            if cand != t_res and cand.is_relative_to(t_res) and cand.exists():
                cand.unlink(missing_ok=True) if cand.is_file() else safe_rmtree(cand)


def _iter_mirror_subdir_names(proj_root: Path) -> List[str]:
    """Restituisce le sottodirectory da copiare includendo eventuali blueprint numerati."""
    names, seen = list(_MIRROR_DIRS), set(_MIRROR_DIRS)
    try:
        entries = sorted(proj_root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return names
    for entry in entries:
        if entry.name not in seen and not _is_reparse_entry(entry) and entry.is_dir() and _NUMBERED_BLUEPRINT_DIR_RE.match(entry.name):
            names.append(entry.name)
            seen.add(entry.name)
    return names


def _is_sibling_projects_parent(parent_dir: Path) -> bool:
    """Identifica i contenitori di progetti fratelli (NK_External_Projects o NK Proget/Locale)."""
    return parent_dir.name == "NK_External_Projects" or (parent_dir.name.lower() == "locale" and is_nk_proget_locale_path(parent_dir))


def _mirror_project_base(proj_root: Path, dst_dir: Path) -> None:
    """Copia le directory autorizzate e i file radice sicuri di un progetto nel mirror."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    ignore_fn = _build_mirror_ignore(proj_root)
    for rel_dir in _iter_mirror_subdir_names(proj_root):
        if _is_safe_local_dir(src_sub := proj_root / rel_dir, proj_root):
            shutil.copytree(src_sub, dst_dir / rel_dir, ignore=ignore_fn, dirs_exist_ok=True)
    for entry in proj_root.iterdir():
        if not _is_reparse_entry(entry) and entry.is_file() and not entry.name.startswith((".coverage", ".env")) and not entry.name.lower().endswith(_ROOT_EXCLUDED_SUFFIXES) and (entry.name in _ROOT_FILES or entry.suffix.lower() in _ROOT_ALLOWED_SUFFIXES):
            shutil.copy2(entry, dst_dir / entry.name)


def mirror_workspace_to_nvme(workspace_root: Path, staging_dir: Optional[Path] = None, prefix: str = "nk_pytest_iso_", apply_overlay: bool = False, mirror_siblings: bool = True, overlay_siblings: bool = False) -> Path:
    """Crea una copia isolata del workspace su NVMe in TEMP restituendo mirror_dir."""
    ws_root = Path(workspace_root).resolve()
    mirror_root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    mirror_dir = mirror_root / (ws_root.name or "NK_Hub")
    _mirror_project_base(ws_root, mirror_dir)
    stg_src = Path(staging_dir) if staging_dir is not None else (ws_root / ".staging")
    if stg_src.exists() and not _is_reparse_entry(stg_src) and stg_src.is_dir():
        stg_res = stg_src.resolve()
        if apply_overlay:
            _apply_staging_overlay_to_mirror(mirror_dir, stg_res, ws_root)
        else:
            shutil.copytree(stg_res, mirror_dir / ".staging", ignore=_build_mirror_ignore(ws_root), dirs_exist_ok=True)
    if mirror_siblings and _is_sibling_projects_parent(ws_root.parent):
        for sib in ws_root.parent.iterdir():
            if sib != ws_root and not sib.name.startswith(".") and _is_safe_local_dir(sib, ws_root.parent):
                sib_dst = mirror_root / sib.name
                _mirror_project_base(sib, sib_dst)
                sib_stg = sib / ".staging"
                if apply_overlay and overlay_siblings and _is_safe_local_dir(sib_stg, sib):
                    _apply_staging_overlay_to_mirror(sib_dst, sib_stg.resolve(), sib)
    return mirror_dir


def _strip_dot_slash_prefix(norm: str) -> str:
    """Rimuove prefissi './' ripetuti senza corrompere directory puntate come '.staging/'."""
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _resolve_mirror_targets(mirror_dir: Path, ws_root: Path, targets: Sequence[str]) -> List[str]:
    """Normalizza i target pytest relativi a mirror_dir rimuovendo prefissi .staging/."""
    ws_prefix = ws_root.as_posix().rstrip("/") + "/"
    resolved: List[str] = []
    for raw_t in (list(targets) if targets else ["tests"]):
        norm = str(raw_t).strip().replace("\\", "/")
        if not norm or not norm.lstrip("./"):
            continue
        if norm.lower().startswith(ws_prefix.lower()):
            norm = norm[len(ws_prefix) :].lstrip("/")
        else:
            norm = _strip_dot_slash_prefix(norm)
            if norm.startswith(f"{mirror_dir.name}/"):
                norm = norm[len(mirror_dir.name) + 1 :]
        if norm.startswith(".staging/tests/") or norm == ".staging/tests":
            norm = norm[len(".staging/") :]
        resolved.append(norm)
    return resolved or ["tests"]


def _kill_detached_tree(pid: int) -> None:
    """Termina processo figlio e discendenti su timeout senza bloccare conhost."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=win32_detached_flags(), timeout=2.0)
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


def _extract_pytest_metrics(log_text: str, cov_json: Optional[Path], junit_xml: Optional[Path] = None) -> Dict[str, Any]:
    """Estrae conteggi Pytest tramite SSOT JUnit XML/bottom-up e metriche coverage JSON."""
    try:
        summary = parse_pytest_summary(log_text, "", junit_xml_path=junit_xml)
    except (OSError, ValueError):
        summary = parse_pytest_summary(log_text, "", junit_xml_path=None)
    metrics: Dict[str, Any] = {
        "passed": int(summary.get("passed", 0)), "failed": int(summary.get("failed", 0)),
        "errors": int(summary.get("errors", 0)), "skipped": int(summary.get("skipped", 0)),
        "xfailed": int(summary.get("xfailed", 0)),
    }
    if cov_json is not None and cov_json.is_file():
        try:
            tot = json.loads(cov_json.read_text(encoding="utf-8")).get("totals", {})
            if isinstance(tot, dict) and tot:
                ns, cl = float(tot.get("num_statements", 0) or 0), float(tot.get("covered_lines", 0) or 0)
                nb, cb = float(tot.get("num_branches", 0) or 0), float(tot.get("covered_branches", 0) or 0)
                sp, bp, cp = tot.get("percent_statements_covered"), tot.get("percent_branches_covered"), tot.get("percent_covered")
                metrics["coverage"] = {
                    "statement_coverage_pct": round(float(sp if sp is not None else ((cl / ns) * 100.0 if ns else 0.0)), 2),
                    "true_branch_coverage_pct": round(float(bp if bp is not None else ((cb / nb) * 100.0 if nb else 0.0)), 2),
                    "combined_coverage_pct": round(float(cp if cp is not None else 0.0), 2),
                }
        except (OSError, ValueError, TypeError):
            pass
    return metrics


def _resolve_junit_flag_path(extra_args: Sequence[str], default_junit: Path) -> Tuple[List[str], Optional[Path]]:
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
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    for k in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"):
        env.pop(k, None)
    has_conftest = (mirror_dir / "tests" / "conftest.py").is_file()
    py_parts = [str(mirror_dir)] if (has_conftest or apply_overlay or not (mirror_dir / ".staging").is_dir()) else [str(mirror_dir / ".staging"), str(mirror_dir)]
    env["PYTHONPATH"] = os.pathsep.join(py_parts)
    return env


def _run_single_detached_proc(cmd: List[str], mirror_dir: Path, env: Dict[str, str], log_file: Path, timeout_sec: float) -> Tuple[int, bool, float, str]:
    """Esegue un singolo processo pytest detached nel mirror NVMe con gestione timeout."""
    timed_out, rc = False, 1
    t0, deadline = time.perf_counter(), time.perf_counter() + max(0.05, float(timeout_sec))
    with open(log_file, "w", encoding="utf-8", errors="replace") as log_fh:
        proc = subprocess.Popen(cmd, cwd=str(mirror_dir), env=env, stdin=subprocess.DEVNULL, stdout=log_fh, stderr=subprocess.STDOUT, creationflags=win32_detached_flags(), shell=False)
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
    return rc, timed_out, round(time.perf_counter() - t0, 3), (log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else "")


def run_detached_pytest(
    workspace_root: Path, targets: Sequence[str] = ("tests",), extra_args: Sequence[str] = ("-q", "--tb=short"),
    timeout_sec: float = 180.0, coverage: bool = False, apply_overlay: bool = False,
    staging_dir: Optional[Path] = None, log_dir: Optional[Path] = None, keep_mirror: bool = False,
) -> Dict[str, Any]:
    """Esegue pytest in mirror NVMe su TEMP con sharding parallelo o fallback single-process."""
    ws_root, run_id = Path(workspace_root).resolve(), uuid.uuid4().hex[:10]
    diag_dir = (Path(log_dir).resolve() if log_dir is not None else (Path(tempfile.gettempdir()) / "nk_diagnostics"))
    diag_dir.mkdir(parents=True, exist_ok=True)
    log_file, status_file, last_file = diag_dir / f"pytest_iso_{run_id}.log", diag_dir / f"pytest_iso_{run_id}_status.json", diag_dir / "pytest_iso_last.json"

    mirror_dir = mirror_workspace_to_nvme(ws_root, staging_dir=staging_dir, apply_overlay=apply_overlay)
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
            par = run_parallel_pytest_shards(mirror_dir=mirror_dir, mirror_root=mirror_root, test_files=parallel_files, base_env=env, extra_args=extra_args, timeout_sec=timeout_sec, coverage=coverage, cov_json=cov_json, junit_xml_path=junit_xml_path, log_file=log_file, kill_tree_fn=_kill_detached_tree, detached_flags=win32_detached_flags())
            rc, timed_out, duration_s, log_text = int(par["rc"]), bool(par["timed_out"]), float(par["duration_s"]), str(par["log_text"])
        else:
            imp_args = [] if any(str(a).startswith("--import-mode") for a in extra_args) else ["--import-mode=importlib"]
            cmd: List[str] = [sys.executable, "-B", "-u", "-m", "pytest", *norm_targets, "-p", "no:cacheprovider", *imp_args, f"--basetemp={basetemp.as_posix()}", *junit_flags, *list(extra_args)]
            if coverage and cov_json is not None:
                env["COVERAGE_FILE"] = str(mirror_root / ".coverage")
                cmd.extend((["-p", "pytest_cov"] if env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") else []) + [f"--cov={resolve_coverage_source(mirror_dir)}", "--cov-branch", f"--cov-report=json:{cov_json.as_posix()}"])
            rc, timed_out, duration_s, log_text = _run_single_detached_proc(cmd, mirror_dir, env, log_file, timeout_sec)
        parsed = _extract_pytest_metrics(log_text, cov_json, junit_xml=junit_xml_path)
    finally:
        if not keep_mirror:
            mirror_cleaned = safe_rmtree(mirror_root)

    passed_ok = (rc == 0) and (not timed_out) and parsed["failed"] == 0 and parsed["errors"] == 0
    result: Dict[str, Any] = {
        "run_id": run_id, "status": "PASS" if passed_ok else ("TIMEOUT" if timed_out else "FAIL"), "success": passed_ok,
        "exit_code": rc, "timed_out": timed_out, "passed": parsed["passed"], "failed": parsed["failed"],
        "errors": parsed["errors"], "skipped": parsed["skipped"], "xfailed": parsed["xfailed"], "duration_s": duration_s,
        "targets": norm_targets, "mirror_dir": str(mirror_dir), "mirror_cleaned": mirror_cleaned,
        "log_file": str(log_file), "status_file": str(status_file), "tail": "\n".join(log_text.splitlines()[-40:]),
    }
    if "coverage" in parsed:
        result["coverage"] = parsed["coverage"]
    atomic_write_json(status_file, result, indent=2, ensure_ascii=False)
    atomic_write_json(last_file, result, indent=2, ensure_ascii=False)
    return result

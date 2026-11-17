# -*- coding: utf-8 -*-
"""Runner isolato NVMe per esecuzione pytest detached anti-crash Win32."""

from __future__ import annotations

import json, os, re, shutil, stat, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from _internal.nk_common.io import atomic_write_json

WIN32_CREATE_NEW_PROCESS_GROUP: int = 0x00000200
WIN32_CREATE_NO_WINDOW: int = 0x08000000
WIN32_DETACHED_FLAGS: int = (WIN32_CREATE_NEW_PROCESS_GROUP | WIN32_CREATE_NO_WINDOW) if sys.platform == "win32" else 0
_MIRROR_DIRS: Sequence[str] = ("scripts", "tests", ".agents", "nk_genome", "nk_docs_and_setup", "nk_tracking", "src", "src_app", "app", "config")
_ROOT_FILES: Set[str] = {"pytest.ini", "pyproject.toml", "setup.cfg", "VERSION", ".gitignore"}
_IGNORED: Set[str] = {"__pycache__", ".pytest_cache", ".git", ".venv", "venv", "node_modules", ".wal"}


def win32_detached_flags(extra_flags: int = 0) -> int:
    """Restituisce i flag Win32 detached combinati con eventuali flag extra."""
    return (WIN32_DETACHED_FLAGS | int(extra_flags)) if sys.platform == "win32" else 0


def is_temp_workspace(path: Path) -> bool:
    """Verifica se un percorso risiede dentro una cartella temporanea locale."""
    cand = Path(path).resolve()
    roots: List[Path] = [Path(tempfile.gettempdir()).resolve()]
    for k in ("TEMP", "TMP", "TMPDIR"):
        if raw := os.environ.get(k, "").strip():
            roots.append(Path(raw).resolve())
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
    """Carica i percorsi relativi marcati per rimozione in .deleted_files.json."""
    manifest = staging_dir / ".deleted_files.json"
    if not manifest.is_file():
        return set()
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        items = raw.get("deleted_files", []) if isinstance(raw, dict) else raw
        return {str(it).replace("\\", "/").lstrip("/") for it in items if str(it).strip()} if isinstance(items, list) else set()
    except (OSError, ValueError):
        return set()


def _build_mirror_ignore(ws_root: Path) -> Callable[[str, List[str]], Set[str]]:
    """Costruisce il filtro per escludere cache, .git, venv e tracking di sessione."""
    trk_root = (ws_root / "nk_tracking").resolve()

    def _ignore(src_dir: str, names: List[str]) -> Set[str]:
        src_p = Path(src_dir).resolve()
        in_trk = src_p == trk_root or trk_root in src_p.parents
        return {n for n in names if n in _IGNORED or n.endswith((".pyc", ".pyo")) or n.startswith(".coverage") or (in_trk and n in ("sessions", "handoff"))}

    return _ignore


def _copy_tree_overlay(src_dir: Path, dst_dir: Path, ignore_fn: Callable[[str, List[str]], Set[str]]) -> None:
    """Copia ricorsivamente i file da src_dir a dst_dir sovrascrivendo i file esistenti."""
    for root, dirs, files in os.walk(src_dir):
        rel_root = Path(root).relative_to(src_dir)
        ignored = ignore_fn(root, list(dirs) + list(files))
        dirs[:] = [d for d in dirs if d not in ignored]
        for fname in files:
            if fname in ignored or fname in (".gitkeep", ".deleted_files.json"):
                continue
            dst_f = dst_dir / rel_root / fname
            dst_f.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(root) / fname, dst_f)


def _apply_staging_overlay_to_mirror(mirror_dir: Path, stg_dir: Path, ws_root: Path) -> None:
    """Sovrappone i file staged sul mirror e applica i tombstone da .deleted_files.json."""
    _copy_tree_overlay(stg_dir, mirror_dir, _build_mirror_ignore(ws_root))
    for rel_del in _load_deleted_set(stg_dir):
        cand = (mirror_dir / rel_del).resolve()
        if cand.is_relative_to(mirror_dir.resolve()):
            if cand.is_dir():
                safe_rmtree(cand)
            elif cand.is_file() or cand.is_symlink():
                cand.unlink(missing_ok=True)


def _sync_staging_tests_for_pytest(mirror_dir: Path, ws_root: Path) -> None:
    """Allinea mirror_dir/tests con .staging/tests evitando conflitti ImportPathMismatch."""
    stg_dir = mirror_dir / ".staging"
    stg_tests = stg_dir / "tests"
    if stg_tests.is_dir():
        _copy_tree_overlay(stg_tests, mirror_dir / "tests", _build_mirror_ignore(ws_root))
    for rel_del in _load_deleted_set(stg_dir):
        if rel_del.startswith("tests/"):
            cand = (mirror_dir / rel_del).resolve()
            if cand.is_relative_to((mirror_dir / "tests").resolve()) and cand.exists():
                cand.unlink(missing_ok=True) if cand.is_file() else safe_rmtree(cand)


def mirror_workspace_to_nvme(
    workspace_root: Path, staging_dir: Optional[Path] = None, prefix: str = "nk_pytest_iso_", apply_overlay: bool = False,
) -> Path:
    """Crea una copia isolata del workspace su NVMe in TEMP restituendo mirror_dir."""
    ws_root = Path(workspace_root).resolve()
    mirror_root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    mirror_dir = mirror_root / (ws_root.name or "NK_Hub")
    mirror_dir.mkdir(parents=True, exist_ok=True)
    ignore_fn = _build_mirror_ignore(ws_root)
    for rel_dir in _MIRROR_DIRS:
        if (src_sub := ws_root / rel_dir).is_dir():
            shutil.copytree(src_sub, mirror_dir / rel_dir, ignore=ignore_fn, dirs_exist_ok=True)
    for entry in ws_root.iterdir():
        if entry.is_file() and not entry.name.startswith(".coverage") and (entry.name in _ROOT_FILES or entry.suffix.lower() in (".md", ".json")):
            shutil.copy2(entry, mirror_dir / entry.name)
    stg_src = Path(staging_dir).resolve() if staging_dir is not None else (ws_root / ".staging")
    if stg_src.is_dir():
        if apply_overlay:
            _apply_staging_overlay_to_mirror(mirror_dir, stg_src, ws_root)
        else:
            shutil.copytree(stg_src, mirror_dir / ".staging", ignore=ignore_fn, dirs_exist_ok=True)
    return mirror_dir


def _resolve_mirror_targets(mirror_dir: Path, ws_root: Path, targets: Sequence[str]) -> List[str]:
    """Normalizza i target pytest relativi a mirror_dir rimuovendo prefissi .staging/."""
    raw_list = list(targets) if targets else ["tests"]
    ws_prefix = ws_root.as_posix().rstrip("/") + "/"
    resolved: List[str] = []
    for raw_t in raw_list:
        norm = str(raw_t).strip().replace("\\", "/").lstrip("./")
        if not norm:
            continue
        if norm.lower().startswith(ws_prefix.lower()):
            norm = norm[len(ws_prefix) :]
        elif norm.startswith(f"{mirror_dir.name}/"):
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


def _extract_pytest_metrics(log_text: str, cov_json: Optional[Path]) -> Dict[str, Any]:
    """Estrae conteggi Pytest dal log e metriche coverage dal file JSON."""
    metrics: Dict[str, Any] = {k: (int(m.group(1)) if (m := re.search(pat, log_text)) else 0) for k, pat in (("passed", r"(\d+)\s+passed"), ("failed", r"(\d+)\s+failed"), ("errors", r"(\d+)\s+errors?"), ("skipped", r"(\d+)\s+skipped"), ("xfailed", r"(\d+)\s+xfailed"))}
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


def run_detached_pytest(
    workspace_root: Path, targets: Sequence[str] = ("tests",), extra_args: Sequence[str] = ("-q", "--tb=short"),
    timeout_sec: float = 180.0, coverage: bool = False, apply_overlay: bool = False,
    staging_dir: Optional[Path] = None, log_dir: Optional[Path] = None, keep_mirror: bool = False,
) -> Dict[str, Any]:
    """Esegue pytest in mirror NVMe su TEMP con subprocess detached e status JSON atomico."""
    ws_root, run_id = Path(workspace_root).resolve(), uuid.uuid4().hex[:10]
    diag_dir = Path(log_dir).resolve() if log_dir is not None else (Path(tempfile.gettempdir()) / "nk_diagnostics")
    diag_dir.mkdir(parents=True, exist_ok=True)
    log_file, status_file, last_file = diag_dir / f"pytest_iso_{run_id}.log", diag_dir / f"pytest_iso_{run_id}_status.json", diag_dir / "pytest_iso_last.json"

    mirror_dir = mirror_workspace_to_nvme(ws_root, staging_dir=staging_dir, apply_overlay=apply_overlay)
    if not apply_overlay and (mirror_dir / ".staging").is_dir():
        _sync_staging_tests_for_pytest(mirror_dir, ws_root)
    mirror_root, basetemp = mirror_dir.parent, mirror_dir.parent / "basetemp"
    basetemp.mkdir(parents=True, exist_ok=True)
    norm_targets = _resolve_mirror_targets(mirror_dir, ws_root, targets)
    cov_json: Optional[Path] = (mirror_root / "cov.json") if coverage else None

    env = os.environ.copy()
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    for k in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COVERAGE_PROCESS_START"):
        env.pop(k, None)
    has_conftest = (mirror_dir / "tests" / "conftest.py").is_file()
    py_parts = [str(mirror_dir)] if (has_conftest or apply_overlay or not (mirror_dir / ".staging").is_dir()) else [str(mirror_dir / ".staging"), str(mirror_dir)]
    env["PYTHONPATH"] = os.pathsep.join(py_parts)

    imp_args = [] if any(str(a).startswith("--import-mode") for a in extra_args) else ["--import-mode=importlib"]
    cmd: List[str] = [sys.executable, "-B", "-u", "-m", "pytest", *norm_targets, "-p", "no:cacheprovider", *imp_args, f"--basetemp={basetemp.as_posix()}", *list(extra_args)]
    if coverage and cov_json is not None:
        env["COVERAGE_FILE"] = str(mirror_root / ".coverage")
        cmd.extend((["-p", "pytest_cov"] if env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") else []) + ["--cov=scripts", "--cov-branch", f"--cov-report=json:{cov_json.as_posix()}"])

    timed_out, rc, duration_s, mirror_cleaned, log_text = False, 1, 0.0, False, ""
    parsed: Dict[str, Any] = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0}
    try:
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
                    except Exception:
                        pass
                    break
                time.sleep(0.05)
            else:
                rc = int(polled)
        duration_s = round(time.perf_counter() - t0, 3)
        log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else ""
        parsed = _extract_pytest_metrics(log_text, cov_json)
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

# -*- coding: utf-8 -*-
"""Helper di mirror NVMe, overlay .staging/ e normalizzazione target per pytest isolato."""

from __future__ import annotations

import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_common.lane_paths import (
    is_lane_container_entry,
    strip_staging_rel_parts,
)
from _internal.nk_common.nvme_base_cache import (
    clone_nvme_base_to_mirror,
    sync_nvme_base_cache,
)
from _internal.nk_common.paths import is_nk_proget_locale_path, normalize_rel_path
from _internal.nk_common.staging_manifest import is_reparse_entry as _is_reparse_entry
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

_MIRROR_DIRS: Sequence[str] = (
    "scripts", "tests", ".agents", "nk_genome", "nk_docs_and_setup", "nk_tracking",
    "src", "src_app", "app", "config", "deploy", "static", "templates", "frontend", "migrations",
    "public", "pages", "components", "lib", "hooks", "styles", "e2e", "playwright",
    "packages", "apps", "client", "web", "server", "api", "shared", "prisma", "__tests__",
    "types", "utils", "assets",
)
_NUMBERED_BLUEPRINT_DIR_RE = re.compile(r"^\d{2}_[A-Za-z0-9_]+$")
_ROOT_FILES: Set[str] = {"pytest.ini", "pyproject.toml", "setup.cfg", "VERSION", ".gitignore", "conftest.py"}
_ROOT_ALLOWED_SUFFIXES: Tuple[str, ...] = (
    ".md", ".json", ".bat", ".cmd", ".sh", ".txt", ".ini", ".cfg", ".toml", ".yml", ".yaml",
    ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx", ".html", ".css", ".lock",
)
_ROOT_EXCLUDED_SUFFIXES: Tuple[str, ...] = (
    ".db", ".sqlite", ".sqlite3", ".env", ".zip", ".wal", ".shm", ".key",
)
_MIRROR_EXCLUDED_SUFFIXES: Tuple[str, ...] = (
    ".pyc", ".pyo", ".zip", ".key", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3",
)
_IGNORED: Set[str] = {"__pycache__", ".pytest_cache", ".git", ".venv", "venv", "node_modules", ".wal"}


def _handle_rm_readonly(func: Any, path: str, _exc: Any) -> None:
    """Rimuove il bit sola lettura su Windows durante la pulizia."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _unlink_reparse_only(path: Path) -> bool:
    """Rimuove esclusivamente una junction NTFS o symlink senza scendere nella target."""
    if not (_is_reparse_entry(path) or path.is_symlink()):
        return False
    try:
        os.rmdir(path)
    except OSError:
        os.unlink(path)
    return True


def _prepare_rmtree_target(target_dir: Path) -> bool:
    """Scollega eventuali junction/reparse point; True se target_dir e gia assente o scollegata."""
    if not (target_dir.exists() or target_dir.is_symlink() or _is_reparse_entry(target_dir)):
        return True
    if _unlink_reparse_only(target_dir):
        return not target_dir.exists()
    for w_root, dirs, files in os.walk(target_dir, topdown=True, followlinks=False):
        w_p = Path(w_root)
        dirs[:] = [d for d in dirs if not _unlink_reparse_only(w_p / d)]
        for fn in files:
            _unlink_reparse_only(w_p / fn)
    return False


def safe_rmtree(target_dir: Path) -> bool:
    """Elimina ricorsivamente una cartella scollegando prima eventuali junction/reparse point."""
    import sys

    if _prepare_rmtree_target(target_dir):
        return True
    kw: Dict[str, Any] = (
        {"onexc": _handle_rm_readonly}
        if sys.version_info >= (3, 12)
        else {"onerror": _handle_rm_readonly}
    )
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


def _build_mirror_ignore(ws_root: Path, *, exclude_lanes: bool = False, stg_dir: Optional[Path] = None) -> Callable[[str, List[str]], Set[str]]:
    """Esclude cache, .git, zip/segreti/db, reparse point e opzionalmente lanes/ al depth 0."""
    trk_root = (ws_root / "nk_tracking").resolve()
    stg_root = stg_dir.resolve() if stg_dir is not None else None

    def _ignore(src_dir: str, names: List[str]) -> Set[str]:
        src_p = Path(src_dir).resolve()
        in_trk = src_p == trk_root or trk_root in src_p.parents
        at_stg_top = exclude_lanes and stg_root is not None and src_p == stg_root
        return {n for n in names if _is_mirror_ignored_name(n, src_p, in_trk) or (at_stg_top and is_lane_container_entry((n,)))}

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


def _apply_staging_overlay_to_mirror(mirror_dir: Path, stg_dir: Path, ws_root: Path, *, exclude_lanes: bool = False) -> None:
    """Sovrappone i file staged sul mirror e applica i tombstone da .deleted_files.json."""
    _copy_tree_overlay(stg_dir, mirror_dir, _build_mirror_ignore(ws_root, exclude_lanes=exclude_lanes, stg_dir=stg_dir))
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


def _is_mirror_root_file(entry: Path) -> bool:
    """True per i file radice sicuri autorizzati nel mirror NVMe."""
    low = entry.name.lower()
    return not entry.name.startswith((".coverage", ".env")) and not low.endswith(_ROOT_EXCLUDED_SUFFIXES) and (entry.name in _ROOT_FILES or entry.suffix.lower() in _ROOT_ALLOWED_SUFFIXES)


def _mirror_project_base(proj_root: Path, dst_dir: Path) -> None:
    """Copia base progetto tramite NVMe Base Cache RO + clone indipendente (zero os.link)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    ignore_fn, subdir_names = _build_mirror_ignore(proj_root), _iter_mirror_subdir_names(proj_root)
    try:
        clone_nvme_base_to_mirror(sync_nvme_base_cache(proj_root, subdir_names, ignore_fn, _is_mirror_root_file, _is_safe_local_dir), dst_dir, repo_root_hint=proj_root)
        return
    except OSError:
        pass
    for rel_dir in subdir_names:
        if _is_safe_local_dir(src_sub := proj_root / rel_dir, proj_root):
            shutil.copytree(src_sub, dst_dir / rel_dir, ignore=ignore_fn, dirs_exist_ok=True)
    for entry in proj_root.iterdir():
        if not _is_reparse_entry(entry) and entry.is_file() and _is_mirror_root_file(entry):
            shutil.copy2(entry, dst_dir / entry.name)


def _resolve_mirror_targets(mirror_dir: Path, ws_root: Path, targets: Sequence[str]) -> List[str]:
    """Normalizza i target pytest relativi a mirror_dir rimuovendo prefissi .staging/[lanes/<id>/]."""
    ws_prefix = ws_root.as_posix().rstrip("/") + "/"
    resolved: List[str] = []
    for raw_t in (list(targets) if targets else ["tests"]):
        norm = str(raw_t).strip().replace("\\", "/")
        if not norm or not norm.lstrip("./"):
            continue
        if norm.lower().startswith(ws_prefix.lower()):
            norm = norm[len(ws_prefix) :].lstrip("/")
        else:
            while norm.startswith("./"):
                norm = norm[2:]
            if norm.startswith(f"{mirror_dir.name}/"):
                norm = norm[len(mirror_dir.name) + 1 :]
        idx, rel_parts, _lane = strip_staging_rel_parts(Path(norm).parts)
        if idx >= 0 and rel_parts and rel_parts[0] == "tests":
            norm = "/".join(rel_parts)
        elif idx >= 0 and _lane is not None and rel_parts:
            norm = ".staging/" + "/".join(rel_parts)
        resolved.append(norm)
    return resolved or ["tests"]

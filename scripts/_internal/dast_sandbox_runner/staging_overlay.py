"""Preparazione Shadow Sandbox da root e overlay .staging/ per verifica E2E."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

from _internal.nk_common.isolated_test_runner import _MIRROR_DIRS, _is_reparse_entry
from _internal.nk_common.lane_leases import allocate_lane_loopback_port
from _internal.nk_common.lane_paths import is_lane_container_entry, validate_lane_id
from _internal.nk_common.nvme_mirror_helpers import _ROOT_ALLOWED_SUFFIXES, _ROOT_FILES, safe_rmtree
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

from .sandbox_fs import (
    ShadowSandbox,
    _resolve_confined_sandbox_path,
    _strip_builder_holdouts_from_sandbox,
)


def _is_blocked_reparse(entry: Path, base_resolved: Path) -> bool:
    """Rileva symlink esterni, NTFS junction o reparse point non confinati."""
    if not _is_reparse_entry(entry):
        return False
    if not entry.is_symlink():
        return True
    try:
        return not entry.resolve().is_relative_to(base_resolved)
    except OSError:
        return True


def _iter_safe_walk_files(dir_path: Path) -> List[Path]:
    """Elenca i file regolari in dir_path evitando symlink e junction Win32."""
    files_found: List[Path] = []
    for walk_root, dirs, files in os.walk(dir_path, followlinks=False):
        dirs[:] = [d for d in dirs if not _is_reparse_entry(Path(walk_root) / d)]
        for fname in files:
            sub = Path(walk_root) / fname
            if not _is_reparse_entry(sub) and sub.is_file():
                files_found.append(sub)
    return files_found


def _dir_exceeds_bytes(dir_path: Path, max_bytes: int) -> bool:
    """Verifica se la dimensione cumulativa dei file in dir_path supera max_bytes."""
    total = 0
    try:
        for sub in _iter_safe_walk_files(dir_path):
            total += sub.stat().st_size
            if total > max_bytes:
                return True
    except OSError:
        return True
    return False


def _build_sandbox_ignore_fn(
    root: Path, max_heavy_bytes: int
) -> Callable[[str, List[str]], set[str]]:
    """Costruisce la funzione ignore per shutil.copytree con blocco symlink, junction e file pesanti."""
    root_resolved = root.resolve()
    base_ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".pytest_cache",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".wal",
        ".mypy_cache",
        ".ruff_cache",
    )

    def _sandbox_ignore_heavy(src: str, names: List[str]) -> set[str]:
        ignored = set(base_ignore(src, names))
        src_path = Path(src)
        parts_lower = {pt.lower() for pt in src_path.parts}
        in_heavy_dir = "data" in parts_lower
        for name in names:
            if name in ignored:
                continue
            cand = src_path / name
            try:
                if _is_blocked_reparse(cand, root_resolved):
                    ignored.add(name)
                    continue
                if in_heavy_dir or name.lower() == "data":
                    if cand.is_file() and cand.stat().st_size > max_heavy_bytes:
                        ignored.add(name)
                    elif cand.is_dir() and _dir_exceeds_bytes(cand, max_heavy_bytes):
                        ignored.add(name)
            except OSError:
                ignored.add(name)
        return ignored

    return _sandbox_ignore_heavy


def _filter_safe_walk_subdirs(
    walk_p: Path, dirs: List[str], stg_resolved: Path, is_top: bool
) -> List[str]:
    """Filtra le sottodirectory sicure durante la raccolta overlay staging."""
    safe_dirs: List[str] = []
    for dname in sorted(dirs):
        if is_top and is_lane_container_entry((dname,)):
            continue
        dpath = walk_p / dname
        if _is_blocked_reparse(dpath, stg_resolved):
            raise ValueError(f"Symlink esterno o junction bloccato nell'overlay staging: {dpath}")
        if dname != "__pycache__" and not _is_reparse_entry(dpath):
            safe_dirs.append(dname)
    return safe_dirs


def _collect_safe_walk_files(
    walk_p: Path, files: List[str], stg_resolved: Path, is_top: bool
) -> List[Path]:
    """Raccoglie i file validi in una directory staging escludendo metadati e reparse."""
    out: List[Path] = []
    for fname in sorted(files):
        if is_top and is_lane_container_entry((fname,)):
            continue
        fpath = walk_p / fname
        if _is_blocked_reparse(fpath, stg_resolved):
            raise ValueError(f"Symlink esterno o junction bloccato nell'overlay staging: {fpath}")
        if not fpath.is_file() or "__pycache__" in fpath.parts or fname in (".gitkeep", ".deleted_files.json"):
            continue
        out.append(fpath)
    return out


def _collect_safe_staging_files(stg: Path, stg_resolved: Path) -> List[Path]:
    """Raccoglie i file staged bloccando reparse esterni e saltando lanes/ in legacy."""
    excl_lanes = stg_resolved.name == ".staging"
    collected: List[Path] = []
    for walk_root, dirs, files in os.walk(stg, followlinks=False):
        walk_p = Path(walk_root)
        is_top = excl_lanes and walk_p.resolve() == stg_resolved
        dirs[:] = _filter_safe_walk_subdirs(walk_p, dirs, stg_resolved, is_top)
        collected.extend(_collect_safe_walk_files(walk_p, files, stg_resolved, is_top))
    return sorted(collected, key=lambda p: p.relative_to(stg).as_posix())


def _parse_deleted_files_manifest(del_manifest: Path) -> List[str]:
    """Valida in modo fail-closed .deleted_files.json riusando il parser SSOT."""
    if not del_manifest.exists():
        return []
    validated = parse_deleted_files_manifest(del_manifest)
    raw = json.loads(del_manifest.read_text(encoding="utf-8-sig"))
    raw_items = raw["deleted_files"] if isinstance(raw, dict) else raw
    if any(not str(item).strip() for item in raw_items):
        raise ValueError(
            "Elemento non valido in .deleted_files.json: attesa stringa non vuota."
        )
    return validated


_EXCLUDED_TOP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".staging",
        ".mypy_cache",
        ".ruff_cache",
        ".wal",
    }
)


def _should_copy_root_dir(
    item: Path, copied_dirs: set[str]
) -> bool:
    """True per directory radice di progetto (es. custom_pkg) escluse cache/ambienti."""
    return (
        item.is_dir()
        and not item.name.startswith(".")
        and item.name not in _EXCLUDED_TOP_DIRS
        and item.name not in copied_dirs
    )


def _copy_allowed_root_files(
    root: Path,
    root_resolved: Path,
    sb: ShadowSandbox,
    ignore_fn: Optional[Callable[[str, List[str]], set[str]]] = None,
    copied_dirs: Optional[set[str]] = None,
) -> None:
    """Copia directory extra non escluse e file radice autorizzati nella ShadowSandbox."""
    allowed_root_names = set(_ROOT_FILES)
    allowed_root_exts = {".py", *_ROOT_ALLOWED_SUFFIXES}
    excluded_root_suffixes = (".db", ".sqlite", ".sqlite3", ".env", ".zip", ".wal", ".shm")
    seen_dirs = copied_dirs if copied_dirs is not None else set(_MIRROR_DIRS)
    for item in root.iterdir():
        if _is_blocked_reparse(item, root_resolved):
            continue
        if _should_copy_root_dir(item, seen_dirs):
            dst_item = _resolve_confined_sandbox_path(sb.sandbox_dir, item.name)
            shutil.copytree(item, dst_item, dirs_exist_ok=True, ignore=ignore_fn)
            seen_dirs.add(item.name)
        elif (
            item.is_file()
            and not item.name.startswith((".coverage", ".env"))
            and not item.name.lower().endswith(excluded_root_suffixes)
            and (item.name in allowed_root_names or item.suffix.lower() in allowed_root_exts)
            and item.stat().st_size <= 50 * 1024 * 1024
        ):
            shutil.copy2(item, _resolve_confined_sandbox_path(sb.sandbox_dir, item.name))


def _mirror_evaluator_github_dir(
    root: Path,
    root_resolved: Path,
    sb: ShadowSandbox,
    norm_prof: str,
    max_heavy_bytes: int,
    root_ignore_fn: Optional[Callable[[str, List[str]], set[str]]],
) -> None:
    """Specchia .github/ dal root o parent root nel profilo evaluator mantenendo i controlli reparse."""
    if norm_prof != "evaluator":
        return
    src_gh = root / ".github"
    if src_gh.is_dir() and not _is_blocked_reparse(src_gh, root_resolved):
        dst_gh = _resolve_confined_sandbox_path(sb.sandbox_dir, ".github")
        shutil.copytree(src_gh, dst_gh, dirs_exist_ok=True, ignore=root_ignore_fn)
        return
    parent_root = root.parent
    if parent_root == root:
        return
    parent_gh = parent_root / ".github"
    parent_res = parent_root.resolve()
    if parent_gh.is_dir() and not _is_blocked_reparse(parent_gh, parent_res):
        dst_gh = _resolve_confined_sandbox_path(sb.sandbox_dir, ".github")
        parent_ignore = _build_sandbox_ignore_fn(parent_res, max_heavy_bytes)
        shutil.copytree(parent_gh, dst_gh, dirs_exist_ok=True, ignore=parent_ignore)


def prepare_staging_overlay(
    root: Path,
    stg: Path,
    sb: ShadowSandbox,
    norm_prof: str,
) -> Tuple[List[str], List[str], List[str]]:
    """Popola la ShadowSandbox con allowlist _MIRROR_DIRS/extra, .staging/ e tombstones."""
    max_heavy_data_bytes = 5 * 1024 * 1024
    root_resolved = root.resolve()
    ignore_fn = _build_sandbox_ignore_fn(root_resolved, max_heavy_data_bytes)
    overlay_files: List[str] = []
    deleted_applied: List[str] = []
    stripped_holdouts: List[str] = []
    sb_root_resolved = sb.sandbox_dir.resolve()
    copied_dirs: set[str] = set()

    for dname in _MIRROR_DIRS:
        src_d = root / dname
        if _is_blocked_reparse(src_d, root_resolved):
            continue
        if src_d.exists() and src_d.is_dir():
            dst_d = _resolve_confined_sandbox_path(sb.sandbox_dir, dname)
            shutil.copytree(src_d, dst_d, dirs_exist_ok=True, ignore=ignore_fn)
            copied_dirs.add(dname)

    _mirror_evaluator_github_dir(root, root_resolved, sb, norm_prof, max_heavy_data_bytes, ignore_fn)
    _copy_allowed_root_files(root, root_resolved, sb, ignore_fn=ignore_fn, copied_dirs=copied_dirs)

    if stg.exists() and stg.is_dir() and not _is_reparse_entry(stg):
        stg_resolved = stg.resolve()
        for stg_file in _collect_safe_staging_files(stg, stg_resolved):
            rel = stg_file.relative_to(stg)
            if rel.parts and rel.parts[0].lower() == "data":
                try:
                    if stg_file.stat().st_size > max_heavy_data_bytes:
                        continue
                except OSError:
                    continue
            dst_file = _resolve_confined_sandbox_path(sb.sandbox_dir, rel)
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stg_file, dst_file)
            overlay_files.append(rel.as_posix())

        del_manifest = stg / ".deleted_files.json"
        if del_manifest.exists() and del_manifest.is_file():
            for rel_del in _parse_deleted_files_manifest(del_manifest):
                cand_del = _resolve_confined_sandbox_path(sb.sandbox_dir, rel_del)
                if (
                    cand_del.is_relative_to(sb_root_resolved)
                    and cand_del.exists()
                    and cand_del.is_file()
                ):
                    cand_del.unlink(missing_ok=True)
                    deleted_applied.append(rel_del)

    if norm_prof == "builder":
        stripped_holdouts = _strip_builder_holdouts_from_sandbox(sb.sandbox_dir)

    return overlay_files, deleted_applied, stripped_holdouts


def allocate_dast_port(lane_id: Optional[str]) -> int:
    """Alloca una porta loopback libera dedicata alla lane DAST."""
    lease_key = f"dast-{validate_lane_id(lane_id)}" if lane_id else "dast-legacy"
    return allocate_lane_loopback_port(lease_key)


def resolve_dast_lane_report_path(diag_dir: Path, lane_id: Optional[str]) -> Path:
    """Risolve il percorso report DAST isolato per lane nella diag_dir."""
    if lane_id:
        return diag_dir / f"dast_last_report_{validate_lane_id(lane_id)}.json"
    return diag_dir / "dast_last_report.json"


def snapshot_overlay_staging_to_nvme(
    stg: Path, norm_lane: Optional[str]
) -> Tuple[Path, Optional[Path]]:
    """Crea uno snapshot NVMe isolato di .staging/[lanes/<id>/] con marker anti-override."""
    if not (stg.exists() and stg.is_dir() and not _is_reparse_entry(stg)):
        return stg, None
    snap_root = Path(tempfile.mkdtemp(prefix="nk_dast_stg_")).resolve()
    (snap_root / ".nk_dast_snapshot_marker").write_text(
        "dast_nvme_snapshot\n", encoding="utf-8"
    )
    snap_stg = (
        (snap_root / ".staging" / "lanes" / norm_lane)
        if norm_lane
        else (snap_root / ".staging")
    )
    snap_stg.mkdir(parents=True, exist_ok=True)
    try:
        stg_resolved = stg.resolve()
        for stg_file in _collect_safe_staging_files(stg, stg_resolved):
            rel = stg_file.relative_to(stg)
            dst_file = snap_stg / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stg_file, dst_file)
        del_m = stg / ".deleted_files.json"
        if del_m.exists() and del_m.is_file() and not _is_reparse_entry(del_m):
            shutil.copy2(del_m, snap_stg / ".deleted_files.json")
    except Exception:
        safe_rmtree(snap_root)
        raise
    return snap_stg, snap_root


def cleanup_nvme_staging_snapshot(snap_root: Optional[Path]) -> None:
    """Rimuove in sicurezza la radice dello snapshot NVMe DAST."""
    if snap_root is not None:
        safe_rmtree(snap_root)


@contextmanager
def nvme_staging_snapshot_ctx(
    stg: Path, norm_lane: Optional[str]
) -> Iterator[Path]:
    """Context manager per snapshot NVMe temporaneo dell'overlay staging."""
    snap_stg, snap_root = snapshot_overlay_staging_to_nvme(stg, norm_lane)
    try:
        yield snap_stg
    finally:
        cleanup_nvme_staging_snapshot(snap_root)

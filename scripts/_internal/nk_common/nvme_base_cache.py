# -*- coding: utf-8 -*-
"""Cache base NVMe in sola lettura con clone locale indipendente (zero os.link)."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Tuple

from _internal.nk_common.nvme_storage_guards import FailClosedNamedMutex
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.win32_mutex import repo_path_hash12


def _ensure_writable_file(path: Path) -> None:
    try:
        if path.exists():
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _mark_readonly_file(path: Path) -> None:
    try:
        if path.exists():
            os.chmod(path, stat.S_IREAD)
    except OSError:
        pass


def _walk_subdir_index(
    sub_root: Path,
    proj_root: Path,
    ignore_fn: Callable[[str, list[str]], set[str]],
    index: Dict[str, Tuple[Path, int, int]],
) -> None:
    """Scansiona una sottocartella workspace popolando index senza seguire reparse point."""
    for cur_dir, dirs, files in os.walk(sub_root, followlinks=False):
        cur_p = Path(cur_dir)
        ignored = ignore_fn(cur_dir, list(dirs) + list(files))
        dirs[:] = [d for d in dirs if d not in ignored and not is_reparse_entry(cur_p / d)]
        for fname in files:
            if fname in ignored:
                continue
            src_f = cur_p / fname
            if is_reparse_entry(src_f):
                continue
            try:
                st = src_f.stat(follow_symlinks=False)
            except OSError:
                continue
            index[src_f.relative_to(proj_root).as_posix()] = (
                src_f, int(st.st_mtime_ns), int(st.st_size)
            )


def _collect_source_index(
    proj_root: Path,
    subdir_names: Sequence[str],
    ignore_fn: Callable[[str, list[str]], set[str]],
    root_file_filter: Callable[[Path], bool],
    is_safe_dir_fn: Callable[[Path, Path], bool],
) -> Dict[str, Tuple[Path, int, int]]:
    """Indicizza i file sorgente (rel_posix -> (src_path, mtime_ns, size))."""
    index: Dict[str, Tuple[Path, int, int]] = {}
    for rel_dir in subdir_names:
        sub_root = proj_root / rel_dir
        if is_safe_dir_fn(sub_root, proj_root):
            _walk_subdir_index(sub_root, proj_root, ignore_fn, index)
    for entry in proj_root.iterdir():
        if not is_reparse_entry(entry) and entry.is_file() and root_file_filter(entry):
            try:
                st = entry.stat(follow_symlinks=False)
                index[entry.name] = (entry, int(st.st_mtime_ns), int(st.st_size))
            except OSError:
                continue
    return index


def _prune_stale_base_files(base_dir: Path, keep_rels: Dict[str, Tuple[Path, int, int]]) -> None:
    """Rimuove dalla cache base NVMe i file non piu presenti nel workspace."""
    for cur_dir, _dirs, files in os.walk(base_dir, topdown=False, followlinks=False):
        cur_p = Path(cur_dir)
        for fname in files:
            fpath = cur_p / fname
            rel_k = fpath.relative_to(base_dir).as_posix()
            if rel_k not in keep_rels:
                _ensure_writable_file(fpath)
                fpath.unlink(missing_ok=True)
        if cur_p != base_dir:
            try:
                if not any(cur_p.iterdir()):
                    cur_p.rmdir()
            except OSError:
                pass


def _sync_single_base_file(base_dir: Path, rel_k: str, meta: Tuple[Path, int, int]) -> None:
    """Sincronizza un singolo file nella base cache NVMe lasciandolo read-only."""
    src_f, src_mt, src_sz = meta
    dst_f = base_dir / rel_k
    if dst_f.is_file():
        try:
            dst_st = dst_f.stat(follow_symlinks=False)
            if int(dst_st.st_mtime_ns) == src_mt and int(dst_st.st_size) == src_sz:
                return
        except OSError:
            _ensure_writable_file(dst_f)
        else:
            _ensure_writable_file(dst_f)
    dst_f.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_f, dst_f)
    _mark_readonly_file(dst_f)


def _resolve_safe_base_cache_dirs(cache_root: Optional[Path], h12: str) -> Tuple[Path, Path, Path, Path]:
    """Risolve e verifica reparse point su path lessicali e canonici della cache NVMe."""
    raw_root = cache_root if cache_root is not None else (Path(tempfile.gettempdir()) / "nk_nvme_base_cache")
    raw_dir = raw_root / h12
    if is_reparse_entry(raw_root) or is_reparse_entry(raw_dir):
        raise OSError(f"Reparse point vietato nella base cache NVMe: {raw_dir}")
    res_root = raw_root.resolve()
    return raw_root, raw_dir, res_root, res_root / h12


def _assert_safe_cache_paths(raw_root: Path, raw_dir: Path, base_root: Path, base_dir: Path) -> None:
    if any(is_reparse_entry(p) for p in (raw_root, raw_dir, base_root, base_dir)):
        raise OSError(f"Reparse point vietato nella base cache NVMe: {base_dir}")


def sync_nvme_base_cache(
    proj_root: Path,
    subdir_names: Sequence[str],
    ignore_fn: Callable[[str, list[str]], set[str]],
    root_file_filter: Callable[[Path], bool],
    is_safe_dir_fn: Callable[[Path, Path], bool],
    *,
    cache_root: Optional[Path] = None,
) -> Path:
    """Sincronizza in modo incrementale la base cache NVMe marcando i file read-only."""
    resolved = Path(proj_root).resolve()
    h12 = repo_path_hash12(resolved)
    raw_root, raw_dir, base_root, base_dir = _resolve_safe_base_cache_dirs(cache_root, h12)
    src_index = _collect_source_index(
        resolved, subdir_names, ignore_fn, root_file_filter, is_safe_dir_fn
    )
    with FailClosedNamedMutex(f"Local\\NK_NvmeBaseCache_{h12}", wait_ms=5000):
        _assert_safe_cache_paths(raw_root, raw_dir, base_root, base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        _prune_stale_base_files(base_dir, src_index)
        for rel_k, meta in src_index.items():
            _sync_single_base_file(base_dir, rel_k, meta)
    return base_dir


def clone_nvme_base_to_mirror(
    base_cache_dir: Path,
    mirror_dir: Path,
    *,
    repo_root_hint: Optional[Path] = None,
) -> None:
    """Clona da cache base NVMe a mirror_dir tramite copia file indipendente (zero os.link)."""
    h12 = repo_path_hash12(repo_root_hint) if repo_root_hint is not None else base_cache_dir.name
    with FailClosedNamedMutex(f"Local\\NK_NvmeBaseCache_{h12}", wait_ms=5000):
        shutil.copytree(base_cache_dir, mirror_dir, dirs_exist_ok=True)
    for cur_dir, _dirs, files in os.walk(mirror_dir, followlinks=False):
        cur_p = Path(cur_dir)
        for fname in files:
            _ensure_writable_file(cur_p / fname)

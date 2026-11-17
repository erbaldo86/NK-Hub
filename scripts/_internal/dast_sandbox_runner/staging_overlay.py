"""Preparazione Shadow Sandbox da root e overlay .staging/ per verifica E2E."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, List, Tuple

from .sandbox_fs import (
    ShadowSandbox,
    _resolve_confined_sandbox_path,
    _strip_builder_holdouts_from_sandbox,
)


def _dir_exceeds_bytes(dir_path: Path, max_bytes: int) -> bool:
    """Verifica se la dimensione cumulativa dei file in dir_path supera max_bytes."""
    total = 0
    try:
        for sub in dir_path.rglob("*"):
            if sub.is_file():
                total += sub.stat().st_size
                if total > max_bytes:
                    return True
    except OSError:
        return True
    return False


def _build_sandbox_ignore_fn(
    root: Path, max_heavy_bytes: int
) -> Callable[[str, List[str]], set[str]]:
    """Costruisce la funzione ignore per shutil.copytree con blocco symlink e file pesanti."""
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
                if cand.is_symlink() and not cand.resolve().is_relative_to(root):
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


def prepare_staging_overlay(
    root: Path,
    stg: Path,
    sb: ShadowSandbox,
    norm_prof: str,
) -> Tuple[List[str], List[str], List[str]]:
    """Popola la ShadowSandbox dal repository root, sovrappone .staging/ e applica tombstones."""
    essential_dirs = (
        "scripts",
        "tests",
        ".agents",
        "nk_genome",
        "genome",
        "nk_tracking",
        "src",
        "src_app",
        "app",
        "data",
        "config",
    )
    excluded_top_dirs = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".staging",
        ".mypy_cache",
        ".ruff_cache",
    }
    allowed_root_exts = {
        ".py",
        ".md",
        ".json",
        ".ini",
        ".toml",
        ".cfg",
        ".txt",
        ".yaml",
        ".yml",
    }
    max_heavy_data_bytes = 5 * 1024 * 1024
    ignore_fn = _build_sandbox_ignore_fn(root, max_heavy_data_bytes)
    overlay_files: List[str] = []
    deleted_applied: List[str] = []
    stripped_holdouts: List[str] = []
    sb_root_resolved = sb.sandbox_dir.resolve()

    copied_top_dirs: set[str] = set()
    for dname in essential_dirs:
        src_d = root / dname
        if src_d.is_symlink() and not src_d.resolve().is_relative_to(root):
            continue
        if src_d.exists() and src_d.is_dir():
            dst_d = _resolve_confined_sandbox_path(sb.sandbox_dir, dname)
            shutil.copytree(src_d, dst_d, dirs_exist_ok=True, ignore=ignore_fn)
            copied_top_dirs.add(dname)

    for item in root.iterdir():
        if item.is_symlink() and not item.resolve().is_relative_to(root):
            continue
        if (
            item.is_dir()
            and item.name not in excluded_top_dirs
            and item.name not in copied_top_dirs
        ):
            dst_item = _resolve_confined_sandbox_path(sb.sandbox_dir, item.name)
            shutil.copytree(item, dst_item, dirs_exist_ok=True, ignore=ignore_fn)
            copied_top_dirs.add(item.name)
        elif (
            item.is_file()
            and item.suffix.lower() in allowed_root_exts
            and item.stat().st_size <= 50 * 1024 * 1024
        ):
            shutil.copy2(
                item, _resolve_confined_sandbox_path(sb.sandbox_dir, item.name)
            )

    if stg.exists() and stg.is_dir():
        stg_resolved = stg.resolve()
        stg_data = stg / "data"
        if (
            stg_data.exists()
            and stg_data.is_dir()
            and not (
                stg_data.is_symlink()
                and not stg_data.resolve().is_relative_to(stg_resolved)
            )
        ):
            shutil.copytree(
                stg_data,
                _resolve_confined_sandbox_path(sb.sandbox_dir, "data"),
                dirs_exist_ok=True,
                ignore=ignore_fn,
            )
        for stg_file in sorted(stg.rglob("*")):
            if stg_file.is_symlink() and not stg_file.resolve().is_relative_to(
                stg_resolved
            ):
                raise ValueError(
                    f"Symlink esterno bloccato nell'overlay staging: {stg_file}"
                )
            if (
                not stg_file.is_file()
                or "__pycache__" in stg_file.parts
                or stg_file.name in (".gitkeep", ".deleted_files.json")
            ):
                continue
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
            try:
                raw_del = json.loads(del_manifest.read_text(encoding="utf-8"))
                del_list = (
                    raw_del
                    if isinstance(raw_del, list)
                    else raw_del.get("deleted_files", [])
                    if isinstance(raw_del, dict)
                    else []
                )
                for rel_del in del_list:
                    cand_del = _resolve_confined_sandbox_path(
                        sb.sandbox_dir, str(rel_del)
                    )
                    if (
                        cand_del.is_relative_to(sb_root_resolved)
                        and cand_del.exists()
                        and cand_del.is_file()
                    ):
                        cand_del.unlink(missing_ok=True)
                        deleted_applied.append(str(rel_del))
            except ValueError:
                raise
            except Exception:
                pass

    if norm_prof == "builder":
        stripped_holdouts = _strip_builder_holdouts_from_sandbox(sb.sandbox_dir)

    return overlay_files, deleted_applied, stripped_holdouts

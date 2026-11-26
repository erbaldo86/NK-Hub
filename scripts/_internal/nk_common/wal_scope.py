# -*- coding: utf-8 -*-
"""Isolamento WAL 2PC per singolo repository senza scansioni globali (pure stdlib)."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Sequence, Union

_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def repo_wal_bucket_hash(root: Union[str, Path]) -> str:
    """Calcola il bucket hash SHA-256 canonico a 12 char per la root del repository."""
    norm = os.path.realpath(str(root)).lower().replace("/", "\\").rstrip("\\")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def get_scoped_wal_dirs(
    roots: Sequence[Union[str, Path]],
    temp_root: Optional[Union[str, Path]] = None,
) -> List[Path]:
    """Restituisce solo le cartelle WAL locali e temp-bucket delle root indicate."""
    base_tmp = (
        Path(temp_root)
        if temp_root is not None
        else Path(os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir())
    )
    temp_wal_base = base_tmp / "nk_2pc_wal"
    scoped: List[Path] = []
    seen: set[str] = set()
    for raw_root in roots:
        if not str(raw_root or "").strip():
            continue
        root_p = Path(raw_root)
        cand_local = root_p / ".wal"
        key_l = str(cand_local).lower()
        if key_l not in seen:
            seen.add(key_l)
            scoped.append(cand_local)
        try:
            bucket = repo_wal_bucket_hash(root_p)
            cand_tmp = temp_wal_base / bucket
            key_t = str(cand_tmp).lower()
            if key_t not in seen:
                seen.add(key_t)
                scoped.append(cand_tmp)
        except OSError:
            continue
    return scoped


def _is_safe_wal_dir(wal_dir: Path) -> bool:
    """Verifica che wal_dir esista e non sia symlink o reparse point."""
    try:
        if not wal_dir.exists() or not wal_dir.is_dir() or wal_dir.is_symlink():
            return False
        st = os.lstat(str(wal_dir))
        return (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) == 0
    except OSError:
        return False


def _wal_dir_has_active_file(wal_dir: Path, cutoff: float) -> bool:
    """True se wal_dir contiene almeno un file .wal recente e privo di reparse point."""
    try:
        with os.scandir(wal_dir) as it:
            for entry in it:
                if not entry.name.endswith(".wal") or entry.is_symlink():
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                is_reparse = (getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) != 0
                if not is_reparse and st.st_mtime >= cutoff:
                    return True
    except OSError:
        return False
    return False


def has_scoped_active_wal(
    roots: Sequence[Union[str, Path]],
    *,
    max_age_sec: float = 120.0,
    temp_root: Optional[Union[str, Path]] = None,
) -> bool:
    """True solo se almeno una directory WAL scoped contiene file .wal recenti non reparse."""
    cutoff = time.time() - max(0.0, float(max_age_sec))
    for wal_dir in get_scoped_wal_dirs(roots, temp_root=temp_root):
        if _is_safe_wal_dir(wal_dir) and _wal_dir_has_active_file(wal_dir, cutoff):
            return True
    return False

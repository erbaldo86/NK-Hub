# -*- coding: utf-8 -*-
"""Helper canonici SSOT per hash manifest staging, JSON strict, finitezza e reparse guard."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple, Type

from _internal.nk_common.io import win_long_path

_MANIFEST_SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".tmp", ".bak"})
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_ASYNC_TEST_LINE_RE = re.compile(
    r"^\s*(?:async\s+def\s+test_|@pytest\.mark\.(?:asyncio|anyio)\b|@anyio\b)|\banyio_backend\b|pytestmark\s*=[^\n]*\b(?:asyncio|anyio)\b",
    re.MULTILINE,
)
_ASYNC_FILE_CACHE: Dict[Tuple[str, int, int], bool] = {}


def file_has_async_marker(fp: Path) -> bool:
    """Controlla rapidamente (con cache valida su mtime+size) se il test usa async/anyio."""
    try:
        st = fp.stat()
    except OSError:
        return False
    key = (str(fp), int(st.st_mtime_ns), int(st.st_size))
    if key in _ASYNC_FILE_CACHE:
        return _ASYNC_FILE_CACHE[key]
    try:
        txt = fp.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False
    hit = ("async" in txt or "anyio" in txt) and bool(_ASYNC_TEST_LINE_RE.search(txt))
    _ASYNC_FILE_CACHE[key] = hit
    return hit


def filter_fast_marker_files(discovered: Sequence[str], profile: str, m_res: Path) -> List[str]:
    """Esclude file privi di mark.fast quando viene richiesto il profilo puro '-m fast'."""
    items = list(discovered)
    if profile != "fast":
        return items
    kept: List[str] = []
    for rel_f in items:
        try:
            txt = (m_res / rel_f).read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            kept.append(rel_f)
            continue
        if "mark.fast" in txt or "pytestmark" in txt:
            kept.append(rel_f)
    return kept if len(kept) >= 4 else items


def is_reparse_entry(p: Path) -> bool:
    """Rileva symlink, junction o reparse point Win32 su file e directory."""
    try:
        if p.is_symlink() or bool(getattr(p, "is_junction", lambda: False)()):
            return True
        attrs = getattr(os.lstat(win_long_path(p)), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def safe_finite_float(val: Any, default: float = 0.0) -> float:
    """Converte val in float finito rifiutando bool, NaN e +/-Inf (fail-closed)."""
    if val is None or isinstance(val, bool):
        return default
    try:
        num = float(val)
    except (TypeError, ValueError):
        return default
    return num if math.isfinite(num) else default


def is_valid_sha256_hex(val: Any) -> bool:
    """Verifica che val sia una stringa SHA-256 esadecimale esattamente di 64 caratteri."""
    return isinstance(val, str) and len(val) == 64 and all(ch in _HEX_CHARS for ch in val)


def no_dup_pairs_hook(
    pairs: List[Tuple[str, Any]], *, exc_cls: Type[Exception] = ValueError
) -> Dict[str, Any]:
    """Rifiuta chiavi duplicate durante json.loads strict."""
    obj: Dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise exc_cls(f"Chiave JSON duplicata vietata: {key!r}")
        obj[key] = value
    return obj


def canonical_json_bytes(
    payload: Any, *, exc_cls: Type[Exception] = ValueError
) -> bytes:
    """Serializza payload in JSON UTF-8 canonico deterministico vietando NaN e Inf."""
    try:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return raw.encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise exc_cls(f"Serializzazione JSON canonica fallita: {exc}") from exc


def compute_payloads_manifest_sha256(payloads: Mapping[str, bytes]) -> str:
    """Calcola lo SHA-256 canonico a partire dai byte in memoria dei payload staged."""
    manifest: Dict[str, str] = {}
    for rel_key in sorted(payloads.keys()):
        norm = str(rel_key).replace("\\", "/").lstrip("/")
        name = Path(norm).name
        parts = Path(norm).parts
        if (
            not norm
            or name == ".gitkeep"
            or "__pycache__" in parts
            or Path(norm).suffix.lower() in _MANIFEST_SKIP_SUFFIXES
        ):
            continue
        manifest[norm] = hashlib.sha256(payloads[rel_key]).hexdigest()
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def compute_staging_manifest_sha256(
    staging_dir: Path, *, reject_symlinks: bool = True
) -> str:
    """Calcola lo SHA-256 canonico di .staging/ usando win_long_path e controllo reparse."""
    payloads: Dict[str, bytes] = {}
    stg = Path(staging_dir)
    if stg.exists():
        if reject_symlinks and is_reparse_entry(stg):
            raise ValueError(f"Reparse point vietato nella root staging: {stg}")
        for cand in sorted(stg.rglob("*"), key=lambda p: p.as_posix()):
            if is_reparse_entry(cand):
                if reject_symlinks:
                    raise ValueError(f"Symlink/reparse point vietato in staging: {cand}")
                continue
            if not cand.is_file():
                continue
            rel = cand.relative_to(stg)
            if (
                cand.name == ".gitkeep"
                or "__pycache__" in rel.parts
                or cand.suffix.lower() in _MANIFEST_SKIP_SUFFIXES
            ):
                continue
            payloads[rel.as_posix()] = win_long_path(cand).read_bytes()
    return compute_payloads_manifest_sha256(payloads)

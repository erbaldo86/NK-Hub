# -*- coding: utf-8 -*-
"""Pulizia directory, igiene WAL e retention report per preflight_health_check."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from _internal.nk_common.constants import VERSION as _COMMON_VERSION
from _internal.nk_common.io import atomic_write_text
from _internal.nk_common.win32_mutex import (
    create_or_open_named_mutex,
    release_win32_mutex,
)

VERSION: str = _COMMON_VERSION
DEFAULT_VERSION: str = VERSION


def _write_anchor_atomic(anchor_path: Path, text: str) -> None:
    """Scrive session_anchor.jsonl in modo atomico protetto da Named Mutex Win32."""
    norm = os.path.abspath(str(anchor_path)).lower()
    m_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    m_name = f"Global\\NK_Anchor_{m_hash}"
    handle, acquired, _err = (
        create_or_open_named_mutex(m_name, wait_ms=2000)
        if sys.platform == "win32"
        else (None, False, "non_win32")
    )
    try:
        ok, err = atomic_write_text(anchor_path, text)
        if not ok:
            raise OSError(err or f"Atomic write failed for {anchor_path}")
    finally:
        if acquired and handle is not None:
            release_win32_mutex(handle)


def safe_remove_dir(dir_path: Path) -> bool:
    """Rimuove un albero di directory gestendo i permessi su Windows."""
    if not dir_path.exists():
        return True

    def on_error(func: Any, p: str, exc_info: Any) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    try:
        shutil.rmtree(dir_path, onerror=on_error)
        return True
    except Exception:
        return not dir_path.exists()


def safe_remove_file(file_path: Path) -> bool:
    """Rimuove un singolo file gestendo i permessi su Windows."""
    if not file_path.exists():
        return True
    try:
        os.chmod(file_path, stat.S_IWRITE)
        file_path.unlink()
        return True
    except Exception:
        return not file_path.exists()


def canonical_wal_directories(workspace_root: Path) -> Tuple[Path, ...]:
    """Restituisce l'elenco chiuso delle directory .wal canoniche."""
    return (
        workspace_root / ".wal",
        workspace_root / "scripts" / ".wal",
        workspace_root / "scripts" / "schemas" / ".wal",
        workspace_root / "tests" / ".wal",
        workspace_root / "nk_genome" / ".wal",
        workspace_root / "nk_tracking" / ".wal",
        workspace_root / ".agents" / ".wal",
        workspace_root / ".staging" / ".wal",
    )


def is_wal_filename(fname: str) -> bool:
    """Restituisce True se il nome appartiene a un file WAL."""
    return (
        fname.endswith(".wal")
        or fname.endswith(".wal_2pc.jsonl")
        or ".wal_tmp" in fname
    )


def scan_workspace_once(checker: Any) -> Tuple[List[Path], List[Path], List[Path]]:
    """Scansiona con os.scandir piatto solo le directory .wal canoniche."""
    if checker._cached_walk is not None:
        return checker._cached_walk

    cache_dirs: List[Path] = []
    wal_files: List[Path] = []
    wal_dirs: List[Path] = []
    seen_files: Set[Path] = set()
    quarantine_dir = (checker.workspace_root / ".wal" / "quarantine").resolve()

    for wdir in checker._canonical_wal_directories():
        if not wdir.exists() or not wdir.is_dir():
            continue
        wal_dirs.append(wdir)
        try:
            with os.scandir(wdir) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.is_file(follow_symlinks=False) and checker._is_wal_filename(entry.name):
                        fpath = Path(entry.path)
                        if fpath.parent.resolve() != quarantine_dir and fpath not in seen_files:
                            seen_files.add(fpath)
                            wal_files.append(fpath)
        except OSError:
            continue

    for shallow_dir in (
        checker.workspace_root,
        checker.workspace_root / ".staging",
        checker.tracking_dir,
    ):
        if not shallow_dir.exists() or not shallow_dir.is_dir():
            continue
        try:
            with os.scandir(shallow_dir) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False) and checker._is_wal_filename(entry.name):
                        fpath = Path(entry.path)
                        if fpath not in seen_files:
                            seen_files.add(fpath)
                            wal_files.append(fpath)
        except OSError:
            continue

    checker._cached_walk = (cache_dirs, wal_files, wal_dirs)
    return checker._cached_walk


def check_ssot_anchor(checker: Any, auto_fix: bool) -> Dict[str, Any]:
    """Verifica l'esistenza e la validita JSONL di session_anchor.jsonl."""
    passed = True
    details: List[str] = []

    if not checker.anchor_file.exists():
        if auto_fix:
            checker.anchor_file.parent.mkdir(parents=True, exist_ok=True)
            init_entry = {
                "event": "PREFLIGHT_HEALTH_CHECK_INITIALIZED",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "INITIALIZED",
            }
            _write_anchor_atomic(checker.anchor_file, json.dumps(init_entry) + "\n")
            details.append("Created canonical session_anchor.jsonl.")
        else:
            passed = False
            details.append("Canonical session_anchor.jsonl is missing.")
    else:
        try:
            raw_lines = checker.anchor_file.read_text(encoding="utf-8").splitlines()
            valid_lines: List[str] = []
            seen_lines = set()
            had_invalid = False
            for line in raw_lines:
                stripped = line.strip()
                if not stripped:
                    had_invalid = True
                    continue
                try:
                    json.loads(stripped)
                    if stripped not in seen_lines:
                        seen_lines.add(stripped)
                        valid_lines.append(stripped)
                    else:
                        had_invalid = True
                except json.JSONDecodeError:
                    had_invalid = True

            if had_invalid:
                if auto_fix and valid_lines:
                    _write_anchor_atomic(
                        checker.anchor_file, "\n".join(valid_lines) + "\n"
                    )
                    details.append("Sanitized session_anchor.jsonl.")
                elif not valid_lines:
                    passed = False
                    details.append("session_anchor.jsonl contains corrupted JSONL.")
        except Exception as exc:
            passed = False
            details.append(f"Error reading session_anchor.jsonl: {exc}")

    rogue_root_anchor = checker.workspace_root / "session_anchor.jsonl"
    if rogue_root_anchor.exists():
        if auto_fix:
            safe_remove_file(rogue_root_anchor)
            details.append("Removed duplicate session_anchor.jsonl from workspace root.")
        else:
            passed = False
            details.append("Rogue session_anchor.jsonl found in workspace root.")

    return {
        "passed": passed,
        "canonical_path": str(checker.anchor_file),
        "details": details,
    }


def check_staging_and_temp(checker: Any, auto_fix: bool) -> Dict[str, Any]:
    """Pulisce cartelle temporanee orfane, .patch in stashes e garantisce manifests/."""
    orphan_dirs = [
        checker.workspace_root / ".commit_ready",
        checker.workspace_root / ".sandbox_tmp",
        checker.workspace_root / ".temp_sandbox",
    ]
    cleaned: List[str] = []
    passed = True
    for d in orphan_dirs:
        if d.exists():
            if auto_fix:
                safe_remove_dir(d)
                cleaned.append(str(d.name))
            else:
                passed = False
                cleaned.append(f"Orphan found: {d.name}")

    if checker.stashes_dir.exists() and checker.stashes_dir.is_dir():
        for pf in sorted(checker.stashes_dir.glob("*.patch")):
            if auto_fix:
                if safe_remove_file(pf):
                    cleaned.append(f"handoff/stashes/{pf.name}")
            else:
                passed = False
                cleaned.append(f"Orphan patch found: handoff/stashes/{pf.name}")
        if auto_fix and checker.stashes_dir.exists() and not any(checker.stashes_dir.iterdir()):
            if safe_remove_dir(checker.stashes_dir):
                cleaned.append("handoff/stashes")

    if checker.tracking_dir.exists() and not checker.manifests_dir.exists() and auto_fix:
        checker.manifests_dir.mkdir(parents=True, exist_ok=True)
        cleaned.append("nk_tracking/manifests")

    staging_dir = checker.workspace_root / ".staging"
    if not staging_dir.exists() and auto_fix:
        staging_dir.mkdir(exist_ok=True)
        (staging_dir / ".gitkeep").touch(exist_ok=True)

    return {
        "passed": passed,
        "cleaned_directories": cleaned,
        "manifests_exists": checker.manifests_dir.exists(),
        "details": "Staging and stashes hygiene verified." if passed else f"Orphan items: {cleaned}",
    }


def is_committed_wal(wal_file: Path) -> bool:
    """Restituisce True solo se l'ultimo record valido del file WAL e COMMITTED."""
    try:
        raw = wal_file.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return False
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return str(obj.get("state", "")).strip().upper() == "COMMITTED"
            return False
        except Exception:
            pass
        for ln in reversed(raw.splitlines()):
            ln_s = ln.strip()
            if not ln_s:
                continue
            try:
                rec = json.loads(ln_s)
            except Exception:
                return False
            if not isinstance(rec, dict):
                return False
            return str(rec.get("state", "")).strip().upper() == "COMMITTED"
    except Exception:
        pass
    return False


def check_and_purge_stale_wals(
    checker: Any, auto_fix: bool, ttl_seconds: float = 60.0
) -> Dict[str, Any]:
    """Scansiona le directory .wal canoniche ed elimina i WAL scaduti oltre il TTL."""
    now = time.time()
    _, wal_candidates, stale_wal_dirs = checker._scan_workspace_once()
    stale_wal_files: List[Path] = []
    for f_path in wal_candidates:
        try:
            if f_path.exists() and (now - f_path.stat().st_mtime) > ttl_seconds and not checker._is_committed_wal(f_path):
                stale_wal_files.append(f_path)
        except OSError:
            pass

    purged_count = 0
    root_wal_dir = (checker.workspace_root / ".wal").resolve()
    if auto_fix:
        for wf in stale_wal_files:
            if safe_remove_file(wf):
                purged_count += 1
        for wd in stale_wal_dirs:
            try:
                if wd.resolve() != root_wal_dir and wd.exists() and not any(wd.iterdir()):
                    safe_remove_dir(wd)
            except Exception:
                pass

    return {
        "passed": True if auto_fix else (len(stale_wal_files) == 0),
        "ttl_seconds": ttl_seconds,
        "stale_wals_detected": len(stale_wal_files),
        "purged_count": purged_count,
    }

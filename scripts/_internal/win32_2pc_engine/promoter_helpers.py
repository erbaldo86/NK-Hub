#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helper di quarantena staging, validazione payload/cancellazioni e sync Git."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from . import constants as _consts
from .constants import TwoPhaseCommitError, compute_sha256
from .io_and_paths import (
    _assert_no_external_reparse,
    _extract_patch_notes_headers,
    _get_repo_hash16,
    _is_reparse_point,
    _resolve_repo_root,
    _unlink_with_retry,
    _validate_win32_canonical_rel_path,
    _win_long_path,
    get_repo_batch_mutex_name,
)
from .mutex import Win32NamedMutex


def quarantine_staging(
    repo_root: Optional[Union[str, Path]] = None,
    staging_dirname: str = ".staging",
) -> Dict[str, Any]:
    """Sposta i contenuti correnti di .staging/ in una cartella isolata di quarantena in %TEMP%."""
    root = _resolve_repo_root(repo_root)
    staging_dir = root / staging_dirname
    quarantine_root = (
        Path(tempfile.gettempdir())
        / "nk_2pc_staging_quarantine"
        / f"{_get_repo_hash16(root)}_{int(time.time() * 1000)}"
    )
    moved_files: List[str] = []

    with Win32NamedMutex(
        get_repo_batch_mutex_name(root),
        timeout_ms=10000,
        is_path=False,
    ):
        if not staging_dir.exists():
            staging_dir.mkdir(parents=True, exist_ok=True)
            (staging_dir / ".gitkeep").write_text("", encoding="utf-8")
            return {
                "status": "SUCCESS",
                "passed": True,
                "quarantine_dir": None,
                "quarantined_count": 0,
                "quarantined_files": [],
            }

        import shutil

        for item in sorted(list(staging_dir.rglob("*"))):
            try:
                if _is_reparse_point(item):
                    if item.is_dir() and not item.is_symlink():
                        os.rmdir(_win_long_path(item))
                    else:
                        _unlink_with_retry(item)
                    continue
                if not item.is_file() or item.name == ".gitkeep":
                    continue
                rel = item.relative_to(staging_dir)
                dest = quarantine_root / rel
                _win_long_path(dest.parent).mkdir(parents=True, exist_ok=True)
                shutil.move(str(_win_long_path(item)), str(_win_long_path(dest)))
                moved_files.append(rel.as_posix())
            except OSError:
                pass

        all_dirs = sorted(
            (d for d in staging_dir.rglob("*") if d.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for d in all_dirs:
            try:
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass

        gitkeep = staging_dir / ".gitkeep"
        if not gitkeep.exists():
            staging_dir.mkdir(parents=True, exist_ok=True)
            gitkeep.write_text("", encoding="utf-8")

    return {
        "status": "SUCCESS",
        "passed": True,
        "quarantine_dir": str(quarantine_root) if moved_files else None,
        "quarantined_count": len(moved_files),
        "quarantined_files": moved_files,
    }


def collect_validated_deletions(
    deleted_manifest: Path,
    root: Path,
    real_root: Path,
    allow_governance_override: bool,
) -> List[Tuple[str, Path]]:
    """Valida il manifest .deleted_files.json contro denylist e reparse esterni."""
    deleted_rel_paths: List[str] = []
    if deleted_manifest.exists() and deleted_manifest.is_file():
        raw_del = json.loads(deleted_manifest.read_text(encoding="utf-8-sig"))
        if isinstance(raw_del, list):
            deleted_rel_paths = [str(x) for x in raw_del if str(x).strip()]
        elif isinstance(raw_del, dict) and isinstance(raw_del.get("deleted_files"), list):
            deleted_rel_paths = [
                str(x) for x in raw_del["deleted_files"] if str(x).strip()
            ]
        else:
            raise TwoPhaseCommitError(
                "Formato invalido per .deleted_files.json: attesa lista o chiave 'deleted_files'."
            )

    validated_deletions: List[Tuple[str, Path]] = []
    for rel_del in deleted_rel_paths:
        clean_rel_del = _validate_win32_canonical_rel_path(rel_del)
        rel_del_norm = clean_rel_del.lower()
        del_target = (root / clean_rel_del).resolve()
        _assert_no_external_reparse(del_target, real_root, stop_at=root)
        real_del_target = Path(os.path.realpath(str(del_target)))
        if real_del_target == real_root or real_root not in real_del_target.parents:
            raise TwoPhaseCommitError(
                f"Percorso di cancellazione fuori dalla root del repository: {rel_del}"
            )
        del_name_low = Path(rel_del_norm).name.lower()
        is_protected_cp = (
            del_name_low.startswith("checkpoint_")
            and del_name_low.endswith(".json")
            and _win_long_path(del_target).exists()
        )
        is_protected_pn = (
            rel_del_norm in ("patch_notes.md", "nk_genome/patch_notes.md")
            and _win_long_path(del_target).exists()
        )
        if not allow_governance_override and (
            rel_del_norm in _consts.PROTECTED_GOVERNANCE_DENYLIST
            or del_name_low == "oracle_lock.json"
            or is_protected_cp
            or is_protected_pn
        ):
            raise TwoPhaseCommitError(
                f"Cancellazione bloccata per file di governance protetto ({rel_del}): richiesto --allow-governance-override ([RULE-ORACLE-LOCK])."
            )
        validated_deletions.append((clean_rel_del, del_target))
    return validated_deletions


def collect_staged_payloads(
    staging_files: List[Path],
    staging_dir: Path,
    root: Path,
    real_root: Path,
    allow_governance_override: bool,
) -> List[Tuple[Path, Path, Path, bytes, str]]:
    """Valida e carica in memoria tutti i payload di staging verificando lock e PATCH_NOTES."""
    staged_payloads: List[Tuple[Path, Path, Path, bytes, str]] = []
    for stg_file in staging_files:
        rel_path = stg_file.relative_to(staging_dir)
        clean_rel = _validate_win32_canonical_rel_path(rel_path)
        rel_norm = clean_rel.lower()
        prod_file = (root / clean_rel).resolve()
        _assert_no_external_reparse(prod_file, real_root, stop_at=root)
        real_prod = Path(os.path.realpath(str(prod_file)))
        if real_prod == real_root or real_root not in real_prod.parents:
            raise TwoPhaseCommitError(
                f"Percorso di promozione fuori dalla root del repository: {rel_path}"
            )
        rel_name_low = Path(rel_norm).name.lower()
        is_protected_cp = (
            rel_name_low.startswith("checkpoint_")
            and rel_name_low.endswith(".json")
            and _win_long_path(prod_file).exists()
        )
        if not allow_governance_override and (
            rel_norm in _consts.PROTECTED_GOVERNANCE_DENYLIST
            or rel_name_low == "oracle_lock.json"
            or is_protected_cp
        ):
            raise TwoPhaseCommitError(
                f"Promozione bloccata per file di governance protetto ({rel_path.as_posix()}): richiesto --allow-governance-override ([RULE-ORACLE-LOCK])."
            )
        stg_bytes = _win_long_path(stg_file).read_bytes()
        if (
            not allow_governance_override
            and rel_norm in ("patch_notes.md", "nk_genome/patch_notes.md")
            and _win_long_path(prod_file).exists()
            and _win_long_path(prod_file).is_file()
        ):
            prod_txt = _win_long_path(prod_file).read_bytes().decode(
                "utf-8-sig", errors="replace"
            )
            stg_txt = stg_bytes.decode("utf-8-sig", errors="replace")
            prod_headers = _extract_patch_notes_headers(prod_txt)
            stg_headers = set(_extract_patch_notes_headers(stg_txt))
            missing_headers = [h for h in prod_headers if h not in stg_headers]
            if missing_headers:
                raise TwoPhaseCommitError(
                    f"Promozione bloccata per {rel_path.as_posix()}: header storici ## [...] rimossi ({missing_headers[0]}); richiesto --allow-governance-override."
                )
        stg_sha = compute_sha256(stg_bytes)
        staged_payloads.append((stg_file, rel_path, prod_file, stg_bytes, stg_sha))
    return staged_payloads


def run_git_sync(
    root: Path, committed: List[Dict[str, Any]], deleted: List[str]
) -> bool:
    """Esegue git add e git rm --cached fuori dal mutex batch se git e nel PATH."""
    import shutil
    import subprocess

    git_exe = shutil.which("git")
    if not git_exe:
        print(
            "[WARN] Eseguibile 'git' non trovato nel PATH; sincronizzazione Git saltata.",
            file=sys.stderr,
        )
        return False
    try:
        files_to_sync: List[str] = [c["relative_path"] for c in committed]
        if files_to_sync:
            proc_git = subprocess.run(
                [git_exe, "add", "--"] + files_to_sync,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
            )
            ok = proc_git.returncode == 0
        else:
            ok = True
        if deleted:
            subprocess.run(
                [git_exe, "rm", "--cached", "--ignore-unmatch", "--"] + deleted,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
            )
        return ok
    except Exception:
        return False

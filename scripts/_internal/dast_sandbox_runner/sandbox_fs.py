"""Confinamento filesystem, ambiente sanitizzato e classe ShadowSandbox."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import (
    _BLOCKED_ENV_KEYS,
    _BUILDER_STRIP_PATHS,
    _SENSITIVE_ENV_TOKENS,
    _facade_attr,
)


def _resolve_confined_sandbox_path(sandbox_dir: Path, rel_path: Path | str) -> Path:
    """Risolve e confina un percorso relativo dentro sandbox_dir bloccando '..' e symlink esterni."""
    raw_str = str(rel_path).strip()
    if not raw_str or "\x00" in raw_str:
        raise ValueError(f"Percorso sandbox vuoto o non valido: {rel_path!r}")
    rel_obj = Path(raw_str)
    if rel_obj.is_absolute() or rel_obj.drive or rel_obj.root:
        raise ValueError(f"Percorso assoluto vietato nella sandbox: {rel_path!r}")
    norm_segments = [seg for seg in raw_str.replace("\\", "/").split("/") if seg]
    if ".." in norm_segments or ".." in rel_obj.parts:
        raise ValueError(f"Path traversal '..' vietato nella sandbox: {rel_path!r}")

    sandbox_root = sandbox_dir.resolve()
    curr = sandbox_dir
    for part in rel_obj.parts:
        curr = curr / part
        if curr.is_symlink():
            resolved_target = curr.resolve()
            if not resolved_target.is_relative_to(sandbox_root):
                raise ValueError(
                    f"Symlink esterno vietato nella sandbox: {rel_path!r}"
                )

    target = (sandbox_dir / rel_obj).resolve()
    if not target.is_relative_to(sandbox_root) or target == sandbox_root:
        raise ValueError(f"Confinamento sandbox violato per: {rel_path!r}")
    return target


def _handle_remove_readonly(func: Any, path: str, exc_info: Any) -> None:
    """Rimuove l'attributo di sola lettura durante la pulizia della sandbox."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _strip_builder_holdouts_from_sandbox(sandbox_dir: Path) -> List[str]:
    """Rimuove dalla sandbox i file e le cartelle riservate all'oracolo in profilo builder."""
    shutil_mod = _facade_attr("shutil", shutil)
    removed: List[str] = []
    for rel_p in _BUILDER_STRIP_PATHS:
        cand = sandbox_dir / rel_p
        if cand.is_dir():
            shutil_mod.rmtree(cand, onerror=_handle_remove_readonly)
            removed.append(rel_p)
        elif cand.exists():
            cand.unlink(missing_ok=True)
            removed.append(rel_p)
    return removed


def _build_sanitized_sandbox_env(
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Filtra os.environ escludendo segreti e override di governance e forza bytecode zero."""
    sanitized: Dict[str, str] = {}
    for k, v in os.environ.items():
        k_up = k.upper()
        if k_up in _BLOCKED_ENV_KEYS or any(
            tok in k_up for tok in _SENSITIVE_ENV_TOKENS
        ):
            continue
        sanitized[k] = v
    if extra_env:
        for k, v in extra_env.items():
            if k.upper() in _BLOCKED_ENV_KEYS:
                continue
            sanitized[k] = v
    sanitized["PYTHONUNBUFFERED"] = "1"
    sanitized["PYTHONDONTWRITEBYTECODE"] = "1"
    return sanitized


class ShadowSandbox:
    """Gestisce una cartella temporanea isolata in %TEMP%\\nk_sandbox_<uuid>\\."""

    def __init__(self, sandbox_id: Optional[str] = None) -> None:
        self.sandbox_id = sandbox_id or f"nk_sandbox_{uuid.uuid4().hex}"
        self.base_temp_dir = Path(tempfile.gettempdir())
        self.sandbox_dir = self.base_temp_dir / self.sandbox_id
        self._is_active = False

    def create(self) -> Path:
        """Crea la cartella isolata della sandbox su disco."""
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self._is_active = True
        return self.sandbox_dir

    def write_file(
        self,
        rel_path: str,
        content: str | bytes,
        encoding: str = "utf-8",
    ) -> Path:
        """Scrive un file confinato nella sandbox bloccando traversal e symlink esterni."""
        if not self._is_active:
            self.create()

        target_path = _resolve_confined_sandbox_path(self.sandbox_dir, rel_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            target_path.write_bytes(content)
        else:
            target_path.write_text(content, encoding=encoding)

        return target_path

    def copy_file(self, src_path: Path | str, dst_rel_path: str = "") -> Path:
        """Copia un file sorgente dentro la sandbox verificando il confinamento."""
        if not self._is_active:
            self.create()

        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        if dst_rel_path:
            if dst_rel_path.endswith(("/", "\\")):
                dst_dir = _resolve_confined_sandbox_path(
                    self.sandbox_dir, dst_rel_path.rstrip("/\\")
                )
                dst_dir.mkdir(parents=True, exist_ok=True)
                dst = _resolve_confined_sandbox_path(
                    self.sandbox_dir, f"{dst_rel_path.rstrip('/\\')}/{src.name}"
                )
            else:
                cand = _resolve_confined_sandbox_path(self.sandbox_dir, dst_rel_path)
                if cand.is_dir():
                    dst = _resolve_confined_sandbox_path(
                        self.sandbox_dir, f"{dst_rel_path}/{src.name}"
                    )
                else:
                    cand.parent.mkdir(parents=True, exist_ok=True)
                    dst = cand
        else:
            dst = _resolve_confined_sandbox_path(self.sandbox_dir, src.name)

        shutil.copy2(src, dst)
        return dst

    def cleanup(self) -> None:
        """Rimuove la cartella temporanea gestendo eventuali lock su Windows."""
        if not self.sandbox_dir.exists():
            self._is_active = False
            return

        shutil_mod = _facade_attr("shutil", shutil)
        time_mod = _facade_attr("time", time)
        for attempt in range(5):
            try:
                shutil_mod.rmtree(self.sandbox_dir, onerror=_handle_remove_readonly)
                break
            except Exception:
                time_mod.sleep(0.05 * (attempt + 1))

        self._is_active = False

    def __enter__(self) -> ShadowSandbox:
        self.create()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    async def __aenter__(self) -> ShadowSandbox:
        self.create()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

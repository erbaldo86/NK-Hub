"""Confinamento filesystem, ambiente sanitizzato e classe ShadowSandbox."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_common.isolated_test_runner import _is_reparse_entry

from .constants import (
    DAST_MAX_OUTPUT_BYTES,
    _BLOCKED_ENV_KEYS,
    _BUILDER_STRIP_PATHS,
    _SENSITIVE_ENV_TOKENS,
    _facade_attr,
)

_SANDBOX_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
_SKIP_TREE_DIRS = frozenset({
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".staging", ".wal",
})


def _truncate_utf8_bytes(raw: bytes | str, max_bytes: int = DAST_MAX_OUTPUT_BYTES) -> str:
    """Tronca stdout/stderr agli ultimi max_bytes UTF-8 validi senza superare il limite."""
    limit = max(0, int(max_bytes))
    if limit == 0:
        return ""
    data = raw.encode("utf-8", errors="replace") if isinstance(raw, str) else bytes(raw)
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace")
    tail = data[-limit:]
    idx = 0
    while idx < len(tail) and idx < 3 and (tail[idx] & 0xC0) == 0x80:
        idx += 1
    text = tail[idx:].decode("utf-8", errors="replace")
    while len(text.encode("utf-8")) > limit and text:
        text = text[1:]
    return text


def _validate_sandbox_id(sandbox_id: Optional[str]) -> str:
    """Valida il formato sicuro di sandbox_id prevenendo path traversal."""
    if sandbox_id is None:
        return f"nk_sandbox_{uuid.uuid4().hex}"
    if not isinstance(sandbox_id, str) or not _SANDBOX_ID_RE.fullmatch(sandbox_id):
        raise ValueError(
            f"sandbox_id non valido (attesi 1..80 caratteri [a-zA-Z0-9_-]): {sandbox_id!r}"
        )
    return sandbox_id


def _assert_sandbox_dir_confined(base_temp_dir: Path, sandbox_dir: Path) -> Path:
    """Verifica che sandbox_dir resti strettamente confinato sotto base_temp_dir."""
    base_resolved = base_temp_dir.resolve()
    if _is_reparse_entry(sandbox_dir):
        raise ValueError(f"Symlink o junction sandbox_dir non consentito: {sandbox_dir}")
    sb_resolved = sandbox_dir.resolve()
    if sb_resolved == base_resolved or not sb_resolved.is_relative_to(base_resolved):
        raise ValueError(
            f"Confinamento sandbox_dir violato: {sb_resolved} fuori da {base_resolved}"
        )
    return sb_resolved


def _assert_reparse_confined(curr: Path, sandbox_root: Path, rel_path: Path | str) -> None:
    """Verifica che un eventuale symlink/reparse point resti confinato o blocca junction."""
    if not _is_reparse_entry(curr):
        return
    resolved_target = curr.resolve()
    if not resolved_target.is_relative_to(sandbox_root) or not curr.is_symlink():
        raise ValueError(
            f"Symlink esterno o junction vietato nella sandbox: {rel_path!r}"
        )


def _resolve_confined_sandbox_path(sandbox_dir: Path, rel_path: Path | str) -> Path:
    """Risolve e confina un percorso relativo dentro sandbox_dir bloccando '..' e symlink/junction esterni."""
    raw_str = str(rel_path).strip()
    if not raw_str or "\x00" in raw_str:
        raise ValueError(f"Percorso sandbox vuoto o non valido: {rel_path!r}")
    rel_obj = Path(raw_str)
    has_win_drive = len(raw_str) >= 2 and raw_str[0].isalpha() and raw_str[1] == ":"
    if rel_obj.is_absolute() or rel_obj.drive or rel_obj.root or has_win_drive or ":" in raw_str or raw_str.startswith(("\\\\", "//")):
        raise ValueError(f"Percorso assoluto vietato nella sandbox: {rel_path!r}")
    norm_segments = [seg for seg in raw_str.replace("\\", "/").split("/") if seg]
    if ".." in norm_segments or ".." in rel_obj.parts:
        raise ValueError(f"Path traversal '..' vietato nella sandbox: {rel_path!r}")

    sandbox_root = sandbox_dir.resolve()
    curr = sandbox_dir
    for part in rel_obj.parts:
        curr = curr / part
        _assert_reparse_confined(curr, sandbox_root, rel_path)

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


def _is_sensitive_or_blocked_env_key(key: str) -> bool:
    """Verifica se una chiave ambiente viola i token sensibili o il blocco governance."""
    k_up = str(key).upper()
    return k_up in _BLOCKED_ENV_KEYS or any(tok in k_up for tok in _SENSITIVE_ENV_TOKENS)


def _build_sanitized_sandbox_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Filtra os.environ ed extra_env escludendo segreti e override e forza bytecode zero."""
    sanitized: Dict[str, str] = {}
    for k, v in os.environ.items():
        if _is_sensitive_or_blocked_env_key(k):
            continue
        sanitized[k] = v
    if extra_env:
        for k, v in extra_env.items():
            if _is_sensitive_or_blocked_env_key(k):
                continue
            sanitized[k] = v
    sanitized["PYTHONUNBUFFERED"] = "1"
    sanitized["PYTHONDONTWRITEBYTECODE"] = "1"
    return sanitized


class ShadowSandbox:
    """Gestisce una cartella temporanea isolata dentro tempfile.gettempdir()."""

    def __init__(self, sandbox_id: Optional[str] = None) -> None:
        self.sandbox_id = _validate_sandbox_id(sandbox_id)
        self.base_temp_dir = Path(tempfile.gettempdir())
        self.sandbox_dir = self.base_temp_dir / self.sandbox_id
        _assert_sandbox_dir_confined(self.base_temp_dir, self.sandbox_dir)
        self._is_active = False

    def create(self) -> Path:
        """Crea la cartella isolata della sandbox su disco."""
        _assert_sandbox_dir_confined(self.base_temp_dir, self.sandbox_dir)
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
        """Rimuove la cartella temporanea dopo controllo confinamento gestendo lock Windows."""
        _assert_sandbox_dir_confined(self.base_temp_dir, self.sandbox_dir)
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


def _is_sandbox_cycle_dir(
    cand: Path, sb_res: Optional[Path] = None, temp_res: Optional[Path] = None
) -> bool:
    """Esclude directory sandbox, TEMP di sistema o antenati/discendenti ciclici."""
    if cand.name.startswith("nk_sandbox_"):
        return True
    t_res = temp_res if temp_res is not None else Path(tempfile.gettempdir()).resolve()
    try:
        d_res = cand.resolve()
    except OSError:
        return True
    if d_res == t_res:
        return True
    if sb_res is None:
        return False
    return d_res == sb_res or d_res in sb_res.parents or sb_res in d_res.parents


def _copy_tree_to_sandbox(
    sb: ShadowSandbox,
    src_dir: Path,
    dst_rel_dir: str,
    overwrite: bool = True,
    max_files: int = 2000,
) -> int:
    """Copia un albero package dentro la sandbox saltando cache e reparse point esterni."""
    src_resolved, sb_res, temp_res = src_dir.resolve(), sb.sandbox_dir.resolve(), Path(tempfile.gettempdir()).resolve()
    if _is_sandbox_cycle_dir(src_resolved, sb_res, temp_res):
        return 0
    copied = 0
    for walk_root, dirs, files in os.walk(src_resolved, followlinks=False):
        root_p = Path(walk_root)
        dirs[:] = [
            d for d in sorted(dirs)
            if d not in _SKIP_TREE_DIRS
            and not _is_reparse_entry(root_p / d)
            and not _is_sandbox_cycle_dir(root_p / d, sb_res, temp_res)
        ]
        rel_dir = root_p.relative_to(src_resolved)
        for fname in sorted(files):
            if fname.endswith((".pyc", ".pyo")):
                continue
            fpath = root_p / fname
            if _is_reparse_entry(fpath) or not fpath.is_file():
                continue
            dst = _resolve_confined_sandbox_path(sb.sandbox_dir, (Path(dst_rel_dir) / rel_dir / fname).as_posix())
            if not overwrite and dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fpath, dst)
            copied += 1
            if copied >= max_files:
                return copied
    return copied


def _find_enclosing_package_root(script_dir: Path) -> Optional[Path]:
    """Risale le directory con __init__.py per individuare la radice del pacchetto Python."""
    pkg_root: Optional[Path] = None
    cur = script_dir.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    while cur != cur.parent and cur != temp_root and (cur / "__init__.py").is_file():
        pkg_root = cur
        cur = cur.parent
    return pkg_root


def _should_copy_child_pkg(sub: Path, sb_res: Optional[Path] = None) -> bool:
    """Determina se una sottodirectory contiene un pacchetto Python o moduli importabili."""
    if not sub.is_dir() or sub.name.startswith(".") or sub.name in _SKIP_TREE_DIRS:
        return False
    if sub.name in ("tests", "nk_tracking", "data") or _is_reparse_entry(sub) or _is_sandbox_cycle_dir(sub, sb_res):
        return False
    if (sub / "nk_tracking").exists() or (sub / ".staging").exists():
        return False
    if (sub / "__init__.py").is_file() or sub.name in ("_internal", "schemas", "scripts", "src", "src_app", "app"):
        return True
    return any(True for _ in sub.rglob("*.py"))


def _copy_flat_script_siblings(
    sb: ShadowSandbox, script_dir: Path, script_res: Path, overwrite: bool
) -> None:
    """Copia fino a 50 moduli Python fratelli non reparse dalla directory dello script."""
    sibling_py = [
        p for p in sorted(script_dir.glob("*.py"))
        if p.is_file() and p.resolve() != script_res and not _is_reparse_entry(p)
    ]
    if len(sibling_py) > 50:
        return
    for sib in sibling_py:
        sib_dst = _resolve_confined_sandbox_path(sb.sandbox_dir, sib.name)
        if overwrite or not sib_dst.exists():
            sb.copy_file(sib)


def copy_script_package_context(
    sb: ShadowSandbox,
    src_script: Path,
    overwrite: bool = True,
) -> Tuple[str, List[str]]:
    """Copia uno script con l'intero albero package nella sandbox e restituisce (rel_entry, py_roots)."""
    script_res = src_script.resolve()
    script_dir, sb_res, temp_res = script_res.parent, sb.sandbox_dir.resolve(), Path(tempfile.gettempdir()).resolve()
    pkg_root = _find_enclosing_package_root(script_dir)
    if pkg_root is not None and not _is_sandbox_cycle_dir(pkg_root, sb_res, temp_res):
        _copy_tree_to_sandbox(sb, pkg_root, pkg_root.name, overwrite=overwrite)
        target_rel = script_res.relative_to(pkg_root.parent).as_posix()
        return target_rel, [str(sb.sandbox_dir), str((sb.sandbox_dir / target_rel).parent)]

    target_dst = _resolve_confined_sandbox_path(sb.sandbox_dir, script_res.name)
    if overwrite or not target_dst.exists():
        sb.copy_file(script_res)
    if script_dir != temp_res:
        _copy_flat_script_siblings(sb, script_dir, script_res, overwrite)
        for sub in sorted(script_dir.iterdir()):
            if _should_copy_child_pkg(sub, sb_res):
                _copy_tree_to_sandbox(sb, sub, sub.name, overwrite=overwrite)
    return script_res.name, [str(sb.sandbox_dir)]

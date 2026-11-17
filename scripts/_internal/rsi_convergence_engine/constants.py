"""Costanti, risoluzione path overlay, cache AST e utilita I/O per RSI."""

from __future__ import annotations

import ast
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.nk_common.paths import resolve_scripts_dir, resolve_workspace_root

_scripts_dir = Path(resolve_scripts_dir(__file__))
_workspace_root = Path(resolve_workspace_root(__file__))

for _p in (
    _workspace_root,
    _workspace_root / "scripts",
    _workspace_root / ".staging" / "scripts",
    _scripts_dir,
):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(_scripts_dir) in sys.path:
    sys.path.remove(str(_scripts_dir))
sys.path.insert(0, str(_scripts_dir))

_IPC_LOCK = threading.Lock()
_IPC_CACHE: Dict[str, Any] = {}


def _get_ipc_contracts() -> Tuple[Any, Any, Any]:
    """Carica pigramente i contratti Pydantic per evitare import a freddo su CLI --help."""
    if "RSIDefectVector" in _IPC_CACHE:
        return (
            _IPC_CACHE["RSIDefectVector"],
            _IPC_CACHE["RSIIterationRecord"],
            _IPC_CACHE["RSISessionReport"],
        )
    with _IPC_LOCK:
        if "RSIDefectVector" in _IPC_CACHE:
            return (
                _IPC_CACHE["RSIDefectVector"],
                _IPC_CACHE["RSIIterationRecord"],
                _IPC_CACHE["RSISessionReport"],
            )
        try:
            from schemas.nk_ipc_contracts import (
                RSIDefectVector as _vec,
                RSIIterationRecord as _rec,
                RSISessionReport as _rep,
            )
        except ImportError:
            from scripts.schemas.nk_ipc_contracts import (
                RSIDefectVector as _vec,
                RSIIterationRecord as _rec,
                RSISessionReport as _rep,
            )
        _IPC_CACHE["RSIDefectVector"] = _vec
        _IPC_CACHE["RSIIterationRecord"] = _rec
        _IPC_CACHE["RSISessionReport"] = _rep
        return _vec, _rec, _rep


def __getattr__(name: str) -> Any:
    """Risolve pigramente i contratti RSI Pydantic al primo accesso."""
    if name in ("RSIDefectVector", "DefectVector"):
        return _get_ipc_contracts()[0]
    if name == "RSIIterationRecord":
        return _get_ipc_contracts()[1]
    if name == "RSISessionReport":
        return _get_ipc_contracts()[2]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


MODE_ITERATION_CAPS: Dict[str, int] = {
    "mode_c": 2,
    "c": 2,
    "vibe": 2,
    "mode_b": 3,
    "b": 3,
    "fast": 3,
    "mode_a": 4,
    "a": 4,
    "sovereign": 4,
}

EXCLUDED_SCAN_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".staging",
    ".pytest_cache",
    "NK_External_Projects",
    "NK_Hub",
    "01_Agenti_Skill_e_Regole",
    "nk_docs_and_setup",
}

_TELEMETRY_LOCK = threading.Lock()
_FILE_AST_CACHE: Dict[Tuple[str, int, int], Tuple[str, Optional[ast.AST]]] = {}


def _get_cached_file_and_ast(file_path: Path) -> Tuple[str, Optional[ast.AST]]:
    """Restituisce (source_text, ast_tree) dalla cache in-memory indicizzata per (path_str, mtime_ns, size)."""
    resolved = file_path.resolve()
    st = resolved.stat()
    key = (str(resolved), int(st.st_mtime_ns), int(st.st_size))
    cached = _FILE_AST_CACHE.get(key)
    if cached is not None:
        return cached
    source_text = resolved.read_text(encoding="utf-8", errors="replace")
    ast_tree: Optional[ast.AST] = None
    if resolved.suffix == ".py":
        try:
            ast_tree = ast.parse(source_text, filename=str(resolved))
        except Exception:
            ast_tree = None
    _FILE_AST_CACHE[key] = (source_text, ast_tree)
    return source_text, ast_tree


def _collect_overlay_md_files(
    root: Path,
    rel_subdir: str,
    recursive: bool = True,
) -> List[Path]:
    """Unisce i file Markdown di produzione con gli override e le aggiunte presenti in .staging/."""
    resolved_root = Path(root).resolve()
    clean_sub = rel_subdir.strip("/\\")
    if resolved_root.name == ".staging":
        prod_base = resolved_root.parent / clean_sub if clean_sub else resolved_root.parent
        stg_base = resolved_root / clean_sub if clean_sub else resolved_root
        deleted_manifest = resolved_root / ".deleted_files.json"
    else:
        prod_base = resolved_root / clean_sub if clean_sub else resolved_root
        stg_base = (
            resolved_root / ".staging" / clean_sub
            if clean_sub
            else resolved_root / ".staging"
        )
        deleted_manifest = resolved_root / ".staging" / ".deleted_files.json"

    deleted_rels: Set[str] = set()
    if deleted_manifest.is_file():
        try:
            raw_del = json.loads(deleted_manifest.read_text(encoding="utf-8"))
            if isinstance(raw_del, list):
                deleted_rels = {
                    str(item).strip().replace("\\", "/").lstrip("/")
                    for item in raw_del
                    if str(item).strip()
                }
        except Exception:
            pass

    overlay_map: Dict[str, Path] = {}
    if prod_base.exists() and prod_base.is_dir():
        prod_iter = prod_base.rglob("*.md") if recursive else prod_base.glob("*.md")
        for md_p in sorted(prod_iter):
            if not md_p.is_file():
                continue
            rel_inside = md_p.relative_to(prod_base).as_posix()
            if any(part in EXCLUDED_SCAN_DIRS for part in Path(rel_inside).parts):
                continue
            full_rel = f"{clean_sub}/{rel_inside}" if clean_sub else rel_inside
            if full_rel in deleted_rels:
                continue
            overlay_map[rel_inside] = md_p

    if stg_base.exists() and stg_base.is_dir() and stg_base.resolve() != prod_base.resolve():
        stg_iter = stg_base.rglob("*.md") if recursive else stg_base.glob("*.md")
        for md_p in sorted(stg_iter):
            if not md_p.is_file():
                continue
            rel_inside = md_p.relative_to(stg_base).as_posix()
            if any(
                part in (EXCLUDED_SCAN_DIRS - {".staging"})
                for part in Path(rel_inside).parts
            ):
                continue
            overlay_map[rel_inside] = md_p

    return [overlay_map[k] for k in sorted(overlay_map.keys())]


def _is_excluded_rel_path(path: Path, base_root: Path) -> bool:
    """Verifica se il percorso relativo a base_root attraversa directory escluse."""
    try:
        rel_parts = path.relative_to(base_root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in EXCLUDED_SCAN_DIRS for part in rel_parts)


def _extract_sast_report_count(sast_report_path: Optional[Path | str]) -> int:
    """Estrae il conteggio di violazioni SAST critiche da un report JSON esterno."""
    if not sast_report_path:
        return 0
    rpath = Path(sast_report_path)
    if not rpath.exists() or not rpath.is_file():
        return 0
    try:
        data = json.loads(rpath.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, dict):
            for key in (
                "sast_critical",
                "sast_violations_count",
                "critical_count",
                "total_sast_violations",
            ):
                if key in data and isinstance(data[key], int):
                    return max(0, int(data[key]))
            metrics = data.get("metrics")
            if isinstance(metrics, dict) and "sast_violations_count" in metrics:
                return max(0, int(metrics["sast_violations_count"]))
            violations = data.get("violations")
            if isinstance(violations, list):
                return len(violations)
    except Exception:
        pass
    return 0


def resolve_candidate_impl(root: Path, rel_path: str) -> Path:
    """Risolve un singolo file dando priorita a .staging/ se presente."""
    staging_cand = root / ".staging" / rel_path
    if staging_cand.exists():
        return staging_cand
    direct_cand = root / rel_path
    if direct_cand.exists():
        return direct_cand
    if root.name == ".staging":
        parent_cand = root.parent / rel_path
        if parent_cand.exists():
            return parent_cand
    return direct_cand


def load_staging_deleted_set_impl(root: Path) -> Set[str]:
    """Carica i percorsi relativi destinati a cancellazione da .staging/.deleted_files.json."""
    del_manifest = root / ".staging" / ".deleted_files.json"
    if not del_manifest.is_file():
        return set()
    try:
        raw_del = json.loads(del_manifest.read_text(encoding="utf-8"))
        del_items = (
            raw_del.get("deleted_files", [])
            if isinstance(raw_del, dict)
            else raw_del
        )
        if isinstance(del_items, list):
            return {
                str(item).replace("\\", "/").lstrip("/") for item in del_items
            }
    except Exception:
        pass
    return set()

# -*- coding: utf-8 -*-
"""Costanti, risoluzione path overlay (P0-02), cache AST RepoSnapshotCache e lazy bridge."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from _internal.nk_common.paths import (
    reconfigure_streams as _nk_reconfigure_streams,
    resolve_scripts_dir,
    resolve_workspace_root,
)
from _internal.nk_common.repo_snapshot_cache import get_repo_snapshot_cache
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

_scripts_dir = Path(resolve_scripts_dir(__file__))
_workspace_root = Path(resolve_workspace_root(__file__))

for _p in (_workspace_root, _workspace_root / "scripts", _workspace_root / ".staging" / "scripts", _scripts_dir):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(_scripts_dir) in sys.path:
    sys.path.remove(str(_scripts_dir))
sys.path.insert(0, str(_scripts_dir))

_IPC_LOCK = threading.Lock()
_IPC_CACHE: Dict[str, Any] = {}
_HOOKS: Dict[str, Callable[..., Any]] = {}
_FALLBACK_STATE: Dict[str, Any] = {
    "reconfigured": False, "hsm_loaded": False, "hsm_cls": None,
    "agv_loaded": False, "agv_cls": None, "ste100_fn": None, "grounding_fn": None,
}
MODE_ITERATION_CAPS: Dict[str, int] = {
    "mode_d": 0, "d": 0, "discovery": 0,
    "mode_c": 2, "c": 2, "vibe": 2,
    "mode_b": 3, "b": 3, "fast": 3,
    "mode_a": 4, "a": 4, "sovereign": 4,
}
VIBE_SCAN_SUFFIXES: Tuple[str, ...] = (".py", ".md", ".json", ".ts", ".tsx", ".js", ".jsx", ".css")
EXCLUDED_SCAN_DIRS: Set[str] = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".staging",
    ".pytest_cache", "NK_External_Projects", "NK_Hub", "01_Agenti_Skill_e_Regole", "nk_docs_and_setup",
}
_TELEMETRY_LOCK = threading.Lock()
_FILE_AST_CACHE: Dict[Tuple[str, int, int], Tuple[str, Optional[ast.AST]]] = {}


def _load_ipc_contract_tuple() -> Tuple[Any, Any, Any]:
    try:
        from schemas.nk_ipc_contracts import RSIDefectVector as _vec, RSIIterationRecord as _rec, RSISessionReport as _rep
    except ImportError:
        from scripts.schemas.nk_ipc_contracts import RSIDefectVector as _vec, RSIIterationRecord as _rec, RSISessionReport as _rep
    return _vec, _rec, _rep


def _get_ipc_contracts() -> Tuple[Any, Any, Any]:
    """Carica pigramente i contratti Pydantic RSI."""
    if "RSIDefectVector" in _IPC_CACHE:
        return _IPC_CACHE["RSIDefectVector"], _IPC_CACHE["RSIIterationRecord"], _IPC_CACHE["RSISessionReport"]
    with _IPC_LOCK:
        if "RSIDefectVector" not in _IPC_CACHE:
            _vec, _rec, _rep = _load_ipc_contract_tuple()
            _IPC_CACHE.update({"RSIDefectVector": _vec, "RSIIterationRecord": _rec, "RSISessionReport": _rep})
        return _IPC_CACHE["RSIDefectVector"], _IPC_CACHE["RSIIterationRecord"], _IPC_CACHE["RSISessionReport"]


def __getattr__(name: str) -> Any:
    """Risolve pigramente i contratti RSI Pydantic al primo accesso."""
    if name in ("RSIDefectVector", "DefectVector"):
        return _get_ipc_contracts()[0]
    if name == "RSIIterationRecord":
        return _get_ipc_contracts()[1]
    if name == "RSISessionReport":
        return _get_ipc_contracts()[2]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _get_cached_file_and_ast(file_path: Path) -> Tuple[str, Optional[ast.AST]]:
    """Restituisce (source_text, ast_tree) delegando a RepoSnapshotCache condivisa."""
    resolved = file_path.resolve()
    st = resolved.stat()
    key = (str(resolved), int(st.st_mtime_ns), int(st.st_size))
    if key in _FILE_AST_CACHE:
        return _FILE_AST_CACHE[key]
    source_text, ast_tree, _ = get_repo_snapshot_cache().get_text_and_ast(resolved)
    _FILE_AST_CACHE[key] = (source_text, ast_tree)
    return source_text, ast_tree


def _strip_leading_prefix(clean: str, prefix: str, allow_strip: bool) -> Tuple[str, bool]:
    if allow_strip and clean.startswith(prefix):
        return clean[len(prefix) :].lstrip("/"), True
    return clean, False


def normalize_rel_for_root(root: Path, rel_path: str) -> str:
    """Normalizza un path relativo rimuovendo prefissi duplicati NK_Hub/ (fix P0-02)."""
    clean = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    while clean.startswith("./"):
        clean = clean[2:].lstrip("/")
    resolved_root = Path(root).resolve()
    is_stg = resolved_root.name == ".staging"
    prod_root = resolved_root.parent if is_stg else resolved_root
    prefix = f"{prod_root.name}/" if prod_root.name else ""
    can_strip_prod = bool(prefix) and (prod_root.name == "NK_Hub" or not (prod_root / prod_root.name).is_dir())
    while clean:
        clean, stripped = _strip_leading_prefix(clean, prefix, can_strip_prod)
        if not stripped:
            clean, stripped = _strip_leading_prefix(clean, ".staging/", is_stg)
        if not stripped:
            break
    return clean


def _parse_deleted_manifest_rels(deleted_manifest: Path) -> Set[str]:
    """Legge .deleted_files.json tramite parser SSOT tas_ssot_io in modo fail-safe."""
    if not deleted_manifest.is_file():
        return set()
    try:
        items = parse_deleted_files_manifest(deleted_manifest)
    except (OSError, ValueError):
        return set()
    return {str(item).strip().replace("\\", "/").lstrip("/") for item in items if item is not None and str(item).strip()}


def _scan_md_tree(base_dir: Path, recursive: bool, excluded_dirs: Set[str], deleted_rels: Set[str], clean_sub: str) -> Dict[str, Path]:
    """Raccoglie file Markdown da una directory escludendo cartelle ignorate e rimossi."""
    out: Dict[str, Path] = {}
    if not base_dir.is_dir():
        return out
    iterator = base_dir.rglob("*.md") if recursive else base_dir.glob("*.md")
    for md_p in sorted(iterator):
        if not md_p.is_file():
            continue
        rel_inside = md_p.relative_to(base_dir).as_posix()
        full_rel = f"{clean_sub}/{rel_inside}" if clean_sub else rel_inside
        if not any(part in excluded_dirs for part in Path(rel_inside).parts) and full_rel not in deleted_rels:
            out[rel_inside] = md_p
    return out


def _collect_overlay_md_files(root: Path, rel_subdir: str, recursive: bool = True) -> List[Path]:
    """Unisce i file Markdown di produzione con gli override presenti in .staging/."""
    resolved_root = Path(root).resolve()
    clean_sub = normalize_rel_for_root(resolved_root, rel_subdir).strip("/")
    is_stg = resolved_root.name == ".staging"
    prod_root = resolved_root.parent if is_stg else resolved_root
    stg_root = resolved_root if is_stg else resolved_root / ".staging"
    prod_base, stg_base = (prod_root / clean_sub if clean_sub else prod_root), (stg_root / clean_sub if clean_sub else stg_root)
    deleted_rels = _parse_deleted_manifest_rels(stg_root / ".deleted_files.json")
    overlay_map = _scan_md_tree(prod_base, recursive, EXCLUDED_SCAN_DIRS, deleted_rels, clean_sub)
    if stg_base.resolve() != prod_base.resolve():
        overlay_map.update(_scan_md_tree(stg_base, recursive, EXCLUDED_SCAN_DIRS - {".staging"}, set(), clean_sub))
    return [overlay_map[k] for k in sorted(overlay_map.keys())]


def _is_excluded_rel_path(path: Path, base_root: Path) -> bool:
    """Verifica se il percorso relativo a base_root attraversa directory escluse."""
    try:
        rel_parts = path.relative_to(base_root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in EXCLUDED_SCAN_DIRS for part in rel_parts)


def resolve_candidate_impl(root: Path, rel_path: str) -> Path:
    """Risolve un file privilegiando .staging/ senza duplicare il prefisso NK_Hub/ (P0-02)."""
    norm_rel = normalize_rel_for_root(root, rel_path)
    for cand in (root / ".staging" / norm_rel, root / norm_rel):
        if cand.exists():
            return cand
    if root.name == ".staging" and (root.parent / norm_rel).exists():
        return root.parent / norm_rel
    return root / norm_rel


def load_staging_deleted_set_impl(root: Path) -> Set[str]:
    """Carica i percorsi relativi destinati a cancellazione da .staging/.deleted_files.json."""
    base = Path(root)
    return _parse_deleted_manifest_rels(base / ".deleted_files.json" if base.name == ".staging" else base / ".staging" / ".deleted_files.json")


def register_lazy_hooks(
    *, reconfigure_fn: Callable[[], None], hsm_fn: Callable[[], Any], agv_fn: Callable[[], Any],
    ste100_fn: Callable[[], Callable[..., Dict[str, Any]]], grounding_fn: Callable[[], Optional[Callable[..., Dict[str, Any]]]],
) -> None:
    """Registra i callback lazy della facciata RSI."""
    _HOOKS.update({"reconfigure": reconfigure_fn, "hsm": hsm_fn, "agv": agv_fn, "ste100": ste100_fn, "grounding": grounding_fn})


def _import_first_attr(candidates: Tuple[Tuple[str, str], ...]) -> Any:
    for mod_name, attr_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, attr_name):
                return getattr(mod, attr_name)
        except ImportError:
            continue
    return None


def fallback_load_ntt_module(scripts_dir: Optional[Path] = None, workspace_root: Optional[Path] = None) -> Any:
    """Carica esplicitamente scripts/nk_transcript_tools.py in assenza della facciata."""
    s_dir, ws_root = Path(scripts_dir or _scripts_dir), Path(workspace_root or _workspace_root)
    for cand in (s_dir / "nk_transcript_tools.py", ws_root / ".staging" / "scripts" / "nk_transcript_tools.py", ws_root / "scripts" / "nk_transcript_tools.py"):
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("_rsi_nk_transcript_tools_fallback", cand)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


def get_reconfigure_streams() -> None:
    if callable(fn := _HOOKS.get("reconfigure")):
        fn()
    elif not _FALLBACK_STATE["reconfigured"]:
        _nk_reconfigure_streams()
        _FALLBACK_STATE["reconfigured"] = True


def _direct_load_hsm_cls() -> Any:
    if not _FALLBACK_STATE["hsm_loaded"]:
        _FALLBACK_STATE["hsm_loaded"] = True
        _FALLBACK_STATE["hsm_cls"] = _import_first_attr((("auto_heal_pipeline", "HealingSnapshotManager"), ("scripts.auto_heal_pipeline", "HealingSnapshotManager")))
    return _FALLBACK_STATE["hsm_cls"]


def get_healing_snapshot_manager_cls() -> Any:
    return fn() if callable(fn := _HOOKS.get("hsm")) else _direct_load_hsm_cls()


def _direct_load_agv_cls() -> Any:
    if not _FALLBACK_STATE["agv_loaded"]:
        _FALLBACK_STATE["agv_loaded"] = True
        _FALLBACK_STATE["agv_cls"] = _import_first_attr((("ast_guard_validator", "ASTGuardValidator"), ("scripts.ast_guard_validator", "ASTGuardValidator")))
    return _FALLBACK_STATE["agv_cls"]


def get_ast_guard_validator() -> Any:
    return fn() if callable(fn := _HOOKS.get("agv")) else _direct_load_agv_cls()


def _direct_load_ste100_fn() -> Callable[..., Dict[str, Any]]:
    if _FALLBACK_STATE["ste100_fn"] is None:
        res = _import_first_attr((("nk_transcript_tools", "verify_ste100_compliance"), ("scripts.nk_transcript_tools", "verify_ste100_compliance")))
        if res is None and (mod := fallback_load_ntt_module()):
            res = getattr(mod, "verify_ste100_compliance", None)
        if res is None:
            raise RuntimeError("SSOT nk_transcript_tools.verify_ste100_compliance non disponibile.")
        _FALLBACK_STATE["ste100_fn"] = res
    return _FALLBACK_STATE["ste100_fn"]


def get_ste100_validator() -> Callable[..., Dict[str, Any]]:
    return fn() if callable(fn := _HOOKS.get("ste100")) else _direct_load_ste100_fn()


def _direct_load_grounding_fn() -> Optional[Callable[..., Dict[str, Any]]]:
    if _FALLBACK_STATE["grounding_fn"] is None:
        res = _import_first_attr((("nk_transcript_tools", "verify_report_grounding"), ("scripts.nk_transcript_tools", "verify_report_grounding")))
        if res is None and (mod := fallback_load_ntt_module()):
            res = getattr(mod, "verify_report_grounding", None)
        _FALLBACK_STATE["grounding_fn"] = res
    return _FALLBACK_STATE["grounding_fn"]


def get_report_grounding_validator() -> Optional[Callable[..., Dict[str, Any]]]:
    return fn() if callable(fn := _HOOKS.get("grounding")) else _direct_load_grounding_fn()


def facade_get_cached_attr(facade_ns: Dict[str, Any], flag_key: str, val_key: str, getter: Callable[[], Any]) -> Any:
    """Helper stateless per mantenere CC=1 e nesting=0 nelle funzioni della facciata."""
    if flag_key and facade_ns.get(flag_key):
        return facade_ns.get(val_key)
    if not flag_key and facade_ns.get(val_key) is not None:
        return facade_ns[val_key]
    val = getter()
    facade_ns[val_key] = val
    if flag_key:
        facade_ns[flag_key] = True
    return val


def facade_ensure_exports_loaded(facade_ns: Dict[str, Any], export_map: Dict[str, Tuple[str, str]], **hook_fns: Any) -> Dict[str, Any]:
    """Registra hook e popola gli export della facciata preservando CC=1 lato facciata."""
    if not facade_ns.get("_HOOKS_REGISTERED"):
        register_lazy_hooks(**hook_fns)
        facade_ns["_HOOKS_REGISTERED"] = True
    if not facade_ns.get("_EXPORTS_LOADED"):
        for exp_name, (mod_path, attr_name) in export_map.items():
            facade_ns[exp_name] = getattr(importlib.import_module(mod_path), attr_name)
        facade_ns["_EXPORTS_LOADED"] = True
    return facade_ns

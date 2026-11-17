"""Risoluzione simboli per facade scripts/*.py con re-export da _internal.<pkg>."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.ast_repo_mapper.models import (
    SymbolEdge,
    SymbolNode,
    SymbolType,
)
from _internal.ast_repo_mapper.parser_resilient import ResilientParser
from _internal.ast_repo_mapper.symbol_extractor import SymbolExtractor

try:
    from _internal.nk_common.ast_exports import (
        group_lazy_exports_by_module,
        resolve_dotted_module_file,
    )
except ImportError:  # pragma: no cover
    import _internal.nk_common as _nk_common_pkg

    _stg_common_dir = str(Path(__file__).resolve().parent.parent / "nk_common")
    if hasattr(_nk_common_pkg, "__path__") and _stg_common_dir not in _nk_common_pkg.__path__:
        _nk_common_pkg.__path__.insert(0, _stg_common_dir)
    from _internal.nk_common.ast_exports import (
        group_lazy_exports_by_module,
        resolve_dotted_module_file,
    )


def _candidate_scripts_roots(file_path: Path, root_dir: Optional[Path]) -> List[Path]:
    """Restituisce le radici candidate per risolvere package _internal."""
    roots: List[Path] = []
    seen: Set[Path] = set()
    cands: List[Path] = []
    if root_dir is not None:
        cands.append(root_dir / ".staging" / "scripts")
    cands.append(file_path.parent)
    if root_dir is not None:
        cands.append(root_dir / "scripts")
    for cand in cands:
        try:
            res = cand.resolve()
        except OSError:
            res = cand
        if res not in seen and cand.is_dir():
            seen.add(res)
            roots.append(cand)
    return roots


def _resolve_internal_file(
    mod_name: str,
    roots: List[Path],
) -> Optional[Path]:
    """Mappa un nome modulo _internal.* sul file .py corrispondente."""
    clean = mod_name[len("scripts.") :] if mod_name.startswith("scripts.") else mod_name
    if clean != "_internal" and not clean.startswith("_internal."):
        return None
    return resolve_dotted_module_file(clean, roots)


def _resolve_relative_module(
    current_mod: str,
    node_mod: Optional[str],
    level: int,
    current_file: Path,
) -> str:
    """Risolve un import relativo rispetto al package corrente dentro _internal."""
    if level <= 0:
        return node_mod or ""
    parts = current_mod.split(".")
    pkg_parts = parts if current_file.name == "__init__.py" else parts[:-1]
    trim = max(0, level - 1)
    base_parts = pkg_parts[: len(pkg_parts) - trim] if trim <= len(pkg_parts) else []
    if node_mod:
        base_parts.extend(node_mod.split("."))
    return ".".join(base_parts)


def _collect_from_internal_module(
    mod_name: str,
    wanted_names: Optional[Set[str]],
    roots: List[Path],
    facade_rel_str: str,
    visited: Set[Tuple[Path, Tuple[str, ...]]],
    collected_nodes: Dict[str, SymbolNode],
    collected_edges: List[SymbolEdge],
    collected_calls: Dict[str, Set[str]],
    dep_stamps: Dict[str, Tuple[float, int]],
) -> None:
    """Estrae simboli esportati da un modulo _internal mantenendo module_path della facade."""
    sub_file = _resolve_internal_file(mod_name, roots)
    if sub_file is None:
        return
    try:
        resolved_sub = sub_file.resolve()
        st = sub_file.stat()
    except OSError:
        return

    visit_key = (
        resolved_sub,
        tuple(sorted(wanted_names)) if wanted_names is not None else ("*",),
    )
    if visit_key in visited:
        return
    visited.add(visit_key)
    dep_stamps[str(sub_file)] = (st.st_mtime, st.st_size)

    try:
        sub_content = sub_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    sub_lines = sub_content.splitlines(keepends=True)
    sub_tree, _ = ResilientParser.parse_safe(sub_content, filename=facade_rel_str)
    if not sub_tree:
        return

    sub_ext = SymbolExtractor(module_path=facade_rel_str, source_lines=sub_lines)
    sub_ext.visit(sub_tree)

    kept_ids: Set[str] = set()
    kept_top_names: Set[str] = set()
    for node in sub_ext.graph.nodes.values():
        if node.symbol_type == SymbolType.IMPORT or node.parent_id is not None:
            continue
        if wanted_names is None or node.name in wanted_names:
            kept_ids.add(node.id)
            kept_top_names.add(node.name)

    changed = True
    while changed:
        changed = False
        for node in sub_ext.graph.nodes.values():
            if node.id not in kept_ids and node.parent_id in kept_ids:
                kept_ids.add(node.id)
                changed = True

    for nid in kept_ids:
        if nid not in collected_nodes:
            collected_nodes[nid] = sub_ext.graph.nodes[nid]

    for edge in sub_ext.graph.edges:
        if edge.source_id in kept_ids and edge.target_id in kept_ids:
            collected_edges.append(edge)

    for sc_id, sc_vals in sub_ext.scope_calls.items():
        if sc_id in kept_ids:
            collected_calls.setdefault(sc_id, set()).update(sc_vals)

    remaining = None if wanted_names is None else (wanted_names - kept_top_names)
    if (remaining is None or remaining) and isinstance(sub_tree, ast.Module):
        pending_targets: List[Tuple[str, Set[str]]] = []
        for stmt in sub_tree.body:
            if not isinstance(stmt, ast.ImportFrom):
                continue
            tgt_mod = _resolve_relative_module(mod_name, stmt.module, stmt.level, sub_file)
            if not (tgt_mod.startswith("_internal.") or tgt_mod.startswith("scripts._internal.")):
                continue
            if any(a.name == "*" for a in stmt.names):
                sub_wanted: Optional[Set[str]] = remaining
            else:
                names = {a.name for a in stmt.names}
                sub_wanted = names if remaining is None else (names & remaining)
                if not sub_wanted:
                    continue
            pending_targets.append((tgt_mod, sub_wanted if sub_wanted is not None else set()))

        for raw_lazy_mod, lazy_names in group_lazy_exports_by_module(sub_tree).items():
            if raw_lazy_mod.startswith("."):
                stripped = raw_lazy_mod.lstrip(".")
                lvl = len(raw_lazy_mod) - len(stripped)
                tgt_mod = _resolve_relative_module(mod_name, stripped or None, lvl, sub_file)
            else:
                tgt_mod = raw_lazy_mod
            if not (tgt_mod.startswith("_internal.") or tgt_mod.startswith("scripts._internal.")):
                continue
            sub_wanted_lazy = set(lazy_names) if remaining is None else (set(lazy_names) & remaining)
            if not sub_wanted_lazy:
                continue
            pending_targets.append((tgt_mod, sub_wanted_lazy))

        for tgt_mod, target_wanted in pending_targets:
            _collect_from_internal_module(
                mod_name=tgt_mod,
                wanted_names=target_wanted or remaining,
                roots=roots,
                facade_rel_str=facade_rel_str,
                visited=visited,
                collected_nodes=collected_nodes,
                collected_edges=collected_edges,
                collected_calls=collected_calls,
                dep_stamps=dep_stamps,
            )


def extract_python_module_symbols(
    file_path: Path,
    rel_str: str,
    content: str,
    root_dir: Optional[Path] = None,
) -> Tuple[List[SymbolNode], List[SymbolEdge], Dict[str, Set[str]], List[List[Any]]]:
    """Estrae nodi, archi e chiamate da un .py includendo re-export _internal e _LAZY_EXPORT_MAP."""
    lines = content.splitlines(keepends=True)
    tree, _ = ResilientParser.parse_safe(content, filename=rel_str)
    extractor = SymbolExtractor(module_path=rel_str, source_lines=lines)
    if tree:
        extractor.visit(tree)

    nodes_map: Dict[str, SymbolNode] = dict(extractor.graph.nodes)
    edges_list: List[SymbolEdge] = list(extractor.graph.edges)
    scope_calls_map: Dict[str, Set[str]] = {k: set(v) for k, v in extractor.scope_calls.items()}
    dep_stamps: Dict[str, Tuple[float, int]] = {}

    is_canonical_script = rel_str.startswith("scripts/") or file_path.parent.name in (
        "scripts",
        "schemas",
    )
    if is_canonical_script and isinstance(tree, ast.Module):
        roots = _candidate_scripts_roots(file_path, root_dir)
        visited: Set[Tuple[Path, Tuple[str, ...]]] = set()
        for stmt in tree.body:
            if not isinstance(stmt, ast.ImportFrom) or not stmt.module:
                continue
            mod = stmt.module
            if not (mod.startswith("_internal.") or mod.startswith("scripts._internal.")):
                continue
            wanted: Optional[Set[str]] = (
                None if any(a.name == "*" for a in stmt.names) else {a.name for a in stmt.names}
            )
            _collect_from_internal_module(
                mod_name=mod,
                wanted_names=wanted,
                roots=roots,
                facade_rel_str=rel_str,
                visited=visited,
                collected_nodes=nodes_map,
                collected_edges=edges_list,
                collected_calls=scope_calls_map,
                dep_stamps=dep_stamps,
            )

        for mod_name, lazy_names in group_lazy_exports_by_module(tree).items():
            if not (
                mod_name.startswith("_internal.")
                or mod_name.startswith("scripts._internal.")
            ):
                continue
            _collect_from_internal_module(
                mod_name=mod_name,
                wanted_names=set(lazy_names),
                roots=roots,
                facade_rel_str=rel_str,
                visited=visited,
                collected_nodes=nodes_map,
                collected_edges=edges_list,
                collected_calls=scope_calls_map,
                dep_stamps=dep_stamps,
            )

    deps_meta = [[p, m, s] for p, (m, s) in sorted(dep_stamps.items())]
    return list(nodes_map.values()), edges_list, scope_calls_map, deps_meta


def internal_deps_still_valid(c_entry: Dict[str, Any]) -> bool:
    """Verifica se eventuali dipendenze _internal memorizzate in cache sono ancora valide."""
    for item in c_entry.get("internal_deps", ()):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return False
        dep_path_str, dep_mtime, dep_size = item
        try:
            st = Path(str(dep_path_str)).stat()
        except OSError:
            return False
        if st.st_mtime != dep_mtime or st.st_size != dep_size:
            return False
    return True

"""Esportazione snapshot markdown e interrogazione sottografo simboli."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from _internal.ast_repo_mapper.facade_resolver import (
    extract_python_module_symbols,
    internal_deps_still_valid,
)
from _internal.ast_repo_mapper.generator import RepoMapGenerator
from _internal.ast_repo_mapper.models import (
    CACHE_SCHEMA_VERSION,
    EdgeType,
    RepoMapConfig,
    RepoMapResult,
    SymbolEdge,
    SymbolGraph,
    SymbolNode,
    SymbolType,
)
from _internal.ast_repo_mapper.polyglot_and_cache import (
    AtomicCacheManager,
    PolyglotExtractor,
)


def export_markdown_snapshot(root_dir: Path, output_path: Path, max_tokens: int = 1100) -> RepoMapResult:
    """Genera e scrive autonomamente lo snapshot canonico repo_map.md."""
    cfg = RepoMapConfig(max_tokens=max_tokens, polyglot=True)
    res = RepoMapGenerator.generate(root_dir=root_dir, config=cfg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(res.content, encoding="utf-8")
    return res


def query_symbol_subgraph(
    symbol_name: str,
    root: Optional[Path] = None,
    root_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Estrae definizioni, chiamanti (callers) e chiamati (callees) per un simbolo senza modificare repo_map.md."""
    effective_root = root_dir if root_dir is not None else root
    root_dir = Path(effective_root).resolve() if effective_root is not None else Path(".").resolve()
    target_sym = str(symbol_name or "").strip()
    if not target_sym:
        return {
            "symbol": "",
            "found": False,
            "definitions": [],
            "callers": [],
            "callees": [],
        }

    subgraph_exts = {".py", ".js", ".ts", ".jsx", ".tsx"}
    file_map: Dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in RepoMapGenerator.EXCLUDED_DIRS]
        dpath = Path(dirpath)
        for fname in filenames:
            p = dpath / fname
            if p.suffix.lower() in subgraph_exts:
                try:
                    rel_parts = p.relative_to(root_dir).parts
                except ValueError:
                    rel_parts = p.parts
                if any(part in RepoMapGenerator.EXCLUDED_DIRS for part in rel_parts):
                    continue
                rel_key = str(p.relative_to(root_dir)).replace("\\", "/")
                file_map[rel_key] = p

    master_graph = SymbolGraph()
    staging_root = root_dir / ".staging"
    if staging_root.exists() and staging_root.is_dir():
        staging_excluded = RepoMapGenerator.EXCLUDED_DIRS - {".staging"}
        for dirpath, dirnames, filenames in os.walk(staging_root, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in staging_excluded]
            dpath = Path(dirpath)
            for fname in filenames:
                p = dpath / fname
                if p.suffix.lower() in subgraph_exts:
                    try:
                        rel_parts = p.relative_to(staging_root).parts
                    except ValueError:
                        rel_parts = p.parts
                    if any(part in staging_excluded for part in rel_parts):
                        continue
                    rel_key = str(p.relative_to(staging_root)).replace("\\", "/")
                    file_map[rel_key] = p
    scope_calls: Dict[str, Set[str]] = {}
    node_by_id: Dict[str, SymbolNode] = {}

    cache_path = AtomicCacheManager.get_default_cache_path(root_dir)
    cached_payload = AtomicCacheManager.load_safe(cache_path)
    cached_files: Dict[str, Any] = (
        dict((cached_payload or {}).get("files", {}))
        if (cached_payload or {}).get("version") == CACHE_SCHEMA_VERSION
        else {}
    )
    cache_dirty = False

    for rel_str, file_path in sorted(file_map.items()):
        try:
            st = file_path.stat()
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            continue

        c_entry = cached_files.get(rel_str)
        if (
            c_entry
            and c_entry.get("mtime") == mtime
            and c_entry.get("size") == size
            and c_entry.get("abs_path") == str(file_path)
            and "nodes" in c_entry
            and "edges" in c_entry
            and "scope_calls" in c_entry
            and internal_deps_still_valid(c_entry)
        ):
            for nd in c_entry.get("nodes", []):
                try:
                    node = SymbolNode.model_validate(nd)
                    master_graph.add_node(node)
                    node_by_id[node.id] = node
                except Exception:
                    pass
            for ed in c_entry.get("edges", []):
                try:
                    master_graph.add_edge(SymbolEdge.model_validate(ed))
                except Exception:
                    pass
            for sc_id, sc_list in c_entry.get("scope_calls", {}).items():
                scope_calls[sc_id] = set(sc_list)
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        file_nodes: List[SymbolNode] = []
        file_edges: List[SymbolEdge] = []
        raw_scope_calls: Dict[str, Set[str]] = {}
        internal_deps: List[List[Any]] = []

        if file_path.suffix.lower() == ".py":
            file_nodes, file_edges, raw_scope_calls, internal_deps = extract_python_module_symbols(
                file_path=file_path,
                rel_str=rel_str,
                content=content,
                root_dir=root_dir,
            )
            for node in file_nodes:
                master_graph.add_node(node)
                node_by_id[node.id] = node
            for sc_id, called_names in raw_scope_calls.items():
                scope_calls[sc_id] = set(called_names)
            for edge in file_edges:
                master_graph.add_edge(edge)
        else:
            p_nodes = PolyglotExtractor.extract_symbols(rel_str, content)
            p_edges, p_calls = PolyglotExtractor.extract_call_edges(
                rel_str, content, p_nodes
            )
            for node in p_nodes:
                master_graph.add_node(node)
                node_by_id[node.id] = node
                file_nodes.append(node)
            for sc_id, called_names in p_calls.items():
                scope_calls[sc_id] = set(called_names)
                raw_scope_calls[sc_id] = set(called_names)
            for edge in p_edges:
                master_graph.add_edge(edge)
                file_edges.append(edge)

        cached_files[rel_str] = {
            "abs_path": str(file_path),
            "mtime": mtime,
            "size": size,
            "internal_deps": internal_deps,
            "nodes": [n.model_dump() for n in file_nodes],
            "edges": [e.model_dump() for e in file_edges],
            "scope_calls": {
                k: sorted(v) for k, v in raw_scope_calls.items()
            },
        }
        cache_dirty = True

    if cache_dirty:
        AtomicCacheManager.save_atomic(
            {"version": CACHE_SCHEMA_VERSION, "files": cached_files}, cache_path
        )

    RepoMapGenerator._link_cross_module_edges(master_graph)
    RepoMapGenerator._link_cross_file_calls(master_graph, scope_calls)

    matched_nodes: List[SymbolNode] = []
    for node in master_graph.nodes.values():
        if node.symbol_type == SymbolType.IMPORT:
            continue
        if (
            node.name == target_sym
            or node.id == target_sym
            or node.id.endswith(f":{target_sym}")
            or node.id.endswith(f".{target_sym}")
        ):
            matched_nodes.append(node)

    definitions: List[Dict[str, Any]] = [
        {
            "id": n.id,
            "name": n.name,
            "symbol_type": (
                n.symbol_type.value
                if hasattr(n.symbol_type, "value")
                else str(n.symbol_type)
            ),
            "module_path": n.module_path,
            "line_start": n.line_start,
            "line_end": n.line_end,
            "signature": n.signature or n.name,
        }
        for n in matched_nodes
    ]

    matched_ids = {n.id for n in matched_nodes}
    matched_names = {n.name for n in matched_nodes} | {target_sym}

    caller_ids: Set[str] = set()
    callee_names: Set[str] = set()

    for edge in master_graph.edges:
        if edge.edge_type == EdgeType.CALL:
            if edge.target_id in matched_ids:
                caller_ids.add(edge.source_id)
            if edge.source_id in matched_ids:
                tgt_n = node_by_id.get(edge.target_id)
                callee_names.add(tgt_n.name if tgt_n else edge.target_id)

    for scope_id, called_set in scope_calls.items():
        if scope_id in matched_ids:
            callee_names.update(called_set)
        elif called_set & matched_names:
            caller_ids.add(scope_id)

    callers_list: List[Dict[str, Any]] = []
    for cid in sorted(caller_ids):
        cn = node_by_id.get(cid)
        if cn:
            callers_list.append(
                {
                    "id": cn.id,
                    "name": cn.name,
                    "module_path": cn.module_path,
                    "line_start": cn.line_start,
                }
            )
        else:
            callers_list.append({"id": cid, "name": cid.split(":")[-1]})

    callees_list: List[Dict[str, Any]] = []
    for cname in sorted(callee_names):
        cdefs = [
            n
            for n in master_graph.nodes.values()
            if n.name == cname and n.symbol_type != SymbolType.IMPORT
        ]
        if cdefs:
            for cd in cdefs:
                callees_list.append(
                    {
                        "id": cd.id,
                        "name": cd.name,
                        "module_path": cd.module_path,
                        "line_start": cd.line_start,
                    }
                )
        else:
            callees_list.append({"id": cname, "name": cname})

    return {
        "symbol": target_sym,
        "found": len(definitions) > 0,
        "definitions": definitions,
        "callers": callers_list,
        "callees": callees_list,
    }

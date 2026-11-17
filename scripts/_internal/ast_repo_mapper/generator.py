"""Orchestratore della High-Density AST Repo-Map e collegamento cross-modulo."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from _internal.ast_repo_mapper.facade_resolver import (
    extract_python_module_symbols,
    internal_deps_still_valid,
)
from _internal.ast_repo_mapper.map_rendering import (
    compact_sig_for_ste100_impl,
    render_expanded_module_impl,
    render_inline_compact_module_impl,
    render_two_tier_map_impl,
)
from _internal.ast_repo_mapper.models import (
    CACHE_SCHEMA_VERSION,
    DEFAULT_EXCLUDED_DIRS,
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
from _internal.ast_repo_mapper.ranking_and_slicing import PersonalizedPageRank


def link_cross_module_edges_impl(graph: SymbolGraph) -> None:
    """Collega gli import ai simboli definiti in altri moduli del grafo."""
    name_to_defs: Dict[str, List[SymbolNode]] = {}
    module_stem_to_defs: Dict[str, List[SymbolNode]] = {}

    for node in graph.nodes.values():
        if node.symbol_type != SymbolType.IMPORT:
            name_to_defs.setdefault(node.name, []).append(node)
            stem = Path(node.module_path).stem
            module_stem_to_defs.setdefault(stem, []).append(node)

    for node in list(graph.nodes.values()):
        if node.symbol_type != SymbolType.IMPORT:
            continue
        target_candidates: List[SymbolNode] = []
        if node.name in name_to_defs:
            target_candidates.extend(name_to_defs[node.name])
        if node.name in module_stem_to_defs:
            target_candidates.extend(module_stem_to_defs[node.name])

        for target in target_candidates:
            if target.module_path != node.module_path:
                graph.add_edge(
                    SymbolEdge(
                        source_id=node.id,
                        target_id=target.id,
                        edge_type=EdgeType.IMPORT_USAGE,
                        weight=1.2,
                    )
                )


def link_cross_file_calls_impl(
    graph: SymbolGraph, scope_calls: Dict[str, Set[str]]
) -> None:
    """Collega nella Passata 2 gli archi CALL verso simboli definiti nel progetto."""
    if not scope_calls:
        return
    name_to_ids: Dict[str, List[str]] = {}
    for node in graph.nodes.values():
        if node.symbol_type not in (SymbolType.IMPORT, SymbolType.CSS_RULE):
            name_to_ids.setdefault(node.name, []).append(node.id)

    existing_calls: Set[Tuple[str, str]] = {
        (e.source_id, e.target_id)
        for e in graph.edges
        if e.edge_type == EdgeType.CALL
    }

    for src_id, called_names in scope_calls.items():
        if src_id not in graph.nodes:
            continue
        for cname in called_names:
            for tgt_id in name_to_ids.get(cname, ()):
                if tgt_id != src_id and (src_id, tgt_id) not in existing_calls:
                    existing_calls.add((src_id, tgt_id))
                    graph.add_edge(
                        SymbolEdge(
                            source_id=src_id,
                            target_id=tgt_id,
                            edge_type=EdgeType.CALL,
                            weight=1.5,
                        )
                    )


def generate_repo_map_impl(
    cls: type, root_dir: Path, config: Optional[RepoMapConfig] = None
) -> RepoMapResult:
    start_time = time.perf_counter()
    config = config or RepoMapConfig()
    cache_path = (
        Path(config.cache_dir)
        if config.cache_dir
        else AtomicCacheManager.get_default_cache_path(root_dir)
    )

    cached_payload = AtomicCacheManager.load_safe(cache_path) if config.cache_enabled else None
    cached_files = (
        (cached_payload or {}).get("files", {})
        if (cached_payload or {}).get("version") == CACHE_SCHEMA_VERSION
        else {}
    )

    file_map: Dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in cls.EXCLUDED_DIRS]
        dpath = Path(dirpath)
        for fname in filenames:
            p = dpath / fname
            if p.suffix.lower() in cls.SUPPORTED_EXTS:
                try:
                    rel_parts = p.relative_to(root_dir).parts
                except ValueError:
                    rel_parts = p.parts
                if any(part in cls.EXCLUDED_DIRS for part in rel_parts):
                    continue
                rel_key = str(p.relative_to(root_dir)).replace("\\", "/")
                file_map[rel_key] = p

    staging_root = root_dir / ".staging"
    if staging_root.is_dir():
        non_staging_excluded = cls.EXCLUDED_DIRS - {".staging"}
        for sub_name in ("scripts", "tests"):
            sub_dir = staging_root / sub_name
            if not sub_dir.is_dir():
                continue
            for p in sub_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in cls.SUPPORTED_EXTS:
                    rel_parts = p.relative_to(staging_root).parts
                    if any(part in non_staging_excluded for part in rel_parts):
                        continue
                    rel_key = str(p.relative_to(staging_root)).replace("\\", "/")
                    file_map[rel_key] = p

    master_graph = SymbolGraph()
    new_cached_files: Dict[str, Any] = {}
    all_scope_calls: Dict[str, Set[str]] = {}
    hits = 0

    for rel_str, file_path in sorted(file_map.items()):
        mtime = file_path.stat().st_mtime
        size = file_path.stat().st_size

        c_entry = cached_files.get(rel_str)
        if (
            c_entry
            and c_entry.get("mtime") == mtime
            and c_entry.get("size") == size
            and "edges" in c_entry
            and "scope_calls" in c_entry
            and internal_deps_still_valid(c_entry)
            and not (
                rel_str.startswith("scripts/")
                and rel_str.endswith("/__init__.py")
                and not any(
                    nd.get("symbol_type") != SymbolType.IMPORT.value
                    for nd in c_entry.get("nodes", [])
                )
            )
        ):
            for nd in c_entry.get("nodes", []):
                try:
                    master_graph.add_node(SymbolNode.model_validate(nd))
                except Exception:
                    pass
            for ed in c_entry.get("edges", []):
                try:
                    master_graph.add_edge(SymbolEdge.model_validate(ed))
                except Exception:
                    pass
            for sc_id, sc_list in c_entry.get("scope_calls", {}).items():
                all_scope_calls[sc_id] = set(sc_list)
            new_cached_files[rel_str] = c_entry
            hits += 1
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        file_nodes: List[SymbolNode] = []
        file_edges: List[SymbolEdge] = []
        file_scope_calls: Dict[str, List[str]] = {}
        internal_deps: List[List[Any]] = []
        if file_path.suffix.lower() == ".py":
            file_nodes, file_edges, raw_sc, internal_deps = extract_python_module_symbols(
                file_path=file_path,
                rel_str=rel_str,
                content=content,
                root_dir=root_dir,
            )
            if (
                rel_str.startswith("scripts/")
                and rel_str.endswith("/__init__.py")
                and not any(n.symbol_type != SymbolType.IMPORT for n in file_nodes)
            ):
                file_nodes.append(
                    SymbolNode(
                        id=f"{rel_str}:init",
                        name="init",
                        symbol_type=SymbolType.CONSTANT,
                        module_path=rel_str,
                        line_start=1,
                        line_end=1,
                        signature="init",
                    )
                )
            for node in file_nodes:
                master_graph.add_node(node)
            for edge in file_edges:
                master_graph.add_edge(edge)
            for sc_id, sc_vals in raw_sc.items():
                all_scope_calls[sc_id] = set(sc_vals)
                file_scope_calls[sc_id] = sorted(sc_vals)
        elif config.polyglot:
            p_nodes = PolyglotExtractor.extract_symbols(rel_str, content)
            p_edges, p_calls = PolyglotExtractor.extract_call_edges(
                rel_str, content, p_nodes
            )
            for node in p_nodes:
                master_graph.add_node(node)
                file_nodes.append(node)
            for edge in p_edges:
                master_graph.add_edge(edge)
                file_edges.append(edge)
            for sc_id, sc_vals in p_calls.items():
                all_scope_calls[sc_id] = set(sc_vals)
                file_scope_calls[sc_id] = sorted(sc_vals)

        new_cached_files[rel_str] = {
            "abs_path": str(file_path),
            "mtime": mtime,
            "size": size,
            "internal_deps": internal_deps,
            "nodes": [n.model_dump() for n in file_nodes],
            "edges": [e.model_dump() for e in file_edges],
            "scope_calls": file_scope_calls,
        }

    cls._link_cross_module_edges(master_graph)
    cls._link_cross_file_calls(master_graph, all_scope_calls)

    if config.cache_enabled:
        AtomicCacheManager.save_atomic(
            {"version": CACHE_SCHEMA_VERSION, "files": new_cached_files}, cache_path
        )

    focal_ids: Set[str] = set()
    clean_focals = [f.replace("\\", "/") for f in config.focal_files]
    for fid in master_graph.nodes:
        if any(cf in fid for cf in clean_focals):
            focal_ids.add(fid)

    pr_result = PersonalizedPageRank.compute(master_graph, target_symbol_ids=focal_ids)

    formatted_map, final_tokens = cls._render_two_tier_map(
        root_dir=root_dir,
        graph=master_graph,
        pr_scores=pr_result.scores,
        focal_ids=focal_ids,
        max_tokens=config.max_tokens,
    )

    elapsed = round((time.perf_counter() - start_time) * 1000, 2)
    return RepoMapResult(
        content=formatted_map,
        token_count=final_tokens,
        files_scanned=len(file_map),
        cached_hits=hits,
        elapsed_ms=elapsed,
        focal_files=config.focal_files,
    )


class RepoMapGenerator:
    """
    Genera la High-Density AST Repo-Map.
    Coordina il parsing incrementale, PageRank con archi cross-modulo e clustering.
    """

    SUPPORTED_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".html"}
    EXCLUDED_DIRS = set(DEFAULT_EXCLUDED_DIRS)

    @classmethod
    def build_map(cls, root_dir: Path, config: Optional[RepoMapConfig] = None) -> RepoMapResult:
        """Costruisce la mappa normalizzando i percorsi in formato POSIX."""
        return cls.generate(root_dir=root_dir, config=config)

    @classmethod
    def generate(cls, root_dir: Path, config: Optional[RepoMapConfig] = None) -> RepoMapResult:
        return generate_repo_map_impl(cls, root_dir=root_dir, config=config)

    @classmethod
    def _link_cross_module_edges(cls, graph: SymbolGraph) -> None:
        """Collega gli import ai simboli definiti in altri moduli del grafo."""
        link_cross_module_edges_impl(graph)

    @classmethod
    def _link_cross_file_calls(
        cls, graph: SymbolGraph, scope_calls: Dict[str, Set[str]]
    ) -> None:
        """Collega nella Passata 2 gli archi CALL verso simboli definiti nel progetto."""
        link_cross_file_calls_impl(graph, scope_calls)

    @classmethod
    def _compact_sig_for_ste100(cls, sig: str, max_words: int = 16) -> str:
        """Garantisce che ogni firma renderizzata rispetti il limite di 20 parole STE100."""
        return compact_sig_for_ste100_impl(sig, max_words=max_words)

    @classmethod
    def _render_expanded_module(cls, mod: str, syms: List[SymbolNode]) -> str:
        return render_expanded_module_impl(mod, syms)

    @classmethod
    def _render_inline_compact_module(cls, mod: str, syms: List[SymbolNode]) -> str:
        return render_inline_compact_module_impl(mod, syms)

    @classmethod
    def _render_two_tier_map(
        cls,
        root_dir: Path,
        graph: SymbolGraph,
        pr_scores: Dict[str, float],
        focal_ids: Set[str],
        max_tokens: int,
    ) -> Tuple[str, int]:
        """
        Formatta la mappa ad alta densita con compattazione elastica a tre livelli.
        Garantisce un margine di sicurezza <= 82% di max_tokens.
        """
        return render_two_tier_map_impl(root_dir, graph, pr_scores, focal_ids, max_tokens)

"""Personalized PageRank e KarpathySurgicalSlicer per contesto AST."""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from _internal.ast_repo_mapper.models import (
    PageRankResult,
    SliceResult,
    SymbolGraph,
    SymbolNode,
    SymbolType,
    estimate_tokens,
)
from _internal.ast_repo_mapper.parser_resilient import ResilientParser
from _internal.ast_repo_mapper.symbol_extractor import SymbolExtractor


class PersonalizedPageRank:
    """
    Calcola Personalized PageRank su un SymbolGraph con fattore di smorzamento d=0.85.
    Concentra il vettore di teletrasporto sui simboli focali target.
    """

    @classmethod
    def compute(
        cls,
        graph: SymbolGraph,
        target_symbol_ids: Optional[Set[str]] = None,
        damping: float = 0.85,
        max_iter: int = 100,
        epsilon: float = 1e-6,
    ) -> PageRankResult:
        nodes = list(graph.nodes.keys())
        n = len(nodes)
        if n == 0:
            return PageRankResult(scores={}, ranked_symbols=[], iterations=0, converged=True)

        node_index = {node_id: idx for idx, node_id in enumerate(nodes)}

        v = [0.0] * n
        valid_targets = [tid for tid in (target_symbol_ids or set()) if tid in node_index]
        if valid_targets:
            teleport_prob = 1.0 / len(valid_targets)
            for tid in valid_targets:
                v[node_index[tid]] = teleport_prob
        else:
            uniform_prob = 1.0 / n
            v = [uniform_prob] * n

        out_weights = [0.0] * n
        for src_id, edges in graph.adjacency_out.items():
            if src_id in node_index:
                src_idx = node_index[src_id]
                out_weights[src_idx] = sum(w for _, w in edges)

        p = list(v)
        converged = False
        iteration = 0

        for iteration in range(1, max_iter + 1):
            p_next = [0.0] * n
            dangling_sum = 0.0

            for i in range(n):
                node_id = nodes[i]
                if out_weights[i] > 0.0:
                    for target_id, weight in graph.adjacency_out.get(node_id, []):
                        if target_id in node_index:
                            t_idx = node_index[target_id]
                            p_next[t_idx] += damping * p[i] * (weight / out_weights[i])
                else:
                    dangling_sum += p[i]

            teleport_contrib = (1.0 - damping) + damping * dangling_sum
            for i in range(n):
                p_next[i] += teleport_contrib * v[i]

            diff = sum(abs(p_next[i] - p[i]) for i in range(n))
            p = p_next
            if diff < epsilon:
                converged = True
                break

        total_p = sum(p)
        if total_p > 0.0:
            p = [x / total_p for x in p]

        scores = {nodes[i]: p[i] for i in range(n)}
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)

        return PageRankResult(
            scores=scores,
            ranked_symbols=ranked,
            iterations=iteration,
            converged=converged,
        )


class KarpathySurgicalSlicer:
    """
    Esegue lo slicing chirurgico Karpathy con ricerca binaria semantica.
    Preserva tutti i simboli focali per intero e rispetta il limite max_tokens.
    """

    TOKEN_BUDGET: int = 780

    @classmethod
    def slice_module(
        cls,
        source_code: str,
        focal_symbol_names: List[str],
        module_path: str = "module.py",
        max_tokens: int = TOKEN_BUDGET,
    ) -> SliceResult:
        source_lines = source_code.splitlines(keepends=True)
        tree, _ = ResilientParser.parse_safe(source_code, filename=module_path)

        extractor = SymbolExtractor(module_path=module_path, source_lines=source_lines)
        if tree:
            extractor.visit(tree)
        graph = extractor.graph

        focal_ids: Set[str] = set()
        for focal_name in focal_symbol_names:
            if focal_name in extractor.symbol_name_to_ids:
                focal_ids.update(extractor.symbol_name_to_ids[focal_name])
            elif focal_name in graph.nodes:
                focal_ids.add(focal_name)
            else:
                for sid in graph.nodes:
                    if focal_name in sid:
                        focal_ids.add(sid)

        pr_result = PersonalizedPageRank.compute(graph, target_symbol_ids=focal_ids)

        non_focal_ranked = [
            (sid, score) for sid, score in pr_result.ranked_symbols
            if sid not in focal_ids and graph.nodes[sid].symbol_type != SymbolType.IMPORT
        ]

        best_slice: Optional[str] = None
        best_tokens = 0
        best_collapsed: List[str] = []
        best_omitted: List[str] = []

        for include_docs in (True, False):
            low = 0
            high = len(non_focal_ranked)
            while low <= high:
                mid = (low + high) // 2
                retained_non_focal = {sid for sid, _ in non_focal_ranked[:mid]}
                retained_set = focal_ids | retained_non_focal

                candidate_text, collapsed, omitted = cls._render_slice_nodes(
                    source_lines=source_lines,
                    graph=graph,
                    focal_ids=focal_ids,
                    retained_ids=retained_set,
                    include_docs=include_docs,
                )
                t_count = estimate_tokens(candidate_text)

                if t_count < max_tokens:
                    if best_slice is None or t_count > best_tokens or (mid > 0 and not best_collapsed):
                        best_slice = candidate_text
                        best_tokens = t_count
                        best_collapsed = collapsed
                        best_omitted = omitted
                    low = mid + 1
                else:
                    high = mid - 1

            if best_slice is not None and best_tokens < max_tokens:
                break

        if best_slice is None:
            best_slice, best_collapsed, best_omitted = cls._multi_focal_compress(
                graph=graph,
                focal_ids=focal_ids,
                max_tokens=max_tokens,
            )
            best_tokens = estimate_tokens(best_slice)

        orig_len = max(len(source_code), 1)
        ratio = round(len(best_slice) / orig_len, 4)

        return SliceResult(
            sliced_code=best_slice,
            token_count=best_tokens,
            focal_symbols=list(focal_ids),
            collapsed_symbols=best_collapsed,
            omitted_symbols=best_omitted,
            compression_ratio=ratio,
        )

    @classmethod
    def _multi_focal_compress(
        cls,
        graph: SymbolGraph,
        focal_ids: Set[str],
        max_tokens: int,
    ) -> Tuple[str, List[str], List[str]]:
        """Preserva le firme di tutti i simboli focali senza troncare la sintassi."""
        rendered_parts: List[str] = []
        collapsed: List[str] = []
        omitted: List[str] = []

        for fid in sorted(focal_ids):
            node = graph.nodes.get(fid)
            if node:
                sig = node.signature or f"def {node.name}(): ..."
                rendered_parts.append(f"{sig}\n    ...")
                collapsed.append(fid)

        text = "\n\n".join(rendered_parts) + "\n"
        if estimate_tokens(text) > max_tokens:
            names = [f"# {graph.nodes[f].name}" for f in focal_ids if f in graph.nodes]
            text = "\n".join(names[:10]) + "\n"

        return text, collapsed, omitted

    @classmethod
    def _render_slice_nodes(
        cls,
        source_lines: List[str],
        graph: SymbolGraph,
        focal_ids: Set[str],
        retained_ids: Set[str],
        include_docs: bool,
    ) -> Tuple[str, List[str], List[str]]:
        collapsed: List[str] = []
        omitted: List[str] = []

        header_lines: List[str] = []
        rendered_blocks: List[str] = []

        for _, node in graph.nodes.items():
            if node.symbol_type == SymbolType.IMPORT:
                if node.raw_source:
                    header_lines.append(node.raw_source.rstrip())

        if header_lines:
            rendered_blocks.append("\n".join(sorted(set(header_lines))))

        top_level_nodes = [
            n for n in graph.nodes.values()
            if n.parent_id is None and n.symbol_type not in (SymbolType.IMPORT, SymbolType.MODULE)
        ]
        top_level_nodes.sort(key=lambda n: n.line_start)

        for t_node in top_level_nodes:
            is_focal = t_node.id in focal_ids
            children = [n for n in graph.nodes.values() if n.parent_id == t_node.id]
            has_focal_child = any(c.id in focal_ids for c in children)
            has_retained_child = any(c.id in retained_ids for c in children)

            if is_focal and not children:
                raw = t_node.raw_source or ""
                rendered_blocks.append(raw.rstrip())
            elif is_focal and children:
                skeleton = cls._render_node_skeleton(
                    t_node, graph, focal_ids, retained_ids, include_docs, collapsed, omitted
                )
                if skeleton:
                    rendered_blocks.append(skeleton)
            elif t_node.id in retained_ids or has_focal_child or has_retained_child:
                skeleton = cls._render_node_skeleton(
                    t_node, graph, focal_ids, retained_ids, include_docs, collapsed, omitted
                )
                if skeleton:
                    rendered_blocks.append(skeleton)
            else:
                omitted.append(t_node.id)

        slice_output = "\n\n".join(rendered_blocks) + "\n"
        return slice_output, collapsed, omitted

    @classmethod
    def _render_node_skeleton(
        cls,
        node: SymbolNode,
        graph: SymbolGraph,
        focal_ids: Set[str],
        retained_ids: Set[str],
        include_docs: bool,
        collapsed_acc: List[str],
        omitted_acc: List[str],
    ) -> str:
        if node.symbol_type == SymbolType.CLASS:
            lines: List[str] = [node.signature or f"class {node.name}:"]
            if include_docs and node.docstring:
                lines.append(f'    """{node.docstring.strip()}"""')

            children = [n for n in graph.nodes.values() if n.parent_id == node.id]
            children.sort(key=lambda n: n.line_start)

            if not children:
                lines.append("    ...")
            else:
                for child in children:
                    if child.id in focal_ids:
                        child_src = child.raw_source or f"def {child.name}(): ..."
                        indented = "\n".join("    " + l if l.strip() else "" for l in child_src.splitlines())
                        lines.append(indented)
                    elif child.id in retained_ids:
                        collapsed_acc.append(child.id)
                        child_sig = child.signature or f"def {child.name}():"
                        lines.append(f"    {child_sig}")
                        if include_docs and child.docstring:
                            lines.append(f'        """{child.docstring.strip()}"""')
                        lines.append("        ...")
                    else:
                        omitted_acc.append(child.id)
            return "\n".join(lines)

        elif node.symbol_type in (SymbolType.FUNCTION, SymbolType.ASYNC_FUNCTION):
            collapsed_acc.append(node.id)
            lines = [node.signature or f"def {node.name}():"]
            if include_docs and node.docstring:
                lines.append(f'    """{node.docstring.strip()}"""')
            lines.append("    ...")
            return "\n".join(lines)

        elif node.symbol_type == SymbolType.CONSTANT:
            return node.signature or f"{node.name} = ..."

        return ""

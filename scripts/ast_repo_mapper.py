"""
Nexus Keystone v1.1.0-Universal - Compiler, Code Intelligence & Slicing
Module: ast_repo_mapper.py
Author: NK-Python-Async-Builder (Node 3)

Features:
- Symbol Graph Generator (classes, methods, functions, constants, imports, type references, call graph).
- Personalized PageRank (damping factor d=0.85) with teleport vector on target symbols/files.
- Karpathy Surgical Slicer with Semantic Binary Search (< 800 tokens hard ceiling).
- Resilient CST / AST Parser tolerant to intermediate syntax and indentation errors.
"""

from __future__ import annotations

import ast
import math
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# PYDANTIC V2 STRICT DATA MODELS
# ============================================================================

class SymbolType(str, Enum):
    MODULE = "MODULE"
    CLASS = "CLASS"
    METHOD = "METHOD"
    FUNCTION = "FUNCTION"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    CONSTANT = "CONSTANT"
    IMPORT = "IMPORT"
    TYPE_ALIAS = "TYPE_ALIAS"


class EdgeType(str, Enum):
    CALL = "CALL"
    INHERITANCE = "INHERITANCE"
    TYPE_REFERENCE = "TYPE_REFERENCE"
    IMPORT_USAGE = "IMPORT_USAGE"
    CONTAINMENT = "CONTAINMENT"
    ATTRIBUTE_ACCESS = "ATTRIBUTE_ACCESS"


class SymbolNode(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    id: str = Field(description="Unique fully qualified symbol identifier, e.g. module:ClassName.method")
    name: str = Field(description="Short symbol name")
    symbol_type: SymbolType = Field(description="Type of code symbol")
    module_path: str = Field(description="File or module relative path")
    parent_id: Optional[str] = Field(default=None, description="Parent container ID if method or nested")
    line_start: int = Field(ge=1, description="1-indexed starting line")
    line_end: int = Field(ge=1, description="1-indexed ending line")
    signature: Optional[str] = Field(default=None, description="Full signature representation")
    docstring: Optional[str] = Field(default=None, description="Extracted docstring")
    return_type: Optional[str] = Field(default=None, description="Return type annotation as string")
    is_async: bool = Field(default=False, description="Whether the function is async")
    raw_source: Optional[str] = Field(default=None, description="Original source snippet for symbol")


class SymbolEdge(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    source_id: str = Field(description="Source symbol ID")
    target_id: str = Field(description="Target symbol ID")
    edge_type: EdgeType = Field(description="Relationship category")
    weight: float = Field(default=1.0, ge=0.0, description="Edge weight for PageRank transition")


class SymbolGraph(BaseModel):
    model_config = ConfigDict(strict=True)

    nodes: Dict[str, SymbolNode] = Field(default_factory=dict, description="Lookup map of nodes by ID")
    edges: List[SymbolEdge] = Field(default_factory=list, description="Directed edges between symbols")
    adjacency_out: Dict[str, List[Tuple[str, float]]] = Field(
        default_factory=dict, description="Outgoing adjacency list: source -> list of (target, weight)"
    )
    adjacency_in: Dict[str, List[Tuple[str, float]]] = Field(
        default_factory=dict, description="Incoming adjacency list: target -> list of (source, weight)"
    )

    def add_node(self, node: SymbolNode) -> None:
        self.nodes[node.id] = node
        if node.id not in self.adjacency_out:
            self.adjacency_out[node.id] = []
        if node.id not in self.adjacency_in:
            self.adjacency_in[node.id] = []

    def add_edge(self, edge: SymbolEdge) -> None:
        self.edges.append(edge)
        if edge.source_id not in self.adjacency_out:
            self.adjacency_out[edge.source_id] = []
        if edge.target_id not in self.adjacency_in:
            self.adjacency_in[edge.target_id] = []
        self.adjacency_out[edge.source_id].append((edge.target_id, edge.weight))
        self.adjacency_in[edge.target_id].append((edge.source_id, edge.weight))

    def get_node(self, node_id: str) -> Optional[SymbolNode]:
        return self.nodes.get(node_id)


class PageRankResult(BaseModel):
    model_config = ConfigDict(strict=True)

    scores: Dict[str, float] = Field(description="Symbol ID to PageRank score mapping")
    ranked_symbols: List[Tuple[str, float]] = Field(description="Sorted list of (symbol_id, score) descending")
    iterations: int = Field(description="Number of power iterations to convergence")
    converged: bool = Field(description="Whether power iteration converged under epsilon")


class SliceResult(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    sliced_code: str = Field(description="Surgically sliced source code text")
    token_count: int = Field(description="Estimated token count strictly < 800")
    focal_symbols: List[str] = Field(description="List of focal symbol IDs preserved in full")
    collapsed_symbols: List[str] = Field(description="List of symbols collapsed into skeleton signatures")
    omitted_symbols: List[str] = Field(description="List of low-relevance symbols omitted")
    compression_ratio: float = Field(description="Ratio of sliced chars to original chars")


# ============================================================================
# RESILIENT CST / AST PARSER
# ============================================================================

class ResilientParser:
    """
    Parser resilient to intermediate syntax and indentation errors.
    If standard ast.parse fails, it applies block-level isolation and regex fallback
    to extract symbols without halting execution.
    """

    @classmethod
    def parse_safe(cls, source: str, filename: str = "<string>") -> Tuple[Optional[ast.AST], List[str]]:
        warnings: List[str] = []
        try:
            tree = ast.parse(source, filename=filename)
            return tree, warnings
        except SyntaxError as se:
            warnings.append(f"SyntaxError on line {se.lineno}, col {se.offset}: {se.msg}")

        sanitized_tree = cls._recover_ast_chunks(source, filename, warnings)
        return sanitized_tree, warnings

    @classmethod
    def _recover_ast_chunks(cls, source: str, filename: str, warnings: List[str]) -> Optional[ast.AST]:
        lines = source.splitlines(keepends=True)
        if not lines:
            return ast.parse("")

        block_ranges: List[Tuple[int, int]] = []
        start_idx = 0
        for i in range(1, len(lines)):
            line = lines[i]
            if line and not line[0].isspace() and not line.strip().startswith("#"):
                block_ranges.append((start_idx, i))
                start_idx = i
        block_ranges.append((start_idx, len(lines)))

        valid_nodes: List[ast.stmt] = []
        for b_start, b_end in block_ranges:
            block_code = "".join(lines[b_start:b_end])
            try:
                sub_tree = ast.parse(block_code, filename=filename)
                for node in sub_tree.body:
                    cls._offset_linenos(node, b_start)
                    valid_nodes.append(node)
            except SyntaxError as block_se:
                warnings.append(
                    f"Recovering malformed block at lines {b_start+1}-{b_end}: {block_se.msg}"
                )
                stub_nodes = cls._extract_stubs_from_broken_block(block_code, b_start)
                valid_nodes.extend(stub_nodes)

        mod = ast.Module(body=valid_nodes, type_ignores=[])
        return mod

    @classmethod
    def _offset_linenos(cls, node: ast.AST, offset: int) -> None:
        for child in ast.walk(node):
            if hasattr(child, "lineno"):
                child.lineno += offset  # type: ignore[misc]
            if hasattr(child, "end_lineno") and child.end_lineno is not None:
                child.end_lineno += offset  # type: ignore[misc]

    @classmethod
    def _extract_stubs_from_broken_block(cls, block_code: str, line_offset: int) -> List[ast.stmt]:
        stubs: List[ast.stmt] = []
        lines = block_code.splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            fn_match = re.match(r"^(async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)(\s*->.*?)?:", stripped)
            if fn_match:
                is_async = bool(fn_match.group(1))
                fn_name = fn_match.group(2)
                cur_line = line_offset + idx + 1
                try:
                    stub_src = f"{'async ' if is_async else ''}def {fn_name}(): pass"
                    stub_tree = ast.parse(stub_src)
                    fn_node = stub_tree.body[0]
                    fn_node.lineno = cur_line
                    fn_node.end_lineno = cur_line + 1
                    stubs.append(fn_node)
                except Exception:
                    pass
                continue

            cls_match = re.match(r"^class\s+([a-zA-Z_][a-zA-Z0-9_]*)(\(.*?\))?:", stripped)
            if cls_match:
                cls_name = cls_match.group(1)
                cur_line = line_offset + idx + 1
                try:
                    stub_src = f"class {cls_name}: pass"
                    stub_tree = ast.parse(stub_src)
                    c_node = stub_tree.body[0]
                    c_node.lineno = cur_line
                    c_node.end_lineno = cur_line + 1
                    stubs.append(c_node)
                except Exception:
                    pass
        return stubs


# ============================================================================
# SYMBOL GRAPH GENERATOR
# ============================================================================

class SymbolExtractor(ast.NodeVisitor):
    """
    Extracts structured symbols and dependency relationships from AST.
    """

    def __init__(self, module_path: str, source_lines: List[str]):
        self.module_path = module_path
        self.source_lines = source_lines
        self.graph = SymbolGraph()
        self.current_class_id: Optional[str] = None
        self.current_scope_id: Optional[str] = None
        self.symbol_name_to_ids: Dict[str, Set[str]] = {}

    def _register_name_mapping(self, name: str, symbol_id: str) -> None:
        if name not in self.symbol_name_to_ids:
            self.symbol_name_to_ids[name] = set()
        self.symbol_name_to_ids[name].add(symbol_id)

    def _get_raw_source(self, start_line: int, end_line: int) -> str:
        s = max(0, start_line - 1)
        e = min(len(self.source_lines), end_line)
        return "".join(self.source_lines[s:e])

    def _format_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        prefix = "async def " if is_async else "def "
        args_str = self._format_arguments(node.args)
        ret_ann = ""
        if node.returns:
            try:
                ret_ann = f" -> {ast.unparse(node.returns)}"
            except Exception:
                ret_ann = ""
        return f"{prefix}{node.name}({args_str}){ret_ann}"

    def _format_arguments(self, args: ast.arguments) -> str:
        parts: List[str] = []
        posonly = getattr(args, "posonlyargs", [])
        for arg in posonly:
            ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            parts.append(f"{arg.arg}{ann}")
        if posonly:
            parts.append("/")

        num_defaults = len(args.defaults)
        offset = len(args.args) - num_defaults
        for i, arg in enumerate(args.args):
            ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            default_idx = i - offset
            if default_idx >= 0 and default_idx < len(args.defaults):
                try:
                    def_val = ast.unparse(args.defaults[default_idx])
                    parts.append(f"{arg.arg}{ann}={def_val}")
                except Exception:
                    parts.append(f"{arg.arg}{ann}=...")
            else:
                parts.append(f"{arg.arg}{ann}")

        if args.vararg:
            ann = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
            parts.append(f"*{args.vararg.arg}{ann}")
        elif args.kwonlyargs:
            parts.append("*")

        for i, arg in enumerate(args.kwonlyargs):
            ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            kw_def = args.kw_defaults[i]
            if kw_def is not None:
                try:
                    def_val = ast.unparse(kw_def)
                    parts.append(f"{arg.arg}{ann}={def_val}")
                except Exception:
                    parts.append(f"{arg.arg}{ann}=...")
            else:
                parts.append(f"{arg.arg}{ann}")

        if args.kwarg:
            ann = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
            parts.append(f"**{args.kwarg.arg}{ann}")

        return ", ".join(parts)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            sym_id = f"{self.module_path}:import_{alias.name}"
            sym_node = SymbolNode(
                id=sym_id,
                name=alias.name,
                symbol_type=SymbolType.IMPORT,
                module_path=self.module_path,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                signature=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                raw_source=self._get_raw_source(node.lineno, getattr(node, "end_lineno", node.lineno)),
            )
            self.graph.add_node(sym_node)
            self._register_name_mapping(alias.asname or alias.name, sym_id)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for alias in node.names:
            sym_id = f"{self.module_path}:import_{mod}.{alias.name}"
            sym_node = SymbolNode(
                id=sym_id,
                name=alias.name,
                symbol_type=SymbolType.IMPORT,
                module_path=self.module_path,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                signature=f"from {mod} import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                raw_source=self._get_raw_source(node.lineno, getattr(node, "end_lineno", node.lineno)),
            )
            self.graph.add_node(sym_node)
            self._register_name_mapping(alias.asname or alias.name, sym_id)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.current_scope_id is None or self.current_scope_id == self.current_class_id:
            for target in node.targets:
                if isinstance(target, ast.Name) and (target.id.isupper() or self.current_class_id is None):
                    sym_id = (
                        f"{self.current_class_id}.{target.id}"
                        if self.current_class_id
                        else f"{self.module_path}:{target.id}"
                    )
                    sym_node = SymbolNode(
                        id=sym_id,
                        name=target.id,
                        symbol_type=SymbolType.CONSTANT,
                        module_path=self.module_path,
                        parent_id=self.current_class_id,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=f"{target.id} = ...",
                        raw_source=self._get_raw_source(node.lineno, getattr(node, "end_lineno", node.lineno)),
                    )
                    self.graph.add_node(sym_node)
                    self._register_name_mapping(target.id, sym_id)
                    if self.current_class_id:
                        self.graph.add_edge(
                            SymbolEdge(
                                source_id=self.current_class_id,
                                target_id=sym_id,
                                edge_type=EdgeType.CONTAINMENT,
                                weight=1.0,
                            )
                        )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_id = f"{self.module_path}:{node.name}"
        doc = ast.get_docstring(node)
        bases_str = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
        sig = f"class {node.name}({bases_str}):" if bases_str else f"class {node.name}:"

        sym_node = SymbolNode(
            id=class_id,
            name=node.name,
            symbol_type=SymbolType.CLASS,
            module_path=self.module_path,
            parent_id=self.current_class_id,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            signature=sig,
            docstring=doc,
            raw_source=self._get_raw_source(node.lineno, getattr(node, "end_lineno", node.lineno)),
        )
        self.graph.add_node(sym_node)
        self._register_name_mapping(node.name, class_id)

        for base in node.bases:
            base_name = ast.unparse(base)
            if base_name in self.symbol_name_to_ids:
                for target_id in self.symbol_name_to_ids[base_name]:
                    self.graph.add_edge(
                        SymbolEdge(
                            source_id=class_id,
                            target_id=target_id,
                            edge_type=EdgeType.INHERITANCE,
                            weight=2.0,
                        )
                    )

        prev_class = self.current_class_id
        prev_scope = self.current_scope_id
        self.current_class_id = class_id
        self.current_scope_id = class_id

        self.generic_visit(node)

        self.current_class_id = prev_class
        self.current_scope_id = prev_scope

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_function(node, is_async=True)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        if self.current_class_id:
            fn_id = f"{self.current_class_id}.{node.name}"
            sym_type = SymbolType.METHOD
        else:
            fn_id = f"{self.module_path}:{node.name}"
            sym_type = SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION

        doc = ast.get_docstring(node)
        sig = self._format_signature(node)
        ret_type = ast.unparse(node.returns) if node.returns else None

        sym_node = SymbolNode(
            id=fn_id,
            name=node.name,
            symbol_type=sym_type,
            module_path=self.module_path,
            parent_id=self.current_class_id,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            signature=sig,
            docstring=doc,
            return_type=ret_type,
            is_async=is_async,
            raw_source=self._get_raw_source(node.lineno, getattr(node, "end_lineno", node.lineno)),
        )
        self.graph.add_node(sym_node)
        self._register_name_mapping(node.name, fn_id)

        if self.current_class_id:
            self.graph.add_edge(
                SymbolEdge(
                    source_id=self.current_class_id,
                    target_id=fn_id,
                    edge_type=EdgeType.CONTAINMENT,
                    weight=1.5,
                )
            )

        for arg in node.args.args + getattr(node.args, "posonlyargs", []) + node.args.kwonlyargs:
            if arg.annotation:
                ann_str = ast.unparse(arg.annotation)
                self._link_type_references(fn_id, ann_str)
        if node.returns:
            self._link_type_references(fn_id, ast.unparse(node.returns))

        prev_scope = self.current_scope_id
        self.current_scope_id = fn_id

        self.generic_visit(node)

        self.current_scope_id = prev_scope

    def _link_type_references(self, source_id: str, type_str: str) -> None:
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", type_str)
        for token_name in tokens:
            if token_name in self.symbol_name_to_ids:
                for target_id in self.symbol_name_to_ids[token_name]:
                    if target_id != source_id:
                        self.graph.add_edge(
                            SymbolEdge(
                                source_id=source_id,
                                target_id=target_id,
                                edge_type=EdgeType.TYPE_REFERENCE,
                                weight=1.0,
                            )
                        )

    def visit_Call(self, node: ast.Call) -> None:
        if self.current_scope_id:
            callee_name: Optional[str] = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name and callee_name in self.symbol_name_to_ids:
                for target_id in self.symbol_name_to_ids[callee_name]:
                    if target_id != self.current_scope_id:
                        self.graph.add_edge(
                            SymbolEdge(
                                source_id=self.current_scope_id,
                                target_id=target_id,
                                edge_type=EdgeType.CALL,
                                weight=1.5,
                            )
                        )
        self.generic_visit(node)


# ============================================================================
# PERSONALIZED PAGERANK ALGORITHM (d = 0.85)
# ============================================================================

class PersonalizedPageRank:
    """
    Computes Personalized PageRank on a SymbolGraph with damping factor d=0.85
    and teleport vector concentrated on target focal symbols.
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


# ============================================================================
# TOKEN ESTIMATOR & KARPATHY SURGICAL SLICER (< 800 TOKENS)
# ============================================================================

def estimate_tokens(text: str) -> int:
    """
    Deterministic Token Estimator compatible with BPE (GPT-4 / Claude / TikToken).
    Combines word/punctuation fragmentation with byte-length safeguards.
    """
    if not text:
        return 0
    pattern = re.compile(r"\w+|[^\w\s]", re.UNICODE)
    tokens = pattern.findall(text)
    char_estimate = int(math.ceil(len(text) / 3.5))
    return max(len(tokens), char_estimate)


class KarpathySurgicalSlicer:
    """
    Karpathy Surgical Slicer with Semantic Binary Search.
    Extracts the outline of the target module, preserves focal symbols in full,
    collapses non-focal bodies to '...', and strictly respects a hard limit of < 800 tokens.
    """

    TOKEN_BUDGET: int = 780  # Hard safety ceiling below 800 tokens

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

        # Compute PageRank focused on focal symbols
        pr_result = PersonalizedPageRank.compute(graph, target_symbol_ids=focal_ids)

        # Ranked list of non-focal symbols
        non_focal_ranked = [
            (sid, score) for sid, score in pr_result.ranked_symbols
            if sid not in focal_ids and graph.nodes[sid].symbol_type != SymbolType.IMPORT
        ]

        # Semantic Binary Search over retained top-K non-focal symbol skeletons
        # We test candidate levels: first with docstrings, then without docstrings
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
                # If we successfully found a fitting slice with skeletons, use it
                break

        # Emergency Fallback if even focal alone exceeds budget: compress focal body lines
        if best_slice is None:
            best_slice, best_collapsed, best_omitted = cls._emergency_focal_compress(
                source_lines=source_lines,
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

        for sym_id, node in graph.nodes.items():
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
            # Check if any children are focal or retained
            children = [n for n in graph.nodes.values() if n.parent_id == t_node.id]
            has_focal_child = any(c.id in focal_ids for c in children)
            has_retained_child = any(c.id in retained_ids for c in children)

            if is_focal and not children:
                raw = t_node.raw_source or ""
                rendered_blocks.append(raw.rstrip())
            elif is_focal and children:
                # Class itself is focal: if children are focal/retained, render skeleton or full
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

    @classmethod
    def _emergency_focal_compress(
        cls,
        source_lines: List[str],
        graph: SymbolGraph,
        focal_ids: Set[str],
        max_tokens: int,
    ) -> Tuple[str, List[str], List[str]]:
        focal_nodes = [graph.nodes[fid] for fid in focal_ids if fid in graph.nodes]
        if not focal_nodes:
            return ("# Sliced Context (Empty focal selection)\n", [], [])

        focal_node = focal_nodes[0]
        raw_lines = (focal_node.raw_source or "").splitlines()
        
        low = 1
        high = len(raw_lines)
        best_text = f"# Focal symbol: {focal_node.name}\n..."

        while low <= high:
            mid = (low + high) // 2
            candidate = "\n".join(raw_lines[:mid]) + "\n    # ... [truncated to fit token budget] ...\n"
            if estimate_tokens(candidate) < max_tokens:
                best_text = candidate
                low = mid + 1
            else:
                high = mid - 1

        return best_text, [], list(graph.nodes.keys())


# ============================================================================
# CONVENIENCE REPO SCANNER
# ============================================================================

def build_repo_symbol_graph(file_paths: List[str]) -> SymbolGraph:
    """
    Builds a unified SymbolGraph across multiple Python files.
    """
    master_graph = SymbolGraph()
    all_extractors: List[SymbolExtractor] = []

    for path_str in file_paths:
        p = Path(path_str)
        if not p.exists() or p.suffix != ".py":
            continue
        try:
            source = p.read_text(encoding="utf-8", errors="replace")
            source_lines = source.splitlines(keepends=True)
            tree, _ = ResilientParser.parse_safe(source, filename=path_str)
            extractor = SymbolExtractor(module_path=path_str, source_lines=source_lines)
            if tree:
                extractor.visit(tree)
            all_extractors.append(extractor)
            for node in extractor.graph.nodes.values():
                master_graph.add_node(node)
            for edge in extractor.graph.edges:
                master_graph.add_edge(edge)
        except Exception:
            continue

    global_symbol_lookup: Dict[str, Set[str]] = {}
    for ext in all_extractors:
        for name, ids in ext.symbol_name_to_ids.items():
            if name not in global_symbol_lookup:
                global_symbol_lookup[name] = set()
            global_symbol_lookup[name].update(ids)

    for node in list(master_graph.nodes.values()):
        if node.symbol_type == SymbolType.IMPORT:
            if node.name in global_symbol_lookup:
                for target_id in global_symbol_lookup[node.name]:
                    if target_id != node.id:
                        master_graph.add_edge(
                            SymbolEdge(
                                source_id=node.id,
                                target_id=target_id,
                                edge_type=EdgeType.IMPORT_USAGE,
                                weight=1.2,
                            )
                        )

    return master_graph

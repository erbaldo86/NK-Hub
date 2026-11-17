"""Estrattore AST Python per simboli, archi e scope_calls."""

from __future__ import annotations

import ast
import re
from typing import Dict, List, Optional, Set, Tuple

from _internal.ast_repo_mapper.models import (
    EdgeType,
    SymbolEdge,
    SymbolGraph,
    SymbolNode,
    SymbolType,
)


class SymbolExtractor(ast.NodeVisitor):
    """Estrae i simboli strutturati e le relazioni di dipendenza dall'AST."""

    def __init__(self, module_path: str, source_lines: List[str]):
        self.module_path = str(module_path).replace("\\", "/")
        self.source_lines = source_lines
        self.graph = SymbolGraph()
        self.current_class_id: Optional[str] = None
        self.current_scope_id: Optional[str] = None
        self.symbol_name_to_ids: Dict[str, Set[str]] = {}
        self.scope_calls: Dict[str, Set[str]] = {}
        self._extraction_pass: int = 0
        self._seen_edges: Set[Tuple[str, str, EdgeType]] = set()

    def _add_unique_edge(self, edge: SymbolEdge) -> None:
        key = (edge.source_id, edge.target_id, edge.edge_type)
        if key not in self._seen_edges:
            self._seen_edges.add(key)
            self.graph.add_edge(edge)

    def visit_Module(self, node: ast.Module) -> None:
        self._extraction_pass = 1
        self.generic_visit(node)
        self._extraction_pass = 2
        self.generic_visit(node)
        self._extraction_pass = 0

    def _register_name_mapping(self, name: str, symbol_id: str) -> None:
        self.symbol_name_to_ids.setdefault(name, set()).add(symbol_id)

    def _get_raw_source(self, start_line: int, end_line: int) -> str:
        s = max(0, start_line - 1)
        e = min(len(self.source_lines), end_line)
        return "".join(self.source_lines[s:e])

    def _format_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        args_str = self._format_arguments(node.args)
        ret_ann = ""
        if node.returns:
            try:
                ret_ann = f" -> {ast.unparse(node.returns)}"
            except Exception:
                ret_ann = ""
        return f"{prefix}{node.name}({args_str}){ret_ann}"

    def _format_arg(self, arg: ast.arg, default_node: Optional[ast.expr] = None) -> str:
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        if default_node is None:
            return f"{arg.arg}{ann}"
        try:
            return f"{arg.arg}{ann}={ast.unparse(default_node)}"
        except Exception:
            return f"{arg.arg}{ann}=..."

    def _format_arguments(self, args: ast.arguments) -> str:
        parts: List[str] = []
        posonly = getattr(args, "posonlyargs", [])
        for arg in posonly:
            parts.append(self._format_arg(arg))
        if posonly:
            parts.append("/")

        offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            d_idx = i - offset
            def_node = args.defaults[d_idx] if 0 <= d_idx < len(args.defaults) else None
            parts.append(self._format_arg(arg, def_node))

        if args.vararg:
            parts.append("*" + self._format_arg(args.vararg))
        elif args.kwonlyargs:
            parts.append("*")

        for i, arg in enumerate(args.kwonlyargs):
            parts.append(self._format_arg(arg, args.kw_defaults[i]))

        if args.kwarg:
            parts.append("**" + self._format_arg(args.kwarg))
        return ", ".join(parts)

    def _record_import_node(
        self,
        node: ast.AST,
        sym_id: str,
        name: str,
        asname: Optional[str],
        signature: str,
    ) -> None:
        end_ln = getattr(node, "end_lineno", node.lineno)  # type: ignore[attr-defined]
        sym_node = SymbolNode(
            id=sym_id,
            name=name,
            symbol_type=SymbolType.IMPORT,
            module_path=self.module_path,
            line_start=node.lineno,  # type: ignore[attr-defined]
            line_end=end_ln,
            signature=signature + (f" as {asname}" if asname else ""),
            raw_source=self._get_raw_source(node.lineno, end_ln),  # type: ignore[attr-defined]
        )
        self.graph.add_node(sym_node)
        self._register_name_mapping(asname or name, sym_id)

    def visit_Import(self, node: ast.Import) -> None:
        if self._extraction_pass in (0, 1):
            for alias in node.names:
                self._record_import_node(
                    node,
                    f"{self.module_path}:import_{alias.name}",
                    alias.name,
                    alias.asname,
                    f"import {alias.name}",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._extraction_pass in (0, 1):
            mod = node.module or ""
            for alias in node.names:
                self._record_import_node(
                    node,
                    f"{self.module_path}:import_{mod}.{alias.name}",
                    alias.name,
                    alias.asname,
                    f"from {mod} import {alias.name}",
                )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._extraction_pass in (0, 1):
            if self.current_scope_id is None or self.current_scope_id == self.current_class_id:
                for target in node.targets:
                    if isinstance(target, ast.Name) and (target.id.isupper() or self.current_class_id is None):
                        sym_id = (
                            f"{self.current_class_id}.{target.id}"
                            if self.current_class_id
                            else f"{self.module_path}:{target.id}"
                        )
                        end_ln = getattr(node, "end_lineno", node.lineno)
                        sym_node = SymbolNode(
                            id=sym_id,
                            name=target.id,
                            symbol_type=SymbolType.CONSTANT,
                            module_path=self.module_path,
                            parent_id=self.current_class_id,
                            line_start=node.lineno,
                            line_end=end_ln,
                            signature=f"{target.id} = ...",
                            raw_source=self._get_raw_source(node.lineno, end_ln),
                        )
                        self.graph.add_node(sym_node)
                        self._register_name_mapping(target.id, sym_id)
                        if self.current_class_id:
                            self._add_unique_edge(
                                SymbolEdge(
                                    source_id=self.current_class_id,
                                    target_id=sym_id,
                                    edge_type=EdgeType.CONTAINMENT,
                                    weight=1.0,
                                )
                            )
        if self._extraction_pass in (0, 2):
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_id = (
            f"{self.current_class_id}.{node.name}"
            if self.current_class_id
            else f"{self.module_path}:{node.name}"
        )
        if self._extraction_pass in (0, 1):
            doc = ast.get_docstring(node)
            bases_str = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            sig = f"class {node.name}({bases_str}):" if bases_str else f"class {node.name}:"
            end_ln = getattr(node, "end_lineno", node.lineno)
            sym_node = SymbolNode(
                id=class_id,
                name=node.name,
                symbol_type=SymbolType.CLASS,
                module_path=self.module_path,
                parent_id=self.current_class_id,
                line_start=node.lineno,
                line_end=end_ln,
                signature=sig,
                docstring=doc,
                raw_source=self._get_raw_source(node.lineno, end_ln),
            )
            self.graph.add_node(sym_node)
            self._register_name_mapping(node.name, class_id)
            if self.current_class_id:
                self._add_unique_edge(
                    SymbolEdge(
                        source_id=self.current_class_id,
                        target_id=class_id,
                        edge_type=EdgeType.CONTAINMENT,
                        weight=1.5,
                    )
                )

        if self._extraction_pass in (0, 2):
            for base in node.bases:
                base_name = ast.unparse(base)
                cand_names = [base_name] + re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", base_name)
                for b_tok in dict.fromkeys(cand_names):
                    for target_id in self.symbol_name_to_ids.get(b_tok, ()):
                        if target_id != class_id:
                            self._add_unique_edge(
                                SymbolEdge(
                                    source_id=class_id,
                                    target_id=target_id,
                                    edge_type=EdgeType.INHERITANCE,
                                    weight=2.0,
                                )
                            )

        prev_class, prev_scope = self.current_class_id, self.current_scope_id
        self.current_class_id = class_id
        self.current_scope_id = class_id
        self.generic_visit(node)
        self.current_class_id, self.current_scope_id = prev_class, prev_scope

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

        if self._extraction_pass in (0, 1):
            doc = ast.get_docstring(node)
            sig = self._format_signature(node)
            ret_type = ast.unparse(node.returns) if node.returns else None
            end_ln = getattr(node, "end_lineno", node.lineno)
            sym_node = SymbolNode(
                id=fn_id,
                name=node.name,
                symbol_type=sym_type,
                module_path=self.module_path,
                parent_id=self.current_class_id,
                line_start=node.lineno,
                line_end=end_ln,
                signature=sig,
                docstring=doc,
                return_type=ret_type,
                is_async=is_async,
                raw_source=self._get_raw_source(node.lineno, end_ln),
            )
            self.graph.add_node(sym_node)
            self._register_name_mapping(node.name, fn_id)
            if self.current_class_id:
                self._add_unique_edge(
                    SymbolEdge(
                        source_id=self.current_class_id,
                        target_id=fn_id,
                        edge_type=EdgeType.CONTAINMENT,
                        weight=1.5,
                    )
                )

        if self._extraction_pass in (0, 2):
            for arg in node.args.args + getattr(node.args, "posonlyargs", []) + node.args.kwonlyargs:
                if arg.annotation:
                    self._link_type_references(fn_id, ast.unparse(arg.annotation))
            if node.returns:
                self._link_type_references(fn_id, ast.unparse(node.returns))

        prev_scope = self.current_scope_id
        self.current_scope_id = fn_id
        self.generic_visit(node)
        if fn_id in self.scope_calls:
            self.scope_calls[fn_id].discard(node.name)
        self.current_scope_id = prev_scope

    def _link_type_references(self, source_id: str, type_str: str) -> None:
        for token_name in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", type_str):
            for target_id in self.symbol_name_to_ids.get(token_name, ()):
                if target_id != source_id:
                    self._add_unique_edge(
                        SymbolEdge(
                            source_id=source_id,
                            target_id=target_id,
                            edge_type=EdgeType.TYPE_REFERENCE,
                            weight=1.0,
                        )
                    )

    def visit_Call(self, node: ast.Call) -> None:
        if self._extraction_pass == 1:
            return
        if self.current_scope_id:
            callee_name: Optional[str] = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name:
                self.scope_calls.setdefault(self.current_scope_id, set()).add(callee_name)
                for target_id in self.symbol_name_to_ids.get(callee_name, ()):
                    if target_id != self.current_scope_id:
                        self._add_unique_edge(
                            SymbolEdge(
                                source_id=self.current_scope_id,
                                target_id=target_id,
                                edge_type=EdgeType.CALL,
                                weight=1.5,
                            )
                        )
        self.generic_visit(node)

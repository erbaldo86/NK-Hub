"""Collector AST per firme di funzioni, classi, basi e simboli globali."""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from _internal.ast_guard_validator.models import (
    FunctionSignatureSnapshot,
    _normalize_type_ast_node,
)


def _accessor_role_from_decorators(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    """Estrae il ruolo accessor (@property, setter, deleter, getter) dai decoratori."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            return "property"
        if isinstance(dec, ast.Attribute) and dec.attr in (
            "setter",
            "deleter",
            "getter",
        ):
            return dec.attr
    return ""


def _resolve_signature_key(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    current_class: Optional[str],
    existing: Dict[str, FunctionSignatureSnapshot],
) -> str:
    """Calcola chiave firma disambiguando @property getter, setter e deleter."""
    base_key = f"{current_class}.{node.name}" if current_class else node.name
    role = _accessor_role_from_decorators(node)
    if role in ("setter", "deleter"):
        return f"{base_key}[{role}]"
    if role == "getter" and base_key in existing:
        return f"{base_key}[getter]"
    return base_key


class SignatureCollector(ast.NodeVisitor):
    """Raccoglie firme delle funzioni, classi, basi ereditarie e nomi globali di modulo."""

    def __init__(self) -> None:
        self.signatures: Dict[str, FunctionSignatureSnapshot] = {}
        self.classes: Set[str] = set()
        self.class_bases: Dict[str, List[str]] = {}
        self.current_class: Optional[str] = None
        self.function_depth: int = 0
        self.imported_names: Set[str] = set()
        self.defined_globals: Set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.function_depth == 0:
            self.classes.add(node.name)
            cls_key = (
                f"{self.current_class}.{node.name}"
                if self.current_class
                else node.name
            )
            if getattr(self, "skip_unparse", False):
                self.class_bases[cls_key] = []
            else:
                self.class_bases[cls_key] = [
                    _normalize_type_ast_node(base) for base in node.bases
                ]
            self.defined_globals.add(node.name)
            for tp in getattr(node, "type_params", []):
                if hasattr(tp, "name"):
                    self.defined_globals.add(tp.name)
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_names.add(name.split(".")[0])
            if self.function_depth == 0:
                self.defined_globals.add(name)
                if alias.name:
                    self.defined_globals.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_names.add(name)
            if self.function_depth == 0:
                self.defined_globals.add(name)
        self.generic_visit(node)

    def _extract_target_names(self, node: ast.AST, target_set: Set[str]) -> None:
        if isinstance(node, ast.Name):
            target_set.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._extract_target_names(elt, target_set)
        elif isinstance(node, ast.Starred):
            self._extract_target_names(node.value, target_set)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.current_class is None and self.function_depth == 0:
            for t in node.targets:
                self._extract_target_names(t, self.defined_globals)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self.current_class is None and self.function_depth == 0:
            self._extract_target_names(node.target, self.defined_globals)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        if self.current_class is None and self.function_depth == 0:
            self._extract_target_names(node.target, self.defined_globals)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        if self.current_class is None and self.function_depth == 0:
            self._extract_target_names(node.target, self.defined_globals)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        if self.current_class is None and self.function_depth == 0:
            for item in node.items:
                if item.optional_vars:
                    self._extract_target_names(
                        item.optional_vars, self.defined_globals
                    )
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        if self.current_class is None and self.function_depth == 0:
            for item in node.items:
                if item.optional_vars:
                    self._extract_target_names(
                        item.optional_vars, self.defined_globals
                    )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if self.current_class is None and self.function_depth == 0 and node.name:
            self.defined_globals.add(node.name)
        self.generic_visit(node)

    def visit_TypeAlias(self, node: Any) -> None:
        if self.function_depth == 0 and hasattr(node, "name"):
            if isinstance(node.name, ast.Name):
                self.defined_globals.add(node.name.id)
            elif isinstance(node.name, str):
                self.defined_globals.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, is_async=False)
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, is_async=True)
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    def _record_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        if self.function_depth > 0:
            return
        key = _resolve_signature_key(node, self.current_class, self.signatures)
        if self.current_class is None:
            self.defined_globals.add(node.name)

        posonly = [a.arg for a in getattr(node.args, "posonlyargs", [])]
        pos_args = [a.arg for a in node.args.args]
        kwonly = [a.arg for a in node.args.kwonlyargs]
        vararg = node.args.vararg.arg if node.args.vararg else None
        kwarg = node.args.kwarg.arg if node.args.kwarg else None

        defaults_count = len(node.args.defaults)
        kw_defaults_count = len([d for d in node.args.kw_defaults if d is not None])
        kwonly_with_defaults = [
            a.arg
            for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults)
            if d is not None
        ]

        annotations: Dict[str, str] = {}
        return_ann: Optional[str] = None
        if not getattr(self, "skip_unparse", False):
            for arg in (
                getattr(node.args, "posonlyargs", [])
                + node.args.args
                + node.args.kwonlyargs
            ):
                if arg.annotation:
                    annotations[arg.arg] = ast.unparse(arg.annotation)
            if node.args.vararg and node.args.vararg.annotation:
                annotations[node.args.vararg.arg] = ast.unparse(
                    node.args.vararg.annotation
                )
            if node.args.kwarg and node.args.kwarg.annotation:
                annotations[node.args.kwarg.arg] = ast.unparse(
                    node.args.kwarg.annotation
                )
            return_ann = ast.unparse(node.returns) if node.returns else None

        self.signatures[key] = FunctionSignatureSnapshot(
            name=node.name,
            is_async=is_async,
            posonly_args=posonly,
            pos_args=pos_args,
            vararg=vararg,
            kwonly_args=kwonly,
            kwarg=kwarg,
            defaults_count=defaults_count,
            kw_defaults_count=kw_defaults_count,
            kwonly_with_defaults=kwonly_with_defaults,
            annotations=annotations,
            return_annotation=return_ann,
            parent_class=self.current_class,
        )

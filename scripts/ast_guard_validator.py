#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validatore statico AST deterministico per Nexus Keystone v3.0.0.
Modulo: ast_guard_validator.py.
Implementa la correzione U-20 (function_depth in SignatureCollector e confronto con produzione).

Funzionalita principali:
1. Verifica la purezza sintattica pre-modifica e post-modifica tramite ast.parse.
2. Verifica l'invariante di conservazione delle firme di funzioni e metodi.
3. Verifica l'integrita dello scope escludendo le variabili locali da defined_globals (U-20).
4. Supporta PEP 634 Pattern Matching, PEP 695 Type Parameters, comprehension e operatore walrus.
"""

from __future__ import annotations

import ast
import builtins
import difflib
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


class ViolationType(str, Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SIGNATURE_MUTATION = "SIGNATURE_MUTATION"
    UNAUTHORIZED_DELETION = "UNAUTHORIZED_DELETION"
    UNDEFINED_NAME = "UNDEFINED_NAME"
    MALFORMED_IMPORT = "MALFORMED_IMPORT"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    SAST_VIOLATION = "SAST_VIOLATION"


class GuardViolation(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    violation_type: ViolationType = Field(description="Categoria della violazione AST")
    symbol_name: Optional[str] = Field(
        default=None, description="Nome del simbolo coinvolto"
    )
    line_number: Optional[int] = Field(
        default=None, description="Numero di riga (1-indexed)"
    )
    column: Optional[int] = Field(default=None, description="Offset di colonna (0-indexed)")
    message: str = Field(description="Diagnosi esplicativa dell'errore")
    diff_context: Optional[str] = Field(
        default=None, description="Frammento diff o contesto della riga"
    )


class FunctionSignatureSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    name: str = Field(description="Nome della funzione o del metodo")
    is_async: bool = Field(description="Indica se la funzione e asincrona")
    posonly_args: List[str] = Field(
        default_factory=list, description="Argomenti solo posizionali"
    )
    pos_args: List[str] = Field(
        default_factory=list, description="Argomenti posizionali standard"
    )
    vararg: Optional[str] = Field(default=None, description="Nome *args se presente")
    kwonly_args: List[str] = Field(
        default_factory=list, description="Argomenti solo keyword"
    )
    kwarg: Optional[str] = Field(default=None, description="Nome **kwargs se presente")
    defaults_count: int = Field(
        default=0, description="Numero di valori di default posizionali"
    )
    kw_defaults_count: int = Field(
        default=0, description="Numero di valori di default keyword non-None"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Mappa argomento -> stringa annotazione"
    )
    return_annotation: Optional[str] = Field(
        default=None, description="Stringa annotazione tipo di ritorno"
    )
    parent_class: Optional[str] = Field(
        default=None, description="Nome della classe contenitore"
    )


class ValidationReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    is_valid: bool = Field(description="True se non ci sono violazioni critiche")
    pre_symbol_count: int = Field(description="Totale simboli nell'AST pre-modifica")
    post_symbol_count: int = Field(description="Totale simboli nell'AST post-modifica")
    violations: List[GuardViolation] = Field(
        default_factory=list, description="Lista delle violazioni rilevate"
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Metriche dettagliate di validazione"
    )


class SignatureCollector(ast.NodeVisitor):
    """Raccoglie le firme delle funzioni e i nomi globali di modulo (U-20)."""

    def __init__(self) -> None:
        self.signatures: Dict[str, FunctionSignatureSnapshot] = {}
        self.classes: Set[str] = set()
        self.current_class: Optional[str] = None
        self.function_depth: int = 0
        self.imported_names: Set[str] = set()
        self.defined_globals: Set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.function_depth == 0:
            self.classes.add(node.name)
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
        # U-20: registra solo variabili a livello di modulo (function_depth == 0)
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
        key = (
            f"{self.current_class}.{node.name}"
            if self.current_class
            else node.name
        )
        if self.current_class is None:
            self.defined_globals.add(node.name)

        posonly = [a.arg for a in getattr(node.args, "posonlyargs", [])]
        pos_args = [a.arg for a in node.args.args]
        kwonly = [a.arg for a in node.args.kwonlyargs]
        vararg = node.args.vararg.arg if node.args.vararg else None
        kwarg = node.args.kwarg.arg if node.args.kwarg else None

        defaults_count = len(node.args.defaults)
        kw_defaults_count = len([d for d in node.args.kw_defaults if d is not None])

        annotations: Dict[str, str] = {}
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
            annotations=annotations,
            return_annotation=return_ann,
            parent_class=self.current_class,
        )


MODULE_DUNDERS: Set[str] = {
    "__name__",
    "__doc__",
    "__file__",
    "__package__",
    "__loader__",
    "__spec__",
    "__annotations__",
    "__builtins__",
    "__cached__",
}


class ScopeIntegrityChecker(ast.NodeVisitor):
    """Verifica che ogni variabile referenziata in lettura sia definita nello scope visibile."""

    def __init__(self, global_names: Set[str]) -> None:
        self.global_names = set(global_names) | MODULE_DUNDERS
        self.builtins_set = set(dir(builtins))
        self.scope_stack: List[Set[str]] = [set(self.global_names)]
        self.violations: List[GuardViolation] = []

    def _current_visible_names(self) -> Set[str]:
        names: Set[str] = set(self.builtins_set)
        for s in self.scope_stack:
            names.update(s)
        return names

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in node.args.defaults:
            if d is not None:
                self.visit(d)
        for d in getattr(node.args, "kw_defaults", []):
            if d is not None:
                self.visit(d)
        local_scope: Set[str] = set()
        for arg in (
            getattr(node.args, "posonlyargs", [])
            + node.args.args
            + node.args.kwonlyargs
        ):
            local_scope.add(arg.arg)
        if node.args.vararg:
            local_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_scope.add(node.args.kwarg.arg)
        self.scope_stack.append(local_scope)
        self.visit(node.body)
        self.scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw)

        self.scope_stack[-1].add(node.name)
        local_scope: Set[str] = set()
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                local_scope.add(tp.name)

        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    self._extract_target_names(t, local_scope)
            elif isinstance(stmt, ast.AnnAssign):
                self._extract_target_names(stmt.target, local_scope)

        self.scope_stack.append(local_scope)
        for child in node.body:
            self.visit(child)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_func(node)

    def _process_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for d in node.args.defaults:
            if d is not None:
                self.visit(d)
        for d in getattr(node.args, "kw_defaults", []):
            if d is not None:
                self.visit(d)

        self.scope_stack[-1].add(node.name)
        local_scope: Set[str] = set()

        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                local_scope.add(tp.name)

        for arg in (
            getattr(node.args, "posonlyargs", [])
            + node.args.args
            + node.args.kwonlyargs
        ):
            local_scope.add(arg.arg)
        if node.args.vararg:
            local_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_scope.add(node.args.kwarg.arg)

        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    self._extract_target_names(t, local_scope)
            elif isinstance(child, ast.AnnAssign):
                self._extract_target_names(child.target, local_scope)
            elif isinstance(child, ast.For):
                self._extract_target_names(child.target, local_scope)
            elif isinstance(child, ast.AsyncFor):
                self._extract_target_names(child.target, local_scope)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                local_scope.add(child.name)
            elif isinstance(child, ast.With):
                for item in child.items:
                    if item.optional_vars:
                        self._extract_target_names(item.optional_vars, local_scope)
            elif isinstance(child, ast.AsyncWith):
                for item in child.items:
                    if item.optional_vars:
                        self._extract_target_names(item.optional_vars, local_scope)
            elif isinstance(child, ast.NamedExpr):
                if isinstance(child.target, ast.Name):
                    local_scope.add(child.target.id)
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    name = alias.asname or alias.name
                    local_scope.add(name)
                    local_scope.add(name.split(".")[0])
            elif isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    local_scope.add(alias.asname or alias.name)
            elif isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                local_scope.add(child.name)

        self.scope_stack.append(local_scope)

        for child in node.body:
            self.visit(child)

        self.scope_stack.pop()

    def _extract_target_names(self, node: ast.AST, target_set: Set[str]) -> None:
        if isinstance(node, ast.Name):
            target_set.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._extract_target_names(elt, target_set)
        elif isinstance(node, ast.Starred):
            self._extract_target_names(node.value, target_set)

    def visit_Match(self, node: Any) -> None:
        self.visit(node.subject)
        for case in node.cases:
            pattern_bindings: Set[str] = set()
            self._extract_pattern_bindings(case.pattern, pattern_bindings)
            self.scope_stack[-1].update(pattern_bindings)
            if case.guard:
                self.visit(case.guard)
            for stmt in case.body:
                self.visit(stmt)

    def _extract_pattern_bindings(self, pattern: Any, bindings: Set[str]) -> None:
        if pattern is None:
            return
        p_type = type(pattern).__name__

        if p_type == "MatchAs":
            if getattr(pattern, "name", None):
                bindings.add(pattern.name)
            if getattr(pattern, "pattern", None):
                self._extract_pattern_bindings(pattern.pattern, bindings)
        elif p_type == "MatchStar":
            if getattr(pattern, "name", None):
                bindings.add(pattern.name)
        elif p_type == "MatchMapping":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)
            if getattr(pattern, "rest", None):
                bindings.add(pattern.rest)
        elif p_type == "MatchClass":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)
            for p in getattr(pattern, "kwd_patterns", []):
                self._extract_pattern_bindings(p, bindings)
        elif p_type == "MatchSequence":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)
        elif p_type == "MatchOr":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)

    def visit_TypeAlias(self, node: Any) -> None:
        if hasattr(node, "name"):
            if isinstance(node.name, ast.Name):
                self.scope_stack[-1].add(node.name.id)
            elif isinstance(node.name, str):
                self.scope_stack[-1].add(node.name)
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                self.scope_stack[-1].add(tp.name)
        if hasattr(node, "value"):
            self.visit(node.value)

    def _visit_comprehension_common(
        self, generators: List[ast.comprehension], visit_elts_fn: Any
    ) -> None:
        comp_scope: Set[str] = set()
        for gen in generators:
            self.visit(gen.iter)
            self._extract_target_names(gen.target, comp_scope)

        self.scope_stack.append(comp_scope)
        for gen in generators:
            for if_expr in gen.ifs:
                self.visit(if_expr)
        visit_elts_fn()
        self.scope_stack.pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension_common(node.generators, lambda: self.visit(node.elt))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension_common(node.generators, lambda: self.visit(node.elt))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension_common(node.generators, lambda: self.visit(node.elt))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        def visit_kv() -> None:
            self.visit(node.key)
            self.visit(node.value)

        self._visit_comprehension_common(node.generators, visit_kv)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            frame_idx = len(self.scope_stack) - 1
            if frame_idx > 0:
                self.scope_stack[frame_idx - 1].add(node.target.id)
            self.scope_stack[frame_idx].add(node.target.id)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            visible = self._current_visible_names()
            if node.id not in visible:
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.UNDEFINED_NAME,
                        symbol_name=node.id,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message=f"Undefined name '{node.id}' referenced without import or local binding.",
                    )
                )
        self.generic_visit(node)


class SASTConstructChecker(ast.NodeVisitor):
    """Rileva costrutti non sicuri eval, exec, compile, deserializzazioni, shell=True e MagicMock."""

    def __init__(self) -> None:
        self.violations: List[GuardViolation] = []
        self._imported_aliases: Dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name
            self._imported_aliases[bound] = alias.name
            if alias.name == "unittest.mock" or "MagicMock" in bound:
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name=alias.name,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message="Zero-Mock violation: unittest.mock or MagicMock import detected.",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name
            if node.module:
                self._imported_aliases[bound] = f"{node.module}.{alias.name}"
            if alias.name == "MagicMock" or (node.module and "unittest.mock" in node.module):
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name=alias.name,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message="Zero-Mock violation: MagicMock import detected.",
                    )
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            resolved = self._imported_aliases.get(func.id, func.id)
            if func.id in ("eval", "exec", "compile"):
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name=func.id,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message=f"Unsafe SAST construct '{func.id}()' detected.",
                    )
                )
            elif func.id == "MagicMock" or resolved.endswith(".MagicMock"):
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name="MagicMock",
                        line_number=node.lineno,
                        column=node.col_offset,
                        message="Zero-Mock violation: MagicMock instantiation detected.",
                    )
                )
            elif func.id == "open" and node.args:
                first_arg = node.args[0]
                raw_path = ""
                if isinstance(first_arg, ast.Constant) and isinstance(
                    first_arg.value, str
                ):
                    raw_path = first_arg.value
                elif isinstance(first_arg, ast.JoinedStr):
                    raw_path = "".join(
                        p.value
                        for p in first_arg.values
                        if isinstance(p, ast.Constant) and isinstance(p.value, str)
                    )
                if "../" in raw_path or "..\\" in raw_path:
                    self.violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SAST_VIOLATION,
                            symbol_name="open",
                            line_number=node.lineno,
                            column=node.col_offset,
                            message="Unsafe path traversal in 'open()' detected.",
                        )
                    )
            elif resolved in ("os.system", "os.popen"):
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name=resolved,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message=f"Unsafe OS command execution '{resolved}()' detected.",
                    )
                )
            elif resolved in (
                "pickle.loads",
                "pickle.load",
                "marshal.loads",
                "marshal.load",
            ):
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name=resolved,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message=f"Unsafe deserialization '{resolved}()' detected.",
                    )
                )
            elif resolved in (
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_output",
            ):
                for kw in node.keywords:
                    if (
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        self.violations.append(
                            GuardViolation(
                                violation_type=ViolationType.SAST_VIOLATION,
                                symbol_name=resolved,
                                line_number=node.lineno,
                                column=node.col_offset,
                                message=f"Unsafe '{resolved}(..., shell=True)' detected.",
                            )
                        )
                        break
            elif resolved == "yaml.load":
                has_safe_loader = False
                for kw in node.keywords:
                    if kw.arg == "Loader" and "SafeLoader" in ast.unparse(kw.value):
                        has_safe_loader = True
                if not has_safe_loader:
                    self.violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SAST_VIOLATION,
                            symbol_name="yaml.load",
                            line_number=node.lineno,
                            column=node.col_offset,
                            message="Unsafe 'yaml.load()' without SafeLoader detected.",
                        )
                    )
        elif isinstance(func, ast.Attribute):
            val = func.value
            attr = func.attr
            if isinstance(val, ast.Name):
                base_mod = self._imported_aliases.get(val.id, val.id)
                if base_mod == "pickle" and attr in ("loads", "load"):
                    self.violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SAST_VIOLATION,
                            symbol_name=f"pickle.{attr}",
                            line_number=node.lineno,
                            column=node.col_offset,
                            message=f"Unsafe deserialization 'pickle.{attr}()' detected.",
                        )
                    )
                elif base_mod == "yaml" and attr == "load":
                    has_safe_loader = False
                    for kw in node.keywords:
                        if kw.arg == "Loader" and "SafeLoader" in ast.unparse(kw.value):
                            has_safe_loader = True
                    if not has_safe_loader:
                        self.violations.append(
                            GuardViolation(
                                violation_type=ViolationType.SAST_VIOLATION,
                                symbol_name="yaml.load",
                                line_number=node.lineno,
                                column=node.col_offset,
                                message="Unsafe 'yaml.load()' without SafeLoader detected.",
                            )
                        )
                elif base_mod == "os" and attr in ("system", "popen"):
                    self.violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SAST_VIOLATION,
                            symbol_name=f"os.{attr}",
                            line_number=node.lineno,
                            column=node.col_offset,
                            message=f"Unsafe OS command execution 'os.{attr}()' detected.",
                        )
                    )
                elif base_mod == "marshal" and attr in ("loads", "load"):
                    self.violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SAST_VIOLATION,
                            symbol_name=f"marshal.{attr}",
                            line_number=node.lineno,
                            column=node.col_offset,
                            message=f"Unsafe deserialization 'marshal.{attr}()' detected.",
                        )
                    )
                elif base_mod == "subprocess" and attr in (
                    "run",
                    "Popen",
                    "call",
                    "check_output",
                ):
                    for kw in node.keywords:
                        if (
                            kw.arg == "shell"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            self.violations.append(
                                GuardViolation(
                                    violation_type=ViolationType.SAST_VIOLATION,
                                    symbol_name=f"subprocess.{attr}",
                                    line_number=node.lineno,
                                    column=node.col_offset,
                                    message=f"Unsafe 'subprocess.{attr}(..., shell=True)' detected.",
                                )
                            )
                            break
            if attr in ("execute", "executemany") and node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.JoinedStr):
                    raw_sql = "".join(
                        part.value
                        for part in first_arg.values
                        if isinstance(part, ast.Constant)
                        and isinstance(part.value, str)
                    ).upper()
                    sql_keywords = (
                        "SELECT ",
                        "INSERT ",
                        "UPDATE ",
                        "DELETE ",
                        "DROP ",
                    )
                    if any(kw in raw_sql for kw in sql_keywords):
                        self.violations.append(
                            GuardViolation(
                                violation_type=ViolationType.SAST_VIOLATION,
                                symbol_name=attr,
                                line_number=node.lineno,
                                column=node.col_offset,
                                message=f"Unsafe SQL f-string injection in '.{attr}()' detected.",
                            )
                        )
            if attr == "MagicMock":
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SAST_VIOLATION,
                        symbol_name="MagicMock",
                        line_number=node.lineno,
                        column=node.col_offset,
                        message="Zero-Mock violation: MagicMock attribute call detected.",
                    )
                )
        self.generic_visit(node)


class ASTGuardValidator:
    """Validatore principale che coordina purezza sintattica, firme e integrita scope."""

    def __init__(self, allowed_mutations: Optional[Set[str]] = None) -> None:
        if isinstance(allowed_mutations, str):
            self.allowed_mutations: Set[str] = {
                s.strip() for s in allowed_mutations.split(",") if s.strip()
            }
        elif allowed_mutations is not None:
            self.allowed_mutations = {
                str(s).strip() for s in allowed_mutations if str(s).strip()
            }
        else:
            self.allowed_mutations = set()

    @classmethod
    def check_sast_constructs(cls, code: str) -> List[GuardViolation]:
        """Scansiona l'AST per rilevare costrutti SAST proibiti e uso di MagicMock."""
        try:
            tree = ast.parse(code, type_comments=True)
        except SyntaxError:
            return []
        sast_checker = SASTConstructChecker()
        sast_checker.visit(tree)
        return sast_checker.violations

    @classmethod
    def validate_code_edit(
        cls,
        pre_code: str,
        post_code: str,
        allowed_mutations: Optional[Set[str]] = None,
        target_file: str = "<target>",
    ) -> ValidationReport:
        """Esegue la suite completa di guardie AST sulla trasformazione del codice."""
        violations: List[GuardViolation] = []
        allowed = allowed_mutations or set()

        pre_tree = cls._parse_or_report(pre_code, "pre_edit", violations)
        post_tree = cls._parse_or_report(post_code, "post_edit", violations)

        if post_tree is None:
            return ValidationReport(
                is_valid=False,
                pre_symbol_count=0,
                post_symbol_count=0,
                violations=violations,
                metrics={"fatal_syntax_error": True},
            )

        pre_collector = SignatureCollector()
        if pre_tree:
            pre_collector.visit(pre_tree)

        post_collector = SignatureCollector()
        post_collector.visit(post_tree)

        cls._verify_signatures(
            pre_collector.signatures,
            post_collector.signatures,
            allowed,
            violations,
        )

        checker = ScopeIntegrityChecker(global_names=post_collector.defined_globals)
        checker.visit(post_tree)
        violations.extend(checker.violations)

        sast_checker = SASTConstructChecker()
        sast_checker.visit(post_tree)
        sast_violations = sast_checker.violations
        violations.extend(sast_violations)

        diff = difflib.unified_diff(
            pre_code.splitlines(),
            post_code.splitlines(),
            fromfile=f"pre/{target_file}",
            tofile=f"post/{target_file}",
            lineterm="",
        )
        diff_lines = list(diff)

        is_valid = len(violations) == 0

        return ValidationReport(
            is_valid=is_valid,
            pre_symbol_count=len(pre_collector.signatures) + len(pre_collector.classes),
            post_symbol_count=len(post_collector.signatures)
            + len(post_collector.classes),
            violations=violations,
            metrics={
                "diff_line_count": len(diff_lines),
                "total_violations": len(violations),
                "sast_violations_count": len(sast_violations),
                "sast_violations": [v.message for v in sast_violations],
                "syntax_clean": True,
                "pre_functions": len(pre_collector.signatures),
                "post_functions": len(post_collector.signatures),
                "pre_classes": len(pre_collector.classes),
                "post_classes": len(post_collector.classes),
            },
        )

    @classmethod
    def _parse_or_report(
        cls, code: str, stage: str, violations: List[GuardViolation]
    ) -> Optional[ast.AST]:
        try:
            return ast.parse(code, type_comments=True)
        except SyntaxError as se:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SYNTAX_ERROR,
                    symbol_name=None,
                    line_number=se.lineno,
                    column=se.offset,
                    message=f"SyntaxError in {stage}: {se.msg}",
                    diff_context=se.text,
                )
            )
            return None

    @classmethod
    def _verify_signatures(
        cls,
        pre_sigs: Dict[str, FunctionSignatureSnapshot],
        post_sigs: Dict[str, FunctionSignatureSnapshot],
        allowed_mutations: Set[str],
        violations: List[GuardViolation],
    ) -> None:
        for name, pre_sig in pre_sigs.items():
            if name in allowed_mutations:
                continue

            if name not in post_sigs:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.UNAUTHORIZED_DELETION,
                        symbol_name=name,
                        message=f"Function/Method '{name}' was deleted without explicit authorization in allowed_mutations.",
                    )
                )
                continue

            post_sig = post_sigs[name]

            # 1. Invariante async
            if pre_sig.is_async != post_sig.is_async:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Async modifier altered for '{name}'. Pre: is_async={pre_sig.is_async}, Post: is_async={post_sig.is_async}",
                    )
                )

            # 2. Invariante argomenti posizionali e default (consente solo estensioni opzionali retrocompatibili)
            pre_n = len(pre_sig.pos_args)
            post_n = len(post_sig.pos_args)
            pre_req = pre_n - pre_sig.defaults_count
            post_req = post_n - post_sig.defaults_count

            is_backward_compatible_extension = (
                post_n > pre_n
                and post_sig.pos_args[:pre_n] == pre_sig.pos_args
                and post_req <= pre_req
                and post_sig.defaults_count >= pre_sig.defaults_count
            )

            if not is_backward_compatible_extension:
                if pre_sig.pos_args != post_sig.pos_args:
                    violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SIGNATURE_MUTATION,
                            symbol_name=name,
                            message=f"Positional arguments changed for '{name}'. Expected {pre_sig.pos_args}, got {post_sig.pos_args}",
                        )
                    )
                elif pre_sig.defaults_count != post_sig.defaults_count:
                    violations.append(
                        GuardViolation(
                            violation_type=ViolationType.SIGNATURE_MUTATION,
                            symbol_name=name,
                            message=f"Default parameter count changed for '{name}'. Expected {pre_sig.defaults_count}, got {post_sig.defaults_count}",
                        )
                    )

            # 3. Invariante argomenti keyword-only
            if pre_sig.kwonly_args != post_sig.kwonly_args:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Keyword-only arguments changed for '{name}'. Expected {pre_sig.kwonly_args}, got {post_sig.kwonly_args}",
                    )
                )

            # 4. Invariante annotazioni di tipo esistenti
            for arg_name, pre_ann in pre_sig.annotations.items():
                post_ann = post_sig.annotations.get(arg_name)
                if post_ann != pre_ann:
                    violations.append(
                        GuardViolation(
                            violation_type=ViolationType.TYPE_MISMATCH,
                            symbol_name=f"{name}:{arg_name}",
                            message=f"Type annotation for parameter '{arg_name}' altered in '{name}'. Expected '{pre_ann}', got '{post_ann}'",
                        )
                    )

            if (
                pre_sig.return_annotation is not None
                and pre_sig.return_annotation != post_sig.return_annotation
            ):
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.TYPE_MISMATCH,
                        symbol_name=f"{name}:return",
                        message=f"Return type annotation altered for '{name}'. Expected '{pre_sig.return_annotation}', got '{post_sig.return_annotation}'",
                    )
                )


def _resolve_production_counterpart(py_file: Path, workspace_root: Path) -> Optional[Path]:
    """Individua il file di produzione corrispondente se py_file si trova in .staging/."""
    resolved = py_file.resolve()
    parts = list(resolved.parts)
    if ".staging" in parts:
        idx = parts.index(".staging")
        rel_parts = parts[idx + 1 :]
        if rel_parts:
            prod_cand = workspace_root.joinpath(*rel_parts)
            if prod_cand.exists() and prod_cand.is_file() and prod_cand != resolved:
                return prod_cand
    return None


def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Deterministic AST Guard Validator")
    parser.add_argument(
        "target_path",
        nargs="?",
        default=None,
        help="Percorso del file o directory Python da scansionare, oppure 'all'",
    )
    parser.add_argument(
        "--target",
        "--stage-dir",
        dest="target",
        default=None,
        help="File o directory target da scansionare, oppure 'all'",
    )
    parser.add_argument(
        "--allowed-mutations",
        type=str,
        default="",
        help="Simboli separati da virgola autorizzati a mutare firma",
    )

    args = parser.parse_args()
    raw_target = args.target or args.target_path
    allowed_set = {
        s.strip() for s in args.allowed_mutations.split(",") if s.strip()
    }
    validator = ASTGuardValidator(allowed_mutations=allowed_set)

    if not raw_target:
        raw_target = "all"

    script_dir = Path(__file__).resolve().parent
    workspace_root = (
        script_dir.parent.parent
        if script_dir.parent.name == ".staging"
        else script_dir.parent
    )

    targets_to_scan: List[Path] = []
    if raw_target.lower() == "all":
        for candidate in ["scripts", "tests"]:
            cand_path = workspace_root / candidate
            if cand_path.exists():
                targets_to_scan.append(cand_path)
    else:
        p = Path(raw_target)
        if not p.exists():
            print(f"[ERROR] Path does not exist: {p}")
            return 1
        targets_to_scan.append(p)

    py_files: List[Path] = []
    for t in targets_to_scan:
        if t.is_file() and t.suffix == ".py":
            py_files.append(t)
        elif t.is_dir():
            py_files.extend(
                sorted([f for f in t.rglob("*.py") if "__pycache__" not in f.parts])
            )

    py_files = sorted(list(dict.fromkeys(py_files)))

    total_violations = 0
    print("================================================================================")
    print(f"AST GUARD VALIDATOR: Scanning {len(py_files)} files across targets")
    print("================================================================================")

    for py_file in py_files:
        try:
            code = py_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[FAIL] {py_file} - Could not read file: {e}")
            total_violations += 1
            continue

        # U-20: confronta il file in .staging/ con la controparte di produzione se esiste
        prod_file = _resolve_production_counterpart(py_file, workspace_root)
        pre_code = code
        if prod_file is not None:
            try:
                pre_code = prod_file.read_text(encoding="utf-8")
            except Exception:
                pre_code = code

        report = validator.validate_code_edit(
            pre_code,
            code,
            allowed_mutations=validator.allowed_mutations,
            target_file=py_file.name,
        )
        rel_path = py_file.as_posix()
        if not report.is_valid:
            print(f"[FAIL] {rel_path} - {len(report.violations)} AST violation(s):")
            for v in report.violations:
                loc = (
                    f"L{v.line_number}:{v.column}"
                    if v.line_number is not None
                    else "GLOBAL"
                )
                print(f"       - [{v.violation_type.value}] {loc}: {v.message}")
            total_violations += len(report.violations)
        else:
            print(f"[PASS] {rel_path} (Symbols: {report.post_symbol_count})")

    print("================================================================================")
    if total_violations == 0:
        print(
            f"[RESULT] ALL {len(py_files)} FILES PASSED DETERMINISTIC AST GUARD VALIDATION."
        )
        return 0
    else:
        print(
            f"[RESULT] FAILED: {total_violations} total violations detected across {len(py_files)} files."
        )
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

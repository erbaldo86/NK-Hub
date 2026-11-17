"""Controllo deterministico integrita scope lessicale e binding/del."""

from __future__ import annotations

import ast
import builtins
from typing import Any, List, Set

from _internal.ast_guard_validator.models import GuardViolation, ViolationType
from _internal.ast_guard_validator.scope_bindings import (
    collect_func_local_bindings,
    extract_deleted_names,
    extract_pattern_bindings,
    extract_target_names,
)


MODULE_DUNDERS: Set[str] = {
    "__name__", "__doc__", "__file__", "__package__", "__loader__",
    "__spec__", "__annotations__", "__builtins__", "__cached__",
}


class ScopeIntegrityChecker(ast.NodeVisitor):
    """Verifica che ogni variabile referenziata in lettura sia definita, non cancellata e non UnboundLocal."""

    def __init__(self, global_names: Set[str]) -> None:
        self.global_names = set(global_names) | MODULE_DUNDERS
        self.builtins_set = set(dir(builtins))
        self.scope_stack: List[Set[str]] = [set(self.global_names)]
        self.deleted_stack: List[Set[str]] = [set()]
        self.scope_is_class: List[bool] = [False]
        self.scope_all_bindings: List[Set[str]] = [set(self.global_names)]
        self.scope_future_locals: List[Set[str]] = [set()]
        self._comp_depth: int = 0
        self.violations: List[GuardViolation] = []

    def _current_visible_names(self) -> Set[str]:
        names: Set[str] = set(self.builtins_set)
        last_idx = len(self.scope_stack) - 1
        for idx, s in enumerate(self.scope_stack):
            if idx < last_idx and self.scope_is_class[idx]:
                continue
            names.update(s)
            if idx < last_idx and idx < len(self.scope_all_bindings):
                names.update(self.scope_all_bindings[idx])
        if self.deleted_stack:
            names -= self.deleted_stack[-1]
        return names

    def _bind_name_in_current_scope(self, name: str) -> None:
        self.scope_stack[-1].add(name)
        self.deleted_stack[-1].discard(name)
        if self.scope_future_locals:
            self.scope_future_locals[-1].discard(name)

    def _bind_target_names_in_current_scope(self, target_node: ast.AST) -> None:
        bound: Set[str] = set()
        self._extract_target_names(target_node, bound)
        for b_name in bound:
            self._bind_name_in_current_scope(b_name)

    def _extract_deleted_names(self, node: ast.AST, out: Set[str]) -> None:
        extract_deleted_names(node, out)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, (ast.Subscript, ast.Attribute)):
                self.visit(target)
                continue
            deleted_names: Set[str] = set()
            self._extract_deleted_names(target, deleted_names)
            for d_name in deleted_names:
                self.scope_stack[-1].discard(d_name)
                self.deleted_stack[-1].add(d_name)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for t in node.targets:
            if isinstance(t, (ast.Subscript, ast.Attribute)):
                self.visit(t)
            else:
                self._bind_target_names_in_current_scope(t)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.annotation:
            self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            if isinstance(node.target, (ast.Subscript, ast.Attribute)):
                self.visit(node.target)
            else:
                self._bind_target_names_in_current_scope(node.target)

    def _record_undef(self, sym: str, node: ast.AST, message: str) -> None:
        self.violations.append(GuardViolation(
            violation_type=ViolationType.UNDEFINED_NAME, symbol_name=sym,
            line_number=node.lineno, column=node.col_offset, message=message,
        ))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            is_future_local = bool(self.scope_future_locals and node.target.id in self.scope_future_locals[-1])
            if (
                node.target.id in self.deleted_stack[-1]
                or is_future_local
                or node.target.id not in self._current_visible_names()
            ):
                self._record_undef(
                    node.target.id, node,
                    f"Undefined or deleted name '{node.target.id}' referenced in augmented assignment.",
                )
        else:
            self.visit(node.target)
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._bind_name_in_current_scope(node.target.id)

    def _visit_for_common(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        self._bind_target_names_in_current_scope(node.target)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_For(self, node: ast.For) -> None:
        self._visit_for_common(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_for_common(node)

    def _visit_with_common(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._bind_target_names_in_current_scope(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with_common(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with_common(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type:
            self.visit(node.type)
        if node.name:
            self._bind_name_in_current_scope(node.name)
        for stmt in node.body:
            self.visit(stmt)

    def _push_scope(
        self, local_scope: Set[str], is_class: bool = False,
        all_bindings: Set[str] | None = None, future_locals: Set[str] | None = None,
    ) -> None:
        self.scope_stack.append(local_scope)
        self.deleted_stack.append(set())
        self.scope_is_class.append(is_class)
        self.scope_all_bindings.append(set(local_scope) if all_bindings is None else all_bindings)
        self.scope_future_locals.append(set() if future_locals is None else future_locals)

    def _pop_scope(self) -> None:
        self.scope_future_locals.pop()
        self.scope_all_bindings.pop()
        self.scope_is_class.pop()
        self.deleted_stack.pop()
        self.scope_stack.pop()

    def _collect_signature_params(self, args: ast.arguments, scope: Set[str]) -> None:
        for arg in getattr(args, "posonlyargs", []) + args.args + args.kwonlyargs:
            scope.add(arg.arg)
        if args.vararg:
            scope.add(args.vararg.arg)
        if args.kwarg:
            scope.add(args.kwarg.arg)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in node.args.defaults:
            if d is not None:
                self.visit(d)
        for d in getattr(node.args, "kw_defaults", []):
            if d is not None:
                self.visit(d)
        local_scope: Set[str] = set()
        self._collect_signature_params(node.args, local_scope)
        self._push_scope(local_scope)
        try:
            self.visit(node.body)
        finally:
            self._pop_scope()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expr in (*node.decorator_list, *node.bases, *node.keywords):
            self.visit(expr)
        self._bind_name_in_current_scope(node.name)
        local_scope: Set[str] = {tp.name for tp in getattr(node, "type_params", []) if hasattr(tp, "name")}
        self._push_scope(local_scope, is_class=True)
        try:
            for child in node.body:
                self.visit(child)
        finally:
            self._pop_scope()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_func(node)

    def _process_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for d in (*node.args.defaults, *getattr(node.args, "kw_defaults", [])):
            if d is not None:
                self.visit(d)
        self._bind_name_in_current_scope(node.name)
        local_scope: Set[str] = {tp.name for tp in getattr(node, "type_params", []) if hasattr(tp, "name")}
        self._collect_signature_params(node.args, local_scope)

        all_func_bindings: Set[str] = set(local_scope)
        declared_nonlocal_global: Set[str] = set()
        self._collect_func_local_bindings(node.body, all_func_bindings, declared_nonlocal_global)
        local_scope.update(declared_nonlocal_global)
        self._push_scope(local_scope, all_bindings=all_func_bindings, future_locals=all_func_bindings - local_scope)
        try:
            for child in node.body:
                self.visit(child)
        finally:
            self._pop_scope()

    def _collect_func_local_bindings(
        self, nodes: List[ast.stmt], local_scope: Set[str], declared_shared: Set[str] | None = None,
    ) -> None:
        """Raccoglie i simboli locali della funzione senza scendere in funzioni o classi annidate."""
        collect_func_local_bindings(nodes, local_scope, declared_shared)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self._bind_name_in_current_scope(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self._bind_name_in_current_scope(name)

    def _extract_target_names(self, node: ast.AST, target_set: Set[str]) -> None:
        extract_target_names(node, target_set)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._bind_name_in_current_scope(name)
            self._bind_name_in_current_scope(name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._bind_name_in_current_scope(alias.asname or alias.name)

    def visit_Match(self, node: Any) -> None:
        self.visit(node.subject)
        for case in node.cases:
            pattern_bindings: Set[str] = set()
            self._extract_pattern_bindings(case.pattern, pattern_bindings)
            for pb in pattern_bindings:
                self._bind_name_in_current_scope(pb)
            if case.guard:
                self.visit(case.guard)
            for stmt in case.body:
                self.visit(stmt)

    def _extract_pattern_bindings(self, pattern: Any, bindings: Set[str]) -> None:
        extract_pattern_bindings(pattern, bindings)

    def visit_TypeAlias(self, node: Any) -> None:
        if hasattr(node, "name"):
            if isinstance(node.name, ast.Name):
                self._bind_name_in_current_scope(node.name.id)
            elif isinstance(node.name, str):
                self._bind_name_in_current_scope(node.name)
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                self._bind_name_in_current_scope(tp.name)
        if hasattr(node, "value"):
            self.visit(node.value)

    def _visit_comprehension_common(
        self, generators: List[ast.comprehension], visit_elts_fn: Any
    ) -> None:
        if generators:
            self.visit(generators[0].iter)
        comp_scope: Set[str] = set()
        self._push_scope(comp_scope)
        self._comp_depth += 1
        try:
            for idx, gen in enumerate(generators):
                if idx > 0:
                    self.visit(gen.iter)
                self._extract_target_names(gen.target, comp_scope)
                for if_expr in gen.ifs:
                    self.visit(if_expr)
            visit_elts_fn()
        finally:
            self._comp_depth -= 1
            self._pop_scope()

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
            self._bind_name_in_current_scope(node.target.id)
            if self._comp_depth > 0:
                target_idx = max(0, len(self.scope_stack) - 1 - self._comp_depth)
                self.scope_stack[target_idx].add(node.target.id)
                self.deleted_stack[target_idx].discard(node.target.id)
                if target_idx < len(self.scope_future_locals):
                    self.scope_future_locals[target_idx].discard(node.target.id)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            if self.deleted_stack and node.id in self.deleted_stack[-1]:
                self._record_undef(node.id, node, f"Variable '{node.id}' referenced after 'del {node.id}' without re-binding.")
            elif self.scope_future_locals and node.id in self.scope_future_locals[-1]:
                self._record_undef(node.id, node, f"Local variable '{node.id}' referenced before assignment (UnboundLocalError).")
            elif node.id not in self._current_visible_names():
                self._record_undef(node.id, node, f"Undefined name '{node.id}' referenced without import or local binding.")
        self.generic_visit(node)

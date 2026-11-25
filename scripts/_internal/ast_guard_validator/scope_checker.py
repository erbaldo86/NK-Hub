"""Controllo deterministico integrita scope lessicale, branch del e binding global/nonlocal."""

from __future__ import annotations

import ast
import builtins
from typing import Any, List, Set

from _internal.ast_guard_validator.models import GuardViolation, ViolationType
from _internal.ast_guard_validator.scope_bindings import (
    collect_func_local_bindings,
    extract_deleted_names,
    extract_pattern_bindings,  # noqa: F401
    extract_target_names,
)
from _internal.ast_guard_validator.scope_branch_helpers import (
    bind_name_with_shared_decls,
    collect_module_global_bindings,
    push_scope_frames,
    register_shared_decl_in_scope,
    visit_comprehension_common_impl,
    visit_func_annotations_impl,
    visit_if_with_branch_merge,
    visit_match_impl,
    visit_named_expr_impl,
    visit_type_alias_impl,
)

MODULE_DUNDERS: Set[str] = {
    "__name__", "__doc__", "__file__", "__package__", "__loader__",
    "__spec__", "__annotations__", "__builtins__", "__cached__",
}


class ScopeIntegrityChecker(ast.NodeVisitor):
    """Verifica che ogni variabile in lettura sia definita, non cancellata e non UnboundLocal."""

    def __init__(self, global_names: Set[str]) -> None:
        self.global_names = set(global_names) | MODULE_DUNDERS
        self.builtins_set = set(dir(builtins))
        self.scope_stack: List[Set[str]] = [set(self.global_names)]
        self.deleted_stack: List[Set[str]] = [set()]
        self.scope_is_class: List[bool] = [False]
        self.scope_all_bindings: List[Set[str]] = [set(self.global_names)]
        self.scope_future_locals: List[Set[str]] = [set()]
        self.scope_global_decls: List[Set[str]] = [set()]
        self.scope_nonlocal_decls: List[Set[str]] = [set()]
        self._comp_depth: int = 0
        self._has_future_annotations: bool = False
        self.violations: List[GuardViolation] = []

    def visit_Module(self, node: ast.Module) -> None:
        self.scope_all_bindings[0].update(collect_module_global_bindings(node))
        self.generic_visit(node)

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
        bind_name_with_shared_decls(self, name)

    def _bind_target_names_in_current_scope(self, target_node: ast.AST) -> None:
        bound: Set[str] = set()
        self._extract_target_names(target_node, bound)
        for b_name in bound:
            self._bind_name_in_current_scope(b_name)

    def _visit_and_bind_target(self, target_node: ast.AST) -> None:
        if isinstance(target_node, (ast.Subscript, ast.Attribute)):
            self.visit(target_node)
        elif isinstance(target_node, (ast.Tuple, ast.List)):
            for elt in target_node.elts:
                self._visit_and_bind_target(elt)
        elif isinstance(target_node, ast.Starred):
            self._visit_and_bind_target(target_node.value)
        else:
            self._bind_target_names_in_current_scope(target_node)

    def _visit_and_delete_target(self, target_node: ast.AST) -> None:
        if isinstance(target_node, (ast.Subscript, ast.Attribute)):
            self.visit(target_node)
        elif isinstance(target_node, (ast.Tuple, ast.List)):
            for elt in target_node.elts:
                self._visit_and_delete_target(elt)
        else:
            deleted_names: Set[str] = set()
            self._extract_deleted_names(target_node, deleted_names)
            for d_name in deleted_names:
                self.scope_stack[-1].discard(d_name)
                self.deleted_stack[-1].add(d_name)

    def _extract_deleted_names(self, node: ast.AST, out: Set[str]) -> None:
        extract_deleted_names(node, out)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._visit_and_delete_target(target)

    def visit_If(self, node: ast.If) -> None:
        visit_if_with_branch_merge(self, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for t in node.targets:
            self._visit_and_bind_target(t)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.annotation and not self._has_future_annotations:
            self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self._visit_and_bind_target(node.target)

    def _record_undef(self, sym: str, node: ast.AST, message: str) -> None:
        self.violations.append(GuardViolation(
            violation_type=ViolationType.UNDEFINED_NAME, symbol_name=sym,
            line_number=node.lineno, column=node.col_offset, message=message,
        ))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            is_future = bool(self.scope_future_locals and node.target.id in self.scope_future_locals[-1])
            if (
                node.target.id in self.deleted_stack[-1]
                or is_future
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
        self._visit_and_bind_target(node.target)
        for stmt in (*node.body, *node.orelse):
            self.visit(stmt)

    def visit_For(self, node: ast.For) -> None:
        self._visit_for_common(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_for_common(node)

    def _visit_with_common(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._visit_and_bind_target(item.optional_vars)
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
        global_decls: Set[str] | None = None, nonlocal_decls: Set[str] | None = None,
    ) -> None:
        push_scope_frames(
            self,
            local_scope,
            is_class=is_class,
            all_bindings=all_bindings,
            future_locals=future_locals,
            global_decls=global_decls,
            nonlocal_decls=nonlocal_decls,
        )

    def _pop_scope(self) -> None:
        self.scope_nonlocal_decls.pop()
        self.scope_global_decls.pop()
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

    def _visit_func_annotations(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, type_params: Set[str]
    ) -> None:
        visit_func_annotations_impl(self, node, type_params)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in (*node.args.defaults, *getattr(node.args, "kw_defaults", [])):
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
        g_decls: Set[str] = set()
        nl_decls: Set[str] = set()
        collect_func_local_bindings(list(node.body), set(), declared_globals=g_decls, declared_nonlocals=nl_decls)
        self._push_scope(local_scope, is_class=True, global_decls=g_decls, nonlocal_decls=nl_decls)
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
        type_param_names: Set[str] = {tp.name for tp in getattr(node, "type_params", []) if hasattr(tp, "name")}
        self._visit_func_annotations(node, type_param_names)
        self._bind_name_in_current_scope(node.name)
        local_scope: Set[str] = set(type_param_names)
        self._collect_signature_params(node.args, local_scope)
        all_func_bindings: Set[str] = set(local_scope)
        declared_shared: Set[str] = set()
        g_decls: Set[str] = set()
        nl_decls: Set[str] = set()
        collect_func_local_bindings(
            node.body, all_func_bindings, declared_shared,
            declared_globals=g_decls, declared_nonlocals=nl_decls,
        )
        local_scope.update(declared_shared)
        self._push_scope(
            local_scope, all_bindings=all_func_bindings,
            future_locals=all_func_bindings - local_scope,
            global_decls=g_decls, nonlocal_decls=nl_decls,
        )
        try:
            for child in node.body:
                self.visit(child)
        finally:
            self._pop_scope()

    def visit_Global(self, node: ast.Global) -> None:
        register_shared_decl_in_scope(self, node.names, is_global=True)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        register_shared_decl_in_scope(self, node.names, is_global=False)

    def _extract_target_names(self, node: ast.AST, target_set: Set[str]) -> None:
        extract_target_names(node, target_set)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._bind_name_in_current_scope(name)
            self._bind_name_in_current_scope(name.split(".")[0])

    def _track_future_annotations(self, node: ast.ImportFrom) -> None:
        if node.module == "__future__" and any(alias.name == "annotations" for alias in node.names):
            self._has_future_annotations = True

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._track_future_annotations(node)
        for alias in node.names:
            self._bind_name_in_current_scope(alias.asname or alias.name)

    def visit_Match(self, node: Any) -> None:
        visit_match_impl(self, node)

    def visit_TypeAlias(self, node: Any) -> None:
        visit_type_alias_impl(self, node)

    def _visit_comprehension_common(
        self, generators: List[ast.comprehension], visit_elts_fn: Any
    ) -> None:
        visit_comprehension_common_impl(self, generators, visit_elts_fn)

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
        visit_named_expr_impl(self, node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            if self.deleted_stack and node.id in self.deleted_stack[-1]:
                self._record_undef(node.id, node, f"Variable '{node.id}' referenced after 'del {node.id}' without re-binding.")
            elif self.scope_future_locals and node.id in self.scope_future_locals[-1]:
                self._record_undef(node.id, node, f"Local variable '{node.id}' referenced before assignment (UnboundLocalError).")
            elif node.id not in self._current_visible_names():
                self._record_undef(node.id, node, f"Undefined name '{node.id}' referenced without import or local binding.")
        self.generic_visit(node)

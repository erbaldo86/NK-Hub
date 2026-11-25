"""Helper per branch if/del, visibilita global/nonlocal e visitatori composti in ScopeIntegrityChecker."""

from __future__ import annotations

import ast
from typing import Any, List, Optional, Sequence, Set, Tuple

from _internal.ast_guard_validator.scope_bindings import (
    collect_func_local_bindings,
    extract_pattern_bindings,
    extract_target_names,
)


def push_scope_frames(
    checker: Any,
    local_scope: Set[str],
    is_class: bool = False,
    all_bindings: Optional[Set[str]] = None,
    future_locals: Optional[Set[str]] = None,
    global_decls: Optional[Set[str]] = None,
    nonlocal_decls: Optional[Set[str]] = None,
) -> None:
    """Aggiunge un frame completo allo stack scope di ScopeIntegrityChecker."""
    checker.scope_stack.append(local_scope)
    checker.deleted_stack.append(set())
    checker.scope_is_class.append(is_class)
    checker.scope_all_bindings.append(set(local_scope) if all_bindings is None else all_bindings)
    checker.scope_future_locals.append(set() if future_locals is None else future_locals)
    checker.scope_global_decls.append(set() if global_decls is None else global_decls)
    checker.scope_nonlocal_decls.append(set() if nonlocal_decls is None else nonlocal_decls)


def _iter_same_scope_nodes(stmts: Sequence[ast.stmt]) -> List[ast.AST]:
    out: List[ast.AST] = []
    stack: List[ast.AST] = list(stmts)
    while stack:
        cur = stack.pop()
        out.append(cur)
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(cur))
    return out


def _record_import_or_def_assigned(sub: ast.AST, assigned: Set[str]) -> None:
    if isinstance(sub, ast.Import):
        for alias in sub.names:
            aname = alias.asname or alias.name
            assigned.update((aname, aname.split(".")[0]))
    elif isinstance(sub, ast.ImportFrom):
        for alias in sub.names:
            assigned.add(alias.asname or alias.name)
    elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        assigned.add(sub.name)


def _record_assigned_from_stmt(sub: ast.AST, assigned: Set[str]) -> None:
    if isinstance(sub, ast.Assign):
        for t in sub.targets:
            extract_target_names(t, assigned)
    elif isinstance(sub, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        if not isinstance(sub, ast.AnnAssign) or sub.value is not None:
            extract_target_names(sub.target, assigned)
    elif isinstance(sub, (ast.For, ast.AsyncFor)):
        extract_target_names(sub.target, assigned)
    elif isinstance(sub, (ast.With, ast.AsyncWith)):
        for item in sub.items:
            if item.optional_vars:
                extract_target_names(item.optional_vars, assigned)
    elif isinstance(sub, ast.ExceptHandler) and sub.name:
        assigned.add(sub.name)
    else:
        _record_import_or_def_assigned(sub, assigned)


def collect_module_global_bindings(tree: ast.AST) -> Set[str]:
    """Individua nomi dichiarati global e assegnati in funzioni/classi per visibilita cross-func."""
    globals_bound: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        g_decls: Set[str] = set()
        collect_func_local_bindings(list(node.body), set(), declared_globals=g_decls)
        if not g_decls:
            continue
        strictly_assigned: Set[str] = set()
        for sub in _iter_same_scope_nodes(node.body):
            _record_assigned_from_stmt(sub, strictly_assigned)
        globals_bound.update(g_decls & strictly_assigned)
    return globals_bound


def register_shared_decl_in_scope(
    checker: Any, names: Sequence[str], is_global: bool
) -> None:
    """Registra dichiarazioni global o nonlocal nel frame corrente."""
    decls = checker.scope_global_decls if is_global else checker.scope_nonlocal_decls
    for name in names:
        if decls:
            decls[-1].add(name)
        checker.scope_stack[-1].add(name)
        checker.deleted_stack[-1].discard(name)
        if checker.scope_future_locals:
            checker.scope_future_locals[-1].discard(name)


def bind_name_with_shared_decls(checker: Any, name: str) -> None:
    """Registra il binding di name nello scope corrente e nei frame global/nonlocal dichiarati."""
    checker.scope_stack[-1].add(name)
    checker.deleted_stack[-1].discard(name)
    if checker.scope_future_locals:
        checker.scope_future_locals[-1].discard(name)
    if len(checker.scope_stack) <= 1:
        return
    if checker.scope_global_decls and name in checker.scope_global_decls[-1]:
        checker.scope_stack[0].add(name)
        checker.deleted_stack[0].discard(name)
        checker.scope_all_bindings[0].add(name)
    elif checker.scope_nonlocal_decls and name in checker.scope_nonlocal_decls[-1]:
        for idx in range(len(checker.scope_stack) - 2, 0, -1):
            if checker.scope_is_class[idx]:
                continue
            if (
                name in checker.scope_all_bindings[idx]
                or name in checker.scope_stack[idx]
                or idx == 1
            ):
                checker.scope_stack[idx].add(name)
                checker.deleted_stack[idx].discard(name)
                checker.scope_future_locals[idx].discard(name)
                break


def visit_func_annotations_impl(
    checker: Any,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    type_params: Set[str],
) -> None:
    """Visita le annotazioni di parametri e ritorno se __future__.annotations non e attivo."""
    if checker._has_future_annotations:
        return
    if type_params:
        checker._push_scope(set(type_params))
    try:
        for arg in (
            getattr(node.args, "posonlyargs", []) + node.args.args + node.args.kwonlyargs
        ):
            if arg.annotation is not None:
                checker.visit(arg.annotation)
        if node.args.vararg and node.args.vararg.annotation is not None:
            checker.visit(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation is not None:
            checker.visit(node.args.kwarg.annotation)
        if node.returns is not None:
            checker.visit(node.returns)
    finally:
        if type_params:
            checker._pop_scope()


def stmts_terminate(stmts: Sequence[ast.stmt]) -> bool:
    """True se il blocco di statement termina sempre il controllo lineare."""
    for stmt in stmts:
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            return True
        if isinstance(stmt, ast.If) and stmt.orelse:
            if stmts_terminate(stmt.body) and stmts_terminate(stmt.orelse):
                return True
        if type(stmt).__name__ in ("Try", "TryStar"):
            handlers = getattr(stmt, "handlers", ())
            finalbody = getattr(stmt, "finalbody", ())
            if finalbody and stmts_terminate(finalbody):
                return True
            if (
                (stmts_terminate(getattr(stmt, "body", ())) or stmts_terminate(getattr(stmt, "orelse", ())))
                and handlers
                and all(stmts_terminate(h.body) for h in handlers)
            ):
                return True
    return False


def _snapshot_scope_frames(checker: Any) -> Tuple[List[Set[str]], List[Set[str]], List[Set[str]]]:
    return (
        [set(s) for s in checker.scope_stack],
        [set(d) for d in checker.deleted_stack],
        [set(f) for f in checker.scope_future_locals],
    )


def _restore_scope_frames(
    checker: Any, snap: Tuple[List[Set[str]], List[Set[str]], List[Set[str]]]
) -> None:
    scopes, deleted, futures = snap
    checker.scope_stack = [set(s) for s in scopes]
    checker.deleted_stack = [set(d) for d in deleted]
    checker.scope_future_locals = [set(f) for f in futures]


def visit_if_with_branch_merge(checker: Any, node: ast.If) -> None:
    """Visita un nodo ast.If isolando binding e cancellazioni del tra rami if/else."""
    checker.visit(node.test)
    if not checker.scope_stack:
        for stmt in (*node.body, *node.orelse):
            checker.visit(stmt)
        return
    pre_snap = _snapshot_scope_frames(checker)
    for stmt in node.body:
        checker.visit(stmt)
    body_snap = _snapshot_scope_frames(checker)
    body_term = stmts_terminate(node.body)
    _restore_scope_frames(checker, pre_snap)
    for stmt in node.orelse:
        checker.visit(stmt)
    else_snap = _snapshot_scope_frames(checker)
    else_term = stmts_terminate(node.orelse) if node.orelse else False
    if body_term and not else_term:
        _restore_scope_frames(checker, else_snap)
        return
    if else_term and not body_term:
        _restore_scope_frames(checker, body_snap)
        return
    b_scopes, b_dels, b_futs = body_snap
    e_scopes, e_dels, e_futs = else_snap
    for idx in range(min(len(b_scopes), len(e_scopes))):
        merged_del = b_dels[idx] & e_dels[idx]
        checker.deleted_stack[idx] = merged_del
        checker.scope_stack[idx] = (b_scopes[idx] | e_scopes[idx]) - merged_del
        checker.scope_future_locals[idx] = b_futs[idx] & e_futs[idx]


def visit_match_impl(checker: Any, node: Any) -> None:
    """Visita pattern e body di match/case Python 3.10+ nello scope corrente."""
    checker.visit(node.subject)
    for case in node.cases:
        pattern_bindings: Set[str] = set()
        extract_pattern_bindings(case.pattern, pattern_bindings)
        for pb in pattern_bindings:
            checker._bind_name_in_current_scope(pb)
        if case.guard:
            checker.visit(case.guard)
        for stmt in case.body:
            checker.visit(stmt)


def visit_type_alias_impl(checker: Any, node: Any) -> None:
    """Registra i type alias PEP 695 e relativi type_params."""
    if hasattr(node, "name"):
        if isinstance(node.name, ast.Name):
            checker._bind_name_in_current_scope(node.name.id)
        elif isinstance(node.name, str):
            checker._bind_name_in_current_scope(node.name)
    for tp in getattr(node, "type_params", []):
        if hasattr(tp, "name"):
            checker._bind_name_in_current_scope(tp.name)
    if hasattr(node, "value"):
        checker.visit(node.value)


def visit_comprehension_common_impl(
    checker: Any, generators: List[ast.comprehension], visit_elts_fn: Any
) -> None:
    """Gestisce lo scope isolato di comprehension e generator expression."""
    if generators:
        checker.visit(generators[0].iter)
    comp_scope: Set[str] = set()
    checker._push_scope(comp_scope)
    checker._comp_depth += 1
    try:
        for idx, gen in enumerate(generators):
            if idx > 0:
                checker.visit(gen.iter)
            extract_target_names(gen.target, comp_scope)
            for if_expr in gen.ifs:
                checker.visit(if_expr)
        visit_elts_fn()
    finally:
        checker._comp_depth -= 1
        checker._pop_scope()


def visit_named_expr_impl(checker: Any, node: ast.NamedExpr) -> None:
    """Gestisce il walrus operator propagando il binding fuori dalle comprehension."""
    checker.visit(node.value)
    if not isinstance(node.target, ast.Name):
        return
    name = node.target.id
    checker._bind_name_in_current_scope(name)
    if checker._comp_depth > 0:
        target_idx = max(0, len(checker.scope_stack) - 1 - checker._comp_depth)
        checker.scope_stack[target_idx].add(name)
        checker.deleted_stack[target_idx].discard(name)
        if target_idx < len(checker.scope_future_locals):
            checker.scope_future_locals[target_idx].discard(name)
        if (
            checker.scope_global_decls
            and target_idx < len(checker.scope_global_decls)
            and name in checker.scope_global_decls[target_idx]
        ):
            checker.scope_stack[0].add(name)
            checker.deleted_stack[0].discard(name)
            checker.scope_all_bindings[0].add(name)

"""Helper pure-AST per estrazione binding e pattern in ScopeIntegrityChecker."""

from __future__ import annotations

import ast
from typing import Any, List, Optional, Set


def extract_deleted_names(node: ast.AST, out: Set[str]) -> None:
    """Estrae i nomi semplici destinati a cancellazione tramite del."""
    if isinstance(node, ast.Name):
        out.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            extract_deleted_names(elt, out)


def extract_target_names(node: ast.AST, target_set: Set[str]) -> None:
    """Estrae i nomi assegnati da target singoli, tuple, liste o starred."""
    if isinstance(node, ast.Name):
        target_set.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            extract_target_names(elt, target_set)
    elif isinstance(node, ast.Starred):
        extract_target_names(node.value, target_set)


def extract_pattern_bindings(pattern: Any, bindings: Set[str]) -> None:
    """Estrae i nomi associati nei pattern Python 3.10+ match/case."""
    if pattern is None:
        return
    p_type = type(pattern).__name__

    if p_type == "MatchAs":
        if getattr(pattern, "name", None):
            bindings.add(pattern.name)
        if getattr(pattern, "pattern", None):
            extract_pattern_bindings(pattern.pattern, bindings)
    elif p_type == "MatchStar":
        if getattr(pattern, "name", None):
            bindings.add(pattern.name)
    elif p_type == "MatchMapping":
        for p in getattr(pattern, "patterns", []):
            extract_pattern_bindings(p, bindings)
        if getattr(pattern, "rest", None):
            bindings.add(pattern.rest)
    elif p_type in ("MatchClass", "MatchSequence", "MatchOr"):
        for p in getattr(pattern, "patterns", []):
            extract_pattern_bindings(p, bindings)
        if p_type == "MatchClass":
            for p in getattr(pattern, "kwd_patterns", []):
                extract_pattern_bindings(p, bindings)


def collect_func_local_bindings(
    nodes: List[ast.stmt],
    local_scope: Set[str],
    declared_shared: Optional[Set[str]] = None,
) -> None:
    """Raccoglie i simboli locali della funzione senza scendere in funzioni o classi annidate."""
    stack: List[ast.AST] = list(nodes)
    while stack:
        child = stack.pop()
        if isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            local_scope.add(child.name)
            continue
        if isinstance(
            child,
            (
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
                ast.GeneratorExp,
                ast.DictComp,
            ),
        ):
            continue
        if isinstance(child, ast.Assign):
            for t in child.targets:
                extract_target_names(t, local_scope)
        elif isinstance(child, (ast.AnnAssign, ast.AugAssign)):
            extract_target_names(child.target, local_scope)
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            extract_target_names(child.target, local_scope)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            local_scope.add(child.name)
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            for item in child.items:
                if item.optional_vars:
                    extract_target_names(item.optional_vars, local_scope)
        elif isinstance(child, ast.Import):
            for alias in child.names:
                name = alias.asname or alias.name
                local_scope.add(name)
                local_scope.add(name.split(".")[0])
        elif isinstance(child, ast.ImportFrom):
            for alias in child.names:
                local_scope.add(alias.asname or alias.name)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            for name in child.names:
                local_scope.add(name)
                if declared_shared is not None:
                    declared_shared.add(name)
        stack.extend(ast.iter_child_nodes(child))

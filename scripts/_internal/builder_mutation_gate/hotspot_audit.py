# -*- coding: utf-8 -*-
"""Scanner AST di funzioni hotspot e utilita di parsing per builder_mutation_gate."""

from __future__ import annotations

import ast
from typing import List, Optional, Sequence, Set, Tuple

try:
    from _internal.nk_common.repo_snapshot_cache import get_repo_snapshot_cache
except ImportError:
    get_repo_snapshot_cache = None  # type: ignore[assignment]

_IGNORED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.IfExp, ast.Assert)


def _parse_ast_cached(code: str) -> Optional[ast.Module]:
    """Esegue il parsing AST sfruttando RepoSnapshotCache se disponibile."""
    if get_repo_snapshot_cache is not None:
        tree, syn_err = get_repo_snapshot_cache().parse_source_cached(code)
        if syn_err is not None or not isinstance(tree, ast.Module):
            return None
        return tree
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None
    return parsed if isinstance(parsed, ast.Module) else None


def _decorator_role(stmt: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Estrae il ruolo accessor (@property, setter, deleter, getter) dai decoratori."""
    for dec in stmt.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            return "property"
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter", "getter"):
            return dec.attr
    return ""


def _unique_func_qname(stmt: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str, seen: Set[str]) -> str:
    """Calcola la chiave qualificata univoca disambiguando @property/setter e omonimi."""
    base_qname = f"{prefix}.{stmt.name}" if prefix else stmt.name
    role = _decorator_role(stmt)
    qname = f"{base_qname}[{role}]" if role in ("setter", "deleter") else base_qname
    if qname in seen:
        if role and f"{base_qname}[{role}]" not in seen:
            qname = f"{base_qname}[{role}]"
        else:
            idx = 2
            while f"{qname}#{idx}" in seen:
                idx += 1
            qname = f"{qname}#{idx}"
    seen.add(qname)
    return qname


def _strip_docstring_stmts(body: Sequence[ast.stmt]) -> List[ast.stmt]:
    """Rimuove eventuale docstring iniziale da una lista di statement AST."""
    items = list(body)
    if (
        items
        and isinstance(items[0], ast.Expr)
        and isinstance(items[0].value, ast.Constant)
        and isinstance(items[0].value.value, str)
    ):
        return items[1:]
    return items


def _iter_top_and_class_funcs(tree: ast.AST) -> List[Tuple[str, ast.AST]]:
    """Elenca in ordine deterministico funzioni top-level e metodi di classe."""
    found, seen = [], set()

    def _visit(body: Sequence[ast.stmt], prefix: str) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                _visit(stmt.body, f"{prefix}.{stmt.name}" if prefix else stmt.name)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append((_unique_func_qname(stmt, prefix, seen), stmt))

    if isinstance(tree, ast.Module):
        _visit(tree.body, "")
    return found


def _calc_if_nesting(stmt: ast.If, depth: int) -> int:
    """Calcola la profondita massima in una catena if/elif/else."""
    best, cur = depth + 1, stmt
    while cur is not None:
        best = max(best, _calc_block_nesting(cur.body, depth + 1))
        if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
            cur = cur.orelse[0]
            continue
        if cur.orelse:
            best = max(best, _calc_block_nesting(cur.orelse, depth + 1))
        break
    return best


def _calc_try_or_match_nesting(stmt: ast.stmt, depth: int) -> Optional[int]:
    """Calcola il nesting di blocchi Try/TryStar/Match restituendo None per altri nodi."""
    sname = type(stmt).__name__
    if sname in ("Try", "TryStar"):
        subs = [getattr(stmt, "body", ()), *(h.body for h in getattr(stmt, "handlers", ())), getattr(stmt, "orelse", ()), getattr(stmt, "finalbody", ())]
        return max((_calc_block_nesting(b, depth + 1) for b in subs if b), default=depth + 1)
    if sname == "Match":
        return max((_calc_block_nesting(c.body, depth + 1) for c in getattr(stmt, "cases", ())), default=depth + 1)
    return None


def _calc_stmt_nesting(stmt: ast.stmt, depth: int) -> int:
    """Calcola la profondita di annidamento strutturato di un singolo statement."""
    if isinstance(stmt, _IGNORED_SCOPES):
        return depth
    if isinstance(stmt, ast.If):
        return _calc_if_nesting(stmt, depth)
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
        best = _calc_block_nesting(stmt.body, depth + 1)
        return max(best, _calc_block_nesting(stmt.orelse, depth + 1)) if stmt.orelse else best
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return _calc_block_nesting(stmt.body, depth + 1)
    special = _calc_try_or_match_nesting(stmt, depth)
    return special if special is not None else depth


def _calc_block_nesting(stmts: Sequence[ast.stmt], depth: int) -> int:
    return max((_calc_stmt_nesting(st, depth) for st in stmts), default=depth)


def _calc_cc_and_loc(fn_node: ast.AST) -> Tuple[int, int]:
    """Calcola CC ciclomatica e statement AST eseguibili (LOC) escludendo docstring e sotto-scope."""
    cc, loc = 1, 0
    stack: List[ast.AST] = list(reversed(_strip_docstring_stmts(getattr(fn_node, "body", []))))
    while stack:
        node = stack.pop()
        if isinstance(node, _IGNORED_SCOPES):
            continue
        if isinstance(node, ast.stmt):
            loc += 1
        if isinstance(node, _BRANCH_NODES):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += max(0, len(node.values) - 1)
        elif isinstance(node, ast.comprehension):
            cc += 1 + len(node.ifs)
        elif type(node).__name__ == "match_case":
            cc += 1
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return cc, loc


def _rank_hotspot_nodes(tree: ast.AST) -> List[Tuple[str, ast.AST]]:
    """Seleziona e ordina gli hotspot (CC >= 4 o LOC >= 40) per score decrescente e (lineno, name)."""
    ranked: List[Tuple[int, int, str, ast.AST]] = []
    for qname, fn_node in _iter_top_and_class_funcs(tree):
        cc, loc = _calc_cc_and_loc(fn_node)
        if cc < 4 and loc < 40:
            continue
        nest = _calc_block_nesting(_strip_docstring_stmts(getattr(fn_node, "body", [])), 0)
        ranked.append((-(cc * max(1, nest)), int(getattr(fn_node, "lineno", 1)), qname, fn_node))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(qname, fn_node) for _neg_s, _ln, qname, fn_node in ranked]


def select_hotspot_functions(post_code: str) -> List[str]:
    """Restituisce i nomi qualificati delle funzioni hotspot ordinate per priorita."""
    post_tree = _parse_ast_cached(post_code)
    return [qname for qname, _fn in _rank_hotspot_nodes(post_tree)] if post_tree is not None else []

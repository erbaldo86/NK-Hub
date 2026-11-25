# -*- coding: utf-8 -*-
"""Regole pure AST per metriche differenziali di complessita, nesting, except silenziosi e test tautologici."""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field


class QualityDiffViolation(BaseModel):
    """Singola violazione del ratchet qualitativo differenziale o del gate frontend."""

    model_config = ConfigDict(strict=True, frozen=True)

    rule_id: str = Field(description="Identificativo canonico della regola")
    file_path: str = Field(description="Percorso del file interessato")
    symbol_name: Optional[str] = Field(default=None, description="Nome qualificato della funzione")
    line_number: Optional[int] = Field(default=None, description="Riga 1-indexed")
    severity: str = Field(default="MEDIUM", description="HIGH, MEDIUM o LOW")
    message: str = Field(description="Diagnosi della violazione")


_NESTED_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_BRANCH_NODE_TYPES = (
    ast.If, ast.For, ast.AsyncFor, ast.While,
    ast.ExceptHandler, ast.With, ast.AsyncWith, ast.IfExp, ast.Assert,
)


def _is_wildcard_match_case(node: ast.AST) -> bool:
    """Restituisce True se il nodo match_case corrisponde a 'case _:' senza guard."""
    if getattr(node, "guard", None) is not None:
        return False
    pat = getattr(node, "pattern", None)
    return (
        type(pat).__name__ == "MatchAs"
        and getattr(pat, "pattern", None) is None
        and getattr(pat, "name", None) is None
    )


def compute_cyclomatic_complexity(fn_node: ast.AST) -> int:
    """Calcola la complessita ciclomatica pure-AST escludendo funzioni/classi annidate."""
    cc = 1
    stack: List[ast.AST] = list(getattr(fn_node, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPE_TYPES):
            continue
        if isinstance(node, _BRANCH_NODE_TYPES):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += max(0, len(node.values) - 1)
        elif isinstance(node, ast.comprehension):
            cc += 1 + len(node.ifs)
        elif type(node).__name__ == "match_case" and not _is_wildcard_match_case(node):
            cc += 1
        stack.extend(ast.iter_child_nodes(node))
    return cc


def _if_chain_max_depth(stmt: ast.If, depth: int) -> int:
    """Calcola la profondita massima in catene if/elif/else senza inflazionare gli elif."""
    best = depth + 1
    cur_if: Optional[ast.If] = stmt
    while cur_if is not None:
        best = max(best, _stmt_list_max_depth(cur_if.body, depth + 1))
        if len(cur_if.orelse) == 1 and isinstance(cur_if.orelse[0], ast.If):
            cur_if = cur_if.orelse[0]
        else:
            if cur_if.orelse:
                best = max(best, _stmt_list_max_depth(cur_if.orelse, depth + 1))
            cur_if = None
    return best


def _try_max_depth(stmt: ast.AST, depth: int) -> int:
    """Calcola la profondita massima nei rami body/except/else/finally di un Try."""
    best = _stmt_list_max_depth(getattr(stmt, "body", ()), depth + 1)
    for handler in getattr(stmt, "handlers", ()):
        best = max(best, _stmt_list_max_depth(handler.body, depth + 1))
    for attr in ("orelse", "finalbody"):
        sub = getattr(stmt, attr, ())
        if sub:
            best = max(best, _stmt_list_max_depth(sub, depth + 1))
    return best


def _compound_stmt_max_depth(stmt: ast.stmt, depth: int) -> int:
    """Restituisce la profondita massima per singolo statement composto."""
    if isinstance(stmt, _NESTED_SCOPE_TYPES):
        return depth
    if isinstance(stmt, ast.If):
        return _if_chain_max_depth(stmt, depth)
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
        best = _stmt_list_max_depth(stmt.body, depth + 1)
        return max(best, _stmt_list_max_depth(stmt.orelse, depth + 1)) if stmt.orelse else best
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return _stmt_list_max_depth(stmt.body, depth + 1)
    stmt_name = type(stmt).__name__
    if stmt_name in ("Try", "TryStar"):
        return _try_max_depth(stmt, depth)
    if stmt_name == "Match":
        best = depth + 1
        for case in getattr(stmt, "cases", ()):
            best = max(best, _stmt_list_max_depth(case.body, depth + 1))
        return best
    return depth


def _stmt_list_max_depth(stmts: Sequence[ast.stmt], depth: int) -> int:
    """Calcola la profondita massima di annidamento di controllo in un blocco."""
    best = depth
    for stmt in stmts:
        best = max(best, _compound_stmt_max_depth(stmt, depth))
    return best


def compute_max_nesting(fn_node: ast.AST) -> int:
    """Restituisce la profondita massima di nesting strutturato dentro fn_node.body."""
    return _stmt_list_max_depth(getattr(fn_node, "body", ()), 0)


def _is_broad_exception_type(exc_type: Optional[ast.expr]) -> bool:
    """Verifica se l'handler cattura qualsiasi eccezione (bare, Exception, BaseException)."""
    if exc_type is None:
        return True
    if isinstance(exc_type, ast.Name) and exc_type.id in ("Exception", "BaseException"):
        return True
    if isinstance(exc_type, ast.Tuple):
        return any(_is_broad_exception_type(elt) for elt in exc_type.elts)
    return False


def _is_noop_body(stmts: Sequence[ast.stmt]) -> bool:
    """Restituisce True se il blocco contiene solo pass, Ellipsis o docstring."""
    if not stmts:
        return True
    for st in stmts:
        if isinstance(st, ast.Pass):
            continue
        if (
            isinstance(st, ast.Expr)
            and isinstance(st.value, ast.Constant)
            and (st.value.value is Ellipsis or isinstance(st.value.value, str))
        ):
            continue
        return False
    return True


def find_silent_except_handlers(fn_node: ast.AST) -> List[int]:
    """Individua i numeri di riga di handler except silenziosi dentro la funzione."""
    lines: List[int] = []
    stack: List[ast.AST] = list(getattr(fn_node, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPE_TYPES):
            continue
        if isinstance(node, ast.ExceptHandler):
            if _is_broad_exception_type(node.type) and _is_noop_body(node.body):
                lines.append(getattr(node, "lineno", 1))
        stack.extend(ast.iter_child_nodes(node))
    return sorted(lines)


_PURE_BINOPS: Dict[type, Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
}
_PURE_DIV_MOD_OPS: Dict[type, Any] = {
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}
_PURE_CMP_OPS: Tuple[Tuple[type, Any], ...] = (
    (ast.Eq, lambda a, b: a == b), (ast.NotEq, lambda a, b: a != b),
    (ast.Lt, lambda a, b: a < b), (ast.LtE, lambda a, b: a <= b),
    (ast.Gt, lambda a, b: a > b), (ast.GtE, lambda a, b: a >= b),
    (ast.Is, lambda a, b: a is b), (ast.IsNot, lambda a, b: a is not b),
    (ast.In, lambda a, b: a in b), (ast.NotIn, lambda a, b: a not in b),
)


def _eval_pure_const_binop(node: ast.BinOp) -> Tuple[bool, Any]:
    ok_l, lval = _eval_pure_const_node(node.left)
    ok_r, rval = _eval_pure_const_node(node.right)
    if not (ok_l and ok_r):
        return False, None
    op_type = type(node.op)
    try:
        if op_type in _PURE_BINOPS:
            return True, _PURE_BINOPS[op_type](lval, rval)
        if op_type in _PURE_DIV_MOD_OPS and rval != 0:
            return True, _PURE_DIV_MOD_OPS[op_type](lval, rval)
    except TypeError:
        return False, None
    return False, None


def _eval_pure_const_compare(node: ast.Compare) -> Tuple[bool, Any]:
    ok_l, cur_l = _eval_pure_const_node(node.left)
    if not ok_l:
        return False, None
    all_matched = True
    for op, comp in zip(node.ops, node.comparators):
        ok_r, cur_r = _eval_pure_const_node(comp)
        if not ok_r:
            return False, None
        fn = next((f for cls, f in _PURE_CMP_OPS if isinstance(op, cls)), None)
        if fn is None:
            return False, None
        try:
            if not bool(fn(cur_l, cur_r)):
                all_matched = False
        except TypeError:
            return False, None
        cur_l = cur_r
    return True, all_matched


def _eval_pure_const_unary(node: ast.UnaryOp) -> Tuple[bool, Any]:
    ok_o, oval = _eval_pure_const_node(node.operand)
    if not ok_o:
        return False, None
    if isinstance(node.op, ast.Not):
        return True, not bool(oval)
    if isinstance(oval, (int, float)) and not isinstance(oval, bool):
        if isinstance(node.op, ast.USub):
            return True, -oval
        if isinstance(node.op, ast.UAdd):
            return True, +oval
    return False, None


def _eval_pure_const_boolop(node: ast.BoolOp) -> Tuple[bool, Any]:
    vals = [_eval_pure_const_node(v) for v in node.values]
    if not all(ok for ok, _ in vals):
        return False, None
    if isinstance(node.op, ast.And):
        return True, all(bool(v) for _, v in vals)
    if isinstance(node.op, ast.Or):
        return True, any(bool(v) for _, v in vals)
    return False, None


def _eval_pure_const_seq(node: ast.Tuple | ast.List) -> Tuple[bool, Any]:
    items = [_eval_pure_const_node(e) for e in node.elts]
    if not all(ok for ok, _ in items):
        return False, None
    seq = [v for _, v in items]
    return True, tuple(seq) if isinstance(node, ast.Tuple) else seq


def _eval_pure_const_node(node: ast.AST) -> Tuple[bool, Any]:
    """Valuta espressioni pure costanti (incluso 1 + 1 == 2) senza side-effect."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.UnaryOp):
        return _eval_pure_const_unary(node)
    if isinstance(node, ast.BinOp):
        return _eval_pure_const_binop(node)
    if isinstance(node, ast.Compare):
        return _eval_pure_const_compare(node)
    if isinstance(node, ast.BoolOp):
        return _eval_pure_const_boolop(node)
    if isinstance(node, (ast.Tuple, ast.List)):
        return _eval_pure_const_seq(node)
    return False, None


def _is_tautological_assert(node: ast.Assert) -> bool:
    """Riconosce asserzioni sempre vere (assert True, assert 1 + 1 == 2, assert x == x)."""
    test = node.test
    ok_const, const_val = _eval_pure_const_node(test)
    if ok_const:
        return bool(const_val)
    if (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and len(test.comparators) == 1
        and isinstance(test.ops[0], (ast.Eq, ast.Is, ast.LtE, ast.GtE))
    ):
        left_dump = ast.dump(test.left, include_attributes=False)
        right_dump = ast.dump(test.comparators[0], include_attributes=False)
        return left_dump == right_dump
    return False


def _is_test_verification_call(call_node: ast.Call) -> bool:
    """Riconosce chiamate di verifica test (pytest.raises, assert*, check_*, verify_*)."""
    target = call_node.func
    name = ""
    if isinstance(target, ast.Name):
        name = target.id
    elif isinstance(target, ast.Attribute):
        name = target.attr
    if not name:
        return False
    return name in ("raises", "warns", "fail", "assertRaises") or name.startswith(
        ("assert", "_assert", "check_", "verify_")
    )


def find_test_assert_issues(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef, is_test_file: bool
) -> List[Tuple[str, int, str]]:
    """Rileva asserzioni tautologiche o funzioni di test prive di qualunque verifica."""
    if not is_test_file or not fn_node.name.startswith("test_"):
        return []
    issues: List[Tuple[str, int, str]] = []
    assert_count = 0
    check_calls = 0
    stack: List[ast.AST] = list(fn_node.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPE_TYPES):
            continue
        if isinstance(node, ast.Assert):
            assert_count += 1
            if _is_tautological_assert(node):
                ln = getattr(node, "lineno", fn_node.lineno)
                issues.append(("QD-TAUTOLOGICAL-ASSERT", ln, f"Tautological assertion in '{fn_node.name}' at line {ln}."))
        elif isinstance(node, ast.Call) and _is_test_verification_call(node):
            check_calls += 1
        stack.extend(ast.iter_child_nodes(node))
    if assert_count == 0 and check_calls == 0:
        issues.append(("QD-ZERO-ASSERT-TEST", fn_node.lineno, f"Test function '{fn_node.name}' has zero assertions or verification calls."))
    return issues


def _metric_decorator_role(stmt: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Estrae il ruolo @property/setter/deleter/getter dai decoratori."""
    for dec in stmt.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            return "property"
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter", "getter"):
            return dec.attr
    return ""


def _resolve_metric_qname(
    stmt: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
    existing: Dict[str, Dict[str, Any]],
) -> str:
    """Calcola chiave metrica univoca disambiguando @property/setter/deleter."""
    base_qname = f"{prefix}.{stmt.name}" if prefix else stmt.name
    role = _metric_decorator_role(stmt)
    qname = f"{base_qname}[{role}]" if role in ("setter", "deleter") else base_qname
    if qname in existing:
        if role and f"{base_qname}[{role}]" not in existing:
            qname = f"{base_qname}[{role}]"
        else:
            qname = f"{qname}@{stmt.lineno}"
    return qname


def extract_function_metrics(
    tree: ast.AST, is_test_file: bool = False
) -> Dict[str, Dict[str, Any]]:
    """Estrae metriche qualitative pure-AST indicizzate per nome qualificato di funzione."""
    metrics: Dict[str, Dict[str, Any]] = {}

    def _visit_block(stmts: Sequence[ast.stmt], prefix: str) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.ClassDef):
                cls_prefix = f"{prefix}.{stmt.name}" if prefix else stmt.name
                _visit_block(stmt.body, cls_prefix)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = _resolve_metric_qname(stmt, prefix, metrics)
                metrics[qname] = {
                    "cc": compute_cyclomatic_complexity(stmt),
                    "nesting": compute_max_nesting(stmt),
                    "silent_except_lines": find_silent_except_handlers(stmt),
                    "test_assert_issues": find_test_assert_issues(stmt, is_test_file),
                    "lineno": stmt.lineno,
                    "body_dump": ast.dump(stmt, include_attributes=False),
                }
                _visit_block(stmt.body, qname)

    _visit_block(getattr(tree, "body", ()), "")
    return metrics

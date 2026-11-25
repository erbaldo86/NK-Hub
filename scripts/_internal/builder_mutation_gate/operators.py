# -*- coding: utf-8 -*-
"""Tabelle operatori AST pure-stdlib e guardie Path/annotazioni per builder_mutation_gate."""

from __future__ import annotations

import ast
from typing import Callable, Dict, List, Optional, Tuple

CMP_FLIPS: Dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

BINOP_FLIPS: Dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
}

AUGOP_FLIPS: Dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
}

OP_ORDER: Tuple[str, ...] = (
    "ComparisonFlip",
    "BoolOpFlip",
    "BinOpFlip",
    "AugAssignFlip",
    "UnaryNotDrop",
    "BoolReturnFlip",
    "ReturnNoneFlip",
    "BoundaryOffByOne",
)

PATH_HINT_TOKENS: Tuple[str, ...] = (
    "path",
    "dir",
    "root",
    "file",
    "folder",
    "base",
    "stage",
    "stg",
    "sandbox",
    "sb",
    "ws",
    "mirror",
    "tmp",
    "temp",
    "cwd",
)

_TYPE_ALIAS_NODE = getattr(ast, "TypeAlias", None)


def is_ignored_scope_node(node: ast.AST) -> bool:
    """True per definizioni annidate e TypeAlias esclusi dalla mutazione locale."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return True
    return _TYPE_ALIAS_NODE is not None and isinstance(node, _TYPE_ALIAS_NODE)


def iter_owned_children(node: ast.AST) -> List[ast.AST]:
    """Restituisce i nodi figli eseguibili escludendo la type annotation di AnnAssign."""
    if isinstance(node, ast.AnnAssign):
        children: List[ast.AST] = [node.target]
        if node.value is not None:
            children.append(node.value)
        return children
    return list(ast.iter_child_nodes(node))


def is_boundary_context(node: ast.AST, parent: Optional[ast.AST]) -> bool:
    """Verifica che la costante int sia un bound in ast.Compare o chiamata range()."""
    if not isinstance(node, ast.Constant):
        return False
    if not isinstance(node.value, int) or isinstance(node.value, bool):
        return False
    if isinstance(parent, ast.Compare):
        return True
    return (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id == "range"
    )


def _is_str_literal_expr(expr: ast.AST) -> bool:
    return isinstance(expr, ast.JoinedStr) or (
        isinstance(expr, ast.Constant) and isinstance(expr.value, str)
    )


def is_path_expr(expr: ast.AST) -> bool:
    """Riconosce espressioni pathlib per evitare mutazioni Path / 'x' -> Path * 'x'."""
    if _is_str_literal_expr(expr):
        return True
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return is_path_expr(expr.left) or is_path_expr(expr.right)
    if isinstance(expr, ast.Call):
        fn_name = expr.func.id if isinstance(expr.func, ast.Name) else getattr(expr.func, "attr", "")
        if fn_name in ("Path", "PurePath", "PosixPath", "WindowsPath", "resolve", "joinpath"):
            return True
    ident = expr.id.lower() if isinstance(expr, ast.Name) else (
        expr.attr.lower() if isinstance(expr, ast.Attribute) else ""
    )
    return any(tok in ident for tok in PATH_HINT_TOKENS)


def is_path_div_binop(node: ast.BinOp) -> bool:
    """Restituisce True quando l'operatore / e usato come join di percorsi Path."""
    return isinstance(node.op, ast.Div) and (is_path_expr(node.left) or is_path_expr(node.right))


def _match_compare(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMP_FLIPS:
        return "ComparisonFlip"
    return None


def _match_boolop(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        return "BoolOpFlip"
    return None


def _match_binop(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if not isinstance(node, ast.BinOp) or type(node.op) not in BINOP_FLIPS:
        return None
    if _is_str_literal_expr(node.left) or is_path_div_binop(node):
        return None
    return "BinOpFlip"


def _match_augassign(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if not isinstance(node, ast.AugAssign) or type(node.op) not in AUGOP_FLIPS:
        return None
    if isinstance(node.op, ast.Add) and _is_str_literal_expr(node.value):
        return None
    if isinstance(node.op, ast.Div) and (is_path_expr(node.target) or is_path_expr(node.value)):
        return None
    return "AugAssignFlip"


def _match_unary(node: ast.AST, parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and parent is not None:
        return "UnaryNotDrop"
    return None


def _match_return(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if not isinstance(node, ast.Return) or node.value is None:
        return None
    if isinstance(node.value, ast.Constant):
        if isinstance(node.value.value, bool):
            return "BoolReturnFlip"
        if node.value.value is None:
            return None
    return "ReturnNoneFlip"


def _match_constant(node: ast.AST, parent: Optional[ast.AST]) -> Optional[str]:
    return "BoundaryOffByOne" if is_boundary_context(node, parent) else None


_NODE_MATCH_TABLE: Dict[type[ast.AST], Callable[[ast.AST, Optional[ast.AST]], Optional[str]]] = {
    ast.Compare: _match_compare,
    ast.BoolOp: _match_boolop,
    ast.BinOp: _match_binop,
    ast.AugAssign: _match_augassign,
    ast.UnaryOp: _match_unary,
    ast.Return: _match_return,
    ast.Constant: _match_constant,
}


def match_operator_for_node(node: ast.AST, parent: Optional[ast.AST]) -> Optional[str]:
    """Classifica il singolo nodo AST tramite tabella di lookup (CC <= 2)."""
    matcher = _NODE_MATCH_TABLE.get(type(node))
    return matcher(node, parent) if matcher is not None else None


def replace_unary_not_child(parent: Optional[ast.AST], target_unary: ast.UnaryOp) -> str:
    """Rimuove ast.Not sostituendo target_unary nel padre con il suo operando."""
    if parent is None:
        return ""
    for field_name, field_val in ast.iter_fields(parent):
        if field_val is target_unary:
            setattr(parent, field_name, target_unary.operand)
            return ast.unparse(target_unary.operand)
        if isinstance(field_val, list):
            for idx, item in enumerate(field_val):
                if item is target_unary:
                    field_val[idx] = target_unary.operand
                    return ast.unparse(target_unary.operand)
    return ""


def _apply_comparison_flip(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Compare):
        node.ops[0] = CMP_FLIPS[type(node.ops[0])]()
    return None


def _apply_boolop_flip(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.BoolOp):
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    return None


def _apply_binop_flip(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.BinOp):
        node.op = BINOP_FLIPS[type(node.op)]()
    return None


def _apply_augassign_flip(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.AugAssign):
        node.op = AUGOP_FLIPS[type(node.op)]()
    return None


def _apply_unary_not_drop(node: ast.AST, parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.UnaryOp):
        replaced = replace_unary_not_child(parent, node)
        return replaced if replaced else None
    return None


def _apply_bool_return_flip(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant):
        node.value = ast.Constant(value=not bool(node.value.value))
    return None


def _apply_return_none_flip(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Return):
        node.value = ast.Constant(value=None)
    return None


def _apply_boundary_off_by_one(node: ast.AST, _parent: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        old_val = int(node.value)
        node.value = old_val + 1 if old_val == 0 else old_val - 1
    return None


_MUTATION_APPLY_TABLE: Dict[str, Callable[[ast.AST, Optional[ast.AST]], Optional[str]]] = {
    "ComparisonFlip": _apply_comparison_flip,
    "BoolOpFlip": _apply_boolop_flip,
    "BinOpFlip": _apply_binop_flip,
    "AugAssignFlip": _apply_augassign_flip,
    "UnaryNotDrop": _apply_unary_not_drop,
    "BoolReturnFlip": _apply_bool_return_flip,
    "ReturnNoneFlip": _apply_return_none_flip,
    "BoundaryOffByOne": _apply_boundary_off_by_one,
}


def apply_node_mutation(
    node: ast.AST, op_name: str, parent: Optional[ast.AST] = None
) -> str:
    """Applica in-place la mutazione tramite tabella di dispatch (CC <= 3, nesting <= 1)."""
    applier = _MUTATION_APPLY_TABLE.get(op_name)
    if applier is None:
        return ast.unparse(node)
    override = applier(node, parent)
    return override if override else ast.unparse(node)

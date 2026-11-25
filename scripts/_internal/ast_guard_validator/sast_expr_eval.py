"""Valutatori costanti pure-AST per confronti, moltiplicazioni stringa e traversal."""

from __future__ import annotations

import ast
import re
from typing import Any, List, Optional, Tuple

from _internal.ast_guard_validator.sast_constants import LITERAL_ENV_PATH_RE

_MAX_STR_REPEAT: int = 4096
_TRUTHY_CAST_SYMS = ("bool", "int", "str", "builtins.bool", "builtins.int", "builtins.str")


def eval_int_or_none(node: Optional[ast.AST]) -> Tuple[bool, Optional[int]]:
    if node is None:
        return True, None
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return True, node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        return True, -node.operand.value
    return False, None


def eval_const_mult_str(checker: Any, node: ast.BinOp) -> Optional[str]:
    """Valuta espressioni stringa moltiplicate per intero costante (es. '.' * 2)."""
    if not isinstance(node.op, ast.Mult):
        return None
    for str_node, count_node in ((node.left, node.right), (node.right, node.left)):
        base_s = checker._eval_const_str_expr(str_node)
        ok_n, count_n = eval_int_or_none(count_node)
        if base_s is not None and ok_n and count_n is not None:
            if count_n <= 0:
                return ""
            if count_n > _MAX_STR_REPEAT or len(base_s) * count_n > _MAX_STR_REPEAT:
                return None
            return base_s * count_n
    return None


def _collapse_joined_str_chunks(checker: Any, node: ast.JoinedStr) -> List[str]:
    chunks: List[str] = []
    acc: List[str] = []
    for part in node.values:
        val_node = part.value if isinstance(part, ast.FormattedValue) else part
        part_s = checker._eval_const_str_expr(val_node)
        if part_s is not None:
            acc.append(part_s)
        else:
            if acc:
                chunks.append("".join(acc))
                acc.clear()
            chunks.append("")
    if acc:
        chunks.append("".join(acc))
    return chunks


def collapse_partial_str_chunks(checker: Any, node: ast.AST) -> List[str]:
    """Raccoglie chunk stringa contigui valutando sotto-espressioni costanti (+, *, f-string)."""
    full_s = checker._eval_const_str_expr(node)
    if full_s is not None:
        return [full_s]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_c = collapse_partial_str_chunks(checker, node.left)
        right_c = collapse_partial_str_chunks(checker, node.right)
        if left_c and right_c and left_c[-1] and right_c[0]:
            return left_c[:-1] + [left_c[-1] + right_c[0]] + right_c[1:]
        return [c for c in (*left_c, *right_c) if c]
    if isinstance(node, ast.JoinedStr):
        return _collapse_joined_str_chunks(checker, node)
    return [""]


def _eval_const_unary(checker: Any, node: ast.UnaryOp) -> Tuple[bool, Any]:
    ok, val = _eval_const_operand(checker, node.operand)
    if not ok:
        return False, None
    if isinstance(node.op, ast.Not):
        return True, not bool(val)
    if isinstance(node.op, ast.USub) and isinstance(val, (int, float)):
        return True, -val
    if isinstance(node.op, ast.UAdd) and isinstance(val, (int, float)):
        return True, +val
    if isinstance(node.op, ast.Invert) and isinstance(val, int) and not isinstance(val, bool):
        return True, ~val
    return False, None


def _eval_const_container(checker: Any, node: ast.AST) -> Tuple[bool, Any]:
    elts = getattr(node, "elts", ())
    vals: List[Any] = []
    for elt in elts:
        ok, v = _eval_const_operand(checker, elt)
        if not ok:
            return False, None
        vals.append(v)
    if isinstance(node, ast.Tuple):
        return True, tuple(vals)
    if isinstance(node, ast.List):
        return True, vals
    try:
        return True, set(vals)
    except TypeError:
        return False, None


def _eval_const_binop(checker: Any, node: ast.BinOp) -> Tuple[bool, Any]:
    const_s = checker._eval_const_str_expr(node)
    if const_s is not None:
        return True, const_s
    ok_l, l_val = _eval_const_operand(checker, node.left)
    ok_r, r_val = _eval_const_operand(checker, node.right)
    if not (ok_l and ok_r and isinstance(l_val, (int, float)) and isinstance(r_val, (int, float))):
        return False, None
    if isinstance(node.op, ast.Add):
        return True, l_val + r_val
    if isinstance(node.op, ast.Sub):
        return True, l_val - r_val
    if isinstance(node.op, ast.Mult):
        return True, l_val * r_val
    return False, None


def _eval_const_operand(checker: Any, node: ast.AST) -> Tuple[bool, Any]:
    """Valuta in modo deterministico un operando costante per confronti statici."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.Name):
        if node.id in getattr(checker, "_const_str_vars", {}):
            return True, checker._const_str_vars[node.id]
        if node.id in getattr(checker, "_const_truthy_vars", {}):
            return True, True
        if node.id in getattr(checker, "_const_falsy_vars", ()):
            return True, False
        return False, None
    if isinstance(node, ast.UnaryOp):
        return _eval_const_unary(checker, node)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return _eval_const_container(checker, node)
    if isinstance(node, ast.BinOp):
        return _eval_const_binop(checker, node)
    return False, None


def _apply_cmp_op(op: ast.cmpop, left: Any, right: Any) -> Tuple[bool, bool]:
    """Applica un operatore ast.cmpop senza side effect."""
    try:
        if isinstance(op, ast.Eq):
            return True, bool(left == right)
        if isinstance(op, ast.NotEq):
            return True, bool(left != right)
        if isinstance(op, ast.Lt):
            return True, bool(left < right)
        if isinstance(op, ast.LtE):
            return True, bool(left <= right)
        if isinstance(op, ast.Gt):
            return True, bool(left > right)
        if isinstance(op, ast.GtE):
            return True, bool(left >= right)
        if isinstance(op, ast.Is):
            return True, bool(left is right)
        if isinstance(op, ast.IsNot):
            return True, bool(left is not right)
        if isinstance(op, ast.In):
            return True, bool(left in right)
        if isinstance(op, ast.NotIn):
            return True, bool(left not in right)
    except TypeError:
        return False, False
    return False, False


def eval_const_compare(checker: Any, node: ast.Compare) -> Tuple[bool, bool]:
    """Valuta un nodo ast.Compare tra soli operandi costanti (es. 1 == 1)."""
    ok_l, cur_left = _eval_const_operand(checker, node.left)
    if not ok_l:
        return False, False
    for op, comp in zip(node.ops, node.comparators):
        ok_r, cur_right = _eval_const_operand(checker, comp)
        if not ok_r:
            return False, False
        ok_cmp, matched = _apply_cmp_op(op, cur_left, cur_right)
        if not ok_cmp:
            return False, False
        if not matched:
            return True, False
        cur_left = cur_right
    return True, True


def _is_truthy_not(checker: Any, operand: ast.AST) -> bool:
    if isinstance(operand, ast.Constant):
        return not bool(operand.value)
    if isinstance(operand, (ast.List, ast.Tuple, ast.Set)):
        return len(operand.elts) == 0
    if isinstance(operand, ast.Dict):
        return len(operand.keys) == 0
    if isinstance(operand, ast.Compare):
        ok_cmp, cmp_val = eval_const_compare(checker, operand)
        return bool(ok_cmp and not cmp_val)
    return False


def _is_truthy_unary(checker: Any, node: ast.UnaryOp) -> bool:
    if isinstance(node.op, ast.Not):
        return _is_truthy_not(checker, node.operand)
    if (
        isinstance(node.op, (ast.USub, ast.UAdd))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        val = -node.operand.value if isinstance(node.op, ast.USub) else +node.operand.value
        return bool(val)
    if (
        isinstance(node.op, ast.Invert)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        return bool(~node.operand.value)
    return False


def _is_truthy_boolop(checker: Any, node: ast.BoolOp) -> bool:
    if isinstance(node.op, ast.Or):
        return any(is_truthy_constant_expr(checker, v) for v in node.values)
    if isinstance(node.op, ast.And):
        return all(is_truthy_constant_expr(checker, v) for v in node.values)
    return False


def _is_truthy_atom_or_call(checker: Any, node: ast.AST) -> Tuple[bool, bool]:
    if isinstance(node, ast.Constant):
        return True, bool(node.value)
    if isinstance(node, ast.Name):
        return True, bool(checker._const_truthy_vars.get(node.id, False))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return True, len(node.elts) > 0
    if isinstance(node, ast.Dict):
        return True, len(node.keys) > 0
    if isinstance(node, ast.JoinedStr):
        s = checker._eval_const_str_expr(node)
        return True, (bool(s) if s is not None else len(node.values) > 0)
    return False, False


def is_truthy_constant_expr(checker: Any, node: ast.AST) -> bool:
    """Determina se un nodo AST e una costante truthy preservando i parametri dinamici."""
    handled, atom_val = _is_truthy_atom_or_call(checker, node)
    if handled:
        return atom_val
    if isinstance(node, ast.Compare):
        ok_cmp, cmp_val = eval_const_compare(checker, node)
        return bool(ok_cmp and cmp_val)
    if isinstance(node, ast.UnaryOp):
        return _is_truthy_unary(checker, node)
    if isinstance(node, ast.BoolOp):
        return _is_truthy_boolop(checker, node)
    if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Constant):
        branch = node.body if bool(node.test.value) else node.orelse
        return is_truthy_constant_expr(checker, branch)
    if isinstance(node, ast.Call) and checker._resolve_symbol_expr(node.func) in _TRUTHY_CAST_SYMS and len(node.args) == 1:
        return is_truthy_constant_expr(checker, node.args[0])
    return False


def _is_falsy_composite_expr(checker: Any, node: ast.AST) -> bool:
    """Verifica BoolOp, IfExp o bool(...) staticamente falsy."""
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return any(is_falsy_constant_expr(checker, v) for v in node.values)
        if isinstance(node.op, ast.Or):
            return all(is_falsy_constant_expr(checker, v) for v in node.values)
    if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Constant):
        branch = node.body if bool(node.test.value) else node.orelse
        return is_falsy_constant_expr(checker, branch)
    if (
        isinstance(node, ast.Call)
        and checker._resolve_symbol_expr(node.func) in ("bool", "builtins.bool")
        and len(node.args) == 1
    ):
        return is_falsy_constant_expr(checker, node.args[0])
    return False


def is_falsy_constant_expr(checker: Any, node: ast.AST) -> bool:
    """Restituisce True SOLO se il nodo AST e staticamente garantito falsy."""
    if isinstance(node, ast.Constant):
        return not bool(node.value)
    if isinstance(node, ast.Name):
        return node.id in getattr(checker, "_const_falsy_vars", ())
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) == 0
    if isinstance(node, ast.Dict):
        return len(node.keys) == 0
    if isinstance(node, ast.Compare):
        ok_cmp, cmp_val = eval_const_compare(checker, node)
        return bool(ok_cmp and not cmp_val)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return is_truthy_constant_expr(checker, node.operand)
    return _is_falsy_composite_expr(checker, node)


def _has_partial_binop_traversal(checker: Any, node: ast.BinOp) -> bool:
    for chunk in collapse_partial_str_chunks(checker, node):
        if (
            "../" in chunk
            or "..\\" in chunk
            or chunk.endswith(("/..", "\\.."))
            or (chunk.strip() == ".." and isinstance(node.op, ast.Mult))
        ):
            return True
    return False


def _has_joined_str_traversal(checker: Any, node: ast.JoinedStr) -> bool:
    pieces: List[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            pieces.append(part.value)
        elif isinstance(part, ast.FormattedValue):
            pieces.append(checker._eval_const_str_expr(part.value) or "")
    raw_parts = "".join(pieces)
    return (
        "../" in raw_parts
        or "..\\" in raw_parts
        or raw_parts.strip() == ".."
        or raw_parts.endswith(("/..", "\\.."))
    )


def has_traversal_in_node(checker: Any, node: ast.AST) -> bool:
    """Verifica se un argomento stringa costante o parziale (+, *, f-string) contiene '..'."""
    full_s = checker._eval_const_str_expr(node)
    if full_s is not None:
        segs = [seg for seg in re.split(r"[\\/]+", full_s.strip()) if seg]
        if ".." in segs:
            return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        return _has_partial_binop_traversal(checker, node)
    if isinstance(node, ast.JoinedStr):
        return _has_joined_str_traversal(checker, node)
    return False


def find_literal_env_token_in_node(checker: Any, node: ast.AST) -> Optional[str]:
    """Individua token env letterali non espansi in costanti o f-string."""
    full_s = checker._eval_const_str_expr(node)
    if full_s is not None:
        m = LITERAL_ENV_PATH_RE.search(full_s)
        return m.group(0) if m else None
    if isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                m = LITERAL_ENV_PATH_RE.search(part.value)
                if m:
                    return m.group(0)
    return None

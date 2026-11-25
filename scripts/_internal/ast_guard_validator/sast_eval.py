"""Valutatori AST simbolici, aliasing e binding per il checker SAST."""

from __future__ import annotations

import ast
from typing import Any, Optional

from _internal.ast_guard_validator.sast_constants import (
    DANGEROUS_MODULES,
    GRANT_SNAPSHOT_NAMES,
)
from _internal.ast_guard_validator.sast_expr_eval import (
    eval_const_mult_str,
    eval_int_or_none,
    find_literal_env_token_in_node,
    has_traversal_in_node,
    is_falsy_constant_expr,
    is_truthy_constant_expr,
)
from _internal.ast_guard_validator.sast_taint_helpers import (
    resolve_name_alias_with_shadow,
    update_sql_taint_for_name,
)


def resolve_symbol_expr(checker: Any, node: ast.AST) -> Optional[str]:
    """Risolve ricorsivamente alias di importazione e assegnazioni dirette semplici."""
    if isinstance(node, ast.NamedExpr):
        return resolve_symbol_expr(checker, node.value)
    if isinstance(node, ast.Name):
        return resolve_name_alias_with_shadow(checker, node)
    if isinstance(node, ast.Attribute):
        base = resolve_symbol_expr(checker, node.value)
        if base:
            return f"{base}.{node.attr}"
    return None


def _clear_extra_bound_state(checker: Any, name: str) -> None:
    """Pulisce falsy_vars e taint SQL nello scope corrente (estratto per CC <= 1)."""
    if hasattr(checker, "_const_falsy_vars"):
        checker._const_falsy_vars.discard(name)
    if hasattr(checker, "_tainted_sql_vars"):
        checker._tainted_sql_vars.pop(name, None)
    if getattr(checker, "_scope_stack", None):
        checker._scope_stack[-1]["sql_taint"].discard(name)


def clear_bound_name_state(checker: Any, name: str) -> None:
    """Rimuove lo stato di aliasing, costanti e taint SQL associato a name."""
    checker._symbol_aliases.pop(name, None)
    checker._imported_aliases.pop(name, None)
    checker._const_str_vars.pop(name, None)
    checker._namespace_vars.discard(name)
    checker._const_truthy_vars.pop(name, None)
    _clear_extra_bound_state(checker, name)


def _bind_truthiness_state(checker: Any, name: str, value_node: ast.AST) -> None:
    """Aggiorna _const_truthy_vars e _const_falsy_vars su espressioni statiche."""
    is_truthy_c = checker._is_truthy_constant_expr(value_node)
    is_falsy_c = is_falsy_constant_expr(checker, value_node)
    falsy_set = getattr(checker, "_const_falsy_vars", None)
    if is_truthy_c:
        checker._const_truthy_vars[name] = True
        if falsy_set is not None:
            falsy_set.discard(name)
    elif is_falsy_c:
        checker._const_truthy_vars.pop(name, None)
        if falsy_set is not None:
            falsy_set.add(name)
    else:
        checker._const_truthy_vars.pop(name, None)
        if falsy_set is not None:
            falsy_set.discard(name)


def bind_value_to_name(checker: Any, name: str, value_node: ast.AST) -> None:
    """Associa alias, costanti stringa/bool, namespace e taint SQL 1-hop al nome."""
    sym = checker._resolve_symbol_expr(value_node)
    const_s = checker._eval_const_str_expr(value_node)
    is_ns = checker._is_namespace_expr(value_node)

    if sym and sym != name:
        checker._symbol_aliases[name] = sym
        checker._imported_aliases.pop(name, None)
    elif sym is None:
        checker._symbol_aliases.pop(name, None)
        checker._imported_aliases.pop(name, None)

    if const_s is not None:
        checker._const_str_vars[name] = const_s
    else:
        checker._const_str_vars.pop(name, None)

    if is_ns:
        checker._namespace_vars.add(name)
    else:
        checker._namespace_vars.discard(name)

    _bind_truthiness_state(checker, name, value_node)
    update_sql_taint_for_name(checker, name, value_node)


def bind_assignment_target(checker: Any, target: ast.AST, value_node: ast.AST) -> None:
    """Propaga il binding SAST su target semplici o tuple/liste scompattate."""
    if isinstance(target, ast.Name):
        bind_value_to_name(checker, target.id, value_node)
    elif (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value_node, (ast.Tuple, ast.List))
        and len(target.elts) == len(value_node.elts)
    ):
        for t_elt, v_elt in zip(target.elts, value_node.elts):
            bind_assignment_target(checker, t_elt, v_elt)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for sub in ast.walk(target):
            if isinstance(sub, ast.Name):
                clear_bound_name_state(checker, sub.id)


def has_reverse_slice_expr(checker: Any, node: ast.AST) -> bool:
    """Rileva qualsiasi espressione con slice invertito [::-1] usata per offuscare simboli."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Slice):
            step = sub.slice.step
            if (
                isinstance(step, ast.UnaryOp)
                and isinstance(step.op, ast.USub)
                and isinstance(step.operand, ast.Constant)
                and step.operand.value == 1
            ) or (isinstance(step, ast.Constant) and step.value == -1):
                return True
        if (
            isinstance(sub, ast.Call)
            and checker._resolve_symbol_expr(sub.func)
            in ("reversed", "builtins.reversed")
        ):
            return True
    return False


def eval_const_str_expr(checker: Any, node: ast.AST) -> Optional[str]:
    """Esegue folding statico di stringhe da costanti, +, *, slice, join, chr e f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in checker._const_str_vars:
        return checker._const_str_vars[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_s = eval_const_str_expr(checker, node.left)
        right_s = eval_const_str_expr(checker, node.right)
        if left_s is not None and right_s is not None:
            return left_s + right_s
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return eval_const_mult_str(checker, node)
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
        base_s = eval_const_str_expr(checker, node.value)
        if base_s is not None:
            ok_l, low = eval_int_or_none(node.slice.lower)
            ok_u, up = eval_int_or_none(node.slice.upper)
            ok_s, st = eval_int_or_none(node.slice.step)
            if ok_l and ok_u and ok_s:
                try:
                    return base_s[slice(low, up, st)]
                except Exception:
                    return None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            val_node = part.value if isinstance(part, ast.FormattedValue) else part
            val_s = eval_const_str_expr(checker, val_node)
            if val_s is None:
                return None
            parts.append(val_s)
        return "".join(parts)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and len(node.args) == 1
    ):
        sep_s = eval_const_str_expr(checker, node.func.value)
        if sep_s is not None:
            arg0 = node.args[0]
            if isinstance(arg0, (ast.List, ast.Tuple, ast.Set)):
                items = []
                for elt in arg0.elts:
                    elt_s = eval_const_str_expr(checker, elt)
                    if elt_s is None:
                        return None
                    items.append(elt_s)
                return sep_s.join(items)
            if (
                isinstance(arg0, ast.Call)
                and checker._resolve_symbol_expr(arg0.func)
                in ("reversed", "builtins.reversed")
                and len(arg0.args) == 1
            ):
                rev_s = eval_const_str_expr(checker, arg0.args[0])
                if rev_s is not None:
                    return sep_s.join(reversed(rev_s))
    if (
        isinstance(node, ast.Call)
        and checker._resolve_symbol_expr(node.func) in ("chr", "builtins.chr")
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, int)
    ):
        try:
            return chr(node.args[0].value)
        except Exception:
            return None
    return None


def is_namespace_expr(checker: Any, node: ast.AST) -> bool:
    """Identifica globals(), locals(), vars(), builtins, __builtins__, sys.modules['builtins'] e alias."""
    if isinstance(node, ast.Name):
        resolved = checker._resolve_symbol_expr(node)
        if (
            node.id in ("__builtins__", "builtins", "__dict__")
            or resolved in ("__builtins__", "builtins", "__dict__")
            or node.id in checker._namespace_vars
        ):
            return True
    if isinstance(node, ast.Call):
        fn_sym = checker._resolve_symbol_expr(node.func)
        if fn_sym in (
            "globals", "locals", "vars",
            "builtins.globals", "builtins.locals", "builtins.vars",
            "__builtins__.globals", "__builtins__.locals", "__builtins__.vars",
        ):
            return True
        if (
            fn_sym in ("getattr", "builtins.getattr", "__builtins__.getattr")
            and len(node.args) >= 2
        ):
            attr_s = checker._eval_const_str_expr(node.args[1])
            if attr_s in ("__builtins__", "builtins", "__dict__", "__globals__"):
                return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("get", "pop", "setdefault")
        and checker._is_sys_modules_expr(node.func.value)
        and node.args
    ):
        mod_k = checker._eval_const_str_expr(node.args[0])
        if mod_k in DANGEROUS_MODULES or checker._has_reverse_slice_expr(node.args[0]):
            return True
    if isinstance(node, ast.Attribute) and node.attr in (
        "__builtins__", "__dict__", "__globals__",
        "f_globals", "f_locals", "f_builtins",
    ):
        return True
    if isinstance(node, ast.Subscript):
        if checker._is_sys_modules_expr(node.value):
            mod_k = checker._eval_const_str_expr(node.slice)
            if mod_k in DANGEROUS_MODULES or checker._has_reverse_slice_expr(node.slice):
                return True
        key_s = checker._eval_const_str_expr(node.slice)
        if key_s in ("__builtins__", "builtins", "__dict__", "__globals__"):
            return True
    return False


def is_grant_or_snapshot_expr(checker: Any, node: ast.AST) -> bool:
    """Identifica espressioni riferite a collezioni grants o snapshots."""
    candidates = [ast.unparse(node).lower().strip()]
    resolved = checker._resolve_symbol_expr(node)
    if resolved:
        candidates.append(resolved.lower().strip())
    for cand in candidates:
        if cand.startswith("self."):
            cand = cand[5:]
        if cand in GRANT_SNAPSHOT_NAMES:
            return True
    return False


__all__ = [
    "bind_assignment_target",
    "bind_value_to_name",
    "clear_bound_name_state",
    "eval_const_str_expr",
    "eval_int_or_none",
    "find_literal_env_token_in_node",
    "has_reverse_slice_expr",
    "has_traversal_in_node",
    "is_falsy_constant_expr",
    "is_grant_or_snapshot_expr",
    "is_namespace_expr",
    "is_truthy_constant_expr",
    "resolve_symbol_expr",
]

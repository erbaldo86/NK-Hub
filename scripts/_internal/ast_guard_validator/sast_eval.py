"""Valutatori AST simbolici e costanti per il checker SAST."""

from __future__ import annotations

import ast
import re
from typing import Any, Optional, Tuple

from _internal.ast_guard_validator.sast_constants import (
    DANGEROUS_MODULES,
    GRANT_SNAPSHOT_NAMES,
    LITERAL_ENV_PATH_RE,
)


def resolve_symbol_expr(checker: Any, node: ast.AST) -> Optional[str]:
    """Risolve ricorsivamente alias di importazione e assegnazioni dirette semplici."""
    if isinstance(node, ast.NamedExpr):
        return resolve_symbol_expr(checker, node.value)
    if isinstance(node, ast.Name):
        cur = node.id
        seen = set()
        for _ in range(8):
            if cur in seen:
                break
            seen.add(cur)
            if cur in checker._symbol_aliases:
                nxt = checker._symbol_aliases[cur]
            elif cur in checker._imported_aliases:
                nxt = checker._imported_aliases[cur]
            else:
                break
            if not nxt or nxt == cur:
                break
            cur = nxt
        return cur
    if isinstance(node, ast.Attribute):
        base = resolve_symbol_expr(checker, node.value)
        if base:
            return f"{base}.{node.attr}"
    return None


def clear_bound_name_state(checker: Any, name: str) -> None:
    checker._symbol_aliases.pop(name, None)
    checker._const_str_vars.pop(name, None)
    checker._namespace_vars.discard(name)
    checker._const_truthy_vars.pop(name, None)


def bind_value_to_name(checker: Any, name: str, value_node: ast.AST) -> None:
    sym = checker._resolve_symbol_expr(value_node)
    const_s = checker._eval_const_str_expr(value_node)
    is_ns = checker._is_namespace_expr(value_node)
    is_truthy_c = isinstance(value_node, ast.Constant) and bool(value_node.value)
    is_falsy_c = isinstance(value_node, ast.Constant) and not bool(value_node.value)

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

    if is_truthy_c:
        checker._const_truthy_vars[name] = True
    elif is_falsy_c or not isinstance(value_node, ast.Constant):
        checker._const_truthy_vars.pop(name, None)


def bind_assignment_target(checker: Any, target: ast.AST, value_node: ast.AST) -> None:
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


def eval_int_or_none(node: Optional[ast.AST]) -> Tuple[bool, Optional[int]]:
    if node is None:
        return True, None
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return True, node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        return True, -node.operand.value
    return False, None


def eval_const_str_expr(checker: Any, node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in checker._const_str_vars:
        return checker._const_str_vars[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_s = eval_const_str_expr(checker, node.left)
        right_s = eval_const_str_expr(checker, node.right)
        if left_s is not None and right_s is not None:
            return left_s + right_s
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
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                parts.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                val_s = eval_const_str_expr(checker, part.value)
                if val_s is None:
                    return None
                parts.append(val_s)
            else:
                val_s = eval_const_str_expr(checker, part)
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


def is_truthy_constant_expr(checker: Any, node: ast.AST) -> bool:
    """Determina se un nodo AST e una costante truthy preservando i parametri booleani dinamici."""
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.Name):
        return bool(checker._const_truthy_vars.get(node.id, False))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) > 0
    if isinstance(node, ast.Dict):
        return len(node.keys) > 0
    if isinstance(node, ast.JoinedStr):
        s = checker._eval_const_str_expr(node)
        return bool(s) if s is not None else len(node.values) > 0
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            if isinstance(node.operand, ast.Constant):
                return not bool(node.operand.value)
            if isinstance(node.operand, (ast.List, ast.Tuple, ast.Set)):
                return len(node.operand.elts) == 0
            if isinstance(node.operand, ast.Dict):
                return len(node.operand.keys) == 0
        elif (
            isinstance(node.op, (ast.USub, ast.UAdd))
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))
        ):
            return bool(
                -node.operand.value
                if isinstance(node.op, ast.USub)
                else +node.operand.value
            )
        elif (
            isinstance(node.op, ast.Invert)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, int)
        ):
            return bool(~node.operand.value)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return any(is_truthy_constant_expr(checker, v) for v in node.values)
        if isinstance(node.op, ast.And):
            return all(is_truthy_constant_expr(checker, v) for v in node.values)
    if isinstance(node, ast.IfExp):
        if isinstance(node.test, ast.Constant):
            branch = node.body if bool(node.test.value) else node.orelse
            return is_truthy_constant_expr(checker, branch)
    if (
        isinstance(node, ast.Call)
        and checker._resolve_symbol_expr(node.func)
        in ("bool", "int", "str", "builtins.bool", "builtins.int", "builtins.str")
        and len(node.args) == 1
    ):
        return is_truthy_constant_expr(checker, node.args[0])
    return False


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
            "globals",
            "locals",
            "vars",
            "builtins.globals",
            "builtins.locals",
            "builtins.vars",
            "__builtins__.globals",
            "__builtins__.locals",
            "__builtins__.vars",
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
        "__builtins__",
        "__dict__",
        "__globals__",
        "f_globals",
        "f_locals",
        "f_builtins",
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


def has_traversal_in_node(checker: Any, node: ast.AST) -> bool:
    """Verifica se un argomento stringa costante o parziale f-string contiene il segmento '..'."""
    full_s = checker._eval_const_str_expr(node)
    if full_s is not None:
        segs = [seg for seg in re.split(r"[\\/]+", full_s.strip()) if seg]
        if ".." in segs:
            return True
    if isinstance(node, ast.JoinedStr):
        raw_parts = "".join(
            p.value
            for p in node.values
            if isinstance(p, ast.Constant) and isinstance(p.value, str)
        )
        if (
            "../" in raw_parts
            or "..\\" in raw_parts
            or raw_parts.strip() == ".."
            or raw_parts.endswith(("/..", "\\.."))
        ):
            return True
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


def is_grant_or_snapshot_expr(checker: Any, node: ast.AST) -> bool:
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

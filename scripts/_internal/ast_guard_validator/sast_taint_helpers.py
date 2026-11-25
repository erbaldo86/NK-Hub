"""Helper pure-stdlib per contesto target, scope lessicale e taint SQL 1-hop SAST."""

from __future__ import annotations

import ast
import re
from typing import Any, List, Optional, Sequence, Set, Tuple

SQL_INJ_KEYWORD_RE = re.compile(
    r"\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s",
    re.IGNORECASE,
)


def _is_test_target_path(
    basename: str, path_parts: List[str], explicit_flag: bool
) -> bool:
    if explicit_flag or basename == "conftest.py" or "tests" in path_parts:
        return True
    return basename.startswith("test_") or basename.endswith("_test.py")


def _is_self_validator_path(
    parent_parts: List[str], basename: str, has_app_parent: bool
) -> bool:
    if has_app_parent:
        return False
    if parent_parts[-1:] == ["scripts"] and basename == "ast_guard_validator.py":
        return True
    return (
        len(parent_parts) >= 3
        and parent_parts[-3:] == ["scripts", "_internal", "ast_guard_validator"]
    )


def _is_hub_scripts_path(parent_parts: List[str], app_segments: Set[str]) -> bool:
    scripts_idx = max(
        (i for i, seg in enumerate(parent_parts) if seg == "scripts"), default=-1
    )
    if scripts_idx < 0:
        return False
    first_app_idx = min(
        (i for i, seg in enumerate(parent_parts) if seg in app_segments), default=-1
    )
    return first_app_idx < 0 or scripts_idx < first_app_idx


def classify_target_context(
    target_file: str, is_test_file_flag: bool
) -> Tuple[str, bool, bool, bool, bool]:
    """Classifica contesto test, self-validator, src_app e business app dal target."""
    raw_target = str(target_file) if target_file is not None else ""
    norm_target = raw_target.strip().replace("\\", "/")
    path_parts = [p.lower() for p in norm_target.split("/") if p]
    basename = path_parts[-1] if path_parts else ""
    is_test = _is_test_target_path(basename, path_parts, bool(is_test_file_flag))
    parent_parts = path_parts[:-1] if len(path_parts) > 1 else []
    app_segments = {"src_app", "src", "app"}
    has_app_parent = any(seg in app_segments for seg in parent_parts)
    is_self_val = _is_self_validator_path(parent_parts, basename, has_app_parent)
    is_anonymous = norm_target in ("", "<target>", "<unknown>", "<string>")
    in_hub_scripts = _is_hub_scripts_path(parent_parts, app_segments)
    in_app = (
        has_app_parent
        and not is_anonymous
        and not in_hub_scripts
        and not is_test
        and not is_self_val
    )
    in_business_app = in_app and any(seg in ("src_app", "app") for seg in parent_parts)
    return norm_target or "<target>", is_test, is_self_val, in_app, in_business_app


def extract_static_sql_fragments(node: ast.AST, checker: Any = None) -> str:
    """Raccoglie i frammenti stringa costanti da f-string, concatenazioni + e var note."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and checker is not None:
        return str(getattr(checker, "_const_str_vars", {}).get(node.id, ""))
    if isinstance(node, ast.JoinedStr):
        return "".join(extract_static_sql_fragments(p, checker) for p in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return extract_static_sql_fragments(node.left, checker) + extract_static_sql_fragments(
            node.right
        )
    return ""


def detect_sql_injection_kind(checker: Any, sql_node: ast.AST) -> Optional[str]:
    """Identifica vettori SQL injection (f-string, %, .format(), +) su query SQL."""
    while isinstance(sql_node, ast.NamedExpr):
        sql_node = sql_node.value
    raw_sql = ""
    kind = ""
    if isinstance(sql_node, ast.JoinedStr):
        if any(isinstance(p, ast.FormattedValue) for p in sql_node.values):
            raw_sql = extract_static_sql_fragments(sql_node, checker)
            kind = "f-string"
    elif isinstance(sql_node, ast.BinOp) and isinstance(sql_node.op, ast.Mod):
        raw_sql = extract_static_sql_fragments(sql_node.left, checker)
        kind = "%-formatting"
    elif (
        isinstance(sql_node, ast.Call)
        and isinstance(sql_node.func, ast.Attribute)
        and sql_node.func.attr == "format"
    ):
        raw_sql = extract_static_sql_fragments(sql_node.func.value, checker)
        kind = ".format()"
    elif isinstance(sql_node, ast.BinOp) and isinstance(sql_node.op, ast.Add):
        if checker._eval_const_str_expr(sql_node) is None:
            raw_sql = extract_static_sql_fragments(sql_node, checker)
            kind = "string concatenation"
    if kind and SQL_INJ_KEYWORD_RE.search(raw_sql):
        return kind
    return None


def resolve_tainted_sql_name(checker: Any, name: str) -> Optional[str]:
    """Restituisce il tipo di taint SQL se la variabile e tainted nello scope lessicale attivo."""
    taint_map = getattr(checker, "_tainted_sql_vars", {})
    if name in taint_map:
        return str(taint_map[name])
    for frame in reversed(getattr(checker, "_scope_stack", ())):
        if name in frame.get("sql_taint", ()):
            return "tainted variable"
        if name in frame.get("locals", ()):
            return None
    return None


def update_sql_taint_for_name(checker: Any, name: str, value_node: ast.AST) -> None:
    """Aggiorna il tracking taint SQL 1-hop nello scope corrente per una assegnazione."""
    if not hasattr(checker, "_tainted_sql_vars"):
        return
    scope_stack = getattr(checker, "_scope_stack", None)
    if scope_stack:
        scope_stack[-1]["locals"].add(name)
    taint_kind = detect_sql_injection_kind(checker, value_node)
    if taint_kind is None and isinstance(value_node, ast.Name):
        taint_kind = resolve_tainted_sql_name(checker, value_node.id)
    if taint_kind:
        checker._tainted_sql_vars[name] = taint_kind
        if scope_stack:
            scope_stack[-1]["sql_taint"].add(name)
    else:
        checker._tainted_sql_vars.pop(name, None)
        if scope_stack:
            scope_stack[-1]["sql_taint"].discard(name)


def resolve_name_alias_with_shadow(checker: Any, node: ast.Name) -> Optional[str]:
    """Risolve alias di ast.Name escludendo parametri locali eval/compile."""
    if node.id in ("eval", "compile") and is_param_shadowed(checker, node.id):
        return None
    cur = node.id
    seen: Set[str] = set()
    for _ in range(8):
        if cur in seen:
            break
        seen.add(cur)
        nxt = checker._symbol_aliases.get(cur) or checker._imported_aliases.get(cur)
        if not nxt or nxt == cur:
            break
        cur = nxt
    return cur


def update_sql_taint_augassign(
    checker: Any, name: str, op: ast.operator, value_node: ast.AST
) -> None:
    """Aggiorna il taint SQL su assegnazioni incrementali (es. sql += uid)."""
    scope_stack = getattr(checker, "_scope_stack", None)
    if isinstance(op, ast.Add):
        if resolve_tainted_sql_name(checker, name):
            return
        synth = ast.BinOp(
            left=ast.Name(id=name, ctx=ast.Load()),
            op=ast.Add(),
            right=value_node,
        )
        taint_kind = detect_sql_injection_kind(checker, synth)
        if taint_kind:
            checker._tainted_sql_vars[name] = taint_kind
            if scope_stack:
                scope_stack[-1]["sql_taint"].add(name)
            return
    checker._tainted_sql_vars.pop(name, None)
    if scope_stack:
        scope_stack[-1]["sql_taint"].discard(name)


def collect_param_names(args: ast.arguments) -> Set[str]:
    """Estrae tutti i nomi dei parametri da una definizione di funzione o lambda."""
    params: Set[str] = {
        a.arg for a in (*getattr(args, "posonlyargs", ()), *args.args, *args.kwonlyargs)
    }
    if args.vararg:
        params.add(args.vararg.arg)
    if args.kwarg:
        params.add(args.kwarg.arg)
    return params


def is_param_shadowed(checker: Any, name: str) -> bool:
    """True se il nome corrisponde a un parametro attivo non oscurato da locale interno."""
    for frame in reversed(getattr(checker, "_scope_stack", ())):
        if name in frame.get("params", ()):
            return True
        if name in frame.get("locals", ()):
            return False
    return False


def visit_function_header(
    checker: Any, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> None:
    """Visita decoratori, default, type_params e annotazioni nello scope esterno."""
    for dec in node.decorator_list:
        checker.visit(dec)
    for tp in getattr(node, "type_params", ()):
        checker.visit(tp)
    for expr in (*node.args.defaults, *getattr(node.args, "kw_defaults", ())):
        if expr is not None:
            checker.visit(expr)
    for arg in (
        *getattr(node.args, "posonlyargs", ()),
        *node.args.args,
        *node.args.kwonlyargs,
    ):
        if arg.annotation is not None:
            checker.visit(arg.annotation)
    for var_arg in (node.args.vararg, node.args.kwarg):
        if var_arg is not None and var_arg.annotation is not None:
            checker.visit(var_arg.annotation)
    if node.returns is not None:
        checker.visit(node.returns)


def visit_with_lexical_scope(
    checker: Any, params: Set[str], body: Sequence[ast.stmt] | ast.AST
) -> None:
    """Isola aliasing, costanti e taint SQL dentro un frame lessicale dedicato."""
    has_falsy_attr = hasattr(checker, "_const_falsy_vars")
    snap = (
        dict(checker._imported_aliases),
        dict(checker._symbol_aliases),
        dict(checker._const_str_vars),
        dict(checker._const_truthy_vars),
        set(getattr(checker, "_const_falsy_vars", ())),
        set(checker._namespace_vars),
        dict(checker._tainted_sql_vars),
    )
    checker._scope_stack.append(
        {"params": set(params), "locals": set(params), "sql_taint": set()}
    )
    for pname in params:
        checker._clear_bound_name_state(pname)
    try:
        if isinstance(body, ast.AST):
            checker.visit(body)
        else:
            for stmt in body:
                checker.visit(stmt)
    finally:
        checker._scope_stack.pop()
        (
            checker._imported_aliases,
            checker._symbol_aliases,
            checker._const_str_vars,
            checker._const_truthy_vars,
            falsy_snap,
            checker._namespace_vars,
            checker._tainted_sql_vars,
        ) = snap
        if has_falsy_attr:
            checker._const_falsy_vars = falsy_snap

"""Helper specifici per controlli SAST su import, subprocess, yaml, path, attributi e SQL."""

from __future__ import annotations

import ast
from typing import Any, List, Optional, Tuple

from _internal.ast_guard_validator.sast_constants import (
    DANGEROUS_LOOKUP_SYMS,
    DANGEROUS_MODULES,
    MRO_EVASION_ATTRS,
)
from _internal.ast_guard_validator.sast_expr_eval import is_falsy_constant_expr
from _internal.ast_guard_validator.sast_taint_helpers import (
    detect_sql_injection_kind,
    resolve_tainted_sql_name,
)


def _expand_arg_nodes(nodes: List[ast.AST]) -> List[ast.AST]:
    """Espande superficialmente contenitori e Starred preservando i nodi originali."""
    expanded: List[ast.AST] = []
    for item in nodes:
        expanded.append(item)
        if isinstance(item, ast.Starred):
            expanded.append(item.value)
            if isinstance(item.value, (ast.List, ast.Tuple, ast.Set)):
                expanded.extend(item.value.elts)
        elif isinstance(item, (ast.List, ast.Tuple, ast.Set)):
            expanded.extend(item.elts)
    return expanded


def _iter_call_arg_nodes(node: ast.Call) -> List[ast.AST]:
    """Restituisce tutti i nodi argomento posizionali e keyword di ast.Call."""
    raw = list(node.args) + [kw.value for kw in node.keywords]
    return _expand_arg_nodes(raw)


def _check_import_mod_arg(checker: Any, node: ast.Call, arg_node: ast.AST) -> bool:
    """Verifica un singolo argomento di importlib.import_module; True se emessa violazione."""
    if checker._has_reverse_slice_expr(arg_node):
        checker._emit_sast(
            "importlib.import_module",
            node,
            "Unsafe reverse-slice obfuscation in 'importlib.import_module()' detected.",
        )
        return True
    mod_arg = checker._eval_const_str_expr(arg_node)
    if mod_arg and mod_arg.strip().split(".")[0] in DANGEROUS_MODULES | {"sys"}:
        checker._emit_sast(
            "importlib.import_module",
            node,
            f"Unsafe dynamic import 'importlib.import_module({mod_arg!r})' detected.",
        )
        return True
    return False


def _iter_import_mod_candidates(node: ast.Call) -> List[ast.AST]:
    """Raccoglie argomenti posizionali e keyword name=/package= di import_module."""
    return list(node.args[:1]) + [
        kw.value for kw in node.keywords if kw.arg in ("name", "package")
    ]


def check_import_module_call(checker: Any, node: ast.Call) -> None:
    """Rileva import dinamici vietati o offuscati tramite importlib.import_module."""
    any(_check_import_mod_arg(checker, node, arg) for arg in _iter_import_mod_candidates(node))


def _check_subprocess_cmd_keywords(checker: Any, symbol: str, node: ast.Call) -> None:
    """Verifica argomenti args=/cmd=/executable=/cwd= e posizionali di subprocess."""
    cmd_nodes: List[ast.AST] = list(node.args[:1]) + [
        kw.value
        for kw in node.keywords
        if kw.arg in ("args", "cmd", "executable", "cwd")
    ]
    for cand in _expand_arg_nodes(cmd_nodes):
        if checker._has_reverse_slice_expr(cand):
            checker._emit_sast(
                symbol,
                node,
                f"Unsafe reverse-slice obfuscation in '{symbol}()' detected.",
            )
            return
        if checker._has_traversal_in_node(cand):
            checker._emit_sast(
                symbol,
                node,
                f"Unsafe constant '..' path traversal in '{symbol}()' detected.",
            )
            return
        hit = checker._find_literal_env_token_in_node(cand)
        if hit:
            checker._emit_sast(
                symbol,
                node,
                f"[RULE-NO-LITERAL-ENV-PATH] Unexpanded literal env path '{hit}' passed to '{symbol}()'; use tempfile.gettempdir() or os.environ.get().",
            )
            return


def _is_sanctioned_platform_runner_shell(checker: Any, shell_val: ast.AST) -> bool:
    """Consente esclusivamente shell=effective_shell nel wrapper sicuro scripts/platform_runner.py."""
    norm_t = str(getattr(checker, "target_file", "") or "").replace("\\", "/").lower()
    is_runner = norm_t == "scripts/platform_runner.py" or norm_t.endswith("/scripts/platform_runner.py")
    return bool(is_runner and isinstance(shell_val, ast.Name) and shell_val.id == "effective_shell")


def _check_shell_arg(
    checker: Any,
    symbol: str,
    node: ast.Call,
    shell_val: ast.AST,
    is_positional: bool = False,
) -> bool:
    """Blocca shell=True o shell=var non staticamente falsy nei wrapper subprocess."""
    if checker._is_truthy_constant_expr(shell_val):
        kind = "positional shell" if is_positional else "shell"
        checker._emit_sast(
            symbol,
            node,
            f"Unsafe truthy {kind} parameter in '{symbol}(..., shell=...)' detected.",
        )
        return True
    if not is_falsy_constant_expr(checker, shell_val) and not _is_sanctioned_platform_runner_shell(
        checker, shell_val
    ):
        checker._emit_sast(
            symbol,
            node,
            f"Unsafe dynamic shell variable/expression in '{symbol}(..., shell=...)' detected.",
        )
        return True
    return False


def check_subprocess_call(checker: Any, symbol: str, attr: str, node: ast.Call) -> None:
    """Verifica shell=True/var, getoutput, **kwargs e args=/cmd= nei wrapper subprocess."""
    if attr in ("getoutput", "getstatusoutput"):
        checker._emit_sast(
            symbol,
            node,
            f"Unsafe implicit shell execution '{symbol}()' detected.",
        )
        return
    for kw in node.keywords:
        if kw.arg is None:
            checker._emit_sast(
                symbol,
                node,
                f"Unsafe arbitrary **kwargs unpacking in '{symbol}()' detected.",
            )
            return
        if kw.arg == "shell" and _check_shell_arg(checker, symbol, node, kw.value):
            return
    if len(node.args) >= 9 and _check_shell_arg(
        checker, symbol, node, node.args[8], is_positional=True
    ):
        return
    _check_subprocess_cmd_keywords(checker, symbol, node)


def check_yaml_call(checker: Any, attr: str, node: ast.Call) -> None:
    """Impone SafeLoader o CSafeLoader nelle chiamate PyYAML."""
    if attr in ("unsafe_load", "unsafe_load_all", "full_load", "full_load_all"):
        checker._emit_sast(
            f"yaml.{attr}",
            node,
            f"Unsafe 'yaml.{attr}()' deserialization detected.",
        )
        return
    if attr in ("load", "load_all"):
        loader_node: Optional[ast.AST] = node.args[1] if len(node.args) >= 2 else None
        for kw in node.keywords:
            if kw.arg == "Loader":
                loader_node = kw.value
                break
        is_safe = False
        if loader_node is not None:
            loader_sym = checker._resolve_symbol_expr(loader_node) or ""
            loader_tail = loader_sym.split(".")[-1] if loader_sym else ""
            if loader_tail in ("SafeLoader", "CSafeLoader"):
                is_safe = True
            elif isinstance(loader_node, ast.Attribute) and loader_node.attr in (
                "SafeLoader",
                "CSafeLoader",
            ):
                is_safe = True
        if not is_safe:
            checker._emit_sast(
                f"yaml.{attr}",
                node,
                f"Unsafe 'yaml.{attr}()' without SafeLoader detected.",
            )


def check_path_traversal_args(checker: Any, symbol: str, node: ast.Call) -> None:
    """Blocca argomenti costanti (posizionali o keyword) con segmento '..' in API filesystem."""
    for arg in _iter_call_arg_nodes(node):
        if checker._has_traversal_in_node(arg):
            checker._emit_sast(
                symbol,
                node,
                f"Unsafe constant '..' path traversal in '{symbol}()' detected.",
            )
            return


def check_literal_env_path_args(checker: Any, symbol: str, node: ast.Call) -> None:
    """Rileva variabili ambiente letterali non espanse passate a API filesystem/path."""
    for arg in _iter_call_arg_nodes(node):
        hit = checker._find_literal_env_token_in_node(arg)
        if hit:
            checker._emit_sast(
                symbol,
                node,
                f"[RULE-NO-LITERAL-ENV-PATH] Unexpanded literal env path '{hit}' passed to '{symbol}()'; use tempfile.gettempdir() or os.environ.get().",
            )
            return


def check_dynamic_attr_access(
    checker: Any,
    node: ast.Call,
    target_arg: ast.AST,
    name_arg: ast.AST,
    api_name: str,
) -> bool:
    """Verifica accessi dinamici tramite getattr o __getattribute__."""
    attr_arg = checker._eval_const_str_expr(name_arg)
    has_rev = checker._has_reverse_slice_expr(name_arg)
    is_ns_target = checker._is_namespace_expr(target_arg)
    target_sym = checker._resolve_symbol_expr(target_arg) or ""
    target_root = target_sym.split(".")[0] if target_sym else ""
    is_danger_mod_target = target_root in (
        "os", "nt", "posix", "pty", "subprocess",
        "builtins", "__builtins__", "pickle", "marshal",
    )
    if target_root == "ctypes" and attr_arg == "windll":
        checker._emit_sast(
            "ctypes.windll",
            node,
            f"Unsafe dynamic {api_name} access to 'ctypes.windll' detected.",
        )
    elif (
        has_rev
        or is_ns_target
        or attr_arg in (DANGEROUS_LOOKUP_SYMS | MRO_EVASION_ATTRS)
        or (
            is_danger_mod_target
            and (
                attr_arg is None
                or attr_arg in DANGEROUS_LOOKUP_SYMS
                or attr_arg.startswith(("exec", "spawn"))
            )
        )
    ):
        checker._emit_sast(
            api_name,
            node,
            f"Unsafe dynamic {api_name} access '{attr_arg or '<dynamic>'}' detected.",
        )
    elif not checker.is_test_file and (
        (target_root == "inspect" and attr_arg in ("currentframe", "stack"))
        or (target_root == "sys" and attr_arg in ("_getframe", "modules"))
    ):
        rule = "SAST-GAMING-D01" if attr_arg == "modules" else "SAST-GAMING-D02"
        checker._emit_gaming_violation(
            rule,
            node,
            f"Prohibited {api_name} introspection '{target_root}.{attr_arg}' detected.",
        )
        return True
    return False


def _dispatch_getattr_call(checker: Any, node: ast.Call) -> bool:
    """Esegue il controllo dinamico su getattr da args o keyword object/name."""
    pair = _extract_getattr_pair(node)
    if pair is None:
        return False
    return check_dynamic_attr_access(checker, node, pair[0], pair[1], "getattr")


def check_getattr_call(checker: Any, node: ast.Call) -> bool:
    """Wrapper dedicato per verifiche su chiamate getattr() posizionali o keyword."""
    return _dispatch_getattr_call(checker, node)


def _check_dunder_import_call(checker: Any, node: ast.Call) -> None:
    """Verifica argomenti posizionali e keyword name= di __import__()."""
    cand_nodes: List[ast.AST] = list(node.args[:1]) + [
        kw.value for kw in node.keywords if kw.arg == "name"
    ]
    for arg_node in cand_nodes:
        if checker._has_reverse_slice_expr(arg_node):
            checker._emit_sast(
                "__import__",
                node,
                "Unsafe reverse-slice obfuscation in '__import__()' detected.",
            )
            return
        mod_arg = checker._eval_const_str_expr(arg_node)
        if mod_arg and mod_arg.split(".")[0] in DANGEROUS_MODULES | {"sys"}:
            checker._emit_sast(
                "__import__",
                node,
                f"Unsafe dynamic import '__import__({mod_arg!r})' detected.",
            )
            return


def _extract_getattr_pair(
    node: ast.Call,
) -> Optional[Tuple[ast.AST, ast.AST]]:
    """Estrae coppia (oggetto, nome_attributo) da args o kwargs di getattr/__getattribute__."""
    if len(node.args) >= 2:
        return node.args[0], node.args[1]
    obj_node: Optional[ast.AST] = node.args[0] if node.args else None
    name_node: Optional[ast.AST] = None
    for kw in node.keywords:
        if kw.arg in ("object", "obj") and obj_node is None:
            obj_node = kw.value
        elif kw.arg == "name":
            name_node = kw.value
    if obj_node is not None and name_node is not None:
        return obj_node, name_node
    return None


def _check_single_sql_arg(checker: Any, attr: str, node: ast.Call, sql_node: ast.AST) -> bool:
    """Verifica un singolo argomento SQL diretto o variabile tainted 1-hop; True se segnalato."""
    inj_kind = detect_sql_injection_kind(checker, sql_node)
    if inj_kind:
        checker._emit_sast(attr, node, f"Unsafe SQL {inj_kind} injection in '.{attr}()' detected.")
        return True
    if isinstance(sql_node, ast.Name):
        taint_kind = resolve_tainted_sql_name(checker, sql_node.id)
        if taint_kind:
            checker._emit_sast(
                attr, node,
                f"Unsafe 1-hop tainted SQL variable '{sql_node.id}' ({taint_kind}) in '.{attr}()' detected.",
            )
            return True
    return False


def _check_sql_execute_call(checker: Any, attr: str, node: ast.Call) -> None:
    """Verifica SQL injection diretta e variabili SQL tainted 1-hop su execute/executemany."""
    sql_nodes: List[ast.AST] = list(node.args[:1]) + [
        kw.value
        for kw in node.keywords
        if kw.arg in ("sql", "query", "statement", "command")
    ]
    for sql_node in sql_nodes:
        if _check_single_sql_arg(checker, attr, node, sql_node):
            return

"""Helper specifici per controlli SAST su import, subprocess, yaml, path e attributi."""

from __future__ import annotations

import ast
from typing import Any, List, Optional

from _internal.ast_guard_validator.sast_constants import (
    DANGEROUS_LOOKUP_SYMS,
    DANGEROUS_MODULES,
    MRO_EVASION_ATTRS,
)


def check_import_module_call(checker: Any, node: ast.Call) -> None:
    """Rileva import dinamici vietati o offuscati tramite importlib.import_module."""
    if not node.args:
        return
    if checker._has_reverse_slice_expr(node.args[0]):
        checker._emit_sast(
            "importlib.import_module",
            node,
            "Unsafe reverse-slice obfuscation in 'importlib.import_module()' detected.",
        )
        return
    mod_arg = checker._eval_const_str_expr(node.args[0])
    if mod_arg and mod_arg.strip().split(".")[0] in DANGEROUS_MODULES | {"sys"}:
        checker._emit_sast(
            "importlib.import_module",
            node,
            f"Unsafe dynamic import 'importlib.import_module({mod_arg!r})' detected.",
        )


def check_subprocess_call(checker: Any, symbol: str, attr: str, node: ast.Call) -> None:
    """Verifica shell=True, getoutput e **kwargs nei wrapper subprocess."""
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
        if kw.arg == "shell" and checker._is_truthy_constant_expr(kw.value):
            checker._emit_sast(
                symbol,
                node,
                f"Unsafe truthy shell parameter in '{symbol}(..., shell=...)' detected.",
            )
            return
    if len(node.args) >= 9 and checker._is_truthy_constant_expr(node.args[8]):
        checker._emit_sast(
            symbol,
            node,
            f"Unsafe truthy positional shell parameter in '{symbol}()' detected.",
        )


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
    """Blocca argomenti costanti con segmento '..' in API filesystem."""
    for arg in node.args:
        if checker._has_traversal_in_node(arg):
            checker._emit_sast(
                symbol,
                node,
                f"Unsafe constant '..' path traversal in '{symbol}()' detected.",
            )
            return


def check_literal_env_path_args(checker: Any, symbol: str, node: ast.Call) -> None:
    """Rileva variabili ambiente letterali non espanse passate a API filesystem/path."""
    arg_nodes: List[ast.AST] = list(node.args) + [kw.value for kw in node.keywords]
    for arg in arg_nodes:
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
        "os",
        "nt",
        "posix",
        "pty",
        "subprocess",
        "builtins",
        "__builtins__",
        "pickle",
        "marshal",
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


def check_getattr_call(checker: Any, node: ast.Call) -> bool:
    """Wrapper dedicato per verifiche su chiamate getattr()."""
    return check_dynamic_attr_access(checker, node, node.args[0], node.args[1], "getattr")

"""Controlli SAST su nodi ast.Call per SASTConstructChecker."""

from __future__ import annotations

import ast
from typing import Any, Tuple

from _internal.ast_guard_validator.sast_call_helpers import (
    check_dynamic_attr_access as _check_dynamic_attr_access,
    check_getattr_call as _check_getattr_call,
    check_import_module_call,
    check_literal_env_path_args,
    check_path_traversal_args,
    check_subprocess_call,
    check_yaml_call,
)
from _internal.ast_guard_validator.sast_constants import (
    DANGEROUS_LOOKUP_SYMS,
    DANGEROUS_MODULES,
    MOCK_SYMBOLS,
    MRO_EVASION_ATTRS,
    PATH_CTORS,
    SUBPROCESS_CALLS,
    TOK_FIXTURE_FN,
)


def check_call_resolved(
    checker: Any, node: ast.Call, func: ast.expr, resolved: str
) -> Tuple[bool, bool]:
    """Verifica chiamate con simbolo risolto rispetto a SAST, Zero-Mock e gaming."""
    handled_mock = False
    handled_gaming = False

    if resolved in (
        "eval",
        "exec",
        "compile",
        "builtins.eval",
        "builtins.exec",
        "builtins.compile",
        "__builtins__.eval",
        "__builtins__.exec",
        "__builtins__.compile",
    ):
        sym_name = func.id if isinstance(func, ast.Name) else resolved
        checker._emit_sast(
            sym_name,
            node,
            f"Unsafe SAST construct '{resolved}()' detected.",
        )
    elif resolved in ("import_module", "importlib.import_module"):
        checker._check_import_module_call(node)
    elif resolved in ("attrgetter", "operator.attrgetter") and node.args:
        for ag_arg in node.args:
            if checker._has_reverse_slice_expr(ag_arg):
                checker._emit_sast(
                    "operator.attrgetter",
                    node,
                    "Unsafe reverse-slice obfuscation in 'operator.attrgetter()' detected.",
                )
                break
            attr_s = checker._eval_const_str_expr(ag_arg)
            if attr_s and any(
                p in DANGEROUS_LOOKUP_SYMS | MRO_EVASION_ATTRS
                for p in attr_s.split(".")
            ):
                checker._emit_sast(
                    "operator.attrgetter",
                    node,
                    f"Unsafe 'operator.attrgetter({attr_s!r})' detected.",
                )
                break
    elif (
        resolved in ("__import__", "builtins.__import__", "__builtins__.__import__")
        and node.args
    ):
        if checker._has_reverse_slice_expr(node.args[0]):
            checker._emit_sast(
                "__import__",
                node,
                "Unsafe reverse-slice obfuscation in '__import__()' detected.",
            )
        else:
            mod_arg = checker._eval_const_str_expr(node.args[0])
            if mod_arg and mod_arg.split(".")[0] in DANGEROUS_MODULES | {"sys"}:
                checker._emit_sast(
                    "__import__",
                    node,
                    f"Unsafe dynamic import '__import__({mod_arg!r})' detected.",
                )
    elif (
        resolved
        in (
            "getattr",
            "builtins.getattr",
            "__builtins__.getattr",
            "__getattribute__",
            "builtins.__getattribute__",
            "__builtins__.__getattribute__",
            "object.__getattribute__",
            "type.__getattribute__",
        )
        and len(node.args) >= 2
    ):
        handled_gaming = _check_dynamic_attr_access(
            checker, node, node.args[0], node.args[1], resolved
        )
    elif (
        resolved in MOCK_SYMBOLS
        or any(resolved.endswith(f".{m}") for m in MOCK_SYMBOLS)
        or resolved.startswith(("unittest.mock.", "mock."))
    ):
        sym_mock = func.id if isinstance(func, ast.Name) else resolved
        checker._emit_sast(
            sym_mock,
            node,
            f"Zero-Mock violation: '{resolved}()' instantiation/patch detected.",
        )
        handled_mock = True
    elif resolved in ("open", "builtins.open", "__builtins__.open", "io.open"):
        open_sym = "io.open" if resolved == "io.open" else "open"
        checker._check_path_traversal_args(open_sym, node)
        checker._check_literal_env_path_args(open_sym, node)
    elif resolved in PATH_CTORS or any(resolved == f"pathlib.{p}" for p in PATH_CTORS):
        sym_path = func.id if isinstance(func, ast.Name) else resolved
        checker._check_path_traversal_args(sym_path, node)
        checker._check_literal_env_path_args(sym_path, node)
    elif resolved in ("os.path.join", "posixpath.join", "ntpath.join"):
        checker._check_path_traversal_args(resolved, node)
        checker._check_literal_env_path_args(resolved, node)
    elif resolved in ("os.makedirs", "os.mkdir"):
        checker._check_literal_env_path_args(resolved, node)
    elif resolved == "pty.spawn":
        checker._emit_sast(
            "pty.spawn",
            node,
            "Unsafe PTY command execution 'pty.spawn()' detected.",
        )
    elif resolved == "asyncio.create_subprocess_shell":
        checker._emit_sast(
            "asyncio.create_subprocess_shell",
            node,
            "Unsafe shell subprocess 'asyncio.create_subprocess_shell()' detected.",
        )
    elif "." in resolved and resolved.rsplit(".", 1)[0] in ("os", "nt", "posix"):
        os_attr = resolved.rsplit(".", 1)[1]
        if os_attr in ("system", "popen") or os_attr.startswith(("exec", "spawn")):
            checker._emit_sast(
                resolved,
                node,
                f"Unsafe OS command execution '{resolved}()' detected.",
            )
    elif resolved in (
        "pickle.loads",
        "pickle.load",
        "_pickle.loads",
        "_pickle.load",
        "marshal.loads",
        "marshal.load",
    ):
        checker._emit_sast(
            resolved,
            node,
            f"Unsafe deserialization '{resolved}()' detected.",
        )
    elif resolved.startswith("subprocess."):
        sp_attr = resolved.split(".", 1)[1]
        if sp_attr in SUBPROCESS_CALLS | {"getoutput", "getstatusoutput"}:
            checker._check_subprocess_call(resolved, sp_attr, node)
    elif resolved.startswith("yaml."):
        y_attr = resolved.split(".", 1)[1]
        checker._check_yaml_call(y_attr, node)

    if not checker.is_test_file and not handled_gaming:
        if resolved in (
            "currentframe",
            "_getframe",
            "inspect.currentframe",
            "inspect.stack",
            "sys._getframe",
        ):
            checker._emit_gaming_violation(
                "SAST-GAMING-D02",
                node,
                f"Prohibited stack introspection '{resolved}()' detected.",
            )
            handled_gaming = True
        elif resolved == TOK_FIXTURE_FN or resolved.endswith(f".{TOK_FIXTURE_FN}"):
            checker._emit_gaming_violation(
                "SAST-GAMING-D03",
                node,
                f"Prohibited sandbox fixture call '{resolved}()' detected.",
            )
            handled_gaming = True

    return handled_mock, handled_gaming


def check_call_attribute(
    checker: Any,
    node: ast.Call,
    func: ast.Attribute,
    handled_mock: bool,
    handled_gaming: bool,
) -> None:
    """Verifica chiamate a metodo tramite ast.Attribute su lookup dinamici, SQL e mock."""
    val = func.value
    attr = func.attr

    if attr == "__getattribute__" and node.args and not handled_gaming:
        if _check_dynamic_attr_access(checker, node, val, node.args[0], "__getattribute__"):
            handled_gaming = True

    if attr in ("get", "pop", "setdefault") and node.args:
        k_node = node.args[0]
        k_str = checker._eval_const_str_expr(k_node)
        has_rev = checker._has_reverse_slice_expr(k_node)
        if checker._is_sys_modules_expr(val):
            if k_str in DANGEROUS_MODULES or has_rev:
                checker._emit_sast(
                    f"sys.modules.{attr}",
                    node,
                    f"Unsafe dynamic module lookup 'sys.modules.{attr}({k_str or '<reversed>'!r})' detected.",
                )
            elif not checker.is_test_file and k_str == "pytest":
                checker._emit_gaming_violation(
                    "SAST-GAMING-D01",
                    node,
                    f"sys.modules.{attr}('pytest') sniffing detected.",
                )
                handled_gaming = True
        elif checker._is_namespace_expr(val):
            checker._emit_sast(
                f"namespace.{attr}",
                node,
                f"Unsafe dynamic namespace lookup '.{attr}({k_str or '<dynamic>'!r})' detected.",
            )
        elif has_rev and k_str in DANGEROUS_LOOKUP_SYMS:
            checker._emit_sast(
                f"reverse_lookup.{attr}",
                node,
                f"Unsafe reverse-slice lookup '.{attr}({k_str!r})' detected.",
            )

    if attr == "joinpath":
        checker._check_path_traversal_args("Path.joinpath", node)
        checker._check_literal_env_path_args("Path.joinpath", node)

    if attr in ("execute", "executemany") and node.args:
        first_arg = node.args[0]
        if isinstance(first_arg, ast.JoinedStr):
            raw_sql = "".join(
                part.value
                for part in first_arg.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            ).upper()
            sql_keywords = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ")
            if any(kw in raw_sql for kw in sql_keywords):
                checker._emit_sast(
                    attr,
                    node,
                    f"Unsafe SQL f-string injection in '.{attr}()' detected.",
                )

    if not handled_mock and attr in MOCK_SYMBOLS:
        checker._emit_sast(
            attr,
            node,
            f"Zero-Mock violation: '{attr}' attribute call detected.",
        )

    if not checker.is_test_file and not handled_gaming:
        if (
            attr == "get"
            and node.args
            and checker._eval_const_str_expr(node.args[0]) == "pytest"
            and isinstance(val, ast.Attribute)
            and val.attr == "modules"
        ):
            checker._emit_gaming_violation(
                "SAST-GAMING-D01",
                node,
                "sys.modules.get('pytest') sniffing detected.",
            )
        elif attr in ("currentframe", "_getframe"):
            checker._emit_gaming_violation(
                "SAST-GAMING-D02",
                node,
                f"Prohibited stack introspection '.{attr}()' detected.",
            )
        elif attr == TOK_FIXTURE_FN:
            checker._emit_gaming_violation(
                "SAST-GAMING-D03",
                node,
                f"Prohibited sandbox fixture call '.{attr}()' detected.",
            )


__all__ = [
    "check_call_attribute",
    "check_call_resolved",
    "check_import_module_call",
    "check_literal_env_path_args",
    "check_path_traversal_args",
    "check_subprocess_call",
    "check_yaml_call",
    "_check_dynamic_attr_access",
    "_check_getattr_call",
]

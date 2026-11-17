"""Helper su nodi AST non-Call per SASTConstructChecker."""

from __future__ import annotations

import ast
from typing import Any


def check_binop_node(checker: Any, node: ast.BinOp) -> bool:
    """Verifica traversal su '/' e token gaming su '+'; ritorna True se skippa generic_visit."""
    if isinstance(node.op, ast.Div) and not checker.is_self_validator:
        if checker._has_traversal_in_node(node.right) or checker._has_traversal_in_node(
            node.left
        ):
            checker._emit_sast(
                "Path.traversal",
                node,
                "Unsafe constant '..' path traversal via '/' operator detected.",
            )
    if (
        not checker.is_test_file
        and not checker.is_self_validator
        and isinstance(node.op, ast.Add)
    ):
        combined = checker._eval_const_str_expr(node)
        if combined and (
            checker._TOK_PYTEST_CUR in combined or checker._TOK_NK_SANDBOX in combined
        ):
            checker._emit_gaming_violation(
                "SAST-GAMING-D01",
                node,
                f"Test or sandbox environment string concatenation '{combined}' detected.",
            )
            return True
    return False


def check_constant_node(checker: Any, node: ast.Constant) -> None:
    """Controlla costanti stringa vietate o hardcoded in codice non-test."""
    if (
        not checker.is_test_file
        and not checker.is_self_validator
        and isinstance(node.value, str)
    ):
        val = node.value
        if checker._TOK_PYTEST_CUR in val or checker._TOK_NK_SANDBOX in val:
            checker._emit_gaming_violation(
                "SAST-GAMING-D01",
                node,
                f"Test or sandbox environment sniffing '{val}' detected.",
            )
        if checker.in_src_app:
            if checker._TOK_EXT_PROJ.lower() in val.lower():
                checker._emit_gaming_violation(
                    "SAST-GAMING-D03",
                    node,
                    "Hardcoded external project host path in application code detected.",
                )
            for bad_tok in checker._SUSPICIOUS_HARDCODED_TOKENS:
                if bad_tok in val:
                    checker._emit_gaming_violation(
                        "SAST-GAMING-D04",
                        node,
                        f"Suspicious hardcoded gaming constant '{bad_tok}' in application code detected.",
                    )


def check_subscript_node(checker: Any, node: ast.Subscript) -> None:
    """Rileva lookup dinamici su sys.modules, namespace o slice invertiti."""
    if checker.is_self_validator or not isinstance(node.ctx, ast.Load):
        return
    key_str = checker._eval_const_str_expr(node.slice)
    rev_slice = (
        not isinstance(node.slice, ast.Slice)
        and checker._has_reverse_slice_expr(node.slice)
    )
    if checker._is_sys_modules_expr(node.value):
        if key_str in checker._DANGEROUS_MODULES or rev_slice:
            checker._emit_sast(
                "sys.modules",
                node,
                f"Unsafe dynamic module lookup sys.modules[{key_str or '<reversed>'!r}] detected.",
            )
        elif not checker.is_test_file and key_str == "pytest":
            checker._emit_gaming_violation(
                "SAST-GAMING-D01",
                node,
                "Direct sys.modules['pytest'] sniffing detected.",
            )
    elif checker._is_namespace_expr(node.value):
        is_attr_dict = (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
            and not checker._is_namespace_expr(node.value.value)
        )
        if (
            not is_attr_dict
            or key_str in checker._DANGEROUS_LOOKUP_SYMS
            or rev_slice
            or key_str is None
        ):
            checker._emit_sast(
                key_str or "namespace_subscript",
                node,
                f"Unsafe dynamic namespace subscript access '{key_str or '<dynamic>'}' detected.",
            )
    elif rev_slice and key_str in checker._DANGEROUS_LOOKUP_SYMS:
        checker._emit_sast(
            key_str,
            node,
            f"Obfuscated reverse-slice lookup '{key_str}' detected.",
        )


def check_attribute_node(checker: Any, node: ast.Attribute) -> None:
    """Rileva accessi a ctypes.windll, MRO e attributi frame."""
    if checker.is_self_validator:
        return
    resolved_attr = checker._resolve_symbol_expr(node)
    if resolved_attr == "ctypes.windll" or (
        isinstance(node.value, ast.Name)
        and checker._resolve_symbol_expr(node.value) == "windll"
    ):
        checker._emit_sast(
            "ctypes.windll",
            node,
            "Unsafe raw 'ctypes.windll' access detected; use ctypes.WinDLL(..., use_last_error=True).",
        )
    elif node.attr in checker._MRO_EVASION_ATTRS:
        checker._emit_sast(
            node.attr,
            node,
            f"Unsafe MRO/namespace introspection attribute '.{node.attr}' detected.",
        )
    elif not checker.is_test_file and node.attr in checker._FRAME_ATTRS:
        checker._emit_gaming_violation(
            "SAST-GAMING-D02",
            node,
            f"Prohibited frame attribute access '.{node.attr}' detected.",
        )


def check_compare_node(checker: Any, node: ast.Compare) -> None:
    """Rileva sniffing di pytest in sys.modules e soglie gaming in src_app."""
    if checker.is_test_file or checker.is_self_validator:
        return
    left_const = checker._eval_const_str_expr(node.left)
    if left_const == "pytest":
        for comp in node.comparators:
            if checker._is_sys_modules_expr(comp) or (
                isinstance(comp, ast.Attribute) and comp.attr == "modules"
            ):
                checker._emit_gaming_violation(
                    "SAST-GAMING-D01",
                    node,
                    "sys.modules 'pytest' membership sniffing detected.",
                )
    if checker.in_src_app:
        operands = [node.left, *node.comparators]
        has_grant_or_snapshot_len = False
        has_threshold_int = False
        for op_node in operands:
            if (
                isinstance(op_node, ast.Call)
                and checker._resolve_symbol_expr(op_node.func)
                in ("len", "builtins.len", "__builtins__.len")
                and len(op_node.args) == 1
                and checker._is_grant_or_snapshot_expr(op_node.args[0])
            ):
                has_grant_or_snapshot_len = True
            elif (
                isinstance(op_node, ast.Constant)
                and isinstance(op_node.value, int)
                and not isinstance(op_node.value, bool)
                and op_node.value >= 10
            ):
                has_threshold_int = True
        if has_grant_or_snapshot_len and has_threshold_int:
            checker._emit_gaming_violation(
                "SAST-GAMING-D04",
                node,
                "Conditional branching on len(grant/snapshot) >= 10 detected.",
            )


def check_import_node(checker: Any, node: ast.Import) -> None:
    """Registra alias import e blocca import mock."""
    for alias in node.names:
        bound = alias.asname if alias.asname else alias.name.split(".")[0]
        checker._imported_aliases[bound] = alias.name if alias.asname else bound
        checker._symbol_aliases.pop(bound, None)
        if (
            alias.name in ("unittest.mock", "mock")
            or alias.name.startswith(("unittest.mock.", "mock."))
            or any(m in (alias.asname or alias.name) for m in checker._MOCK_SYMBOLS)
        ):
            checker._emit_sast(
                alias.name,
                node,
                "Zero-Mock violation: unittest.mock or MagicMock import detected.",
            )


def check_import_from_node(checker: Any, node: ast.ImportFrom) -> None:
    """Registra alias ImportFrom e blocca import mock o ctypes.windll."""
    for alias in node.names:
        bound = alias.asname or alias.name
        if node.module:
            checker._imported_aliases[bound] = f"{node.module}.{alias.name}"
            checker._symbol_aliases.pop(bound, None)
        if (
            alias.name in checker._MOCK_SYMBOLS
            or (node.module in ("unittest.mock", "mock"))
            or (node.module and node.module.startswith(("unittest.mock.", "mock.")))
            or (node.module == "unittest" and alias.name == "mock")
        ):
            checker._emit_sast(
                alias.name,
                node,
                "Zero-Mock violation: unittest.mock / MagicMock import detected.",
            )
        elif (
            not checker.is_self_validator
            and node.module == "ctypes"
            and alias.name == "windll"
        ):
            checker._emit_sast(
                "ctypes.windll",
                node,
                "Unsafe raw 'ctypes.windll' import detected; use ctypes.WinDLL(..., use_last_error=True).",
            )

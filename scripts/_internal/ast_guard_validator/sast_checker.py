"""Visitor AST SASTConstructChecker per blocchi Zero-Mock, SAST e anti-gaming."""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple

from _internal.ast_guard_validator.models import GuardViolation, ViolationType
from _internal.ast_guard_validator.sast_call_checks import (
    check_call_attribute,
    check_call_resolved,
    check_import_module_call,
    check_literal_env_path_args,
    check_path_traversal_args,
    check_subprocess_call,
    check_yaml_call,
)
from _internal.ast_guard_validator.sast_constants import (
    DANGEROUS_LOOKUP_SYMS,
    DANGEROUS_MODULES,
    ENV_VAR_NAMES_PATTERN,
    FRAME_ATTRS,
    GRANT_SNAPSHOT_NAMES,
    LITERAL_ENV_PATH_RE,
    MOCK_MODULE_EXPORTS,
    MOCK_SYMBOLS,
    MRO_EVASION_ATTRS,
    PATH_CTORS,
    SUBPROCESS_CALLS,
    SUSPICIOUS_HARDCODED_TOKENS,
    TOK_EXT_PROJ,
    TOK_FIXTURE_FN,
    TOK_NK_SANDBOX,
    TOK_PYTEST_CUR,
)
from _internal.ast_guard_validator.sast_eval import (
    bind_assignment_target,
    bind_value_to_name,
    clear_bound_name_state,
    eval_const_str_expr,
    eval_int_or_none,
    find_literal_env_token_in_node,
    has_reverse_slice_expr,
    has_traversal_in_node,
    is_grant_or_snapshot_expr,
    is_namespace_expr,
    is_truthy_constant_expr,
    resolve_symbol_expr,
)
from _internal.ast_guard_validator.sast_node_checks import (
    check_attribute_node,
    check_binop_node,
    check_compare_node,
    check_constant_node,
    check_import_from_node,
    check_import_node,
    check_subscript_node,
)


class SASTConstructChecker(ast.NodeVisitor):
    """Rileva costrutti SAST non sicuri, alias/rebinding dinamici, Zero-Mock, ctypes.windll e test-gaming."""

    _TOK_PYTEST_CUR: str = TOK_PYTEST_CUR
    _TOK_NK_SANDBOX: str = TOK_NK_SANDBOX
    _TOK_FIXTURE_FN: str = TOK_FIXTURE_FN
    _TOK_EXT_PROJ: str = TOK_EXT_PROJ
    _ENV_VAR_NAMES_PATTERN: str = ENV_VAR_NAMES_PATTERN
    _LITERAL_ENV_PATH_RE = LITERAL_ENV_PATH_RE
    _FRAME_ATTRS: Set[str] = FRAME_ATTRS
    _MRO_EVASION_ATTRS: Set[str] = MRO_EVASION_ATTRS
    _DANGEROUS_MODULES: Set[str] = DANGEROUS_MODULES
    _DANGEROUS_LOOKUP_SYMS: Set[str] = DANGEROUS_LOOKUP_SYMS
    _MOCK_SYMBOLS: Set[str] = MOCK_SYMBOLS
    _MOCK_MODULE_EXPORTS: Set[str] = MOCK_MODULE_EXPORTS
    _PATH_CTORS: Set[str] = PATH_CTORS
    _SUBPROCESS_CALLS: Set[str] = SUBPROCESS_CALLS
    _GRANT_SNAPSHOT_NAMES: Set[str] = GRANT_SNAPSHOT_NAMES
    _SUSPICIOUS_HARDCODED_TOKENS: Set[str] = SUSPICIOUS_HARDCODED_TOKENS

    def __init__(
        self, target_file: str = "<target>", is_test_file: bool = False
    ) -> None:
        self.violations: List[GuardViolation] = []
        self.sast_violations: List[GuardViolation] = self.violations
        self._imported_aliases: Dict[str, str] = {}
        self._symbol_aliases: Dict[str, str] = {}
        self._const_str_vars: Dict[str, str] = {}
        self._const_truthy_vars: Dict[str, bool] = {}
        self._namespace_vars: Set[str] = set()

        raw_target = str(target_file) if target_file is not None else ""
        norm_target = raw_target.strip().replace("\\", "/")
        path_parts = [p.lower() for p in norm_target.split("/") if p]
        basename = path_parts[-1] if path_parts else ""
        self.target_file = norm_target or "<target>"
        self.is_test_file = bool(
            is_test_file
            or basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename == "conftest.py"
            or "tests" in path_parts
        )
        self.is_self_validator = basename == "ast_guard_validator.py"
        is_anonymous_snippet = norm_target in ("", "<target>", "<unknown>", "<string>")
        in_hub_scripts = "scripts" in path_parts
        parent_parts = path_parts[:-1] if len(path_parts) > 1 else []
        self.in_src_app = bool(
            not is_anonymous_snippet
            and not in_hub_scripts
            and not self.is_test_file
            and not self.is_self_validator
            and any(seg in ("src_app", "src", "app") for seg in parent_parts)
        )
        self.in_explicit_src_app = self.in_src_app

    def _emit_sast(self, symbol: str, node: ast.AST, message: str) -> None:
        self.violations.append(
            GuardViolation(
                violation_type=ViolationType.SAST_VIOLATION,
                symbol_name=symbol,
                line_number=getattr(node, "lineno", None),
                column=getattr(node, "col_offset", None),
                message=message,
                severity="CRITICAL",
            )
        )

    def _emit_gaming_violation(
        self, rule_id: str, node: ast.AST, detail: str
    ) -> None:
        self.violations.append(
            GuardViolation(
                violation_type=ViolationType.SAST_VIOLATION,
                symbol_name=rule_id,
                line_number=getattr(node, "lineno", None),
                column=getattr(node, "col_offset", None),
                message=f"[CRITICAL] {rule_id}: {detail}",
                severity="CRITICAL",
            )
        )

    def _resolve_symbol_expr(self, node: ast.AST) -> Optional[str]:
        """Risolve ricorsivamente alias di importazione e assegnazioni dirette semplici."""
        return resolve_symbol_expr(self, node)

    def _clear_bound_name_state(self, name: str) -> None:
        clear_bound_name_state(self, name)

    def _bind_value_to_name(self, name: str, value_node: ast.AST) -> None:
        bind_value_to_name(self, name, value_node)

    def _bind_assignment_target(self, target: ast.AST, value_node: ast.AST) -> None:
        bind_assignment_target(self, target, value_node)

    def _has_reverse_slice_expr(self, node: ast.AST) -> bool:
        """Rileva qualsiasi espressione con slice invertito [::-1] usata per offuscare simboli."""
        return has_reverse_slice_expr(self, node)

    def _eval_int_or_none(self, node: Optional[ast.AST]) -> Tuple[bool, Optional[int]]:
        return eval_int_or_none(node)

    def _eval_const_str_expr(self, node: ast.AST) -> Optional[str]:
        return eval_const_str_expr(self, node)

    def _is_truthy_constant_expr(self, node: ast.AST) -> bool:
        """Determina se un nodo AST e una costante truthy preservando i parametri booleani dinamici."""
        return is_truthy_constant_expr(self, node)

    def _is_sys_modules_expr(self, node: ast.AST) -> bool:
        return self._resolve_symbol_expr(node) == "sys.modules"

    def _is_namespace_expr(self, node: ast.AST) -> bool:
        """Identifica globals(), locals(), vars(), builtins, __builtins__, sys.modules['builtins'] e alias."""
        return is_namespace_expr(self, node)

    def _has_traversal_in_node(self, node: ast.AST) -> bool:
        """Verifica se un argomento stringa costante o parziale f-string contiene il segmento '..'."""
        return has_traversal_in_node(self, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind_assignment_target(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._bind_assignment_target(node.target, node.value)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind_assignment_target(node.target, node.value)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if check_binop_node(self, node):
            return
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        if not self.is_test_file and not self.is_self_validator:
            combined = self._eval_const_str_expr(node)
            if combined and (
                self._TOK_PYTEST_CUR in combined or self._TOK_NK_SANDBOX in combined
            ):
                self._emit_gaming_violation(
                    "SAST-GAMING-D01",
                    node,
                    f"Test or sandbox environment f-string '{combined}' detected.",
                )
                return
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        check_constant_node(self, node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        check_subscript_node(self, node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        check_attribute_node(self, node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if (
            not self.is_test_file
            and not self.is_self_validator
            and node.name == self._TOK_FIXTURE_FN
        ):
            self._emit_gaming_violation(
                "SAST-GAMING-D03",
                node,
                f"Prohibited sandbox fixture helper function '{node.name}' detected.",
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if (
            not self.is_test_file
            and not self.is_self_validator
            and node.name == self._TOK_FIXTURE_FN
        ):
            self._emit_gaming_violation(
                "SAST-GAMING-D03",
                node,
                f"Prohibited sandbox fixture helper function '{node.name}' detected.",
            )
        self.generic_visit(node)

    def _is_grant_or_snapshot_expr(self, node: ast.AST) -> bool:
        return is_grant_or_snapshot_expr(self, node)

    def visit_Compare(self, node: ast.Compare) -> None:
        check_compare_node(self, node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        check_import_node(self, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        check_import_from_node(self, node)
        self.generic_visit(node)

    def _check_import_module_call(self, node: ast.Call) -> None:
        check_import_module_call(self, node)

    def _check_subprocess_call(self, symbol: str, attr: str, node: ast.Call) -> None:
        check_subprocess_call(self, symbol, attr, node)

    def _check_yaml_call(self, attr: str, node: ast.Call) -> None:
        check_yaml_call(self, attr, node)

    def _check_path_traversal_args(self, symbol: str, node: ast.Call) -> None:
        check_path_traversal_args(self, symbol, node)

    def _find_literal_env_token_in_node(self, node: ast.AST) -> Optional[str]:
        """Individua token env letterali non espansi in costanti o f-string."""
        return find_literal_env_token_in_node(self, node)

    def _check_literal_env_path_args(self, symbol: str, node: ast.Call) -> None:
        """Rileva variabili ambiente letterali non espanse passate a API filesystem/path."""
        check_literal_env_path_args(self, symbol, node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.is_self_validator:
            self.generic_visit(node)
            return
        func = node.func
        resolved = self._resolve_symbol_expr(func)
        handled_mock = False
        handled_gaming = False
        if resolved:
            handled_mock, handled_gaming = check_call_resolved(self, node, func, resolved)
        if isinstance(func, ast.Attribute):
            check_call_attribute(self, node, func, handled_mock, handled_gaming)
        self.generic_visit(node)

"""Visitor AST SASTConstructChecker per blocchi Zero-Mock, SAST, scope e taint SQL."""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

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
    bind_value_to_name,  # noqa: F401
    clear_bound_name_state,
    eval_const_str_expr,
    eval_int_or_none,  # noqa: F401
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
from _internal.ast_guard_validator.sast_taint_helpers import (
    classify_target_context as _classify_target_context,
    collect_param_names,
    is_param_shadowed,
    update_sql_taint_augassign,
    visit_function_header,
    visit_with_lexical_scope,
)

_BARE_DANGEROUS_NAMES: Set[str] = {"eval", "exec", "compile", "__import__"}


class SASTConstructChecker(ast.NodeVisitor):
    """Rileva costrutti SAST, alias dinamici, Zero-Mock, taint SQL 1-hop e test-gaming."""

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
        self._const_falsy_vars: Set[str] = set()
        self._namespace_vars: Set[str] = set()
        self._tainted_sql_vars: Dict[str, str] = {}
        self._scope_stack: List[Dict[str, Set[str]]] = [
            {"params": set(), "locals": set(), "sql_taint": set()}
        ]
        self._direct_call_func_ids: Set[int] = set()

        clean_target, is_test, is_self_val, in_app, in_biz_app = _classify_target_context(
            target_file, is_test_file
        )
        self.target_file = clean_target
        self.is_test_file = is_test
        self.is_self_validator = is_self_val
        self.in_src_app = in_app
        self.in_explicit_src_app = in_app
        self.in_business_app = in_biz_app

    def _emit_sast(self, symbol: str, node: ast.AST, message: str) -> None:
        self.violations.append(GuardViolation(
            violation_type=ViolationType.SAST_VIOLATION,
            symbol_name=symbol,
            line_number=getattr(node, "lineno", None),
            column=getattr(node, "col_offset", None),
            message=message,
            severity="CRITICAL",
        ))

    def _emit_gaming_violation(
        self, rule_id: str, node: ast.AST, detail: str
    ) -> None:
        self.violations.append(GuardViolation(
            violation_type=ViolationType.SAST_VIOLATION,
            symbol_name=rule_id,
            line_number=getattr(node, "lineno", None),
            column=getattr(node, "col_offset", None),
            message=f"[CRITICAL] {rule_id}: {detail}",
            severity="CRITICAL",
        ))

    def _is_param_in_scope(self, name: str) -> bool:
        return is_param_shadowed(self, name)

    def _resolve_symbol_expr(self, node: ast.AST) -> Optional[str]:
        return resolve_symbol_expr(self, node)

    def _clear_bound_name_state(self, name: str) -> None:
        clear_bound_name_state(self, name)

    def _bind_assignment_target(self, target: ast.AST, value_node: ast.AST) -> None:
        bind_assignment_target(self, target, value_node)

    def _has_reverse_slice_expr(self, node: ast.AST) -> bool:
        return has_reverse_slice_expr(self, node)

    def _eval_const_str_expr(self, node: ast.AST) -> Optional[str]:
        return eval_const_str_expr(self, node)

    def _is_truthy_constant_expr(self, node: ast.AST) -> bool:
        return is_truthy_constant_expr(self, node)

    def _is_sys_modules_expr(self, node: ast.AST) -> bool:
        return self._resolve_symbol_expr(node) == "sys.modules"

    def _is_namespace_expr(self, node: ast.AST) -> bool:
        return is_namespace_expr(self, node)

    def _has_traversal_in_node(self, node: ast.AST) -> bool:
        return has_traversal_in_node(self, node)

    def _visit_with_self_validator_off(self, check_fn: Any, node: ast.AST) -> Any:
        prev = self.is_self_validator
        self.is_self_validator = False
        try:
            return check_fn(self, node)
        finally:
            self.is_self_validator = prev

    def _dispatch_binop(self, node: ast.BinOp) -> bool:
        if isinstance(node.op, ast.Add):
            return check_binop_node(self, node)
        return bool(self._visit_with_self_validator_off(check_binop_node, node))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind_assignment_target(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._bind_assignment_target(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            update_sql_taint_augassign(self, node.target.id, node.op, node.value)
            self._const_str_vars.pop(node.target.id, None)
            self._const_truthy_vars.pop(node.target.id, None)
            self._const_falsy_vars.discard(node.target.id)
            self._symbol_aliases.pop(node.target.id, None)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            for sub in ast.walk(target):
                if isinstance(sub, ast.Name):
                    self._clear_bound_name_state(sub.id)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind_assignment_target(node.target, node.value)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if self._dispatch_binop(node):
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

    def _is_unsafe_bare_name_load(self, node: ast.Name) -> bool:
        """Verifica se un ast.Name isolato espone un builtin pericoloso non mascherato."""
        if not isinstance(node.ctx, ast.Load) or id(node) in self._direct_call_func_ids:
            return False
        if node.id not in _BARE_DANGEROUS_NAMES:
            return False
        return not (node.id in ("eval", "compile") and self._is_param_in_scope(node.id))

    def visit_Name(self, node: ast.Name) -> None:
        if self._is_unsafe_bare_name_load(node):
            self._emit_sast(
                node.id,
                node,
                f"Unsafe standalone reference to dangerous builtin '{node.id}' detected.",
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._visit_with_self_validator_off(check_subscript_node, node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._visit_with_self_validator_off(check_attribute_node, node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expr in (*node.decorator_list, *node.bases, *node.keywords):
            self.visit(expr)
        for tp in getattr(node, "type_params", ()):
            self.visit(tp)
        visit_with_lexical_scope(self, set(), node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expr in (*node.args.defaults, *getattr(node.args, "kw_defaults", ())):
            if expr is not None:
                self.visit(expr)
        visit_with_lexical_scope(self, collect_param_names(node.args), node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self.is_test_file and node.name == self._TOK_FIXTURE_FN:
            self._emit_gaming_violation(
                "SAST-GAMING-D03",
                node,
                f"Prohibited sandbox fixture helper function '{node.name}' detected.",
            )
        visit_function_header(self, node)
        visit_with_lexical_scope(self, collect_param_names(node.args), node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self.is_test_file and node.name == self._TOK_FIXTURE_FN:
            self._emit_gaming_violation(
                "SAST-GAMING-D03",
                node,
                f"Prohibited sandbox fixture helper function '{node.name}' detected.",
            )
        visit_function_header(self, node)
        visit_with_lexical_scope(self, collect_param_names(node.args), node.body)

    def _is_grant_or_snapshot_expr(self, node: ast.AST) -> bool:
        return is_grant_or_snapshot_expr(self, node)

    def visit_Compare(self, node: ast.Compare) -> None:
        self._visit_with_self_validator_off(check_compare_node, node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        check_import_node(self, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._visit_with_self_validator_off(check_import_from_node, node)
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
        return find_literal_env_token_in_node(self, node)

    def _check_literal_env_path_args(self, symbol: str, node: ast.Call) -> None:
        check_literal_env_path_args(self, symbol, node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        resolved = self._resolve_symbol_expr(func)
        handled_mock = False
        handled_gaming = False
        if resolved:
            handled_mock, handled_gaming = check_call_resolved(self, node, func, resolved)
        if isinstance(func, ast.Attribute):
            check_call_attribute(self, node, func, handled_mock, handled_gaming)
        self._direct_call_func_ids.add(id(func))
        try:
            self.generic_visit(node)
        finally:
            self._direct_call_func_ids.discard(id(func))

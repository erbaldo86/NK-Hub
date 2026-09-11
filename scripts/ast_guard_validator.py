"""
Nexus Keystone v1.1.0-Universal - Compiler, Code Intelligence & Slicing
Module: ast_guard_validator.py
Author: NK-Python-Async-Builder (Node 3)

Features:
- Pre-edit and post-edit AST Validator.
- Syntactic Purity Check (ast.parse with detailed diagnostics).
- Signature Preservation Invariant (parameters, types, defaults, asyncness, return annotations).
- Import Graph & Scope Integrity with PEP 634 Pattern Matching, PEP 695 Type Parameters,
  TypeAlias, Comprehensions, and Walrus Operator (:=) support.
"""

from __future__ import annotations

import ast
import builtins
import difflib
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# PYDANTIC V2 STRICT DATA MODELS
# ============================================================================

class ViolationType(str, Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SIGNATURE_MUTATION = "SIGNATURE_MUTATION"
    UNAUTHORIZED_DELETION = "UNAUTHORIZED_DELETION"
    UNDEFINED_NAME = "UNDEFINED_NAME"
    MALFORMED_IMPORT = "MALFORMED_IMPORT"
    TYPE_MISMATCH = "TYPE_MISMATCH"


class GuardViolation(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    violation_type: ViolationType = Field(description="Category of AST violation")
    symbol_name: Optional[str] = Field(default=None, description="Name of symbol violated, if applicable")
    line_number: Optional[int] = Field(default=None, description="1-indexed line number")
    column: Optional[int] = Field(default=None, description="0-indexed column offset")
    message: str = Field(description="Explanatory error diagnosis")
    diff_context: Optional[str] = Field(default=None, description="Diff snippet or code line context")


class FunctionSignatureSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    name: str = Field(description="Function or method name")
    is_async: bool = Field(description="Whether the function is async")
    posonly_args: List[str] = Field(default_factory=list, description="Positional-only argument names")
    pos_args: List[str] = Field(default_factory=list, description="Standard positional argument names")
    vararg: Optional[str] = Field(default=None, description="*args name if present")
    kwonly_args: List[str] = Field(default_factory=list, description="Keyword-only argument names")
    kwarg: Optional[str] = Field(default=None, description="**kwargs name if present")
    defaults_count: int = Field(default=0, description="Count of default values on positional args")
    kw_defaults_count: int = Field(default=0, description="Count of non-None keyword defaults")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Argument name -> annotation string")
    return_annotation: Optional[str] = Field(default=None, description="Return type annotation string")
    parent_class: Optional[str] = Field(default=None, description="Enclosing class name")


class ValidationReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    is_valid: bool = Field(description="True if zero critical violations found")
    pre_symbol_count: int = Field(description="Total functions/classes in pre-edit AST")
    post_symbol_count: int = Field(description="Total functions/classes in post-edit AST")
    violations: List[GuardViolation] = Field(default_factory=list, description="List of detected violations")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Detailed validation metrics")


# ============================================================================
# SIGNATURE EXTRACTOR HELPER
# ============================================================================

class SignatureCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.signatures: Dict[str, FunctionSignatureSnapshot] = {}
        self.classes: Set[str] = set()
        self.current_class: Optional[str] = None
        self.imported_names: Set[str] = set()
        self.defined_globals: Set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.add(node.name)
        self.defined_globals.add(node.name)
        # PEP 695 Type Parameters on Class
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                self.defined_globals.add(tp.name)
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_names.add(name.split(".")[0])
            self.defined_globals.add(name)
            if alias.name:
                self.defined_globals.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_names.add(name)
            self.defined_globals.add(name)
        self.generic_visit(node)

    def _extract_target_names(self, node: ast.AST, target_set: Set[str]) -> None:
        if isinstance(node, ast.Name):
            target_set.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._extract_target_names(elt, target_set)
        elif isinstance(node, ast.Starred):
            self._extract_target_names(node.value, target_set)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.current_class is None:
            for t in node.targets:
                self._extract_target_names(t, self.defined_globals)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self.current_class is None:
            self._extract_target_names(node.target, self.defined_globals)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        if self.current_class is None:
            self._extract_target_names(node.target, self.defined_globals)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        if self.current_class is None:
            self._extract_target_names(node.target, self.defined_globals)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        if self.current_class is None:
            for item in node.items:
                if item.optional_vars:
                    self._extract_target_names(item.optional_vars, self.defined_globals)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        if self.current_class is None:
            for item in node.items:
                if item.optional_vars:
                    self._extract_target_names(item.optional_vars, self.defined_globals)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if self.current_class is None and node.name:
            self.defined_globals.add(node.name)
        self.generic_visit(node)

    def visit_TypeAlias(self, node: Any) -> None:
        # PEP 695 TypeAlias support
        if hasattr(node, "name"):
            if isinstance(node.name, ast.Name):
                self.defined_globals.add(node.name.id)
            elif isinstance(node.name, str):
                self.defined_globals.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, is_async=True)
        self.generic_visit(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        key = f"{self.current_class}.{node.name}" if self.current_class else node.name
        if self.current_class is None:
            self.defined_globals.add(node.name)

        posonly = [a.arg for a in getattr(node.args, "posonlyargs", [])]
        pos_args = [a.arg for a in node.args.args]
        kwonly = [a.arg for a in node.args.kwonlyargs]
        vararg = node.args.vararg.arg if node.args.vararg else None
        kwarg = node.args.kwarg.arg if node.args.kwarg else None

        defaults_count = len(node.args.defaults)
        kw_defaults_count = len([d for d in node.args.kw_defaults if d is not None])

        annotations: Dict[str, str] = {}
        for arg in getattr(node.args, "posonlyargs", []) + node.args.args + node.args.kwonlyargs:
            if arg.annotation:
                annotations[arg.arg] = ast.unparse(arg.annotation)
        if node.args.vararg and node.args.vararg.annotation:
            annotations[node.args.vararg.arg] = ast.unparse(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation:
            annotations[node.args.kwarg.arg] = ast.unparse(node.args.kwarg.annotation)

        return_ann = ast.unparse(node.returns) if node.returns else None

        self.signatures[key] = FunctionSignatureSnapshot(
            name=node.name,
            is_async=is_async,
            posonly_args=posonly,
            pos_args=pos_args,
            vararg=vararg,
            kwonly_args=kwonly,
            kwarg=kwarg,
            defaults_count=defaults_count,
            kw_defaults_count=kw_defaults_count,
            annotations=annotations,
            return_annotation=return_ann,
            parent_class=self.current_class,
        )


# ============================================================================
# SCOPE INTEGRITY VISITOR (PEP 634, PEP 695, Comprehensions, Walrus)
# ============================================================================

MODULE_DUNDERS: Set[str] = {
    "__name__",
    "__doc__",
    "__file__",
    "__package__",
    "__loader__",
    "__spec__",
    "__annotations__",
    "__builtins__",
    "__cached__",
}


class ScopeIntegrityChecker(ast.NodeVisitor):
    """
    Checks that every referenced variable in Load context is defined in local scope,
    enclosing scopes, globals, or standard builtins.
    Fully supports:
    - PEP 634 Pattern Matching (ast.Match, ast.MatchCase and pattern binding variables).
    - PEP 695 Type Parameters (Function, AsyncFunction, Class type_params, TypeAlias).
    - Comprehensions (ListComp, SetComp, DictComp, GeneratorExp) with isolated sub-scopes.
    - Walrus operator (ast.NamedExpr :=) escaping comprehension scopes to enclosing scope.
    - Lambda expressions and standard Python module attributes.
    """

    def __init__(self, global_names: Set[str]) -> None:
        self.global_names = set(global_names) | MODULE_DUNDERS
        self.builtins_set = set(dir(builtins))
        self.scope_stack: List[Set[str]] = [set(self.global_names)]
        self.violations: List[GuardViolation] = []

    def _current_visible_names(self) -> Set[str]:
        names: Set[str] = set(self.builtins_set)
        for s in self.scope_stack:
            names.update(s)
        return names

    def visit_Lambda(self, node: ast.Lambda) -> None:
        local_scope: Set[str] = set()
        for arg in getattr(node.args, "posonlyargs", []) + node.args.args + node.args.kwonlyargs:
            local_scope.add(arg.arg)
        if node.args.vararg:
            local_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_scope.add(node.args.kwarg.arg)
        self.scope_stack.append(local_scope)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack[-1].add(node.name)
        local_scope: Set[str] = set()
        # PEP 695 type parameters on class
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                local_scope.add(tp.name)
        self.scope_stack.append(local_scope)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_func(node)

    def _process_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack[-1].add(node.name)
        local_scope: Set[str] = set()

        # Add PEP 695 type parameters
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                local_scope.add(tp.name)

        # Add parameters to local scope
        for arg in getattr(node.args, "posonlyargs", []) + node.args.args + node.args.kwonlyargs:
            local_scope.add(arg.arg)
        if node.args.vararg:
            local_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_scope.add(node.args.kwarg.arg)

        # Pre-scan body assignments to handle Python's lexical scoping
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    self._extract_target_names(t, local_scope)
            elif isinstance(child, ast.AnnAssign):
                self._extract_target_names(child.target, local_scope)
            elif isinstance(child, ast.For):
                self._extract_target_names(child.target, local_scope)
            elif isinstance(child, ast.AsyncFor):
                self._extract_target_names(child.target, local_scope)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                local_scope.add(child.name)
            elif isinstance(child, ast.With):
                for item in child.items:
                    if item.optional_vars:
                        self._extract_target_names(item.optional_vars, local_scope)
            elif isinstance(child, ast.AsyncWith):
                for item in child.items:
                    if item.optional_vars:
                        self._extract_target_names(item.optional_vars, local_scope)
            elif isinstance(child, ast.NamedExpr):
                # Walrus := inside function body binds to function scope
                if isinstance(child.target, ast.Name):
                    local_scope.add(child.target.id)

        self.scope_stack.append(local_scope)

        for child in node.body:
            self.visit(child)

        self.scope_stack.pop()

    def _extract_target_names(self, node: ast.AST, target_set: Set[str]) -> None:
        if isinstance(node, ast.Name):
            target_set.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._extract_target_names(elt, target_set)
        elif isinstance(node, ast.Starred):
            self._extract_target_names(node.value, target_set)

    # ----------------------------------------------------------------------
    # PEP 634 Pattern Matching Support
    # ----------------------------------------------------------------------
    def visit_Match(self, node: Any) -> None:
        # Match subject is evaluated in current scope
        self.visit(node.subject)
        for case in node.cases:
            pattern_bindings: Set[str] = set()
            self._extract_pattern_bindings(case.pattern, pattern_bindings)
            # Add pattern bindings to current scope frame
            self.scope_stack[-1].update(pattern_bindings)
            if case.guard:
                self.visit(case.guard)
            for stmt in case.body:
                self.visit(stmt)

    def _extract_pattern_bindings(self, pattern: Any, bindings: Set[str]) -> None:
        if pattern is None:
            return
        p_type = type(pattern).__name__

        if p_type == "MatchAs":
            if getattr(pattern, "name", None):
                bindings.add(pattern.name)
            if getattr(pattern, "pattern", None):
                self._extract_pattern_bindings(pattern.pattern, bindings)
        elif p_type == "MatchStar":
            if getattr(pattern, "name", None):
                bindings.add(pattern.name)
        elif p_type == "MatchMapping":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)
            if getattr(pattern, "rest", None):
                bindings.add(pattern.rest)
        elif p_type == "MatchClass":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)
            for p in getattr(pattern, "kwd_patterns", []):
                self._extract_pattern_bindings(p, bindings)
        elif p_type == "MatchSequence":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)
        elif p_type == "MatchOr":
            for p in getattr(pattern, "patterns", []):
                self._extract_pattern_bindings(p, bindings)

    # ----------------------------------------------------------------------
    # PEP 695 TypeAlias Support
    # ----------------------------------------------------------------------
    def visit_TypeAlias(self, node: Any) -> None:
        if hasattr(node, "name"):
            if isinstance(node.name, ast.Name):
                self.scope_stack[-1].add(node.name.id)
            elif isinstance(node.name, str):
                self.scope_stack[-1].add(node.name)
        # Type params
        for tp in getattr(node, "type_params", []):
            if hasattr(tp, "name"):
                self.scope_stack[-1].add(tp.name)
        if hasattr(node, "value"):
            self.visit(node.value)

    # ----------------------------------------------------------------------
    # Comprehensions Support (Isolated Sub-Scopes)
    # ----------------------------------------------------------------------
    def _visit_comprehension_common(self, generators: List[ast.comprehension], visit_elts_fn: Any) -> None:
        comp_scope: Set[str] = set()
        for gen in generators:
            # gen.iter is evaluated in the enclosing scope BEFORE binding gen.target
            self.visit(gen.iter)
            self._extract_target_names(gen.target, comp_scope)

        self.scope_stack.append(comp_scope)
        for gen in generators:
            for if_expr in gen.ifs:
                self.visit(if_expr)
        visit_elts_fn()
        self.scope_stack.pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension_common(node.generators, lambda: self.visit(node.elt))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension_common(node.generators, lambda: self.visit(node.elt))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension_common(node.generators, lambda: self.visit(node.elt))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        def visit_kv():
            self.visit(node.key)
            self.visit(node.value)
        self._visit_comprehension_common(node.generators, visit_kv)

    # ----------------------------------------------------------------------
    # Walrus Operator (ast.NamedExpr :=)
    # ----------------------------------------------------------------------
    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        # Evaluate value first
        self.visit(node.value)
        # Target escapes comprehension sub-scopes to the enclosing function/module scope
        if isinstance(node.target, ast.Name):
            # Target is placed in outermost function or global frame
            frame_idx = len(self.scope_stack) - 1
            # If at top of comprehension, place in parent frame
            if frame_idx > 0:
                self.scope_stack[frame_idx - 1].add(node.target.id)
            self.scope_stack[frame_idx].add(node.target.id)

    # ----------------------------------------------------------------------
    # Name Resolution Check
    # ----------------------------------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            visible = self._current_visible_names()
            if node.id not in visible:
                self.violations.append(
                    GuardViolation(
                        violation_type=ViolationType.UNDEFINED_NAME,
                        symbol_name=node.id,
                        line_number=node.lineno,
                        column=node.col_offset,
                        message=f"Undefined name '{node.id}' referenced without import or local binding.",
                    )
                )
        self.generic_visit(node)


# ============================================================================
# AST GUARD VALIDATOR
# ============================================================================

class ASTGuardValidator:
    """
    Main validator coordinating Syntactic Purity, Signature Preservation Invariant,
    and Scope / Import Graph Integrity.
    """

    @classmethod
    def validate_code_edit(
        cls,
        pre_code: str,
        post_code: str,
        allowed_mutations: Optional[Set[str]] = None,
        target_file: str = "<target>",
    ) -> ValidationReport:
        """
        Executes full suite of deterministic AST guards on the code transformation.
        """
        violations: List[GuardViolation] = []
        allowed = allowed_mutations or set()

        # GATE 1: Syntactic Purity (Pre & Post)
        pre_tree = cls._parse_or_report(pre_code, "pre_edit", violations)
        post_tree = cls._parse_or_report(post_code, "post_edit", violations)

        if post_tree is None:
            # Fatal syntax error in post edit
            return ValidationReport(
                is_valid=False,
                pre_symbol_count=0,
                post_symbol_count=0,
                violations=violations,
                metrics={"fatal_syntax_error": True},
            )

        # Extract pre-edit signatures
        pre_collector = SignatureCollector()
        if pre_tree:
            pre_collector.visit(pre_tree)

        # Extract post-edit signatures
        post_collector = SignatureCollector()
        post_collector.visit(post_tree)

        # GATE 2: Signature Preservation Invariant & Unauthorized Deletions
        cls._verify_signatures(
            pre_collector.signatures,
            post_collector.signatures,
            allowed,
            violations,
        )

        # GATE 3: Scope & Unbound Name Integrity
        checker = ScopeIntegrityChecker(global_names=post_collector.defined_globals)
        checker.visit(post_tree)
        violations.extend(checker.violations)

        # Metrics computation
        diff = difflib.unified_diff(
            pre_code.splitlines(),
            post_code.splitlines(),
            fromfile=f"pre/{target_file}",
            tofile=f"post/{target_file}",
            lineterm="",
        )
        diff_lines = list(diff)

        is_valid = len(violations) == 0

        return ValidationReport(
            is_valid=is_valid,
            pre_symbol_count=len(pre_collector.signatures) + len(pre_collector.classes),
            post_symbol_count=len(post_collector.signatures) + len(post_collector.classes),
            violations=violations,
            metrics={
                "diff_line_count": len(diff_lines),
                "total_violations": len(violations),
                "syntax_clean": True,
                "pre_functions": len(pre_collector.signatures),
                "post_functions": len(post_collector.signatures),
                "pre_classes": len(pre_collector.classes),
                "post_classes": len(post_collector.classes),
            },
        )

    @classmethod
    def _parse_or_report(cls, code: str, stage: str, violations: List[GuardViolation]) -> Optional[ast.AST]:
        try:
            return ast.parse(code, type_comments=True)
        except SyntaxError as se:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SYNTAX_ERROR,
                    symbol_name=None,
                    line_number=se.lineno,
                    column=se.offset,
                    message=f"SyntaxError in {stage}: {se.msg}",
                    diff_context=se.text,
                )
            )
            return None

    @classmethod
    def _verify_signatures(
        cls,
        pre_sigs: Dict[str, FunctionSignatureSnapshot],
        post_sigs: Dict[str, FunctionSignatureSnapshot],
        allowed_mutations: Set[str],
        violations: List[GuardViolation],
    ) -> None:
        for name, pre_sig in pre_sigs.items():
            if name in allowed_mutations:
                continue

            if name not in post_sigs:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.UNAUTHORIZED_DELETION,
                        symbol_name=name,
                        message=f"Function/Method '{name}' was deleted without explicit authorization in allowed_mutations.",
                    )
                )
                continue

            post_sig = post_sigs[name]

            # 1. Asyncness invariant
            if pre_sig.is_async != post_sig.is_async:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Async modifier altered for '{name}'. Pre: is_async={pre_sig.is_async}, Post: is_async={post_sig.is_async}",
                    )
                )

            # 2. Positional Arguments Invariant
            if pre_sig.pos_args != post_sig.pos_args:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Positional arguments changed for '{name}'. Expected {pre_sig.pos_args}, got {post_sig.pos_args}",
                    )
                )

            # 3. Keyword-only Arguments Invariant
            if pre_sig.kwonly_args != post_sig.kwonly_args:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Keyword-only arguments changed for '{name}'. Expected {pre_sig.kwonly_args}, got {post_sig.kwonly_args}",
                    )
                )

            # 4. Defaults count invariant
            if pre_sig.defaults_count != post_sig.defaults_count:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.SIGNATURE_MUTATION,
                        symbol_name=name,
                        message=f"Default parameter count changed for '{name}'. Expected {pre_sig.defaults_count}, got {post_sig.defaults_count}",
                    )
                )

            # 5. Type Annotation Invariant
            for arg_name, pre_ann in pre_sig.annotations.items():
                post_ann = post_sig.annotations.get(arg_name)
                if post_ann != pre_ann:
                    violations.append(
                        GuardViolation(
                            violation_type=ViolationType.TYPE_MISMATCH,
                            symbol_name=f"{name}:{arg_name}",
                            message=f"Type annotation for parameter '{arg_name}' altered in '{name}'. Expected '{pre_ann}', got '{post_ann}'",
                        )
                    )

            if pre_sig.return_annotation != post_sig.return_annotation:
                violations.append(
                    GuardViolation(
                        violation_type=ViolationType.TYPE_MISMATCH,
                        symbol_name=f"{name}:return",
                        message=f"Return type annotation altered for '{name}'. Expected '{pre_sig.return_annotation}', got '{post_sig.return_annotation}'",
                    )
                )


def main() -> int:
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Deterministic AST Guard Validator")
    parser.add_argument(
        "target_path",
        nargs="?",
        default=None,
        help="Path to Python file or directory to scan, or 'all'",
    )
    parser.add_argument(
        "--target",
        dest="target_flag",
        default=None,
        help="Target file or directory to scan, or 'all'",
    )

    args = parser.parse_args()
    raw_target = args.target_flag or args.target_path

    if not raw_target:
        raw_target = "all"

    targets_to_scan: List[Path] = []
    if raw_target.lower() == "all":
        workspace_root = Path(__file__).resolve().parent.parent
        for candidate in ["scripts", "tests", "src_app"]:
            cand_path = workspace_root / candidate
            if cand_path.exists():
                targets_to_scan.append(cand_path)
    else:
        p = Path(raw_target)
        if not p.exists():
            print(f"[ERROR] Path does not exist: {p}")
            return 1
        targets_to_scan.append(p)

    py_files: List[Path] = []
    for t in targets_to_scan:
        if t.is_file() and t.suffix == ".py":
            py_files.append(t)
        elif t.is_dir():
            py_files.extend(sorted([f for f in t.rglob("*.py") if "__pycache__" not in f.parts]))

    py_files = sorted(list(dict.fromkeys(py_files)))

    total_violations = 0
    print("================================================================================")
    print(f"AST GUARD VALIDATOR: Scanning {len(py_files)} files across targets")
    print("================================================================================")

    for py_file in py_files:
        try:
            code = py_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[FAIL] {py_file} - Could not read file: {e}")
            total_violations += 1
            continue

        report = ASTGuardValidator.validate_code_edit(code, code, target_file=py_file.name)
        rel_path = py_file.as_posix()
        if not report.is_valid:
            print(f"[FAIL] {rel_path} - {len(report.violations)} AST violation(s):")
            for v in report.violations:
                loc = f"L{v.line_number}:{v.column}" if v.line_number is not None else "GLOBAL"
                print(f"       - [{v.violation_type.value}] {loc}: {v.message}")
            total_violations += len(report.violations)
        else:
            print(f"[PASS] {rel_path} (Symbols: {report.post_symbol_count})")

    print("================================================================================")
    if total_violations == 0:
        print(f"[RESULT] ALL {len(py_files)} FILES PASSED DETERMINISTIC AST GUARD VALIDATION.")
        return 0
    else:
        print(f"[RESULT] FAILED: {total_violations} total violations detected across {len(py_files)} files.")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())



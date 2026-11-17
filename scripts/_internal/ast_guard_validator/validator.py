"""Classe canonica ASTGuardValidator di coordinamento statico AST."""

from __future__ import annotations

import ast
import difflib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from _internal.ast_guard_validator.models import (
    PROTECTED_SECURITY_ANCHORS,
    FunctionSignatureSnapshot,
    GuardViolation,
    ValidationReport,
    ViolationType,
)
from _internal.ast_guard_validator.reexports import (
    _resolve_local_import_exports,
    _resolve_local_import_roots,
    validate_pydantic_catalog_records,
)
from _internal.ast_guard_validator.sast_checker import SASTConstructChecker
from _internal.ast_guard_validator.scope_checker import ScopeIntegrityChecker
from _internal.ast_guard_validator.signature_collector import SignatureCollector
from _internal.ast_guard_validator.validator_helpers import (
    verify_classes_impl,
    verify_signatures_impl,
)


class ASTGuardValidator:
    """Validatore principale che coordina purezza sintattica, firme, classi e integrita scope."""

    PROTECTED_SECURITY_ANCHORS = PROTECTED_SECURITY_ANCHORS

    def __init__(self, allowed_mutations: Optional[Set[str]] = None) -> None:
        if isinstance(allowed_mutations, str):
            self.allowed_mutations: Set[str] = {
                s.strip() for s in allowed_mutations.split(",") if s.strip()
            }
        elif allowed_mutations is not None:
            self.allowed_mutations = {
                str(s).strip() for s in allowed_mutations if str(s).strip()
            }
        else:
            self.allowed_mutations = set()

    @classmethod
    def validate_pydantic_catalog_records(
        cls, records: List[Dict[str, Any]], model_cls: Any
    ) -> Dict[str, Any]:
        """Delega il Pre-Flight Schema Grounding in RAM su una collezione di record."""
        return validate_pydantic_catalog_records(records, model_cls)

    @classmethod
    def check_sast_constructs(
        cls, code: str, target_file: str = "<target>"
    ) -> List[GuardViolation]:
        """Scansiona l'AST in modalita fail-closed rilevando SyntaxError, costrutti SAST e MagicMock."""
        try:
            tree = ast.parse(code, type_comments=True)
        except (SyntaxError, ValueError) as se:
            return [
                GuardViolation(
                    violation_type=ViolationType.SYNTAX_ERROR,
                    symbol_name=None,
                    line_number=getattr(se, "lineno", None),
                    column=getattr(se, "offset", None),
                    message=f"SyntaxError in {target_file}: {getattr(se, 'msg', str(se))}",
                    diff_context=getattr(se, "text", None),
                    severity="CRITICAL",
                )
            ]
        sast_checker = SASTConstructChecker(target_file=target_file)
        sast_checker.visit(tree)
        return sast_checker.violations

    @classmethod
    def validate_code_edit(
        cls,
        pre_code: str,
        post_code: str,
        allowed_mutations: Optional[Set[str]] = None,
        target_file: str = "<target>",
    ) -> ValidationReport:
        """Esegue la suite completa di guardie AST sulla trasformazione del codice."""
        violations: List[GuardViolation] = []
        allowed = allowed_mutations or set()

        if pre_code == post_code:
            post_tree = cls._parse_or_report(post_code, "post_edit", violations)
            pre_tree = post_tree
        else:
            pre_tree = cls._parse_or_report(pre_code, "pre_edit", violations)
            post_tree = cls._parse_or_report(post_code, "post_edit", violations)

        if post_tree is None:
            return ValidationReport(
                is_valid=False,
                pre_symbol_count=0,
                post_symbol_count=0,
                violations=violations,
                metrics={
                    "fatal_syntax_error": True,
                    "syntax_clean": False,
                    "total_violations": len(violations),
                    "sast_violations_count": len(violations),
                },
            )

        post_collector = SignatureCollector()
        if pre_code == post_code:
            post_collector.skip_unparse = True  # type: ignore[attr-defined]
        post_collector.visit(post_tree)

        if pre_code != post_code:
            _search_roots, _cur_dir = _resolve_local_import_roots(target_file)
            if _search_roots:
                _target_visited: Set[Path] = set()
                try:
                    _raw_t = Path(target_file)
                    _res_t = (
                        _raw_t if _raw_t.is_absolute() else (Path.cwd() / _raw_t)
                    ).resolve()
                    _target_visited.add(_res_t)
                except OSError:
                    pass
                _resolve_local_import_exports(
                    post_tree,
                    post_collector,
                    _search_roots,
                    _cur_dir,
                    skip_unparse=False,
                    visited=_target_visited,
                    cache={},
                )

        if pre_code == post_code:
            pre_collector = post_collector
        else:
            pre_collector = SignatureCollector()
            if pre_tree:
                pre_collector.visit(pre_tree)
            cls._verify_classes(
                pre_collector.class_bases,
                post_collector.class_bases,
                allowed,
                violations,
                target_file=target_file,
            )
            cls._verify_signatures(
                pre_collector.signatures,
                post_collector.signatures,
                allowed,
                violations,
            )

        checker = ScopeIntegrityChecker(global_names=post_collector.defined_globals)
        checker.visit(post_tree)
        violations.extend(checker.violations)

        sast_checker = SASTConstructChecker(target_file=target_file)
        sast_checker.visit(post_tree)
        sast_violations = sast_checker.sast_violations
        violations.extend(sast_violations)

        if pre_code == post_code:
            diff_lines: List[str] = []
        else:
            diff = difflib.unified_diff(
                pre_code.splitlines(),
                post_code.splitlines(),
                fromfile=f"pre/{target_file}",
                tofile=f"post/{target_file}",
                lineterm="",
            )
            diff_lines = list(diff)

        is_valid = len(violations) == 0
        syntax_err_count = sum(
            1 for v in violations if v.violation_type == ViolationType.SYNTAX_ERROR
        )

        return ValidationReport(
            is_valid=is_valid,
            pre_symbol_count=len(pre_collector.signatures) + len(pre_collector.classes),
            post_symbol_count=len(post_collector.signatures)
            + len(post_collector.classes),
            violations=violations,
            metrics={
                "diff_line_count": len(diff_lines),
                "total_violations": len(violations),
                "sast_violations_count": len(sast_violations) + syntax_err_count,
                "sast_violations": [v.message for v in sast_violations],
                "syntax_clean": syntax_err_count == 0,
                "pre_functions": len(pre_collector.signatures),
                "post_functions": len(post_collector.signatures),
                "pre_classes": len(pre_collector.classes),
                "post_classes": len(post_collector.classes),
            },
        )

    @classmethod
    def _parse_or_report(
        cls, code: str, stage: str, violations: List[GuardViolation]
    ) -> Optional[ast.AST]:
        try:
            return ast.parse(code, type_comments=True)
        except (SyntaxError, ValueError) as se:
            violations.append(
                GuardViolation(
                    violation_type=ViolationType.SYNTAX_ERROR,
                    symbol_name=None,
                    line_number=getattr(se, "lineno", None),
                    column=getattr(se, "offset", None),
                    message=f"SyntaxError in {stage}: {getattr(se, 'msg', str(se))}",
                    diff_context=getattr(se, "text", None),
                    severity="CRITICAL",
                )
            )
            return None

    @classmethod
    def _verify_classes(
        cls,
        pre_class_bases: Dict[str, List[str]],
        post_class_bases: Dict[str, List[str]],
        allowed_mutations: Set[str],
        violations: List[GuardViolation],
        target_file: str = "<target>",
    ) -> None:
        verify_classes_impl(
            pre_class_bases,
            post_class_bases,
            allowed_mutations,
            violations,
            target_file=target_file,
        )

    @classmethod
    def _verify_signatures(
        cls,
        pre_sigs: Dict[str, FunctionSignatureSnapshot],
        post_sigs: Dict[str, FunctionSignatureSnapshot],
        allowed_mutations: Set[str],
        violations: List[GuardViolation],
    ) -> None:
        verify_signatures_impl(pre_sigs, post_sigs, allowed_mutations, violations)

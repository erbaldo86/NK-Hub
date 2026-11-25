"""Classe canonica ASTGuardValidator di coordinamento statico AST."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
    _resolve_prod_import_roots,
    _resolve_target_path,
    validate_pydantic_catalog_records,
)
from _internal.ast_guard_validator.sast_checker import SASTConstructChecker
from _internal.ast_guard_validator.scope_checker import ScopeIntegrityChecker
from _internal.ast_guard_validator.signature_collector import SignatureCollector
from _internal.ast_guard_validator.validator_helpers import (
    parse_ast_cached,
    verify_classes_impl,
    verify_signatures_impl,
)


def _compute_visited_set(target_file: str, prod_only: bool = False) -> Set[Path]:
    """Costruisce il set visited iniziale per evitare cicli di auto-importazione."""
    if not target_file or target_file.startswith("<"):
        return set()
    res_t = _resolve_target_path(target_file)
    if prod_only and ".staging" in res_t.parts:
        parts = list(res_t.parts)
        idx = parts.index(".staging")
        rel = parts[idx + 1 :]
        if rel:
            prod_t = Path(*parts[:idx]).joinpath(*rel) if idx > 0 else Path(*rel)
            return {prod_t}
    return {res_t}


def _resolve_pre_exports(
    pre_tree: Optional[ast.AST],
    pre_collector: SignatureCollector,
    target_file: str,
) -> None:
    """Risolve i re-export di pre_collector in isolamento stretto sui soli path di produzione."""
    if pre_tree is None:
        return
    pre_roots, pre_cur_dir = _resolve_prod_import_roots(target_file)
    if not pre_roots:
        return
    _resolve_local_import_exports(
        pre_tree,
        pre_collector,
        pre_roots,
        pre_cur_dir,
        skip_unparse=False,
        visited=_compute_visited_set(target_file, prod_only=True),
        cache={},
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
    def _syntax_error_violation(
        cls, se: Optional[Exception], stage_label: str
    ) -> GuardViolation:
        err = se if se is not None else SyntaxError("parse failure")
        return GuardViolation(
            violation_type=ViolationType.SYNTAX_ERROR,
            symbol_name=None,
            line_number=getattr(err, "lineno", None),
            column=getattr(err, "offset", None),
            message=f"SyntaxError in {stage_label}: {getattr(err, 'msg', str(err))}",
            diff_context=getattr(err, "text", None),
            severity="CRITICAL",
        )

    @classmethod
    def _parse_sast_tree_or_error(
        cls, code: str, target_file: str, tree: Optional[ast.AST]
    ) -> Tuple[Optional[ast.AST], List[GuardViolation]]:
        if tree is not None:
            return tree, []
        parsed, err = parse_ast_cached(code, target_file)
        if parsed is None:
            return None, [cls._syntax_error_violation(err, target_file)]
        return parsed, []

    @classmethod
    def check_sast_constructs(
        cls,
        code: str,
        target_file: str = "<target>",
        tree: Optional[ast.AST] = None,
    ) -> List[GuardViolation]:
        """Scansiona l'AST in modalita fail-closed riusando un eventuale AST gia parsato."""
        parsed_tree, syntax_errs = cls._parse_sast_tree_or_error(code, target_file, tree)
        if parsed_tree is None:
            return syntax_errs
        sast_checker = SASTConstructChecker(target_file=target_file)
        sast_checker.visit(parsed_tree)
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
                _resolve_local_import_exports(
                    post_tree,
                    post_collector,
                    _search_roots,
                    _cur_dir,
                    skip_unparse=False,
                    visited=_compute_visited_set(target_file, prod_only=False),
                    cache={},
                )

        if pre_code == post_code:
            pre_collector = post_collector
        else:
            pre_collector = SignatureCollector()
            if pre_tree:
                pre_collector.visit(pre_tree)
                _resolve_pre_exports(pre_tree, pre_collector, target_file)
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

        diff_line_count = cls._compute_diff_line_count(pre_code, post_code)

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
                "diff_line_count": diff_line_count,
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
    def _compute_diff_line_count(cls, pre_code: str, post_code: str) -> int:
        if pre_code == post_code:
            return 0
        pre_lines = pre_code.splitlines()
        post_lines = post_code.splitlines()
        return sum(1 for a, b in zip(pre_lines, post_lines) if a != b) + abs(
            len(post_lines) - len(pre_lines)
        )

    @classmethod
    def _parse_or_report(
        cls, code: str, stage: str, violations: List[GuardViolation]
    ) -> Optional[ast.AST]:
        parsed, err = parse_ast_cached(code, f"<{stage}>")
        if parsed is None:
            violations.append(cls._syntax_error_violation(err, stage))
            return None
        return parsed

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

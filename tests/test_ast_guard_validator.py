# -*- coding: utf-8 -*-
"""
Nexus Keystone v1.1.0-Universal
Test Module 5: Static AST Guard Validator
7 Tests: Syntactic Purity, Signatures, Type Annotations, Scope Integrity, PEP 634 Match, PEP 695 Type Params, Comprehensions & Walrus.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
SCRIPTS_DIR = STAGING_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(STAGING_DIR))

from ast_guard_validator import ASTGuardValidator, ViolationType


class TestASTGuardValidator(unittest.TestCase):
    def setUp(self):
        self.clean_pre = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier
"""

    # 28. test_syntactic_purity_ast_check
    def test_syntactic_purity_ast_check(self):
        """28. Validates immediate rejection of code with syntax errors."""
        broken_post = "def calculate_sum(items: List[int]:\n    return 42"
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, broken_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.SYNTAX_ERROR for v in rep.violations))

    # 29. test_signature_preservation_invariant
    def test_signature_preservation_invariant(self):
        """29. Validates detection of parameter removal without authorization."""
        mutated_post = """
from typing import List

def calculate_sum(items: List[int]) -> int:
    return sum(items)
"""
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, mutated_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.SIGNATURE_MUTATION for v in rep.violations))

    # 30. test_type_annotation_preservation
    def test_type_annotation_preservation(self):
        """30. Validates detection of type annotation mutations."""
        mutated_post = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> float:
    return float(sum(items) * multiplier)
"""
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, mutated_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.TYPE_MISMATCH for v in rep.violations))

    # 31. test_scope_integrity_unbound_name
    def test_scope_integrity_unbound_name(self):
        """31. Validates detection of undefined/unimported variables."""
        unbound_post = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier + undefined_external_val
"""
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, unbound_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.UNDEFINED_NAME for v in rep.violations))

    # 32. test_scope_integrity_pep634_pattern_matching
    def test_scope_integrity_pep634_pattern_matching(self):
        """32. Validates zero false positives on PEP 634 ast.Match and ast.MatchCase."""
        pep634_code = """
def process_command(command):
    match command:
        case {"type": "write", "data": payload}:
            return payload
        case [first, *rest]:
            return first
        case _:
            return None
"""
        rep = ASTGuardValidator.validate_code_edit(pep634_code, pep634_code)
        self.assertTrue(rep.is_valid, f"PEP 634 should pass cleanly: {rep.violations}")

    # 33. test_scope_integrity_pep695_type_parameters
    def test_scope_integrity_pep695_type_parameters(self):
        """33. Validates zero false positives on PEP 695 type parameters & TypeAlias."""
        code = """
type Vector[T] = list[T]

def identity[T](val: T) -> T:
    return val

class Container[T]:
    def __init__(self, item: T) -> None:
        self.item = item
"""
        rep = ASTGuardValidator.validate_code_edit(code, code)
        self.assertTrue(rep.is_valid, f"PEP 695 should pass cleanly: {rep.violations}")

    # 34. test_scope_integrity_comprehensions_walrus
    def test_scope_integrity_comprehensions_walrus(self):
        """34. Validates zero false positives on comprehensions and walrus operator (:=)."""
        code = """
def process_data(raw_items: list[str]) -> list[int]:
    results = [n for item in raw_items if (n := len(item)) > 3]
    return results
"""
        rep = ASTGuardValidator.validate_code_edit(code, code)
        self.assertTrue(rep.is_valid, f"Comprehensions and walrus should pass: {rep.violations}")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Nexus Keystone v3.0.0-STE100-Unified
Modulo di test 5: Static AST Guard Validator.
Valida purezza sintattica, firme, annotazioni di tipo, scope, PEP 634, PEP 695 e walrus.
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
        """28. Valida il rifiuto immediato di codice con errori di sintassi."""
        broken_post = "def calculate_sum(items: List[int]:\n    return 42"
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, broken_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.SYNTAX_ERROR for v in rep.violations))

    # 29. test_signature_and_type_preservation
    def test_signature_and_type_preservation(self):
        """29. Valida il rilevamento di rimozione parametri e mutazioni di tipo."""
        mutated_param = """
from typing import List

def calculate_sum(items: List[int]) -> int:
    return sum(items)
"""
        rep_a = ASTGuardValidator.validate_code_edit(self.clean_pre, mutated_param)
        self.assertFalse(rep_a.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.SIGNATURE_MUTATION for v in rep_a.violations))

        mutated_type = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> float:
    return float(sum(items) * multiplier)
"""
        rep_b = ASTGuardValidator.validate_code_edit(self.clean_pre, mutated_type)
        self.assertFalse(rep_b.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.TYPE_MISMATCH for v in rep_b.violations))

    # 30. test_scope_integrity_unbound_name
    def test_scope_integrity_unbound_name(self):
        """30. Valida il rilevamento di variabili, decoratori e default non definiti."""
        unbound_post = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier + undefined_external_val
"""
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, unbound_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any(v.violation_type == ViolationType.UNDEFINED_NAME for v in rep.violations))

        # Undefined decorator
        rep_dec = ASTGuardValidator.validate_code_edit("", "@undefined_decorator\ndef foo(): pass\n")
        self.assertFalse(rep_dec.is_valid)
        self.assertTrue(any(v.symbol_name == "undefined_decorator" for v in rep_dec.violations))

        # Undefined default arg
        rep_def = ASTGuardValidator.validate_code_edit("", "def bar(val=undefined_default): pass\n")
        self.assertFalse(rep_def.is_valid)
        self.assertTrue(any(v.symbol_name == "undefined_default" for v in rep_def.violations))

    # 32. test_scope_integrity_pep634_pattern_matching
    def test_scope_integrity_pep634_pattern_matching(self):
        """32. Valida zero falsi positivi su PEP 634 ast.Match e ast.MatchCase."""
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
    @unittest.skipIf(sys.version_info < (3, 12), "PEP 695 type parameters require Python 3.12+")
    def test_scope_integrity_pep695_type_parameters(self):
        """33. Valida zero falsi positivi su PEP 695 type parameters e TypeAlias."""
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
        """34. Valida zero falsi positivi su comprehension e operatore walrus."""
        code = """
def process_data(raw_items: list[str]) -> list[int]:
    results = [n for item in raw_items if (n := len(item)) > 3]
    return results
"""
        rep = ASTGuardValidator.validate_code_edit(code, code)
        self.assertTrue(rep.is_valid, f"Comprehensions and walrus should pass: {rep.violations}")


if __name__ == "__main__":
    unittest.main()

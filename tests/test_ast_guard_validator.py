# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Static AST Guard Validator e Guardia GT-14 (v3.3.0).
Modulo: tests/test_ast_guard_validator.py.
Valida purezza sintattica, firme, annotazioni di tipo, scope, PEP 634/695, walrus e GT-14.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
STAGING_DIR = CURRENT_DIR.parent
WORKSPACE_ROOT = (
    STAGING_DIR.parent if STAGING_DIR.name == ".staging" else STAGING_DIR
)
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from ast_guard_validator import ASTGuardValidator, ViolationType


class TestASTGuardValidator(unittest.TestCase):
    def setUp(self):
        self.clean_pre = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier
"""

    def test_syntactic_purity_ast_check(self):
        """1. Valida rifiuto errori di sintassi, SAST construct check e permessi Auditor (GT-14)."""
        broken_post = "def calculate_sum(items: List[int]:\n    return 42"
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, broken_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(
            any(v.violation_type == ViolationType.SYNTAX_ERROR for v in rep.violations)
        )

        auditors = [
            "NK-Static-AST-Guard",
            "NK-DAST-Sandbox-Runner",
            "NK-SBFL-Fault-Localizer",
            "NK-Oracle-Evaluator",
            "NK-Cold-Reviewer",
            "NK-Documentation-Verifier",
            "NK-RSI-Auditor",
        ]
        for skill_name in auditors:
            skill_md = WORKSPACE_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
            if skill_md.exists():
                frontmatter = skill_md.read_text(encoding="utf-8").split("---")[1]
                self.assertNotIn("write_to_file", frontmatter)
                self.assertNotIn("enable_write_tools: true", frontmatter)

    def test_signature_and_type_preservation(self):
        """2. Valida il rilevamento di rimozione parametri e mutazioni di tipo."""
        mutated_param = """
from typing import List

def calculate_sum(items: List[int]) -> int:
    return sum(items)
"""
        rep_a = ASTGuardValidator.validate_code_edit(self.clean_pre, mutated_param)
        self.assertFalse(rep_a.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.SIGNATURE_MUTATION
                for v in rep_a.violations
            )
        )

        mutated_type = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> float:
    return float(sum(items) * multiplier)
"""
        rep_b = ASTGuardValidator.validate_code_edit(self.clean_pre, mutated_type)
        self.assertFalse(rep_b.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.TYPE_MISMATCH
                for v in rep_b.violations
            )
        )

    def test_scope_integrity_unbound_name(self):
        """3. Valida il rilevamento di variabili, decoratori e default non definiti."""
        unbound_post = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier + undefined_external_val
"""
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, unbound_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.UNDEFINED_NAME
                for v in rep.violations
            )
        )

        rep_dec = ASTGuardValidator.validate_code_edit(
            "", "@undefined_decorator\ndef foo(): pass\n"
        )
        self.assertFalse(rep_dec.is_valid)

        rep_def = ASTGuardValidator.validate_code_edit(
            "", "def bar(val=undefined_default): pass\n"
        )
        self.assertFalse(rep_def.is_valid)

    def test_scope_integrity_comprehensions_walrus(self):
        """4. Valida zero falsi positivi su PEP 634 Match, PEP 695 TypeParams e walrus."""
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
        rep_match = ASTGuardValidator.validate_code_edit(pep634_code, pep634_code)
        self.assertTrue(rep_match.is_valid)

        if sys.version_info >= (3, 12):
            pep695_code = """
type Vector[T] = list[T]
def identity[T](val: T) -> T:
    return val
"""
            rep_695 = ASTGuardValidator.validate_code_edit(pep695_code, pep695_code)
            self.assertTrue(rep_695.is_valid)

        walrus_code = """
def process_data(raw_items: list[str]) -> list[int]:
    results = [n for item in raw_items if (n := len(item)) > 3]
    return results
"""
        rep_walrus = ASTGuardValidator.validate_code_edit(walrus_code, walrus_code)
        self.assertTrue(rep_walrus.is_valid)


if __name__ == "__main__":
    unittest.main()

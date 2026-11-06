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
STAGING_SCRIPTS_DIR = WORKSPACE_ROOT / ".staging" / "scripts"

for _p in (WORKSPACE_ROOT, SCRIPTS_DIR, STAGING_SCRIPTS_DIR):
    if _p.exists():
        _ps = str(_p)
        if _ps in sys.path:
            sys.path.remove(_ps)
        sys.path.insert(0, _ps)

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

    def test_c2_c3_c4_c6_and_nested_scope_fixes(self):
        """5. Valida C2 (default posizionale), C3 (kwonly default), C4 (_helper), C6 (Optional/Union) e scope."""
        # C2: aggiunta valore di default a parametro posizionale esistente
        pre_c2 = "def compute(a: int, b: int) -> int:\n    return a + b\n"
        post_c2 = "def compute(a: int, b: int = 10) -> int:\n    return a + b\n"
        rep_c2 = ASTGuardValidator.validate_code_edit(pre_c2, post_c2)
        self.assertTrue(rep_c2.is_valid, f"C2 failed: {rep_c2.violations}")

        # C3: aggiunta nuovo parametro kwonly_args con default consentita, senza default bloccata
        pre_c3 = "def fetch(url: str) -> str:\n    return url\n"
        post_c3_ok = "def fetch(url: str, *, timeout: float = 5.0) -> str:\n    return url\n"
        rep_c3_ok = ASTGuardValidator.validate_code_edit(pre_c3, post_c3_ok)
        self.assertTrue(rep_c3_ok.is_valid, f"C3 ok failed: {rep_c3_ok.violations}")

        post_c3_bad = "def fetch(url: str, *, timeout: float) -> str:\n    return url\n"
        rep_c3_bad = ASTGuardValidator.validate_code_edit(pre_c3, post_c3_bad)
        self.assertFalse(rep_c3_bad.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.SIGNATURE_MUTATION
                for v in rep_c3_bad.violations
            )
        )

        # C4: eliminazione helper privato _helper esente, ma __dunder__ o funzione pubblica bloccata
        pre_c4 = (
            "def _internal_helper(x: int) -> int:\n    return x + 1\n\n"
            "def public_api(x: int) -> int:\n    return x + 1\n"
        )
        post_c4_ok = "def public_api(x: int) -> int:\n    return x + 1\n"
        rep_c4_ok = ASTGuardValidator.validate_code_edit(pre_c4, post_c4_ok)
        self.assertTrue(rep_c4_ok.is_valid, f"C4 failed: {rep_c4_ok.violations}")

        pre_dunder = "class Box:\n    def __init__(self, v: int) -> None:\n        self.v = v\n"
        post_dunder = "class Box:\n    pass\n"
        rep_dunder = ASTGuardValidator.validate_code_edit(pre_dunder, post_dunder)
        self.assertFalse(rep_dunder.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.UNAUTHORIZED_DELETION
                for v in rep_dunder.violations
            )
        )

        # C6: normalizzazione annotazioni equivalenti Optional[T] <-> T | None <-> Union[T, None]
        pre_c6 = (
            "from typing import Optional, List\n"
            "def parse(tag: Optional[str], items: List[int]) -> Optional[int]:\n"
            "    return len(items) if tag else None\n"
        )
        post_c6 = (
            "from typing import Union\n"
            "def parse(tag: str | None, items: list[int]) -> Union[int, None]:\n"
            "    return len(items) if tag else None\n"
        )
        rep_c6 = ASTGuardValidator.validate_code_edit(pre_c6, post_c6)
        self.assertTrue(rep_c6.is_valid, f"C6 failed: {rep_c6.violations}")

        # Scope: variabile definita in funzione annidata non deve trapelare nello scope esterno
        leak_nested = (
            "def outer() -> int:\n"
            "    def inner() -> int:\n"
            "        secret_inner = 42\n"
            "        return secret_inner\n"
            "    return secret_inner\n"
        )
        rep_nested = ASTGuardValidator.validate_code_edit(leak_nested, leak_nested)
        self.assertFalse(rep_nested.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.UNDEFINED_NAME
                and v.symbol_name == "secret_inner"
                for v in rep_nested.violations
            )
        )

        # C7: user_grants non genera falso positivo SAST-GAMING-D04
        domain_grants_code = (
            "def has_many_permissions(user_grants: list) -> bool:\n"
            "    return len(user_grants) >= 12\n"
        )
        rep_c7 = ASTGuardValidator.validate_code_edit(
            domain_grants_code,
            domain_grants_code,
            target_file="src_app/auth_service.py",
        )
        self.assertTrue(rep_c7.is_valid, f"C7 false positive: {rep_c7.violations}")
        walrus_comp = "def f():\n    items = [y := x + 1 for x in range(3)]\n    return y + len(items)\n"
        rep_m06_ok = ASTGuardValidator.validate_code_edit(walrus_comp, walrus_comp)
        self.assertTrue(rep_m06_ok.is_valid)
        walrus_no_comp = "def outer():\n    def inner():\n        return (z_local := 1)\n    return z_local\n"
        rep_m06_bad = ASTGuardValidator.validate_code_edit(walrus_no_comp, walrus_no_comp)
        self.assertFalse(rep_m06_bad.is_valid)
        yaml_bad_code = "from yaml import load\ndef parse_y(d: str):\n    return load(d)\n"
        rep_m09_bad = ASTGuardValidator.validate_code_edit(yaml_bad_code, yaml_bad_code)
        self.assertFalse(rep_m09_bad.is_valid)
        self.assertTrue(any(v.symbol_name == "yaml.load" for v in rep_m09_bad.violations))
        yaml_ok_code = "import yaml\ndef parse_y(d: str):\n    return yaml.load(d, Loader=yaml.SafeLoader)\n"
        rep_m09_ok = ASTGuardValidator.validate_code_edit(yaml_ok_code, yaml_ok_code)
        self.assertTrue(rep_m09_ok.is_valid)


if __name__ == "__main__":
    unittest.main()

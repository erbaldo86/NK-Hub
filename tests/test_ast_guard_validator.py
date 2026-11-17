# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Static AST Guard Validator e Guardia GT-14 (v6.4.0-Carbon).
Modulo: tests/test_ast_guard_validator.py.
Valida purezza sintattica, firme, annotazioni di tipo, scope, alias SAST, PEP 634/695, walrus e GT-14.
"""

from __future__ import annotations

import sys
import unittest

import pytest

try:
    from conftest import WORKSPACE_ROOT, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, load_nk_script_module

_agv_mod = load_nk_script_module("ast_guard_validator")
ASTGuardValidator = _agv_mod.ASTGuardValidator
ViolationType = _agv_mod.ViolationType

pytestmark = pytest.mark.fast


class TestASTGuardValidator(unittest.TestCase):
    """Test di regressione e chiusura branch per ASTGuardValidator."""

    def setUp(self):
        self.clean_pre = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier
"""

    def test_syntactic_purity_ast_check(self):
        """Valida rifiuto errori di sintassi, SAST construct check e permessi Auditor (GT-14)."""
        broken_post = "def calculate_sum(items: List[int]:\n    return 42"
        rep = ASTGuardValidator.validate_code_edit(self.clean_pre, broken_post)
        self.assertFalse(rep.is_valid)
        self.assertTrue(
            any(v.violation_type == ViolationType.SYNTAX_ERROR for v in rep.violations)
        )

        auditors = [
            "NK-Ideator",
            "NK-Bug-Diagnostic-Engine",
            "NK-Security-Auditor",
            "NK-Dynamic-Sandbox-StressTester",
            "NK-Oracle-Evaluator",
        ]
        for skill_name in auditors:
            skill_md = WORKSPACE_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
            self.assertTrue(skill_md.is_file())
            frontmatter = skill_md.read_text(encoding="utf-8").split("---")[1]
            self.assertNotIn("write_to_file", frontmatter)
            self.assertNotIn("enable_write_tools: true", frontmatter)

    def test_signature_and_type_preservation(self):
        """Valida il rilevamento di rimozione parametri e mutazioni di tipo."""
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
        """Valida il rilevamento di variabili, decoratori e default non definiti."""
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
        """Valida zero falsi positivi su PEP 634 Match, PEP 695 TypeParams e walrus."""
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
        """Valida C2 (default posizionale), C3 (kwonly), C4 (_helper), C6 (Union) e nested leak."""
        pre_c2 = "def compute(a: int, b: int) -> int:\n    return a + b\n"
        post_c2 = "def compute(a: int, b: int = 10) -> int:\n    return a + b\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit(pre_c2, post_c2).is_valid)

        pre_c3 = "def fetch(url: str) -> str:\n    return url\n"
        post_c3_ok = "def fetch(url: str, *, timeout: float = 5.0) -> str:\n    return url\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit(pre_c3, post_c3_ok).is_valid)

        post_c3_bad = "def fetch(url: str, *, timeout: float) -> str:\n    return url\n"
        rep_c3_bad = ASTGuardValidator.validate_code_edit(pre_c3, post_c3_bad)
        self.assertFalse(rep_c3_bad.is_valid)
        self.assertTrue(
            any(v.violation_type == ViolationType.SIGNATURE_MUTATION for v in rep_c3_bad.violations)
        )

        pre_c4 = (
            "def _internal_helper(x: int) -> int:\n    return x + 1\n\n"
            "def public_api(x: int) -> int:\n    return x + 1\n"
        )
        post_c4_ok = "def public_api(x: int) -> int:\n    return x + 1\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit(pre_c4, post_c4_ok).is_valid)

        pre_dunder = "class Box:\n    def __init__(self, v: int) -> None:\n        self.v = v\n"
        rep_dunder = ASTGuardValidator.validate_code_edit(pre_dunder, "class Box:\n    pass\n")
        self.assertFalse(rep_dunder.is_valid)
        self.assertTrue(
            any(v.violation_type == ViolationType.UNAUTHORIZED_DELETION for v in rep_dunder.violations)
        )

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
        self.assertTrue(ASTGuardValidator.validate_code_edit(pre_c6, post_c6).is_valid)

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
                v.violation_type == ViolationType.UNDEFINED_NAME and v.symbol_name == "secret_inner"
                for v in rep_nested.violations
            )
        )

    def test_domain_grants_walrus_and_yaml_loader(self):
        """Valida assenza falsi positivi C7, walrus in comprehension e yaml.load."""
        domain_grants_code = (
            "def has_many_permissions(user_grants: list) -> bool:\n"
            "    return len(user_grants) >= 12\n"
        )
        rep_c7 = ASTGuardValidator.validate_code_edit(
            domain_grants_code, domain_grants_code, target_file="src_app/auth_service.py"
        )
        self.assertTrue(rep_c7.is_valid, f"C7 false positive: {rep_c7.violations}")

        walrus_comp = "def f():\n    items = [y := x + 1 for x in range(3)]\n    return y + len(items)\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit(walrus_comp, walrus_comp).is_valid)

        walrus_no_comp = "def outer():\n    def inner():\n        return (z_local := 1)\n    return z_local\n"
        self.assertFalse(ASTGuardValidator.validate_code_edit(walrus_no_comp, walrus_no_comp).is_valid)

        yaml_bad = "from yaml import load\ndef parse_y(d: str):\n    return load(d)\n"
        rep_bad = ASTGuardValidator.validate_code_edit(yaml_bad, yaml_bad)
        self.assertFalse(rep_bad.is_valid)
        self.assertTrue(any(v.symbol_name == "yaml.load" for v in rep_bad.violations))

        yaml_ok = "import yaml\ndef parse_y(d: str):\n    return yaml.load(d, Loader=yaml.SafeLoader)\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit(yaml_ok, yaml_ok).is_valid)

        yaml_pos_ok = "import yaml\ndef parse_p(d: str):\n    return yaml.load(d, yaml.SafeLoader)\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit(yaml_pos_ok, yaml_pos_ok).is_valid)

        yaml_unsafe = "import yaml\ndef parse_u(d: str):\n    return yaml.unsafe_load(d)\n"
        self.assertFalse(ASTGuardValidator.validate_code_edit(yaml_unsafe, yaml_unsafe).is_valid)

    def test_sast_evasion_vectors_and_global_nonlocal_scope(self):
        """Valida il blocco dei vettori di evasione SAST, compile e global/nonlocal."""
        evasion_snippets = [
            'def f():\n    return compile("x=1", "<str>", "exec")\n',
            'def f():\n    return getattr(__builtins__, f"{\'ev\'}al")\n',
            'def f():\n    return getattr(__builtins__, "".join(["ev", "al"]))\n',
            'def f():\n    return __builtins__["eval"]\n',
            'import builtins\ndef f():\n    return builtins.__dict__["exec"]\n',
            'import importlib\ndef f():\n    return importlib.import_module("os")\n',
            'import operator\ndef f():\n    return operator.attrgetter("eval")\n',
            'import os\ndef f():\n    return os.execv("/bin/sh", ["sh"])\n',
            'import os\ndef f():\n    return os.spawnv(0, "/bin/sh", ["sh"])\n',
        ]
        for snippet in evasion_snippets:
            rep = ASTGuardValidator.validate_code_edit("", snippet)
            self.assertFalse(rep.is_valid, f"Evasion not blocked for: {snippet}")
            self.assertTrue(
                any(v.violation_type == ViolationType.SAST_VIOLATION for v in rep.violations),
                f"Missing SAST_VIOLATION for: {snippet}",
            )

        global_nonlocal_code = (
            "def outer_fn() -> int:\n"
            "    global GLOBAL_SHARED_STATE\n"
            "    def inner_fn() -> int:\n"
            "        nonlocal ENCLOSING_STATE\n"
            "        return GLOBAL_SHARED_STATE + ENCLOSING_STATE\n"
            "    return inner_fn()\n"
        )
        rep_gn = ASTGuardValidator.validate_code_edit(
            global_nonlocal_code, global_nonlocal_code
        )
        self.assertTrue(rep_gn.is_valid, f"B4.2 global/nonlocal failed: {rep_gn.violations}")

    def test_sast_import_aliases_blocked_crit05(self):
        """Valida CRIT-05: blocco SAST su alias di importazione."""
        alias_snippets = [
            "import subprocess as sp\ndef run_bad() -> None:\n    sp.Popen(['cmd', '/c', 'dir'], shell=True)\n",
            "from subprocess import Popen as spawn_cmd\ndef run_bad2() -> None:\n    spawn_cmd('echo 1', shell=True)\n",
            "import pickle as pkl\ndef load_bad(raw: bytes):\n    return pkl.loads(raw)\n",
            "import os as operating_sys\ndef sys_bad() -> int:\n    return operating_sys.system('whoami')\n",
        ]
        for snippet in alias_snippets:
            rep = ASTGuardValidator.validate_code_edit("", snippet, target_file="src/alias_evasion.py")
            self.assertFalse(rep.is_valid, f"Alias SAST evasion not blocked: {snippet}")
            self.assertTrue(
                any(v.violation_type == ViolationType.SAST_VIOLATION for v in rep.violations),
                f"Expected SAST_VIOLATION on alias snippet: {snippet}",
            )

    def test_wp_r1_scope_and_getattribute_evasion(self):
        """Valida WP-R1: UnboundLocalError, class LEGB leak, comprehension class iter e __getattribute__."""
        unbound_local = "def f():\n    y = x + 1\n    x = 2\n    return y\n"
        rep_ub = ASTGuardValidator.validate_code_edit("", unbound_local)
        self.assertFalse(rep_ub.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.UNDEFINED_NAME and v.symbol_name == "x"
                for v in rep_ub.violations
            )
        )

        unbound_shadow = "G_VAL = 10\ndef f():\n    y = G_VAL + 1\n    G_VAL = 2\n    return y\n"
        rep_sh = ASTGuardValidator.validate_code_edit("", unbound_shadow)
        self.assertFalse(rep_sh.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.UNDEFINED_NAME and v.symbol_name == "G_VAL"
                for v in rep_sh.violations
            )
        )

        class_leak = "class Box:\n    secret = 42\n    def reveal(self) -> int:\n        return secret\n"
        rep_cls = ASTGuardValidator.validate_code_edit("", class_leak)
        self.assertFalse(rep_cls.is_valid)
        self.assertTrue(
            any(
                v.violation_type == ViolationType.UNDEFINED_NAME and v.symbol_name == "secret"
                for v in rep_cls.violations
            )
        )

        class_comp_ok = "class Table:\n    ITEMS = [1, 2, 3]\n    DOUBLED = [x * 2 for x in ITEMS]\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit("", class_comp_ok).is_valid)

        closure_ok = "def outer():\n    def inner():\n        return late_v\n    late_v = 9\n    return inner()\n"
        self.assertTrue(ASTGuardValidator.validate_code_edit("", closure_ok).is_valid)

        getattribute_evasions = [
            'def f():\n    return __builtins__.__getattribute__("".join(["ev", "al"]))("1")\n',
            'def f():\n    fn = "".join(["ev", "al"])\n    return __builtins__.__getattribute__(fn)("1")\n',
            'def f():\n    return object.__getattribute__(__builtins__, "".join(["ev", "al"]))("1")\n',
        ]
        for snippet in getattribute_evasions:
            rep_ga = ASTGuardValidator.validate_code_edit("", snippet)
            self.assertFalse(rep_ga.is_valid, f"__getattribute__ not blocked: {snippet}")
            self.assertTrue(
                any(v.violation_type == ViolationType.SAST_VIOLATION for v in rep_ga.violations),
                f"Expected SAST_VIOLATION for: {snippet}",
            )

    def test_scope_checker_async_delete_augassign_and_match_variants(self):
        """Chiude i branch su del tupla, AsyncFor/AsyncWith, AugAssign, lambda, dict/set comp e Match."""
        valid_complex = """
class Box:
    def __init__(self, v: int) -> None:
        self.v = v

async def run_async(stream, ctx_mgr, mapping, obj):
    a = 1
    b = 2
    del (a, b)
    c = [10]
    del c[0]
    obj.v += 1
    fn = lambda *args, k=5, **kw: (args, k, kw)
    dcomp = {str(i): i for i in range(2)}
    scomp = {i for i in range(2)}
    gcomp = sum(i for i in range(2))
    async for item in stream:
        pass
    async with ctx_mgr as handle:
        pass
    match mapping:
        case {"k": val, **rest_map}:
            return (val, rest_map, fn, dcomp, scomp, gcomp, handle)
        case Box(v=1 | 2):
            return 2
        case _:
            return 0
"""
        rep_ok = ASTGuardValidator.validate_code_edit("", valid_complex)
        self.assertTrue(rep_ok.is_valid, f"Valid scope constructs rejected: {rep_ok.violations}")

        bad_snippets = [
            "def f():\n    del a\n    return a\n",
            "def f():\n    x += 1\n    x = 2\n",
            "def f():\n    y += 1\n",
            "def f():\n    fn = lambda bad_arg=missing_def: bad_arg\n    return fn\n",
        ]
        for bad in bad_snippets:
            self.assertFalse(ASTGuardValidator.validate_code_edit("", bad).is_valid, bad)

        if sys.version_info >= (3, 12):
            bad_alias = "type BadVec[T] = MissingBase[T]\n"
            self.assertFalse(ASTGuardValidator.validate_code_edit("", bad_alias).is_valid)

        nested_walrus = (
            "def f(rows):\n"
            "    tot = 1\n"
            "    del tot\n"
            "    res = [tot := r for r in rows]\n"
            "    return (tot, res)\n"
        )
        self.assertTrue(ASTGuardValidator.validate_code_edit("", nested_walrus).is_valid)

    def test_sast_eval_string_folding_truthiness_and_tuple_unpacking(self):
        """Chiude i branch di sast_eval su NamedExpr, unpack, chr, reversed, slice negativo e truthiness."""
        blocked_vectors = [
            'import os\ndef f():\n    return (x := os).system("id")\n',
            'import os, subprocess\ndef f():\n    a, b = os, subprocess\n    return a.system("id")\n',
            'import builtins\ndef f():\n    fn = "".join(reversed("lave"))\n    return getattr(builtins, fn)("1")\n',
            'import builtins\ndef f():\n    fn = chr(101) + "val"\n    return getattr(builtins, fn)("1")\n',
            'import builtins\ndef f():\n    fn = "lave"[::-1]\n    return getattr(builtins, fn)("1")\n',
            'import sys\ndef f():\n    return sys.modules.get("os").system("id")\n',
            'import sys\ndef f():\n    return sys.modules["os"].system("id")\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=not {})\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=bool(1))\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=(1 if True else 0))\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=(False or True))\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=(True and True))\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=~0)\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=-1)\n',
            'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=not [])\n',
            'import subprocess\ndef f():\n    truth = 1\n    return subprocess.run(["cmd"], shell=truth)\n',
        ]
        for snippet in blocked_vectors:
            rep = ASTGuardValidator.validate_code_edit("", snippet)
            self.assertFalse(rep.is_valid, f"Expected block for: {snippet}")
            self.assertTrue(
                any(v.violation_type == ViolationType.SAST_VIOLATION for v in rep.violations),
                snippet,
            )

        safe_shell = 'import subprocess\ndef f():\n    return subprocess.run(["echo"], shell=not True)\n'
        self.assertTrue(ASTGuardValidator.validate_code_edit("", safe_shell).is_valid)

    def test_sast_call_checks_traversal_sql_pty_async_and_mocks(self):
        """Chiude i branch di sast_call_checks su traversal, SQL f-string, pty, asyncio, kwargs e Mock."""
        blocked_calls = [
            'import os\ndef f(b):\n    return os.path.join(b, "../secret.txt")\n',
            'from pathlib import Path\ndef f(b):\n    return Path(b).joinpath("..", "etc")\n',
            'import pty\ndef f():\n    return pty.spawn("/bin/sh")\n',
            'import asyncio\nasync def f():\n    return await asyncio.create_subprocess_shell("id")\n',
            'import subprocess\ndef f():\n    return subprocess.getoutput("id")\n',
            'import subprocess\ndef f(kw):\n    return subprocess.run(["echo"], **kw)\n',
            'def f(cur, uid):\n    return cur.execute(f"SELECT * FROM u WHERE id={uid}")\n',
            'from unittest.mock import MagicMock\ndef f():\n    return MagicMock()\n',
        ]
        for snippet in blocked_calls:
            rep = ASTGuardValidator.validate_code_edit(
                "", snippet, target_file="scripts/sample_mod.py"
            )
            self.assertFalse(rep.is_valid, f"Expected violation for: {snippet}")


if __name__ == "__main__":
    unittest.main()
